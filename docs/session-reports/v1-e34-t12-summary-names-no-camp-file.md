# Session report: v1-e34-t12-summary-names-no-camp-file

| | |
|---|---|
| Task | `v1-e34-t12-summary-names-no-camp-file` — The pull summary names a camp download by id, never by title |
| Spec | [`plan_specs/v1/e34-caselist-sync/t12-summary-names-no-camp-file.yaml`](../../plan_specs/v1/e34-caselist-sync/t12-summary-names-no-camp-file.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t12-summary-names-no-camp-file` |
| Session status | COMPLETE |

## Summary

A camp download is now named by its OpenEv id in everything a pull writes for a person: `openev-512`,
plus `(sha256 2b912c191a8a)` once the run has the bytes. Each OpenEv selection in the summary drops
`inbox_name` and gains `inbox_file`, which names the file the way `inbox_retention` already does.
Removing a key is not additive under `v1-e34-t07`'s rule, so `RUN_SUMMARY_SCHEMA_VERSION` is now 3.
The scheduled-sync runbook's "can be pasted as they are" is true again. It also says that older
summaries and logs may still name camp files.

**Read first:**
- **Sweep row 2. The spec said the run record and the bucket's copy did not carry a camp title.
  They did.** When the archive reader refuses a camp zip, its message names the inbox file:
  `openev-777-<title>.zip cannot be read as an archive`. That message went into the import stage's
  reason. From there it reached the run record, the run log, the bucket's copy and
  `caselist runs --json`, because `redact` removes only path-shaped words and a bare file name has
  no `/`. The red output below shows it.
- **Sweep row 4 changes an exit code.** An `OSError` while writing or reading a camp download used
  to escape the run. The CLI then printed its message, which quotes the inbox path and the title,
  on the stdout line, with exit 70. Now that is a failed download or import named by id and error
  class (`openev-777: PermissionError`), with exit 1. See Deviation 2.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `name-by-id` — Camp downloads named by id in summaries | Done | The fix is in `caselist_sync.py`. The tests are a new `test_summary_names_no_camp_file.py` (7 tests) and one CLI test in `test_caselist_pull.py`. The runbook changed. Both test files were committed red before the code that turns them green. |

## Acceptance criteria

All results are from the final tree, at `e58d5ea` plus this report and the phase change.
`scripts/task sync` reported "Current branch … is up to date": `origin/dev` had nothing new.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — A pull that selects camp downloads produces a JSON summary, a run-summary file and a stdout log line with no camp title and no inbox file name, shown failing first with a probe-string fixture; each selection is identified by its OpenEv id | PASS | Red first at `a5319bb` (core) and against the old `caselist_sync.py` (CLI); output below. Green: the probe `Zqxprobe` is in the fixture's camp folder, its title and so its inbox name (`openev-512-Zqxprobe_Estuary_Solvency_Advocate.docx`). It appears nowhere in the dry-run JSON, the JSON summary, the summary file, the run record, the run log, the bucket's copy, the notification text as `MacOsNotifier.command_for` builds it, the `debate_core` log lines, the stdout line of `caselist pull --json`, the rendered `caselist pull`, or `caselist runs` in both forms. Cases: select (dry run); download, import, publish, confirm and retention; a revision (512 → 640); an import the archive reader refuses, on two runs; and an `OSError` on write and on read. The selections are written by hand, for example `{"openev_id": 512, "inbox_file": "sha256 2b912c191a8a", "year": 2026, "event": "POLICY", "decision": "download", "note": null, "revision_of": null}`. |
| **ac2** — Every reader of the summary's selections is listed and still works; the runbook's statement about pasting the log is true again | PASS | The readers table is below. No code, test, script or doc reads `inbox_name`: `git grep` finds it only in `caselist_sync.py` itself. The one test that pinned the version (`test_window_the_run_summary_reports_the_window_and_the_spend_inside_it`) now expects 3. The [runbook's statement](../runbooks/caselist-scheduled-sync.md#watching-it) now names camp titles, says how a camp download is named, and says older files may still name camp files. The full fast suite passes. |
| Node `name-by-id`: `uv run pytest packages/debate_core/tests/application/caselist` | PASS | `463 passed in 20.88s` |
| Mutation, each mutant on a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY` | PASS | 4 of 4 caught (table below) |
| CI's Python selection: `uv run pytest -m "not slow and not live" packages tests` | PASS | `4568 passed, 1 skipped, 1 warning in 117.01s`. The skip is the existing parser eval that waits on human corrections. The warning is `test_smoke_harness`'s deliberate blocked-socket check. Measured at 1 min 57 s, so I ran it in the session. |
| `uv run ruff format --check .` / `ruff check .` / `pyright` / `lint-imports` | PASS | `529 files already formatted` / `All checks passed!` / `0 errors, 0 warnings, 0 informations` / `Contracts: 11 kept, 0 broken.` |
| `uv run scripts/check_links.py` / `scripts/check_command_blocks.py` / `python scripts/docs_index.py --check-descriptions` | PASS | `OK: 1280 relative links and anchors in 180 Markdown files` / `OK: no # comments in 185 shell code blocks in 106 Markdown files` / `All 30 indexed documents under docs/ have a description` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | PASS | `OK: 310 files, 38 epics, 252 tasks, 20 releases`. `--require-succeeded v1-e34-t12-summary-names-no-camp-file` gives `Succeeded`. |

### ac1, shown failing first

**Core, `a5319bb`, the test alone against the unchanged sync.** Command:
`uv run pytest packages/debate_core/tests/application/caselist/test_summary_names_no_camp_file.py -n0 -p no:cacheprovider --no-cov -q`

```
E       AssertionError: a camp file's title reached ["the JSON summary (`caselist pull --json`, the agent's stdout)"]
E       AssertionError: a camp file's title reached ["the JSON summary (`caselist pull --json`, the agent's stdout)", 'the run-summary file']
E       AssertionError: a camp file's title reached ["the JSON summary (`caselist pull --json`, the agent's stdout)", "the bucket's copy of the run record", 'the run log', 'the run record', 'the run-summary file']
E       assert 2 == 3
FAILED …::test_a_pull_that_fetches_and_imports_a_camp_file_names_it_by_id_and_digest_alone
FAILED …::test_a_pull_that_fetches_a_revision_names_both_versions_by_id_alone
FAILED …::test_a_camp_download_whose_import_is_refused_is_named_by_id_and_digest_alone
FAILED …::test_the_summary_schema_is_version_3_because_a_key_was_removed
4 failed, 1 passed in 0.46s
```

The first failure is the dry run, which writes no file. The third is the refused import: the
title reaches the run record, the run log and the bucket's copy too. The passing test checks that
the probe is in every name the fixture's file goes by.

**CLI, the new test against `a5319bb`'s `caselist_sync.py`.** The old file was written over the
committed one, the test was run, and then `git checkout HEAD --` restored it. `git status --porcelain`
printed nothing afterwards.

```
E       AssertionError: a camp file's title reached the stdout line of `caselist pull --json`: '{"schema_version": 1, "status": "error", "command": "caselist pull", "data": null, "error": {"code": "CASELIST_PULL_INCOMPLETE", "message": "1 stage(s) of the caselist pull did not complete — import: 1 imported; 1 refused: openev-777: openev-777-Zqxprobe_Camp_Release.zip cannot be read as an archi…
1 failed, 17 deselected in 1.93s
```

**The `OSError` cases, `a4ea158`, against `9acbbd6`'s sync (before the last fix):**

```
E       PermissionError: [Errno 13] Permission denied: '/private/var/folders/…/evidence/inbox/openev-777-Zqxprobe_Camp_Release.zip'
E       PermissionError: [Errno 13] Permission denied: '/private/var/folders/…/evidence/inbox/openev-777-Zqxprobe_Camp_Release.zip'
2 failed, 5 passed in 0.87s
```

### Mutation

Each mutant was applied by a script. The script fails if its target text is not found exactly
once. Each run used a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (0 entries at the start). The
command was the new core file, `test_caselist_pull.py` and `test_caselist_sync.py` (110 tests),
with `-n0 -p no:cacheprovider --no-cov`. After each run, `git checkout HEAD --` restored the file,
and `git diff --quiet HEAD` confirmed it.

| Mutant | Caught by | Result |
|---|---|---|
| `"inbox_name": self.inbox_name` put back into `OpenEvSelection.as_json` | all 5 probe tests in the core file and the CLI test | `6 failed, 104 passed in 21.05s` |
| The title put back into the import stage's reason (the scrub in `_camp_download_refused` made a no-op) | `test_a_camp_download_whose_import_is_refused_…`, CLI test | `2 failed, 108 passed in 20.82s` |
| The title put back into the `OSError` reason (`{refused}` instead of its class name) | both `OSError` tests | `2 failed, 108 passed in 21.47s` |
| `RUN_SUMMARY_SCHEMA_VERSION` left at 2 | the version test, the summary-file assertion in the fetch test, `test_window_the_run_summary_reports_…` | `3 failed, 107 passed in 22.45s` |

No test here uses Hypothesis. I isolated the database anyway, as working agreement 8 asks.

## The sweep: every camp-file string that reached something a person may paste

I read `caselist_sync.py` in full, plus `sync_runs.py`, `caselist_pull.py`, `caselist_runs.py`, the
macOS notifier, the OpenCaselist client's error paths (`openev.py`, `inbox_writer.py`,
`transport.py`, the port's error classes), the archive reader, and the importers' log calls. Each
row below is a place a camp file's path, file name or title could reach output. Before and after
are the probe fixture's own text.

| # | Source | Reached | Before | After |
|---|---|---|---|---|
| 1 | `OpenEvSelection.as_json()["inbox_name"]` | JSON summary, summary file, stdout line (also inside the failure envelope's `details`) | `"inbox_name": "openev-512-Zqxprobe_Estuary_Solvency_Advocate.docx"` | Key removed. `"inbox_file": "sha256 2b912c191a8a"`, or `null` when the run never had the bytes (a dry run of a file not yet in the inbox, a failed fetch) |
| 2 | Import stage reason. The archive reader's `UnreadableArchive(location.name, …)` and `ArchiveTooLarge(source=location.name)`, and `_inbox_file`'s `UnreadableArchive(path.name, …)`, all name the inbox file | Stage reason in the JSON summary, summary file and stdout line; the failure message; the CLI table; the run record, run log and bucket's copy (`redact` keeps it, no `/`); `caselist runs --json` | `openev-777: openev-777-Zqxprobe_Camp_Release.zip cannot be read as an archive: not a readable zip file` | `openev-777 (sha256 adfcdbc5d3da): the download cannot be read as an archive: not a readable zip file` |
| 3 | Download stage reason, `openev-<id>: {error}` | As row 2 | No title today: every client error names `openev-<id>` (`DownloadConflict` keeps the inbox path as an attribute, never in its message) | The same scrub as row 2 applies, so a future error that quotes the name is covered. Text unchanged: `openev-777: …` |
| 4 | An `OSError` writing into the inbox (partial file, link) or opening a camp zip | Escaped the run. The run record kept only `error_class`, but the CLI's exit-70 envelope on stdout printed `str(error)` | `[Errno 13] Permission denied: '/…/inbox/openev-777-Zqxprobe_Camp_Release.zip'` | A failed download (`0 fetched, then: openev-777: PermissionError`) or a refused import (`openev-777 (sha256 adfcdbc5d3da): PermissionError`), exit 1 |

Checked and already clean, so unchanged:

| Output | Why it is clean |
|---|---|
| Select stage reason: the removal and revision sentences, and `note` | Ids and fixed text only (`openev-512 -> openev-640`, `v1-e34-t07`/`t08`). The revision test pins the sentence. |
| Retention stage reason and `inbox_retention` | `<caselist> <date>` or `sha256 <12 hex>` (`v1-e34-t11`). Its two `f"sha256 {digest[:12]}"` sites now share the `_sha256_label` helper; the output is the same. |
| Notifications | Built from the record's counts, stage names and error class, never a message. The tests check the text `MacOsNotifier.command_for` would run. |
| `caselist runs` table | Run id, time, outcome, counts. No reasons. |
| `debate_core` log lines (the agent's `err.log`) | Ids, counts and digests (`openev.py`, `_log_counts`, `_log_snapshot`, `_judge_unrecorded`). The core tests check every INFO-and-above record, its message and its extras. |
| The run record's schema | It carries no selections, so it is unchanged. Only its stage reasons changed, through rows 2 to 4. |

## Who reads the summary

| Reader | What it reads | What it sees now |
|---|---|---|
| `caselist pull --json` (`pull_summary`) and the launchd stdout log `caselist-sync.jsonl` | `as_json()` unchanged, plus `environment`, `bucket`, `summary_written_to` and `run_record` | `schema_version` 3, `inbox_file` instead of `inbox_name`, and reasons named by id. It reads no selection key itself. |
| `<data_dir>/caselist-sync-runs/<run id>.json` | Written, never read back by code (as `v1-e34-t06`/`t07` found) | The same object. |
| The CLI table, caption and failure (`_pull_table`, `_caption`, `_pull_failure`) | The `RunSummary` object: stage reasons, counts, and `summary.openev[].wanted` for the dry-run caption | The reasons from rows 2 to 4. No selection's name was ever read. |
| The run record (`record_for_summary`), the run log and the bucket's copy | The `RunSummary` object: counts and redacted stage reasons | The reasons from rows 2 to 4. Same schema, so a record is still one every earlier build reads. |
| `caselist runs` | Run records | `--json` shows the new reasons. The table is unchanged. |
| Notifications (`notifications_for`) | Record counts, stage names, error class | Unchanged. |
| Tests | `test_caselist_sync.py` pinned version 2. CLI tests read `selections`, `summary_written_to` and counts. Smoke tests read `openev_selections[].openev_id`/`decision` and `openev_skipped_as_removed`. Retention tests read `inbox_retention`. | The version pin now expects 3. Nothing else read `inbox_name`, so nothing else changed. |
| Docs | The scheduled-sync runbook's field table and pasting statement. `caselist-removal.md` reads `openev_selections`' decision. `docs/data/caselist-sync-runs.md` uses `jq` on counts. t11's follow-up `jq` reads `inbox_retention`. | The runbook gains an `openev_selections[]` row and the amended statement. The other three still hold. |
| `ops/launchd/run-caselist-sync.sh` | Nothing: it `exec`s the command | Unchanged. |

## Files changed

- `packages/debate_core/src/debate_core/application/caselist_sync.py`
  - `OpenEvSelection` gains `download_sha256`. It is set at selection from the inbox digest the
    select stage already computes, or by the download stage from what it fetched.
  - `OpenEvSelection` gains `label` (`openev-<id> (sha256 …)`) and `with_download`.
  - `as_json` drops `inbox_name` and gains `inbox_file`.
  - A new `_camp_download_refused` builds the download and import stages' camp-download reasons
    (rows 2 to 4), and both stages catch `OSError` for camp downloads.
  - New `_sha256_label`. `RUN_SUMMARY_SCHEMA_VERSION` is 3, with its docstring. The module
    docstring's "What is logged and summarised" now says how a camp download is named.
- `packages/debate_core/tests/application/caselist/test_summary_names_no_camp_file.py` (new): the
  probe tests, 7 in all.
- `packages/debate_core/tests/application/test_caselist_sync.py`: the version pin, 2 → 3.
- `packages/debate_cli/tests/commands/test_caselist_pull.py`: the probe served through respx. It
  checks the `--json` stdout line, the rendered table, the summary file, `caselist runs` in both
  forms, and the notifications (a `RecordingNotifier` patched into `ServiceContainer`).
- `docs/runbooks/caselist-scheduled-sync.md`:
  - the pasting statement, with the sentence about older summaries and logs;
  - an `openev_selections[]` row;
  - how to find a refused camp download's inbox copy from its id.

## Deviations from the spec

1. **The spec's "the run record and the bucket's copy do not carry it" was untrue for a refused
   camp import** (sweep row 2). I fixed that under your instruction to sweep every output, so the
   scope did not change. The spec's out-of-scope item still holds: the run record's *schema* is
   unchanged.
2. **An `OSError` on a camp download now fails that stage instead of the run** (sweep row 4). It
   was exit 70 with the title on stdout. It is now exit 1, with the file named by id and error
   class. `caselist_pull`'s docstring already says 1 means "a download, an import or a publish
   failed".

   This is narrower than it might sound:
   - Only the two camp-download loops catch it. A weekly archive's `OSError` still ends the run,
     but it names no camp file.
   - An `OSError` from anything else the import does, such as a full disk while storing a blob,
     is caught too. It is reported as that download's refused import, by class name only.

   I chose this over leaving a forbidden string reachable on a rare path. If you would rather keep
   exit 70 for `OSError`, the alternative is to change the CLI's generic handler so it stops
   printing the message of an exception it did not model. That handler is in `debate_cli.app`,
   outside this task's packages.

## Decisions and assumptions

1. **`inbox_file`, not a bare digest.** Its value is `sha256 <12 hex>`, the string `inbox_retention`
   gives the same file. So "which id was the camp download retention removed" can be answered by
   matching strings. It is `null` when the run never had the bytes. For a file found in the inbox,
   it is set at selection, so `already_in_inbox` and inbox-matched `already_imported` carry it too.
2. **The scrub replaces every name the file goes by** with "the download": the inbox name, the
   upstream path (with and without its leading `/`), its last component, and the listing's
   `filename`. Today only the inbox name ever appears in a message. The others cost one line each
   and cover an error class that later quotes the upstream name.
3. **The probe's absence is checked case-insensitively.** It is also checked in the log records'
   extras as well as their messages, and in the bucket's raw copy, not only the parsed record.
4. **Your files on disk were not touched.** That covers your data directory, the installed agent
   and its log. Every test uses a temporary data directory and moto.

## Operator follow-ups

None required. No command here needs credentials or runs longer than about 2 minutes.

For information: the installed agent runs an installed build. It keeps writing `inbox_name` until
a build that contains this change is installed by the usual install step in
`docs/runbooks/caselist-scheduled-sync.md`. The runbook's new sentence covers the summaries and
logs written before then.

## Follow-up work

1. **The dry run's download reason names the inbox's own path**: `would download N file(s) into
   /Users/…/inbox` (`_plan_remaining_stages`, since `v1-e34-t02`). It is not a camp file, so I
   left it. But `v1-e34-t11` kept the inbox path out of the summary for being your home directory,
   and this reason prints it in `caselist pull --dry-run --json`. (E34)
2. **The CLI's generic handler prints `str(exception)` for any unmodelled exception**
   (`debate_cli.app`, exit 70). An `OSError` there quotes a path, in any command. This task closed
   the camp-download routes into it (Deviation 2). The general case belongs with the CLI's error
   handling (E01).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
