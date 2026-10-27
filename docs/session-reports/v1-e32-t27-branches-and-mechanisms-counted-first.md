# Session report: v1-e32-t27-branches-and-mechanisms-counted-first

| | |
|---|---|
| Task | `v1-e32-t27-branches-and-mechanisms-counted-first` — Branches and mechanisms in the DA sections, counted first |
| Spec | [`plan_specs/v1/e32-argument-landscape/t27-branches-and-mechanisms-counted-first.yaml`](../../plan_specs/v1/e32-argument-landscape/t27-branches-and-mechanisms-counted-first.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t27-branches-and-mechanisms-counted-first` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Stopped at the checkpoint, as briefed: the counts are taken, nothing is built.** The Goal stays
`InProgress`. ac1 passes. ac2 and ac3 wait for the PM's ruling on
[the relay prompt](#questions-for-the-pm).

**What the counts say** (hspolicy26 through 2026-10-20, taxonomy 1.4.0, read-only, 52 s):

* **Branches are not in the headings.**
  * No DA has a named or impact heading nested under another named heading below the position: 0
    documents on all 20 DAs.
  * Read in file order instead, Midterms has only 9 of 418 documents, from 6 teams, with an impact card
    after a named block. No outer heading is used by two teams, so the coach's list of branch headings
    is empty.
  * `dems win` never sits over an impact card, either nested or in file order.
  * The branch is in the tags. 242 Midterms documents (96 teams) have tags saying the Democrats win,
    against 14 documents (9 teams) for the Republicans. The three impact ranks' copies sit almost
    entirely in the Democrats' documents.
* **The mechanism: half the Economy DA is labelled, and its link-tag words rarely repeat.**
  * 46 of 89 Economy DA documents (22 of 44 teams) label a link or an internal link. 43 label neither.
  * Grouped by tag words, those cards make 220 groups, and 188 of them belong to one team. 29 groups
    used by two or more teams pass the screen ([the list](#word-list-2-the-economy-das-link-tag-word-groups)).
  * The shared groups describe one mechanism: paying for the plan, through spending and tax hikes, hits
    investment, jobs and GDP. Several of them are answers rather than links.
* **Splitting the Economy DA by link has little to go on.** Only 13 of the 46 labelled documents, and 6
  of the 44 teams, use the words of just one family (taxes, stocks, debt or rates). The seven most-shared
  groups use none.

**Recommendation:** a narrow version of option 2. A team's labelled link names an impact rank ahead of
its tag, with no taxonomy change. On hspolicy26 that renames 12 of 44 DA rows, one of them the Economy
DA's rank 2. I recommend against a two-level scenario (it would change nothing) and against splitting by
link ([the options](#the-three-options-measured)).

## The counts before building (ac1)

**What ran.** Read-only scripts in the session's scratchpad, built as t25's counts were:
* `counts/count_branches_and_mechanisms.py`:
  * wired by hand over `~/.debate-research/dev`, with no container, no worker pool, no aff assignments
    and no analytic texts;
  * the classification cache read through the run's read-only view;
  * the report's own `_LinkChains` captured, so sub-headings, chain roles, the named-heading rule and
    the impact rows are the shipped ones;
  * taxonomy 1.4.0 at `18da46d`, which is dev with t22 and t25;
  * a 115 s alarm on the interpreter.

  It took 56.3 s on the first run and **51.2 s on the final run** (52.3 s wall-clock, load average 5.8).
  No process outlived it. The two runs agree on every count.
* `counts/count_siblings_and_families.py` and `counts/count_coverage_and_direction.py` read a dump the
  first script wrote into the scratchpad, in under a second each.
* **Read-only:**
  * the classification cache's time (2026-10-26 01:27) and size are those t25 counted on;
  * `debate.sqlite3`'s SHA-256 is the same before and after every run;
  * nothing was written outside the scratchpad.
* **What printed.** stdout printed position ids and numbers only. The two word lists the PM allowed
  went to a separate scratchpad file, already screened, and are copied
  [below](#the-two-word-lists-for-the-coach).

**Definitions** (Decisions 1 to 4 say why):
* **Named heading.** t14's rule (`card_scenario`), with the coach's `not_scenarios` *not* applied, so
  that `dems win` still counts as one. Answers, role labels, headings the coach ruled name no position,
  numbered scenario headings and `NOT_A_SCENARIO` words are still not named headings.
* **Impact heading.** t10's rule, as t14 reads it.
* **Card counts.** Only counted cards: READS, on the position's side, as the report counts them.

### (a) Branches, per DA

**Nested headings, as the spec defines a branch.** Below the position, a card has at most two
sub-headings.
* Of 4,833 counted Midterms cards: 2,009 have none, 2,807 have one and 17 have two. The 17 are in 3
  documents: a link under a link, a uniqueness under a uniqueness, and a named impact under a bare
  `impact`.
* No other DA has a card with two sub-headings.
* So **no DA nests a named or impact heading under another named heading below the position: 0
  documents and 0 teams on all 20 DAs.**

**Read in file order instead.** Since teams do not nest headings, I also counted branches as sibling
blocks:
* a named block, and the labelled impact cards in later blocks of the same position section, until the
  next named block, numbered block or answer;
* uniqueness, link and impact blocks between them do not end it.

| DA | Documents | Teams | Nest a named or impact heading under a named heading: documents (teams) | An impact card after a named block, in file order: documents (teams) | Outer headings / used by 2+ teams | Of those, dropped by the coach |
|---|---|---|---|---|---|---|
| `ai-da` | 28 | 25 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `capital-flight-da` | 19 | 7 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `court-clog-da` | 17 | 9 | 0 (0) | 1 (1) | 1 / 0 | 0 |
| `debt-da` | 49 | 33 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `democracy-da` | 62 | 38 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `doctors-da` | 3 | 4 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `economy-da` | 89 | 44 | 0 (0) | 2 (1) | 2 / 0 | 0 |
| `federalism-da` | 44 | 35 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `hhs-da` | 20 | 6 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `innovation-da` | 9 | 3 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `irs-da` | 28 | 15 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `medical-devices-da` | 13 | 8 | 0 (0) | 1 (1) | 1 / 0 | 0 |
| **`midterms-da`** | **418** | **127** | **0 (0)** | **9 (6)** | **8 / 0** | **0** |
| `permitting-reform-da` | 10 | 6 | 0 (0) | 1 (1) | 1 / 0 | 0 |
| `pharma-da` | 74 | 45 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `politics-da` | 6 | 4 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `rates-da` | 44 | 16 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `stocks-da` | 53 | 24 | 0 (0) | 1 (1) | 1 / 0 | 0 |
| `taxes-da` | 11 | 7 | 0 (0) | 0 (0) | 0 / 0 | 0 |
| `unions-da` | 19 | 18 | 0 (0) | 0 (0) | 0 / 0 | 0 |

* Midterms' 9 documents: in 7 the later block is a named impact (`… impact` with words beside the
  label), and in 2 it is a bare `impact`.
* **No outer heading is used by two or more teams on any DA**, so there are none to list with their
  teams, documents and ranks. None of the 8 Midterms outer headings is a form the coach dropped.
* **`dems win`.** It is a named block heading in 8 Midterms documents from 5 teams. No labelled impact
  card sits under it, and it is never an outer heading in file order.

**Where the Midterms branch words are**, counted with the coach's own words as probes (`dems`,
`democrats`, `republicans`, `gop`, and words for winning). These are the session's probes, not heading
words read from the store.

| Where | Documents holding a dems word | Documents holding a republicans word |
|---|---|---|
| A heading above the position, or the position heading | 0 | 0 |
| A sub-heading, any shape | 33 | 19 |
| A tag | 357 | 236 |

* Of the 32 sections with a dems or republicans block, a labelled impact card follows within the next
  four blocks in **2**. In 8 the block is the section's last; the rest are followed by uniqueness, link
  or answer blocks, or other named blocks.
* **The branch per document, from its tags.** A tag holding a dems word followed by a word for winning:

| A document's tags say | Documents | Teams |
|---|---|---|
| The Democrats win, only | 242 | 96 |
| The Republicans win, only | 14 | 9 |
| Both | 47 | 20 |
| Neither | 115 | 56 |

  A team can read documents in more than one row. The impact ranks' copies sit in Democrats-only
  documents, against Republicans-only ones: rank 1, 22 against 1; rank 2, 34 against 1; rank 3, 9
  against 1.

### (b) The mechanism

**Every DA.** In this table:
* "Groups" are labelled cards grouped by their tag's words ([Decision 3](#decisions-and-assumptions));
* "printable shared" means used by two or more teams and not withheld;
* the last column is [option 2's](#the-three-options-measured) reach in the impact rows.

| DA | Documents | Label a link or IL | Link | IL | Neither | Teams labelling | Link-tag groups / used by 2+ teams (withheld) | Documents (teams) holding a printable shared group | Words beside a link label in a heading: documents / distinct / 2+ teams (withheld) | Impact rows a link ahead of the tag renames |
|---|---|---|---|---|---|---|---|---|---|---|
| `ai-da` | 28 | 0 | 0 | 0 | 28 | 0 | 0 / 0 (0) | 0 (0) | 0 / 0 / 0 (0) | 0 of 0 |
| `capital-flight-da` | 19 | 6 | 5 | 6 | 13 | 2 | 31 / 4 (0) | 4 (2) | 6 / 6 / 3 (0) | 0 of 3 |
| `court-clog-da` | 17 | 5 | 5 | 1 | 12 | 4 | 16 / 3 (1) | 3 (2) | 0 / 0 / 0 (0) | 1 of 3 |
| `debt-da` | 49 | 0 | 0 | 0 | 49 | 0 | 0 / 0 (0) | 0 (0) | 0 / 0 / 0 (0) | 0 of 0 |
| `democracy-da` | 62 | 0 | 0 | 0 | 62 | 0 | 0 / 0 (0) | 0 (0) | 0 / 0 / 0 (0) | 0 of 2 |
| `doctors-da` | 3 | 0 | 0 | 0 | 3 | 0 | 0 / 0 (0) | 0 (0) | 0 / 0 / 0 (0) | 0 of 0 |
| **`economy-da`** | **89** | **46** | **46** | **11** | **43** | **22** | **220 / 32 (3)** | **23 (11)** | **27 / 26 / 3 (1)** | **1 of 3** |
| `federalism-da` | 44 | 3 | 2 | 2 | 41 | 2 | 5 / 0 (0) | 0 (0) | 2 / 2 / 0 (0) | 0 of 1 |
| `hhs-da` | 20 | 14 | 14 | 0 | 6 | 4 | 21 / 4 (1) | 10 (4) | 4 / 4 / 0 (0) | 3 of 3 |
| `innovation-da` | 9 | 0 | 0 | 0 | 9 | 0 | 0 / 0 (0) | 0 (0) | 0 / 0 / 0 (0) | 0 of 0 |
| `irs-da` | 28 | 17 | 16 | 8 | 11 | 8 | 47 / 17 (1) | 15 (8) | 8 / 2 / 1 (0) | 0 of 3 |
| `medical-devices-da` | 13 | 7 | 7 | 2 | 6 | 3 | 25 / 6 (0) | 5 (2) | 3 / 3 / 0 (0) | 2 of 3 |
| `midterms-da` | 418 | 162 | 148 | 73 | 256 | 64 | 442 / 117 (22) | 124 (54) | 89 / 31 / 3 (1) | 0 of 3 |
| `permitting-reform-da` | 10 | 2 | 2 | 0 | 8 | 1 | 3 / 0 (0) | 0 (0) | 2 / 1 / 0 (0) | 1 of 3 |
| `pharma-da` | 74 | 24 | 22 | 10 | 50 | 17 | 100 / 17 (6) | 11 (8) | 18 / 13 / 1 (1) | 0 of 3 |
| `politics-da` | 6 | 0 | 0 | 0 | 6 | 0 | 0 / 0 (0) | 0 (0) | 0 / 0 / 0 (0) | 0 of 2 |
| `rates-da` | 44 | 26 | 26 | 10 | 18 | 10 | 83 / 9 (2) | 11 (5) | 17 / 5 / 1 (1) | 1 of 3 |
| `stocks-da` | 53 | 18 | 18 | 2 | 35 | 10 | 69 / 4 (2) | 4 (4) | 10 / 10 / 3 (0) | 2 of 3 |
| `taxes-da` | 11 | 10 | 10 | 0 | 1 | 7 | 59 / 12 (0) | 5 (5) | 9 / 11 / 3 (0) | 1 of 3 |
| `unions-da` | 19 | 0 | 0 | 0 | 19 | 0 | 0 / 0 (0) | 0 (0) | 0 / 0 / 0 (0) | 0 of 3 |

**The Economy DA in detail:**
* 89 documents and 44 teams. 46 documents label a link or an internal link (all 46 a link, 11 an
  internal link as well), from 22 teams. **43 documents label neither.**
* 459 labelled cards, in 220 groups by tag words. By how many teams use each group:

  | Teams | 1 | 2 | 3 | 4 | 6 | 7 | 8 |
  |---|---|---|---|---|---|---|---|
  | Groups | 188 | 20 | 2 | 2 | 5 | 2 | 1 |

* **32 groups are used by two or more teams. 3 of them are withheld** (they hold a caselist word) and
  counted only. **The other 29 are [listed for the coach](#word-list-2-the-economy-das-link-tag-word-groups).**
  They reach 23 of the 46 labelled documents and 11 of the 22 labelling teams.
* **Groups 1 to 10** are each used by 4 to 8 teams, in 13 to 18 documents. They look like the link cards
  of one widely shared file.
* Words beside a link label in a heading (`taxes link`): 27 documents, 26 distinct, 3 used by two or more
  teams, 1 of those withheld.
* **The impact ranks.** All three are named `(tag)` today, as t25 recorded. A labelled link card sits
  above an impact copy in its section for **rank 2 only**.

**Whether some "Economy DAs" are different DAs by link.** The family words are the session's, matched
as whole words in the labelled cards' tag words and the words beside a link label:
* taxes: `tax`, `taxes`, `taxation`, `taxing`;
* stocks: `stock`, `stocks`, `equities`, `equity`;
* debt: `debt`, `deficit`, `deficits`, `borrowing`;
* rates: `rate`, `rates`, `interest`, `fed`, `bond`, `bonds`, `yields`.

| | Taxes | Stocks | Debt | Rates |
|---|---|---|---|---|
| Economy DA documents holding the family's words | 32 | 18 | 9 | 22 |
| Teams | 17 | 11 | 6 | 11 |

| Families per labelled document | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Documents (of 46) | 6 | 13 (taxes 6, stocks 6, rates 1) | 13 | 14 |

| Families per team | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Teams (of 44) | 24 | 6 (taxes 4, stocks 2) | 4 | 9 | 1 |

* **For comparison**, the taxonomy's separate DAs on this store: `taxes-da` has 7 teams and 12 rounds,
  `stocks-da` 24 and 58, `rates-da` 16 and 46. `economy-da` has 44 teams and 92 rounds.
* **The family words overcount.** Group 8 is `rates` for "the top *rate*", which is a tax rate. Most
  labelled documents hold several families because one file runs several link cards.
* **The groups do not suggest separate DAs by link.** The seven most-shared groups hold no family word.
  Read together, the shared groups describe one link: the plan's cost, paid by spending and tax hikes,
  hurting investment, jobs and GDP. That overlaps the Taxes DA's link more than it divides the Economy
  DA. Whether `taxes-da` and `economy-da` should stay apart is the coach's call; I build nothing on it.

### The two word lists for the coach

Both lists are screened as t22's seed was, read-only:
* the screen read all 5,126 hspolicy26 disclosures from `debate.sqlite3` opened `mode=ro`, giving 959
  caselist words;
* a word holding a caselist word is withheld by `is_withheld` and counted, never written;
* a word one team uses is never listed;
* as a second check, the report's pre-share scan (`scan_report`) found **0 hits** in list 2.

No team code, school, tournament word or card text is printed here or in the counts.

#### Word list 1: outer branch headings two or more teams use

**None.** No outer heading is used by two or more teams on any DA, whether read by nesting or in file
order, so there is nothing to list or withhold.

#### Word list 2: the Economy DA's link-tag word groups

29 groups, with teams and documents. Each group is the tag's words, normalized as a heading and with
label words removed, the way t14 forms the words beside a label. Numbers 13, 26 and 31 are the 3 withheld.
The family column is the session's family words, as above.

| Group | Teams | Documents | Label | Family words | Words |
|---|---|---|---|---|---|
| 1 | 8 | 17 | link | | increased government spending has spillover effects that eviscerate investment |
| 2 | 7 | 18 | link | | those alone devastate the economy cant raise revenue presumption |
| 3 | 7 | 17 | link | | causes an unemployment crisis |
| 4 | 6 | 17 | link | | frame defense through uncertainty investors have priced in the status quo but the plans an unprecedented shock that results in compounding recessionary effects that swamp adaptation |
| 5 | 6 | 17 | link | | uncertainty its perceived as too much spending even if materially beneficial |
| 6 | 6 | 15 | link | | budgets conservative estimates confirm the tail end of financing the plan is 2 trillion a year that collapses the gdp |
| 7 | 6 | 15 | link | | inequality it encourages growth at the top not the bottom |
| 8 | 6 | 15 | link | rates | it straight turns the case hikes trade off with social services they raise the top rate to above revenue maximizing |
| 9 | 4 | 13 | link | | demand it reduces non health spending 80 forces people out of the labor market |
| 10 | 4 | 13 | link | taxes | taxes it requires massive payroll income corporate hikes |
| 11 | 3 | 3 | internal link | stocks | a stock crash reverses wealthy spending thats key to economic growth |
| 12 | 3 | 3 | link | | should is immediate |
| 14 | 2 | 5 | link | | which means it omits massive variables that hamstring solvency thats proven by robust simulations |
| 15 | 2 | 4 | link | | its insignificant disproven by studies |
| 16 | 2 | 4 | link | taxes | payroll taxes are worse thats crfb |
| 17 | 2 | 3 | link | taxes | unemployment is worse taxes also cause it |
| 18 | 2 | 3 | link | | workers are worse |
| 19 | 2 | 2 | link | | demand it collapses non health spending 80 forces people out of the labor market |
| 20 | 2 | 2 | link | | economic shocks are faster than cost savings the transition period causes collapse |
| 21 | 2 | 2 | link | | establish must be at present time |
| 22 | 2 | 2 | link | | externally the government cant raise revenue hampering stability thats crfb |
| 23 | 2 | 2 | link | taxes | its fast the mere perception of taxes causes offshoring |
| 24 | 2 | 2 | link | | steps arent sufficient |
| 25 | 2 | 2 | link | taxes | straight turns the case tax hikes collapse ability to raise revenue for social services |
| 27 | 2 | 2 | link | taxes | taxes it requires massive payroll income corporate tax hikes |
| 28 | 2 | 2 | link | | thats jayapals bill its two years |
| 29 | 2 | 2 | link | debt, rates, taxes | the tax rate doubles spending drops eighty percent debt massively increases 17 million workers exit the economy |
| 30 | 2 | 2 | link | taxes | their advocates call for increased corporate wealth taxes |
| 32 | 2 | 2 | link | taxes | wealth taxes collapse investment domestic business |

**What the groups are.**
* Most are whole tag sentences, so a group is in effect one shared card, not a mechanism name.
* Groups 12, 14, 15, 21 and 24 read as answers (to a counterplan, to T, to a solvency claim) that carry
  a link label, not links.
* Group 28 names the bill's sponsor, a public official, not a caselist word.

### The three options, measured

**1. A two-level scenario (branch, then impact) in the taxonomy.**
* **On hspolicy26 it changes nothing a reader sees.** No outer heading has two teams, so no Midterms row
  would gain a branch, read either way.
* It still costs a taxonomy bump (1.5.0 under t08's lock, since lists change) and the ~12-minute refill
  that re-keys the caches.
* What hspolicy26 shows is one branch, written in tags: 242 documents and 96 teams say the Democrats
  win, against 14 and 9. A branch read from tags would label almost every Midterms rank `Dems win`.
  That is a new rule over tag words (a coach's branch forms matched in uniqueness tags), or t07's model
  stage.

**2. The mechanism as a named link per DA, ahead of the tag in t25's order.** Two ways to build it:
* **(2a) The labelled link, read as t25 reads an internal link.** Order: scenario, internal link,
  **link**, tag, card above, with the mark `(link)`. The link is the nearest card above the impact copy
  in its section that is counted and labelled a link. The tag with the most teams is quoted whole.
  * **On hspolicy26:** a labelled link sits above the impact copy for 24 of 44 DA rows. **12 rows are
    renamed:** 11 now named by their tag and 1 now left out. One more row's link is withheld, so its
    tag stays. Those 12 rows are on 8 DAs: HHS 3, Medical devices 2, Stocks 2, and Court clog,
    Economy, Permitting reform, Rates and Taxes 1 each.
  * **The Economy DA:** rank 2 is renamed. Ranks 1 and 3 keep their tag.
  * **Advantages are untouched on this store.** t25's order is shared by both kinds, and an advantage
    can label a link, but no advantage impact copy has a labelled link above it: 0 of 43 rows (a third
    run of the same script, 54.9 s, with every other count unchanged). The Midterms DA is untouched
    too: its 3 rows are named by scenario.
  * **No taxonomy change,** so no bump and no refill. The goldens, a `LeadInSource` value, and the dry
    run's per-kind line change.
* **(2b) A coach-named link list per DA,** in t22's pattern: a name and its forms, matched against the
  link-tag groups.
  * **On hspolicy26:** for the Economy DA, the 29 printable groups reach 23 of the 46 labelled
    documents and 11 of the 22 labelling teams. 188 of its 220 groups belong to one team and could
    never show.
  * Several shared groups are answers, which the coach would drop.
  * It needs taxonomy 1.5.0 and the refill.

**3. Splitting DAs by link in the taxonomy.**
* **On hspolicy26:** only 13 of 46 labelled Economy documents and 6 of 44 teams use the words of one
  family. A whole-document split would move at most 4 teams toward `taxes-da` and 2 toward `stocks-da`.
  27 labelled documents use two or three families, and 43 documents are not labelled at all.
* **It is not a taxonomy edit alone.** A position is placed by its headings and aliases, and a split by
  link needs a classification rule that reads link tags. That re-keys the classification cache, and it
  is outside this task's rules.

## Questions for the PM

A paste-ready relay prompt:

```text
v1-e32-t27 (branches and mechanisms, counted first): the counts are taken; nothing is built. Stopped at
the checkpoint. ac1 PASS; ac2 and ac3 wait for your ruling. Goal InProgress.

The counts (hspolicy26 through 2026-10-20, taxonomy 1.4.0, read-only, wired by hand, 51 s under an
alarm; stdout ids and numbers only; the two word lists are in the report, screened against 5,126
disclosures, 0 scan hits):

(a) Branches.
- Nested headings, as the spec defines a branch: 0 documents on all 20 DAs. Below the position a card
  has at most 2 sub-headings (17 of 4,833 Midterms cards; none named over named).
- Read in file order instead (an impact card after a named block in its section): Midterms 9 of 418
  documents from 6 teams, 8 outer headings, none used by 2 teams; other DAs 0 to 2 documents.
- So there are no outer headings that 2+ teams use, and none of them is dropped. "dems win" is a block
  heading in 8 documents from 5 teams, never over an impact card.
- The branch is in the tags. Documents saying the Democrats win: 242 (96 teams). The Republicans: 14
  (9 teams). Both 47, neither 115. Impact ranks 1, 2 and 3: 22, 34 and 9 copies in Democrats-only
  documents, against 1 each in Republicans-only ones.

(b) The mechanism.
- Economy DA: 46 of 89 documents (22 of 44 teams) label a link or an internal link; 43 label neither.
  459 labelled cards make 220 tag-word groups, 188 of them one team's. 32 groups are used by 2+ teams:
  3 withheld, 29 listed. They reach 23 documents and 11 teams.
- The shared groups describe one link: paying for the plan through spending and tax hikes hurts
  investment, jobs and GDP. 5 of them are answers that carry a link label.
- Split by link (my family words: taxes, stocks, debt, rates): only 13 of 46 labelled documents and 6
  of 44 teams use one family (teams: taxes 4, stocks 2). The 7 most-shared groups use none.
- Every DA: a summary line each in the report; 7 of 20 DAs label no link or IL in any document.

Options, with what each changes on hspolicy26:
1. Two-level scenario (branch, then impact) in the taxonomy: nothing shown (no outer heading has 2
   teams). Costs 1.5.0 plus the refill. A branch from tags would label nearly every Midterms rank
   "Dems win" and needs a new tag-word rule or t07.
2. The mechanism as a named link, ahead of the tag in t25's order:
   (2a) the labelled link above the impact copy, read as t25 reads an internal link, marked (link).
        Order: scenario, internal link, link, tag, card above. Renames 12 of 44 DA rows (11 from a
        tag, 1 from left out) on 8 DAs, including the Economy DA's rank 2 (ranks 1 and 3 keep their
        tag). Advantages: 0 of 43 rows have a labelled link above, so none changes. No taxonomy
        change, no bump, no refill.
   (2b) a coach-named link list per DA (t22's pattern, forms matched against link-tag groups): the
        Economy DA's 29 groups reach 23 of 46 labelled documents; needs 1.5.0 plus the refill.
3. Split DAs by link: at most 4 teams toward taxes-da and 2 toward stocks-da; needs a classification
   rule reading link tags, which re-keys the classification cache. Not a taxonomy edit alone.

Recommendation: 2a alone. It is deterministic, adds no model call and no bump, and changes 12 rows
measurably. Not 1: it would show nothing on this store. Not 3: the data do not divide the Economy DA by
link. Defer 2b until the coach has read the 29 groups and says whether naming them is worth it (most
groups are whole tag sentences, several are answers). Short mechanism names otherwise belong to t07.

Questions:
Q1. Rule 1, 2a, 2b, 3, or a hybrid.
Q2. If 2a: confirm the order (scenario, internal link, link, tag, card above) and the mark "(link)".
Q3. Two notes for the coach, no build here: hspolicy26's Midterms DA is run almost entirely as "Dems
    win"; and the Economy DA's shared link is the plan's financing, which overlaps the Taxes DA (7
    teams).
2a stays inside the spec's packages (LeadInSource is in debate_core.domain, already listed).
```

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| branches-and-mechanisms | In progress | Counts taken and sent (ac1). The build waits for the PM's ruling. The node's test command passes on the unchanged branch (baseline). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before building, read-only, (a) and (b), sent to the PM with the three options | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python <scratchpad>/counts/count_branches_and_mechanisms.py config/landscape <scratchpad>/counts/word_lists_final.json` → exit 0 in 51.2 s; no process left; `debate.sqlite3` SHA-256 unchanged. [The counts](#the-counts-before-building-ac1) and [the relay prompt](#questions-for-the-pm) |
| ac2: after the ruling, on synthetic fixtures, the chosen option matches hand-written goldens; tests shown failing first | NOT RUN | Waits for the ruling. Nothing is built before it, as the brief says |
| ac3: the operator's dry run on hspolicy26 shows the ruling, with counts before and after (operator) | NOT RUN | Waits for the build. The counts before are in this report: for 2a, 12 of 44 DA rows renamed, Economy rank 2 |
| branches-and-mechanisms: `uv run pytest packages/debate_core/tests/arguments/landscape` | NOT RUN (baseline green) | Baseline only, before any change: `.venv/bin/python -m pytest -q -p no:randomly packages/debate_core/tests/arguments/landscape` → **977 passed in 28.94s**. The node is done only after the build |

## Before the report (working agreement 10)

Only this report changed, so the checks are the cheap ones:
* **`uv run --frozen python scripts/affected_tests.py --run`.** It chose 26 test files, the always-run
  list. Result: **1 failed, 1,360 passed in 121.54s**, at load average 7.2.
  * The run took 2 min 11 s in all, past the two-minute line. I ran it without an alarm, expecting it to
    be shorter. That was my mistake.
  * The failure was
    `tests/scripts/test_caselist_run_deploy.py::test_every_aws_call_is_made_as_the_deployer_profile_in_us_east_1`.
    This is the deploy-script test t22 recorded failing under load, which the PM filed as an E40 task.
    Alone it passed: `1 passed in 6.86s`. This branch changes no code.
* `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` → no `#` comments in 504
  blocks, this report included.
* `scripts/docs_index.py --check-descriptions` → all 54 documents have a description.
* `uv run scripts/validate_specs.py` → OK, 475 files.
* No ruff, pyright or lint-imports run, since no Python file changed.

## Files changed

* `docs/session-reports/v1-e32-t27-branches-and-mechanisms-counted-first.md`: this report.

No code, config, fixture or spec changed. The count scripts are in the session's scratchpad
(`counts/`), as t25's were.

## Deviations from the spec

1. **The spec's branch (a nested heading) does not occur on hspolicy26, so I also counted a second
   reading.**
   * The nested count is reported as specified: 0 on every DA.
   * The second reading is in file order: an impact card after a named block in its section.
   * Both are counts only.
2. **Words in the report.** The spec's forbidden list says no heading words in the counts. The PM's
   clarification of 2026-10-26 puts two screened word lists in the report only, and keeps the counts
   to ids and numbers. That is what was done. List 1 is empty. The PM records the clarification in the
   next batch.
3. **The counts were run by the session.** They are read-only, over files the operator already has, and
   took 51 s. Working agreement 2 and the brief allow that.

## Decisions and assumptions

1. **A named heading ignores the coach's drops.** Otherwise `dems win`, which the coach dropped, could
   never be an outer heading, and the PM asked how many dropped headings are outer ones. Everything
   else in t14's rule applies: answers, role labels, headings the coach ruled name no position, numbered
   headings and `NOT_A_SCENARIO` words are not named headings.
2. **The file-order reading.** A named block opens a branch. Labelled impact cards in later blocks of
   the same position section belong to it until the next named block, numbered block or answer.
   Uniqueness, link and impact blocks do not end it. Only counted cards are read, so a block of uncounted
   cards neither opens nor ends one.
3. **Link-tag groups are formed as t14 forms the words beside a label.** The tag is normalized by
   `normalize_heading`, and t14's label words (`link`, `internal`, `il`, `impact`, `and`, …) are removed.
   A group is that whole string, so it is in effect one shared tag. Its teams are those reading any card
   in it.
4. **Probes and families are the session's words**, not words read from the store:
   * the Midterms probes: `dems`, `dem`, `democrats`, `democrat`; `republicans`, `republican`, `gop`,
     `reps`; and words for winning;
   * the four link families.

   They are crude by design. The family words overcount (a tax *rate* is `rates`), and the
   Democrats-win probe is "a dems word, then a word for winning, in one tag". They size the options and
   classify nothing.
5. **Option 2a's reach** mirrors t25's internal link exactly: walk up the file from each labelled impact
   copy, within its position section, skipping uncounted cards, to the first counted card labelled a
   link. Then take the tag with the most teams, apply `is_withheld`, and rename the row when it is now
   named by a tag, by the card above, or left out.
6. **"Documents" are counted per DA.** A document holding several DAs is counted under each, so the
   rows of the tables are not summed into a DA total.

## Operator follow-ups

None yet. After the ruling, the build's ac3 needs the operator's dry run, and the refill too if the
ruling bumps the taxonomy. The blocks will come with the build.

## Follow-up work

* **Branches from tags (t07 or a new E32 task),** if the coach wants them. hspolicy26 writes the
  Midterms DA's branch in its uniqueness tags, not its headings.
* **Economy DA and Taxes DA,** a coach's question: the Economy DA's shared link is the plan's
  financing, through spending and tax hikes.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
