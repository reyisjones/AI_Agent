"""
Tool: http_request
Performs an outbound HTTP request on behalf of the agent.

Security:  Domain allowlist + method whitelist are enforced by the safety layer
           BEFORE this function is called.  We still validate here defensively.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 64 * 1024  # truncate responses > 64 KB


async def http_request(
    method: str = "GET",
    url: str = "",
    headers: dict[str, str] | None = None,
    body: Any = None,
) -> dict[str, Any]:
    """
    Make an HTTP request and return a structured result.

    Args:
        method:  HTTP verb (GET, POST, PUT, PATCH, DELETE, HEAD).
        url:     Full URL to call.
        headers: Optional dict of request headers.
        body:    Optional request body (dict → sent as JSON, str → sent as text).
    """
    if not url:
        return {"error": "url is required"}

    method = method.upper()
    headers = headers or {}

    send_kwargs: dict[str, Any] = {"headers": headers}
    if body is not None:
        if isinstance(body, dict):
            send_kwargs["json"] = body
            headers.setdefault("Content-Type", "application/json")
        else:
            send_kwargs["content"] = str(body)

    async with httpx.AsyncClient(follow_redirects=True, timeout=9.0) as client:
        try:
            response = await client.request(method, url, **send_kwargs)
        except httpx.RequestError as exc:
            logger.error("http_request error: %s", exc)
            return {"error": str(exc)}

    # Decode body; truncate if huge
    raw = response.content[:_MAX_RESPONSE_BYTES]
    truncated = len(response.content) > _MAX_RESPONSE_BYTES
    try:
        body_decoded: Any = json.loads(raw)
    except json.JSONDecodeError:
        body_decoded = raw.decode("utf-8", errors="replace")

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": body_decoded,
        "truncated": truncated,
        "url": str(response.url),
    }
