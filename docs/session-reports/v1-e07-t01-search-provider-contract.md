# Session report: v1-e07-t01-search-provider-contract

| | |
|---|---|
| Task | `v1-e07-t01-search-provider-contract` — SearchProvider contract, health and circuit breaking |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t01-search-provider-contract.yaml`](../../plan_specs/v1/e07-discovery-adapters/t01-search-provider-contract.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t01-search-provider-contract` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The discovery port is finalized, and the machinery every discovery adapter will use is in place.

* **The discovery values.** `ProviderQuery`, `CandidateResult` and `ProviderResponse` moved from
  `application/ports/providers.py`, which still re-exports them, into `domain/discovery.py`.
* **The wrapper and the registry.** In `debate_core.integrations.discovery`, `ResilientProvider`
  wraps any adapter with a timeout, a clock-driven circuit breaker, a Retry-After hold and a
  redacted health record. `ProviderRegistry` builds only the providers settings enable and reports
  their health.
* **The contract kit.** `debate_core.testing.contracts.search_provider` holds each adapter to
  seven rules on its own recorded respx fixtures. A `FakeProvider` passes it, and 16 fakes that
  each break one rule fail that rule's check.

All four Goal criteria and every node criterion pass, and the Goal is `Succeeded`.

**The PM should look first at the kit's location** (Deviations, first item). Your notes put it in
`packages/debate_core/tests/contracts/`, but t02 to t07 could not import it from there. I built it
where the repo's other shared contracts live and sent the question as a relay prompt; no answer had
arrived when this report was written. If you choose otherwise, moving it is mechanical.

The second thing worth reading is the log redaction. httpx logs every request URL at INFO, the
`mailto=` included. The kit fails an adapter for that, and
`integrations/discovery/redaction.py` is what a correct adapter uses to avoid it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `candidate-types` (CandidateResult, ProviderQuery and ProviderResponse) | Done | The three models moved, unchanged in meaning, to `domain/discovery.py`. Added `raw_ref`, a rule that a response's results all name its provider, and `BreakerState` and `ProviderHealth`. |
| `resilient-wrapper` (Timeout and circuit breaker wrapper) | Done | `integrations/discovery/resilience.py`: `CircuitBreaker` (closed, open, half-open with one probe), `ResilientProvider`, `ResiliencePolicy`. Also `http_failures.py` (HTTP status to error) and two new errors, `ProviderTimedOut` and `ProviderCircuitOpen`. |
| `registry-health` (ProviderRegistry and health metrics) | Done | `integrations/discovery/registry.py`, plus three non-secret `ProviderSettings` fields for the timeout and the breaker. |
| `contract-kit` (Provider contract test kit) | Done | `debate_core/testing/contracts/search_provider.py` (see Deviations), `integrations/discovery/redaction.py`, the FakeProvider binding and the broken fakes. |

The red runs (below) were taken node by node. The import-linter line in `pyproject.toml` was
committed last, after the affected-set measurement (see Tests run).

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — `SearchProvider.search(ProviderQuery) -> ProviderResponse(results, provider, elapsed, partial, error)` is the only discovery port; CandidateResult validates identifiers (DOI lowercase, no URL prefix) and a timezone-aware `published_at` | PASS | `uv run pytest packages/debate_core/tests/domain/test_discovery.py` → `32 passed`. `test_search_provider_is_the_only_port_that_answers_a_provider_query` checks every Protocol in `application.ports`. The DOI cases cover a resolver URL, an uppercase prefix, `doi:`, whitespace and bad input. The `published_at` cases cover naive, offset and ISO without offset. |
| ac2 — ResilientProvider enforces the configured timeout, opens the breaker after N consecutive failures, skips calls for the cool-down, then half-opens with a single probe | PASS | `uv run pytest packages/debate_core/tests/integrations/discovery/test_resilience.py` → `38 passed`. Every transition is written by hand on `debate_core.testing.fakes.FixedClock`, including a failed probe that reopens for a fresh cool-down, a cancelled probe, and late results that must not decide a half-open breaker. |
| ac3 — ProviderRegistry instantiates only enabled providers and exposes health snapshots (state, last error, p50 latency, success/error counts) | PASS | `uv run pytest packages/debate_core/tests/integrations/discovery/test_registry.py` → `18 passed`. No CLI footer: your ac3 ruling ("expose the health snapshots only"). |
| ac4 — a contract test kit (fixture loader and assertions) exists, a FakeProvider passes it, and each later adapter imports it | PASS (location pending your ruling) | `uv run pytest packages/debate_core/tests/integrations/discovery/test_fake_provider.py` → `42 passed`: three bindings run the full kit, and 16 broken fakes each fail their rule's check, matched on the check's own message. The kit lives in `debate_core.testing.contracts.search_provider`, where t02 to t07 can import it; see Deviations. |
| Node `candidate-types`: Discovery model tests pass | PASS | `uv run pytest packages/debate_core/tests/domain/test_discovery.py` → `32 passed in 1.62s` |
| Node `resilient-wrapper`: Breaker and timeout tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/discovery/test_resilience.py` → `38 passed in 1.53s` (path as amended by your ruling) |
| Node `registry-health`: Registry tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/discovery/test_registry.py` → `18 passed in 2.43s` (path as amended) |
| Node `contract-kit`: FakeProvider passes the contract kit | PASS | `uv run pytest packages/debate_core/tests/integrations/discovery/test_fake_provider.py` → `42 passed in 1.55s` (path as amended) |
| Node `contract-kit`: Import boundaries hold | PASS | `uv run lint-imports` → `Contracts: 12 kept, 0 broken.` |
| Epic plan `t01`: the task reports phase Succeeded | PASS | `uv run scripts/validate_specs.py --require-succeeded v1-e07-t01-search-provider-contract` → `v1-e07-t01-search-provider-contract: Succeeded` |

Your notes asked for these, each shown by a test:

| PM note | Where it is shown |
|---|---|
| Breaker clock-injected with `FixedClock`, imported from `debate_core.testing.fakes` | Every test in `test_resilience.py` and `test_registry.py`; no file imports from `debate_core.testing` itself. |
| Closed, open and half-open transitions written by hand, including a half-open probe that fails and reopens | `test_a_probe_that_fails_reopens_the_breaker_for_a_fresh_cool_down`; the wrapper version is `test_a_half_open_provider_sends_one_probe_and_skips_concurrent_calls`. |
| Never retries a non-idempotent request | The wrapper never retries anything: `test_a_failed_call_is_made_exactly_once`, three cases. The kit enforces it on adapters: `RetriesAPost` fails, `TestFakeProviderOverPost` passes. |
| Recorded fixtures only, no live provider call | Every HTTP exchange is served by respx from `tests/fixtures/discovery/fake_provider/`. An unmatched request raises. The suite's `--disable-socket` is unchanged. |
| Keys and contact email never in a log, an error, a health snapshot or a repr | `test_resilience.py::test_no_secret_reaches_an_error_its_cause_a_log_line_the_health_record_or_a_repr`, `test_registry.py::test_no_key_or_contact_email_reaches_…`, `test_redaction.py` (9 tests), and the kit's check 7 with four broken fakes. |

## Red runs

Each red run used the task's tests against a skeleton with the real signatures and none of the
behaviour, placed first on `PYTHONPATH` from a scratch copy of `src`. In each run I printed the
module's `__file__` first to confirm the skeleton was the copy loaded.

| Area | Skeleton | Result | What passed, and why |
|---|---|---|---|
| Domain values | `domain/discovery.py` without the two new validators | 4 failed, 28 passed | The failures were all `DID NOT RAISE`, on the stranger-result rule and the `open_until` rule. DOI and timezone validation already existed from v1-e02-t02, so those tests passed; mutants 16 to 20 show they bite. |
| Resilience | A pass-through `ResilientProvider` and an always-closed breaker | 29 failed, 5 passed, plus 4 hang-dependent tests run one by one | The two timeout tests hung until a 5 s alarm (exit 142); the two probe tests failed. The 5 passes were a new breaker being closed, a pass-through call, two "made exactly once" cases a non-retrying skeleton meets trivially, and the policy defaults. |
| HTTP mapping and errors | `provider_error_for_status` and `retry_after_seconds` returning `None`; the new errors without `ERROR_CODE` | 18 failed, 45 passed | The passes were the cases that expect `None` and the existing hierarchy's tests. |
| Registry | Builds every factory, uses the default policy, redacts nothing; settings fields without bounds | 16 failed, 2 passed | The 2 passes were "a factory is handed the settings" and "the defaults agree". |
| Contract kit | Every `assert_*` reduced to `return None` | 16 failed, 26 passed | All 16 broken-fake tests failed with `DID NOT RAISE`. The passes were the bindings, which a check-nothing kit lets through, the loader, and the empty-secrets case. |
| Log filter | `SecretLogFilter.filter` returning `True`, `protect_logs` a no-op | 7 failed, 44 passed | Among the failures is the kit's own secrets check on the correct GET fake: httpx's `HTTP Request:` line carried the `mailto`. |

## Mutation

There were 22 mutants, about the PM's cap of 20, on the breaker transitions, the timeout, the
rate-limit hold and identifier validation. The driver asserted a clean tree, saved each file's
bytes, ran that area's test file with `-x` under a 20 s alarm, restored the bytes and checked them,
and checked `git diff` at the end. **22 of 22 were caught.**

| # | Mutant | Caught by |
|---|---|---|
| 0 | Half-open only after the cool-down ends, not at its end (`>=` to `>`) | `test_the_breaker_half_opens_exactly_when_the_cool_down_ends` |
| 1 | Opens one failure past the threshold | `test_the_breaker_stays_closed_below_the_threshold_and_opens_on_it` |
| 2 | A closed success does not reset the count | `test_a_success_resets_the_count_so_only_consecutive_failures_open_the_breaker` |
| 3 | Half-open admits concurrent probes | `test_a_half_open_breaker_admits_one_probe_and_refuses_everything_else_while_it_runs` |
| 4 | A failed probe does not reopen | `test_a_probe_that_fails_reopens_the_breaker_for_a_fresh_cool_down` |
| 5 | A successful probe does not close | `test_a_probe_that_succeeds_closes_the_breaker` |
| 6 | Releasing any call frees the probe slot | `test_releasing_an_ordinary_call_does_not_free_the_probe_slot` |
| 7 | A late failure while open reopens (extends the cool-down) | `test_a_late_failure_while_open_does_not_extend_the_cool_down` |
| 8 | No cool-down | `test_the_breaker_stays_closed_below_the_threshold_and_opens_on_it` |
| 9 | A cancelled probe is never released | `test_a_cancelled_probe_leaves_the_breaker_half_open_for_the_next_call` |
| 10 | The rate-limit hold outlasts Retry-After by an instant (`<=` to `<`) | `test_a_rate_limit_holds_every_call_until_retry_after_has_passed` |
| 11 | Retry-After ignored, cool-down always | same |
| 12 | A rate limit sets no hold | same |
| 13 | Every `TimeoutError` is taken for the deadline | `test_an_adapters_own_timeout_error_is_not_mistaken_for_the_deadline` |
| 14 | No deadline at all (`asyncio.timeout(None)`) | The timeout test hung and SIGALRM killed pytest at 20 s, after 14 tests had passed. The driver printed `rc=-14` because it looked for the shell's 142. There was no pytest-timeout, so a hang is how this one is caught. |
| 15 | A timeout reported as plain `ProviderUnavailable` | `test_a_call_that_outlives_the_timeout_is_cancelled_and_reported_as_timed_out` |
| 16 | DOI not lowercased | `test_a_candidate_stores_a_doi_bare_and_lowercase_…[10.1126/SCIENCE.AAR7204-…]` |
| 17 | DOI prefix matched case-sensitively | the same test's `HTTPS://DOI.ORG/…` case |
| 18 | DOI registrant may be one digit | `test_a_candidate_refuses_a_doi_it_cannot_normalize[10.12/too-short-prefix]` |
| 19 | `doi:` prefix not stripped | the `doi:` case |
| 20 | `published_at` keeps its offset | `test_a_candidate_stores_an_offset_publication_time_in_utc`. This needed the `utcoffset() == 0` line: two aware datetimes for the same instant compare equal. |
| 21 | A response may carry another provider's result | `test_a_response_refuses_a_result_from_another_provider` |

The kit's own checks were shown biting by the 16 broken fakes in `test_fake_provider.py` (the
contract-kit red run above), one or more per check.

## Tests run

* **Affected set: not run whole.** `uv run scripts/affected_tests.py` selected **298 test files**
  (errors.py and settings.py are imported almost everywhere). That is well past the two-minute line;
  at a load of 6, about 190 files took about four minutes. Per working agreement 10 it is left to
  the pull request's `ci`, which runs the whole selection anyway, and is not handed to the operator.
  The selection was measured before the `pyproject.toml` commit. After that commit the script
  reports the whole selection as affected, because any `pyproject.toml` is shared test ground. The
  only change there is one name on an import-linter list.
* **What I ran within the two minutes**, once, on the tree before that last commit:

  ```bash
  .venv/bin/python -m pytest -m "not slow and not live" -n auto -q packages/debate_core/tests/domain packages/debate_core/tests/application packages/debate_core/tests/integrations/discovery packages/debate_core/tests/contracts packages/debate_core/tests/testing tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_config_command.py packages/debate_cli/tests/test_output.py packages/debate_cli/tests/test_recorded_failure_codes.py packages/debate_cli/tests/test_retryable_store_failures.py packages/debate_cli/tests/test_unmodelled_error_prints_no_text.py
  ```

  The result was `4138 passed in 71.70s`, under `perl -e 'alarm 115; …'` at a load average of 2.3.
  That covers the test directories of every changed module, the always-run list, and the CLI tests
  that read `errors.py` (exit and error codes) and `settings.py` (`config show`). After the
  `pyproject.toml` commit I ran `tests/architecture` again: `110 passed`.
* **Checks** (after the last format, in this order):
  * `uv run ruff format --check .` → clean
  * `uv run ruff check .` → `All checks passed!`
  * `uv run --frozen pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`
  * `uv run --frozen lint-imports` → `Contracts: 12 kept, 0 broken.`
  * `uv run scripts/validate_specs.py` → `OK: 396 files, 39 epics, 336 tasks, 21 releases`
  * `uv run scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 334 shell
    code blocks in 132 Markdown files (1 session reports changed since origin/dev)`
  * `tests/docs`, `tests/scripts/test_check_command_blocks.py`, `tests/scripts/test_docs_index.py`
    → `162 passed`

## Files changed

* **`debate_core.domain`**: `discovery.py` (new) holds the three discovery values, which moved
  here, plus `BreakerState` and `ProviderHealth`.
* **`debate_core.application`**:
  * `ports/providers.py` re-exports the moved values. The `SearchProvider` docstring now says it is
    the only discovery port, and that adapters are wrapped in `ResilientProvider` and held to the
    kit.
  * `errors.py` adds `ProviderTimedOut` and `ProviderCircuitOpen` under `ProviderUnavailable`.
  * `settings.py` adds three fields to `ProviderSettings`: `timeout_seconds`,
    `breaker_failure_threshold` and `breaker_cooldown_seconds`.
* **`debate_core.integrations.discovery`** (new): `resilience.py`, `registry.py`, `http_failures.py`
  and `redaction.py`. The `__init__` holds only a docstring.
* **`debate_core.testing.contracts`**: `search_provider.py` (new, the kit) and a `README.md`
  paragraph. The package `__init__` does not re-export it: import it from the submodule, as
  v1-e01-t29 asks.
* **Tests**: `tests/domain/test_discovery.py` and `tests/integrations/discovery/` (five files) are
  new. `test_errors.py` adds the two errors. `test_fakes.py` changes one test's data (see Decisions).
* **Fixtures**: `tests/fixtures/discovery/fake_provider/`, with invented bodies and a README.
* **`pyproject.toml`**: `debate_core.integrations.discovery` joins the boto3-forbidden source list.
  The contract's own comment asks for that "in the PR that creates it".
* **Spec**: your naming ruling. The resilience and registry outputs and the three test commands now
  use `integrations/discovery`, each with a `PM ruling 2026-10-20` comment. The phase is
  `Succeeded`.

### What changed in each existing type (your note: finalize in place, list the changes)

| Type | Before (v1-e02-t02) | Now |
|---|---|---|
| `ProviderQuery` | in `application/ports/providers.py` | Moved to `domain/discovery.py` and re-exported; no field changed. The spec's "text, since/until, max_results and language" are `query` and `filters` (`SearchFilters`), which already held all four. |
| `CandidateResult` | same module | Moved and re-exported. Added `raw_ref`, the slot the forbidden list allows for a provider's raw record. No field renamed. The spec's `provider_id` is `provider_record_id`, `venue` is `publication`, `abstract/snippet` is `snippet`, and "OA links" is the one `open_access_url` t02 asks for. |
| `ArticleIdentifiers` (the identifiers slot) | DOI normalization and PMID check | Unchanged, because it is inlined into the committed `Article` JSON Schema. The spec's `s2_id` is `semantic_scholar_id` and `arxiv` is `arxiv_id`. Tests through `CandidateResult` now cover the DOI rules. |
| `ProviderResponse` | `partial`/`error` check | Moved and re-exported. New rule: it refuses a result whose `provider` is not its own. |
| `SearchProvider` | async `search`, `name` | Signature unchanged; docstring extended. |
| `SearchProviderName` (settings) | five names | Unchanged. t07's government providers add theirs, as its docstring says. |
| `ProviderSettings` | `enabled`, three secrets | Three non-secret fields added, with bounds. |

## Deviations from the spec

1. **The kit's location: `debate_core/testing/contracts/search_provider.py`, not
   `packages/debate_core/tests/contracts/search_provider_contract.py`.** Your ruling is pending.
   Your notes said "in packages/debate_core/tests/contracts/, so that t02 to t07 import it", which
   repeats the spec's node output. Those two parts conflict: pytest runs with
   `--import-mode=importlib`, nothing under `packages/debate_core/tests/` is a package, and
   `pythonpath` holds only `tests/pytest_plugins`, so no other test file can import a module there.
   The repo's convention for a shared suite is `debate_core/testing/contracts/<port>.py`, and
   `ModelRouterContract` took that route in v1-e05-t01 for the same reason. I sent the question
   during the session as a relay prompt with three options and recommended this one. No criterion
   names the path; the node's outputs entry still does, unchanged, pending your ruling. If you
   choose option 2, the module moves as it is and the bindings change one import.
2. **The kit has no transport of its own.** Import-linter forbids httpx in `debate_core.testing`, so
   the kit describes exchanges as data. Each binding serves them through respx; the FakeProvider's
   `replay_with_respx` is about 30 lines that a real adapter can copy whole.
3. **Additions the spec does not name**, each needed for a criterion or a note of yours:
   * `http_failures.py`, the spec's "error mapping, rate-limit headers", so that every adapter maps
     a 429 and its Retry-After the same way the wrapper and the kit expect.
   * `redaction.py`, because without it no adapter can meet your "never in a log": httpx logs
     request URLs at INFO.
   * The two error classes and the three settings fields: "configured timeout" and "N consecutive
     failures" needed a home.
   * The one import-linter line.
4. **Spec paths in t02 to t07 still say `integrations/search/`.** I did not edit other tasks'
   specs. Each adapter task will need your naming ruling applied to its own spec.

## Decisions and assumptions

* **Async, as the port already is.** The spec's "asyncio timeouts" fits it, so nothing conflicts.
  The timeout is `asyncio.timeout`, the event loop's own clock, because cancelling a running call
  is the loop's job. The breaker, the hold and the latencies read only the injected `Clock`.
* **The wrapper never retries anything.** One search is at most one call to the adapter. A retry of
  an idempotent `GET` after a transient error belongs inside the adapter's call, under the same
  timeout, which `HttpSettings.max_retries` already describes. The kit allows such a retry up to
  `max_attempts` (default 3, which is 1 plus that setting's default) and refuses any resend of a
  non-idempotent request.
* **Rate limits.** A `ProviderRateLimited` holds every call until its Retry-After has passed, and
  for the cool-down when it named none. It also counts as a breaker failure.
* **Who decides a half-open breaker.** Only the probe's outcome counts. A call admitted before the
  breaker opened that finishes later is counted in health but decides nothing. A cancelled probe
  frees the slot.
* **Untranslated exceptions.** An adapter that leaks a non-`ProviderError` is reported as
  `ProviderUnavailable` naming the exception's type, chained to the original after redaction, so
  one buggy adapter cannot fail a federated search.
* **Error codes.** Both new errors keep `PROVIDER_UNAVAILABLE`, so `debate_cli.exit_codes` and the
  retryable-code list need no change.
* **Health.** The state is read lazily: an open breaker whose cool-down has passed reports
  `half_open`. p50 is the median of the last 50 attempts that reached the provider, failures
  included (a provider that keeps timing out should show it). Skipped calls are counted separately.
* **Redaction scope.** The values are every `SecretStr` in `ProviderSettings`, read from the fields,
  so a key a later adapter adds is covered without a list to update. Each value is removed raw and
  URL-encoded. The log filter is one per process on the package logger and on httpx's and
  httpcore's. A filter does not see child loggers, so every module in the package logs on the one
  package logger; `test_every_module_in_the_package_logs_on_the_one_protected_logger` checks this.
* **`test_fakes.py` data change.** The new response rule caught an existing test scripting a fake
  named `openalex-fake` with results tagged `fake-provider`. I changed that test's data to name its
  provider, rather than loosening the rule.

## Things found along the way

* **respx side effects leak the route into the exception chain.** respx re-raises a `side_effect`
  `from` an internal error whose text is the route pattern, query string included. So the correct
  fake first failed the kit's secrets check, with the contact email in the chain. The binding now
  raises transport failures in its own transport function. The kit's docstring tells t02 to t07.
* **Overlapping test sentinels can hide a leak.** A broken fake's email, `unprotected-coach@…`,
  contained the registered `coach@example.org`. The shared filter masked part of it, and the
  "leak" test passed. I changed the sentinel to one that shares nothing with the registered value.
* **A traceback quotes source lines.** The exception-scrubbing test first held the key as a literal
  in its source, and the logged traceback showed it. Real adapters never hold a key in their source,
  so the test builds the value at run time.

## Operator follow-ups

None. The affected set is over two minutes and is left to the pull request's `ci` under working
agreement 10, with no hand-off.

## Follow-up work

* **t02 to t07 specs**: apply the `integrations/discovery` naming ruling. Each adapter's binding
  copies `replay_with_respx`. Each adapter calls `protect_logs` in its constructor and logs on
  `debate_core.integrations.discovery.redaction.logger`.
* **t02 (OpenAlex), packaging.** httpx is in the `opencaselist` extra, whose comment says "and
  nothing else". The first HTTP adapter has to decide whether discovery joins that extra or gets
  its own. That is a `pyproject.toml` change, which makes it whole-selection shared ground.
* **t07 (government)**: its ac3 wants a `NOT_CONFIGURED` health status for a missing api.data.gov
  key. `ProviderHealth` would gain a field, or `BreakerState` a sibling, in that task.
* **The CLI provider status footer** reads `ProviderRegistry.health()`. Wiring the registry into
  `debate_cli.container` belongs to that task and to E08's fan-out.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
