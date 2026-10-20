<!-- docs-index: The student search pilot's SQLite FTS5 index: its schema, manifest and pointer, and the record of each full-store build -->
# The search pilot's index

What `debate-research tub index build` writes, column by column, and what `tub index publish` puts in
the bucket. This is the contract the pilot's function (`v1-e39-t03`, `v1-e39-t06`) and the weekly
refresh (`v1-e39-t09`) read the index by. Decision:
[ADR-0019](../adr/0019-student-search-pilot-stack-sign-in-and-hosting.md) (c). Spec:
[`v1-e39-t02`](../../plan_specs/v1/e39-evidence-search-pilot/t02-search-index-build.yaml). How to
build and publish one: [docs/guides/search-index.md](../guides/search-index.md).

## One build is three files

```
<data_dir>/tub-index/<index id>/search-index.sqlite       the index: SQLite 3, FTS5
<data_dir>/tub-index/<index id>/search-index.sqlite.gz    the same file gzipped: what is published
<data_dir>/tub-index/<index id>/manifest.json             what the build is and was built from
```

The **index id** is the first 16 hex characters of the SQLite file's sha256. The same store gives
the same bytes, built by the same SQLite and zlib, so a rebuild of an unchanged store has the same
id. Published, the gzip object and the manifest go to
`reports/tub/search/<index id>/` and the pointer to `reports/tub/search/current.json`, last
([store layout](../architecture/evidence-store-layout.md#reportstubsearch-the-student-search-pilots-index)).

## What goes in

One **document** per card cluster with a surviving occurrence, under the running
`card-fingerprint-v4`. A cluster is one cluster id in one store (a caselist slug, or `openev`), read
from the occurrence table of the newest generation of the running parser version's directory. A
per-source file that no occurrence row names is never read. The suppression list applies: an
occurrence it stops is left out, and so is a caselist occurrence a path hold covers; a cluster left
with none is left out.

Each document's **representative** is the first of its surviving occurrences in this order, over
stored fields alone:

1. FULL, then ABBREVIATED, then CITE_ONLY;
2. attributed before unattributed: a caselist occurrence whose disclosure is on record, a camp
   occurrence whose release record is;
3. the latest last snapshot (a camp release by its year, then its name);
4. the smallest occurrence key: source sha256, first element index, disclosure digest, release.

The representative's tag, cite, text and formatting are the document's. They come from its source's
document record (`DocumentRecord.to_parsed_document`); the occurrence table carries no tag or cite.

## The schema, format version 1

`PRAGMA user_version` is the format version, and `PRAGMA application_id` is `0x54554253`
(`TUBS`). The file uses no SQLite or FTS5 feature newer than **3.40.0**, the version the function's
Lambda image runs. Its journal mode is the rollback journal, never WAL. The writer builds it with no
journal and finishes with `VACUUM`, so it has no free pages.

### `index_info`

| Column | |
|---|---|
| `key` | `format_version`, `sqlite_feature_ceiling` |
| `value` | `1`, `3.40.0` |

### `documents`: one row per cluster

| Column | Type | Searchable | What it holds |
|---|---|---|---|
| `doc_id` | integer key | | The document's rank in (caselist, cluster id) order, from 1 |
| `caselist` | text | | Caselist slug, or `openev` |
| `cluster_id` | text | | The cluster id under `card-fingerprint-v4`. Unique with `caselist` |
| `event` | text | | `LD`, `POLICY` or `PF`: from the caselist slug, or the camp release |
| `camp` | text | | The camp, for an `openev` document; null otherwise |
| `tag` | text | **yes** | The representative's tag, exactly as written; null when the card has none |
| `cite` | text | **yes** | Its full cite, exactly as written, except for a cutter mark (`//JD`) at its end, which is removed |
| `short_cite` | text | | Its short cite (`Okonkwo 26`); null when unreadable |
| `read_aloud` | text | **yes** | The underlined or highlighted stretches of its evidence text, in order, joined by a space: `read_aloud_text(text, decode_formatting_spans(formatting_spans))` gives it again |
| `text` | text | **yes** | Its evidence text, exactly as written; empty for CITE_ONLY |
| `completeness` | text | | `FULL`, `ABBREVIATED` or `CITE_ONLY` |
| `formatting_spans` | text | | Its formatting spans in the parser's order, as compact JSON: `[emphasis, start, end]`, with the colour after a highlight's, as in `[["UNDERLINE",0,15],["HIGHLIGHT",9,22,"cyan"]]`. Offsets index into `text`, start inclusive, end exclusive. The parser's `rule_id` and `match_source` are not stored. `decode_formatting_spans` in `debate_core.domain.search_index` reads it back |
| `font_size_spans` | text | | Its font-size spans, as compact JSON `[start, end, half_points]`; `decode_font_size_spans` reads it back |
| `sides` | text | | JSON array of the sides its occurrences were disclosed on, sorted, `UNKNOWN` left out |
| `first_seen` | text | | Earliest first snapshot of its occurrences, `YYYY-MM-DD`; null for `openev` |
| `last_seen` | text | | Latest last snapshot of its occurrences; null for `openev` |
| `file_count` | integer | | Distinct sources among its occurrences |
| `team_count` | integer | | Distinct school and team code pairs among its occurrences' disclosures on record |
| `occurrence_count` | integer | | Its surviving occurrences |

### `occurrences`: every surviving occurrence, never searchable

Keyed on `(doc_id, ordinal)`; `ordinal` 0 is the representative, and the rest follow the order above.
Every occurrence keeps its `source_sha256` and `disclosure` digest, so the function can hide one a
newer suppression list stops (`v1-e39-t07`). Only the first `provenance_limit` keep who disclosed it
(`provenance` = 1); the rest have every provenance column null. Indexed by `source_sha256`.

| Column | What it holds |
|---|---|
| `doc_id`, `ordinal` | Which document, and where in the order |
| `caselist` | Caselist slug, or `openev` |
| `source_sha256` | The source the card was read from |
| `disclosure` | Digest of `<caselist>/<path>`; null for a camp file |
| `first_element_index`, `last_element_index` | Where the card is in its source |
| `snapshot`, `last_snapshot` | First and latest snapshot listing it; a release for a camp file |
| `completeness` | As parsed |
| `attributed` | 1 when its disclosure, or for a camp file its release record, is on record |
| `provenance` | 1 when the provenance columns below are kept |
| `side`, `school`, `team_code`, `tournament`, `round` | As disclosed, for a caselist occurrence with a disclosure on record |
| `camp`, `camp_year`, `camp_event`, `camp_file_title` | The camp release, for a camp occurrence; the title only with its release record |

### `search`: the full-text index

```sql
CREATE VIRTUAL TABLE search USING fts5(tag, cite, read_aloud, text,
  content='documents', content_rowid='doc_id', tokenize='unicode61 remove_diacritics 2')
```

An external-content FTS5 table over the four searchable columns, so the text is stored once, in
`documents`. Its rowid is `doc_id`. Column weights for `bm25()` are the query's, not the index's
(`v1-e39-t03`). The `search_data`, `search_idx`, `search_docsize` and `search_config` tables are
FTS5's own.

## Never searchable, never stored

* **School, team code, tournament and round** are in `occurrences` and in no FTS5 table, so no query
  can match them (the data-use policy's E39 gate item 8). A test builds an index whose fixture
  disclosures name a school, team code, tournament and round, and checks that a full-text query for
  each matches nothing.
* **A camp file title** (`camp_file_title`, the importer's title without extension, camp, year or lab
  initials) is stored for a camp card's provenance line and is in no FTS5 table either (PM ruling
  2026-10-20); a test checks that a word found only in one matches nothing.
* **Never stored:** a cutter mark, a disclosure path or a caselist file name, a card's section
  headings and undertag, a name from a document body. The ports the build reads hold no path, and
  the cite's trailing cutter mark is removed before it is stored.

## The manifest

`manifest.json` is a `SearchIndexManifest`, validated by
[`search-index-manifest.schema.json`](search-index-manifest.schema.json), which is generated from the
model by `uv run scripts/export_search_index_schema.py` and checked against it by a test in every
run. It records the format version, the parser and fingerprint versions, the building SQLite version
and the 3.40.0 ceiling, the provenance limit, each store read (version directory, latest snapshot,
row count and a digest of its rows), the suppression list's digest, the counts, and the size and
sha256 of the SQLite file and of the gzip object. It holds no time, host or path.

## The pointer

`reports/tub/search/current.json`:

| Field | |
|---|---|
| `pointer_version` | `1` |
| `format_version` | The current index's format version |
| `index_id` | The current index's id |
| `manifest_key`, `manifest_sha256` | Its manifest, by key and digest |
| `object_key`, `object_sha256` | Its gzip object, by key and digest |
| `sqlite_sha256` | The digest of the SQLite file the object decompresses to |

`publish` refuses an index whose parser or fingerprint version is not the running build's, or whose
format version it does not write, before it uploads anything.

## Full-store builds

Each operator-run build of the whole store, recorded for the size ADR-0019 (c) 6 estimated (280 to
550 MB, 110 to 220 MB gzipped, with a revisit trigger at 400 MB gzipped). Counts only.

| Date | Parser | Stores | Documents | Occurrences | SQLite file | gzip object | Build time | Peak memory |
|---|---|---|---|---|---|---|---|---|
| 2026-10-20 | `2026.10.18-docx-5` | hsld26 11,675; hspf26 10,365; hspolicy26 18,772; openev 5,846 | 46,658 | 273,390 | 1,483,825,152 bytes (1.48 GB) | 319,949,165 bytes (320 MB) | 233 s | 1.18 GB resident |

**2026-10-20** (`v1-e39-t02`, index `5119ffd998e18ad9`, latest snapshot 2026-10-13, built by SQLite
3.50.4 on the operator's Mac from the dev data directory). 273,390 occurrence rows read and indexed,
0 suppressed, 0 clusters left out, every representative attributed; 115,140 occurrences keep their
provenance (limit 5). The Lambda image's SQLite 3.40.0 opened it read-only: `integrity_check` `ok`,
46,658 documents, and a full-text query answered.

Against ADR-0019 (c) 6: the gzip object, 320 MB, is above the 110 to 220 MB estimate and below the
400 MB revisit trigger, which is about 4.1 s at 78 MB/s. The SQLite file, 1.48 GB, is 2.7 times the
550 MB upper estimate and above the 1 GB the plan allows for the season. A live copy and an
incoming one at a weekly swap take 2.97 GB of the function's 4,096 MB of ephemeral storage.

Where the space goes, in MB:

| Part | MB | |
|---|---|---|
| `documents.formatting_spans` | 805.3 | About 115 spans a document, each a JSON object with its `rule_id` and `match_source` |
| `documents.text` | 241.4 | |
| `search_data` (the FTS5 index) | 157.6 | |
| `documents.font_size_spans` | 73.5 | |
| `documents.read_aloud` | 60.8 | |
| `occurrences`, and its index by source | 59.3 and 20.8 | |
| `documents.cite`, `documents.tag` | 15.5 and 4.1 | |
