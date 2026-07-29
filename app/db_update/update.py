"""Orchestrate update_databases: fetch -> normalize -> upsert -> record freshness.

The ONLY code path that touches the network (via ``sources``). Transmits zero
user data. Each source is updated atomically and independently: a failure leaves
previously-loaded rows (seed or a prior update) intact, so the app never regresses
to empty.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from .. import config
from .. import db as dbmod
from . import normalize, sources
from .sources import SOURCES

# Column order for bulk insert (must match the tuple built in _row_tuple).
_COLUMNS = [
    "rsid", "genotype", "gene", "trait", "category", "sensitivity", "effect_text",
    "magnitude", "plain_summary", "risk_allele", "ref_allele", "alt_allele", "orientation",
    "ambiguous_strand", "chrom", "pos_b37", "pos_b38", "effect_size", "confidence",
    "evidence", "source", "source_version", "fetched_date", "citation",
]

_NORMALIZERS = {
    "gwas_catalog": normalize.normalize_gwas,
    "clinvar": normalize.normalize_clinvar,
    "pharmgkb": normalize.normalize_pharmgkb,
}

ProgressCB = Callable[[dict], None] | None


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_tuple(row: dict, source: str, version: str, fetched: str) -> tuple:
    row = {**row, "source": source, "source_version": version, "fetched_date": fetched}
    return tuple(row.get(c) for c in _COLUMNS)


def _emit(cb: ProgressCB, **event) -> dict:
    if cb:
        cb(event)
    return event


def update_source(key: str, *, limit: int | None = None, progress: ProgressCB = None,
                  db_path: Path | None = None) -> dict:
    """Update a single source atomically. Returns a per-source result dict."""
    src = SOURCES[key]
    path = db_path or config.DB_FILE
    dl_dir = config.DOWNLOAD_DIR
    _emit(progress, source=key, phase="head", message=f"Checking {src.name}…")

    head = sources.http_head(src.url)
    version = sources.version_from_last_modified(head.get("last_modified"))

    _emit(progress, source=key, phase="download", pct=0.0,
          message=f"Downloading {src.name} ({head.get('content_length',0)//(1024*1024)} MB)…")
    dest = dl_dir / Path(src.url).name
    dl = sources.download(
        src.url, dest,
        progress=lambda lbl, pct: _emit(progress, source=key, phase="download", pct=pct),
        label=src.name,
    )
    version = sources.version_from_last_modified(dl.get("last_modified")) or version

    _emit(progress, source=key, phase="normalize", pct=0.0, message=f"Parsing {src.name}…")
    normalizer = _NORMALIZERS[key]
    fetched = _now_utc()

    conn = dbmod.connect(path)
    try:
        dbmod.init_schema(conn)
        cur = conn.cursor()
        # Parent freshness row must exist before annotation rows (FK).
        cur.execute(
            """INSERT OR REPLACE INTO source_release
               (source, source_version, fetched_date, download_url, record_count,
                genome_build, origin, license, display_name)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (key, version, fetched, src.url, 0, src.genome_build, "update", src.license, src.name),
        )
        # Replace this source's rows in place; other sources untouched.
        cur.execute("DELETE FROM annotation WHERE source = ?", (key,))

        count = 0
        batch: list[tuple] = []
        insert_sql = (
            f"INSERT OR IGNORE INTO annotation ({','.join(_COLUMNS)}) "
            f"VALUES ({','.join('?' for _ in _COLUMNS)})"
        )
        for row in normalizer(dest, limit=limit):
            batch.append(_row_tuple(row, key, version, fetched))
            if len(batch) >= 5000:
                cur.executemany(insert_sql, batch)
                count += len(batch)
                batch.clear()
                _emit(progress, source=key, phase="index", message=f"{src.name}: {count:,} rows…")
        if batch:
            cur.executemany(insert_sql, batch)
            count += len(batch)
        # Report the ACTUAL stored row count (after unique-index dedup), not attempts.
        stored = cur.execute("SELECT COUNT(*) FROM annotation WHERE source = ?", (key,)).fetchone()[0]
        cur.execute(
            "UPDATE source_release SET record_count = ? WHERE source = ? AND source_version = ?",
            (stored, key, version),
        )
        count = stored
        conn.commit()
        conn.execute("ANALYZE")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # Clean up the (large) download; it contains no user data anyway.
    try:
        dest.unlink(missing_ok=True)
    except OSError:
        pass

    result = {"source": key, "name": src.name, "version": version, "record_count": count,
              "license": src.license, "ok": True}
    _emit(progress, source=key, phase="done", message=f"{src.name}: {count:,} annotations", **{"pct": 1.0})
    return result


def update_databases(keys: list[str] | None = None, *, limit: int | None = None,
                     progress: ProgressCB = None, db_path: Path | None = None) -> dict:
    """Update several sources with per-source graceful fallback, then write manifest."""
    keys = keys or list(SOURCES.keys())
    results = []
    for key in keys:
        try:
            results.append(update_source(key, limit=limit, progress=progress, db_path=db_path))
        except Exception as exc:  # keep previously-loaded rows intact; report + continue
            results.append({"source": key, "name": SOURCES[key].name, "ok": False, "error": str(exc)})
            _emit(progress, source=key, phase="error", message=f"{SOURCES[key].name} failed: {exc}")

    manifest = write_manifest(db_path=db_path)
    _emit(progress, source="*", phase="complete", message="Update complete")
    return {"results": results, "manifest": manifest}


def write_manifest(db_path: Path | None = None) -> dict:
    """Mirror source_release into data/manifest.json for the UI freshness panel."""
    path = db_path or config.DB_FILE
    sources_out = []
    if dbmod.db_exists_and_ready(path):
        conn = dbmod.connect(path, readonly=True)
        try:
            for r in conn.execute("SELECT * FROM source_release ORDER BY source"):
                sources_out.append(dict(r))
        finally:
            conn.close()
    manifest = {"generated_at": _now_utc(), "sources": sources_out}
    config.MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
