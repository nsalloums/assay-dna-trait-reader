"""Annotation-database status + update endpoints.

GET /api/db/status reads only local freshness metadata. POST /api/db/update is the
SOLE endpoint permitted to touch the network — it downloads PUBLIC annotation DBs
(GWAS Catalog / ClinVar / PharmGKB) and transmits ZERO user data. The network
module (``db_update``) is imported lazily here, keeping it off the parse/annotate
import graph so that path is provably network-silent.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.annotation import get_store, reload_store

router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/api/db/status")
def db_status() -> dict:
    store = get_store()
    sources = store.freshness()
    return {
        "ready": store.ready,
        "offline_ready": store.ready,
        "sources": sources,
    }


class UpdateRequest(BaseModel):
    sources: list[str] | None = None
    limit: int | None = None


@router.post("/api/db/update")
async def db_update(req: UpdateRequest) -> StreamingResponse:
    # Lazy import: keeps the network client off the parse/annotate import graph.
    from ..db_update import update as upd
    from ..db_update.sources import SOURCES

    keys = req.sources or list(SOURCES.keys())
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def progress(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def runner():
        try:
            await loop.run_in_executor(
                None, lambda: upd.update_databases(keys=keys, limit=req.limit, progress=progress)
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"phase": "__end__"})

    async def gen():
        yield _sse("start", {"sources": keys})
        task = asyncio.create_task(runner())
        try:
            while True:
                ev = await queue.get()
                if ev.get("phase") == "__end__":
                    break
                yield _sse("progress", ev)
        finally:
            await task
        store = reload_store()
        yield _sse("done", {"ready": store.ready, "sources": store.freshness()})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
