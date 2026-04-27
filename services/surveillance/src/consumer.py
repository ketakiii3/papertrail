"""Kafka consumer that enqueues surveillance Celery tasks.

Subscribes to `insider.new`. For each event, enqueues
`surveillance.compute_event_study(transaction_id)`. Lightweight on purpose —
the actual compute happens in the Celery worker pool.
"""

from __future__ import annotations

import asyncio
import logging

from shared.kafka_client import close_producer, consume

from .tasks import compute_event_study

logger = logging.getLogger(__name__)


async def handle(payload: dict) -> None:
    transaction_id = payload.get("transaction_id")
    if transaction_id is None:
        logger.warning(f"insider.new event missing transaction_id: {payload}")
        return
    async_result = compute_event_study.delay(transaction_id)
    logger.info(f"enqueued event study for txn {transaction_id} -> task {async_result.id}")


async def run() -> None:
    try:
        await consume("insider.new", "surveillance", handle)
    finally:
        await close_producer()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    asyncio.run(run())
