"""Watchlist endpoints."""

from fastapi import APIRouter, HTTPException

from shared.db import get_pool
from src.schemas import WatchlistRequest

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


@router.post("")
async def add_to_watchlist(req: WatchlistRequest):
    pool = await get_pool()

    # Verify company exists
    company = await pool.fetchrow(
        "SELECT id FROM companies WHERE ticker = $1", req.ticker.upper()
    )
    if not company:
        raise HTTPException(404, f"Company {req.ticker} not found")

    await pool.execute(
        """INSERT INTO watchlist (email, ticker)
           VALUES ($1, $2)
           ON CONFLICT (email, ticker) DO NOTHING""",
        req.email, req.ticker.upper(),
    )

    return {"status": "ok", "message": f"Added {req.ticker.upper()} to watchlist"}


@router.get("")
async def get_watchlist(email: str):
    pool = await get_pool()
    rows = await pool.fetch(
        """SELECT w.ticker, c.name, c.sector
           FROM watchlist w
           JOIN companies c ON c.ticker = w.ticker
           WHERE w.email = $1
           ORDER BY w.created_at DESC""",
        email,
    )
    return [dict(r) for r in rows]


@router.delete("/{ticker}")
async def remove_from_watchlist(ticker: str, email: str):
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM watchlist WHERE email = $1 AND ticker = $2",
        email, ticker.upper(),
    )
    return {"status": "ok", "message": f"Removed {ticker.upper()} from watchlist"}
