"""Build the local annotation DB from the committed curated seed (OFFLINE).

Imports no network client. Produces a fully-functional, offline annotation store
from ``data/seed/associations.json`` so the app works out-of-the-box with zero
network. The larger public sources are layered on later via ``update_databases``.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .. import config
from .. import db as dbmod

SEED_SOURCE = "curated_seed"
SEED_DISPLAY = "Curated educational seed"
SEED_LICENSE = (
    "Project MIT license. Interpretations are project-authored plain-language summaries, "
    "drafted with AI assistance and not reviewed by a geneticist or clinician. Each names "
    "its source database (GWAS Catalog, ClinVar, PharmGKB/CPIC) but carries no "
    "per-association citation. No third-party dataset files are redistributed in the seed."
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _other_allele(alleles_forward: str, risk_allele: str) -> str | None:
    bases = [b for b in alleles_forward.upper() if b in "ACGT"]
    others = [b for b in bases if b != risk_allele.upper()]
    return others[0] if others else None


def build_seed(db_path: Path | None = None, seed_file: Path | None = None) -> dict:
    """(Re)build the curated-seed rows into the annotation DB. Idempotent."""
    path = Path(db_path) if db_path else config.DB_FILE
    seed = json.loads((Path(seed_file) if seed_file else config.SEED_FILE).read_text(encoding="utf-8"))

    version = "2026-07 (curated)"
    fetched = _now_utc()

    conn = dbmod.connect(path)
    try:
        dbmod.init_schema(conn)
        cur = conn.cursor()
        # Replace seed rows in place (leave any updated public sources untouched).
        cur.execute("DELETE FROM annotation WHERE source = ?", (SEED_SOURCE,))
        cur.execute("DELETE FROM haplotype_rule WHERE source = ?", (SEED_SOURCE,))

        # Freshness ledger for the seed FIRST (annotation rows FK-reference it).
        cur.execute(
            """INSERT OR REPLACE INTO source_release
               (source, source_version, fetched_date, download_url, record_count,
                genome_build, origin, license, display_name)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (SEED_SOURCE, version, fetched, None, 0,
             "GRCh37", "seed", SEED_LICENSE, SEED_DISPLAY),
        )

        rows = []
        for a in seed["associations"]:
            rsid = a["rsid"].lower()
            risk = a["risk_allele"]
            ref = _other_allele(a["alleles_forward"], risk)
            for gt, meta in a["genotypes"].items():
                gt_sorted = "".join(sorted(gt.upper()))
                rows.append((
                    rsid, gt_sorted, a["gene"], a["trait"], a["category"], a["sensitivity"],
                    meta["effect"], meta.get("magnitude"), a["plain_summary"],
                    risk, ref, risk, "forward", int(bool(a["ambiguous_strand"])),
                    a.get("chrom"), a.get("pos_b37"), a.get("pos_b38"),
                    None, None, a.get("evidence"), SEED_SOURCE, version, fetched, None,
                ))
        cur.executemany(
            """INSERT OR IGNORE INTO annotation
               (rsid, genotype, gene, trait, category, sensitivity, effect_text, magnitude,
                plain_summary, risk_allele, ref_allele, alt_allele, orientation, ambiguous_strand,
                chrom, pos_b37, pos_b38, effect_size, confidence, evidence,
                source, source_version, fetched_date, citation)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )

        # Haplotype rules (APOE, …).
        for hap in seed.get("haplotypes", []):
            cur.execute(
                """INSERT OR REPLACE INTO haplotype_rule
                   (id, trait, gene, category, sensitivity, member_rsids, diplotypes,
                    plain_summary, evidence, source, source_version, fetched_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    hap["id"], hap["trait"], hap.get("gene"), hap["category"],
                    hap.get("sensitivity", "health"),
                    json.dumps([m.lower() for m in hap["member_rsids"]]),
                    json.dumps(hap["diplotypes"]),
                    hap.get("plain_summary"), hap.get("evidence"),
                    SEED_SOURCE, version, fetched,
                ),
            )

        # Update the seed ledger with the final record count.
        cur.execute(
            "UPDATE source_release SET record_count = ? WHERE source = ? AND source_version = ?",
            (len(rows), SEED_SOURCE, version),
        )
        conn.execute("ANALYZE")
        conn.commit()
    finally:
        conn.close()

    return {"source": SEED_SOURCE, "version": version, "annotation_rows": len(rows),
            "haplotypes": len(seed.get("haplotypes", [])), "db_path": str(path)}


if __name__ == "__main__":
    result = build_seed()
    print(json.dumps(result, indent=2))
