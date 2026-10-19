"""Offline classifier: weighted keyword scoring. A realistic baseline to beat with a model."""

from __future__ import annotations

import re

from ..core import CompletionRequest

KEYWORDS = {
    "billing": ["invoice", "charged", "charge", "refund", "payment", "billing", "card", "receipt", "price", "subscription fee", "overcharged", "double charged"],
    "bug": ["error", "bug", "crash", "broken", "doesn't work", "not working", "fails", "exception", "500", "glitch", "wrong result"],
    "account_access": ["password", "login", "log in", "sign in", "2fa", "locked out", "reset", "verification code", "mfa", "can't access my account"],
    "feature_request": ["feature request", "would be great", "please add", "it would be nice", "suggestion", "wish", "could you add", "support for"],
    "how_to": ["how do i", "how to", "where can i", "is it possible", "documentation", "tutorial", "how can i"],
    "outage": ["down", "outage", "unavailable", "not loading", "timeout", "all users", "status page", "production is"],
    "security": ["hacked", "breach", "phishing", "suspicious", "compromised", "unauthorized", "leak", "stolen"],
    "cancellation": ["cancel", "close my account", "unsubscribe", "downgrade", "terminate", "switching to"],
}
NEGATIVE = ["angry", "frustrated", "terrible", "unacceptable", "worst", "disappointed", "ridiculous", "again", "still", "!!"]
POSITIVE = ["thanks", "thank you", "love", "great", "appreciate", "awesome"]
BASE_PRIORITY = {"outage": "P1", "security": "P1", "bug": "P2", "account_access": "P2", "billing": "P2",
                 "cancellation": "P3", "how_to": "P4", "feature_request": "P4", "other": "P4"}


def classify(request: CompletionRequest) -> dict:
    text = request.context["text"].lower()
    tier = request.context.get("tier", "free")
    scores = {cat: sum(text.count(k) for k in kws) for cat, kws in KEYWORDS.items()}
    total = sum(scores.values())
    category = max(scores, key=lambda k: (scores[k], -list(KEYWORDS).index(k))) if total else "other"
    confidence = 0.4 if not total else min(0.95, 0.45 + 0.5 * scores[category] / total)
    priority = BASE_PRIORITY[category]
    urgent = re.search(r"\b(urgent|asap|immediately|critical|blocked)\b", text)
    if urgent and priority in ("P3", "P4") and category not in ("feature_request", "how_to"):
        priority = "P2"
    if tier == "enterprise" and priority == "P2" and urgent:
        priority = "P1"
    neg = sum(text.count(w) for w in NEGATIVE)
    pos = sum(text.count(w) for w in POSITIVE)
    sentiment = "negative" if neg > pos else "positive" if pos > neg else "neutral"
    reasons = [f"matched {scores[category]} {category} keyword(s)"] if total else ["no category keywords matched"]
    if urgent:
        reasons.append("urgency language present")
    subject = text.split("\n", 1)[0].removeprefix("subject:").strip()
    return {"category": category, "priority": priority, "sentiment": sentiment, "confidence": round(confidence, 2),
            "summary": f"Customer ({tier}) reports a {category.replace('_', ' ')} issue: {subject[:100]}", "reasons": reasons}


RESPONDERS = {"support_triage.classify": classify}
