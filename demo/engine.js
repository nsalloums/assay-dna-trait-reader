"use strict";
/* ASSAY — annotation engine, 100% IN THE BROWSER (static demo, no backend).
 *
 * Ports the reference logic of the local Python app:
 *   app/core/parsing.py     -> parseDNA(text, filename)
 *   app/core/strand.py      -> normalizeCall(raw) + toForward(gt, forwardSet, ambiguous)
 *   app/core/annotation.py  -> annotateLocal(genotypes)  (+ ordering consolidation)
 *   app/db_update/build_seed.py -> reading window.SEED (associations + APOE haplotype)
 *
 * PRIVACY INVARIANT: this file makes NO network calls. It only reads text already
 * loaded into memory (File.text()) and compares it against window.SEED, which is
 * already embedded as a global. Nothing is uploaded or transmitted.
 */

/* ------------------------------------------------------------------ strand */
/* EXACT mirror of app/core/strand.py */

const COMPLEMENT = { A: "T", T: "A", C: "G", G: "C" };
const ACGT = new Set(["A", "C", "G", "T"]);

// "No call" tokens — dropped, never matched (config.NO_CALL_TOKENS).
const NO_CALL_TOKENS = new Set(["--", "00", "NN", "DD", "II", "-", "", "..", "I", "D"]);

/* Normalize a raw vendor genotype to an alphabetically-sorted ACGT string, or
 * null. Returns null for no-calls, indels, or anything with a non-ACGT base.
 * Haploid calls (a single base) are returned as a single character. */
function normalizeCall(raw) {
  if (raw === null || raw === undefined) return null;
  let g = String(raw).trim().toUpperCase();
  if (NO_CALL_TOKENS.has(g)) return null;
  // Strip common padding/whitespace inside the token.
  g = g.replace(/ /g, "").replace(/\//g, "").replace(/\|/g, "");
  if (!g) return null;
  for (const ch of g) if (!ACGT.has(ch)) return null;
  if (g.length > 2) return null; // not a SNP call we interpret (e.g. an indel)
  return g.split("").sort().join("");
}

/* Complement + re-sort an already-normalized genotype (e.g. 'AG' -> 'CT'). */
function complementGenotype(genotype) {
  return genotype.split("").map((b) => COMPLEMENT[b]).sort().join("");
}

/* Parse a forward allele string 'A/G' into a Set of bases. */
function forwardAlleleSet(allelesForward) {
  const out = new Set();
  for (const b of String(allelesForward || "").toUpperCase().replace(/\//g, "")) {
    if (ACGT.has(b)) out.add(b);
  }
  return out;
}

function isSubset(small, big) {
  for (const x of small) if (!big.has(x)) return false;
  return true;
}

/* Resolve a normalized user genotype against the curated forward strand.
 * Returns { genotype, flipped, note, withheld }. Mirror of to_forward_strand. */
function toForward(genotypeSorted, forwardAlleles, ambiguous) {
  const alleles = new Set(genotypeSorted.split(""));

  // (a) Already on the forward strand.
  if (isSubset(alleles, forwardAlleles)) {
    let note = "";
    if (ambiguous) {
      note = "strand-ambiguous (A/T or C/G) — trusting the vendor's plus-strand orientation";
    }
    return { genotype: genotypeSorted, flipped: false, note, withheld: false };
  }

  // (b) Ambiguous SNP whose call doesn't fit the forward pair — withheld.
  if (ambiguous) {
    return {
      genotype: null,
      flipped: false,
      note: "strand-ambiguous and does not match reference orientation — result withheld",
      withheld: true,
    };
  }

  // (c) Non-ambiguous: try to complement (rescues old minus-strand files).
  const comp = new Set([...alleles].map((a) => COMPLEMENT[a]));
  if (isSubset(comp, forwardAlleles)) {
    return {
      genotype: complementGenotype(genotypeSorted),
      flipped: true,
      note: "strand-normalized: complement-flipped from vendor minus strand",
      withheld: false,
    };
  }

  // (d) Alleles don't fit either orientation — not this variant / bad call.
  return {
    genotype: null,
    flipped: false,
    note: "genotype alleles do not match this variant's orientation — result withheld",
    withheld: true,
  };
}

/* ----------------------------------------------------------------- parsing */
/* Ports app/core/parsing.py to the browser. We do NOT use snps (the Python
 * library): instead we apply the consumer raw-data format rules directly to the
 * text. Matching is by rsID, so we SKIP genome-build detection (shown as "—"
 * apart from a simple vendor hint). */

// Vendor hints detected in the header/comment lines.
const VENDOR_HINTS = [
  [/23andme/i, "23andMe"],
  [/ancestry/i, "AncestryDNA"],
  [/family\s*tree\s*dna|ftdna/i, "FamilyTreeDNA"],
  [/myheritage/i, "MyHeritage"],
  [/living\s*dna/i, "LivingDNA"],
  [/tellmegen/i, "tellmeGen"],
];

function detectVendor(text, filename) {
  const head = text.slice(0, 4000);
  for (const [re, name] of VENDOR_HINTS) if (re.test(head)) return name;
  const fn = (filename || "").toLowerCase();
  for (const [re, name] of VENDOR_HINTS) if (re.test(fn)) return name;
  // Heuristic: the quoted CSV header RSID,CHROMOSOME,POSITION,RESULT is the
  // FamilyTreeDNA signature (MyHeritage is already caught by its earlier comment).
  if (/rsid\s*,\s*chromosome\s*,\s*position\s*,\s*result/i.test(head)) return "FamilyTreeDNA";
  return "Generic";
}

function splitFields(line) {
  // Tab or comma delimiter (consumer files use one or the other).
  const parts = line.indexOf("\t") >= 0 ? line.split("\t") : line.split(",");
  // Strip wrapping quotes and spaces (FamilyTreeDNA/MyHeritage quote each field).
  return parts.map((p) => p.trim().replace(/^"(.*)"$/, "$1").trim());
}

function looksLikeHeader(fields) {
  const f0 = (fields[0] || "").toLowerCase();
  return f0 === "rsid" || f0 === "rs id" || f0 === "snp" || f0.startsWith("rsid");
}

/* Parse DNA-file text -> object with genotypes and a summary.
 * Returns { vendor, build, snp_count, called_count, genotypes, warnings }.
 * genotypes: map rsid(lowercase) -> normalized genotype (strand not yet resolved;
 * strand resolution happens in annotateLocal, as in Python). */
function parseDNA(text, filename) {
  const vendor = detectVendor(text, filename);
  const warnings = [];
  const genotypes = {};
  let snpCount = 0;
  let called = 0;
  let headerSkipped = false;

  const lines = text.split(/\r\n|\r|\n/);
  for (const rawLine of lines) {
    const line = rawLine;
    if (!line) continue;
    if (line[0] === "#") continue; // vendor comments
    const fields = splitFields(line);
    if (fields.length < 4) continue; // not a data row (rsid, chrom, pos, ...)
    // Skip the header row (the first data row that clearly looks like a header).
    if (!headerSkipped && looksLikeHeader(fields)) {
      headerSkipped = true;
      continue;
    }
    headerSkipped = true; // from here on, everything else is data
    const rsid = fields[0];
    if (!rsid || rsid.toLowerCase() === "rsid") continue;

    // 5 columns -> genotype = col3 + col4 (allele1 + allele2, AncestryDNA format).
    // >= 4 columns -> genotype = col3 (23andMe/FTDNA/MyHeritage/LivingDNA format).
    let gtRaw;
    if (fields.length >= 5) gtRaw = (fields[3] || "") + (fields[4] || "");
    else gtRaw = fields[3] || "";

    snpCount++;
    const norm = normalizeCall(gtRaw);
    if (norm === null) continue; // no-call: dropped, never matched
    called++;
    genotypes[rsid.toLowerCase()] = norm;
  }

  if (snpCount === 0) {
    throw new Error("Could not read this file: unrecognized or empty DNA format.");
  }

  // We skip genome-build detection (matching is by rsID).
  return {
    vendor,
    build: null,
    snp_count: snpCount,
    called_count: called,
    genotypes,
    warnings,
  };
}

/* -------------------------------------------------------------- annotation */
/* Ports app/core/annotation.py: walks window.SEED.associations, resolves the
 * strand per variant and does genotype-specific matching; then resolves the APOE
 * haplotype from rs429358 + rs7412. The demo has only the curated seed (no
 * GWAS/ClinVar/PharmGKB). Both languages ride along on each match. */

// Fixed seed provenance for the demo (equivalent to build_seed's source_release).
const SEED_PROV = {
  source: "curated_seed",
  source_display: "Curated seed (educational)",
  source_version: "2026-07 (curated)",
  source_date: "2026-07-01T00:00:00Z",
  release_date: "2026-07 (curated)",
};

function zygosity(genotype) {
  return new Set(genotype.split("")).size === 1 ? "homozygous" : "heterozygous";
}

function assocForwardSet(a) {
  // Mirror of _forward_pair: use the forward allele pair declared in the seed.
  return forwardAlleleSet(a.alleles_forward);
}

function matchAssociation(a, userGt) {
  const forward = assocForwardSet(a);
  const ambiguous = !!a.ambiguous_strand;
  const res = toForward(userGt, forward, ambiguous);
  if (res.withheld || res.genotype === null) return null;
  const fwdGt = res.genotype;
  const meta = a.genotypes[fwdGt];
  if (!meta) return null; // user's genotype is not among the interpreted ones

  return {
    rsid: a.rsid.toLowerCase(),
    user_genotype: userGt,
    resolved_genotype: fwdGt,
    gene: a.gene,
    trait: a.trait,
    trait_es: a.trait_es,
    category: a.category,
    sensitivity: a.sensitivity,
    is_health: a.sensitivity === "health",
    effect_text: meta.effect || "",
    effect_text_es: meta.effect_es || meta.effect || "",
    carrier_note: "",
    carrier_note_es: "",
    magnitude: meta.magnitude,
    plain_summary: a.plain_summary,
    plain_summary_es: a.plain_summary_es,
    risk_allele: a.risk_allele,
    zygosity: zygosity(fwdGt),
    ambiguous_strand: ambiguous,
    strand_note: res.note,
    flipped: res.flipped,
    confidence: null,
    chrom: a.chrom,
    pos_b37: a.pos_b37,
    source: SEED_PROV.source,
    source_display: SEED_PROV.source_display,
    source_version: SEED_PROV.source_version,
    source_date: SEED_PROV.source_date,
    release_date: SEED_PROV.release_date,
    evidence: a.evidence,
    citation: null,
  };
}

function matchHaplotype(hap, genotypes, assocByRsid) {
  const members = hap.member_rsids.map((m) => m.toLowerCase());
  const resolved = {};
  for (const rsid of members) {
    const raw = genotypes[rsid];
    if (raw === undefined) return null; // a member SNP is missing
    const a = assocByRsid[rsid];
    const forward = a ? assocForwardSet(a) : forwardAlleleSet("");
    const ambiguous = a ? !!a.ambiguous_strand : false;
    const r = toForward(raw, forward, ambiguous);
    if (r.genotype === null) return null;
    resolved[rsid] = r.genotype;
  }
  const key = members.map((m) => resolved[m]).join("|");
  const dip = hap.diplotypes[key];
  if (!dip) return null;

  return {
    rsid: members.join("+"),
    user_genotype: members.map((m) => `${m}=${genotypes[m]}`).join(" "),
    resolved_genotype: dip.name,
    gene: hap.gene,
    trait: hap.trait,
    trait_es: hap.trait_es,
    category: hap.category,
    sensitivity: hap.sensitivity || "health",
    is_health: (hap.sensitivity || "health") === "health",
    effect_text: dip.effect,
    effect_text_es: dip.effect_es || dip.effect,
    carrier_note: "",
    carrier_note_es: "",
    magnitude: dip.magnitude,
    plain_summary: hap.plain_summary,
    plain_summary_es: hap.plain_summary_es,
    risk_allele: null,
    zygosity: "diplotype",
    ambiguous_strand: false,
    strand_note: "",
    flipped: false,
    confidence: null,
    chrom: null,
    pos_b37: null,
    source: SEED_PROV.source,
    source_display: SEED_PROV.source_display,
    source_version: SEED_PROV.source_version,
    source_date: SEED_PROV.source_date,
    release_date: SEED_PROV.release_date,
    evidence: hap.evidence,
    citation: null,
    is_haplotype: true,
  };
}

/* Orders like consolidate() in Python: by category, health first within each
 * category, then higher relevance. Array.sort is stable (ES2019+), so ties keep
 * the seed order. */
function consolidateOrder(matches) {
  return matches.slice().sort((x, y) => {
    const cx = x.category || "", cy = y.category || "";
    if (cx < cy) return -1;
    if (cx > cy) return 1;
    const hx = x.is_health ? 0 : 1, hy = y.is_health ? 0 : 1;
    if (hx !== hy) return hx - hy;
    return (y.magnitude || 0) - (x.magnitude || 0);
  });
}

/* Entry point: given the user's genotype map, returns the sorted array of matches
 * ready to render. */
function annotateLocal(genotypes) {
  const seed = window.SEED || {};
  const associations = seed.associations || [];
  const haplotypes = seed.haplotypes || [];

  const assocByRsid = {};
  for (const a of associations) assocByRsid[a.rsid.toLowerCase()] = a;

  const matches = [];
  // Walk the associations in seed order (stable ties).
  for (const a of associations) {
    const rsid = a.rsid.toLowerCase();
    const userGt = genotypes[rsid];
    if (userGt === undefined) continue;
    const m = matchAssociation(a, userGt);
    if (m) matches.push(m);
  }
  // Haplotypes (APOE) last, as in store.match().
  for (const hap of haplotypes) {
    const m = matchHaplotype(hap, genotypes, assocByRsid);
    if (m) matches.push(m);
  }

  return consolidateOrder(matches);
}

/* Expose as globals (scripts are loaded as classic <script>, no modules). */
window.parseDNA = parseDNA;
window.normalizeCall = normalizeCall;
window.toForward = toForward;
window.annotateLocal = annotateLocal;
