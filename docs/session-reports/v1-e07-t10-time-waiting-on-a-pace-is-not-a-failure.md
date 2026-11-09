# Session report: v1-e07-t10-time-waiting-on-a-pace-is-not-a-failure

| | |
|---|---|
| Task | `v1-e07-t10-time-waiting-on-a-pace-is-not-a-failure` — The resilience wrapper does not count time a provider spends waiting on its own pace as a failure |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t10-time-waiting-on-a-pace-is-not-a-failure.yaml`](../../plan_specs/v1/e07-discovery-adapters/t10-time-waiting-on-a-pace-is-not-a-failure.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t10-time-waiting-on-a-pace-is-not-a-failure` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Built to the PM's ruling of 2026-11-08, as proposed below before any code. A shared pacer,
`debate_core.integrations.discovery.pace`, queues an adapter's calls at the rate, burst and
concurrency it configures, on the injected clock. It tells `ResilientProvider`, through a listener
the wrapper installs for each call, when a call waits and how its wait ends. The wrapper suspends a
call's timeout while it is queued, so the timeout fails only `timeout_seconds` of time not queued,
and leaves queued time out of the latency median. A call the pace never sent ("not asked") is
counted in the new `ProviderHealth.not_asked_count`, and is neither a success, a failure nor a
latency sample. Crossref moved onto the shared pacer and its `_Pacer` is gone. Its eleven-query
public-pool case was pinned first against today's code, on the event loop's virtual time, and still
gives the same results, statuses, "not asked" answers and finishing times.

**Look first** at Decisions 1 and 2. Decision 1: a query the pace releases late and that then runs
slow is now cut off by the search's 15 s deadline before the wrapper's timeout, so the breaker no
longer counts it as a failure. It is still a timeout in the footer. Decision 2: a "not asked"
answer no longer resets the breaker's failure count, and no longer closes a half-open breaker. One
Deviation: `debate_core.domain` is outside the spec's packages (for `not_asked_count`), so it is
added to the spec with a comment.

## Proposal (written before the code, to the PM's ruling of 2026-11-08)

The PM ruled the shape in advance; this is how it is built, so the review can check the code
against it.

* **`debate_core.integrations.discovery.pace`** (new) holds the shared pacer.
  * `Pace(requests, interval_seconds, burst=1, concurrency=None)`: no more than `burst` starts in
    any window of `burst × interval / requests` seconds, and no more than `concurrency` calls in
    flight. With a burst of one, starts are evenly spaced `interval / requests` apart, which is
    Crossref's pace today. `burst` must divide `requests`, so no window of `interval_seconds` ever
    holds more than `requests` starts (the forbidden "a provider's limits exceeded").
  * `Pacer(pace, clock=, sleep=)`: first come, first served, on the injected clock and the injected
    sleep. `async with pacer.turn(within=...) as sent:` waits for the call's turn; `sent` is
    False when the turn would come `within` seconds or more after the call arrived (its deadline,
    re-read on every look, because Crossref's reserve moves as answers arrive). `retune(pace)`
    changes the pace from now on (Crossref's tightening to advertised headers). The slot is freed
    when the `async with` block ends, however it ends.
  * The pacer tells the wrapper about each call through a context variable the wrapper sets for
    the call it is making (`PaceListener`): when the call starts waiting, and whether its wait
    ended released, refused at its deadline ("not asked") or cancelled. No port changes, and an
    adapter that does not pace is untouched.
* **`ResilientProvider`** counts each call's queued time from those reports.
  * While a call is queued its timeout is suspended (`asyncio.Timeout.reschedule(None)`); when the
    pace releases it, the timeout is set to the call's start plus `timeout_seconds` plus the
    time queued. So the timeout fails a call only for `timeout_seconds` of time it was not queued,
    and a query that was sent and runs slow still times out.
  * Latency in `provider_health` is the call's elapsed time less its queued time, for successes and
    failures alike.
  * A call whose only pace turn was refused (a "not asked" answer) is returned unchanged, but it is
    neither a success, a failure nor a latency sample: the breaker's permit is released with no
    verdict (as a cancelled call's is), so it neither resets nor adds to the failure count, and
    `ProviderHealth` gains `not_asked_count`, the number of such calls. `success_count` counts
    calls the provider answered.
* **Crossref** moves onto the shared pacer: `PoolLimits` stays (the pool's name and its rate
  phrase) and gives its `Pace`; the median-answer reserve and the "not asked" answer stay in the
  adapter, because they are Crossref's choice of deadline and its wording. `_Pacer` goes.
* **Tests, on virtual time only**: first a pin of the eleven-query public-pool case on the event
  loop's virtual time (`VirtualTimeEventLoop`, so the wrapper's timeout and the search's deadline
  are live too) with every call's outcome, results, "not asked" answer and finishing time written
  by hand, committed and passing against today's code. Then, shown failing first: queued time is
  not latency; queued time is not the timeout's failure (and a released call that runs slow still
  times out); a "not asked" answer is neither a failure nor a latency sample; a pacer shared by
  concurrent calls releases them in arrival order at its rate, burst and concurrency. Then mutants
  on the queue accounting and the deadline check.
* **Semantic Scholar** (`v1-e07-t04`) can build a `Pacer` from its own limits; nothing else changes
  for other adapters.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| `time-waiting-on-a-pace-is-not-a-failure` (Pace not failure) | Done | Pin, then red runs, then the wrapper and the pacer, then Crossref, then mutants. Commits `5beeba5` (pin), `d2e9035` (pacer and wrapper), `a5af20f` (Crossref), `cb650db` and the late-release pin (tests from the mutant run and Decision 1). |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: queued time counts neither as a timeout failure nor as latency, and Crossref's eleven-query public-pool case behaves as today on virtual time, by tests shown failing first | PASS | Pin first: `test_the_public_pool_case_on_the_loops_virtual_time_keeps_its_results_footer_and_not_asked_answers` (3 cases), hand-written and committed alone in `5beeba5`, `3 passed` against today's code and still passing after the move. Red runs and the green run are under **Tests shown failing first** below. |
| Node: Pace not failure tests pass (`uv run pytest packages/debate_core/tests/integrations/discovery -k "resilien or crossref or pace"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/discovery -k "resilien or crossref or pace"` → `271 passed in 6.63s` at `a5af20f`. The later test commits add 4 more, which pass in the run below. |

### Tests shown failing first

All new tests run on `run_in_virtual_time` (`VirtualTimeEventLoop` plus `EventLoopClock`), so the
pacer's sleeps, the wrapper's `asyncio.timeout`, the fan-out's deadline and every clock read one
virtual clock. Nothing sleeps for real and nothing reaches the network.

* **Red run A.** The shared pacer was in place, with today's wrapper and today's Crossref:
  `pytest test_pace.py test_crossref.py -k "pace or loops_virtual_time or not_asked_answers_apart" -n 0`
  → `9 failed, 31 passed`. Each test failed on its own assertion:
  * queued time is latency: `assert 1200.0 == 200.0` (`test_time_queued_on_a_pace_is_not_the_calls_latency`);
  * queued time fails the timeout: `ProviderTimedOut: paced: no answer within 1s` (`…does_not_count_towards_the_timeout`), and `…0.5s` for the multi-query call;
  * a released slow call timed out while still queued: `assert 1.0 == 3.0` (`…still_times_out_its_timeout_after_its_release[a call queued for 2 s]`);
  * a "not asked" answer counted as a success: `assert (2, 1, 0) == (1, 1, 1)`;
  * a refused probe closed the breaker: `[OPEN, CLOSED, CLOSED] != [OPEN, HALF_OPEN, CLOSED]`;
  * Crossref's health: `assert (11, 0, 0) == (9, 2, 0)`, `(6, 5, 0)`, `(3, 8, 0)`.

  The never-queued control (`…[a call never queued]`) passed, as it should: it behaves the same
  before and after. The pin passed.
* **Red run B.** A pacer that releases every call at once, so the pacer's own tests are seen to
  fail: `-k "releases_them_in_order or retuned or turn_would_come"` → `6 failed`, every start at
  `0.0` (for example `assert [0.0, 0.0, 0.0, 0.0, 0.0, 0.0] == approx([0.0, 0.5, …])`). The real
  pacer was then restored and checked with `cmp`.
* **Green.** After the wrapper: `test_pace.py test_resilience.py test_crossref.py -n 0` →
  `3 failed, 261 passed`, all three Crossref's health test, because Crossref still had its own
  pacer. After Crossref moved: `3 failed, 261 passed`, all three the older eleven-query test's
  `success_count == 11` line, which ruling 3 changes (now `(asked, 11 - asked)`). After that edit
  the node command passed (above).

### Mutants

These target the queue accounting (`resilience._CallTime`, the not-asked path) and the deadline
check (`pace.Pacer._wait`, `Turn`). Each one ran against `test_pace.py`, `test_crossref.py` and
`test_resilience.py` with `-n 0`, bounded at 115 s, from a clean commit, and the file was restored
after each. The tests use no Hypothesis; each run still set a new empty
`HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8).

| Mutant | Result |
|---|---|
| Queued time does not suspend the timeout | caught, 3 failed (`…does_not_count_towards_the_timeout`, `…[a call queued for 2 s]`, the multi-query test) |
| The timeout is not moved on by the queued time | caught, 3 failed (same three) |
| Latency keeps the queued time | caught, 7 failed |
| Every wait ends a queued stretch, not only the last (overlapping waits counted twice) | **survived** at first; caught after the multi-query test was given a third query (1 failed) |
| A call with any refused turn is "not asked", even with a query sent | **survived** at first; caught by the new `…of_which_one_was_sent_are_an_answer_not_a_not_asked` (1 failed) |
| A not-asked call counted a success | caught, 8 failed |
| A not-asked call gives the breaker a success | caught, 2 failed (the not-asked test and the probe test) |
| A not-asked call is a latency sample | caught, 2 failed |
| Deadline boundary: `now > deadline` instead of `>=` | **not a catch: hangs.** The run stopped at its 115 s limit (exit 124). At `now == deadline` the mutated check falls through to a sleep of `min(ready_at, deadline) - now = 0`, so the loop spins without time moving: on the virtual loop and on the test's `VirtualTime` alike, in `…not_asked_at_that_deadline` and in the pin's 0.5 s case. There is no terminating wrong behaviour for an assertion to see. Today's `_Pacer` had the same property. |
| Deadline counted from each look, not from arrival | caught, at assertions (`…not_asked_at_that_deadline` and the not-asked test FAILED, in a 25 s rerun with `-v`), before a later test hung waiting for a turn that never ends |
| `within` read once, not on every look | **survived** at first; caught by the new `test_a_query_waiting_when_an_answer_moves_the_reserve_keeps_to_the_new_deadline` (1 failed) |
| A free wait sleeps past the deadline | caught, 1 failed (`…not_asked_at_that_deadline`) |
| A full wait ignores the deadline | caught, 1 failed (the pin, 1.5 s case: not-asked answers at the wrong time) |
| No concurrency limit | caught, 13 failed |
| A refused turn reported as released | caught, 8 failed |
| The pacer never tells the listener a call waits | caught, 9 failed |
| Burst ignored | caught, 1 failed (`…[four every two seconds, two back to back]`) |

Seventeen mutants. Sixteen are caught at assertions, three of them only after the new tests in
`cb650db`. The boundary mutant hangs.

### Before the report

* **Affected set:** `uv run scripts/affected_tests.py` → `563 of 734 test files (76.7%) chosen in
  17.8 s from 8 changed files`. The root `conftest.py` reaches `debate_core.domain.discovery` through
  the fake router and `ports.providers`. That is well over two minutes, so by agreement 10 it is left
  to the pull request's `ci` check, with no hand-off. Run instead, within the limit: the changed test
  directories, Crossref's consumers and the always-run list,
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/discovery packages/debate_core/tests/domain/test_discovery.py packages/debate_core/tests/application/test_federated_dedupe.py packages/debate_core/tests/application/test_federated_ranking.py packages/debate_core/tests/application/test_federated_search_articles.py packages/debate_core/tests/application/test_federated_search.py packages/debate_cli/tests/test_search_command.py packages/debate_cli/tests/test_search_presenter.py packages/debate_cli/tests/test_search_presenter_standing_feed.py packages/debate_core/tests/testing/test_virtual_time.py tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py -n auto -m "not slow and not live"`
  → `1784 passed in 23.23s`. That covers t16's public-pool footer test, which runs Crossref's pacer on the CLI.
* `ruff format --check .` → `2033 files already formatted`; `ruff check .` → `All checks passed!`.
* `pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`.
* `lint-imports` → `Contracts: 20 kept, 0 broken`.
* `uv run scripts/export_schemas.py --check` → `OK: 10 schemas … are up to date` (`ProviderHealth` is in no exported schema).
* `uv run scripts/validate_specs.py` → `OK: 655 files, 41 epics, 592 tasks, 22 releases`.

## Files changed

* `packages/debate_core/src/debate_core/integrations/discovery/pace.py` (new): `Pace`, `Pacer`,
  `Turn`, `TurnOutcome`, `PaceListener`, `listening`, `Sleep`.
* `packages/debate_core/src/debate_core/integrations/discovery/resilience.py`: `_CallTime`, the
  per-call listener (suspends and moves the timeout, takes queued time out of latency), the not-asked
  path, `not_asked_count` in `health()`, and the module docstring.
* `packages/debate_core/src/debate_core/integrations/discovery/crossref.py`: on the shared pacer.
  `_Pacer` and `PoolLimits.spacing` are gone (nothing else read `spacing`); `PoolLimits.pace` is
  new. The reserve, header tightening and "not asked" wording stay in the adapter. `Sleep` is still
  exported, now from `pace`.
* `packages/debate_core/src/debate_core/domain/discovery.py`: `ProviderHealth.not_asked_count`
  (default 0), and `success_count` reads "Calls the provider answered".
* `packages/debate_core/tests/integrations/discovery/test_pace.py` (new): the pacer and the wrapper
  on virtual time.
* `packages/debate_core/tests/integrations/discovery/test_crossref.py`: the pin, the health test,
  the moving-reserve test, the late-release test, and the older eleven-query test's
  `success_count` line.
* `plan_specs/v1/e07-discovery-adapters/t10-time-waiting-on-a-pace-is-not-a-failure.yaml`:
  `debate_core.domain` added to the packages, with a comment above it; phase `Succeeded`.

## Deviations from the spec

* **`debate_core.domain` is outside `constraints.packages`.** Ruling 3 asks provider_health to show
  not-asked answers, and `ProviderHealth` is a domain model, so `not_asked_count` is added there. It
  is additive with a default of 0, so every existing constructor and JSON consumer still works; no
  test pins `provider_health`'s key set (grepped `tests/` and `debate_cli/tests`). The spec's packages
  now list it, with a session comment above the line. The PM may prefer to restate it as a ruling.

## Decisions and assumptions

1. **A sent query's timeout counts from its release (ruling 2), and this has a consequence for late
   releases.** The pace's deadline still makes sure an answer *of the usual length* comes back
   within `timeout_seconds` of the query being asked. But a query released at 6 s that then hangs
   now has until 16 s, so the search's 15 s deadline cuts it off first. The footer still says
   timeout (`crossref: no answer before the search's 15s deadline`), but the wrapper's call was
   cancelled, so the breaker records no failure. Measured on today's code with the same test, that
   query was `crossref: no answer within 10s`, a breaker failure. Queries released before 5 s that
   hang still time out in the wrapper and still count, so a Crossref that hangs on every query
   still opens its breaker from its first queries. Pinned by
   `test_a_query_released_late_that_runs_slow_is_still_a_timeout_cut_off_by_the_searchs_deadline`.
   The forbidden "a query that was sent and ran slow no longer timing out" holds: it times out,
   `timeout_seconds` after its release or at the search's deadline, whichever is first. If the PM
   wants the breaker to hear of those too, the remedy is a follow-up: cap a released call's
   timeout at what remains of the search's deadline.
2. **A "not asked" answer gives the breaker no verdict.** Its permit is released, as a cancelled
   call's is, so it neither resets nor adds to the failure count, and a half-open probe that is not
   asked leaves the breaker half open for the next call. Until now it counted as a success. Ruling
   3 says "neither a failure nor a latency sample", and a query never sent says nothing about the
   provider either way (t03's reasoning), so it is not a success either. `success_count` now counts
   calls the provider answered: the eleven-query case reads 9, 6 and 3 with 2, 5 and 8 not asked,
   where it read 11.
3. **How the wrapper hears of the pace: a context variable, not a port change.** The wrapper sets
   a `PaceListener` around each call it makes, and the pacer reports to whatever listener is set.
   `SearchProvider` is unchanged, an adapter that does not pace is untouched, and a turn taken
   outside any wrapper reports to nobody (tested).
4. **Two clocks, each for its own job.** The timeout is the event loop's, as before, so the wrapper
   moves it with `asyncio.Timeout.reschedule` on loop time. Latency is read from the injected clock,
   as before. On `VirtualTimeEventLoop` with `EventLoopClock` they are one clock, which is how the
   new tests run.
5. **The pace's burst.** No more than `burst` starts in any window of `burst × interval / requests`
   seconds, and `burst` must divide `requests`, so no window of `interval_seconds` ever holds more
   than `requests` starts (the forbidden "a provider's limits exceeded"; every pacer test checks it).
   With a burst of one this is exactly Crossref's even pace: the start one spacing after the last.
   `retune` applies to calls already waiting, as Crossref's tightening did.
6. **A call that asks several queries at once is queued while any of them waits.** Its timeout is
   suspended for that time, and its latency excludes it. It is "not asked" only when every query's
   turn was refused; one sent query makes it an answer. No multi-query adapter paces today
   (OpenAlex and the feeds do not), so this is defined and tested but has no user yet.
7. **Crossref keeps its deadline and its words.** The reserve (median answer time, clamped) and the
   "not asked" text stay in the adapter and are passed to the pacer as `within`, re-read on every
   look as before. With ruling 2 the reserve no longer protects a query from the wrapper's timeout.
   It still decides whether a query is worth sending, so the eleven-query case is unchanged.
   Semantic Scholar chooses its own `within`.
8. **The pin is stronger than the old eleven-query test.** The old test ran on `VirtualTime`, so
   the wrapper's timeout stayed on the real loop and could never fire. The pin runs on the loop's
   virtual time, so the wrapper's timeout and the fan-out's deadline both take part, and it pins
   every call's finishing time: 0.5, 1.5, … 8.5 s and the not-asked answers at 9 s; 1.5 to 9 s and
   8.5 s; 2.5, 5, 7.5 s and 7.5 s. The "same footer" is pinned through its inputs, because
   `footer_lines` is a function of the statuses (each one's outcome, `partial`, error and results),
   and `debate_cli` is outside this task's packages.

## Operator follow-ups

None. The affected set (563 files) is the pull request's `ci` check's, under agreement 10.

## Follow-up work

* **The breaker does not hear of a late-released query that hangs** (Decision 1). Capping a
  released call's timeout at what is left of the search's deadline would bring it back. The PM
  decides; it belongs in E07 with the wrapper.
* **`test_search_presenter.py`'s stand-in Crossref** answers "not asked" without the pacer, so the
  wrapper there counts those answers as successes (`success_count == 3`). It still passes and pins
  the footer, but it no longer shows what the real adapter's health reads (1 answered, 2 not asked).
  Moving the stand-in onto a `Pacer` is a `debate_cli` test change, outside this task's packages.
* **`v1-e07-t04` (Semantic Scholar)** can configure `Pacer(Pace(requests=1, interval_seconds=1.0,
  concurrency=1), clock=…)` from its own limits and choose its own `within`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-09

**Notes:**

The PM read the built code in the worktree: `pace.py` (new), the `resilience.py` diff, the Crossref
diff and the domain line. It matches the proposal and the PM's ruling of 2026-11-08, point by point.

- `Pacer._wait` is Crossref's old `admit` loop, generalised. Starts are now spaced by burst, the deadline
  is re-read from `within` on every look, and the release-or-deadline wait is unchanged. With a burst of
  one, `_ready_at` is the old `last_start + spacing`.
- The listener is installed by the wrapper through a context variable. `waiting()` fires before the line
  lock is taken, so time spent behind another caller counts as queued.
- `_CallTime` suspends the `asyncio.timeout` on the first wait. When the last wait ends, it reschedules
  the timeout to the original deadline plus the queued loop time. So a sent call still has
  `timeout_seconds` of its own.
- The new Pacer keeps the old `_Pacer`'s loop-bound `asyncio.Lock` and `Event`. That brings no new risk.

1. **ac1 passes.**
   - **The pin.** The pin on the loop's virtual time was committed alone (`5beeba5`) and passed against
     today's code with every finishing time written by hand. It is stronger than the old test, because the
     wrapper's timeout and the fan-out's deadline both take part now.
   - **The red runs.** Red run A: 9 failed, each at its own assertion, with the never-queued control and
     the pin passing as they should. Red run B: 6 failed, against a pacer that releases everything at once.
   - **Green.** The node command passed 271, and the bounded affected subset 1,784.
   - **The mutants.** 16 of 17 were caught at assertions. Three of those survived at first, and the session
     closed each with a new test rather than arguing it away.
   - **The 17th, the deadline boundary `>` for `>=`, is accepted as not catchable.** At `now == deadline`
     it sleeps 0 and spins without time moving. There is no terminating wrong behaviour to assert on, and
     the old `_Pacer` had the same property.
2. **Decision 1 is accepted.** A query released late that then hangs is now cut off by the search's 15 s
   deadline before its own timeout, so the breaker hears no failure. The footer still says timeout, so the
   forbidden case ("a query that was sent and ran slow no longer timing out") holds.
   - A Crossref that hangs on everything still opens its breaker from the queries released before about 5 s.
   - This is ruling 2 working as written.
   - Whether the breaker should also hear of the late ones is filed below, proposal first.
3. **Decision 2 is accepted.** A "not asked" answer gives the breaker no verdict: the permit is released, as
   a cancelled call's is, so it neither resets nor adds to the failure count, and a half-open probe that
   is not asked stays half open. That is ruling 3 read correctly, since a query never sent says nothing
   about the provider. `success_count` now means calls answered, and the eleven-query case reads 9/6/3
   answered with 2/5/8 not asked.
4. **The deviation is accepted as a PM ruling.** `debate_core.domain` joins the packages for
   `ProviderHealth.not_asked_count`. It is additive with a default of 0, `export_schemas --check` is OK,
   and no test pins the key set. The session's comment in the spec stands.
5. **Decisions 3 to 8 are accepted.**
   - 3, a context variable rather than a port change.
   - 4, the loop clock for the timeout and the injected clock for latency.
   - 5, burst dividing `requests`, so no interval exceeds the limit.
   - 6, a multi-query call is queued while any of its queries waits, and is not asked only if all were
     refused.
   - 7, Crossref keeps its reserve and its wording.
   - 8, the pin's footer is pinned through its inputs.
6. **Follow-ups, which the PM files in the next batch:**
   - **E07, p3, proposal first:** the breaker hears of a released query that the search's deadline cut off
     (Decision 1). The proposal says how the wrapper learns what is left of the search's deadline, or
     offers another way.
   - **E07, p3:** `test_search_presenter.py`'s stand-in Crossref queues on a real `Pacer`, so its health
     reads what the real adapter's would (1 answered, 2 not asked). The packages are `debate_cli` tests.
   - `v1-e07-t04` (Semantic Scholar) is ready once this merges. It configures its own `Pacer` and its own
     `within`.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
