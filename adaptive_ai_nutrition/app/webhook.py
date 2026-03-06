"""
app/webhook.py
FastAPI router for the Telegram webhook endpoint.
Section 4.2 + Section 9 — Architecture document.

Route: POST /telegram
- Validates the secret token header
- Parses the Telegram Update
- Routes to NutritionController based on message content
- Logs events to ElasticSearch
"""
import os
import logging
from fastapi import APIRouter, Header, HTTPException, Request, Depends

from app.telegram_bot import process_webhook_update

logger = logging.getLogger(__name__)
router = APIRouter()

WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


def _verify_secret(x_telegram_bot_api_secret_token: str = Header(default="")) -> None:
    """Validates Telegram webhook secret token."""
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret.")


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    _: None = Depends(_verify_secret),
) -> dict:
    """
    Main Telegram webhook handler.
    Passes the update to python-telegram-bot's update queue.
    """
    try:
        update_json = await request.json()
        await process_webhook_update(update_json)
        return {"ok": True}
    except Exception as exc:
        logger.exception("Error handling webhook update: %s", exc)
        return {"ok": True}   # Always return 200 to Telegram
