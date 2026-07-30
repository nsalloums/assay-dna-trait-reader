"""Deterministic synthetic test corpus (NO real human data, ever).

Uses snps' SyntheticSNPGenerator to emit vendor-format files with KNOWN injected
genotypes so every expected annotation is decided in advance. To keep goldens
deterministic we overwrite EVERY curated-seed rsID in each file (the generator
emits sequential rsIDs that collide with low-numbered real rsIDs), setting
non-injected seed rsIDs to a no-call so they never match.

Each fixture entry declares, per rsID: the genotype written to the file, and the
expected FORWARD-strand genotype the app should resolve to (or None = expect no
annotation: no-call, omitted, or ambiguous-withheld).
"""
from __future__ import annotations

import json
from pathlib import Path

from snps.io.generator import SyntheticSNPGenerator

ROOT = Path(__file__).resolve().parents[1]
SEED = json.loads((ROOT / "data" / "seed" / "associations.json").read_text(encoding="utf-8"))
SEED_BY_RSID = {a["rsid"]: a for a in SEED["associations"]}
HAP = {h["id"]: h for h in SEED["haplotypes"]}

WRITERS = {"23andme": "_write_snps_as_23andme", "ancestry": "_write_snps_as_ancestry",
           "ftdna": "_write_snps_as_ftdna"}

# fixture -> (vendor, build, [(rsid, written_genotype, expected_forward_or_None), ...])
FIXTURES: dict[str, tuple] = {
    "rich_b37_23andme": ("23andme", 37, [
        ("rs12913832", "GG", "GG"), ("rs1426654", "AA", "AA"), ("rs1805007", "TT", "TT"),
        ("rs12203592", "TT", "TT"), ("rs713598", "CC", "CC"), ("rs1726866", "AA", "AA"),
        ("rs17822931", "TT", "TT"), ("rs4988235", "AA", "AA"), ("rs762551", "AA", "AA"),
        ("rs671", "GG", "GG"), ("rs1815739", "TT", "TT"), ("rs4680", "AA", "AA"),
        ("rs10427255", "CC", "CC"),
    ]),
    "health_pharma_b37_23andme": ("23andme", 37, [
        ("rs1800562", "AA", "AA"), ("rs1799945", "CC", "CC"), ("rs1801133", "AA", "AA"),
        ("rs429358", "CC", "CC"), ("rs7412", "CC", "CC"), ("rs9939609", "AA", "AA"),
        ("rs7903146", "TT", "TT"), ("rs16969968", "AA", "AA"), ("rs9923231", "TT", "TT"),
        ("rs1799853", "CC", "CC"), ("rs1057910", "AA", "AA"), ("rs4244285", "AA", "AA"),
        ("rs12248560", "CC", "CC"), ("rs4149056", "CC", "CC"),
    ]),
    # Same rsIDs/genotypes as rich, but build 38 — annotations must be identical (match by rsID).
    "rich_b38_23andme": ("23andme", 38, [
        ("rs12913832", "GG", "GG"), ("rs1426654", "AA", "AA"), ("rs1805007", "TT", "TT"),
        ("rs12203592", "TT", "TT"), ("rs713598", "CC", "CC"), ("rs1726866", "AA", "AA"),
        ("rs17822931", "TT", "TT"), ("rs4988235", "AA", "AA"), ("rs762551", "AA", "AA"),
        ("rs671", "GG", "GG"), ("rs1815739", "TT", "TT"), ("rs4680", "AA", "AA"),
        ("rs10427255", "CC", "CC"),
    ]),
    # Minus-strand legacy file: non-ambiguous calls are the COMPLEMENT of the forward
    # pair (must auto-flip); ambiguous A/T & C/G calls must NOT be flipped (trust vendor).
    "legacy_minus_b37_23andme": ("23andme", 37, [
        ("rs9923231", "AA", "TT"),   # C/T non-ambig: A/A -> flip -> T/T (warfarin sensitive)
        ("rs1801133", "TT", "AA"),   # A/G non-ambig: T/T -> flip -> A/A (MTHFR 677TT)
        ("rs4988235", "TT", "AA"),   # A/G non-ambig: T/T -> flip -> A/A (lactase persistent)
        ("rs1800562", "TT", "AA"),   # A/G non-ambig: T/T -> flip -> A/A (C282Y homozygous)
        ("rs713598", "GG", "GG"),    # C/G AMBIGUOUS: must stay GG (taster), NOT flip to CC
        ("rs9939609", "TT", "TT"),   # A/T AMBIGUOUS: must stay TT, NOT flip to AA
    ]),
    # No-calls and low coverage: nothing should be annotated for these sites.
    "nocall_lowcov_b37_23andme": ("23andme", 37, [
        ("rs1815739", "--", None), ("rs671", "00", None), ("rs4680", "NN", None),
        # rs12913832, rs4988235, rs1800562 are intentionally OMITTED (not written).
    ]),
    # Format independence: rich genotypes in Ancestry + FTDNA layouts.
    "rich_b37_ancestry": ("ancestry", 37, [
        ("rs12913832", "GG", "GG"), ("rs4988235", "AA", "AA"), ("rs1815739", "TT", "TT"),
        ("rs671", "GG", "GG"), ("rs713598", "CC", "CC"), ("rs17822931", "TT", "TT"),
    ]),
    "rich_b37_ftdna": ("ftdna", 37, [
        ("rs12913832", "GG", "GG"), ("rs4988235", "AA", "AA"), ("rs1815739", "TT", "TT"),
        ("rs671", "GG", "GG"), ("rs713598", "CC", "CC"), ("rs17822931", "TT", "TT"),
    ]),
}

OMITTED = {"nocall_lowcov_b37_23andme": {"rs12913832", "rs4988235", "rs1800562"}}


def _pos(assoc: dict, build: int) -> int:
    p = assoc.get("pos_b38") if build == 38 else assoc.get("pos_b37")
    return int(p) if p else 1000


def write_fixture(name: str, outdir: Path) -> dict:
    vendor, build, injected = FIXTURES[name]
    gen = SyntheticSNPGenerator(build=build, seed=42)
    df = gen.generate_snps(num_snps=20000, inject_build_markers=True)

    injected_rsids = {r for r, _, _ in injected}
    omit = OMITTED.get(name, set())
    # Overwrite EVERY seed rsID: no-call by default (deterministic), unless injected/omitted.
    for rsid, a in SEED_BY_RSID.items():
        if rsid in injected_rsids or rsid in omit:
            continue
        df.loc[rsid] = [a["chrom"], _pos(a, build), "--"]
    for rsid, gt, _ in injected:
        a = SEED_BY_RSID[rsid]
        df.loc[rsid] = [a["chrom"], _pos(a, build), gt]

    ext = ".csv" if vendor == "ftdna" else ".txt"
    path = outdir / f"{name}{ext}"
    getattr(gen, WRITERS[vendor])(df, str(path))

    # Golden expectation from the seed interpretations for the expected forward genotypes.
    expected: dict[str, dict] = {}
    for rsid, _gt, fwd in injected:
        if fwd is None:
            continue
        a = SEED_BY_RSID[rsid]
        interp = a["genotypes"].get(fwd)
        if interp:
            expected[rsid] = {
                "genotype": fwd, "effect": interp["effect"], "magnitude": interp["magnitude"],
                "sensitivity": a["sensitivity"], "trait": a["trait"], "category": a["category"],
            }

    # APOE diplotype expectation, if both member SNPs are present.
    apoe = None
    fwd_map = {r: f for r, _, f in injected if f}
    hap = HAP["apoe_isoform"]
    members = [m for m in hap["member_rsids"]]
    if all(m in fwd_map for m in members):
        key = "|".join(fwd_map[m] for m in members)
        dip = hap["diplotypes"].get(key)
        if dip:
            apoe = dip["name"]

    return {"name": name, "path": str(path), "vendor": vendor, "build": build,
            "expected": expected, "apoe": apoe,
            "no_annotation_rsids": sorted({r for r, _, f in injected if f is None} | omit)}


def generate_all(outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    return {name: write_fixture(name, outdir) for name in FIXTURES}


if __name__ == "__main__":
    manifest = generate_all(ROOT / "tests" / "corpus")
    for name, m in manifest.items():
        print(f"{name:34} {m['vendor']:9} b{m['build']} "
              f"expected={len(m['expected'])} apoe={m['apoe']} "
              f"no-annot={len(m['no_annotation_rsids'])}")
