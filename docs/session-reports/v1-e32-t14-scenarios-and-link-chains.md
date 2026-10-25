# Session report: v1-e32-t14-scenarios-and-link-chains

| | |
|---|---|
| Task | `v1-e32-t14-scenarios-and-link-chains` — Each DA's and advantage's scenarios and link chain, and what each impact card runs through |
| Spec | [`plan_specs/v1/e32-argument-landscape/t14-scenarios-and-link-chains.yaml`](../../plan_specs/v1/e32-argument-landscape/t14-scenarios-and-link-chains.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t14-scenarios-and-link-chains` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Under each DA's and advantage's impact cards, the report now shows what each impact runs through,
and beside them the position's link chain.** The rules are the PM's rulings of 2026-10-25 on the
counts below, recorded as a comment above the spec's acceptance criteria.

* **What a row shows:**
  * its **scenario**, from heading words two or more teams use under the position, withheld when a
    word is a caselist school's, team code's or tournament's;
  * its **labelled internal link**, the nearest card above it under the same position heading that a
    heading or tag labels one;
  * failing that, report.md alone shows the **card above it in the file**, never called an internal
    link and counted apart.
* **The link chain:** each role's most-read card, ranked as t10's ruling 3 ranks impact cards:
  uniqueness, link, internal link and impact, and for advantages harms, inherency and solvency.
* **Per kind,** report.md says how many documents carry no scenario heading and no role label (ac3),
  how many rows show each lead-in, how many names were withheld, and how many positions lack a card
  for each role.
* **impact_cards.csv** gains `scenario` and `internal_link_tag` only. There is no new file and no
  chain row.

**Checks:**
* The hand-written goldens (`78cc4bc`, before any code) matched byte for byte on the first run.
* The rule's tests failed against two opposite skeletons, with no case passing both. The service's
  tests failed against a skeleton that fills nothing; one passed only vacuously and was tightened.
* All 20 mutants were caught, the nine aimed at the PM's cases among them.

**On hspolicy26 the build reproduces the ruled counts** (read-only, 53.7 s, no worker pool, store
unchanged):
* 44 DA and 43 advantage rows;
* labelled internal links on 7 and 0 of them;
* the card above on 11 and 30;
* the same names used by two or more teams, and the same 4 withheld.

Three figures differ from what was sent, each traced to a ruled rule, not a defect:
* **rows with a scenario,** DA 13 and advantage 0 (sent: 23 and 5): the two-team threshold and one
  withheld name;
* **advantage positions with a link card,** 8 (sent: 9): the ruled `link turn` exclusion applies to
  tags;
* **ac3,** DA 251 of 662 and advantage 676 of 1,164 (sent: 328 and 1,005): ruling 1 makes tag
  openings and t10's impact label role labels.

The Goal is `Succeeded`: every criterion passed.

**The PM's rulings after the build (2026-10-25):** ac3 stays as built, (a), with the sent counts
on the record beside the built ones. Deviation 1 is kept: `no link`, `no impact`, `lt` and `l t`
stay in the not-a-scenario list. Both are under [the rulings after the
build](#the-pms-rulings-after-the-build).

**The sync:** `scripts/task sync` rebased the branch onto `e39bbed`, after v1-e32-t15 and v1-e32-t18
merged. Five files conflicted: the domain module and the service (both `landscape_report.py`),
`render.py`, a test docstring and the guide. Each kept both sides. All 819 landscape tests pass
after it, goldens included.

## The counts on the real store

**How they were taken.** Read-only, counts only, hspolicy26 through 2026-10-20, taxonomy 1.2.0 with
the coach's overrides, as `landscape report` stands on `dev`.

* **Guards.** The script stopped if any `DEBATE_*` variable was set or a `caselist pull` was
  running. Neither was.
* **Time limit and pools.** The interpreter ran under `perl -e 'alarm 115'`. This count needs no raw
  re-read, so no worker pool was started: it reads the stored cards only. The script asserted
  `multiprocessing.active_children()` empty before exiting.
* **Runtime:** the store read and classification took 79.4 s at load average 7.5 on 11 cores. Each
  counting pass over its scratch output took a few seconds.
* **It wrote nothing.** All 15 files under `landscape/` and `reports/` in the data directory had the
  same SHA-256 after the run as before. That covers the classification cache, the plan-text and
  analytic-text caches, the review queue and the operator's bundles.
* **The scripts** are scratch files outside the repository. Their scratch output holds normalized
  headings, tag words and hashed team identities, never card text, and stays on this machine.
* **Every printed line was screened.**
  * First by the report's scan before sharing (`scan_report` over the reading's disclosures).
  * Then by a stricter screen: a line goes when it holds any word of four letters or more from a
    caselist school or tournament, or any team code.
  * 4 scenario-name lines were withheld, and nothing here comes from them.
* **Coverage matches t10's to the card.** 3,825 sources and 126,681 cards were read. Of them, 30,558
  are counted under a DA or advantage: 9,401 DA cards and 21,157 advantage cards, as in t10.

**What is counted.** Following the PM's brief and t10's rule:

* **The cards:** those placed under a DA or advantage, READS, at or above the review threshold, in
  a round on the position's own side.
* **A document** is a file holding at least one such card for the position.
* **The headings** are each card's own `section_path`, cut as `heading_path` cuts it (open tag
  dropped, three levels). Each is normalized by t01's normalizer, with the disclosing team's names
  and the caselist's schools taken out, exactly as the matcher reads it.
* **A sub-heading** is a heading below the one that placed the card. That is the matcher's nearest
  alias or override, recomputed from the same headings.
  * A sub-heading can never be an alias: an alias below would have placed the card itself.
  * A heading the coach ruled names no position still labels a role. The coach ruled `impact`,
    `link`, `solvency`, `u`, `uniqueness` and `uq` name none, and those are the bare role headings.
    Such a heading never names a scenario.
* **The impact cards** are t10's, by t10's rule (`is_impact_card`), unchanged. No second list was
  written.

### Where the structure sits

| | DA | Advantage |
|---|---|---|
| Counted cards | 9,401 | 21,157 |
| Of them, with a sub-heading under the position's heading | 6,416 (68.2%) | 1,561 (7.4%) |
| Most common shape | `DA > block` (4,599), `1NC > DA > block` (1,800) | the advantage is the deepest heading (19,596) |
| Placed by a position heading nested under another DA's or advantage's heading | 194 cards (84 documents) | 48 cards (27 documents) |

The last row is where a scenario that is itself an alias would show. `Pandemics` under the Disease
advantage places the card under the Pandemics advantage instead, and the scenario is lost. For
advantages that is 48 cards in 27 documents. Of the 194 DA cards, 182 sit under a heading that is an
advantage's alias.

### Role labels, by documents

A sub-heading carries a role label when it holds the label's words (the proposed list is in question
1); `u` and `l` count only as a heading's first word. Tags were counted apart, by their opening after
t10's enumerator. A tag opening `u` is not a uniqueness label: of 106 counted cards whose tag opens
`u`, 105 open `U.S.`.

| Label (documents whose sub-heading holds it; tag opens) | DA documents: heading / tag | Advantage documents: heading / tag |
|---|---|---|
| `u` (first word, not `u s`), `uq`, `uniqueness` | 146, 88, 35 / tag `uniqueness` 16 | 19, 8, 1 / 0 |
| `link`, `links`, `l` (first word) | 226, 3, 33 / tag `link` 32, `the link` 15 | 16, 0, 1 / tag `link` 4, `the link` 3 |
| not a link: `link turn`, `link turns`, `no link`, `link defense`, `lt`, `l t` | 8, 4, 2, 0, 3, 4 | 5, 0, 1, 3, 0, 4 |
| `internal`, `internal link(s)`, `il`, `i l` | 81, 8, 12, 20 / tag `i l` 2 | 3, 1, 0, 1 / 0 |
| impact (t10's heading rule) | 185 | 26 |
| `harms`, `harm`; `inherency`; `solvency` (advantages only) | | 1, 2; 4; 22 / tag `solvency` 3 |
| A heading holding two roles' labels | 0 | 0 |
| An answer sub-heading (`AT: No Link`, the team's own frontline) | 141 | 57 |

Under the proposed rule, 302 DA documents carry a role label: uniqueness 246, link 246, internal link
110, impact 185. 76 advantage documents do: uniqueness 26, link 10, internal link 4, impact 26, harms
3, inherency 4, solvency 22. A sub-heading is the only place counted here: t10's 187 DA documents
with an impact heading count one anywhere on the path.

### Scenario headings, by documents

* **Numbered:** `scenario`, `scen`, `sc`, `advantage` or `adv`, then a number, as the first words.
  0 DA documents and 6 advantage documents (Economy 3, Access 2, Data 1). Tags opening `scenario`: 0 DA
  documents and 7 advantage documents; `scenarios`: 0 and 12.
* **Named, the spec's definition** ("broad"): any other sub-heading that is neither an alias nor a
  role label. 200 DA documents and 161 advantage documents.
* **Named, proposed** ("narrow"): the broad set less answer sub-headings and the structure words in
  question 2. 136 DA documents and 108 advantage documents.

**What the broad set holds besides scenarios:**
* overviews (`o v`, `overview`, `ov`, t11's);
* `kick`, and numbered speech answers (`2ac1`, `1nc3`);
* `turns case` abbreviated (`t c costs`, `tc disease`), `defense`, `extra`;
* under advantages, the aff's answers filed without a marker: `cap k ...`, `dedev`, `clog`,
  `court curbing`, `isolationism`.

The narrow set drops all of those except answers with no marker and no kind word, such as
`too early`, `trump steals` and `other issues` under Midterms.

### Per DA and advantage, by documents

`Scenario heading` is numbered or named (narrow); `Scenario (broad)` is numbered or named by the
spec's definition. Both are distinct documents. `Role label` is any role label. `Neither (broad)`
uses the broad scenario column.

| DA | Documents | Scenario heading | Scenario (broad) | Role label (U / L / IL / I) | Both | Neither | Neither (broad) |
|---|---|---|---|---|---|---|---|
| Midterms DA | 418 | 91 | 136 | 191 (147 / 143 / 71 / 110) | 63 | 199 | 188 |
| Economy DA | 89 | 10 | 22 | 45 (40 / 43 / 11 / 19) | 9 | 43 | 43 |
| Pharma DA | 74 | 9 | 15 | 28 (21 / 21 / 10 / 19) | 5 | 42 | 39 |
| Democracy DA | 62 | 1 | 1 | 0 | 0 | 61 | 61 |
| Stocks DA | 53 | 4 | 4 | 21 (13 / 17 / 2 / 9) | 4 | 32 | 32 |
| Debt DA | 49 | 2 | 2 | 0 | 0 | 47 | 47 |
| Federalism DA | 44 | 4 | 5 | 3 (3 / 2 / 2 / 0) | 1 | 38 | 38 |
| Rates DA | 44 | 1 | 9 | 23 (19 / 20 / 10 / 13) | 1 | 21 | 21 |
| AI DA | 28 | 0 | 0 | 0 | 0 | 28 | 28 |
| IRS DA | 28 | 3 | 7 | 21 (20 / 16 / 8 / 16) | 3 | 7 | 6 |
| HHS DA | 20 | 4 | 6 | 8 (3 / 6 / 0 / 6) | 3 | 11 | 9 |
| Capital flight DA | 19 | 3 | 3 | 7 (4 / 5 / 6 / 7) | 2 | 11 | 11 |
| Unions DA | 19 | 1 | 3 | 1 (1 / 0 / 0 / 0) | 0 | 17 | 16 |
| Court clog DA | 17 | 3 | 8 | 7 (4 / 5 / 1 / 6) | 1 | 8 | 4 |
| Medical devices DA | 13 | 5 | 6 | 9 (8 / 7 / 2 / 7) | 3 | 2 | 2 |
| Taxes DA | 11 | 1 | 2 | 10 (8 / 10 / 0 / 5) | 1 | 1 | 1 |
| Permitting reform DA | 10 | 3 | 3 | 4 (3 / 2 / 0 / 4) | 2 | 5 | 5 |
| Innovation DA | 9 | 2 | 2 | 0 | 0 | 7 | 7 |
| Politics DA | 6 | 0 | 1 | 0 | 0 | 6 | 5 |
| Doctors DA | 3 | 0 | 1 | 1 (1 / 0 / 0 / 0) | 0 | 2 | 1 |
| **Distinct documents** | **662** | **136** | **200** | **302 (246 / 246 / 110 / 185)** | **104** | **328 (49.5%)** | **318 (48.0%)** |

| Advantage | Documents | Scenario heading | Scenario (broad) | Role label (U / L / IL / I / H / Inh / S) | Both | Neither | Neither (broad) |
|---|---|---|---|---|---|---|---|
| Costs | 394 | 29 | 36 | 16 (7 / 1 / 0 / 2 / 3 / 3 / 3) | 7 | 356 | 350 |
| Disease | 241 | 7 | 23 | 0 | 0 | 234 | 218 |
| Economy | 225 | 25 | 29 | 16 (6 / 2 / 1 / 4 / 0 / 0 / 7) | 8 | 192 | 190 |
| Inequality | 220 | 3 | 7 | 3 (0 / 0 / 0 / 3 / 0 / 0 / 0) | 0 | 214 | 210 |
| Coverage | 217 | 11 | 21 | 5 (1 / 1 / 0 / 2 / 0 / 1 / 3) | 3 | 204 | 195 |
| Growth | 184 | 17 | 21 | 11 (6 / 1 / 0 / 1 / 0 / 0 / 5) | 4 | 160 | 157 |
| Access | 109 | 5 | 5 | 3 (0 / 0 / 0 / 0 / 0 / 0 / 3) | 1 | 102 | 102 |
| Budgets | 103 | 0 | 0 | 2 (0 / 0 / 0 / 2 / 0 / 0 / 0) | 0 | 101 | 101 |
| Stagnation | 93 | 7 | 24 | 9 (1 / 3 / 2 / 7 / 0 / 0 / 1) | 2 | 79 | 67 |
| Bioterror | 86 | 4 | 4 | 1 (0 / 0 / 0 / 1 / 0 / 0 / 0) | 1 | 82 | 82 |
| Innovation | 71 | 2 | 6 | 8 (6 / 1 / 1 / 0 / 0 / 0 / 0) | 1 | 62 | 61 |
| Pandemics | 51 | 1 | 1 | 0 | 0 | 50 | 50 |
| Data | 42 | 5 | 12 | 2 (0 / 1 / 0 / 1 / 0 / 0 / 0) | 0 | 35 | 29 |
| Sustainability | 29 | 0 | 0 | 0 | 0 | 29 | 29 |
| Pharma | 15 | 1 | 4 | 4 (0 / 0 / 0 / 3 / 0 / 0 / 1) | 1 | 11 | 8 |
| Biotech | 12 | 3 | 3 | 0 | 0 | 9 | 9 |
| **Distinct documents** | **1,164** | **113** | **166** | **76 (26 / 10 / 4 / 26 / 3 / 4 / 22)** | **30** | **1,005 (86.3%)** | **965 (82.9%)** |

No DA document has a numbered scenario heading. Among advantages, the numbered ones are Economy 3,
Access 2 and Data 1. Data's one is in a document that also has a named one.

### t10's impact cards

| | DA (959 impact cards) | Advantage (598) |
|---|---|---|
| Under a scenario heading, numbered or named (narrow) | 11 | 12 |
| Under a named sub-heading, the spec's definition (broad) | 19 | 26 |
| Under an impact or internal-link heading with other words (`dome impact`, `impact iran`) | 359 | 29 |
| A scenario from either | **370 (38.6%)** | **41 (6.9%)** |
| A card directly above it in the same block | 548 | 554 |
| The first card of its block | 411 | 44 |
| Nearest card above under the same position heading, any block, labelled internal link | 75 (73 by heading, 2 by tag) | 2 (by heading) |

**What the card directly above in the same block carries:**

| The card above | DA (548) | Advantage (554) |
|---|---|---|
| An impact card by the block's shared heading (an `Impact` block) | 412 | 45 |
| An impact card by its own tag | 45 | 8 |
| Its tag opens with an internal-link word | 2 | 0 |
| Its tag opens with a link word | 2 | 0 |
| No label | 87 | 501 |

In one block every card shares the headings, so only the tag tells the card above apart. For DAs,
the internal link is its own block above the impact block. For advantages, the card above is
unlabelled in 501 of 554 cases. In a 1AC it is usually the internal link, but no heading or label
says so.

### What the report would show

These are t10's top three impact rows, per DA and advantage, as ranked today: 44 DA rows over 16 DAs
and 43 advantage rows over 15 advantages. A row gets a value when one of its labelled copies has one.

| A row gets | DA rows | Advantage rows |
|---|---|---|
| A scenario from a scenario heading alone | 3 | 3 |
| A scenario from a heading or the words beside an impact/IL label (option a) | **23 of 44** | **5 of 43** |
| A labelled internal-link card above, under the same position heading | **7 of 44** | **0 of 43** |
| An unlabelled card directly above that is not an impact card (question 3's alternative) | 11 | 30 |

**A most-read card per chain role** means a cluster with at least one labelled copy counted for the
position, by heading or tag. The counts give the positions that would have one, and the median
number of teams reading the top cluster:

| Role | DAs (of 20) | Advantages (of 16) |
|---|---|---|
| Uniqueness | 15 (median 2 teams) | 6 (1) |
| Link | 13 (3) | 9 (1) |
| Internal link | 10 (2) | 3 (1) |
| Impact (t10's top impact card) | 16 (3) | 15 (3) |
| Harms / inherency / solvency | | 1 / 2 / 7 (1 each) |

By heading alone, link drops to 7 advantages, and impact to 12 DAs and 10 advantages.

### Scenario names, grouped by normalized words, with teams

A name is a numbered heading's words after `scenario N (is)`, a narrow named sub-heading, or the
words beside an impact or IL label. Shown when two or more teams use it, which is option (a)'s
threshold; the screened lines are left out.

| Position | Distinct names | Used by 2+ teams | The 2+ names, teams (documents) |
|---|---|---|---|
| Midterms DA | 128 | 16 | `dome` 15 (32), `golden dome` 5 (7), `dems win` 3 (4), `iran` 3 (4), `polycrisis` 3 (8), `china coop` 2 (7), `corruption` 2 (3), `dem win crushes trumpism` 2 (5), `democracy` 2 (2), `dome arms racing` 2 (2), `other issues` 2 (2), `too early` 2 (2), `trump steals` 2 (3), `warming` 2 (2); 2 withheld by the screen |
| IRS DA | 7 | 1 | `terrorism` 7 (14) |
| Medical devices DA | 5 | 2 | `augmentation` 4 (5), `augmentation innovation key` 2 (3) |
| Pharma DA | 22 | 2 | `china` 3 (4), `biotech` 2 (3) |
| Economy DA | 19 | 2 | `decline` 2 (8), `econ` 2 (3) |
| Capital flight DA | 6 | 1 | `dollar` 2 (3) |
| Court clog DA | 8 | 1 | `emerging tech` 2 (3) |
| Economy advantage | 24 | 3 | `costs rising` 4 (7), `contention the advantage` 3 (4), `debt` 3 (3) |
| Disease advantage | 9 | 3 | `clog` 2 (2), `court curbing` 2 (2); 1 withheld |
| Costs advantage | 32 | 2 | `dedev` 2 (2), `isolationism` 2 (2) |
| Inequality advantage | 7 | 1 | `inequality` 2 (2) |
| Stagnation advantage | 11 | 1 | 1 withheld |
| The other 13 DAs and 11 advantages | 0 to 24 each | 0 | |

Under DAs the 2+ names are mostly scenarios, with two caveats: `dome` and `golden dome` are one
scenario named two ways, and `too early`, `trump steals` and `other issues` are answers without a
marker. Under advantages most are the aff's answers to DAs and Ks (`clog`, `dedev`), not scenarios.

## The build on the real store

**How it ran.** Read-only, hspolicy26 through 2026-10-20, taxonomy 1.2.0, the build as committed
(`2ea5c6a`, before the sync, which changed no rule or service line).
* **Guards:** no `DEBATE_*` variable was set and no `caselist pull` was running; the script checks
  both and stops otherwise.
* **Time limit:** `perl -e 'alarm 115'` on the interpreter.
* **How:** `landscape_cards` and `LandscapeReportService.bundle` over t10's read-only inputs
  (Deviation 2). No pool, and `multiprocessing.active_children()` was empty at the end.
* **Runtime:** 53.7 s at load average 6.5.
* **It wrote nothing:** all 15 files under `landscape/` and `reports/` had the same SHA-256 after it.
* **Coverage as t10's:** 63,494 of 126,681 cards; impact coverage advantage 411 of 1,164, DA 296 of
  662.
* **Printing:** counts, and the scenario names, each line screened as before.

| Count | Sent with the counts | The build | Why they differ |
|---|---|---|---|
| Impact rows, DA / advantage | 44 / 43 | 44 / 43 | |
| Rows with a labelled internal link | 7 / 0 | 7 / 0 | |
| Rows showing the card above it in the file | 11 / 30 | 11 / 30 | |
| Rows with a scenario | 23 / 5 | **13 / 0** | The sent figure had no threshold. Two teams leave 13 / 1, and the advantage's one is withheld |
| Scenario names withheld | 4 lines | 2 / 2 | |
| Names used by two or more teams | | identical to [the counts' list](#scenario-names-grouped-by-normalized-words-with-teams) | |
| DA positions (of 20) with a card for uniqueness, link, IL, impact | 15, 13, 10, 16 | 15, 13, 10, 16 | |
| Advantage positions (of 16): uniqueness, link, IL, impact, harms, inherency, solvency | 6, 9, 3, 15, 1, 2, 7 | 6, **8**, 3, 15, 1, 2, 7 | The Pandemics advantage's only link-like tag opens `link turn`, which the ruled exclusions keep out of tags too |
| ac3: documents with no scenario heading and no role label | 328 / 1,005 | **251 / 676** | Ruling 1 counts tag openings and t10's impact card as labels; the PM kept it, (a), on 2026-10-25 |
| The scan before sharing, report.md and impact_cards.csv | | no hit | |

**ac3, step by step.** Each step adds one change, on the same documents.

| Step | DA (of 662) | Advantage (of 1,164) |
|---|---|---|
| As sent: sub-heading labels only, t10's impact heading among them | 328 | 1,005 |
| With Deviation 1's not-a-scenario additions | 328 | 1,005 |
| With ruling 1's tag openings and t10's impact card (the build) | **251** | **676** |

**The coach's seed for option (b)** is the table of names used by two or more teams under [the
counts](#scenario-names-grouped-by-normalized-words-with-teams). The build finds exactly those names,
with the same teams. Midterms DA has 14 shown and 2 withheld. Under the advantages, Disease has 2
shown and 1 withheld, and Stagnation 0 shown and 1 withheld. The names that hold a caselist word stay
counted and unprinted, here as in the report.

## The PM's rulings after the build

Ruled on 2026-10-25, on the second question block.

1. **ac3's measure: (a), as built.** "Neither" counts what the chain and the scenarios could not see:
   no scenario heading, and no label the chain reads, whether a sub-heading's, a tag opening's or
   t10's impact card. On hspolicy26 through 2026-10-20, beside the counts sent before the ruling:

   | Documents with no scenario heading and no role label | Sent with the counts (sub-heading labels only) | Built and ruled |
   |---|---|---|
   | DA, of 662 | 328 | **251** |
   | Advantage, of 1,164 | 1,005 | **676** |

2. **Deviation 1: keep it.** `no link`, `no impact`, `lt` and `l t` stay in the not-a-scenario list.
   They are the role rules' own exclusions, and defense filed under `No impact` must never become a
   scenario name.

Neither ruling changes code, a golden or a count: both confirm what was built. The spec's ruling
comment records them beside the first five.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| scenarios-and-chains | Done | Counts sent (ac1) and ruled on, then, in order:<br>1. the rulings in the spec (`48ddfe1`);<br>2. the fixture's headings, the domain values and the goldens by hand (`78cc4bc`);<br>3. the rule's tests, red against two skeletons, then the rule;<br>4. the service and renderer, then the service tests, red against a skeleton (`d587d99`, `28aef3a`, `9615025`);<br>5. 20 mutants;<br>6. a read-only re-count with the build;<br>7. the coach's guide (`70f4208`);<br>8. the sync |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, per DA and advantage, of documents with scenario headings, chain-role labels or neither, and of t10's impact cards under a scenario heading or below another card, sent to the PM with the proposed role labels and scenario-naming options | PASS | [The counts on the real store](#the-counts-on-the-real-store) and the first question block. The PM ruled on 2026-10-25: role labels (a); scenario names (c), building (a) now; the internal link (a) plus the card-above line; the chain as proposed; scope yes |
| ac2: after the ruling, on the synthetic fixture, report.md shows under each impact card its scenario and its internal link's tag, and per DA and advantage its most-read card per chain role, matching hand-written golden files; an ANSWERS card or a card on the other side never fills a role; a role or scenario no heading or label gives is counted, not guessed; tests shown failing first | PASS | `test_rendering_the_fixture_matches_the_golden_file[report.md]` and `[impact_cards.csv]` pass against goldens committed in `78cc4bc` before any rule or service code. ANSWERS: `test_chain_an_answers_card_never_fills_a_role` (a3's cluster 36 fills the IL once made READS) and `test_lead_in_an_answers_card_is_never_the_internal_link`. Other side: `test_chain_a_card_in_a_round_on_the_other_side_never_fills_a_role` (a6's cluster 45, once its round has no side). Counted, not guessed: `test_coverage_counts_what_no_heading_or_label_gives_per_kind` and every "no labelled card" and "no labelled internal link" line of the golden. Red runs [below](#checks-shown-failing-for-their-reason) |
| ac3: the report states, per kind, how many documents carry no scenario heading and no role label | PASS | report.md: "Advantage documents with no scenario heading and no role label: 1 of 6 (16.7%)." and "DA documents with no scenario heading and no role label: 2 of 6 (33.3%)." On hspolicy26: DA 251 of 662 and advantage 676 of 1,164, as built and ruled (a) on 2026-10-25; the sent counts were 328 and 1,005 |
| scenarios-and-chains: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | PASS | Run as `.venv/bin/python -m pytest …` under a 110 s alarm, with the landscape tests: **819 passed in 3.23s** after the sync (`test_landscape_report.py` alone: 80 before the sync) |

### Checks shown failing for their reason

* **The goldens against today's code**, before any t14 code (`76847fd`, before the sync): **12
  failed, 85 passed**.
  * Failing: `report.md`, `impact_cards.csv` and t10's coverage-line test.
  * Also failing: nine hand counts of t03 and t10, which the eleven new fixture cards shift. I
    re-counted them by hand from the fixture table (cards 45 → 56, placed 34 → 45, the other-side
    rounds 1 → 2, Costs and Spending top cards, the impact rows and coverage). After that only
    t14's three failed.
  * `top_cards.csv`, `positions.csv`, `trends.csv` and `schools.csv` passed on that run. Their hand
    edits (new top-card rows, coverage `45/56`) agree with t03's existing code, which is a check on
    those edits.
* **The rule, `test_link_chains.py`** (137 cases):
  * against a skeleton that labels nothing: **62 failed, 75 passed**;
  * against one that labels and withholds everything: **122 failed, 15 passed**;
  * no case passes under both (`comm -12` of the two pass lists is empty);
  * the real rule: 137 passed, with t10's 80 `test_impacts.py` cases unchanged after `tag_opening`
    was factored out.
* **The service:** a scratch pytest plugin replaced `_LinkChains` with one that fills nothing (no
  source edit). **14 failed, 98 passed.** Two of this task's tests passed under it:
  * `test_lead_in_the_card_above_is_never_an_impact_card_or_in_another_block` guards the other
    direction, and the card-above mutants catch it;
  * `test_chain_the_impact_role_is_the_impact_sections_first_row` passed vacuously, looping over no
    chain cards. It now names the three positions first: red under the skeleton (1 failed), green on
    the build (`28aef3a`).
* **20 mutants, all caught.**
  * Each ran in a fresh process with bytecode writing off and `__pycache__` cleared, and each file
    was restored and checked by SHA-256.
  * The test files were `test_link_chains.py`, `test_impacts.py`, `test_landscape_report.py` and
    `test_render.py` (329 tests, 330 with the card-above test).
  * No Hypothesis is used, so working agreement 8's database rule does not arise.
  * The runs were on `2ea5c6a`, before the sync, which rewrote no rule or service line.
  * "t14 tests" counts this task's tests and the two goldens that hold its sections.

  | Mutant | Failed | Of them, t14 tests |
  |---|---|---|
  | Role: a `u` in a tag labels uniqueness (the PM's) | 6 | 6 |
  | Role: `no link` labels a link (the PM's) | 5 | 5 |
  | Role: an answer sub-heading fills a role (the PM's) | 5 | 5 |
  | Role: a heading holding two roles fills both | 2 | 2 (the rule's unit tests; no fixture heading holds two) |
  | Role: `u s` (U.S.) labels uniqueness in a heading | 2 | 2 (unit tests) |
  | Role: harms, inherency and solvency label a DA's cards | 7 | 7 |
  | Threshold: one team shows a name (the PM's) | 4 | 4 |
  | Threshold: three teams are needed | 5 | 5 |
  | Withheld: no name is withheld (the PM's) | 6 | 5 |
  | Withheld: a withheld name is shown, only counted | 5 | 4 |
  | Withheld: team codes are not caselist words | 3 | 3 (unit tests; the fixture's withheld name holds a school word) |
  | Withheld: school and tournament words of any length | 1 | 1 |
  | ANSWERS: an uncounted card above can be the internal link (the PM's) | 4 | 4 |
  | ANSWERS count as reads (shared with t03; the PM's) | 21 | 7 |
  | Other side counts (shared with t03; the PM's) | 22 | 6 |
  | Card above: the line calls itself an internal link (the PM's) | 1, then **2** | 1, then 2 |
  | Card above: it fills `internal_link_tag`, and so the CSV | 4, then 5 | 4 |
  | Card above: shown beside a labelled internal link | 1 | 1 |
  | Card above: an impact card above counts | 1 | 1 |
  | Card above: any card directly above, whatever its block | 3 | 3 |

  The PM's card-above mutant was first caught by the report.md golden alone. I added
  `test_the_card_above_an_impact_is_never_called_its_internal_link` (`9615025`) and re-ran the five
  card-above mutants: 2 and 5 tests now.

## Before the report (working agreement 10)

All of these ran after the sync, on `fddd459`.

* **The affected set is over two minutes.** `uv run scripts/affected_tests.py` chose 196 of 477 files
  (41.1%) from 24 changed files. I ran them as `.venv/bin/python -m pytest -q -n 6 -m "not slow and
  not live" -p no:randomly <files>` under a 115 s alarm, at load average 4.3.
  * The alarm stopped it at 77%. Its progress lines up to then hold 4,248 passes and no failure or
    error.
  * No process outlived it.
  * So it is left to the pull request's `ci`, which runs the whole selection.
* **Within the two minutes, the tests of what changed and the always-run list:**
  * the landscape, analytic-text, plan-text, aff-assignment, classification and file-suggest tests in
    `packages/debate_core/tests/application`, plus `packages/debate_core/tests/arguments/landscape`,
    `packages/debate_core/tests/domain` and `packages/debate_core/tests/integrations/landscape`;
  * the two landscape removal tests in `application/caselist`;
  * `packages/debate_cli/tests/test_landscape_command.py` and `tests/smoke/test_landscape_smoke.py`;
  * `tests/config`, `tests/architecture`, `tests/specs` and `tests/scripts`;
  * result: **3,949 passed in 70.06s**, under a 115 s alarm at load average 9.7.
* **The fixture generator reproduces the committed inputs byte for byte** after the sync (`git
  status` clean after `scripts/make_landscape_fixture.py`).
* `uv run --frozen ruff format --check .` → 1320 files already formatted. `uv run --frozen ruff
  check .` → all checks passed.
* `uv run --frozen pyright`, bare as CI runs it → 0 errors, 0 warnings.
* `uv run --frozen lint-imports` → 16 kept, 0 broken. `scripts/check_thin_handlers.py` → 54 handlers
  within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 451 files. `--require-succeeded
  v1-e32-t14-scenarios-and-link-chains` → Succeeded. The ruling comment parses as a comment: the
  parsed description does not contain it.
* `scripts/check_command_blocks.py --base origin/dev` → no `#` comments, this report included.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.

## Files changed

* **`debate_core.arguments.landscape.link_chains`** (new): the rule.
  * Contents: `heading_roles`, `tag_role`, `card_roles`, `card_scenario`, `caselist_words`,
    `is_withheld`, `NOT_A_LINK` and `NOT_A_SCENARIO`.
  * Its tests are `tests/arguments/landscape/test_link_chains.py` (new, 137).
* **`arguments/landscape/impacts.py`:** `tag_opening`, t10's enumerator-skipping, factored out so both
  rules read a tag's opening alike.
* **`arguments/landscape/matcher.py`:** `PositionMatcher.placing_index`, the index of the heading
  `place` already finds, made public so the report reads sub-headings by the matcher's own rule.
* **`domain/landscape_report.py`:**
  * `LandscapeCard.heading_answers`;
  * `ImpactCard.scenario`, `.internal_link_tag` and `.card_above_tag`;
  * `ChainRole`, `CHAIN_ROLES`, `ChainCard`, `RoleGap` and `ChainCoverage`;
  * `LandscapeReport.chain_cards` and `.chain_coverage`.
* **`application/landscape_report.py`:** `landscape_cards` records each heading's answer flag;
  `_LinkChains` reads roles, scenarios and lead-ins from the counted cards; the docstring's new
  section.
* **`arguments/landscape/render.py`:** `IMPACT_CARD_COLUMNS` gains the two columns, and report.md
  gains the impact table's Scenario column, the lead-in bullets, the chain table, the per-kind lines
  and two "How to read" bullets.
* **Tests:**
  * `test_landscape_report.py`: 17 new tests (chain, lead-in, scenario, coverage, answer flags),
    and the hand counts the fixture's new cards shift, edited by hand;
  * `test_render.py`: the card-above test, the column pin, t10's coverage line, and "report.md lists
    impact and chain cards only".
* **`tests/fixtures/landscape/`:**
  * the inputs: six cards re-headed, eleven added, the taxonomy's aliases, written by
    `scripts/make_landscape_fixture.py`;
  * the README's new section;
  * the goldens, by hand: report.md, impact_cards.csv, top_cards.csv, and every header's coverage.
* **`scripts/make_landscape_fixture.py`:** the cards, `answers` and `ALIASES`, in scope by the PM's
  ruling.
* **`docs/guides/landscape-taxonomy.md`:** a "Scenarios and link chains" section, and a `none`
  decision still labelling a role.
* **The spec:** the rulings as a comment above `acceptanceCriteria`, `scripts` in
  `constraints.packages` with its comment, and the phase.

## Deviations from the spec

1. **Four phrases added to the not-a-scenario list,** kept by the PM's ruling of 2026-10-25:
   `no link`, `no impact`, `lt` and `l t`, beside
   `link defense`, which `defense` already covered.
   * **Why:** ruling 2 took my list as sent. But these phrases are the role rules' own exclusions
     (ruling 1 and t10's). Without them, `no impact` under the Midterms DA would name a scenario
     "no impact" as soon as two teams used it.
   * **On hspolicy26,** 24 DA cards (19 under `lt`, 5 under a heading holding `no impact`) and 1
     advantage card (`no link`) stop counting as under a scenario heading.
     No document's ac3 count moves, since each of those files carries a role label anyway, and the
     list of names two or more teams use is unchanged.
   * In the fixture, `b3`'s `no impact` is the case.
   * **Ruled 2026-10-25: keep them.** They are the role rules' own exclusions, and defense filed
     under `No impact` must never become a scenario name.
2. **The re-count used the report service directly, not the run's dry run.**
   * The dry run reads t09's and t11's caches through a spawned worker pool, re-parsing what they
     lack. That put it near the two-minute line, where an alarm that kills the parent orphans its
     workers.
   * t09's aff assignments and t11's texts touch neither section, so the script fed the built
     `landscape_cards` and `LandscapeReportService.bundle` the same read-only inputs t10's count used.
   * It started no pool.

## Decisions and assumptions

1. **The placing heading** was recomputed from the card's normalized headings with the matcher's own
   rule (nearest alias or override, from the inside out). No counted card lacked one.
2. **Same block** in the counts means the same raw heading path, as `heading_path` cuts it. The build
   would compare the normalized headings the fixture and `LandscapeCard` carry, which can join two
   raw headings that normalize alike (`1NC Link`, `Link`). Both mean the same block.
3. **The card directly above** is the previous card of the same file by first paragraph. A card with
   no first paragraph is left out, as the matcher leaves it out.
4. **A no-position ruling is not a role ruling.** The coach's overrides say a heading places no
   position. They say nothing about its role, so `link`, `u` and the others still label one. My
   first pass skipped them, and every role count came out low (DA 243 documents, not 302). I caught
   it because `solvency` showed in 22 advantage documents and the rule counted 7. Only the corrected
   counts are reported here.
5. **Sub-headings in the build** are found by `PositionMatcher.placing_index` over the card's
   normalized headings (`LandscapeCard.headings`), the same rule the counts recomputed. The fixture's
   taxonomy gained the aliases its headings name so this works there as on the real taxonomy.
6. **The same block** is equal normalized headings and answer flags. **The same position heading**
   is equal headings and flags down to the placing one. The walk for an internal link stops at the
   first card of another position heading, and passes over a card not counted for the position.
7. **A row's scenario, internal link and card above** each come from its labelled copies. Each copy
   adds its teams, and the value with the most teams shows, ties to the first in text order. A copy's
   scenario name counts only if it is shown for the position (two or more teams, not withheld). The
   card above is looked for only when no copy has a labelled internal link.
8. **ac3 counts every role label the chain reads:** a sub-heading's, a tag opening's, and t10's
   impact card. A document has neither when none of its counted cards for a position of the kind is
   under a scenario heading or carries one. Ruled (a), as built, on 2026-10-25.
9. **A withheld name** is one two or more teams use that holds a word of a caselist school or
   tournament of four letters or more, or any team code, from every disclosure the report reads.
   Only names that would otherwise show are counted as withheld.
10. **The chain's impact role** is t10's impact card, whatever else its heading holds, so it is the
    impact section's first row. An answer sub-heading that holds `impact` therefore still makes t10's
    impact card, as t10's rule always did; it fills none of the other six roles.

## Operator follow-ups

1. **The pull request,** from the worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t14-scenarios-and-link-chains
```

```bash
scripts/task pr v1-e32-t14-scenarios-and-link-chains
```

2. **After the merge,** the next `landscape report` run adds the scenario, internal-link, card-above
   and link-chain sections to report.md and the two columns to impact_cards.csv. Republishing is the
   PM's to coordinate. On today's store the scan before sharing found no hit in report.md or
   impact_cards.csv.

## Follow-up work

* **The coach's scenario vocabulary (option b, after Nov 1):**
  * the names below, used by two or more teams, are its seed;
  * a taxonomy version bump under v1-e32-t08's lock, for the PM to file;
  * "dome" and "golden dome" stay apart until the coach merges them.
* **v3 E21's chain completeness** is the long-term version, in the debate tub. Nothing here builds
  toward it, as briefed.
* **Unlabelled structure** is a model-stage question, like t10's unlabelled impacts: v1-e32-t07's,
  not this task's. On hspolicy26 that is 676 of 1,164 advantage documents and 251 of 662 DA
  documents.
* **The source heading normalizer still leaves some school first words in headings** (t10's
  follow-up). Withholding by word catches them in scenario names.

## Questions for the PM

The first block was answered on 2026-10-25 (see the spec's ruling comment). Kept as sent:

```text
v1-e32-t14 questions (session, 2026-10-25): counts first, nothing built

Read-only, hspolicy26 through 2026-10-20, taxonomy 1.2.0 with the coach's
overrides; counts only; guards checked, interpreter under alarm 115, no
pool needed (stored cards only), all 15 landscape/reports files unchanged.
Cards as t10 counts them: under a DA or advantage, READS, threshold, own
side. 662 DA documents (9,401 cards), 1,164 advantage documents (21,157).
Headings: each card's section_path cut as heading_path cuts it, normalized
by t01's normalizer with the team's names and the caselist's schools out.
A sub-heading is one below the heading that placed the card (never an
alias, by construction). Impact cards are t10's, unchanged.

The counts, per kind:
  DA: role label under the DA's heading 302 (45.6%): uniqueness 246,
    link 246, internal link 110, impact 185. Scenario heading 136 (named
    only; numbered "Scenario 1"/"Sc 2": 0). Both 104. Neither 328 (49.5%).
  Advantage: role label 76 (6.5%): uniqueness 26, link 10, IL 4, impact
    26, harms 3, inherency 4, solvency 22. Scenario heading 113 (numbered
    6). Both 30. Neither 1,005 (86.3%). In 19,596 of 21,157 advantage
    cards the advantage is the deepest heading: nothing sits below it.
  With the spec's broad "named" (any non-alias, non-role sub-heading):
    neither DA 318, advantage 965. The broad set is mostly overviews,
    kick, "2ac1", t/c, defense and aff answers ("dedev", "clog").
  t10's impact cards, DA 959 / advantage 598:
    under a scenario heading 11 / 12;
    under an impact or IL heading with other words ("dome impact",
      "impact iran") 359 / 29; either 370 / 41;
    a card directly above in the same block 548 / 554; what it carries:
      an impact (shared Impact heading) 412 / 45, impact by tag 45 / 8,
      IL word in its tag 2 / 0, link word 2 / 0, no label 87 / 501;
    a labelled IL card above anywhere under the same position heading
      75 / 2.
  In t10's top three rows (44 DA rows, 43 advantage rows):
    scenario under option (a) 23 / 5; labelled IL above 7 / 0;
    an unlabelled non-impact card directly above 11 / 30.
  Scenario names used by 2+ teams: Midterms 16 of 128 (dome 15 teams,
    golden dome 5, polycrisis 3, iran 3, china coop 2, ...), IRS
    terrorism 7, Medical devices augmentation 4, Pharma china 3; under
    advantages 0 to 3 per position, mostly aff answers (clog, dedev).
    The full list is in the session report; 4 lines withheld by the scan
    and a stricter school-word screen.

1. Role labels. A sub-heading below the placing heading labels a role when
   it holds, as whole words:
     uniqueness: "uniqueness", "uq", or "u" as its first word (never
       "u s", U.S.);
     link: "link", "links", or "l" as its first word; not "link turn(s)",
       "no link", "link defense", "lt", "l t", nor "internal link";
     internal link: "internal link(s)", "internal", "internals", "il",
       "i l";
     impact: t10's rule as it stands (heading or tag), reused, not
       rewritten;
     advantages only: harms "harms", "harm"; inherency "inherency",
       "inh"; solvency "solvency", "solv".
   A tag opening (after t10's enumerator) also labels: "uniqueness",
   "uq"; "link", "links", "the link"; "internal link", "internal", "il",
   "i l". Never "u" in a tag (105 of 106 such tags are U.S.). An answer
   sub-heading ("AT: No Link") fills no role; a heading holding two roles'
   labels fills neither (0 today). An ANSWERS card or an other-side card
   never fills one (they are not counted at all). A heading the coach
   ruled names no position still labels a role: impact, link, solvency,
   u, uniqueness and uq are all such rulings today.
   (a) As proposed.
   (b) Headings only, no tags.
   Recommendation: (a). Tags add DA links in 32 + 15 documents and are
   how most of the advantages' link labels appear (7 positions by
   heading, 9 with tags).

2. Naming a scenario.
   (a) Normalized heading words, shown only when 2+ teams use them. The
       words are a numbered heading's after "scenario N (is)", a named
       sub-heading's, or those beside an impact or IL label ("Dome
       impact" -> dome). Not a scenario: answer sub-headings, the coach's
       no-position headings, and sub-headings holding overview, ov, o v,
       kick, extra(s), defense, turn(s), framing, solves case, t c, tc,
       new, or a kind word (da, disad, cp, counterplan, k, kritik, t,
       theory), or a numbered speech answer (2ac1, 1nc3). A row shows the
       name most of its labelled copies' teams use; none otherwise,
       counted. 23 of 44 DA rows, 5 of 43 advantage rows get one.
       No coach time. Costs: "dome" and "golden dome" stay apart, and
       answers without a marker ("too early", "trump steals") show.
   (b) A coach-edited scenario vocabulary per position in the taxonomy
       (names and their heading forms, as t09's mechanisms), 1.3.0 under
       t08's released-ids lock. Merges dome/golden dome, drops the noise.
       About 45 names to read today. Needs coach time before Nov 1.
   (c) (a) now, and (a)'s 2+ team list handed to the coach after Nov 1 as
       the seed of (b), the way t01 seeded aliases.
   Recommendation: (c), which is (a) for Nov 1. It needs no coach time,
   and its list is exactly what (b) would start from. Either way, a name
   holding any word of a caselist school, team code or tournament is
   withheld and counted (report.md shows heading words for the first
   time; t10 found the normalizer misses some school first words), and
   the scan before sharing still runs.

3. The internal link under an impact card.
   (a) Labelled only: the nearest card above it under the same position
       heading in its file whose heading or tag labels it internal link;
       its tag as parsed, the most common across the row's copies by
       teams; "no labelled internal link" otherwise, counted. 7 of 44 DA
       rows, 0 of 43 advantage rows.
   (b) Also the unlabelled card directly above in the same block when it
       is not itself an impact card, shown as "card above", never called
       an internal link. 11 DA rows, 30 advantage rows.
   Recommendation: (a). "Never guessed" covers position as well as
   wording, and (b) assumes the card above is the link. The report says
   how many rows have none, so the gap is visible to the coach.

4. The link chain per DA and advantage: its most-read card per role,
   clusters ranked by distinct teams of their labelled copies (t10's
   ruling 3, card by card), tag and cite as top cards show them; "no
   labelled card" otherwise, counted. Impact is t10's rank-1 row.
   Positions with a card: DA (of 20) uniqueness 15, link 13, IL 10,
   impact 16; advantage (of 16) uniqueness 6, link 9, IL 3, impact 15,
   harms 1, inherency 2, solvency 7. Most top clusters are read by 1 to
   3 teams.
   Where: report.md under each position, beside its impact block; in
   impact_cards.csv only the new columns scenario and internal_link_tag
   (no chain rows, no new file). Agree?
   Recommendation: yes. A chain row in the CSV would change what an
   impact_cards.csv row means.

5. Scope. The fixture's cards need scenario and role headings, and
   scripts/make_landscape_fixture.py is its only writer (t10's Deviation
   1, ruled yes for t10). Amend constraints.packages with scripts
   (that file only)? Nothing else outside it is needed: the CLI and smoke
   tests pin the bundle's file names, not impact_cards.csv's columns.
   Recommendation: yes.
```

Second block, after the build (2026-10-25), answered the same day: (1) (a), (2) yes. Kept as sent:

```text
v1-e32-t14 questions after the build (session, 2026-10-25)

Built as ruled: hand-written goldens matched byte for byte on the first run;
the rule's tests red against two opposite skeletons, the service's against a
fill-nothing one; 20 mutants caught (the nine on the PM's cases among them). A read-only
re-count on hspolicy26 with the build (53.7 s, no pool, store unchanged)
matches the ruled counts: 44 / 43 rows, labelled IL 7 / 0, card above
11 / 30, the same names used by 2+ teams, the same 4 withheld, no scan hit.
Rows with a scenario are 13 / 0 (sent 23 / 5, before the two-team threshold
and withholding). Goal Succeeded. Synced onto dev after t15 and t18; both
sides kept; 819 landscape tests pass.

1. ac3's measure. A document has neither when none of its counted cards is
   under a scenario heading or carries a role label, a label being what the
   chain reads: a sub-heading's, a tag opening's (ruling 1), or t10's impact
   card. On hspolicy26: DA 251 of 662, advantage 676 of 1,164. The counts I
   sent used sub-heading labels only: 328 and 1,005.
   (a) As built: every label the chain reads.
   (b) Sub-heading labels only, as sent.
   Recommendation: (a). The line then says exactly what the chain and the
   scenarios could not see, as t10's ac3 line does for impacts; under (b),
   an advantage whose impact the report lists by its tag would still count
   as carrying no label.

2. Deviation 1. I added `no link`, `no impact`, `lt` and `l t` to the
   not-a-scenario list; they are the role rules' own exclusions. On
   hspolicy26 it moves 25 cards and no document or shown name. Keep them?
   Recommendation: yes. Without them, "no impact" names a scenario as soon
   as two teams file defense under it.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
