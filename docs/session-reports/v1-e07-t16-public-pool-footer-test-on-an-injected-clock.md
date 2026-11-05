# Session report: v1-e07-t16-public-pool-footer-test-on-an-injected-clock

| | |
|---|---|
| Task | `v1-e07-t16-public-pool-footer-test-on-an-injected-clock` — The public-pool footer test counts its results on an injected clock, not the real one |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t16-public-pool-footer-test-on-an-injected-clock.yaml`](../../plan_specs/v1/e07-discovery-adapters/t16-public-pool-footer-test-on-an-injected-clock.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t16-public-pool-footer-test-on-an-injected-clock` |
| Session status | COMPLETE |

## Summary

The task ran as the PM narrowed it on 2026-11-05, then as the PM ruled on its six questions the same
day. `v1-e32-t49` (`def4453`) had already put the footer test's pacer on PacerTime. This session
removed the `moving_clock` field that left unused, and put the footer test's own event loop on
virtual time (ruling 1). That removes its last real-time dependency, the resilience wrapper's
2-second timeout. A sweep found every test whose outcome can wait on real time, by reading and by
recording every timer each test arms on a real event loop. Eleven test functions (twelve cases) are
now fixed. Five were moved onto an injected clock or `VirtualTimeEventLoop`. One is the footer test.
Five more had 100 ms wall-clock bounds, replaced by a check that the virtual loop only ever asked
the real selector to poll (ruling 2). Each was shown red first under a simulated busy runner, then
gave one answer over 20 repetitions with and without the stall. No production code changed, and no
assertion was loosened. Three tests are follow-ups the PM filed (rulings 3, 4 and 6). The 227
evidence-search cases stay as they are (ruling 5). Every swept test is listed below by name and
count, with its verdict.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `public-pool-footer-test-on-an-injected-c` (Injected clock) | Done | The footer test's pacer is on `def4453`'s PacerTime, and since this task its loop is on virtual time too; measured at both profiles. The sweep and the other ten fixes are this session's. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the footer test runs on an injected clock and gives one count every run, shown by repeated runs at both profiles | PASS | 20 repetitions per profile (scratch repetition plugin, `-n 6`): 20 `[dev-…]` and 20 `[prod-…]` passed, unstalled and again under a 2.1-second blocking stall inside the pacer's first wait. Without `on_virtual_time` the same stall failed both profiles (`crossref: timeout on 1 of 12 queries: no answer within 2s`). |
| ac1: any other test waiting on a real pace or deadline is fixed or named for the PM | PASS | The sweep below: 11 functions fixed here, 3 follow-ups filed by the PM, 6 performance budgets left as they are by design, and the rest deterministic as they are, each named. |
| Node: Injected clock tests pass (`uv run pytest packages/debate_cli/tests/test_search_command.py -k public_pool`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_search_command.py -k public_pool` → `2 passed in 3.53s` |

### Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` (57 files) | Stopped at its 115-second limit at about 97%, with no failure before it. That is over the two-minute line, so the whole affected set is left to the PR's `ci` (agreement 10). |
| The same 57 files less the 22 under `tests/scripts`, with CI's markers (`-n auto -m "not slow and not live"`) | `1044 passed in 37.50s`: every changed test file, the always-run list, the docs checks and the rest of the selection. `--explain` selects the 22 `tests/scripts` files only through this task's own spec and report paths, which every task changes. |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1969 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_cli packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 637 files, 41 epics, 574 tasks, 22 releases` |
| `scripts/check_command_blocks.py --base origin/dev`, `scripts/check_links.py`, `scripts/docs_index.py --check-descriptions` | No `#` comments in 679 blocks; 3618 links OK; all 68 indexed documents described |
| This spec against `origin/dev` | Only this task's phase differs |

### What `moving_clock` was, and its removal

`Seams.moving_clock` let the container's clock run on from `NOW` in real time. The footer test was
its only user, and `def4453` stopped using it. `git grep moving_clock` found it nowhere but the
field's declaration and the fixture's one `if seams.moving_clock:` branch. Both are gone, with the
`time` import only that branch used (`7beb562`). Every container the fixture builds now has its
clock standing at `NOW`. The committed-profile tests → `10 passed`.

## The sweep

**How it was found.** By reading: a grep of every test and `debate_core.testing` for `time.sleep`,
`asyncio.sleep` with a delay, `time.monotonic`, `perf_counter`, `asyncio.timeout`, `wait_for`,
`.wait(timeout`, `join(timeout`, `threading.Timer`, `datetime.now` and `time.time`; and every test
that builds a provider, the resilience wrapper, a registry or a fan-out stage. By recording: a scratch
pytest plugin patched `asyncio.BaseEventLoop.call_later` and `call_at` to log, per test, every timer
armed on a loop that is not a `VirtualTimeEventLoop`. That covers every `asyncio.sleep`,
`asyncio.timeout` and `wait_for`, including those behind default arguments such as
`sleep=asyncio.sleep`, which grep cannot see. It also wrapped `EvidenceSearchService.search` to log
searches run on its default `time.monotonic` clock. On the final code it ran over
`integrations/discovery/`, the four `test_federated_*` files, `testing/test_virtual_time.py`, the
CLI's `test_search_*`, `test_cut_command.py` and `commands/test_doctor.py`, the evidence-search and
search-index-holder files, `integrations/opencaselist/`, `test_sts_caller_identity.py`,
`test_http_fetcher.py`, `integrations/bedrock/` and the API's four `test_search_pages*` files. In all,
1,313 + 755 + 218 tests passed under it, in three runs of about 5 seconds each.

**The line drawn.** A test is fixed or filed when a stall of under 2 seconds can change its answer,
or when its answer depends on the order threads or processes are scheduled in. A test whose only
exposure is one stall of 2 seconds or more inside one operation is deterministic as it is, listed
with its margin. A timer that can only end one way (a fake that never answers) is deterministic
whatever its length.

**How each fix was shown.** Every run used `scripts/hard_stop.py 115`. A "busy runner" is a scratch
plugin that injects a blocking `time.sleep` at the point named. Repetitions use a scratch plugin that
parametrizes a test 20 times, since pytest dedupes repeated node ids.

### Fixed here: 11 functions, 12 cases

| Test (cases) | What waited on real time | Seam used | Red on the old test | Green |
|---|---|---|---|---|
| `debate_cli/tests/test_search_command.py::test_on_the_committed_profile_without_a_contact_email_crossref_names_the_public_pool_in_the_footer` (2: dev, prod) | Pace on PacerTime (`def4453`), but the wrapper's 2 s timeout and the 15 s fan-out deadline on the real loop | `on_virtual_time` (ruling 1) | 2.1 s stall inside the pacer's first wait → both failed, `crossref: timeout on 1 of 12 queries: no answer within 2s` | 20 repetitions per profile → 40 passed unstalled, 40 passed at the 2.1 s stall |
| `…::test_a_provider_that_times_out_makes_the_results_partial_and_exits_6` (1) | Providers' timeout 0.2 s on the real loop. OpenAlex's recorded answer sleeps 5 s, and the feed had to answer inside the same 0.2 s. | New `on_virtual_time` fixture: swaps the command's own `_run` for `run_in_virtual_time` | 0.3 s stall before each non-OpenAlex answer → 2 failed: exit 3, `openalex` and `rss` both `timeout` | Unstalled, 0.3 s and 1.0 s pass. 20 repetitions → 40 passed unstalled, 40 passed at 0.3 s (both tests). |
| `…::test_a_partial_search_in_json_carries_its_results_and_the_failed_provider` (1) | The same, in JSON | The same | (in the 2 failed above) | (in the 40 passed above) |
| `debate_core/tests/integrations/opencaselist/test_client.py::test_retry_after_as_an_http_date_is_honoured` (1) | Wrote its HTTP date from the real now, against a client wall clock frozen at fixture setup; bound 121 s | The client's injected wall clock: the fixture's stands at `IN_2030` and the date is written from it. Exact: `sleeps == [120.0]`, two requests (was `any(100 <= s <= 121)`). | 2 s stall after the `client` fixture → failed, `retrying in 121.5s` | `test_client.py` 72 passed. 20 repetitions → 20 passed unstalled, 20 passed at 2 s. |
| `debate_core/tests/integrations/s3/test_sts_caller_identity.py::TestAnAccountThatDoesNotAnswer::test_the_question_gives_up_after_its_own_time_limit_and_says_aws_did_not_answer` (1) | `wait_for` 0.2 s on the real loop; asserted under 2 s of `time.monotonic` | `run_in_virtual_time`; exact `gave_up_at == 0.2` on the loop's clock | 2 s stall inside `wait_for` → failed `gave up at its own limit, not when the client did` | 20 repetitions → 40 passed unstalled, 40 passed at 2 s (both tests). |
| `…::test_the_profile_check_reports_no_answer_for_it_and_asks_the_next_profile` (1) | Two 0.2 s limits; asserted under 3 s | The same; `finished_at == 0.4` | failed `assert (…066 - …060) < 3` | (in the 40 passed above) |
| `debate_core/tests/testing/test_virtual_time.py::test_an_hour_of_sleep_passes_instantly_and_is_seen_by_the_loop_clock` (1) | `perf_counter` bound of 0.1 s, meant to prove virtual time spends no real time | `selector_polls`: every timeout the loop passed to the real selector beneath it is recorded, and the test asserts it was asked something and only ever to poll (ruling 2) | 0.15 s stall as each `asyncio.Runner` starts → the five old bounds 5 failed (`assert 0.157… < 0.1` and the like) | 20 repetitions of the five → 100 passed unstalled, 100 passed at 0.15 s |
| `…::test_waiting_on_nothing_raises_instead_of_hanging` (1) | The same bound | The same | (in the 5 failed above) | (in the 100 passed above) |
| `debate_core/tests/application/test_federated_search.py::test_fan_out_takes_as_long_as_the_slowest_provider_not_the_sum_of_them` (1) | The same bound | The same | (in the 5 failed above) | (in the 100 passed above) |
| `…::test_fan_out_cuts_off_a_provider_still_running_at_the_deadline_and_keeps_the_others` (1) | The same bound | The same | (in the 5 failed above) | (in the 100 passed above) |
| `…::test_fan_out_with_every_provider_past_the_deadline_fails_at_the_deadline` (1) | The same bound | The same | (in the 5 failed above) | (in the 100 passed above) |

**The fixes are checked against the breaks they exist to catch:**

* **The selector check still proves what the bound meant (ruling 2).** A scratch plugin replaced
  the virtual loop's selector with a broken one that really sleeps (up to 50 ms a wait, so the
  hour-long test cannot hang) before moving its clock. All five new checks failed against it:
  `the real selector was asked to wait (timeouts [0.05]), so real time passed`. The old bounds caught
  2 of the 5; the other three slept under their 100 ms. The calls are read at
  `selectors.DefaultSelector`, which the loop's selector inherits from, and the loop's selector
  always calls `super().select(0)`. So the check needed no seam on the loop, and nothing in
  `debate_core.testing` changed.
* **The STS pair catches a wrong time limit.** A planted doubled time limit in
  `caller_identity.py` (`timeout=self._time_limit_seconds * 2`) fails both new STS tests and passes
  the old ones (0.4 s is under 2). The production file was restored from a saved copy, and
  `git status` showed only the test file changed.

### Follow-ups filed by the PM: 3 functions, 3 cases (left as they are here)

| Test (cases) | Why it can give a different answer, and the evidence | Follow-up |
|---|---|---|
| `debate_core/tests/application/test_caselist_parse.py::test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on` (1) | Real spawned workers. The 1.5 s limit is counted from dispatch, which includes the worker's start. With a scratch `sitecustomize` slowing every spawned interpreter's start: 1.2 s → passes; 1.5 s → `{'TIMEOUT': 6}` for `{'NOT_A_ZIP': 1, 'TIMEOUT': 1}`. | Ruling 3, E31, p3: a worker's limit starts when it reports ready. A production change. |
| `debate_core/tests/application/test_caselist_sync_run_lock.py::test_writers_waiting_together_share_one_renewal` (1) | Thread order, not a clock. A writer scheduled after the first renewal finishes asks for a third. Every `before_write` delayed 50 ms (scratch plugin) → `assert 6 == 2`. | Ruling 4, E40, p3: release the writers on a hook the lock offers for tests, when a writer starts waiting |
| `tests/scripts/test_compare_card_clusters.py::test_one_key_answers_and_a_key_pressed_before_the_question_is_discarded` (1), testing `scripts/compare_card_clusters.py`'s `read_key` | A pty test. The answer key `d` is written by a `threading.Timer` at 0.3 s. If `read_key`'s `TCSAFLUSH` comes after it, the key written at 3.0 s (`u`) answers. Not demonstrated. | Ruling 6, E41, p3; outside this task's packages |

### Left as they are, wall-clock budgets by design: 6 functions, 6 cases

Each measures elapsed real time against a budget, so a slow enough runner fails it by design. The PM
has not ruled on these, and none has a follow-up.

* `debate_core/tests/integrations/discovery/test_feed_parsing.py::test_an_entity_expansion_attack_is_refused_without_expanding` (1): under 1.0 s
* `debate_core/tests/integrations/docx_parser/test_structural_fixtures.py::test_a_three_hundred_page_file_parses_within_the_budget` (1): under 20 s
* `debate_core/tests/application/test_file_quality_mutations.py::test_a_hundred_card_file_passes_every_check_within_the_budget` (1): under 5 s
* `tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline` (1): `eval` marker
* `debate_core/tests/application/test_evidence_search_scale.py`: both tests (2), `slow` marker, off the PR path

### Deterministic as they are, from reading

* **Real-loop timers under 2 s that can only end one way: 5 functions, 5 cases.**
  * `debate_core/tests/integrations/discovery/test_crossref.py::test_a_sent_query_that_runs_slow_still_times_out` (1): 0.05 s timeout over a 5 s sleep.
  * `debate_core/tests/integrations/discovery/test_resilience.py`, three tests, each a 0.01 s timeout over a fake that never answers:
    * `test_a_call_that_outlives_the_timeout_is_cancelled_and_reported_as_timed_out` (1)
    * `test_timeouts_count_towards_the_breaker` (1)
    * `test_queries_asked_at_once_share_one_timeout_and_fail_as_one_call` (1)
  * `debate_core/tests/integrations/opencaselist/test_client.py::test_a_retry_after_of_nan_does_not_hang_the_transport` (1): a real 0.01 s backoff and 0.5 s pacer under a 5 s `wait_for`, a 4.5 s margin.
* **Threads: 3 functions, 3 cases.**
  * `debate_core/tests/application/test_caselist_sync_run_lock.py::test_the_background_thread_renews_until_released` (1) and `::test_a_lease_taken_again_after_a_release_renews_again` (1): 5 s polling margins.
  * `::test_a_write_that_arrives_during_an_in_flight_renewal_waits_for_the_next_one` (1): a slow runner weakens its 0.2 s "has not written yet" check, but cannot change its answer.
* **A sleep cancelled at once: 1 function, 1 case.**
  * `debate_core/tests/application/test_caselist_sync_run_state.py::test_a_stop_cancels_the_run_once_and_a_cancellation_nobody_asked_for_stays_one` (1)
* **Wall-clock dates: 7 functions, 7 cases.** Only a UTC-midnight crossing mid-test changes these.
  * `debate_core/tests/domain/caselist/test_values.py::test_todays_snapshot_date_is_accepted` (1) and `::test_a_snapshot_date_in_the_future_is_rejected` (1)
  * `debate_cli/tests/commands/test_caselist_runs.py`:
    * `test_runs_last_5_shows_the_five_newest_with_every_column` (1)
    * `test_runs_calls_out_a_schedule_that_has_stopped` (1)
    * `test_runs_shows_the_nine_parse_counts_kept_beside_a_record_each_under_its_own_name` (1)
    * `test_runs_shows_each_runs_codes_and_verdict_from_its_details` (1)
    * `test_runs_shows_the_banners_own_words_beside_the_verdict` (1)
* **Real processes by design, outside this task's packages: 7 functions, 8 cases.**
  * `tests/scripts/test_hard_stop.py`, process trees with 0.5 to 3 s reaping margins:
    * `test_hard_stop_kills_every_process_of_a_tree_that_ignores_term` (1)
    * `test_hard_stop_ends_a_tree_that_obeys_term_without_kill` (1)
    * `test_hard_stop_passes_output_through_while_the_command_runs` (1)
    * `test_hard_stop_stops_what_a_command_in_time_left_running_in_its_group` (1)
    * `test_hard_stop_cannot_reach_a_child_that_started_its_own_session` (1)
    * `test_hard_stop_reaches_xdist_workers_and_their_subprocesses_which_stay_in_the_run_s_group` (1)
  * `tests/scripts/test_parts_dealt_by_durations.py::test_a_part_records_each_files_setup_call_and_teardown_seconds` (2): a lower bound, which a slow runner only helps.
  * Not counted by name: the `tests/smoke` stand-ins wait up to their start-up timeout for a stand-in process (`tests/smoke/stand_ins/process.py`), and `tests/smoke/test_network_guard.py`'s `loopback_listener` fixture waits up to 5 s. These are start-up waits in shared fixtures, run in validate-dev.

### Deterministic as they are, from the recording

The recording lists every function with its case count. The smallest margin anywhere in this group
is 5 s.

<details>
<summary>Real-loop timers of 2 seconds or more, nothing real waiting inside them: 174 functions, 229 cases</summary>

* `debate_cli/tests/test_search_command.py`: 51 cases, smallest real timer 10 s
  * `test_a_da_link_search_on_the_nhi_topic_asks_openalex_its_links_then_the_mechanisms_in_the_united_states` (1)
  * `test_a_one_router_auto_cut_a_cent_short_of_its_max_cost_is_refused_as_before` (1)
  * `test_a_one_router_auto_cut_spends_up_to_its_max_cost_as_before` (1)
  * `test_a_provider_that_is_not_enabled_is_named_in_the_footer_and_the_search_is_partial` (1)
  * `test_a_search_that_asks_no_enabled_provider_exits_1` (1)
  * `test_a_topic_alone_searches_the_query_as_typed` (1)
  * `test_an_expanded_search_reads_each_feed_once_however_many_queries_it_asks` (1)
  * `test_auto_cut_after_a_search_no_provider_answered_ends_as_search_does_and_cuts_nothing` (1)
  * `test_auto_cut_does_not_fetch_a_result_an_earlier_fetch_found_paywalled` (1)
  * `test_auto_cut_exits_0_with_n_verified_when_the_search_was_partial_and_names_the_provider` (1)
  * `test_auto_cut_json_output_carries_the_search_and_the_report` (1)
  * `test_auto_cut_max_cost_is_the_commands_per_run_budget` (1)
  * `test_auto_cut_report_prints_as_a_table_and_is_report_json_beside_the_bundle` (1)
  * `test_auto_cut_short_of_n_exits_8_in_json_with_the_report_as_details` (1)
  * `test_auto_cut_skips_paywalled_and_robots_disallowed_results_lists_them_and_goes_on` (1)
  * `test_auto_cut_stops_at_the_budget_guard_exits_9_and_keeps_the_verified_card` (1)
  * `test_auto_cut_under_max_cost_ends_on_a_model_with_no_price` (1)
  * `test_auto_cut_writes_three_verified_cards_under_one_block_heading_and_a_matching_manifest` (1)
  * `test_each_familys_own_need_expands_before_any_provider_is_asked` (3)
  * `test_every_provider_answering_with_nothing_exits_7` (1)
  * `test_every_provider_failing_exits_3` (1)
  * `test_expand_llm_adds_the_models_validated_queries` (1)
  * `test_expand_llm_and_auto_cut_stop_at_one_budget_for_the_whole_command` (2)
  * `test_expand_llm_that_cannot_reach_a_model_prints_the_expansions_warning` (1)
  * `test_govinfo_with_its_key_is_asked_on_its_topic_with_the_key_in_a_header_only` (1)
  * `test_govinfo_without_an_api_data_gov_key_is_reported_not_configured_on_its_topic` (1)
  * `test_no_model_is_asked_without_expand_llm` (1)
  * `test_on_the_committed_profile_a_contact_email_puts_crossref_in_the_polite_pool_and_is_never_printed` (2)
  * `test_on_the_committed_profile_a_search_on_the_nhi_topic_with_a_key_asks_govinfo_and_is_complete` (2)
  * `test_on_the_committed_profile_a_search_on_the_nhi_topic_without_a_key_reports_govinfo_not_configured` (2)
  * `test_on_the_committed_profile_a_search_with_no_topic_asks_crossref_publicly_and_no_government_source` (2)
  * `test_presenter_json_gives_each_result_its_place_in_raw_provider_order` (1)
  * `test_presenter_json_items_carry_rank_score_features_explanation_identifiers_and_sources` (1)
  * `test_presenter_json_puts_only_the_envelope_on_stdout_and_progress_on_stderr` (1)
  * `test_presenter_max_results_caps_the_rows` (1)
  * `test_presenter_never_prints_an_abstract_or_a_feed_description` (1)
  * `test_presenter_table_shows_ranked_deduplicated_rows_and_the_provider_footer` (1)
  * `test_ranked_candidates_become_stored_results_through_articles_without_a_fetch` (1)
  * `test_save_writes_the_search_object_to_a_file` (1)
  * `test_the_container_builds_crossref_when_providers_enabled_names_it` (1)
  * `test_the_container_registers_openalex_feeds_and_google_news_and_closes_them` (1)
  * `test_the_federal_register_is_asked_only_by_a_search_on_a_topic_that_lists_it` (1)
  * `test_the_stored_search_records_its_expansion` (1)
  * `test_two_commands_in_one_process_are_two_budget_runs` (1)
* `debate_cli/tests/test_search_presenter.py`: 3 cases, smallest real timer 10 s
  * `test_queries_crossref_never_sent_make_the_search_partial_and_say_why_without_a_failure` (1)
  * `test_the_json_keeps_the_period_start_and_names_no_precision_yet` (1)
  * `test_the_table_shows_a_year_or_a_month_and_never_an_invented_day` (1)
* `debate_cli/tests/test_search_presenter_standing_feed.py`: 2 cases, smallest real timer 10 s
  * `test_a_new_feed_failure_beside_a_standing_one_is_partial_and_names_both` (1)
  * `test_a_standing_feed_failure_is_named_in_the_footer_and_the_search_is_complete` (1)
* `debate_core/tests/application/test_federated_search_articles.py`: 1 cases, smallest real timer 15 s
  * `test_the_service_stores_the_matched_results_and_returns_the_ranking_and_articles` (1)
* `debate_core/tests/application/test_search_index_refresh_checked_against.py`: 15 cases, smallest real timer 300 s
  * `test_index_refresh_a_different_index_is_published_as_before_and_records_nothing` (1)
  * `test_index_refresh_a_record_beside_another_manifest_is_not_read` (1)
  * `test_index_refresh_rebuilding_under_the_list_the_manifest_names_writes_nothing` (1)
  * `test_index_refresh_rebuilding_under_the_list_the_record_names_writes_nothing` (1)
  * `test_index_refresh_record_bytes_name_no_path_and_are_written_like_the_manifest` (1)
  * `test_index_refresh_record_comes_back_beside_the_manifest_a_run_restores` (1)
  * `test_index_refresh_record_is_never_read_by_the_function_which_loads_the_index_as_before` (1)
  * `test_index_refresh_record_pends_when_the_session_expires_before_it_is_written` (1)
  * `test_index_refresh_records_a_longer_list_after_a_rebuild_from_nothing_as_the_cloud_rebuilds` (1)
  * `test_index_refresh_records_a_longer_list_beside_the_manifest_without_uploading_the_index` (1)
  * `test_index_refresh_restore_leaves_out_a_record_beside_another_manifest` (1)
  * `test_index_refresh_restore_without_a_record_restores_the_manifest_alone` (1)
  * `test_index_refresh_writes_no_record_once_the_runs_lease_was_taken` (1)
  * `test_index_refresh_writes_the_record_again_for_a_list_longer_still_and_nothing_else` (1)
  * `test_index_refresh_writes_the_record_under_the_runs_lock` (1)
* `debate_core/tests/integrations/bedrock/test_prompt_registry_wiring.py`: 2 cases, smallest real timer 300 s
  * `test_live_mode_sends_a_structured_call_with_the_text_the_registry_renders` (1)
  * `test_record_mode_sends_the_call_and_writes_a_cassette_replay_then_serves` (1)
* `debate_core/tests/integrations/bedrock/test_router.py`: 78 cases, smallest real timer 300 s
  * `TestBedrockModelRouterContract::test_a_refused_answer_is_described_without_its_values` (1)
  * `TestBedrockModelRouterContract::test_an_answer_is_validated_strictly_without_coercion` (1)
  * `TestBedrockModelRouterContract::test_an_answer_that_does_not_fit_the_schema_is_refused_naming_the_prompt` (1)
  * `TestBedrockModelRouterContract::test_embed_returns_one_vector_per_text_in_order` (1)
  * `TestBedrockModelRouterContract::test_per_call_overrides_are_reported_on_the_route` (1)
  * `TestBedrockModelRouterContract::test_rerank_names_every_document_once_best_first` (1)
  * `TestBedrockModelRouterContract::test_structured_output_is_an_instance_of_the_requested_schema` (3)
  * `TestBedrockModelRouterContract::test_the_resolved_route_is_populated` (3)
  * `TestBedrockModelRouterContract::test_usage_is_reported` (1)
  * `test_a_client_is_built_once_per_region_and_timeout` (1)
  * `test_an_invalid_answer_carries_the_usage_of_the_call_that_produced_it` (1)
  * `test_embed_asks_for_the_dimensions_the_route_names` (1)
  * `test_embed_refuses_a_response_with_no_usable_vector` (3)
  * `test_embed_reports_no_token_count_when_a_response_lacks_one` (1)
  * `test_embed_sends_one_titan_request_per_text_in_order` (1)
  * `test_first_call_asks_each_question_by_changing_the_adapters_request_in_one_way` (1)
  * `test_first_call_counts_the_tokens_its_accepted_calls_were_billed` (1)
  * `test_first_call_denied_access_stops_a_route_without_sending_the_rest` (1)
  * `test_first_call_probes_each_model_once_however_many_routes_name_it` (1)
  * `test_first_call_records_each_refusal_with_bedrocks_code_and_message` (1)
  * `test_first_call_signs_every_client_with_the_profile_it_is_given` (1)
  * `test_rerank_orders_results_best_first_whatever_order_they_arrive_in` (1)
  * `test_rerank_refuses_results_that_do_not_name_each_document_once` (4)
  * `test_rerank_sends_every_document_in_one_cohere_request` (1)
  * `test_retry_a_throttled_call_until_it_succeeds_counting_each_attempt` (1)
  * `test_retry_an_unavailable_model_then_report_it_unavailable` (3)
  * `test_retry_applies_to_embeddings_and_rerank_too` (1)
  * `test_retry_bound_of_one_attempt_sends_once` (1)
  * `test_retry_never_resends_a_refusal_a_validation_error_or_a_model_that_ran` (8)
  * `test_retry_stops_at_the_routes_attempts_and_reports_the_rate_limit` (1)
  * `test_retry_validation_error_keeps_the_providers_code_for_the_first_real_call` (1)
  * `test_retry_waits_are_jittered_below_their_ceiling` (1)
  * `test_retry_waits_grow_by_doubling_up_to_the_cap` (1)
  * `test_structured_output_called_twice_is_refused_rather_than_picked_from` (1)
  * `test_structured_output_cut_off_or_withheld_is_invalid_even_with_a_tool_call` (3)
  * `test_structured_output_from_another_tool_is_not_an_answer` (1)
  * `test_structured_output_is_accepted_on_a_finished_turn` (2)
  * `test_structured_output_is_validated_strictly_without_coercion` (1)
  * `test_structured_output_never_forces_the_tool` (3)
  * `test_structured_output_parses_the_tool_input_into_the_schema` (1)
  * `test_structured_output_refused_is_recorded_as_received_and_replays_as_the_same_error` (4)
  * `test_structured_output_reports_model_profile_region_and_request_id` (1)
  * `test_structured_output_reports_usage_from_the_response` (1)
  * `test_structured_output_sends_a_per_call_effort_over_the_routes` (1)
  * `test_structured_output_sends_a_temperature_only_when_one_is_set` (1)
  * `test_structured_output_sends_no_effort_temperature_or_output_config_the_route_lacks` (1)
  * `test_structured_output_sends_the_routes_effort_as_output_config` (1)
  * `test_structured_output_sends_the_schema_as_the_single_tool_with_tool_choice_auto` (1)
  * `test_structured_output_that_fails_the_schema_is_invalid_output` (1)
  * `test_structured_output_with_no_tool_call_is_invalid_output_naming_the_prompt` (1)
  * `test_the_client_comes_from_the_routes_region_and_timeout` (1)
  * `test_the_router_builds_each_client_with_its_profile` (1)
* `debate_core/tests/integrations/discovery/test_crossref.py`: 8 cases, smallest real timer 10 s
  * `test_a_429_holds_crossref_for_its_retry_after_and_one_without_for_the_cooldown` (1)
  * `test_a_query_not_asked_on_the_polite_pool_names_its_rate_and_no_cure` (1)
  * `test_eleven_queries_on_the_polite_pool_are_all_answered_at_one_and_a_half_seconds` (1)
  * `test_eleven_queries_on_the_public_pool_send_what_fits_and_leave_the_breaker_closed` (3)
  * `test_no_contact_email_reaches_a_log_line_an_error_a_repr_or_a_health_snapshot` (1)
  * `test_the_registry_answers_the_recorded_search_through_the_wrapper` (1)
* `debate_core/tests/integrations/discovery/test_feeds.py`: 2 cases, smallest real timer 10 s
  * `test_the_feed_registry_builds_rss_wrapped_and_it_answers` (1)
  * `test_the_google_news_registry_builds_it_wrapped_under_its_own_name` (1)
* `debate_core/tests/integrations/discovery/test_government.py`: 13 cases, smallest real timer 5 s
  * `test_federal_register_is_built_and_answers_with_no_key_configured` (1)
  * `test_federal_register_no_configured_secret_reaches_a_log_line_an_error_or_a_snapshot` (1)
  * `test_federal_register_redirects_open_the_breaker_and_the_open_breaker_sends_nothing` (1)
  * `test_govinfo_429_holds_it_for_the_cooldown_without_sending_again` (1)
  * `test_govinfo_key_reaches_no_log_line_error_repr_or_snapshot` (1)
  * `test_key_missing_is_reported_not_configured_for_every_query_not_as_an_error` (1)
  * `test_topic_absent_leaves_the_government_providers_neither_asked_nor_reported` (1)
  * `test_topic_gate_reports_a_government_provider_named_by_providers_as_not_configured` (2)
  * `test_topic_known_with_no_government_providers_asks_none_of_them` (1)
  * `test_topic_lists_a_provider_settings_do_not_enable_so_it_is_not_asked` (1)
  * `test_topic_that_lists_only_govinfo_does_not_ask_the_federal_register` (1)
  * `test_topic_that_lists_the_government_providers_asks_them_beside_the_others` (1)
* `debate_core/tests/integrations/discovery/test_openalex.py`: 5 cases, smallest real timer 10 s
  * `test_a_429_holds_openalex_for_its_retry_after_without_sending` (1)
  * `test_a_spent_daily_budget_holds_openalex_for_the_cooldown` (1)
  * `test_no_secret_reaches_a_log_line_an_error_a_repr_or_a_health_snapshot` (1)
  * `test_server_errors_open_the_breaker_and_the_open_breaker_sends_nothing` (1)
  * `test_the_registry_answers_the_recorded_search_through_the_wrapper` (1)
* `debate_core/tests/integrations/discovery/test_registry.py`: 2 cases, smallest real timer 10 s
  * `test_health_has_one_snapshot_per_provider_with_state_last_error_p50_and_counts` (1)
  * `test_no_key_or_contact_email_reaches_a_log_an_error_a_health_snapshot_or_a_repr` (1)
* `debate_core/tests/integrations/discovery/test_resilience.py`: 20 cases, smallest real timer 5 s
  * `test_a_call_inside_the_timeout_returns_the_adapters_response_unchanged` (1)
  * `test_a_cancelled_probe_leaves_the_breaker_half_open_for_the_next_call` (1)
  * `test_a_failed_call_is_made_exactly_once` (3)
  * `test_a_half_open_provider_sends_one_probe_and_skips_concurrent_calls` (1)
  * `test_a_rate_limit_holds_every_call_until_retry_after_has_passed` (1)
  * `test_a_rate_limit_without_retry_after_holds_for_the_cool_down` (1)
  * `test_a_response_under_another_name_is_a_failure` (1)
  * `test_after_n_consecutive_failures_calls_are_skipped_for_the_cool_down` (1)
  * `test_an_adapter_answering_a_different_number_of_queries_than_it_was_asked_has_failed` (1)
  * `test_an_adapters_own_timeout_error_is_not_mistaken_for_the_deadline` (1)
  * `test_an_open_provider_reports_when_it_will_probe` (1)
  * `test_an_untranslated_exception_becomes_provider_unavailable_naming_its_type` (1)
  * `test_every_query_asked_at_once_is_one_call_one_admission_and_one_success` (1)
  * `test_health_reports_counts_last_error_and_the_median_latency` (1)
  * `test_no_secret_reaches_an_error_its_cause_a_log_line_the_health_record_or_a_repr` (1)
  * `test_queries_asked_at_once_answered_under_another_name_have_failed` (1)
  * `test_queries_asked_at_once_are_refused_together_while_the_breaker_is_open` (1)
  * `test_the_median_is_taken_over_the_latency_window_only` (1)
* `debate_core/tests/integrations/opencaselist/test_client.py`: 8 cases, smallest real timer 5 s
  * `test_a_retry_after_that_is_not_digits_or_a_date_falls_back_to_the_backoff` (8)
* `debate_core/tests/integrations/s3/test_sts_caller_identity.py`: 19 cases, smallest real timer 5 s
  * `TestACredentialThatCannotBeAsked::test_an_expired_session_is_reported_with_the_login_for_its_profile` (1)
  * `TestAnAccountThatDoesNotAnswer::test_a_failure_inside_the_limit_is_translated_as_before` (1)
  * `TestAnAccountThatDoesNotAnswer::test_an_answer_inside_the_limit_is_the_answer` (1)
  * `TestAnAdapterBuiltFromAProfile::test_it_answers_for_the_role_that_profile_is_signed_in_as` (1)
  * `TestTheRoleACredentialIsSignedInAs::test_a_credential_that_is_not_a_role_has_no_role_name` (1)
  * `TestTheRoleACredentialIsSignedInAs::test_a_role_under_a_path_is_named_without_the_path` (1)
  * `TestTheRoleACredentialIsSignedInAs::test_a_user_with_its_own_key_has_no_role_name` (1)
  * `TestTheRoleACredentialIsSignedInAs::test_an_assumed_role_is_named_by_its_role_name_alone` (1)
  * `TestWhatIsReadOutOfTheAnswer::test_only_an_assumed_role_yields_a_name` (11)

</details>

<details>
<summary>Evidence search on the default 2.0-second <code>time.monotonic</code> budget: 127 functions, 227 cases (ruling 5: left as they are)</summary>

A stall of 2 seconds inside one search would turn its page partial. None has been seen to fail. If
one fails on CI, a shared standing-clock fixture becomes its own task (ruling 5).

* `debate_api/tests/test_search_pages.py`: 24 cases
  * `test_a_camp_result_counts_its_files_and_names_no_team` (1)
  * `test_a_cursor_from_another_search_is_refused_with_a_link_back_to_the_first_page` (1)
  * `test_a_date_filter_is_labelled_caselist_cards_only_next_to_it_and_leaves_camp_cards_out` (1)
  * `test_a_long_cards_result_carries_a_snippet_not_the_card_and_its_page_keeps_the_budget` (1)
  * `test_a_long_query_says_only_its_first_part_was_used` (1)
  * `test_a_query_with_only_excluded_words_says_there_is_nothing_to_search_for` (1)
  * `test_a_result_shows_its_tag_short_cite_snippet_counts_and_provenance_line` (1)
  * `test_a_search_answers_twenty_results_and_a_link_to_the_next_five` (1)
  * `test_a_search_rechecks_the_pointer_by_conditional_get_five_minutes_on` (1)
  * `test_a_search_with_no_match_says_so` (1)
  * `test_a_side_filter_is_labelled_caselist_cards_only_next_to_it_and_leaves_camp_cards_out` (1)
  * `test_each_filter_narrows_the_results` (5)
  * `test_every_search_page_keeps_the_weight_budget_before_its_card_body` (1)
  * `test_every_search_page_loads_only_the_first_party_script_and_stylesheet_and_nothing_inline` (1)
  * `test_hostile_card_text_is_escaped_on_the_results_and_card_pages` (1)
  * `test_no_search_page_names_another_origin` (1)
  * `test_once_the_index_is_loaded_the_caselist_filter_offers_its_stores` (1)
  * `test_the_app_logs_no_query_card_id_or_card_text_for_a_search_a_card_view_and_a_copy` (1)
  * `test_the_filters_keep_their_values_on_the_results_page` (1)
  * `test_without_those_filters_the_camp_card_is_found_and_neither_note_is_applied` (1)
* `debate_api/tests/test_search_pages_find_on_openev.py`: 5 cases
  * `test_a_camp_card_from_unknown_shows_no_link_whatever_the_table_says` (1)
  * `test_on_a_format_two_index_the_camp_card_links_too` (1)
  * `test_the_link_is_the_camps_word_and_year_whatever_the_title_or_stored_id_say` (1)
  * `test_the_results_page_links_to_no_camp_page` (1)
  * `test_the_years_upper_bound_is_the_apps_own_clocks_season_plus_one` (1)
* `debate_api/tests/test_search_pages_follow_ups.py`: 16 cases
  * `test_a_card_opened_from_a_results_page_links_back_to_that_page` (1)
  * `test_a_card_opened_from_the_first_page_links_back_to_the_first_page` (1)
  * `test_a_card_page_with_its_search_still_writes_only_its_card_viewed_record` (1)
  * `test_a_cursor_from_an_index_since_replaced_lands_on_a_new_search` (1)
  * `test_a_cursor_from_another_search_lands_on_a_new_search` (1)
  * `test_a_search_shows_how_many_cards_matched_above_the_results_on_every_page` (1)
  * `test_a_search_with_no_match_or_nothing_to_search_for_shows_no_count` (1)
  * `test_each_result_links_to_its_card_with_the_searchs_words_filters_and_page` (1)
  * `test_past_the_cap_the_count_says_more_than_the_cap` (1)
  * `test_the_count_is_for_the_query_and_its_filters` (6)
  * `test_the_searched_audit_record_still_counts_the_first_pages_results_not_the_total` (1)
* `debate_api/tests/test_search_pages_passage.py`: 10 cases
  * `test_a_passage_finds_the_card_holding_most_of_its_words` (1)
  * `test_a_passage_or_prefix_search_logs_none_of_its_words` (1)
  * `test_a_passage_search_pages_counts_and_comes_back_in_passage_mode` (1)
  * `test_a_passage_search_writes_one_searched_record_with_its_result_count_only` (1)
  * `test_a_plain_search_cursor_is_refused_in_passage_mode` (1)
  * `test_a_prefix_finds_every_word_it_starts` (1)
  * `test_a_prefix_under_three_letters_is_refused_with_a_message_and_no_record` (1)
  * `test_on_format_one_a_passage_search_says_it_is_not_available_yet` (1)
  * `test_on_format_one_a_plain_search_runs_and_says_words_are_matched_as_written` (1)
  * `test_the_search_form_keeps_search_by_passage_ticked_on_its_results` (1)
* `debate_core/tests/application/test_evidence_search.py`: 64 cases
  * `test_evidence_search_answers_not_found_when_every_occurrence_is_suppressed` (1)
  * `test_evidence_search_cursor_from_another_query_filters_or_index_is_refused` (1)
  * `test_evidence_search_fills_a_page_past_hidden_cards_and_skips_none` (1)
  * `test_evidence_search_filters_keep_the_documents_written_by_hand` (17)
  * `test_evidence_search_first_seen_leaves_camp_cards_out_and_says_so` (1)
  * `test_evidence_search_gives_no_team_count_when_a_survivor_kept_no_provenance` (1)
  * `test_evidence_search_hides_a_card_whose_representative_is_suppressed` (1)
  * `test_evidence_search_hit_carries_what_a_results_page_shows` (1)
  * `test_evidence_search_leaves_out_a_suppressed_occurrence_and_counts_again` (1)
  * `test_evidence_search_never_matches_a_school_team_tournament_round_camp_or_title` (16)
  * `test_evidence_search_pages_hold_twenty_then_twenty_then_five_in_ranking_order` (1)
  * `test_evidence_search_pages_under_a_filter` (1)
  * `test_evidence_search_past_its_budget_returns_what_it_has_flagged_partial` (1)
  * `test_evidence_search_prefix_searches_only_the_field_it_names` (11)
  * `test_evidence_search_side_and_first_seen_filters_each_say_so` (1)
  * `test_evidence_search_side_filter_leaves_camp_cards_out_and_says_so` (4)
  * `test_evidence_search_stopped_after_finding_the_next_hit_resumes_at_that_hit` (1)
  * `test_evidence_search_with_nothing_to_search_for_returns_no_results_and_says_so` (1)
  * `test_evidence_search_within_its_budget_is_not_partial` (1)
  * `test_evidence_search_without_a_predicate_hides_nothing` (1)
* `debate_core/tests/application/test_evidence_search_cursor_check.py`: 8 cases
  * `test_a_cursor_the_search_refuses_is_refused_by_the_check_too` (7)
  * `test_a_cursor_the_search_wrote_is_accepted_for_its_query_and_filters` (1)
* `debate_core/tests/application/test_evidence_search_passage.py`: 36 cases
  * `test_format_one_passage_search_is_not_run_and_says_so` (1)
  * `test_format_one_plain_search_matches_words_as_written_and_says_so` (5)
  * `test_format_one_short_prefix_says_both` (1)
  * `test_passage_finds_the_cards_sharing_most_of_its_words_best_first` (1)
  * `test_passage_hides_and_counts_without_a_suppressed_card` (1)
  * `test_passage_leaves_out_a_card_sharing_fewer_than_the_minimum` (1)
  * `test_passage_of_stop_words_alone_has_nothing_to_search` (1)
  * `test_passage_of_the_same_words_as_plain_words_finds_only_the_card_holding_all` (1)
  * `test_passage_pages_and_its_cursor_is_refused_by_the_plain_search` (1)
  * `test_passage_share_is_the_services_setting` (5)
  * `test_passage_takes_the_filters` (1)
  * `test_prefix_matches_every_word_it_starts` (6)
  * `test_prefix_under_three_characters_is_refused_and_says_so` (3)
  * `test_stemmed_word_matches_its_other_forms` (8)
* `debate_core/tests/application/test_evidence_search_ranking.py`: 1 cases
  * `test_search_ranking_weights_score_at_least_every_candidate_on_the_relevance_set` (1)
* `debate_core/tests/application/test_evidence_search_result_count.py`: 25 cases
  * `test_a_count_stopped_part_way_is_left_out_while_the_page_is_whole` (1)
  * `test_a_query_with_nothing_to_search_for_has_no_count` (1)
  * `test_a_suppressed_representative_is_not_counted_as_it_is_not_shown` (1)
  * `test_every_page_carries_the_exact_count_for_its_filters` (10)
  * `test_the_count_equals_the_results_a_student_can_page_through` (5)
  * `test_the_count_is_exact_up_to_the_cap_and_marked_more_past_it` (5)
  * `test_the_count_is_for_the_parsed_query_not_its_spelling` (1)
  * `test_the_count_reads_on_past_suppressed_rows_to_reach_the_cap` (1)
* `debate_core/tests/application/test_search_index_holder.py`: 14 cases
  * `test_a_clock_that_runs_backwards_rechecks_rather_than_trusting_the_last_check` (1)
  * `test_a_failed_recheck_keeps_the_current_index_serving_and_waits_an_interval` (1)
  * `test_a_new_pointer_is_fetched_to_a_new_path_swapped_in_and_the_old_file_deleted` (1)
  * `test_a_refused_new_index_leaves_the_current_one_serving` (1)
  * `test_a_refused_pointer_is_not_fetched_again_until_it_changes` (1)
  * `test_an_environment_frozen_past_five_minutes_rechecks_before_it_answers` (1)
  * `test_an_index_swapped_out_under_a_request_is_deleted_when_that_request_ends` (1)
  * `test_five_minutes_on_the_pointer_is_read_by_conditional_get_and_an_unchanged_one_costs_no_body` (1)
  * `test_the_checked_file_is_read_only_and_opened_read_only_and_immutable` (1)
  * `test_the_first_lease_reads_the_pointer_then_the_manifest_then_streams_the_object` (1)
  * `test_the_recheck_comes_five_minutes_on_as_adr_0019_sets_it` (1)
  * `test_the_same_index_republished_is_not_fetched_again` (1)
  * `test_with_no_index_loaded_every_lease_tries_again` (1)
  * `test_within_five_minutes_no_request_reads_the_pointer_again` (1)
* `debate_core/tests/application/test_search_index_holder_app_log.py`: 3 cases
  * `test_a_cold_load_logs_its_time_its_file_and_object_bytes_and_the_directory_total` (1)
  * `test_a_passage_search_logs_its_time_alone_and_no_line_holds_the_query` (1)
  * `test_at_a_replacement_the_directory_total_is_the_peak_both_files_before_the_old_one_goes` (1)
* `debate_core/tests/application/test_search_index_holder_formats.py`: 4 cases
  * `test_holder_keeps_serving_when_a_format_it_does_not_read_is_published` (1)
  * `test_holder_moves_from_format_one_to_format_two_when_the_weekly_update_publishes_it` (1)
  * `test_holder_serves_a_format_one_index_and_says_what_it_cannot_do` (1)
  * `test_holder_serves_a_format_two_index_with_stems_and_passages` (1)
* `debate_core/tests/application/test_search_index_holder_suppression.py`: 14 cases
  * `test_a_card_removed_whole_is_gone_from_results_and_its_page_at_five_minutes_and_not_before` (1)
  * `test_a_card_whose_representative_is_withdrawn_is_not_found_until_the_next_build` (1)
  * `test_a_list_holding_a_line_this_build_cannot_read_is_refused_whole` (3)
  * `test_a_list_that_cannot_be_read_refuses_the_request_and_the_next_one_tries_again` (1)
  * `test_a_withdrawal_of_another_disclosure_of_the_same_bytes_hides_nothing` (1)
  * `test_a_withdrawn_disclosure_leaves_the_card_with_the_other_teams_file` (1)
  * `test_an_environment_frozen_past_five_minutes_rereads_the_list_before_it_answers` (1)
  * `test_an_unsuppress_brings_the_card_back_at_the_next_reread` (1)
  * `test_closing_the_holder_forgets_the_list_so_the_next_lease_reads_it_whole` (1)
  * `test_five_minutes_on_an_unchanged_list_costs_a_conditional_get_and_no_body` (1)
  * `test_the_list_is_read_before_the_pointer_and_not_again_within_five_minutes` (1)
  * `test_with_no_list_in_the_bucket_nothing_is_hidden` (1)
* `debate_core/tests/application/test_search_index_refresh_checked_against.py`: 1 cases
  * `test_index_refresh_record_is_never_read_by_the_function_which_loads_the_index_as_before` (1)
* `debate_core/tests/integrations/local/test_search_index_reader_sqlite_features.py`: 2 cases
  * `test_search_index_reader_never_raises_a_syntax_error_on_any_query` (1)
  * `test_search_index_reader_runs_only_statements_sqlite_3_40_has` (1)

</details>

**PacerTime** still serves one file (`test_search_command.py`), so it stays there. The PM's
condition for moving it into `debate_core.testing` is not met. It is a near copy of
`test_crossref.py`'s `VirtualTime`; merging the two would be a refactor for another task.

## Files changed

* `packages/debate_cli/tests/test_search_command.py`: `moving_clock` removed; the `on_virtual_time`
  fixture; the footer test and the two provider-timeout tests use it, with docstrings saying why.
* `packages/debate_core/tests/integrations/opencaselist/test_client.py`: the simulated wall clock
  stands at `IN_2030`; the Retry-After date test writes its date from it and asserts exactly.
* `packages/debate_core/tests/integrations/s3/test_sts_caller_identity.py`: the two no-answer tests
  run on `run_in_virtual_time` and assert the loop's clock.
* `packages/debate_core/tests/testing/selector_polls.py` (new): records what the virtual loop asks
  the real selector, and asserts it only polled.
* `packages/debate_core/tests/testing/test_virtual_time.py`, `packages/debate_core/tests/application/test_federated_search.py`:
  the five 0.1 s bounds replaced by that check; `REAL_TIME_BUDGET_SECONDS` and the `time` imports removed.
* `plan_specs/v1/e07-discovery-adapters/t16-public-pool-footer-test-on-an-injected-clock.yaml`: phase `Succeeded`.
* This report.

## Deviations from the spec

* **The scope is the PM's narrowing and rulings of 2026-11-05, not the spec's description.**
  `v1-e32-t49` did the footer test's pacer in `def4453`; this task added its loop (ruling 1). The
  spec text is unchanged here; the PM amends it in the next batch.
* **Fixed beyond the footer test, as the rulings asked:** ten more test functions, in
  `debate_cli/tests` and `debate_core/tests` only.
* **One test outside `constraints.packages` is named, not touched:** the `tests/scripts` pty test
  (ruling 6).

## Decisions and assumptions

* **`VirtualTimeEventLoop` rather than PacerTime for the CLI tests and the STS pair.** Their waits are
  timeouts and `wait_for` on the loop's clock, so the loop is the seam those calls already read. For
  the CLI it is reached through the command's own `_run`, which runs one coroutine with
  `asyncio.run`. The search path does no thread offloads (`to_thread`, `run_in_executor`), so the
  virtual loop cannot jump past real work.
* **"The virtual loop's selector was only ever asked to poll" is read at the real selector beneath
  it.** The virtual loop's own selector is asked to wait for each timer by design; what it must never
  do is pass a wait on to the real selector. `selector_polls` records calls only from subclasses of
  `DefaultSelector`, so a plain selector elsewhere in the process is not counted. It also asserts the
  recording saw something, so a check that recorded nothing cannot pass.
* **The OpenCaselist fixture's wall clock stands at a fixed instant** instead of the real now. Its
  docstring said it started at the real now only for the Retry-After date test. `test_client.py`
  passes whole after the change (72 passed).
* **Assertions got tighter, never looser.** `any(100 <= s <= 121)` became `== [120.0]`. The STS
  bounds of `< 2` and `< 3` s became `== 0.2` and `== 0.4` on the loop's clock. A bound that real time
  was under 0.1 s became "the real selector never waited".
* **The 2-second line** is a judgement. Moving it to 3 s adds nothing new: the evidence-search group,
  at 2 s, is listed and ruled on. Moving it to 1 s leaves the same tests fixed and filed.

## Operator follow-ups

None.

## Follow-up work

Filed by the PM on 2026-11-05 from this task's questions; listed here so the report stands alone:

* E31, p3 (ruling 3): a parse worker's time limit starts when the worker reports ready.
  `test_a_parse_past_the_time_limit_is_stopped_and_the_run_carries_on` is left as it is.
* E40, p3 (ruling 4): `test_writers_waiting_together_share_one_renewal` releases its writers on a
  test hook the run lock offers when a writer starts waiting.
* E41, p3 (ruling 6): the pty key test's 0.3 s timer in `tests/scripts/test_compare_card_clusters.py`
  (`scripts/compare_card_clusters.py`).

Not filed: the six wall-clock performance budgets above. They are listed for the PM; I propose
nothing for them.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
