"""Contradiction Detector entry point."""

import asyncio
import logging
import sys

sys.path.insert(0, "/app")

from src.detector import run_consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def main():
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
