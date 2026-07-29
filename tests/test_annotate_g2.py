"""G2 — Annotate: parsed genotypes join to the (seed) store and every expected
association is surfaced exactly, with correct strand handling and provenance.
Golden expectations come from the corpus manifest (derived from the seed).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core import parsing
from tests.conftest import haplotype_matches, seed_matches

ALL_FIXTURES = [
    "rich_b37_23andme", "health_pharma_b37_23andme", "rich_b38_23andme",
    "legacy_minus_b37_23andme", "nocall_lowcov_b37_23andme",
    "rich_b37_ancestry", "rich_b37_ftdna",
]


def _genotypes(path: str) -> dict:
    return parsing.parse_bytes(Path(path).read_bytes()).genotypes


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_expected_annotations_exact(corpus, store, name):
    m = corpus[name]
    matches = seed_matches(store, _genotypes(m["path"]))

    # Every expected association is present with the correct genotype/effect/sensitivity.
    for rsid, exp in m["expected"].items():
        assert rsid in matches, f"{name}: missing expected annotation {rsid}"
        got = matches[rsid]
        assert got["resolved_genotype"] == exp["genotype"], f"{name}:{rsid} genotype"
        assert got["effect_text"] == exp["effect"], f"{name}:{rsid} effect text"
        assert got["magnitude"] == exp["magnitude"], f"{name}:{rsid} magnitude"
        assert got["is_health"] == (exp["sensitivity"] == "health"), f"{name}:{rsid} sensitivity"
        # provenance present
        assert got["source"] and got["source_version"] and got["source_date"]

    # No annotation for no-call / omitted / ambiguous-withheld sites.
    for rsid in m["no_annotation_rsids"]:
        assert rsid not in matches, f"{name}: {rsid} should NOT be annotated"


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_no_false_positives(corpus, store, name):
    """Only expected rsIDs surface as curated-seed genotype hits (no extras)."""
    m = corpus[name]
    matches = seed_matches(store, _genotypes(m["path"]))
    assert set(matches.keys()) == set(m["expected"].keys()), (
        f"{name}: surfaced {set(matches)} but expected {set(m['expected'])}"
    )


def test_apoe_diplotype_fires(corpus, store):
    m = corpus["health_pharma_b37_23andme"]
    haps = haplotype_matches(store, _genotypes(m["path"]))
    assert any(h["resolved_genotype"] == m["apoe"] for h in haps), "APOE ε4/ε4 diplotype expected"
    apoe = next(h for h in haps if h["resolved_genotype"] == m["apoe"])
    assert apoe["is_health"] and "Alzheimer" in apoe["trait"]


def test_build37_and_build38_identical_annotations(corpus, store):
    """Matching is by rsID, so identical genotypes on b37 vs b38 give identical results."""
    a = seed_matches(store, _genotypes(corpus["rich_b37_23andme"]["path"]))
    b = seed_matches(store, _genotypes(corpus["rich_b38_23andme"]["path"]))
    assert {k: v["effect_text"] for k, v in a.items()} == {k: v["effect_text"] for k, v in b.items()}


def test_minus_strand_flips_and_ambiguous_kept(corpus, store):
    m = corpus["legacy_minus_b37_23andme"]
    matches = seed_matches(store, _genotypes(m["path"]))
    # Non-ambiguous minus-strand calls were complement-flipped.
    assert matches["rs9923231"]["resolved_genotype"] == "TT" and matches["rs9923231"]["flipped"]
    assert matches["rs4988235"]["resolved_genotype"] == "AA" and matches["rs4988235"]["flipped"]
    assert matches["rs1800562"]["resolved_genotype"] == "AA" and matches["rs1800562"]["flipped"]
    # Ambiguous palindromes were NOT flipped (trusted as written).
    assert matches["rs713598"]["resolved_genotype"] == "GG" and not matches["rs713598"]["flipped"]
    assert matches["rs9939609"]["resolved_genotype"] == "TT" and not matches["rs9939609"]["flipped"]


def test_format_independence(corpus, store):
    """Same injected genotypes surface identically across 23andMe/Ancestry/FTDNA."""
    ref = seed_matches(store, _genotypes(corpus["rich_b37_ancestry"]["path"]))
    ft = seed_matches(store, _genotypes(corpus["rich_b37_ftdna"]["path"]))
    assert {k: v["effect_text"] for k, v in ref.items()} == {k: v["effect_text"] for k, v in ft.items()}
    assert len(ref) == len(corpus["rich_b37_ancestry"]["expected"])
