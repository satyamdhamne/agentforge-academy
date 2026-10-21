"""Index building and retrieval.

Permissions are applied *inside* retrieval: callers pass the document ids the user may read, and both the
pgvector query and the Python fallback filter on them before ranking. Text the user may not see never reaches
the reranker or the model.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from ...models import RagChunk, RagDataset, RagDocument, RagIndex
from .chunking import STRATEGIES, chunk
from .embeddings import cosine, embed, tokens

DEFAULT_CONFIG = {"chunker": "markdown", "size": 120, "overlap": 20, "embedder": "hashing-384"}
_PGVECTOR: dict[str, bool] = {}
_CACHE: dict[uuid.UUID, tuple[str, list[dict[str, Any]]]] = {}


def normalize_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    c = {**DEFAULT_CONFIG, **{k: v for k, v in (cfg or {}).items() if k in DEFAULT_CONFIG and v not in (None, "")}}
    c["chunker"] = c["chunker"] if c["chunker"] in STRATEGIES else "recursive"
    c["size"] = max(20, min(int(c["size"]), 1000))
    c["overlap"] = max(0, min(int(c["overlap"]), c["size"] // 2))
    return c


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def pgvector_enabled(db: Session) -> bool:
    url = str(db.get_bind().url)
    if url not in _PGVECTOR:
        _PGVECTOR[url] = bool(db.execute(text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'rag_chunks' AND column_name = 'embedding_vec'")).scalar())
    return _PGVECTOR[url]


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def get_index(db: Session, dataset: RagDataset, cfg: dict[str, Any]) -> RagIndex:
    """Return an up-to-date index for this dataset and configuration, (re)building it if documents changed."""
    config = normalize_config(cfg)
    docs = db.scalars(select(RagDocument).where(RagDocument.dataset_id == dataset.id).order_by(RagDocument.created_at)).all()
    corpus = _hash(sorted((str(d.id), d.content_hash) for d in docs))
    chash = _hash(config)
    idx = db.scalar(select(RagIndex).where(RagIndex.dataset_id == dataset.id, RagIndex.config_hash == chash))
    if idx is not None and idx.corpus_hash == corpus:
        return idx
    started = time.perf_counter()
    if idx is None:
        idx = RagIndex(dataset_id=dataset.id, config=config, config_hash=chash, corpus_hash=corpus)
        db.add(idx)
        db.flush()
    else:
        db.execute(delete(RagChunk).where(RagChunk.index_id == idx.id))
        idx.corpus_hash = corpus
    rows: list[RagChunk] = []
    for d in docs:
        pieces = chunk(d.text, config["chunker"], config["size"], config["overlap"])
        vectors = embed([f"{p.heading}\n{p.text}" if p.heading else p.text for p in pieces], config["embedder"]) if pieces else []
        for i, (p, v) in enumerate(zip(pieces, vectors)):
            rows.append(RagChunk(index_id=idx.id, document_id=d.id, ordinal=i, text=p.text, start_char=p.start, end_char=p.end,
                                 token_count=round(p.words * 1.3), heading=p.heading[:300], embedding=v))
    db.add_all(rows)
    db.flush()
    use_pg = pgvector_enabled(db)
    if use_pg and rows:
        db.execute(text("UPDATE rag_chunks SET embedding_vec = CAST(:v AS vector) WHERE id = :id"),
                   [{"v": _vec_literal(r.embedding), "id": r.id} for r in rows])
    idx.chunk_count = len(rows)
    idx.backend = "pgvector" if use_pg else "python"
    idx.build_ms = int((time.perf_counter() - started) * 1000)
    db.flush()
    _CACHE.pop(idx.id, None)
    return idx


def _chunks(db: Session, idx: RagIndex) -> list[dict[str, Any]]:
    cached = _CACHE.get(idx.id)
    if cached and cached[0] == idx.corpus_hash:
        return cached[1]
    rows = db.execute(select(RagChunk.id, RagChunk.document_id, RagChunk.ordinal, RagChunk.text, RagChunk.heading,
                             RagChunk.embedding, RagChunk.token_count).where(RagChunk.index_id == idx.id)).all()
    data = [{"id": r.id, "document_id": r.document_id, "ordinal": r.ordinal, "text": r.text, "heading": r.heading,
             "embedding": list(r.embedding), "tokens": tokens(f"{r.heading} {r.text}"), "token_count": r.token_count} for r in rows]
    if len(_CACHE) > 32:
        _CACHE.clear()
    _CACHE[idx.id] = (idx.corpus_hash, data)
    return data


@dataclass
class Hit:
    chunk: dict[str, Any]
    vector: float | None = None
    keyword: float | None = None
    fused: float | None = None
    rerank: float | None = None
    ranks: dict[str, int] = field(default_factory=dict)

    @property
    def score(self) -> float:
        for v in (self.rerank, self.fused, self.vector, self.keyword):
            if v is not None:
                return v
        return 0.0


def vector_search(db: Session, idx: RagIndex, qvec: list[float], allowed: set[uuid.UUID], k: int) -> list[Hit]:
    if not allowed:
        return []
    by_id = {c["id"]: c for c in _chunks(db, idx)}
    if idx.backend == "pgvector" and pgvector_enabled(db):
        rows = db.execute(text(
            "SELECT id, 1 - (embedding_vec <=> CAST(:q AS vector)) AS score FROM rag_chunks "
            "WHERE index_id = :idx AND document_id = ANY(:docs) ORDER BY embedding_vec <=> CAST(:q AS vector) LIMIT :k"),
            {"q": _vec_literal(qvec), "idx": idx.id, "docs": list(allowed), "k": k}).all()
        return [Hit(by_id[r.id], vector=round(float(r.score), 4)) for r in rows if r.id in by_id]
    scored = [(cosine(qvec, c["embedding"]), c) for c in by_id.values() if c["document_id"] in allowed]
    scored.sort(key=lambda x: -x[0])
    return [Hit(c, vector=round(s, 4)) for s, c in scored[:k]]


def keyword_search(db: Session, idx: RagIndex, query: str, allowed: set[uuid.UUID], k: int, k1: float = 1.2, b: float = 0.75) -> list[Hit]:
    """BM25 over the chunks the user may read."""
    docs = [c for c in _chunks(db, idx) if c["document_id"] in allowed]
    if not docs:
        return []
    q = set(tokens(query))
    n = len(docs)
    avg = sum(len(c["tokens"]) for c in docs) / n or 1
    df = Counter(t for c in docs for t in set(c["tokens"]) if t in q)
    scored = []
    for c in docs:
        tf = Counter(t for t in c["tokens"] if t in q)
        s = 0.0
        for t, f in tf.items():
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(c["tokens"]) / avg))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [Hit(c, keyword=round(s, 4)) for s, c in scored[:k]]


def rrf(lists: dict[str, list[Hit]], k: int = 60) -> list[Hit]:
    merged: dict[uuid.UUID, Hit] = {}
    for name, hits in lists.items():
        for rank, h in enumerate(hits, start=1):
            m = merged.setdefault(h.chunk["id"], Hit(h.chunk))
            if h.vector is not None:
                m.vector = h.vector
            if h.keyword is not None:
                m.keyword = h.keyword
            m.ranks[name] = rank
            m.fused = round((m.fused or 0) + 1 / (k + rank), 5)
    return sorted(merged.values(), key=lambda h: -(h.fused or 0))


def rerank(query: str, hits: list[Hit]) -> list[Hit]:
    """Lexical reranker: rewards covering more distinct query terms and keeping them close together."""
    q = [t for t in tokens(query)]
    qs = set(q)
    for h in hits:
        toks = h.chunk["tokens"]
        coverage = len(qs & set(toks)) / (len(qs) or 1)
        positions = [i for i, t in enumerate(toks) if t in qs]
        span = (positions[-1] - positions[0] + 1) if len(positions) > 1 else len(toks) or 1
        proximity = min(1.0, len(set(toks[i] for i in positions)) / span * 3) if positions else 0.0
        h.rerank = round(0.75 * coverage + 0.25 * proximity, 4)
    return sorted(hits, key=lambda h: (-(h.rerank or 0), -(h.fused or h.vector or h.keyword or 0)))


def retrieve(db: Session, idx: RagIndex, query: str, allowed: set[uuid.UUID], strategy: str, top_k: int,
             use_rerank: bool, min_score: float = 0.2) -> tuple[list[Hit], dict[str, int]]:
    timings: dict[str, int] = {}
    pool = top_k * 4 if (use_rerank or strategy == "hybrid") else top_k
    t = time.perf_counter()
    qvec = embed([query], idx.config["embedder"])[0] if strategy in ("vector", "hybrid") else []
    timings["embed_query_ms"] = int((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    if strategy == "keyword":
        hits = keyword_search(db, idx, query, allowed, pool)
    elif strategy == "vector":
        hits = vector_search(db, idx, qvec, allowed, pool)
    else:
        hits = rrf({"vector": vector_search(db, idx, qvec, allowed, pool), "keyword": keyword_search(db, idx, query, allowed, pool)})
    timings["search_ms"] = int((time.perf_counter() - t) * 1000)
    if use_rerank:
        t = time.perf_counter()
        hits = [h for h in rerank(query, hits) if (h.rerank or 0) >= min_score]  # relevance threshold
        timings["rerank_ms"] = int((time.perf_counter() - t) * 1000)
    return hits[:top_k], timings


def allowed_documents(db: Session, dataset: RagDataset, groups: list[str]) -> dict[uuid.UUID, RagDocument]:
    docs = db.scalars(select(RagDocument).where(RagDocument.dataset_id == dataset.id)).all()
    gs = set(groups)
    return {d.id: d for d in docs if "everyone" in (d.allowed_groups or []) or gs & set(d.allowed_groups or [])}


def clean_text(raw: str) -> str:
    """Normalise whitespace and strip control characters; keeps Markdown structure."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw)
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()
