# Session report: v1-e39-t14-index-shrink-guard

| | |
|---|---|
| Task | `v1-e39-t14-index-shrink-guard` — An index that would drop most of the cards is never published |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t14-index-shrink-guard.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t14-index-shrink-guard.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t14-index-shrink-guard` |
| Session status | COMPLETE (Goal Succeeded after the PM's ruling on ac3; see [PM conditions](#pm-conditions)) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`tub index publish` and the weekly run's search index stage now share one check,
`check_index_size` in `debate_core.application.search_index_publish`. Before the first upload,
`SearchIndexPublishService.publish` reads `current.json` and the manifest it names, then refuses
three things. First, an index built from a store whose aggregates hold no rows, even at a first
publish. Second, an index holding none, or under `caselist.search_index_minimum_share_percent`
(90), of a store's documents in the current index, compared store by store. Third, any publish
when the current index cannot be read. Each refusal names the store, both counts and the index
left current, and `current.json` is untouched. `--allow-shrink "<reason>"` publishes a real
shrink. Its reason goes in the result, the `--json` data, a stderr line and a log line, never in
the manifest or the pointer. The weekly stage reaches the check through the same service, never
passes the override (by test and by mutant), reports a refusal as a failed stage, and records each
run's growth against the index it would replace.

**Look first at three things.** Deviation 1: ac3 says "measured on the function from its app log",
but the app log records no bytes, so this is worked out from the holder's code (the PM amended ac3 to match, ruling 1a, and the
Goal is now Succeeded). Decision 2: an unreadable current index now refuses the publish, which replaces one
`v1-e39-t09` rule. Deviation 2: the build already refused the 2026-10-22 empty aggregates. The
exposure the guard closes is a build of fewer stores, such as 4e's index of a few documents
replacing dev's 52,059.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `shrink-guard` (Index shrink guard) | Done | Red skeleton `ce9b366`, green `20fccc4`, docs and spec comment `c3e7fa9`, more tests `0993c0b`. Its criterion passes (below). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a build under the configured share of the current index, or from a store with empty aggregates, is refused before publishing and leaves the pointer, by tests shown failing first, in both the command and the weekly stage | PASS | Red run on the skeleton `ce9b366`: 21 failed, 12 passed ([the red run](#the-red-run)). Green: the tests named there. In the command: `test_search_index_publish_refuses_one_store_under_the_share_and_leaves_the_pointer`, `…_a_store_at_0_with_the_total_fine_and_leaves_the_pointer`, `…_a_first_index_of_empty_aggregates_and_writes_no_pointer`, `…_every_store_emptied_over_the_current_index`, and the CLI's `test_tub_index_publish_refuses_an_index_that_drops_a_stores_documents`. In the weekly stage: `test_index_stage_refuses_a_shrunken_index_and_leaves_the_pointer_and_the_local_index`, `test_index_stage_refuses_a_store_at_0_with_the_total_fine` and `test_index_stage_refuses_every_stores_aggregates_emptied_and_leaves_the_pointer`. The last one passed at red: the build already refuses an empty occurrence table (Deviation 2). The run around the stage: `test_index_stage_refused_by_the_shrink_guard_is_named_in_the_summary_details_and_notification`. |
| ac2: `--allow-shrink` with a reason publishes and records the reason (in the manifest, as written); the weekly stage never passes it, by test | PASS as amended | The PM's ruling, now a comment above ac2 in the spec: the reason is recorded in the publish's output, not the manifest. `test_search_index_publish_with_allow_shrink_publishes_and_records_the_reason_outside_the_manifest` checks the result, the log line's `reason`, `replaced` and `stores_shrunk`, and that the bucket's manifest is the local file byte for byte. `test_tub_index_publish_with_allow_shrink_publishes_and_prints_the_reason` checks `data.allowed_shrink` and the stderr line; `…_prints_the_reason_in_its_table_too` checks the table. The stage never passes it: `RecordingPublisher.overrides == [None, …]` in four stage tests, and mutant 15 below. |
| ac3: the replacement's peak temporary storage, measured on the function from its app log, reported to the PM with a recommendation on ADR-0019's lines; each run's growth in its record | PASS as amended (PM ruling 2026-10-22, now a comment above ac3: worked out from the holder's code). As first written: NOT RUN | **Measured on the function from its app log: NOT RUN.** The function logs `search index <id> loaded` and `… closed and deleted` with no byte counts, and the brief says not to change the holder here. No session or hand-off can take that measurement until a log line carries the bytes (Follow-up 2). **Worked out from the holder's code, as the brief asks:** [The storage measurement](#the-storage-measurement), written into `docs/data/search-index.md`, with the recommendation. **Growth per run: PASS.** `test_index_stage_records_each_runs_growth_against_the_index_it_replaced`, `…_a_refused_runs_shrink_as_negative_growth`, `…_that_changed_nothing_records_no_growth`; the run summary and run details carry the four keys (`test_index_stage_runs_after_parse_and_before_landscape_even_when_nothing_was_imported`, and the refusal test above). |
| Node `shrink-guard`: `uv run pytest packages/debate_core/tests/application -k search_index` | PASS | `182 passed in 8.75s` (before the last commit's 6 new tests; after it, `-k "search_index or index_stage"`: `199 passed in 7.95s`). |

## The red run

The skeleton (`ce9b366`) had every new name with its real signature. `check_index_size` refused
nothing, `publish` treated an unreadable current index as none, and the stage recorded no growth.
Command:
`.venv/bin/python -m pytest -n 0 -p no:randomly -q -rA packages/debate_core/tests/application/test_search_index_shrink_guard.py`
plus the four new CLI tests by node id. Result: **21 failed, 12 passed**.

| Failed for | Tests |
|---|---|
| `DID NOT RAISE SearchIndexWouldShrink` (6) | the rule's under-the-share, store-at-0, share-of-0 and every-store-named tests; the publish's under-the-share and store-at-0 tests |
| `DID NOT RAISE SearchIndexStoreEmpty` (4) | the rule's first-publish and against-a-current-index tests; the publish's first-publish and every-store-emptied tests |
| `DID NOT RAISE CurrentSearchIndexUnreadable` (2) | the publish's unreadable pointer and unreadable manifest |
| No refusal: the stage `COMPLETED`, the CLI exited 0, or `allowed_shrink` was `None` (9) | the stage's two refusals and its two growth tests; the rule's and the publish's override tests; the CLI's refusal and its two override tests |

The 12 that passed at red, and why: the five must-not-refuse cases (a store at exactly 90%, a
store the current index does not hold, a reason the guard did not need, the weekly stage at the
share, no growth on an unchanged run, where the fields default to `None`). The six reason-shape
checks, which are input validation in the skeleton. And the weekly stage over every store's
aggregates emptied, which the build refuses with `SearchIndexStoreNotReady` since `v1-e39-t02`.

## Mutation runs

Each mutant was applied alone, run with `-n 0 -p no:randomly -x` against
`test_search_index_shrink_guard.py`, `test_search_index_stage.py` and
`test_search_index_publish.py`, with a new empty `HYPOTHESIS_STORAGE_DIRECTORY` (none of these
tests uses Hypothesis), and restored with a byte comparison. The runner is in the session
scratchpad, not the repo. **24 of 24 caught.**

| # | Mutant | Caught by |
|---|---|---|
| 0 | share: `<` becomes `<=` | `…passes_a_store_at_exactly_the_share` |
| 1 | share: the percent compared without `* 100` | `…refuses_one_store_under_the_share_though_the_total_grew` |
| 2 | share: `<` becomes `>` | the same |
| 3 | share: the zero rule removed | `…refuses_a_store_at_0_whatever_the_share_is_set_to` |
| 4 | share: the index's total instead of the store's count | `…under_the_share_though_the_total_grew` |
| 5 | share: a store missing from the build counts as unchanged | `…holds_at_0_with_the_total_fine` |
| 6 | loop: a store the current index holds at 0 is compared | `…does_not_compare_a_store_the_current_index_does_not_hold` |
| 7 | loop: only the first store | `…holds_at_0_with_the_total_fine` |
| 8 | loop: stops at the first shrink | `…names_every_store_it_refuses_for` |
| 9 | loop: only the stores the new index has | `…holds_at_0_with_the_total_fine` |
| 10 | empty: the rule disabled | `…empty_aggregates_at_a_first_publish` |
| 11 | empty: not applied at a first publish | the same |
| 12 | empty: passed by a reason | `…empty_aggregates_against_a_current_index_and_with_a_reason` |
| 13 | publish: an unreadable current index passed without a reason | `…when_the_current_index_cannot_be_read[pointer…]` |
| 14 | publish: the current index never read | `…publish_refuses_one_store_under_the_share_and_leaves_the_pointer` |
| 15 | stage: passes `allow_shrink="weekly run"` | `test_index_stage_refuses_a_shrunken_index_and_leaves_the_pointer_and_the_local_index` |
| 16 | stage: a shrink refusal reported as skipped, not failed | the same |
| 17 | stage: no `--allow-shrink` hint on a shrink | the same |
| 18 | stage: growth's sign reversed | `…records_each_runs_growth_against_the_index_it_replaced` |
| 19 | stage: growth recorded against the same index | `…that_changed_nothing_records_no_growth` |
| 20 | current: a missing manifest read as nothing published | `…a_pointer_whose_manifest_cannot_be_used[missing…]` |
| 21 | current: an unparseable manifest read as nothing published | `…[unparseable…]` |
| 22 | current: another index's manifest accepted | `…[another index's…]` |
| 23 | the share's 0 to 100 range not checked | `…takes_a_share_of_0_to_100[-1]` |

**The share and loop mutants against the weekly stage's tests alone** (`-k index_stage`), to show
the stage reaches the same function rather than a copy of it. Mutants 0, 4, 7 and 14 were caught by
stage tests. Mutants 3, 5 and 10 survived there, and each is equivalent on the stage's path. At the
default 90%, a store at 0 is also under the share. The stage always builds the same stores, so
none goes missing from a build. The build refuses empty aggregates before the publish is reached.
The rule's and the publish's tests catch all three (above).

## The storage measurement

Worked out from `SearchIndexHolder` (`application/search_index_holder.py`) and
`S3SearchIndexSource.stream_object`; not measured on the function (ac3, NOT RUN as written). The
holder is unchanged. Written into
[`docs/data/search-index.md`](../data/search-index.md#the-functions-temporary-storage-while-one-index-replaces-another).

**What exists at once while index A serves and the pointer names B:**

1. A's SQLite file, in `/tmp/tub-index/`, until the swap.
2. **No gzip file.** The object streams from S3 in 1 MiB chunks through `zlib` and both sha256s
   into `<B>-<uuid>.part`, which grows to B's SQLite size.
3. The `.part` file is renamed to `.sqlite`, the same file, so nothing is copied.
4. The swap deletes A at once: the refresh runs under the lock before the request takes its lease,
   and Lambda gives an environment one request at a time, so no lease on A is open. A refused
   download deletes its `.part` file. A new process deletes leftover `.sqlite` and `.part` files.

**Peak = A's SQLite + B's SQLite.** The holder never keeps more than one old index. A second one
could only exist if a request still held A while B replaced it, and on Lambda none can. The reader
opens `mode=ro&immutable=1`, so no journal. SQLite's own temporary files for a large sort are not
counted. Nothing else in `debate_api` writes `/tmp` (its only `tempfile` use names the holder's
directory).

| Case | Peak bytes | Share of 4,096 MB (4,294,967,296 bytes) |
|---|---|---|
| Today: 839,438,336 replaced by the same size | 1,678,876,672 | 39.1% |
| Next week at 11.6%: 839,438,336 + 936,813,183 | 1,776,251,519 | 41.4% |
| ADR-0019's 1 GB allowance, 1 GB replacing 1 GB | 2,000,000,000 | 46.6% |
| `/tmp` full at a swap: a 2,029,757,701-byte file replaced by one 11.6% larger | 4,294,967,295 | 100% |

The 11.6% is documents, not bytes a document: 52,059 against the 46,658 of 2026-10-20, at the same
16,125 SQLite bytes a document. At 11.6% every week, the SQLite file passes 900,000,000 within the
week, 1 GB in about two weeks, and fills `/tmp` at a swap in about eight. The gzip object
(314,054,035, a ratio of 0.374) passes 400,000,000 in about three weeks.

**Recommendation to the PM.**

1. **Leave the storage at 4,096 MB for now.** It is at 39% and binds only at about a 2.0 GB SQLite
   file. Raising it is one Terraform local (`function_ephemeral_storage_mb`, up to 10,240) at about
   a cent a month (ADR-0019's cost table). Raise it when the run summaries' growth puts that line
   within a month.
2. **Move the 900,000,000 SQLite warning to where storage binds,** for example 1,700,000,000 bytes:
   a same-size swap at 79% of `/tmp`. Amend ADR-0019 (c) 6's "1 GB uncompressed" to say storage
   allows about 2 GB at a swap. At today's growth the 900 MB warning fires from next week on, every
   week, and a warning that always fires stops being read. The 1 GB figure only stood in for the
   cold start, and the gzip line measures that directly.
3. **Keep the 400,000,000 gzip trigger as it is.** It is the one students feel (about 5 s at the
   625 Mbps cap), about three weeks away. `v1-e39-t04`'s bandwidth-quota request could start now,
   since AWS takes time to answer one.

## Files changed

- **`debate_core.application`**:
  - `search_index_publish.py`: the shrink guard. `check_index_size`, the three refusals,
    `current()`, `--allow-shrink`'s reason and its log line, and `PublishedSearchIndex.replaced`
    and `.allowed_shrink`.
  - `search_index_refresh.py`: the weekly stage reads the current index through the same service,
    records growth, and gives a refused shrink its own hint. `_published_pointer` is gone.
  - `caselist_sync.py` and `sync_runs.py`: four growth keys in the run summary and run details,
    both additive.
  - `settings.py`: `caselist.search_index_minimum_share_percent`.
- **`debate_cli`**: `tub index publish --allow-shrink REASON`, its `--json` data (`replaced`,
  `allowed_shrink`), a stderr note and the table caption. The container passes the share to the
  one publish service the command and the stage share.
- **Tests**:
  - `test_search_index_shrink_guard.py` (new): the rule, the publish service, and the stage.
  - `test_tub_index.py`: the CLI tests.
  - `test_caselist_sync_index_stage.py`: the run around a refusal, and the summary's four new keys.
  - `test_search_index_stage.py`: four `v1-e39-t09` tests adjusted (Deviation 3).
- **Docs**:
  - `docs/runbooks/caselist-scheduled-sync.md`: the outcome table, each run's growth, and
    [The shrink guard](../runbooks/caselist-scheduled-sync.md#the-shrink-guard) with the by-hand
    block.
  - `docs/runbooks/caselist-removal.md`: P3, a refused rebuild.
  - `docs/runbooks/evidence-search.md`: the app log table, so it no longer says "publish again"
    where the guard now needs `--allow-shrink`.
  - `docs/data/search-index.md`: the storage working.
- **Spec**: the PM's ruling comment above ac2, placed above the key and checked against the parsed
  YAML (the descriptions are unchanged).

## Deviations from the spec

1. **ac3's "measured on the function from its app log" is not done.** The function's log lines
   carry no byte counts, and the PM's brief says not to change the holder in this task. The peak
   is worked out from the code, as the brief asks. The relay prompt below asked the PM to amend
   ac3; the PM did (ruling 1a), and the Goal is Succeeded.
2. **The spec's premise about 2026-10-22.** The description says the next build "would have
   published an empty index". A build of those stores would not have: since `v1-e39-t02` the build
   refuses a store whose `occurrences.jsonl` is missing or holds no rows (`SearchIndexStoreNotReady`).
   The weekly stage reads this Mac's store, which was not emptied. The exposure the guard closes is
   a build of fewer stores, or a store emptied by suppression. That day, 4e published a scratch
   index of 2 documents (`a0c928bebd03f8aa`) over dev's 52,059 (`767b9c7c056b80cb`). The per-store
   rule now refuses that unless `--allow-shrink` says why. The empty-aggregate rule is still
   checked at the publish, from the manifest, against any directory however it was built
   (`test_search_index_publish_refuses_a_first_index_of_empty_aggregates_and_writes_no_pointer`).
3. **Four `v1-e39-t09` stage tests changed.** Each shrank a store of 2 cards to 1 (50%), which the
   guard now refuses. `…rebuilds_when_only_the_suppression_list_changed` starts from ten cards, so
   one suppressed keeps 90%. `…a_failed_upload…` and `…a_session_that_expires_mid_publish…` grow
   the store instead. `…never_removes_the_index_current_json_names` and `…a_failed_upload…` use a
   new `SwitchableBucket.refuse_upload`, because the old `refuse` also refused reads of the
   manifest key, which the publish now makes. What each test checks is unchanged.
4. **The spec's description and ac2 still say "recorded in the manifest".** I added the PM's
   comment as instructed and left the prose to the PM.
5. **`docs/guides/search-index.md` not updated.** It describes `tub index publish` but is outside
   `constraints.packages` (`docs/runbooks`, `docs/data`). See Follow-up 1.

## Decisions and assumptions

1. **The empty-store rule is never overridden**, not even by `--allow-shrink`. A store with no
   aggregate rows is a broken store, not a shrink; the fix is its rebuild, or a build without it.
2. **An unreadable current index refuses the publish** (`CurrentSearchIndexUnreadable`), and
   `--allow-shrink` passes it. That covers a pointer this build cannot parse, a missing manifest,
   one whose bytes are not the pointer's, one that does not parse, and one of another index. With
   nothing to compare, publishing could replace anything. This replaces `v1-e39-t09`'s rule that
   "a pointer this build cannot read is behind by definition: publishing replaces it". That rule
   would also let an older agent overwrite a newer build's pointer. **The PM may prefer the old
   rule;** the relay prompt asks.
3. **"A store the current index holds"** means one with more than 0 documents in it. A store held
   at 0 is not compared, so a store that is legitimately empty does not block every later publish.
4. **The comparison is in integers** (`kept * 100 < share * held`), so exactly 90% passes. The
   setting is a whole percent from 0 to 100. At 0, the store-at-0 rule still holds.
5. **Growth is measured against the index `current.json` named when the stage read it,** when that
   is another index. A refused run records its negative growth too. An unchanged run, a run without
   a session, and a first publish record none.
6. **The reason is one line of 1 to 200 characters**, checked in the CLI and the service. Nothing
   can check that it holds no card text. The help text and the runbook say what belongs in it (a
   request id), and it is never stored.
7. **The override line goes to stderr with `note`, not `detail`,** so it shows without
   `--verbose`. The CLI has no logger. The log line is the publish service's `logger.warning`, with
   `index_id`, `replaced`, `reason` and `stores_shrunk` as extras.

## Checks run

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `262 of 400 test files (65.5%)`, 7,160 tests (`--collect-only`): the root conftest imports `settings.py`. Past two minutes, so not run; the PR's `ci` runs the whole selection (agreement 10). |
| `.venv/bin/python -m pytest -n auto -m "not slow and not live" -q packages/debate_core/tests/application` (alarm 115) | `3122 passed in 88.61s` (before `0993c0b`'s 6 new tests and one deleted branch) |
| `.venv/bin/python -m pytest -n auto -m "not slow and not live" -q packages/debate_cli/tests tests/architecture tests/specs tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py packages/debate_api/tests/test_removal_runbook_index_prune.py` (alarm 115) | `1291 passed in 43.42s` |
| After `0993c0b`: `.venv/bin/python -m pytest -n auto -q -m "not slow and not live" packages/debate_core/tests/application -k "search_index or index_stage"` | `199 passed in 7.95s` |
| Coverage of the changed modules over their four test files | every new line covered; what is left uncovered predates this task |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1115 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 15 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 46 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/check_command_blocks.py` | `OK: no # comments in 349 shell code blocks in 138 Markdown files` |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | `All 43 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` | `OK: 420 files, 40 epics, 358 tasks, 22 releases` |

## Operator follow-ups

None. The next weekly run uses the guard; its summary's `search_index` now holds the growth keys.

## Follow-up work

1. **`docs/guides/search-index.md`** should mention the shrink guard and `--allow-shrink` beside
   its publish commands. The guide is E39's, outside this task's packages.
2. **A log line with the bytes on `/tmp`** (`search index <id> loaded`, plus the file's size and
   the directory's total) would let ac3's measurement be read from the app log, as ac3 asks. That
   changes the holder; `v1-e39-t10` or a small E39 task.
3. **ADR-0019's lines:** the PM's call on the recommendation above. If the 900,000,000 warning
   moves, it is `SQLITE_BYTES_WARNING` in `search_index_refresh.py`, plus the ADR's (c) 6 and the
   scheduled sync runbook.
4. **`v1-e39-t04`'s bandwidth-quota request,** about three weeks before the gzip object passes
   400 MB at this rate.

### Questions for the PM, ready to paste

```text
v1-e39-t14 (index shrink guard) is done and committed. The Goal is left InProgress for one criterion. Two rulings, please:

1. ac3 says the peak temporary storage is "measured on the function from its app log". The app log has no byte counts (only "search index <id> loaded" and "... closed and deleted"), and your brief said not to change the holder in this task. So I worked it out from the holder's code, as the brief asked. The peak is the old SQLite plus the new one, because the gzip object streams through zlib and never lands on disk: 1,678,876,672 bytes, 39.1% of 4,096 MB, today. It is in docs/data/search-index.md.
   Options:
   (a) Amend ac3 to "worked out from the holder's code". I then set the Goal to Succeeded. RECOMMENDED: it is what the brief asked for, and the code fully determines which files exist when.
   (b) Keep ac3 as written. Add a follow-up that puts the bytes into the "loaded" log line, and measure after it deploys. The Goal stays InProgress until then.

2. An unreadable current index now refuses the publish: an unparseable current.json, or a missing, mismatched, unparseable or other index's manifest. It is overridable with --allow-shrink. This replaces v1-e39-t09's rule that "a pointer this build cannot read is behind: publishing replaces it", for the weekly stage too.
   Options:
   (a) Keep the refusal. RECOMMENDED: with nothing to compare against, the guard cannot know what the publish replaces, and the old rule also lets an older agent overwrite a newer build's pointer.
   (b) Restore t09's rule: an unreadable pointer counts as nothing published, and only the empty-store rule applies.

FYI, proceeding unless told otherwise:
- The empty-aggregates rule is never overridden, even with --allow-shrink.
- The build already refused 2026-10-22's empty aggregates (since v1-e39-t02). The case the guard newly closes is a build of fewer stores, such as 4e's 2-document index replacing dev's 52,059.
- My recommendation on ADR-0019's lines: keep 4,096 MB; move the 900 MB SQLite warning to about 1.7 GB, where storage binds; keep the 400 MB gzip trigger, which is about three weeks away at 11.6% a week.

Reply: "1a" or "1b", and "2a" or "2b".
```

## PM conditions

The PM accepted on 2026-10-22 with five conditions, closed in this session after a sync. Commit ids
in this report are after the last sync, relative to `origin/dev` at `197f202` (#417); the red
skeleton is `ce9b366`, green `20fccc4`.

**The sync.** `scripts/task sync v1-e39-t14-index-shrink-guard` rebased the branch's seven commits
onto `bcf6972` without a conflict. Dev had gained `v1-e39-t11` (#415), which changed
`search_index_holder.py`. That change only adds `ScreenedSearch.check_cursor`; downloading,
swapping and deleting are untouched, and the reader still opens `mode=ro&immutable=1`. The storage
working stands as written.

| Condition | Done |
|---|---|
| 1. ac3 amended as in ruling 1, then the Goal `Succeeded` | The comment is above ac3; the parsed descriptions are unchanged. `uv run scripts/task_helper.py set-phase v1-e39-t14-index-shrink-guard Succeeded` → `phase: Succeeded`. |
| 2. `SQLITE_BYTES_WARNING` = 1,700,000,000, its pinning test by hand, ADR-0019 (c) 6, the runbook's warning line, `docs/adr` in the packages | `search_index_refresh.py`: the constant, its docstring, the module's "Size" section and the warning's sentence, which now names the function's ephemeral storage. `test_index_stage_warns_past_each_of_adr_0019s_lines`: the pin reads `(1_700_000_000, 400_000_000)`, written by hand, and a new case says 900,000,001 no longer warns. Against the old value it failed (`5 failed`, `assert (900000000, 400000000) == (1700000000, 400000000)`); against the new one `5 passed`. ADR-0019 (c) 6 is amended in place under "Amended 2026-10-22", with the original estimate kept and this report's working cited. The scheduled sync runbook's warning line moves. `docs/adr` and `docs/guides` are in `constraints.packages`, under the PM's comment. |
| Ruling 2a: record the replaced t09 rule in the scheduled sync runbook's stage outcomes | "A rule this replaced", under the outcome table. |
| 3. The shrink guard and `--allow-shrink` in `docs/guides/search-index.md` | Three refusals added to its "It refuses" list, and a section "Publishing a real shrink: `--allow-shrink`" beside the publish commands, with one command block. |
| 4. The spec's prose | Left to the PM. |
| 5. Sync, then the checks | Below. |

**The checks after the sync:**

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -n 0 -p no:randomly -q` over `test_search_index_shrink_guard.py`, `test_search_index_stage.py`, `test_search_index_publish.py`, `test_caselist_sync_index_stage.py` and the CLI's `test_tub_index.py` | `105 passed in 4.71s` |
| `.venv/bin/python -m pytest -n auto -m "not slow and not live" -q packages/debate_core/tests/application` (alarm 115) | `3174 passed in 84.27s` |
| The same over `packages/debate_cli/tests tests/architecture tests/specs tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py packages/debate_api/tests/test_removal_runbook_index_prune.py` | `1291 passed in 39.53s` |
| `uv run pytest packages/debate_core/tests/application -k search_index` (the node's criterion) | `188 passed in 7.06s` |
| `uv run scripts/affected_tests.py` | `262 of 404 test files (64.9%)`, past two minutes as before; the whole selection is the PR's `ci` |
| `ruff format --check .` / `ruff check .` | `1121 files already formatted` / `All checks passed!` |
| `pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` / `check_thin_handlers.py` | `Contracts: 15 kept, 0 broken.` / `OK: 46 … within 25 statements` |
| `scripts/validate_specs.py` | `OK: 423 files, 40 epics, 361 tasks, 22 releases` |
| `check_command_blocks.py --base origin/dev` / `docs_index.py --check-descriptions` | `OK: no # comments in 350 shell code blocks in 139 Markdown files (1 session reports changed since origin/dev)` / `All 43 indexed documents under docs/ have a description` |

**A second sync.** While the checks above ran, `v1-e33-t08` (#417) merged into dev. It touches none
of this task's files. `scripts/task sync` rebased the nine commits onto `197f202` without a conflict,
and everything was run again on that base: the five test files `105 passed in 4.67s`;
`packages/debate_core/tests/application` `3175 passed in 75.62s`; the CLI tests, the always-run list
and the docs tests `1291 passed in 37.00s`; `ruff format --check` `1124 files already formatted`,
`ruff check`, pyright (`0 errors`), `lint-imports` (`15 kept, 0 broken`), `check_thin_handlers.py`,
`validate_specs.py` (`OK: 423 files`), `check_command_blocks.py --base origin/dev` (`350 shell code
blocks in 140 Markdown files`) and `docs_index.py --check-descriptions`, all passing.

**For the PM's next batch, not changed here:** two other task specs still quote the old line.
`t09-weekly-index-refresh.yaml` (Succeeded) says "warns above 900,000,000 SQLite bytes" in its
description and a criterion. `t13-passage-search.yaml`'s description weighs its growth against "the
900,000,000-byte line". Both are other tasks' specs.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on conditions closed in this session before the pull request. Record them under "PM
conditions", set the Goal `Succeeded` once condition 1 is in, and open the pull request with no
`--partial`. If anything comes out differently from what is written here, stop and ask for another
review.

**What the PM checked.**
* The branch is clean, on origin/dev at `aa6d4b9`, and the diff is the 17 files listed.
* Since then dev has gained v1-e39-t11 (#415), which changes the search reader, the pages and
  `domain/evidence_search.py`, and v1-e33-t08 may land before you. So sync (condition 5).
* The command and the weekly stage reach one `check_index_size` through one service. The stage
  never passes the override, by test and by mutant 15.

**What is good.**
* **The premise correction (Deviation 2) is exactly right.** The build already refused empty
  aggregates, and the real exposure was 4e's 2-document index replacing 52,059. The per-store rule
  is what closes it.
* **The rule is precise.** Integer comparison, exactly 90% passes, and a store held at 0 is not
  compared. Running the mutants against the stage's tests alone shows the stage reaches the same
  function, with each survivor explained as equivalent on that path.
* **The storage working is careful.** The gzip streams through zlib and never lands, the swap
  deletes A at once, and Lambda's one request per environment means no second old index. The peak
  is A plus B: 39% today.

**Rulings on the PM questions.**

1. **1a: amend ac3 to "worked out from the holder's code".** The code fully determines which files
   exist when. The log line with bytes on `/tmp` (Follow-up 2) is already v1-e39-t10's ac5 (the
   holder's load lines in the app log, with the index's size); the PM adds the `/tmp` total to
   that brief. Add above ac3: `# PM ruling 2026-10-22: the peak is worked out from the holder's
   code (A's SQLite plus B's, the gzip streamed); the bytes on /tmp reach the app log with
   v1-e39-t10's ac5.`
2. **2a: keep the refusal,** overridable with `--allow-shrink`. With nothing to compare, the guard
   cannot know what it replaces, and t09's rule let an older agent overwrite a newer build's
   pointer. Record the replaced t09 rule in `docs/runbooks/caselist-scheduled-sync.md`, where the
   weekly stage's outcomes are listed.

**The FYIs are accepted.** That covers the empty-store rule, never overridden, and Deviation 3's
four adjusted t09 tests.

**On ADR-0019's lines, the recommendation is accepted.**
* **The storage stays at 4,096 MB.**
* **The 900,000,000 SQLite warning moves to 1,700,000,000.** A warning that fires every week stops
  being read, and storage binds at about 2 GB at a swap.
* **The 400,000,000 gzip trigger stays,** since that is the one students feel.

**Conditions, all closed in this session:**

1. **ac3** amended as in ruling 1.
2. **`SQLITE_BYTES_WARNING` = 1,700,000,000,** with the test that pins it changed by hand.
   * Amend ADR-0019 (c) 6's "1 GB uncompressed" to say storage allows about 2 GB at a same-size
     swap, the 1.7 GB warning leaving headroom, and the 400 MB gzip trigger unchanged. Cite this
     report's working.
   * Update the scheduled sync runbook's warning line.
   * Add `docs/adr` to `constraints.packages` with `# PM ruling 2026-10-22: ADR-0019 (c) 6's size
     line moves with the warning.`
3. **Follow-up 1 now:** add the shrink guard and `--allow-shrink` to `docs/guides/search-index.md`
   beside its publish commands, and add `docs/guides` to the packages under the same comment.
4. **The spec's prose (Deviation 4).** Leave the description and ac2's "manifest" wording to the
   PM's next batch; the ruling comment above ac2 stands.
5. **Sync** (`scripts/task sync`), then re-run:
   * the shrink-guard, stage and publish tests, and the changed directories with the always-run
     list;
   * pyright, `lint-imports`, ruff, `validate_specs.py` and the docs checks.

   Record the results.

**Placed by the PM.**
* `v1-e39-t04`'s bandwidth-quota request, about three weeks before the gzip object passes 400 MB,
  goes on the promotion list as an operator step with a date.
* The `/tmp` log line goes to v1-e39-t10.

**Operator follow-up:** none beyond the next weekly run. Its summary's `search_index` now carries
the growth keys, which the PM reads after Wednesday.
