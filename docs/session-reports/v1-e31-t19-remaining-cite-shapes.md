# Session report: v1-e31-t19-remaining-cite-shapes

| | |
|---|---|
| Task | `v1-e31-t19-remaining-cite-shapes` — The cite shapes the parser still misses, counted first |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t19-remaining-cite-shapes.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t19-remaining-cite-shapes.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t19-remaining-cite-shapes`, rebased with `scripts/task sync` onto `origin/dev` at `2f01f1b` |
| Session status | PARTIAL: counts, rulings, sample, rules, version and documents are done. Two criteria wait on the operator: the re-parse (ac4, second half) and the Word check for (7) (ac5, second half). The Goal stays `InProgress` |

## Summary

Every shape was counted first, read-only over the dev data directory as `v1-e31-t12` counted, and
the PM ruled on the counts before any rule changed. Four rules are built and one hold is changed:
a cite behind a first name or a title (1); the cite and body rules read through a paragraph style
that maps to no unit, never the heading rules (2, broad, by PM amendment); a highlighted cite where
a cite stands with a body below (3); `v1-e31-t09`'s cite-style hold asks for a styled name and year
at the head (4); and a short cite written `Okonkwo ‘26` with a left quote is read (6). (5) is
measured and left, as ruled.

The coach's sample of 70 items found no paragraph taken wrongly by any rule. Over the same 11,148
sources the new parser `2026.10.18-docx-5` reads a cite for 10,324 more cards (205,589 to 215,913),
tagged cards with no cite fall from 28,054 to 19,544, and 218,218 of the 233,643 stored cards are
identical in every field. The labelled PR subset's cite precision rises from 0.957 to 0.969 and its
recall from 0.500 to 0.705.

**Look at first:**

1. **(6) is twenty times my estimate.** I estimated 415 more short cites from the 131 files with
   `Okonkwo ‘26` alone on a line. 9,602 cards hold a short cite written with a left quote now: most
   are cites that open `Okonkwo ‘26 [...]`. It is the same rule the PM approved, measured in full.
2. **The cause of (6) is U+2018, not U+2019.** The spec's example is `’`; those lines were read
   already. Word types `‘` for an apostrophe after a space.
3. **The re-parse waits for `v1-e31-t20`'s rebuild (its step 13).** Operator follow-ups, below.
4. **(7) is not counted.** The operator's check in Word has not come back.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cite-shapes`: Remaining cite shapes | Done but for the two operator steps | `uv run pytest packages/debate_core/tests/integrations/docx_parser` → `860 passed, 2 xfailed in 3.01s` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: before any rule changes, the counts for (1) to (5), and for each shape the share a proposed rule reaches and the share it would wrongly take, on a sample checked by the coach | PASS | Counts sent to the PM before any rule change and ruled on 2026-10-18 ([The counts](#the-counts)). Reach in the counts: (1) 4,864 of 8,250 (59%); (2) 1,268 cites and 12,744 body paragraphs; (3) 488 of 645 (76%); (4) 25 of 26. Wrongly taken on the coach's sample (seed 20261018, 70 items, 710 s): 0 of 10, 0 of 14, 0 of 10, 0 of 7 ([The coach's sample](#the-coachs-sample)) |
| ac2: each of (1) to (4) built or ruled out on those counts; each built rule has synthetic fixtures shown failing first; the labelled evaluation's cite precision does not fall | PASS | All four built. Red at `0441a0e`: `36 failed, 196 passed`, every failure an `AssertionError` ([Red then green](#red-then-green)). `uv run python scripts/run_parser_eval.py --tier pr-subset`: cite precision 0.957 → 0.969, recall 0.500 → 0.705; tags, evidence and card boundaries unchanged. The full tier is not corrected yet and was not run |
| ac3: (4): the hold no longer holds a paragraph whose style marks no name and year at its head, and t09's 300-word fixture changes to match, by test | PASS | `test_first_corpus_parse_findings.py::TestACiteThatDoesNotOpenTheBody::test_a_paragraph_of_300_words_with_a_run_in_the_cite_character_style_is_the_body` (both positions `FULL`, the paragraph is the body), and `TestTheCiteStyleHold` (3 tests, a styled name and year at the head still holds). Both failed first at `0441a0e` |
| ac4, first half: `parser_version` is bumped | PASS | `2026.10.18-docx-5`. `TestTheParserVersion` → 3 passed; they failed first at `8b89d2d` (`3 failed`), and a mutant reverting the version fails 13 tests |
| ac4, second half: the operator's re-parse records the cards whose cite changed in `docs/data/caselist-parse-report.md` | **NOT RUN** | Operator-run, after the merge and after `v1-e31-t20`'s rebuild (step 13) has finished. The report holds the read-only side-by-side, marked as that. [Operator follow-ups](#operator-follow-ups), step 2 |
| ac5, (6): the short cite read from the line above, curly or straight apostrophe, by synthetic fixture shown failing first, with the corpus count of cards it fills | PASS | `TestAShortCiteWithALeftQuote`: U+2018 failed first at `0441a0e`, U+2019 and straight passed before and after. Corpus: 9,602 cards hold a short cite written with a left quote, none before; 9,547 cards that keep their range gain a short cite in all |
| ac5, (7): if the operator confirms the tag is in the document, counted and fixed; if not, the report says so | **NOT RUN** | The operator's Word check has not come back. Located read-only: the file of t12's step 6 for `heuristic-cite-line-bracketed`, cards 2 and 3 of 16; above each cite a short underlined line at reading size, read as body. Nothing counted or changed. [Operator follow-ups](#operator-follow-ups), step 1 |
| Node: `uv run pytest packages/debate_core/tests/integrations/docx_parser` | PASS | `860 passed, 2 xfailed in 3.01s` |
| Default suite, in eighths, on the rebased branch | PASS but one known failure | `uv run --frozen pytest -n auto -m "not slow and not live" --part K/8`: 1,051; 1,055; 1,052; 1,045; 1,041; 1,050 and 1 xfailed; 1,050 and 1 failed; 1,049 and 1 xfailed. 8,393 passed. The failure is `tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline`, which fails on this Mac until the baseline is written at the end of labelling (known; not investigated) |
| Static checks and gates | PASS | `pyright` 0 errors (whole repository, after the last format); `ruff check .` and `ruff format --check .` clean, 805 files; `lint-imports` 12 kept; `check_thin_handlers.py`, `check_links.py`, `check_command_blocks.py`, `docs_index.py --check-descriptions`, `export_schemas.py --check` OK; the slow parser timing test `1 passed in 4.49s` |
| `uv run scripts/validate_specs.py` | PASS | `OK: 366 files, 38 epics, 308 tasks, 20 releases`. Phase `InProgress` |

## The counts

Measured 2026-10-18, read-only, as t12 measured: the 11,148 parsed DOCX sources of the stored
`2026.10.12-docx-3` (233,643 cards) re-parsed in place from their blobs by scratch scripts outside
the repository and the data directory. Counts, lengths, formatting flags and rule ids only. Every
total over all cards equals the stored figures of the 2026-10-16 re-parse. The full tables are in
[`docs/data/caselist-parse-report.md`](../data/caselist-parse-report.md#the-remaining-cite-shapes-v1-e31-t19).

| | Shape | Count | Spec's figure | Ruling |
|---|---|---|---|---|
| 1 | A cite behind a first name or a title | 8,250 tagged cards (6,204 read as nothing, 2,046 as body) | 7,200 | Built, on the sample |
| 2 | A cite in a paragraph style that maps to no unit | 1,355 paragraphs (1,255 by an alias); in 955 the body below is in the same style | 957 | Built broad: the cite and body rules, never the heading rules (PM) |
| 3 | Highlighted cites | 645 (599 bold opening, 38 styled head, 8 one bracket) | 593 | Built, on the sample |
| 4 | t09's cite-style hold | 26 guesses held with the style on no name and year at the head | 19 | Built as ruled (PM) |
| 5 | Short plain lines inside a body | 91,345 read as nothing; 43,488 between two body paragraphs of one card, in 15,796 cards | not measured | Left here (PM): the task merged with `v1-e31-t23` rules on it |
| 6 | A short cite on its own line | 296 short lines with U+2018; 9,602 cards fill | 4 cards seen | Built (PM approved) |
| 7 | Two cards with no tag | Located; waiting on the operator | 2 cards | Not counted |

The growth over the spec's figures is the 1,575 sources imported on 2026-10-14.

## The rules

| Rule | Where | Rule id on the paragraph |
|---|---|---|
| A line where a cite stands whose name and year start within 40 characters behind one to three capitalised words or a title, the name and year (or the opening) in bold or followed by one bracket; no highlighting, no cite-style run, 2,000 characters or fewer | `style_classifier.is_a_cite_behind_a_first_name_or_title`, asked by the parser's assembly | `assembly-cite-behind-a-name-before-the-body:…` |
| A paragraph style that maps to `OTHER` lets the cite-run-style, wiki, cite-line, long-cite-line and body rules see through it; never the outline-level or bold-heading rules, and never in a table cell or a blank paragraph | `style_classifier.classify_paragraph`, `_through_an_unmapped_style` | `<rule>:<style rule>`, for example `heuristic-prose-paragraph:verbatim-alias-id:NormalWeb` |
| A highlighted paragraph with a cite's shape (bold name and year at the head, one bracket after the year, or the cite style on a name and year at the head), where a cite stands and the next paragraph that says anything is body | `style_classifier.is_a_highlighted_cite`, asked by the assembly | `assembly-highlighted-cite-before-the-body:…` |
| A guessed cite is held by its cite style only when the style marks a name and a year at its head | `parser._the_cite_style_marks_its_source` (was `_carries_a_cite_style`) | The existing `assembly-cite-guess-…` ids |
| A left quote directly before a digit is read as `’` wherever the profile's cite patterns are matched; the short cite is cut from the cite as written | `style_classifier.for_matching`, `parser._short_cite` | Unchanged |

## The coach's sample

`scripts/sample_cite_shapes.py`, run by the operator on 2026-10-18 from this worktree at the
commit then `41bb6e8` (now `f261a2f`, the same tree): seed 20261018, 70 items, drawn blind and
shuffled across rules and sides, one key each, 710 seconds answering. The three new rules ran
behind a flag only the sampler switched on, so the sample judged the code that ships; the flag was
removed once the tallies were in (`8b89d2d`).

| Rule, side | In the corpus | Asked | Yes | No | Unsure | Wrong takes |
|---|---|---|---|---|---|---|
| (1) taken, read as nothing / as body before | 4,176 / 1,013 | 8 / 2 | 8 / 2 | 0 | 0 | 0 of 10 |
| (1) left, read as nothing / as body | 2,186 / 1,110 | 7 / 3 | 4 / 3 | 0 | 3 / 0 | (misses: 7 of 10 are cites) |
| (2) taken as cites / as body | 1,339 / 12,852 | 6 / 8 | 6 / 8 | 0 | 0 | 0 of 14 (the PM's stop line: 2 of 8 bodies) |
| (2) left as nothing | 2,162 | 6 | 2 | 3 | 1 | (misses: 2 of 6) |
| (3) taken / left | 493 / 221 | 10 / 10 | 10 / 10 | 0 | 0 | 0 of 10 (misses: 10 of 10 left are cites) |
| (4) re-read as body / still held | 25 / 7 | 7 / 3 | 0 / 3 | 7 / 0 | 0 | 0 of 7 ("no, not the cite" is right for a body) |

Each item asked "Is the marked paragraph this card's cite, or a line of it?", except (2)'s bodies
("part of the card's text?") and (2)'s left side ("a cite, or part of a card's text?"). Ten a
side tells "mostly right" from "often wrong", about ±15 points at 95%, and no finer.

## Red then green

Commit ids are after the sync onto `2f01f1b`.

| Commit | What it adds | Tests |
|---|---|---|
| `4673409` | The PM's amendment to item (2) in the spec | |
| `0441a0e` | The tests, with the rules under review asked for through an inert flag; t09's fixture expects the body | **36 failed, 196 passed**, every failure an `AssertionError`. Package suite: 36 failed, 5,758 passed, 2 xfailed |
| `981f819` | (4) and (6), and t12's mid-paragraph hold test restated | 28 failed (the flagged rules), 204 passed |
| `8ebb9d7` | (1), (2), (3) behind the flag | 65 passed |
| `f261a2f` | The sampler and its tests | 10 passed |
| `8b89d2d` | The rules switched on for good; t12's three highlighting tests restated; version tests | Version: **3 failed** |
| `734afa1` | `2026.10.18-docx-5`; ten structural expectations' `parser_version` line | 3,374 passed but the known baseline test |
| `e76b932`, `6da8609` | Edge tests the mutation review asked for; two unreachable checks deleted | |
| `f5f1ab1` | The parse report and the store document | |

**What cannot fail first, and is not claimed to:** the tests named "what the rule leaves", "is
left as it was" and "changes nothing", and the U+2019 and straight-apostrophe cases of (6). They
have the same answer with and without the rules; the mutants below show each is the other side of
a condition. The sampler is a new script, so its tests could only fail as a missing module; the
mutants are its evidence.

## Mutation testing

On `6da8609`, the final source. Each run: one textual change on one line, the nine test files that
read these rules (1,063 tests, 1.6 to 6 s a run), a new empty `HYPOTHESIS_STORAGE_DIRECTORY`, the
file restored from saved bytes and checked, and `git status --porcelain` empty after each batch.
Four batches of under two minutes.

**54 mutants, 54 caught, every one by assertion failures.** None errored or failed at collection.

| Rule | Mutants | Each condition dropped or moved |
|---|---|---|
| (6) a left quote | 9 | `for_matching` changes nothing; a left quote anywhere; each of the five pattern sites reads the text as written; the short cite matched on, or cut from, the wrong text |
| (1) behind a first name | 18 | never takes; anywhere, not only where a cite stands; the bound ±1; highlighted taken; a cite-style run taken; the head ±1; anything before the name; no title list; a sentence opener as a first name; three words to two and to four; a word of any case; the opening's bold, the name's bold, any bold not needed; the bracket shape never taken |
| (3) highlighted | 11 | never takes; no body need follow; anything after it is a body; a blank line ends the look-ahead; need not be highlighted; the styled bound +1; the styled shape never taken; the bound +1; a sentence opener as an author; the bold opening, or the bracket, not counted |
| (2) an unmapped style | 7 | never seen through; every style seen through; a table cell, or a blank paragraph, seen through; the body rule left out; the heading rule let in; the style left out of the rule id |
| (4) the hold | 2 | never holds; any cite-style run holds, as before |
| The version | 1 | reverted: 13 tests |
| The sampler | 6 | read as nothing and as body swapped; an unmapped style's cite counted as body; the draw not shuffled; more than planned drawn; answers tallied under one stratum; tallies allowed inside the repository |

**What the first pass found** (56 mutants on `e76b932`): four survived.

- **Two checks no input reaches, deleted:** the name and year at the very front (an empty prefix is
  no first name already) and the visible-run guard on the bold stretch (a name and year always has
  one).
- **Two gaps, each given a test:** a highlighted cite whose year follows a left quote, and a draw
  where a stratum has more candidates than its plan.

Before that, a review of every condition against the tests added ten edge tests (`e76b932`): a left
quote behind a first name, a title before three names, part of the name in bold, the cite style on
a phrase further in, a blank line before the body, the highlighted shape's own contract, the
unmapped style's table and blank-mark guards, a left quote inside a name, the wiki guess with a
left quote, and a shuffled draw.

## The corpus, before and after

Read-only, the new parser over the same bytes as the stored `2026.10.12-docx-3` cards. The start
commit's parser reproduces the stored cards exactly (openev: 8,033 of 8,033 identical in every
field), so the stored directory is the "before". Run twice, the second time with a breakdown of
completeness changes; every count agrees.

| Caselist | Cards before | After | `CITE_ONLY` before | After | No tag before | After | With a cite before | After | Tagged, no cite before | After |
|---|---|---|---|---|---|---|---|---|---|---|
| hsld26 | 74,725 | 75,336 | 707 | 676 | 1,495 | 1,563 | 68,921 | 70,914 | 5,804 | 4,422 |
| hspf26 | 49,204 | 50,246 | 408 | 390 | 2,682 | 3,038 | 35,092 | 41,696 | 14,112 | 8,550 |
| hspolicy26 | 101,681 | 101,826 | 1,251 | 1,265 | 1,072 | 1,093 | 94,309 | 95,713 | 7,372 | 6,113 |
| openev | 8,033 | 8,049 | 78 | 78 | 73 | 75 | 7,267 | 7,590 | 766 | 459 |
| **Total** | 233,643 | 235,457 | 2,444 | 2,409 | 5,322 | 5,769 | 205,589 | 215,913 | 28,054 | 19,544 |

- **No card is `ABBREVIATED`,** before or after. **218,218 are identical in every field.**
- **Among cards that keep their range:** 8,594 gain a cite, one loses it (a held guess the hold now
  reads as the card's text), 9,547 gain a short cite, 16 have a different tag, 27 differ only in
  their section path.
- **25 go from `CITE_ONLY` to `FULL`** (23 by the hold) **and 28 from `FULL` to `CITE_ONLY`.** Of
  the 28, 10 are a cite behind a first name that had been the card's only "body" paragraph; the
  other 18 carry no new rule id and are read by the cite-line rule, which fits a line opening with
  a short cite written with a left quote. That last is a reading of rule ids, not a check of each
  card.
- **548 ranges are gone and 2,362 are new,** 500 of them with no tag: tags restored with their
  cards in files written in an unmapped style, and cards behind cites that are read now.
- **The rules, by paragraph in a card:** 5,189 behind a first name, 493 highlighted, 13,939 read
  through an unmapped style (1,339 cites and the rest body).

## Files changed

- `packages/debate_core/src/debate_core/evidence/style_classifier.py`: `for_matching`;
  `is_a_cite_behind_a_first_name_or_title` with `TITLES_BEFORE_A_NAME` and
  `MOST_WORDS_BEFORE_THE_AUTHORS_NAME`; `is_a_highlighted_cite`; `_through_an_unmapped_style` and its
  place in `classify_paragraph`; `the_cite_style_marks_a_name_and_year_at_the_head` made public.
- `packages/debate_core/src/debate_core/integrations/docx_parser/parser.py`:
  `_read_cites_where_a_cite_stands` (was `_read_bracketed_cites_where_a_cite_stands`) with
  `_why_it_is_a_cite_where_a_cite_stands` and `_followed_by_a_body`;
  `_the_cite_style_marks_its_source`; `_short_cite` on `for_matching`; the version.
- `packages/debate_core/tests/integrations/docx_parser/test_remaining_cite_shapes.py` (new): 77
  tests.
- `packages/debate_core/tests/integrations/docx_parser/test_first_corpus_parse_findings.py`: t09's
  300-word fixture is the body (as ruled).
- `packages/debate_core/tests/integrations/docx_parser/test_cite_detection.py`: t12's mid-paragraph
  hold test, its three highlighting tests and its version pin, restated (Deviation 5).
- `scripts/sample_cite_shapes.py` (new) and `tests/scripts/test_sample_cite_shapes.py` (new, 11
  tests).
- `tests/fixtures/debate_files/structural/*.expected.json`: ten lines, each `parser_version`. No
  label file and nothing under `tests/evals/baselines/` is touched.
- `docs/data/caselist-parse-report.md`: a section for this task. `docs/data/parsed-card-store.md`:
  the version, the hold, the new rule ids, the left quote.
- `plan_specs/v1/e31-debate-file-parsing/t19-remaining-cite-shapes.yaml`: the PM's amendment to
  item (2). The phase stays `InProgress`.

## Deviations from the spec

1. **The corpus counts ran in the session**, though the forbidden list says "Running the corpus
   counts or a re-parse in a session (operator-run only)". The PM's kickoff notes of 2026-10-18
   said to count read-only over the dev store as t12 did, and the PM's ruling of the same day
   accepted it: the notes overrode the forbidden entry. Every run was read-only and wrote nothing
   to the data directory: the census (four command rounds), the side-by-sides for (2), (4) and (6),
   the two full side-by-side comparisons, a scan of openev with the sampler, and the location of
   (7)'s file.
2. **Two commands ran past two minutes.**
   - The first census round: `perl -e 'alarm 115'` was on the shell around `xargs -P 8`, so it
     killed the shell and the eight read-only shards ran on, about 2.5 minutes in all. Every later
     round put the alarm on each child (the PM's note: bound the children); none passed 90 s.
   - One run of the whole `debate_core` package suite took 143 s. Offline tests only. The suite ran
     in eighths after that.
3. **(5)'s figures in my message to the PM were a subset.** I wrote "22,812 of 40 characters or
   fewer with no sentence end (11,422 in capitals)". Those counted only lines that were neither
   bold, italic nor holding a name and year. Exact: 24,207 of 40 characters or fewer with no
   sentence end, and 11,957 in capitals, 11,799 of them 40 characters or fewer. The parse report
   holds the exact table. Nothing ruled on depended on the difference.
4. **(6)'s reach in my message was 415 more short cites; the corpus run gives 9,602.** The earlier
   side-by-side covered only the 131 files with a short line alone. The spec's `’` example is
   already read; the shape is U+2018.
5. **Four tests of earlier tasks are restated, not left:**
   - t09's 300-word fixture test (ac3; ruled);
   - t12's `test_a_run_in_the_cite_character_style_leaves_it_a_cite`, now `…_in_its_middle_is_emphasis`
     (the same ruling);
   - t12's three `test_highlighting_leaves_it_as_it_was`, now `…_is_not_this_rules_and_is_a_cite_with_a_body_below`:
     t12's rules still refuse highlighting; (3) reads the cite;
   - t12's version pin, which now asks only that the version sorts after `2026.10.12-docx-3`.
6. **The three sampled rules lived behind a constructor flag** from `8ebb9d7` to `8b89d2d`, so the
   sample judged the code that ships while the parser's output stayed as it was. The flag and the
   classifier keyword are gone.
7. **The PR-subset evaluation was also run on the start commit's parser** (its source extracted
   with `git archive` and put first on `PYTHONPATH`), to quote evidence and boundary scores before
   and after. Its cite figures equal the "before" the PM quoted.
8. **Scratch files** (52 MB in the session's scratchpad: per-paragraph features, digests, counts,
   no text) are kept until the review, in case another cut is wanted. I delete them on your word.

## Decisions and assumptions

- **(1) sits in the assembly, where a cite stands.** The same shape fits 437 paragraphs elsewhere,
  after a body or a heading. *Alternative:* the classifier, which would take those too.
- **(1) turns away a paragraph that carries the cite style,** as measured and sampled: 11 in the
  corpus. Such a paragraph is the style rule's, and the hold's.
- **(1)'s first-name test is written out:** one to three capitalised words or initials, or a title
  from a written list (checked before the sentence openers). *Alternative:* any short phrase, which
  is how 1,940 of the 8,250 begin, and which sentences share.
- **(1) leaves the short cite empty.** `Adaeze Okonkwo 26` reads `Okonkwo 26` aloud, but the short
  cite pattern reads the front of a cite only, and an invented short cite would be repeated as fact.
  Follow-up work.
- **(2) includes a paragraph in `Normal` by name** (6 of the 1,355), since the profile maps `Normal`
  to `OTHER` like the aliases; and excludes table cells and blank paragraphs, which a mutant shows
  matters for a blank small-print mark.
- **(3)'s body below is the next paragraph that says anything,** blank lines and page furniture
  stepped over, as the classifier read it.
- **(6) reads a left quote only before a digit.** `O‘Brien` stays as written. The short cite keeps
  the file's character.
- **The version is `2026.10.18-docx-5`:** the date the output changed and the next counter.
- **`profile_version` is unchanged:** the profile file is untouched, so the operator's labelling is
  not disturbed (the PM's ruling on (6)).

## Operator follow-ups

### 1. (7): the Word check (about 5 minutes; reads the data directory, writes one copy to /tmp)

Open the file and print, on your screen only, where the two cards are:

```zsh
cd ~/.debate-research/dev/parsed
C=hspf26
R=heuristic-cite-line-bracketed
D=$(find ${C}/2026.10.12-docx-3/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r --arg r "${R}" 'select(.record == "document") | "\([.document.cards[] | select(any(.rule_ids[]; startswith($r)))] | length) \(.source_sha256)"' | sort -rn | head -1 | cut -d' ' -f2)
cp -f ~/.debate-research/dev/blobs/sha256/${D:0:2}/${D:2:2}/${D} /tmp/tag-check.docx
open /tmp/tag-check.docx
jq -r --arg r "${R}" 'select(.record == "document") | .document.cards as $all | [$all | to_entries[] | select(any(.value.rule_ids[]; startswith($r)))][:5][] | select((.value.tag // "") == "") | "card \(.key + 1) of \($all | length)\n  line above its cite, as stored: \(($all[.key - 1].evidence_text | split("\n") | last)[:80])\n  its cite starts: \(.value.full_cite[:80])"' ${C}/2026.10.12-docx-3/sha256/${D:0:2}/${D:2:2}/${D}.jsonl
```

Expected: card 2 of 16 and card 3 of 16. For each, answer in a message: is the line just above its
cite the card's tag (yes, no or unsure), and how it is formatted, in a few words. No text from the
file. Then:

```zsh
rm -f /tmp/tag-check.docx
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
```

If yes, the shape is counted and fixed the same way in a follow-up (a small change, its own
fixtures, the same version if before the merge); if no, the report says so and nothing changes.

### 2. The re-parse (ac4): after the merge, and after `v1-e31-t20`'s rebuild (its step 13)

Run it only once t20's step 13 has finished, so the two never overlap, and not while `caselist
pull` is running. The PM may combine these steps with t20's, as for t11 and t12. They follow t12's
steps and the scheduled-sync runbook's "After a release that bumps the parser version".

**Time and disk.** About 35 minutes for the dev parse and publish (the 2026-10-16 runs took 1,970
s), about 20 for the second run, 15 for prod, 15 by eye. A version directory is about 6 to 7 GB;
have at least 8 GiB free.

**2a. Start on an updated `dev`** (seconds):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git status --short
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t19-remaining-cite-shapes:'
export DEBATE_ENV=dev
uv run debate-research caselist runs --last 1
df -h ~/.debate-research
```

Expected: `dev`; `git status` prints nothing; `git log` prints one line; the last run has finished;
at least 8 GiB available. If `git log` prints nothing, the merge is not on `dev`: stop.

**2b. The dry run, and the counts before** (about 3 minutes; writes nothing; no AWS session):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --dry-run | jq -c '.data | {caselist, version, fingerprint_version, sources, to_parse, skipped, suppressed}'; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.12-docx-3/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | "\(.completeness) \(if .tag == null then "no-tag" else "tagged" end) \(if .full_cite == "" then "no-cite" else "cite" end) \(if .short_cite == null then "no-short" else "short" end)"' | sort | uniq -c; done > ~/cites-before-t19.txt
cat ~/cites-before-t19.txt
```

Expected from the first loop: `version` `2026.10.18-docx-5` and `to_parse` equal to `sources` for
each caselist. If `version` is `2026.10.12-docx-3`, the checkout does not carry the task: stop.

**2c. The dev parse and publish** (about 35 minutes), one caselist at a time:

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-dev-evidence
export DEBATE_ENV=dev
uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/reparse4-dev-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/reparse4-dev-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/reparse4-dev-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish > ~/reparse4-dev-openev.json; echo "exit $?"
```

Expected: `exit 0` each time. The seven failures of 2026-10-16 are gone: `v1-e31-t15`'s part of the
version reads six of them and records the seventh, a CardMirror file, as an unsupported format. On
`PARSED_PUBLISH_INCOMPLETE` run the same line again.

**2d. The counts to paste back** (about 3 minutes; counts only):

```zsh
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, sources, parsed, cards, unsupported, failed, elapsed_seconds, publish: .publish.counts}' ~/reparse4-dev-${c}.json; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.18-docx-5/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | "\(.completeness) \(if .tag == null then "no-tag" else "tagged" end) \(if .full_cite == "" then "no-cite" else "cite" end) \(if .short_cite == null then "no-short" else "short" end)"' | sort | uniq -c; done > ~/cites-after-t19.txt
cat ~/cites-after-t19.txt
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.18-docx-5/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | (.rule_ids[] | if startswith("assembly-cite-behind-a-name") then "behind a name" elif startswith("assembly-highlighted-cite") then "highlighted" elif test(":verbatim-") then "through an unmapped style" else empty end), (if (.short_cite // "") | test("‘") then "short cite with a left quote" else empty end)' | sort | uniq -c; done
ls -d ~/.debate-research/dev/parsed/*/*
du -sh ~/.debate-research/dev/parsed
```

Expected, if no source was imported after 2026-10-16:

| Caselist | Cards | `CITE_ONLY` | No tag | With a cite | Tagged, no cite | With a short cite |
|---|---|---|---|---|---|---|
| hsld26 | 75,399 | 676 | 1,563 | 70,977 | 4,422 | 50,512 |
| hspf26 | 50,246 | 390 | 3,038 | 41,696 | 8,550 | 35,638 |
| hspolicy26 | 101,826 | 1,265 | 1,093 | 95,713 | 6,113 | 61,162 |
| openev | 8,081 | 80 | 78 | 7,619 | 462 | 4,490 |
| **Total** | 235,552 | 2,411 | 5,772 | 216,005 | 19,547 | 151,802 |

These include `v1-e31-t15`'s six sources refused before and read now (95 cards, in hsld26 and
openev).

and from the third loop:

| | hsld26 | hspf26 | hspolicy26 | openev |
|---|---|---|---|---|
| behind a name | 1,042 | 2,866 | 1,025 | 256 |
| highlighted | 29 | 426 | 34 | 4 |
| through an unmapped style | 3,414 | 9,473 | 963 | 89 |
| short cite with a left quote | 1,679 | 3,412 | 4,259 | 252 |

No line in `~/cites-after-t19.txt` begins `ABBREVIATED`. `ls` shows two directories a caselist.
After a pull every figure is a little higher; send the files and the loops' output as they are.

**2e. The second run, which must parse and upload nothing** (about 20 minutes):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --publish | jq -c '.data | {caselist, version, attempted, skipped, elapsed_seconds, uploaded: .publish.counts.uploaded}'; done
```

Expected: `attempted` 0, `skipped` equal to the sources and `uploaded` 0 for each caselist.

**2f. Five files by eye** (about 15 minutes), as t12's step 6. Each row finds the file with the most
cards matching `M`, opens it, and prints five of them. Set `C` and `M` from the table and paste the
block once a row.

| File | `C` | `M` |
|---|---|---|
| 1 | `hspf26` | `^assembly-cite-behind-a-name` |
| 2 | `hspf26` | `^assembly-highlighted-cite` |
| 3 | `hspf26` | `:verbatim-` |
| 4 | `hsld26` | `^assembly-cite-behind-a-name` |
| 5 | `hspolicy26` | `^assembly-highlighted-cite` |

```zsh
cd ~/.debate-research/dev/parsed
C=hspf26
M='^assembly-cite-behind-a-name'
D=$(find ${C}/2026.10.18-docx-5/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r --arg m "${M}" 'select(.record == "document") | "\([.document.cards[] | select(any(.rule_ids[]; test($m)))] | length) \(.source_sha256)"' | sort -rn | head -1 | cut -d' ' -f2)
cp -f ~/.debate-research/dev/blobs/sha256/${D:0:2}/${D:2:2}/${D} /tmp/cite-check.docx
open /tmp/cite-check.docx
jq -r --arg m "${M}" 'select(.record == "document") | [.document.cards[] | select(any(.rule_ids[]; test($m)))][:5][] | "\(.completeness) | \(.tag) | \(.short_cite) | \(.full_cite[:80]) | \(.evidence_text[:60])"' ${C}/2026.10.18-docx-5/sha256/${D:0:2}/${D:2:2}/${D}.jsonl
```

For each card printed, find it by its tag and answer: is the tag the card's tag; is the cite the
card's cite and not a sentence of the card; does the evidence start where the card's quoted text
starts and not with the citation. Send tallies only: for each file, how many of its cards are right
on each question. Then:

```zsh
rm -f /tmp/cite-check.docx
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
```

A cite printed that is a sentence of the card, or evidence that begins with the citation, is a
wrong reading by a new rule: do not publish to prod; send the tally and the row.

**2g. The prod publish**, from the dev data directory, after dev looks right (about 15 minutes):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research --json caselist parse --caselist hsld26 --dry-run | jq -c '.data | {caselist, version, to_parse, skipped}'
uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/reparse4-prod-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/reparse4-prod-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/reparse4-prod-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/reparse4-prod-openev.json; echo "exit $?"
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

The dry run must show `2026.10.18-docx-5` and `to_parse` 0; if not, the data directory is wrong:
stop. The `unset` at the end matters.

**2h. Install a build that carries this task and reload the agent**, on a day other than Wednesday
morning, by the scheduled-sync runbook (`scripts/install_channel.sh` with the tag, its Step 2 and
Step 3, then `ops/launchd/install.sh --check-launchd`). The tag does not exist yet, so the commands
come from the runbook. Afterwards the agent's dry run should show `2026.10.18-docx-5` and
`to_parse` 0.

**2i. Record it.** Whoever closes ac4 adds the counts to `docs/data/caselist-parse-report.md`
beside the read-only figures, and sets the Goal `Succeeded` in a spec PR, together with (7)'s
outcome.

## Follow-up work

- **(5), short plain lines inside a body (E31):** for the later task merged with `v1-e31-t23`,
  after `v1-e31-t20` merges (the PM's ruling). Its starting figures are in the parse report.
- **What the cautious rules leave (E31):** 2,186 lines behind a first name read as nothing (7 of the
  10 sampled left items are cites), and 221 highlighted cite shapes elsewhere than under a tag with
  a body below (10 of 10 sampled are cites). Widening either needs its own counts and sample.
- **A short cite behind a first name (E31, small):** the 5,189 cites read behind a first name have
  no short cite. `Okonkwo 26` is there, behind `Adaeze`; reading it would change the short-cite
  pattern's "front only" rule, which is a ruling.
- **(7), if the operator confirms a tag:** the shape counted and fixed as ac5 says.
- **The sampler** (`scripts/sample_cite_shapes.py`) keeps working on the new parser and can repeat
  the sample with the same seed; it asks about rules that are now on, so a repeat measures the
  shipped parser.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-18

**Notes:**

The work is strong and nearly done. Two things stop the merge today: a parser-version collision,
and a rule whose reach turned out twenty times larger than was sampled. Append a section headed
"After the PM review of 2026-10-18" for both, and I review again.

**1. The version collides with `v1-e31-t15`.** Both branches set `DOCX_PARSER_VERSION =
"2026.10.18-docx-4"` for different parsers. Two parsers under one version string would make the
store's version directories lie. `v1-e31-t15` is ahead in review and merges first. Then:

* run `scripts/task sync` onto the `dev` that holds it, and take the next counter
  (`2026.10.18-docx-5`, or the date you make the change if that is later), with its own history
  line;
* change every place this branch names `docx-4` to the new version: the version tests, the ten
  structural expectations, `parsed-card-store.md`, the parse report section, and each operator
  step (2b expects the version, 2d's paths, 2g's dry run, 2h);
* re-run the read-only side-by-side on the synced parser, so the operator's expected tables include
  t15's effect (its 7 sources now parse), and update the tables;
* re-run `run_parser_eval.py --tier pr-subset` and the default suite on the synced branch.

**2. (6) needs a sample before it ships.** I approved (6) without a sample as a narrow
normalisation: a few hundred lines, by your estimate. It now changes 9,602 cards' short cites. Your
own reading of rule ids also attributes 18 of the 28 FULL to CITE_ONLY changes to it: a body
paragraph opening with a left-quoted short cite read as a cite line, so the card loses its body.
That is the one change in this task that can take evidence away from a card, and nobody has looked
at it. Through `scripts/sample_cite_shapes.py`:

* **all 18** of those cards: is the paragraph now read as a cite really the cite, or the card's
  text?
* **10** cards that gain a left-quoted short cite: is the short cite right?

That is 28 items and about 5 minutes for the operator, with the seed, items asked and time
recorded.

* If any of the 18 is the card's text, stop and propose how to narrow (6). For example, the left
  quote could be read as `’` for the short-cite pattern only and not for the cite-line rule. Don't
  build it until I rule.
* If the short cites are wrong more than once in 10, the same applies.

**3. (7):** the operator's Word check (Operator follow-ups, step 1) may come before or after the
merge. If after, it is recorded with ac4.

**Already accepted, and not to be redone:**

* **ac1:** the counts first, the rulings before any rule, and a sample of 70 with 0 wrong takes in
  41 taken items.
* **The rules,** with every condition mutated: 54 of 54 caught, and the four first-pass survivors
  resolved properly.
* **The flag that let the sample judge the shipped code,** then removed. A good method.
* **The PR-subset cite precision rose** (0.957 to 0.969) and recall rose (0.500 to 0.705), with
  tags, evidence and boundaries unchanged.
* **Deviations 1 to 7:** accepted. Deviation 3's correction to the (5) figures is noted. Nothing
  ruled depended on it.
* **Decisions:** all accepted. Leaving (1)'s short cite empty rather than inventing one is right.
* **Deviation 8, the scratch files:** keep them until this second review, then delete them.

**Follow-ups, for the next PM batch:**

* **The cautious rules' leftovers:** 2,186 lines behind a first name and 221 highlighted shapes.
  Filed at p3, each with its own counts and sample.
* **A short cite behind a first name:** needs a ruling on the "front only" short-cite rule. Filed at
  p3.
* **(5):** goes with the `v1-e31-t23` merge, as ruled.

## After the PM review of 2026-10-18

Both items are done. The branch is rebased with `scripts/task sync` onto `origin/dev` at `5a77636`,
which holds `v1-e31-t15`. Commit ids in the sections above are from before that rebase; the ones
here are after it. The Goal stays `InProgress`: the re-parse (ac4) and the Word check for (7)
(ac5) are still the operator's.

### 1. The version: `2026.10.18-docx-5`

`v1-e31-t15` merged with `2026.10.18-docx-4`, and the date is still 2026-10-18, so this task's
version is the next counter, `2026.10.18-docx-5`, with its own history line after t15's
(`9b8dc57`, resolved in the rebase).

- **Every place this branch named `docx-4` now names `docx-5`:** the version constant and its
  history; `TestTheParserVersion` (which now also sorts after t15's version); the ten structural
  expectations' `parser_version` line; `parsed-card-store.md` (a row of its own in the version
  table beside t15's, and the new rule ids); the parse report's section; and every operator step
  above (2b's expected version, 2d's and 2f's paths, 2g's dry run, 2h).
- **One more of t15's lines changed, as t15 changed t12's.** t15's
  `test_it_is_the_version_this_task_bumped_to` pinned `2026.10.18-docx-4`; it now asks for that
  version or a later one, in the words t15 used for t12's test. The rebase kept t15's version of
  t12's test and dropped mine.
- **The side-by-side, re-run on the synced parser,** read-only, both kinds of source: the 11,148
  parsed before and the 7 refused before.
  - Over the 11,148, every figure equals the first run: 218,218 cards identical, 9,602 short cites
    with a left quote, the same completeness changes and rule counts. t15 changes no card there.
  - t15 reads six of the seven refused sources (five in hsld26, one in openev), with 95 cards, and
    names the seventh an unsupported format.
  - So the operator's expected totals become 235,552 cards, 2,411 `CITE_ONLY`, 5,772 with no tag,
    216,005 with a cite, 19,547 tagged with no cite and 151,802 with a short cite. Step 2d's table
    and step 2c's note on failures are updated to match.
- **The PR-subset evaluation, re-run on the synced branch.** The labels moved on `dev`
  (`labels/2026 10 19`), so every parser was measured again on the same labels:

  | Parser | Cite precision | Cite recall | Tag precision | Tag recall | Evidence precision | Evidence recall | Card boundaries |
  |---|---|---|---|---|---|---|---|
  | `2026.10.12-docx-3` | 0.957 (22, 1 wrong) | 0.500 (22 of 44) | 0.949 | 0.860 | 0.943 | 0.968 | 36 of 38 |
  | `2026.10.18-docx-4` (t15, `dev`) | 0.957 | 0.500 | 0.949 | 0.860 | 0.943 | 0.968 | 36 of 38 |
  | `2026.10.18-docx-5` | 0.969 (31, 1 wrong) | 0.705 (31 of 44) | 0.949 | 0.860 | 0.943 | 0.968 | 36 of 38 |

  Cite precision does not fall. Only the tag recall and the boundary counts moved, with the labels,
  and they are the same before and after this task.
- **The default suite, in eighths, on the synced branch:** 1,061; 1,065; 1,063; 1,057; 1,052; 1,061
  and 1 xfailed; 1,061 and 1 failed; 1,059 and 1 xfailed. 8,479 passed. The failure is the known
  `test_the_labeled_pr_subset_holds_the_baseline`. `pyright` 0 errors. The mutant that reverts the
  version to t15's is caught by 12 tests.

### 2. (6), sampled before it ships

`scripts/sample_cite_shapes.py --plan left-quote` (`7d36310`, `b3180ba`) adds two strata. They
compare the parser's cards with the cards the store holds for the same source, read in place:

- **a cite line that leaves its card no body:** a card stored `FULL` that is `CITE_ONLY` now at the
  same range, whose rule ids name none of this task's other rules or a re-read. The marked paragraph
  is the cite line that opens with a short cite only once the left quote is read as `’`. Every one of
  these cards is drawn;
- **a card gaining a short cite written with a left quote,** with the short cite shown under the
  cite.

Before the operator's run, a read-only count over the store in shards found exactly the 18 cards,
and all 18 hold such a line: the attribution by rule ids was right. The second stratum is 9,584
(those plus the 18 are the 9,602). The plan's code has 4 new tests; 11 mutants were caught, three
of them only after tests were added for a card `CITE_ONLY` before and after, a left-quoted line
under an ordinary cite, and a short cite the store already held.

**The operator's run, 2026-10-18,** seed 20261019, 28 items, 148 seconds answering:

| Side | In the corpus | Asked | Yes | No | Unsure |
|---|---|---|---|---|---|
| A cite line that leaves its card no body (the card's cite?) | 18 | 18 | 18 | 0 | 0 |
| A card gaining a short cite with a left quote (the right short cite?) | 9,584 | 10 | 10 | 0 | 0 |

The tallies' last line: "Of the cards whose cite line leaves them no body, 0 hold no line read
only through the left quote."

**None of the 18 is the card's text, and no short cite is wrong**, so neither stop condition is
met and nothing is narrowed. (6) stands as built. Each of the 18 is a card whose only "body" was its
own cite line, which the old patterns could not read. The parse report's sample section holds both
tables.

### Criteria, as they stand now

| Criterion | Status |
|---|---|
| ac1 | PASS, as accepted |
| ac2 | PASS: cite precision 0.957 → 0.969 on the synced branch and the moved labels |
| ac3 | PASS |
| ac4, first half | PASS: `2026.10.18-docx-5` |
| ac4, second half | **NOT RUN**: operator, after the merge and after `v1-e31-t20`'s step 13 |
| ac5, (6) | PASS, now with a coach's sample: 18 of 18 and 10 of 10 right |
| ac5, (7) | **NOT RUN**: the operator's Word check (step 1) |

**Scratch files:** kept until this second review, as you asked, then deleted on your word.

## PM review, second

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-18

**Notes:**

Accepted. Both items of the first review are done. The Goal stays `InProgress` for ac4's re-parse
and (7)'s Word check, so the merge uses `--partial`.

* **The version.** I checked the worktree. The branch sits on `origin/dev` at `5a77636`, which holds
  `v1-e31-t15`, and `DOCX_PARSER_VERSION` is `2026.10.18-docx-5`. The `docx-4` strings left are t15's
  own pins, now "or later", and the reference to t15's version, as they should be. The side-by-side
  was re-run on the synced parser, and the operator's expected tables now include t15's six newly
  read sources. So the one re-parse covers both tasks: step 2c's note on the failures is ac4 for
  `v1-e31-t15` as well.
* **(6)'s sample.** All 18 cards that lose their body under (6) were drawn, and all 18 are cards
  whose only "body" was their own cite line. 10 of 10 left-quoted short cites are right. The count
  that found exactly the 18 confirms the rule-id attribution, and the new strata's mutants were
  caught. (6) stands as built.
* **The PR-subset table** measures every parser on the moved labels. The comparison is like with
  like, and cite precision does not fall (0.957 to 0.969).
* **The scratch files** may be deleted now.

**For the operator:** the re-parse (step 2) runs after `v1-e31-t20`'s step 13, once. Its counts close
ac4 for both t19 and t15, recorded in one close-out. (7)'s Word check (step 1) is any time.

### (7): the operator's Word check, 2026-10-19 (recorded by the PM)

The operator ran Operator follow-ups step 1 and checked both cards in Word. For card 2 and card 3
of 16, the line just above the bracketed cite **is the card's tag**, formatted as an ordinary bold
tag. So the shape is a defect: ac5's second half, "counted and fixed", is carried by
`v1-e31-t24-bold-tag-above-bracketed-cite`, filed in the PM close-out of 2026-10-19, which counts
the shape over the corpus before any rule changes. This task's Goal stays `InProgress` for ac4's
re-parse; (7) closes when `v1-e31-t24` does.

### ac4: the operator's re-parse, 2026-10-19 (recorded by the PM)

The combined re-parse to `2026.10.18-docx-5` matched this report's expected tables exactly: 235,552
cards, 216,005 with a cite (205,589 before), 151,802 with a short cite (140,527), 19,547 tagged with no
cite (28,054), and the four new rules' counts line for line. Five files by eye (step 2f) were right on
every card. The before-and-after table is in
[the parse report](../data/caselist-parse-report.md#the-re-parse-to-docx-5-and-the-re-cluster-on-the-store-operator-run-2026-10-19).
ac4 passes. ac5's (7) was recorded above and is carried by `v1-e31-t24`. The PM sets the Goal
`Succeeded` in the close-out of 2026-10-20.
