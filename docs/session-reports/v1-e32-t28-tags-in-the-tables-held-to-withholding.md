# Session report: v1-e32-t28-tags-in-the-tables-held-to-withholding

| | |
|---|---|
| Task | `v1-e32-t28-tags-in-the-tables-held-to-withholding` — Tags quoted in the impact and link-chain tables, held to the report's withholding, counted first |
| Spec | [`plan_specs/v1/e32-argument-landscape/t28-tags-in-the-tables-held-to-withholding.yaml`](../../plan_specs/v1/e32-argument-landscape/t28-tags-in-the-tables-held-to-withholding.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t28-tags-in-the-tables-held-to-withholding` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Stopped at the PM's stop condition (a), with the counts. Nothing is withheld yet, and the Goal stays
`InProgress`.**

**Why it stopped.** Withholding as t25 does would blank **105 of top_cards.csv's 364 tags (28.8%)**.
That is over the quarter the PM's brief set. The other two tables are under it:
* the impact table: 6 of 87 tags (6.9%);
* the link-chain table: 15 of 96 (15.6%).

**What drives it.** 93 of the 105 are tournament words. Two of those words make up most of the matches:
* the most-matched word is in 50 tags and the next in 48, and 46 tags hold both;
* both are lower-case dictionary words, and both are words of the topic's own taxonomy (its labels,
  aliases or tag keywords).

So condition (b) nearly holds as well: not one word, but a pair of the topic's own words.

Condition (c) does not hold. Nothing other than the report reads a tag from top_cards.csv
([below](#the-pms-three-stop-conditions)).

**What the PM should look at first:** [the relay prompt](#questions-for-the-pm). It has four options;
my recommendation is (b), to stop withholding tournament words everywhere. The tables would then
withhold 2, 2 and 18 tags (2.3%, 2.1%, 4.9%).

**What is built:** only the count. `scripts/landscape_table_tag_words.py` prints ac1's counts, counts
only. With `--show-words` it also prints the matched words, on the operator's screen only. The PM asked
for that optional block, and nobody ran it. Its test was written by hand from the synthetic fixtures,
and it caught 5 of 5 mutants. report.md, the CSVs and the guide are unchanged.

## The counts (ac1)

**What ran:**
* A read-only script in the session's scratchpad (`counts/count_table_tags.py` with
  `counts/table_tag_counts.py`). It was wired by hand as t25's and t27's counts were:
  * over `~/.debate-research/dev`;
  * no container, no worker pool, no aff assignments and no analytic texts;
  * the classification cache read through the run's read-only view.
* hspolicy26 through 2026-10-20, taxonomy 1.4.0. The report was built by the shipped
  `LandscapeReportService`.
* The final run took 50 s under a 115 s alarm on the interpreter. Each of the four runs took 49 to 61 s.
  `debate.sqlite3`'s SHA-256 was unchanged after every run, no process outlived one, and no `DEBATE_`
  variable was set.
* The committed script (`--data-dir ~/.debate-research/dev --caselist hspolicy26 --through 2026-10-20`)
  printed the same per-table counts in 50.0 s.

"Holding a caselist word" is the report's own `is_withheld`, against the report's own `caselist_words`.
The words are split by where each came from:
* **school word:** a word of a school's name, over three characters;
* **team-code shape:** a word of a team code, at any length;
* **tournament word:** a word of a tournament's name, over three characters.

There are 937 words: 183 school words, 543 team-code shapes and 226 tournament words. 15 words are in
two kinds, so a tag can count under two kinds. Nothing printed a word, a tag, a school or a team code.

### hspolicy26, per table

| Table | Rows | With a tag | Holding a caselist word | School word | Team-code shape | Tournament word |
|---|---|---|---|---|---|---|
| Impact table (report.md's Tag column; impact_cards.csv's `tag` is the same rows) | 87 | 87 | **6 (6.9%)** | 0 | 2 | 4 |
| Link-chain table | 96 | 96 | **15 (15.6%)** | 0 | 2 | 13 |
| top_cards.csv | 368 | 364 | **105 (28.8%)** | 1 | 17 | 93 |

* **Impact table.** The 6 tags are 4 advantage and 2 DA tags: t25's 6 own tags withheld. All 31
  link-chain Impact rows are the impact table's rank 1, so the two tables overlap there.
* **top_cards.csv.** By kind of position: advantage 29, DA 19, K 17, CP 13, T 11, aff 10, theory 6.
  99 tags match one kind and 6 match two.

### What the matches are made of (counts only)

| | Impact table | Link-chain table | top_cards.csv |
|---|---|---|---|
| Distinct words matched | 4 | 10 | 25 |
| Tags holding each of the three most-matched words | 2, 2, 1 | 5, 2, 2 | **50, 48, 16** |
| Tags holding both of the two most-matched words | 0 | 0 | **46** |
| Those three words: lower-case dictionary word | yes, yes, yes | yes, yes, yes | yes, yes, yes |
| Those three words: in the topic's taxonomy (labels, aliases, tag keywords) | yes, no, no | no, yes, yes | **yes, yes, yes** |
| Those three words: kind | team code, tournament, tournament | tournament ×3 | **tournament, tournament, team code** |
| Matched words that are lower-case dictionary words | 4 of 4 | 10 of 10 | 22 of 25 |

**The dictionary check.** "Dictionary word" means the word is a lower-case entry of the Mac's
`/usr/share/dict/words` (Webster's Second, 235,976 entries). The check printed only yes or no. It is the
session's test of the PM's "looks like an ordinary English word", not a rule the report could ship: CI
has no such file.

### What each narrower rule would withhold

These are counts for the options in [the relay prompt](#questions-for-the-pm). Each rule would also
change t25's lines, because they withhold with the same words.

| If the report did not withhold… | Impact table | Link-chain table | top_cards.csv |
|---|---|---|---|
| (as ruled: every caselist word) | 6 (6.9%) | 15 (15.6%) | 105 (28.8%) |
| the most-matched word | 4 (4.6%) | 10 (10.4%) | 103 (28.3%) |
| the two most-matched words | 2 (2.3%) | 10 (10.4%) | 66 (18.1%) |
| any word of the topic's taxonomy | 4 (4.6%) | 10 (10.4%) | 40 (11.0%) |
| **any tournament word** | **2 (2.3%)** | **2 (2.1%)** | **18 (4.9%)** |
| any tournament word or word of the topic's taxonomy | 0 | 0 | 2 (0.5%) |
| any lower-case dictionary word (not shippable, see above) | 0 | 0 | 3 (0.8%) |

### The synthetic fixtures

From `tests/fixtures/landscape/synthetic_caselist`, read as is and with t25's edits
(`readable_impact_chains/edits.yaml`). The test expects these counts, written by hand. The caselist has
18 words: 5 school words, 8 team-code shapes and 6 tournament words, with `fictional` in two kinds.

| Table | Unchanged | t25's edits |
|---|---|---|
| Impact table | 7 rows, 7 with a tag, 0 holding a word | 7 rows, 6 with a tag, 1 holding a word (school word) |
| Link-chain table | 9 rows, 9 with a tag, 0 | 9 rows, 9 with a tag, 1 (school word) |
| top_cards.csv | 23 rows, 23 with a tag, 0 | 23 rows, 22 with a tag, 0 |

In the edited fixture, the one tag holding a word is the Costs advantage's rank-1 impact tag. The
link-chain table quotes the same tag as its Impact row. top_cards.csv shows the tag most copies of that
cluster carry, which is not the edited one.

## The PM's three stop conditions

| Condition | Holds? | Evidence |
|---|---|---|
| (a) withholding would blank more than a quarter of any one table's tags | **Yes**: top_cards.csv | 105 of 364, 28.8%. The impact table is at 6.9% and the link-chain table at 15.6%. |
| (b) most matches in a table come from one word that looks like an ordinary English word | **Not by the letter; nearly** | top_cards.csv: the most-matched word is in 50 of 105 tags (47.6%). With the next word (48 tags, 46 of them shared), two dictionary words that are also words of the topic's taxonomy are in 52 of the 105 tags. In the other two tables no word is in more than 5 tags. Every match there is a dictionary word. |
| (c) top_cards.csv has a consumer other than the report that a withheld tag would break | **No** | The pilot's landscape pages read only `report.md` and `schools.md` (`debate_core/application/tub/landscape_pages.py`). The file builder (`files suggest`, `file_suggest_service.py`) reads `report.top_cards` in memory: the position, rank, fingerprint, source key and element index. It never reads a tag ("No tag and no text of a card") and never reads the CSV. The CLI counts its rows (`top_card_rows`). The removal runbook and the bucket tests name the file only. |

Under the brief, (a) means: stop and send the counts. Nothing was withheld.

## Questions for the PM

A paste-ready relay prompt:

```text
v1-e32-t28 (tags in the tables held to withholding): stopped at your condition (a), counts only. Nothing is built yet.

Counts, hspolicy26 through 2026-10-20 (taxonomy 1.4.0, read-only, 50 s). These are tags holding a caselist word,
by kind of word:
- Impact table (report.md's Tag column; impact_cards.csv's tag is the same rows): 6 of 87 (6.9%).
  Team-code shape 2, tournament word 4.
- Link-chain table: 15 of 96 (15.6%). Team-code shape 2, tournament word 13.
- top_cards.csv: 105 of 364 (28.8%). School word 1, team-code shape 17, tournament word 93.
  This is over your quarter, so (a) holds.

(b), nearly. In top_cards.csv the most-matched word is in 50 of the 105 tags, and the next in 48; 46 tags hold
both. Both are tournament words, both are lower-case dictionary words, and both are words of the topic's own
taxonomy (labels, aliases or tag keywords). In the other two tables no word is in more than 5 tags, and every
matched word is a dictionary word.
(c) does not hold. The pilot reads only report.md and schools.md. The file builder (files suggest) reads the
report's top cards in memory, for rank, fingerprint and source, and never a tag or the CSV.

Options. Each applies to every place the report withholds a tag (t25's lines too), so it withholds one way
everywhere. Counts are impact / link-chain / top_cards.csv:
(a) Withhold every caselist word, as you pre-ruled: 6 / 15 / 105 tags (6.9% / 15.6% / 28.8%). Rows and their counts stay.
(b) Withhold school words and team codes, but no tournament word: 2 / 2 / 18 (2.3% / 2.1% / 4.9%).
(c) As (b), and also no word of the topic's own taxonomy: 0 / 0 / 2 (0.5%).
(d) Withhold every caselist word in report.md's two tables now (6 and 15), and leave top_cards.csv as parsed until
    you rule on it. top_cards.csv is not on the pilot.

My recommendation: (b).
- Tournament words are 93 of top_cards.csv's 105 matches and 13 of the link-chain table's 15.
- Every matched word in report.md's two tables, and 22 of 25 in top_cards.csv, is a dictionary word; top_cards.csv's
  top two are this topic's own words.
- The policy treats a tournament label as personal only combined with a team code (its personal-data list),
  and the circuit-wide report carries no team code.
- School words and team codes stay withheld everywhere, as policy 1.13 asks.
- (b) also gives back t25's lead-in names withheld for a tournament word: 4 of its 6 own tags.
(c) goes further, but it is a per-taxonomy word list to keep. (a) blanks over a quarter of top_cards.csv, mostly
for the topic's own words.

If you pick (b) or (c), the build session counts t25's lines (scenario names, tags, internal links, cards above)
under the narrower words first, then builds as you pre-ruled: same rule in all places, rows kept with their counts,
hand-written goldens, tests red first, your three mutants, one line in the guide.

The words themselves are on the operator's screen only if the coach wants to look (optional block in the report,
not run).
```

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| tags-in-the-tables | Stopped at the PM's condition (a) | In order:<br>1. ac1's counts, read-only, on hspolicy26 and the synthetic fixtures;<br>2. the three stop conditions checked: (a) holds;<br>3. the optional words block, as a counts-first script with a hand-written test (`f4c9b01`);<br>4. 5 mutants on it;<br>5. the checks before the report.<br><br>Nothing is withheld: ac2 waits on the ruling. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, read-only, per table and by kind of word matched, sent to the PM | PASS | [The counts](#the-counts-ac1), read-only, 50 s, counts only, `debate.sqlite3` unchanged. The [relay prompt](#questions-for-the-pm) carries them to the PM. They are reproducible from committed code: `.venv/bin/python scripts/landscape_table_tag_words.py --data-dir ~/.debate-research/dev --caselist hspolicy26 --through 2026-10-20` → the same three table lines, `Runtime 50.0 s.` |
| ac2: after the ruling, on synthetic fixtures, the tables withhold as ruled, matching hand-written goldens; tests shown failing first | NOT RUN | Stopped at the PM's condition (a), as the brief directs: "Stop and send the PM the counts instead". It waits on the PM's ruling. The guide line and the PM's three mutants belong to it. |
| tags-in-the-tables: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | `.venv/bin/python -m pytest -q packages/debate_core/tests/arguments/landscape` → **1017 passed in 6.67s** (no landscape code changed) |

### Checks shown failing for their reason

`tests/scripts/test_landscape_table_tag_words.py` has 5 tests. Every expected line was written by hand
from the fixture READMEs and the goldens, and all 5 pass. They passed on their first run, so I applied
5 mutants to the script, each alone. Each mutant ran in a fresh process
(`-n 0 -p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1`) with a new empty
`HYPOTHESIS_STORAGE_DIRECTORY`; no Hypothesis is used. The file was then restored, checked by SHA-256,
and `git status` was clean afterwards.

| Mutant | Failed | Caught by |
|---|---|---|
| The words are printed without `--show-words` | 3 of 5 | the unchanged, edited and two-kinds cases |
| Team codes are looked for only over three characters | 5 of 5 | the words-by-kind case. The script's own guard (the kinds together must equal `caselist_words`) refuses the rest. |
| A held tag is counted twice | 3 of 5 | the edited, two-kinds and words cases |
| A tag is counted under its first kind only | 1 of 5 | `test_a_tag_holding_two_kinds_counts_under_both` |
| An empty tag is counted as quoted | 2 of 5 | the edited and words cases (6 and 22 with a tag) |

## Before the report (working agreement 10)

On `f4c9b01` (the script and its test; the report is uncommitted text):
* **The affected set:** `uv run scripts/affected_tests.py` chose 40 files.
  * Run: `.venv/bin/python -m pytest -q -n 6 -m "not slow and not live" -p no:randomly <the 40 files>`
    under a 115 s alarm.
  * Result: **1884 passed in 73.89s**, and no process outlived it. The run includes `tests/architecture`
    and `tests/specs`.
* The node's command → 1017 passed in 6.67s.
* `uv run --frozen ruff format --check .` → 1540 files already formatted. `uv run --frozen ruff check .`
  → all checks passed.
* `.venv/bin/pyright`, bare as CI runs it → 0 errors, 0 warnings in 20 s. No package changed; the
  script is outside pyright's `include`.
* `uv run --frozen lint-imports` → 18 kept, 0 broken. `scripts/check_thin_handlers.py` → 67 handlers
  within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 490 files.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`scripts/landscape_table_tag_words.py`** (new): the counts, per table and by kind of word, counts
  only. `--show-words` adds the words, for the operator's screen only. It reads the working copy wired
  by hand, writes nothing and calls no model.
* **`tests/scripts/test_landscape_table_tag_words.py`** (new): 5 tests over the synthetic caselist,
  unchanged and with t25's edits, with expectations written by hand.
* **This report.**

The scratchpad scripts that took the ac1 counts are not committed. They hold the dictionary and
taxonomy-word checks, which the report cannot ship.

## Deviations from the spec

None. `scripts` and `tests/scripts` are in `constraints.packages`. Nothing committed, and nothing
printed, holds a matched word, a tag, a school or a team code. The script prints words only when the
operator passes `--show-words`.

## Decisions and assumptions

* **impact_cards.csv is counted with the impact table.** Its `tag` column holds the same rows' tags.
  "Withhold in one way everywhere" would reach it too, so the build would withhold it with the impact
  table.
* **"Team-code shape" is read as a word of a caselist team code,** as `caselist_words` takes them, at
  any length. It does not mean any word shaped like a code.
* **The kinds overlap.** 15 of hspolicy26's 937 words are in two kinds, so a tag can count under two,
  and the kinds can add up to more than the tags (6 tags in top_cards.csv).
* **The topic's taxonomy words** are the words of every position's label, aliases and tag keywords in
  taxonomy 1.4.0, plus the topic's resolution when given (187 words). 8 of the 937 caselist words are
  among them.
* **The optional words block is a committed script, not a one-off.** The PM said the coach may look
  later, and a scratchpad does not last. By default it prints the same counts, so ac1 can be reproduced
  from committed code.
* **No republish block.** This branch changes no file of the report, so a republish would publish the
  same bytes. The build session writes the republish block after the ruling.

## Operator follow-ups

**Optional, and not run in this task: the matched words, for the coach.** It is read-only and writes
nothing. It takes about 50 s.

Where: your Mac, in the task worktree. The words it prints are for your screen only: do not paste them
back into the session, a report or a commit.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t28-tags-in-the-tables-held-to-withholding
uv run python scripts/landscape_table_tag_words.py --data-dir ~/.debate-research/dev --caselist hspolicy26 --through 2026-10-20 --show-words
```

Success looks like:
* exit 0;
* the header and the three table lines, with the same counts as [the table above](#hspolicy26-per-table):
  6 of 87, 15 of 96, 105 of 364;
* each table line followed by its matched words, each with its kind and its number of tags;
* a last line of `Runtime … s.`

## Follow-up work

* **ac2, after the PM's ruling:** the build as pre-ruled, under whichever words the ruling picks. If the
  ruling narrows the words, t25's lines are counted again first. The work includes the goldens, the
  red run, the PM's three mutants, the guide line and the republish block. It continues in this task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
