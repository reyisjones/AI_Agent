"""
Tool registry — single source of truth for tool schemas and handlers.

Schemas follow the OpenAI function-calling JSON Schema format.
The agent core reads TOOLS_SCHEMAS to build the `tools` payload and
calls dispatch() to execute a selected tool.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Coroutine

from app.safety.content_safety import safe_tool_call
from app.tools.get_time import get_time
from app.tools.http_request import http_request
from app.tools.knowledge_search import knowledge_search

logger = logging.getLogger(__name__)

# ── JSON Schemas (OpenAI function format) ────────────────────────────────────

TOOLS_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_time",
        "description": (
            "Returns the current date and time for a given IANA timezone. "
            "Use this whenever users ask about the current time or date."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "IANA timezone name, e.g. 'America/New_York', "
                        "'Europe/London', 'Asia/Tokyo'. Defaults to 'UTC'."
                    ),
                }
            },
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "http_request",
        "description": (
            "Performs an outbound HTTP request to an allowed domain and returns "
            "the response. Useful for fetching data from external APIs. "
            "Only allowed domains: see configuration."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
                    "description": "HTTP method.",
                },
                "url": {
                    "type": "string",
                    "description": "Full URL including scheme, e.g. https://httpbin.org/get",
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers as key-value pairs.",
                    "additionalProperties": {"type": "string"},
                },
                "body": {
                    "type": "object",
                    "description": "Optional request body (sent as JSON).",
                },
            },
            "required": ["method", "url"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "knowledge_search",
        "description": (
            "Searches the local documentation knowledge base for information "
            "relevant to a query. Use this to answer questions about the product, "
            "policies, or any topic covered in the docs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query in natural language or keywords.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 3).",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": False,
    },
]

# ── Handler map ───────────────────────────────────────────────────────────────

_HANDLERS: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {
    "get_time": get_time,
    "http_request": http_request,
    "knowledge_search": knowledge_search,
}


async def dispatch(tool_name: str, arguments_json: str) -> str:
    """
    Parse *arguments_json*, run the tool through the safety layer, and
    return a JSON-encoded result string (as expected by the Responses API).
    """
    if tool_name not in _HANDLERS:
        error = {"error": f"Unknown tool: '{tool_name}'"}
        return json.dumps(error)

    try:
        args: dict[str, Any] = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid tool arguments JSON: {exc}"})

    handler = _HANDLERS[tool_name]

    try:
        result = await safe_tool_call(tool_name, handler, args)
    except Exception as exc:  # safety errors, timeouts, etc.
        logger.warning("Tool '%s' rejected or failed: %s", tool_name, exc)
        return json.dumps({"error": str(exc)})

    logger.info("Tool '%s' completed successfully", tool_name)
    return json.dumps(result, default=str)


def get_schema_for(tool_name: str) -> dict[str, Any] | None:
    """Return the JSON schema for a named tool, or None if not found."""
    return next((s for s in TOOLS_SCHEMAS if s["name"] == tool_name), None)
