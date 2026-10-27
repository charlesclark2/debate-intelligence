# Session report: v1-e05-t07-usage-telemetry

| | |
|---|---|
| Task | `v1-e05-t07-usage-telemetry` — Token/cost telemetry and budgets |
| Spec | [`plan_specs/v1/e05-model-router/t07-usage-telemetry.yaml`](../../plan_specs/v1/e05-model-router/t07-usage-telemetry.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t07-usage-telemetry` |
| Session status | COMPLETE: phase Succeeded after the PM's rulings of 2026-10-26 (Deviations 1 and 2) |

## Summary

Every real model call, in record and live mode, is now recorded with its run, prompt, model,
attempt, tokens, latency, estimated cost and time. The records go to
`<data_dir>/usage/YYYY-MM-DD.jsonl`, priced from a new `config/model_pricing.yaml`. A
`BudgetGuard` refuses a call before it is made when its ceiling could take the run or the local
day past its limit. `debate-research usage` summarizes a day, and `debate_cli.options.budget`
gives commands a `--max-cost` option.

The chain sits where the PM's brief put it: `build_model_router` builds
`RecordReplay(BudgetGuard(UsageRecordingRouter(real router)))`. Replay and the fake router are not
wrapped. An invalid answer now carries its usage (`InvalidModelOutput.usage`, set by the Bedrock
adapter). That puts both attempts of a repaired call in the log and in the budget, which the spec's
2026-10-24 amendment asks for. A test shows the first attempt's tokens in the log.

Every plan-node criterion passes, and ac2, ac3 and ac4 pass. All 21 mutants are caught, including
the PM's three; one first survived and a test was added for it. The phase stays **InProgress**
because two things need the PM:

1. **ac1 fails as written and passes as amended.** "Every ModelResponse carries a UsageRecord"
   would mean a new field on a domain type (outside `constraints.packages`) and a change to every
   cassette.
2. **The budget setting names.** The brief names `models.budget.per_run_usd`/`per_day_usd`, but
   `models.budget_usd_daily` already exists for this guard. I built option A from the relay prompt
   and will apply whatever the ruling says.

**Look first at:** Deviations 1 and 2, and FYI 1 under Decisions. While prices are unset,
dev's and prod's daily limits refuse every record or live call.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `usage-pricing` | Done | `UsageRecord`, `ModelPrice`/`ModelPricing` and `search_units` in `integrations/models/usage.py`; `config/model_pricing.yaml` with every price unset |
| `recording-router` | Done | `UsageRecordingRouter` in `integrations/models/usage_router.py`; `UsageLog` (append, read, per-day ledger, summary) in `usage.py`; usage on `InvalidModelOutput` and `OutputAttempt`; wired in `build_model_router` |
| `budget-guard` | Done | `BudgetGuard`, `BudgetLimits`, `CallPricer`/`SpendLedger` ports and the three errors in `application/budget.py`; `RoutePricing` (the ceilings) in `usage_router.py`; `models.budget_usd_per_run` |
| `cli-surfaces` | Done | `debate-research usage` (`commands/usage.py`), `MaxCost`/`with_max_cost` (`options/budget.py`), the container's `usage_log()`; smoke check `tests/smoke/test_usage_smoke.py` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 Every ModelResponse carries a UsageRecord (run_id, prompt_id, model_id, tokens, latency_ms, estimated_cost_usd), appended to a local JSONL log | **FAIL as written / PASS as amended** (Deviation 2) | As written: `ModelResponse` (domain) is unchanged and carries `ModelUsage` (tokens, latency), not a `UsageRecord`. As amended ("every call made through the real router yields a UsageRecord … appended to a local JSONL usage log"): `test_record_holds_exactly_the_telemetry_fields_and_no_others` pins the exact keys, and `test_record_of_a_structured_call_names_its_run_prompt_model_tokens_latency_cost_and_time` pins hand-worked values. `uv run pytest packages/debate_core/tests/integrations/models/test_usage.py -k record` → 21 passed |
| ac2 Cost is computed from `config/model_pricing.yaml`; an unpriced model_id yields cost null and a warning | PASS | `test_pricing_an_unpriced_model_costs_null_with_a_warning_naming_it[test.unknown / test.unpriced]`, `test_record_of_an_unpriced_model_has_a_null_cost_not_zero`, `test_pricing_file_has_an_entry_for_every_model_the_routing_files_route`; no price appears in Python code |
| ac3 With a per-run budget of $0.05 and fixture usage over it, the next call raises BudgetExceededError and no request reaches the delegate | PASS | `test_ac3_with_a_five_cent_run_budget_spent_the_next_call_is_refused_and_reaches_no_router` (`delegate.calls == ["example.select-passage"]`), and the same through the factory: `test_build_model_router_holds_a_real_router_to_the_settings_run_budget[live/record]`. `uv run pytest packages/debate_core/tests/application/test_budget.py` → 24 passed |
| ac4 `debate-research usage --date 2026-09-17` prints calls, tokens and cost by prompt_id and model_id; `--json` gives the same data | PASS | `test_usage_table_shows_the_same_groups_and_a_total` and `test_usage_json_groups_a_days_calls_tokens_and_cost_by_prompt_and_model` over a hand-written day file. `--json` is the root option: `debate-research --json usage --date 2026-09-17` |
| Node `usage-pricing`: `uv run pytest …/test_usage.py -k pricing` | PASS | 21 passed in 1.43s |
| Node `recording-router`: `uv run pytest …/test_usage.py -k record` | PASS | 21 passed in 1.33s |
| Node `budget-guard`: `uv run pytest packages/debate_core/tests/application/test_budget.py` | PASS | 21 passed in 1.78s at the node; 24 after the factory tests were added |
| Node `cli-surfaces`: `uv run pytest packages/debate_cli/tests/test_usage_command.py` | PASS | 12 passed in 2.96s |
| Node `cli-surfaces`: `uv run debate-research usage --help` | PASS | exit 0; shows `--date YYYY-MM-DD  The local day to summarize. Default: today.` |
| PM brief: the first attempt's tokens of a repaired call are in the log | PASS | `test_record_both_attempts_of_a_repaired_call_first_attempt_tokens_included`: attempt 1 `example.select-passage` 900/60 tokens ($0.0012), attempt 2 `model.repair` 1200/40 ($0.0014); `result.attempts[n].usage` carries both. `test_both_attempts_of_a_repaired_call_count_against_the_budget` covers the budget |
| PM brief: a test checks the record's exact keys | PASS | `test_record_holds_exactly_the_telemetry_fields_and_no_others` |

### Red run (working agreement 8; the PM's red-first rule)

Commit `849d448` holds the skeleton: real signatures, and nothing recorded, priced or refused.
`.venv/bin/python -m pytest -p no:randomly -n 0 --tb=line` over the three new test files and the
adapter's new test gave **58 failed, 18 passed in 3.06s**. Grouped by their `E` lines, the failures
are:

* DID NOT RAISE ConfigurationError, BudgetExceededError or UnpricedModelError;
* null costs and zero spend where values were expected;
* missing day files (`FileNotFoundError` when a test reads the log);
* `[] ==` where groups or usages were expected.

None was a collection error. The 18 that passed:

* must-not-refuse cases: search units of 0 documents, partly-priced and unreported-token costs being
  null, a missing pricing file, a call with no answer not being logged, an empty day, the per-day
  ceiling that fits, no limit, a failed call letting go of its hold;
* the negative-limit and refusal-message rules, written into the skeleton;
* the `usage` command's empty-day, bad-date and help paths, plus `--max-cost` left out and below
  zero, because the command was written in final form.

### Mutants (21, each against the committed tree, each with a fresh `HYPOTHESIS_STORAGE_DIRECTORY`)

The runner applied each mutant exactly once and ran the four covering test files
(`test_usage.py`, `test_budget.py`, `test_usage_command.py`, the adapter's `test_router.py`) with
`-x -n 0`. It restored and byte-compared the source afterwards, and `git status` was clean after
each batch.

| # | Mutant | Result | Caught by |
|---|---|---|---|
| 1 | **PM:** the guard checks after the call | CAUGHT | `test_ac3_…_reaches_no_router` |
| 2 | **PM:** only the second attempt of a repaired call is counted (the recorder drops an invalid answer's usage) | CAUGHT | `test_record_both_attempts_of_a_repaired_call_first_attempt_tokens_included` |
| 3 | **PM:** an unpriced model is priced at 0 instead of null (`ModelPricing`) | CAUGHT | `test_pricing_an_unpriced_model_costs_null_with_a_warning_naming_it` |
| 4 | **PM, the guard's side:** an unpriced model's ceiling is 0 instead of null | CAUGHT | `test_an_unpriced_model_is_refused_naming_it_when_a_limit_is_set` |
| 5 | The guard ignores in-flight holds | CAUGHT | `test_calls_in_flight_hold_their_ceilings_so_a_burst_cannot_overspend` |
| 6 | The guard ignores this call's ceiling | CAUGHT | `test_both_attempts_of_a_repaired_call_count_against_the_budget` |
| 7 | `>` becomes `>=` | CAUGHT | `test_spend_exactly_at_the_limit_is_allowed_and_a_cent_more_is_not` |
| 8 | A finished call never lets go of its hold | CAUGHT | `test_ac3_…` |
| 9 | The day is the UTC date | CAUGHT | `test_record_holds_exactly_the_telemetry_fields_and_no_others` (the file is named for the wrong day) |
| 10 | Every call is recorded as attempt 1 | CAUGHT | `test_record_both_attempts_…` |
| 11 | The ceiling counts characters, not bytes | CAUGHT | `test_ceiling_counts_bytes_not_characters_and_a_call_s_own_output_cap` |
| 12 | The ceiling leaves out the input side | CAUGHT | `test_ac3_…` |
| 13 | Search units rounded down | CAUGHT | `test_pricing_cost_of_a_rerank_is_its_search_units` |
| 14 | The ledger skips an unreadable line | CAUGHT | `test_record_ledger_refuses_a_line_it_cannot_read_rather_than_skip_its_cost` |
| 15 | The ledger never re-reads a file | CAUGHT | `test_record_ledger_reads_lines_appended_after_its_last_read` |
| 16 | A line appended in two writes without the lock | CAUGHT | `test_record_lines_stay_whole_when_calls_and_threads_append_at_once` |
| 17 | The Bedrock adapter's refused answer carries no usage | CAUGHT | `test_an_invalid_answer_carries_the_usage_of_the_call_that_produced_it` |
| 18 | The structured-output guard keeps no usage for a refused attempt | CAUGHT | `test_record_both_attempts_…` |
| 19 | `build_model_router` never builds the guard | SURVIVED, then CAUGHT | First run: 173 passed. Commit `07769eb` added `test_build_model_router_holds_a_real_router_to_the_settings_run_budget` and `test_the_test_profile_s_zero_daily_budget_refuses_a_live_call_to_an_unpriced_model`; re-run: caught |
| 20 | `--max-cost` ignored | CAUGHT | `test_max_cost_sets_the_per_run_limit_for_the_one_command` |
| 21 | A price needs no `as_of`/`source` | CAUGHT | `test_pricing_file_that_is_not_the_schema_is_a_configuration_error_naming_the_key[price-without-as-of]` |

Each mutant run took 0.9 to 5.9 s. No test here uses Hypothesis.

### Tests and checks run before this report (working agreement 10)

`uv run scripts/affected_tests.py` chose **428 of 526 test files (81.4%)**: `settings.py` changed,
and the root `conftest.py` imports it through `ports/model_router.py`. That is well over two minutes,
so per agreement 10 it was **not** run and is left to the pull request's `ci`. Within the limit, I ran
the test directories of what changed and the always-run list, each wrapped in
`perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live"`:

| Run | Result |
|---|---|
| `packages/debate_core/tests/application`, `…/integrations/models`, `…/integrations/bedrock` | 4608 passed in 104.11s |
| `packages/debate_cli/tests --ignore=…/bucket_mode` | 1036 passed in 69.63s |
| `packages/debate_cli/tests/bucket_mode` | 99 passed in 78.67s |
| `tests/architecture tests/specs tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py tests/smoke/test_usage_smoke.py` | 483 passed in 15.24s |

Two runs hit the 115 s alarm while another worktree's suite held the load at 30–39. Neither left
an orphaned worker of this worktree (`pgrep` found none). Both were re-run split as above, and those
are the results shown.

| Check | Result |
|---|---|
| `uv run ruff format --check .` | ok |
| `uv run ruff check .` | All checks passed |
| `uv run --frozen pyright` (whole repo, as CI runs it) | 0 errors, 0 warnings |
| `uv run lint-imports` | 18 kept, 0 broken |
| `uv run python scripts/check_thin_handlers.py` | 67 handlers within 25 statements |
| `uv run python scripts/docs_index.py --check-descriptions` | all 53 described |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | no `#` comments in 504 blocks |
| `uv run scripts/validate_specs.py` | OK: 469 files, 40 epics, 407 tasks, 22 releases |

## Files changed

* **`packages/debate_core/src/debate_core/application/`**
  * `budget.py` (new): the guard, the limits, the ports and the errors.
  * `errors.py`, `model_errors.py`, `structured_output.py`: an invalid answer and each attempt carry
    their `ModelUsage`.
  * `settings.py`: `budget_usd_per_run`; `budget_usd_daily` is now optional (Deviation 1).
* **`packages/debate_core/src/debate_core/integrations/`**
  * `models/usage.py` and `models/usage_router.py` (new).
  * `models/factory.py`: the wiring, plus `budget_limits()`.
  * `bedrock/router.py`: the adapter puts Converse's usage on an invalid answer.
* **`packages/debate_cli/src/debate_cli/`**
  * `commands/usage.py` and `options/` (new).
  * `commands/__init__.py`: registration.
  * `container.py`: `usage_log()`, and the landscape stage's router gets the container's clock and
    usage log.
* **`config/model_pricing.yaml`** (new; pre-approved outside `constraints.packages`).
* **Tests:**
  * new: `test_usage.py`, `test_budget.py`, `test_usage_command.py`, `tests/smoke/test_usage_smoke.py`,
    and one adapter test in `test_router.py`.
  * changed, because the `test` profile's $0 limit now applies: `test_factory.py`'s `settings_with`
    and `test_prompt_registry_wiring.py`'s `settings` get no limit and a `tmp_path` data dir. The
    live wiring test now also asserts the call was logged.
  * changed pins: `test_factory.py` and `test_settings*.py` for the new and now-optional fields;
    `test_installation.py` and `test_doctor.py` for the container's new integration import
    (`models.usage`, 32 → 33); `test_bucket_mode_lock.py` classifies `usage` as never writing a
    bucket.
* **`docs/runbooks/bedrock-access.md`**: the one line the brief asked for, after Step 7.

## Deviations from the spec

1. **Settings names: ruled option A, as built (PM, 2026-10-26).**
   * The brief says "Limits come from settings: models.budget.per_run_usd and per_day_usd. Code has
     no default limit."
   * `models.budget_usd_daily` already existed: "Ceiling on model spend per day … Enforced by the E05
     BudgetGuard". Dev is 2.0, prod 20.0 and test 0.0; the dev cap is tested; about 50 files name
     it; settings use `extra="forbid"`.
   * I built option A from the relay prompt:
     * the per-day limit is `models.budget_usd_daily`, whose field default changes from `0.0` to
       `None` (no limit), so code holds no default;
     * the profile values are unchanged and now take effect;
     * the per-run limit is a new `models.budget_usd_per_run: float | None = None`.
   * The names are read in one place, `factory.budget_limits()`.
   * **PM ruling (2026-10-26):** option A, as built: `models.budget_usd_daily` and
     `models.budget_usd_per_run`. No code change followed.
2. **ac1's wording.** It is FAIL as written and PASS as amended; see the criteria table. Suggested
   amendment: "Every call made through the real router yields a UsageRecord (…) appended to a local
   JSONL usage log; the response keeps its ModelUsage."
   * **PM ruling (2026-10-26):** ac1 is amended as suggested, in the PM's next batch. ac1 is
     therefore PASS as amended, and the Goal is set to Succeeded.
3. **Outside `constraints.packages`**, each as the brief or the repo's rules require:
   * `config/model_pricing.yaml` and the settings change, which the brief pre-approved;
   * `docs/runbooks/bedrock-access.md`, which the brief asked for;
   * `tests/smoke/test_usage_smoke.py`, because `plan_specs/README.md` asks for a smoke check for a
     new command and the spec has no smoke node;
   * pinned tests outside the new files, listed under Files changed.
4. **The pricing file also prices `anthropic.claude-opus-5-5`.** The brief listed Haiku, Sonnet,
   Titan and Cohere, but prod routes `deep_audit` to Opus. A test requires an entry for every model
   id in every routing file.
5. **Rerank is priced per 1K search units.** The spec says "per search unit"; per 1K matches how
   the page lists it and the per-1K-token convention. `search_units` = ceil(documents / 100).

## Decisions and assumptions

* **FYI 1: fail closed while prices are unset.** Under option A, dev ($2/day) and prod ($20/day)
  have limits from the moment this merges, and every model is unpriced until the PM's price batch.
  So **every record or live model call in dev and prod is refused** with `UnpricedModelError`
  naming the model until the prices are committed. Replay and the fake router are unaffected.
  I built no bypass.
  * **Prices committed (PM addition, 2026-10-26).** The operator read the AWS Bedrock pricing page
    (us-east-1, on-demand) on 2026-10-26, and `config/model_pricing.yaml` now holds the PM's
    values, each with `as_of: 2026-10-26` and `source: https://aws.amazon.com/bedrock/pricing/`.
    So the gap above closes with this branch. Calls in dev and prod are now held to their daily
    limits at those prices, rather than refused as unpriced.
  * The tests that pinned "every price unset" now pin "every price set and well-formed":
    * `test_pricing_every_committed_price_is_set_and_well_formed` checks the PM's table, written
      by hand;
    * `test_pricing_the_committed_prices_price_each_kind_of_call` checks one hand-worked cost per
      kind of call;
    * `test_the_test_profile_s_zero_daily_budget_refuses_a_live_call_at_the_committed_prices` is
      now a per-day `BudgetExceededError` with a $0.0010263 ceiling.
  * Both pins fail when one price is changed (Haiku output 0.0005 → 0.005: 2 failed), and the
    file was restored byte for byte.
  * Commands run: `test_usage.py`, `test_factory.py`, `test_budget.py`,
    `test_prompt_registry_wiring.py` and `test_aws_extra.py` → 99 passed; ruff and pyright clean.
* **What a record holds**: `run_id, prompt_id, prompt_version, model_id, attempt, input_tokens,
  output_tokens, latency_ms, estimated_cost_usd, recorded_at`, and nothing else.
  * A repair is recorded as what was sent: `model.repair`, attempt 2. `max_repairs` is exactly 1,
    so a `model.repair` prompt is attempt 2.
  * Embed and rerank have null prompt fields and attempt 1.
  * `test_record_never_holds_prompt_variables_or_document_text` checks that invented words in a
    call's variables, texts and documents never reach the log.
* **Run.** One `build_model_router` call is one run, with a new `uuid4` run id. The landscape
  builds one per command.
* **Day.** The local date of the injected clock (`application.budget.local_day`). It both names the
  file and decides the per-day limit.
* **Latency.** The recorder measures it itself, around the delegate call, so it includes the
  adapter's throttling retries and backoff. `ModelUsage.latency_ms` is the successful attempt's only.
* **Estimate (ceiling).**
  * Generative: the route's `max_tokens` × the output price, plus the prompt variables' UTF-8 bytes
    × the input price, as compact JSON, since no tokenizer exceeds one token per byte. **Left out:**
    the prompt template's own wording, the system prompt and the tool's schema definition, which the
    adapter adds and the wrapper never sees. It also assumes `max_tokens` bounds every output token
    billed.
  * Embedding: the texts' bytes, a full bound.
  * Rerank: its search units, **leaving out** Cohere's splitting of long documents. Cohere also
    splits a document over 512 tokens into several, each counted as a document, so a rerank of long
    documents can bill more search units than ceil(documents / 100). The ceiling leaves that out,
    because a document's token count is not known before the call (PM note, 2026-10-26).
  * A route with no `max_tokens` cannot be bounded and is refused when a limit is set. No current
    route lacks one.
  * Because the input side is incomplete, a run's last call can overshoot a limit by what was left
    out. Post-call accounting then refuses every call after it.
* **Parallel calls.** Each call holds its ceiling under a lock from the check until it finishes.
  Appends are one `os.write` under `flock` on an `O_APPEND` file.
* **Ledger.** `UsageLog.spent` reads each day file from where it last stopped, so a long run never
  re-reads its day, and other processes' finished calls count. **Another process's in-flight calls
  do not count**, so two concurrent processes can each overshoot by at most one call's ceiling.
  An unreadable line raises `UnreadableUsageLog`, which refuses the call, rather than being skipped.
* **Pricing file location.** `model_pricing.yaml` beside the routing file, which settings already
  anchor to the checkout. `build_model_router(pricing_file=…)` overrides it. A missing file prices
  nothing, so costs are null with a warning naming the path, and calls are refused under a limit.
* **`--max-cost`** replaces `models.budget_usd_per_run` for one command (the brief's "sets the
  per-run limit"). It does not take the lower of the two.
* **Not logged:** an `InvalidModelOutput` with no `model_id` (no router raises one today); a call
  that got no answer, which reports no usage; and the `first_call` probe, which calls the adapter
  directly. The runbook line says so.

## Operator follow-ups

**Read the prices for `config/model_pricing.yaml`.** The PM commits them in a batch. This is
read-only and finishes in under a second. Where: your Mac, in the task worktree.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e05-t07-usage-telemetry
grep -h "model_id:" config/model_routing.dev.yaml config/model_routing.prod.yaml | sort -u
```

**What success looks like.** Five lines, which the session saw when it ran this:

* `amazon.titan-embed-text-v2:0`
* `anthropic.claude-haiku-5-5`
* `anthropic.claude-opus-5-5`
* `anthropic.claude-sonnet-5-5`
* `cohere.rerank-v3-5:0`

**What to send the PM.** Read the AWS Bedrock pricing page for us-east-1, on-demand: the
Claude models are called through the `us.` cross-region inference profiles. For each id, send:

| Model | Prices to send | Field names |
|---|---|---|
| Each Claude model | USD per 1,000 input tokens and per 1,000 output tokens | `input_usd_per_1k_tokens`, `output_usd_per_1k_tokens` |
| Titan embed | USD per 1,000 input tokens | `input_usd_per_1k_tokens` |
| Cohere Rerank 3.5 | USD per 1,000 queries | `usd_per_1k_search_units` |

Also send the date you read them (`as_of`) and the page's URL (`source`). If the page lists a
price per million tokens, divide by 1,000. If the page prices these models differently through a
cross-region profile, send that price and say so.

No other hand-off. The affected set (81% of the suite) is left to the PR's `ci` under agreement 10.

## Follow-up work

* **Bedrock cache tokens.** Converse can report `cacheReadInputTokens` and
  `cacheWriteInputTokens`; the adapter does not read them and `ModelUsage` has no field for them
  (not widened here, per the brief). They belong to v1-e05 if prompt caching is turned on.
* **Adopt `--max-cost`** in `landscape` (E32), `cut` (E06), auto-cut and `daily` (E08), as the
  brief scoped out. `options/budget.py`'s docstring shows the two lines a command adds.
* **Installed builds have no pricing file.** `scripts/stamp_build.py` bundles the profiles and
  routing files, not `model_pricing.yaml`, so an installed build's real calls would be unpriced.
  Today no installed build can make one: the model stage needs `prompts/` from a checkout. The
  bundle list and its pins belong with v1-e01-t09's stamping.
* **`config show` attribution.** A `--max-cost` override is not reported as the source of
  `models.budget_usd_per_run`, because `with_max_cost` copies the settings and does not re-layer
  them. Worth doing when a command adopts it.
* **Cross-process in-flight holds**, if two concurrent model-heavy processes become normal: a lock
  file beside the day's log.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-26

**Notes:**

Telemetry and budgets built where the brief put them, failing closed. The rulings below close the
two open questions, so the Goal can be `Succeeded`.
1. **Ruling on the settings names: option A, as built.**
   * The per-day limit stays `models.budget_usd_daily`. Its field default becomes `None`, so code
     holds no limit, and the profiles keep dev at $2, prod at $20 and test at $0.
   * The per-run limit is `models.budget_usd_per_run`.
   * The brief's `models.budget.*` names were the PM's error: an existing, tested setting already
     named the guard.
2. **Ruling on ac1: amended as the session suggests.** "Every call made through the real router
   yields a UsageRecord (run_id, prompt_id, model_id, input/output tokens, latency_ms,
   estimated_cost_usd) appended to a local JSONL usage log; the response keeps its ModelUsage."
   The PM amends the spec in the next batch, and ac1 passes as amended. Widening a domain type and
   every cassette for this would buy nothing.
3. **ac2 to ac4 and every node criterion pass.**
   * Red first: 58 failed against a skeleton. The 18 passes are must-not-refuse cases and paths
     written in final form, each named.
   * The exact-keys test and the never-logged-text test hold the record to telemetry only.
   * Both attempts of a repaired call are in the log and the budget (the 2026-10-24 amendment).
4. **Mutants: 21.** All are caught, the PM's three among them. Mutant 19 (the factory never builds
   the guard) survived first, and the two factory tests added for it in `07769eb` catch it.
5. **Deviations 3 to 5 accepted:**
   * the files outside `constraints.packages`, which the PM adds in the next batch;
   * the Opus entry, since prod routes `deep_audit` to it;
   * rerank priced per 1,000 search units.
6. **FYI 1 is accepted as the intended behaviour.** Until the prices are committed, every record or
   live call in dev and prod is refused by name. The `first_call` probe calls the adapter directly,
   so `v1-e05-t08`'s operator steps are unaffected. `v1-e32-t07`'s live run waits for the PM's price
   batch, which follows the operator's read of the AWS page.
7. **Decisions accepted:**
   * one run per `build_model_router`;
   * the local day for both the file and the limit;
   * latency measured around the delegate;
   * the ceiling's stated gaps;
   * in-flight holds within a process;
   * an unreadable ledger line refusing the call;
   * `--max-cost` replacing the per-run limit for one command, with the daily limit still applying.
8. **Follow-ups:** an installed build lacking `model_pricing.yaml` is filed by the PM with the
   build-stamping work. Cache tokens, adopting `--max-cost`, `config show` attribution and
   cross-process holds stay as listed.
9. **The affected set** (428 files, since `settings.py` changed) is left to the PR's `ci` under
   agreement 10. The changed directories and the always-run list passed, as did the static checks.

No re-review is needed. Set the Goal to `Succeeded`, and the PR merges in full.
