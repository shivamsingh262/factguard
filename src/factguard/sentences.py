"""Sentence splitting that keeps whitespace, so dropped sentences leave tidy text."""

from __future__ import annotations

import re
from collections.abc import Iterable

_END = re.compile(r"[.!?]+[\"')\]]*[ \t]*(?:\n\s*|[ \t]+)|\n\s*")
_ABBREVIATION = re.compile(r"(?:\b(?:e\.g|i\.e|vs|etc|approx|incl|Mr|Ms|Dr)|^\s*\d{1,3})\.$")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences and lines. Each piece keeps its trailing whitespace,
    so "".join(pieces) == text."""
    pieces: list[str] = []
    start = 0
    for m in _END.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        # "e.g. " and the "1. " of a numbered list are not sentence ends.
        if text[m.start()] == "." and _ABBREVIATION.search(text[line_start : m.start() + 1]):
            continue
        pieces.append(text[start : m.end()])
        start = m.end()
    if start < len(text):
        pieces.append(text[start:])
    return pieces


_EMPTY_BULLET = re.compile(r"(?m)^[ \t]*(?:[-*•]|\d{1,3}[.)])[ \t]*$\n?")


def drop_sentences(text: str, spans: Iterable[tuple[int, int]]) -> tuple[str, list[str]]:
    """Remove every sentence that overlaps one of the (start, end) spans.

    Returns the remaining text and the removed sentences."""
    spans = list(spans)
    kept: list[str] = []
    dropped: list[str] = []
    pos = 0
    for piece in split_sentences(text):
        start, end = pos, pos + len(piece)
        pos = end
        if any(s < end and e > start for s, e in spans):
            body = piece.rstrip()
            dropped.append(body.strip())
            # A sentence that ended its line takes the line break with it; keep the
            # break unless the line is already closed, so lists keep their shape.
            if "\n" in piece[len(body) :] and kept and not kept[-1].endswith("\n"):
                kept.append("\n")
        else:
            kept.append(piece)
    out = "".join(kept)
    out = _EMPTY_BULLET.sub("", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip(), dropped
