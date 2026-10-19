"""Ingestion, chunking, permission filtering, retrieval and reranking for document Q&A."""

from __future__ import annotations

import base64
import io
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..core.text import TfidfIndex, terms

CORPUS_DIR = Path(__file__).parent / "corpus"


@dataclass
class Document:
    id: str
    title: str
    text: str
    allowed_groups: list[str] = field(default_factory=lambda: ["everyone"])


@dataclass
class Chunk:
    id: str
    doc_id: str
    title: str
    section: str
    text: str
    position: int

    def to_dict(self) -> dict:
        return asdict(self)


def load_seed_corpus() -> list[Document]:
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        meta: dict[str, str] = {}
        body = raw
        if raw.startswith("---"):
            _, front, body = raw.split("---", 2)
            for line in front.strip().splitlines():
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        groups = [g.strip() for g in meta.get("allowed_groups", "everyone").split(",") if g.strip()]
        docs.append(Document(path.stem, meta.get("title", path.stem), body.strip(), groups))
    return docs


def extract_pdf_text(pdf_base64: str) -> str:
    """Extract text from a PDF. Requires the optional `pypdf` dependency (pip install agentforge-agents[pdf])."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ValueError("PDF support requires the 'pypdf' package") from exc
    data = base64.b64decode(pdf_base64, validate=True)
    if not data.startswith(b"%PDF"):
        raise ValueError("File is not a PDF")
    reader = PdfReader(io.BytesIO(data))
    if len(reader.pages) > 200:
        raise ValueError("PDF has more than 200 pages")
    return "\n\n".join(f"## Page {i + 1}\n{(p.extract_text() or '').strip()}" for i, p in enumerate(reader.pages))


def permitted(doc: Document, user_groups: list[str]) -> bool:
    return "everyone" in doc.allowed_groups or bool(set(doc.allowed_groups) & set(user_groups))


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def chunk_document(doc: Document, chunk_words: int = 120, overlap_words: int = 20) -> list[Chunk]:
    """Section-aware chunking: split on markdown headings, then pack sentences up to `chunk_words`
    with `overlap_words` carried over. Sentences are never cut in half."""
    if overlap_words >= chunk_words:
        raise ValueError("overlap must be smaller than chunk size")
    chunks: list[Chunk] = []
    section = doc.title
    sentences: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", doc.text):
        block = block.strip()
        if not block:
            continue
        heading = re.match(r"^#{1,6}\s+(.*)", block)
        if heading and "\n" not in block:
            section = heading.group(1).strip()
            continue
        if heading:
            section = heading.group(1).strip()
            block = block.split("\n", 1)[1]
        for s in _SENTENCE.split(" ".join(block.split())):
            sentences.append((section, s))

    current: list[str] = []
    current_section = sentences[0][0] if sentences else doc.title

    def flush() -> None:
        if current:
            chunks.append(Chunk(f"{doc.id}#{len(chunks)}", doc.id, doc.title, current_section, " ".join(current), len(chunks)))

    for sec, sent in sentences:
        words = len(sent.split())
        size = sum(len(s.split()) for s in current)
        if current and (sec != current_section or size + words > chunk_words):
            flush()
            carry: list[str] = []
            if sec == current_section and overlap_words:
                for s in reversed(current):
                    if sum(len(c.split()) for c in carry) + len(s.split()) > overlap_words:
                        break
                    carry.insert(0, s)
            current = carry
            current_section = sec
        current.append(sent)
    flush()
    return chunks


def retrieve(chunks: list[Chunk], query: str, top_k: int = 4) -> list[dict]:
    """Two-stage retrieval: TF-IDF cosine for recall, then a lexical-coverage rerank for precision."""
    index = TfidfIndex({c.id: f"{c.section}. {c.text}" for c in chunks})
    by_id = {c.id: c for c in chunks}
    candidates = index.search(query, top_k=max(top_k * 3, 10))
    q_terms = set(terms(query))
    results = []
    for chunk_id, sim in candidates:
        c = by_id[chunk_id]
        c_terms = set(terms(f"{c.section} {c.text}"))
        coverage = len(q_terms & c_terms) / len(q_terms) if q_terms else 0.0
        score = 0.7 * sim + 0.3 * coverage
        results.append({**c.to_dict(), "similarity": round(sim, 4), "coverage": round(coverage, 4), "score": round(score, 4)})
    results.sort(key=lambda r: (-r["score"], r["id"]))
    return results[:top_k]
