# Session report: v1-e32-t57-school-rounds-fit-the-page-budget-and-are-checked-at-report-time

| | |
|---|---|
| Task | `v1-e32-t57-school-rounds-fit-the-page-budget-and-are-checked-at-report-time` — The per-school round lists stay inside the page budget all season, and a school page over it is named at report time |
| Spec | [`plan_specs/v1/e32-argument-landscape/t57-school-rounds-fit-the-page-budget-and-are-checked-at-report-time.yaml`](../../plan_specs/v1/e32-argument-landscape/t57-school-rounds-fit-the-page-budget-and-are-checked-at-report-time.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t57-school-rounds-fit-the-page-budget-and-are-checked-at-report-time` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Built to the PM's ruling of 2026-11-07, which accepted the proposal on all four questions.

1. **Team pages.** Each team's rounds now have a page of their own, cut from `schools.md`: a `####`
   heading inside its school's `###`. The school page keeps its table, less the per-row Team page
   column, then lists the school's teams. Each team in the list has its openCaselist link and a link
   to `/landscape/<caselist>/schools/<school>/<team>`. A `####` heading never makes a school page.
2. **The check.** The dry run and the publish measure every school-view page: the front page, each
   school, each team and each position. A page counts as its body's bytes plus a 28 KiB frame
   allowance, against ADR-0019's 153,600. The text has a `PAGES:` line, and `--json` has a `pages`
   object, which also records the largest position page each week. A page over the budget is named
   and published all the same.
3. **The move.** To measure the bytes the pilot sends, the Markdown cut and render moved from
   `debate_api` into `debate_core.arguments.landscape.pages`. Golden pages, written before the move,
   are byte for byte the same after it. `debate_core` now declares markdown-it-py.

**Size at the season's end.** The test renders the largest school through `debate_core` at 151 and
453 rows, with 1,158 and 3,474 round lines. The largest team has 257 and 771 lines. The school page
and the team page stay under the budget at every one of these sizes. The same school page as built
before this task is 155,156 to 412,392 bytes.

`schools.csv` and `school_rounds.csv` are unchanged, column for column. The circuit-wide files are
unchanged. ac4 is the operator's republish after the 2026-11-11 run, so the Goal stays `InProgress`.

**The PM should look first at the deploy order** (Operator follow-ups, item 1). A dev pilot older than
this task, serving a `schools.md` that has team headings, makes a "school" page of every team. So the
pilot carrying this task must be deployed to dev before the republish.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `school-rounds-fit-the-page-budget-and-ar` (Rounds within the budget) | Done | Proposal measured and ruled first (ac1). Each part's tests were shown failing first, then built to the ruling; 22 mutants on the check and the cut, all caught (two after a test was tightened). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the proposal, with the bytes measured at the largest real size and the season's projected size, ruled on by the PM before any code | PASS | Sent on 2026-11-07 before any code. The measurements are under **The proposal's measurements** below; the harness was a scratch test, not committed. The PM ruled the same day and accepted all four questions. Nothing was committed between the proposal and the ruling. |
| ac2: the largest school page at both sizes stays under the budget, by a test carrying a page that large, shown failing first | PASS | `test_the_largest_school_page_and_team_page_stay_under_the_budget_today_and_at_the_seasons_end`, in `packages/debate_api/tests/test_landscape_pages.py`, runs four sizes: rows 151 and 453 × lines 1,158 and 3,474. It checks the school page and the largest team's page (257 and 771 lines). Green: **4 passed**. Red against `render.py` as it was before the team pages: **4 failed**, each at `(200, 404) == (200, 200)` (no team page). A scratch copy that weighs only the school page failed on the budget itself: 155,156, 240,140, 327,288 and 412,392 bytes. |
| ac3: the dry run and the publish name every school-view page over the budget, in text and `--json`, and do with it what the PM ruled, by tests shown failing first | PASS | Red runs, all at assertions unless noted, and the matching green runs (each command below):<br>• `test_landscape_page_sizes.py`: **6 failed** against the empty-result skeleton; two of them as an IndexError on the empty tuple. Then **6 passed**.<br>• `test_landscape_run.py -k page`: **3 failed**, then **3 passed**.<br>• `test_landscape_command.py -k page`: **7 failed**, then **7 passed**.<br>The dry run and the publish each name all 11 of synthetic26's pages when the budget is one byte over the frame. The publish uploads the whole bundle, refuses nothing, and needs no flag. |
| ac4: the operator republishes the hspolicy26 report from the snapshot after the 2026-11-11 run, and the PM records the largest page's bytes | NOT RUN | Operator, after the merge and after the dev pilot is deployed with this task. The blocks are under **The republish (ac4)**, at the end of this report. |
| Node: `uv run pytest packages/debate_api/tests/test_landscape_pages.py packages/debate_core/tests -k school` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <the same paths> -k school -q`: **324 passed** in 23.2 s, at a load average near 97 (other work on the Mac). |

### The proposal's measurements (ac1)

The measuring harness built each option's page the way the budget test does: it served the page
through `LandscapeWorld`, then counted the response plus the script and the stylesheet. Its "today"
page reproduced the budget test's 149,208 bytes. The projection: hspolicy26's range in
`config/landscape/topics.yaml` ends 2027-06-30, so the last weekly snapshot is 2027-06-29. That is 34
snapshots after 2026-11-03 and 51 in all. At 68.1 lines a snapshot, the largest school holds 3,474
lines and the largest team 771. Rows were measured at 151 and at a linear 453.

| Option (bytes; budget 153,600) | Today | Season end, 453 rows | Season end, 151 rows |
|---|---|---|---|
| As built before this task | 149,208 | 394,570 | 310,312 |
| Team pages: the school page, link on every row | 70,290 | 157,512 | 73,254 |
| Team pages: the school page, link once per team (ruled) | 42,487 | 74,141 | 45,451 |
| Team pages: the largest team's page | 44,123 | 79,142 | 79,142 |
| One compact line per position | 137,628 | 359,830 | 275,572 |
| Compact, by tournament (3 rounds a tournament assumed) | 122,188 | 313,510 | 229,252 |
| A cap, the rest in `school_rounds.csv` | all 1,158 lines fit | 9 of 3,474 lines fit | 1,222 of 3,474 lines fit |

### The tests, and why each was red

| Test file | Red | Why |
|---|---|---|
| `packages/debate_core/tests/arguments/landscape/test_render.py` | 6 failed | The golden `schools.md` (hand-edited to the ruled shape) and five tests that pin it: the old Team page column, the bold team lines, no team list |
| `packages/debate_core/tests/arguments/landscape/test_pages.py` (new) | 4 failed, 1 passed | A `####` made school pages, no team pages, links left as text, and a stray `####` made a school. The fifth pins the old shape, which already rendered |
| Pilot: `test_landscape_pages.py`, `test_landscape_bundles.py`, the authorization matrix, `test_exposure.py`, `test_audit_record_schema.py` | 14 failed | No team route (404s), no `team` audit kind |
| `packages/debate_core/tests/application/test_landscape_page_sizes.py` (new) | 6 failed | The skeleton measured nothing |
| `test_landscape_run.py -k page` | 3 failed | `pages` empty |
| `test_landscape_command.py -k page` | 7 failed | No `pages` key, no `PAGES:` line |
| The ac2 budget test | 4 failed | As in the ac2 row above |
| `tests/docs/test_landscape_runbook_pages.py` (new), against the runbook before its edit | 4 failed | No pages counts, no names block (one ValueError on the missing block), no stop |
| `test_landscape_image.py`, against `uv.lock` before its edit | 1 failed | `debate-core` declared no markdown-it-py |

**Tests that passed on their first run, by design.** The new tests for the removal, `caselist status`,
the purge and the season window passed when written: the team pages live in `schools.md`, and these
reach it by name, with no code change. They are:

- `test_a_schools_md_holding_team_pages_goes_whole_with_every_team_page_in_it`;
- `test_a_schools_md_holding_team_pages_left_behind_is_counted_as_residue`;
- `test_the_purge_and_the_season_window_reach_the_team_pages_through_schools_md`.

They guard against a future that puts team pages in a file of their own. The scan's case is in
`test_landscape_run.py` and `test_render.py`: the schools.md that is scanned holds `#### QW` and
`#### XX`, and gives no hit. The pilot's case is in `test_landscape_bundles.py`: a deleted
`schools.md` takes the team page with it, which answers 404 with "No positions by school this week".

**The frame.** Every school-view page kind has 162-character headings in the test. The frames measured
were:

| Page kind | Frame (bytes) |
|---|---|
| Front page | 26,940 |
| School | 27,075 |
| Team | 27,831 |
| Position | 26,789 |

The largest leaves 841 bytes of the 28,672-byte allowance. The check's figure was at least the pilot's
on every page.

### Mutants

Each mutant was applied to a committed tree and run against the check's and the cut's tests. It was
then restored with `git checkout HEAD --`. No Hypothesis test is involved.

| # | Mutant | Caught by |
|---|---|---|
| 1 | Over the budget at `>` rather than `>=` | The boundary test (the page at the budget) |
| 2 | A page's bytes without the frame | The bytes test |
| 3 | The largest position page taken from any kind of page | The measure test |
| 4 | Frame allowance cut to 26 KiB | The frame test and the four budget tests (5 failed) |
| 5 | Teams not measured | The measure test |
| 6 | Front page not measured | Two tests |
| 7 | Positions not measured | The measure test |
| 8 | Characters counted, not bytes | The `Écoles é.` test (17 vs 19) |
| 9 | A team's school not recorded | The measure test |
| 10 | The run ignores its budget | Two run tests |
| 11 | `report.md` measured instead of `schools.md` | Three run tests |
| 12 | The CLI lists every page as over | Three CLI tests |
| 13 | The CLI says none is over when some are | Two CLI tests |
| 14 | The front page's body loses the schools' index | The measure test |
| 15 | The escape drops the apostrophe | **Survived** at first. Caught once a golden school, "St. Fictional's", was added; its page was written by the pre-move template |
| 16 | `####` is a school | Two tests |
| 17 | A deeper heading joins the school rather than its team | The team-body test |
| 18 | A stray `####` makes a school | The front-page test |
| 19 | Team links not rewritten | The link test |
| 20 | Anchors counted per school, not over the file | The link test (`#ab-2` and `#ab-3`) |
| 21 | `render.py` does not count the school headings | The anchor test |
| 22 | The team list leaves out a team that has rows but no line | **Survived** at first. Caught once `test_a_team_in_the_table_with_no_round_line_is_still_listed_with_its_openCaselist_link` was added |

### What I ran before this report

Run after `scripts/task sync` onto `origin/dev` at `c1d2d46`.

**The affected set.** Before the pyproject edit, `uv run --frozen scripts/affected_tests.py` chose 216
of 723 test files from 107 changed files. That is well over two minutes of tests. After the edit,
`uv run --frozen scripts/affected_tests.py --run` printed "The whole selection is affected:
packages/debate_core/pyproject.toml is shared test ground" and ran nothing. As working agreement 10
says, that run is the pull request's `ci`, which the PM's ruling (Q4) accepted.

I ran these myself, each bounded at 115 s:

| What | Result |
|---|---|
| The always-run list: `tests/architecture/`, `tests/specs/` and the CLI's `test_app.py`, `test_help_rendering.py` and `test_container_factories.py` | **378 passed** |
| `packages/debate_core/tests/arguments/landscape/`, every `application/test_landscape_*.py`, and the two school-view removal files | **1,707 passed** |
| `packages/debate_core/tests/domain/` and `application/tub/` | **1,279 passed** |
| `packages/debate_api/tests/` | **1,140 passed** |
| Every `packages/debate_cli/tests/test_landscape*.py`, and `tests/docs/` | **408 passed** |
| `tests/smoke/test_landscape_smoke.py` and `test_caselist_remove_smoke.py` | **48 passed** in 77 s |

And the whole-repo checks:

- `ruff format --check .`: 2013 files already formatted;
- `ruff check .`: all passed;
- `pyright` on the whole repository: 0 errors;
- `lint-imports`: 20 kept;
- `check_thin_handlers.py`: 73 handlers within 25 statements;
- `check_command_blocks.py --base origin/dev`, `check_links.py` and `docs_index.py --check-descriptions`:
  OK;
- `uv lock --check --offline`: resolved 151 packages;
- `validate_specs.py`: OK.

## Files changed

- **`packages/debate_core`**
  - `arguments/landscape/pages.py` (new, moved from `debate_api.landscape_markdown`): the cut and
    render; the team cut; team-link rewriting; the school view's front-page body.
  - `arguments/landscape/render.py`: the school's table without its team page column, the team list,
    and the `####` team headings, with anchors counted over the file.
  - `domain/landscape_pages.py`: `PAGE_BUDGET`, `PAGE_FRAME_ALLOWANCE`, `PageSize`,
    `SchoolViewPageSizes`, `LandscapePage.TEAM` and `LandscapeLink.TEAM_ROUNDS`.
  - `application/landscape_page_sizes.py` (new): the measurement.
  - `application/landscape_run.py`: measures every run; `pages` on the result; a test-only
    `page_budget`.
  - `pyproject.toml`: declares markdown-it-py.
- **`packages/debate_api`**
  - `landscape_markdown.py`: now only `RenderedBundle` and `render_bundle`.
  - `landscape_pages.py` and `routes.py`: the team route.
  - `templates/landscape_team.html` (new).
  - `templates/landscape_school_view.html`: its body now comes from the renderer.
  - `README.md`.
- **`packages/debate_cli`**: `commands/landscape.py` adds `pages` in `--json`, the `PAGES:` line, and
  the help text.
- **`docs/data/tub-audit-record.schema.json`**: the `team` page kind.
- **`uv.lock`**: two lines for debate-core's new dependency.
- **Tests**
  - `packages/debate_core/tests`:
    - new: `arguments/landscape/test_pages.py` and `application/test_landscape_page_sizes.py`;
    - updated: `test_render.py`, `test_landscape_run.py` and
      `caselist/test_removal_reaches_landscape_school_views.py`.
  - `packages/debate_api/tests`:
    - new: `test_landscape_pages_golden.py` with `fixtures/landscape_pages_golden/`;
    - updated: `test_landscape_pages.py`, `test_landscape_bundles.py`,
      `test_auth_authorization_matrix.py`, `test_exposure.py`, `test_audit_record_schema.py`,
      `test_landscape_image.py`, and `fixtures/landscape/` (EF's team page and its README line).
  - `packages/debate_cli/tests/test_landscape_command.py`.
  - `tests/fixtures/landscape/golden/schools.md`: hand-edited to the ruled shape.
  - `tests/docs/`: `test_annual_purge_runbook.py`, and the new `test_landscape_runbook_pages.py`.
  - `tests/smoke/`: `test_landscape_smoke.py` and `README.md`.
- **Docs**
  - `docs/runbooks/landscape-report-from-the-cloud-run.md`: steps 3 and 4 print the pages counts;
    step 3 stops on a page over the budget; a terminal-only block reads the names.
  - `docs/guides/landscape-taxonomy.md`: the Round by round paragraph, and a page-budget paragraph.

## Deviations from the spec

1. **Files outside `constraints.packages`.** The ruling's own requirements live in four places the
   spec doesn't list:
   - `tests/docs/`: the purge's and the season window's test, and the runbook test;
   - `docs/data/tub-audit-record.schema.json`: the audit record's `team` kind (Q1);
   - `packages/debate_core/pyproject.toml` and `uv.lock`: the dependency (Q4).
2. **The spec's description still says "a school page over it is named".** The PM's ruling (Q3)
   extends the check to every school-view page and records the largest position page. I built the
   ruling. The spec's text is the PM's to amend.

## Decisions and assumptions

**The team pages and their links**

- **A team's heading** is its team code alone: `#### QX`. Its page's address is that heading's anchor
  inside its school, `/landscape/<caselist>/schools/<school>/qx`. The page's title names both the team
  and the school.
- **The "round by round" link** in `schools.md` is `#<anchor>`. The anchor follows the domain's
  `Anchors` rule, counted over every heading of the file in order, where a repeat gets `-2`, as the
  pilot numbers repeats (the PM's ruling of 2026-10-26).
  - The pilot rewrites a link to one of this school's team anchors into that team's page address. A
    link to another school's team stays text.
  - On this Mac, a Markdown viewer that numbers repeats from `-1` (GitHub's rule) sends a repeated
    team code to another school's team of the same code. The pilot is exact.
- **The team list item** reads `- QX: [round by round](#qx), [openCaselist](<url>)`, or `…, no
  openCaselist page`. Order:
  - teams with round lines first, in the lines' order;
  - then any team with table rows but no line. Under the counts' rule there is none, but the list is
    now the only place its openCaselist link could appear.
- **Deeper headings and strays.** A heading deeper than `####` stays on its team's page. A `####`
  before any school has no page, and shows on the front page.
- **Older `schools.md` files** (no `####`) render exactly as before; the goldens hold that. So the new
  pilot serves last week's bundles unchanged. The reverse doesn't hold: see the deploy order.

**How the check measures**

- **The front page's index lists** were written by the template. They are now produced by `pages.py`,
  so the check can measure the front page as sent. The escaping is MarkupSafe's (`&#34;`, `&#39;`) and
  the quoting is Jinja's `urlencode`. The goldens for both, written by the old template, are byte for
  byte equal, apostrophe included.
- **Over the budget means a page reaching it** (`>=`), because the budget test holds a page under it
  (`<`).
- **Over-budget page names stay in the terminal.** `--json`'s `over_budget` names each page's heading
  and school. The runbook's success lines print counts and bytes only, and a separate terminal-only
  block reads the names, as with scan hits.
- **The run's `page_budget`** exists only for tests. It defaults to ADR-0019's figure, which is
  unchanged. The CLI tests patch the run module's `PAGE_BUDGET` instead.

**The tests and fixtures**

- **The goldens are characterisation, not expectations** (working agreement 6 allows this for churn;
  the acceptance rests on the hand-written tests). Whenever a golden had to prove equality with the
  old code, it was written by the old code:
  - every page at the commit before the move;
  - the flat view and "St. Fictional's" by the template and renderer of the team-pages commit, which
    was `1ade57e` before the sync and is `bac873d` now.

  `LANDSCAPE_PAGES_GOLDEN_WRITE=1` rewrites them, and that run always fails.
- **The synthetic round line** in the ac2 test has one word more in its tournament ("Invented Open")
  than t54's. That makes the team page at least v1-e32-t54's real 69.4 bytes a line; without it the
  line was 68.3. The rows use invented position ids longer than real ones. So the synthetic pages are
  no smaller than real ones of the same counts.
- **t54's budget test** stays as it was. It still serves the old-shape page with the report parts and
  the largest position page.

**The dependency**

- markdown-it-py is declared `>=4.0`, as `debate_api` declares it, and the lock still holds 4.2.0.
- `uv lock --offline` could not resolve: fastapi isn't in uv's cache. So I added the two lines to
  `debate-core`'s entry in `uv.lock` by hand, and `uv lock --check --offline` accepts the result.
- No licence check runs in `scripts/` or `.github/workflows/`. markdown-it-py is MIT.
- `debate_api` keeps its own declaration, though it no longer imports the library directly
  (Follow-up work).

## Operator follow-ups

1. **After the merge, before the republish: deploy the dev pilot carrying this task.** A pilot older
   than this task cuts every `####` of the new `schools.md` into a "school", so its front page would
   list every team as a school. Two blocks from the main clone, on `dev`: the deploy's dry run (it
   builds the image and makes no AWS call), then the deploy. Each refuses a set `DEBATE_` variable, a
   running caselist pull, a clone not on `dev` and a clone without this task.

   **Operator command** (expected runtime ~3 min; builds the image, deploys nothing)
   Where: your Mac, in a new terminal window, after this task has merged into `dev`
   ```bash
   MAIN="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence"
   cd "$MAIN" || echo "STOP: no clone at ${MAIN}"
   if [ "$(git -C "$MAIN" branch --show-current)" != dev ]; then echo "STOP: ${MAIN} is not on dev"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell; open a new window"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; else git -C "$MAIN" pull --ff-only && git -C "$MAIN" grep -c 'def landscape_team' HEAD -- packages/debate_api/src/debate_api/landscape_pages.py && scripts/tub_deploy.sh dev --dry-run 2>&1 | tail -4; fi
   ```
   Success looks like the pull's summary, a count of `1` (the clone carries this task), and the dry
   run's end without an error. A `0` stops: the merge isn't in the clone.

   **Operator command** (expected runtime ~3 min; deploys the pilot to dev)
   Where: your Mac, in the same window, after the dry run above succeeded
   ```bash
   cd "$MAIN"
   if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell; open a new window"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ "$(git -C "$MAIN" grep -c 'def landscape_team' HEAD -- packages/debate_api/src/debate_api/landscape_pages.py)" != 1 ]; then echo "STOP: ${MAIN} does not carry v1-e32-t57"; else aws sso login --sso-session debate && scripts/tub_deploy.sh dev 2>&1 | tail -5; fi
   ```
   Success looks like `{"status":"ok"}`, then `Deployed <sha> to dev`, where `<sha>` is the clone's
   `git rev-parse --short HEAD`.

2. **ac4: the republish**, below, after the 2026-11-11 cloud run (a Wednesday): Thursday 2026-11-12 or
   later.

## Follow-up work

- **`debate_api`'s own markdown-it-py declaration** is now redundant, since the image gets the package
  through `debate-core`. `test_landscape_image.py` still pins it. Removing both is a small upkeep task
  (E41).
- **The frame allowance's room.** With 162-character headings, the largest frame is 27,831 of 28,672
  bytes. When the site's script or stylesheet grows by more than about 800 bytes, the frame test fails
  first, and the allowance is raised in that pull request. The PM may want that rule written into
  ADR-0019's notes.
- **Position pages' growth** is on record weekly (`largest_position_page`) but not projected. If a
  position read by most of the circuit's teams nears the budget, the check names it; a split of
  position pages would be its own task.
- **The spec's text** (Deviation 2).

## The republish (ac4), after the merge

These are steps 1 to 4 of
[landscape-report-from-the-cloud-run.md](../runbooks/landscape-report-from-the-cloud-run.md), run
from the main clone on `dev` with `uv run`, over a copy restored for this republish. Run every block
in one terminal window. Step 5, deleting the copy, follows the runbook as the PM directs. Every block
refuses a Wednesday, a set `DEBATE_` variable and a running caselist pull.

**Operator command** (expected runtime a few seconds; pulls the main clone on `dev` and checks it)
Where: your Mac, in a new terminal window, on Thursday 2026-11-12 or later, after the deploy above
```bash
CASELIST=hspolicy26
COPY="$HOME/.debate-research/landscape-copy-${CASELIST}"
MAIN="$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence"
CFG="$MAIN/config/landscape"
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif [ "$(git -C "$MAIN" branch --show-current)" != dev ]; then echo "STOP: ${MAIN} is not on dev"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ -e "$COPY" ]; then echo "STOP: ${COPY} exists already; delete it with the runbook's step 5 first"; else git -C "$MAIN" pull --ff-only && git -C "$MAIN" grep -c measure_school_view HEAD -- packages/debate_core/src/debate_core/application/landscape_run.py; grep -c -E "caselist: ${CASELIST}\$" "$CFG/topics.yaml"; date +%A; df -g "$HOME" | awk 'NR == 2 { print $4 " GB free" }'; fi
```
Success looks like:

- the pull's summary;
- a count of 2 (the clone carries this task's check);
- a count of `1` (the topic);
- a day that is not Wednesday;
- 15 GB free or more.

**Operator command** (expected runtime ~3 to 10 min; step 1, restores the copy with its raw sources under the dev run lock)
Where: your Mac, in the same window
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ -e "$COPY" ]; then echo "STOP: ${COPY} exists already"; else aws sso login --profile debate-dev-evidence && cd "$MAIN" && caffeinate -i env DEBATE_ENV=dev uv run debate-research --json caselist restore-run-state --into "$COPY" --caselist "$CASELIST" --with-sources > /tmp/landscape-restore.json; echo "exit $?"; grep -oE '"(manifests|parsed_version|parsed_objects|named|fetched|fetched_bytes|suppressed)": ("[^"]*"|[0-9]+)|"code": "[A-Z_]+"' /tmp/landscape-restore.json; fi
```
Success looks like:

- `exit 0`;
- `"parsed_version": "2026.11.03-docx-9"`, this build's, unless a later parser bump merged first;
- `"fetched"` equal to `"named"` less `"suppressed"`, and above zero.

`RUN_LOCK_HELD` means the cloud run still holds the lock: wait for it to record, then run the block
again. Any other stop: see the runbook's step 1.

**Operator command** (expected runtime under a minute; step 2's dry run, writes nothing)
Where: your Mac, in the same window
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else cd "$MAIN" && env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" uv run debate-research --json caselist parse --caselist "$CASELIST" --dry-run > /tmp/landscape-parse-dry-run.json; echo "exit $?"; grep -oE '"(version|parser_version|sources|skipped|suppressed|to_parse)": ("[^"]*"|[0-9]+)|"code": "[A-Z_]+"' /tmp/landscape-parse-dry-run.json; fi
```
Success looks like `exit 0`, the parser version step 1 printed, and `"sources"` above zero. A
`"to_parse"` of `0` means the copy is parsed already: go to step 3.

**Operator command** (expected runtime ~16 to 20 min from nothing, much less when step 1 restored a parsed directory; step 2, parses into the copy)
Where: your Mac, in the same window
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ ! -d "$COPY" ]; then echo "STOP: no copy at ${COPY}"; else cd "$MAIN" && caffeinate -i env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$COPY" uv run debate-research --json caselist parse --caselist "$CASELIST" > /tmp/landscape-parse.json; echo "exit $?"; grep -oE '"(version|attempted|parsed|cards|failure_rate|threshold_exceeded|elapsed_seconds)": ("[^"]*"|[0-9.]+|true|false)|"code": "[A-Z_]+"' /tmp/landscape-parse.json; fi
```
Success looks like `exit 0`, `"parsed"` and `"cards"` above zero, and `"threshold_exceeded": false`.

**Operator command** (expected runtime ~5 to 12 min; step 3, the dry run, with the pages counts)
Where: your Mac, in the same window
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ ! -f "$COPY/debate-research-restored-copy.json" ]; then echo "STOP: ${COPY} holds no debate-research-restored-copy.json"; elif [ ! -f "$CFG/topics.yaml" ]; then echo "STOP: no topics.yaml in ${CFG}"; else aws sso login --profile debate-dev-evidence && cd "$MAIN" && caffeinate -i env DEBATE_ENV=dev uv run debate-research --json landscape report --caselist "$CASELIST" --restored-copy "$COPY" --config-dir "$CFG" --model-mode none --publish --dry-run > /tmp/landscape-dry-run.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; c = d.get("counts") or {}; m = (d.get("classification") or {}).get("model") or {}; s = d.get("scan") or {}; p = d.get("pages") or {}; print("code", (e.get("error") or {}).get("code")); print("snapshot", d.get("snapshot"), "parsed_version", d.get("parsed_version"), "stale", (d.get("staleness") or {}).get("stale")); print("sources", c.get("sources"), "cards", c.get("cards"), "counted", c.get("cards_counted"), "positions", c.get("positions")); print("would_ask", m.get("would_ask"), "held_back", m.get("held_back"), "model_calls", d.get("model_calls")); print("scan_hits", len(s.get("hits") or []), "not_yet_accepted", s.get("not_yet_accepted"), "digest", s.get("digest")); print("planned", [one["action"] for one in (d.get("publish") or {}).get("planned") or []]); print("school_view", d.get("school_view")); print("pages_checked", p.get("checked"), "pages_over_budget", len(p.get("over_budget") or []), "largest_page", (p.get("largest") or {}).get("kind"), (p.get("largest") or {}).get("bytes"), "largest_position_page", (p.get("largest_position") or {}).get("bytes"), "budget", p.get("budget"))' /tmp/landscape-dry-run.json; fi
```
Success looks like:

- `exit 0` and `code None`;
- `snapshot 2026-11-10` (the week the 2026-11-11 run pulled) and `stale False`;
- `would_ask 0` and `model_calls 0`;
- `not_yet_accepted 0`;
- `planned` with eight entries, all `UPLOAD` (a week not published before);
- `school_view` with its counts;
- `pages_checked` above zero and `pages_over_budget 0`;
- `largest_page` and `largest_position_page` with their bytes, and `budget 153600`.

**Send the PM these lines.** They hold counts and bytes only. **Stop** on:

- `PARSED_VERSION_NOT_IN_STORE`;
- `stale True`;
- `not_yet_accepted` above zero (the runbook's step 3 reading block; those lines stay in the
  terminal);
- `pages_over_budget` above zero. Don't publish until the PM says. The pages' names are for this
  terminal only, from the next block.

**Operator command** (expected runtime a second; only when `pages_over_budget` is above zero, for this terminal only)
Where: your Mac, in the same window
```bash
python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; [print(p["kind"], p["school"] or "", p["page"], p["bytes"]) for p in (d.get("pages") or {}).get("over_budget") or []]' /tmp/landscape-dry-run.json
```
It prints each page over the budget: its kind, a team's school, its heading and its bytes. Tell the PM
the kinds and the bytes only.

**Operator command** (expected runtime a few minutes; step 4, publishes to the dev bucket under the run lock)
Where: your Mac, in the same window, after the PM has read the dry run's lines
```bash
if [ "$(date +%u)" = 3 ]; then echo "STOP: it is Wednesday, the cloud run's day"; elif env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; elif pgrep -fl 'debate-research( --json)? caselist pull'; then echo "STOP: a caselist pull is running (above)"; elif [ ! -f "$COPY/debate-research-restored-copy.json" ]; then echo "STOP: ${COPY} holds no debate-research-restored-copy.json"; elif [ ! -f "$CFG/topics.yaml" ]; then echo "STOP: no topics.yaml in ${CFG}"; else aws sso login --profile debate-dev-evidence && cd "$MAIN" && caffeinate -i env DEBATE_ENV=dev uv run debate-research --json landscape report --caselist "$CASELIST" --restored-copy "$COPY" --config-dir "$CFG" --model-mode none --publish > /tmp/landscape-publish.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); d = e.get("data") or (e.get("error") or {}).get("details") or {}; p = d.get("publish") or {}; g = d.get("pages") or {}; print("code", (e.get("error") or {}).get("code")); print("snapshot", d.get("snapshot"), "model_calls", d.get("model_calls"), "cards", (d.get("counts") or {}).get("cards")); print("uploaded", len(p.get("uploaded") or []), "unchanged", len(p.get("unchanged") or []), "refused", p.get("refused")); print("pages_over_budget", len(g.get("over_budget") or []), "largest_page", (g.get("largest") or {}).get("kind"), (g.get("largest") or {}).get("bytes"), "largest_position_page", (g.get("largest_position") or {}).get("bytes"))' /tmp/landscape-publish.json; fi
```
Success looks like:

- `exit 0` and `code None`;
- the dry run's `snapshot` and `cards`;
- `model_calls 0`;
- `uploaded 8 unchanged 0 refused None`;
- the dry run's `pages_over_budget`, `largest_page` and `largest_position_page`.

Send the PM the last line: it records the largest page's bytes (ac4). `RUN_LOCK_HELD` means a run holds
the lock: wait, then run the block again. A scan refusal is the runbook's step 4 digest block. Then
step 5 of the runbook deletes the copy and this runbook's files under `/tmp`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-07

**Notes:**

Built to the ruling, and measured where it matters: the largest school page goes from 149 KB to about
42 KB, and the season's projected sizes hold under the budget for both the school and the team page.

1. **ac1 passes.** The proposal was measured and ruled before any code, and nothing was committed in
   between.
2. **ac2 passes.** Four sizes (151 and 453 rows, 1,158 and 3,474 lines; teams of 257 and 771). Red
   against the old renderer was 4 failed at the missing team page. The synthetic round line was made no
   cheaper than the real 69.4 bytes, which is the detail that makes this test honest.
3. **ac3 passes.** The check names every over-budget page in the dry run and the publish, and refuses
   nothing, as ruled. The runbook's step 3 stops on `pages_over_budget` above 0, with names read in the
   terminal only. Red runs 6, 3 and 7 failed, then green.
4. **The move is proven byte-identical.** The goldens were written by the old code before the move, and
   the old template wrote the apostrophe golden that caught mutant 15. All 22 mutants are caught, and the
   two that first survived each got their test.
5. **Deviations accepted.** The four places outside the packages are where the ruling's requirements
   live. The spec's description is amended by the PM in the next batch. The hand-edited `uv.lock`: if
   `ci`'s locked sync refuses it, the operator runs `uv lock` on the Mac with the network and the PR
   takes the result.
6. **Decisions accepted.**
   - A team heading is the team code, with anchors counted over the file as the pilot numbers them.
   - Teams with no round line are still listed, so their openCaselist link is not lost.
   - Older `schools.md` files render as before.
   - Over budget means reaching it (`>=`).
7. **The deploy order, settled with dev's parser plan.** A dev pilot deployed from `dev` now would also
   carry docx-9 and turn Download off until the 2026-11-11 index. So the dev pilot is deployed once, on
   Thursday 2026-11-12, after that run records its docx-9 index. That single deploy carries both docx-9
   (v1-e40-t16's ruling) and this task. The republish (ac4) follows the deploy. No bundle with team
   headings is published before then, and the weekly run publishes no landscape bundle.
8. **Follow-ups, which the PM files or writes in the next batch:**
   - `debate_api`'s redundant markdown-it-py declaration (E41, p3);
   - the frame allowance's rule (raise it in the pull request whose script or stylesheet passes it),
     written as a PM note in ADR-0019;
   - position-page growth stays recorded weekly, with a split as its own task if the check ever names
     one.
9. **Merge:** `scripts/task pr --partial` once `ci` (the whole selection) is green. The Goal stays
   `InProgress` until ac4 is recorded.
