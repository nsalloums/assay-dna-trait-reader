-- ============================================================================
-- Local DNA Trait Extractor — unified annotation store (SQLite)
--
-- PRIVACY INVARIANT: this database contains ONLY public annotation data plus the
-- project's own curated seed. User genotypes are NEVER written here (or anywhere
-- on disk). Trait matching happens in memory by joining the parsed genotypes
-- (held only in RAM) against this read-only store.
--
-- Encoding: UTF-8. PRAGMA user_version tracks schema version (see SCHEMA_VERSION).
-- ============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- One row per ingested source release: the freshness / provenance ledger the UI
-- reads to render "data current as of {date}" per source.
CREATE TABLE IF NOT EXISTS source_release (
    source         TEXT NOT NULL,      -- 'curated_seed' | 'gwas_catalog' | 'clinvar' | 'pharmgkb'
    source_version TEXT NOT NULL,      -- release date/version string parsed at fetch time
    fetched_date   TEXT NOT NULL,      -- ISO-8601 UTC when we downloaded/built
    download_url   TEXT,
    record_count   INTEGER NOT NULL DEFAULT 0,
    genome_build   TEXT,               -- 'GRCh37' | 'GRCh38'
    origin         TEXT NOT NULL DEFAULT 'update',  -- 'seed' | 'update'
    license        TEXT,               -- carried through for in-app attribution
    display_name   TEXT,               -- e.g. 'NHGRI-EBI GWAS Catalog'
    PRIMARY KEY (source, source_version)
);

-- Core annotation table. Grain = one interpreted assertion for an rsID, optionally
-- specific to a genotype. rsid is the universal join key (matching is by rsID, not
-- by position, so results are build-independent).
CREATE TABLE IF NOT EXISTS annotation (
    id               INTEGER PRIMARY KEY,
    rsid             TEXT NOT NULL,               -- normalized lowercase 'rs<digits>'
    genotype         TEXT,                        -- forward-strand, alpha-sorted diploid e.g. 'AG';
                                                  -- NULL = allele/association-level (GWAS/ClinVar/PharmGKB)
    gene             TEXT,
    trait            TEXT,
    trait_es         TEXT,                        -- optional Spanish trait name (curated seed only)
    category         TEXT NOT NULL,
    sensitivity      TEXT NOT NULL DEFAULT 'low', -- 'low' | 'health'
    effect_text      TEXT,                        -- genotype-specific meaning / clinical significance / pgx text
    effect_text_es   TEXT,                        -- optional Spanish rendering of effect_text
    magnitude        REAL,                        -- 0-4 salience score
    plain_summary    TEXT,                        -- association-level plain-language summary
    plain_summary_es TEXT,                        -- optional Spanish rendering of plain_summary
    risk_allele      TEXT,                        -- effect/risk/pathogenic allele
    ref_allele       TEXT,
    alt_allele       TEXT,
    orientation      TEXT NOT NULL DEFAULT 'forward',  -- vs GRCh reference
    ambiguous_strand INTEGER NOT NULL DEFAULT 0,  -- 1 if A/T or C/G (palindromic)
    chrom            TEXT,
    pos_b37          INTEGER,
    pos_b38          INTEGER,
    effect_size      TEXT,                        -- raw 'OR=1.23' / 'BETA=...' / p-value (GWAS)
    confidence       TEXT,                        -- ClinVar stars | PharmGKB LoE | GWAS p-tier
    evidence         TEXT,                        -- human-readable evidence base label
    source           TEXT NOT NULL,
    source_version   TEXT NOT NULL,
    fetched_date     TEXT NOT NULL,
    citation         TEXT,                        -- PMID / RCVaccession / PharmGKB clin-ann id
    FOREIGN KEY (source, source_version)
        REFERENCES source_release(source, source_version) ON DELETE CASCADE
);

-- Multi-SNP (haplotype/diplotype) rules, e.g. APOE from rs429358 + rs7412.
CREATE TABLE IF NOT EXISTS haplotype_rule (
    id             TEXT PRIMARY KEY,             -- 'apoe_isoform'
    trait          TEXT NOT NULL,
    trait_es       TEXT,                          -- optional Spanish trait name
    gene           TEXT,
    category       TEXT NOT NULL,
    sensitivity    TEXT NOT NULL DEFAULT 'health',
    member_rsids   TEXT NOT NULL,                -- JSON array ["rs429358","rs7412"]
    diplotypes     TEXT NOT NULL,                -- JSON map "GT|GT" -> {name, effect, effect_es, magnitude}
    plain_summary  TEXT,
    plain_summary_es TEXT,
    evidence       TEXT,
    source         TEXT NOT NULL,
    source_version TEXT NOT NULL,
    fetched_date   TEXT NOT NULL
);

-- Merged/deprecated rsID -> current rsID (built from dbSNP/Ensembl at build/update
-- time). Lets a user's old-array rsID match current annotations with NO runtime network.
CREATE TABLE IF NOT EXISTS rsid_alias (
    old_rsid       TEXT PRIMARY KEY,
    current_rsid   TEXT NOT NULL,
    source_version TEXT
);

-- ---- Indexes: rsID-first lookups are the hot path -------------------------
CREATE INDEX IF NOT EXISTS idx_annotation_rsid          ON annotation(rsid);
CREATE INDEX IF NOT EXISTS idx_annotation_rsid_genotype ON annotation(rsid, genotype);
CREATE INDEX IF NOT EXISTS idx_annotation_category      ON annotation(category);
CREATE INDEX IF NOT EXISTS idx_annotation_source        ON annotation(source);
CREATE INDEX IF NOT EXISTS idx_alias_current            ON rsid_alias(current_rsid);

-- Idempotent upsert identity for a single assertion (prevents dupes on re-run).
CREATE UNIQUE INDEX IF NOT EXISTS uq_annotation_natural
    ON annotation(source, rsid, IFNULL(genotype,''), IFNULL(trait,''),
                  IFNULL(risk_allele,''), IFNULL(citation,''));
