import json
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


async def publish_event(stream: str, data: dict):
    r = await get_redis()
    await r.xadd(stream, {"data": json.dumps(data)})


async def create_consumer_group(stream: str, group: str):
    r = await get_redis()
    try:
        await r.xgroup_create(stream, group, id="0", mkstream=True)
    except aioredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


async def consume_events(stream: str, group: str, consumer: str, count: int = 10, block: int = 5000):
    r = await get_redis()
    messages = await r.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block)
    results = []
    for _stream_name, entries in messages:
        for msg_id, fields in entries:
            data = json.loads(fields["data"])
            results.append((msg_id, data))
            await r.xack(stream, group, msg_id)
    return results
