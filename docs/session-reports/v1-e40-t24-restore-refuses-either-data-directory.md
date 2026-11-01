# Session report: v1-e40-t24-restore-refuses-either-data-directory

| | |
|---|---|
| Task | `v1-e40-t24-restore-refuses-either-data-directory` — A restore refuses both environments' data directories, not only its own |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t24-restore-refuses-either-data-directory.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t24-restore-refuses-either-data-directory.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t24-restore-refuses-either-data-directory` |
| Session status | COMPLETE |

## Summary

`caselist restore-run-state --into <dir>` now refuses the data directories of both environments, dev's and
prod's, whichever one it runs in. It refuses either data directory itself, any path inside one, and any
path holding one. Before this change a dev restore into `~/.debate-research/prod` went through while prod's
directory was absent or empty, and the restored-copy marker would have landed there. It now fails with
`RESTORE_TARGET_REFUSED` before the lock is taken and before any directory is made.

The running environment's data directory is the one its settings loaded. The other environment's comes
from that environment's own profile file, falling back to its built-in profile, and never from this shell's
`DEBATE_STORAGE__DATA_DIR` (see Decisions). Paths are compared after resolving symlinks, `..`, `~`, a
trailing slash and letter case. If an environment's profile can't be read, every target is refused.

The PM should look first at two additions beyond the brief (Deviations 2 and 3), and at the sibling hint,
which is in words rather than a path because of the forbidden list (Deviation 1). Tests failed first
(79 red), and all 4 of the PM's mutants plus 4 of mine were caught. All three runbooks that restore already
name siblings, so none changed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `restore-refuses-either-data-directory` (Either data directory refused) | Done | Red commit `7a83ab0`, fix `a6e9030`, typing `750e978`, runbook siblings named in tests `4c26410`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a dev restore into prod's data directory, inside it or holding it is refused, as is the converse in prod, and a copy elsewhere is accepted, by tests shown failing first | PASS | Red at `7a83ab0` (skeleton = today's check: the loaded data directory alone, no case folding): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/application/test_restore_refuses_either_data_directory.py packages/debate_core/tests/application/test_restored_copy_marker.py packages/debate_cli/tests/bucket_mode/test_restore_run_state.py -q -p no:randomly -rA --tb=line` → **79 failed, 80 passed in 19.63s**, every failure an assertion (none at collection). Green at `a6e9030` → **159 passed in 20.18s**. At HEAD `4c26410` → **165 passed in 26.29s**. The red and mutant tables are below. |
| Node: "Either data directory refused tests pass" (`uv run pytest packages/debate_core/tests -k restore`) | PASS | Run with the same venv, bounded: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k restore -q -p no:randomly` → **135 passed in 52.86s** (load about 17; most of the time is collection). |

### Red run, by test (at `7a83ab0`)

| Test | Red | Why |
|---|---|---|
| core `test_a_restore_refuses_the_other_environments_data_directory_itself` (dev and prod running × 2 layouts × absent/empty/in use) | 12 failed | Accepted, or refused only as "not empty" |
| core `..._a_directory_inside_the_other_environments_data_directory` | 12 failed | Accepted |
| core `..._a_directory_holding_only_the_other_environments_data_directory` | 6 failed | Accepted |
| core `test_a_symbolic_link_to_prods_data_directory_is_prods_data_directory` (dangling, empty, in use) | 3 failed | Accepted |
| core `test_a_link_on_the_way_to_prods_data_directory_is_followed_too` | 3 failed | Accepted |
| core `test_prods_data_directory_however_it_is_spelled_is_refused` (`/`, `..`, `.`, `PROD`, `.Debate-Research/Prod/copy`) | 6 failed | Accepted |
| core `test_a_dev_restore_into_prods_data_directory_leaves_no_marker_and_makes_no_directory` | 2 failed | The restore went through, and the marker was written into prod's directory |
| core `test_an_environment_whose_data_directory_is_not_known_refuses_every_directory` | 1 failed | Accepted |
| CLI `test_a_dev_restore_refuses_prods_data_directory_before_the_lock_is_taken` (4 shapes × 3 states × with/without sources) | 24 failed | The lock was taken; a bucket never seeded then refused it |
| CLI `test_a_prod_restore_refuses_devs_data_directory_before_the_lock_is_taken` | 8 failed | Same, in prod with `--confirm-prod` |
| CLI `test_a_prod_profile_that_cannot_be_read_refuses_every_directory` | 1 failed | Accepted |
| CLI `test_its_own_data_directory_is_refused_though_this_shell_points_elsewhere` | 1 failed | Accepted |
| Sibling tests (core 24, CLI 2), holding both (2), resolver (7), t21's marker tests (8), existing CLI tests (37) | passed | Expected: these hold under today's check. The sibling tests are the ones the "sibling refused" mutant fails |

### Mutants

Each mutant was applied to the working tree, run against the three changed test files, and reverted with
`git checkout HEAD -- packages/`. The applier is the scratch script
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e40-t24-restore-refuses-either-data-directory/b1e10cc6-64e1-4f85-aab7-3c6ed06e1360/scratchpad/mutants.py`
(not committed). No Hypothesis property is involved, so agreement 8's empty database does not apply. Every
summary line read "N failed, M passed": no errors, no collection failures. These runs were at `750e978`,
before the runbook siblings were added (159 tests).

| Mutant | Result | Caught by |
|---|---|---|
| 1. Only the running environment checked (entries filtered to `environment == running`) | 78 failed | All the other-environment tests, core and CLI |
| 2. Parent case dropped (the "holds" branch removed) | 22 failed | core holding-only (6), holding-both (2), link-on-the-way (3); CLI dev (6), prod (2), and t21's existing holding cases (3) |
| 3. Symlinks not resolved (`normpath(absolute())` in place of `resolve()`) | 16 failed | core symlink (3), link-on-the-way (3); CLI symlink cases (6 dev, 2 prod) and t21's existing link case (2) |
| 4. Sibling refused (inside tested as a string prefix) | 27 failed | Every sibling test, core (24) and CLI (2), plus the sibling restore. Re-run at HEAD, it refuses the cutover runbook's `prod-publish-2026-11-04` and J2's `dev-journey-copy` |
| Extra: letter case not folded | 2 failed | `~/.debate-research/PROD`, `~/.Debate-Research/Prod/copy` |
| Extra: an environment that can't be resolved is skipped instead of refusing | 2 failed | core unresolved, CLI unreadable prod profile |
| Extra: this shell's `DEBATE_STORAGE__DATA_DIR` reaches the other environment | 27 failed | Resolver test, the CLI dev tests (24), own-profile test, unreadable profile |
| Extra: the container drops the running environment's own profile entry | 1 failed | `test_its_own_data_directory_is_refused_though_this_shell_points_elsewhere` |

### Checks before the report

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list only) | **190 of 619 test files (30.7%)**, from 9 changed files. The `container.py` edit reaches almost every CLI test. That is well past two minutes, so under agreement 10 it is **left to the pull request's `ci` check** and was not run here |
| Always-run list: `tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py`, `-m "not slow and not live"`, under `hard_stop.py 115` | **373 passed in 25.23s** |
| The changed CLI test file's directory: `packages/debate_cli/tests/bucket_mode`, same markers and limit | **222 passed in 96.49s** |
| `tests/docs/test_restored_copy_search.py tests/smoke/test_caselist_restore_run_state.py` (the smoke check pins "this environment's own data directory"; run against this checkout's console script) | **24 passed in 6.51s** |
| `ruff format --check .` / `ruff check .` | 1718 files already formatted / All checks passed |
| `pyright packages/debate_core packages/debate_cli` | 0 errors, 0 warnings |
| `lint-imports` | Contracts: 20 kept, 0 broken |
| `scripts/check_thin_handlers.py` | OK: 69 handlers within 25 statements |
| `uv run scripts/validate_specs.py` (after setting the phase to Succeeded) | OK: 545 files, 41 epics, 482 tasks, 22 releases |

## Files changed

- `packages/debate_core/src/debate_core/application/environment_data_dirs.py` (new): `profile_data_dir(environment, *, bundled_config_root)`.
  It returns the data directory an environment's own profile names, then its built-in profile, expanded the
  way `StorageSettings` expands it. It raises `ConfigurationError` on a profile it can't read.
- `packages/debate_core/src/debate_core/application/caselist/run_state_restore.py`: adds `DataDirectory`.
  `restore_target_refusal` and `RunStateRestore` now take `data_dirs` in place of `live_data_dir`. The
  refusal names the environment, folds letter case, and refuses everything when an environment is unknown.
- `packages/debate_cli/src/debate_cli/container.py`: `_data_dirs_a_restore_refuses()` builds the list: this
  run's data directory first, then dev's and prod's from their profiles (with the installed build's bundled
  configuration), and `None` for one that can't be read.
- `packages/debate_cli/src/debate_cli/commands/caselist_restore.py`: the docstring, the `--into` help and the
  refusal's hint now say "both data directories", in words.
- Tests: `packages/debate_core/tests/application/test_restore_refuses_either_data_directory.py` (new, 85
  tests). `packages/debate_cli/tests/bucket_mode/test_restore_run_state.py` gains 37 tests, plus an autouse
  prod profile, so no test resolves prod's directory under the real home folder.
  `test_restored_copy_marker.py` takes the new parameter.
- The spec's phase.

## Deviations from the spec

1. **The sibling suggestion is in words, not a path.** The PM's brief says the refusal "suggests a sibling
   path", but the spec forbids "a path in a refusal's message beyond what the current refusals print", and
   the current refusals print none. The forbidden list wins. The reasons end "name a new, empty one beside
   the data directories", and the hint reads "Name a new or empty directory outside both data directories,
   dev's and prod's, for example one beside them." Tests assert that no path appears in the refusal.
2. **The running environment's directory without the shell's override is refused too.** When
   `DEBATE_STORAGE__DATA_DIR` moves this run's data directory, the directory its profile names (where its
   scheduled agent keeps its data) is refused as well as the moved one. This errs toward refusing more, and
   none of the runbooks restores under an override (they stop if any `DEBATE_*` is set). It has one test and
   one mutant.
3. **Letter case is folded.** The Mac's file system is case-insensitive, so `--into ~/.debate-research/PROD`
   while prod's directory is absent would otherwise create the directory prod later uses. On a case-sensitive
   disk this can only refuse more. It has two tests and one mutant.
4. The node's command `uv run pytest packages/debate_core/tests -k restore` was run as `.venv/bin/python -m
   pytest ...` under `hard_stop.py 115`. That is the same venv, without uv's sync.

## Decisions and assumptions

- **How the other environment's directory is resolved, without loading its whole settings.** Loading prod's
  settings in a dev shell would apply every `DEBATE_*` variable and the `.env` file to prod: a dev
  `DEBATE_STORAGE__DATA_DIR` would become prod's data directory, and prod-only checks would run on dev's
  values. So `profile_data_dir` reads only the two layers that belong to the environment: its profile file,
  found as `load_settings` finds it (`DEBATE_PROFILE_DIR`, then the installed build's bundled configuration,
  then the checkout), and its built-in profile. The value goes through `StorageSettings` itself, so `~` and
  `$VARS` expand as they would when loaded.
- **When it can't be resolved** (invalid TOML, an unreadable file, a `data_dir` that is not a path), the
  container records `None`. The restore then refuses every target with "prod's data directory could not be
  resolved from its settings, so the directory named cannot be checked against it; `DEBATE_ENV=prod
  debate-research config show` says why". That message carries no path, and nothing is written.
- **The refusal code** stays `RESTORE_TARGET_REFUSED` (v1-e40-t21's): it is the same refusal, before the lock,
  with nothing written. The running environment's reasons keep their wording and add the environment's name,
  for example "is this environment's own data directory (dev's)", so the smoke check's and the CLI tests'
  pinned phrases still match. The other environment's reasons read "is prod's data directory, which a
  restore in dev stays out of too".
- **"Real path"** means `expanduser().resolve()`. Non-strict `resolve` follows a dangling link to where prod's
  directory will be, and resolves a target that doesn't exist yet through its nearest existing parent. Both
  cases are tested.
- **Runbooks, checked; none changed.** Each restore target is a sibling of both data directories, inside
  neither and holding neither:
  - `docs/runbooks/evidence-search.md`, J2: `COPY="$HOME/.debate-research/dev-journey-copy"`
  - `docs/runbooks/landscape-report-from-the-cloud-run.md`, restore step: `COPY="$HOME/.debate-research/landscape-copy-${CASELIST}"`
  - `docs/runbooks/caselist-cutover.md`, "Until the promotion": `COPY="$HOME/.debate-research/prod-publish-${WEEK}"`

  All three are in the sibling tests, with an invented caselist and week. The cutover's name starts with
  "prod", which is the case the prefix mutant would wrongly refuse.

## Operator follow-ups

None. The affected set (190 files) runs in the pull request's `ci` check.

## Follow-up work

- **A launchd agent's plist override is invisible here.** An agent installed with `DEBATE_STORAGE__DATA_DIR`
  in its plist keeps its data where only the plist says, and neither the profile nor this shell sees it. The
  installer already reads the plist's data directory (`ops/launchd/install.sh`, `data_directory_in`). A
  restore could read the same value; that belongs to E40 or E41 if the PM wants it. No runbook installs an
  agent that way today.
- **The landscape's `--restored-copy` check** (`landscape_restored_copy.restored_copy_refusal`) still compares
  only the running environment's directory. It only reads, never writes a marker, and since v1-e40-t23 it
  requires the marker, which a data directory never has, so a data directory is already refused there by
  that rule. I'm listing it only for consistency; the PM decides whether it matters.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

A dev restore can no longer leave its marker in prod's data directory, or the reverse. The PM read the
diff of `run_state_restore.py`, `environment_data_dirs.py`, `container.py` and `caselist_restore.py`.
1. **ac1 passes.**
   * Red against today's check: 79 failed, all at assertions, with none at collection.
   * Green: 159 passed, then 165 at HEAD. The node criterion passes (135).
   * The PM's four mutants are caught: one environment only (78), the holding case dropped (22),
     links not resolved (16), and the sibling refused as a string prefix (27). The prefix mutant
     also refuses the cutover runbook's `prod-publish-<week>`, which the sibling tests are there to
     catch.
   * The four extra mutants are caught as well. The one that guards the design is "this shell's
     `DEBATE_STORAGE__DATA_DIR` reaches the other environment" (27).
2. **Resolving the other environment from its own two layers: accepted.** Reading only the profile
   file and the built-in profile, through `StorageSettings` for the expansion, is right. Loading
   prod's whole settings in a dev shell would hand prod every dev override. The profile is found the
   way `load_settings` finds it, with the same bundled configuration root.
3. **Deviations accepted:**
   * **1:** the sibling hint is in words. The forbidden list wins over the brief, and a test holds
     every refusal free of paths.
   * **2:** the running environment's profile directory is refused under an override as well. It
     only refuses more, and no runbook restores under a `DEBATE_*` override.
   * **3:** letter case is folded. It is right for the Mac, and on a case-sensitive disk it only
     refuses more.
   * **4:** the node ran through the venv under `hard_stop`.
4. **Decisions accepted:**
   * an unreadable profile refuses every target, naming `config show` and no path;
   * `RESTORE_TARGET_REFUSED` is kept, with the running environment's pinned phrases unchanged, so
     the smoke check and the earlier tests still match;
   * non-strict `resolve` is used, so dangling links and targets not made yet are followed (both
     tested);
   * the autouse prod profile in the CLI tests, so no test reads the real home folder.
5. **Runbooks:** the three restore targets (J2, the landscape restore, the cutover) are siblings of
   both data directories and are in the sibling tests. None needed a change.
6. **Follow-ups, the PM's rulings:**
   * **The launchd plist override:** not filed. The weekly run is in the cloud now, and no runbook
     installs an agent with a data directory in its plist. This gets reopened if one does.
   * **The landscape `--restored-copy` check:** not filed. Since v1-e40-t23 it requires the marker,
     which no data directory has, so a data directory is already refused there.
7. **Closing checks:** the affected set (190 files, through `container.py`) is left to the PR's `ci`
   under agreement 10. The always-run list (373), `bucket_mode` (222), the docs and smoke restore
   checks (24), ruff, pyright, lint-imports, thin handlers and the specs are clean.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows. The change
   reaches the Mac with the next installed CLI, and the cloud image never runs a restore.
