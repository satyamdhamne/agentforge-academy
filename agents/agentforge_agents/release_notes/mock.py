"""Offline rewriter: light, rule-based plain-language rewrite of commit descriptions."""

from __future__ import annotations

import re

from ..core import CompletionRequest

JARGON = [(r"\bendpoint\b", "API"), (r"\bUI\b", "interface"), (r"\bperf\b", "performance"), (r"\bauth\b", "sign-in"),
          (r"\bdeps?\b", "dependencies"), (r"\bconfig\b", "settings"), (r"\bN\+1\b", "redundant database"),
          (r"\bpagination\b", "paging")]
PREFIX = {"feat": "", "fix": "Fixed: ", "perf": "Faster: ", "security": "Security: ", "breaking": "Action required: "}


def rewrite(request: CompletionRequest) -> dict:
    items = []
    for c in request.context["items"]:
        text = c["description"]
        for pattern, repl in JARGON:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        text = re.sub(r"`([^`]+)`", r"\1", text).strip().rstrip(".")
        text = PREFIX.get(c["section"], "") + text[0].upper() + text[1:] + "."
        items.append({"id": c["id"], "text": text})
    feats = [i["text"] for i, c in zip(items, request.context["items"]) if c["section"] in ("feat", "breaking")]
    return {"highlights": feats[:3], "items": items}


RESPONDERS = {"release_notes.rewrite": rewrite}
