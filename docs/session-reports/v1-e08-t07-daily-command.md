# Session report: v1-e08-t07-daily-command

| | |
|---|---|
| Task | `v1-e08-t07-daily-command` — `debate-research daily` digests |
| Spec | [`plan_specs/v1/e08-research-workflows/t07-daily-command.yaml`](../../plan_specs/v1/e08-research-workflows/t07-daily-command.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t07-daily-command` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research daily <preset> [--date YYYY-MM-DD] [--window 1d] [--format md|json] [--auto-cut N]` is
built. `config/daily_presets.yaml` ships `politics` and `nhi` (your ruling 1). Every preset in the file
is checked against the taxonomy, the provider names and the feed lists whenever `daily` runs.
`DigestService` (in `debate_core.application`) runs each preset query, expanded for each argument/need
pair, through `search`'s own `FederatedSearchService` for the window. It leaves out anything a digest of
another date listed, matched by canonical URL or DOI. It groups the rest by pair. The seen-set is saved
in `<data dir>/daily/seen/<preset>.json` only after the digest file is written.

The container builds the feed and Google News providers from the preset's feed topics alone.
`--auto-cut N` hands the new results to t06's `BatchCutService`. The provider footer is the search's
own, in the file, on stdout and in the JSON. Every acceptance criterion passes on synthetic fixtures,
offline. **The Goal is Succeeded.**

Look at these first:

1. **`BatchCandidate` gained an optional `need`** (Deviation 3). A digest's results come from searches
   for different needs, and `BatchCutRequest` carries one. The change adds a field that defaults to
   None, so `search --auto-cut` is unchanged: all 87 of its tests pass on the commit that changes
   nothing else.
2. **A second run of the same date lists that date's results again**, rather than writing an empty
   digest over the first one (Decisions). Question 1.
3. **Two changes outside the packages first listed**: `scripts/stamp_build.py` bundles the presets
   into an installed build, and there is a new smoke check. Both are added to `constraints.packages`
   with a comment (Deviation 2).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `presets`: Daily preset config | Done | `config/daily_presets.yaml` (politics, nhi); `domain/daily_preset.py` (the file's shape); `application/daily_preset_config.py` (load, then check every preset's arguments, needs, topic, providers and feed topics). 21 tests. |
| `digest-service`: DigestService with seen-set | Done | `application/digest_service.py` (searches, grouping, the writer-then-record order, `--auto-cut` candidates); `application/digest_seen_set.py` (the seen-set and its atomic file store); the optional `need` on `BatchCandidate`. 29 + 1 tests. |
| `daily-command`: daily command and Markdown/JSON renderers | Done | `commands/daily.py` (20 statements), `presenters/daily_presenter.py`, `container.py` (`daily_presets`, `daily_digesting`, `DailyDigesting`), registration. Small no-change refactors in the search presenter, batch report presenter and `search_auto_cut.py`. 23 CLI tests, a smoke check, the bundling. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `daily politics --date 2026-09-17` on fixtures writes digests/politics-2026-09-17.md grouping new results by argument/need with title, publisher, date, explanation and URL | PASS | `test_daily_politics_writes_the_dated_digest_grouped_by_argument_and_need`: exit 0. The whole file equals `SEPTEMBER_17_MARKDOWN`, written by hand from `courier_2026-09-17.xml`. That is two groups in preset order, each result's title, publisher, date and canonical URL, the review note, and the footer `rss: ok, 3 results from 10 queries`. The week-old item is absent, and so is the snippet sentinel. The only part not hand-written is each "Why" line, the ranker's explanation. `test_each_why_is_the_rankings_explanation_…` checks those lines equal the JSON's `explanation`, in order. |
| ac2: running the same preset for the next date omits results already listed on the previous day | PASS | CLI: `test_the_next_date_omits_results_the_previous_day_listed`. It runs `--date 2026-09-18 --window 2d`, so the 17th's three items are inside the window again. The file equals `SEPTEMBER_18_MARKDOWN`: the two new items, and `3 left out as listed in an earlier digest`. The 17th's file is byte-for-byte unchanged. Core: `test_the_next_date_omits_what_the_previous_day_listed` (the provider ignores the window, so only the seen-set keeps the items out), `test_a_result_seen_under_its_doi_is_omitted_at_another_url`, `test_a_source_merged_from_two_urls_is_seen_at_either`. |
| ac3 (amended by your ruling 1): every preset in the file (politics, nhi) validates on load, an invented third preset loads with no code change, and an unknown preset exits 2 listing the presets | PASS | `test_the_committed_presets_validate_against_the_committed_taxonomy_and_feed_lists`. The invented preset: `test_an_invented_third_preset_loads_with_no_code_change` (core), and `test_an_invented_preset_in_the_file_runs_with_no_code_change` (CLI, end to end: a `senate-watch` preset added to a copy of the file writes its digest). Unknown preset: `test_an_unknown_preset_exits_2_listing_the_presets_and_searches_nothing` (`no daily preset named 'data-centers'; the presets are politics, nhi`, no request sent), and the same in the smoke check. Refusals: 10 kinds of wrong reference and 7 wrong shapes, each naming the preset or file. |
| ac4: `--format json` emits the digest as JSON, and the provider status footer reports partial results | PASS | `test_format_json_writes_the_digest_as_json_and_prints_it`. The `.json` file plus its `file` key equals the envelope's `data`. Groups, titles, publishers, dates and URLs are written by hand. Also checked: the window, feed topics, `providers` (exactly `rss ok 10 queries 3 results`), 10 `provider_calls` and the 4 searches in order. Partial: `test_a_feed_that_fails_makes_the_digest_partial_and_the_footer_says_so` (one feed answers 503: exit 6, `Providers: PARTIAL, results may be missing`, `rss: partial, 3 results from 10 queries: …The Example Ledger…` in the file and on stdout). `test_a_partial_digest_in_json_carries_the_same_statuses` (`SEARCH_PARTIAL`, 6, the same summaries and calls). |
| Node: Presets config exists (`config/daily_presets.yaml` contains `politics`) | PASS | `grep -c politics config/daily_presets.yaml` → 5 |
| Node: Digest service tests pass (`uv run pytest packages/debate_core/tests/application/test_digest_service.py`) | PASS | `29 passed in 3.16s` |
| Node: daily command tests pass offline (`uv run pytest packages/debate_cli/tests/test_daily_command.py`) | PASS | `23 passed in 5.04s` |
| Node: daily help renders (`uv run debate-research daily --help`) | PASS | exit 0 |

### The other cases you asked for

* **A failed run marks nothing seen.**
  * Core: `test_a_run_whose_writer_fails_marks_nothing_seen`. The writer raises, no seen-set file
    exists afterwards, and the next run lists all four results.
  * CLI: `test_a_run_that_cannot_write_its_digest_marks_nothing_seen`. A read-only `digests/` gives a
    nonzero exit, no file and no seen-set, and the next run lists all three.
  * `test_a_digest_no_provider_answered_is_not_written_and_marks_nothing`: exit 3 `SEARCH_FAILED`, no
    `digests/`, no seen-set.
* **Feeds from another preset's topics are never read.**
  * `test_a_politics_digest_reads_only_the_politics_feeds`: the requests are exactly the two politics
    feed URLs.
  * `test_an_nhi_digest_reads_only_the_health_insurance_feeds_and_names_its_unasked_providers`: the
    requests are exactly the health feed. The four providers the test profile does not enable are
    `not configured` in the footer, and the run exits 6.
* **A feed awaiting review runs, and the digest says so.** One of the test's politics feeds is
  `awaiting_coach_review`. Its items are listed, and the file says `Feed topic politics was read with
  1 feed still awaiting the coach's review: The Example Courier.` (in ac1's hand-written file, and
  `feed_topics` in the JSON).
* **`--auto-cut N` on the replay router.**
  * `test_auto_cut_hands_the_new_results_to_the_batch_each_groups_first_then_the_next`: report.json's
    entries are the news page VERIFIED, the paywalled page SKIPPED and the think-tank page VERIFIED,
    in that order. The bundle is `digests/politics-2026-09-17.docx` with two cards under the digest's
    heading, beside its manifest.
  * `test_each_auto_cut_card_is_cut_for_the_need_its_search_was_for`: the two `card.select` calls were
    asked for `Uniqueness for bill` and `Uniqueness for Senate`.
  * `test_auto_cut_with_no_new_results_is_short_and_writes_no_bundle`: exit 8.
* **The seen-set's place and shape.**
  * `test_the_seen_set_is_in_the_data_directory_by_canonical_url_and_never_beside_the_digests`: the
    only file outside the data directory is the digest.
  * The core test of the file's contents checks every key and date by hand.
* **The clock.** `test_with_no_date_the_digest_is_for_today_by_the_clock`. The container's clock is
  overridden in every CLI test, and every window is asserted.

### Red first

Each suite was run against a refuse-nothing skeleton before its implementation was trusted. The tests
were not changed between the red run and the green one.

* **Presets.** `check_daily_presets` returned what it was given, and `load_daily_presets` did not
  wrap errors. Result: **18 failed, 3 passed**. The three are the accept paths: the committed file,
  the invented preset, and the refusal tests' own base preset.
* **Digest service.** `build` returned an empty digest, `run` wrote it and recorded nothing,
  `DigestWindow.parse` always gave 1 day, `listed_before` was always False and the candidates were
  empty. Result: **23 failed, 5 passed**. The five pass vacuously on an empty digest: `1d`,
  no-sources-changes-nothing, same-date rerun, the empty digest's candidates, and rank order. The
  mutants below cover what they cannot.
* **The per-candidate need.** With `need = request.need` restored, the new batch test failed at its
  assertion (`['Politics DA…'] == ['Midterms DA…']`). Restored: `26 passed`.
* **CLI.** The command kept its signature and had an empty body. Result: **22 failed, 1 passed** (the
  help test).
* **Bundling.** Without the `stamp_build.py` change, 4 of the stamp tests failed: the bundled list,
  the bytes check, the refusal of a checkout without the file, and the refusal of a wheel without it.

### Mutants

There are 19 mutants, on the seen-set and the grouping, plus the `--auto-cut` candidate order. Each
was planted in the committed tree and run against `test_digest_service.py` and
`test_daily_command.py` (`-n 0`), then restored with `git checkout HEAD --`. The harness is
`mutants.py` in the session's scratchpad. No Hypothesis property is involved. Every catch failed at an
assertion, not at collection.

| Mutant | Caught by |
|---|---|
| DOIs never count as listed | the DOI-at-another-URL test |
| URLs never count as listed | 4: next date (core and CLI), merged URLs, auto-cut with nothing new |
| The same date counts as an earlier digest | 2: same-date rerun (core), the JSON rerun (CLI) |
| Only a later date counts | 5 |
| No DOI is recorded | 2: DOI at another URL, the seen-set file's contents |
| Only the merged source's URL is recorded, not its members' | the merged-URLs test, written after the first nine mutants showed this case had none |
| An unreadable seen-set file is read as empty | the unreadable-file test |
| **A date already recorded is overwritten** | **survives: equivalent.** Every result that reaches a digest has each key either unrecorded or recorded under the same date, otherwise it would have been left out, so `setdefault` and assignment write the same file. Kept as `setdefault`, which states the rule. |
| The seen-set saved before the digest is written | 2: the failing writer (core), the read-only directory (CLI) |
| A FAILED digest written and recorded | 2 |
| A source two searches find listed twice | the two-groups test |
| The seen-set never asked | 5 |
| Pairs in reverse order | 10 |
| Every group under the first pair's heading | 7 |
| Results in reverse rank order | the rank-order test |
| The window starts a day early | 5 |
| The searches sent without the window | 9 |
| `--auto-cut` candidates in digest order, not each group's first | 2: the core order test, the CLI report order |
| `--auto-cut` candidates with no need of their own | 2: the core candidates test, the CLI `card.select` needs |

### Before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | `272 of 738 test files (36.9%) chosen in 19.7 s from 31 changed files`. That is well over two minutes (t05's 443 files were too), so it is left to the pull request's `ci` under agreement 10. No operator hand-off. |
| always-run list: `hard_stop.py 115 … pytest tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py -m "not slow and not live"` | `379 passed in 22.12s` |
| the changed areas: `hard_stop.py 115 … pytest` over `test_daily_command.py`, `test_search_command.py`, `commands/test_doctor.py`, `test_installation.py`, core `test_daily_presets.py`, `test_digest_service.py`, `test_batch_cut_service.py`, `test_federated_search.py`, `test_federated_search_articles.py`, `test_export_service.py`, `tests/scripts/test_stamp_build.py`, `tests/smoke/test_daily_smoke.py`, `test_search_smoke.py`, `test_cli_smoke.py`, `test_cut_smoke.py` | `434 passed in 26.24s` |
| `hard_stop.py 115 … pytest packages/debate_core/tests/application` | **Stopped at its 115-second limit**, so there is no result. That directory is left to `ci` with the rest of the affected set. |
| `uv run --frozen ruff format --check .` / `ruff check .` | `2044 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_cli packages/debate_core` (+ the smoke, stamp script and its test) | `0 errors, 0 warnings, 0 informations` (30 s). A planted `x: int = "…"` in `debate_cli` reported `1 error`, so the run reads the package. |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `20 kept, 0 broken` / `74 … handlers within 25 statements` (`daily`: 20) |
| `uv run scripts/validate_specs.py` | `OK: 655 files, 41 epics, 592 tasks, 22 releases` |
| `check_command_blocks.py`, `check_links.py`, `docs_index.py --check-descriptions` | all OK |

The smoke checks ran against the source checkout's console script (`installed: false`). validate-dev
runs them against the stamped wheel, where the unknown-preset check also shows the presets file was
bundled.

## Files changed

* **`config/daily_presets.yaml`** (new): `politics` and `nhi`, with a header saying what each key
  does and that the coach adds the LD and PF presets.
* **`packages/debate_core/src/debate_core/`**
  * `domain/daily_preset.py` (new): `DailyPreset`, `DailyPair`, `DailyPresets`.
  * `application/daily_preset_config.py` (new): the loader and the reference checks.
  * `application/digest_service.py` (new): `DigestService`, `DigestWindow`, `Digest`,
    `digest_batch_candidates`, `digest_bundle_need`.
  * `application/digest_seen_set.py` (new): `DigestSeenSet`, `source_keys`, `FileDigestSeenStore`.
  * `application/batch_cut_service.py`: `BatchCandidate.need` (Deviation 3).
* **`packages/debate_cli/src/debate_cli/`**
  * `commands/daily.py` (new), `presenters/daily_presenter.py` (new), `command_registry.py`.
  * `container.py`: `daily_presets`, `daily_digesting`, `DailyDigesting`, `DAILY_SEEN_DIRECTORY`,
    `daily_digesting` in `SERVICE_NAMES`. The federated search build is split so `daily` reuses it
    over its own providers.
  * `presenters/search_presenter.py`, `presenters/batch_report_presenter.py`, `search_auto_cut.py`:
    shared helpers, no behaviour change (`status_footer_lines`, `provider_calls_json`,
    `display_date`, `entry_json`, `batch_report_table`, `cut_and_write`, `write_atomically`). They
    were committed alone (25d7304), and `test_search_command.py` passed whole: `87 passed`.
  * `README.md`: a `daily` section and the exit-code rows.
* **Tests**
  * `packages/debate_core/tests/application/test_daily_presets.py`, `test_digest_service.py` (new),
    and one test in `test_batch_cut_service.py`.
  * `packages/debate_cli/tests/test_daily_command.py` and `fixtures/daily/` (new, synthetic, with a
    README).
  * Pins moved: `test_app.py` (the services list gains `daily_digesting`), and
    `test_container_factories.py` (`feed_topics: tuple[str, ...]`).
* **`scripts/stamp_build.py`, `tests/scripts/test_stamp_build.py`**: the installed build carries
  `config/daily_presets.yaml`, and `check-wheels` requires it.
* **`tests/smoke/test_daily_smoke.py`** (new): help, and the unknown preset listing the bundled presets.
* **The spec**: ac3 and the presets node amended with your ruling as a comment, and
  `constraints.packages` widened with a comment. Goal Succeeded.

## Deviations from the spec

1. **ac3 and the presets node, by your ruling of 2026-11-09.** `data-centers` and `space` are not
   shipped. The coach adds the current LD and PF presets as config. Both texts are amended in the
   spec, with the old wording in a comment above them.
2. **Files outside the packages first listed**, added to `constraints.packages` with a comment for
   you to keep or undo:
   * `debate_core.domain`: the spec's own output path, `domain/daily_preset.py`, is there.
   * `scripts/stamp_build.py` and its test: without them, an installed `daily` stops with "no such
     file", as `search` would have before v1-e08-t09.
   * `tests/smoke/test_daily_smoke.py`: working agreement 5 asks for one.
3. **`BatchCandidate.need`, an optional field in `BatchCutService`.** Your ruling 5 says `--auto-cut`
   hands the new results to `BatchCutService` "exactly as `search --auto-cut` does". A digest's
   results come from searches for several needs, and a `BatchCutRequest` names one. The walk, the
   skipping, the concurrency, the stop rules and report.json's naming are unchanged. The only change
   is that a candidate may carry its own need, and the request's need is used when it does not.
   * The alternative was one batch per argument/need group. Each batch writes `report.json` into the
     same directory under the same name, so the groups of one run would overwrite each other's
     reports, and avoiding that means changing t18's naming. That was ruled out.
   * The bundle has one block heading, the digest's (`Politics daily digest: 2026-09-17`). Each card
     is still cut for its own need.
4. **`--digest-dir`**, an option the spec's command line does not list. The default, `digests` in the
   working directory, is ac1's path. The option lets a person keep digests somewhere other than where
   they run the command.

## Decisions and assumptions

* **The window** is `Nd`, from 1 to 31 days. It runs from the start of the first day to the end of
  `--date`, in UTC. It is each search's own `since`/`until`, so it overrules the templates' recency
  windows, the 30 days of politics DA uniqueness included. `--date` defaults to today by the
  container's clock.
* **What "listed before" means.** A key recorded under a different date counts as listed before. A
  key recorded under the same date was listed by that date's own digest, which the rerun replaces, so
  the rerun lists it again (Question 1). Running an earlier date after a later one leaves out what
  the later one listed.
* **The keys.** The keys are the merged source's canonical URL and every member record's URL,
  canonicalized as dedupe does it, plus every DOI, compared in lower case. A source is the same when
  any key matches.
* **Grouping.** Groups follow the preset's pair order. Within a group, results go query by query,
  each search's in rank order. A source that two searches find is listed once, in the first group,
  in preset order, that found it. Each search is stored, as `search` stores it.
* **The `--auto-cut` order.** Candidates go each group's first result, then each group's second, and
  so on, numbered from 1. That way N cards are cut from across the digest's needs, not all from its
  first group.
* **Exit codes.** A complete digest exits 0, whether it has new results or none: a quiet day is still
  a digest, and its file is written (Question 2). Partial is 6, with the digest written and its
  results counted as listed. Nothing answered is 3, and nothing asked is 1. In both of those cases no
  file is written and nothing is recorded. A broken presets file is a configuration error, exit 1,
  naming the preset.
* **What is shown.** The Markdown shows a result's canonical URL, without tracking parameters. The
  JSON carries `url` and `canonical_url`, and `--auto-cut` fetches `url`, as `search --auto-cut`
  does. Neither prints a snippet or an abstract: a sentinel in every fixture description proves it.
  Titles are Markdown-escaped.
* **A feed awaiting review** is noted per feed topic, naming the feeds' publishers. Review is recorded
  per feed in the files.
* **Preset references** use exact ids, not aliases: `ptx` is refused with "did you mean
  'politics-da'". A government provider is refused on a preset whose topic's feed list does not
  enable it, because the search would never ask it.
* **The presets' content is a first draft for the coach.**
  * Politics asks `bill` and `Senate` for politics DA and midterms DA uniqueness. Uniqueness only,
    your ruling 3.
  * NHI asks `health insurance` on `policy-2026-27-nhi` for spending, federalism and economy DA
    uniqueness, over OpenAlex, Crossref, the feeds, the Federal Register and GovInfo.

## Operator follow-ups

None required: no criterion needs a live run.

**Optional, after this merges and a dev pre-release containing it is installed: one real politics
digest** (under a minute). It reads the coach's politics feeds over the network. It writes only to a
scratch folder on your Desktop, used both as the data directory and for the digest, so the real dev
seen-set is untouched. It prints only counts.

Where: your Mac, any terminal
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else mkdir -p "$HOME/Desktop/daily-check" && cd "$HOME/Desktop/daily-check" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$HOME/Desktop/daily-check/data" debate-research --json daily politics --digest-dir "$HOME/Desktop/daily-check" > /tmp/daily-politics.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); r = e.get("error") or {}; d = e.get("data") or r.get("details") or {}; print("code", r.get("code"), "status", d.get("status"), "new", d.get("new_results")); print("groups", [(g["heading"], len(g["results"])) for g in d.get("groups") or []]); print("providers", [(p["provider"], p["outcome"], p["queries"], p["results"]) for p in d.get("providers") or []])' /tmp/daily-politics.json; fi
```
Success looks like `exit 0` (or `exit 6`, with a feed named in `providers`), `status COMPLETE`, and
`providers` listing `rss` with 10 queries. `new 0` is also an answer. It means today's feeds hold
nothing that matches every word of a template, and that is worth knowing before the coach tunes the
queries. Paste back the three lines only. The titles stay in the Desktop file.

## Follow-up work

* **v1-e08-t18 (report names per run) should cover `daily --auto-cut` too.** Its report.json goes in
  the digest directory under the fixed name. So each day's `--auto-cut` run replaces the previous
  day's report, and a `search --auto-cut` into the same folder does as well. Your ruling 5 left the
  naming to t18, so nothing changed here.
* **The feed provider keeps an item only when every word of a filled template is in it.** For
  example, `Senate vote count Senate`, `bill likely to pass Congress` or `health insurance federal
  spending debate Congress`. Real headlines may rarely carry all the words of the longer templates.
  The optional run above gives the first real count. If it is low, either the coach shortens the
  preset queries, or E08 files a task for digest-specific templates.
* **A preset whose providers an environment does not enable is partial every day.** An example is
  `nhi` on a machine without an api.data.gov key, where GovInfo is `not configured` and the run exits
  6. That is the search's own rule. A coach scripting `daily` should expect it.
* **The link-level politics queries** (a DA's bill against a plan's mechanism) are the separate E08
  task you said you would file (ruling 3).

### Questions for the PM

````text
PM questions from v1-e08-t07 (debate-research daily), session of 2026-11-09. Two, both small; the task is
built and Succeeded either way, and each answer changes one line.

1. Running the same date twice. The seen-set records each source's canonical URLs and DOIs with the date
   of the digest that first listed it. A source is left out when it was recorded under another date. One
   recorded under the date being built was listed by that date's own digest, so a second run of that date
   lists it again and writes the same digest, rather than an empty one over the first.
   Options:
   (A) Same date lists again (built): a rerun after a failed --auto-cut, or with a wider --window,
       reproduces the day's digest. ac2 passes; the forbidden "re-listing results already reported in a
       previous digest" holds because the same date's digest is the same digest, replaced.
   (B) Any recorded date leaves it out: a rerun of a date writes an empty digest over the first one.
       ac2 passes; the first file is lost.
   Recommendation: A. It is the reading of "previous digest" that keeps a rerun from destroying the day's
   file. Mutation shows the rule is load-bearing (making the same date count as earlier fails 2 tests).

2. Exit code for a complete digest with nothing new. search exits 7 (NO_RESULTS) when every provider
   answered and nothing matched. daily exits 0: the digest is written and says "0 new results". A quiet
   day is a normal digest, and a scheduled caller would otherwise treat every quiet day as a failure.
   Options: (A) 0, as built; (B) 7, as search.
   Recommendation: A.

FYI, proceeding as built unless you say otherwise:
- BatchCandidate gained an optional need (Deviation 3), so --auto-cut cuts each result for its own
  argument and need in one batch, with one report.json; search --auto-cut is unchanged (87 tests pass on
  the change alone).
- --digest-dir (default ./digests) is an option the spec's command line does not list.
- scripts/stamp_build.py bundles config/daily_presets.yaml, and tests/smoke/test_daily_smoke.py is new;
  both are added to constraints.packages with a comment.
- t18 should cover daily --auto-cut's report.json too.

Reply with 1A/1B and 2A/2B, and anything to undo from the FYI list.
````

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-09

**Notes:**

The PM read the presets file, the commit list and the shape of the change in the worktree. The business
logic is in `debate_core.application`:

- the preset check (`daily_preset_config`);
- `DigestService`;
- the seen-set and its atomic store.

`commands/daily.py` stays thin at 20 statements. The container builds the feed and Google News providers
from the preset's own feed topics, and search's helpers were shared in a commit of their own (`25d7304`),
after which `test_search_command.py` passed whole.

1. **ac1 to ac4 pass**, on synthetic fixtures, offline:
   - ac1, the digest file written by hand;
   - ac2, the next date with a 2-day window, the 17th's file unchanged;
   - ac3 as amended by ruling 1, the invented third preset loading end to end and the unknown preset
     exiting 2 with the list;
   - ac4, the JSON envelope and the partial footer.

   Every extra case the PM asked for has its own test: a DOI seen at another URL, a failed run marking
   nothing seen (three ways), feeds from another preset never read, and the review note. Red ran four
   times against refuse-nothing skeletons. Of 19 mutants, 18 are caught. The survivor, `setdefault`
   against assignment, is shown to be equivalent.
2. **The PM's answers to the session's questions.**
   - **1A.** A rerun of the same date lists that date's results again and replaces the file. That keeps
     the forbidden line: the same date's digest is the same digest, replaced, not a later one listing it
     again.
   - **2A.** A complete digest with nothing new exits 0 and writes its file. A quiet day is a normal
     digest.
3. **The deviations are accepted.**
   - 1, ruling 1.
   - 2, `debate_core.domain`, `stamp_build.py` and its test, and the smoke check, each kept in
     `constraints.packages`.
   - 3, the optional `BatchCandidate.need`. It is the right reading of ruling 5: one batch and one
     `report.json`, each card cut for its own need. It defaults to None, and `search --auto-cut` is
     unchanged (87 pass on the change alone).
   - 4, `--digest-dir`, whose default is ac1's path.
4. **The decisions are accepted.** They include:
   - the window overrules the templates' recency windows;
   - keys are every member URL canonicalized, plus DOIs in lower case;
   - each source is listed once, in the first group in preset order;
   - the round-robin `--auto-cut` order;
   - partial exits 6 and counts its results as listed;
   - no snippet or abstract is printed, proved by a sentinel.
5. **The presets are a first draft, and they are the coach's to change in config.** The PM notes one thing
   for the coach: the 2026 midterms were on 2026-11-03, so the `midterms-da` uniqueness pair may be dropped
   or retargeted. That is a config edit and needs no task.
6. **Follow-ups, which the PM files in the next batch:**
   - v1-e08-t18 is amended so `daily --auto-cut`'s `report.json` is named per run too;
   - E08, p3: digest queries against the feed provider's every-word rule, once the optional real politics
     digest gives the first count;
   - the link-level politics DA task (ruling 3).
7. **The operator follow-up** (one real politics digest into a Desktop scratch folder) is optional and runs
   after a dev build carrying this is installed. It is not an acceptance criterion.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`. This branch starts
   before v1-e07-t10 and v1-e07-t04, and v1-e07-t04 also changes `debate_cli/container.py`. So if it merges
   first, run `scripts/task sync` here before the PR, keep both changes, and re-run `test_daily_command.py`,
   `test_search_command.py` and `test_container_factories.py`.
