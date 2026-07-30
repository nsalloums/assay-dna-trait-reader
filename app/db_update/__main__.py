"""CLI for building/refreshing the local annotation store.

    python -m app.db_update seed                 # build the offline curated seed DB
    python -m app.db_update update               # download + ingest all public sources
    python -m app.db_update update --sources pharmgkb,gwas_catalog --limit 20000
    python -m app.db_update status               # show freshness

Only ``update`` touches the network (public annotation DBs only; zero user data).
"""
from __future__ import annotations

import argparse
import json
import sys

from . import build_seed as seed_mod
from . import update as update_mod


def _progress(event: dict) -> None:
    phase = event.get("phase", "")
    if phase in {"download"} and "pct" in event:
        return  # too chatty for the CLI
    msg = event.get("message") or f"{event.get('source')}: {phase}"
    print(f"  {msg}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="app.db_update")
    sub = ap.add_subparsers(dest="cmd", required=False)

    sub.add_parser("seed", help="Build the offline curated seed DB")

    up = sub.add_parser("update", help="Download + ingest public annotation sources")
    up.add_argument("--sources", help="comma-separated: gwas_catalog,clinvar,pharmgkb")
    up.add_argument("--limit", type=int, default=None, help="max rows per source (testing)")

    sub.add_parser("status", help="Show freshness manifest")

    args = ap.parse_args(argv)
    cmd = args.cmd or "seed"

    if cmd == "seed":
        result = seed_mod.build_seed()
        update_mod.write_manifest()
        print(json.dumps(result, indent=2))
        return 0

    if cmd == "update":
        # Ensure a seed exists so the DB is never empty even if downloads fail.
        from .. import db as dbmod
        if not dbmod.db_exists_and_ready():
            seed_mod.build_seed()
        keys = args.sources.split(",") if args.sources else None
        result = update_mod.update_databases(keys=keys, limit=args.limit, progress=_progress)
        summary = [{k: r.get(k) for k in ("source", "record_count", "ok", "error")}
                   for r in result["results"]]
        print(json.dumps({"results": summary}, indent=2))
        return 0

    if cmd == "status":
        manifest = update_mod.write_manifest()
        print(json.dumps(manifest, indent=2))
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
