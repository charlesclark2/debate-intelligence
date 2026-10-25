# Session report: v1-e04-t04-content-extraction

| | |
|---|---|
| Task | `v1-e04-t04-content-extraction` — Readable-text extraction (HTML + PDF) |
| Spec | [`plan_specs/v1/e04-article-retrieval/t04-content-extraction.yaml`](../../plan_specs/v1/e04-article-retrieval/t04-content-extraction.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t04-content-extraction` |
| Session status | COMPLETE |

## Summary

Two `ContentExtractor` adapters turn fetched bytes into `ExtractedContent`. `TrafilaturaExtractor`
reads web pages with trafilatura, and readability-lxml when trafilatura finds fewer than the configured
minimum characters. `PdfExtractor` reads open-access PDFs with pypdf. The rules that decide a PDF's
text (running headers, footers, page numbers, joining a line that ends in a hyphen, paragraphs) are a
pure module, `debate_core.retrieval.pdf_layout`, built to the PM's rulings of 2026-10-25 and tested
on hand-written lines. Every hyphen join and every removed line is recorded on the output, every
refusal is a typed `ExtractionError` and never part of the text, and metadata hints are
`UnverifiedMetadataHints`. All four goal criteria and every node criterion pass; the Goal is
`Succeeded`. Worth looking at first: the as-built de-hyphenation rule and its fixture counts
(Decisions), the two readings of the PM's rulings flagged under Deviations, and the mutation table.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `extracted-model` — ExtractedContent model and dispatcher | Done | `retrieval/extraction.py`: `ExtractedContent`, `ExtractionQuality` and the hints (renamed `UnverifiedMetadataHints`) moved here from the providers port, as `FetchResult` moved in t02; new `LineJoin`, `RemovedLine`, the refusals, `document_kind` and `ContentTypeDispatcher`. |
| `pdf-extractor` — Open-access PDF extractor | Done | `retrieval/pdf_layout.py` (the rules, no PDF library) and `integrations/pdf_extractor.py` (pypdf reads positioned lines). Red against a skeleton first, then green. |
| `html-extractor` — trafilatura extractor with fallback | Done | `integrations/html_extractor.py`. |
| `golden-tests` — Golden extraction fixtures and gates | Done | `tests/fixtures/extraction/`: three synthetic HTML pages and a synthetic PDF, each with a hand-written `.expected.json` committed before any extractor existed (`a50ea75`); import contracts for the new libraries. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — TrafilaturaExtractor implements the port and, on news, think-tank and .gov samples, returns body paragraphs matching golden files with navigation, ads and comments excluded | PASS | `uv run pytest packages/debate_core/tests/integrations/test_html_extractor.py` → 47 passed. Per sample: paragraphs equal the hand-written list, none of the listed navigation, ad, comment and footer strings appears, hints equal the hand-written ones, and every paragraph is found verbatim in the page's visible text. Port conformance: `test_port_conformance.py` passes in the run below. |
| ac2 — below the configured minimum the fallback runs and `fallback_used` is true | PASS | Same file: for each sample, a minimum equal to the primary's character count leaves `fallback_used` false and one character more makes it true; a table layout trafilatura cannot read is recovered by readability-lxml (`extractor_name` names it). |
| ac3 — PdfExtractor produces paragraphs from a sample open-access journal PDF with running headers, footers and page numbers removed and end-of-line hyphenation joined | PASS | `uv run pytest packages/debate_core/tests/integrations/test_pdf_extractor.py` → 18 passed: the synthetic three-page article gives its 16 hand-written paragraphs, 13 joins and 8 removed lines. The sample is synthetic, as the PM preferred, not a downloaded paper. |
| ac4 — every ExtractedContent carries extractor_name, extractor_version (library version included) and quality signals; unsupported types raise UnsupportedContentType | PASS | `pdf-layout-1+pypdf-6.21.2`; `html-1+trafilatura-2.3.1+readability-lxml-0.9+lxml-6.1.3` (both pinned by tests against the installed versions). The model rejects quality counts that do not match the paragraphs. `UnsupportedContentType` tests in `test_extraction.py`, `test_html_extractor.py`, `test_pdf_extractor.py`. |
| Node `extracted-model`: Extraction model exists (`class ExtractedContent` in `retrieval/extraction.py`) | PASS | `grep -n "class ExtractedContent" packages/debate_core/src/debate_core/retrieval/extraction.py` → line found. |
| Node `html-extractor`: HTML extraction tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/test_html_extractor.py` → `47 passed`. |
| Node `pdf-extractor`: PDF extraction tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/test_pdf_extractor.py` → `18 passed`. |
| Node `golden-tests`: Golden extraction suite passes | PASS | `uv run pytest packages/debate_core/tests/integrations -k extractor` → `65 passed`. |
| Node `golden-tests`: Import boundaries hold | PASS | `uv run lint-imports` → `Contracts: 18 kept, 0 broken.` |

### Red before green

* **Layout rules** (`e40ac28`): 36 tests against a skeleton that removes nothing and joins every line
  with a space: 27 failed, 9 passed. The 9 are the checks of what must survive (captions, one-off
  numbers, repeats outside the edge zones, non-forms, a spaced dash, a column move, blank lines, and
  the character-accounting property), which a do-nothing layout satisfies by construction. The
  journal article's hand-written expectation was among the 27; it then passed unchanged. Three of my
  own expectations were wrong and are corrected in `f07e4b7`, each named in its message.
* **HTML samples:** the extractor's selection swapped for a skeleton (every leaf block on the page,
  no title rule, empty hints) and the golden tests run: 9 failed (paragraphs, excluded boilerplate and
  hints, for each sample), 3 passed (every paragraph is page text, true of any selection). Restored
  from the commit afterwards.

### Checks before the report

The branch changes `pyproject.toml` and `uv.lock`, so `uv run scripts/affected_tests.py --run` printed
`The whole selection is affected: packages/debate_core/pyproject.toml is shared test ground` and ran
nothing. Under agreement 10 and the PM's note, the whole selection is left to the pull request's `ci`.
The import-graph reach of the code-only commits alone (`--diff` per commit, unioned) is 306 test
files, most of them reached through the providers port and the shared fakes; that is also left to CI.
What was run:

| Command | Result |
|---|---|
| `.venv/bin/python -m pytest -q` over `tests/retrieval/`, the two extractor suites and `test_http_fetcher.py`, `test_fakes.py`, `test_port_conformance.py`, `test_snapshot_service.py`, `tests/contracts/`, the tests that read the lock or the extras (`test_aws_extra.py`, `test_installation.py`, `commands/test_doctor.py`, `test_card_download_image.py`), the always-run list (`tests/architecture/`, `tests/specs/`, `test_app.py`, `test_help_rendering.py`) and the docs checks (`tests/docs/`, `test_check_command_blocks.py`, `test_docs_index.py`) | `1770 passed in 29.15s` (30.6 s wall clock) |
| `uv run ruff format --check .` | `1384 files already formatted` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` (77 s) |
| `uv run lint-imports` | `Contracts: 18 kept, 0 broken.` |
| `uv run python scripts/check_thin_handlers.py` | `OK: 61 CLI command and API route handlers within 25 statements` |
| `uv run python scripts/check_command_blocks.py --base HEAD` | `OK: no '#' comments in 486 shell code blocks` |
| `uv run scripts/validate_specs.py` | `OK: 457 files, 40 epics, 395 tasks, 22 releases` |

### Mutation runs

22 mutants on the four places the PM named, plus the HTML title rule. Each run used only the test
files covering the mutated module, `-x`, and a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`
(agreement 8); every catch is a failing test, none a collection error; each file was restored and
checked byte for byte. The catching test is the first one `-x` stopped at.

| Mutant | Result | Caught by |
|---|---|---|
| De-hyphenation: the hyphenated form elsewhere drops the hyphen (**compound fused**) | caught, 0.9 s | `test_a_compound_whose_hyphenated_form_appears_elsewhere_keeps_its_hyphen` |
| De-hyphenation: UNDETERMINED drops the hyphen (**compound fused when unsure**) | caught, 0.8 s | `test_when_neither_spelling_appears_the_hyphen_stays_and_the_join_is_undetermined` |
| De-hyphenation: a join inserts a space (**split word left split**) | caught, 0.8 s | `test_a_broken_word_whose_joined_form_appears_elsewhere_loses_its_hyphen_and_no_space_is_added` |
| De-hyphenation: the joined form elsewhere keeps the hyphen (broken word left hyphenated) | caught, 1.5 s | same |
| De-hyphenation: spellings compared case-sensitively | caught, 2.0 s | `test_spellings_elsewhere_are_compared_case_insensitively` |
| De-hyphenation: the fragment after another break counts as evidence | caught, 1.6 s | `test_the_journal_article_lines_lay_out_as_the_hand_written_expectation` |
| De-hyphenation: the fragment before another break counts as evidence | caught, 2.0 s (**survived the first run**) | `test_other_line_end_hyphenations_are_not_evidence_for_either_spelling` |
| De-hyphenation: a dash after a space is a join | caught, 1.5 s | `test_a_dash_after_a_space_is_an_ordinary_line_break` |
| Removal: a line on one page counts as repeated | caught, 1.6 s | `test_a_line_repeated_at_the_top_of_two_pages_is_a_running_header_and_is_recorded` |
| Removal: every line is in the edge zone | caught, 1.8 s | `test_a_line_repeated_outside_the_edge_zones_stays` |
| Removal: a page-number form may be part of a line (the caption risk) | caught, 3.1 s | `test_a_line_repeated_at_the_top_of_two_pages_is_a_running_header_and_is_recorded` |
| Removal: page numbers need not advance with the page | caught, 1.7 s | `test_numbers_that_do_not_advance_with_the_page_stay` |
| Removal: any edge line, not only the outermost, can be a page number | caught, 1.5 s | `test_a_number_that_is_not_the_outermost_line_stays_even_when_it_fits_the_sequence` |
| Removal: running lines compared without collapsing whitespace | caught, 1.9 s | `test_running_lines_match_with_their_whitespace_collapsed` |
| Removal: uppercase roman numerals accepted (**equivalent in the first run**, see below) | caught, 2.1 s | `test_text_around_a_number_or_an_uppercase_numeral_is_not_a_page_number_form` |
| Fallback: runs at exactly the minimum (`<` becomes `<=`) | caught, 2.4 s | `test_the_fallback_does_not_run_when_the_primary_reaches_the_minimum_exactly[news-article]` |
| Fallback: never runs | caught, 1.9 s | `test_the_fallback_runs_when_the_primary_is_one_character_short[news-article]` |
| Fallback: its text is kept even when shorter | caught, 1.7 s | `test_the_primarys_text_is_kept_when_the_fallback_found_no_more` |
| HTML: the `h1` title kept as a paragraph | caught, 1.6 s | `test_trafilatura_extractor_returns_the_hand_written_paragraphs[news-article]` |
| UnsupportedContentType: an image declared as HTML is read as HTML | caught, 1.7 s | `test_a_type_no_extractor_reads_is_refused_naming_both_types[...image/png]` |
| UnsupportedContentType: the declared type decides before the bytes | caught, 2.1 s | `test_the_bytes_then_the_declared_type_choose_the_extractor[...pdf]` |
| UnsupportedContentType: the PDF extractor accepts any document kind | caught, 4.0 s | `test_what_is_not_a_pdf_raises_unsupported_content_type[...text/html]` |

**22 of 22 caught** on the final run. The first run caught 20. Two survivors, and what was done:

* *The fragment before another line-end break counted as evidence* survived: no test had a fragment
  equal to a spelling another join looks up. `an exam-|ple of an example-|like case` now pins the
  PM's rule (the fragment `example` does not drop `exam-ple`'s hyphen), in `f49b925`.
* *A case-insensitive roman-numeral regex* survived because the regex could not be told apart from
  its absence: `_roman_value` already accepts only lowercase numerals written the standard way. The
  regex was removed (agreement 8), and the mutant retargeted at `_roman_value`, where it is caught.

The property `test_every_character_is_in_the_text_a_removed_line_or_a_dropped_join` was checked for
what it generates (`--hypothesis-show-statistics`, fresh database). Of the run's 300 valid examples
(340 generated, 40 invalid), at least one dropped join appears in about 20%, a kept join in about
28%, removed lines in about 49%, and three or more paragraphs in about 66%. (Hypothesis reports these
as shares of all 340; they are converted here.) It proves accounting (no character created or lost except recorded ones),
not which way a join goes; the example tests do that.

## Files changed

* **`packages/debate_core/src/debate_core/retrieval/`** — `extraction.py` (new: the output model,
  join and removal records, refusals, `document_kind`, `ContentTypeDispatcher`); `pdf_layout.py`
  (new: the PDF rules, no library).
* **`packages/debate_core/src/debate_core/integrations/`** — `html_extractor.py` and
  `pdf_extractor.py` (new adapters).
* **`packages/debate_core/src/debate_core/application/ports/providers.py`** — the three extraction
  models moved out; the port's docstring names the typed refusals.
* **`packages/debate_core/src/debate_core/testing/fakes/providers.py`** — imports the moved models;
  behaviour unchanged.
* **`packages/debate_core/tests/`** — `retrieval/test_extraction.py`, `retrieval/test_pdf_layout.py`,
  `integrations/test_html_extractor.py`, `integrations/test_pdf_extractor.py` (new).
* **`tests/fixtures/extraction/`** — three synthetic HTML pages, the PDF builder and the PDF, four
  hand-written `.expected.json` files, the shared comparison helper, a README recording provenance.
* **`tests/architecture/test_import_contracts.py`** — four planted violations for the two new contracts.
* **`pyproject.toml`, `packages/debate_core/pyproject.toml`, `uv.lock`** — the `extraction` extra and
  dev dependencies; the two new import contracts and the adapters added to the per-adapter lists.
* **`plan_specs/v1/e04-article-retrieval/t04-content-extraction.yaml`** — Goal phase `Succeeded`.

## Deviations from the spec

* **Two files outside `constraints.packages`.** The spec names `debate_core.retrieval` and
  `debate_core.integrations`; the move of `ExtractedContent` to `retrieval/extraction.py` (the node's
  stated output) also edits the providers port, which imported and re-exported it, and the shared
  fake, which built it. Neither changes behaviour.
* **Names.** The node says "MetadataHints and QualitySignals models". The existing
  `ExtractionQuality` keeps its name (t03's spec reads "QualitySignals" as a description of it); the
  hints are renamed `UnverifiedMetadataHints`, so their type says they are unverified, as the PM asked.
* **A paywall marker refusal in the extractor.** Not in the spec; the PM's context asked for it. Only
  schema.org `isAccessibleForFree: false` is read (JSON-LD at any depth, `@graph`, `hasPart`, and
  microdata), because that markup is already parsed for hints. The versioned list of markers stays
  t03's (`paywall_rules.v1.json`); t05 maps `PaywallMarkerFound` to `PAYWALLED`.
* **Two readings of the PM's rulings, for the PM to confirm:**
  * *"Page n of m".* The ruling lists `Page n` and `n of m`, not their combination, which the
    fixture's footer uses. It is accepted as a form (one regular expression in `_ARABIC_FORMS`); if
    the list is meant literally, that line goes and the fixture's page-number lines stay as body text.
  * *"Only spellings that appear mid-line count".* Read as: the fragments on either side of any
    line-end break do not count. A complete word that happens to start or end a line unbroken does
    count (`test_a_word_that_starts_or_ends_a_line_unbroken_is_evidence`). Under the stricter reading
    (no first or last word of any line), the fixture's text would be the same, but two decisions would
    change: `de-|extinction` would be UNDETERMINED (both mid-line `De-extinction`s start a line) and
    `co-|operation` HYPHENATED (its `cooperation` starts a line).
* **No licence allowlist.** The PM ruled that chardet and tld be added to the repo's licence
  allowlist or check if it keeps one. It keeps none (`git grep` for allowlist, liccheck,
  pip-licenses: nothing), so the ruling is recorded here, under Dependencies, and nowhere else.

## Decisions and assumptions

### The PM's rulings of 2026-10-25, as built

1. **De-hyphenation: approved as proposed**, spellings compared case-insensitively and other
   line-end hyphenations not counted as evidence. Both are tested and both have a caught mutant.
2. **Headers and footers: approved, with the caption risk closed.** A page number's whole text must
   be a page-number form, and its number must advance with the page by one offset on two or more
   pages. `test_table_captions_on_consecutive_pages_are_not_page_numbers` puts `Table 2` and `Table 3`
   as the outermost lines of pages 2 and 3, with `Figure 4` at the foot of page 4: nothing is removed.
3. **Licences: chardet 5.2.0 and tld 0.13.2 accepted**, recorded below.
4. **Synthetic HTML samples: confirmed.** Nothing was fetched.

### The de-hyphenation rule

A line ending in a hyphen or dash straight after a non-space character, followed by a line of the
same paragraph, is joined to it with no space, and the join is recorded: paragraph index, offset in
that paragraph, page, the character, whether it was kept, the decision, and the counts of the two
spellings found elsewhere. A soft hyphen is dropped (`SOFT_HYPHEN`); a dash, or a hyphen without a
letter on both sides, is kept (`NOT_A_WORD_BREAK`); between letters the document's other spellings
decide, case-folded and leaving out every fragment beside a line-end break: the hyphenated form
alone keeps it (`HYPHENATED_FORM_IN_DOCUMENT`), the joined form alone drops it
(`JOINED_FORM_IN_DOCUMENT`), and neither or both keeps it (`UNDETERMINED`). `LineJoin` refuses a
decision that disagrees with whether the character was kept, and `ExtractedContent` refuses a kept
join whose character is not at its offset.

**The fixture's counts** (the PM asked for kept, dropped and UNDETERMINED), pinned by
`test_the_journal_article_counts_reported_to_the_pm` and by the hand-written expectation, through
pypdf as well as over the builder's lines: **13 joins: 5 dropped, 8 kept, of which 3 UNDETERMINED.**

| Break | Really | Elsewhere (hyphenated / joined) | Decision | Result |
|---|---|---|---|---|
| `extinc-` / `tion` | broken word | 0 / 2 | `JOINED_FORM_IN_DOCUMENT`: dropped | right |
| `de-` / `extinction` | compound | 2 / 0 | `HYPHENATED_FORM_IN_DOCUMENT`: kept | right |
| `well-` / `intentioned` | compound | 0 / 0 | `UNDETERMINED`: kept | right |
| `conser-` / `vation` | broken word | 0 / 3 | `JOINED_FORM_IN_DOCUMENT`: dropped | right |
| `2019-` / `2024` | year range | (digits) | `NOT_A_WORD_BREAK`: kept | right |
| `long-` / `term` | compound | 2 / 0 | `HYPHENATED_FORM_IN_DOCUMENT`: kept | right |
| `co-` / `operation` | either spelling | 1 / 1 | `UNDETERMINED`: kept | the printed spelling |
| `bio` + U+00AD / `diversity` | broken word | (soft hyphen) | `SOFT_HYPHEN`: dropped | right |
| `popu-` / `lations` | broken word | 0 / 3 | `JOINED_FORM_IN_DOCUMENT`: dropped | right |
| `cost-` / `effective` | compound | 1 / 0 | `HYPHENATED_FORM_IN_DOCUMENT`: kept | right |
| `resur-` / `rection` | broken word | 0 / 0 | `UNDETERMINED`: kept | broken word left hyphenated |
| `envi-` / `ronmental` (pages 2 to 3) | broken word | 0 / 1 | `JOINED_FORM_IN_DOCUMENT`: dropped | right |
| `Okonkwo-` / `Hale` | compound name | 1 / 0 | `HYPHENATED_FORM_IN_DOCUMENT`: kept | right |

Compounds joined without their hyphen: 0. Broken words left hyphenated: 1. The two simpler rules
would have fused 5 compounds (drop between letters) or left 5 broken words hyphenated (keep always).
These are the behaviours on a fixture written to exercise every branch, not rates on real papers
(Follow-up work).

### Running headers, footers and page numbers

Candidates are the three lines nearest each end of a page, by position. A line whose exact text
(whitespace collapsed) is in an edge zone on two or more pages is a running header or footer. Then
the outermost line left at each end is a page number when its whole text is a bare integer,
`Page n` (any case), `n of m`, `Page n of m`, `- n -` (hyphen or en dash) or a lowercase roman numeral
written the standard way, and its number less the page's position in the file is the same on two or
more pages. Everything else stays. Each removal is recorded with its page, edge, reason and text.

**Removed per fixture:** `journal-article.pdf` 8 (page 1: 2, page 2: 3, page 3: 3; 2 running headers,
3 running footers, 3 page numbers; 2 of 72, 3 of 69 and 3 of 11 characters). The page-limit and
stream-limit samples remove nothing (each page's sentence differs; the long page is one page). One-off
short lines inside the edge zones stay: page 1's masthead, `2. Methods`, `ronmental conditions that
caused its loss.`, `4. Conclusion` and `Received 3 March 2026; accepted 9 June 2026.`; in the rule
tests also `Notes` and a lone `2`.

### Paragraphs in a PDF

A paragraph starts at a different type size, a vertical gap over 1.3 times the page's median line
spacing, or a line indented by more than half its type size from the line above. At a page break, or
a move up the page into the next column, it continues unless the line before ended a sentence
(`.`, `!`, `?` or `:`, before any closing quotes or brackets), the type size changes, or the new line
is indented from the one after it. This moves whitespace only.

### Dependencies and their licences, as locked

Locked by the operator on 2026-10-25. Each licence was read from the installed package's own metadata
(`License-Expression`, else `License`, else its classifiers), at the locked version.

| Package | Locked version | Licence (as declared) | Brought in by |
|---|---|---|---|
| `trafilatura` | 2.3.1 | Apache-2.0 | `extraction` extra |
| `readability-lxml` | 0.9 | Apache-2.0 | `extraction` extra |
| `pypdf` | 6.21.2 | BSD-3-Clause | `extraction` extra |
| `babel` | 2.18.0 | BSD-3-Clause | courlan |
| `chardet` | 5.2.0 | LGPL (classifier: LGPLv2 or later) — **accepted by the PM, 2026-10-25** | readability-lxml 0.9 |
| `charset-normalizer` | 3.5.2 (was 3.5.1) | MIT | trafilatura and htmldate (both require `>=3.5.2`) |
| `courlan` | 1.4.0 | Apache-2.0 | trafilatura |
| `cssselect` | 1.3.0 | BSD | readability-lxml |
| `dateparser` | 1.4.3 | BSD-3-Clause | htmldate |
| `htmldate` | 1.11.0 | Apache-2.0 | trafilatura |
| `justext` | 3.0.2 | BSD-2-Clause | trafilatura |
| `lxml-html-clean` | 0.4.5 | BSD-3-Clause | readability-lxml, justext |
| `pytz` | 2026.5 | MIT | dateparser |
| `regex` | 2026.9.29 | Apache-2.0 AND CNRI-Python | dateparser |
| `tld` | 0.13.2 | MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later — **accepted by the PM under MPL-1.1, the option the project elects** | courlan 1.4.0 (trafilatura 2.3.1) |
| `tzlocal` | 5.4.5 | MIT | dateparser |
| `tzdata` | 2026.5 | not installed: locked only for `sys_platform == 'win32'` | tzlocal |
| `lxml` | 6.1.3 (already locked) | BSD-3-Clause | trafilatura, readability-lxml |

Nothing is GPL-only or AGPL. chardet and tld are weak copyleft, used unmodified as installed
libraries. The PM's ruling covers these versions; a later bump of either that changes its declared
licence goes back to the PM. trafilatura's floor in `pyproject.toml` is 2.0 because it was GPLv3+
before 1.8.0.

### HTML choices

* **Strict decoding.** BOM, then the `Content-Type` charset, then `<meta charset>`, then UTF-8;
  `iso-8859-1`, `latin1` and `ascii` labels read as windows-1252, as WHATWG does, so curly quotes
  survive. A page that does not decode is refused (`UnreadableDocument`), never repaired with
  replacement characters. This may refuse some real pages with a stray byte; that is the integrity
  trade, and t05 records it as an access status.
* **trafilatura settings:** `fast=True` (its own internal fallbacks off, so `fallback_used` means
  ours ran), `favor_precision=True`, comments, tables, images, links and formatting off. Tables are
  left out because a data table's cells make poor card text; that is a choice the PM can reverse.
* **The fallback's text is kept only when longer** than the primary's, and `extractor_name` says
  whose text it is. `fallback_used` means the fallback ran.
* **The `h1` is left out of the paragraphs.** It is the title and is reported as the title hint.
  trafilatura puts it in its body as `<head rend="h1">`; the hand-written expectations, written before
  any code, treat it as metadata, and a mutant keeping it is caught.
* **Whitespace.** A `<br>` and any whitespace run inside a paragraph become one space, as a browser
  renders them; without that, trafilatura's `<lb/>` would fuse the words on either side of a line
  break (`test_a_line_break_inside_a_paragraph_never_joins_two_words`).
* **Hints** are raw strings: JSON-LD `headline` or `name` of the first article-type node, else
  `og:title`, else `<title>`; JSON-LD `author`, else `<meta name="author">`; `datePublished`, else
  `article:published_time`; `og:site_name`, else the JSON-LD publisher; `rel=canonical` resolved
  against the final URL. trafilatura's own metadata is not used, because it normalizes dates and names.

### PDF choices

* **pypdf with `strict=False`**, which tolerates structural damage such as a bad cross-reference
  table. Damage that would lose text is refused: a truncated compressed stream raises in both modes
  (probed before choosing), and `test_a_truncated_stream_is_refused_not_read_in_part` pins it.
* **Limits:** 50 MB and 500 pages by default, both checked before any page is read; pypdf's
  decompression ceilings lowered from 75 MB to 20 MB per stream for every filter, through its
  context-local `apply_configuration`, so no process-wide setting changes. An encrypted file is
  refused on its `/Encrypt` entry before any page is read. pypdf's constructor tries an empty
  password itself, so a copy-restricted file would open; the extractor refuses it anyway.
* **Hints** are the information dictionary's `/Title` and `/Author` only.
* **Characters in code.** Hyphens, dashes and quotes in the rules and tests are written as `\u`
  escapes (`5c9bf41`): a literal soft hyphen is invisible in an editor.

### Smaller choices

* **The fallback minimum (default 250, trafilatura's own) and the size limits are constructor
  parameters**, not settings, because settings live in `debate_core.application`, outside this
  task's packages. ArticleService (t05) can pass them from settings.
* **An empty or textless page is an empty extraction**, not a refusal: no paragraphs,
  `fallback_used` true, `character_count` 0, which is what t03's truncation heuristic reads.
* **Extraction is deterministic for its `extractor_version`**: the same bytes twice give equal
  results, tested for both extractors, which is what a later re-extraction check in E03 will need.

## Operator follow-ups

**Lock and install the extraction dependencies** (network; expected runtime about 1 minute). None of
`trafilatura`, `readability-lxml` or `pypdf` was in uv's cache, so the lock could not be made offline.
Where: your Mac.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e04-t04-content-extraction
uv lock
uv sync --all-packages
git status --short
```

Done 2026-10-25: 17 packages added (`trafilatura` 2.3.1, `readability-lxml` 0.9, `pypdf` 6.21.2 and
14 they need), `charset-normalizer` 3.5.1 to 3.5.2, `git status` showed only ` M uv.lock`; committed
as `e2e3f64`.

Nothing else. The whole-selection run is the pull request's `ci` (agreement 10).

## Follow-up work

* **How often each de-hyphenation decision fires on real papers** (E04, after t05). Run in place
  over a sample of open-access PDFs, never committed: share of joins per decision, a hand check of the
  `UNDETERMINED` ones, and how many PDFs are refused as unreadable under `strict=False`.
* **How often strict HTML decoding refuses real pages** (E04, after t05), measured the same way.
* **A licence check in CI** (E01). The repo has no licence allowlist, so the PM's ruling on chardet
  and tld lives only in this report; a check over `uv.lock` would catch a bump that changes a licence.
* **Wiring.** t05 composes `ContentTypeDispatcher(html=TrafilaturaExtractor(), pdf=PdfExtractor())`,
  maps each `ExtractionError` to an access status, and passes the minimum and limits from settings;
  t06 builds it in the CLI's composition root, where `debate-cli` will need debate-core's
  `extraction` extra and the two pinned integration lists (`test_doctor.py`, `test_installation.py`)
  will change.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
