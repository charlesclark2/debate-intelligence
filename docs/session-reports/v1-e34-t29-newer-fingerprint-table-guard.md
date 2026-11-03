# Session report: v1-e34-t29-newer-fingerprint-table-guard

| | |
|---|---|
| Task | `v1-e34-t29-newer-fingerprint-table-guard` — An older build never rewrites or publishes an occurrence table stamped with a newer fingerprint version |
| Spec | [`plan_specs/v1/e34-caselist-sync/t29-newer-fingerprint-table-guard.yaml`](../../plan_specs/v1/e34-caselist-sync/t29-newer-fingerprint-table-guard.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t29-newer-fingerprint-table-guard` |
| Session status | COMPLETE |

## Summary

Three code paths write or move an occurrence table: the parse pipeline's rebuild, the parsed
store's publish, and `store sync`. Each now asks one rule,
`occurrence_table_guard.refuse_newer_table`, before it writes anything. The rule refuses when the
table's stamp is newer than the build's own, judged by version number. The refusal is
`NewerFingerprintTable` (`NEWER_FINGERPRINT_TABLE`), and it names both versions and the store. An
equal or older stamp is rebuilt and published exactly as before; one test checks that byte for
byte against a store with no prior table.

Every path the PM asked about is listed under "Every path that writes or moves an occurrence
table" below:

* The weekly run's parse stage and `caselist parse` by hand both run the guarded rebuild.
* `caselist parse --publish` runs the guarded publish.
* `caselist publish` touches no table.
* `store sync` moves `parsed/` as named objects, and is now guarded.

Tests that patch the rule's comparison fail if any path decides for itself, and an AST inventory
fails when a new caller writes the aggregates.

Two things to look at first:

* **The new store method (Deviation 1).** `read_occurrence_stamps` lives in
  `integrations.local` and `testing`, outside the spec's packages.
* **The order (Deviation 2).** `EXACT_FINGERPRINT_VERSIONS` is a set, so the rule orders stamps
  by their version number.

Synced onto `dev` at `2e6a7b2`, after v1-e39-t09 merged (#376). t09's stage list and run details
are taken as they are, and `search_index_refresh.py` is untouched. All three criteria pass, so the
Goal is `Succeeded`.

## Every path that writes or moves an occurrence table

The PM's list first, found from the code: `write_aggregates` callers, `ParsedStorePublisher` users,
every user of `AGGREGATE_NAMES` and `OCCURRENCES_NAME`, and `store sync`'s keyspaces.

| Path | Entry points | What it does to a table | Guarded | Asks the rule about |
|---|---|---|---|---|
| `CaselistParseService.run` (`caselist_parse.py`) | The weekly run's parse stage (`PullParseStage.parse_new_sources`); `caselist parse`, with and without `--publish` | Rebuilds `occurrences.jsonl` of the version directory it writes | Yes, first thing in `run`, before any per-source write | The table it would replace as the caselist's current one: its own directory's, or, for a new directory (`--reparse`, a profile or parser bump), the one it supersedes |
| `ParsedStorePublisher.publish` (`caselist/parsed_publish.py`) | The parse stage's publish (`PullParseStage.publish`); `caselist parse --publish` | Uploads the local table, replacing the bucket's | Yes, after listing and before the first upload | The local table it sends, and the bucket's when the bucket holds other bytes (downloaded only then) |
| `EvidenceSyncService` `_move` (`evidence_sync.py`) | `store sync --push` and `--pull`. The `objects` keyspace is rooted at `<data_dir>/objects/`, and `parsed/` is one of `EVIDENCE_PREFIXES`, so a pull copies the bucket's `parsed/` there and a push sends that copy back | Overwrites a `changed` named object, `parsed/<c>/<v>/occurrences.jsonl` included | Yes, per object, before it moves | Push: its own copy, and the bucket's when `changed`. Pull: this machine's copy when `changed` |
| `caselist publish` (`publish_service.py`) | `caselist publish`, the run's publish stage | None: manifests and raw blobs only | Not needed | — |
| `caselist remove` (`removal_plan.py`, `removal_residue.py`) | `caselist remove`, residue clearing | Deletes the aggregates of the caselists a removal touches | No, deliberately | A deletion puts no clusters back, and a removal must never be refused |
| Search index build and refresh (`search_index_build.py`, `search_index_refresh.py`, `tub index`) | `tub index build/publish`, t09's index stage | Reads the table; writes an index, never a table | Not this task's | t09's ac3 skips a store whose fingerprint version differs (PM: stay out) |
| `file_recipes.py`, `caselist_card_stats.py`, `scripts/compare_card_clusters.py` | `caselist cards`, recipes, the clusters comparison | Read only | Not needed | — |

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `fingerprint-guard` | Done | The rule, its three callers, the hint in the weekly run, the runbook, and the ac2 amendment. Red run against a refuse-nothing skeleton, then green, then 22 mutants |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** A rebuild or publish over a newer-stamped table is refused with both versions named, by tests for the parse stage and the publish stage shown failing first | PASS | **Red** (commit "red run, the paths wired to a refuse-nothing skeleton", `c70e654`), the five new test files at `-n 0`: `24 failed, 35 passed in 7.73s`. **Green** (commit "the one rule refuses…", `2ea4b18`): `59 passed in 7.29s`; on the final tree `60 passed in 7.26s`. Parse stage: `test_a_rebuild_over_a_table_a_newer_build_stamped_is_refused_and_writes_nothing` (directory byte for byte, parser asked nothing, message names `synthetic-fingerprint-v8`, `synthetic-fingerprint-v7` and "this machine's parsed store"), `test_a_reparse_never_supersedes_…`, and the weekly run's `test_a_pull_over_a_table_a_newer_build_stamped_fails_the_parse_stage_and_leaves_it`. Publish stage: `test_a_publish_of_a_table_a_newer_build_stamped_…`, `test_a_publish_over_the_buckets_table_…` (bucket byte for byte, no PutObject), the weekly run's `test_a_pull_whose_bucket_holds_a_table_…`, and the CLI's three `caselist parse` tests (exit 1, `NEWER_FINGERPRINT_TABLE`) |
| **ac2** (amended, PM ruling 2026-10-20) An equal or older stamp rebuilds as before, by test; a refusal appears in the run summary and the failure notification (v1-e34-t03), naming both versions and the store, by test | PASS | `test_an_equal_or_older_table_is_rebuilt_exactly_as_a_build_with_no_table_builds_it[v7, v6]`: the rebuilt `occurrences.jsonl` equals, byte for byte, the one a fresh store at the same build writes. Also the reparse, publish, weekly-run, CLI and store-sync equal-or-older cases, all of which passed against the skeleton too. Run summary: the parse stage's `reason` ends `testcl26: the occurrence table of testcl26 2026.10.20-docx-6 in this machine's parsed store is stamped synthetic-fingerprint-v8, newer than this build's synthetic-fingerprint-v7; it was left as it was; …`. Notification: `caselist pull finished with a failed stage`, message `… the parse stage failed on NEWER_FINGERPRINT_TABLE …`, hint naming both versions and the store, fix `PARSE_COMMAND` (`test_pull_refuses_a_newer_fingerprint_table.py`) |
| **ac3** An earlier build (the agent's at the time) reads every file this build writes, by the cross-build check | PASS | Agent build `v1.1.0-dev.64` (`cd69a3d`; the agent "runs `1.1.0.dev64`", `docs/data/caselist-parse-report.md`, and t09 leaves the next reinstall pending). **Run files:** `write_newer_fingerprint_table_files.py` writes three scenarios (refused here, refused in the bucket, older rebuilt), and `read_sync_run_files.py` reads them with this build, `dev` at `2e6a7b2` and the agent build: each exit 0, `refused or skipped: 0`, output identical past the reader line, including the refused stage's reason and its details' code and hint. **Parsed store:** `check_an_older_build_reads_this_builds_parsed_store.py`, written by this build and read by the agent build: exit 0; `read 2026.10.20-docx-6: 7 per-source files, 4 documents, 6 index rows, 3 failure rows, 5 occurrence rows`; `publish …: succeeded True, uploaded 9`; `parse: wrote 2026.10.18-docx-5 (new)`. Commands under "Cross-build check" |
| Node: `uv run pytest packages/debate_core/tests/application -k "parse or publish or fingerprint"` | PASS | `612 passed in 18.74s` on the final tree (run as `.venv/bin/python -m pytest …` under `perl -e 'alarm 115; exec @ARGV'`) |
| Forbidden: changing the fingerprint or clustering rules | PASS | `debate_core/evidence/` and `caselist_card_stats.py` untouched (`git diff 2e6a7b2 --stat`) |
| Forbidden: a path, school, team code or file name in a record or a log | PASS | The refusal names a caselist slug, a version directory, a store by role and two versions. The guard logs nothing. `caselist_sync`'s existing no-path scrub still applies to the sentence |
| Forbidden: network or AWS access in any test | PASS | moto and the filesystem only, as the suites they extend |
| ruff, pyright, lint-imports, specs, docs | PASS | `ruff format --check packages tests scripts`: 746 files already formatted. `ruff check`: all passed. `pyright packages/debate_core packages/debate_cli`: 0 errors. `lint-imports`: 12 kept, 0 broken. `validate_specs.py`: `OK: 396 files, 39 epics, 336 tasks, 21 releases`. `check_command_blocks.py --base origin/dev`: 335 blocks in 131 files, no `#`. `check_links.py`: 1924 links and anchors OK |
| Affected set (working agreement 10) | Left to CI | `affected_tests.py` chose 295 of 359 test files (82%; `testing/fakes.py` is imported by the root conftest), which is most of the six-minute selection. Run instead, under the two minutes: the always-run list, the docs tests, the test files of every changed module (parse, publish, pull parse stage, stage failure codes, run records, removal, store sync, local store, t09's index stage and build, the CLI's parse), and the new files: `884 passed in 22.89s` |

### The red run

Against the skeleton, `is_newer_fingerprint_version` returned `False`, `newer_stamp` returned
`None`, and `refuse_newer_table` did nothing. The wiring was in place. The failures by `E` line:

| Count | `E` line | Tests |
|---|---|---|
| 7 | `DID NOT RAISE NewerFingerprintTable` | parse, reparse, publish (two), the two bypass tests at service level, the rule's refusal |
| 3 | `assert 0 == <ExitCode.DOMAIN_FAILURE: 1>` | the CLI's three |
| 3 | `not enough values to unpack (expected 1, got 0)` | store sync: no failed object, push (two) and pull |
| 3 | `assert False` | an unorderable stamp counts as newer (three params) |
| 2 | `assert False is True` | `v8` and `v10` are newer than `v7` |
| 1 | `assert None == 'synthetic-fingerprint-v12'` | the newest of several is named |
| 1 | `assert set() == {'debate_core…ble_guard.py'}` | the inventory: the skeleton's `newer_stamp` called no comparison |
| 1 | `{… (True, None)} == {… 'NEWER_FINGERPRINT_TABLE')}` | store sync takes the rule's answer |
| 1 | `[] == ['NEWER_FINGERPRINT_TABLE']` | the weekly stage takes the rule's answer |
| 1 | `('completed', []) == ('failed', [… 'NEWER_FINGERPRINT_TABLE'])` | the weekly run over this machine's table |
| 1 | `('failed', ['CHECKSUM_MISMATCH']) == ('failed', ['NEWER_FINGERPRINT_TABLE'])` | the weekly run over the bucket's table (see below) |

The 35 that passed are the cases that must not refuse:

* equal and older stamps, in every path;
* stamp reading, key naming, and the real-versions order test;
* the `write_aggregates` inventory.

One finding from the red: with no guard, the two-machine bucket case already failed the stage,
but on `CHECKSUM_MISMATCH`, not on the table. The two machines' per-source records carry their
own fingerprint stamps, so their per-source files differ, and the publisher withholds the
aggregates. That protects the table only by accident: a newer machine that never published the
per-source files, or a `store sync --push`, has no such luck.

### Mutation (working agreement 10, about 20, on the rule and its callers)

22 mutants, one run of the five new test files each (`-x -n 0`), restored from byte copies. 21
killed, 1 survived:

* **The rule** (`occurrence_table_guard.py`):
  * equal refused;
  * `>` to `<`;
  * numbers compared as text;
  * family ignored;
  * an unorderable stamp treated as older;
  * `max` to `min`;
  * a bad line stops the read;
  * versions swapped in the message.

  All killed.
* **`>` to `>=`: survived, equivalent.** Same family and same canonical number (`[1-9][0-9]*`)
  is the same string, which the `stamped == build` check has already returned on.
* **Parse:**
  * guard removed;
  * guard moved after the per-source writes;
  * superseded directory unchecked;
  * the local store reads no stamps.

  All killed.
* **Publish:**
  * guard removed;
  * guard moved after the per-source uploads;
  * local table unchecked;
  * bucket table never downloaded;
  * a directory with no table not skipped.

  All killed. The last was killed by a test added after coverage showed the line unreached.
* **Store sync:**
  * guard removed;
  * pull unchecked;
  * bucket unchecked.

  All killed.
* **Weekly run:** `fix_for` without the hint. Killed.

**Coverage of the new lines:**

* `occurrence_table_guard.py`: 100%.
* The new methods in `caselist_parse`, `evidence_sync` and the local store: fully covered.
* `ParsedStorePublisher._refuse_a_newer_table`: covered except the `NotFound` on a head between
  the listing and the head, a race no test stages.

### Cross-build check

Where: this worktree, with `S` the session's scratchpad. The agent build and `dev` were extracted
with `git archive v1.1.0-dev.64` and `git archive 2e6a7b2`
(`packages/debate_core/src packages/debate_cli/src`).

```bash
WRITE_NEWER_FINGERPRINT_TABLE_FILES="${S}/files/this-build" .venv/bin/python -m pytest packages/debate_core/tests/application/caselist/write_newer_fingerprint_table_files.py -p no:cacheprovider --no-cov -n 0 -q
.venv/bin/python -I packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" this-build
(export PYTHONPATH="${S}/start/packages/debate_core/src"; .venv/bin/python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" start-commit)
(export PYTHONPATH="${S}/agent/packages/debate_core/src"; .venv/bin/python packages/debate_core/tests/application/caselist/read_sync_run_files.py "${S}/files/this-build" agent-build)
```

All three readers exit 0, and the three outputs agree past the first line. The agent build's
output, in part:

```text
refused_here:
  record 20260916T060000Z: incomplete; select completed, download completed, import completed, publish completed, parse failed, search_index skipped, landscape skipped, report completed, retention completed
    parse reason: 0 caselist(s) parsed: … testcl26: the occurrence table of testcl26 2026.10.20-docx-6 in this machine's parsed store is stamped synthetic-fingerprint-v8, newer than this build's synthetic-fingerprint-v7; it was left as it was; the parsed store of testcl26 is not published
  details 20260916T060000Z: read, failure_codes [], 1 stage(s)
    parse error_codes ['NEWER_FINGERPRINT_TABLE']; hint: The occurrence table of testcl26 2026.10.20-docx-6 in this machine's parsed store is stamped synthetic-fingerprint-v8, and this build's fingerprint version is synthetic-fingerprint-v7. Rebuild and publish it with a build at synthetic-fingerprint-v8 or later, and install that build for the weekly agent. …
  bucket reports/sync-run-details/2026/20260916T060000Z.json: read as SyncRunDetails
  bucket reports/sync-runs/2026/20260916T060000Z.json: read as SyncRunRecord
refused_in_the_bucket: … in the bucket is stamped synthetic-fingerprint-v8 … (same shape)
refused or skipped: 0
```

The parsed store:

```bash
(export CHECK_PARSED_STORE=write CHECK_PARSED_STORE_DIR="${S}/parsed-store"; .venv/bin/python -m pytest packages/debate_core/tests/application/check_an_older_build_reads_this_builds_parsed_store.py -p no:cacheprovider --no-cov -n 0 -q -s)
(export CHECK_PARSED_STORE=read CHECK_PARSED_STORE_DIR="${S}/parsed-store" PYTHONPATH="${S}/agent/packages/debate_core/src"; .venv/bin/python -m pytest packages/debate_core/tests/application/check_an_older_build_reads_this_builds_parsed_store.py -p no:cacheprovider --no-cov -n 0 -q -s)
```

Both exit 0. The reader line names the agent source and `parser 2026.10.18-docx-5`, and its read,
publish and parse lines are quoted under ac3.

## Files changed

* **`debate_core.application.caselist.occurrence_table_guard`** (new): the rule, the order, the
  error and its hint, and the raw stamp reader.
* **`debate_core.application.caselist_parse`**: `run` asks the rule first; docstring section "A
  table a newer build stamped".
* **`debate_core.application.caselist.parsed_publish`**: the publish asks the rule of its own
  table and of the bucket's before the first upload; docstring.
* **`debate_core.application.evidence_sync`**: `_move` asks the rule for a `parsed/` occurrence
  table; docstring.
* **`debate_core.application.caselist_sync`**: `fix_for` gives a refusal its own hint; the parse
  stage's docstring names `NEWER_FINGERPRINT_TABLE`. No change to the stage list or run details.
* **`debate_core.application.ports.parsed_store`**: `ParsedStore.read_occurrence_stamps`.
* **`debate_core.integrations.local.parsed_store`** and **`debate_core.testing.fakes`**: its two
  implementations (Deviation 1).
* **Tests:**
  * `caselist/test_occurrence_table_guard.py` (the rule, the order on synthetic versions, one
    real-versions test, the call inventory);
  * `test_caselist_parse_newer_fingerprint_table.py` (parse and publish);
  * `caselist/test_pull_refuses_a_newer_fingerprint_table.py` (the weekly run, summary and
    notification);
  * `test_store_sync_newer_fingerprint_table.py`;
  * the CLI's `test_caselist_parse_newer_fingerprint_table.py`;
  * the cross-build writer `caselist/write_newer_fingerprint_table_files.py`, and
    `read_sync_run_files.py`, which now prints a refused stage's reason and hint.
* **`docs/runbooks/caselist-scheduled-sync.md`**: `NEWER_FINGERPRINT_TABLE` among the parse
  stage's codes, and what to do about it.
* **The spec**: ac2 amended with the PM's ruling as a comment, and the Goal set to `Succeeded`.

## Deviations from the spec

1. **A store method outside the spec's packages.** `ParsedStore.read_occurrence_stamps` is new on
   the port (in scope). Its implementations are in `debate_core.integrations.local.parsed_store`
   (7 lines) and `debate_core.testing.fakes` (3 lines), which `constraints.packages` does not
   list.

   Why it is needed: the parse path can read a table only through the port, and
   `read_occurrences` validates every row with a model that forbids unknown fields. So a table
   whose newer build added a field, the case this task exists for, would fail as an unmodelled
   `UnreadableParsedStore` (`INTERNAL_ERROR`). It would never become a refusal naming the
   versions.

   The new method reads each row's `fingerprint_version` from its JSON alone, through the
   guard's shared reader, which the publisher and store sync use too. I did not amend the
   packages list; the PM may.
2. **"By `EXACT_FINGERPRINT_VERSIONS` order"**: the list is a `frozenset`, with no order. It also
   loses its older members when the normalization changes, so a build after such a bump could
   not place an older stamp by membership at all.

   The rule orders `<family>-v<N>` by `N`, which is the order the set's members were added in. A
   stamp of another family, or with no canonical number, cannot be ordered and is treated as
   newer (refused), because the build cannot vouch that its rules are not older.

   `test_every_version_the_real_list_names_orders_at_or_below_the_real_build` holds the order to
   the real list. Every other test uses `synthetic-fingerprint-v6/7/8`, as the PM asked.

## Decisions and assumptions

* **The superseded table counts.** A `--reparse` or profile bump by an older build would make a
  new generation the caselist's current table, which is a rewrite by another route. So the
  rebuild asks the rule of the directory it supersedes too.

  This includes a parser-version bump over a newer-fingerprint directory: refused, because that
  build's clusters are the older ones. The agent at `docx-5` writing its own directory beside a
  newer one is unaffected; its superseded directory is the newest one below its own.
* **Refused before anything is written.** The parse refuses before the first per-source file, and
  the publish refuses before the first upload. Store sync refuses the one object before it moves,
  and the rest of the sync goes on, as for any failed object. Mutants that move the check later
  are killed.
* **What each direction asks about.** A publish or a push asks of the table it sends and the one
  it overwrites. A pull asks only of the copy it overwrites. It publishes nothing, so a newer
  table in the bucket still comes down into `objects/parsed/`, which no reader opens.
* **`--dry-run` is not refused.** It writes nothing. The real run that follows is.
* **The bucket's table is downloaded only when its bytes differ** from the local table's (one
  head of each). A weekly publish after new sources therefore downloads one table per caselist.
  At the largest measured table, 239,055 rows, that is roughly 130 MB. A refusal that fails a
  weekly stage costs that download; an equal stamp is then uploaded as before.
* **A line with no readable stamp is passed over.** It cannot name a newer version, and a table
  with no stamped row (or none at all) has nothing to protect.
* **The hint** comes from the error (`NewerFingerprintTable.fix`) through `fix_for`, by type, as
  the other refusals' hints do. The stage's `_UNPUBLISHED_PARSED_STORE_FIX` follows it, unchanged.
* **Coordination with v1-e39-t09:** worked on `dev` at `ec45409`, then synced with
  `scripts/task sync` once #376 merged (clean rebase). Its stage list and run details are taken
  as they are. `search_index_refresh.py` and `sync_runs.py` are untouched; `caselist_sync.py`
  changed only in `fix_for` and a docstring.

## Operator follow-ups

None. The affected set is the pull request's `ci` check (agreement 10).

## Follow-up work

1. **`store sync` moves `parsed/` at all** (E29 or E34). Its `objects` keyspace treats bucket
   `parsed/` as named objects under `<data_dir>/objects/parsed/`, a copy no reader uses. A push
   from a machine that pulled earlier overwrites any per-source file or aggregate that changed
   since. The table is guarded now; the index, failures and per-source files are not.

   Skipping `parsed/` in store sync, since `caselist parse --publish` is its publisher, may be
   the simpler rule. That is the PM's call.
2. **The per-source records' own stamp** decides nothing (`ports/parsed_store.py`). It still makes
   two machines at different fingerprint versions write different per-source files for the same
   bytes. Their publishes then meet as `CHECKSUM_MISMATCH` (seen in the red run). Worth one line
   in the parsed-store layout doc, or a decision about that stamp.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-21

**Notes:**

Accepted. One edit in this session before the pull request: amend the spec's packages (question 1
below). The pull request then opens with no `--partial`.

**What is good:**

* **The path list is found from the code,** not from my notes: `write_aggregates` callers,
  `AGGREGATE_NAMES` and `OCCURRENCES_NAME` users, and `store sync`'s keyspaces. It also says why
  `caselist remove` is deliberately unguarded: a removal must never be refused.
* **One rule, with tests that fail if a path decides for itself,** and an AST inventory for future
  callers. This is the `stored_row_hold` pattern again, as asked.
* **The red run taught something real:** without the guard, the two-machine bucket case failed on
  `CHECKSUM_MISMATCH`, which protects the table only by accident. That is the best argument for
  this task.
* **Counting the superseded table** (a `--reparse` or parser bump by an older build) closes the
  route around the rule that I had not named.
* **The cross-build check uses the agent's actual build** (`v1.1.0-dev.64`), with run files and a
  parsed store read back.

**Rulings:**

1. **Deviation 1: accepted.** Add `debate_core.integrations` and `debate_core.testing` to
   `constraints.packages`, with a comment `PM ruling 2026-10-21 (v1-e34-t29 review)`. Run
   `validate_specs.py` and commit. Reading the stamp from raw JSON is what makes a newer build's
   table a refusal by name rather than an `INTERNAL_ERROR`.
2. **Deviation 2: accepted.** A `frozenset` has no order, and ordering by `N` within a family,
   with anything unorderable treated as newer, is the safe reading. The one real-versions test is
   the right tie.
3. **Follow-up 1: a small p2 task in E29**, which owns `store sync`: stop moving `parsed/`, since
   `caselist parse --publish` is its only publisher. Follow-up 2 (the per-source stamp) goes into
   the same task as a line in the parsed-store layout doc. The PM files it in the next batch.

**Noted, no change:** a weekly publish after new sources downloads the bucket's table when its
bytes differ, up to about 130 MB per caselist. That is acceptable at weekly cadence. If it ever
matters, a ranged read of the first stamped row would do.

**Note for the operator's re-parse to `docx-6` today:** the fingerprint stays `card-fingerprint-v4`,
so the guard sees an equal stamp and refuses nothing, whether or not this has merged first.
