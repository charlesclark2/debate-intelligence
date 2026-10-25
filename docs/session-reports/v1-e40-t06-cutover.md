# Session report: v1-e40-t06-cutover

| | |
|---|---|
| Task | `v1-e40-t06-cutover` — Cut over: the cloud run takes the schedule and the Mac stops |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t06-cutover.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t06-cutover.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t06-cutover` |
| Session status | PARTIAL: everything a session can build is built and tested, except the base images' digests, which wait for the operator's paste (Operator follow-up 1). The Goal stays `InProgress`: ac1 and ac2 are the cutover session's to run <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The build the cutover's operator session needs is here, and the cutover itself is a runbook,
[`docs/runbooks/caselist-cutover.md`](../runbooks/caselist-cutover.md), one block per step of
ADR-0020 (4), each with its guard and expected output. The pieces:

* **`debate-research caselist restore-run-state --into <dir>`**, over `v1-e40-t04`'s
  `RunState.restore`. It holds the bucket's run lock while it restores, writes only into the named
  directory (the run state and the suppression list it uses are built over that directory), and
  refuses the data directory itself, a directory inside it or holding it (links followed), a file,
  and a non-empty directory, before it takes the lock. 17 moto tests, two more in the lock suite's
  parametrized tables, three smoke checks. Red first, and 12 mutants (below).
* **`caselist.sync_caselists = ["hsld26", "hspolicy26", "hspf26"]` and `caselist.run_state =
  "bucket"` in `config/profiles/dev.toml`**, read from the Mac's installed plist. In the same commits,
  the plist template and `install.sh` lose their `--caselist` arguments (ADR-0020 (5)).
* **Two plan checks** in the runbook, in `t02`, `t03` and `t05`'s style: `IMAGEPLAN` for step 4's
  image change (`2 to add, 4 to change, 2 to destroy`, the run's schedule still `DISABLED`, and
  nothing in either task definition changed but the image) and `SCHEDULEPLAN` for step 8's run
  schedule (`0 to add, 1 to change, 0 to destroy`, the state alone). Each prints `PLAN OK` only for
  its exact shape. 29 tests read them out of the runbook and run them on synthetic plans.
* **The comparison**, `ops/caselist_run/compare_cloud_run.py` (ac1): restore under the lock, check
  the copy is the named run's, re-parse every store and rebuild the index offline, compare source
  records, occurrence records and the index's counts, and print and write counts only. 11 tests
  against a stand-in build.
* **`check_image.sh` refuses a base image whose Python is not the one debate-research runs on**, so a
  digest left behind when `requires-python` moves is caught. The digests themselves are not pinned
  yet: reading them is a live registry call, which is the operator's (Operator follow-up 1).

**Why `--force`.** `v1-e40-t02` to `t05` merged `--partial`: their Goals stay `InProgress` only for
operator steps that happen at this cutover (`t02`'s and `t03`'s by the cutover's runs, `t04`'s seed
and `t05`'s test alert and late-run email). Their code is merged and applied in dev, which is what
this task builds on.

**What the PM should read first:**

1. **Bucket mode is in the dev profile** (Decisions 1). The PM's list named the caselists; the
   merged runbook of `t04` says `t06` puts bucket mode in the profile too, and ADR-0020 (4) step 4
   installs "a build that has the bucket lock and sets bucket mode". So a dev build installed on the
   Mac before the seed is refused by an unseeded bucket. The runbook's order handles it; question 1
   asks the PM to confirm.
2. **The base images' digests** wait for Operator follow-up 1's paste. The Dockerfile change, its
   test and the registry pages it cites are one commit after it.
3. **Prod by hand until the promotion has a gap** (question 2): a copy restored under the dev lock
   holds no raw sources, so a hand publish of new weeks' sources to prod has nothing to publish them
   from, and no command fetches them.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cutover` — Cutover | Built; its operator steps are the cutover session's | The node's criterion passes; the Goal's ac1 and ac2 are operator steps, NOT RUN |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — a dev cloud run and the Mac's offline reproduction of its parse and index agree on records, parse counts and index document count, recorded in `docs/data` (operator) | NOT RUN | An operator step after the cutover's run by hand: the runbook's step 7. The script it runs is built and tested (below); the record, `docs/data/caselist-cloud-run-comparison.md`, is written by that run and committed then |
| ac2 — the Mac's schedule is off, a second runner is refused by the lock, the runbooks give the fallback; prod follows at promotion (operator) | NOT RUN | The Mac's schedule off is step 2; the second runner refused is step 6, during step 5's run. The fallback week and prod are runbook sections now. The lock's refusal of a second runner is tested against moto for the restore (`test_it_is_refused_while_the_cloud_run_holds_the_lock_and_restores_nothing`) and was for the pull by `v1-e40-t04` |
| Node `cutover`: `uv run pytest tests/smoke --collect-only -q` | PASS | `143/152 tests collected (9 deselected) in 0.41s` |

### What was built, and its evidence

| Piece | Command | Result |
|---|---|---|
| `restore-run-state` | `.venv/bin/python -m pytest -q -n 0 -p no:randomly packages/debate_cli/tests/bucket_mode/test_restore_run_state.py` | `15 passed in 38.04s`, three times in one process; `17 passed` under `-n 4` with the two fresh-machine tests added after the mutants |
| …its red run, against a skeleton that refuses no directory and takes no lock | `pytest … test_restore_run_state.py test_bucket_mode_lock.py -k restore` | `11 failed, 6 passed`: the six are the guards the skeleton kept (local mode, prod, no caselists, the copy's contents, the suppression list, the setting's default) |
| …classified with the bucket-writing commands | `test_bucket_mode_lock.py -k "classified or restore"` | `3 passed`: classified, takes and releases the lock, refused under another's lease |
| …in an installed build, offline | `pytest tests/smoke/test_caselist_restore_run_state.py` | `4 passed` (the profile check asserts the bundled values only for an installed build: this checkout's script reads no profile) |
| The dev profile | `pytest packages/debate_core/tests/application/test_settings_environments.py` | `30 passed`; red against the old profile: `assert () == ('hsld26', 'h...26', 'hspf26')` |
| The installer without `--caselist` | `pytest tests/integration/test_launchd_install.py packages/debate_cli/tests/test_runbook_reinstall_runs_the_profile_check.py` | `136 passed`; the new tests against the old installer: `10 failed, 1 passed` |
| The comparison | `pytest tests/scripts/test_compare_cloud_run.py` | `11 passed`; with a comparison that finds no difference: `3 failed`, the three `DIFFER` tests |
| The plan checks | `pytest tests/docs/test_cutover_plan_checks.py` | `29 passed`; with both checks printing `PLAN OK` whatever they read: `24 failed, 5 passed` (the five: the three shapes that are OK, and the two that read the runbook) |
| The image's base Python check | `pytest tests/scripts/test_caselist_run_deploy.py` | `21 passed` |
| Mutants | 12, below | 12 caught, 3 of them only after the tests were strengthened |

### Mutants

Twelve, on the restore's refusals, its lock, its guards and its wiring, each run against
`test_restore_run_state.py` and the lock suite's restore cases (`-n 4 -p no:randomly`, under
`alarm 115`), and the file restored from git after each. No Hypothesis property is involved, so
agreement 8's database rule does not arise.

| Mutant | First run | After 2b75a80 |
|---|---|---|
| The data directory itself allowed | **survived**: the non-empty check refused it first | caught: 3 failed |
| A directory inside it allowed | caught: 1 failed | |
| A directory holding it allowed | **survived**, the same way | caught: 2 failed |
| A file allowed | caught: 1 failed | |
| A non-empty directory allowed | caught: 1 failed | |
| Links not followed (`absolute()` for `resolve()`) | **survived**: the link's target is not empty | caught: 1 failed |
| The CLI's refusal dropped (the service still refuses, inside the lock) | caught: 6 failed | |
| No lock taken | caught: 5 failed | |
| Local mode not refused | caught: 1 failed | |
| Prod not confirmed | caught: 1 failed | |
| The copy's suppression list not reconciled | caught: 1 failed | |
| The run state built over the live data directory | caught: 1 failed | |

The three survivors were not checks without a purpose: each gives the operator a different reason,
and on a fresh Mac, whose data directory does not exist yet, the non-empty check cannot stand in for
the first two. So the tests now assert each refusal's reason, and a new test restores into a data
directory not yet made and into its empty parent. Re-run, all three are caught.

### Before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `187 of 489 test files (38.2%) chosen in 6.3 s from 26 changed files.` Run once under `perl -e 'alarm 115'`: it did not finish in 115 s, so it is left to the PR's `ci` (agreement 10). No worker was left running |
| The always-run list, the docs checks and the changed areas, under `alarm 115`: `tests/architecture tests/specs`, `test_app.py`, `test_help_rendering.py`, `tests/docs`, `test_check_command_blocks.py`, `test_docs_index.py`, the new smoke file, `test_compare_cloud_run.py`, `test_caselist_run_deploy.py`, `test_launchd_install.py`, `test_runbook_reinstall_runs_the_profile_check.py`, `test_settings_environments.py` | `712 passed in 42.24s` |
| `packages/debate_cli/tests/bucket_mode` (`container.py` changed) | `75 passed` after the fix below; the first run had `1 failed, 74 passed` |
| `packages/debate_cli/tests` but `bucket_mode`, under `alarm 115` | `956 passed in 33.94s` |
| `tests/smoke`, under `alarm 115` | `143 passed, 3 warnings in 84.80s` |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1351 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 16 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 55 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 457 files, 40 epics, 395 tasks, 22 releases` |
| `scripts/docs_index.py --check-descriptions`, `check_command_blocks.py --base origin/dev`, `check_links.py` | `All 49 indexed documents under docs/ have a description`; `OK: no '#' comments in 479 shell code blocks in 159 Markdown files`; `OK: 2464 relative links and anchors in 360 Markdown files` |
| `shellcheck` over `install.sh`, `run-caselist-sync.sh`, `check_image.sh` | clean (and `test_the_shell_scripts_pass_shellcheck`) |

**The one failure, and its fix.** `test_the_copy_holds…` and the parametrized refusal failed when
the whole file ran in one process: the live `debate.sqlite3` changed, and its `-wal` and `-shm` went,
during a refused restore. A probe of `sqlite3.connect` during the refusal recorded no connection at
all. An earlier command of the same test (the pull or the seed, in the same process) leaves a SQLite
connection for the garbage collector, and closing it checkpoints the WAL whenever collection
happens. The tests now collect before they snapshot the directory (bfcb40c), and pass three times
in one process.

## Files changed

* **`packages/debate_core/src/debate_core/application/caselist/run_state_restore.py`** (new): the
  restore into a named directory and its refusals.
* **`packages/debate_cli/`**: `commands/caselist_restore.py` (new, the command), `commands/__init__.py`
  (registered), `container.py` (the run state and the suppression list over any directory, and the
  service). Tests: `tests/bucket_mode/test_restore_run_state.py` (new),
  `tests/bucket_mode/test_bucket_mode_lock.py` (classified), and
  `tests/test_runbook_reinstall_runs_the_profile_check.py` (the installer's new sentence).
* **`config/profiles/dev.toml`**: the caselists and bucket mode. Pinned in
  `packages/debate_core/tests/application/test_settings_environments.py`.
* **`ops/launchd/`**: the template and `install.sh` without `--caselist`; the wrapper's comments.
  Tests: `tests/integration/test_launchd_install.py`.
* **`ops/caselist_run/`**: `compare_cloud_run.py` (new); `check_image.sh` (the base image's Python).
  Tests: `tests/scripts/test_compare_cloud_run.py` (new), `tests/scripts/test_caselist_run_deploy.py`.
  The Dockerfile's digests follow Operator follow-up 1.
* **`ops/README.md`**.
* **`docs/runbooks/`**: `caselist-cutover.md` (new); `caselist-scheduled-sync.md` (the cutover's
  banner, the installer without `--caselist`); `caselist-cloud-run.md` (step 8 points at the
  cutover; seven `ok:` lines); `caselist-run-alerts.md` (seven `ok:` lines). Tests:
  `tests/docs/test_cutover_plan_checks.py` (new).
* **`tests/smoke/test_caselist_restore_run_state.py`** (new).

## Deviations from the spec

1. **Files outside `constraints.packages`.** The packages are `docs/runbooks`, `docs/data`, `ops` and
   `tests/smoke`, but the spec's own amendments put pieces elsewhere: `restore-run-state` (2026-10-24)
   is `debate_core.application`, `debate_cli` and their tests; `caselist.sync_caselists` is
   `config/profiles/dev.toml`; the installer's tests are `tests/integration/`; the comparison's and
   the image check's are `tests/scripts/`; and the plan checks' tests are `tests/docs/`, because
   `tests/smoke` admits only checks that run the installed build. Recommend the PM amend `packages`
   to name them, as for `t04` and `t05`.
2. **The image apply's plan check is an image change only**, not the spec's bucket-mode apply. The
   spec's amendment (2026-10-24) asks for a check of `2 to add, 4 to change, 2 to destroy` with the run
   schedule `DISABLED`; `t05`'s apply then carried bucket mode early (the PM's ruling (a)), and the
   PM's brief for this task says step 8's apply is an image change only. `IMAGEPLAN` checks the same
   counts and schedule, and also that no task definition's environment, command, entry point, roles
   or size changes. A plan that still added bucket mode would stop it.
3. **"Offline" in the comparison** reads raw sources from the dev bucket's `raw/`. The restore brings
   no raw sources (ADR-0020 (3)), and a re-parse needs every one, so the re-parse in bucket mode
   fetches them read-only, as a cloud run's parse does. Nothing is downloaded from OpenCaselist and
   nothing is written to any bucket: the parse takes no `--publish`, and in bucket mode every write
   needs the lock, which it does not hold. The runbook says so.
4. **The base images are not pinned yet** (the spec's amendment of 2026-10-24). Reading a digest is a
   live registry call, which is the operator's (Operator follow-up 1); the pin is one commit after
   the paste.

## Decisions and assumptions

1. **Bucket mode in the dev profile.** ADR-0020 (4) step 4 installs on the Mac "a build that has the
   bucket lock and sets bucket mode", and `t04`'s merged runbook says this task puts it in the
   profile. Left to an environment variable, each hand command on the Mac would need it, and
   agreement 11's guards refuse a leftover `DEBATE_*` override. Its cost: a dev build in bucket mode
   is refused by an unseeded bucket, so the build is installed after the Mac's last run, and the seed
   follows at once (runbook steps 1 to 3). The cloud task sets bucket mode itself, so it changes
   nothing there. Prod's profile stays local until the home moves.
2. **The restore's directory must be new or empty.** A copy restored over another store would mix
   the two, and its newest parsed generation, which a parse or a publish reads, could be the other
   store's. A re-restore into a previous copy was considered for speed and refused for that reason.
3. **The restore asks `--confirm-prod` in prod**, as the seed's `--execute` does: holding prod's lock
   turns a scheduled run away.
4. **The lock is the shared helper's** (`holding_the_bucket_lock`): SIGTERM releases it, and the
   restore is classified with the bucket-writing commands, so the classification test covers it.
5. **The copy's suppression list is reconciled** with the bucket's after the restore. The copy's
   own list starts empty, so this writes only the copy; a parse or an index build in the copy then
   leaves out what the bucket's list stops, as the cloud run's did.
6. **The comparison compares records, not only counts.** Each store's source and occurrence records
   are compared by a digest of their sorted lines as well as by count, so two stores with different
   cards in the same numbers differ. The likeliest real difference is a per-file timeout on one
   machine and not the other, which the record would show as a `FAILED` count and different source
   records.
7. **The second runner is the real `caselist pull`**, run only while the cloud run is `RUNNING` with
   20 minutes or more of lease left, so that no pull can start after the cloud run releases the lock.
8. **The installer refuses a build that names no caselist**, whose agent would be refused every
   week, and over an older agent drops its `--caselist` arguments and says which they were and which
   the build names. `--check-launchd` still hands an older agent's caselists to its check.
9. **The scratch copy is removed** after the comparison: a removal does not reach it.

## Operator follow-ups

In order. Each block's prose in the runbook says what to read and what stops you; the PM reads every
plan before its apply.

**1. Now, before the PR: the two base images' digests** (for the Dockerfile; expected runtime ~1 min).
Read-only, from the registries. Docker Desktop must be running.

**Operator command** (expected runtime ~1 min)
Where: this task's worktree
```bash
cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e40-t06-cutover"
BASE=$(scripts/caselist_run_deploy.sh --print-base-image | cut -d' ' -f1)
echo "$BASE"
docker buildx imagetools inspect "$BASE" | head -3
docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.11.7 | head -3
```
Success looks like `python:<the minor>-slim-bookworm`, then for each image its `Name:`, `MediaType:`
(an index) and `Digest: sha256:<64 hex digits>`. Paste the output back; the session pins both index
digests in `ops/caselist_run/Dockerfile`, citing
<https://hub.docker.com/_/python/tags?name=slim-bookworm> and
<https://github.com/astral-sh/uv/pkgs/container/uv>, and its test.

**2. The cutover**, from [`docs/runbooks/caselist-cutover.md`](../runbooks/caselist-cutover.md), after
this task merges and its dev pre-release is green:

| Runbook step | When | Expected runtime |
|---|---|---|
| Before you start: the worktree, where dev stands | Before Tuesday 2026-10-27 | ~2 min |
| 1. The Mac's last run: sign in and the token (Tuesday evening); its record (Wednesday after 09:00) | 2026-10-27, 2026-10-28 | ~1 min each |
| 2. Unload the agent | After step 1's record reads `completed` | ~1 min |
| 3. The release; install it; every build on `PATH` checked; the plist without its caselists; the seed's plan; the seed | The cutover session, 2026-10-29 or 30 | ~8 min |
| 4. The image: dry run, push, digest, plan, `IMAGEPLAN`, the PM's word, apply | The same | ~12 min |
| 5. One run by hand; its record and details (`caselist-cloud-run.md` step 8's two blocks); its log | The same | up to ~2.5 h |
| 6. The second runner refused (ac2), while step 5 runs | The same | ~1 min |
| 7. The comparison (ac1); then removing the copy | After step 5 | ~1.5 h |
| 8. The schedule on: plan, `SCHEDULEPLAN`, the PM's word, apply | After step 7 agrees | ~4 min |
| 9. The late-run alarm's email: `caselist-run-alerts.md`'s three "At the cutover" blocks | After step 8 | ~4 min |

Send the PM: step 5's three log lines (the summary line's length, `summary lines found`, SIGTERM),
step 6's output, step 7's `/tmp/caselist-comparison.txt` and its record, and every plan. The session,
if still open, commits the record as `docs/data/caselist-cloud-run-comparison.md`; the PM then sets
this Goal `Succeeded`, and `t02` to `t05`'s as their own criteria allow.

## Follow-up work

* **A `moved` holder for the home's move** (ADR-0020 (7) step 3): no command writes the dev lock
  "held for good" naming `home_environment: prod`. Needed before the pilot's promotion; an E40 task.
* **Raw sources for a hand publish to prod** (question 2): `restore-run-state` brings none, and
  `caselist publish` to prod needs a new week's sources locally.
* **A policy sentence for a copy restored on the Mac** (question 3). The data-use policy lists the
  cloud run's working copy, for the length of a run; a copy restored on the Mac for the comparison or
  a prod publish is not named. Proposed, for the policy's next version: "A working copy restored on
  the operator's machine from the bucket, for a comparison or a hand publish, kept for the length of
  that step and then deleted." The runbook deletes it already; the policy is the PM's to change.
* **`caselist.sync_caselists`'s description** in `settings.py` still says a committed slug "would
  make it ours", which ADR-0020 (5) reversed. A one-line change, left out here because `settings.py`
  reaches every test (any task that touches it next).
* **`v1-e40-t05`'s note on the Terraform 1.16 panic** for `infrastructure/README.md` is still open;
  this task changes no Terraform.

## PM questions (relay prompt)

```text
v1-e40-t06 (cutover) is built and committed, PARTIAL: the base images' digests wait for the
operator's paste (one read-only registry block), and ac1/ac2 are the cutover session's.

1. Bucket mode in the dev profile. I put caselist.run_state = "bucket" in config/profiles/dev.toml
   beside the caselists, as t04's merged runbook says t06 does and ADR-0020 (4) step 4 ("a build that
   ... sets bucket mode") implies. Consequence: a dev build installed before the seed is refused by
   the unseeded bucket, so the runbook installs it after the Mac's last run and seeds at once.
   a) Keep it in the profile (recommended): the Mac's hand commands, the fallback week and
      restore-run-state need no override, which agreement 11's guards would refuse anyway.
   b) Take it out: every Mac command against dev after the seed sets DEBATE_CASELIST__RUN_STATE.
2. Prod by hand until the promotion. A copy restored under the dev lock holds no raw sources, so a
   hand publish of a new week's sources to prod has nothing to publish them from.
   a) A --with-sources option on restore-run-state that fetches the raw sources the copy's manifests
      name, as a follow-up task before the next prod publish (recommended).
   b) Publish prod from the comparison's copy once (its re-parse fetched every source), then (a).
   c) Leave prod unpublished until the promotion.
3. The data-use policy names the cloud run's working copy but not a copy restored on the Mac. The
   runbook deletes it after each step. Proposed sentence in the report's follow-ups; yours to adopt.
4. Packages: amend constraints.packages to name debate_core.application, debate_cli and their
   tests, config/profiles, tests/integration, tests/scripts and tests/docs (deviation 1).

FYI, going ahead unless you say otherwise:
- IMAGEPLAN also stops a plan whose task definitions change anything but the image.
- SCHEDULEPLAN checks the state change the tfvars switch asks for, so the fallback week reuses it.
- The comparison compares record digests as well as counts, and fetches raw sources read-only from
  the dev bucket for its re-parse.
- The second-runner check is the real pull, guarded to run only while the cloud run holds 20+
  minutes of lease.

Reply with: 1a/1b, 2a/2b/2c, 3 adopt or not, 4 amend or not.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
