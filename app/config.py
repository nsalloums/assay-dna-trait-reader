"""Central configuration and filesystem paths.

Everything here is local. No secrets, no remote endpoints (annotation-source URLs
live only in ``app/db_update/sources.py``, the sole network-touching module).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
SCHEMA_FILE = DATA_DIR / "schema.sql"
SEED_FILE = SEED_DIR / "associations.json"          # committed, redistributable curated seed
DB_FILE = DATA_DIR / "annotations.db"               # built locally (gitignored)
MANIFEST_FILE = DATA_DIR / "manifest.json"          # freshness manifest the UI reads
DOWNLOAD_DIR = DATA_DIR / "downloads"               # transient source downloads (gitignored)

WEB_DIR = ROOT / "web"

# Schema version — bump when data/schema.sql changes in an incompatible way.
# v2 added bilingual (_es) text columns to annotation and haplotype_rule.
SCHEMA_VERSION = 2

# --- Server -----------------------------------------------------------------
# Loopback ONLY. Never bind 0.0.0.0 — the app must not be reachable off-device.
HOST = "127.0.0.1"
PORT = 8765

# --- Upload / session limits ------------------------------------------------
MAX_UPLOAD_BYTES = 96 * 1024 * 1024        # generous for large 23andMe/Ancestry files
MAX_DECOMPRESSED_BYTES = 512 * 1024 * 1024  # cap on inflated size (zip/gzip bomb guard)
SESSION_TTL_SECONDS = 30 * 60         # in-memory parsed genotypes expire after 30 min
SESSION_SWEEP_SECONDS = 60            # how often the TTL sweeper runs

# Genotype tokens that mean "no call" — dropped, never matched.
NO_CALL_TOKENS = frozenset({"--", "00", "NN", "DD", "II", "-", "", "..", "I", "D"})
