"""Chunking strategies. Sizes are in words (a stable, explainable proxy for tokens: ~1.3 tokens per word)."""

from __future__ import annotations

import re
from dataclasses import dataclass

STRATEGIES = ("fixed", "recursive", "markdown")


@dataclass
class Chunk:
    text: str
    start: int
    end: int
    heading: str = ""

    @property
    def words(self) -> int:
        return len(self.text.split())


def _word_spans(text: str, offset: int = 0) -> list[tuple[int, int]]:
    return [(m.start() + offset, m.end() + offset) for m in re.finditer(r"\S+", text)]


def fixed(text: str, size: int, overlap: int, heading: str = "", offset: int = 0) -> list[Chunk]:
    """Sliding window of `size` words with `overlap` words shared between neighbours. Ignores structure."""
    spans = _word_spans(text, offset)
    if not spans:
        return []
    step = max(1, size - overlap)
    out = []
    for i in range(0, len(spans), step):
        window = spans[i: i + size]
        start, end = window[0][0], window[-1][1]
        out.append(Chunk(text[start - offset: end - offset], start, end, heading))
        if i + size >= len(spans):
            break
    return out


def recursive(text: str, size: int, overlap: int, heading: str = "", offset: int = 0) -> list[Chunk]:
    """Split on paragraphs, then sentences, packing whole units up to `size` words; overlap carries the tail."""
    units: list[tuple[int, int]] = []
    for para in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", text):
        ptext = para.group(0)
        if len(ptext.split()) <= size:
            units.append((para.start(), para.end()))
            continue
        for sent in re.finditer(r"[^.!?]+(?:[.!?]+|$)", ptext):
            if sent.group(0).strip():
                units.append((para.start() + sent.start(), para.start() + sent.end()))
    out: list[Chunk] = []
    cur: list[tuple[int, int]] = []
    count = 0
    for u in units:
        n = len(text[u[0]:u[1]].split())
        if n > size:  # a single huge sentence: fall back to fixed windows
            if cur:
                out.append(_mk(text, cur, heading, offset))
                cur, count = [], 0
            out.extend(fixed(text[u[0]:u[1]], size, overlap, heading, offset + u[0]))
            continue
        if count + n > size and cur:
            out.append(_mk(text, cur, heading, offset))
            tail: list[tuple[int, int]] = []
            tail_words = 0
            for prev in reversed(cur):  # carry whole trailing units as overlap
                w = len(text[prev[0]:prev[1]].split())
                if tail_words + w > overlap:
                    break
                tail.insert(0, prev)
                tail_words += w
            cur, count = tail, tail_words
        cur.append(u)
        count += n
    if cur:
        out.append(_mk(text, cur, heading, offset))
    return out


def _mk(text: str, units: list[tuple[int, int]], heading: str, offset: int) -> Chunk:
    start, end = units[0][0], units[-1][1]
    return Chunk(text[start:end].strip(), start + offset, end + offset, heading)


def markdown(text: str, size: int, overlap: int) -> list[Chunk]:
    """Structure-aware: split on headings first, keep the heading path with each chunk, then pack recursively."""
    sections = list(re.finditer(r"^(#{1,6})\s+(.+)$", text, flags=re.M))
    if not sections:
        return recursive(text, size, overlap)
    out: list[Chunk] = []
    path: list[str] = []
    if sections[0].start() > 0 and text[: sections[0].start()].strip():
        out.extend(recursive(text[: sections[0].start()], size, overlap))
    for i, m in enumerate(sections):
        level = len(m.group(1))
        path = path[: level - 1] + [m.group(2).strip()]
        body_start = m.end()
        body_end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
        body = text[body_start:body_end]
        if body.strip():
            out.extend(recursive(body, size, overlap, " › ".join(path), body_start))
    return out


def chunk(text: str, strategy: str, size: int, overlap: int) -> list[Chunk]:
    size = max(20, min(size, 1000))
    overlap = max(0, min(overlap, size // 2))
    if strategy == "fixed":
        return fixed(text, size, overlap)
    if strategy == "markdown":
        return markdown(text, size, overlap)
    return recursive(text, size, overlap)
