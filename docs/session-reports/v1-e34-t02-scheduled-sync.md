# Session report: v1-e34-t02-scheduled-sync

| | |
|---|---|
| Task | `v1-e34-t02-scheduled-sync` — Weekly scheduled sync |
| Spec | [`plan_specs/v1/e34-caselist-sync/t02-scheduled-sync.yaml`](../../plan_specs/v1/e34-caselist-sync/t02-scheduled-sync.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t02-scheduled-sync` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research caselist pull` now does the whole weekly cycle, and `ops/launchd/` packages the
schedule that will run it. `CaselistSyncService` composes the pieces the other tasks built — the
OpenCaselist source (t01), the archive and OpenEv importers (E30 t03/t04), the publisher (t05) and
the status check — into seven named stages: select, download, import, publish, parse, landscape,
report. The three that put bytes somewhere durable are the ones that have to complete; parse
(`v1-e31-t06`) and landscape (`v1-e32-t05`) do not exist, so **the skip path is what the tests
exercise as the normal case**, and neither a missing stage nor a failing one changes the exit code
of a run whose bytes are already safe.

The cadence is weekly and nothing here polls. `docs/policies/caselist-data-use.md` E34 gate 4 is
what fixes that, ADR-0017 is the premise the rest rests on, and the runbook says in as many words
that the interval is not to be shortened without renegotiating the policy with the maintainer.

The four items the `v1-e34-t01` review handed to this task are all implemented and each has a test
named after it: `<inbox>/.partial/` is skipped when the inbox is read; an archive whose name is
already in the inbox is never fetched again, because the client reports `already_present` only
after spending one of the day's five bulk downloads; a `ProviderRateLimited` carrying a day-long
`Retry-After` means "skip today" and the run goes on to import and publish what it has; and an
`UNRECOGNISED` listing is counted and named in the summary but never downloaded, because an
archive with no date cannot be filed as a snapshot.

Two things the PM should look at first. **Deviation 1** is the question the spec does not settle
and which this session deliberately did not decide: whether the weekly run should also refresh
`<slug>-all-<date>.zip`, and how often, against a 5-per-day cap. **Deviation 2** is how the
`report` stage was interpreted, since the spec calls it a remote stage that can pend but puts
run-log storage in `v1-e34-t03`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `sync-service` — CaselistSyncService orchestration | Done | `application/caselist_sync.py` (1,643 lines) and 27 tests. Selection, the round-robin daily budget, the download ledger, the `flock` run lock, `RunSummary`, and the optional-stage ports for E31 and E32 |
| `dry-run-and-deferred-publish` — Dry-run and deferred publish | Done | `plan()` is the dry run *and* the first stage of a real run, so the two cannot disagree. `StoreCredentialsExpired`/`StoreAccessDenied` write `caselist-sync-pending.json`; `publish_pending()` drains it |
| `pull-command` — `caselist pull` and smoke check | Done | `commands/caselist_pull.py`, `container.caselist_sync()`, five new settings, 14 CLI tests through respx and the real client, and `tests/smoke/test_caselist_pull.py` (unmarked, so it runs in CI) |
| `launchd-agent` — template, wrapper and installer | Done | `ops/launchd/` plus `docs/runbooks/caselist-scheduled-sync.md` and 8 installer tests |
| `operator-enable` — operator validates in dev and enables | **NOT RUN** | Operator-only by the spec and by this session's instructions. `docs/data/caselist-sync-runs.md` is created and waiting for the two rows. See Operator follow-ups |

## Acceptance criteria

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — a fake source with two new archives and one new OpenEv file: download, import, parse, publish (moto), report, oldest-first; an immediate re-run downloads nothing and reports "nothing new" with exit 0 | PASS, with `parse` skipped by design | Service level: `uv run pytest packages/debate_core/tests/application/test_caselist_sync.py` → `27 passed in 4.77s`. The scenario is exactly ac1's — `2026-09-01` pre-imported, two new weeklies and one new camp file listed. `test_a_run_downloads_the_new_weeklies_oldest_first_and_imports_them` asserts the fetch order `[…-2026-09-08.zip, …-2026-09-15.zip]` and the hand-derived counts (28 imported, 2 duplicate, 11 new blobs, 8 skipped); `test_a_run_publishes_the_snapshots_it_imported` publishes to moto and asserts 14 objects; `test_an_immediate_re_run_downloads_nothing_and_reports_nothing_new` asserts zero fetches and `nothing_new`. CLI level, through the console script: `uv run pytest tests/smoke/test_caselist_pull.py` → `2 passed in 8.73s`, exit code `0` on the re-run. `parse` is `skipped` with the reason `no parse pipeline is installed (v1-e31-t06 has not shipped)` — the spec's own description requires exactly that; see Deviation 3 |
| ac2 — `--dry-run` prints what it would download and the stages it would run, and leaves the local store, S3 (moto) and the manifests unchanged | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_sync.py -k "dry_run or pending"` → `4 passed in 5.62s`. `test_a_dry_run_lists_what_it_would_do_and_changes_nothing` fingerprints every file under the data directory before and after and asserts equality, asserts `await bucket.list_objects("") == ()`, and asserts no download call was made. The CLI form is `test_a_dry_run_lists_what_it_would_download_and_writes_nothing` (no inbox and no `objects/` directory afterwards) and the first half of the smoke check |
| ac3 — expired S3 credentials: local stages complete, publish and report are pending, `--publish-pending` completes them later | PASS | Same command as ac2. `test_expired_credentials_leave_the_local_stages_done_and_the_rest_pending`: `download` and `import` `completed`, `publish` and `report` `pending`, `caselist-sync-pending.json` written, and the `aws sso login …` hint carried through to the stage reason. `test_publish_pending_completes_what_the_expired_run_left`: after the session is restored, `publish_pending()` uploads the same 14 objects, downloads nothing, and removes the pending file |
| ac4 — a second concurrent run exits immediately with a lock message; each run writes a JSON summary with the named counts and no token or student names | PASS | `test_a_second_run_while_one_is_running_exits_at_once_with_a_lock_message` → `SyncRunInProgress` ("another caselist sync is already running"), with zero fetches, and the lock released afterwards. Through the command: `test_a_second_run_while_one_holds_the_lock_exits_at_once` → exit `1`, `error.code == "SYNC_RUN_IN_PROGRESS"`. The summary: `test_each_run_writes_a_json_summary_with_no_school_team_code_or_token` asserts every count ac4 names (`archives_seen`, `archives_downloaded`, `files_imported`, `files_duplicate`, `cards_parsed`, `parse_failures`, `objects_published`, `reports_written`, `duration_seconds`) and that none of `Maple Grove`, `Cedar Hollow`, `Northgate Prep`, `Riverbend Academy`, `ZaLu` or the word `token` appears in the file; `test_nothing_the_command_prints_carries_the_token` runs the command with a per-test random token and asserts it is on neither stream |
| ac5, first half — `ops/launchd/` has a plist template that passes `plutil -lint`, a wrapper setting DEBATE_ENV and the AWS profile, and an installer whose `--dry-run` renders without loading | PASS | `uv run pytest tests/integration/test_launchd_install.py` → `8 passed in 1.49s`, on macOS (Darwin 25.6.0), so the `plutil -lint` case ran rather than being skipped. By hand: `ops/launchd/install.sh --caselist testcl26 --env dev --dry-run > /tmp/agent.plist && plutil -lint /tmp/agent.plist` → `/tmp/agent.plist: OK`, with `~/Library/LaunchAgents` untouched. `uv run shellcheck ops/launchd/*.sh` → clean |
| ac5, second half — the operator has recorded the dev validation run and the first scheduled run | **NOT RUN** | Operator-only. Running against the live API and enabling a schedule are both outside what this session may do (spec: "Installing and enabling it is an operator step"). `docs/data/caselist-sync-runs.md` exists with the table and states plainly that no run is recorded yet; it deliberately does **not** carry a plausible row. Operator follow-ups 1–3 |

### Node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `sync-service` — Orchestration and idempotency tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_sync.py` → `27 passed in 4.77s` |
| `dry-run-and-deferred-publish` — Dry-run and deferred-publish tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_sync.py -k "dry_run or pending"` → `4 passed in 5.62s` |
| `pull-command` — pull command tests pass offline | PASS | `uv run pytest packages/debate_cli/tests/commands/test_caselist_pull.py` → `14 passed in 7.73s`. Offline: respx answers OpenCaselist and `--disable-socket` is on |
| `pull-command` — pull help renders | PASS | `uv run debate-research caselist pull --help` → exit `0`, listing `--caselist`, `--dry-run` and `--publish-pending` |
| `launchd-agent` — plist template schedules a weekly run (`artifact_exists`, `contentMatch: StartCalendarInterval`) | PASS | `grep -c StartCalendarInterval ops/launchd/com.debate-intelligence.caselist-sync.plist.template` → `3` (the key, and two references in the header comment) |
| `launchd-agent` — installer dry-run renders a lint-clean plist (skipped off macOS) | PASS | `uv run pytest tests/integration/test_launchd_install.py` → `8 passed in 1.49s`. On macOS, so `test_the_rendered_plist_is_one_launchctl_will_load` ran |
| `operator-enable` — first scheduled run is recorded (`artifact_exists`, `contentMatch: scheduled`) | **NOT RUN** | The file exists and contains the word, but the criterion is about a *run that happened*. Reported NOT RUN rather than PASS, because a mechanically matching string over an empty table is exactly the "plausible value" working agreement 6 forbids |
| `operator-enable` — Charlie confirms the agent is loaded | **NOT RUN** | Operator follow-up 3 |

### Whole-repository checks

| Check | Status | Evidence |
|---|---|---|
| Full default suite | PASS | `uv run pytest -q` → `2222 passed in 26.92s`, no failures and no skips outside the opt-in `live` check. This task adds 51 tests that run by default (27 + 14 + 8 + 2) and one that does not (the `live` smoke check) |
| Formatting and lint | PASS | `uv run ruff check .` → `All checks passed!`; `uv run ruff format` leaves the tree unchanged |
| Type checking | PASS | `uv run pyright packages` → `0 errors, 0 warnings, 0 informations` (strict over `debate_core`) |
| Import boundaries | PASS | `uv run lint-imports` → `Contracts: 5 kept, 0 broken` |
| Shell lint | PASS | `uv run shellcheck ops/launchd/install.sh ops/launchd/run-caselist-sync.sh` → clean |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases` |
| CI budget | Within | The three files this task adds to the PR path run in about 20s together (`4.77 + 7.73 + 8.73`), and the whole suite is 27s |

## Files changed

**The service (`packages/debate_core/src/debate_core/application/`)**

* `caselist_sync.py` — new. The run: stages, selection, the daily budget, the download ledger, the
  run lock, the pending-work file, `RunSummary`, and the `CaselistParseStage` / `LandscapeStage`
  protocols E31 and E32 will implement. At the top level beside `evidence_sync.py`, which is the
  path the spec's node output names.
* `settings.py` — `caselist.sync_caselists`, `inbox_dir`, `bulk_downloads_per_day`, `openev_event`
  and `openev_year`, plus `MAX_CASELIST_BULK_DOWNLOADS_PER_DAY = 5` as a ceiling a profile cannot
  raise, alongside the existing per-minute one.
* `ports/caselist_source.py` — `openev_inbox_name` moved here from the client. The sync has to
  know the name a file *will* have before it asks for the bytes, and it may not import the HTTP
  adapter (the import-linter contract); the port is where both sides can agree on it. The client
  still exports it from its old home.
* `caselist/publish_service.py`, `ports/caselist_source.py`,
  `integrations/opencaselist/inbox_writer.py` — three module docstrings rewrote their premise from
  the withdrawn ADR-0016 to ADR-0017. See Deviation 4.

**The command (`packages/debate_cli/`)**

* `commands/caselist_pull.py` — new; `commands/__init__.py` registers `caselist pull`.
* `container.py` — `caselist_sync()`, and `DEFAULT_INBOX_DIRECTORY`. The publisher and the status
  check are `None` when the environment names no bucket, so the run skips with a reason instead of
  failing.
* `tests/test_app.py` — `caselist_sync` added to the services `doctor` reports.
* `README.md` — `caselist pull` named as the first command something other than a person runs.

**The schedule (`ops/`)** — `README.md`, and `launchd/` with the plist template, the wrapper and
`install.sh`.

**Tests** — `packages/debate_core/tests/application/test_caselist_sync.py` (27),
`packages/debate_cli/tests/commands/test_caselist_pull.py` (14),
`tests/integration/test_launchd_install.py` (8), `tests/smoke/test_caselist_pull.py` (2 offline,
1 live and opt-in), `tests/smoke/README.md`.

**Docs** — `docs/runbooks/caselist-scheduled-sync.md`, `docs/data/caselist-sync-runs.md`,
`docs/README.md` (both indexed).

## Deviations from the spec

### 1. Whether a weekly run should also refresh the full archive — raised, not decided

The downloads listing carries two archive kinds per caselist, and ADR-0017 records that only one
`<slug>-all-<date>.zip` is listed at a time because the site regenerates it rather than retaining
it per date. The spec tells this task to pull the weeklies and is silent on the full archive. It
is now implemented as `FULL_ARCHIVE_NOT_PULLED_WEEKLY`: the full archive is listed, counted, named
in every run summary, and never fetched. **This is a placeholder for a decision, not the
decision.** The PM should settle it, and here is what I would say if asked:

* **For refreshing it periodically.** ADR-0017 makes the full archive the corpus, and the weeklies
  a history. A weekly-only sync drifts from the corpus in one direction that the weeklies cannot
  correct: `REMOVED` is only meaningful against the full archive (ADR-0017 decision 5), so a file
  withdrawn between two full archives is invisible to a run that never fetches one. Over a season
  the store accumulates files that are no longer disclosed anywhere.
* **Against fetching it weekly.** It is the largest download the site serves, it is one of five a
  day for every caselist it is fetched for, and almost all of its contents are bytes the store
  already holds — content addressing means it costs nothing on disk, but it costs the allowance.
  With three caselists, a weekly full archive plus a weekly delta is six of the five.
* **What I would propose**, for the PM to accept or replace: monthly, one caselist per week on a
  rotation, so the full-archive fetch is one extra download in any given run and every caselist is
  refreshed within a month. That fits the cap without a special case, and it puts an upper bound on
  how long a withdrawal can go unnoticed. It needs a spec change — a new criterion and a setting —
  which is why it is not in this PR.
* Not in scope either way: the back-catalogue fetch of the eight older weeklies, which is
  `v1-e30-t06`'s.

### 2. What the `report` stage is

The spec's description groups "the S3 publish and report steps" as the two that need credentials
and can be recorded as pending (ac3 says the same), while listing run-log storage as out of scope
and `v1-e34-t03`'s. Those two statements cannot both be satisfied by a report stage that writes a
run log to S3.

Implemented reading: **the report stage confirms, in the bucket, the snapshots this run says it
published** — one `caselist status` per published snapshot. It is remote, so it pends with publish
exactly as ac3 requires; it writes nothing to the bucket, so it does not step on t03. The run's
own JSON summary is written locally at the end of every real run regardless, which is what ac4
requires. If the PM meant "publish the run summary object to S3", that is a one-line change to this
stage once t03 defines the key it goes under.

Related, and smaller: the report stage checks each published snapshot by name rather than the
whole caselist. A caselist-wide check reported a snapshot imported before this run and never
published as drift *of this run*, which it is not; completing that one is `caselist publish`'s job.

### 3. Stage order: publish before parse

ac1 lists the stages as "downloads, imports …, parses, publishes (moto) and reports". The spec's
description says the opposite and gives the reason: "the run still completes download, import and
publish before anything optional, because those are the stages that put bytes somewhere durable".
The description is what is implemented — select, download, import, publish, parse, landscape,
report. No behaviour ac1 describes is missing; only the order of two words differs. ac1's text
could be brought into line when the spec is next touched.

### 4. Three docstrings rested on a withdrawn ADR

`ports/caselist_source.py`, `integrations/opencaselist/inbox_writer.py` and
`caselist/publish_service.py` each justified a rule with ADR-0016's "a download is a window and a
dropped one is gone", which ADR-0017 supersedes. All three rules are still right; two of the three
premises under them are not. I rewrote the three passages against ADR-0017 rather than leave a
withdrawn premise in the files this task's own module reads and extends — that is the failure
working agreement 7 was written about. No behaviour changed, and the port's section keeps one line
saying what it used to rest on.

### 5. Files touched outside the spec's `packages` constraint

The constraint lists `debate_core.application`, `debate_cli.commands`, `ops/launchd` and
`tests/smoke`. Also changed, each for a reason the task cannot avoid:

* `debate_core.application.ports.caselist_source` — `openev_inbox_name`, above.
* `debate_core.application.settings` — the five settings a run reads.
* `debate_cli.container` — the composition root is the only place a command may obtain a service.
* `debate_core.integrations.opencaselist.openev` and `…inbox_writer` — the re-export and one
  docstring.
* `packages/debate_cli/tests/commands/` and `tests/integration/` — the two test paths the node
  criteria name.
* `docs/`, `ops/README.md`, `packages/debate_cli/README.md`, `tests/smoke/README.md` — the runbook,
  the data log and their index entries.

### 6. `sync_caselists` takes JSON in the environment

`DEBATE_CASELIST__SYNC_CASELISTS` must be JSON (`["hsld26"]`), because pydantic-settings decodes a
list-valued variable before any validator of ours sees it. That is true of every list setting in
the module, not something this task introduced. A profile file takes a TOML list, and the launchd
agent passes `--caselist` flags, so nothing in the shipped path uses the environment form.

## Decisions and assumptions

* **The daily budget is shared round-robin across caselists**, oldest-first within each. Globally
  oldest-first would let one caselist with a back-catalogue spend the whole allowance every week
  and starve the others. What gets deferred is always a caselist's *newest* archive, which is the
  one certain to still be listed next week.
* **The budget is a day's, not a run's.** `<data_dir>/caselist-sync-downloads.json` records what
  has been spent today, so a second run on the same day starts from what is left. Its day is the
  clock's UTC date, which can differ from the server's day boundary by hours; the effect is at
  most that a run is a little more cautious than it needed to be.
* **A rate limit is "not today" when `Retry-After` is an hour or more** (`SKIP_TODAY_SECONDS`).
  Below that the transport has already slept through what it could, so anything longer means no
  further archive is coming today, whatever number the server chose to state.
* **A dry run takes the run lock** — it reads the inbox and the manifests, and a real run writing
  them underneath it would make its plan fiction — but writes no run summary, because ac2 says the
  local store is left unchanged. The summary is still returned and printed.
* **A publish that fails for a reason other than credentials is added to the pending-work file
  too**, so the next run retries it. The stage is `FAILED` rather than `PENDING`, so the exit code
  is 1 and the operator sees it; the pending entry is what stops it being quietly dropped.
* **`UNRECOGNISED` listings are never downloaded.** The importer files snapshots by date and orders
  them by date; an undated archive has no place in that. It is counted and named in the summary so
  that a naming change upstream is a number somebody sees rather than a silently empty run.
* **A caselist whose event this build does not know is downloaded but not imported.** The event
  decides whether `Aff` or `Pro` is a legal side, so a guess would mis-file a whole archive. The
  bytes stay in the inbox, the import stage fails with the message naming the table to add the slug
  to, and the other caselists in the same run still import.
* **`event_for_caselist` is passed from the command, not read by the container.** The slug-to-event
  table is `debate_cli.commands.caselist`'s; a composition root that imported a command module to
  reach it would have the dependency the wrong way round.
* **The inbox default is `<data_dir>/inbox`**, so one environment is one directory and a dev pull
  can never drop an archive where a prod import would read it.
* **An OpenEv download that is not a `.zip` becomes one member named as it sits in the inbox**,
  which is the name the camp-metadata parser already strips the `openev-<id>-` prefix from. A
  `.zip` goes through the archive reader. Both are tested.
* **The live smoke check lists and never downloads**, and is skipped unless `CASELIST_LIVE_SLUG`
  is set. A live download would spend one of the five for nothing the respx test does not prove.
  The *offline* smoke check is deliberately unmarked so it runs in CI: a `live` marker there would
  have made the one check covering the scheduled command collect-and-skip while looking green.
* **Every expected value in this task's tests is hand-written.** The import counts come from the
  committed, hand-written `expected_summary.json` and `expected_openev_import.json` with the
  arithmetic written out in the test docstring; the publish count (14 source objects for the three
  synthetic weeks) was derived by hand from the fixture tables before it was run, and independently
  matches `expected_publish.json`'s `totals.source_objects`.

## Operator follow-ups

Nothing below can be done from a session: two of them run against the live site and one puts a
schedule on your Mac.

**1. Validate the pipeline in dev** (expected runtime: a few minutes, mostly download)

Where: your Mac, anywhere — this uses your installed `debate-research`, not the worktree.

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true \
    debate-research caselist pull --caselist hsld26 --dry-run
```

Success: exit `0`, a stage table whose `select` row lists the archives the site has, and a caption
saying what it *would* download. Nothing is written. Read the decisions column before going on —
`already_imported`, `full_archive_not_pulled_weekly` and `unrecognised_name` are all normal.

Then the real run:

```bash
DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true \
    debate-research caselist pull --caselist hsld26
```

Success: exit `0`, with `publish: completed` and `report: completed`. `parse: skipped` and
`landscape: skipped` are expected — E31 and E32 have not shipped. Paste the caption line and the
stage table back into the session, and record the counts in `docs/data/caselist-sync-runs.md`.

**2. Install and enable the weekly agent** (expected runtime: under a minute)

Where: your Mac, in this worktree (the installer lives here).

```bash
ops/launchd/install.sh --caselist hsld26 --env prod --dry-run   # read it first
ops/launchd/install.sh --caselist hsld26 --env prod
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
launchctl print gui/$UID/com.debate-intelligence.caselist-sync
```

Success: `install.sh` prints where it wrote the plist; `launchctl print` shows the job with its
program arguments and a `StartCalendarInterval` of Wednesday 06:00. Nothing runs at load.
`docs/runbooks/caselist-scheduled-sync.md` has the whole procedure, including how to disable it.

**3. Record the first scheduled run** (after the following Wednesday)

```bash
tail -n 1 ~/Library/Logs/debate-research/caselist-sync.jsonl | jq .data
debate-research caselist status --caselist hsld26
```

Success: the summary's `objects_published` agrees with what `caselist status` says is in the
bucket, and `succeeded` is `true`. Add the row to `docs/data/caselist-sync-runs.md` with
"How it started" = `scheduled`. That closes ac5's second half and both `operator-enable` criteria.

**4. Confirm the other two caselists behave like `hsld26`** — ADR-0017's last consequence says
`hspolicy26` and `hspf26` are *assumed* to publish the same two archive kinds and that this is
confirmed before the backfill runs. `caselist pull --caselist hspolicy26 --dry-run` answers it
with one listing call and no download.

## Follow-up work

* **The full-archive question (PM).** Deviation 1. It needs a spec change, in this epic or in
  `v1-e30-t06`, before anything fetches an `-all-` archive on a schedule.
* **`v1-e34-t03-sync-monitoring`** inherits three things it can build on directly: the per-run JSON
  summary and where it is written (`<data_dir>/caselist-sync-runs/<run id>.json`, and
  `caselist-sync.jsonl` for scheduled runs), the `pending_publish` list as the signal that a run
  finished without publishing, and the `stages[]` array as the thing a failure notification should
  quote. If it wants the summary in S3, the `report` stage is where that goes (Deviation 2).
* **`v1-e31-t06-parse-pipeline`** implements `CaselistParseStage`: one method,
  `parse_new_sources(*, caselists) -> ParseStageResult(files_parsed, cards_parsed, failures)`.
  `v1-e32-t05-landscape-cli` implements `LandscapeStage.regenerate(*, caselists) ->
  LandscapeStageResult(reports_written)`. Both are protocols in `caselist_sync.py` with the shapes
  the run summary already has fields for; if either task wants a different shape, the protocol is
  the place to change it and the container is the only wiring.
* **A shellcheck pre-commit hook.** `shellcheck` is already a dev dependency and
  `tests/integration/test_launchd_install.py` runs it over `ops/launchd/`, but there is still no
  hook covering the repository's shell scripts generally. `v1-e36-t05` was noted as the first
  script with a lint criterion; a hook would cover both.
* **A caselist CLI guide.** `docs/guides/evidence-store-cli.md` covers `store`; `caselist
  import|publish|status|pull` has a runbook for the schedule but no guide for the commands. Worth
  a task once E30 and E34 are both complete.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-09-23

**Notes:**

Accepted, and merging with `--partial`: ac5's second half and both `operator-enable` criteria are
genuinely operator-only, so the Goal stays `InProgress` until the two runs are recorded.

**Spec amended in this branch, three changes.**

1. **ac1 was wrong and the implementation is right.** ac1 listed `parse` between import and publish;
   the spec's own description says publish comes before anything optional, "because those are the
   stages that put bytes somewhere durable", and `v1-e31-t06` does not exist, so ac1 as written was
   unsatisfiable. ac1 now names the implemented order and says the skip path is the case it is
   tested against. Deviation 3 is closed — the session read the description correctly and flagged
   the clash instead of quietly passing either way, which is what should have happened.
2. **Deviation 2 accepted as the reading.** The description now says the report step confirms the
   run's published snapshots in the bucket and writes nothing there, so it can pend with publish
   under ac3 without stepping on t03. Checking by snapshot name rather than caselist-wide is right
   for the same reason: drift from an earlier run is not this run's to report.
3. `status.phase` returned to `InProgress` (see above).

**Deviation 1 — the full archive — decided, and it is not this task's.**

No policy interval governs it. Removal under `docs/policies/caselist-data-use.md` is
**request-driven by email**, with the 7-day clock running from the request, and the policy is
explicit that taking a disclosure off OpenCaselist is the site's act, not a request to us. So
`REMOVED` detected by diffing a full archive is an analytical signal, not a compliance obligation,
and the interval is a cost question against the 5-per-day cap rather than a deadline.

The session's proposal is accepted: **monthly, one caselist per week on a rotation**, which is one
extra download in any given run and bounds how long a withdrawal goes unnoticed at about a month.
It goes to **`v1-e30-t06-initial-backfill`**, not here and not a new task — t06 already fetches the
full archive for the back-catalogue, and there is nothing to refresh until it has run once. The
shipped `FULL_ARCHIVE_NOT_PULLED_WEEKLY` decision is the correct placeholder meanwhile: listed,
counted, named in every summary, never fetched.

Separately, and not blocking: whether a disclosure withdrawn from OpenCaselist should itself trigger
suppression on our side is a **policy question**, not an engineering one. The policy says withdrawal
is respected but routes it through email only. If the answer turns out to be yes, the refresh
interval stops being a cost question and this decision gets revisited. Raised against
`v1-e30-t07-source-removal`.

**Deviations 4, 5 and 6 accepted without change.** Rewriting three docstrings off the withdrawn
ADR-0016 (Deviation 4) is working agreement 7 applied correctly, and the diff is prose only. The
`openev_inbox_name` move to the port (Deviation 5) is forced by the import-linter contract and is a
pure move with the old export kept. None of the out-of-scope files exceed what the work required:
`settings.py` and `ports/` are inside `debate_core.application`, and `container.py` is the only
place a command may obtain a service.

**Checks I ran rather than took on the report's word.**

* `_log_summary` emits counts, caselist slugs, dates and stage names only, and says so in its
  docstring. Policy rule 4 holds; the slug is permitted by rule 3's own key format.
* The inbox is read once in `plan()` and passed into selection, so `ALREADY_IN_INBOX` is a
  selection decision taken **before** any download. That is the fix the t01 review asked for — the
  client reporting `already_present` after streaming the file would have spent one of the five.
* The out-of-scope diff is 12 insertions and 16 deletions across three files, all prose plus the
  one function move.

**Backlog raised by this review, not against this task:** the kickoff prompt in
`scripts/task_helper.py` tells every session to finish by setting the phase to `Succeeded`, with no
mention of the partial case, which is why a task with two operator-only criteria arrived marked
`Succeeded`. `scripts/` is being rewritten by `v1-e01-t05` right now, so this waits for that to
merge.
