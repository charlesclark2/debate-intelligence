# Session report: v1-e07-t10-time-waiting-on-a-pace-is-not-a-failure

| | |
|---|---|
| Task | `v1-e07-t10-time-waiting-on-a-pace-is-not-a-failure` — The resilience wrapper does not count time a provider spends waiting on its own pace as a failure |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t10-time-waiting-on-a-pace-is-not-a-failure.yaml`](../../plan_specs/v1/e07-discovery-adapters/t10-time-waiting-on-a-pace-is-not-a-failure.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t10-time-waiting-on-a-pace-is-not-a-failure` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

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
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

None.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
