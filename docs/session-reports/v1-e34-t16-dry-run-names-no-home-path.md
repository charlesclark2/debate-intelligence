# Session report: v1-e34-t16-dry-run-names-no-home-path

| | |
|---|---|
| Task | `v1-e34-t16-dry-run-names-no-home-path` — The dry run's download plan names no path on the operator's machine |
| Spec | [`plan_specs/v1/e34-caselist-sync/t16-dry-run-names-no-home-path.yaml`](../../plan_specs/v1/e34-caselist-sync/t16-dry-run-names-no-home-path.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t16-dry-run-names-no-home-path` |
| Session status | COMPLETE |

## Summary

No pull output a person is told they may paste names a path on this machine any more. The probe
found three paths, all under the data directory: the dry run's download plan (the known one), the
`summary_written_to` field in `caselist pull --json`, and the message printed when another run
holds the run lock. The dry run now plans `would download N file(s) into the inbox`.
`summary_written_to` is now `caselist-sync-runs/<run id>.json`, the summary file's path inside the
data directory. The lock refusal now names `caselist-sync.lock in the data directory`. The probe
runs a data directory under one distinctive path and `HOME` under another. It covers every run
`run_record_scenarios.SCENARIOS` describes, plus five more, and every output on your list. Nothing
else carried a path. No exit code, record shape or details shape changed. The runbook's pasting
statement was untrue in those three places, so I corrected it rather than keeping it word for word.

**Read first:**
- **`summary_written_to` changed meaning, not shape.** The key and its type (`string | null`) stay
  the same. The value goes from an absolute path to a path relative to the data directory. Nothing
  in code, scripts or docs reads it. Five tests opened it as a path, and they now join it to the data
  directory. One of them is the smoke test `tests/smoke/test_caselist_pull_in_process.py`, which is
  outside `constraints.packages` (Deviation 2). It is not a record and the installed agent never
  reads it, so your "stop if a record's shape changes" did not apply. It is still a change a
  program reading the agent's stdout log would notice, so check it first. If you would rather keep
  the key unchanged and drop the path some other way, that is a one-line change.
- **A dry run writes no summary file**, which the spec's description and ac1 assume it does
  (Deviation 1). It never has: `run_pull` returns `summary_path=None` for a dry run, and the
  service writes nothing (`v1-e34-t02` ac2). The test asserts that, and checks the summary files of
  every real run instead.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `no-home-path` — The inbox named by role | Done | Fixes in `caselist_sync.py` (the dry-run reason, `SyncRunInProgress`'s message) and `caselist_pull.py` (`summary_written_to`). Probe tests are the new `test_pull_names_no_path_on_this_machine.py` (core, 16 tests) and `test_caselist_pull_names_no_path.py` (CLI, 4 tests). Both were committed red at `a456ad4`, before the fix at `af09099`. |

## Acceptance criteria

The results below are from `af09099` plus this report and the phase change. `scripts/task sync`
was not run, because `dev` had nothing this task needed.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — A dry run with a data directory under a distinctive probe path produces a JSON summary, a summary file and a rendered table without the probe, shown failing first | PASS | The red output is below, at `a456ad4`, with the tests on the start commit's source. Green: in core, `test_a_dry_run_names_the_inbox_by_its_role_and_no_path_on_this_machine` plans 2 weeks and 2 camp files, with 1 week already in the inbox. It looks in the JSON summary, the log lines and the progress lines. The reason is written by hand: `would download 4 file(s) into the inbox`. In the CLI, `test_a_dry_run_prints_the_inbox_by_its_role_and_no_path_on_this_machine` checks `--json` and the rendered table (with `--verbose`, `COLUMNS=1000`), both stdout and stderr. The summary file: a dry run writes none (asserted, Deviation 1). The real runs' summary files are probed under ac2. |
| **ac2** — Every other pull stage reason is checked for the probe the same way, and the runbook's pasting statement stays true | PASS | 10 recorded scenarios and 4 more in core, and 2 more runs in the CLI. The outputs are listed under "What the probe reads" below, and every reason source under "The sweep". The [runbook statement](../runbooks/caselist-scheduled-sync.md#watching-it) is corrected: it was false for the three outputs fixed here. |
| Node `no-home-path`: `uv run pytest packages/debate_core/tests/application/caselist` | PASS | `1370 passed in 55.46s` |
| Mutation, one per fix, each on a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` | PASS | 4 of 4 caught (table below) |
| Default suite, `uv run pytest --part K/4 -q -p no:cacheprovider`, K = 1…4, one after another, each under `perl -e 'alarm …'` | PASS | `2035 passed in 98.35s` / `2045 passed, 1 xfailed in 79.49s` / `2044 passed, 1 skipped, 2 warnings in 66.54s` / `2037 passed, 1 xfailed, 1 warning in 83.98s`. The load average was 5 to 54, because other sessions were running. The warnings come from existing tests: the two new files run with no warnings. |
| `uv run ruff format --check .` / `ruff check .` / `pyright` / `lint-imports` | PASS | `796 files already formatted` / `All checks passed!` / `0 errors, 0 warnings, 0 informations` / `Contracts: 12 kept, 0 broken.` |
| `uv run scripts/check_command_blocks.py` / `scripts/check_links.py` | PASS | `OK: no # comments in 279 shell code blocks in 122 Markdown files` / `OK: 1643 relative links and anchors in 244 Markdown files` |
| `uv run scripts/validate_specs.py` (after `set-phase … Succeeded`) | PASS | `OK: 366 files, 38 epics, 308 tasks, 20 releases`. `--require-succeeded v1-e34-t16-dry-run-names-no-home-path` gives `Succeeded`. |

### Shown failing first

`a456ad4` is the start commit plus the two test files. Command:
`uv run pytest <both new files> -n0 -p no:cacheprovider --no-cov -q --tb=line`. Paths are shortened
to `…` here only:

```
"run 1: the JSON summary (`caselist pull --json`, the agent's stdout)": ["the data directory's probe", …,
  "an absolute path at 777: '…\"reason\": \"would download 4 file(s) into /private/var/folders/…/T/pytest-of-ch'"]
"stopped run 1: the error the command reports": ["the data directory's probe", …,
  "an absolute path at 55: 'another caselist sync is already running (lock held at /private/var/folders/…'"]
"caselist pull --json --dry-run": […, "would download 3 file(s) into /private/var/folders/…"]
"caselist pull --dry-run": […, "│ download  │ planned   │ would download 3 file(s) into /private/var/folders/…"]
"caselist pull --json": […, "\"summary_written_to\": \"/private/var/folders/…"]
"caselist pull --json": […, "another caselist sync is already running (lock held at /private/var/folders/…"]
"caselist pull": […, "│ another caselist sync is already running (lock held at /private/var/folders/…"]
FAILED …/test_pull_names_no_path_on_this_machine.py::test_a_dry_run_names_the_inbox_by_its_role_and_no_path_on_this_machine
FAILED …/test_pull_names_no_path_on_this_machine.py::test_a_run_the_recorded_scenarios_do_not_cover_names_no_path_on_this_machine[a_run_another_runs_lock_refused]
FAILED …/test_caselist_pull_names_no_path.py::test_a_dry_run_prints_the_inbox_by_its_role_and_no_path_on_this_machine
FAILED …/test_caselist_pull_names_no_path.py::test_a_run_and_the_run_list_print_no_path_on_this_machine
FAILED …/test_caselist_pull_names_no_path.py::test_a_run_another_runs_lock_refused_prints_no_path_on_this_machine
5 failed, 15 passed in 6.22s
```

Every hit also named the temporary directory and the user's name, because macOS puts pytest's
temporary directory under `pytest-of-<user>`. The 15 that passed are the 10 recorded scenarios,
the other 3 core scenarios and the 2 tests of the probe itself. My first run also hit the log lines
in every test, which was a bug in the harness: I had serialised `vars(record)`, and that includes
the LogRecord's own `pathname`, the source file that logged it. The probe now reads the message and
the `extra=` fields a caller passed, which is what a log handler writes.

### The probe

| What | Where |
|---|---|
| Data directory | `<tmp>/Zqxdataprobe/.debate-research/dev` (CLI: `…/test`), deliberately not under `HOME` |
| `HOME` | `<tmp>/Zqxhomeprobe/operator`, set with `monkeypatch`. `Path.home()` is asserted to be it. With it, boto3 finds no `~/.aws` |
| Searched for, case-insensitively | both probes; `str(tmp_path)` and its resolved form; `getpass.getuser()` as a whole word (when it is 3 or more letters); any `~/` or `/Users/`, `/home/`, `/private/`, `/var/`, `/tmp/`, `/Volumes/`, `/opt/`, `/etc/` that does not follow a word, dot, colon or slash, so a URL's path and a `docs/…` citation do not match |
| The probe tested on itself | `test_the_probe_is_in_the_data_directory_and_the_home_directory_and_nowhere_else` (core) and `test_the_probe_finds_a_path_into_the_data_directory_or_the_home_directory` (CLI). They check it finds the inbox path, a home path, `~/…` and `/Users/someone/…`, and does not flag the fixed wording, a `storage.data_dir` hint, a `docs/runbooks/…` citation or a URL. |

### What the probe reads

| Output | Core test | CLI test |
|---|---|---|
| JSON summary (`as_json`, which `--json` and the agent's stdout print) | every pull | every `--json` pull, the whole stdout line |
| Summary files, `caselist-sync-runs/*.json` | every file in the directory | every file in the directory |
| The `--json` envelope: `summary_written_to`, `run_record`, `run_details`, and on failure `error.message` and `error.details` | — | yes |
| Rendered table and caption, and stderr including `--verbose` progress lines | progress lines | yes, at `COLUMNS=1000` so no path is wrapped |
| Run record, and `caselist-sync-runs.jsonl` | yes | yes (the file) |
| Run details, and `caselist-sync-run-details.jsonl` (`v1-e34-t19`) | yes | yes (the file) |
| The bucket: `reports/sync-runs/…` and `reports/sync-run-details/…` | every object under `reports/` | — (the `test` environment has no bucket) |
| Notifications and login banners, as `MacOsNotifier.command_for` would run them (`v1-e34-t23`, `t26`) | yes | — |
| `caselist runs` and `caselist runs --json` | — | yes, after a real run and after a refused one |
| The message and hint of an error that stopped a run | yes | yes (the envelope) |
| `debate_core` log lines, INFO and above, with their `extra=` fields | yes | — |

Runs probed: all 10 of `run_record_scenarios.SCENARIOS` (a week imported and published; a publish
answered 503; a publish refused for a missing grant; a week that cannot be read; a publish left for
a login, then drained by `--publish-pending`; drift, then an expiry; an expired `caselist_token`; an
error nobody modelled, whose message carries `/Users/someone/…`; a parse of two weeks; a refusal to
start because the profile is not configured, then the run that publishes its record). Then the dry
run, and camp files fetched, imported, published and cleared by retention, then a nothing-new run.
Then a run another run's lock refused, a camp download the inbox refused with an `OSError` quoting
its path, and a manifest directory this machine refused (`chmod`, skipped as root as
`needs_permissions` does elsewhere). In the CLI: the dry run, three weeks imported and then a
nothing-new run, and a lock refusal.

### Mutation

A script applied each mutant and failed unless its target text appeared exactly once. Each run used
a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`, with 0 entries at the start. The command ran both new
files, `test_caselist_pull.py` and `test_caselist_sync.py` (161 tests), with
`-n0 -p no:cacheprovider --no-cov`. After each run `git checkout HEAD --` restored the file, and
`git diff --quiet HEAD` confirmed it.

| Mutant | Caught by | Result |
|---|---|---|
| The inbox's path put back in the dry-run plan (`into {self._inbox}`) | core and CLI dry-run tests | `2 failed, 159 passed in 60.17s` |
| A path built from the home directory in the dry-run plan (`into {Path.home()}/inbox`) | core and CLI dry-run tests. The core failure reads `"the home directory's probe"`, which I confirmed in a separate run | `2 failed, 159 passed in 59.44s` |
| `summary_written_to` back to `str(written_to)` | CLI run test; `test_a_run_downloads_imports_and_reports_this_weeks_archives`'s new equality | `2 failed, 159 passed in 60.19s` |
| The lock's path put back in `SyncRunInProgress` (`lock held at {lock_path}`) | core `a_run_another_runs_lock_refused`; CLI lock test | `2 failed, 159 passed in 60.42s` |

No test here uses Hypothesis. I isolated the database anyway, as working agreement 8 asks.

**Checks this change could have disarmed.** Five existing assertions opened `summary_written_to`
as a path: three in `test_caselist_pull.py`, one in `test_caselist_pull_parses.py` and one in the
smoke test. Each now joins it to the data directory. Joining a relative path to an absolute one
gives the absolute one, so on their own they would pass the third mutant. That is why
`test_a_run_downloads_imports_and_reports_this_weeks_archives` gained an exact equality, which
caught it. The `already running` substring checks (`test_caselist_pull.py`, `test_caselist_sync.py`)
and the two runbooks that quote it still match, because the message keeps that prefix.

## The sweep: every reason a pull's stages record

I read every `tally.record`, `tally.fail`, `tally.add_to_reason` and `_StageFailure` in
`caselist_sync.py` (56 sites), the sentence helpers they call, `fix_for`, `reported_error_message`,
and the messages of the errors they quote.

| Stage | What its reason is built from | Path? |
|---|---|---|
| select | counts, the ledger window as a UTC time, `_full_archive_reason` (slugs, dates, counts), `_removal_sentence` and `_revision_sentence` (OpenEv ids), `ProviderRateLimited` (`rate limited (retry after Ns)`); for publish-pending, a count | none |
| download (dry run) | **`into {self._inbox}`** | **fixed: `into the inbox`** |
| download | counts, then `_failure` or `_camp_failure` | none: see `_failure` below |
| import (dry run) | counts and fixed text | none |
| import | counts, snapshot names, withdrawn and taken-out counts, `_failure` and `_camp_failure` per archive (`v1-e34-t12`) | none |
| publish | snapshot names, `no local manifest`, SHA-256 digests, `_failure`, `_NO_BUCKET` | none |
| parse | `_parse_stage_sentence` counts, slugs, `_failure`, `StoreCredentialsExpired` (fixed text and the login command), `_FAILURE_RATE_FIX`, `_UNPUBLISHED_PARSED_STORE_FIX` | none |
| landscape | fixed text | none |
| report | `drift.sentence` (snapshots and kinds), `StoreCredentialsExpired`, fixed text | none |
| retention | `InboxRetention.sentence`: `<caselist> <date>` or `sha256 <12 hex>` (`v1-e34-t11`), a failed removal by error class | none |
| any, through `add_to_reason` | `local_only_reason`: `the bucket's copy could not be read without a login (<StoreCredentialsExpired>)` | none |
| `_failure`, `_camp_failure` | a `DomainError`'s own message, or an exception's class and errno; then `_naming_no_local_directory` swaps the inbox and data directory paths, as given and resolved, for their names (`v1-e34-t13`) | none that the probe or a reading found. A `DomainError` quoting a path outside both directories would get through; none does. |
| hints | `fix_for`: `storage.data_dir` by name; the bucket's grant fix and the profile fix (`docs/runbooks/evidence-store.md`, never the AWS config's path) | none |

Outside the stages:

| Output | Before | After |
|---|---|---|
| `SyncRunInProgress`, raised before any stage. `caselist pull` prints it as `error.message`, which the agent's stdout log keeps. The record, built through `redact`, already left the path out | `another caselist sync is already running (lock held at /…/.debate-research/dev/caselist-sync.lock); this run did nothing. …` | `another caselist sync is already running (it holds the run lock, caselist-sync.lock in the data directory); this run did nothing. …` |
| `summary_written_to` in `caselist pull --json`, and so in the failure envelope's `error.details` | `/…/.debate-research/dev/caselist-sync-runs/<run id>.json` | `caselist-sync-runs/<run id>.json` |
| Run record, run log, bucket copy | Already clean: `redact` removes path-shaped words | unchanged |
| Details, notifications, banners | Already clean: `hint_for_a_record` removes absolute and `~/` paths; notifications are built from counts, codes and hints | unchanged |
| `caselist runs`, both forms | Already clean: records and details | unchanged |
| `--verbose` progress lines | `pulling <slugs>`, `completing the publishes an earlier run deferred` | unchanged |

## Files changed

- **`debate_core.application`, `caselist_sync.py`:** the dry run's download reason names the inbox
  by role. `SyncRunInProgress`'s message names the lock by file name in the data directory, and its
  docstring says why. `lock_path` is unchanged.
- **`debate_cli.commands`, `caselist_pull.py`:** `pull_summary` gives `summary_written_to` as
  `caselist-sync-runs/<run id>.json`. Its `written_to` parameter is now typed `Path | None` instead
  of `Any`. The docstring says why.
- **Tests, new:** `packages/debate_core/tests/application/caselist/test_pull_names_no_path_on_this_machine.py`
  (16 tests) and `packages/debate_cli/tests/commands/test_caselist_pull_names_no_path.py` (4 tests).
- **Tests, changed:** `test_caselist_pull.py` (three readers of `summary_written_to`, one new exact
  equality), `test_caselist_pull_parses.py` (one reader), `tests/smoke/test_caselist_pull_in_process.py`
  (one reader).
- **Docs:** `docs/runbooks/caselist-scheduled-sync.md`, the pasting statement under "Watching it".
- **Spec:** the task Goal's phase is `Succeeded`.

## Deviations from the spec

1. **A dry run writes no summary file.** ac1 and the description say the path reached "the JSON
   summary and the summary file". For a dry run only the JSON summary held it: a dry run has written
   nothing since `v1-e34-t02` ac2. The dry-run test asserts that no summary file exists. The
   summary-file half of the criterion is held over every real run's file under ac2 instead. A spec
   wording fix for you to make, if you want one: "a JSON summary and a rendered table, and writes
   no summary file".
2. **Outside `constraints.packages`:** `tests/smoke/test_caselist_pull_in_process.py`, one line,
   because it opened `summary_written_to` as an absolute path; and the scheduled-sync runbook, which
   your notes asked me to keep true.
3. **Two fixes beyond the dry run**, `summary_written_to` and the lock refusal, both found by the
   probe as your notes asked. Neither changes an exit code (the lock refusal still exits `1` as
   `SYNC_RUN_IN_PROGRESS`) or a record's or details' shape.
4. **The runbook statement was corrected, not kept word for word.** "These logs can be pasted into
   an issue as they are" was untrue for the three outputs above. It now says what the probe
   proves, and that summaries and envelopes written before this change may still hold the data
   directory's path in those three places.

## Decisions and assumptions

- **`summary_written_to` as a relative path.** I kept the key, rather than drop it or name it by
  role in words, so that a program can still find the file by joining it to the data directory, as
  `<data_dir>/caselist-sync-runs/` is written throughout the runbook. It is built from
  `RUN_SUMMARY_DIRECTORY` and the file's name, not with `relative_to(data_dir)`, so it cannot raise
  if a caller passes a file somewhere else.
- **No backstop scrub on the summary's reasons.** A blanket "remove any absolute path" pass over
  every stage reason would make each targeted fix one that mutation cannot tell from its absence:
  the dry-run mutant would be scrubbed back to "the inbox" and survive (working agreement 8). The
  probe is the guard instead.
- **The data directory is not under `HOME` in the probe.** In real use it is
  (`~/.debate-research/<env>`). Keeping them apart is what lets the probe tell a string built from
  `Path.home()` from one built from the data directory, and the second dry-run mutant shows the home
  probe catching the first kind.
- **`config show` was left alone**, as the spec says.

## Operator follow-ups

None required. If you want to see it against your own dev environment, this dry run only lists:
it asks OpenCaselist for its listings with your token, and fetches and writes nothing (about 10
seconds). It runs in this task's worktree, which has the change.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e34-t16-dry-run-names-no-home-path
DEBATE_ENV=dev uv run debate-research --json caselist pull --dry-run | grep -c "$HOME"
```

Success looks like `0`.

## Follow-up work

1. **`caselist remove` prints the inbox's path and the lock's path.** Its plan prints
   `DOWNLOAD INBOX (<path>)` (`caselist_remove.py:648-655`) and `"inbox_directory"` in `--json`.
   `InboxInUse` says `it holds <lock path>` (`inbox_purge.py:393`). Neither is a pull output, so
   both are out of scope here. Whether they matter depends on whether a removal's output is
   something you tell people they may paste. If it is, the same treatment belongs to the removal
   epic.
2. **ac1's wording** (Deviation 1).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-18

**Notes:**

Accepted in full, with the phase `Succeeded`.

**The probe did what a probe is for.** It found the known leak and two nobody had written down: the
`--json` envelope's `summary_written_to`, and the lock refusal's message, which the agent's stdout
log keeps. A data directory and a `HOME` under different probes, plus the user's name, means a
string built from `Path.home()` is caught as well as one built from the data directory. The second
dry-run mutant proves that.

**The work itself:**

* **Red first,** with the failing output shown, and the harness's own first bug (`vars(record)`
  carrying the LogRecord's `pathname`) found and fixed before it could hide anything.
* **The probe tested on itself,** both ways: it finds what it must, and passes the fixed wording, a
  setting's name, a docs citation and a URL.
* **No backstop scrub, on purpose.** A blanket path filter would have made every targeted fix
  indistinguishable from its absence under mutation. The probe is the guard, and that reasoning is
  right.
* **Five readers of `summary_written_to` kept honest:** joining a relative path to an absolute one
  would have passed the reverted mutant, so you added an exact equality, and it caught it.
* **The sweep table:** all 56 reason sites read and accounted for.

**Rulings:**

* **`summary_written_to` as a path relative to the data directory:** accepted. The key and type are
  unchanged, nothing in the repository reads it, and the agent never does.
* **Deviation 1, a dry run writes no summary file:** accepted. ac1's wording assumed otherwise. The
  real runs' files are probed under ac2, which covers what ac1 meant.
* **Deviation 2, the smoke test line and the runbook:** accepted.
* **Deviation 3, the two extra fixes:** accepted. They are what the notes asked the probe to find.
* **Deviation 4, the runbook's pasting statement corrected rather than kept:** accepted. It was
  false, and the new one says what is proven, including that older output may still hold the path.
* **Follow-up 1, `caselist remove` printing the inbox and lock paths:** yes, it matters. The removal
  runbook asks the operator to read and keep its output. Added to `v1-e30-t20`, which is about
  what a removal plan prints, in the next PM batch.
