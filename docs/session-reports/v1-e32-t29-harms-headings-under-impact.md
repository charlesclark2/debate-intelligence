# Session report: v1-e32-t29-harms-headings-under-impact

| | |
|---|---|
| Task | `v1-e32-t29-harms-headings-under-impact` — Harms headings counted under Impact, the word the coach's debaters use |
| Spec | [`plan_specs/v1/e32-argument-landscape/t29-harms-headings-under-impact.yaml`](../../plan_specs/v1/e32-argument-landscape/t29-harms-headings-under-impact.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t29-harms-headings-under-impact` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Built as the PM ruled (Q1 (A), Q2 yes, 2026-10-27). The Goal is `Succeeded`.**

The task ran in two sessions.
* **The first** took ac1's counts and stopped at the PM's stop condition (b). Its counts and its relay
  prompt are [below](#the-counts-ac1), unchanged.
* **The PM's ruling:** build as pre-ruled, with `debate_core.application`, `debate_core.domain` and
  `docs/guides` added to the packages, `ChainRole.HARMS` removed, and the four FYIs accepted
  ([the ruling](#the-pms-ruling-2026-10-27)).
* **The second** built it.

**One rule, in one place.** In `link_chains.heading_roles`, an advantage's `harms` or `harm` heading
labels Impact. It is read only where the Harms role read it: a sub-heading below the placing heading,
not an answer, naming no other role. An advantage's or DA's impact cards are now the counted cards
whose roles hold Impact. So the impact table, impact_cards.csv, the chain's Impact row, t25's card
above, and the documents with no labelled impact all read one set. `ChainRole.HARMS` and the "Harms"
label are gone. No taxonomy id changed.

**On hspolicy26 through 2026-10-20, after the build** (the same reading built with the old and the
new code, [below](#hspolicy26-before-and-after-the-build)):
* **One advantage's impact table moves: Costs advantage (`costs-advantage`).**
  * Its rank 1 is now a cluster read by 3 teams. It was rank 4, tied on 2 teams.
  * The old ranks 1 and 2 are now ranks 2 and 3, and the old rank 3 drops off.
  * The chain's Impact row goes from 2 teams to 3.
* **Nothing else moves.**
  * The other 15 advantages are unchanged.
  * Every DA row is byte for byte the same.
  * Not one count of what names a rank changed, the card-above counts included.
* **Advantage documents with no labelled impact:** 753 of 1,164, now 751.
* **Rows:** link-chain rows go from 96 to 95, the one Harms card row dropped.
* **"Harms" in report.md:** 18 times, now 0. The word `harms`/`harm` stays in one header line, which
  says that heading labels an advantage's impact.

**Tests:**
* The goldens were written by hand first and run red against the unchanged code: 28 failed.
* The PM's three mutants and six more were all caught.
* The synthetic fixture now has an advantage with only harms headings, one with both, and a DA
  untouched.
* t28's withholding holds on a row the fold adds.

## The PM's ruling, 2026-10-27

> Q1: (A), build as pre-ruled. The rank-1 change is the fold doing what it says: one more team read
> that cluster as its impact, breaking a 4-way tie on a single advantage. Name the change in the
> build's report (before and after, counts only) and in the republish block's pilot check, so the coach
> knows which advantage's impact table moves.
>
> Q2: yes. debate_core.application, debate_core.domain and docs/guides are added to
> constraints.packages in the PM's batch of 2026-10-27 (w), and you may change them now. Remove
> ChainRole.HARMS rather than leaving it unused, since nothing persists it.
>
> The FYIs are accepted as you wrote them: one rule in link_chains.heading_roles […]; an advantage's
> impact cards are the cards whose roles hold Impact […]; t14's scenario names treat "<words> harms" as
> "<words> impact"; t25's "card above, unless it is an impact card" counts a harms card as an impact
> card. Count the lead-in changes in the report.

Batch (w) reached `dev` during the build (`a197923`). The branch was synced onto it with
`scripts/task sync`. Its `constraints.packages` line is the ruling's, and I did not edit the spec.

## The build (ac2)

| Where | What changed |
|---|---|
| `arguments/landscape/link_chains.py` | `HARMS_WORDS`. `heading_roles` adds Impact for an advantage's harms word, and nothing for a DA's. `card_roles` keeps a sub-heading's sole Impact label: it adds a card only for a harms heading, since an impact word there is t10's impact card already. `card_scenario` takes the harms words off an advantage's heading as label words, so `Dome harms` names `dome` as `Dome impact` does, and a bare `Harms` names nothing. The module docstring says why: the coach's word, 2026-10-27. |
| `domain/landscape_report.py` | `ChainRole.HARMS` removed, and with it the role from `CHAIN_ROLES[ADVANTAGE]`. |
| `application/landscape_report.py` | `_LinkChains` builds the impact cards itself: per DA and advantage, the counted cards whose roles hold Impact (`_is_impact`, using the matcher's placing heading). `build` reads them from it for the impact table and the impact coverage. The card above a row uses the same rule. The kind-blind `_is_impact` and its `is_impact_card` import are gone. The module docstring gains "Its impact cards". |
| `arguments/landscape/render.py` | No "Harms" label. The **Impact cards** header line adds "Under an advantage, a heading saying `harms` or `harm` labels its impact too: debaters call that part of an advantage its impact." The **link chain** line drops harms. |
| `docs/guides/landscape-taxonomy.md` | The chain-roles line names impact for a harms heading. A new line, **Harms is an advantage's impact**, gives the why: the coach's word, 2026-10-27. The scenario line adds `Dome harms`. It also drops a tournament's words from what withholds a name, which t28's ruling had already changed ([Decisions](#decisions-and-assumptions)). |

### The fixture and its goldens

[`tests/fixtures/landscape/harms_under_impact/`](../../tests/fixtures/landscape/harms_under_impact/README.md)
changes five cards' headings on the synthetic caselist, and nothing else. Its README works out every
expected cell by hand.

| Card | New headings | Case | Expected |
|---|---|---|---|
| `a4` ¶0, `a6` ¶3 (cluster 6) | `innovation advantage` > `harms` / `harm` | **Only harms** | Innovation gets an impact table: rank 1, 2 teams, named by its tag. Its chain gets an Impact row, 2 teams. |
| `a3` ¶3 (cluster 2) | `costs advantage` > `harm` | **Both** | Costs rank 1 keeps its card, now 2 teams, and its scenario. The chain's Impact row has 2 teams. |
| `a5` ¶9 (cluster 38) | `costs advantage` > `harms` | Both, past the table | Counted at rank 4, not shown. |
| `b5` ¶3 (cluster 14) | `spending da` > `harms` | **A DA, untouched** | Nothing a DA shows changes. |

* **Advantage documents with no labelled impact:** 3 of 6, now 1 of 6.
* **Advantage documents with no scenario heading and no role label:** 1 of 6, now 0 of 6.
* **The gap line:** it loses its `harms 2 of 2` entry, and impact goes from `1 of 2` to `0 of 2`.

The hand-written goldens are `impact_sections.md` and `impact_cards.csv`.

`test_harms_under_impact.py` (14 tests) also checks these things:
* The rest of report.md is `golden/report.md`'s.
* No role named harms is left.
* "Harms" is in no table or line. `harms` is named only in the header's Impact cards line, and in no
  CSV.
* Every harms card is counted past the ranks shown (`impact_cards=10`).
* The documents with no labelled impact count the harms cards.
* The chain's Impact row is the impact table's rank 1, with its harms teams.
* A harms heading labels nothing when it also names another role, when it answers, or when it sits at
  or above the placing heading.
* A DA's `harms` changes nothing a DA shows: impact rows, chain rows and both coverages.
* **t28's withholding:** a school word in the tag of the row the fold adds leaves the impact cell and
  the chain's Impact cell empty, with teams and cite kept. The table counts read 1 / 1 / 0, and the
  rank is left out and counted.
* **t25's card above:** a harms card above an impact card is an impact card, as an `impact` card is,
  so it is not the card above. A DA's harms card above is still shown.

`test_link_chains.py` gains the rule's unit cases:
* harms labels an advantage's impact, and nothing of a DA's;
* a harms heading naming another role labels neither;
* `Dome harms` names `dome` under an advantage and `dome harms` under a DA.

**Older goldens this changes, edited by hand:**
* `golden/report.md`: the two header lines, no Harms rows, and no `harms 2 of 2`.
* The `impact_sections.md` of `readable_impact_chains/`, `link_lead_ins/`, `tags_in_the_tables/` and
  `scenario_vocabulary/`: no Harms rows, and no `harms 2 of 2`.
* `test_landscape_report.py`: the advantage's role gaps lose `("harms", 2)`.

### Tests shown failing first

The goldens, the fixture and the tests were committed first (`ca5fb4b`), and run against the unchanged
code:

```bash
.venv/bin/python -m pytest -n 4 -p no:randomly -m "not slow and not live" -q --tb=line packages/debate_core/tests/arguments/landscape packages/debate_core/tests/application/test_landscape_report.py
```

**28 failed, 1,125 passed in 104.85 s**, under a load of about 5 to 14. Every failure is an
`AssertionError` on the behaviour asked for, but one: the withholding test's `StopIteration`, because the
Innovation impact row the fold adds does not exist yet.
* **Golden mismatches:** report.md (6), the impact sections (5) and impact_cards.csv (1).
* **Role assertions:** `frozenset({HARMS})` where Impact was asked for.
* **Counts:** `('02', 1) == ('02', 2)` and `[] == [('06', 1)]`.
* **No harms role:** `'harms' in {…}`.
* **The DA case:** it fails only once harms is read for a DA (mutant 3).

**After the build:** 1,153 passed in 3.44 s, on the same command.

### Mutants (agreement 8)

Each was run against `packages/debate_core/tests/arguments/landscape` and
`packages/debate_core/tests/application/test_landscape_report.py`:
* each run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (no test here uses Hypothesis);
* none errored at collection;
* `git checkout` restored the file after each, and `git status` was clean after both batches.

| Mutant | Result | Caught by (among others) |
|---|---|---|
| **PM (1)** a harms card dropped instead of counted under Impact (`heading_roles` without the harms clause) | caught, 15 failed | the impact golden and CSV, `test_every_harms_card_is_counted_under_impact_past_the_ranks_shown` |
| **PM (2)** "Harms" still printed in one place (the link-chain header line names harms again) | caught, 7 failed | `test_harms_is_named_only_where_the_header_says…`, every rest-of-report.md golden |
| **PM (3)** harms read as impact for a DA too | caught, 9 failed | `test_a_das_harms_heading_changes_nothing_a_da_shows`, the impact golden |
| `card_roles` keeps its old "no sole Impact label" guard | caught, 9 failed | the goldens, the count tests |
| Impact cards picked kind-blind again (`is_impact_card`) | caught, 8 failed | the goldens, the count tests |
| The card above read kind-blind again | caught, 1 failed | `test_a_harms_card_above_an_impact_card_is_an_impact_card_not_the_card_above` |
| `Dome harms` names `dome harms` under an advantage | caught, 2 failed | the scenario unit tests |
| The harms words taken off a DA's heading too | caught, 1 failed | `test_the_words_beside_an_advantages_harms_label…` |
| Harms read in any heading, not only where the role read it | caught, 3 failed | the "another role", "answers" and "at or above" tests |

The card-above mutant is caught by one test only. That test is its own case: a harms card above an
impact card, in one block.

### hspolicy26 before and after the build

**How it ran:**
* The ac1 script's reading (read-only, over `~/.debate-research/dev`, no container or pool) was built
  twice. Each build ran under a 115 s alarm on the interpreter.
* **Before:** the pre-build source (`git archive` of the red commit's `packages/debate_core/src`, first
  on `PYTHONPATH`), in 53.1 s.
* **After:** the branch's code, in 53.8 s.
* **The store was unchanged:** `debate.sqlite3`'s SHA-256 was `feac070d…` before and after. No
  `DEBATE_` variable was set, and no process outlived either run.
* **Counts only:** cluster digests stayed in the scratchpad.

| hspolicy26 through 2026-10-20 | Before | After |
|---|---|---|
| Impact rows / link-chain rows / top_cards.csv rows | 87 / 96 / 368 | 87 / **95** / 368 |
| Advantages whose impact rows change | — | **1 of 16 (`costs-advantage`)** |
| Costs advantage, teams of ranks 1, 2, 3 | 2, 2, 2 | **3**, 2, 2 |
| Costs advantage, where the after ranks were before | — | rank 1 was rank 4 (off the table); ranks 2 and 3 were ranks 1 and 2 |
| Costs advantage chain: Impact row teams; Harms row | 2; 1 team | **3**; gone |
| Costs advantage, what names each rank | tag, tag, tag; each with a card above | tag, tag, tag; each with a card above |
| Advantage documents with no labelled impact | 753 of 1,164 (64.7%) | **751** of 1,164 (64.5%) |
| Advantage documents with no scenario heading and no role label | 676 of 1,164 | 676 of 1,164 |
| Ranks named, advantage: scenario / internal link / link / tag / card above; left out | 0 / 0 / 0 / 41 / 1; 1 | 0 / 0 / 0 / 41 / 1; 1 |
| Rows with a card above, advantage / DA | 30 / 10 | 30 / 10 |
| Scenario names withheld; tags withheld (advantage) | 0; 2 | 0; 2 |
| Tags left empty (impact / chain / top_cards.csv) | 2 / 2 / 18 | 2 / 2 / 18 |
| Positions with no labelled card, advantage | … impact 1, **harms 15**, inherency 14 … of 16 | … impact 1, inherency 14 … of 16 |
| Every DA impact row and chain row, and both DA coverages | — | byte for byte the same |
| Whole-word `harms`/`harm` in report.md; `\| Harms \|` rows | 18; 16 | **2 (one header line); 0** |
| … in impact_cards.csv | 0 | 0 |

**The lead-in changes the PM asked to count: none.**
* Every advantage and DA count of what names a rank is the same, and so are the rows with a card above.
* The three Costs ranks are named by their tags before and after, and each has a card above.

The published report.md of 2026-10-27 (78,897 B) shows the "before" column: `753 of 1,164 (64.7%)`,
Costs ranks at 2, 2, 2 teams, and `harms 15 of 16`.

## The counts (ac1)

**What ran:**
* A read-only script in the session's scratchpad, wired by hand as t28's counts were:
  * over `~/.debate-research/dev`;
  * no container, no worker pool, no aff assignments and no analytic texts;
  * the classification cache read through the run's read-only view.
  * It captures the report's own `_LinkChains`, so a card's roles, sub-headings and impact cards are
    read exactly as the report reads them.
* The script:
  `/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e32-t29-harms-headings-under-impact/9212a325-8372-4c2e-ae27-200339aed9b5/scratchpad/counts/count_harms.py`.
  The synthetic count is `count_synthetic.py` beside it.
* **Code:** HEAD `40f9d3d`, which already holds t28 (`414ad95`). No sync was needed.
* **Input:** hspolicy26 through 2026-10-20, taxonomy 1.4.0.
* **Runs:** three runs of 49.1 s, 51.2 s and 68.6 s, each under a 115 s alarm on the interpreter.
  The later two added detail fields only. Every count they share is the same in all three.
* **The store was unchanged:** `debate.sqlite3`'s SHA-256 was `feac070d…` before and after. No
  `DEBATE_` variable was set, no `caselist pull` was running, and no process outlived a run.
* **The published bundle:** the counts below match the report.md published at 01:13 on 2026-10-27
  (78,897 B). It has 16 `| Harms |` rows, 15 of them empty, and the line `harms 15 of 16`.

### Harms rows and what they carry

| | Synthetic caselist | hspolicy26 |
|---|---|---|
| Advantages with a link-chain table | 2 | 16 |
| … with a Harms row (a labelled card) | 0 | **1** |
| … of those, also with an Impact row | 0 | **1** |
| Advantages with an Impact row | 1 | 15 |
| Counted cards in the Harms role (all advantages) | 0 | 16 |
| … distinct clusters | 0 | 12 |
| … documents | 0 | 3 |
| … heading blocks (a document and its headings down to the harms one) | 0 | 5 |
| … already impact cards today (tag or heading) | 0 | 1 |
| Harms sub-headings by form: `harms` / `harm` | 0 / 0 | 8 / 8 |
| Harms sub-headings holding other words besides the label (distinct / card headings) | 0 / 0 | 2 / 8 |
| … of those word sets used by two or more teams | 0 | 0 |
| Advantage cards with a harms heading at or above the placing heading | 0 | 0 |
| **Stop condition (a):** counted non-advantage cards with a harms word in any heading | 0 | **0** |

All 16 harms cards on hspolicy26 are under one advantage.

### Where "Harms" reaches the output today

| Place | Synthetic caselist | hspolicy26 |
|---|---|---|
| report.md link-chain tables, `Harms` rows | 2 (both "no labelled card") | 16 (15 "no labelled card") |
| report.md per-kind line "Positions with no labelled card, by role: … harms N of M" | 1 (`harms 2 of 2`) | 1 (`harms 15 of 16`) |
| report.md header bullet "**The link chain** … for an advantage harms, inherency and solvency" | 1 | 1 |
| report.md lines under "What each impact runs through" | 0 | 0 |
| report.md, every whole-word `harm`/`harms` (the three places above, no tag holds one) | 4 | 18 |
| impact_cards.csv (it has no role column; no tag holds the word) | 0 | 0 |
| The dry run, `scripts/landscape_dry_run_by_section.py` (it prints no role) | 0 | 0 |
| The guide, `docs/guides/landscape-taxonomy.md` line 586 | 1 | 1 |

`ChainRole.HARMS` is never persisted. No stored report, cache or CSV holds the value `harms`, so
removing the role leaves nothing to migrate.

### What-if: harms read as impact

I took the what-if over the same reading. Each advantage's impact reads became its impact cards
today, plus every card in its Harms role. They were then ranked by the report's own `_ranked`, the
rule both the impact table and the chain's Impact row use.

| Advantages (hspolicy26) | Count |
|---|---|
| Unchanged (no harms card) | 15 |
| Same rank 1, counts added | 0 |
| **A new rank 1** | **1** |
| Impact rank 1 where there was none | 0 |

**Stop condition (b):** one advantage has both rows, and its rank 1 changes. That is 1 of 1, over
half.

The one advantage that changes, before → after:

| | Before | After |
|---|---|---|
| Impact card reads | 47 | 62 |
| Impact clusters | 12 | 22 |
| Documents with an impact card | 43 | 45 |
| Clusters read by two or more teams | 4 | 4 |
| Teams of the three ranks shown | 2, 2, 2 | 3, 2, 2 |
| Rank-1 card | its old rank 1 | its **old rank 4** (2 teams before, 3 after) |
| Where the old rank 1 goes | — | rank 2 |
| Old shown ranks still shown | — | 2 of 3 (the old rank 3 drops off) |
| Is the new rank 1 the card in today's Harms row? | — | no |
| Harms reads in the new rank-1 cluster | — | 1 |

**Why the rank changes:** all four 2-team clusters were tied, and the cluster id decided their
order. The one harms read adds a team to the one cluster that was just off the table. No count is
lost: every harms read lands under Impact (47 + 15 new reads = 62; the 16th harms card was already
an impact card).

**Scenario names.** The scenario names shown would not change. Two harms sub-headings hold words
besides the label, on 8 card headings, but no team pair shares one.

## Question for the PM

The first session's relay prompt, as sent. The PM's answer is [above](#the-pms-ruling-2026-10-27).


````text
v1-e32-t29 (harms headings under Impact): stopped at your stop condition (b), counts only, nothing built.

Facts (hspolicy26 through 2026-10-20, taxonomy 1.4.0, read-only; synthetic caselist has no harms heading):
- 1 of 16 advantages has a Harms row; all 16 harms cards (12 clusters, 3 documents) are under it. The
  other 15 print an empty "Harms | no labelled card" row. No DA, CP, K or aff card has a harms heading
  (condition a: no). No taxonomy or override uses "harm"/"harms" (condition c: no).
- That one advantage is also the only one with both rows, and the fold changes its impact rank 1: 1 of 1,
  so condition (b) holds.
- How: the new rank 1 is NOT a harms-only card. It is an impact cluster already counted at rank 4, tied
  with three others on 2 teams and kept off the 3-row table by the cluster-id tie-break. One copy read
  under a "harm" heading gives it a third team. Old rank 1 -> rank 2; old rank 3 drops off. Impact reads
  47 -> 62, clusters 12 -> 22, documents 43 -> 45; no count lost.
- "Harms" reaches report.md in 18 places (16 chain rows, the "harms 15 of 16" gap line, the header
  bullet), the guide once, and nothing else (not impact_cards.csv, not the dry run, no lead-in line).

Question 1, the stop:
  (A) Build as pre-ruled. The rank-1 change is the fold doing what it says: one more team read that card
      as its impact. The trigger is a 1-advantage denominator and a 4-way tie.   <- recommended
  (B) Build, but leave the impact ranking as today and only drop the Harms row, label and line. This loses
      the 15 harms reads from Impact, so it breaks "no count lost".
  (C) Hold the task; tell the coach what changes first.
Recommendation: (A). The rule (b) guards against the fold reshuffling impacts widely, and here it moves
one tied cluster up from just off the table on one advantage. I would name the change in the report and
in the republish's pilot check.

Question 2, scope: the build cannot stay inside constraints.packages. Impact cards are picked kind-blind
in debate_core/application/landscape_report.py (`_is_impact`, before the matcher is built), and the roles
an advantage's table shows are CHAIN_ROLES / ChainRole.HARMS in debate_core/domain/landscape_report.py.
The guide line you asked for is in docs/guides/landscape-taxonomy.md. May I add those three paths to
constraints.packages? (Recommended: yes. Nothing persists ChainRole.HARMS, so I would remove the member,
not leave it unused.)

FYI, what I'll do unless you say otherwise:
- One rule, in link_chains.heading_roles: for an advantage, `harms`/`harm` label Impact. An advantage's
  impact cards become the cards whose roles hold Impact, so the impact table, impact_cards.csv, the
  chain's Impact row and the "no labelled impact" counts all read the same set. Harms is read only where
  the Harms role read it today (a sub-heading below the placing heading, not an answer, naming no other
  role), so no card is gained or lost beyond that.
- t14's "words beside an impact label" names a scenario from "Dome harms" as from "Dome impact"; a bare
  "Harms" names none. On hspolicy26 this shows no new name (no two teams share the words).
- t25's "card above, unless it is an impact card" treats a harms card above as an impact card. I'll
  count the lead-in changes in the build's report.

Reply with: Q1 A/B/C, Q2 yes/no, and any FYI you want changed.
````

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `harms-under-impact` (Harms under Impact) | Done | Counted first (first session); built after the PM's ruling; its criterion passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts first, where harms reaches the report and what it carries, in the report | PASS | `count_harms.py` (hspolicy26) and `count_synthetic.py` (synthetic), first session → [the counts](#the-counts-ac1); after the build, `count_after.py` before and after → [hspolicy26 before and after](#hspolicy26-before-and-after-the-build) |
| ac2: on the synthetic fixtures no section reads "Harms", its cards and headings counted under the advantage's impact with no count lost, matching hand-written goldens, tests shown failing first | PASS | Red: 28 failed, 1,125 passed against the unchanged code ([above](#tests-shown-failing-first)). Green: `.venv/bin/python -m pytest -n 4 -p no:randomly -m "not slow and not live" -q packages/debate_core/tests/arguments/landscape packages/debate_core/tests/application/test_landscape_report.py` → `1153 passed in 3.44s` |
| Node: Landscape tests pass, `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | Run as `.venv/bin/python -m pytest packages/debate_core/tests/arguments/landscape` under a 110 s alarm → `1047 passed in 11.35s` |

## Before the report (working agreement 10)

After the last sync (onto `4c0fe72`, the PM's batch (w) and the index refresh):

* **The affected set** (`uv run scripts/affected_tests.py`) is 216 of 553 test files, from 19 changed
  files. It reaches that far because of the domain and application modules. That is past two minutes,
  so it is left to the pull request's `ci`.
* **Within two minutes**, the touched suites:
  * Every landscape test file in the set, the 22 outside `arguments/landscape` among them: API image,
    CLI command, application, domain, integrations, scripts and smoke. Run as
    `.venv/bin/python -m pytest -n 6 -m "not slow and not live" -q packages/debate_core/tests/arguments/landscape <those 22 files>`
    → `1439 passed in 18.96s`.
  * The always-run list, 22 files, in three commands. As one command it ran into the alarm twice in
    this session's load. A killed run was not counted, and none left an orphan the second time.
    * The 19 lighter files → `1116 passed, 1 warning in 40.43s`.
    * `tests/scripts/test_affected_tests.py` and `test_affected_tests_planted_breaks.py` → `77 passed in
      11.23s`.
    * `tests/scripts/test_ci_workflow_test_job.py` → `22 passed in 15.59s`.
* **Checks:**
  * `uv run ruff format --check packages/debate_core scripts` → `832 files already formatted`.
  * `uv run ruff check packages/debate_core scripts` → `All checks passed!`.
  * `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`.
  * `uv run lint-imports` → `Contracts: 18 kept, 0 broken.`
  * `uv run scripts/validate_specs.py` → `OK: 492 files, 40 epics, 430 tasks, 22 releases`.
  * `uv run python scripts/check_links.py` → `OK: 2793 relative links and anchors in 429 Markdown files`.
  * `uv run python scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 533 shell
    code blocks in 194 Markdown files (1 session reports changed since origin/dev)`.
  * `uv run scripts/validate_specs.py --require-succeeded v1-e32-t29-harms-headings-under-impact` →
    `Succeeded`, after the phase was set.

## Files changed

* **`packages/debate_core/src/debate_core/arguments/landscape/`:** `link_chains.py`, the one rule;
  `render.py`, no Harms label and the two header lines.
* **`packages/debate_core/src/debate_core/domain/landscape_report.py`:** `ChainRole.HARMS` removed.
* **`packages/debate_core/src/debate_core/application/landscape_report.py`:** impact cards read from
  roles, in `_LinkChains`.
* **`packages/debate_core/tests/`:** `test_harms_under_impact.py` (new); `test_link_chains.py` and
  `test_landscape_report.py`, with the harms role's cases replaced.
* **`tests/fixtures/landscape/`:**
  * `harms_under_impact/`, new: the README, `edits.yaml` and the two hand-written goldens;
  * `golden/report.md` and four `impact_sections.md`, edited by hand.
* **`docs/guides/landscape-taxonomy.md`:** the chain-roles line, the new harms line, and the scenario
  line.
* **`docs/session-reports/v1-e32-t29-harms-headings-under-impact.md`:** this report.
* **The spec:** only the phase, `Succeeded`.

## Deviations from the spec

None at the end. The first session's one was the build needing `debate_core.application`,
`debate_core.domain` and `docs/guides`. The PM's batch (w) added all three to
`constraints.packages`, and it is on `dev`.

## Decisions and assumptions

* **"Read only where the Harms role read them."**
  * A harms heading labels an advantage's impact as a sub-heading below the placing heading, not an
    answer, and naming no other role.
  * A heading that is the position's own heading, or above it, labels nothing, as before. So does
    `Harms and solvency`.
  * `Harms impact` labels Impact, as before through its impact word.
  * Three tests pin it, and the "any heading" mutant shows they matter.
* **Scenario words beside a harms label are read for an advantage only.**
  * `Dome harms impact` under an advantage now names `dome`. It named nothing before: two roles' labels
    fill neither.
  * Under a DA, `harms` is not a label, so the words keep it: `dome harms`.
  * On hspolicy26, no shown name changes (none of the 2 word sets is used by two teams).
* **The header says `harms` once.** The Impact cards line says a harms heading labels an advantage's
  impact, so a reader knows why those cards are there. "Harms" as a row, a section or a role is gone.
  The test allows the word only in that line.
* **Both kinds read their impact cards from roles**, and a DA's are t10's exactly. A DA's sole-Impact
  sub-heading holds an impact word, so it is already t10's impact card. All DA rows on hspolicy26 are
  identical.
* **The guide's scenario line** also said a name is withheld for a tournament's words. t28's ruling
  ended that, and its report corrected two other such sentences. This one sat in the bullet I was
  editing, so I corrected it in its own commit (`91a2129`).

## Operator follow-ups

**The republish to dev, after this task merges into `dev`, on any day but a Wednesday** (the cloud run's
day). Nobody ran it in this task. It is t28's block, with this task's merge check and a Wednesday check.
It reads the Mac's dev working copy, as t28's did, and in bucket mode it holds the dev run lock while it
publishes.

**Operator command** (expected runtime ~2 min, most of it the report's build)
Where: the `dev-preview` worktree, after this task has merged into `dev`, not on a Wednesday
```bash
cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview"
git fetch origin
git switch --detach origin/dev
grep -q 'HARMS_WORDS: Final' packages/debate_core/src/debate_core/arguments/landscape/link_chains.py && echo "ok: v1-e32-t29 merged at $(git rev-parse --short HEAD)" || echo "STOP: origin/dev has no v1-e32-t29"
aws sso login --profile debate-dev-evidence
if [ "$(date +%u)" = 3 ]; then
  echo "STOP: it is Wednesday, the cloud run's day"
elif env | grep -q '^DEBATE_'; then
  echo "STOP: unset these first: $(env | grep -o '^DEBATE_[A-Za-z_]*' | tr '\n' ' ')"
elif pgrep -f "caselist pull" > /dev/null; then
  echo "STOP: a caselist pull is running"
else
  uv run debate-research landscape report --caselist hspolicy26 --publish --dry-run
fi
```

What to read before going on:

* The first line must be `ok: v1-e32-t29 merged at <commit>`. Stop on any `STOP` line.
* The dry run names hspolicy26's newest snapshot and its counts. Positions read must be above zero, and
  planned uploads must be above zero.
* **If the scan held the publish back (exit 1),** read its hits with the PM.
  * A hit may name a tournament inside a card's tag, as t28's report expected. Every tag this task
    adds to a table is held to t28's withholding.
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
if [ "$(date +%u)" = 3 ]; then
  echo "STOP: it is Wednesday, the cloud run's day"
elif env | grep -q '^DEBATE_'; then
  echo "STOP: unset these first: $(env | grep -o '^DEBATE_[A-Za-z_]*' | tr '\n' ' ')"
elif pgrep -f "caselist pull" > /dev/null; then
  echo "STOP: a caselist pull is running"
else
  uv run debate-research landscape report --caselist hspolicy26 --publish --accept-scan-hits DIGEST_FROM_THE_DRY_RUN
fi
```

Success looks like `Uploaded N, unchanged M` to `reports/landscape/hspolicy26/<snapshot>/`.
* N is at least 2: report.md (its header and every advantage's chain table) and impact_cards.csv
  change.
* N plus M equals the dry run's planned uploads.

**The pilot check.** Wait at least five minutes after the upload.
1. Sign in at <https://tub.dev.wfbdebate.com/landscape/hspolicy26>.
2. Find the word "Harms": no link-chain table has a Harms row, and the advantages' line "Positions with
   no labelled card, by role" names no harms.
3. **The one impact table that moves is the Costs advantage's.** For the snapshot through 2026-10-20:
   * its impact cards read 3, 2, 2 in the Teams column (they read 2, 2, 2);
   * its link chain's Impact row reads 3 teams;
   * "Advantage documents with no labelled impact" reads `751 of 1,164 (64.5%)` (it read 753).

   A newer snapshot has its own counts, but the Costs advantage's table is still the one to look at.
4. Paste the upload line, the Costs advantage's Teams column and the "no labelled impact" line back into
   the session or the PR.

## Follow-up work

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-28

**Notes:**

Harms is read as an advantage's impact, by one rule, as ruled on 2026-10-27 (Q1 (A), Q2 yes).
1. **ac1 passes.** The first session's counts stand unchanged. The after-build run over the same
   reading matches the what-if exactly: one advantage moves (Costs: 2, 2, 2 becomes 3, 2, 2, its old
   rank 4 up to rank 1), 753 becomes 751 of 1,164, link-chain rows go from 96 to 95, and "Harms" leaves
   report.md except for the one header line. Every DA row is byte for byte the same, and the lead-in
   changes the ruling asked to count are none. The store's SHA-256 was the same before and after.
2. **ac2 passes.**
   * Red: 28 failed against the unchanged code, each on the behaviour asked for (the one
     `StopIteration` is the row the fold adds, not yet there). Green: 1,153 passed.
   * Nine mutants, the PM's three among them, all caught. The card-above mutant is caught by one
     test, which is that case's own test; that is enough.
   * The fixture covers the three cases asked for: only harms, both, and a DA untouched. t28's
     withholding holds on the row the fold adds.
3. **Decisions accepted:**
   * harms is read only where the Harms role read it (a sub-heading below the placing heading, not an
     answer, naming no other role), pinned by three tests;
   * scenario words beside a harms label are read for an advantage only. `Dome harms impact` now names
     `dome` where it named nothing; no shown name changes on hspolicy26;
   * the header names `harms` once, to say why those cards are under Impact;
   * both kinds read impact cards from roles, a DA's being t10's exactly;
   * the guide's tournament-words sentence corrected in its own commit (`91a2129`), following t28's
     ruling.
4. **`ChainRole.HARMS` removed.** Nothing persists it, as the counts showed.
5. **The affected set** (216 of 553 files, through the domain and application modules) is left to the
   PR's `ci`. The touched suites, the always-run list and the checks pass.
6. **Merge timing:** after Thursday 2026-10-29's tag has a green validate-dev run, with the other held
   PRs, after `v1-e01-t42`. It is not part of Thursday's image.
7. **The republish:** not today (Wednesday 2026-10-28, the cloud run's day; the block refuses anyway).
   `v1-e32-t28`'s republish has not run either, and this task's block is t28's, so one republish after
   this task merges carries both. Paste t28's pilot lines with this task's: the Costs advantage's Teams
   column, its chain's Impact row, and the "no labelled impact" line.
