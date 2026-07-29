"use strict";
/* ASSAY frontend — DEMO ESTÁTICO. NO hay backend: leer el archivo, normalizar la
   hebra y emparejar rasgos ocurre 100% EN EL NAVEGADOR (ver engine.js). Cero
   llamadas de red: el archivo se lee con File.text() y jamás sale del navegador.
   Solo se usa el seed curado embebido en window.SEED. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const CAT_LABELS = {
  appearance: "Apariencia", taste_and_smell: "Gusto y olfato",
  diet_and_metabolism: "Dieta y metabolismo", physical_performance: "Rendimiento físico",
  sensory_and_reflex: "Sentidos y reflejos", behavioral_neuro_soft: "Conducta (leve)",
  carrier_and_metabolic_health: "Portador y metabólico", complex_disease_risk: "Riesgo de enfermedad",
  pharmacogenomics: "Farmacogenómica", gwas_risk: "Asociaciones GWAS",
  clinical_significance: "Clínico (ClinVar)",
};
const SOURCE_CHIP = {
  curated_seed: ["seed", "Curado"], gwas_catalog: ["gwas", "GWAS Catalog"],
  clinvar: ["clinvar", "ClinVar"], pharmgkb: ["pharmgkb", "PharmGKB"],
};

const state = {
  sessionId: null,
  matches: [],
  meta: null,
  activeCat: "__all__",
  query: "",
  effectOnly: false,
  healthRevealed: false,
  catGroups: new Map(), // category -> {wrap, list, count, isHealth}
  selected: new Set(), // Set of match objects chosen for the report
};

/* ------------------------------------------------------------------ theme */
function initTheme() {
  const saved = localStorage.getItem("assay-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  $("#btn-theme").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const isDark = cur === "dark" || (cur !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
    const next = isDark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("assay-theme", next);
  });
}

/* ---------------------------------------------------------------- upload */
function initUpload() {
  const dz = $("#dropzone"), input = $("#file-input");
  $("#btn-browse").addEventListener("click", (e) => { e.stopPropagation(); input.click(); });
  dz.addEventListener("click", () => input.click());
  dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => { if (input.files[0]) handleFile(input.files[0]); });

  const overlay = $("#drag-overlay");
  let depth = 0;
  window.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; overlay.classList.add("show"); });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("dragleave", (e) => { e.preventDefault(); if (--depth <= 0) overlay.classList.remove("show"); });
  window.addEventListener("drop", (e) => {
    e.preventDefault(); depth = 0; overlay.classList.remove("show");
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  });
  $("#btn-reset").addEventListener("click", resetAll);

  const btnExample = $("#btn-example");
  if (btnExample) btnExample.addEventListener("click", loadExampleFile);
}

/* ----------------------------------------------------- archivo de ejemplo */
/* Genotipos de ejemplo (JAMÁS datos reales): una mezcla divertida por categorías
   + un par de resultados de salud para ver la puerta de salud y el haplotipo APOE.
   Todos están en hebra directa, así que emparejan sin necesidad de complementar. */
const EXAMPLE_GENOTYPES = [
  // Apariencia
  ["rs12913832", "15", 28365618, "GG"], // ojos azules
  ["rs1426654", "15", 48426484, "AA"],  // piel más clara
  ["rs1805007", "16", 89986117, "CT"],  // portador/a pelo rojo
  ["rs12203592", "6", 396321, "CT"],    // pecas/bronceado intermedio
  // Gusto y olfato
  ["rs713598", "7", 141673345, "GG"],   // catador/a amargo (palindrómico C/G)
  ["rs17822931", "16", 48258198, "CT"], // cerumen húmedo
  ["rs72921001", "11", 6889648, "CC"],  // cilantro sabe a jabón
  // Dieta y metabolismo
  ["rs4988235", "2", 136608646, "AA"],  // tolera la lactosa
  ["rs762551", "15", 75041917, "AA"],   // cafeína rápida
  ["rs671", "12", 112241766, "AG"],     // rubor con el alcohol
  // Rendimiento físico
  ["rs1815739", "11", 66328095, "CC"],  // fibra rápida (sprint)
  // Sentidos / conducta
  ["rs10427255", "2", 146125523, "CC"], // estornudo con la luz
  ["rs4680", "22", 19951271, "AG"],     // COMT intermedio
  // Salud (activan la puerta de salud) + haplotipo APOE ε4/ε4
  ["rs429358", "19", 45411941, "CC"],   // APOE sitio 1
  ["rs7412", "19", 45412079, "CC"],     // APOE sitio 2  -> ε4/ε4
  ["rs1800562", "6", 26093141, "AG"],   // HFE C282Y portador/a
  ["rs9939609", "16", 53820527, "AA"],  // FTO IMC (palindrómico A/T)
];

// PRNG determinista (mulberry32) para que el relleno sea reproducible sin depender
// de Math.random y sin comprometer nada — son filas sintéticas de descarte.
function makeRng(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* Construye un texto en formato 23andMe con los genotipos conocidos + ~600 filas
   de relleno aleatorias (rsIDs altos que no colisionan con el seed). */
function buildExampleText() {
  const seedRsids = new Set(
    ((window.SEED || {}).associations || []).map((a) => a.rsid.toLowerCase())
  );
  const lines = [
    "# Archivo de EJEMPLO generado por ASSAY (demo) — datos SINTÉTICOS, no reales.",
    "# Formato compatible con 23andMe. Nada de esto pertenece a una persona real.",
    "# rsid\tchromosome\tposition\tgenotype",
  ];

  // Filas conocidas primero (así el ejemplo es legible si alguien lo inspecciona).
  for (const [rsid, chrom, pos, gt] of EXAMPLE_GENOTYPES) {
    lines.push(`${rsid}\t${chrom}\t${pos}\t${gt}`);
  }

  // ~600 filas de relleno aleatorias.
  const rng = makeRng(20260709);
  const bases = "ACGT";
  const pick = () => bases[Math.floor(rng() * 4)];
  const FILLER = 600;
  let made = 0;
  let n = 1_000_000;
  while (made < FILLER) {
    n += 1 + Math.floor(rng() * 5000);
    const rsid = "rs" + n;
    if (seedRsids.has(rsid)) continue; // no colisionar con el seed
    const chrom = 1 + Math.floor(rng() * 22);
    const pos = 10000 + Math.floor(rng() * 240000000);
    const gt = pick() + pick();
    lines.push(`${rsid}\t${chrom}\t${pos}\t${gt}`);
    made++;
  }

  return lines.join("\n") + "\n";
}

function loadExampleFile() {
  const text = buildExampleText();
  const file = new File([text], "ejemplo-assay-23andme.txt", { type: "text/plain" });
  handleFile(file);
}

async function handleFile(file) {
  $("#landing-error").hidden = true;
  setMeter(0.08, true);

  // Leer el archivo EN EL NAVEGADOR — nunca sale de esta máquina, no se sube.
  let text;
  try {
    text = await file.text();
  } catch (err) {
    setMeter(0, false);
    return showLandingError("No se pudo leer el archivo.");
  }

  // Parsear localmente (engine.js). Detecta proveedor y extrae rsid -> genotipo.
  let parsed;
  try {
    parsed = parseDNA(text, file.name);
  } catch (err) {
    setMeter(0, false);
    return showLandingError(
      "No se pudo leer este archivo: formato de ADN no reconocido o vacío."
    );
  }
  if (!parsed || parsed.snp_count === 0) {
    setMeter(0, false);
    return showLandingError(
      "No se pudo leer este archivo: formato de ADN no reconocido o vacío."
    );
  }

  // NO fijamos state.sessionId: no hay sesión de servidor que purgar (el DELETE de
  // pagehide queda inhibido). Los genotipos viven solo en RAM del navegador.
  fillInstrumentBar(parsed);
  enterResultsView();
  annotate(parsed);
}

function showLandingError(msg) {
  const el = $("#landing-error"); el.textContent = msg; el.hidden = false;
  setMeter(0, false);
}

function fillInstrumentBar(d) {
  $("#stat-vendor").textContent = d.vendor || "—";
  $("#stat-build").textContent = d.build ? `GRCh${d.build === 36 ? 36 : d.build === 38 ? 38 : 37}` : "—";
  $("#stat-snps").textContent = (d.snp_count || 0).toLocaleString();
  $("#btn-reset").hidden = false;
  if (d.warnings && d.warnings.length) {
    $("#stat-build").title = d.warnings.join(" ");
  }
}

/* -------------------------------------------------------------- annotate */
/* Anotación 100% local. Construye la metadata desde window.SEED, empareja con
   engine.js (annotateLocal) y renderiza en tandas con setTimeout para conservar
   el efecto de renderizado progresivo (sin SSE, sin red). */
function annotate(parsed) {
  clearResults();
  setMeter(0.15, true);

  // Metadata equivalente al evento "meta" del backend, pero armada localmente.
  const seed = window.SEED || {};
  const recordCount =
    (seed.associations ? seed.associations.length : 0) +
    (seed.haplotypes ? seed.haplotypes.length : 0);
  const sources = [{
    source: "curated_seed",
    display_name: "Seed curado (educativo)",
    version: "2026-07 (curado)",
    ingested_at: "2026-07-01T00:00:00Z",
    record_count: recordCount,
    origin: "seed",
    license: "MIT",
  }];
  state.meta = {
    vendor: parsed.vendor,
    build: parsed.build,
    snp_count: parsed.snp_count,
    called_count: parsed.called_count,
    sources,
    disclaimers: seed.disclaimers || {},
    categories: seed.trait_categories || [],
  };
  applyDisclaimers(state.meta.disclaimers);
  renderSources(sources);

  // Emparejar (rápido, en memoria) contra el seed curado.
  const matches = annotateLocal(parsed.genotypes);
  const total = matches.length;
  const counts_by_category = {};
  let health_count = 0;
  for (const m of matches) {
    counts_by_category[m.category] = (counts_by_category[m.category] || 0) + 1;
    if (m.is_health) health_count++;
  }

  // Render progresivo en tandas para un efecto tipo "streaming" local.
  const BATCH = 8;
  let i = 0;
  const step = () => {
    const slice = matches.slice(i, i + BATCH);
    slice.forEach(addMatch);
    i += slice.length;
    updateCounts();
    if (total) setMeter(0.15 + 0.85 * (i / total), true);
    if (i < total) {
      setTimeout(step, 40);
    } else {
      finishAnnotate({ total, counts_by_category, health_count });
    }
  };
  if (total === 0) {
    finishAnnotate({ total, counts_by_category, health_count });
  } else {
    step();
  }
}

function finishAnnotate(data) {
  setMeter(1, true);
  setTimeout(() => setMeter(0, false), 400);
  $("#stat-matches").textContent = (data.total || 0).toLocaleString();
  const hc = data.health_count || 0;
  if (hc > 0 && !state.healthRevealed) {
    $("#health-gate").hidden = false;
    $("#health-count-inline").textContent = hc;
  }
  updateCounts();
  if ((data.total || 0) === 0) {
    $("#empty-note").hidden = false;
    $("#empty-note").textContent = "No se encontraron asociaciones en tu archivo para las bases cargadas. Puede que tu chip no incluya estos marcadores.";
  }
}

/* -------------------------------------------------------------- rendering */
function catLabel(cat) { return CAT_LABELS[cat] || cat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()); }

function ensureCatGroup(cat, isHealth) {
  if (state.catGroups.has(cat)) return state.catGroups.get(cat);
  const wrap = document.createElement("div");
  wrap.className = "cat-block"; wrap.dataset.cat = cat;
  const header = document.createElement("div");
  header.className = "cat-header"; header.textContent = catLabel(cat);
  const list = document.createElement("div"); list.className = "cat-list";
  wrap.append(header, list);
  $("#results").append(wrap);

  // rail item
  const rail = $("#category-rail");
  const btn = document.createElement("button");
  btn.className = "rail-item" + (isHealth ? " health" : "");
  btn.dataset.cat = cat;
  btn.innerHTML = `<span class="rail-label">${catLabel(cat)}</span><span class="rail-count mono" data-count>0</span>`;
  btn.addEventListener("click", () => setActiveCat(cat));
  rail.append(btn);

  const g = { wrap, list, count: 0, isHealth };
  state.catGroups.set(cat, g);
  return g;
}

function addMatch(m) {
  state.matches.push(m);
  const g = ensureCatGroup(m.category, m.is_health);
  g.count++;
  const row = buildRow(m);
  g.list.append(row);
  applyRowVisibility(row, m);
}

function buildRow(m) {
  const tpl = $("#tpl-result-row").content.cloneNode(true);
  const row = tpl.querySelector(".row");
  row.dataset.cat = m.category;
  row.dataset.health = m.is_health ? "1" : "0";
  row._m = m;

  // Per-row selection checkbox (for the local report). Selection is keyed on the
  // match object itself, so it survives filtering (refilter only toggles hidden).
  const chk = tpl.querySelector(".chk-row");
  row._chk = chk;
  chk.checked = state.selected.has(m);
  // Stop propagation on the whole label (not just the input) so clicking the
  // label's padding never bubbles to <summary> and toggles the <details>.
  const chkLabel = chk.closest(".row-check") || chk;
  chkLabel.addEventListener("click", (e) => e.stopPropagation());
  chk.addEventListener("change", (e) => {
    e.stopPropagation();
    if (chk.checked) state.selected.add(m); else state.selected.delete(m);
    row.classList.toggle("is-selected", chk.checked);
    syncSelectionUI();
  });
  row.classList.toggle("is-selected", chk.checked);
  row._searchText = `${m.trait || ""} ${m.gene || ""} ${m.rsid || ""} ${m.effect_text || ""}`.toLowerCase();
  row._hasEffect = (m.magnitude || 0) >= 1.5;

  const meaning = m.effect_text || "";
  tpl.querySelector(".geno").textContent = m.resolved_genotype || m.user_genotype || "—";
  const traitEl = tpl.querySelector(".row-trait");
  traitEl.textContent = m.trait || m.rsid;
  if (m.gene) { const g = document.createElement("span"); g.className = "row-gene mono"; g.textContent = " " + m.gene; traitEl.append(g); }
  // The brief, plain-language "what this means" line lives right under the trait.
  tpl.querySelector(".row-meaning").textContent = truncate(meaning, 130);

  // provenance chip + freshness dot
  const [chipClass, chipLabel] = SOURCE_CHIP[m.source] || ["seed", m.source_display || m.source];
  const src = tpl.querySelector(".row-source");
  const chip = document.createElement("span"); chip.className = `chip ${chipClass}`; chip.textContent = chipLabel;
  const dot = document.createElement("span"); dot.className = `dot ${freshnessClass(m.source_date)}`;
  dot.title = m.source_date ? `En caché: ${m.source_date}` : "actualidad desconocida";
  src.append(chip, dot);

  // detail — full readable explanation, then extra context, then technical meta
  const explain = meaning + (m.carrier_note ? " " + m.carrier_note : "");
  tpl.querySelector(".row-explain-text").textContent = explain;
  const ctx = tpl.querySelector(".row-context");
  if (m.plain_summary) ctx.textContent = m.plain_summary; else ctx.hidden = true;
  tpl.querySelector(".row-meta").innerHTML = metaLine(m);
  if (m.is_health) tpl.querySelector(".row-health-note").hidden = false;
  if (m.flipped || (m.strand_note && m.ambiguous_strand)) {
    const sn = tpl.querySelector(".row-strand-note");
    sn.hidden = false; sn.textContent = "⤿ " + m.strand_note;
  }
  return row;
}

function metaLine(m) {
  const bits = [];
  if (m.rsid) bits.push(`<b>rsID</b> ${m.rsid}`);
  if (m.chrom) bits.push(`<b>crom</b> ${m.chrom}${m.pos_b37 ? ":" + m.pos_b37 : ""}`);
  if (m.risk_allele) bits.push(`<b>alelo de riesgo</b> ${m.risk_allele}`);
  if (m.magnitude != null) bits.push(`<b>relevancia</b> ${m.magnitude}`);
  if (m.confidence) bits.push(`<b>evidencia</b> ${escapeHtml(m.confidence)}`);
  bits.push(`<b>fuente</b> ${escapeHtml(m.source_display || m.source)} ${m.release_date ? "· " + m.release_date : ""}`);
  if (m.citation) bits.push(`<b>ref</b> ${escapeHtml(String(m.citation))}`);
  if (m.truncated_count) bits.push(`<b>+${m.truncated_count} más</b> de esta fuente`);
  return bits.join(" ");
}

/* ------------------------------------------------------------- filtering */
function applyRowVisibility(row, m) {
  const catOk = state.activeCat === "__all__" || state.activeCat === m.category;
  const healthOk = !m.is_health || state.healthRevealed;
  const effOk = !state.effectOnly || row._hasEffect;
  const searchOk = !state.query || row._searchText.includes(state.query);
  row.hidden = !(catOk && healthOk && effOk && searchOk);
}

function refilter() {
  let visible = 0;
  for (const g of state.catGroups.values()) {
    let gv = 0;
    for (const row of g.list.children) {
      applyRowVisibility(row, row._m);
      if (!row.hidden) { gv++; visible++; }
    }
    g.wrap.hidden = gv === 0;
  }
  const total = state.matches.length;
  $("#search-count").textContent = state.query || state.effectOnly || state.activeCat !== "__all__"
    ? `Mostrando ${visible} de ${total}` : "";
  $("#empty-note").hidden = !(total > 0 && visible === 0);
  if (total > 0 && visible === 0) $("#empty-note").textContent = "Ningún resultado coincide con tus filtros.";
}

function updateCounts() {
  let all = 0;
  for (const [cat, g] of state.catGroups) {
    const shown = g.isHealth && !state.healthRevealed ? g.count : g.count;
    const btn = $(`.rail-item[data-cat="${CSS.escape(cat)}"] [data-count]`);
    if (btn) btn.textContent = g.count;
    all += g.count;
  }
  const allBtn = $('.rail-item[data-cat="__all__"] [data-count]');
  if (allBtn) allBtn.textContent = all;
}

function setActiveCat(cat) {
  state.activeCat = cat;
  $$(".rail-item").forEach((b) => b.classList.toggle("active", b.dataset.cat === cat));
  refilter();
}

/* ------------------------------------------------------------ disclaimers */
function applyDisclaimers(d) {
  if (!d) return;
  if (d.global_banner) $("#disclaimer-text").textContent = d.global_banner;
  // Surface the strongest health disclaimers (incl. the explicit "never change
  // medication/dosing" language) on the health gate.
  if (d.health_result) $("#health-gate-detail").textContent = d.health_result;
  if (d.false_positive_note) $("#health-gate-fp").textContent = d.false_positive_note;
}

/* ------------------------------------------------------ sources / freshness */
function freshnessClass(dateStr) {
  if (!dateStr) return "";
  const d = Date.parse(dateStr);
  if (isNaN(d)) return "";
  const days = (Date.now() - d) / 86400000;
  return days < 45 ? "fresh" : days < 180 ? "aging" : "stale";
}

function renderSources(sources) {
  const list = $("#sources-list");
  list.innerHTML = "";
  let freshest = "stale";
  (sources || []).forEach((s) => {
    const card = document.createElement("div");
    card.className = "source-card";
    const fc = freshnessClass(s.ingested_at);
    if (fc === "fresh") freshest = "fresh"; else if (fc === "aging" && freshest !== "fresh") freshest = "aging";
    card.innerHTML =
      `<h3><span class="dot ${fc}"></span> ${escapeHtml(s.display_name || s.source)}
         <span class="chip ${(SOURCE_CHIP[s.source] || ["seed"])[0]}">${(s.origin || "").toUpperCase()}</span></h3>
       <div class="meta">
         <span>release / version: ${escapeHtml(s.version || "—")}</span>
         <span>ingested: ${escapeHtml((s.ingested_at || "—").replace("T", " ").replace("Z", " UTC"))}</span>
         <span>records: ${(s.record_count || 0).toLocaleString()}</span>
         <span>license: ${escapeHtml(s.license || "—")}</span>
       </div>`;
    list.append(card);
  });
  $("#fresh-dot").className = "dot " + freshest;
}

function initDrawer() {
  const drawer = $("#freshness-drawer"), backdrop = $("#drawer-backdrop");
  // Fuente por defecto del demo (el seed curado). Sin red: si aún no se ha anotado,
  // mostramos igualmente la ficha del seed embebido.
  const seedSource = () => {
    const seed = window.SEED || {};
    const recordCount =
      (seed.associations ? seed.associations.length : 0) +
      (seed.haplotypes ? seed.haplotypes.length : 0);
    return [{
      source: "curated_seed",
      display_name: "Seed curado (educativo)",
      version: "2026-07 (curado)",
      ingested_at: "2026-07-01T00:00:00Z",
      record_count: recordCount,
      origin: "seed",
      license: "MIT",
    }];
  };
  const open = () => {
    if (!state.meta) renderSources(seedSource());
    drawer.hidden = false; backdrop.hidden = false;
  };
  const close = () => { drawer.hidden = true; backdrop.hidden = true; };
  $("#btn-freshness").addEventListener("click", open);
  $("#btn-close-drawer").addEventListener("click", close);
  backdrop.addEventListener("click", close);

  // En el demo estático no hay descarga de bases públicas (requiere backend local).
  // Deshabilitamos el botón y explicamos dónde está disponible.
  const btnUpdate = $("#btn-update");
  if (btnUpdate) {
    btnUpdate.disabled = true;
    btnUpdate.title = "Disponible en la versión local (descarga las bases completas)";
  }
  const note = $(".drawer-note");
  if (note) {
    note.textContent =
      "Disponible en la versión local (descarga las bases completas). Este demo funciona " +
      "solo con el seed curado y 100% en tu navegador; nada se descarga ni se sube.";
  }
}

/* ------------------------------------------------------------------ views */
function enterResultsView() {
  $("#landing").hidden = true;
  $("#results-view").hidden = false;
}

function clearResults() {
  state.selected.clear(); syncSelectionUI();
  state.matches = []; state.catGroups.clear();
  // Re-arma la puerta de salud y reinicia los filtros transitorios para cada
  // archivo nuevo, de modo que una anotación fresca siempre empiece sin filtrar
  // (por cualquier vía, incluido soltar un segundo archivo sobre los resultados).
  state.healthRevealed = false;
  state.activeCat = "__all__"; state.query = ""; state.effectOnly = false;
  const search = $("#search"); if (search) search.value = "";
  const fe = $("#filter-effect"); if (fe) fe.checked = false;
  $("#results").innerHTML = "";
  $$(".rail-item:not([data-cat='__all__'])").forEach((b) => b.remove());
  $$(".rail-item").forEach((b) => b.classList.toggle("active", b.dataset.cat === "__all__"));
  $("#search-count").textContent = "";
  $("#empty-note").hidden = true;
  $("#health-gate").hidden = true;
  $("#stat-matches").textContent = "0";
}

function resetAll() {
  // Sin sesión de servidor que purgar en el demo: los genotipos viven solo en la
  // memoria del navegador y se descartan al reemplazar el estado / recargar.
  state.sessionId = null; state.healthRevealed = false; state.activeCat = "__all__";
  state.query = ""; state.effectOnly = false; state.selected.clear();
  $("#search").value = ""; $("#filter-effect").checked = false;
  clearResults();
  $("#stat-vendor").textContent = "—"; $("#stat-build").textContent = "—"; $("#stat-snps").textContent = "0";
  $("#btn-reset").hidden = true;
  $("#results-view").hidden = true; $("#landing").hidden = false;
  setActiveCat("__all__");
}

/* ----------------------------------------------------------------- filters */
function initFilters() {
  $("#category-rail .rail-item[data-cat='__all__']").addEventListener("click", () => setActiveCat("__all__"));
  let t;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(t);
    t = setTimeout(() => { state.query = e.target.value.trim().toLowerCase(); refilter(); }, 150);
  });
  $("#filter-effect").addEventListener("change", (e) => { state.effectOnly = e.target.checked; refilter(); });
  $("#btn-show-health").addEventListener("click", () => {
    state.healthRevealed = true; $("#health-gate").hidden = true; refilter();
  });
}

/* -------------------------------------------------------- selection + report */
function syncSelectionUI() {
  const n = state.selected.size;
  const bar = $("#selection-bar");
  if (!bar) return;
  $("#sel-count").textContent = n + (n === 1 ? " seleccionado" : " seleccionados");
  bar.hidden = n === 0;
  $("#btn-report-html").disabled = n === 0;
  $("#btn-report-print").disabled = n === 0;
}

function selectAllVisible() {
  for (const g of state.catGroups.values()) {
    for (const row of g.list.children) {
      if (!row.hidden) {
        state.selected.add(row._m);
        row._chk.checked = true;
        row.classList.add("is-selected");
      }
    }
  }
  syncSelectionUI();
}

function clearSelection() {
  state.selected.clear();
  for (const g of state.catGroups.values()) {
    for (const row of g.list.children) {
      row._chk.checked = false;
      row.classList.remove("is-selected");
    }
  }
  syncSelectionUI();
}

/* Selected matches in the stable order of state.matches (groupable). */
function collectSelected() {
  return state.matches.filter((m) => state.selected.has(m));
}

/* Provenance line for the report: source · version/date · rsID (+ extras). */
function reportProvenance(m) {
  const bits = [];
  bits.push(escapeHtml(m.source_display || m.source || "—"));
  const ver = m.source_version || m.source_date || m.release_date;
  if (ver) bits.push(escapeHtml(String(ver)));
  if (m.rsid) bits.push(escapeHtml(m.rsid));
  if (m.chrom) bits.push("crom " + escapeHtml(m.chrom) + (m.pos_b37 ? ":" + escapeHtml(String(m.pos_b37)) : ""));
  if (m.risk_allele) bits.push("alelo de riesgo " + escapeHtml(m.risk_allele));
  if (m.magnitude != null) bits.push("relevancia " + escapeHtml(String(m.magnitude)));
  return bits.join(" · ");
}

const REPORT_HEALTH_NOTE =
  "⚠ Relacionado con la salud — no es un diagnóstico. Los datos crudos de consumo se equivocan " +
  "cerca del 40% de las veces en variantes clínicamente relevantes. Confírmalo con una prueba de " +
  "grado clínico y un/a profesional antes de actuar.";

/* Pure function: returns a fully self-contained HTML document string. No network,
   no <script> (CSP script-src 'self'), only an embedded <style> (style-src allows it). */
function buildReportHTML(matches, meta) {
  const m0 = meta || {};
  const disc = m0.disclaimers || {};
  const vendor = m0.vendor || $("#stat-vendor").textContent || "—";
  const build = m0.build ? ("GRCh" + m0.build) : ($("#stat-build").textContent || "—");
  const snps = (m0.snp_count != null)
    ? m0.snp_count.toLocaleString()
    : ($("#stat-snps").textContent || "0");
  const fecha = new Date().toLocaleDateString("es-ES", { year: "numeric", month: "long", day: "numeric" });
  const nSel = matches.length;
  const anySalud = matches.some((m) => m.is_health);

  // Group by category, preserving first-appearance order.
  const order = [];
  const groups = new Map();
  for (const m of matches) {
    if (!groups.has(m.category)) { groups.set(m.category, []); order.push(m.category); }
    groups.get(m.category).push(m);
  }

  const style = `
    :root{color-scheme:light}
    *{box-sizing:border-box}
    body{margin:0;background:#FBFAF7;color:#1A1D21;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;
      font-size:14px;line-height:1.55;padding:32px 28px;max-width:900px;margin:0 auto}
    .mono{font-family:ui-monospace,Consolas,"Roboto Mono",monospace;font-variant-numeric:tabular-nums}
    .rep-head{border-bottom:2px solid #0E7C86;padding-bottom:14px;margin-bottom:18px}
    .rep-title{font-weight:700;letter-spacing:.14em;font-size:20px;margin:0 0 8px}
    .rep-title small{font-weight:600;letter-spacing:.02em;color:#5B6169}
    .rep-readout{display:flex;flex-wrap:wrap;gap:6px 22px;font-size:12px;color:#5B6169;margin:6px 0}
    .rep-readout b{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#8A9099;font-weight:600}
    .rep-gen{font-size:12px;color:#8A9099;margin-top:4px}
    .avisos{border:1px solid #0E7C86;background:#E5F2F2;border-radius:8px;padding:12px 14px;margin-bottom:20px;font-size:12.5px}
    .avisos p{margin:0 0 8px}
    .avisos p:last-child{margin-bottom:0}
    .avisos-salud{border-left:3px solid #B42318;background:#FDECEA;border-radius:4px;padding:10px 12px;margin-top:10px}
    .avisos-salud p{color:#1A1D21}
    h2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#8A9099;
      border-bottom:1px solid #E7E4DC;padding:16px 0 6px;margin:0 0 4px;font-weight:600}
    .rep-item{border-bottom:1px solid #E7E4DC;padding:12px 2px}
    .rep-item-head{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
    .geno{font-size:14px;font-weight:600;letter-spacing:.5px;padding:2px 6px;
      border:1px solid #D8D4CA;border-radius:4px;white-space:nowrap}
    .rep-trait{font-weight:600;font-size:14px}
    .rep-gene{font-size:11.5px;color:#8A9099}
    .rep-explain{font-size:13px;margin:8px 0 0;max-width:80ch}
    .rep-context{font-size:12.5px;color:#5B6169;margin:6px 0 0;max-width:80ch}
    .rep-prov{font-size:11px;color:#8A9099;margin:8px 0 0}
    .rep-health-note{background:#FDECEA;border-left:3px solid #B42318;padding:8px 12px;
      border-radius:4px;font-size:12px;margin:10px 0 0;max-width:80ch}
    .rep-foot{margin-top:24px;padding-top:14px;border-top:1px solid #E7E4DC;font-size:11.5px;color:#8A9099}
    @media print{
      @page{margin:16mm}
      body{-webkit-print-color-adjust:exact;print-color-adjust:exact}
      .cat-block,.rep-item,.avisos{break-inside:avoid}
    }`;

  let avisos = "";
  if (disc.global_banner) avisos += `<p>${escapeHtml(disc.global_banner)}</p>`;
  if (anySalud && (disc.health_result || disc.false_positive_note)) {
    avisos += `<div class="avisos-salud">`;
    if (disc.health_result) avisos += `<p>${escapeHtml(disc.health_result)}</p>`;
    if (disc.false_positive_note) avisos += `<p>${escapeHtml(disc.false_positive_note)}</p>`;
    avisos += `</div>`;
  }

  let body = "";
  for (const cat of order) {
    body += `<div class="cat-block"><h2>${escapeHtml(catLabel(cat))}</h2>`;
    for (const m of groups.get(cat)) {
      const geno = escapeHtml(m.resolved_genotype || m.user_genotype || "—");
      const trait = escapeHtml(m.trait || m.rsid || "—");
      const gene = m.gene ? `<span class="rep-gene mono">${escapeHtml(m.gene)}</span>` : "";
      const explain = escapeHtml((m.effect_text || "") + (m.carrier_note ? " " + m.carrier_note : "")).trim();
      const context = m.plain_summary ? `<p class="rep-context">${escapeHtml(m.plain_summary)}</p>` : "";
      const health = m.is_health ? `<p class="rep-health-note">${escapeHtml(REPORT_HEALTH_NOTE)}</p>` : "";
      body +=
        `<div class="rep-item">
          <div class="rep-item-head">
            <span class="geno mono">${geno}</span>
            <span class="rep-trait">${trait}</span>${gene}
          </div>
          ${explain ? `<p class="rep-explain">${explain}</p>` : ""}
          ${context}
          <p class="rep-prov mono">${reportProvenance(m)}</p>
          ${health}
        </div>`;
    }
    body += `</div>`;
  }

  return `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ASSAY — Reporte de rasgos</title>
<style>${style}</style>
</head>
<body>
<div class="rep-head">
  <h1 class="rep-title">ASSAY <small>— Reporte de rasgos</small></h1>
  <div class="rep-readout">
    <span><b>proveedor</b>${escapeHtml(String(vendor))}</span>
    <span><b>versión</b>${escapeHtml(String(build))}</span>
    <span><b>SNPs</b><span class="mono">${escapeHtml(String(snps))}</span></span>
    <span><b>seleccionados</b><span class="mono">${nSel}</span></span>
  </div>
  <div class="rep-gen">Generado localmente el ${escapeHtml(fecha)} — nada sale de tu dispositivo.</div>
</div>
${avisos ? `<section class="avisos">${avisos}</section>` : ""}
${body}
<div class="rep-foot">Solo con fines educativos y de investigación — no es un diagnóstico. Generado localmente el ${escapeHtml(fecha)}.</div>
</body>
</html>`;
}

function downloadReportHTML() {
  const sel = collectSelected();
  if (!sel.length) return;
  const html = buildReportHTML(sel, state.meta);
  const blob = new Blob([html], { type: "text/html" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  const d = new Date();
  const stamp = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  a.download = "reporte-assay-" + stamp + ".html";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 0);
}

function printReport() {
  const sel = collectSelected();
  if (!sel.length) return;
  const html = buildReportHTML(sel, state.meta);
  const w = window.open("", "_blank");
  if (!w) {
    alert("El navegador bloqueó la ventana emergente. Usa «Descargar HTML» y ábrelo para imprimir.");
    return;
  }
  w.document.open(); w.document.write(html); w.document.close(); w.focus();
  // print() is invoked from THIS parent window (app.js = 'self'); no script is
  // injected into the child document, so CSP script-src 'self' is respected.
  // Guard so onload + the fallback timer never raise two print dialogs.
  let printed = false;
  const doPrint = () => { if (printed) return; printed = true; try { w.print(); } catch (e) { /* ignore */ } };
  w.onload = doPrint;
  setTimeout(doPrint, 400);
}

function initReport() {
  $("#btn-select-visible").addEventListener("click", selectAllVisible);
  $("#btn-clear-sel").addEventListener("click", clearSelection);
  $("#btn-report-html").addEventListener("click", downloadReportHTML);
  $("#btn-report-print").addEventListener("click", printReport);
  syncSelectionUI();
}

/* ------------------------------------------------------------------ utils */
function setMeter(frac, show) {
  const m = $("#meter"), f = $("#meter-fill");
  m.hidden = !show; f.style.width = Math.round(frac * 100) + "%";
}
function truncate(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }

/* En el demo no hay sesión de servidor: nada que purgar al salir. Los genotipos
   viven solo en la memoria del navegador y desaparecen al recargar/cerrar. */

/* ------------------------------------------------------------------- init */
initTheme();
initUpload();
initFilters();
initDrawer();
initReport();
