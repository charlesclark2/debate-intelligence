# Session report: v1-e33-t16-publish-names-an-older-quality-report

| | |
|---|---|
| Task | `v1-e33-t16-publish-names-an-older-quality-report` — files publish names a quality report written by an older version of the checks, rather than calling it missing |
| Spec | [`plan_specs/v1/e33-file-builder/t16-publish-names-an-older-quality-report.yaml`](../../plan_specs/v1/e33-file-builder/t16-publish-names-an-older-quality-report.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t16-publish-names-an-older-quality-report` |
| Session status | COMPLETE |

## Summary

`files publish` now refuses a built file whose quality report was written by another version of the
checks as `QUALITY_REPORT_OUTDATED`, naming both versions (`its quality report was written by version
2026.10.27-file-checks-2 of the checks, and this build runs 2026.10.31-file-checks-3`), with no path in
the message and `QUALITY_REPORT_MISSING`'s hint word for word. It does this whether or not the older
report still reads. An absent report, or one that names no version and is not a report, stays
`QUALITY_REPORT_MISSING`; neither is ever published. Under the PM's amendment of 2026-10-31, a file that
publish lets through with warnings now has each warning printed below the table in `files check`'s own
line (`finding_line`), under its slug, and carried in `--json` as the file's `warnings`. The PM may want
to look first at **the hint's path** (Decisions): the hint is MISSING's, so it holds the command
line's `.docx` path, which a strict reading of the forbidden "a path … in a refusal" would not allow.
The second thing to look at is that **the codes are documented in `docs/data/`, not `docs/runbooks/`**
(Deviations).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `publish-names-an-older-quality-report` (Older report named) | Done | Red over a skeleton (`933701e`), then the gate and the presenter (`d29b65f`); 17 of 17 mutants caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: an older report is refused with its own code naming both checker versions, an absent one keeps `QUALITY_REPORT_MISSING`, a current one publishes as before; by tests shown failing first | PASS | Red at `933701e` (below): both older-report cases came back `QUALITY_REPORT_MISSING` or were let through to the bucket. Green: `test_a_report_from_an_older_version_of_the_checks_is_refused_naming_both_versions_and_no_path[as_the_older_checker_wrote_it, only_its_version_older]`, `test_an_older_report_is_refused_by_a_dry_run_too_and_files_check_lets_it_through`, the five `test_a_report_that_is_absent_or_unreadable_stays_missing[…]` cases, and on the CLI `test_files_publish_refuses_a_report_from_an_older_version_of_the_checks_naming_both`. "A current one publishes as before" is the existing moto tests (`test_a_pass_file_publishes_five_objects_under_its_prefix_metadata_last` and the rest of the file), unchanged and passing |
| ac2: (PM amendment 2026-10-31) a file publish lets through with warnings prints each warned check's finding line as `files check` does, messages only, and a `QUALITY_FAILED` refusal still carries the sidecar's warnings; by tests shown failing first | PASS | Red at `933701e`: no lines below the table and an empty `warnings`. Green: `test_a_warned_file_carries_each_warned_result_and_a_clean_one_none` (core), `test_files_publish_prints_each_warning_of_a_file_it_lets_through_as_files_check_does` (CLI dry run: the last two lines are `Warned, not blocked in policy-nhi-politics-da-answers:` and `WARN sidecar: the sidecar was written under style profile 2026.11.02-verbatim-2; …`, and `--json`'s `warnings` match), and t15's real publish test now also pins `Warned, not blocked in politics-da-slot-left:` plus t15's `SLOT_LEFT` line. t10's `test_files_publish_re_check_warns_of_another_style_profile_and_its_refusal_says_so` is unchanged and passes |
| Node: Older report named tests pass | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/application/test_file_publish_service.py` → `42 passed in 7.33s` |
| Node: files publish CLI tests pass, the warning lines included (added with ac2) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_cli/tests/commands/test_files.py -k publish` → `10 passed in 7.81s` |

### Red run (`933701e`, over the skeleton)

The skeleton added `FileRefusalCode.QUALITY_REPORT_OUTDATED` and an empty `warnings` field on
`FilePlan`/`PublishOutcome`, with no behaviour, so every test fails at an assertion and none at
collection. Command: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <file> -k
<new tests> -p no:randomly -q --tb=line -n 0`.

* `test_file_publish_service.py`: **4 failed, 5 passed**.
  * Both `…older_version_of_the_checks…` cases and the dry-run case failed with
    `assert <FileRefusalCode.QUALITY_REPORT_MISSING> == 'QUALITY_REPORT_OUTDATED'`. The exception is the
    `only_its_version_older` case: that report still reads, so the old gate let it through, and it
    failed at the offline world's `AssertionError: publish asked for a bucket: the file was let through
    the gate`. That is the bug the forbidden entry names.
  * The warned-file test failed with `assert [] == [(cite-present, WARN, 1, 'the card has no short
    cite'), …]`.
  * The five `stays_missing` cases passed, as they must: they describe the old behaviour that is kept.
* `test_files.py`: **3 failed**.
  * The CLI older-report test failed with `'QUALITY_REPORT_MISSING' == 'QUALITY_REPORT_OUTDATED'`.
  * The new dry-run warning test and t15's real-publish test showed only the caption below the table.

### Mutants

There are 17 mutants: the PM's six, plus variants. Each was applied to the committed source, then the
core publish file and `test_files.py -k "publish or older or warned or absent_or_unreadable or report"`
were run (58 tests, `-n 4`, about 4 s), and the file was restored with `git checkout HEAD --`. No test
here uses Hypothesis, so agreement 8's fresh database does not apply. Every mutant was caught; `git status` was clean afterwards.

| Mutant | Caught by |
|---|---|
| 1. An older report called missing (the OUTDATED branch off) | 4 tests: both core older cases, the dry-run case, the CLI test |
| 1b. An older report given `QUALITY_REPORT_MISSING`'s code | The same 4 |
| 2. An absent report called older | 3: `…no_quality_report_is_refused…`, `…dry_run_still_refuses…`, `stays_missing[absent]` |
| 2b. A current-version report that does not read called older | 4: `stays_missing[no-checker-version, checker-version-not-text, current-version-unreadable]` and the existing `…not_one_is_missing…` |
| 2c. A report that is not JSON called older | `stays_missing[not-json]` |
| 2d. Every report naming any version called older (no comparison) | 36 tests: every file that reaches the gate's later steps |
| 3. Only the older version named | 3: both core older cases, the CLI test |
| 3b. Only this build's version named | The same 3 |
| 4. An older report published when it still reads (the version asked only after the model fails) | `…older_version…[only_its_version_older]`, at the offline world's assertion that publish asked for a bucket. That is a deliberate assertion, not a crash. |
| 5. The warning lines dropped from the table | 2: the CLI dry-run warning test, t15's publish test |
| 5b. Warnings not carried by the service | 3: the core warned test, both CLI tests |
| 5c. Warnings dropped from a dry run's outcome | 2: the core warned test, the CLI dry-run test |
| 5d. Warnings dropped from an upload's outcome | t15's real publish test (moto) |
| 5e. The check's name printed instead of its finding line | 2: both CLI tests |
| 5f. Warnings dropped from `--json` | The CLI dry-run test |
| 6. The report's path in the refusal | 3: both core older cases, the CLI test |
| 6b. The report's file name in the refusal | The same 3 |

### Checks before the report

* `uv run scripts/affected_tests.py` chose **88 of 627 test files**. `--run`, bounded with
  `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run`, was **stopped at
  its 115-second limit at 41%**, with every result shown up to then a pass (load average 8.5). Under
  agreement 10 the full affected set is left to the pull request's `ci` check, which runs the same
  selection. Not handed to the operator.
* Within the limit, the changed areas and the always-run list:
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n 6 -m "not slow and not
  live" tests/architecture tests/specs packages/debate_cli/tests/test_app.py
  packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py
  packages/debate_core/tests/application/test_file_publish_service.py
  packages/debate_core/tests/application/test_file_build_service.py
  packages/debate_cli/tests/commands/test_files.py
  packages/debate_cli/tests/test_files_check_findings_presenter.py tests/smoke/test_files_publish.py
  tests/smoke/test_files_cli.py tests/docs/test_check_links.py` → **549 passed in 45.61s**.
* `uv run ruff format --check .` → `1735 files already formatted`.
* `uv run ruff check .` → `All checks passed!`.
* `uv run pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations`.
* `uv run lint-imports` → `Contracts: 20 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 549 files, 41 epics, 486 tasks, 22 releases`.
* `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 70 … within 25 statements`.
* `scripts/docs_index.py --check-descriptions` → `All 61 indexed documents … have a description`.
* `scripts/check_links.py` → `OK: 3233 relative links and anchors in 509 Markdown files`.
* `scripts/check_command_blocks.py` → `OK: no # comments in 635 shell code blocks`.

## Files changed

* `packages/debate_core/src/debate_core/application/file_publish_service.py`:
  * the new code `QUALITY_REPORT_OUTDATED`;
  * `_read_report` returns the report, or the checker version it records when that is not
    `CHECKER_VERSION`, read from the raw JSON before the model;
  * the refusal itself;
  * `warnings` (the re-check's WARN results) on `FilePlan` and `PublishOutcome`;
  * the module docstring's gate steps 1 and 4.
* `packages/debate_cli/src/debate_cli/presenters/files_presenter.py`: the publish table's lines below
  (`_warning_lines`), `warnings` in each file's `--json`, and the module docstring.
* `packages/debate_core/tests/application/test_file_publish_service.py`: an `offline_world` fixture
  (no bucket, not even moto's, and asking for one fails the test), and the nine new tests above.
* `packages/debate_cli/tests/commands/test_files.py`: two new dry-run tests (no moto) and one more
  assertion in t15's publish test.
* `docs/data/built-file-metadata.md`: the gate's step 1 (the new code) and step 4 (the warning lines).
* `plan_specs/…/t16-publish-names-an-older-quality-report.yaml`:
  * the PM amendment paragraph, dated as asked;
  * `ac2`;
  * a second node criterion for the CLI tests;
  * the phase.

## Deviations from the spec

* **The codes are documented in `docs/data/built-file-metadata.md`, not under `docs/runbooks/`.** The
  spec's packages name `docs/runbooks`, and the PM asked to "say where the codes are documented and
  update that line". No runbook names a `files publish` refusal code (`git grep QUALITY_REPORT --
  docs/runbooks` finds nothing). The list of the gate's codes is in `docs/data/built-file-metadata.md`,
  under "What is published, and what is refused", and in the service's module docstring. Both are
  updated. `docs/data` is not in the spec's `constraints.packages`. I did not add it; the PM may want
  to swap `docs/runbooks` for `docs/data`.
* **A second criterion on the plan node.** The PM asked for `ac2` on the Goal. Its tests live in
  `test_files.py`, which the node's command does not run. I added a `test_passes` criterion running
  `test_files.py -k publish`.

## Decisions and assumptions

* **"Older" is "another version than this build's".** Versions are date-stamped strings
  (`2026.10.31-file-checks-3`) with no ordering contract. A report from a newer build is unlikely, but
  it is equally not this build's verdict. So the code is `QUALITY_REPORT_OUTDATED`, as the PM
  suggested, and its message says only what is true either way: `its quality report was written by
  version X of the checks, and this build runs Y`.
* **An older report is refused even when it still reads.** Today every older report fails to read,
  because t15 added a check and a report must summarise every check. The next bump that adds no check
  would leave older reports readable. The old gate would then have published them on the strength of
  the re-check. The forbidden entry ("Publishing a file whose report is older (it stays a refusal)")
  rules that out, so the version is read from the raw JSON before the model is tried. Mutant 4 is this
  case.
* **Where MISSING ends.** A report is OUTDATED only when its JSON has a non-empty text `checker_version`
  that is not this build's. These stay `QUALITY_REPORT_MISSING`, with the message unchanged:
  * no file;
  * not JSON;
  * no version;
  * a version that is not text;
  * this version, but a report that does not read.
* **No path in the message; the hint is MISSING's.** The message names neither the report's path nor
  its file name: the CLI line already starts with the `.docx` name. The hint is MISSING's exactly, as
  the PM asked ("with the same hint"): ``Check it with `debate-research files check <docx as typed>`,
  then publish again.`` That is the command the coach runs, and it holds the path the coach typed, as
  every publish hint has since t05. I read the forbidden "a path … in a refusal" as the refusal's
  message, because the PM asked for the same hint in the same sentence. If the hint must hold no path
  either, every publish hint changes, which is outside this task, so I left them.
* **Precedence.** OUTDATED is asked before STALE: a report from older checks for other bytes is
  OUTDATED. `files check` fixes both.
* **How the warnings read beside t10's refusal.** The same sidecar WARN reads differently depending on
  whether the file is let through.
  * For a file let through, the table's caption still names the warned checks (`1 WOULD_PUBLISH.
    Warned, not blocked: policy-nhi-politics-da-answers: sidecar`; existing tests pin it). Below the
    table, publish now prints:

    ```text
    Warned, not blocked in policy-nhi-politics-da-answers:
      WARN sidecar: the sidecar was written under style profile 2026.11.02-verbatim-2; the files were re-read with 2026.09.20-verbatim-1, and a card the two profiles read differently fails evidence-identity
    ```

  * For a refused file, nothing is printed below the table. Its `QUALITY_FAILED` refusal carries the
    sidecar WARN in its own message, as t10 made it: `[QUALITY_FAILED] the file does not PASS, checked
    again now: evidence-identity failed; the sidecar was written under style profile … (failing:
    evidence-identity)`.
  * So the cause is on screen once either way. It is in the refusal when the file is stopped, and in
    `files check`'s line when it is not.
  * The warnings come from publish's own re-check, the report that is uploaded, not from the report on
    disk.
* **`--json` gains `warnings` per file**, each shaped as `.quality.json`'s `results` entries (as `files
  check`'s `quality.findings`). No test or smoke check pins the publish file payload's key set (checked
  with `git grep warned_checks` over `tests/smoke` and the CLI tests).
* **Tests without moto where publish's real path does not need it.** The new core tests use an
  `offline_world` with no bucket. A refusal never builds a bucket client, and a file wrongly let
  through fails the test at the bucket factory. The new CLI tests are dry runs. The one real upload
  with warnings is t15's existing moto test, which gained one assertion. That test is the only one
  that catches mutant 5d (warnings dropped from an upload's outcome).
* `origin/dev` was compared at the start (only this task's start commit differs). I did not fetch
  again before the report.

## Operator follow-ups

None. The affected set, over two minutes here, is left to the pull request's `ci` check (agreement
10).

## Follow-up work

* The hint of every `files publish` refusal names the `.docx` path as typed. If the PM reads the
  forbidden "a path … in a refusal" as covering hints, every hint should change to name the file and
  not its path. That would be a small E33 task.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The coach now sees why a file is refused and what each warning says, without running another command.
1. **ac1 passes.**
   * Red over a skeleton: 4 + 3 failed, all at assertions. The `only_its_version_older` case failed
     at the offline world's bucket assertion, which is exactly the hole the forbidden entry names.
     The five `stays_missing` cases passed at red because they pin behaviour that is kept.
   * Green: the node criterion passes (42), and so does the added CLI criterion (10).
   * All 17 mutants are caught, the PM's six among them. Mutant 4, an older report published when it
     still reads, is the one that matters most.
2. **ac2 passes.** A warned file's finding lines are printed as `files check` prints them and are
   carried in `--json`. t10's refusal test is unchanged.
3. **The hint's path: accepted as built, and the follow-up is not filed.** The forbidden entry is
   about what the refusal reports, not about echoing back the command the coach just typed in their
   own terminal. The hint holds the `.docx` path exactly as typed, as every publish hint has since
   t05, and nothing is logged or uploaded. The message itself names no path, and mutants 6 and 6b
   hold that.
4. **Deviations accepted:**
   * The codes are documented in `docs/data/built-file-metadata.md`, where the gate's codes already
     live. The PM's next batch adds `docs/data` to the spec's packages.
   * The second node criterion for the CLI tests.
5. **Decisions accepted:**
   * "Older" means "another version than this build's", with a message that is true either way;
   * the version is read from the raw JSON before the model, so a report that still reads is refused
     too;
   * where MISSING ends (no file, not JSON, no version, a non-text version, or this version but
     unreadable);
   * OUTDATED is checked before STALE;
   * the warnings come from publish's own re-check, the report that is uploaded;
   * `warnings` per file in `--json`, shaped like `.quality.json`'s results;
   * the offline world, with no bucket at all, for refusals. The one real upload with warnings
     stays t15's moto test, which catches 5d.
6. **Closing checks:** the affected set (88 files) stopped at 41% at its limit with every result so
   far a pass, and is left to the PR's `ci` under agreement 10. The changed areas and the always-run
   list (549), ruff, pyright, lint-imports, thin handlers, the doc checks and the specs are clean.
7. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows. A coach holding
   a file built before checks-3 now sees `QUALITY_REPORT_OUTDATED` and runs `files check`, as the
   hint says.
