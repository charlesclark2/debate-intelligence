# Session report: v1-e40-t34-openev-metadata-reimport-in-bucket-mode

| | |
|---|---|
| Task | `v1-e40-t34-openev-metadata-reimport-in-bucket-mode` — The OpenEv metadata re-import runs in bucket mode, so a camp table change reaches dev's records |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t34-openev-metadata-reimport-in-bucket-mode.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t34-openev-metadata-reimport-in-bucket-mode.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t34-openev-metadata-reimport-in-bucket-mode` |
| Session status | PARTIAL: everything a session can close is done; ac2 is the operator's run after the merge, so the Goal stays InProgress <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`caselist reimport-openev-metadata` now has a bucket-mode form. In dev, where the run state is in the
bucket since the cutover, it is a dry run unless `--execute`. The dry run restores the bucket's run
state into the working copy, as `caselist remove`'s dry run does, re-derives with nothing written, and
prints camps by name with their counts before and after. It takes no lock and writes nothing to the
bucket. `--execute` holds the run lock from the restore to the end. It restores, re-derives, refuses a
bundle changed since its restore, publishes the release manifest and saves the run-state bundle. Both
refuse the no-import window (every Wednesday included), a moved home and an unseeded bucket, and prod
needs `--confirm-prod`. The logic is a new `debate_core` service; the CLI only routes and renders.
18 new tests and 3 new lock-suite cases were shown failing against a refuse-nothing skeleton (19
failed, every one at an assertion). All 6 of the PM's mutants, and 3 more, were caught. The runbook
(caselist-cloud-run.md, "A camp table change") has the operator's dry run, the counts the PM reads,
the run and a check. **The Goal stays InProgress:** ac2 is the operator's run on dev after the merge,
recorded by the PM ([Operator follow-ups](#operator-follow-ups)). **Look first at** the two
[questions](#questions-for-the-pm) (2026-ld, and prod's refile) and Deviation 2: `remove`'s dry run
restores into the data directory, not a scratch copy.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `openev-metadata-reimport-in-bucket-mode` (Bucket mode re-import) | Done | Service, CLI form, container factory, tests red then green, 9 mutants, runbook and its doc test. Its criterion passes (below) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1, "In bucket mode, the re-import takes the lock, restores, re-derives, publishes the manifest and saves the bundle; its dry run changes nothing and prints the counts; it refuses in the window, on a Wednesday and in prod without the flag; by tests shown failing first" | PASS | Red: [19 failed, 1 passed](#red-first), every failure an assertion. Green: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k reimport -n 4 -q -p no:randomly` → `28 passed in 26.58s`. By test: [below](#what-each-test-holds). Mutants: [9 of 9 caught](#mutants) |
| ac2, "The operator's dry run on dev, read by the PM, then the run, leaves dev's bundle with Michigan's 6 files refiled (operator, recorded by the PM)" | **NOT RUN** | The operator's, after this merges: it needs the dev SSO session and the merged build. The blocks are in [Operator follow-ups](#operator-follow-ups), and the counts to expect come from a read-only count of the Mac's copy ([below](#the-counts-the-dry-run-should-show)) |
| Node: "Bucket mode re-import tests pass" (`uv run pytest packages/debate_cli/tests -k reimport`) | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k reimport -n 4 -q -p no:randomly` (the session's time limit, Deviation 1) → `28 passed in 26.58s`: 18 in the new file, 7 of `v1-e30-t08`'s local-mode tests, 3 lock-suite cases |

### What each test holds

All in `packages/debate_cli/tests/bucket_mode/test_bucket_mode_openev_reimport.py`, through the real
application and composition root, over moto (versioned, conditional writes). The bundle is the one
`caselist seed-run-state` writes after a pull of the parse world's synthetic weeks and its invented
camp file. Each re-import runs from a data directory of its own. The expected counts are written by
hand in the module's docstring from the pulled row: camp `UNKNOWN` → `TSF`, 1 title and 1 warning
changed, 1 record, 1 file not held. The row keeps `openev_camp_word` as written (`v1-e30-t31`).

* The dry run: the counts, `applied false`, the `--execute` command to run; **every version of every
  key** in the bucket unchanged (the lock's included), the lock never taken, the working copy
  restored. Its text names `TSF` and `UNKNOWN` and no title word or path.
* The run: the counts, the manifest `uploaded`, the bundle saved under a new version, the row's camp
  `TSF` with `openev_camp_word`, digest, path, size, classification and identity unchanged; the lock
  taken under `caselist reimport-openev-metadata` and free after.
* The bundle holds the refile: a dry run from another fresh working copy restores `TSF` before and
  after, 0 rows and 0 records to change.
* A second run publishes and saves nothing.
* No bytes: no `GetObject` under `raw/` from any client, and the local blob store's `get` refuses.
  The file is counted as not held (`blobs_missing 1`), and the blob tree stays empty.
* The window: Tuesday 06:00, Wednesday 00:30 and Wednesday 23:30 Chicago refused for the dry run and
  the run (`INSIDE_NO_IMPORT_WINDOW`, closing at `2026-10-22T05:00:00+00:00`), nothing restored or
  written. Tuesday 05:59 and Thursday 00:00 run. A window that opens as the lock is taken stops it
  before the restore, with the lock released.
* Prod (a bucket-mode prod profile over the same bucket): `--execute` without `--confirm-prod` is
  `CONFIRMATION_REQUIRED`, nothing restored or written. With the flag it reaches the lock, whose home
  is dev's (`RUN_LOCK_WRONG_HOME`): the flag was what stopped it.
* A live lease is `RUN_LOCK_HELD`. A moved home is `RUN_HOME_MOVED`, with the lock's own message,
  for the dry run and the run. An unseeded bucket is `RUN_STATE_NOT_SEEDED` for both. Nothing is
  written in any of them.
* A bundle rewritten between the restore and the publish is `BUNDLE_CHANGED_SINCE_RESTORE`: nothing
  is published, the rewriter's bundle stays, the lock is released.
* `--dry-run --execute` is a usage error.

`test_bucket_mode_lock.py` now classifies the command as one that writes a bucket and adds it to
`COMMANDS`, so the suite's three parametrized checks cover it: it takes the lock and frees it, it is
refused while another runner holds it, and it is refused after the move, naming the move.

### Red first

Before any mutant, the service's two methods were replaced by a refuse-nothing skeleton. That is
`v1-e30-t08`'s behaviour over the local copy: no window, no lock, no restore, no publish, no save.
The CLI's prod refusal was removed too. The tests, committed at `f124971`, were run against it:

`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/bucket_mode/test_bucket_mode_openev_reimport.py packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py -k reimport -n 4 -q -p no:randomly --tb=line` → **19 failed, 1 passed in 26.63s**. All 30 tracebacks are `AssertionError`s: 16 at an exit code that was `NO_RECORDED_RELEASE` (the skeleton read an unrestored working copy), the rest at "never took the lock" and at refusals that were not made. The one that passed is the `--dry-run --execute` usage error, which the skeleton kept. The code was restored with `git checkout HEAD --`.

The window-inside-the-lock test was added after that run (`d204b26`); its red is the mutant below.
The runbook's doc test was shown failing by renaming the summary's `bundle_saved` key: `1 failed, 2
passed`, at the run's read.

### Mutants

Each was applied to the committed code by exact replacement and run against the same two files. No
test here uses Hypothesis, but each run still had a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (agreement
8). The code was restored with `git checkout HEAD --` after each, and `git status` was clean at the
end. Every catch is an `AssertionError` at the test's own line, not a crash.

| Mutant | Result | Caught by |
|---|---|---|
| 1, the bundle not saved (a `BundleSave(saved=True)` returned, no save) | 3 failed | the run's new bundle version; the read-back from another copy (`UNKNOWN` before); the second run |
| 2, the lock not taken (`_locked` yields without the guard) | 14 failed | the lock suite's three cases ("never took the lock"), the run (`OPENEV_REIMPORT_INCOMPLETE`: the fence refused the publish), the held-lock, moved and unseeded refusals |
| 3, the dry run writing to the bucket (the dry run runs `execute`) | 2 failed | the dry run's `applied`/published/saved, and its text |
| 4a, the window not refused | 4 failed | the three moments inside it, and the window opening at the lock |
| 4b, a Wednesday not refused (Tuesday from 06:00 only) | 2 failed | Wednesday 00:30 and 23:30 |
| 5, prod allowed without the flag | 1 failed | the prod test: `RUN_LOCK_WRONG_HOME` where `CONFIRMATION_REQUIRED` was due |
| 6, a file's bytes read (each `raw/` object fetched after the restore) | 1 failed | "no source fetched from the bucket" |
| Extra: the bundle-changed refusal removed | 1 failed | the rewritten-bundle test |
| Extra: the window not asked again inside the lock | 1 failed | the window opening as the lock is taken |

Each run was 19 to 21 s.

### The counts the dry run should show

A read-only re-derive of the Mac's copy of both releases, `$HOME/.debate-research/dev/objects/manifests/openev/`
(2026-policy written 2026-10-09, 2026-ld 2026-10-14), with this build's packaged table, through
`rederive_release` and `corrected_camp_file` (the service's own functions). Camp-file records were
compared against a scratch copy of the database, deleted after. 0.01 s. Counts and camp names only:

| Release | Rows | Changed | Titles | Warnings | Records to correct | Files (digests) | Camps that move |
|---|---|---|---|---|---|---|---|
| `2026-policy` | 105 | 6 | 0 | 0 | 6 (0 missing) | 102 | Michigan 40 → 34, Michigan Classic 0 → 5, MNDI 0 → 1 |
| `2026-ld` | 2 | 2 | 0 | 2 | 2 (0 missing) | 2 | none |

The policy figures agree with `v1-e30-t32`'s count. The Mac's copy would also give 106 rows their
upstream identity (it carries none), so the runbook says that count can be up to 106 and moves no
camp. Dev's bundle was seeded from this copy, but a cloud run may have added rows since, so the
runbook reads the run's file count against the dry run's rather than pinning 105.

## Tests and checks run

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k reimport -n 4 -q -p no:randomly` | `28 passed in 26.58s` |
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/architecture tests/docs/test_openev_reimport_runbook_reads.py packages/debate_cli/tests/bucket_mode/test_bucket_mode_openev_reimport.py packages/debate_cli/tests/test_caselist_reimport_openev_metadata.py -n 4 -q -p no:randomly --tb=short` (after the move below) | `281 passed in 24.30s` |
| The always-run list: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py -n auto -m "not slow and not live" -q` | `375 passed in 19.84s` |
| The changed test directory: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/bucket_mode/ -n auto -m "not slow and not live" -q` | Progress reached 100% with no `F` or `E`, then the hard stop ended the session at 115 s before pytest's summary line, so no pass count was printed |
| `tests/smoke/test_caselist_camp_identity_smoke.py tests/smoke/test_caselist_import_smoke.py` (the local form's smoke checks), same bound, `-n 4` | `14 passed in 35.31s` |
| `uv run scripts/affected_tests.py` | 157 of 641 test files, from 12 changed files |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | Stopped at its 115 s limit at 32% (exit 124), so the whole set is about six minutes: **left to the pull request's `ci`** (agreement 10). It showed one `F`. A `-v` run of the same selection, also stopped at 115 s, named it: `tests/architecture/test_a_command_module_imports_no_other_command.py::…[caselist]`, with 2940 passed before the stop. Fixed in `95494d4` by moving the bucket form out of `commands/`; the architecture suite then passed (row 2) |
| `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `1771 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright` (the whole repository, as CI runs it) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 70 CLI command and API route handlers within 25 statements`; `reimport_openev_metadata` holds 15 |
| `uv run scripts/check_command_blocks.py`, `uv run --frozen python scripts/check_links.py` | `OK` (646 blocks), `OK` (3314 links) |
| `uv run scripts/validate_specs.py` | `OK: 562 files, 41 epics, 499 tasks, 22 releases` |

**`origin/dev` moved** during the session: v1-e40-t29 merged (`b21e3b6`). It edits
`test_bucket_mode_lock.py` at a test of its own (line ~609), away from this branch's two edits there.
`git merge-tree --write-tree HEAD origin/dev` merges with no conflict. The branch was not synced,
because `scripts/task sync` pushes; the PR's `ci` runs on the merged result.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/openev_metadata_reimport_in_bucket.py`
  (new): `OpenEvMetadataReimportInBucket` (the dry run and the run), `BucketReimport`,
  `InsideTheNoImportWindow` (`INSIDE_NO_IMPORT_WINDOW`, the code the backfile import's window
  refusal uses).
* `packages/debate_cli/src/debate_cli/openev_reimport_in_bucket.py` (new): the bucket form's
  rendering, the prod refusal, the JSON summary, and `reimport_counts`, which both forms now share.
  It sits beside `caselist_publish_refusals.py`, not in `commands/`.
* `packages/debate_cli/src/debate_cli/commands/caselist.py`: `--execute` and `--confirm-prod` on the
  command, routed to the bucket form in bucket mode; `--dry-run --execute` refused; docstring.
* `packages/debate_cli/src/debate_cli/container.py`: `openev_metadata_reimport_in_bucket()`.
* `packages/debate_cli/tests/bucket_mode/test_bucket_mode_openev_reimport.py` (new), and
  `test_bucket_mode_lock.py`: the command classified as bucket-writing and added to `COMMANDS`.
* `tests/docs/test_openev_reimport_runbook_reads.py` (new): runs the runbook's two `grep -oE` reads
  over the command's real JSON line.
* `docs/runbooks/caselist-cloud-run.md`: "A camp table change: the OpenEv metadata re-import".
  `caselist-removal.md` and `caselist-backfill.md`: their pre-cutover re-import blocks now say dev
  runs it from the new section instead.

Not touched: `bucket_run.py`, `run_lock.py` (the lock's refusals are reused as raised, wording
unchanged, so v1-e40-t29's change to how a moved refusal is recorded is not crossed), the parse
workers, and `ROADMAP.md`/`docs/README.md`.

## Deviations from the spec

1. **The node's command was run under the session's time limit**, as
   `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests -k
   reimport -n 4`, not `uv run pytest …`. The selection is the same.
2. **`remove`'s dry run does not use a scratch copy.** The brief says to restore "read-only (or into
   a scratch copy, as `remove`'s dry run does)". `remove`'s dry run restores into the data directory,
   which in bucket mode is the working copy (`removal_run_state()` is `run_state()` over
   `storage.data_dir`, and `on_the_working_copy` restores before planning, without the lock). The
   re-import matches that: its dry run restores into the data directory and takes no lock. The
   runbook gives both commands a directory of their own, `$HOME/.debate-research/reimport-working-copy`,
   by `DEBATE_STORAGE__DATA_DIR` on the one command, so the Mac's own dev copy is left as it is.
3. **No smoke check was added** (agreement 5). `tests/smoke` is not in `constraints.packages`, and a
   smoke check of the bucket form needs a seeded bucket. The local form's smoke checks pass (14
   passed). See Follow-up work.
4. **Local mode is unchanged.** "The dry run is the default" is the bucket-mode form's. In local mode
   the command still applies unless `--dry-run`, as `v1-e30-t08` made it and two runbooks and its
   tests rely on, and `--execute` changes nothing there.

## Decisions and assumptions

* **"Any Wednesday" is already inside the window.** `in_no_import_window` (the backfile import's)
  covers Tuesday from 06:00 and the whole of Wednesday, Chicago time. It is reused, not restated, and
  the tests hold both Wednesday ends.
* **The lock is held for the whole run, and the bundle check is kept.** A single hold from the
  restore to the save means only a writer outside the lock could change the bundle. The backfile
  import's `BUNDLE_CHANGED_SINCE_RESTORE` check is still asked before the publish, as the PM
  directed. It is tested by rewriting the bundle mid-run, and its mutant is caught.
* **The window is asked again once the lock is held**, as the backfile import's locked steps ask it.
  Agreement 8's question is whether the second check can be told from its absence. It can: the test
  where the window opens as the lock is taken.
* **The dry run refuses an unseeded bucket and a moved home** by reading the lock object, as the
  backfile import's plan does, raising the lock's own `RunStateNotSeeded` and `RunHomeMoved`. Without
  that, a dry run on an unseeded bucket would fail as `RUN_STATE_BUNDLE_MISSING`, and on a moved home
  it would print counts for a bundle that is no longer the records. It reads the lock and never takes
  it. `remove`'s dry run checks neither.
* **The bucket form's importer reads the suppression list's local and bucket copies as one**, as the
  publisher does. The local form keeps the local copy alone.
* **A release already right changes nothing**: no publish, no save, and a `null` next step.
* **The prod refusal is the CLI's**, `CONFIRMATION_REQUIRED` before anything, as `backfile-import`'s.
* **What a working copy reports as not held** (`blobs_missing`): every file, since a restore fetches
  no source. The caption says "not held in this working copy, which fetches no file", so the number
  reads as expected.
* **The bucket form's JSON leaves out the local manifest's path** the local form prints: it is under
  the home directory, and the removal's JSON names none either.

## Operator follow-ups

ac2, after this task merges into `dev`, from
[caselist-cloud-run.md, "Michigan's refile"](../runbooks/caselist-cloud-run.md#michigans-refile-v1-e30-t32-after-v1-e40-t34-merges),
copied here. Not inside the no-import window: Thursday to Monday, or a Tuesday before 06:00 Chicago.

**Operator command** (expected runtime ~1 min)
Where: your Mac
```bash
WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
cd "$WT" || echo "WT does not exist: $WT"
git fetch origin
git switch --detach origin/dev
test -f packages/debate_core/src/debate_core/application/caselist/openev_metadata_reimport_in_bucket.py && echo "ok: origin/dev $(git rev-parse --short HEAD), the bucket-mode re-import merged" || echo "NOT MERGED: wait for v1-e40-t34 to merge into dev"
aws sso login --profile debate-dev-evidence
aws sts get-caller-identity --profile debate-dev-evidence --query Arn --output text
```
Success looks like `ok: origin/dev <commit>, the bucket-mode re-import merged`, then an ARN containing
`AWSReservedSSO_DebateDevEvidenceOperator`.

**The dry run** of both camp releases. It writes nothing to the bucket and takes no lock.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, a new terminal window
```bash
cd "$WT"
COPY="$HOME/.debate-research/reimport-working-copy"
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
if [[ -n "$PULL" ]] || env | grep -q '^DEBATE_'; then
  echo "STOP: a caselist pull is running, or DEBATE_ overrides are set in this shell; nothing ran"
else
  for EVENT in policy ld; do
    env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" uv run debate-research caselist reimport-openev-metadata --year 2026 --event "$EVENT"
  done
fi
```
Success looks like two `(dry run)` tables whose captions end in `DRY RUN: … the run lock was not
taken.` **Send both tables to the PM.** `2026-policy` should show Michigan 40 → 34, Michigan Classic
0 → 5, MNDI 0 → 1, every other camp unchanged, and `6 changed: 0 title(s) and 0 warning(s) changed,
6 camp-file record(s) to correct`. `2026-ld` should show its camps unchanged and `2 warning(s)
changed`, which any table gives ([question 1](#questions-for-the-pm)). Anything else, an error code
or a `STOP` line: stop and send it to the PM.

**The run**, after the PM has read the counts. `2026-policy` only.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, a new terminal window
```bash
cd "$WT"
COPY="$HOME/.debate-research/reimport-working-copy"
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
if [[ -n "$PULL" ]] || env | grep -q '^DEBATE_'; then
  echo "STOP: a caselist pull is running, or DEBATE_ overrides are set in this shell; nothing ran"
else
  env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" uv run debate-research --json caselist reimport-openev-metadata --year 2026 --event policy --execute | grep -oE '"status": "(ok|error)"|"applied": (true|false)|"rows": [0-9]+|"rows_changed": [0-9]+|"camp_files_updated": [0-9]+|"manifest_published": ("[a-z]+"|null)|"bundle_saved": (true|false)|"code": "[A-Z_]+"'
fi
```
Success looks like `"status": "ok"`, `"applied": true`, `"rows"` the dry run's file count (105 on the
Mac's copy), `"rows_changed": 6`, `"camp_files_updated": 6`, `"manifest_published": "uploaded"`,
`"bundle_saved": true`, and no `"code"` line. `"rows": 0` or nothing printed is not a success.

**The check**, read-only.

**Operator command** (expected runtime ~1 min)
Where: `$WT`, in the same window
```bash
cd "$WT"
env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" uv run debate-research --json caselist reimport-openev-metadata --year 2026 --event policy | grep -oE '"rows": [0-9]+|"rows_changed": [0-9]+|"camp_files_updated": [0-9]+|"manifest_changed": (true|false)|"code": "[A-Z_]+"'
```
Success looks like `"rows"` as in the run, `"rows_changed": 0`, `"camp_files_updated": 0` and
`"manifest_changed": false`: dev's bundle holds Michigan's 6 files refiled. The next weekly cloud run
carries the camps to the occurrence rows and the cards. The PM records ac2 from these lines.

## Follow-up work

* **Prod's Michigan refile** ([question 2](#questions-for-the-pm)). Prod is in local mode, and its
  `openev` manifest was published from the Mac's dev data directory. Dev's refile changes dev's
  bundle only. Once prod is in bucket mode, the same command with `--execute --confirm-prod` works
  there. Until then this task gives no route for prod. E40.
* **A smoke check of the bucket form**, in `tests/smoke`, needs a seeded synthetic bucket like
  `tests/smoke`'s pull checks. It is outside this task's packages. E40 or E41.

## Questions for the PM

Paste-ready:

> **v1-e40-t34: two questions before ac2's run.**
>
> **1. Re-derive `2026-ld` too?** Its 2 rows change their warnings under any table, from a reworded
> warning, and no camp moves (measured read-only on the Mac's copy: 2 rows, 2 warnings, 0 titles, 2
> records). The runbook's dry run shows both releases and its run does `2026-policy` only.
> (a) **Leave `2026-ld`** until another reason to re-derive it (recommended: it changes no camp, and
> a run that changes only warning text is churn in the bundle and the manifest's versions).
> (b) Run it too, after the policy run, with the same `--execute` block and `--event ld`.
>
> **2. Prod's refile.** Prod is in local mode, and its manifests were published from the Mac's dev
> data directory, which is stale since the cutover. Michigan's split reaches prod's records only by
> some route. (a) **Wait for the run's home to move to prod** (ADR-0020 (7)). Then this command, with
> `--execute --confirm-prod`, refiles prod's bundle the same way (recommended: no hand publish from
> a stale copy). (b) A follow-up task: publish dev's refiled manifest to prod from a restored copy.
> That is the "restored-copy publish" that already needs your ruling.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

A careful bucket-mode form that follows `remove`'s pattern where it should and tightens it where
`remove` is loose: the dry run checks an unseeded bucket and a moved home.
1. **ac1 passes.**
   * Red over a refuse-nothing skeleton: 19 failed, all at assertions.
   * Green: 28, and the node criterion passes.
   * All six of the PM's mutants (4 in two forms) and the two extras are caught. Mutant 6 is caught
     by a check that no `raw/` object is ever fetched.
   * The dry run's test holds every version of every key unchanged, the lock included.
2. **ac2 is the operator's,** after the merge, outside the no-import window. The Goal stays
   `InProgress`.
3. **Questions, the PM's rulings:**
   * **1: (a).** Leave `2026-ld`: it moves no camp, and a warnings-only rewrite is churn.
   * **2: (a).** Prod's refile waits for the run's home to move to prod. Then this command with
     `--execute --confirm-prod` does it, with no hand publish from a stale copy.
4. **Deviations accepted:**
   * **1:** the node run under the time limit.
   * **2:** `remove`'s dry run restores into the data directory, so this matches it, and the runbook
     gives both blocks a working-copy directory of their own.
   * **3:** no smoke check.
   * **4:** local mode unchanged.
5. **Decisions accepted:**
   * the backfile import's window rule reused, Wednesdays included;
   * one lock hold, with the bundle-changed check still asked;
   * the window asked again inside the lock;
   * the dry run reading the lock without taking it;
   * the suppression list's two copies read as one;
   * a release already right changes nothing;
   * the CLI's prod refusal;
   * `blobs_missing` explained in its caption;
   * no local path in the JSON;
   * the bucket form moved out of `commands/` for the architecture rule.
6. **Closing checks:** the affected set (157 files) is left to the PR's `ci` under agreement 10, after
   its one failure was found and fixed (`95494d4`). The reimport selection (28), architecture with the
   runbook test (281), the always-run list (375), the local form's smoke checks (14), ruff, pyright
   over the whole repository, lint-imports, thin handlers, the doc checks and the specs are clean.
7. **Merge:** `scripts/task pr --partial` once `ci` is green, after `scripts/task sync`: v1-e40-t29
   merged with no conflict. ac2 then runs outside the window, and not while a backfile import holds
   the lock.

## Operator records (recorded by the PM, 2026-11-01)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac2 | Operator follow-up | PASS | 2026-11-01, from the `caselist-credentials-dev` worktree at `5d20ecb`, into a separate working copy. Dry run, `2026-policy`: Michigan 40 → 34, Michigan Classic 0 → 5, MNDI 0 → 1, every other camp unchanged; 105 files, 6 changed (0 titles, 0 warnings), 6 camp-file records to correct, 106 rows given their upstream identity; the run lock not taken. The run (`--execute`): `status` ok, `applied` true, `rows` 105, `rows_changed` 6, `camp_files_updated` 6, `manifest_published` uploaded, `bundle_saved` true, no error code. The check (the dry run again): `rows_changed` 0, `camp_files_updated` 0, `manifest_changed` false |

ac2 passes, so the Goal is `Succeeded` in this batch. `2026-ld` (3 files, all `UNKNOWN`, 2 reworded warnings) was dry-run only and left alone, by the PM's ruling. Wednesday's run carries the new camps into the occurrence rows and the index; the cards link once dev's function is redeployed past `babccae`.
