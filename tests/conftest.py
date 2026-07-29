"""Shared pytest fixtures.

The annotation store under test is pinned to a SEED-ONLY database built in a temp
dir, so golden assertions are deterministic and independent of any live GWAS/
ClinVar/PharmGKB freshness. All test inputs are synthetic (no real human data).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.annotation import AnnotationStore
from app.db_update import build_seed
from tests import make_corpus


@pytest.fixture(scope="session")
def seed_db(tmp_path_factory) -> Path:
    db = tmp_path_factory.mktemp("annodb") / "seed_only.db"
    build_seed.build_seed(db_path=db)
    return db


@pytest.fixture(scope="session")
def store(seed_db) -> AnnotationStore:
    return AnnotationStore.load(seed_db)


@pytest.fixture(scope="session")
def corpus(tmp_path_factory) -> dict:
    outdir = tmp_path_factory.mktemp("corpus")
    return make_corpus.generate_all(outdir)


def seed_matches(store: AnnotationStore, genotypes: dict) -> dict:
    """{rsid: match} for curated-seed, genotype-specific hits only."""
    out = {}
    for m in store.match(genotypes):
        if m["source"] == "curated_seed" and not m.get("is_haplotype"):
            out[m["rsid"]] = m
    return out


def haplotype_matches(store: AnnotationStore, genotypes: dict) -> list:
    return [m for m in store.match(genotypes) if m.get("is_haplotype")]
