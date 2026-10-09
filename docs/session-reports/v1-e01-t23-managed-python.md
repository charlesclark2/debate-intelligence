# Session report: v1-e01-t23-managed-python

| | |
|---|---|
| Task | `v1-e01-t23-managed-python` — The installed build runs on a Python that uv manages |
| Spec | [`plan_specs/v1/e01-repo-foundation/t23-managed-python.yaml`](../../plan_specs/v1/e01-repo-foundation/t23-managed-python.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t23-managed-python` |
| Session status | PARTIAL. ac1–ac3 and the node criterion pass. ac4 is the operator's reinstall of the agent's build after its 2026-10-14 run, so it is NOT RUN and the Goal stays `InProgress`. Merge with `scripts/task pr --partial` |

## Summary

**Both installs now ask uv for a Python it manages.** The rehearsal and the real install both run
`uv tool install --force --managed-python --python "${REQUIRES_PYTHON}" …`. debate_core's
Requires-Python is still passed as `--python`, and t22's `--constraints` is unchanged. uv
0.11.7 (Homebrew 2026-04-15) has the option. It first appeared in **uv 0.6.8**: uv 0.6.6 and 0.6.7
reject it with `error: unexpected argument '--managed-python' found`, exit 2, before installing
anything. The script asks uv first (`uv --managed-python --version`) and refuses an older uv by
name, with nothing installed. After each install it checks that the tool environment's base Python
lies inside `uv python dir`, so a uv that accepts the option and then ignores it is caught in the
rehearsal.

**Why anaconda won, measured.** It was not PATH order. A managed 3.12.13 has been in
`~/.local/share/uv/python` since June, and with anaconda only first on PATH, uv's default already
picks it. What beats it is the activated conda base environment that `conda init` leaves in every
shell (`CONDA_PREFIX=~/anaconda3`, `CONDA_DEFAULT_ENV=base`). uv considers that environment before
its own installations. `uv python find --system '>=3.12, <3.13'` gives `~/anaconda3/bin/python3`
as the shell is, the managed one with `CONDA_PREFIX` unset, and the managed one with
`--managed-python`. A satisfying Python only on PATH does win in one case: when no managed one is
installed. Both cases are tested.

**ac2: uv downloads one, and the installer says so.** When `uv python find --managed-python` finds
nothing, the script prints `No Python that uv manages matches '…' yet, so uv will download one into
<uv python dir>.` It then leaves the download to uv, with no refusal path, as decided. Done for real
in scratch directories with this shell's anaconda base still active: `Downloading
cpython-3.12.13-macos-aarch64-none (download) (16.9MiB)`, then the whole install, rehearsal and real
install, in 9 s, exit 0. On its own the download takes 0.96 s and 1.45 s from an empty cache.

**doctor reports, and never fails on, whether uv manages its Python.** It has three new facts:
`python_base_prefix` (`sys.base_prefix`), `uv_python_directory` (what `uv python dir` would print,
worked out from doctor's own environment) and `python_uv_managed` (the first lies strictly inside
the second, with links followed on both sides). The runbook's "Checking an installed build" says
why this matters for the agent: a conda or Homebrew update can no longer change its interpreter.

**PM, look first at:**

* **Decision 1, the check after each install.** It is a refusal, but only of a build already on an
  unmanaged Python, which the forbidden list rules out. It is not a refusal to download. Mutation
  shows it is the only check that catches a uv ignoring the option.
* **Decision 3, the stand-in test sets conda's variables as well as PATH.** With PATH alone, uv
  already picks a managed Python when one exists, so a PATH-only test would pass on the old script.
* **Decision 5: doctor answers from its own environment.** A build installed with a
  `UV_PYTHON_INSTALL_DIR` that doctor's environment lacks shows `no`. That happened with my scratch
  build. The agent's real install uses the default directory, so for the agent the answer is right.

## How the operator's real install was protected

* Every real `uv tool install` ran in a pytest `tmp_path` or under `scratch.sh` in the session
  scratchpad. `scratch.sh` exports scratch `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR` and
  `UV_PYTHON_INSTALL_DIR`, strips `.venv` from PATH, and exits 99 unless `uv tool dir`,
  `uv tool dir --bin` and `uv python dir` all resolve inside the scratchpad. The proof run logged
  all three. The old-uv probes ran through `uvx` with a scratch `UV_CACHE_DIR`, `UV_TOOL_DIR` and
  `UV_TOOL_BIN_DIR`.
* The tests use the real managed-Python directory (or the runner's `UV_PYTHON_INSTALL_DIR`) only to
  *find* a managed 3.12 (`uv python find`, with downloads off) and to create tool environments
  in `tmp_path` from it. Nothing is installed into or removed from that directory.
* Before and after the session, read-only, `fingerprint.sh` in the scratchpad recorded:
  * the SHA-256 and mtime (`1791426128`) of `~/.local/share/uv/tools/debate-cli/uv-receipt.toml`;
  * the `~/.local/bin/debate-research` link and the SHA-256 of its target;
  * the tool's `bin/python` link (`/Users/charlesclark/anaconda3/bin/python3`);
  * one hash over every file in the tool environment (4,555 files);
  * a hash over the names and mtimes of `~/.local/share/uv/python`'s entries;
  * the SHA-256 of the agent's plist and of its copied wrapper.

  `diff` of the two → `IDENTICAL`. The agent was never loaded, run or edited.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `managed-python` — A uv-managed interpreter for the installed build | Done | Installer tests written and committed first (`b1b21d9`), then shown failing against the unchanged script: 5 failed, 36 passed. Then the script. Doctor tests were written and shown failing (11 failed, 29 passed) before doctor changed. Then the README and the runbook. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — both installs use a Python uv manages, through uv's own option, still matching debate_core's Requires-Python; a test puts a satisfying unmanaged Python first on PATH and shows the installed tool's interpreter is not it; the script states the option and what a uv without it does; shown failing first | **PASS** | **Option:** `--managed-python`, on both `uv tool install` calls, beside `--python "${REQUIRES_PYTHON}"`. Confirmed in `uv tool install --help` on **uv 0.11.7 (Homebrew 2026-04-15 aarch64-apple-darwin)**: `--managed-python  Require use of uv-managed Python versions [env: UV_MANAGED_PYTHON=]`. **Stand-in:** a copy of the managed 3.12 outside uv's directory (executable, libpython, standard library; 32 MB, 0.43 s to copy), put first on PATH with `CONDA_PREFIX`/`CONDA_DEFAULT_ENV=base`, as `conda init` leaves a shell. **Tests** (`tests/scripts/test_install_channel.py`): `test_a_conda_python_first_on_path_is_not_the_python_the_build_runs_on` (exit 0; `bin/python` resolves inside the managed installation, not the stand-in), with `test_control_without_the_option_uv_installs_on_that_conda_python` (the same install without the option resolves into the stand-in, so the stand-in is live). `test_both_installs_ask_uv_for_a_python_it_manages`. `test_a_uv_without_the_option_is_refused_before_anything_is_installed` (the shim rejects the option as uv 0.6.7 does → exit 1, names `--managed-python` and `uv 0.6.8`, no `tool install` call). `test_a_uv_that_ignores_the_option_is_caught_in_the_rehearsal` (exit 1, `which is not a Python uv manages`, names the stand-in, `not touched`, one install only). **Failing first**, against the unchanged script (tests at `b1b21d9`): 5 failed, 36 passed. The conda test failed with `AssertionError: PosixPath('…/anaconda3/bin/python3.12')`; the two refusal tests with `assert 0 == 1`; the option test because neither call had it; the ac2 test on the missing notice. The control passed. **The script states it:** header step 3a names `--managed-python`, why it is needed (conda's base environment comes first), uv 0.6.8 as the first version with it, and what an older uv does. **Measured** with uv 0.6.6 through `uvx`: `error: unexpected argument '--managed-python' found`, exit 2, and the scratch tool directory held only uv's `.gitignore` and `.lock`. uv 0.6.7 lacks the option, 0.6.8 has it. **Real build** (`v0.1.0-dev.991` from `c77c166`, this shell's anaconda base active): `The build runs on the Python at <scratch>/pythons/cpython-3.12.13-macos-aarch64-none, which uv manages.`, twice; `Managed by uv │ yes`, twice; the tool's `pyvenv.cfg` `home = <scratch>/pythons/cpython-3.12-macos-aarch64-none/bin`. |
| **ac2** — with no managed Python installed, the installer obtains one through uv and says so, or refuses with the command that installs one; choose and say why | **PASS** | **Chosen: uv downloads one, and the installer says so** (the PM's decision; Decision 2). **Test** `test_with_no_managed_python_uv_is_left_free_to_download_one_and_the_installer_says_so`. It uses an empty `UV_PYTHON_INSTALL_DIR`, no `UV_PYTHON_DOWNLOADS` in the script's environment, and the stand-in first on PATH. It asserts: the notice `No Python that uv manages matches '…' yet` and `uv will download one into <that directory>`; for every `tool install` call, the shim recorded `UV_PYTHON_DOWNLOADS` as left by the script (`unset`, never `never`), `--managed-python` present and `--no-python-downloads` absent; and uv's error `in managed installations`, so uv did not fall back to the stand-in. The shim then sets `UV_PYTHON_DOWNLOADS=never` itself, so the test stays offline, exits 1 and installs nothing. Against the unchanged script it failed on the notice. That script had installed the build, exit 0, on the PATH stand-in. **Real download**, in scratch: `Downloading cpython-3.12.13-macos-aarch64-none (download) (16.9MiB)`, then the full install, exit 0, in 9 s. The download alone, from an empty cache, took 0.96 s and 1.45 s. With `UV_PYTHON_DOWNLOADS=never` set by a caller, uv refuses, and the script's message gives `uv python install '<specifier>'`. |
| **ac3** — doctor reports whether the running interpreter is uv-managed, informationally; the runbook's "Checking an installed build" says why it matters for the agent | **PASS** | **How it is decided** (Decision 4). The directory is `UV_PYTHON_INSTALL_DIR` when it is set and not empty, against the working directory if relative. Otherwise it is `$XDG_DATA_HOME/uv/python` when `XDG_DATA_HOME` is absolute, otherwise `$HOME/.local/share/uv/python`. Windows uses `%APPDATA%\uv\data\python`, from uv's documentation and not measured. The Python is managed when `realpath(sys.base_prefix)` lies strictly inside `realpath(directory)`, compared by path components. **Tests** (`packages/debate_cli/tests/commands/test_doctor.py`, 40): `test_doctor_reports_whether_its_python_is_one_uv_manages_and_exits_0_either_way`, three cases: inside uv's directory → `true`, anaconda → `false`, Homebrew → `false`. Each exits 0 in JSON and for a person, and the table shows `Managed by uv │ yes/no`. `test_the_managed_fact_follows_links_and_compares_whole_path_components`: uv's minor-version link → managed; a link out of uv's directory into anaconda → not managed; a link from elsewhere into uv's → managed; uv's directory reached through a link → managed; a sibling `python-elsewhere` → not; the directory itself → not. `test_uvs_python_directory_is_found_as_uv_finds_it`, 5 cases written by hand from `uv python dir`'s output, plus the relative and Windows cases. Informational: `unmanaged_python` and `managed_python` × JSON/human, exit 0. The property is widened to the three facts: fresh database, `--hypothesis-show-statistics`, `100 passing, 0 failing, 2 invalid`; events `python not uv-managed 20.59%`, `python managed other 77.45%`. **Failing first:** 11 failed, 29 passed. **Runbook:** "A Python uv manages, and why the agent needs one", the download paragraph, and doctor's three rows. **Real:** the scratch build said `yes` during its install. Run from this checkout (base `/Users/charlesclark/anaconda3`), doctor says `no` and exits 0. |
| **ac4** — operator: reinstall the agent's build in a week the agent is not due to run; record doctor showing a managed interpreter and the agent-environment check passing | **NOT RUN** | It needs the operator's real install and the merged pre-release, and it must wait until after the agent's run on Wednesday 2026-10-14. Operator follow-up 2. |
| `managed-python`: `uv run pytest tests/scripts/test_install_channel.py` | **PASS** | `41 passed in 14.18s` (35 before this task, 10.5 s per t22) |
| Forbidden: an installed build whose interpreter lies outside uv's managed-Python directory | **PASS** | The script refuses one after each install (Decision 1). Tests: the conda test and `…ignores_the_option…`. Mutants below. |
| Forbidden: network access in the tests | **PASS** | All index and wheel URLs are `file://`. The shim sets `UV_PYTHON_DOWNLOADS=never` on every uv call after logging what the script allowed. The `managed_python` fixture runs `uv python find` with downloads off. Every other setting is as in t22. The doctor tests run in-process under `--disable-socket`. |
| Forbidden: doctor failing on where its interpreter came from | **PASS** | Informational tests, the property, and three mutants that fail on an unmanaged Python, each caught. |
| Forbidden: touching the operator's real install in a session | **PASS** | Fingerprint before and after `IDENTICAL` (above). |

### Mutations

`mutate.py` in the scratchpad applies each mutant to committed bytes after asserting that the
replaced text occurs exactly once. It runs the tests with a **new, empty
`HYPOTHESIS_STORAGE_DIRECTORY`** each time, restores the bytes and checks them by SHA-256.
`git status --porcelain` was `''` after every batch. No attempt errored at collection; every catch
below is a test failure. Only `test_doctor.py` has a Hypothesis property; the installer tests have
none.

**Installer, the mutants the PM listed** (`tests/scripts/test_install_channel.py`, 41 tests). Batch: 60 s.

| Mutant | Result |
|---|---|
| The option dropped from the rehearsal (`${1:+--managed-python}`) | **Caught**, 3: `test_a_conda_python_first_on_path_…`, `test_both_installs_ask_…`, the ac2 test. The conda test fails through the new check: `…rehearsal…/tools runs on the Python at …/anaconda3, which is not a Python uv manages …`, then `the installed debate-research was not touched`, `assert 1 == 0` |
| The option dropped from the real install | **Caught**, 2: `test_a_conda_python_first_on_path_…`, `test_both_installs_ask_…`. The ac2 test cannot catch it: there the rehearsal stops offline before the real install |
| Downloads forced off: `--no-python-downloads` on the install | **Caught**: the ac2 test |
| Downloads forced off: `UV_PYTHON_DOWNLOADS=never` exported by the script | **Caught**: the ac2 test |

**Installer, three more of my own.** Batch: 46 s.

| Mutant | Result |
|---|---|
| No up-front refusal of a uv without the option | **Caught**: `test_a_uv_without_the_option_…`. uv's own rejection still stops the rehearsal, but the message no longer names the option or says nothing was installed |
| No check that the interpreter lies inside `uv python dir` | **Caught**: `test_a_uv_that_ignores_the_option_…`, the only test that catches it |
| No notice that uv will download one | **Caught**: the ac2 test |

**doctor** (`test_doctor.py` and `test_app.py`, 71 tests). Final batch on the committed code: 39 s.

| Mutant | Result |
|---|---|
| The managed fact always yes | **Caught**, 2: `…exits_0_either_way[anaconda]`, `[homebrew]` |
| The managed fact always no | **Caught**: `…exits_0_either_way[inside uv's directory]` |
| doctor fails an unmanaged Python, in `doctor_failure` | **Caught**, 28, including the property and both `unmanaged_python` informational cases. Most of the others fail because this checkout's own `.venv` is on anaconda, so here every in-process doctor run is "unmanaged" |
| The command exits 1 on an unmanaged Python, in `doctor()` (outside the property's reach) | **Caught**, 29, including both `unmanaged_python` informational cases |
| `base_prefix`'s links not followed | **Survived** in the first doctor batch, because every link in the test pointed within uv's directory. I added a link out of uv's directory into an anaconda stand-in (must be `no`) and a link from elsewhere into uv's (must be `yes`), committed in `8686df6`. Then **caught**, 1 |
| uv's directory's links not followed | **Caught**, 1 (added with the case above) |
| Compared as strings, not path components | **Caught**, 1: the sibling `python-elsewhere` |
| `UV_PYTHON_INSTALL_DIR` ignored | **Caught**, 5 |

The doctor batch ran three times. Before the link cases, 6 of 7 were caught. After them, 8 of 8.
After the version-free renames (`6511349`), 8 of 8 again. The table is the last run.

### Whole-repo checks

* **Default suite** (`uv run --frozen pytest -q`, fresh Hypothesis database) → `4301 passed, 1
  skipped, 1 warning in 100.52s`. The skip is the parser eval
  (`tests/evals/parser/test_parser_eval.py:279`, "4 of 6 pr-subset files are not yet corrected by
  a person"). The warning is pytest-socket's in the smoke harness, as in t14 and t22. Total coverage
  96%; `commands/doctor.py` 100%. The suite now takes 100 s here, close to the two-minute line
  (Follow-up work).
* `tests/scripts/test_validate_dev.py` → `70 passed`. `tests/smoke` (checkout) → `56 passed, 1
  warning`. `tests/docs` → `51 passed`. `tests/architecture` → passed, after the version-free
  renames below.
* **validate-dev's smoke tier against the scratch-installed build**:
  `DEBATE_SMOKE_BIN=<scratch>/proof/bin/debate-research DEBATE_SMOKE_EXPECT_SHA=c77c166… DEBATE_SMOKE_EXPECT_TAG=v0.1.0-dev.991 uv run --frozen pytest tests/smoke -m "not live and not in_process" -q --no-cov`
  → `27 passed in 5.16s`, doctor's smoke check included.
* `shellcheck scripts/install_channel.sh` → clean. `uvx --from actionlint-py actionlint` → clean.
  `ruff check .` → `All checks passed!`. `ruff format --check .` → `511 files already
  formatted`. `pyright` → `0 errors`. `lint-imports` → `Contracts: 11 kept, 0 broken.`.
  `check_thin_handlers.py` → `OK: 19 …`. `uv lock --check` → clean. `check_links.py` → `OK: 1258
  relative links and anchors in 171 Markdown files`. `docs_index.py --check-descriptions` → `All
  30 indexed documents under docs/ have a description`.
* `uv run scripts/validate_specs.py` → `OK: 309 files, 38 epics, 251 tasks, 20 releases`.
* **Paste safety:** no line with `#` in a shell block of the runbook's new text or of this report's
  operator follow-ups.
* **`scripts/task sync`**, run before this report: it rebased cleanly onto `origin/dev`, and pushed
  nothing because the branch is not on origin. dev had gained only the generated-files refresh
  (#176). `v1-e34-t11` has not merged, so there were no runbook changes of its to combine. Whichever
  of the two merges second rebases onto the other's runbook.

## The runners

* Every workflow that runs the installer first runs `uv python install` from `.python-version`.
  setup-uv sets `UV_PYTHON_INSTALL_DIR=/home/runner/work/_temp/uv-python-dir`. In the dev-prerelease
  run for `8ebbfa0` (run 37721196067), that step logged `Downloading
  cpython-3.12.15-linux-x86_64-gnu (download) (32.7MiB)` and `Installed Python 3.12.15 in 1.01s`.
  The installer's doctor then showed `Python 3.12.15`, so the runners were already on a managed
  Python.
* **So `--managed-python` adds no download on the runners** while `.python-version` and debate_core's
  bound agree. The new uv calls (`--version`, `python find`, `python dir` twice) take milliseconds.
  If the two ever disagree, the install downloads the matching Python itself, about 33 MB and 1 s
  going by the runner's own `uv python install`.
* **Baseline for follow-up 1:** dev-prerelease's "Install the build as its users will…" step took 6 s
  in both recent runs (03:07:29→03:07:35, 03:23:18→03:23:24). validate-dev's "Install the
  pre-release and run the smoke tiers…" step took 24 s.
* **validate-dev's smoke check of doctor** passed against the scratch-installed build (27 passed,
  above). I did not add a `python_uv_managed` assertion there (Decision 6).

## Files changed

* **`scripts/install_channel.sh`**: the `--managed-python` probe and refusal; `--managed-python`
  on the install in `install_and_check`; the check that the tool's base Python lies inside
  `uv python dir`, with its message; the download notice before the rehearsal; header step 3a and
  the uv version in "Needs".
* **`packages/debate_cli/src/debate_cli/commands/doctor.py`**: `uv_python_directory`,
  `is_uv_managed`; three facts and their table rows; the module docstring section "Whether uv
  manages this Python"; the Unicode hint names a Python uv manages.
* **Tests**: `tests/scripts/test_install_channel.py` (the shim's downloads log and its two new
  settings, conda variables stripped from the inherited environment, the stand-in builder, 6 new
  tests); `packages/debate_cli/tests/commands/test_doctor.py` (5 new tests, 2 informational cases,
  the property widened).
* **Docs**: `packages/debate_cli/README.md` (doctor section);
  `docs/runbooks/caselist-scheduled-sync.md` ("Checking an installed build").
* **This report.** The spec is unchanged; the Goal stays `InProgress` (ac4).

## Deviations from the spec

None. Every file is inside `constraints.packages`.

## Decisions and assumptions

1. **The installer checks what uv gave it, not only what it asked for.** The idea is t22's freeze
   comparison applied to the interpreter. After each install, the tool's `sys.base_prefix` and
   `uv python dir`, both with links followed (`cd -P` and `pwd -P`), must show the first strictly
   inside the second. Otherwise the script refuses, naming both. In the rehearsal that leaves the
   real install untouched. This is a refusal of a build on an unmanaged Python, which the forbidden
   list rules out, and not a refusal to download. Mutation shows it is the only check that catches
   a uv ignoring the option. It also catches the option dropped from the rehearsal in the conda
   test, which would otherwise pass, because the real install would still be managed.
2. **ac2: download, and say so.** This is the PM's decision. The agent never runs the installer, so
   a download only ever happens while someone is watching, and it takes a second or two.
   * The notice comes from `uv python find --system --managed-python --no-python-downloads`. That
     probe never downloads; uv makes the download itself, during the install.
   * The script never sets `UV_PYTHON_DOWNLOADS` and never passes `--no-python-downloads`.
   * A caller's `UV_PYTHON_DOWNLOADS=never` still holds. uv then refuses, and the script's message
     ends `(if downloads are off, \`uv python install '<specifier>'\` installs one)`.
3. **The stand-in, and why the test also sets conda's variables.** I measured with
   `uv python find --system '>=3.12, <3.13'` on uv 0.11.7:
   * an unmanaged 3.12 first on PATH, with a managed 3.12 installed → the managed one;
   * the same with `CONDA_PREFIX=<it>` and `CONDA_DEFAULT_ENV=base` → the unmanaged one;
   * the same with `--managed-python` → the managed one;
   * `CONDA_PREFIX` without `CONDA_DEFAULT_ENV=base` → the managed one;
   * the unmanaged one only on PATH and no managed one installed → the unmanaged one.

   So a PATH-only test with a managed Python installed would pass on the old script, and would not
   reproduce the coach's Mac. The ac1 test does what `conda init` does: the stand-in first on PATH
   and the base environment active. The ac2 test covers PATH alone with nothing managed installed.
   The stand-in is a copy of the managed interpreter made outside uv's directory. It is the same
   CPython in a different place, so it differs only in what uv decides by: where it is. The copy
   leaves out site-packages, `__pycache__`, `config-*` and `test`. **Not yet run on Linux.** It
   copies `lib/libpython*`, which covers python-build-standalone's Linux layout as I understand it.
   The PR's `ci` run is its first Linux run.
4. **How doctor decides, precisely.** The directory rules come from `uv python dir`'s output on
   uv 0.11.7:
   * `UV_PYTHON_INSTALL_DIR=/x/y` → `/x/y`;
   * `=rel` → `rel`, as given, which doctor reads against the working directory;
   * empty → the default;
   * `XDG_DATA_HOME=/xdg` → `/xdg/uv/python`;
   * `=relxdg` → ignored;
   * `HOME=/h` → `/h/.local/share/uv/python`;
   * `='~/tilde'` → `~/tilde`, printed literally. I did not measure whether uv expands `~` when it
     uses the value, so doctor does not.

   "Managed" means strictly inside, by path components, after `realpath` on both sides. So uv's
   minor-version link counts as managed, a name in uv's directory that links to anaconda does not,
   and `…/uv/python-elsewhere` does not. The comparison uses `sys.base_prefix`, not
   `sys.executable`, because the executable is the tool environment's own `bin/python`. The rule is
   uv's own (uv decides by location). It is not a guess from a directory name.
5. **doctor answers from its own environment.** For the agent's build that is the default directory,
   under the plist's `HOME`, with no `UV_PYTHON_INSTALL_DIR`, so the answer is right. A build
   installed with a custom `UV_PYTHON_INSTALL_DIR` shows `no` wherever that variable is not set.
   The scratch build did: `python_uv_managed: False` from my shell, `yes` inside its install. The
   runbook and the README say so. Since the fact never fails anything, this costs a misleading
   `no` in an unusual setup, never a failed run.
6. **No smoke assertion on `python_uv_managed`.** `tests/smoke` is outside this task's packages,
   and the PM asked only that validate-dev's doctor check keep passing, which it does. An assertion
   there would also depend on the runner passing `UV_PYTHON_INSTALL_DIR` through to the smoke tests'
   environment, which I have not checked (Decision 5). Follow-up work.
7. **"Only reinstalling the build changes the agent's interpreter" is nearly, not exactly, true.**
   uv points tool environments at its minor-version link: the scratch build's `pyvenv.cfg` says
   `home = …/cpython-3.12-macos-aarch64-none/bin`, a link to `cpython-3.12.13-…`. So
   `uv python upgrade` (a preview feature) moves the build to a newer 3.12 patch release, and
   `uv python uninstall` removes its interpreter. Both are uv commands someone runs on purpose, never
   a side effect of conda or Homebrew. A patch release within one minor version keeps the Unicode
   database. The runbook says exactly this.
8. **The installer tests now need a managed Python**, not just any 3.12. CI's `uv python install`
   provides one. Locally, the `managed_python` fixture fails, rather than skips, with "`uv python
   install` installs one", so a missing interpreter can't silently pass the suite. The inherited
   environment's conda variables, `UV_PYTHON`, `UV_MANAGED_PYTHON`, `UV_NO_MANAGED_PYTHON` and
   `UV_PYTHON_PREFERENCE` are stripped, so this session's activated anaconda no longer reaches the
   tests unless a test puts the stand-in there.
9. **The probe is `uv --managed-python --version`**, a global option on a command that does nothing.
   It was measured: exit 0 on 0.6.8 and 0.11.7, exit 2 with `unexpected argument` on 0.6.6. It
   doesn't depend on help-text formatting.
10. **Versions in doctor's test names.** `tests/architecture/test_single_interpreter_source.py`
    flagged the `cpython-3.12.13-…` style names I first used. They were incidental, so the
    installations are now named `cpython-patch-release-…`, `cpython-minor-version-link-…` and
    `cpython-really-anaconda-…`.

## Operator follow-ups

**1. After this merges to `dev`: the publish gate ran the new install on the runner's uv.** Run it
about 4 minutes after the merge, once dev-prerelease and validate-dev have finished. Each command
takes seconds.

```bash
SHA=$(gh pr list --repo charlesclark2/debate-intelligence --state merged --head task/v1-e01-t23-managed-python --json mergeCommit --jq '.[0].mergeCommit.oid')
RUN=$(gh run list --repo charlesclark2/debate-intelligence --workflow dev-prerelease.yml --commit "${SHA}" --json databaseId --jq '.[0].databaseId')
echo "${SHA} ${RUN}"
gh run view "${RUN}" --repo charlesclark2/debate-intelligence --json conclusion --jq .conclusion
gh run view "${RUN}" --repo charlesclark2/debate-intelligence --log | grep -E "which uv manages|Managed by uv|will download one|The rehearsal passed|Installed debate-research|install_channel:"
gh run view "${RUN}" --repo charlesclark2/debate-intelligence --json jobs --jq '.jobs[].steps[] | select(.name | startswith("Install the build")) | "\(.startedAt) \(.completedAt)"'
```

Success:

* `success`;
* `The build runs on the Python at /home/runner/work/_temp/uv-python-dir/cpython-3.12.…, which uv
  manages.`, twice;
* a `Managed by uv` row reading `yes`, twice;
* **no** `will download one` line: the runner's `uv python install` already provided it;
* `The rehearsal passed.` and `Installed debate-research 0.1.0.devN from v0.1.0-dev.N`;
* **no** `install_channel:` line;
* the step's two timestamps about 6 s apart, as before this task.

If the step failed, nothing was published; paste its log. Then validate-dev, whose smoke tier runs
doctor's smoke check on the published build:

```bash
VRUN=$(gh run list --repo charlesclark2/debate-intelligence --workflow validate-dev.yml --commit "${SHA}" --json databaseId --jq '.[0].databaseId')
gh run view "${VRUN}" --repo charlesclark2/debate-intelligence --json conclusion --jq .conclusion
gh run view "${VRUN}" --repo charlesclark2/debate-intelligence --log | grep -E "passed|failed|validate-dev smoke"
```

Success: `success`, a smoke summary with no failures, and `validate-dev smoke: passed`. Run both
blocks in the same terminal, because the second uses `SHA`.

**2. ac4: move the agent's build to the first pre-release containing this task, and check it.**
Run it on **Wednesday 2026-10-14 after the agent's 06:00 run has finished**, or on any later day up
to Tuesday 2026-10-20 afternoon. **Never between Tuesday evening and Wednesday 06:00.** Run
everything in one terminal; each block takes seconds.

First, check that the agent is not running, and record the build's interpreter as it is now:

```bash
launchctl print gui/$UID/com.debate-intelligence.caselist-sync | grep -E 'state =|runs =|last exit code ='
readlink ~/.local/share/uv/tools/debate-cli/bin/python
```

Expected: `state = not running`, and `runs` and `last exit code` from the Wednesday run. If `state`
says `running`, wait and repeat. `readlink` should print `/Users/charlesclark/anaconda3/bin/python3`,
which is the "before".

Then install the pre-release built from this task's merge commit:

```bash
cd ~
SHA=$(gh pr list --repo charlesclark2/debate-intelligence --state merged --head task/v1-e01-t23-managed-python --json mergeCommit --jq '.[0].mergeCommit.oid')
TAG=$(gh api repos/charlesclark2/debate-intelligence/releases --jq ".[] | select(.body | contains(\"${SHA}\")) | .tag_name")
echo "${SHA} ${TAG}"
curl -fsSL "https://raw.githubusercontent.com/charlesclark2/debate-intelligence/${TAG}/scripts/install_channel.sh" -o "${TMPDIR}install_channel.sh"
grep -c -- "--managed-python" "${TMPDIR}install_channel.sh" && sh "${TMPDIR}install_channel.sh" "${TAG}"
```

Check what you see:

* `echo` prints the merge commit and **one** tag, the one follow-up 1's log named. If it prints no
  tag, stop and paste the output: that commit's build was not published.
* `grep -c` prints a number above 0, which shows the tag's script is this task's. If it prints 0,
  nothing is installed.
* The install prints `The build runs on the Python at
  /Users/charlesclark/.local/share/uv/python/cpython-3.12.…-macos-aarch64-none, which uv manages.`
  twice, `The rehearsal passed.`, and ends `Installed debate-research … from <tag> at
  /Users/charlesclark/.local/bin/debate-research`.
* There should be no download: a managed 3.12 is already installed. If the script says `uv will
  download one`, that is fine too.

Then check the build as the agent runs it:

```bash
readlink ~/.local/share/uv/tools/debate-cli/bin/python
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" sh -c 'command -v debate-research; debate-research --version; debate-research --json doctor | tr "," "\n" | grep -E "python_version|python_base_prefix|uv_python_directory|python_uv_managed"; debate-research doctor >/dev/null; echo "doctor exit=$?"'
```

Success:

* `readlink` prints `/Users/charlesclark/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12`;
* `/Users/charlesclark/.local/bin/debate-research`, then the new version;
* `"python_base_prefix": "/Users/charlesclark/.local/share/uv/python/cpython-3.12.…-macos-aarch64-none"`,
  `"uv_python_directory": "/Users/charlesclark/.local/share/uv/python"`,
  `"python_uv_managed": true`;
* `doctor exit=0`.

Paste all three blocks' output back for the report. If the install ended with `the installed
debate-research was not touched`, paste it: the agent keeps its previous build and nothing needs
rolling back. The agent's plist and wrapper do not change, because the console-script path is the
same, so there is no reload and no `--check-launchd`. The next scheduled run uses the new build.

## Follow-up work

* **A smoke assertion that the published build is on a Python uv manages** (E01, for the PM). It
  would mean adding `tests/smoke` to a task's packages, and first checking that validate-dev's smoke
  environment carries the runner's `UV_PYTHON_INSTALL_DIR` (Decision 6).
* **The default suite now takes 100 s on this Mac** (4301 tests), up from t22's 64–69 s and t10's
  84 s. The next session that runs it should treat it as an operator command, or confirm it is
  still under two minutes.
* **The stand-in's first Linux run is the PR's `ci`** (Decision 3). If it fails there, the likely
  cause is the copy's layout, not the installer.
* **uv's own "not on your PATH" warning** for the rehearsal directory is still in every install log,
  as t14 and t22 noted.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-08

**Notes:**

Accepted as a partial merge (`scripts/task pr --partial`). The phase stays `InProgress` until
Charlie runs operator follow-up 2 after the agent's 2026-10-14 run, and the PM records it.

* **The finding that it was conda's activated base environment, not PATH order:** that measurement
  is what makes the ac1 test honest. A PATH-only stand-in would have passed against the old script.
  Setting `CONDA_PREFIX` and `CONDA_DEFAULT_ENV` the way `conda init` does, with the control test
  showing the stand-in is live, is the right construction.
* **Decision 1 (check what uv gave, not only what was asked for): accepted.** It is t22's principle
  applied to the interpreter, and mutation shows it is the only check that catches a uv ignoring the
  option.
* **Decision 2 (download, and say so):** accepted, as decided.
* **Decision 4 (how doctor decides):** accepted. It uses uv's own rule (location under
  `uv python dir`), resolves links on both sides, and compares by path component. The surviving link
  mutant, followed by the new test that catches it, is mutation testing doing its job.
* **Decisions 5 and 7: accepted.** They are stated honestly. doctor answers from its own
  environment, and "only a reinstall changes the interpreter" is true except for uv commands someone
  runs on purpose.
* **Decision 8 (the installer tests need a managed Python and fail rather than skip without one):**
  accepted. CI installs one, and this Mac has one.

**Not filed:**

* **A smoke assertion on `python_uv_managed`.** It is informational, and it depends on the runner's
  `UV_PYTHON_INSTALL_DIR` reaching the smoke environment.
* **uv's PATH warning:** as before.

**Noted:** the default suite is now about 100 s on this Mac. A session that runs the whole suite
uses `-n auto`, or hands it to the operator if it passes two minutes (working agreement 1).

**Operator follow-up 2:** the PM will give Charlie the tag from follow-up 1's log, rather than
relying on the release body naming the commit.

### Operator follow-up 1, recorded (PM, 2026-10-08)

**Follow-up 1: PASS.** The dev pre-release for `cee3587` (`v0.1.0-dev.71`, run 37745434211, the
build promotion #184 carried) logged, in "Install the build as its users will and check it can
import everything it wires":

* `The build runs on the Python at /home/runner/work/_temp/uv-python-dir/cpython-3.12.15-linux-x86_64-gnu, which uv manages.`
* doctor's row `Managed by uv │ yes`.

`validate-dev` posted `success` on `cee3587` for `v0.1.0-dev.71`.

**Follow-up 2** is still open, so the Goal stays `InProgress`. The agent is reinstalled with
`v0.1.0-dev.71`, or a newer validated tag, only after the scheduled run of Wednesday 2026-10-14
06:00 CDT has been checked for v1-e34-t05.
