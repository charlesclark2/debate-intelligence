# Session report: v1-e01-t22-install-resolves-once

| | |
|---|---|
| Task | `v1-e01-t22-install-resolves-once` — The real install is the build the rehearsal checked, and doctor answers for all of it |
| Spec | [`plan_specs/v1/e01-repo-foundation/t22-install-resolves-once.yaml`](../../plan_specs/v1/e01-repo-foundation/t22-install-resolves-once.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t22-install-resolves-once` |
| Session status | COMPLETE. Every criterion passed; the Goal is `Succeeded`. Follow-up 1 is the first run of the new script on the runner's uv, after the merge |

## Summary

**The real install is pinned to the rehearsal.** Once the rehearsal passes, `install_channel.sh`
runs `uv pip freeze` on the rehearsal environment. The two first-party `file://` lines are left out,
because their verified URLs still supply them. Every other line must be `name==version`, or the
script refuses before the real install. Those lines are passed to the real `uv tool install` as
`--constraints`. Afterwards the script freezes the real environment and requires it to equal the
rehearsal's. A test publishes `thirdparty-dep` 2.0 to a local index the moment the rehearsal ends.
The real install still gets 1.0. On the unchanged script the same test fails with `'2.0' == '1.0'`.

**doctor now fails when a wired integration does not import.** It calls
`debate_cli.installation.check_installation()`, the same logic as the installer's check, so there is
still only one list of modules: the one read from the container's imports. Each module that does not
import is named, with its reason, and doctor exits 1 with `INTEGRATIONS_DO_NOT_IMPORT`. If the
Unicode check fails as well, the code is `INSTALLATION_CHECKS_FAILED` and the message gives both.
A declared extra's missing distribution is reported (`extras_missing_distributions`) but stays
informational. `python -m debate_cli.installation` stays in the installer, because it is the check
that refuses such a build.

**Proved on a real build.** I stamped and built this branch's HEAD as dev-prerelease does
(`v0.1.0-dev.990`) and installed it in scratch directories. The script pinned 40 third-party
distributions, the two freezes matched, and it exited 0. validate-dev's smoke tier then ran
against that installed build: `27 passed`, including the new doctor assertions. With boto3 removed
from that scratch build, doctor exited 1 naming `debate_core.integrations.s3`, and the smoke check
failed. With only lxml removed, doctor exited 0 and reported `{'lxml': 'docx'}`, while
`python -m debate_cli.installation` exited 1 (`INCOMPLETE`).

**PM, look first at:**

* **Decision 1 (constraints, not `--exclude-newer`)**, and the one gap constraints leave: a new
  file for a version that is already pinned (Follow-up work).
* **Decision 3:** what happens if a future uv changes `--constraints`. Three cases, and the
  measured behaviour behind each.
* **Decision 6:** why `python -m debate_cli.installation` stays in the installer beside doctor.

## How the operator's real install was protected

* Every `uv tool install` ran in a pytest `tmp_path` or under `scratch.sh` in the session
  scratchpad. `scratch.sh` exports a scratch `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, strips `.venv` from
  PATH and exits 99 unless `uv tool dir` and `uv tool dir --bin` both resolve inside the
  scratchpad. The probes before the tests asserted the same in Python before installing.
* Before and after the session, read-only: SHA-256 of
  `~/.local/share/uv/tools/debate-cli/uv-receipt.toml` and of `~/.local/bin/debate-research`, the
  symlink target, one hash over every file in the tool environment (4,463 files) and the receipt's
  mtime (`1791354055`). `diff` of the two → `IDENTICAL`.
* The `uv pip uninstall` of boto3 and lxml ran with `--python` set to the scratch build's
  interpreter, after a guard that the path was inside the scratchpad.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `resolve-once` — One resolution for both installs, and a fuller doctor | Done | Pinning and its tests (ac1), doctor's integration check and its tests (ac2), the smoke assertion (ac3), docs. Each new test was run against the unchanged code first and failed for its reason. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — the real install resolves exactly what the rehearsal resolved; a test publishes a newer third-party release between the two installs to a local index; the real install keeps the rehearsal's version; shown failing without the change | **PASS** | **Test** `test_a_release_published_between_the_rehearsal_and_the_real_install_is_not_installed` (a `file://` PEP 503 index, no network). The uv shim runs a publish script at the first uv call outside the rehearsal's tool directory after one inside it, i.e. the moment the rehearsal ends. The script copies `thirdparty_dep-2.0` into the index and lists it. Asserts: exit 0, the publish ran and 2.0 is on the page, and the real tool environment imports `thirdparty_dep.VERSION == "1.0"`. **Shown failing without the change:** the same test on the unchanged script (`f17aa8f^`) → `AssertionError: assert '2.0' == '1.0'`. **Control** `test_control_an_unpinned_install_after_that_publish_takes_the_newer_release`: two plain installs around the publish → `("1.0", "2.0")`, so the publish is live. `test_only_the_real_install_is_pinned_and_to_what_the_rehearsal_installed`: no `--constraints` on the rehearsal, `--constraints` on the real install, and the receipt says `constraints = [{name = "thirdparty-dep", specifier = "==1.0"}]`. `test_a_uv_that_ignores_the_pins_is_caught_by_comparing_the_two_installs`: the shim drops `--constraints` → exit 1, `the real install is not the build the rehearsal checked`, `-thirdparty-dep==1.0`, `+thirdparty-dep==2.0`. `test_a_rehearsal_holding_something_that_cannot_be_pinned_is_refused_before_the_real_install` × 3 (a third-party URL, an editable, `debate-core==` from an index) → exit 1, `cannot be pinned`, names the line, only one `tool install` call. **uv** 0.11.7 (Homebrew 2026-04-15 aarch64-apple-darwin); the behaviour relied on is under Decision 2. **Real build:** `Pinning the real install to the 40 third-party distributions the rehearsal checked.`, `Resolved 42 packages`, freezes equal, exit 0, receipt holds 40 constraints. |
| **ac2** — doctor reports whether every wired integration imports and exits 1 naming each one that does not, beside the Unicode check; docstring, README exit table and runbook say so; every other fact informational; the installer still refuses an incomplete build; say what happens to `python -m debate_cli.installation` | **PASS** | `test_doctor.py`, 25 tests. Healthy checkout: `integrations_wired` equals the 7 modules written by hand, `integrations_failed == {}`, `integrations_import is True`. With `sys.modules` set to `None` for `s3` and `opencaselist` (the real import machinery raises): exit 1, `INTEGRATIONS_DO_NOT_IMPORT`, `2 of the 7 integrations`, both modules named with `ModuleNotFoundError: no module named '…'`, the whole report in `error.details`. For a person: the table, then a panel with `<module>: ModuleNotFoundError…` per module. Both checks failing → `INSTALLATION_CHECKS_FAILED`, with both versions, the policy page and both modules. A dynamic import in the container → exit 70. Informational, ×JSON and human, all exit 0: settings unconfigured, unknown versions, Python `2.7.18`, platform `Plan9`, no services, **missing extra distributions** (lxml, boto3), **nothing wired**. Property `test_doctor_fails_exactly_when_the_database_differs_or_an_integration_does_not_import`, fresh database, `--hypothesis-show-statistics`: `100 passing, 0 failing, 4 invalid`; events `an integration fails 35.58%`, `databases differ 51.92%`, `distributions missing 52.88%`, `settings not configured 25.96%`. **The installer still refuses an incomplete build:** `test_a_missing_extra_distribution_is_informational_here_and_refused_by_the_installers_check` (doctor 0, `installation.main([]) == 1`, `lxml (debate-core[docx])  MISSING`). The installer tests that make the check fail still pass. On the real build with lxml removed: doctor `ok True {'lxml': 'docx'}`, exit 0, and `python -m debate_cli.installation` → `INCOMPLETE`, exit 1. With boto3 removed as well: doctor exit 1, `1 of the 7 integrations debate-research wires do not import: debate_core.integrations.s3 (…)`. **Documented:** module docstring, `--help` (0/1/70, shown above), the CLI README (doctor section and its exit table, row 1 of the general table, "What an installed build resolved"), the runbook's "Checking an installed build" (what the installer checks, the pinning, doctor's exit table). **`python -m debate_cli.installation`** stays in the installer (Decision 6). |
| **ac3** — validate-dev's smoke check of doctor asserts the new fact on the installed build, and passes | **PASS** | `tests/smoke/test_cli_smoke.py::test_doctor_reports_the_builds_own_interpreter_and_every_service` now also asserts `integrations_import is True`, `integrations_failed == {}`, and that `s3` and `opencaselist` are among `integrations_wired`. Run validate-dev's way against the scratch-installed `v0.1.0-dev.990` built from HEAD `2c19926`: `DEBATE_SMOKE_BIN=<scratch>/tools-real/bin/debate-research DEBATE_SMOKE_EXPECT_SHA=2c19926… DEBATE_SMOKE_EXPECT_TAG=v0.1.0-dev.990 uv run --frozen pytest tests/smoke -m "not live and not in_process" -q --no-cov` → `27 passed in 8.93s`. **Shown failing:** with boto3 removed from that build, both doctor smoke checks fail (`INTEGRATIONS_DO_NOT_IMPORT` … `assert 1 == 0`). The first run in validate-dev itself happens after the merge (follow-up 1). |
| resolve-once: `uv run pytest tests/scripts/test_install_channel.py` | PASS | `35 passed in 10.51s` |
| resolve-once: `uv run pytest packages/debate_cli/tests/commands/test_doctor.py` | PASS | `25 passed, 10 warnings in 4.96s`. The warnings are pytest-socket blocking urllib3's import-time IPv6 probe (Decision 9). |
| Forbidden: touching the operator's real install | PASS | Fingerprint before and after identical (above). |
| Forbidden: a second resolution that can differ from the one the rehearsal checked | PASS, with one named gap | Every third-party version is pinned to the rehearsal's, and the two environments are compared afterwards. The gap: a new file for an already-pinned version (Decision 1, Follow-up work). |
| Forbidden: doctor failing on anything it cannot state precisely | PASS | Two failing checks, each naming what failed. Every other fact, missing distributions included, is shown not to fail (tests, property, mutants). |
| Forbidden: network access in the tests | PASS | Every index and wheel URL is `file://`; `UV_PYTHON_DOWNLOADS=never`, `UV_NO_CONFIG=1`, a temporary uv cache, as t14. The doctor tests run in-process under `--disable-socket`. urllib3 creating (never connecting) an IPv6 socket at import is blocked and handled (Decision 9). |

### Mutations

The runner (`mutate.py`, in the session scratchpad) applied each mutant to committed bytes and
asserted the replaced text occurred exactly once. Each run used a **new, empty
`HYPOTHESIS_STORAGE_DIRECTORY`**. The runner restored the original bytes and checked them by
SHA-256, and `git status --porcelain` was `''` after each batch. No attempt errored at collection;
every catch below is a test failure.

**Installer** (`tests/scripts/test_install_channel.py`, 35 tests). Batch: 75 s.

| Mutant | Result |
|---|---|
| The pin dropped from the real install | **Caught**: `test_a_release_published_between_…` (the real install took 2.0, so the comparison failed it: `-thirdparty-dep==1.0`, `+thirdparty-dep==2.0`, `assert 1 == 0`), `test_only_the_real_install_is_pinned_…` |
| The pin taken after the rehearsal: constraints from a fresh `uv pip compile` once the rehearsal has ended, not from the rehearsal's environment | **Caught**: `test_a_release_published_between_…` with `assert '2.0' == '1.0'` (checked on its own). Also 4 other tests, incidentally: the compile bypasses the shim's freeze line, and its list is not the rehearsal's |
| The installer skipping the integration check | **Caught**, 4 tests: `test_an_installed_build_whose_integration_check_fails_fails_the_install`, `…byte_for_byte_untouched[integration check]`, `test_every_check_runs_in_the_rehearsal_and_again_…`, `test_the_option_leaves_every_failure_as_it_was[integration check]` |
| No comparison of the two installs afterwards | **Caught**: `test_a_uv_that_ignores_the_pins_…` |
| Anything in the rehearsal accepted as pinnable | **Caught**: the 3 `cannot_be_pinned` cases |
| A first-party line from an index treated as third-party | **Caught**: `[first-party from an index]` |
| The rehearsal pinned too (`--constraints /dev/null`) | **Caught**: `test_only_the_real_install_is_pinned_…` |

**doctor** (`test_doctor.py`, `test_app.py`, `test_installation.py`, 82 tests). Batch: 41 s.

| Mutant | Result |
|---|---|
| doctor not reporting a missing integration | **Caught**, 4 tests, including the property |
| doctor failing on an integration that imports (every wired module treated as failed) | **Caught**, 20 tests, including the property and every informational case but `nothing_wired`, which has no modules to treat as failed |
| doctor failing on a missing extra's distribution | **Caught**: the property, `test_a_missing_extra_distribution_is_informational_…`, both `missing_extra_distributions` cases |
| Both checks failing reports only the first | **Caught**: `test_both_checks_failing_are_both_reported`, the property. My first version (`if failures:`) also failed a healthy doctor, so its 22 failures said nothing about this; I corrected it to `if len(failures) <= 2:` and re-ran the batch |
| The integration facts built from nothing instead of `check_installation` | **Caught**, 3 tests |
| The person's panel drops which integrations failed | **Caught**, 2 tests |
| An integration failure exits 70, not 1 | **Caught**, 3 tests, including the property |

### Whole-repo checks

* **Full suite**, run in the session (t14's operator run on this Mac took 71 s, so it was expected
  under two minutes): `uv run --frozen pytest -q` → `4196 passed, 1 skipped, 1 warning in
  68.66s`, and again `4196 passed … in 63.48s`. The skip is the parser eval
  (`tests/evals/parser/test_parser_eval.py:279`, "4 of 6 pr-subset files are not yet corrected
  by a person"). The warning is pytest-socket's deliberate one in
  `test_smoke_harness.py::test_pytests_own_process_has_no_network_in_an_offline_check`, as in t14.
  Total coverage 96%; `commands/doctor.py` 100%.
* `tests/scripts/test_validate_dev.py` → `70 passed`. `tests/smoke` (checkout) → `56 passed, 1
  warning` (the harness's).
* `ruff check .` → `All checks passed!`; `ruff format --check .` → `505 files already formatted`;
  `pyright` → `0 errors`; `lint-imports` → `Contracts: 11 kept, 0 broken.`;
  `check_thin_handlers.py` → `OK: 19 … within 25 statements`; `uv lock --check` → clean;
  `shellcheck scripts/install_channel.sh` → clean; `uvx --from actionlint-py actionlint` → clean;
  `check_links.py` → `OK: 1247 relative links and anchors in 168 Markdown files`;
  `tests/docs` → `51 passed`.
* `uv run scripts/validate_specs.py` → `OK: 308 files, 38 epics, 250 tasks, 20 releases`.

## Files changed

* **`scripts/install_channel.sh`**: `install_and_check` takes an optional constraints file. After
  the rehearsal: freeze, refuse anything unpinnable, write the constraints, pin the real install,
  then compare the two freezes. Header steps 4 and 5 rewritten.
* **`packages/debate_cli/src/debate_cli/commands/doctor.py`**: four facts (`integrations_wired`,
  `integrations_failed`, `integrations_import`, `extras_missing_distributions`);
  `integration_failure`, `doctor_failure` (both checks together); per-module panel details; table
  rows; module docstring and `--help`.
* **`packages/debate_cli/src/debate_cli/installation.py`**: docstring only. doctor shares
  `check_installation`, and the docstring says why the installer runs both.
* **Tests**: `tests/scripts/test_install_channel.py` (the shim's three settings,
  `third_party_wheel`, `add_to_index`, 5 new tests, 7 cases); `packages/debate_cli/tests/commands/test_doctor.py`
  (6 new tests, two informational cases, the property widened); `tests/smoke/test_cli_smoke.py`
  (doctor's assertions).
* **Docs**: `packages/debate_cli/README.md`; `docs/runbooks/caselist-scheduled-sync.md`.
* **`plan_specs/…/t22-install-resolves-once.yaml`**: Goal `Succeeded`.

## Deviations from the spec

None. Every file is inside `constraints.packages`.

## Decisions and assumptions

1. **Constraints from the rehearsal's environment, not `--exclude-newer`.** I measured both with
   uv 0.11.7 before choosing:
   * **What each one pins to.** Constraints are read from the environment every check ran
     against, so they describe the checked build by construction. `--exclude-newer T` describes a
     moment, and relies on the index telling the same story about that moment twice.
   * **Clocks.** `T` comes from the local clock, and uv compares it with the index's upload times.
     If the Mac's clock runs ahead of PyPI's, a file uploaded after the rehearsal resolved can have
     an upload time before `T`. The real install then admits it, and nothing says so. Constraints
     involve no clock.
   * **Index metadata.** Against a `file://` index without upload times, `--exclude-newer` dropped
     every file, even with a cutoff of 2030, and the install failed. Against a find-links directory
     it was ignored: a 2020 cutoff, and the file installed anyway. So an index or mirror without
     PEP 700 upload times fails every install, and a find-links source is silently unpinned.
     Constraints behave the same whatever the source.
   * **Testability did not decide it.** uv 0.11.7 reads a non-standard `data-upload-time`
     attribute from a local HTML index (a 2018 cutoff excluded a file stamped 2019), so either
     option could be tested offline.
   * **What constraints give up.** They pin versions, not files. Suppose a project adds a wheel to
     a release that is already pinned (a platform wheel uploaded after the sdist) between the two
     installs. The real install could pick that file, and the freeze comparison would not see it,
     because the version is the same. `--exclude-newer`, with a correct clock, would exclude it.
     This gap is far narrower than the one t14 named (any new release), but it is not zero; see
     Follow-up work. Both first-party wheels still come only from the verified `file://` URLs:
     they are left out of the constraints, and the provenance check is unchanged.
2. **The uv behaviour this relies on, measured with uv 0.11.7 (Homebrew 2026-04-15
   aarch64-apple-darwin).**
   * `uv pip freeze --python <env>` prints `name==version` for an index install and
     `name @ file://…` for a URL install. `--quiet` drops the "Using Python … environment at"
     line, and errors still print (a missing interpreter → `error: No virtual environment …`, exit 2).
   * `uv tool install --constraints` holds the resolution. In a probe the unpinned second install
     got 2.0 and the pinned one 1.0, with the URL requirements unaffected.
   * The receipt records the pins by content (`constraints = [{ name = "thirdparty-dep",
     specifier = "==1.0" }]`), not by the temporary file's path.
   * An unsatisfiable constraint → exit 1, and an existing tool environment is untouched: a hash
     over every entry's name, mtime and size was the same before and after, and it still imported 1.0.
3. **If a future uv changes `--constraints`.** The runners' uv is unpinned (`setup-uv@v10.2.0`
   installs the latest).
   * **Removed or renamed:** uv rejects the option before doing anything. Measured: `error:
     unexpected argument …`, exit 2, and the tool environment's hash unchanged. The rehearsal passes
     and the real install fails, leaving the previous install in place. Every install fails loudly
     until the script is updated.
   * **Accepted but ignored or weakened:** the comparison after the real install fails the
     script and lists the differences. By then the real install has replaced the previous one, and
     the message says so. Before that reaches a person, the PR `ci` check runs `tests/scripts`
     (the default pytest selection) on the runner's latest uv, and
     `test_a_release_published_between_…` and `test_a_uv_that_ignores_the_pins_…` would fail
     there. dev-prerelease runs the same script into scratch directories, so a failure there
     stops a publish rather than replacing anyone's install.
   * **The freeze format changed:** any line that is not `name==version` or a first-party URL line
     makes the script refuse before the real install, with nothing touched.
4. **The comparison after the real install.** Asking uv for something does not show that uv did
   it. The rehearsal's freeze and the real install's freeze must be byte-for-byte equal, including
   the two first-party URL lines, which both installs take from the same URLs. It runs after the
   real install's checks, so it only makes the exit status true; the pins are what keep the two
   the same. On the real build, the two freezes of 42 lines matched, so it raised no false alarm.
5. **When the test publishes.** "Between the rehearsal and the real install" is taken as early as
   possible: at the first uv call after the rehearsal ends, which is the rehearsal's freeze. That
   is what lets the test catch "the pin taken after the rehearsal". The constraints analogue of a
   late timestamp is constraints from a resolution made after the rehearsal rather than from its
   environment. Publishing just before the real install's `tool install` would let that mutant
   through.
6. **`python -m debate_cli.installation` stays as a separate step in the installer.** doctor now
   answers "does every wired integration import", but the PM's rule keeps every other fact
   informational, including a declared extra's missing distribution, and the installer must still
   refuse that. The module's `main` is the check that does. So both run, in the same order as
   before: the installation check, then doctor. Every caller:
   * **`install_channel.sh`**: unchanged, in the rehearsal and again after the real install.
   * **`.github/workflows/dev-prerelease.yml`** and **`scripts/validate_dev.py`**: they reach it
     only through `install_channel.sh`; unchanged.
   * **`debate_cli/app.py`**: imports `incomplete_installation_failure`, not the check; unchanged.
   * **`packages/debate_cli/pyproject.toml`**'s comment, `debate_cli/container.py`'s docstring and
     `docs/process/branching-and-environments.md`: still accurate; unchanged.
   * **`installation.py`'s docstring, the CLI README and the runbook**: updated to say doctor
     shares the check, and which of the two refuses what.
7. **doctor's report and failures.**
   * One failure keeps its own code. Both at once are `INSTALLATION_CHECKS_FAILED`, with both
     messages and both hints, so a program can tell which checks failed from `error.code` plus the
     report in `error.details`.
   * A person's panel lists each failing module as `module: reason`, and the two Unicode versions
     when they differ.
   * `UnfollowableWiring` (a dynamic import in the container) is exit 70, as a bug. doctor cannot
     say whether the integrations import, and it is not a fact about this installation.
   * A container that wires nothing is informational: there is nothing that fails to import, and
     the installer's check already refuses it as not covered.
   * doctor now imports every integration, boto3 included. A warm `debate-research --json doctor`
     takes 0.38–0.40 s here.
8. **What the freeze parser refuses.** Any line that is not `debate-cli @ …`, `debate-core @ …`
   or `name==version` (PEP 503 name; version characters `[A-Za-z0-9.!+_-]`), and any `debate-cli`
   or `debate-core` line in another form. A first-party line from an index cannot happen past the
   provenance check, but if it ever appeared it must not become a constraint.
9. **pytest-socket warnings from urllib3.** Importing botocore imports urllib3, which creates (and
   never connects) an IPv6 socket at import time to probe for support (`_has_ipv6("::1")`).
   pytest-socket blocks it with a warning, and urllib3 treats the refusal as "no IPv6". The doctor
   tests now import the integrations, so the warning appears once per worker in
   `test_doctor.py`. `test_installation.py` already did the same before this task: run alone, it
   shows `26 passed, 3 warnings`. No bytes leave the process. In the full suite the only warning
   left is the smoke harness's own.

## Operator follow-ups

**1. After this merges to `dev`: the publish gate ran the pinned install on the runner's uv.**
Run it 2–4 minutes after the merge, once dev-prerelease and validate-dev have finished.

```bash
RUN=$(gh run list --repo charlesclark2/debate-intelligence --workflow dev-prerelease.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "${RUN}" --repo charlesclark2/debate-intelligence --json conclusion --jq .conclusion
gh run view "${RUN}" --repo charlesclark2/debate-intelligence --log | grep -E "Pinning the real install|Integrations import|The rehearsal passed|Installed debate-research|install_channel:"
```

Success:

* `success`;
* `Pinning the real install to the N third-party distributions the rehearsal checked.`, with N
  around 40;
* an `Integrations import` row reading `yes`, twice;
* `The rehearsal passed.` and `Installed debate-research 0.1.0.devN from v0.1.0-dev.N`;
* **no** `install_channel:` line.

If the step failed, nothing was published; paste its log. Then check validate-dev's smoke job,
which now asserts the integrations on the published build:

```bash
VRUN=$(gh run list --repo charlesclark2/debate-intelligence --workflow validate-dev.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "${VRUN}" --repo charlesclark2/debate-intelligence --json conclusion --jq .conclusion
gh run view "${VRUN}" --repo charlesclark2/debate-intelligence --log | grep -E "passed|failed|validate-dev smoke"
```

Success: `success`, a smoke summary with no failures, and `validate-dev smoke: passed`.

**2. Optional: move the launchd agent's build to the first pre-release containing this task.**
Any time after step 1, ideally before the agent's next run on Wednesday 2026-10-14. The rehearsal
guards it as before, and now the real install is pinned to what the rehearsal checked. Run it in
one terminal.

```bash
cd ~
TAG=$(gh release list --repo charlesclark2/debate-intelligence --limit 1 --json tagName --jq '.[0].tagName')
echo "${TAG}"
curl -fsSL "https://raw.githubusercontent.com/charlesclark2/debate-intelligence/${TAG}/scripts/install_channel.sh" -o "${TMPDIR}install_channel.sh"
grep -c "Pinning the real install" "${TMPDIR}install_channel.sh"
sh "${TMPDIR}install_channel.sh" "${TAG}"
```

Check what you see:

* `echo` prints the tag from step 1.
* `grep -c` prints 1, which shows that the tag's script is this task's.
* The install prints `The rehearsal passed.`, then `Pinning the real install to the N third-party
  distributions the rehearsal checked.`, and ends with `Installed debate-research … from ${TAG} at
  /Users/charlesclark/.local/bin/debate-research`.

Then check the build as the agent runs it (seconds):

```bash
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" sh -c 'command -v debate-research; debate-research --version; debate-research doctor >/dev/null; echo "doctor exit=$?"'
```

Success: `/Users/charlesclark/.local/bin/debate-research`, the new version, and `doctor exit=0`,
which now also means every wired integration imports. If the install ended with `the installed
debate-research was not touched`, paste its output; the agent is still on its previous build. If it
ended with `the real install is not the build the rehearsal checked`, paste it too: the previous
build has been replaced, and the message lists how the two differ.

## Follow-up work

* **A new file for a version that is already pinned** (E01, for the PM to decide). Constraints
  pin versions, so a wheel added to an already-pinned release between the two installs could still
  be chosen by the real install (Decision 1). Closing it would mean pinning files as well as
  versions. Two ways: add `--exclude-newer` with a timestamp taken before the rehearsal (the
  option you asked me to choose against, used together with constraints), or compare the installed
  wheels' tags (`*.dist-info/WHEEL`) before trusting the real install. The window is the seconds
  between the two installs, and the build differs only in packaging, not in released source.
* **The reason given for an unnamed `ModuleNotFoundError` names more than it should** (E01).
  `installation._import_failure` names every absent optional distribution, not just the one the
  integration needs. On the real build with boto3 and lxml both removed, doctor said
  `debate_core.integrations.s3 (ModuleNotFoundError: needs boto3 (debate-core[aws]), lxml
  (debate-core[docx]))`, though the S3 adapter needs only boto3. This is v1-e01-t17's logic, and I
  reused it as the brief asked. It could map each integration to its extra.
* **uv's own "not on your PATH" warning** for the rehearsal's temporary bin directory is still in
  every install log, as t14 noted.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
