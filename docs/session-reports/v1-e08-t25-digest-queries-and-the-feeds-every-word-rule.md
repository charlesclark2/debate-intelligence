# Session report: v1-e08-t25-digest-queries-and-the-feeds-every-word-rule

| | |
|---|---|
| Task | `v1-e08-t25-digest-queries-and-the-feeds-every-word-rule` — A daily digest's queries find what the feeds carry, measured on a real digest first |
| Spec | [`plan_specs/v1/e08-research-workflows/t25-digest-queries-and-the-feeds-every-word-rule.yaml`](../../plan_specs/v1/e08-research-workflows/t25-digest-queries-and-the-feeds-every-word-rule.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t25-digest-queries-and-the-feeds-every-word-rule` |
| Session status | PARTIAL: the operator's counts are in (2026-11-12); stopped for the PM's ruling on the queries |

## Summary

This session did the two things the PM's brief of 2026-11-12 allowed before the stop.

* **The measurement.** [`scripts/count_digest_feed_matches.py`](../../scripts/count_digest_feed_matches.py)
  runs on the operator's installed dev build. It reads the politics preset's real feeds once, into an
  in-memory cache, and writes nothing. For the 24-hour and 72-hour windows it prints counts only, for
  each filled query by its template id and pair: what today's every-word rule keeps, what the query's
  own words alone keep, what the query's own words plus any one of the template's words keep, and what
  six proposed shorter digest templates keep. The operator ran it on 2026-11-12 (build
  1.1.0.dev413) and pasted the output straight into the session. Under today's rule every query kept
  0 items in both windows. The proposal is under [Proposal](#proposal-from-the-counts): new two-word
  digest templates, 4 items in 24 hours and 6 in 72. It waits for the PM's ruling, and there is no
  code for it before that.
* **The ruled date default (ac3).** With no `--date`, a digest now covers the 24 hours before the run,
  by the injected clock. It is dated by the run's date in the new setting `daily.time_zone`, which is
  America/Chicago in the dev and prod profiles. `--date` and `--window` keep their meaning. An unknown
  zone is refused when the settings load, naming `daily.time_zone`. 23 new tests were shown failing
  against a skeleton that refused nothing and kept the UTC rule, and they pass now.

The Goal stays **InProgress**: ac1 needs the operator's run and the PM's ruling, and ac2 is the ruled
change, which is not built. For the PM, look first at the changeover note under Decisions (2). It is
what a coach with digests already named by UTC date sees once.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `digest-queries-and-the-feeds-every-word` (Digest queries) | IN PROGRESS | The measurement script and the ruled date default (ac3) are done. The query proposal (ac1) waits for the operator's counts and the ruling, and the ruled change (ac2) comes after it. The node's test command passes today (below). It has to pass again once ac2 is built. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the operator's real digest counts are recorded, and the PM rules on the proposal before any code (operator) | NOT RUN (counts recorded; ruling pending) | The counts are recorded under [Measured counts](#measured-counts-2026-11-12), and the operator's whole output is in the appendix. The proposal is written; the PM's ruling is pending. Offline check of the script: `.venv/bin/python -I scripts/count_digest_feed_matches.py politics --offline`, run from `$HOME`. It printed every section, and I hand-checked its counts against the four made-up items. For example, in the 72-hour window `Senate midterms polling` keeps 0 under every-word, because the item says "polls", and 1 under own-plus-one. |
| ac2: the ruled change holds, by tests on fixtures shown failing first | NOT RUN | No ruling yet, and no code before one (the PM's brief). |
| ac3: a digest run with no `--date` covers the ruled hours, not the UTC date's, by tests on an injected clock shown failing first | PASS | **Red** (commits `5a9c1b5` and `1a77ae4`): the tests ran against a skeleton with the new API that still took the UTC date and whole UTC days, and an unvalidated `daily.time_zone`. `pytest -n 0 --tb=line` over `test_digest_service.py`, `test_daily_command.py`, `test_settings.py` and `test_settings_environments.py` gave **23 failed, 162 passed**. Every failure was on an assertion, for example `assert datetime.date(2026, 11, 12) == datetime.date(2026, 11, 11)` (23:00 Chicago), `assert ['politics-2026-09-18.json'] == ['politics-2026-09-17.json']` (Los Angeles), `'- Window: … (1 day, UTC)' == '- Window: …fore the run)'` (07:00 Chicago), and `DID NOT RAISE ConfigurationError` (each unknown zone). The 3-day CLI test first crashed with FileNotFoundError. I changed it to assert the file list first, and it then failed on `['politics-2026-09-18.md'] == ['politics-2026-09-17.md']`. **Green** (`1049ff1`): the same files, with the configuration-gaps presenter tests, gave **192 passed in 3.14 s**. **Mutants**: (a) the CLI ignores the setting and hard-codes Chicago: caught by `test_with_no_date_the_digest_is_dated_in_the_configured_zone[los angeles…]`; (b) a no-date window of 24 hours whatever `--window` says: caught by `test_a_wider_window_with_no_date…` (core) and `test_with_no_date_and_a_wider_window…` (CLI). The four cases asked for: 23:00 Chicago is 2026-11-11 with 05:00Z–05:00Z (`test_a_run_at_23_00_in_chicago…`, and in the CLI `test_with_no_date_a_run_at_23_00_in_chicago…`). 07:00 Chicago (`…07_00…`, both). Both changeover days: 1 November, when the clocks fall back, and 8 March, when they spring forward (`test_on_the_day_the_clocks_fall_back…`, `…spring_forward…`). A non-default zone: Los Angeles and Tokyo in core, Los Angeles in the CLI. |
| Node: "Digest queries tests pass" (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "digest or feed"`) | PASS (for what is built) | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q packages/debate_core/tests packages/debate_cli/tests -k "digest or feed" -m "not slow and not live"` → **507 passed in 68.17 s**, exit 0. To be run again after ac2. |

### Checks before the report

* `uv run scripts/affected_tests.py`: **748 of 748 test files (100.0%)**. The root conftest imports
  `debate_core.application.settings`, which changed. That is the whole selection, so per agreement 10
  I ran nothing more of it and it is left to the pull request's `ci`. Within the two minutes I ran:
  * the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`,
    `test_container_factories.py`);
  * the docs checks (`tests/docs`, `test_check_command_blocks.py`, `test_docs_index.py`);
  * every test of the changed modules (`test_digest_service.py`, `test_daily_presets.py`,
    `test_run_state_saves_held_digests.py`, `test_daily_command.py`, the configuration-gaps presenter
    tests, `tests/smoke/test_daily_smoke.py`);
  * every test that reads the whole settings or the committed profiles (all nine `test_settings*.py`,
    `test_config_command.py`, `test_version.py`, `test_routing_file_checked_at_startup.py`,
    `test_per_user_credentials_and_a_missing_working_folder.py`, `tests/smoke/test_cli_smoke.py`,
    `test_factory.py`, `tests/scripts/test_stamp_build.py`).

  All 30 paths were checked with `ls -d` first. Result: `pytest -q -n 6 -m "not slow and not live"`
  → **1240 passed in 34.01 s**.
* `packages/debate_core/tests/application` as a whole, the changed modules' directory, did not finish
  inside 115 seconds at a load of about 7 (`hard_stop` exit 124). It is in CI's whole selection.
* `uv run ruff format --check .` → `2075 files already formatted`. `uv run ruff check .` → `All checks
  passed!`
* `uv run pyright packages/debate_core packages/debate_cli tests/smoke tests/architecture` → `0 errors`.
  `uv run pyright scripts/count_digest_feed_matches.py` → `0 errors`.
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken`. `uv run scripts/check_thin_handlers.py` →
  `OK: 74 CLI command and API route handlers within 25 statements`.
* `uv run scripts/check_command_blocks.py` → OK (697 blocks). `uv run scripts/check_links.py` → OK.
* `uv run scripts/validate_specs.py` → `OK: 669 files, 41 epics, 606 tasks, 22 releases`.
* The new smoke check was shown failing: with `time_zone = "America/Denver"` planted in `dev.toml` it
  failed `assert 'America/Denver' == 'America/Chicago'`. I restored the file from HEAD afterwards.

## Measured counts (2026-11-12)

The operator ran `scripts/count_digest_feed_matches.py politics` on build 1.1.0.dev413 at
2026-11-12T23:21Z, and it exited 0. All four feeds were read and none failed. The output holds counts,
publisher names and template texts only, and no feed item's text. It is copied whole in the appendix.

**Items per feed** (each link once across the feeds; no feed had an undated item):

| Feed | Listed | In the 24 hours | In the 72 hours |
|---|---|---|---|
| NPR | 10 | 10 | 10 |
| PBS NewsHour | 20 | 13 | 20 |
| Politico | 30 | 4 | 14 |
| The Hill | 15 | 15 | 15 |
| All feeds | 75 | 42 | 59 |

**Distinct items kept, by rule** (24 hours / 72 hours):

| Group | Today's every-word rule | The query's own words | Own words + any one template word | Proposed two-word templates |
|---|---|---|---|---|
| Politics DA uniqueness | 0 / 0 | 11 / 14 | 10 / 12 | 3 / 3 |
| Midterms DA uniqueness | 0 / 0 | 11 / 14 | 2 / 4 | 2 / 4 |
| Whole digest | 0 / 0 | 11 / 14 | 10 / 13 | 4 / 6 |

What the rows show:

* **Every filled taxonomy query kept 0 under every-word**, in both windows. That is all 10 queries:
  `{query} vote count Senate`, `likely to pass Congress`, `will not pass`, `{topic} midterms polling`
  and `election forecast`, each for `bill` and for `Senate`.
* **Own words alone:** `bill` keeps 2 in each window, and `Senate` keeps 10 in 24 hours and 13 in 72.
  The politics group, the midterms group and the whole digest each count 11 (24 hours) and 14 (72
  hours). The groups therefore hold the same items. A source is listed once, in the first group that
  finds it, so under this rule the midterms group would be empty.
* **Own words plus one template word is inflated by function words.** The templates hold `to`, `will`
  and `not`. `Senate likely to pass Congress` keeps 7 in 24 hours, while `Senate Congress` keeps 1, so
  at least 6 of the 7 matched `likely`, `to` or `pass`. Which of the three was not measured.
* **The proposed templates that kept anything** (24 hours / 72 hours): `bill Congress` 1 / 1,
  `Senate Congress` 1 / 1, `Senate Republicans` 1 / 1, `Senate election` 2 / 4. These kept 0: `vote`,
  `midterms` and `polls` with either query, and `bill Republicans` and `bill election`. In 24 hours one item is kept by both groups' templates (3 + 2 = 5 against 4
  distinct).

## Proposal from the counts

**Recommended: new digest-specific templates, two words each** (`{query}` plus one strong word),
asked by `daily` in place of the taxonomy's uniqueness templates. The every-word rule and the
coach-reviewed templates stay as they are, and so does `search`.

* On 2026-11-12 the six candidates measured took the politics digest from **0 to 4 items in the 24
  hours and 6 in the 72 hours**.
* They keep the groups apart: politics DA 3 / 3 and midterms DA 2 / 4.
* Each item carries the query word and one word of the argument, so what the digest lists is on
  topic, not just any headline that names the Senate.
* The list is new configuration, which the coach can extend. The script counts any candidate against
  the real feeds in under a minute, and the four that kept nothing would be dropped or replaced.

**Not recommended:**

* **The looser feed match, with the query's own words required and the template's words ranked.**
  It finds the most, 11 in 24 hours and 14 in 72. But both pairs' searches require the same word, so
  the groups hold the same items: the digest stops being grouped by argument, and the midterms group
  would be empty.
* **The query's own words plus one template word,** 10 / 13. Its count is mostly function words (see
  above), so these numbers are not evidence for it.
* A variant that skips function words (an item needs the query word and one of the template's content
  words) was not measured. One more run of the script, under a minute, would count it if the PM
  wants it weighed.
* **Shorter preset queries** cannot help: `bill` and `Senate` are one word each already.

**One thing to keep in mind about the numbers:** the midterms were on 2026-11-03, nine days before
this run. Few `polling` or `forecast` items is what the calendar predicts, whichever rule is used.

## Files changed

* **`scripts/count_digest_feed_matches.py`** (new): the operator's per-query count.
* **`packages/debate_core/src/debate_core/application/digest_service.py`**: `DigestRequest` gains
  `run_at`, `zone`, `before_the_run()` and `bounds()`, `DigestWindow.span`, `Digest.zone` and
  `ONE_DAY`. The module docstring has a section on the window and the date.
* **`packages/debate_core/src/debate_core/application/settings.py`**: `DailySettings` with
  `time_zone`, validated against the IANA database at load, and `Settings.daily`.
* **`config/profiles/dev.toml`, `prod.toml`**: `[daily] time_zone = "America/Chicago"`.
* **`packages/debate_cli/src/debate_cli/commands/daily.py`**: builds the request from the clock and
  the zone when there is no `--date`. The help for `--date` and `--window`, and the docstring, say so.
* **`packages/debate_cli/src/debate_cli/presenters/daily_presenter.py`**: a no-date digest's
  `Window` line gives the hours in the zone.
* **Tests**: `test_digest_service.py` (12 tests), `test_daily_command.py` (6 tests and a settable
  clock), `test_settings.py` (3 tests over 10 cases), `test_settings_environments.py` (2 cases),
  `tests/smoke/test_daily_smoke.py` (1).
* **Docs**: `docs/guides/daily-digests.md` (new, for the coach) and the `daily` section of
  `packages/debate_cli/README.md`.

## Deviations from the spec

1. **The ac3 ruling is in the PM's brief of 2026-11-12, not yet in the spec.** The spec's description
   still says "propose the default … and stop for the ruling". I built the brief's rule as written.
   The spec wants the ruling added to its amendments.
2. **Two paths outside `constraints.packages`.**
   * `scripts/count_digest_feed_matches.py`: the brief allows "a small script under scripts/".
   * `tests/smoke/test_daily_smoke.py`: agreement 5 asks every user-facing change to update its smoke
     checks, and `daily --help` and `config show` changed.

## Decisions and assumptions

1. **The field's built-in default is America/Chicago as well, not UTC.** The profiles set it, as the
   brief says, and the built-in profiles and the test profile get the same value. So no environment
   dates the coach's digest by UTC, and the budget's month is already Chicago's. A non-default zone
   is tested through `DEBATE_DAILY__TIME_ZONE`.
2. **What changes for a coach with digests already written under UTC dates.** Existing files and the
   seen-set keep their format and stay readable; nothing migrates. One thing happens once. Suppose an
   evening run with the older build (after 18:00 CST, or 19:00 CDT) named its file for the next UTC
   date, D. Then the first run with this build on local date D has the same name, so it replaces that
   file. It also lists again whichever of that file's results are still inside its 24 hours, because
   the older build recorded them under D, and a digest lists again what its own date listed (v1-e08-t07,
   ruling 1). From the next date on, nothing is listed twice.
   `test_a_source_an_evening_run_recorded_under_the_utc_date_is_listed_once_more_on_that_local_date`
   pins this, and the guide tells the coach to rename that file first to keep it. I built nothing to
   detect such a file: the seen-set does not record how its dates were taken.
3. **The 24-hour window sits easily with "new since last".** I did not need to stop over it. The
   seen-set is keyed by the digest's date, which is now the local date. A morning and an evening run
   on one date are that date's digest twice, as two runs of one `--date` are, and the next date's run
   leaves both out. The tests `…morning_and_an_evening_run…` and `…next_evenings_run_leaves_out…` show
   both.
4. **"24 hours" means 24 hours of time.** On a changeover day the window reads as 23 or 25 hours on
   the wall clock. `--window Nd` with no `--date` is N × 24 hours.
5. **The JSON is unchanged in shape.** `window` keeps `days`, `since` and `until`, and for a no-date
   digest `since` and `until` are the exact instants. The Markdown `Window` line names the zone:
   `2026-09-17 07:00 to 2026-09-18 07:00 America/Chicago (the 24 hours before the run)`.
6. **The refusal never quotes the value**, as every settings refusal does. Names refused: an unknown
   city, `Central`, empty, and a relative or absolute path.
7. **What the measurement counts.**
   * Counts are before each search's `max_results` cut (20).
   * Each link counts once across the feeds, as the provider counts them.
   * An undated item is outside both windows, as the provider treats it.
   * The six proposed templates are counted in the same run, because their counts cost no extra
     fetch: `{query} vote`, `{query} Congress`, `{query} Republicans` for politics DA uniqueness, and
     `{query} midterms`, `{query} election`, `{query} polls` for midterms DA uniqueness. They go in no
     taxonomy, so no coach-reviewed template changes.
   * Shorter preset queries are not a separate option to count: the politics preset's queries are
     already one word each (`bill`, `Senate`), so every extra word comes from the templates.

## Operator follow-ups

**Done, 2026-11-12:** the operator ran the block below and pasted the output into the session. It
exited 0 and its counts are recorded above. The block stays here because a second run, with other
candidate templates or the function-word variant, uses the same command.

**The per-query counts for the politics digest** (under a minute). This is v1-e08-t25's ac1
measurement.

* **Before you run it.** It needs a dev pre-release installed with `scripts/install_channel.sh`,
  v1.1.0-dev.402 or later; it imports only code that build already has. Run it from your home folder,
  with the installed build's own Python, on the script in this worktree.
* **What it does.** It reads the four politics feeds, NPR, PBS NewsHour, Politico and The Hill (or
  whatever the build's bundled `config/feeds/politics.yaml` lists), once each, over the network.
* **What it writes: nothing.** No feed cache (the feeds go into an in-memory cache, so it sends no
  conditional headers), no seen-set, no SQLite file and no digest.
* **What it prints: counts only.** Feed publisher names and the committed template texts appear, but
  never a title, summary, link or other text of a feed item.

Where: your Mac, any terminal
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && env DEBATE_ENV=dev "$(uv tool dir)/debate-cli/bin/python" -I /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e08-t25-digest-queries-and-the-feeds-every-word-rule/scripts/count_digest_feed_matches.py politics; echo "exit $?"; fi
```

**What success looks like:**

* the first line reads `build 1.1.0-dev.<N> preset politics feeds 4 read 4 failed 0 run <time>Z`,
  without `OFFLINE`;
* each feed's row has `listed` above zero;
* there are two sections, `window 24h` and `window 72h`, each with 22 query rows (10 `taxonomy`, 12
  `proposed`) and six `distinct items kept` rows;
* the last line is `exit 0`.

**How to read it.**

* A zero in a query row is an answer, not a failure.
* A feed row reading `failed: HTTP 403` (or similar) is worth knowing, and the counts still stand for
  the other feeds.
* A line starting `STOP:` means nothing was measured.

**What to paste back:** the whole output, to the PM. It is all counts.

## Follow-up work

* **The ruled query change** (this task's ac2), after the PM's ruling on the proposal above. If digest
  templates are ruled: new templates in a place only `daily` reads, with tests on synthetic fixtures
  shown failing first.
* **`daily` by a scheduler.** If the coach ever schedules `daily`, the scheduled run's time decides
  the hours covered. A run at a fixed local hour now gives back-to-back 24-hour windows with no gap.
  Under the UTC date it did not. Nothing to do now.

### Questions for the PM

````text
PM questions from v1-e08-t25 (digest queries and the every-word rule), session of 2026-11-12. The
operator's per-query counts are in (build 1.1.0.dev413, 2026-11-12T23:21Z, all four politics feeds
read, exit 0); the operator pasted them into the session directly. ac3 (the date default) is built
as you ruled. The session is stopped for ruling 1.

The counts, distinct items kept by the whole politics digest, 24 hours / 72 hours (42 / 59 items in
the windows):
- today's every-word rule: 0 / 0. All 10 filled queries keep 0 in both windows.
- the query's own words alone (bill, Senate): 11 / 14. The politics group, the midterms group and the
  whole digest all count the same 11 / 14, so they are the same items, and the midterms group would
  be empty (a source is listed once, in its first group).
- own words plus any one template word: 10 / 13 (politics 10 / 12, midterms 2 / 4). Inflated by the
  templates' function words: `Senate likely to pass Congress` keeps 7, yet `Senate Congress` keeps 1.
- six proposed two-word digest templates: 4 / 6 (politics 3 / 3, midterms 2 / 4). Hits:
  `bill Congress` 1 / 1, `Senate Congress` 1 / 1, `Senate Republicans` 1 / 1, `Senate election`
  2 / 4. `vote`, `midterms`, `polls`, `bill Republicans` and `bill election` kept 0.

1. Which change for the digest's queries?
   Options:
   (A) New digest-specific templates, two words each ({query} plus one strong word), asked by daily
       in place of the taxonomy's uniqueness templates; the every-word rule, search and every
       coach-reviewed template unchanged. Measured: 0 -> 4 items a day, 6 over three days, groups kept
       apart. The coach extends the list; the script counts a candidate in under a minute.
   (B) A looser feed match for digests: the query's own words required, the template's words
       ranked. Measured: 11 / 14, but the two groups become one list.
   (C) Own words plus one of the template's content words (function words such as to, will, not
       skipped). Keeps the groups apart and the reviewed templates; not measured. One more operator
       run, under a minute, would count it before you rule.
   Shorter preset queries are not an option: bill and Senate are one word each already.
   Recommendation: A, with the four candidates that kept something (bill Congress, Senate Congress,
   Senate Republicans, Senate election) as the first list. If you would rather weigh C first, I add
   its column to the script and hand the operator the same block again.
   Context for the midterms numbers: the midterms were 2026-11-03, so few polling or forecast items
   is expected this week under any rule.

2. The changeover for digests already named by UTC date. Suppose an evening run with the older build
   named its file for the next date, D. The first run on local date D with this build replaces that
   file, and lists again whichever of its results are still in the 24 hours. This happens once; the
   guide tells the coach to rename the file first to keep it.
   Options: (A) as built and documented; (B) refuse to replace a digest file this build did not
   write. That needs a marker in the file, because the seen-set does not record which rule dated it.
   Recommendation: A. It is one file, once, and the coach is told.

FYI, proceeding as built unless you say otherwise:
- daily.time_zone's built-in default is America/Chicago too, not UTC, so the test profile and a
  build with no profile also date by the coach's zone.
- The ruling isn't in the spec yet (Deviations 1). scripts/ and tests/smoke/ are outside
  constraints.packages: the brief allows the script, and agreement 5 asks for the smoke check
  (Deviations 2).
- The affected set is the whole selection (settings.py feeds the root conftest), so it is CI's. I
  ran the always-run list and every test of the changed modules and of the settings: 1240 passed.
````

## Appendix: the operator's output, 2026-11-12

As pasted, without the shell prompt line. Counts, publisher names and committed template texts only.

```text
build 1.1.0.dev413 preset politics feeds 4 read 4 failed 0 run 2026-11-12T23:21Z

feed | listed | undated | in_24h | in_72h
NPR | 10 | 0 | 10 | 10
PBS NewsHour | 20 | 0 | 13 | 20
Politico | 30 | 0 | 4 | 14
The Hill | 15 | 0 | 15 | 15
all feeds | 75 | 0 | 42 | 59

window 24h: 42 items
kind | pair | preset_query | template_id | template | every_word | own_words | own_plus_one
taxonomy | politics-da/uniqueness | bill | politics-da/uniqueness/1 | {query} vote count Senate | 0 | 2 | 1
taxonomy | politics-da/uniqueness | bill | politics-da/uniqueness/2 | {query} likely to pass Congress | 0 | 2 | 1
taxonomy | politics-da/uniqueness | bill | politics-da/uniqueness/3 | {query} will not pass | 0 | 2 | 0
proposed | politics-da/uniqueness | bill | digest/politics-da/uniqueness/1 | {query} vote | 0 | - | -
proposed | politics-da/uniqueness | bill | digest/politics-da/uniqueness/2 | {query} Congress | 1 | - | -
proposed | politics-da/uniqueness | bill | digest/politics-da/uniqueness/3 | {query} Republicans | 0 | - | -
taxonomy | politics-da/uniqueness | Senate | politics-da/uniqueness/1 | {query} vote count Senate | 0 | 10 | 0
taxonomy | politics-da/uniqueness | Senate | politics-da/uniqueness/2 | {query} likely to pass Congress | 0 | 10 | 7
taxonomy | politics-da/uniqueness | Senate | politics-da/uniqueness/3 | {query} will not pass | 0 | 10 | 1
proposed | politics-da/uniqueness | Senate | digest/politics-da/uniqueness/1 | {query} vote | 0 | - | -
proposed | politics-da/uniqueness | Senate | digest/politics-da/uniqueness/2 | {query} Congress | 1 | - | -
proposed | politics-da/uniqueness | Senate | digest/politics-da/uniqueness/3 | {query} Republicans | 1 | - | -
taxonomy | midterms-da/uniqueness | bill | midterms-da/uniqueness/1 | {topic} midterms polling | 0 | 2 | 0
taxonomy | midterms-da/uniqueness | bill | midterms-da/uniqueness/2 | {query} election forecast | 0 | 2 | 0
proposed | midterms-da/uniqueness | bill | digest/midterms-da/uniqueness/1 | {query} midterms | 0 | - | -
proposed | midterms-da/uniqueness | bill | digest/midterms-da/uniqueness/2 | {query} election | 0 | - | -
proposed | midterms-da/uniqueness | bill | digest/midterms-da/uniqueness/3 | {query} polls | 0 | - | -
taxonomy | midterms-da/uniqueness | Senate | midterms-da/uniqueness/1 | {topic} midterms polling | 0 | 10 | 0
taxonomy | midterms-da/uniqueness | Senate | midterms-da/uniqueness/2 | {query} election forecast | 0 | 10 | 2
proposed | midterms-da/uniqueness | Senate | digest/midterms-da/uniqueness/1 | {query} midterms | 0 | - | -
proposed | midterms-da/uniqueness | Senate | digest/midterms-da/uniqueness/2 | {query} election | 2 | - | -
proposed | midterms-da/uniqueness | Senate | digest/midterms-da/uniqueness/3 | {query} polls | 0 | - | -
distinct items kept, any query of the group:
taxonomy | politics-da/uniqueness | 0 | 11 | 10
proposed | politics-da/uniqueness | 3 | - | -
taxonomy | midterms-da/uniqueness | 0 | 11 | 2
proposed | midterms-da/uniqueness | 2 | - | -
taxonomy | whole digest | 0 | 11 | 10
proposed | whole digest | 4 | - | -

window 72h: 59 items
kind | pair | preset_query | template_id | template | every_word | own_words | own_plus_one
taxonomy | politics-da/uniqueness | bill | politics-da/uniqueness/1 | {query} vote count Senate | 0 | 2 | 1
taxonomy | politics-da/uniqueness | bill | politics-da/uniqueness/2 | {query} likely to pass Congress | 0 | 2 | 1
taxonomy | politics-da/uniqueness | bill | politics-da/uniqueness/3 | {query} will not pass | 0 | 2 | 0
proposed | politics-da/uniqueness | bill | digest/politics-da/uniqueness/1 | {query} vote | 0 | - | -
proposed | politics-da/uniqueness | bill | digest/politics-da/uniqueness/2 | {query} Congress | 1 | - | -
proposed | politics-da/uniqueness | bill | digest/politics-da/uniqueness/3 | {query} Republicans | 0 | - | -
taxonomy | politics-da/uniqueness | Senate | politics-da/uniqueness/1 | {query} vote count Senate | 0 | 13 | 0
taxonomy | politics-da/uniqueness | Senate | politics-da/uniqueness/2 | {query} likely to pass Congress | 0 | 13 | 9
taxonomy | politics-da/uniqueness | Senate | politics-da/uniqueness/3 | {query} will not pass | 0 | 13 | 1
proposed | politics-da/uniqueness | Senate | digest/politics-da/uniqueness/1 | {query} vote | 0 | - | -
proposed | politics-da/uniqueness | Senate | digest/politics-da/uniqueness/2 | {query} Congress | 1 | - | -
proposed | politics-da/uniqueness | Senate | digest/politics-da/uniqueness/3 | {query} Republicans | 1 | - | -
taxonomy | midterms-da/uniqueness | bill | midterms-da/uniqueness/1 | {topic} midterms polling | 0 | 2 | 0
taxonomy | midterms-da/uniqueness | bill | midterms-da/uniqueness/2 | {query} election forecast | 0 | 2 | 0
proposed | midterms-da/uniqueness | bill | digest/midterms-da/uniqueness/1 | {query} midterms | 0 | - | -
proposed | midterms-da/uniqueness | bill | digest/midterms-da/uniqueness/2 | {query} election | 0 | - | -
proposed | midterms-da/uniqueness | bill | digest/midterms-da/uniqueness/3 | {query} polls | 0 | - | -
taxonomy | midterms-da/uniqueness | Senate | midterms-da/uniqueness/1 | {topic} midterms polling | 0 | 13 | 0
taxonomy | midterms-da/uniqueness | Senate | midterms-da/uniqueness/2 | {query} election forecast | 0 | 13 | 4
proposed | midterms-da/uniqueness | Senate | digest/midterms-da/uniqueness/1 | {query} midterms | 0 | - | -
proposed | midterms-da/uniqueness | Senate | digest/midterms-da/uniqueness/2 | {query} election | 4 | - | -
proposed | midterms-da/uniqueness | Senate | digest/midterms-da/uniqueness/3 | {query} polls | 0 | - | -
distinct items kept, any query of the group:
taxonomy | politics-da/uniqueness | 0 | 14 | 12
proposed | politics-da/uniqueness | 3 | - | -
taxonomy | midterms-da/uniqueness | 0 | 14 | 4
proposed | midterms-da/uniqueness | 4 | - | -
taxonomy | whole digest | 0 | 14 | 13
proposed | whole digest | 6 | - | -
exit 0
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
