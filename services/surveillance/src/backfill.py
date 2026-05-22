"""Replay event-study computation across existing insider transactions.

Selects rows from `insider_transactions` that have no `surveillance_flags`
entry and enqueues `compute_event_study.delay(id)` for each. Use --overwrite
when retuning thresholds — it deletes existing flag rows first so the
UNIQUE(transaction_id) constraint doesn't drop the recomputed result.

Usage (inside the compose network — needs the Celery broker reachable):

    docker compose run --rm --no-deps surveillance \\
        python -m surveillance.backfill --dry-run

    docker compose run --rm --no-deps surveillance \\
        python -m surveillance.backfill --ticker AAPL --limit 50

    docker compose run --rm --no-deps surveillance \\
        python -m surveillance.backfill --overwrite

Watch task progress at http://localhost:5555 (Flower) or with
`docker compose logs -f celery-worker`.
"""

from __future__ import annotations

import argparse
import logging
import sys

import psycopg2
import psycopg2.extras

from shared.config import settings

from .tasks import _pg_url_to_dsn, compute_event_study

logger = logging.getLogger(__name__)


def _select_transactions(
    cur, *, ticker: str | None, limit: int | None, overwrite: bool
) -> list[dict]:
    where = []
    params: list = []
    if ticker:
        where.append("c.ticker = %s")
        params.append(ticker.upper())
    if not overwrite:
        where.append("f.id IS NULL")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    limit_sql = "" if limit is None else "LIMIT %s"
    if limit is not None:
        params.append(limit)

    cur.execute(
        f"""SELECT t.id, t.transaction_date, c.ticker
            FROM insider_transactions t
            JOIN companies c ON c.id = t.company_id
            LEFT JOIN surveillance_flags f ON f.transaction_id = t.id
            {where_sql}
            ORDER BY t.transaction_date DESC
            {limit_sql}""",
        params,
    )
    return [dict(r) for r in cur.fetchall()]


def _delete_existing_flags(cur, transaction_ids: list[int]) -> int:
    if not transaction_ids:
        return 0
    cur.execute(
        "DELETE FROM surveillance_flags WHERE transaction_id = ANY(%s)",
        (transaction_ids,),
    )
    return cur.rowcount


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the number of transactions enqueued.")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Restrict to one company by ticker (case-insensitive).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be enqueued; do not enqueue.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Include transactions that already have a flag row; "
                             "delete those existing rows so recomputation can write fresh.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    with psycopg2.connect(_pg_url_to_dsn(settings.DATABASE_URL)) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            rows = _select_transactions(
                cur,
                ticker=args.ticker,
                limit=args.limit,
                overwrite=args.overwrite,
            )

        logger.info(
            "found %d transaction(s) to process (ticker=%s, limit=%s, overwrite=%s)",
            len(rows), args.ticker or "*", args.limit, args.overwrite,
        )

        if args.dry_run:
            for r in rows[:20]:
                logger.info("  would enqueue: id=%s ticker=%s date=%s",
                            r["id"], r["ticker"], r["transaction_date"])
            if len(rows) > 20:
                logger.info("  ... and %d more", len(rows) - 20)
            return 0

        if args.overwrite and rows:
            with conn.cursor() as cur:
                deleted = _delete_existing_flags(cur, [r["id"] for r in rows])
            conn.commit()
            logger.info("deleted %d existing flag row(s) for overwrite", deleted)

    enqueued = 0
    for r in rows:
        try:
            result = compute_event_study.delay(r["id"])
            enqueued += 1
            logger.info("enqueued id=%s ticker=%s -> task %s",
                        r["id"], r["ticker"], result.id)
        except Exception:
            logger.exception("failed to enqueue id=%s", r["id"])

    logger.info("backfill: enqueued %d / %d task(s)", enqueued, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
