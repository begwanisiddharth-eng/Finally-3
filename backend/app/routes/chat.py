"""Chat endpoints (sections 8, 9)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..chat import ChatError, handle_chat
from ..schemas import ChatRequest

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("")
async def post_chat(request: Request, body: ChatRequest) -> dict:
    state = request.app.state
    try:
        return await handle_chat(state.db, state.cache, state.manager, body.message)
    except ChatError as e:
        # Upstream LLM failure: no chat_messages row is written (section 8).
        raise HTTPException(status_code=502, detail=f"Chat upstream failure: {e}") from e


@router.get("/history")
async def get_history(request: Request) -> list[dict]:
    return await request.app.state.db.list_chat(limit=20)
