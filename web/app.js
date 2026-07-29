"use strict";
/* ASSAY frontend. Talks only to the same-origin localhost API. No third-party
   requests (CSP connect-src 'self'). Your genotypes never leave this machine. */

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
  } catch (err) { return showLandingError("No se pudo conectar con el servidor local."); }
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    setMeter(0, false);
    return showLandingError(j.detail || "No se pudo leer este archivo.");
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
  if (!res.ok) { setMeter(0, false); return showLandingError("Falló la anotación."); }

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
    $("#empty-note").textContent = "No se encontraron asociaciones en tu archivo para las bases cargadas. Puede que tu chip no incluya estos marcadores.";
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
  btn.disabled = true; log.hidden = false; log.textContent = "Iniciando…\n";
  try {
    const res = await fetch("/api/db/update", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
    });
    await readSSE(res, (event, data) => {
      if (event === "progress" && data.message) log.textContent += data.message + "\n";
      else if (event === "done") { log.textContent += "Listo.\n"; renderSources(data.sources); }
      log.scrollTop = log.scrollHeight;
    });
  } catch (e) { log.textContent += "Falló la actualización: " + e + "\n"; }
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

/* purge in-memory session when leaving the page */
window.addEventListener("pagehide", () => {
  if (state.sessionId) {
    try { fetch(`/api/session/${state.sessionId}`, { method: "DELETE", keepalive: true }); } catch (e) {}
  }
});

/* ------------------------------------------------------------------- init */
initTheme();
initUpload();
initFilters();
initDrawer();
initReport();
