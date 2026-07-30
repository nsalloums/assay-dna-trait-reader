"""Annotation engine: join in-memory user genotypes against the local store.

Loaded once at startup into memory for fast, fully-offline lookups. No network,
no user-data persistence. Matching is by rsID (build-independent), with strand
resolution applied per variant and APOE resolved as a two-SNP diplotype.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .. import config
from .. import db as dbmod
from .strand import forward_allele_set, to_forward_strand

_ACGT = frozenset("ACGT")


def _zygosity(genotype: str) -> str:
    if len(set(genotype)) == 1:
        return "homozygous"
    return "heterozygous"


def _readable_effect(row: dict) -> tuple[str, str]:
    """Return (English, Spanish) plain-language explanations of what a match means.

    Curated-seed rows carry their own bilingual text (effect_text / effect_text_es).
    Bulk sources (GWAS/ClinVar/PharmGKB) carry English source data, so we wrap them
    in a short, honest framing per language that never reads as a diagnosis. The
    frontend picks the language; both are always populated."""
    src = row.get("source")
    cat = row.get("category")
    if src == "curated_seed":
        en = row.get("effect_text") or ""
        return en, (row.get("effect_text_es") or en)
    trait_en = row.get("trait") or "this trait"
    trait_es = row.get("trait") or "esta característica"
    if cat == "gwas_risk":
        return (
            f"Genetic studies associate this variant with “{trait_en}”. "
            f"It is a statistical tendency across populations, not a diagnosis.",
            f"Estudios genéticos asocian esta variante con «{trait_es}». "
            f"Es una tendencia estadística de poblaciones, no un diagnóstico.",
        )
    if cat == "clinical_significance":
        sig = (row.get("effect_text") or "").replace("ClinVar clinical significance: ", "")
        return (
            f"Clinical significance reported in ClinVar: {sig}. "
            f"A consumer data point can be a false positive — confirm it with a clinical test.",
            f"Significado clínico reportado en ClinVar: {sig}. "
            f"Un dato de consumo puede ser un falso positivo — confírmalo con una prueba clínica.",
        )
    if cat == "pharmacogenomics":
        return (
            f"It may influence your response to “{trait_en}”. "
            f"It is advisory: do not change any medication or dose based on this.",
            f"Puede influir en tu respuesta a «{trait_es}». "
            f"Es orientativo: no cambies ninguna medicación ni dosis por esto.",
        )
    en = row.get("effect_text") or ""
    return en, (row.get("effect_text_es") or en)


@dataclass
class AnnotationStore:
    haplotypes: list[dict] = field(default_factory=list)
    releases: dict[tuple[str, str], dict] = field(default_factory=dict)  # (source,version) -> release
    aliases: dict[str, str] = field(default_factory=dict)        # old_rsid -> current_rsid
    ready: bool = False
    db_path: Path | None = None

    # ---- loading -----------------------------------------------------------
    # Only small metadata (haplotypes, releases, aliases) is held in memory.
    # Annotation rows are queried per request via a read-only temp-table JOIN so
    # the store scales from 105 seed rows to millions after a full source ingest,
    # keeps startup instant, and — being read-only — CANNOT write user data to disk.
    @classmethod
    def load(cls, db_path: Path | None = None) -> "AnnotationStore":
        store = cls()
        path = db_path or config.DB_FILE
        store.db_path = path
        if not dbmod.db_exists_and_ready(path):
            return store  # not ready; callers check .ready
        conn = dbmod.connect(path, readonly=True)
        try:
            for row in conn.execute("SELECT * FROM haplotype_rule"):
                h = dict(row)
                h["member_rsids"] = json.loads(h["member_rsids"])
                h["diplotypes"] = json.loads(h["diplotypes"])
                store.haplotypes.append(h)
            for row in conn.execute("SELECT * FROM source_release"):
                r = dict(row)
                store.releases[(r["source"], r["source_version"])] = r
            try:
                for row in conn.execute("SELECT old_rsid, current_rsid FROM rsid_alias"):
                    store.aliases[row["old_rsid"]] = row["current_rsid"]
            except sqlite3.Error:
                pass
        finally:
            conn.close()
        store.ready = True
        return store

    def _fetch_candidate_rows(self, conn: sqlite3.Connection, rsids: set[str]) -> dict[str, list[dict]]:
        """Load annotation rows for exactly the user's rsIDs via a temp-table JOIN.
        The temp table holds ONLY rsIDs (no genotypes), lives in memory, and is
        dropped when the connection closes — no user data is ever persisted.

        temp_store=MEMORY is what keeps that true; it is set in db.connect() so it
        applies to every read-only connection. See test_temp_tables_never_touch_disk."""
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS q(rsid TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM q")
        conn.executemany("INSERT OR IGNORE INTO q(rsid) VALUES (?)", [(r,) for r in rsids])
        out: dict[str, list[dict]] = {}
        for row in conn.execute("SELECT a.* FROM annotation a JOIN q ON a.rsid = q.rsid"):
            r = dict(row)
            out.setdefault(r["rsid"], []).append(r)
        return out

    # ---- provenance --------------------------------------------------------
    def _provenance(self, row: dict) -> dict:
        rel = self.releases.get((row["source"], row["source_version"]), {})
        return {
            "source": row["source"],
            "source_display": rel.get("display_name") or row["source"],
            "source_version": row["source_version"],
            "source_date": rel.get("fetched_date"),
            "release_date": row["source_version"],
            "license": rel.get("license"),
            "origin": rel.get("origin"),
        }

    # ---- matching ----------------------------------------------------------
    def _forward_pair(self, rows: list[dict]) -> set[str]:
        bases: set[str] = set()
        for r in rows:
            for a in (r.get("ref_allele"), r.get("alt_allele"), r.get("risk_allele")):
                if a:
                    bases |= {b for b in a.upper() if b in _ACGT}
        return bases

    def match(self, genotypes: dict[str, str]) -> Iterator[dict]:
        """Yield one match dict per surfaced association for the user's genotypes.

        Opens a read-only connection, resolves candidate rows for exactly the
        user's rsIDs via a temp-table JOIN, then applies strand + genotype logic
        in Python. The connection (and its rsID-only temp table) is closed at the
        end — no user data touches disk."""
        if not self.ready or not self.db_path:
            return
        # Map alias old->current so an alias target inherits the old rsid's call.
        alias_call: dict[str, str] = {}
        query_rsids = set(genotypes.keys())
        for old, cur in self.aliases.items():
            if old in genotypes:
                query_rsids.add(cur)
                alias_call.setdefault(cur, genotypes[old])

        conn = dbmod.connect(self.db_path, readonly=True)
        try:
            rows_by_rsid = self._fetch_candidate_rows(conn, query_rsids)

            for rsid, rows in rows_by_rsid.items():
                user_gt = genotypes.get(rsid) or alias_call.get(rsid)
                if user_gt is None:
                    continue
                forward = self._forward_pair(rows)
                ambiguous = bool(rows[0].get("ambiguous_strand"))
                # Allele-level GWAS rows carry only a risk allele, and PharmGKB
                # per-genotype rows carry no ref/alt at all — so `forward` may be a
                # singleton or empty. Without a full pair we cannot infer strand,
                # so fall back to trusting the vendor's plus strand by seeding the
                # forward set with the user's own alleles. This keeps heterozygous
                # carriers and PharmGKB genotypes from being wrongly withheld.
                if len(forward) < 2:
                    forward = forward | set(user_gt)
                res = to_forward_strand(user_gt, forward, ambiguous)
                if res.withheld or res.genotype is None:
                    continue
                fwd_gt = res.genotype
                for row in rows:
                    m = self._match_row(row, user_gt, fwd_gt, res)
                    if m is not None:
                        yield m

            # Haplotype (multi-SNP) rules, e.g. APOE — fetch member rows in same conn.
            yield from self._match_haplotypes(conn, genotypes)
        finally:
            conn.close()

    def _match_row(self, row: dict, user_gt: str, fwd_gt: str, res) -> dict | None:
        row_gt = row.get("genotype")
        carrier_note = ""
        carrier_note_es = ""
        if row_gt:
            # Genotype-specific (curated seed / PharmGKB per-genotype): exact match.
            if row_gt != fwd_gt:
                return None
        else:
            # Allele-level (GWAS/ClinVar): the user carries the risk/alt allele?
            allele = (row.get("risk_allele") or row.get("alt_allele") or "").upper()
            if not allele or not (set(allele) & set(fwd_gt)):
                return None
            homo = len(set(fwd_gt)) == 1
            carrier_note = f"You carry the {allele} allele ({'homozygous' if homo else 'heterozygous'})."
            carrier_note_es = f"Tienes el alelo {allele} ({'homocigoto' if homo else 'heterocigoto'})."

        effect_en, effect_es = _readable_effect(row)  # brief, plain-language "what this means", both languages

        prov = self._provenance(row)
        return {
            "rsid": row["rsid"],
            "user_genotype": user_gt,
            "resolved_genotype": fwd_gt,
            "gene": row.get("gene"),
            "trait": row.get("trait"),
            "trait_es": row.get("trait_es"),
            "category": row["category"],
            "sensitivity": row.get("sensitivity", "low"),
            "is_health": row.get("sensitivity") == "health",
            "effect_text": effect_en,
            "effect_text_es": effect_es,
            "carrier_note": carrier_note,
            "carrier_note_es": carrier_note_es,
            "magnitude": row.get("magnitude"),
            "plain_summary": row.get("plain_summary"),
            "plain_summary_es": row.get("plain_summary_es"),
            "risk_allele": row.get("risk_allele"),
            "zygosity": _zygosity(fwd_gt),
            "ambiguous_strand": bool(row.get("ambiguous_strand")),
            "strand_note": res.note,
            "flipped": res.flipped,
            "confidence": row.get("confidence"),
            "effect_size": row.get("effect_size"),
            "chrom": row.get("chrom"),
            "pos_b37": row.get("pos_b37"),
            "pos_b38": row.get("pos_b38"),
            "evidence": row.get("evidence"),
            "citation": row.get("citation"),
            **prov,
        }

    def _match_haplotypes(self, conn: sqlite3.Connection, genotypes: dict[str, str]) -> Iterator[dict]:
        for hap in self.haplotypes:
            members = [m.lower() for m in hap["member_rsids"]]
            member_rows = self._fetch_candidate_rows(conn, set(members))
            resolved: dict[str, str] = {}
            ok = True
            for rsid in members:
                raw = genotypes.get(rsid)
                if raw is None:
                    ok = False
                    break
                rows = member_rows.get(rsid)
                forward = self._forward_pair(rows) if rows else forward_allele_set("")
                ambiguous = bool(rows[0].get("ambiguous_strand")) if rows else False
                r = to_forward_strand(raw, forward, ambiguous)
                if r.genotype is None:
                    ok = False
                    break
                resolved[rsid] = r.genotype
            if not ok:
                continue
            key = "|".join(resolved[m] for m in members)
            dip = hap["diplotypes"].get(key)
            if not dip:
                continue
            prov = self._provenance({
                "source": hap["source"],
                "source_version": hap["source_version"],
            })
            yield {
                "rsid": "+".join(members),
                "user_genotype": " ".join(f"{m}={genotypes.get(m.lower())}" for m in members),
                "resolved_genotype": dip["name"],
                "gene": hap.get("gene"),
                "trait": hap["trait"],
                "trait_es": hap.get("trait_es"),
                "category": hap["category"],
                "sensitivity": hap.get("sensitivity", "health"),
                "is_health": hap.get("sensitivity") == "health",
                "effect_text": dip["effect"],
                "effect_text_es": dip.get("effect_es") or dip["effect"],
                "carrier_note": "",
                "carrier_note_es": "",
                "magnitude": dip.get("magnitude"),
                "plain_summary": hap.get("plain_summary"),
                "plain_summary_es": hap.get("plain_summary_es"),
                "risk_allele": None,
                "zygosity": "diplotype",
                "ambiguous_strand": False,
                "strand_note": "",
                "flipped": False,
                "confidence": None,
                "effect_size": None,
                "chrom": None,
                "pos_b37": None,
                "pos_b38": None,
                "evidence": hap.get("evidence"),
                "citation": None,
                "is_haplotype": True,
                **prov,
            }

    # ---- freshness ---------------------------------------------------------
    def freshness(self) -> list[dict]:
        out = []
        for (source, version), rel in sorted(self.releases.items()):
            out.append({
                "source": source,
                "display_name": rel.get("display_name") or source,
                "version": version,
                "released_at": version,
                "ingested_at": rel.get("fetched_date"),
                "record_count": rel.get("record_count"),
                "genome_build": rel.get("genome_build"),
                "origin": rel.get("origin"),
                "license": rel.get("license"),
            })
        return out


def consolidate(matches: list[dict], cap_per_group: int = 6) -> list[dict]:
    """Tame noisy many-per-SNP sources for the UI.

    Curated-seed and haplotype rows are always kept (few, and the headline). For
    allele-level sources (GWAS/ClinVar/PharmGKB) that can produce dozens of rows
    per rsID (one per drug/study), dedupe by trait, keep the top ``cap_per_group``
    by magnitude, and flag how many more were collapsed. Final order groups by
    category with health surfaced and highest-magnitude first.
    """
    headline: list[dict] = []
    grouped: dict[tuple, list[dict]] = {}
    for m in matches:
        if m["source"] == "curated_seed" or m.get("is_haplotype"):
            headline.append(m)
        else:
            grouped.setdefault((m["rsid"], m["source"], m["category"]), []).append(m)

    out = list(headline)
    for rows in grouped.values():
        by_trait: dict[str, dict] = {}
        for r in sorted(rows, key=lambda x: -(x.get("magnitude") or 0)):
            by_trait.setdefault(r.get("trait") or "", r)
        uniq = list(by_trait.values())
        keep = uniq[:cap_per_group]
        extra = len(uniq) - len(keep)
        if keep and extra > 0:
            keep[0] = {**keep[0], "truncated_count": extra}
        out.extend(keep)

    out.sort(key=lambda m: (m.get("category") or "", not m.get("is_health"), -(m.get("magnitude") or 0)))
    return out


# Process-local singleton, (re)loaded in the app lifespan and after DB updates.
_STORE: AnnotationStore | None = None


def get_store() -> AnnotationStore:
    global _STORE
    if _STORE is None:
        _STORE = AnnotationStore.load()
    return _STORE


def reload_store() -> AnnotationStore:
    global _STORE
    _STORE = AnnotationStore.load()
    return _STORE
