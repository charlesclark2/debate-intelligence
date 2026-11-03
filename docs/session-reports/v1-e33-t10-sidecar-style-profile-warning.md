# Session report: v1-e33-t10-sidecar-style-profile-warning

| | |
|---|---|
| Task | `v1-e33-t10-sidecar-style-profile-warning` — files check and files publish warn when a built file's style profile is not the running one |
| Spec | [`plan_specs/v1/e33-file-builder/t10-sidecar-style-profile-warning.yaml`](../../plan_specs/v1/e33-file-builder/t10-sidecar-style-profile-warning.yaml) |
| Epic / release | `v1-e33-file-builder` / `v1.2` |
| Branch | `task/v1-e33-t10-sidecar-style-profile-warning` |
| Session status | COMPLETE |

## Summary

`check_sidecar` now adds one WARN beside the parser one when the sidecar's `style_profile_version`
is not the running profile's. The WARN names both profiles and says once that a card the two
profiles read differently fails `evidence-identity`:

```text
WARN sidecar: the sidecar was written under style profile 2026.11.02-verbatim-2; the files were re-read with 2026.09.20-verbatim-1, and a card the two profiles read differently fails evidence-identity
```

The same profile gives no warning. `files check` prints the WARN as t12 prints any finding, as the
first line after the table and above the per-card `evidence-identity` lines it explains. It is in
`--json`'s `quality.findings`. `files publish`'s re-check gets the WARN through the same
`FileQualityService.check_file`. A file that still passes lists `sidecar` among its warned checks.
A file the re-check refuses (`QUALITY_FAILED`) now has the sidecar check's warnings in its refusal
message, so the cause is on screen next to `evidence-identity failed`. Of everything here, the PM
should look first at that last change, which is under Decisions. It is a WARN only and never a
refusal. Tests were shown failing first, and nine mutants were each caught at the intended
assertion. The affected set takes about 4 minutes, so it is left to the pull request's `ci`
(agreement 10).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `sidecar-profile-warning` (Sidecar style profile warning) | Done | Red at `55c2ee3` (tests + a signature-only skeleton), green at `17ba773`; one test-argument correction at `5573e51`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a sidecar with another style profile gives one WARN naming both, in `files check` and `files publish`'s re-check; the same profile gives none; tests shown failing first | PASS | Red, at `55c2ee3`, where `check_sidecar` took the two profile versions and did nothing with them: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -p no:randomly -n 0 -q --tb=line packages/debate_core/tests/evidence/file_checks/test_structure.py packages/debate_cli/tests/commands/test_files.py -k "sidecar or profile"` → `4 failed, 20 passed, 58 deselected`: the two new structure tests (`assert [] == [(WARN, None, '…')]`), the `files check` CLI test (`assert [] == ['Failures and warnings:', 'WARN sidecar: …']`) and the `files publish` CLI test (`assert ('WOULD_PUBLISH', []) == ('WOULD_PUBLISH', ['sidecar'])`), each at an assertion. The test of a sidecar with no `style_profile_version` passed at red, because it pins behaviour that already existed (Decisions). Green, at `17ba773` / `5573e51`: the same command → `24 passed`; the changed areas below → `820 passed`. |
| Node: File check tests pass (`uv run pytest packages/debate_core/tests/evidence/file_checks/test_structure.py`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 uv run pytest packages/debate_core/tests/evidence/file_checks/test_structure.py` → `48 passed in 2.15s`. |

### The tests

* `packages/debate_core/tests/evidence/file_checks/test_structure.py` (the node's file):
  * `test_a_sidecar_from_another_style_profile_is_one_warning_naming_both_profiles` checks for exactly one WARN, with its message written by hand.
  * `test_a_sidecar_from_another_parser_and_another_profile_warns_of_each_parser_first` checks for both WARNs, the parser's first.
  * `test_a_sidecar_that_cannot_be_read_names_no_profile` checks that `problems=("style_profile_version: Field required",)` gives that FAIL and nothing else.
  * The four existing sidecar tests now pass the running profile as the sidecar's. The unreadable-sidecar test passes `None`, as an unreadable sidecar has no profile. They pin "the same profile gives none".
* `packages/debate_cli/tests/commands/test_files.py`, over the policy example built by the CLI, with its sidecar's JSON rewritten and its `.docx` left as built:
  * `test_files_check_warns_once_of_a_sidecar_from_another_style_profile_naming_both`: before the rewrite, `findings == []`. After it, exit 0, `PASS`, and the lines after the table are exactly `Failures and warnings:` and the WARN. `--json`'s findings hold that one WARN.
  * `test_files_check_fails_a_sidecar_with_no_style_profile_as_not_valid_and_names_no_profile` checks that a sidecar without the key fails with `the sidecar is not valid: style_profile_version: Field required`, and that no finding mentions a style profile.
  * `test_files_publish_re_check_warns_of_another_style_profile_and_its_refusal_says_so` uses `--dry-run`, so no bucket client is built and moto is not used. The quality report beside the file is `files build`'s, from before the rewrite, so the warning can only come from publish's re-check. The file is `WOULD_PUBLISH` with `warned_checks == ["sidecar"]`. Then card 1's sidecar entry is made to end one paragraph later, as another profile might have bounded it. The result is `QUALITY_FAILED` with `failing_checks == ["evidence-identity"]`, and the WARN text appears in the refusal message, the envelope's message and the stderr panel.

### Mutants (agreement 8; each run with a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`)

Each mutant was applied to the committed code at `5573e51`. The structure test file and the three
new CLI tests were run with `-n 0 -p no:randomly`, and the file was restored with
`git checkout HEAD --`. The tree was clean afterwards. Every catch below is an `AssertionError` at
the line named, not an error before or outside the check.

| Mutant | Caught | By (first failing assertion) |
|---|---|---|
| 1. A warning on the same profile (`if sidecar_style_profile_version is not None:`) | Yes, 4 tests | `test_structure.py:81` (the valid sidecar is no longer PASS alone), `:116`, `:134`; `test_files.py:964` (`findings == []` before the rewrite) |
| 2. No warning on another profile (`if False:`) | Yes, 4 tests | `test_structure.py:150`, `:164`; `test_files.py:970` (check), `:1024` (publish `warned_checks`) |
| 3a. Only the running profile named (the sidecar's replaced by the running one) | Yes, 4 tests | `test_structure.py:150`, `:164`; `test_files.py:970`, `:1036` |
| 3b. Only the sidecar's profile named | Yes, 4 tests | the same four lines |
| 4a. Publish skips the re-check (`fresh = report`, the stored report) | Yes | `test_files.py:1024`: `('WOULD_PUBLISH', []) == ('WOULD_PUBLISH', ['sidecar'])` |
| 4b. Publish's warned checks read from the stored report, not the re-check | Yes | `test_files.py:1024` |
| 4c. Publish's refusal drops the sidecar's warnings | Yes | `test_files.py:1036`: the WARN text not in the refusal message |
| 4d. The service passes no sidecar profile to `check_sidecar` | Yes, 2 tests | `test_files.py:970` (check), `:1024` (publish) |
| 5. The warning made a refusal (`CheckStatus.FAIL`) | Yes, 4 tests | `test_structure.py:150`, `:164`; `test_files.py:969` (check exits 1, not 0) and the publish test's exit code |

### Before the report

* **Affected set:** `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run`
  selected 91 files. The 115-second limit stopped it at 45% (exit 124; load average about 6), so the
  whole set needs about 4 minutes. Under agreement 10 it is left to the pull request's `ci` check,
  which runs the same selection, and was not handed to the operator.
* **Within the limit, the test directories of what changed, the files smoke checks and the always-run list:**
  `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -n auto -m "not slow and not live" packages/debate_core/tests/evidence/file_checks packages/debate_core/tests/application/test_file_*.py packages/debate_cli/tests/commands/test_files.py packages/debate_cli/tests/test_files_*.py tests/smoke/test_files_cli.py tests/smoke/test_files_publish.py tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py`
  → `820 passed in 36.28s`, exit 0 in 38 s.
* `uv run --frozen ruff format --check .` → `1726 files already formatted`; `uv run --frozen ruff check .` → `All checks passed!`
* `uv run --frozen pyright packages/debate_core packages/debate_cli` → `0 errors, 0 warnings, 0 informations`
* `uv run --frozen lint-imports` → `Contracts: 20 kept, 0 broken.`; `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 69 CLI command and API route handlers within 25 statements`
* `uv run scripts/validate_specs.py` → `OK: 545 files, 41 epics, 482 tasks, 22 releases`
* The spec on `origin/dev` differs from this branch's only by `status.phase`, so there was no PM amendment to take in.

## Files changed

* `packages/debate_core/src/debate_core/evidence/file_checks/structure.py`: `check_sidecar` takes `sidecar_style_profile_version` and `style_profile_version` and adds the WARN after the parser one. Its docstring says why the profile matters and how the WARN reads beside t12's lines.
* `packages/debate_core/src/debate_core/application/file_quality_service.py`: passes the sidecar's profile and the running parser's profile (`self._parser.profile_version`, the one the report already records as `style_profile_version`).
* `packages/debate_core/src/debate_core/application/file_publish_service.py`: `_quality_refusal` adds the sidecar check's WARN messages to the `QUALITY_FAILED` message.
* `packages/debate_core/tests/evidence/file_checks/test_structure.py`, `packages/debate_cli/tests/commands/test_files.py`: the tests above.
* `plan_specs/v1/e33-file-builder/t10-sidecar-style-profile-warning.yaml`: Goal set to `Succeeded`.

## Deviations from the spec

None.

## Decisions and assumptions

* **The wording follows the parser warning.** The first half matches the parser warning ("the sidecar was written under … ; the files were re-read with …"). The second half says once that a card the two profiles read differently fails `evidence-identity`, as the PM allowed. The `sidecar` check comes first in the report, so in `files check` this WARN is printed above t12's per-card lines. Those lines (`report.finding_line`) are unchanged, and the identity check's own messages are unchanged too.
* **A sidecar with no `style_profile_version` does not exist in practice, and it FAILs, not WARNs.** The field has been required on `FileProvenanceManifest` since the first sidecar (`v1-e33-t02`, `29f074d`, found with `git log -S`), and every writer has written it. So no file built before t09 lacks it. A sidecar without it does not read as a sidecar, and `files check` fails it as `the sidecar is not valid: style_profile_version: Field required`, the same FAIL as for any other missing field. The checks that need a sidecar then fail with "not checked without a valid sidecar", and no profile is named. That behaviour existed before this task and is now pinned by a structure test and a CLI test. A file in that state is rebuilt, which `files publish` would require anyway.
* **The publish refusal carries the sidecar check's warnings, including the parser one.** Publish shows only check names for warned files (`Warned, not blocked: <slug>: sidecar`) and only failing check names for refused ones. Without a change, the coach would see `evidence-identity failed` and no cause, the symptom this task is meant to remove. The smallest change that puts the cause on screen was to add every WARN of the `sidecar` check to `_quality_refusal`'s message. That message is used for the stored report (`as its quality report records it`) and for the re-check (`checked again now`). A sidecar from another parser is warned of the same way and causes the same identity failures, so it is included. The PM may want to narrow that to the profile WARN only. The existing tests of the message (`test_file_publish_service.py`) check substrings and still pass.
* **No new field on the quality report.** `FileQualityReport` records `sidecar_parser_version` but not the sidecar's profile. A matching `sidecar_style_profile_version` would change `.quality.json`'s shape, which published files carry. The spec asks only for the WARN, and the WARN names both profiles, so I did not add the field.
* **The synthetic built file.** "Another style profile" is the policy example built under the running profile, with its sidecar's `style_profile_version` rewritten to `2026.11.02-verbatim-2` (t09's test value). The real identity failure from another profile, a card bounded differently, is made by moving card 1's `last_element_index` one paragraph later. The CLI tests use no network, AWS or moto. The publish test is a dry run, and `as_dev`'s `testing` credentials are never used.

## Operator follow-ups

None. The affected set (about 4 minutes) is the pull request's `ci` check's, under agreement 10.

## Follow-up work

* When `files publish` publishes a file with warnings, it names only the warned checks (`Warned, not blocked: <slug>: sidecar`), not their messages. For a file built under another profile whose cards still pass, the coach therefore sees `sidecar` and has to run `files check` to learn which profiles. Publish could print t12's finding lines for warned files, as `files check` does. That would be a small task in E33 if the PM wants it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

The cause of the identity failures is now on screen, which was the point.
1. **ac1 passes.**
   * Red on a signature-only skeleton: 4 failed, all at assertions. The no-profile test passed at
     red because it pins behaviour that already existed, and the report says so.
   * Green: 24, then 820 over the changed areas. The node criterion passes (48).
   * All nine mutants are caught at the intended assertions, the PM's five among them (3 and 4 each
     in several forms).
2. **The publish refusal carrying the sidecar's warnings: accepted, parser warning included.**
   * A sidecar from another parser causes the same identity failures and leaves the coach with the
     same blank, so narrowing it to the profile warning would only hide a cause.
   * The PM read `_quality_refusal`: it adds only the `sidecar` check's WARN messages, which name
     versions and never a path or a card.
3. **Decisions accepted:**
   * the wording, which mirrors the parser warning and gives the identity explanation once;
   * a sidecar with no profile stays the existing FAIL (the field has been required since t02), now
     pinned by two tests;
   * no new field on the quality report, since `.quality.json` travels with published files;
   * the synthetic file made by rewriting the sidecar and moving one card's bound;
   * the publish test as a dry run, with no moto.
4. **Follow-up (publish printing the warned checks' finding lines):** folded into `v1-e33-t16`
   (publish names an older quality report) by the PM's next batch. It is the same service and the
   same reader.
5. **Closing checks:** the affected set (91 files, about 4 minutes) is left to the PR's `ci` under
   agreement 10. The changed areas, the files smoke checks and the always-run list (820), ruff,
   pyright, lint-imports, thin handlers and the specs are clean.
6. **Merge:** a plain `scripts/task pr` once `ci` is green. No operator step follows.
