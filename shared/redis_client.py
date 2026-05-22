"""Async Redis connection used for caching only.

Inter-service events moved to Kafka (see shared/kafka_client.py). Redis still
backs the yfinance OHLCV cache (surveillance/market_data.py) and is Celery's
broker + result backend (shared/celery_app.py).
"""

import redis.asyncio as aioredis
from shared.config import settings


_redis = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.close()
        _redis = None
