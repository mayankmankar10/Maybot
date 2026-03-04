"""
app/main.py
FastAPI application entry point.
Polling mode — no webhook dependency.
Architecture: FastAPI + PostgreSQL + ElasticSearch + Telegram polling.
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

from db.session import engine
from db.models import Base
from app.telegram_bot import start_polling, stop_polling

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan:
      Startup  → create DB tables (graceful if Postgres not ready)
               → start Telegram long-polling (background, non-blocking)
      Shutdown → stop polling gracefully
    """
    logger.info("Starting Adaptive AI Nutrition Agent…")

    # --- Database ---
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ready.")
    except Exception as e:
        logger.warning(
            "Database not available at startup: %s — "
            "DB-dependent routes will fail until Postgres is up.", e,
        )

    # --- Telegram polling (background, non-blocking) ---
    await start_polling()

    yield  # Application is running

    # --- Graceful shutdown ---
    await stop_polling()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Adaptive AI Nutrition Agent",
    description=(
        "Production-structured, skill-based, closed-loop AI nutrition system. "
        "FastAPI + PostgreSQL + ElasticSearch + Telegram (polling mode)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# NOTE: Webhook router is intentionally excluded in polling mode.
# It remains in app/webhook.py and can be re-enabled when moving to webhook mode.
# To re-enable: uncomment the lines below and set TELEGRAM_WEBHOOK_SECRET in .env
# from app.webhook import router as webhook_router
# app.include_router(webhook_router)


@app.get("/health")
def health_check() -> dict:
    """Lightweight health check endpoint."""
    return {"status": "ok", "service": "adaptive-ai-nutrition", "mode": "polling"}
