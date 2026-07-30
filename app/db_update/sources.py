"""Annotation-source registry + downloader — the ONLY network-touching module.

Reached exclusively from the explicit ``update_databases`` step (never from the
parse/annotate runtime path). Every request is GET-only against a hardcoded host
ALLOWLIST of public annotation databases and carries ZERO user data (there is no
user data in memory during an update). A host guard makes egress to anything but
the allowlisted DB hosts impossible.
"""
from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from .. import config

# Hosts this module is permitted to contact. Anything else raises.
# NOTE: every host in a source's redirect chain must be listed, not just the entry
# point — _GuardedRedirectHandler re-validates each 3xx target. ClinPGx serves a 303
# from api.clinpgx.org to s3.pgkb.org, so both are required.
ALLOWED_HOSTS = frozenset({
    "ftp.ebi.ac.uk",          # GWAS Catalog bulk
    "www.ebi.ac.uk",          # GWAS Catalog (redirect/browse)
    "ftp.ncbi.nlm.nih.gov",   # ClinVar
    "api.clinpgx.org",        # ClinPGx (formerly PharmGKB) — registry entry point
    "s3.pgkb.org",            # ClinPGx — 303 redirect target that actually serves the zip
    "rest.ensembl.org",       # dbSNP/Ensembl normalization (build-time)
    "grch37.rest.ensembl.org",
})

USER_AGENT = "LocalDNATraitExtractor/0.1 (privacy-first; contact: local user)"
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB ceiling for any single source file


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate the host allowlist on EVERY redirect target, so a 3xx cannot
    bounce the request to a non-allowlisted host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _guard(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_GuardedRedirectHandler())


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str
    files: tuple[str, ...]     # logical files this source needs (informational)
    license: str
    license_url: str
    redistributable: bool
    cadence: str
    genome_build: str


SOURCES: dict[str, Source] = {
    "gwas_catalog": Source(
        key="gwas_catalog",
        name="NHGRI-EBI GWAS Catalog",
        url="https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/"
            "gwas-catalog-associations_ontology-annotated-full.zip",
        files=("gwas-catalog-associations_ontology-annotated.tsv",),
        license="EMBL-EBI Terms of Use — freely reusable with citation of the GWAS Catalog.",
        license_url="https://www.ebi.ac.uk/gwas/docs/about",
        redistributable=True,
        cadence="Biweekly",
        genome_build="GRCh38",
    ),
    "clinvar": Source(
        key="clinvar",
        name="NCBI ClinVar",
        url="https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz",
        files=("variant_summary.txt.gz",),
        license="Public domain (U.S. Government work). Cite ClinVar; not a clinical diagnosis.",
        license_url="https://www.ncbi.nlm.nih.gov/clinvar/docs/maintenance_use/",
        redistributable=True,
        cadence="Weekly",
        genome_build="GRCh38",
    ),
    # PharmGKB merged into ClinPGx (with CPIC and PharmCAT) in July 2025; pharmgkb.org
    # URLs now 301 to clinpgx.org. The licence did not change with the rebrand: the
    # LICENSE.txt shipped inside the download still reads CC BY-SA 4.0 and still requires
    # attribution to PharmGKB specifically, so the attribution text below keeps that name.
    "pharmgkb": Source(
        key="pharmgkb",
        name="ClinPGx (PharmGKB)",
        url="https://api.clinpgx.org/v1/download/file/data/clinicalAnnotations.zip",
        files=("clinical_annotations.tsv", "clinical_ann_alleles.tsv"),
        license="CC BY-SA 4.0 (copyleft). Attribution to PharmGKB required; data may not be "
                "sold; NOT bundled in the redistributable seed.",
        license_url="https://www.clinpgx.org/page/dataUsagePolicy",
        redistributable=False,   # copyleft: fetch on user's machine, do not rebundle
        cadence="Monthly",
        genome_build="GRCh38",
    ),
}

ProgressCB = Callable[[str, float], None] | None


def _guard(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise PermissionError(
            f"Refusing to contact non-allowlisted host {host!r}. "
            f"update_databases may only reach: {sorted(ALLOWED_HOSTS)}"
        )
    return url


def http_head(url: str) -> dict:
    """HEAD request to read Last-Modified / size without downloading the body."""
    _guard(url)
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with _opener().open(req, timeout=60) as resp:
        _guard(resp.url)  # host must still be allowlisted after any redirects
        return {
            "status": resp.status,
            "last_modified": resp.headers.get("Last-Modified"),
            "content_length": int(resp.headers.get("Content-Length") or 0),
            "final_url": resp.url,
        }


def download(url: str, dest: Path, progress: ProgressCB = None, label: str = "") -> dict:
    """Stream a public annotation file to ``dest`` on local disk.

    GET-only, no request body — so no user data can ever be transmitted here.
    """
    _guard(url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener().open(req, timeout=120) as resp:
        _guard(resp.url)  # host must still be allowlisted after any redirects
        total = int(resp.headers.get("Content-Length") or 0)
        last_modified = resp.headers.get("Last-Modified")
        read = 0
        chunk = 1024 * 256
        with open(dest, "wb") as fh:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                read += len(buf)
                if read > MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"Download exceeded {MAX_DOWNLOAD_BYTES} bytes; aborting.")
                fh.write(buf)
                if progress and total:
                    progress(label or url, read / total)
    return {"path": str(dest), "bytes": read, "last_modified": last_modified,
            "content_length": total}


def version_from_last_modified(last_modified: str | None) -> str:
    """Turn an HTTP Last-Modified header into a compact release/version string."""
    if not last_modified:
        return "unknown"
    # e.g. 'Mon, 22 Jun 2026 00:00:00 GMT' -> '2026-06-22'
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(last_modified)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return last_modified
