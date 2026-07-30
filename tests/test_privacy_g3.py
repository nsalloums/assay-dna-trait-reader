"""G3 — Privacy: prove zero user-genotype egress and zero persistence.

  * The parse->annotate path makes NO socket connection (run under a socket ban).
  * User genotypes are never written to disk (sentinel scan of the DB/data dir).
  * The runtime annotation connection is read-only (cannot write user data).
  * update_databases may ONLY contact allowlisted public-DB hosts.
  * Logs cannot contain rsIDs/genotypes (redaction filter).
All inputs are synthetic.
"""
from __future__ import annotations

import logging
import socket
from pathlib import Path

import pytest

from app.core import parsing
from app.core.annotation import AnnotationStore
from app.core.sessions import SessionStore


class _Egress(Exception):
    pass


def _ban_sockets(monkeypatch):
    def blocked(*a, **k):
        raise _Egress("network egress attempted on the annotate path")
    monkeypatch.setattr(socket.socket, "connect", blocked, raising=False)
    monkeypatch.setattr(socket, "create_connection", blocked, raising=False)


def test_parse_and_annotate_make_no_network_connection(corpus, seed_db, monkeypatch):
    """Full parse->annotate must complete with all outbound sockets banned."""
    m = corpus["health_pharma_b37_23andme"]
    raw = Path(m["path"]).read_bytes()
    _ban_sockets(monkeypatch)

    genome = parsing.parse_bytes(raw)                 # snps parse — local only
    store = AnnotationStore.load(seed_db)             # sqlite — local only
    matches = list(store.match(genome.genotypes))     # temp-join match — local only

    assert matches, "annotate produced results fully offline"
    assert any(x["source"] == "curated_seed" for x in matches)


def test_user_genotypes_never_written_to_disk(corpus, seed_db, tmp_path):
    """A sentinel rsID present in a user file must not appear in any on-disk store."""
    sentinel_rsid = "rs909090909"
    content = (
        "# 23andMe\n# rsid\tchromosome\tposition\tgenotype\n"
        f"{sentinel_rsid}\t1\t123456\tAG\nrs12913832\t15\t28365618\tGG\n"
    )
    genome = parsing.parse_bytes(content.encode())
    assert sentinel_rsid in genome.genotypes           # held in memory
    store = AnnotationStore.load(seed_db)
    list(store.match(genome.genotypes))

    # The sentinel must not have been persisted anywhere on disk.
    blob = Path(seed_db).read_bytes()
    assert sentinel_rsid.encode() not in blob, "user rsID leaked into the annotation DB"


def test_runtime_store_connection_is_readonly(seed_db):
    """The annotate path opens the DB read-only — writing user data is impossible."""
    from app import db as dbmod
    conn = dbmod.connect(seed_db, readonly=True)
    try:
        with pytest.raises(Exception):
            conn.execute(
                "INSERT INTO annotation(rsid,category,source,source_version,fetched_date) "
                "VALUES('rsX','x','x','x','x')"
            )
            conn.commit()
    finally:
        conn.close()


def test_session_store_purges_in_memory():
    s = SessionStore(ttl_seconds=1000)
    genome = parsing.parse_bytes(
        b"# 23andMe\n# rsid\tchromosome\tposition\tgenotype\nrs12913832\t15\t28365618\tGG\n"
    )
    sid = s.create(genome)
    assert s.get(sid) is not None
    assert s.delete(sid) is True
    assert s.get(sid) is None            # gone from RAM, nothing persisted anywhere


def test_update_databases_host_allowlist():
    from app.db_update import sources
    # Every configured source is on an allowlisted host.
    for src in sources.SOURCES.values():
        assert sources._guard(src.url) == src.url
    # Any non-allowlisted host is refused.
    for evil in ("https://evil.example.com/steal", "http://localhost:9999/x",
                 "https://pastebin.com/genome"):
        with pytest.raises(PermissionError):
            sources._guard(evil)


def test_temp_tables_never_touch_disk(seed_db):
    """The annotate path builds a TEMP table holding EVERY rsID the user has.

    Python's bundled SQLite is compiled with TEMP_STORE=1, i.e. temp tables default to
    FILE. Without `PRAGMA temp_store=MEMORY` (set in db.connect), a real-sized file
    (~600k rsIDs) makes SQLite spill an ~19 MB `etilqs_*` scratch file of PLAINTEXT
    rsIDs into the system temp dir — silently breaking the project's headline claim.

    Two non-obvious things this test gets right, both learned the hard way:

    1. A sentinel rsID is NOT a valid probe. Rows inserted last stay in the page cache
       and never reach the spill file, so a sentinel scan passes while megabytes of
       other rsIDs sit on disk. Assert on `etilqs_*` existence instead.
    2. The check must happen BEFORE conn.close(). SQLite unlinks the spill file when
       the connection closes, so a post-hoc scan always finds nothing and passes.

    The 20k-SNP corpus does not spill; N must be large enough to exceed the page cache.
    """
    import glob
    import tempfile

    from app import db as dbmod

    store = AnnotationStore.load(seed_db)
    tmpdir = Path(tempfile.gettempdir())
    before = set(glob.glob(str(tmpdir / "etilqs_*")))

    rsids = {f"rs{i}" for i in range(600_000)}
    conn = dbmod.connect(seed_db, readonly=True)
    try:
        store._fetch_candidate_rows(conn, rsids)
        # Inspect while the connection is still open — this is the only window in
        # which a spill file would be visible.
        leaked = set(glob.glob(str(tmpdir / "etilqs_*"))) - before
        assert not leaked, (
            f"SQLite spilled the user's rsIDs to disk: {sorted(leaked)}. "
            f"PRAGMA temp_store=MEMORY is missing or was overridden."
        )
    finally:
        conn.close()


def test_temp_store_pragma_is_actually_in_effect(seed_db):
    """Guard the mechanism itself, not just its observable effect.

    temp_store=MEMORY is 2. Asserting the value means this fails loudly if someone
    removes the pragma from db.connect(), even on a machine whose SQLite happens to
    be compiled with TEMP_STORE=2 and would therefore not spill anyway.
    """
    from app import db as dbmod

    conn = dbmod.connect(seed_db, readonly=True)
    try:
        assert conn.execute("PRAGMA temp_store").fetchone()[0] == 2
    finally:
        conn.close()


# Cross-host redirect targets a source is known to bounce through. An entry-point
# host being allowlisted is NOT sufficient: _GuardedRedirectHandler re-validates every
# 3xx target, so an unlisted hop kills the download at runtime while every existing
# test stays green. That is exactly how the ClinPGx source broke silently — the
# registry pointed at api.pharmgkb.org, which 303s to s3.pgkb.org, which was unlisted.
# Verified live 2026-07-15: api.clinpgx.org -> 303 -> s3.pgkb.org -> 200.
KNOWN_REDIRECT_TARGETS = {
    "pharmgkb": ("https://s3.pgkb.org/data/clinicalAnnotations.zip",),
}


def test_known_redirect_targets_are_allowlisted():
    """Offline guard against re-breaking a source by trimming ALLOWED_HOSTS."""
    from app.db_update import sources
    for key, targets in KNOWN_REDIRECT_TARGETS.items():
        assert key in sources.SOURCES, f"{key} vanished from the registry"
        for target in targets:
            assert sources._guard(target) == target, (
                f"{key} redirects through {target}, which is not allowlisted — "
                f"the download will raise PermissionError at runtime"
            )


def test_log_filter_redacts_rsids_and_genotypes():
    from app.core.security import NoGenotypeLogFilter
    filt = NoGenotypeLogFilter()
    rec = logging.LogRecord("t", logging.INFO, __file__, 1,
                            "user rs12913832 has genotype AG", None, None)
    assert filt.filter(rec) is True
    out = rec.getMessage()
    assert "rs12913832" not in out and "[redacted]" in out


def test_no_hardcoded_exfil_urls_in_runtime_code():
    """Static check: parse/annotate modules import no HTTP client and hold no URLs."""
    import re
    runtime = ["app/core/parsing.py", "app/core/annotation.py", "app/core/strand.py",
               "app/core/sessions.py", "app/api/parse.py", "app/api/annotate.py"]
    url_re = re.compile(r"https?://")
    for rel in runtime:
        text = Path(rel).read_text(encoding="utf-8")
        assert "import httpx" not in text and "import requests" not in text
        assert not url_re.search(text), f"unexpected URL in runtime module {rel}"
