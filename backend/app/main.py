from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .core.errors import install_error_handlers
from .core.middleware import CSRFMiddleware, RequestContextMiddleware, configure_logging
from .modules import admin, agents, auth, challenges, codelab, learning, misc


def create_app() -> FastAPI:
    s = get_settings()
    if not s.is_test:
        configure_logging(s.log_level)
    app = FastAPI(
        title="AgentForge Academy API",
        version="1.0.0",
        description="Learning platform API: catalog, lessons, challenges, sandboxed code execution and AI agents.",
        openapi_url=f"{s.api_prefix}/openapi.json",
        docs_url=f"{s.api_prefix}/docs",
        redoc_url=None,
    )
    # Order matters: the last added middleware runs first. Context (trace id) wraps everything.
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                       allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key", "X-Request-Id"],
                       expose_headers=["X-Trace-Id"])
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)

    for r in (auth.router, auth.me_router, learning.router, challenges.router, codelab.router, agents.router,
              admin.router, admin.public_router, misc.router):
        app.include_router(r, prefix=s.api_prefix)
    app.include_router(misc.health_router)
    return app


app = create_app()
