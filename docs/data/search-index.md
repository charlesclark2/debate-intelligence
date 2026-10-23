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

### Only real cards

A cluster whose representative is no card is left out, with all its occurrences (`v1-e39-t12`, PM
ruling 2026-10-22, rule C). Both thresholds are one constant, `CARD_ONLY_RULE` in
`debate_core.application.search_index_build`:

| A representative is no card when | Reason recorded |
|---|---|
| Its completeness is CITE_ONLY: a tag and a cite with no evidence text | `cite_only` |
| Its full cite is empty or only whitespace, and its evidence text has fewer than **25** words, counted as whitespace-separated words (`str.split()`) | `no_cite_few_words` |

It is judged on the representative alone. For CITE_ONLY that is every member of the cluster, since
completeness leads the order above. For a card with no cite, another member may have one; reading
every member's card would change the representative order, so they are not read. The parser, the
parsed store and every fingerprint are untouched: this is the build's rule, and a rebuild with
another rule needs no re-parse.

The counts that led to it, over the dev index `767b9c7c056b80cb` (52,059 documents, 2026-10-22), are
in the [`v1-e39-t12` session report](../session-reports/v1-e39-t12-card-only-results.md#the-counts):
1,291 CITE_ONLY and 334 with no cite and under 25 words, 1,625 in all, at most 3.9% of a caselist.

**Where the count is.** What a build left out, by store and reason, is in its result:
`tub index build`'s table caption (`N left out as no card (A cite only, B with no cite and under
25 words)`) and its `--json` `data.not_cards_by_store`, and, for a weekly run that built, the stage's
reason and the run summary's `search_index.not_cards_by_store`. It is **not** in the manifest: the
deployed function reads the manifest with `extra="forbid"`, so a new field would make it refuse the
index (PM ruling 2026-10-22). A run that kept an index already built records `null`, and a weekly run
that finds the stores unchanged keeps the newest index whatever rule built it.

**What the second read costs.** The rule needs the card, which only the document record holds, so the
build reads the representatives' sources twice: once to judge each card, then to write the documents
kept, numbered among themselves. Timed read-only on the operator's Mac on 2026-10-22, one pass took
4.4 s for `openev` (5,846 documents, 95 sources) and 24.3 s for `hspf26` (11,393 documents, 2,133
sources), about 2.1 ms a document, so roughly 100 s more for the whole dev store's 52,059. The full
build is not re-timed here.

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
| `doc_id` | integer key | | The document's rank in (caselist, cluster id) order among the documents kept, from 1 |
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

## How the index is read

`EvidenceSearchService` in `debate_core.application.evidence_search` reads the index read-only and
immutable, through `SqliteSearchIndexReader` (`v1-e39-t03`). A student's query is parsed into quoted
FTS5 phrases and never handed to `MATCH` as typed. It is ranked by `bm25()` with the weights in
`RANKING_WEIGHTS` (tag 10, cite 6, read-aloud text 3, text 1), filtered on `documents`' stored
columns, and paged 20 at a time. `occurrences` is read only by `doc_id`.

**The time budget has a known limit** (accepted by the PM, 2026-10-20). A search that runs past its
budget, 2 s by default, returns what it has fetched, flagged partial. SQLite's progress handler checks
the budget between virtual-machine instructions. FTS5 ranks and sorts every match inside one
instruction, before the first row comes back, and nothing in SQLite 3.40.0 can interrupt that sort.
So a search can overrun its budget by the length of that sort.

The times below were measured on the operator's Mac, not on the function. `v1-e39-t10` measures
query time on the Lambda function itself.

| Index | Queries | Warm p50 | Warm p95 | Warm max |
|---|---|---|---|---|
| The dev index `b9fd48d280ab1c71`, 46,658 documents | Twenty generic queries, 60 timed runs | under 4 ms | 12.1 ms | 207 ms (`the`, 45,948 matches) |
| Synthetic, 250,000 documents | Twenty queries over a skewed invented vocabulary, 60 timed runs | 69.1 ms | 341 ms | 421 ms |

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

| Date | Parser | Spans stored | Stores | Documents | Occurrences | SQLite file | gzip object | Bytes per document (SQLite, gzip) | Build time | Peak memory |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-20 | `2026.10.18-docx-5` | As parser objects | hsld26 11,675; hspf26 10,365; hspolicy26 18,772; openev 5,846 | 46,658 | 273,390 | 1,483,825,152 bytes (1.48 GB) | 319,949,165 bytes (320 MB) | 31,802 and 6,857 | 233 s | 1.18 GB resident |
| 2026-10-20 | `2026.10.18-docx-5` | Compact | The same | 46,658 | 273,390 | 752,369,664 bytes (752 MB) | 281,749,702 bytes (282 MB) | 16,125 and 6,039 | 205 s | 1.14 GB resident |

Both builds read the same store: the dev data directory on the operator's Mac, latest snapshot
2026-10-13, built by SQLite 3.50.4. All 273,390 occurrence rows were read and indexed, with 0
suppressed, 0 clusters left out and every representative attributed; 115,140 occurrences keep their
provenance (limit 5). The Lambda image's SQLite 3.40.0 opened each read-only: `integrity_check` `ok`
and 46,658 documents.

**What changed between them.** The first build (index `5119ffd998e18ad9`) stored each formatting and
font-size span as a JSON object carrying the parser's `rule_id` and `match_source`. That was 805 MB,
54% of the file, at about 115 spans a document. The second (index `b9fd48d280ab1c71`, PM review
2026-10-20, question 4 (a)) stores them as compact arrays without those two fields, still format
version 1. Formatting spans fell from 805.3 to 128.5 MB and font sizes from 73.5 to 19.0 MB; nothing
else changed. The gzip object fell only 12%, because the repeated JSON keys had compressed well.

**Against ADR-0019 (c) 6, the second build.** The SQLite file, 752 MB, is 1.4 times the 550 MB
upper estimate and under the 0.9 GB the PM set as the line for an ADR note. It leaves 248 MB of the
1 GB the plan allows for the season, about 33% growth at today's 16,125 bytes a document. The gzip
object, 282 MB, is above the 110 to 220 MB estimate and below the 400 MB revisit trigger; at 78 MB/s
it downloads in about 3.6 s. A live copy and an incoming one at a weekly swap take 1.50 GB of the
function's 4,096 MB of ephemeral storage.

Where the space goes in the second build, as a share of the 752 MB file (MB from SQLite's `dbstat`
and the columns' byte lengths, read-only):

| Part | MB | Share |
|---|---|---|
| `documents.text` | 241.4 | 32.1% |
| `search_data` (the FTS5 index) | 157.6 | 20.9% |
| `documents.formatting_spans` | 128.5 | 17.1% |
| `documents.read_aloud` | 60.8 | 8.1% |
| `occurrences` | 59.3 | 7.9% |
| `occurrences_by_source` (its index) | 20.8 | 2.8% |
| `documents.font_size_spans` | 19.0 | 2.5% |
| `documents.cite` | 15.5 | 2.1% |
| `documents.tag` | 4.1 | 0.5% |
| The `(caselist, cluster_id)` index, `short_cite`, `sides` and the FTS5 bookkeeping | 5.4 | 0.7% |

The `documents` table is 509.9 MB in all, 67.8%; the rest of it is page and record overhead.
`v1-e39-t09` can track growth against the 1 GB allowance by bytes per document.

## The function's temporary storage while one index replaces another

Worked out from `SearchIndexHolder`'s code (`debate_core.application.search_index_holder`) by
`v1-e39-t14`, 2026-10-22. It is not a measurement taken on the function: no log line records the
bytes on `/tmp`. Sizes are bytes; the function has 4,096 MB of ephemeral storage, 4,294,967,296
bytes.

**What exists at once.** While an environment serves index A and the pointer names index B:

1. A's SQLite file stays in `/tmp/tub-index/`, open and serving, until the swap.
2. B's gzip object is never written to disk. `S3SearchIndexSource.stream_object` reads it in 1 MiB
   chunks, and the holder inflates each chunk as it arrives, hashing both streams, into
   `<B>-<uuid>.part`. That file grows to B's SQLite size.
3. Once both digests and both sizes check out, the `.part` file is made read-only and renamed to
   `.sqlite`. That is the same file, so nothing is copied.
4. The reader opens B, the holder swaps to it, and A's file is deleted at once, because no request
   holds A then: the refresh runs before a request takes its lease, and Lambda gives an environment
   one request at a time. A refused download deletes its `.part` file, and a new process deletes any
   `.sqlite` or `.part` file an earlier one left.

So the peak is **A's SQLite file plus B's**, during step 2, and the gzip object adds nothing. The
holder never keeps more than one old index. Only a request still reading A at the swap would keep A
until it finishes, and the function never has one. The reader opens the file `mode=ro&immutable=1`,
so SQLite writes no journal beside it. SQLite's own temporary files for a large sort are not
counted here.

| Case | A's SQLite | B's SQLite | Peak | Share of 4,096 MB |
|---|---|---|---|---|
| Today, B the same size as A | 839,438,336 | 839,438,336 | 1,678,876,672 | 39.1% |
| Next week at 2026-10-22's 11.6% | 839,438,336 | 936,813,183 | 1,776,251,519 | 41.4% |
| ADR-0019's 1 GB allowance | 1,000,000,000 | 1,000,000,000 | 2,000,000,000 | 46.6% |
| A SQLite file of 2,029,757,701 bytes, growing 11.6% | 2,029,757,701 | 2,265,209,594 | 4,294,967,295 | 100% |

The 11.6% of the week to 2026-10-22 is new documents: index `767b9c7c056b80cb` holds 52,059 of
them, 11.6% more than the 46,658 of 2026-10-20, at the same 16,125 SQLite bytes a document. At that
rate every week, the SQLite file passes `v1-e39-t09`'s 900,000,000-byte warning within the week (the
PM moved that warning to 1,700,000,000 on 2026-10-22, from this working),
ADR-0019's 1 GB allowance in about two, and fills `/tmp` at a swap in about eight. The gzip object,
314,054,035 bytes, passes the 400,000,000-byte revisit trigger in about three. Each weekly run's
growth is in its summary from `v1-e39-t14` on (`documents_growth`, `sqlite_bytes_growth`,
`gzip_bytes_growth`), so the rate can be read rather than assumed.
