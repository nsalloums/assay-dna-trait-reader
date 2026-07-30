"""Upload + parse endpoints.

The upload is sent as a raw request body (application/octet-stream) and read fully
into memory — Starlette's multipart UploadFile would spool large bodies to a temp
file on disk, which would violate the in-memory-only guarantee, so we avoid it. The
custom X-Filename header also forces a CORS preflight, so a malicious cross-origin
page cannot POST a body here. Parsed genotypes are stashed in the in-memory session
store (RAM only, TTL-bounded) and only a non-sensitive summary is returned.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from .. import config
from ..core import parsing
from ..core.sessions import STORE

router = APIRouter()


@router.post("/api/parse")
async def parse(request: Request) -> dict:
    # Reject oversized uploads BEFORE reading the body into memory.
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The file exceeds the {config.MAX_UPLOAD_BYTES // (1024*1024)} MB limit.",
        )

    raw = await request.body()  # buffered in RAM by Starlette; never spooled to disk
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The file exceeds the {config.MAX_UPLOAD_BYTES // (1024*1024)} MB limit.",
        )

    filename = request.headers.get("x-filename", "")
    try:
        genome = parsing.parse_bytes(raw, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        del raw  # drop the raw bytes reference promptly

    session_id = STORE.create(genome)
    return {"session_id": session_id, **genome.summary()}


@router.delete("/api/session/{session_id}", status_code=204)
def delete_session(session_id: str) -> Response:
    """Explicitly purge a session's in-memory genotypes (called on reset/unload)."""
    STORE.delete(session_id)
    return Response(status_code=204)
