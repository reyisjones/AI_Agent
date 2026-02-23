"""
Tool: knowledge_search
Searches plain-text / Markdown files in the local docs/ folder using
simple TF-based keyword matching.  No external vector DB required.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".md", ".txt", ".rst"}


def _score_document(content: str, query_tokens: list[str]) -> float:
    """Very lightweight TF score: sum of token frequencies (case-insensitive)."""
    lowered = content.lower()
    return sum(lowered.count(tok) for tok in query_tokens)


def _snippet(content: str, query_tokens: list[str], max_chars: int = 400) -> str:
    """Return a short snippet around the first matching token."""
    lowered = content.lower()
    for tok in query_tokens:
        idx = lowered.find(tok)
        if idx != -1:
            start = max(0, idx - 100)
            end = min(len(content), idx + max_chars)
            snippet = content[start:end].strip()
            return f"…{snippet}…" if start > 0 else snippet
    return content[:max_chars].strip()


async def knowledge_search(query: str, top_k: int = 3) -> dict[str, Any]:
    """
    Search local documentation files for *query*.

    Args:
        query: Natural-language or keyword search query.
        top_k: Maximum number of results to return (default 3).
    """
    settings = get_settings()
    docs_dir = Path(settings.docs_path)

    if not docs_dir.exists():
        return {"error": f"Docs directory '{docs_dir}' not found.", "results": []}

    # Tokenise the query
    query_tokens = [
        t.lower()
        for t in re.split(r"\W+", query)
        if len(t) > 2
    ]
    if not query_tokens:
        return {"error": "Query too short or no useful tokens.", "results": []}

    scored: list[tuple[float, str, str]] = []  # (score, filename, snippet)

    for root, _, files in os.walk(docs_dir):
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in _SUPPORTED_EXTENSIONS:
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Could not read %s: %s", fpath, exc)
                continue

            score = _score_document(content, query_tokens)
            if score > 0:
                rel_path = str(fpath.relative_to(docs_dir))
                scored.append((score, rel_path, _snippet(content, query_tokens)))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_results = scored[:top_k]

    return {
        "query": query,
        "results": [
            {"file": rel, "score": score, "snippet": snip}
            for score, rel, snip in top_results
        ],
        "total_found": len(scored),
    }
