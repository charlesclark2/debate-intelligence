# Session report: v1-e32-t23-school-page-team-links

| | |
|---|---|
| Task | `v1-e32-t23-school-page-team-links` — Team links on a school's page, as on a position's |
| Spec | [`plan_specs/v1/e32-argument-landscape/t23-school-page-team-links.yaml`](../../plan_specs/v1/e32-argument-landscape/t23-school-page-team-links.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t23-school-page-team-links` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`schools.md`'s by-school table now has the same **Team page** column as the by-position tables. It
uses the same rule (`SchoolView.team_page`) and the same cell (`[openCaselist](…)`, or `none`), so a
team's cell is the same in both tables. This is a three-line change to `render_schools_markdown`.

* **The golden file was changed by hand first.** The golden `schools.md` and the new tests were
  committed red (`a9cd37b`) before the renderer changed.
* **The pilot needed no code change.** `landscape_markdown._schools` already renders each school's
  page with `team_pages=True`, so `landscape_link` checks those links and opens them in a new tab, as
  it does on a position page. A new pilot test over the synthetic bundle shows this, as does an
  extended test in which a link the rule would not build stays text on a school page.
* **The Goal stays `InProgress`.** ac3, the operator's republish of hspolicy26 after the cutover's
  seed, is NOT RUN: no dev bucket write is allowed before the seed. Its operator blocks are below.
  This PR merges `--partial`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `school-page-team-links` (School page team links) | Code and tests done; republish waits for the seed | The node's criterion (landscape tests) passes. The republish in its description is ac3, an operator step after `v1-e40-t06`'s seed. The Plan status is left as it was. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — On the synthetic fixture, the by-school table has a team page column whose cell for each team matches the by-position tables (`none` where the rule gives no link), matching hand-written golden files, with the tests shown failing first | PASS | **Red** at `a9cd37b`, with the golden and the tests changed and the renderer not yet changed: `.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape/test_render.py packages/debate_api/tests/test_landscape_pages.py -p no:randomly -n 0` → `6 failed, 185 passed`. The failures were `test_rendering_the_fixture_matches_the_golden_file[schools.md]` (the diff begins at `- \| Rounds \| Team page \|`), `test_the_school_view_carries_no_debater_name_tag_cite_or_path` (it compares against the same golden file), `test_a_team_code_that_is_not_one_address_word_gets_no_link_and_is_counted`, `test_a_team_reads_the_same_team_page_by_school_as_by_position` (by-school cells read `{'1'}` and `{'2'}`, the rounds column, where by-position cells read `{'none'}` and `[openCaselist](…)`), and the pilot test for both members (see ac2). **Green** after `e8ce35d`: `uv run pytest packages/debate_core/tests/arguments/landscape` → `773 passed in 28.76s`. |
| ac2 — The pilot renders the by-school table's team links as checked team pages that open in a new tab, by a test over a synthetic bundle | PASS | `test_a_school_page_links_each_team_page_in_a_new_tab_and_shows_none_as_text` (student and coach). It was red at `a9cd37b`: the Ashgrove page held only its back link. It is green after the synthetic bundle `synthpolicy26/2026-10-20/schools.md` got the column, with no pilot code change. `test_a_team_page_link_the_rule_would_not_build_is_text_in_the_school_view` now also checks a school page: a link to another caselist, or with a deeper path, is shown as text, and the real link is kept. `.venv/bin/python -m pytest packages/debate_api/tests/test_landscape_pages.py packages/debate_api/tests/test_landscape_bundles.py packages/debate_core/tests/application/test_landscape_run.py -p no:randomly` → `212 passed in 5.16s`. |
| ac3 — After the seed, the operator republishes hspolicy26 to dev and the pilot's school page shows the links | NOT RUN | This is an operator step after `v1-e40-t06`'s seed. The spec forbids any dev bucket write before the seed. See [Operator follow-ups](#operator-follow-ups). |
| Node criterion: Landscape tests pass (`uv run pytest packages/debate_core/tests/arguments/landscape`) | PASS | `773 passed in 28.76s` |

**Mutants** (4, each run against the committed tree and restored with `git checkout`; none uses
Hypothesis):

| Mutant | Tests run | Result |
|---|---|---|
| By-school cell always `_team_page_cell(None)` | `test_render.py` | caught, 4 failed |
| By-school header and divider back to four columns, cells kept | `test_render.py` | caught, 2 failed (the golden file and the no-debater test that compares against it) |
| By-school cell built from the school's first row instead of its own row | `test_render.py` | caught, 4 failed |
| Pilot school pages rendered with `team_pages=False` | `test_landscape_pages.py`, `test_landscape_bundles.py` | caught, 4 failed |

**Before the report** (agreement 10):

* **The affected set** is 220 files (`uv run scripts/affected_tests.py`). Run with CI's markers, the
  alarm on the interpreter, it took more than two minutes:
  `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" <the 220 files>`.
  It was stopped at 115 s, 90% through, with 5,832 passed and no failure or error. No worker was
  left running. The whole set is left to the PR's `ci`.
* **Within two minutes I ran** the changed test files and their directories, the always-run list and
  the docs checks: `tests/architecture tests/specs packages/debate_cli/tests/test_app.py
  packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py
  tests/scripts/test_docs_index.py packages/debate_core/tests/arguments/landscape
  packages/debate_api/tests/test_landscape_pages.py packages/debate_api/tests/test_landscape_bundles.py
  packages/debate_core/tests/application/test_landscape_run.py packages/debate_cli/tests/test_landscape_command.py`
  → `1530 passed in 21.01s`.
* **The whole-repo checks:**
  * `uv run ruff format --check .` → `1385 files already formatted`
  * `uv run ruff check .` → `All checks passed!`
  * `pyright packages/debate_core packages/debate_api` → `0 errors, 0 warnings, 0 informations`
  * `uv run lint-imports` → `Contracts: 18 kept, 0 broken.`
  * `uv run scripts/check_thin_handlers.py` → `OK: 61 CLI command and API route handlers within 25 statements`
  * `uv run scripts/check_command_blocks.py` → `OK: no # comments in 486 shell code blocks in 165 Markdown files`
  * `uv run scripts/docs_index.py --check-descriptions` → `All 49 indexed documents under docs/ have a description`
  * `uv run scripts/validate_specs.py` → `OK: 464 files, 40 epics, 402 tasks, 22 releases`

## Files changed

* **`debate_core.arguments.landscape.render`**: the by-school table's header, divider and rows gain
  the Team page column through `_team_page_cell(view.team_page(row))`. The module docstring says
  that both of schools.md's lists carry the link.
* **`tests/fixtures/landscape/golden/schools.md`**: changed by hand. Every by-school row gets a cell:
  Birchmoor's QQ and ZZ link to their pages, and the other six team codes read `none`, as they do in
  the by-position tables.
* **`packages/debate_core/tests`**:
  * `test_render.py`: a new test that every team's cell is the same in both sections (8 teams, 6
    `none`), and the not-one-address-word test now also checks the by-school rows;
  * `test_landscape_run.py`: its school-view assertion now pins the whole row, ending `| 1 | none |`.
    The old four-cell string was still a substring of the new row, so it no longer pinned the row.
* **`packages/debate_api/tests`**:
  * the synthetic bundle `synthpolicy26/2026-10-20/schools.md` gets the column, written by hand, and
    the fixtures' README says so;
  * `test_landscape_pages.py`: the new school page test, and the page-budget test's school pages
    shaped like hspolicy26's now have a link on every row. The test checks that the largest school
    page shows 117 new-tab links. That page, with its script and stylesheet, weighed 57,903 bytes
    against the budget of 153,600, measured once with a print that was then removed;
  * `test_landscape_bundles.py`: the planted school view's by-school table carries a bad link and a
    real one.
* **`docs/guides/landscape-taxonomy.md`**: both lists carry the link, in a Team page column that
  reads the same for a team in either list.

## Deviations from the spec

None.

## Decisions and assumptions

1. **The older synthetic bundle keeps the old shape.** `synthpolicy26/2026-10-13/schools.md` is the
   bundle that must never be shown, so its by-school table is left as it was before this task. That
   is also what a bundle published before this change looks like.
2. **No lead paragraph for the by-school section.** The page's opening paragraph already says it
   links each team's openCaselist page, and the by-position lead explains when a link is given. The
   brief asked for the column only.
3. **Smoke checks are unchanged.** `tests/smoke/test_landscape_smoke.py` checks that `schools.md` is
   written and how it is marked, not what it contains. `tests/smoke` is also outside this task's
   packages. The change is inside a file the smoke check already covers.
4. **No pilot code change, and no deploy.** The pilot renders whatever `schools.md` the bucket holds,
   so after the republish the links show within the shelf's five-minute refresh, on the image that
   is already deployed.

## Operator follow-ups

**ac3: republish hspolicy26 to dev after the cutover's seed** (`v1-e40-t06`, step 3 of
`docs/runbooks/caselist-cutover.md`). Do not run this before the seed. Until then a bucket-mode
checkout refuses the publish with `RUN_STATE_NOT_SEEDED`, and getting past that would write to dev
outside the lock. In bucket mode `landscape report --publish` takes the run lock (ADR-0020, amended
2026-10-24), so do not run it while a cloud run is going. The sequence is the first dev run's
(`docs/data/landscape/first-run-policy.md`, "The first dev run"): a dry run, then the publish.

**Operator command** (expected runtime ~2 min, most of it the report's build)
Where: the `dev-preview` worktree, after this task has merged into `dev` and the seed is done
```bash
cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview"
git fetch origin
git switch --detach origin/dev
grep -q 'Position | Rounds | Team page |' packages/debate_core/src/debate_core/arguments/landscape/render.py && echo "ok: v1-e32-t23 merged at $(git rev-parse --short HEAD)" || echo "STOP: origin/dev has no v1-e32-t23"
aws sso login --profile debate-dev-evidence
if env | grep -q '^DEBATE_'; then
  echo "STOP: unset these first: $(env | grep -o '^DEBATE_[A-Za-z_]*' | tr '\n' ' ')"
elif pgrep -f "caselist pull" > /dev/null; then
  echo "STOP: a caselist pull is running"
else
  uv run debate-research landscape report --caselist hspolicy26 --publish --dry-run
fi
```

What to read before going on:

* The first line must be `ok: v1-e32-t23 merged at <commit>`. Stop on any `STOP` line.
* The dry run names hspolicy26's newest snapshot, 2026-10-20 or later, and its counts. Positions
  read must be above zero, and planned uploads must be above zero.
* If it says the scan held the publish back (exit 1), read its hits with the PM, as on 2026-10-24.
  Once they are accepted, copy the digest it printed into the next block. Stop if a hit names a team.
* Stop if the dry run is refused because the run lock is held or the bucket is not seeded.

**Operator command** (expected runtime ~2 min)
Where: the `dev-preview` worktree, straight after the dry run. Replace `DIGEST_FROM_THE_DRY_RUN`
with the digest the dry run printed. If the dry run reported no scan hits, delete
`--accept-scan-hits DIGEST_FROM_THE_DRY_RUN`. Pasted as it is, the placeholder is refused and
nothing is published.
```bash
cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview"
if env | grep -q '^DEBATE_'; then
  echo "STOP: unset these first: $(env | grep -o '^DEBATE_[A-Za-z_]*' | tr '\n' ' ')"
elif pgrep -f "caselist pull" > /dev/null; then
  echo "STOP: a caselist pull is running"
else
  uv run debate-research landscape report --caselist hspolicy26 --publish --accept-scan-hits DIGEST_FROM_THE_DRY_RUN
fi
```

Success looks like `Uploaded N, unchanged M` to `reports/landscape/hspolicy26/<snapshot>/`. N is at
least 1, because `schools.md` changed, and N plus M equals the dry run's planned uploads, which are
above zero.

**The pilot check.** Wait at least five minutes after the upload, then sign in at
<https://tub.dev.wfbdebate.com/landscape/hspolicy26/schools> and open any school. Its table has a
**Team page** column: each linked cell reads "openCaselist (opens in a new tab)", and a team with no
link reads `none`. Open one link and check that it lands on that team's openCaselist page in a new
tab. Then open one of that team's positions from the front page and check that the team's cell reads
the same there. Paste the upload line and what the page showed back into the session or the PR.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
