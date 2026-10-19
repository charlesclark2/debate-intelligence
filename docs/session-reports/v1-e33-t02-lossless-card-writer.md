# Session report: v1-e33-t02-lossless-card-writer

| | |
|---|---|
| Task | `v1-e33-t02-lossless-card-writer` — Lossless card writer |
| Spec | [`plan_specs/v1/e33-file-builder/t02-lossless-card-writer.yaml`](../../plan_specs/v1/e33-file-builder/t02-lossless-card-writer.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t02-lossless-card-writer` |
| Session status | PARTIAL: the session's work is done; ac6, the coach's Word check and the CardMirror round-trip, is NOT RUN |

## Summary

The lossless card writer exists behind a new port,
`debate_core.application.ports.evidence_file_writer.EvidenceFileWriter`. Given a recipe resolved by
`v1-e33-t01`, it builds a Verbatim `.docx` and its `<file>.provenance.json` sidecar. Each card's
paragraphs are deep-copied as OOXML from the source's own parsed XML, found by the occurrence's
element indices and checked against its fingerprint first. The style table comes from
`templates/base.docx`, generated from the E31 style profile and never from a source. The new text is
the coach's headings, tag overrides and analytics, one header line, and the data-use policy's
provenance line below every cite (PM amendment to ac2, 2026-10-19).

Before handing a file back, the writer re-parses it with the E31 parser (`2026.10.18-docx-5`). It
refuses any card that does not read as its source.

**The Goal stays `InProgress`.** ac6 needs the coach to open the three fixture files in Word with
Verbatim, and the operator to run the CardMirror round-trip. Both are under
[Operator follow-ups](#operator-follow-ups). Merge with `scripts/task pr v1-e33-t02-lossless-card-writer --partial`.

**Read first:**

* **[The highlighted-cite refusal](#the-provenance-line-and-the-highlighted-cite):** the provenance line
  stands between a highlighted cite and its body, so those cards are refused. Per your ruling this is
  (a) now and (d) through `v1-e31-t24`. It reaches the 645 highlighted cites `v1-e31-t19` counted.
* **[Deviations](#deviations-from-the-spec)**, especially the CardMirror check, which ADR-0014 keeps
  out of CI.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `base-template`: Base document generated from the style profile | Done | `scripts/build_file_base_template.py` writes `templates/base.docx` from the profile. Your Word defaults are added to `verbatim.yaml`, each marked "Word default, not measured". A drift test and `--check` are shown failing. |
| `run-copier`: OOXML run copier with style remapping | Done | Tracked changes are resolved the parser's way. Styles are re-mapped through the profile, and an unmapped one becomes a warning. Hyperlinks are re-created. Forbidden characters are counted per card through t15's own function. Five kinds of content are refused, the fifth being TABLE (your FYI ruling). |
| `file-assembly`: Evidence file assembly behind the port | Done | The read-back names the provenance line as the cause when it is one, without knowing any parser rule (your ruling). The `.docx` is a function of the recipe and the sources alone. |
| `provenance-sidecar`: Provenance sidecar manifest | Done | `FileProvenanceManifest`, plus `docs/data/file-provenance.schema.json` with a drift test, as t01 did it. |
| `fidelity-and-compat`: Fidelity suite, Word/Verbatim and CardMirror | Session's part done | The re-parse suite passes. Pyright and import boundaries pass. The coach's check is NOT RUN. |

## Acceptance criteria

Goal criteria:

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: re-parsing a built fixture file with the E31 parser gives each card's evidence text, cite text and formatting spans as parsing it in its source does | **PASS** | `uv run pytest packages/debate_core/tests/integrations/docx_file_writer/test_fidelity.py` → `31 passed`. Coverage, each comparing evidence text, cite text, emphasis coverage per highlight colour, and exact font-size spans, card by card: synthetic cards holding named and direct underline, emphasis, bold, five highlight colours, sizes 12/16/22/26, a tracked insertion, a deletion, a comment, and U+0001 and U+FFFE; every E31 structural fixture with cards, one file each and all together; ten cite shapes, each checked to be read by the rule its name says. Parser version: **`2026.10.18-docx-5`**, asserted by `test_the_parser_ac1_is_measured_with_is_the_current_one`. The highlighted-cite shape is the one exception, refused (below). |
| **ac2** (PM amendment 2026-10-19): the API takes no card text; overrides, analytics and the policy's provenance line are the only strings written; an overridden tag is coach-authored with the original's hash | **PASS** | `test_assembly_takes_no_card_text_through_its_api`: the request is `(resolved, built_at)`, and no field reachable from it is named for evidence, cite, runs, body or text. `test_assembly_adds_no_text_but_headings_overrides_analytics_the_header_and_provenance_lines`: every paragraph of a built file is copied from a source or is one of the allowed strings. `test_provenance_marks_an_overridden_tag_as_the_coachs_with_the_original_tags_hash`. The line comes from the occurrence and its disclosure record (`provenance_line`). Without a disclosure it names no team (`test_assembly_writes_the_line_without_a_team_for_a_card_with_no_disclosure_on_record`). Ten cite shapes re-parse with the line read as undertag and in neither the cite nor the evidence. |
| **ac3**: headings in the profile's styles; source character styles re-mapped; an unmapped style keeps its direct formatting and is warned, never silently dropped | **PASS** | `test_assembly_writes_the_recipe_in_order_in_the_profiles_styles` (Heading1–4, Analytic, Undertag, written out in full by hand). `test_source_character_styles_are_remapped_to_the_profile_ids` covers re-mapping by alias id, drifted name, `basedOn` and the cite alias. `test_an_unmapped_style_keeps_its_direct_formatting_and_is_listed_as_a_warning` and `test_provenance_lists_an_unmapped_style_as_a_warning` cover the warning in the sidecar. |
| **ac4**: images, text boxes, embedded objects and footnotes refused as UNSUPPORTED_CONTENT and listed; no partial file | **PASS** | `test_content_that_cannot_be_copied_losslessly_is_refused_by_kind` covers image, text box, embedded object, chart and footnote. Also tested: a table, an object with no relationship, ink behind a relationship, and every kind one card holds. At file level, `test_refusal_a_card_with_content_that_cannot_be_copied_refuses_the_whole_file` covers each kind, and `test_refusal_every_card_that_cannot_be_copied_is_listed` gives two cards, two refusals and no bytes. A picture inside a tracked deletion does not refuse its card. |
| **ac5**: the sidecar validates against `docs/data/file-provenance.schema.json` with one entry per card; the same recipe and sources give byte-identical `.docx` and sidecar, with fixed timestamps and no author metadata | **PASS** | `test_provenance_sidecar_validates_against_the_committed_schema` (jsonschema 4.26). The schema also refuses `VERIFIED`. `test_provenance_has_one_entry_per_card_in_file_order`. `test_deterministic_the_same_request_builds_the_same_bytes`. `test_deterministic_the_order_sources_were_stored_in_changes_nothing`. A later `built_at` changes only the sidecar's `built_at`, and another zone gives the same bytes. Zip entries are in a fixed order, dated 1980-01-01, created on MS-DOS. `core.xml` holds the title and no creator, lastModifiedBy or dates. |
| **ac6**: the coach opens each format's fixture file in Word with Verbatim without a repair prompt; the CardMirror round-trip, conditional on ADR-0014 | **NOT RUN** (Word half reported; CardMirror half pending) | **Word with Verbatim, reported by the operator on 2026-10-19:** the three files, built by follow-up 1 (LD 4 cards, PF 4, Policy 5), were checked and "everything looked correct", including the `[Disclosed: …]` line under each cite in the Undertag style. **CardMirror:** the harness's `npm install` failed on CardMirror's own `postinstall` (`sh: patch-package: command not found`). The install command is corrected (follow-up 3), and the round-trip is to be re-run. Needs the coach in Word and the operator's Node harness. ADR-0014 answered "Yes", so the round-trip applies, and it is operator-run outside CI and `validate-dev` (Deviation 1). The files are built by `scripts/build_example_evidence_files.py`, and `test_example_files.py` builds them in its own run: Policy 5 cards, LD 4, PF 4, each with a pinned card, written outside the repository. |

Node criteria:

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Base template matches the style profile | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_file_writer/test_base_template.py` → `11 passed` |
| Run copier tests pass on synthetic OOXML | PASS | `… test_run_copier.py` → `44 passed` |
| Assembly and determinism tests pass | PASS | `… test_writer.py -k "assembly or deterministic"` → `19 passed` |
| Provenance schema exists, contains `source_sha256` | PASS | `grep -c source_sha256 docs/data/file-provenance.schema.json` → `2`; `uv run scripts/export_file_provenance_schema.py --check` → `OK` |
| Provenance manifest tests pass | PASS | `… test_writer.py -k provenance` → `17 passed` |
| Re-parse fidelity suite passes offline | PASS | `… test_fidelity.py` → `31 passed` |
| Type check passes for debate_core | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` |
| Import boundaries hold (no E06 renderer import) | PASS | `uv run lint-imports` → `Contracts: 12 kept, 0 broken.` The renderer module does not exist yet, so the boundary is a test that reads the writer's imports (`test_the_writer_never_imports_the_e06_docx_renderer`), agreed in your FYI ruling 4. |
| Coach opens built files in Word with Verbatim (CardMirror if ADR-0014 adopts it) | NOT RUN | As ac6. |

### The provenance line and the highlighted cite

The parser reads a highlighted cite (`v1-e31-t19`'s `assembly-highlighted-cite-before-the-body`) as a
cite only when the next paragraph that is not page furniture is body. The provenance line stands
between them, so the built file reads that cite as body: the card's cite and its evidence both change.

Your ruling (2026-10-19) was (a) now and (d) through `v1-e31-t24`:

* The line goes below every cite.
* Such a card is refused as `READBACK_MISMATCH`, with the reason "the provenance line stands between a
  highlighted cite and its body".
* The writer knows no parser rule. When a card fails the read-back, the writer re-parses the same file
  with that card's line left out. If the card then reads as its source, the line is the cause. Where the
  cite above the line is highlighted, the reason says so; otherwise it says "the provenance line below
  the cite changes how the card reads".

`test_a_highlighted_cite_is_refused_until_the_parser_steps_over_the_line` pins this, and it flips by
itself:

* It first asks the parser whether a highlighted cite with an Undertag line before its body is still a
  cite.
* At `2026.10.18-docx-5` it is not, so the test asserts the refusal and its reason.
* Once `v1-e31-t24` makes it one, the test asserts that the same card builds and reads back as its
  source. The writer needs no change of its own.
* `test_today_the_parser_does_not_step_over_the_line` fails the day the parser changes, which is the
  signal `v1-e31-t24` will see.

**How many stored cards this reaches:** `v1-e31-t19` counted **645 highlighted cites** in 233,643
cards: 599 with a bold opening, 38 with a styled head, 8 with one bracket. That count was taken
2026-10-18, by re-parsing the `2026.10.12-docx-3` store read-only. I did not count again: that needs
the operator's data directory, which this session does not read. All three kinds are read by the rule
the line defeats, and both shapes I built (bold opening, one bracket) are refused.

## Red first

The tests and a refuse-nothing skeleton were committed together as `c8468b0`, before the
implementation (`8531b06`). The skeleton has the real names and signatures:

* the copier copies nothing and refuses nothing;
* the writer writes a file with no body and a sidecar with no cards;
* the base has an empty style table, and the zip is written with the clock;
* t15's function ignores the stand-in, and `check_replacement_character` accepts anything;
* the profile's and the sidecar's checks are off.

```text
$ uv run pytest -n 0 -p no:randomly --tb=line -q packages/debate_core/tests/integrations/docx_file_writer packages/debate_core/tests/evidence/test_style_profile.py
104 failed, 106 passed in 2.16s
```

The failures, grouped by their `E` lines (counted from the recorded run):

* 18 in `test_fidelity.py`: `assert 0 == 1` and `assert 0 == 2`. The built file has no cards to read back.
* 10 `DID NOT RAISE ValueError`: the stand-in guard.
* 5 `assert False` at `isinstance(result, UnsupportedCard)`, the refusal of each kind, and 13 more
  `assert False` at the writer's `FileBuildRefusal` checks.
* About 15 `IndexError: tuple index out of range`: no copied paragraphs, and no sidecar entries to index.
* The rest are the expected values written by hand:
  * `assert '[Disclosed]' == '[Disclosed: …Round 4]'` (four line shapes);
  * `assert [] == [('Analytic', …` (the file's paragraphs);
  * `assert {(2026, 10, 19, 1, 19, 54)} == {(1980, 1, 1, 0, 0, 0)}` (the clock in the zip);
  * `assert None == ''` (the stand-in);
  * `assert [] == [2, 0]` (per-card counts);
  * `Id="rId3"` missing from the relationships;
  * the two profile-marker checks.

The 26 writer-side tests that passed at red, each for a reason I can name:

* Data the skeleton keeps (2): the Word-default list, and the nine measured definitions.
* Pins on the parser and the fixtures, not on the writer (4): the parser version; the synthetic sources
  hold every shape; the list of structural fixtures with cards; the parser does not yet step over the line.
* Static boundaries (2): no E06 import, no model call.
* What the skeleton satisfies trivially (13): the API's shape; a naive time refused (the port is real);
  no author or source metadata; the schema drift check and schema validation of a sidecar with no
  cards; the versions; the sidecar's name; allowed stand-ins; no stand-in for a clean source; the
  example script's guard, its unchanged recipes, and two runs alike; the schema order and determinism
  of an empty style table.
* Three determinism tests that passed **only because both builds fell in the same clock second**
  (same request, later request, other zone). The zip-date test is the one that fails reliably, and it
  did. A second recorded run gave 105 passed, consistent with one of these straddling a second.

The 79 profile tests that passed were the existing ones, plus the "nine measured" check.

## Mutation table

Driver: `mutants.py` in the session scratchpad. It commits nothing:

* It asserts each mutated file is committed and keeps its bytes.
* It applies a mutant only when its text matches exactly once.
* It runs `uv run --frozen pytest -n 4 -p no:randomly -q --tb=no -rf` over
  `tests/integrations/docx_file_writer`, `tests/evidence/test_style_profile.py` and
  `tests/domain/test_file_provenance.py`, plus `tests/integrations/docx_parser` for `package.py`
  mutants.
* **Every run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`**. No test here uses Hypothesis; the
  setting is per working agreement 8.
* It restores each file and checks its SHA-256, and `git status --porcelain` was empty after every batch.
* It reads a mutant as caught from an `N failed` in pytest's summary. The first round counted
  `xfailed` as a failure, and that misread K03; fixed below. No mutant errored at collection.

Final run, against `8659a3c`: **56 of 56 applicable caught**. Two were not applicable because their
code was deleted.

| Mutant | File | Mutation | Result | First test that caught it |
|---|---|---|---|---|
| R01 | `run_copier.py` | a tracked insertion is not unwrapped | CAUGHT (3 failed) | `test_a_tracked_insertion_is_kept_and_a_deletion_dropped_as_the_parser_reads_them` |
| R02 | `run_copier.py` | a tracked deletion is kept | CAUGHT (4) | same |
| R03 | `run_copier.py` | a comment reference is kept | CAUGHT (1) | `test_a_comment_reference_inside_a_run_with_text_is_dropped_and_the_text_kept` |
| R04 | `run_copier.py` | rsids and paragraph ids are kept | CAUGHT (1) | `test_no_author_date_or_editing_fingerprint_survives` |
| R05 | `run_copier.py` | a paragraph-mark revision is kept | DELETED | see below |
| R06 | `run_copier.py` | styles are not re-mapped | CAUGHT (2) | `test_a_stretch_underlined_by_an_alias_beside_the_profiles_own_style_reads_back` |
| R07 | `run_copier.py` | an unmapped style is dropped silently | CAUGHT (2) | `test_provenance_lists_an_unmapped_style_as_a_warning` |
| R08 | `run_copier.py` | a style the base defines is removed | CAUGHT (5) | `test_source_character_styles_are_remapped_to_the_profile_ids` |
| R09 | `run_copier.py` | a heuristic tag keeps no tag style | CAUGHT (1) | `test_a_heuristic_tag_is_given_the_profile_tag_style` |
| R10 | `run_copier.py` | the line is placed after the wrong paragraph | CAUGHT (18) | `test_a_card_in_profile_styles_is_copied_element_for_element` |
| R11 | `run_copier.py` | a hyperlink keeps the source's relationship id | CAUGHT (2) | `test_assembly_writes_a_hyperlinks_target_into_the_built_files_relationships` |
| R12 | `run_copier.py` | a hyperlink with no target keeps a dangling id | CAUGHT (2) | `test_a_hyperlink_to_an_internal_target_is_kept_as_text_with_a_warning` |
| R13 | `run_copier.py` | numbering is kept | CAUGHT (1) | `test_numbering_is_dropped_with_a_warning` |
| R14 | `run_copier.py` | a picture is called an object | CAUGHT (4) | `test_refusal_…_refuses_the_whole_file[image]` |
| R15 | `run_copier.py` | a text box in a drawing is not called one | CAUGHT (3) | `test_refusal_…_refuses_the_whole_file[text_box]` |
| R16 | `run_copier.py` | a footnote reference is copied | CAUGHT (4) | `test_refusal_…_refuses_the_whole_file[footnote]` |
| R17 | `run_copier.py` | an object element is not refused by name | CAUGHT (1) | `test_an_embedded_object_is_refused_even_with_no_relationship` |
| R18 | `run_copier.py` | a relationship attribute is not refused | CAUGHT (1) | `test_anything_else_that_points_into_another_part_is_refused` |
| R19 | `run_copier.py` | a table is copied | CAUGHT (1) | `test_a_table_inside_a_card_is_refused` |
| R20 | `run_copier.py` | a text-box paragraph in range is not refused | DELETED | see below |
| R21 | `run_copier.py` | content judged before deletions are dropped | CAUGHT (1) | `test_a_picture_somebody_deleted_does_not_refuse_the_card` |
| R22 | `run_copier.py` | replacements in text are not counted | CAUGHT (6) | `test_forbidden_characters_are_written_as_the_replacement_character_and_counted` |
| R23 | `run_copier.py` | the stand-in is written, not U+FFFD | CAUGHT (6) | same |
| R24 | `run_copier.py` | the source is never re-opened with a stand-in | CAUGHT (6) | same |
| R25 | `run_copier.py` | the stand-in is chosen without checking the source | CAUGHT (1) | `test_the_count_holds_when_the_source_uses_the_first_private_use_character` |
| R26 | `run_copier.py` | a comment's run is kept | CAUGHT (1) | `test_comments_bookmarks_proofing_and_permission_marks_are_dropped` |
| W01 | `writer.py` | no provenance line is written | CAUGHT (51) | `test_a_file_built_from_a_structural_fixture_reads_back_as_the_fixture[…]` |
| W02 | `writer.py` | no read-back | CAUGHT (5) | `test_a_card_the_line_does_not_change_is_refused_without_blaming_the_line` |
| W03 | `writer.py` | the diagnosis keeps the line | CAUGHT (2) | `test_a_highlighted_cite_is_refused_until_the_parser_steps_over_the_line` |
| W04 | `writer.py` | every line-caused refusal blames a highlighted cite | CAUGHT (1) | `test_refusal_names_the_line_as_the_cause_of_any_change_it_makes_without_knowing_the_rule` |
| W05 | `writer.py` | the card's fingerprint is not checked | CAUGHT (1) | `test_refusal_an_occurrence_that_does_not_point_at_its_card[another-card]` |
| W06 | `writer.py` | the last element index is not checked | CAUGHT (1) | `…[last-index]` |
| W07 | `writer.py` | the tag override is ignored | CAUGHT (22) | `test_t01s_example_recipes_are_not_changed` |
| W08 | `writer.py` | no header line | CAUGHT (3) | `test_assembly_writes_the_recipe_in_order_in_the_profiles_styles` |
| W09 | `writer.py` | the line names no team | CAUGHT (5) | same |
| W10 | `writer.py` | the line departs from the policy's form | CAUGHT (3) | same |
| W11 | `writer.py` | the original tag's hash is not recorded | CAUGHT (1) | `test_provenance_marks_an_overridden_tag_as_the_coachs_with_the_original_tags_hash` |
| W12 | `writer.py` | the per-card count is not recorded | CAUGHT (2) | `test_a_forbidden_character_reads_back_as_the_replacement_character_the_parser_gave` |
| W13 | `writer.py` | warnings are not recorded per card | CAUGHT (1) | `test_provenance_lists_an_unmapped_style_as_a_warning` |
| W14 | `writer.py` | the evidence hash is the cite's | CAUGHT (1) | `test_provenance_records_each_cards_occurrence_and_its_source_hashes` |
| W15 | `writer.py` | the card count is not compared | CAUGHT (1) | `test_refusal_a_built_file_that_reads_as_more_cards_than_were_written` |
| W16 | `writer.py` | a camp card is not refused up front | CAUGHT (1) | `test_refusal_a_camp_card_cannot_be_built_from_a_schema_version_1_recipe` |
| P01 | `package_writer.py` | zip entries carry the clock | CAUGHT (3) | `test_the_committed_base_is_what_the_profile_renders` |
| P02 | `package_writer.py` | zip entries carry the writing system | CAUGHT (3) | same |
| B01 | `base_template.py` | paragraph properties out of the schema's order | CAUGHT (1) | same |
| B02 | `base_template.py` | a team template is ignored | CAUGHT (1) | `test_a_team_template_supplies_the_styles_it_defines_and_nothing_else` |
| B03 | `base_template.py` | a style's underline is not written | CAUGHT (1) | `test_the_committed_base_is_what_the_profile_renders` |
| B04 | `base_template.py` | Word opens the file in compatibility mode | CAUGHT (1) | same |
| B05 | `base_template.py` | the core part names a creator | CAUGHT (1) | `test_deterministic_the_built_file_holds_no_author_no_time_and_no_source_metadata` |
| S01 | `style_profile.py` | an unmeasured definition need not say so | CAUGHT (1) | `test_a_writer_definition_not_measured_must_say_so_in_its_notes` |
| K01 | `docx_parser/package.py` | t15's function ignores the stand-in | CAUGHT (6) | `test_only_the_copied_cards_replacements_are_counted` |
| K02 | `docx_parser/package.py` | any stand-in is accepted | CAUGHT (10) | `test_a_stand_in_that_could_build_markup_or_move_a_word_is_refused[<]` |
| K03 | `docx_parser/package.py` | an internal relationship taken for an external one | CAUGHT (1) | `test_a_hyperlink_to_an_internal_target_is_kept_as_text_with_a_warning` |
| F01 | `file_provenance.py` | the formatting digest does not join touching ranges | CAUGHT (2) | `test_a_stretch_underlined_by_an_alias_beside_the_profiles_own_style_reads_back` |
| F02 | `file_provenance.py` | an override not marked as the coach's is accepted | CAUGHT (2) | `test_an_entry_that_says_what_a_sidecar_must_not_is_refused[override-not-the-coachs]` |
| F03 | `file_provenance.py` | card positions out of order are accepted | CAUGHT (4) | `test_card_positions_run_one_two_three_in_file_order[positions1]` |
| F04 | `file_provenance.py` | built_at written in its own zone | CAUGHT (1) | `test_deterministic_a_time_in_another_zone_is_written_as_the_same_instant` |

Each run took 1.3 to 5.7 s.

The first round, against `8531b06`, left eleven survivors. Each was dealt with in `8659a3c`:

* **R05 and R20 were deleted, not tested** (working agreement 8), because mutation could not tell them
  from their absence:
  * R05 was a loop dropping a tracked change to the paragraph mark. The general passes already do it:
    the mark's `w:ins` is empty and unwraps to nothing, and its `w:del` is dropped.
  * R20 refused a text box's own paragraphs. The paragraph holding the box always comes first in the
    card's range and is refused for the box, so those paragraphs are now skipped.
* **R03**: the comment's run was removed whole first. A test now puts a reference in a run with text.
* **R17 and R18** each caught what the other missed. New tests: an object with no relationship id,
  and ink (a `w14:contentPart` behind `r:id`).
* **W04, W15, W16, K03, F01, F02, F03** had no test:
  * W04 and W15 now use two small test parsers that wrap the real one. One loses the cite of a card
    carrying the line, standing in for a line-caused change to a cite that is not highlighted, which
    no shape does today. The other reads one card more.
  * W16: a camp card.
  * K03: a hyperlink to an internal target.
  * F01: an alias beside the profile's own underline. The source reads two spans and the built file
    one, which is why the digest compares coverage.
  * F02 and F03: unit tests of the sidecar model.
* **K03 first showed as caught.** The driver counted `2 xfailed` as a failure; the real line was
  `1149 passed, 2 xfailed`. I fixed the classification and checked every earlier row for the same
  misread: no other row had one.

### The guards, failing for their reasons

Each was applied to the committed file, run, restored and checked by SHA-256; `git status` was empty
afterwards.

| Change | Check | Result |
|---|---|---|
| Heading2's underline in `verbatim.yaml` changed, base not regenerated | `test_the_committed_base_is_what_the_profile_renders`; `scripts/build_file_base_template.py --check` | `1 failed`; `stale: …/templates/base.docx`, exit 1 |
| A sidecar field's description changed, schema not regenerated | `test_provenance_schema_committed_matches_the_models`; `scripts/export_file_provenance_schema.py --check` | `1 failed`; `stale: docs/data/file-provenance.schema.json`, exit 1 |
| `import boto3` in `writer.py` | `uv run lint-imports` | the AWS SDK contract `BROKEN`, `11 kept, 1 broken`, exit 1 |
| `import httpx` in `run_copier.py` | `uv run lint-imports` | the httpx contract `BROKEN`, `11 kept, 1 broken`, exit 1 |

Before the first generation, `--check` on each script also exited 1 (`stale`), with no file present.

## Measurements

**Default selection, in eighths.** `uv run --frozen pytest -n auto -m "not slow and not live" --part K/8 -q -p no:randomly`,
one part at a time under a 115 s `alarm`. The load average was 5 to 25.

| Part | Result | Time |
|---|---|---|
| 1/8 | 1109 passed | 54.5 s |
| 2/8 | 1113 passed | 43.6 s |
| 3/8 | 1109 passed, 2 warnings | 47.2 s |
| 4/8 | 1102 passed, 1 warning | 44.3 s |
| 5/8 | 1096 passed | 52.5 s |
| 6/8 | 1107 passed, 1 xfailed | 42.2 s |
| 7/8 | 1 failed, 1109 passed | 34.2 s |
| 8/8 | 1109 passed, 1 xfailed | 39.2 s |

That is 8,854 passed and 2 xfailed. The one failure is
`tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline`, known on this
Mac until the baseline is written; not investigated. The time-limit test did not fail.

CI's other commands:

* `uv run ruff format --check .` → clean; `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_core` and the four scripts → `0 errors`
* `uv run lint-imports` → `12 kept`
* `uv run python scripts/check_command_blocks.py`, `scripts/docs_index.py --check-descriptions` and
  `scripts/check_links.py` → pass
* `uv run scripts/validate_specs.py` → `OK`

**The existing style fixtures are unchanged by the profile's additions.** `scripts/generate_style_fixtures.py`
now writes only the measured definitions. Regenerated into the scratchpad, every part of all six
fixtures is byte-identical to the committed ones (the `.docx` containers differ only by zip
timestamps).

## Files changed

* **`plan_specs/…/t02-lossless-card-writer.yaml`**: your ac2 amendment, marked; `debate_core.evidence`,
  `debate_core.testing` and `pyproject.toml` in `constraints.packages`, marked as agreed by you.
* **`debate_core/application/ports/evidence_file_writer.py`** (new): the port, the request, the built
  file, the refusal codes and `UnsupportedContentKind`.
* **`debate_core/domain/file_provenance.py`** (new): `FileProvenanceManifest` and its entry, the text
  and formatting digests, and the schema renderer.
* **`debate_core/integrations/docx_file_writer/`** (new):
  * `base_template.py`: the base and its generator;
  * `run_copier.py`: the copier;
  * `writer.py`: assembly, sidecar, read-back;
  * `package_writer.py`: the deterministic zip;
  * `templates/base.docx`: generated.
* **`debate_core/integrations/docx_parser/`**: no parser output changes, so no version bump.
  * `package.py`: t15's `_replace_forbidden_characters` takes a replacement (U+FFFD by default), with
    `check_replacement_character` guarding it; `open_debate_docx` passes it through;
    `read_part_relationships` is new; `DocxPackage.document_part` is new.
  * `parser.py`: the body walk is published as `body_paragraphs`, so the writer numbers paragraphs
    with the parser's own walk.
* **`debate_core/domain/style_profile.py`** and **`evidence/style_profiles/verbatim.yaml`**: your Word
  defaults, the `measured` flag, `is_default`, `writer_document_defaults`, and the check that an
  unmeasured value says so.
* **`debate_core/testing/file_builder.py`** (new): the synthetic world the tests and the fixture script share.
* **`scripts/`**:
  * `build_file_base_template.py` (new);
  * `export_file_provenance_schema.py` (new);
  * `build_example_evidence_files.py` (new, for ac6);
  * `generate_style_fixtures.py`: measured definitions only, so the fixtures stay as they are.
* **`docs/data/file-provenance.schema.json`** (generated).
* **`pyproject.toml`**: `docx_file_writer` in the AWS SDK and httpx contracts' source lists.
* **Tests** (new):
  * `tests/integrations/docx_file_writer/`: `test_base_template.py`, `test_run_copier.py`,
    `test_writer.py`, `test_fidelity.py`, `test_example_files.py`, `conftest.py`;
  * `tests/domain/test_file_provenance.py`;
  * three tests added to `tests/evidence/test_style_profile.py`.

## Deviations from the spec

1. **No `tests/compat/cardmirror/roundtrip.mjs` and no `slow` round-trip test.** ADR-0014 answered
   question 1 "Yes", so the CardMirror check applies. But it also says the Node harness is never run in
   CI, `validate-dev` or nightly: it is operator tooling. Per your ruling, the operator runs the
   existing `scripts/cardmirror-roundtrip/` and `scripts/compare_docx_roundtrip.py` on the three built
   files as part of ac6 (below).
2. **ac2 amended by you** (2026-10-19): the policy's provenance line is written below every cite. Cards
   whose highlighted cite the line defeats are refused until `v1-e31-t24` (your ruling, above).
3. **TABLE is a fifth `UNSUPPORTED_CONTENT` kind** beside ac4's four (your FYI ruling 2).
4. **Outside the original `constraints.packages`:**
   * `debate_core.evidence`: the Word defaults in `verbatim.yaml`, your ruling 1;
   * `debate_core.testing`: `file_builder`, your FYI ruling 3;
   * `pyproject.toml`: your FYI ruling 4;
   * `docs/data/file-provenance.schema.json`: named in the spec's own outputs.
5. **"Build files from the scrubbed E31 structural fixtures"**: done, and also from synthetic sources
   built in memory, as your notes asked. The fixtures are themselves synthetic.
6. **`profile_version` is not bumped** (your FYI ruling 1).
7. **A camp (OpenEv) occurrence is refused** as `SOURCE_UNREADABLE` ("cannot be referenced by a schema
   version 1 recipe"). t01's schema cannot reach one, and your t01 ruling 3 made camp pins a follow-up.

## Decisions and assumptions

1. **Finding a card.** The writer re-parses the source with the running parser. It takes the card that
   runs exactly from the occurrence's first to its last element index, and requires its exact
   fingerprint to be the recipe's and the row's. The plan node's "evidence hash" is this: a row carries
   a fingerprint, not a text hash. A source that changed under a row, or a row pointing at the wrong
   paragraphs, is `OCCURRENCE_MISMATCH`. Source bytes come from the existing `SnapshotStore.get`, which
   re-hashes what it reads, so no new port.
2. **Copying from the parser's own tree.** The source is opened with `open_debate_docx`, guards and
   all, and paragraphs are numbered with the parser's own walk (`body_paragraphs`). A forbidden
   character has therefore already been replaced exactly as the parser replaces it, and ac1 holds for
   it by construction (your note).
3. **The per-card count of forbidden characters**, through t15's own function. When a source had any,
   it is opened a second time with a stand-in in place of U+FFFD: the first Private Use character that
   source does not hold. Each stand-in in a copied card is counted and written as U+FFFD, so a U+FFFD
   the source wrote itself is never counted. `check_replacement_character` refuses a stand-in that could
   build markup or move a word.
4. **What is dropped, and why.** Each item mirrors a parser rule or the forbidden list:
   * `w:ins` and `w:moveTo` are unwrapped; `w:del`, `w:moveFrom` and `w:delText` are dropped;
   * comment ranges, comment references and their runs, bookmarks, `proofErr`, permission ranges,
     `rPrChange`/`pPrChange`, an in-paragraph `sectPr`, `lastRenderedPageBreak`, every `w:rsid*`, and
     `w14:paraId`/`textId`;
   * numbering (`w:numPr`), with a warning: the built file has no numbering part, and the parser reads
     no list number as text.
5. **Styles.** A style the profile resolves becomes the profile's id for the same unit or emphasis:
   by id, name, `basedOn` chain or de-duplication suffix, exactly as the classifier resolves it. A
   style the base defines is kept (`Hyperlink`, `Normal`). Any other is removed and warned, and its
   direct formatting stays. A copied tag is given the profile's tag style even when the source's was
   found by the heuristic, so every tag shows in the navigation pane.
6. **Formatting is compared as coverage**: which characters each emphasis and highlight colour covers,
   touching ranges joined, plus exact font-size spans. The parser joins touching spans only when the
   same rule found them, so re-mapping an alias can turn two spans into one over the same characters
   (shown by test). `formatting_sha256` in the sidecar is that reading, so t04 can recompute it from a
   re-parse.
7. **The read-back is the one guard** (your ruling). Every built file is re-parsed and each card's tag,
   cite, evidence, formatting and provenance line compared with its source, as well as the card count.
   The cause is found by asking the parser (decision 8), never from rule ids.
8. **The provenance line.** It takes the policy's example form:
   `[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]`.
   * The date is the occurrence's first snapshot (`snapshot`). The sidecar records both first and
     latest.
   * The side is written Aff, Neg, Pro or Con.
   * With no tournament or round, the line ends at the side. With the side unknown, it ends at the
     tournament and round.
   * With no disclosure on record it is `[Disclosed: <caselist> <snapshot>]`.
9. **The header line**:
   "Disclosed cards (FILE_IMPORT) from <caselists>, each copied from the file that disclosed it and not
   verified by this platform. Who disclosed each card is below its cite." It is in the Analytic style.
   No part of a built file contains the token `VERIFIED`, which a test checks.
10. **The `.docx` does not depend on `built_at`.** It goes into the sidecar only. The core part holds
    the title and nothing else, so the same recipe and sources build the same file on any day. That
    is ac5 in its stronger form, and it suits t05's deduplication.
11. **The base template**: the profile's 15 definitions and document defaults; Word compatibility
    mode 15 in `settings.xml` (also a Word default, not measured); an empty body; no theme, numbering
    or font table parts; no `sectPr`, so Word's page defaults apply. `CiteParagraph` and `CardBody` are
    not defined. Fewer than 0.3% of surveyed files use them, and a copied paragraph in either keeps the
    id the parser reads.
12. **The read-back's diagnosis writes the file twice** only when a card fails. The second file is
    never handed back.

## Operator follow-ups

**1. Build the three fixture files** (about 5 s). Run it in the task worktree. It writes outside the
repository and refuses a directory inside a git working tree.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e33-t02-lossless-card-writer
uv run scripts/build_example_evidence_files.py --output ~/e33-example-files/built
```

Success looks like three lines: `LD: …ld-space-colonization-nc.docx (4 cards)`,
`PF: …pf-data-center-moratorium-con-blocks.docx (4 cards)` and
`POLICY: …policy-nhi-politics-da-answers.docx (5 cards)`, each with its `.provenance.json` beside it.

**2. The coach's check (ac6).** Open each of the three `.docx` files in Word with Verbatim. Report for
each, yes or no:

* Did Word ask to repair the file?
* Does the navigation pane show the pocket, hat, block and tag levels?
* Do underline, emphasis and highlighting look as a Verbatim user expects?
* Does each card show its `[Disclosed: …]` line below its cite in the Undertag style?

**3. The CardMirror round-trip (ADR-0014; operator tooling, never in CI).** The first block is one-time
setup, about 30 s, and needs Node 20 and GitHub access for the pinned CardMirror. A plain
`npm install` stops with `sh: patch-package: command not found`, as it did on the operator's first
try on 2026-10-19. CardMirror's `postinstall` runs a tool it lists only as a dev dependency, and its
one patch is to its collaborative-editing sync layer, nothing the round-trip uses. So the scripts are
skipped and esbuild's alone is run; `scripts/cardmirror-roundtrip/README.md` says why.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e33-t02-lossless-card-writer/scripts/cardmirror-roundtrip
npm install --ignore-scripts
npm rebuild esbuild
```

Then the round-trip and the comparison, under a minute for three files:

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e33-t02-lossless-card-writer/scripts/cardmirror-roundtrip
npm run roundtrip -- --input ~/e33-example-files --output ~/e33-cardmirror-out
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e33-t02-lossless-card-writer
uv run python scripts/compare_docx_roundtrip.py --manifest ~/e33-cardmirror-out/roundtrip-manifest.json --output ~/e33-cardmirror-out/summary.json
```

Success looks like this:

* `roundtrip` exits 0 with three files under the category `built`;
* `summary.json` reports no differences, only the known normalizations (underline encoding,
  whitespace, soft hyphens).

Paste the summary's per-category counts back. Its rows are keyed by SHA-256 prefix and carry no text.

## Follow-up work

1. **`v1-e31-t24`** (yours): the highlighted-cite look-ahead steps over an Undertag line.
   `test_today_the_parser_does_not_step_over_the_line` will fail, and the pinned refusal test will then
   assert the card builds. Nothing in the writer changes.
2. **`v1-e33-t04`**: `text_sha256` and `formatting_sha256` in `debate_core.domain.file_provenance` are
   the readings the sidecar's hashes use; a re-parse of a built file recomputes them. The writer
   already refuses a file that fails them, so t04's check is a second reading, on a file at rest.
3. **`v1-e33-t03`** writes `<file>.docx` and `provenance_sidecar_name(<file>.docx)` from
   `BuiltEvidenceFile`, and reports a `FileBuildRefusal`'s cards as the refusals list them.
4. **The camp-pin follow-up** (your t01 ruling 3) needs two things here: the OpenEv form of the
   provenance line (`[OpenEv: <camp> <year> — <event>, <file title>]`), and a source document for a
   camp occurrence, which the writer now refuses.
5. **A team's own `styles.xml`**, once scrubbed and committed, feeds
   `scripts/build_file_base_template.py --team-styles`. The base's drift test would then need to
   render with it.
6. **Numbered lists in cards** lose their numbers, with a warning. Carrying a numbering part is a small
   task if coaches want it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
