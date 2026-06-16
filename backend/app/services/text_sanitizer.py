"""Helpers for cleaning provider-specific text artifacts."""

from __future__ import annotations

import re

_FILE_CITATION_RE = re.compile(
    r"[\u25a0\u25aa\u25fc\u25fe\u2606\u2605\u21a9\u21b5\u3010\u3011\[\]\(\)]*"
    r"(?:filcite|filecite)"
    r"\S*",
    flags=re.IGNORECASE,
)
_CITATION_GLYPHS_RE = re.compile(r"[\u25a0\u25aa\u25fc\u25fe\u2606\u2605\u21a9\u21b5]")


def clean_agent_text(text: str) -> str:
    """Remove raw citation markers returned by Foundry/RAG responses."""
    cleaned = _FILE_CITATION_RE.sub("", text)
    cleaned = _CITATION_GLYPHS_RE.sub("", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()
