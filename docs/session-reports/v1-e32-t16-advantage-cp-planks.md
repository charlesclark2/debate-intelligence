# Session report: v1-e32-t16-advantage-cp-planks

| | |
|---|---|
| Task | `v1-e32-t16-advantage-cp-planks` — An advantage counterplan's planks, and the advantage each one solves |
| Spec | [`plan_specs/v1/e32-argument-landscape/t16-advantage-cp-planks.yaml`](../../plan_specs/v1/e32-argument-landscape/t16-advantage-cp-planks.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t16-advantage-cp-planks` |
| Session status | COMPLETE: built and tested after the PM's rulings of 2026-10-25; the operator's refill and dry run recorded; the phase is Succeeded; one scan hit in a plank table for the PM to read before the first publish <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Built, after the PM's rulings of 2026-10-25** ([below](#the-pms-rulings-applied)). report.md now shows
each CP's planks under its CP texts, on synthetic sources, against hand-written golden files.

* **What a plank is:**
  * **a list:** the paragraphs after a CP text ending in a colon, up to the first card or heading.
    A list plank passes the actor guard through its CP text.
  * **separate planks:** later `should` analytics past the guard, or paragraphs opening `Plank 2:`,
    `2.` or `Second,`.
  * A list paragraph that is only an advantage's alias is a label naming the plank after it.
* **What it solves:** every advantage its own words, its label or a card under it name, by an alias
  as whole words. A plan is never named. A card saying `solves` with other words is counted, never
  shown.
* **How it shows.** Planks are grouped by the advantage they solve: the top 3 per advantage, then "and
  N more planks, read by M teams", with "not named" last.
  * A plank naming two advantages is under each, and counted once in the CP's total.
  * A plank naming a school is withheld and counted.
  * Planks are in report.md only.
* **Tests were shown failing first.** 15 targeted mutants were all caught, after one redundant check
  was removed ([below](#mutants)).
* **The planks have their own section,** "Counterplan planks", after the CP texts in report.md's
  negative part (the PM's note after `v1-e32-t20` merged). The contents list links it. t20's
  before-the-reorder fixture and its identity test are removed: the golden report.md still pins every
  byte ([below](#after-v1-e32-t20-the-planks-own-section)).
* **On hspolicy26** ([below](#the-operators-refill-and-the-dry-run-2026-10-25)):
  * **The operator's refill** read all 3,825 on-topic sources in 458.9 s, with 0 unread.
  * **Planks:** 475 found, 447 placed. Under a CP in negative files there are 158 distinct planks
    under 5 CPs, in 17 groups, with 0 withheld. `advantage-cp` has 92 planks, 13 teams and 9 groups.
  * **The dry run without `--publish`** took 75.7 s and wrote nothing. It shows 38 plank rows.
  * **Its scan:** 9 hits, 8 of them t09's in `top_cards.csv`. The other is **1 team-code hit in a
    plank table, not yet accepted** (digest `79cbed0d4d7e`): a question for the PM before the first
    publish. The PM ruled (a) on 2026-10-25: the operator reads it first
    ([below](#questions-for-the-pm)).
* **The counts that led to the rulings are kept below:** 152 planks under `advantage-cp`, most in
  lists after a colon stem, 24 naming an advantage in their own words.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| advantage-cp-planks | Done | The counts (2026-10-25), the PM's rulings (2026-10-25), then the reader, the cache counts, the report's grouping and section, the fixture and golden, the fill and dry-run scripts and the guide; after t20, the planks' own section; the operator's refill and dry run (2026-10-25) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, of advantage-CP blocks with several `should` analytics, plank labels or numbered planks, and of planks naming an advantage by heading, card or own words, or none, sent to the PM with the proposed plank rule | PASS | [The counts](#the-counts-hspolicy26-through-2026-10-20), [the proposed rule](#the-proposed-plank-rule), [the questions](#questions-for-the-pm), sent 2026-10-25 and ruled on the same day. Nothing was built before the ruling |
| ac2: after the ruling, on synthetic sources, report.md shows each multi-plank CP's planks with team counts and what each solves or "not named", matching hand-written golden files; never beside a school or team code; a plank naming a school withheld and counted; tests shown failing first | PASS | `tests/fixtures/landscape/golden/report.md`'s States CP planks and plank coverage, hand-written from the fixture README's new "Planks" table, matched on the renderer's first run (`test_rendering_the_fixture_matches_the_golden_file[report.md]`). Never beside a school or team code: `test_texts_a_text_is_never_beside_a_school_or_team_code`, which dumps the whole texts model with its planks, now non-empty. Withheld and counted: `test_planks_a_plank_naming_a_school_is_withheld_and_counted`, and `CpPlanks.withheld == 1`. Red runs: [below](#checks-shown-failing-for-their-reason) |
| ac3: the operator's refill of the analytic-text cache and a dry run without `--publish` on hspolicy26, with the scan's hits by section (operator) | PASS | The operator ran both from this worktree on 2026-10-25 ([below](#the-operators-refill-and-the-dry-run-2026-10-25)). The refill: 3,825 sources, 0 cached, 3,825 parsed, 0 unread, cache written, in 458.9 s. The dry run: nothing written, 7 files planned, in 75.7 s. Scan, 9 hits by section: 1 team code in report.md's plank table, not yet accepted; 4 team codes, 3 schools and 1 tournament in `top_cards.csv`, all accepted; digest `79cbed0d4d7e` |
| advantage-cp-planks node: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/application/test_landscape_report.py -q` under `perl -e 'alarm 100'` → 81 passed (76 before this task's tests) |
| PM ruling 2: a mutant where a list plank under a stem that fails the guard still shows | PASS | "list plank under a stem failing the guard shows": 4 failed ([below](#mutants)) |
| PM: mutants on the list boundary (past the first card, the 60-word cap), the alias-only label read as a plank, a partial-word alias match, and a plank double-counted in the totals | PASS | 2, 1 (removed) and 1 (off by one), 4, 1 and 2 failed ([below](#mutants)) |

## The counts (hspolicy26, through 2026-10-20)

### How they were read

* **Guards.** Every run was read-only and started from a check, made by the script itself:
  * no `DEBATE_*` variable set;
  * no `caselist pull` running.
* **Time limits.** Each run had `perl -e 'alarm 115'` on the interpreter. Its parent also set its
  own 100 s alarm, which unwinds through the pool runner's `finally` and stops the workers.
* **Orphans.** After every run, a check for my worktree's spawn workers found none.
  * Six workers from the `dev-preview` worktree, with their parent alive, were someone else's run.
* **The guard fired once:** see [Decisions 4](#decisions-and-assumptions).
* **Load.** The load average was 4 to 12 on 11 cores, so the pools ran 7 workers.
* **Output.** The script is a scratch file outside the repository.
  * It printed counts only.
  * Its scratch files hold digests, element indexes, word counts, flags, position ids and taxonomy
    aliases. They hold no paragraph text and no names.
* **The sources:** t02's reader (`read_seed_sources`), as t11 read them. That is 3,825 on-topic
  sources, of which **2,070 are negative**.
  * Each source was parsed in memory by the code's parser, under a placeholder path, through t09's
    `blob_jobs`.
  * All 2,070 parsed: 0 failed.
* **t11's reader and placement, reused:**
  * `section_paragraphs_of`;
  * `heading_placement`, the label's own `section_path` cut as a card's, normalized with the team's
    names and the caselist's schools taken out;
  * `passes_actor_guard`;
  * `read_analytic_texts`, for a cross-check.

  There is no second placement.
* **Terms:**
  * **A CP text by its place** is t11's: a `should` analytic the store does not keep, of at most 120
    words, whose nearest placed heading is a CP the team reads.
  * **A block** runs from one pocket, hat or block heading to the next.
  * **Teams** are the negative disclosing teams' opaque identities.
* **Naming an advantage** uses t02's alias table, whole phrase only:
  * **A heading** names one when it normalizes to an alias of an advantage, or to `solves <alias>`
    (also `cp solves`, `<alias> solvency`).
  * **A card** names one when its tag holds `solves <alias>` as whole words, or is an alias.
  * **A plank's own words** name one when they hold an alias as a whole phrase.
  * "Advantage" means a position of kind `advantage`, on the aff side. An aff plan's alias
    (`medicare for all`) is counted apart.

### Blocks under each CP (the first pass, all 2,070 negative sources)

**The CPs selected:** `advantage-cp`, plus every CP with a block holding two or more `should`
analytics. That adds `states-cp` and `nhs-cp`, and no other CP.

| | advantage-cp | states-cp | nhs-cp |
|---|---|---|---|
| Blocks with a CP text by its place (blocks, documents, teams) | 31, 30, **14** | 101, 100, 40 | 6, 6, 4 |
| ... with 2 or more `should` analytics | **1, 1, 1** | 13, 13, 6 | 1, 1, 1 |
| ... with 2 or more past the actor guard | 0 | 8, 8, 5 | 0 |
| ... with an inline plank label (`Plank 2:`, `2.`, `Second,`) | 7, 6, 5 | 29, 12, 4 | 0 |
| ... with a plank label on its own paragraph | 0 | 0 | 0 |
| Plank headings (`Plank 1 ...`) in the CP's section | 3 headings, 1 doc, 1 team | 0 | 0 |
| **One paragraph with numbered planks** (2 or more `1.`, `(1)` or `Plank 1`) | 0 | 0 | 0 |
| One `should` analytic with 2 or more ordinals (`first ... second`) | 0 | 0 | 0 |
| One `should` analytic with 2 or more `should`s | 0 | 2, 2, 2 | 0 |

The other CPs with a CP text by its place have no block with two `should` analytics:
* `public-option-cp`: 13 blocks, 8 teams;
* `vouchers-cp`: 5 blocks, 4 teams;
* `delay-cp` and `smokers-pic`: 3 blocks each;
* `taxes-pic`: 1 block.

### What follows the CP text (the second pass)

This pass re-read every negative source holding the CP's section: a stored card any of whose path
prefixes places under the CP, or a CP-text block from the first pass. That is 264 sources for the
three CPs, then 25 for the others. In it, the "list" is every paragraph after the CP text in its
block, up to the first card or heading, that is an analytic, undertag or unstyled paragraph the
store does not keep.

| CP text by its place | advantage-cp | states-cp |
|---|---|---|
| CP texts (texts, documents, teams) | 32, 30, 14 | 114, 100, 40 |
| ... under 20 words | 30 | 75 |
| **... ending in a colon** (a stem) | **24, 23, 12** | 65, 64, 25 |
| Stems followed by 2 / 3 / 4 / 5 or more list paragraphs | 2 / 3 / 4 / **15** | 20 / 5 / 4 / 36 |
| Stems whose list ends at a card / a heading / the CP's end | 22 / 1 / 1 | 65 / 0 / 0 |
| Texts not ending in a colon (documents, teams) | 8, 8, 4 | 49, 42, 25 |
| Distinct texts; teams on the commonest | 6; **12** | 38; 9 |

**Every stem passes the actor guard:** 24 of 24 under `advantage-cp` and 68 of 68 under the other
CPs. **No list plank passes it on its own words:** 0 of 143, and 6 of 279 elsewhere. The plank names
no actor; the stem does.

**Other findings in the `advantage-cp` section.** 80 negative documents (38 teams) hold the section,
counting cards anywhere under it.
* **50 documents (26 teams) hold no CP text by its place.** 44 of them hold the CP's cards only:
  solvency files, or a text the store keeps as a card's tag.
* **Cards naming an advantage:** 32 tags in 20 documents, 13 teams. 9 lists (6 teams) are followed,
  before the next CP text, by such a card. It comes after the whole list, so it names no one plank.
* **Headings naming an advantage** (`Solves <advantage>`): 14 in 10 documents, 4 teams. None follows
  a list.
* **`solves` with words that are no alias** (an impact the taxonomy does not name): 87 card tags (21
  teams) and 27 headings (9 teams).

### The planks under the proposed rule

The rule is [below](#the-proposed-plank-rule). A list plank is at most 60 words; the longest found
is 47.

| | advantage-cp | states-cp | public-option-cp, taxes-pic, vouchers-cp |
|---|---|---|---|
| **Planks** (planks, teams) | **152, 14** | 297, 28 | 4, 4 and 5; one team each |
| ... in a list after a stem | 143, 12 | 266, 25 | all 13 |
| ... separate, in the CP text's block (a further `should` analytic past the guard, or a labelled plank) | 9, 3 | 31, 4 | 0 |
| List planks' words: median, 90th percentile, longest | 9, 23, 31 | 7, 17, 47 | |
| **Named by a heading or card under it** | **0** | 0 | 0 |
| **Named by its own words, one advantage** | **24, 10** | 10, 5 | 2 (`public-option-cp`) |
| ... of which say `solves <advantage>` | 1 | 0 | 0 |
| Its own words name 2 advantages or more | 0 | 4, 2 | 0 |
| **Naming none** | **128, 14** | 283, 28 | 11 |
| Its own words name an aff plan (not counted as solving) | 5, 2 | 20, 5 | 0 |
| **Naming a school** (to be withheld) | 0 | 0 | 0 |
| Distinct planks, by normalized words; read by one team | 103; **92** | 66; 47 | 13; 13 |
| Team-plank pairs; on the top 3 / 5 / 10 | 114; **6** / 10 / 20 | 152; 44 / 72 / 87 | |

**The advantages planks name in their own words, all by a one-word alias.**
* Under `advantage-cp`: `costs` 6, `budgets` 5, `innovation` 3, `disease` 3, `coverage` 2,
  `inequality` 2, `pandemics` 2 and `bioterror` 1. No multi-word alias matched.
* Under `states-cp`: `coverage` 7, `costs` 4, `access` 4, `budgets` 2 and `innovation` 1.

**Short list paragraphs.** 16 list paragraphs under `advantage-cp` are 3 words or fewer. 14 of them
are unstyled, and 4 of those are an advantage's alias and nothing more. They may be a label naming
the next plank; the counts cannot tell.

**t11's cross-check.** In the first pass's multi-plank blocks, t11 keeps plank 1 as its CP text by
place in 4 of the 6 `advantage-cp` blocks, and keeps none of planks 2 onward (13 planks).

### Runtimes

| Pass | What it read | Wall-clock |
|---|---|---|
| Sample | 52 negative sources | 40.1 s, the reader 31.6 s of it |
| **First pass**, 8 shards, 7 workers | all 2,070 negative sources | 60.6, 55.5, 52.8, 74.4, 65.7, 63.5, 59.7 and 53.7 s; the reader 25.9 to 33.6 s of each |
| **Second pass**, 2 shards, 7 workers | the 264 sources with the three CPs' sections | 45.5 to 64.0 s a shard, three times (two more fields were added each time) |
| Second pass, the other CPs | 25 sources | 32.3 s |
| Aggregations | the reader and the scratch files | under 40 s each |

## The proposed plank rule

1. **A plank hangs off a CP text t11 already reads**, by label or by its place, past t11's guard. A
   CP text has planks in one of two shapes:
   * **A list.** The CP text ends in a colon. Its planks are the paragraphs that follow it in its
     block, up to the first card or heading. Each is an analytic, undertag or unstyled paragraph the
     store does not keep, of at most 60 words. A list paragraph that is only an advantage's alias
     (4 today) names the plank after it and is not a plank (question 1).
   * **Separate planks.** In the CP text's block, each further `should` analytic past the actor
     guard is a plank, and so is each paragraph opening with a plank label (`Plank 2:`, `2.`,
     `Second,`).

   A CP text with neither shape stays one text, as today.
2. **The actor guard** applies to every plank. A list plank passes it through its stem, since the
   stem names the actor and the plank never does (0 of 143). A separate plank passes it on its own
   words, or by its label (question 2).
3. **What it solves**, never guessed. A plank solves every advantage named:
   * by a card under it, between it and the next plank, whose tag says `solves <alias>` or is an
     alias;
   * by a heading under it that normalizes to an alias or to `solves <alias>`;
   * or by its own words holding an advantage's alias as a whole phrase.

   Otherwise it shows "solves: not named". Only positions of kind `advantage` count. A card after a
   whole list names no one plank. An impact the taxonomy does not name is not shown (question 3).
4. **Shown in report.md only,** under the CP's texts, never beside a school or team code. Planks are
   grouped by their normalized words (t11's digest), with their team counts, and cut off at t11's
   top 3 (question 4). A plank naming a school of the caselist is withheld and counted: 0 today.

## The PM's rulings, applied

The PM ruled on the counts on 2026-10-25:
* (1) the rule as written, lists included, and (a): an alias-only list paragraph is a label;
* (2) (a): a list plank passes the guard through its stem;
* (3) (a): advantages only, by any alias, as whole phrases;
* (4) (b): the top 3 per advantage within each CP.

They are a PM-ruling comment above the spec's `acceptanceCriteria`, committed before the build
(`f6fc110`). The branch was first synced onto `origin/dev` with `scripts/task sync`. That brought in
t15's merge and the PM batch of 2026-10-25, with no conflict; the branch was not on the remote, so
nothing was pushed.

### What was built

| Where | What |
|---|---|
| `domain/landscape_texts.py` | `AnalyticTextKind.CP_PLANK`, its forms `LIST` and `SEPARATE`. A plank's reading adds its CP text's paragraph (`stem_element_index`), the advantages it solves (ids, sorted) and its cards saying `solves` with other words, a count. No words. `PlankGroup` and `CpPlanks`, the report's groups; `LandscapeTexts.planks`. `TextCoverage` gains the plank counts |
| `arguments/landscape/analytic_texts.py` | The planks of each CP text the reader finds (`_Planks`), the plank label (`plank_words`), the advantage aliases of the taxonomy (`AnalyticTextRules.advantage_aliases`), matching them as whole phrases (`advantage_aliases_in`), reading a plank back without its label. `_RULE_VERSION` is `analytic-texts-2` and the 60-word cap is in the digest, so the cache refills |
| `application/ports/analytic_text_store.py`, `application/analytic_texts.py` | The cache keeps each source's alias-only labels and refused list planks, beside t11's guard count; the run and the report's inputs carry them; planks are quoted like CP texts |
| `application/landscape_report.py` | Planks counted as a CP text is, then per CP grouped by what they solve (`_cp_planks`): the top 3 per group through t11's `top_texts`, "not named" last, the totals once per plank, a school-naming plank counted once |
| `arguments/landscape/render.py` | Under the CP texts' coverage, where every plank went; under each CP's texts table, its planks' totals, one table by what they solve, and each group's "and N more planks" |
| `testing/landscape_report.py` | The fixture's loader reads a plank's `stem`, `solves` and counts |
| `tests/fixtures/landscape/` | The States CP's planks in `analytic_texts.json`, by hand; the README's "Planks"; the golden `report.md` |
| `scripts/read_landscape_texts.py` | Prints the plank counts, and with `--quote` the planks naming each advantage alias in their own words |
| `docs/guides/landscape-taxonomy.md` | "A CP's planks" |

### Checks shown failing for their reason

Each suite ran red before its code, against a skeleton that found no planks:

| Suite | Red |
|---|---|
| `arguments/landscape/test_cp_planks.py` (the reader) | 12 failed, 9 passed. The 9 are the reading's validation cases (8) and the alias table (1), written with the domain types before these tests, so they never ran red |
| `application/test_analytic_texts.py` (the service) | 2 failed, 16 passed, both on the missing counts (`AttributeError`); the plank assertions before them passed on the reader |
| `application/test_landscape_report.py` | 5 failed, 76 passed. `test_planks_out_of_range_files_are_not_read` passed against the skeleton: t11's loop already counted in-range planks by their kind, and the new counts default to 0 |
| `arguments/landscape/test_render.py`, the golden `report.md` | 1 failed, 35 passed |
| `tests/scripts/test_read_landscape_texts.py` | Written with the script's change; then run against the committed script: 2 failed, 2 passed (the data-directory and empty-store guards). The new script was restored from a copy, byte for byte |
| `integrations/landscape/test_analytic_text_store.py` | Its "no field for text" pin failed on the new fields, and was extended by hand with the five: two counts, a paragraph index, the advantages' ids, a count |

Two expectations of t11's changed with the rulings, by hand:
* **`test_the_first_should_analytic_of_a_block_under_a_placed_cp_is_its_text_by_place`.** Its block's
  second `should` analytic, past the guard, is now the first text's separate plank (ruling 1).
* **The CP-text coverage row: 16 found and 2 under no heading.** The fixture's `b6` gained a labelled
  CP text with no actor, under no heading, whose list the guard refuses. t11's golden lines changed to
  match: 16 found, 3 not placed, 2 of them under no heading.

### Mutants

There were 15 targeted mutants. Each:
* was applied to one file, after a check that its target occurs exactly once;
* ran the six covering suites (233 tests) in a fresh process, with bytecode writing off and
  `__pycache__` cleared;
* was restored from a copy and compared byte for byte.

No Hypothesis is used, so there is no example database to isolate (agreement 8). Every run took 1.9
to 2.1 s.

| Rule | Mutant | Failed |
|---|---|---|
| List boundary | the list goes on past the first card | 2 |
| List boundary | no 60-word cap | 1 |
| List boundary | the cap at 59 words (`<` for `<=`) | 1 |
| Label | an alias-only paragraph read as a plank | 4 |
| Label | the label names no plank | 2 |
| Naming | an alias matched inside a word | 1 |
| Naming | a card under a plank names nothing | 1 |
| Guard | a list plank under a stem failing the guard still shows | 4 |
| Totals | a plank naming two advantages counted twice | 2 |
| Groups | no top-3 cap per advantage | 2 |
| Groups | "not named" not last | 2 |
| Groups | a two-advantage plank under its first advantage only | 2 |
| Withholding | a school-naming plank never counted | 4 |
| Withholding | counted once per group, not per CP | 4 |
| Withholding | shown (`top_texts` never withholds) | 10 |

**Two survivors on the way, both settled before the final run:**
* **"A withheld plank still shown" survived.** The report skipped a school-naming plank before grouping,
  and `top_texts` also withholds it in every group, so the skip could not be told from its absence.
  The skip was removed (agreement 8). Withholding now rests on `top_texts`, which the last mutant
  checks; the set that counts a withheld plank once per CP stays.
* **"Counted once per group" survived first.** The fixture's school-naming plank named no advantage,
  so it sat in one group either way. It now names both advantages; the golden is unchanged, since a
  withheld plank shows in neither group.

A refinement I tried, leaving a withheld plank's teams out of the group's teams that order the
groups, could not be told apart on the fixture either, and was reverted, not kept untested.

### Before the report (working agreement 10)

* **The affected set** (`scripts/affected_tests.py`) is **191 of 477 test files**.
  * I ran it once, `-n auto -m "not slow and not live"`, under a 115 s limit on the interpreter. The
    limit stopped it at about 89% (exit 142), with the load at 4 to 7.
  * Its 17 worker processes exited on their own once their parent's channel closed, and none was
    left.
  * So, by agreement 10, the whole affected set is left to the pull request's `ci`.
* **Within the limit, the directories of what changed and the always-run list:**

  | Run | Result |
  |---|---|
  | `arguments/landscape`, `integrations/landscape`, `tests/config`, the application's landscape, analytic-text and plan-text tests, the landscape scripts' tests | 999 passed in 3.0 s |
  | The domain's landscape tests, `tests/architecture`, `tests/specs`, `tests/smoke/test_landscape_smoke.py` | 417 passed in 6.7 s |
  | `packages/debate_cli/tests` without `bucket_mode/` | 954 passed in 38.7 s |
  | `bucket_mode/` without `test_bucket_mode_kills.py` | 37 passed in 22.6 s |

  **The bucket-mode kill tests** kill real subprocesses, and ran 15 tests in 110 s in one process under
  this load. In the whole CLI run they held the session past the limit twice, after every other test
  had passed. They import nothing this task changed, so they are left to `ci`.
* **The cheap checks:**
  * `ruff format --check .`: 1319 files already formatted;
  * `ruff check .`: all checks passed;
  * `pyright packages/debate_core`: 0 errors;
  * `lint-imports`: 16 kept, 0 broken;
  * `check_thin_handlers.py`: 54 handlers within 25 statements;
  * `docs_index.py --check-descriptions`: OK;
  * `check_command_blocks.py --base origin/dev`: OK;
  * `check_links.py`: OK;
  * `pre-commit run check-merge-conflict --all-files`: passed;
  * `validate_specs.py`: OK, 453 files.
* **No shared test ground changed:** no `pyproject.toml`, `uv.lock`, conftest or pytest plugin. So no
  whole-selection hand-off.

### Counts by alias

The PM asked for these, to see whether a one-word alias over-matches.
* **From the counts** (the same whole-phrase match, on the planks the rule finds):
  * under `advantage-cp`: `costs` 6, `budgets` 5, `innovation` 3, `disease` 3, `coverage` 2,
    `inequality` 2, `pandemics` 2 and `bioterror` 1;
  * under `states-cp`: `coverage` 7, `costs` 4, `access` 4, `budgets` 2 and `innovation` 1;
  * under `public-option-cp`: `coverage` 1 and `costs` 1.

  Every match is a one-word alias. No multi-word alias matched.
* **From the operator's refill** (every plank read again, any CP, each copy counted): `budgets` 6,
  `costs` 6, `coverage` 6, `innovation` 3, `disease` 2, `inequality` 1 and `pandemics` 1. That is 25
  plank copies naming an advantage in their own words, every one by a one-word alias.

The counts cannot say whether a match is right: they print no plank. That would take the coach
reading the shown planks in report.md, or the operator reading the dry run's.

## After v1-e32-t20: the planks' own section

`v1-e32-t20` merged into `dev` while the operator ran the refill. `scripts/task sync` rebased this
branch onto it. Two files conflicted, both resolved keeping both sides:
* the report module's imports;
* `render.py`, where t20 split the overviews out of the texts section.

The branch was not on the remote, so nothing was pushed. Then, as the PM asked:
* **"Counterplan planks" is its own section,** in report.md's negative part, right after "Counterplan
  texts, alternatives and roles of the ballot". The renderer's negative part lists it after the texts
  section, so t20's contents list links it with no other change.
  * It holds where every plank found went, then each CP's plank table.
  * The CP texts section is t11's again. Each CP's text stays there, shown once, above the CP's planks
    in the next section.
  * The golden report.md was edited by hand to match: the coverage and the States CP's table moved, the
    section's opening paragraph is new, and the contents line gained its link. It matched on the
    renderer's first run.
  * t20's heading-order test gained the new heading, by hand.
* **`tests/fixtures/landscape/report_before_sides_together.md` and
  `test_every_section_of_report_md_is_byte_identical_to_its_section_before_the_reorder` are removed.**
  Their job, proving t20's reorder changed no section, is done, and the golden report.md still pins
  every byte of the rendered report. Their helper `_by_heading` went with them, and the module's
  docstring says why.
* **The dry run's section names:** a hit in a plank table is now under "Counterplan planks: plank
  table". The operator's dry run ran before the move, so it printed "Counterplan texts: plank table"
  for the same line. A hit's digest is keyed on its file, kind, term and line, never its place, so
  `79cbed0d4d7e` is unchanged.
* **After the sync**, the directories of what changed and the always-run list:
  * 1,366 passed in 9.5 s (the landscape suites, the scripts' tests, `tests/config`,
    `tests/architecture`, `tests/specs`, the landscape smoke test);
  * 1,084 passed in 36.8 s (the domain's landscape tests and `packages/debate_cli/tests` without
    `bucket_mode/`).
  * The affected set is 193 of 481 files. Its run before the sync stopped at its alarm, so it is left
    to `ci`.
  * `pyright packages/debate_core` 0 errors; `lint-imports` 16 kept; `ruff format --check` 1,334
    files; `check_thin_handlers.py` OK.

## The operator's refill and the dry run (2026-10-25)

Both were run by the operator from this worktree, with the guards of t11's blocks, before the merge.

**The refill, `scripts/read_landscape_texts.py --caselist hspolicy26 --quote`.** Its whole output:

```text
Read hspolicy26 2026.10.20-docx-6 through 2026-10-20: 3825 sources on policy-2026-27-nhi, 2070 negative, 1770 affirmative.
Analytic texts: 3825 sources, 0 cached, 3825 parsed, 0 refused by the parser, 0 unread; cache written.
  CP_TEXT: 235 found, 171 placed
  K_ALTERNATIVE: 545 found, 90 placed
  ROLE_OF_THE_BALLOT: 50 found, 1 placed
  OVERVIEW: 1108 found, 572 placed
  CP_PLANK: 475 found, 447 placed
CP texts by place in negative files: 151 kept by the actor guard, 5 refused.
CP planks: 4 alias-only labels, 4 list planks refused with their CP text, 7 cards under a plank saying solves with other words.
Quoted: 198 sources read again for 705 texts; 705 read as they were read, 0 not, 0 unread.
Planks under a CP in negative files: 158 under 5 CPs, in 17 groups by what they solve, 0 withheld for naming a school.
  advantage-cp: 92 planks, 9 groups, 0 withheld
  public-option-cp: 4 planks, 3 groups, 0 withheld
  states-cp: 53 planks, 3 groups, 0 withheld
  taxes-pic: 4 planks, 1 groups, 0 withheld
  vouchers-cp: 5 planks, 1 groups, 0 withheld
Planks naming an advantage alias in their own words: budgets 6, costs 6, coverage 6, innovation 3, disease 2, inequality 1, pandemics 1.
Runtime 458.9 s.
```

* **t11's lines are unchanged:** 235, 545, 50 and 1,108 found, and 151 kept and 5 refused by the guard.
  The rules digest moved, but no CP text, alternative, role of the ballot or overview reads
  differently.
* **The 4 alias-only labels** match the counts' 4.
* **The plank figures are the reader's, and smaller than the counts' approximation.** The counts' pass
  hung lists off every `should` analytic placed on a CP, and found 152 under `advantage-cp`. The reader
  hangs planks only off a CP text t11 reads, and finds 92 distinct ones there.
* **The 7 cards saying `solves` with other words** are over every plank read; the report counts the 5
  under counted planks.
* The runtime, 458.9 s, is inside the PM's estimate of about 9 minutes.

**The dry run, `scripts/landscape_dry_run_by_section.py --caselist hspolicy26`,** on the warm cache.
Its whole output:

```text
Dry run of hspolicy26 through 2026-10-20, taxonomy 1.2.0: nothing written; 7 files planned.
Planks: 158 under 5 CPs, in 17 groups by what they solve, 38 rows shown, 0 withheld for naming a school.
  states-cp: 53 planks, 26 teams, 3 groups, 0 withheld
  advantage-cp: 92 planks, 13 teams, 9 groups, 0 withheld
  public-option-cp: 4 planks, 1 teams, 3 groups, 0 withheld
  taxes-pic: 4 planks, 1 teams, 1 groups, 0 withheld
  vouchers-cp: 5 planks, 1 teams, 1 groups, 0 withheld
Planks found: 475 in 97 files; 422 counted, 25 elsewhere, 21 under headings that place nothing, 7 under no heading; 4 refused with their CP text, 4 alias-only labels, 5 cards saying solves with other words, 0 not read again.
Scan: 9 hits, 1 not yet accepted (digest 79cbed0d4d7e).
  report.md | Counterplan texts: plank table | team_code: 1 (1 not yet accepted)
  top_cards.csv | (whole file) | team_code: 4 (0 not yet accepted)
  top_cards.csv | (whole file) | school: 3 (0 not yet accepted)
  top_cards.csv | (whole file) | tournament: 1 (0 not yet accepted)
Hits in report.md's plank tables: 1.
Runtime 75.7 s.
```

* **The report's planks agree with the refill's:** 158 under the same 5 CPs, in 17 groups, 0 withheld.
* **38 plank rows** are shown under the cut-off of 3 per advantage.
* **Every plank found is counted somewhere:** 422 + 25 + 21 + 7 = 475.
* **The scan, by section.**
  * The 8 hits in `top_cards.csv` are t09's: 4 team codes, 3 schools and 1 tournament, all already
    accepted.
  * **1 new hit: a team code in a plank table.** A word of some plank's own text is a disclosed team
    code. The counts cannot say which word; the CLI's `--dry-run` shows the line in the operator's
    terminal.
  * The plank-table hit is the only one not yet accepted. So the first publish stops on digest
    `79cbed0d4d7e` until the operator reads it ([question](#questions-for-the-pm)).
* The dry run took 75.7 s, against t11's 74 s.

## Files changed

* **`debate_core.domain`:** `landscape_texts.py`.
* **`debate_core.arguments.landscape`:** `analytic_texts.py`; `render.py`, with the "Counterplan
  planks" section in the negative part.
* **`debate_core.application`:**
  * `analytic_texts.py`, `landscape_report.py`, `ports/analytic_text_store.py`;
  * `landscape_scan.py`: `hits_by_section`, the dry run's hits by section;
  * `landscape_run.py`: the result keeps its rendered files in memory.
* **`debate_core.testing`:** `landscape_report.py`, the fixture's loader ([Deviations](#deviations-from-the-spec)).
* **Tests:**
  * `packages/debate_core/tests`: `arguments/landscape/test_cp_planks.py` (new); `test_analytic_texts.py`
    (t11's two-`should` expectation); `application/test_analytic_texts.py`;
    `application/test_landscape_report.py`; `integrations/landscape/test_analytic_text_store.py`;
  * `tests/scripts/test_read_landscape_texts.py`.
* **`tests/fixtures/landscape`:** `synthetic_caselist/analytic_texts.json` and its README, by hand;
  `golden/report.md`, by hand; `report_before_sides_together.md` removed (the PM's note of 2026-10-25),
  with its test in `arguments/landscape/test_render.py`.
* **`scripts/read_landscape_texts.py`**, and **`scripts/landscape_dry_run_by_section.py`** (new) with
  `tests/scripts/test_landscape_dry_run_by_section.py`; `application/test_landscape_scan.py` and
  `test_landscape_run.py`.
* **`docs/guides/landscape-taxonomy.md`:** "A CP's planks".
* **The spec:** the PM's rulings as a comment above `acceptanceCriteria`, and the `packages` amendment.
* **This report.**

## Deviations from the spec

None open. **`debate_core.testing`**, the fixture's loader, was outside `constraints.packages`; the PM
ruled on 2026-10-25 to add it. The amendment is a PM-ruling comment above `packages` in the spec.

## Decisions and assumptions

From the counts (2026-10-25):

1. **A list was counted although the spec names only `should` analytics, labels and numbered
   paragraphs.** The `should` count alone (1 block) could not explain 14 teams. The second pass
   looked at what follows the CP text, and found the planks there.
2. **The CPs counted** are `advantage-cp` and every CP with a block of two or more `should`
   analytics (`states-cp`, `nhs-cp`), as asked. The other CPs were then checked for lists too:
   three have one, each one team's.
3. **"An alias of an aff-side position"** was split into advantages and aff plans. A plank naming the
   plan (`medicare for all`) says what it changes, not what it solves.
4. **The pull guard fired once, falsely.** It matched another session's shell, whose own command line
   held the text `pgrep -f "caselist pull"`. I made the script skip shell processes (`zsh`, `bash`,
   `sh`) and kept everything else. A real pull runs as `uv` or Python, and would still stop it. That
   shard was then run again.

From the build:

5. **No heading can be under a plank.** The proposed rule named "a card or heading under the plank".
   Planks are read within their CP text's block, and a heading ends the block, so no heading lies
   between a plank and the next. The alias-only label of ruling 1 is what names a list plank from
   above it.
6. **A plank is placed with its CP text,** whatever that is placed under. It counts as a CP text does:
   under a CP, READS, in a round not on the other side. Elsewhere it is counted where it went.
7. **The planks of a CP text run to the block's next heading or next CP text.**
   * The list ends at the first card, as ruled. Separate planks can follow it in the same block.
   * A card's tag names the most recent separate plank before it. A card after a list names no plank.
8. **A list paragraph holding `should` is a list plank.** It is not a separate plank too: each
   paragraph is read once.
9. **An alias-only label** is a list paragraph that normalizes, as a heading does (`2. Medical
   Innovation:`), to an advantage's alias.
10. **A plank's advantages are the union over its copies.** Two files with the same words may name
    different advantages, for example when one has a card under it. Each name comes from a file, so the
    union guesses nothing.
11. **The CP's total counts its distinct planks, the withheld one included.** It says how many are
    withheld (`8, read by 6 teams ... 1 is withheld`).
12. **The groups are ordered** by the distinct teams with a plank in them, then the advantage's id,
    with "not named" last. A group's teams are every one of its planks' teams.
13. **"The stem once above its CP's plank groups"** is t11's texts table, unchanged. A CP's planks
    hang off several of its texts, so they are grouped per CP under that table, not per text.
14. **The fill's counts by alias** count each plank read again, not each distinct plank, over every
    CP. They show how often an alias matches, which is what the PM asked to see.
15. **The fixture keeps t11's golden lines.** `b6`'s second text gained a colon, which leaves its
    digest unchanged, and the list hangs off it. The only t11 line that moved is the new labelled
    text's.
16. **The dry run that reports the scan by section is a script, not the CLI command.** The CLI's dry run
    prints each hit's line, which may name a team, for the terminal only, and a dry run writes no
    report.md to map lines to sections. t11 counted its sections with a scratch script. The script
    runs the CLI's own service, and the run's result now keeps the rendered files, in memory only, for
    `hits_by_section`. Only report.md is counted by section: the school view's headings are schools.
    A hit inside a CP's plank table is counted apart. Its tests: `test_landscape_scan.py` (2, red then
    green), `test_landscape_run.py`'s in-memory files (red on the missing field), and the script's (2,
    red against a stub).
17. **The refill counts planks grouped and withheld, under a CP, in negative files,** with `--quote`.
    Withholding needs the words read again. The groups count only planks that could be read again and
    are not withheld, as the report shows them. Its test gained a list plank naming a school of the
    caselist, and ran red against the committed script.

## Operator follow-ups

1. **Done, 2026-10-25: 458.9 s, its output [above](#the-operators-refill-and-the-dry-run-2026-10-25).**
   Refill the analytic-text cache for hspolicy26 (expected runtime about 9 minutes on a loaded
   machine, the PM's estimate; t11's first fill took 551 s).
   * **Why it is needed:** the rules digest changed, so every on-topic source of the newest snapshot
     is read again through the parser.
   * **What it writes:** only `~/.debate-research/dev/landscape/analytic_texts/hspolicy26.jsonl`, with
     digests, indexes, ids and counts, no text.
   * **What it prints:** counts only, with `--quote` the planks read again and their counts by alias.
   * **Its guards:** it refuses to start if a `DEBATE_*` variable is set or a `caselist pull` is
     running.

   First, from the task worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t16-advantage-cp-planks
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/read_landscape_texts.py --caselist hspolicy26 --quote; fi
```

   **Success looks like:**
   * the `Read hspolicy26 ...` line. Through 2026-10-20 it says 3825 sources, 2070 negative and 1770
     affirmative; a newer snapshot says more;
   * an `Analytic texts:` line with `0 cached` (the rules digest changed), a parsed count above zero,
     `0 unread` and `cache written`;
   * each kind's found and placed counts, `CP_PLANK` above zero, then the `CP texts by place` and
     `CP planks:` lines;
   * the `Quoted:` line with `0 not` and `0 unread`;
   * the `Planks under a CP in negative files:` line, planks and groups above zero, with a line per CP;
   * the `Planks naming an advantage alias in their own words:` line;
   * the `Runtime` line.

   Paste every line back. A `STOP:` line means nothing ran.
2. **Done, 2026-10-25: 75.7 s, nothing written ([above](#the-operators-refill-and-the-dry-run-2026-10-25)).**
   Then the dry run, without `--publish`, on the warm cache (expected about 75 s; t11's took 74 s).
   * **What it runs:** `scripts/landscape_dry_run_by_section.py`, the CLI's own landscape service,
     built by its container, as `landscape report --dry-run` runs it.
   * **What it prints:** counts only. That is the planks shown, grouped and withheld, and the scan's
     hits by file, report.md section and kind. It never prints a hit's term or line, or a text.
   * **What it writes:** nothing. Run it after the refill, never before: without the refill, the dry run
     would read every file again and write no cache.

   From the same worktree:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/landscape_dry_run_by_section.py --caselist hspolicy26; fi
```

   **Success looks like:**
   * a `Dry run of hspolicy26 through ...: nothing written; 7 files planned.` line;
   * a `Planks:` line with planks and groups above zero, a line per CP, and the `Planks found:` line;
   * the `Scan:` line with its digest, a line per file, section and kind, and the `Hits in report.md's
     plank tables:` line. t11's dry run had 8 hits, all in `top_cards.csv`, digest `81374e646621`;
   * the `Runtime` line.

   Paste every line back. The CLI's own `--dry-run` shows each hit's line, for the terminal only, if a
   hit needs reading.
3. **The first publish with the planks** is the PM's to coordinate, after the review, under the ruling
   of 2026-10-25 on the plank-table hit ([questions](#questions-for-the-pm)):
   * the operator reads that hit's line in `debate-research landscape report --caselist hspolicy26
     --dry-run`;
   * if it is an ordinary word, the publish adds `--accept-scan-hits` with the digest that dry run
     prints (`79cbed0d4d7e` today);
   * if it names a team, nothing is published and withholding such planks becomes a follow-up task.

## Follow-up work

* **The CLI's JSON** does not carry the plank counts, as it does not carry t11's text counts
  (`LandscapeRunResult.analytic_texts` holds them for t05's command).
* **A card after a whole list** (9 lists, 6 teams, in the counts) names an advantage that no one plank
  can be given. Pairing them by order would be a guess; a rule for it, if the coach wants one, is a
  ruling first.

## Questions for the PM

**Answered.** The PM ruled on the counts on 2026-10-25 ([above](#the-pms-rulings-applied)). The
questions as sent are kept below.

**The question from the build** (`debate_core.testing` in `constraints.packages`) was ruled yes on
2026-10-25 and is in the spec.

**The question from the dry run was ruled (a) on 2026-10-25.** Before the first publish with planks:
* The operator reads the hit's line in the CLI's dry run.
* **If the word is an ordinary one,** as t09's `All` was, the operator publishes with
  `--accept-scan-hits` and the digest the dry run prints. Today that is `79cbed0d4d7e`; it changes if
  anything else in the scan changes.
* **If it really names a team,** nothing is published. Option (b) then becomes a follow-up task:
  withhold a plank that holds a disclosed team code as a whole word.

The question as sent:

```text
v1-e32-t16 question (session, 2026-10-25, after the operator's refill and dry
run). The refill read all 3,825 sources in 458.9 s; the dry run wrote nothing:
158 planks under 5 CPs, 17 groups, 38 rows shown, 0 withheld. Its scan has 9
hits: t09's 8 in top_cards.csv, all accepted, and 1 new one, a team code in a
report.md plank table, not yet accepted (digest 79cbed0d4d7e). A word of a
plank's own text is a disclosed team code; the counts cannot say which.

1. Before the first publish:
   (a) the operator reads that hit's line in `debate-research landscape report
       --caselist hspolicy26 --dry-run` and, if the word is an ordinary one, as
       t09's "All" was, publishes with --accept-scan-hits 79cbed0d4d7e;
   (b) withhold, as a school-naming plank is, any plank holding a disclosed team
       code as a whole word (a code change and a re-review).
   Recommendation: (a). The scan exists for this read, and policy 1.13's rule is
   about a plank beside a team code, not a word that happens to be one; if the
   operator finds a real team named, (b) as a follow-up.
```

The questions on the counts, as sent:

```text
v1-e32-t16 counts (session, 2026-10-25). Counts only, nothing built.
hspolicy26 through 2026-10-20, taxonomy 1.2.0, t11's reader and placement
(section_paragraphs_of, heading_placement, the actor guard), all 2,070
negative sources re-read in memory, 0 failed; then the 264 holding the CPs'
sections. Every run guarded and time-limited, no worker left behind.

What the counts show. An advantage CP's planks are a list, not more "should"
analytics. Under advantage-cp, 14 teams have a CP text by its place; only 1
block holds two "should" analytics and 6 blocks (5 teams) label their planks.
But 24 of the texts (23 docs, 12 teams) are a short stem ending in a colon
("... should:"), followed by one paragraph per plank with no "should" and no
actor (2 to 5+ paragraphs, ending at the first card). Word's list numbers are
not in the text. So t11 shows the stem (its 12-team "text") and drops every
plank, not only plank 2 onward. No CP has one paragraph with numbered planks.

Under the proposed rule (below):
- advantage-cp: 152 planks, 14 teams (143 in lists, 9 separate).
  No heading or card under a plank names an advantage. 24 planks (10 teams)
  name one in their own words, each by a one-word alias (costs 6, budgets 5,
  innovation 3, disease 3, coverage 2, inequality 2, pandemics 2, bioterror 1).
  128 name none. 9 lists are followed by a card naming an advantage, after
  the whole list. 0 name a school.
- states-cp: 297 planks, 28 teams; 10 name one advantage, 4 name two or
  more, 283 none. Three other CPs: 13 planks, one team each.
- advantage-cp's planks are almost all different: 103 distinct, 92 read by
  one team, 114 team-plank pairs; a top 3 per CP covers 6 of them.

The proposed rule. A plank hangs off a CP text t11 already reads. (a) A list:
the CP text ends in a colon, and its planks are the following paragraphs in
its block up to the first card or heading (analytic, undertag or unstyled, not
kept, at most 60 words). (b) Separate: further "should" analytics past the
guard, or paragraphs opening "Plank 2:", "2.", "Second,", in the CP text's
block. What it solves: a card or heading under the plank naming an advantage
by alias or "solves <alias>", or its own words holding an advantage's alias as
a whole phrase; every one named is listed; otherwise "solves: not named".
report.md only; a plank naming a school withheld and counted.

1. Approve the rule, lists included? And the 4 list paragraphs that are only
   an advantage's alias: (a) a label naming the plank after it, not a plank;
   (b) a plank like any other.
   Recommendation: the rule as written, and (a). Without lists the section
   would show 9 advantage-cp planks from 3 teams.

2. The actor guard on every plank. 24 of 24 stems pass it; 0 of 143 list
   planks do on their own words, since the plank names no actor.
   (a) A list plank passes through its stem; a separate one on its own words
       or its label.
   (b) Every plank on its own words: no list plank would show.
   Recommendation: (a).

3. What counts as naming. (a) Advantages only, by any alias, one-word ones
   included (all 24 matches are one-word); (b) also aff plans (5 advantage-cp
   planks name a plan); (c) multi-word aliases only (0 matches). Impacts the
   taxonomy does not name ("solves <other words>": 87 card tags, 27 headings)
   are not shown; showing them would quote a team's heading.
   Recommendation: (a).

4. The cut-off. (a) t11's top 3 distinct planks per CP, then "and N more
   planks, read by M teams": advantage-cp shows 6 of 114 team-plank pairs.
   (b) The top 3 per advantage solved within each CP, "not named" as one
   group: advantage-cp shows up to 27 planks (8 advantages and "not named").
   Recommendation: (b), since that is what the coach asked to see per plank;
   (a) if "top 3 per plank" meant per CP.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
