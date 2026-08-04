import os
import json
import logging
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["notify"])


class NotifyRequest(BaseModel):
    message: str = Field(..., description="Message/note to send to team Telegram bot")
    sender: Optional[str] = Field("Dashboard", description="Sender display name")


@router.post("/notify", status_code=200)
async def send_team_notification(payload: NotifyRequest):
    """
    Sends review notes / alerts from the Tender OCR Dashboard directly to a Telegram team chat bot.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id or bot_token == "your_bot_token_here" or chat_id == "your_chat_id_here":
        logger.error("[NOTIFY] Missing or unconfigured TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in env vars.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram bot credentials not configured on server (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing)."
        )

    if not payload.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message content cannot be empty."
        )

    sender_name = payload.sender.strip() if payload.sender else "Dashboard"
    telegram_text = f"📋 {sender_name}: {payload.message.strip()}"

    telegram_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
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
                logger.info(f"[NOTIFY] Message sent successfully to Telegram chat {chat_id}")
                return {"status": "sent"}
            else:
                error_msg = res_json.get("description", "Unknown Telegram API error")
                logger.error(f"[NOTIFY] Telegram API error: {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Telegram API error: {error_msg}"
                )

    except HTTPError as http_err:
        err_detail = http_err.read().decode("utf-8") if http_err.fp else str(http_err)
        logger.error(f"[NOTIFY] Telegram HTTPError: {http_err.code} - {err_detail}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Telegram notification HTTP error ({http_err.code})"
        )
    except URLError as url_err:
        logger.error(f"[NOTIFY] Telegram URLError: {url_err.reason}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not connect to Telegram servers: {url_err.reason}"
        )
    except Exception as e:
        logger.error(f"[NOTIFY] Unexpected notification error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal notification error: {str(e)}"
        )
