# Session report: v1-e08-t25-digest-queries-and-the-feeds-every-word-rule

| | |
|---|---|
| Task | `v1-e08-t25-digest-queries-and-the-feeds-every-word-rule` — A daily digest's queries find what the feeds carry, measured on a real digest first |
| Spec | [`plan_specs/v1/e08-research-workflows/t25-digest-queries-and-the-feeds-every-word-rule.yaml`](../../plan_specs/v1/e08-research-workflows/t25-digest-queries-and-the-feeds-every-word-rule.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t25-digest-queries-and-the-feeds-every-word-rule` |
| Session status | COMPLETE |

## Summary

The task is done in three steps.

* **Measured first (ac1).** I wrote
  [`scripts/count_digest_feed_matches.py`](../../scripts/count_digest_feed_matches.py), which prints
  counts only. The operator ran it on 2026-11-12 (build 1.1.0.dev413, 23:21Z) on the politics feeds.
  Under the every-word rule, every one of the ten filled taxonomy queries kept 0 items, in the 24 hours
  (42 items) and in the 72 hours (59). The counts are recorded below, all four strategies and both
  windows. The PM ruled the same day for new two-word digest templates.
* **The ruled change (ac2).** `daily` now asks the digest templates in
  [`config/daily_templates.yaml`](../../config/daily_templates.yaml), and never the taxonomy's. The
  file holds the ruled four: `bill Congress`, `Senate Congress`, `Senate Republicans`,
  `Senate election`. These are unchanged: `search`, the feed provider's every-word rule, and all 456
  coach-reviewed templates (now pinned by test). By the PM's ruling C (2026-11-12), a pair with no
  digest templates asks the taxonomy's templates exactly as on dev, and the digest names that group
  under its heading. Today that is each of the `nhi` preset's pairs, pinned to the eight queries
  dev's own code asks. So the change reaches only the politics preset. The tests were shown failing
  first against a skeleton (34 red) and then against the query-alone build (8 red). Seven planted
  breaks were caught.
* **The date default (ac3), as ruled before the stop.** With no `--date`, a digest covers the 24 hours
  before the run and is dated in `daily.time_zone`, which is America/Chicago.

Every criterion passes, so the Goal is **Succeeded**. One operator follow-up waits for the merge: one
real `daily politics` on a dev build that carries this change.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `digest-queries-and-the-feeds-every-word` (Digest queries) | DONE | In order: the measurement script; the date default (ac3); the operator's counts and the proposal; the PM's ruling of 2026-11-12; the digest templates (ac2); the PM's ruling C on the fallback. The node's test command passes after both (below). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the operator's real digest counts are recorded, and the PM rules on the proposal before any code (operator) | PASS | The operator ran the Operator follow-ups block on 2026-11-12T23:21Z (build 1.1.0.dev413, 4 of 4 feeds read, exit 0). The counts for all four strategies and both windows are under [Measured counts](#measured-counts-2026-11-12), and the whole output is in the appendix. The proposal is [Proposal from the counts](#proposal-from-the-counts). The PM ruled for option A on 2026-11-12, and the PM records the ruling. No query code came before the ruling: the first ac2 commit is `eada0db`, after it. Before the run I checked the script offline from `$HOME` against four made-up items and worked the counts out by hand. |
| ac2: the ruled change holds, by tests on fixtures shown failing first | PASS | **First ruling, red** (`eada0db`, a skeleton whose stage still asked the taxonomy's templates and whose loader and checks refused nothing): `pytest -n 0 --tb=line` over `test_digest_service.py`, `test_digest_templates.py`, `test_feeds.py`, `test_daily_command.py` and `tests/scripts/test_stamp_build.py` gave **34 failed, 233 passed**, every failure an assertion or a "did not raise". For example, `assert ['bill vote c…ot pass', …] == ['bill Congre…ate election']`, `DID NOT RAISE DigestTemplateError`, and `'… 10 queries\n' == '… 4 queries\n'`. **Green** (`864aa74`): **267 passed**. **Ruling C (the fallback), red against the query-alone build** (`472642f`; the rename `8ef037a` and the `asks_taxonomy` alias changed no behaviour): over `test_digest_service.py`, `test_digest_templates.py` and `test_daily_command.py`, **8 failed, 105 passed**, every one an assertion. Examples: `assert ['health insu…th insurance'] == ['health insu…thy now', …]` (nhi asks dev's eight queries); `assert [('Spending D…s', True, [])] == …` (nhi's three groups kept apart); `assert ['bill', 'bill'] == ['bill vote c…ion forecast']`. **Green** (`08c1c5c`): **270 passed** over the five files. **The pins come from dev, not from this branch.** The eight nhi queries were recorded by running dev's own code at 5c71e42 in a scratch worktree, which was then removed: `health insurance federal spending debate Congress`, `Congress spending restraint health insurance`, `states lead health insurance policy`, `health insurance state innovation federalism`, `health insurance clean federal and state separation now`, `health insurance federalism healthy now`, `health insurance economic growth forecast`, `health insurance recession risk`. The three groups and GovInfo's "8 of 8 queries" are dev's own hand-written expectations, restored. The core list is dev's `test_every_query_is_the_pairs_expansion_asked_inside_the_window`. **Planted breaks, each restored from HEAD:** (1) `search` given the digest stage → `test_search_still_asks_the_taxonomys_uniqueness_templates` failed; (2) one reviewed template edited → the two pin tests failed; (3) the every-word rule loosened to any word → 3 cases failed; (4) a no-template group falling back silently → 5 failed (under the first ruling); (5) **the named line dropped** → `test_an_nhi_pair_with_no_digest_templates_asks_the_taxonomys_templates_as_on_dev_and_says_so` failed; (6) **a fallback to the query alone** → 8 failed, the same 8 as the red run; (7) a pair with digest templates also asking the taxonomy's → 20 failed. **Tests for each point:** digest templates only for politics, `test_daily_asks_the_digest_templates_and_none_of_the_taxonomys_uniqueness_templates` and `test_a_pair_with_digest_templates_never_also_asks_the_taxonomys`; `search` unchanged, `test_search_still_asks…`; every-word unchanged, `test_a_digest_templates_two_words_are_both_required…`; reviewed templates pinned, `test_every_coach_reviewed_template_is_byte_for_byte_as_it_was` (35 arguments, 456 templates, sha256); groups apart, `test_the_two_groups_list_what_their_own_templates_found_and_nothing_twice` and the nhi groups; the fallback asks the taxonomy's and is named, `test_an_nhi_pair_with_no_digest_templates_asks_the_taxonomys_templates_as_on_dev_and_says_so`, `test_a_pair_with_no_digest_templates_asks_the_taxonomys_templates_and_says_so`, `test_with_no_digest_templates_at_all_every_pair_asks_as_it_did_before` and `test_the_nhi_presets_pairs_have_none_and_ask_the_taxonomys_templates`, with `test_a_politics_digest_carries_no_such_line` for the converse. |
| ac3: a digest run with no `--date` covers the ruled hours, not the UTC date's, by tests on an injected clock shown failing first | PASS | **Red** (commits `5a9c1b5` and `1a77ae4`): the tests ran against a skeleton with the new API that still took the UTC date and whole UTC days, and an unvalidated `daily.time_zone`. `pytest -n 0 --tb=line` over `test_digest_service.py`, `test_daily_command.py`, `test_settings.py` and `test_settings_environments.py` gave **23 failed, 162 passed**. Every failure was on an assertion, for example `assert datetime.date(2026, 11, 12) == datetime.date(2026, 11, 11)` (23:00 Chicago), `assert ['politics-2026-09-18.json'] == ['politics-2026-09-17.json']` (Los Angeles), `'- Window: … (1 day, UTC)' == '- Window: …fore the run)'` (07:00 Chicago), and `DID NOT RAISE ConfigurationError` (each unknown zone). The 3-day CLI test first crashed with FileNotFoundError; I changed it to assert the file list first, and it then failed on `['politics-2026-09-18.md'] == ['politics-2026-09-17.md']`. **Green** (`1049ff1`): **192 passed**. **Mutants**: (a) the CLI hard-codes Chicago instead of reading the setting: caught by the Los Angeles case; (b) a 24-hour window whatever `--window` says: caught in core and in the CLI. The four cases asked for: 23:00 Chicago (2026-11-11, 05:00Z to 05:00Z), 07:00 Chicago, both changeover days (1 November, when the clocks fall back, and 8 March, when they spring forward), and a non-default zone (Los Angeles and Tokyo). With ac2 the CLI cases' expected items changed with the fixtures (B, I, C), and they still pass. |
| Node: "Digest queries tests pass" (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "digest or feed"`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q packages/debate_core/tests packages/debate_cli/tests -k "digest or feed" -m "not slow and not live"` after ruling C → **548 passed in 34.25 s**, exit 0. |

### Checks before the report

* `uv run scripts/affected_tests.py`: **749 of 749 test files (100.0%)**, from 28 changed files. The
  root conftest imports `debate_core.application.settings`, which changed. That is the whole
  selection, so per agreement 10 it is left to the pull request's `ci`. Within the two minutes I ran
  35 paths, each checked with `ls -d` first:
  * the always-run list (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`,
    `test_container_factories.py`);
  * the docs checks;
  * every test of the changed modules (`test_digest_service.py`, `test_digest_templates.py`,
    `test_daily_presets.py`, `test_run_state_saves_held_digests.py`, `test_feeds.py`,
    `test_daily_command.py`, the configuration-gaps presenter tests, `tests/smoke/test_daily_smoke.py`);
  * `search`'s command and presenter tests, because the container's federated-search builder changed;
  * `test_installation.py`;
  * every test that reads the whole settings or the committed profiles (all nine `test_settings*.py`,
    `test_config_command.py`, `test_version.py`, `test_routing_file_checked_at_startup.py`,
    `test_per_user_credentials_and_a_missing_working_folder.py`, `tests/smoke/test_cli_smoke.py`,
    `test_factory.py`);
  * `tests/scripts/test_stamp_build.py`.

  Result, after ruling C: `pytest -q -n 6 -m "not slow and not live"` → **1499 passed in 37.50 s**.
* `packages/debate_core/tests/application` as a whole did not finish inside 115 seconds earlier in
  the session (`hard_stop` exit 124), so it is in CI's whole selection.
* `uv run ruff format --check .` → `2077 files already formatted`. `uv run ruff check .` → `All checks
  passed!`
* `uv run pyright packages/debate_core packages/debate_cli tests/smoke tests/architecture
  scripts/count_digest_feed_matches.py scripts/stamp_build.py` → `0 errors`.
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken`. `uv run scripts/check_thin_handlers.py` →
  `OK: 74 CLI command and API route handlers within 25 statements`.
* `uv run scripts/check_command_blocks.py --base origin/dev` → OK (703 blocks, this report included).
  `uv run scripts/check_links.py` → OK.
* `uv run scripts/validate_specs.py` → `OK: 669 files, 41 epics, 606 tasks, 22 releases`.
* The ac3 smoke check was shown failing earlier with `time_zone = "America/Denver"` planted in
  `dev.toml`.

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

**Ruled by the PM, 2026-11-12: option A**, digest-specific templates, with the four that kept
something as the first list. Not B, because its extra items are unseen (counts only) and it merges
the groups. Not C, because it is unmeasured, and the function-word rule is more to get right than A's
list. The rest of this section is the proposal as it was written.

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

* **The digest templates (ac2).**
  * `config/daily_templates.yaml` (new): the ruled four, each with its measured counts as a comment.
  * `packages/debate_core/src/debate_core/application/digest_templates.py` (new): the file's model,
    the loader, the checks against the taxonomy and the presets, `queries_for` and `asks_taxonomy`, and
    `DigestExpansionStage`, which hands a pair with no group to the taxonomy's `QueryExpansionStage`.
  * `digest_service.py`: `DigestService` takes the templates, skips a search no template is for, gives
    each group `asked_taxonomy_templates`, and gains `planned_searches()`.
  * `container.py`: `daily_templates()`, and daily's federated search built with the digest stage.
    `search` keeps the taxonomy's stage.
  * `daily.py`: the progress line counts the planned searches; the docstring.
  * `daily_presenter.py`: the note under a group that asked the taxonomy's templates, and
    `asked_taxonomy_templates` in the JSON group.
  * `config/daily_presets.yaml`: its header comment.
* **The date default (ac3).**
  * `digest_service.py`: `DigestRequest.before_the_run()` and `bounds()`, `DigestWindow.span`, and
    `Digest.zone`.
  * `settings.py`: `DailySettings.time_zone`.
  * `config/profiles/dev.toml`, `prod.toml`: `[daily] time_zone`.
  * `daily.py`: the help and the request.
  * `daily_presenter.py`: the `Window` line.
* **Bundling.** `scripts/stamp_build.py` and `tests/scripts/test_stamp_build.py`: a published build
  carries `config/daily_templates.yaml`, and `check-wheels` requires it.
* **The measurement.** `scripts/count_digest_feed_matches.py` (new). It now counts the committed
  digest templates and any `--candidate`, counts only.
* **Tests.**
  * `test_digest_templates.py` (new, 24 cases).
  * `test_digest_service.py`: the world asks test-written digest templates; 5 new ac2 tests and 12
    ac3 tests.
  * `test_feeds.py`: 1 test over 6 cases.
  * `test_daily_command.py`: 6 new ac2 tests (8 cases) and 6 ac3 tests, with the expectations
    rewritten by hand.
  * `test_settings.py`, `test_settings_environments.py`, and `tests/smoke/test_daily_smoke.py` (ac3).
  * The fixtures `courier_2026-09-17.xml` (new item I), `courier_2026-09-18.xml` (G and H retitled, I
    listed again) and `courier_auto_cut.xml` (the second item retitled), with their README.
* **Docs.** `docs/guides/daily-digests.md` (new): the window and the zone, the digest templates, the
  fallback, and "Counting a template before adding it" with its block. Also the `daily` section of
  `packages/debate_cli/README.md`.

## Deviations from the spec

1. **The rulings are in the PM's brief and rulings of 2026-11-12, not yet in the spec.** The PM's
   next batch amends the spec.
2. **Paths outside `constraints.packages`**, which the PM's next batch adds:
   * `scripts/count_digest_feed_matches.py` (the brief allows it);
   * `tests/smoke/test_daily_smoke.py` (agreement 5);
   * `scripts/stamp_build.py` and `tests/scripts/test_stamp_build.py`. A published build reads only
     the config files `stamp_build.py` bundles, so without them an installed `daily` could not find
     its templates.

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
8. **The four are exactly four.** A template's `queries` lists the preset queries it is asked for.
   So `{query} Republicans` and `{query} election` are asked for `Senate` alone, because `bill
   Republicans` and `bill election` kept nothing. A pair whose group has no template for a query runs
   no search for it: midterms DA x `bill`. The politics digest asks 4 queries in 3 searches. It used
   to ask 10 in 4.
9. **The fallback is the PM's ruling C (2026-11-12): the taxonomy's templates, named.** A pair with no
   digest templates asks the taxonomy's uniqueness templates exactly as before this task. The digest
   stage hands that search to the taxonomy's own `QueryExpansionStage`, the one `search` uses. Under
   the group's heading the digest says "No digest templates for this pair in
   config/daily_templates.yaml: its searches asked the taxonomy's templates."; the JSON group carries
   `asked_taxonomy_templates: true`. The ruling's change therefore reaches only pairs with digest
   templates, today the politics preset's.

   **Rejected:** (A) the preset's query alone, named, which I had built first. Under it, `nhi`'s
   three groups collapsed into one bare `health insurance` search. (B) none asked, named. Under it,
   the season's main topic would have had no digest. The PM's reason: the every-word rule is the feed
   provider's alone, and `nhi`'s reviewed templates were doing work against OpenAlex, Crossref and the
   government sources. The PM also said the earlier list of two fallbacks was too narrow, and that
   this is the PM's to own.
10. **A template is the query and one word, enforced.** The file refuses anything else when it
    loads: three words, the query alone, a filled query, the query twice. That keeps the measured
    rule from drifting back to long queries.
11. **The pin on the reviewed templates** is a sha256 of every coach-reviewed argument's templates
    (text and window) as canonical JSON: 35 arguments and 456 templates, taxonomy 1.6.0 as on dev. It
    is written beside a hand-written list of the two uniqueness pairs `daily` used to ask. A change to
    any byte of any reviewed template's text fails it, and so does a change to a window.
12. **The fixtures changed with the rule, written by hand.** I added item I ("Senate Republicans block
    the stopgap") on the 17th so that politics x Senate finds something. I retitled G and H on the 18th
    so that the next-date test still has new items, and retitled the auto-cut feed's second item so the
    three cassette pages are still found in the same order. Item A stays as a witness: only the
    taxonomy's `Senate vote count Senate` would keep it, and the digest does not list it.


## Operator follow-ups

### After this merges: one real politics digest with no --date

This is the PM's follow-up (2026-11-12), under a minute. It needs a dev pre-release that carries this
branch, installed with `scripts/install_channel.sh`. It stops without doing anything if `DEBATE_`
overrides are set, or if any `debate-research` command is running (v1-e39-t18's pilot-index work
included).

* **What it reads.** The politics feeds, over the network.
* **What it writes.** Only to a scratch folder on your Desktop, `daily-check-t25`, which is both the
  data directory and the digest directory. The real dev seen-set and feed cache are untouched. The
  digest file and the JSON, which hold titles, stay in that folder.
* **What it prints.** Counts only.

Where: your Mac, any terminal
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -f debate-research > /dev/null; then echo "STOP: a debate-research command is running; wait for it"; else mkdir -p "$HOME/Desktop/daily-check-t25" && cd "$HOME" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$HOME/Desktop/daily-check-t25/data" debate-research --json daily politics --digest-dir "$HOME/Desktop/daily-check-t25" > "$HOME/Desktop/daily-check-t25/daily.json"; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); r = e.get("error") or {}; d = e.get("data") or r.get("details") or {}; w = d.get("window") or {}; print("code", r.get("code"), "status", d.get("status"), "date", d.get("date"), "new", d.get("new_results"), "listed_before", d.get("listed_before")); print("window", w.get("since"), w.get("until")); print("groups", [(g["heading"], len(g["results"]), g.get("asked_taxonomy_templates")) for g in d.get("groups") or []]); print("providers", [(p["provider"], p["outcome"], p["queries"], p["results"]) for p in d.get("providers") or []])' "$HOME/Desktop/daily-check-t25/daily.json"; fi
```

**What success looks like:**

* `exit 0`, `code None` and `status COMPLETE`;
* `date` is today's date in Chicago;
* `window` is the 24 hours ending at about the time you ran it, in UTC;
* `new` is in the low single digits;
* `groups` lists both `Politics DA — Uniqueness` and `Midterms DA — Uniqueness`, each with `False`
  (it has digest templates);
* `providers` is `[('rss', 'ok', 4, N)]`: 4 queries.

`new 0`, or a group with 0, is an answer on a quiet day, not a failure. `exit 6` names a feed in
`providers` that did not answer. Paste the `exit` line and the four lines after it back to the PM.

### Done, 2026-11-12: the per-query counts

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
  `proposed`) and six `distinct items kept` rows. That was the script as it ran then; it now prints
  `digest` and `candidate` rows instead of `proposed` (the guide's "Counting a template before adding
  it");
* the last line is `exit 0`.

**How to read it.**

* A zero in a query row is an answer, not a failure.
* A feed row reading `failed: HTTP 403` (or similar) is worth knowing, and the counts still stand for
  the other feeds.
* A line starting `STOP:` means nothing was measured.

**What to paste back:** the whole output, to the PM. It is all counts.

## Follow-up work

* **`nhi`'s feeds under the every-word rule.** Whether they are starved can be counted with the
  script (`count_digest_feed_matches.py nhi`) before any `nhi` digest template is proposed.
* **Re-measure the midterms templates after the season turns.** The 2026-11-12 counts came nine days
  after the midterms. `{query} polls` and `{query} midterms` kept nothing then, and may not later.
* **`daily` by a scheduler.** If the coach ever schedules `daily`, the scheduled run's time decides
  the hours covered. A run at a fixed local hour now gives back-to-back 24-hour windows with no gap.

### Questions for the PM

None open. The PM's rulings of 2026-11-12 are built as given: A for the queries, C for the fallback,
and A for the once-only replacement of a UTC-dated file.

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

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-12

**Notes:**

Accepted. ac1, ac2, ac3 and the node pass, and the Goal is `Succeeded`.

* **ac1.** The operator's run of 2026-11-12T23:21Z is recorded whole, and it printed counts,
  publisher names and committed template texts only. The first query commit, `eada0db`, comes after
  the ruling. The proposal argues from the numbers, including the function-word inflation in "own
  plus one", and the PM ruled A.
* **ac2, checked against the branch.** The diff touches no taxonomy file and no prompt.
  `config/daily_templates.yaml` holds exactly the ruled four, each with its measured counts. The
  reviewed templates are pinned by a sha256 over all 456. Ruling C's tests were shown failing against
  the query-alone build, with nhi's eight queries pinned from dev's own code at `5c71e42`, not from
  the new code. Mutants 5 and 6 (the named line dropped, and a fallback to the query alone) were
  caught, as the ruling asked. Scoping each template by `queries`, so that the zero-count pairs run
  no search, is a good reading of the ruling.
* **ac3.** The tests were shown red on an injected clock at 23:00 and 07:00 Chicago, on both
  changeover days and in two other zones. An explicit `--date` keeps its UTC days, as ruled.
* **Decisions 1 to 12: accepted.** On decision 1, the default zone: `DailySettings` validates its
  default, so every settings load now resolves `America/Chicago` through the system's time zone
  database. The PM checked where that runs. The pilot API does not load `Settings` (it has its own
  `PilotConfiguration`). The cloud run image already resolves the same zone at import, through
  `backfile_import.NO_IMPORT_WINDOW_ZONE`, and the hspolicy25 rebuild ran on it. The Mac and CI have
  the database. So nothing breaks today. As insurance, an unconditional `tzdata` dependency is filed
  as a p3 follow-up in the next PM batch; today the lock carries it only for Windows.
* **The deviations are accepted.** The next PM batch amends the spec: the rulings (A, C, and the date
  default), plus `scripts/`, `tests/smoke/`, `scripts/stamp_build.py` and `tests/scripts/` in its
  packages.
* **The affected set** is the whole selection, so it goes to `ci` under agreement 10. The 1,499 tests
  run within the limit are enough for review.
* **The operator's post-merge block is accepted.** Its guards are: no `DEBATE_` overrides, and no
  `debate-research` process (v1-e39-t18's included). It writes only to a Desktop scratch folder and
  prints counts and group headings only. The PM records it.
* **Follow-ups, into the next PM batch:** the nhi feed count and the midterms re-measure as notes on
  the epic; the scheduler note needs nothing now.

`scripts/task pr`
