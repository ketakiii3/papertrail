"""EDGAR Ingester entry point."""

import asyncio
import logging
import sys

# Add project root to path
sys.path.insert(0, "/app")

from src.ingester import run_ingestion, run_continuous

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="EDGAR Filing Ingester")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=3600, help="Seconds between cycles")
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_ingestion())
    else:
        asyncio.run(run_continuous(args.interval))


if __name__ == "__main__":
    main()
