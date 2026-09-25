# Runbook: the weekly caselist sync

How the weekly OpenCaselist pull is installed, enabled, watched and turned off on the operator's
Mac. The command it runs is `debate-research caselist pull` (`v1-e34-t02-scheduled-sync`); the
schedule around it is `ops/launchd/`.

| | |
|---|---|
| Runs on | Charlie's Mac, as Charlie, under launchd |
| Cadence | **Weekly.** Wednesday 06:00 local by default |
| Command | `debate-research caselist pull --caselist <slug> …` |
| Agent label | `com.debate-intelligence.caselist-sync` |
| Logs | `~/Library/Logs/debate-research/caselist-sync.jsonl` and `…err.log` |
| Run summaries | `<data_dir>/caselist-sync-runs/<run id>.json` |

## Weekly is not a preference

[`docs/policies/caselist-data-use.md`](../policies/caselist-data-use.md) E34 gate 4 permits
**weekly cadence at most, no polling faster than archives are published**. It was agreed with the
OpenCaselist maintainer, whose confirmation (clause 12 of the clause register) is scoped to the
weekly archives, and [ADR-0017](../adr/0017-caselist-corpus-is-retrievable.md) records that the
daily cadence a superseded decision record proposed contradicted it and was therefore wrong.

Do not shorten the interval. If a faster cadence ever looks necessary, it is renegotiated with the
maintainer and the policy is revised and re-approved first; the schedule follows the policy, never
the other way round.

Two more ceilings the site sets, both handled in code rather than here:

* **10 file downloads per minute** (clause 12). The client paces itself below it and refuses a
  configuration above it.
* **5 bulk archive downloads per user per day** (upstream `weeklyLimiter`). The run budgets for it
  across the configured caselists before it fetches anything, and keeps a per-day ledger at
  `<data_dir>/caselist-sync-downloads.json`. If the site applies the limiter anyway, the run
  records the rest of the archives as deferred and goes on to import and publish what it already
  has — a deferred archive is a delay, not a loss, because the site keeps a back-catalogue of the
  weeklies (ADR-0017).

## Before you install anything

1. **The policy gate.** `caselist.api_enabled` must be on for the environment you are installing
   for. It is off by default on purpose: turning it on is the decision the E34 gate describes.
2. **A token.** `debate-research caselist auth login`, once, for that environment
   (`v1-e34-t01`). `caselist auth status --check` confirms it.
3. **An AWS session**, if you want the run to publish: `aws sso login --profile
   debate-<env>-evidence`. Without one the run still downloads and imports, and records the
   publish as pending.
4. **A validation run in dev**, below. The schedule is enabled only after that has passed.

## Step 1 — rehearse, in dev

```bash
DEBATE_ENV=dev debate-research caselist pull --caselist hsld26 --dry-run
```

It makes listing calls only and writes nothing. Read the table: every archive the site lists, and
what the run decided about each. `already_imported`, `full_archive_not_pulled_weekly` and
`unrecognised_name` are all normal. `over_daily_budget` means there is more back-catalogue than
one day's allowance, which is `v1-e30-t06`'s job rather than this schedule's.

Then the real thing, still in dev:

```bash
DEBATE_ENV=dev debate-research caselist pull --caselist hsld26
```

Success is exit `0` with `publish: completed` and `report: completed` in the stage table.
`parse: skipped` and `landscape: skipped` are expected until E31 and E32 ship — those stages are
optional by design and cannot fail a run whose bytes are already captured.

Record the counts in [`docs/data/caselist-sync-runs.md`](../data/caselist-sync-runs.md).

## Step 2 — install the agent

```bash
ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --env prod --dry-run
```

`--dry-run` prints the plist and writes nothing; read it before you install it. Then:

```bash
ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --env prod
```

That writes `~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist`, creates the log
directory and lints the plist with `plutil`. **It starts nothing**, and `RunAtLoad` is false, so
even loading the agent does not trigger a pull.

`--weekday`, `--hour` and `--minute` move the schedule; the default is Wednesday 06:00, the day
after the site publishes the week's archives. `--debate-research` gives the full path to the
console script when it is not on the PATH of the shell you install from.

## Step 3 — enable it

```bash
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
launchctl print gui/$UID/com.debate-intelligence.caselist-sync
```

`print` should show the job, its program arguments and its calendar interval. To run it once,
immediately, without waiting for Wednesday:

```bash
launchctl kickstart -p gui/$UID/com.debate-intelligence.caselist-sync
```

A missed run is not skipped: launchd runs a `StartCalendarInterval` job when the machine next
wakes, so a laptop that was shut at 06:00 on Wednesday runs it that evening.

## Watching it

You should not have to go looking. A failed stage, an expired `caselist_token`, an expired SSO
session, and a cap backlog that has grown for two runs in a row each post a macOS notification
naming the command that fixes it (`caselist.notifier`, `auto` by default). Every run also appends
one record to the run log, `<data_dir>/caselist-sync-runs.jsonl`, and publishes it to
`reports/sync-runs/<yyyy>/<run-id>.json` in the bucket (`v1-e34-t03`):

```bash
debate-research caselist runs --last 5            # this machine's log
debate-research caselist runs --last 5 --remote   # the bucket's copy
```

Its caption says how long ago the newest run started, and says the schedule may have stopped when
that is more than eight days — the one failure that leaves no record and sends no notification.

The raw output of each run is still there:

```bash
tail -n 1 ~/Library/Logs/debate-research/caselist-sync.jsonl | jq .data
tail -n 40 ~/Library/Logs/debate-research/caselist-sync.err.log
```

One JSON object per run on stdout. The fields to read first:

| Field | What it says |
|---|---|
| `succeeded` | Whether every stage that puts bytes somewhere durable finished |
| `nothing_new` | A normal week with no new archive published yet. Never true when the cap deferred anything |
| `archives_wanted`, `archives_downloaded`, `archives_deferred` | Newer than what was held; fetched; left by the daily cap for a later run |
| `openev_downloaded` | Camp files fetched |
| `files_imported`, `blobs_stored` | What the importers filed, and how much of it was new |
| `objects_published` | What reached the bucket |
| `pending_publish` | Snapshots waiting for an AWS session |
| `stages[]` | One entry per stage, each with the sentence saying why it ended that way |

Nothing in that object is a school, a team code, a debater's initials, a disclosure path or the
`caselist_token` — the policy forbids all of them in a log, and the summary is built to the same
rule, so these logs can be pasted into an issue as they are.

## When something goes wrong

**`pending_publish` is not empty.** The SSO session expired. Log in and drain it:

```bash
aws sso login --profile debate-prod-evidence
debate-research caselist pull --publish-pending
```

**`another caselist sync is already running`.** A run holds the lock at
`<data_dir>/caselist-sync.lock`. It is an `flock`, so the kernel drops it when the process ends —
if you see this with no `debate-research` process running, something is holding the file open;
`lsof <data_dir>/caselist-sync.lock` says what.

**`the caselist_token has expired or been revoked`.** `debate-research caselist auth login` again.
If it happens immediately after a fresh login, **stop** and do not retry: access may have been
suspended, which is the site's right (policy clause 10), and the next step is to contact the
maintainer, not to work around it.

**A download failed.** Everything that did download is in the inbox and imported. Run the same
command again — an archive already in the inbox is not fetched a second time, which matters
because each fetch spends one of the day's five.

**The run says `over_daily_budget` week after week** (a *caselist backlog growing* notification,
or `archives_deferred` rising in `caselist runs`). There is more back-catalogue than a weekly
run will ever catch up on. That is the one-off fetch in `v1-e30-t06`, not a reason to raise the
ceiling.

## Disabling it

```bash
launchctl bootout gui/$UID/com.debate-intelligence.caselist-sync
```

The agent stops; the plist stays. To remove it entirely:

```bash
rm ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
```

Nothing already captured is affected: the archives, the manifests and the bucket are all
independent of the schedule.

## Related

* [`docs/policies/caselist-data-use.md`](../policies/caselist-data-use.md) — the rules the
  schedule exists inside
* [`docs/adr/0017-caselist-corpus-is-retrievable.md`](../adr/0017-caselist-corpus-is-retrievable.md)
  — why weekly, and why a missed run is a delay rather than a loss
* [`docs/runbooks/evidence-store.md`](evidence-store.md) — the bucket the run publishes to
* [`docs/runbooks/caselist-removal.md`](caselist-removal.md) — taking a file back out
* [`docs/data/caselist-sync-runs.md`](../data/caselist-sync-runs.md) — the recorded runs
