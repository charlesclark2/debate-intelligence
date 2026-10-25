# Session report: v1-e32-t14-scenarios-and-link-chains

| | |
|---|---|
| Task | `v1-e32-t14-scenarios-and-link-chains` — Each DA's and advantage's scenarios and link chain, and what each impact card runs through |
| Spec | [`plan_specs/v1/e32-argument-landscape/t14-scenarios-and-link-chains.yaml`](../../plan_specs/v1/e32-argument-landscape/t14-scenarios-and-link-chains.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t14-scenarios-and-link-chains` |
| Session status | IN PROGRESS: counts sent, waiting for the PM's ruling <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Counts first (ac1). Nothing is built yet.** The counts are below, read-only, over hspolicy26
through 2026-10-20 under taxonomy 1.2.0. The proposed role labels and the scenario-naming options
are in [the question block](#questions-for-the-pm).

**What the counts say:**

* **DAs carry structure; advantages almost none.**
  * Of 662 DA documents, 302 (45.6%) label a chain role under the DA's heading.
  * Of 1,164 advantage documents, 76 (6.5%) do. In 19,596 of 21,157 counted advantage cards, the
    heading that places the card is the deepest one, so nothing sits below it.
* **Numbered scenario headings barely exist.** `Scenario 1` or `Sc 2` appears in 0 DA documents and
  6 advantage documents.
* **A DA's scenario is mostly in the words beside its impact label** (`Dome impact`,
  `Terrorism impact`). That covers 359 of 959 DA impact cards, against 11 under a scenario heading.
* **A labelled internal link above an impact card is rare.**
  * The card directly above, in the same block, carries an internal-link label for 2 of 959 DA
    impact cards. IL cards sit in their own block, so the card above is usually another impact.
  * Searching every block under the same position heading finds one for 75 of the 959 DA impact
    cards and 2 of the 598 advantage impact cards.
* **In the rows the report would show** (t10's top three, 87 rows over 31 positions):
  * 23 of 44 DA rows and 5 of 43 advantage rows get a scenario under option (a);
  * 7 DA rows and 0 advantage rows get a labelled internal link.
* **ac3's line today:** 328 of 662 DA documents (49.5%) and 1,005 of 1,164 advantage documents
  (86.3%) carry no scenario heading and no role label.

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

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| scenarios-and-chains | In progress | Counts taken and sent (ac1). Waiting for the PM's ruling before the goldens, the rule and the build |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before any rule, per DA and advantage, of documents with scenario headings, chain-role labels or neither, and of t10's impact cards under a scenario heading or below another card, sent to the PM with the proposed role labels and scenario-naming options | PASS (sent; awaiting the ruling) | [The counts on the real store](#the-counts-on-the-real-store) and [the question block](#questions-for-the-pm) |
| ac2: after the ruling, goldens, the never-fills-a-role rules, tests shown failing first | NOT RUN | Waits for the ruling |
| ac3: the report states, per kind, how many documents carry no scenario heading and no role label | NOT RUN | Waits for the ruling. Today's values: DA 328 of 662, advantage 1,005 of 1,164 |
| scenarios-and-chains: `uv run pytest packages/debate_core/tests/application/test_landscape_report.py` | NOT RUN | Waits for the build |

## Files changed

* This report only, so far.

## Deviations from the spec

None yet. Question 5 asks for the one scope amendment the build would need.

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

## Operator follow-ups

None yet.

## Follow-up work

* **v3 E21's chain completeness** is the long-term version, in the debate tub. Nothing here builds
  toward it, as briefed.
* **Unlabelled advantage structure** (1,005 of 1,164 documents) is a model-stage question, like
  t10's unlabelled impacts: v1-e32-t07's, not this task's.

## Questions for the PM

Sent 2026-10-25, before anything is built:

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

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
