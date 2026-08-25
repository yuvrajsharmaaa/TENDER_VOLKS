import os
import re
import json
import time
import logging
from collections import defaultdict
from threading import Lock
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from fastapi import APIRouter, HTTPException, Request as FastAPIRequest, status
from pydantic import BaseModel, Field
from typing import Optional
import redis

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["notify"])

# Strict format regex for Telegram bot tokens: <8-12 digits>:<30-50 alphanumeric/dash/underscore chars>
TELEGRAM_BOT_TOKEN_REGEX = re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{30,50}$")
# Strict format for Telegram chat IDs (numeric or channel username)
TELEGRAM_CHAT_ID_REGEX = re.compile(r"^(@[A-Za-z0-9_]{5,32}|-?\d{1,20})$")


class RateLimiter:
    """
    Hybrid sliding-window rate limiter per client IP.
    Uses Redis sorted sets for distributed / multi-worker deployments when available,
    and seamlessly falls back to a thread-safe in-memory sliding window when Redis is offline.
    Default: max 10 notifications per 60 seconds.
    """
    def __init__(self, max_requests: int = 10, window_seconds: int = 60, redis_url: Optional[str] = None):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()
        self._redis_client: Optional[redis.Redis] = None
        self._redis_url = redis_url
        self._last_redis_check_failed: float = 0.0
        self._redis_retry_cooldown: float = 30.0  # seconds to wait before retrying broken Redis connection

    def _get_redis(self) -> Optional[redis.Redis]:
        if self._redis_client is not None:
            return self._redis_client

        now = time.time()
        # Prevent blocking connect attempts on every request if Redis is down
        if now - self._last_redis_check_failed < self._redis_retry_cooldown:
            return None

        target_url = self._redis_url or os.getenv("REDIS_URL") or getattr(settings, "redis_url", None)
        if target_url:
            try:
                client = redis.Redis.from_url(
                    target_url,
                    decode_responses=False,
                    socket_timeout=0.5,
                    socket_connect_timeout=0.5
                )
                client.ping()
                self._redis_client = client
                return self._redis_client
            except Exception as e:
                logger.debug(f"[NOTIFY] Redis unavailable for rate limiting ({e}); utilizing in-memory limiter.")
                self._redis_client = None
                self._last_redis_check_failed = now
        return None

    def is_allowed(self, client_ip: str) -> tuple[bool, int]:
        now = time.time()

        # 1. Distributed Redis Sliding Window
        r = self._get_redis()
        if r is not None:
            try:
                key = f"ratelimit:notify:{client_ip}"
                clear_before = now - self.window_seconds
                pipe = r.pipeline()
                pipe.zremrangebyscore(key, 0, clear_before)
                pipe.zadd(key, {str(now): now})
                pipe.zrange(key, 0, 0, withscores=True)
                pipe.zcard(key)
                pipe.expire(key, self.window_seconds * 2)
                results = pipe.execute()

                oldest_entry = results[2]  # list of tuples (member, score)
                count = results[3]

                if count > self.max_requests:
                    if oldest_entry:
                        oldest_ts = float(oldest_entry[0][1])
                        retry_after = max(1, int(self.window_seconds - (now - oldest_ts)))
                    else:
                        retry_after = self.window_seconds
                    return False, retry_after
                return True, 0
            except Exception as redis_err:
                logger.debug(f"[NOTIFY] Redis rate limit check error ({redis_err}), using in-memory fallback.")
                self._redis_client = None
                self._last_redis_check_failed = now

        # 2. In-Memory Thread-Safe Sliding Window Fallback
        with self.lock:
            # Clean up old timestamps for this IP
            timestamps = [t for t in self.requests[client_ip] if now - t < self.window_seconds]
            self.requests[client_ip] = timestamps

            if len(timestamps) >= self.max_requests:
                oldest = timestamps[0]
                retry_after = max(1, int(self.window_seconds - (now - oldest)))
                return False, retry_after

            self.requests[client_ip].append(now)

            # Periodic cleanup of completely stale IPs to prevent memory leaks
            if len(self.requests) > 1000:
                stale_keys = [k for k, v in self.requests.items() if not v or (now - v[-1] > self.window_seconds * 2)]
                for k in stale_keys:
                    del self.requests[k]

            return True, 0


limiter = RateLimiter(max_requests=10, window_seconds=60)


class NotifyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096, description="Message/note to send to team Telegram bot")
    sender: Optional[str] = Field("Dashboard", max_length=100, description="Sender display name")


def validate_telegram_url(bot_token: str) -> str:
    """
    Validates bot token format and constructs/validates an explicit HTTPS URL to api.telegram.org
    to prevent SSRF vulnerabilities (CWE-918).
    """
    clean_token = str(bot_token).strip()
    if not TELEGRAM_BOT_TOKEN_REGEX.match(clean_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram bot token format."
        )

    # Safe quoting preserves ':' necessary for Telegram bot endpoint path
    safe_bot_token = quote(clean_token, safe=":")
    telegram_url = f"https://api.telegram.org/bot{safe_bot_token}/sendMessage"

    # Enforce strict domain and scheme validation
    parsed = urlsplit(telegram_url)
    if parsed.scheme != "https" or parsed.hostname != "api.telegram.org" or (parsed.port not in (None, 443)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram destination endpoint."
        )

    expected_path = f"/bot{safe_bot_token}/sendMessage"
    if parsed.path != expected_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram request path."
        )

    return telegram_url


@router.post("/notify", status_code=200)
async def send_team_notification(payload: NotifyRequest, request: FastAPIRequest):
    """
    Sends review notes / alerts from the Tender OCR Dashboard directly to a Telegram team chat bot.
    Includes distributed rate limiting, SSRF protection, credential sanitization in logs, and input validation.
    """
    # 1. Rate Limiting Check (Distributed Redis or In-Memory fallback)
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = limiter.is_allowed(client_ip)
    if not allowed:
        logger.warning(f"[NOTIFY] Rate limit exceeded for client {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Please wait {retry_after} seconds before sending another notification.",
            headers={"Retry-After": str(retry_after)}
        )

    # 2. Credential Verification
    raw_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if raw_token is None:
        raw_token = getattr(settings, "telegram_bot_token", None)
    
    raw_chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if raw_chat_id is None:
        raw_chat_id = getattr(settings, "telegram_chat_id", None)

    bot_token = str(raw_token).strip() if raw_token else ""
    chat_id = str(raw_chat_id).strip() if raw_chat_id else ""

    if not bot_token or not chat_id or bot_token in ("your_bot_token_here", "") or chat_id in ("your_chat_id_here", ""):
        logger.error("[NOTIFY] Missing or unconfigured TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in settings or env vars.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram bot credentials not configured on server (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing)."
        )

    if not TELEGRAM_CHAT_ID_REGEX.match(chat_id):
        logger.error("[NOTIFY] Invalid TELEGRAM_CHAT_ID format.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Telegram chat ID format."
        )

    # 3. Input Validation & Sanitization
    clean_message = payload.message.strip()
    if not clean_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty."
        )

    if len(clean_message) > 4096:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content exceeds maximum length of 4096 characters."
        )

    sender_name = (payload.sender or "").strip()[:100] or "Dashboard"
    telegram_text = f"📋 {sender_name}: {clean_message}"

    # 4. SSRF-Safe URL Construction & Validation
    telegram_url = validate_telegram_url(bot_token)

    body_data = json.dumps({
        "chat_id": chat_id,
        "text": telegram_text
    }).encode("utf-8")

    req = Request(
        telegram_url,
        data=body_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)

            if res_json.get("ok"):
                logger.info("[NOTIFY] Message sent successfully to Telegram")
                return {"status": "sent"}
            else:
                logger.error("[NOTIFY] Telegram API returned non-ok response")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Telegram API rejected the notification request."
                )

    except HTTPError as http_err:
        # Sanitize log output to avoid leaking bot token from URL or error stream
        logger.error(f"[NOTIFY] Telegram HTTPError: {http_err.code}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Telegram notification HTTP error ({http_err.code})"
        )
    except URLError:
        logger.error("[NOTIFY] Telegram connection error (URLError)")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not connect to Telegram servers."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[NOTIFY] Unexpected notification error: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal notification error."
        )
