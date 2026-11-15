# Session report: v1-e08-t18-auto-cut-report-names-per-run

| | |
|---|---|
| Task | `v1-e08-t18-auto-cut-report-names-per-run` — An auto-cut run's report does not replace the last run's in the same directory |
| Spec | [`plan_specs/v1/e08-research-workflows/t18-auto-cut-report-names-per-run.yaml`](../../plan_specs/v1/e08-research-workflows/t18-auto-cut-report-names-per-run.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t18-auto-cut-report-names-per-run` |
| Session status | BLOCKED: waiting for the PM's ruling on the report's name (proposal below) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

No code is changed yet. As the PM asked (2026-11-14), this session proposes first and stops for the
ruling: the proposal, the survey of every reader of the fixed name and the old-file answer are under
**Decisions and assumptions**. The Goal stays InProgress.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

* **`tests/integration/test_e2e_research.py` and `tests/integration/ACCEPTANCE.md` are outside
  `constraints.packages`** (`debate_cli, debate_core.application, packages/debate_cli/tests,
  docs/guides`) but read the fixed name, so the end-to-end tests would go red on dev's push run
  without the edit. Proposed: edit them (the path only) and add `tests/integration` to
  `constraints.packages`; waiting on the PM.
* `packages/debate_cli/README.md` is under `debate_cli`; read as in scope.

## Decisions and assumptions

### Proposal for the PM's ruling: `<bundle stem>.report.json`

**Recommended: name the report after the bundle, `<stem>.report.json`**, made the same way as the
manifest (`AutoCutOptions.manifest`, `<stem>.manifest.json`), in `AutoCutOptions.report`
(`packages/debate_cli/src/debate_cli/search_auto_cut.py:104`). Both commands build their files
through that one class, so one change covers `search --auto-cut` and `daily --auto-cut`:

| Command | Bundle | Manifest (unchanged) | Report today | Report proposed |
|---|---|---|---|---|
| `search --auto-cut N --output out/nhi.docx` | `out/nhi.docx` | `out/nhi.manifest.json` | `out/report.json` | `out/nhi.report.json` |
| `daily politics --date 2026-11-14 --auto-cut N` | `digests/politics-2026-11-14.docx` | `digests/politics-2026-11-14.manifest.json` | `digests/report.json` | `digests/politics-2026-11-14.report.json` |

Why this over `--report PATH`: no new option to learn or forget; each report sits and sorts with its
own bundle and manifest; `daily` (which has no `--output`) needs no option of its own; and the
bundle's name is already the user's choice of "which run is this". A `--report` option would still
default to some fixed name, so a coach who never passes it keeps the bug.

It does not collide with any other file beside a bundle: the quality reports are
`<file>.docx.quality.json` (`quality_report_names`), the digest `<preset>-<date>.md` or `.json`.

Where it lives: file names beside the bundle are the command line's surface, as the manifest's and
the digest's already are (`search_auto_cut.py`, `daily_presenter.digest_file_name`). No decision of
`debate_core`'s moves into `debate_cli`.

### Is daily's bundle name unique per day?

Per preset and date, yes: `<preset>-<date>.docx` (`daily._cut_options`), the date being `--date` or
the run's date in `daily.time_zone` (`DigestRequest.before_the_run`). Two presets on one day never
share it. Two runs of **one preset for one date** do (a rerun of `--date D`, a different `--window`
for the same date, or two runs with no `--date` in one local day). That is by design today: "Running a
date again writes its digest again", and the bundle and manifest are replaced with it. The report
inherits exactly that, so it stays paired with the digest and bundle it describes. The proposal does
not make one report per run on the same date; that would need a per-run part in the digest's name
too, which is outside this task.

`search` inherits the same rule from `--output`: two runs into one directory with different
`--output` names keep both reports; the same `--output` replaces its bundle, manifest and report
together, as it replaces the bundle and manifest today.

### Every reader of `report.json` by its fixed name

No code reads the report back: no command, the API, a worker or `verify` opens it. The `--json`
output's `auto_cut.files.report` carries the path, so its readers follow the new name unchanged. The
readers of the fixed name are tests and prose:

| Reader | Where | What it needs |
|---|---|---|
| search CLI tests | `packages/debate_cli/tests/test_search_command.py:1825, 1863, 1928, 2299, 2310` | read `<stem>.report.json`; the "Report:" line names it |
| daily CLI tests | `packages/debate_cli/tests/test_daily_command.py:1032, 1074` | read `politics-<date>.report.json` |
| presenter test | `packages/debate_cli/tests/test_presenters_configuration_gaps_named_with_their_cure.py:228` | a placeholder `Path`; nothing to change (a name only) |
| end-to-end tests (slow) | `tests/integration/test_e2e_research.py:172, 245` | read `<stem>.report.json` beside `out`. **Outside `constraints.packages`** (see Deviations) |
| acceptance table | `tests/integration/ACCEPTANCE.md:76` | say `<bundle>.report.json`. Outside `constraints.packages` too |
| smoke checks | `tests/smoke/test_search_smoke.py`, `tests/smoke/test_daily_smoke.py` | nothing: they read `--help` only. (`validate-dev.yml:245`'s `report.json` is the smoke run's own report, unrelated) |
| help and docstrings | `search.py:186` (`--output` help), `search.py:220`, `daily.py:29, 260`, `search_auto_cut.py:21-28, 168`, `batch_report_presenter.py:1-14, 66-76, 108, 132`, `daily_presenter.py:320` | name `<bundle>.report.json` |
| package README | `packages/debate_cli/README.md:720` (and the `search --auto-cut` section) | name it |
| guides | `docs/guides/`: none mentions `--auto-cut` or the report today | `docs/guides/daily-digests.md` gains a short `--auto-cut` section naming the files, `search`'s included |
| runbooks | none | nothing |

### An old `report.json`

Left where it is, never renamed or deleted: the new build never writes or opens the fixed name. No
reader must still find one, since nothing reads the report back. It is the last pre-upgrade run's
report; the guide says so in one sentence, so a coach is not puzzled by it.

### After the ruling (plan)

1. Tests first, shown failing on this commit: two `search --auto-cut` runs with different `--output`
   into one directory keep both reports; two `daily --auto-cut` runs of different dates into one
   digest directory keep both; each report beside its own bundle and manifest; `report.json` not
   written. Existing tests move to the new name.
2. The change in `AutoCutOptions.report`, help, docstrings, README, guide.
3. A mutant committed alone that writes `report.json` again, run against the new tests.
4. Affected set, ruff, pyright, lint-imports, `validate_specs.py`.

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
