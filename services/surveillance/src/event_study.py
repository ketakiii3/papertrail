"""Event-study computation: market model regression + abnormal returns.

Pure functions only. All inputs are pandas DataFrames already aligned to trading
days; all I/O (yfinance, Postgres, Redis) is in market_data.py and tasks.py.

Methodology — see surveillance-prd.md §6:
  - Baseline window T1 = [-30, -2] trading days (gap day -1 excluded).
  - Event window   T2 = [0, +5] trading days (t=0 = transaction_date, rolled
                                              forward to next trading day).
  - Market model:  r_i = α + β · r_m + ε   fit on T1 by OLS.
  - AR_t           = r_i,t - (α + β · r_m,t)        for t in T2.
  - CAR            = Σ AR_t over T2.
  - z              = CAR / (σ_AR_baseline · √N_event)
  - vol_ratio      = mean(Vol on T2) / mean(Vol on T1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

BASELINE_START = -30
BASELINE_END = -2  # inclusive; excludes gap day -1
EVENT_START = 0
EVENT_END = 5  # inclusive
MIN_BASELINE_OBS = 20  # need enough days for a meaningful regression


@dataclass
class MarketModelFit:
    alpha: float
    beta: float
    r2: float
    residual_std: float  # σ of residuals on the baseline window
    n_obs: int


@dataclass
class EventStudyResult:
    event_date: date              # actual trading day used for t=0
    fit: MarketModelFit | None    # None if insufficient data
    daily_ar: list[dict] = field(default_factory=list)  # [{date, ret, expected, ar}]
    car: float | None = None
    car_zscore: float | None = None
    volume_ratio: float | None = None
    insufficient_reason: str | None = None  # set when we can't compute


def _pct_returns(prices: pd.Series) -> pd.Series:
    """Simple daily returns from a price series indexed by trading day."""
    return prices.pct_change().dropna()


def compute_market_model(
    stock_returns: pd.Series, market_returns: pd.Series
) -> MarketModelFit:
    """OLS fit of r_i = α + β · r_m + ε on aligned baseline returns."""
    df = pd.concat([stock_returns, market_returns], axis=1, join="inner").dropna()
    df.columns = ["r_i", "r_m"]
    n = len(df)
    if n < MIN_BASELINE_OBS:
        raise ValueError(f"baseline has {n} obs, need ≥ {MIN_BASELINE_OBS}")

    x = df["r_m"].to_numpy()
    y = df["r_i"].to_numpy()
    x_mean, y_mean = x.mean(), y.mean()
    x_var = ((x - x_mean) ** 2).sum()
    if x_var == 0:
        raise ValueError("market returns have zero variance on baseline")

    beta = ((x - x_mean) * (y - y_mean)).sum() / x_var
    alpha = y_mean - beta * x_mean
    residuals = y - (alpha + beta * x)
    ss_res = (residuals ** 2).sum()
    ss_tot = ((y - y_mean) ** 2).sum()
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    # Sample std with ddof=2 (two parameters estimated).
    residual_std = float(np.sqrt(ss_res / max(n - 2, 1)))

    return MarketModelFit(
        alpha=float(alpha),
        beta=float(beta),
        r2=float(r2),
        residual_std=residual_std,
        n_obs=n,
    )


def _locate_event_index(
    trading_days: pd.DatetimeIndex, event_date: date
) -> int | None:
    """Index of the first trading day on or after event_date. None if past data end."""
    target = pd.Timestamp(event_date)
    pos = trading_days.searchsorted(target, side="left")
    if pos >= len(trading_days):
        return None
    return int(pos)


def compute_abnormal_returns(
    stock_ohlcv: pd.DataFrame,
    market_ohlcv: pd.DataFrame,
    event_date: date,
    *,
    baseline: tuple[int, int] = (BASELINE_START, BASELINE_END),
    event: tuple[int, int] = (EVENT_START, EVENT_END),
) -> EventStudyResult:
    """Run the full event study for one transaction.

    `stock_ohlcv` and `market_ohlcv` must be DataFrames with a DatetimeIndex
    (trading days) and at least 'Close' and 'Volume' columns. They should cover
    the full window [event_date + baseline[0] - 1, event_date + event[1]] in
    *trading days*; market_data.py's job is to pull enough calendar history.
    """
    # Align to common trading days
    common_idx = stock_ohlcv.index.intersection(market_ohlcv.index)
    stock = stock_ohlcv.loc[common_idx].sort_index()
    market = market_ohlcv.loc[common_idx].sort_index()

    event_idx = _locate_event_index(common_idx, event_date)
    if event_idx is None:
        return EventStudyResult(event_date=event_date, fit=None,
                                insufficient_reason="event_date_after_data_end")

    actual_event_day = common_idx[event_idx].date()

    bs_start_idx = event_idx + baseline[0]
    bs_end_idx = event_idx + baseline[1]  # inclusive
    ev_end_idx = event_idx + event[1]     # inclusive

    if bs_start_idx < 1:  # need bs_start_idx-1 to exist for first return
        return EventStudyResult(event_date=actual_event_day, fit=None,
                                insufficient_reason="insufficient_history")
    if ev_end_idx >= len(common_idx):
        return EventStudyResult(event_date=actual_event_day, fit=None,
                                insufficient_reason="event_window_incomplete")

    # Returns from prices: index aligns to the *day of return*.
    stock_ret = _pct_returns(stock["Close"])
    market_ret = _pct_returns(market["Close"])

    # Slice baseline returns: trading days bs_start_idx..bs_end_idx (inclusive).
    baseline_dates = common_idx[bs_start_idx:bs_end_idx + 1]
    bl_stock = stock_ret.loc[stock_ret.index.intersection(baseline_dates)]
    bl_market = market_ret.loc[market_ret.index.intersection(baseline_dates)]

    try:
        fit = compute_market_model(bl_stock, bl_market)
    except ValueError as e:
        return EventStudyResult(event_date=actual_event_day, fit=None,
                                insufficient_reason=f"market_model_fail:{e}")

    # Event window returns
    event_dates = common_idx[event_idx:ev_end_idx + 1]
    ev_stock = stock_ret.reindex(event_dates).dropna()
    ev_market = market_ret.reindex(event_dates).dropna()
    aligned = pd.concat([ev_stock, ev_market], axis=1, join="inner").dropna()
    aligned.columns = ["r_i", "r_m"]

    daily = []
    car = 0.0
    for ts, row in aligned.iterrows():
        expected = fit.alpha + fit.beta * row["r_m"]
        ar = row["r_i"] - expected
        car += ar
        daily.append({
            "date": ts.date().isoformat(),
            "ret": float(row["r_i"]),
            "expected": float(expected),
            "ar": float(ar),
        })

    n_event = len(daily)
    if n_event == 0 or fit.residual_std == 0:
        z = None
    else:
        z = car / (fit.residual_std * math.sqrt(n_event))

    # Volume ratio
    bl_vol = stock.loc[stock.index.intersection(baseline_dates), "Volume"].mean()
    ev_vol = stock.loc[stock.index.intersection(event_dates), "Volume"].mean()
    vol_ratio = float(ev_vol / bl_vol) if bl_vol and bl_vol > 0 else None

    return EventStudyResult(
        event_date=actual_event_day,
        fit=fit,
        daily_ar=daily,
        car=float(car),
        car_zscore=float(z) if z is not None else None,
        volume_ratio=vol_ratio,
    )
