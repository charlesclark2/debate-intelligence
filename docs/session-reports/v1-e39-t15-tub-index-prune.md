# Session report: v1-e39-t15-tub-index-prune

| | |
|---|---|
| Task | `v1-e39-t15-tub-index-prune` — tub index prune: the runbook's prune of superseded index versions as one command |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t15-tub-index-prune.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t15-tub-index-prune.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t15-tub-index-prune` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research tub index prune --env <env>` replaces the pasted P4 script in the removal runbook.
The dry run lists every version and delete marker under `reports/tub/search/` except the current
index's directory and the current `current.json`, and prints counts by index directory (ids cut to
eight characters) and a confirmation code. `--execute --confirm <code>` deletes exactly that list. It
refuses on a Wednesday in Chicago, takes the bucket's run lock, and reads `current.json` again before
the first delete. Both runs refuse a pointer that names an index the listing does not hold. The rules
live in `debate_core.application.search_index_prune`, and the command in
`debate_cli.commands.tub_index_prune`. The removal runbook's P4 and the annual purge's step 5 now run
the command, and the purge's step keeps `purge_guard`. **The Goal stays `InProgress`:** ac2's dev
prune is the operator's after the merge (blocks below), so the task merges `--partial`. Look first at
the deleted `packages/debate_api` test (Deviation 1) and at the affected set, which I left to CI
(Deviation 3).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prune` — Index prune command | Done | Tests red against a refuse-nothing skeleton first. Six mutants from the PM's list, plus four more, all caught. Its criterion passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — the dry run lists every superseded version and refuses a pointer the listing does not hold; `--execute` with the code deletes exactly them and refuses if the pointer moved, by tests shown failing first against a stubbed bucket | PASS | Red run (below): 37 failed, 5 passed against the skeleton. Green: `.venv/bin/python -m pytest packages/debate_core/tests/application/test_search_index_prune.py packages/debate_cli/tests/test_tub_index_prune.py -q` → `42 passed`. Both files use moto's versioned bucket through the real S3 adapters; the CLI file uses the real composition root, both profiles signed in as their roles, in bucket mode |
| ac2 — the runbook's P4 uses the command, and one dev prune is recorded (operator) | NOT RUN (partly done) | P4 runs the command as a dry run block and an `--execute --confirm "$CODE"` block, and the annual purge's step 5 does the same after `purge_guard`. `uv run scripts/check_command_blocks.py` → `OK: no # comments in 578 shell code blocks`. `uv run scripts/check_links.py` → `OK: 2940 relative links and anchors`. `tests/docs/test_annual_purge_runbook.py` passes. **The dev prune is not run:** it needs the merged command and the takedown credential, so it is the operator's after the merge (Operator follow-ups) |
| Node `prune`: tub index tests pass (`uv run pytest packages/debate_cli/tests -k tub_index`) | PASS | `uv run pytest packages/debate_cli/tests -k tub_index` → `33 passed in 9.15s` |

### The red run

Commit `f7d458a` (before the sync, `41673ad`) holds the tests and a skeleton that refuses nothing.
`plan` deletes everything it lists, the code is a constant that is never checked, `execute` deletes
with no re-read, and the command takes no lock and runs no guard.

`.venv/bin/python -m pytest packages/debate_core/tests/application/test_search_index_prune.py packages/debate_cli/tests/test_tub_index_prune.py -p no:randomly -q --tb=line`
→ `36 failed, 6 passed`. One of the six passed by doing nothing:
`test_execute_refuses_a_plan_that_would_delete_the_current_index` looped over the skeleton's empty
`kept`. Commit `f0aab3f` makes it assert `kept` first, and it then fails against the skeleton too:
**37 failed, 5 passed**. The five that pass are correct before any rule exists:

* three `is_cloud_run_day` cases whose answer is `False`;
* `test_tub_index_prune_dry_run_still_runs_on_a_wednesday`, a negative;
* `test_tub_index_prune_needs_the_takedown_profile`, which the container already answered: its
  takedown factory raises `TakedownNotConfigured` with no `DEBATE_REMOVAL_PROFILE`.

The skeleton's CLI deletes in bucket mode failed with `RUN_LOCK_NOT_HELD`: the takedown client's
deletes are fenced by the run lock like every bucket write (`v1-e40-t04`).

### Mutants

Agreement 8: each run got a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (nothing here uses Hypothesis).
Each mutant is one textual change, run against both test files and then restored. I ran the
script from the scratchpad; no mutant was committed.

| Mutant | Result | Caught by (count of failing tests) |
|---|---|---|
| 1a. The current index directory deleted: the plan's filter keeps only the pointer | CAUGHT | 9: the dry-run and execute tests in both files |
| 1b. The same, in the last check before the delete | CAUGHT | 1: `test_execute_refuses_a_plan_that_would_delete_the_current_index` |
| 2a. The current pointer deleted: the plan's filter keeps only the directory | CAUGHT | 9, as 1a |
| 2b. The same, in the last check | CAUGHT | 1, as 1b |
| 3. `--execute` without the code: the confirmation comparison skipped | CAUGHT | 7: missing, empty and wrong codes in both files, and a code from an earlier listing |
| 4. The pointer re-read skipped | CAUGHT | 2: `test_a_pointer_that_moved_after_the_dry_run_refuses_and_deletes_nothing`, `test_tub_index_prune_execute_refuses_when_the_pointer_moves_while_it_waits_for_the_lock` |
| 5. A pointer outside the listing accepted | CAUGHT | 4: an index never uploaded, a deleted gzip object, a missing manifest (core), and the CLI refusal |
| 6. The run-lock guard dropped (`execute` called without `run_holding_the_bucket_lock`) | CAUGHT | 4: the lock-holder check, the held-lock refusal, the moved-while-waiting test, and the plain execute (the fence refuses its deletes) |
| 7a. The Wednesday refusal before the lock dropped | CAUGHT | 1: `test_tub_index_prune_execute_refuses_on_a_wednesday_in_chicago` (no lock version may name the prune) |
| 7b. The Wednesday refusal inside `execute` dropped | CAUGHT | 1: `test_execute_refuses_on_the_cloud_runs_day_and_deletes_nothing` |

The two Wednesday checks hid each other at first. Without the CLI's check, the service's still
refused, so no test noticed. Commit `af95e2e` adds the assertion that a Wednesday `--execute` takes
no lock, so each check has a case only it answers.

### Before the report (on `origin/dev` at `fb1009e`, after `scripts/task sync`)

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `335 of 571 test files (58.7%) chosen in 14.3 s from 15 changed files` |
| The affected set, under a hard stop: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest $(cat affected.txt) -m "not slow and not live" -q -p no:randomly` | **Stopped at 115 s, unfinished** (machine load 18 at the start). Left to the pull request's `ci` check, under agreement 10. No worker was left running |
| The always-run list and the tests of what changed: `tests/architecture tests/specs tests/docs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_cli/tests/test_tub_index.py packages/debate_cli/tests/test_tub_index_prune.py packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py packages/debate_core/tests/application/test_search_index_prune.py packages/debate_core/tests/application/test_search_index_publish.py` | `613 passed in 44.30s` |
| `uv run ruff format --check .` | `1599 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli packages/debate_api` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run --frozen pre-commit run check-merge-conflict --all-files` | `Passed` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 58 indexed documents under docs/ have a description` |
| `uv run scripts/check_command_blocks.py`, `uv run scripts/check_links.py` | OK, as in ac2 |
| `uv run scripts/validate_specs.py` | `OK: 493 files, 40 epics, 431 tasks, 22 releases` (Goal left `InProgress`) |

## Files changed

* **`packages/debate_core/src/debate_core/application/search_index_prune.py`** (new): the plan, the
  confirmation code, the refusals, the re-read and the last check.
* **`packages/debate_core/src/debate_core/application/ports/evidence_versions.py`**: the docstring no
  longer says the removal service is the only one that deletes through the port.
* **`packages/debate_cli/src/debate_cli/commands/tub_index_prune.py`** (new),
  **`command_registry.py`**, **`container.py`**, **`bucket_lock.py`**: the command, its registration,
  its factory (the everyday bucket for the pointer, the takedown access for versions), and the lock's
  list of who takes it.
* **Tests**: `packages/debate_core/tests/application/test_search_index_prune.py` and
  `packages/debate_cli/tests/test_tub_index_prune.py` (new). In
  `packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py`, `tub index prune` is classified as
  a bucket writer.
* **`packages/debate_api/tests/test_removal_runbook_index_prune.py`**: deleted (Deviation 1).
* **Runbooks**: `caselist-removal.md` P4 rewritten around the command; `annual-purge.md` step 5 runs
  it after `purge_guard`, and its Tooling, Destructive and step 10 rows say so; `evidence-search.md`
  points at it.

## Deviations from the spec

1. **I deleted a test outside `constraints.packages`.**
   `packages/debate_api/tests/test_removal_runbook_index_prune.py` (`v1-e39-t07`) extracted P4's
   pasted Python from the runbook and ran it. The spec replaces that script with the command, so the
   test could only fail or test nothing. Where its cases went:
   * the current directory and pointer kept, everything else deleted:
     `test_the_dry_run_lists_every_superseded_version_and_delete_marker` and
     `test_the_dry_run_keeps_the_current_index_directory_and_the_current_pointer`;
   * a pointer the listing does not hold: `test_a_pointer_naming_an_index_the_listing_does_not_hold_is_refused`;
   * only the current index: `test_a_bucket_with_only_the_current_index_has_nothing_to_delete`;
   * requests split at 1,000: no counterpart. The S3 adapter deletes one version per call, each fenced
     by the lock, so there is no batch.

   The PM may want `packages/debate_api/tests` added to the spec's packages after the fact.
2. **No smoke check.** Agreement 5 asks for one when a CLI command is added. `tests/smoke` is not in
   this spec's packages, and no `tub index` command has one yet to extend (Follow-up 2).
3. **The affected set ran into its two-minute stop** and is left to the pull request's `ci` check
   (agreement 10). It is wide because `container.py` and the version port's docstring are hub
   modules. Without the docstring fix it was 199 files, but the docstring would then be false.

## Decisions and assumptions

* **Two credentials, as P4 had.** The takedown profile lists and deletes; the everyday profile reads
  `current.json`. The takedown role has `ListBucketVersions`, `GetObjectVersion`, `DeleteObject` and
  `DeleteObjectVersion` under `reports/tub/search/`, but no plain `GetObject`
  (`infrastructure/modules/evidence_bucket/README.md`). Both runs need `DEBATE_REMOVAL_PROFILE`, since
  the dry run lists too, and both ask STS first that the profile is this environment's takedown role
  (`NOT_THE_TAKEDOWN_ROLE`), as `caselist remove`'s preflight does.
* **The listing comes before the pointer read.** A publish that lands between them leaves a pointer
  naming an index the listing does not hold, which is refused, instead of a plan that lists the new
  index as superseded.
* **What counts as "the listing holds the pointer's index":** current, non-marker versions of the
  pointer's `manifest_key` and `object_key`, both inside `reports/tub/search/<index id>/`, plus a
  current `current.json`. No pointer (`NO_CURRENT_SEARCH_INDEX`) and an unreadable one
  (`SEARCH_INDEX_POINTER_UNREADABLE`) are refused too: with nothing to keep, nothing is deleted.
* **Every version inside the current directory is kept**, noncurrent ones included, as P4 kept them.
  They are the same content-addressed index.
* **The confirmation code is `caselist retire`'s pattern.** Twelve hex characters
  (`CONFIRMATION_LENGTH` is imported from `version_retention`) of a SHA-256 over the location, the
  index kept and every `(key, version id)` it would delete. `--execute` plans again and compares
  codes, so any change since the dry run is `CONFIRMATION_MISMATCH`.
* **The guards, in order:** `--env` must match `DEBATE_ENV`; `DEBATE_REMOVAL_PROFILE` must be set;
  prod's `--execute` needs `--confirm-prod`; a Wednesday is refused before the lock is taken. Inside
  the lock, `execute` checks the code and the day again, re-reads the pointer
  (`SEARCH_INDEX_POINTER_MOVED`), and refuses a plan naming anything it keeps
  (`WOULD_DELETE_THE_CURRENT_SEARCH_INDEX`). A held lock is the existing `RUN_LOCK_HELD`, from
  `run_holding_the_bucket_lock`, the call `caselist retire --bucket` and `tub index publish` use.
* **"Wednesday" means all of Wednesday in America/Chicago**, the cloud run's zone. That matches
  `purge_guard`, which checks the Mac's own day, but this works on any clock.
* **Output.** The console shows counts by index directory (eight characters of the id) and
  `current.json`; it never shows a key or the prefix. `--json` carries `delete`, each version's key,
  version id and marker flag, plus `counts`, `groups`, `keeps` and `confirmation`.

## Operator follow-ups

**The dev prune for ac2**, after this branch has merged into `dev`, and **not on a Wednesday**. Run
the blocks from this task's worktree before `scripts/task finish` removes it: its code is what merged.
Each block starts with the checks agreement 11 asks for: no running pull, no `DEBATE_` override, not
Wednesday in Chicago. The first also checks that this branch is in `origin/dev`.

**1. The dry run** (expected runtime about a minute, most of it the two sign-ins; reads only)
Where: your Mac, a new terminal window
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t15-tub-index-prune
git fetch -q origin dev
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
DAY=$(TZ=America/Chicago date +%A)
if [[ -n "$PULL" ]] || env | grep -q '^DEBATE_'; then
  echo "STOP: a caselist pull is running, or a DEBATE_ variable is set in this shell; open a new window"
elif [ "$DAY" = "Wednesday" ]; then
  echo "STOP: it is Wednesday in Chicago; run this on another day"
elif git merge-base --is-ancestor HEAD origin/dev; then
  aws sso login --profile debate-dev-evidence
  aws sso login --profile debate-dev-evidence-removal
  DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research tub index prune --env dev
else
  echo "STOP: this branch is not in origin/dev yet"
fi
```
Success looks like a table titled `tub index prune on s3://debate-dev-evidence-a7508de8: current index
<eight characters>`. It has one row per index directory under `reports/tub/search/` and one for
`current.json`. The current index's row reads `kept`, `current.json`'s reads `current kept, older
would be deleted`, and every other row `would be deleted`. Below it is the line `Dry run: nothing was
changed. Would delete N version(s) and M delete marker(s) of K key(s), in D superseded index
directory(ies) ...; keeps 3 version(s). To carry it out, add: --execute --confirm <code>`. I have not
read dev's bucket, so I cannot say what N, M, K and D will be. **Paste the whole output into the
session for the PM to read before block 2.**
Stop on any refusal. Stop if a row other than the current index's and `current.json`'s says `kept`.
Stop if `keeps` is not 3: more means the current index has noncurrent versions, which the PM should
see first.

**2. The delete** (expected runtime seconds; deletes, and cannot be undone), only after the PM has
read block 1's counts. Set `CODE` to the code block 1 printed.

Where: your Mac, the same window
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t15-tub-index-prune
CODE=put-the-code-block-1-printed-here
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
DAY=$(TZ=America/Chicago date +%A)
if [[ -n "$PULL" ]] || env | grep -q '^DEBATE_'; then
  echo "STOP: a caselist pull is running, or a DEBATE_ variable is set in this shell; open a new window"
elif [ "$DAY" = "Wednesday" ]; then
  echo "STOP: it is Wednesday in Chicago; run this on another day"
else
  DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research tub index prune --env dev --execute --confirm "$CODE"
fi
```
Success looks like the same table with `deleted` in place of `would be deleted`, and a line beginning
`Deleted N:` with N equal to block 1's versions plus delete markers. A refusal deleted nothing.
`CONFIRMATION_MISMATCH` or `SEARCH_INDEX_POINTER_MOVED` means the listing or the pointer changed:
run block 1 again. `RUN_LOCK_HELD` means a run holds the lock: wait for it, then block 1 again.

**3. The check: the current index is still there and still serves** (expected runtime seconds;
reads only). The dry run again, then the current index's gzip object read by its key from
`current.json`.

Where: your Mac, the same window
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t15-tub-index-prune
DEBATE_ENV=dev DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research tub index prune --env dev
BUCKET=$(python3 -I -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["storage"]["s3"]["bucket"])' config/profiles/dev.toml)
OBJECT_KEY=$(aws s3 cp "s3://${BUCKET}/reports/tub/search/current.json" - --profile debate-dev-evidence | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["object_key"])')
aws s3api head-object --profile debate-dev-evidence --bucket "$BUCKET" --key "$OBJECT_KEY" --query ContentLength --output text
```
Success looks like `Dry run: nothing to delete. Kept 3 version(s).` under the same current index as
block 1, then a byte count above zero. Then, five minutes after block 2, sign in to
`https://tub.dev.wfbdebate.com/` and search for any word: the results carry a count above zero.
Paste blocks 1 to 3's output and the search's count back; the session records them here for ac2.

## Follow-up work

1. **A runbook test for P4's shape** (`tests/docs`, outside this spec's packages). It would replace
   the deleted script test by checking that P4's dry run and `--execute` are two blocks and that the
   delete takes `--confirm "$CODE"`, as `tests/docs/test_annual_purge_runbook.py` does for the purge.
   For E39 or E01.
2. **A smoke check for `tub index build`, `publish` and `prune`** against the moto stand-in in
   `tests/smoke` (agreement 5). None of the three has one. For E39.
3. **`docs/architecture/evidence-store-layout.md`'s `reports/` row** still says superseded index
   versions are "pruned by `v1-e39-t07`". It could name `tub index prune` (`v1-e39-t15`); that file is
   outside this spec's packages.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
