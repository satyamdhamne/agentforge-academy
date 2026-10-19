"""Regex candidate extraction and arithmetic/consistency validation for invoices."""

from __future__ import annotations

import re
from datetime import date, datetime

_NUM = r"-?\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})|-?\d+(?:\.\d{2})"
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY"}
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y"]
_DATE_TOKEN = r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4}|\d{1,2}[ -][A-Za-z]{3,9}[ -]\d{4}|[A-Za-z]{3,9} \d{1,2}, \d{4})"


def to_number(s: str | None) -> float | None:
    if s is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", s.replace(",", ""))
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def parse_date(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _labelled_amount(text: str, labels: str) -> str | None:
    m = re.search(rf"(?im)^\s*(?:{labels})\b[^\n]*?[$€£₹]?\s*({_NUM})\s*$", text)
    return m.group(1) if m else None


def extract_candidates(text: str) -> dict:
    inv = re.search(r"(?i)invoice\s*(?:no\.?|number|#)\s*[:#]?\s*([A-Z0-9][A-Z0-9-/]{2,})", text)
    inv_date = re.search(rf"(?i)(?:invoice date|date of issue|issued|date)\s*[:\-]?\s*{_DATE_TOKEN}", text)
    due = re.search(rf"(?i)(?:due date|payment due|due)\s*[:\-]?\s*{_DATE_TOKEN}", text)
    currency = None
    code = re.search(r"\b(USD|EUR|GBP|INR|JPY|CAD|AUD)\b", text)
    if code:
        currency = code.group(1)
    else:
        for sym, cur in CURRENCY_SYMBOLS.items():
            if sym in text:
                currency = cur
                break
    lines = [l for l in text.splitlines() if l.strip()]
    vendor = lines[0].strip() if lines else None
    items = []
    for line in lines:
        m = re.match(rf"^\s*(?P<desc>[A-Za-z].*?)\s{{2,}}(?P<qty>\d+(?:\.\d+)?)\s+[$€£₹]?\s*(?P<unit>{_NUM})\s+[$€£₹]?\s*(?P<amount>{_NUM})\s*$", line)
        if m and not re.match(r"(?i)\s*(sub ?total|total|tax|vat|gst|amount due|balance)", m.group("desc")):
            items.append({"description": m.group("desc").strip(), "quantity": float(m.group("qty")),
                          "unit_price": to_number(m.group("unit")), "amount": to_number(m.group("amount"))})
    return {
        "vendor": vendor,
        "invoice_number": inv.group(1) if inv else None,
        "invoice_date": inv_date.group(1) if inv_date else None,
        "due_date": due.group(1) if due else None,
        "currency": currency,
        "subtotal": to_number(_labelled_amount(text, r"sub ?total")),
        "tax": to_number(_labelled_amount(text, r"tax|vat|gst|sales tax")),
        "total": to_number(_labelled_amount(text, r"total(?! *tax)|amount due|balance due|grand total")),
        "line_items": items,
    }


def _appears(value: float | None, text: str) -> bool:
    if value is None:
        return True
    digits = re.sub(r"\D", "", text)
    return f"{value:.2f}".replace(".", "") in digits or f"{int(value)}" in digits


def validate_invoice(inv: dict, source_text: str) -> list[dict]:
    """Return a list of issues. Arithmetic checks catch extraction errors; grounding checks catch hallucinations."""
    issues: list[dict] = []
    tol = 0.02

    def add(code: str, severity: str, message: str) -> None:
        issues.append({"code": code, "severity": severity, "message": message})

    for field in ("vendor", "invoice_number", "invoice_date", "total", "currency"):
        if inv.get(field) in (None, ""):
            add(f"missing_{field}", "error", f"{field.replace('_', ' ')} not found")
    if inv.get("invoice_number") and inv["invoice_number"] not in source_text:
        add("ungrounded_invoice_number", "error", "Invoice number does not appear in the document")
    for field in ("subtotal", "tax", "total"):
        if not _appears(inv.get(field), source_text):
            add(f"ungrounded_{field}", "error", f"{field} value does not appear in the document")
    items = inv.get("line_items") or []
    for i, it in enumerate(items):
        if None not in (it.get("quantity"), it.get("unit_price"), it.get("amount")):
            if abs(it["quantity"] * it["unit_price"] - it["amount"]) > tol:
                add("line_math", "error", f"Line {i + 1}: quantity × unit price ≠ amount")
    sub, tax, total = inv.get("subtotal"), inv.get("tax"), inv.get("total")
    if items and sub is not None and all(it.get("amount") is not None for it in items):
        if abs(sum(it["amount"] for it in items) - sub) > tol * max(1, len(items)):
            add("subtotal_mismatch", "error", "Line items do not sum to the subtotal")
    if sub is not None and total is not None and abs(sub + (tax or 0) - total) > tol:
        add("total_mismatch", "error", "Subtotal + tax ≠ total")
    d1, d2 = parse_date(inv.get("invoice_date")), parse_date(inv.get("due_date"))
    if inv.get("invoice_date") and not d1:
        add("bad_invoice_date", "warning", "Invoice date could not be parsed")
    if d1 and d2 and d2 < d1:
        add("due_before_issue", "error", "Due date is before the invoice date")
    if inv.get("currency") and not re.fullmatch(r"[A-Z]{3}", inv["currency"]):
        add("bad_currency", "warning", "Currency is not an ISO 4217 code")
    if not items:
        add("no_line_items", "warning", "No line items extracted")
    return issues
