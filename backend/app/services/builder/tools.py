"""Allowlisted tools for Agent Builder tool nodes.

Read-only tools run directly. Side-effect tools (send_email, create_ticket) are *simulated*: they never contact
external systems, and the validator only accepts graphs where a human approval node precedes them on every path.
There is deliberately no generic HTTP or shell tool.
"""

from __future__ import annotations

import ast
import json
import operator
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..assertions import lenient_json


class ToolFailure(Exception):
    pass


@dataclass
class ToolDef:
    name: str
    description: str
    args: dict[str, str]  # arg name -> description
    side_effect: bool
    fn: Callable[..., Any]


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos, ast.FloorDiv: operator.floordiv}


def calculator(expression: str) -> dict:
    """Safe arithmetic: numbers, + - * / // % ** and parentheses only (parsed, never eval'd)."""
    if len(expression) > 200:
        raise ToolFailure("Expression too long")

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ToolFailure("Exponent too large")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ToolFailure("Only numbers and + - * / // % ** ( ) are allowed")

    try:
        value = ev(ast.parse(expression.replace("^", "**").replace(",", ""), mode="eval"))
    except (SyntaxError, ZeroDivisionError) as exc:
        raise ToolFailure(f"Can't evaluate: {exc}") from exc
    return {"expression": expression, "value": round(value, 10) if isinstance(value, float) else value}


DEMO_SQL = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, plan TEXT, country TEXT);
CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, status TEXT, total REAL, created_on TEXT);
INSERT INTO customers VALUES (1,'Ada Labs','business','UK'),(2,'Grace Systems','starter','US'),(3,'Linus Data','enterprise','FI'),
  (4,'Margaret AI','business','US'),(5,'Ken Robotics','starter','JP');
INSERT INTO orders (customer_id,status,total,created_on) VALUES (1,'paid',199,'2026-09-01'),(1,'paid',199,'2026-10-01'),
  (2,'paid',29,'2026-10-02'),(3,'paid',4800,'2026-09-15'),(4,'refunded',199,'2026-10-03'),(4,'paid',199,'2026-10-04'),
  (5,'pending',29,'2026-10-05');
"""


def sql_query(sql: str) -> dict:
    """Read-only SELECT against a small demo database (customers, orders). Writes are rejected by the SQLite authorizer."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(DEMO_SQL)
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    conn.set_authorizer(lambda action, *args: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    steps = {"n": 0}

    def guard() -> int:
        steps["n"] += 1
        return 1 if steps["n"] > 2000 else 0  # abort runaway queries

    conn.set_progress_handler(guard, 1000)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(50)
    except sqlite3.Error as exc:
        raise ToolFailure(f"SQL error: {exc}") from exc
    finally:
        conn.close()
    return {"columns": cols, "rows": [list(r) for r in rows], "row_count": len(rows)}


def json_extract(text: str, path: str = "") -> dict:
    data = lenient_json(text)
    if data is None:
        raise ToolFailure("No JSON found in the text")
    cur = data
    for part in [p for p in path.split(".") if p]:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise ToolFailure(f"Path '{path}' not found")
    return {"value": cur}


def word_count(text: str) -> dict:
    return {"words": len(text.split()), "characters": len(text)}


def current_time() -> dict:
    return {"utc": datetime.now(UTC).isoformat(timespec="seconds")}


def send_email(to: str, subject: str, body: str) -> dict:
    if "@" not in to:
        raise ToolFailure("'to' must be an email address")
    return {"status": "simulated", "to": to, "subject": subject[:200], "body_preview": body[:300],
            "note": "Simulated: the Agent Builder never sends real email."}


def create_ticket(title: str, priority: str = "normal", body: str = "") -> dict:
    return {"status": "simulated", "ticket_id": f"SIM-{abs(hash(title)) % 10000:04d}", "title": title[:200], "priority": priority,
            "note": "Simulated: no external tracker was called."}


TOOLS: dict[str, ToolDef] = {t.name: t for t in [
    ToolDef("calculator", "Evaluate an arithmetic expression safely.", {"expression": "e.g. (199 * 12) * 0.85"}, False, calculator),
    ToolDef("kb_search", "Search a RAG dataset you can read (permission-filtered).", {"query": "search text", "dataset": "dataset slug"},
            False, None),  # bound by the executor (needs the database and the user's groups)
    ToolDef("sql_query", "Run a read-only SELECT on the demo customers/orders database.", {"sql": "SELECT ..."}, False, sql_query),
    ToolDef("json_extract", "Parse JSON from text and pick a value by dotted path.", {"text": "text containing JSON", "path": "a.b.0"},
            False, json_extract),
    ToolDef("word_count", "Count words and characters.", {"text": "any text"}, False, word_count),
    ToolDef("current_time", "Current UTC time.", {}, False, current_time),
    ToolDef("send_email", "Send an email (simulated). Requires human approval upstream.", {"to": "address", "subject": "subject", "body": "body"},
            True, send_email),
    ToolDef("create_ticket", "Create a ticket (simulated). Requires human approval upstream.",
            {"title": "title", "priority": "low | normal | high", "body": "details"}, True, create_ticket),
]}


def describe() -> list[dict]:
    return [{"name": t.name, "description": t.description, "args": t.args, "side_effect": t.side_effect} for t in TOOLS.values()]


def to_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
