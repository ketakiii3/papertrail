"""FastAPI API Server entry point."""

import sys
sys.path.insert(0, "/app")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from shared.db import get_pool, close_pool
from shared.redis_client import get_redis, close_redis
from shared.config import settings

from src.routers import companies, search, watchlist, ws, filings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await get_pool()
    await get_redis()
    yield
    # Shutdown
    await close_pool()
    await close_redis()


app = FastAPI(
    title="PaperTrail API",
    description="SEC Filing Contradiction Detector",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(search.router)
app.include_router(watchlist.router)
app.include_router(ws.router)
app.include_router(filings.router)


@app.get("/")
async def root():
    """Avoid a bare 404 when opening http://localhost:8000/ in the browser."""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "papertrail-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )
