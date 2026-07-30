#!/usr/bin/env python3
"""Build-time helper: enrich the curated seed associations with
GRCh37/GRCh38 coordinates, forward-strand alleles, and strand-ambiguity flags
from the Ensembl REST API.

This is a ONE-TIME BUILD STEP. It contacts Ensembl (public reference data only —
never any user genotype) and writes the committed, reproducible seed artifact
``data/seed/associations.json`` that the app then uses fully offline.

Usage:
    python scripts/enrich_seed_coords.py            # fetch from Ensembl + write
    python scripts/enrich_seed_coords.py --offline  # rebuild text from base, no net;
                                                    # reuses existing coordinates

Either way the script refuses to write a seed with fewer coordinates than the one
already on disk — a partial Ensembl outage must not silently degrade the committed
artifact.

The curated biology (rsIDs, risk alleles, genotype interpretations, plain-language
summaries, disclaimers, strand rules) lives in ``data/seed/_curated_base.json`` and
is authored by hand — Ensembl only supplies coordinates/allele strings.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"
BASE_FILE = SEED_DIR / "_curated_base.json"
OUT_FILE = SEED_DIR / "associations.json"

VALID_CHROMS = {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}
COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}

ENSEMBL = {
    "GRCh38": "https://rest.ensembl.org/variation/homo_sapiens",
    "GRCh37": "https://grch37.rest.ensembl.org/variation/homo_sapiens",
}


def ensembl_batch(rsids: list[str], assembly: str) -> dict:
    """POST a batch of rsIDs to Ensembl; return {rsid: record}. Public data only."""
    body = json.dumps({"ids": rsids}).encode("utf-8")
    req = urllib.request.Request(
        ENSEMBL[assembly],
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:  # pragma: no cover - network
            wait = 2 ** attempt
            print(f"  Ensembl {assembly} attempt {attempt+1} failed ({exc}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Ensembl {assembly} unreachable after retries")


def pick_mapping(record: dict, assembly: str) -> dict | None:
    """Choose the canonical primary-assembly mapping (skip patches/haplotypes)."""
    for m in record.get("mappings", []):
        if m.get("assembly_name") == assembly and str(m.get("seq_region_name")) in VALID_CHROMS:
            return m
    return None


def forward_pair(assoc: dict) -> list[str]:
    """The two curated forward-strand alleles, derived from the genotype keys."""
    letters = set()
    for gt in assoc["genotypes"]:
        letters.update(gt.upper())
    return sorted(letters)


def is_ambiguous(pair: list[str]) -> bool:
    s = set(pair)
    return s == {"A", "T"} or s == {"C", "G"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="rebuild without contacting Ensembl")
    args = ap.parse_args()

    base = json.loads(BASE_FILE.read_text(encoding="utf-8"))
    assocs = base["associations"]
    rsids = [a["rsid"] for a in assocs]

    coords: dict[str, dict] = {}
    if args.offline:
        # --offline must PRESERVE coordinates already enriched into the committed
        # artifact. The base file carries none, so rebuilding from it alone silently
        # produced a coordinate-less seed and overwrote the real one.
        if OUT_FILE.exists():
            prev_assocs = json.loads(OUT_FILE.read_text(encoding="utf-8")).get("associations", [])
            for r in prev_assocs:
                coords[r["rsid"]] = {
                    "chrom": r.get("chrom"),
                    "pos_b37": r.get("pos_b37"),
                    "pos_b38": r.get("pos_b38"),
                    "allele_string": r.get("ensembl_allele_string"),
                }
            kept = sum(1 for c in coords.values() if c.get("chrom"))
            print(f"--offline: reusing coordinates for {kept} rsIDs from {OUT_FILE.name}")
        else:
            print(f"--offline: {OUT_FILE.name} does not exist, so there are no coordinates "
                  f"to reuse; output will have none.", file=sys.stderr)
    else:
        for assembly in ("GRCh37", "GRCh38"):
            print(f"Fetching {len(rsids)} rsIDs from Ensembl {assembly} ...")
            data = ensembl_batch(rsids, assembly)
            for rsid in rsids:
                rec = data.get(rsid)
                if not rec:
                    print(f"  ! Ensembl {assembly} returned nothing for {rsid}", file=sys.stderr)
                    continue
                m = pick_mapping(rec, assembly)
                if not m:
                    print(f"  ! No primary {assembly} mapping for {rsid}", file=sys.stderr)
                    continue
                c = coords.setdefault(rsid, {})
                c["chrom"] = str(m["seq_region_name"])
                c[f"pos_{'b37' if assembly == 'GRCh37' else 'b38'}"] = int(m["start"])
                c["allele_string"] = m.get("allele_string")
                c["ensembl_strand"] = m.get("strand")

    enriched = []
    for a in assocs:
        pair = forward_pair(a)
        c = coords.get(a["rsid"], {})
        row = {
            "rsid": a["rsid"],
            "gene": a["gene"],
            "trait": a["trait"],
            "trait_es": a.get("trait_es"),
            "category": a["category"],
            "sensitivity": base["category_sensitivity"].get(a["category"], "low"),
            "risk_allele": a["risk_allele"],
            "curated_build": a.get("build", "GRCh37"),
            "chrom": c.get("chrom"),
            "pos_b37": c.get("pos_b37"),
            "pos_b38": c.get("pos_b38"),
            "alleles_forward": "/".join(pair),
            "ensembl_allele_string": c.get("allele_string"),
            "ambiguous_strand": is_ambiguous(pair),
            "evidence": a["source"],
            "plain_summary": a["plain_summary"],
            "plain_summary_es": a.get("plain_summary_es"),
            # genotypes carry both `effect` (English) and `effect_es` per genotype.
            "genotypes": a["genotypes"],
        }
        enriched.append(row)

    missing = [r["rsid"] for r in enriched if not r["chrom"]]
    if missing:
        print(f"WARNING: {len(missing)} rsIDs missing coords: {missing}", file=sys.stderr)

    # Never regress the committed artifact. Whatever the cause — --offline with no prior
    # file, a partial Ensembl outage, a bad batch — overwriting an enriched seed with a
    # less-enriched one is always a mistake, so refuse rather than destroy.
    new_with_coords = len(enriched) - len(missing)
    if OUT_FILE.exists():
        prev_with_coords = sum(
            1 for r in json.loads(OUT_FILE.read_text(encoding="utf-8")).get("associations", [])
            if r.get("chrom")
        )
        if new_with_coords < prev_with_coords:
            print(f"ABORT: this run would drop coordinates from {prev_with_coords} to "
                  f"{new_with_coords} associations. Refusing to overwrite {OUT_FILE.name}.\n"
                  f"       Ensembl was probably unreachable or returned partial data — retry "
                  f"later. If you genuinely intend to rebuild a coordinate-less seed, delete "
                  f"{OUT_FILE.name} first.", file=sys.stderr)
            return 1

    out = {
        "schema_version": 1,
        "description": "Curated educational seed of well-replicated SNP-trait associations. "
                       "Interpretations are project-authored plain-language summaries, drafted "
                       "with AI assistance and not reviewed by a geneticist or clinician; each "
                       "names its source database (GWAS Catalog / ClinVar / PharmGKB) but carries "
                       "no per-association citation. Coordinates/alleles from Ensembl. "
                       "Redistributable (no PharmGKB data files are bundled).",
        "trait_categories": base["trait_categories"],
        "disclaimers": base["disclaimers"],
        "strand_rules_summary": base["strand_rules_summary"],
        "strand_rules_summary_es": base.get("strand_rules_summary_es"),
        "haplotypes": base["haplotypes"],
        "associations": enriched,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_FILE} with {len(enriched)} associations "
          f"({len(enriched) - len(missing)} with coordinates).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
