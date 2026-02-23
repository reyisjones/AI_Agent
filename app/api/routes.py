"""
FastAPI route handlers.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.agent.core import run_agent
from app.api.models import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    ToolSchema,
)
from app.config import get_settings
from app.memory import short_term
from app.memory.summarizer import summarize_and_store
from app.observability.telemetry import get_request_id, new_request_id
from app.safety.content_safety import ContentSafetyError, content_safety_check
from app.tools.registry import TOOLS_SCHEMAS

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

_SUMMARIZE_THRESHOLD = 20  # summarize after this many messages in a session


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.service_version,
        environment=settings.app_env,
    )


# ── Tools catalogue ───────────────────────────────────────────────────────────

@router.get("/tools", response_model=list[ToolSchema], tags=["tools"])
async def list_tools() -> list[ToolSchema]:
    """Return the list of available tools and their schemas."""
    return [
        ToolSchema(
            name=t["name"],
            description=t.get("description", ""),
            parameters=t.get("parameters", {}),
        )
        for t in TOOLS_SCHEMAS
    ]


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    tags=["agent"],
)
async def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> ChatResponse:
    """
    Send a message to the AI agent and receive a reply.

    Pass the same `session_id` across turns to maintain conversation context.
    """
    rid = new_request_id()
    logger.info(
        "chat request | session=%s user=%s request_id=%s",
        body.session_id,
        body.user_id or "anon",
        rid,
    )

    # ── Input safety check ────────────────────────────────────────────────
    try:
        safe_message = content_safety_check(body.message, context="input")
    except ContentSafetyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # ── Run agent ─────────────────────────────────────────────────────────
    try:
        result = await run_agent(
            session_id=body.session_id,
            user_message=safe_message,
            user_id=body.user_id,
        )
    except Exception as exc:
        logger.exception("Agent run failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent encountered an internal error. Please try again.",
        )

    # ── Output safety check ───────────────────────────────────────────────
    try:
        safe_reply = content_safety_check(result["reply"], context="output")
    except ContentSafetyError:
        safe_reply = "I'm sorry, I can't provide that response."

    # ── Background: maybe summarize session ───────────────────────────────
    session = await short_term.get_session(body.session_id)
    if len(session) >= _SUMMARIZE_THRESHOLD:
        background_tasks.add_task(
            summarize_and_store,
            body.session_id,
            session,
            body.user_id,
        )

    return ChatResponse(
        session_id=result["session_id"],
        response_id=result["response_id"],
        reply=safe_reply,
        tools_called=result["tools_called"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
    )


# ── Session management ────────────────────────────────────────────────────────

@router.delete("/sessions/{session_id}", status_code=204, tags=["agent"])
async def clear_session(session_id: str) -> None:
    """Delete a session and its short-term memory."""
    await short_term.delete_session(session_id)
