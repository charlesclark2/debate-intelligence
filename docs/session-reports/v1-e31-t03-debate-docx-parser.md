# Session report: v1-e31-t03-debate-docx-parser

| | |
|---|---|
| Task | `v1-e31-t03-debate-docx-parser` — Debate .docx parser |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t03-debate-docx-parser.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t03-debate-docx-parser.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t03-debate-docx-parser` |
| Session status | COMPLETE |

## Summary

The deterministic `.docx` adapter is in, behind a new `DebateFileParser` port. A file goes through
three modules: `package.py` bounds and opens the zip and the XML, `runs.py` turns paragraphs into
text and character-offset formatting spans in one walk, and `parser.py` classifies the paragraphs
through the shipped t02 style profile and classifier and groups them into cards with `FILE_IMPORT`
provenance. Nothing in the parser re-derives a heuristic t02 already owns; the three decisions
added here are the ones the classifier cannot make because each needs to see what comes after a
paragraph or where it sits — a tag with no card under it is an analytic, a first-and-last-words
card is `ABBREVIATED`, and a table cell or text box is `OTHER` whatever style it carries.

Two things the PM should look at first. **The fixtures earned their keep.** Writing the expected
answers by hand before running the parser caught two real bugs that every test I had written
myself passed: a second tag under a block came out as a *child* of the first tag rather than its
sibling, and a tag demoted to an analytic stopped occupying tag level in the hierarchy. **And the
spec's `python-docx + lxml` is one library too many** — python-docx parses with
`remove_blank_text=True`, which can silently drop a whitespace-only run in exactly the converted
files this parser exists for, and ac3 says evidence text is copied exactly. Deviation 1 below.

Underline is counted once. CardMirror writes both encodings on body runs and 63% of the surveyed
corpus has been through it, so a reader that counted them separately would double the underlining
of most of the corpus; `cardmirror-caselist-upload.docx` is the fixture that holds it down, and
the family is treated as the common case rather than an edge throughout.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `parse-model-and-port` | DONE | `domain/debate_files.py` and `application/ports/debate_files.py`, plus `FakeDebateFileParser` in `debate_core.testing`. |
| `safe-loading` | DONE | `integrations/docx_parser/package.py`. Limits checked from the zip directory *and* against the bytes actually read. |
| `run-formatting` | DONE | `integrations/docx_parser/runs.py`. Text and offsets built in one walk so they cannot disagree. |
| `section-and-card-assembly` | DONE | `integrations/docx_parser/parser.py`. Two bugs found and fixed at the fixture node; see Summary. |
| `structural-fixtures` | DONE | Ten synthetic fixtures + `MANIFEST.md`, generator script, and the `slow` timing test. The node's "scrub 8-10 files" wording is superseded — Deviation 2. |

## Acceptance criteria

All commands run from the task worktree. Test counts are from the named file only; the whole
repository suite is `1536 passed in 23.76s`.

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — units resolved only through the t02 profile; every section has a section path and records its match source | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_parser.py` → `35 passed`. `TestUnitsAndSectionPaths` covers all seven units, the rule id and match source on each, paths, and heading closure. Fixture suite re-checks the same on ten files: `test_structural_fixtures.py` → `81 passed`. |
| ac2 — tag+cite+evidence grouped; short cite split; tag with no card is ANALYTIC; ABBREVIATED / CITE_ONLY not padded or dropped | PASS | Same run: `TestCardAssembly`, `TestCompleteness`. `wiki-converted-cite-entries.docx` carries one `ABBREVIATED` and one `CITE_ONLY` card with hand-written expected values. |
| ac3 — fidelity test re-reads the XML; text equals concatenated `w:t`; underline, emphasis, bold, highlight and font-size spans land on the right offsets | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_runs.py` → `38 passed`. `test_paragraph_text_equals_the_concatenated_w_t_text_of_its_runs` walks the tree a second time with a function that knows nothing about the reader; `test_every_span_selects_exactly_the_characters_of_the_run_that_produced_it` slices the text with each span. |
| ac4 — every card carries FILE_IMPORT provenance (caselist, snapshot, sha256, path, element range, parser and profile versions) and no verified status | PASS | `test_parser.py::TestProvenance` (7 tests) plus `test_debate_files.py` → `33 passed`, where the model itself refuses any other provenance mode or verification status. |
| ac5 — insertions kept, deletions dropped, comments/docProps never read, tables/text boxes OTHER, malformed/oversized/macro/.doc/.pdf yield a typed ParseFailure | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_package.py` → `28 passed` (every refusal by reason, and `parts_read` asserted exactly). `test_runs.py::TestTrackedChanges`, `test_parser.py::TestTablesAndTextBoxes`, `TestRefusals`. `tracked-changes-and-comments.docx` puts the string `NEVER READ` in `docProps/core.xml` and `word/comments.xml`; a fixture test asserts it reaches no output. |
| ac6 — 8–10 synthetic structural fixtures with snapshot expectations; a 300-page (~5 MB) file parses in under 20 s in a `slow` test; no real file committed | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_structural_fixtures.py` → `81 passed` (10 fixtures × 8 checks + 1 coverage test). Slow tier: `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_structural_fixtures.py -m slow` → `1 passed in 7.44s`; the measured parse itself is **0.98 s for a 2.9 MB document** and the committed test uses 5250 cards / 5.25 MB of `word/document.xml`, against a 20 s budget. No real or scrubbed file is committed. |

### Node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `parse-model-and-port` — ParsedCard model exists (`contentMatch: class ParsedCard`) | PASS | `grep -c "class ParsedCard" packages/debate_core/src/debate_core/domain/debate_files.py` → `1` |
| `parse-model-and-port` — parse model invariants and JSON round-trip tests pass | PASS | `uv run pytest packages/debate_core/tests/domain/test_debate_files.py` → `33 passed in 3.24s` |
| `safe-loading` — loader safety tests pass (zip bomb, entity expansion, macro, wrong format) | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_package.py` → `28 passed in 3.29s` |
| `run-formatting` — run formatting and fidelity tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_runs.py` → `38 passed in 3.48s` |
| `section-and-card-assembly` — assembly and provenance tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_parser.py` → `35 passed in 3.43s` |
| `structural-fixtures` — fixture manifest exists (`contentMatch: wiki-converted`) | PASS | `grep -c "wiki-converted" tests/fixtures/debate_files/structural/MANIFEST.md` → `2` |
| `structural-fixtures` — structural fixture tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/docx_parser/test_structural_fixtures.py` → `81 passed in 3.49s` |
| `structural-fixtures` — type check passes for debate_core | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` |
| `structural-fixtures` — import boundaries hold | PASS | `uv run lint-imports` → `Contracts: 2 kept, 0 broken.` |
| `structural-fixtures` — **custom: coach reviews scrubbed structural fixtures** | NOT APPLICABLE | There are no scrubbed fixtures to review: every fixture is synthetic and contains no real evidence, cite, school or team code, so there is nothing to confirm the absence of. See Deviation 2 and the optional check under Operator follow-ups. |

Also run, though not a criterion of this task:

| Check | Result |
|---|---|
| Whole repository test suite | `uv run pytest` → `1536 passed in 23.76s` |
| Lint and format | `uv run ruff check .` → `All checks passed!` |
| Pre-commit on every changed file | all hooks `Passed` (terraform and site hooks skipped, no files) |
| Spec validation | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases` |
| Published JSON schemas still current | `uv run scripts/export_schemas.py --check` → `OK: 7 schemas … are up to date` |

## Files changed

**Domain and port (`packages/debate_core/src/debate_core/`)**
* `domain/debate_files.py` — new. `ParsedDocument`, `FileSection`, `ParsedCard`, `FormattingSpan`,
  `FontSizeSpan`, `CardCompleteness`, `FileImportProvenance`, `ParseFailure`, `ParseFailureReason`.
  The invariants live here: a span may not run past the text it indexes, a card may not claim to be
  verified, a `CITE_ONLY` card may not carry a body.
* `application/ports/debate_files.py` — new. The `DebateFileParser` Protocol.
* `application/ports/__init__.py` — re-export and one row in the port table.

**Adapter (`packages/debate_core/src/debate_core/integrations/docx_parser/`)** — new package:
`package.py` (safety and parts), `runs.py` (text and spans), `parser.py` (assembly), `__init__.py`.

**Test doubles (`packages/debate_core/src/debate_core/testing/`)**
* `fakes.py`, `__init__.py` — `FakeDebateFileParser` and `build_fake_debate_file_parser()`, the
  latter annotated as the Protocol so pyright checks conformance in this package.
* `docx_builder.py` — new. Builds WordprocessingML packages from strings. It ships with the
  library rather than sitting in a test directory because `v1-e31-t05` and `v1-e31-t06` need the
  same helpers, and because it is what keeps a unit test and a committed fixture describing a file
  the same way.

**Tests (`packages/debate_core/tests/`)** — `domain/test_debate_files.py`,
`application/test_debate_file_parser_fake.py`, and `integrations/docx_parser/` with `conftest.py`,
`test_package.py`, `test_runs.py`, `test_parser.py`, `test_structural_fixtures.py`.

**Fixtures (`tests/fixtures/debate_files/structural/`)** — ten `.docx` files, ten
`.expected.json` files and `MANIFEST.md`.

**Tooling** — `scripts/generate_structural_fixtures.py` (new); `pyproject.toml` (the `lxml-stubs`
dev dependency and a second import-linter contract); `packages/debate_core/pyproject.toml` (the
`docx` optional extra); `packages/debate_core/README.md` (three sections); `uv.lock`.

## Deviations from the spec

1. **python-docx is not used. The parser reads OOXML with lxml alone.** The spec description says
   "reads `word/document.xml` with python-docx + lxml". Two reasons not to:
   *Fidelity.* python-docx builds its parser with `remove_blank_text=True`. A `<w:t>` holding only
   spaces and carrying no `xml:space="preserve"` can be dropped by it. Word always writes the
   attribute, but the Google Docs exports and wiki-to-docx conversions this parser exists for are
   exactly the files that might not — and ac3 says a card's evidence text is the run text character
   for character. *Order.* The zip must be bounded before anything decompresses it, which no
   package opener offers; by the time python-docx would help, the work is done. lxml alone does the
   job with `resolve_entities`, `load_dtd`, `dtd_validation`, `huge_tree` and the network all off.
   The spec's constraint — no python-docx or lxml in `domain/` or `application/` — is unaffected and
   is now enforced by an import-linter contract rather than by convention. **The PM may want to
   amend the description; no behaviour depends on the answer.**

2. **The `structural-fixtures` node still says "Scrub 8-10 files with `scripts/scrub_docx_fixture.py`
   … with a MANIFEST.md (category, season, scrub date)", and its `custom` criterion asks Charlie to
   confirm no names or authorship remain in the scrubbed files.** Goal criterion ac6 on the same
   spec says the opposite — "8-10 **synthetic** structural fixtures … No real file or excerpt is
   committed" — and the PM ruling merged with `v1-e31-t02` settles it: no real files or excerpts go
   in the repository, scrubbed or not. I followed ac6 and the ruling. The node's wording and its
   manual criterion are left as they are for the PM to amend; the `MANIFEST.md` columns are family
   and corpus rather than season and scrub date, because there is nothing to date.

3. **`ParsedCard` has an `undertag` field** that the node's model list does not name. The spec
   requires undertags to be recognised and to belong to the tag above them without starting a new
   card, so a card needs somewhere to put them; folding them into `tag` would conflate two things a
   writer has to emit differently.

4. **Two dependency changes the spec does not name.** `debate-core` gains an optional `docx` extra
   (`lxml>=5.3`), matching how `aws` carries boto3; and `lxml-stubs` joins the dev group because
   pyright runs strict over `debate_core` and lxml ships no inline types — the same reason
   `boto3-stubs` is already there. A second import-linter contract keeps `lxml` and `docx` out of
   everything but the adapter.

5. **The large synthetic file is built in memory, not committed.** ac6 asks for "a 300-page (about
   5 MB) synthetic file". It is 5250 cards, 9001 paragraphs, 5.25 MB of `word/document.xml` —
   about 300 pages — built by the `slow` test. The `.docx` itself is only 0.12 MB because synthetic
   text compresses; committing a multi-megabyte binary that changes whenever the generator does
   would be a file nobody can review.

## Decisions and assumptions

* **A card reports the weakest match that built it, not the strongest.** A card is only as
  trustworthy as its least certain step. This has a consequence worth knowing before reading a
  number: an ordinary Verbatim card reports `HEURISTIC` at 0.75, because Verbatim gives a card body
  no paragraph style and the body is found by its underlining. `rule_ids` carries the detail, and
  `v1-e31-t05` is what should sort misses by it.
* **A paragraph in a table cell or a text box is `OTHER` even when it carries `Heading4`.** t02's
  `classify_paragraph` *documents* "table cells and empty paragraphs, which are `OTHER` whatever
  else they look like" but resolves a paragraph style first, so it returns `TAG` for that
  paragraph. ac5 requires `OTHER`, so the parser overrides at assembly and keeps the original rule
  id in `assembly-table-cell`. I did not change t02. **This is a small mismatch between t02's
  docstring and its code that the PM may want to log** — see Follow-up work.
* **`element_index` is the paragraph's position in the parser's document-order walk of the body**,
  counting table and text-box paragraphs. Reproducible from the same bytes under the same parser
  version, which is what the provenance claim needs.
* **The port is synchronous and a refusal is a return value.** Parsing waits on nothing, so `async`
  would advertise a concurrency that is not there; and a bulk import of twelve thousand files needs
  a row per failure it can count, not an exception that stops the run.
* **`debate_files` models are not added to `EXPORTED_MODELS`/`schemas/`.** Those publish what the
  web client and the V2 API read. A `ParsedCard` is consumed inside the platform by t04, t06 and
  `v3-e20-t01`; if V3 exposes it, that is the task to add the schema in.
* **Limits** (`PackageLimits`): 1024 entries, 128 MiB uncompressed total, 64 MiB per part, 200×
  compression ratio checked only on entries of 4 KiB compressed or more. All an order of magnitude
  above what real debate files measure and well below what a zip bomb needs.
* **A card may start at a cite with no tag above it.** Ordinary in a wiki-converted disclosure. A
  stray evidence paragraph with neither tag nor cite is a section but not a card.

## Operator follow-ups

Nothing is blocking. Two optional items:

**1. Look at the fixtures (optional, ~5 minutes).** The node's manual criterion was written for
scrubbed real files, which do not exist. What is worth a coach's eye instead is whether the ten
synthetic files *look like debate files* — the judgement no test can make.

```bash
open tests/fixtures/debate_files/structural/*.docx
```

Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e31-t03-debate-docx-parser`.
Success looks like: each file reads as the family its row in
`tests/fixtures/debate_files/structural/MANIFEST.md` claims. Nothing in them is real, so there is
no privacy question to answer.

**2. The `slow` tier runs the timing test.** No action now; `validate-dev` picks it up.

```bash
uv run pytest packages/debate_core/tests/integrations/docx_parser/test_structural_fixtures.py -m slow
```

Expected runtime ~8 s; success looks like `1 passed`.

## Follow-up work

* **t02's classifier docstring and code disagree about table cells.** The docstring lists table
  cells as `OTHER` "whatever else they look like", but the style-resolution rule runs first, so a
  styled paragraph in a table comes back as its style's unit. This parser overrides it, so nothing
  is broken; the mismatch belongs to `v1-e31-t02`, and the PM should decide whether to fix the code
  to match the docstring or the docstring to match the code.
* **The short-cite pattern is t02's starting point, and it shows.** `[no author given], an
  unsigned briefing note` correctly yields no short cite, but the pattern has not met a real cite
  tail yet. `v1-e31-t05` is where it should be refined against the labelled set, and that task
  should expect to change `cite.short_cite_pattern` in the profile rather than the parser.
* **Text boxes are always `OTHER`.** True for the page banners and margin notes the survey saw. If
  the accuracy evaluation finds a team that puts cards in text boxes, that is a spec change, not a
  bug fix.
* **`FileSection` is emitted for every paragraph, including `OTHER`.** That is what makes element
  ranges meaningful and lets t05 count false positives, but it means a parsed 300-page file holds
  ~9,000 sections. `v1-e31-t06` should decide whether its card store persists sections at all.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-09-21

**Notes:** All three deviations upheld. The lxml decision is the right one and is now in the spec
with its reasoning; the structural-fixtures node wording was a leftover the t02 ruling should have
caught and has been corrected; the tenth node criterion is correctly NOT APPLICABLE. The
hand-written expectations are recorded as working agreement 6.
