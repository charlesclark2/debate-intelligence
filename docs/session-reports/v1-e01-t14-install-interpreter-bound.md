# Session report: v1-e01-t14-install-interpreter-bound

| | |
|---|---|
| Task | `v1-e01-t14-install-interpreter-bound` — One source for the supported interpreter, enforced at install |
| Spec | [`plan_specs/v1/e01-repo-foundation/t14-install-interpreter-bound.yaml`](../../plan_specs/v1/e01-repo-foundation/t14-install-interpreter-bound.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t14-install-interpreter-bound` |
| Session status | COMPLETE. Every criterion passed; the Goal is `Succeeded`. The operator's full-suite run passed (follow-up 0) |

## Summary

`scripts/install_channel.sh` no longer has `PYTHON_VERSION=3.12`. It reads `Requires-Python` from
the `debate_core` wheel's METADATA and passes that specifier to uv as `--python`. If the field is
missing, empty, repeated, only in the description body, or not a specifier, or if the METADATA or
the wheel cannot be read, the script refuses. The refusal names the wheel and uv is never called.

`debate-research doctor` can now fail, on one check only: it exits 1 when the running Python's
Unicode database is not the normalizer's pin, naming both versions and
`docs/evidence/normalization.md`. If it cannot determine the pin at all it exits 70, as a bug.
Every other fact it reports stays informational.

The script now installs into a temporary tool directory first and runs every check there:
provenance, `--version --json`, `python -m debate_cli.installation` and `doctor`. Only if all of
them pass does it replace the real install, and then it repeats the checks.
`--no-path-warning` silences the PATH warning and nothing else; dev-prerelease and validate-dev
pass it.

The supported interpreter is now stated once. Every other workspace `requires-python` equals
debate_core's, and ruff and pyright infer their target from it. A test reads every tracked file
and fails on a Python version anywhere else.

**ac3 was proved on a real build** in scratch tool and bin directories, on a uv-managed 3.13.13.
The build's bound admitted 3.13 only, which is the failure this task guards: someone raises the
bound without moving the pin. doctor failed the rehearsal with `This Python's Unicode database is
15.1.0, but evidence-normalizer-v1 is pinned to Unicode 15.0.0`. The script refused, and nothing
was installed. The real install's fingerprint is unchanged.

**PM, look first at:**

* **Deviations 1–4.** Each is an edit the PM authorised during the session: the debate_core
  accessor, the stale mentions in docs and one comment, the workspace pyprojects, and one smoke
  assertion.
* **Decision 4.** Once the rehearsal passes, the real install repeats every check. If one of those
  repeated checks fails, the real install has already been replaced. The window is narrow but
  real, and Follow-up work proposes how to close it.
* **Decision 7.** What the ac4 scanner counts as "a Python version", and the named exemptions.

## How the operator's real install was protected

* Every install ran through `scratch.sh` in the session scratchpad. It exports fresh
  `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, sets `UV_PYTHON_INSTALL_DIR` to a scratch directory with
  `UV_PYTHON_PREFERENCE=only-managed` and `UV_PYTHON_DOWNLOADS=never`, and exits 99 unless
  `uv tool dir` and `uv tool dir --bin` both resolve inside the scratchpad. Each run logged them,
  for example `uv tool dir --bin = <scratchpad>/tools-final-ac3/bin`.
* The 3.13 is uv-managed, downloaded into the scratch Python directory:
  `UV_PYTHON_INSTALL_DIR=<scratchpad>/pythons uv python install 3.13 --no-bin` →
  `Installed Python 3.13.13 in 1.44s`. A managed 3.12.13 was installed there the same way, for the
  sound build. No download came near two minutes, so there was nothing to hand over.
* Before and after the session I fingerprinted the real install, read-only: SHA-256 of
  `~/.local/share/uv/tools/debate-cli/uv-receipt.toml` and of `~/.local/bin/debate-research`, the
  symlink target, a hash over every file in the tool environment, and the receipt's mtime
  (`1790911031`). `diff` of the two → identical.
* No `uv tool install` or `uninstall` ran outside the wrapper or a pytest `tmp_path`. The
  `uv tool install` probe early in the session (whether uv accepts a specifier) exported scratch
  directories first and printed them.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `doctor-can-fail` — doctor checks the Unicode database and can fail | Done | Reproduced first: with `unicodedata.unidata_version` faked to `15.1.0`, the old doctor exited 0 (`assert 0 == <ExitCode.DOMAIN_FAILURE: 1>`). Then `pinned_unicode_version()` in debate_core (Deviation 1), the four new report fields, `unicode_database_failure`, and the exit codes in the docstring, the CLI README and the runbook. |
| `interpreter-from-metadata` — the install script reads the wheel's Requires-Python | Done | Plus the rehearsal (ac5), doctor in the checks (ac3) and `--no-path-warning` (ac6), with dev-prerelease.yml and validate_dev.py passing it. |
| `one-source` — one statement of the supported interpreter | Done | Workspace `requires-python` lines made equal; ruff `target-version` and pyright `pythonVersion` removed; stale mentions edited; `tests/architecture/test_single_interpreter_source.py`; runbook section "Checking an installed build". |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — the script derives the interpreter from the core wheel's `Requires-Python`; changing the bound changes the request; unreadable metadata makes it refuse; `PYTHON_VERSION=3.12` is gone | **PASS** | **uv accepts a specifier**, checked with the installed **uv 0.11.7 (Homebrew 2026-04-15)**: `uv tool install --force --python ">=3.12, <3.13" "debate-cli @ file://…" --with "debate-core @ file://…"` in scratch directories → installed on 3.12.7, with a homebrew 3.13 on PATH. A real wheel's field is `Requires-Python: >=3.12, <3.13`, with a space, and passes unchanged. **Tests** (`tests/scripts/test_install_channel.py`, real uv, a logging `uv` shim): `test_uv_is_asked_for_the_python_the_core_wheel_requires`: both installs carry `--python <debate_core's specifier>`, which the test reads from the pyproject. `test_changing_the_bound_in_the_wheel_changes_what_uv_is_asked_for`: the wheel says `>=9.1,<9.2` → uv is asked for exactly that and fails, and nothing is installed. `test_metadata_that_cannot_be_read_makes_the_script_refuse_rather_than_guess`, 7 cases: no line, empty value, only in the body, stated twice, not a specifier (`$(touch pwned)`, which never runs), no METADATA, not a zip. Each → exit 1, names `debate_core-0.1.0.dev7-py3-none-any.whl`, says `refusing to guess`, and no `uv tool install` call is made. `test_the_script_holds_no_interpreter_version_of_its_own`. **Real wheels:** dev916's rehearsal said `on a Python matching '>=3.12, <3.13' (debate_core's Requires-Python)` and installed on 3.12.13. dev917's said `'>=3.13, <3.14'` and installed on 3.13.13. `grep PYTHON_VERSION scripts/install_channel.sh` → nothing. Mutations: specifier and refusal tables. |
| **ac2** — doctor reports the running database against the pin, exits non-zero naming both versions and the policy page; exit codes documented; every other fact stays non-failing | **PASS** | `packages/debate_cli/tests/commands/test_doctor.py`, 15 tests, including: the JSON fields; the mismatch → exit 1, `UNICODE_DATABASE_MISMATCH`, message with `15.0.0`, `15.1.0` and `docs/evidence/normalization.md`, full report in `error.details`; a person sees the table, then a panel with the two versions; an unreadable pin → exit 70 `INTERNAL_ERROR` with the "bug in debate-research" hint; five other facts changed (settings unconfigured, unknown package versions, Python `2.7.18`, platform `Plan9`, no services) × JSON and human → exit 0. Property `test_doctor_fails_exactly_when_the_running_database_is_not_the_pin`, on a fresh database with `--hypothesis-show-statistics`: `100 passing, 0 failing, 0 invalid`, events `databases match 70%`, `differ 30%`, `settings not configured 11%`. Every report carries every fact, including the real sentinels (`0.0.0+unknown`, `False`, `""`, `[]`). **Real build:** the sound dev916 wheels installed by hand with `uv tool install --python 3.13` (uv allows it: exit 0), then `debate-research --json doctor` → `error UNICODE_DATABASE_MISMATCH 1`, `This Python's Unicode database is 15.1.0, but evidence-normalizer-v1 is pinned to Unicode 15.0.0, … See docs/evidence/normalization.md.`, and the human run → `doctor exit=1`. **Documented:** the `doctor` docstring and `--help` (0/1/70), the module docstring, `packages/debate_cli/README.md` (a `doctor` section with its own exit table, plus row 1 of the general table), and the runbook's "Checking an installed build" table. |
| **ac3** — the script runs doctor post-install and fails the install on non-zero, leaving no half-installed tool; proved against a real install on 3.13: fails, names the mismatch, `command -v debate-research` finds nothing new; `--version --json` check kept | **PASS** | **Real, uv-managed 3.13.13**, scratch directories, `.venv` stripped from PATH, the build (dev917) stamped and built from HEAD `971e8dd` as dev-prerelease does, with every `requires-python` set to admit 3.13 only. `scratch.sh final-ac3 sh scripts/install_channel.sh --dir <final-313>/dist v0.1.0-dev.917` → `--version --json` printed and passed; `7/7 wired integrations import … complete`; doctor table `Python 3.13.13 / Normalizer's Unicode 15.0.0 / Python's Unicode 15.1.0 / Unicode matches pin no`; panel `UNICODE_DATABASE_MISMATCH`; then `install_channel: debate-research doctor failed for the build installed from v0.1.0-dev.917 (see above)` and `install_channel: the build from v0.1.0-dev.917 failed a check in the rehearsal install (see above); the installed debate-research was not touched`; `exit=1`. `command -v debate-research` before: `/Users/charlesclark/.local/bin/debate-research`, after: the same; scratch bin and tool directory both empty. The whole run took 3.0 s. **Tests:** `test_a_failing_doctor_fails_the_install_and_leaves_nothing_on_the_path`, and `test_every_check_runs_in_the_rehearsal_and_again_after_the_real_install` (the version report, the integration check and doctor each appear twice, in order). |
| **ac4** — the interpreter is stated once; a test enumerates the repository and fails on a new hardcoded version; the runbook describes checking an install | **PASS** | `uv run pytest tests/architecture/test_single_interpreter_source.py` → `23 passed`. It reads every tracked file (`git ls-files`). Every workspace `requires-python` must equal debate_core's exactly (5 files). Named exemptions fail if stale. Scanner cases pass and fail as written, and a planted file shows it working. **Shown failing on the tree before this node** (export of `b772593` with the new test): 2 failed, listing the four `>=3.12` pyprojects, `README.md:51`, the architecture row, `normalization.md:202/204/206`, `test_app.py:133`, `snapshot_service.py:135`, `pyproject.toml:70 target-version = "py312"`, `pyproject.toml:102 pythonVersion = "3.12"` and `install_channel.sh:38` (`cp312`). It also showed the test's own exemption list, now exempt by name (Decision 7). **Runbook:** `docs/runbooks/caselist-scheduled-sync.md` "Checking an installed build": which Python (none chosen by hand; the wheel's metadata), what the installer checks before it replaces anything, a block that runs doctor as the agent runs it, and doctor's exit table. No version is named. |
| **ac5** — rehearse in a temporary tool directory, run every check there, replace only if all pass; a test shows a failing build leaves the previous install untouched; doctor runs in the rehearsal | **PASS** | `test_a_build_failing_a_check_leaves_the_previous_install_byte_for_byte_untouched[integration check / doctor]`: install dev7, run it, snapshot every entry under the tool directory (kind, mode, mtime, SHA-256 or link target); try dev8 failing that check → exit 1, `failed a check in the rehearsal install`, `not touched`; snapshot equal; dev7 still runs; the one `uv tool install` went to a temporary directory. `test_the_rehearsal_goes_to_a_temporary_directory_even_when_the_caller_chose_one`: the caller's `UV_TOOL_DIR` gets only the second install, and the rehearsal directory is removed. **Real wheels:** with dev916 installed in `tools-final-sound`, installing dev917 into the same directory → exit 1 in the rehearsal. The fingerprint of `tools-final-sound` (5599 entries, every file's hash and mtime) is `97edd664…c746` before and after, and the binary still reports `0.1.0.dev916`. |
| **ac6** — an explicit option silences only the PATH warning; both workflows pass it; a test shows the warning present without it and absent with it | **PASS** | Option `--no-path-warning`. `test_the_path_warning_is_shown_without_the_option_and_not_with_it`: present without; absent with, no other `install_channel:` line, and the closing `Installed …` line kept. `test_the_warning_is_never_guessed_away_from_the_environment[CI=true / GITHUB_ACTIONS=true / TERM=dumb]`. `test_the_option_leaves_every_failure_as_it_was[integration check / doctor / unreadable metadata]`: identical `install_channel:` lines with and without. **Callers:** `.github/workflows/dev-prerelease.yml` runs `sh scripts/install_channel.sh --no-path-warning --dir dist "$TAG"`, held by `test_the_workflows_that_install_into_scratch_directories_pass_the_option`. `scripts/validate_dev.py` passes `[*installer, "--no-path-warning", tag]`; validate-dev.yml installs only through it. `test_the_smoke_tier_passes_against_the_build_it_installed` expected the old log line and failed on the change before it was updated: `- v0.1.0-dev.5 UV_TOOL_DIR=…` / `+ --no-path-warning v0.1.0-dev.5 UV_TOOL_DIR=…`. |
| doctor-can-fail: `uv run pytest packages/debate_cli/tests/commands/test_doctor.py` | PASS | `15 passed in 5.42s` |
| interpreter-from-metadata: `uv run pytest tests/scripts/test_install_channel.py` | PASS | `28 passed in 8.51s` |
| interpreter-from-metadata: `shellcheck scripts/install_channel.sh` | PASS | clean |
| one-source: `uv run pytest tests/architecture/test_single_interpreter_source.py` | PASS | `23 passed in 2.11s` |
| Forbidden: a fourth statement of the supported interpreter, docs included | PASS | ac4's test. The remaining mentions are permitted or exempt by name with a reason (Decision 7). |
| Forbidden: relaxing or removing debate_core's upper bound | PASS | Unchanged, `>=3.12,<3.13`. The other members were narrowed to equal it. |
| Forbidden: doctor failing on anything but a precisely stated check | PASS | ac2's tests and the doctor mutation table. |
| Forbidden: network access in tests | PASS | Every URL in the install tests is `file://`, with `UV_PYTHON_DOWNLOADS=never`, `UV_NO_CONFIG=1` and a temporary uv cache. The doctor and scanner tests are in-process or local git. The suite's socket blocking still applies. |

### Mutations

Each mutant was applied to committed bytes by a runner in the scratchpad. Each run used a **new,
empty `HYPOTHESIS_STORAGE_DIRECTORY`**. The original bytes were restored and checked by SHA-256,
and `git status --porcelain` was empty after every batch. A run that errored at collection, or a
mutation that did not apply, would have been reported as such; none did. Final runs were on HEAD
`971e8dd`, each batch under 50 s.

**Specifier reading** (`tests/scripts/test_install_channel.py`)

| Mutant | Result |
|---|---|
| Reads `Metadata-Version` instead of `Requires-Python` | **Caught**, 19 tests, including `test_uv_is_asked_for_…` and `test_changing_the_bound_…` |
| Reads `Requires-Dist` instead | **Caught**, 18 tests |
| Constant fallback (`>=3.12,<3.13`) when the field is empty | **Caught**: the 3 "no Requires-Python" cases and `test_the_option_leaves_every_failure_as_it_was[unreadable metadata]` |
| `--python "3.12"` passed instead of the specifier | **Caught**: `test_uv_is_asked_for_…`, `test_changing_the_bound_…`, `test_the_script_holds_no_interpreter_version_of_its_own` |
| Whole METADATA read, not only the header | **Caught**: `[only in the description body]` |

**Refusal on unreadable metadata**

| Mutant | Result |
|---|---|
| unzip failure swallowed (`|| true`) | **Caught**: `[no METADATA in the wheel]`, `[not a zip archive]`. Only by the message: the next check still refuses, as "states no Requires-Python" (Decision 3) |
| Missing Requires-Python not refused | **Caught**: the 3 missing/empty/body cases. Only by the message: the specifier check then refuses an empty value (Decision 3) |
| Stated twice not refused | **Caught**: `[stated twice]`. uv was then asked to install |
| Non-specifier not refused | **Caught**: `[not a specifier]`. uv was then asked to install |
| Refusal replaced by a guess (`>=3.12`) | **Caught**, 4 tests |

**doctor fails only on the mismatch** (`test_doctor.py` and the doctor tests in `test_app.py`)

| Mutant | Result |
|---|---|
| Fails when settings are not configured | **Caught**: the property, and the two `unconfigured_settings` cases |
| Fails when a package version is unknown (`0.0.0+unknown`) | **Caught**: the property, and the two `unknown_package_versions` cases. My first version of this mutant compared against `"unknown"`, which no report contains, so it never fired and survived. I corrected the mutant and made the property generate the real sentinels and every key |
| Never fails | **Caught**, 3 tests |
| Always fails | **Caught**, 14 tests |
| Compares `python_version` instead of the Unicode database | **Caught**, 15 tests |
| Mismatch exits 70, not 1 | **Caught**, 3 tests |
| Fails a program but not a person | **Caught**: `test_a_person_sees_the_report_and_then_the_mismatch` |
| Unreadable pin reported as a mismatch | **Caught**: `test_an_unreadable_pin_is_a_bug_not_a_mismatch` |
| Failure drops the report from `error.details` | **Caught**: the JSON mismatch test |

The property on its own, from cold, against the five decision mutants (settings, unknown version,
never, always, wrong field) → each caught in 3–5 s.

**Rehearsal before replace** (`tests/scripts/test_install_channel.py`)

| Mutant | Result |
|---|---|
| Real install before the rehearsal | **Caught**: both byte-for-byte cases, the doctor install test, the temporary-directory test |
| Rehearsal installs into the real tool directory | **Caught**, the same 4 |
| Failed rehearsal not fatal | **Caught**: both byte-for-byte cases and the doctor install test |
| doctor not among the checks | **Caught**, 4 tests |
| Rehearsal installs but skips its checks | **Caught**, 4 tests |

**The warning option's scope**

| Mutant | Result |
|---|---|
| Option accepted and ignored | **Caught**: `test_the_path_warning_is_shown_without_the_option_and_not_with_it` |
| Option also skips doctor | **Caught**: `test_the_option_leaves_every_failure_as_it_was[doctor]` |
| Option silences failure messages | **Caught**, all 3 failure cases |
| Warning guessed away when `CI` is set | **Caught**: `test_the_warning_is_never_guessed_away_from_the_environment[CI]` |
| Option silences the closing message | **Caught**: `test_the_path_warning_is_shown_…` |
| validate_dev.py stops passing it | **Caught**: `test_the_smoke_tier_passes_against_the_build_it_installed` |
| dev-prerelease.yml stops passing it | **Caught**: `test_the_workflows_that_install_into_scratch_directories_pass_the_option` |

### Whole-repo checks

* `uv run --frozen pytest packages/debate_cli/tests tests/scripts tests/architecture tests/docs tests/smoke packages/debate_core/tests/evidence -q --no-cov` → `1770 passed, 1 warning in 55.83s`. The warning is pytest-socket's note in the smoke harness, as before.
* `tests/scripts/test_validate_dev.py` is inside that run (`70 passed` on its own).
* **Recorded smoke tier against the installed dev916 build** (validate-dev's way): `DEBATE_SMOKE_BIN=<scratch>/bin/debate-research DEBATE_SMOKE_EXPECT_SHA=971e8dd… DEBATE_SMOKE_EXPECT_TAG=v0.1.0-dev.916 uv run --frozen pytest tests/smoke -m "not live and not in_process" -q` → `27 passed in 5.47s`, including doctor's smoke check and its new Unicode assertion.
* `ruff check .` → `All checks passed!`; `ruff format --check .` → `502 files already formatted`. `pyright` → `0 errors` (it now reports `Assuming Python version 3.12.7`, from the `.venv`). `lint-imports` → `Contracts: 11 kept, 0 broken.` `check_thin_handlers.py` → `OK: 19 … within 25 statements`. `uv lock --check` → clean, and `uv lock` changed nothing. `shellcheck scripts/install_channel.sh` → clean. `uvx --from actionlint-py actionlint` → clean. `check_links.py` → `OK: 1238 relative links and anchors in 166 Markdown files`.
* `uv run scripts/validate_specs.py` → `OK: 307 files, 38 epics, 249 tasks, 20 releases`.
* **Full suite, run by the operator** (reported 2026-10-07, this worktree at `c50b3a5`): `uv run pytest -q` → `4151 passed, 1 skipped, 1 warning in 70.96s`. The skip is the parser eval (`tests/evals/parser/test_parser_eval.py:279`, "4 of 6 pr-subset files are not yet corrected by a person"), not this task's. The warning is pytest-socket's note in `test_smoke_harness.py`, as before. Total coverage 96%; `commands/doctor.py` 100%, `evidence/normalization.py` 100%.

## Files changed

* **`scripts/install_channel.sh`**: the interpreter is read from the core wheel's METADATA, with
  every refusal; `install_and_check`, run first in a temporary tool directory and then for real;
  doctor among the checks; `--no-path-warning`; header rewritten (what it does, options, needs
  `unzip`). Temporary paths no longer get a double slash when `TMPDIR` ends in one.
* **`packages/debate_cli/src/debate_cli/commands/doctor.py`**: four new facts, the exit-code
  contract (module docstring and `--help`), and `unicode_database_failure`. A person's failure
  panel names the two versions rather than repeating the table.
* **`packages/debate_core/src/debate_core/evidence/normalization.py`**: `pinned_unicode_version()`
  (Deviation 1). **`packages/debate_core/tests/evidence/test_normalization.py`**: two tests.
* **Tests**: `packages/debate_cli/tests/commands/test_doctor.py` (new);
  `tests/scripts/test_install_channel.py` (uv shim, Requires-Python in the synthetic wheels, a
  stand-in doctor, 16 new tests); `tests/architecture/test_single_interpreter_source.py` (new);
  `tests/scripts/test_validate_dev.py` (the expected installer line); `packages/debate_cli/tests/test_app.py`
  (the Python check reads debate_core's metadata); `tests/smoke/test_cli_smoke.py` (Deviation 4).
* **`scripts/validate_dev.py`, `.github/workflows/dev-prerelease.yml`**: pass `--no-path-warning`.
* **`pyproject.toml`, `packages/{debate_api,debate_cli,debate_workers}/pyproject.toml`**:
  `requires-python` equal to debate_core's. Removed ruff's `target-version` and pyright's
  `pythonVersion`; both now infer 3.12 (Deviation 3).
* **Docs**: `docs/runbooks/caselist-scheduled-sync.md` ("Checking an installed build");
  `packages/debate_cli/README.md` (`doctor` section and exit table); `README.md`,
  `docs/evidence/normalization.md`, `docs/architecture/architecture_proposal.md`, and a comment in
  `debate_core/application/snapshot_service.py` (Deviation 2).
  In the runbook I also moved two trailing `#` comments out of the `caselist runs` block and into
  the prose. They were there before this task, and pasted into zsh they become arguments (working
  agreement 9).
* **`plan_specs/…/t14-install-interpreter-bound.yaml`**: `constraints.packages` amended with the
  PM's comment; Goal `Succeeded`.

## Deviations from the spec

1. **A public accessor in debate_core**, outside the spec's packages, chosen by the PM in this
   session. `debate_core` exposed the pin only through `character_rules()`, which raises
   `UnicodeDatabaseMismatchError` on exactly the interpreter doctor has to diagnose.
   `pinned_unicode_version(version)` reads the pin without the database check, and an unknown
   version is still refused. `_definition` and the new function share one lookup (`_registered`),
   so the table is read in one place, and nothing else changed. Tests:
   `test_chars_the_pin_can_be_read_under_the_database_it_refuses` and
   `test_chars_the_pin_of_an_unknown_version_is_refused_not_defaulted`.
2. **Stale mentions edited to point at debate_core's `requires-python`** (PM's instruction):
   * `README.md`: "Python 3.12 (pinned in `.python-version`)".
   * `docs/evidence/normalization.md`: the bullet that quoted the bound and said the script passes
     `--python 3.12`, which would now be false. It now says the script reads the specifier and
     doctor exits 1 on a mismatch.
   * `docs/architecture/architecture_proposal.md`: the "Python 3.12+" row, which implied 3.13
     works.
   * `snapshot_service.py`: the comment "requires Python <3.13"; comment only.

   ADR-0001's "3.12+" stays as written and is exempted by name.
3. **The workspace pyprojects and tool settings.** The other four `requires-python` lines (root,
   debate_api, debate_cli, debate_workers) were `>=3.12`. They are now debate_core's exact string,
   which the PM's rule requires. Two further statements surfaced in `pyproject.toml` that the
   brief did not list: ruff's `target-version = "py312"` and pyright's `pythonVersion = "3.12"`.
   I removed both. ruff now infers its target from `requires-python`
   (`linter.unresolved_target_version = 3.12`, unchanged), and pyright from the `.venv` that
   `uv sync` builds from `.python-version`. Both stay clean. `uv.lock` is unchanged, because its
   `requires-python` was already the intersection.
4. **One assertion added to `tests/smoke/test_cli_smoke.py`**, not in the package list. Working
   agreement 5 asks a task that changes a user-facing surface to update its smoke check. doctor's
   check now also asserts `unicode_database_matches` and that the two versions are equal, so every
   validate-dev run states that the published build runs on its pin. It passed against the
   installed dev916 build.
5. **`constraints.packages`.** The PM's list ("packages/debate_cli: commands, the installation
   module, tests"; "docs: runbooks and the README exit table") is written as entries under the
   comment "added on the PM's instruction, 2026-10-02". The second group (Deviations 1–3) is under
   the same comment, with a note that it came from the session's scope questions.

## Decisions and assumptions

1. **The specifier is passed as written**, `>=3.12, <3.13` with its space. uv 0.11.7 accepts it,
   checked with a real install. The runners' uv is not pinned (`astral-sh/setup-uv@v10.2.0`
   installs the latest), so the first proof on the runner's uv is the dev-prerelease run after
   this merges (operator follow-up 2).
2. **Only the METADATA header is read**: everything up to the first blank line, with CR stripped.
   A `Requires-Python:` line in the long description is not metadata, and a test shows it refused.
3. **The refusals overlap on purpose.** The specifier-character check would also refuse an empty
   value, and a swallowed unzip failure ends up refused as "no Requires-Python". Mutation tells
   these checks apart from their absence only by message. I kept them because each failure then
   names its real cause ("could not read METADATA" is not "states no Requires-Python"), not
   because they protect anything the next check would miss. Removing them would leave the install
   equally safe and the messages vaguer. The checks that stand alone are "stated twice" and "not a
   specifier": without them, uv is asked to install.
4. **After the rehearsal, the real install repeats every check.** uv cannot move a tool
   environment, because shebangs and `pyvenv.cfg` hold absolute paths, so the real install is a
   second `uv tool install` from the same verified wheels and uv's warm cache. Re-checking it means
   the exit status describes the install that is actually there. The limit: if a check passes in
   the rehearsal and fails on the real install, the real install has already been replaced. That
   needs the two installs to resolve differently, for example when a third-party release lands on
   PyPI between them, seconds apart. Follow-up work proposes closing it.
5. **doctor's exit codes.** 0 healthy. 1 (`DOMAIN_FAILURE`) on the mismatch only, the outcome
   "the answer is a failure, and running again gives the same answer". 70 when the pin cannot be
   determined at all: `pinned_unicode_version` raises `UnknownNormalizerVersionError`, a
   `NormalizationError`, not a `DomainError`, so the root handler reports it as `INTERNAL_ERROR`
   with "This is a bug in debate-research", and `install_channel.sh` refuses the build. JSON gets
   one envelope, with the whole report under `error.details` on a failure. A person gets the
   table, then a panel naming the two versions.
6. **doctor runs in its human form during the install**, so a person reading the log sees the
   table and the panel. The script acts on the exit status only.
7. **What ac4's scanner counts, and what it permits.**
   * **What counts:** `3.8`–`3.19`, alone or with a patch number, and the tags `py3XY`/`cp3XY`.
     `py3-none-any`, `boto3 1.43.12`, `0.3.12` and `13.12` are not counted. Every case is a test,
     built from integers so the test file states no version.
   * **Permitted by rule:** debate_core's declaration and workspace copies equal to it;
     `.python-version`; `uv.lock`; a `python-version:` key in a workflow (the CI matrix; none
     exists today); session reports, plan specs and `ROADMAP.md` as records; other ecosystems'
     lockfiles (`site/pnpm-lock.yaml` has `js-yaml@3.15.2`); and the scanner's own file, which
     quotes the lines it exempts.
   * **Exempt by exact line, with reasons:** ADR-0001; two sentences in the normalization policy
     stating which CPython ships the pinned database; the CPython-to-Unicode table in
     `test_normalization.py`; five sample `3.12.7` values in `test_output.py` and the CLI README's
     sample envelope; and the seven PEP 723 headers, left as they are.
   * A changed exempt line is a new line, and an exemption that matches nothing fails.
8. **`test_app.py` checks the interpreter with `packaging`**, which is not declared directly but
   comes with pytest, a hard dependency of the test environment.
9. **uv's own "not on your PATH" warning** still appears for the rehearsal's temporary bin
   directory. It is uv's message, not the script's, and `--no-path-warning` does not touch it. uv
   0.11.7 has no option to turn it off for one install.

## Operator follow-ups

**0. Full suite** — DONE by the operator: `4151 passed, 1 skipped in 70.96s` (see Whole-repo checks).

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t14-install-interpreter-bound
git branch --show-current
uv run pytest -q
```

`git branch --show-current` must print `task/v1-e01-t14-install-interpreter-bound`. Success: every
test passes, apart from the known skip (`tests/evals/parser/test_parser_eval.py`, "not yet
corrected by a person"). Paste the last 10 lines.

**1. After this merges to `dev`: the publish gate ran the new install** (~4 min after the merge;
dev-prerelease is this script's first run on Linux).

```bash
RUN=$(gh run list --repo charlesclark2/debate-intelligence --workflow dev-prerelease.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "${RUN}" --repo charlesclark2/debate-intelligence --json conclusion --jq .conclusion
gh run view "${RUN}" --repo charlesclark2/debate-intelligence --log | grep -E "on a Python matching|Unicode matches pin|The rehearsal passed|Installed debate-research|install_channel:"
```

Success:

* `success`;
* `on a Python matching '>=3.12, <3.13' (debate_core's Requires-Python)`;
* a `Unicode matches pin` row reading `yes`, twice (rehearsal and real install);
* `The rehearsal passed`;
* `Installed debate-research 0.1.0.devN from v0.1.0-dev.N`;
* **no** `install_channel:` line, because the PATH warning is silenced there.

If the step failed, nothing was published; paste its log. validate-dev then runs automatically, and
its smoke job's log should end `validate-dev smoke: passed`.

**2. Optional: move the launchd agent's build to the first pre-release containing this task.**
Run it any time after step 1, ideally before the agent's next Wednesday 06:00 run. The rehearsal guards it: if the build
fails any check, the script says `the installed debate-research was not touched` and the agent
keeps the build it has. Run it in one terminal.

```bash
cd ~
TAG=$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')
echo "${TAG}"
curl -fsSL "https://raw.githubusercontent.com/charlesclark2/debate-intelligence/${TAG}/scripts/install_channel.sh" -o "${TMPDIR}install_channel.sh"
grep -c "no-path-warning" "${TMPDIR}install_channel.sh"
sh "${TMPDIR}install_channel.sh" "${TAG}"
```

Check what you see:

* `echo` prints the tag from step 1.
* `grep -c` prints 1 or more, which shows the tag's script is this task's.
* The install prints `Rehearsing the install …` and `The rehearsal passed.`, then ends with
  `Installed debate-research … from ${TAG} at /Users/charlesclark/.local/bin/debate-research`.

A PATH warning here is expected only if `~/.local/bin` is not first on this shell's PATH. Then check
the build as the agent runs it (seconds):

```bash
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" sh -c 'command -v debate-research; debate-research --version; debate-research doctor >/dev/null; echo "doctor exit=$?"'
```

Success: `/Users/charlesclark/.local/bin/debate-research`, the new version, and `doctor exit=0`.
If the install ended with `the installed debate-research was not touched`, paste its output; the
agent is still on its previous build and nothing needs rolling back.

## Follow-up work

* **Close the window between rehearsal and replacement** (E01). Have the real install use exactly
  what the rehearsal resolved: write the rehearsal environment's `uv pip freeze` to a constraints
  file and pass it to the second `uv tool install` (`--constraints`). The two installs then cannot
  resolve differently (Decision 4).
* **ADR-0001 says "3.12+"**, which `debate_core`'s bound contradicts. It is exempt as a decision
  record, but the PM may want a short superseding note or a pointer from the ADR index.
* **One command for "is this installation sound".** doctor answers the interpreter question, and
  `python -m debate_cli.installation` answers the wiring question. The installer runs both. A
  person checking an install by hand runs doctor, which does not import the integrations.
  v1-e01-t17 suggested folding the import check into doctor. It would fit doctor's contract now:
  "an integration does not import" is a fact doctor can state precisely. It needs a decision on
  whether a failing import should be exit 1.
* **Hand-run uv installs are still possible.** Nothing stops `uv tool install --python 3.13` of
  our wheels (shown here, exit 0). The runbook says not to, and doctor catches it afterwards with
  exit 1. Refusing at import time would mean debate_cli checking the database on start-up, which is
  a separate decision.
* **uv's own PATH warning for the rehearsal directory** (Decision 9): harmless noise in every
  install log.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-07

**Notes:**

Accepted, phase `Succeeded`, with no code changes requested.

What makes this one trustworthy:

* **The real install was fingerprinted before and after,** read-only, and was unchanged.
* **ac3 was proved on a real build whose bound admitted 3.13,** which is the exact failure this task
  guards against.
* **The specifier is passed as written,** confirmed against a real uv.
* **Each mutant that was caught only through its message is explained** (Decision 3). The two
  checks that stand on their own ("stated twice", "not a specifier") are the ones that matter, and
  you said so.

Deviations and decisions:

* **Deviations 1 to 3 and 5:** accepted. They are what the PM's addendum authorised.
* **Deviation 4** (doctor's smoke assertion): accepted. Working agreement 5 is the right reason.
  I added `tests/smoke` to `constraints.packages` in this branch.
* **Decision 4 (the window between the rehearsal and the real install): accepted for now, and
  filed.** The real install's repeated checks mean the exit status is truthful. But a real install
  that fails those checks has already replaced the agent's build, which is what ac5 is meant to
  prevent. Filed as **v1-e01-t22-install-resolves-once**: pin the second resolution to the first
  (`--exclude-newer` from a timestamp taken before the rehearsal, or constraints from the rehearsal's
  resolution).
* **"One command for is this installation sound": decided yes, in t22.** "An integration the CLI
  wires does not import" is a fact doctor can state precisely, so it becomes exit 1 alongside the
  Unicode check.
* **Decision 7 (the scanner and its exemptions):** accepted. A changed exempt line counts as a new
  line, and an exemption that matches nothing fails the test. That keeps the list honest.
* **Decision 8** (`packaging` comes in through pytest): accepted.

**Not filed:**

* **ADR-0001's "3.12+".** It records the choice of Python, not a version bound, and it is exempt by
  name. The bound lives in the metadata now.
* **Refusing at import time on a hand-run uv install.** The normalizer already refuses at first use,
  and doctor names the mismatch.
* **uv's own PATH warning,** which is harmless noise.

`python3 scripts/validate_specs.py` on this branch, with t22 and its epic entry, reports
`OK: 308 files, 38 epics, 250 tasks, 20 releases`.

**Operator follow-ups:**

* **1** stands as written. It is the first time the script runs on the runner's uv.
* **2** is optional, and the next agent run is Wednesday 2026-10-14.
