"""Health endpoint (sections 6, 8)."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["system"])

HEALTH_FRESHNESS_SECONDS = 10.0  # cache counts as healthy if written within this window


@router.get("/health")
async def health(request: Request) -> dict:
    state = request.app.state
    healthy = state.cache.seconds_since_update() <= HEALTH_FRESHNESS_SECONDS
    return {
        "status": "ok",
        "data_source": state.manager.active_source_name,
        "market_data_healthy": healthy,
    }
