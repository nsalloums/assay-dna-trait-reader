"""Regression tests locking the fixes for the adversarial-review findings."""
from __future__ import annotations

import gzip

import pytest

from app import config
from app import db as dbmod
from app.core import parsing
from app.core.annotation import AnnotationStore
from app.db_update import build_seed


def _store_with_extra_rows(db_path):
    build_seed.build_seed(db_path=db_path)
    conn = dbmod.connect(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO source_release(source,source_version,fetched_date,record_count,"
        "genome_build,origin,display_name) VALUES('gwas_catalog','v1','2026-01-01',0,'GRCh38','update','GWAS')"
    )
    conn.execute(
        "INSERT OR REPLACE INTO source_release(source,source_version,fetched_date,record_count,"
        "genome_build,origin,display_name) VALUES('pharmgkb','v1','2026-01-01',0,'GRCh38','update','PharmGKB')"
    )
    # GWAS allele-level row (risk allele only, no ref/alt) — the finding-1 shape.
    conn.execute(
        "INSERT INTO annotation(rsid,category,sensitivity,risk_allele,trait,effect_text,"
        "source,source_version,fetched_date) VALUES('rs1421085','gwas_risk','health','A','BMI',"
        "'Associated with: BMI','gwas_catalog','v1','2026-01-01')"
    )
    # PharmGKB per-genotype row (genotype only, no ref/alt/risk) — the finding-2 shape.
    conn.execute(
        "INSERT INTO annotation(rsid,genotype,category,sensitivity,trait,effect_text,"
        "source,source_version,fetched_date) VALUES('rs3745274','GT','pharmacogenomics','health',"
        "'warfarin — Dosage','PGx text','pharmgkb','v1','2026-01-01')"
    )
    conn.commit()
    conn.close()
    return AnnotationStore.load(db_path)


def test_heterozygous_gwas_carrier_is_surfaced(tmp_path):
    """Finding 1: a het risk-allele carrier must be reported, not silently withheld."""
    store = _store_with_extra_rows(tmp_path / "db.sqlite")
    hits = [m for m in store.match({"rs1421085": "AG"}) if m["rsid"] == "rs1421085"]
    assert hits, "heterozygous GWAS carrier should be surfaced"
    assert hits[0]["zygosity"] == "heterozygous"
    # The carrier detail now lives in carrier_note (Spanish framing).
    assert "alelo A" in hits[0]["carrier_note"] and "heterocigoto" in hits[0]["carrier_note"]


def test_non_carrier_gwas_is_not_matched(tmp_path):
    """A user WITHOUT the risk allele must not be annotated."""
    store = _store_with_extra_rows(tmp_path / "db.sqlite")
    hits = [m for m in store.match({"rs1421085": "GG"}) if m["rsid"] == "rs1421085"]
    assert not hits


def test_pharmgkb_genotype_row_is_surfaced(tmp_path):
    """Finding 2: a standalone PharmGKB per-genotype row must match its genotype."""
    store = _store_with_extra_rows(tmp_path / "db.sqlite")
    hits = [m for m in store.match({"rs3745274": "GT"}) if m["rsid"] == "rs3745274"]
    assert hits and hits[0]["source"] == "pharmgkb"
    # A different genotype must NOT match the GT-specific row.
    assert not [m for m in store.match({"rs3745274": "GG"}) if m["rsid"] == "rs3745274"]


def test_gzip_bomb_rejected(monkeypatch):
    """Finding 3: decompression is capped (bounded read rejects over-large inflate)."""
    monkeypatch.setattr(config, "MAX_DECOMPRESSED_BYTES", 100)
    payload = gzip.compress(b"X" * 50_000)
    with pytest.raises(ValueError):
        parsing._decompress_if_needed(payload, "bomb.gz")


def test_redirect_guard_blocks_offhost():
    """Finding 8: a redirect to a non-allowlisted host is refused."""
    import urllib.request
    from app.db_update.sources import _GuardedRedirectHandler
    h = _GuardedRedirectHandler()
    req = urllib.request.Request("https://ftp.ebi.ac.uk/x")
    with pytest.raises(PermissionError):
        h.redirect_request(req, None, 302, "Found", {}, "https://evil.example.com/steal")


def test_oversized_upload_rejected_by_content_length(monkeypatch):
    """Findings 9/13: oversized upload rejected via Content-Length before full read."""
    from starlette.testclient import TestClient
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 50)
    from app.main import app
    with TestClient(app) as client:
        r = client.post("/api/parse", content=b"X" * 500,
                        headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 413
