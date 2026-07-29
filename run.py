#!/usr/bin/env python3
"""One-command local launcher.

    python run.py

Starts the app on http://127.0.0.1:8765 (loopback only). On first run it builds
the offline curated-seed database automatically, so the app works immediately with
zero network. Run `python -m app.db_update update` once to enrich with the full
public sources (GWAS Catalog / ClinVar / PharmGKB) for offline use thereafter.
"""
from __future__ import annotations

import webbrowser

import uvicorn

from app import config
from app.core import security
from app.db import db_exists_and_ready
from app.db_update import build_seed


def main() -> None:
    security.assert_loopback(config.HOST)

    if not db_exists_and_ready():
        print("First run: building the offline curated-seed database…")
        info = build_seed.build_seed()
        print(f"  Seeded {info['annotation_rows']} annotations across the curated set.")

    url = f"http://{config.HOST}:{config.PORT}"
    print(f"\n  Local DNA Trait Extractor — {url}")
    print("  100% local · your DNA never leaves this machine · educational use only\n")
    with __import__("contextlib").suppress(Exception):
        webbrowser.open(url)

    # Single worker keeps the in-memory session store coherent.
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, workers=1, log_level="info")


if __name__ == "__main__":
    main()
