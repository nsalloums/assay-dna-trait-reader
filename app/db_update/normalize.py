"""Normalize downloaded public sources into the unified annotation schema.

Pure local transforms — this module imports no network client. Each function
streams its (potentially very large) input and yields annotation-row dicts keyed
by rsID, filtered to single-rsID variants for the MVP.
"""
from __future__ import annotations

import csv
import gzip
import io
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterator

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

RS_RE = re.compile(r"^rs\d+$")
_ACGT = frozenset("ACGT")


def _blank_row() -> dict:
    return {
        "rsid": None, "genotype": None, "gene": None, "trait": None, "category": None,
        "sensitivity": "low", "effect_text": None, "magnitude": None, "plain_summary": None,
        "risk_allele": None, "ref_allele": None, "alt_allele": None, "orientation": "forward",
        "ambiguous_strand": 0, "chrom": None, "pos_b37": None, "pos_b38": None,
        "effect_size": None, "confidence": None, "evidence": None, "citation": None,
    }


def _is_ambiguous(a: str | None, b: str | None) -> int:
    if not a or not b:
        return 0
    s = {a.upper(), b.upper()}
    return 1 if s in ({"A", "T"}, {"C", "G"}) else 0


# --------------------------------------------------------------------------- GWAS
def normalize_gwas(zip_path: Path, limit: int | None = None) -> Iterator[dict]:
    """Yield GWAS Catalog association rows (single-rsID, known risk allele)."""
    with zipfile.ZipFile(zip_path) as zf:
        member = next((n for n in zf.namelist() if n.endswith(".tsv")), None)
        if member is None:
            return
        with zf.open(member) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text, delimiter="\t")
            emitted = 0
            for r in reader:
                snps = (r.get("SNPS") or "").strip()
                if not RS_RE.match(snps):
                    continue
                strongest = (r.get("STRONGEST SNP-RISK ALLELE") or "").strip()
                risk = strongest.rsplit("-", 1)[-1].strip().upper() if "-" in strongest else ""
                if risk not in _ACGT:  # '?' or non-SNP risk allele -> skip
                    continue
                trait = (r.get("DISEASE/TRAIT") or r.get("MAPPED_TRAIT") or "").strip()
                if not trait:
                    continue
                pval = (r.get("P-VALUE") or "").strip()
                orbeta = (r.get("OR or BETA") or "").strip()
                try:
                    p = float(pval) if pval else 1.0
                except ValueError:
                    p = 1.0
                row = _blank_row()
                row.update(
                    rsid=snps.lower(),
                    category="gwas_risk",
                    # Conservative: GWAS Catalog traits are predominantly diseases/
                    # phenotypes, so gate them behind the health disclaimer.
                    sensitivity="health",
                    gene=(r.get("MAPPED_GENE") or r.get("REPORTED GENE(S)") or "").strip() or None,
                    trait=trait,
                    risk_allele=risk,
                    effect_text=f"Associated with: {trait}",
                    effect_size=(f"OR/BETA={orbeta}; " if orbeta else "") + (f"p={pval}" if pval else ""),
                    confidence="genome-wide significant" if p < 5e-8 else "suggestive",
                    magnitude=2.0 if p < 5e-8 else 1.0,
                    chrom=(r.get("CHR_ID") or "").strip() or None,
                    pos_b38=_int_or_none((r.get("CHR_POS") or "").strip()),
                    evidence="GWAS Catalog",
                    citation=(r.get("PUBMEDID") or "").strip() or None,
                )
                yield row
                emitted += 1
                if limit and emitted >= limit:
                    return


# ------------------------------------------------------------------------ ClinVar
_STAR = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, single submitter": 1,
    "criteria provided, conflicting classifications": 1,
    "criteria provided, conflicting interpretations": 1,
    "no assertion criteria provided": 0,
    "no classification provided": 0,
    "no classifications from unflagged records": 0,
}


def _clinvar_stars(review_status: str) -> str:
    stars = _STAR.get((review_status or "").strip().lower(), 0)
    return f"{stars}★ {review_status}".strip()


def normalize_clinvar(gz_path: Path, build: str = "GRCh38", limit: int | None = None) -> Iterator[dict]:
    """Yield ClinVar rows for a single assembly, single-rsID, with a real rsID."""
    with gzip.open(gz_path, "rt", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        emitted = 0
        for r in reader:
            if (r.get("Assembly") or "").strip() != build:
                continue
            rsnum = (r.get("RS# (dbSNP)") or r.get("RS# (dbSNP)".replace(" ", "")) or "-1").strip()
            if not rsnum or rsnum == "-1":
                continue
            sig = (r.get("ClinicalSignificance") or "").strip()
            if not sig:
                continue
            ref = (r.get("ReferenceAlleleVCF") or "").strip().upper()
            alt = (r.get("AlternateAlleleVCF") or "").strip().upper()
            # Consumer arrays genotype SNVs only. Skip indels/MNVs: a multi-base alt
            # like 'AT' would otherwise spuriously "carrier-match" an unrelated SNP
            # call (set('AT') & set('AG') = {'A'}).
            if not (len(ref) == 1 and len(alt) == 1 and ref in _ACGT and alt in _ACGT):
                continue
            pos = _int_or_none((r.get("PositionVCF") or r.get("Start") or "").strip())
            row = _blank_row()
            row.update(
                rsid=f"rs{rsnum}",
                category="clinical_significance",
                sensitivity="health",
                gene=(r.get("GeneSymbol") or "").strip() or None,
                trait=(r.get("PhenotypeList") or "").strip() or None,
                effect_text=f"ClinVar clinical significance: {sig}",
                risk_allele=alt,
                ref_allele=ref,
                alt_allele=alt,
                ambiguous_strand=_is_ambiguous(ref, alt),
                chrom=(r.get("Chromosome") or "").strip() or None,
                pos_b38=pos if build == "GRCh38" else None,
                pos_b37=pos if build == "GRCh37" else None,
                confidence=_clinvar_stars(r.get("ReviewStatus") or ""),
                magnitude=_clinvar_magnitude(sig),
                evidence="ClinVar",
                citation=(r.get("RCVaccession") or "").strip() or None,
            )
            yield row
            emitted += 1
            if limit and emitted >= limit:
                return


def _clinvar_magnitude(sig: str) -> float:
    s = sig.lower()
    if "pathogenic" in s and "likely" not in s and "conflict" not in s:
        return 3.0
    if "likely pathogenic" in s:
        return 2.5
    if "risk" in s or "association" in s:
        return 2.0
    if "benign" in s:
        return 0.5
    return 1.0


# ----------------------------------------------------------------------- PharmGKB
def normalize_pharmgkb(zip_path: Path, limit: int | None = None) -> Iterator[dict]:
    """Yield PharmGKB per-genotype rows by joining clinical_ann_alleles to
    clinical_annotations on Clinical Annotation ID. Single-rsID variants only."""
    with zipfile.ZipFile(zip_path) as zf:
        names = {Path(n).name: n for n in zf.namelist()}
        ann_name = names.get("clinical_annotations.tsv")
        alleles_name = names.get("clinical_ann_alleles.tsv")
        if not ann_name or not alleles_name:
            return

        anns: dict[str, dict] = {}
        with zf.open(ann_name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"), delimiter="\t")
            for r in reader:
                cid = (r.get("Clinical Annotation ID") or "").strip()
                if cid:
                    anns[cid] = r

        with zf.open(alleles_name) as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"), delimiter="\t")
            emitted = 0
            for r in reader:
                cid = (r.get("Clinical Annotation ID") or "").strip()
                ann = anns.get(cid)
                if not ann:
                    continue
                variant = (ann.get("Variant/Haplotypes") or "").strip()
                if not RS_RE.match(variant):  # single-rsID only (skip star-allele haplotypes)
                    continue
                genotype = (r.get("Genotype/Allele") or "").strip()
                gt_norm = "".join(sorted(genotype.upper())) if genotype and set(genotype.upper()) <= _ACGT and len(genotype) <= 2 else None
                text = (r.get("Annotation Text") or "").strip()
                drugs = (ann.get("Drug(s)") or "").strip()
                phenotype = (ann.get("Phenotype Category") or "").strip()
                row = _blank_row()
                row.update(
                    rsid=variant.lower(),
                    genotype=gt_norm,
                    category="pharmacogenomics",
                    sensitivity="health",
                    gene=(ann.get("Gene") or "").strip() or None,
                    trait=(f"{drugs} — {phenotype}".strip(" —") or "Drug response") if (drugs or phenotype) else "Drug response",
                    effect_text=text or f"PharmGKB annotation for {variant} {genotype}".strip(),
                    confidence=(ann.get("Level of Evidence") or "").strip() or None,
                    magnitude=2.0,
                    evidence="PharmGKB (CC BY-SA 4.0)",
                    citation=cid or None,
                )
                yield row
                emitted += 1
                if limit and emitted >= limit:
                    return


def _int_or_none(v: str) -> int | None:
    try:
        return int(v)
    except (ValueError, TypeError):
        return None
