"""
Short-term memory — per-session conversation history.

Primary backend: Redis (JSON-encoded list of message dicts).
Fallback:        in-process dict (single-process only; lost on restart).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── In-process fallback ──────────────────────────────────────────────────────
_local_store: dict[str, list[dict[str, Any]]] = {}

# ── Redis client singleton ───────────────────────────────────────────────────
_redis_client: Any = None
_redis_available = False


async def _get_redis() -> Any:
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as aioredis  # type: ignore[import]

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        _redis_client = client
        _redis_available = True
        logger.info("Short-term memory: Redis connected at %s", settings.redis_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable (%s). Using in-memory fallback.", exc)
        _redis_available = False
    return _redis_client


# ── Public API ────────────────────────────────────────────────────────────────

async def get_session(session_id: str) -> list[dict[str, Any]]:
    """Return the message history for *session_id* (empty list if new)."""
    client = await _get_redis()
    if _redis_available and client:
        raw = await client.get(_key(session_id))
        return json.loads(raw) if raw else []
    return list(_local_store.get(session_id, []))


async def save_session(session_id: str, messages: list[dict[str, Any]]) -> None:
    """Persist *messages* for *session_id*."""
    client = await _get_redis()
    if _redis_available and client:
        settings = get_settings()
        await client.setex(
            _key(session_id),
            settings.session_ttl_seconds,
            json.dumps(messages),
        )
    else:
        _local_store[session_id] = list(messages)


async def delete_session(session_id: str) -> None:
    """Remove a session (e.g. on explicit logout)."""
    client = await _get_redis()
    if _redis_available and client:
        await client.delete(_key(session_id))
    else:
        _local_store.pop(session_id, None)


async def append_message(
    session_id: str, role: str, content: str
) -> list[dict[str, Any]]:
    """Append one message and return the updated history."""
    messages = await get_session(session_id)
    messages.append({"role": role, "content": content})
    await save_session(session_id, messages)
    return messages


def _key(session_id: str) -> str:
    return f"session:{session_id}"
