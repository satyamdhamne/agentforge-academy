"""Prompt simulator: a deterministic, rule-based stand-in for a language model.

It does not understand language. It reproduces a handful of well-documented model behaviours so learners can
practise prompt engineering offline and see cause and effect:

* Prompt injection: instructions such as "ignore previous instructions" inside user-supplied content are
  obeyed unless the system prompt tells the model to treat that content as data.
* Output format: asking for JSON without saying "only JSON" yields prose plus a fenced block (a classic parse
  failure); a JSON schema or "only JSON" yields clean JSON.
* Few-shot prompting: label formats shown in examples are copied.
* Classification: picks the listed label with the most keyword overlap.
* Grounding: when numbered passages are supplied and citations are requested, answers extract from the best
  passage and cite it as [n]; with no relevant passage it says it doesn't know.
* Length: "one sentence", "N words", "bullet points" and "concise" are respected.

Everything it returns is labelled provider="mock", model="simulator-1".
"""

from __future__ import annotations

import json
import re
from typing import Any

INJECTION = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|system)\s+"
    r"(instructions?|rules|prompts?|directions)", re.I)
DEFENSE = re.compile(
    r"(untrusted|treat (it|them|this|the [a-z ]{1,30}) as (data|content|text)|as data,? not (as )?instructions|"
    r"(do not|don't|never) (follow|obey|execute|act on) (any )?(instructions|commands)|"
    r"ignore (any )?(instructions|commands) (in|inside|within|contained)|instructions (in|inside|within) the "
    r"[a-z ]{1,30} (are|must be) (ignored|treated as data))", re.I)
STOP = set("""a an the and or but if then else of to in on for with at by from as is are was were be been being this that
these those it its into over under about your you we our they their he she his her them i me my not no yes do does did
can could should would will shall may might must please return answer respond reply give provide using use based one two three four five sentence sentences words summarise summarize summary
which what who whom when where why how all any each every some such only own same so than too very just also""".split())
WORD = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def _words(text: str) -> list[str]:
    return [w.lower().strip("'") for w in WORD.findall(text)]


def _keywords(text: str) -> set[str]:
    out = set()
    for w in _words(text):
        if w in STOP or len(w) < 3:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def _sentences(text: str) -> list[str]:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    lines = [ln.strip(" -*#>\t") for ln in text.splitlines()]
    joined = " ".join(ln for ln in lines if ln)
    return [s.strip() for s in SENT.split(joined) if len(s.strip()) > 2]


def _split_messages(messages: list[Any]) -> tuple[str, str]:
    system = "\n".join(m.content for m in messages if m.role == "system")
    user = "\n".join(m.content for m in messages if m.role in ("user", "tool"))
    return system, user


def _data_segment(user: str) -> str:
    """The part of the user message that looks like supplied data rather than instructions."""
    tagged = re.findall(r"<([a-z_][\w-]*)>(.*?)</\1>", user, flags=re.S | re.I)
    if tagged:
        return "\n".join(body for _, body in tagged)
    fenced = re.findall(r'"""(.*?)"""|```(?:\w+)?\n(.*?)```', user, flags=re.S)
    if fenced:
        return "\n".join(a or b for a, b in fenced)
    m = re.search(r"(?:^|\n)\s*(?:text|input|ticket|email|document|context|content|message|diff|query|transcript)\s*:\s*(.+)",
                  user, flags=re.S | re.I)
    return m.group(1) if m else user


def _question(user: str) -> str:
    m = re.search(r"(?:^|\n)\s*question\s*:\s*(.+)", user, flags=re.I)
    return m.group(1).strip().splitlines()[0] if m else ""


def _rank_sentences(text: str, focus: str) -> list[str]:
    """Most relevant sentences first; earlier sentences win ties (leads are usually the gist)."""
    sents = [s for s in _sentences(text) if not INJECTION.search(s)]
    kw = _keywords(focus)
    scored = []
    for i, s in enumerate(sents):
        overlap = len(kw & _keywords(s)) if kw else 0
        scored.append((overlap - i * 0.25, -i, s))
    scored.sort(reverse=True)
    return [s for _, _, s in scored]


def _length_rules(prompt: str) -> dict[str, Any]:
    p = prompt.lower()
    rules: dict[str, Any] = {}
    m = re.search(r"(?:under|at most|no more than|max(?:imum)?(?: of)?|within|in)\s+(\d{1,3})\s+words", p)
    if m:
        rules["max_words"] = int(m.group(1))
    if re.search(r"\b(one|1|a single) sentence\b", p):
        rules["sentences"] = 1
    elif re.search(r"\b(two|2) sentences\b", p):
        rules["sentences"] = 2
    elif re.search(r"\b(concise|brief|short|succinct)\b", p):
        rules["sentences"] = 2
    if re.search(r"bullet|bulleted|as a list|- item", p):
        rules["bullets"] = True
    return rules


def _apply_length(sents: list[str], rules: dict[str, Any], default: int = 3) -> str:
    n = rules.get("sentences", default)
    chosen = sents[: max(1, n)] or ["I don't have enough information to answer."]
    text = "\n".join(f"- {s}" for s in chosen) if rules.get("bullets") else " ".join(chosen)
    if "max_words" in rules:
        words = text.split()
        if len(words) > rules["max_words"]:
            text = " ".join(words[: rules["max_words"]]).rstrip(",;:.") + "."
    return text


# ---------------------------------------------------------------- classification & few-shot

LABEL_LIST = re.compile(
    r"(?:one of|categories|category|labels?|classes|choose from|options|classify (?:it |this |the [a-z]+ )?(?:as|into))"
    r"\s*[:\-]?\s*\[?([A-Za-z0-9_\- ,/|\"']{3,200})\]?", re.I)


def _labels(prompt: str) -> list[str]:
    m = LABEL_LIST.search(prompt)
    if not m:
        return []
    raw = re.split(r"\s*(?:,|\||/|\bor\b)\s*", m.group(1).strip().rstrip("."))
    labels = [r.strip(" \"'.") for r in raw if r.strip(" \"'.")]
    labels = [lbl.split()[0] if len(lbl.split()) > 3 else lbl for lbl in labels]
    return [lbl for lbl in labels if 1 < len(lbl) <= 40][:12] if len(labels) >= 2 else []


def _few_shot(prompt: str) -> tuple[list[tuple[str, str]], str | None]:
    pairs = re.findall(r"(?:input|text|ticket|q)\s*:\s*(.+?)\n\s*(?:output|label|category|a)\s*:\s*(.+?)(?=\n|$)", prompt, flags=re.I)
    tail = re.findall(r"(?:input|text|ticket|q)\s*:\s*(.+?)\s*(?:\n\s*(?:output|label|category|a)\s*:\s*)?$", prompt.strip(), flags=re.I | re.S)
    return [(a.strip(), b.strip()) for a, b in pairs], (tail[-1].strip() if tail else None)


def _classify(text: str, labels: list[str]) -> str:
    kw = _keywords(text)
    hints = {
        "billing": {"invoice", "charge", "charged", "refund", "payment", "card", "price", "bill", "subscription", "plan"},
        "bug": {"error", "crash", "broken", "exception", "fails", "failing", "bug", "500", "stack"},
        "technical": {"error", "crash", "api", "timeout", "bug", "broken"},
        "account": {"password", "login", "sign", "email", "account", "locked", "2fa"},
        "feature": {"feature", "request", "would", "add", "support", "wish", "suggestion"},
        "feature_request": {"feature", "request", "would", "add", "support", "wish", "suggestion"},
        "positive": {"great", "love", "thanks", "excellent", "happy", "awesome", "good"},
        "negative": {"bad", "terrible", "angry", "worst", "disappointed", "broken", "hate", "frustrated"},
        "neutral": set(),
        "urgent": {"outage", "down", "urgent", "asap", "immediately", "production", "critical"},
        "high": {"outage", "down", "urgent", "asap", "immediately", "production", "critical", "all"},
        "low": {"question", "wondering", "minor", "cosmetic", "typo"},
        "spam": {"winner", "prize", "click", "free", "offer", "crypto"},
        "security": {"phishing", "breach", "password", "leak", "vulnerability", "suspicious"},
    }
    best, best_score = labels[0], -1.0
    for i, label in enumerate(labels):
        lk = _keywords(label.replace("_", " ")) | hints.get(label.lower(), set())
        score = len(kw & lk) - i * 0.01
        if score > best_score:
            best, best_score = label, score
    if best_score <= 0:  # no evidence for any label: prefer a neutral default over the first option
        for fallback in ("normal", "neutral", "medium", "other", "none", "general"):
            match = next((lbl for lbl in labels if lbl.lower() == fallback), None)
            if match:
                return match
    return best


# ---------------------------------------------------------------- JSON schema filling

NUM = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4})\b")


def _number_near(text: str, names: list[str]) -> float | None:
    for name in names:
        m = re.search(rf"{name}[^\d\n]{{0,25}}(-?\$?\d[\d,]*(?:\.\d+)?)", text, flags=re.I)
        if m:
            return float(m.group(1).replace("$", "").replace(",", ""))
    return None


def _fill(schema: dict[str, Any], name: str, text: str, prompt: str) -> Any:
    t = schema.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "string")
    if "enum" in schema:
        return _classify(text, [str(e) for e in schema["enum"]])
    if t == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {k: _fill(v, k, text, prompt) for k, v in props.items()}
    if t == "array":
        items = schema.get("items", {"type": "string"})
        if items.get("type") == "object":
            return []
        sents = _rank_sentences(text, prompt + " " + name)
        if items.get("type") in ("number", "integer"):
            return [float(n.replace("$", "").replace(",", "")) for n in NUM.findall(text)[:3]]
        return [s[:120] for s in sents[: min(3, schema.get("maxItems", 3))]]
    if t in ("number", "integer"):
        n = _number_near(text, [name.replace("_", " "), name, "total", "amount", "price", "count"])
        if n is None:
            nums = NUM.findall(text)
            n = float(nums[0].replace("$", "").replace(",", "")) if nums else 0
        return int(n) if t == "integer" else n
    if t == "boolean":
        return bool(_keywords(name) & _keywords(text))
    lname = name.lower()
    if "email" in lname:
        m = EMAIL.search(text)
        return m.group(0) if m else ""
    if "date" in lname or lname.endswith("_at") or lname == "due":
        m = DATE.search(text)
        return m.group(0) if m else ""
    if lname in ("currency",):
        m = re.search(r"\b(USD|EUR|GBP|INR|JPY)\b|\$", text)
        return (m.group(1) or "USD") if m else ""
    if any(k in lname for k in ("vendor", "company", "customer", "name", "title", "author", "owner")):
        m = re.search(rf"{name.replace('_', '[ _]')}\s*[:\-]\s*([^\n,;]+)", text, flags=re.I)
        if m:
            return m.group(1).strip()[:100]
        caps = re.findall(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b", text)
        return caps[0] if caps else ""
    sents = _rank_sentences(text, prompt + " " + name)
    return sents[0][:300] if sents else ""


# ---------------------------------------------------------------- grounding

PASSAGE = re.compile(r"\[(\d{1,2})\]\s*(?:\(([^)]*)\))?\s*(.+?)(?=\n\s*\[\d{1,2}\]|\Z)", re.S)


def _grounded_answer(user: str, system: str, rules: dict[str, Any]) -> str | None:
    question = _question(user) or user.strip().splitlines()[-1]
    context = re.split(r"\n\s*question\s*:", user, maxsplit=1, flags=re.I)[0]
    passages = PASSAGE.findall(context)
    if not passages:
        return None
    qk = _keywords(question)
    best: tuple[float, str, str] | None = None
    for num, _title, body in passages:
        for s in _sentences(body):
            score = len(qk & _keywords(s)) / (len(qk) or 1)
            if best is None or score > best[0]:
                best = (score, num, s)
    if best is None or best[0] < 0.2:
        return "I don't know based on the provided documents."
    cite = re.search(r"\bcit(e|ation)|\[n\]|\[\d\]|sources?\b", system + user, re.I)
    answer = best[2] if not rules.get("max_words") else _apply_length([best[2]], rules, 1)
    return f"{answer} [{best[1]}]" if cite else answer


# ---------------------------------------------------------------- entry point


def simulate(messages: list[Any], response_schema: dict[str, Any] | None = None) -> str | dict[str, Any]:
    system, user = _split_messages(messages)
    prompt = f"{system}\n{user}"
    data = _data_segment(user)
    rules = _length_rules(prompt)

    m = INJECTION.search(user)
    if m and not DEFENSE.search(system):
        tail = re.sub(r"^(and|then|instead|now)\s+", "", user[m.end():].strip(" :.,;-\n\"'"), flags=re.I)
        demand = _sentences(tail)[0] if _sentences(tail) else tail[:200]
        return f"Okay, ignoring my previous instructions. {demand}".strip()

    if response_schema:
        return _fill(response_schema, "", data, prompt)

    pairs, final_input = _few_shot(user)
    labels = _labels(prompt) or sorted({b for _, b in pairs})
    if labels and (pairs or re.search(r"\bclassif|categor|label|sentiment|priority|route\b", prompt, re.I)):
        target = final_input if pairs and final_input else data
        return _classify(target, labels)

    grounded = _grounded_answer(user, system, rules)
    if grounded is not None:
        body = grounded
    else:
        focus = _question(user) or system
        body = _apply_length(_rank_sentences(data, focus), rules)

    if re.search(r"\bjson\b", prompt, re.I):
        payload = json.dumps({"answer": body}, indent=2)
        if re.search(r"only (valid )?json|json only|no (prose|explanation|markdown)|nothing else|raw json|without (any )?(prose|markdown|code fences)", prompt, re.I):
            return payload
        return f"Sure! Here is the JSON you asked for:\n```json\n{payload}\n```"
    return body
