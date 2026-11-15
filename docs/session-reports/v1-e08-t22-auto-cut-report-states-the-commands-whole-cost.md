# Session report: v1-e08-t22-auto-cut-report-states-the-commands-whole-cost

| | |
|---|---|
| Task | `v1-e08-t22-auto-cut-report-states-the-commands-whole-cost` — The auto-cut report states the whole command's spend beside its own calls' cost |
| Spec | [`plan_specs/v1/e08-research-workflows/t22-auto-cut-report-states-the-commands-whole-cost.yaml`](../../plan_specs/v1/e08-research-workflows/t22-auto-cut-report-states-the-commands-whole-cost.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t22-auto-cut-report-states-the-commands-whole-cost` |
| Session status | COMPLETE |

## Summary

The auto-cut report now carries `command_cost_usd` beside `cost_usd`, in `<bundle>.report.json` and
in `--json`'s `auto_cut` object, for `search --auto-cut` and `daily --auto-cut`. The figure is read
from the command's one budget run, the object `--max-cost` checks: `RunSpend`
(`debate_core.application.budget`) asks the usage log for the run's spend exactly as each `BudgetGuard`
does, and `BatchCutService` reads it once the walk is over. It is never added up from the entries.
`cost_usd` keeps its meaning and value. The `Model cost:` line under the table names the whole command
only when the two figures print differently, in the PM's wording. The guide's `--auto-cut` section says
which figure is which and which one the limit counts. **Look first at** the rule that makes
`command_cost_usd` null when a cut's call had no price (Decisions), and the guide correction about
`daily --max-cost` (Deviations). The affected set is all 771 test files, because the root conftest
imports `budget.py`, so it is left to the pull request's CI (Acceptance criteria).

## What I found (the PM's item 1: "say what you find")

* **`daily --auto-cut`: the two figures are equal.** Only the cuts call a model. `daily` builds its
  federated search with no structured-output guard (`_build_daily_digesting` passes `None`) over
  `DigestExpansionStage`, which reads the committed templates. Nothing else in the command builds a model
  router. Measured on the live stand-in (`test_daily_auto_cut_costs_the_whole_command_what_its_cuts_cost`,
  kept basetemp): 4 usage records, all `card.select` or `card.markup`, one run id;
  `cost_usd` 0.335158, `command_cost_usd` 0.335158.
* **`search --auto-cut --expand-llm`: the command spends more than its cuts.** Same stand-in, every call
  priced at its guard ceiling from the committed routing and pricing files: 9 records, one
  `search.expand` ($0.0010746) and eight cut calls. `cost_usd` 0.672052, `command_cost_usd` 0.6731266.
  The line reads `Model cost: $0.6721 for the cuts, $0.6731 for the whole command (the --max-cost limit
  counts the whole command)`.
* **The two figures can differ in the last bits when the command spent only on its cuts.** The run's
  total adds the calls one by one in the order they were logged, and `cost_usd` adds each cut's own sum.
  Without `--expand-llm` (8 records) they differ below the line's precision. So the line compares the
  figures **as printed**, and a mutant that compares the raw floats is caught by the live CLI test as
  well as by the hand-built one.
* **`daily` has no `--max-cost` option.** `_cut_options` passes `None`, and `daily --help` lists none.
  The guide's "Real model calls" section said `--max-cost` works on `daily --auto-cut`. For `daily` the
  per-run limit is `models.budget_usd_per_run`, and the guard counts the command as one run in the same
  way (the daily test sets that limit, so a guard counted every call).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `auto-cut-report-states-the-commands-whol` (Whole cost) | Done | Red run against a skeleton (commit `7b3caaf`), then the implementation (`9162eaf`), then a daily payload pin (`3673c7a`). 12 mutants, all caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the auto-cut report carries `command_cost_usd`, equal to what the budget counted for the whole command, beside `cost_usd`, by tests shown failing first | PASS | Red: 12 failed / 24 passed against the skeleton (below). Green: the node's command, 27 passed. `test_auto_cut_with_expand_llm_reports_the_whole_commands_cost_beside_the_cuts_cost` checks `command_cost_usd` against the run's usage records and that it is the key after `cost_usd`. `test_the_auto_cut_command_cost_is_what_the_per_run_limit_counted_through_every_router` checks it against the `spent_usd` of a refusal from the run's second guard. |
| Node: Whole cost tests pass (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "auto_cut and cost"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 -q -p no:cacheprovider packages/debate_core/tests packages/debate_cli/tests -k "auto_cut and cost"` → `27 passed in 53.97s`, exit 0 |

### The red run, against a skeleton

The skeleton commit `7b3caaf` added the report field, the payload keys, the container wiring and
`RunSpend`. In it, `RunSpend.usd()` returned 0.0, `BatchCutService` ignored the run it was given, and
the `Model cost:` line was unchanged. Every new test was run against it
(`hard_stop.py 115 ... pytest -n 4 --tb=line` over the five files, selected with `-k`) → `12 failed, 24
passed in 18.18s`. Each failure is an assertion, none an error:

| Test | Failed at |
|---|---|
| `test_the_auto_cut_command_cost_counts_the_runs_own_calls_on_every_day_it_ran` | `assert 0.0 == 0.375` |
| `test_the_auto_cut_command_cost_asks_the_ledger_for_the_run_as_its_guards_do` | `assert 0.0 == 0.0123` |
| `test_a_usage_log_that_cannot_be_read_makes_the_auto_cut_command_cost_unknown` | `assert 0.0 is None` |
| `test_the_auto_cut_command_cost_is_what_the_per_run_limit_counted_through_every_router` | `assert 0.0 == 0.0066 ± 6.6e-09` |
| `test_the_auto_cut_report_reads_the_whole_commands_cost_from_its_run_once_the_cuts_are_over` | "the expansion's $0.02 and the cuts' $0.015" |
| `test_a_replayed_auto_cut_with_nothing_else_spent_costs_the_command_nothing` | `(0.0, None) == (0.0, 0.0)` |
| `test_an_auto_cut_whose_command_cost_more_than_its_cuts_names_both_costs` | `'Model cost: $0.0150' == 'Model cost: ...hole command)'` |
| `test_auto_cut_with_expand_llm_reports_the_whole_commands_cost_beside_the_cuts_cost` | "what the budget run counted" (None) |
| `test_auto_cut_with_expand_llm_names_the_whole_commands_cost_under_its_table` | the line's ending |
| `test_auto_cut_without_expand_llm_costs_the_command_its_cuts_and_prints_the_cost_line_unchanged` | `None == 0.672052 ± 6.7e-07` |
| `test_auto_cut_with_fixture_answers_costs_the_command_nothing` | `(0.0, None) == (0.0, 0.0)` |
| `test_daily_auto_cut_costs_the_whole_command_what_its_cuts_cost` | "what the budget run counted" (None) |

The 24 that passed against the skeleton are the tests that pin unchanged behaviour (the line kept as it
was, an unknown run left null, the unpriced cut) and t17's live tests, run beside them to check that the
stand-in still works after it moved. `test_daily_auto_cut_payload_carries_the_reports_command_cost_beside_its_cuts_cost`
was added after green, because the daily command's own tests cannot tell the two keys apart. Its red is
the daily payload mutant below.

### Mutants

The PM's two mutants and ten more, one replacement each, run with
`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 4 -q --tb=no -rf` over the five
test files with the same `-k`, then restored with `git checkout HEAD --`. All were caught, each at an
assertion (no collection or import error). No property tests are involved, so there was no Hypothesis
database.

| Mutant | Caught by |
|---|---|
| `command_cost_usd = cost_usd` (PM) | 4 tests: the batch service's run read and unreadable-run tests, both `--expand-llm` CLI tests |
| `command_cost_usd` recomputed from the entries, `sum(entry.cost_usd or 0.0 ...)` (PM) | the same 4 |
| The run read before the walk instead of after | 6: the batch service's run read, both `--expand-llm` CLI tests, the search test without `--expand-llm`, both daily tests |
| The unpriced-cut rule dropped | `test_an_unpriced_cut_makes_the_auto_cut_reports_command_cost_unknown_too` |
| `RunSpend` returns the day's spend, not the run's | 3 budget tests |
| `RunSpend` lets an unreadable log raise | `test_a_usage_log_that_cannot_be_read_makes_the_auto_cut_command_cost_unknown` |
| The container gives the service no run | 5 CLI tests (search and daily) |
| The line never names the command | the hand-built "names both costs" test, `test_auto_cut_with_expand_llm_names_the_whole_commands_cost_under_its_table` |
| The line names any known command cost | 5: two hand-built "keeps the line" tests, the fixture-answers test, the search test without `--expand-llm`, the daily line test |
| The line compares raw floats | 3: two hand-built tests and the live search test without `--expand-llm` (the last-bits difference above) |
| Search's payload writes `cost_usd` under `command_cost_usd` | `test_auto_cut_with_expand_llm_reports_the_whole_commands_cost_beside_the_cuts_cost` |
| Daily's payload writes `cost_usd` under `command_cost_usd` | `test_daily_auto_cut_payload_carries_the_reports_command_cost_beside_its_cuts_cost` |

### Checks before the report

| Check | Result |
|---|---|
| Touched test files whole (`test_budget.py`, `test_batch_cut_service.py`, `test_batch_report_command_cost_line.py`, `test_batch_report_refused_line.py`, `test_search_command.py`, `test_daily_command.py`, `test_presenters_configuration_gaps_named_with_their_cure.py`), `hard_stop.py 115 ... -n 4` | `275 passed in 12.62s`; with `-m slow`, no test (these files hold no slow test) |
| Always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`), `-m "not slow and not live"` | `379 passed in 21.17s` |
| `packages/debate_core/tests/integrations/models` (the usage log and the factory, `budget.py`'s users) | `566 passed in 6.03s` |
| `packages/debate_core/tests/application` | Stopped by `hard_stop.py` at 115 s at 96%, with no failure printed, at a load average of 8 to 12 from other work on the machine. The session's permission check refused a run of the directory in two halves, which came too close to agreement 10's "never in parts", so the rest is left to CI. Its two changed test files ran whole above. |
| `uv run scripts/affected_tests.py` | `771 of 771 test files (100.0%) chosen`: the root conftest imports `fake_router`, then `debate_core.integrations.models`, then `factory`, then `budget.py`. Not run: under agreement 10 an affected set over about two minutes goes to the pull request's `ci` check, which runs the whole selection, and not to the operator. |
| `uv run --frozen ruff check .`, `ruff format --check .` | clean; 2133 files already formatted |
| `uv run --frozen pyright` (whole project, as CI) | `0 errors, 0 warnings, 0 informations` (38 s) |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 74 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 685 files, 41 epics, 622 tasks, 22 releases` |
| `scripts/check_command_blocks.py`, `scripts/check_links.py` | OK: 721 blocks in 261 files; 3900 links and anchors in 676 files |

## Files changed

* `packages/debate_core/src/debate_core/application/budget.py`: `RunSpend`, the run's spend as its
  guards read it, or None when the usage log cannot be read.
* `packages/debate_core/src/debate_core/application/batch_cut_service.py`: the `CommandSpend` protocol,
  the service's `command_spend` parameter, `BatchReport.command_cost_usd` read after the walk, and the
  module's Cost section.
* `packages/debate_cli/src/debate_cli/container.py`: `run_spend()`, given to `BatchCutService`. Wiring
  only.
* `packages/debate_cli/src/debate_cli/presenters/batch_report_presenter.py`,
  `presenters/daily_presenter.py`: the `command_cost_usd` key after `cost_usd`, and `_cost_line`, which
  compares the two figures as printed. `search_auto_cut.py`: its docstring names the key.
* `docs/guides/daily-digests.md`: "What a run cost" under `--auto-cut`, and the `--max-cost` bullet
  corrected.
* Tests: `test_budget.py` (4), `test_batch_cut_service.py` (5), the new `test_batch_report_command_cost_line.py`
  (6), `test_search_command.py` (4), `test_daily_command.py` (2, and a `live_models` seam like
  search's). The live Bedrock stand-in that t17 wrote in `test_search_command.py` moved unchanged to
  `packages/debate_cli/tests/ceiling_spending_bedrock.py`, so the daily tests can use it too.

## Deviations from the spec

* **`docs/guides/daily-digests.md` is outside `constraints.packages`.** The spec's description ("say
  in the guide which is which") and the PM's item 3 both ask for it, so I edited it.
* **The guide's `--max-cost` bullet now leaves out `daily`.** It said `--max-cost` works on
  `daily --auto-cut`, which has no such option (What I found). It now says that `--max-cost` is
  `search --auto-cut`'s, and that `models.budget_usd_per_run` holds a `daily --auto-cut` the same way.
  This is one bullet in the section the task already edits. Revert it if adding `--max-cost` to `daily`
  is the intended fix (Follow-up work).

## Decisions and assumptions

* **When a cut's call has no price, `command_cost_usd` is null.** The run's total counts an
  unpriced call as nothing, as the limit does. A number would then read low beside a `cost_usd` that
  says "unpriced". The cuts are part of the command, so when their cost is unknown, so is the command's.
  This sets the key to null and computes nothing from the entries. It can happen only with no limit set,
  because under a limit the guard refuses an unpriced call before it is made.
* **When the usage log cannot be read, `command_cost_usd` is null** and the command goes on. Without a
  limit nothing read the log before, so a damaged line must not fail a run after its cuts are made and
  before its bundle is written.
* **The line compares the figures as printed** (`$%.4f`), for the reason in What I found. This is
  presentation, in the presenter. The figures themselves are the report's.
* **The figure is read in the application, after the walk.** The service holds the run reader and the
  report holds the figure, so `debate_cli` decides nothing. Export calls no model, so reading the run
  before the bundle is written misses nothing.
* **The PM's wording is used for `daily` too.** The line names `--max-cost`, which `daily` does not
  have. It cannot appear in `daily` today, because there the two figures are always equal.

## Operator follow-ups

None. The whole-selection run is the pull request's `ci` check (agreement 10).

## Follow-up work

* **An unpriced expansion call is not reflected in `command_cost_usd`.** With no limit set and a
  `search.expand` route the pricing file does not price, the run's total counts that call as nothing,
  while `cost_usd` is still a number. Making it null needs the usage log (`debate_core.integrations.models.usage`,
  outside this task's packages) to count unpriced records per run as it counts their cost. This belongs
  to E08 or the upkeep epic.
* **Should `daily` take `--max-cost`?** It is the PM's call (E08). The guide now matches the code.

A relay block for the PM, bundling both questions:

```text
v1-e08-t22 asks two questions (session report, Follow-up work):
1. daily has no --max-cost (its auto-cut passes None; only models.budget_usd_per_run limits it). The guide said it had one, and I corrected the guide. Options: (a) leave it, so daily is limited by the setting only; (b) a task adds --max-cost to daily. Recommendation: (b), since coaches run daily --auto-cut and the search option is what the guide teaches. Until then, (a) is accurate.
2. An unpriced search.expand call, with no limit set, adds nothing to command_cost_usd. Options: (a) accept it, because under any limit the guard refuses an unpriced call first; (b) a task makes the usage log count unpriced records per run, so command_cost_usd can be null. Recommendation: (a), unless the beta runs without a limit.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
