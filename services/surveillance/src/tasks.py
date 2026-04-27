"""Celery tasks for the surveillance module."""

from __future__ import annotations

import json
import logging
from datetime import date

import psycopg2
import psycopg2.extras

from shared.celery_app import celery_app
from shared.config import settings

from .event_study import compute_abnormal_returns
from .flagger import should_flag
from .market_data import fetch_event_window
from .publisher import publish_flag_sync

logger = logging.getLogger(__name__)


def _pg_url_to_dsn(url: str) -> str:
    """asyncpg-style URL works for psycopg2 too; just strip the +driver if any."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _conn():
    return psycopg2.connect(_pg_url_to_dsn(settings.DATABASE_URL))


@celery_app.task(name="surveillance.add")
def add(x: int, y: int) -> int:
    """Kept for smoke testing; safe to remove later."""
    return x + y


@celery_app.task(
    name="surveillance.compute_event_study",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError,),
)
def compute_event_study(self, transaction_id: int) -> dict:
    """Run an event study for one insider transaction; persist + publish flag."""
    with _conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """SELECT t.id, t.company_id, t.insider_name, t.transaction_type,
                      t.shares, t.price, t.total_value, t.transaction_date,
                      c.ticker
               FROM insider_transactions t
               JOIN companies c ON c.id = t.company_id
               WHERE t.id = %s""",
            (transaction_id,),
        )
        row = cur.fetchone()
        if row is None:
            logger.warning(f"transaction {transaction_id} not found; nothing to do")
            return {"status": "not_found"}

        cur.execute("SELECT 1 FROM surveillance_flags WHERE transaction_id = %s", (transaction_id,))
        if cur.fetchone() is not None:
            logger.info(f"transaction {transaction_id} already has a flag row; skipping")
            return {"status": "already_processed"}

    ticker: str = row["ticker"]
    txn_date: date = row["transaction_date"]
    company_id: int = row["company_id"]

    fetched = fetch_event_window(ticker, txn_date)
    if fetched is None:
        _persist_insufficient(transaction_id, company_id, txn_date,
                              reason="market_data_unavailable")
        return {"status": "market_data_unavailable"}

    stock_df, market_df = fetched
    result = compute_abnormal_returns(stock_df, market_df, txn_date)

    if result.insufficient_reason == "event_window_incomplete":
        countdown = 60 * 60 * 24 * 2  # check back in 2 days
        logger.info(f"txn {transaction_id}: event window not elapsed; deferring {countdown}s")
        raise self.retry(countdown=countdown, max_retries=10, exc=RuntimeError("event_window_incomplete"))

    if result.insufficient_reason:
        _persist_insufficient(transaction_id, company_id, txn_date,
                              reason=result.insufficient_reason)
        return {"status": result.insufficient_reason}

    decision = should_flag(result)

    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO surveillance_flags
               (transaction_id, company_id, event_date, car, car_zscore, volume_ratio,
                baseline_alpha, baseline_beta, baseline_r2, daily_ar,
                flagged, flag_reason)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (transaction_id) DO NOTHING""",
            (
                transaction_id,
                company_id,
                result.event_date,
                result.car,
                result.car_zscore,
                result.volume_ratio,
                result.fit.alpha if result.fit else None,
                result.fit.beta if result.fit else None,
                result.fit.r2 if result.fit else None,
                json.dumps(result.daily_ar),
                decision.flagged,
                decision.reason,
            ),
        )
        conn.commit()

    publish_flag_sync({
        "transaction_id": transaction_id,
        "company_id": company_id,
        "ticker": ticker,
        "insider_name": row["insider_name"],
        "transaction_type": row["transaction_type"],
        "event_date": result.event_date.isoformat(),
        "car": result.car,
        "car_zscore": result.car_zscore,
        "volume_ratio": result.volume_ratio,
        "flagged": decision.flagged,
        "flag_reason": decision.reason,
    })

    logger.info(
        f"txn {transaction_id} {ticker}: CAR={result.car:+.4f} "
        f"z={result.car_zscore:+.2f} vol_x={result.volume_ratio:.2f} "
        f"flagged={decision.flagged}"
    )
    return {"status": "ok", "flagged": decision.flagged,
            "car": result.car, "z": result.car_zscore}


def _persist_insufficient(
    transaction_id: int, company_id: int, event_date: date, *, reason: str
) -> None:
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO surveillance_flags
               (transaction_id, company_id, event_date, flagged, flag_reason)
               VALUES (%s,%s,%s,false,%s)
               ON CONFLICT (transaction_id) DO NOTHING""",
            (transaction_id, company_id, event_date, reason),
        )
        conn.commit()
