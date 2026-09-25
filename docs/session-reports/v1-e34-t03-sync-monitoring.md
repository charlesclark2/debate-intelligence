# Session report: v1-e34-t03-sync-monitoring

| | |
|---|---|
| Task | `v1-e34-t03-sync-monitoring` — Sync run log and staleness warnings |
| Spec | [`plan_specs/v1/e34-caselist-sync/t03-sync-monitoring.yaml`](../../plan_specs/v1/e34-caselist-sync/t03-sync-monitoring.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t03-sync-monitoring` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> — one ac5 measurement is an operator follow-up |

## Summary

Every real `caselist pull` now leaves exactly one `SyncRunRecord` (Pydantic, `extra="forbid"`). The
record goes to `<data_dir>/caselist-sync-runs.jsonl` and to `reports/sync-runs/<yyyy>/<run-id>.json`
in the bucket. That includes runs that raise before or during the pipeline. The bucket upload is
deferred like other publish work when the SSO session has expired, and the next run publishes it.
A `Notifier` port (osascript on the Mac, null elsewhere and in every test) posts one notification
per condition, each naming its fix: a failed stage, `CaselistAuthExpired`, an expired SSO session,
and a cap backlog that has grown two runs in a row. `debate-research caselist runs [--last N]
[--remote]` lists recent runs and says when the schedule appears to have stopped.

The measured defect is fixed: a run the daily cap blocked is no longer `nothing_new`. The select
stage, download stage, caption and record now state wanted and deferred counts. The stale-data
banner for ac3 is a **hook**, because the landscape renderer (`v1-e32-t03`/`t05`) does not exist
yet. Look at that Deviation first, then the ac5 measurement under Operator follow-ups.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| (ac5/ac6 fix, before the nodes) | Done | The cap-blocked "Nothing new" was reproduced in a test on unchanged code first (see Decisions), then fixed in `caselist_sync.py` |
| `run-record` — SyncRunRecord and run log persistence | Done | `application/sync_runs.py`: record, JSONL log, bucket publication with a pending-records file, `redact()` |
| `notifier` — Notifier port with macOS and null adapters | Done | `ports/notifier.py` (`Notifier`, `NullNotifier`, `RecordingNotifier`), `integrations/local/macos_notifier.py`; `caselist.notifier` setting |
| `sync-hooks` — hook run records and notifications into the sync | Done | `SyncRunMonitor.watch()` wraps the pull from outside the service (see Deviations) |
| `staleness-banner` — stale-data banner in landscape reports | Done as a hook | `application/landscape_staleness.py`; `caselist.stale_after_days` (8) |
| `runs-command` — `caselist runs` command and smoke check | Done | `commands/caselist_runs.py`, `tests/smoke/test_caselist_runs.py`, runbook updated |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — each pull, successful or failed, produces exactly one validated SyncRunRecord locally and at `reports/sync-runs/<yyyy>/<run-id>.json` (moto) | PASS | `uv run pytest packages/debate_core/tests/application/test_sync_runs.py` → 11 passed (one-record-per-run for success and for a raising run, moto publication, expired-session deferral then publication of both, schema refuses unknown fields). `uv run pytest tests/smoke/test_caselist_runs.py` → 1 passed (pull → record in local log and bucket) |
| ac2 — a failing stage, CaselistAuthExpired and an expired SSO session each trigger one notification naming the fix, verified with a recording notifier | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_sync.py -k "run_record or notify or redact"` → 8 passed: failed download → one notification, fix `debate-research caselist pull`; `CaselistAuthExpired` → one, fix `debate-research caselist auth login`; expired SSO → one, fix `aws sso login --profile debate-dev-evidence && debate-research caselist pull --publish-pending` |
| ac3 — banner at nine days, none at seven, CSV metadata `stale=true` | PASS (against a stand-in report) | `uv run pytest packages/debate_core/tests/application/test_landscape_staleness.py` → 7 passed (9 days: banner first line names 2026-09-15 and `stale=true`; 7 days: report unchanged, `stale=false`; 8 days is the last current day; configurable threshold; no snapshot is stale). No real landscape report exists yet; see Deviations |
| ac4 — `caselist runs --last 5` shows run id, start, outcome, downloaded, cap-deferred, pending publish; redaction test | PASS | `uv run pytest packages/debate_cli/tests/commands/test_caselist_runs.py` → 9 passed (`--last 5` table headings and JSON, overdue schedule, `--remote` without a bucket). Redaction: `test_redact_no_fixture_token_or_student_name_reaches_a_record_or_a_notification` plants the fixture token and a synthetic student name (`Juniper Okafor`) in a disclosure path in an `OSError`, then searches the local log, the moto object and every notification. `test_redact_an_expired_token_run_record_carries_neither_the_token_nor_a_path` does the same through the command |
| ac5 — a cap-truncated run is visibly different: select detail, caption and record state wanted and deferred; deferred carried as a backlog the next run reports | PASS | `uv run pytest packages/debate_core/tests/application/test_caselist_sync.py -k "cap or nothing_new"` → 7 passed (select detail `1 to fetch of 2 wanted, 1 deferred by the daily download cap`). CLI: `test_a_truncated_pull_states_wanted_and_deferred_and_the_next_run_carries_the_backlog` (caption `2 of 3 wanted archive(s)`, next record `backlog_carried == 1`). `test_sync_runs.py`: backlog 1→3→5 flags `hsld26`; 7,7,7 (the dev day's reruns) does not |
| ac5 — "Measured on a real dev run of three caselists before the notification thresholds are chosen" | NOT RUN | Needs the live API, the operator's token and a day's downloads. The threshold implemented is the spec's own rule (grows for two runs), in `BACKLOG_GROWTH_RUNS`. See Operator follow-ups and Deviations |
| ac6 — `nothing_new` distinguishes nothing to fetch from not allowed to fetch; caption says how many wait; staleness treats a cap-bound run as not current | PASS | Reproduced first on unchanged code (see Decisions). After the fix: `test_a_run_the_cap_blocked_entirely_is_not_nothing_new`, `test_an_immediate_re_run_with_nothing_deferred_is_still_nothing_new`, CLI `test_a_cap_blocked_pull_is_not_captioned_nothing_new` (caption `Nothing fetched: 3 archive(s) wanted and all 3 deferred by the daily download cap`), staleness `test_a_cap_bound_run_makes_a_fresh_snapshot_stale` and `test_a_later_run_that_fetched_the_backlog_makes_it_current_again` |
| Node `run-record`: `uv run pytest packages/debate_core/tests/application/test_sync_runs.py` | PASS | 11 passed in 5.30s |
| Node `notifier`: artifact `application/ports/notifier.py` contains `class Notifier(Protocol)` | PASS | `grep` → line 61 |
| Node `sync-hooks`: `uv run pytest …/test_caselist_sync.py -k "run_record or notify or redact"` | PASS | 8 passed in 4.41s |
| Node `staleness-banner`: `uv run pytest …/test_landscape_staleness.py` | PASS | 7 passed in 3.98s |
| Node `runs-command`: `uv run pytest packages/debate_cli/tests/commands/test_caselist_runs.py` | PASS | 9 passed in 6.72s |
| Node `runs-command`: `uv run pyright packages/debate_core` | PASS | 0 errors, 0 warnings, 0 informations |
| Full default suite (not a spec criterion) | PASS | `uv run pytest` → 2384 passed, 1 skipped in 28.97s (30s wall) |
| Lint, format, import contracts (not spec criteria) | PASS | `uv run ruff check .` → all passed; `uv run ruff format --check .` → 348 files already formatted; `uv run lint-imports` → 5 kept, 0 broken |
| `uv run scripts/validate_specs.py` | PASS | `OK: 284 files, 38 epics, 226 tasks, 20 releases`; `--require-succeeded v1-e34-t03-sync-monitoring` → Succeeded |

`uv run pyright packages/debate_cli tests/smoke` reports one error, in `tests/smoke/test_site.py:44`
(`import site_smoke`). This task did not touch that file. The import resolves only when the check
runs from `scripts/`.

## Files changed

**`debate_core.application` (new)**
* `sync_runs.py`: `SyncRunRecord`, `SyncRunLog` (JSONL), `SyncRunMonitor`, `SyncRunHistory`,
  `redact()`, `notifications_for()`, `read_remote_records()`.
* `landscape_staleness.py`: `LandscapeStalenessCheck`, `assess_staleness`, `with_stale_banner`,
  `with_staleness_metadata`.
* `ports/notifier.py`: `Notifier`, `Notification`, `NullNotifier`, `RecordingNotifier`. Also
  re-exported from `ports/__init__.py`.

**`debate_core.application` (changed)**
* `caselist_sync.py` (t02's module; see Deviations for exactly what).
* `settings.py`: `SyncNotifierKind`, `caselist.notifier`, `caselist.stale_after_days`.

**`debate_core.integrations`**
* `local/macos_notifier.py`: `MacOsNotifier`, which passes the text to osascript as argv.

**`debate_cli`**
* `commands/caselist_runs.py` (new) and its registration in `commands/__init__.py`.
* `commands/caselist_pull.py`: runs under the monitor, adds `run_record` to the JSON and changes the caption.
* `container.py`: `caselist_sync_monitor`, `caselist_sync_history`, `sync_notifier`.

**Tests**
* New: `debate_core/tests/application/test_sync_runs.py`, `test_landscape_staleness.py`,
  `debate_cli/tests/commands/test_caselist_runs.py`, `tests/smoke/test_caselist_runs.py`.
* Additions to `test_caselist_sync.py`: the cap tests and the monitor tests.
* `debate_cli/tests/test_app.py`: the pinned container service list gains the two new services.
* `tests/smoke/test_caselist_pull.py`: its dev profile now pins `notifier = "none"`.

**Config and docs**
* `config/profiles/test.toml`: `[caselist] notifier = "none"`.
* `tests/smoke/README.md`: a row for the new smoke check.
* `docs/runbooks/caselist-scheduled-sync.md`: *Watching it* covers notifications, `caselist runs` and the new counts.

**Spec**
* The task Goal phase is now `Succeeded`.

## Deviations from the spec

1. **t02's module was changed, only for ac5/ac6.** In
   `packages/debate_core/src/debate_core/application/caselist_sync.py`:
   * `ArchiveSelection.deferred_by_cap` (new property) and the `_DEFERRED_BY_CAP` constant.
   * `SyncPlan.nothing_new` and `RunSummary.nothing_new` exclude cap-deferred runs.
   * `RunSummary.archives_wanted` and `archives_deferred` are new properties; `as_json()` gains
     the keys `archives_wanted` and `archives_deferred`.
   * The select stage's detail states wanted and deferred counts when they differ. The download
     stage's skip reason, when the cap blocked everything, now says so instead of "nothing new to
     download".

   In `packages/debate_cli/src/debate_cli/commands/caselist_pull.py` (t02's command): the caption
   states wanted and deferred counts and the carried backlog. The command also runs under the
   monitor, and its JSON gains `run_record`. Nothing else in either file was refactored.
2. **The hooks are outside `CaselistSyncService`, not inside it.** The node says "hook run
   records and notifications into CaselistSyncService". Doing that literally would have meant
   refactoring t02's module beyond ac5/ac6. `SyncRunMonitor.watch()` wraps the pull instead, and
   `caselist pull` always goes through it. That also records refusals raised before the service
   exists, such as the API not being turned on or no caselist being configured.
3. **ac3 is delivered as a hook, tested against a stand-in report.** No landscape report
   generator exists: `v1-e32-t03` and `v1-e32-t05` are `Pending`. `landscape_staleness.py` is what
   they will call. The CSV "header block" format is `v1-e32-t03`'s to define, so this task supplies
   the metadata as a mapping (`stale`, `newest_snapshot`, `snapshot_age_days`,
   `archives_awaiting_download`) for that block to merge. **The PM should add "call
   `LandscapeStalenessCheck` and `with_stale_banner`" to `v1-e32-t03`/`t05`**, because this task
   may not edit those specs.
4. **A failed optional stage still exits 0.** The spec's forbidden list says "every failure
   yields a non-zero exit, a run record and a notification". `v1-e34-t02` deliberately exits 0 when
   parse or landscape fails (documented in `caselist_pull.py`). This task records and notifies
   every failed stage, optional ones included, and left t02's exit-code rule alone. The PM should
   decide which rule stands.
5. **A run that did not happen at all.** The spec's description says monitoring "still fires on
   a run that did not happen at all", but no criterion covers it. What is built:
   `caselist runs` reports `overdue` and says "the schedule may have stopped" when the newest
   record is more than `stale_after_days` old (or there is none), and the runbook points there.
   Nothing *pushes* a notification for a missed run: that needs a second trigger independent of
   the job that failed to run, such as a launchd watchdog. See Follow-up work.
6. **The ac5 measurement is not run** (live, credentialed, spends real downloads). See Operator
   follow-ups. The implemented threshold is the spec's own sentence.
7. **Dry runs leave no record.** `v1-e34-t02` ac2 says a dry run writes nothing. ac1's "each pull
   run" is read as each real run.
8. **A configuration file outside the stated packages:** `config/profiles/test.toml`. It makes
   `notifier = "none"` explicit for `test`, although `auto` already never notifies there.

## Decisions and assumptions

* **Reproduction first (task note 1).** The first attempt to reproduce did not show the defect:
  the shared test scenario lists one OpenEv file, and downloading it made `nothing_new` false. The
  dev runs fetched no OpenEv files, so the cap tests list none either. On unchanged code, with the
  day's allowance spent, the result was:
  * `nothing_new= True succeeded= True`
  * decisions `['already_imported', 'full_archive_not_pulled_weekly', 'over_daily_budget', 'over_daily_budget', 'unrecognised_name']`
  * select stage: `5 archive(s) and 0 OpenEv file(s) listed; 0 to fetch`
  * download stage: `nothing new to download`

  That is the measured defect exactly.
* **A cap-bound run counts as not current for the stale-data banner (task note 3).** The spec's
  ac6 already says so; the reasoning follows.
  * `within_daily_budget` fetches a caselist's oldest wanted archives first, so what the cap
    defers is always its *newest*.
  * `_decide_archive` only ever wants archives dated after the newest held snapshot.
  * So every deferred archive is a published week the landscape does not contain, however young
    the newest snapshot is.

  The check reads the latest run record that listed the caselist. A later run that fetched the
  backlog clears it.
* **A later run clears the stale flag.** The flag keys on the *latest* run that listed the
  caselist, not on any run in history. Otherwise the flag would stick after the backlog was gone.
* **Both cap signals count as "deferred by the cap".** The run's own budget
  (`OVER_DAILY_BUDGET`) and the server's day-long `Retry-After` (`DEFERRED_BY_RATE_LIMIT`) both
  count.
* **Backlog growth is tracked per caselist.** A caselist is flagged when its deferred count rose
  at each of the last two runs that listed it (three data points, strictly increasing). A flat
  7, 7, 7 (the dev day's reruns) is not growth.
* **Notification text is built from counts, slugs, stage names and error class names only**,
  never from an exception message, so the screen cannot show what a record may not hold.
  * Records keep redacted messages for `DomainError`s only.
  * Any other exception keeps its class and no message, because its text was not written by this
    project.
  * `redact()` removes registered secrets (the settings token), `caselist_token=` values, URL
    queries and anything path-shaped, quoted or not.
* **osascript text travels as argv**, and the AppleScript itself is a constant. That is stronger
  than escaping, which the node description suggested. It is tested with a hostile `" & (do shell
  script …)` message.
* **The SSO notification also covers `StoreAccessDenied`.** It fires when publish or report
  pended, or when the record's own upload raised `StoreCredentialsExpired`, and uses the adapter's
  own login hint when it has one. t02 pends publish on `StoreAccessDenied` as well, so the same
  notification covers that case too.
* **Outcome precedence:** `failed` > `publish_pending` > `incomplete` > `cap_deferred` >
  `nothing_new` > `completed`. The record's fields keep the detail that one word cannot.

## Operator follow-ups

1. **The ac5 measurement: a real dev run of three caselists** (live API, your token, spends real
   downloads). The first scheduled run in `v1-e34-t05-enable-schedule` may be the natural place.
   `docs/data/caselist-sync-runs.md` says the outstanding weeklies belong to
   `v1-e30-t06-initial-backfill` and are not pulled ad hoc, so please decide *which* run this is
   before starting one.

   **Operator command** (expected runtime ~1–3 min: 5 archive downloads paced at ≤8/min, plus import and publish)

   Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e34-t03-sync-monitoring`, after `aws sso login --profile debate-dev-evidence`
   ```bash
   DEBATE_ENV=dev uv run debate-research caselist pull --caselist hsld26 --caselist hspolicy26 --caselist hspf26
   DEBATE_ENV=dev uv run debate-research --json caselist runs --last 5 | jq '.data.runs[] | {run_id, outcome, archives_wanted, archives_downloaded, archives_deferred, deferred_by_caselist, backlog_carried, backlog_growing}'
   ```
   Success looks like:
   * exit 0;
   * a caption naming "N of M wanted archive(s)" and the deferred count, never "Nothing new";
   * one `cap_deferred` record with `deferred_by_caselist` for all three slugs.

   Paste the jq output back. A second run on a later day then shows whether the backlog shrinks.
   If it does, `BACKLOG_GROWTH_RUNS = 2` stands.
2. **Optional, for the discrepancy below:** the raw JSON of `~/.debate-research/dev/caselist-sync-runs/20260924T042401Z.json`.

## Follow-up work

* **`docs/data/caselist-sync-runs.md` may have a counting discrepancy, or there may be a
  selection defect.** The second run of 2026-09-24 is recorded as "0 of 11 wanted … all 11
  weeklies deferred". After the first run imported 5 of 12, the selection rules mark the 5
  fetched weeklies `already_imported`, which leaves **7** wanted, not 11. Either the recorded row
  is a miscount, or the second run did not see the first run's manifests as its newest snapshot.
  The second would be a t02 selection bug worth a task. I could not tell which without the raw
  JSON (Operator follow-up 2). Owner: PM, possibly `v1-e34-t02` follow-up.
* **That doc's "Until those ship, read the `selections`" note becomes stale** when this merges.
  Owner: PM (operator-recorded data doc; left untouched here).
* **Wire the stale-data hook into the landscape report** in `v1-e32-t03`/`v1-e32-t05`
  (Deviation 3). Owner: E32.
* **A pushed notification for a missed scheduled run** needs a watchdog independent of the job
  itself, for example a second launchd agent or a login-time check that runs `caselist runs` and
  notifies when `overdue` (Deviation 5). Owner: `v1-e34-t05` or a new E34 task.
* **The exit code for a failed optional stage** (Deviation 4). Owner: PM decision.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

Accepted. ac5's measurement has been taken and the phase stays `Succeeded`.

**ac5 is closed, and the criterion was wrong rather than the session.** I wrote "measured on a real
dev run of three caselists", which collides with `v1-e30-t06` owning the outstanding weeklies — the
session was right to stop and ask rather than spend a day's allowance on another task's work. A
`--dry-run` measures the same thing for nothing: `within_daily_budget` runs during `plan()`, so the
clamp shows without a download. ac5 now says so, and says it must not be a real pull. The
measurement is recorded in `docs/data/caselist-sync-runs.md`:

| Caselist | Listed | Already imported | Wanted | Granted | Deferred |
|---|---|---|---|---|---|
| `hsld26` | 13 | 5 | 7 | 2 | 5 |
| `hspolicy26` | 12 | 0 | 11 | 2 | 9 |
| `hspf26` | 12 | 0 | 11 | 1 | 10 |

An allowance of 5 split 2/2/1 across queues of 7, 11 and 11 — the round-robin behaving exactly as
its docstring claims, oldest-first within each caselist so what is deferred is always the newest.
**The measurement supports the threshold the session chose.** In steady state three caselists
publish about three weeklies a week against an allowance of five, so an ordinary run defers nothing
and a backlog that has grown twice running is genuinely abnormal. A backlog that is merely large is
not, which is why "grown two runs in a row" is the right trigger and "non-empty" would have cried
wolf every day of the backfill.

**Item 2 was my defect, not a selection bug, and the session handled it correctly.**
`20260924T042401Z` is `hspolicy26`, not `hsld26` — a different caselist with an empty store, which
is why it wanted 11 and not 7. The decisions in its JSON (`over_daily_budget: 11` plus one full
archive = 12 listed, against `hsld26`'s 13) settle it. My table carried a "Caselists" column with
the *count* and never the slug, so three rows for three caselists read as one caselist's history.
Slugs are not identifying information — they are the value the object keys already carry under
policy rule 3 — so there was no reason to omit them, and the table now names them. Flagging an
inconsistency and declining to conclude which side was wrong without the raw JSON is exactly right.

**Deviations, all accepted.**

* Changing `caselist_sync.py` and `caselist_pull.py` for ac5 and ac6 only is what the kickoff
  authorised; the report names the files, which is what was asked.
* Wrapping the recording around the pull rather than inside the sync service is the better of the
  two: it keeps `v1-e34-t02`'s module to orchestration and means a recording failure cannot lose a
  run that captured bytes.
* Treating a cap-bound run as not-current for the staleness banner is the right call and the
  reasoning is right — each deferred archive is a published week the landscape is missing. The
  report says the decision was made deliberately, which ac3 asked for.

**Two spec amendments the session correctly could not make itself.**

1. **The exit-code rule in `forbidden` was too broad.** It read "every failure yields a non-zero
   exit", which contradicts `v1-e34-t02`'s design that parse and landscape cannot fail a run whose
   bytes are already captured. The session flagged the conflict instead of changing code to match a
   line it doubted. Now scoped: every failure yields a record and a notification, and a failed
   *mandatory* stage (download, import, publish) also yields a non-zero exit. Exiting 1 every week
   over an optional stage would teach the operator to ignore the exit code, which is the failure
   this epic exists to prevent.
2. **`v1-e32-t03-landscape-report` and `v1-e32-t05-landscape-cli`** now each require calling the
   staleness hook — a report that cannot say how old its newest snapshot is does not ship. Without
   this the hook would have sat unused and ac3 would have been true of nothing.

**Accepted as a limitation, not a gap.** Nothing can push a notification about a run that never
started; the banner catches it at the point of use, because a missed run ages the snapshots and the
next report says so. Whether the schedule *itself* stopping deserves a push belongs to
`v1-e34-t05-enable-schedule`, which is what puts the agent on the machine.

**What the measurement also established, and it is not this task's.** The cap is five downloads a
day and the schedule runs weekly, so one run takes at most five while about three new archives
arrive — a net drain of roughly two a week against a backlog of 29. The weekly schedule keeps a
current store current; it cannot build one. `v1-e30-t06-initial-backfill` is what builds it, over
several days, and the decision not to pull ad hoc holds.
