# Session report: v1-e05-t15-monthly-model-budget

| | |
|---|---|
| Task | `v1-e05-t15-monthly-model-budget` — A monthly model budget beside the daily one, at the coach's $50 ceiling |
| Spec | [`plan_specs/v1/e05-model-router/t15-monthly-model-budget.yaml`](../../plan_specs/v1/e05-model-router/t15-monthly-model-budget.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t15-monthly-model-budget` |
| Session status | COMPLETE |

## Summary

`models.budget_usd_monthly` now holds the calendar month in America/Chicago the way
`budget_usd_daily` holds the day: the budget guard refuses, before it is made, a call whose ceiling
could take the month past the limit, by the same comparison (a call landing exactly on the limit is
made), and an unpriced model is refused whenever any of the three limits is set. The month's spend is
read from the usage log under the data directory, each record placed by its own timestamp, not by
the name of the day file it is in. Both bundled profiles set the month to $50; prod's daily limit
falls from $20 to $1.50 and dev's stays $2. `debate-research usage` shows the month's spend and both
limits under the day's total, in `--json` and the table, and a refusal names `per-run`, `per-day` or
`per-month` and what remains of it. The counts (ac1) found one usage log, the Mac's dev data
directory, that sees every model call that can be made today, so there was no stop. Look first at
**Counts**, then at **Decisions** 1 and 2 (the month read from each record's timestamp, and the
files read one day either side of the month).

## Counts (ac1)

Taken read-only on the operator's Mac on 2026-10-27, before any code changed.

| Where | What was found |
|---|---|
| The Mac's dev data directory, `~/.debate-research/dev` | Exists. It has **no `usage/` directory**: 0 usage files, 0 records. No real model call has been logged anywhere yet. |
| Prod's data directory, `~/.debate-research/prod` | **Does not exist.** Prod publishes have run with `DEBATE_STORAGE__DATA_DIR` naming dev's directory, so a prod-environment run with that override would log into dev's `usage/` too. |
| Any usage file anywhere on the Mac | `find ~/.debate-research ~/Documents/debate /private/tmp -path '*/usage/*.jsonl'` found **0 files**. |
| Overrides that move a run's data directory | No `DEBATE_*` variable in the shell. No `.env` in the main checkout or in any of the 8 worktrees sets a `DEBATE_*` data-directory, environment or model key. |
| The Mac's launchd agents | **1** (`com.debate-intelligence.caselist-sync`, `DEBATE_ENV=dev`). It runs `caselist pull` (or `doctor` in its check mode), which makes no model call. |
| The cloud task (`ops/caselist_run`) | Runs `caselist pull` and `caselist auth renew` from an installed build. Neither makes a model call. The landscape's model stage refuses to run outside a source checkout (it reads `prompts/`), and the image is not one. The task's role has no Bedrock permission: nothing under `infrastructure/modules/caselist_run` names Bedrock. |
| Who can call Bedrock | Only the SSO permission sets of `infrastructure/modules/bedrock_access` (`bedrock:InvokeModel`), used through `models.aws_profile` (`debate-dev-bedrock`). Prod's grant is applied by `v1-e05-t17`, still Pending, so prod cannot call a model today. |
| Code that builds a router able to reach a model | One site: `ServiceContainer.landscape_model_stage` (`packages/debate_cli/src/debate_cli/container.py`), used by `landscape run --model-mode live\|record` and `landscape evaluate --model-mode record`. It passes `usage_log=self.usage_log()`, the log under the settings' data directory. No script under `scripts/` or `tests/evals/` builds one. The Bedrock runbook's access probe calls the adapter directly and is not logged, as the runbook already says. |
| How the log's files and entries are dated | Files are named by the date in **this machine's zone** (`UsageLog(local_zone=None)`, `local_day`); the Mac's zone is America/Chicago (`/etc/localtime`). Each entry's `recorded_at` is **UTC**. |

**Does one usage log see every call a month makes?** Yes, today. Every call that can be made is
made on the operator's Mac, from a source checkout, signed with the dev Bedrock profile, and logged
to `<data_dir>/usage/`, which for every configuration found is `~/.debate-research/dev/usage/`. A
single guard over that directory sees the month. What it cannot see, and what the AWS Budgets alarm
(`v1-e05-t16`) is for: a run whose `DEBATE_STORAGE__DATA_DIR` names some other directory (a scratch
store, as on 2026-10-22), a run under `DEBATE_ENV=prod` with no override once prod's grant exists,
the runbook's unlogged probe, and any other machine.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `monthly-budget` (Monthly model budget) | Done | Counts first, then a refuse-nothing skeleton with the tests run red against it (`fe98b57`), then the implementation (`5fc1865`), and two test strengthenings from the mutation run (`cf5080e`, `c67a59e`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, where calls are made and logged, and whether one log sees a month's calls, in the report | PASS | **Counts**, above: read-only `ls`/`find`/`plutil`/`git grep`, taken before the first edit. |
| ac2: a call that could take the month past `models.budget_usd_monthly` is refused before it is made, across a month's boundary in America/Chicago, by tests shown failing first; both profiles set 50.0 and prod's daily limit is 1.5 | PASS | **Red**, against the skeleton commit `fe98b57` (month unchecked, profiles unchanged): `.venv/bin/python -m pytest -p no:randomly -n 0 --tb=line` over the eight touched test files → `28 failed, 379 passed`, plus `tests/smoke/test_cli_smoke.py::test_dev_and_prod_get_their_own_data_directory_routing_file_and_budget` → `1 failed` (`assert (2.0, 20.0) == (2.0, 1.5)`). Every one failed at an assertion for its reason: `DID NOT RAISE BudgetExceededError` (month across days, month at midnight in Chicago for files named in Chicago and in UTC, month beside a daily limit, in-flight holds, factory), `DID NOT RAISE UnpricedModelError` (monthly limit alone), `month_usd=0.0 == 0.875`, `20.0 == 1.5`, `None == 50.0`, `KeyError: 'month'`. **Green**, at `5fc1865`: the same files → `408 passed in 5.44s`. Profiles: `test_committed_dev_and_prod_profiles_differ_in_data_dir_and_routing_file_and_set_their_budgets` pins dev 2.0 / prod 1.5 a day and 50.0 a month each, read from `config/profiles/{dev,prod}.toml`. |
| ac3: `debate-research usage` shows the month's spend and the limit, by test | PASS | `test_usage_json_shows_the_month_s_spend_and_both_limits_beside_the_day_s`, `test_usage_table_shows_the_month_s_spend_and_both_limits_under_the_day_s_total`, `test_usage_without_a_date_shows_this_month_in_chicago`, `test_usage_shows_an_unset_limit_as_none` (red at `fe98b57`, green since). |
| Node `monthly-budget`: Model router tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/models` → `528 passed in 3.36s`. |

### Mutation run (agreement 8)

17 mutants over `budget.py`, `usage.py`, `factory.py`, `settings.py`, the `usage` command and the two
profiles, one at a time, each against `test_budget.py`, `test_usage.py`, `test_factory.py`,
`test_usage_command.py`, `test_settings_environments.py`, `test_settings.py` and
`test_config_command.py`, each run with `HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty directory
(none of these tests uses Hypothesis), each source file restored after its run and `git status`
clean after each batch. No run errored.

| Mutant | Result |
|---|---|
| PM 1: the month taken in UTC (`CalendarMonth.of` reads UTC) | Caught, 42 tests, e.g. `test_a_moment_s_month_is_its_month_in_chicago[november-small-hours]` |
| PM 2: the monthly check skipped when a daily limit is also set | Caught, 2: `test_the_month_counts_every_day_of_it_and_not_only_today`, `test_the_month_is_checked_when_the_run_and_the_day_have_room` |
| PM 3: the monthly check reading only today's file | Caught, 5, e.g. `test_the_month_counts_every_day_of_it_and_not_only_today` |
| PM 4: an unpriced model allowed when only the monthly limit is set (`enforced` ignores the month) | Caught, 7, e.g. `test_an_unpriced_model_is_refused_whichever_limit_alone_is_set[month-limit-only]` |
| The month taken from the file's name, not the record's time | Caught, 3 |
| No margin day either side of the month | Caught, 7 |
| A file's month total overwritten, not added to | **Survived** the first run. `c67a59e` makes the same-file ledger test assert the month; then caught |
| The factory drops the monthly limit | Caught, 3 |
| `remaining_usd` is the limit | Caught, 5 |
| `month_usage` keeps the margin days' other-month records | Caught, 4 |
| `month_usage` counts no call as unpriced | Caught, 4 |
| `usage` reports the daily limit as the monthly one | Caught, 3 |
| `usage`'s table loses its month label | Caught, 1 |
| The built-in prod daily limit back at $20 | Caught, 1 |
| `dev.toml` loses its `budget_usd_monthly` line | Caught, 1, after `cf5080e` pinned where dev's value comes from (written before this run: the built-in $50 would have masked it) |
| `prod.toml`'s month at $60 | Caught, 4, e.g. `test_no_committed_or_built_in_budget_is_above_the_coach_s_ceiling[prod]` |
| December's last day off by a month | Caught, 1 |

### Checks before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (the list, not `--run`) | 357 of 547 test files (65.3%), because `settings.py` is imported by the root `conftest.py`. That is past two minutes, so under agreement 10 it is left to the pull request's `ci`, which runs the same affected set. Not run here. |
| The touched test files, the test directories of the router, the always-run list and the docs checks: `.venv/bin/python -m pytest -n auto -q -m "not slow and not live" tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py packages/debate_core/tests/integrations/models packages/debate_core/tests/integrations/bedrock packages/debate_core/tests/application/test_budget.py packages/debate_core/tests/application/test_settings.py packages/debate_core/tests/application/test_settings_environments.py packages/debate_cli/tests/test_usage_command.py packages/debate_cli/tests/test_config_command.py packages/debate_cli/tests/bucket_mode/test_bucket_mode_lock.py tests/smoke/test_cli_smoke.py` | `1419 passed in 34.18s` (load average about 20). The whole of `packages/debate_core/tests/application/` (172 files) and `packages/debate_cli/tests/` did not fit in the remaining two minutes at that load, and are in the affected set CI runs. |
| `uv run --frozen ruff check .` / `uv run --frozen ruff format --check .` | All checks passed / 1535 files already formatted |
| `uv run pyright packages/debate_core packages/debate_cli tests/smoke/test_cli_smoke.py` | 0 errors, 0 warnings |
| `uv run --frozen lint-imports` | 18 kept, 0 broken |
| `uv run --frozen python scripts/check_thin_handlers.py` | 67 handlers within 25 statements |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | All 56 indexed documents have a description |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | No `#` comments in 513 shell code blocks |
| `uv run scripts/validate_specs.py`, after the phase was set to Succeeded | `OK: 490 files, 40 epics, 428 tasks, 22 releases` |

### After the pull request's first `ci` run

Part 8 of 8 of the affected set failed, and `ci` failed with it:
`packages/debate_cli/tests/test_version.py::test_config_show_differs_between_dev_and_prod_in_an_installed_build[prod-20.0]`,
`assert 1.5 == 20.0`. A fifth test, beyond the four the PM named, pinned prod's old $20 a day, through the installed build's
`config show`. The hunt for tests that assumed the old values missed it, and it was in none of the
files run here. It now states dev's $2 and prod's $1.50 a day and why, and also pins each
environment's $50 a month. Reproduced and checked locally with CI's own selection
(`scripts/ci_test_selection.py` against base `ff1e8b3`: the same 357 files) and the same command
as CI's part 8 (`pytest -n auto -m "not slow and not live" --part 8/8`):

* Before the fix: part 8's tests in its settings-related files gave `1 failed, 235 passed`, the same failure as CI.
* After the fix: all of part 8 gave `1249 passed in 104.06s`.

Parts 1 to 7 passed in CI.

## Files changed

* `packages/debate_core/src/debate_core/application/budget.py`: `CalendarMonth` and
  `BUDGET_MONTH_ZONE` (America/Chicago); `BudgetLimits.per_month_usd`, in `enforced`;
  `Spend.month_usd`; the ledger's `month` argument; the guard's `per-month` check in the same loop and
  comparison as the run's and the day's; `BudgetExceededError.remaining_usd`, in its message.
* `packages/debate_core/src/debate_core/integrations/models/usage.py`: the ledger adds each record's
  cost to its own Chicago month, over `month_paths(month)` (the month's day files and one either
  side); `month_usage(month)` and `MonthUsage` for the CLI.
* `packages/debate_core/src/debate_core/integrations/models/factory.py`: `budget_limits` passes the
  monthly limit, so the guard is built when only it is set.
* `packages/debate_core/src/debate_core/application/settings.py`: `models.budget_usd_monthly`;
  `MONTHLY_MODEL_BUDGET_CEILING_USD = 50.0`; built-in dev and prod at $50 a month, prod at $1.50 a day.
* `config/profiles/dev.toml`, `config/profiles/prod.toml`: `budget_usd_monthly = 50.0`; prod's
  `budget_usd_daily = 1.5`; the comments say why, and no longer say prod's daily limit is never dev's.
* `packages/debate_cli/src/debate_cli/commands/usage.py`: `month` and `limits` in the JSON; Daily
  limit, Month and Monthly limit rows under the table's Total, which now always shows.
* Tests: `test_budget.py`, `test_usage.py`, `test_usage_command.py` (the month, the limits, the
  mutants); `test_factory.py`, `test_record_replay.py` (the ledger's new argument and the settings
  list); `test_settings_environments.py`, `test_settings.py`, `test_config_command.py`,
  `tests/smoke/test_cli_smoke.py`, `packages/debate_cli/tests/test_version.py` (each states dev's
  and prod's values and why instead of an ordering or prod's old $20; the bundle fixture's own
  values moved to $1.75 and $1.25 a day, which no committed profile has).
* `docs/process/branching-and-environments.md`: the Model spend row and a "Model spend" paragraph
  replace "prod's is $20" and "never share a daily model budget". `docs/runbooks/bedrock-access.md`:
  the month in the budget sentence and in what `usage` shows.

## Deviations from the spec

None. The counts did not call for a checkpoint.

## Decisions and assumptions

1. **The month is read from each record's timestamp, not from the file's name.** Files are named by
   the date in the machine's zone, which on the Mac is Chicago but on a machine in UTC is not; entry
   timestamps are UTC. So each record's `recorded_at` is converted to America/Chicago and that month
   is the one it counts toward. `test_the_month_turns_at_midnight_in_chicago_not_in_utc` runs it
   with files named in Chicago and in UTC.
2. **A month's records are looked for in its own day files and one day either side**
   (`MONTH_FILE_MARGIN`): no zone's date is more than a day from Chicago's, so a record of the month
   can be filed at most one day outside it. That is 30 to 33 file opens per guarded call, most of
   them for files that do not exist; each file is read only from where the last read stopped.
3. **The day's limit is still the machine's local day**, as `v1-e05-t07` built it. On the Mac that
   is Chicago's day too. Only the month was ruled to be Chicago's.
4. **`usage --date D` shows D's month; `usage` with no date shows the month it is now in Chicago.**
5. **A refusal's remaining amount is `max(0, limit − spent or held)`**, a count like the others in
   the message, and is in the JSON `details` as `remaining_usd`.
6. **The `test` profile sets no monthly limit.** Its $0 day already refuses any real call, and the
   spec names the two bundled profiles.
7. **Built-in profiles carry the same values** as the bundled ones ($2 / $1.50 a day, $50 a
   month), so a wheel built without `config/profiles/` is held to the coach's ceiling too.
8. **`MONTHLY_MODEL_BUDGET_CEILING_USD`** is a named constant, and a test checks that no committed or
   built-in dev or prod budget (run, day or month) is above it, for the forbidden "raising any
   budget above the coach's ceiling". Dev's $2 a day over thirty days is $60, so the check is on each
   budget, not on a day times thirty; the month holds the total.

## Operator follow-ups

None.

## Follow-up work

* A model call made with `DEBATE_STORAGE__DATA_DIR` naming another directory is logged there and
  is not in the dev log's month. When prod's grant is applied (`v1-e05-t17`) and prod runs with its
  own data directory, dev and prod will each hold $50 separately, $100 between them, until the
  promotion lowers one; the AWS Budgets alarm (`v1-e05-t16`) is what sees the account's total. The
  PM may want the promotion task to name which profile's month drops.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-27

**Notes:**

The month is held the way the day is, by the same comparison, and the counts showed where its blind
spots are.
1. **ac1 passes.** One usage log (`~/.debate-research/dev/usage/`) sees every model call that can be
   made today. Its blind spots are named: another data directory, prod once its grant exists, the
   unlogged probe and another machine. They are exactly what `v1-e05-t16`'s AWS alarm is for. No
   checkpoint was needed.
2. **ac2 and ac3 pass.** Red against the skeleton: 28 failed plus the smoke check, each at an
   assertion for its reason. Green: 408. The month turns at midnight in Chicago, with files named in
   Chicago or in UTC. Both profiles set $50 a month, and prod's daily limit is $1.50.
3. **Mutants: 17, the PM's four among them.** One survived (a file's month total overwritten) and was
   caught after the ledger test asserted the month. The `dev.toml` mutant needed the source pin first,
   because the built-in $50 would have masked it, and that pin was written before the run.
4. **Decisions accepted:**
   * the month read from each record's UTC timestamp, not the file name;
   * one margin day each side of the month;
   * the day still the machine's local day, as `v1-e05-t07` built it;
   * `usage` with no date showing this month in Chicago;
   * the remaining amount in the refusal;
   * the `test` profile without a month;
   * built-in values equal to the bundled ones;
   * the ceiling as a named constant, checked per budget.
   The 30 to 33 file opens per guarded call are fine at this volume (e32-t07's sample is about 500
   calls).
5. **The follow-up is taken.** When `v1-e05-t17` applies prod's grant, dev and prod would each hold
   $50, or $100 together. The PM amends `v1-e05-t17` so that the coach splits the $50 between the
   two profiles' monthly limits in that task, with dev $40 and prod $10 unless he says otherwise. The
   AWS alarm stays the account-wide check.
6. **The affected set** (357 files, widened by `settings.py` under the root conftest) is left to the
   PR's `ci` under agreement 10. The touched files, the router's directories, the always-run list and
   the docs checks passed (1,419), as did the static checks.

No re-review is needed. The Goal is `Succeeded`, and the PR merges in full. It changes nothing the
weekly run calls, so it may merge before Thursday's image.

### The coach's word on note 5, recorded by the PM 2026-10-27

Added in the PM batch of 2026-10-27 (w), since the note was written after this task's pull request was
pushed. The coach accepts $100 a month across the two environments ($50 in each profile, as built), on
one condition: model work is never duplicated between them. Note 5's split is withdrawn. The PM batch of
2026-10-27 (v) amended `v1-e05-t17` and `v1-e32-t07` so that a card's classification is made once, in
dev, and reused by prod, and `v1-e05-t16` to a $100 budget with its first notification at $50. Nothing in
this task changes.
