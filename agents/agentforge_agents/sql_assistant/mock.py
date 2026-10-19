"""Offline responder: intent templates for common analytics questions over the demo schema.

Questions that match no template get a clarification request - the honest behaviour for a
system that cannot actually understand arbitrary language.
"""

from __future__ import annotations

import re

from ..core import CompletionRequest

REVENUE = "SUM(oi.quantity * oi.unit_price)"
VALID = "o.status IN ('paid','shipped')"
ASSUME_REV = "Revenue counts only orders with status paid or shipped."
COUNTRIES = ["india", "united states", "germany", "united kingdom", "brazil", "japan", "canada"]


def _n(q: str, default: int = 5) -> int:
    m = re.search(r"\btop\s+(\d{1,3})\b|\b(\d{1,3})\s+(?:best|top|most)\b", q)
    return int(m.group(1) or m.group(2)) if m else default


def generate(request: CompletionRequest) -> dict:
    q = request.context.get("question", "").lower()
    n = _n(q)
    def out(sql: str, explanation: str, assumptions: list[str] | None = None) -> dict:
        return {"sql": sql, "explanation": explanation, "assumptions": assumptions or []}

    if re.search(r"customer", q) and re.search(r"revenue|spen[dt]|top|best|most valuable", q) and "country" not in q:
        return out(f"SELECT c.id, c.name, ROUND({REVENUE}, 2) AS revenue\nFROM customers c\nJOIN orders o ON o.customer_id = c.id\n"
                   f"JOIN order_items oi ON oi.order_id = o.id\nWHERE {VALID}\nGROUP BY c.id, c.name\nORDER BY revenue DESC\nLIMIT {n};",
                   f"Ranks customers by total revenue and returns the top {n}.", [ASSUME_REV])
    if re.search(r"(revenue|sales).*(month|monthly)|monthly (revenue|sales)", q):
        return out(f"SELECT strftime('%Y-%m', o.created_at) AS month, ROUND({REVENUE}, 2) AS revenue\nFROM orders o\n"
                   f"JOIN order_items oi ON oi.order_id = o.id\nWHERE {VALID}\nGROUP BY month\nORDER BY month;",
                   "Groups paid/shipped order revenue by calendar month.", [ASSUME_REV])
    if re.search(r"categor", q):
        return out(f"SELECT p.category, ROUND({REVENUE}, 2) AS revenue, SUM(oi.quantity) AS units\nFROM order_items oi\n"
                   f"JOIN orders o ON o.id = oi.order_id\nJOIN products p ON p.id = oi.product_id\nWHERE {VALID}\n"
                   "GROUP BY p.category\nORDER BY revenue DESC;", "Revenue and units per product category.", [ASSUME_REV])
    if re.search(r"never (been )?ordered|no orders.*product|products? (with )?no (orders|sales)|unsold", q):
        return out("SELECT p.id, p.name\nFROM products p\nLEFT JOIN order_items oi ON oi.product_id = p.id\n"
                   "WHERE oi.id IS NULL\nORDER BY p.id;", "Anti-join: products with no order items.")
    if re.search(r"customers? (with(out)?|who have) (no|never|not)|never (placed|ordered)|without (any )?orders", q):
        return out("SELECT c.id, c.name, c.email\nFROM customers c\nWHERE NOT EXISTS (\n  SELECT 1 FROM orders o WHERE o.customer_id = c.id\n)\n"
                   "ORDER BY c.id;", "Customers that have never placed an order (NOT EXISTS anti-join).")
    if re.search(r"product", q) and re.search(r"best|top|most|popular|sold|selling", q):
        return out(f"SELECT p.name, SUM(oi.quantity) AS units_sold\nFROM order_items oi\nJOIN orders o ON o.id = oi.order_id\n"
                   f"JOIN products p ON p.id = oi.product_id\nWHERE {VALID}\nGROUP BY p.id, p.name\nORDER BY units_sold DESC\nLIMIT {n};",
                   f"Top {n} products by units sold.", ["Units count only paid or shipped orders."])
    if re.search(r"status", q) and re.search(r"order", q):
        return out("SELECT status, COUNT(*) AS orders\nFROM orders\nGROUP BY status\nORDER BY orders DESC;", "Order count per status.")
    if re.search(r"average order value|aov|average (order|basket)", q):
        return out(f"SELECT ROUND(AVG(order_total), 2) AS average_order_value\nFROM (\n  SELECT o.id, {REVENUE} AS order_total\n"
                   f"  FROM orders o JOIN order_items oi ON oi.order_id = o.id\n  WHERE {VALID}\n  GROUP BY o.id\n) t;",
                   "Average of per-order totals.", [ASSUME_REV])
    country = next((c for c in COUNTRIES if c in q), None)
    if country and re.search(r"customer", q):
        return out(f"SELECT COUNT(*) AS customers\nFROM customers\nWHERE country = '{country.title()}';",
                   f"Counts customers located in {country.title()}.")
    if re.search(r"customers?.*(per|by) country|countr(y|ies).*customers", q):
        return out("SELECT country, COUNT(*) AS customers\nFROM customers\nGROUP BY country\nORDER BY customers DESC;",
                   "Customer count per country.")
    if re.search(r"how many orders|number of orders|total orders|count (of )?orders", q):
        return out("SELECT COUNT(*) AS orders\nFROM orders;", "Total number of orders (all statuses).",
                   ["Counts orders in every status, including cancelled."])
    return {"sql": "", "explanation": "", "assumptions": [], "needs_clarification": True,
            "clarification_question": "I couldn't map that to the schema. Which table or metric do you mean "
                                      "(customers, orders, products, revenue)?"}


RESPONDERS = {"sql_assistant.generate": generate}
