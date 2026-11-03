# Session report: v1-e05-t12-installed-build-carries-model-pricing

| | |
|---|---|
| Task | `v1-e05-t12-installed-build-carries-model-pricing` — An installed build carries config/model_pricing.yaml beside the routing files |
| Spec | [`plan_specs/v1/e05-model-router/t12-installed-build-carries-model-pricing.yaml`](../../plan_specs/v1/e05-model-router/t12-installed-build-carries-model-pricing.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t12-installed-build-carries-model-pricing` |
| Session status | COMPLETE |

## Summary

`scripts/stamp_build.py` now copies `config/model_pricing.yaml` into the wheel's
`_bundled_config/config/` alongside the routing files, and `check-wheels` refuses a debate_cli wheel
without it. The resolution side needed no change: `build_model_router` already reads the
`model_pricing.yaml` beside `models.routing_file`, and in an installed build that routing file is
the bundled one, so the pricing file is found there once it is shipped. Before this change every
installed build failed closed on its first model call under the dev or prod budget, with
`UnpricedModelError: ... _bundled_config/config/model_pricing.yaml (not found)`. That was shown
on a real stamped build of the start commit, and the new smoke check reproduces it. The new smoke
check runs one live-mode call on the build's own interpreter, with a stand-in where Bedrock would
be, and checks its cost against the committed price. It passes against the checkout's script (the
PR's tier) and against a stamped build of this branch. All four mutants (the PM's three, the third
in two forms) were caught.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `bundled-pricing` (Bundled pricing file) | Done | Red tests first, then the stamp and the wheel check; smoke check added; four mutants caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1, "A stamped build holds the pricing file, and an installed build's router prices a call from it, by tests shown failing first; the smoke check covers it" | PASS | **Red, unit**, on the start code with the new tests: `.venv/bin/python -m pytest tests/scripts/test_stamp_build.py -p no:randomly -n 0 --tb=line` → `3 failed, 22 passed`: the bundle listing (no `model_pricing.yaml`), the wheel check (`assert [] == ['…missing …/model_pricing.yaml']`), and the stamped build's router (`UnpricedModelError: model call to anthropic.claude-haiku-4-5-20251001-v1:0 refused: a budget limit is set and the call cannot be priced: …/_bundled_config/config/model_pricing.yaml (not found) …`). **Green**: `25 passed`. **Red, smoke, installed build**: start commit `6e5c344` exported with `git archive`, stamped with the old script, wheels built with `uv build --offline`, installed outside the checkout (see Decisions), then `DEBATE_SMOKE_BIN=…/venv-before/bin/debate-research DEBATE_SMOKE_EXPECT_SHA=6e5c344… DEBATE_SMOKE_EXPECT_TAG=v0.0.1-dev.1 pytest tests/smoke/test_cli_smoke.py -k "priced or own_data_directory"` → `1 failed, 1 passed`: the new check failed with the same `UnpricedModelError`, and the existing bundled-routing check passed. **Green, smoke, installed build**: commit `325372d` stamped with the new script, `check-wheels` → `wheels in dist are publishable as 0.0.1.dev2`, installed the same way, whole `tests/smoke/test_cli_smoke.py` → `17 passed in 68.07s`. **Green, smoke, checkout's script** (what the PR's `ci` runs): `pytest tests/smoke/test_cli_smoke.py -k priced` → `1 passed`, and in the affected set below. The new `check-wheels` also refuses the start commit's real wheel: `debate_cli-0.0.1.dev1-py3-none-any.whl: missing debate_cli/_bundled_config/config/model_pricing.yaml`, exit 1 |
| Node `bundled-pricing`, "Stamp build tests pass" (`uv run pytest tests/scripts -k stamp`) | PASS | Run as `.venv/bin/python -m pytest tests/scripts -k stamp` under a hard time limit → `25 passed in 14.93s` |

### Mutants (agreement 8)

Each was applied to the committed tree and run against `tests/scripts/test_stamp_build.py`, with
`HYPOTHESIS_STORAGE_DIRECTORY` set to a new empty directory each time (these tests use no
Hypothesis property). The file was restored with `git checkout HEAD --` after each run, and the tree
was clean at the end. All 25 tests were collected in every run, and every catch is an assertion
failure, not an error:

| Mutant | Caught by | Failure |
|---|---|---|
| The pricing file left out of the stamp (its `("model_pricing.yaml", "")` entry deleted from `bundle_configuration`) | the bundle listing; the stamped build's router | listing mismatch; `UnpricedModelError` |
| The installed build resolving the checkout's file (`build_model_router` reads `(find_repository_root() or Path.cwd()) / "config" / model_pricing.yaml`) | the stamped build's router; the missing-file refusal | `assert 0.011 == 0.017`, the committed Haiku 4.5 price instead of the bundled synthetic one; `DID NOT RAISE UnpricedModelError` |
| A missing pricing file treated as free: the budget guard skipped when the file is not found | the missing-file refusal | `DID NOT RAISE UnpricedModelError` |
| A missing pricing file treated as free: an unpriced call's ceiling read as $0 (`RoutePricing._unpriced` returns `usd=0.0`) | the missing-file refusal | `DID NOT RAISE UnpricedModelError` |

### Before the report (agreement 10)

| Check | Result |
|---|---|
| Affected set: `uv run scripts/affected_tests.py` lists 45 of 571 test files from 6 changed files, `tests/smoke/test_cli_smoke.py` and `tests/scripts/test_stamp_build.py` among them. Its run command was run on the interpreter under a hard limit: `.venv/bin/python -m pytest -n auto -m "not slow and not live" <the 45 files>` | `2065 passed in 83.65s` |
| `uv run --frozen ruff format --check .` | `1601 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `pyright` (the repository's configuration, `packages/`; no package changed) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run --frozen python scripts/check_command_blocks.py` | `OK: no # comments in 578 shell code blocks in 197 Markdown files` |
| `uv run scripts/validate_specs.py` | `OK: 493 files, 40 epics, 431 tasks, 22 releases` |

## Files changed

* `scripts/stamp_build.py`: bundles `config/model_pricing.yaml` with the routing files; adds
  `_bundled_config/config/model_pricing.yaml` to `REQUIRED_CLI_MEMBERS`, so `check-wheels`
  refuses a wheel without it; the module docstring says why.
* `tests/scripts/test_stamp_build.py`: the bundle listing pin now includes `model_pricing.yaml`. New
  tests: a wheel missing the file is refused; a stamped build's router prices a live-mode call from
  the copy it carries, under the dev profile's budgets; and a stamped build whose bundled pricing
  file is missing refuses the call under its budget, before the stand-in is reached and with nothing
  logged. Prices are a synthetic file's, written into the copied checkout before the stamp, and the
  expected $0.017 is worked out by hand in the test.
* `tests/smoke/test_cli_smoke.py`: `test_a_model_call_is_priced_from_the_pricing_file_the_build_carries`.
  The build's own interpreter loads settings with `debate_cli.build_info.settings_loader()`, as the
  CLI does, then makes one high_volume call through `build_model_router` in live mode with a
  stand-in router, and prints the usage records. The test checks the model, the tokens and the
  cost, worked out from the committed `config/model_pricing.yaml` price for the committed dev
  high_volume model. It also checks where the pricing file was read: the wheel's `_bundled_config`
  copy for an installed build, the checkout's `config/` for the checkout's script.
* `tests/smoke/README.md`: the `test_cli_smoke.py` row describes the new check.
* The task spec: Goal phase `Succeeded`.

## Deviations from the spec

None. The PM's note asked for the installed build to "resolve it the same way" as the routing
files. It already did (`routing_file.parent / model_pricing.yaml`, where `routing_file` is anchored
to the bundled root), so no resolution code changed. Mutant 2 holds that resolution in place.

## Decisions and assumptions

* **The smoke red was taken on a locally stamped build, not on a published pre-release.** Rehearsing
  against the newest dev pre-release would mean downloading it, a live network call that goes to the
  operator, and uv's offline cache could not resolve a fresh install. So the start commit and this
  branch's commit were each exported with `git archive` into the session's scratch directory,
  stamped, and built with `uv build --offline`. The two wheels were installed `--no-deps` into a venv
  there on the managed CPython 3.12.13. Third-party dependencies came from the worktree venv's
  `site-packages` through a plain-path `.pth` line, which does not activate the worktree's editable
  `debate_core`/`debate_cli` finders: `debate_cli.__file__` and `debate_core.__file__` were the
  scratch venv's copies, and no `packages/*/src` path was on `sys.path`. The binary and interpreter
  were outside the checkout, as the harness requires. validate-dev runs the same check against the
  real pre-release after the merge.
* **No refusal at stamp time for a checkout without the pricing file.** The routing files are copied
  by glob with no such check either. `check-wheels` runs straight after the build in
  `dev-prerelease.yml` and refuses the wheel by name, so a build without the file still never
  publishes.
* **The PM's mutant 3, "a missing pricing file treated as free rather than refused", was run in two
  forms.** The factory skipping the guard when the file is missing, and an unpriced ceiling read as
  $0. Both are plausible ways to write it, and the missing-file test catches both.
* `pyright tests/scripts/test_stamp_build.py` reports the file's existing `import stamp_build`
  (loaded through `sys.path`) as unresolved. That is not new, and CI's pyright covers `packages/`
  only.

## Operator follow-ups

None. The real pre-release's check runs in validate-dev after the merge into `dev`. The
`dev-prerelease` run's `check-wheels` step is the first place a missing pricing file would now stop
a publish.

## Follow-up work

* **The cloud-run landscape stage will need more than the pricing file in an installed build**
  (for the PM, who is filing it). The stamp bundles only `config/profiles/`, the routing files and
  now the pricing file. `config/landscape/` is not in a wheel, and `landscape report` reads it from a
  checkout around the working directory or from `--config-dir`
  (`debate_cli/options/landscape_config.py`). Neither are `config/federated_ranking.yaml`,
  `config/format_profiles/` or `config/feeds/`.
* **Two docstrings say the stamp copies `config/` whole, and it doesn't**:
  `debate_core/application/federated_ranking.py` (`FEDERATED_RANKING_CONFIG_PATH`) and
  `debate_core/evidence/format_profile.py`. The `debate_cli/build_info.py` module docstring still
  describes the bundle as "the committed profiles and routing files". `debate_cli` is outside this
  task's packages, so none of these was edited. They belong with the landscape item above, or in a
  small E01 docs fix.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-30

**Notes:**

An installed build now carries its prices, and the first model call from one no longer fails closed.
1. **ac1 passes, at all three levels.**
   * Unit: red 3 failed, among them the stamped build's router refusing with `UnpricedModelError`
     against the start code. Green: 25 passed.
   * Smoke on a real stamped build of the start commit: red, with the same refusal. On this branch:
     17 passed.
   * Smoke on the checkout's script: passed.
   * `check-wheels` now refuses the start commit's real wheel by name.
2. **The finding matters.** Every installed build, the cloud image included, would have refused its
   first model call under a budget. Nothing hits it today, but the cloud landscape work would have hit
   it first.
3. **Mutants:** the PM's three, the third in two forms. All are caught by assertions, with 25 collected
   in every run. Mutant 2, the checkout's file read instead of the bundled one, holds the resolution
   in place that you found already correct.
4. **No deviation, rightly.** The resolution already anchors the pricing file beside the bundled routing
   file. Only the stamp was missing it.
5. **Decisions accepted:**
   * the smoke red on locally stamped builds, installed outside the checkout with the editable finders
     shown inactive (validate-dev checks the real pre-release after the merge);
   * no stamp-time refusal, since `check-wheels` stops a publish by name;
   * mutant 3 in two forms.
6. **Follow-up work:**
   * the landscape config, `federated_ranking.yaml`, `format_profiles/` and `feeds/` are not in a
     wheel. That goes into the cloud-run landscape stage task when the PM files it.
     `v1-e40-t17` runs the report from a checkout, so it doesn't need them;
   * the three docstrings that say the stamp copies `config/` whole: filed as an E01 p3 docs fix in
     the PM's next batch.
7. **The affected set ran:** 45 files, 2,065 passed in 84 s. ruff, pyright, lint-imports, the command
   blocks and the specs pass.
8. **Merge:** any time. The PM reads the next pre-release's validate-dev, whose smoke tier runs the new
   check against the real build.
