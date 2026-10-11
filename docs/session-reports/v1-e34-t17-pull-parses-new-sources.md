# Session report: v1-e34-t17-pull-parses-new-sources

| | |
|---|---|
| Task | `v1-e34-t17-pull-parses-new-sources` — The weekly pull parses the sources it imported |
| Spec | [`plan_specs/v1/e34-caselist-sync/t17-pull-parses-new-sources.yaml`](../../plan_specs/v1/e34-caselist-sync/t17-pull-parses-new-sources.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t17-pull-parses-new-sources` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`caselist pull` now parses what it imported. After the raw publish, the run hands each caselist it
imported into to the parse pipeline `caselist parse` runs, through a thin adapter
(`PullParseStage`), rebuilds that caselist's aggregates and, where the run publishes, publishes the
parsed store. The stage is **on by default**. The failure rate is judged only in a run that tried at
least 100 sources (ac6), and `caselist parse --publish` exits by `exit_code_for_failure_codes`
(ac7). Six of the seven criteria pass. **ac5 is NOT RUN**: it is the first scheduled run after the
agent is reinstalled, which waits for `v1-e34-t05`'s Wednesday check, so the Goal stays
`InProgress` and this merges with `--partial`.

Four things for the PM to look at first:

1. **The agent has no time limit.** Neither the plist template, the wrapper nor the installed plist
   sets one. The default is therefore argued against the bounds a run does have, in
   [The timing arithmetic](#the-timing-arithmetic-and-the-default).
2. **A failed parse stage leaves the exit code at `0`.** That is `v1-e34-t13`'s rule read
   literally: it reads the required stages, and parse is not one. See Deviation 1.
3. **In the usual week the parsed store will not reach the bucket unattended.** The code's own
   docstring says a weekly run usually finds the SSO session expired. The stage then parses here
   and is `pending`, and `--publish-pending` does not finish it. See Decision 2.
4. **The rebuild is about four weeks from the PM's 900 s line** for hspolicy26, at the last three
   weeks' growth, if rebuild time is proportional to the store. See Follow-up 1.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `parse-stage` — The pull's parse stage is wired | Done, except the first scheduled run | The adapter, the wiring, the setting, the summary counts and the runbook are done. The first scheduled run is ac5 |

## Acceptance criteria

The full suite was run in two halves at the last code commit (`3041816`), after the rebase onto
`origin/dev` at `c3f3cb6`: `uv run pytest packages/debate_core/tests -q` → `3766 passed in 73.24s`,
and `uv run pytest packages/debate_cli/tests packages/debate_api/tests packages/debate_workers/tests tests -q`
→ `1745 passed, 1 skipped, 1 warning in 76.69s`. Together they are the whole default selection:
5,511 passed. The skip is `tests/evals/parser/test_parser_eval.py`,
as on `dev`. `ruff check`, `ruff format --check`, `pyright` (0 errors), `lint-imports` (12 kept),
`scripts/check_thin_handlers.py`, `scripts/check_links.py` and `scripts/check_command_blocks.py` pass.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — a pull that imports a new snapshot parses only that snapshot's new sources, rebuilds the touched caselists' aggregates and, when publishing, publishes them; one that imports nothing parses nothing; counting parser, the first failing first | PASS | `test_caselist_pull_parses.py::test_a_pull_that_imports_a_new_snapshot_parses_only_that_snapshots_new_sources`, through the real composition root. **Failing first**, on the unmodified code: `AssertionError: assert [] == ['0cf11d8ceb4...']`, the parser was asked for nothing. Now: the second pull's parser is asked for `direct` alone, `attempted 1, skipped 6`, and both aggregates hold 7 rows. Publishing, against moto: `test_pull_parses_new_sources.py::test_a_pull_parses_the_new_snapshots_new_sources_rebuilds_the_aggregates_and_publishes_them` (9 objects uploaded, then 3). Nothing imported: `test_a_pull_that_imports_nothing_parses_nothing` and `..._asks_nothing_of_the_stage`: no parser call, no file's modification time moved |
| **ac2** — a parse-stage failure is in the summary with the error code `v1-e34-t13` records, exits as its rule says, and the import and raw publish stand | PASS | Rate: `test_a_failure_rate_over_the_threshold_fails_the_stage_and_nothing_before_it` → `PARSE_FAILURE_RATE_EXCEEDED`. Store unavailable: `test_a_parsed_store_the_bucket_does_not_answer_for_fails_the_stage_with_the_stores_code` → `STORE_UNAVAILABLE`. Crash: `test_a_parse_that_crashes_outright_fails_the_stage_by_its_class_and_the_run_finishes` → `INTERNAL_ERROR`, reason `RuntimeError`; and one worker killed in the real pool, `test_a_worker_that_dies_on_one_source_is_a_failed_source_and_counts_toward_the_rate`. Each asserts both weeks imported, published, confirmed, owed by nothing, the zips gone from the inbox, `succeeded`, and `failure_codes == ()`. Exit: `test_a_parse_stage_over_the_failure_rate_is_reported_and_the_run_still_exits_zero` (exit 0), and beside a retryable publish failure `failure_codes == ("STORE_UNAVAILABLE",)`. See Deviation 1 |
| **ac3** — the summary carries the stage's counts only, schema version bumped if the shape changes | PASS | `parse` is nine integers or `null`; `cards_parsed` and `parse_failures` are gone; `schema_version` is 5. `test_the_summary_says_of_the_stage_nine_integers_and_nothing_else`, `test_the_summary_carries_the_stages_counts_and_nothing_else_under_schema_version_five`. No path, school, team code, file name or card text: `test_nothing_the_pull_prints_or_logs_names_a_school_a_team_a_file_or_a_card` reads stdout, the summary file, the run log and every log record at INFO or above |
| **ac4** — the setting that disables the stage is in the agent runbook with its default and the figures that justify it | PASS | `caselist.parse_imported_sources`, default on. [The parse stage](../runbooks/caselist-scheduled-sync.md#the-parse-stage) has the figures, the arithmetic and how to turn it off for the agent. `test_the_stage_is_on_unless_the_setting_turns_it_off` |
| **ac5** — operator-run: the first scheduled run after the reinstall shows the stage's counts in `caselist runs --last 1` and exits as `v1-e34-t13`'s rule says | NOT RUN | Needs the agent reinstalled with this build, which waits for `v1-e34-t05`'s scheduled-run check on Wednesday. No session can run it. Steps under Operator follow-ups. What it will read is tested: `test_runs_shows_what_the_newest_runs_parse_stage_did` |
| **ac6** — the rate is judged only from a configurable minimum of sources tried; below it failures are reported and do not fail the stage; default and reasoning documented; boundary both sides; a small run over the minimum still fails, failing first | PASS | `parse.failure_rate_minimum_sources`, default 100. **Failing first**: `test_a_run_too_small_for_its_rate_to_be_judged_reports_its_failure_and_exits_zero` gave exit 1, `1 of the 4 source(s) this run tried to read failed (25.0%), above the 20.0% threshold`. Boundary: minimum 5 not judged, 4 judged, 3 judged and failing, at the report (`test_caselist_parse.py`, core), the command (`test_caselist_parse.py`, CLI) and the stage (`test_the_stage_judges_the_rate_from_the_minimum_number_of_sources_tried`) |
| **ac7** — `caselist parse --publish` exits by `exit_code_for_failure_codes`; the pull's stage records those codes; failing first for a bucket that does not answer | PASS | **Failing first**: `test_a_publish_the_bucket_did_not_take_exits_three_and_names_the_code` gave `assert <ExitCode.DOMAIN_FAILURE: 1> == <ExitCode.RETRIEVAL_FAILURE: 3>`. Now 3 for uploads answered 503, and 1 with a checksum mismatch among them. The stage: `test_objects_the_bucket_did_not_take_are_recorded_under_the_publishers_codes` → `CHECKSUM_MISMATCH` and `STORE_UNAVAILABLE` |
| Node: `uv run pytest packages/debate_core/tests/application -k "pull or sync"` | PASS | `285 passed in 13.08s` |

**What "failing first" was run against.** The three tests named above ran on the unmodified code
and failed on their own assertions. The other new command-line tests failed then too, some on an
assertion and some because the settings refused a variable that did not exist yet. The core tests
in `test_pull_parses_new_sources.py` could not run before the adapter existed: they would have
failed at import, which shows nothing. Their evidence is the mutation run below.

## The timing arithmetic and the default

**The agent's time limit: none.** `ops/launchd/com.debate-intelligence.caselist-sync.plist.template`
has no `ExitTimeOut` and no `TimeOut`. `run-caselist-sync.sh` ends in `exec` with no timeout.
`install.sh` adds none. The runbook states none. The installed plist, read with `plutil -p` on
2026-10-11, has neither key: it is `DEBATE_ENV=dev`, three caselists (hsld26, hspolicy26, hspf26),
Wednesday 06:00, `ProcessType` `Background`, `LowPriorityIO`.

**What the stage costs**, from `v1-e31-t06`'s operator run (2026-10-10, 11,126 sources, a terminal,
six workers):

| | hsld26 | hspf26 | hspolicy26 | openev | All four | The agent's three |
|---|---|---|---|---|---|---|
| Rebuild and publish check, nothing new | 348 s | 214 s | 460 s | 60 s | 1,082 s (18.0 min) | 1,022 s (17.0 min) |
| First parse of everything | 518 s | 352 s | 747 s | 106 s | 1,723 s (28.7 min) | 1,617 s (27.0 min) |

* Parsing and uploading: 1,723 − 1,082 = 641 s for 9,741 DOCX sources, so at most 0.066 s each.
* A week's new sources, three caselists: 2,884 in the largest week (2026-09-15), 2,471 in the
  latest (2026-10-06). At 0.066 s: 190 s and 163 s.
* An ordinary scheduled run: 1,022 + 163 = **1,185 s, 19.7 min**. The largest week: 1,212 s,
  20.2 min. With a camp file, 60 s more. After a parser-version bump, all four: **1,723 s, 28.7 min**.

The spec's "roughly 18 minutes" is the rebuild alone. The week's parsing adds about three.

**Against each bound a run has:**

| Bound | Size | The stage, at 20 and 29 min |
|---|---|---|
| A time limit on the agent | None | Nothing to exceed |
| The next scheduled run | 10,080 min | 0.2% and 0.3% |
| The operator's AWS session (`session_duration = "PT8H"`), which only the publish needs | 480 min | 4.2% and 6.0% |
| The PM's line for an incremental rebuild, 900 s for one caselist | 900 s | hspolicy26's 460 s is 51% |

**Default: on.** There is no limit to fit inside, and the stage is a small share of each bound that
exists. Three limits on that conclusion, all in the runbook:

* The figures are a terminal's. The agent runs as a `Background` process with low-priority I/O, and
  the scheduled figure is unmeasured until ac5.
* The rebuild grows with the store (Follow-up 1).
* With no time limit, nothing stops a rebuild that runs long (Follow-up 3).

## Files changed

**`packages/debate_core/src/debate_core/application/`**

* `caselist_pull_parse.py` (new): `PullParseStage`, 82 lines, two methods over
  `CaselistParseService.plan`/`run` and `ParsedStorePublisher.publish`.
* `caselist_sync.py`: the stage's port (two methods, one caselist at a time), `ParsedCaselist`,
  `PublishedParsedStore`, `ParseStageCounts`, `caselists_to_parse`, the rewritten `_parse_stage`,
  the summary's `parse` object and schema version 5, and a "The parse stage" section in the module
  docstring.
* `caselist_parse.py`: `ParseRunReport.tried`, `minimum_sources`, `rate_is_judged`; the service's
  required `failure_rate_minimum_sources`; `PARSE_FAILURE_RATE_EXCEEDED` as a constant.
* `caselist/parsed_publish.py`: `ParsedPublishReport.failure_codes`.
* `settings.py`: `caselist.parse_imported_sources` and `parse.failure_rate_minimum_sources`.
* `sync_runs.py`: a pending parse stage is a publish waiting for a login; a failed one is notified
  with the parse command; the stage's reason is kept whole in the run log.

**`packages/debate_cli/src/debate_cli/`**

* `container.py`: builds the stage over the pull's own suppression list, with the parsed store's
  publisher where there is a bucket, unless the setting is off.
* `commands/caselist_parse.py`: exit by failure codes; `failure_rate_judged`,
  `failure_rate_minimum_sources` and the publish's `failure_codes` in the output.
* `commands/caselist_runs.py`: the caption says what the newest run's parse stage did.
* `commands/caselist_pull.py`: docstring.

**Tests**: `test_pull_parses_new_sources.py` (new, 26 tests, moto), `test_caselist_pull_parses.py`
(new, 8 tests, composition root), and additions to both `test_caselist_parse.py` files,
`test_caselist_sync.py`, `test_caselist_sync_full_archive.py`, `test_caselist_runs.py` and
`tests/smoke/test_caselist_pull.py`. Existing tests were brought to the new shapes.

**`docs/runbooks/caselist-scheduled-sync.md`**: a "The parse stage" section, and the places that
said the stage was skipped.

## Deviations from the spec

1. **A failed parse stage does not change the exit code.** ac2 says the run "exits as
   v1-e34-t13's rule says". That rule reads the stages in `REQUIRED_STAGES`, and its own amended
   ac2 gives the case: "a refusal in report alone exits 0 with report failed, its hint and a
   notification". Parse is the same. A run whose only failure is the parse stage exits `0`, with
   the stage `failed`, its codes recorded, and a notification. Making parse a required stage would
   also break forbidden item 1 in spirit, since `succeeded` would be false for a run that captured
   everything. If the PM meant a non-zero exit, that is a change to the rule, not to this stage.
2. **ac6's rule is in the parse pipeline's own report, so it governs `caselist parse` too.** The
   spec puts "the parse pipeline's own behaviour" out of scope; ac6, added later, states the rule
   for "the parse failure rate" without limiting it to the stage. One rule in one place
   (`ParseRunReport.exceeds_threshold`) seemed right: otherwise the by-hand command that finishes
   a stage would fail on a run the stage had let pass. `caselist parse` on a run under 100 sources
   tried now exits 0 whatever its rate, and says `failure_rate_judged: false`.
3. **Three small changes outside the spec's description, each so that an existing promise stays
   true.** All in `debate_core.application` or `debate_cli`:
   * The failed-stage notification named `caselist pull` as the fix. For a parse failure that
     fixes nothing, because a pull that imports nothing parses nothing. It now names
     `caselist parse --caselist <slug> --publish`.
   * A pending parse stage makes the run record `publish_pending` and adds a sentence to the login
     notification. Without it a run with the parsed store unpublished was recorded `completed`.
   * `caselist runs` shows the newest run's parse sentence under its table. ac5 reads the counts
     there, and the table had no place for them. The run record's schema is untouched.
4. **Read-only looks at the operator's machine**, as the brief allowed for figures. `plutil -p` on
   the installed plist, for the time limit. Two counting scripts over `index.jsonl` of the
   completed `2026.09.20-docx-1` directory in `~/.debate-research/dev/parsed`, for week sizes and
   failures per week. The `2026.10.10-docx-2` directory, which the operator's run is writing, was
   listed by name and not opened. Nothing was written there. Counts only left the machine's files.
5. **Failing first, for the core tests, is the mutation run.** See the note under the criteria.

## Decisions and assumptions

### 1. Scope after a parser-version bump: the plan covers the touched caselists

The PM's preference, and the code agrees. The stage calls `plan(caselist)` with no snapshot.

* **Steady state.** The skip key leaves every source parsed under the running versions alone, so
  what is parsed is the week's new sources. That is ac1, and the counting-parser test shows it.
* **Why not the imported snapshots' sources.** After a bump `_choose_version` starts a new
  directory with nothing recorded. Parsing one week into it leaves aggregates built from that week
  alone, which the publisher then sends as the current store. It also never catches up a source an
  earlier run failed to parse.
* **A directory that is missing.** Every source of the caselist is parsed: a first parse, or the
  first after a bump. The summary counts it in `full_parses` and the stage's sentence says "parsed
  in full, into a version directory that held nothing", so it is not taken for a large week.
  Tested with a bumped parser: 7 attempted, 0 skipped, the old directory byte for byte.
* **A directory partly filled** by a killed run. What is recorded is skipped, the rest is parsed,
  and the aggregates are rebuilt from all of it. Tested: 2 attempted, 5 skipped, `full_parses` 0.
* **A second generation** (`--reparse`, or a profile bump). The stage writes and publishes the
  newest generation. Tested.
* **A caselist the run did not import into** is not touched. After a bump, `openev` stays on the
  old version until a camp file arrives or the operator parses it.
* **The runbook** has the operator run `caselist parse --publish` for all four caselists after a
  release that bumps the parser version, before the agent meets the build, with the dry run that
  shows whether a full parse is due.
* **A complete archive** names no caselist to parse. A run that imported only one would otherwise
  rebuild every aggregate to change none.

### 2. A session that expires during the parsed store's publish

**What is owed:** the bucket's copy of the version directory, for each caselist the stage names.
The parsed store on this machine is whole, because the parse needs no session.

**The import and the raw publish stand** (forbidden item 1). They finish, and are written down,
before the stage starts. The stage writes nothing to the pending-work file. Tested for a session
missing from the start (both weeks still owed, the file's only key is `publish`) and for one that
runs out after the raw publish is confirmed (nothing owed, no file).

**The pending-work file cannot carry it without a schema change.** Every entry must be a target
`caselist publish` accepts (`validate_publish_target`), and a parsed store is a version directory.
A build that met any other entry would refuse the file as `PENDING_WORK_UNREADABLE`, and `write()`
rebuilds the file from snapshot pairs, so an extra key would be dropped by the next raw publish.

**So the operator finishes it with a stated step**, in the runbook under "When the AWS session has
expired": after `aws sso login`, `caselist parse --caselist <slug> --publish`, which parses nothing
already parsed, rebuilds and uploads what the bucket lacks. Or nothing: the next pull that imports
into the caselist with a session publishes the whole directory, because the publisher sends
whatever the bucket lacks. Both are tested. `--publish-pending` is tested to leave it alone.

**The stage is `pending`, not `failed`**, when a login is the only thing missing. `v1-e34-t13`
keeps `pending` for an expired session, and a weekly `failed` stage would teach the operator to
ignore it. Unlike the publish stage's, this pending is in no file. A bucket that refuses or does
not answer is `failed`, with its code.

**Two guards worth knowing about:**

* Once the publish stage has pended, the stage asks the bucket for nothing.
* If the suppression list was read from this machine's copy alone while the aggregates were
  rebuilt, they are not published, even to a bucket that answers. The pull's list falls back to
  the local copy without a login; an aggregate built from it may hold a source a removal elsewhere
  took out. Tested, and mutated.

**What I considered and left for the follow-up.** The owed raw snapshots already name the caselists
whose parsed store is unpublished, so `--publish-pending` could infer it with no schema change. It
covers only an expiry before the raw publish, it would need a rebuild under the full suppression
list before publishing aggregates rebuilt hours earlier (the 18 minutes again), and it changes a
command documented to run no derived stage. Follow-up 2.

### 3. The default for ac6's minimum: 100

Counted read-only from the dev parsed store's `2026.09.20-docx-1` index: new DOCX sources per
caselist per week, and failures. A caselist-week here is a week that brought the store at least one
new source of any format.

| Weeks with | Caselist-weeks | DOCX sources in them | Share |
|---|---|---|---|
| Fewer than 20 new DOCX sources | 19 | 72 | 0.7% |
| 20 to 99 | 5 | 262 | 2.7% |
| 100 or more | 15 | 9,305 | 96.5% |
| **All** | 39 | 9,639 | |

* **Small weeks are common.** In 19 of 39 caselist-weeks one unreadable file is over 5%.
* **The worst batch of unreadable files in one week is 5**: hsld26, 2026-09-15, five
  `MALFORMED_XML` exports of one program, among 1,360. Five is over 5% of any run under 100, and
  exactly 5%, so not over it, of a run of 100. 100 is the smallest minimum at which that batch
  cannot fail a run alone.
* **A camp release is 102 sources**, the PM's own example, so a run that size is the smallest the
  rate is read from.
* **Little is lost.** The 15 judged weeks hold 96.5% of the sources, and every failure recorded so
  far fell in a week of 300 or more.

The other defensible value is **20**, the smallest run in which one file alone cannot cross 5%,
which is how ac6 words the reason. It would also judge the five weeks of 20 to 99 sources, where
two to five files fail a run. I chose 100 because a batch of five has already happened. The worst
week of any kind was 9 failures of 807 (hspolicy26, 2026-10-06), the parser defect `v1-e31-t09`
fixed; that is 1.1% and would not have tripped either value.

What 100 gives up: a parse that fails outright in a week under 100 sources is not a failed stage.
Its `failed` count says so, and the next larger week is judged.

### Other choices

* **The stage's port is two methods, one caselist at a time.** The run decides between them whether
  a publish may follow, and a publish that fails does not cost the counts of a parse that did not.
* **One caselist's failure does not stop the others.** Tested with two caselists.
* **A rate over the threshold does not stop the publish.** `caselist parse --publish` publishes
  what parsed and then reports the rate; the stage does the same.
* **`full_parses` and `not_published`** are in the counts beside the six ac3 names, with
  `caselists`. All integers.
* **Schema version 5** removes `cards_parsed` and `parse_failures`, which no stage ever filled.
* **`test_caselist_pull.py`** turns the stage off in its fixture, as it does the rotation: it
  would start a pool in every test to parse documents with no cards. The stage has its own module.
* **The smoke check** runs the stage as the agent will, with one worker. The pull smoke module
  went from 56.5 s to 64.6 s run serially.

## Mutation results

66 mutants, one at a time against the committed tree, each restored with `git checkout` and the
file compared with its original. Every run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`. **66
caught, none survived, none errored at collection**: every verdict is a count of failed tests
beside passed ones. 64 ran before the rebase; six were run again after it and two were added.

| Aimed at | Mutants | Caught | Examples |
|---|---|---|---|
| The adapter | 16 | 16 | Plans with `reparse=True`; a dry run in place of the run; each count zeroed; `full_parse` always and never; the rate ignoring the minimum; the directory named by the parser version (caught by one test, the second-generation one, written after I saw it would survive) |
| The stage in the run | 20 | 20 | Parses complete archives; one parse per snapshot; runs with nothing imported; lets a crash end the run; publishes after a local-only list; forgets the publish pended; an expired session as a failure; a refused bucket as pending; parses before the raw publish; parse as a required stage |
| The minimum-sources rule | 11 | 11 | `>` for `>=`; always judged; never judged; counting unsupported sources; the rule not applied; not passed to a run or a dry run; zero accepted; the default as 20; the container passing 1 |
| The exit mapping | 6 | 6 | Always 1; always 3; every code `STORE_UNAVAILABLE`; no codes; codes of every object; the output omitting them |
| The summary, the monitor, `caselist runs` | 9 | 9 | Schema left at 4; counts dropped; a parse failure told to pull again; a pending parse recorded as completed; the reason cut at 500 characters |
| The composition root | 4 | 4 | The stage given the local list; no publisher; the setting ignored; off by default |

Three tests were written because a mutant would have survived: the second generation, the dry
run's minimum, and the run log keeping the stage's whole sentence.

## Operator follow-ups

**Before the PR.** Nothing to run. The branch is rebased on `origin/dev` at `c3f3cb6`, which has
`v1-e30-t11`. `scripts/task sync` stopped twice, in `caselist_sync.py`'s `__all__` and in
`tests/smoke/README.md`; both sides were kept in each, and the full suite was run after it. The
merge is `scripts/task pr v1-e34-t17-pull-parses-new-sources --partial`.

**ac5, after `v1-e34-t05`'s Wednesday check and after this build is installed** with
`scripts/install_channel.sh` and the tag the merge publishes, as the runbook's "Before you install
anything" gives it. The installed agent is `dev`, over `~/.debate-research/dev`, for hsld26,
hspolicy26 and hspf26.

1. Check that no full parse is due, with the installed build. `To parse` should be small against
   `Sources` for each caselist. If it is the whole caselist, do
   [the by-hand parse](../runbooks/caselist-scheduled-sync.md#after-a-release-that-bumps-the-parser-version)
   first. Seconds each.

   ```bash
   cd "$HOME"
   DEBATE_ENV=dev debate-research caselist parse --caselist hsld26 --dry-run
   DEBATE_ENV=dev debate-research caselist parse --caselist hspolicy26 --dry-run
   DEBATE_ENV=dev debate-research caselist parse --caselist hspf26 --dry-run
   ```

2. Reinstall and reload the agent, from the main checkout on `dev`, as the runbook's Steps 2 and 3
   give it. Nothing here switches a branch or commits. The first line prints the plist and writes
   nothing; read it, then run the rest. About a minute. Success is `exit code 0` from the last
   line, with the version you installed.

   ```bash
   cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence"
   ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --caselist hspf26 --env dev --debate-research "$HOME/.local/bin/debate-research" --dry-run
   ```

   ```bash
   cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence"
   ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --caselist hspf26 --env dev --debate-research "$HOME/.local/bin/debate-research"
   launchctl bootout gui/$UID/com.debate-intelligence.caselist-sync
   launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
   launchctl print gui/$UID/com.debate-intelligence.caselist-sync
   ops/launchd/install.sh --check-launchd
   ```

3. After the next Wednesday 06:00 run. Seconds.

   ```bash
   cd "$HOME"
   DEBATE_ENV=dev debate-research caselist runs --last 1
   tail -n 1 ~/Library/Logs/debate-research/caselist-sync.jsonl | jq '{status: .status, duration: .data.duration_seconds, parse: .data.parse, stage: [.data.stages[] | select(.stage == "parse")]}'
   launchctl print gui/$UID/com.debate-intelligence.caselist-sync | grep "last exit code"
   ```

   Success: the caption of the first command ends with `Parse stage of the newest run`, its
   outcome and its counts; `parse` in the second holds nine integers with `full_parses` 0; and the
   exit code is 0, or 3 or 1 only if a download, an import or the raw publish failed. In that case
   the second command's `status` is `error` and its other fields are `null`: the same object is
   under `.error.details`. If the SSO
   session had expired, the stage is `pending` and `not_published` is 3: that is the expected
   reading, not a failure of the criterion. Send back `duration`, the `parse` object and the
   stage's outcome. `duration` is the first scheduled figure for the stage under a `Background`
   process, and belongs in `docs/data/caselist-sync-runs.md`.

## Follow-up work

1. **The incremental rebuild is now on a clock (E31).** hspolicy26's rebuild was 460 s over 2,629
   DOCX sources. It gained 816, 300 and 807 sources in the last three weeks, 641 a week. If the
   rebuild is proportional to the store it reaches the PM's 900 s line in about four weeks, and
   `v1-e31-t06` noted it can be worse than proportional. Every scheduled run now pays it.
2. **`--publish-pending` should finish the parsed store's publish (E34).** Since a weekly run
   usually finds the session expired, the bucket's parsed store will usually trail this machine's
   until the operator runs `caselist parse --publish`. Nothing in V1 reads the bucket's copy, and
   one run per caselist catches up however many weeks were missed. Either a pending-work schema
   that names a version directory, or the inference under Decision 2 with its three costs.
3. **Nothing bounds the stage's time (E34).** A rebuild that runs for hours holds the run lock,
   and the next run is refused while it does. A time budget for the stage, or the plist's
   `ExitTimeOut`, would bound it. Related: `caselist parse` by hand does not take the run lock, so
   it can write a version directory while a scheduled pull's stage does.
4. **A timeout or a dead worker is never tried again (E31).** `SourceEntry.retried_next_run` is
   true for `SOURCE_MISSING` alone, so a source whose worker died once in an unattended run stays
   `FAILED` under its skip key until a `--reparse`.
5. **The run record has no parse counts (E34).** They reach `caselist runs` as a sentence. A
   record schema with a `parse` object would let the table show them, at the cost of a record an
   older build refuses.
6. **Two data directories publishing one bucket's parsed store replace each other's aggregates
   (E31).** Prod is published by hand from the dev directory today, which is consistent. The
   runbook says so; nothing enforces it.
7. **A failed parse stage is retried only when its caselist is next imported into (E34).** For
   `openev` that can be weeks. The notification names the command.
8. **`docs/data/caselist-parse-report.md`** says of openev's 4 failures in 102 that "one more bad
   file in a release that size crosses 5%". Five in 102 is 4.9%; it takes six. That file is outside
   this task's packages.
9. **The first scheduled run's figures** belong in `docs/data/caselist-sync-runs.md`, also outside
   this task's packages.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
