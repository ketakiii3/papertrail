"""yfinance OHLCV fetcher with Redis caching.

Synchronous (yfinance is sync). Called from Celery tasks which run in the
prefork worker pool, so blocking is fine.
"""

from __future__ import annotations

import io
import json
import logging
import os
from datetime import date, timedelta

import pandas as pd
import redis
import yfinance as yf

from shared.config import settings

logger = logging.getLogger(__name__)

CACHE_TTL = int(os.getenv("SURV_PRICE_CACHE_TTL", "86400"))
MARKET_INDEX = os.getenv("SURV_MARKET_INDEX", "SPY")

# Pull more calendar days than the trading-day window so weekends/holidays
# don't shrink the baseline. ~50 calendar days easily covers 30 trading days.
CALENDAR_DAYS_BEFORE = 60
CALENDAR_DAYS_AFTER = 15

_redis: redis.Redis | None = None


def _r() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis


def _cache_key(ticker: str, start: date, end: date) -> str:
    return f"ohlcv:{ticker}:{start.isoformat()}:{end.isoformat()}"


def _df_from_cached(blob: bytes) -> pd.DataFrame:
    payload = json.loads(blob.decode("utf-8"))
    df = pd.read_json(io.StringIO(payload), orient="split")
    df.index = pd.to_datetime(df.index)
    return df


def _df_to_cached(df: pd.DataFrame) -> bytes:
    return json.dumps(df.to_json(orient="split", date_format="iso")).encode("utf-8")


def fetch_ohlcv(ticker: str, start: date, end: date) -> pd.DataFrame | None:
    """Fetch daily OHLCV for `ticker` between `start` and `end` inclusive.

    Returns None if yfinance returned nothing (delisted, bad ticker, network).
    Cached in Redis under (ticker, start, end) for SURV_PRICE_CACHE_TTL seconds.
    """
    key = _cache_key(ticker, start, end)
    try:
        cached = _r().get(key)
        if cached:
            return _df_from_cached(cached)
    except Exception as e:
        logger.warning(f"Redis cache read failed for {key}: {e}")

    try:
        # yfinance end is exclusive
        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {ticker}: {e}")
        return None

    if df is None or df.empty:
        return None

    # yfinance sometimes returns a column MultiIndex when downloading; flatten.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    df = df[keep]

    try:
        _r().setex(key, CACHE_TTL, _df_to_cached(df))
    except Exception as e:
        logger.warning(f"Redis cache write failed for {key}: {e}")

    return df


def fetch_event_window(ticker: str, event_date: date) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """Fetch (stock, market) OHLCV around event_date.

    Returns None if either ticker has no data.
    """
    start = event_date - timedelta(days=CALENDAR_DAYS_BEFORE)
    end = event_date + timedelta(days=CALENDAR_DAYS_AFTER)

    stock = fetch_ohlcv(ticker, start, end)
    if stock is None:
        return None
    market = fetch_ohlcv(MARKET_INDEX, start, end)
    if market is None:
        return None
    return stock, market
