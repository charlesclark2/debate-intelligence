<!-- docs-index: Installing, enabling, watching and disabling the weekly `caselist pull` launchd agent -->
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

**A Python uv manages, and why the agent needs one.** The installer also asks uv for a Python that
uv itself manages (`--managed-python`, in the rehearsal and the real install), one kept in the
directory `uv python dir` prints (`~/.local/share/uv/python` by default). Without that, uv takes the
first Python that matches, and an activated conda base environment, which `conda init` puts in
every shell, comes before uv's own. Builds installed before `v1-e01-t23` therefore ran on
anaconda's `python3`, and a `conda update python`, a Homebrew upgrade of a Python on PATH, or
removing anaconda would change or delete the agent's interpreter in place: no install runs, no
rehearsal catches it, and the next Wednesday run fails. A Python uv manages is changed only by uv:
by reinstalling the build, or by a `uv python` command you run on purpose (`uv python uninstall`,
or `uv python upgrade`, which moves a build to a newer patch release of the same minor version).
After each install the installer checks that the build's base Python really is under
`uv python dir`, prints `The build runs on the Python at …, which uv manages.`, and refuses the
build otherwise.

If no Python that uv manages matches yet, the installer says `No Python that uv manages matches
'…' yet, so uv will download one into …`, and uv downloads it during the install (17 MB on this
Mac, 33 MB on the Linux runners; one to two seconds each, measured). The agent never runs the
installer, so this only happens while you are watching. `doctor` decides `Managed by uv` from its
own environment, so a build installed with `UV_PYTHON_INSTALL_DIR` set shows `no` wherever that
variable is not set; the agent's build uses the default directory. With `UV_PYTHON_DOWNLOADS=never` set, uv refuses instead, and
`uv python install '<the specifier>'` installs one. The installer needs uv 0.6.8 or newer, the
first with `--managed-python`; it refuses an older uv by name before installing anything.

**What the installer checks before it replaces anything.** `install_channel.sh` first installs the
build into a temporary tool directory and checks it there: the wheels' provenance,
`debate-research --version --json`, `python -m debate_cli.installation` (every wired integration
imports, and every package the build declares is installed) and `debate-research doctor`. Only if
all of them pass does it install into the real tool directory, the one the agent runs, and repeat
the checks. A build that fails in the rehearsal ends with `the installed debate-research was not
touched`, and the agent keeps running the build it had.

**The real install is the build the rehearsal checked.** The real install does not resolve the
third-party packages afresh. It is pinned to exactly the versions the rehearsal installed, and the
log says `Pinning the real install to the N third-party distributions the rehearsal checked.` A
release published to PyPI in the seconds between the two installs therefore cannot change what the
agent runs. Afterwards the script compares the two environments. If they differ it fails with
`the real install is not the build the rehearsal checked`, lists the differences, and says the
previous install has already been replaced. Run the script again; if it fails the same way, the
installed uv is not keeping to `--constraints`, and that needs reporting rather than working around.

**Checking the build the agent runs now**, at any time, as the agent runs it:

```bash
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" sh -c 'command -v debate-research; debate-research doctor; echo "doctor exit=$?"'
```

`doctor` reports the build's versions, its interpreter, its wiring, its Unicode database beside
the normalizer's pin, and whether every integration the CLI wires imports. It also reports the
`Base interpreter` (the Python installation behind the build's environment), `uv's Pythons` (the
directory `uv python dir` would print in that environment) and `Managed by uv`, which is `yes` when
the first lies inside the second, links followed. For the agent's build it should say `yes`; `no`
means the build is on a Python that conda, Homebrew or anything else on the Mac can change, and
reinstalling a tag with `install_channel.sh` moves it to one uv manages. `Managed by uv` never
changes doctor's exit status. Its exit status:

| Exit | Means | What to do |
|---|---|---|
| 0 | The report was produced, the interpreter's Unicode database is the one the normalizer is pinned to, and every wired integration imports. | Nothing. |
| 1 | A check failed. The two Unicode databases differ (`UNICODE_DATABASE_MISMATCH`, naming both versions and the policy page), so every command that normalizes evidence text would refuse to run. Or wired integrations do not import (`INTEGRATIONS_DO_NOT_IMPORT`, naming each one and why), so every command that uses them would fail. Both at once are `INSTALLATION_CHECKS_FAILED`. | Reinstall a tag with `install_channel.sh`, which picks a Python the wheel admits and refuses an incomplete build. Never add a package to the tool environment by hand. |
| 70 | `doctor` could not make a check at all: the normalizer's pinned version is unknown, or the CLI wires an integration in a way it cannot follow. That is a bug in the build, not a verdict on the installation. | Install a different tag and report the build. |

Nothing else `doctor` reports changes its exit status. Settings not loaded, an unknown package
version, an unexpected platform, a Python uv does not manage, or a declared extra's package missing (`Extras' packages missing`)
are described, never failed: none of them is a failure it can state precisely. A missing package
that a wired integration needs makes that integration fail to import, and that is exit 1. The
installer refuses a build with any declared package missing.

## Step 1 — rehearse, in dev

```bash
DEBATE_ENV=dev debate-research caselist pull --caselist hsld26 --dry-run
```

It makes listing calls to OpenCaselist, reads the bucket to compare what the inbox holds with it,
and writes nothing. Read the table: every archive the site lists, and what the run decided about
each. `already_imported`, `full_archive_not_pulled_weekly` and `unrecognised_name` are all normal.
`over_daily_budget` means there is more back-catalogue than one day's allowance, which is
`v1-e30-t06`'s job rather than this schedule's. The `retention` row lists what a real run would
remove from the inbox ([The download inbox](#the-download-inbox)); without an AWS session it can
confirm nothing, and lists every imported download as kept.

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
ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --env prod --debate-research "$HOME/.local/bin/debate-research" --dry-run
```

`--dry-run` prints the plist and writes nothing; read it before you install it. Then:

```bash
ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --env prod --debate-research "$HOME/.local/bin/debate-research"
```

That writes `~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist`, copies the
wrapper out of the checkout, creates the log directory and lints the plist with `plutil`. **It
starts nothing**, and `RunAtLoad` is false, so even loading the agent does not trigger a pull.

`--weekday`, `--hour` and `--minute` move the schedule; the default is Wednesday 06:00, the day
after the site publishes the week's archives.

### What the agent runs, and where it is

The agent runs nothing from a git checkout (`v1-e34-t10`):

| | Where | Why there |
|---|---|---|
| Wrapper | `~/.local/share/debate-research/launchd/run-caselist-sync.sh`, the installer's copy of `ops/launchd/run-caselist-sync.sh` | Beside uv's tool directory, outside every working tree and every protected folder, with no spaces in the path |
| Console script | `DEBATE_RESEARCH_BIN` in the plist: the path given with `--debate-research`, or the `debate-research` this shell finds, written as found | So that no other `debate-research` earlier on a PATH can stand in for the installed build |
| `PATH` | The console script's directory, then `/usr/bin:/bin:/usr/sbin:/sbin` | The command runs nothing else but `osascript`, for notifications, which is in `/usr/bin`. The installing shell's PATH is not copied |
| Data | Whatever the installed build reports for `storage.data_dir`; the installer asks it with `config show` | The bundled profile decides it, not the checkout |
| Refused | Any of the above, the log directory or HOME under `~/Documents`, `~/Desktop`, `~/Downloads`, `~/Library/Mobile Documents` (iCloud Drive), `~/Library/CloudStorage` (Dropbox, Google Drive and other File Provider folders) or `/Volumes`; or inside a git working tree or a project `.venv` | macOS privacy protection keeps launchd agents out of those folders, and a checkout or `.venv` changes under the agent |

The wrapper is copied out for two reasons. A checkout's copy is whatever branch is checked out at
06:00 on Wednesday. And macOS privacy protection does not let a launchd agent open anything under
the folders in the table's last row. The first scheduled run, on 2026-10-07, ran the checkout's wrapper under `~/Documents`
and exited 126 with `Operation not permitted`. The installer refuses a wrapper destination
(`--wrapper-dir`), log directory, data directory or console script under any of those folders, or
inside a git working tree or a project `.venv`, naming the path and the reason. Nothing is written
when it refuses.

**Reinstall to update the wrapper.** Editing `ops/launchd/run-caselist-sync.sh`, or pulling a
change to it, does not reach the agent. Running `install.sh` again replaces the copy in one rename,
with mode 0755. launchd keeps the plist it loaded, so when the plist changes too (a new wrapper
path, console script or schedule), boot the agent out and bootstrap it again (Step 3). That resets
the `runs` count `launchctl print` shows to 0.

## Step 3 — enable it

```bash
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
launchctl print gui/$UID/com.debate-intelligence.caselist-sync
```

After a reinstall, when the agent is already loaded, boot it out and bootstrap the new plist:

```bash
launchctl bootout gui/$UID/com.debate-intelligence.caselist-sync
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
launchctl print gui/$UID/com.debate-intelligence.caselist-sync
```

If `bootstrap` says `Bootstrap failed: 5: Input/output error`, the bootout had not finished; run
the bootstrap line again.

`print` should show the job, its program arguments (the copied wrapper under
`~/.local/share/debate-research/launchd/`, never a checkout) and its calendar interval. To run it once,
immediately, without waiting for Wednesday:

```bash
launchctl kickstart -p gui/$UID/com.debate-intelligence.caselist-sync
```

A missed run is not skipped: launchd runs a `StartCalendarInterval` job when the machine next
wakes, so a laptop that was shut at 06:00 on Wednesday runs it that evening.

**Proving launchd can run it, without a sync.** After every install or reinstall:

```bash
ops/launchd/install.sh --check-launchd
```

It loads a one-off copy of the installed plist as `com.debate-intelligence.caselist-sync.check`,
with no schedule, running the copied wrapper's `--check`. That prints the path
`DEBATE_RESEARCH_BIN` resolves to and the build's `debate-research --version`, and nothing else: no
`caselist pull`, no listing call, no download. The installer kickstarts it, waits for it, prints
its log (`~/Library/Logs/debate-research/caselist-sync-check.log`) and exit code, and boots it out.
It reads the agent's `runs` count before and after and fails if it changed. It refuses to run
against an agent whose wrapper is not this checkout's copied out, so reinstall first. Success is
`exit code 0`, the version you installed, and the same `runs` before and after. An exit code of
126 is the privacy-protection failure above.

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
| `inbox_retention` | What left the inbox and the bytes freed, and what stayed and why. See [The download inbox](#the-download-inbox) |
| `stages[]` | One entry per stage, each with the sentence saying why it ended that way |

Nothing in that object is a school, a team code, a debater's initials, a disclosure path or the
`caselist_token` — the policy forbids all of them in a log, and the summary is built to the same
rule, so these logs can be pasted into an issue as they are.

## The download inbox

`<data_dir>/inbox` (or `caselist.inbox_dir`) is where a pull downloads to and what it imports from.
Between two runs it holds:

* **Weekly archives** waiting to be imported or published (`<slug>-weekly-<date>.zip`): a week whose
  import failed, a newer week waiting behind it, or a week whose publish is pending an AWS login.
* **Camp downloads** in the same state (`openev-<id>-<name>`), and any camp download the OpenEv
  delivery record does not cover.
* **A camp release holding only junk** (`.DS_Store`, `__MACOSX/`, no camp file), named as
  `not_imported` in every summary: no manifest row with a classification came from it, so
  retention keeps it. It is not imported again (`v1-e34-t08`); the delivery record says it was.
* `.partial/`, downloads in progress, which a run sweeps.
* Anything put there by hand. The pull never touches a file whose name it did not give it.

Everything else leaves at the end of the run that confirms it, in the **retention** stage, which
runs after the report stage while the run still holds its lock (`v1-e34-t11`). A file is removed
only when all of these are true:

1. **It is imported.** A manifest on this machine came from these exact bytes: the week's own
   manifest names the zip's sha256, or an OpenEv release manifest row names the camp download's.
   That is what keeps a download waiting for an import retry, since the retry imports precisely the
   inbox files no manifest came from.
2. **Its snapshot is confirmed in the bucket, by this run.** For a week this run published, that is
   the report stage's comparison. For a week an earlier run imported, the retention stage compares
   it with the bucket itself (the same comparison `caselist status` makes) rather than trusting
   what an earlier run said. An expired SSO session therefore confirms nothing, and the files wait
   for a run that can check.
3. **For a camp download, the delivery record holds its digests**
   (`<data_dir>/caselist-sync-openev-deliveries.json`). Once the copy is gone, the record is how the
   next run knows a camp release was already imported, or was removed. A camp file imported before
   `v1-e34-t07` has no record entry, so its copy stays, named in every summary. That is harmless,
   and it is never fetched again while the copy is there.

**Nothing is kept longer, the newest week included.** The usual reason to keep a zip is that
re-importing after a failed publish costs nothing. Here a zip is removed only after its publish is
confirmed, and a publish (or a re-publish, after drift) reads the local store, never the inbox, so
that case cannot arise. The newest weekly is also the largest, because the weeklies are cumulative.
A removed week is never fetched again: a week on or before the newest imported one is
`already_imported` whether or not its zip is here. The site keeps the weekly back-catalogue
(ADR-0017), so a zip can be fetched again by hand if one is ever needed.

**A run that downloads nothing still runs retention.** The first run after `v1-e34-t11` therefore
clears the backlog that earlier builds left: every weekly they imported and published. A **dry run**
removes nothing. Its retention row lists what a real run would remove now (`would_remove`, with the
bytes), what it would keep and why, and the weeks it would also remove once it had imported them
and the bucket confirmed them. `--publish-pending` removes nothing; the next pull does. An
environment with no bucket can confirm no publish, so nothing ever leaves its inbox.

**What the summary says.** The `retention` stage's reason, which the run log and the bucket's run
report keep as written, lists every removed and kept file and the total bytes freed. Weeklies are
named by caselist and date (`hsld26 2026-09-15`), and camp downloads and anything else by count and
the first twelve hex digits of the sha256, never by file name: a camp file's name is its title, and a
name given by hand can say anything. The JSON summary carries the same lists under `inbox_retention`.
A kept file's reason is one of:

| Reason | What it means | What to do |
|---|---|---|
| `not_imported` | No manifest came from these bytes. Usually the import failed, or the week waits behind an older one; the next run imports it. | Fix what the import stage's reason names (see "An import failed"). A week that no run will import, whose week is held from other bytes, can be deleted by hand |
| `not_confirmed` | Imported, but the bucket does not hold the snapshot in sync, or could not be read | `aws sso login` and `caselist pull --publish-pending`; if it persists, `caselist status` names the drift |
| `no_delivery_record` | A camp download imported before the delivery record existed | Nothing. It stays and costs nothing |
| `unclassified` | A file whose name the pull does not give a download | Yours to keep or delete |

**Removal and retention both delete inbox files, and never the same ones twice.** `caselist remove`
(`v1-e30-t09`) deletes or rewrites the inbox files holding something a removal took out, whether or
not they are imported. Retention deletes imported, confirmed downloads, whatever they hold. Both take
the sync's run lock, so they cannot run at once, and each counts only what it deleted: retention
judges the inbox as a removal left it.

Measure the inbox before and after with `du -sh <data_dir>/inbox`.

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

**A download failed.** What did download is imported, up to the first week that did not arrive,
and leaves the inbox once the bucket confirms it; a newer week of the same caselist waits in the inbox behind it rather than being
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

**The select stage says *N taken as a revision of an id no longer listed (openev-512 -> openev-640)*.**
A camp uploaded a file again. OpenEv cannot replace a file in place, so a revision is the old id
deleted and a new id uploaded, normally at the same path. The run fetched the new id because a row
of the release manifest at its path names the old id (`openev-512-…`, the name the sync gave that
download) and the old id is no longer listed anywhere (`v1-e34-t08`). The selection's `revision_of`
says the same in the JSON. Nothing needs doing. The old version stays in the store beside the new
one; nothing is deleted. A camp file imported by hand is never taken as a revision, because its row
does not say which upload it came from, so a re-upload of one is not fetched; fetch it by hand
through `caselist import-openev` if it matters.

**A camp file shows `same_path_as_a_removed_file`.** OpenEv lists a new id at the path of a camp
file that was removed; that is how a camp uploads a file again, since OpenEv cannot replace a file in
place. The run holds it back: a removal covers a camp's later upload of the same file, because the request
was about the material and a revised file normally still contains it (PM decision, `v1-e34-t07`).
This hold is decided before a revision is fetched, and it holds a revision whose old version was
removed on another machine too, since the bucket's copy of the list is read. Nothing needs doing.
After `caselist unsuppress` of the old file, the next run fetches the new id. If the data-use policy
is ever read the other way, this becomes a download; until then, fetching such a file by hand
through `caselist import-openev` is a decision to record in the register.

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

The agent stops; the plist and the copied wrapper stay. To remove both:

```bash
rm ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
rm ~/.local/share/debate-research/launchd/run-caselist-sync.sh
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
