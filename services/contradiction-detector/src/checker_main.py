"""Checker agent entry point: `python -m src.checker_main` (consumer),
or `python -m src.checker_main --id 12 [--id 13]` to check stored pairs once."""

import argparse
import asyncio
import logging
import sys

sys.path.insert(0, "/app")

from shared.db import close_pool
from shared.kafka_client import close_producer
from src.checker_service import check_contradiction, run_consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)


async def _check_once(ids: list[int]) -> None:
    try:
        for cid in ids:
            await check_contradiction(cid)
    finally:
        await close_producer()
        await close_pool()


def main():
    parser = argparse.ArgumentParser(description="PaperTrail checker agent")
    parser.add_argument("--id", type=int, action="append", help="Check this contradiction id and exit")
    args = parser.parse_args()
    asyncio.run(_check_once(args.id) if args.id else run_consumer())


if __name__ == "__main__":
    main()
