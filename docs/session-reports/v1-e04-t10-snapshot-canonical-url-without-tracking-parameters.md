# Session report: v1-e04-t10-snapshot-canonical-url-without-tracking-parameters

| | |
|---|---|
| Task | `v1-e04-t10-snapshot-canonical-url-without-tracking-parameters` — A snapshot's canonical URL drops the tracking parameters its article's does |
| Spec | [`plan_specs/v1/e04-article-retrieval/t10-snapshot-canonical-url-without-tracking-parameters.yaml`](../../plan_specs/v1/e04-article-retrieval/t10-snapshot-canonical-url-without-tracking-parameters.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t10-snapshot-canonical-url-without-tracking-parameters` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The field was **the retrieved URL under a misleading name**. `SourceSnapshot.canonical_url` has been
described as "The URL actually retrieved, after redirects" since `v1-e02-t01`, and `ArticleService`
filled it with `fetched.final_url` on purpose (its docstring: "the snapshot's `canonical_url` is, as
its field says, the URL actually retrieved"). I fixed it by the spec's second route. The URL that
answered moves to a new field named for it, `retrieved_url`. `canonical_url` stays as the canonical
field, because the manifest a coach is handed needs one, and a new snapshot now records its
article's canonical URL there, so the two agree. **No stored row changes and none needs a
backfill.** Snapshots are immutable. Verify also compares a manifest's snapshot reference, `canonical_url`
included, with the stored record, so rewriting a row would make every manifest already exported
from it fail as `SNAPSHOT_REFERENCE_MISMATCH`. Old rows keep the URL they hold, and the one reader that
needs a retrieved URL falls back to it for them. On the operator's Mac a count would touch no row:
there is no production store, and the dev store has 0 snapshots. The beta coaches' stores were not
counted. **Look first at the reader
table**, the "Coach-visible today" line, and the one survivor of the first mutation run, which a
recorded PDF now catches.

## The finding, shown on a recorded page (before any code change)

A probe script (scratchpad only, not committed) ran `test_card_service_e2e.py`'s own path: the real
fetcher over t06's replayed `news-article` cassette, the real extractors and SQLite in a temporary
directory, then a cut with the fake router. It printed, on the unchanged code at `9633fc6`:

```text
requested URL            https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter
article.canonical_url    https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away
snapshot.canonical_url   https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter
source_snapshots rows    [('…mammoth-revival-years-away?utm_source=newsletter', '…mammoth-revival-years-away?utm_source=newsletter')]
manifest reference       https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter
card cite URL (value)    https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away
card cite URL (source)   meta_tag
card cite URL (raw)      /science/2026/09/14/mammoth-revival-years-away
card status              VERIFIED
```

(The `source_snapshots rows` pair is the `canonical_url` column and the same key in the row's JSON
document.) What a snapshot recorded before this task, by provenance:

* **PUBLISHER_RETRIEVED**: `fetched.final_url`, the URL that answered after redirects, tracking
  parameters and all (`article_service.py`, `_publisher_snapshot`).
* **USER_SUPPLIED**: the canonical form of the source URL the user named, which is the article's key
  (`ingest_user_text`). Nothing was retrieved, so this one was canonical already.

## Every reader of the snapshot's `canonical_url`, and what it depends on

Found by `git grep` over `packages/`, `tests/`, `scripts/` and `web/` for the field, for
`SnapshotReference` and for the `source_snapshots` table. One repository adapter (SQLite) and one
fake implement `save_snapshot`; V1 has no cloud snapshot store.

| Reader | What it reads, and what it depends on | Tracking parameters a coach sees, before this task |
|---|---|---|
| **The card's cite and link** (`CitationService.resolve` → `resolve_citation`, printed by `card_rendering` as "URL") | Passes the snapshot's field to `harvest_page` as `retrieved_url`: the base for the page's relative links, path dates and DOIs read from the URL, and the URL of last resort, canonicalized. The page's own stated URLs (JSON-LD, rel=canonical, `og:url`) rank first. **Needs the URL the bytes were read from**, not a canonical one. | **No** in the printed cite. On the recorded news page the cite URL is the page's rel=canonical (probe above). For a page stating no URL of its own (the recorded PDFs), the value is the retrieved URL canonicalized, and the citation's `raw` keeps the retrieved URL as read, so the manifest's card JSON carries it in `citation.canonical_url.raw`. That is `raw`'s contract (the text a value was read out of), and this task leaves it as it is. |
| **The .docx export** (`ExportService` → `docx_manifest_part`) | The visible cite comes from the card's citation (row above). The manifest is embedded as a custom XML part, `customXml/item1.xml`, and its `snapshots[].canonical_url` is the snapshot's field. | **Yes, hidden**: not in Word's visible body, but in the embedded manifest that `verify` reads and anyone unzipping the file sees. |
| **The manifest** (`SnapshotReference.of`, `evidence/manifest.py`) | Copies the field into every `snapshots[]` entry. Written as `<name>.manifest.json` by `search --auto-cut` and by `daily`'s auto-cut (`<preset>-<date>.manifest.json`), embedded in every exported .docx, and summarized by `cut --json` as `data.manifest.snapshots`. Depends on nothing but the stored record. | **Yes**: the `.manifest.json` files a coach is handed, and `cut --json`. This is the "snapshot row" v1-e09-t05 saw. |
| **Verify's snapshot reference check** (`VerifyManifest._reference_reasons`) | Compares every `SnapshotReference` field, `canonical_url` included, between the manifest and the stored record; any difference is `SNAPSHOT_REFERENCE_MISMATCH`. **Depends on the stored value never changing.** The verifier's text check reads the blobs and hashes, never the URL. | No; it prints field names, not values. |
| **The citation check in verify** | Re-resolves the cite through `CitationService` (first row), so it depends on the same retrieved URL. | No. |
| **The search index** | None. Federated search and its articles step read `MergedCandidate.canonical_url` and `ArticleRepository.find_by_canonical_url`, both the article's; the evidence search index holds caselist cards. | — |
| **Dedupe and lookup** | None today. `find_by_canonical_url` reads `articles.canonical_url`. The `source_snapshots.canonical_url` column is written by `save_snapshot` and never queried. | — |
| **v1-e04-t08's planned lookup** "by a snapshot's fetched URL" | Needs the URL a snapshot was fetched from kept on the snapshot. That is now `retrieved_url` (in the row's JSON document, no column of its own), and for rows stored before this task the `canonical_url` column. Matching a tracking variant needs both sides in canonical form. A short link that *redirects* is recorded only as its destination: the fetch target before redirects (`RetrievalOutcome.fetch_url`) is not stored on any snapshot. Under the spec's first route alone, the fetched URL would have been lost and t08 would have had nothing to look up. | — |
| **The API and the web site** | None. `debate_api` and `web/` serialize no snapshot field. The CLI's `fetch` shows the outcome's identity key and the snapshot's id and hashes, never its URL. | — |
| **Logs** | `ArticleService`'s `article retrieval` event logs the outcome's identity key, not the snapshot's field. | — |

**Coach-visible today, with tracking parameters**: the auto-cut `.manifest.json` files (`search
--auto-cut` and `daily`), the manifest inside every exported .docx, and `cut --json`'s
`manifest.snapshots`. After this task, all three name a new snapshot by its article's canonical URL.

## What changed

* `SourceSnapshot.canonical_url` is now "the canonical URL of the article this snapshot was taken of".
  A row stored before this task holds the URL retrieved, and the description says so.
* New `SourceSnapshot.retrieved_url: HttpUrlStr | None` is the URL that answered, tracking parameters
  and all. It is None for user-supplied text and for rows stored before this task. With
  `exclude_if` for None, a snapshot with none is stored byte for byte as before: the existing
  `test_a_snapshot_with_no_stated_citation_is_stored_byte_for_byte_as_before` pins that.
* `SnapshotService.create(..., retrieved_url=None)`. `ArticleService` passes the article's identity
  (the canonical form, then a same-site rel=canonical) as `canonical_url`, and `fetched.final_url`
  as `retrieved_url`. `ingest_user_text` is unchanged.
* `CitationService` harvests a publisher page at `retrieved_url`, or at `canonical_url` for a row
  stored before this task (`_retrieved_url`).
* The manifest's `SnapshotReference.canonical_url` keeps its key and shape, so manifest versions and
  verify are unchanged. Only its description changed. `card_manifest.v1.json` and
  `source_snapshot.schema.json` were regenerated (`uv run --frozen scripts/export_schemas.py`).

**The rule that decides the query**, quoted from v1-e04-t01 (`retrieval/canonical_url.py`, content
rule 7): "Parameters on the tracking deny list are removed (`query_parameters`). A parameter on no
list is kept." And `query_parameters.py`: "**Anything on none of these lists is kept.**" The
snapshot does not apply a rule of its own: it takes the article's identity, so any later change to
those lists, or to rel=canonical, reaches both at once.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `snapshot-canonical-url-without-tracking` (Canonical URL) | Done | Investigation first (above), red tests committed alone (`1b7c4eb`), fix (`2a23a28`), one test added after the first mutation run left a survivor (`8c90e7d`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a snapshot's canonical URL agrees with its article's on a recorded page carrying tracking parameters, by a test shown failing first | PASS | Red at `1b7c4eb` against the unchanged code: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/test_snapshot_canonical_url.py -n 0 -q --tb=line` → `6 failed, 1 passed in 1.01s` (red-run detail below). Green at `8c90e7d`: the same file → `8 passed in 0.61s`. |
| Node: Canonical URL tests pass (`uv run pytest packages/debate_core/tests -k "snapshot or canonical"`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k "snapshot or canonical" -n auto -q` → `1077 passed in 20.63s`. |

### The tests (`packages/debate_core/tests/application/test_snapshot_canonical_url.py`)

All run on recorded pages: the real HTTP fetcher over t06's replay transport (which never reaches the
network), the real extractors, and SQLite in `tmp_path`. "Served at" means a committed cassette's
page bytes, answered at another URL so that it carries the parameters a test needs. Every expected
URL was written by hand.

| Test | Page and URL | Expects |
|---|---|---|
| `test_the_newsletter_link_gives_a_snapshot_canonical_url_without_utm_source` | the committed `news-article` cassette, `?utm_source=newsletter` | article = snapshot = `…/mammoth-revival-years-away`; `retrieved_url` the link; the SQLite row's column and document say the same |
| `test_utm_and_other_tracking_parameters_stay_out_of_the_snapshot_canonical_url` | news page at `?utm_source&utm_medium&utm_campaign&fbclid&gclid&mc_eid` | the same canonical URL; `retrieved_url` keeps all six |
| `test_the_manifest_reference_names_the_snapshot_by_its_canonical_url` | same | `SnapshotReference.of(...)` (what the manifests carry) names the canonical URL |
| `test_a_snapshot_canonical_url_is_its_article_rel_canonical_not_the_link_that_was_followed` | news page at `/s/mammoth?utm_source=newsletter` | the page's rel=canonical, the story's path, not the short path |
| `test_a_snapshot_canonical_url_keeps_the_query_parameters_that_select_content` | government PDF (states no canonical URL) at `?utm_source=newsletter&id=7&edition=summary&fbclid=…` | `…annual-report.pdf?edition=summary&id=7`: `id` is on the allow list, `edition` on no list, both kept and sorted |
| `test_a_user_supplied_snapshot_canonical_url_is_its_article_and_it_records_no_retrieved_url` | news paragraphs as user text, source URL with six trackers | canonical URL as above, `retrieved_url` None, nothing fetched |
| `test_a_snapshot_stored_with_the_retrieved_url_as_its_canonical_url_reads_and_cites_as_before` | a row in the pre-task shape | reads back equal, manifest reference unchanged (`?utm_source=newsletter`), cite harvested as before |
| `test_a_page_stating_no_canonical_url_is_cited_from_the_url_it_was_read_from` | the PDF above | cite URL `…?edition=summary&id=7`, its `raw` the URL as fetched |

**The red run** (`1b7c4eb`, the code unchanged): five tests failed on the canonical-URL assertion
itself, each showing the snapshot holding the fetched URL, e.g. `'…mammoth-revival-years-away'` !=
`'…?utm_source=newsletter&utm_medium=email&…&mc_eid=4f2a9c'`. The PDF test failed the same way,
with `utm_source` and `fbclid` still in. The user-supplied test failed only at `retrieved_url`
(`AttributeError`), because that path was already canonical. The stored-before-this-task test passed,
as a guard should. Each test checks the canonical URL before it touches the new field, so the red
failures are the bug and not a missing attribute.

**Two existing tests changed.** v1-e04-t05's
`test_an_accessible_amp_page_is_fetched_where_it_was_given_never_at_the_guessed_www_host` and
`test_an_accessible_page_with_a_same_site_canonical_is_stored_under_it_and_both_urls_are_kept`
pinned `snapshot.canonical_url == <the URL that answered>`, the behaviour this task changes. They now
pin `canonical_url` to the article's URL and `retrieved_url` to the URL that answered, which keeps
what each was written to show: the AMP page was read where it was given, and both URLs are kept.

### Mutants

Run by a scratchpad script that applies each mutant to the committed tree, runs the covering files
(`test_snapshot_canonical_url.py`, `test_article_service.py`, `test_citation_service.py`,
`test_snapshot_service.py`, `packages/debate_core/tests/domain`) with `-n 0`, each with a new, empty
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8), then `git checkout HEAD --` the file. `git status
--porcelain -- packages` was empty after each batch.

| Mutant | Result |
|---|---|
| **Keeps the tracking parameters**: `canonical_url=fetched.final_url` (the pre-task code) | caught, 7 failed (all five canonical tests and both updated t05 tests) |
| **Strips a meaningful query**: `canonical_url=identity.split('?')[0]` | caught, 1 failed: the PDF query test, `'…annual-report.pdf'` != `'…?edition=summary&id=7'` |
| Ignores rel=canonical: `canonical_url=_canonical(fetched.final_url)` | caught, 2 failed (the short-link test and t05's same-site test) |
| `ArticleService` drops `retrieved_url` | caught, 6 failed |
| `SnapshotService.create` drops `retrieved_url` | caught, 6 failed |
| The harvest without its fallback: `return snapshot.retrieved_url` | caught, 41 failed. A crash: `harvest_page` raises `TypeError` on `None`. That is what the change would really do to every pre-task row and to `test_citation_service.py`'s worlds, which build snapshots in the pre-task shape, not a disabled guard failing somewhere else. |
| The harvest reads `canonical_url` only | **survived the first run** (`1466 passed`): on pages that state their own URL it makes no difference. I added `test_a_page_stating_no_canonical_url_is_cited_from_the_url_it_was_read_from` (`8c90e7d`, which also passes on the pre-task code), and the rerun **caught** it, 1 failed (`raw` became the canonical URL). |
| `exclude_if` removed from `retrieved_url` (a stored `null`) | caught, 5 failed by the existing byte-for-byte record tests |

## Existing rows and the backfill question

* **The stored bytes never change**, and this task writes no row it did not create. A snapshot stored
  before this task keeps `canonical_url` = the URL that answered, and has no `retrieved_url`.
* **No backfill is needed, and one would do harm.** The repository refuses to rewrite a snapshot (the
  contract's `save_snapshot` of a changed record is a conflict). Verify compares the stored record
  with every manifest already written, the `.manifest.json` files and the manifests inside exported
  .docx files, so rewriting `canonical_url` would turn each of those cards
  `SNAPSHOT_REFERENCE_MISMATCH` ("differs from the stored snapshot record in canonical_url").
  Readers handle old rows: the harvest falls back to `canonical_url`, and nothing else reads the
  value.
* **What stays visible**: an old snapshot keeps its tracking parameters in any new manifest that
  references it. That includes a retrieval with unchanged text, which reuses the newest snapshot as
  stored (v1-e04-t05's rule). A new snapshot is made only when the text changes.
* **How many rows a count would touch: none on the operator's Mac** (counted 2026-11-14, after the
  report was first written). The production profile's store, `~/.debate-research/prod`, does not
  exist there: `~/.debate-research/` holds only `dev/` and `dev.env`, and the count's `sqlite3` said
  `unable to open database`. The dev store, `~/.debate-research/dev/debate.sqlite3`, has no
  snapshots. The operator's count of all snapshots, publisher snapshots and the rows named
  otherwise than their article printed `0||`, the blanks being `SUM` over no rows. My check without
  the join printed `snapshot_rows 0`, `article_rows 361` (articles search recorded without
  fetching). So no stored snapshot on that machine holds a fetched URL under `canonical_url`.
  **Not counted: the beta coaches' stores.** If coaches run the CLI on their own machines, their
  snapshots are in their own `~/.debate-research/<env>/debate.sqlite3`, and the same query (under
  Operator follow-ups) counts each one. Where those stores live is the PM's question to answer.

## Commands run before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list only) | 771 test files: `domain/article.py` reaches almost the whole suite (about 6 minutes on this Mac), so I did not run `--run`, and left it to the pull request's `ci` check (agreement 10). |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_core/tests/domain packages/debate_core/tests/evidence packages/debate_core/tests/integrations/local -n auto -q` | `3753 passed in 40.64s` (the always-run list and the changed modules' directories) |
| The same, over `packages/debate_core/tests/application` whole | stopped at its 115-second limit at 96% with no failure printed (load average 9–15), so I ran the next row instead |
| The same, over the 18 application files that touch articles, snapshots, cards, cites, export or verify (`test_article_fetch`, `test_article_registration_service`, `test_article_service`, `test_batch_cut_service`, `test_card_edit_service`, `test_card_service`, `test_card_service_e2e`, `test_citation_service`, `test_export_docx`, `test_export_service`, `test_fakes`, `test_federated_search_articles`, `test_port_conformance`, `test_snapshot_canonical_url`, `test_snapshot_service`, `test_verify_docx`, `test_verify_manifest`, `test_year_and_month_dates_in_a_cite`), plus `packages/debate_cli/tests/test_{cut,fetch,search,daily}_command.py`, `tests/cli/test_fetch_cli.py`, `tests/smoke/test_{cut,fetch}_smoke.py`, `tests/integration` | `939 passed in 21.22s` |
| `… -m slow tests/integration packages/debate_core/tests/application/test_article_service.py packages/debate_core/tests/application/test_snapshot_canonical_url.py` | `12 passed in 5.57s` (the auto-cut end-to-end tests that read the manifest) |
| `.venv/bin/ruff format --check .` / `.venv/bin/ruff check .` | `2132 files already formatted` / `All checks passed!` |
| `.venv/bin/pyright` (whole project, after the last format) | `0 errors, 0 warnings, 0 informations` |
| `.venv/bin/lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 685 files, 41 epics, 622 tasks, 22 releases` |

## Files changed

* `packages/debate_core/src/debate_core/domain/article.py`: `retrieved_url`, and `canonical_url`'s
  description.
* `packages/debate_core/src/debate_core/application/snapshot_service.py`, `article_service.py`,
  `citation_service.py`: write both URLs; read the retrieved URL with its fallback; docstrings.
* `packages/debate_core/src/debate_core/evidence/manifest.py`: `SnapshotReference.canonical_url`'s
  description only (see Deviations).
* `packages/debate_core/schemas/source_snapshot.schema.json`, `card_manifest.v1.json`: regenerated.
* `packages/debate_core/tests/application/test_snapshot_canonical_url.py` (new),
  `test_article_service.py` (two assertions, see above).
* The spec's phase, and this report.

## Deviations from the spec

* **Two files outside `constraints.packages`.** `debate_core.evidence` (`manifest.py`) and
  `packages/debate_core/schemas/` changed, as description text only. `SnapshotReference.canonical_url`
  said "The URL actually retrieved, after redirects", which this change makes untrue for every new
  snapshot, and the committed schemas are generated from those descriptions (their tests fail when
  stale). No field, key or manifest version changed.
* **A network call at the start of the session.** I ran `git fetch origin dev` to check the spec
  against dev for amendments (it showed only the phase, InProgress here and Pending on dev), against
  the standing rule that even read-only network calls go to the operator. It changed nothing in the
  worktree. I did not fetch again before the report, so I have not checked whether the PM amended
  the spec on dev during the session.

## Decisions and assumptions

* **Route 2, not route 1 alone.** Making the field canonical and nothing more would have thrown away
  the URL the bytes were read from. That is provenance, and the cite harvest and t08's planned
  lookup both need it. The PM's second route allows keeping a canonical field where a reader needs
  one, and the coach's manifest is that reader. So `canonical_url` is that field, and the URL that
  answered moves to `retrieved_url`. Under the PM's ruling this needed no stop: it changes no
  existing row.
* **The manifest gains no `retrieved_url`.** Adding a key to `SnapshotReference` (`extra="forbid"`)
  would make a manifest this build writes unreadable to an older build, and would need a manifest
  version. Nothing a manifest reader does needs it.
* **No new SQLite column.** `retrieved_url` lives in the row's JSON document. The existing
  `canonical_url` column now holds the canonical URL for new rows. Neither is queried today; t08
  decides whether it needs an indexed column.
* **No smoke check changed.** The CLI's output shapes are unchanged, and only the value a new
  snapshot's manifest reference holds changes. `tests/smoke/test_cut_smoke.py` builds its snapshot
  directly in the pre-task shape and still passes (the 939-test row above).
* **Expected values are hand-written** from the URL fetched, the page's rel=canonical and t01's
  rules (agreement 6). None was saved from a run.

## Operator follow-ups

**Done on the operator's Mac, 2026-11-14:** the production store does not exist there, and the dev
store has 0 snapshots (results under "Existing rows and the backfill question"). The commands stay
here for any other store, such as a beta coach's.

**How many stored snapshots a backfill would touch** (read-only, seconds). This is for the PM's
backfill question; I recommend no backfill (above). Where: the machine that holds the store, any
directory. It prints three
counts per store: all snapshots, publisher snapshots, and the rows named otherwise than their article
(the rows a canonical backfill would rewrite). `-readonly` changes nothing, though a read of a WAL
database can leave `-wal`/`-shm` files beside it, which is harmless. A store that does not exist
prints `unable to open database`. Run the first command for the production profile's store:

```bash
sqlite3 -readonly -header ~/.debate-research/prod/debate.sqlite3 "SELECT COUNT(*) AS snapshots, SUM(json_extract(s.document, '\$.provenance_mode') = 'PUBLISHER_RETRIEVED') AS publisher, SUM(s.canonical_url <> a.canonical_url) AS named_otherwise_than_their_article FROM source_snapshots s JOIN articles a ON a.article_id = s.article_id"
```

and this one for the dev profile's store:

```bash
sqlite3 -readonly -header ~/.debate-research/dev/debate.sqlite3 "SELECT COUNT(*) AS snapshots, SUM(json_extract(s.document, '\$.provenance_mode') = 'PUBLISHER_RETRIEVED') AS publisher, SUM(s.canonical_url <> a.canonical_url) AS named_otherwise_than_their_article FROM source_snapshots s JOIN articles a ON a.article_id = s.article_id"
```

Success looks like one header line and one line of three numbers, for example `12|11|9`. I checked
the query on a scratch store with one planted row, where it printed `1|1|1`. If coaches' stores live
anywhere else, the same query applies to each `debate.sqlite3`.

## Follow-up work

* **v1-e04-t08 (lookup by a snapshot's fetched URL).** The URL to look up is now `retrieved_url`, or
  the `canonical_url` column for rows stored before this task. Neither is indexed, and a redirected
  short link is stored only as its destination (the fetch target is not kept). t08 should decide
  whether to store the fetch target and its canonical form in a column. That is a schema change, so
  it needs the PM's word on a migration.
* **A page's own stated URL is not canonicalized in the cite** (E06, `citation_harvest._urls`). An
  `og:url` or rel=canonical that itself carries `utm_` parameters would go into the card's cite as
  stated. No recorded page does this, so I measured nothing; noted only because the PM asked which
  readers can show a coach tracking parameters.
* **v1-e09-t05's end-to-end test** reads "which page an auto-cut card came from" through the
  snapshot's article because of this field. It could now read the manifest directly (E09). Nothing
  breaks if it does not.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
