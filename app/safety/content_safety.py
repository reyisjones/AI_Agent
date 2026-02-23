"""
Content-safety hook and tool-safety layer.

content_safety_check  — basic keyword/pattern filter on user input + model output.
ToolSafetyLayer       — wraps tool execution with allow/deny logic, rate limiting,
                        and timeout enforcement.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── patterns that should always be refused ──────────────────────────────────
_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(rm\s+-rf|format\s+c:|del\s+/[sq])\b", re.IGNORECASE),
    re.compile(r"\b(exec|eval|__import__)\s*\(", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"(DROP\s+TABLE|DELETE\s+FROM|TRUNCATE\s+TABLE)", re.IGNORECASE),
]

_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),       # credit card
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
]


class ContentSafetyError(ValueError):
    """Raised when content fails the safety check."""


def content_safety_check(text: str, *, context: str = "input") -> str:
    """
    Scan *text* for blocked patterns.
    Returns the (potentially redacted) text or raises ContentSafetyError.
    """
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(text):
            logger.warning("Content safety block [%s]: matched pattern %s", context, pattern.pattern)
            raise ContentSafetyError(
                f"Request refused: content safety policy violation ({context})."
            )

    # Redact sensitive data from output (best-effort)
    result = text
    if context == "output":
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub("[REDACTED]", result)

    return result


# ── Tool safety layer ────────────────────────────────────────────────────────

class ToolSafetyError(ValueError):
    """Raised when a tool call is rejected by the safety layer."""


class _RateLimiter:
    """Simple in-process sliding-window rate limiter per tool name."""

    def __init__(self, max_calls: int, window_seconds: float = 60.0) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._calls: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> None:
        now = time.monotonic()
        window_start = now - self._window
        calls = [t for t in self._calls[key] if t > window_start]
        if len(calls) >= self._max:
            raise ToolSafetyError(
                f"Rate limit exceeded for '{key}': max {self._max} calls/min."
            )
        calls.append(now)
        self._calls[key] = calls


_limiter: _RateLimiter | None = None


def _get_limiter() -> _RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = _RateLimiter(get_settings().tool_rate_limit_per_minute)
    return _limiter


def _validate_http_request_args(args: dict[str, Any]) -> None:
    """Enforce domain allowlist and method whitelist for http_request."""
    settings = get_settings()
    url: str = args.get("url", "")
    if not url:
        raise ToolSafetyError("http_request: 'url' is required.")

    parsed = urlparse(url)
    host = parsed.hostname or ""
    allowed = settings.allowed_http_domains
    if not any(host == d or host.endswith(f".{d}") for d in allowed):
        raise ToolSafetyError(
            f"http_request: domain '{host}' is not in the allowlist. "
            f"Allowed: {allowed}"
        )

    method = args.get("method", "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
        raise ToolSafetyError(f"http_request: method '{method}' is not allowed.")


_TOOL_VALIDATORS: dict[str, Any] = {
    "http_request": _validate_http_request_args,
}


async def safe_tool_call(
    tool_name: str,
    tool_fn: Any,
    args: dict[str, Any],
) -> Any:
    """
    Execute *tool_fn* with *args* after running:
      1. rate-limit check
      2. argument-level validators (per-tool)
      3. timeout enforcement
    """
    settings = get_settings()

    # Rate limit
    _get_limiter().check(tool_name)

    # Per-tool validation
    if tool_name in _TOOL_VALIDATORS:
        _TOOL_VALIDATORS[tool_name](args)

    # Scan arguments for blocked content
    for v in args.values():
        if isinstance(v, str):
            content_safety_check(v, context=f"tool:{tool_name}:arg")

    # Execute with timeout
    try:
        return await asyncio.wait_for(
            tool_fn(**args),
            timeout=settings.tool_timeout_seconds,
        )
    except asyncio.TimeoutError:
        raise ToolSafetyError(
            f"Tool '{tool_name}' timed out after {settings.tool_timeout_seconds}s."
        )
