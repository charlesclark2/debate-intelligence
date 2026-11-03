# Session report: v1-e31-t15-zip-guard-and-exporter-quirks

| | |
|---|---|
| Task | `v1-e31-t15-zip-guard-and-exporter-quirks` — The zip guard judges only the parts it reads, and exporter quirks are decided |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t15-zip-guard-and-exporter-quirks.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t15-zip-guard-and-exporter-quirks.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t15-zip-guard-and-exporter-quirks` |
| Session status | PARTIAL: the session's work is done; ac4, the operator's re-parse counts, is NOT RUN |

## Summary

The three refusals `v1-e31-t09` left are decided and implemented, and the parser is
`2026.10.18-docx-4`.

* **The compression ratio is judged on the parts the reader opens.** It is judged before each part
  is inflated. The total uncompressed limit and the entry limit still count every entry, unchanged.
* **The CardMirror decision** (PM with Charlie, 2026-10-18) went into the spec in the first commit,
  before any code. Each raw character XML 1.0 forbids in a part the parser reads becomes U+FFFD, one
  for one. The count goes in the document's `warnings`, and a character reference is still refused.
* **A `.cmir` is `UNSUPPORTED` under its own format, `CMIR`.** It is identified from one inflated
  byte, and the pipeline files it under `CMIR`, not under the `DOCX` its name gave.

A read-only re-read of the dev store's 7 `FAILED` sources with the new parser gives 0 failures:

* the 5 CardMirror files parse, with 4, 4, 4, 27 and 27 characters replaced, all 66 in evidence
  text;
* the openev file parses, 32 cards;
* the gzip file is `UNSUPPORTED` / `CMIR`.

The six-file PR-subset evaluation is identical before and after, apart from the version string.

**The Goal stays `InProgress`.** ac4 needs the operator's re-parse after this branch merges, with
`v1-e31-t19`'s, so it is NOT RUN. Merge with `scripts/task pr v1-e31-t15-zip-guard-and-exporter-quirks --partial`.

**Read first:**

* **[Deviation 1](#deviations-from-the-spec):** ac3 needed four lines in
  `debate_core/application`, which is not in the spec's `constraints.packages`.
* **[PM questions](#pm-questions):** a proposed one-sentence amendment to the data-use policy's
  "byte-for-byte" cite rule, and one to the parse report's "which the parser never does".

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `zip-guard`: Refusals decided | Done | Red first (`e264b03`: 44 failed against a skeleton that only adds names), then implemented (`f294b36`). 18 of 18 mutants caught. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: a synthetic zip with an over-ratio part the reader never opens parses, and one whose over-ratio part is read is still refused, each shown failing first; the total limit unchanged, by test | **PASS** | `TestTheRatioIsJudgedOnThePartsTheReaderOpens` and `TestTheTotalLimitCountsEveryEntry` in [`test_zip_guard_and_exporter_quirks.py`](../../packages/debate_core/tests/integrations/docx_parser/test_zip_guard_and_exporter_quirks.py). Red at `e264b03` (output in [Red first](#red-first)): the thumbnail, the media part and the unreferenced `word/document.xml` were refused `COMPRESSION_RATIO_EXCEEDED`, and the 144 MiB package of unread parts was refused for its ratio instead of `TOO_LARGE`. The over-ratio read parts were already refused, before and after. The default limits are pinned by `test_the_default_limits_are_unchanged`. |
| **ac2**: the CardMirror decision recorded in the spec by the PM before the code changes, and implemented with fixtures either way | **PASS** | The decision is in the spec's `description`, marked "Decision, PM with Charlie, 2026-10-18", in `21d88be`, the branch's first commit and before any code. The fixtures are synthetic CardMirror-shaped packages holding the shapes `t09` found: four raw U+0001 (70 characters in, 70 out), and one U+0002 with 26 U+FFFE (66 in, 66 out). Each was refused `MALFORMED_XML` at `e264b03`. Now each parses, with U+FFFD at every position (expected texts written by hand), the count right (4, 27), and the underline span at the same offsets. A DOCTYPE, an entity, an external entity and a UTF-16 DOCTYPE, each beside a forbidden character, are still `FORBIDDEN_XML_CONSTRUCT`. `&#1;`, `&#x1;`, `&#x0002;`, `&#0;`, `&#xFFFE;`, `&#xffff;` and `&#31;` are still `MALFORMED_XML`. |
| **ac3**: a `.cmir` source is counted as unsupported with its own format, by test | **PASS** | `TestCardMirrorNativeFiles` (parser: `UNSUPPORTED_FORMAT`, `source_format` `CMIR`), and `test_a_cardmirror_native_file_counts_as_unsupported_under_its_own_format` in `test_caselist_parse.py` (pipeline: `report.unsupported == {"CMIR": 1, "DOC": 1, "PDF": 1}`, `report.failed == {}`, the `failures.jsonl` row `UNSUPPORTED` / `CMIR`). Red at `e264b03`: `NOT_A_ZIP`, and `{'DOC': 1, 'PDF': 1}`. |
| **ac4**: operator-run, the next parse's refusal counts recorded in `docs/data/caselist-parse-report.md` | **NOT RUN** | Needs the merged branch and the operator's re-parse, to run with `v1-e31-t19`'s after `v1-e31-t20`'s rebuild so the corpus is parsed once. See [Operator follow-ups](#operator-follow-ups), which give the expected counts from the read-only re-read. |
| Node `zip-guard`: `uv run pytest packages/debate_core/tests/integrations` | **PASS** | At `00d8f0d`: `1920 passed, 2 xfailed in 8.11s`. |

## Red first

The tests and a do-nothing skeleton were committed together in `e264b03`. The skeleton adds only
names: `SourceFormat.CMIR`, an unused `ParseFailure.source_format`, an unused
`DocxPackage.forbidden_characters_replaced`. Every new test then fails for its own reason, not for a
missing name:

```text
$ uv run pytest -n 0 -p no:randomly <the new file> test_package.py <the pipeline .cmir test> --tb=line
35 x  AssertionError: ParseFailure(... reason=<ParseFailureReason.MALFORMED_XML ...>, detail='word/document.xml is not well-formed XML', parser_version='2026.10.12-docx-3', source_format=None)
 1 x  DocxPackageError: MALFORMED_XML ... lxml.etree.XMLSyntaxError: PCDATA invalid Char value 1   (the styles-part count)
 3 x  DocxPackageError: COMPRESSION_RATIO_EXCEEDED: one entry expands 1028-fold (974-fold), above the limit of 200   (thumbnail, media part, unreferenced word/document.xml)
 1 x  assert <COMPRESSION_RATIO_EXCEEDED> is <TOO_LARGE>   (144 MiB of unread parts)
 1 x  assert <MALFORMED_XML> is <FORBIDDEN_XML_CONSTRUCT>   (UTF-16 DOCTYPE beside U+0002)
 1 x  assert <NOT_A_ZIP> is <UNSUPPORTED_FORMAT>   (.cmir)
 1 x  assert None is <SourceFormat.CMIR>   (only the head inflated)
 1 x  assert {'DOC': 1, 'PDF': 1} == {'CMIR': 1, 'DOC': 1, 'PDF': 1}   (pipeline)
44 failed, 62 passed
```

The other new tests pass at `e264b03` and still pass. They pin behaviour that must not move:

* every read part over the ratio is refused;
* a part is refused for its ratio before it is inflated;
* the default limits are unchanged;
* character references and UTF-8 declarations are refused;
* a plain gzip stream is `NOT_A_ZIP`;
* tab, line feed and carriage return are not counted.

Mutants 2, 3, 5 and 10 to 11 below show that they bite.

## Mutation table

Driver: each mutant is one textual replacement in the committed source. It runs
`uv run pytest -n 4 -p no:randomly --tb=no -rf` over the new test file, `test_package.py`,
`test_first_corpus_parse_findings.py` and the pipeline `.cmir` test. **Every run had a fresh, empty
`HYPOTHESIS_STORAGE_DIRECTORY`** (a new temporary directory per mutant). The file is restored after
each run and its sha256 checked against the original. `git status` was clean afterwards. No mutant
errored at collection.

| # | Mutant | Result | Caught by (first of them) |
|---|---|---|---|
| 1 | **The ratio judged on every entry, read or not** (the old guard) | Caught, 4 | `test_an_over_ratio_thumbnail_the_reader_never_opens_does_not_refuse_the_file`, the media part, the unreferenced `document.xml`, the 144 MiB total |
| 2 | The ratio not judged on the parts the reader opens | Caught, 7 | `test_an_over_ratio_document_part_is_still_refused`, each other read part |
| 3 | The ratio judged after the part is inflated | Caught, 1 | `test_a_part_is_judged_before_any_of_it_is_inflated` |
| 4 | The total skips parts the reader never opens | Caught, 3 | `test_parts_the_reader_never_opens_still_count_toward_the_total` |
| 5 | **A forbidden character reference let through** (rewritten to `&#xFFFD;` before parsing) | Caught, 8 | `test_a_forbidden_character_written_as_a_character_reference[&#1;]` and six more, and the one beside a raw character |
| 6 | A forbidden character deleted, not replaced | Caught, 35 | Every replacement test |
| 7 | Only the three characters `t09` saw are replaced | Caught, 28 | `test_each_is_replaced_by_one_replacement_character[U+0003]` and the other 27 |
| 8 | Tab replaced too | Caught, 1 | `test_tab_line_feed_and_carriage_return_are_not_counted[tab]` |
| 9 | A UTF-16 part rewritten as if UTF-8 | Caught, 30 | `test_a_utf16_part_is_read_in_its_own_encoding`, `t09`'s UTF-16 declaration tests |
| 10 | A part in another encoding rewritten as UTF-8 | Caught, 1 | `test_a_part_in_an_encoding_with_no_replacement_character_is_judged_as_it_is` |
| 11 | The parsed document type no longer refused | Caught, 28 | `test_a_utf16_document_type_with_a_forbidden_character_beside_it`, `t09`'s |
| 12 | The styles part's count dropped | Caught, 1 | `test_a_forbidden_character_in_the_styles_part_is_counted_with_the_documents` |
| 13 | The count not recorded in `warnings` | Caught, 34 | Every test that checks the warning |
| 14 | A `.cmir` inflated in full to identify it | Caught, 2 | `test_only_the_head_of_the_stream_is_inflated` |
| 15 | Any gzip stream taken for a `.cmir` | Caught, 3 | `test_a_gzip_stream_that_is_not_a_cardmirror_document_is_still_not_a_zip[plain-text]` |
| 16 | The parser drops the identified format | Caught, 3 | `test_a_cmir_named_docx_is_unsupported_with_its_own_format`, the pipeline test |
| 17 | The pipeline files a `.cmir` under its manifest's format | Caught, 1 | `test_a_cardmirror_native_file_counts_as_unsupported_under_its_own_format` |
| 18 | A `.cmir` counted as failed (`NOT_A_ZIP`) | Caught, 2 | The parser and pipeline `.cmir` tests |

Each run took 1.8 to 3.2 s. One mutant was considered and not run, because it is equivalent:
replacing the characters *before* the `<!DOCTYPE`/`<!ENTITY` byte scan rather than after. The
rewrite only ever writes U+FFFD in place of a character neither pattern contains, so it can neither
make nor break a match.

## Measurements

**Parser evaluation, PR subset.** I ran `uv run python scripts/run_parser_eval.py --tier pr-subset`
once before any change (`2026.10.12-docx-3`) and once after (`2026.10.18-docx-4`). Both runs: 6
files, 410 of 410 paragraphs labelled, gate FAILED because no baseline is established (expected on
this Mac). The two JSON reports are **identical apart from `parser_version`**, compared
field-for-field. No file in the subset holds a forbidden character, an over-ratio part or a gzip
stream. No `--write-baseline`; no label or baseline file touched.

**Read-only over the dev data directory.** I read the `2026.10.12-docx-3` store's `failures.jsonl`
for all four caselists and re-read every `FAILED` source's blob with this branch's parser, in
process. Under a 100 s `alarm`, it took 1.1 s. It printed reasons and counts only, and wrote
nothing.

| Caselist | `FAILED` under docx-3 | With docx-4 |
|---|---|---|
| hsld26 | `MALFORMED_XML` 5 | All 5 `PARSED`, 63 cards; 4, 4, 4, 27 and 27 characters replaced |
| hsld26 | `NOT_A_ZIP` 1 | `UNSUPPORTED`, `CMIR` |
| openev | `COMPRESSION_RATIO_EXCEEDED` 1 | `PARSED`, 32 cards, nothing replaced |
| hspf26, hspolicy26 | none | none |

All 66 replaced characters land in `evidence_text`: none in a tag, a cite or an undertag. The gzip
file was identified from its first inflated byte (`{`), read from its first 4 KiB. A source that
parsed before still parses the same way:

* a part that parsed held no raw forbidden character, so its bytes are not rewritten;
* a part's ratio was within the limit, or it would not have parsed;
* a gzip stream cannot be a zip.

The PR-subset result is consistent with that.

**The agent's build reads what this one writes.** I extracted `v1.1.0-dev.18` with `git archive`
(parser `2026.10.12-docx-3`, store schema 2) into the scratchpad. This branch parsed the fictional
parse-pipeline world into a scratch data directory, with one source given a file holding a raw
U+0001 and U+FFFE and the NOT_A_ZIP source given a `.cmir`. The old build then ran over that
directory:

* It read the new `document` record with `DocumentRecord.to_parsed_document`: the warning
  `2 character(s) XML 1.0 forbids were each replaced by U+FFFD; no other character moved` and both
  U+FFFD came back.
* It refuses the `CMIR` `source` entry if handed it directly (`enum`), as expected: its
  `SourceFormat` has no such value.
* Its own `caselist parse` plan, run, failure listing and second plan, over the directory holding
  both versions, all completed. It wrote `2026.10.12-docx-3`, parsed 4, counted `NOT_A_ZIP` 1, then
  planned 0. Every reader of stored entries in that build (`read_entries`, `read_index`,
  `read_failures`) takes a directory of its own parser version only, so it never meets a `CMIR`
  entry.

**Default suite, in eighths** (load 6 to 14). `uv run pytest --part K/8 -q -p no:randomly`, one
part at a time, under a 115 s `alarm`:

| Part | Result |
|---|---|
| 1/8 | 1049 passed in 66.85s |
| 2/8 | 1053 passed in 35.03s |
| 3/8 | 1052 passed in 34.19s |
| 4/8 | 1045 passed in 40.73s |
| 5/8 | 1040 passed in 34.83s, after the `SourceFormat` token pin was updated (it failed once on it first) |
| 6/8 | 1049 passed, 1 xfailed in 40.89s |
| 7/8 | 1050 passed, 1 failed in 37.23s |
| 8/8 | 1047 passed, 1 xfailed in 31.74s |

8,385 passed, 2 xfailed, 1 failed. The failure is
`tests/evals/parser/test_parser_eval.py::test_the_labeled_pr_subset_holds_the_baseline`, known on
this Mac until the baseline is written; not investigated.

Ruff format and check, pyright on every changed file (0 errors), `lint-imports` (12 kept),
`scripts/check_links.py`, `scripts/check_command_blocks.py` and `scripts/validate_specs.py` all pass.

## Files changed

* **`plan_specs/.../t15-zip-guard-and-exporter-quirks.yaml`**: the PM's decision, quoted and marked,
  in `spec.description`. Nothing else in the spec.
* **`debate_core/integrations/docx_parser/package.py`**:
  * the ratio moves from the directory pass to `_judge_compression_ratio`, which `_read_part` calls
    before it opens a part;
  * `_replace_forbidden_characters` and `_part_encoding` run between the declaration scan and the
    parser, and `DocxPackage.forbidden_characters_replaced` carries the count;
  * `.cmir` identification sits in `_refuse_non_zip_formats`;
  * `DocxPackageError.source_format` is new;
  * the module docstring has a section quoting the decision.
* **`debate_core/integrations/docx_parser/parser.py`**:
  * `DOCX_PARSER_VERSION = "2026.10.18-docx-4"`, with its history line;
  * the replacement warning;
  * `ParseFailure.source_format` passed through.
* **`debate_core/integrations/docx_parser/__init__.py`**: the overview names the one exception to
  copying text exactly.
* **`debate_core/domain`**:
  * `SourceFormat.CMIR`;
  * `ParseFailure.source_format`: optional, in memory only, never stored;
  * a paragraph in `ParsedCard`'s docstring.
* **`debate_core/application/caselist_parse.py`**, **`application/ports/parsed_store.py`**: the
  entry takes the format the parser found; a docstring and a field description. See Deviation 1.
* **Tests:**
  * the new [`test_zip_guard_and_exporter_quirks.py`](../../packages/debate_core/tests/integrations/docx_parser/test_zip_guard_and_exporter_quirks.py), 79 tests;
  * one pipeline test in `test_caselist_parse.py`;
  * three existing tests changed, each in Deviation 2.
* **`tests/fixtures/debate_files/structural/*.expected.json`**: the `parser_version` line of each
  of the ten, edited by hand. Nothing else in them moved.
* **`docs/data/parsed-card-store.md`**:
  * the `2026.10.18-docx-4` row;
  * `CMIR` under `source_format` and `UNSUPPORTED`;
  * the ratio and total-limit rows split;
  * a subsection on U+FFFD and how a reader finds the count.

## Deviations from the spec

1. **Two files outside `constraints.packages`.** ac3 asks for a `.cmir` to be counted "with its own
   format". The run report counts unsupported sources by the stored entry's `source_format`, which
   the pipeline takes from the manifest, and the manifest says `DOCX` for the one file the corpus
   holds, because it is named `.docx`. So the parser reports the format it found
   (`ParseFailure.source_format`), and the pipeline's `_record` files the entry under it: four lines
   in `debate_core/application/caselist_parse.py`. `application/ports/parsed_store.py` changes only a
   field's description. Without them the `.cmir` would count as unsupported under `DOCX`. The spec
   needs `debate_core.application` in its packages, or the PM can ask me to take the pipeline lines
   out. [PM question 3](#pm-questions).
2. **Three existing tests changed, each because the task changed what they pinned.**
   * `test_package.py`: `test_an_entry_that_expands_a_thousandfold_is_refused` put its filler in
     `word/media/image1.bin`, which the reader never opens. That is exactly what ac1 now reads. Its
     filler moved into the document part, and it is renamed
     `test_a_part_the_reader_opens_that_expands_a_thousandfold_is_refused`.
   * `test_cite_detection.py`: `v1-e31-t12`'s `test_it_is_the_version_this_task_bumped_to` pinned
     `2026.10.12-docx-3` exactly. It now asserts that version *or a later one*, and the exact pin for
     `2026.10.18-docx-4` is in this task's file.
   * `domain/caselist/test_values.py`: the `SourceFormat` token set gains `CMIR`.

## Decisions and assumptions

* **Where the count went: the document's `warnings`, not a new field.** `warnings` is where the
  parse result already carries per-source facts: the tracked-deletions count already goes there, as
  `N tracked deletion(s) were dropped; ...`. The new line is
  `N character(s) XML 1.0 forbids were each replaced by U+FFFD; no other character moved`, and a
  source with none has no such line. A new `ParsedDocument` field was the alternative. The domain
  base class is `extra="forbid"`, so the agent's build would refuse every stored document that
  carried one. Shown above: that build reads the new warning.
* **The `CMIR` value in a stored entry.** It is a new value, not a new field, and it is written only
  into `2026.10.18-docx-4` directories, which the agent's build never reads. Shown above.
* **A file *named* `.cmir` is still `OTHER`.** Mapping the extension in `path_parser` would put
  `CMIR` into the manifests, which the agent's build does read and would refuse. The corpus holds no
  such file: none of the `OTHER` sources' names ends `.cmir`. Follow-up work.
* **"Decided from the part names and relationships before anything is inflated"**, made concrete:
  * Every part the reader opens goes through `_read_part`, which judges its ratio from the directory
    before `archive.open`.
  * `[Content_Types].xml` and `_rels/.rels` are opened by fixed name, the main document part by the
    relationship that names it, and the styles part by its place beside the document.
  * Each is judged before any of it is inflated. A test with broken compressed bytes proves it: it is
    refused for the ratio, not as a malformed package.
  * The relationships part is the one that must be inflated (once judged) to learn the document's
    name.
* **Encodings.** UTF-8 parts are rewritten byte for byte. Each forbidden character is a whole
  match there: a C0 control byte never occurs inside another character, and `EF BF BE` / `EF BF BF`
  start where a character starts.

  UTF-16 parts are decoded, rewritten and re-encoded in the same byte order; a part that does not
  decode is left alone. Any other declared encoding, UTF-32 and anything else with a zero byte in
  its first four are handed to the parser unchanged, and it refuses them as before. ISO-8859-1, for
  instance, cannot write U+FFFD.

  Office Open XML allows only UTF-8 and UTF-16, and `t09` found every document part in the corpus
  UTF-8.
* **`[Content_Types].xml` is read but never parsed** (only searched for the macro content type), so
  it is neither rewritten nor counted. `_rels/.rels`, the document part and the styles part are, and
  the count is their sum: a test puts one in a style name.
* **`.cmir` identification**: gzip magic, then one inflated byte from at most the first 4 KiB, which
  must be `{`. A gzip stream that is not a JSON object is still `NOT_A_ZIP`, so nothing is called a
  `.cmir` on the magic alone.
* **The ratio refusal's detail now names the part** (`docProps/thumbnail.emf expands 278-fold`).
  Part names are within what `detail` may hold. It used to say "one entry".
* **Fixtures are built in memory** from `debate_core.testing.docx_builder`, the convention for
  package tests, rather than committed `.docx` binaries. Every expected text is a literal written
  from the fixture's markup.

## PM questions

Paste-ready for the PM:

```text
PM questions from v1-e31-t15 (zip guard and exporter quirks), 2026-10-18. Four, each with a recommendation.

1. Data-use policy, Attribution rule 1 (docs/policies/caselist-data-use.md): "The original cite is kept verbatim. It is copied from the source document's own runs, byte-for-byte ...". From parser 2026.10.18-docx-4 a raw character XML 1.0 forbids becomes U+FFFD, in a cite as anywhere else. Today none of the 66 replaced characters is in a cite (all are in evidence text), but the rule would be untrue for one that is.
   Proposed sentence, appended to rule 1: "The one exception is a character XML 1.0 forbids, which the parser replaces one for one with U+FFFD (Decision, PM with Charlie, 2026-10-18, v1-e31-t15)."
   (a) Amend as proposed. RECOMMENDED: the policy then says what the store holds.
   (b) Leave the policy and accept the gap until a cite holds one.
   (c) Other wording.
   I have not edited the policy.

2. Parse report (docs/data/caselist-parse-report.md, the paragraph on the 5 malformed files): "Taking them out would be editing evidence text, which the parser never does." It records 2026-10-10.
   Proposed sentence after it: "From 2026.10.18-docx-4 the parser replaces each such character with U+FFFD, one for one, by decision (v1-e31-t15); nothing is taken out."
   (a) Add it. RECOMMENDED: the history stays and the reader learns what changed.
   (b) Leave it; ac4's section will report the new counts.

3. Spec scope: ac3's "counted ... with its own format" needed four lines in debate_core/application/caselist_parse.py (_record files the entry under the format the parser found) and a field description in application/ports/parsed_store.py. debate_core.application is not in constraints.packages.
   (a) Add debate_core.application to the spec's packages. RECOMMENDED: without it the .cmir counts as unsupported under DOCX.
   (b) Have me take the pipeline lines out.

4. A file named .cmir is still OTHER from the importer. Mapping the extension to CMIR would write CMIR into manifests, which the agent's build (v1.1.0-dev.18) reads and would refuse. The corpus holds no .cmir-named file.
   (a) A follow-up task once the agent runs a build that knows CMIR. RECOMMENDED.
   (b) Drop it.
```

## Operator follow-ups

**ac4: the refusal counts after the next parse.** These are not a second parse. Run them after
`v1-e31-t19`'s re-parse, which follows `v1-e31-t20`'s rebuild, so the corpus is parsed once, with
this branch, `t19` and `t20` all merged. The parse itself is the runbook's
[After a release that bumps the parser version](../runbooks/caselist-scheduled-sync.md#after-a-release-that-bumps-the-parser-version),
about 30 minutes. The counts below are read-only and take seconds.

Where: your Mac, any shell, after the parse. Set `V` to the parser version the parse wrote: its dry
run names it. It is `2026.10.18-docx-4` unless `t19` bumps the version again, and then it is
`t19`'s.

```bash
V=2026.10.18-docx-4
for c in hsld26 hspf26 hspolicy26 openev; do echo "$c"; jq -r '"\(.outcome) \(.reason) \(.source_format)"' "$HOME/.debate-research/dev/parsed/$c/${V}/failures.jsonl" | sort | uniq -c; done
find "$HOME/.debate-research/dev/parsed" -path "*/${V}/sha256/*" -name '*.jsonl' -print0 | xargs -0 jq -r 'select(.record == "document") | .document.warnings[]? | select(test("U\\+FFFD"))' | awk '{n += $1; f += 1} END {print f+0, "sources,", n+0, "characters replaced"}'
```

Success looks like this, for the sources the `2026.10.12-docx-3` store holds today:

* **hsld26**: no `FAILED` line at all, and
  `UNSUPPORTED UNSUPPORTED_FORMAT CMIR` 1, `... OTHER` 43, `... PDF` 66.
* **hspf26**: `OTHER` 17, `PDF` 1387.
* **hspolicy26**: `OTHER` 12, `PDF` 19.
* **openev**: `OTHER` 2, and no `FAILED` line.
* **The last line**: `5 sources, 66 characters replaced`.

Sources a weekly pull imported after 2026-10-18 can add to any count. A `FAILED` line is then a new
file: report its reason. Both commands were checked against a scratch store this branch wrote, and
printed the expected `CMIR` line and `1 sources, 2 characters replaced`.

Paste the output back. Whoever closes ac4 records the counts in `docs/data/caselist-parse-report.md`
and sets the Goal to `Succeeded` in a small spec PR, as `v1-e31-t09` did.

## Follow-up work

* **Map a `.cmir` extension to `CMIR` in the importer** (E30, after the agent runs a build that
  knows `CMIR`). [PM question 4](#pm-questions).
* **Tell CardMirror's maintainer the exporter writes characters XML forbids** (E31; outward-facing,
  the PM's call). Five files so far, and more each week while the exporter does it. A fix upstream
  makes the replacement rare instead of routine.
* **`ParsedCard` field descriptions** still say `tag` and `full_cite` are "exactly as written" and
  `evidence_text` "copied exactly". The class docstring now names the one exception. I left the
  field descriptions alone, because they are what a JSON schema of the model shows, and that is the
  PM's wording to choose.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-18

**Notes:**

Accepted, on condition that the session applies the four changes below before the PR. The Goal
stays `InProgress` for ac4, so the merge uses `--partial`.

**Apply before the PR:**

1. **The spec's `constraints.packages`** gains `debate_core.application` (PM question 3, (a)) and
   `docs/policies` (for item 2). Mark it "PM amendment 2026-10-18".
2. **PM question 1, (a): the policy sentence**, appended to Attribution rule 1 exactly as proposed.
   The policy then says what the store holds.
3. **PM question 2, (a): the parse-report sentence**, added as proposed. The history stays and the
   reader learns what changed.
4. **The `ParsedCard` field descriptions** (Follow-up 3). Make `tag`, `full_cite` and
   `evidence_text` name the same one exception the class docstring now names, briefly, e.g. "...
   exactly as written, except that a character XML 1.0 forbids is replaced by U+FFFD". A field
   description that is untrue is worse than a long one.

**The work itself:**

* **The decision is in the spec before any code** (`21d88be`), as ac2 asks.
* **Red against a skeleton that adds only names**, so every failure is a behaviour failure. The
  tests that pass at red pin what must not move, and mutants show they bite.
* **The ratio guard.** I read `_judge_compression_ratio` and `_read_part`. The ratio is judged from
  the directory before a byte is inflated, the read is still bounded at the part limit plus one,
  and the total and entry limits still count every entry. A part that lies about its size is
  caught. The guard is narrower in what it judges and no weaker in what it allows.
* **Forbidden characters.** Every XML protection is unchanged, which the DOCTYPE and entity tests
  prove beside a forbidden character. Character references are still refused. The rewrite is
  encoding-aware and leaves an encoding it cannot handle to the parser.
* **The count went in `warnings`, not a new field,** so the agent's build reads the stored document.
  That is shown by running `v1.1.0-dev.18` over a store this branch wrote.
* **The dev store's 7 failures re-read read-only** become 6 parsed and 1 `CMIR`, with all 66
  replaced characters in evidence text. The PR-subset evaluation is identical but for the version.
* **18 of 18 mutants caught.** The one not run is argued equivalent, correctly.

**Rulings:**

* **Deviation 1, the pipeline lines:** accepted. They are what ac3 means, and the spec is amended
  to match (item 1 above).
* **Deviation 2, the three tests:** accepted. Each pinned exactly what this task changed.
* **Decisions:** all accepted. The two choices that keep the agent's build reading the store (the
  count in `warnings`, and `CMIR` written only into docx-4 directories) are the right ones.
* **PM question 4: (a).** It is filed as an E30 follow-up, after the agent runs a build that knows
  `CMIR`.

**Follow-ups:**

* **Telling CardMirror's maintainer** is outward-facing. It goes to the operator, not a task.
* **ac4** is run with `v1-e31-t19`'s re-parse, after `v1-e31-t20`'s rebuild, by the operator, and
  recorded in a close-out.
* **`v1-e31-t19` also bumps `DOCX_PARSER_VERSION`.** Whichever merges second rebases and takes a
  later version string, with its own history line.

### ac4: the operator's re-parse, 2026-10-19 (recorded by the PM)

The combined re-parse to `2026.10.18-docx-5` (`v1-e31-t20`'s after-merge list) parsed every source
again. No source failed; every source not parsed is counted as an unsupported format, the one `.cmir`
file under `CMIR`; forbidden characters were replaced in 5 sources, 66 characters. The counts are in
[the parse report](../data/caselist-parse-report.md#the-re-parse-to-docx-5-and-the-re-cluster-on-the-store-operator-run-2026-10-19).
ac4 passes, and the PM sets the Goal `Succeeded` in the close-out of 2026-10-20.
