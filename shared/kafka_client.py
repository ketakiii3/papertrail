"""Kafka (Redpanda) client — JSON producer + consumer helpers.

Replaces shared/redis_client.publish_event for inter-service eventing.
Redis is still used for caching and as Celery broker.
"""

import json
import logging
from typing import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from shared.config import settings

logger = logging.getLogger(__name__)

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            enable_idempotence=True,
            acks="all",
        )
        await _producer.start()
    return _producer


async def close_producer() -> None:
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None


async def publish(topic: str, payload: dict, key: str | None = None) -> None:
    producer = await get_producer()
    await producer.send_and_wait(
        topic,
        value=payload,
        key=key.encode("utf-8") if key else None,
    )


async def consume(
    topic: str,
    group_id: str,
    handler: Callable[[dict], Awaitable[None]],
    *,
    auto_offset_reset: str = "earliest",
) -> None:
    """Long-running consumer loop. `handler` receives the deserialized JSON payload.

    Manual commit after the handler returns successfully — at-least-once delivery.
    Handlers must be idempotent.
    """
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=group_id,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        enable_auto_commit=False,
        auto_offset_reset=auto_offset_reset,
    )
    await consumer.start()
    logger.info("kafka consumer started: topic=%s group=%s", topic, group_id)
    try:
        async for msg in consumer:
            try:
                await handler(msg.value)
                await consumer.commit()
            except Exception:
                logger.exception(
                    "handler failed; not committing offset (will redeliver) topic=%s offset=%s",
                    msg.topic, msg.offset,
                )
    finally:
        await consumer.stop()
