"""Threshold logic for flagging an event-study result as anomalous."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .event_study import EventStudyResult


CAR_Z_THRESHOLD = float(os.getenv("SURV_CAR_Z_THRESHOLD", "2.0"))
VOLUME_THRESHOLD = float(os.getenv("SURV_VOLUME_THRESHOLD", "1.5"))


@dataclass
class FlagDecision:
    flagged: bool
    reason: str  # human-readable; also used as stored flag_reason


def should_flag(
    result: EventStudyResult,
    *,
    z_threshold: float = CAR_Z_THRESHOLD,
    volume_threshold: float = VOLUME_THRESHOLD,
) -> FlagDecision:
    if result.insufficient_reason:
        return FlagDecision(flagged=False, reason=result.insufficient_reason)
    if result.car_zscore is None or result.volume_ratio is None:
        return FlagDecision(flagged=False, reason="missing_stats")

    z_hit = abs(result.car_zscore) > z_threshold
    vol_hit = result.volume_ratio > volume_threshold

    if z_hit and vol_hit:
        return FlagDecision(
            flagged=True,
            reason=f"car_z={result.car_zscore:+.2f} vol_x={result.volume_ratio:.2f}",
        )
    parts = []
    if not z_hit:
        parts.append(f"|z|={abs(result.car_zscore):.2f}≤{z_threshold}")
    if not vol_hit:
        parts.append(f"vol={result.volume_ratio:.2f}≤{volume_threshold}")
    return FlagDecision(flagged=False, reason="; ".join(parts))
