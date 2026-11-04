# Session report: v1-e08-t17-one-max-cost-across-every-router-a-command-builds

| | |
|---|---|
| Task | `v1-e08-t17-one-max-cost-across-every-router-a-command-builds` — `--max-cost` is one limit for the whole command, whatever routers it builds |
| Spec | [`plan_specs/v1/e08-research-workflows/t17-one-max-cost-across-every-router-a-command-builds.yaml`](../../plan_specs/v1/e08-research-workflows/t17-one-max-cost-across-every-router-a-command-builds.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t17-one-max-cost-across-every-router-a-command-builds` |
| Session status | COMPLETE |

## Summary

Before this change, every router `build_model_router` built was a budget run of its own, so
`search --expand-llm --auto-cut` gave its search router and its card router the full `--max-cost`
each. A new `BudgetRun` in `debate_core.application.budget` now carries the run id, the run's lock
and the ceilings its in-flight calls hold. `BudgetGuard` and `build_model_router` take a `BudgetRun`
where they used to take a bare id. The CLI container makes one `BudgetRun` per command
(`ServiceContainer.budget_run()`) and gives it to all three routers it can build. Every guard of a
command therefore reads one run's spend and holds against one total. The red test, written against
today's code, shows the two-router command spending $0.506527 under a $0.505452 limit. After the
change it stops at the limit, and the refusal names the command's total. The two one-router tests
passed before and after. The PM should look first at the shared in-flight holds (Decisions 2): they
go beyond sharing the id, and they are why `factory.py`, outside the spec's packages, changed
(Deviation 1).

## Which commands build more than one router (PM ruling 2)

Read from the code: `build_model_router` is called only by `debate_cli/container.py`, in three
builders. The API, the workers and the scripts never call it.

| Command | Routers it can build | More than one? |
|---|---|---|
| `search --expand-llm --auto-cut N` | `_search_model_router` (`search.expand`, `high_volume`) and `_card_model_router` (`card.select`, `card.markup`) | **Yes: the only one** |
| `search --expand-llm` without `--auto-cut` | the search router | No (`--max-cost` is a usage error without `--auto-cut`; `models.budget_usd_per_run` still applies) |
| `search --auto-cut N` without `--expand-llm` | the card router (a container singleton shared by every cut) | No |
| `cut` | the card router | No |
| `landscape report`/`run` with a model mode | `landscape_model_stage`, not a singleton, but `LandscapeRunService._classifier_for` calls it once per `run()` and the command calls `run()` once | No |
| `landscape evaluate` (and `--breakdown`) | `landscape_model_stage`, called once by `evaluate`/`break_down`, one per command | No |

The landscape stage gets the command's run too, so a future command that called it twice would
still be one run.

Before and after, as tests in `packages/debate_cli/tests/test_search_command.py` show them (the
container builds both routers itself, live, through the usage log and the guard, over a stand-in for
`bedrock_router_factory` whose every call costs its whole guard ceiling at the committed
`config/model_pricing.yaml` prices; no price is written in a test):

| Case | Before (commit `cedbf0b`, today's source) | After |
|---|---|---|
| `--expand-llm --auto-cut 3`, limit = the three cuts' own cost (+1e-9) by `--max-cost` | exit 0, spent $0.506527 under $0.505452 | exit 9; spent ≤ limit; one run id; the 3rd cut's `card.markup` refused; 2 VERIFIED |
| the same, limit from `models.budget_usd_per_run`, no `--max-cost` | as above | as above |
| `--auto-cut 3` alone, limit = the cuts' cost (+1e-9) | exit 0, 3 VERIFIED, each entry's `cost_usd` its own two calls | unchanged |
| `--auto-cut 3` alone, limit = the cuts' cost (−1e-9) | exit 9, refusal text exactly as v1-e05-t07 words it | unchanged |

The after-refusal names the command's total and the limit: `the per-run budget is $L, $S is already
spent or held`, where `S` is the sum of every usage record of the command, the expansion's
included.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `one-max-cost-across-every-router-a-comma` (One limit) | Done | Red CLI tests (`cedbf0b`), red core tests against a skeleton (`25cf5d2`), implementation (`d6a25e7`), settings description restored (`31d0700`), leak test and phase (`e5d7385`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: every router one command builds shares one budget run, so `--max-cost` limits the command's total, by tests shown failing first with two routers, and a one-router command's behaviour is unchanged | PASS | Red on today's source (`cedbf0b`): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_search_command.py -k "one_budget or one_router" -n 0` → `2 failed, 2 passed`: both `test_expand_llm_and_auto_cut_stop_at_one_budget_for_the_whole_command` cases fail with `the command spent $0.506527 under a $0.505452 limit`, and both one-router tests pass. Core red against the id-only skeleton (`25cf5d2`), over `test_budget.py`, `test_record_replay.py`, `test_usage.py` and `test_factory.py` → `1 failed, 298 passed`: `test_calls_in_flight_through_two_guards_of_one_budget_run_hold_against_one_limit` admitted 4 calls where 2 fit. After: `test_search_command.py -k "budget or max_cost or one_router"` (the four, the leak test, the help pin and the three existing budget tests) → `9 passed`; the same four core files → `299 passed`. |
| Node: One limit tests pass (`uv run pytest packages/debate_cli/tests packages/debate_core/tests -k "budget or max_cost"`) | PASS | Run bounded by `scripts/hard_stop.py 115` → `96 passed, 5 warnings in 25.56s` (an earlier run, before the leak test: `95 passed in 45.57s`). |

### Checks shown failing (planted breaks, each restored with `git checkout HEAD --`)

| Planted break | Tests run | Result |
|---|---|---|
| `budget_run()` returns a new `BudgetRun()` each call | the four one-limit CLI tests | 2 failed (both two-router cases), 2 passed |
| the card router is given `run=None` | the same | 2 failed, 2 passed |
| `BudgetRun.holding` passes `0.0` to `refuse` (guards see no holds) | `test_budget.py` | 3 failed, including the two-guard hold test |
| the hold is never added | `test_budget.py` | 7 failed |
| the hold is never released | `test_budget.py` | 6 failed, including `test_a_budget_run_lets_go_of_a_hold_through_either_guard_when_its_call_ends` |
| one process-wide `BudgetRun` for every container | `-k two_commands` | `test_two_commands_in_one_process_are_two_budget_runs` failed |
| the `--max-cost` help as it was (`options/budget.py` from `c0a41a8`) | `-k max_cost_help` | `test_max_cost_help_says_it_is_one_limit_for_the_whole_command` failed |

### Before the report

* Affected set: `uv run scripts/affected_tests.py` → `464 of 690 test files (67.2%) chosen in 16.5 s
  from 12 changed files`. `factory.py` reaches the root conftest through `debate_core.integrations.models`,
  so two thirds of the suite is selected, well over two minutes. Under working agreement 10 it was not
  run and is left to the pull request's `ci`. In its place, within two minutes:
  * the always-run list plus the changed modules' tests (`tests/architecture`, `tests/specs`,
    `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`,
    `packages/debate_core/tests/integrations/models`, `.../integrations/bedrock`, `test_budget.py`,
    `test_batch_cut_service.py`, `test_search_command.py`, `test_cut_command.py`, `test_usage_command.py`,
    `test_landscape_evaluate_route.py`, `test_landscape_command.py`, `test_installation.py`), with
    `-n auto -m "not slow and not live"` → `1413 passed in 34.74s`;
  * `packages/debate_core/tests/application` whole → `5201 passed in 90.57s`.
* `uv run --frozen ruff format --check .` → `1936 files already formatted`; `ruff check .` → `All checks passed!`
* `uv run --frozen pyright` (whole repo, as CI) → `0 errors, 0 warnings, 0 informations`
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`
* `scripts/check_thin_handlers.py` → `OK: 72 CLI command and API route handlers within 25 statements`
* `scripts/docs_index.py --check-descriptions` → `All 68 indexed documents under docs/ have a description`;
  `scripts/check_command_blocks.py` → OK; `scripts/check_links.py` → `OK: 3539 relative links and anchors`
* `uv run scripts/validate_specs.py` → `OK: 619 files, 41 epics, 556 tasks, 22 releases`

## Files changed

* `packages/debate_core/src/debate_core/application/budget.py`: `BudgetRun` (the run's id, lock and
  in-flight holds, with `holding()`); `BudgetGuard` takes `run: BudgetRun`, keeps `run_id` as a
  property, and its check moved into `_refuse_past_a_limit` with the same comparison and messages;
  the module docstring says a run is one command, whatever routers it builds.
* `packages/debate_core/src/debate_core/integrations/models/factory.py`: `run: BudgetRun | None` in
  place of `run_id: str | None`; the usage recorder names `run.run_id` and the guard gets the run.
* `packages/debate_cli/src/debate_cli/container.py`: `budget_run()`, a per-container singleton,
  passed to the landscape, card and search router builders.
* `packages/debate_cli/src/debate_cli/options/budget.py`, `search_auto_cut.py`: the `--max-cost` help
  says "one limit for the whole command, whatever models it asks", and the docstrings say why.
* `docs/runbooks/bedrock-access.md`: one sentence saying the run is the whole command.
* Tests: `packages/debate_cli/tests/test_search_command.py` (a `live_models` seam, a Bedrock stand-in
  that spends each call's ceiling, six one-limit tests and a help pin);
  `packages/debate_core/tests/application/test_budget.py` (five guard-level tests and a factory test,
  parametrised over one shared run and one run per router); `test_record_replay.py`, `test_usage.py`
  and the two existing helpers in `test_budget.py` changed only from `run_id="x"` to `run=BudgetRun("x")`.

## Deviations from the spec

1. **`debate_core.integrations.models.factory` changed, outside `constraints.packages`** (which names
   `debate_core.application`). The factory is where a router's guard is built, so it is the only place
   the shared `BudgetRun` can reach the guard. The change is one parameter (`run_id` became `run`) and
   its docstrings. The PM may want `debate_core.integrations.models` added to the spec's packages.
2. **`docs/runbooks/bedrock-access.md` changed**, also outside the packages, under PM ruling 5. It
   explains `models.budget_usd_per_run`, which `--max-cost` sets. No guide under `docs/guides`
   mentions `--max-cost`.
3. **Test call sites in files of unchanged behaviour were edited**, mechanically
   (`run_id="x"` became `run=BudgetRun("x")`). There are two in `test_budget.py`, two in
   `test_record_replay.py` and one in `test_usage.py`. No assertion changed.

## Decisions and assumptions

1. **The run identity's home (ruling 1, my proposal): the container.** `ServiceContainer.budget_run()`
   is a singleton of the container, and `root_callback` builds one container per command invocation.
   `CliRunner` runs the callback on every invoke, so tests that run many commands in one process get a
   run each. `test_two_commands_in_one_process_are_two_budget_runs` shows it, and fails against a
   process-wide run. The CLI only creates the identity: the rule that guards of one run share a lock,
   a ledger query and a held total is `BudgetRun`'s, in `debate_core`.
2. **Holds are shared, not only the id.** Sharing the id alone would fix today's command, because
   the expansion's call finishes before any cut starts. But two guards with their own holds could
   each admit a call in flight that the other cannot see, so "one limit" would hold only while no
   command overlaps calls across its routers. With the lock and held total on the run, the guarantee
   v1-e05-t07 gives one router (a burst cannot pass a check only one call fits) now covers the whole
   command. Day and month checks see the run's holds as before.
3. **The red scenario's limit is measured, not priced by hand.** A run with no limit, in a data
   directory of its own, measures what the three cuts cost; the limit under test is that, plus one part
   in 10⁹, so the cuts alone fit and the expansion's $0.001075 does not. The stand-in reports its
   prompt variables' bytes in and its route's `max_tokens` out, which is exactly `RoutePricing`'s
   ceiling, so every call spends its whole ceiling at the committed prices.
4. **The settings field's description was left as it was** (`31d0700` restores it). It already says
   "one run (one command)". Changing it did not shrink or grow the affected set, so it was dropped as
   unneeded churn.
5. **Unchanged, by the PM's list:** the one-router tests passed before and after, including the exact
   v1-e05-t07 refusal text. v1-e08-t06's per-entry `cost_usd` and `report.json`'s `cost_usd` are
   asserted in `test_a_one_router_auto_cut_spends_up_to_its_max_cost_as_before`. The unpriced-model,
   per-month and per-day tests in `test_budget.py` pass unchanged. `models.budget_usd_per_run` without
   `--max-cost` is the one limit: the second parametrisation of the two-router test.

## Operator follow-ups

None. The affected set (464 files) is left to the pull request's `ci`, per working agreement 10.

## Follow-up work

* **The auto-cut report's `cost_usd` leaves out the expansion's call** (E08). As v1-e08-t06 defined it,
  `report.json` and the BUDGET_EXCEEDED panel give the cuts' total, and a call made outside a cut is
  counted nowhere. The per-run limit now counts the expansion's call, so the limit and the report's
  total can differ by that call. The refusal's own sentence gives the command's total. A
  `command_cost_usd` beside `cost_usd`, or an expansion line, would make the figures agree. This task
  was told to leave the report's figures as they were.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
