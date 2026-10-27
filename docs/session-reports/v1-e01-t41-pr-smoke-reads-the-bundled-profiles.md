# Session report: v1-e01-t41-pr-smoke-reads-the-bundled-profiles

| | |
|---|---|
| Task | `v1-e01-t41-pr-smoke-reads-the-bundled-profiles` — The pull request's smoke tier reads the bundled profiles, as the installed build does |
| Spec | [`plan_specs/v1/e01-repo-foundation/t41-pr-smoke-reads-the-bundled-profiles.yaml`](../../plan_specs/v1/e01-repo-foundation/t41-pr-smoke-reads-the-bundled-profiles.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t41-pr-smoke-reads-the-bundled-profiles` |
| Session status | COMPLETE |

## Summary

The checkout's smoke build now reads the committed profiles, as an installed build does. Why it
didn't before: `load_settings` finds profile files by walking up from the working directory
(`find_repository_root()`), unless the caller passes a bundled root, and only a stamped build
does that (`debate_cli.build_info.bundled_config_root()` needs `_build_info.py`). The harness
runs the checkout's console script from a scratch `smoke-cwd`, so no checkout was found and every
value came from `built-in:dev`. v1-e05-t03's source-checkout anchor (`_source_checkout()`) covers
only `models.routing_file`, never the profile file. The fix is in the harness alone.
`resolve_build` gives the checkout's build a `profile_directory` (this checkout's
`config/profiles`, which `scripts/stamp_build.py` copies into the wheel), and `InstalledCli`
passes it as `DEBATE_PROFILE_DIR`. An installed build gets no profile directory, so validate-dev's
path through `DEBATE_SMOKE_BIN` is unchanged, and two harness tests now pin that.

Counted with the profiles read, 2 of the tier's 155 checks changed outcome, both pass → fail.
The 2 checks #571 added after the sync changed nothing. Both premises are fixed in the checks,
and a new guard check fails if the checkout's build falls back to the built-in values. Both of
the PM's mutants were caught. The first thing to look at is the count table under Decisions.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `smoke-profiles` (Smoke reads the profiles) | Done | Harness change (`27282b8`), then premise fixes, guard check and docs (`e934a2a`), rebased onto `origin/dev` at `191478f` with `scripts/task sync`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, the smoke checks whose outcome changes when the profiles are read, in the report | PASS | Before: the tier in quarters at `bd9c628` (old harness) → 155 passed. Then the harness change alone (`c7ec4ac`, no check edited) in quarters → 2 failed, 153 passed. Outcomes compared test by test from the junit files: exactly 2 changed, both pass → fail. Listed with causes under Decisions. After the sync, #571's checks were run under both harnesses → no change. |
| ac2: the checkout's smoke build reads the bundled profiles, shown by a test that reverts the 2026-10-27 pin and fails; every smoke check passes | PASS | Pin reverted as a mutant (not committed, as the PM asked): `test_caselist_backfile.py` without `DEBATE_CASELIST__API_ENABLED=false` → **3 failed** under the new harness (`CASELIST_TOKEN_MISSING` on `backfile-survey`, `STORE_PROFILE_NOT_CONFIGURED` on both `backfile-import` forms). The same mutant under the old harness → 3 passed, which was the gap. Every smoke check: see the next row. |
| Node `smoke-profiles`: Smoke tier passes (`uv run pytest tests/smoke -m "not live"`) | PASS | Run in four parts, each under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest tests/smoke -m "not live" --part K/4`, because the whole tier measured about 150 s. At `4f9ed81`: 39 + 39 + 39 + 39 = **156 passed**, 0 failed, 0 skipped. After the sync, the one smoke file dev had changed (`test_caselist_restore_run_state.py`) → 6 passed. |

### Mutants (agreement 8; each run with `HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory)

None of the selected tests use Hypothesis. The empty database is set anyway, as the agreement asks.

| Mutant | Run | Result |
|---|---|---|
| 1 (PM): the checkout's build falls back to the built-in values (`resolve_build` gives it no profile directory) | `test_cli_smoke.py`, `test_caselist_restore_run_state.py`, `test_smoke_harness.py` | **Caught**: 4 failed. The guard check `test_config_show_reads_the_api_gate_from_the_dev_profile_not_the_built_in_values` (`False is True`), and the three checks whose premises now name profile values: restore-run-state's profile check, `doctor --evidence-profiles` and dev/prod's Bedrock profiles. |
| 2 (PM): the 2026-10-27 pin removed from `test_caselist_backfile.py` | that file | **Caught**: 3 failed in the PR tier. Under the harness from before this task the same mutant gave 3 passed. |
| 3: `resolve_build` gives an installed build the checkout's profile directory too | `test_smoke_harness.py` + the guard check | **Caught** by `test_an_installed_build_is_described_by_the_variables_validate_dev_sets` (new assertion `profile_directory is None`). |
| 4: `InstalledCli.environment()` sets `DEBATE_PROFILE_DIR` for every build, whatever the build says | same | **Caught** by `test_no_inherited_debate_or_aws_variable_reaches_the_build`, whose allowed set has no `DEBATE_PROFILE_DIR`. |
| 5: the checkout's build is given `config/` instead of `config/profiles/` | same | **Caught** by the guard check: no `dev.toml` there, so the value falls back to built-in. |

### Checks before the report (agreement 10)

* `uv run scripts/affected_tests.py` → 65 of 547 test files, 26 of them in `tests/smoke`, which
  alone took about 150 s in parts. The set is over two minutes, so it is left to the pull
  request's `ci`, which runs the same affected set. Within the two minutes:
  * `tests/smoke`, the directory this task changed: the whole tier in quarters, above (156
    passed), and the one file the sync changed (6 passed);
  * the always-run list plus the docs checks (the smoke README changed):
    `.venv/bin/python -m pytest -n auto -m "not slow and not live" tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs/ tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`
    → 551 passed in 21.9 s before the sync, and again in 22.4 s after it (Final checks).
* `ruff format --check .` → 1538 files already formatted; `ruff check .` → All checks passed.
* `uv run --frozen pyright tests/smoke` → 0 errors; `--stats` on the five changed Python files →
  5 checked. No package source changed.
* `uv run --frozen lint-imports` → 18 kept, 0 broken; `scripts/check_thin_handlers.py` → OK, 67
  handlers.
* Spec validation and the docs checks: under Decisions, "Final checks".

## Files changed

* `tests/smoke/installed_build.py`: the fix. `SmokeBuild.profile_directory` is set by
  `resolve_build` for the checkout's script only, and `InstalledCli.environment()` passes it as
  `DEBATE_PROFILE_DIR`. The module docstring says why.
* `tests/smoke/test_cli_smoke.py`: the guard check, `doctor --evidence-profiles` fixed to expect
  the Bedrock profile from both builds, the dev/prod check's Bedrock assertion made to hold for
  both, a routing-file assertion for the checkout, and two docstrings updated.
* `tests/smoke/test_caselist_restore_run_state.py`: the profile check's checkout branch, which
  expected built-in values, is removed. Both builds now assert the dev profile.
* `tests/smoke/test_smoke_harness.py`: an installed build gets no profile directory.
* `tests/smoke/test_caselist_backfile.py`: docstring only. The pin stays, and now holds in both tiers.
* `tests/smoke/README.md`: a paragraph saying both builds read the committed profiles, and how.
* The spec's Goal phase, and this report.

## Deviations from the spec

None. Every change is under `tests/smoke`, inside `constraints.packages`. Nothing in
`debate_core`, `debate_cli`, `config/profiles` or validate-dev's path changed.

## Decisions and assumptions

**The count (ac1).** Old harness against new, with no check edited, at `c7ec4ac`, compared test
by test:

| Check | Before → after | Cause |
|---|---|---|
| `test_caselist_restore_run_state.py::test_the_bundled_dev_profile_names_the_weekly_caselists_and_keeps_the_runs_state_in_the_bucket` | passed → failed | Its checkout branch asserted `caselist.run_state` came from `default` with the value `local`. The dev profile sets `run_state = "bucket"` (v1-e40-t06). Fixed: both builds assert the profile's caselists, `bucket`, and a `profile:` source. |
| `test_cli_smoke.py::test_doctor_checks_the_evidence_profiles_only_when_asked_and_fails_on_one_that_is_not_defined` | passed → failed | It expected the `models.aws_profile` entry (`debate-dev-bedrock`, from the dev profile, v1-e05-t08) only from an installed build. Fixed: expected from both. |

These checks branched on `build.installed` for profile values, or said in their text that the
checkout falls back, but kept their outcome. They were updated so that the PR tier asserts what
validate-dev asserts:
* `test_dev_and_prod_get_their_own_data_directory_routing_file_and_budget`: the Bedrock profile
  assertion now holds for both builds. The `_bundled_config` routing-file assertion stays
  installed-only, because it is about the wheel, and the checkout's branch now asserts the
  routing file is under this checkout's `config/`.
* `test_doctor_checks_the_search_index_stores_only_when_asked_and_fails_on_one_never_parsed`:
  docstring only. It reads the caselists from `config show`, so it already followed the profile.
* `test_caselist_backfile.py`: docstring only. The PM's pin is what kept it passing.

The 2 checks #571 added (`refuses_the_data_directory...[with sources]` and
`offers_sources_and_takes_a_snapshot_only_with_them`) pass under both harnesses, so they don't
change the count.

**`DEBATE_PROFILE_DIR` rather than a stamped stand-in.** An installed build reads
`_bundled_config/config/profiles/<env>.toml`, which `stamp_build.bundle_configuration` copies
byte for byte from `config/profiles/*.toml`. It anchors routing files on `_bundled_config`,
holding copies of `config/model_routing.*.yaml`. The checkout already anchors routing files on
itself (v1-e05-t03), so the profile file was the one input that differed. Naming that directory
gives the checkout's build the same bytes through the override that `load_settings` already
documents ("`DEBATE_PROFILE_DIR` still overrides both"). Precedence is the same for checks too: a
check that sets its own `DEBATE_PROFILE_DIR` (pull, remove, publish, runs, auth) wins over the
harness's, as it wins over an installed build's bundled copy. Stamping a stand-in build
(`_build_info.py` and `_bundled_config` in the package) would also change the channel to `dev`
and write into the source tree that the in-process tests import, so I didn't. The only difference
left is the source label's path, absolute in both cases: the checkout's
`profile:<checkout>/config/profiles/dev.toml` against `profile:<site-packages>/debate_cli/_bundled_config/config/profiles/dev.toml`.
The guard check asserts each build's own form.

**The guard check reads the expected value from the committed `config/profiles/dev.toml`**, so a
later change to the gate won't break it. The source assertion is what catches a fallback.
validate-dev runs the tier from a checkout of the commit it installed, so the file it reads is
the one that build's wheel copied.

**The installed-build branches are first exercised in validate-dev.** The guard check's
`_bundled_config` branch is new. The installed-build assertions in the other edited checks were
there before and haven't changed. The label shape it asserts is the one
`test_settings_environments.py::test_an_installed_build_reads_its_bundled_profile_even_inside_a_checkout`
already pins for a bundled root.

**Time (the PR tier must not grow by more than a few seconds).** The whole-tier wall clock is
dominated by machine load (load average 4 to 25 during this session), so here are both
measures:

| Run | Commit | Parts 1/2/3/4 (s) | Sum (s) | Load average |
|---|---|---|---|---|
| Before | `bd9c628` | 32.7 / 36.1 / 34.9 / 50.1 | 153.8 | 4 to 8 |
| Counting run (harness only, 2 failing) | `c7ec4ac` | 27.5 / 27.8 / 28.1 / 35.3 | 118.7 | 10 to 13 |
| After | `4f9ed81` | 29.9 / 28.8 / 41.3 / 45.5 | 145.4 | 8 to 16 |

The change's own cost is one `DEBATE_PROFILE_DIR` variable and one TOML read per CLI process.
Measured directly as 8 interleaved pairs of `debate-research --json config show` from a scratch
directory: median 0.586 s with built-in values and 0.565 s with the profile read. No measurable
difference. The new guard check adds one such run, about 0.6 s on one worker.

**The sync.** `origin/dev` gained #571 (v1-e40-t10) during the session, which edited
`test_caselist_restore_run_state.py` in hunks that don't overlap mine. `scripts/task sync`
rebased cleanly. That file was re-run under both harnesses and the count re-checked, above.

**Commit names.** The runs above were measured before the sync, at `bd9c628` (start), `c7ec4ac`
(harness only) and `4f9ed81` (premise fixes). The rebase made those `eaa8247`, `27282b8` and
`e934a2a`, with the same content.

**Final checks**, after the sync, the phase change and this report:
* `uv run scripts/validate_specs.py` → OK: 490 files, 40 epics, 428 tasks, 22 releases.
* `uv run --frozen python scripts/docs_index.py --check-descriptions` → all 56 indexed documents
  have a description.
* `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → OK: no `#` comments
  in 518 shell code blocks in 190 Markdown files, this report included.
* The always-run list plus the docs checks, the command above → 551 passed in 22.4 s.

## Operator follow-ups

None. The pull request's `ci` runs the 65-file affected set, which is over the session's two
minutes. validate-dev's next run is the first to exercise the guard check against an installed
build.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
