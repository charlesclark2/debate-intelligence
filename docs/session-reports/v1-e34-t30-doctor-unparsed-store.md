# Session report: v1-e34-t30-doctor-unparsed-store

| | |
|---|---|
| Task | `v1-e34-t30-doctor-unparsed-store` — doctor says when a store the weekly run will index has never been parsed |
| Spec | [`plan_specs/v1/e34-caselist-sync/t30-doctor-unparsed-store.yaml`](../../plan_specs/v1/e34-caselist-sync/t30-doctor-unparsed-store.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t30-doctor-unparsed-store` |
| Session status | COMPLETE |

## Summary

`debate-research doctor --search-index` names each store that the weekly run's search index stage
would index but that this build's parser has never parsed. Each one comes with its fix,
`debate-research caselist parse --caselist <slug>`, and doctor exits `1`. Where the run has no such
stage, because `caselist.refresh_search_index` is off or the environment names no bucket, the check
says it does not apply, says why, and passes. As the PM ruled, it is an option modelled on
`--evidence-profiles`: plain `doctor` still loads no settings. The logic is
`SearchIndexStoreCheck` in `debate_core.application`, and `doctor.py` only renders it.

The stage and the check now share two functions in `caselist_sync`: the store list (the caselists,
each once, then `openev`) and the rule for whether the stage is wired in. The composition root wires
the stage by that same rule. `ops/launchd/install.sh --check-launchd` now runs the check as the agent
will.

**What the PM should look at first:** [Decision 1](#decisions-and-assumptions). The installed agent
names its caselists as `--caselist` arguments in its plist, not in `caselist.sync_caselists`. So
`--check-launchd` hands the agent's caselists to `doctor` as `DEBATE_CASELIST__SYNC_CASELISTS` in
the one-off check's environment. A hand-run `doctor --search-index` on Charlie's Mac sees no
caselists unless that variable is set, and then checks `openev` alone (it says so).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `doctor-check` (Unparsed-store check) | Done | The check, the `--search-index` option, the shared store list and wiring rule, the launchd check, the runbook and a smoke check. Tests shown red against a skeleton that refuses nothing, then green; 18 of 18 mutants killed. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: doctor names each unparsed store the stage would index, with the parse command, and passes when every store is parsed or the setting is off, by tests shown failing first | PASS | Red, then green, below. Tests by case: no version directory (`test_stores_with_no_version_directory_fail_doctor_each_named_with_its_parse_command`, and the core test of the same name); an older parser only (`test_a_store_parsed_only_by_an_older_parser_fails_doctor`); every store parsed (`test_every_store_parsed_passes`); the setting off (`test_with_the_setting_off_the_check_does_not_apply_and_passes`); no bucket (`test_with_no_bucket_the_check_does_not_apply_and_passes`); plain doctor loads no settings (`test_plain_doctor_loads_no_settings_and_checks_no_store`, where loading settings fails the test). |
| Node `doctor-check`: Doctor tests pass (`uv run pytest packages/debate_cli/tests -k doctor`) | PASS | `uv run pytest packages/debate_cli/tests -k doctor` → `72 passed in 3.24s`. Its first run gave `1 failed, 71 passed`: `test_app.py` pins the container's service list by hand, and the new `search_index_store_check` was added to it. |

**Red.** The skeleton: the check reports every store parsed and always applies,
`why_no_search_index_stage` always returns `None`, and `ops/launchd/` is as on the base commit
(`aa60700`). The new and changed tests, run against it:

```bash
perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -p no:randomly -q packages/debate_core/tests/application/test_search_index_store_check.py packages/debate_cli/tests/commands/test_doctor_search_index.py tests/integration/test_launchd_install.py -k "search_index or store_check or check_mode or launchd_check or real_command or plutil_stand_in"
```

→ `30 failed, 28 passed in 19.34s`. Every failure is an assertion, for its reason. For example:
`assert None == 'turned off by setting (caselist.refresh_search_index); …'`, `assert 0 ==
<ExitCode.DOMAIN_FAILURE: 1>`, `assert [('hsld26', True), …] == [('hsld26', False), …]`, and the
wrapper's calls `['--version', 'doctor --evidence-profiles'] == ['--version', 'doctor
--evidence-profiles --search-index']`. The 28 that pass are the ones a check that refuses nothing
should pass: plain doctor, every store parsed, and the store list itself.

**Green.** The same command → `55 passed, 3 failed`. The three were in the tests, not the code:
- Two real-command tests read the table without stripping its box characters.
- The new real-command test inherited the bundled dev profile's `aws_profile`, so the profile check
  failed as well.
- The existing test of a misspelt profile, through the wrapper, now also met an unparsed `openev`.

After the fixes ([Decisions](#decisions-and-assumptions) 5 and 6):

```bash
perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q packages/debate_core/tests/application/test_search_index_store_check.py packages/debate_cli/tests/commands/test_doctor_search_index.py packages/debate_cli/tests/commands/test_doctor.py packages/debate_cli/tests/commands/test_doctor_evidence_profiles.py tests/integration/test_launchd_install.py
```

→ `211 passed in 50.13s`.

**Mutation run.** Each mutant was applied to the source, the covering tests were run with `-x`,
and the file was restored and checked byte for byte. The covering tests were
`test_search_index_store_check.py` and `test_doctor_search_index.py`, or
`tests/smoke/test_caselist_pull_in_process.py` for the container mutant. The script is not
committed. **18 of 18 killed** (pytest exits `2` under xdist `-x`, and each run shows its failures):

| Mutant | Failed tests |
|---|---|
| Applies or not: setting check inverted / bucket check inverted | 11 / 11 |
| Setting check dropped / bucket check dropped | 6 / 3 |
| Bucket said before the setting | 2 |
| Bucket check needs both missing (`and`) | 3 |
| The check ignores "does not apply" | 11 |
| The container wires the stage when the rule gives a reason | 2 |
| Version: `==` → `!=` | 9 |
| Version: generation not stripped (`name == version`) | 1 |
| Version: prefix match (`startswith`) | 1 |
| Version: any directory counts | 4 |
| Version: `any` → `all` | 8 |
| Version: `==` → `<=` (older counts) | 3 |
| Store list: `openev` left out / caselists not deduplicated | 8 / 1 |
| doctor never fails on a store / plain doctor runs the check | 5 / 1 |

## Closing checks (working agreement 10)

| Check | Result |
|---|---|
| `uv run scripts/affected_tests.py`, then that list under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -n auto -m "not slow and not live" <files>` | `203 of 387 test files (52.5%) chosen in 4.7 s from 14 changed files`. The alarm stopped the run at 1:55 with about 92% of it done (exit 142), and there was no failure in what ran. The set is past two minutes, so the rest is left to the PR's `ci`, under the PM's ruling of 2026-10-19. |
| Changed test directories and the always-run list, under the same alarm | See [the run below](#the-changed-directories-and-the-always-run-list). |
| `uv run --frozen ruff format --check .` | `1077 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright` (its `include` is `packages`) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 15 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 404 files, 39 epics, 344 tasks, 21 releases` |

### The changed directories and the always-run list

Two runs, each under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -q -n auto -m "not
slow and not live"`:

| Run | Result |
|---|---|
| `packages/debate_cli/tests`; the always-run list (`tests/architecture`, `tests/specs`, plus `test_app.py` and `test_help_rendering.py`, which that directory already holds); the docs checks (`tests/docs`, `tests/scripts/test_check_command_blocks.py`, `tests/scripts/test_docs_index.py`); `tests/integration/test_launchd_install.py`; `tests/smoke/test_cli_smoke.py`, `test_caselist_pull_in_process.py`, `test_caselist_runs.py` | `1373 passed in 64.25s` |
| `packages/debate_core/tests/application`, which holds both changed core modules' tests | `3023 passed in 62.39s` |

`uv run scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 339 shell code
blocks in 137 Markdown files (1 session reports changed since origin/dev)`.

## Files changed

- **`packages/debate_core/src/debate_core/application/search_index_store_check.py`** (new):
  `SearchIndexStoreCheck`, its findings, and `parse_command`.
- **`packages/debate_core/src/debate_core/application/caselist_sync.py`**: two new functions.
  `search_index_stores(caselists)` is the stage's store list, which the stage now calls instead of
  building the tuple inline. `why_no_search_index_stage(bucket_named=, refresh_search_index=)` is
  the wiring rule, in the words the run records.
- **`packages/debate_cli/src/debate_cli/container.py`**: wires the stage by
  `why_no_search_index_stage`, and adds `search_index_store_check()` (in `SERVICE_NAMES`).
- **`packages/debate_cli/src/debate_cli/commands/doctor.py`**: the `--search-index` option, its
  rows, its failure (`SEARCH_INDEX_STORE_NOT_READY`), and the module docstring's new section and
  "Exit codes". Combined hints now each end with a full stop
  ([Decision 6](#decisions-and-assumptions)).
- **`ops/launchd/run-caselist-sync.sh`**: `--check` runs `doctor --evidence-profiles
  --search-index`, and still takes no argument.
- **`ops/launchd/install.sh`**: `--check-launchd` puts the agent's `--caselist` slugs into the check
  plist as `DEBATE_CASELIST__SYNC_CASELISTS`. Its help text and its exit-`2` message name the new
  check.
- **Tests:**
  - `packages/debate_core/tests/application/test_search_index_store_check.py` (new).
  - `packages/debate_cli/tests/commands/test_doctor_search_index.py` (new).
  - `packages/debate_cli/tests/test_app.py`: the pinned service list.
  - `tests/integration/test_launchd_install.py`: the wrapper's command; the hand-off of the
    caselists; a real-command run that fails on an unparsed store; one more `plutil` stand-in step.
  - `tests/smoke/test_cli_smoke.py`: the option on the installed build.
- **`docs/runbooks/caselist-scheduled-sync.md`**:
  - A row for the never-parsed failure in "The search index stage".
  - "Before the first Wednesday, check that every store is parsed".
  - What `--check-launchd` now runs and what its success looks like.
- **`plan_specs/v1/e34-caselist-sync/t30-doctor-unparsed-store.yaml`**: `ops/launchd`,
  `tests/integration` and `tests/smoke` added to `constraints.packages`, with comments; Goal set to
  `Succeeded`.

## Deviations from the spec

1. **`tests/smoke` added to `constraints.packages`.** It was not in the spec or in the PM's
   context. Working agreement 5 asks a changed CLI surface to update its smoke checks, so `validate-dev`
   now runs `doctor --search-index` against the pre-release, as it runs `--evidence-profiles`. The
   spec carries a comment saying so. The PM may prefer to strike it.
2. **`tests/integration` added with `ops/launchd`.** The PM's ruling put the launchd tests "wherever
   install.sh's tests already live", which is `tests/integration/test_launchd_install.py`. The
   ruling's comment, in the PM's words, sits above the list and names both.
3. **`packages/debate_cli/tests/test_app.py`** pins the container's service list by hand, so it
   changed with the new service. It is inside `packages/debate_cli/tests`, as the spec allows; noted
   because the spec's own acceptance command found it, not the tests written for the task.

## Decisions and assumptions

1. **Where the agent's caselists come from.** The PM's context says "the configured caselists plus
   openev". The agent does not configure them as a setting: `install.sh` writes them as
   `--caselist <slug>` arguments after the wrapper, and no profile sets `caselist.sync_caselists`.
   A check that read only settings would check `openev` alone on Charlie's Mac.
   - **Option rejected:** `doctor --caselist` with the wrapper passing the agent's arguments through.
     The wrapper's `--check` refuses any argument, on purpose (`v1-e34-t10`: "a `--check` that went
     on to read caselist arguments would be one step from a pull"), and an existing test holds it to
     that.
   - **What I did:** `--check-launchd` reads the slugs as it strips them from the check's copy of the
     plist, and sets `EnvironmentVariables.DEBATE_CASELIST__SYNC_CASELISTS` to their JSON there. That
     is the setting a pull without `--caselist` follows, so `doctor` takes "the configured caselists"
     from the same place `caselist pull` would. The agent's plist is not touched, and a test checks
     it byte for byte.
   - **Confirmed on this Mac:** `/usr/bin/plutil -replace` creates a missing key, run on a scratch
     plist. The `plutil` stand-in test now holds the stand-in to the real tool on that step.
   - **Consequence:** by hand, the runbook gives
     `DEBATE_CASELIST__SYNC_CASELISTS='["hsld26","hspolicy26"]' debate-research doctor --search-index`.
     With no caselists, the check says `none configured (caselist.sync_caselists), so openev alone
     is checked`. A `doctor --caselist` option for hand runs would be a small follow-up if the PM
     wants one.
2. **"Parsed" includes a later generation.** A version directory named `<installed
   version>_reparse-<n>` counts as parsed, compared through `parse_version_directory`, which is the
   stage's own reading. Directories of other parsers count as not parsed:
   - **Older:** under this check that store is unparsed, as the PM ruled. The stage itself skips
     rather than fails on it, and either way no index is built. The runbook says so.
   - **Newer:** this build cannot index it either. The command offered is still `caselist parse`.
   - **Completeness:** not checked, per the PM.
3. **The failure's code is `SEARCH_INDEX_STORE_NOT_READY`**, the code the stage fails with on such a
   store. This follows `--evidence-profiles`, which reports the code a command stopped by the same
   setting reports. Exit `1`.
4. **The installer's pre-install check stays `doctor --evidence-profiles`.** Adding `--search-index`
   there would refuse every first install, which comes before the first parse. Only `--check-launchd`,
   which the runbook runs after an install, checks the stores.
5. **The existing real-command profile test turns the stage off.**
   `test_over_the_real_command_the_check_fails_on_a_profile_the_aws_config_lacks_and_names_its_setting`
   runs the wrapper's `--check`, which now also checks stores, in an installation with nothing parsed.
   Its installation sets `DEBATE_CASELIST__REFRESH_SEARCH_INDEX=false`, with a comment, so it stays a
   test of the profile check. The new real-command test of the store check uses the `test`
   environment with a bucket set by variable, because `test` configures no evidence profile and a
   custom `DEBATE_PROFILE_DIR` still inherits the bundled dev profile's `aws_profile`.
6. **Combined hints end with a full stop.** The profile hint has none, so with both checks failing
   the panel read "… logging in changes nothing Run `debate-research caselist parse …`". Now each
   hint is a sentence; no existing test pinned the old joining.
7. **No smoke node in the spec.** The smoke check was added under the existing doctor checks in
   `tests/smoke/test_cli_smoke.py` ([Deviation 1](#deviations-from-the-spec)). It runs in a few
   seconds and reaches no network.

## Operator follow-ups

1. **After this merges and a dev build with it is installed, one `doctor` on Charlie's Mac against
   dev** (the PM's follow-up; a few seconds plus up to 10 for the profile's AWS answer). Where: any
   terminal on Charlie's Mac.

   ```bash
   cd ~ && DEBATE_ENV=dev DEBATE_CASELIST__SYNC_CASELISTS='["hsld26","hspolicy26","hspf26"]' debate-research doctor --evidence-profiles --search-index; echo "doctor exit=$?"
   ```

   Success looks like:
   - `doctor exit=0`.
   - `Search index caselists hsld26, hspolicy26, hspf26`.
   - Four `Search index store` rows, each `parsed by 2026.10.20-docx-6`: the three caselists and
     `openev`.
   - The evidence profile row as usual.

   The PM's note says the three caselists are parsed on docx-6, but not whether `openev` is. If the
   only failure is `openev: not parsed by this build's parser`, that is the check working. The fix it
   names, `debate-research caselist parse --caselist openev`, is what keeps Wednesday's stage from
   failing.
2. **Reinstall the agent from a checkout with this change, then run `ops/launchd/install.sh
   --check-launchd`.** The wrapper changed, so until the reinstall `--check-launchd` refuses with
   `the installed agent's wrapper … is not this checkout's …; reinstall with this script first`, as
   it does for any wrapper change. Use the runbook's sequence, "Reinstalling the agent" in
   `docs/runbooks/caselist-scheduled-sync.md`. Success: `exit code 0`, and in the log one
   `Search index store` row for each of the agent's caselists and `openev`, each `parsed by` the
   build's parser version.

## Follow-up work

- **A `doctor --caselist` option for hand runs**, if the PM wants one ([Decision 1](#decisions-and-assumptions)).
  It belongs to this epic. Not needed by the agent or `--check-launchd`.
- **A completeness check** for a version directory (an `occurrences.jsonl` present, rows in it). The
  PM has kept it out of this task; `v1-e31-t30` is building one for publish-only, and a later task
  can reuse it here.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted with no conditions. Open the pull request with no `--partial`.

**What the PM checked.**
* The branch is clean, 2 commits on origin/dev at `bbfe702`. The only dev commit since is a docs
  refresh, so no sync is needed.
* The diff is the 14 files listed.
* The container wires the stage through `why_no_search_index_stage`, and the stage takes its
  stores from `search_index_stores`, so the check and the run cannot drift apart.
* `--check-launchd` collects only the values that follow `--caselist`, leaves the agent's plist
  untouched, and still passes `--check` with no argument.
* The installer's pre-install check is unchanged.

**Rulings.**

1. **Decision 1 is accepted:** the agent's caselists go into the check plist's environment as
   `caselist.sync_caselists`. It keeps `--check` argument-free, as v1-e34-t10 requires.
   * **No `doctor --caselist` follow-up.** Hand runs set the variable, as the runbook shows.
   * **The real fix is a design question for E40.** Where the weekly run's caselists are
     configured, a setting or plist arguments, is decided once by the E40 ADR (the cloud caselist
     run), since a cloud run has no plist. The PM adds that question to the ADR task.
2. **Deviations 1 to 3 are accepted:** `tests/smoke` under working agreement 5, `tests/integration`
   with `ops/launchd`, and the pinned service list.
3. **Decision 4 is accepted:** a first install comes before the first parse, so only
   `--check-launchd` checks the stores.
4. **Decisions 2, 3, 5 and 6 are accepted as written.**

**Operator follow-ups: accepted, with two notes.**
* **`openev` is parsed on `2026.10.20-docx-6`.** The dev bucket's retirement dry run of
  2026-10-22 lists it current, 107 objects. Expect four passing store rows.
* **One agent reinstall covers this task, v1-e29-t12 and v1-e31-t30.** The installed agent is
  `1.1.0.dev85`, which also predates the OpenAlex setting in the checkout's `.env`. The PM will
  give Charlie one reinstall, then `--check-launchd`, then the `doctor` line, once v1-e31-t30 has
  merged too. They are not run separately.

## PM record, 2026-10-22

Added by the PM. Nothing above is changed, and this section is not a review.

* **Operator follow-ups 1 and 2:** the agent was reinstalled at `1.1.0.dev103` on 2026-10-22 and
  `ops/launchd/install.sh --check-launchd` exited 0. Its log showed `Search index caselists hsld26,
  hspolicy26, hspf26` and four `Search index store` rows, `hsld26`, `hspolicy26`, `hspf26` and
  `openev`, each `parsed by 2026.10.20-docx-6`, with the agent's `runs` 0 before and after. The
  check under launchd covers the hand-run `doctor` line, so both follow-ups are closed.
