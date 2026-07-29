"""In-memory parse of a raw DNA file via apriha/snps.

PRIVACY: the raw upload is read into memory and handed to snps as bytes. We set
snps' output/resources dirs to a throwaway temp location and NEVER call any
``save``/``to_*`` helper, so no user genotype is ever written to disk. The parsed
genotypes live only in the returned in-memory object (held by the session store).
"""
from __future__ import annotations

import gzip
import io
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field

from snps import SNPs

from .. import config
from .strand import normalize_call


@dataclass
class ParsedGenome:
    """Holds parsed genotypes IN MEMORY ONLY. Never persisted or transmitted."""
    vendor: str
    build: int | None
    build_detected: bool
    assembly: str | None
    snp_count: int
    called_count: int
    chromosomes: list[str]
    genotypes: dict[str, str] = field(repr=False, default_factory=dict)  # rsid(lower) -> forward-sorted-ish call
    deduced_sex: str = ""
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        """The non-sensitive summary safe to return to the (localhost) UI.

        Deliberately excludes ``genotypes`` — no rsID/genotype leaves the process."""
        return {
            "vendor": self.vendor,
            "build": self.build,
            "build_detected": self.build_detected,
            "assembly": self.assembly,
            "snp_count": self.snp_count,
            "called_count": self.called_count,
            "chromosomes": self.chromosomes,
            "deduced_sex": self.deduced_sex,
            "warnings": self.warnings,
        }


def _decompress_if_needed(raw: bytes, filename: str) -> bytes:
    """23andMe ships .zip; some vendors .gz. Unpack in memory, but cap the inflated
    size to guard against zip/gzip decompression bombs (the upload-size limit only
    bounds the COMPRESSED bytes)."""
    limit = config.MAX_DECOMPRESSED_BYTES
    name = (filename or "").lower()
    if raw[:2] == b"PK" or name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            members = [n for n in zf.namelist() if not n.endswith("/")]
            if not members:
                raise ValueError("El archivo ZIP está vacío.")
            # Pick the largest member (the genome file, not a readme).
            member = max(members, key=lambda n: zf.getinfo(n).file_size)
            if zf.getinfo(member).file_size > limit:
                raise ValueError("El archivo descomprimido es demasiado grande.")
            # Bounded read: decompress at most limit+1 bytes and reject if exceeded
            # (defends against a spoofed header file_size).
            with zf.open(member) as fh:
                data = fh.read(limit + 1)
            if len(data) > limit:
                raise ValueError("El archivo descomprimido es demasiado grande.")
            return data
    if raw[:2] == b"\x1f\x8b" or name.endswith(".gz"):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
            data = gz.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Decompressed file is too large.")
        return data
    return raw


def parse_bytes(raw: bytes, filename: str = "") -> ParsedGenome:
    """Parse raw DNA-file bytes fully in memory and return a ParsedGenome."""
    data = _decompress_if_needed(raw, filename)

    warnings: list[str] = []
    # Throwaway dir — snps may create empty output/resources dirs; user data is
    # never written to them because we never call save/to_*. Removed in `finally`.
    tmp = tempfile.mkdtemp(prefix="dnatx_snps_")
    try:
        return _parse_with_snps(data, tmp, warnings)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _parse_with_snps(data: bytes, tmp: str, warnings: list[str]) -> ParsedGenome:
    snps = SNPs(data, output_dir=tmp, resources_dir=tmp)

    if not snps.valid:
        raise ValueError("No se pudo leer este archivo: formato de ADN no reconocido o vacío.")

    vendor = snps.source or "Desconocido"
    build = snps.build or None
    if not snps.build_detected:
        warnings.append("No se pudo detectar con seguridad la versión del genoma; se asume la reportada.")

    try:
        sex = snps.determine_sex()
    except Exception:  # determine_sex can raise on partial data
        sex = ""

    df = snps.snps
    chroms = sorted({str(c) for c in df["chrom"].unique()}, key=_chrom_key)

    # Build the in-memory genotype map. Normalize each call (drop no-calls). This
    # dict is the ONLY place user genotypes live, and only in RAM.
    genotypes: dict[str, str] = {}
    called = 0
    for rsid, gt in zip(df.index.to_list(), df["genotype"].to_list()):
        norm = normalize_call(gt)
        if norm is None:
            continue
        called += 1
        genotypes[str(rsid).lower()] = norm

    return ParsedGenome(
        vendor=vendor,
        build=int(build) if build else None,
        build_detected=bool(snps.build_detected),
        assembly=snps.assembly or None,
        snp_count=int(snps.count),
        called_count=called,
        chromosomes=chroms,
        genotypes=genotypes,
        deduced_sex=sex or "",
        warnings=warnings,
    )


def _chrom_key(c: str) -> tuple:
    """Sort chromosomes 1..22, X, Y, MT naturally."""
    order = {"X": 23, "Y": 24, "MT": 25, "M": 25}
    return (order.get(c, 0) or (int(c) if c.isdigit() else 99), c)
