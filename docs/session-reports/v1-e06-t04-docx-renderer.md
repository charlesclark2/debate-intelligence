# Session report: v1-e06-t04-docx-renderer

| | |
|---|---|
| Task | `v1-e06-t04-docx-renderer` — DOCX renderer |
| Spec | [`plan_specs/v1/e06-card-cutting/t04-docx-renderer.yaml`](../../plan_specs/v1/e06-card-cutting/t04-docx-renderer.yaml) |
| Epic / release | `v1-e06-card-cutting` / `v1.3` |
| Branch | `task/v1-e06-t04-docx-renderer` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`render_cards_docx` (`debate_core.evidence.docx_renderer`) writes the cards of one t05
`CardManifest` as a Verbatim .docx with python-docx. Each card is:

* its tag as a `Heading4`;
* a red banner, for a card that is not VERIFIED, naming its reason codes;
* its cite: the short cite in the cite style, the rest at the profile's full-cite size, then a mark
  for each unverified or student-cleared field;
* its evidence paragraph.

An optional pocket, hat and block are written once at the top. Evidence runs come only from CardSpan
offsets (`run_segmentation.py`, a pure function, tested first). Every evidence run is a slice of
`evidence_text`; the omission marker and `Interpolation.rendered` are runs of their own. The manifest
is embedded byte for byte in a custom XML part, and `read_embedded_manifest` (standard library only,
for t07) gives it back. `ExportService.export_docx` is the DOCX side of the service; it receives the
renderer as a port.

**The Goal stays `InProgress`.** Every criterion passes except ac5, which is half done:

* **Word: PASS.** The operator opened the rendered sample in Word on 2026-10-27: no repair prompt,
  and the navigation pane shows the headings.
* **LibreOffice: NOT RUN.** The open check is written, marked `slow`, and skips on this Mac (no
  soffice). validate-dev's slow job now installs LibreOffice, so the check first runs there, after
  merge.

All 22 mutants were caught, including two variants of each of the PM's three.

What to look at first:

* **Deviations 1 and 4.** The two new FormatProfile fields (pre-approved), and the spec's "emphasis"
  runs, which the domain cannot express.
* **Decision 2.** The renderer takes, beside each card, its cite text and reason codes. Both are made
  in the application layer, which `evidence` cannot import.
* **Follow-up 1.** python-docx is not a runtime dependency of debate-core yet. t06 must add it to an
  extra when it wires the renderer.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `span-runs`: CardSpan to run segmentation | Done | `evidence/run_segmentation.py`: `segment_runs`, `omission_offsets`, `lay_out_evidence`. Red against a skeleton that applies no spans (`9061d44`): 17 failed, 5 passed (the skeleton already handles no spans, no evidence and a card with no cut; the layout-equals-segmentation property is vacuous while both ignore spans). Green (`e3efcf2`): 22 passed. |
| (profile fields, for the next nodes) | Done | `omission_marker` and `unverified_banner_color` on `FormatProfile`, values in all three YAML files (Deviation 1). The updated `test_format_profile.py` ran against the previous model: 33 failed, 28 passed. The new refusal cases passed vacuously there, because the old model refused the new keys outright; mutant 21 shows the bracket rule bites. Green (`e7c12fa`): 61 passed. |
| `document-structure` | Done | `evidence/docx_renderer.py`, `evidence/card_rendering.py`. Red against a skeleton writing python-docx's empty default document (`84cf61e`): `-k structure` 19 failed, 4 passed. The 4 are the heading name and outline-level checks, which python-docx's own template also meets. The style-table comparison is what pins the definitions. Green (`cec1f8b`): 23 passed. |
| `banners-and-marks` | Done | Red (`47984bb`): `-k unverified` 8 failed, 8 passed. The passes are `CardToRender`'s reason-code checks (committed with the input types in `cec1f8b`, before their tests; mutants 17 and 18 show they bite) and the two "a verified card has no banner or mark" checks, true while nothing drew one. Green (`52b99fa`): 16 passed. |
| `manifest-part` | Done | `evidence/docx_manifest_part.py`. Red against a skeleton that embeds and finds nothing (`72701ea`): `-k manifest` 9 failed, 1 passed (a structure test whose name contains "manifest"). Green (`7a8e09e`): 11 passed. |
| (ExportService.export_docx) | Done | `application/export_service.py`, `application/ports/card_document.py`. Red against a skeleton that refuses everything (`66018f5`): 6 failed. Green (`9eceb71`): 6 passed. |
| `renderer-suite` | Done | The LibreOffice check (`slow`), the validate-dev install step and its tests (`6bcfe9e`; the step's 3 tests failed against the workflow without it), and the quality gates below. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the evidence paragraph concatenates to exactly `Card.evidence_text` once the renderer's markers and interpolations are taken out; runs carry underline/highlight exactly over the CardSpan ranges (read back) | PASS | All read back with python-docx, independently of the renderer. `test_structure_the_evidence_runs_are_the_card_spans_condensed_where_nothing_is_read`: t02's VERIFIED news card against 11 runs written by hand from t04's paragraphs and t02's `NEWS_SPANS` (text, underline, highlight, size), the marker at the cut. `test_structure_the_evidence_reads_back_as_exactly_the_cards_evidence_text`: the same card with two interpolations, one at the cut. `test_structure_unicode_tabs_breaks_overlaps_cuts_and_interpolations_read_back_exactly`: a hand-built card with Æ, ø, curly quotes, an em dash, 🐘, a tab, a blank line, overlapping spans across a cut, and interpolations at the start, at the cut and at the end. Each strips the additions where the *card* says they go (`evidence_read_back`, its own arithmetic) and compares text and per-character underline/highlight against the spans. Mutants 3 to 6 caught. |
| ac2: tags, cites and pocket/hat/block use the profile's style names and outline levels, so the file opens with navigable headings in Word with Verbatim | PASS (Word with Verbatim: see ac5) | `-k structure`, 23 passed. `test_structure_heading_styles_carry_the_style_profiles_names_and_outline_levels`: `Heading1` to `Heading4`, names `heading 1` to `heading 4`, outline levels 0 to 3, written by hand. `test_structure_the_style_table_is_the_one_the_lossless_writer_generates_from_the_style_profile`: `word/styles.xml` is canonically equal to E33's `render_styles_xml(profile)`. `test_structure_the_verbatim_parser_reads_the_card_back_under_its_headings`: the project's own Verbatim parser reads the rendered file as one card, with the tag, the section path (pocket, hat, block) and short cite `Whitfield 26`. In Word, the operator saw the headings in the navigation pane (2026-10-27). Verbatim's own navigation was not reported. |
| ac3: UNVERIFIED cards render a banner listing reasons; unverified cite fields are marked | PASS | `-k unverified`, 16 passed. The banner is `UNVERIFIED — not a finished card: CITATION_UNVERIFIED, EVIDENCE_UNVERIFIED, CARD_INCOMPLETE`, in red `FF0000` from the profile, in the base's Normal style, under the tag. A FAILED card's banner says FAILED. A mix of four cards has a banner on exactly the two that are not VERIFIED. Reasons are codes only, required exactly when the card is not VERIFIED. The banner holds no evidence word. Marks: `[author unverified] [date unverified] [URL unverified]` from the citation's flags; an optional field only when shown unverified; `[author cleared by student]` for a cleared field, never "unverified". Mutants 1, 2, 15 to 18 and 22 caught. |
| ac4: a custom XML part in namespace `urn:debate-intelligence:manifest:v1` with one entry per card, readable back via a helper t07 uses | PASS | `-k manifest`, 11 passed. The part (`customXml/item1.xml`) is one `manifest` element in the namespace, with no children, whose text is `serialize_manifest(manifest)` byte for byte. It is related from the document, with an `itemProps1.xml` naming the namespace. `read_embedded_manifest(path)` returns an equal `CardManifest`, and `read_embedded_manifest_bytes(path)` the same bytes. Both survive a python-docx save and reopen with a bibliography-style custom XML part added beside it. "One entry per card" is the manifest's `cards` list: one manifest per document, its cards in document order (`test_one_manifest_lists_every_card_of_the_document_in_document_order`, 3 cards). The reader refuses no manifest, two, a DOCTYPE, and an element holding more than text. Mutants 19 and 20 caught. |
| ac5: opens without repair prompts in Word and LibreOffice (LibreOffice headless conversion test, `slow`, run in validate-dev's slow tier, which installs LibreOffice) | Word: PASS. LibreOffice: NOT RUN | **Word:** the operator opened the rendered sample (Operator follow-up 1) in Word on 2026-10-27 and reported no repair prompt, with the headings in the navigation pane. **LibreOffice:** `test_libreoffice_opens_a_rendered_document_headless_and_reads_every_paragraph` is marked `slow`. `uv run pytest packages/debate_core/tests/evidence/test_docx_renderer.py -m slow -rs` → `1 skipped` ("LibreOffice (soffice) is not installed here"). validate-dev's slow job did not install LibreOffice, so it now does (`Install LibreOffice for the rendered-DOCX open check`). `tests/scripts/test_validate_dev_workflow.py` → 21 passed, the 3 new tests failing first against the old workflow. The check first runs in validate-dev after merge (Operator follow-up 2). |
| ac6: each omitted range is marked at its evidence-text offset with the profile's omission marker, each interpolation rendered at its anchor with `Interpolation.rendered`; neither is ever in `evidence_text` or read back as evidence | PASS | The marker is `FormatProfile.omission_marker` (`" … "`), which may hold no bracket (validator, mutant 21). The renderer adds brackets only through `Interpolation.rendered` (mutant 12). Placement: `test_an_omission_sits_where_its_kept_text_before_it_ends`, `test_each_of_several_omissions_sits_after_all_the_kept_text_before_it`, the layout example, and two properties against an oracle over random cards with cuts, interpolations and spans. The read-backs in ac1 show neither is read as evidence. PM mutants 5 and 6 caught. |
| Node `span-runs`: `uv run pytest packages/debate_core/tests/evidence/test_run_segmentation.py` | PASS | 22 passed in 1.92s |
| Node `document-structure`: `uv run pytest packages/debate_core/tests/evidence/test_docx_renderer.py -k structure` | PASS | 23 passed in 1.79s |
| Node `banners-and-marks`: `... -k unverified` | PASS | 16 passed in 1.69s |
| Node `manifest-part`: `... -k manifest` | PASS | 11 passed in 2.25s |
| Node `renderer-suite`: `uv run pytest packages/debate_core/tests/evidence/test_docx_renderer.py` | PASS | 49 passed in 2.84s (the `slow` check deselected by default) |
| Node `renderer-suite`: `uv run pyright packages/debate_core` | PASS | 0 errors, 0 warnings, 0 informations (19 s) |
| Forbidden: emitting evidence text other than `Card.evidence_text` | Holds | Evidence runs are `evidence_text[start:end]` from offsets. The only other text in the paragraph is the profile's marker and `Interpolation.rendered`, each a run of its own. Text a .docx cannot carry as written (a carriage return, which python-docx reads back as a line feed, or a character XML forbids) is refused, never altered (mutant 13). |
| Forbidden: rendering an UNVERIFIED card without the banner | Holds | A `CardToRender` that is not VERIFIED cannot be built without a reason code. The renderer draws `banner_text` for every status but VERIFIED. Mutants 1, 2 and 18 caught. |
| Forbidden: styling values hard-coded outside FormatProfile | Holds | The style table is the style profile's writer definitions. Paragraph and character styles come from `ResolvedFormatProfile`; sizes, highlight, banner colour and marker from `FormatProfile` (mutant 22). The literals left are content, not styling: the banner wording, the mark labels, the author name. The settings part's compatibility mode 15 is a Word default the lossless writer's base also writes. |

### Mutation run (agreements 8 and 10)

22 mutants over `run_segmentation.py`, `docx_renderer.py`, `card_rendering.py`,
`docx_manifest_part.py` and `format_profile.py`:

* Each was planted on the committed tree by exact replacement, each target asserted to occur once.
  One planting attempt failed on a target the formatter had rewrapped. Its first edit was in place, so
  the file was restored from git and the harness made to restore in a `finally`. That attempt is not
  counted.
* Each ran against `test_run_segmentation.py`, `test_docx_renderer.py`, `test_format_profile.py` and
  `test_export_docx.py` (138 tests; baseline 138 passed) with `-n 0 -p no:randomly` and a fresh
  `HYPOTHESIS_STORAGE_DIRECTORY`.
* The original bytes were written back and compared after each. `git status --porcelain` was empty at
  the end.
* Every mutant failed with assertion failures (exit 1), none with a collection error.
* The Hypothesis properties were checked for what they generate (`--hypothesis-show-statistics`):
  * overlapping underline and highlight in about 40 to 45% of cases;
  * a break where no span starts or ends in about 43%;
  * cards with cuts and spans in about 41 to 47%;
  * an omission and an interpolation at one place in about 10 to 11%.

| # | Mutant | Caught by (first failure) |
|---|---|---|
| 1 | **PM: an UNVERIFIED card renders without the banner** (the renderer drops it) | 6 failed: `an_unverified_card_gets_a_red_banner_under_its_tag_naming_its_reasons_by_code` |
| 2 | **PM: an UNVERIFIED card renders without the banner** (only FAILED gets one) | 5 failed: the same |
| 3 | **PM: an underline run off by one at a span boundary** (starts one character early) | 11 failed: `overlapping_underline_and_highlight_split_where_either_starts_or_ends` |
| 4 | **PM: an underline run off by one at a span boundary** (ends one character late) | 11 failed: the same |
| 5 | **PM: an omission marker is read back as evidence** (written into the evidence run before it) | 4 failed: `structure_the_evidence_runs_are_the_card_spans_condensed_where_nothing_is_read` |
| 6 | **PM: an omission marker is read back as evidence** (it carries the underline style) | 2 failed: the same |
| 7 | runs merged across a break | 9 failed: `a_break_splits_a_run_with_the_same_styles_either_side` |
| 8 | an interpolation drawn before the cut at its place | 4 failed: `the_layout_interleaves_runs_the_cut_and_interpolations_in_reading_order` |
| 9 | a cut placed one character late | 11 failed: `an_omission_sits_where_its_kept_text_before_it_ends` |
| 10 | every marked run highlighted | 3 failed: `structure_the_evidence_runs_are_...` |
| 11 | unread text not condensed | 2 failed: the same |
| 12 | an interpolation written without its brackets | 2 failed: `structure_the_evidence_reads_back_as_exactly_the_cards_evidence_text` |
| 13 | a carriage return written (and read back as a line feed) | 1 failed: `..._cannot_carry_as_written_is_refused_never_altered[\r-U+000D]` |
| 14 | cards that are not the manifest's rendered | 1 failed: `structure_the_cards_must_be_the_manifests_cards_in_its_order` |
| 15 | a cleared field marked unverified | 1 failed: `a_field_the_student_cleared_is_marked_cleared_not_unverified` |
| 16 | a missing optional field marked | 5 failed: `structure_a_verified_card_is_its_tag_its_cite_and_its_evidence_in_that_order` |
| 17 | a reason may be any string | 3 failed: `unverified_reasons_are_codes_...[UNVERIFIED-reasons3-is a code]` |
| 18 | an UNVERIFIED card may come with no reason | 3 failed: `unverified_reasons_are_codes_...[UNVERIFIED-reasons0-its banner must name why]` |
| 19 | the manifest reader opens a part declaring a document type | 1 failed: `the_manifest_reader_refuses_a_custom_xml_part_that_declares_a_document_type` |
| 20 | the manifest's text not escaped | 1 failed: `a_manifest_holding_xml_markup_characters_round_trips_exactly` |
| 21 | an omission marker may hold a bracket | 3 failed: `impossible_values_are_refused[changes5-omission_marker]` |
| 22 | the banner colour fixed in code | 1 failed: `the_unverified_banner_takes_its_colour_from_the_format_profile` |

### Checks before the report (agreement 10)

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (list only) | 128 of 544 test files (23.5%) from 18 changed files |
| The affected set, as `--run` runs it: `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" <the 128 files>` | Stopped by the alarm at 115 s at about 78%, with no failure printed; the load average was 5 to 8. So it is past the two-minute line and left to the PR's `ci` (PM ruling of 2026-10-19). One orphaned xdist worker from this run finished its last test and exited on its own; a later `pgrep` found nothing from this worktree. |
| The changed test directories and the always-run list, under the same alarm: `packages/debate_core/tests/evidence`, `tests/architecture`, `tests/specs`, `packages/debate_cli/tests/test_app.py`, `test_help_rendering.py`, `tests/scripts/test_validate_dev_workflow.py`, and from `packages/debate_core/tests/application`: `test_export_docx.py`, `test_export_service.py`, `test_verify_manifest.py`, `test_card_service.py`, `test_port_conformance.py` | 2095 passed in 31.59 s (load average 24 from other work on the machine) |
| The affected files that read the profiles, the packaging or the workflows: `test_doctor_evidence_profiles.py`, `test_installation.py`, `docx_file_writer/test_fidelity.py`, and from `tests/scripts`: `test_analyze_team_formatting.py`, `test_workflow_runners.py`, `test_install_channel.py`, `test_check_command_blocks.py`, `test_docs_index.py`, `test_dev_prerelease_workflow.py`, `test_release_version.py`, `test_ci_workflow_test_selection.py` | 363 passed in 22.86 s |
| `uv run --frozen ruff format --check .` / `ruff check .` | 1519 files already formatted / All checks passed! |
| `uv run --frozen pyright` (whole repo, as CI) | 0 errors, 0 warnings, 0 informations |
| `uv run --frozen lint-imports` | Contracts: 18 kept, 0 broken |
| `uv run --frozen python scripts/check_thin_handlers.py` | OK: 67 CLI command and API route handlers within 25 statements |
| `uv run scripts/export_schemas.py --check` | OK: 10 schemas up to date |
| `uv run scripts/validate_specs.py` | OK: 478 files, 40 epics, 416 tasks, 22 releases |
| After this report: `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` | OK: no `#` comments in 507 shell code blocks in 189 Markdown files (1 session report changed) |
| `uv run --frozen python scripts/docs_index.py --check-descriptions` | All 55 indexed documents under docs/ have a description |
| `pytest tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` | 191 passed in 2.37s |

## Files changed

* **`debate_core.evidence`**:
  * `run_segmentation.py` (new): the pure span-to-run function and the evidence layout.
  * `card_rendering.py` (new, no document library): `CardToRender`, `CiteText`, `DocumentHeadings`,
    `RenderRefused`, `banner_text`, `cite_marks`.
  * `docx_renderer.py` (new): `render_cards_docx`, the base package from the style profile, fixed
    times.
  * `docx_manifest_part.py` (new, standard library only): the part's XML, `read_embedded_manifest`
    and `read_embedded_manifest_bytes`.
  * `format_profile.py`: `omission_marker` and `unverified_banner_color`.
* **`debate_core.application`**: `export_service.py` (`export_docx`, `render_docx` port argument),
  `ports/card_document.py` (new: `CardDocumentRenderer`).
* **`config/format_profiles/`**: the two values in `team-default`, `flow` and `plain`
  (pre-approved).
* **`.github/workflows/validate-dev.yml`**: one step installing `libreoffice-writer` in the slow job
  (pre-approved).
* **Tests**:
  * `packages/debate_core/tests/evidence/test_run_segmentation.py`, `test_docx_renderer.py` (new);
  * `packages/debate_core/tests/application/test_export_docx.py` (new);
  * `test_format_profile.py` (the new keys, the survey-citation check skipping the two rendering
    choices, the new refusals);
  * `tests/scripts/test_validate_dev_workflow.py` (the install step; not pre-approved, Deviation 2).
* **The spec**: phase only (`InProgress`, set at the start, left there).

## Deviations from the spec

1. **FormatProfile gains two card-rendering choices.** Nothing defined an omission marker or the
   banner's colour and style:
   * the style profile's ellipsis markers are for wiki-converted cites, not evidence;
   * ADR-0018 says only that "the ellipsis is a rendering decision";
   * FormatProfile had neither.

   As pre-approved by the PM, `omission_marker` (`" … "`) and `unverified_banner_color` (`FF0000`)
   are FormatProfile fields with values in all three profiles. The banner is drawn in the base
   style profile's Normal paragraph style. Each YAML value carries a comment saying it is a rendering
   choice, not measured, and a test holds that. t03's `VALID` example and its survey-citation check
   changed with them. The PM amends t03's ac3 in the next batch.
2. **Files outside `constraints.packages`.**
   * Pre-approved: `config/format_profiles`, `.github/workflows` (the one LibreOffice step).
   * Not pre-approved: `tests/scripts/test_validate_dev_workflow.py`, which tests that step beside
     the existing pull-step tests: before the tier, installs `libreoffice-writer`, and a failed
     install fails the step rather than letting the check skip. `debate_core.domain` is unchanged.
3. **ac4's "one entry per card"** is the manifest's `cards` list. There is one manifest per
   document, t05's whole `CardManifest`, as the PM's note says.
4. **No emphasis runs.** The spec names "underline/emphasis/highlight runs", but `SpanStyle` has only
   UNDERLINE and HIGHLIGHT, so a CardSpan cannot mark emphasis and the renderer draws none.
   Segmentation is generic over `SpanStyle`, and the renderer maps span styles to character styles
   in one table (`_CHARACTER_STYLE_OF_SPAN`). An `EMPHASIS` span style would be one entry there, plus
   the domain enum and the `card.markup` contract (E05). See question 3.
5. **ac5's LibreOffice half is NOT RUN** (its Word half passed; see the criteria table), so the Goal
   stays `InProgress`.

## Decisions and assumptions

1. **python-docx over a base built from the style profile.** python-docx's default template carries
   about 800 KB that no profile defines:
   * its own heading styles (blue, italic `Heading4`);
   * `stylesWithEffects`;
   * a thumbnail of some other document;
   * a bibliography custom XML part.

   The renderer instead opens a minimal package it builds from the style profile:
   * the styles part: the profile's document defaults and writer definitions, element for element as
     the E33 writer emits them (a test compares them canonically);
   * Word's compatibility mode 15, as the E33 base sets it;
   * an empty body and an empty core-properties part.

   python-docx then adds the paragraphs and the manifest part. The two writers share the profile and
   produce one style table. Neither imports the other: the layers forbid it.
2. **What the renderer takes.** The cite text and the failure reasons are made in the application
   layer (`format_cite`, `CardFailure`), which `evidence` cannot import. So the renderer takes the
   manifest and, per card, a `CardToRender`: the card, its `CiteText` (short cite and full line) and
   its reason codes. They must be the manifest's cards in its order.
   `ExportService.export_docx` builds them:
   * the cite is `format_cite`'s;
   * the codes are each failure's code, then the verifier's code it carries, once each, e.g.
     `EVIDENCE_UNVERIFIED, CARD_INCOMPLETE`;
   * it refuses failures for a card it is not exporting, and a card that is not VERIFIED with none.
3. **The renderer is a port in the application layer** (`CardDocumentRenderer`). The import contract
   "Document libraries stay inside debate_core.integrations.docx_parser" covers
   `debate_core.application`, indirect imports included. `debate_core.evidence` is not on it, so the
   spec's module locations pass `lint-imports`. The composition root (t06) passes `render_cards_docx`
   in.
4. **Paragraph styles.**
   * Pocket, hat, block and tag must have writer definitions; otherwise the render is refused rather
     than losing navigation.
   * The cite and the evidence use the profile's styles for them when it writes a definition, and
     the default paragraph style otherwise. The verbatim profile defines neither `CiteParagraph` nor
     `CardBody`, so both are `Normal`, as Verbatim files are.
5. **Banner.**
   * Placed directly under the tag, so it is read before the cite.
   * It names the card's own status (`UNVERIFIED` or `FAILED`) and the codes, joined by commas.
   * It is one red run.
6. **Cite marks.**
   * Labels: author, credentials, title, publication, date, URL, accessed date.
   * A required field not verified is "unverified", missing or not. An optional field is marked only
     when it is shown unverified.
   * A cleared field is "cleared by student".
   * The marks are one run after the cite, at the full-cite size.
7. **What the renderer adds to the evidence:**
   * the marker and each interpolation, each a run of its own, never underlined or highlighted (no
     span covers them), at the base size;
   * where a cut and an interpolation share a place, the cut first, since an interpolation is read
     with the text after it.
8. **Same input, same bytes.**
   * The core-property times are the manifest's `generated_at`.
   * Every zip member is stamped with it: python-docx's own save is rewritten with fixed timestamps,
     a dozen lines.
   * The custom XML item id is derived from the manifest's SHA-256.
   * Only `docProps/core.xml` is written. Author and last editor are `debate-research`; there is no
     title, subject, comment or keyword.
9. **The manifest reader** finds the manifest by its element, not by its part name: Word may renumber
   custom XML parts and add its own. It refuses:
   * a part that declares a document type;
   * a part over 64 MiB;
   * a manifest element holding more than text;
   * none, or two.

   Manifest validation errors propagate: a newer build's manifest is t07's to report.
10. **Headings** are one optional pocket, hat and block per document. `Card.format_profile` is not
    consulted: the caller chooses the profile (t06's `--format`).
11. **Read-back is independent.** The tests read with python-docx, which the renderer uses only to
    write, and with the project's Verbatim parser. `evidence_read_back` strips additions by its own
    arithmetic from the card, not by calling the renderer's layout.

## Operator follow-ups

**1. Open the sample in Word (ac5's Word half, ac2's navigable headings), about a minute.** The file
is synthetic: two of the tests' hand-built cards under a pocket, hat and block, one VERIFIED with
Unicode, a cut and interpolations, one UNVERIFIED with its banner. Open it on your Mac:

```bash
open -a "Microsoft Word" /private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e06-t04-docx-renderer/98401fba-622f-433b-8790-c003acaf211a/scratchpad/v1-e06-t04-sample.docx
```

Success looks like:

* no repair prompt;
* the navigation pane shows Aff, Methane, Feedbacks and the two tags;
* the short cites are bold;
* the evidence is underlined and cyan-highlighted where the spans are, with unread text small;
* the second card has a red "UNVERIFIED — not a finished card: CITATION_UNVERIFIED" line under its
  tag.

If you have Verbatim, its heading navigation should show the same. Tell the session or the PM what
you saw. If the scratch file is gone, the PM can ask the session to render it again.

**Result (2026-10-27):** the operator ran the command above and reported no repair prompt, and the
navigation pane shows the headings. The other items in the list were not reported on.

**2. After the merge into dev, check validate-dev's slow tier.** It now installs LibreOffice and runs
`test_libreoffice_opens_a_rendered_document_headless_and_reads_every_paragraph`. A pass there,
with no skip, closes ac5's LibreOffice half. Nothing to run by hand. To run it locally before then,
install LibreOffice (a large install, your call) and run, in the task worktree:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e06-t04-docx-renderer
uv run pytest -m slow packages/debate_core/tests/evidence/test_docx_renderer.py -k libreoffice -rs
```

Success looks like `1 passed` in under a minute; `1 skipped` means soffice is not on the PATH.

### For the PM (relay prompt)

> v1-e06-t04 is done except ac5's LibreOffice half, so the Goal stays InProgress. Four things:
>
> 1. **ac5.** Word passed: the operator opened the rendered sample with no repair prompt and the
>    headings in the navigation pane (2026-10-27). The LibreOffice check is written and marked slow;
>    validate-dev's slow job now installs libreoffice-writer (with workflow tests), and the check
>    first runs there after merge. Recommendation: merge `--partial`, and close ac5 when
>    validate-dev's slow tier passes with no skip.
> 2. **t03 amendment (pre-approved).** FormatProfile has `omission_marker` (`" … "`, no brackets
>    allowed) and `unverified_banner_color` (`FF0000`), in all three profiles. Proposed ac3 wording:
>    "FormatProfile names its base style profile and defines only cite layout, base size,
>    highlight colour, condensed size, and two card-rendering choices: the omission marker and the
>    UNVERIFIED banner colour."
> 3. **Emphasis.** The spec names emphasis runs, but `SpanStyle` has no EMPHASIS, so the renderer
>    draws none. Options: (a) leave it (recommended: the markup contract has no emphasis either);
>    (b) a later task adds `SpanStyle.EMPHASIS` across the domain, the card.markup contract and one
>    renderer table entry.
> 4. **t06 needs python-docx at runtime.** It is only in the dev group today. When t06 wires
>    `render_cards_docx` into the container, python-docx must join debate-core's `docx` extra
>    (pyproject and uv.lock). The installation check covers wired integrations only, so it would
>    not notice an evidence module. Recommendation: add it to t06's spec now.
>
> Deviation 2 lists one test file outside the approved paths (the workflow step's tests).

**The PM's rulings (2026-10-27, review ACCEPTED):**

1. **ac5:** the pull request merges `--partial`. ac5 closes when validate-dev's slow tier runs the
   LibreOffice check with no skip; the Goal stays `InProgress` until then.
2. **t03 amendment:** the PM amends t03's ac3 for `omission_marker` and `unverified_banner_color`.
3. **Emphasis:** (a). No emphasis runs; `SpanStyle` and the `card.markup` contract are unchanged.
4. **python-docx at runtime:** the PM amends t06 to add python-docx to debate-core's `docx` extra
   when it wires the renderer.

## Follow-up work

1. **`v1-e06-t06-cut-command`:**
   * add `python-docx` to debate-core's `docx` extra;
   * build `ExportService(..., render_docx=render_cards_docx)` in the container;
   * pass `CutResult.failures` to `export_docx`.
2. **`v1-e06-t07-verify-docx`:**
   * `read_embedded_manifest_bytes` can feed verify's existing JSON reader, which already reports a
     newer manifest version;
   * a body reader strips the renderer's additions by position from the manifest card, as
     `evidence_read_back` in the tests does: each omission where the kept text before it ends, each
     interpolation before its anchor, a cut before an interpolation at one place.
3. **Emphasis spans (E05/E02)**, if wanted: question 3.
4. **The affected set (128 files)** did not finish inside two minutes under the machine's load at the
   time. It is left to the PR's `ci`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-27

**Notes:**

The renderer that turns a cut card into a Verbatim document: evidence only as slices of
`evidence_text`, additions as runs of their own, the banner on every card that is not VERIFIED, and
the manifest embedded byte for byte.
1. **ac1 to ac4, ac6 and every node criterion pass.**
   * The read-back is independent of the renderer, through python-docx and the project's own
     Verbatim parser, which reads the rendered file back as one card under its pocket, hat and block.
   * The Unicode, tab, overlap, cut and interpolation case reads back exactly.
   * The style table is canonically E33's, from the style profile.
   * Red first per node, each pass explained.
2. **ac5:** Word passed. The operator opened the sample on 2026-10-27 with no repair prompt and the
   headings in the navigation pane. The LibreOffice half runs in validate-dev's slow tier, which now
   installs `libreoffice-writer`, and the PM records it when that tier passes with no skip.
3. **Mutants: 22, two variants of each of the PM's three among them.** The Hypothesis properties were
   checked for what they generate.
4. **Rulings on the relay:**
   * 1: merge `--partial`, ac5 closed from validate-dev.
   * 2: the PM amends t03's ac3 to the proposed wording.
   * 3: (a), no emphasis, since neither `SpanStyle` nor the markup contract has it.
   * 4: the PM amends `v1-e06-t06` to put `python-docx` in debate-core's `docx` extra and wire
     `render_cards_docx` in the container.
5. **Deviations 1 to 5 accepted,** including the workflow step's tests outside the approved paths.
6. **Decisions 1 to 11 accepted,** including:
   * a minimal base built from the style profile rather than python-docx's template;
   * the renderer as an application port;
   * the cite text and reason codes made in the application layer;
   * byte-identical output from `generated_at`;
   * a manifest reader that finds its element by name and refuses document types.
7. **The affected set** (128 files) did not finish within two minutes under load, so it is left to
   the PR's `ci` under agreement 10. The changed directories, the always-run list and the profile,
   packaging and workflow tests passed, and the static checks are clean.

No re-review is needed. The PR merges `--partial`, phase `InProgress`, until validate-dev's slow tier
runs the LibreOffice check.

## PM record, 2026-10-27

Added by the PM. Nothing above is changed, and this section is not a review.

* **validate-dev has not yet run the LibreOffice check on a build that carries this task.** Its last
  three runs (two dispatched on 2026-10-26 and the scheduled run of 2026-10-27) validated
  `v1.1.0-dev.159` (#541), from before this task merged. Each failed in its smoke tier on
  `tests/smoke/test_caselist_backfile.py`. That was not this task's code: the bundled dev profile
  turns the API gate on (`v1-e40-t06`), and the test assumed it off.
* The PM batch of 2026-10-27 (u) pins the gate in that test, and `v1-e01-t41` makes the pull
  request's smoke tier read the bundled profiles. ac5's LibreOffice half closes on the first green
  validate-dev run of a pre-release carrying this task. The Goal stays `InProgress` until then.

## Operator records (recorded by the PM, 2026-10-30)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac5, LibreOffice | NOT RUN | PASS | validate-dev's slow tier on `v1.1.0-dev.164` (`03b23e2`, run `40644901906`, 2026-10-28): LibreOffice 24.2.7.2 installed for the rendered-DOCX open check, no `SKIPPED` line, `slow tier: passed`, `SLOW_RESULT: success` |

Every criterion passes, so the Goal is `Succeeded`.
