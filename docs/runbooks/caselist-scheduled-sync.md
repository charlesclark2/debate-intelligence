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
  across the configured caselists before it fetches anything, counting over a **rolling 24
  hours** rather than a calendar day: a download may start only if fewer than five started in the
  24 hours before it. Which day the site itself counts has never been established, and a rolling
  window is safe against any of them, where a calendar day hands out a fresh five at its midnight.
  Every download's start time is kept in `<data_dir>/caselist-sync-download-starts.json`, and each
  run's stage table and summary say what it counted against (`bulk_download_window_start`,
  `bulk_downloads_spent_in_window`). If the site applies the limiter anyway, the run records the
  rest of the archives as deferred and goes on to import and publish what it already has — a
  deferred archive is a delay, not a loss, because the site keeps a back-catalogue of the weeklies
  (ADR-0017).

  Builds before `v1-e34-t06` kept a calendar-day ledger, `<data_dir>/caselist-sync-downloads.json`.
  Newer builds still read it, counting its downloads from when it was last written, and never
  write it, so a build of either kind can run beside the other without the newer one handing out
  what the older one spent. Leave the file where it is; it stops counting 24 hours after its last
  write.

## Before you install anything

1. **The policy gate.** `caselist.api_enabled` must be on for the environment you are installing
   for. It is off by default on purpose: turning it on is the decision the E34 gate describes.
   The agent runs an *installed* build (`scripts/install_channel.sh <tag>`, v1-e01-t09), and an
   installed build reads the gate from the `config/profiles/<env>.toml` **bundled into its wheel
   when it was built**, not from any checkout. Editing the profile in a checkout changes nothing
   for the agent until a new build is installed. `debate-research --json config show` run as the
   agent runs (same `DEBATE_ENV`, from `$HOME`) shows the value and, under `sources`, which
   bundled file it came from.

   The build must also be complete: `install_channel.sh` ends with
   `N/N wired integrations import; declared extras: aws, docx, opencaselist; complete` and refuses
   a build that cannot import the S3 adapter or the OpenCaselist client (v1-e01-t17). Builds
   published before that change lack boto3, so every `caselist pull` they run fails with exit 70.
   Never add a package to the tool environment by hand to get past that; install a later tag.
   How to check an install, and what the installer does before it replaces the agent's build, is
   under [Checking an installed build](#checking-an-installed-build).
2. **A token.** `debate-research caselist auth login`, once, for that environment
   (`v1-e34-t01`). `caselist auth status --check` confirms it.
3. **An AWS session**, if you want the run to publish: `aws sso login --profile
   debate-<env>-evidence`. Without one the run still downloads and imports, and records the
   publish as pending.
4. **A validation run in dev**, below. The schedule is enabled only after that has passed.

## Checking an installed build

**Which Python.** You never choose one. The supported interpreter is whatever the `debate_core`
wheel's `Requires-Python` metadata admits (from `debate_core`'s `requires-python`), and
`install_channel.sh` reads it from the wheel it is about to install and passes it to uv. It refuses,
naming the wheel, if it cannot read it. Do not install the tool by hand with `uv tool install`: uv
ignores the upper bound of a dependency's `Requires-Python`, so a hand-run install can land on a
Python whose Unicode database the evidence normalizer is not pinned to
([`docs/evidence/normalization.md`](../evidence/normalization.md)).

**What the installer checks before it replaces anything.** `install_channel.sh` first installs the
build into a temporary tool directory and checks it there: the wheels' provenance,
`debate-research --version --json`, `python -m debate_cli.installation` (every wired integration
imports) and `debate-research doctor`. Only if all of them pass does it install into the real tool
directory, the one the agent runs, and repeat the checks. A build that fails in the rehearsal ends
with `the installed debate-research was not touched`, and the agent keeps running the build it had.

**Checking the build the agent runs now**, at any time, as the agent runs it:

```bash
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" sh -c 'command -v debate-research; debate-research doctor; echo "doctor exit=$?"'
```

`doctor` reports the build's versions, its interpreter, its wiring, and its Unicode database beside
the normalizer's pin. Its exit status:

| Exit | Means | What to do |
|---|---|---|
| 0 | The report was produced and the interpreter's Unicode database is the one the normalizer is pinned to. | Nothing. |
| 1 | The two Unicode databases differ (`UNICODE_DATABASE_MISMATCH`, naming both versions and the policy page). Every command that normalizes evidence text would refuse to run. | Reinstall a tag with `install_channel.sh`, which picks a Python the wheel admits. |
| 70 | `doctor` could not determine the normalizer's pinned version at all. That is a bug in the build, not a verdict on the interpreter. | Install a different tag and report the build. |

Nothing else `doctor` reports changes its exit status. Settings not loaded, an unknown package
version or an unexpected platform are described, never failed: none of them is a failure it can
state precisely.

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
`reports/sync-runs/<yyyy>/<run-id>.json` in the bucket (`v1-e34-t03`). The first command reads this
machine's log, the second the bucket's copy:

```bash
debate-research caselist runs --last 5
debate-research caselist runs --last 5 --remote
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
| `bulk_download_window_start`, `bulk_downloads_spent_in_window` | The 24 hours the run counted its downloads against, and what had already been spent in them |
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

**A download failed.** What did download is in the inbox and imported, up to the first week that
did not arrive; a newer week of the same caselist waits in the inbox behind it rather than being
imported out of order. Nothing needs doing: the next scheduled run fetches the missing week and
imports it and everything behind it, oldest first, and it does not fetch again anything already
in the inbox — each fetch spends one of the five.

**An import failed** (`import: failed`, with the archive and the reason in its detail). The archive
stays in the inbox, and the next run imports it from there without downloading it again, then the
newer weeks of that caselist that waited behind it. What the operator has to do is remove the
cause the reason names — an archive over `caselist.max_archive_bytes`, a caselist slug this build
does not know the event of, an unreadable zip — because a run meets the same archive again and,
with the cause still there, fails the same way. An unreadable zip is the one case to delete by
hand: remove it from the inbox, and the next run downloads it again.

**A camp file shows `skipped_as_removed`** (and the select stage says *N OpenEv file(s) skipped as
removed*). Nothing is wrong: it was taken out with `caselist remove`, and the run did not fetch it
again for the importer to refuse. The decision is read from the suppression list on every run, so
after `caselist unsuppress` the next run fetches it again, and says so in the select stage (*fetched
before and neither recorded nor suppressed now*). Which bytes each OpenEv id delivered is kept in
`<data_dir>/caselist-sync-openev-deliveries.json`; it holds digests only, and deleting it costs at
most one download of each removed file, which the importer refuses. `caselist remove` deletes a
removed camp file's copy from the inbox, and writes its digests to that record first when the
record does not have them (`v1-e30-t09`), so the copy going does not cost a download either.

**A camp file shows `same_path_as_a_removed_file`.** OpenEv lists a new id at the path of a camp
file that was removed; that is how a camp uploads a file again, since OpenEv cannot replace a file in
place. The run holds it back: a removal covers a camp's later upload of the same file, because the request
was about the material and a revised file normally still contains it (PM decision, `v1-e34-t07`).
Nothing needs doing. If the data-use policy is ever read the other way, this becomes a download; until
then, fetching such a file by hand through `caselist import-openev` is a decision to record in the
register.

**A camp file shows `suppression_list_unreadable`.** The run could not read the suppression list:
the bucket refused its copy (a missing grant, `access denied`) or a copy has a line nobody can read.
It did not fetch any camp file it may have been told to remove, and the import stage fails for the
same reason. Fix what the import stage's reason names; the next run decides it. An expired SSO
session does not cause this (below).

**The summary's `suppression_list_local_copy_only` is set** (and the select or import stage says
*this machine's copy of the suppression list alone was read*). The SSO session had expired, so the
run read this machine's copy of the list instead of both, imported as usual, and left the publish
pending. That is safe while this is the only machine that imports, because every removal writes both
copies; log in and run `caselist pull --publish-pending`. If a second machine ever imports, this is
the day to revisit it (`v1-e34-t07`, `v1-e30-t07` Deviation 7).

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

**Turning the API off without stopping the agent.** Because the gate is baked into the installed
build, there are two ways: install a build whose committed profile says `api_enabled = false`, or
add `DEBATE_CASELIST__API_ENABLED=false` to the agent's `EnvironmentVariables` in the plist and
reload it. The environment variable beats the bundled profile, and the next run refuses to reach
the network. Editing `config/profiles/*.toml` in a checkout is **not** a way to turn it off.

## Related

* [`docs/policies/caselist-data-use.md`](../policies/caselist-data-use.md) — the rules the
  schedule exists inside
* [`docs/adr/0017-caselist-corpus-is-retrievable.md`](../adr/0017-caselist-corpus-is-retrievable.md)
  — why weekly, and why a missed run is a delay rather than a loss
* [`docs/runbooks/evidence-store.md`](evidence-store.md) — the bucket the run publishes to
* [`docs/runbooks/caselist-removal.md`](caselist-removal.md) — taking a file back out
* [`docs/data/caselist-sync-runs.md`](../data/caselist-sync-runs.md) — the recorded runs
