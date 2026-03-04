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
from sqlalchemy.orm import Session

from db.session import get_db
from app.controller import NutritionController
from elastic_logging.elastic_logger import ElasticLogger

logger = logging.getLogger(__name__)
router = APIRouter()
elastic = ElasticLogger()
controller = NutritionController()

WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


def _verify_secret(x_telegram_bot_api_secret_token: str = Header(default="")) -> None:
    """Validates Telegram webhook secret token."""
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret.")


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(_verify_secret),
) -> dict:
    """
    Main Telegram webhook handler.
    All Telegram Update routing happens here.
    """
    update = await request.json()
    message = update.get("message", {})
    text = message.get("text", "").strip()
    user_id = message.get("from", {}).get("id")

    if not user_id:
        return {"ok": True}   # Ignore non-message updates

    logger.info("Received message from user %s: %s", user_id, text[:80])

    try:
        result = _route(user_id, text, update, db)
        elastic.log_event(user_id=user_id, event="message_handled", metadata={"command": text[:50]})
        return {"ok": True, "result": result}
    except Exception as exc:
        logger.exception("Error handling update for user %s: %s", user_id, exc)
        elastic.log_event(user_id=user_id, event="error", metadata={"error": str(exc)})
        return {"ok": True}   # Always return 200 to Telegram


def _route(user_id: int, text: str, update: dict, db: Session) -> dict:
    """
    Simple command router.
    Extend this as new commands are added.
    """
    if text.startswith("/start"):
        # New user onboarding — in a real bot this would be a multi-step conversation
        # For now it returns a placeholder until the conversation state machine is built
        return {"action": "onboarding_started", "user_id": user_id}

    if text.startswith("/log"):
        # Example: /log 79.5 90
        # Returns a placeholder until full parsing is implemented
        return {"action": "log_received", "user_id": user_id}

    return {"action": "unknown_command"}
