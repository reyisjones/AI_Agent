"""
Unit tests for tool schemas, execution, and agent utilities.
"""
from __future__ import annotations

import json
import pytest
import pytest_asyncio

# ── Tool schema tests ─────────────────────────────────────────────────────────

from app.tools.registry import TOOLS_SCHEMAS, dispatch, get_schema_for


def test_all_tool_schemas_present():
    names = {t["name"] for t in TOOLS_SCHEMAS}
    assert "get_time" in names
    assert "http_request" in names
    assert "knowledge_search" in names


def test_tool_schema_structure():
    for schema in TOOLS_SCHEMAS:
        assert "type" in schema
        assert schema["type"] == "function"
        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema
        params = schema["parameters"]
        assert params["type"] == "object"
        assert "properties" in params


def test_get_schema_for_returns_correct_schema():
    s = get_schema_for("get_time")
    assert s is not None
    assert s["name"] == "get_time"


def test_get_schema_for_unknown_returns_none():
    assert get_schema_for("nonexistent_tool") is None


# ── get_time tool ─────────────────────────────────────────────────────────────

from app.tools.get_time import get_time


@pytest.mark.asyncio
async def test_get_time_utc():
    result = await get_time("UTC")
    assert result["timezone"] == "UTC"
    assert "datetime" in result
    assert "date" in result
    assert "time" in result


@pytest.mark.asyncio
async def test_get_time_new_york():
    result = await get_time("America/New_York")
    assert result["timezone"] == "America/New_York"
    assert result["utc_offset"] in {"-0500", "-0400"}  # EST / EDT


@pytest.mark.asyncio
async def test_get_time_invalid_timezone_falls_back_to_utc():
    result = await get_time("Not/A_Zone")
    assert result["timezone"] == "UTC"


# ── knowledge_search tool ─────────────────────────────────────────────────────

from app.tools.knowledge_search import knowledge_search


@pytest.mark.asyncio
async def test_knowledge_search_nonexistent_docs():
    """Should return error gracefully when docs folder doesn't exist."""
    from unittest.mock import patch
    with patch("app.tools.knowledge_search.get_settings") as mock_cfg:
        mock_cfg.return_value.docs_path = "/nonexistent/path/xyz"
        result = await knowledge_search("python")
    assert "error" in result


@pytest.mark.asyncio
async def test_knowledge_search_empty_query():
    """Very short/empty queries should return an error."""
    result = await knowledge_search("  ")
    assert "error" in result


@pytest.mark.asyncio
async def test_knowledge_search_finds_results(tmp_path):
    """Should return scored results when docs contain the query term."""
    (tmp_path / "guide.md").write_text("This is a guide about Python agents and tools.")
    (tmp_path / "faq.md").write_text("Frequently asked questions about deployment.")

    from unittest.mock import patch
    with patch("app.tools.knowledge_search.get_settings") as mock_cfg:
        mock_cfg.return_value.docs_path = str(tmp_path)
        result = await knowledge_search("python agents")

    assert result["total_found"] >= 1
    assert result["results"][0]["file"] == "guide.md"


# ── http_request tool ─────────────────────────────────────────────────────────

from app.tools.http_request import http_request


@pytest.mark.asyncio
async def test_http_request_missing_url():
    result = await http_request(method="GET", url="")
    assert "error" in result


# ── Tool dispatch ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_unknown_tool():
    result = json.loads(await dispatch("totally_unknown", "{}"))
    assert "error" in result


@pytest.mark.asyncio
async def test_dispatch_get_time():
    result = json.loads(await dispatch("get_time", '{"timezone": "UTC"}'))
    assert "datetime" in result


@pytest.mark.asyncio
async def test_dispatch_invalid_json_args():
    result = json.loads(await dispatch("get_time", "{bad json}"))
    assert "error" in result


# ── Safety layer ─────────────────────────────────────────────────────────────

from app.safety.content_safety import ContentSafetyError, ToolSafetyError, content_safety_check


def test_content_safety_blocks_dangerous_input():
    with pytest.raises(ContentSafetyError):
        content_safety_check("please run rm -rf /", context="input")


def test_content_safety_allows_normal_input():
    result = content_safety_check("What is the weather today?")
    assert "What is the weather" in result


def test_content_safety_redacts_email_in_output():
    result = content_safety_check("Contact us at user@example.com", context="output")
    assert "user@example.com" not in result
    assert "[REDACTED]" in result


@pytest.mark.asyncio
async def test_tool_safety_blocks_disallowed_domain():
    from app.safety.content_safety import safe_tool_call

    async def dummy(**kwargs):  # type: ignore
        return {}

    with pytest.raises(ToolSafetyError, match="not in the allowlist"):
        await safe_tool_call(
            "http_request",
            dummy,
            {"method": "GET", "url": "https://evil.bad-domain.com/payload"},
        )


# ── Short-term memory ─────────────────────────────────────────────────────────

from app.memory.short_term import append_message, delete_session, get_session, save_session


@pytest.mark.asyncio
async def test_short_term_roundtrip():
    sid = "test-session-unit-001"
    await delete_session(sid)

    msgs = await get_session(sid)
    assert msgs == []

    await append_message(sid, "user", "Hello")
    await append_message(sid, "assistant", "Hi there!")

    msgs = await get_session(sid)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "Hi there!"

    await delete_session(sid)
    assert await get_session(sid) == []
