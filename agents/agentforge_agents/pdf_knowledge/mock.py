"""Offline responder: extractive answering. Picks the retrieved sentences that best cover the question.

Extractive answers are always grounded (they are copied from passages), which makes this mock a
useful baseline when evaluating whether a generative model adds value.
"""

from __future__ import annotations

import re

from ..core import CompletionRequest
from ..core.text import terms

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def answer(request: CompletionRequest) -> dict:
    q_terms = set(terms(request.context["question"]))
    scored = []
    for i, hit in enumerate(request.context["hits"]):
        for s in _SENTENCE.split(hit["text"]):
            overlap = len(q_terms & set(terms(s)))
            if overlap:
                scored.append((overlap + hit["score"], i + 1, s.strip()))
    if not scored:
        return {"answer": "The retrieved passages do not answer this question.", "citations": [], "answerable": False,
                "confidence": "low"}
    scored.sort(key=lambda x: -x[0])
    best = scored[0][0]
    chosen, used = [], set()
    for score, n, sentence in scored:
        if sentence in used or score < best * 0.6 or len(chosen) == 3:
            continue
        used.add(sentence)
        chosen.append((n, sentence))
    text = " ".join(f"{s.rstrip('.')}. [{n}]" for n, s in chosen)
    coverage = len(q_terms & set(terms(" ".join(s for _, s in chosen)))) / max(len(q_terms), 1)
    if coverage < 0.34:  # the best sentences share too few question terms to count as an answer
        return {"answer": "The retrieved passages do not clearly answer this question.", "citations": [],
                "answerable": False, "confidence": "low"}
    return {"answer": text, "citations": sorted({n for n, _ in chosen}), "answerable": True,
            "confidence": "high" if coverage >= 0.75 else "medium" if coverage >= 0.4 else "low"}


RESPONDERS = {"pdf_knowledge.answer": answer}
