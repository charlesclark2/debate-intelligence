# Session report: v1-e07-t16-public-pool-footer-test-on-an-injected-clock

| | |
|---|---|
| Task | `v1-e07-t16-public-pool-footer-test-on-an-injected-clock` — The public-pool footer test counts its results on an injected clock, not the real one |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t16-public-pool-footer-test-on-an-injected-clock.yaml`](../../plan_specs/v1/e07-discovery-adapters/t16-public-pool-footer-test-on-an-injected-clock.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t16-public-pool-footer-test-on-an-injected-clock` |
| Session status | COMPLETE |

## Summary

The task ran as the PM narrowed it on 2026-11-05. The footer test itself was already fixed on dev
by `v1-e32-t49` (`def4453`, PacerTime), so it was not redone. This session removed the
`moving_clock` field that fix left unused. It then swept the tests for any outcome that waits on
real time, by reading the code and by recording every timer each test arms on a real event loop.
Five tests could give a different answer on a busy runner and had a seam they could use. All five
now run on an injected clock or on `VirtualTimeEventLoop`. Each was shown red first under a
simulated busy runner, then passed 20 repetitions with and without that stall. No production code
changed.

**For the PM first:** nine test functions (ten cases) can still give a different answer on a slow
runner and are named, not fixed, below. Their fixes need a decision that is yours: the footer test
you scoped out, a production change, or an assertion whose meaning would change. Six wall-clock
performance budgets and 227 evidence-search cases on a 2-second budget are listed beside them.
Everything open is bundled in one question block (Follow-up work). The tightest margins are the
five 0.1-second wall-clock bounds in `test_virtual_time.py` and `test_federated_search.py`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `public-pool-footer-test-on-an-injected-c` (Injected clock) | Done | The footer test's injected clock is `def4453`'s (`v1-e32-t49`), measured here at both profiles. The sweep and the five fixes are this session's. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the footer test runs on an injected clock and gives one count every run, shown by repeated runs at both profiles | PASS | 20 repetitions per profile (scratch repetition plugin, `-n 6`) → `40 passed`: 20 `[dev-…]`, 20 `[prod-…]`. The injected clock is `def4453`'s PacerTime. Under a 1.0-second stall inside the pacer's first wait it still passes. A 2.1-second stall reaches its one remaining real-time edge, named below (Footer test). |
| ac1: any other test waiting on a real pace or deadline is fixed or named for the PM | PASS | Five fixed (below, each red first, then 20 repetitions stalled and unstalled). Nine functions (ten cases) are named for the PM with evidence, beside six performance budgets and the evidence-search group. Every other test the sweep reached is judged deterministic, with its margin. |
| Node: Injected clock tests pass (`uv run pytest packages/debate_cli/tests/test_search_command.py -k public_pool`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_search_command.py -k public_pool` → `2 passed in 3.15s` |

### Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` (55 files) | Stopped at its 115-second limit at about 97%, nothing failed before it. Over the two-minute line, so the whole affected set is left to the PR's `ci` (agreement 10). |
| The same 55 files less the 22 under `tests/scripts`, with CI's markers (`-n auto -m "not slow and not live"`) | `993 passed in 37.76s`. These are the three changed test files, the always-run list, the docs checks and the rest of the selection. `--explain` selects the 22 `tests/scripts` files only through this task's own spec and report paths, which every task changes. |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1968 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_cli packages/debate_core` | `0 errors, 0 warnings, 0 informations` (27 s) |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 637 files, 41 epics, 574 tasks, 22 releases` |
| `scripts/check_command_blocks.py --base origin/dev`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | No `#` comments in 679 blocks; 3618 links OK; all 68 indexed documents described |

### What `moving_clock` was, and its removal

`Seams.moving_clock` let the container's clock run on from `NOW` in real time. The footer test was
its only user, and `def4453` stopped using it. `git grep moving_clock` found it nowhere but the
field's declaration and the fixture's one `if seams.moving_clock:` branch. Both are gone, with the
`time` import that only that branch used (`7beb562`). Every container the fixture builds now has its
clock standing at `NOW`, as every other test already had it. The committed-profile tests →
`10 passed`.

### The five fixed tests

Every red and green run used `scripts/hard_stop.py 115`. Each "busy runner" is a scratch pytest
plugin that injects a blocking `time.sleep` at the point named. Repetitions use a scratch plugin
that parametrizes the test 20 times (pytest dedupes repeated node ids).

| Test (cases) | What waited on real time | Seam used | Red on the old test | Green |
|---|---|---|---|---|
| `debate_cli/tests/test_search_command.py::test_a_provider_that_times_out_makes_the_results_partial_and_exits_6` (1) | Providers' timeout 0.2 s on the real loop. OpenAlex's recorded answer sleeps 5 s; the feed had to answer inside the same 0.2 s. | New `on_virtual_time` fixture swaps the command's own `_run` for `run_in_virtual_time` | 0.3 s stall before each non-OpenAlex answer → `2 failed`: exit 3, `openalex` and `rss` both `timeout` (FAILED for PARTIAL) | Unstalled, 0.3 s and 1.0 s stalls pass. 20 repetitions → `40 passed` unstalled, `40 passed` at 0.3 s (both tests). |
| `…::test_a_partial_search_in_json_carries_its_results_and_the_failed_provider` (1) | The same, in JSON | The same | (in the `2 failed` above) | (in the `40 passed` above) |
| `debate_core/tests/integrations/opencaselist/test_client.py::test_retry_after_as_an_http_date_is_honoured` (1) | Wrote its HTTP date from the real now, while the client's wall clock was frozen at the real now when the fixture was built; the bound was 121 s | The client's injected wall clock: the fixture's stands at `IN_2030`, and the date is written from it. Assertion now exact: `sleeps == [120.0]` and two requests (was `any(100 <= s <= 121)`). | 2 s stall after the `client` fixture → `1 failed`, `retrying in 121.5s` | `test_client.py` → `72 passed`. 20 repetitions → `20 passed` unstalled, `20 passed` with the 2 s stall. |
| `debate_core/tests/integrations/s3/test_sts_caller_identity.py::TestAnAccountThatDoesNotAnswer::test_the_question_gives_up_after_its_own_time_limit_and_says_aws_did_not_answer` (1) | `wait_for` 0.2 s on the real loop; asserted under 2 s of `time.monotonic` | `run_in_virtual_time`; asserts the loop's clock exactly: `gave_up_at == 0.2` | 2 s stall inside `wait_for` → failed `gave up at its own limit, not when the client did` | 20 repetitions → `40 passed` unstalled, `40 passed` with the 2 s stall (both tests). |
| `…::test_the_profile_check_reports_no_answer_for_it_and_asks_the_next_profile` (1) | Two 0.2 s limits; asserted under 3 s | The same; `finished_at == 0.4` | failed `assert (…066 - …060) < 3` | (in the `40 passed` above) |

For the STS pair, a planted doubled time limit in `caller_identity.py` (`timeout=self._time_limit_seconds * 2`)
fails both new tests (`2 failed`) and passes the old ones (`6 passed`), since 0.4 s is under 2. The
production file was restored from a saved copy, and `git status` showed only the test file changed.

### The sweep: every test whose outcome can wait on real time

**How it was found.** By reading: a grep of the tests and `debate_core.testing` for `time.sleep`,
`asyncio.sleep` with a delay, `time.monotonic`, `perf_counter`, `asyncio.timeout`, `wait_for`,
`.wait(timeout`, `join(timeout`, `datetime.now`, `time.time`; and every test constructing a
provider, the resilience wrapper, a registry or a fan-out stage. By recording: a scratch plugin
patched `BaseEventLoop.call_later` and `call_at` to log every timer armed on a loop that is not a
`VirtualTimeEventLoop` (every `asyncio.sleep`, `asyncio.timeout` and `wait_for`). It also wrapped
`EvidenceSearchService.search` to log searches run on the default `time.monotonic` clock. It ran over
`integrations/discovery/`, the four `test_federated_*` files, the CLI's `test_search_*` and
`test_cut_command.py`, `commands/test_doctor.py`, the evidence-search and search-index-holder files,
`integrations/opencaselist/`, `test_sts_caller_identity.py`, `test_http_fetcher.py`,
`integrations/bedrock/` and the API's four `test_search_pages*` files: 1,308 + 755 + 218 tests
passed under it, in three runs of about 7 seconds each.

**The line drawn.** A test is listed for fixing or for the PM when a stall of under 2 seconds can
change its answer, or when its answer depends on the order threads or processes are scheduled in.
A test whose only exposure is a single stall of 2 seconds or more, landing inside one operation, is
judged deterministic and counted by file with its margin. The original footer failures were
millisecond ordering, not multi-second stalls. A timer that can only end one way (a fake that never
answers) is deterministic whatever its length.

**Fixed:** the five tests above (5 cases).

**Named for the PM** (can give a different answer, not fixed here):

| Test (cases) | Margin and evidence | Why not fixed here |
|---|---|---|
| `test_search_command.py::test_on_the_committed_profile_without_a_contact_email_crossref_names_the_public_pool_in_the_footer` (2) | The pace is on PacerTime, but the wrapper's 2 s timeout and the 15 s fan-out deadline are on the real loop. A 2.1 s stall inside the pacer's first wait → footer `crossref: timeout on 1 of 12 queries: no answer within 2s` (both profiles). A 2.1 s stall inside Crossref's answer does not trip it: that query runs into the handler before the other eleven tasks have armed their timeouts. Tried and reverted: adding `on_virtual_time` to it → 20 repetitions `40 passed` unstalled, `40 passed` at the 2.1 s pacer stall. | The PM scoped this test out ("do not redo it"). A one-parameter change, offered below. |
| `debate_core/tests/testing/test_virtual_time.py::test_an_hour_of_sleep_passes_instantly_and_is_seen_by_the_loop_clock`, `::test_waiting_on_nothing_raises_instead_of_hanging` (2) | `perf_counter` bound of 0.1 s (`REAL_TIME_BUDGET_SECONDS`), proving virtual time spends no real time. A 0.1 s hiccup fails them. | The bound is the test's claim. Replacing it with a deterministic proof (the loop's selector was only ever asked to poll) changes what it asserts. |
| `debate_core/tests/application/test_federated_search.py::test_fan_out_takes_as_long_as_the_slowest_provider_not_the_sum_of_them`, `::test_fan_out_cuts_off_a_provider_still_running_at_the_deadline_and_keeps_the_others`, `::test_fan_out_with_every_provider_past_the_deadline_fails_at_the_deadline` (3) | The same 0.1 s real-time bound beside exact virtual-time assertions | The same |
| `debate_core/tests/application/test_caselist_parse.py::test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on` (1) | Real spawned worker processes, 1.5 s limit counted from dispatch, which includes the worker's start. A scratch `sitecustomize` that slows every spawned interpreter's start: 1.2 s → passes, 1.5 s → `{'TIMEOUT': 6}` for `{'NOT_A_ZIP': 1, 'TIMEOUT': 1}`. | No seam can tell a slow worker from a stalled one. The runner's `clock` parameter only moves the deadline it already has. A fix is a production change (start a worker's limit when it says it is ready), so it is the PM's call. |
| `debate_core/tests/application/test_caselist_sync_run_lock.py::test_writers_waiting_together_share_one_renewal` (1) | Thread ordering, not a clock. The gate opens right after five writer threads start; a writer scheduled after the first renewal finishes asks for a third. Every `before_write` delayed 50 ms (scratch plugin) → `assert 6 == 2`. | No time seam. The fix is test-only (open the gate once all five writers wait), but it needs a way to see waiters: the lock's private `_condition`. |
| `tests/scripts/test_compare_card_clusters.py::test_one_key_answers_and_a_key_pressed_before_the_question_is_discarded` (1) | A pty test: the answer key `d` is written by a `threading.Timer` at 0.3 s; if `read_key`'s flush comes after it, the key at 3.0 s (`u`) answers. Not demonstrated. | Outside this task's packages |
| Wall-clock performance budgets, by design: `integrations/discovery/test_feed_parsing.py::test_an_entity_expansion_attack_is_refused_without_expanding` (1, under 1.0 s); `integrations/docx_parser/test_structural_fixtures.py::test_a_three_hundred_page_file_parses_within_the_budget` (1, under 20 s); `application/test_file_quality_mutations.py::test_a_hundred_card_file_passes_every_check_within_the_budget` (1, under 5 s); `tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline` (1, `eval` marker); `application/test_evidence_search_scale.py` (2, `slow`, off the PR path) | Each measures elapsed real time against a budget | Measuring real time is what they are for; no assertion was loosened. Listed so the PM can see them. |
| Evidence search on the default 2.0 s budget (`EvidenceSearchService`'s `time.monotonic` clock): 227 cases. `debate_api/tests/test_search_pages.py` 24, `…_find_on_openev.py` 5, `…_follow_ups.py` 16, `…_passage.py` 10; `debate_core/tests/application/test_evidence_search.py` 64, `…_cursor_check.py` 8, `…_passage.py` 36, `…_ranking.py` 1, `…_result_count.py` 25, `test_search_index_holder.py` 14, `…_app_log.py` 3, `…_formats.py` 4, `…_suppression.py` 14, `test_search_index_refresh_checked_against.py` 1; `integrations/local/test_search_index_reader_sqlite_features.py` 2 | A stall of 2 s inside one search turns its page partial | At the 2 s line, so judged deterministic by the rule above. Named because of the count: the seam exists (`clock=`, and the holder's `build_service`), and a standing clock for these is the PM's call. |

**Deterministic as they are:**

* Under 2 s on a real loop, but the timer can only end one way: `test_crossref.py::test_a_sent_query_that_runs_slow_still_times_out` (1: 0.05 s timeout over a 5 s sleep); `test_resilience.py::test_a_call_that_outlives_the_timeout_is_cancelled_and_reported_as_timed_out`, `::test_timeouts_count_towards_the_breaker`, `::test_queries_asked_at_once_share_one_timeout_and_fail_as_one_call` (3: 0.01 s over a fake that never answers); `test_client.py::test_a_retry_after_of_nan_does_not_hang_the_transport` (1: real 0.01 s backoff and 0.5 s pacer under a 5 s `wait_for`, a 4.5 s margin).
* Real-loop timers of 2 s or more, nothing real waiting inside them, by file (cases, smallest timer): `debate_cli/tests/test_search_command.py` 51 (10 s wrapper; 15 s fan-out); `test_search_presenter.py` 3 (10 s); `test_search_presenter_standing_feed.py` 2 (10 s); `debate_core/tests/application/test_federated_search_articles.py` 1 (15 s); `test_search_index_refresh_checked_against.py` 15 (300 s); `integrations/bedrock/test_router.py` 78 and `test_prompt_registry_wiring.py` 2 (300 s); `integrations/discovery/test_crossref.py` 8 (10 s; the pace itself on `VirtualTime`), `test_feeds.py` 2, `test_openalex.py` 5, `test_registry.py` 2 (10 s), `test_government.py` 13 (5 s), `test_resilience.py` 20 (5 s); `integrations/opencaselist/test_client.py` 8 (5 s); `integrations/s3/test_sts_caller_identity.py` 19 (5 s). Total 229.
* Threads with 5 s polling margins: `test_caselist_sync_run_lock.py::test_the_background_thread_renews_until_released`, `::test_a_lease_taken_again_after_a_release_renews_again` (2). `::test_a_write_that_arrives_during_an_in_flight_renewal_waits_for_the_next_one` (1): a slow runner weakens its 0.2 s "has not written yet" check but cannot change its answer, since a late writer still waits for the second renewal.
* `test_caselist_sync_run_state.py::test_a_stop_cancels_the_run_once_and_a_cancellation_nobody_asked_for_stays_one` (1): the `asyncio.sleep(1)` is cancelled at once.
* Wall-clock dates, changed only by a UTC-midnight crossing mid-test: `domain/caselist/test_values.py::test_todays_snapshot_date_is_accepted`, `::test_a_snapshot_date_in_the_future_is_rejected` (2); `debate_cli/tests/commands/test_caselist_runs.py`: `test_runs_last_5_shows_the_five_newest_with_every_column`, `test_runs_calls_out_a_schedule_that_has_stopped`, `test_runs_shows_the_nine_parse_counts_kept_beside_a_record_each_under_its_own_name`, `test_runs_shows_each_runs_codes_and_verdict_from_its_details`, `test_runs_shows_the_banners_own_words_beside_the_verdict` (5).
* Outside this task's packages, real processes by design: `tests/scripts/test_hard_stop.py` (process trees, 0.5 to 3 s reaping margins); `tests/scripts/test_parts_dealt_by_durations.py::test_a_part_records_each_files_setup_call_and_teardown_seconds` (2: a lower bound, which a slow runner only helps). The `tests/smoke` stand-ins and `test_network_guard.py` wait up to 5 s for a process or listener.

**PacerTime** serves one file (`test_search_command.py`), so it stays there. None of the five fixes
needed it, so the PM's condition for moving it into `debate_core.testing` is not met. It is a
near copy of `test_crossref.py`'s `VirtualTime`. Merging the two would be a refactor for another task.

## Files changed

* `packages/debate_cli/tests/test_search_command.py`: `moving_clock` removed; the
  `on_virtual_time` fixture; the two provider-timeout tests use it, with docstrings saying why.
* `packages/debate_core/tests/integrations/opencaselist/test_client.py`: the simulated wall clock
  stands at `IN_2030`; the Retry-After date test writes its date from it and asserts exactly.
* `packages/debate_core/tests/integrations/s3/test_sts_caller_identity.py`: the two no-answer tests
  run on `run_in_virtual_time` and assert the loop's clock.
* `plan_specs/v1/e07-discovery-adapters/t16-public-pool-footer-test-on-an-injected-clock.yaml`:
  phase `Succeeded`.
* This report.

## Deviations from the spec

* **The scope is the PM's narrowing of 2026-11-05, not the spec's description.** The spec asks for
  the footer test's injected clock. `v1-e32-t49` did that in `def4453`, so it was not redone, and
  ac1's first half is measured on that work. The spec text is unchanged here; the PM amends it in
  the next batch.
* **The sweep's lists give names for every fixed or named test, and per-file counts for the two
  large deterministic groups.** Those groups are 229 timer cases and 227 evidence-search cases. The
  recording method above regenerates their names; say if you want them listed.
* **One test outside `constraints.packages` is named, not touched:**
  `tests/scripts/test_compare_card_clusters.py`'s pty test.

## Decisions and assumptions

* **`VirtualTimeEventLoop` rather than PacerTime for the CLI pair and the STS pair.** Their waits are
  timeouts and `wait_for` on the loop's clock, not a pacer's injected sleep. The loop is the seam
  those calls already read. For the CLI the loop is reached through the command's own `_run`, which
  `asyncio.run`s one coroutine. The search path does no thread offloads (`to_thread`,
  `run_in_executor`), so the virtual loop cannot jump past real work.
* **The OpenCaselist fixture's wall clock now stands at a fixed instant** instead of the real now.
  Its docstring said it started at the real now only because the Retry-After date test wrote its
  date from the real now. `test_client.py` runs whole after the change (`72 passed`).
* **Assertions got tighter, never looser.** `any(100 <= s <= 121)` became `== [120.0]`. `< 2` and
  `< 3` seconds became `== 0.2` and `== 0.4` on the loop's clock.
* **The 2-second line** is a judgement, set out above, and the PM may draw it elsewhere. Moving it
  to 3 s adds nothing new: the evidence-search group, at 2 s, is already listed. Moving it to 1 s
  leaves the same tests fixed and named.

## Operator follow-ups

None.

## Follow-up work

The open decisions, as one block to relay to the PM:

```text
v1-e07-t16 asks the PM six questions (session report, "Named for the PM").

1. Footer test residual. Its pace is on PacerTime, but the wrapper's 2-second timeout is still on
   the real loop. A 2.1 s stall while the queries wait gives "timeout on 1 of 12 queries".
   Options: (a) give it the on_virtual_time fixture, one parameter, tried here: 40/40 unstalled and
   40/40 at the 2.1 s stall; (b) leave it.
   Recommendation: (a), in this task's PR if you allow it, since the fixture is already here.

2. The five 0.1-second wall-clock bounds (test_virtual_time.py 2, test_federated_search.py 3)
   that prove virtual time spends no real time. A 100 ms hiccup fails them.
   Options: (a) replace each bound with a deterministic check that the virtual loop's selector
   was only ever asked to poll; (b) raise the bound; (c) leave them.
   Recommendation: (a), as a follow-up task; (b) only moves the line.

3. test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on. Its 1.5 s limit includes
   a fresh worker's start; 1.5 s of slow spawn times out every source.
   Options: (a) production change: a worker's limit starts when it reports ready; (b) a longer
   limit and stall, at real seconds per run; (c) leave it.
   Recommendation: (a), as a caselist-epic follow-up.

4. test_writers_waiting_together_share_one_renewal: a thread-ordering race, 6 renewals for 2 when
   writers start 50 ms late. A test-only fix opens the gate once all five wait, which needs a view
   of the lock's private condition.
   Recommendation: a follow-up task for the run-lock owner.

5. Evidence search: 227 test cases run on the 2.0 s time.monotonic budget, with a 2-second margin.
   Options: (a) give the tests a standing clock by default (shared fixture), with the budget tests
   keeping theirs; (b) leave them.
   Recommendation: (b) for now; the margin is the same as the line drawn.

6. tests/scripts pty key test (0.3 s timer): outside this task's packages.
   Recommendation: a follow-up with the scripts' owner.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
