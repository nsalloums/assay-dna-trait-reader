"""Liveness/readiness probe."""
from __future__ import annotations

import snps
from fastapi import APIRouter

from .. import __version__
from ..core.annotation import get_store

router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    store = get_store()
    return {
        "status": "ok",
        "app_version": __version__,
        "snps_version": snps.__version__,
        "db_ready": store.ready,
    }
