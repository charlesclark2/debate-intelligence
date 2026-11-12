# Session report: v1-e07-t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429

| | |
|---|---|
| Task | `v1-e07-t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429` — A paced call checks the breaker and the rate-limit hold when its turn comes, and a 429 backs the provider off exponentially |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429.yaml`](../../plan_specs/v1/e07-discovery-adapters/t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t22-a-paced-call-checks-the-breaker-at-its-turn-and-backs-off-on-429` |
| Session status | COMPLETE |

## Summary

A call queued on its adapter's pace now checks the rate-limit hold and the circuit breaker again when its
turn comes. If they would refuse it now, it is not sent: it is refused as a skip, and its place in the
queue goes to the next call at once. A `429` without `Retry-After` now holds the provider for an
exponential hold (2 s doubling to a 60 s cap, lengthened by up to half by an injected random fraction),
and an answer resets the doubling. A `Retry-After` is still kept to the second. On the night's case,
eight keyless Semantic Scholar queries all answered `429`, the wrapper now sends **one** request where
2026-11-11 sent eight. Once the breaker opens with queries still queued (a run of `503`s in the
test), nothing more is sent; that night four more requests went out after it opened. No port changed: the pacer asks the wrapper's
`PaceListener` through one new method, `turn_came`. Look first at the behaviour change for adapters
other than Semantic Scholar: OpenAlex's spent daily budget and GovInfo's hourly cap now get the 2 s
backoff instead of the 60 s cool-down (Follow-up work 1). The affected set ran over two minutes and is
left to the pull request's `ci`.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| `a-paced-call-checks-the-breaker-at-its-t` (Back off at the turn) | Done | Shape written into this report first (`d239cfc`), tests red against a skeleton (`723b6d1`), implementation (`4fd33d1`), the redundant step cap a mutant found dropped (second-to-last code commit), docs. |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a call whose turn comes while the breaker is open or a hold has not ended is not sent and is counted skipped, and the night's case (eight queries, every answer 429) sends no request inside a hold, by tests on virtual time shown failing first | PASS | Red: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <discovery>/test_resilience.py test_pace.py test_semantic_scholar.py test_crossref.py test_openalex.py test_government.py -n 0 --tb=line` against the skeleton (`723b6d1`) → `26 failed, 803 passed`, every failure an assertion. The night's case on the real adapter, `test_the_nights_case_sends_one_request_and_none_inside_its_hold`: before, `assert [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, ...] == [0.0, 2.75]` (all eight sent, a second apart); after, one request at 0 s, seven refused at 1 s as `ProviderRateLimited`, `error_count 1, skipped_count 7`, the breaker closed, and a ninth query sent at 2.75 s when the hold ends. Breaker at the turn, `test_the_nights_shape_of_failures_sends_nothing_once_the_breaker_opens`: before, all eight sent; after, `[0.0, 1.0, 2.0]`, five refused at 3 s as `ProviderCircuitOpen`, skipped 5. Fan-out view (`test_the_nights_search_names_semantic_scholar_rate_limited_on_every_query`): before, every query asked; after, one asked and all eight recorded `rate_limited`. In `test_pace.py`, the hold, the breaker and the half-open probe at the turn, and the pacer's own refusal contract. Green: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/discovery -n 0` → `1112 passed in 1.65s`. |
| ac2: a 429 holds the provider for Retry-After's seconds, or without it for an exponential hold with jitter from the stated base to the stated cap, reset by an answer, by tests with an injected random source shown failing first, with mutants on the doubling, the cap, the reset and the turn-time check | PASS | Tests in `test_resilience.py` on `FixedClock` with `random_fraction` injected (`drawing([...])`). The holds are written by hand: 2, 4, 8, 16, 32, 60, 60 with no jitter; 2.5, 4.2, 11.2 at draws 0.5, 0.1, 0.8; 2, 4, 2 across an answer; 4 after a 503 between two 429s; 4, not 8, after a call the hold refused; `Retry-After: 5` kept exactly with no draw and counted in the doubling; a batched adapter held the same. All red against the skeleton (it held 60 s every time). The 20 mutants and the overflow-guard mutant are in Decisions below: 19 caught, and 1, the step's own cap, survived as an equivalent and was removed. Each mutant ran with a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (these files hold no property tests). |
| Node: Back off at the turn tests pass (`uv run pytest packages/debate_core/tests/integrations/discovery -k "resilien or pace or semantic or crossref"`) | PASS | Run as written under `scripts/hard_stop.py 115` → `485 passed in 1.88s`. |
| t04's amendment: the adapters' tests in one process after the discovery suites | PASS (run) | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/opencaselist packages/debate_core/tests/integrations/test_http_fetcher.py packages/debate_core/tests/integrations/test_crossref_doi.py <every other discovery test file> packages/debate_core/tests/integrations/discovery/test_semantic_scholar.py -n 0 -p no:randomly -q` → `1476 passed in 6.85s`. |

## Files changed

* `packages/debate_core/src/debate_core/integrations/discovery/pace.py`: `PaceListener.turn_came`,
  `TurnOutcome.REFUSED`, and the pacer asking the listener before it releases a call.
* `packages/debate_core/src/debate_core/integrations/discovery/resilience.py`: the backoff (three
  constants with their reasons, `rate_limit_hold_seconds`, `random_fraction`, the 429 count and its
  reset), the turn-time check (`at_turn`, `_CallTime.turn_came` and `refused_with`,
  `_skipped_at_turn`), and the module docstring.
* `crossref.py`, `semantic_scholar.py`, `openalex.py`, `govinfo.py`, `data_gov.py` (same directory):
  docstrings only. A 429 without `Retry-After` gets the exponential backoff now, not the cool-down,
  and the two paced adapters say a queued query is refused at its turn.
* `packages/debate_core/tests/integrations/discovery/`: 17 new tests (`test_resilience.py`,
  `test_pace.py`, `test_semantic_scholar.py`); one replaced (`test_a_rate_limit_without_retry_after_holds_for_the_cool_down`);
  three registry-level tests in `test_crossref.py`, `test_openalex.py` and `test_government.py` now
  expect the first backoff, 2 s up to 3 s, instead of the cool-down.
* `docs/guides/provider-credentials.md` and `packages/debate_cli/README.md` (the search section): what
  a student sees when a provider is held.
* The task spec's Goal phase, and this report.

## Deviations from the spec

* **`packages/debate_cli/README.md` is outside `constraints.packages`.** The PM's ruling 4 asked for
  its search section to say what a student sees when a provider is held, so it has one paragraph. No
  code in `debate_cli` changed.
* **No smoke check was added or changed.** The footer's words, the exit codes and the JSON are
  unchanged: a held provider was already `rate_limited`, and a benched one `breaker_open`. What
  changed is how many requests go out, which the virtual-time tests pin and a smoke run against the
  fake router cannot see.

## Decisions and assumptions

### The shape, chosen before the code (written first, as asked)

One correction since it was written: the step's own cap went (see the mutants), so the formula is
now `min(cap, base × 2^(n−1) × (1 + draw / 2))`, which gives the same holds.

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
  one, the `n`-th consecutive 429 holds it for `step = base * 2^(n-1)` lengthened by a
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

### What changed from that shape while building it

* **The night's tests needed answer latency, and the breaker case uses 503s.** In the first red run,
  the instant mock answers let the first query finish before the other seven had even started, so
  they were refused by the hold at their start, and the tests could not show a check at the turn.
  On the night the answers took real time, so all eight were queued first. Each refusal now comes
  back 0.25 s after its request, and the expected times above moved by that quarter second (the
  hold ends at 2.75 s). With that latency a `Retry-After: 1` hold still covers the next turn, so the
  breaker-at-the-turn case on Semantic Scholar is a run of `503`s, which the breaker counts and no
  hold covers: requests at 0, 1 and 2 s, then five refusals at 3 s. The `Retry-After` case is
  `Retry-After: 30`.
* **One hand-written expectation was my arithmetic, wrong.** The fourth 429 in a row at draw 0.9 holds
  16 × 1.45 = 23.2 s; the table said 11.6 (8 × 1.45). Corrected after the first green run, before
  any mutant ran.
* **The registry takes no random source.** It builds every wrapper with `random.random`, so the three
  registry-level adapter tests assert the first hold's bounds, at least 2 s and under 3 s. The exact
  holds are pinned at the wrapper, with the source injected. Adding a parameter to
  `ProviderRegistry.from_settings` only for those tests would have widened what the change reaches.
* **A refusal is recognised by identity.** `_CallTime` keeps every exception it raised at a turn, and
  the wrapper treats an exception as a skip only when it is one of those. An adapter that wrapped or
  replaced the refusal would have it counted as a failure, which fails toward caution. Neither paced
  adapter catches anything around its turn.

### How a refusal at the turn stops the adapter's send (ruling 1)

The adapter's send is the body of `async with self._pacer.turn(within=...) as sent:`. The pacer asks
`turn_came()` inside `Turn.__aenter__`, before it records a start or a slot. A listener that raises
makes `__aenter__` raise that exception, so Python never enters the body and nothing reaches httpx. The
exception leaves the adapter's `search` as it is (`test_a_turn_its_listener_refuses_raises_the_refusal_takes_no_start_and_frees_the_next_turn`
pins all three: the refusal raised, the body not run, and the next call starting at the same instant).
The wrapper's `_guarded` then sees its own refusal come back from `ask()`. It releases the permit and
counts a skip without calling `_fail`, so the refusal is not counted as a failure, a latency sample or
another 429.

### The mutants

Run by `run_mutants.py` (in the session scratchpad, not committed). It applies each mutant to the
committed file, deletes `__pycache__`, sets `PYTHONDONTWRITEBYTECODE=1` and a fresh
`HYPOTHESIS_STORAGE_DIRECTORY`, runs `test_resilience.py`, `test_pace.py` and
`test_semantic_scholar.py` with `-n 0` (274 tests), and restores the file with `git checkout HEAD --`.
The first pass reported a stale result for one mutant. The step-cap mutant and the final-cap mutant
are the same length and ran within one second, so Python reused the previous mutant's bytecode. Both
fixes went in and all 20 were run again. Every catch below is an assertion failure.

| Mutant | Tests failing |
|---|---|
| doubling: never doubles | 15 |
| doubling: starts one doubling late | 17 |
| doubling: the 429 count does not add up (always 1) | 7 |
| cap: the hold's cap removed | 2 |
| cap: the step's own cap removed | **0, equivalent**: the hold's cap already bounds every hold. The step's cap was deleted (agreement 8), and the formula and docstrings say so. |
| cap: 120 s | 5 |
| base: 1 s | 20 |
| jitter: shortens instead of lengthens | 10 |
| jitter: the draw ignored | 3 |
| reset: an answer does not reset the doubling | 1 (`test_an_answer_resets_the_doubling`) |
| Retry-After: ignored, always the backoff | 5 |
| Retry-After: without one, the old cool-down | 9 |
| Retry-After: a 429 with one does not count in the doubling | 1 |
| turn: the pacer never asks the listener | 8 |
| turn: the hold not checked at the turn | 4 |
| turn: the breaker not checked at the turn | 3 |
| turn: a half-open breaker refuses instead of admitting the call as its probe | 1 |
| turn: a refused turn takes a start and a slot | 7 |
| turn: a refusal at the turn counted as a failure | 5 |
| turn: a refusal at the turn not counted skipped | 5 |

After the step's cap went, the guard that stops counting doublings at 32 became the one thing between
a long run of 429s and a float overflow. A new case, two thousand 429s in a row, pins it. With the
guard removed, that case fails with `OverflowError: int too large to convert to float`. That crash is
the very failure the guard exists to prevent, so it counts as a catch.

### Checks run before the report

* Affected set: `uv run scripts/affected_tests.py` chose **128 of 743 test files** in 31.9 s, among
  them `tests/scripts/test_ci_workflow_test_job.py` (the partition proof), four smoke files and three
  e2e files. Run once as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <those
  files> -n auto -m "not slow and not live"` at a load near 11: **stopped at its 115-second limit,
  3816 passed and none failed before the stop**. It is over two minutes, so under agreement 10 it is
  left to the pull request's `ci`, which runs the same set.
* Within two minutes instead: `tests/architecture tests/specs tests/docs`, the three CLI always-run
  files, `packages/debate_core/tests/application/test_federated_search.py` and
  `tests/smoke/test_search_smoke.py` → `677 passed in 20.20s`; the discovery suites and the
  one-process run above.
* `uv run ruff format --check .` → `2059 files already formatted`; `uv run ruff check .` → `All checks
  passed!`; `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`;
  `uv run lint-imports` → `Contracts: 20 kept, 0 broken`; `scripts/check_thin_handlers.py` → OK;
  `scripts/docs_index.py --check-descriptions` → all 69 described; `scripts/check_command_blocks.py
  --base origin/dev` → OK; `uv run scripts/validate_specs.py` → `OK: 669 files, 41 epics, 606 tasks,
  22 releases`.
* The task spec on the local `origin/dev` differs from this branch only in its phase (no PM amendment).

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

1. **For the PM: a 429 that means "come back tomorrow".** Ruling 2 applies the backoff to every
   adapter, so OpenAlex's spent daily budget and api.data.gov's spent hourly allowance (GovInfo), which
   both answer `429` with no `Retry-After`, are now held 2 s and then 4 s, where before they were held
   for the 60 s cool-down. The third `429` in a row opens the breaker for its cool-down, and from
   then on the breaker lets one probe through per cool-down, as before. So such a provider now gets
   three requests in its first six seconds or so, where before it got one a minute. This follows the ruling as written; if
   the PM wants an adapter that knows its 429 is a spent budget to say so (a longer hold of its own),
   that is a small E07 task.
2. **v1-e07-t20 can go ahead once this merges.** The keyed Semantic Scholar smoke waits on this task
   (t04's operator record 2), and the operator agreed to the backoff on that condition.
3. **For whoever writes the first paced multi-query adapter.** No production adapter both answers
   several queries in one call and paces them. A refusal at one query's turn fails that whole call as
   a skip. An adapter that gathers its queries with `asyncio.gather` leaves the others running after
   the first raises, as before this task, so it should use a `TaskGroup`, which cancels them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

The PM read the constants in `resilience.py`: `RATE_LIMIT_HOLD_BASE_SECONDS` 2.0,
`RATE_LIMIT_HOLD_CAP_SECONDS` 60.0 and `RATE_LIMIT_HOLD_JITTER` 0.5, each with its reason, and none
written as a provider's published limit.

1. **ac1 passes.**
   - **Red:** 26 failed against a skeleton that changes nothing, every one at an assertion.
   - **The night's case**, on the real Semantic Scholar adapter on virtual time: one request at 0 s,
     then seven refused at their turns as skips. On 2026-11-11, eight were sent. A ninth query goes out
     when the hold ends.
   - **The breaker at the turn**, shown with 503s: three sent, then five refused once the breaker opens.
   - **The session's own test fix:** it found that instant mock answers couldn't show a check at the
     turn, and gave the mocks real latency. That's the right correction, and it is written down.
2. **ac2 passes.**
   - **The holds**, written by hand with an injected random source: 2, 4, 8, 16, 32, 60 and 60; jitter
     only ever lengthens a hold; an answer resets the doubling; `Retry-After` is kept to the second and
     counts in the doubling.
   - **The mutants:** 19 of 20 caught. The step's own cap was rightly found equivalent and removed. The
     overflow guard that removal exposed is pinned by a run of two thousand 429s.
   - **The stale-bytecode result** on the first pass was found and the run repeated, which is good
     practice.
3. **No port changed.**
   - `PaceListener.turn_came` and `TurnOutcome.REFUSED` keep v1-e07-t10's shape.
   - A refusal raised in `Turn.__aenter__` never enters the adapter's send.
   - The wrapper counts its own refusal as a skip, recognised by identity, so it is not counted as a
     failure, a latency sample or another 429.
4. **This meets the operator's Semantic Scholar agreement of 2026-11-11.** That's exponential backoff with
   jitter, `Retry-After` honoured, no request inside a hold, and nothing sent once the breaker opens. So
   v1-e07-t20 and the keyed smoke (v1-e07-t04's operator follow-up 2) may go ahead once this merges, and
   the next batch records the agreement as met.
5. **The deviations are accepted.** The CLI README paragraph is the PM's ruling 4. No smoke check was
   added, because nothing a student sees changed, only how many requests go out.
6. **Follow-ups, which the PM files in the next batch:**
   - **E07, p3:** an adapter that knows its 429 means a spent budget gives a longer hold of its own. This
     is OpenAlex's daily budget and api.data.gov's hourly allowance, which now get three requests in
     about six seconds before the breaker opens, where before they got one a minute.
   - **A note for the first paced multi-query adapter:** use a `TaskGroup`, so a refusal at one turn
     cancels the rest. The PM writes it into E07's epic notes; it is not a task.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
