"""Client for the isolated sandbox runner service. The API process itself never executes learner code."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.errors import AppError

log = logging.getLogger("agentforge.sandbox")


class SandboxUnavailable(AppError):
    status_code, code = 503, "sandbox_unavailable"


class SandboxClient:
    def __init__(self, base_url: str, token: str, timeout_s: float = 20.0, transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_s, transport=transport,
                                    headers={"X-Sandbox-Token": token} if token else {})

    def status(self) -> dict[str, Any]:
        try:
            r = self._client.get("/healthz", timeout=3)
            r.raise_for_status()
            return {"available": True, **r.json()}
        except httpx.HTTPError as exc:
            log.warning("sandbox health check failed: %s", exc)
            return {"available": False, "languages": {}}

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self._client.post("/v1/run", json=payload)
        except httpx.HTTPError as exc:
            raise SandboxUnavailable("Code runner is unreachable right now.") from exc
        if r.status_code == 401:
            raise SandboxUnavailable("Code runner rejected the service token (check SANDBOX_TOKEN).")
        if r.status_code >= 400:
            raise AppError(f"Code runner error: {r.text[:300]}", code="sandbox_error", status_code=502)
        return r.json()


_client: SandboxClient | None = None
_UNSET = object()
_override: object = _UNSET


def get_sandbox() -> SandboxClient | None:
    """Returns None when no sandbox is configured: code execution is then disabled and labelled as such."""
    global _client
    if _override is not _UNSET:
        return _override  # type: ignore[return-value]
    s = get_settings()
    if not s.sandbox_url:
        return None
    if _client is None or _client.base_url != s.sandbox_url.rstrip("/"):
        _client = SandboxClient(s.sandbox_url, s.sandbox_token)
    return _client


def override_sandbox(client: SandboxClient | None | object = _UNSET) -> None:
    """Test hook: force a specific client (or None). Call with no argument to restore normal behaviour."""
    global _override
    _override = client
