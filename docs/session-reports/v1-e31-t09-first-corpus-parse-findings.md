# Session report: v1-e31-t09-first-corpus-parse-findings

| | |
|---|---|
| Task | `v1-e31-t09-first-corpus-parse-findings` — Parser findings from the first full-corpus parse |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t09-first-corpus-parse-findings.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t09-first-corpus-parse-findings.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t09-first-corpus-parse-findings` |
| Session status | PARTIAL: the session's work is done; the operator's re-parse (ac4) is NOT RUN |

## Summary

The first full-corpus parse left two findings, and both were parser defects. **The 23
`FORBIDDEN_XML_CONSTRUCT` refusals declare nothing.** The refusal's scan looked for the words
`SYSTEM "` and `PUBLIC '` anywhere in a part, and all 23 files simply say *the system "…"* or
*public '…'* in a paragraph of card text. **About 11,000 of the 15,528 empty-tag cards are not
cards the documents hold.** A paragraph inside a card's body, guessed by the classifier to be a
cite, closed the card and opened another with no tag; and a blank line in `Heading 4` was read as a
tag. Both are fixed in the parser's assembly, `parser_version` is `2026.10.10-docx-2`, and a
read-only run of that parser over the same 9,741 DOCX sources gives 23 more files parsed, 7
failures instead of 30, and 4,446 cards with no tag instead of 15,528. The five `MALFORMED_XML`
files, the `NOT_A_ZIP` and the `COMPRESSION_RATIO_EXCEEDED` are genuine and stay refused. ac5, the
parsed store's `PermissionError`, is done.

**The Goal stays `InProgress`.** ac4's second half, the operator's re-parse in dev, can only run
after this branch merges, and is marked NOT RUN. Merge with
`scripts/task pr v1-e31-t09-first-corpus-parse-findings --partial`.

**Read first:**

- **`ABBREVIATED` is wrong for most of the cards it marks, and I did not change it.** A card is
  `ABBREVIATED` when its body or cite holds an ellipsis anywhere. Of the 22,443 stored, 176 have a
  body of 300 characters or fewer and 21,278 one longer than 1,000. The operator's sample shows it
  after the fix: its first card, now read whole, is `ABBREVIATED`. `v1-e31-t08` measures
  abbreviated disclosures by this field. It is the first item under Follow-up work, and one test
  here is a strict `xfail` that records it.
- **`ParsedCard.tag` is still a string in memory; "no tag" is `null` in every record**
  (Deviation 3). Making the attribute itself `str | None` breaks `caselist_card_stats.py`, which
  sorts and compares it as text and which I may not edit. The store's records never carry `""`,
  and `ParsedCard.has_tag` is how code asks.
- **A UTF-16 route past the refusal was open, and is closed** (Deviation 5). A document part
  written in UTF-16 with a `DOCTYPE` opened under the old scan and under mine: the scan reads bytes.
  An internal entity in an attribute value was expanded by the parser. Not in your list, but it is
  the guard I was changing.
- **The blank-line rule reaches further than the 39 empty tags** (Deviation 6). 1,847 stored cards
  carry an empty string in their section path from the same cause.
- **4,446 cards with no tag remain, and I cannot say how many are right.** The labelled evaluation
  has two corrected files and neither holds one.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `corpus-findings`: Refusals and empty tags diagnosed and fixed | Done, except the operator's re-parse | Diagnosed read-only against the dev store. Tests were written and committed red before any source change (`815ab76`: 90 failed, 68 passed). The final test set against the start commit's source: 114 failed, 894 passed. On the branch every test passes, and 38 of 39 mutants are caught. The re-parse is Operator follow-ups, below. |

## Acceptance criteria

Results are from `8f2e11d`, the branch tip before this report, rebased onto `origin/dev` at
`8c082b5`. The start commit after the rebase is `d08728b`.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a read-only diagnosis of the real refusals, counts and construct names only, recorded in the report: for each refusal reason, which construct or defect, in which part, and how many files | PASS | [The diagnosis](#the-diagnosis-ac1). Scratch scripts in the session's scratch directory read `~/.debate-research/dev/blobs` and `parsed` and wrote nothing there. Every figure is also in [`docs/data/caselist-parse-report.md`](../data/caselist-parse-report.md#what-the-refusals-and-the-empty-tags-were-v1-e31-t09). |
| **ac2**: every construct judged safe to accept has a synthetic fixture parsed after the change and refused before it, shown failing first; every construct still refused has a fixture showing the refusal stays | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_first_corpus_parse_findings.py` → `90 passed, 1 xfailed`. Accepted: six spellings of the words in body text, tags, cites and a style name (`TestProseThatNamesASystemOrThePublic`, 13 cases; all 13 `FORBIDDEN_XML_CONSTRUCT` before). Still refused: nine hostile variants, in the document part, in UTF-16, in the styles and relationships parts, and before any parser is built (`TestDeclarationsAreStillRefused`, 49 cases). The options: `TestTheXmlParserResolvesNothing`, 3 tests. [Shown failing first](#shown-failing-first). |
| **ac3**: cards with an empty tag counted per caselist and completeness; the rule that produces them identified on a synthetic fixture that reproduces the shape, and fixed (shown failing first) or justified | PASS | [Empty tags](#empty-tags-ac3). `TestABodyParagraphGuessedToBeACite` rebuilds the operator's sample from invented text: one card whose body runs through two paragraphs the classifier takes for cite entries. Before: four cards, two with no tag. After: two cards, each with its tag. `TestABlankLineInAStructuralStyle` is the second rule. `TestACiteThatIsStillACite` is what is justified as correct and left alone. |
| **ac4**, first half: if the parser changes, `parser_version` is bumped | PASS | `DOCX_PARSER_VERSION` is `2026.10.10-docx-2`. `TestTheParserVersion` (3 tests), and the ten structural fixtures' `test_the_committed_expectations_are_not_stale`. Reverting the bump fails 11 tests. `v1-e31-t06`'s `test_a_parser_version_bump_parses_everything_into_its_own_directory` already holds the new-directory mechanism. |
| **ac4**, second half: operator-run, a re-parse in dev writes a new version directory, and the report records the refusal counts and empty-tag counts before and after | **NOT RUN** | It needs the merged branch, about 30 minutes, and an AWS session. "Before" is recorded here. The "after" expected of it is in [Operator follow-ups](#operator-follow-ups), from a read-only run of the new parser over the same sources. |
| **ac5** (added by the PM, 2026-10-10): `LocalParsedStore` translates a `PermissionError` into `LocalStoreAccessDenied` naming "the parsed card store" through `refusals.py`; a listing of an unreadable tree raises; `caselist parse` exits 3 with `STORE_ACCESS_DENIED` and a hint naming `storage.data_dir`, shown failing first | PASS | `uv run pytest packages/debate_core/tests/integrations/local/test_refused_parsed_store.py` → `18 passed`. `uv run pytest packages/debate_cli/tests/test_caselist_parse.py` → `17 passed`, six of them new. [The parsed store](#the-parsed-store-ac5). |
| Node `corpus-findings`: `uv run pytest packages/debate_core/tests/integrations` | PASS | `733 passed, 1 xfailed in 6.11s` |
| Forbidden: accepting an XML entity declaration or external reference that the refusal guards against | PASS | Nine hostile variants are refused in four encodings and three parts. The parser's options are tested by what they stop. Mutants `xml-01` to `xml-08`: seven caught, one not ([Mutation testing](#mutation-testing)). |
| Forbidden: committing, quoting or logging any real disclosed file, tag, cite or card text | PASS | Every fixture is built in memory from invented text. No scratch script printed text: they print counts, rule ids, part names, code points and boolean features. Nothing from a scratch script is committed. |
| Forbidden: a school, team code, path or file name in any document or report | PASS | None. No digest or digest prefix is committed either, the sample's included. |
| t03's structural fixtures produce identical output | PASS | Before the ten `.expected.json` were touched, the new parser passed every content check on them: 80 of 80, with only the ten staleness checks failing on the version. `git diff d08728b 8f2e11d -- tests/fixtures` is ten lines, each `parser_version`. The ten `.docx` are byte-identical to `dev`'s. |
| Default suite, in two commands so each stays under two minutes | PASS | `uv run pytest -m "not slow and not live" packages --no-cov -q` → `3878 passed, 1 xfailed in 56.09s`. The same over `tests` → `1245 passed, 1 skipped, 1 warning in 41.65s`. The skip is the parser eval waiting on corrected labels; the warning is the smoke harness's blocked-socket check. The slow parser timing test: `1 passed in 3.42s`. |
| Static checks | PASS | `pyright` 0 errors; `lint-imports` 12 kept, 0 broken; `ruff check .` and `ruff format --check .` clean, 576 files; `check_thin_handlers.py` OK, 21 handlers; `check_links.py` OK; `check_command_blocks.py --base origin/dev` OK; `docs_index.py --check-descriptions` OK; `export_schemas.py --check` OK. |
| `uv run scripts/validate_specs.py` | PASS | `OK: 325 files, 38 epics, 267 tasks, 20 releases`. The phase is `InProgress`, deliberately. |

## The diagnosis (ac1)

Read on 2026-10-10 from the dev data directory, which still holds exactly what the first corpus
parse wrote. Files were told apart by sha256 prefix in the session's terminal only.

| Reason | Caselist | Files | The construct or defect | Part |
|---|---|---|---|---|
| `FORBIDDEN_XML_CONSTRUCT` | hspolicy26 | 19 | The words `system "` (16 files) or `system '` (3) in paragraph text. No `DOCTYPE`, no entity declaration | `word/document.xml`, inside `w:t` |
| `FORBIDDEN_XML_CONSTRUCT` | openev | 3 | The words `public '` (2 files), or `system '` and `system "` (1) | `word/document.xml`, inside `w:t` |
| `FORBIDDEN_XML_CONSTRUCT` | hspf26 | 1 | The words `public '` | `word/document.xml`, inside `w:t` |
| `MALFORMED_XML` | hsld26 | 3 | Four raw U+0001 control characters in the text, which XML 1.0 forbids | `word/document.xml`, inside `w:t` |
| `MALFORMED_XML` | hsld26 | 2 | One raw U+0002 and 26 raw U+FFFE in the text | `word/document.xml`, inside `w:t` |
| `NOT_A_ZIP` | hsld26 | 1 | A gzip stream holding a JSON document, 44 KB: the shape of CardMirror's native `.cmir` format | The whole file |
| `COMPRESSION_RATIO_EXCEEDED` | openev | 1 | One entry expands 278-fold against the limit of 200: a 1.9 MB page thumbnail stored as 7 KB | `docProps/thumbnail.emf` |

- **The 23 are one defect, and no tool's fingerprint explains it.** They are spread over three
  package shapes (7, 9 and 7 files). Each document part is well-formed UTF-8 with no document type,
  and each of the 27 matches sits inside the text of a `w:t` element. `_rels/.rels`,
  `[Content_Types].xml` and `word/styles.xml` of the 23 hold no match.
- **The five malformed files are CardMirror exports.** All five have the same eight parts, with
  `docProps/custom.xml` and no `docProps/app.xml`, and their one custom property is CardMirror's
  document id (its name only was read, never a value). 2,703 sources share that shape and 2,691 of
  them parse. The exporter wrote a character XML does not allow. The three U+0001 files are
  well-formed once those four characters are removed, so the characters are the whole defect
  there. They stay refused: removing a character is editing evidence text.
- **The `NOT_A_ZIP` is genuinely not a DOCX.** `docs/architecture/cardmirror-evaluation.md`
  describes `.cmir` as "a gzip-compressed JSON envelope", which is what the bytes are. I inflated
  at most 8 MB of it and read its first four bytes.
- **The compression ratio is left alone.** Of 9,738 distinct DOCX sources that open as a zip, 9,732
  have no entry above 50-fold, five have one between 50 and 100, and this is the only one above
  100. The file is plainly ordinary: the entry is the thumbnail Word saves, in a part the parser
  never opens. But the margin is 39%, not trivially small, so by your rule the limit stays. See
  Follow-up work for the change that would read it.

## Empty tags (ac3)

The store holds **15,528** cards with an empty tag out of 207,056 (7.5%), in 5,947 of its 9,711
parsed sources. Every one is `""`; none is whitespace.

| Caselist | `FULL` | `ABBREVIATED` | `CITE_ONLY` | Empty tags | Expected after: `FULL` | `ABBREVIATED` | `CITE_ONLY` | No tag |
|---|---|---|---|---|---|---|---|---|
| hsld26 | 1,554 | 2,227 | 821 | 4,602 | 869 | 198 | 286 | 1,353 |
| hspf26 | 2,688 | 585 | 372 | 3,645 | 1,566 | 170 | 167 | 1,903 |
| hspolicy26 | 2,995 | 3,192 | 695 | 6,882 | 532 | 204 | 356 | 1,092 |
| openev | 231 | 112 | 56 | 399 | 59 | 20 | 19 | 98 |
| **Total** | 7,468 | 6,116 | 1,944 | 15,528 | 3,026 | 592 | 828 | 4,446 |

**The rules.** I re-read every parsed source with the stored parser's own section reading and
mirrored its assembly. The mirror counts 15,528, the store's figure exactly.

| Rule in `parser.py` | Cards | Verdict |
|---|---|---|
| `_advance`: a cite arriving after a body closes the card and starts one with no tag | 14,387 | **Defect where the "cite" is a body paragraph.** The classifier's two cite heuristics fire on body text: `heuristic-wiki-cite-entry` on any paragraph holding an ellipsis and a name with a year (6,182 times here; 6,055 of those do not open with a cite and 3,344 are longer than 1,000 characters), and `heuristic-cite-line-author-year` on any paragraph of 400 characters or fewer that opens with a capitalised word and a number, such as *In 2019* (6,826). A cite style accounts for the other 1,379 |
| `_advance`: a cite with no card open starts one with no tag | 1,102 | **Correct.** After a block (505), loose text (290), a hat (147), an analytic (103), a pocket (38) or at the top of the file (19). The file gives the cite no tag |
| `_demote_tags_with_no_card` skips a blank `Heading 4`, which then opens a card | 39 | **Defect.** The blank line also stopped the real tag above it from seeing its card, so the tag became an analytic |

**The operator's sample is the first rule.** Its second and third stored cards are the middle and
the end of the first card's body: two paragraphs of small print that each hold an ellipsis and a
name with a year. The first was read as a cite entry, which made the rest of the body a card with
no tag, `ABBREVIATED` because its "cite" holds the ellipsis. The second was read the same way with
nothing after it: `CITE_ONLY`. Under the new parser that source has 10 cards where it had 12, none
without a tag, and its first card runs from its tag to its last body paragraph.

**The fix is in the assembly, because the classifier is `debate_core/evidence/` and not mine.** It
is also where the missing fact is: the classifier sees one paragraph and cannot know a body is
open.

- **A cite guessed inside an open body is body when it is formatted as body.** All of: a card is
  open and already has a body; the classifier's match is a heuristic, not a cite style; the
  paragraph is small print throughout or carries highlighting; it does not open with a bold run.
  The section becomes `EVIDENCE` with rule id `assembly-cite-guess-inside-card-body:<the guess>`
  and confidence at most 0.6, so every card it touched can be found. 11,872 paragraphs.
- **A blank line in a structural style is `OTHER`**, with rule id
  `assembly-empty-paragraph:<the style rule>`. 7,986 paragraphs. A blank line in a body style is
  left alone, so evidence text does not change.

**Why those conditions, from counts.** Among the 800 cite-line cites that start a card with
nothing open, which are likelier to be real, 92% open with a run that is bold or 13 point and 10%
are small print throughout. Among the 6,826 arriving inside a body it is the other way round: 77%
are small print throughout and 16% open bold or at 13 point. A bold opening in small print is
evidence both ways, so there the classifier's answer stands. Underline alone decides nothing: the
sample's own genuine cites carry underlined links.

**What stays, and how a reader should treat it.** 4,446 cards have no tag after the fix: 1,653
whose cite came from a cite style, 2,394 from the cite-line heuristic and 399 from the wiki
heuristic. A card with no tag and `CITE_ONLY` (828) is legitimate: a citation listed on its own,
with no claim and no text, to be treated as a citation and not as an argument. One with a body is
evidence with no claim line above it: the file is written that way, or it is a second card under
the previous card's tag. [`parsed-card-store.md`](../data/parsed-card-store.md#a-card-with-no-tag)
says this for readers. I cannot say how many of the 3,618 with a body are still a split.

**What the change did not touch.** 186,642 stored cards have the same paragraph range under the
new parser. Every one has the same evidence text, the same cite, the same tag and the same
completeness. 1,630 have a different section path, because the blank heading no longer puts an
empty string in it.

**The model.** `ParsedCard` now says which it is. `has_tag` is the question. A record writes "no
tag" as `"tag": null`, never `""`. A tag of nothing but whitespace is refused. `""` and `null` are
both read as "no tag", so the `2026.09.20-docx-1` directories stay readable.

## The parsed store (ac5)

`LocalParsedStore` raises `LocalStoreAccessDenied` for every refusal, with operation `list`, `read`
or `write`, the role "the parsed card store", the data-directory hint and the `PermissionError` as
its cause. `read_entries` walks with `files_under`, not `Path.rglob`.

| Call | Before: what an unreadable directory did | Now |
|---|---|---|
| `caselist parse`, `--dry-run`, `--reparse`, `--failures`, with `parsed/` unreadable | Exit 70, `INTERNAL_ERROR`, the data directory's path in the message | Exit 3, `STORE_ACCESS_DENIED`, the role and the hint, no path |
| `caselist parse --dry-run`, one fan-out directory unreadable | **Exit 0, with the sources filed there counted as never parsed** | Exit 3 |
| `caselist parse`, one fan-out directory unreadable | Would parse those sources again and fail writing them, exit 70 | Exit 3 before anything is parsed; the store is byte-identical afterwards |
| Another caselist's directory unreadable | Not reached | Not reached: the listing opens only the caselist and version asked for |
| A store that does not exist | Lists nothing, reads `None` | Unchanged |

- **One directory, one name.** `refusals.py` called `<data_dir>/parsed` "the parsed-file
  directory", which is what `v1-e34-t13`'s publisher and version store said. You asked for "the
  parsed card store" through `refusals.py`, so I changed the entry: both now say that. Two of
  t13's tests changed by that string (Deviation 4).
- **`caselist pull` has no parse stage wired yet**, so nothing in the scheduled sync changes.
  `v1-e34-t17` will find the refusal arriving as `STORE_ACCESS_DENIED`, a retryable code.

## Shown failing first

The tests were written and committed before any source change. At that commit (`815ab76`):
**90 failed, 68 passed**. The 68 are the existing tests of those files and the guards that must
hold both ways.

For the final set I checked out the start commit's `packages/debate_core/src` and
`packages/debate_cli/src` over the clean, committed tip, ran the six test paths the mutation runs
use, restored with `git checkout HEAD --`, and confirmed `git status --porcelain` was empty and
`git diff --quiet HEAD` held. Result: **114 failed, 894 passed, 1 skipped, 4 errors**. The four
errors are one fixture's own assertion, which calls `has_tag`. No test failed at collection.

| Finding | Test | Before | After |
|---|---|---|---|
| Prose refused as a declaration | `test_a_card_whose_text_quotes_a_word_after_system_or_public_is_read` ×6 | `FORBIDDEN_XML_CONSTRUCT` | One card, text exact |
| A UTF-16 declaration | `test_one_written_in_utf_16_is_refused_…` ×27 | `DID NOT RAISE`: the part opened | `FORBIDDEN_XML_CONSTRUCT` |
| The sample's shape | `test_the_file_holds_two_cards_and_each_has_its_tag` | Four cards, tags `[tag, "", "", tag]` | Two cards |
| The sample's body | `test_the_first_cards_body_runs_to_its_last_paragraph` | Body ends after two of six paragraphs | Whole body, elements 0 to 7 |
| A blank `Heading 4` under a tag | `test_a_blank_heading_4_under_a_tag_does_not_take_the_cards_tag` | Tag `""` | The tag |
| A blank `Heading 4` in a body | `test_a_blank_heading_4_inside_a_body_does_not_end_the_card` | The second half of the body is in no card | One card, whole body |
| A blank heading in a path | `test_a_blank_heading_closes_no_level_and_names_none` ×3 | `(…, "")` | The real headings |
| "No tag" in a record | `test_a_card_with_no_tag_is_stored_as_null_…` | `AttributeError`: no `has_tag` | `null` |
| A refused store | `test_a_parsed_store_this_machine_refuses_exits_three_…` ×4 | Exit 70 | Exit 3 |
| A partly refused store | `test_a_dry_run_over_a_partly_refused_store_…` | Exit 0 | Exit 3 |
| The version | `test_it_is_not_the_version_the_first_corpus_parse_wrote` | Equal | Different |

Three rows are honest about what "failing first" could show. The eight hostile variants in an
8-bit encoding were refused before and are refused now; their red is the nine
`…never_reaches_an_xml_parser` cases, and the mutants are their proof. Four of the model tests
fail on a missing attribute, `has_tag`, which is an error rather than a wrong answer; the other
eight fail on what the model did. And
`test_a_blank_heading_closes_no_level_and_names_none[Heading4]` passes both ways, because a blank
tag between a block and a tag harmed nothing.

## Mutation testing

A driver applied each mutant to the clean, committed tree, ran the tests, restored the files with
`git checkout HEAD --` and checked `git status --porcelain` and `git diff --quiet HEAD`. A mutant
whose target text is not found exactly once aborts and is not counted; none did. Each run had its
own new, empty `HYPOTHESIS_STORAGE_DIRECTORY`. The suite was 1,013 tests across six paths, 8 to 9
seconds a run. The 39 mutants ran in five batches, the longest 1 min 24 s. No catching test is
property-based, so Hypothesis generated nothing and there are no statistics to report. Every catch
is an assertion failure; none is a collection error. Two mutants also errored four tests through
one fixture's own assertion; those four are not in the counts below.

The runs were made before the rebase onto `8c082b5`, which brought in two generated files:
`git diff --quiet 6b2488a 8f2e11d -- packages tests plan_specs docs/data` holds.

**38 of 39 caught.** Yours first:

| Mutant | Caught | Tests failing | Examples |
|---|---|---|---|
| **Entity resolution turned on** (`resolve_entities=True`) | yes | 9 | the three option tests; six UTF-16 cases |
| **The hostile variant accepted**: both refusals removed | yes | 51 | every hostile test, and t03's two |
| The hostile variant: the byte scan removed | yes | 9 | `…never_reaches_an_xml_parser` |
| The hostile variant: the scan no longer looks for `DOCTYPE` | yes | 4 | the same, and the refusal's wording |
| The hostile variant: the check after parsing removed | yes | 27 | every UTF-16 case |
| **The empty-tag fix reverted**: the cite-guess rule | yes | 8 | the sample's tests |
| The empty-tag fix reverted: the blank-line rule | yes | 7 | the blank-line tests |
| The empty-tag fix reverted: both | yes | 15 | both groups |
| **`parser_version` not bumped** | yes | 11 | the version test; ten staleness checks |
| **The parsed store's `PermissionError` left raw**, in `version_directories` | yes | 6 | adapter ×2, CLI ×4 |
| Left raw, in the entries listing | yes | 8 | adapter ×6, CLI ×2 |
| Left raw, opening a source file | yes | 1 | the unopenable file |
| Left raw, in `read_document` | yes | 2 | the refused document |
| Left raw, in the aggregates | yes | 3 | index, failures, occurrences |
| Left raw, in a write | yes | 2 | source and aggregates |
| **Its listing swallowing the refusal** (`rglob`) | yes | 4 | the fan-out tests; the CLI dry run |
| The listing swallowing it, in `version_directories` | yes | 4 | adapter ×2, CLI |
| The listing swallowing it, in `directories_in` | yes | 3 | the refused root |

Mine:

| Mutant | Caught | Tests failing |
|---|---|---|
| External DTD loading turned on | yes | 10 |
| **Network access allowed** (`no_network=False`) | **no** | 0 |
| The old scan for the words restored | yes | 13 |
| The rule applies with no body open | yes | 1 |
| The rule second-guesses a cite style | yes | 1 |
| The rule ignores how the paragraph is formatted | yes | 3 |
| A bold name no longer keeps a cite | yes | 1 |
| Small print no longer counts as body | yes | 7 |
| Highlighting no longer counts as body | yes | 1 |
| Underline counts as body | yes | 1 |
| The blank-line rule reaches body lines | yes | 1 |
| A line of spaces is not blank | yes | 1 |
| The re-read paragraph keeps the unit `CITE` | yes | 8 |
| The re-read paragraph keeps the classifier's confidence | yes | 1 |
| "No tag" written as an empty string | yes | 2 |
| `null` not read as no tag | yes | 6 |
| A whitespace-only tag accepted | yes | 5 |
| `has_tag` always true | yes | 6 |
| A refused document reads as an absent one | yes | 1 |
| The role names the old directory | yes | 23 |
| The listing opens every caselist's directory | yes | 1 |

**The one not caught, `no_network=False`.** With entity resolution and DTD loading both off,
nothing asks the parser for a URL, so no offline test can tell the option from its absence. Working
agreement 8 says the honest outcome is usually to delete such a check. I kept it: it is the only
thing between a later change to either of the other two options and a fetch. It is pinned by
reading the code, not by a test, and I am saying so.

Eleven mutants are caught by one test each. Each guards a single branch with one test written for
it.

## The parser evaluation

**Not available as an evaluation.** This machine has the path map and the digest key, but 28 of
the 30 label files are still uncorrected pre-labels, so both tiers skip: `uv run pytest
tests/evals/parser -m eval -rs` → `2 skipped` ("28 of 30 full files are not yet corrected by a
person", "4 of 6 pr-subset files…"). There is no baseline to report against.

What I could measure honestly is smaller. I scored the two corrected files with the harness's own
`score_file`, before and after, in a scratch script. Both are team files, 60 paragraphs and 5
labelled cards in all, with no untagged card, so they say nothing about the cite-guess rule.

| On the two corrected files | `2026.09.20-docx-1` | `2026.10.10-docx-2` |
|---|---|---|
| TAG precision / recall / F1 | 0.714 / 0.833 / 0.769 | 1.000 / 0.833 / 0.909 |
| OTHER precision / recall / F1 | 0.909 / 0.833 / 0.870 | 0.923 / 1.000 / 0.960 |
| Every other unit | | unchanged |
| Card boundaries matched | 4 of 5 | 4 of 5 |
| Completeness correct | 4 of 4 | 4 of 4 |

The change is the blank-line rule: two blank `Heading 4` lines a person labelled `OTHER` and the
parser called `TAG`.

## Files changed

- `packages/debate_core/src/debate_core/integrations/docx_parser/`
  - `package.py`: the scan looks for `<!DOCTYPE` and `<!ENTITY` only; a parsed part that carries a
    document type is refused; `hardened_xml_parser()` is the one place the options are set.
  - `parser.py`: the blank-line rule, the cite-guess rule, `DOCX_PARSER_VERSION`, and the module
    docstring's list of what the assembly decides.
- `packages/debate_core/src/debate_core/domain/debate_files.py`: `ParsedCard.has_tag`, `null` for
  "no tag" in every record, a whitespace-only tag refused.
- `packages/debate_core/src/debate_core/integrations/local/`
  - `parsed_store.py`: every walk and read translated; `files_under` in place of `rglob`.
  - `refusals.py`: `directories_in`, `is_regular_file`, and the role "the parsed card store".
- Tests, new: `test_first_corpus_parse_findings.py` (91) and `test_refused_parsed_store.py` (18).
- Tests, extended: `test_debate_files.py` (12), `test_local_parsed_store.py` (4), the CLI's
  `test_caselist_parse.py` (6).
- Tests, changed by one string or constant: `test_refused_directories.py` and
  `test_refused_local_store_callers.py` (the role), `tests/evals/parser/test_parser_eval.py` (its
  synthetic baseline names the running parser).
- `tests/fixtures/debate_files/structural/*.expected.json`: `parser_version`, ten lines.
- Docs: `docs/data/caselist-parse-report.md` (the diagnosis and the counts) and
  `docs/data/parsed-card-store.md` (the versions, a card with no tag, what `ABBREVIATED` means
  today, a refused directory).
- `plan_specs/v1/e31-debate-file-parsing/t09-first-corpus-parse-findings.yaml`: ac5.

## Deviations from the spec

1. **ac5 was added to the spec by the PM on 2026-10-10**, with `debate_core.integrations.local`
   authorised for it. It is committed as your wording.
2. **Two test files outside `constraints.packages` changed.**
   `packages/debate_cli/tests/test_caselist_parse.py` gained six tests, because ac5 asks for the
   command's exit code and that is where the command is tested. No CLI source changed: the exit
   and the hint come from `v1-e01-t20`'s rule. `tests/evals/parser/test_parser_eval.py` changed in
   one constant: its synthetic baseline pinned `2026.09.20-docx-1` as a literal, so the bump made
   the gate add a note the test does not expect. It now names the running parser. The note itself
   has its own test in `test_metrics.py`.
3. **`ParsedCard.tag` is not `str | None`.** You asked that the store's records never carry an
   empty string for "no tag" and that `ParsedCard` say which it is. Both hold, but the attribute is
   still a string, `""` when there is none. `caselist_card_stats.py` puts it in a
   `Counter[tuple[str, str]]` and takes a `min` over those tuples, and `CardOccurrence.tag` is a
   `str`. With `None` the first fails pyright and the second fails at run time, and I may not edit
   that file. If you want the attribute changed, it is two lines there and one in
   `card_occurrence.py`, after `v1-e31-t08` merges.
4. **`refusals.py`'s role for `<data_dir>/parsed` changed from "the parsed-file directory" to "the
   parsed card store"**, so the object store and version store that `v1-e34-t13` translated now
   say that too. Two of t13's assertions changed by the string.
5. **A refusal you did not ask for: any document type, in any encoding.** While showing that
   narrowing the scan weakens nothing, I found that a part in UTF-16 with a `DOCTYPE` opens, before
   my change and after it, because the scan reads bytes. The parser left entities in text alone,
   but expanded an internal entity inside an attribute value. `_parse_xml` now refuses a parsed
   part whose tree carries a document type. Such a part does reach the hardened parser before it
   is refused; a declaration in an 8-bit encoding still never does, and a test holds that.
6. **The blank-line rule covers every structural style, not only `Heading 4`.** The 39 empty tags
   come from blank tags. The same reading put an empty string in 1,847 cards' section paths, reset
   the heading levels below a blank pocket, hat or block, and ended a card at a blank analytic
   line, dropping the body under it. One rule fixes all of them. It changes no evidence text.
7. **One read-only scratch run took 126 seconds**, six over the line. I ran the after-fix
   comparison one caselist at a time to keep each under two minutes and misjudged hspolicy26, whose
   earlier section-only pass took 38 seconds. It read the dev store and wrote nothing.
8. **I rebased onto `origin/dev`** when it moved by one commit of generated files, which is what
   `scripts/task sync` does. The rebase was clean and nothing was pushed.
9. **One test is a strict `xfail`.** `test_the_first_card_is_a_full_card` asserts what the fixture
   holds, a whole card, and fails because of the `ABBREVIATED` rule. I would rather the suite
   record a known wrong answer than assert it as the right one.
10. **`PARSED_STORE_SCHEMA_VERSION` is still 1**, though a card's `tag` may now be `null`. The
    constant is in `application/ports`, outside my packages, and nothing reads a stored card except
    through `ParsedCard`, which reads both. A `jq` reader that calls a string function on `.tag`
    would need a null check.

## Decisions and assumptions

- **Why the scan can drop the words.** XML allows an external identifier, `SYSTEM` or `PUBLIC`, in
  three declarations only: a document type, an entity and a notation. The last two can only be
  written inside the first. So a part with no `<!DOCTYPE` holds none, and the words elsewhere are
  character data. Nothing the old scan stopped gets through the new one.
- **Why accepting a refused file bumps the version.** A refusal is a recorded entry, and the skip
  key is the digest and the two versions. Under the same version the 23 files would be skipped for
  good. The bump is what makes the next run try them.
- **The version's name.** `2026.10.10-docx-2`: the date of the change and the next number. It
  sorts after `2026.09.20-docx-1`, which the store's ordering needs, and a test holds that.
- **The fixtures are built in memory, not committed as `.docx`.** `tests/fixtures/…/structural`
  is capped at ten files by a test and written by a script in `scripts/`, outside my packages.
  Each file here is spelled out paragraph by paragraph in the test, with its expected cards
  written by hand beside it.
- **The regenerated `.docx` were not committed.** The generator rewrote all ten with a different
  zip timestamp and identical parts, because the builder gained a fixed timestamp after they were
  first written. I restored them, so they are byte-identical to `dev`'s.
- **"Formatted as body" uses the profile's own shrink rule** and the classifier's own
  `has_highlighted_run`. No new threshold was introduced.
- **A document type that declares nothing is refused too.** It is harmless, and it is also
  something no Word package has.
- **The property name read from `docProps/custom.xml`.** That part is on the parser's never-read
  list because its values can name a person. A scratch script read the property *names* of the
  five malformed files, to name the generator as you allowed. The parser still never opens it.
- **Nothing of yours was written.** The dev data directory was read by scratch scripts kept
  outside the repository. I did not run `debate-research` against it, not even `--dry-run`, because
  I could not rule out that opening the environment writes something.

## Operator follow-ups

These close ac4. They run only after this sequence:

1. The PM accepts the report.
2. The branch merges with `scripts/task pr v1-e31-t09-first-corpus-parse-findings --partial`.
3. `scripts/task finish v1-e31-t09-first-corpus-parse-findings --partial` closes it out.

Don't run them while `caselist pull` is running.

**What to know before starting.**

- **Disk.** Each version directory is about 5.8 GB on this Mac and about 5.8 GB in each bucket.
  The re-parse writes a second one beside the first, and **the old one stays**, here and in both
  buckets. `~/.debate-research/dev/parsed` goes from 5.8 GB to about 11.6 GB. The disk had 14 GiB
  free on 2026-10-10.
- **`v1-e31-t08`.** If it has merged too, this one re-parse covers both: the parser version makes
  the new directory either way. The dry run prints the fingerprint version, so the output says
  which you have. The counts expected below are sources, cards and tags, which fingerprints do not
  change. Occurrences and clusters will differ from the first run's and are not predicted here.
- **A weekly pull since 2026-10-10** adds sources. "Sources" and "to parse" then rise by what it
  imported, and the other counts with them.

**1. Start in the main checkout, on an updated `dev`** (seconds):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git status --short
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t09-first-corpus-parse-findings:'
git log --oneline -1 --grep='^v1-e31-t08'
export DEBATE_ENV=dev
uv run debate-research caselist runs --last 1
df -h ~/.debate-research
```

Expected: `dev`; `git status` prints nothing; the first `git log` line is this task's squash-merge
commit; the last pull run has finished; at least 8 GiB free. If the first `git log` prints
nothing, the merge is not on `dev` yet: stop. The second prints a line only if `v1-e31-t08` has
merged, which is fine either way.

**2. The dry run, and a fingerprint of the old directories** (about a minute; writes nothing; needs
no AWS session):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --dry-run | jq -c '.data | {caselist, version, new_version, superseded, fingerprint_version, to_parse, skipped, suppressed}'; done
find ~/.debate-research/dev/parsed/*/2026.09.20-docx-1 -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 > ~/parsed-old-version-before.txt
cat ~/parsed-old-version-before.txt
```

Expected for each caselist: `version` `2026.10.10-docx-2`, `new_version` true, `superseded`
`2026.09.20-docx-1`, `skipped` 0 and `suppressed` 0. `to_parse` is 4,461 for hsld26, 2,657 for
hspolicy26, 3,906 for hspf26 and 102 for openev, as the store stood on 2026-10-10. If `version` is
anything else, the build is not this one: stop and paste the four lines back.

**3. The dev re-parse and publish** (about 30 minutes in all; the first full parse measured 518 s
for hsld26, 747 s for hspolicy26, 352 s for hspf26 and 106 s for openev). One caselist at a time.

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-dev-evidence
export DEBATE_ENV=dev
uv run debate-research --json caselist parse --caselist hsld26 --publish > ~/reparse-dev-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish > ~/reparse-dev-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish > ~/reparse-dev-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish > ~/reparse-dev-openev.json; echo "exit $?"
```

Expected: `exit 0` each time.

* **`exit 1` with `PARSE_FAILURE_RATE_EXCEEDED`:** not expected for any caselist. Send the counts.
* **`PARSED_PUBLISH_INCOMPLETE`:** something was not confirmed in the bucket. Run the same line
  again.
* **`exit 3` with `STORE_ACCESS_DENIED`:** this Mac refused a directory under the data directory.
  The message says which store; fix the permission and run the same line again.

**4. The counts to paste back** (about 2 minutes; prints counts and sizes only):

```zsh
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, superseded, fingerprint_version, sources, parsed, cards, unsupported, failed, failure_rate, store, elapsed_seconds, publish: .publish.counts}' ~/reparse-dev-${c}.json; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.10-docx-2/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | select(.tag == null) | .completeness' | sort | uniq -c; done
grep -rlF '"tag":""' ~/.debate-research/dev/parsed/*/2026.10.10-docx-2/sha256 | wc -l
find ~/.debate-research/dev/parsed/*/2026.09.20-docx-1 -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | diff - ~/parsed-old-version-before.txt && echo "old directories unchanged"
ls -d ~/.debate-research/dev/parsed/*/*
du -sh ~/.debate-research/dev/parsed
```

Expected, if no weekly pull has run since 2026-10-10:

| Caselist | Sources | Parsed | Unsupported | Failed, by reason | Failure rate | Cards | Uploaded |
|---|---|---|---|---|---|---|---|
| hsld26 | 4,461 | 4,354 | 101 | 6: `MALFORMED_XML` 5, `NOT_A_ZIP` 1 | 0.14% | 64,675 | 4,464 |
| hspolicy26 | 2,657 | 2,629 | 28 | 0 | 0% | 82,563 | 2,660 |
| hspf26 | 3,906 | 2,650 | 1,256 | 0 | 0% | 42,902 | 3,909 |
| openev | 102 | 101 | 0 | 1: `COMPRESSION_RATIO_EXCEEDED` | 0.98% | 8,056 | 105 |
| **Total** | 11,126 | 9,734 | 1,385 | 7 | | 198,196 | 11,138 |

No `FORBIDDEN_XML_CONSTRUCT` anywhere: it was 23. Cards with no tag, which the second loop prints:

| Caselist | `FULL` | `ABBREVIATED` | `CITE_ONLY` | Total |
|---|---|---|---|---|
| hsld26 | 869 | 198 | 286 | 1,353 |
| hspolicy26 | 532 | 204 | 356 | 1,092 |
| hspf26 | 1,566 | 170 | 167 | 1,903 |
| openev | 59 | 20 | 19 | 98 |
| **Total** | 3,026 | 592 | 828 | 4,446 |

The `grep` line prints 0: no record says `"tag":""`. The `diff` line prints "old directories
unchanged". `ls` shows two directories for each caselist, and `du` about 11.6 GB.

These figures come from running this branch's parser over the same sources, read-only, on
2026-10-10. A count that differs with no pull in between is worth sending back before prod.

**5. The second run, which must parse and upload nothing** (about 18 minutes in all; it is the
rebuild, which measured 348, 460, 214 and 60 s):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --publish | jq -c '.data | {caselist, version, attempted, skipped, elapsed_seconds, uploaded: .publish.counts.uploaded}'; done
uv run debate-research store ls parsed/hsld26/2026.10.10-docx-2/index.jsonl
```

Expected: `attempted` 0, `skipped` equal to the sources, and `uploaded` 0 for each caselist;
`store ls` lists 1 object.

**6. The sample again** (about 5 minutes, by eye). The source the first sample check found wrong.
Its digest prefix is in the kickoff, not here: put it into `P`.

```zsh
cd ~/.debate-research/dev/parsed/hsld26/2026.10.10-docx-2
P=paste-the-sample-digest-prefix-here
D=$(jq -r --arg p "${P}" 'select(.source_sha256 | startswith($p)) | .source_sha256' index.jsonl)
jq -r --arg d "${D}" 'select(.source_sha256 == $d) | "\(.outcome) \(.cards)"' index.jsonl
cp -f ~/.debate-research/dev/blobs/sha256/${D:0:2}/${D:2:2}/${D} /tmp/parse-sample.docx
open /tmp/parse-sample.docx
sed -n 2p sha256/${D:0:2}/${D:2:2}/${D}.jsonl | jq -r '.document.cards[:5][] | "\(.completeness)  \(.tag)"'
```

Expected: `PARSED 10`, where it was 12. The five lines are the document's first five cards, each
with its tag. **The first says `ABBREVIATED` and the card is whole**: that is the completeness rule
under Follow-up work, not a new fault. The other four tallied as right before should still be.
Record tallies only; the file and the tags are real disclosures. Then:

```zsh
rm -f /tmp/parse-sample.docx
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
```

**7. The prod publish**, from the same dev data directory, only after dev looks right (about 15
minutes; nothing is parsed again; the first measured 279, 370, 202 and 55 s):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research --json caselist parse --caselist hsld26 --dry-run | jq -c '.data | {caselist, version, to_parse, skipped}'
uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/reparse-prod-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/reparse-prod-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/reparse-prod-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/reparse-prod-openev.json; echo "exit $?"
uv run debate-research store ls parsed/hsld26/2026.10.10-docx-2/index.jsonl
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

* **`DEBATE_STORAGE__DATA_DIR` is the point of this block.** Without it the prod profile reads an
  empty `~/.debate-research/prod` and publishes nothing.
* **The dry run** must show `version` `2026.10.10-docx-2`, `to_parse` 0 and `skipped` 4,461. If
  `to_parse` is not 0, the data directory is wrong: stop.
* **Each publish** should exit 0 and upload what dev's did: 4,464, 2,660, 3,909 and 105.
* **Paste back** the first loop of step 4 with `reparse-prod-` in place of `reparse-dev-`.
* **The `unset` at the end matters.** A shell left on prod with the dev data directory is how the
  next command would write to prod unchecked.
* **Prod's `parsed/2026.09.20-docx-1/` prefixes stay**, as dev's do.

The JSON summaries hold counts, digests and keys, and no names or paths. Keep them out of the
repository all the same. Whoever closes ac4 records the counts in
`docs/data/caselist-parse-report.md` and sets the Goal to `Succeeded` in a small spec PR.

## Follow-up work

- **`ABBREVIATED` marks whole cards (E31, before `v1-e31-t08`'s numbers are relied on).**
  `_completeness` calls a card abbreviated when an ellipsis marker is anywhere in its body or cite.
  21,278 of 22,443 such cards have a body over 1,000 characters. A first-and-last-words disclosure
  is short and is little else. The rule is in `parser.py`, so it is a parser version of its own,
  and it needs the labelled set to pick the bound.
- **The classifier's two cite heuristics (E31, with `v1-e31-t05`'s labels).**
  `heuristic-wiki-cite-entry` has no length bound and takes a name and a year anywhere in the
  paragraph; `heuristic-cite-line-author-year` takes any capitalised word followed by two or four
  digits, so *In 2019* and *Since 2001* are authors. My rule works around both from the assembly
  for the cases formatting can settle. The 2,793 cards with no tag that still start at one of them
  are where a fix in `style_classifier.py` would show.
- **Make `ParsedCard.tag` `str | None` in memory (E31, after `v1-e31-t08`).** See Deviation 3.
  `CardOccurrence.tag` and `caselist cards --json` still say `""` for a card with no tag.
- **The ratio guard refuses a file for a part the parser never opens (E31, p3).** One file today.
  Judging the ratio only on parts the reader will open, with the total uncompressed limit still
  over everything, would read it. That is a change to the zip-bomb guard and is yours to decide.
- **CardMirror writes characters XML forbids (E31, p3).** Five files today, and more each week if
  the exporter does not change. Reading them means dropping a character from evidence text, so it
  is a policy question before it is a parser one. The `.cmir` upload is one file; a `SourceFormat`
  of its own would count it as unsupported rather than failed.
- **`PARSED_STORE_SCHEMA_VERSION` and a nullable `tag`** (E31). See Deviation 10.
- **`v1-e34-t17`**: when it wires the parse stage into `caselist pull`, a refused parsed store
  arrives as `STORE_ACCESS_DENIED`.
- **Retention of superseded version directories** (already noted at t06's close-out) now has a
  second 5.8 GB directory per place to argue for it.
- **Pre-existing, noticed:** `tests/fixtures/debate_files/structural/*.docx` are not what
  `scripts/generate_structural_fixtures.py` writes today. The parts are identical and the zip
  timestamps differ, so a regeneration rewrites ten binaries for nothing.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-10

**Notes:**

This is excellent work, and nearly all of it stands as it is. I am asking for one more fix, and
only because the operator's re-parse costs 30 minutes and another 5.8 GB in three places. It is
the defect you found and set aside: `ABBREVIATED`. You were right to raise it rather than widen
the task on your own. I am widening it, because one re-parse should carry both fixes rather than
two.

**What stands:**

* **The diagnosis.** All 23 `FORBIDDEN_XML_CONSTRUCT` refusals were prose, not declarations. The
  five malformed files traced to one exporter's control characters. The `.cmir` was identified
  from its bytes. The ratio was measured against the corpus distribution. Every one is specific,
  counted and checkable, and none names a file.
* **The empty tags.** You mirrored the assembly until it reproduced the store's 15,528 exactly,
  then attributed every card to a rule. That is the right standard of evidence. Deciding "formatted
  as body" from the corpus's own counts, using existing profile rules and no new threshold, is the
  right method.
* **Deviation 5, the UTF-16 route,** is the most important thing in this report. A guard that
  scans bytes cannot see a declaration written in two-byte characters, and an internal entity in
  an attribute was expanded. You found it while proving that narrowing the scan weakened nothing,
  which is what that proof is for. Refusing any parsed part that carries a document type closes
  it, and the 8-bit cases still never reach a parser.
* **The `no_network` mutant you could not catch:** keep the option, as you did. Offline tests
  cannot observe it while the other two options are off. It is defence in depth against a later
  change to either of them. You said so plainly, which is what working agreement 8 asks.
* **Deviations 1, 2, 4, 6, 8 and 9:** accepted.
* **Deviation 3:** accepted. Making `ParsedCard.tag` `str | None` follows `v1-e31-t08`, as you
  propose.
* **Deviation 7:** a 126-second read-only run, 6 seconds over the line. Noted. It wrote nothing.
* **The refusals that stay:** accepted. The ratio guard stays, by my own rule. CardMirror's
  control characters stay refused: dropping a character, even an invisible one, is editing
  disclosed text, and five files do not justify a policy exception. The PM files both as
  follow-ups.

**Change 1: decide `ABBREVIATED` from the disclosure's shape (ac6, added to the spec in this
branch).** The current rule marks a card abbreviated if an ellipsis marker appears anywhere in its
body or cite. 95% of the cards it marks are whole cards with an omission. This matters beyond the
label:

* `CaselistCardStatsService.place` clusters only `FULL` cards. Every other card goes down the
  abbreviation-linking path, so these 21,000 whole cards are never compared as near-duplicates.
* `v1-e31-t08`, running now, measures abbreviated linking on the real store through that path.
* E32's counts are built on it.

How:

* **Derive the rule from the corpus, read-only and counts only.** Among cards carrying a marker,
  measure: the body's word count; how many markers it holds; where the marker sits; and the word
  counts of the fragments either side. The disclosure shape is short, with one marker joining an
  opening fragment and a closing fragment. A cut card is long, and its markers sit mid-text. Pick
  the bounds where the distribution separates. Report the histogram as counts and the bounds you
  chose with the reason. If it does not separate cleanly, say so and choose the conservative side,
  so that a whole card is not called abbreviated.
* **A marker in the cite is not evidence of abbreviation.** Cites carry ellipses for their own
  reasons.
* **Fixtures, synthetic, each shown failing first.**
  * A full card with one omission marker mid-body is `FULL`.
  * A full card with several omissions is `FULL`.
  * A first-words-marker-last-words disclosure is `ABBREVIATED`, including the wiki profile's other
    marker spellings.
  * A short body with no marker is `FULL`.
  * A cite with a marker and a full body is `FULL`.
  * `CITE_ONLY` is unchanged.
  * Your strict xfail passes and stops being an xfail.
* **Same version.** `2026.10.10-docx-2` has written nothing anywhere, so it carries this too.
  Re-run the read-only comparison over the 9,741 sources. Report completeness counts per caselist
  before and after, and how many cards change from `ABBREVIATED` to `FULL` and the reverse.
  Re-check the two corrected evaluation files.
* **Mutation, each shown caught:** the marker-anywhere rule restored; the length bound removed; a
  marker in the cite counted.

**Change 2: bump `PARSED_STORE_SCHEMA_VERSION` (authorised outside your packages:
`debate_core.application.ports`).** Deviation 10 is right that `ParsedCard` reads both forms. But
a record whose `tag` can now be `null` is a new record shape. The version is how a reader that
does not go through `ParsedCard` (a `jq` line, E32's code, a future cloud reader) learns that.
Make it 2. Records in `2026.09.20-docx-1` stay 1. Readers accept both, shown by reading a stored
version-1 record. `parsed-card-store.md` says what changed.

**Change 3: the operator follow-ups.**

* Update every expected count for Change 1: the card totals if any change, the completeness split,
  and the no-tag table by completeness.
* **Disk.** The new directory leaves about 8 GiB free on 14 GiB. Keep the 8 GiB check before
  step 3, and say what to do if it fails: stop, nothing is deleted.
* Leave the old directory alone; its retention is a PM follow-up.
* Step 6's sample check should now also read the first card as `FULL`.

**Coordination with `v1-e31-t08`.** The PM is telling t08's session about Change 1 now. If t08
merges first, run `scripts/task sync` before your report and re-run everything, as briefed.

**When you resubmit:** append a revision section with the evidence for Changes 1 to 3, re-run the
full suite and the gates, and add a new empty PM review after this one. ac4's re-parse stays NOT
RUN, and the Goal stays `InProgress`.
