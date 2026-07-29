"""Annotate endpoint — the core progressive-rendering path (SSE).

Joins the in-memory parsed genotypes for a session against the LOCAL annotation
store and streams matches as they resolve. This path opens NO sockets to any
external host (the module imports only local core code), so an auditor can assert
it is network-silent. Only derived match rows for the user's own genotypes are
streamed to the localhost UI.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core import content
from ..core.annotation import consolidate, get_store
from ..core.sessions import STORE

router = APIRouter()

BATCH = 25


class AnnotateRequest(BaseModel):
    session_id: str
    categories: list[str] | None = None
    include_health: bool = True


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/annotate")
async def annotate(req: AnnotateRequest) -> StreamingResponse:
    genome = STORE.get(req.session_id)
    if genome is None:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada. Vuelve a subir el archivo.")

    store = get_store()
    if not store.ready:
        raise HTTPException(status_code=503, detail="La base de anotación no está construida. Ejecuta update_databases / seed.")

    async def gen():
        yield _sse("meta", {
            "vendor": genome.vendor,
            "build": genome.build,
            "snp_count": genome.snp_count,
            "called_count": genome.called_count,
            "sources": store.freshness(),
            "disclaimers": content.disclaimers(),
            "categories": content.trait_categories(),
        })

        # Run the (CPU/IO-bound, local, ~1s) match off the event loop.
        loop = asyncio.get_running_loop()
        matches = await loop.run_in_executor(
            None, lambda: consolidate(list(store.match(genome.genotypes)))
        )
        if req.categories:
            wanted = set(req.categories)
            matches = [m for m in matches if m.get("category") in wanted]

        total = len(matches)
        cat_counts: Counter[str] = Counter(m.get("category", "other") for m in matches)
        yield _sse("progress", {"done": 0, "total": total})

        batch: list[dict] = []
        for i, m in enumerate(matches, 1):
            batch.append(m)
            if len(batch) >= BATCH:
                yield _sse("matches", {"rows": batch})
                yield _sse("progress", {"done": i, "total": total})
                batch = []
                await asyncio.sleep(0)  # keep the stream live
        if batch:
            yield _sse("matches", {"rows": batch})

        yield _sse("done", {
            "total": total,
            "counts_by_category": dict(cat_counts),
            "health_count": sum(1 for m in matches if m.get("is_health")),
        })

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
