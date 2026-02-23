"""
Long-term memory — user preferences and conversation summaries in Postgres.

Uses SQLAlchemy async core (no ORM) to stay lightweight.
Tables are created on startup if they don't exist.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None


# ── Engine singleton ─────────────────────────────────────────────────────────

async def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.postgres_dsn,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=False,
        )
    return _engine


# ── Schema bootstrap ─────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id     TEXT PRIMARY KEY,
    preferences JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    user_id     TEXT,
    summary     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_summaries_user  ON conversation_summaries (user_id);
CREATE INDEX IF NOT EXISTS ix_summaries_sess  ON conversation_summaries (session_id);
"""


async def init_db() -> None:
    """Create tables if they do not exist.  Call once at startup."""
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            for stmt in _DDL.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(text(stmt))
        logger.info("Long-term memory: Postgres tables ready.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Postgres unavailable — long-term memory disabled. %s", exc)


# ── User preferences ──────────────────────────────────────────────────────────

async def get_preferences(user_id: str) -> dict[str, Any]:
    try:
        engine = await get_engine()
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT preferences FROM user_preferences WHERE user_id = :uid"),
                {"uid": user_id},
            )
            r = row.fetchone()
            return r[0] if r else {}
    except Exception as exc:
        logger.warning("get_preferences failed: %s", exc)
        return {}


async def upsert_preferences(user_id: str, prefs: dict[str, Any]) -> None:
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO user_preferences (user_id, preferences, updated_at)
                    VALUES (:uid, :prefs::jsonb, NOW())
                    ON CONFLICT (user_id) DO UPDATE
                        SET preferences = user_preferences.preferences || :prefs::jsonb,
                            updated_at  = NOW()
                    """
                ),
                {"uid": user_id, "prefs": __import__("json").dumps(prefs)},
            )
    except Exception as exc:
        logger.warning("upsert_preferences failed: %s", exc)


# ── Conversation summaries ────────────────────────────────────────────────────

async def save_summary(session_id: str, summary: str, user_id: str | None = None) -> None:
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO conversation_summaries
                        (session_id, user_id, summary, created_at)
                    VALUES (:sid, :uid, :summary, NOW())
                    """
                ),
                {"sid": session_id, "uid": user_id, "summary": summary},
            )
    except Exception as exc:
        logger.warning("save_summary failed: %s", exc)


async def get_summaries(user_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve the most recent *limit* summaries for *user_id*."""
    try:
        engine = await get_engine()
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    """
                    SELECT session_id, summary, created_at
                    FROM   conversation_summaries
                    WHERE  user_id = :uid
                    ORDER  BY created_at DESC
                    LIMIT  :lim
                    """
                ),
                {"uid": user_id, "lim": limit},
            )
            return [
                {"session_id": r[0], "summary": r[1], "created_at": r[2].isoformat()}
                for r in rows.fetchall()
            ]
    except Exception as exc:
        logger.warning("get_summaries failed: %s", exc)
        return []
