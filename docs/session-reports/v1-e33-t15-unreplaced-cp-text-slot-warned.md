# Session report: v1-e33-t15-unreplaced-cp-text-slot-warned

| | |
|---|---|
| Task | `v1-e33-t15-unreplaced-cp-text-slot-warned` — A built file still holding the CP text placeholder is warned, and a CP draft has a smoke check |
| Spec | [`plan_specs/v1/e33-file-builder/t15-unreplaced-cp-text-slot-warned.yaml`](../../plan_specs/v1/e33-file-builder/t15-unreplaced-cp-text-slot-warned.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t15-unreplaced-cp-text-slot-warned` |
| Session status | COMPLETE |

## Summary

A built file whose analytic is still `files suggest`'s CP text slot now gets a WARN from a new quality
check, `placeholders-replaced`. The WARN names the slot's paragraph and the headings above it, pocket to
block. It is never a FAIL, so the file still publishes. `files build` and `files check` print it as a
finding line through t12's `finding_line`, and `files publish` lists it under "Warned, not blocked".
The presenter needed no special case for any of the three. The QUALITY_FAILED hint now says the
findings are listed above and that the `.quality.md` has the full report. A synthetic counterplan recipe
and a `kind` argument give the example corpus a CP position. The new smoke check suggests a draft for it,
finds the slot first, marks the draft ready unchanged, builds it, and finds the WARN. It passed on the
checkout's script and on an offline stamped, installed build. The checker version is now
`2026.10.31-file-checks-3`. **Look first at** the two consequences of a new check id under
[Decisions](#decisions-and-assumptions):

* every checks table has one more PASS row;
* a `.quality.json` written before this change is no longer readable, so publishing such a file needs a
  `files check` first. e33-t05's prod file holds no slot.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `unreplaced-cp-text-slot-warned` — Placeholder warned | Done | Tests and a do-nothing skeleton first (`71abc60`, red), then the check, its wiring, the version bump and the hint (`0c0ad00`, green); one test's unpack made an assertion (`9baaa5b`) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a built file holding the placeholder carries a WARN naming its block | PASS | `test_placeholders.py` (6 tests, results written out whole with hand-counted paragraphs), `test_file_quality_mutations.py::test_a_file_still_holding_the_cp_text_slot_passes_warned_naming_its_block` (the finding line and the `.quality.md` line, by hand), `test_file_build_service.py::test_a_built_file_still_holding_the_cp_text_slot_is_built_and_warned_naming_its_block` |
| ac1: shown by build, check and publish | PASS | `test_files.py::test_files_build_check_and_publish_warn_of_the_cp_text_slot_and_publish_goes_ahead`: build and check print `Failures and warnings:` then the line below; publish exits 0 with `1 PUBLISHED. Warned, not blocked: politics-da-slot-left: placeholders-replaced` and five objects in moto's bucket. `test_file_publish_service.py::test_a_file_still_holding_the_cp_text_slot_is_published_warned_not_blocked`: `warned_checks == (placeholders-replaced,)`, metadata `(1, ["placeholders-replaced"])` |
| ac1: a file without it is unchanged | PASS | Its verdict and findings are unchanged; its checks table has one PASS row more. `test_a_file_built_by_t02_passes_every_check` (every check PASS, the new one included), `test_a_file_without_the_slot_has_one_pass_result`, `test_only_an_analytic_that_is_exactly_the_slot_is_warned`, and t12's `test_files_build_and_check_of_a_clean_file_print_nothing_after_the_table`, unchanged and green. t12's hand-written clean table gains the `placeholders-replaced PASS 0 0` row (Deviations) |
| ac1: the QUALITY_FAILED hint says the findings are above | PASS | `test_the_quality_failed_hint_says_the_findings_are_listed_above_and_names_the_full_report`, for check and build |
| ac1: a smoke check builds a CP draft from the example corpus and finds the slot first | PASS | Checkout's script: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -p no:randomly -q -n 0 tests/smoke/test_files_cli.py` → `3 passed in 12.54s`. Installed build ([below](#the-installed-build)): `tests/smoke/test_files_cli.py tests/smoke/test_files_publish.py` with `-m "not live and not in_process"` → `5 passed in 7.66s` |
| ac1: tests shown failing first | PASS | [Red run](#red-then-green): 13 failed, 219 passed on the skeleton; smoke 1 failed, 2 passed |
| Node: `uv run pytest packages/debate_core/tests -k "file_check or quality"` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests -k "file_check or quality" -q` (the same selection, without uv's sync) → `143 passed in 45.03s` |
| Forbidden: a FAIL for the placeholder | PASS | The check's only statuses are WARN and PASS. `test_the_slot_is_never_a_fail`, and mutant 1 (the check a FAIL) is caught by 9 tests and the smoke check. A file that does not parse fails this check with that reason, as every check that reads the document does (Deviations) |
| Forbidden: a real disclosed file in a fixture | PASS | `tests/fixtures/file_builder/counterplans/policy-nhi-states-cp.yaml` is invented: its fingerprints are made-up hex, it has no pins, and the corpus builds every source from synthetic text. No school or team code is named. The smoke check asserts that the corpus's invented teams never appear in the output |

### What a person sees

The finding line `files build` and `files check` print below the checks table. It is written by hand in
`test_files.py` from the policy example, with its first analytic replaced by the slot:

```text
Failures and warnings:
  WARN placeholders-replaced paragraph 4, under Politics DA answers > Uniqueness > Non-unique - the agenda is already stalled: the analytic is still the placeholder for the counterplan's text that `files suggest` drafts: write the text the team reads in its place, then build again
```

The QUALITY_FAILED panel's hint was `Read the .quality.md beside the file for each card's finding.`. It
is now `Each finding is listed above; the .quality.md beside the file has the full report.`.

### Red, then green

* Red, on the skeleton (`71abc60`). The skeleton has the enum member and description, the constant
  moved, and a `check_placeholders` that returns nothing and is not wired in:
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -p no:randomly --tb=line -q`
  over the changed test files → `13 failed, 219 passed in 7.07s`. The failures:
  * the six placeholder unit tests;
  * the service, build, publish and CLI tests that expect the WARN;
  * the not-a-docx test, which expects the new check to say why it cannot run;
  * the hint test;
  * the hand-written Markdown, because the checker version was not yet bumped.

  The smoke module on the checkout's script (`-n 0`) → `1 failed, 2 passed`. The counterplan check failed
  at the build's findings (`assert [] == [('WARN', 'pl…`), after its draft-opens-with-the-slot
  assertions had passed.

  One more test failed in an earlier run, not counted above: `test_no_check_calls_a_model` pins the
  number of check modules it scans at 5, and the new module makes 6. That pin was updated before the
  recorded run.
* Green (`0c0ad00`): the same files plus `test_file_suggest_service.py` → `266 passed in 5.10s`, and the
  smoke module → `3 passed in 12.54s`.

### Mutants (agreement 8; each run had a fresh `HYPOTHESIS_STORAGE_DIRECTORY`, though no test here uses Hypothesis)

A scratch driver applied each mutant to the committed source, ran the unit and CLI tests below, and then
restored the file from HEAD, checking that `git status` was clean. Mutants 1 to 4 and 6 to 8 were also run
against the files smoke module on the checkout's script. The unit and CLI tests were
`packages/debate_core/tests/evidence/file_checks`, `test_file_quality_mutations.py`,
`test_file_build_service.py`, `test_file_publish_service.py`, `test_files_check_findings_presenter.py`
and `packages/debate_cli/tests/commands/test_files.py`.

| Mutant | Where | Result |
|---|---|---|
| (1) The check a FAIL | `placeholders.py` | Caught: 9 failed, all at assertions. The smoke check also failed: the build exits 1 with `QUALITY_FAILED: placeholders-replaced` |
| (2) The string copied rather than the constant, then the constant changed | `placeholders.py`: compares with the literal, and `CP_TEXT_SLOT` becomes `[the counterplan's text: write it here]` | Caught: 8 failed (the check never warns). The smoke check also failed: `assert [] == [('WARN', …)]`. On the installed build it failed at the draft's first item, because the test reads the checkout's constant ([below](#the-installed-build)) |
| (3) The block not named | `placeholders.py`: `section_path=None` | Caught: 6 failed. The smoke check also failed: `('WARN', …, 3, None)` |
| (4) Publish blocked by it | `file_publish_service.py`: refuses when a finding is `placeholders-replaced` | Caught: 2 failed, the publish service test (`REFUSED is PUBLISHED`) and the CLI publish. The files smoke check does not publish, so it passed |
| (5) The hint unchanged | `files_presenter.py` | Caught: 1 failed, the hint test |
| (6) The check not wired into the service | `file_quality_service.py` | Caught: 4 failed. The smoke check also failed |
| (7) A substring match instead of an exact one | `placeholders.py` | Caught: 1 failed, `test_only_an_analytic_that_is_exactly_the_slot_is_warned`. The smoke check passed, as expected |
| (8) Every heading named by its text, known or not | `placeholders.py` | Caught: 1 failed, `test_a_heading_the_sidecar_does_not_name_is_given_by_its_level_and_paragraph`. The smoke check passed |

Mutant 6 failed one build-service test at a tuple unpack rather than an assertion; the other three
catches were assertions. The unpack is now an assertion (`9baaa5b`).

### The installed build

HEAD `9baaa5b` was built offline in the scratchpad, outside the checkout:

1. `git archive HEAD`, then `scripts/stamp_build.py stamp --version 0.0.1.dev915 --tag v0.0.1-dev.915
   --channel dev --commit 9baaa5b… --run-id local`.
2. `uv build --offline` for `debate-core` and for `debate-cli`.
3. A new uv venv on the managed CPython 3.12.13 with the two wheels installed `--no-deps`. A `.pth` holds
   one plain path, the worktree venv's `site-packages`, for third-party packages only.

In that venv, `debate_core.__file__` and `debate_cli.__file__` were in its own `site-packages`, and no
`packages/*/src` path was on `sys.path`. `debate-research --version --json` reported channel `dev`,
commit `9baaa5b…` and tag `v0.0.1-dev.915`.

The runs against it, each with `DEBATE_SMOKE_BIN`, `DEBATE_SMOKE_EXPECT_SHA` and
`DEBATE_SMOKE_EXPECT_TAG` set:

1. `tests/smoke/test_files_cli.py tests/smoke/test_files_publish.py -m "not live and not in_process"`
   → `5 passed in 7.66s`.
2. Mutant 2, in a `debate-core` wheel rebuilt from the scratch copy and reinstalled with `--reinstall`
   (`grep` confirmed both changes in the installed module) → `1 failed, 2 passed`. The check failed at
   `test_files_cli.py:214`: the installed build's draft opened with the changed constant, and the test
   compares it with the checkout's. In `validate-dev` the installed build and the checkout are the same
   commit.
3. The clean wheel was rebuilt and reinstalled, and `diff -r` matched its `debate_core` source to the
   worktree's. The files smoke module → `3 passed in 7.69s`.

### Before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --run` | `94 of 615 test files (15.3%) chosen in 13.1 s from 19 changed files`. Stopped at its 115-second limit (exit 124) at 94%, with load near 15 from other sessions: 3,323 passed and no failure or error before the stop. Agreement 10 leaves the rest to the pull request's `ci` check, which runs the same affected set |
| The always-run list: `tests/architecture tests/specs` and the CLI's `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | `372 passed in 16.41s` |
| The changed test files and the suggest service's (as in green above) | `266 passed`; files smoke `3 passed` |
| `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `1708 files already formatted` / `All checks passed!` |
| `.venv/bin/pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `.venv/bin/lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/export_file_quality_schema.py --check` | `OK: docs/data/file-quality-report.schema.json is up to date` |
| `uv run scripts/validate_specs.py` | `OK: 543 files, 41 epics, 480 tasks, 22 releases` |
| `git diff HEAD origin/dev -- <this spec>` | Only `status.phase` differs: no PM amendment while the task ran |

## Files changed

* **`debate_core.evidence.file_checks`**: new `placeholders.py`, which holds the check and `CP_TEXT_SLOT`,
  now defined here. In `report.py`: `QualityCheck.PLACEHOLDERS_REPLACED` (last, so the other checks keep
  their order), its description, and `CHECKER_VERSION` `2026.10.31-file-checks-3`. `__init__.py`'s
  docstring lists the module.
* **`debate_core.application`**: `file_quality_service.py` runs the check after the heading check, with
  the sidecar's known headings, and counts it among the checks that need the document.
  `file_suggest_service.py` imports `CP_TEXT_SLOT` from the checks and still exports it; its docstring
  says the build warns of the slot.
* **`debate_cli`**: `files_presenter.py`, the QUALITY_FAILED hint.
* **`docs/data/file-quality-report.schema.json`**: regenerated by `scripts/export_file_quality_schema.py`.
  The enum gains `placeholders-replaced`.
* **Tests**:
  * `test_placeholders.py` (new).
  * New tests in `test_file_quality_mutations.py`, `test_file_build_service.py`,
    `test_file_publish_service.py`, `test_files.py` and `test_files_check_findings_presenter.py`.
  * Pins updated for the new check, listed under Deviations.
* **`tests/fixtures/file_builder`**:
  * `counterplans/policy-nhi-states-cp.yaml` (new, synthetic).
  * `example_corpus.py`: `example_corpus(..., kind="da")` and `COUNTERPLANS`. t01's examples keep `da`,
    so their corpora are byte for byte what they were.
* **`tests/smoke/test_files_cli.py`**: the counterplan check. The world fixture's body moved into
  `planted()`, which both fixtures call; the two existing checks are otherwise unchanged and still pass.

## Deviations from the spec

* **A generated file outside the listed packages.** `docs/data/file-quality-report.schema.json` is the
  report model's schema, regenerated by its script. Its drift test fails without it.
* **Three hand-written pins grew with the new check.**
  * t12's `test_a_file_with_no_warn_or_fail_prints_exactly_the_table_it_printed_before` now has a ninth
    row, `placeholders-replaced PASS 0 0`. Its docstring says why.
  * `test_report.py`'s expected Markdown has the new row and the new checker version.
  * `test_no_check_calls_a_model` counts 6 check modules instead of 5, and the new module passes its
    word scan.

  The spec says "a file without it is unchanged", and I read that as: its status, findings and
  finding lines are unchanged. Its checks table is not quite unchanged, because a new check id always
  adds a row (Decisions).
* **The counterplan recipe is not in `recipes/`.** That directory is pinned to t01's three examples
  (`test_file_recipes.py`), and `docs/guides/file-recipes.md` quotes each of them. Adding a fourth there
  would mean editing the guide, which is outside this task's packages. It sits in
  `tests/fixtures/file_builder/counterplans/` instead. The PM asked for it "in the file-builder example
  corpus (tests/fixtures/file_builder)", and it is there.
* **A FAIL under the new check id when the file does not parse.** A file the parser refuses fails every
  check that reads the document, each saying "the built file does not parse: …"
  (`file_quality_service.py`'s "When a check cannot run"). This check reads the document, so it is in
  that list too. The FAIL is about the file, not the placeholder, and such a file already fails
  evidence-identity and four other checks. Only the PM can rule otherwise, for example to leave this
  check silent when the file does not parse. I did not do that, because a PASS summary for a check that
  never ran is what the service's rule forbids.

## Decisions and assumptions

* **A new check id rather than a new result of an existing one.** The existing checks ask about the
  sidecar, card identity, cites, duplicates, heading structure, alignment, provenance and removals.
  None of them asks what an analytic says. A WARN under `heading-structure` or `cite-present` would name
  the wrong check in every line the coach reads, and in `metadata.json`'s `warned_checks`. It costs two
  things:
  * every checks table and `.quality.md` gains one PASS row;
  * a report is held to "every check, once, in order". So a `.quality.json` written by checker
    `2026.10.22-file-checks-2` no longer validates against this build's model. I ran it: an old-shape
    report is refused with `a report summarises every check once, in order`.
* **What the bump means for files built before.**
  * **Already published.** Nothing is re-read. `find_by_source` reads `metadata.json`, which keeps its
    `checker_version`.
  * **Built but not yet published.** `files publish` now refuses the file as `QUALITY_REPORT_MISSING`
    ("is missing or is not a quality report this build reads"), with the hint to run `files check`. After
    `files check`, a file without the slot gets `placeholders-replaced` PASS and publishes as before.
  * **e33-t05's prod file** has no placeholder, so its verdict is unchanged. If it were published again
    after a `files check`, the code says its `.quality.json` and `metadata.json` would be written again,
    not skipped, because their bytes carry the new checker version. I read this from the code; I did not
    run it. t08's bump had the same effect.
* **Where the constant lives.** The PM asked that the check read `CP_TEXT_SLOT`, not copy it.
  `debate_core.evidence` sits below `debate_core.application` in the layers contract, and the quality
  service cannot import the suggest service: suggest imports build, which imports quality, so that
  would be a cycle. So the constant is defined once, in the checks' module, and the suggest service
  imports and re-exports it. Every test that builds with the slot imports it from `files suggest`'s
  module, as t11's tests do.
* **Naming the block.** The WARN's `section_path` gives the pocket, hat and block above the slot,
  outermost first, and `paragraph_index` gives its paragraph. A heading the sidecar records as the
  coach's is named by its text. Any other is named by level and paragraph (`block at paragraph 3`), as
  the heading check names one, so the report never carries text the coach did not write. The message
  does not repeat the slot's words.
* **Exactly the slot.** An analytic with the slot's words inside a longer text is the coach's own and is
  not flagged. Only paragraphs the parser reads as `ANALYTIC` are looked at, which is what the writer
  writes an analytic as.
* **The hint** applies wherever the panel uses the default. `files check`'s notes still replace it when
  there are any, as before.
* **The smoke check's counterplan** is named `states-cp` (side NEG, kind `cp`). Its draft is
  `states-cp-neg-draft.yaml`, with no block left out. The check reads the block's name from the draft,
  not from a guess at how suggest normalizes headings.

## Operator follow-ups

None. The affected set's remainder runs in the pull request's `ci` check (agreement 10).

## Follow-up work

* **Publish's handling of an older report.** A file built before a checker bump is refused as
  `QUALITY_REPORT_MISSING`. That wording reads as if the report were absent, while the hint (run
  `files check`) is right. Publish could name the case: "written by an older version of the checks".
  This belongs to E33, in `file_publish_service.py`. The PM decides whether it is worth a task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

An unreplaced CP text slot now shows wherever the coach looks, and still publishes.
1. **ac1 passes.**
   * Red: 13 failed on a do-nothing skeleton, plus the smoke check failing at the build's findings
     after its slot-first assertions passed. Green: 266 and 3.
   * The node criterion passes (143).
   * The finding line, written by hand, names the paragraph and pocket > hat > block.
   * The smoke check passes on an offline stamped, installed build too.
2. **Mutants:** eight, all caught. Mutant 2 (the copied string) shows the constant is really read.
   Mutant 4 (publish blocked) is caught by both the service and the CLI. You turned mutant 6's tuple
   unpack into an assertion.
3. **Decisions accepted:**
   * **A new check id, `placeholders-replaced`, last in order.** A WARN under another check would name
     the wrong check in every line the coach reads.
   * **The checker version bumped to `2026.10.31-file-checks-3`, with what that means stated.**
     Published files are untouched. A built but unpublished file needs a `files check` before publish
     (`QUALITY_REPORT_MISSING` until then). e33-t05's prod file has no slot.
   * **`CP_TEXT_SLOT` defined in the checks module and re-exported by suggest,** which the layers
     contract and the import cycle require.
   * **Headings the coach didn't write named by level and paragraph,** so no other text leaks.
   * **An exact match only.**
4. **Deviations accepted:**
   * the regenerated schema, which its drift test requires (the PM's next batch adds `docs/data` to
     the spec's packages);
   * the three pins that grew by one row;
   * the counterplan recipe kept out of `recipes/`, so the guide's quoted examples stay as they are;
   * a FAIL under the new id when the file doesn't parse, as every document-reading check does, which
     is the service's rule.
5. **Follow-up: yes, one p3 E33 task in the PM's next batch.** Publish names a report written by an
   older checker version as such, instead of "missing".
6. **Closing checks:** the affected set (94 files) stopped at 94% at its limit with nothing failing,
   and is left to the PR's `ci` under agreement 10. The always-run list (372), the changed files (266),
   the files smoke check (3), ruff, pyright, lint-imports, thin handlers, the schema check and the
   specs are clean.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. v1-e33-t14 also touches file-recipes.md;
   whichever merges second rebases that paragraph.
