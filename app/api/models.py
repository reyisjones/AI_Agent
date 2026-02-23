"""
Pydantic request/response models for the Agent API.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(
        ...,
        description="Unique session identifier (UUID recommended). "
        "Use the same value across turns to maintain conversation history.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=32_000,
        description="User message text.",
    )
    user_id: str | None = Field(
        default=None,
        description="Optional user identifier for long-term personalisation.",
    )


class ChatResponse(BaseModel):
    session_id: str
    response_id: str = Field(description="OpenAI response ID for this turn.")
    reply: str = Field(description="Assistant reply text.")
    tools_called: list[str] = Field(
        default_factory=list, description="Names of tools invoked during this turn."
    )
    input_tokens: int
    output_tokens: int


class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str | None = None
