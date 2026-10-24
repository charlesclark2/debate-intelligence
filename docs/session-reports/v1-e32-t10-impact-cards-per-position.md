# Session report: v1-e32-t10-impact-cards-per-position

| | |
|---|---|
| Task | `v1-e32-t10-impact-cards-per-position` — Impact cards per DA and advantage in the landscape report |
| Spec | [`plan_specs/v1/e32-argument-landscape/t10-impact-cards-per-position.yaml`](../../plan_specs/v1/e32-argument-landscape/t10-impact-cards-per-position.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t10-impact-cards-per-position` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**The landscape report now lists each DA's and each advantage's impact cards** (up to 3 per
position) under its kind's table in report.md, and in a new `impact_cards.csv`. Each kind also says
how many of its documents carry no labelled impact. The rule is the PM's ruling of 2026-10-24 on the
counts below. It is pure functions in `arguments/landscape/impacts.py`, and the service applies it
card by card.

* **The rule** (recorded in the spec as a PM-ruling comment): an `impact` or `impacts` heading over
  the card, except `no impact`, `impact defense` and `impact turn(s)`; or a `turns case` heading; or
  a tag opening, after one leading enumerator, with one of the fifteen ruled words.
* **What counts:** only cards the report already counts as READS, at or above the threshold, in a
  round on the position's own side, so an ANSWERS card or a card on the other side is never an
  impact card.
* **Ranking:** by the distinct teams reading the cluster's *labelled* copies, then by cluster id.
* **What a row shows:** the tag and short cite exactly as parsed, the `raw/` source reference, and
  FILE_IMPORT.

**The build reproduces the ruled counts exactly** on hspolicy26 through 2026-10-20 (read-only, dry
run, 44.5 s):
* advantages: 411 of 1,164 documents labelled, 753 not;
* DAs: 296 of 662 labelled, 366 not;
* 31 positions and 87 impact rows, with the same top three, cluster and team count, for every one
  of the 31.

**Checks:**
* The hand-written goldens matched byte for byte on the first run.
* The tests were shown failing against skeletons first.
* 21 mutants, all caught. One first survived, a `turns case` heading that also holds an exclusion,
  and got a test.

The Goal is `Succeeded`: every criterion passed.

**Look first at Deviation 1:** four files outside `constraints.packages`, each a one-line consequence
of a fourth bundle file or of the fixture's generator (question 1).

**Something to know:** at 17:05 today, while this session waited for the ruling, a non-dry
`landscape report` run, not this session's, rewrote the classification cache and the review queue
and wrote a three-file bundle to `reports/landscape/hspolicy26/2026-10-20/`. A `report.html` beside
it appeared at 17:25. That fits the operator's first dev run (t05's follow-up). My re-count left all
of it byte for byte as it was.

## The counts on the real store

**How they were taken.** Read-only, counts only, hspolicy26 through 2026-10-20, taxonomy 1.1.0 and
the coach's 45 decisions, as `landscape report` stands on `dev`. Before each run, no `DEBATE_*`
variable was set and no `caselist pull` was running.

* **The script** was a scratchpad script, not committed. It read the store as t05's run service
  does, and classified through the run's read-only view of t02's cache.
* **It wrote nothing to the store.** The classification cache and the plan-text cache had the same
  SHA-256 after both runs as before. Nothing under `landscape/review/` changed, and no report
  directory was created.
* **Runtime:** 38.6 s and 41.6 s, at load average 4.5 and 2.3.
* **Coverage matches t05's wired run to the card:** 63,494 of 126,681 cards counted.
* **The cache missed every lookup** (107,187). It holds taxonomy 1.0.0 entries, and every landscape
  run since 1.1.0 has been a read-only dry run, so nothing has rewritten it. Classification ran
  deterministically in memory instead. The first real run rewrites the cache; this is expected, not
  a defect.

**What a document is.** A parsed file holding at least one card that the report counts for the
position: placed under it, READS, at or above the review threshold, and in a round on the position's
own side. This is t03's rule (the PM's rulings). 20,119 DA and advantage cards were placed only in
rounds on the other side, and none of them counts here. No counted card was in a round on no
readable side.

**The comparison with t03's measure.** t03's measure was `impact` or `impacts` in a heading, or
anywhere in the tag. On today's taxonomy it finds 333 of 662 DA documents (50.3%) and 235 of 1,164
advantage documents (20.2%). t03 had 284 of 562 and 229 of 1,129 under 1.0.0. The difference is
1.1.0's three new DAs and the coach's decisions.

### Impact headings, by documents (cards)

A heading is normalized as the matcher reads it (t01's normalizer, with the caselist's schools taken
out). It matches when it holds the label as whole words.

| Heading label | DA documents (cards) | Advantage documents (cards) |
|---|---|---|
| `impact` | 186 (779) | 31 (80) |
| `impacts` | 1 (2) | 0 |
| `impact overview` | 10 (17) | 0 |
| `turns case` | 21 (47) | 0 |
| `t c`, `tc` (T/C) | 17 (40), 10 (19) | 0 |
| `i l`, `il`, `internal link` | 21 (50), 12 (28), 8 (20) | 1 (2), 0, 1 (7) |
| `i l and impact`, `impact calc`, `magnitude`, `escalation`, `outweighs` | 0 | 0, apart from `outweighs` 1 (1) |
| `extinction`, `war`, `nuclear war`, `terminal`, `timeframe` | 1, 10, 1, 2, 2 | 5, 8, 0, 0, 0 |
| `overview`, `ov` (t11's, not an impact) | 42 (175), 19 (64) | 5 (5), 1 (1) |
| answers inside an impact heading: `no impact`, `impact defense`, `impact turn(s)` | 7 (12), 3 (8), 8 (22) | 0, 2 (2), 0 |

### Tags that open with an impact word, by documents (cards)

The tag's words are compared after a leading enumerator: a number, a letter `a` to `h`, or `first`
to `fifth`.

| Tag opens with | DA documents (cards) | Advantage documents (cards) |
|---|---|---|
| `extinction` | 76 (88) | 244 (335) |
| `existential` | 1 (1) | 110 (111) |
| `the impact`, `our impact`, `impact`, `impacts` | 16, 16, 14, 1 | 35, 1, 6, 0 |
| `nuclear war`, `nuke war`, `goes nuclear` | 5, 1, 2 | 14, 11, 0 |
| `turns case` | 29 (33) | 0 |
| `timeframe`, `magnitude`, `probability` | 29, 9, 0 | 2, 0, 4 (5) |
| `outweighs` | 9 (9) | 0 |
| `escalation` | 0 | 4 (4) |
| not proposed: `independently` | 19 (20) | 269 (297) |
| not proposed: `nuclear` alone, `war` alone, `otherwise extinction` | 16, 3, 1 | 19, 3, 15 |
| not proposed: `no impact` (defense) | 32 (36) | 11 (11) |

### The proposed rule, per kind

A card is an impact card when either of these holds:
* **A heading on its path** holds `impact` or `impacts`, but not `no impact`, `impact defense` or
  `impact turn(s)`; or it holds `turns case`.
* **Its tag**, after an enumerator, opens with one of the proposed words: `impact`, `impacts`, `the
  impact`, `our impact`, `extinction`, `existential`, `nuclear war`, `nuke war`, `goes nuclear`,
  `escalation`, `turns case`, `outweighs`, `magnitude`, `timeframe` or `probability`.

| Rule | DA documents with one | Advantage documents with one | DA / advantage documents with none |
|---|---|---|---|
| Narrow: headings `impact(s)`; tags opening `impact(s)`, `the impact`, `our impact` | 214 of 662 (32.3%) | 73 of 1,164 (6.3%) | 448 (67.7%) / 1,091 (93.7%) |
| **Proposed**, card by card | **296 (44.7%)**: 187 by heading, 172 by tag, 63 both | **411 (35.3%)**: 29 by heading, 397 by tag, 15 both | **366 (55.3%) / 753 (64.7%)** |
| Proposed, a cluster counted once any copy is labelled | 484 (73.1%) | 806 (69.2%) | 178 / 358 |

Under the proposed rule, 959 of 9,401 counted DA cards and 598 of 21,157 counted advantage cards are
impact cards.

### Per position, proposed rule, card by card

| DA | Documents | Heading `impact(s)` | Heading `turns case` | Tag word | Any | None | Impact clusters |
|---|---|---|---|---|---|---|---|
| Midterms DA | 418 | 104 | 12 | 90 | 177 | 241 | 164 |
| Economy DA | 89 | 18 | 1 | 22 | 36 | 53 | 40 |
| Pharma DA | 74 | 18 | 1 | 11 | 27 | 47 | 48 |
| Democracy DA | 62 | 0 | 0 | 2 | 2 | 60 | 2 |
| Stocks DA | 53 | 8 | 2 | 14 | 16 | 37 | 14 |
| Debt DA | 49 | 0 | 0 | 0 | 0 | 49 | 0 |
| Rates DA | 44 | 13 | 0 | 19 | 25 | 19 | 30 |
| Federalism DA | 44 | 0 | 0 | 1 | 1 | 43 | 1 |
| AI DA | 28 | 0 | 0 | 0 | 0 | 28 | 0 |
| IRS DA | 28 | 16 | 2 | 5 | 18 | 10 | 20 |
| HHS DA | 20 | 6 | 0 | 1 | 7 | 13 | 10 |
| Capital flight DA | 19 | 5 | 3 | 10 | 12 | 7 | 15 |
| Unions DA | 19 | 1 | 0 | 0 | 1 | 18 | 6 |
| Court clog DA | 17 | 6 | 0 | 7 | 11 | 6 | 24 |
| Medical devices DA | 13 | 7 | 0 | 3 | 9 | 4 | 6 |
| Taxes DA | 11 | 5 | 0 | 0 | 5 | 6 | 6 |
| Permitting reform DA | 10 | 4 | 0 | 0 | 4 | 6 | 16 |
| Innovation DA | 9 | 0 | 0 | 0 | 0 | 9 | 0 |
| Politics DA | 6 | 0 | 0 | 1 | 1 | 5 | 2 |
| Doctors DA | 3 | 0 | 0 | 0 | 0 | 3 | 0 |
| **Distinct documents** | **662** | **176** | **21** | **172** | **296** | **366** | |

| Advantage | Documents | Heading `impact(s)` | Heading `turns case` | Tag word | Any | None | Impact clusters |
|---|---|---|---|---|---|---|---|
| Costs | 394 | 2 | 0 | 42 | 43 | 351 | 12 |
| Disease | 241 | 0 | 0 | 21 | 21 | 220 | 10 |
| Economy | 225 | 4 | 0 | 14 | 18 | 207 | 19 |
| Inequality | 220 | 3 | 0 | 97 | 99 | 121 | 10 |
| Coverage | 217 | 3 | 0 | 43 | 44 | 173 | 32 |
| Growth | 184 | 2 | 0 | 14 | 16 | 168 | 14 |
| Access | 109 | 0 | 0 | 74 | 74 | 35 | 5 |
| Budgets | 103 | 2 | 0 | 56 | 56 | 47 | 8 |
| Stagnation | 93 | 7 | 0 | 27 | 31 | 62 | 19 |
| Bioterror | 86 | 1 | 0 | 13 | 14 | 72 | 12 |
| Innovation | 71 | 0 | 0 | 8 | 8 | 63 | 8 |
| Pandemics | 51 | 1 | 0 | 0 | 1 | 50 | 1 |
| Data | 42 | 1 | 0 | 13 | 13 | 29 | 12 |
| Sustainability | 29 | 0 | 0 | 7 | 7 | 22 | 3 |
| Pharma | 15 | 3 | 0 | 4 | 6 | 9 | 9 |
| Biotech | 12 | 0 | 0 | 0 | 0 | 12 | 0 |
| **Distinct documents** | **1,164** | **29** | **0** | **397** | **411** | **753** | |

31 of the 36 DAs and advantages have at least one impact card. Debt, AI, Innovation and Doctors DA
and the Biotech advantage have none.

### What the top three would show

I read these in my own terminal and quote none of them. Ranked by distinct teams, then cluster id:
* **Tag-opening cards:** of 50 sampled at random (seeded), every one is an impact or
  impact-comparison claim. One of them answers impact defense.
* **Cards placed by heading alone:** of 40 sampled, about half are impact claims. The rest are
  rebuttals filed inside an "Impact" block ("err neg", "doesn't assume the plan").
* **The top three per position, card by card:** about four in five rows read as impact claims. The
  misses come from the heading signal.
* **The top three, cluster-wide:** worse at the top. One team's label carries a widely read card
  into the list: two of the Economy advantage's top three become admin-cost and monopsony cards read
  by 30 or more teams. Cluster-wide changes the top three of 21 of the 31 positions.

**Headings are only read, never shown.** Some raw headings still carry a school name that the source
heading normalizer does not take out. A report never shows a heading, only the tag and the short
cite as parsed, so this changes nothing in what a report says. I kept every such word out of this
report and out of the question block.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| impact-cards | Done | Counts sent and ruled on, then, in order:<br>1. the rulings in the spec;<br>2. the goldens by hand;<br>3. the rule and its tests, red then green;<br>4. the fixture's headings;<br>5. the service and renderer, red then green;<br>6. mutation;<br>7. a read-only re-count with the build |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, per DA and advantage, of documents with a labelled impact card, sent to the PM with the proposed impact-heading list | PASS | [The counts on the real store](#the-counts-on-the-real-store) and the first question block. The PM ruled on 2026-10-24: (a), (a), (a), yes |
| ac2: after the ruling, on the synthetic fixture, report.md shows up to N impact cards under each DA and advantage, and impact_cards.csv lists them, matching hand-written golden files byte for byte; an ANSWERS card or a card on the other side is never an impact card; tests shown failing first | PASS | `test_rendering_the_fixture_matches_the_golden_file[report.md]` and `[impact_cards.csv]` pass against goldens committed in `04675a1`, before any code. `test_impact_an_answer_is_never_an_impact_card` (`b7`'s answer, in a round on no readable side, is listed once made READS) and `test_impact_a_card_in_a_round_on_the_other_side_is_never_an_impact_card` (`a6`'s, listed once its round has no side). Red runs [below](#checks-shown-failing-for-their-reason) |
| ac3: the report states, per kind, how many documents carry no labelled impact | PASS | report.md: "Advantage documents with no labelled impact: 4 of 6 (66.7%)." and "DA documents with no labelled impact: 3 of 6 (50.0%)."; impact_cards.csv: `# no_labelled_impact_advantage=4/6`, `# no_labelled_impact_da=3/6` (`test_each_kind_says_how_many_of_its_documents_carry_no_labelled_impact`). On the real store, 753 of 1,164 and 366 of 662 |
| impact-cards: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | PASS | Run as `.venv/bin/python -m pytest …` under a 110 s alarm → `52 passed in 2.52s` |

### Checks shown failing for their reason

* **The rule, `test_impacts.py`:**
  * against a skeleton that labels every card: **41 failed, 36 passed**;
  * against one that labels none: **37 failed, 40 passed**;
  * every case fails under one of the two, except the constants test, which pins the list itself;
  * the real rule: 77 passed, 80 after the added case.
* **The service: a refuse-nothing skeleton** (every counted card of every kind an impact card)
  against `test_landscape_report.py` and `test_render.py`: **13 failed, 57 passed**.
  * Among the failures: both new goldens, the coverage line, the exclusions, the labelled-copies
    rule, the kinds, the side and role cases, and the cap.
  * Two impact tests passed under it. The range and threshold test holds a rule the skeleton keeps,
    from t03's counting. The ranking test checked ranks without clusters, so I tightened it to the
    clusters it ranks.
* **21 mutants, all caught.** Each ran in a fresh process, with bytecode writing off and
  `__pycache__` cleared. Each file was restored and checked by SHA-256 after every mutant. No
  Hypothesis is used, so agreement 8's database rule does not arise. The test files were
  `test_landscape_report.py`, `test_render.py` and `test_impacts.py`, 147 tests (150 after the added
  case).
  * "Impact tests" counts this task's tests plus the two goldens that hold the impact section
    (report.md, impact_cards.csv).
  * Mutants of code shared with t03 (the side rule, ANSWERS, ranking) are caught by the impact
    tests on their own.

  | Mutant | Failed | Of them, impact tests |
  |---|---|---|
  | Side: a placement in a round on the other side counts | 14 | 7 |
  | Side: ANSWERS count as reads | 15 | 8 |
  | Card by card: a cluster counts once any copy is labelled | 11 | 11 |
  | Kinds: every kind's impact cards are listed | 4 | 4 |
  | Coverage: every counted document is labelled | 4 | 4 |
  | Exclusion: `no impact` labels an impact | 12 | 12 |
  | Exclusion: `impact defense` labels an impact | 8 | 8 |
  | Exclusion: `impact turns` labels an impact | 9 | 9 |
  | Exclusion: `impact turn` labels an impact | 1 | 1 (the rule's unit test; no fixture heading says `impact turn`) |
  | Exclusion: no exclusion is applied | 17 | 17 |
  | Exclusion: an excluded heading excludes even `turns case` | 3 | 3, **after a new test**. It first survived (0 failed): no test had a heading holding both. Under the ruling a `turns case` heading is an impact label whatever else it holds ("impact turns case"), and the counts were taken that way. `test_turns_case_labels_an_impact_whatever_else_the_heading_holds` was added |
  | Heading: `turns case` labels nothing | 14 | 14 |
  | Heading: words matched as substrings | 2 | 2 |
  | Enumerator: none is skipped | 18 | 18 |
  | Enumerator: every leading enumerator is skipped | 1 | 1 |
  | Enumerator: numbers only | 5 | 5 |
  | Tag: an impact word anywhere in the tag | 15 | 15 |
  | Ranking: by cluster id alone | 6 | 6 |
  | Ranking: ties broken by cluster id, descending | 10 | 8 |
  | Ranking: teams count cards, not distinct teams | 10 | 6 |
  | Ranking: no cap | 2 | 1 |

### The re-count with the build

Read-only on hspolicy26 at 2026-10-20: `LandscapeRunService.run(dry_run=True)` through the CLI's
composition root, from a scratchpad script that printed counts only. Before it ran, no `DEBATE_*`
variable was set and no `caselist pull` was running.

**It wrote nothing:**
* the classification cache, the plan-text cache, the review queue, and the operator's bundle with
  its `report.html` had the same SHA-256 after the run as before;
* the run reported `written False`.

**44.5 s** at load average 8.7. Taxonomy 1.1.0; 63,494 of 126,681 cards counted, as before.

| Count | Ruled on (the scratch rule) | The build |
|---|---|---|
| Advantage documents: labelled / not | 411 / 753 of 1,164 | 411 / 753 of 1,164 |
| DA documents: labelled / not | 296 / 366 of 662 | 296 / 366 of 662 |
| Positions with an impact card | 31 | 31 |
| Impact rows (up to 3 each) | 87 | 87 |
| Positions whose top three differ (cluster or teams) | | 0 |
| The scan before sharing | | no hit in `impact_cards.csv` or report.md; top_cards.csv's same 6 hits as t05's run (3 school, 2 team code, 1 tournament) |

The bundle the dry run planned is `positions.csv`, `top_cards.csv`, `impact_cards.csv`, `report.md`.

## Before the report (working agreement 10)

* **The affected set is over two minutes.** `uv run scripts/affected_tests.py` chose 166 of 444
  files (37.4%) from 22 changed files. I ran them as
  `.venv/bin/python -m pytest -q -n auto -m "not slow and not live" -p no:randomly <files>` under a
  115 s alarm, at load average 6.9.
  * The alarm stopped it at 92%. Its progress lines up to then hold 4,248 passes and no failure or
    error.
  * The warnings after them are the xdist workers' teardown failing once their parent was gone.
  * Two processes the run had started (a stand-in server and a test's `install.sh`) outlived it
    briefly and exited by themselves.
  * So it is left to the pull request's `ci`, which runs the whole selection.
* **Within the two minutes, the tests of what changed and the always-run list:**
  * the landscape, aff-assignment, plan-text and classification tests in
    `packages/debate_core/tests/application`, plus `packages/debate_core/tests/arguments/landscape`,
    `packages/debate_core/tests/domain` and `packages/debate_core/tests/integrations/landscape`;
  * `packages/debate_cli/tests/test_landscape_command.py`, `tests/smoke/test_landscape_smoke.py`,
    `tests/config`, `tests/architecture` and `tests/specs`;
  * result: **1,999 passed in 8.76s**.
* `packages/debate_cli/tests` → **898 passed in 28.69s**. Its one failure on the way indexed the
  bundle's keys by position (`KEYS[2]`); it now indexes by name.
* `tests/smoke/test_landscape_smoke.py -m "not live and not in_process"` → 2 passed.
* `uv run --frozen ruff format --check .` → 1225 files already formatted.
  `uv run --frozen ruff check .` → all checks passed.
* `uv run --frozen pyright`, bare as CI runs it → 0 errors, 0 warnings.
* `uv run --frozen lint-imports` → 16 kept, 0 broken.
* `scripts/check_thin_handlers.py` → 48 handlers within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 434 files. `--require-succeeded
  v1-e32-t10-impact-cards-per-position` → Succeeded. The spec's ruling comment parses as a comment:
  the description does not contain it.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`arguments/landscape/impacts.py`** (new): the rule. It holds `is_impact_heading`,
  `tag_opens_with_impact`, `is_impact_card` and the ruled lists. Its tests are
  `tests/arguments/landscape/test_impacts.py` (new, 80).
* **`domain/landscape_report.py`:**
  * `LandscapeCard.headings`;
  * `ImpactCard` (a `TopCard` of the labelled copies) and `ImpactCoverage`;
  * `DEFAULT_IMPACT_CARDS` = 3 and `IMPACT_KINDS`;
  * `ReportHeader.impact_cards_per_position`;
  * `LandscapeReport.impact_cards` and `.impact_coverage`.
* **`application/landscape_report.py`:**
  * `landscape_cards` computes each card's headings, as the matcher reads them;
  * the service ranks impact clusters and counts coverage per kind;
  * top cards and impact cards share one ranking function, `_ranked`;
  * the bundle gains `impact_cards.csv`.
* **`application/landscape_run.py`:** `BUNDLE_FILES` gains `impact_cards.csv`, uploaded before
  report.md. The reading's school names are passed to `landscape_cards`.
* **`arguments/landscape/render.py`:**
  * the impact block under the advantages and DAs tables;
  * a line in "How to read the numbers";
  * `render_impact_cards_csv` and `IMPACT_CARD_COLUMNS`.
* **Tests:**
  * `test_landscape_report.py`: 10 impact tests and a `landscape_cards` headings test. The hand
    counts the new fixture card changes were edited by hand.
  * `test_render.py`: the fourth golden. A new escaping test and a coverage-line test. t03's
    "report.md lists no card" became "report.md lists impact cards only".
  * `test_landscape_run.py`: the four files.
* **`tests/fixtures/landscape/`:**
  * the goldens: `impact_cards.csv` (new), the report.md section, and the coverage line of all
    four (`04675a1`, by hand);
  * `synthetic_caselist/`: the cards' headings, two retagged copies, a new card, and the README's
    impact section.
* **Outside `constraints.packages`** (Deviation 1): `scripts/make_landscape_fixture.py`,
  `packages/debate_cli/tests/test_landscape_command.py`,
  `packages/debate_cli/src/debate_cli/commands/landscape.py` (docstring only), and
  `tests/smoke/test_landscape_smoke.py`.
* **The spec:** the PM's rulings as a comment above the folded description, and the phase.

## Deviations from the spec

1. **Four files outside `constraints.packages`:**
   * **`scripts/make_landscape_fixture.py`.** It is the only writer of the synthetic caselist.
     Hand-editing `cards.jsonl` would leave the generator to erase the headings on its next run.
   * **The CLI's tests and the smoke check.** They pin the bundle's file list, and the spec puts
     `impact_cards.csv` in the bundle. Each change adds the name, and one test now indexes the
     bundle by name.
   * **The CLI command's docstring**, which names the bundle's files.

   No CLI behaviour changed. Question 1.
2. **t03's fixture, goldens and one of its tests changed.**
   * The fixture gained one card: `b7`'s answer to the Midterms DA, in a round on no readable side.
     It is the only case where the ANSWERS role alone keeps a labelled card out.
   * As a result, coverage in all four files' headers went from 33/44 to 34/45, and the Unclassified
     card count from 10 of 44 to 10 of 45. Both were edited by hand, never regenerated.
   * Two copies whose tags no top-card row shows were retagged (cluster 2 copy `d`, cluster 6 copy
     `c`), so `top_cards.csv`'s rows are unchanged.
   * t03's test that report.md lists no card now says it lists only impact cards. That is the
     coach's ask the PM filed this task for.

## Decisions and assumptions

1. **A card's headings** are the ones the position matcher reads: its path without an open tag
   (`heading_path`), each normalized with the disclosing teams' and the caselist's school names taken
   out (`normalize_source_heading`). They are computed in `landscape_cards` and carried on
   `LandscapeCard.headings`, never shown. The counts were taken the same way.
2. **The ranking is top cards' own function**, applied to the labelled copies only. A row shows the
   commonest tag and cite among those copies, from the first such card by digest and paragraph, so
   an impact row can show a different copy than the cluster's top-card row (cluster 2 in the
   fixture).
3. **Coverage per kind:** a document is a file holding a card counted for a position of the kind. A
   file counted for two DAs is one DA document. Both kinds are always computed, `0/0` when a caselist
   has none, so the CSV header always carries both lines. report.md writes a kind's block only under
   that kind's table.
4. **report.md's block:**
   * `#### Advantages: impact cards` under the advantages table, and the same for Disadvantages;
   * first the kind's no-labelled-impact line;
   * then each position in report order, with a Rank, Teams, Tag and Cite table, or "no labelled
     impact card";
   * tags and cites are escaped as labels are; the CSV keeps them exact.
5. **impact_cards.csv** has top_cards.csv's columns. Its header block adds
   `impact_cards_per_position` and `no_labelled_impact_<kind>=<none>/<documents>`. It is uploaded
   before report.md, so the page a person opens still goes last.
6. **The enumerator** is one leading `1`–`99`, `a`–`h` or `first`–`fifth`, as counted and ruled. So
   the article in "A nuclear war …" is skipped too, and the tag labels an impact. A test states this.
7. **N defaults to 3** (`DEFAULT_IMPACT_CARDS`), the PM's brief. `LandscapeReportService(impact_cards=…)`
   sets it. The CLI has no flag, as it has none for top cards.

## Operator follow-ups

1. **The pull request**, from the worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t10-impact-cards-per-position
```

```bash
scripts/task pr v1-e32-t10-impact-cards-per-position
```

2. **After the merge,** the next `landscape report` run writes `impact_cards.csv` beside the other
   three files, and a `--publish` adds it to `reports/landscape/<caselist>/<snapshot>/`. The scan
   before sharing covers it. On today's store it found no hit in it.

## Follow-up work

* **The source heading normalizer leaves some schools in headings** (v1-e32-t02's `CaselistNames`,
  or a new E32 task). It strips a school only by its full name. The counts found headings carrying a
  school's first word, and this task's headings test hit the same edge. No report shows a heading,
  but the review queue and the candidates sheet show them to the coach. I have not measured how
  often this happens.
* **Unlabelled impacts** (753 advantage documents, 366 DA documents on hspolicy26) are v1-e32-t07's
  model stage, as ruled.

## Questions for the PM

The first block was answered on 2026-10-24: (1) a, (2) a, (3) a, (4) yes. Kept as asked:

```text
v1-e32-t10 questions (session, 2026-10-24): counts first, nothing built

Read-only, hspolicy26 through 2026-10-20, taxonomy 1.1.0 with the coach's 45
decisions; counts only. A document is a file with a card the report counts
for the position (READS, at or above the threshold, round on its own side;
20,119 other-side DA/advantage cards excluded). 662 DA documents, 1,164
advantage documents. t03's measure ("impact" in a heading or anywhere in the
tag) now finds 333 of 662 DA and 235 of 1,164 advantage documents.

Impact headings (documents, DA / advantage):
  impact 186 / 31, impacts 1 / 0, impact overview 10 / 0,
  turns case 21 / 0, T/C ("t c", "tc") 17 and 10 / 0,
  i/l ("i l", "il", "internal link") 21, 12, 8 / 1, 0, 1,
  "i l and impact", impact calc, magnitude, escalation 0 / 0,
  overview 42 / 5 (t11's, not an impact),
  inside an impact heading: "no impact" 7, "impact defense" 3,
  "impact turn(s)" 8 / 0, 2, 0.

Tags opening with an impact word (documents, DA / advantage; after a
leading enumerator such as "1", "b", "third"):
  extinction 76 / 244, existential 1 / 110, the impact 16 / 35,
  our impact 16 / 1, impact(s) 15 / 6, nuclear war 5 / 14, nuke war 1 / 11,
  goes nuclear 2 / 0, turns case 29 / 0, timeframe 29 / 2, magnitude 9 / 0,
  outweighs 9 / 0, probability 0 / 4, escalation 0 / 4.
  Not proposed: independently 19 / 269 (mostly add-ons and links),
  "no impact" 32 / 11 (defense), nuclear alone 16 / 19.

Under the proposed rule, card by card:
  DA: 296 of 662 documents (44.7%) hold an impact card, 187 by heading and
    172 by tag; 366 (55.3%) hold none.
  Advantage: 411 of 1,164 (35.3%), 29 by heading and 397 by tag; 753 (64.7%)
    hold none.
  Narrow rule (headings impact(s); tags opening impact(s), the/our impact):
    DA 214 (32.3%), advantage 73 (6.3%).
  Per position: Midterms 177 of 418, Economy DA 36 of 89, Pharma DA 27 of 74.
    The Debt, AI, Innovation and Doctors DAs and the Biotech advantage have
    none. The Inequality advantage has 99 of 220, Costs 43 of 394. The full
    table is in the session report.

1. Heading list. A card is an impact card when a heading on its path holds
   "impact" or "impacts" (whole words), but not "no impact", "impact
   defense" or "impact turn(s)"; or holds "turns case".
   (a) As proposed.
   (b) Also T/C ("t c", "tc") and i/l.
   (c) Only "impact" and "impacts", no exclusions.
   Recommendation: (a). T/C is ambiguous as an abbreviation; i/l alone is a
   link, not an impact; the exclusions are defense or answers filed under an
   impact heading. "i l and impact" never occurs.

2. Tag words. A card is an impact card when its tag, after one leading
   enumerator, opens with: impact, impacts, the impact, our impact,
   extinction, existential, nuclear war, nuke war, goes nuclear, escalation,
   turns case, outweighs, magnitude, timeframe, probability.
   (a) As proposed.
   (b) Only impact, impacts, the impact and our impact.
   Recommendation: (a). It is what makes advantages countable at all (6.3%
   becomes 35.3%): a 1AC opens the tag with the impact itself. Of 50 such
   cards sampled at random, all 50 are impact or impact-comparison claims.

3. Card or cluster. Is a cluster an impact card when one of its copies is
   labelled, so that every team reading any copy under the position counts?
   (a) Card by card: only the labelled copies count, and their teams rank
       the cluster.
   (b) Cluster-wide: DA 484 documents (73.1%), advantage 806 (69.2%); the top
       three changes for 21 of 31 positions.
   Recommendation: (a), as the spec words it. Cluster-wide lets one team's
   label carry widely read link and solvency cards into the top three (two
   of the Economy advantage's top three, read by 30 or more teams each).
   Card by card, about four in five top-three rows read as impact claims;
   the misses are rebuttals inside an "Impact" block, from the heading
   signal.

4. The "no labelled impact" line (ac3) uses the same rule and denominator:
   DA 366 of 662, advantage 753 of 1,164 today, per kind, in report.md's
   impact section and in impact_cards.csv's header block. Agree?
   Recommendation: yes. With the rule ruled, the line says exactly what the
   section could not see, and t07's model stage is what closes it.
```

Second block, after the build (2026-10-24):

```text
v1-e32-t10 questions after the build (session, 2026-10-24)

Built as ruled: the rule as pure functions, hand-written goldens matched byte
for byte, 21 mutants caught (one first survived, a test added), and a
read-only dry run on hspolicy26 reproduces the ruled counts exactly: advantage
411 of 1,164 labelled, DA 296 of 662, 31 positions, 87 rows, the same top
three for all 31. Goal Succeeded.

1. Amend constraints.packages with scripts/make_landscape_fixture.py (the
   fixture's only writer), packages/debate_cli (the landscape command's tests
   and its docstring) and tests/smoke (the bundle's file list)?
   Each change is the fourth bundle file's name, or the cards' headings in
   the generator; no CLI behaviour changed (Deviation 1).
   Recommendation: yes, as for t03's scripts and tests.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED, with one condition closed in-session
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-24

**Notes:**

1. **Built as ruled.**
   * Hand-written goldens were committed before any code and match byte for byte.
   * 21 mutants were caught. One first survived and got its test.
   * The read-only dry run on hspolicy26 reproduces the ruled counts exactly: advantage 411 of
     1,164 labelled, DA 296 of 662, 31 positions, and the same top three for all 31.
   * The side and ANSWERS rules are each pinned by a fixture card.
2. **Deviation 2 is accepted.** It adds t03's fixture card, and the goldens and coverage counts were
   edited by hand, never regenerated. The two retagged copies keep `top_cards.csv`'s rows unchanged.
3. **Question 1: yes.** Amend `constraints.packages` with `scripts` (`make_landscape_fixture.py`),
   `packages/debate_cli` (tests and the command's docstring only) and `tests/smoke`, with a
   PM-ruling comment. This is the one condition. No re-review is needed.

**The PR:** opened without `--partial`. The next weekly landscape run carries `impact_cards.csv`
and the report's impact section, with the same scan before sharing.
