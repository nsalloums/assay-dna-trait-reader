"""FastAPI application: serves the local SPA and the on-device parse/annotate API.

Runtime privacy posture:
  * Binds loopback only (enforced in run.py / the lifespan check).
  * Strict CSP + security headers on every response.
  * Parse/annotate import only local core modules (no HTTP client).
  * User genotypes live only in the in-memory, TTL-bounded session store.
"""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import config
from .api import annotate, db, health, parse
from .core import security
from .core.annotation import get_store
from .core.sessions import STORE
from .db_update import build_seed


async def _session_sweeper():
    while True:
        await asyncio.sleep(config.SESSION_SWEEP_SECONDS)
        STORE.sweep()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    security.install_log_filter()
    # Ensure the app works out-of-the-box: build the offline seed DB if none exists.
    from . import db as dbmod
    if not dbmod.db_exists_and_ready():
        build_seed.build_seed()
    get_store()  # load annotation store into memory (metadata only)

    sweeper = asyncio.create_task(_session_sweeper())
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper
        STORE.clear()  # no user data lingers in RAM after shutdown


def create_app() -> FastAPI:
    app = FastAPI(
        title="Local DNA Trait Extractor",
        version="0.1.0",
        description="100% local, privacy-first DNA trait extraction. Educational use only.",
        lifespan=lifespan,
        docs_url=None,       # no external Swagger CDN assets (CSP-friendly, offline)
        redoc_url=None,
    )
    app.add_middleware(security.SecurityHeadersMiddleware)

    app.include_router(health.router)
    app.include_router(parse.router)
    app.include_router(annotate.router)
    app.include_router(db.router)

    # Serve the SPA same-origin so CSP connect-src 'self' fully applies.
    if config.WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(config.WEB_DIR), html=True), name="web")

    return app


app = create_app()
