# How ASSAY was built — the multi-agent orchestration prompt

**This is not app documentation: it's the actual prompt it was built with, published on purpose.**

I built ASSAY through AI multi-agent orchestration (Claude Opus 4.8 in Claude Code). I specified
the constraints — local-only, no genotype egress, don't rebundle PharmGKB because of its copyleft,
flag palindromes instead of guessing — and the AI wrote most of the code under them. I publish the
prompt because the process feels like the most interesting part of the project, and because I'd
rather tell you myself than have you infer it from the git history.

Two caveats to read before interpreting what follows:

1. **The "Geneticist" in §4 is an AI sub-agent role, not a person.** I am not a geneticist or a
   physician, and no geneticist has reviewed this project. That roster describes fictional personas
   the AI played. Where the document says "geneticist-verified", read "verified by an LLM asked to
   act as a geneticist" — which is not the same thing and must not be treated as if it were. The
   seed interpretations are not clinically reviewed.
2. **This document is the original plan, not a record of what was delivered.** Some of the §8
   acceptance criteria were met more weakly than the text suggests. The real status is in the
   README and in `tests/`.

---

## 0. Mission

Build an **open-source, 100% local** web application that:

1. Lets any user drop in a **raw DNA file** (23andMe, MyHeritage, AncestryDNA, FamilyTreeDNA, LivingDNA, tellmeGen, or a generic CSV/TSV) **on their own machine**.
2. Parses the SNPs (rsIDs) and cross-references them against **actively maintained** annotation databases to surface every identified trait/characteristic/association for that person's genotypes.
3. **Never uploads, stores, or transmits any user genetic data.** All computation happens on the user's device. No accounts, no telemetry, no cloud.
4. Ships with a **fast, clean, respectable UI/UX** (instant drag-and-drop, progressive rendering, no spinners-of-death).

This is intentionally a **small, focused MVP**, not a clinical product. Educational/research use only.

---

## 1. Hard constraints (non-negotiable)

- **Privacy:** raw data and parsed genotypes stay in memory / on local disk only. No network calls carry user genotype data. The only outbound network activity allowed is **downloading the public annotation databases** (which contain no user data) during a build/refresh step, ideally run once and cached locally so the app itself can run offline.
- **No data storage of users:** no database of user genomes, no logging of rsIDs, no analytics on genetic content.
- **Licensing:** respect the license of every dependency and data source. Do **not** scrape SNPedia (its terms restrict crawling and it is barely maintained since the MyHeritage acquisition). Use bulk-download sources with clear redistribution terms instead (see §3).
- **Not medical advice:** every trait output must carry a clear disclaimer. Direct-to-consumer raw data has a documented ~40% false-positive rate for clinically significant variants, so any health-adjacent result must recommend clinical confirmation and must not be phrased as a diagnosis.

---

## 2. Recommended foundation (clone, don't reinvent)

- **Parsing layer:** clone and build on **`apriha/snps`** (Python, MIT-style, actively maintained). It already:
  - reads every major vendor format and generic CSV/TSV,
  - detects genome build (36/37/38) and can remap between builds,
  - merges files and flags discrepant SNPs,
  - **generates synthetic genotype data** via `SyntheticSNPGenerator` (use this for the test corpus — see §6).
- **Everything else** (annotation join, trait engine, UI) is built fresh on top of it. Evaluate but do not assume correctness of any existing "trait detector" repo; treat them as reference only.

---

## 3. Annotation data sources — use MAINTAINED ones, combined

Do **not** rely on SNPedia. Build a local annotation store by ingesting and refreshing these:

| Source | What it gives | Access | Cadence |
|---|---|---|---|
| **NHGRI-EBI GWAS Catalog** | SNP ↔ trait/phenotype associations (the core of "characteristics") | Bulk TSV download from EBI | Continuous / frequent |
| **ClinVar (NCBI)** | Clinical significance of variants | FTP bulk (VCF + tab-delimited) | Monthly releases |
| **PharmGKB** | Pharmacogenomics (drug response) | Downloadable annotation files | Regular |
| **dbSNP / Ensembl** (support only) | rsID normalization, build/position, strand/orientation | REST / bulk | As needed |

Design an **`update_databases` task** that fetches the latest release of each, normalizes them to a common internal schema keyed by rsID + genotype, records the source version/date, and caches locally. Surface the "data current as of {date}" per source in the UI so users know freshness. Handle **strand/orientation** correctly (a known footgun: reference-vs-vendor strand mismatches flip alleles).

---

## 4. Agent roster

Spin up the following specialized sub-agents. Each has a defined role, owns specific files, and reports progress against the shared goals in §5.

1. **Orchestrator / Project Lead**
   Owns the goal-based loop, assigns tasks, resolves conflicts, enforces the §1 constraints on every deliverable, decides when success criteria are met or a goal must be re-scoped.

2. **Geneticist (domain expert)**
   Senior human-genetics expertise. Responsibilities:
   - Define the internal SNP/genotype/annotation schema and the strand/orientation normalization rules.
   - Curate which trait categories are in scope for the MVP (e.g. common non-sensitive traits first; gate health/clinical categories behind explicit disclaimers).
   - Validate that the annotation join is biologically correct (right allele → right association, correct build).
   - **Generate a synthetic test corpus** of raw files across vendors/builds/edge cases using `snps`' `SyntheticSNPGenerator`, including deliberately tricky cases (minus-strand SNPs, missing calls, no-calls `--`, mixed builds). No real human data is ever used in testing.
   - Author the medical-disclaimer and false-positive language.

3. **Data Engineer**
   Builds the `update_databases` ingestion + normalization pipeline (§3), the local cache, versioning/freshness metadata, and the fast rsID→annotation lookup index.

4. **Backend Engineer**
   Wraps `apriha/snps` into a local parse→annotate service that runs entirely on-device. Guarantees no user genotype leaves the process. Exposes a minimal local API to the frontend.

5. **Frontend / UX Engineer**
   Delivers the "respectable and fast" interface (§7): drag-and-drop upload, instant feedback, progressive result rendering, filtering by trait category, clear provenance and disclaimers. Follows a clean, intentional visual design (not a templated default look).

6. **QA / Privacy Auditor**
   - Runs the geneticist's synthetic corpus through the full pipeline and checks outputs against expected annotations.
   - **Audits for privacy leaks:** inspects all network traffic during a run and asserts that zero user genotype data leaves the machine (fail the build if any does).
   - Checks licensing/attribution compliance for every data source and dependency.

(Add or drop agents if the Orchestrator judges it necessary — e.g. a DevOps agent for packaging/one-click local run — but keep the team lean; this is a small MVP.)

---

## 5. Goal-based loop

Operate as an iterative loop. Each iteration: **plan → assign → build → test → evaluate against success criteria → replan.** Do not stop until all Definition-of-Done criteria pass or a blocker requires a human decision (then surface it clearly).

**Goals (in priority order):**

- **G1 — Parse:** Any supported raw file is correctly parsed; build is detected; strand normalized. *Success:* 100% of synthetic corpus parses with correct build detection.
- **G2 — Annotate:** Parsed genotypes are joined to the combined GWAS Catalog + ClinVar + PharmGKB store and every matching trait/association is surfaced with source + freshness. *Success:* geneticist-verified expected annotations match on the synthetic corpus.
- **G3 — Privacy:** Full local run with zero outbound user-data. *Success:* QA/Privacy audit passes with zero leaks.
- **G4 — UX:** Fast, clean upload→results experience with disclaimers and category filtering. *Success:* time-to-first-result is snappy on a mid-range laptop; UX review passes.
- **G5 — Freshness:** `update_databases` fetches latest releases and records versions. *Success:* re-running it updates the "current as of" dates.

Each agent reports, every iteration: what advanced, what's blocked, and which success criteria now pass. The Orchestrator recomputes the plan from that state.

---

## 6. Testing with synthetic raws (explicit)

The Geneticist generates all test data — **never use a real person's file.** Use `snps`' synthetic generator to emit 23andMe/Ancestry/FTDNA-format files with known injected genotypes so expected annotations are known in advance. Cover: multiple builds, minus-strand SNPs, no-calls, low-coverage vendors, and a "rich" file that triggers many trait categories. QA replays these on every iteration as a regression suite.

---

## 7. UX requirements

- **Upload:** drag-and-drop or file-picker; auto-detect vendor/format; show detected build and SNP count immediately.
- **Speed:** parse and render progressively — show results as they resolve, never block on the whole file.
- **Results:** grouped by trait category; each row shows the user's genotype, the association, the **source + version/date**, and a plain-language summary. Filter/search by category or keyword.
- **Trust:** persistent, unmissable "educational, not medical advice — confirm clinically" banner; per-result provenance; "data current as of {date}" per source.
- **Design:** clean, intentional, distinctive — avoid a generic template look. Fast, legible, no clutter.

---

## 8. Definition of Done

- One-command local run; app works **offline** after a one-time `update_databases`.
- Supported vendor files parse correctly (validated on synthetic corpus).
- Traits surfaced from **combined maintained sources** with visible provenance and freshness.
- **Privacy audit passes: zero user genotype data leaves the device; nothing stored server-side.**
- Disclaimers and false-positive guidance present throughout.
- README documents setup, data sources + their licenses, refresh process, and the privacy model.

---

## 9. Guardrails summary

Local-only • no user-data storage • maintained sources (GWAS Catalog + ClinVar + PharmGKB, **not** SNPedia scraping) • correct strand/build handling • educational-only with clinical-confirmation warnings • synthetic test data only • respect all licenses.
