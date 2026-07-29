"""In-memory, TTL-bounded session store for parsed genotypes.

This is the ONLY place a user's genotypes live, and only in RAM. Sessions are
keyed by an opaque uuid4 handle (not an identity), expire after a TTL, and can be
purged explicitly (the UI calls DELETE /api/session on reset/unload). Nothing here
is ever written to disk or transmitted.
"""
from __future__ import annotations

import threading
import time
import uuid

from .. import config
from .parsing import ParsedGenome


class SessionStore:
    def __init__(self, ttl_seconds: int = config.SESSION_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._data: dict[str, tuple[float, ParsedGenome]] = {}

    def create(self, genome: ParsedGenome) -> str:
        sid = uuid.uuid4().hex
        with self._lock:
            self._data[sid] = (time.monotonic(), genome)
        return sid

    def get(self, sid: str) -> ParsedGenome | None:
        with self._lock:
            entry = self._data.get(sid)
            if not entry:
                return None
            ts, genome = entry
            if time.monotonic() - ts > self._ttl:
                # Expired: drop it now.
                self._data.pop(sid, None)
                return None
            return genome

    def delete(self, sid: str) -> bool:
        with self._lock:
            return self._data.pop(sid, None) is not None

    def sweep(self) -> int:
        """Drop expired sessions; return how many were removed."""
        now = time.monotonic()
        with self._lock:
            expired = [sid for sid, (ts, _) in self._data.items() if now - ts > self._ttl]
            for sid in expired:
                self._data.pop(sid, None)
        return len(expired)

    def clear(self) -> None:
        """Drop every session (called on shutdown so no data lingers in RAM)."""
        with self._lock:
            self._data.clear()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._data)


# Single process-local store (uvicorn runs a single worker so this stays coherent).
STORE = SessionStore()
