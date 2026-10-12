# Session report: v1-e31-t12-cite-detection

| | |
|---|---|
| Task | `v1-e31-t12-cite-detection` — Cites the parser misses or misreads |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t12-cite-detection.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t12-cite-detection.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t12-cite-detection` |
| Session status | PARTIAL: the code, fixtures, counts and documents are done. The operator's re-parse (the second half of ac4) is NOT RUN, so the Goal stays `InProgress` and this merges with `--partial` |

## Summary

The five cite shapes are counted over the dev store, labelled as 62 invented examples, and
settled. Four are defects, one of them in part, and are fixed in the classifier and the parser's
assembly; the fifth is correct output and is left. The parser's output changes, so it is `2026.10.12-docx-3`. Over the
same 9,741 DOCX sources the new parser reads a cite for 9,358 more cards (164,581 to 173,939),
`CITE_ONLY` falls from 2,254 to 2,025, and 183,575 of the 198,205 stored cards are identical in
every field. Tag and cite precision do not fall anywhere they are measured. The largest thing I
found is not in the spec's figures: 33,624 tagged cards have no cite, not 337.

## Read these first

1. **The parser version is bumped, and that has to be handled before the agent meets the build.**
   `2026.10.10-docx-2` becomes `2026.10.12-docx-3`. A new parser version starts an empty version
   directory, so the first parse under it reads every source: about 30 minutes for the four
   caselists.
   - Since `v1-e34-t17` the weekly pull's parse stage would do that full parse itself, on the
     first scheduled run after the agent is reinstalled from a build that carries this task.
   - The scheduled-sync runbook says to do it by hand instead, with `caselist parse --publish`
     for each caselist, before the agent meets the build.
   - The agent runs `v0.1.0-dev.119` through Wednesday 2026-10-14's scheduled run. That build
     does not carry this task, so Wednesday's run is unaffected and writes `2026.10.10-docx-2`.
   - [Operator follow-ups](#operator-follow-ups) are written for the reinstall after it: the dry
     run that shows a full parse is due, the by-hand parse in dev, the counts, a check by eye of
     five files, the publish to prod, and only then the install.
   - I ran the dry run from this branch, read-only (1.7 s). It reports `2026.10.12-docx-3` and
     every source to parse: 4,461, 2,657, 3,906 and 102.
2. **Shape (3) is a hundred times the size the spec gives, and I fixed the part formatting
   settles.** The spec says 337 cards have no cite. Those are the cards one of `v1-e31-t09`'s
   rules re-read. Counted directly, 33,624 tagged cards in the store have no cite, 17% of all
   cards, and 21,585 of them have a line under the tag that was read as nothing. The cite-line
   guess stops at 400 characters, and a cite that carries its author's credentials is longer.
   A line of 401 to 2,000 characters that opens in bold with a name and a year is now a cite
   line: 8,426 paragraphs, 8,394 of which name a credential or hold a link. This is the widest
   change in the task. It has its own function, rule id, tests and mutants, so it comes out
   cleanly if you want (3) held to the 337. The alternative is under
   [Decisions](#decisions-and-assumptions).
3. **Stored cards change, and a few leave.** 13,521 cards keep their paragraph range and differ,
   9,181 of them by gaining a cite. 1,109 ranges are gone and 1,274 are new, mostly one card for
   another. 23 cards with no tag are gone with nothing in their place: each began at a sentence
   such as *In 2019 …* that had been read as a cite, with no tag and no cite above it, which the
   parser's own rule and the labelling guide call a stray body. 586 paragraphs leave the store
   and 9,998 join it.
4. **Five cards get worse, through an accepted rule of `v1-e31-t09`.** They go from `FULL` to
   `CITE_ONLY` with their body in the cite. That task holds a guessed cite that carries a
   cite-style run where it is. In these five the paragraph above was a long styled cite read as
   body, which had opened the body; it is read as a cite now, so the rule applies. Changing it
   would change one of that task's fixtures, so I left it and filed it.
5. **The two corrected evaluation files score the same before and after, and hold none of the
   five shapes.** They do hold five cites the parser still misses.
6. **What is left is mostly one shape.** 24,431 tagged cards still have no cite. 7,200 of them
   have a name and a year a few words into the line under the tag, behind a first name or a
   title. That is a formatting question, and the largest follow-up.
7. **For `v1-e31-t11`:** the evidence text differs for 2,515 cards that keep their range (2,227
   lose their cite from its front, 220 gain a body), and 1,109 ranges are replaced by 1,274, so
   those fingerprints differ under the new parser. I touched none of that task's files.
8. **Dev has not moved.** `origin/dev` is still `50eae0d`, where this branch started. No sync was
   needed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cite-detection`: Cite shapes settled | Done but for the operator's re-parse | `uv run pytest packages/debate_core/tests/integrations packages/debate_core/tests/evidence` → `2348 passed, 2 xfailed in 8.67s`. The two expected failures are the one line left on purpose, under shape (5) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: for each of (1) to (5), counts from the dev store, read-only, and at least ten labelled examples added to the evaluation set; the report says which are defects | PASS, with the count for (3) differing from the spec's | Counts under [The five shapes](#the-five-shapes) and in [`docs/data/caselist-parse-report.md`](../data/caselist-parse-report.md#cites-the-parser-missed-or-misread-v1-e31-t12). The stored directory's own counts and the old parser's agree. Examples: 13, 12, 12, 14 and 11 a shape in `tests/evals/parser/cite_shapes.py`; `uv run pytest tests/evals/parser/test_cite_shapes.py` → `84 passed`. As written, (3) is 337; as measured, the shape is 33,624 cards and the 337 are among them |
| ac2: each defect has a synthetic fixture shown failing first, and the fix does not lower tag or cite precision on the labelled evaluation | PASS | Red at `4ebb98a`: `343 failed, 259 passed, 2 xfailed`, every failure an assertion. Green at `9accc81`. [Precision](#precision-before-and-after): unchanged on the two corrected files, and 0.805 to 1.000 for cites on the synthetic set |
| ac3: a card whose only paragraph is a cite is `CITE_ONLY`, whatever the cite's bracket and initials form, by fixture | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_cite_detection.py -k TestACardThatIsOnlyACite` → `227 passed`. Five forms, two bracket kinds, thirteen signatures, three lengths, three kinds of formatting |
| ac4, first half: if the parser changes, `parser_version` is bumped | PASS | `2026.10.12-docx-3`. `TestTheParserVersion` → 4 passed; a mutant that reverts it fails 12 tests |
| ac4, second half: operator-run, the re-parse's cite and completeness counts before and after, recorded in `docs/data/caselist-parse-report.md` | **NOT RUN** | It needs the merge, about 30 minutes of parsing, and AWS sessions for both buckets. The document holds the read-only measurement, marked as that. [Operator follow-ups](#operator-follow-ups) |
| Node: `uv run pytest packages/debate_core/tests/integrations packages/debate_core/tests/evidence` | PASS | `2348 passed, 2 xfailed in 8.67s` |
| Default suite, in four parts | PASS | `uv run --frozen pytest -n auto -m "not slow and not live" --part K/4`: `1607 passed in 34.28s`; `1613 passed, 1 xfailed in 28.65s`; `1617 passed, 1 skipped, 1 warning in 26.38s`; `1613 passed, 1 xfailed in 29.38s`. 6,450 passed in all. The skip is the evaluation's PR subset, which waits on four uncorrected label files |
| Static checks and gates | PASS | `pyright` 0 errors; `lint-imports` 12 kept; `ruff check` and `ruff format --check` clean, 414 files; `check_thin_handlers.py`, `check_links.py`, `check_command_blocks.py --base origin/dev`, `docs_index.py --check-descriptions` and `export_schemas.py --check` OK. The slow parser timing test: `1 passed in 3.18s` |
| `uv run scripts/validate_specs.py` | PASS | `OK: 347 files, 38 epics, 289 tasks, 20 releases`. Phase `InProgress` |

## The five shapes

Measured on 2026-10-12, read-only, over the dev data directory: the stored
`2026.10.10-docx-2` cards, and the old and new parsers run side by side in one process over the
same bytes of the 9,741 DOCX sources. Only counts, lengths, formatting flags and rule ids left the
scripts. The full tables are in
[`docs/data/caselist-parse-report.md`](../data/caselist-parse-report.md#cites-the-parser-missed-or-misread-v1-e31-t12).

| | Shape | Count | Verdict | Why |
|---|---|---|---|---|
| 1a | A cite line that opens with a word no author is called (*In 2019*) | About 5,400 lines guessed; 686 still cites after `v1-e31-t09`'s rules, 526 not in bold and 160 in bold | **Defect, fixed** for lines not in bold: 457 are no longer cites | In a first count with a wider word list, 419 of 564 such lines held no link, credential, date or quoted title, against 75 of the 869 lines not in bold that open with a real name |
| 1b | A guessed cite entry with no length bound | 1,080 guessed entries; 460 over 2,000 characters | **Defect, fixed** for 335: no cite style and no name and year in the first 300 characters | 220 cards had their body in the cite and no evidence text |
| 2 | A cite in the cite character style past 1,000 characters | 1,221 with the style on a name and year at the head and no highlighting. 811 read as nothing, 329 as body, 81 as cites | **Defect, fixed** | 1,219 name a credential; 1,203 sit under a tag with a body below |
| 3 | A card with no cite | 33,624 tagged cards. The spec's 337 are among them | **Defect in part, fixed in part**: 9,193 cards have a cite now, 113 of the 337 | In 21,585 a line under the tag was read as nothing. A cite on the tag line (2,343 cards) or missing from the file is **correct output** |
| 4 | A bracketed cite that ends in the cutter's initials | 85,173 paragraphs are a name and year and one bracket to the end; 8,131 were not read as cites. 866 open with the bracket; 304 of those stand where a cite stands, unread | **Defect, fixed**: 83,843 and 420 are read. 14 cards that were only such a cite were stored `FULL` | It is the commonest way the corpus writes a cite. It was read only with a cite style or at 400 characters or fewer |
| 5 | A short small-print line directly under a cite | 218 | **Correct output**, left | 178 open with a word such as *In* and a year and 174 of those end a sentence; 15 more are sentences. At most 25 could be a second line of the cite, and only their words say so |

What is fixed and where:

| Rule | Where | Rule id on the paragraph |
|---|---|---|
| A word that opens a sentence is not an author, unless the line opens in bold | `style_classifier.py`, the cite-line guess | None: the line is body, or nothing, by its own formatting |
| A cite in the cite style past 1,000 characters, to 4,000, when the style marks a name and year starting in its first 40 characters and nothing is highlighted | `style_classifier.py`, the style rule | `verbatim-cite-run-style-past-the-profile-bound` |
| A cite line of 401 to 2,000 characters that opens in bold with a name and year, not highlighted | `style_classifier.py`, a new rule after the cite-line guess | `heuristic-cite-line-bold-author-year` |
| The same length: a name and year, then one bracket to the end but for a signature of 30 characters or fewer | The same rule | `heuristic-cite-line-bracketed` |
| A paragraph wholly inside one bracket with a name and year at its head, under a tag or the card's cite and before any body | `parser.py`, a pass before tags are demoted | `assembly-bracketed-cite-before-the-body:…` |
| A guessed cite entry over 2,000 characters, with no cite style and no name and year in its first 300, is body wherever a card is open | `parser.py`, the two re-reads from `v1-e31-t09` | The three ids those already use |

What needs a model and is left to `v1-e31-t13`: a card written as one paragraph behind its cite, a
short wiki entry of first and last words, and a cite that sits on the tag line.

## Red then green

Tests came first. The fixtures were committed against the unchanged parser, with only constants
and two pure helpers that nothing called, so every failure is on behaviour.

| Commit | What it adds | New fixtures |
|---|---|---|
| `4ebb98a` | The labelled examples, the parser and classifier tests, inert helpers | **343 failed, 259 passed, 2 xfailed.** No errors. All 62 examples fail or pass as labelled: 37 `MISREAD` fail, 24 `ALREADY_RIGHT` pass, 1 `STILL_MISREAD` is an expected failure |
| `8425d66` | A sentence opener is not an author | 310 failed, 292 passed |
| `aa2c881` | The styled cite past the profile's bound | 275 failed, 327 passed |
| `439c9de` | The long cite line: bold, or one bracket | 119 failed, 483 passed |
| `9accc81` | The bracketed cite before the body, the guess longer than a cite entry, and the version | **602 passed, 2 xfailed** |
| `96ffc64` | A fix the corpus run found: eight cards split by a bracketed reference | Its fixture failed against `9accc81`: 1 failed, 1 passed |
| `72e3e6a`, `03487cd`, `2e1a500`, `c30ebae` | Edge tests, and what mutation found | 621 passed, 2 xfailed |

What each rule carries, from the mutant that switches it off:

| Rule switched off | Tests that fail |
|---|---|
| A sentence opener is not an author | 35 |
| The styled cite past the profile's bound | 17 |
| The long cite line, both shapes | 167 (the bold shape alone 28, the bracket alone 100) |
| The bracketed cite before the body | 104 |
| The guess longer than a cite entry | 19 |
| The version | 12 |

**What cannot fail first, and is not claimed to:** the 24 `ALREADY_RIGHT` examples and the tests
named "is left as it was" or "is still". They have the same answer with and without the rules.
Each is the other side of a rule, and a mutant proves it: for example "a highlighted paragraph is
taken" fails the highlighted tests of each rule.

**ac3 by fixture.** `TestACardThatIsOnlyACite` builds a tag and one cite paragraph and expects
one `CITE_ONLY` card whose `full_cite` is the paragraph and whose evidence text is empty:

- five forms: a bracket after a name and year that is plain, bold, or in the cite style, and the
  whole cite inside the bracket with and without a first name;
- square and round brackets;
- thirteen signatures after the bracket: none, initials in either case, behind slashes, a dash or
  a bar, two cutters, a word and initials, and a full stop;
- 300, 620 and 1,400 characters, at reading size, in small print, and with an underlined link.

227 tests. 174 failed first. The 53 that passed first are the cites the parser already read: a
cite style up to 1,000 characters, and a name and year at 400 or fewer.

## Precision before and after

**The two person-corrected files** (60 labelled paragraphs, scores only, both parsers over the
same files):

| Parser | Tag precision | Tag recall | Cite precision | Cite recall | Card boundaries | Completeness |
|---|---|---|---|---|---|---|
| `2026.10.10-docx-2` | 1.000 | 0.833 (5 of 6) | 0.500 (1 right, 1 wrong) | 0.167 (1 of 6) | 4 of 5 | 4 of 4 |
| `2026.10.12-docx-3` | 1.000 | 0.833 | 0.500 | 0.167 | 4 of 5 | 4 of 4 |

Identical, unit for unit. Neither file holds a paragraph the rules reach. They hold five cites
read as body, which I looked at by shape only: four of 177 to 395 characters with no name and
year at their front, one of them highlighted throughout, and one of 1,737 characters with a styled
name and year at its head and highlighting. A person labelled that last one a cite. It is the
shape I left under (2) because of its highlighting, and it is a follow-up.

**The synthetic set** (62 examples, 263 paragraphs, 63 cards; `uv run python -m
tests.evals.parser.cite_shapes` prints the second table):

| Shape, under `2026.10.10-docx-2` | Tag precision | Tag recall | Cite precision | Cite recall | Card boundaries | Cards parsed | Completeness |
|---|---|---|---|---|---|---|---|
| A sentence guessed to be a cite | 1.000 | 1.000 | 0.600 | 1.000 | 10 of 13 | 17 | 7 of 10 |
| A styled cite past the profile bound | 1.000 | 0.917 | 1.000 | 0.333 | 11 of 12 | 11 | 11 of 11 |
| A card with no cite | 1.000 | 0.909 | 1.000 | 0.100 | 9 of 13 | 10 | 9 of 9 |
| A bracketed cite with initials | 1.000 | 1.000 | 1.000 | 0.143 | 14 of 14 | 14 | 6 of 14 |
| A small-print line under a cite | 1.000 | 1.000 | 1.000 | 0.933 | 11 of 11 | 11 | 11 of 11 |
| **All five** | 1.000 | 0.967 | 0.805 | 0.524 | 55 of 63 | 63 | 44 of 55 |

| Shape, under `2026.10.12-docx-3` | Tag precision | Tag recall | Cite precision | Cite recall | Card boundaries | Cards parsed | Completeness |
|---|---|---|---|---|---|---|---|
| A sentence guessed to be a cite | 1.000 | 1.000 | 1.000 | 1.000 | 13 of 13 | 13 | 13 of 13 |
| A styled cite past the profile bound | 1.000 | 1.000 | 1.000 | 1.000 | 12 of 12 | 12 | 12 of 12 |
| A card with no cite | 1.000 | 1.000 | 1.000 | 1.000 | 13 of 13 | 13 | 13 of 13 |
| A bracketed cite with initials | 1.000 | 1.000 | 1.000 | 1.000 | 14 of 14 | 14 | 14 of 14 |
| A small-print line under a cite | 1.000 | 1.000 | 1.000 | 0.933 | 11 of 11 | 11 | 11 of 11 |
| **All five** | 1.000 | 1.000 | 1.000 | 0.984 | 63 of 63 | 63 | 63 of 63 |

- The "before" table is the old parser's source, taken from the start commit, over the final
  example set.
- The one cite still missed is a second line of a cite in small print with no bold opening. It is
  in the set as `STILL_MISREAD`, with a test that expects the failure.
- The set is mine, built to hold these shapes, so the "after" row says the rules do what they
  were written to do, not how the parser does on real files. The corpus counts and the two
  corrected files are the outside checks.

## Mutation testing

On `c30ebae`, the final source. Each run: a clean committed tree, one textual change, the tests
with a new empty `HYPOTHESIS_STORAGE_DIRECTORY`, the file restored from git, the tree checked
clean. 1,288 tests across the parser tests, the classifier and profile tests and
`tests/evals/parser`; 3.3 to 4.2 seconds a run; five commands of under two minutes.

**91 mutants, 91 caught, every one by assertion failures.** No run errored and none failed at
collection.

| Rule | Mutants | Caught |
|---|---|---|
| A sentence opener is not an author | 10 | 10 |
| The styled cite past the profile's bound | 15 | 15 |
| The long cite line | 9 | 9 |
| One bracket to the end | 15 | 15 |
| A cite wholly inside a bracket | 26 | 26 |
| A guess longer than a cite entry | 15 | 15 |
| The parser version | 1 | 1 |

Each condition has a mutant that drops it and one or two that move it. By rule, with the number
of tests that fail:

- **A sentence opener:** never applied 35; the bold opening no longer holds a line 6; case ignored
  so an acronym is an opener 2; only the first of two authors weighed 1; bold on the paragraph
  mark not counted 1; bold anywhere counted 2; a month on the list 7; *In* off the list 23; a
  short surname on the list 1; a sentence opener not passed over when a name is looked for 9.
- **The styled cite:** never applied 17; the bound removed 2, one lower 2, one higher 2; a
  highlighted paragraph taken 2; a name and year anywhere 4; the head one shorter 3, one longer 2;
  the style need not touch the name 4; a run ending where the name begins counts 1; a run starting
  where the year ends counts 1; leading white space not counted 1; the head measured with it 1;
  reported under the old rule's id 6; reported as a heuristic 2.
- **The long cite line:** never applied 167; the bound removed 6, one lower 7, one higher 4; a
  highlighted paragraph taken 6; a sentence opener opens one 4; no bold opening asked 30; the bold
  shape never taken 28; tried before the short rule 4.
- **One bracket to the end:** never taken 100; tried before the bold shape 1; only white space
  between year and bracket 14; nothing between 98; no dash 6; no stop, colon or semicolon 6; any
  word between 3; the signature bound removed 10, one shorter 2, one longer 4; the space before
  it counted 2; an inner bracket closes it 2; either kind closes it 3; a bracket that never closes
  counts 3; square only 72.
- **Wholly inside a bracket:** never applied 104; read anywhere, a body included 4; a cite stands
  at the head of a file 1; a body does not end the place 1; a blank line ends it 1; not after an
  undertag 1; not after a line of the cite 2; not after a tag 101; after a guess a body may take
  1; a body style re-read too 1; a table cell re-read too 1; only what was read as nothing 89;
  only what was read as body 15; tags demoted first 13; no rule named 2; highlighted taken 2; the
  bound removed 1, one lower 2, one higher 1; the bracket need not run to the end 4; no name and
  year asked 5; anywhere 2; the head one shorter 2, one longer 1; reported as surer than a guess
  1; reported as a style match 1.
- **A guess longer than a cite entry:** never applied 19; the bound removed 2, one lower 1, one
  higher 1; a cite-style run no longer holds it 1; a name and year at its head no longer holds it
  2; one anywhere holds it 18; a paragraph with none at all is held 1; the head one shorter 1, one
  longer 1; before the body it must still be formatted as body 15; under a bare tag only
  `v1-e31-t09`'s test 1; inside a body it must still be formatted as body 3; with no card open it
  is re-read and dropped 1; the look-ahead counts a long guess as a cite 1.

**What the first pass found**, before this one. 89 mutants on an earlier tree:

- **Two were not caught, and each got a test:** a cite standing at the head of a file with nothing
  above it, and a long guess whose only name and year is a sentence opener.
- **Four were caught only by an unpacking error,** where a test took `(card,) = cards` and the
  mutant changed the number of cards. The count is asserted first now, so those fail by assertion.
- **Three checks were deleted because no input reaches them:** the long cite line's lower bound
  (the short rule has already taken such a line), the wiki rule id in the length test (every
  other guess is bounded at 2,000 already), and a guard in `_opens_in_bold` for a paragraph with
  no visible run (it is asked only of a paragraph that opens with a name and a year).

## The corpus, before and after

Read-only, both parsers in one process over the same bytes. "Before" is `2026.10.10-docx-2`, and
its figures equal the stored directory's. Run three times: once to find problems, once on
`03487cd`, and once on the final source `c30ebae`. The last two are identical in every count.

| Caselist | Cards before | After | `CITE_ONLY` before | After | No tag before | After | With a cite before | After | Tagged, no cite before | After |
|---|---|---|---|---|---|---|---|---|---|---|
| hsld26 | 64,678 | 64,693 | 729 | 602 | 1,356 | 1,347 | 57,409 | 59,399 | 7,269 | 5,294 |
| hspf26 | 42,906 | 43,264 | 400 | 347 | 1,907 | 2,250 | 25,243 | 30,946 | 17,663 | 12,318 |
| hspolicy26 | 82,565 | 82,380 | 1,036 | 998 | 1,094 | 902 | 74,953 | 76,327 | 7,612 | 6,053 |
| openev | 8,056 | 8,033 | 89 | 78 | 98 | 73 | 6,976 | 7,267 | 1,080 | 766 |
| **Total** | 198,205 | 198,370 | 2,254 | 2,025 | 4,455 | 4,572 | 164,581 | 173,939 | 33,624 | 24,431 |

- **No card is `ABBREVIATED`,** before or after.
- **183,575 stored cards are identical in every field** but the parser version.
- **13,521 keep their range and differ.** 9,181 gain a cite: 6,954 where it had been read as
  nothing and 2,227 where it had been the first paragraph of the evidence text. 3,883 differ only
  in rule ids or confidence. 220 go from `CITE_ONLY` to `FULL` and 19 from `FULL` to `CITE_ONLY`:
  14 cards that are only a cite, and the five in Read these first.
- **61 cards lose a cite.** Their only cite was a line such as *In 2019 …*. They are tagged cards
  with a body and no cite now.
- **1,109 ranges are gone and 1,274 are new.** 307 cards are where none was stored, each behind a
  cite that had been read as nothing. 23 are gone with nothing in their place.
- **586 paragraphs leave** (195,408 characters): 440 are the whole of those 23 cards; 108 are
  short plain lines that had been cite text and are read as nothing, as the classifier reads any
  short plain line. **9,998 join** (6,473,442 characters): 7,527 cites and 2,368 body paragraphs
  of cards that were not stored.
- **hspf26 gains 358 cards and 343 with no tag.** Those files often write no tags, and their
  cites are read now. **hspolicy26 loses 185 cards,** mostly ones a sentence had split.

**One problem the first run found, fixed before the others.** The rule for a cite wholly inside a
bracket split eight cards: the paragraph above was a guessed cite the assembly re-reads as body,
so the bracketed line stood inside a body. `96ffc64` holds it, with a fixture that failed first.

## Files changed

- `packages/debate_core/src/debate_core/evidence/style_classifier.py`: the written-out list of
  sentence openers; `first_name_and_year` and `is_a_cite_wholly_in_brackets`, exported for the
  parser; the style rule past the profile's bound; `_long_cite_line_match`; five constants with
  the counts they were set from.
- `packages/debate_core/src/debate_core/integrations/docx_parser/parser.py`:
  `_read_bracketed_cites_where_a_cite_stands`, `_is_longer_than_a_cite_entry`,
  `_is_a_guess_a_body_may_take` (which three places now share),
  `A_CITE_ENTRY_NAMES_ITS_SOURCE_WITHIN_CHARACTERS`, and the version.
- `tests/evals/parser/cite_shapes.py` and `test_cite_shapes.py`: the 62 labelled examples and
  their scoring. The evaluation set's synthetic half.
- `packages/debate_core/tests/integrations/docx_parser/test_cite_detection.py`: every example
  read on its own, ac3, and each rule at its edges. 434 tests.
- `packages/debate_core/tests/evidence/test_style_classifier_cite_shapes.py`: the classifier's
  rules described in code. 103 tests.
- `packages/debate_core/tests/integrations/docx_parser/test_first_corpus_parse_findings.py`: one
  fixture's text, see Deviation 5.
- `tests/fixtures/debate_files/structural/*.expected.json`: ten lines, each `parser_version`.
- `docs/data/caselist-parse-report.md`: a section on the five shapes, the rules and the expected
  re-parse. `docs/data/parsed-card-store.md`: the version, the new rule ids, and a card with no
  cite.

Nothing in the files of `v1-e31-t11`, `v1-e34-t22` or `v1-e30-t13`. The style profile is not
changed, so `profile_version` is not either.

## Deviations from the spec

1. **(3) is counted as the shape, not as the 337.** The spec's figure is the cards one earlier
   rule re-read. The shape it names, a card with no cite, is 33,624 tagged cards. I counted both,
   and the fix reaches 9,193 cards, 113 of them among the 337. ac1 passes as measured; as written
   it names a count the store does not support.
2. **The fix for (3) is a change to the cite-line guess's bound,** which the spec does not list.
   Under (1) it lists two faults of that guess, and its 400-character bound is a third.
3. **(4) is fixed for cites with no initials, and for a cite that opens with its bracket,** as
   well as the shape seen in the sample. ac3 says "whatever the cite's bracket and initials form",
   and I cannot see the sample.
4. **Three commands ran past two minutes.** All were read-only passes chained in one command: 122
   seconds, 124 seconds, and one the harness moved to the background at 170 seconds, which took
   about four minutes. This Mac was shared with three other sessions and its load average reached
   45. From then on I ran at most two shards a command, each command 50 to 110 seconds.
5. **One of `v1-e31-t09`'s fixtures has different text.** `OPENS_WITH_A_YEAR` read *In 2019 the
   operator …*, and four tests pinned the assembly's rule id on it. The classifier no longer
   guesses that line, so it reads *March 2019 was …*: a month is still a guess, and the four tests
   hold the earlier rule as before.
6. **Ten structural expectations changed by one line each,** the `parser_version`. No expected
   card changed.
7. **I ran two things the spec calls operator-run, both read-only and short:** the parse dry run
   from this branch (1.7 s, wrote nothing) and a count of the stored cards with `jq` (52 s).
   Working agreement 2 allows a read-only command that finishes in seconds.
8. **The two corrected evaluation files were read** from where the path map says they are, for
   scores and, for the paragraphs the labels and the parser disagree on, lengths and formatting
   flags. No text left the script.
9. **One example is an expected failure.** A second line of a cite in small print is labelled a
   cite and read as body, before and after. Its test is `xfail(strict=True)`, so it says when
   that changes.
10. **A labelling choice.** A tag with a body and no cite is labelled as a card. The labelling
    guide says a card must have a cite paragraph, in a sentence about a body with no cite *and
    no tag*. I took the reading a debater would: a card missing its cite. Three examples.
11. **Read-only passes, all outside the repository and the data directory:** the census of cite
    shapes three times (once to measure, twice after adding fields, one of those lost to a field
    name of mine that overwrote another), and the side-by-side comparison three times.
12. **The scratch files are still there:** 3.7 GB of counts, flags, lengths and digests in the
    session's temporary directory, kept until the task closes in case you want another cut.
13. **The synthetic table is printed by the module itself** (`python -m
    tests.evals.parser.cite_shapes`), since `scripts/` is not in this task's packages.

## Decisions and assumptions

**1. Each shape: defect or correct output.** In [The five shapes](#the-five-shapes), with counts
and reasons.

**2. Which are fixed here.** (1), (2), (4) and the part of (3) a formatting rule settles. (5) is
left. What needs a model is left to `v1-e31-t13`.

**3. The version: `2026.10.12-docx-3`.** The date the output changed and the next counter, as the
two before it.

Choices inside those, each with the alternative:

- **(3): fix the bold cite line now.** *Alternative:* hold (3) to the 337, report the 33,624 and
  file the bound as a task. That is the smaller change. I did not take it because the counts are
  one-sided (8,394 of 8,426 name a credential or hold a link; 7,821 of 7,873 under a tag have a
  body below), the rule is a formatting rule of the kind the kickoff asks for, and leaving it
  means another parser version and another 30-minute re-parse for the same cards. It is separable:
  one branch of one function, one rule id and its own tests.
- **The sentence-opener list is short on purpose.** No months, no seasons, none of the short words
  that are also surnames, and case is kept so an acronym stays an author. *Alternative:* a wider
  list would take 29 more lines that open with a month, and risks a real cite by an author called
  May or March.
- **A line that opens in bold is left to the old reading** even behind a sentence opener: 160
  lines. *Alternative:* take those too. Without the cite-line reading, a bold line of heading size
  falls to the rule that makes it a tag, which I could not check.
- **The length rule for a guessed entry lives in the assembly, not the classifier.** The spec says
  the wiki guess "has no length bound". *Alternative:* bound it in the classifier. Then a long
  guess with no card open would be body with no card and be dropped, and `v1-e31-t09` kept those
  (16 paragraphs) on purpose.
- **300 characters for where a cite entry names its source,** not the 40 used for a styled cite.
  It is the cautious side: 67 long guesses with a name and year between the front and 300 are
  left as cites. *Alternative:* 40 would re-read at least 49 more as body.
- **A highlighted paragraph is never taken by the three new cite rules.** *Alternative:* take it
  when a body follows. One corrected evaluation file holds a highlighted cite, so the premise that
  nobody highlights a citation is not always true. But a card written as one paragraph is
  highlighted too, and taking one of those would empty its evidence text. 593 and 26 paragraphs
  are left for this.
- **A cite wholly inside a bracket is decided by where it stands, in the assembly.** In the
  classifier it would also take the 395 that sit inside a body, which are a source's own
  references, and split their cards.
- **4,000 characters for a styled cite and 2,000 for an unstyled one.** The style is the author's
  mark, so it is trusted further. The longest styled one in the corpus is 3,283.
- **A signature after the bracket is 30 characters or fewer,** not initials only. Cutters sign with
  names and handles as often as initials: 77,042 of the 82,928 cites of this shape already read
  have 30 or fewer characters there.
- **The profile is untouched.** Its model is in `debate_core.domain`, outside this task's
  packages, so the new bounds are constants in the classifier beside the one already there.
- **`v1-e31-t09`'s cite-style hold is left as it is,** though it costs five cards. See Read these
  first, 4.

**Assumptions.** A plain SHA-256 of a source is a join key, so no digest is in this report: the
operator's steps find their five files at run time. A build that carries this task will be
published after the merge; I do not know its tag.

## Operator follow-ups

These close the second half of ac4. They run only after:

1. the PM accepts this report;
2. the branch merges with `scripts/task pr v1-e31-t12-cite-detection --partial`;
3. `scripts/task finish v1-e31-t12-cite-detection --partial` closes it out;
4. Wednesday 2026-10-14's scheduled run has finished.

**Do steps 1 to 7 before installing a build that carries this task.** Step 8 is the install. The
agent's current build, `v0.1.0-dev.119`, does not carry it and goes on writing
`2026.10.10-docx-2`, which nothing here changes.

**What to know before starting.**

- **Time.** About 30 minutes for the parse, 18 for the second run, 15 for prod, and about 15 for
  the check by eye. Don't run any of this while `caselist pull` is running.
- **Disk.** A version directory is about 5.8 GB. The parse writes a second one beside
  `2026.10.10-docx-2`, which stays where it is, here and in both buckets.
- **Wednesday's pull adds sources.** The expected figures below are for the store as it stood on
  2026-10-12. After a pull, "sources", "to parse" and every count rise by what it imported, in the
  old directory and the new one alike. Step 2 takes the "before" counts at the moment you parse,
  so the comparison is exact either way.
- **If this is skipped,** nothing is lost. The first scheduled run on the new build does the full
  parse itself, takes about 30 minutes where it takes 20, and says so in `full_parses`. `openev`
  would stay on the old version until a camp file arrives.

**1. Start in the main checkout, on an updated `dev`** (seconds):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git status --short
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t12-cite-detection:'
export DEBATE_ENV=dev
uv run debate-research caselist runs --last 1
df -h ~/.debate-research
```

Expected: `dev`; `git status` prints nothing; `git log` prints one line; the last pull run has
finished; `df` shows **at least 8 GiB available**.

* **`git log` prints nothing:** the merge is not on `dev` yet. Stop.
* **Less than 8 GiB available:** stop, delete nothing, and send the `df` line.

**2. The dry run that shows a full parse is due, and the counts before** (about 2 minutes; writes
nothing under the data directory; needs no AWS session):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --dry-run | jq -c '.data | {caselist, version, fingerprint_version, sources, to_parse, skipped, suppressed}'; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.10-docx-2/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | "\(.completeness) \(if .tag == null then "no-tag" else "tagged" end) \(if .full_cite == "" then "no-cite" else "cite" end)"' | sort | uniq -c; done > ~/cites-before.txt
cat ~/cites-before.txt
find ~/.debate-research/dev/parsed/*/2026.10.10-docx-2 -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 > ~/parsed-docx-2-before.txt
cat ~/parsed-docx-2-before.txt
```

Expected from the first loop, for each caselist: `version` `2026.10.12-docx-3`,
`fingerprint_version` `card-fingerprint-v2`, **`to_parse` equal to `sources`**, `skipped` 0 and
`suppressed` 0. That is a full parse. On 2026-10-12 `sources` was 4,461 for hsld26, 2,657 for
hspolicy26, 3,906 for hspf26 and 102 for openev.

* **`version` is `2026.10.10-docx-2`:** this checkout does not carry the task. Stop.
* **`to_parse` is 0:** the new directory is already written. Go to step 4.

Expected in `~/cites-before.txt`, as the store stood on 2026-10-12 (I counted the stored
directory with this command):

| Caselist | `FULL tagged cite` | `FULL tagged no-cite` | `FULL no-tag cite` | `CITE_ONLY tagged cite` | `CITE_ONLY no-tag cite` |
|---|---|---|---|---|---|
| hsld26 | 55,594 | 7,269 | 1,086 | 459 | 270 |
| hspf26 | 23,088 | 17,663 | 1,755 | 248 | 152 |
| hspolicy26 | 73,178 | 7,612 | 739 | 681 | 355 |
| openev | 6,808 | 1,080 | 79 | 70 | 19 |

**3. The dev parse and publish** (about 30 minutes; the 2026-10-11 parse took 492 s, 611 s, 277 s
and 86 s). One caselist at a time.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-dev-evidence
export DEBATE_ENV=dev
uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/reparse3-dev-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/reparse3-dev-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/reparse3-dev-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish > ~/reparse3-dev-openev.json; echo "exit $?"
```

Expected: `exit 0` each time.

* **`exit 1` with `PARSE_FAILURE_RATE_EXCEEDED`:** not expected. Send the counts.
* **`PARSED_PUBLISH_INCOMPLETE`:** something was not confirmed in the bucket. Run the same line
  again.
* **`exit 3` with `STORE_ACCESS_DENIED`:** this Mac refused a directory under the data directory.
  The message says which; fix the permission and run the same line again.

**4. The counts to paste back** (about 3 minutes; prints counts, versions and sizes only):

```zsh
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, fingerprint_version, sources, parsed, cards, unsupported, failed, failure_rate, elapsed_seconds, publish: .publish.counts}' ~/reparse3-dev-${c}.json; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.12-docx-3/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | "\(.completeness) \(if .tag == null then "no-tag" else "tagged" end) \(if .full_cite == "" then "no-cite" else "cite" end)"' | sort | uniq -c; done > ~/cites-after.txt
cat ~/cites-after.txt
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.12-docx-3/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[].rule_ids[] | split(":")[0] | select(startswith("verbatim-cite-run-style") or startswith("heuristic-cite-line") or startswith("assembly-bracketed") or startswith("heuristic-wiki"))' | sort | uniq -c; done
find ~/.debate-research/dev/parsed/*/2026.10.10-docx-2 -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | diff - ~/parsed-docx-2-before.txt && echo "old directories unchanged"
ls -d ~/.debate-research/dev/parsed/*/*
du -sh ~/.debate-research/dev/parsed
```

Expected, if no source was imported after 2026-10-12. The first loop:

| Caselist | Sources | Parsed | Unsupported | Failed | Cards | Uploaded |
|---|---|---|---|---|---|---|
| hsld26 | 4,461 | 4,354 | 101 | 6 | 64,693 | 4,464 |
| hspolicy26 | 2,657 | 2,629 | 28 | 0 | 82,380 | 2,660 |
| hspf26 | 3,906 | 2,650 | 1,256 | 0 | 43,264 | 3,909 |
| openev | 102 | 101 | 0 | 1 | 8,033 | 105 |
| **Total** | 11,126 | 9,734 | 1,385 | 7 | 198,370 | 11,138 |

The same seven failures as on 2026-10-11. `~/cites-after.txt`, and **no line beginning
`ABBREVIATED`**:

| Caselist | `FULL tagged cite` | `FULL tagged no-cite` | `FULL no-tag cite` | `CITE_ONLY tagged cite` | `CITE_ONLY no-tag cite` | Cards |
|---|---|---|---|---|---|---|
| hsld26 | 57,697 | 5,294 | 1,100 | 355 | 247 | 64,693 |
| hspf26 | 28,467 | 12,318 | 2,132 | 229 | 118 | 43,264 |
| hspolicy26 | 74,762 | 6,053 | 567 | 663 | 335 | 82,380 |
| openev | 7,130 | 766 | 59 | 64 | 14 | 8,033 |
| **Total** | 168,056 | 24,431 | 3,858 | 1,311 | 714 | 198,370 |

Against the table in step 2: cards with a cite rise from 164,581 to 173,939, tagged cards with no
cite fall from 33,624 to 24,431, `CITE_ONLY` falls from 2,254 to 2,025, and cards with no tag rise
from 4,455 to 4,572.

The third loop, the rule that read each cite paragraph:

| Rule | hsld26 | hspf26 | hspolicy26 | openev | Total |
|---|---|---|---|---|---|
| `verbatim-cite-run-style` | 52,424 | 9,595 | 70,449 | 6,544 | 139,012 |
| `verbatim-cite-run-style-past-the-profile-bound` | 407 | 118 | 611 | 85 | 1,221 |
| `heuristic-cite-line-author-year` | 5,633 | 15,285 | 2,786 | 556 | 24,260 |
| `heuristic-cite-line-bold-author-year` | 1,637 | 5,570 | 1,017 | 202 | 8,426 |
| `heuristic-cite-line-bracketed` | 26 | 175 | 20 | 2 | 223 |
| `assembly-bracketed-cite-before-the-body` | 125 | 47 | 56 | 56 | 284 |
| `heuristic-wiki-cite-entry` | 145 | 221 | 279 | 24 | 669 |

* **The `diff` line** prints "old directories unchanged".
* **`ls`** shows two directories for each caselist, and **`du`** about 11.6 GB.
* **A count that differs with no import in between** is worth sending back before prod.
* **After Wednesday's pull** every figure is a little higher than these. Send the two text files
  and the loops' output as they are.

**5. The second run, which must parse and upload nothing** (about 18 minutes; it is the rebuild,
which took 314 s, 473 s, 193 s and 71 s on 2026-10-11):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --publish | jq -c '.data | {caselist, version, attempted, skipped, elapsed_seconds, uploaded: .publish.counts.uploaded}'; done
uv run debate-research store ls parsed/hsld26/2026.10.12-docx-3/index.jsonl
```

Expected: `attempted` 0, `skipped` equal to the sources, and `uploaded` 0 for each caselist;
`store ls` lists 1 object.

**6. Five files, by eye** (about 15 minutes). Each file is the source with the most cards read by
one rule. The block finds it, opens it in Word, and prints five of those cards: completeness,
tag, short cite, the first 80 characters of the cite, and the first 60 of the evidence text. Set
`C` and `R` from the table, paste the block, and repeat for each row.

| File | `C` | `R` |
|---|---|---|
| 1 | `hspf26` | `heuristic-cite-line-bold-author-year` |
| 2 | `hspolicy26` | `verbatim-cite-run-style-past-the-profile-bound` |
| 3 | `hspf26` | `heuristic-cite-line-bracketed` |
| 4 | `hsld26` | `assembly-bracketed-cite-before-the-body` |
| 5 | `hsld26` | `assembly-cite-guess-after-card-cite:heuristic-wiki-cite-entry` |

```zsh
cd ~/.debate-research/dev/parsed
C=hspf26
R=heuristic-cite-line-bold-author-year
D=$(find ${C}/2026.10.12-docx-3/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r --arg r "${R}" 'select(.record == "document") | "\([.document.cards[] | select(any(.rule_ids[]; startswith($r)))] | length) \(.source_sha256)"' | sort -rn | head -1 | cut -d' ' -f2)
cp -f ~/.debate-research/dev/blobs/sha256/${D:0:2}/${D:2:2}/${D} /tmp/cite-check.docx
open /tmp/cite-check.docx
jq -r --arg r "${R}" 'select(.record == "document") | [.document.cards[] | select(any(.rule_ids[]; startswith($r)))][:5][] | "\(.completeness) | \(.tag) | \(.short_cite) | \(.full_cite[:80]) | \(.evidence_text[:60])"' ${C}/2026.10.12-docx-3/sha256/${D:0:2}/${D:2:2}/${D}.jsonl
```

For each of the five cards printed, find it in the document by its tag and answer three
questions. Files 1 to 4 test a cite that is read now; file 5 tests a body that is read now.

| Question | Right when |
|---|---|
| Is the tag the card's tag? | The printed tag is the line above the card's cite in the document |
| Is the cite the card's cite? | The printed cite starts where the document's cite starts, and for files 1 to 4 it is a citation, not a sentence of the card |
| Is the evidence the card's text? | The printed evidence starts where the card's quoted text starts, and does not begin with the citation |

Record tallies only: for each file, how many of its five cards are right on each question, 25
cards and 75 answers in all. The files, tags and cites are real disclosures, so nothing from them
goes in a message or a document. Then:

```zsh
rm -f /tmp/cite-check.docx
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
```

* **A cite printed for files 1 to 4 that is a sentence of the card,** or evidence that begins
  with the citation: that is a wrong reading by a new rule. Do not run step 7; send the tally and
  the row.
* **Fewer than five cards printed:** that file has fewer. Count what is there.

**7. The prod publish**, from the same dev data directory, only after dev looks right and the
check by eye is clean (about 15 minutes; nothing is parsed again):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research --json caselist parse --caselist hsld26 --dry-run | jq -c '.data | {caselist, version, fingerprint_version, to_parse, skipped}'
uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/reparse3-prod-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/reparse3-prod-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/reparse3-prod-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/reparse3-prod-openev.json; echo "exit $?"
uv run debate-research store ls parsed/hsld26/2026.10.12-docx-3/index.jsonl
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

* **`DEBATE_STORAGE__DATA_DIR` is the point of this block.** Without it the prod profile reads an
  empty `~/.debate-research/prod` and publishes nothing.
* **The dry run** must show `version` `2026.10.12-docx-3`, `to_parse` 0 and `skipped` equal to
  hsld26's sources. If `to_parse` is not 0, the data directory is wrong: stop.
* **Each publish** should exit 0 and upload what dev's did.
* **Paste back** the first loop of step 4 with `reparse3-prod-` in place of `reparse3-dev-`.
* **The `unset` at the end matters.** A shell left on prod with the dev data directory is how the
  next command would write to prod unchecked.
* **Prod's `2026.10.10-docx-2` prefixes stay,** as dev's do.

**8. Install the build that carries this task, and reload the agent** (minutes). On a day other
than Wednesday morning. Follow the scheduled-sync runbook: `scripts/install_channel.sh` with the
tag, then its Step 2 and Step 3, then `ops/launchd/install.sh --check-launchd`. I have not
written those commands out, because the tag does not exist yet and the runbook is their source.
Afterwards, as the agent runs it:

```zsh
cd ~
DEBATE_ENV=dev debate-research --json caselist parse --caselist hsld26 --dry-run | jq -c '.data | {caselist, version, to_parse, skipped}'
```

Expected: `version` `2026.10.12-docx-3` and `to_parse` 0.

* **`version` is `2026.10.10-docx-2`:** the installed build does not carry this task, and the
  agent would go on writing the old directory. Install a later tag.
* **`to_parse` equals the sources:** the by-hand parse wrote a different data directory from the
  one the agent reads. Stop and send the line.
* **The next scheduled run** should report `full_parses` 0.

**9. Record it.** Whoever closes ac4 adds the re-parse's counts to
`docs/data/caselist-parse-report.md` beside the read-only figures, and sets the Goal to
`Succeeded` in a small spec PR. The JSON summaries hold counts, digests and keys, and no names or
paths. Keep them out of the repository all the same.

## Follow-up work

- **A cite behind a first name or a title (E31; the largest thing left).** 7,200 tagged cards with
  no cite have a name and a year starting within the first 40 characters of the line under the
  tag, but not at its front: 5,396 read as nothing, 1,804 as the body's first paragraph. The long
  cite line asks that the name and year open the line. Whether bold on the name, or the bracket
  after it, is enough for these is a formatting question with counts to take first.
- **A cite in a paragraph style that resolves to nothing (E31).** 957 lines shaped like a cite,
  904 by an alias, sit in a style such as a list or web style that the profile maps to no unit. A
  paragraph style is read before every cite rule, so none sees them. The fix is in the profile's
  aliases or in the order of the classifier's rules, and it touches every converted file.
- **Highlighted cites (labelled evaluation).** 593 lines open in bold with a name and a year and
  hold highlighting; 344 are a name and year and one bracket; 26 carry a styled name and year at
  the head. One corrected evaluation file has such a paragraph labelled a cite. A card written as
  one paragraph looks the same. A rule that takes one only when a body follows would reach about
  half, by the counts for the 26.
- **`v1-e31-t09`'s cite-style hold (E31, small).** A guessed cite that carries a cite-style run
  is held as a cite at any length. 19 such paragraphs over 2,000 characters, formatted as body,
  stand under a card's cite, five of them new with this task. By the measure under (2), a style
  that marks no name and year at the head is emphasis. Changing it changes that task's fixture
  for a 300-word paragraph, so it is yours to rule on.
- **Short plain lines inside a body are read as nothing (E31).** 108 sentences that open with a
  word such as *In* were cite text and are in no card now. They join every other short,
  unformatted line of a body, which the classifier has always dropped. The size of that whole
  population is not measured here.
- **The other cites the corrected files show.** Four of 177 to 395 characters with no name and
  year at their front. Nothing by shape tells them from a body's first line: `v1-e31-t13`.
- **Sentence openers left:** 160 lines that open in bold and 72 in capitals are still cites, and
  29 that open with a month.
- **The second line of a cite in small print:** at most 25 of the 218. Left.
- **The dry run still says `new_version: false` for a new parser version** (`v1-e31-t16`). The
  operator steps do not rely on it.
- **`docs/runbooks/caselist-scheduled-sync.md` names `2026.10.10-docx-2`** in its timings and in
  "After a release that bumps the parser version". It is right as history. The procedure there is
  what step 8 follows, and it is outside this task's packages.
- **`v1-e31-t11`:** the evidence text differs for 2,515 cards that keep their range, and 1,109
  ranges are replaced by 1,274, so their fingerprints differ.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
