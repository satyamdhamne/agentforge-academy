"""Small, dependency-free text utilities used by several agents."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
STOPWORDS = frozenset(
    ["a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "has", "have", "how", "i", "if", "in", "into", "is", "it", "its", "of", "on", "or", "our", "so", "than", "that", "the", "their", "then", "there", "these", "they", "this", "to", "was", "we", "were", "what", "when", "where", "which", "who", "why", "will", "with", "you", "your", "my", "me", "not", "no", "yes", "should", "would", "could", "must", "may", "might", "shall", "get", "many", "much", "any", "all", "also", "just", "about", "there", "here"]
)


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    words = _WORD.findall(text.lower())
    return [w for w in words if not (drop_stopwords and w in STOPWORDS)]


def stem(word: str) -> str:
    """Tiny suffix stripper: enough to match 'refunds'/'refund' and 'deployed'/'deploy'."""
    for suffix in ("ing", "edly", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def terms(text: str) -> list[str]:
    return [stem(w) for w in tokenize(text)]


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class TfidfIndex:
    """In-memory TF-IDF index. Stands in for an embedding model so retrieval runs offline."""

    def __init__(self, docs: dict[str, str]):
        self.doc_terms = {doc_id: Counter(terms(text)) for doc_id, text in docs.items()}
        n = len(docs) or 1
        df: Counter[str] = Counter()
        for counts in self.doc_terms.values():
            df.update(counts.keys())
        self.idf = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}
        self.vectors = {doc_id: self._weigh(counts) for doc_id, counts in self.doc_terms.items()}

    def _weigh(self, counts: Counter[str]) -> dict[str, float]:
        return {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in counts.items()}

    def embed(self, text: str) -> dict[str, float]:
        return self._weigh(Counter(terms(text)))

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        q = self.embed(query)
        scored = [(doc_id, cosine(q, vec)) for doc_id, vec in self.vectors.items()]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return [s for s in scored[:top_k] if s[1] > 0]


def hashed_embedding(text: str, dims: int = 256) -> list[float]:
    """Deterministic 'feature hashing' embedding. Used where a dense vector is required (pgvector demos)."""
    vec = [0.0] * dims
    for t in terms(text):
        h = int(hashlib.blake2b(t.encode(), digest_size=8).hexdigest(), 16)
        vec[h % dims] += 1.0 if (h >> 63) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


# ---- PII redaction ------------------------------------------------------------------------------

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)")
_CARD = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    """Replace emails, card numbers (Luhn-checked), SSNs and phone numbers with placeholders."""
    counts: Counter[str] = Counter()

    def card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            counts["card"] += 1
            return "[REDACTED_CARD]"
        return m.group(0)

    def sub(pattern: re.Pattern[str], label: str, s: str) -> str:
        def repl(_m: re.Match[str]) -> str:
            counts[label] += 1
            return f"[REDACTED_{label.upper()}]"

        return pattern.sub(repl, s)

    out = sub(_EMAIL, "email", text)
    out = _CARD.sub(card, out)
    out = sub(_SSN, "ssn", out)
    out = sub(_PHONE, "phone", out)
    return out, dict(counts)


def fence_untrusted(label: str, content: str, max_chars: int = 12_000) -> str:
    """Wrap untrusted data in clear delimiters so prompts can tell the model to treat it as data only."""
    body = content[:max_chars]
    if len(content) > max_chars:
        body += f"\n...[truncated {len(content) - max_chars} chars]"
    tag = label.upper().replace(" ", "_")
    body = body.replace(f"</{tag}>", f"<\\/{tag}>")
    return f"<{tag}>\n{body}\n</{tag}>"
