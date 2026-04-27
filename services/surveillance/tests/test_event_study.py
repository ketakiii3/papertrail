"""Unit tests for event_study + flagger using synthetic OHLCV.

Tests cover:
  - market model recovers known α, β
  - flat data (no anomaly) → CAR ≈ 0, not flagged
  - injected +5% anomaly on event days → flagged with positive z
  - insufficient history → reason set, not flagged
  - incomplete event window → reason set, not flagged
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from surveillance.event_study import (
    BASELINE_END,
    BASELINE_START,
    EVENT_END,
    compute_abnormal_returns,
    compute_market_model,
)
from surveillance.flagger import should_flag


def _trading_days(start: date, n: int) -> pd.DatetimeIndex:
    """n consecutive weekday timestamps starting from `start`."""
    days = []
    d = pd.Timestamp(start)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return pd.DatetimeIndex(days)


def _ohlcv(prices: np.ndarray, idx: pd.DatetimeIndex, vol: float = 1_000_000) -> pd.DataFrame:
    return pd.DataFrame({"Close": prices, "Volume": vol}, index=idx)


def _build_market_and_stock(
    n_days: int,
    *,
    alpha: float = 0.0,
    beta: float = 1.0,
    seed: int = 42,
    event_idx: int | None = None,
    event_days: int = 0,
    event_jump: float = 0.0,
    event_vol_mult: float = 1.0,
):
    """Construct aligned market + stock OHLCV with a known DGP.

    stock_return_t = α + β · market_return_t + ε_t
    Optionally inject a constant return jump on event_days starting at event_idx.
    """
    rng = np.random.default_rng(seed)
    market_returns = rng.normal(loc=0.0005, scale=0.01, size=n_days)
    noise = rng.normal(loc=0.0, scale=0.005, size=n_days)
    stock_returns = alpha + beta * market_returns + noise

    if event_idx is not None and event_days > 0:
        for i in range(event_days):
            if event_idx + i < n_days:
                stock_returns[event_idx + i] += event_jump

    market_prices = 100 * np.cumprod(1 + market_returns)
    stock_prices = 100 * np.cumprod(1 + stock_returns)

    idx = _trading_days(date(2025, 1, 2), n_days)

    market_df = _ohlcv(market_prices, idx)
    stock_df = _ohlcv(stock_prices, idx)

    if event_idx is not None and event_vol_mult != 1.0:
        for i in range(event_days):
            if event_idx + i < n_days:
                stock_df.iloc[event_idx + i, stock_df.columns.get_loc("Volume")] *= event_vol_mult

    return stock_df, market_df, idx


def test_market_model_recovers_known_alpha_beta():
    rng = np.random.default_rng(0)
    n = 200
    market = pd.Series(rng.normal(0, 0.01, n))
    noise = pd.Series(rng.normal(0, 0.001, n))  # very small noise
    stock = 0.0002 + 1.5 * market + noise

    fit = compute_market_model(stock, market)
    assert fit.alpha == pytest.approx(0.0002, abs=2e-4)
    assert fit.beta == pytest.approx(1.5, abs=0.01)
    assert fit.r2 > 0.99
    assert fit.n_obs == n


def test_market_model_rejects_too_little_data():
    market = pd.Series(np.random.normal(0, 0.01, 5))
    stock = pd.Series(np.random.normal(0, 0.01, 5))
    with pytest.raises(ValueError, match="baseline has"):
        compute_market_model(stock, market)


def test_no_anomaly_yields_small_car_and_unflagged():
    n = 60
    stock_df, market_df, idx = _build_market_and_stock(n_days=n, alpha=0, beta=1.0)
    event_date = idx[n - EVENT_END - 1].date()  # leave room for event window

    result = compute_abnormal_returns(stock_df, market_df, event_date)
    assert result.insufficient_reason is None
    assert result.fit is not None
    assert abs(result.car) < 0.05  # noise-only CAR should be small
    assert abs(result.car_zscore) < 2.0
    assert result.volume_ratio == pytest.approx(1.0, abs=1e-9)

    decision = should_flag(result)
    assert decision.flagged is False


def test_injected_anomaly_is_flagged():
    n = 60
    event_position = n - EVENT_END - 1
    stock_df, market_df, idx = _build_market_and_stock(
        n_days=n,
        alpha=0,
        beta=1.0,
        event_idx=event_position,
        event_days=EVENT_END + 1,   # full event window
        event_jump=0.03,            # +3% extra return per day → CAR ≈ 18%
        event_vol_mult=4.0,         # 4× volume on event days
    )
    event_date = idx[event_position].date()

    result = compute_abnormal_returns(stock_df, market_df, event_date)
    assert result.insufficient_reason is None
    assert result.car > 0.10
    assert result.car_zscore > 3.0
    assert result.volume_ratio > 1.5

    decision = should_flag(result)
    assert decision.flagged is True
    assert "car_z=" in decision.reason


def test_insufficient_history_returns_reason():
    n = 10
    stock_df, market_df, idx = _build_market_and_stock(n_days=n)
    event_date = idx[5].date()

    result = compute_abnormal_returns(stock_df, market_df, event_date)
    assert result.insufficient_reason == "insufficient_history"
    assert result.car is None

    decision = should_flag(result)
    assert decision.flagged is False
    assert decision.reason == "insufficient_history"


def test_event_window_incomplete_returns_reason():
    n = 35
    stock_df, market_df, idx = _build_market_and_stock(n_days=n)
    # Place event such that baseline fits but event window runs past data end.
    event_date = idx[n - 2].date()

    result = compute_abnormal_returns(stock_df, market_df, event_date)
    assert result.insufficient_reason == "event_window_incomplete"

    decision = should_flag(result)
    assert decision.flagged is False
    assert decision.reason == "event_window_incomplete"


def test_event_date_after_data_end():
    stock_df, market_df, idx = _build_market_and_stock(n_days=40)
    future = idx[-1].date() + timedelta(days=30)

    result = compute_abnormal_returns(stock_df, market_df, future)
    assert result.insufficient_reason == "event_date_after_data_end"


def test_event_date_rolls_to_next_trading_day():
    n = 60
    stock_df, market_df, idx = _build_market_and_stock(n_days=n)
    # Find a Monday in the middle of the window so its preceding Saturday is
    # bracketed by two real trading days.
    monday = next(
        ts for i, ts in enumerate(idx)
        if ts.weekday() == 0 and 30 <= i <= n - EVENT_END - 2
    )
    saturday = monday - timedelta(days=2)
    assert saturday.weekday() == 5

    result = compute_abnormal_returns(stock_df, market_df, saturday.date())
    assert result.event_date == monday.date()
