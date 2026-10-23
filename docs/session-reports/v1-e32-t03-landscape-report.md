# Session report: v1-e32-t03-landscape-report

| | |
|---|---|
| Task | `v1-e32-t03-landscape-report` — Weekly landscape report |
| Spec | [`plan_specs/v1/e32-argument-landscape/t03-landscape-report.yaml`](../../plan_specs/v1/e32-argument-landscape/t03-landscape-report.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t03-landscape-report` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task builds `LandscapeReportService` in `debate_core.application`. It is a pure aggregation
with no model, reading t02's classifications, E30's disclosures and E31's clusters. Its output is a
report bundle of `report.md`, `positions.csv` and `top_cards.csv`, rendered by
`arguments/landscape/render.py` and passed through v1-e34-t03's staleness hook.

* **The aff seam for v1-e32-t09** is an optional per-round `AffAssignment` (round id, position id,
  method). The report counts it when it is present; otherwise it shows the unidentified share.
* **The Unclassified section** counts cards, and rounds by side.
* **The header** names the overrides digest, the prompt version `none`, coverage by cards and by
  rounds, and the denominators behind every share.

Every criterion a session can close passes. **The Goal stays InProgress** because ac5 is the coach's
sign-off on the layout, which only he can give (NOT RUN, see Operator follow-ups). Question 4 asks
how to close it without holding up t05, whose context needs this task Succeeded.

**Look first at Deviation 1.** The read-only preview on hspolicy26 through 2026-10-20 showed that
**53.2% of the position-rounds counted were on the position's opposite side**. These are aff files
with a `Midterms DA` block and neg files with a `Costs advantage` block: the 2AC and 1NC answers,
which t02 records as READS because no `AT:` marker shows. Counted as reads, they made the Midterms DA
"966 rounds, 528 of them aff". The report now counts a placement in a round on the other side as
answering the position. It reports the number it set aside (4,734 rounds on hspolicy26), and
question 1 asks the PM to confirm the rule.

**Then the preview** ([below](#the-preview-on-the-real-store)). It ran read-only in 41 s. The scan
found no team code and no school in a team's sense: its five hits are an author's surname, an
ordinary word that is also a disclosed code, and a filename token.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| synthetic-caselist-fixture | Done | `scripts/make_landscape_fixture.py` writes `tests/fixtures/landscape/synthetic_caselist/`: 15 sources, 18 disclosure rows over three weekly snapshots, 16 rounds in range by 8 teams, 46 cards (44 in range). Team codes are `XX`, `YY`, `ZZ`, `QQ`, `VV`, `WW`, `JJ` and `KK` at four fictional schools. Its README lists what each part exercises. The golden files in `tests/fixtures/landscape/golden/` were written by hand from the generator's table |
| report-model | Done | `domain/landscape_report.py`: `LandscapeReport`, `ReportHeader`, `PositionStats`, `TopCard`, `UnclassifiedSummary`, `AffIdentification`, plus the inputs `LandscapeCard` and `AffAssignment` |
| aggregation | Done | `application/landscape_report.py`: `LandscapeReportService`, `round_id`, `overrides_digest`, `landscape_cards`. `read_seed_sources` now also returns the on-topic disclosures as E30 records them, and each card's short cite |
| top-cards | Done | One row per E31 cluster, ranked by distinct teams then cluster id. The row shows the commonest tag and short cite, taken from the first such card |
| renderers | Done | `arguments/landscape/render.py`, golden tests, pyright clean. The coach's review (custom criterion) is NOT RUN |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: positions.csv for the two-snapshot fixture has one row per position read, with the listed columns, matching a hand-computed expected file | PASS | `test_aggregate_positions_match_the_hand_computed_file` compares every value of every row to `golden/positions.csv`. `test_rendering_the_fixture_matches_the_golden_file[positions.csv]` compares the whole file byte for byte. `test_the_csv_columns_are_the_specs` pins the ten columns |
| ac2: top_cards.csv lists up to N (default 5) fingerprints per position, with teams_reading, tag, short cite, source object key, element index and FILE_IMPORT; near-duplicates of one bucket count once | PASS | `golden/top_cards.csv` byte for byte. `test_top_cards_rank_clusters_by_distinct_teams_and_count_near_duplicates_once`: cluster 2 has four exact fingerprints, one team reads two of them, and teams_reading is 4. Also `..._are_capped_at_n_per_position`, `..._ties_are_broken_by_fingerprint` and `..._every_row_is_file_import` |
| ac3: items below the report threshold, or waiting in the review queue, are excluded and reported as an Unclassified line with count and share | PASS | `test_aggregate_below_threshold_and_queued_items_are_unclassified_not_counted`: 10 of 44 cards, 8 queued and 2 below the threshold; `courts-cp` (below the threshold only) has no row. `..._the_report_threshold_decides_what_is_unclassified` runs at 0.95 and 0.4. `..._unclassified_rounds_are_counted_by_side`: aff rounds with no identified aff 3 of 7, neg rounds with no placed negative position 1 of 8 |
| ac4: rendering the same inputs twice gives byte-identical Markdown and CSV (golden files), and a scan finds no team code from the fixture disclosures | PASS | `test_rendering_the_fixture_matches_the_golden_file` (3 files). `test_rendering_the_same_inputs_twice_in_any_order_is_byte_identical` uses three shuffles of every input. `test_a_scan_of_the_output_finds_no_team_code_school_tournament_or_path_from_the_disclosures`, shown failing on planted `XX` and on a planted school (below) |
| ac5: the coach reviews the fixture report and confirms the sections and column names are usable for weekly prep | NOT RUN | A sign-off only the coach can give. The preview and the fixture report are ready for him; the question is in Operator follow-ups |
| synthetic-caselist-fixture: the README contains "synthetic" | PASS | `grep -c synthetic tests/fixtures/landscape/synthetic_caselist/README.md` → 2 |
| report-model: `domain/landscape_report.py` contains `class PositionStats` | PASS | `grep -c "class PositionStats" …` → 1 |
| aggregation: `pytest …/test_landscape_report.py -k aggregate` | PASS | 29 passed in 2.20s |
| top-cards: `pytest …/test_landscape_report.py -k top_cards` | PASS | 7 passed in 2.23s |
| renderers: `pytest …/arguments/landscape/test_render.py` | PASS | 13 passed in 3.42s |
| renderers: `uv run pyright packages/debate_core` | PASS | 0 errors, 0 warnings, 0 informations (14.0 s) |
| renderers: the coach reviews the fixture report layout | NOT RUN | Same as ac5 |

I ran each pytest command as `.venv/bin/python -m pytest …` under `perl -e 'alarm 110'`, which puts
the time limit on the interpreter (working agreement 10).

### Checks shown failing for their reason

* **Red run against a skeleton service with every rule and refusal removed.** It counted every placed
  card in every round of its file, whatever its role, confidence or date. It ignored assignments,
  grouped top cards by exact fingerprint in input order, marked nothing new, and refused nothing.
  Result: **30 failed, 19 passed**. Among the failures were all four aff-seam tests: assignment
  counted, method named, refusals, and placed-card identification. The 19 that passed hold no
  counting rule: round ids, the store join, the scan, the stale banner, and two top-card tests that
  passed by input-order coincidence. The second of those led to a new test,
  `test_top_cards_the_first_card_by_digest_shows_only_when_its_tag_and_cite_are_the_commonest`.
* **Red run against an empty renderer: 10 failed, 2 passed.** Determinism and the scan pass on empty
  output, so `test_the_scan_finds_a_team_code_planted_in_a_tag` shows that the scan can fail.
* **The scan, planted:** `XX` in a fixture tag → `report.md names ['XX']`. A school's first word in a
  fixture cite → `report.md names ['Birchmoor']`. The fixture was restored from git after each.
* **21 mutants of the counting rules, all caught**, on the final code. Each ran in a fresh process
  with bytecode writing off and `__pycache__` cleared, and the file was restored byte for byte. No
  Hypothesis is used, so working agreement 8's database rule does not arise. Two first survived or
  weakened, and each was fixed with a fixture case or a test:

  | Mutant | Failed |
  |---|---|
  | A placement in a round on the other side counts as a read | 8 |
  | ANSWERS count as reads | 7, **after a fixture card was added**. Once the other-side rule landed, every ANSWERS card sat in a round on the other side, so this fell to 2. `b7`'s answer to `nhi-t`, in a round on no readable side, now pins it alone |
  | Top cards grouped by exact fingerprint, not by cluster | 11 |
  | teams_reading counts cards, not distinct teams | 5 |
  | Top-card ties not broken by fingerprint | 2 |
  | Top-card ties broken by fingerprint, descending | 3 |
  | Position ties not broken by id | 2 |
  | Positions ranked by rounds before teams | 1, **after a new test**. It first survived (51 passed), because teams and rounds order alike in every kind of the fixture. `test_aggregate_positions_rank_by_teams_before_rounds` was added |
  | An aff card still counts in a round t09 assigned another aff | 1 |
  | An assignment is not counted as a read | 1 |
  | Assigned rounds identified as PLACED_CARD | 1 |
  | An assignment of a negative round is not refused | 1 |
  | An assignment naming a non-aff is not refused | 1 |
  | The report's own threshold ignored | 2 |
  | The range leaves out the snapshot day itself | 29 |
  | A round's first seen is its latest listing | 5 |
  | New includes the previous snapshot | 4 |
  | share_of_teams counts teams on any side | 4 |
  | share_of_teams over every team | 6 |
  | A disclosure with no readable team is a team | 1 |
  | A top card shows the first card, not the commonest | 4 |

### The preview on the real store

Read-only, counts only, hspolicy26 through 2026-10-20 (t02 Decision 9). The guards were checked
first: no `DEBATE_*` variable was set and no caselist pull was running.

The run used a scratchpad script, not committed. It wrapped t02's cache so that a write would be
refused, and it never rewrote the review queue. The cache's checksum is the same before and after.
The three files are in `~/Documents/debate/landscape-seed/landscape-preview/`, outside the
repository, and nothing from them is committed.

| Count | Value |
|---|---|
| Runtime | **41.1 s** (read 28.1, classify from cache 8.9, build 4.1); 81 s on one run that started at load average 12.6 |
| Sources on the topic; disclosures; cards with a cluster | 3,825; 5,075; 126,681 |
| Cache | 107,203 hits of 107,203; 0 writes |
| Snapshot; previous; staleness | 2026-10-20; 2026-10-13; newest 2026-10-20, 3 days old, not stale |
| Taxonomy; overrides; parser; prompt | 1.0.0; `none`; `2026.10.20-docx-6`; `none` |
| Coverage by cards | 60,987 of 126,681 (48.1%), as t02 measured |
| Rounds; teams | 4,352 rounds by 567 teams: 2,192 aff by 552, 2,160 neg by 392 |
| Coverage by rounds | 2,201 of 4,352 (50.6%) |
| Aff rounds with no identified aff | 1,998 of 2,192 (91.1%); 194 identified by a placed card |
| Neg rounds with no placed negative position | 1,389 of 2,160 (64.3%) |
| Set aside as answers (other side) | 4,734 rounds, counted once per position |
| Positions read; new this week; top-card rows | 68 (1 aff, 14 advantages, 4 theory, 17 DAs, 13 CPs, 11 Ks, 8 T); 0; 318 |
| Files | report.md 822 lines, positions.csv 87, top_cards.csv 337 |

Before the other-side rule, the same run had 73 positions and 2,996 rounds with a read. The most-read
rows after it are below. The Midterms DA was "966 rounds, 164 teams, 528 aff rounds" before.

| Position | Rounds | Teams | Share of teams |
|---|---|---|---|
| Costs advantage | 454 | 136 | 24.6% of aff teams |
| Midterms DA | 438 | 127 | 32.4% of neg teams |
| States CP | 199 | 85 | 21.7% of neg teams |
| Single payer | 194 | 77 | 13.9% of aff teams |

**The other side, by kind**, from the first preview (counts only): advantages 2,238 of 4,661
position-rounds (48.0%), DAs 1,162 of 2,004 (58.0%), CPs 631 of 1,023 (61.7%), Ks 309 of 472
(65.5%), T 341 of 483 (70.6%), theory 38 of 49 (77.6%), affs 15 of 209 (7.2%).

**The scan.** It covered every school, team code and tournament that the on-topic disclosures name,
schools and tournaments over three characters. Codes were matched case-sensitively as whole words,
names as words without case.

* positions.csv: no hit.
* report.md: 3 school names, 1 team code and 2 tournaments.
* top_cards.csv: 3 school names, 1 team code and 1 tournament.

I read each hit in its line, and none names a team:

* two of the "school names" are evidence authors' surnames in short cites, and the third is the word
  "union" in a tag;
* the "team code" is a disclosed code that is also an ordinary English word, matching that word in
  two tags;
* the "tournaments" are filename tokens that are also an author's surname or the word "disclosure".

The words themselves are left out of this report on purpose. The platform stores no debater names,
so nothing exists to scan for them. Tags and short cites are shown exactly as parsed.

## Before the report (working agreement 10)

* `uv run scripts/affected_tests.py` listed 56 files (8.6 s). I ran them with CI's markers:
  `.venv/bin/python -m pytest -q -n auto -m "not slow and not live" -p no:randomly <files>` under a
  115 s alarm, at load average 30 → **2,051 passed, 2 skipped in 61.32 s**. The 2 skips are t02's
  overrides-file checks, which have no file to check yet.
* `uv run --frozen ruff format --check .` → 1188 files already formatted.
* `uv run --frozen ruff check .` → all checks passed.
* `uv run --frozen pyright packages/debate_core` → 0 errors.
* `uv run --frozen lint-imports` → 16 kept, 0 broken.
* `scripts/check_thin_handlers.py` → 47 handlers within 25 statements.
* `scripts/check_command_blocks.py` → OK. `scripts/check_links.py` → OK.
  `scripts/docs_index.py --check-descriptions` → OK.
* `uv run scripts/validate_specs.py` → OK, 431 files.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`domain/landscape_report.py`** (new): the report and its two inputs.
* **`application/landscape_report.py`** (new): `LandscapeReportService` (`build`, `bundle`), and:
  * `round_id`, t09's name for a round;
  * `overrides_digest`;
  * `landscape_cards`, which joins a reading's cards to the occurrence table's clusters;
  * `ReportCannotShip`.
* **`arguments/landscape/render.py`** (new): Markdown and the two CSVs.
* **`application/landscape_seeding.py`, `arguments/landscape/seeding.py`**: `SeedReading.disclosures`
  holds the on-topic live disclosures as E30 `Disclosure`s, in memory, not in the `repr`.
  `SeedCard.short_cite` is new.
* **`testing/landscape_report.py`** (new): reads the fixture back for both test modules.
  `testing/landscape_store.py`: `PlantedCard.short_cite`.
* **Tests:** `tests/application/test_landscape_report.py` (41) and
  `tests/arguments/landscape/test_render.py` (13), new; `test_landscape_seeding.py` gains one.
* **`scripts/make_landscape_fixture.py`** (new) and **`tests/fixtures/landscape/`**:
  `synthetic_caselist/` (generated inputs and README) and `golden/` (hand-written).
* **The spec:** the garbled staleness sentence fixed with a PM-ruling comment above the folded block
  (brief item 2). The phase is unchanged.

## Deviations from the spec

1. **A placement in a round on the position's opposite side counts as answering it, not reading it.**
   The spec counts "the rounds and distinct teams that READ it". t02's role is READS unless an `AT:`
   or `A2` heading is on the path. On the real store, 53.2% of position-rounds were aff rounds placing
   cards under negative positions, and the reverse. They are frontlines, and counting them made the
   Rounds and Teams columns mostly answers.
   * The rule is in the service, and the count it sets aside is in the Unclassified section
     (`other_side_position_rounds`).
   * A round on no readable side still counts, since nothing shows it answers.
   * As a result, a sided position's aff/neg split is always one-sided, apart from unknown-side
     rounds (rounds minus the two splits). The split is still meaningful for a position either side
     reads.
   * Question 1.
2. **Files outside `constraints.packages`:**
   * `scripts/make_landscape_fixture.py`, which the plan node names as an output;
   * `debate_core.testing`, the shared fixture reader. Test modules cannot import one another in
     importlib mode, and a conftest change would make the whole selection affected;
   * `packages/debate_core/tests`.

   Question 2.
3. **t01/t02 code changed:** `SeedCard.short_cite` and `SeedReading.disclosures`, both
   defaulted, so the report reads the documents once with classification instead of twice. Seeding
   and classification behave as before; their tests pass unchanged in the affected set.
4. **The report's inputs from the store are assembled here, not in t05.** `landscape_cards` and
   `SeedReading.disclosures` are what the preview needed. They give t05's first run a tested join
   rather than a script to copy. Writing, local paths and publishing remain t05's.
5. **The golden files changed after the other-side rule.** Two fixture cards were added (a 2AC
   spending block, and an answer in a round on no readable side). The goldens and the tests' hand
   counts were edited by hand, from 42 cards in range to 44 and from 31 placed to 33. They were never
   regenerated from output (working agreement 6). The first goldens matched the implementation on
   the first run, before either had seen the other.

## Decisions and assumptions

1. **A round** is one team, one side, one tournament and one round, using the round's normalized
   form when it has one, compared without case. One file listed in two weekly windows, or two files
   for one round, make one round. A file whose name gives no tournament, no round or no readable
   team is a round of its own, so unlabelled files are never merged.
2. **`round_id`** is 16 hex digits of a digest of those fields, so t09 can name a round without the
   report or the assignment ever holding a team code.
3. **A team** is a school and team code, compared without case. A disclosure the path parser could
   read neither of (`UNKNOWN`) reads its round but is no team.
4. **share_of_teams** (the PM's ruling) is the teams reading a position in rounds on its own side,
   over the distinct teams disclosing on that side through the snapshot. For a position either side
   reads, both are over every team. The header and the CSV header block name the denominators.
5. **First seen** is the earliest snapshot that lists a round; a position's is the earliest over its
   reading rounds. **New** means first seen after the previous snapshot, which is the snapshot before
   the newest one in range. In a caselist's first snapshot nothing is new, rather than everything.
6. **Order:** positions by side (aff, neg, both), then kind in the taxonomy's kind order, then teams,
   then rounds, then id. Teams come before rounds because a team that discloses every round should
   not outrank many teams. Top cards are ordered by distinct teams, then cluster id.
7. **What a top-card row shows** is one real card: the tag and short cite pair most of the cluster's
   cards under the position carry (ties go to text order), from the first such card by source digest
   and paragraph. Its snapshot is the one its file was first disclosed in. The key is
   `raw/caselist/<slug>/sha256/ab/cd/<digest>` from `publish_plan.source_key`.
8. **The overrides digest** is t02's `digest_for` over every heading the overrides file decides, or
   `none`. It is the digest the cache keys on, rather than a hash of the file's bytes, so a re-dated
   or reformatted file does not change it.
9. **The aff seam.** An assignment is the round's aff, and a card placed under another aff in that
   round does not count. Advantages and negative positions are counted as placed either way.
   * An assignment for a round outside the range is ignored.
   * An assignment is refused (`ReportCannotShip`) when it names a non-aff or an unknown id, falls on
     a negative round, or repeats a round.
   * The method is an upper-case token t09 names, and the report prints it beside the count.
     `PLACED_CARD` is the method of an aff a placed card identified.
10. **A report does not ship** (`ReportCannotShip`) when:
    * the staleness hook found no snapshot;
    * the hook is of another caselist;
    * a classification was placed under another taxonomy version;
    * a position is retired with nowhere to count;
    * no disclosure is in range.
11. **Prompt version** is the distinct prompt versions of the cards in range, so `none` today, and
    t07's MODEL results will show up without a change here.
12. **Formats.** Each CSV starts with a `# key=value` header block, the hook's `stale=` among its
    lines, then an ordinary header row. Shares are fractions to three places, rounded half up.
    Markdown percentages have one place and counts have thousands separators. A tag or cite in
    Markdown has its table and emphasis characters escaped and whitespace collapsed; the CSV keeps it
    exact.

## Operator follow-ups

1. **The coach's review (ac5 and the renderers node's custom criterion).** Please give the coach:
   * the real preview, `~/Documents/debate/landscape-seed/landscape-preview/report.md`, with the two
     CSVs beside it. It is hspolicy26 through 2026-10-20, real tags, outside the repository;
   * the fixture report, `tests/fixtures/landscape/golden/report.md` and its CSVs in the worktree.

   Ask him:

   ```text
   Do these sections work for the weekly prep meeting: About this report, Affirmative
   positions (affs, advantages, theory), Negative positions (DAs, CPs, Ks, T, theory),
   New this week, Most-read cards, Unclassified? And these columns: Rounds, Teams,
   Aff rounds, Neg rounds, Share of teams, First seen, New; and for cards Rank, Teams,
   Tag, Short cite, Source, Paragraph, First disclosed? Yes or no, and what would you
   change (order, columns, how long tags show, anything missing)?
   ```

   Paste his answer back into this session. It records yes or no and his changes, makes any change
   he asks for, and sets the phase if he says yes. The preview never left this machine.
2. **The pull request,** after the PM's review, from the worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t03-landscape-report
```

```bash
scripts/task pr v1-e32-t03-landscape-report
```

Add `--partial` if the PM accepts it with ac5 still open (question 4).

## Follow-up work

* **t05's description has the same splice** (v1-e32-t05, PM): "review-queue editing stays the The
  command calls the staleness hook … t02 decisions-CSV workflow."
* **t05 wires the run log into the staleness check** (v1-e32-t05). The preview passed
  `run_log=None`, so a cap-bound run would not have shown as stale.
* **Policy gate 4, the scan before sharing** (v1-e32-t05). A scan like the preview's finds ordinary
  words that are also codes or schools, so it should list hits for the operator to read before
  `--publish`, not refuse outright (question 3).
* **Side as a role signal in t02** (v1-e32-t07 or a new task). If the PM prefers the other-side rule
  upstream, the matcher would need each source's sides; the report's rule could then go.
* **Long tags.** Some real tags are a paragraph long, and the Markdown shows them whole, as parsed.
  This is for the coach to say whether a cut would help (question 1 of his review).

## Questions for the PM

```text
v1-e32-t03 questions (session, 2026-10-23)

1. On hspolicy26, 53.2% of position-rounds were on the position's opposite side:
   aff files with a "Midterms DA" block, neg files with a "Costs advantage" block,
   i.e. frontlines with no AT: marker, which t02 records as READS. The report now
   counts such a placement as answering the position (rounds on no readable side
   still count) and reports how many it set aside (4,734). Keep it?
   (a) Keep the rule in the report, as built.
   (b) Count any side again, with the aff/neg split showing the answers.
   (c) Keep (a) now, and file a task to infer ANSWERS from side in t02's matcher.
   Recommendation: (a), with (c) only if t07 or t09 needs the role upstream. As
   (b) the Midterms DA reads "966 rounds, 164 teams, 528 aff rounds"; under (a) it
   is 438 neg rounds by 127 teams, which is what a coach means by "read".

2. Amend constraints.packages with scripts (make_landscape_fixture.py, named by the
   plan node), debate_core.testing (the shared fixture reader) and
   packages/debate_core/tests (Deviation 2)?
   Recommendation: yes, as for t01 and t02.

3. Policy gate 4 (no team codes before sharing): the preview's scan found no team,
   but one disclosed code is an ordinary English word, and two schools share
   evidence authors' surnames. Should t05 refuse to publish on a scan hit, or list
   the hits for the operator?
   Recommendation: list them with their lines and ask before --publish; a refusal
   would block every week on words like that code.

4. ac5 is the coach's sign-off, and t05's context needs t03 Succeeded. If he has
   not answered by 2026-10-27:
   (a) merge t03 --partial and let t05 start, recording his answer in t05's
       first-run note and setting t03 Succeeded then;
   (b) wait for him.
   Recommendation: (a). The preview is the shape t05 will write, and the
   2026-11-07 date leaves no slack for a wait.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
