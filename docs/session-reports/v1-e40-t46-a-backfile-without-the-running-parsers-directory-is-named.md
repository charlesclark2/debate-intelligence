# Session report: v1-e40-t46-a-backfile-without-the-running-parsers-directory-is-named

| | |
|---|---|
| Task | `v1-e40-t46-a-backfile-without-the-running-parsers-directory-is-named` — A backfile with no directory at the running parser version is named |
| Spec | [`plan_specs/v1/e40-cloud-caselist-run/t46-a-backfile-without-the-running-parsers-directory-is-named.yaml`](../../plan_specs/v1/e40-cloud-caselist-run/t46-a-backfile-without-the-running-parsers-directory-is-named.yaml) |
| Epic / release | `v1-e40-cloud-caselist-run` / `v1.8` |
| Branch | `task/v1-e40-t46-a-backfile-without-the-running-parsers-directory-is-named` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`caselist runs --remote` now names each backfile whose parsed store in the bucket has no directory
at the reference parser version. Each one is printed with every parser version it does hold, newest
first, or as not imported. When none is named, one line says all N are at the version. The rule is in
a new module, `debate_core.application.caselist.backfile_parser_versions`. The backfiles come from
`caselist.backfile_caselists`, the setting `caselist backfile-import` and the pull's refusal read.
The reference is the parser version the newest non-failed run shown recorded restoring the parsed
store at (`details.bucket_run.restore.parsed_version`, which a bucket-mode run writes from its own
build), or else this build's `DOCX_PARSER_VERSION`. The line says which was used. `--json` gains one
top-level object, `backfile_parser_versions` (`null` without `--remote`), and every existing field is
unchanged. The check is informational: the exit status, the verdicts and the overdue warning are as
they were, and a listing the bucket refuses is reported in a sentence, not as an exit status. Tests
on synthetic stores were shown failing first. The only open item is the operator's live check after
tonight's hspolicy25 rebuild. It is a follow-up, not an acceptance criterion, so the Goal is
`Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-backfile-without-the-running-parsers-d` (Backfile parser version named) | Done | Core rule and tests in commit `4856738`, CLI wiring and tests in `213267c` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: "Each backfile with no directory at the running parser version is named with the version it holds, by tests on synthetic stores shown failing first." | PASS | Red, then green, on the two test files below. See "Red runs". |
| Node: "Backfile parser version named tests pass" (`uv run pytest packages/debate_core/tests packages/debate_cli/tests -k backfile`) | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests packages/debate_cli/tests -k backfile -q -p no:cacheprovider` → `120 passed in 74.86s` |

### The tests

* `packages/debate_core/tests/application/caselist/test_backfile_parser_versions.py` (19 tests)
  uses an in-memory `VersionDirectoryPlace` defined in the test. It covers each case the PM listed:
  * at the reference version only: not named;
  * at an older version only: named, with it;
  * holding both: not named;
  * several older versions, given out of order and with a `_reparse-2` generation: named, newest
    first, each parser version once;
  * never imported: named as not imported.

  It also covers: a reparse generation of the reference counts as at the reference; a newer-only
  backfile is named; the order follows the setting; only the backfiles' own prefixes are listed,
  never `caselists()`; no backfiles means no listing and no line; the lines and the JSON object are
  written out whole; and how the reference is picked (no runs means this build; the newest
  non-failed run that recorded a version wins; failed runs, runs with no recorded restore version
  and runs with no details are passed over; run order does not matter).
* `packages/debate_cli/tests/bucket_mode/test_backfile_parser_versions_in_caselist_runs.py`
  (7 tests) goes through the real app and composition root over moto's in-memory S3 (the
  `bucket_mode` world). It plants version directories and one run record with details. It covers:
  hspolicy25's state of 2026-11-12 as `--json` and as table lines; several older versions newest
  first; the all-at-version line; a reference taken from the newest run and named on the line; exit
  status, verdicts, overdue and every other `data` field equal with and without backfiles named;
  without `--remote` the key is `null` and nothing is printed; a refused listing exits 0, gives
  `null` and prints a sentence.

Every expected value is written by hand from the rulings. The CLI tests take `BUILD` from
`DOCX_PARSER_VERSION`, so they survive a parser bump; the older versions are hand-written labels.

### Red runs

| Run | Command | Result |
|---|---|---|
| Core tests vs a names-nothing skeleton (reference always this build, no lines, minimal JSON) | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -q --tb=line -p no:cacheprovider packages/debate_core/tests/application/caselist/test_backfile_parser_versions.py` | `14 failed, 5 passed in 0.64s`. All 14 are AssertionErrors. The 5 that pass are the three "not named" cases, "no backfiles says nothing" and "no run means this build", which any do-nothing skeleton satisfies |
| The three "not named" tests vs a names-everything skeleton | same file, `-k "not_named or second_generation_of_the_reference or no_backfiles"` | `3 failed, 1 passed`. The pass is "no backfiles", which lists nothing in either skeleton |
| CLI tests vs the pre-task `caselist_runs.py` (`git show HEAD:…` at the time, i.e. dev's) | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -n 0 -q --tb=line -p no:cacheprovider packages/debate_cli/tests/bucket_mode/test_backfile_parser_versions_in_caselist_runs.py` | `7 failed in 2.63s`, every one `KeyError: 'backfile_parser_versions'` (the key is absent) |
| CLI tests vs the task's command over the names-nothing core skeleton | same | `6 failed, 1 passed in 3.91s`. Two fail at assertions (e.g. `assert {'backfiles_checked': 4} is None` for the refused listing) and four on the skeleton's missing JSON keys. The pass is "without `--remote`", the handler's own behaviour, which failed in the previous run |
| Green | both files | `26 passed in 3.95s` |

Each restore was checked: `cmp` against the saved copy for the command, and `git checkout HEAD --`
plus `git diff --quiet` for the core module.

### Before the report

| Check | Command | Result |
|---|---|---|
| Affected set | `uv run scripts/affected_tests.py` | `308 of 746 test files (41.3%) chosen in 20.6 s from 7 changed files`. Not run, see below |
| Always-run list, changed modules' tests, other `caselist runs --remote` tests | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q -p no:cacheprovider -m "not slow and not live" tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_cli/tests/commands/test_caselist_runs.py packages/debate_core/tests/application/caselist/test_version_retention.py packages/debate_core/tests/application/caselist/test_version_retention_lifecycle.py packages/debate_core/tests/application/caselist/test_backfile_parser_versions.py packages/debate_cli/tests/test_retryable_store_failures.py packages/debate_cli/tests/test_missing_profile_and_missing_grant.py packages/debate_cli/tests/test_pull_refused_before_the_bucket_is_built.py` | `503 passed in 33.81s` |
| `packages/debate_cli/tests/bucket_mode/` (the new CLI test's directory) | the same, over the directory | The whole directory hit the 115 s limit at about 97% with no failure printed. Run again in two halves of 9 files: `163 passed in 82.70s` and `124 passed in 42.71s` |
| Format | `uv run ruff format --check .` | `2068 files already formatted` |
| Lint | `uv run ruff check .` | `All checks passed!` |
| Types | `uv run pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` (27 s) |
| Import contracts | `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| Thin handlers | `uv run scripts/check_thin_handlers.py` | `OK: 74 CLI command and API route handlers within 25 statements` |
| Specs | `uv run scripts/validate_specs.py` | `OK: 669 files, 41 epics, 606 tasks, 22 releases` (warnings only, none about this task) |

**Why the affected set was not run.** It is 308 of 746 files. Two edits reach that far, and each
reaches about the same set alone (re-measured with the `version_retention.py` edit reverted: still
308):

* `caselist_runs.py` reaches every test that runs `caselist runs` through `debate_cli.app`;
* `version_retention.py` is imported by the root conftest (via `cassette_filing`) and by
  `exit_codes`.

41% of a roughly six-minute whole selection is past the two-minute line. Under working agreement 10
(PM ruling 2026-10-19) it goes to the pull request's `ci` check, which runs the same affected set. It
is not handed to the operator. In its place I ran the always-run list, the changed modules' test
directories and the other `caselist runs --remote` tests, all listed above.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist/backfile_parser_versions.py` (new):
  the rule. Picks the reference (`reference_version`), lists each backfile's version directories
  through `VersionDirectoryPlace` (`backfile_parser_versions`), and builds the lines and the JSON.
* `packages/debate_core/src/debate_core/application/caselist/version_retention.py`: two read-only
  properties, `place` and `parser_version`. With them the command reuses the bucket place that
  `caselist retire --bucket` already lists in (everyday profile) and this build's parser version,
  without a change to `debate_cli/container.py`.
* `packages/debate_cli/src/debate_cli/commands/caselist_runs.py`: under `--remote`, the check's lines
  go in `TableSpec.lines_below` and its object in `--json` as `backfile_parser_versions`. A
  `StoreAccessDenied` from the listing becomes `null` and one sentence. The module docstring gains a
  section.
* `packages/debate_core/tests/application/caselist/test_backfile_parser_versions.py`,
  `packages/debate_cli/tests/bucket_mode/test_backfile_parser_versions_in_caselist_runs.py` (new):
  the tests above.
* The task spec: Goal phase `Succeeded`.

## Deviations from the spec

* **No smoke check.** Working agreement 5 asks a task that changes a user-facing surface to update
  its smoke checks (`tests/smoke/test_caselist_runs.py`). This task's `constraints.packages` do not
  include `tests/`, and its plan has no smoke node, so none was added. Filed under Follow-up work.
* **The node criterion was run as `.venv/bin/python -m pytest`**, under `scripts/hard_stop.py 115`,
  rather than `uv run pytest`: same interpreter and arguments, without uv's sync (agreement 10's form).

## Decisions and assumptions

* **"The newest completed run"** is taken as the newest run *shown* (the `--last N` window, default
  5) whose record did not fail (`SyncRunRecord.succeeded`: `completed`, `nothing_new`,
  `cap_deferred`, `publish_pending`, `incomplete`) and whose details record
  `bucket_run.restore.parsed_version`. A failed run is passed over in case a broken image is being
  rolled back. `nothing_new` counts, since a weekly run with nothing new still restored at its build's
  version. A `--publish-pending` run, a local-mode run and a run from a build before `v1-e40-t04`
  record no restore version and are passed over. With none of these in the window, the reference is
  this build's `DOCX_PARSER_VERSION`. No field was added to the run record or its details (ruling 2).
* **"Holds the reference version"** means a directory whose parser version, with any `_reparse-N`
  generation stripped (`parse_version_directory`), equals the reference. The versions listed for a
  named backfile are parser versions, each once, sorted newest first by the same string order
  `caselist retire` uses (date first). A backfile with only a *newer* directory is named too. The
  ruling's rule is literal, and a newer directory still means it is not at the version the run uses.
* **No backfiles configured** (the `test` profile, an installation without backfiles): no line, and
  no listing is made. `--json` still gives the object with `backfiles_checked: 0` and `named: []`.
  "All 0 backfile(s)" says nothing worth reading.
* **Without `--remote`** the object is `null` and nothing is listed (ruling 1: the bucket is the
  home). The Mac's own parsed store has been stale since the cutover.
* **A refused listing** (`StoreAccessDenied`) is said ("The backfiles' parser versions were not
  checked: not allowed to ListObjectsV2 s3://…/parsed/<slug>/.") and leaves the exit status alone
  (ruling 5). Any other store error, such as an expired session, propagates as it does for the rest
  of the command. The run records were already read with the same profile, so a session that expires
  in between is the only way to get one.
* **Permission (ruling 6).** The new read is `s3:ListBucket` on the evidence bucket with prefix
  `parsed/<backfile>/` and delimiter `/`, signed with the everyday profile
  (`storage.s3.aws_profile`, `debate-dev-evidence`). `infrastructure/modules/evidence_bucket/operator_access.tf`'s
  `ListDocumentedEvidencePrefixes` statement grants `s3:ListBucket` for `s3:prefix` `parsed/` and
  `parsed/*` (`evidence_prefixes` in `main.tf`). `caselist retire --bucket` already makes the same
  call with the same profile. No IAM or Terraform change is needed, and none was made.
* **Wording.** House plural style `backfile(s)`. A run-sourced reference reads
  `parser <version> (recorded by run <run id>)`, beside the PM's `parser <version> (this build)`.

## Operator follow-ups

**Operator command** (expected runtime under a minute)

Run this only after tonight's hspolicy25 rebuild (the ECS task started 00:53 Chicago) has finished.
Where: your Mac, from the home folder, on an installed build that carries this task (after it merges
and the build is installed). The first line opens the everyday dev session if it has expired.

```bash
cd "$HOME"
aws sso login --profile debate-dev-evidence
env DEBATE_ENV=dev debate-research caselist runs --remote --last 3
```

Success looks like this: below the runs table, exactly one line reading
`All 4 backfile(s) are at parser 2026.11.03-docx-9 (recorded by run <the newest cloud run's id>).`
The bracket may instead read `(this build)` if none of the three newest runs restored a parsed store.
No backfile is named. If hspolicy25 is still named with `holds 2026.10.27-docx-7`, the rebuild has not
published its docx-9 directory yet. If the line reads `The backfiles' parser versions were not
checked: ...`, paste it back: that is the permission the decision above says is already granted.

## Follow-up work

* **Runbook line** (`docs/runbooks/caselist-cloud-run.md`, outside this task's packages). Under
  Step 8's "Its record reads as a Mac run's does" and the parse-owed section, add a sentence: after a
  parser bump, `caselist runs --remote` names below its table each backfile with no directory at the
  run's parser version, and the cure is a `caselist backfile-import` of that backfile in the cloud
  (v1-e40-t09's procedure). E40.
* **Smoke check** for `caselist runs --remote` with a backfile behind (`tests/smoke/`, outside this
  task's packages): the installed build's `--json` carries `backfile_parser_versions`. E40 or E41.
* **Retiring hspolicy25's docx-7 directory** after the rebuild is `caselist retire --bucket`'s job.
  This check does not name hspolicy25 while the docx-9 directory exists, so it says nothing either way.
* **Doctor vs runs.** I think `caselist runs --remote` is the better home, and did not build the
  doctor variant. `doctor` checks this machine's setup and makes no bucket listing per caselist,
  while this is a fact about the bucket's state that the operator reads after every weekly run.
* **The reference window is `--last N`.** With five failed runs in a row the reference falls back to
  this build's version, which is right when the Mac's build matches the image and may differ when it
  does not. The line always says which was used. Reading further back would cost more bucket reads.
  I did not do that; the PM may want it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
