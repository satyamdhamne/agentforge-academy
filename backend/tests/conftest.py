"""Integration-test fixtures.

Tests run against a real PostgreSQL database (TEST_DATABASE_URL, default: agentforge_test on localhost) that is
dropped and re-created once per session, migrated with Alembic (so migrations are tested too) and seeded.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://agentforge:agentforge@localhost:5432/agentforge_test")

os.environ.update({
    "ENV": "test", "DATABASE_URL": TEST_DB_URL, "SANDBOX_URL": "", "LLM_PROVIDER": "mock",
    "RATE_LIMIT_AUTH_PER_MINUTE": "1000", "RATE_LIMIT_SANDBOX_PER_MINUTE": "1000", "RATE_LIMIT_AGENT_RUNS_PER_MINUTE": "1000",
    "CORS_ORIGINS": "http://localhost:5173", "MAIL_BACKEND": "console",
})

PASSWORD = "correct-horse-battery"


def _recreate_database(url: str) -> None:
    u = make_url(url)
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :d AND pid <> pg_backend_pid()"),
                  {"d": u.database})
        c.execute(text(f'DROP DATABASE IF EXISTS "{u.database}"'))
        c.execute(text(f'CREATE DATABASE "{u.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def database():
    from alembic.config import Config

    from alembic import command
    from app.core.config import get_settings
    from app.core.db import SessionLocal, reset_engine
    from app.seed.loader import seed_all

    _recreate_database(TEST_DB_URL)
    get_settings.cache_clear()
    reset_engine()
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    command.upgrade(cfg, "head")
    with SessionLocal() as db:
        seed_all(db)
    yield
    reset_engine()


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    from app.core.ratelimit import limiter
    from app.modules import challenges
    from app.services.sandbox import override_sandbox

    limiter.reset()
    monkeypatch.setattr(challenges, "ATTEMPT_COOLDOWN_S", 0)
    override_sandbox(None)  # code execution disabled unless a test opts in
    yield
    override_sandbox()


@pytest.fixture
def app():
    from app.main import create_app

    return create_app()


class Api:
    """TestClient wrapper that handles the CSRF double-submit cookie like the real frontend."""

    def __init__(self, app):
        from fastapi.testclient import TestClient

        self.c = TestClient(app, base_url="http://testserver")
        self.csrf = self.c.get("/api/v1/auth/csrf").json()["csrf_token"]

    def _h(self, headers=None):
        return {"X-CSRF-Token": self.csrf, **(headers or {})}

    def get(self, path, **kw):
        return self.c.get(f"/api/v1{path}", **kw)

    def post(self, path, json=None, headers=None, **kw):
        return self.c.post(f"/api/v1{path}", json=json, headers=self._h(headers), **kw)

    def patch(self, path, json=None, headers=None):
        return self.c.patch(f"/api/v1{path}", json=json, headers=self._h(headers))

    def register(self, name="Test Learner") -> dict:
        email = f"user-{uuid.uuid4().hex[:10]}@example.com"
        r = self.post("/auth/register", {"email": email, "password": PASSWORD, "display_name": name})
        assert r.status_code == 201, r.text
        return {**r.json(), "password": PASSWORD}

    def login(self, email, password):
        r = self.post("/auth/login", {"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture
def api(app):
    return Api(app)


@pytest.fixture
def learner(app):
    a = Api(app)
    a.user = a.register()
    return a


@pytest.fixture
def admin(app):
    from app.core.config import get_settings

    s = get_settings()
    a = Api(app)
    a.user = a.login(s.seed_admin_email, s.seed_admin_password)
    return a


@pytest.fixture
def author(app):
    from app.core.config import get_settings

    a = Api(app)
    a.user = a.login("author@example.com", get_settings().seed_demo_password)
    return a


class LocalSandbox:
    """TEST ONLY: calls the sandbox executor in-process (subprocess with rlimits). Production uses the isolated service."""

    def __init__(self):
        sys.path.insert(0, str(ROOT / "sandbox"))
        from runner.executor import execute

        self._execute = execute

    def status(self):
        return {"available": True, "languages": {"python": True, "javascript": True, "sql": True}}

    def run(self, payload: dict) -> dict:
        return self._execute(payload["language"], payload["code"], stdin=payload.get("stdin", ""),
                             timeout_ms=payload.get("timeout_ms", 5000), tests=payload.get("tests"),
                             sql_setup=payload.get("sql_setup"), sql_expected=payload.get("sql_expected")).to_dict()


@pytest.fixture
def sandbox():
    from app.services.sandbox import override_sandbox

    sb = LocalSandbox()
    override_sandbox(sb)
    return sb
