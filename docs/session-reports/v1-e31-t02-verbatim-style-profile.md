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

**What the PM should look at first:** the session is PARTIAL, and for a reason the spec did not
anticipate. Goal criteria `ac1`–`ac5` all pass. The `fixtures-and-gates` node deliberately does
**not** ship the 4-6 scrubbed excerpts of real files it asks for: this repository is public, and
`docs/policies/caselist-data-use.md` prohibitions 1 and 9 forbid publishing caselist or camp data
"or any file built from them" to a git repository. That covers the team's own files too — teams
read cards other teams cut and disclosed, so essentially every real debate file contains another
program's evidence. Deviation 3 has the evidence, and the PM withdrew the criterion rather than
failing it.

That withdrawal is now the *only* thing keeping the session at PARTIAL. The second gap —
`uv run lint-imports`, which had no tool to run — closed when this branch was rebased onto
`origin/dev` and picked up import-linter from `v1-e29-t04`; it passes. Whether PARTIAL still fits
a session whose one remaining gap is a criterion the PM deliberately removed is the PM's call; the
status field is left as ruled. There is nothing outstanding for the operator to run.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `scrub-script` — Fixture scrub script | COMPLETE | `scripts/scrub_docx_fixture.py` plus 31 tests. Smoke-run against a real 383-paragraph team file, and a matching defect found and fixed after the first review pass (see Decisions). |
| `style-survey` — Style survey of the downloaded corpus | COMPLETE | `scripts/survey_docx_styles.py` plus 21 tests; report committed, over 2,066 files. Run in-session rather than handed to the operator — see Deviations. |
| `profile-model` — StyleProfile model and verbatim.yaml | COMPLETE | Model, YAML, loader, 78 tests. |
| `heuristic-classifier` — Non-Verbatim paragraph and run classifier | COMPLETE | `style_classifier.py`, 71 tests, 100% statement and branch coverage. |
| `fixtures-and-gates` — Style fixtures, coach review and quality gates | PARTIAL | Six synthetic fixtures, their expectations and `MANIFEST.md` are in; `pyright` passes. The scrubbed excerpts are withdrawn on policy grounds (Deviation 3), which removes the coach review with them; `lint-imports` could not run. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal `ac1` — `StyleProfile` loads from `verbatim.yaml` with a `profile_version`, defines `StructuralUnit` (POCKET…OTHER), and resolves every Verbatim style id/name and alias seen in the survey, including `basedOn`, to a unit or run emphasis | **PASS** | `uv run pytest packages/debate_core/tests/evidence/test_style_profile.py` → `78 passed`. Covers the exact enum member list, all nine canonical paragraph ids, all six character ids, the recorded aliases (`%tag`, `Analytics`, `cardtext`, `UnderlineFIXEDChar`, `StyleBoldUnderline`, `AAAUNDERLINEKEYBOARD`, `IntenseEmphasis`, `TitleChar`), display-name resolution, the de-duplication rule (`Heading411`→TAG, `Emphasis1`→EMPHASIS) and `basedOn` fallback (`HeadingFake`→BLOCK, `Rehighlighting`→EMPHASIS), plus `resolve_based_on_chain` on a missing ancestor and on a cycle. |
| Goal `ac2` — the profile records the CardMirror node/mark per ADR-0014, and a test asserts the mapping covers every unit and every CardMirror type listed in the evaluation note | **PASS** | Same run. `test_every_cardmirror_node_in_the_evaluation_note_is_accounted_for` and its mark twin parse the `### Nodes` and `### Marks` tables out of `docs/architecture/cardmirror-evaluation.md` and assert set equality in both directions (21 nodes, 20 marks); a guard test fails if the extraction ever comes back empty. `test_every_structural_unit_has_a_cardmirror_node` covers all nine units; `RunEmphasis.HEADING` is asserted to be the only emphasis with no mark, and its rule has to say so. |
| Goal `ac3` — the classifier labels headings, cite lines and evidence in the heuristic fixtures with the expected unit, rule id and match source `HEURISTIC`, deterministically and with no model calls | **PASS** | `uv run pytest packages/debate_core/tests/evidence/test_style_classifier.py` → `71 passed`. `test_every_fixture_paragraph_classifies_as_its_expectations_say` reads all six `.docx` fixtures and checks unit, rule id and match source against the committed `.expected.json`; `test_the_heuristic_fixtures_are_classified_without_a_single_verbatim_style` asserts every result in the three heuristic fixtures is `HEURISTIC` and that headings, a cite line and evidence are all present. Determinism: two tests classify 50 times and compare. No model calls: `test_style_classification_reaches_no_model` greps the module source. |
| Goal `ac4` — `scrub_docx_fixture.py` removes `docProps` author fields, comments, `people.xml`, custom XML and tracked-change authors and replaces names/team codes from a coach-supplied list; its tests prove a seeded name no longer appears anywhere in the output package | **PASS** | `uv run pytest tests/scripts/test_scrub_docx_fixture.py` → `23 passed`. `test_seeded_name_and_team_code_appear_nowhere_in_the_scrubbed_package` searches every part of the output three ways — raw bytes as text, XML tags stripped and whitespace collapsed, and the part names — and a companion test proves the input really did contain the name, so the first cannot pass vacuously. |
| Goal `ac5` — `docs/data/debate-file-style-survey.md` records aggregate style-name frequencies and the share of files per template family across the hsld26 snapshots and camp files, with no file names, schools or team codes | **PASS** | [`docs/data/debate-file-style-survey.md`](../data/debate-file-style-survey.md), 2,066 files: caselist 1,582, camp 110, team 374. Families: verbatim 23%, cardmirror 63%, wiki-converted 3%, other-heuristic 11%. Style tables give per-style file counts and reference counts; a style id is named only if it is published vocabulary or Word's de-duplication of one (see Decisions). Checked by hand for names after generation: `grep -ciE "maggie\|jordan\|tashma\|alex"` → `0`. |
| Node `scrub-script` — Scrub script tests pass | **PASS** | `uv run pytest tests/scripts/test_scrub_docx_fixture.py` → `31 passed`. Eight of those were added after a defect found in review; see Decisions. |
| Node `style-survey` — Style survey report committed (`contentMatch: "template family"`) | **PASS** | `docs/data/debate-file-style-survey.md` exists; `grep -c "template family"` → `1`. |
| Node `profile-model` — Style profile model and alias resolution tests pass | **PASS** | `uv run pytest packages/debate_core/tests/evidence/test_style_profile.py` → `78 passed in 2.02s`. |
| Node `heuristic-classifier` — Classifier tests pass | **PASS** | `uv run pytest packages/debate_core/tests/evidence/test_style_classifier.py` → `71 passed in 2.19s`. |
| Node `fixtures-and-gates` — Style fixture manifest exists (`contentMatch: "scrubbed"`) | **PASS** | `tests/fixtures/debate_files/style_profile/MANIFEST.md` exists; `grep -c "scrubbed"` → `2`. |
| Node `fixtures-and-gates` — Coach reviews scrubbed excerpts | **NOT RUN — criterion withdrawn** | No scrubbed excerpts are committed, so there is nothing to review, and none should be: see Deviation 3. Committing one would publish another program's disclosed evidence to a public repository, which `caselist-data-use.md` prohibitions 1 and 9 forbid and which scrubbing does not cure. Confirmed by the coach on 2026-09-20. `MANIFEST.md` records the reasoning in place of the slots. |
| Node `fixtures-and-gates` — Type check passes for `debate_core` | **PASS** | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`. |
| Node `fixtures-and-gates` — Import boundaries hold | **PASS** | `uv run lint-imports` → `Analyzed 94 files, 329 dependencies. … Contracts: 1 kept, 0 broken.` It could not run when this report was first written; rebasing onto `origin/dev` picked up `v1-e29-t04-s3-blob-store`, which added import-linter and the first contract. **What it proves is narrower than its name:** the single contract forbids `boto3`/`botocore` outside `debate_core.integrations.s3`, so it confirms this task's modules import no AWS SDK and nothing more. The boundary this task actually cares about is still held by its own tests — `test_the_style_profile_model_imports_no_io_library` (no `docx`, `lxml`, `yaml`, `boto3`, `botocore`, `httpx`, `typer` or `fastapi` in `domain/style_profile.py`) and `test_style_classification_reaches_no_model`. `v1-e02-t06` still owes the contracts that would make those tests redundant. |

Whole-suite check, re-run after rebasing onto `origin/dev` (which brought `v1-e02-t04`,
`v1-e29-t04` and `v1-e36-t06` with it): `uv run pytest` → **`1316 passed`**, 98% coverage overall,
with `style_classifier.py` and `style_profile_loader.py` at 100% and `style_profile.py` at 99%.
`uv run ruff check .` → `All checks passed!`; `uv run ruff format --check .` → `210 files already
formatted`; `uv run pyright packages/debate_core` → `0 errors`; `uv run lint-imports` →
`1 kept, 0 broken`; `uv run scripts/validate_specs.py` → `OK: 281 files, 38 epics, 223 tasks,
20 releases`.

One merge conflict during the rebase, in `packages/debate_core/README.md`: `v1-e29-t04` and this
task each added a section immediately before `### schemas/`. Both belong; resolved by keeping both,
with the S3 adapter section beside the other adapters and the style profile after it.

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

**`tests/scripts/`** — `test_scrub_docx_fixture.py` (31 tests) and `test_survey_docx_styles.py`
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

2. **`uv run lint-imports` could not be run — since resolved by the rebase, and no longer a
   deviation.** When this report was first written import-linter was not a dependency of the
   workspace, exactly as `v1-e30-t02-caselist-domain-model` had reported, and two tests in
   `test_style_profile.py` stood in for it. Rebasing onto `origin/dev` before opening the PR picked
   up `v1-e29-t04-s3-blob-store`, which added import-linter and the first contract, and
   `uv run lint-imports` now passes. PM ruling 3 accepted the substitute; it turned out not to be
   needed. The substitute tests stay, because the one existing contract only forbids the AWS SDK
   outside `integrations.s3` and says nothing about the domain layer importing `lxml` — which is
   the boundary this task's `forbidden` list actually names. Nothing was added to
   `pyproject.toml`; the remaining contracts are still `v1-e02-t06`'s to design.

3. **The 4-6 scrubbed excerpts are withdrawn, not merely outstanding.** The `fixtures-and-gates`
   node asks for them alongside the synthetic fixtures. They should not be committed, and the
   reason survived three attempts to find a way round it.

   * **The repository is public** (`charlesclark2/debate-intelligence`).
     [`caselist-data-use.md`](../policies/caselist-data-use.md) prohibition 1 forbids publishing
     "the archives, the sources, the parsed cards **or any file built from them**" to a git
     repository, and prohibition 9 forbids committing real caselist or camp files or excerpts at
     all. Permitted use 5 already says committed evaluation fixtures are synthetic and real-corpus
     evaluation runs "against the corpus in place".
   * **The team's own files are not a separate category.** This was the fallback — the team's work
     product rather than someone else's disclosure — and it does not survive contact with how the
     activity works. Teams read cards other teams cut and disclosed; re-cutting evidence somebody
     has already found is not something anyone does. Measured over the team's fourteen files: eight
     carry cite-tail cutter marks belonging to other programs' debaters (`Willie T` 46 times across
     4 files, plus `Oliver J`, `PT`, `AD`, `TM`, `MH`, `EA`, `RP`, `AWright`) or strings shaped like
     other schools' team codes (23 in one file, 14 in another). The remaining six carry no cite-tail
     marks at all, which is not evidence of origin either way. There is no file that can be
     certified as only this team's work.
   * **Scrubbing does not cure it.** Replacing a debater's initials protects that debater. The card
     is still another school's disclosed evidence, republished on a public repository, outside the
     Tabroom login it sits behind.

   Confirmed with the coach on 2026-09-20. `MANIFEST.md` now records this in place of the slots,
   and the scrub script's own docstring says plainly that scrubbing makes a copy safe to work with
   locally and does not make a real file safe to commit. **Recommended spec amendment:** drop the
   scrubbed excerpts and the coach-review criterion from this node, and from `v1-e31-t03`'s `ac6`,
   which asks for 8-10 of the same thing. Real-file coverage belongs to `v1-e31-t05-parser-eval`,
   in place, over all 2,066 files — stronger evidence than six hand-picked ones.

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
  full aggregate, which — per PM ruling 6 — is now written on **every** run to
  `docs/data/debate-file-style-survey.full.json`, gitignored, beside the committed report. The
  report is a summary of that file: 47 paragraph style ids and 75 character ids are in the
  aggregate, 24 of the paragraph ids are withheld from the report, and the aggregate also carries
  every display name and all 6,127 `basedOn` links. That is what stops `UnderlineFIXEDChar` and
  `StyleBoldUnderline` — real underline aliases the report does not name — from being lost next
  season, without relying on anyone having passed an optional flag.

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

* **The scrub script had a matching defect, found in review and fixed.** Replacement was an
  unanchored case-insensitive substring match. That is safe for a full name and dangerous for a
  cutter mark: real teams sign cites with two letters, and `AD`, `PT`, `EA`, `TM` and `RP` are all
  real marks in this corpus. Unanchored, `AD` rewrites the inside of `ADVANTAGE`, `PT` of
  `CAPTURE`, `EA` of `TEAM` — silently, inside quoted evidence, which is worse than any privacy
  problem the script solves. Replacement is now anchored so it can never begin or end inside a
  word. Verification deliberately is **not**: for a string long enough to be unmistakable it still
  looks anywhere, including inside the bytes of an embedded image, where there are no word
  boundaries to anchor to. Eight regression tests cover both halves, including the case from a real
  file where `Charlie C.` is a cutter mark and `Charlie Kirk` is a person named in the quotation.

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
  --output docs/data/debate-file-style-survey.md
```

Success looks like `surveyed 2066 files -> docs/data/debate-file-style-survey.md` and `git diff`
showing no change to the committed report. Point `caselist=` at the newest hsld26 snapshot only:
the snapshots are cumulative, so surveying all three counts most files three times.

The run also writes `docs/data/debate-file-style-survey.full.json` — always, and gitignored —
which holds every style id including the ones the report withholds. **Read it after a refresh:**
a style id that has spread to enough files to matter belongs in the profile's alias list, and the
aggregate is the only place it appears.

**2. Nothing else.** The fixture replacement list and the scrubbed excerpts that earlier drafts of
this report asked for are withdrawn — see Deviation 3. There is no scrubbing for the operator to
do and no list to write.

**3. Nothing to change in GitHub or AWS for this task.** One thing worth knowing rather than doing:
the repository is public, which is what makes Deviation 3 binding. If it ever goes private that
changes the risk but not the policy, and the policy is the thing that would have to be amended.


## Follow-up work

* **`v1-e31-t03`'s `ac6` needs the same amendment this task did.** It asks for 8-10 scrubbed
  structural fixtures from team, caselist, wiki-converted and camp files. Every argument in
  Deviation 3 applies to it unchanged, and it will block in exactly the same place. Better to amend
  it now than to have a session discover it again. `v1-e31-t05-parser-eval` should be checked too:
  its labelled set is fine as long as the labels live in the repository and the files it labels do
  not.

* **Cards travel between teams, and the cite-tail cutter mark is how you can tell — which is a
  finding for `v1-e31-t04-card-fingerprints`.** That task was specced around "the same card
  disclosed by many teams"; the corpus shows the same card also travels *into* team files, marked
  with the initials of whoever originally cut it. A mark like `Willie T` at the end of a cite is a
  real provenance signal about which program a card came from, sitting in the text the parser
  already reads. Worth recording on a `ParsedCard` rather than discarding — it is a cheap
  cross-team occurrence link. It is also personal data about a student at another school, so it
  belongs under the same minimization rules as a team code, never expanded or re-identified
  (`caselist-data-use.md` prohibition 6).

* **`scripts/compare_docx_roundtrip.py` keeps its own style tables.** It was written for the t01
  spike, before the profile existed, and its `PARAGRAPH_STYLE_UNITS`, `CITE_STYLES` and
  `NAMED_UNDERLINE_STYLES` now duplicate a subset of `verbatim.yaml` — with fewer aliases. It is
  operator tooling and never runs in CI, so this is not urgent, but the two will drift. Belongs
  with `v1-e33-t02-lossless-card-writer`, which is the next task to use that harness.

* **The magenta and red highlight question.** Both appear in the corpus (3,646 and 1,417 runs) but
  far below cyan, green and yellow, and the profile records them as not reading colours. If a team
  does read magenta, that shows up in `v1-e31-t05-parser-eval` as a per-unit recall miss, which is
  the right place to find out rather than guessing now.

* **`v1-e02-t06-import-boundary-guard` should absorb this task's two substitute tests.**
  import-linter now exists, via `v1-e29-t04`, with one contract covering the AWS SDK. When `t06`
  writes the full set, they should cover `debate_core.domain` importing no I/O library at all and
  `debate_core.evidence` importing no provider SDK — at which point
  `test_the_style_profile_model_imports_no_io_library` and `test_style_classification_reaches_no_model`
  become redundant and should be deleted rather than left to rot as a second, weaker copy of the
  same rule.

* **The full aggregate is where new aliases will be found, and nothing yet schedules a re-read.**
  PM ruling 6 made it unconditional and gitignored, so it is always on disk beside the report
  rather than behind a flag someone has to remember. What is still manual is looking at it. A
  sensible trigger is the next hsld26 snapshot backfill (`v1-e30-t06-initial-backfill`): re-run the
  survey, diff the JSON against the previous run, and add any alias that has spread to enough files
  to matter. Worth a line in that task's spec rather than trusting to memory.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude, project chat), 2026-09-20

**Rulings, in the order you asked them:**

1. **Withdraw the scrubbed excerpts. Agreed, and the reasoning is the important part.** Measuring
   that 8 of the team's 14 files carry other programs' cutter marks is what settles it: "our own work
   product" is not a safe category in an activity where cards travel. Prohibitions 1, 9 and 10 apply
   to team files as much as to caselist ones, and scrubbing a debater's initials does not change
   whose evidence it is. The node now takes synthetic fixtures, one per measured template family, and
   the coach-review criterion is withdrawn rather than failed. The scrub script still ships for
   operator-side use.
2. **v1-e31-t03 ac6 amended the same way, and v1-e31-t05 with it.** t03 takes synthetic structural
   fixtures; t05 keeps labels and scores in the repository (keyed by sha256, paragraph index and text
   hash) and leaves the files on your machine. Ruling now, as you suggested, rather than blocking a
   session later.
3. **lint-imports NOT RUN: accepted**, on the v1-e30-t02 precedent, with the substitutes standing.
   This is the fourth task to carry it, so v1-e02-t06 moves up the queue, and its contracts should
   cover debate_core.evidence when it lands.
4. **"Operator-run" is a runtime-and-consequence judgement, not a label, and you judged it right.**
   A read-only scan of files Charlie already has, finishing in 21 seconds, is not a hand-off. I have
   written the rule into docs/process/working-agreements.md so it is not a judgement call next time:
   a hand-off is (a) over about two minutes, (b) a change outside the worktree, or (c) something
   needing credentials or approval. The node's wording is amended to match.
5. **StyleProfile stays out of EXPORTED_MODELS.** The published schemas are the contract the web
   client and V2 API read; the profile is configuration this package loads for itself. Export it if
   and when a client needs it.
6. **The redaction rule is right, and the manual step is not.** Naming only published vocabulary is
   correct; relying on someone remembering to read an uncommitted --json aggregate is how
   UnderlineFIXEDChar gets lost next season. **One commit before you open the PR:** make
   survey_docx_styles.py always write the full unredacted aggregate to a gitignored path (e.g.
   docs/data/.style-survey-full.json, added to .gitignore), and have the refresh instructions cite
   that file rather than a flag. The spec is amended to require it.
7. **PARTIAL session with a Succeeded Goal: confirmed.** All five Goal criteria pass; the gaps are at
   node level, one withdrawn and one deferred to a task that does not exist yet. That is exactly the
   combination the report's status field is for.

**Two findings worth more than the rulings:**

- The scrub-script defect is an evidence-integrity near-miss caught in the right place: an unanchored
  two-letter replacement rewriting the inside of ADVANTAGE, CAPTURE and TEAM inside quoted evidence
  would have been very hard to find later. Anchored replacement with unanchored verification is the
  right asymmetry, and the Charlie C. / Charlie Kirk regression test is the one that proves it.
- 63% of the corpus, and 78% of caselist files, carries CardMirror bookmarks. The editor ADR-0014
  made a compatibility target is what most disclosed files have already passed through, so its dual
  underline encoding is the common case rather than an edge. That is a direct input to v1-e33-t02 and
  strengthens ADR-0014.

Cutter marks are now recorded in v1-e31-t04's spec as opaque provenance under the same minimization
rules as a team code. All spec amendments are on branch `specs/style-profile-rulings`.
