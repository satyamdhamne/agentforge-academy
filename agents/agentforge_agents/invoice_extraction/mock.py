"""Offline extractor: returns the regex candidates as the extraction (a common production baseline)."""

from __future__ import annotations

from ..core import CompletionRequest


def extract(request: CompletionRequest) -> dict:
    return dict(request.context["candidates"])


RESPONDERS = {"invoice_extraction.extract": extract}
