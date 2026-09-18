# Session report: v1-e01-t03-uv-workspace-tooling

| | |
|---|---|
| Task | `v1-e01-t03-uv-workspace-tooling` — uv workspace, Python 3.12 and quality tooling |
| Spec | [`plan_specs/v1/e01-repo-foundation/t03-uv-workspace-tooling.yaml`](../../plan_specs/v1/e01-repo-foundation/t03-uv-workspace-tooling.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t03-uv-workspace-tooling` |
| Session status | COMPLETE (one node criterion's shell command fails on macOS only; spec fix proposed under Deviations) |

## Summary

The skeleton is now a working uv workspace. The root `pyproject.toml` declares `debate_core`,
`debate_cli`, `debate_api` and `debate_workers` as workspace members. Each member is an empty
src-layout package with `py.typed` and one smoke test. Python is pinned to 3.12, and `uv.lock`
is committed. The root file also configures all the shared tooling: ruff (lint and format, line
length 110), pyright (strict for `debate_core`, standard elsewhere), and pytest with xdist,
coverage, pytest-socket, respx and hypothesis. All five project markers are registered there,
and `slow` and `live` are deselected by default. pre-commit hooks run through `uv run --frozen`,
so their versions come from the lockfile. Every acceptance criterion passes from a clean clone
except one. The node check "All project markers are registered" fails on macOS because BSD `wc`
left-pads its count. The markers themselves are correct: see Deviations for evidence and a
one-word spec fix. Things for the PM to check first: `scripts/` is excluded from ruff (see
Decisions), and the delivery packages depend on `debate-core` as a workspace source.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| Root workspace and package shells (`workspace`) | Done | Root plus 4 member `pyproject.toml` files (build backend `uv_build`), `.python-version` = 3.12, `src/<pkg>/__init__.py` + `py.typed`, `uv.lock` (41 packages). |
| ruff lint and format configuration (`lint-format`) | Done | Rules F, E, W, I, B, UP, SIM; line length 110; target py312; `scripts/` excluded (see Decisions). |
| pyright strict for debate_core (`type-check`) | Done | `[tool.pyright]` `typeCheckingMode = "standard"`, `strict = ["packages/debate_core"]`. Probe: an untyped function gave 4 strict errors in debate_core and none in debate_cli. |
| pytest, xdist, coverage, respx, hypothesis (`test-tooling`) | Done except one criterion's command on macOS | Dev dependency group; pytest config; one `tests/test_smoke.py` per package (importable + ships `py.typed`). Marker-count command: see Deviations. |
| pre-commit hooks (`pre-commit`) | Done | Local hooks: ruff check, ruff format, trailing whitespace, end-of-file fixer, large-file guard (500 KB). `uv run pre-commit install` documented in README. |

## Acceptance criteria

The clean-clone run was: `git clone --branch task/v1-e01-t03-uv-workspace-tooling <worktree>
<scratch>/clean-clone`, followed by every command below. Python 3.12.13, uv 0.11.7, macOS arm64.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1: `uv sync --all-packages` works from a clean clone on 3.12 and all four packages import | PASS | `uv sync --all-packages --locked` → rc 0; `uv run python -c "import debate_core, debate_cli, debate_api, debate_workers"` → `3.12.13 imports ok` |
| Goal ac2: ruff check, ruff format --check and strict pyright on debate_core pass | PASS | `uv run ruff check` → `All checks passed!`; `uv run ruff format --check` → `42 files already formatted`; `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` |
| Goal ac3: pytest runs in parallel with coverage and blocked sockets; markers registered; slow and live deselected by default | PASS | `uv run pytest` → `11 workers [8 items]`, coverage table, `8 passed`. Scratch probe test (not committed): opening a socket raises `SocketBlockedError`; default run → `3 passed, 2 deselected`; `-m slow` → `1 passed, 4 deselected`; `-m live` → `1 passed, 4 deselected`; an unregistered `@pytest.mark.bogus` → `'bogus' not found in markers configuration option`. `pytest --markers` lists exactly `slow`, `live`, `eval`, `dev`, `prod`. |
| Goal ac4: pre-commit runs ruff, ruff-format, EOF/trailing whitespace and a large-file guard | PASS | `uv run pre-commit run --all-files` → all 5 hooks `Passed`; a staged 684 KB file → `large_file_probe.bin (684 KB) exceeds 500 KB.`, rc 1 (probe file removed afterwards) |
| workspace: Workspace syncs from lockfile | PASS | `uv sync --all-packages --locked` → rc 0 |
| workspace: Workspace members declared (`[tool.uv.workspace]` in pyproject.toml) | PASS | `grep -c '^\[tool.uv.workspace\]' pyproject.toml` → `1` |
| lint-format: ruff lint passes | PASS | `uv run ruff check` → `All checks passed!` |
| lint-format: ruff format check passes | PASS | `uv run ruff format --check` → `42 files already formatted` |
| type-check: pyright strict passes on debate_core | PASS | `uv run pyright packages/debate_core` → `0 errors` |
| test-tooling: Smoke tests pass in parallel with coverage | PASS | `uv run pytest -n auto --cov` → `8 passed in 1.71s`, coverage report printed |
| test-tooling: Default pytest run excludes slow and live markers | PASS | `grep -c 'not slow and not live' pyproject.toml` → `1` |
| test-tooling: All project markers are registered | FAIL on macOS (the spec command is not portable; the markers are correct) | Spec command `bash -c "uv run pytest --markers \| grep -E '^@pytest.mark.(slow\|live\|eval\|dev\|prod):' \| wc -l \| grep -qx 5"` → rc 1, because BSD `wc -l` prints `       5` (checked with `od -c`). The same pipeline with `grep -c` instead of `wc -l` → rc 0, and so does `wc -l \| tr -d ' '` → rc 0. GNU `wc` on the Linux CI runner prints a bare `5`, so the spec command should pass there as written. |
| pre-commit: pre-commit passes on all files | PASS | `uv run pre-commit run --all-files` → rc 0 |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 219 files, 28 epics, 174 tasks, 17 releases`; `--require-succeeded v1-e01-t03-uv-workspace-tooling` → `Succeeded` |

## Files changed

* **Workspace root:** `pyproject.toml` (workspace members, dev dependency group, and the ruff,
  pyright, pytest and coverage config), `.python-version`, `uv.lock`.
* **`packages/debate_{core,cli,api,workers}/`:** `pyproject.toml`, `src/<pkg>/__init__.py` (one-line
  docstring), `src/<pkg>/py.typed`, `tests/test_smoke.py`. These are the empty package shells the spec asks for.
* **`.pre-commit-config.yaml`:** the pre-commit hooks.
* **`README.md`:** new "Development setup" section covering `uv sync`, `uv run pre-commit install`,
  the check commands, and how markers work.
* **`.gitignore`:** added `.coverage.*`, `coverage.xml`, `.hypothesis/`. These are files the new
  test tooling writes.
* **Spec:** `t03-uv-workspace-tooling.yaml` Goal `status.phase` set to `Succeeded`.

## Deviations from the spec

* **The criterion "All project markers are registered" (node `test-tooling`) has a
  non-portable command.** `wc -l | grep -qx 5` depends on GNU `wc` output. BSD/macOS `wc`
  left-pads the number, so the check fails on the operator's Mac even though exactly the five
  markers are registered. I did not edit the spec. Suggested fix for the PM: change the args to
  `[-c, "uv run pytest --markers | grep -cE '^@pytest.mark.(slow|live|eval|dev|prod):' | grep -qx 5"]`,
  which passes on both platforms (verified on macOS).
* **`README.md` and `.gitignore` were edited.** Neither is in `constraints.packages`. The
  `pre-commit` node description asks for the README change. The `.gitignore` additions only
  cover files written by tools this task introduces.

## Decisions and assumptions

* **`scripts/` is excluded from ruff** (`extend-exclude`, plus `force-exclude = true` so
  pre-commit respects it). The existing `validate_specs.py`, `task_helper.py` and
  `spec_index.py` produce 5 lint errors and 3 formatting diffs under the new config. Those files
  belong to v1-e01-t05-spec-tooling and v1-e01-t11-task-workflow-cli, and t05 can run in
  parallel with this task. Reformatting them here would go outside this task's package list and
  could cause merge conflicts. Goal ac2 scopes the checks to "the empty packages", which is
  consistent with excluding `scripts/`.
* **The pre-commit hooks are `repo: local` and run through `uv run --frozen`** (language
  `unsupported`, the pre-commit 4.x name for `system`). Tool versions therefore come from
  `uv.lock` rather than a second set of hook `rev:` pins, and the hooks fetch nothing from
  GitHub. The trade-off is that the whitespace, end-of-file and large-file hooks use the
  `pre-commit-hooks` PyPI package, which is now a dev dependency.
* **The root is a non-packaged project** (`[tool.uv] package = false`) named `debate-intelligence`,
  so it can own the `dev` dependency group.
* **Build backend is `uv_build`** (`>=0.11.7,<0.12`). Member distributions are `debate-core`,
  `debate-cli`, `debate-api` and `debate-workers`, version 0.1.0. The three delivery packages
  depend on `debate-core` as a workspace source. No runtime dependencies were added: Typer
  arrives in t07 and FastAPI in V2.
* **Version ranges:** all dev tools use lower-bound ranges, and the committed `uv.lock` pins the
  exact versions. The versions resolved are ruff 0.16.8, pyright 1.1.414 (with the `nodejs`
  extra, so no system Node is needed), pytest 9.1.1, pytest-xdist 3.8.0, pytest-cov 7.1.0,
  pytest-socket 0.8.1, respx 0.23.1, hypothesis 6.168.0, pre-commit 4.6.2 and pre-commit-hooks
  6.0.0.
* **`requires-python = ">=3.12"`, with `.python-version` pinning 3.12.** The architecture says
  "3.12+", so there is no upper bound.
* **pytest details:** `--import-mode=importlib` lets four packages each have a
  `tests/test_smoke.py`. `--strict-config` is on. `tests/` is included in testpaths for
  cross-package suites. `-n auto` and `--cov` are in addopts, so a plain `uv run pytest` meets
  ac3. Pass `-n 0` or `--no-cov` for debugging. The coverage warning `no-data-collected` is
  turned off because xdist workers that receive no tests always emit it.
* **Large-file guard threshold:** 500 KB (the tool's default).

## Operator follow-ups

None. All commands ran in seconds (full sync about 4 s, test run about 3 s).

## Follow-up work

* **v1-e01-t05-spec-tooling (or t11):** bring `scripts/*.py` up to the ruff config (5 lint
  errors, 3 files to reformat), then remove `extend-exclude = ["scripts"]` from the root
  `pyproject.toml`.
* **v1-e01-t04-ci-pipeline:** CI can run `uv sync --all-packages --locked`, the ruff and pyright
  commands above, and `uv run pytest`. The marker-count check passes on Linux as written, but the
  portable `grep -c` form is safer.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
