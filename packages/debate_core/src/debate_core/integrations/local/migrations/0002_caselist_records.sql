-- Migration 2: what an import of disclosed or camp evidence learned (v1-e30-t02, v1-e30-t03).
--
-- Four tables for the four kinds of record the CaselistRepository port stores. They follow
-- migration 1's shape — the entity as `document`, the JSON its own Pydantic model produced, plus
-- the few key columns SQLite needs to find and order rows — with two differences that come from
-- the port rather than from this file.
--
-- **Keys are natural, not minted.** A snapshot is its (caselist, snapshot), a source document is
-- its sha256, a disclosure is its (caselist, snapshot, source_path) and a camp file is its
-- (source_sha256, year, event). There is no ULID anywhere here, because an import is a
-- re-statement of what a public archive says rather than an edit a person makes, and it is those
-- keys that make re-importing an unchanged archive a no-op instead of a second copy.
--
-- **`sort_key` carries the listing order.** Every listing is newest snapshot first and then
-- ascending by its remaining key parts, which is two directions in one ORDER BY. Rather than
-- write that as a mixed-direction index that keyset pagination then cannot use, each row stores
-- one text key whose plain ascending order *is* the documented order: the snapshot date
-- inverted (`date.min + (date.max - day)`), then the remaining parts, joined by U+0001 — a
-- character no school name, team code or path contains. A page boundary is then a single
-- `sort_key > ?`, which is what makes pagination reproducible.
--
-- Dates are stored as ISO 8601 text (`2026-09-15`), which is fixed width, so SQLite's
-- lexicographic comparison is chronological comparison.
--
-- No foreign key from a disclosure to its source document. The port does not promise one exists
-- yet — an import stores the source and the disclosure in one transaction, but a removal
-- (v1-e30-t07) deletes a source while its manifest rows stay readable — and DynamoDB could not
-- enforce it in V2 either.

CREATE TABLE caselist_snapshots (
    caselist TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    archive_sha256 TEXT NOT NULL,
    document TEXT NOT NULL,
    PRIMARY KEY (caselist, snapshot)
) STRICT;

-- list_snapshots and latest_snapshot: one caselist's archives, newest date first.
CREATE INDEX caselist_snapshots_by_date ON caselist_snapshots (caselist, snapshot DESC);

CREATE TABLE caselist_sources (
    sha256 TEXT PRIMARY KEY NOT NULL,
    caselist TEXT,
    byte_size INTEGER NOT NULL,
    source_format TEXT NOT NULL,
    origin TEXT NOT NULL,
    first_seen_snapshot TEXT NOT NULL,
    last_seen_snapshot TEXT NOT NULL,
    sort_key TEXT NOT NULL,
    document TEXT NOT NULL
) STRICT;

-- list_sources with and without a caselist filter, in sort_key order.
CREATE INDEX caselist_sources_by_sort_key ON caselist_sources (sort_key);
CREATE INDEX caselist_sources_by_caselist ON caselist_sources (caselist, sort_key);

-- The snapshot filter asks which sources were present in one week: first_seen <= week <= last_seen.
CREATE INDEX caselist_sources_by_seen_range ON caselist_sources (first_seen_snapshot, last_seen_snapshot);

CREATE TABLE caselist_disclosures (
    caselist TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    school TEXT NOT NULL,
    team_code TEXT NOT NULL,
    sort_key TEXT NOT NULL,
    document TEXT NOT NULL,
    PRIMARY KEY (caselist, snapshot, source_path)
) STRICT;

CREATE INDEX caselist_disclosures_by_sort_key ON caselist_disclosures (sort_key);

-- The per-school and per-team landscape views (E32), and the "what does removing this file
-- affect?" question v1-e30-t07 asks before it deletes anything.
CREATE INDEX caselist_disclosures_by_team ON caselist_disclosures (caselist, school, team_code, sort_key);
CREATE INDEX caselist_disclosures_by_source ON caselist_disclosures (source_sha256, sort_key);

CREATE TABLE caselist_camp_files (
    source_sha256 TEXT NOT NULL,
    year INTEGER NOT NULL,
    event TEXT NOT NULL,
    camp TEXT NOT NULL,
    file_title TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    sort_key TEXT NOT NULL,
    document TEXT NOT NULL,
    PRIMARY KEY (source_sha256, year, event)
) STRICT;

CREATE INDEX caselist_camp_files_by_sort_key ON caselist_camp_files (sort_key);
CREATE INDEX caselist_camp_files_by_release ON caselist_camp_files (camp, year, event, sort_key);
CREATE INDEX caselist_camp_files_by_source ON caselist_camp_files (source_sha256, sort_key);
