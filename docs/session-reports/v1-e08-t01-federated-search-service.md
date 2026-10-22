# Session report: v1-e08-t01-federated-search-service

| | |
|---|---|
| Task | `v1-e08-t01-federated-search-service` — SearchService fan-out |
| Spec | [`plan_specs/v1/e08-research-workflows/t01-federated-search-service.yaml`](../../plan_specs/v1/e08-research-workflows/t01-federated-search-service.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t01-federated-search-service` |
| Session status | COMPLETE |

## Summary

`FederatedSearchService` (`application/federated_search.py`, types in
`application/federated_search_types.py`) runs a search as four stages in a fixed order: expand,
fan_out, normalize, rank. The sibling tasks' stages (t02 to t04) default to `PassThroughStage`.
`FanOutStage` asks every selected provider every query at once, in one `asyncio.TaskGroup` under one
overall deadline. It records each call as one `ProviderStatus`: ok, timeout, error, rate_limited,
breaker_open or not_configured. `search_status` turns those records into COMPLETE, PARTIAL or
FAILED. Nothing a provider raises leaves the fan-out.

The service takes a new, small port, `DiscoveryProviders` (the enabled providers and the health of
each). `ProviderRegistry` satisfies it with no change. The search, its per-provider record (the raw
results) and any ranking are stored through `SearchRepository`, which I extended with two methods.
Its contract, the in-memory fake and the SQLite adapter (migration `0003`) were extended to match.

**Look at these first:**

* `ProviderStatus` and `ProviderOutcome` are new values in `debate_core.domain.discovery`. That
  takes the task into `debate_core.domain`, beyond the `debate_core.testing` you anticipated. See
  Deviations 1.
* The ac2 tests run on a virtual-time event loop (`debate_core.testing.virtual_time`). See
  Decisions 1.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| Amend the spec (PM ruling 2026-10-21) | Done | Module, service and test names changed to "federated". Packages extended, each with a comment. Commit `f59812c`. |
| `search-types`: SearchRequest, SearchOutcome and stage pipeline | Done | `federated_search_types.py`: `SearchRequest`, `SearchState`, `SearchStage`, `PassThroughStage`, `StageName`, `SearchPipeline`, `SearchOutcome`. `ProviderStatus` is in the domain (Deviations 1). |
| `fan-out`: concurrent provider fan-out | Done | `federated_search.py`: `FanOutStage`, `search_status`, `selected_providers`, `FederatedSearchService`. Commit `235aa73`. |
| `persistence`: persist Search and raw results | Done | Port, contract, fake, SQLite and migration in commit `d2e6fe6`. The service writes through them (`235aa73`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: three fake providers, one sleeps past its timeout and one raises. Search returns the healthy provider's results with status PARTIAL and a status list naming each outcome | PASS | `test_fan_out_with_one_provider_past_its_timeout_and_one_raising_is_partial_with_the_healthy_results` goes through the real `ProviderRegistry` and `ResilientProvider` (10 s timeout; the slow fake takes 30 s). It asserts PARTIAL, the healthy provider's two candidates, outcomes `[ok, timeout, error]` and the error text of each. Further tests cover each failure kind separately, a breaker skip through the real breaker, not_configured, an impostor answer and an untranslated exception. |
| ac2: total wall time is bounded by the overall deadline, not the sum of provider latencies (injected clock) | PASS | Providers of 3, 4 and 5 s finish in 5 s on the injected clock, not 12, and the status elapsed times are 3000, 4000 and 5000 ms. Providers of 3 and 60 s under an 8 s deadline end at 8 s: the 60 s one is `timeout` ("no answer before the search's 8s deadline", 8000 ms) and the 3 s answer is kept. Every provider past a 12 s deadline gives FAILED at 12 s. Each test also asserts it took under 100 ms of real time. The whole file runs in 0.14 s. |
| ac3: a Search record and its raw per-provider results are persisted via SearchRepository and can be reloaded by search_id | PASS | `test_a_search_and_its_raw_provider_results_reload_by_search_id` runs on both the in-memory and the SQLite repository. It reloads the search field for field (query, filters, provider_set, PARTIAL, owner, clock times) and the per-provider record, including the answered response's candidates. A second test stores a rank stage's ranking. The SearchRepository contract has 7 new tests, which pass on both adapters (56 passed). |
| ac4: ordered stage pipeline (expand → fan_out → normalize → rank) with no-op defaults | PASS | Tests show: the order of `pipeline.stages`; the three defaults are `PassThroughStage`; recording stages each run once, in order, and each sees what the previous one produced; a dedupe stand-in passed as `normalize=` changes the result while the provider record stays the same and the service code is untouched; an `expand=` stage that adds a query makes fan_out ask every provider both queries. |
| Node `search-types`: `federated_search_types.py` exists and contains `class SearchStage` | PASS | `grep -c "class SearchStage" …/federated_search_types.py` → `1` |
| Node `fan-out`: `uv run pytest packages/debate_core/tests/application/test_federated_search.py -k fan_out` | PASS | `21 passed in 2.55s` |
| Node `persistence`: `uv run pytest packages/debate_core/tests/application/test_federated_search.py` | PASS | `40 passed in 2.41s` (0.14 s in one process; no test over 5 ms) |
| Node `persistence`: `uv run lint-imports` | PASS | `Contracts: 12 kept, 0 broken.` |

### Showing the checks fail for their reason

* **Red run against a naive skeleton.** I replaced `FanOutStage.run` with sequential awaits, no
  exception handling and no deadline, and made `search_status` always return COMPLETE. Running
  `test_federated_search.py` against it gave **26 failed, 14 passed**. The 14 that passed test
  what the skeleton kept: stage order, the request rules and the all-answered case. The ac2
  concurrency test failed because the calls ran one after another.
* **New contract tests before the SQLite adapter had the methods:** 7 failed on
  `TestSqliteSearchRepository` (`AttributeError: … no attribute 'save_provider_statuses'`) and
  passed on the in-memory fake.
* **Mutation, 21 mutants on `federated_search.py`: all 21 caught.** Each mutant was run alone with
  `-x` under a 60 s alarm and its own empty `HYPOTHESIS_STORAGE_DIRECTORY`. That directory is
  agreement 8's rule; these tests use no Hypothesis. Every catch was a failing assertion, not a
  collection error. The mutants:
  * Status rule (6): no answer gives PARTIAL; the FAILED branch returns PARTIAL; the fall-through
    returns FAILED; one answer is enough for COMPLETE; a partial answer counts as complete; `all`
    becomes `any`.
  * Classification (8): own timeout recorded as error; open breaker recorded as error; open breaker
    recorded as timeout; rate limit recorded as error; the `ProviderError` clause checked first; an
    untranslated exception escapes; an untranslated exception's text is kept; an answer under
    another name is accepted.
  * Deadline (5): no deadline; a deadline twice as long; expiry fails the search; a cut-off call
    recorded as error; a cut-off call's elapsed time measured from now.
  * Concurrency (1): providers asked one after another.
  * Selection (1): an unknown requested provider is dropped.

  Each mutant took 0.6 to 1.0 s.
* **SQLite adapter, 2 mutants:** `ORDER BY position DESC` was caught by 3 contract tests. Dropping
  the `DELETE` before the insert was caught by the replacement test.

### Before the report (working agreement 10)

* **Affected set:** `uv run scripts/affected_tests.py` selects **357 test files**, effectively
  the whole selection. Nearly every test imports `debate_core.application.ports` or
  `debate_core.domain`, and this branch changes both. That is over the two-minute line, so I did not
  run it and did not hand it to the operator. It is left to the PR's `ci` check. No shared test
  ground changed (no `pyproject.toml`, `uv.lock`, `conftest.py` or `tests/pytest_plugins/`), so no
  whole-selection operator run is warranted. My one attempt over the changed areas plus the
  always-run list was too broad: it hit its 115 s alarm unfinished, so it counts for nothing. I split
  it:
  * The changed areas: `test_federated_search.py`, `test_port_conformance.py`, `test_fakes.py`,
    and all of `tests/domain`, `tests/contracts`, `tests/integrations/local`,
    `tests/integrations/discovery` and `tests/testing` (`-n 4`, CI's markers) → **1524 passed in
    13.26s**.
  * The always-run list (`tests/architecture`, `tests/specs`, the CLI's `test_app.py` and
    `test_help_rendering.py`) plus `tests/scripts/test_check_command_blocks.py` → **309 passed, 1
    warning in 20.73s**. The warning is pytest-socket's "a test tried to use socket.socket" from
    `test_doctor_renders_a_table`, a CLI test this branch does not touch.
* `uv run ruff format --check .` → `1023 files already formatted`; `uv run ruff check .` → `All
  checks passed!`
* `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`. That is the only
  package changed.
* `uv run lint-imports` → `Contracts: 12 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 396 files, 39 epics, 336 tasks, 21 releases`;
  `--require-succeeded v1-e08-t01-federated-search-service` → `Succeeded`
* `uv run scripts/check_command_blocks.py` → `OK: no # comments in 333 shell code blocks in 131
  Markdown files`

## Files changed

* **Spec:** `plan_specs/v1/e08-research-workflows/t01-federated-search-service.yaml`. The names
  and packages, per the PM ruling of 2026-10-21, each with a comment.
* **Domain:** `debate_core/domain/discovery.py`. Adds `ProviderOutcome` and `ProviderStatus`, the
  stored record of one call.
* **Ports:**
  * `application/ports/providers.py` and `ports/__init__.py`: `DiscoveryProviders`.
  * `application/ports/persistence.py`: `SearchRepository.save_provider_statuses` and
    `list_provider_statuses`.
* **Application:** `application/federated_search_types.py` and `application/federated_search.py`
  (new).
* **Testing kit:**
  * `testing/contracts/repositories.py`: 7 per-provider-record contract tests.
  * `testing/fakes.py`: the in-memory repository's two new methods.
  * `testing/builders.py`: `build_candidate_result` and `build_provider_status`.
  * `testing/virtual_time.py` (new): the virtual-time loop and `EventLoopClock`.
* **SQLite adapter:**
  * `integrations/local/migrations/0003_search_provider_statuses.sql` (new).
  * `integrations/local/sqlite_repos.py`: the two methods.
  * `integrations/local/sqlite_db.py`: the docstring now names the second foreign key.
* **Tests:**
  * `tests/application/test_federated_search.py` (new, 40 tests).
  * `tests/testing/test_virtual_time.py` (new, 5 tests).
  * `tests/domain/test_discovery.py`: `ProviderStatus` validation.
  * `tests/integrations/discovery/test_registry.py`: `ProviderRegistry` conforms to
    `DiscoveryProviders`.
  * `tests/integrations/local/test_sqlite_db.py`: the expected table set, and the cascade and
    foreign key of the new table.
* **Docs:** `packages/debate_core/README.md`, module table rows.

## Deviations from the spec

1. **The packages grew beyond `debate_core.application`.** The spec is amended with the PM-ruling
   comment. You anticipated `debate_core.testing` for the contract. Two more turned out necessary:
   * **`debate_core.domain`:** the per-provider record is a stored value built from domain values
     (`ProviderQuery`, `ProviderResponse`). Every other record a repository stores lives in the
     domain, so `ProviderStatus` went beside `ProviderResponse`.
   * **`debate_core.integrations.local`:** extending the port means the SQLite adapter needs the
     two methods and a migration, or it stops passing the contract you asked every adapter to keep
     passing.

   The alternative for the first was to define `ProviderStatus` in `application/ports/providers.py`
   (like `FetchResult`) and stay out of the domain. **Please confirm the domain placement or ask me
   to move it.**
2. **One more outcome than the spec lists.** The fan-out node lists `ok, timeout, error,
   breaker_open, not_configured`. I added `rate_limited`, because `ProviderRateLimited` is a
   separate error type with its own meaning (back off, the provider is not down). Folding it into
   `error` would hide that.
3. **"Per-provider timeouts" in the spec are `ResilientProvider`'s, as you ruled.** The service
   adds no per-provider timeout. The only timer it adds is the overall deadline.
4. **Migration number.** `0003_search_provider_statuses.sql` is the next free number on `dev`
   today, and no sibling worktree has a `0003`. A task that merges another `0003` first would make
   one of the two renumber; `load_migrations` refuses two files claiming one version, so it cannot
   pass unnoticed.

## Decisions and assumptions

1. **How ac2 is proven without real waiting.** `debate_core.testing.virtual_time` provides:
   * `VirtualTimeEventLoop`: an ordinary `SelectorEventLoop` whose selector polls instead of
     blocking and moves the loop's `time()` forward by the wait it skipped. `asyncio.sleep`,
     `asyncio.timeout` and `call_later` all read that clock, so a 60 s provider and an 8 s deadline
     fire at their virtual instants in microseconds. Tasks interleave exactly as on a real loop,
     because the scheduler is unchanged.
   * `EventLoopClock`: the `Clock` port read from the same loop clock. The service's recorded
     times, which ac2's assertions read, therefore agree with the deadline asyncio enforces.

   The deadline itself is `asyncio.timeout` on the loop clock, as in `ResilientProvider`: cancelling
   a running call is the loop's job, and driving it from the injected `Clock` would mean polling.
   The assertion was not weakened: it is exact (5 s, not 12; 8 s at the deadline). Each timing test
   also asserts under 100 ms of real time. A loop with nothing scheduled raises
   `VirtualTimeDeadlock` instead of hanging the suite. No dependency was added (no `looptime`), so
   `pyproject.toml` and `uv.lock` are untouched.
2. **Fan-out asks every provider every query**, query-major, and records one `ProviderStatus` per
   call. t04's expansion produces several queries, and this way it plugs in as an `expand` stage
   without changing the fan-out. A test shows it.
3. **Stages share one immutable `SearchState`.** It has `queries`, `provider_statuses`,
   `candidates` and `results`. t02's `MergedCandidate`s will be a new field with a default, not a
   new orchestration. Stages after fan_out must leave `provider_statuses` alone, because status and
   storage are taken from it; the module docstring says so.
4. **Status rule:**
   * COMPLETE: every call answered and none of the answers was marked partial.
   * FAILED: no call answered, including a search that made no calls at all (nothing enabled, or
     only unknown names requested).
   * PARTIAL: everything else.

   A provider that answers with `partial=True` (some of its feeds failed) makes the search PARTIAL,
   which is how `ProviderResponse`'s docstring describes a partial answer.
5. **A requested provider that settings do not enable** stays in `Search.provider_set` and is
   reported `not_configured`. Dropping it would make a search look complete when it asked fewer
   providers than requested.
6. **An untranslated exception from a provider** (not a `ProviderError`) is recorded by its type
   alone. Its text was never redacted, so none of it is stored. In normal wiring this cannot
   happen, because `ResilientProvider` translates everything first.
7. **Deadline default:** `DEFAULT_DEADLINE_SECONDS = 15.0`, a constructor parameter. That is above
   the providers' default 10 s timeout, so a provider that times out on its own is reported by its
   own timeout. I did not add a setting, because the CLI wiring is t05's. The deadline covers the
   fan_out stage only.
8. **Storage happens once, after the last stage:**
   * `save` (search record), then `save_provider_statuses`, then `save_results` with the rank
     stage's results. The default rank stage produces none, so an empty ranking is stored.
   * Nothing is stored if the search itself is cancelled.
   * `created_at` and `updated_at` come from the `Clock`.
9. **`SearchOutcome.provider_health`** is each provider's health snapshot just after the search,
   read through the port, so t05's status footer needs nothing more from the service.
10. **Tests import integrations.** The ac1 and breaker tests import `debate_core.integrations`
    from the application tests, so that "sleeps past its timeout" is `ResilientProvider`'s real
    timeout. import-linter governs `src` packages only. The `DiscoveryProviders` conformance test
    lives with the registry's own tests, as you suggested.

## Operator follow-ups

None. The affected set covers effectively the whole selection and is left to the PR's `ci` check
(agreement 10). No shared test ground changed.

## Follow-up work

* **v1-e08-t05 (search command):**
  * Build `FederatedSearchService` in the CLI container from `ProviderRegistry.from_settings`.
  * Decide where the overall deadline is configured. A `providers.search_deadline_seconds` setting
    beside `timeout_seconds` would be the natural place.
* **v1-e08-t04 (expansion):** its ac2 says "the expansion is recorded on the persisted Search".
  Each call's exact query (filters included) is already stored in its `ProviderStatus.query`, so
  the expanded queries are recoverable today. t04 can decide whether that is enough or whether
  `Search` needs a field.
* **v1-e08-t02 (normalize):** adds its `MergedCandidate`s as a new `SearchState` field. The
  `normalize` slot and the test showing a swap are ready.
* **E07 (discovery adapters), optional:** `ResilientProvider` raises `ProviderRateLimited` both
  for its own hold and for the adapter's 429, so the fan-out cannot tell "held" from "refused" and
  reports both as `rate_limited`. If the CLI ever needs the difference, the wrapper needs a distinct
  error.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-21

**Notes:**

Accepted, with nothing more to do before the pull request. Every criterion passes, the Goal is
`Succeeded`, and the pull request opens with no `--partial`. Its `ci` check runs the whole selection;
paste any failure back here.

**What is good:**

* **ac1 goes through the real `ProviderRegistry` and `ResilientProvider`,** so "sleeps past its
  timeout" is the real timeout, not a fake's say-so.
* **ac2 is exact and fast.** The virtual-time loop moves the loop's own clock, so `asyncio.timeout`,
  `sleep` and `call_later` fire at their virtual instants with the scheduler unchanged:
  * 3, 4 and 5 s providers finish at 5 s, not 12;
  * the 8 s deadline cuts the 60 s call at 8 s and keeps the 3 s answer;
  * each test runs in under 100 ms of real time.

  `VirtualTimeDeadlock` instead of a hang is a good touch, and no dependency was added.
* **The status rule is stated and mutated:** 21 of 21 caught, plus the two SQLite mutants. A
  requested but unenabled provider stays in `provider_set` as `not_configured`, rather than
  silently shrinking the search. That is the honest choice.
* **Extending the port meant extending every adapter:** the contract, the fake, SQLite and
  migration `0003`, red first on SQLite. That is exactly the rule.

**Rulings:**

1. **Deviation 1: domain placement confirmed.** `ProviderStatus` is a stored record built from
   domain values, and every other stored record lives in `debate_core.domain`.
   `debate_core.integrations.local` follows from the contract rule. Both are accepted.
2. **Deviation 2 (`rate_limited`): accepted.** Backing off is not the same as being down.
3. **Deviations 3 and 4: accepted.** If another `0003` migration merges first,
   `load_migrations` refuses the clash and the second to merge renumbers.

**Follow-ups, placed by the PM in the next batch:**

* **v1-e08-t05:** wire `FederatedSearchService` in the container from
  `ProviderRegistry.from_settings`, and add `providers.search_deadline_seconds` beside
  `timeout_seconds`, default 15.
* **v1-e08-t04:** the expanded queries are already recoverable from each `ProviderStatus.query`. t04
  decides whether `Search` needs a field.
* **v1-e08-t02:** `MergedCandidate`s are a new `SearchState` field, in the `normalize` slot.
* **E07, "held" versus "refused" rate limits:** no task now. If the CLI ever needs the
  difference, `ResilientProvider` gains a distinct error.
