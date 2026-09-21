# Session report: v1-e31-t02-verbatim-style-profile

| | |
|---|---|
| Task | `v1-e31-t02-verbatim-style-profile` — Verbatim/CardMirror style profile |
| Spec | [`plan_specs/v1/e31-debate-file-parsing/t02-verbatim-style-profile.yaml`](../../plan_specs/v1/e31-debate-file-parsing/t02-verbatim-style-profile.yaml) |
| Epic / release | `v1-e31-debate-file-parsing` / `v1.1` |
| Branch | `task/v1-e31-t02-verbatim-style-profile` |
| Session status | PARTIAL |

## Summary

The platform now has one description of what a debate `.docx` looks like, and every number in it
was measured rather than assumed. `scripts/survey_docx_styles.py` read 2,066 real files — the
hsld26-0915 caselist snapshot, camp files, and one team's files across three seasons — and the
aggregate is committed at [`docs/data/debate-file-style-survey.md`](../data/debate-file-style-survey.md).
The profile itself is a `StyleProfile` model in `debate_core.domain.style_profile` plus
`evidence/style_profiles/verbatim.yaml`, loaded by `debate_core.evidence.style_profile_loader`, and
a deterministic classifier in `debate_core.evidence.style_classifier` for the 14% of the corpus
that carries no Verbatim styles at all. `scripts/scrub_docx_fixture.py` is the gate every fixture
taken from a real file passes through.

**Two findings changed the design.** 63% of the corpus — and 78% of caselist files — carries
CardMirror's `pmd-heading-` bookmarks, so the editor ADR-0014 made a compatibility target is
already what most disclosed files have been through, and its dual underline encoding is the common
case rather than an edge. And `basedOn` is not trustworthy on its own: `Heading411` appears in 197
files and is a Heading 4 that inherits from `Heading1`, so resolving by inheritance would have
called those files' tags pockets. The profile resolves by id, then alias, then display name, then
Word's numeric de-duplication suffix, and only then `basedOn`.

**What the PM should look at first:** the session is PARTIAL. Goal criteria `ac1`–`ac5` all pass,
but the `fixtures-and-gates` node is short of two things — the 4-6 scrubbed excerpts of real files
and the coach review of them, both of which need a replacement list only Charlie holds, and
`uv run lint-imports`, whose tool is not installed yet. Both are in **Operator follow-ups**, and
there is a recommendation under **Follow-up work** about where the scrubbed excerpts should live.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `scrub-script` — Fixture scrub script | COMPLETE | `scripts/scrub_docx_fixture.py` plus 23 tests. Also smoke-run against a real 383-paragraph team file (see Decisions). |
| `style-survey` — Style survey of the downloaded corpus | COMPLETE | `scripts/survey_docx_styles.py` plus 21 tests; report committed, over 2,066 files. Run in-session rather than handed to the operator — see Deviations. |
| `profile-model` — StyleProfile model and verbatim.yaml | COMPLETE | Model, YAML, loader, 78 tests. |
| `heuristic-classifier` — Non-Verbatim paragraph and run classifier | COMPLETE | `style_classifier.py`, 71 tests, 100% statement and branch coverage. |
| `fixtures-and-gates` — Style fixtures, coach review and quality gates | PARTIAL | Six synthetic fixtures, their expectations and `MANIFEST.md` are in; `pyright` passes. The scrubbed excerpts, the coach review and `lint-imports` did not happen. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal `ac1` — `StyleProfile` loads from `verbatim.yaml` with a `profile_version`, defines `StructuralUnit` (POCKET…OTHER), and resolves every Verbatim style id/name and alias seen in the survey, including `basedOn`, to a unit or run emphasis | **PASS** | `uv run pytest packages/debate_core/tests/evidence/test_style_profile.py` → `78 passed`. Covers the exact enum member list, all nine canonical paragraph ids, all six character ids, the recorded aliases (`%tag`, `Analytics`, `cardtext`, `UnderlineFIXEDChar`, `StyleBoldUnderline`, `AAAUNDERLINEKEYBOARD`, `IntenseEmphasis`, `TitleChar`), display-name resolution, the de-duplication rule (`Heading411`→TAG, `Emphasis1`→EMPHASIS) and `basedOn` fallback (`HeadingFake`→BLOCK, `Rehighlighting`→EMPHASIS), plus `resolve_based_on_chain` on a missing ancestor and on a cycle. |
| Goal `ac2` — the profile records the CardMirror node/mark per ADR-0014, and a test asserts the mapping covers every unit and every CardMirror type listed in the evaluation note | **PASS** | Same run. `test_every_cardmirror_node_in_the_evaluation_note_is_accounted_for` and its mark twin parse the `### Nodes` and `### Marks` tables out of `docs/architecture/cardmirror-evaluation.md` and assert set equality in both directions (21 nodes, 20 marks); a guard test fails if the extraction ever comes back empty. `test_every_structural_unit_has_a_cardmirror_node` covers all nine units; `RunEmphasis.HEADING` is asserted to be the only emphasis with no mark, and its rule has to say so. |
| Goal `ac3` — the classifier labels headings, cite lines and evidence in the heuristic fixtures with the expected unit, rule id and match source `HEURISTIC`, deterministically and with no model calls | **PASS** | `uv run pytest packages/debate_core/tests/evidence/test_style_classifier.py` → `71 passed`. `test_every_fixture_paragraph_classifies_as_its_expectations_say` reads all six `.docx` fixtures and checks unit, rule id and match source against the committed `.expected.json`; `test_the_heuristic_fixtures_are_classified_without_a_single_verbatim_style` asserts every result in the three heuristic fixtures is `HEURISTIC` and that headings, a cite line and evidence are all present. Determinism: two tests classify 50 times and compare. No model calls: `test_style_classification_reaches_no_model` greps the module source. |
| Goal `ac4` — `scrub_docx_fixture.py` removes `docProps` author fields, comments, `people.xml`, custom XML and tracked-change authors and replaces names/team codes from a coach-supplied list; its tests prove a seeded name no longer appears anywhere in the output package | **PASS** | `uv run pytest tests/scripts/test_scrub_docx_fixture.py` → `23 passed`. `test_seeded_name_and_team_code_appear_nowhere_in_the_scrubbed_package` searches every part of the output three ways — raw bytes as text, XML tags stripped and whitespace collapsed, and the part names — and a companion test proves the input really did contain the name, so the first cannot pass vacuously. |
| Goal `ac5` — `docs/data/debate-file-style-survey.md` records aggregate style-name frequencies and the share of files per template family across the hsld26 snapshots and camp files, with no file names, schools or team codes | **PASS** | [`docs/data/debate-file-style-survey.md`](../data/debate-file-style-survey.md), 2,066 files: caselist 1,582, camp 110, team 374. Families: verbatim 23%, cardmirror 63%, wiki-converted 3%, other-heuristic 11%. Style tables give per-style file counts and reference counts; a style id is named only if it is published vocabulary or Word's de-duplication of one (see Decisions). Checked by hand for names after generation: `grep -ciE "maggie\|jordan\|tashma\|alex"` → `0`. |
| Node `scrub-script` — Scrub script tests pass | **PASS** | `uv run pytest tests/scripts/test_scrub_docx_fixture.py` → `23 passed in 1.52s`. |
| Node `style-survey` — Style survey report committed (`contentMatch: "template family"`) | **PASS** | `docs/data/debate-file-style-survey.md` exists; `grep -c "template family"` → `1`. |
| Node `profile-model` — Style profile model and alias resolution tests pass | **PASS** | `uv run pytest packages/debate_core/tests/evidence/test_style_profile.py` → `78 passed in 2.02s`. |
| Node `heuristic-classifier` — Classifier tests pass | **PASS** | `uv run pytest packages/debate_core/tests/evidence/test_style_classifier.py` → `71 passed in 2.19s`. |
| Node `fixtures-and-gates` — Style fixture manifest exists (`contentMatch: "scrubbed"`) | **PASS** | `tests/fixtures/debate_files/style_profile/MANIFEST.md` exists; `grep -c "scrubbed"` → `2`. |
| Node `fixtures-and-gates` — Coach reviews scrubbed excerpts | **NOT RUN** | No scrubbed excerpts are committed, so there is nothing to review. Scrubbing a real file needs the coach-supplied replacement list of names and team codes, which the spec keeps outside the repository and which does not exist yet; the script refuses to run without one. The `MANIFEST.md` carries the five slots, the exact command and the two-step procedure. See Operator follow-ups. |
| Node `fixtures-and-gates` — Type check passes for `debate_core` | **PASS** | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`. |
| Node `fixtures-and-gates` — Import boundaries hold | **NOT RUN** | `uv run lint-imports` → `error: Failed to spawn: lint-imports / No such file or directory (os error 2)`. import-linter is not a dependency yet: it arrives with `v1-e02-t06-import-boundary-guard`, whose Goal is `Pending`. Equivalent checks run instead: `test_the_style_profile_model_imports_no_io_library` asserts `debate_core.domain.style_profile` imports nothing matching `docx`, `lxml`, `yaml`, `boto3`, `botocore`, `httpx`, `typer` or `fastapi`, and `test_style_classification_reaches_no_model` asserts the classifier's source mentions no model router or provider; both pass, and `uv run pyright packages/debate_core` is clean. See Deviations. |

Whole-suite check, after the work: `uv run pytest` → **`976 passed in 16.84s`**, 99% coverage
(`style_classifier.py` and `style_profile_loader.py` at 100%, `style_profile.py` at 99%).
`uv run ruff check .` → `All checks passed!`; `uv run ruff format --check .` → `179 files already
formatted`; `uv run scripts/validate_specs.py` → `OK: 281 files, 38 epics, 223 tasks, 20 releases`.

## Files changed

**`packages/debate_core/src/debate_core/domain/`** — `style_profile.py` is new: the
`StructuralUnit`, `RunEmphasis` and `StyleMatchSource` enums, the `StyleProfile` model and its
sub-models, and the five-route resolution. `__init__.py` re-exports them.

**`packages/debate_core/src/debate_core/evidence/`** — a new subpackage.
`style_profiles/verbatim.yaml` is the profile data; `style_profile_loader.py` loads and caches it
and resolves a document's own `basedOn` chains; `style_classifier.py` is the non-Verbatim
classifier; `__init__.py` is the package's public surface.

**`packages/debate_core/tests/evidence/`** — `test_style_profile.py` (78 tests) and
`test_style_classifier.py` (71 tests, including the fixture-backed ones and a small `.docx` reader
that `v1-e31-t03` supersedes).

**`scripts/`** — `scrub_docx_fixture.py` (the fixture gate), `survey_docx_styles.py` (the survey)
and `generate_style_fixtures.py` (builds the fixtures from the profile).

**`tests/scripts/`** — `test_scrub_docx_fixture.py` (23 tests) and `test_survey_docx_styles.py`
(21 tests). Both synthesize their own `.docx` packages in-process; nothing real is read.

**`tests/fixtures/debate_files/style_profile/`** — six synthetic `.docx` fixtures, their
`.expected.json` expectations, and `MANIFEST.md`.

**`docs/`** — `data/debate-file-style-survey.md` is new (and `data/` is a new directory, now listed
in `docs/README.md`). `packages/debate_core/README.md` gains a section on the profile.

**`plan_specs/v1/e31-debate-file-parsing/t02-verbatim-style-profile.yaml`** — Goal phase to
`Succeeded`.

## Deviations from the spec

1. **The style survey was run in this session rather than handed to the operator.** The
   `style-survey` node describes itself as operator-run and estimates "several minutes", on the
   basis that it would cross the two-minute hand-off threshold in
   [working-agreements.md §2](../process/working-agreements.md#2-anything-over-about-2-minutes-goes-to-the-operator).
   Measured, it does not: 186 files in 2.4 s, and the full 2,066-file run in **21 s**. The script
   reads only style information, emits only aggregates, and the files never left the machine
   holding them, so running it here cost nothing the hand-off was protecting. The exact command and
   corpus are in Operator follow-ups so the run is reproducible, and the report's own "Refreshing
   this report" section documents it.

2. **`uv run lint-imports` could not be run.** import-linter is not a dependency of this workspace;
   it is introduced by `v1-e02-t06-import-boundary-guard`, whose Goal is `Pending`. This is the same
   gap `v1-e30-t02-caselist-domain-model` reported, and the same substitute applies: two tests in
   `test_style_profile.py` assert the boundary directly for the modules this task adds, and
   `pyright` is clean. Nothing was added to `pyproject.toml`, because the import-linter contracts
   are `v1-e02-t06`'s to design.

3. **The 4-6 scrubbed excerpts are not committed, and the coach review did not happen.** The
   `fixtures-and-gates` node's description asks for them alongside the synthetic fixtures. Producing
   one requires the replacement list of real names and team codes, which the spec itself places
   outside the repository and which the coach maintains; the scrub script refuses to run without
   one, and guessing at the list is precisely the failure the gate exists to prevent. The synthetic
   fixtures, the scrub script, the manifest rows and the procedure are all in place, so the work
   left is the operator's. See Operator follow-ups and Follow-up work.

4. **`StyleProfile` was not added to `EXPORTED_MODELS`.** The published JSON Schemas are the
   contract the web client and the V2 API read, and they carry entities. The profile is
   configuration this package loads for itself, so it is documented in the package README instead.
   Flagged because the spec does not say either way.

## Decisions and assumptions

* **Resolution order is measured, not chosen.** Canonical id → recorded alias → display name →
  Word's numeric de-duplication suffix → `basedOn`. `basedOn` is last because the survey found
  `Heading411` in 197 files, inheriting from `Heading1` and meaning `Heading4`. A fixture and two
  tests pin this so a later edit cannot quietly reorder it.

* **The survey report names a style id only when it is published vocabulary or Word's
  de-duplication of one.** The first full run put `MaggieTag`, `JordanAnalytics` and
  `TashmaHeading1` into the committed report — real first names, in 12 to 23 files each, so a
  k-anonymity threshold alone did not catch them. Style ids a person chose are now counted and not
  named, over-long Word-concatenated ids are elided in the middle, and the full list stays in the
  uncommitted `--json` aggregate for the operator. The cost is real: `UnderlineFIXEDChar` and
  `StyleBoldUnderline` are useful aliases the report no longer surfaces on its own. They reached
  the profile through the JSON in this session, and the refresh instructions say to read it.

* **The writer style definitions were measured from 400 files, not written from memory.** Heading 2
  carries a **double** underline in 370 of them — not something worth guessing at, since single
  would look subtly wrong to anyone who cuts cards. `Emphasis` leaves `bold` inherited because the
  corpus is genuinely split (off in 262, on in 113), and imposing one reading on a team's template
  is not the writer's call.

* **The shrink threshold is measured too.** Over 63,599 sized runs in 120 caselist files, 79.7% of
  non-underlined runs are at `w:sz` 16 (8 pt) while underlined and highlighted runs sit at 22-26.
  Shrunk text is still evidence and is still parsed; being small is a formatting fact.

* **The heuristics are deliberately conservative, and one fixture exists to prove it.**
  `ordinary-document-with-outline-levels.docx` is a syllabus. No paragraph in it may be promoted to
  a pocket, hat, block or tag, and a test asserts that. The size and weight guards that make this
  true are CardMirror's, which the evaluation note recommended as a starting point.

* **Fixture expectations are written by hand, never generated by running the classifier.** A
  fixture whose answers came from the code under test proves nothing. `generate_style_fixtures.py`
  declares the expected unit, rule id and match source per paragraph; the test compares. A separate
  test fails if the committed expectations name an older `profile_version` than the profile does.

* **The scrub script replaces names across run boundaries.** Word splits a name into two runs after
  a spell-check pass, and a per-run replacement would miss it while the verification pass caught
  it — a scrub that always fails is no better than one that never runs. The replacement rewrites
  only the `w:t` nodes a match actually touches, so every run outside the match keeps its
  formatting, which is the whole value of a style fixture.

* **The scrub script was smoke-run against a real file**, a 383-paragraph team file, with output in
  the session scratchpad and not in the repository. It dropped three `customXml` parts, blanked
  five document properties, passed its own verification, and the result reads back cleanly with
  `python-docx` (`core_properties.author` and `last_modified_by` both empty). That is a check that
  the tool works on real input, not a substitute for the coach's review.

* **`RunEmphasis.HEADING` has no CardMirror mark**, and that is recorded rather than papered over.
  `HeadingNChar` styles carry a structural style's run formatting into a run, which is a formatting
  fact rather than an emphasis. A test asserts it is the only such emphasis.

## Operator follow-ups

**1. Reproduce or refresh the style survey** (expected runtime ~25 s for 2,066 files)

Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e31-t02-verbatim-style-profile`

```bash
uv run python scripts/survey_docx_styles.py \
  --input "caselist=$HOME/Documents/debate/2026-2027/LD Debate/Opencaselist/hsld26-0915" \
  --input "caselist=$HOME/Documents/debate/cardmirror-sample/caselist" \
  --input "caselist=$HOME/Documents/debate/cardmirror-sample/caselist-non-verbatim" \
  --input "caselist=$HOME/Documents/debate/cardmirror-sample/caselist-wiki" \
  --input "camp=$HOME/Documents/debate/2026-2027/Policy Debate/Camp Files" \
  --input "camp=$HOME/Documents/debate/cardmirror-sample/camp" \
  --input "team=$HOME/Documents/debate/cardmirror-sample/team" \
  --input "team=$HOME/Documents/debate/2024-2025" \
  --input "team=$HOME/Documents/debate/2025-2026" \
  --min-files 3 \
  --corpus-description "the hsld26-0915 caselist snapshot, camp files, and one team's files across the 2024-25, 2025-26 and 2026-27 seasons" \
  --output docs/data/debate-file-style-survey.md \
  --json ~/style-survey-full.json
```

Success looks like `surveyed 2066 files -> docs/data/debate-file-style-survey.md` and `git diff`
showing no change to the committed report. Point `caselist=` at the newest hsld26 snapshot only:
the snapshots are cumulative, so surveying all three counts most files three times. The `--json`
file carries every style id, including the ones the report withholds — it stays outside the
repository.

**2. Write the fixture replacement list.** This is the input everything below waits on. It names
real students, so it lives outside the repository and is never committed:

```bash
mkdir -p ~/.debate-intelligence
$EDITOR ~/.debate-intelligence/fixture-replacements.yaml
```

```yaml
version: 1
replacements:
  - find: <a real first and last name>
    replace: <an invented one>
  - find: <a team code>
    replace: <an invented one>
```

The script refuses a list whose replacement text still matches another entry, and refuses to write
any output in which a listed string survives.

**3. Scrub and review the 4-6 excerpts** (a few minutes each, mostly your reading time)

For each of the five slots in
[`tests/fixtures/debate_files/style_profile/MANIFEST.md`](../../tests/fixtures/debate_files/style_profile/MANIFEST.md):

```bash
uv run python scripts/scrub_docx_fixture.py "<source>.docx" \
    --output tests/fixtures/debate_files/style_profile/<descriptive-name>.docx \
    --replacements ~/.debate-intelligence/fixture-replacements.yaml
```

Keep each excerpt to a few cards, not a whole file. Then open each one in Word and confirm no name,
team code or authorship metadata remains and that the formatting looks like a real file. Fill in
the manifest row with the scrub date and your confirmation, and commit the `.docx` and the row
together. This is the node's `Coach reviews scrubbed excerpts` criterion.

**4. Nothing to change in GitHub or AWS for this task.**

## Follow-up work

* **The scrubbed excerpts may belong in `v1-e31-t03-debate-docx-parser` rather than here.** That
  task's `ac6` already asks for 8-10 scrubbed structural fixtures from the same categories, drawn
  from the same files, needing the same replacement list and the same coach review. Curating them
  once, there, would be cheaper than curating five here and eight more a task later — and it would
  let this task close on its synthetic fixtures, which is what its own tests need. A spec amendment
  moving the excerpts (and the coach-review criterion) to `t03` is the PM's call; if you would
  rather keep them here, Operator follow-up 3 is the whole job.

* **`scripts/compare_docx_roundtrip.py` keeps its own style tables.** It was written for the t01
  spike, before the profile existed, and its `PARAGRAPH_STYLE_UNITS`, `CITE_STYLES` and
  `NAMED_UNDERLINE_STYLES` now duplicate a subset of `verbatim.yaml` — with fewer aliases. It is
  operator tooling and never runs in CI, so this is not urgent, but the two will drift. Belongs
  with `v1-e33-t02-lossless-card-writer`, which is the next task to use that harness.

* **The magenta and red highlight question.** Both appear in the corpus (3,646 and 1,417 runs) but
  far below cyan, green and yellow, and the profile records them as not reading colours. If a team
  does read magenta, that shows up in `v1-e31-t05-parser-eval` as a per-unit recall miss, which is
  the right place to find out rather than guessing now.

* **`v1-e02-t06-import-boundary-guard` is now blocking a fourth task's criterion.** `v1-e30-t02`
  reported the same gap. When import-linter lands, its contracts should cover
  `debate_core.evidence` (no `docx`, no `lxml`, no provider SDK) as well as `domain` and
  `application`.

* **The survey script's `--json` aggregate is where new aliases will be found.** Nothing schedules
  a re-read of it. A sensible trigger is the next hsld26 snapshot backfill
  (`v1-e30-t06-initial-backfill`): re-run the survey, diff the JSON, and add any alias that has
  spread to enough files to matter.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
