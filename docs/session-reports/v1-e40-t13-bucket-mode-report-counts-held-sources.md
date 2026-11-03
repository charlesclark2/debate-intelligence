# Session report: v1-e40-t13-bucket-mode-report-counts-held-sources

| | |
|---|---|
| Task | `v1-e40-t13-bucket-mode-report-counts-held-sources` — In bucket mode, the report stage counts a source the bucket holds at its manifest digest as present |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t13-bucket-mode-report-counts-held-sources.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t13-bucket-mode-report-counts-held-sources.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t13-bucket-mode-report-counts-held-sources` |
| Session status | COMPLETE (Goal stays `InProgress`: ac2 is read after the merge, from a dev cloud run on a new image) |

## Summary

In bucket mode, `CaselistStatusService` now counts a source the local manifest names, that this
machine lacks and the bucket holds with the manifest's recorded digest and size, as present: it
leaves `missing_local`, so the snapshot is in sync and not `incomplete`. The container passes the
mode in (`bucket_mode=self._in_bucket_mode`), so the report stage of `caselist pull`, its retention
stage and `caselist status` all read the one rule. Nothing reads more of the bucket: the rule uses
the `HeadObject` the service already made for `published_sources`, and a test counts the requests.
Local mode is unchanged. Against moto, the cutover's false drift reproduces exactly before the fix
(`openev 2026-policy (something missing)`, the camp download kept as not confirmed, the record
`incomplete`). After the fix the same run confirms the release, releases the download and records
`completed`. ac1 passes. ac2 can only be read after the merge, from the first dev cloud run on a new
image that touches such a snapshot, so the Goal stays `InProgress`. The image follow-up below comes
from the runbook.

**Look first at:** the proposed status wording (Decisions 2), and the publish check (Decisions 4):
the publish already succeeded before the fix, so nothing about it is in scope.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `bucket-mode-report` | Done | Status service rule, container wiring, `caselist status` note and JSON count, runbook line; tests red first, then 13 mutants. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: against moto, a bucket-mode copy missing raw sources the bucket holds at the manifest's digests reports in sync, releases its download, records `completed`; a source missing from the bucket or held with another digest still drifts; local mode unchanged; tests shown failing first | PASS | Red first, against a skeleton that took `bucket_mode` and did nothing with it: `.venv/bin/python -m pytest packages/debate_core/tests/application/caselist/test_bucket_mode_held_sources_drift.py -n 0 -p no:randomly --tb=line -q` → `5 failed, 4 passed`. The 5 that failed were the in-sync case, the partly-held case, and the bucket-lacks, another-digest and no-recorded-digest cases, each failing on `missing_local` still listing every source. The 4 that passed were guards that hold either way: local mode, the request count, a missing manifest, a suppressed row. The CLI file, before the container passed the mode: `2 failed, 2 passed`. The run-level case failed on `'reason': '0 snapshot(s) confirmed; not in sync: openev 2026-policy (something missing)'`, and `caselist status` in bucket mode returned an error envelope (`'status': 'error'`) instead of exit 0. Green: the core file `10 passed` (it gained the size case after the mutants, below) and the CLI file `4 passed` (`test_a_release_whose_older_sources_only_the_bucket_holds_is_no_drift_and_the_run_completes`: exit 0, report `completed` with `1 snapshot(s) confirmed in the bucket` and no drift, retention removed the one `camp_download` and kept nothing, record `outcome: completed`, `failure_codes: []`). |
| ac2: the first dev cloud run after the merge that touches a snapshot whose raw sources it does not all hold records no drift for it (operator) | NOT RUN | It can only be read after this branch merges and a new run image is deployed (Operator follow-ups 1 to 4), from the first such run's record (follow-up 5). No session can close it. |
| Node `bucket-mode-report`: `uv run pytest packages/debate_core/tests/application -k drift` | PASS | Run as `.venv/bin/python -m pytest packages/debate_core/tests/application -k drift -q` under a 115 s alarm → `47 passed in 23.23s`. |

**Mutants** (13: a script in the session's scratchpad that applies one, runs the
covering files with `-n 4 -p no:randomly` and a fresh `HYPOTHESIS_STORAGE_DIRECTORY` each time,
and restores the file with `git checkout`; the tree was clean after each batch). Covering files: the
two new test files, and `test_status_service.py` for the service's mutants.

| # | Mutant | Result |
|---|---|---|
| 0 | PM 1: a source the bucket lacks counted present (`held_only = missing_local`) | CAUGHT: 3 failed (bucket lacks, another digest, no recorded digest) |
| 1 | PM 2: a source with another digest counted present (mismatch branch also adds to the held set) | CAUGHT: 2 failed (another digest, no recorded digest) |
| 2 | PM 3: the rule applies in local mode (`if True`) | CAUGHT: 3 failed (both local-mode tests, and `test_status_service`'s `test_a_source_this_machine_lost_is_missing_locally`) |
| 3 | held sources kept in `missing_local` | CAUGHT: 5 failed |
| 4 | held sources counted as local files | CAUGHT: 2 failed |
| 5 | `held_only_in_bucket` not reported | CAUGHT: 3 failed |
| 6 | size not compared, digest alone decides | **SURVIVED** on the first run (`23 passed`). Added `test_a_source_recorded_at_the_manifests_digest_with_another_size_is_drift`; then CAUGHT, 1 failed. The size comparison predates this task, and nothing covered it. |
| 7 | `in_sync` ignores `missing_local` | CAUGHT: 2 failed |
| 8 | `incomplete` ignores `missing_local` | CAUGHT: 2 failed |
| 9 | a held source headed a second time (a new request) | CAUGHT: 1 failed (the request count) |
| 10 | the container passes `bucket_mode=False` | CAUGHT: 2 failed (the run-level case and `caselist status` in bucket mode) |
| 11 | the status caption omits the held-only line | CAUGHT: 1 failed |
| 12 | the status JSON always carries `held_only_in_bucket` | CAUGHT: 1 failed (local mode's output unchanged) |

**Checks before the report.**

* `uv run scripts/affected_tests.py` → `268 of 528 test files (50.8%) chosen in 12.4 s from 8 changed
  files`. The container is a hub, so that is about half the selection: more than two minutes on
  this machine, whose load average was 14 to 29 from other sessions. Under agreement 10 it is left
  to the pull request's `ci` check, with no hand-off. Within two minutes each, I ran the test
  directories of what changed and the always-run list:
  * `packages/debate_core/tests/application/caselist` → `1625 passed in 68.71s`;
  * `packages/debate_cli/tests/bucket_mode` → `103 passed in 56.40s`;
  * the three `caselist status` command files, `tests/architecture`, `tests/specs`, `test_app.py`,
    `test_help_rendering.py`, `tests/docs`, `tests/scripts/test_check_command_blocks.py`,
    `tests/scripts/test_docs_index.py` and `packages/debate_core/tests/application/test_caselist_sync.py`
    → `615 passed in 23.21s`.
  The first attempt put the second and third groups in one run. The 115 s alarm stopped it at about
  90%, with no failure printed. No worker was left behind. I split it and ran both parts, as above.
* `uv run --frozen ruff check .`, `ruff format --check .`, `lint-imports` (18 kept, 0 broken),
  `python scripts/check_thin_handlers.py` (66 handlers within 25 statements), `python
  scripts/docs_index.py --check-descriptions`, `python scripts/check_command_blocks.py --base
  origin/dev` (no `#` comments in 504 blocks): all exit 0.
* `uv run --frozen pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings`.
* `uv run scripts/validate_specs.py` → `OK: 475 files, 40 epics, 413 tasks, 22 releases`. The Goal stays `InProgress` (ac2), so no phase was set.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/status_service.py`: the
  `bucket_mode` argument, `SnapshotStatus.held_only_in_bucket`, the rule in `_snapshot_status`, and
  the module docstring's new section, "A working copy restored without raw sources".
* `packages/debate_cli/src/debate_cli/container.py`: passes `bucket_mode=self._in_bucket_mode` to
  the one status service the report stage, retention and `caselist status` share.
* `packages/debate_cli/src/debate_cli/commands/caselist.py`: the counts-only line under the status
  table, and `held_only_in_bucket` in a snapshot's `--json` entry only when above zero.
* `packages/debate_core/tests/application/caselist/test_bucket_mode_held_sources_drift.py`: the
  rule against moto (10 tests).
* `packages/debate_cli/tests/bucket_mode/test_bucket_mode_held_sources_drift.py`: the run-level
  acceptance case, the publish check, and `caselist status` in both modes, through the real
  composition root (4 tests).
* `docs/runbooks/caselist-scheduled-sync.md`: one line on the bucket-mode rule, where the runbook
  explains a report stage's drift.

## Deviations from the spec

None.

## Decisions and assumptions

1. **The mode is a constructor argument, set by the container.** The PM asked for the mode to be
   passed in by the caller, in the status service, so the report stage, retention and `caselist
   status` agree. The container builds one service (`caselist_status()`, a singleton) that the sync
   service and the command both use. So `bucket_mode=self._in_bucket_mode` there is the one place,
   and no reader is patched. Every other constructor (tests, the removal service's tests) defaults
   to `False`, which is local mode.
2. **The proposed wording**, under the status table, one line for all snapshots:
   `Raw sources held only in the bucket: 3 in openev 2026-ld. Bucket mode counts each as present, at the manifest's digest.`
   With more snapshots: `… held only in the bucket: 3 in openev 2026-ld, 1 in openev 2026-pf. …`. Counts,
   slugs and snapshot names only. The `Local files` column still reads `0/3`.
3. **`--json` carries `held_only_in_bucket` (a count) only when it is above zero.** Local mode never
   has one, so local mode's JSON is byte for byte what it was (mutant 12 shows the test that pins
   it). `missing_local` in bucket mode no longer lists a held source. It lists what is drift, as
   the CLI's failure panel ("source(s) not on this machine") reads it.
4. **The publish check passed before the fix, so nothing about it is in scope.**
   `test_a_new_file_joining_sources_only_the_bucket_holds_publishes` runs the PM's case through a
   real pull: a camp file joins a release whose older file only the bucket holds. The publish stage
   reads `2 object(s) uploaded across 1 snapshot(s): 1 source(s) and 1 manifest(s)`, and the bucket's
   manifest names both. That held before the change too (the exploratory run printed the same
   reason). `publish_plan` checks the bucket's listing (`verify`) before it looks for local bytes
   (`missing_locally`). It is not a red-first test, because nothing in it was broken.
5. **Size is part of "the manifest's digest".** The rule counts a source present only where the
   recorded digest and the size both match, the same test `published_sources` already used. Bytes
   of another size under a matching recorded digest are other bytes (mutant 6's new test).
6. **The CLI case uses an invented second camp file**, `TSF-Kelp Inherency.docx` in the harness's
   invented `Tamarack` camp, with the parse world's `verbatim` body. I screened the name against the
   dev database's caselist words, read-only, for hspolicy26 (959 words), hsld26 (982) and hspf26
   (1,159): nothing withheld. The `.sqlite3` file's SHA-256 was the same before and after the read.
   A `-shm` mtime may have moved.
7. **The first CLI red run had a test bug, which I fixed before the red run counted.** The harness
   answers `GET /download?path=` with a path that has no leading `/`. My first download stub
   compared against the listed path, so the second file got the first file's bytes. That run failed
   on its premise, not on the drift, and it is not the red run quoted above.

## Operator follow-ups

**The fix reaches the cloud only when a new run image is deployed.** The steps below are
`docs/runbooks/caselist-cloud-run.md`'s own: "Before you start", step 5's dry run and push, step 6's
digest check, plan and apply, with the counts that "A new image, later" gives. The commands are
copied, none is new. **Never time this into a Wednesday run.** The login runs Wednesdays at 03:00
Chicago time and the run at 06:00. Deploy on a Monday, Tuesday or Thursday, after this branch is
merged and a dev pre-release containing it has a green validate-dev run (image job included).

1. **Move the apply worktree to `origin/dev`** ("Before you start"; it is already initialised).

   **Operator command** (expected runtime ~1 min)
   Where: your Mac, anywhere
   ```bash
   WT="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/caselist-credentials-dev"
   cd "$WT" || { echo "WT does not exist: $WT"; }
   git fetch origin
   git switch --detach origin/dev
   test -f infrastructure/modules/caselist_run/run_task.tf && test -f ops/caselist_run/Dockerfile \
     && echo "ok: $(pwd) at origin/dev $(git rev-parse --short HEAD), the run merged" \
     || echo "NOT MERGED: origin/dev has no infrastructure/modules/caselist_run/run_task.tf; wait for v1-e40-t03 to merge"
   git status --porcelain | grep -v 'owner.auto.tfvars' | head -3
   ```
   Success looks like `ok: <the worktree> at origin/dev <commit>, the run merged`, and nothing after it.

2. **Pick the release and build the image, dry run first** (step 5). Set `TAG` to the newest dev
   pre-release that contains this task's merge.

   **Operator command** (expected runtime ~1 min)
   Where: `$WT`
   ```bash
   cd "$WT"
   gh release list --repo charlesclark2/debate-intelligence --limit 3 --json tagName,createdAt --jq '.[] | .tagName + " " + .createdAt'
   TAG="$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')"
   echo "TAG=$TAG"
   if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the listing block first"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else time scripts/caselist_run_deploy.sh dev "$TAG" --dry-run; fi
   ```
   Success looks like seven `ok:` lines, the last `ok: SQLite 3.x.y with FTS5`, then `Dry run
   complete.` with `debate-dev-caselist-run:<tag> built and checked`. A `check image:` line means
   stop: nothing was pushed.

   **Then the push**, which registers a run task definition with the new image and prints the
   digest line ("A new image, later").

   **Operator command** (expected runtime ~3 min)
   Where: `$WT`, in the shell that set `TAG`
   ```bash
   cd "$WT"
   aws sso login --sso-session debate
   if [ -z "$TAG" ]; then echo "STOP: TAG is not set; run the listing block first"; elif env | grep -qE '^(CASELIST_RUN_DEPLOY_PROFILE|DEBATE_RELEASE_REPO)='; then echo "STOP: a deploy override is set in this shell"; else scripts/caselist_run_deploy.sh dev "$TAG" 2>&1 | tee /tmp/caselist-run-deploy.txt | tail -8; fi
   grep -E '^pushed: |caselist_image_digest = ' /tmp/caselist-run-deploy.txt
   ```
   Success looks like `pushed: …/debate-dev-caselist-run@sha256:<64 hex digits>` and the line
   `caselist_image_digest = "sha256:<the same digits>"`.

3. **Replace the digest line, then the plan** (step 6). In `infrastructure/envs/dev/owner.auto.tfvars`,
   replace the existing `caselist_image_digest = …` line by hand with the one the push printed. The
   runbook has no command for replacing it, and step 6's append block stops on a line that is
   already there. Then the runbook's check and plan:

   **Operator command** (expected runtime ~2 min)
   Where: `$WT`
   ```bash
   cd "$WT"
   terraform fmt infrastructure/envs/dev
   grep -cE '^caselist_image_digest += "sha256:[0-9a-f]{64}"$' infrastructure/envs/dev/owner.auto.tfvars
   if env | grep -qE '^(TF_VAR_|TF_WORKSPACE=|TF_DATA_DIR=|TF_CLI_ARGS)'; then echo "STOP: a Terraform override is set in this shell"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -no-color -out=caselist-tasks.tfplan | tee /tmp/caselist-tasks-plan.txt | tail -5; fi
   grep -E '^Plan:|must be replaced|will be destroyed' /tmp/caselist-tasks-plan.txt
   grep -E '^  # ' /tmp/caselist-tasks-plan.txt | grep -v 'module.caselist_run' | head
   ```
   **What to read, and what stops you.** The first count is `1`. Expect `Plan: 2 to add, 4 to
   change, 2 to destroy.`: the login and run task definitions each replaced (the two `must be
   replaced` lines, and nowhere else), and the two schedules and two scheduler roles' policies
   pointed at the new revisions. The second `grep` prints nothing. Any other shape, an account
   assignment or a permission set: stop. **Send the plan to the PM, and apply only after the PM's
   word.**

4. **The apply**, after the PM has read the plan.

   **Operator command** (expected runtime ~1 min)
   Where: `$WT`
   ```bash
   cd "$WT"
   AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false caselist-tasks.tfplan
   AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev output caselist_run_schedule_state
   ```
   Success looks like `Apply complete! Resources: 2 added, 4 changed, 2 destroyed.`, then `"ENABLED"`
   (the cutover's step 8 enabled the run's schedule).

5. **ac2, read from the first run after the image that touches such a snapshot.** That is a run that
   imports into a snapshot whose older raw sources it does not hold: in practice a new OpenEv camp
   file joining an existing release, as `openev 2026-ld` was. The runbook's record check (step 8,
   "Its record reads as a Mac run's does"):

   **Operator command** (expected runtime ~1 min)
   Where: your Mac, the installed build
   ```bash
   aws sso login --profile debate-dev-evidence
   debate-research caselist runs --remote --last 3
   ```
   ac2 passes when that run reads `completed`, its imported snapshots include such a snapshot, and
   its report stage records no drift for it. Before the fix, that report stage read `CASELIST_DRIFT`
   on `openev 2026-ld (something missing)`. A run that touches no such snapshot says nothing about
   ac2: wait for one.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-26

**Notes:**

The cutover's false drift is fixed at its one source, with no new read of the bucket.
1. **ac1 and the node's criterion pass.**
   * Against moto, the cutover's drift reproduces before the fix: something missing, the camp
     download kept as not confirmed, the record `incomplete`.
   * After the fix the same run releases the download and records `completed`.
   * Red first: 5 failed in the core file, and 2 failed in the CLI file before the container passed
     the mode. The passes are guards that hold either way, each named.
   * Local mode's outputs are unchanged, and a test counts the bucket requests.
2. **Mutants: 13, the PM's three among them.** Mutant 6 (size not compared) survived first. That
   comparison predates this task and nothing covered it, so the new test closes an older gap.
3. **Decisions accepted:**
   * the mode as a constructor argument, set once in the container, so the report stage, retention
     and `caselist status` share one rule;
   * the status line's wording, as proposed;
   * `held_only_in_bucket` in `--json` only when above zero;
   * size as part of the manifest's digest;
   * the invented camp file, screened read-only;
   * the first red run's test bug, honestly set aside.
4. **Decision 4, the publish check, is accepted.** It passed before the fix, because `publish_plan`
   reads the bucket's listing before local bytes, so it is a guard test, not a red one.
5. **The image follow-up.** The PM chooses its timing: after Wednesday 2026-10-28's first scheduled
   run has been checked, so that run is read on the cutover's image. The PM reads the plan before
   the apply.
   * Step 3's by-hand replacement of the digest line is a runbook gap. The PM adds a replace block
     to `caselist-cloud-run.md`'s "A new image, later" in the next batch.
6. **ac2** is read from the first run on the new image that touches such a snapshot. The PM
   records it.
7. **The affected set** (268 files) is left to the PR's `ci` under agreement 10. The changed
   directories and the always-run list passed, and the static checks are clean.

No re-review is needed. The PR merges `--partial`, phase `InProgress`, until ac2.

## Operator records (recorded by the PM, 2026-10-30)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac2, the first dev cloud run on a new image | NOT RUN | NOT RUN (image deployed) | The image carrying this task, `v1.1.0-dev.164`, was deployed to dev on 2026-10-29 (`caselist-new-image.tfplan`, read by the PM: 2 added, 5 changed, 2 destroyed, the fifth `task_stopped["run"]`'s message from `v1-e40-t09`; run task definition revision 8, digest `sha256:81656bbf…0317`, the schedule `ENABLED`). The first scheduled run on it is Wednesday 2026-11-04, after which ac2 is read |

The Goal stays `InProgress` until that run is read.
