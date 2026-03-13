"""Transcript Ingester entry point."""

import asyncio
import logging
import sys

sys.path.insert(0, "/app")

from src.ingester import run_transcript_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def main():
    asyncio.run(run_transcript_ingestion())


if __name__ == "__main__":
    main()
