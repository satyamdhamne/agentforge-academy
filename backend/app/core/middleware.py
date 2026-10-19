"""Request-scoped trace ids, structured access logs, security headers and CSRF protection."""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import get_settings
from .security import constant_time_equals

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT = {"/api/v1/auth/csrf"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": round(record.created, 3), "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        for key in ("trace_id", "path", "method", "status", "duration_ms", "user_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True  # replaced by our structured access log


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        trace_id = incoming if incoming.isalnum() and len(incoming) <= 64 else uuid.uuid4().hex
        request.state.trace_id = trace_id
        started = time.perf_counter()
        response: Response = await call_next(request)
        duration = round((time.perf_counter() - started) * 1000, 1)
        response.headers["X-Trace-Id"] = trace_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        logging.getLogger("agentforge.access").info(
            "request", extra={"trace_id": trace_id, "path": request.url.path, "method": request.method,
                              "status": response.status_code, "duration_ms": duration})
        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit cookie: unsafe requests must echo the CSRF cookie in the X-CSRF-Token header.

    Combined with SameSite=Lax session cookies and an Origin check, this blocks cross-site form posts
    and fetches. The token is random per browser and not tied to secrets.
    """

    async def dispatch(self, request: Request, call_next):
        s = get_settings()
        if request.method not in SAFE_METHODS and request.url.path.startswith("/api/") and request.url.path not in CSRF_EXEMPT:
            origin = request.headers.get("origin")
            if origin:
                o = urlparse(origin)
                allowed = {urlparse(x).netloc for x in s.cors_origins} | {request.url.netloc}
                if o.netloc not in allowed:
                    return self._reject(request, "Origin not allowed")
            cookie = request.cookies.get(s.csrf_cookie)
            header = request.headers.get("x-csrf-token")
            if not constant_time_equals(cookie, header):
                return self._reject(request, "Missing or invalid CSRF token. Fetch /api/v1/auth/csrf first.")
        return await call_next(request)

    @staticmethod
    def _reject(request: Request, message: str) -> JSONResponse:
        return JSONResponse(status_code=403, content={"error": {"code": "csrf_failed", "message": message, "details": None,
                                                                "trace_id": getattr(request.state, "trace_id", None)}})


def client_ip(request: Request) -> str:
    s = get_settings()
    if s.trusted_proxies > 0:
        forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(forwarded) >= s.trusted_proxies:
            return forwarded[-s.trusted_proxies]
    return request.client.host if request.client else "unknown"
