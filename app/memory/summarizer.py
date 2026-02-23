"""
Summarizer — runs as a background task triggered when a session ends or
exceeds a message threshold.

Calls the OpenAI API to condense the conversation into a short summary and
persists it to Postgres via long_term memory.
"""
from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import get_settings
from app.memory import long_term

logger = logging.getLogger(__name__)

_SUMMARIZER_PROMPT = (
    "You are a concise summarizer. Summarize the following conversation in "
    "2-4 sentences, capturing the user's intent, key decisions, and any "
    "important details. Be factual and brief."
)


async def summarize_and_store(
    session_id: str,
    messages: list[dict[str, Any]],
    user_id: str | None = None,
) -> str | None:
    """
    Summarize *messages* and persist to Postgres.
    Returns the summary string, or None on failure.
    """
    if len(messages) < 2:
        return None  # nothing meaningful to summarize

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Build a plain-text transcript
    transcript = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in messages
        if isinstance(m.get("content"), str)
    )

    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SUMMARIZER_PROMPT},
                {"role": "user", "content": transcript},
            ],
            max_tokens=256,
            temperature=0.0,
        )
        summary = response.choices[0].message.content or ""
        await long_term.save_summary(session_id, summary.strip(), user_id=user_id)
        logger.info("Summary stored for session %s", session_id)
        return summary
    except Exception as exc:  # noqa: BLE001
        logger.warning("Summarizer failed for session %s: %s", session_id, exc)
        return None
