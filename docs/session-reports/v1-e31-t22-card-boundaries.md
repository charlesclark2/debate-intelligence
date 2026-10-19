# Session report: v1-e31-t22-card-boundaries

| | |
|---|---|
| Task | `v1-e31-t22-card-boundaries` — Bodies too long to be one card, and two cards stored as one |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t22-card-boundaries.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t22-card-boundaries.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t22-card-boundaries` |
| Session status | IN PROGRESS: the counts (ac1) are in; the sample (ac2) is built and waits on the operator. No parser rule is changed <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The PM's order is followed: counts, then the sample, then the PM's ruling, and only then a parser
change. The operator ran the counts on the `2026.10.18-docx-5` store on 2026-10-19
([The counts](#the-counts)). The sampler is built and tested, and its command is with the operator
([Operator follow-ups](#operator-follow-ups), step 2). When its tallies are in, the PM gets the
tallies, what each kind turns out to be, and the rules proposed. No parser rule, version or
fixture has changed.

**What the counts say, before the sample:**

1. **Long bodies are common, and the parser did end most of them where the file put a heading.**
   12,048 stored cards, 2,994 distinct texts, are over 3,000 words: 3% to 5.5% of each caselist's
   cards. 64% end at a tag in a debate style and 21% at a pocket, hat or block. Only 142 end at a
   cite and 531 at the end of the file.
2. **Of the PM's four things to check, two are small and two are for the sample.**
   - *Files with no styles:* 117 cards (1%).
   - *Files that write no tags:* 44.
   - *A whole file that is one card:* 3.
   - *Tags written in body style* (a short line above a cite-shaped paragraph): at most 1,174 (10%).
   - *Cards separated only by their cites:* at most 1,029 (9%).
   - *Prose with nothing cut* (under 5% marked up): 1,600 (13%), 667 of them in hspf26, a quarter of
     its long bodies.
3. **Most long bodies (8,245, 68%) are marked up and hold no cite-shaped paragraph.** They are either
   one long card or cards whose boundaries look like nothing the count looks for. The sample decides.
4. **"Cite-shaped" is probably loose.** 60% of the cite-shaped paragraphs were read as small-print
   body, and only 7% as a cite the body kept. A small-print line of 400 characters or fewer that
   opens with a name and a year is first read as a cite, so most of these are longer: likely
   sentences of a source that name another near their start. The two "inside" kinds are upper
   bounds until the sample says otherwise.
5. **Two cards in one body is common too.** 4,560 distinct texts (7% to 8% of the full texts in each
   caselist, 1.8% of openev's) hold two shorter bodies whole that share no text. They are carried by
   37,128 stored cards, about eight each, so these are much-disclosed cards. 3,297 hold exactly two,
   and in 4,142 the smaller of the two is 64 words or more. That is the shape of one long card that
   teams cut at different places, as much as of two cards stored as one. The sample decides.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `card-boundaries`: Card boundaries | In progress | ac1 done; ac2's sampler built, its run with the operator |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: before any rule changes, the operator-run counts for (1) and (2) per caselist, with (1) split by ending rule and by files that write tags | PASS | The operator's run of 2026-10-19 on `2026.10.18-docx-5`, all four caselists, `exit 0`, nothing not reproduced: [The counts](#the-counts). No rule has changed |
| ac2: a sample of each, through v1-e31-t21's sampler, tallies only | NOT RUN | `scripts/sample_card_boundaries.py` built and tested ([The sample](#the-sample)); the operator's command is step 2 |
| ac3: each defect has a synthetic fixture shown failing first; tag and cite precision and card boundaries do not fall | NOT RUN | After the PM's ruling |
| ac4: `parser_version` bumped; the operator's re-parse records (1) and (2) before and after | NOT RUN | After ac3 |
| Node: `uv run pytest packages/debate_core/tests -k "docx or parser"` | NOT RUN | Run before the report, with the PM's list of 2026-10-19 (working agreement 10) |

## The counts

The operator ran `scripts/count_card_boundaries.py` on 2026-10-19 from this worktree at `0323438`,
read-only, over the dev data directory's `2026.10.18-docx-5` store: 11,154 sources, 6.3 minutes in
all (88, 45, 219 and 28 seconds by caselist). The totals below are the four caselists' figures
summed by hand. Every card over the line was parsed again and reproduced exactly: 0 not reproduced,
0 without a blob.

### (1) Bodies too long to be one card

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Cards in the store | 75,399 | 50,246 | 101,826 | 8,081 | 235,552 |
| **Cards over 3,000 words** | **4,130** | **2,705** | **4,946** | **267** | **12,048** |
| Distinct texts | 969 | 635 | 1,199 | 191 | 2,994 |

**By what ended the card, and whether its file writes tags** (ac1's two splits):

| Ended by | hsld26 | hspf26 | hspolicy26 | openev | Total | In a file with no tags |
|---|---|---|---|---|---|---|
| A tag in a debate style | 2,801 | 1,356 | 3,326 | 177 | 7,660 | 0 |
| A pocket, hat or block heading | 686 | 703 | 1,117 | 82 | 2,588 | 6 |
| A tag with no cite or body under it | 274 | 177 | 260 | 5 | 716 | 0 |
| The end of the file | 230 | 159 | 140 | 2 | 531 | 9 |
| A tag the classifier guessed from its formatting | 81 | 223 | 47 | 0 | 351 | 0 |
| A cite, starting a card with no tag | 35 | 85 | 21 | 1 | 142 | 29 |
| An analytic | 23 | 2 | 35 | 0 | 60 | 0 |
| **In a file that writes tags / no tags** | 4,125 / 5 | 2,670 / 35 | 4,942 / 4 | 267 / 0 | **12,004 / 44** | |

**By what is inside** (first that applies), and how many are in a file that uses no debate style:

| Inside | hsld26 | hspf26 | hspolicy26 | openev | Total | No debate style |
|---|---|---|---|---|---|---|
| A short line above a cite-shaped paragraph | 256 | 449 | 439 | 30 | 1,174 | 17 |
| A cite-shaped paragraph, no short line above | 163 | 192 | 647 | 27 | 1,029 | 17 |
| No cite inside, marked up (5% or more) | 3,351 | 1,397 | 3,307 | 190 | 8,245 | 68 |
| No cite inside, plain prose (under 5%) | 360 | 667 | 553 | 20 | 1,600 | 15 |
| **Files using no debate style** | 52 | 55 | 10 | 0 | **117** | |

**The rest:**

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| 3,001 to 5,000 words | 2,357 | 1,342 | 3,294 | 197 | 7,190 |
| 5,001 to 10,000 words | 1,694 | 1,322 | 1,400 | 65 | 4,481 |
| Over 10,000 words | 79 | 41 | 252 | 5 | 377 |
| In a file of 1 card / 2 to 5 / 6 to 20 / 21 or more | 0 / 76 / 2,939 / 1,115 | 1 / 29 / 1,482 / 1,193 | 2 / 8 / 1,069 / 3,867 | 0 / 0 / 20 / 247 | 3 / 113 / 5,510 / 6,422 |
| Marked up: none / under 5% / 5% or more | 1 / 393 / 3,736 | 19 / 801 / 1,885 | 4 / 666 / 4,276 | 1 / 25 / 241 | 25 / 1,885 / 10,138 |
| With a tag and a cite / a tag, no cite / a cite, no tag | 3,944 / 123 / 63 | 2,322 / 240 / 143 | 4,820 / 101 / 25 | 255 / 9 / 3 | 11,341 / 473 / 234 |

**The rule that read each cite-shaped paragraph** (paragraphs, not cards; 4,844 in all): small-print
body 2,914; marked-up body 1,294; a cite guess the body kept 329; read as nothing 231; prose 41; a
paragraph style (three families) 35.

### (2) Two cards stored as one

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Distinct full texts | 16,774 | 14,561 | 25,701 | 6,400 | 63,436 |
| **Holding two bodies that share no text** | **1,212** | **1,207** | **2,023** | **118** | **4,560** |
| Stored cards carrying them | 11,013 | 6,280 | 19,666 | 169 | 37,128 |
| Holding two that do not overlap (the looser test) | 1,430 | 1,346 | 2,255 | 142 | 5,173 |

Of the 4,560:

| | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| Holder 0 to 299 words / 300 to 999 / 1,000 to 2,999 / 3,000 or more | 42 / 324 / 631 / 215 | 45 / 500 / 434 / 228 | 122 / 802 / 800 / 299 | 7 / 45 / 46 / 20 | 216 / 1,671 / 1,911 / 762 |
| Bodies sharing nothing: 2 / 3 to 5 / 6 or more | 913 / 289 / 10 | 916 / 268 / 23 | 1,385 / 598 / 40 | 83 / 32 / 3 | 3,297 / 1,187 / 76 |
| The smaller of the two: 64 words or more / under 64 | 1,102 / 110 | 1,049 / 158 | 1,876 / 147 | 115 / 3 | 4,142 / 418 |
| Holder also over the 3,000-word line | 207 | 221 | 292 | 17 | 737 |

The holder bands count words as the clusterer reads them and the 3,000-word line counts words
between spaces. That is why 762 holders are in the top band and 737 are over the line.

## The counting script

`scripts/count_card_boundaries.py`, with the logic in
`packages/debate_core/src/debate_core/evidence/card_boundaries.py`. Read-only; it prints counts
and rule-family names only.

**(1) Bodies too long to be one card.** Every stored card over 3,000 words, by whitespace words.
The store keeps no paragraphs, so each source holding one is parsed again from its blob by this
checkout's parser (still `docx-5`), and the card is described by its file's paragraphs. A card the
parse does not give back, with the same range and the same exact fingerprint, is counted as
`not_reproduced` and not described. The splits:

- **By ending:** the first paragraph after the card that the parser read as something: a tag in a
  debate style, a tag guessed from bold at a tag size, a pocket, hat or block, a tag with nothing
  under it, an analytic, a cite (starting a card with no tag), or the end of the file. The spec's
  split by ending is crossed with the split by files that write tags.
- **By whether the file writes tags at all:** any tag, including one demoted for having no card
  under it.
- **By whether the file uses any debate style:** a paragraph style the profile maps to a unit, or
  the cite character style. This is the PM's "files with no styles at all".
- **By what is inside** (first that applies), for the PM's things to check:
  1. *a short line above a cite-shaped paragraph*: a tag typed in body style above a cite the
     parser did not read;
  2. *a cite-shaped paragraph with no short line above*: cards separated only by their cites;
  3. *no cite inside, marked up* (at least 5% of characters underlined, emphasised or
     highlighted): one long card, or cards with neither tag nor cite between them;
  4. *no cite inside, plain prose*: a PF case or a speech written out.

  "Cite-shaped" means a name and a year within the first 40 characters of a paragraph of 2,000
  characters or fewer, once the body has begun. A "short line" is at most 300 characters, the
  classifier's heading length, and is not itself cite-shaped. The rule each cite-shaped paragraph
  was read by is tallied by its family.
- Also by word band, cards in the file, marked-up share, and whether the card has a tag and a cite.

**(2) Two cards stored as one.** Every distinct full body that holds two or more shorter bodies
whole that share no five-word run, by `CutIndex.containers` (the clusterer's own "holds": at least
as large, holding an end of the shorter, and containing nine-tenths of it or all of it but for one
word; a copy is not held). Counted in distinct texts and in the stored cards that carry them. The
looser count, two held bodies that do not overlap (under three-tenths shared), is beside it,
because that is the test `v1-e31-t20` refuses a witness by. Split by holder word band, whether the
smaller of the two is short (under 64 words), how many held bodies share nothing, and whether the
holder is also over 3,000 words.

`--save-candidates FILE` writes the store positions of what was counted (digests and indices, no
text) so the sample can draw from them without counting again. The script refuses a path inside
the repository or inside the data directory, which belongs to the store tooling (the PM,
2026-10-19). The path is `~/t22-card-boundary-candidates.jsonl`, the constant `CANDIDATES` that the
sampler reads by default.

### Tests, and the checks shown failing

- `packages/debate_core/tests/evidence/test_card_boundaries.py` and
  `tests/scripts/test_count_card_boundaries.py`, on invented `.docx` files, numbered-word bodies and
  an invented store of six sources: a long card, a holding file, one source with no blob, and three
  whose blobs differ from what was stored, one per half of the "reproduced" check.
- **Mutation.** One textual change per run, both test files, a fresh `HYPOTHESIS_STORAGE_DIRECTORY`
  each run, the file restored from saved bytes and checked, `git status` checked after each batch.
  The first pass found 9 survivors:
  - six gaps, each given a test: a 300-character line above a cite, a paragraph left in `Normal`,
    the "not overlapping" candidates group, each half of the reproduction check, a marked-up share
    between 0 and 1%, and a card with no cite;
  - three checks no input reaches, deleted rather than tested: a completeness filter (a cite-only
    card has no words), keeping bodies of full cards only, and a unit check on the line above a
    cite (once a body has begun, a tag or a cite would have closed the card).

  Also, the word-count reproduction check became an exact-fingerprint check. **Final run on
  `9bc4f76`: 47 mutants, 47 caught**, 43 by assertion and 4 by a "did not raise" or an exception
  from a refused option. One caught mutant had written `scripts/candidates.jsonl` before failing.
  It was deleted, and the test now removes such a file itself.

## The sample

`scripts/sample_card_boundaries.py` draws from the positions the count saved. It asks one question
with one key per item, through `v1-e31-t21`'s sampler: `compare_card_clusters.read_key` (one key,
no Enter, keys pressed early discarded), its rule that card text goes only to a terminal, the
screen cleared between items and at the end, and closing tallies appended to a file.

**The plan, 60 items:**

| Stratum | Population (distinct texts, a caselist each) | Drawn | Question and keys |
|---|---|---|---|
| Long body: a short line above a cite-shaped paragraph | from the 1,174 cards | 10 | "What is this body?" `o` one card, `s` several cards stored as one, `n` no cards (a case, a speech, notes or an article not cut), `u` unsure |
| Long body: a cite-shaped paragraph, no short line above | from the 1,029 | 10 | the same |
| Long body: no cite inside, marked up | from the 8,245 | 10 | the same |
| Long body: no cite inside, plain prose | from the 1,600 | 10 | the same |
| Two cards in one: body under 1,000 words | from about 1,887 | 10 | "The two marked parts, A and B, share no text. Are they two cards, or one card cut twice?" `t` two cards (a boundary the parser missed), `o` one card cut twice, `u` unsure |
| Two cards in one: body of 1,000 words or more | from about 2,673 | 10 | the same |

Ten a stratum tells "mostly" from "often", about ±15 points at 95%, and no finer. Each stratum is
drawn by distinct text, so a card disclosed fifty times is as likely as one disclosed once. A text
is drawn once in all, and the order is shuffled, so it does not say which stratum an item is from.

**What an item shows:** the card's range as this checkout's parser reads it from the source's blob,
one line a paragraph. Each line gives what the parser read the paragraph as (`tag`, `cite`, `body`,
or `NOTHING` in bold: where a tag typed in body style would be), its words, its share underlined or
highlighted, the count's marks (◆ names a source at its head, ▸ a short line above one), and its
opening and end. A body holding two cards also gives each paragraph's share in A and in B, with A
the part the body holds first. Long runs of body paragraphs are shown as a count. Kept in view: the
first four and last three paragraphs, every line read as nothing or of 30 words or fewer, every
marked line, and every line where A gives way to B, each with the lines beside it. The item ends
with the paragraph that ended the card. An item the parse does not reproduce is skipped and
counted.

**Tests:** `tests/scripts/test_sample_card_boundaries.py`. The plan; the draw (by stratum, one draw a
text, the same again by seed, blind order); what an item shows, row by row; the answering loop
(each item's own keys, `q` stops); the tallies, counts only; an end-to-end run on an invented store
whose positions the count script saved; refusals of a non-terminal and of a tallies file inside the
repository or the data directory; a drawn item not reproduced; and A told from B whichever order the
count named them. **Mutation:** 15 mutants, 8 caught at once. The 7 survivors were the draw's filter
and band edge, rows kept, stopping on `q`, the reproduction check, A before B, and where A gives way
to B. Each was given a test, and all 7 are caught on re-run: 22 runs in all.

## Files changed

- `packages/debate_core/src/debate_core/evidence/card_boundaries.py` (new): the per-paragraph
  reading of a card's range (`paragraphs_inside`, `ending_of`), the long-body reading, the bodies
  holding two cards, and their tallies.
- `packages/debate_core/tests/evidence/test_card_boundaries.py` (new).
- `scripts/count_card_boundaries.py` (new) and `tests/scripts/test_count_card_boundaries.py` (new).
- `scripts/sample_card_boundaries.py` (new) and `tests/scripts/test_sample_card_boundaries.py` (new).

## Deviations from the spec

1. **The scripts' tests are in `tests/scripts`, outside `constraints.packages`**, which lists
   `scripts` but not `tests/scripts`, where every script's tests live. Agreed by the PM, 2026-10-19.
2. **The sample is a new script that uses `v1-e31-t21`'s sampler's parts, not a new mode of
   `compare_card_clusters.py sample`.** t21's sample shows a pair of texts and asks "same card?".
   Neither question here is about a pair, and the paragraphs read as nothing, where a missed tag
   would be, are in no stored text: they need the source parsed again, as `v1-e31-t19`'s sampler
   did. It takes t21's key reader, terminal rule, screen clearing and tally file, as t19's did.

## Decisions and assumptions

- **Words are whitespace words** for the 3,000 line (the spec's "words"). The holder bands in (2)
  are the clusterer's matching words, since (2) is the clusterer's measure.
- **The long-body reading runs on this checkout's parser.** It is `docx-5`, the store's version,
  and each card must come back with the same range and body or it is counted apart. The count found
  none that did not.
- **The "inside" kinds are guesses to be sampled, not verdicts.** The 5% marked-up line and the
  300-character short line are stated in the code.
- **openev is counted with the three caselists,** each on its own.
- **The sample draws by distinct text,** not by stored card. The pilot indexes one result per card
  cluster, so what a student meets is the text, not how often it was disclosed.
- **Two cards in one is sampled in two bands of the holder's length, split at 1,000 words,** near
  the median (about 1,887 below and 2,673 above: the count's bands read the clusterer's words and
  the sampler's band words between spaces, so the sampler's own population line is the exact one).
  A short holder is the shape of `v1-e31-t11`'s false join; a
  long one is closer to (1).

## Operator follow-ups

### 1. The counts (ac1): done, 2026-10-19

Run after A5 of `v1-e31-t20`'s list, once the local store was `docx-5`. Its figures are in
[The counts](#the-counts). The candidates are at `~/t22-card-boundary-candidates.jsonl`, outside
the data directory.

### 2. The sample (ac2): about 2 minutes to start, then about 20 to 30 minutes answering

Read-only. It reads `~/t22-card-boundary-candidates.jsonl`, the store and the blobs, and appends
counts to `~/t22-card-boundary-sample-tallies.txt`. Run it in a terminal window at full width
(120 columns or more). It shows card text on the screen only. One key per item, no Enter; `q`
stops and keeps the tallies so far.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e31-t22-card-boundaries
git log --oneline -1
uv run python scripts/sample_card_boundaries.py --expect-version 2026.10.18-docx-5 --seed 20261019 --save-tallies ~/t22-card-boundary-sample-tallies.txt
cat ~/t22-card-boundary-sample-tallies.txt
```

Success: the last lines start `Card-boundary sample, seed 20261019: drew 60 of 60 planned`, with
one line a stratum and the answers under each. Paste those lines back, which are counts only, with
a few words of what you saw in any stratum where the answers were mixed. No card text. A line
`not reproduced ... skipped` should not appear: if it does, paste it too.

**How to read an item.**

- *A long body:* look for lines read as `NOTHING` or marked ▸ / ◆ partway down that are a tag and
  a cite: `s`. A single article cut at length: `o`. A case, a speech, notes or an article with
  nothing cut: `n`.
- *Two cards in one:* look at what stands between A's paragraphs and B's. A tag or a cite, or a
  change of subject that two cards would have: `t`. The same article running on: `o`.

## Follow-up work

None yet.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
