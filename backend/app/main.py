"""FastAPI entrypoint: wires the market data manager, API routers, lifespan
init/shutdown (section 7), the normalized error envelope, and static serving."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")  # must precede any env read (section 5)

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .db import Database  # noqa: E402
from .market import MarketDataManager, PriceCache  # noqa: E402
from .portfolio import portfolio_total_value  # noqa: E402
from .routes import (  # noqa: E402
    chat_router,
    health_router,
    portfolio_router,
    system_router,
    watchlist_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL = 30.0  # seconds between portfolio-value snapshots (section 7)


def _first_validation_message(exc: RequestValidationError) -> str:
    """Flatten a Pydantic request-validation error into one human message."""
    errors = exc.errors()
    if not errors:
        return "Invalid request."
    first = errors[0]
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    msg = first.get("msg", "Invalid request.")
    return f"{loc}: {msg}" if loc else msg

def _db_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH") or (REPO_ROOT / "db" / "finally.db"))


def _frontend_out() -> Path:
    return Path(os.environ.get("FRONTEND_DIR") or (REPO_ROOT / "frontend" / "out"))


async def _snapshot_loop(db: Database, cache: PriceCache) -> None:
    """Record a portfolio-value snapshot every SNAPSHOT_INTERVAL seconds."""
    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL)
        try:
            await db.insert_snapshot(await portfolio_total_value(db, cache))
        except Exception:
            logger.exception("Portfolio snapshot failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize + seed the database.
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    await db.connect()
    # Each app start begins with a blank chat (no prior-session history).
    await db.clear_chat()

    # 2. Load watchlist + held tickers.
    watchlist = await db.list_watchlist()
    positions = [p["ticker"] for p in await db.list_positions()]
    tracked = list(dict.fromkeys(watchlist + positions))  # union, order-stable

    # 3. Start the market data manager with the union.
    cache = PriceCache()
    manager = MarketDataManager(cache)
    await manager.start(tracked)

    app.state.db = db
    app.state.cache = cache
    app.state.manager = manager

    # 4. Start the snapshot background task.
    snapshot_task = asyncio.create_task(_snapshot_loop(db, cache), name="snapshot-loop")

    # 5. Take the startup snapshot so the P&L chart has a point immediately.
    await db.insert_snapshot(await portfolio_total_value(db, cache))

    logger.info("FinAlly backend ready (source=%s)", manager.active_source_name)
    try:
        yield
    finally:
        # Shutdown in reverse order (section 7).
        snapshot_task.cancel()
        try:
            await snapshot_task
        except asyncio.CancelledError:
            pass
        await manager.stop()
        await db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="FinAlly", lifespan=lifespan)

    # Normalized error envelope: the frontend extracts {"error": ...} always.
    @app.exception_handler(HTTPException)
    async def _http_exc(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": _first_validation_message(exc)})

    @app.exception_handler(Exception)
    async def _unhandled_exc(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"error": "Internal server error"})

    # API routers first, then the SSE stream, then the static mount last so the
    # root mount cannot shadow /api/* routes (section 11).
    app.include_router(portfolio_router)
    app.include_router(watchlist_router)
    app.include_router(chat_router)
    app.include_router(health_router)
    app.include_router(system_router)

    # The SSE router reads the cache from app.state at request time.
    @app.get("/api/stream/prices")
    async def stream_prices(request: Request):
        from fastapi.responses import StreamingResponse

        from .market.stream import _generate_events

        return StreamingResponse(
            _generate_events(request.app.state.cache, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    frontend_out = _frontend_out()
    if frontend_out.is_dir():
        app.mount("/", StaticFiles(directory=frontend_out, html=True), name="static")
    else:
        logger.warning("Frontend build not found at %s; serving API only", frontend_out)

    return app


app = create_app()
