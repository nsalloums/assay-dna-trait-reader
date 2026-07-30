# 🧬 ASSAY — Local, privacy-first DNA trait reader

[![CI](https://github.com/nsalloums/assay-dna-trait-reader/actions/workflows/ci.yml/badge.svg)](https://github.com/nsalloums/assay-dna-trait-reader/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

Drop your consumer DNA file (23andMe, AncestryDNA, FamilyTreeDNA, MyHeritage,
LivingDNA, tellmeGen, or generic CSV/TSV) and read the traits associated with your
genotypes — **100% locally, on your own machine.** No accounts, no uploads, no cloud,
no telemetry. Your DNA never leaves your computer. **The app reads in English or Spanish** —
toggle the language in the top bar.

> **Educational use only — not a medical device and not medical advice.** In a study
> of 49 cases referred to a clinical lab for confirmation, **40% of the rare,
> high-penetrance variants** (BRCA1/2, TP53, MLH1…) found in consumer raw data **were
> not confirmed** ([Tandy-Connor et al., *Genet Med* 2018](https://doi.org/10.1038/gim.2018.38)).
> That figure comes from a selected cohort and does not apply equally to the common
> SNPs this app shows, but it makes the point: confirm any health result with a
> clinical-grade test and a professional. Nothing here is a diagnosis.

### ▶ [Try it now in your browser — nothing to install](https://nsalloums.github.io/assay-dna-trait-reader/)

Drop your file, or click **"Try a sample file"** if you don't have one handy. Everything
runs in your browser: no backend, nothing uploaded.

---

## Provenance and limits (read this first)

I built this **myself, with no clinical or genetics training**, via AI multi-agent
orchestration. I specified the constraints — local-only, don't rebundle PharmGKB because
of its copyleft, flag palindromic SNPs instead of guessing — and the AI wrote most of the
code under them. The full prompt is published in
[`docs/how-this-was-built.md`](docs/how-this-was-built.md).

What that means in practice, said plainly:

- **No geneticist has reviewed this project.** The 35 curated-seed interpretations are
  plain-language summaries of well-replicated associations; they **name** their source
  database (GWAS Catalog / ClinVar / PharmGKB) but **carry no per-association citation**
  (no PMID). Individual literature backing is still pending.
- **What *is* machine-verified** is the privacy architecture, not the biology:
  `tests/test_privacy_g3.py` blocks every socket and checks that parse→annotate still
  works. That part is mechanical, not a promise.
- **Effect sizes come mostly from European-ancestry cohorts** and do not transfer equally
  to admixed populations. See [Ancestry](#ancestry-a-real-limitation).

---

## Quick start

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

python run.py            # → http://127.0.0.1:8765
```

On first launch the app automatically builds a small **offline curated database**, so it
works immediately with no network. Drag a DNA file onto the page and your traits appear in
real time, grouped by category, each with its source and date, and a **short,
easy-to-read explanation** of what it means.

### Enrich with the full public databases (optional, one time)

```bash
python -m app.db_update update            # GWAS Catalog + ClinVar + PharmGKB
python -m app.db_update update --sources gwas_catalog,pharmgkb   # pick sources
python -m app.db_update status            # check freshness
```

This is the **only** step that uses the network. It downloads *public* annotation
databases to your machine (they contain no user data). After running it once, the app
works fully offline. You can also launch it from the app's **Data sources** panel.

---

## Privacy model (how we guarantee your DNA is yours)

| Guarantee | How it's enforced |
|---|---|
| Listens **on loopback only** | `run.py` rejects any host other than `127.0.0.1` (`app/core/security.assert_loopback`). |
| Genotypes live **in RAM only** | The upload is processed in memory; calls stay in an in-memory session store with a TTL (`app/core/sessions.py`). They are never written to disk or a DB. |
| The annotation path **never touches the network** | `app/core/*` and `app/api/{parse,annotate}.py` **import no HTTP client**. All networking is isolated in `app/db_update/sources.py`, reached only by `POST /api/db/update`. A test blocks every socket and checks parse→annotate still works. |
| The runtime DB is **read-only** | The annotation store is opened `mode=ro`; user data physically cannot be written. Matching uses a temp table of rsIDs (dropped on close, kept in RAM). |
| **No persistence or logging** of genetic data | No genotype is written to disk, logs, or temp files. A log filter redacts anything that looks like an rsID/genotype. No analytics, no reporting SDK. |
| Strict **CSP** | `connect-src 'self'` prevents the SPA from contacting any third-party host; no CDN, no web fonts, everything self-hosted (`app/core/security.py`). |
| The update step carries **zero user data** | Only GETs against an allowlist of hosts (EBI / NCBI / ClinPGx / Ensembl); any other host is refused, even after redirects. |

All test data is **synthetic** (generated by `snps`' `SyntheticSNPGenerator`). A real human
file is never used.

---

## Data sources and licenses

The app combines **actively maintained** annotation databases (not SNPedia, whose terms
restrict crawling). See [`NOTICE`](NOTICE) for full attribution.

| Source | What it provides | License | How we use it |
|---|---|---|---|
| **NHGRI-EBI GWAS Catalog** | SNP ↔ trait/phenotype associations | EBI terms — reusable with citation | Downloaded on-device by `update_databases` |
| **NCBI ClinVar** | Clinical significance of variants | Public domain (U.S. Government work) | Downloaded on-device by `update_databases` |
| **ClinPGx** (formerly PharmGKB) | Pharmacogenomics (drug response) | **CC BY-SA 4.0 (copyleft)** | **Never rebundled** — downloaded onto *your* machine at update time, in its own partition, with attribution |
| **dbSNP / Ensembl** | rsID normalization, GRCh37/38 coordinates | Public domain / EMBL-EBI | **Build-time only** (`scripts/enrich_seed_coords.py`); never at runtime |

**Why PharmGKB isn't bundled:** CC BY-SA is viral copyleft. Bundling its data would force
the entire distributed set under BY-SA. Instead we distribute *code*, and the user
downloads ClinPGx locally — keeping the distributed artifact copyleft-free. The
redistributable seed (`data/seed/associations.json`) contains only project-authored
interpretations, which **name** their source database but **carry no per-association
citation** (see [Provenance and limits](#provenance-and-limits-read-this-first)).

The `LICENSE.txt` shipped *inside* the ClinPGx download adds two conditions on top of a
plain CC BY-SA, which is why "just attribute it" isn't enough: anyone who receives altered
data must first agree to the same license (with proof made available to PharmGKB), and
*"under no circumstances can PharmGKB data be sold for other's private or commercial use."*

**Why we don't use SNPedia:** it's the obvious source for a trait reader and nearly the
whole niche uses it — including the most popular tool in the space. But SNPedia is
**CC BY-NC-SA 3.0** (non-commercial + copyleft) and has been **owned by MyHeritage since
2019**. Building on it means your project inherits a non-commercial restriction and depends
on the wiki of a company that competes with the tests you analyze. We prefer sources from
public institutions (EMBL-EBI, NCBI, Stanford/St. Jude) even though it's more work.

Each result shows its **source, version/release, and the "data current as of" date**, with
a freshness dot. Re-running `update_databases` advances those dates.

---

## Every result, explained (easy to read)

Each match shows:

- The detected **genotype** (e.g. `GG`), the **trait**, and the **gene**.
- A **short plain-language line** of what it means (e.g. *"You most likely have blue
  eyes."*).
- On expand: a **"What does it mean?"** block with the full explanation, extra context,
  the technical provenance (rsID, chromosome, allele, evidence, source + date), and, for
  health results, the no-diagnosis notice.

The curated seed (the best-known traits) ships **bilingual**: plain English as the canonical
text plus a full Spanish translation alongside it, so the app reads in either language via the
top-bar toggle. Traits from the bulk sources (GWAS/ClinVar/PharmGKB) keep their original-language
name (it's source data), but are framed with an honest, non-diagnostic explanation.

---

## How we handle the hard parts (correctly)

- **Strand / orientation** (the #1 bug). Genotypes are normalized to the **forward (+)
  strand**, alphabetically sorted, before comparing (`app/core/strand.py`). Old minus-strand
  reads of *non-palindromic* SNPs are detected and complemented; **palindromic** A/T and C/G
  SNPs (e.g. `rs713598`, `rs9939609`, `rs16891982`, `rs1799945`) can't be resolved by
  complement, so we trust the vendor's + strand and **flag** them, never guessing a flip.
- **Genome build (36/37/38)**. `snps` detects the build; matching is by **rsID** (not by
  position), so identical genotypes on GRCh37 vs GRCh38 give identical results.
- **No-calls** (`--`, `00`, `NN`, `DD`, `II`) are dropped, never matched.
- **Multi-SNP haplotypes** like **APOE** ε2/ε3/ε4 are resolved from `rs429358` + `rs7412`.
- **Health gate**. Health/clinical/pharmacogenomic categories are hidden behind an explicit
  reveal and carry the no-diagnosis and false-positive notices.

---

## Ancestry: a real limitation

The app is in Spanish, so many of its users will have admixed ancestry (European /
Amerindian / African). **The effect sizes it shows come mostly from European-ancestry
cohorts and do not transfer equally.** This isn't a legal footnote: it changes the number.

- **APOE.** The seed says ε3/ε4 carries "about 2–3× the average risk of late-onset
  Alzheimer's." That flat number hides a large spread: a 2023 meta-analysis found ORs from
  1.88 (Caribbean Hispanic) to 3.51 (South American) depending on the proportion of
  European ancestry.
- **`rs4988235` (lactase).** **Does not tag lactase persistence in most African-ancestry
  populations** — there the signal is carried by other variants (`rs182549`, `rs41380347`).
  A `GG` → "more likely lactose intolerant" will simply be wrong for part of the
  Afro-descendant Latin American population.
- **`rs12913832` (eye color).** ~85% predictive in Northern Europeans; materially weaker in
  Southern European and admixed populations.

Pending work: a per-association `ancestry_basis` field and a persistent UI banner. Today
it's only documented here, which is less than it should be.

---

## Architecture

```
run.py                      one-command launcher (loopback only)
app/
  main.py                   FastAPI app: static SPA + API, CSP middleware, lifespan
  config.py  db.py          paths/constants; SQLite helpers (read-only at runtime)
  api/                      parse · annotate (SSE) · db/status+update · health
  core/                     parsing (snps) · strand · sessions · annotation · security · content
  db_update/                sources (ONLY network module) · normalize · update · build_seed
data/
  schema.sql                DDL for the unified annotation store
  seed/_curated_base.json   hand-authored bilingual (EN/ES) source of the curated seed
  seed/associations.json    redistributable curated seed (35 associations + APOE rule), bilingual EN/ES
  annotations.db            built locally (git-ignored)
web/                        vanilla-JS SPA (ASSAY design; no external assets; EN/ES toggle)
demo/                       static demo: the same engine ported to JS, no backend (GitHub Pages)
tests/                      synthetic corpus + G1/G2/G3 golden + privacy tests
docs/how-this-was-built.md  the multi-agent orchestration prompt it was built with
.github/workflows/ci.yml    tests on Linux/macOS/Windows × Python 3.12/3.13 + privacy job
scripts/enrich_seed_coords.py   coordinate enrichment (Ensembl) at build time
```

The parse → annotate flow: the upload is processed in memory with `snps`; genotypes go to
an in-memory session; `POST /api/annotate` streams matches over **SSE** as they resolve
(progressive rendering), matching against the local read-only store.

---

## Tests

```bash
python -m pytest tests/ -q
```

Covers the acceptance criteria with a **synthetic** corpus (7 vendor/build/edge-case files
with known injected genotypes and expected values):

- **G1 Parse** — vendor + build detection, strand normalization, no-call handling.
- **G2 Annotate** — exact annotations, zero false positives, APOE diplotype, GRCh37/38
  identity, minus-strand flips, palindrome non-flips, format independence.
- **G3 Privacy** — parse→annotate with **all sockets blocked**, no-persistence sentinel
  scan, read-only store, session purge, host allowlist, log redaction.
- **ClinVar normalizer** — validated against a fixture (without downloading 440 MB).

Regenerate the corpus / rebuild the seed:

```bash
python -m tests.make_corpus            # writes fixtures to tests/corpus/
python -m app.db_update seed           # rebuilds the seed DB
python scripts/enrich_seed_coords.py   # refreshes seed coordinates from Ensembl (base is bilingual EN/ES)
```

---

## License

[MIT](LICENSE) for this project's code and curated seed. Third-party data and dependencies
keep their own licenses — see [`NOTICE`](NOTICE). PharmGKB data is not redistributed here;
it is downloaded onto your machine under CC BY-SA 4.0.
