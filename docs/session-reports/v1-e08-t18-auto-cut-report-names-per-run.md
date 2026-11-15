# Session report: v1-e08-t18-auto-cut-report-names-per-run

| | |
|---|---|
| Task | `v1-e08-t18-auto-cut-report-names-per-run` — An auto-cut run's report does not replace the last run's in the same directory |
| Spec | [`plan_specs/v1/e08-research-workflows/t18-auto-cut-report-names-per-run.yaml`](../../plan_specs/v1/e08-research-workflows/t18-auto-cut-report-names-per-run.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t18-auto-cut-report-names-per-run` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

An auto-cut run's report is now named after its bundle, as the PM ruled on 2026-11-14:
`search --auto-cut --output nhi.docx` writes `nhi.report.json`, and `daily politics --auto-cut`
writes `politics-<date>.report.json`, each beside its bundle and its manifest (unchanged). Two runs
into one directory keep both reports. The fixed `report.json` is never written, opened, renamed or
deleted. The change is one property, `AutoCutOptions.report` in `debate_cli`. Both commands name their
files through it. The rest is tests, help text, docstrings, the README and a new `--auto-cut` section
in `docs/guides/daily-digests.md`. The report already said when a run wrote no bundle (`"bundle":
null`), so per the ruling nothing changed there. The PM may want to look first at the two-run tests and
the second mutant: only those tests catch a report name that is fixed but not `report.json`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `auto-cut-report-names-per-run` (Report names) | Done | Red run first (17 failed), then the change, green (24 passed on the node's command); two mutants caught |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: Two auto-cut runs into one directory keep both reports, by a test shown failing first, and the guide names the report's file | PASS | **Red, before the change** (`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_search_command.py packages/debate_cli/tests/test_daily_command.py -k auto_cut -q --tb=line`) → `17 failed, 11 passed`, every failure a missing per-bundle report (12× `bundle.report.json`, 1× `first.report.json`, 2× `politics-2026-09-17.report.json`, 1× `politics-2026-09-18.report.json`) and 1× the `Report:` line naming `report.json`. The new tests among them: `test_two_auto_cut_runs_into_one_directory_keep_both_reports_each_beside_its_own_bundle` (search, `first.docx` then `second.docx`; the first report's bytes are unchanged after the second run, each names its own bundle, manifest and report, no `report.json`) and `test_two_days_auto_cut_runs_into_one_digest_directory_keep_both_reports` (daily, 2026-09-17 then 2026-09-18). **Green**: same command → `28 passed`. **Guide**: `docs/guides/daily-digests.md`, section "`--auto-cut`: cards from the digest, and the report of each run", names `politics-2026-11-14.report.json` and `nhi.report.json` and the old `report.json` |
| Node: Report names tests pass (`uv run pytest packages/debate_cli/tests/test_search_command.py -k auto_cut`) | PASS | `24 passed in 3.47s` |

**Mutants** (each applied to the committed code, run, and restored with `git checkout HEAD --`; tree
clean after each):

| Mutant in `AutoCutOptions.report` | Result |
|---|---|
| `return self.output.parent / "report.json"` (the fixed name again, as the PM asked) | caught: search and daily `-k auto_cut` → `17 failed, 11 passed`, each on the missing `<bundle>.report.json`, both new tests among them; slow e2e (`tests/integration/test_e2e_research.py -m slow`) → `2 failed, 1 passed` |
| `return self.output.parent / "bundle.report.json"` (fixed, but the name every single-run test uses) | caught by the new two-run search test alone: `1 failed, 23 passed`. Without it no test would see a report name fixed per directory |

## Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run --slow` | 115 of 767 test files chosen from 13 changed files; **stopped at the 115-second limit** (exit 124) at load ~3–17, with no failure printed before the stop. Under agreement 10 the affected set is left to the pull request's `ci` check |
| `pytest tests/architecture tests/specs -n auto -m "not slow and not live"` (always-run list) | `339 passed in 6.81s` |
| `pytest packages/debate_cli/tests -n auto -m "not slow and not live"` (the changed package's test directory) | stopped at the 115-second limit at load ~19–25 (other work on the machine); 1,872 passed, none failed, before the stop. Its auto-cut, daily, search, presenter, app, help and container tests passed in full separately (`160 passed`, and in the always-run list) |
| `pytest tests/integration/test_e2e_research.py -m slow` | `3 passed in 2.98s` |
| `pytest tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py` | `356 passed in 3.55s` |
| `uv run scripts/check_command_blocks.py` | OK, 719 blocks in 261 files |
| `uv run ruff format --check .` / `uv run ruff check .` | 2124 files already formatted / All checks passed |
| `uv run pyright packages/debate_cli tests/integration` | 0 errors, 0 warnings |
| `uv run lint-imports` / `uv run scripts/check_thin_handlers.py` | 20 kept, 0 broken / 74 handlers within 25 statements |
| `uv run scripts/validate_specs.py` | OK: 685 files, 41 epics, 622 tasks, 22 releases |

## Files changed

* `packages/debate_cli/src/debate_cli/search_auto_cut.py`: the report's name (`REPORT_SUFFIX`,
  `AutoCutOptions.report`) and the module docstring.
* `packages/debate_cli/src/debate_cli/commands/search.py`, `commands/daily.py`,
  `presenters/batch_report_presenter.py`, `presenters/daily_presenter.py`: `--output`'s help and
  docstrings name `<name>.report.json` / `<preset>-<date>.report.json`, and what a null `bundle` means.
* `packages/debate_cli/README.md`: the `daily` section names the three files.
* `packages/debate_cli/tests/test_search_command.py`, `test_daily_command.py`: the two-run tests, the
  existing reads moved to the new name, the "no report" checks covering both names.
* `tests/integration/test_e2e_research.py`, `tests/integration/ACCEPTANCE.md`: the path only (see
  Deviations).
* `docs/guides/daily-digests.md`: the `--auto-cut` section.
* `plan_specs/.../t18-auto-cut-report-names-per-run.yaml`: phase `Succeeded`.

## Deviations from the spec

* **`tests/integration/test_e2e_research.py` and `tests/integration/ACCEPTANCE.md` edited outside
  `constraints.packages`**, by the PM's ruling of 2026-11-14 ("(2) Yes. Edit
  tests/integration/test_e2e_research.py and tests/integration/ACCEPTANCE.md, path only, with no
  assertion changed or weakened. Record it as a Deviation citing this ruling. The PM adds
  tests/integration to the spec's packages in the next batch."). The change is `"report.json"` →
  `"bundle.report.json"` in two reads and in one table cell; no assertion changed.
* `packages/debate_cli/README.md` is under `debate_cli`; read as in scope.

## Decisions and assumptions

### Proposal for the PM's ruling: `<bundle stem>.report.json` (written before the ruling, kept as proposed)

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

### The PM's ruling (2026-11-14), applied as given

> (1) <bundle stem>.report.json, for search and daily alike, built in debate_cli beside the manifest's
> and digest's names. [...] The rule "running a date again writes its digest again" carries over: one
> report per preset per date, and the same --output replaces bundle, manifest and report together. Old
> report.json files are left in place and never renamed or deleted. The guide says in one sentence that
> such a file is the last report from before the upgrade.
>
> (2) Yes. Edit tests/integration/test_e2e_research.py and tests/integration/ACCEPTANCE.md, path only,
> with no assertion changed or weakened. Record it as a Deviation citing this ruling.
>
> On the quirk: [...] If the report does not already say that this run wrote no bundle [...] add one
> field that says so [...]. If it already says so, name the field in the report and change nothing.

### A report beside an older bundle of the same name: the field is `bundle`

It already says so, so nothing changed. Both payloads write `"bundle": null` (and `"manifest": null`)
when the run cut no card: `report_payload` (`batch_report_presenter.py`) and `auto_cut_payload`
(`daily_presenter.py`) both write `str(files.bundle) if files.bundle is not None else None`, and
`cut_and_write` returns `AutoCutFiles(report=...)` with no bundle when nothing was cut. Beside them,
`verified` and `unverified` are both 0. Tests pinning it: search,
`test_auto_cut_under_max_cost_ends_on_a_model_with_no_price` (`report["bundle"] is None`, already
there); daily, the new `test_two_days_auto_cut_runs_into_one_digest_directory_keep_both_reports`,
whose second day cuts nothing and asserts `bundle` is `None`. Only docstrings changed: `AutoCutFiles`
and the module docstring of `search_auto_cut.py` say what a null `bundle` means. The guide says it to
the coach.

### Choices the ruling left to the session

* `REPORT_FILE_NAME` (exported, imported nowhere) became `REPORT_SUFFIX = ".report.json"`, used by
  `AutoCutOptions.report` as `output.with_name(f"{output.stem}{REPORT_SUFFIX}")`, the manifest's form.
* The two "no report is written" checks in `test_search_command.py` (a usage error, a search no
  provider answered) would have passed for free under the new name, so each now asserts that neither
  `bundle.report.json` nor `report.json` exists.
* The README has no `search --auto-cut` file section; its `daily` section names the three files and
  says `search` names its report after `--output`. The guide's new section covers both commands.

## Operator follow-ups

None. The affected set ran past 115 seconds, so under agreement 10 it is left to the pull request's
`ci` check, with no hand-off.

## Follow-up work

* (FYI, unchanged by the ruling.) A run that cuts no card writes its report but leaves an earlier
  run's bundle and manifest of the same name in place. The report says so (`bundle` is null) and the
  guide tells the coach; whether such a run should also remove or rename the older bundle is the PM's
  call (E08).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
