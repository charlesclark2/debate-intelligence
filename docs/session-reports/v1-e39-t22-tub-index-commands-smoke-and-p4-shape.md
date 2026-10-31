# Session report: v1-e39-t22-tub-index-commands-smoke-and-p4-shape

| | |
|---|---|
| Task | `v1-e39-t22-tub-index-commands-smoke-and-p4-shape` — Smoke checks for tub index build, publish and prune, and a test of P4's shape |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t22-tub-index-commands-smoke-and-p4-shape.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t22-tub-index-commands-smoke-and-p4-shape.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t22-tub-index-commands-smoke-and-p4-shape` |
| Session status | COMPLETE |

## Summary

`tests/smoke/test_tub_index_smoke.py` adds three smoke checks, one each for `tub index build`,
`tub index publish` and `tub index prune`. They run the build as a process against the S3 stand-in,
in bucket mode with the bucket's run lock, as dev runs. The build makes the parsed store itself, from
two structural fixtures filed as two weeks of `testcl26`. What the index must hold comes from those
fixtures' hand-written `.expected.json`. `tests/docs/test_removal_runbook_index_prune_shape.py`
checks the removal runbook's P4. Its dry run and its `--execute --confirm "$CODE"` must be two
blocks, with the dry run first and the "Stop, and do not run the next block, if" prose between them.
All four checks pass on this checkout's script. The three smoke checks also pass on a stamped,
installed build. Each check failed against the breaks listed below. No check found a bug in a
command, so none is xfail.

**The PM should look first at one decision.** `tub index prune --execute` refuses on a Wednesday in
Chicago, and the installed build reads the machine's clock. Validate-dev runs nightly, so on
Wednesdays the execute part asserts that refusal, and that nothing was deleted, in place of the
deletion. It never skips. See Decisions and Follow-up work.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `tub-index-commands-smoke-and-p4-shape` (Tub index smoke) | Done | Three smoke checks, the P4 shape test, a row in `tests/smoke/README.md`'s table of checks |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node: Tub index smoke tests pass (`uv run pytest tests/smoke -k tub`) | PASS | `uv run pytest tests/smoke -k tub` → `3 passed in 15.01s` |
| ac1: the three smoke checks pass on the checkout's script | PASS | as above. The checkout's `.venv/bin/debate-research`, the harness default |
| ac1: the three smoke checks pass on an installed build | PASS | A wheel stamped offline at `2fffba7` (`0.0.1.dev22`, tag `v0.0.1-dev.22`, channel `dev`), installed in a scratch venv; `debate_core.__file__` and `debate_cli.__file__` are in that venv, and no `packages/*/src` is on `sys.path`. `DEBATE_SMOKE_BIN=<venv>/bin/debate-research DEBATE_SMOKE_EXPECT_SHA=2fffba7c… DEBATE_SMOKE_EXPECT_TAG=v0.0.1-dev.22 pytest tests/smoke/test_tub_index_smoke.py tests/smoke/test_cli_smoke.py -k "tub or version" -m "not live and not in_process"` → `4 passed` (the three, and the version check that the harness ran the stamped build) |
| ac1: each smoke check shown failing against a break | PASS | Seven breaks, in the table below. Each failed the check aimed at it, for its reason, and was restored with `git checkout HEAD --` |
| ac1: the P4 shape test fails when the two blocks merge | PASS | Three edits of the runbook, in the table below. Each failed, and the file was restored |

### The breaks, and what caught them

Each break was applied to the checkout and run with the one check it aims at
(`pytest tests/smoke/test_tub_index_smoke.py -k <build|publish|prune> -n 0`). The tree was restored
after each run, and `git status` was clean.

| Break | Check | Result |
|---|---|---|
| `build` registered to `tub_index.publish` (a wrong entry point) | build | FAILED: the build's envelope is `status: error` |
| `build`'s `--json` drops `not_cards_by_store` | build | FAILED: `{'directory', 'manifest'} == {'directory', …'not_cards_by_store'}` |
| `publish` registered to `tub_index.build` | publish | FAILED: the publish's envelope is `status: error` |
| `publish` writes the pointer to `current.json.next`, not `current.json` | publish | FAILED: `the pointer is written last, once` |
| `prune` registered to `tub_index.publish` | prune | FAILED: the prune's envelope is `status: error` |
| `prune` ignores `--confirm` in the command and in the service's backstop | prune | FAILED: the wrong code's `--execute` exits 0 and deletes (`assert wrong["exit_code"] == DOMAIN_FAILURE`) |
| `prune` executes on its dry run | prune | FAILED: `assert True is False` (`applied`) |
| **Installed build:** a debate-core wheel whose publish writes `current.json.next`, built from the scratch archive, nothing committed | publish | FAILED: `the pointer is written last, once` |

Ignoring `--confirm` in the command alone was caught too, but by the error code: the service checks
the code again (`SearchIndexPrune.execute`) and refused, so nothing was deleted. The break in the
table removes both checks, so the run shows the smoke check catching a deletion the operator never
confirmed.

**The Wednesday branch was run as well.** With `is_cloud_run_day` made to return `True`, a rule the
build and the check share, the prune check passed by its refusal branch: `PASSED`, not skipped. On
the session's own day (Saturday 2026-10-31) it passed by its deletion branch.

### The P4 shape test's breaks

The test was run against an edited `docs/runbooks/caselist-removal.md`, and the file was restored
after each run.

| Edit | Result |
|---|---|
| The two blocks merged into one | FAILED: `P4 runs the prune in 1 block(s), not a dry run block and a delete block` |
| The two blocks swapped | FAILED: `the first block is not the dry run alone: [' --execute --confirm "$CODE"']` |
| The deletion chained onto the dry run's line with `&&`, the delete block left in place | FAILED: `the first block is not the dry run alone: [' && \\', ' --execute --confirm "$CODE"']` |

### Before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` (50 files) | `2153 passed in 102.10s`; the script reported `pytest exited 0 after 104 s` (116 s wall clock, selection included) |
| `uv run ruff format --check .` | `1637 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright tests/smoke/test_tub_index_smoke.py tests/docs/test_removal_runbook_index_prune_shape.py` | `0 errors, 0 warnings, 0 informations`. No package source changed |
| `uv run lint-imports` | `Contracts: 19 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 519 files, 40 epics, 457 tasks, 22 releases` |
| `uv run scripts/check_command_blocks.py` | `OK: no '#' comments in 592 shell code blocks in 198 Markdown files` |
| `uv run scripts/check_links.py` | `OK: 3028 relative links and anchors in 468 Markdown files` |

The spec was compared with the local `origin/dev` (`7ac6ce0`, not fetched in the session). The e39
directory has no change since the branch's base (`9004bb9`).

## Files changed

* `tests/smoke/test_tub_index_smoke.py` (new): the three smoke checks.
* `tests/smoke/README.md`: the new file's row in "The checks".
* `tests/docs/test_removal_runbook_index_prune_shape.py` (new): the P4 shape test.
* The task spec's phase, and this report.

## Deviations from the spec

None.

## Decisions and assumptions

* **The parsed store is made by the build, not planted.** The landscape smoke check's planted
  `synthetic26` store cannot be indexed. `tub index build` refuses a slug that
  `debate_cli.caselist_events.EVENTS_BY_SLUG_PREFIX` does not know, and `synthetic` is not in it.
  The synthetic weekly archives of `tests/fixtures/caselist/` parse to no cards. The structural
  fixtures filed under `testcl26` give both: `testcl` is in the table for the smoke checks, and the
  fixtures hold real cards whose expectations were written by hand. Each check runs `caselist import`
  and `caselist parse` through the build.
* **Two fixtures and two weeks give a few cards and two different indexes.** Builds are
  deterministic, so rebuilding one store gives the same index id. Week one is
  `cardmirror-camp-file.docx` from one invented team: two FULL cards with cites, two documents. Week
  two adds `wiki-converted-cite-entries.docx` from a second invented team. Its ABBREVIATED card is
  the Okonkwo card cut short and joins that document as a third occurrence. Its cite-only entry is
  no card. So week two holds two documents and three occurrences, with one cite-only entry left out,
  under a new index id. The publish's shrink guard does not come into it.
* **Bucket mode, with the lock seeded free by the check.** Dev runs `caselist.run_state = "bucket"`.
  The check's own client writes the lock object as the cutover's seed leaves it
  (`LockBody(home_environment="dev", state=FREE)`). The checks assert that publish and
  `prune --execute` leave the lock free. The profiles are signed in as their Identity Center roles
  through the stand-in's IAM and STS, as the removal smoke check signs them in. The prune's deletes
  are asserted to be signed by the takedown profile's key.
* **On a Wednesday in Chicago the execute part checks the refusal.** The build's clock is the
  machine's, and nothing in a smoke check may patch the build. The check reads `is_cloud_run_day`
  before the wrong-code run and after the real one. If the build refused with
  `PRUNE_ON_CLOUD_RUN_DAY`, one of those times must be a Wednesday in Chicago, and the listing must
  be unchanged. Otherwise neither time may be, and the deletion is checked in full. The wrong-code
  run accepts either refusal code until the day is known. On a Wednesday, validate-dev therefore does
  not check that `--execute --confirm` deletes exactly the plan, nor that a wrong code is refused for
  being wrong rather than for the day. The in-process tests in `packages/debate_cli/tests` still
  check both with a pinned clock on every pull request.
* **The P4 test checks one thing beyond "two blocks, dry run first":** that the prose between them
  still says what stops the operator (`Stop, and do not run the next block, if`), working agreement
  11's middle part. It does not check the guards inside the blocks.

## Operator follow-ups

None. The installed-build run used an offline stamped build in the scratchpad. Validate-dev runs
the new checks against the published pre-release after merge.

## Follow-up work

* **A dev-only clock for the build** (E01 smoke harness, or E39). With such a setting, the prune
  smoke check could pin a weekday and check the deletion every night, and pin a Wednesday and check
  the refusal. `storage.s3.endpoint_url` is the model: dev accepts it, prod refuses it. It is a design
  question for the PM, since the build reads no clock override today. Until then the execute part
  covers only the refusal on one night in seven.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The three `tub index` commands now have smoke checks run as a process against the S3 stand-in, and
P4's two-block shape is held by a test.
1. **ac1 passes.**
   * The smoke checks run on the checkout's script (3 passed) and on a stamped, installed build, with
     the version check proving the harness ran that build (4 passed).
   * Seven breaks were each caught by the check aimed at them, and an eighth on the installed build.
   * Removing both `--confirm` checks, so that the smoke check is what catches an unconfirmed
     deletion, is the right way to make that break mean something.
   * The P4 test fails on a merge, a swap and an `&&` chain.
2. **Decisions accepted:**
   * a parsed store the build makes from two hand-checked structural fixtures, giving two distinct
     indexes;
   * bucket mode, with the lock seeded free and checked free after;
   * the deletes checked as signed by the takedown profile;
   * the prose check between P4's blocks.
3. **The Wednesday branch is accepted as built.** It asserts the refusal and an unchanged listing,
   never a skip, and it was run both ways in the session. The deletion and the wrong-code refusal
   stay pinned every day by the in-process tests.
4. **Follow-up, a dev-only clock: no task.** A setting that moves the build's clock would let a
   build step past the cloud-run-day guard, which is a safety rule. The smoke harness is not reason
   enough to add one, even for dev. One night in seven checking the refusal is acceptable.
5. **Closing checks:** the affected set ran whole within the limit (50 files, 2,153 passed), and the
   whole-repo checks pass.
6. **Merge:** once the PR's `ci` is green. It is a plain `scripts/task pr`. Validate-dev runs the new
   checks against the next pre-release.
