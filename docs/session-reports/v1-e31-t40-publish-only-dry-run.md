# Session report: v1-e31-t40-publish-only-dry-run

| | |
|---|---|
| Task | `v1-e31-t40-publish-only-dry-run` — caselist parse --publish-only has a dry run that lists what it would send and refuses what it would refuse |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t40-publish-only-dry-run.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t40-publish-only-dry-run.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t40-publish-only-dry-run` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research caselist parse --caselist <slug> --publish-only --dry-run` makes every check
`--publish-only` makes, in the same order, and is refused by each with the same code, message, hint,
details and exit code. It then lists what the publish would do with each object of the version
directory, in total and by kind (per-source files, aggregates, the placement state): `upload`,
`present` (in the bucket with the same digest), `suppressed` and `blocked`, each with a count and
bytes. It uploads nothing, takes no lock (it reads the lock and refuses what taking it would), and
writes nothing to either bucket or the data directory. Every test shows that, by object versions and
by every file's bytes and modification time. The plan is `ParsedStorePublisher.plan`, which decides
each object with the code the publish decides by. The cutover runbook's step 6 now runs the dry run
before each store's publish. Its check compares the plan with the copy's objects and bytes and
leaves a file the publish block requires. `--confirm-prod` stays on the real publish only. The
phase is `Succeeded`.

**Look at these first:**

1. **Making the dry run write nothing fixed a write the real `--publish-only` also made** (Decisions,
   first item). Building the parse service opened and migrated `debate.sqlite3` before any check
   ran, for a card placer that reads no database. The data-directory test caught it, and the
   container now asks for the placer only when a rebuild places cards.
2. **Deviation 1**: four files outside `constraints.packages` changed, because they pinned
   `--dry-run` as refused or described it so.
3. **`PARSED_PUBLISH_BLOCKED`**, a new code: a per-source file prod holds with other bytes fails the
   dry run, exit `1`, as `caselist publish --dry-run` fails `PUBLISH_BLOCKED`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `publish-only-dry-run` | Done | Core plan, CLI option, lock read, smoke check, runbook step 6 and guide. Red runs recorded before green; 21 of 21 mutants killed; 10 planted runbook breaks caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the dry run makes the publish's checks and lists its uploads and skips with counts and bytes while writing nothing, and the cutover runbook's step 6 runs it first, by tests on moto shown failing first | PASS | **Red 1, the code as of `ade970e`**, the three new test files committed alone (`673efd9`): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/test_caselist_parse_publish_only_dry_run.py packages/debate_cli/tests/test_caselist_parse_publish_only_dry_run.py packages/debate_cli/tests/bucket_mode/test_bucket_mode_publish_only_dry_run.py -q -p no:randomly --tb=line` → `18 failed, 3 passed, 1 error`. The error is the core file's import of the plan types, which did not exist yet. The CLI tests failed because `--dry-run` beside `--publish-only` was a usage error. The 3 that passed are "refused beside `--publish`, `--reparse`, `--snapshot`", which need no new code. **Red 2, a refuse-nothing skeleton** (the dry run plans the unchecked current directory and asks no guard): the CLI and bucket-mode files → 12 of their 21 tests failed. They were all 8 refusal cases, both lock refusals, the blocked case and the table. **Green:** the three files in one process (`-n 0 -p no:randomly`) → `27 passed`. Tests on moto (CLI, bucket mode) and on an on-disk store (core). See "What the tests hold" below |
| Node `publish-only-dry-run`: Publish-only dry run tests pass (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k publish_only`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k publish_only -q -p no:randomly` → `81 passed in 91.37s` |

### What the tests hold

* **Counts against the real publish that follows.** Core: over an empty bucket, the plan uploads 6
  per-source files, 3 aggregates and 1 placement state. Those counts are written by hand from the
  fixture's table: six sources through 09-08, no camp paths outside `openev`. Each object's bytes are
  measured on disk by the test. The publish that follows uploads exactly the planned keys. After a
  partial publish, the publish skips exactly the plan's `present` keys. A suppressed source is
  planned `suppressed` with its bytes. An aggregate the bucket holds differently is an `upload` that
  replaces it. CLI on moto: dev from an empty bucket, prod after dev, and a bucket missing two
  files. In each, the real `--publish-only`'s `uploaded`, `skipped`, `suppressed` and `failed`
  equal the dry run's `upload`, `present`, `suppressed` and `blocked`.
* **Each refusal alike.** One parametrized test per code: `PARSED_VERSION_DIRECTORY_MISSING`,
  `PARSED_AGGREGATES_MISSING` and `PARSED_SOURCE_FILES_MISSING` (the directory whole);
  `PARSED_BY_ANOTHER_PARSER_VERSION` and `PARSED_FINGERPRINT_VERSION_MISMATCH` (this build's
  versions); `PARSED_AGGREGATES_NAME_WHAT_THE_LIST_STOPS` for a removal and for a path hold only
  prod's list holds (the target's list); and `ENVIRONMENT_NOT_SYNCABLE`. In each, the dry run's
  `error` object equals the real run's, key for key, and the exit codes are equal. Neither writes.
  Also: `RUN_LOCK_HELD` in bucket mode while another runner holds the lease, and
  `BUCKET_KEEPS_RUN_STATE` in local mode on a seeded bucket, both alike. The occurrence table guard
  refuses the plan as it refuses the publish (core).
* **Nothing written.** Every version and delete marker of both versioned moto buckets, before and
  after. Every file and directory of the data directory, by bytes and modification time, after a
  `gc.collect()` so that an earlier in-process connection cannot checkpoint during the dry run. In
  bucket mode, every object's ETag and every version of the lock object, unchanged.
* **Text and `--json` the same.** Each table row's eight figures are parsed and compared with
  `--json`'s, for each kind and the total. The `--json` keys are pinned whole: `data`, `plan`,
  `by_kind`, `objects` and `bytes`.

### Mutation check (the write guard and the counts)

A scratch script, not committed. It applies one exact-string mutant at a time, runs the test files
that cover it under `hard_stop.py 115`, and restores the original bytes, checked by digest. The
worktree was clean after each batch. **21 of 21 killed**, each by an assertion, not a crash:

| # | Mutant | Result |
|---|---|---|
| 1 | The dry run publishes, then plans | killed (5 failed: versions changed) |
| 2 | The plan uploads each aggregate it plans | killed (3 failed) |
| 3 | The dry run takes the lock around the plan | killed (1 failed: a lock version added) |
| 4 | The dry run never reads the lock | killed (2 failed) |
| 5 | The lock read takes the lease in bucket mode | killed (1 failed) |
| 6 | The lock read skips local mode's seeded-bucket check | killed (1 failed) |
| 7 | The parse service opens the database at construction again | killed (8 failed: `debate.sqlite3-wal`/`-shm` written) |
| 8 | The dry run needs `--confirm-prod` | killed (3 failed) |
| 9 | The dry run's environment guard as a read's (`writing=False`) | killed (1 failed) |
| 10 | The plan skips the occurrence table guard | killed (1 failed) |
| 11 | `present` never recognised (shared with the publish) | killed (4 failed) |
| 12 | A suppressed file's bytes counted as 0 | killed (1 failed) |
| 13 | A suppressed source planned as an upload | killed (1 failed) |
| 14 | `count` ignores the kind | killed (5 failed) |
| 15 | `size` ignores the kind | killed (2 failed) |
| 16 | The placement state counted as an aggregate | killed (4 failed) |
| 17 | Aggregates planned though a source is blocked | killed (1 failed) |
| 18 | `--json`'s bytes are counts | killed (3 failed) |
| 19 | The table's Aggregates row gives the total | killed (1 failed) |
| 20 | `--json`'s totals are the per-source files' | killed (4 failed) |
| 21 | A blocked plan exits 0 | killed (1 failed) |

### The smoke check and the runbook's tests

* **Smoke** (`tests/smoke/test_caselist_parse.py`): `--dry-run` is out of the "refused beside
  `--publish-only`" loop. A new check runs both commands offline: the harness's empty AWS config
  defines no profile for the build's dev bucket. `--publish-only --dry-run` and `--publish-only`
  are refused with the same error, `STORE_PROFILE_NOT_CONFIGURED`, and the data directory is
  unchanged. **Red** with `caselist_parse.py` as of `ade970e` (restored after, bytes checked): `1
  failed`, the old `USAGE_ERROR`. **Green:** the file → `5 passed`.
* **Runbook** (`tests/docs/test_prod_publish_checks.py`). The step 6 heredoc `PUBLISHPLAN` is read
  out of the runbook and run on synthetic answers, as `PARSECHECK` and `COMPARE` are. It passes
  only when the plan's `upload`, `present` and `suppressed` together are the copy's objects and
  bytes at the restored version. It stops on a refusal, on an answer with no plan, and on any figure
  that differs. A stale OK file is removed. A block test checks that the dry run block comes
  straight before the publish block and carries no `--confirm-prod`. It also checks that the publish
  block refuses without the dry run's OK and uses it up after the publish. **Ten planted breaks in
  the runbook's text, each caught** (bytes not compared, `suppressed` not counted, version not
  checked, a stale OK kept, a refusal passing, a publish's answer passing, the publish without the
  OK, `--confirm-prod` on the dry run, the OK not used up). The first try missed one: a refusal
  passing was indistinguishable from the plan check, because a refused envelope has `data: null`.
  The two stops now say different things (`refused: <code>`, `the answer holds no plan; was it the
  dry run?`), and both are caught. `tests/docs/test_prod_publish_checks.py` → `46 passed`.

### Affected set and whole-repo checks

* `uv run scripts/affected_tests.py` chose **358 of 730** test files (49.0%, from 15 changed files).
  That is well past two minutes: v1-e31-t30's 205 files reached 76% at 115 s. So under agreement 10
  the whole set is the pull request's `ci`, with no operator hand-off. Within two minutes each, the
  changed modules' test directories and the always-run list:

| Command (each `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest … -q -p no:randomly -m "not slow and not live"`) | Result |
|---|---|
| `tests/architecture tests/specs tests/docs tests/smoke/test_caselist_parse.py packages/debate_cli/tests/*.py` (the always-run list is among these) | `1591 passed in 74.98s` |
| `packages/debate_core/tests/application/*.py` | `3520 passed, 7 skipped in 52.38s` |
| `packages/debate_core/tests/application/caselist`, whole | stopped at its 115-second limit (load 12 to 16) |
| the same directory's first 56 test files | `1129 passed in 66.92s` |
| the same directory's other 55 | `778 passed in 80.87s` |
| `packages/debate_cli/tests/bucket_mode`, whole, then its first 8 files | each stopped at its 115-second limit (load 13 to 25) |
| `bucket_mode` files 1 to 4 / 5 to 8 / 9 to 12 / 13 to 17 | `59 passed in 58.60s` / `97 passed in 79.54s` / `15 passed in 18.13s` / `107 passed in 66.13s` |
| The neighbours, earlier: both publish-only files, `test_caselist_parse.py` (CLI and core), `test_caselist_parse_newer_fingerprint_table.py`, `test_bucket_mode_lock.py`, `test_publish_verify_parse_pull_panels.py`, `test_occurrence_table_guard.py` | `263 passed in 55.81s` |

| Check | Result |
|---|---|
| `uv run --frozen ruff format --check packages/debate_core packages/debate_cli tests/smoke tests/docs` | `1136 files already formatted` |
| `uv run --frozen ruff check` (same paths) | `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen pyright tests/docs/test_prod_publish_checks.py tests/smoke/test_caselist_parse.py` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 73 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 655 files, 41 epics, 592 tasks, 22 releases` |
| `uv run scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 696 shell code blocks in 255 Markdown files (1 session reports changed since origin/dev)` |
| `uv run scripts/check_links.py` | `OK: 3723 relative links and anchors in 630 Markdown files` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 69 indexed documents under docs/ have a description` |

`origin/dev` moved by one merge while I worked (v1-e30-t34, #864). It changes `container.py` too,
about 850 lines from my hunk, and none of my other files. The spec differs from dev's only in its
phase. I have not synced; `scripts/task` does that.

## Files changed

* **`packages/debate_core/src/debate_core/application/caselist/parsed_publish.py`**: the plan
  types (`ParsedObjectKind`, `PlannedAction`, `PlannedObject`, `ParsedPublishPlan`) and
  `ParsedStorePublisher.plan`. `publish` and `plan` now share what comes before the first object
  (`_directory`: the list, held uploads, both listings, the occurrence table guard) and the
  per-object decision (`_compared`, `_action`). The publish's behaviour is unchanged: t30's two test files
  and the neighbours above pass.
* **`packages/debate_core/src/debate_core/application/caselist/run_lock.py`**:
  `BucketWriteGuard.refuse_what_holding_would_refuse`, the read-only twin of `held`. In bucket mode
  it is `BucketRunLock.check()` (take's rules, nothing written); in local mode, ruling 3(a)'s
  seeded-bucket read.
* **`packages/debate_cli/src/debate_cli/commands/caselist_parse.py`**: `--dry-run` is no longer
  refused beside `--publish-only`. `_publish_only_dry_run`, `publish_only_plan_summary` (the
  `--json`), `_plan_failure` (`PARSED_PUBLISH_BLOCKED`), the table, and the module docstring. Its
  missing `--failures` heading is restored too. `_not_confirmed`'s body moved to `_named_objects`,
  which both failures use.
* **`packages/debate_cli/src/debate_cli/container.py`**: the parse service's card placer factory is
  `lambda: self.caselist_card_stats().placer()`, so the SQLite file is opened at a rebuild's placing
  and not when the service is built.
* **Tests:** `packages/debate_core/tests/application/test_caselist_parse_publish_only_dry_run.py`
  (6), `packages/debate_cli/tests/test_caselist_parse_publish_only_dry_run.py` (18),
  `packages/debate_cli/tests/bucket_mode/test_bucket_mode_publish_only_dry_run.py` (3). In
  `test_caselist_parse_publish_only.py`, the "refused beside" case for `--dry-run` is removed, and
  the docstring says why.
* **`docs/runbooks/caselist-cutover.md`**, step 6: two blocks per store, the dry run with its
  `PUBLISHPLAN` check, then the publish, which requires the check's `parsed-planned-<store>.txt` and
  uses it up. New success lines and stops.
* **Outside `constraints.packages` (Deviation 1):** `tests/smoke/test_caselist_parse.py`,
  `tests/smoke/README.md`, `tests/docs/test_prod_publish_checks.py`,
  `docs/guides/parsed-store-publish-only.md`.
* **The task spec:** phase `Succeeded`.

## Deviations from the spec

1. **Four files outside `constraints.packages` changed.** Each pinned or described `--dry-run` as
   refused beside `--publish-only`, which this task undoes:
   * `tests/smoke/test_caselist_parse.py` refused it in its option loop, and `plan_specs/README.md`
     asks a CLI surface change to carry its smoke check. Its README row says so.
   * `tests/docs/test_prod_publish_checks.py` required every runbook block holding
     `--publish-only` to carry `--confirm-prod`. The step 6 dry run must not, by the task's own
     instruction. The brief also asked for `tests/docs` to keep passing, and its new heredoc is
     tested where the other step checks are.
   * `docs/guides/parsed-store-publish-only.md` listed `--dry-run` among the refused options. It now
     has a section on the dry run, and its second-environment example runs the dry run first.

   Suggested spec line, if the PM agrees: add `tests/smoke`, `tests/docs` and `docs/guides` to
   `constraints.packages`, with a comment such as `# PM ruling: the option this task frees was
   pinned refused in the smoke check, the runbook's tests and the guide.`

## Decisions and assumptions

* **The SQLite open, and a change to the real `--publish-only`.** `caselist_parse(with_bucket=True)`
  built a `CaselistCardStatsService` over `SqliteDatabase.open` at construction, only to hand over
  its bound `placer`. That opened and migrated `debate.sqlite3`, writing its `-wal` and `-shm`,
  before `publishable_version` asked anything. `CardPlacer` reads thresholds and markers, no
  database. The factory is now a lambda, so the database is opened at the first rebuild's placing,
  as it was before for every rebuild. As a result, `--publish-only` (real and dry run) and the
  `--failures` listing no longer open the database. The rebuild's tests pass unchanged: core
  `test_caselist_parse.py`, `application/caselist`, and every bucket-mode pull.
* **The environment guard is a publish's** (`no_bucket(writing=True)`), unlike `caselist publish
  --dry-run`, which uses a read's. The brief asked for "refusing exactly as it would", so a `test`
  environment is `ENVIRONMENT_NOT_SYNCABLE` for both. Only `--confirm-prod` is the real run's, as the
  brief asked.
* **The lock is read, never taken.** The real `--publish-only` holds the lock while it writes. The
  dry run asks `refuse_what_holding_would_refuse` after the directory's checks, at the point where
  the real run takes the lock. `RUN_LOCK_HELD` (bucket mode) and `BUCKET_KEEPS_RUN_STATE` (local
  mode) are tested alike. The other refusals of taking it (a bucket never seeded, a run home moved)
  come from take's own rules, which `check()` applies, and from the same `refuse_a_seeded_bucket` in
  local mode; they are not tested here. `bucket_lock.py`'s "a dry run takes nothing" still holds.
* **The occurrence table guard is the publisher's**, asked inside `plan` before any object, as in
  `publish`. A newer table in the bucket is downloaded into a temporary directory to read its stamps,
  as the publish does, never into the data directory.
* **`PARSED_PUBLISH_BLOCKED`.** A plan with a `blocked` object is the publish's
  `PARSED_PUBLISH_INCOMPLETE` foretold. The dry run prints the plan, then fails with this code. The
  exit code comes from `exit_code_for_failure_codes`: `1` on a checksum mismatch, `3` when every
  blocked object is one a store did not answer for. `--json` puts the whole plan in `details`, as
  the other failures do. A blocked per-source file withholds the aggregates in the publish, so the
  plan lists none (mutant 17).
* **Kinds.** The placement state is its own kind, as the brief named it. `camp_paths.jsonl`
  (`openev` only) counts among the aggregates. Bytes are this machine's sizes: equal digests mean
  equal sizes for `present`, and a suppressed file is headed locally for its size. The publish
  never heads a suppressed file, and that is a local read.
* **`--json` shape.** `plan.objects` and `plan.bytes` are the totals, and `plan.by_kind` gives the
  same per kind. Each is keyed by `upload`, `present`, `suppressed` and `blocked`. Every key is new
  (no existing JSON shape changed), and pinned whole by `test_the_dry_runs_json_keys_are_pinned_whole`.
* **Runbook step 6.** The dry run block reads the plan against the copy's directory. `upload`,
  `present` and `suppressed` together must be the copy's file count and bytes. This is stricter than
  the old success line ("`uploaded` plus `skipped` equal to the copy's count"), which left out
  suppressed files. The check writes `parsed-planned-<store>.txt` only on a match. The publish block
  requires that file and deletes it after the publish, so a retry always starts from a new dry run
  and its plan. The publish's success line asks for `uploaded` equal to the dry run's `upload`. The
  dry run's runtime is written as an estimate, "about a minute, not yet measured".

## Operator follow-ups

None. The first real use is v1-e40-t16's prod session (its ac2), whose step 6 now runs the dry run
before each store's publish. That session will measure the dry run's runtime.

## Follow-up work

1. **The two largest test directories no longer fit one 115-second run on this Mac under load.**
   `packages/debate_core/tests/application/caselist` and `packages/debate_cli/tests/bucket_mode`
   were each stopped at the limit at loads of 12 to 25, and needed two and four runs. This is for
   information only: CI's parts are dealt by duration and are not affected.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
