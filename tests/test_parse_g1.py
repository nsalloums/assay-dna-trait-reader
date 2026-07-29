"""G1 — Parse: every supported synthetic file parses, build is detected, strand
is normalized, no-calls are dropped. Uses only synthetic data.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core import parsing
from app.core.strand import StrandResult, forward_allele_set, normalize_call, to_forward_strand

VENDOR_MARKERS = {"23andme": "23andMe", "ancestry": "AncestryDNA", "ftdna": "FTDNA"}


@pytest.mark.parametrize("name", [
    "rich_b37_23andme", "health_pharma_b37_23andme", "rich_b38_23andme",
    "legacy_minus_b37_23andme", "nocall_lowcov_b37_23andme",
    "rich_b37_ancestry", "rich_b37_ftdna",
])
def test_parses_and_detects_vendor_and_build(corpus, name):
    m = corpus[name]
    raw = Path(m["path"]).read_bytes()
    genome = parsing.parse_bytes(raw, filename=Path(m["path"]).name)
    assert genome.snp_count > 1000
    assert VENDOR_MARKERS[m["vendor"]].lower() in genome.vendor.lower()
    # build markers were injected -> build detected and correct
    assert genome.build_detected, f"build not detected for {name}"
    assert genome.build == m["build"], f"expected build {m['build']}, got {genome.build}"


def test_nocalls_are_dropped(corpus):
    """'--', '00', 'NN' must not appear in the parsed genotype map."""
    m = corpus["nocall_lowcov_b37_23andme"]
    genome = parsing.parse_bytes(Path(m["path"]).read_bytes())
    for rsid in ("rs1815739", "rs671", "rs4680"):
        assert rsid not in genome.genotypes, f"{rsid} no-call should have been dropped"
    # Omitted sites are simply absent.
    for rsid in ("rs12913832", "rs4988235", "rs1800562"):
        assert rsid not in genome.genotypes


def test_normalize_call_sorts_and_filters():
    assert normalize_call("GA") == "AG"
    assert normalize_call("gg") == "GG"
    assert normalize_call("--") is None
    assert normalize_call("00") is None
    assert normalize_call("NN") is None
    assert normalize_call("DI") is None      # indel -> not a SNP call
    assert normalize_call("A") == "A"        # haploid


def test_strand_forward_kept_when_already_forward():
    r = to_forward_strand("AG", forward_allele_set("A/G"), ambiguous=False)
    assert r.genotype == "AG" and not r.flipped and not r.withheld


def test_strand_minus_is_complement_flipped():
    # forward pair C/T; vendor 'AA' (minus) -> must flip to 'TT'
    r = to_forward_strand("AA", forward_allele_set("C/T"), ambiguous=False)
    assert r.genotype == "TT" and r.flipped and not r.withheld


def test_strand_ambiguous_is_never_flipped():
    # palindromic C/G: 'GG' must be trusted as-is (no complement flip)
    r = to_forward_strand("GG", forward_allele_set("C/G"), ambiguous=True)
    assert r.genotype == "GG" and not r.flipped
    # A/T palindrome likewise
    r2 = to_forward_strand("TT", forward_allele_set("A/T"), ambiguous=True)
    assert r2.genotype == "TT" and not r2.flipped


def test_strand_mismatch_withheld():
    # 'AC' on an A/G variant fits neither the forward pair {A,G} nor its complement
    # {T,C}, so it cannot be resolved and must be withheld (not guessed).
    r = to_forward_strand("AC", forward_allele_set("A/G"), ambiguous=False)
    assert r.genotype is None and r.withheld
