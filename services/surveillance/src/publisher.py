"""Kafka publisher for surveillance.flag events.

Called from inside the Celery task (sync context). aiokafka is async, so we
spin up a short-lived event loop per publish — fine for low-frequency events.
"""

from __future__ import annotations

import asyncio
import logging

from shared.kafka_client import close_producer, publish

logger = logging.getLogger(__name__)


def publish_flag_sync(payload: dict) -> None:
    async def _do():
        try:
            await publish("surveillance.flag", payload)
        finally:
            await close_producer()

    try:
        asyncio.run(_do())
    except Exception as e:
        logger.warning(f"surveillance.flag publish failed: {e}")
