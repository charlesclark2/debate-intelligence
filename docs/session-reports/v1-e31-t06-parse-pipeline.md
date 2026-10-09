# Session report: v1-e31-t06-parse-pipeline

| | |
|---|---|
| Task | `v1-e31-t06-parse-pipeline` — Incremental parse pipeline |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t06-parse-pipeline.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t06-parse-pipeline.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t06-parse-pipeline` |
| Session status | PARTIAL: every node and criterion this session can close passes; ac5 (the operator's full-corpus parse and publish, dev then prod) is NOT RUN |

## Summary

`debate-research caselist parse` now exists. It reads the sources the local weekly manifests and
OpenEv release store, and skips any it has already parsed under the same source sha256,
`parser_version` and `profile_version`. It parses the rest with the t03 parser in a bounded spawn
pool with a per-file time limit, then rebuilds the index, failures file and occurrence table with
the t04 fingerprinting and clustering. The store is JSONL under
`<data_dir>/parsed/<caselist>/<parser_version>/`, documented in
[`docs/data/parsed-card-store.md`](../data/parsed-card-store.md). `--publish` copies it to
`parsed/` in the `DEBATE_ENV` bucket, skipping objects whose checksum matches.

**Read these first:**

1. **Deviation 1, a policy conflict.** The data-use policy says personal data may live only in the
   local store, the bucket's `manifests/` prefix, built-file sidecars and the per-school view.
   `parsed/` is not on that list. So the store holds no disclosure path, school, team code,
   tournament or round. A disclosure is recorded by the same digest the suppression list uses, and
   a card's path is put back from the manifests on read. The PM should confirm this, or amend the
   policy.
2. **Short-card recall is materially below overall recall.** On t04's variant set, overall recall
   is 0.947 but 0.333 on pairs involving a short card. On the new short-card set it is 0.708 for
   full short cards and 0.250 for an abbreviated disclosure against its full copy. Precision is
   1.000 everywhere. This is a spec change for its own task; see "Short-card recall".
3. **The rebuild can go quadratic.** Rebuilding one synthetic 300-page file of near-copies took
   57 s (12.8 million candidate checks). How the real corpus behaves is what the operator run
   measures; the estimates are under Operator follow-ups.

**The Goal stays `InProgress`.** ac5 is the operator's run and cannot close in a session. Merge with
`scripts/task pr --partial`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `parsed-store` — Parsed card store port and local JSONL adapter | Done | `application/ports/parsed_store.py` (records, version naming, skip key, the port), `integrations/local/parsed_store.py` (Deviation 3), the in-memory fake, and the layout document. |
| `incremental-parse-service` — CaselistParseService with incremental skipping | Done | `application/caselist_parse.py`, with `application/caselist/parse_sources.py` (enumeration and the full-archive rule) and `application/caselist/parse_workers.py` (the pool). |
| `publish-parsed` — Publish the parsed store to S3 | Done | `application/caselist/parsed_publish.py`, in the vocabulary of `caselist publish` (`SourceResult`). |
| `parse-cli-and-smoke` — `caselist parse` command, smoke check and gates | Done | `debate_cli/commands/caselist_parse.py`, the container factories, `tests/smoke/test_caselist_parse.py`. |
| `operator-corpus-parse` — First full-corpus parse and publish (operator-run) | Not run | The commands are under Operator follow-ups. `docs/data/caselist-parse-report.md` is the template the run fills in. |

## Acceptance criteria

The session ran every command from the task worktree on 2026-10-09, with the default pytest options
(coverage, xdist) unless a row says otherwise.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — A second run over an unchanged store parses zero files and reports every source skipped; a new snapshot parses only its new sources; `--reparse` or a `parser_version` bump re-parses into a new version directory without touching the old one | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_parse.py` → `35 passed in 7.13s`. `test_a_second_run_…_parses_nothing_and_skips_every_source`: the counting parser is called 0 times, skipped 6, and the version directory is byte-identical. `test_importing_a_new_snapshot_parses_only_its_new_sources`: only `direct` is parsed. `test_reparse_writes_a_new_version_directory_and_leaves_the_old_one_byte_for_byte`, `test_a_parser_version_bump_…` and `test_a_profile_bump_…`: the old directory's bytes are unchanged in each. Shown failing first (below). Through the CLI: `test_a_second_run_parses_nothing_and_reports_every_source_skipped`. |
| **ac2** — The layout (index, per-source ParsedDocument JSONL, occurrences, failures) is documented in `docs/data/parsed-card-store.md`, and every record carries caselist, snapshot, source sha256, parser_version, profile_version and fingerprint_version | PASS | The document exists with its docs-index line. `grep -c parser_version docs/data/parsed-card-store.md` → `4`. `test_every_record_in_every_file_carries_the_six_fields` (adapter) and `test_every_record_the_run_writes_carries_the_six_fields` (service) read every line of every file written and check all six. |
| **ac3** — One failing source never aborts the run; it is recorded in failures.jsonl with a typed reason and listed by `caselist parse --failures`; exit 0 unless the failure rate exceeds a configurable threshold | PASS | `test_one_failing_source_is_recorded_with_its_reason_and_the_run_carries_on`: `NOT_A_ZIP` for the broken file, and `UNSUPPORTED_FORMAT` with format `PDF` and `DOC`. `test_a_parser_that_raises_…` (`PARSER_ERROR`), `test_a_parse_past_the_time_limit_…` (`TIMEOUT`, real pool), `test_a_worker_that_dies_…` (`WORKER_CRASHED`, real pool). `test_unsupported_formats_count_on_neither_side_of_the_failure_rate`: 0.25, not 0.5. CLI: `test_failures_lists_each_source_…`, `test_a_failure_rate_above_the_threshold_exits_non_zero_…` (`DEBATE_PARSE__FAILURE_RATE_THRESHOLD`). Shown failing first. |
| **ac4** — `--publish` uploads new parsed objects to `parsed/<caselist>/<parser_version>/` in the DEBATE_ENV bucket through the blob-store port, skips objects whose checksum matches, and a rerun uploads nothing | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_parse.py -k publish` → `6 passed in 5.52s` (moto). PutObject requests are counted at botocore's event hook: the first publish puts exactly the local files, with aggregates last; a rerun puts 0; a new snapshot puts the new source's file plus the two aggregates it changed. Mismatch withholds the aggregates; a suppressed source's file is never sent; keys and metadata name no identifier. CLI: `test_publish_uploads_the_store_and_a_rerun_uploads_nothing`, and prod refused without `--confirm-prod`. Shown failing first. |
| **ac5** — `docs/data/caselist-parse-report.md` records the operator-run parse of the downloaded snapshots and camp files in dev and then prod | NOT RUN | The operator's run, well over 2 minutes and against real buckets (working agreement 2; the spec forbids it in a session). The template exists, holds only counts, and deliberately contains no `prod` string until the run is recorded. Commands, runtimes and what to paste back are under Operator follow-ups. |
| **ac6** — The suppression list is a required argument with no default; after a removal, no aggregate holds an entry derived from a removed source; a test removes a source that contributed to each aggregate, shown failing first | PASS | `test_the_suppression_list_is_a_required_argument_with_no_default`. `uv run pytest packages/debate_core/tests/application/caselist/test_parsed_store_removal.py` → `5 passed in 5.94s`: a real `caselist remove --execute` on moto removes a team that contributed to all three aggregates. Afterwards no aggregate, local or in the bucket, in any version directory, current or noncurrent, holds its rows; the next run rebuilds each one without them; and a removal made on another machine (suppression list only) is honoured by each aggregate. Red first: below. |
| Node `parsed-store`: `uv run pytest packages/debate_core/tests/integrations/test_local_parsed_store.py` | PASS | `26 passed in 4.93s` |
| Node `parsed-store`: `docs/data/parsed-card-store.md` contains `parser_version` | PASS | `grep -c parser_version docs/data/parsed-card-store.md` → `4` |
| Node `incremental-parse-service`: `uv run pytest packages/debate_core/tests/application/test_caselist_parse.py` | PASS | `35 passed in 7.13s` |
| Node `publish-parsed`: `uv run pytest packages/debate_core/tests/application/test_caselist_parse.py -k publish` | PASS | `6 passed in 5.52s` |
| Node `parse-cli-and-smoke`: `uv run pytest packages/debate_cli/tests/test_caselist_parse.py` | PASS | `11 passed in 6.35s` |
| Node `parse-cli-and-smoke`: `uv run pytest tests/smoke/test_caselist_parse.py` | PASS | `3 passed in 5.54s`, unmarked, offline, through the console script with a two-worker pool |
| Node `parse-cli-and-smoke`: `uv run pyright packages/debate_core packages/debate_cli` | PASS | `0 errors, 0 warnings, 0 informations` |
| Node `parse-cli-and-smoke`: `uv run lint-imports` | PASS | `Contracts: 12 kept, 0 broken.` (one contract added, Deviation 6) |
| Node `operator-corpus-parse`: `docs/data/caselist-parse-report.md` contains `prod` | NOT RUN | `grep -c -i prod docs/data/caselist-parse-report.md` → `0`, by design, until the operator's run is recorded |

Also run, not criteria of this task:

| Check | Result |
|---|---|
| Whole default suite, `uv run pytest -q --no-cov` | `4829 passed, 1 skipped, 1 warning in 65.34s`. The skip is the existing parser eval that waits on human corrections; the warning is `test_smoke_harness.py`'s, unchanged |
| `uv run ruff check .`, `uv run ruff format --check .` | `All checks passed!`, `564 files already formatted` |
| `uv run pyright` (whole repository) | `0 errors, 0 warnings, 0 informations` |
| `uv run scripts/check_thin_handlers.py` | `OK: 21 CLI command and API route handlers within 25 statements` (`caselist parse` is 22) |
| `uv run scripts/check_command_blocks.py --base origin/dev`, `uv run scripts/check_links.py`, `uv run scripts/docs_index.py --check-descriptions` | all OK |
| `uv run scripts/validate_specs.py` | `OK: 319 files, 38 epics, 261 tasks, 20 releases` |

## Shown failing first

Each check was run with the behaviour it guards removed, by exact replacement in a scratch script
that refused an anchor not found exactly once. The file was then restored from git and the tree
checked clean.

| Criterion | Behaviour removed | Result |
|---|---|---|
| ac1, the second run parses zero | The skip check (`if skip_key(...) not in done` → `if True`) | `test_a_second_run_…` fails: the run tries to parse every source again, and the adapter refuses it with `ParsedStoreRefusal: source 0cf11d8c… is already recorded in testcl26/2026.09.20-docx-1; a re-parse writes a new version directory` |
| ac3, one failing source does not abort the run | The worker's catch of a parser that raises | `test_a_parser_that_raises_on_one_source_fails_that_source_only` fails with `RuntimeError: synthetic parser bug`: the run stopped |
| ac4, the rerun uploads nothing | The publisher's checksum skip | `test_a_publish_rerun_uploads_nothing` fails: `assert 0 == 9` skipped |
| ac6, the removal cleans each aggregate | Written before the removal planner knew about aggregates, and run on that code | 2 failed, 3 passed: `test_caselist_remove_leaves_no_aggregate_holding_the_team_…` (`failures.jsonl` still held the team's PDF and `.doc`), and `test_the_next_run_rebuilds_each_aggregate_…` (the older directory still had its `index.jsonl`). The 3 that passed are the precondition, the per-source deletion (see Decisions, "What `caselist remove` already did") and the removal-elsewhere case, which the rebuild already handled |

## Mutation runs

Each mutant ran in a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` made with `tempfile.mkdtemp` and
checked empty first, in two batches of 21.5 s and 17.3 s wall-clock, with `-x`, so a "failed"
count is a floor rather than the total. None of these tests uses a
Hypothesis property, so the isolation is set as working agreement 8 requires but cannot affect
them. Each ran its tests (no collection errors), each file was restored from git, and
`git status --porcelain` was empty after every run.

| Mutant | Tests run | Result | Time |
|---|---|---|---|
| The skip key without `profile_version` | service and store tests | CAUGHT: 2 failed (`test_a_profile_bump_…` ran into the old directory; `test_the_skip_key_is_the_digest_and_both_versions`) | 4.3 s |
| A re-parse writing into the old version directory (the service picks it) | service tests | CAUGHT: 3 failed, each on the adapter's `ParsedStoreRefusal` | 4.3 s |
| The same, with the adapter's refusal also removed | service tests | CAUGHT: 2 failed on `version == …_reparse-2` and the old directory's bytes | 4.3 s |
| An unsupported format counted towards the failure rate | service tests | CAUGHT: 3 failed, `assert 0.5 == 0.25` | 4.1 s |
| Full-archive manifests included in enumeration | service tests | CAUGHT: every one of the five planted key shapes failed (re-run without `-x`: 5 failed, 30 passed) | 4.5 s (8.5 s without `-x`) |
| The suppression list not consulted for the index | service and removal tests | CAUGHT: `assert (7, 14) == (5, 14)` | 4.7 s |
| …for the failures file | service and removal tests | CAUGHT: `failures.jsonl` kept the PDF and `.doc` | 4.7 s |
| …for the occurrence table | service and removal tests | CAUGHT: `assert (5, 16) == (5, 14)` | 4.7 s |
| `caselist remove` no longer deletes the aggregates | removal tests | CAUGHT: 2 failed | 3.2 s |

## Short-card recall

Measured by `packages/debate_core/tests/evidence/test_short_card_recall.py` (run with `-s`), over two
hand-labelled sets. One is t04's variant set. The other is the new `tests/fixtures/fingerprints/short_cards.jsonl`,
committed with its labels (`bd98e42`) before the measuring test existed: four invented short cards
(13 to 34 words) with trimmed, OCR-split and mistyped copies, a long card for comparison, and twelve
abbreviated disclosures cut several ways. Both go through `CaselistCardStatsService.place`, the step
the pipeline builds its occurrence table with. A card is short below 60 words. Figures are over
pairs of rows.

| Pairs | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| Variant set, all | 71 | 0 | 4 | 1.000 | **0.947** |
| Variant set, involving a short card | 2 | 0 | 4 | 1.000 | **0.333** |
| Variant set, long cards only | 69 | 0 | 0 | 1.000 | 1.000 |
| Short-card set, all | 36 | 0 | 45 | 1.000 | 0.444 |
| Short-card set, full short cards | 17 | 0 | 7 | 1.000 | **0.708** |
| Short-card set, the full long card | 1 | 0 | 0 | 1.000 | 1.000 |
| Short-card set, abbreviated against a full copy | 11 | 0 | 33 | 1.000 | **0.250** |
| Short-card set, abbreviated against abbreviated | 7 | 0 | 5 | 1.000 | 0.583 |

**Short-card recall is materially below overall recall.** Precision is perfect. The misses come
from three mechanisms, read off the cluster each row landed in:

1. **One changed word drops a short card below the confirmation threshold.** In a 33-word card a
   one-word typo removes 5 of about 29 shingles: containment 0.83 against the 0.9 threshold. An OCR
   split in a 19-word card gives 0.67. A long card absorbs the same edit. This is the threshold, not
   the banding: t04's other miss (containment 1.0, Jaccard 0.44, never paired by the 32x4 banding)
   is the banding's.
2. **A split full card leaves every abbreviation of it unlinked.** An abbreviated disclosure links
   only when every full card matching its cite and opening and closing words is in one cluster. When
   the typo copy above formed its own cluster, all five abbreviations of that card matched two
   clusters, and each stayed unlinked. One near-duplicate miss among the full copies therefore
   becomes a miss for every abbreviated disclosure of the card.
3. **Abbreviations with no full copy never meet unless cut identically.** Two teams' abbreviations
   of the same card, cut at different words, are two clusters. In a wiki-converted caselist, where
   most cards are abbreviated, this is likely the common case.

This bears directly on E32's counts: cluster and distinct-team counts will be undercounted for the
format the corpus is mostly made of. Changing the banding, the thresholds for short bodies or the
linking rule is a spec change for its own task, not this one; see Follow-up work. The real corpus's
short-card share is in the operator's run (`linked_abbreviated` and `unlinked_abbreviated` are what
`caselist cards` would report; the store's occurrence rows carry `membership`).

## Files changed

**Application layer (`packages/debate_core/src/debate_core/application/`)**
* `ports/parsed_store.py` (new): the store's records (`SourceEntry`, `DocumentRecord`,
  `OccurrenceRecord`), version-directory naming, the skip key, aggregate names and the `ParsedStore`
  port. `ports/__init__.py`: the re-export and a row in the port table.
* `caselist_parse.py` (new): `CaselistParseService`, its plan, run report and failure listing.
* `caselist/parse_sources.py` (new): enumeration from manifests, with the explicit
  weekly-series-only rule.
* `caselist/parse_workers.py` (new): the in-process runner and the bounded spawn pool with a per-file
  time limit.
* `caselist/parsed_publish.py` (new): `ParsedStorePublisher`.
* `caselist/removal_plan.py`: `caselist remove` also deletes every parsed aggregate of the caselists
  it touches (`ObjectKind.PARSED_AGGREGATE`).
* `ports/debate_files.py`: `profile_version` on the parser port (Deviation 4).
* `caselist_card_stats.py`: `place()` made public, with `CardPlacement` (Deviation 5), and two
  docstrings corrected.
* `settings.py`: the `parse` group (`workers`, `worker_cap`, `per_file_timeout_seconds`,
  `failure_rate_threshold`).

**Adapters**: `integrations/local/parsed_store.py` (new); `integrations/docx_parser/parser.py`:
`profile_version`.

**Test doubles (`debate_core.testing.fakes`)**: `InMemoryParsedStore`, `build_fake_parsed_store`,
`MisbehavingDebateFileParser` (stalls, dies or raises on chosen digests, for the pool), and
`profile_version` on `FakeDebateFileParser`.

**CLI (`packages/debate_cli/`)**: `commands/caselist_parse.py` (new), its registration,
`container.py` (`caselist_parse`, `parsed_publisher`, `SERVICE_NAMES`), and the hand-pinned
integration lists in `tests/test_installation.py`, `tests/commands/test_doctor.py` and
`tests/test_app.py`.

**Tests**: `packages/debate_core/tests/integrations/test_local_parsed_store.py`,
`packages/debate_core/tests/application/test_caselist_parse.py`,
`packages/debate_core/tests/application/caselist/test_parsed_store_removal.py`,
`packages/debate_core/tests/evidence/test_short_card_recall.py`,
`packages/debate_cli/tests/test_caselist_parse.py`, `tests/smoke/test_caselist_parse.py` and its
README row.

**Fixtures**: `tests/fixtures/parse_pipeline/build_parse_world.py` (a fictional caselist whose files
are t03's structural fixtures, with hand-written expectations), and
`tests/fixtures/fingerprints/short_cards.jsonl`.

**Configuration**: `pyproject.toml` (one import-linter contract split, Deviation 6) and
`tests/architecture/test_import_contracts.py` (its violation probe).

**Docs**: `docs/data/parsed-card-store.md` and `docs/data/caselist-parse-report.md` (new, each with
its docs-index line).

## Deviations from the spec

1. **The store holds no personal data, so what is published is not quite what t04 expected.** The
   spec says the same objects go to `parsed/` in the bucket. The data-use policy lists the only places
   personal data may live: the local store, the buckets' `manifests/` prefix, a built file's
   provenance sidecar and the per-school view. It treats disclosure paths and team codes as personal
   data about minors. `parsed/` is not on that list. Working agreement 7 says the policy governs, so:
   * A stored document is the `ParsedDocument` without its `source_path` or any card's
     `provenance.source_path`. `DocumentRecord.to_parsed_document(path)` puts the path back, taking it
     from the manifests.
   * The occurrence table is one row per card per disclosure. Each row holds caselist, snapshot and
     `disclosure_digest(caselist, path)`: the pseudonym the suppression list already uses for a
     withdrawn disclosure. It does not persist t04's `CardOccurrence`, which carries school, team
     code, tournament, round and cutter mark. Who disclosed a card is a join with the manifests.
   * What is published is exactly what is on disk, so a re-publish compares checksums file by file.

   The other way round is for the PM and Charlie to decide: amend the policy to add `parsed/` (same
   bucket, same controls as `manifests/`). Then the store could hold paths and t04's team-keyed
   occurrences directly. t04's report assumed that; its "keep the cutter mark out of anything
   published outside the private stores" reads `parsed/` as a private store.

2. **Version directories have generations.** The spec's layout is `<parser_version>/`. A `--reparse`,
   or a style-profile change under the same parser version, must write a new directory without
   touching the old one (ac1, and the PM's brief). That needs a second name, so it writes
   `<parser_version>_reparse-<n>`. The newest generation of the running parser version is the current
   directory. Readers find it with `ParsedStore.version_directories`.
3. **The adapter is `integrations/local/parsed_store.py`, not `integrations/local_parsed_store.py`.**
   Inside `integrations.local` it falls under the import-linter contracts that already name that
   package. At the spec's path it would sit outside the AWS-SDK and HTTP-client contracts, which list
   adapter subpackages by name. The test file is at the spec's path.
4. **The `DebateFileParser` port gained `profile_version`** (t03's port; the adapter and the fake
   implement it). The skip key needs the profile version before a file is parsed, not read off the
   result.
5. **t04's `CaselistCardStatsService` gained a public `place()`**, the first three steps of `report()`
   without the join to disclosures, with `_Placed` renamed `CardPlacement`. The pipeline reuses t04's
   fingerprinting, clustering and linking through it. `report()` is unchanged, and all of t04's tests
   pass untouched.
6. **An import-linter contract was split.** t03's "Document libraries stay inside
   `debate_core.integrations.docx_parser`" forbade `debate_cli` from reaching lxml even through the
   composition root, which has to build the parser. `debate_cli` moved to a new contract, "The CLI
   reaches lxml only through `debate_core.integrations.docx_parser`", with indirect imports allowed:
   the same shape as the existing AWS-SDK contract. `tests/architecture/test_import_contracts.py`
   gained the matching violation probe, and it is caught. `pyproject.toml` and `tests/architecture/`
   are outside `constraints.packages`.
7. **Store methods are `write_source` and friends, not `put_source`.** t07's architecture test scans
   for calls named `put_source` (the caselist repository's write) outside the import pipeline, and
   flagged the store's method of the same name. The scan stays as it is.
8. **Flags the spec's list does not name.** `--confirm-prod`: publishing to prod needs it, as
   `caselist publish` does and as the brief asks. `--json` is accepted after the command as well as
   before it, as `caselist cards` does.
9. **Outside `constraints.packages`**: `debate_core.testing` (fakes), the fixtures under `tests/fixtures/`,
   the tests under `packages/*/tests/`, `tests/architecture/`, `pyproject.toml` and
   `tests/smoke/README.md`. Each is the test, fixture or configuration side of a change inside the
   listed packages.
10. **The spec's description has a garbled sentence.** The PM's short-card paragraph was inserted in
    the middle of "OpenSearch indexing is V2 and derived from this store", which now reads "OpenSearch
    indexing is Measure near-duplicate recall … V2 and derived from this store." Left for the PM to
    fix.

## Decisions and assumptions

* **ac6: rebuilt, not filtered on read.** Two reasons. First, the policy's retention table deletes
  "parsed cards, fingerprints and classifications derived from them" with their sources, and a
  removal purges noncurrent versions at once. Filtering on read leaves the removed source's
  fingerprints at rest, here and in old bucket versions of the aggregates. Second, a filter on read
  has to be right in every reader E32, E33 and E34 will write; a rebuild is right once. So:
  * every run rebuilds all three aggregates from scratch, from the per-source files, the manifests
    and the suppression list, and never carries a row forward;
  * each aggregate consults the list itself (the mutation runs show each check is needed);
  * `caselist remove --execute` deletes the aggregates of every caselist it touches, in every
    version directory, locally and in the bucket with every version.
  
  Between a removal and the next run, no aggregate holds the source because none exists. Readers
  treat a missing aggregate as "not built". Older version directories keep their per-source files
  and are not rebuilt, because nothing writes to them again.
* **What `caselist remove` already did.** It deletes any file under `parsed/<caselist>/` whose name
  starts with the removed digest, in the bucket with every version and locally, at any depth. The
  per-source file name begins with the digest, so the spec's statement holds for this layout without
  a change. `test_caselist_remove_deletes_the_removed_sources_files_in_every_version_directory` shows
  it in two version directories. What it did not do was touch the aggregates. That was the gap, and
  is fixed above.
* **The full-archive rule.** Only `manifests/<slug>/<YYYY-MM-DD>.jsonl` and
  `manifests/openev/<year>-<event>.jsonl` are read (`parse_sources.series_snapshot`). Anything else
  under the prefix is never enumerated, whatever `v1-e34-t04` calls its namespace. The test plants
  five plausible shapes (`full/`, `all/`, `archive/`, `-all`, `.full`) naming a digest the weeklies
  hold and one they do not. It checks that neither reaches the parse or the occurrence table.
  `v1-e34-t04` is still `Pending`; run `scripts/task sync` after it merges and re-run this test.
* **Unsupported formats.** `UNSUPPORTED_FORMAT` gives outcome `UNSUPPORTED`, with the manifest's
  format (`PDF`, `DOC`, `OTHER`) beside it. Every other reason is `FAILED`, including
  `MACRO_ENABLED`, `TIMEOUT`, `WORKER_CRASHED` and `PARSER_ERROR`. The failure rate is `FAILED` over
  the sources this run tried that are not `UNSUPPORTED`, and 0 when it tried none. A `.docm` file is
  stored as `OTHER` and is therefore `UNSUPPORTED`; `MACRO_ENABLED` is a `.docx` that turns out to
  carry macros. The default threshold is 5%.
* **Which failures are retried.** All are recorded under the skip key and skipped next time, except
  `SOURCE_MISSING` (a manifest names a blob this machine does not hold), which says nothing about
  the bytes. `--reparse` retries everything, in a new generation.
* **Per caselist.** Each caselist's store stands alone, so the same bytes in two caselists, or a
  camp file a team also disclosed, are parsed once per store. That way removal and publish reach
  each store by caselist, and a card's provenance names the right caselist or camp.
* **Parsed under the earliest snapshot.** A source's document records the earliest snapshot and the
  first path (by path order) of its earliest live disclosure. The occurrence table carries every
  disclosure.
* **Sections are not stored** (t03 left this to t06). A 300-page file has about 9,000, they are
  reproducible from the bytes by the same parser version, and no reader needs them. Cards are stored
  whole, with spans.
* **The pool.** Workers are spawned (not forked) on every platform. Each has its own pipe, so a parse
  past the limit is ended by terminating that worker and starting another. A future-based executor
  can only abandon a stuck parse and lose the worker. The default is the machine's cores minus one,
  at most 6 (`parse.worker_cap`). The per-file limit is 120 s; a 300-page file parses in about 2 s. No
  worker starts when nothing needs parsing.
* **Writes are atomic and incremental.** Each per-source file is written as its result arrives, so a
  run stopped part-way keeps what it finished, and the next run skips it.
* **Publishing order.** Per-source files go first and aggregates last, and the aggregates are
  withheld if any per-source file failed. A per-source file the bucket holds with other bytes is
  reported and left alone, as `caselist publish` treats a mismatch; an aggregate is replaced.
* **What is logged.** One INFO line per run, and one per publish, of counts, the caselist and the
  version. DEBUG adds the sha256 prefix and reason of each failure. Tests capture `debate_core` at
  DEBUG and check that no fictional school, team code, tournament, filename fragment, tag or card
  text appears. `--failures` prints paths to the terminal, and its `--json` carries
  `contains_disclosure_paths: true` and a notice. No document reproduces its output.
* **Read-only counts of the operator's store.** To size the estimates, the session read the dev data
  directory's manifests and counted distinct stored sources by format and bytes (0.1 s, nothing
  written). The counts are in the parse report's "corpus before the run" table. There are no legacy
  `.doc` files in the corpus; there are 1,320 PDFs, 1,240 of them in PF.

## Throughput, and the estimate for the corpus

Measured on this Mac (11 cores, so 6 default workers) with a scratch script over synthetic files
(`--no-cov`, nothing committed):

| Run | Result |
|---|---|
| 400 sources: the 10 structural fixtures, 40 distinct copies each (839 KiB), pool of 6 | 0.69 s, 579 files/s, of which the rebuild was 0.15 s |
| The same in one process | 0.53 s, 760 files/s: at 2 KiB a file, worker start-up costs more than parsing |
| t03's 300-page synthetic file (5.01 MiB `document.xml`, 5,250 cards), in one process | parse 1.78 to 2.23 s, about 0.4 s per MiB of `document.xml`; stored record 9.6 MiB |
| Two of those, pool of 6 | parse about 5.4 s; **rebuild 57 s** |

The rebuild figure is the one to watch. Profiling it, 12.8 million Jaccard/containment
confirmations account for nearly all of it, because every card in that synthetic file is a near-copy
of every other (they differ only in a zone number), so LSH makes almost every pair a candidate.
Reading, validating, fingerprinting and MinHashing the 10,500 cards took about 3 s altogether. Real
cards are mostly distinct, so the real rebuild should be far cheaper. But it is single-process,
holds a caselist's cards in memory, and is repeated on every run.

**Estimate for the corpus** (11,126 sources: 9,741 DOCX, 2,259 MiB compressed). The real
`document.xml` sizes are not measured. At 4 to 8 times the compressed size, parsing is 9 to 18 GiB
of XML, 1 to 2.3 CPU-hours, so **about 10 to 25 minutes with 6 workers**. Each caselist's rebuild
adds an estimated 2 to 6 minutes, and the first publish of about 11,130 objects an estimated 10 to
20 minutes (the backfill runbook's figure for a store of that size). The per-caselist figures are
in Operator follow-ups. A second run parses nothing and costs the rebuild plus the publish's
checksum checks.

## Operator follow-ups

**1. The full-corpus parse and publish, dev first** (ac5). Two hand-offs: dev, then prod. Run them
on your Mac in this task worktree, or in any checkout that holds this branch's commits. Don't run
them while `caselist pull` is running: `caselist runs --last 1` shows the last run.

Start in the worktree and confirm the branch and commit:

```zsh
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t06-parse-pipeline
git branch --show-current
git log --oneline -1
```

Expected: `task/v1-e31-t06-parse-pipeline`, and `8e36e83` or a later commit of this report.

**The dry run** (seconds, writes nothing, needs no AWS session):

```zsh
export DEBATE_ENV=dev
uv run debate-research caselist parse --caselist hsld26 --dry-run
uv run debate-research caselist parse --caselist hspolicy26 --dry-run
uv run debate-research caselist parse --caselist hspf26 --dry-run
uv run debate-research caselist parse --caselist openev --dry-run
```

Success looks like this: version `2026.09.20-docx-1`, skipped 0 and suppressed 0 for each. "To
parse" should be 4,461 for hsld26, 2,657 for hspolicy26, 3,906 for hspf26 and 102 for openev. Any
other count, stop and paste the tables back.

**The dev parse and publish** (expected runtimes: hsld26 15 to 25 min, hspolicy26 10 to 20, hspf26
15 to 30, openev 2 to 5; 45 to 80 minutes in all). Run one caselist at a time. Keep Activity Monitor
open on the `python` processes: if one grows past about 8 GB during the rebuild, stop it with
Ctrl-C and tell me the size.

```zsh
aws sso login --profile debate-dev-evidence
export DEBATE_ENV=dev
uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/parse-dev-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/parse-dev-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/parse-dev-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish > ~/parse-dev-openev.json; echo "exit $?"
```

Success looks like `exit 0` each time. `exit 1` with `PARSE_FAILURE_RATE_EXCEEDED` means more than
5% of the DOCX sources failed. The store and the publish are still complete; send me the counts
before raising the threshold. `PARSED_PUBLISH_INCOMPLETE` means something was not confirmed in the
bucket: run the same line again. Then paste back this, which prints counts only:

```zsh
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, sources, parsed, cards, unsupported, failed, failure_rate, store, elapsed_seconds, publish: .publish.counts}' ~/parse-dev-${c}.json; done
du -sh ~/.debate-research/dev/parsed
```

**The check that a second run parses and uploads nothing** (a few minutes each, mostly the rebuild):

```zsh
export DEBATE_ENV=dev
uv run debate-research --json caselist parse --caselist hsld26 --publish | jq -c '.data | {attempted, skipped, uploaded: .publish.counts.uploaded}'
uv run debate-research --json caselist parse --caselist openev --publish | jq -c '.data | {attempted, skipped, uploaded: .publish.counts.uploaded}'
uv run debate-research store ls parsed/hsld26/2026.09.20-docx-1/index.jsonl
```

Success looks like `attempted` 0, `skipped` equal to the sources, and `uploaded` 0 for both, and
`store ls` listing 1 object.

**A sample check** (about 10 minutes, by eye). Five random parsed sources from hsld26, each opened
in Word beside the cards the store holds for it. First, the five digests and their card counts:

```zsh
cd ~/.debate-research/dev/parsed/hsld26/2026.09.20-docx-1
jq -r 'select(.outcome == "PARSED" and .cards > 0) | "\(.source_sha256) \(.cards)"' index.jsonl | sort -R | head -5
```

Then, for each digest, copy it into `D` and run the block. It opens the file in Word and prints
the first five tags the store holds:

```zsh
D=paste-one-digest-here
cp -f ~/.debate-research/dev/blobs/sha256/${D:0:2}/${D:2:2}/${D} /tmp/parse-sample.docx
open /tmp/parse-sample.docx
sed -n 2p sha256/${D:0:2}/${D:2:2}/${D}.jsonl | jq -r '.document.cards[:5][] | "\(.completeness)  \(.tag)"'
```

For each file, check that the card count is roughly what the document holds and that the five tags
are its first five cards' tags. Record only tallies (looks right / doubtful / wrong). Then close
Word and run `rm -f /tmp/parse-sample.docx` and `cd -`. The file and the tags are real disclosures:
nothing from them goes into a message, an issue or a file.

**2. The prod publish**, from the same dev data directory, only after dev looks right (20 to 40
minutes; prod parses nothing and rebuilds and publishes):

```zsh
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research caselist parse --caselist hsld26 --dry-run
uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/parse-prod-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/parse-prod-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/parse-prod-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/parse-prod-openev.json; echo "exit $?"
uv run debate-research store ls parsed/hsld26/2026.09.20-docx-1/index.jsonl
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

`DEBATE_STORAGE__DATA_DIR` is the point of this block: without it the prod profile reads an empty
`~/.debate-research/prod` and publishes nothing. The dry run must show "To parse" 0 and "Skipped"
equal to the sources; if "To parse" is not 0, the data directory is wrong, so stop. Each publish
should exit 0 with `uploaded` equal to the dev publish's count for that caselist. Paste back the same
`jq` line with `parse-prod-` in place of `parse-dev-`. `unset` at the end matters: a shell left on
prod with the dev directory is how the next command would write to prod unchecked.

The JSON summaries hold counts, digests and keys, no names or paths. Keep them out of the
repository all the same. A later session records them in `docs/data/caselist-parse-report.md`.

## Follow-up work

1. **Short-card recall (E31, a spec change of its own).** See "Short-card recall". Three separate
   fixes, each a decision:
   * a candidate and confirmation step for short bodies, such as containment-oriented candidates
     from first and last shingles, or a length-aware threshold;
   * a linking rule that tolerates a split among the matching full cards, for example linking to
     the cluster of the longest match;
   * a link key among abbreviated disclosures themselves (short cite plus overlapping opening and
     closing words), for cards no team disclosed in full.
   
   The set in `short_cards.jsonl` is the regression set for whichever is chosen.
2. **The rebuild's cost (E31 or E32).** It is single-process, holds a caselist's cards in memory, is
   repeated on every run, and can go quadratic on near-copy-heavy input (57 s for one synthetic
   file). Caching each stored document's MinHash signatures, and clustering incrementally, would make
   a weekly run cost only its new cards. The operator run says whether this is needed now.
3. **The scheduled pull's parse stage (E34).** `caselist pull` has an optional `CaselistParseStage`
   that `v1-e34-t02` left for this task, and `debate-cli`'s dependency comment says t06 wires it.
   It is not wired here. It would change what the operator's installed weekly agent does each week,
   and this spec does not ask for that. Wiring it is a small adapter over
   `CaselistParseService.plan`/`run`; it should come after the first operator run shows the
   runtime.
4. **The removal runbook (`docs/runbooks/caselist-removal.md`).** It needs one step after a removal:
   `caselist parse --caselist <slug> --publish`, in dev and prod, to rebuild the aggregates the
   removal deleted. Not edited here, because the runbook is outside this task's packages.
5. **`caselist cards --parsed` reads ParsedCard or ParsedDocument JSONL, not this store.** E32 reads
   the store through `ParsedStore`. If `caselist cards` should read it too, it needs the manifests
   to put the paths back.
6. **The policy question in Deviation 1** (PM and Charlie): `parsed/` as a place personal data may
   live, or the path-free store as built.
7. **The garbled sentence in the spec's description** (Deviation 10), for the PM.
8. **`v1-e34-t04`**: when it merges, run `scripts/task sync` on any open E31 branch and re-run
   `test_the_full_archive_namespace_is_neither_parsed_nor_in_the_occurrence_table`. If its namespace
   is not one of the five planted shapes, add it to the test.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
