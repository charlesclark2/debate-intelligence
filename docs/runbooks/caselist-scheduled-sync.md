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
| Pending-work file | `<data_dir>/caselist-sync-pending.json`, only while a publish is owed. See [The pending-work file](#the-pending-work-file) |
| Parses | The sources each run imported, into `<data_dir>/parsed/`, unless `caselist.parse_imported_sources` is off. See [The parse stage](#the-parse-stage) |

## Weekly is not a preference

[`docs/policies/caselist-data-use.md`](../policies/caselist-data-use.md) E34 gate 4 permits
**weekly cadence at most, no polling faster than archives are published**. It was agreed with the
OpenCaselist maintainer, whose confirmation (clause 12 of the clause register) covers scheduled
retrieval of the archives, weekly and complete, through the API at 10 file downloads per minute
(policy 1.6), and [ADR-0017](../adr/0017-caselist-corpus-is-retrievable.md) records that the
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

  Builds before `v1-e34-t06` (tags up to `v0.1.0-dev.12`) kept a calendar-day ledger,
  `<data_dir>/caselist-sync-downloads.json`. The builds from `v1-e34-t06` on read it beside the
  rolling window while an old-format build still ran against the same data directory, and never
  wrote it. Since `v1-e34-t09` no build reads it: the cap is counted from
  `caselist-sync-download-starts.json` alone, and a copy left in a data directory is ignored and
  may be deleted. Never install a build older than `v0.1.0-dev.13` for the agent or run one against
  a data directory: it would write the calendar ledger again, and nothing newer would count what it
  spent.

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
   publish as pending. The profile itself has to be one this Mac's AWS config defines, or the run
   is refused before it starts; `debate-research doctor --evidence-profiles` says whether it is
   ([Checking the evidence profiles](#checking-the-evidence-profiles)).
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

### Checking the evidence profiles

Plain `doctor` says nothing about AWS. It loads no settings, reads no AWS config and reaches no
network, because the installer runs it on every install, on machines that have no AWS config.
`doctor --evidence-profiles` adds one check (`v1-e34-t22`): each AWS profile this environment is
configured to reach the evidence bucket with. That is the everyday profile, `storage.s3.aws_profile`,
and the takedown profile when `DEBATE_REMOVAL_PROFILE` is set in the shell it runs in. As the agent
runs it, with the `PATH` and the environment its plist gives it and nothing of this shell's:

```bash
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research doctor --evidence-profiles; echo "doctor exit=$?"'
```

It adds one row for each profile to the report, `Evidence profile`, and reads this Mac's AWS
config and asks AWS one question for each profile that is defined: who it is signed in as. What a
row says:

| The row says | Means | Exit |
|---|---|---|
| `debate-prod-evidence (storage.s3.aws_profile): defined, and signed in as DebateProdEvidenceOperator` | The profile is in this Mac's AWS config and its session is live. The name is the permission set's: `DebateProdEvidenceOperator` for prod's everyday profile, `DebateDevEvidenceOperator` for dev's | `0` |
| `… defined; its session has expired or was never started, so AWS cannot be asked which permission set it is (aws sso login --profile debate-prod-evidence)` | The profile is defined. Run the login it gives to see the permission set. This does not fail the check: a run without a session still captures and imports | `0` |
| `… defined; AWS did not answer when asked which permission set it is signed in as` | No verdict on the profile. Run it again when the Mac is online | `0` |
| `… not defined in this machine's AWS config` | The setting names a profile this Mac does not have. The command fails with `STORE_PROFILE_NOT_CONFIGURED`, naming the profile and the setting, and a scheduled run would be refused before it starts. See [A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define) | `1` |
| `Evidence profiles: none configured for this environment` | The environment names no bucket, as `test` does | `0` |

A profile signed in as something unexpected is said in the same row and does not fail the check.
The takedown profile is compared with the permission set a takedown runs as: one signed in as
anything else reads `… a takedown runs only as DebateProdEvidenceRemoval, so caselist remove
--execute will refuse this profile`. The row names a profile, the setting that holds its name and
a permission set, and never an account, a role's full identifier or where the AWS config is.

## Step 1 — rehearse, in dev

```bash
DEBATE_ENV=dev debate-research caselist pull --caselist hsld26 --dry-run
```

It makes listing calls to OpenCaselist, reads the bucket to compare what the inbox holds with it,
and writes nothing. Read the table: every archive the site lists, and what the run decided about
each. `already_imported`, `unrecognised_name` and the complete archive's `full_archive_not_due`,
`full_archive_waits_its_turn` and `full_archive_deferred_for_weeklies` are all normal (see
[The complete archive](#the-complete-archive)).
`over_daily_budget` means there is more back-catalogue than one day's allowance, which is
`v1-e30-t06`'s job rather than this schedule's. The `retention` row lists what a real run would
remove from the inbox ([The download inbox](#the-download-inbox)); without an AWS session it can
confirm nothing, and lists every imported download as kept.

Then the real thing, still in dev:

```bash
DEBATE_ENV=dev debate-research caselist pull --caselist hsld26
```

Success is exit `0` with `publish: completed` and `report: completed` in the stage table.
Exit `0` with `publish: pending` means the SSO session expired after the import: what was captured
is safe, and [When something goes wrong](#when-something-goes-wrong) says how to finish it.
Exit `3` and exit `1` both mean a download, an import or a publish did not complete, and
[What the exit code says](#what-the-exit-code-says) says which is which: `3` is transient and the
next run retries it, `1` is a verdict someone has to look at. Exit `70` is a bug. The agent never
retries any of them on its own; the next attempt is next week's run.
`parse: completed` is the normal outcome when the run imported anything, and `parse: skipped` when
it imported nothing ([The parse stage](#the-parse-stage)). `landscape: skipped` is expected until
E32 ships. Both stages are optional by design and cannot fail a run whose bytes are already
captured: a failed parse stage is reported and the exit code stays `0`.

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
`DEBATE_RESEARCH_BIN` resolves to and the build's `debate-research --version`, then runs
`debate-research doctor --evidence-profiles` (`v1-e34-t22`), and nothing else: no `caselist pull`,
no listing call to OpenCaselist, no download. The installer kickstarts it, waits for it, prints
its log (`~/Library/Logs/debate-research/caselist-sync-check.log`) and exit code, and boots it out.
It reads the agent's `runs` count before and after and fails if it changed. It refuses to run
against an agent whose wrapper is not this checkout's copied out, so reinstall first.

The log is `doctor`'s report as launchd runs the build: with the plist's `HOME`, `PATH` and
`DEBATE_ENV`, and nothing of a shell's. Its `Evidence profile` row is the one
[Checking the evidence profiles](#checking-the-evidence-profiles) describes, for the profile the
weekly run will use. Success is `exit code 0`, the version you installed, that row saying
`defined`, and the same `runs` before and after.

| Exit code | Means |
|---|---|
| `0` | launchd ran the build, the build's own checks passed, and the profile is defined. A session that has expired is still `0`: the row says so, and gives the login |
| `1` | A check `doctor` makes failed. If the row says `not defined in this machine's AWS config`, the weekly run would be refused before it starts: see [A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define). An exit code of 1 is also what a Unicode database mismatch or an integration that does not import give ([Checking an installed build](#checking-an-installed-build)) |
| `2` | The installed build is older than the profile check and does not know the option. Install a newer build with `scripts/install_channel.sh`, then run the check again |
| `126` | The privacy-protection failure above |

## Reinstalling the agent

For a new build, a changed wrapper, or a changed schedule. Nothing here fetches anything, and
the two checks are the point of doing it in this order: the first finds a profile the AWS config
does not define before the agent is replaced, and the second finds it as launchd will meet it.

1. **Install the build**: `scripts/install_channel.sh` with the tag to install. It rehearses the
   install and refuses a build that fails its checks, leaving the one the agent runs untouched
   ([Checking an installed build](#checking-an-installed-build)).

2. **Check the evidence profile, as the agent will run.** Sign in first, so that the check can
   say which permission set the profile is (`debate-dev-evidence` for an agent installed with
   `--env dev`). The environment is read from the installed plist, not typed:

   ```bash
   aws sso login --profile debate-prod-evidence
   AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
   AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
   env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research doctor --evidence-profiles; echo "doctor exit=$?"'
   ```

   Success is `doctor exit=0` and the row `Evidence profile` reading `debate-prod-evidence
   (storage.s3.aws_profile): defined, and signed in as DebateProdEvidenceOperator`. A session that
   has expired does not fail the check: the row says `expired` and gives the login, and the exit
   is still `0`. **Stop if it exits `1` with `STORE_PROFILE_NOT_CONFIGURED`**: the setting
   `storage.s3.aws_profile` names a profile this Mac's AWS config does not define, and the weekly
   run would be refused before it starts. Correct it as
   [A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define) says,
   then run the check again. An exit of `2`, "No such option", means the build installed in step
   1 is older than the check.

3. **Install the agent** with the caselists it already follows. The first command prints them,
   and the second is [Step 2](#step-2--install-the-agent)'s, with those caselists:

   ```bash
   plutil -extract ProgramArguments json -o - ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
   ops/launchd/install.sh --caselist hsld26 --caselist hspolicy26 --env prod --debate-research "$HOME/.local/bin/debate-research"
   ```

4. **Reload it.** launchd keeps the plist it loaded:

   ```bash
   launchctl bootout gui/$UID/com.debate-intelligence.caselist-sync
   launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
   launchctl print gui/$UID/com.debate-intelligence.caselist-sync
   ```

   If `bootstrap` says `Bootstrap failed: 5: Input/output error`, the bootout had not finished;
   run the bootstrap line again. `print` should show the copied wrapper, the caselists and the
   calendar interval, and `runs = 0`.

5. **Check it under launchd:**

   ```bash
   ops/launchd/install.sh --check-launchd
   ```

   Success is `exit code 0`, the version installed in step 1, the same `Evidence profile` row as
   in step 2, and the same `runs` before and after
   ([Step 3](#step-3--enable-it) has the table of exit codes). This is the check that counts: it
   is launchd's environment, not a shell's, reading the AWS config launchd's `HOME` leads to.

The next scheduled run is the first with the new build. If the profile is not defined on the day
after all, that run is no longer silent:
[A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define) says what
it leaves.

## Watching it

You should not have to go looking. A failed stage, an expired `caselist_token`, an expired SSO
session, and a cap backlog that has grown for two runs in a row each post a macOS notification
naming the command that fixes it (`caselist.notifier`, `auto` by default).
[What a notification says](#what-a-notification-says) lists each one. Every run also appends
one record to the run log, `<data_dir>/caselist-sync-runs.jsonl`, and publishes it to
`reports/sync-runs/<yyyy>/<run-id>.json` in the bucket (`v1-e34-t03`). The first command reads this
machine's log, the second the bucket's copy:

```bash
debate-research caselist runs --last 5
debate-research caselist runs --last 5 --remote
```

Its caption says how long ago the newest run started, and says the schedule may have stopped when
that is more than eight days — the one failure that leaves no record and sends no notification.
Its last column, `Parse stage`, is each run's parse counts
([Reading what it did](#reading-what-it-did)).

**The 06:00 run and the AWS session.** An SSO session lasts hours, not a week, so the Wednesday
06:00 run usually finds it expired. That is not a failure: the run downloads and imports
everything, records the publish as `pending` (outcome `publish_pending`), and the next run, or this,
publishes it. The first scheduled run, on 2026-10-14, did exactly that
([docs/data/caselist-sync-runs.md](../data/caselist-sync-runs.md)). To have the run publish by
itself, sign in on Tuesday evening; otherwise run the second line after it:

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev debate-research caselist pull --publish-pending
```

### The record, and the details beside it

A run is written down in two places (`v1-e34-t19`):

| | On this Mac | In the bucket | Holds |
|---|---|---|---|
| The **record** | `<data_dir>/caselist-sync-runs.jsonl` | `reports/sync-runs/<yyyy>/<run-id>.json` | What it always has: the outcome, the counts, each stage's outcome and reason |
| The run's **details** | `<data_dir>/caselist-sync-run-details.jsonl` | `reports/sync-run-details/<yyyy>/<run-id>.json` | Each failed stage's `error_codes` and `hint`, a pending stage's `earlier_findings`, the codes the exit code was decided from, and the parse stage's nine counts |

They are two files because the record cannot change. Every build refuses a record with a field
it does not know, and the agent goes on running the build it was installed with: a record with
one more field would be a run that build cannot see, in `caselist runs`, in the backlog it
carries from week to week, and in the list of records it still has to publish. So the record
this build writes is the record the installed build wrote, field for field, and what is new is
kept beside it under the same run id. No older build opens the details. `caselist runs` puts the
two together:

```bash
debate-research --json caselist runs --last 1 | jq '.data.runs[0].details'
```

`details` is `null`, and the `Parse stage` column says `not recorded`, for a run a build before
`v1-e34-t19` recorded. That is every run of an agent that has not been reinstalled since. It
also happens once in the other direction: a record that waited for a login and was then
published by an older build goes to the bucket without its details, which stay on this Mac.
After the reinstall every run has both.

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
| `objects_published` | What reached the bucket from the raw store: sources and manifests |
| `parse` | The parse stage's counts and nothing else: `caselists`, `full_parses`, `attempted`, `skipped`, `unsupported`, `failed`, `cards`, `uploaded`, `not_published`. `null` when the stage parsed nothing. See [The parse stage](#the-parse-stage) |
| `pending_publish` | Every snapshot this Mac has imported that the bucket had not confirmed complete when the publish stage ended: what [the pending-work file](#the-pending-work-file) holds after the run. Whether that waits for a login or for something else is the `publish` stage's outcome, not this list |
| `inbox_retention` | What left the inbox and the bytes freed, and what stayed and why. See [The download inbox](#the-download-inbox) |
| `full_archive` | What the complete-archive rotation decided and why (`reason`), what the weeklies left of the day's allowance, and for a complete archive imported, its `bytes` and its `withdrawn` and `superseded` counts. See [The complete archive](#the-complete-archive) |
| `openev_selections[]` | Each camp file OpenEv listed: its `openev_id`, the run's `decision`, and `inbox_file`, the first twelve hex digits of the download's sha256 once the run had its bytes (the name `inbox_retention` gives the same file) |
| `stages[]` | One entry per stage, each with the sentence saying why it ended that way (`reason`). A failed stage also carries `error_codes`, the code of each failure behind it, and, when a store refused it, `hint`, the fix that applies (`v1-e34-t13`). A `pending` stage carries `earlier_findings`, the codes of what it had already found when the session expired (`v1-e34-t19`); they never change the exit code. See [What the exit code says](#what-the-exit-code-says) |
| `run_record`, `run_details` | What the run log keeps of this run, and what is kept beside it. See [The record, and the details beside it](#the-record-and-the-details-beside-it) |
| `schema_version` | `5` since `v1-e34-t17`, which replaced `cards_parsed` and `parse_failures` (always `0`; no stage filled them) with `parse`. `4` since `v1-e34-t13`, which added `error_codes` and `hint` to every stage; a summary written before that says `3` and has neither. `v1-e34-t19` added `earlier_findings` to every stage and left the version at `5`, because nothing is decided from it. Nothing reads a summary back; `caselist runs` reads the run log, which builds of every kind read and write alike |

Nothing in that object is a school, a team code, a debater's initials, a disclosure path, a camp
file's title or the `caselist_token` — the policy forbids all of them in a log, and the summary is
built to the same rule, so these logs can be pasted into an issue as they are. A camp download is
named by its OpenEv id, `openev-777`, with `(sha256 2b912c191a8a)` once the run has its bytes, and
never by its file name, which is its title (`v1-e34-t12`). Summaries and logs written before that
change may still name camp files, so check older ones before pasting them. A failed stage's reason,
codes and hint name no path on this Mac either: a folder the operating system refused is named by
what it is for, and the data directory and the inbox by those names (`v1-e34-t13`). A run that ended
on a bug, exit `70`, prints the error envelope instead of the summary, and it names the exception's
class and not its message (`v1-e01-t25`). An envelope written before that change may quote a path
in `error.message`, so check older exit-`70` lines before pasting them.

## What the exit code says

A run that captured everything exits `0`. When a download, an import or a publish did not complete,
the exit code says whether doing nothing is enough (`v1-e34-t13`). Each failed stage records the
error code of every failure behind it, in `stages[].error_codes`, and the command reads the codes
of the stages that had to finish (select, download, import, publish). The envelope's `error.code`
is `CASELIST_PULL_INCOMPLETE` either way.

| Exit | Means | What to do |
|---|---|---|
| `0` | Every stage that puts bytes somewhere durable finished. That includes a run that found nothing new, one whose `publish` is `pending` on an expired SSO session, and one where only `report` or `retention` failed | Nothing, or what the stage table names. `publish: pending` is under [When something goes wrong](#when-something-goes-wrong) |
| `3` | **Transient.** Every failure is one a later run may not meet | Usually nothing: next week's run retries it, and what was captured is kept. Read the failed stage's `hint` first; a refused store has a fix to make before the retry helps |
| `1` | **A verdict.** At least one failure will be the same next time, or the run was refused before it started | Read the failed stage's reason and deal with what it names |
| `70` | A bug | Report it, by the class the envelope names (`error.details.exception_type`): since `v1-e01-t25` the log holds the class and never the exception's message. The same command by hand with `--verbose` prints the traceback, message included, on stderr. That traceback can quote a path on this Mac and a camp file's title, so read it and do not paste it as it is |

The agent never runs again on any exit code: launchd records the number and waits for next week's
slot. A `3` on Wednesday therefore means "next Wednesday's run, or the same command by hand now".

Which failure is which:

| The stage failed because | `error_codes` | Exit |
|---|---|---|
| The bucket did not answer: a 5xx, a throttle, a timeout | `STORE_UNAVAILABLE` | `3` |
| The bucket refused the profile: it is signed in and lacks a grant | `STORE_ACCESS_DENIED` | `3`, with a `hint` |
| This Mac refused a folder under the data directory, or a manifest file in one | `STORE_ACCESS_DENIED` | `3`, with a `hint` |
| OpenCaselist answered a download with a 5xx, or the connection failed or timed out, and the client's retries ran out | `PROVIDER_UNAVAILABLE` | `3` |
| OpenCaselist rate-limited a download, and it was not the daily cap | `PROVIDER_RATE_LIMITED` | `3` |
| The daily cap, on a weekly archive | none: the stage completes and the week is deferred | `0` |
| The daily cap, on a camp file | `DAILY_DOWNLOAD_LIMIT_REACHED` | `1`: a verdict for the day |
| OpenCaselist answered `401` or `403`: the `caselist_token` expired. Never retried, by policy | `CASELIST_AUTH_EXPIRED` | `1` |
| The file host no longer serves an archive it listed | `ARCHIVE_UNAVAILABLE` | `1` |
| An archive is over `caselist.max_archive_bytes` | `ARCHIVE_TOO_LARGE` | `1` |
| A download did not arrive whole | `DOWNLOAD_INTEGRITY_ERROR` | `1` |
| A zip cannot be read: it is not a zip, or this Mac will not open the file. That archive's import fails, and the run's other archives are imported | `UNREADABLE_ARCHIVE` | `1` |
| A manifest on this Mac has a line nobody can read, so the snapshot it describes cannot be published. The other snapshots are | `UNREADABLE_MANIFEST` | `1` |
| A copy of the suppression list has a line nobody can read | `UNREADABLE_APPEND_ONLY_RECORD` | `1` |
| A source's bytes in the bucket are not the ones its key names | `CHECKSUM_MISMATCH` | `1` |
| The pending-work file names a snapshot this Mac holds no manifest for | `NOTHING_TO_PUBLISH` | `1`, once: the snapshot leaves the file, because no run here can publish it |
| The pending-work file cannot be read | `PENDING_WORK_UNREADABLE` | `1`, with a `hint`. The file is left as it is. See [The pending-work file](#the-pending-work-file) |
| The AWS profile the run was given is not one this Mac's AWS config defines | `STORE_PROFILE_NOT_CONFIGURED` | `1`, with a `hint`. See [A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define) |
| `--full-archive` cannot be covered by the day's allowance | none: the run is refused before any stage, with `error.code` `FULL_ARCHIVE_REFUSED` | `1` |
| Anything with a code that is on neither list, or with no code | for example `INTERNAL_ERROR` | `1` |

**The parse stage decides nothing here.** It is not one of the stages that had to finish, so a
failed parse stage leaves the exit code where the four above put it, `0` when they finished. It
records its codes all the same, in its own `error_codes`: `PARSE_FAILURE_RATE_EXCEEDED`, the codes
above for a store that did not answer or refused, the code of each object of the parsed store the
bucket did not confirm, and `INTERNAL_ERROR` for a parse that crashed.
[The parse stage](#the-parse-stage) says what to do about each.

**`publish: pending` decides nothing either, whatever it found first.** A publish that the session
expired on is `pending` and exits `0`, as it always has. If a snapshot had already ended incomplete
on a code before that, a checksum mismatch say, the stage carries the code in `earlier_findings`
and not in `error_codes`, and the exit code does not read it (`v1-e34-t19`). The login notification
says so when the code is one that needs a person
([What a notification says](#what-a-notification-says)). The retry after the login then reports it
as a failed publish, with the exit code that goes with it.

One failure of the second kind among any number of the first makes the run a `1`: a week that
cannot be read is not fixed by the bucket coming back. A failure that ends the run before any stage
records it, such as OpenCaselist not answering the listing, exits as it does in every other command:
`3` for a store or a provider that did not answer, with that failure's own `error.code`.

**A `hint` on a failed stage is the fix that applies, and it is never a login.** The pending-work
file has one when it cannot be read ([The pending-work file](#the-pending-work-file)). Two refusals
have one, and they are told apart by where the refusal came from:

* *This Mac refused a folder.* The hint names the folder by what it is for ("the blob directory",
  "the manifest directory") and the setting `storage.data_dir`. Check that the user the agent runs
  as can read and write the data directory, then run the command again. A single manifest file the
  user cannot open, or a manifest folder the user cannot write to, is the same refusal with the
  same hint (`v1-e34-t19`; it used to be exit `70`).
* *The bucket refused the profile.* The hint says the profile lacks a grant and points at
  [`evidence-store.md`](evidence-store.md), which lists what each profile is granted and how to
  check it. `aws sso login` does not change a grant.

Before `v1-e34-t13` both were reported as `publish: pending` with a notification naming
`aws sso login`, and a failed stage exited `1` whatever it failed on. The sentence about the grant
is written by the S3 adapter (`v1-e29-t07`), so `caselist publish`, `caselist status`, `store sync`
and `caselist remove` show the same one.

### A profile the AWS config does not define

`storage.s3.aws_profile` in the environment's profile names the AWS profile the run publishes with.
When this Mac's AWS config defines no profile of that name, the run cannot build its connection to
the bucket at all, and it is refused before any stage:

* exit `1`, with `error.code` `STORE_PROFILE_NOT_CONFIGURED`;
* the message names the profile and the setting it came from, and the `hint` says to correct the
  setting or add the profile, as [`evidence-store.md`](evidence-store.md) describes;
* nothing is fetched or imported, and the pending-work file is not touched.

**The run is recorded and announced** (`v1-e34-t22`). It used to be silent: the run log's copy in
the bucket is built from the same profile, so nothing could be built to record the run, and the
exit code launchd kept was the only sign. Now the refusal is the error the run stopped on:

* **A record on this Mac.** One line in `<data_dir>/caselist-sync-runs.jsonl` with the outcome
  `failed`, no stages, and the error's class, `StoreProfileNotConfigured`. It is the record a run
  stopped by an expired `caselist_token` has always had, and nothing is added to it.
* **Its details beside it.** One line in `<data_dir>/caselist-sync-run-details.jsonl` with
  `failure_codes` of `STORE_PROFILE_NOT_CONFIGURED` and the fix as `hint`, which names the setting.
* **One banner**, titled `caselist pull failed: needs a person`:

  > Run 20261014T100000Z (prod) stopped with StoreProfileNotConfigured. A person should look: at
  > least one failure here will be the same on the next scheduled run. The bucket was never
  > reached: set storage.s3.aws_profile to a profile this machine's AWS config defines, or add the
  > profile to it: docs/runbooks/evidence-store.md lists the evidence profiles and how they are
  > added. It is not an expired session, and logging in changes nothing.

* **The record is owed to the bucket.** It could not be published, since the bucket is what could
  not be reached. Its run id is kept in `<data_dir>/caselist-sync-records-pending.json`, behind any
  already there, and the next run that reaches the bucket publishes the record and its details
  with its own. That is next week's run or, once the setting is corrected, this:

  ```bash
  debate-research caselist pull --publish-pending
  ```

`debate-research caselist runs` shows the refused run from this Mac's log straight away, and from
the bucket once a later run has published it.

**What to correct.** The agent's build takes the profile's name from the profile bundled into it,
`debate-prod-evidence` for prod, unless `DEBATE_STORAGE__S3__AWS_PROFILE` in the plist says
otherwise. So either this Mac's AWS config has lost that profile, and
[`evidence-store.md`](evidence-store.md) says how the evidence profiles are added, or the
override misspells it. Then confirm it, as the agent runs:

```bash
AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research doctor --evidence-profiles; echo "doctor exit=$?"'
```

`doctor exit=0` and the profile's row reading `defined`
([Checking the evidence profiles](#checking-the-evidence-profiles)). `ops/launchd/install.sh
--check-launchd` makes the same check under launchd, and both are in
[Reinstalling the agent](#reinstalling-the-agent), so that the setting is found by a person
before a scheduled run finds it.

It is a configuration error, not an expired session: `aws sso login` does not define a profile, and
next week's run ends the same way. Until `v1-e29-t07` it was reported as
`STORE_CREDENTIALS_EXPIRED` with exit `3`, "a retry may succeed".

## What a notification says

Each banner has a title, the command to run once the fix is made (under the title), and a body.
A failed run's title is its verdict, so it can be read without opening the banner
(`v1-e34-t19`). The verdict is the exit code said in words, decided by the same rule.

| Title | When | Exit |
|---|---|---|
| `caselist pull failed: will be retried` | A download, an import or a publish failed, or the run stopped on an error, and every failure is one a later run may not meet | `3` |
| `caselist pull failed: needs a person` | The same, and at least one failure will be the same next week. Also a run that stopped on a bug | `1`, `70` |
| `caselist pull finished with a failed stage` | Only a stage that did not have to finish failed: parse, report or retention | `0` |
| `caselist publish waiting for an AWS login` | The SSO session had expired | `0` |
| `caselist pull stopped: OpenCaselist login expired` | The `caselist_token` expired | `1` |
| `caselist backlog growing` | The cap has deferred more archives for two runs in a row | `0` |

**The two wordings of a failed run.** The body names each failed stage with the codes it failed on,
and then says one of two things. When the next scheduled run should retry it:

> Run 20261014T100000Z (prod): the publish stage failed on STORE_UNAVAILABLE. The next scheduled run should retry it: every failure here is one a later run may not meet. What was captured is kept.

When a person should look:

> Run 20261014T100000Z (prod): the import stage failed on UNREADABLE_ARCHIVE. A person should look: at least one failure here will be the same on the next scheduled run. What was captured is kept.

A run that stopped on an error before any stage could record it says `stopped with` and the
error's class, then the same sentence. A run refused because its AWS profile is not defined is
one of these, with the fix after it
([A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define)).

**The fix, when the stage has one.** A failed stage's `hint` follows the sentence, word for word as
the summary gives it. Either wording can have one. With the first, the hint is what to do before
the retry can help: a refusal exits `3`, and next week's run is refused again until the permission
or the grant is fixed.

> Run 20261014T100000Z (prod): the publish stage failed on STORE_ACCESS_DENIED. The next scheduled run should retry it: every failure here is one a later run may not meet. What was captured is kept. This machine refused the blob directory: check that this user can read and write it, under the environment's data directory (storage.data_dir). It is a permission on this machine, not the AWS session.

The hints are the ones [What the exit code says](#what-the-exit-code-says) describes: a folder
this Mac refused, a grant the profile lacks, and the pending-work file when it cannot be read.
None of them names a path: a folder is named by what it is for.

**A failed parse stage** gets neither wording, because the run exits `0` and the next scheduled run
does not retry a parse. Its banner carries the stage's own hint, which names the command:
`debate-research caselist parse --caselist <slug> --publish` for a parsed store the bucket did not
take, and `debate-research caselist parse --caselist <slug> --failures` for a failure rate over the
threshold. See [The parse stage](#the-parse-stage).

**A login that will not be enough.** When the session expired after a snapshot had already ended
incomplete on something no later run cures, the login banner adds a sentence:

> Run 20261014T100000Z (prod) kept everything it fetched; 2 snapshot(s) and the run record wait to be published. A person should look as well: before the session expired a snapshot ended incomplete on CHECKSUM_MISMATCH, which the login will not fix.

Log in and drain as usual. The retry publishes the rest and reports that snapshot as a failed
publish; the stage's reason names it. A snapshot that ended incomplete on something a retry does
cure, a `503` say, adds no sentence: the drain publishes it.

Notification Centre shows the first lines of a body and the rest when the banner is opened. The
whole of it is also in the run's details:

```bash
debate-research --json caselist runs --last 1 | jq '.data.runs[0].details'
```

## The complete archive

Besides the week's weeklies, a run may fetch **one** caselist's complete archive,
`<slug>-all-<date>.zip` (`v1-e34-t04`). It is the only way to see that a disclosure was taken down
upstream: a file an earlier snapshot held and the complete archive does not. A weekly's `REMOVED`
cannot say that, because a weekly is a window of edits and its file names carry a per-team
sequence number.

The rules, every run:

* **After the weeklies.** The weeklies are planned first, against the same five-a-day ledger. A
  complete archive is fetched only from what they leave, and is fetched last.
* **One per run**, whatever is due.
* **Due** when the newest complete archive this machine holds is more than
  `caselist.full_archive_interval_days` old (30 by default; at least 7), or when it holds none.
* **Least recently refreshed first**: a caselist with none yet, then the oldest. The others wait
  for the next run, so the rotation catches up by itself after a missed week.

With three caselists and weekly runs, each caselist's complete archive is refreshed about every
five weeks: due after 30 days, fetched by the next run that has a download left over. The policy's
E34 gate 4 ("weekly cadence at most") is kept: nothing runs more often than the weekly agent, and
there is no second schedule.

`caselist.full_archive_rotation = false` in the profile turns the rotation off. The run then says so
and fetches none, and `--full-archive` still works.

**Reading what it did.** The `select` row of the table ends with a `complete archive:` sentence: what
was fetched or why nothing was, what the weeklies left of the allowance, and each caselist's state
and when it was last refreshed. The summary's `full_archive` holds the same, and for an imported one:

| Field | What it says |
|---|---|
| `bytes` | The complete archive's size. A complete archive is the largest file the site serves; the pull accepts up to `caselist.max_full_archive_bytes` (8 GiB), and a weekly is still held to `caselist.max_archive_bytes` (2 GiB) |
| `withdrawn` | Files an earlier snapshot of the caselist held (weekly or complete) that are gone from the complete archive, together with every path they were held at |
| `superseded` | Files gone from the complete archive whose path is still there, holding other bytes: re-uploaded |
| `earlier_snapshots` | How many earlier snapshots it was compared with |

Counts only, never a path or a name. A file re-uploaded under a new name counts as withdrawn,
because its sequence number changed its path. Neither count suppresses anything: whether a
withdrawal upstream should is a question for the data-use policy, not for the sync. The complete
archive's manifest is `manifests/<slug>/full/<date>.jsonl`, beside the weekly series and never in
it, and its snapshot is named `full/<date>` by `caselist status` and `caselist publish`. It leaves
the inbox on the same conditions as a weekly. `caselist remove` reaches it like any other manifest.
Never pass one to `caselist import`, which refuses it: that command files into the weekly series.

**When to reach for `--full-archive`.** To refresh one caselist now rather than wait for the
rotation: the first time after installing a build with the rotation, to see a withdrawal count
for a caselist you are about to report on, or after its complete archive has been deferred for
the weeklies several runs in a row. It takes the run's one slot for that caselist, still after the
weeklies, and the run refuses, exit `1` with nothing fetched, when the day's allowance cannot cover
it. Always dry-run first: the caption says what would be fetched and how many bulk downloads the
weeklies leave.

```bash
DEBATE_ENV=dev debate-research caselist pull --caselist hsld26 --full-archive hsld26 --dry-run
```

Then, if the caption says it would be fetched:

```bash
DEBATE_ENV=dev debate-research --json caselist pull --caselist hsld26 --full-archive hsld26 | jq '{succeeded: .data.succeeded, stages: [.data.stages[] | {stage, outcome}], full_archive: .data.full_archive}'
DEBATE_ENV=dev debate-research caselist status --caselist hsld26
```

Check one caselist at a time in dev: an unscoped dev `caselist status` exits `1` because of
`testcl26`, kept there by PM decision.

To put the complete archive in prod, publish the caselist from the dev store, as the backfill did.
A whole-caselist publish includes its complete archives:

```bash
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="$HOME/.debate-research/dev"
debate-research caselist publish --caselist hsld26 --dry-run
debate-research caselist publish --caselist hsld26 --confirm-prod
debate-research caselist status --caselist hsld26
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

**An agent installed before this build** does none of this: it runs the build it was installed
with, whose weekly run lists the complete archive and never fetches it. After a reinstall with a
build containing `v1-e34-t04` (Step 2), its next run fetches one complete archive if the weeklies
leave a download, because no caselist has one yet, and the run after that the next caselist.
`debate-research caselist pull --help` lists `--full-archive` on a build that has it.

## The parse stage

After it has published, a run parses what it imported (`v1-e34-t17`). It is the same pipeline
`debate-research caselist parse` runs ([`parsed-card-store.md`](../data/parsed-card-store.md)):

* **Which caselists.** Each caselist a weekly archive or a camp file was imported into, once. Camp
  files are the caselist `openev`. A complete archive names none, because its sources are not
  parsed. A run that imported nothing parses nothing and rebuilds nothing.
* **What is parsed.** Every source of that caselist not yet parsed under the build's parser and
  profile versions. In an ordinary week that is the week's new sources; everything else is
  `skipped`.
* **The aggregates.** The caselist's index, failures file and occurrence table are rebuilt from
  every source it holds. This is most of the stage's time.
* **Published.** Where the run publishes at all, the caselist's version directory is then copied
  to `parsed/<caselist>/<version>/` in the bucket: whatever the bucket lacks of the whole directory.

### The setting, its default and the figures behind it

`caselist.parse_imported_sources` turns the stage on or off. **It is on by default.**

The agent has no time limit to fit inside. `ops/launchd/com.debate-intelligence.caselist-sync.plist.template`
sets no `ExitTimeOut` and no `TimeOut`, the wrapper `exec`s the command with no timeout, and the
installed plist, read on 2026-10-11, has neither key. So the stage is sized against the bounds a
run does have. The figures come from two operator runs, both from a terminal.

**The rebuild alone.** A `caselist parse --publish` that found nothing to parse and nothing to
upload: the rebuild and the publish's checksum checks, which is what each caselist a pull imports
into adds to that pull.

| Measured | hsld26 | hspf26 | hspolicy26 | openev | All four | The agent's three |
|---|---|---|---|---|---|---|
| 2026-10-11, parser `2026.10.10-docx-2` and `card-fingerprint-v2`, the build current on that day | 314 s | 193 s | 473 s | 71 s | 1,051 s (17.5 min) | 980 s (16.3 min) |
| 2026-10-10, parser `2026.09.20-docx-1` ([`caselist-parse-report.md`](../data/caselist-parse-report.md), `v1-e31-t06`) | 348 s | 214 s | 460 s | 60 s | 1,082 s (18.0 min) | 1,022 s (17.0 min) |

The arithmetic below uses the 2026-10-11 row. The two runs differ by 3% in total and by up to 18%
for one caselist (openev), so read any one figure as good to about that.

**A first parse of everything**, as after a parser-version bump:

| Measured | All four |
|---|---|
| 2026-10-11, parser `2026.10.10-docx-2` | about 30 minutes, 1,800 s |
| 2026-10-10, parser `2026.09.20-docx-1` | 518 + 352 + 747 + 106 = 1,723 s (28.7 min) |

**One new source.** A first parse less the rebuild is the parsing and uploading. On 2026-10-10
that was 1,723 − 1,082 = 641 s for 9,741 DOCX sources, 0.066 s each. The 2026-10-11 run is known
only as "about 30 minutes", which gives about 1,800 − 1,051 = 749 s, 0.077 s each if it read
the same 9,741 sources. The arithmetic uses the larger, 0.077 s. The largest week so far (2026-09-15) brought
2,884 new sources to the three weekly caselists, which at that rate is 222 s; the latest
(2026-10-06) brought 2,471, which is 190 s. So:

| A scheduled run that | Costs | In minutes |
|---|---|---|
| imports all three weekly caselists in an ordinary week | 980 + 190 = 1,170 s | 19.5 |
| does so in the largest week on record | 980 + 222 = 1,202 s | 20.0 |
| also imports a camp file | add 71 s | 20.7 to 21.2 |
| is the first after a parser-version bump, all four caselists | about 1,800 s | about 30 |

Against each bound:

| Bound | Where it is set | Size | The stage's share, at 20 and at 30 minutes |
|---|---|---|---|
| A time limit on the agent | The plist template and the wrapper | None | Nothing to exceed |
| The next scheduled run | `StartCalendarInterval`, weekly | 10,080 min | 0.2% and 0.3% |
| The AWS session, which only the publish needs | `session_duration` of the operator permission set, `infrastructure/modules/evidence_bucket/operator_access.tf` | 480 min | 4.2% and 6.3% |
| The PM's line for building an incremental rebuild | `v1-e31-t06`'s review: 900 s for one caselist's rebuild | 900 s | The slowest rebuild, hspolicy26's 473 s, is 53% |

Three things these figures do not cover:

* **They were measured in a terminal.** The agent runs with `ProcessType` `Background` and
  `LowPriorityIO`, which macOS gives less of the machine. The scheduled figure is not known until
  the first scheduled run with this build records it.
* **The rebuild grows with the store.** hspolicy26 has gained about 640 sources a week over the
  last three weeks, on a store of 2,629 DOCX sources. If its rebuild grows in step from 473 s, it
  reaches the 900 s line at about 5,000 sources, a little under four weeks away.
* **Nothing stops a stage that runs long.** With no time limit, a rebuild that takes hours holds
  the run's lock for hours, and `caselist remove` and any other pull are refused meanwhile. The
  sign is `caselist runs` showing no record for the week.

**Turning it off for the agent**, without a new build: add the setting to the plist's environment
and reload the agent ([Step 3](#step-3--enable-it)).

```bash
/usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:DEBATE_CASELIST__PARSE_IMPORTED_SOURCES string false" ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
launchctl bootout gui/$UID/com.debate-intelligence.caselist-sync
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
```

The stage is then `skipped`, with the setting's name as its reason, and `caselist parse` does the
same work by hand. Running `ops/launchd/install.sh` again writes the plist afresh, without the
line. `parse_imported_sources = false` under `[caselist]` in a profile does the same for a build
made from it.

### Reading what it did

The summary's `parse` holds counts only, and the stage's row in the table says the same in a
sentence. `caselist runs` shows every run's counts in its last column, `Parse stage`
(`v1-e34-t19`), and the stage's sentence under the table for the newest run, unless the stage was
skipped:

```bash
debate-research caselist runs --last 5
tail -n 1 ~/Library/Logs/debate-research/caselist-sync.jsonl | jq '.data.parse'
debate-research --json caselist runs --last 1 | jq '.data.runs[0].details.parse'
debate-research --json caselist runs --last 1 | jq '.data.runs[0].stages[] | select(.stage == "parse")'
```

The column gives the nine counts on four lines: caselists and how many in full; sources attempted,
skipped, unsupported and failed; cards; objects uploaded and caselists not published. It says
`did not run` for a run whose parse stage parsed nothing (turned off, or nothing imported), and
`not recorded` for a run a build before `v1-e34-t19` recorded, which kept no counts. The counts are
in the run's details, not its record
([The record, and the details beside it](#the-record-and-the-details-beside-it)).

| Count | What it says |
|---|---|
| `caselists` | Caselists parsed |
| `full_parses` | Of those, the ones parsed in full because the build's version directory held nothing. Expect `0`. Anything else is a first parse or a new parser version; see below |
| `attempted`, `skipped` | Sources handed to the parser, and sources already parsed and left alone |
| `unsupported` | Of those attempted, PDFs, legacy `.doc` files and other formats V1 does not read. Not failures |
| `failed` | Of those attempted, the ones that could not be read. `caselist parse --caselist <slug> --failures` lists them |
| `cards` | Cards in the sources this run parsed |
| `uploaded` | Objects of the parsed store put in the bucket: a file for each source, and the aggregates that changed |
| `not_published` | Caselists whose parsed store this run did not publish complete. `0` in a good week |

**The failure rate.** A caselist's parse fails the stage when more than `parse.failure_rate_threshold`
(5%) of the sources it tried could not be read, but only when it tried at least
`parse.failure_rate_minimum_sources` of them. Below that, failures are counted in `failed` and never
fail the stage. **The default is 100**, for two measured reasons:

* The most unreadable files any one week has delivered is 5, all exports of one program, in
  hsld26's week of 2026-09-15. Five is over 5% of any run of fewer than 100 sources, and exactly
  5%, so not over it, of a run of 100.
* A weekly pull tries only that week's new sources. Of the 39 caselist-weeks that brought the
  store a new source, 19 had fewer than 20 new DOCX sources and 5 more had 20 to 99; one unreadable
  file in a week of ten is 10%. The 15 weeks of 100 or more hold 9,305 of the 9,639 DOCX sources,
  96.5%, and every failure recorded so far fell in a week of 300 or more, so the rate is still
  judged where the files are.
  A camp release, the smallest run the rate has been read from, is 102 sources.

A run under the minimum that fails outright, every source, is still not a failed stage. Its `failed`
count says so, and the next week of 100 or more is judged.

### After a release that bumps the parser version

The stage parses whatever is not parsed under the build's versions. A new parser version starts a
new version directory, which holds nothing, so the first scheduled run after such a release would
parse every imported caselist in full: about 30 minutes where it takes 20, with `full_parses` above
`0`. A caselist that run does not import into, `openev` in most weeks, would stay on the old version
until a camp file arrives.

Do the full parse by hand instead, before the agent meets the new build. Install the build on a
day other than Wednesday morning, or boot the agent out first ([Disabling it](#disabling-it)).

1. See what is due. `To parse` equal to `Sources` means a full parse.

   ```bash
   DEBATE_ENV=dev debate-research caselist parse --caselist hsld26 --dry-run
   ```

2. Parse and publish each caselist, one at a time, with no pull running. About 30 minutes for all
   four: that is the 2026-10-11 parse under `2026.10.10-docx-2`, and the 2026-10-10 one took 518 s,
   352 s, 747 s and 106 s, 28.7 minutes.

   ```bash
   aws sso login --profile debate-dev-evidence
   DEBATE_ENV=dev debate-research caselist parse --caselist hsld26 --publish
   DEBATE_ENV=dev debate-research caselist parse --caselist hspf26 --publish
   DEBATE_ENV=dev debate-research caselist parse --caselist hspolicy26 --publish
   DEBATE_ENV=dev debate-research caselist parse --caselist openev --publish
   ```

3. Reinstall and reload the agent ([Step 2](#step-2--install-the-agent), [Step 3](#step-3--enable-it)).

If this was skipped, nothing is lost: the scheduled run does the full parse itself and says so in
`full_parses`, and the last line of step 2 catches `openev` up.

### One data directory for each bucket

The aggregates a run publishes are rebuilt from the data directory the run reads. The agent parses
`~/.debate-research/dev` and publishes to the dev bucket, and the parsed store in prod is published
by hand from that same directory. Do not point an agent at a bucket whose parsed store another
data directory publishes: each would replace the other's aggregates with its own.

### When the AWS session has expired

The parse itself needs no session, so the parsed store on this Mac is current either way. Its copy
in the bucket is not: the stage is `pending`, `not_published` counts the caselists, and the stage's
reason names them. The import and the raw publish are untouched by this; what they owe is in
[the pending-work file](#the-pending-work-file) exactly as before.

**`caselist pull --publish-pending` does not publish the parsed store.** The pending-work file
lists snapshots, and a parsed store is a version directory, which the file cannot name. After the
login, either leave it, because the next run that imports into the caselist with a session
publishes the whole directory, or publish it now:

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev debate-research caselist pull --publish-pending
DEBATE_ENV=dev debate-research caselist parse --caselist hsld26 --publish
```

The last line parses nothing that is parsed, rebuilds the aggregates and uploads what the bucket
lacks, so it takes about as long as that caselist's rebuild in the table above. In prod it needs
`--confirm-prod`. However many weeks were missed, one run per caselist catches up.

## The download inbox

`<data_dir>/inbox` (or `caselist.inbox_dir`) is where a pull downloads to and what it imports from.
Between two runs it holds:

* **Weekly archives** waiting to be imported or published (`<slug>-weekly-<date>.zip`): a week whose
  import failed, a newer week waiting behind it, or a week whose publish is pending an AWS login.
* **Camp downloads** in the same state (`openev-<id>-<name>`), and any camp download the OpenEv
  delivery record does not cover.
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

**A camp release of junk alone leaves on a condition of its own** (`v1-e34-t15`). A release holding
nothing but junk (`.DS_Store`, `__MACOSX/`, a Word `~$` lock file, and no camp file) is imported
once, keeps nothing, and is not imported again (`v1-e34-t08`). No manifest row comes from its bytes,
so condition 1 can never hold, and until `v1-e34-t15` it stayed for good as `not_imported`. A Word
lock file in it stores the name of whoever had the document open, which is one more reason not to
keep it. It is removed when its id's entry in the delivery record exists, names no member, and names
these exact bytes as what the id delivered. The entry is written only once an import completes, and
it is what the next run reads to neither fetch nor import the release again. There is no snapshot
for the bucket to confirm. Its reason is `junk_only`, never `not_imported`.

What leaves, and when:

| What | Leaves on | Until then |
|---|---|---|
| A weekly or complete archive | The first run that finds its snapshot confirmed in the bucket after importing it: usually the run that imports it | `not_imported` or `not_confirmed` |
| A camp download that held camp files | The first run that finds its release confirmed in the bucket, with its delivery entry written | `not_imported`, `not_confirmed` or `no_delivery_record` |
| A camp release of junk alone | The run that imports it, since the import writes the entry; or, for one an earlier build imported and left, the next real run | `not_imported`, while its import has not completed |
| A camp download with no delivery entry, or whose entry names camp files no manifest row came from | Not by retention, until an import completes and its release is confirmed | `not_imported` or `no_delivery_record` |
| Anything the pull did not name | Never | `unclassified` |

**Nothing is kept longer, the newest week included.** The usual reason to keep a zip is that
re-importing after a failed publish costs nothing. Here a zip is removed only after its publish is
confirmed, and a publish (or a re-publish, after drift) reads the local store, never the inbox, so
that case cannot arise. A removed week is never fetched again: a week on or before the newest
imported one is `already_imported` whether or not its zip is here. The site keeps the weekly
back-catalogue (ADR-0017), so a zip can be fetched again by hand if one is ever needed.

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
name given by hand can say anything. A camp release of junk alone is named by its OpenEv id as well,
and never by anything inside it, a lock file's contents least of all:
`1 camp download(s), openev-960 sha256 97633cd06d14 (imported, and it held junk alone)`. The JSON
summary carries the same lists under `inbox_retention`. A removed file carries no `reason`, except a
camp release of junk alone: `"reason": "junk_only"`, with its `"openev_id"`. A kept file's reason is
one of:

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

## The pending-work file

`<data_dir>/caselist-sync-pending.json` is the list of publishes this Mac owes (`v1-e34-t18`).

**What it holds.** Every snapshot this Mac has imported that the bucket has not confirmed
complete, and nothing else. It does not matter what ended the publish stage: an expired session, a
bucket that refused or did not answer, an upload that failed, or the Mac shutting down part-way.
A run writes the file before its first upload and again when the publish stage ends, so a run
that is killed has already written down what it owes. After a killed run the file can name a
snapshot the bucket does hold; the next run finds it complete and takes it off.

**When it is there.** Only while something is owed. A run that owes nothing removes it, so no
file means nothing is owed.

**Its shape.** One object with one list. Each entry is a target `caselist publish` would take: a
week, a complete archive (`full/<date>`), or a camp release under `openev`.

```json
{
  "publish": [
    {"caselist": "hsld26", "snapshot": "2026-10-07"},
    {"caselist": "hsld26", "snapshot": "full/2026-10-07"},
    {"caselist": "openev", "snapshot": "2026-policy"}
  ]
}
```

**What takes a snapshot off it.** The bucket confirming it complete: every source's checksum read
back from the bucket, then the manifest. Being attempted is not enough. One other thing does: a
snapshot this Mac holds no manifest for can never be published from here, so the run that finds
it reports it (`NOTHING_TO_PUBLISH`, exit `1`) and drops it, where it used to fail every run
after.

**Checking it is empty after a retry.** Run these as the agent's user, with the agent's
`DEBATE_ENV`. The first line asks the installed build where its data directory is.

```bash
PENDING="$(debate-research --json config show | jq -r '.data.settings["storage.data_dir"]')/caselist-sync-pending.json"
ls -l "${PENDING}"
```

`No such file or directory` is the answer you want: nothing is owed. If the file is listed,
something still is, and this shows what:

```bash
jq . "${PENDING}"
```

The retry's own summary says the same thing in `pending_publish`, which is `[]` when the file is
gone.

**If the file cannot be read.** The publish stage fails with `PENDING_WORK_UNREADABLE` and exit
`1`, and the run leaves the file exactly as it found it. A run never writes over a file it could
not read, because the file may name snapshots nothing else remembers. What that run imported
itself is still published; if the bucket did not confirm some of it, the stage's `reason` ends
with `not recorded as owed:` and their names. To repair it:

1. Look at it with `cat "${PENDING}"`. A file cut short usually still shows which snapshots it
   named.
2. Write it again in the shape above, with those snapshots and any the stage's `reason` listed.
   Then drain it and check it is gone, as above:

   ```bash
   debate-research caselist pull --publish-pending
   ```

3. If it cannot be made out at all, move it aside and ask the bucket instead. `caselist status`
   names every snapshot this Mac holds that the bucket does not, one caselist at a time, and
   `caselist publish` publishes them. Use `--caselist openev` for the camp releases, and add
   `--confirm-prod` to the publish in prod.

   ```bash
   mv "${PENDING}" "${PENDING}.unreadable"
   debate-research caselist status --caselist hsld26
   debate-research caselist publish --caselist hsld26
   debate-research caselist status --caselist hsld26
   ```

The sync writes the file to a second file beside it, puts that on the disk, renames it into place
and then puts the folder on the disk too (`v1-e34-t19`), so neither a run that dies while writing
nor the Mac losing power just after can be what cut it short. The download ledger, the OpenEv
delivery record and each run's summary are written the same way. Something else did: an editor, a
restore, a full disk at the wrong moment for another tool.

## When something goes wrong

**`pending_publish` is not empty, and `publish` is `pending`.** The SSO session expired. Log in
and drain it:

```bash
aws sso login --profile debate-prod-evidence
debate-research caselist pull --publish-pending
```

The retry takes a snapshot off the list only once the bucket has confirmed it. If the session
expires again part-way, what was confirmed is off the list and the rest is still on it; log in and
run the same command again. [The pending-work file](#the-pending-work-file) says how to check that
nothing is left.

**`pending_publish` is not empty, and `publish` is `failed`.** The snapshots are imported and still
owed, and logging in is not the fix. If the stage has a `hint`, a store refused it: make the fix the
hint names (a permission on the data directory, or a grant; see
[What the exit code says](#what-the-exit-code-says)). If its code is `STORE_UNAVAILABLE`, the bucket
did not answer and there is nothing to fix. Either way the next scheduled run publishes them, or
drain them now:

```bash
debate-research caselist pull --publish-pending
```

**`publish` is `pending`, and its `earlier_findings` is not empty.** The session expired, and
before it did a snapshot ended incomplete on the code shown. Log in and drain it as above. If the
banner said *a person should look as well*, the drain will report that snapshot as a failed publish
with exit `1`, and its reason will name the snapshot and the source: a `CHECKSUM_MISMATCH` is a
source whose key in the bucket holds other bytes, which nothing overwrites and a person has to
look at ([`evidence-store-cli.md`](../guides/evidence-store-cli.md)).

**`publish` is `failed` with `UNREADABLE_MANIFEST`.** A manifest on this Mac has a line that is not
what the importer writes, so the snapshot it describes was not published; every other snapshot
was, and that one stays in [the pending-work file](#the-pending-work-file). The stage's reason
gives the manifest's key and the line number, never the line. Before `v1-e34-t19` this ended the
run with no summary. Importing the archive again rewrites the manifest: put the zip back in the
inbox if retention has removed it, or run `caselist import` on it, then drain.

**`publish` is `failed` with `PENDING_WORK_UNREADABLE`.** The file that lists what is owed could not
be read, and the run left it alone. This is exit `1` and no later run fixes it by itself. Follow
[The pending-work file](#the-pending-work-file).

**`parse: pending`, and exit `0`.** The run parsed what it imported and could not publish the
parsed store for want of an AWS session. See
[When the AWS session has expired](#when-the-aws-session-has-expired).

**`parse: failed`, and exit `0`.** What was imported and published is kept; the stage's
`error_codes` say what it failed on, and its reason names each caselist.

* `PARSE_FAILURE_RATE_EXCEEDED`: more than 5% of at least 100 sources a caselist tried could not be
  read. Look at them before anything else:

  ```bash
  DEBATE_ENV=dev debate-research caselist parse --caselist hsld26 --failures
  ```

  That listing names schools and teams, so it stays in the terminal. What parsed is in the store
  and, where the run publishes, in the bucket.
* `STORE_UNAVAILABLE`, or `STORE_ACCESS_DENIED` with a `hint`: the bucket did not take the parsed
  store. After the fix the hint names, if there is one, publish it as above with
  `caselist parse --caselist <slug> --publish`, or leave it to the next run that imports into that
  caselist.
* `CHECKSUM_MISMATCH`: the bucket holds a file of the parsed store with other bytes, which the
  same parser never produces twice. It needs a person; nothing was overwritten.
* `INTERNAL_ERROR`: the parse crashed. Run `caselist parse --caselist <slug>` by hand to see it,
  and report it.

Running `caselist pull` again does not retry a parse stage: a pull that imports nothing parses
nothing.

**`report: failed` with a `hint`, and exit `0`.** Everything was published, and the comparison that
confirms it was refused. Nothing is lost and nothing waits for a login, but nothing leaves the inbox
until a run can confirm it. Make the fix the hint names; the next run confirms and clears the inbox.

**The run stopped with `STORE_ACCESS_DENIED` before fetching anything.** This Mac refused the
manifest folder, or one manifest file in it (`v1-e34-t19`), so the run could not tell which weeks
it already holds. It stops there rather than take every listed week for new and fetch them all
again, which is what an unreadable folder used to cause. Fix the permission on the data directory
and run the command again. The banner is `caselist pull failed: will be retried`, with the same
fix in its body.

**The banner says `needs a person`, and the run `stopped with StoreProfileNotConfigured`.** The
profile setting names an AWS profile this Mac's AWS config does not define, so the run was refused
before it fetched anything. Nothing is lost and nothing was spent. The run is in `caselist runs`
as `failed`, and its record waits to be published. Correct the setting or add the profile, confirm
it with `debate-research doctor --evidence-profiles`, and publish the record with
`debate-research caselist pull --publish-pending`, or leave it to next week's run:
[A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define) has each
step. `aws sso login` does not fix it.

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
imported out of order. With exit `3` nothing needs doing: the next scheduled run fetches the missing week and
imports it and everything behind it, oldest first, and it does not fetch again anything already
in the inbox — each fetch spends one of the five. With exit `1` the download stage's reason says
what will be the same next week (see [What the exit code says](#what-the-exit-code-says)).

**An import failed** (`import: failed`, with the archive and the reason in its detail). The archive
stays in the inbox, and the next run imports it from there without downloading it again, then the
newer weeks of that caselist that waited behind it. What the operator has to do is remove the
cause the reason names — an archive over `caselist.max_archive_bytes`, a caselist slug this build
does not know the event of, an unreadable zip — because a run meets the same archive again and,
with the cause still there, fails the same way. An unreadable zip is the one case to delete by
hand: remove it from the inbox, and the next run downloads it again. If the reason says the file in
the inbox *could not be read (PermissionError)*, the zip may be whole and this user cannot open
it: fix its permission instead, and the next run imports it from the inbox without a download.
One archive that cannot be read no longer stops the run (`v1-e34-t19`): the other caselists' weeks,
the camp files and the complete archive are imported, and the same caselist's newer weeks wait
behind it as behind any failed import. A camp download is named in the
reason by its id, `openev-777 (sha256 2b912c191a8a)`; its file in the inbox is the one whose name
starts `openev-777-`.

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
removed on another machine too, since the bucket's copy of the list is read. It covers a copy
already in the inbox as well (`v1-e34-t14`): a new id downloaded before this machine knew of the
removal, whose import never ran, is held rather than imported from there. The select stage names it
by id and digest, `openev-640 (sha256 1f2e3d4c5b6a)`, never by its title. A held copy stays in the
inbox untouched; retention keeps it as `not_imported` (no manifest came from its bytes), and
`caselist remove` leaves it alone, since the list names none of its bytes. Nothing needs doing.
After `caselist unsuppress` of the old file, the next run fetches the new id, or imports the copy
already in the inbox without downloading it. If the data-use policy is ever read the other way, this
becomes a download; until then, fetching such a file by hand through `caselist import-openev` is a
decision to record in the register.

**A camp file shows `suppression_list_unreadable`.** The run could not read the suppression list:
the bucket refused its copy (a missing grant, `access denied`) or a copy has a line nobody can read.
It did not fetch any camp file it may have been told to remove, nor import a copy of one already in
the inbox whose path a removal may cover, and the import stage fails for the same reason. Fix what the import stage's reason names; the next run decides it. An expired SSO
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

**An agent installed before `v1-e34-t17`** runs the build it was installed with, which has no
parse stage. After a reinstall with a build that has it, the first scheduled run parses what it
imports. [`caselist-sync-runs.md`](../data/caselist-sync-runs.md) is where that run's duration and
its `parse` counts are recorded, beside the terminal figures above.

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
