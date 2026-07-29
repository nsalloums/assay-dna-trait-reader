"""SQLite connection + schema helpers for the local annotation store.

This module imports NO network client. It only ever reads/writes the local
annotation database, which contains public annotation data + the curated seed —
never user genotypes.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config


def connect(db_path: Path | None = None, *, readonly: bool = False) -> sqlite3.Connection:
    """Open the annotation DB. Read-only connections are used on the runtime
    (parse/annotate) path so it is structurally impossible to write user data."""
    path = Path(db_path) if db_path else config.DB_FILE
    if readonly:
        uri = f"file:{path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Keep SQLite temp tables/indexes/sorters in RAM, never on disk. The annotate path
    # builds a TEMP table of the user's rsIDs, and Python's bundled SQLite is compiled
    # with TEMP_STORE=1 (default: FILE) — so without this, a ~600k-rsID file spills an
    # ~19 MB etilqs_* scratch file of plaintext rsIDs into the system temp dir. This
    # lives here, not at the call site, so that every read-only connection is safe by
    # construction rather than by a caller remembering.
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables/indexes from data/schema.sql (idempotent) and stamp version."""
    conn.executescript(config.SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version = {config.SCHEMA_VERSION}")
    conn.commit()


def db_exists_and_ready(db_path: Path | None = None) -> bool:
    """True if the DB file exists and has at least one annotation row."""
    path = Path(db_path) if db_path else config.DB_FILE
    if not path.exists():
        return False
    try:
        conn = connect(path, readonly=True)
        try:
            row = conn.execute("SELECT COUNT(*) AS n FROM annotation").fetchone()
            return bool(row and row["n"] > 0)
        finally:
            conn.close()
    except sqlite3.Error:
        return False
