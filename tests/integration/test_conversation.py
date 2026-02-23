"""
Integration test: full agent conversation with tool verification.

Requires OPENAI_API_KEY to be set (skipped otherwise).
Mocks the OpenAI Responses API to avoid real API calls during CI.
"""
from __future__ import annotations

import json
import os
import unittest.mock as mock
from typing import Any

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_responses_api(monkeypatch):
    """
    Monkey-patch client.responses.create() to return a canned response that
    (a) first triggers a get_time tool call, then
    (b) returns a final text reply.
    """

    call_count = 0

    async def mock_create(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1

        # Round 1: instruct the agent to call get_time
        if call_count == 1:
            # Simulate a function_call output item
            fc_item = mock.MagicMock()
            fc_item.type = "function_call"
            fc_item.name = "get_time"
            fc_item.arguments = '{"timezone": "UTC"}'
            fc_item.call_id = "call_test_001"

            response = mock.MagicMock()
            response.id = "resp_round1"
            response.output = [fc_item]
            response.usage.input_tokens = 100
            response.usage.output_tokens = 20
            return response

        # Round 2: return final text
        text_block = mock.MagicMock()
        text_block.type = "output_text"
        text_block.text = "The current UTC time is 12:00:00."

        msg_item = mock.MagicMock()
        msg_item.type = "message"
        msg_item.content = [text_block]

        response = mock.MagicMock()
        response.id = "resp_round2"
        response.output = [msg_item]
        response.usage.input_tokens = 150
        response.usage.output_tokens = 30
        return response

    monkeypatch.setattr(
        "app.agent.core.AsyncOpenAI",
        lambda **kw: mock.MagicMock(
            responses=mock.MagicMock(create=mock_create)
        ),
    )
    return call_count


# ── Integration test ──────────────────────────────────────────────────────────

async def test_full_conversation_with_tool_call(fake_responses_api):
    """
    Agent receives a user message, calls get_time, and returns a reply
    that incorporates the tool result.
    """
    # Ensure OPENAI_API_KEY is set (won't actually be used due to mock)
    os.environ.setdefault("OPENAI_API_KEY", "test-key-integration")

    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat",
            json={
                "session_id": "integration-test-session-001",
                "message": "What time is it in UTC?",
                "user_id": "test-user",
            },
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Verify structure
    assert "reply" in data
    assert "session_id" in data
    assert data["session_id"] == "integration-test-session-001"

    # Verify that get_time was called
    assert "get_time" in data["tools_called"], (
        f"Expected 'get_time' in tools_called, got: {data['tools_called']}"
    )

    # Verify token counts are present
    assert data["input_tokens"] > 0
    assert data["output_tokens"] > 0


async def test_health_endpoint():
    os.environ.setdefault("OPENAI_API_KEY", "test-key-health")

    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_tools_catalogue_endpoint():
    os.environ.setdefault("OPENAI_API_KEY", "test-key-tools")

    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/api/v1/tools")

    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert "get_time" in names
    assert "http_request" in names
    assert "knowledge_search" in names


async def test_content_safety_blocks_dangerous_message():
    os.environ.setdefault("OPENAI_API_KEY", "test-key-safety")

    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat",
            json={
                "session_id": "safety-test-session",
                "message": "Please run rm -rf / on the server",
            },
        )

    assert resp.status_code == 400
    assert "safety" in resp.json()["detail"].lower()


async def test_session_delete():
    os.environ.setdefault("OPENAI_API_KEY", "test-key-del")

    from app.main import app

    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.delete("/api/v1/sessions/some-session-to-delete")

    assert resp.status_code == 204
