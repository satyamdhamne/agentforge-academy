from __future__ import annotations

import re
import uuid

from tests.conftest import PASSWORD, Api


def test_register_creates_session_profile_and_free_plan(api):
    u = api.register("Grace")
    assert u["profile"]["display_name"] == "Grace"
    assert u["plan"] == "free" and u["roles"] == ["learner"] and u["email_verified"] is False
    me = api.get("/auth/me").json()
    assert me["email"] == u["email"]


def test_register_rejects_weak_and_duplicate(api):
    r = api.post("/auth/register", {"email": "weak@example.com", "password": "short", "display_name": "W"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "weak_password"
    u = api.register()
    r = api.post("/auth/register", {"email": u["email"].upper(), "password": PASSWORD, "display_name": "Dup"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


def test_login_logout_and_bad_credentials(app):
    a = Api(app)
    u = a.register()
    a.post("/auth/logout")
    assert a.get("/auth/me").status_code == 401
    b = Api(app)
    r = b.post("/auth/login", {"email": u["email"], "password": "wrong-password-123"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"
    r = b.post("/auth/login", {"email": "nobody-" + uuid.uuid4().hex + "@example.com", "password": "whatever-123"})
    assert r.status_code == 401  # same response for unknown accounts
    b.login(u["email"], PASSWORD)
    assert b.get("/auth/me").status_code == 200


def test_session_cookie_is_httponly(app):
    a = Api(app)
    email = f"c-{uuid.uuid4().hex[:8]}@example.com"
    r = a.post("/auth/register", {"email": email, "password": PASSWORD, "display_name": "Cookie"})
    cookie = r.headers["set-cookie"]
    assert "af_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_email_verification_and_password_reset(app, monkeypatch):
    from app.modules import auth

    sent: list[str] = []
    monkeypatch.setattr(auth, "send_email", lambda to, subject, body: sent.append(body))
    a = Api(app)
    u = a.register()
    token = re.search(r"token=([\w-]+)", sent[-1]).group(1)
    assert a.post("/auth/verify-email", {"token": token}).json() == {"verified": True}
    assert a.get("/auth/me").json()["email_verified"] is True
    assert a.post("/auth/verify-email", {"token": token}).status_code == 400  # single use

    # Reset: identical response for unknown emails (no enumeration)
    unknown = a.post("/auth/password-reset/request", {"email": "ghost@example.com"}).json()
    known = a.post("/auth/password-reset/request", {"email": u["email"]}).json()
    assert unknown == known
    reset_token = re.search(r"token=([\w-]+)", sent[-1]).group(1)
    assert a.post("/auth/password-reset/confirm", {"token": reset_token, "new_password": "brand-new-secret-42"}).json() == {"reset": True}
    assert a.get("/auth/me").status_code == 401  # all sessions revoked
    a.login(u["email"], "brand-new-secret-42")


def test_profile_update(learner):
    r = learner.patch("/me/profile", {"display_name": "  Lee  ", "experience_level": "advanced", "goals": ["RAG"]})
    assert r.status_code == 200
    assert r.json()["profile"]["display_name"] == "Lee" and r.json()["profile"]["goals"] == ["RAG"]
    assert learner.patch("/me/profile", {"experience_level": "wizard"}).status_code == 422


def test_csrf_required_for_unsafe_requests(app):
    from fastapi.testclient import TestClient

    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    token = c.get("/api/v1/auth/csrf").json()["csrf_token"]
    r = c.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"},
               headers={"X-CSRF-Token": token, "Origin": "https://evil.example"})
    assert r.status_code == 403  # cross-origin rejected even with a token


def test_auth_rate_limit(app, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "rate_limit_auth_per_minute", 3)
    a = Api(app)
    codes = [a.post("/auth/login", {"email": "x@example.com", "password": "nope-nope-nope"}).status_code for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[-1] == 429
