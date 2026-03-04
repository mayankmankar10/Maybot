"""
logging/elastic_logger.py

ElasticLogger — Writes structured event documents to Elasticsearch.
Section 4.4 — Architecture document.

Event document schema:
    {
        "user_id":    <int>,
        "event":      <str>,   e.g. "plateau_detected", "plan_generated", "adjustment_applied"
        "adjustment": <float>, optional
        "week":       <int>,   optional
        "metadata":   <dict>,  optional
        "timestamp":  <str>    ISO 8601
    }
"""
import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from elasticsearch import Elasticsearch, BadRequestError

logger = logging.getLogger(__name__)

# Suppress elastic_transport's verbose retry/node-pool INFO logs — we handle
# failures ourselves and only want to see actual errors.
logging.getLogger("elastic_transport").setLevel(logging.ERROR)
logging.getLogger("elastic_transport.transport").setLevel(logging.ERROR)
logging.getLogger("elastic_transport.node_pool").setLevel(logging.ERROR)

ELASTIC_HOST = os.getenv("ELASTIC_HOST", "http://localhost:9200")
ELASTIC_INDEX = os.getenv("ELASTIC_INDEX", "nutrition_logs")

# Thread pool for non-blocking ES writes
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="es_log")


class ElasticLogger:
    """
    Thin wrapper around the Elasticsearch client for structured event logging.
    Failures are caught and logged locally — never propagated to the caller.
    """

    def __init__(self):
        self._client = Elasticsearch(
            ELASTIC_HOST,
            max_retries=0,            # fail fast — no retry storm
            retry_on_timeout=False,
            request_timeout=2,        # 2-second hard cap per request
        )
        self._index = ELASTIC_INDEX
        self._ensure_index()

    def _ensure_index(self) -> None:
        """Create the index with correct mappings if it doesn't exist."""
        try:
            if not self._client.indices.exists(index=self._index):
                self._client.indices.create(
                    index=self._index,
                    mappings={
                        "properties": {
                            "user_id":    {"type": "long"},
                            "event":      {"type": "keyword"},
                            "adjustment": {"type": "float"},
                            "week":       {"type": "integer"},
                            "metadata":   {"type": "object", "enabled": True},
                            "timestamp":  {"type": "date"},
                        }
                    },
                )
        except BadRequestError:
            pass  # Index already exists
        except Exception as exc:
            logger.warning("ElasticSearch index creation skipped: %s", exc)

    def _do_index(self, doc: dict) -> None:
        """Blocking ES index call — runs inside thread executor."""
        try:
            self._client.index(index=self._index, document=doc)
        except Exception as exc:
            logger.error("ElasticLogger.log_event failed: %s — doc: %s", exc, doc)

    def log_event(
        self,
        user_id: int,
        event: str,
        week: int | None = None,
        adjustment: float | None = None,
        metadata: dict | None = None,
    ) -> None:
        """
        Non-blocking fire-and-forget ES write.
        Submits to a thread pool and returns immediately — never blocks handlers.
        """
        doc = {
            "user_id":   user_id,
            "event":     event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if week is not None:
            doc["week"] = week
        if adjustment is not None:
            doc["adjustment"] = adjustment
        if metadata is not None:
            doc["metadata"] = metadata

        # Submit to background thread — returns immediately
        _executor.submit(self._do_index, doc)
