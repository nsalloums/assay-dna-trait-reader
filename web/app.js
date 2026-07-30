"use strict";
/* ASSAY frontend. Talks only to the same-origin localhost API. No third-party
   requests (CSP connect-src 'self'). Your genotypes never leave this machine. */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* ------------------------------------------------------------------ i18n */
/* English is the canonical language; Spanish is an optional reading mode.
   Static UI text is tagged with data-i18n* in the HTML; seed-derived text
   (traits, effects, summaries, disclaimers) carries an `_es` sibling and is
   picked at render time by L(). */
const I18N = {
  en: {
    drag_overlay: "Drop your DNA file to read it — locally",
    brand_sub: "local DNA trait reader",
    stat_vendor: "vendor", stat_build: "build", stat_matches: "matches",
    btn_freshness: "Data sources", btn_freshness_title: "Data sources and freshness",
    btn_theme_title: "Toggle light/dark", btn_theme_aria: "Toggle theme",
    btn_reset: "Load another file",
    disclaimer_strong: "For educational and research use only — not a diagnosis.",
    disclaimer_text: "Everything runs locally; your DNA never leaves this machine. Consumer raw-data genotypes have a high false-positive rate (~40%) for clinically relevant variants — confirm any health result with a clinical-grade test and a professional.",
    dropzone_aria: "Upload a DNA file — drag and drop or press Enter to browse",
    drop_title: "Drop your DNA file",
    drop_privacy: "Processed <strong>on your device</strong> — files never leave this machine, and are not uploaded or stored.",
    btn_browse: "Choose a file…",
    btn_example: "Try a sample file",
    demo_badge: "<strong>Demo</strong> — everything runs in your browser; nothing is uploaded. Curated seed only (educational).",
    step1: "Drop a file — it's processed locally in seconds.",
    step2: "Traits appear grouped by category, with source and date.",
    step3: "Nothing is uploaded, logged, or stored. On reload, it's gone.",
    rail_aria: "Trait categories", rail_all: "All results",
    search_ph: "Filter by trait, gene, or rsID…", search_aria: "Filter results",
    filter_effect: "Only genotypes with an effect",
    health_gate_strong: "Health-related results are hidden.",
    health_gate_body: "These variants (carrier, disease risk, drug response) need extra care and clinical confirmation. Found",
    btn_show_health: "Show health results",
    selection_aria: "Selection actions",
    btn_select_visible: "Select all visible", btn_clear_sel: "Clear",
    btn_report_html: "Download HTML", btn_report_print: "Print / PDF",
    drawer_aria: "Annotation data sources", drawer_title: "Annotation data sources", close: "Close",
    drawer_lede: "The only time this app uses the network is to download these <strong>public</strong> annotation databases — never your genotypes.",
    btn_update: "Update from public databases",
    drawer_note: "Downloads public data (GWAS Catalog, ClinVar, PharmGKB) to this machine only. It's large; done once, then the app works offline.",
    src_version: "release / version", src_ingested: "ingested", src_records: "records", src_license: "license",
    row_explain_label: "What does it mean?",
    row_check_title: "Select for the report", row_check_aria: "Select this result for the report",
    row_health_note: "⚠ Health-related — <strong>not a diagnosis.</strong> Consumer raw data is wrong about 40% of the time for clinically relevant variants. Confirm with a clinical-grade test and a professional before acting.",
    meta_chrom: "chr", meta_risk: "risk allele", meta_relevance: "relevance",
    meta_evidence: "evidence", meta_source: "source", meta_ref: "ref",
    freshness_unknown: "freshness unknown",
    empty_no_assoc: "No associations were found in your file for the loaded databases. Your chip may not include these markers.",
    empty_no_filter: "No results match your filters.",
    err_connect: "Could not connect to the local server.",
    err_read: "Could not read this file.",
    err_annotate: "Annotation failed.",
    report_title: "Traits report", report_selected: "selected",
    popup_blocked: "The browser blocked the pop-up. Use “Download HTML” and open it to print.",
    update_starting: "Starting…\n", update_done: "Done.\n", update_failed: "Update failed: ",
  },
  es: {
    drag_overlay: "Suelta tu archivo de ADN para leerlo — localmente",
    brand_sub: "lector local de rasgos de ADN",
    stat_vendor: "proveedor", stat_build: "versión", stat_matches: "coincidencias",
    btn_freshness: "Fuentes de datos", btn_freshness_title: "Fuentes de datos y actualidad",
    btn_theme_title: "Cambiar claro/oscuro", btn_theme_aria: "Cambiar tema",
    btn_reset: "Cargar otro archivo",
    disclaimer_strong: "Solo con fines educativos y de investigación — no es un diagnóstico.",
    disclaimer_text: "Todo se ejecuta localmente; tu ADN nunca sale de esta máquina. Los genotipos de datos crudos de consumo tienen una alta tasa de falsos positivos (~40%) para variantes clínicamente relevantes — confirma cualquier resultado de salud con una prueba de grado clínico y un/a profesional.",
    dropzone_aria: "Sube un archivo de ADN — arrastra y suelta o pulsa Enter para explorar",
    drop_title: "Suelta tu archivo de ADN",
    drop_privacy: "Se procesa <strong>en tu dispositivo</strong> — los archivos nunca salen de esta máquina, no se suben ni se guardan.",
    btn_browse: "Elegir un archivo…",
    btn_example: "Probar con un archivo de ejemplo",
    demo_badge: "<strong>Demo</strong> — todo corre en tu navegador; nada se sube. Solo el seed curado (educativo).",
    step1: "Suelta un archivo — se procesa localmente en segundos.",
    step2: "Los rasgos aparecen agrupados por categoría, con fuente y fecha.",
    step3: "Nada se sube, se registra ni se guarda. Al recargar, desaparece.",
    rail_aria: "Categorías de rasgos", rail_all: "Todos los resultados",
    search_ph: "Filtrar por rasgo, gen o rsID…", search_aria: "Filtrar resultados",
    filter_effect: "Solo genotipos con efecto",
    health_gate_strong: "Los resultados relacionados con la salud están ocultos.",
    health_gate_body: "Estas variantes (portador, riesgo de enfermedad, respuesta a fármacos) requieren cuidado extra y confirmación clínica. Se encontraron",
    btn_show_health: "Ver resultados de salud",
    selection_aria: "Acciones de selección",
    btn_select_visible: "Seleccionar todos los visibles", btn_clear_sel: "Limpiar",
    btn_report_html: "Descargar HTML", btn_report_print: "Imprimir / PDF",
    drawer_aria: "Fuentes de datos de anotación", drawer_title: "Fuentes de datos de anotación", close: "Cerrar",
    drawer_lede: "La única vez que esta app usa la red es para descargar estas bases de datos <strong>públicas</strong> de anotación — nunca tus genotipos.",
    btn_update: "Actualizar desde bases públicas",
    drawer_note: "Descarga datos públicos (GWAS Catalog, ClinVar, PharmGKB) solo a esta máquina. Es grande; se hace una vez y luego la app funciona sin conexión.",
    src_version: "lanzamiento / versión", src_ingested: "importado", src_records: "registros", src_license: "licencia",
    row_explain_label: "¿Qué significa?",
    row_check_title: "Seleccionar para el reporte", row_check_aria: "Seleccionar este resultado para el reporte",
    row_health_note: "⚠ Relacionado con la salud — <strong>no es un diagnóstico.</strong> Los datos crudos de consumo se equivocan cerca del 40% de las veces en variantes clínicamente relevantes. Confírmalo con una prueba de grado clínico y un/a profesional antes de actuar.",
    meta_chrom: "crom", meta_risk: "alelo de riesgo", meta_relevance: "relevancia",
    meta_evidence: "evidencia", meta_source: "fuente", meta_ref: "ref",
    freshness_unknown: "actualidad desconocida",
    empty_no_assoc: "No se encontraron asociaciones en tu archivo para las bases cargadas. Puede que tu chip no incluya estos marcadores.",
    empty_no_filter: "Ningún resultado coincide con tus filtros.",
    err_connect: "No se pudo conectar con el servidor local.",
    err_read: "No se pudo leer este archivo.",
    err_annotate: "Falló la anotación.",
    report_title: "Reporte de rasgos", report_selected: "seleccionados",
    popup_blocked: "El navegador bloqueó la ventana emergente. Usa «Descargar HTML» y ábrelo para imprimir.",
    update_starting: "Iniciando…\n", update_done: "Listo.\n", update_failed: "Falló la actualización: ",
  },
};

const CAT_LABELS = {
  en: {
    appearance: "Appearance", taste_and_smell: "Taste & smell",
    diet_and_metabolism: "Diet & metabolism", physical_performance: "Physical performance",
    sensory_and_reflex: "Senses & reflexes", behavioral_neuro_soft: "Behavior (soft)",
    carrier_and_metabolic_health: "Carrier & metabolic", complex_disease_risk: "Disease risk",
    pharmacogenomics: "Pharmacogenomics", gwas_risk: "GWAS associations",
    clinical_significance: "Clinical (ClinVar)",
  },
  es: {
    appearance: "Apariencia", taste_and_smell: "Gusto y olfato",
    diet_and_metabolism: "Dieta y metabolismo", physical_performance: "Rendimiento físico",
    sensory_and_reflex: "Sentidos y reflejos", behavioral_neuro_soft: "Conducta (leve)",
    carrier_and_metabolic_health: "Portador y metabólico", complex_disease_risk: "Riesgo de enfermedad",
    pharmacogenomics: "Farmacogenómica", gwas_risk: "Asociaciones GWAS",
    clinical_significance: "Clínico (ClinVar)",
  },
};
const SOURCE_CHIP = {
  curated_seed: ["seed", "Curated"], gwas_catalog: ["gwas", "GWAS Catalog"],
  clinvar: ["clinvar", "ClinVar"], pharmgkb: ["pharmgkb", "PharmGKB"],
};

const state = {
  sessionId: null,
  matches: [],
  meta: null,
  lang: "en",
  activeCat: "__all__",
  query: "",
  effectOnly: false,
  healthRevealed: false,
  catGroups: new Map(), // category -> {wrap, list, count, isHealth}
  selected: new Set(), // Set of match objects chosen for the report
};

/* t: static UI string in the active language. L: localized seed field (falls
   back to the English base if the _es sibling is missing). */
function t(key) {
  const d = I18N[state.lang] || I18N.en;
  return key in d ? d[key] : (I18N.en[key] ?? key);
}
function L(obj, field) {
  if (!obj) return "";
  if (state.lang === "es") {
    const v = obj[field + "_es"];
    if (v != null && v !== "") return v;
  }
  return obj[field] ?? "";
}
function tShowing(v, total) { return state.lang === "es" ? `Mostrando ${v} de ${total}` : `Showing ${v} of ${total}`; }
function tSelected(n) { return state.lang === "es" ? `${n} ${n === 1 ? "seleccionado" : "seleccionados"}` : `${n} selected`; }

function applyStaticI18n() {
  document.documentElement.lang = state.lang;
  $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  $$("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
  $$("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  $$("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
  const lb = $("#btn-lang");
  if (lb) lb.textContent = state.lang === "es" ? "EN" : "ES";
}

function setLang(lang) {
  state.lang = lang === "es" ? "es" : "en";
  localStorage.setItem("assay-lang", state.lang);
  applyStaticI18n();
  if (state.meta) {
    applyDisclaimers(state.meta.disclaimers);
    renderSources(state.meta.sources);
  }
  if (state.matches.length) rerenderMatches();
  refilter();
  syncSelectionUI();
}

function initLang() {
  const saved = localStorage.getItem("assay-lang");
  state.lang = saved === "es" ? "es" : "en";
  applyStaticI18n();
  const lb = $("#btn-lang");
  if (lb) lb.addEventListener("click", () => setLang(state.lang === "es" ? "en" : "es"));
}

/* Rebuild the rendered results in the current language, preserving selection,
   health-gate state, and active category. Keeps the match objects intact. */
function rerenderMatches() {
  const saved = state.matches.slice();
  state.matches = [];
  state.catGroups.clear();
  $("#results").innerHTML = "";
  $$(".rail-item:not([data-cat='__all__'])").forEach((b) => b.remove());
  saved.forEach(addMatch);
  updateCounts();
  const hc = saved.filter((m) => m.is_health).length;
  $("#health-count-inline").textContent = hc;
  $("#health-gate").hidden = !(hc > 0 && !state.healthRevealed);
  $$(".rail-item").forEach((b) => b.classList.toggle("active", b.dataset.cat === state.activeCat));
}

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
}

async function handleFile(file) {
  $("#landing-error").hidden = true;
  setMeter(0.08, true);
  let res;
  try {
    // Raw body (not multipart) so the server never spools to disk; the custom
    // header forces a same-origin CORS preflight.
    res = await fetch("/api/parse", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream", "X-Filename": file.name },
      body: file,
    });
  } catch (err) { return showLandingError(t("err_connect")); }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    setMeter(0, false);
    return showLandingError(j.detail || t("err_read"));
  }
  const data = await res.json();
  state.sessionId = data.session_id;
  fillInstrumentBar(data);
  enterResultsView();
  annotate();
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
async function annotate() {
  clearResults();
  setMeter(0.15, true);
  const res = await fetch("/api/annotate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessionId }),
  });
  if (!res.ok) { setMeter(0, false); return showLandingError(t("err_annotate")); }

  await readSSE(res, (event, data) => {
    if (event === "meta") {
      state.meta = data;
      applyDisclaimers(data.disclaimers);
      renderSources(data.sources);
    } else if (event === "matches") {
      data.rows.forEach(addMatch);
      updateCounts();
    } else if (event === "progress") {
      if (data.total) setMeter(0.15 + 0.85 * (data.done / data.total), true);
    } else if (event === "done") {
      finishAnnotate(data);
    }
  });
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
    $("#empty-note").textContent = t("empty_no_assoc");
  }
}

/* Parse an SSE stream from a fetch Response (EventSource is GET-only). */
async function readSSE(res, onEvent) {
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let ev = "message", dataLines = [];
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) {
        try { onEvent(ev, JSON.parse(dataLines.join("\n"))); } catch (e) { /* ignore */ }
      }
    }
  }
}

/* -------------------------------------------------------------- rendering */
function catLabel(cat) {
  const d = CAT_LABELS[state.lang] || CAT_LABELS.en;
  return d[cat] || CAT_LABELS.en[cat] || cat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

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
  tpl.querySelector(".row-check").title = t("row_check_title");
  chk.setAttribute("aria-label", t("row_check_aria"));
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

  const trait = L(m, "trait") || m.rsid || "";
  const meaning = L(m, "effect_text");
  const summary = L(m, "plain_summary");
  const carrier = L(m, "carrier_note");
  row._searchText = `${trait} ${m.gene || ""} ${m.rsid || ""} ${meaning}`.toLowerCase();
  row._hasEffect = (m.magnitude || 0) >= 1.5;

  tpl.querySelector(".geno").textContent = m.resolved_genotype || m.user_genotype || "—";
  const traitEl = tpl.querySelector(".row-trait");
  traitEl.textContent = trait;
  if (m.gene) { const g = document.createElement("span"); g.className = "row-gene mono"; g.textContent = " " + m.gene; traitEl.append(g); }
  // The brief, plain-language "what this means" line lives right under the trait.
  tpl.querySelector(".row-meaning").textContent = truncate(meaning, 130);

  // provenance chip + freshness dot
  const [chipClass, chipLabel] = SOURCE_CHIP[m.source] || ["seed", m.source_display || m.source];
  const src = tpl.querySelector(".row-source");
  const chip = document.createElement("span"); chip.className = `chip ${chipClass}`; chip.textContent = chipLabel;
  const dot = document.createElement("span"); dot.className = `dot ${freshnessClass(m.source_date)}`;
  dot.title = m.source_date ? `${state.lang === "es" ? "En caché" : "Cached"}: ${m.source_date}` : t("freshness_unknown");
  src.append(chip, dot);

  // detail — full readable explanation, then extra context, then technical meta
  const explain = meaning + (carrier ? " " + carrier : "");
  tpl.querySelector(".row-explain-label").textContent = t("row_explain_label");
  tpl.querySelector(".row-explain-text").textContent = explain;
  const ctx = tpl.querySelector(".row-context");
  if (summary) ctx.textContent = summary; else ctx.hidden = true;
  tpl.querySelector(".row-meta").innerHTML = metaLine(m);
  if (m.is_health) {
    const hn = tpl.querySelector(".row-health-note");
    hn.hidden = false; hn.innerHTML = t("row_health_note");
  }
  if (m.flipped || (m.strand_note && m.ambiguous_strand)) {
    const sn = tpl.querySelector(".row-strand-note");
    sn.hidden = false; sn.textContent = "⤿ " + m.strand_note;
  }
  return row;
}

function metaLine(m) {
  const bits = [];
  if (m.rsid) bits.push(`<b>rsID</b> ${m.rsid}`);
  if (m.chrom) bits.push(`<b>${t("meta_chrom")}</b> ${m.chrom}${m.pos_b37 ? ":" + m.pos_b37 : ""}`);
  if (m.risk_allele) bits.push(`<b>${t("meta_risk")}</b> ${m.risk_allele}`);
  if (m.magnitude != null) bits.push(`<b>${t("meta_relevance")}</b> ${m.magnitude}`);
  if (m.confidence) bits.push(`<b>${t("meta_evidence")}</b> ${escapeHtml(m.confidence)}`);
  bits.push(`<b>${t("meta_source")}</b> ${escapeHtml(m.source_display || m.source)} ${m.release_date ? "· " + m.release_date : ""}`);
  if (m.citation) bits.push(`<b>${t("meta_ref")}</b> ${escapeHtml(String(m.citation))}`);
  if (m.truncated_count) {
    bits.push(state.lang === "es"
      ? `<b>+${m.truncated_count} más</b> de esta fuente`
      : `<b>+${m.truncated_count} more</b> from this source`);
  }
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
    ? tShowing(visible, total) : "";
  $("#empty-note").hidden = !(total > 0 && visible === 0);
  if (total > 0 && visible === 0) $("#empty-note").textContent = t("empty_no_filter");
}

function updateCounts() {
  let all = 0;
  for (const [cat, g] of state.catGroups) {
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
  const pick = (k) => (state.lang === "es" && d[k + "_es"]) ? d[k + "_es"] : d[k];
  if (d.global_banner) $("#disclaimer-text").textContent = pick("global_banner");
  // Surface the strongest health disclaimers (incl. the explicit "never change
  // medication/dosing" language) on the health gate.
  if (d.health_result) $("#health-gate-detail").textContent = pick("health_result");
  if (d.false_positive_note) $("#health-gate-fp").textContent = pick("false_positive_note");
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
         <span>${t("src_version")}: ${escapeHtml(s.version || "—")}</span>
         <span>${t("src_ingested")}: ${escapeHtml((s.ingested_at || "—").replace("T", " ").replace("Z", " UTC"))}</span>
         <span>${t("src_records")}: ${(s.record_count || 0).toLocaleString()}</span>
         <span>${t("src_license")}: ${escapeHtml(s.license || "—")}</span>
       </div>`;
    list.append(card);
  });
  $("#fresh-dot").className = "dot " + freshest;
}

function initDrawer() {
  const drawer = $("#freshness-drawer"), backdrop = $("#drawer-backdrop");
  const open = async () => {
    if (!state.meta) {
      const r = await fetch("/api/db/status").then((x) => x.json()).catch(() => null);
      if (r) renderSources(r.sources);
    }
    drawer.hidden = false; backdrop.hidden = false;
  };
  const close = () => { drawer.hidden = true; backdrop.hidden = true; };
  $("#btn-freshness").addEventListener("click", open);
  $("#btn-close-drawer").addEventListener("click", close);
  backdrop.addEventListener("click", close);
  $("#btn-update").addEventListener("click", runUpdate);
}

async function runUpdate() {
  const btn = $("#btn-update"), log = $("#update-log");
  btn.disabled = true; log.hidden = false; log.textContent = t("update_starting");
  try {
    const res = await fetch("/api/db/update", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
    });
    await readSSE(res, (event, data) => {
      if (event === "progress" && data.message) log.textContent += data.message + "\n";
      else if (event === "done") { log.textContent += t("update_done"); renderSources(data.sources); }
      log.scrollTop = log.scrollHeight;
    });
  } catch (e) { log.textContent += t("update_failed") + e + "\n"; }
  btn.disabled = false;
}

/* ------------------------------------------------------------------ views */
function enterResultsView() {
  $("#landing").hidden = true;
  $("#results-view").hidden = false;
}

function clearResults() {
  state.selected.clear(); syncSelectionUI();
  state.matches = []; state.catGroups.clear();
  // Re-arm the health confirm-gate for every newly parsed file.
  state.healthRevealed = false;
  $("#results").innerHTML = "";
  $$(".rail-item:not([data-cat='__all__'])").forEach((b) => b.remove());
  $("#empty-note").hidden = true;
  $("#health-gate").hidden = true;
  $("#stat-matches").textContent = "0";
}

async function resetAll() {
  if (state.sessionId) {
    fetch(`/api/session/${state.sessionId}`, { method: "DELETE", keepalive: true }).catch(() => {});
  }
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
  let t2;
  $("#search").addEventListener("input", (e) => {
    clearTimeout(t2);
    t2 = setTimeout(() => { state.query = e.target.value.trim().toLowerCase(); refilter(); }, 150);
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
  $("#sel-count").textContent = tSelected(n);
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
  if (m.chrom) bits.push(t("meta_chrom") + " " + escapeHtml(m.chrom) + (m.pos_b37 ? ":" + escapeHtml(String(m.pos_b37)) : ""));
  if (m.risk_allele) bits.push(t("meta_risk") + " " + escapeHtml(m.risk_allele));
  if (m.magnitude != null) bits.push(t("meta_relevance") + " " + escapeHtml(String(m.magnitude)));
  return bits.join(" · ");
}

function reportHealthNote() {
  return state.lang === "es"
    ? "⚠ Relacionado con la salud — no es un diagnóstico. Los datos crudos de consumo se equivocan cerca del 40% de las veces en variantes clínicamente relevantes. Confírmalo con una prueba de grado clínico y un/a profesional antes de actuar."
    : "⚠ Health-related — not a diagnosis. Consumer raw data is wrong about 40% of the time for clinically relevant variants. Confirm with a clinical-grade test and a professional before acting.";
}

/* Pure function: returns a fully self-contained HTML document string. No network,
   no <script> (CSP script-src 'self'), only an embedded <style> (style-src allows it). */
function buildReportHTML(matches, meta) {
  const m0 = meta || {};
  const disc = m0.disclaimers || {};
  const pickD = (k) => (state.lang === "es" && disc[k + "_es"]) ? disc[k + "_es"] : disc[k];
  const vendor = m0.vendor || $("#stat-vendor").textContent || "—";
  const build = m0.build ? ("GRCh" + m0.build) : ($("#stat-build").textContent || "—");
  const snps = (m0.snp_count != null)
    ? m0.snp_count.toLocaleString()
    : ($("#stat-snps").textContent || "0");
  const locale = state.lang === "es" ? "es-ES" : "en-US";
  const date = new Date().toLocaleDateString(locale, { year: "numeric", month: "long", day: "numeric" });
  const nSel = matches.length;
  const anyHealth = matches.some((m) => m.is_health);

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
    .notes{border:1px solid #0E7C86;background:#E5F2F2;border-radius:8px;padding:12px 14px;margin-bottom:20px;font-size:12.5px}
    .notes p{margin:0 0 8px}
    .notes p:last-child{margin-bottom:0}
    .notes-health{border-left:3px solid #B42318;background:#FDECEA;border-radius:4px;padding:10px 12px;margin-top:10px}
    .notes-health p{color:#1A1D21}
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
      .cat-block,.rep-item,.notes{break-inside:avoid}
    }`;

  let notes = "";
  if (disc.global_banner) notes += `<p>${escapeHtml(pickD("global_banner"))}</p>`;
  if (anyHealth && (disc.health_result || disc.false_positive_note)) {
    notes += `<div class="notes-health">`;
    if (disc.health_result) notes += `<p>${escapeHtml(pickD("health_result"))}</p>`;
    if (disc.false_positive_note) notes += `<p>${escapeHtml(pickD("false_positive_note"))}</p>`;
    notes += `</div>`;
  }

  let body = "";
  for (const cat of order) {
    body += `<div class="cat-block"><h2>${escapeHtml(catLabel(cat))}</h2>`;
    for (const m of groups.get(cat)) {
      const geno = escapeHtml(m.resolved_genotype || m.user_genotype || "—");
      const trait = escapeHtml(L(m, "trait") || m.rsid || "—");
      const gene = m.gene ? `<span class="rep-gene mono">${escapeHtml(m.gene)}</span>` : "";
      const explain = escapeHtml((L(m, "effect_text") || "") + (L(m, "carrier_note") ? " " + L(m, "carrier_note") : "")).trim();
      const summary = L(m, "plain_summary");
      const context = summary ? `<p class="rep-context">${escapeHtml(summary)}</p>` : "";
      const health = m.is_health ? `<p class="rep-health-note">${escapeHtml(reportHealthNote())}</p>` : "";
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
<html lang="${state.lang}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ASSAY — ${escapeHtml(t("report_title"))}</title>
<style>${style}</style>
</head>
<body>
<div class="rep-head">
  <h1 class="rep-title">ASSAY <small>— ${escapeHtml(t("report_title"))}</small></h1>
  <div class="rep-readout">
    <span><b>${escapeHtml(t("stat_vendor"))}</b>${escapeHtml(String(vendor))}</span>
    <span><b>${escapeHtml(t("stat_build"))}</b>${escapeHtml(String(build))}</span>
    <span><b>SNPs</b><span class="mono">${escapeHtml(String(snps))}</span></span>
    <span><b>${escapeHtml(t("report_selected"))}</b><span class="mono">${nSel}</span></span>
  </div>
  <div class="rep-gen">${escapeHtml(
    state.lang === "es"
      ? `Generado localmente el ${date} — nada sale de tu dispositivo.`
      : `Generated locally on ${date} — nothing leaves your device.`)}</div>
</div>
${notes ? `<section class="notes">${notes}</section>` : ""}
${body}
<div class="rep-foot">${escapeHtml(
    state.lang === "es"
      ? `Solo con fines educativos y de investigación — no es un diagnóstico. Generado localmente el ${date}.`
      : `For educational and research use only — not a diagnosis. Generated locally on ${date}.`)}</div>
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
  a.download = "assay-report-" + stamp + ".html";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 0);
}

function printReport() {
  const sel = collectSelected();
  if (!sel.length) return;
  const html = buildReportHTML(sel, state.meta);
  const w = window.open("", "_blank");
  if (!w) {
    alert(t("popup_blocked"));
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

/* purge in-memory session when leaving the page */
window.addEventListener("pagehide", () => {
  if (state.sessionId) {
    try { fetch(`/api/session/${state.sessionId}`, { method: "DELETE", keepalive: true }); } catch (e) {}
  }
});

/* ------------------------------------------------------------------- init */
initLang();
initTheme();
initUpload();
initFilters();
initDrawer();
initReport();
