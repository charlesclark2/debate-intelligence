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

## Revision 2026-10-10: the changes the PM review requested

| | |
|---|---|
| Session status | PARTIAL: Changes 1 to 3 are done; the operator's re-parse (ac4) is still NOT RUN and the Goal is `InProgress` |
| Commits | `93269b5`, `4b22b2a`, `df19af7`, `451db9e`, `8fce88d`, `6a6fa3e`, `7e04604`, and the report commit |
| Synced | Onto `origin/dev` at `7ca98e0`, which has `v1-e31-t08-short-card-recall` (#215) |

Everything above this section is the first report as reviewed, left unchanged. Where it gives a
figure this section changes (the completeness split, the operator's expected counts), **this
section is current.** Its operator follow-ups replace the earlier ones.

**Read first:**

1. **After the fix, no card in the corpus is `ABBREVIATED`.** Not one of the 198,196. That is the
   measurement, not a fault in the rule: no body in the corpus has the shape of a first-and-last-
   words disclosure. All 21,382 cards the old rule would mark become `FULL`, and none moves the
   other way. `v1-e31-t08`'s abbreviation linking will have nothing to link by that route after the
   re-parse, which its sample should expect.
2. **A new finding, raised and not fixed: body text stored as the card's cite.** 2,902 of the
   4,731 `CITE_ONLY` cards are whole cards whose body sits in the cite field, with no evidence
   text. It is the same heuristic as the empty tags, one step earlier in the card. I measured it
   while looking for where a real disclosure would be. It is under
   [Follow-up work added](#follow-up-work-added-in-this-revision), with a proposed rule, because
   you may want it in the same re-parse.
3. **Change 2 has one line more than you asked for.** A version-2 document that says "no tag" as
   `""` is refused by the record model. It is what makes "2" a promise a reader can rely on.
4. **Synced onto t08, and everything was run again.** One conflict, in `parsed-card-store.md`, where
   both tasks added to the same section; both sides are kept. t08 changed no parser, classifier or
   profile file, and the corpus pass after the sync is identical, card for card, to the one before.
5. **The `ABBREVIATED` fixtures could not fail first**, since the old rule marks them too. A mutant
   is their proof.

### Change 1: `ABBREVIATED` from the disclosure's shape (ac6)

**The measurement.** Read-only, numbers only: a scratch pass ran the branch's parser over the
9,741 DOCX sources and kept, for each card, word counts, marker counts and fragment sizes. No text
left the process. The full tables are in
[`docs/data/caselist-parse-report.md`](../data/caselist-parse-report.md#abbreviated-by-shape).

Of the 198,196 cards, 19,402 hold a marker in the body and 1,980 more only in the cite.

| Body words | 1 marker | 2 | 3 to 5 | 6 or more | All |
|---|---|---|---|---|---|
| 20 or fewer | 0 | 0 | 0 | 0 | 0 |
| 21 to 30 | 6 | 0 | 1 | 0 | 7 |
| 31 to 60 | 31 | 0 | 0 | 0 | 31 |
| 61 to 100 | 51 | 2 | 7 | 0 | 60 |
| 101 to 200 | 305 | 39 | 15 | 1 | 360 |
| 201 to 500 | 2,360 | 416 | 135 | 28 | 2,939 |
| 501 to 1,000 | 3,565 | 643 | 459 | 69 | 4,736 |
| Over 1,000 | 5,432 | 1,915 | 2,513 | 1,409 | 11,269 |
| **All** | 11,750 | 3,015 | 3,130 | 1,507 | 19,402 |

* **How many markers:** 11,750 bodies hold one, 7,652 two or more.
* **Where the marker sits**, in the one-marker bodies, by the share of words before it: 554, 970,
  1,600, 1,389, 1,414, 1,572, 928, 977, 1,147 and 1,199 across the ten deciles. Anywhere, as an
  omission in running text does. In 57 it opens or closes the body.
* **The fragments either side**, in the 11,693 one-marker bodies with words on both sides, by the
  longer side, cumulative:

| Longer side, at most | 12 | 15 | 20 | 30 | 40 | 50 | 60 | 80 | 100 | 150 | 200 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Cards | 0 | 0 | 6 | 14 | 38 | 55 | 59 | 109 | 185 | 454 | 806 |

**It does not separate, and I am saying so.** There is no second population. A body with a marker
is longer than one without: 0.5% are 100 words or fewer, against 6.1% of the 174,063 bodies with no
marker. The shortest longer side anywhere is 17 words. The 37 one-marker bodies of 60 words or
fewer are a handful of texts disclosed several times each.

**The rule, on the conservative side.** A body is `ABBREVIATED` when it holds exactly one marker,
has words on both sides of it, and no more than twelve on either side. A marker in the cite decides
nothing. `MAXIMUM_DISCLOSED_FRAGMENT_WORDS = 12` is a constant in `parser.py`; the marker
spellings are still the profile's.

* **Why twelve.** It is the middle of the only gap there is: above the disclosures we have a model
  of (three to nine words a side in the profile's examples) and below everything the corpus holds
  (17 and up). Any bound from 9 to 16 gives the same result on this corpus. At 20 it would mark 6
  cards, at 30 14, at 50 55, and nothing tells those from any other short card.
* **Why exactly one marker.** One joins a beginning to an end. 7,652 bodies hold two or more, and
  7,639 of those are over 120 words.
* **What it costs.** A disclosure that quoted thirteen words a side would be called whole. That is
  the safe way to be wrong, and the corpus holds no such body.

**Fixtures** (`TestAbbreviatedIsADisclosuresShape`, 39 tests, in
`test_first_corpus_parse_findings.py`). Written and committed before the rule (`93269b5`: 21
failed, 15 passed).

| Yours | Test | Before | After |
|---|---|---|---|
| A full card with one omission mid-body is `FULL` | `test_a_whole_card_with_one_omission_is_full` (77 words) | `ABBREVIATED` | `FULL` |
| A full card with several omissions is `FULL` | `…with_several_omissions_is_full`; `…of_several_paragraphs_with_an_omission_in_each…` | `ABBREVIATED` | `FULL` |
| First words, a marker, last words is `ABBREVIATED`, in each spelling | `test_first_words_a_marker_and_last_words_is_abbreviated` ×5; `…written_against_the_words_either_side…` ×5 | `ABBREVIATED` | `ABBREVIATED` |
| A short body with no marker is `FULL` | `test_a_short_body_with_no_marker_is_full` | `FULL` | `FULL` |
| A cite with a marker and a full body is `FULL` | `test_a_marker_in_the_cite_does_not_abbreviate_a_whole_body`; `…a_short_body_either` ×5 | `ABBREVIATED` | `FULL` |
| `CITE_ONLY` is unchanged | `test_a_cite_with_a_marker_and_no_body_is_still_cite_only` | `CITE_ONLY` | `CITE_ONLY` |
| The strict xfail passes and is no longer one | `test_the_first_card_is_a_full_card` | `ABBREVIATED` | `FULL`, an ordinary test |

Mine, for the edges of the rule: a whole card of one sentence (21 words, a marker, 8 words) is
`FULL`; twelve words a side is `ABBREVIATED` in each spelling and thirteen on either side is
`FULL`; a marker that opens or closes a body is `FULL`; two markers, however short the body, are
`FULL`; and a disclosure broken over two lines is still one.

Three of your rows cannot fail first, and I am not claiming they did: the disclosure, the short
body and `CITE_ONLY` have the same answer under both rules. The mutant "nothing is ever
abbreviated" fails 19 tests, and "a body with no text is abbreviated" fails 38.

The revision's final test set against the first submission's source, checked out over the clean
tip and restored (`git status --porcelain` empty, `git diff --quiet HEAD`): **25 failed, 1,037
passed, 1 skipped**. 21 are Change 1 and 4 are Change 2.

**The corpus, before and after.** `2026.10.10-docx-2`, kept: nothing has written it.

| Caselist | Stored: `FULL` | `ABBREVIATED` | `CITE_ONLY` | After: `FULL` | `ABBREVIATED` | `CITE_ONLY` |
|---|---|---|---|---|---|---|
| hsld26 | 57,057 | 8,418 | 2,439 | 62,769 | 0 | 1,906 |
| hspf26 | 40,319 | 2,972 | 1,007 | 42,053 | 0 | 849 |
| hspolicy26 | 74,902 | 10,524 | 2,130 | 80,756 | 0 | 1,807 |
| openev | 6,563 | 529 | 196 | 7,887 | 0 | 169 |
| **Total** | 178,841 | 22,443 | 5,772 | 193,465 | 0 | 4,731 |

The totals differ between the halves (207,056 and 198,196) because of the empty-tag fix, as in the
first report; card totals and the 4,446 cards with no tag do not change in this revision. The
completeness rule on its own, both rules applied to the new parser's cards:

| Caselist | `ABBREVIATED` to `FULL` | `FULL` to `ABBREVIATED` |
|---|---|---|
| hsld26 | 7,908 | 0 |
| hspf26 | 3,026 | 0 |
| hspolicy26 | 9,837 | 0 |
| openev | 611 | 0 |
| **Total** | 21,382 | 0 |

19,402 of the 21,382 held a marker in the body and 1,980 only in the cite. `CITE_ONLY` is untouched
at 4,731. Among the 186,642 stored cards with the same paragraph range under the new parser, 15,781
go from `ABBREVIATED` to `FULL` and no other completeness changes.

**The two corrected evaluation files:** completeness is right on **4 of 4** matched cards, as
before; boundaries 4 of 5, as before. Every unit score is what the first report gives for
`2026.10.10-docx-2`.

**Mutation.** The same driver and rules as before: a clean committed tree, a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` each run, restore and check. 1,063 tests across the same six paths,
7 to 8 seconds a run, two batches of about 65 seconds, on the final tree. Sixteen mutants, sixteen
caught, all by assertion failures. Yours first:

| Mutant | Caught | Tests failing |
|---|---|---|
| **The marker-anywhere rule restored** (any marker in the body) | yes | 15 |
| The marker-anywhere rule restored, the cite included | yes | 21 |
| **The length bound removed** | yes | 5 |
| **A marker in the cite counted** | yes | 6 |
| Several markers allowed | yes | 2 |
| A marker at either end allowed | yes | 4 |
| The bound one word higher | yes | 3 |
| The bound one word lower | yes | 5 |
| The bound held on one side only | yes | 7 |
| Nothing is ever abbreviated | yes | 19 |
| A body with no text is abbreviated, not cite-only | yes | 38 |

A seventeenth, **the marker spellings tried shortest first, was not caught**, and it was right not
to be. I had sorted the spellings longest first so that `[...]` would be one marker. A regular
expression takes the match that starts first, and the bracketed spelling starts at the bracket, so
the order changes nothing for these five spellings. I deleted the sort (`6a6fa3e`), by working
agreement 8, and the twelve-word bound is now tested in every spelling.

### Change 2: `PARSED_STORE_SCHEMA_VERSION` is 2

* **Version 2:** a stored card's `tag` is a string or `null`, never `""`. Every record written now
  says 2: source, document and occurrence.
* **Version 1 stays.** A record keeps the version it was written with. `StoreRecord.schema_version`
  takes 1 or 2, and refuses anything else.
* **A stored version-1 store, written by the old build.** With the start commit's source checked
  out, I wrote a small store through `LocalParsedStore` from three synthetic sources, and committed
  it as `tests/fixtures/parsed_store/written_by_schema_version_1/`: ten records, each
  `"schema_version": 1`, parser `2026.09.20-docx-1`, one card with `"tag": ""`. It is what the
  first corpus parse's directories look like. It is never regenerated: no later build can write it.
* **Readers take both**, shown on those bytes (`test_parsed_store_schema_versions.py`, 10 tests,
  written first: 4 failed, 6 passed at `df19af7`). `LocalParsedStore` lists the directory, reads
  every entry, the index, the failures, the occurrences and the document; the document's empty tag
  reads back as no tag; and a version-1 entry carried into a rebuilt aggregate is byte-identical,
  not re-stamped.
* **`parsed-card-store.md`** has a "Schema versions" section saying what changed, and that nothing
  else did.

| Mutant | Caught | Tests failing |
|---|---|---|
| The version left at 1 | yes | 4 |
| Readers take version 2 only | yes | 4 |
| Readers take version 1 only | yes | 82 |
| A version-2 document may say no tag as `""` | yes | 1 |
| A version-1 document may not say no tag as `""` | yes | 2 |

"Readers take version 1 only" also errors 17 tests in fixtures that write a record. Collection
succeeds under that mutant, so none of its 82 failures is a collection error.

### Change 3: the operator follow-ups

Rewritten below as [Operator follow-ups, revised](#operator-follow-ups-revised). What changed:

* every expected count that Change 1 moves: the completeness split per caselist, and the no-tag
  table by completeness. Card totals do not move;
* one command now prints completeness and tag together, so both tables come from one pass;
* the fingerprint version expected is `card-fingerprint-v2`, in the dry run and in the new
  directory's occurrence rows;
* the record version expected is 2 in the new directory and 1 in the old;
* the 8 GiB check sits before step 3 with what to do if it fails;
* step 6 expects the first card to read `FULL`;
* one line before step 7 for t08's sample.

### The sync with `v1-e31-t08`

`scripts/task sync` after t08 merged. Nothing was pushed: the branch has no remote.

* **One conflict**, in `docs/data/parsed-card-store.md`, "Reading it from a shell": t08 added a
  line and a sentence about fingerprint versions, I had added the no-tag command. Both are kept.
* **The rebase stopped once before that** with "local changes would be overwritten" on two test
  files, with a clean tree when I looked. `git rebase --continue` went on from there. I do not know
  what touched them; the result is checked below.
* **t08 changed no file the parser reads through:** `git diff --stat f5ad52b 7ca98e0` over
  `integrations/`, `style_classifier.py`, `style_profiles/`, `debate_files.py` and
  `style_profile.py` is empty. Its change to `parsed_store.py` is a docstring and a field
  description, and merged with mine cleanly.
* **Re-run after the sync:** the corpus pass (five runs, the longest 64 seconds), whose output is
  identical line for line to the pass before the sync; the evaluation check; all sixteen mutants;
  the failing-first run; the suite and the gates.

### Acceptance criteria, as they stand

Results are from `7e04604`, the tip before this report.

| Criterion | Status | Evidence |
|---|---|---|
| ac1, ac2, ac3, ac5 | PASS | As in the first report. Their tests pass on the synced tree. |
| ac4, first half: `parser_version` bumped | PASS | Still `2026.10.10-docx-2`, as you ruled. |
| ac4, second half: the operator's re-parse | **NOT RUN** | [Operator follow-ups, revised](#operator-follow-ups-revised). |
| **ac6**: `ABBREVIATED` from the disclosure's shape, derived from the corpus by read-only counts; the fixtures, each shown failing first; the xfail an ordinary test; completeness 4 of 4; the same parser version | PASS, with the three rows that cannot fail first named above | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_first_corpus_parse_findings.py -k TestAbbreviated` → `39 passed`. The whole file: 130 passed, no xfail. |
| Node: `uv run pytest packages/debate_core/tests/integrations` | PASS | `783 passed in 4.13s` |
| Default suite, two commands | PASS | `packages`: `4026 passed in 55.95s`. `tests`: `1256 passed, 1 skipped, 1 warning in 45.15s`. The skip and the warning are the same two as before. Slow parser timing test: `1 passed`. |
| Static checks and gates | PASS | `pyright` 0 errors; `lint-imports` 12 kept; `ruff check` and `ruff format --check` clean, 581 files; `check_thin_handlers.py`, `check_links.py`, `check_command_blocks.py --base origin/dev`, `docs_index.py --check-descriptions`, `export_schemas.py --check` all OK. |
| t03's structural fixtures | PASS | Unchanged by this revision: the wiki fixture's first-and-last-words card has eight and nine words a side and is still `ABBREVIATED`. Ten lines differ from the start commit, each `parser_version`. |
| `uv run scripts/validate_specs.py` | PASS | `OK: 327 files, 38 epics, 269 tasks, 20 releases`. Phase `InProgress`. |

### Files changed in this revision

- `packages/debate_core/src/debate_core/integrations/docx_parser/parser.py`: `_completeness` reads
  the body alone; `_is_first_and_last_words`; `MAXIMUM_DISCLOSED_FRAGMENT_WORDS`.
- `packages/debate_core/src/debate_core/domain/debate_files.py`: what `ABBREVIATED` and `FULL` mean,
  in the enum's docstrings.
- `packages/debate_core/src/debate_core/application/ports/parsed_store.py` (authorised): the
  version, `ReadableSchemaVersion`, and the version-2 check on a stored document.
- Tests: 39 in `test_first_corpus_parse_findings.py`; `test_parsed_store_schema_versions.py` (10).
- `tests/fixtures/parsed_store/`: the stored version-1 store and a README saying where it came from.
- Docs: `parsed-card-store.md` (schema versions; what `ABBREVIATED` means) and
  `caselist-parse-report.md` (the histogram, the rule, before and after, and what the measurement
  raised).

### Deviations added in this revision

11. **The record model refuses a version-2 document with `"tag": ""`.** You authorised the bump in
    `application/ports`; this check is a second edit there. Without it "2" is a label, and with it
    a reader can rely on what the label says.
12. **`ABBREVIATED` is empty on the corpus.** ac6 asks that a first-and-last-words disclosure be
    `ABBREVIATED`, which a fixture shows. It does not ask that the corpus contain one, and it
    contains none in a card's body. I chose the bound that calls no whole card abbreviated over one
    that would keep the label in use.
13. **The corpus pass ran as five commands**, hspolicy26 in two halves, so that none passed two
    minutes after the 126-second run you noted. The longest was 94 seconds.
14. **Three more read-only passes than you asked for**, to measure cite paragraphs, once I saw the
    disclosure shape was not in the bodies. They are what Read first, point 2, rests on.
15. **Scratch files of numbers exist outside the repository:** per card, word and marker counts
    with a caselist and nothing else, in the session's scratch directory. No text, digest or path.

### Operator follow-ups, revised

These replace the earlier **Operator follow-ups**. They close ac4, and they run only after:

1. the PM accepts this revision;
2. the branch merges with `scripts/task pr v1-e31-t09-first-corpus-parse-findings --partial`;
3. `scripts/task finish v1-e31-t09-first-corpus-parse-findings --partial` closes it out.

**The PM hands over one combined order with `v1-e31-t08`'s steps.** t08's by-eye sample runs
between step 5 and step 7 here. Don't run any of this while `caselist pull` is running.

**What to know before starting.**

- **Disk.** Each version directory is about 5.8 GB on this Mac and in each bucket. The re-parse
  writes a second one beside the first. **The old one stays where it is**, here and in both
  buckets; whether and when it goes is a PM follow-up, not a step here.
- **`v1-e31-t08` is merged.** This one re-parse covers both tasks: the new directory's occurrence
  rows are built under `card-fingerprint-v2`.
- **A weekly pull since 2026-10-10** adds sources. "Sources" and "to parse" then rise by what it
  imported, and the other counts with them.

**1. Start in the main checkout, on an updated `dev`** (seconds):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git status --short
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t09-first-corpus-parse-findings:'
git log --oneline -1 --grep='^v1-e31-t08-short-card-recall:'
export DEBATE_ENV=dev
uv run debate-research caselist runs --last 1
df -h ~/.debate-research
```

Expected: `dev`; `git status` prints nothing; each `git log` prints one line; the last pull run has
finished; `df` shows **at least 8 GiB available**.

* **Either `git log` prints nothing:** that merge is not on `dev` yet. Stop.
* **Less than 8 GiB available:** stop. **Delete nothing**, the old version directory least of all.
  Send the `df` line; freeing space is the PM's decision.

**2. The dry run, and a fingerprint of the old directories** (about a minute; writes nothing under
the data directory; needs no AWS session):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --dry-run | jq -c '.data | {caselist, version, new_version, superseded, fingerprint_version, to_parse, skipped, suppressed}'; done
find ~/.debate-research/dev/parsed/*/2026.09.20-docx-1 -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 > ~/parsed-old-version-before.txt
cat ~/parsed-old-version-before.txt
```

Expected for each caselist: `version` `2026.10.10-docx-2`, `new_version` true, `superseded`
`2026.09.20-docx-1`, `fingerprint_version` `card-fingerprint-v2`, `skipped` 0 and `suppressed` 0.
`to_parse` is 4,461 for hsld26, 2,657 for hspolicy26, 3,906 for hspf26 and 102 for openev, as the
store stood on 2026-10-10. Any other `version` or `fingerprint_version` means the build is not
this one: stop and paste the four lines back.

**3. The dev re-parse and publish** (about 30 minutes in all; the first full parse measured 518 s
for hsld26, 747 s for hspolicy26, 352 s for hspf26 and 106 s for openev). One caselist at a time.
Run it only if step 1 showed 8 GiB available.

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

**4. The counts to paste back** (about 3 minutes; prints counts, versions and sizes only):

```zsh
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, superseded, fingerprint_version, sources, parsed, cards, unsupported, failed, failure_rate, store, elapsed_seconds, publish: .publish.counts}' ~/reparse-dev-${c}.json; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.10-docx-2/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | "\(.completeness) \(if .tag == null then "no-tag" else "tagged" end)"' | sort | uniq -c; done
for c in hsld26 hspolicy26 hspf26 openev; do jq -r '"\(.schema_version) \(.fingerprint_version)"' ~/.debate-research/dev/parsed/${c}/2026.10.10-docx-2/occurrences.jsonl | sort | uniq -c; done
head -1 ~/.debate-research/dev/parsed/hsld26/2026.09.20-docx-1/index.jsonl | jq -c '{schema_version, parser_version}'
grep -rlF '"tag":""' ~/.debate-research/dev/parsed/*/2026.10.10-docx-2/sha256 | wc -l
find ~/.debate-research/dev/parsed/*/2026.09.20-docx-1 -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | diff - ~/parsed-old-version-before.txt && echo "old directories unchanged"
ls -d ~/.debate-research/dev/parsed/*/*
du -sh ~/.debate-research/dev/parsed
```

Expected, if no weekly pull has run since 2026-10-10. The first loop:

| Caselist | Sources | Parsed | Unsupported | Failed, by reason | Failure rate | Cards | Uploaded |
|---|---|---|---|---|---|---|---|
| hsld26 | 4,461 | 4,354 | 101 | 6: `MALFORMED_XML` 5, `NOT_A_ZIP` 1 | 0.14% | 64,675 | 4,464 |
| hspolicy26 | 2,657 | 2,629 | 28 | 0 | 0% | 82,563 | 2,660 |
| hspf26 | 3,906 | 2,650 | 1,256 | 0 | 0% | 42,902 | 3,909 |
| openev | 102 | 101 | 0 | 1: `COMPRESSION_RATIO_EXCEEDED` | 0.98% | 8,056 | 105 |
| **Total** | 11,126 | 9,734 | 1,385 | 7 | | 198,196 | 11,138 |

No `FORBIDDEN_XML_CONSTRUCT` anywhere: it was 23. The second loop prints four lines for each
caselist, and **no line beginning `ABBREVIATED`**:

| Caselist | `FULL tagged` | `FULL no-tag` | `CITE_ONLY tagged` | `CITE_ONLY no-tag` | Cards | With no tag |
|---|---|---|---|---|---|---|
| hsld26 | 61,702 | 1,067 | 1,620 | 286 | 64,675 | 1,353 |
| hspolicy26 | 80,020 | 736 | 1,451 | 356 | 82,563 | 1,092 |
| hspf26 | 40,317 | 1,736 | 682 | 167 | 42,902 | 1,903 |
| openev | 7,808 | 79 | 150 | 19 | 8,056 | 98 |
| **Total** | 189,847 | 3,618 | 3,903 | 828 | 198,196 | 4,446 |

The completeness split is the sum of each pair: `FULL` 62,769, 80,756, 42,053 and 7,887;
`CITE_ONLY` 1,906, 1,807, 849 and 169; `ABBREVIATED` 0. In the stored `2026.09.20-docx-1` it is
`ABBREVIATED` 8,418, 10,524, 2,972 and 529.

* **The third loop** prints one line for each caselist, `2 card-fingerprint-v2`, with the number of
  occurrence rows. Occurrence and cluster counts are t08's to expect, not predicted here.
* **The `head` line** prints `{"schema_version":1,"parser_version":"2026.09.20-docx-1"}`: the old
  directory is as it was.
* **The `grep` line** prints 0: no record says `"tag":""`.
* **The `diff` line** prints "old directories unchanged".
* **`ls`** shows two directories for each caselist, and **`du`** about 11.6 GB.

These figures come from running this branch's parser over the same sources, read-only, on
2026-10-10, before and after the sync with t08. A count that differs with no pull in between is
worth sending back before prod. A few `ABBREVIATED` lines after a pull are not a fault: a real
first-and-last-words disclosure would be one.

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
with its tag, and **each reads `FULL`, the first included**. In the first parse the second and
third stored cards had no tag; they were the rest of the first card's body, and are in it now. The
other four files tallied as right before should still be. Record tallies only; the file and the
tags are real disclosures. Then:

```zsh
rm -f /tmp/parse-sample.docx
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
```

**Before step 7: `v1-e31-t08`'s ac5 sample runs here, between the dev re-parse and the prod
publish. A "different card" verdict in that sample stops the prod publish.** Do not run step 7
until that sample is done and clean.

**7. The prod publish**, from the same dev data directory, only after dev looks right and t08's
sample is clean (about 15 minutes; nothing is parsed again; the first measured 279, 370, 202 and
55 s):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research --json caselist parse --caselist hsld26 --dry-run | jq -c '.data | {caselist, version, fingerprint_version, to_parse, skipped}'
uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/reparse-prod-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/reparse-prod-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/reparse-prod-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/reparse-prod-openev.json; echo "exit $?"
uv run debate-research store ls parsed/hsld26/2026.10.10-docx-2/index.jsonl
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

* **`DEBATE_STORAGE__DATA_DIR` is the point of this block.** Without it the prod profile reads an
  empty `~/.debate-research/prod` and publishes nothing.
* **The dry run** must show `version` `2026.10.10-docx-2`, `fingerprint_version`
  `card-fingerprint-v2`, `to_parse` 0 and `skipped` 4,461. If `to_parse` is not 0, the data
  directory is wrong: stop.
* **Each publish** should exit 0 and upload what dev's did: 4,464, 2,660, 3,909 and 105.
* **Paste back** the first loop of step 4 with `reparse-prod-` in place of `reparse-dev-`.
* **The `unset` at the end matters.** A shell left on prod with the dev data directory is how the
  next command would write to prod unchecked.
* **Prod's `parsed/<caselist>/2026.09.20-docx-1/` prefixes stay**, as dev's do.

The JSON summaries hold counts, digests and keys, and no names or paths. Keep them out of the
repository all the same. Whoever closes ac4 records the counts in
`docs/data/caselist-parse-report.md` and sets the Goal to `Succeeded` in a small spec PR.

### Follow-up work added in this revision

- **Body text stored as the card's cite (E31, and worth deciding before the re-parse).**
  `heuristic-wiki-cite-entry` takes any paragraph with an ellipsis and a name with a year for a
  cite, at any length. My rule from the first submission keeps such a paragraph in its card when a
  body is already open. The *first* body paragraph has no body open before it, so it is still
  filed as cite text.
  - **Size, under `2026.10.10-docx-2`:** 3,515 cite paragraphs from that heuristic are longer than
    100 words, and 2,058 longer than 1,000. A cite read from a cite style is longer than 200 words
    in 35 cases out of about 140,000. 2,652 of the 3,515 follow another cite paragraph in the same
    card; 863 are the first cite paragraph the card has.
  - **What it does to cards:** 2,902 of the 4,731 `CITE_ONLY` cards hold a cite paragraph of more
    than 100 words. They are whole cards, 2,713 of them with a tag, whose body is in `full_cite`
    and whose `evidence_text` is empty, so nothing fingerprints or clusters them. Another 3,440
    cards have a body and also hold a cite paragraph over 100 words. Across all 6,342 such cards,
    2,846 of the long paragraphs come from a cite character style and may simply be long cites.
  - **A rule that would reach most of it,** in the assembly again: a cite *guessed* after the card
    already has a cite, and formatted as body, opens the body. That is my existing rule with "has
    a body" widened to "has a cite or a body". It would not reach the 863 with no cite before
    them, which need a length bound on what a cite entry can be. I have not written or measured
    either: it is a change to card bodies, and you accepted the empty-tag fix as it stands.
  - **Cost of leaving it:** a third parser version later, and another 5.8 GB re-parse.
- **Where a real first-and-last-words disclosure would be.** In a cite paragraph, not a body: the
  wiki heuristic reads "name, year, first words … last words" as one cite, and the card is
  `CITE_ONLY`. At most 84 cite paragraphs from that heuristic are 40 words or fewer. If such
  entries should count as abbreviated cards, the entry has to be split into its cite and its
  words, which is a model question for E31 and bears on what t08's abbreviation linking has to
  work with.
- **The classifier's cite heuristics**, from the first report, now have a measured cost in three
  places: split cards, cards with no tag, and bodies in the cite field.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-10

**Notes:**

Changes 1 to 3 are accepted as they stand. I am asking for one more change, the one you raised,
for the same reason as last time, and this time the arithmetic is harder. The operator's disk
has 15 GB free. This re-parse takes about 6 GB. A third parser version later would need another
6 GB that is not there unless the first version directory is deleted first. So the body-in-cite
fix goes into this version, or it waits behind a retention task. **This is the last addition to
this task's scope.** Anything else you find goes under Follow-up work, and I will not widen the
task again.

**On Changes 1 to 3:**

* **Change 1 is right, including its uncomfortable result.** The histogram has no second
  population. You said so plainly, chose the bound that calls no whole card abbreviated, and
  showed that every bound from 9 to 16 gives the same answer. Zero `ABBREVIATED` cards in the
  corpus is a measurement, not a defect. Your second finding explains it: where a
  first-and-last-words entry exists, the wiki heuristic files it as a cite.
* **It corrects a premise that came from me.** The briefs for t06 and t08 said abbreviated
  disclosures dominate wiki-converted caselists. In this corpus they do not: at most 84 cite
  entries are 40 words or fewer. t08's abbreviation linking is still correct, but it matters less
  than I said. I will tell t08's operator sample to expect it.
* **Saying which fixtures could not fail first,** and naming the mutants that prove them instead,
  is what working agreement 8 asks. Deleting the sort that no mutant could detect is the same
  discipline.
* **Change 2, with Deviation 11:** accepted. Refusing `""` in a version-2 document is what makes
  the version mean something. The stored version-1 fixture, written by the old build and never
  regenerated, is the right kind of compatibility test.
* **Deviations 12 to 15:** accepted. Delete the scratch files of numbers when the task closes.
* **The rebase that stopped with "local changes would be overwritten" on a clean tree:** noted.
  You checked the result by re-running everything, which is what mattered.

**Change 4: body text filed as cite (ac7, added to the spec in this branch).**

* **The rule you proposed:** a cite guessed by a heuristic after the card already has a cite,
  and formatted as body by your existing rule, opens the body. It reaches about 2,652 of the
  3,515 long heuristic cite paragraphs. A cite style decides nothing here and stays a cite,
  whatever its length. 2,846 long paragraphs come from a cite character style, and they may be
  real long cites.
* **The 863 with no cite before them:** a heuristic cite becomes body only past a length bound.
  Derive the bound from read-only counts, as you did for Change 1. Compare the word lengths of
  heuristic cite paragraphs with those of cite-style cites (35 over 200 words in about 140,000),
  and choose the conservative side, so that a real cite entry is never moved. If the
  distribution does not separate, say so and leave the 863 alone. That is an acceptable
  outcome.
* **Fixtures, synthetic, each shown failing first, or named with the mutant that proves it:**
  * a body paragraph after the card's cite, formatted as body, opens the body;
  * the same paragraph formatted as a cite stays a cite;
  * a cite-style paragraph of 300 words stays a cite;
  * a first heuristic cite past the bound, formatted as body, is body;
  * a short wiki cite entry ("name, year, first words … last words") stays a cite;
  * a card with two real cites keeps both.
* **Measure it on the corpus,** under the same version, read-only:
  * `CITE_ONLY` per caselist before and after;
  * how many cards gain evidence text;
  * changes to card totals and no-tag counts;
  * confirmation that no other field moves for the cards it does not reach.

  Re-check the two corrected evaluation files.
* **Mutation, each one shown caught:** a cite style moved to body; the "already has a cite"
  condition dropped; the formatting condition dropped; the length bound removed.
* **Update the operator follow-ups:** every expected count that Change 4 moves.

**The short wiki entries that are really abbreviated disclosures (at most 84)** stay
`CITE_ONLY`. Splitting an entry into its cite and its words is a model question. The PM files it
for E31 after this task closes. It is not part of this change.

**When you resubmit:**

* Append a second revision section with the evidence for Change 4.
* Re-run the full suite and the gates.
* Add a new, empty PM review after this one.

ac4 stays NOT RUN, and the Goal stays `InProgress`.

## Second revision 2026-10-10: body text filed as cite (Change 4, ac7)

| | |
|---|---|
| Session status | PARTIAL: Change 4 is done; the operator's re-parse (ac4) is still NOT RUN and the Goal is `InProgress` |
| Commits | `38caf62` (your review and ac7), `ed96833`, `97cbd70`, `05f7f5d`, `1d9d99e`, `2c47b8e`, `6c4a11f`, and the report commit |
| Synced | Onto `origin/dev` at `1448452`, which has `v1-e34-t18` (#216). No conflict |

Everything above this section is as you reviewed it, unchanged. Where it gives a figure that
Change 4 moves, **this section is current**, and its operator follow-ups replace both earlier sets.

**Read first:**

1. **`CITE_ONLY` falls from 4,731 to 2,254.** 2,480 cards gain evidence text where they had none,
   and 885 more get the first paragraph of their body back from the cite. The 194,831 cards the
   rule does not reach are identical in every field.
2. **The 863 do separate, and the bound is 2,000 characters.** Paragraphs the corpus marks as
   cites stop at 1,517 characters and do not start again until 2,679. The rule with no cite before
   it moves 337 paragraphs.
3. **The rule has three conditions you did not list.** Each is on the conservative side, has a
   count and a mutant, and is under [Deviations](#deviations-added-in-the-second-revision). The
   third came out of the measurement: without it eleven more cards were split in two.
4. **Card totals and cards with no tag both rise by 9.** In nine cards the paragraph that now
   opens the body is followed by a real cite, which starts a second card under the same tag.
5. **One of your fixtures cannot be built as you wrote it.** The classifier does not call a
   paragraph in the cite *character* style a cite past 1,000 characters. I built the 300-word
   fixture two ways and say below what each shows.
6. **What the counts cannot settle:** 218 short small-print lines directly under a cite are now
   read as the body's first line. They may include second lines of cites.
7. **The `ABBREVIATED` figures in the two data documents are re-measured,** because bodies are
   longer now. The rule and the answer are the same: no card is `ABBREVIATED`, at any bound from 9
   to 16.

### Change 4: the rule

In the assembly, beside the rule from the first submission (`parser.py`,
`_open_the_body_with_a_guessed_cite`). A cite the classifier *guessed*, arriving while a card is
open and has no body yet, is re-read as the body's first paragraph when:

* **it is formatted as body** by the existing test: highlighted, or small print throughout, and
  not opening with a bold name;
* **no run carries the cite character style;**
* **the card already has a cite.** Then it opens the body at any length, unless it is 2,000
  characters or fewer and another cite follows it directly;
* **or the card has no cite,** and the paragraph is longer than 2,000 characters and does not open
  with a name and a year.

A cite read from a cite style is never re-read, at any length. A guess with no card open is left
as it was. Each re-read paragraph records which rule did it and which guess it overrode:
`assembly-cite-guess-after-card-cite:…` or `assembly-cite-guess-longer-than-a-cite:…`. The
existing rule's id is unchanged.

### The bound for the 863

**Measured** read-only, flags and lengths only, over every paragraph the classifier calls a cite:
181,797 of them. The comparison you asked for, by character length, for the 772 paragraphs the
wiki heuristic makes the first cite under a tag. "Marked as a cite" means the paragraph carries
the cite character style or opens with a name and a year:

| Characters | Paragraphs | Marked as a cite | Formatted as body |
|---|---|---|---|
| 1,000 or fewer | 258 | 194 | 6 |
| 1,001 to 1,517 | 81 | 74 | 10 |
| 1,518 to 2,678 | 35 | 0 | 34 |
| 2,679 or more | 398 | 32 | 323 |

* **Cite styles.** A cite read from the character style ends at 999 characters, because the
  classifier's style rule stops at the profile's 1,000: 139,012 paragraphs, 35 over 150 words.
  A cite *paragraph* style has no such stop. Of the 1,414 at the head of a card the longest is
  1,427 characters.
* **It separates.** Marked paragraphs are dense up to 1,517 characters and then absent until
  2,679, where they are whole cards written as one paragraph behind a name.
* **2,000, on the conservative side.** Any bound from 1,518 to 2,678 moves no paragraph the corpus
  marks as a cite. 2,000 leaves alone 11 unmarked paragraphs that 1,518 would have moved.
* **In characters,** as the classifier's two cite bounds are. My earlier figures for this were in
  words; 2,000 characters is about 300 words.
* **The 863 was a count by words over a wider set.** By this measure the paragraphs with no cite
  before them, formatted as body and over 2,000 characters, are 346 under a tag and 19 with no
  card open. The rule moves 337: 5 carry the cite character style and 4 open with a name and a
  year. The 19 are left, because a body with no tag and no cite belongs to no card.

### Fixtures

37 tests in three classes of `test_first_corpus_parse_findings.py`. 33 were written and committed
before the rule (`ed96833`: 14 failed, 19 passed, every failure an assertion). The fixtures for a
short guess between two cites were committed before that condition (`05f7f5d`: 2 failed against
the rule as it stood), and one of the 33 was rewritten there: it had expected a short paragraph
before a second cite to end the card. The last test, for a run in the underline style, came with
its mutant.

| Yours | Test | Before the rule | After |
|---|---|---|---|
| A body paragraph after the card's cite, formatted as body, opens the body | `test_a_body_paragraph_after_the_cards_cite_opens_the_body`, and the other eleven tests of `TestABodyFiledAsTheCardsCite` | `CITE_ONLY`, the paragraph in `full_cite` | `FULL`, the paragraph is the evidence text |
| The same paragraph formatted as a cite stays a cite | `test_the_same_paragraph_formatted_as_a_cite_stays_a_cite` ×3: at reading size; small print behind a bold opening; highlighted behind a bold opening | cite | cite |
| A cite-style paragraph of 300 words stays a cite | `…in_a_cite_paragraph_style_stays_a_cite` ×2; `…with_a_run_in_the_cite_character_style_stays_a_cite` ×2 | cite | cite |
| A first heuristic cite past the bound, formatted as body, is body | `test_a_whole_card_in_one_paragraph_under_its_tag_is_the_cards_body` ×2; `test_a_guess_one_character_past_the_bound_is_the_body` | `CITE_ONLY` | `FULL`, with no cite |
| A short wiki cite entry stays a cite | `test_a_short_wiki_cite_entry_is_still_the_cards_cite` ×4; `test_a_guess_at_the_bound_is_still_the_cards_cite` | cite | cite |
| A card with two real cites keeps both | `test_a_card_with_two_real_cites_keeps_both` ×4: a bold name; the cite character style in small print; a bold name in small print; reading size with an underlined link | both | both |

**Four of your six rows cannot fail first,** and I am not claiming they did: a paragraph that
stays a cite has the same reading with and without the rule. Their proof is a mutant, named in the
[mutation table](#mutation-for-change-4).

**The 300-word cite-style paragraph, built two ways:**

* **In a cite paragraph style** (`CiteParagraph`), 355 words in small print. The classifier reads
  it from the style, the rule never sees a guess, and it stays a cite.
* **With a run in the cite character style.** Past 1,000 characters the classifier's style rule
  lets go, and its wiki heuristic catches the paragraph only because the fixture holds an ellipsis
  and a name with a year. That is a guess, in small print, so the rule would move it. The
  cite-style condition is what holds it.
* **What neither shows.** A 300-word paragraph in the cite character style with no ellipsis is not
  a cite to the classifier at all: it falls through to body text, with or without this change.
  That is `debate_core/evidence/`, which is not mine to edit. It is under Follow-up work.

**Mine, for the edges:** the rest of the body follows the re-read paragraph; each paragraph names
its own rule; a run in the underline style does not count as a cite style; first and last words on
their own line under the cite are an `ABBREVIATED` body; a card with a cite and no tag gets its
body too; a whole body before a second cite makes two cards; two guesses in a row are both body; a
short guess between two cites stays a line of the cite, with or without a blank line between; 2,000
characters stays and 2,001 moves; a long first paragraph opening with a name and a year stays; a
long guess with no card open stays.

**Against the parser without the rule,** the final test set: 16 failed, 1,083 passed, 1 skipped
(mutant "the new rule is never applied", below).

### The corpus, before and after

Read-only, `2026.10.10-docx-2`, both parsers run in one process over the same bytes of the 9,741
DOCX sources. "Before" is the parser as you accepted it in the first revision. Counts only.

| Caselist | `CITE_ONLY` before | After | Gained evidence text | Cards before | After | No tag before | After |
|---|---|---|---|---|---|---|---|
| hsld26 | 1,906 | 729 | 1,178 | 64,675 | 64,678 | 1,353 | 1,356 |
| hspf26 | 849 | 400 | 449 | 42,902 | 42,906 | 1,903 | 1,907 |
| hspolicy26 | 1,807 | 1,036 | 773 | 82,563 | 82,565 | 1,092 | 1,094 |
| openev | 169 | 89 | 80 | 8,056 | 8,056 | 98 | 98 |
| **Total** | 4,731 | 2,254 | 2,480 | 198,196 | 198,205 | 4,446 | 4,455 |

* **Paragraphs moved: 3,365.** 2,491 wiki entries and 537 cite lines after the card's cite, and
  337 wiki entries over the bound with no cite before them. 3,007 are highlighted.
* **Cards that gain evidence text where they had none: 2,480,** 2,445 of them with a tag. 1,721
  gain more than 1,000 words; 40 gain 100 or fewer.
* **Cards whose body grows: 885.** They already had a body, and its first paragraph was in the
  cite.
* **`FULL`** goes from 193,465 to 195,951. **`ABBREVIATED`** stays at 0.
* **Card totals: +9. Cards with no tag: +9.** Nine cards end at a real cite that follows the
  re-read paragraph, and that cite starts a card with no tag. In the seven where the cite follows
  directly, the paragraph is highlighted and between 5,673 and 16,871 characters. Cards with no
  tag are `FULL` 3,659 and `CITE_ONLY` 796, from 3,618 and 828.
* **Cards the rule does not reach: 194,831, every one identical in every field** to the same card
  from the parser without the rule. The remaining 3,374 are the 3,365 it reached and the 9 split
  off them.
* **Cards it reached that keep their paragraph range: 3,356.** All keep their tag, undertag,
  section path and provenance. In all of them every line of the old cite and body is still in the
  new cite or body. All 2,324 that had a short cite keep it.
* **The 337 with no cite before them have no cite afterwards:** `full_cite` is empty and
  `short_cite` is null. They had no short cite before either.
* **A knock-on in the existing rule:** with a body open one paragraph earlier, it takes 40 more
  guesses, 11,912 in all. Its code is unchanged.
* **Your 2,902** (`CITE_ONLY` cards holding a cite paragraph over 100 words) **is 460 now.** Cards
  with a body that hold one go from 3,440 to 3,237. In 371 of those it is a guess, down from 654;
  in the rest it is a cite style. Wiki cite paragraphs over 100 words go from 3,515 to 764.
* **The operator's sample source:** 10 cards, the first five `FULL` with tags, as before. The rule
  touches nothing in it.
* **Against the stored `2026.09.20-docx-1`:** 186,634 cards have the same paragraph range and all
  have the same tag. 3,217 differ in text or cite, all through this rule. 2,451 go from
  `CITE_ONLY` to `FULL` and 15,776 from `ABBREVIATED` to `FULL`.

**What it leaves as cites,** among guesses formatted as body and standing before any body:

| Left as a cite | Paragraphs |
|---|---|
| A cite line as the first cite under a tag: 400 characters at most | 342 |
| A wiki entry as the first cite under a tag, 2,000 characters or fewer | 24 |
| Carries the cite character style | 22 |
| Over 2,000 characters with no card open | 19 |
| 2,000 characters or fewer with no card open | 50 |
| Between the card's cite and another cite, and 2,000 characters or fewer | 11 |
| A first paragraph over 2,000 characters that opens with a name and a year | 4 |

**The re-parse figures in the documents are from the final code.** I ran the whole comparison
again after the last code change, and its output is identical to the run before it. `v1-e34-t18`
changed no file under `integrations/`, `evidence/`, `domain/` or `application/ports/`, so the
corpus was not read again after the sync.

### The two corrected evaluation files

Unchanged, line for line, from the first revision's output: completeness right on **4 of 4**
matched cards, boundaries 4 of 5, and every unit score the same. Neither file holds a paragraph
the rule reaches. The evaluation tiers still skip: 28 of 30 label files are uncorrected.

### Mutation for Change 4

The same driver and rules: a clean committed tree, a fresh `HYPOTHESIS_STORAGE_DIRECTORY` for each
run, restore, and check clean. 1,100 tests across the same six paths, 8 to 17 seconds a run, two
batches of under two minutes, on the synced final tree. **Seventeen mutants, seventeen caught.**
Yours are in bold.

| Mutant | Caught | Tests failing |
|---|---|---|
| **A cite style moved to body:** a style match is re-read like a guess | yes | 2 |
| **A cite style moved to body:** a run in the cite character style no longer holds it | yes | 2 |
| **The "already has a cite" condition dropped** | yes | 9 |
| **The formatting condition dropped** | yes | 15, and 4 errors |
| **The length bound removed:** a first guess of any length is body | yes | 3 |
| **The length bound removed** everywhere it is used | yes | 5 |
| The bound one character lower | yes | 1 |
| The bound one character higher | yes | 1 |
| A long first paragraph that opens with a name and a year is body | yes | 1 |
| The between-two-cites condition dropped | yes | 2 |
| The between-two-cites condition held at any length | yes | 1 |
| The look-ahead counts a guess a body would take as a cite | yes | 1 |
| The look-ahead stops at a blank line | yes | 1 |
| Any character style counts as a cite style | yes | 1 |
| A re-read paragraph keeps the guess's confidence | yes | 4 |
| The new rule is never applied | yes | 16 |
| A long guess with no card open is re-read as body | yes | 1 |

* **Which mutant proves each row that could not fail first:** "the formatting condition dropped"
  fails the same-paragraph-as-a-cite and two-real-cites tests; the two "cite style" mutants fail
  the two 300-word fixtures; "the length bound removed" fails the short wiki entry tests.
* **The 4 errors** under "the formatting condition dropped" are test fixtures that check a file's
  digest before use. The 15 failures are assertions.
* **One condition was deleted, not tested.** I had written "and the card has no body" into the new
  rule. No input can reach it with a body open, because the existing rule has already taken the
  paragraph, so no test could tell it from its absence. It is gone (`2c47b8e`).

### Acceptance criteria, as they stand after Change 4

Results are from `6c4a11f`, the tip before this report, synced onto `origin/dev` at `1448452`.

| Criterion | Status | Evidence |
|---|---|---|
| ac1, ac2, ac3, ac5, ac6 | PASS | As in the first report and the first revision. Their tests pass on the synced tree. |
| ac4, first half: `parser_version` bumped | PASS | Still `2026.10.10-docx-2`. Nothing has written it. |
| ac4, second half: the operator's re-parse | **NOT RUN** | [Operator follow-ups, second revision](#operator-follow-ups-second-revision). |
| **ac7**: a guessed cite after the card's cite, formatted as body, opens the body; with no cite before it, only past a bound derived from the corpus on the conservative side; fixtures each failing first; a cite style stays a cite at any length; the same parser version | PASS, with the four rows that cannot fail first named above, and one fixture built two ways | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_first_corpus_parse_findings.py -k "TestABodyFiledAsTheCardsCite or TestALongGuessUnderATagWithNoCite or TestACiteThatDoesNotOpenTheBody"` → `37 passed`. The whole file: 167 passed. |
| Node: `uv run pytest packages/debate_core/tests/integrations` | PASS | `820 passed in 5.17s` |
| Default suite, two commands | PASS | `packages`: `4125 passed in 66.65s`. `tests`: `1259 passed, 1 skipped, 1 warning in 55.62s`. The skip and the warning are the same two as before. Slow parser timing test: `1 passed`. |
| Static checks and gates | PASS | `pyright` 0 errors; `lint-imports` 12 kept; `ruff check` and `ruff format --check` clean, 583 files; `check_thin_handlers.py`, `check_links.py`, `check_command_blocks.py --base origin/dev`, `docs_index.py --check-descriptions`, `export_schemas.py --check` all OK. |
| t03's structural fixtures | PASS | Unchanged by Change 4. Ten lines still differ from the start commit, each `parser_version`. |
| `uv run scripts/validate_specs.py` | PASS | `OK: 327 files, 38 epics, 269 tasks, 20 releases`. Phase `InProgress`. |

### Files changed in the second revision

- `packages/debate_core/src/debate_core/integrations/docx_parser/parser.py`:
  `_open_the_body_with_a_guessed_cite`, `_followed_by_a_cite`, `_carries_a_cite_style`,
  `LONGEST_GUESSED_CITE_ENTRY_CHARACTERS`, and `_reread_as_body`, which both rules now share.
- `packages/debate_core/tests/integrations/docx_parser/test_first_corpus_parse_findings.py`: 37
  tests, and one docstring's figures.
- `docs/data/caselist-parse-report.md`: a section on the rule, the bound and its result; every
  "after" figure the rule moves; the `ABBREVIATED` tables re-measured.
- `docs/data/parsed-card-store.md`: what `CITE_ONLY` means in each version, and the three rule ids.
- The spec and this report: your review and ac7, committed as you left them (`38caf62`).

Nothing under `debate_core/evidence/` and not `caselist_card_stats.py`.

### Deviations added in the second revision

16. **A run in the cite character style holds a paragraph where it is.** You wrote "a cite guessed
    by a heuristic (never a cite style)". Past 1,000 characters the classifier's style rule lets
    go and its heuristic takes over, so a paragraph the author marked with the cite style arrives
    as a guess. I check the runs as well as the match. It leaves 22 paragraphs alone.
17. **A first paragraph that opens with a name and a year is left, at any length.** A cite run
    together with its card has its cite there, and re-reading it would put the cite in the
    evidence text and leave the card with none. It leaves 4 paragraphs alone.
18. **A short guess between two cites is left.** Not in your rule. Without it the measurement
    showed 20 cards split. Ten of the splits were at small-print paragraphs of exactly 321
    characters, each followed by a cite line of exactly 216: by those lengths, one passage
    disclosed ten times. There the card kept its tag and that line as its body, and the real body
    went to a card with no tag. With the condition 9 cards split. It costs one look-ahead in the
    assembly loop and leaves 11 paragraphs alone.
19. **A guess with no card open is left, at any length.** Re-read as body it would be dropped, and
    the card with it. 19 paragraphs over the bound.
20. **The bound is in characters,** where my proposal and your review counted words.
21. **The 300-word cite-style fixture is built two ways,** as under Fixtures, because the
    classifier's own bound keeps the plain form from being a cite at all.
22. **The data documents' `ABBREVIATED` figures changed** from the ones you accepted in Change 1:
    22,053 bodies with a marker where there were 19,402, and so on down the tables. The rule
    moved cite paragraphs into bodies, so I measured again. No conclusion changes.
23. **Three commands ran past two minutes.** Each was two read-only passes chained in one
    command: about 180 seconds, 165 seconds, and over 170 seconds. The third ran while the
    operator pruned the `uv` cache. Outside that one, no single pass took over 104 seconds. I ran
    one pass per command from then on.
24. **More read-only passes than you listed:** the cite census twice, the before-and-after
    comparison three times (without the between-cites condition, with it, and on the final code),
    and one pass each for the moved paragraphs, the stored cards, the marker histogram and the
    cite-paragraph counts. All write numbers and flags only, outside the repository and outside
    the data directory.
25. **The scratch files are still there:** 258 MB of counts in the session's temporary directory,
    kept until the task closes in case you ask for another cut of them.

### Operator follow-ups, second revision

These replace both earlier sets of operator follow-ups. **The commands are the ones in the first
revision; what differs is the expected counts in step 4.** They close ac4, and they run only after:

1. the PM accepts this second revision;
2. the branch merges with `scripts/task pr v1-e31-t09-first-corpus-parse-findings --partial`;
3. `scripts/task finish v1-e31-t09-first-corpus-parse-findings --partial` closes it out.

**The PM hands over one combined order with `v1-e31-t08`'s steps.** t08's by-eye sample runs
between step 5 and step 7 here. Don't run any of this while `caselist pull` is running.

**What to know before starting.**

- **Disk.** Each version directory is about 5.8 GB on this Mac and in each bucket. The re-parse
  writes a second one beside the first. **The old one stays where it is**, here and in both
  buckets; whether and when it goes is a PM follow-up, not a step here.
- **`v1-e31-t08` is merged.** This one re-parse covers both tasks and all four parser changes: the new directory's occurrence
  rows are built under `card-fingerprint-v2`.
- **A weekly pull since 2026-10-10** adds sources. "Sources" and "to parse" then rise by what it
  imported, and the other counts with them.

**1. Start in the main checkout, on an updated `dev`** (seconds):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
git branch --show-current
git status --short
git pull --ff-only origin dev
git log --oneline -1 --grep='^v1-e31-t09-first-corpus-parse-findings:'
git log --oneline -1 --grep='^v1-e31-t08-short-card-recall:'
export DEBATE_ENV=dev
uv run debate-research caselist runs --last 1
df -h ~/.debate-research
```

Expected: `dev`; `git status` prints nothing; each `git log` prints one line; the last pull run has
finished; `df` shows **at least 8 GiB available**.

* **Either `git log` prints nothing:** that merge is not on `dev` yet. Stop.
* **Less than 8 GiB available:** stop. **Delete nothing**, the old version directory least of all.
  Send the `df` line; freeing space is the PM's decision.

**2. The dry run, and a fingerprint of the old directories** (about a minute; writes nothing under
the data directory; needs no AWS session):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
export DEBATE_ENV=dev
for c in hsld26 hspolicy26 hspf26 openev; do uv run debate-research --json caselist parse --caselist ${c} --dry-run | jq -c '.data | {caselist, version, new_version, superseded, fingerprint_version, to_parse, skipped, suppressed}'; done
find ~/.debate-research/dev/parsed/*/2026.09.20-docx-1 -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 > ~/parsed-old-version-before.txt
cat ~/parsed-old-version-before.txt
```

Expected for each caselist: `version` `2026.10.10-docx-2`, `new_version` true, `superseded`
`2026.09.20-docx-1`, `fingerprint_version` `card-fingerprint-v2`, `skipped` 0 and `suppressed` 0.
`to_parse` is 4,461 for hsld26, 2,657 for hspolicy26, 3,906 for hspf26 and 102 for openev, as the
store stood on 2026-10-10. Any other `version` or `fingerprint_version` means the build is not
this one: stop and paste the four lines back.

**3. The dev re-parse and publish** (about 30 minutes in all; the first full parse measured 518 s
for hsld26, 747 s for hspolicy26, 352 s for hspf26 and 106 s for openev). One caselist at a time.
Run it only if step 1 showed 8 GiB available.

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

**4. The counts to paste back** (about 3 minutes; prints counts, versions and sizes only):

```zsh
for c in hsld26 hspolicy26 hspf26 openev; do jq -c '(.data // .error.details) | {caselist, version, superseded, fingerprint_version, sources, parsed, cards, unsupported, failed, failure_rate, store, elapsed_seconds, publish: .publish.counts}' ~/reparse-dev-${c}.json; done
for c in hsld26 hspolicy26 hspf26 openev; do echo ${c}; find ~/.debate-research/dev/parsed/${c}/2026.10.10-docx-2/sha256 -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.cards[] | "\(.completeness) \(if .tag == null then "no-tag" else "tagged" end)"' | sort | uniq -c; done
for c in hsld26 hspolicy26 hspf26 openev; do jq -r '"\(.schema_version) \(.fingerprint_version)"' ~/.debate-research/dev/parsed/${c}/2026.10.10-docx-2/occurrences.jsonl | sort | uniq -c; done
head -1 ~/.debate-research/dev/parsed/hsld26/2026.09.20-docx-1/index.jsonl | jq -c '{schema_version, parser_version}'
grep -rlF '"tag":""' ~/.debate-research/dev/parsed/*/2026.10.10-docx-2/sha256 | wc -l
find ~/.debate-research/dev/parsed/*/2026.09.20-docx-1 -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | diff - ~/parsed-old-version-before.txt && echo "old directories unchanged"
ls -d ~/.debate-research/dev/parsed/*/*
du -sh ~/.debate-research/dev/parsed
```

Expected, if no weekly pull has run since 2026-10-10. The first loop:

| Caselist | Sources | Parsed | Unsupported | Failed, by reason | Failure rate | Cards | Uploaded |
|---|---|---|---|---|---|---|---|
| hsld26 | 4,461 | 4,354 | 101 | 6: `MALFORMED_XML` 5, `NOT_A_ZIP` 1 | 0.14% | 64,678 | 4,464 |
| hspolicy26 | 2,657 | 2,629 | 28 | 0 | 0% | 82,565 | 2,660 |
| hspf26 | 3,906 | 2,650 | 1,256 | 0 | 0% | 42,906 | 3,909 |
| openev | 102 | 101 | 0 | 1: `COMPRESSION_RATIO_EXCEEDED` | 0.98% | 8,056 | 105 |
| **Total** | 11,126 | 9,734 | 1,385 | 7 | | 198,205 | 11,138 |

No `FORBIDDEN_XML_CONSTRUCT` anywhere: it was 23. The second loop prints four lines for each
caselist, and **no line beginning `ABBREVIATED`**:

| Caselist | `FULL tagged` | `FULL no-tag` | `CITE_ONLY tagged` | `CITE_ONLY no-tag` | Cards | With no tag |
|---|---|---|---|---|---|---|
| hsld26 | 62,863 | 1,086 | 459 | 270 | 64,678 | 1,356 |
| hspolicy26 | 80,790 | 739 | 681 | 355 | 82,565 | 1,094 |
| hspf26 | 40,751 | 1,755 | 248 | 152 | 42,906 | 1,907 |
| openev | 7,888 | 79 | 70 | 19 | 8,056 | 98 |
| **Total** | 192,292 | 3,659 | 1,458 | 796 | 198,205 | 4,455 |

The completeness split is the sum of each pair: `FULL` 63,949, 81,529, 42,506 and 7,967;
`CITE_ONLY` 729, 1,036, 400 and 89; `ABBREVIATED` 0. In the stored `2026.09.20-docx-1` it is
`ABBREVIATED` 8,418, 10,524, 2,972 and 529, and `CITE_ONLY` 2,439, 2,130, 1,007 and 196.

* **The third loop** prints one line for each caselist, `2 card-fingerprint-v2`, with the number of
  occurrence rows. Occurrence and cluster counts are t08's to expect, not predicted here.
* **The `head` line** prints `{"schema_version":1,"parser_version":"2026.09.20-docx-1"}`: the old
  directory is as it was.
* **The `grep` line** prints 0: no record says `"tag":""`.
* **The `diff` line** prints "old directories unchanged".
* **`ls`** shows two directories for each caselist, and **`du`** about 11.6 GB.

These figures come from running this branch's final parser over the same sources, read-only, on
2026-10-10. A count that differs with no pull in between is
worth sending back before prod. A few `ABBREVIATED` lines after a pull are not a fault: a real
first-and-last-words disclosure would be one.

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
with its tag, and **each reads `FULL`, the first included**. In the first parse the second and
third stored cards had no tag; they were the rest of the first card's body, and are in it now. The
other four files tallied as right before should still be. Record tallies only; the file and the
tags are real disclosures. Then:

```zsh
rm -f /tmp/parse-sample.docx
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
```

**Before step 7: `v1-e31-t08`'s ac5 sample runs here, between the dev re-parse and the prod
publish. A "different card" verdict in that sample stops the prod publish.** Do not run step 7
until that sample is done and clean.

**7. The prod publish**, from the same dev data directory, only after dev looks right and t08's
sample is clean (about 15 minutes; nothing is parsed again; the first measured 279, 370, 202 and
55 s):

```zsh
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
uv run debate-research --json caselist parse --caselist hsld26 --dry-run | jq -c '.data | {caselist, version, fingerprint_version, to_parse, skipped}'
uv run debate-research --json caselist parse --caselist hsld26 --publish --confirm-prod > ~/reparse-prod-hsld26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspolicy26 --publish --confirm-prod > ~/reparse-prod-hspolicy26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist hspf26 --publish --confirm-prod > ~/reparse-prod-hspf26.json; echo "exit $?"
uv run debate-research --json caselist parse --caselist openev --publish --confirm-prod > ~/reparse-prod-openev.json; echo "exit $?"
uv run debate-research store ls parsed/hsld26/2026.10.10-docx-2/index.jsonl
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

* **`DEBATE_STORAGE__DATA_DIR` is the point of this block.** Without it the prod profile reads an
  empty `~/.debate-research/prod` and publishes nothing.
* **The dry run** must show `version` `2026.10.10-docx-2`, `fingerprint_version`
  `card-fingerprint-v2`, `to_parse` 0 and `skipped` 4,461. If `to_parse` is not 0, the data
  directory is wrong: stop.
* **Each publish** should exit 0 and upload what dev's did: 4,464, 2,660, 3,909 and 105.
* **Paste back** the first loop of step 4 with `reparse-prod-` in place of `reparse-dev-`.
* **The `unset` at the end matters.** A shell left on prod with the dev data directory is how the
  next command would write to prod unchecked.
* **Prod's `parsed/<caselist>/2026.09.20-docx-1/` prefixes stay**, as dev's do.

The JSON summaries hold counts, digests and keys, and no names or paths. Keep them out of the
repository all the same. Whoever closes ac4 records the counts in
`docs/data/caselist-parse-report.md` and sets the Goal to `Succeeded` in a small spec PR.

### Follow-up work added in the second revision

- **A cite in the cite character style past 1,000 characters (E31, classifier).** 53 of the 69
  first wiki cites between 1,001 and 1,500 characters carry that style. They are real cites that
  the style rule let go and the wiki heuristic caught because they hold an ellipsis. One without
  an ellipsis becomes body text. The fix is the profile's `maximum_cite_characters` or the style
  rule, in `debate_core/evidence/`.
- **A small-print line under the cite (labelled evaluation).** 218 lines of 400 characters or
  fewer, small print with no highlighting, opening with a word and a number, directly under a
  cite and followed by more body. Read as the body's first line now. 9 hold a URL.
- **A card written as one paragraph behind its cite.** 460 `CITE_ONLY` cards still hold a cite
  paragraph over 100 words, and 295 wiki cite paragraphs are over 1,000 words. Most open with a
  bold name. Splitting the cite from the words is the same model question as the short wiki
  entries, which stay `CITE_ONLY` as you ruled.
- **The 337 cards with no cite.** Their cite may be on the tag line or missing from the file.
  Nothing here looks for it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-10

**Notes:**

Accepted as a partial merge. ac4's re-parse stays NOT RUN, and the Goal stays `InProgress`.
Merge with `scripts/task pr v1-e31-t09-first-corpus-parse-findings --partial`. As promised, the
scope does not widen again: everything still open is follow-up work.

**Change 4:**

* **The bound was derived properly.** Paragraphs marked as cites stop at 1,517 characters and
  resume at 2,679. Any bound in the gap moves nothing marked, and 2,000 leaves alone the 11
  unmarked paragraphs a tighter one would have moved.
* **"The 194,831 cards the rule does not reach are identical in every field"** is the guarantee
  that matters most for a change to card bodies, and you checked it by running both parsers over
  the same bytes.
* **The extra conditions are justified, each from a count, and each has a mutant:**
  * Deviation 16: a run in the cite character style still counts as a cite past the classifier's
    1,000 characters.
  * Deviation 17: a name and a year still mark a first paragraph as a cite.
  * Deviation 18: a short guess between two cites is left alone. It came from finding 20 split
    cards and reading what they were, one passage disclosed ten times. That is the method doing
    its job.
  * Deviation 19: a guess with no card open is left alone.
* **The nine cards that now split** at a real cite after a long body are a fair cost, and you
  named it rather than hiding it in a total.
* **Deviations 20 to 24:** accepted. On Deviation 23, one pass per command is the right habit.
* **Deviation 25:** delete the 258 MB of scratch counts when the task closes, after this
  acceptance.

**What this task has done, across three rounds, before anything is re-parsed:**

* 23 refused files are readable;
* about 11,000 cards that were not cards are gone;
* the `ABBREVIATED` label means what it says;
* 2,480 cards with their body in the cite field have evidence text;
* a UTF-16 route past the XML refusal is closed;
* a nullable tag has a store schema version to say so.

That is a large correction to what E32 will count, found by measuring rather than assuming. It
also corrected two premises of mine along the way.

**Follow-up work, filed by the PM after the re-parse, when the real counts are in:**

* the classifier's cite heuristics and the 1,000-character style bound (`debate_core/evidence/`);
* cards written as one paragraph behind their cite, together with short wiki entries as
  abbreviated disclosures (one model question);
* the 218 small-print lines under a cite, for the labelled evaluation;
* the 337 cards with no cite;
* making `ParsedCard.tag` `str | None` now that `v1-e31-t08` has merged;
* the compression-ratio guard on parts the parser never opens;
* CardMirror's control characters, as a policy question;
* `.cmir` as a format of its own;
* retention of superseded version directories.

**The operator run:** the PM hands Charlie one combined order with `v1-e31-t08`'s ac5 sample,
using your second-revision follow-ups. Charlie's disk now has about 76 GiB free, so step 1's
8 GiB check passes with room to spare.
