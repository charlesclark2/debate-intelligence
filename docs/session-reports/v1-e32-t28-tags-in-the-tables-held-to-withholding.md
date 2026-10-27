# Session report: v1-e32-t28-tags-in-the-tables-held-to-withholding

| | |
|---|---|
| Task | `v1-e32-t28-tags-in-the-tables-held-to-withholding` — Tags quoted in the impact and link-chain tables, held to the report's withholding, counted first |
| Spec | [`plan_specs/v1/e32-argument-landscape/t28-tags-in-the-tables-held-to-withholding.yaml`](../../plan_specs/v1/e32-argument-landscape/t28-tags-in-the-tables-held-to-withholding.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t28-tags-in-the-tables-held-to-withholding` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Built as the PM ruled (option (b), 2026-10-27). The Goal is `Succeeded`.**

The task ran in two sessions.
* **The first** took ac1's counts and stopped at the PM's stop condition (a): withholding every caselist
  word would have blanked 105 of top_cards.csv's 364 tags (28.8%). Its counts are
  [below](#the-counts-ac1), unchanged.
* **The PM's ruling (b):** withhold school words and team codes, and no tournament word, everywhere the
  report withholds a tag.
* **This session** built it.

**One rule, in one place.** `caselist_words` (`debate_core/arguments/landscape/link_chains.py`) is now
every word of a caselist school over three characters, and every team code. Its docstring names the
rule and the ruling.

The report builds the set once and hands it to every caller of `is_withheld`:
* scenario names;
* t25's lines under "What each impact runs through";
* the three tables: the impact table with impact_cards.csv, the link-chain table, and top_cards.csv.

**What a withheld tag looks like in a table:**
* Its cell is left empty.
* The row stays, with its rank, teams, cite and source.
* report.md's header gains one line, **Tags left empty**, which counts the cells per table and says
  why no tournament word is withheld.

**hspolicy26 after the build:** 2 / 2 / 18 tags left empty, as the PM expected:

| Table | Tags left empty |
|---|---|
| Impact table | 2 of 87 (2.3%) |
| Link-chain table | 2 of 96 (2.1%) |
| top_cards.csv | 18 of 364 (4.9%) |

**t25's lines under the narrower words.** Every withheld or left-out count fell or stayed; none rose
([below](#t25s-lines-under-the-narrower-words)). Some "rows named by" counts rose: these are rows that a
withheld text had pushed down the order, now named again.

**Tests:**
* The goldens were written by hand before the code and run red against a do-nothing skeleton: 30 failed.
* The PM's four mutants and six more were all caught.
* The PM should look at one consequence: the scan before sharing's tests used to plant a team code in a
  tag. The report now withholds that tag before the scan sees it, so the tests plant a tournament's name
  instead ([decisions](#decisions-and-assumptions)). One of those tests is in `packages/debate_cli/tests`,
  outside the spec's packages: see [Deviations](#deviations-from-the-spec).

## t25's lines under the narrower words

The PM asked for this count before the build, counts only, with a stop if any count rose. It is
hspolicy26 through 2026-10-20, taxonomy 1.4.0.
* **How it ran:** `LandscapeReportService` was built twice from one read-only reading, on the code as it
  stood (`9d74bfe`):
  * once with every caselist word (937 words);
  * once with the report's `caselist_words` replaced by the narrower rule: school words and team codes,
    726 words, all among the 937.
* **Runtime:** 54.0 s under a 115 s alarm.
* **The store:** `debate.sqlite3`'s SHA-256 was the same before and after, no `DEBATE_` variable was
  set, and no process outlived the run.
* **Rows:** both builds have the same rows: 87 impact, 96 link-chain and 368 top_cards.csv rows.

| Per kind (advantage / DA) | Every caselist word | School words and team codes |
|---|---|---|
| Scenario names withheld | 1 / 0 | **0** / 0 |
| Unlisted scenario words withheld (dry run only) | 1 / 2 | **0 / 0** |
| Tags withheld (t25's "Tags withheld" line) | 4 / 2 | **2 / 0** |
| Ranks left out | 2 / 1 | **1 / 0** |
| Ranks named by a scenario | 0 / 9 | 0 / 9 |
| … by an internal link | 0 / 4 | 0 / 4 |
| … by a link | 0 / 12 | 0 / 13 |
| … by the impact card's tag | 39 / 18 | 41 / 18 |
| … by the card above it | 2 / 0 | 1 / 0 |
| Rows with a card above that holds no withheld word | 24 / 10 | 30 / 10 |
| Rows with a link that holds no withheld word (both kinds) | 23 | 24 |

**Reading the stop condition.** I read "if any count rises" as the counts of what is withheld or left
out: names withheld, tags withheld and ranks left out. All of those fall or stay. Some rows-named-by
counts rise, for two reasons:
* A narrower word set hands a row back to an earlier source. One advantage rank's own tag held only a
  tournament word, so it now names the rank instead of the card above.
* A rank left out comes back. 3 ranks were left out; now 1 is.

Those rises are the other side of the falls, not a new withholding, so I did not stop. If the PM meant
every count, these rises are the ones to look at.

## The build (ac2)

| Where | What changed |
|---|---|
| `arguments/landscape/link_chains.py` | `caselist_words`: school words over three characters and team codes, no tournament word. Its docstring names the rule, the ruling and the places that read it. `is_withheld` and the module's text follow. |
| `application/landscape_report.py` | The set is built once in `build` and given to `_LinkChains`, which no longer builds its own. `_without_withheld_tags` leaves out each table row's tag that holds a word, keeps the row and counts it. It runs on the impact rows **after** `with_lead_in`, so t25 still passes over a withheld own tag and counts it. The module docstring gains "Tags in the tables". |
| `domain/landscape_report.py` | `TableTagsWithheld(impact_cards, chain_cards, top_cards)`, carried as `LandscapeReport.table_tags_withheld`. Every field defaults to 0. |
| `arguments/landscape/render.py` | The header line **Tags left empty**, with the three counts. The rule's words in t25's header line and in the per-kind lines read "a caselist school or team code". The module docstring says a withheld tag is an empty cell. |
| `scripts/landscape_table_tag_words.py` | Reads each row's tag **as parsed**, from the card the row shows, so it still counts by kind after the report withholds. Each line adds how many of those tags the report withheld. It refuses (`ValueError`) a report that withheld other tags than the rule's. |
| `docs/guides/landscape-taxonomy.md` | Under "How report.md is laid out": **What the tables withhold**. The two older sentences that named a tournament's words are corrected. |

The line in report.md, on the synthetic caselist read unchanged:

> * **Tags left empty**: a tag holding a word of a caselist school or team code is withheld wherever the
>   report quotes one. In the impact cards, the link chains, `top_cards.csv` and `impact_cards.csv` its
>   cell is left empty and its row kept, with its rank, teams and cite: 0 in the impact cards, 0 in the
>   link chains and 0 in `top_cards.csv`. A tournament's words are not withheld: they are as often the
>   topic's own words, and name no team without a team code.

### The fixture and its goldens

[`tests/fixtures/landscape/tags_in_the_tables/`](../../tests/fixtures/landscape/tags_in_the_tables/README.md)
is t25's edits plus four tags, each on a cluster with a single copy. Its README works out every expected
cell by hand.

| Card | New tag holds | Shows in | Expected |
|---|---|---|---|
| `a1` ¶6 (t25's) | a school word | the impact table rank 1, the Costs chain's Impact row | **left empty**, row kept |
| `a4` ¶3 | only a tournament word | the impact table rank 2 and its line `(tag)`, top_cards.csv | **shown** |
| `b5` ¶6 | only a tournament word | the Spending DA chain's Uniqueness row, top_cards.csv | **shown** |
| `b6` ¶0 | a school word | top_cards.csv `nhi-t` rank 2 | **left empty**, row kept |
| `a5` ¶3 | a team code | top_cards.csv `condo-bad` rank 1 | **left empty**, row kept |

The hand-written goldens are `impact_sections.md`, `impact_cards.csv` and `top_cards.csv`.
`test_tags_in_the_tables.py` (10 tests) also checks four other things:
* The rest of report.md is `golden/report.md`'s, but for the header's counts: 1, 1 and 2.
* Each withheld row keeps its place, teams and cite.
* No quoted tag holds a school word or team code.
* A coach's scenario name holding only a tournament word shows.

**Older goldens this ruling changes**, edited by hand:
* **`golden/report.md`:** the rule's words, and the new line with 0 / 0 / 0.
* **`readable_impact_chains/` (t25):** the Costs rank-1 cell and its chain Impact cell are empty, and so
  is its `tag` in impact_cards.csv.
* **`link_lead_ins/` (t27):** the Spending DA's internal-link cell is empty.
* **`scenario_vocabulary/`:** the rule's words.

Their READMEs say why.

**One expectation I wrote by hand was wrong.** I expected t27's fixture to leave 0 tags empty in
top_cards.csv; the build left 1. The code is right. Cluster 41 (`b5` ¶9, `Deficits spike Birchmoor
rates`) is the Spending DA's internal link, and it is also its top_cards.csv rank 5. I corrected the test
and t27's README.

### Tests shown failing first

On `87235a0`, the tests and goldens with a skeleton: `TableTagsWithheld` and its field only, no rule
change and no withholding.

Command: `.venv/bin/python -m pytest -q -p no:randomly -p no:cacheprovider --tb=line -n 0` over
`test_tags_in_the_tables.py`, `test_readable_impact_chains.py`, `test_link_lead_ins.py`,
`test_scenario_vocabulary.py`, `test_link_chains.py`, `test_render.py` and
`tests/scripts/test_landscape_table_tag_words.py`.

Result: **30 failed, 270 passed in 1.32 s.**
* **The 23 failures in `debate_core`'s tests** are assertions on their own expectations:
  * goldens that differ;
  * a tag the table still quotes (`'2. Extincti...'` where `None` was expected);
  * counts of 0 where 1 / 1 / 2 were expected;
  * the `later` line withheld;
  * `Classic crash` withheld.
* **The script's 7 failures** are not assertions. 6 are a `TypeError` (its new `cards` argument) and 1
  is the old words check. The script itself was not reduced to a skeleton.

The new scan case, `test_a_planted_team_code_is_withheld_before_the_scan`, came later. It was shown
failing under mutant PM 2: `1 failed, 79 passed`.

After the build: the node's command `uv run pytest packages/debate_core/tests/arguments/landscape` →
**1028 passed in 5.02 s**. With `application/test_landscape_report.py` and both scripts' tests → 1147
passed in 4.15 s.

### Mutants (agreement 8)

How each ran:
* Ten mutants, each alone and in a fresh process: `-n 4 -p no:cacheprovider -p no:randomly`,
  `PYTHONDONTWRITEBYTECODE=1`, and a new empty `HYPOTHESIS_STORAGE_DIRECTORY`.
* Over the landscape tests, `application/test_landscape_report.py` and the script's test: 1141 tests.
* Each file was restored afterwards and checked by SHA-256, and `git status` was clean after every
  batch.

| Mutant | Result | Caught by (some of) |
|---|---|---|
| **PM 1:** the impact table's Tag column left unwithheld | caught, 15 failed | the impact sections and impact_cards.csv goldens, `test_a_withheld_tag_leaves_its_row_with_its_counts_in_every_table` |
| **PM 2:** top_cards.csv left unwithheld | caught, 9 failed | the top_cards.csv golden, the count of tags left empty |
| **PM 3:** a withheld row dropped instead of kept with its counts | caught, 20 failed | the row-keeping test, every golden, t25's naming tests |
| **PM 4:** tournament words still withheld in one place only: t25's lines | caught, 3 failed | the impact sections golden, the tournament-word and scenario-name tests |
| Tournament words still withheld in one place only: top_cards.csv | caught, 5 failed | the top_cards.csv golden, the tournament-word test |
| The link-chain table left unwithheld | caught, 13 failed | the impact sections golden, the row-keeping test |
| The impact tags withheld before t25 reads what names the row | caught, 7 failed | t25's naming tests (`test_each_row_takes_the_first_source_it_has`) |
| A withheld tag left out but not counted | caught, 4 failed | the count test, the rest-of-report tests |
| Team codes no longer withheld | caught, 18 failed | the rule's tests, t25's team-code test, the script's refusal |
| The header's impact and link-chain counts swapped | caught, 1 failed | t27's rest-of-report test (0 / 1 / 1) |

### The counts script over hspolicy26, after the build

Command: `.venv/bin/python scripts/landscape_table_tag_words.py --data-dir ~/.debate-research/dev
--caselist hspolicy26 --through 2026-10-20`, on `a9fb24b`.
* It ran read-only in 46.4 s under a 115 s alarm.
* `debate.sqlite3`'s SHA-256 was unchanged (`feac070d…`).
* It printed counts only:

```text
Caselist words: 937; school word 183, team-code shape 543, tournament word 226; in two kinds or more 15; withheld, the school words and team codes: 726.
Impact table (report.md's Tag column, impact_cards.csv's tag): 87 rows, 87 with a tag, 6 holding a word of a caselist school, team code or tournament (6.9%), 2 of them withheld (2.3%); by kind of word: school word 0, team-code shape 2, tournament word 4; the most-matched word is in 2.
Link-chain table: 96 rows, 96 with a tag, 15 holding a word of a caselist school, team code or tournament (15.6%), 2 of them withheld (2.1%); by kind of word: school word 0, team-code shape 2, tournament word 13; the most-matched word is in 5.
top_cards.csv: 368 rows, 364 with a tag, 105 holding a word of a caselist school, team code or tournament (28.8%), 18 of them withheld (4.9%); by kind of word: school word 1, team-code shape 17, tournament word 93; the most-matched word is in 50.
```

**2 / 2 / 18, as expected.** The script refuses a report whose withheld tags differ from the tags
holding a school word or team code. It did not refuse, so the report left exactly those 2, 2 and 18
cells empty.

## The counts (ac1)

From the first session, unchanged. They are the counts the PM ruled on.

**What ran:**
* A read-only script in the session's scratchpad, wired by hand as t25's and t27's counts were:
  * over `~/.debate-research/dev`;
  * no container, no worker pool, no aff assignments and no analytic texts;
  * the classification cache read through the run's read-only view.
* hspolicy26 through 2026-10-20, taxonomy 1.4.0, in 50 s. The store was unchanged.
* "Holding a caselist word" then meant every word of a school or tournament over three characters, and
  every team code: 937 words, 15 of them in two kinds.

| Table | Rows | With a tag | Holding a caselist word | School word | Team-code shape | Tournament word |
|---|---|---|---|---|---|---|
| Impact table (and impact_cards.csv) | 87 | 87 | 6 (6.9%) | 0 | 2 | 4 |
| Link-chain table | 96 | 96 | 15 (15.6%) | 0 | 2 | 13 |
| top_cards.csv | 368 | 364 | 105 (28.8%) | 1 | 17 | 93 |

**Stop condition (a) held:** top_cards.csv was over a quarter.

**Stop condition (b) nearly held.** The two most-matched words are in 50 and 48 of top_cards.csv's 105
tags, and 46 tags hold both. Both are lower-case dictionary words and words of the topic's own taxonomy.

**Stop condition (c) did not hold:** nothing but the report reads a tag from top_cards.csv.

What each narrower rule would have withheld (impact / link-chain / top_cards.csv):

| Rule | Impact | Link-chain | top_cards.csv |
|---|---|---|---|
| Every caselist word | 6 | 15 | 105 |
| No tournament word **(the ruling)** | 2 | 2 | 18 |
| No tournament word and no word of the taxonomy | 0 | 0 | 2 |

The relay prompt with the four options went to the PM, and the PM ruled (b).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| tags-in-the-tables | Done | In order:<br>1. ac1's counts, the stop at (a), and the relay prompt (first session);<br>2. t25's lines counted under the narrower words;<br>3. the fixture and hand-written goldens, red on a skeleton (`87235a0`);<br>4. the build (`0cc3ebb`) and the guide (`a9fb24b`);<br>5. the scan tests (`5af9c72`);<br>6. 10 mutants;<br>7. the hspolicy26 recount. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, read-only, per table and by kind of word matched, sent to the PM | PASS | [The counts](#the-counts-ac1). The relay prompt went to the PM, who ruled (b) on 2026-10-27. |
| ac2: after the ruling, on synthetic fixtures, the tables withhold as ruled, matching hand-written goldens; tests shown failing first | PASS | `tags_in_the_tables/` goldens written by hand before the code. Red on `87235a0`: 30 failed, 270 passed. Green: 1028 landscape tests, 1147 with the report and scripts tests. 10 of 10 mutants caught, the PM's four among them. On hspolicy26: 2 / 2 / 18. |
| tags-in-the-tables: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | `uv run --frozen pytest -q packages/debate_core/tests/arguments/landscape` → **1028 passed in 5.02s** |

## Before the report (working agreement 10)

On `5af9c72`, with this report and the spec's phase uncommitted.

**The affected set** (`uv run --frozen python scripts/affected_tests.py`) chose 213 of 550 test files
from 27 changed files. The domain model and the report service reach most of the application and CLI
tests. It is over the two-minute line, so under the PM's rule of 2026-10-19 the whole set is left to the
pull request's CI, with no hand-off. What did run:
* **The 148 files outside `debate_cli` and `debate_api`.**
  * Run: `-n 6 -m "not slow and not live"` under a 115 s alarm. The alarm stopped it at 78%.
  * It had shown 5 failures by then: `application/test_landscape_run.py`'s scan tests, which planted a
    team code in a tag. They are fixed in `5af9c72` ([decisions](#decisions-and-assumptions)).
  * The workers the alarm orphaned exited on their own; none outlived it.
* **The files that read landscape output.**
  * The eight landscape-adjacent files, with the scan fix: 153 passed, then 80 passed for the run and
    command tests.
  * The 56 affected files that mention the landscape, the scan or the rule: under the alarm, stopped at
    93% with no failure shown.
* The rest of the 213 is left to CI.

**Checks:**
* `uv run --frozen ruff format --check .` → 1543 files already formatted. `uv run --frozen ruff check .`
  → all checks passed.
* `.venv/bin/pyright`, bare as CI runs it → 0 errors, 0 warnings.
  * The script and its test, checked on their own: the script is clean. The test's
    `import landscape_table_tag_words` shows as unresolved, because that import goes through
    `sys.path`; this was so before this task.
* `uv run --frozen lint-imports` → 18 kept, 0 broken. `scripts/check_thin_handlers.py` → 67 handlers
  within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 490 files.
* `scripts/check_command_blocks.py` → exit 0. `scripts/docs_index.py --check-descriptions` → 56
  documents described.
  * `--check` reports docs/README.md stale for a document from another task: the base commit already
    lacked it. CI runs `--check` only on pull requests into main, and a task does not regenerate that
    file.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change.

## Files changed

* **Rule and report:** `link_chains.py` (`caselist_words`), `application/landscape_report.py`,
  `domain/landscape_report.py` (`TableTagsWithheld`), `render.py`.
* **Script:** `scripts/landscape_table_tag_words.py`, which reads parsed tags and checks the withholding.
* **Guide:** `docs/guides/landscape-taxonomy.md`.
* **Fixtures:**
  * new: `tests/fixtures/landscape/tags_in_the_tables/` (README, edits, three goldens);
  * edited: `golden/report.md`, `readable_impact_chains/` (two goldens, README),
    `link_lead_ins/` (golden, README), `scenario_vocabulary/impact_sections.md`.
* **Tests:**
  * new: `test_tags_in_the_tables.py`;
  * updated to the ruling: `test_link_chains.py`, `test_readable_impact_chains.py`,
    `test_link_lead_ins.py`, `tests/scripts/test_landscape_table_tag_words.py`;
  * the scan tests: `application/test_landscape_run.py`, and `packages/debate_cli/tests/test_landscape_command.py`.
* **Spec:** the Goal set to `Succeeded`. **This report.**

## Deviations from the spec

* **`packages/debate_cli/tests/test_landscape_command.py` is outside `constraints.packages`.**
  * Its two scan cases planted Harrowgate Prep's code `PX` in a tag, and expected the scan before
    sharing to find it in top_cards.csv.
  * Under the ruling the report withholds that tag, so the scan finds nothing and the cases fail.
  * I changed the plant to the tournament `Thistle Open`, which the report now quotes and the scan
    finds, and changed the expected hit to `tournament 'Thistle Open'`. Nothing else in the file changed.
  * The PM may want to add `packages/debate_cli/tests` to the spec's packages. I left the constraint for
    the PM, as before.
* Otherwise none. Nothing committed or printed holds a matched hspolicy26 word, tag, school or team code.
  The synthetic fixtures' invented words are in the tests and READMEs, as before.

## Decisions and assumptions

* **Where the tag is left out.** In the report service, as t25 leaves out a withheld internal link,
  rather than in the renderer.
  * So the domain report never holds a withheld tag, and every reader (the CSVs, report.md, the file
    builder) gets the same rows.
  * The file builder reads a top card's rank, fingerprint and source, never its tag, so it is unchanged.
* **An impact row's tag is left out after `with_lead_in`.** Otherwise t25 would see no tag to pass over,
  and its "Tags withheld" count would drop. A mutant shows the order matters.
* **Counted in report.md's header,** one line for all three tables, as every other withholding in the
  report is counted. The CSVs carry no new column or header key. Their `tag` cell is empty, as
  impact_cards.csv's `internal_link_tag` already is for a withheld internal link (t25).
* **One set per report.** `build` makes `caselist_words` once and gives it to `_LinkChains` and to the
  table step, so no place can drift to other words. Mutants PM 4 and its table twin show a drift is
  caught.
* **The scan before sharing is unchanged.**
  * It still looks for whole school and tournament names, and team codes, in every file of the bundle.
  * Since no tournament word is withheld now, a tag holding a whole tournament name reaches the bundle,
    and the scan holds the publish until the hit is read. That is the case the scan tests now plant.
  * A new case shows a planted team code withheld before the scan sees it.
* **The counts script counts parsed tags.** It takes each row's tag from the card the row shows (its
  file's digest and first paragraph), so its by-kind counts survive the withholding. A row naming no card
  is refused.
* **Scenario-name test.** A coach's name holding only a tournament word (`Classic crash`) shows. No test
  pinned the old behaviour for names.

## Operator follow-ups

**The republish to dev, after this task merges into `dev`, on any day but a Wednesday** (the cloud run's
day). Nobody ran it in this task. It is t23's block, with this task's merge check. It reads the Mac's
dev working copy, as t23's did, and in bucket mode it holds the dev run lock while it publishes.

**Operator command** (expected runtime ~2 min, most of it the report's build)
Where: the `dev-preview` worktree, after this task has merged into `dev`, not on a Wednesday
```bash
cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview"
git fetch origin
git switch --detach origin/dev
grep -q 'class TableTagsWithheld' packages/debate_core/src/debate_core/domain/landscape_report.py && echo "ok: v1-e32-t28 merged at $(git rev-parse --short HEAD)" || echo "STOP: origin/dev has no v1-e32-t28"
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

* The first line must be `ok: v1-e32-t28 merged at <commit>`. Stop on any `STOP` line.
* The dry run names hspolicy26's newest snapshot and its counts. Positions read must be above zero, and
  planned uploads must be above zero.
* **If the scan held the publish back (exit 1),** read its hits with the PM.
  * A hit may now name a tournament inside a card's tag, since the report no longer withholds a
    tournament's words.
  * Stop if a hit names a school or a team code.
  * Once the hits are accepted, copy the digest it printed into the next block.
* Stop if the dry run is refused because the run lock is held or the bucket is not seeded.

**Operator command** (expected runtime ~2 min)
Where: the `dev-preview` worktree, straight after the dry run. Replace `DIGEST_FROM_THE_DRY_RUN` with the
digest the dry run printed. If the dry run reported no scan hits, delete
`--accept-scan-hits DIGEST_FROM_THE_DRY_RUN`. Pasted as it is, the placeholder is refused and nothing is
published.
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

Success looks like `Uploaded N, unchanged M` to `reports/landscape/hspolicy26/<snapshot>/`.
* N is at least 1: report.md, top_cards.csv and impact_cards.csv change.
* N plus M equals the dry run's planned uploads.

**The pilot check.** Wait at least five minutes after the upload.
1. Sign in at <https://tub.dev.wfbdebate.com/landscape/hspolicy26>.
2. Under "How to read the numbers", the **Tags left empty** line reads `2 in the impact cards, 2 in the
   link chains and 18 in top_cards.csv` for the snapshot through 2026-10-20. A newer snapshot has its
   own counts.
3. Paste that line and the upload line back into the session or the PR.

## Follow-up work

* **The scope of `constraints.packages`.** See [Deviations](#deviations-from-the-spec): a CLI test
  planted a team code that the ruling now withholds.
* **The dry run does not print the tables' counts.** `landscape_dry_run_by_section.py` prints t25's
  per-kind counts, not the new line. The report's header carries it, and this task's script recounts it.
  Whether the dry run should print it is the PM's to file.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
