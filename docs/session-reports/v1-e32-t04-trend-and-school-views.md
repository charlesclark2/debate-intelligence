# Session report: v1-e32-t04-trend-and-school-views

| | |
|---|---|
| Task | `v1-e32-t04-trend-and-school-views` — Trends and per-school views |
| Spec | [`plan_specs/v1/e32-argument-landscape/t04-trend-and-school-views.yaml`](../../plan_specs/v1/e32-argument-landscape/t04-trend-and-school-views.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t04-trend-and-school-views` |
| Session status | COMPLETE, phase left InProgress for two PM rulings <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The landscape bundle now has weekly trends and a per-school view. **Trends** (`trends.csv`, and
`report.md`'s New this week, Rising and Falling sections) compare a snapshot's seven-day window with
the caselist's previous one on the same topic:
* a week's teams come from the rounds first seen in that window, keyed on team and content (t03's
  round identity), never the path;
* labels are NEW, RISING, FALLING and STEADY, with the 5-point threshold and the 3-team floor
  unchanged;
* a topic change is named, never compared across;
* the report says on its face when its windows span less than a full topic cycle.

The **school view** (`schools.csv`, `schools.md`) lists each school and team code as disclosed, with
the positions its rounds read on each side, the round counts and the last tournament. It takes t03's
counted reads, so `v1-e32-t09`'s aff assignments reach it through the `AffAssignment` seam with no
code of its own.

Every acceptance criterion passes. **I left the phase InProgress** because two rules in the PM's
brief disagree with the spec as written, and the brief says to ask:
1. where the "By school" section goes;
2. whether `last_tournament` is allowed.

Both are in [Questions for the PM](#questions-for-the-pm). The dry run on hspolicy26 is
[below](#dry-run-on-the-newest-hspolicy26-snapshot), counts only. **Look first at question 1:**
I put the school view in its own two files, not in `report.md`, so that the circuit-wide report
still names nobody.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `fixture-extension`: third snapshot and topic-change fixture | Done | The 2026-09-22 window gains five rounds and a file carried in under a new path. A separate LD caselist changes topic between its two snapshots. `expected_trends.csv` and both READMEs' tables were written by hand. |
| `trend-computation`: weekly delta and trend labels | Done | `application/landscape_trends.py`, with domain values in `domain/landscape_trends.py`. The round identity moved into `application/landscape_counts.py` in a separate refactor commit, with output unchanged (`61ed2c4`, 105 t03, t05, t09 and t10 tests unchanged). |
| `school-view`: per-school disclosed-positions view | Done | `application/landscape_schools.py`, `domain/landscape_schools.py` |
| `render-and-gates`: render trends and schools into the bundle | Done | `render.py`, the service's `bundle()`, the run (seven files, `report.md` uploaded last; topic map and range passed in), and the scan (paths only in the school view). The goldens were hand-written before the renderer was run on them, and all seven matched on the first run. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on a three-snapshot fixture, trends.csv gives per position the weekly teams, weekly share, previous share, delta in points and a label, matching a hand-computed expected file | PASS | `test_the_third_windows_trends_csv_matches_the_hand_computed_expected_file`: the rendered rows equal `tests/fixtures/landscape/synthetic_caselist/expected_trends.csv` byte for byte. `test_the_third_window_matches_the_hand_computed_expected_rows` checks the computed values. The working is in the fixture README's "Trends" table. |
| ac2: RISING/FALLING only at ≥ threshold (default 5 points) and ≥ minimum teams (default 3) in one of the two weeks; a first snapshot is all NEW with no deltas | PASS | `test_a_change_of_exactly_the_threshold_moves_only_with_enough_teams` (8 cases, 20 teams a week, so 1 team is exactly 5 points: 4→5 and 2→3 teams move, 1→2, 2→1 and 0→2 are held back). Also `…below_the_configured_threshold…`, `test_the_team_floor_is_configurable`, `test_a_caselists_first_snapshot_is_all_new_with_no_deltas` and `test_a_first_snapshot_writes_all_new_with_no_previous_share_or_delta`. |
| ac3: when topics.yaml maps two snapshots to different topics, no trend rows cross them and the report says the topic changed | PASS (see [question 3](#questions-for-the-pm)) | On the fixture's `topics.yaml`: `test_no_trend_crosses_a_topic_change_and_the_trends_say_it_changed` and `test_a_topic_change_draws_no_trend_and_the_report_says_the_topic_changed`. Through the real run and `YamlTaxonomyRepository`: `test_a_run_reads_a_topic_change_from_topics_yaml_and_draws_no_trend_across_it`. An old-topic round in the inputs is refused: `test_a_round_from_the_other_topic_is_refused`. |
| ac4: schools.csv and the Markdown schools section list school, team code, side, position_id, rounds, last tournament; no debater names; deterministic order | PASS (see [questions 1 and 2](#questions-for-the-pm)) | `test_rendering_the_fixture_matches_the_golden_file[schools.csv]` and `[schools.md]` (hand-written goldens). `test_the_view_matches_the_hand_computed_rows` (26 rows). `test_the_school_view_carries_no_debater_name_tag_cite_or_path`: names planted in every tag, cite, heading and filename leave both files equal to their goldens. `test_shuffled_inputs_give_the_same_view`, plus the bundle-wide shuffle test, for the order. |
| ac5: the trend and school sections are added to the t03 bundle without changing positions.csv or top_cards.csv (t03 goldens still pass) | PASS | `test_rendering_the_fixture_matches_the_golden_file[positions.csv]`, `[top_cards.csv]` and `[impact_cards.csv]` pass. `git diff --stat c03cf83 -- tests/fixtures/landscape/golden/positions.csv …/top_cards.csv …/impact_cards.csv` prints nothing. `report.md`'s golden gained the trend sections, as the render node asks. |
| `fixture-extension`: expected trends file exists, contains `RISING` | PASS | `tests/fixtures/landscape/synthetic_caselist/expected_trends.csv`, 2 `RISING` rows |
| `trend-computation`: `uv run pytest packages/debate_core/tests/application/test_landscape_trends.py` | PASS | `25 passed in 8.57s` |
| `school-view`: `uv run pytest packages/debate_core/tests/application/test_landscape_schools.py` | PASS | `10 passed in 4.29s` |
| `render-and-gates`: `uv run pytest packages/debate_core/tests/arguments/landscape/test_render.py` | PASS | `32 passed in 2.26s` |
| `render-and-gates`: `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations` |

### Mutation checks (working agreement 10; no Hypothesis in these tests)

Each mutant was applied alone, the trend or school test file run against it, and the file restored.
The mutation scripts are in the scratchpad, not the repository.

| Mutant | Result |
|---|---|
| First seen keyed on the path (`source_path` in the round identity) | caught: expected rows. The explicit rename test alone also fails it (`assert 4 == 3`, `KK` counted as a new aff team). |
| Threshold exclusive (`<=` for `<`) | caught: the 4→5 teams case |
| No team floor | caught |
| Floor needs both weeks (`min` for `max`) | caught |
| No cross-topic refusal | caught |
| No topic change named | caught |
| NEW never after the first week | caught |
| Running totals instead of first-seen weeks | caught |
| Weekly teams on any side | caught |
| First week labelled STEADY | caught |
| Rows read only last week dropped | caught |
| School view: no-side rounds become aff rows; earliest tournament for latest; ties to the last; rounds ascending; no-team rounds not counted | all caught |
| School view: disclosures after the snapshot not ignored | **survived** at first. Added `test_a_spelling_disclosed_after_the_snapshot_does_not_change_the_view`, which now catches it. |

I deleted `test_renaming_every_path_changes_no_trend` (agreement 8). It passed against the
path-keyed mutant, because on this fixture renaming every path cannot tell the two keys apart. The
explicit rename test is the one that catches it.

### Before the report (working agreement 10)

* **Affected set: over two minutes, left to the pull request's `ci`.**
  * `uv run scripts/affected_tests.py` lists 169 of 450 test files (37.6%), from 35 changed files.
  * The whole selection takes about six minutes, so this set is about 2.3. t10's 155-file set
    was stopped at its 115 s alarm.
  * The 135 files I did not run are mostly caselist-removal suites, CLI command suites and 18
    smoke checks that build an installed CLI. They reach this change only through the CLI
    container's imports.
* **What I ran instead:** 42 targets, with CI's markers under a 115 s alarm on the interpreter.
  * The targets: every landscape, aff-assignment and plan-text file in the affected list, the whole
    `packages/debate_core/tests/arguments/landscape/` directory, the domain landscape tests, the
    doctor and installation tests, the landscape smoke check, and the always-run list
    (`tests/architecture`, `tests/specs`, the CLI's `test_app.py` and `test_help_rendering.py`).
  * Command: `.venv/bin/python -m pytest -n auto -q -m "not slow and not live" <the 42>`.
  * Result: **1337 passed in 28.76s**, load average 5.1.
* `uv run --frozen ruff check .`: All checks passed.
* `uv run --frozen ruff format --check .`: 1245 files already formatted.
* `uv run --frozen pyright` (the whole repository, as CI runs it): 0 errors, 0 warnings, 0 informations.
* `uv run --frozen lint-imports`: 16 kept, 0 broken.
* `uv run --frozen python scripts/check_thin_handlers.py`: 50 handlers within 25 statements.
* `uv run --frozen python scripts/docs_index.py --check-descriptions`: 46 documents have a description.
* `uv run --frozen python scripts/check_command_blocks.py --base origin/dev`: OK, no `#` comment in 389 shell code blocks in 150 Markdown files, this report among them.
* `uv run scripts/validate_specs.py`: `OK: 435 files, 40 epics, 373 tasks, 22 releases`.

## Dry run on the newest hspolicy26 snapshot

This was read-only, with counts only and no `--publish`. Before it ran, no `DEBATE_*` variable was
set and no `caselist pull` was running.

The run was `LandscapeRunService.run(dry_run=True)` through the CLI's container, from a scratchpad
script that printed counts only. That is t10's method; it asks no bucket and makes no AWS call. The
config was this worktree's `config/landscape`: taxonomy 1.1.0, as released, with the coach's
overrides.

**It wrote nothing.** The run reported `written False`. All 9 files under the data directory's
`landscape/` and `reports/` had the same SHA-256 after the run as before. **43.6 s**, load average 4.0.

| Count | Value |
|---|---|
| Snapshot | 2026-10-20, current (not stale); previous window 2026-10-13 (adjacent) |
| Weekly windows on the topic | **15**, from 2026-07-07 to 2026-10-20 (the store's 15 weekly manifests; 2026-07-21 is missing) |
| Full topic cycle | no: the topic runs 2026-07-01 to 2027-06-30. The report carries the short-history notice. |
| Teams disclosing this window / the previous | aff 150 / 124, neg 129 / 102, either side 166 / 143 |
| Trend rows by label | RISING 4, FALLING 3, STEADY 62, NEW 0 (69 rows) |
| Rows held back by the team floor | 0 |
| Schools / team codes in the school view | 147 / 456 |
| School-view rows | 2,005 (aff 1,120, neg 885) |
| Rounds left out of the school view | 0 on no readable side, 0 by no readable team |
| Scan hits | 6, all in `top_cards.csv` (3 school, 2 team code, 1 tournament): the same six as t05 and t10. None in `report.md`, `trends.csv` or the school view. |
| Planned bundle | `positions.csv`, `top_cards.csv`, `impact_cards.csv`, `trends.csv`, `schools.csv`, `schools.md`, `report.md` |
| t03's counts, for comparison | 75 positions, 353 top-card rows, 4,352 rounds: unchanged from t10's run |

No team floor held a row back, because a 5-point move needs at least 7 aff teams at this week's
150. The floor binds on small caselists and early windows, as the fixture shows. The threshold and
the floor were not changed.

## Files changed

* **`debate_core.domain`**
  * `landscape_trends.py` (new): `TrendLabel`, `TrendRow`, `WeeklyTeams`, `TopicChange`,
    `LandscapeTrends`, and the window definition (`WINDOW_DAYS = 7`, ADR-0016).
  * `landscape_schools.py` (new): `SchoolRow` and `SchoolView`, with the policy row in the docstring.
* **`debate_core.application`**
  * `landscape_counts.py` (new): `round_id` and the team identity, moved from `landscape_report`
    (which re-exports `round_id`), and `CountedReads`.
  * `landscape_trends.py` and `landscape_schools.py` (new): the two computations.
  * `landscape_report.py`: `count()` returns what was counted. The inputs gain `snapshot_topics` and
    `topic_range`, and the bundle gains `trends`, `schools` and three files.
    `CIRCUIT_WIDE_FILES` and `SCHOOL_VIEW_FILES` are new.
  * `landscape_run.py`: `BUNDLE_FILES` is seven files, `report.md` last. Each weekly snapshot's
    topic and the topic's range are passed in. The result carries `trends` and `schools`.
  * `landscape_scan.py`: `school_view_files` are scanned for paths only.
* **`debate_core.arguments`**
  * `landscape/render.py`: `trends.csv`; `report.md`'s short-history notice, weekly-windows row,
    trends bullet and trend sections; `schools.csv`; `schools.md`.
* **`debate_core.testing`**
  * `landscape_report.py`: `read_synthetic_caselist(through=…)`, `read_topic_change_caselist`,
    `topic_change_snapshot_topics`, and a caselist and newest snapshot for `synthetic_staleness`.
* **Tests**
  * New: `packages/debate_core/tests/application/test_landscape_trends.py` and `test_landscape_schools.py`.
  * Additions: `test_render.py`, `test_landscape_run.py`, `test_landscape_scan.py`.
  * t05's pinned bundle lists, updated to seven files: `test_landscape_run.py`,
    `packages/debate_cli/tests/test_landscape_command.py`, and the smoke check
    `tests/smoke/test_landscape_smoke.py` (working agreement 5).
* **Fixtures**
  * `scripts/make_landscape_fixture.py`.
  * `tests/fixtures/landscape/synthetic_caselist/`: new rows only (`git diff` shows no existing row
    changed), `expected_trends.csv`, and the README.
  * `tests/fixtures/landscape/topic_change_caselist/` (new).
  * `tests/fixtures/landscape/golden/`: `trends.csv`, `schools.csv` and `schools.md` are new, and
    `report.md` was updated. All were written by hand.

## Deviations from the spec

1. **Files outside `constraints.packages`.** The spec lists `debate_core.application`, `.arguments`
   and `.domain`. Its own plan nodes need the fixture generator, the fixtures, the fixture reader in
   `debate_core.testing`, and tests. That is t03's ruling 2 of 2026-10-24 again: the generator, the
   shared reader, and the package's tests. Three edits outside even that list only bring pinned
   expectations to the seven-file bundle: the CLI's `test_landscape_command.py` and the smoke check's
   `BUNDLE` tuple, plus t05's own run test in-package. No CLI source changed.
2. **The school view is in `schools.md`, not in `report.md`.** A literal reading of ac4 ("the schools
   section of the Markdown") and the render node puts "By school" in `report.md`. That would make the
   circuit-wide report name schools and team codes. It would break the policy's circuit-wide row and
   the E32 gate's item 4, make `report.md`'s own line "No school, team or debater is named" false,
   and put school codes beside the counterplan and alternative texts t11 is to add. The section is
   in the bundle in its own Markdown file. This is [question 1](#questions-for-the-pm).
3. **trends.csv's column names.** The label ac1 asks for is `trend_label`. `label` is the position's
   name, as in positions.csv. I added `held_back_by_team_floor`, so a STEADY row says why.
4. **t03's "New this week" section is the trends' now.** It lists the same positions, worded by
   window and weekly share. In a caselist's first snapshot the trends call every position NEW (ac2),
   while positions.csv keeps t03's `is_new=false` there: t03's "new" is "after the previous snapshot",
   and a first snapshot has none. The report explains both.

## Decisions and assumptions

1. **First-seen key.** A round is t03's `round_id`: team, side, tournament and round, never the
   path. The path parser reads the per-team sequence number as a copy index and keeps it out of the
   tournament; I checked this on a probe path. A file naming no round is a round of its own,
   identified by its team and its content's digest. So a renamed carried file is the old round, and
   the same bytes read in a new round are a new disclosure. Both cases have tests.
2. **The window and the previous week.** A snapshot's window is the seven days up to its date. The
   previous week is the caselist's snapshot just before this one, from the weekly manifests. If that
   snapshot is on another topic, there is no previous week and the report names the change.
   A gap of more than seven days is stated in the windows row.
3. **Shares** are taken on the position's own side, as t03's are. A week with no team on that side
   gives no delta, and the row is STEADY.
4. **The threshold is inclusive** (exactly 5.0 points moves). The floor is the larger of the two
   weeks' team counts, as ac2 says ("in one of the two weeks"). Both are parameters of the service
   constructor; no CLI flag was added, since the CLI is t05's.
5. **A full topic cycle** means the first window opens on or before the topic's first date in
   `topics.yaml`, and the next window would fall past its last. Without the range, the report says
   it may be short.
6. **Last tournament** is the tournament of the row's latest round by first-seen snapshot. Within
   that snapshot it is the one most of the row's rounds name, ties going to the first in text order.
   A school or code spelled more than one way shows its most common spelling.
7. **The scan in the school view looks for paths only.** Schools, codes and tournaments are its
   content, and listing them would stop every publish on every team. Paths stay hits in every file.
8. **ADR-0016's window, not a daily cadence.** The trends use the weekly manifests, as t05's run
   already does.

## Questions for the PM

A relay prompt for the PM, ready to paste:

```text
v1-e32-t04 (trends and per-school views): three questions; the code is done and every criterion passes as I read it.

1. Where the "By school" section goes.
   Facts: ac4 says "schools.csv and the schools section of the Markdown"; the render node lists "By school" among report.md's
   sections. But report.md is the circuit-wide report. Policy "What a report may show" allows it no school or team code, the
   E32 gate item 4 requires it to hold none before it is shared, report.md says "No school, team or debater is named", and
   t11 will quote CP texts and alternatives there, which policy 1.13 allows only where no school or team code is beside them.
   Options:
   A. (built) The view in its own files in the same bundle: schools.csv and schools.md (with a "By school" section). report.md
      and its CSVs name nobody; the scan checks the school view for paths only. ac4/ac5 pass reading "the Markdown" as the
      bundle's Markdown; amend ac4 to say schools.md.
   B. "By school" inside report.md, as the spec literally says. Breaks the circuit-wide row, gate item 4, and t11's placement.
   Recommendation: A. It keeps the one document the coach shares circuit-wide free of identity, and t11 needs it that way.

2. Whether schools.csv may show last_tournament.
   Facts: ac4 asks for it. Your brief says the school view "shows position ids and counts only", and the policy row allows
   "school plus team code, as disclosed. Never more." A tournament names no one, but it is more than an id or a count, and with
   a team code it locates the team's rounds.
   Options:
   A. (built) Keep it, as ac4 says; the policy row is read as identity (names), which a tournament is not.
   B. Drop it: one column and one Markdown cell; ac4 amended.
   Recommendation: A, if you read the row as identity only; otherwise B. Either is a five-minute change; I have not guessed
   further than the spec.

3. ac3's "no trend rows are emitted across them".
   Built: after a topic change the first window's rows are all NEW with no previous share and no delta (like a first snapshot),
   and the report says the topic changed. The other reading is zero rows in trends.csv. Recommendation: keep rows, since NEW
   is what they are on the new topic.

FYI, going ahead unless told otherwise:
- hspolicy26 has 15 weekly windows (2026-07-07 to 2026-10-20, 2026-07-21 missing), not "a few". The short-history notice still
  shows, because the topic runs to 2027-06-30. No row was held back by the team floor this week (150 aff teams).
- The phase is left InProgress for questions 1 and 2. Reply with a letter for each, and whether to set Succeeded.
```

## Operator follow-ups

None from this session. The publish of the seven-file bundle is the PM's coordinated block. The dry
run above lists the files it would upload. They all go to `reports/landscape/<caselist>/<snapshot>/`
in the private bucket and the local `reports/` directory, and nowhere else.

## Follow-up work

1. **Removal and the annual purge do not yet reach the school view** (E30, removal; and the policy's
   retention table). The policy keeps per-school landscape views "on the same clock as their sources"
   and has them "removed with their sources". `caselist remove` and the September purge do not touch
   `reports/landscape/`. Until they do, a removal needs the bundle rebuilt and republished by hand,
   or the school files deleted. This belongs to E30's removal tasks; it matters once the first school
   view is published.
2. **The CLI's module docstring and output name four files** (`debate_cli/commands/landscape.py`,
   t05's). The bundle is seven files now. The command's JSON has no trend or school counts either.
   A small t05 follow-up; I did not edit CLI source.
3. **The scan cannot flag a debater name in a school directory.** The school view is scanned for
   paths only. The path parser's `TeamCodeText` guard, which rejects whitespace and long codes, is
   what keeps names out of the team-code column. No check covers a person's name used as a school
   directory. This is a policy-level question for E30's import, not for this view.
4. **ADR-0016's consequence ("any report that spans less than a full topic cycle says so")** is now
   done for E32's report. Its other consequence, that a missed week is a permanent hole, shows as
   the missing 2026-07-21 window. The windows row names a gap only when it falls between the two
   compared windows.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
