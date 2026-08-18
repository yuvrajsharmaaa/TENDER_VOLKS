import os
import json
import time
import logging
from collections import defaultdict
from threading import Lock
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from fastapi import APIRouter, HTTPException, Request as FastAPIRequest, status
from pydantic import BaseModel, Field
from typing import Optional

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["notify"])


class RateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter per client IP.
    Default: max 10 notifications per 60 seconds.
    """
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()

    def is_allowed(self, client_ip: str) -> tuple[bool, int]:
        now = time.time()
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


@router.post("/notify", status_code=200)
async def send_team_notification(payload: NotifyRequest, request: FastAPIRequest):
    """
    Sends review notes / alerts from the Tender OCR Dashboard directly to a Telegram team chat bot.
    Includes rate limiting, token sanitization, credential redaction in logs, and input length validation.
    """
    # 1. Rate Limiting Check
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
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or getattr(settings, "telegram_bot_token", None)
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or getattr(settings, "telegram_chat_id", None)

    if not bot_token or not chat_id or bot_token == "your_bot_token_here" or chat_id == "your_chat_id_here":
        logger.error("[NOTIFY] Missing or unconfigured TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in settings or env vars.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram bot credentials not configured on server (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing)."
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

    # 4. Safe URL Encoding for Bot Token (Prevent URL Injection)
    safe_bot_token = quote(str(bot_token).strip(), safe="")
    telegram_url = f"https://api.telegram.org/bot{safe_bot_token}/sendMessage"

    body_data = json.dumps({
        "chat_id": str(chat_id).strip(),
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

