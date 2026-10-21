"""Embedders. All produce 384-dimensional, L2-normalised vectors so they share one pgvector column.

* hashing-384: feature hashing of word unigrams and bigrams. Lexical, deterministic, CPU-only, no download.
* minilm-384: sentence-transformers/all-MiniLM-L6-v2 (semantic) - only if the package and model are available.
* openai-small-384: text-embedding-3-small with dimensions=384 - only when an OpenAI-compatible provider is
  configured server-side and the learner is on a paid plan.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

import httpx

from ...core.config import get_settings

DIM = 384
TOKEN = re.compile(r"[a-z0-9]+")
STOP = set("a an the and or of to in on for with at by from as is are was were be it this that these those".split())


def tokens(text: str) -> list[str]:
    out = []
    for t in TOKEN.findall(text.lower()):
        if t in STOP:
            continue
        if len(t) > 4 and t.endswith("ies"):
            t = t[:-3] + "y"
        elif len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


def _bucket(feature: str) -> tuple[int, float]:
    h = hashlib.blake2b(feature.encode(), digest_size=8).digest()
    return int.from_bytes(h[:4], "little") % DIM, (1.0 if h[4] & 1 else -1.0)


def hashing_embed(text: str) -> list[float]:
    toks = tokens(text)
    counts: dict[str, int] = {}
    for f in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]:
        counts[f] = counts.get(f, 0) + 1
    vec = [0.0] * DIM
    for f, c in counts.items():
        i, sign = _bucket(f)
        vec[i] += sign * (1 + math.log(c)) * (0.6 if "_" in f else 1.0)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@lru_cache(maxsize=1)
def _minilm():
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    except Exception:  # noqa: BLE001 - optional dependency
        return None


def available(live: bool) -> list[dict]:
    s = get_settings()
    out = [{"key": "hashing-384", "label": "Hashing (lexical, CPU)", "available": True,
            "note": "Deterministic feature hashing. Matches shared words, not meaning: good for learning, weak on synonyms."}]
    out.append({"key": "minilm-384", "label": "MiniLM-L6 (semantic, CPU)", "available": _minilm() is not None,
                "note": "pip install sentence-transformers to enable (downloads ~90 MB once)."})
    out.append({"key": "openai-small-384", "label": "OpenAI text-embedding-3-small (384-d)",
                "available": live and s.llm_provider == "openai" and bool(s.openai_api_key),
                "note": "Needs LLM_PROVIDER=openai on the server and a paid plan."})
    return out


def embed(texts: list[str], embedder: str = "hashing-384") -> list[list[float]]:
    if embedder == "minilm-384" and _minilm() is not None:
        return [list(map(float, v)) for v in _minilm().encode(texts, normalize_embeddings=True)]
    if embedder == "openai-small-384":
        s = get_settings()
        r = httpx.post(f"{s.openai_base_url.rstrip('/')}/embeddings", timeout=30,
                       headers={"Authorization": f"Bearer {s.openai_api_key}"},
                       json={"model": "text-embedding-3-small", "input": texts, "dimensions": DIM})
        r.raise_for_status()
        return [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
    return [hashing_embed(t) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
