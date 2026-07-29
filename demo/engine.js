"use strict";
/* ASSAY — motor de anotación 100% EN EL NAVEGADOR (demo estático, sin backend).
 *
 * Porta la lógica de referencia de la app local en Python:
 *   app/core/parsing.py     -> parseDNA(text, filename)
 *   app/core/strand.py      -> normalizeCall(raw) + toForward(gt, forwardSet, ambiguous)
 *   app/core/annotation.py  -> annotateLocal(genotypes)  (+ consolidación de orden)
 *   app/db_update/build_seed.py -> lectura de window.SEED (asociaciones + haplotipo APOE)
 *
 * INVARIANTE DE PRIVACIDAD: este archivo no hace NINGUNA llamada de red. Solo lee
 * texto ya cargado en memoria (File.text()) y lo compara contra window.SEED, que ya
 * está embebido como global. Nada se sube ni se transmite.
 */

/* ------------------------------------------------------------------ strand */
/* Espejo EXACTO de app/core/strand.py */

const COMPLEMENT = { A: "T", T: "A", C: "G", G: "C" };
const ACGT = new Set(["A", "C", "G", "T"]);

// Tokens de "no llamada" — se descartan, nunca se emparejan (config.NO_CALL_TOKENS).
const NO_CALL_TOKENS = new Set(["--", "00", "NN", "DD", "II", "-", "", "..", "I", "D"]);

/* Normaliza un genotipo crudo del proveedor a una cadena ACGT ordenada
 * alfabéticamente, o null. Devuelve null para no-llamadas, indels o cualquier
 * cosa con una base no-ACGT. Las llamadas haploides (una sola base) se
 * devuelven como un único carácter. */
function normalizeCall(raw) {
  if (raw === null || raw === undefined) return null;
  let g = String(raw).trim().toUpperCase();
  if (NO_CALL_TOKENS.has(g)) return null;
  // Quita relleno/espacios comunes dentro del token.
  g = g.replace(/ /g, "").replace(/\//g, "").replace(/\|/g, "");
  if (!g) return null;
  for (const ch of g) if (!ACGT.has(ch)) return null;
  if (g.length > 2) return null; // no es una llamada SNP que interpretemos (p.ej. indel)
  return g.split("").sort().join("");
}

/* Complementa + reordena un genotipo ya normalizado (p.ej. 'AG' -> 'CT'). */
function complementGenotype(genotype) {
  return genotype.split("").map((b) => COMPLEMENT[b]).sort().join("");
}

/* Parsea una cadena de alelos directos 'A/G' a un Set de bases. */
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

/* Resuelve un genotipo de usuario normalizado sobre la hebra directa curada.
 * Devuelve { genotype, flipped, note, withheld }. Espejo de to_forward_strand. */
function toForward(genotypeSorted, forwardAlleles, ambiguous) {
  const alleles = new Set(genotypeSorted.split(""));

  // (a) Ya está en la hebra directa.
  if (isSubset(alleles, forwardAlleles)) {
    let note = "";
    if (ambiguous) {
      note = "strand-ambiguous (A/T or C/G) — trusting the vendor's plus-strand orientation";
    }
    return { genotype: genotypeSorted, flipped: false, note, withheld: false };
  }

  // (b) SNP ambiguo cuya llamada no encaja con el par directo — se retiene.
  if (ambiguous) {
    return {
      genotype: null,
      flipped: false,
      note: "strand-ambiguous and does not match reference orientation — result withheld",
      withheld: true,
    };
  }

  // (c) No ambiguo: intenta complementar (rescata archivos antiguos en hebra −).
  const comp = new Set([...alleles].map((a) => COMPLEMENT[a]));
  if (isSubset(comp, forwardAlleles)) {
    return {
      genotype: complementGenotype(genotypeSorted),
      flipped: true,
      note: "strand-normalized: complement-flipped from vendor minus strand",
      withheld: false,
    };
  }

  // (d) Los alelos no encajan en ninguna orientación — no es esta variante / llamada mala.
  return {
    genotype: null,
    flipped: false,
    note: "genotype alleles do not match this variant's orientation — result withheld",
    withheld: true,
  };
}

/* ----------------------------------------------------------------- parsing */
/* Porta app/core/parsing.py al navegador. NO usamos snps (librería Python): en su
 * lugar aplicamos las reglas de formato de datos crudos de consumo directamente
 * sobre el texto. El emparejamiento es por rsID, así que OMITIMOS la detección de
 * versión del genoma (se muestra "—" salvo una pista simple del proveedor). */

// Pistas de proveedor detectadas en las líneas de cabecera/comentario.
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
  // Heurística: la cabecera CSV entrecomillada RSID,CHROMOSOME,POSITION,RESULT es
  // la firma de FamilyTreeDNA (MyHeritage ya se detecta por su comentario previo).
  if (/rsid\s*,\s*chromosome\s*,\s*position\s*,\s*result/i.test(head)) return "FamilyTreeDNA";
  return "Genérico";
}

function splitFields(line) {
  // Delimitador tab o coma (los archivos de consumo usan uno u otro).
  const parts = line.indexOf("\t") >= 0 ? line.split("\t") : line.split(",");
  // Quita comillas envolventes y espacios (FamilyTreeDNA/MyHeritage citan cada campo).
  return parts.map((p) => p.trim().replace(/^"(.*)"$/, "$1").trim());
}

function looksLikeHeader(fields) {
  const f0 = (fields[0] || "").toLowerCase();
  return f0 === "rsid" || f0 === "rs id" || f0 === "snp" || f0.startsWith("rsid");
}

/* Parsea texto de un archivo de ADN -> objeto con genotipos y resumen.
 * Devuelve { vendor, build, snp_count, called_count, genotypes, warnings }.
 * genotypes: mapa rsid(minúsculas) -> genotipo normalizado (hebra sin resolver;
 * la resolución de hebra ocurre en annotateLocal, como en Python). */
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
    if (line[0] === "#") continue; // comentarios de proveedor
    const fields = splitFields(line);
    if (fields.length < 4) continue; // no es una fila de datos (rsid, crom, pos, ...)
    // Salta la fila de cabecera (la primera fila de datos que sea claramente cabecera).
    if (!headerSkipped && looksLikeHeader(fields)) {
      headerSkipped = true;
      continue;
    }
    headerSkipped = true; // a partir de aquí, todo lo demás son datos
    const rsid = fields[0];
    if (!rsid || rsid.toLowerCase() === "rsid") continue;

    // 5 columnas -> genotipo = col3 + col4 (allele1 + allele2, formato AncestryDNA).
    // >= 4 columnas -> genotipo = col3 (formato 23andMe/FTDNA/MyHeritage/LivingDNA).
    let gtRaw;
    if (fields.length >= 5) gtRaw = (fields[3] || "") + (fields[4] || "");
    else gtRaw = fields[3] || "";

    snpCount++;
    const norm = normalizeCall(gtRaw);
    if (norm === null) continue; // no-llamada: se descarta, nunca se empareja
    called++;
    genotypes[rsid.toLowerCase()] = norm;
  }

  if (snpCount === 0) {
    throw new Error("No se pudo leer este archivo: formato de ADN no reconocido o vacío.");
  }

  // Omitimos la detección de versión del genoma (el emparejamiento es por rsID).
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
/* Porta app/core/annotation.py: recorre window.SEED.associations, resuelve la
 * hebra por variante y hace match genotipo-específico; luego resuelve el
 * haplotipo APOE desde rs429358 + rs7412. En el demo solo existe el seed curado
 * (no hay GWAS/ClinVar/PharmGKB). */

// Provenance fija del seed para el demo (equivale al source_release de build_seed,
// pero con el nombre mostrado en español que pide el demo).
const SEED_PROV = {
  source: "curated_seed",
  source_display: "Seed curado (educativo)",
  source_version: "2026-07 (curado)",
  source_date: "2026-07-01T00:00:00Z",
  release_date: "2026-07 (curado)",
};

function zygosity(genotype) {
  return new Set(genotype.split("")).size === 1 ? "homozygous" : "heterozygous";
}

function assocForwardSet(a) {
  // Espejo de _forward_pair: usa el par de alelos directos declarado en el seed.
  const s = forwardAlleleSet(a.alleles_forward);
  return s;
}

function matchAssociation(a, userGt) {
  const forward = assocForwardSet(a);
  const ambiguous = !!a.ambiguous_strand;
  const res = toForward(userGt, forward, ambiguous);
  if (res.withheld || res.genotype === null) return null;
  const fwdGt = res.genotype;
  const meta = a.genotypes[fwdGt];
  if (!meta) return null; // genotipo del usuario no está entre los interpretados

  return {
    rsid: a.rsid.toLowerCase(),
    user_genotype: userGt,
    resolved_genotype: fwdGt,
    gene: a.gene,
    trait: a.trait,
    category: a.category,
    sensitivity: a.sensitivity,
    is_health: a.sensitivity === "health",
    effect_text: meta.effect || "",
    carrier_note: "",
    magnitude: meta.magnitude,
    plain_summary: a.plain_summary,
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
    if (raw === undefined) return null; // falta un SNP miembro
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
    category: hap.category,
    sensitivity: hap.sensitivity || "health",
    is_health: (hap.sensitivity || "health") === "health",
    effect_text: dip.effect,
    carrier_note: "",
    magnitude: dip.magnitude,
    plain_summary: hap.plain_summary,
    risk_allele: null,
    zygosity: "diplotipo",
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

/* Ordena como consolidate() en Python: por categoría, salud primero dentro de
 * cada categoría, luego mayor relevancia. Array.sort es estable (ES2019+), así
 * que los empates conservan el orden del seed. */
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

/* Punto de entrada: dado el mapa de genotipos del usuario, devuelve el array de
 * coincidencias ya ordenado, listo para renderizar. */
function annotateLocal(genotypes) {
  const seed = window.SEED || {};
  const associations = seed.associations || [];
  const haplotypes = seed.haplotypes || [];

  const assocByRsid = {};
  for (const a of associations) assocByRsid[a.rsid.toLowerCase()] = a;

  const matches = [];
  // Recorre las asociaciones en el orden del seed (empates estables).
  for (const a of associations) {
    const rsid = a.rsid.toLowerCase();
    const userGt = genotypes[rsid];
    if (userGt === undefined) continue;
    const m = matchAssociation(a, userGt);
    if (m) matches.push(m);
  }
  // Haplotipos (APOE) al final, como en store.match().
  for (const hap of haplotypes) {
    const m = matchHaplotype(hap, genotypes, assocByRsid);
    if (m) matches.push(m);
  }

  return consolidateOrder(matches);
}

/* Exponer como globales (los scripts se cargan como <script> clásicos, sin módulos). */
window.parseDNA = parseDNA;
window.normalizeCall = normalizeCall;
window.toForward = toForward;
window.annotateLocal = annotateLocal;
