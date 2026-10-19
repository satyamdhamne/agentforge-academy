"""Demo database plus guarded, read-only SQL execution for the SQL Query Assistant."""

from __future__ import annotations

import random
import sqlite3
import time
from datetime import date, timedelta

SCHEMA_DDL = """CREATE TABLE customers (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  country TEXT NOT NULL, created_at DATE NOT NULL
);
CREATE TABLE products (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, price NUMERIC NOT NULL
);
CREATE TABLE orders (
  id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(id),
  status TEXT NOT NULL CHECK (status IN ('pending','paid','shipped','cancelled','refunded')),
  created_at DATE NOT NULL
);
CREATE TABLE order_items (
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id), quantity INTEGER NOT NULL CHECK (quantity > 0),
  unit_price NUMERIC NOT NULL
);"""

COUNTRIES = ["India", "United States", "Germany", "United Kingdom", "Brazil", "Japan", "Canada"]
PRODUCTS = [
    ("Mechanical Keyboard", "Electronics", 89.0), ("USB-C Hub", "Electronics", 39.0), ("27in Monitor", "Electronics", 249.0),
    ("Noise-Cancelling Headphones", "Electronics", 179.0), ("Standing Desk", "Furniture", 399.0),
    ("Ergonomic Chair", "Furniture", 289.0), ("Desk Lamp", "Furniture", 45.0), ("Clean Code", "Books", 34.0),
    ("Designing Data-Intensive Applications", "Books", 49.0), ("The Pragmatic Programmer", "Books", 42.0),
    ("Coffee Beans 1kg", "Grocery", 24.0), ("Green Tea 100 bags", "Grocery", 12.0), ("Water Bottle", "Accessories", 19.0),
    ("Laptop Sleeve", "Accessories", 29.0), ("Webcam 1080p", "Electronics", 69.0), ("Cable Organizer", "Accessories", 9.0),
    ("Whiteboard", "Furniture", 79.0), ("Notebook Set", "Stationery", 15.0), ("Gel Pens (12)", "Stationery", 8.0),
    ("Vintage Typewriter", "Collectibles", 650.0),
]
FIRST = ["Asha", "Ben", "Chen", "Diego", "Elena", "Farah", "Gita", "Hiro", "Ines", "Jamal", "Kofi", "Lena", "Mateo",
         "Nia", "Omar", "Priya", "Quinn", "Ravi", "Sara", "Tomas"]
LAST = ["Iyer", "Smith", "Wang", "Garcia", "Muller", "Khan", "Patel", "Sato", "Silva", "Brown"]


def build_demo_db() -> sqlite3.Connection:
    """Deterministic e-commerce dataset (seeded RNG) so examples and evals are reproducible."""
    rng = random.Random(42)
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA_DDL)
    start = date(2025, 1, 1)
    customers = []
    for i in range(1, 61):
        name = f"{FIRST[i % len(FIRST)]} {LAST[(i * 7) % len(LAST)]}"
        customers.append((i, name, f"user{i}@example.com", COUNTRIES[i % len(COUNTRIES)],
                          (start + timedelta(days=rng.randint(0, 200))).isoformat()))
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", customers)
    conn.executemany("INSERT INTO products VALUES (?,?,?,?)", [(i + 1, *p) for i, p in enumerate(PRODUCTS)])
    statuses = ["paid"] * 6 + ["shipped"] * 6 + ["pending", "cancelled", "refunded"]
    item_id = 1
    for oid in range(1, 301):
        cid = rng.randint(1, 55)  # customers 56-60 never order (useful for "customers without orders")
        created = start + timedelta(days=rng.randint(0, 364))
        conn.execute("INSERT INTO orders VALUES (?,?,?,?)", (oid, cid, rng.choice(statuses), created.isoformat()))
        for pid in rng.sample(range(1, 20), rng.randint(1, 3)):  # product 20 is never ordered
            qty = rng.randint(1, 4)
            conn.execute("INSERT INTO order_items VALUES (?,?,?,?,?)", (item_id, oid, pid, qty, PRODUCTS[pid - 1][2]))
            item_id += 1
    conn.commit()
    return conn


_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}


def _authorizer(action: int, arg1, arg2, dbname, source) -> int:
    if action in _ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class SQLGuardError(ValueError):
    pass


def check_sql(sql: str) -> str:
    """Cheap static checks before execution. The authorizer is the real enforcement layer."""
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise SQLGuardError("Empty SQL")
    head = cleaned.split(None, 1)[0].upper()
    if head not in ("SELECT", "WITH"):
        raise SQLGuardError(f"Only read-only SELECT/WITH queries are allowed (got {head})")
    if ";" in cleaned.replace("';'", ""):
        raise SQLGuardError("Multiple statements are not allowed")
    return cleaned


def execute_readonly(conn: sqlite3.Connection, sql: str, max_rows: int = 200, timeout_s: float = 2.0) -> dict:
    cleaned = check_sql(sql)
    deadline = time.monotonic() + timeout_s
    conn.execute("PRAGMA query_only = ON")
    conn.set_authorizer(_authorizer)
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
    try:
        cur = conn.execute(cleaned)
        rows = cur.fetchmany(max_rows + 1)
        columns = [d[0] for d in cur.description or []]
    except sqlite3.DatabaseError as exc:
        msg = str(exc)
        if "interrupted" in msg:
            msg = f"Query exceeded the {timeout_s}s time limit"
        raise SQLGuardError(msg) from exc
    finally:
        conn.set_authorizer(None)
        conn.set_progress_handler(None, 0)
    return {
        "columns": columns,
        "rows": [list(r) for r in rows[:max_rows]],
        "row_count": min(len(rows), max_rows),
        "truncated": len(rows) > max_rows,
    }


def describe_schema(conn: sqlite3.Connection) -> str:
    parts = [SCHEMA_DDL, "", "Sample values:"]
    parts.append("orders.status: " + ", ".join(r[0] for r in conn.execute("SELECT DISTINCT status FROM orders ORDER BY 1")))
    parts.append("products.category: " + ", ".join(r[0] for r in conn.execute("SELECT DISTINCT category FROM products ORDER BY 1")))
    parts.append("customers.country: " + ", ".join(r[0] for r in conn.execute("SELECT DISTINCT country FROM customers ORDER BY 1")))
    parts.append("Dates are ISO strings (YYYY-MM-DD); use strftime('%Y-%m', created_at) for months.")
    parts.append("Revenue = SUM(order_items.quantity * order_items.unit_price) over orders with status IN ('paid','shipped').")
    return "\n".join(parts)
