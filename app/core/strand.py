"""Strand / orientation normalization — the single biggest correctness footgun.

Goal: express every user call on the FORWARD (plus) strand of the human reference,
alpha-sorted (so 'AG' not 'GA'), before comparing against curated forward-strand
genotypes.

Rules:
  1. Modern vendor files already report autosomal calls on the plus strand — do not
     blindly complement.
  2. Normalize each call: uppercase, split, drop non-ACGT, sort.
  3. No-calls ('--','00','NN','DD','II', …) are dropped, never matched.
  4. For a NON-ambiguous SNP, auto-detect minus-strand reporting: if the observed
     alleles are the complement of the curated forward pair, flip (A<->T, C<->G).
  5. AMBIGUOUS SNPs (A/T or C/G) cannot be resolved by complement — trust the
     vendor's declared plus strand and FLAG, never guess a flip.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import config

COMPLEMENT = {"A": "T", "T": "A", "C": "G", "G": "C"}
_ACGT = frozenset("ACGT")


def normalize_call(raw: str | None) -> str | None:
    """Normalize a raw vendor genotype to an alpha-sorted ACGT string, or None.

    Returns None for no-calls, missing data, indels, or anything containing a
    non-ACGT base. Haploid calls (single base, e.g. male X/Y/MT) are returned as
    a single sorted character.
    """
    if raw is None:
        return None
    g = str(raw).strip().upper()
    if g in config.NO_CALL_TOKENS:
        return None
    # Strip common padding/whitespace inside the token.
    g = g.replace(" ", "").replace("/", "").replace("|", "")
    if not g or any(ch not in _ACGT for ch in g):
        return None
    if len(g) > 2:  # not a SNP call we interpret (e.g. multi-base indel)
        return None
    return "".join(sorted(g))


def complement_genotype(genotype: str) -> str:
    """Complement + re-sort a normalized genotype (e.g. 'AG' -> 'CT')."""
    return "".join(sorted(COMPLEMENT[b] for b in genotype))


@dataclass(frozen=True)
class StrandResult:
    genotype: str | None   # forward-strand, alpha-sorted; None = could not resolve
    flipped: bool          # True if we complement-flipped a minus-strand call
    note: str              # human-readable orientation note ('' when trivially forward)
    withheld: bool = False # True if we refused to assert (ambiguous/mismatch)


def to_forward_strand(genotype_sorted: str, forward_alleles: set[str], ambiguous: bool) -> StrandResult:
    """Resolve a normalized user genotype onto the curated forward strand.

    ``forward_alleles`` is the set of the variant's two forward-strand alleles
    (e.g. {'A','G'}). ``ambiguous`` marks palindromic A/T or C/G variants.
    """
    alleles = set(genotype_sorted)

    # (a) Already on the forward strand.
    if alleles <= forward_alleles:
        note = ""
        if ambiguous:
            note = "strand-ambiguous (A/T or C/G) — trusting the vendor's plus-strand orientation"
        return StrandResult(genotype_sorted, False, note)

    # (b) Ambiguous SNP whose call doesn't fit the forward pair at all — withhold.
    if ambiguous:
        return StrandResult(
            None, False,
            "strand-ambiguous and does not match reference orientation — result withheld",
            withheld=True,
        )

    # (c) Non-ambiguous: try complement (rescues legacy minus-strand files).
    comp = {COMPLEMENT[a] for a in alleles}
    if comp <= forward_alleles:
        flipped = complement_genotype(genotype_sorted)
        return StrandResult(
            flipped, True,
            "strand-normalized: complement-flipped from vendor minus strand",
        )

    # (d) Alleles fit neither orientation — not this variant / bad call.
    return StrandResult(
        None, False,
        "genotype alleles do not match this variant's orientation — result withheld",
        withheld=True,
    )


def forward_allele_set(alleles_forward: str) -> set[str]:
    """Parse an 'A/G' style forward-allele string into a set of bases."""
    return {b for b in alleles_forward.upper().replace("/", "") if b in _ACGT}
