"""Surveillance flag endpoints — event-study results around insider trades."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from shared.db import get_pool

router = APIRouter(prefix="/api/v1/surveillance", tags=["surveillance"])


@router.get("/flags")
async def list_flags(
    flagged: Optional[bool] = Query(None, description="Filter by flagged status"),
    ticker: Optional[str] = Query(None, description="Filter by ticker (case-insensitive)"),
    limit: int = Query(50, le=500),
):
    pool = await get_pool()
    where = []
    params: list = []
    if flagged is not None:
        params.append(flagged)
        where.append(f"f.flagged = ${len(params)}")
    if ticker:
        params.append(ticker.upper())
        where.append(f"c.ticker = ${len(params)}")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    params.append(limit)
    rows = await pool.fetch(
        f"""SELECT f.id, f.transaction_id, f.event_date,
                   f.car, f.car_zscore, f.volume_ratio,
                   f.flagged, f.flag_reason, f.computed_at,
                   c.ticker, c.name AS company_name,
                   t.insider_name, t.insider_title,
                   t.transaction_type, t.shares, t.price, t.total_value,
                   t.transaction_date
            FROM surveillance_flags f
            JOIN companies c ON c.id = f.company_id
            JOIN insider_transactions t ON t.id = f.transaction_id
            {where_sql}
            ORDER BY f.event_date DESC, f.id DESC
            LIMIT ${len(params)}""",
        *params,
    )
    return [_serialize(r) for r in rows]


@router.get("/flags/{flag_id}")
async def get_flag(flag_id: int):
    pool = await get_pool()
    row = await pool.fetchrow(
        """SELECT f.id, f.transaction_id, f.event_date,
                  f.car, f.car_zscore, f.volume_ratio,
                  f.baseline_alpha, f.baseline_beta, f.baseline_r2,
                  f.daily_ar, f.flagged, f.flag_reason, f.computed_at,
                  c.ticker, c.name AS company_name,
                  t.insider_name, t.insider_title,
                  t.transaction_type, t.shares, t.price, t.total_value,
                  t.transaction_date
           FROM surveillance_flags f
           JOIN companies c ON c.id = f.company_id
           JOIN insider_transactions t ON t.id = f.transaction_id
           WHERE f.id = $1""",
        flag_id,
    )
    if not row:
        raise HTTPException(404, f"Flag {flag_id} not found")
    return _serialize(row, include_daily=True)


def _serialize(row, include_daily: bool = False) -> dict:
    out = {
        "id": row["id"],
        "transaction_id": row["transaction_id"],
        "ticker": row["ticker"],
        "company_name": row["company_name"],
        "insider_name": row["insider_name"],
        "insider_title": row["insider_title"],
        "transaction_type": row["transaction_type"],
        "transaction_date": row["transaction_date"].isoformat() if row["transaction_date"] else None,
        "shares": row["shares"],
        "price": float(row["price"]) if row["price"] is not None else None,
        "total_value": float(row["total_value"]) if row["total_value"] is not None else None,
        "event_date": row["event_date"].isoformat() if row["event_date"] else None,
        "car": float(row["car"]) if row["car"] is not None else None,
        "car_zscore": float(row["car_zscore"]) if row["car_zscore"] is not None else None,
        "volume_ratio": float(row["volume_ratio"]) if row["volume_ratio"] is not None else None,
        "flagged": row["flagged"],
        "flag_reason": row["flag_reason"],
        "computed_at": row["computed_at"].isoformat() if row["computed_at"] else None,
    }
    if include_daily:
        out["baseline_alpha"] = float(row["baseline_alpha"]) if row["baseline_alpha"] is not None else None
        out["baseline_beta"] = float(row["baseline_beta"]) if row["baseline_beta"] is not None else None
        out["baseline_r2"] = float(row["baseline_r2"]) if row["baseline_r2"] is not None else None
        # daily_ar is JSONB → asyncpg returns a JSON string, decode it
        import json
        raw = row["daily_ar"]
        if isinstance(raw, str):
            out["daily_ar"] = json.loads(raw) if raw else []
        else:
            out["daily_ar"] = raw or []
    return out
