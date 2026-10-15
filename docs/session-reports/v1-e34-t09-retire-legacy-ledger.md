# Session report: v1-e34-t09-retire-legacy-ledger

| | |
|---|---|
| Task | `v1-e34-t09-retire-legacy-ledger` — Retire the legacy download ledger |
| Spec | [`plan_specs/v1/e34-caselist-sync/t09-retire-legacy-ledger.yaml`](../../plan_specs/v1/e34-caselist-sync/t09-retire-legacy-ledger.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t09-retire-legacy-ledger` |
| Session status | COMPLETE (phase left `InProgress` for ac2's deletion, which is the operator's) |

## Summary

The legacy read is gone. `DownloadLedger` no longer takes a `legacy_path`,
`LEGACY_DOWNLOAD_LEDGER_FILENAME` is deleted, and `CaselistSyncService` counts the cap from
`caselist-sync-download-starts.json` alone. The tests of the legacy read are gone. Every other cap
test passes unchanged, apart from the window property, which no longer plants a legacy file. A new
test shows that a leftover calendar ledger is ignored: it failed before the change for the reason
expected, and passes after it.

I established from the tagged source that no build that can still run writes the legacy file.
Every tag from `v0.1.0-dev.13`, the `v1-e34-t06` merge, only reads it. The last tag that writes it
is `v0.1.0-dev.12`. The agent runs `v0.1.0-dev.122`, and before that it ran `0.1.0.dev60`, and
both only read it. The backfill finished on 2026-10-09. `dev` and `main` both carry the change.

The phase stays `InProgress`. ac2's last clause, deleting the file, is the operator's, after merge.
The commands are under Operator follow-ups, with read-only checks to run first. Look first at two
things:

* **The node criterion's selector does not collect the rolling-window tests.**
  `-k "budget or cap or download_starts"` picks 38 tests and none of the `test_window_*` tests.
  23 of the 38 match only because "escape" and "landscape" contain "cap". I named the new test so that the selector collects
  it, and also ran `-k window`. See Deviations.
* **Two mutants survived.** Neither one lets a run download more than five in 24 hours. See
  "Mutation run" below.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `remove` — Remove the legacy read | Done | Test first (`c218126`, red), removal (`738fc11`), runbook (`ff40783`), test-name length fix (`a22d163`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — the legacy ledger read and its tests are removed, and the cap is still enforced from the rolling-window file alone, shown by the existing cap tests | PASS | The read, its constant, its export and the `legacy_path` wiring are deleted. Five tests of the read are deleted: 4 functions plus 1 parametrized over 6 bodies, 10 cases in all. `uv run --frozen pytest packages/debate_core/tests/application/test_caselist_sync.py -k window` → `23 passed`. The new leftover-ledger test is red before the change and green after it (below). The whole module → `76 passed`. Full suite in five parts: green (below). |
| ac2 — the report names the build the scheduled agent runs and how it was established that no old-format build still writes to the agent's state directories, and the operator has deleted the legacy file from each | NOT RUN (deletion pending) | The first half is done: see "Which builds write the legacy file" below. The deletion is the operator's after merge. The commands are under Operator follow-ups. The PM records the deletion and sets `Succeeded` at a close-out. |
| Node `remove`: `uv run pytest packages/debate_core/tests -k "budget or cap or download_starts"` | PASS | `39 passed in 4.95s`: the 38 it collected before, plus the new test. |

### Red, then green

The test is
`test_window_the_cap_counts_the_download_starts_file_alone_and_ignores_a_leftover_calendar_ledger`.
It plants the operator's old-format ledger (`{"bulk_downloads": 5, "date": "2026-09-29"}`) 40
minutes before the run. Then it asserts four things: nothing is counted as spent; both weeklies
download; the download-starts file holds exactly the run's two starts; and the leftover file keeps
its bytes and its mtime.

The final test was run against the original source, `git checkout 736440d -- caselist_sync.py`,
then restored with `git checkout HEAD --` and the tree checked clean:

```console
$ uv run --frozen pytest packages/debate_core/tests/application/test_caselist_sync.py -k "budget or cap or download_starts" -q -p no:randomly
E       AssertionError: assert 5 == 0
E        +  where 5 = RunSummary(run_id='20260929T052511Z', ...).bulk_downloads_spent_in_window
FAILED packages/debate_core/tests/application/test_caselist_sync.py::test_window_the_cap_counts_the_download_starts_file_alone_and_ignores_a_leftover_calendar_ledger
1 failed, 8 passed in 2.28s
```

That is the legacy read counting the leftover file's five. The test was first committed red under
a longer name in `c218126` and failed the same way. `a22d163` shortened the name to fit ruff's line
limit. After the change, on this branch: `9 passed` with that selector on the module, and `39
passed` with the node's command over `packages/debate_core/tests`.

### Mutation run

The harness is a scratch script, not in the repository. Each mutant was applied to the committed
`caselist_sync.py`. Then `uv run --frozen pytest packages/debate_core/tests/application/test_caselist_sync.py -n auto`
ran with `HYPOTHESIS_STORAGE_DIRECTORY` set to a new, empty temporary directory. The file was
restored with `git checkout --`, and `git status --porcelain` was checked empty before the next
mutant. It was empty after every mutant.

| Mutant | Result |
|---|---|
| A start exactly 24 hours old still counts (`>=` at the boundary) | CAUGHT, 1 failed: `…_still_counted_at_23h59m_and_released_at_24h01m` |
| A 23-hour window | CAUGHT, 15 failed |
| The download-starts file is not read at all | CAUGHT, 24 failed, including the window property and the new test |
| An unrecognised download-starts file reads as nothing spent | CAUGHT, 6 failed: the 6 `…_unrecognised_ledger_is_counted_as_fully_spent` cases |
| `record` forgets the starts already in the file | CAUGHT, 17 failed, including the window property |
| A start later than now is not counted | CAUGHT, 1 failed: `…_a_clock_set_back_frees_nothing` |
| The service never records a download start | CAUGHT, 5 failed |
| The service grants the whole limit whatever was spent | CAUGHT, 11 failed |
| The service does not clamp the configured allowance to five (`limit=bulk_downloads_per_day`) | SURVIVED |
| `remaining_at` may go negative (no `max(…, 0)`) | SURVIVED |

8 of 10 were caught. Each catch took 3.5 to 5.2 s for the whole module, from a fresh database.
I re-ran both survivors against `packages/debate_core/tests packages/debate_cli/tests -m "not slow and not live"`,
with a fresh database each time. Both still survive, `5438 passed, 2 xfailed` each. Why neither one
lets a run download more than five in 24 hours:

* **No clamp to five in the service.** `CaselistSettings._within_the_sites_daily_limit` refuses a
  `bulk_downloads_per_day` above 5. So no run built from settings reaches the `min()`, and only a
  direct construction with 6 or more could. The `min()` is a second guard that nothing tests.
* **No clamp at zero.** `within_daily_budget` and the full-archive allowance both apply `max(…, 0)`
  themselves, so nothing more is downloaded. The only visible effect is a negative
  `bulk_downloads_allowed` in the plan and summary when more than `limit` starts are in the window.
  That can happen after the operator lowers `bulk_downloads_per_day`. No test records more starts
  than the limit.

Both are pre-existing behaviour of the rolling window, which this task may not change. They are
listed under Follow-up work.

The first wide re-run was cut short by my own `alarm` while the second mutant was still applied.
I restored the file at once with `git checkout --`, checked the tree clean and that no pytest was
still running, and then re-ran that mutant on its own. Its result is the one above.

### Other checks

| Check | Result |
|---|---|
| Load average before the suite parts (11 CPUs) | 1-minute averages 10.37, 11.81, 11.28, 12.41 and 11.46 before parts 1 to 5. It peaked at 39.4 during the wide mutant re-run, from other work on the machine. |
| `uv run --frozen pytest -n auto -m "not slow and not live" --part 1/5` | `1428 passed, 1 skipped in 40.51s` |
| `… --part 2/5` | `1428 passed, 1 xfailed in 32.06s` |
| `… --part 3/5` | `1413 passed, 1 warning in 37.57s` |
| `… --part 4/5` | `1416 passed, 1 xfailed, 1 warning in 33.93s` |
| `… --part 5/5` | `1424 passed, 1 warning in 45.65s` |
| The three warnings | From `pytest_socket`. Two of them name `tests/smoke/test_network_guard.py` tests, which trigger the guard on purpose. None comes from this change. |
| `uv run --frozen ruff format --check .` | `695 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` The first run failed with E501 on the new test's name, fixed in `a22d163`. |
| `uv run --frozen pyright` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `uv run --frozen scripts/check_command_blocks.py --base origin/dev` | `OK: no # comments in 262 shell code blocks in 117 Markdown files`, before the report was written. Run again after it, below. |
| `uv run scripts/check_links.py` | `OK: 1560 relative links and anchors in 222 Markdown files` |
| `uv run scripts/validate_specs.py` | `OK: 348 files, 38 epics, 290 tasks, 20 releases` |

## Which builds write the legacy file

The PM established these facts:

* The scheduled agent is a dev agent (`DEBATE_ENV=dev`, data directory `~/.debate-research/dev`).
* Since 2026-10-14 the agent runs `v0.1.0-dev.122` (`d87febd`). Before that it ran `0.1.0.dev60`,
  which that install replaced.
* The agent's plist runs `~/.local/bin/debate-research`, the uv tool that `install_channel.sh`
  installs.
* The operator also runs commands with `uv run` from a checkout of `dev`, which carries the rolling
  window.

What I established from source:

* **`v0.1.0-dev.122` only reads the file.** I exported it with
  `git archive v0.1.0-dev.122 packages` and read its ledger code. In
  `packages/debate_core/src/debate_core/application/caselist_sync.py`:
  * `DownloadLedger.starts()` calls `DownloadLedger._legacy_starts(self.legacy_path)`, which calls
    `is_file()`, `_read_json_object()` and `stat()`. Those are reads only.
  * `DownloadLedger.record()` is the class's only write. It calls `_write_json(self.path, …)`, and
    `self.path` is `caselist-sync-download-starts.json`.
  * `CaselistSyncService.__init__` passes the legacy file only as `legacy_path=`.

  `git grep` over the whole tag, docs and specs aside, finds no other mention of
  `caselist-sync-downloads.json`, so nothing in that build writes, renames or deletes it.
  `v0.1.0-dev.60` (`ec7b95e`) has the same code: the same constant, and the same `legacy_path=`
  wiring.
* **The last build that writes it is `v0.1.0-dev.12`** (`1f5bcd8`, 2026-09-29). Its
  `DOWNLOAD_LEDGER_FILENAME` is `"caselist-sync-downloads.json"`, and its
  `DownloadLedger.record(day, downloads)` writes `{"date": …, "bulk_downloads": …}` through
  `_write_json`. `git tag --no-contains aa7c2b6` lists exactly `v0.1.0-dev.1` to `v0.1.0-dev.12`,
  and each of them has that constant. `v0.1.0-dev.13` is `aa7c2b6`, the `v1-e34-t06` merge.
  There are no tags other than dev pre-releases, so no stable or prod-channel build exists that
  could be older.

Why none of them can still be writing:

| Writer | Build | Writes the legacy file? |
|---|---|---|
| The scheduled agent | `v0.1.0-dev.122` since 2026-10-14, after `0.1.0.dev60`. Both contain `aa7c2b6`, checked with `git merge-base --is-ancestor`. | No, it reads only. A uv tool install replaces the tool, so one `debate-research` is in the tool directory at a time. |
| `v1-e30-t06`'s backfill | Finished: its last run was `20261009T023420Z`, and the spec is `Succeeded`. Its early runs were on an old-format build: `v0.1.0-dev.5`, per `v1-e34-t06`'s report. | Not any more. It has finished, and its build is no longer the installed tool. |
| The operator's `uv run` from a checkout of `dev` | `origin/dev` and `origin/main` both contain `aa7c2b6`. | No. A worktree whose `HEAD` predates `aa7c2b6` would still write it if `caselist pull` ran there, so the follow-up checks every worktree. |

The file's modification time is the direct record of the last write, and the deletion block shows
it first. Expect late September or early October 2026, no later than the backfill's last run
(2026-10-09 UTC). A later time means an old-format build ran after the backfill: stop and tell the
PM before deleting.

**Deleting the file is safe before or after the agent is reinstalled.** `v0.1.0-dev.122` counts the
legacy file only for 24 hours after its last write, and that write was more than a week ago. Read
or absent, the file counts as nothing.

## Files changed

* `packages/debate_core/src/debate_core/application/caselist_sync.py`: the legacy read is removed.
  * `LEGACY_DOWNLOAD_LEDGER_FILENAME`, its `__all__` entry, `DownloadLedger`'s `legacy_path`
    argument and attribute, `_legacy_starts`, and the service's `legacy_path=` are deleted.
  * `starts()` returns this ledger's own starts.
  * The class docstring says this file is the only one counted and that a leftover is neither read
    nor removed.
  * The unrecognised-file rule (fully spent from the mtime) is unchanged.
* `packages/debate_core/tests/application/test_caselist_sync.py`:
  * The new leftover-ledger test, with its own `LEFTOVER_CALENDAR_LEDGER` file name, written by
    hand because the module no longer names it.
  * Five tests of the legacy read are deleted.
  * The window property no longer plants a legacy file: its `legacy_spent` and
    `legacy_age_seconds` inputs are removed.
  * One helper docstring is corrected.
* `docs/runbooks/caselist-scheduled-sync.md`: the paragraph that said newer builds read the
  calendar ledger and to leave it in place now says the opposite:
  * no build reads it;
  * a leftover may be deleted;
  * a build older than `v0.1.0-dev.13` must never be installed for the agent or run against a data
    directory.
* `docs/session-reports/v1-e34-t09-retire-legacy-ledger.md`: this report.

## Deviations from the spec

* **The window property test changed.** The brief says the cap tests pass unchanged, apart from the
  tests of the legacy read. `test_window_no_24_hours_ever_holds_more_than_five_starts` was both:
  half of its inputs planted a legacy ledger and counted it in the oracle. With the read gone, that
  half would fail by design. I removed those inputs and kept the rolling-window half byte for byte:
  the gaps, the wants, the oracle, the `A_ROLLING_DAY` written in the test, and 150 examples. The
  mutation run shows it still catches `record` forgetting starts and the file not being read.
* **The node's selector misses the tests it is meant to run.** `-k "budget or cap or download_starts"`
  collects no `test_window_*` test. 23 of its 38 matches are names containing "escape" (15) or
  "landscape" (8), which contain "cap". I left the spec alone and ran `-k window` beside it. I suggest
  `-k "window or budget or cap"` if the PM wants the criterion to mean what it says.

## Decisions and assumptions

* **A leftover file is ignored, not deleted, by the code.** The spec gives the deletion to the
  operator, and code that removed a file it no longer reads would be a new write into the state
  directory. The new test asserts that the file's bytes and mtime are untouched.
* **`OPERATOR_LEGACY_LEDGER` stays in the tests.** The unrecognised-ledger test still uses it
  (`old-format-under-the-new-name`), and that case is about the download-starts file, not the
  legacy read.
* **The backfill runbook's day-1 note stays.** `docs/runbooks/caselist-backfill.md` describes the
  UTC-keyed ledger as it was during the backfill, and already says that the rolling window replaced
  it. It is a record, not an instruction.

## Operator follow-ups

**1. Confirm no old-format build is left** (read-only, now; a few seconds). Where: your Mac, any
directory.

Every `debate-research` on PATH, and the version each one reports:

```bash
which -a debate-research
which -a debate-research | while read -r p; do echo "${p}"; "${p}" --version; done
uv tool list --show-paths
```

Success looks like this. `~/.local/bin/debate-research` reports `0.1.0.dev122` on the dev channel,
commit `d87febdcaf23`. `uv tool list` shows `debate-cli v0.1.0.dev122` and nothing older. Any other
entry must report `0.1.0.dev13` or later. A `local channel` entry from a checkout's `.venv` instead
prints a commit, which check 1c below covers.

The agent's plist: its environment, its command, and the build it points at:

```bash
plutil -extract EnvironmentVariables json -o - ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
plutil -extract ProgramArguments json -o - ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
"$(plutil -extract EnvironmentVariables.DEBATE_RESEARCH_BIN raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)" --version
```

Success looks like this:

* `DEBATE_ENV` is `dev`.
* `DEBATE_RESEARCH_BIN` is your `~/.local/bin/debate-research`, and it reports `0.1.0.dev122`.
* No `DEBATE_STORAGE__DATA_DIR` is set, so the agent's data directory is `~/.debate-research/dev`.

If one is set, that directory is a state directory too, and check 1d covers it only if it is
under `~/.debate-research`.

**1c.** Every checkout and worktree of the repository, and whether its `HEAD` carries the rolling
window. Where: in any checkout or worktree of the repository, for example this task's worktree:

```bash
git worktree list --porcelain | sed -n 's/^worktree //p' | while read -r w; do if git -C "${w}" merge-base --is-ancestor aa7c2b6 HEAD; then echo "rolling window   ${w}"; else echo "CALENDAR LEDGER  ${w}"; fi; done
```

Success looks like every line starting `rolling window`. A `CALENDAR LEDGER` line is a worktree
that would write the legacy file if `caselist pull` ran there. Do not run a pull there, and tell
the PM.

**1d.** Every copy of the legacy file under `~/.debate-research`, prod included. This shows whether
the prod data directory has one:

```bash
ls -d ~/.debate-research/*/
find ~/.debate-research -maxdepth 2 -name caselist-sync-downloads.json -exec stat -f '%N  %z bytes  modified %Sm' -t '%Y-%m-%d %H:%M:%S %Z' {} \;
```

Success looks like one line, for `~/.debate-research/dev`, modified no later than 2026-10-09 UTC.
`~/.debate-research/prod` is the bundled prod profile's data directory. The agent never runs there,
and nothing here says a pull did. If `find` lists a prod copy anyway, delete it the same way as in
step 2, with `prod` in place of `dev`.

**2. Delete the legacy file** (after this branch merges; seconds). Where: your Mac, any directory.
Not during a scheduled run, which is Wednesday 06:00. First show its size, modification time and
contents:

```bash
stat -f '%N  %z bytes  modified %Sm' -t '%Y-%m-%d %H:%M:%S %Z' ~/.debate-research/dev/caselist-sync-downloads.json
cat ~/.debate-research/dev/caselist-sync-downloads.json
```

If the modification time is later than 2026-10-09 UTC, stop and send the output to the PM. If it is
not, remove the file and confirm it is gone:

```bash
rm ~/.debate-research/dev/caselist-sync-downloads.json
ls ~/.debate-research/dev/caselist-sync-downloads.json
```

Success looks like `ls` saying `No such file or directory`. Paste the `stat` line and the `ls`
output back to the PM, who records them and sets the phase to `Succeeded` at a close-out.

## Follow-up work

* **E34, the rolling window's own tests** (not this task's to change):
  * Nothing tests `remaining_at`'s clamp at zero. When more than `limit` starts are in the window,
    a run without the clamp downloads nothing extra but reports a negative
    `bulk_downloads_allowed`. A test recording six starts against a limit of five would catch that.
    So would a lowered `bulk_downloads_per_day` with more already spent.
  * Nothing tests the service's `min(bulk_downloads_per_day, 5)`. The settings validator is the
    guard that holds. Either test a direct construction with 6, or delete the `min()` as a second
    guard nothing can reach (working agreement 8 allows that outcome).
* **`v1-e34-t09`'s node criterion:** widen the selector as described in Deviations.
* **Legacy-era wording, left as it is:**
  * `DownloadLedger._spent_when_written`'s docstring ("the latest any of them can be") was written
    for the calendar ledger's downloads. It still reads correctly for an unrecognised file.
  * The backfill runbook's UTC-date note, described under Decisions.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
