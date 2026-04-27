"""Roundtrip 5 messages through Redpanda to verify kafka_client works.

Run inside the compose network:
    docker compose run --rm --no-deps edgar-ingester python -m scripts.kafka_smoke
"""

import asyncio
import logging

from shared.kafka_client import close_producer, consume, publish

logging.basicConfig(level=logging.INFO)

TOPIC = "smoke.test"
GROUP = "smoke-test-consumer"
N = 5


async def main() -> None:
    received: list[dict] = []

    async def handler(payload: dict) -> None:
        received.append(payload)
        print(f"  consumed: {payload}")

    consumer_task = asyncio.create_task(consume(TOPIC, GROUP, handler))

    await asyncio.sleep(2)

    print(f"producing {N} messages to {TOPIC}")
    for i in range(N):
        await publish(TOPIC, {"i": i, "msg": f"hello {i}"})
    await close_producer()

    deadline = asyncio.get_event_loop().time() + 10
    while len(received) < N and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.2)

    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass

    assert len(received) == N, f"expected {N} messages, got {len(received)}"
    print(f"OK: roundtripped {N} messages")


if __name__ == "__main__":
    asyncio.run(main())
