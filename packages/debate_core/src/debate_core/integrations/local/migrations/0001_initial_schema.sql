-- Migration 1: the V1 local schema — articles, their snapshots, cards, searches and rankings.
--
-- Every entity is stored twice over: once as `document`, the JSON its own Pydantic model
-- produced, which is the value of record and is revalidated on the way out; and once as a handful
-- of key columns copied out beside it, which exist only so SQLite can find and order rows. A
-- column that is not a lookup key or a sort key does not belong here — it would be a second,
-- silently diverging copy of a field the document already holds.
--
-- The shape mirrors the V2 cloud model (architecture proposal §7) so that nothing stored here is
-- something DynamoDB could not store: ULID primary keys, no server-generated values, and no
-- foreign key between entities that DynamoDB has no way to enforce. `search_results` is the one
-- exception, and it earns it — a result is part of its search rather than an entity of its own.
--
-- Timestamp columns hold a fixed-width UTC rendering (`YYYY-MM-DDTHH:MM:SS.ffffff`) so that
-- lexicographic order is chronological order. The document keeps the entity's own ISO 8601 form.
--
-- STRICT tables (SQLite 3.37+) make a column's declared type a constraint rather than a
-- suggestion, so an adapter bug that writes an int where a ULID belongs fails here instead of
-- surfacing as a mystery at read time.

CREATE TABLE articles (
    article_id TEXT PRIMARY KEY NOT NULL,
    canonical_url TEXT NOT NULL,
    owner_id TEXT,
    organization_id TEXT,
    created_at TEXT NOT NULL,
    revision INTEGER NOT NULL,
    document TEXT NOT NULL
) STRICT;

-- The platform's dedupe key for a source. Deliberately not UNIQUE: the ArticleRepository port
-- does not promise uniqueness, the in-memory fake does not enforce it, and DynamoDB could not
-- enforce it in V2 without a transaction on every write. Canonicalization happens in E04, before
-- the save; this index is what makes find_by_canonical_url a lookup rather than a scan.
CREATE INDEX articles_by_canonical_url ON articles (canonical_url);

-- Covers list_by_owner, which is newest first with the id as tie-break.
CREATE INDEX articles_by_owner ON articles (owner_id, created_at DESC, article_id DESC);

CREATE TABLE source_snapshots (
    snapshot_id TEXT PRIMARY KEY NOT NULL,
    article_id TEXT NOT NULL,
    owner_id TEXT,
    organization_id TEXT,
    canonical_url TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    raw_blob_key TEXT NOT NULL,
    normalized_blob_key TEXT NOT NULL,
    document TEXT NOT NULL
) STRICT;

-- list_snapshots: every snapshot of one article, newest retrieval first.
CREATE INDEX source_snapshots_by_article ON source_snapshots (article_id, retrieved_at DESC, snapshot_id DESC);

-- Which snapshots point at a blob. The removal runbook needs this before it deletes one, and a
-- store integrity sweep needs it to tell an orphaned blob from a referenced one.
CREATE INDEX source_snapshots_by_raw_blob_key ON source_snapshots (raw_blob_key);

CREATE TABLE cards (
    card_id TEXT PRIMARY KEY NOT NULL,
    owner_id TEXT NOT NULL,
    organization_id TEXT,
    article_id TEXT NOT NULL,
    snapshot_id TEXT,
    created_at TEXT NOT NULL,
    revision INTEGER NOT NULL,
    document TEXT NOT NULL
) STRICT;

CREATE INDEX cards_by_owner ON cards (owner_id, created_at DESC, card_id DESC);
CREATE INDEX cards_by_article ON cards (article_id, created_at DESC, card_id DESC);

-- Which cards were cut from one snapshot: what re-verification iterates after a normalizer
-- version changes, and what a removal has to mark unverifiable.
CREATE INDEX cards_by_snapshot ON cards (snapshot_id);

CREATE TABLE searches (
    search_id TEXT PRIMARY KEY NOT NULL,
    owner_id TEXT,
    organization_id TEXT,
    created_at TEXT NOT NULL,
    revision INTEGER NOT NULL,
    document TEXT NOT NULL
) STRICT;

CREATE INDEX searches_by_owner ON searches (owner_id, created_at DESC, search_id DESC);

-- A ranking, stored as a set per search: a result exists only as part of its search, which is why
-- this is the one place a foreign key belongs. ON DELETE CASCADE keeps a deleted search from
-- leaving its ranking behind, and the primary key states the domain's rule that one search holds
-- at most one result per article.
CREATE TABLE search_results (
    search_id TEXT NOT NULL REFERENCES searches (search_id) ON DELETE CASCADE,
    article_id TEXT NOT NULL,
    "rank" INTEGER NOT NULL,
    document TEXT NOT NULL,
    PRIMARY KEY (search_id, article_id)
) STRICT;

-- Two results may not claim the same position, and list_results reads in rank order.
CREATE UNIQUE INDEX search_results_by_rank ON search_results (search_id, "rank");
