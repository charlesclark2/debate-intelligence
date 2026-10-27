# Session report: v1-e32-t25-readable-impact-chains

| | |
|---|---|
| Task | `v1-e32-t25-readable-impact-chains` — What each impact runs through, named in words a debater uses |
| Spec | [`plan_specs/v1/e32-argument-landscape/t25-readable-impact-chains.yaml`](../../plan_specs/v1/e32-argument-landscape/t25-readable-impact-chains.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t25-readable-impact-chains` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Complete. Every criterion passed, and the Goal is `Succeeded`.** The operator's dry run (ac3,
2026-10-26, 70.7 s) printed exactly the counts the session predicted
([below](#the-operators-dry-run-ac3)).

**What is built.** Under each DA's and advantage's impact cards, "What each impact runs through" names
every rank by the first of these it has, and marks where the name came from:
1. the scenario (t22's list where there is one): `(scenario)`;
2. a labelled internal link: `(internal link)`;
3. the impact card's own tag: `(tag)`;
4. the card above it in its block: `(card above)`.

A tag, internal link or card above holding a word of a caselist school, team code or tournament is
withheld by the report's existing `is_withheld`. It is counted, and the next source names the rank. A
rank nothing names is left out: the position says how many, and so does each kind. No model call, no
taxonomy change. The dry-run script prints one counts-only line per kind.

**ac1, the counts first** ([below](#the-counts-before-building-ac1)). On hspolicy26 through 2026-10-20
(read-only, 51 s), the Economy DA has no labelled internal link on any of its 3 ranks: 2 have only a
card above, 1 has neither. **All 3 of its impact cards have their own tag**, none withheld, so the
spec's premise holds. The build names them `(tag)`, all three.

**What the PM should look at first:**
* **The tag names most ranks.** Every one of the 87 impact cards has its own tag, so the tag names 68
  ranks. The card above, which t14 showed on 41 rows, now names 2. [Question 1](#questions-for-the-pm).
* **Package Deviation.** The domain model (`debate_core.domain`) changed, as in t22
  ([Deviations](#deviations-from-the-spec)).

**How it was checked:**
* The goldens were written by hand and committed before any code (`b2efa7a`). They matched on the first
  green run.
* The tests ran red against a skeleton that names nothing: 30 failed (`6d7fa34`).
* All 21 mutants were caught, the PM's three among them.
* After the build, a read-only recount on hspolicy26 matches every count ac1 predicted.

## The counts before building (ac1)

**What ran.** A read-only script in the session's scratchpad, `counts/count_rank_sources.py`, built as
t14's recount was:
* wired by hand over `~/.debate-research/dev`, with no container, no worker pool, no aff assignments
  and no analytic texts;
* the classification cache read through the run's read-only view;
* taxonomy 1.4.0 at `742aef5`, which is dev with t22;
* a 115 s alarm on the interpreter. It finished in 51.1 s, and no process outlived it.

It printed position ids and counts only. "Withheld" is the report's own `is_withheld` against the
caselist's withholding words.

**Per kind** (the code on dev, t14 under t22's lists):

| Count | Advantage | DA |
|---|---|---|
| Ranks (impact rows) | 43 | 44 |
| With a labelled internal link | 0 | 7 |
| With only a card above | 30 | 11 |
| With neither | 13 | 26 |
| With a scenario (t22's names) | 0 | 9 |
| With its own tag | 43 | 44 |
| Own tag holding a caselist word | 4 | 2 |
| Internal link holding a caselist word | 0 | 0 |
| Card above holding a caselist word | 6 | 1 |

**Each source's share, predicted under the spec's order**, withholding applied:

| Named by | Advantage | DA |
|---|---|---|
| Scenario | 0 | 9 |
| Internal link | 0 | 4 |
| Own tag | 39 | 29 |
| Card above | 2 | 0 |
| Left out | 2 | 2 |

**Per position:**

| Position | Ranks | IL | Card above only | Neither | Scenario | Own tag | Own tag withheld | Card above withheld | Predicted: scenario / IL / tag / card above / left out |
|---|---|---|---|---|---|---|---|---|---|
| `access-advantage` | 3 | 0 | 2 | 1 | 0 | 3 | 0 | 1 | 0 / 0 / 3 / 0 / 0 |
| `bioterror-advantage` | 3 | 0 | 1 | 2 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `budgets-advantage` | 3 | 0 | 3 | 0 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `costs-advantage` | 3 | 0 | 3 | 0 | 0 | 3 | 0 | 2 | 0 / 0 / 3 / 0 / 0 |
| `coverage-advantage` | 3 | 0 | 3 | 0 | 0 | 3 | 1 | 1 | 0 / 0 / 2 / 1 / 0 |
| `data-advantage` | 3 | 0 | 2 | 1 | 0 | 3 | 0 | 1 | 0 / 0 / 3 / 0 / 0 |
| `disease-advantage` | 3 | 0 | 3 | 0 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `economy-advantage` | 3 | 0 | 2 | 1 | 0 | 3 | 1 | 0 | 0 / 0 / 2 / 0 / 1 |
| `growth-advantage` | 3 | 0 | 1 | 2 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `inequality-advantage` | 3 | 0 | 3 | 0 | 0 | 3 | 0 | 1 | 0 / 0 / 3 / 0 / 0 |
| `innovation-advantage` | 3 | 0 | 1 | 2 | 0 | 3 | 1 | 0 | 0 / 0 / 2 / 1 / 0 |
| `pandemics-advantage` | 1 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 / 0 / 1 / 0 / 0 |
| `pharma-advantage` | 3 | 0 | 1 | 2 | 0 | 3 | 1 | 0 | 0 / 0 / 2 / 0 / 1 |
| `stagnation-advantage` | 3 | 0 | 2 | 1 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `sustainability-advantage` | 3 | 0 | 3 | 0 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `capital-flight-da` | 3 | 2 | 1 | 0 | 0 | 3 | 0 | 0 | 0 / 2 / 1 / 0 / 0 |
| `court-clog-da` | 3 | 0 | 0 | 3 | 2 | 3 | 0 | 0 | 2 / 0 / 1 / 0 / 0 |
| `democracy-da` | 2 | 0 | 2 | 0 | 0 | 2 | 0 | 0 | 0 / 0 / 2 / 0 / 0 |
| **`economy-da`** | **3** | **0** | **2** | **1** | **0** | **3** | **0** | **1** | **0 / 0 / 3 / 0 / 0** |
| `federalism-da` | 1 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 0 / 0 / 1 / 0 / 0 |
| `hhs-da` | 3 | 0 | 0 | 3 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `irs-da` | 3 | 2 | 0 | 1 | 2 | 3 | 0 | 0 | 2 / 1 / 0 / 0 / 0 |
| `medical-devices-da` | 3 | 1 | 0 | 2 | 0 | 3 | 0 | 0 | 0 / 1 / 2 / 0 / 0 |
| `midterms-da` | 3 | 2 | 1 | 0 | 3 | 3 | 0 | 0 | 3 / 0 / 0 / 0 / 0 |
| `permitting-reform-da` | 3 | 0 | 0 | 3 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `pharma-da` | 3 | 0 | 1 | 2 | 2 | 3 | 0 | 0 | 2 / 0 / 1 / 0 / 0 |
| `politics-da` | 2 | 0 | 2 | 0 | 0 | 2 | 0 | 0 | 0 / 0 / 2 / 0 / 0 |
| `rates-da` | 3 | 0 | 0 | 3 | 0 | 3 | 1 | 0 | 0 / 0 / 2 / 0 / 1 |
| `stocks-da` | 3 | 0 | 1 | 2 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |
| `taxes-da` | 3 | 0 | 0 | 3 | 0 | 3 | 1 | 0 | 0 / 0 / 2 / 0 / 1 |
| `unions-da` | 3 | 0 | 0 | 3 | 0 | 3 | 0 | 0 | 0 / 0 / 3 / 0 / 0 |

**Did the counts undercut the premise?** No. The PM's stop condition was the Economy DA's impact cards
having no tags. They all have one, so building went on.

The counts agree with t22's operator dry run of 2026-10-26: 43 / 44 rows, 0 / 9 with a scenario. ac1's
"with a labelled internal link" and "card above" agree with the report's own `ChainCoverage` in the same
run: advantage 0 and 30, DA 7 and 11.

### After the build (the same store, read-only)

At `c73b8df`, with the same wiring (`counts/count_named_after.py`, 45.9 s), the report's own counts:

| | Advantage | DA |
|---|---|---|
| Named by a scenario / internal link / tag / card above | 0 / 0 / 39 / 2 | 9 / 4 / 29 / 0 |
| Left out | 2 | 2 |
| Tags withheld (reached and passed over) | 4 | 2 |
| Rows with a labelled internal link / card above kept on the row | 0 / 24 | 7 / 10 |

* Every predicted share holds.
* **The Economy DA:** ranks 1, 2 and 3 are each named `(tag)`.
* The 4 ranks left out are `economy-advantage` rank 3, `pharma-advantage` rank 1, `rates-da` rank 2 and
  `taxes-da` rank 1. In each, the own tag is withheld and there is no card above.
* "Card above kept on the row" fell from 30 to 24 and from 11 to 10. Those 7 card-above texts hold a
  caselist word and are no longer kept on the row. Only 2 of them would have named a rank.

## The operator's dry run (ac3)

**What ran:** [Operator follow-up 1](#operator-follow-ups) at `f572269`, on 2026-10-26. The guards
passed, nothing was written, and it took 70.7 s.

| Dry run line | Expected in this report | Measured |
|---|---|---|
| Taxonomy and writes | 1.4.0, nothing written | `taxonomy 1.4.0: nothing written; 7 files planned` |
| Scenarios, advantage / DA | 43 / 44 rows, 0 / 9 with a scenario, 1 / 0 names withheld (t22's run) | 43 / 44, 0 / 9, 1 / 0; documents 676 of 1164 and 253 of 662, as in t22's |
| Impact ranks named, advantage | 0 / 0 / 39 / 2; 2 left out; 4 tags withheld | **0 by a scenario, 0 by an internal link, 39 by a tag, 2 by the card above; 2 left out; 4 tags withheld** |
| Impact ranks named, DA | 9 / 4 / 29 / 0; 2 left out; 2 tags withheld | **9 by a scenario, 4 by an internal link, 29 by a tag, 0 by the card above; 2 left out; 2 tags withheld** |
| Scan | t22's 9 hits, all accepted; none in the impact-card sections | **9 hits, 0 not yet accepted**: 1 in a plank table, 8 in `top_cards.csv`; none in the impact-card sections |

**Before and after**, per kind:
* **Before** (ac1, t14's lines): a labelled internal link on 0 advantage and 7 DA ranks, only a card
  above on 30 and 11, and neither on 13 and 26. Every rank without an internal link read "no labelled
  internal link".
* **After:** every rank is named except 2 advantage and 2 DA ranks, which are left out and counted.
* **The Economy DA's 3 ranks** are each named `(tag)` in the session's recount at `c73b8df`
  ([after the build](#after-the-build-the-same-store-read-only)). The dry run builds the same report
  and counts per kind, as ruled ([question 3](#questions-for-the-pm)).

The report is local: the republish follows the cloud cutover.

## Questions for the PM

The same questions as a paste-ready relay prompt:

```text
v1-e32-t25 (readable impact chains): built as specified; ac1, ac2 and ac3 pass (the operator's dry run matched every predicted count).
Three questions, each with my recommendation.

1. The tag names most ranks. On hspolicy26 every one of the 87 impact cards has its own tag, so under the
   spec's order (scenario, internal link, tag, card above) the tag names 68 ranks, repeating the table's Tag
   column; the card above, shown on 41 rows by t14, now names 2. Options:
   (a) keep the order as specified and built;
   (b) put the card above ahead of the tag, so a rank with a card above shows it instead of its own tag
       (ac1: 41 ranks have only a card above, 7 of those texts withheld; the exact number named was not counted);
   (c) keep the order but skip the tag line when it repeats the table, leaving those ranks out.
   Recommendation: (a). Your t14 ruling calls the card above "where it sits, not what it does"; the mark
   "(tag)" tells the coach what they are reading; and (c) would leave out 68 of 87 ranks.

2. Withheld tags elsewhere in report.md. Only "What each impact runs through" withholds a tag. The impact
   table's Tag column and the link-chain table (t10 and t14) still quote every tag as parsed, so the 6 own tags
   that hold a caselist word are still printed there. t22's scan found no hit in those sections, so they are
   probably ordinary words that are also school words.
   Recommendation: a follow-up task that counts those words first, then decides; not this task.

3. ac3 says the dry run "shows the Economy DA's ranks named". As you ruled, the dry run prints one
   counts-only line per kind. The Economy DA's ranks (1, 2 and 3, each by its tag) come from the session's
   read-only recount at c73b8df.
   Recommendation: accept the recount for the per-position view, and keep the dry run per kind. A per-position
   line would be about 31 more lines.

Also recorded as Deviations: debate_core.domain changed (LeadInSource, LEAD_IN_ORDER, ImpactCard.named_by, NamedRows,
ChainCoverage's named_rows, rows_left_out and withheld_tags), as in t22; scripts and tests/scripts as you
pre-approved.
```

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| readable-impact-chains | Done | In order:<br>1. ac1's counts, read-only;<br>2. hand-written goldens, committed before any code (`b2efa7a`);<br>3. tests, red against a skeleton (`6d7fa34`);<br>4. the rule, the domain checks, the service, report.md and the dry-run line (`c73b8df`);<br>5. 21 mutants;<br>6. the guide (`a479c74`);<br>7. the recount after the build;<br>8. the operator's dry run (ac3), matching every prediction |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before building, per DA and advantage: ranks with a labelled internal link, with only a card above, and with neither | PASS | [The counts](#the-counts-before-building-ac1): read-only, 51.1 s, ids and counts only. Advantage 0 / 30 / 13 and DA 7 / 11 / 26 of 43 and 44 ranks. Per position, the Economy DA is 0 / 2 / 1, and all 3 of its impact cards have a tag. |
| ac2: on synthetic fixtures, each rank takes the first name in the order, an empty rank is left out and counted, no quoted tag beside a school or team code, matching hand-written goldens; tests shown failing first | PASS | **Goldens** (`b2efa7a`, before any code): `golden/report.md`, `scenario_vocabulary/impact_sections.md`, and `readable_impact_chains/`, a variant reaching every source, a withheld tag and a left-out rank. They pass: `test_the_impact_sections_match_the_hand_written_golden` (both suites), `test_impact_cards_csv_matches_the_hand_written_golden`, `test_rendering_the_fixture_matches_the_golden_file[report.md]`. **Order:** `test_each_row_takes_the_first_source_it_has`, `test_the_order_is_scenario_internal_link_tag_card_above`. **Left out:** `test_an_empty_row_is_left_out_and_counted_never_shown`. **Policy 1.13:** `test_no_line_under_what_each_impact_runs_through_holds_a_caselist_word` (4 cases), `test_a_withheld_*`. The circuit-wide report carries no school or team code at all; these lines also withhold a tag holding any caselist word. **Red:** [below](#checks-shown-failing-for-their-reason). |
| ac3: the operator's dry run on hspolicy26 shows the Economy DA's ranks named, with the counts before and after | PASS | [The operator's dry run](#the-operators-dry-run-ac3), 2026-10-26, 70.7 s: `Impact ranks named, advantage: 0 by a scenario, 0 by an internal link, 39 by a tag, 2 by the card above; 2 left out; 4 tags withheld.` and `Impact ranks named, da: 9 by a scenario, 4 by an internal link, 29 by a tag, 0 by the card above; 2 left out; 2 tags withheld.` These are exactly the predicted counts. Before: ac1's counts. The Economy DA's 3 ranks are named `(tag)` in the session's recount at `c73b8df`. No scan hit in the impact-card sections. |
| readable-impact-chains: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | **977 passed in 27.66s** (load average 4.0) |

### Checks shown failing for their reason

**The goldens before the code** (`b2efa7a`). Each was worked out by hand from the fixture, and
`readable_impact_chains/README.md` shows the working:
* **Base golden.** Every rank of the unchanged caselist is named by its scenario or its tag: Costs
  `economic collapse (scenario)`, then two `(tag)`; Spending two `(tag)`, then `recession (scenario)`;
  Hospital closures `(tag)`. The per-kind lines, and the How-to-read bullet.
* **The variant.** Two edits:
  * `a1`'s rank-1 impact tag gets `Cedarvale`;
  * `a3`'s rank-3 impact tag is removed.

  Two scenario lists:
  * the Costs advantage drops `economic collapse`;
  * the Spending DA lists `cedarvale crash` as `Market crash` and drops `recession`.

  Under them, Costs rank 1 is named `(card above)` with 1 tag withheld, rank 2 `(tag)`, and rank 3 is left
  out and counted. Spending rank 1 is `Market crash (scenario)`, and rank 3 is named by its internal
  link ahead of its own tag.
* **t22's vocabulary golden.** Costs rank 1 is now `(tag)`, and ranks 2 and 3 `Rising costs (scenario)`.

**Red against a skeleton** (`6d7fa34`). The skeleton has every new name, and none does anything:
* `LeadInSource`, `LEAD_IN_ORDER`, `ImpactCard.named_by` and `NamedRows`, with no checks;
* `ChainCoverage`'s three fields, all zero;
* `rank_name`, which names nothing;
* t14's report lines, and no dry-run line.

The run covered the new suite, `test_render.py`, `test_scenario_vocabulary.py`, `test_link_chains.py`,
`application/test_landscape_report.py` and the dry-run script's test. **30 failed, 324 passed.** Every
failure was an assertion or a missing refusal, none an import or setup error:

| Failing, grouped by reason | Count |
|---|---|
| Goldens: the variant's sections and CSV, t22's sections, the base report.md, and the rest of report.md (the bullet) | 6 |
| A row named by nothing (`named_by` None) where a source was expected: order, fall-through, blank tag, team code | 10 |
| t14's lines still quote a withheld internal link and card above (`Birchmoor`, `Driftwood`) | 2 |
| `rank_name` names nothing | 2 |
| Domain checks not there: a row named by a source it lacks (4), coverage order, sum and scenario (3) | 7 |
| Render marks: `(card above)`, `(tag)` | 2 |
| The dry run has no `Impact ranks named` line | 2 |
| `test_an_empty_row_is_left_out_and_counted_never_shown` | 1 |

**Already passing on the skeleton, and why.** They are must-not cases, and the mutants below show they
bite:
* `test_with_nothing_there_nothing_names_the_row`;
* the policy test's `the edits` and `a team code in a tag` cases. t14's lines never quoted an own tag.

**21 mutants, all caught.**
* Each was applied alone, with the tests in a fresh process (`-p no:cacheprovider`,
  `PYTHONDONTWRITEBYTECODE=1`), and the file was restored and checked by SHA-256.
* The test files: the new suite, `test_render.py`, `test_scenario_vocabulary.py`,
  `test_link_chains.py`, `application/test_landscape_report.py` and the dry-run script's test: 354 tests.
* No Hypothesis is used, but each run still set `HYPOTHESIS_STORAGE_DIRECTORY` to a new empty
  directory (working agreement 8).
* `git status` was clean after both batches.

| Mutant | Failed | Caught by |
|---|---|---|
| The tag is chosen ahead of a labelled internal link (the PM's) | 5 | the variant golden, `test_each_row_takes_the_first_source_it_has`, `test_the_order_is_…`, the withheld-IL and team-code cases |
| An empty rank is shown instead of left out (the PM's) | 2 | the variant golden, `test_an_empty_row_is_left_out_and_counted_never_shown` |
| A withheld tag is shown instead of falling through (the PM's) | 12 | the variant golden, the order, fall-through and policy cases |
| The internal link is chosen ahead of the scenario | 130 | every golden; the coverage check refuses the scenario count |
| The card above is chosen ahead of the tag | 6 | both section goldens, the order and blank-tag cases |
| A blank text names the row | 2 | `test_a_blank_tag_is_no_tag`, `test_with_nothing_there_nothing_names_the_row` |
| No text is withheld | 13 | the variant golden, the fall-through and policy cases |
| A withheld text is passed over but not counted | 7 | the variant golden, the counting cases |
| A left-out row forgets what it passed over | 3 | `test_a_withheld_card_above_…`, the team-code case, `test_withheld_texts_…` |
| The own tag is never a candidate | 12 | every golden, the dry run's line |
| The card above is never a candidate | 6 | the variant golden, the card-above cases |
| A withheld internal link stays on the row and in the CSV | 2 | `test_a_withheld_internal_link_…`, `test_a_withheld_text_a_row_never_reaches_…` |
| A withheld card above stays on the row | 1 | `test_a_withheld_card_above_leaves_the_row_out_…` |
| The rows' withheld tags are not added to the kind's | 6 | the variant golden, the counting cases |
| Domain: a row may be named by a source it lacks | 4 | `test_a_row_is_named_only_by_a_source_it_has` (4 cases) |
| Domain: coverage counts sources in any order | 1 | `test_coverage_counts_each_source_once_in_naming_order` |
| Domain: coverage need not name or leave out every row | 1 | `test_coverage_names_every_row_once_or_leaves_it_out` |
| report.md: the left-out count is not said | 2 | the variant golden, `test_an_empty_row_…` |
| report.md: a named row carries no mark | 6 | every golden, both render tests |
| report.md: the kind's tags-withheld line prints the names withheld | 3 | the base and both section goldens |
| Dry run: prints the tags withheld as the rows left out | 1 | `test_the_dry_run_counts_the_impact_ranks_…` |

## Before the report (working agreement 10)

On `a479c74`:
* **The affected set is over two minutes.** `uv run scripts/affected_tests.py` chose 232 of 523 files
  (44.4%) from 18 changed files, in 7.0 s.
  * I ran them as `.venv/bin/python -m pytest -q -n 6 -m "not slow and not live" -p no:randomly
    <files>` under a 115 s alarm, at load average 4.5.
  * The alarm stopped it at 76%. Its progress lines up to then hold **5,184 passes and no failure or
    error**, and no process outlived it.
  * The rest is left to the pull request's `ci`, which runs the whole selection.
* **Within the two minutes, the tests of what changed and the always-run list:**
  * the files: `packages/debate_core/tests/arguments/landscape`; the landscape, plan-text,
    analytic-text, aff-assignment and classification tests in `packages/debate_core/tests/application`;
    `packages/debate_core/tests/domain`; `packages/debate_core/tests/integrations/landscape`;
    `packages/debate_cli/tests/test_landscape_command.py`; `tests/smoke/test_landscape_smoke.py`; the
    dry-run script's test; `tests/architecture`, `tests/specs`, the CLI's `test_app.py` and
    `test_help_rendering.py`; and the docs checks (`tests/docs`, `test_check_command_blocks.py`,
    `test_docs_index.py`);
  * the result: **3,073 passed in 28.20s**, at load average 7.5.
* `uv run --frozen ruff format --check .` → 1,458 files already formatted. `uv run --frozen ruff check .`
  → all checks passed.
* `uv run --frozen pyright`, bare as CI runs it → 0 errors, 0 warnings.
* `uv run --frozen lint-imports` → 18 kept, 0 broken. `scripts/check_thin_handlers.py` → 66 handlers
  within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 469 files.
* `scripts/check_command_blocks.py --base origin/dev` → no `#` comments, this report included.
  `scripts/docs_index.py --check-descriptions` → all 53 documents have a description.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`debate_core.domain.landscape_report`** (see Deviation 1):
  * `LeadInSource`, whose value is report.md's mark, and `LEAD_IN_ORDER`;
  * `ImpactCard.named_by`, with its check that the row has that source's text, and `runs_through`;
  * `NamedRows`, and `ChainCoverage`'s `named_rows`, `rows_left_out` and `withheld_tags`, with checks:
    one count per source in naming order, every row named or left out, and the rows a scenario names
    are the rows with one;
  * `rows_with_card_above`'s description.
* **`debate_core.arguments.landscape.link_chains`:** `rank_name` and `RankName`: the order, blank texts
  as none, and the fall-through; the docstring's section.
* **`debate_core.application.landscape_report`:** `_LinkChains.with_lead_in` names each row. A withheld
  internal link or card above is not kept on the row, and what each row passed over is counted. The
  kind's coverage counts the sources; the docstring's bullets.
* **`debate_core.arguments.landscape.render`:**
  * the rank lines with their marks, and the left-out line;
  * the kind's `Ranks named …` and `Tags withheld …` lines, replacing t14's internal-link and card-above
    line;
  * the How-to-read bullet, and the CSV columns' docstring.
* **`scripts/landscape_dry_run_by_section.py`:** one counts-only line per kind. See Deviation 2.
* **Tests:**
  * `packages/debate_core/tests/arguments/landscape/test_readable_impact_chains.py`, new;
  * `test_render.py`: t14's card-above test, now on marked lines, and a mark-and-escape test;
  * `tests/scripts/test_landscape_dry_run_by_section.py`: the new lines, and a hand-set count test.
* **Fixtures** (`tests/fixtures/landscape/`):
  * `golden/report.md` and `scenario_vocabulary/impact_sections.md`, edited by hand;
  * `readable_impact_chains/`, new: the edits, the README, the sections and the CSV;
  * a paragraph in `synthetic_caselist/README.md`.
* **`docs/guides/landscape-taxonomy.md`:** what names each rank, its mark, the ranks left out, and
  withholding.

## Deviations from the spec

1. **`debate_core.domain` is outside `constraints.packages`.**
   * A rank's source and the kind's counts are report values, and `debate_core.domain.landscape_report`
     is where the report's values live.
   * The counts must reach report.md and the dry-run script. The withholding is the application's, so
     the renderer cannot work them out.
   * t22 recorded the same Deviation, and the PM's ruling of 2026-10-26 adds `debate_core.domain` to
     that spec in the next batch. This task asks the same.
2. **`scripts` and `tests/scripts`** (the dry-run line and its test) are outside `constraints.packages`.
   The PM pre-approved both in the brief of 2026-10-26, and adds them in the next batch.
3. **ac1's counts were run by the session.** They were read-only, over files the operator already has,
   and finished in 51 s. Working agreement 2 and the PM's brief ("If the count runs past two minutes,
   hand it to the operator") allow that.

## Decisions and assumptions

* **Which quoted texts are withheld.** Only the lines under "What each impact runs through" withhold a
  tag, as the PM's brief scopes it ("a withheld candidate falls through"). impact_cards.csv's
  `internal_link_tag` is the same internal link, so a withheld one is empty there too. On hspolicy26
  none is withheld.

  The impact table's Tag column, the link-chain table and `top_cards.csv` are t10's and t14's, and
  still quote every tag as parsed ([question 2](#questions-for-the-pm)). The variant golden shows this:
  `2. Extinction from a Cedarvale collapse` stays in its table row and chain row, and its rank is named
  by the card above.
* **A withheld text is counted only when a rank reaches it,** as t14's rule 9 counts only the names that
  would otherwise show. A withheld internal link under a rank its scenario names is not counted, but it
  is still kept off the row and the CSV (`test_a_withheld_text_a_row_never_reaches_…`).
* **No new quoting or length rule.** t14 quotes a tag whole, as parsed, through `_cell`, and has no
  length rule, so a name is quoted the same way. A text of only whitespace counts as none.
* **The card above stays t14's:** kept on the row only when no labelled internal link is (now: none that
  is not withheld). With the new order that changes nothing a reader sees.
* **The marks** are the PM's words: `(scenario)`, `(internal link)`, `(tag)`, `(card above)`.
* **The left-out line is per position**, after its named lines: "Ranks left out, with no scenario,
  internal link, tag or card above to name them: N." It appears only when N is above 0. Each kind also
  says it: "Ranks named by a scenario: …; by an internal link: …; by the impact card's tag: …; by the
  card above it: …; left out: …".
* **t14's kind line was replaced.** "With a labelled internal link: … of which … show the card above it
  in the file" would now be untrue, since the card above shows only when it names a rank. The fields
  `rows_with_internal_link` and `rows_with_card_above` stay on `ChainCoverage` for t14's tests and the
  validator.
* **impact_cards.csv's columns are unchanged.** The spec asks for report.md only.
* **No branch-over-impact nesting, no mechanisms, no model, no taxonomy change**, as the brief rules.

## Operator follow-ups

1. **ac3: the dry run on hspolicy26. Done** (2026-10-26, 70.7 s; [results](#the-operators-dry-run-ac3)). For a later run:
   * It is the landscape service as a dry run without `--publish`: read-only, no bucket lock, nothing
     written. Expected runtime: about 75 s on the caches t22's refill left warm (t22's run: 70.9 s).
   * It prints counts and ids only, never a name, tag, text, team or school.
   * It refuses to start if a `DEBATE_*` variable is set or a `caselist pull` is running.

   From the task worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t25-readable-impact-chains
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/landscape_dry_run_by_section.py --caselist hspolicy26 --snapshot 2026-10-20; fi
```

   **Success looks like:**
   * `Dry run of hspolicy26 through 2026-10-20, taxonomy 1.4.0: nothing written; 7 files planned.`
   * `Scenarios, advantage (… positions): 43 impact rows, 0 with a scenario, 1 names withheld; …` and
     `Scenarios, da (… positions): 44 impact rows, 9 with a scenario, 0 names withheld; …`, as in t22's
     run.
   * **The new lines. These are the counts after**, as the session's recount predicts:
     * `Impact ranks named, advantage: 0 by a scenario, 0 by an internal link, 39 by a tag, 2 by the
       card above; 2 left out; 4 tags withheld.`
     * `Impact ranks named, da: 9 by a scenario, 4 by an internal link, 29 by a tag, 0 by the card
       above; 2 left out; 2 tags withheld.`
   * **The counts before** are ac1's: with a labelled internal link advantage 0 and DA 7, and only a
     card above 30 and 11. Under t14's lines every other rank said "no labelled internal link", 13 and
     26 of them with nothing more.
   * The scan lines: t22's 9 hits, all accepted earlier (1 in a plank table, 8 in `top_cards.csv`), and
     **no hit** in report.md's `Advantages: impact cards` or `Disadvantages: impact cards` sections.
     Those sections now quote the impact cards' tags, which each pass the report's stricter word-level
     withholding.

   Paste every line back. A `Refused:` line means the run did not start, and says why. If the new lines
   match, the session records them here, marks ac3 PASS and sets the Goal to `Succeeded`.

   A number that differs from the prediction is a finding, not a failure. The store may have moved since
   the counts (its classification cache is from 2026-10-26 01:27), so paste it and the session explains it.

2. **No publish.** The republish follows the cloud cutover, as for t22.

3. **The pull request, after the PM's review.** The branch must not be behind `origin/dev`, so sync once
   more, then open the PR, from the task worktree:

```bash
scripts/task sync v1-e32-t25-readable-impact-chains
```

```bash
scripts/task pr v1-e32-t25-readable-impact-chains
```

## Follow-up work

* **Withholding in the impact table and the link-chain table** (E32). t10's and t14's tables quote every
  tag as parsed. On hspolicy26, 6 own impact tags and 7 card-above tags hold a caselist word by
  `is_withheld`'s rule, though t22's scan found no hit there. Count which words they are first
  ([question 2](#questions-for-the-pm)).
* **Branches and mechanisms over impacts:** the PM's new E32 task, untouched here, as briefed.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
