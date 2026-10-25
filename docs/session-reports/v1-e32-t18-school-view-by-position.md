# Session report: v1-e32-t18-school-view-by-position

| | |
|---|---|
| Task | `v1-e32-t18-school-view-by-position` — The school view by position: every team that reads each DA, CP and K, with its caselist page |
| Spec | [`plan_specs/v1/e32-argument-landscape/t18-school-view-by-position.yaml`](../../plan_specs/v1/e32-argument-landscape/t18-school-view-by-position.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t18-school-view-by-position` |
| Session status | COMPLETE |

## Summary

`schools.md` now has a **By position** section after **By school**. It lists the negative's DAs, CPs,
Ks and Ts, then the affirmative side's positions. Under each position it gives every team that read
it (school, team code, side, rounds), most rounds first, with a link to the team's public openCaselist
page. `schools.csv` gains a `team_page` column holding the link or nothing. The link is built by
`debate_core.domain.search_source_links`' rule, which was reused, not copied: the search pilot's
`source_link` and the school view now call the same `team_page_url`. The view never stores a link. It
works each one out from its own caselist and the row's school and team code, so no other link can get
into a row. A team with no link is counted by reason in both files. **The count on hspolicy26 through
2026-10-20: all 155 schools and all 475 team codes get a link, and none is refused**, so no ruling is
needed. The bundle's file names are unchanged, the circuit-wide files are byte-identical to before
(their goldens did not change), and the scan treats the school view as it did.

One thing to look at first: to give the golden files teams that do get a link, the synthetic fixture's
"Birchmoor Fictional" is now "Birchmoor". It is one word, as the real archive spells every school. That
touched the fixture generator in `scripts/`, which is outside the task's packages (Deviations).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `school-view-by-position`: School view by position | Done | Count first (read-only), then the rule exposed by its three values, the fixture rename, the goldens and tests at red, the implementation, then the mutants |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: on the synthetic fixture, `schools.md`'s "By position" section lists each position's schools and team codes with side, rounds and the team-page link, and `schools.csv`'s `team_page` column matches, against hand-written golden files; a school or team code that is not one address word gets no link; tests shown failing first | PASS | Goldens written by hand from the fixture's rows (below). **Red** at `b8a4fcb`, before the renderer changed: `uv run pytest -q -p no:randomly packages/debate_core/tests/arguments/landscape/test_render.py` → `7 failed, 29 passed`. The failures were both golden files, the no-debater/path golden check, the column pin, the no-link test, the team-code test and the section-order test. The scan test passed at red, as it should, because it pins today's behaviour. **Green** at `d07e386`: the same command → `36 passed`. Not an address word: the golden's three display-name schools (a space in the name) show `none` and an empty `team_page`; `test_a_team_code_that_is_not_one_address_word_gets_no_link_and_is_counted` changes `QQ` to `Q-Q` and checks for no link plus the count "7 do not: 6 whose school…, 1 whose team code…"; the domain tests cover each reason |
| ac2: no circuit-wide file carries a link or team code, by test; the counts of linked and unlinked teams on hspolicy26 are in the report | PASS | `test_no_circuit_wide_file_carries_a_link_and_the_school_view_does` (no `opencaselist`, `http:`, `https:` or `www.` in any of the five circuit-wide files) and the existing `test_a_scan_of_the_output_finds_no_team_code_school_tournament_or_path_from_the_disclosures`, both passing. Counts are under [The count on hspolicy26](#the-count-on-hspolicy26) |
| Node: Landscape report tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` → `65 passed in 5.29s` |

### The count on hspolicy26

Read-only, run before the view was built, with the rule's own `why_no_team_page`. It read the school
view already on this machine for hspolicy26 at 2026-10-20,
`~/.debate-research/dev/reports/landscape/hspolicy26/2026-10-20/schools.csv`, written at taxonomy
1.2.0. Its header matches the 1.2.0 dry run `v1-e32-t09` measured: coverage 63,494/126,681 cards and
2,709/4,352 rounds, and the same 2,109 rows, 155 schools and 475 team codes. The script printed counts
only. It ran in 0.37 s, and the file's SHA-256 was the same before and after (`45632d6e…29d6e9fb`).

| Count | Value |
|---|---|
| Rows; schools; team codes | 2,109; 155; 475 |
| Schools whose name is one address word | **155 of 155** |
| Team codes that get a link | **475 of 475** |
| Team codes without a link, by reason: school not one address word / team code not one address word / unread / caselist | 0 / 0 / 0 / 0 |
| Schools with at least one linked team | 155 |

Nothing is without a link, well under the PM's 10% line, so no ruling is asked for. That fits what
`v1-e39-t11` found on the dev index on 2026-10-22: every school is one word, and every team code is
letters and digits. The rule's other assumption was not checked here, because a session does not call
openCaselist: that the archive spells these words the way openCaselist's own addresses do. It stays
the coach's check: open one link after republishing.

### Mutants

Fifteen mutants were applied one at a time to the rule, the view and the renderer. Each one ran
against the three test files that cover those modules (`tests/domain/test_search_source_links.py`,
`tests/arguments/landscape/test_render.py`, `tests/application/test_landscape_schools.py`) with
`-p no:randomly`, and each run had a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY`, as working agreement
8 requires. None of these files uses Hypothesis, so no catch depends on a saved example. Each file was
restored from `HEAD` and its bytes compared. Every attempt collected and ran, and none errored.

| Mutant | Result | Caught by (among others) |
|---|---|---|
| Rule: the school is not checked (a display name gets a link) | caught, 18 failed | the domain refusal tests; the golden `schools.md` |
| Rule: the team code is not checked | caught, 8 failed | the domain refusal tests |
| Rule: the school is matched by `search`, not whole | caught, 25 failed | the domain refusal tests |
| Rule: a space allowed in a school | caught, 7 failed | the domain tests; the golden `schools.md` and `schools.csv` |
| Rule: a hyphen allowed in a team code | caught, 2 failed | `…says_why[…L-M-team_code]`; the `Q-Q` team-code test |
| Rule: `UNKNOWN` not refused | caught, 4 failed | the domain tests for `UNKNOWN` |
| Rule: the URL built whatever the reason | caught, 35 failed | the domain tests; both goldens |
| View: the link built from the casefolded team code | caught, 5 failed | both goldens |
| View: the link gets an extra round segment | caught, 4 failed | both goldens |
| Circuit-wide: every CSV header carries an openCaselist address | caught, 8 failed | the four circuit-wide CSV goldens; `test_no_circuit_wide_file_carries_a_link…` |
| Circuit-wide: `report.md` links the caselist's openCaselist page | caught, 3 failed | the golden `report.md`; `test_no_circuit_wide_file_carries_a_link…`; the `Q-Q` test |
| CSV: the `team_page` column left empty | caught, 4 failed | the golden `schools.csv`; the no-link test, which checks the view does carry links |
| Count: a team-code refusal counted as a school's | caught, 1 failed | the `Q-Q` team-code test |
| By position: fewest rounds first | caught, 2 failed | the golden `schools.md` |
| By position: the affirmative side first | caught, 2 failed | the golden `schools.md` |

Each run took 2.4 to 2.8 s. The script and its output are in the session's scratchpad.

### Checks before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 201 of 470 test files, from 15 changed files |
| The affected set (`.venv/bin/python -m pytest -n auto -m "not slow and not live"` over that list, under `perl -e 'alarm 115'`) | **Over two minutes:** stopped by the alarm at 81% with no failure and no error; no worker was left behind. Under working agreement 10 it is left to the pull request's `ci` check |
| What changed, within the limit: `packages/debate_core/tests/domain`, `packages/debate_core/tests/arguments/landscape`, the landscape `application` tests (report, schools, scan, run, trends, aff assignment), the two removal school-view tests, `packages/debate_api/tests/test_search_pages_follow_ups.py` (the card page's link), the CLI landscape command, the landscape smoke test, `tests/docs`, and the always-run list (`tests/architecture`, `tests/specs`, the CLI's `test_app.py` and `test_help_rendering.py`) | `2249 passed in 27.00s` |
| `uv run ruff format --check .` | `1300 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright packages/debate_core scripts/make_landscape_fixture.py` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 16 kept, 0 broken.` |
| `uv run python scripts/check_thin_handlers.py` | `OK: 51 CLI command and API route handlers within 25 statements` |
| `uv run python scripts/docs_index.py --check-descriptions` | `All 47 indexed documents under docs/ have a description` |
| `uv run python scripts/check_command_blocks.py` | `OK: no '#' comments in 425 shell code blocks in 152 Markdown files` |
| `uv run scripts/validate_specs.py` | `OK: 445 files, 40 epics, 383 tasks, 22 releases` |

## Files changed

* **`debate_core.domain.search_source_links`.** The rule takes its three values directly:
  `why_no_team_page(caselist, school, team_code)` returns the first part it refuses (`NoTeamPage`:
  unread, caselist, school, team code), and `team_page_url` returns the link. `source_link` calls them,
  and its behaviour is unchanged: the 31 existing tests passed before any new test was added (`3c315cd`).
* **`debate_core.domain.landscape_schools`.** `SchoolView.team_page(row)` gives the link,
  `teams_without_team_page` counts the teams without one by reason (once per team, as `teams` counts),
  and `teams_with_team_page` counts the rest. A row holds no link.
* **`debate_core.arguments.landscape.render`.** `SCHOOL_COLUMNS` gains `team_page`. The `shows=` line
  names the link and policy 1.14, and a `team_pages=` header line holds the count. `schools.md` gets a
  **Team pages** row in its header table, the intro sentence names the link, and the **By position**
  section follows **By school**. The circuit-wide renderers are untouched.
* **`debate_core.application.landscape_schools`.** One docstring sentence: the link is the view's.
* **Tests.** `test_render.py` gets four tests (no link in circuit-wide files, the scan unchanged, a
  team code that is not an address word, section order) and its column pin is updated.
  `test_search_source_links.py` tests `team_page_url` and `why_no_team_page` and checks that the card
  page and the school view link a team alike. `test_landscape_schools.py` has the rename.
* **`tests/fixtures/landscape`.** The golden `schools.md` and `schools.csv` were written by hand (see
  Decisions), the fixture's six Birchmoor disclosure rows were renamed, and the README says why.
* **`scripts/make_landscape_fixture.py`.** One school renamed in `TEAMS` and a line saying why
  (Deviations).
* **`docs/guides/landscape-taxonomy.md`.** A short section for the coach, "Who reads each position:
  the school view".

## Deviations from the spec

* **`scripts/make_landscape_fixture.py` is outside `constraints.packages`.** The task's goldens need
  teams that get a link. Every school in the shared synthetic fixture was a display name with a space,
  so none would have had one. The fixture is in scope (`tests/fixtures/landscape`), and the script is
  what writes it, so I changed the one school there and regenerated. Only the six Birchmoor rows of
  `disclosures.jsonl` changed (school and path; same digests and rounds), so every count in every
  golden is unchanged. The rename is its own commit (`13ccdbd`). In it the existing `schools.md` and
  `schools.csv` goldens were edited by hand for the rename only, and every landscape test passed
  (189 in debate_core, 37 in the CLI and smoke tests) before any new behaviour was added.
* **The count came from the existing local bundle, not a new dry run.** That bundle's `schools.csv`
  is the same view the PM's 155 and 475 come from (see the count section). Reading it took 0.37 s,
  compared with about 50 s for a dry run, and wrote nothing.

## Decisions and assumptions

* **The link is computed, never stored.** Putting `team_page` on `SchoolRow` would let a row carry a
  link from anywhere. As a method of the view over its own caselist and the row's school and team code,
  the forbidden "a link built from anything but the caselist, the school and the team code" cannot
  happen. The link uses the spelling the row shows: the commonest spelling of the team, as `v1-e32-t04`
  shows it.
* **Section order:** the negative side first, by kind in the report's kind order (DAs, CPs, Ks, Ts,
  then any theory the negative reads), then the affirmative side (affs, advantages, theory), then any
  position either side reads. Within a kind, positions follow the report's order (teams, rounds, id).
  Within a position, teams are sorted by rounds, then school, team code and side. Negative headings are
  the report's kind names ("Disadvantages"). Other sides' headings carry the side ("Affirmative side:
  Advantages"), since theory can come up on both sides.
* **Position ids, not labels,** head each position, as the rest of the view does: `v1-e32-t04` keeps
  the view to ids and counts.
* **No link is written `none`** in `schools.md`, so a coach can tell "no link" from a missing cell. In
  the CSV it is empty, as the PM asked.
* **The reasons are counted in the view's files** too, not only in this report: "2 of 8 team codes link
  to their openCaselist page; 6 do not: 6 whose school is not one address word". A team refused for both
  parts is counted under the first part the rule checks (the school).
* **The goldens were written by hand.** The `By position` tables were regrouped by hand from the
  golden rows. For example, `spending-da` is YY, QQ, ZZ and JJ with one round each, and
  `costs-advantage` has XX with two rounds first. The CSV's new column was added to each row from the
  fixture's schools: a Birchmoor row gets its team's URL, and every other row gets nothing. No golden
  came from running the renderer.
* **The scan** (`landscape_scan`) needed no change. A link is not a disclosure path, so the school view,
  which is scanned for paths only, still has no hit. A new test pins that the run's scan of the
  synthetic bundle finds nothing, and that scanning the school view as if it were a circuit-wide file
  finds its schools.

## Operator follow-ups

None. Republishing hspolicy26's bundle with the new section is the PM's to coordinate after the
merge. Nothing was published or written outside this worktree.

## Follow-up work

* **Merging with `v1-e32-t15`.** It also edits `arguments/landscape/render.py`. If a sync conflicts
  there, keep both sides. This task adds `_team_pages`, `_by_position_section` and `_team_page_cell`
  after `render_schools_markdown`, plus constants after `SCHOOL_COLUMNS`. It does not change the
  circuit-wide renderers.
* **The coach's link check.** After the republish, open one team's link from `schools.md` and confirm
  it lands on that team's page. This is the same check `v1-e39-t11` left for the card page; the archive
  spelling a school the way openCaselist's address does was not checked here.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
