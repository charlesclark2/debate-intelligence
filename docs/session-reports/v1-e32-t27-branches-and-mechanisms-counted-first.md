# Session report: v1-e32-t27-branches-and-mechanisms-counted-first

| | |
|---|---|
| Task | `v1-e32-t27-branches-and-mechanisms-counted-first` — Branches and mechanisms in the DA sections, counted first |
| Spec | [`plan_specs/v1/e32-argument-landscape/t27-branches-and-mechanisms-counted-first.yaml`](../../plan_specs/v1/e32-argument-landscape/t27-branches-and-mechanisms-counted-first.yaml) |
| Epic / release | `v1-e32-argument-landscape` / `v1.2` |
| Branch | `task/v1-e32-t27-branches-and-mechanisms-counted-first` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

**Complete. Every criterion passed, and the Goal is `Succeeded`.** The operator's dry run (ac3,
2026-10-26, 66.1 s) matched every predicted count
([below](#the-operators-dry-run-ac3)).

**What is built.** Under each DA's and advantage's impact cards, "What each impact runs through" names
every rank by the first of these it has:
1. its scenario;
2. its internal link;
3. **its link, marked `(link)`**;
4. its own tag;
5. the card above it.

The link is read as t25 reads the internal link. It is the nearest card above the impact copy that is:
* under the same position heading;
* counted for the position;
* labelled a link by t14's reader.

A withheld link falls through to the next source and is counted. A label naming an answer is no link.
There is no taxonomy change, no bump and no model call. The dry run's "Impact ranks named" line gains
"by a link".

**t14's reader took one answer for a link on hspolicy26.** It was a link tag opening `the link turns`,
in 1 document: t14 refused a `link turn(s)` opening but not one with a leading `the`. The reader now
also refuses:
* that opening;
* a link heading naming a non-unique or `no links`;
* a link tag calling its link non-unique.

On hspolicy26 only that one tag changes, and the 12 renamed rows stay 12.

**On hspolicy26, measured after the build** (read-only, wired by hand, 55.9 s):
* **DA rows** are named 9 by a scenario, 4 by an internal link, **12 by a link**, 18 by a tag and 0 by
  the card above. 1 is left out (2 before), and 2 tags are withheld.
* **The Economy DA's rank 2** is `(link)`. Ranks 1 and 3 keep their tag.
* **No advantage row changes.**

Every count is the one the relay prompt predicted.

**How it was checked:**
* The goldens were written by hand and committed before any code (`f428e6f`), and matched on the first
  green run.
* The tests ran red against a skeleton that names nothing by a link: 42 failed (`ccd0ba0`).
* 19 mutants, the PM's three among them, all caught. Two survived the first pass, and the tests they
  showed missing were added (`646428b`).

## The PM's rulings (2026-10-26)

* **2a alone.** A rank is named by the labelled link above its impact copy, read as t25 reads an
  internal link, and marked `(link)`. No branch build, and no 2b or 3.
* **The branch question is answered by the counts.** On hspolicy26 the Midterms DA is run almost entirely
  as "Dems win" in the tags, and no team nests impacts under a branch heading. If "Republicans win"
  grows, t22's unlisted-words line and these counts are where it shows.
* **The order is confirmed:** scenario, internal link, link, tag, card above. The internal link stays
  ahead, as the step nearest the impact.
* **t14's label reader reads "link".** A label naming an answer (no link, link turn, non-unique and the
  like) is not a link. If the reader treats any as one, count them, exclude them, and test it
  ([below](#answer-labels-on-hspolicy26)).
* **A withheld link falls through** to the next source and is counted, as in t25.
* **The build:**
  * goldens hand-written before code, with a variant reaching `(link)` and a withheld link;
  * red first;
  * mutants under working agreement 8, the PM's three among them;
  * no taxonomy change and no bump;
  * "by a link" in the dry run;
  * the dry-run block for ac3;
  * the How-to-read bullet and the guide.

## For the coach

* **The Midterms DA runs as "Dems win."** Across 418 hspolicy26 documents (through 2026-10-20), the tags
  of 242 documents (96 teams) say the Democrats win, against 14 (9 teams) for the Republicans. No team
  nests its impacts under a branch heading. If "Republicans win" grows, it will show in the dry run's
  "Scenario words no list holds" line and in a recount of these numbers.
* **The Economy DA's shared link is the plan's financing.** Its most-shared link cards say that paying
  for the plan, through spending and tax hikes, hurts investment, jobs and GDP. That overlaps the Taxes
  DA (7 teams). Whether the two stay separate positions is your call. The 29 link-tag groups two or
  more teams use are [listed below](#word-list-2-the-economy-das-link-tag-word-groups).

## The build (ac2)

### The goldens, by hand, before any code (`f428e6f`)

* **`golden/report.md`.**
  * The How-to-read bullet names the link.
  * Both per-kind lines gain "by a link": advantage 0, DA 1.
  * The Spending DA's rank 1 becomes `Spending triggers a debt spiral (link)`. Its scenario is withheld,
    no internal link sits above it, and `b1`'s cluster 14 above it is under `link`.
* **`scenario_vocabulary/impact_sections.md`** (t22's) shows the same rank 1 and the per-kind lines.
* **`readable_impact_chains/impact_sections.md`** (t25's):
  * the per-kind lines, with 0 by a link (its Spending rank 1 is named by `Market crash` first);
  * the left-out line's wording.
* **`link_lead_ins/`, the new variant.** Three tag edits and `recession` dropped:
  * `b1`'s link to rank 1 holds `Birchmoor`, so it is **withheld, counted**, and rank 1 falls to its tag;
  * `b5`'s internal link to rank 3 holds `Birchmoor`, so it is **withheld, counted**;
  * `b5`'s paragraph 3 now opens `Link:`, so it **names rank 3 `(link)`** behind the withheld internal
    link.

  Its README works out every line. Its impact sections, its CSV and the rest of report.md (unchanged)
  are each a test.
* **`synthetic_caselist/README.md`**: a bullet on the link.

### The tests

* **`test_link_lead_ins.py` (new), 24 tests:**
  * the three goldens;
  * the unchanged caselist;
  * the order: the internal link ahead of the link (the PM's), the scenario ahead of the link, the link
    ahead of the tag;
  * the nearest link;
  * a link in another section of the file, or on a card that answers the position, naming nothing;
  * no advantage link;
  * five answer labels naming no rank;
  * withholding: fall-through and count, never shown, both link and tag withheld, a withheld link never
    reached.
* **`test_link_chains.py`:**
  * six link headings naming an answer, refused;
  * eight answer tags, refused, among them hspolicy26's `the link turns`;
  * three must-not cases, where later words say `turns` or `unique`.
* **t25's `test_readable_impact_chains.py`:** the order, the counts with a link column, the domain's
  checks with five sources.
* **The dry run's test:** five distinct counts per kind, and the synthetic caselist's line.

### Red against a skeleton (`ccd0ba0`)

The skeleton has the shape and names nothing by a link:
* `LeadInSource.LINK` in the order;
* `ImpactCard.link_tag` and its place in `runs_through`;
* the report's "by a link" label.

The service passes no link. t14's reader is unchanged, and so are the bullet, the left-out wording and
the dry run's label.

The run covered the landscape tests, the report service's tests and the dry run's test: **42 failed,
1,085 passed**.

| Failing, grouped by reason | Count |
|---|---|
| Goldens: base report.md (`test_render`), t22's two, t25's two, the variant's two | 7 |
| Order and service: the unchanged caselist (t25's and the new test), the edits' rank 3, internal link and scenario ahead of the link, link ahead of the tag, the nearest link, t25's case with no lists | 8 |
| Withholding: fall-through and count, both withheld, never reached (the count differs: the skeleton never reaches the withheld link) | 3 |
| Answer labels in the report: five tags (the same reason: rank 1's withheld link not counted) | 5 |
| t14's reader: six headings and seven tags naming an answer, still read as a link | 13 |
| The dry run: its six tests call `report_lines`, which has no "by a link" label (`KeyError: LeadInSource.LINK`) | 6 |

**Already passing on the skeleton, and why:**
* must-not cases: a link in another section; no advantage link; `test_a_withheld_link_is_never_shown`,
  since the skeleton shows no link at all;
* the reader's tag `No links: …`, already none because it never opens `link`;
* the reader's must-not cases.

The mutants below show they bite.

**Two expectations of t25's I had not updated before the red run:**
* the left-out line's wording in `test_an_empty_row_is_left_out_and_counted_never_shown`, which passed
  at red since the skeleton kept the wording;
* the dry run's synthetic lines in `test_the_dry_run_prints_the_planks_…`, which failed at red with the
  `KeyError`.

Both were corrected by hand to the new text after the first green run, and are in `672ada4`.

### The build (`672ada4`, `a87cd88`)

* **`link_chains`:**
  * `NOT_A_LINK` gains `no links`, `non unique`, `nonunique` and `not unique`;
  * a tag is no link when, past a leading `the`, it opens with one of those answers, or when the words
    after `link(s)` call it non-unique;
  * the docstrings.
* **`landscape_report`:**
  * one walk for the internal link and the link (`_labelled_above`: same section, counted cards,
    nearest);
  * the link goes to `rank_name`, and is kept on the row unless withheld.
* **`domain.landscape_report`:** `LeadInSource.LINK`, `LEAD_IN_ORDER`, `ImpactCard.link_tag` (report.md
  only, so impact_cards.csv is unchanged).
* **`render`:** the bullet, the left-out wording, "by a link".
* **The dry-run script:** "by a link".
* **The guide.**

**`a87cd88`.** The first build also refused `turn(s)` and `defense` after `link(s)`. t14's own
openings (`link turn(s)`, `link defense`) already refuse those once a leading `the` is dropped, so the
entries could not be told from their absence. Working agreement 8 says to remove such a check, so it
was removed.

### Mutants

19 mutants:
* each applied alone (one rule, in one or two edits);
* the tests run in a fresh process with `PYTHONDONTWRITEBYTECODE=1` and a new, empty
  `HYPOTHESIS_STORAGE_DIRECTORY` per run (no Hypothesis is used);
* the files restored and checked by SHA-256, and `git status` clean after each batch;
* the test files: `test_link_lead_ins.py`, `test_readable_impact_chains.py`, `test_render.py`,
  `test_scenario_vocabulary.py`, `test_link_chains.py`, `application/test_landscape_report.py` and the
  dry run's test: 392 tests, 394 after `646428b`.

| Mutant | Failed | Caught by |
|---|---|---|
| **The link is chosen ahead of the internal link (the PM's)** | 6 | `test_an_internal_link_names_a_rank_ahead_of_its_link`, the variant's golden, the edits' rank 3, the order |
| **An answer label is read as a link: the tag's check is gone (the PM's)** | 14 | the reader's answer tags, the five answer labels in the report |
| **A withheld link is shown: not passed over, and kept on the row (the PM's)** | 14 | `test_a_withheld_link_is_never_shown`, fall-through and count, both withheld, never reached, the variant's golden |
| The tag is chosen ahead of the link | 22 | the base golden, the unchanged caselist, the dry run's synthetic lines |
| The link is chosen ahead of the scenario | 24 | `test_a_scenario_names_a_rank_ahead_of_its_link`, t14's withheld-name case |
| The card above is chosen ahead of the link | 6 | t25's order and goldens |
| No link is read (the skeleton) | 20 | the goldens, the order and withholding cases |
| The link is read as the internal link's role | 15 | the link ahead of the tag, the scenario ahead of the link, both withheld |
| The walk for a link crosses into another section | 1 | `test_a_link_under_another_heading_of_the_position_names_nothing`. **Survived the first pass**; this test was added in `646428b` |
| A link no team's counted card holds names a rank | 1 | `test_a_link_on_a_card_that_answers_the_position_names_nothing`. **Survived the first pass**; added in `646428b` |
| The farthest link above is read, not the nearest | 5 | `test_the_link_is_the_nearest_…`, the variant's golden |
| A withheld link is passed over but not counted | 12 | the withheld counts in the order, answer and withholding cases |
| A withheld link is kept on the row | 1 | `test_a_withheld_link_falls_through_to_the_tag_and_is_counted` |
| A tag's leading `the` hides an answer | 4 | the reader's `The link turn(s)` tags, the report's `The link turns` |
| A tag calling its link non-unique is a link | 5 | the reader's non-unique tags, the report's `Links are non-unique` |
| A link heading naming a non-unique or `no links` is a link (t14's list as it was) | 6 | the reader's six headings |
| A link-named row shows its internal link's words | 150 | the domain refuses the row (`names the row, but the row has none`) in every report |
| The kind line counts link rows as internal-link rows | 4 | the four goldens |
| The dry run labels the link count as the tag's | 2 | the dry run's two line tests |

## The real store after the build (ac3's prediction)

**What ran.** `counts/count_after_build.py` in the session's scratchpad, wired as the counts were.
* It took 55.9 s and 49.6 s, under the 115 s alarm, and no process outlived it.
* `debate.sqlite3`'s SHA-256 was unchanged, and nothing was written.
* It printed counts and position ids only.

| | Advantage | DA |
|---|---|---|
| Impact rows | 43 | 44 |
| Named by a scenario / internal link / **link** / tag / card above | 0 / 0 / **0** / 39 / 2 | 9 / 4 / **12** / 18 / 0 |
| Left out | 2 | **1** |
| Tags withheld (links included) | 4 | 2 |
| Before (t25's operator dry run): scenario / internal link / tag / card above; left out; withheld | 0 / 0 / 39 / 2; 2; 4 | 9 / 4 / 29 / 0; 2; 2 |
| Scenario lines: rows with a scenario, names withheld, documents with no scenario heading or role label | 0, 1, 676 of 1,164 | 9, 0, 253 of 662 |

* **The 12 DA rows:**
  * by DA: HHS 3, Medical devices 2, Stocks 2, and Court clog, Economy, Permitting reform, Rates and
    Taxes 1 each;
  * 11 were named by their tag, and 1 was left out.
* **The Economy DA:** rank 1 `(tag)`, rank 2 `(link)`, rank 3 `(tag)`.
* **DA tags withheld stay at 2.** The row the link rescued from "left out" no longer reaches its withheld
  own tag (−1). The row whose link is withheld now counts it (+1).
* **Advantages:** no advantage impact copy has a labelled link above it, so nothing changes.
* The scenario lines are t22's and t25's.

### Answer labels on hspolicy26

The PM's rule, "if the reader treats any as one, count them". I first counted with probe phrases, the
session's words: non-unique, no links, takeout, turns, defense, overview and others.
* **Over the 1,787 counted DA cards labelled a link, in 268 documents:**
  * no accepted link heading holds a non-unique, no-links, takeout or turn phrase;
  * 12 link headings in 5 documents hold `overview` or `o v`. They are the team's own link overview, not
    an answer, and stay links;
  * 10 link tags hold `turns` in their first six words. Only one is a link-turn label: a tag opening
    `the link turns …`, which t14 read as a link because only `link turn(s)` openings were refused. In
    the other nine, `turns` comes two or three words in and not after the link word; four of them read
    `turns case` or `turns the case`. The rule reads only the label at the opening, and I did not read
    those tags further.
* **After the build, against t14's old rule** (`count_after_build.py`): the widened reader refuses
  exactly **1 DA link tag in 1 document**, and no heading. No advantage card changes.

## The operator's dry run (ac3)

**What ran:** [Operator follow-up 1](#operator-follow-ups) at `9c1e6ee`, on 2026-10-26. The guards
passed, nothing was written, and it took 66.1 s.

| Dry run line | Expected in this report | Measured |
|---|---|---|
| Taxonomy and writes | 1.4.0, nothing written | `taxonomy 1.4.0: nothing written; 7 files planned` |
| Scenarios, advantage / DA | 43 / 44 rows, 0 / 9 with a scenario, 1 / 0 names withheld; documents 676 of 1164 and 253 of 662 (t22's and t25's runs) | 43 / 44, 0 / 9, 1 / 0; documents 676 of 1164 and 253 of 662 |
| Impact ranks named, advantage | 0 / 0 / 0 / 39 / 2; 2 left out; 4 tags withheld | **0 by a scenario, 0 by an internal link, 0 by a link, 39 by a tag, 2 by the card above; 2 left out; 4 tags withheld** |
| Impact ranks named, DA | 9 / 4 / 12 / 18 / 0; 1 left out; 2 tags withheld | **9 by a scenario, 4 by an internal link, 12 by a link, 18 by a tag, 0 by the card above; 1 left out; 2 tags withheld** |
| Scan | t25's 9 hits, all accepted; none in the impact-card sections | **9 hits, 0 not yet accepted**: 1 in a plank table, 8 in `top_cards.csv`; none in the impact-card sections |

**Before and after**, per kind:
* **Before** (t25's operator dry run, 2026-10-26): advantage 0 / 0 / 39 / 2, 2 left out, 4 withheld;
  DA 9 / 4 / 29 / 0, 2 left out, 2 withheld.
* **After:** 12 DA ranks are named by a link, 11 of them from their tag and 1 from left out. No
  advantage rank changes.
* **The Economy DA's rank 2** is named `(link)`, and ranks 1 and 3 keep their tag, in the session's
  recount after the build ([above](#the-real-store-after-the-build-ac3s-prediction)). The dry run
  builds the same report and counts per kind, as t25's ruling 3 set (Deviation 4).

The other lines (affirmative methods, kritikal affirmatives, planks) are other tasks' and unchanged by
this one. The report is local: nothing is published.

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

Answered on 2026-10-26 ([the rulings](#the-pms-rulings-2026-10-26)). Kept as sent, a paste-ready relay prompt:

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
| branches-and-mechanisms | Done | In order:<br>1. the counts and the relay prompt (`8dd6b9e`);<br>2. the PM's ruling, 2a;<br>3. the hand-written goldens (`f428e6f`);<br>4. the tests, red against a skeleton (`ccd0ba0`);<br>5. the build (`672ada4`), and its simplification (`a87cd88`);<br>6. 19 mutants, and the two tests the survivors showed missing (`646428b`);<br>7. the recount on hspolicy26 and the guide's figure (`ebd0678`);<br>8. the operator's dry run (ac3), matching every prediction. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: counts before building, read-only, (a) and (b), sent to the PM with the three options | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python <scratchpad>/counts/count_branches_and_mechanisms.py config/landscape <scratchpad>/counts/word_lists_final.json` → exit 0 in 51.2 s; no process left; `debate.sqlite3` SHA-256 unchanged. [The counts](#the-counts-before-building-ac1), [the relay prompt](#questions-for-the-pm) and [the rulings](#the-pms-rulings-2026-10-26) |
| ac2: after the ruling, on synthetic fixtures, the chosen option matches hand-written golden files; tests shown failing first | PASS | **Goldens** (`f428e6f`, before any code): `test_link_lead_ins.py::test_the_impact_sections_match_the_hand_written_golden`, `::test_impact_cards_csv_matches_the_hand_written_golden`, `::test_the_rest_of_report_md_is_the_unchanged_caselists`, `test_render.py::test_rendering_the_fixture_matches_the_golden_file[report.md]`, and t22's and t25's impact-section goldens, all passing. **Red:** 42 failed against the skeleton (`ccd0ba0`, [above](#red-against-a-skeleton-ccd0ba0)). **Mutants:** 19 of 19 caught, the PM's three among them |
| ac3: the operator's dry run on hspolicy26 shows the Economy DA's mechanism as ruled, with counts before and after (operator) | PASS | [The operator's dry run](#the-operators-dry-run-ac3), 2026-10-26, 66.1 s: `Impact ranks named, advantage: 0 by a scenario, 0 by an internal link, 0 by a link, 39 by a tag, 2 by the card above; 2 left out; 4 tags withheld.` and `Impact ranks named, da: 9 by a scenario, 4 by an internal link, 12 by a link, 18 by a tag, 0 by the card above; 1 left out; 2 tags withheld.` These are exactly the predicted counts. Before: t25's dry run (DA 29 by a tag, 2 left out). The Economy DA's rank 2 `(link)` is in the session's recount after the build, since the dry run counts per kind (t25's ruling 3). No scan hit in the impact-card sections |
| branches-and-mechanisms: `uv run pytest packages/debate_core/tests/arguments/landscape` | PASS | `.venv/bin/python -m pytest -q -p no:randomly packages/debate_core/tests/arguments/landscape` on `ebd0678` → **1017 passed in 7.75s** (977 at the checkpoint; 40 new) |

## Before the report (working agreement 10)

On `ebd0678`:
* **The affected set is over two minutes.** `uv run --frozen python scripts/affected_tests.py` chose 234
  of 530 files (44.2%) from 20 changed files, in 7.0 s. t25's set was 232 files and ran past two minutes,
  so these are left to the pull request's `ci`, which runs the whole selection.
* **Within the two minutes, the changed directories and the always-run list.** One run of
  `.venv/bin/python -m pytest -q -n 6 -m "not slow and not live" -p no:randomly` under a 115 s alarm:
  * the paths: `packages/debate_core/tests/arguments/landscape`, `packages/debate_core/tests/domain`,
    `packages/debate_core/tests/integrations/landscape`, the nine
    `packages/debate_core/tests/application/test_landscape*.py`,
    `packages/debate_cli/tests/test_landscape_command.py`, `tests/smoke/test_landscape_smoke.py`,
    `tests/architecture`, `tests/specs`, `tests/scripts/test_landscape_dry_run_by_section.py`;
  * the result: **2,789 passed in 17.62s**, at load average 6.4.
* **Then `tests/config` and all of `tests/scripts`:** **1,567 passed in 71.48s**, at load average 7.5.
  No process outlived either run.
* `uv run --frozen ruff format --check .` → 1,478 files already formatted. `uv run --frozen ruff check .`
  → all checks passed.
* `uv run --frozen pyright`, bare as CI runs it → 0 errors, 0 warnings.
* `uv run --frozen lint-imports` → 18 kept, 0 broken. `scripts/check_thin_handlers.py` → 66 handlers
  within 25 statements.
* `uv run scripts/validate_specs.py` → OK, 475 files.
* `scripts/check_command_blocks.py --base origin/dev` → no `#` comments in 504 blocks, this report
  included. `scripts/docs_index.py --check-descriptions` → all 54 documents have a description.
* No `pyproject.toml`, `uv.lock`, conftest or pytest-plugin change, so no whole-selection hand-off.
* **At the checkpoint**, the affected run took 2 min 11 s: it ran without an alarm, past the two-minute
  line. That was my mistake. Its one failure was t22's load-dependent deploy-script test, which passed
  alone in 6.86 s.

## Files changed

* **`debate_core.arguments.landscape.link_chains`:** the answer labels t14's reader now refuses
  (`NOT_A_LINK`, `_LINK_ANSWERS`, `_answers_a_link`), and the docstrings.
* **`debate_core.application.landscape_report`:**
  * `_labelled_above`, one walk for the internal link and the link;
  * the link in `with_lead_in`;
  * the docstrings.
* **`debate_core.domain.landscape_report`:** `LeadInSource.LINK`, `LEAD_IN_ORDER`, `ImpactCard.link_tag`
  and `runs_through`.
* **`debate_core.arguments.landscape.render`:** the How-to-read bullet, the left-out wording, "by a link".
* **`scripts/landscape_dry_run_by_section.py`:** "by a link".
* **Tests:**
  * `arguments/landscape/test_link_lead_ins.py` (new);
  * `test_link_chains.py`: the answer labels;
  * `test_readable_impact_chains.py`: five sources;
  * `tests/scripts/test_landscape_dry_run_by_section.py`: the link count.
* **`tests/fixtures/landscape/`:**
  * `link_lead_ins/`: README, `edits.yaml`, `impact_sections.md`, `impact_cards.csv`;
  * `golden/report.md`;
  * t22's and t25's `impact_sections.md`;
  * `synthetic_caselist/README.md`.
* **`docs/guides/landscape-taxonomy.md`:** the link's place in the order, the answer labels, the example,
  and its reach on hspolicy26.
* This report.

All inside `constraints.packages`. No taxonomy, config or spec change.

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
4. **ac3's wording.** ac3 asks the dry run to show "the Economy DA's mechanism as ruled". As t25's
   ruling 3 set, the dry run prints one counts-only line per kind. The Economy DA's rank 2 `(link)` is
   in the session's read-only recount after the build ([above](#the-real-store-after-the-build-ac3s-prediction)),
   as t25's per-position view was. No per-position line was added.

## Decisions and assumptions

**For the counts:**

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

**For the build:**

7. **The link is kept on the row when it does not name it,** as t25 keeps an internal link. Nothing
   prints it then. A withheld link is never kept. `ImpactCard.link_tag` is report.md's only, so
   impact_cards.csv's columns are unchanged: the ruling names report.md and the dry run.
8. **One walk for both.** The internal link and the link are read by one function. Each is the nearest
   card above a labelled copy that is in the same position section, counted for the position, and
   labelled the role. With several copies, each a different link, the link with the most teams names the
   row, ties by tag, as t25 does.
9. **Where the answer labels are refused.** The PM's rule is applied in t14's reader itself, not only
   where a link names a rank. A link answer is then no link anywhere: in the chain table's Link row and
   in the role-label counts too.
   * On hspolicy26 that changes one DA tag in one document.
   * The scenario lines, the 12 renamed rows and every per-kind count are as predicted.
10. **What counts as an answer label:**
    * headings holding `no links`, `non unique`, `nonunique` or `not unique`, beside t14's `link
      turn(s)`, `no link`, `link defense`, `lt` and `l t`;
    * tags opening with one of those past a leading `the`, or whose words after `link(s)` call it
      non-unique (`is not unique`, `are non-unique`, …).

    `link overview` stays a link: the team's own overview of its link.
11. **Withheld links are counted in the kind's "Tags withheld" line,** since a link is a tag. The line's
    wording is t25's.
12. **The variant uses a drop-only list** (`recession`, t22's rule), to reach the internal link without
    its scenario. One effect, worked out in its README: `cedarvale crash` becomes words no list holds
    rather than a withheld name, so the DA's names withheld go from 1 to 0 in that variant.

## Operator follow-ups

1. **ac3: the dry run on hspolicy26. Done** (2026-10-26, 66.1 s; [results](#the-operators-dry-run-ac3)).
   For a later run:
   * It is the landscape service as a dry run, without `--publish`: read-only, no bucket lock, nothing
     written.
   * Expected runtime: about 75 s on the caches t22's refill left warm (t25's run: 70.7 s).
   * It prints counts and ids only, never a name, tag, text, team or school.
   * It refuses to start if a `DEBATE_*` variable is set or a `caselist pull` is running.

   From the task worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e32-t27-branches-and-mechanisms-counted-first
```

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: a DEBATE_ variable is set; unset it and paste again"; elif pgrep -f "caselist pull" >/dev/null; then echo "STOP: a caselist pull is running; wait for it to finish"; else uv run python scripts/landscape_dry_run_by_section.py --caselist hspolicy26 --snapshot 2026-10-20; fi
```

   **Success looks like:**
   * `Dry run of hspolicy26 through 2026-10-20, taxonomy 1.4.0: nothing written; 7 files planned.`
   * The scenario lines, as in t22's and t25's runs:
     * `Scenarios, advantage (… positions): 43 impact rows, 0 with a scenario, 1 names withheld; 676 of
       1164 documents …`;
     * `Scenarios, da (… positions): 44 impact rows, 9 with a scenario, 0 names withheld; 253 of 662
       documents …`.
   * **The counts after**, from the session's recount after the build:
     * `Impact ranks named, advantage: 0 by a scenario, 0 by an internal link, 0 by a link, 39 by a tag,
       2 by the card above; 2 left out; 4 tags withheld.` (no advantage row changed);
     * `Impact ranks named, da: 9 by a scenario, 4 by an internal link, 12 by a link, 18 by a tag, 0 by
       the card above; 1 left out; 2 tags withheld.`
   * **The counts before** are t25's run (2026-10-26): advantage `0 / 0 / 39 / 2`, 2 left out, 4
     withheld; DA `9 / 4 / 29 / 0`, 2 left out, 2 withheld. 12 DA rows are renamed by a link: 11 from
     their tag, 1 from left out. The Economy DA's rank 2 is among them.
   * The scan lines: t25's 9 hits, all accepted earlier (1 in a plank table, 8 in `top_cards.csv`), and
     **no hit** in report.md's `Advantages: impact cards` or `Disadvantages: impact cards` sections. The
     12 `(link)` lines quote link tags, each of which passed the report's word-level withholding.

   Paste every line back. A `Refused:` line means the run did not start, and says why.
   * If the lines match, the session records them here, marks ac3 PASS and sets the Goal to
     `Succeeded`.
   * A number that differs is a finding, not a failure: paste it and the session explains it.

2. **No publish.** The landscape republish carrying t17, t23, t24, t22 and t25 goes ahead separately, as
   briefed.

3. **The pull request, after the PM's review.** Sync once more, then open the PR, from the task worktree:

```bash
scripts/task sync v1-e32-t27-branches-and-mechanisms-counted-first
```

```bash
scripts/task pr v1-e32-t27-branches-and-mechanisms-counted-first
```

## Follow-up work

* **Branches from tags (t07 or a new E32 task),** if the coach wants them. hspolicy26 writes the Midterms
  DA's branch in its uniqueness tags, not its headings. As ruled, the counts answer the question for now.
* **The Economy DA and the Taxes DA:** the coach's question, [above](#for-the-coach).
* **The chain table's Link row** now also refuses answer labels (Decision 9). On hspolicy26 one tag
  changes. If the refused card was its DA's most-read link card, that DA's Link row shows the next one.
  The dry run does not print the chain table, so it shows at the republish.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-26

**Notes:**

The counts answered the coach's two questions honestly, and 2a was built as ruled.
1. **ac1 passes.**
   * Both readings of a branch were counted. Nesting gives 0, and file order gives no outer heading
     two teams use, so the branch lives in the tags.
   * The mechanism counts show one shared financing link, not separate DAs.
   * The word lists were screened as ruled, with 0 scan hits. List 1 is empty.
2. **ac2 passes.**
   * The goldens were written by hand before any code, with a variant reaching `(link)` and a
     withheld link.
   * Red first: 42 failed against a skeleton. The passes are must-not cases, each named.
   * 19 mutants, the PM's three among them. Two survived the first pass, and the tests they showed
     missing were added in `646428b`.
3. **The recount after the build** matches every prediction: 12 DA rows by a link, 1 left out, no
   advantage row changed, and the Economy DA's rank 2 `(link)`.
4. **The answer labels.** t14's reader read one link-turn tag as a link (`the link turns`). Widening
   the reader's refusals is accepted, and so is applying them in the reader itself (Decision 9), so a
   link answer is no link anywhere.
   * `a87cd88` removed the entries no test could tell from their absence, as working agreement 8
     asks.
5. **Deviations 1 to 4 accepted.** The PM records the word-list clarification and ac3's per-kind
   reading in the next batch.
6. **Decisions 1 to 12 accepted.**
7. **"For the coach"** is relayed to the coach by the PM. Branches from tags stay unfiled unless the
   coach asks.
8. **The checkpoint's affected run without an alarm** is self-reported. The rule stands: the alarm
   goes on the interpreter.
9. **The affected set** (234 files) is left to the PR's `ci` under agreement 10. The changed
   directories, `tests/config`, `tests/scripts` and the always-run list passed, and the static checks
   are clean.

No re-review is needed. When the operator's dry run matches, the session records it, marks ac3 PASS
and sets the Goal to `Succeeded`, and the PR merges in full. A number that differs comes back to the
PM first.

## PM review, second

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-26

**Notes:**

1. **ac3 passes.** The operator's dry run (66.1 s) matched every predicted line:
   * DA: 9 by a scenario, 4 by an internal link, 12 by a link, 18 by a tag, 0 by the card above; 1
     left out; 2 tags withheld;
   * advantages unchanged;
   * the scenario lines as in t22's and t25's runs;
   * no scan hit in the impact-card sections.
2. **The Goal is `Succeeded`.**

The PR merges in full after the sync.
