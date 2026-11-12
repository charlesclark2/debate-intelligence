# Session report: v1-e07-t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429

| | |
|---|---|
| Task | `v1-e07-t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429` — A paced call checks the breaker and the rate-limit hold when its turn comes, and a 429 backs the provider off exponentially |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429.yaml`](../../plan_specs/v1/e07-discovery-adapters/t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

<!-- 3-6 sentences: what was built, how it fits the epic, anything the PM should look at first. -->

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

### The shape, chosen before the code (written first, as asked)

* **The turn-time check.** `PaceListener` gains one method, `turn_came()`. The pacer calls it under
  its line at the moment it would release a call, before it records the start or takes a concurrency
  slot. The wrapper's listener (`_CallTime`) answers by checking the rate-limit hold and the breaker
  again, and raises the refusal they would give a new call. The pacer then records nothing (no
  start, no slot, so the next call in line gets its look at once), tells the listener the wait ended
  `REFUSED` (a new `TurnOutcome`), and re-raises the refusal out of `async with pacer.turn(...)`'s
  entry. The body of that block is the adapter's send, so it never runs, and the refusal leaves the
  adapter's `search` unchanged: neither Crossref nor Semantic Scholar catches a `ProviderError`
  around its turn. No port changes.
* **What the wrapper does with it.** It knows the exception it raised at the turn, and answers that
  one exception as the hold or the breaker answers a call at its start: the breaker permit is
  released with no verdict, `skipped_count` goes up by one, no latency, no failure, and neither the
  hold nor the doubling changes. It re-raises `ProviderRateLimited` or `ProviderCircuitOpen`, so the
  fan-out records `rate_limited` or `breaker_open` as before.
* **The breaker at the turn.** A call keeps the permit it took at its start while the breaker is
  still closed, or when that permit is the probe. Otherwise (the breaker opened while it waited) the
  old permit is released and the breaker is asked again: it refuses with `ProviderCircuitOpen`, or,
  when the breaker has half-opened with no probe out, makes this call the probe.
* **The backoff.** A 429 with a `Retry-After` holds the provider for exactly those seconds. Without
  one, the `n`-th consecutive 429 holds it for `step = min(cap, base * 2^(n-1))` lengthened by a
  random fraction up to half of itself, `min(cap, step * (1 + draw / 2))`, `draw` in `[0, 1)` from an
  injected random source. Base 2 s, cap 60 s, reasons in the module. Every 429 counts towards `n`,
  with a `Retry-After` or without; an answer resets `n` to 0; other failures, skips and "not asked"
  leave it. The hold is the wrapper's, so it applies to every adapter it wraps, paced or not.
* **The night's case, expected by hand.** Eight queries on Semantic Scholar's pace (one a second,
  one at a time), every answer 429 with no `Retry-After`, a 10 s timeout: one request, at 0 s. Its 429
  holds the provider for at least 2 s, so the second query's turn at 1 s is refused, and the six
  behind it get their looks at once and are refused too: 7 skipped, 1 failure, the breaker closed.
  Before this task all eight were sent, at 0 to 7 s. With `Retry-After: 1`, each hold ends at the
  next turn: requests at 0, 1 and 2 s, the third failure opens the breaker, and the five left are
  refused at 3 s as the breaker answers.

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
