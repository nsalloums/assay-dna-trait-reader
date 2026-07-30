"""ClinVar normalizer test against a tiny crafted variant_summary fixture.

Avoids the 440 MB live download while proving the parser is correct: right
assembly filter, rsID handling (skip RS#=-1), ref/alt, significance, stars.
"""
from __future__ import annotations

import gzip
from pathlib import Path

from app.db_update.normalize import normalize_clinvar

COLUMNS = [
    "AlleleID", "Type", "Name", "GeneID", "GeneSymbol", "HGNC_ID", "ClinicalSignificance",
    "ClinSigSimple", "LastEvaluated", "RS# (dbSNP)", "nsv/esv (dbVar)", "RCVaccession",
    "PhenotypeIDs", "PhenotypeList", "Origin", "OriginSimple", "Assembly",
    "ChromosomeAccession", "Chromosome", "Start", "Stop", "ReferenceAllele", "AlternateAllele",
    "Cytogenetic", "ReviewStatus", "NumberSubmitters", "Guidelines", "TestedInGTR", "OtherIDs",
    "SubmitterCategories", "VariationID", "PositionVCF", "ReferenceAlleleVCF", "AlternateAlleleVCF",
]


def _row(**over) -> list[str]:
    base = {c: "" for c in COLUMNS}
    base.update(over)
    return [base[c] for c in COLUMNS]


def _make_fixture(path: Path) -> None:
    rows = [
        COLUMNS,
        # keep: GRCh38, has rsID, pathogenic, expert-panel (3 stars)
        _row(**{"RS# (dbSNP)": "1800562", "GeneSymbol": "HFE", "ClinicalSignificance": "Pathogenic",
                "Assembly": "GRCh38", "Chromosome": "6", "PositionVCF": "26090951",
                "ReferenceAlleleVCF": "G", "AlternateAlleleVCF": "A", "PhenotypeList": "Hemochromatosis",
                "ReviewStatus": "reviewed by expert panel", "RCVaccession": "RCV000000001"}),
        # skip: GRCh37 duplicate of a variant (wrong assembly)
        _row(**{"RS# (dbSNP)": "1800562", "ClinicalSignificance": "Pathogenic", "Assembly": "GRCh37",
                "Chromosome": "6", "PositionVCF": "26093141", "ReferenceAlleleVCF": "G",
                "AlternateAlleleVCF": "A", "ReviewStatus": "reviewed by expert panel"}),
        # skip: no rsID (RS# = -1)
        _row(**{"RS# (dbSNP)": "-1", "ClinicalSignificance": "Benign", "Assembly": "GRCh38",
                "Chromosome": "1", "PositionVCF": "100", "ReferenceAlleleVCF": "C",
                "AlternateAlleleVCF": "T"}),
        # keep: benign, single submitter (1 star)
        _row(**{"RS# (dbSNP)": "1801133", "GeneSymbol": "MTHFR", "ClinicalSignificance": "Benign",
                "Assembly": "GRCh38", "Chromosome": "1", "PositionVCF": "11796321",
                "ReferenceAlleleVCF": "G", "AlternateAlleleVCF": "A", "PhenotypeList": "not specified",
                "ReviewStatus": "criteria provided, single submitter", "RCVaccession": "RCV000000002"}),
        # skip: indel (multi-base alt) must NOT enter the SNP carrier-match path
        _row(**{"RS# (dbSNP)": "9999999", "ClinicalSignificance": "Pathogenic", "Assembly": "GRCh38",
                "Chromosome": "3", "PositionVCF": "500", "ReferenceAlleleVCF": "A",
                "AlternateAlleleVCF": "AT", "ReviewStatus": "criteria provided, single submitter"}),
    ]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        for r in rows:
            fh.write("\t".join(r) + "\n")


def test_normalize_clinvar(tmp_path):
    fixture = tmp_path / "variant_summary.txt.gz"
    _make_fixture(fixture)
    out = {r["rsid"]: r for r in normalize_clinvar(fixture, build="GRCh38")}

    assert set(out) == {"rs1800562", "rs1801133"}, "wrong assembly / RS#=-1 rows must be skipped"

    hfe = out["rs1800562"]
    assert hfe["category"] == "clinical_significance"
    assert hfe["sensitivity"] == "health"
    assert hfe["risk_allele"] == "A" and hfe["ref_allele"] == "G"
    assert "Pathogenic" in hfe["effect_text"]
    assert hfe["confidence"].startswith("3★")
    assert hfe["citation"] == "RCV000000001"
    assert hfe["pos_b38"] == 26090951

    mthfr = out["rs1801133"]
    assert mthfr["confidence"].startswith("1★")
    assert "Benign" in mthfr["effect_text"]
