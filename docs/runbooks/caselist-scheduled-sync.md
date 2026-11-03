<!-- docs-index: Installing, enabling, watching and disabling the weekly `caselist pull` launchd agent -->
# Runbook: the weekly caselist sync

How the weekly OpenCaselist pull is installed, enabled, watched and turned off on the operator's
Mac. The command it runs is `debate-research caselist pull` (`v1-e34-t02-scheduled-sync`); the
schedule around it is `ops/launchd/`.

**From the cutover (`v1-e40-t06`), the weekly run is the cloud's**, in the team's AWS account
([ADR-0020](../adr/0020-weekly-caselist-run-in-the-cloud.md)). The Mac's agent is unloaded and its
plist kept, so that a week the cloud run is down can be run on the Mac by hand. Which machine runs
the week, and how to fall back to the Mac, is [caselist-cutover.md](caselist-cutover.md)'s. This
runbook stays the reference for the Mac's agent, its checks and what a run reports. Two things
changed with the cutover: the agent passes no `--caselist`, because the caselists are the build's
`caselist.sync_caselists`, and every dev build keeps the run's state in the bucket
(`caselist.run_state = "bucket"`), so a pull on the Mac takes the bucket's run lock and restores its
working copy first.

| | |
|---|---|
| Runs on | Charlie's Mac, as Charlie, under launchd |
| Cadence | **Weekly.** Wednesday 06:00 local by default |
| Command | `debate-research caselist pull`, following the build's `caselist.sync_caselists` (until `v1-e40-t06`, `--caselist <slug> …`) |
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
config and asks AWS one question for each profile that is defined: who it is signed in as. A build
from `v1-e05-t08` on also adds a `Model profile` row for `models.aws_profile`, the profile model calls
are signed with. That row never changes the exit code, and the weekly pull needs no model; setting
the profile up is [bedrock-access.md](bedrock-access.md). What an evidence row says:

| The row says | Means | Exit |
|---|---|---|
| `debate-prod-evidence (storage.s3.aws_profile): defined, and signed in as DebateProdEvidenceOperator` | The profile is in this Mac's AWS config and its session is live. The name is the permission set's: `DebateProdEvidenceOperator` for prod's everyday profile, `DebateDevEvidenceOperator` for dev's | `0` |
| `… defined; its session has expired or was never started, so AWS cannot be asked which permission set it is (aws sso login --profile debate-prod-evidence)` | The profile is defined. Run the login it gives to see the permission set. This does not fail the check: a run without a session still captures and imports | `0` |
| `… defined; AWS did not answer when asked which permission set it is signed in as` | No verdict on the profile. The question waits 10 seconds for each profile and then gives up (`v1-e29-t09`), so an offline Mac adds at most that to the check, to `install.sh` and to `--check-launchd`. Run it again when the Mac is online | `0` |
| `… not defined in this machine's AWS config` | The setting names a profile this Mac does not have. The command fails with `STORE_PROFILE_NOT_CONFIGURED`, naming the profile and the setting, and a scheduled run would be refused before it starts. See [A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define) | `1` |
| `Evidence profiles: none configured for this environment` | The environment names no bucket, as `test` does | `0` |

A profile signed in as something unexpected is said in the same row and does not fail the check.
The takedown profile is compared with the permission set a takedown runs as: one signed in as
anything else reads `… a takedown runs only as DebateProdEvidenceRemoval, so caselist remove
--execute will refuse this profile`. Signed in as the other environment's set, it says whose set
that is first, as the everyday profile's row does: `… DebateDevEvidenceRemoval, which is dev's
takedown permission set and not prod's; a takedown runs only as DebateProdEvidenceRemoval, …`
(`v1-e34-t25`). The everyday profile signed in as the other environment's
permission set reads `… DebateDevEvidenceOperator, which is dev's permission set and not prod's:
prod's bucket grants it nothing, so every command that reaches the bucket will be refused`
(`v1-e29-t09`): the profile's block in the AWS config names the other environment's
`sso_role_name`, most likely copied from it. The row names a profile, the setting that holds its
name and a permission set, and never an account, a role's full identifier or where the AWS config
is.

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
it imported nothing ([The parse stage](#the-parse-stage)). `search_index: completed` means the run
built or published the search pilot's index, and `search_index: skipped` that nothing had changed
([The search index stage](#the-search-index-stage)). `landscape: skipped` is expected until
E32 ships. These stages are optional by design and cannot fail a run whose bytes are already
captured: a failed parse or search index stage is reported and the exit code stays `0`.

Record the counts in [`docs/data/caselist-sync-runs.md`](../data/caselist-sync-runs.md).

## Step 2 — install the agent

```bash
ops/launchd/install.sh --env dev --debate-research "$HOME/.local/bin/debate-research" --dry-run
```

`--dry-run` prints the plist and writes nothing; read it before you install it. Then:

```bash
ops/launchd/install.sh --env dev --debate-research "$HOME/.local/bin/debate-research"
```

That writes `~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist`, copies the
wrapper out of the checkout, creates the log directory and lints the plist with `plutil`. **It
starts nothing**, and `RunAtLoad` is false, so even loading the agent does not trigger a pull.

Before it writes anything, the dry run included, the installer asks the build where the agent's
data will be and runs `debate-research doctor --evidence-profiles` as the agent will run it, with
the plist's `HOME`, `PATH` and `DEBATE_ENV` and nothing of your shell's (`v1-e34-t24`). If that
fails it prints what the build said and installs nothing. The usual reason is a profile this Mac's
AWS config does not define ([A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define)).
A build older than that check is refused too, by name. An expired session does not fail it.

The caselists the agent's pull follows are the build's setting `caselist.sync_caselists`, in the
environment's profile (ADR-0020 (5), `v1-e40-t06`), which the installer also asks the build for. It
says which they are, `The agent's pull follows the build's caselist.sync_caselists: …`, and installs
nothing for a build that names none, whose agent would be refused every week. There is no
`--caselist`: a new season's caselists are a profile change and a new build.

The AWS profile the run uses is the build's setting `storage.s3.aws_profile`: `debate-prod-evidence`
for prod and `debate-dev-evidence` for dev. The installer has no option for it. Its old
`--aws-profile` wrote `AWS_PROFILE` into the plist, which nothing the agent runs reads, so it chose
nothing.

To install over an agent that is already installed, use
[Reinstalling the agent](#reinstalling-the-agent): the installer then keeps the installed agent's
environment, schedule, log directory and wrapper directory unless told otherwise.

`--weekday`, `--hour` and `--minute` set the schedule. A first install defaults to Wednesday 06:00,
the day after the site publishes the week's archives; over an installed agent, each one left out
keeps what the agent has (`v1-e34-t25`).

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
`debate-research doctor --evidence-profiles --search-index` (`v1-e34-t22`, `v1-e34-t30`), and
nothing else: no `caselist pull`, no listing call to OpenCaselist, no download. The store check
reads the build's own `caselist.sync_caselists`, as the agent's pull does. An agent installed before
`v1-e40-t06` names its caselists as `--caselist` arguments instead; those reach the store check as
`DEBATE_CASELIST__SYNC_CASELISTS` in the check's environment, because `--check` takes no argument,
and the agent's own plist is not changed. The installer kickstarts it, waits for it, prints
its log (`~/Library/Logs/debate-research/caselist-sync-check.log`) and exit code, and boots it out.
It reads the agent's `runs` count before and after and fails if it changed. It refuses to run
against an agent whose wrapper is not this checkout's copied out, so reinstall first. That
includes an agent installed before a change to `ops/launchd/run-caselist-sync.sh` reached this
checkout, such as `v1-e34-t27`'s: until the reinstall, the check says `the installed agent's
wrapper … is not this checkout's …; reinstall with this script first`.

It takes no option but `--label`, which names the agent to check. It checks the installed agent
as its plist stands, so any other option would be ignored, and is refused instead, by name, with
nothing checked (`v1-e34-t27`). Before that, `--check-launchd --weekday 4` checked the Wednesday
agent and said nothing about Thursday. To change a setting, reinstall with its option
([Reinstalling the agent](#reinstalling-the-agent)), then run the check on its own.

The log is `doctor`'s report as launchd runs the build: with the plist's `HOME`, `PATH` and
`DEBATE_ENV`, and nothing of a shell's. Its `Evidence profile` row is the one
[Checking the evidence profiles](#checking-the-evidence-profiles) describes, for the profile the
weekly run will use. Its `Search index store` rows name each store the run's search index stage
will index, and say whether the build has parsed it
([The search index stage](#the-search-index-stage)). Success is `exit code 0`, the version you
installed, that row saying `defined`, every store `parsed by` the build's parser version (or
`Search index stores: does not apply`), and the same `runs` before and after. A build installed
before `v1-e34-t30` answers with exit code `2`, and the check says it lacks the search index check.

| Exit code | Means |
|---|---|
| `0` | launchd ran the build, the build's own checks passed, and the profile is defined. A session that has expired is still `0`: the row says so, and gives the login |
| `1` | A check `doctor` makes failed. If the row says `not defined in this machine's AWS config`, the weekly run would be refused before it starts: see [A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define). An exit code of 1 is also what a Unicode database mismatch or an integration that does not import give ([Checking an installed build](#checking-an-installed-build)) |
| `2` | The installed build is older than the profile check and does not know the option. Install a newer build with `scripts/install_channel.sh`, then run the check again |
| `126` | The privacy-protection failure above |

## Reinstalling the agent

For a new build, a changed wrapper, or a changed schedule.

**The first build carrying `v1-e39-t12`** comes after its by-hand index build and publish, and
before the agent's next Wednesday run:
[The first index with the card-only rule](#the-first-index-with-the-card-only-rule-v1-e39-t12-once). Nothing here fetches anything, and
the two checks are the point of doing it in this order: the first finds a profile the AWS config
does not define before the agent is replaced, and the second finds it as launchd will meet it.

**The wrapper changed in `v1-e34-t27`.** It no longer exports `AWS_PROFILE`, which did nothing:
the plist sets none, and the run's profile is `storage.s3.aws_profile`. The agent's own runs are
unaffected, but until the agent is reinstalled from a checkout with the change, `--check-launchd`
refuses it, saying `the installed agent's wrapper … is not this checkout's …; reinstall with this
script first`. These steps, with no option but the build in step 3, are the reinstall. They keep
the agent's schedule, Wednesday at 06:00 by default, and its other settings by themselves: no
`--weekday`, `--hour` or `--minute` is needed.

1. **Install the build**: `scripts/install_channel.sh` with the tag to install. It rehearses the
   install and refuses a build that fails its checks, leaving the one the agent runs untouched
   ([Checking an installed build](#checking-an-installed-build)).

2. **Check the evidence profile, as the agent will run.** The environment is read from the
   installed plist, not typed, and the sign-in uses it, so that the check can say which
   permission set the profile is:

   ```bash
   AGENT_PATH=$(plutil -extract EnvironmentVariables.PATH raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
   AGENT_ENV=$(plutil -extract EnvironmentVariables.DEBATE_ENV raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist)
   aws sso login --profile "debate-${AGENT_ENV}-evidence"
   env -i HOME="${HOME}" PATH="${AGENT_PATH}" DEBATE_ENV="${AGENT_ENV}" sh -c 'debate-research doctor --evidence-profiles; echo "doctor exit=$?"'
   ```

   Success is `doctor exit=0` and the row `Evidence profile` reading, for a prod agent,
   `debate-prod-evidence (storage.s3.aws_profile): defined, and signed in as
   DebateProdEvidenceOperator`, and for a dev agent the same with `debate-dev-evidence` and
   `DebateDevEvidenceOperator`. A session that
   has expired does not fail the check: the row says `expired` and gives the login, and the exit
   is still `0`. The installer makes the same check in step 3 and installs nothing if it fails;
   this step shows the row before anything is replaced, signed in.
   **Stop if it exits `1` with `STORE_PROFILE_NOT_CONFIGURED`**: the setting
   `storage.s3.aws_profile` names a profile this Mac's AWS config does not define, and the weekly
   run would be refused before it starts. Correct it as
   [A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define) says,
   then run the check again. An exit of `2`, "No such option", means the build installed in step
   1 is older than the check.

3. **Install the agent**, with no option but the build. Over an installed agent the installer
   reads the installed plist and keeps its environment (`v1-e34-t24`), and its schedule, its log
   directory and its wrapper directory (`v1-e34-t25`). The first three commands
   print them from the installed plist, so you can see what will be kept; the fourth is the
   install:

   ```bash
   plutil -extract EnvironmentVariables.DEBATE_ENV raw ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
   plutil -extract ProgramArguments json -o - ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
   plutil -extract StartCalendarInterval json -o - ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
   ops/launchd/install.sh --debate-research "$HOME/.local/bin/debate-research"
   ```

   It says what it kept, and which key of the plist it read each from, and each should be what the
   first three commands printed. For a dev agent on the default schedule:

   * `Keeping the installed agent's environment, dev, from its plist's DEBATE_ENV (--env changes it).`
   * `Keeping the installed agent's schedule, Wednesday at 06:00, from its plist's StartCalendarInterval (--weekday, --hour and --minute change it).`
   * `Keeping the installed agent's log directory, …/Library/Logs/debate-research, from its plist's StandardOutPath and StandardErrorPath (--log-dir changes it).`
   * `Keeping the installed agent's wrapper directory, …/.local/share/debate-research/launchd, from its plist's ProgramArguments (--wrapper-dir changes it).`
   * `The agent's pull follows the build's caselist.sync_caselists: hsld26 hspolicy26 hspf26.`

   Then it runs step 2's check itself and installs nothing if that fails. Success ends, as a first
   install does, with `Wrote …` and the data directory the agent keeps its data in, which should
   be the one it had. Adding `--dry-run` shows the same lines and writes nothing.

   * **There is no `--caselist`** (`v1-e40-t06`). The caselists are the build's, so a different
     list is a profile change and a new build. An agent installed before then has `--caselist`
     arguments in its plist; the reinstall drops them, `Not carried over from the installed plist:
     the arguments --caselist … after the wrapper.`, and says so again if the build names others.
   * **`--weekday`, `--hour`, `--minute`, `--log-dir` or `--wrapper-dir`** changes that setting
     alone, and the installer says from what to what. Before `v1-e34-t25` each went back to its
     default on a reinstall that did not repeat it, so an agent installed for Thursday moved to
     Wednesday 06:00. A wrapper directory changed leaves the old copy where it is.
   * **A setting the plist does not hold as the installer writes it**, such as a calendar
     interval edited by hand, is refused, naming the plist key and the option that sets it. It is
     never replaced by the default. Give the option to say what it is to be.
   * **`--env` with a different environment** is refused unless `--confirm-env-change` is given
     too, because it moves the agent to another data directory and another bucket. Before
     `v1-e34-t24` the default was `--env prod`, so a dev agent reinstalled without `--env` became
     a prod agent with an empty store, and only the data directory's name said so.
   * **A variable added to the plist by hand**, such as the parse stage's switch, is not carried
     over: `Not carried over from the installed plist: …` names each one. If dropping it would
     move the agent's data directory, the install is refused, naming both directories, unless
     `--confirm-env-change` is given.
   * **An agent installed before `v1-e34-t24`** has `AWS_PROFILE` in its plist. The reinstall
     drops it, and says that nothing reads it.

4. **Reload it.** launchd keeps the plist it loaded:

   ```bash
   launchctl bootout gui/$UID/com.debate-intelligence.caselist-sync
   launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.debate-intelligence.caselist-sync.plist
   launchctl print gui/$UID/com.debate-intelligence.caselist-sync
   ```

   If `bootstrap` says `Bootstrap failed: 5: Input/output error`, the bootout had not finished;
   run the bootstrap line again. `print` should show the copied wrapper as the only program
   argument, the calendar interval, and `runs = 0`.

5. **Check it under launchd:**

   ```bash
   ops/launchd/install.sh --check-launchd
   ```

   Success is `exit code 0`, the version installed in step 1, the same `Evidence profile` row as
   in step 2, and the same `runs` before and after
   ([Step 3](#step-3--enable-it) has the table of exit codes). This is the check that counts: it
   is launchd's environment, not a shell's, reading the AWS config launchd's `HOME` leads to.
   Run it as it is written: it takes no option but `--label`, and refuses any other by name.

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
([Reading what it did](#reading-what-it-did)). After the outcome, `Failed on` is the codes the
run's exit code was decided from and `Verdict` is `retry` when every one is a failure a later run
may not meet (exit `3`) and `person` otherwise, the same rule as the banner's
([What the exit code says](#what-the-exit-code-says), `v1-e34-t23`). Both say `none` for a run that
did not fail, and `not recorded` for a run a build before `v1-e34-t19` recorded. In `--json` the
verdict is `verdict`.

Two banners have words of their own beside the verdict, and `Verdict` shows them after it in
brackets (`v1-e34-t26`): `person (skipped)` for a run another held the lock against, and
`retry (retry once fixed)` for a refusal the next run gets past only once its fix is made. In
`--json` they are `banner`, `skipped` or `retry once fixed`, and `null` for every other run and
for a run with no details.

**A quiet week can hide a torn manifest.** A week that imports and publishes nothing reads no
manifest rows, so a torn line in one is found only when something reads them. When the runs report
nothing for a while, run `caselist status` for each caselist: it reads every manifest, and exits 1
on one it cannot read (`v1-e34-t23`).

```bash
DEBATE_ENV=dev debate-research caselist status --caselist hsld26
```

**The 06:00 run and the AWS session.** An SSO session lasts hours, not a week, so the Wednesday
06:00 run usually finds it expired. That is not a failure: the run downloads and imports
everything, records the publish as `pending` (outcome `publish_pending`), and the next run, or this,
publishes it. A run whose publish finished and whose report stage then lost the session while it
compared is `publish_pending` too, since `v1-e34-t28`: the check waits for the same login, and the
next run, or `--publish-pending`, makes it ([What waits for the login](#what-a-notification-says)). Before, that
run was `completed`. Every installed build reads the value. The first scheduled run, on 2026-10-14, did exactly that
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
| The run's **details** | `<data_dir>/caselist-sync-run-details.jsonl` | `reports/sync-run-details/<yyyy>/<run-id>.json` | Each failed stage's `error_codes` and `hint`, a pending stage's `earlier_findings`, the report stage's `drift` (each snapshot found out of sync, with what differs), the codes the exit code was decided from, the parse stage's nine counts, `held_by_request`, the uploads a removal's hold refused (`v1-e34-t23`), the report stage's `not_compared`, what a check cut short by an expired session did not reach, by caselist and snapshot, and `manifests_published`, how many of the objects published were manifests (`v1-e34-t28`) |

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
| `objects_published` | What reached the bucket from the raw store: sources and manifests. A build before `v1-e34-t28` counted the sources alone, so a republish of a manifest alone said `0 object(s) uploaded`; the publish stage's reason now says how many of each, `1 object(s) uploaded across 1 snapshot(s): 0 source(s) and 1 manifest(s)` |
| `manifests_published` | Of those, the manifests (`v1-e34-t28`). Also in the run's details |
| `parse` | The parse stage's counts and nothing else: `caselists`, `full_parses`, `attempted`, `skipped`, `unsupported`, `failed`, `cards`, `uploaded`, `not_published`. `null` when the stage parsed nothing. See [The parse stage](#the-parse-stage) |
| `pending_publish` | What [the pending-work file](#the-pending-work-file) holds after the run: every snapshot this Mac has imported that the bucket had not confirmed complete when the publish stage ended, and any the report stage then owed again because the bucket's manifest drifted (`v1-e34-t26`). Whether that waits for a login or for something else is the `publish` stage's outcome, not this list |
| `inbox_retention` | What left the inbox and the bytes freed, and what stayed and why. See [The download inbox](#the-download-inbox) |
| `full_archive` | What the complete-archive rotation decided and why (`reason`), what the weeklies left of the day's allowance, and for a complete archive imported, its `bytes` and its `withdrawn` and `superseded` counts. See [The complete archive](#the-complete-archive) |
| `openev_selections[]` | Each camp file OpenEv listed: its `openev_id`, the run's `decision`, and `inbox_file`, the first twelve hex digits of the download's sha256 once the run had its bytes (the name `inbox_retention` gives the same file) |
| `stages[]` | One entry per stage, each with the sentence saying why it ended that way (`reason`). A failed stage also carries `error_codes`, the code of each failure behind it, and, when a store refused it, `hint`, the fix that applies (`v1-e34-t13`). A `pending` stage carries `earlier_findings`, the codes of what it had already found when the session expired (`v1-e34-t19`); they never change the exit code. The report stage's `drift` names each snapshot it found out of sync, failed or before an expiry, with its `kinds`: `manifest`, `source`, `missing`, `suppressed_rows` (`v1-e34-t23`). A `pending` report stage's `not_compared` names what it had not compared when the session expired, for the next pull or `--publish-pending` to compare (`v1-e34-t28`). See [What the exit code says](#what-the-exit-code-says) |
| `held_by_request` | Uploads the imports refused because a removal holds their path, by the removal's request id (`v1-e34-t23`). `{}` when none was |
| `run_record`, `run_details` | What the run log keeps of this run, and what is kept beside it. See [The record, and the details beside it](#the-record-and-the-details-beside-it) |
| `schema_version` | `5` since `v1-e34-t17`, which replaced `cards_parsed` and `parse_failures` (always `0`; no stage filled them) with `parse`. `4` since `v1-e34-t13`, which added `error_codes` and `hint` to every stage; a summary written before that says `3` and has neither. `v1-e34-t19` added `earlier_findings` to every stage and left the version at `5`, because nothing is decided from it. Nothing reads a summary back; `caselist runs` reads the run log, which builds of every kind read and write alike |

Nothing in that object is a school, a team code, a debater's initials, a disclosure path, a camp
file's title or the `caselist_token` — the policy forbids all of them in a log, and the summary is
built to the same rule, so these logs can be pasted into an issue as they are. A camp download is
named by its OpenEv id, `openev-777`, with `(sha256 2b912c191a8a)` once the run has its bytes, and
never by its file name, which is its title (`v1-e34-t12`). Summaries and logs written before that
change may still name camp files, so check older ones before pasting them. A failed stage's reason,
codes and hint name no path on this Mac either: a folder the operating system refused is named by
what it is for, and the data directory and the inbox by those names (`v1-e34-t13`). Nor does any
other output of a pull, by hand or from the agent, with `--json` or without, and `caselist runs` in
both forms: a dry run plans its downloads `into the inbox`, `summary_written_to` is the summary
file's path inside the data directory (`caselist-sync-runs/<run id>.json`), and a run refused
because another holds the lock names `caselist-sync.lock in the data directory` (`v1-e34-t16`). A
summary or envelope written before that change may hold the data directory's path in one of those
three places, so check older ones before pasting them. A run that ended
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
records its codes all the same, in its own `error_codes`: `PARSE_FAILURE_RATE_EXCEEDED`,
`NEWER_FINGERPRINT_TABLE`, the codes above for a store that did not answer or refused, the code of
each object of the parsed store the bucket did not confirm, and `INTERNAL_ERROR` for a parse that
crashed.
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
  stopped by an expired `caselist_token` has always had, and nothing is added to it. Its
  `error_message` keeps the runbook the sentence points at, `docs/runbooks/evidence-store.md`; a
  build before `v1-e34-t23` wrote `[redacted]` in its place.
* **Its details beside it.** One line in `<data_dir>/caselist-sync-run-details.jsonl` with
  `failure_codes` of `STORE_PROFILE_NOT_CONFIGURED` and the fix as `hint`, which names the setting.
* **One banner**, titled `caselist pull failed: needs a person`:

  > Run 20261014T100000Z (prod) stopped: the AWS profile it publishes with is not one this
  > machine's AWS config defines. A person should look: at least one failure here will be the same
  > on the next scheduled run. The bucket was never reached: set storage.s3.aws_profile to a
  > profile this machine's AWS config defines, or add the profile to it:
  > docs/runbooks/evidence-store.md lists the evidence profiles and how they are added. It is not
  > an expired session, and logging in changes nothing.

  Until `v1-e34-t23` it said `stopped with StoreProfileNotConfigured`, the error's class.

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
override misspells it. The installer never writes that override: one in the plist was added by
hand, and a reinstall drops it and says so. Then confirm it, as the agent runs:

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

Each banner has a title, the run and its environment under it (`Run 20261014T100000Z (prod)`), and
a body that starts with the command to run, once any fix is made: `Fix: <command> — `, then the
sentence and the fix. A failed run's title is its verdict, so it can be read without opening the
banner (`v1-e34-t19`). The verdict is the exit code said in words, decided by the same rule.

**What the banner shows of it** (`v1-e34-t23`). On this Mac a banner shows the title, about forty
characters of the line under it, and about ten lines of about forty-five characters of the body;
the rest is shown when the notification is opened. Until `v1-e34-t23` the command was the line
under the title and the end of the body, and the banner cut it in both (seen 2026-10-15). It is
now the first thing in the body, so it is shown whole, and the line under the title is short
enough to be shown whole too.

| Title | When | Exit |
|---|---|---|
| `caselist pull failed: will be retried` | A download, an import or a publish failed, or the run stopped on an error, and every failure is one a later run may not meet | `3` |
| `caselist pull failed: retried once fixed` | The same, and the failure carries a fix to make first: a refusal by this Mac or by the bucket (`v1-e34-t23`) | `3` |
| `caselist pull failed: needs a person` | The same, and at least one failure will be the same next week. Also a run that stopped on a bug | `1`, `70` |
| `caselist pull skipped: another was running` | Another `caselist pull` held the run lock, so this one did nothing (`v1-e34-t23`) | `1` |
| `caselist pull skipped: the weekly run moved to prod` | The weekly run's home has moved to prod, so dev's run lock is held for good and this pull did nothing (`v1-e40-t29`) | `1` |
| `caselist pull finished with a failed stage` | Only a stage that did not have to finish failed: parse, report or retention | `0` |
| `caselist pull: publish a manifest again` | Only the report stage failed, and only because the bucket's copy of a manifest differs from this Mac's. The run owes it again, and the next run publishes it (`v1-e34-t23`, `v1-e34-t26`) | `0` |
| `caselist pull: a manifest drifted again` | The same, for a manifest a run had already owed again, published and seen confirmed, so it is not owed a third time (`v1-e34-t26`) | `0` |
| `caselist publish waiting for an AWS login` | The SSO session had expired | `0` |
| `caselist pull stopped: OpenCaselist login expired` | The `caselist_token` expired | `1` |
| `caselist pull: uploads held by a removal` | An import refused an upload at a path a removal holds (`v1-e34-t23`) | as the rest of the run |
| `caselist backlog growing` | The cap has deferred more archives for two runs in a row | `0` |

**The two wordings of a failed run.** The body names each failed stage with the codes it failed on,
and then says one of two things. When the next scheduled run should retry it:

> Run 20261014T100000Z (prod): the publish stage failed on STORE_UNAVAILABLE. The next scheduled run should retry it: every failure here is one a later run may not meet. What was captured is kept.

When a person should look:

> Run 20261014T100000Z (prod): the import stage failed on UNREADABLE_ARCHIVE. A person should look: at least one failure here will be the same on the next scheduled run. What was captured is kept.

A run that stopped on an error before any stage could record it says `stopped:` and what it
stopped on, in words, then the same sentence. A run refused because its AWS profile is not defined
is one of these, with the fix after it
([A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define)). No banner
names an exception's class (`v1-e34-t23`; before it, the banner named the class). A code with
no words of its own is named by its code, and `caselist runs` shows the class.

**The fix, when the stage has one.** A failed stage's `hint` follows the sentence, word for word as
the summary gives it. A failure the next run may get past, but only once its fix is made, has a
wording of its own (`v1-e34-t23`): a refusal exits `3`, like a store that did not answer, and next
week's run is refused again until the permission or the grant is fixed. So it does not say it will
be retried and stop there:

> Run 20261014T100000Z (prod): the publish stage failed on STORE_ACCESS_DENIED. The next scheduled run retries it, and is refused the same way until the fix that follows is made. What was captured is kept. This machine refused the blob directory: check that this user can read and write it, under the environment's data directory (storage.data_dir). It is a permission on this machine, not the AWS session.

The exit code is the same `3`, and so is the rule that decides it; only the words differ. A run
that stopped before any stage on a refusal with a fix says the same, after `stopped: this machine
or the bucket refused it.` The second wording can have a hint too, and keeps it.

**Another run held the lock.** A run started while another `caselist pull` is running, a pull by
hand while the agent's runs, say, does nothing and exits `1`. That is true by the rule, and a
person has nothing to do about it, so it has its own banner (`v1-e34-t23`):

> Run 20261014T100000Z (prod): Another caselist pull held the run lock, so this one did nothing. That run records and announces its own outcome.

Its command is `debate-research caselist runs`, which shows what the other run recorded once it
finishes. See [When something goes wrong](#when-something-goes-wrong) if no other run is going.

**The weekly run moved to prod.** Once the pilot's promotion has moved the weekly run's home
([caselist-cutover.md](caselist-cutover.md#the-dev-lock-held-for-good)), a dev `caselist pull` on this
Mac is refused with `RUN_HOME_MOVED`, does nothing and exits `1`. Nothing broke: the weekly run runs
from prod now, so the run is recorded as skipped and has its own banner (`v1-e40-t29`):

> Run 20261104T110005Z (dev) skipped: the weekly run now runs from prod, so this pull did nothing. Nothing here needs a person.

Its fix line is `none: prod's weekly cloud run records and announces its own runs`, and it names no
path: not the lock's key, and not the build that moved it. `caselist runs` shows the run as `skipped
(RUN_HOME_MOVED)`, failed on `none`, with the verdict `none (skipped)`. Its record still says `failed`
(`RunHomeMoved`), the record every installed build reads, so a build from before `v1-e40-t29` shows
`failed (RunHomeMoved)` for it, and gives a pull of its own the banner `caselist pull failed: needs a
person`. Every other refusal by the lock keeps its banner and its record.

**A manifest to publish again.** When the report stage's only finding is that the bucket's copy
of a snapshot's manifest differs from this Mac's, the run puts the snapshot back into
[the pending-work file](#the-pending-work-file), and the banner names the snapshots and says
nobody is needed (`v1-e34-t23`, after `v1-e30-t12`; owed again since `v1-e34-t26`):

> Run 20261014T100000Z (prod): the report stage found the bucket's manifest of hsld26 2026-10-13 differs from this machine's. The next scheduled run publishes it again: this machine rewrote the manifest after it was published, and the publish uploads this machine's copy. Nothing here needs a person.

Its command is `debate-research caselist pull --publish-pending`, which publishes it now; the next
scheduled run does it otherwise. Until `v1-e34-t26` nothing owed such a snapshot, and the command
was `caselist publish --caselist <slug>`. Any other kind of drift (a source, something missing,
suppressed rows), alone or beside a manifest mismatch, is owed nothing and keeps the banner
`caselist pull finished with a failed stage`. The report stage's reason names each snapshot with
what differs, and the run's details carry it as `drift`. In bucket mode (the cloud run), a raw source
the working copy lacks but the bucket holds at the manifest's digest is not "something missing": the
report stage, retention and `caselist status` count it present, and `caselist status` adds the line
`Raw sources held only in the bucket: N in <caselist> <snapshot>` (`v1-e40-t13`).

**A manifest that drifted again.** A snapshot is owed again for a drifted manifest once. If the run
that publishes it again sees the bucket confirm it, and the report stage then finds the manifest
differing again, publishing it a third time would not clear it: something keeps changing it. The
run does not owe it again, and says so, naming the snapshot by caselist and date (`v1-e34-t26`):

> Run 20261014T100000Z (prod): the bucket's manifest of hsld26 2026-10-13 differs from this machine's again, after a run published it again and the bucket confirmed it. Publishing it a third time would not clear it, so it is not owed again: a person should look.

Its command is `debate-research caselist status --caselist hsld26`, one for each caselist named,
which compares every snapshot of the caselist with the bucket. Look at what else writes to the
bucket's `manifests/` prefix, or rewrites the manifest on this Mac, before publishing it by hand.
The exit is still `0`: the report stage is not one the exit is decided from (`v1-e34-t13`).

**Uploads a removal's hold refused.** An import that refused an upload because a removal holds its
path says how many, by the removal's request id, and nothing else about it (`v1-e34-t23`, after
`v1-e30-t13`):

> Run 20261014T100000Z (prod): the import refused 1 upload(s) at a path a removal holds, by request: RM-2026-01 1. Nothing of them was stored.

Its command is `debate-research caselist status`, which says whether the same removal is owed
again. The count is also in the import stage's reason and in the run's details, as
`held_by_request`.

The hints are the ones [What the exit code says](#what-the-exit-code-says) describes: a folder
this Mac refused, a grant the profile lacks, and the pending-work file when it cannot be read.
None of them names a path: a folder is named by what it is for.

**A failed parse stage** gets neither wording, because the run exits `0` and the next scheduled run
does not retry a parse. Its command names each caselist whose parsed store the bucket did not take,
each with its own (`v1-e34-t31`):

* `debate-research caselist parse --caselist <slug> --publish-only` when the stage rebuilt that
  caselist from every copy of the suppression list and only the publish is owed. It rebuilds
  nothing.
* `debate-research caselist parse --caselist <slug> --publish`, which rebuilds first, for every
  other caselist: its aggregates may come from the run's own copy of the list alone, which is never
  published, or its rebuild did not finish.

Two caselists are two commands, separated by `;`. The banner carries the stage's own hint too,
which says the same, and names `debate-research caselist parse --caselist <slug> --failures` for a
failure rate over the threshold. A run that a build before `v1-e34-t31` recorded names
`--caselist <slug> --publish` for every caselist, because its details do not say which rebuild read
every copy. See [The parse stage](#the-parse-stage).

A bucket-mode run, the cloud run's, names neither (`v1-e40-t18`): its parsed store is the cloud
run's, and the next cloud run publishes it, whether or not it imports into the caselist
(`v1-e40-t08`). Never run either command on this Mac for it; see [caselist-cloud-run.md, "A failed parse stage"](caselist-cloud-run.md#a-failed-parse-stage).

**A login that will not be enough.** When the session expired after a snapshot had already ended
incomplete on something no later run cures, the login banner adds a sentence:

> Run 20261014T100000Z (prod) kept everything it fetched; 2 snapshot(s) and the run record wait to be published. A person should look as well: before the session expired a snapshot ended incomplete on CHECKSUM_MISMATCH, which the login will not fix.

Log in and drain as usual. The retry publishes the rest and reports that snapshot as a failed
publish; the stage's reason names it. A snapshot that ended incomplete on something a retry does
cure, a `503` say, adds no sentence: the drain publishes it.

The report stage keeps what it found the same way (`v1-e34-t23`). When the session expires while
it compares, a snapshot it had already found out of sync is kept as an earlier finding,
`CASELIST_DRIFT`, with its kind, and the banner says so. The drain does not find it again: it
compares what it publishes and what the check had not reached yet, and that snapshot was published
and compared. If the only finding was a
manifest that differs, it is owed again, and the banner says instead that the publish after the
login uploads this Mac's copy (`v1-e34-t26`); or, for one that drifted again, that a person should
look.

**What waits for the login** (`v1-e34-t26`). The banner counts the snapshots owed and names the run
record, which waits too. When nothing is owed it says so: a run whose only pending stage is the
report stage published everything and then lost its session while it compared, and its banner
used to say `0 snapshot(s) and the run record wait to be published`. It now says what waits:

> Run 20261014T100000Z (prod) kept everything it fetched; no snapshot waits to be published, only the run record. The report stage's check that the bucket holds what this run published was cut short; the next pull, or caselist pull --publish-pending after the login, makes it again.

**The next run makes the check again** (`v1-e34-t28`, the PM's ruling and condition of
2026-10-22). The run's details name what the report stage had not compared when the session
expired, as `not_compared` on the report stage. The next `caselist pull`, the scheduled one or one
by hand, and `caselist pull --publish-pending` each read them from the newest run's details, and the
report stage compares exactly those, after whatever that run publishes, with the same comparison
and the same rules: a manifest that differs and nothing else is owed again, anything else is a
failed report stage for a person. That run's select stage says how many it owes, and its report
stage's reason counts them among the snapshots confirmed. The same holds when the publish itself
waited for the login: what it confirmed before the session expired is compared by the next run too.
A run whose session has expired again is cut short again, and owes what it did not reach, so the
check waits until a run has a session. A dry run compares nothing.

Only the newest run's list counts, and the next run is always handed it. A run the lock refused,
or one that stopped before any stage, is passed over. A run recorded by a build from before `v1-e34-t28` has no list,
and owes no check: its banner said so, and named `caselist status`. The list is in the details and
nowhere else: not in the record, which no build may change, and not in
[the pending-work file](#the-pending-work-file), which holds publishes.

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

* **Which caselists.** First each caselist a parse is owed for (`v1-e40-t08`), in the order owed,
  then each caselist a weekly archive or a camp file was imported into, once. Camp files are the
  caselist `openev`. A complete archive names none, because its sources are not parsed. A run that
  imported nothing and owes nothing parses nothing and rebuilds nothing.
* **What is owed.** A publish that the bucket confirms owes a parse of each snapshot it published,
  written to `caselist-sync-parse-owed.json` in the data directory before the pending-work file lets
  the snapshot go. A caselist whose parsed store has no directory of the build's parser version
  owes a full parse, `openev` included, whether or not anything was imported into it. An entry is
  cleared only when its caselist's parsed store is published complete, so a run killed after its
  publish, or one whose parsed-store publish failed, leaves the parse to the next run, which makes
  it even when it imports nothing. A removal that reaches a snapshot clears its entry: the rebuild
  that follows a removal parses the caselist. `caselist runs` and `caselist status` end with what is
  owed, and `--json` gives it as `parses_owed`.
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
line, and says so: `Not carried over from the installed plist:
DEBATE_CASELIST__PARSE_IMPORTED_SOURCES, which this script does not write.` `parse_imported_sources = false` under `[caselist]` in a profile does the same for a build
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
new version directory, which holds nothing. Since `v1-e40-t08` the first scheduled run after such a
release parses **every caselist it follows in full, `openev` included**, whether or not it imports
anything into them, and before its search index stage, so the index it builds is of the new version.
Its parse stage's reason says `parsed in full, as the parsed store held no directory of parser
version <version>`, and `full_parses` counts them. That run takes about 40 minutes longer than a
usual Wednesday's: the 2026-10-11 full parse under `2026.10.10-docx-2` took 1,465 s on this Mac for
11,126 sources, and hspolicy26 alone took 981 s for 4,342 sources on 2026-10-30.

Each caselist owed a full parse is written down before its parse starts, in the data directory's
`caselist-sync-parse-owed.json`, and cleared once its parsed store is published complete. A run
stopped part-way, by the Mac sleeping or by hand, leaves the caselists it did not finish owed, and
the next run parses them first. `caselist runs` and `caselist status` end with what is owed.

Doing the full parse by hand before the agent meets the new build is no longer needed. It is still
allowed, on a day other than Wednesday morning or with the agent booted out first
([Disabling it](#disabling-it)), if the Wednesday run must stay short:

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev debate-research caselist parse --caselist hsld26 --publish
DEBATE_ENV=dev debate-research caselist parse --caselist hspf26 --publish
DEBATE_ENV=dev debate-research caselist parse --caselist hspolicy26 --publish
DEBATE_ENV=dev debate-research caselist parse --caselist openev --publish
```

A full parse owed stays written down after a parse by hand: the next run finds the new version's
directory, parses nothing again, publishes nothing it lacks, and clears it.

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
login, either leave it, because the next run with a session publishes the whole directory, whether
or not it imports into the caselist (`v1-e40-t08`), or publish it now:

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev debate-research caselist pull --publish-pending
DEBATE_ENV=dev debate-research caselist parse --caselist hsld26 --publish
```

The last line parses nothing that is parsed, rebuilds the aggregates and uploads what the bucket
lacks, so it takes about as long as that caselist's rebuild in the table above. In prod it needs
`--confirm-prod`. However many weeks were missed, one run per caselist catches up.

The stage's reason names the command for each caselist (`v1-e34-t31`). It is `--publish`, the last
line above, when the stage rebuilt that caselist while the bucket's copy of the suppression list
needed the login, which is the usual case after an expired session: those aggregates came from this
Mac's copy of the list alone, and are rebuilt before anything is published. When the session expired
only during the parsed store's own publish, after a rebuild that read every copy, the reason names
`--publish-only` for that caselist instead: run it in place of the last line, with the same caselist,
environment and `--confirm-prod` in prod. It publishes the directory as the run left it and rebuilds
nothing. Run whichever the reason names; `--publish` is never wrong, only slower.

## The search index stage

After the parse stage, a run keeps the student search pilot's index current (`v1-e39-t09`). The
index is `tub index build`'s, from the parsed store on this Mac, for the run's caselists plus
`openev`, and its publish is `tub index publish`'s: the gzip object, then the manifest, each checked
by sha256 as it lands, and `current.json` last
([`docs/runbooks/evidence-search.md`](evidence-search.md) runs the site that reads it). The stage
runs whether or not the run imported anything, and is wired in only where the environment names a
bucket. In order:

1. **With an AWS session, the suppression list's two copies are reconciled**, so that a removal
   recorded in the bucket's copy reaches this Mac's, which is the one the build reads. Without a
   session, or with a bucket that does not answer, the build reads this Mac's copy alone, and the
   stage's reason and the summary's `suppression_list_local_copy_only` say so.
2. **The digests are compared**: each store's `occurrences_sha256` and the suppression list's
   `sha256`, with those in the manifest of the newest index under `~/.debate-research/dev/tub-index`.
3. **It builds only when they differ**, or when the newest index was built by another parser or
   fingerprint version. Otherwise it keeps the newest index and says `unchanged since <index id>`.
4. **With a session, it publishes that index when `current.json` names another one.** It publishes to
   the agent's own environment, dev. Prod is yours, below, until an agent runs against prod.

What each outcome means:

| Stage row | What happened | What to do |
|---|---|---|
| `skipped`, `unchanged since <id>, which current.json names` | Nothing changed. | Nothing. |
| `completed`, `built <id>` … `published` | A new index is live in dev. | Nothing; publish it to prod when you want prod to have it. |
| `pending`, `built, publish pending` | Built with no AWS login; dev still serves the previous index. | Nothing: the next run with a session publishes it without rebuilding. Or publish it now, below. |
| `skipped`, `the parsed store is not this build's version` | The parsed store was parsed by another parser or fingerprint version than the agent's build, for example after a by-hand re-parse with a newer build. | The reason names both versions. A newer store: reinstall the agent with the build that parsed it ([Reinstalling the agent](#reinstalling-the-agent)). An older one: re-parse it with the agent's build ([After a release that bumps the parser version](#after-a-release-that-bumps-the-parser-version)). |
| `skipped`, `the parse stage failed in this run` | An index of what a failed parse left is not built. | See [The parse stage](#the-parse-stage). |
| `failed` | The build or an upload failed. The previous index is still on this Mac and `current.json` still names the previous index; the reason names both. | The stage's hint and the notification say what to fix. The next run tries again. |
| `failed`, `would shrink the published search index: <store> has N documents against M in index <id>` (`SEARCH_INDEX_WOULD_SHRINK`) | The new index holds under 90% of a store's documents in the published one, or none. Nothing was uploaded; `current.json` and both local indexes stay. | Read [The shrink guard](#the-shrink-guard). The run never publishes past it, and refuses again every week until the store is restored or you publish the shrink by hand. |
| `failed`, `whose aggregates hold no occurrence rows` (`SEARCH_INDEX_STORE_EMPTY`), or the build's `occurrence table holds no rows` (`SEARCH_INDEX_STORE_NOT_READY`) | A store's parsed aggregates are empty, as after a whole-file removal that was not followed by its rebuild. | Rebuild that store's aggregates ([the removal runbook's P1b](caselist-removal.md#p1b--right-after-done-rebuild-the-parsed-stores-aggregates)). Never overridden. |
| `failed`, `cannot be compared with the current index's` (`CURRENT_SEARCH_INDEX_UNREADABLE`) | `current.json` or the manifest it names cannot be read, so the guard has nothing to compare with. | Find out why first (the evidence-search runbook's app log table); then publish by hand with `--allow-shrink`, below. |

**A rule this replaced** (PM ruling 2026-10-22, `v1-e39-t14`). Until then, the stage treated a
`current.json` it could not read as behind, and published over it. It now fails on one, the last
row above, because with nothing to compare the guard cannot tell what the publish would replace,
and the old rule let an agent running an older build overwrite a pointer a newer build wrote.
| `failed`, `no version directory of parser …; run debate-research caselist parse --caselist <slug>` | A store the run indexes has never been parsed by the agent's build: on a fresh installation, every store until its first parse. | Run the `caselist parse` it names. Before the first Wednesday, `doctor --search-index` finds every such store at once (below). |

**Before the first Wednesday, check that every store is parsed.** The stage indexes the agent's
caselists and `openev`, each from the agent's build's parser version, and a store with no version
directory of it leaves the run without a current index (`v1-e39-t09`, PM ruling Q3). `doctor
--search-index` (`v1-e34-t30`) names each such store with the command that parses it and exits `1`;
it exits `0` when every store is parsed, and says `does not apply` when the run has no stage
(`caselist.refresh_search_index` off, or no bucket). `ops/launchd/install.sh --check-launchd` runs
it as the agent will, with the agent's caselists ([Step 3](#step-3--enable-it)). By hand, the
caselists are `caselist.sync_caselists`, the ones a pull without `--caselist` follows:

```bash
DEBATE_ENV=dev DEBATE_CASELIST__SYNC_CASELISTS='["hsld26","hspolicy26"]' debate-research doctor --search-index
```

A store parsed only by another parser version counts as not parsed: the run skips the stage on it
rather than failing, but builds no index either.

Every build's summary reports the SQLite file's size and its bytes per document (`search_index` in
the run summary, and in the reason). An index directory is about a gigabyte, so after a successful
build the stage removes superseded ones from this Mac and says how many and the bytes freed
(`removed`, `bytes_freed`). It never removes the two newest, the one `current.json` named when the
run read it, a directory without a readable manifest, or a dot-directory, and a run that built
nothing removes nothing. The copies in the bucket are not touched. A warning in the reason means the index has passed one of
ADR-0019's lines: 1,700,000,000 SQLite bytes, where a swap's two copies fill 79% of the function's
4,096 MB of temporary storage (moved from 900,000,000 by the PM's ruling of 2026-10-22,
`v1-e39-t14`), or 400,000,000 gzip bytes, at which `v1-e39-t04` asks for a higher bandwidth quota.
Bring either to the PM.

**Each run's growth** (`v1-e39-t14`): when `current.json` named another index, the reason ends with
`growth against <id>: +N documents, +B SQLite bytes, +G gzip bytes`, and the run summary's
`search_index` has `previous_index_id`, `documents_growth`, `sqlite_bytes_growth` and
`gzip_bytes_growth`, negative for a shrink. A run that kept the index `current.json` already names
records none. `jq '.search_index'` over the week's summaries gives the series for ADR-0019's sizing.

**What a build left out as no card** (`v1-e39-t12`): a run that built adds `N left out as no card (A
cite only, B with no cite and under 25 words)` to the reason, and the summary's `search_index` has
`not_cards_by_store`, each store's `cite_only` and `no_cite_few_words`. A run that kept the newest
index records `null`: the count is the build's, not the manifest's. See
[The first index with the card-only rule](#the-first-index-with-the-card-only-rule-v1-e39-t12-once).

### The shrink guard

Since `v1-e39-t14`, `tub index publish` and this stage refuse, before uploading anything and with
`current.json` left as it was:

* an index built from a store whose aggregates hold no occurrence rows, even when nothing is
  published yet. Never overridden: rebuild that store's aggregates, or build without it;
* an index holding none of a store's documents that the published index holds, or fewer than
  `caselist.search_index_minimum_share_percent` of them (90 by default), per store, not just in
  total. A store the published index does not hold is not compared;
* any index, when `current.json` or the manifest it names cannot be read.

The refusal names the store, both counts and the index left current. Read them before anything
else. A real shrink is one you can account for: a removal (the dry run's cards for that store), the
card-only rule of `v1-e39-t12`, or a store you meant to drop. Anything else, such as a store
suddenly at 0, means the parsed store lost something: the guard has done its job, and the fix is
the store, not the publish. The 2026-10-22 rebuild that published empty aggregates to dev is the
case it was written for.

For a real shrink, publish the index the refusal named by hand, with one line saying why. Use the
removal's request id where there is one; never card text, a school, a team code or a file name. The
reason is printed, logged and in the `--json` result, and is not stored in the manifest or the
pointer, which the deployed function reads strictly. The refused publish was the plan; this block
is the publish:

**Operator command** (expected runtime seconds)
Where: a new terminal window on this Mac
```bash
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "data dir override: ${DEBATE_STORAGE__DATA_DIR:-none}"
if [[ -n "$PULL" || -n "${DEBATE_STORAGE__DATA_DIR:-}" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  env -u DEBATE_STORAGE__DATA_DIR DEBATE_ENV=dev debate-research tub index publish --env dev --newest --allow-shrink "RM-put-the-request-id-here, whole-file removal"
fi
```
Success looks like a line `published past the shrink guard with --allow-shrink: <store> has N
documents against M in index <id>; reason: ...` naming the counts the refusal named, then a table
whose last row is `reports/tub/search/current.json`. A refusal that says `aggregates hold no
occurrence rows` is the empty-store rule, which no reason passes. In prod, the same with
`debate-prod-evidence`, `DEBATE_ENV=prod`, `--env prod` and `--confirm-prod`, from the data
directory of [One data directory for each bucket](#one-data-directory-for-each-bucket).

### The first index with the card-only rule (`v1-e39-t12`), once

From `v1-e39-t12` on, a build leaves out every entry that is no card: CITE_ONLY, or no cite and
fewer than 25 words of text ([the rule](../data/search-index.md#only-real-cards)). The index dev
serves was built without it. A weekly run that finds the stores unchanged keeps the newest index
whatever rule built it, since the manifest does not record the rule. So the first index with the
rule is built and published by hand, in two blocks, after `v1-e39-t12` merges into `dev`.

**Do this before the agent is reinstalled with a build carrying `v1-e39-t12`, and reinstall it
before its next Wednesday run.** Before: so that the first shrink is read by a person, store by
store, rather than met by an unattended run. Reinstall soon after: until it is reinstalled, the agent
runs its older build, and the first week the stores change it rebuilds without the rule and
publishes the non-cards back. Reinstall as [Reinstalling the agent](#reinstalling-the-agent) says.

The expected drop, from the counts over the dev index of 2026-10-22 (52,059 documents): 1,625
documents in all, at most 3.86% of a store (hsld26 511, hspf26 393, hspolicy26 634, openev 87). The
shrink guard refuses below 90%, so it should pass without `--allow-shrink`, and this runbook never
gives it one here.

The first block builds the index of the stores the published index holds and compares it, store by
store, with that index. It changes nothing in the bucket. It writes one index directory under
`~/.debate-research/dev/tub-index`, which becomes the newest there.

**Operator command** (expected runtime about 5 minutes: a full build, which reads every
representative's source twice)
Where: your Mac, at the root of a checkout of `dev` at or after the merge of `v1-e39-t12`, after
`uv sync --all-packages`
```bash
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  BUCKET=$(python3 -c 'import tomllib; print(tomllib.load(open("config/profiles/dev.toml", "rb"))["storage"]["s3"]["bucket"])')
  CARD_ONLY=$(mktemp -d)
  aws s3 cp "s3://${BUCKET}/reports/tub/search/current.json" "${CARD_ONLY}/current.json" --profile debate-dev-evidence
  MANIFEST_KEY=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["manifest_key"])' "${CARD_ONLY}/current.json")
  aws s3 cp "s3://${BUCKET}/${MANIFEST_KEY}" "${CARD_ONLY}/current-manifest.json" --profile debate-dev-evidence
  STORES=$(python3 -c 'import json, sys; print(" ".join("--caselist " + one["caselist"] for one in json.load(open(sys.argv[1]))["stores"]))' "${CARD_ONLY}/current-manifest.json")
  echo "building: ${STORES}"
  DEBATE_ENV=dev uv run debate-research --json tub index build ${=STORES} > "${CARD_ONLY}/build.json"
  python3 - "${CARD_ONLY}/current-manifest.json" "${CARD_ONLY}/build.json" <<'EOF'
import json, sys
current = json.load(open(sys.argv[1]))
envelope = json.load(open(sys.argv[2]))
if not envelope.get("data"):
    print("STOP: the build failed:", (envelope.get("error") or {}).get("code"))
    raise SystemExit(1)
built = envelope["data"]
before = current["counts"]["documents_by_store"]
after = built["manifest"]["counts"]["documents_by_store"]
left = built["not_cards_by_store"]
print("current index", current["index_id"], current["counts"]["documents"], "documents")
print("new index", built["manifest"]["index_id"], built["manifest"]["counts"]["documents"], "documents")
stop = False
for store in sorted(set(before) | set(after)):
    was, now = before.get(store, 0), after.get(store, 0)
    share = 100 * now / was if was else 100.0
    out = left.get(store, {})
    print(f"{store}: {was:,} -> {now:,} documents ({share:.1f}%); left out as no card: "
          f"{out.get('cite_only', 0):,} cite only, {out.get('no_cite_few_words', 0):,} with no cite and under 25 words")
    stop = stop or now == 0 or share < 90
print("STOP: a store is empty or under 90% of the current index" if stop else "OK: every store keeps 90% or more")
EOF
fi
```
Success looks like `current index <id>`, `new index <id>`, one line per store with a share of about
96% or more, and `OK: every store keeps 90% or more`. Each store's "left out as no card" should be
near the counts above, a little higher if the store has grown since 2026-10-22. **Stop, and take the
output to the PM**, on a `STOP` line, on a store whose share is under 95%, or on counts far from
those above: the rule is not doing what was counted. Nothing has been published.

The second block publishes the newest index, the one the first block built, with no `--allow-shrink`.

**Operator command** (expected runtime under a minute)
Where: the same checkout
```bash
OVERRIDES=$(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')
PULL=$(pgrep -fl 'debate-research( --json)? caselist pull')
echo "running pull: ${PULL:-none}"
echo "DEBATE_ overrides: ${OVERRIDES:-none}"
if [[ -n "$PULL" || -n "$OVERRIDES" ]]; then
  echo "STOP: the line above that is not none says why. Wait for the pull to finish, or open a new window."
else
  aws sso login --profile debate-dev-evidence
  DEBATE_ENV=dev uv run debate-research tub index publish --env dev --newest
fi
```
Success looks like a table titled with the new index id the first block printed, whose last row is
`reports/tub/search/current.json`. **If it is refused** with `would shrink the published search
index`, stop and take the refusal to the PM: do not publish past the guard. Then record the current
and new index ids and document counts, total and per store, in
[the pilot's record](../data/evidence-search-pilot.md#the-card-only-rule-v1-e39-t12), and reinstall
the agent.

### Publishing a pending index by hand

`caselist pull --publish-pending` does not publish the index. The next weekly run with a session
does, without rebuilding it unless reconciling the suppression list changed its digest. To publish
it now to dev: `--newest` picks the newest index under the data directory's `tub-index` by the
stage's own rule, which is the one the run built.

```bash
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev debate-research tub index publish --env dev --newest
```

To prod, from the same data directory, as the parsed store is
([One data directory for each bucket](#one-data-directory-for-each-bucket)):

```bash
aws sso login --profile debate-prod-evidence
export DEBATE_ENV=prod DEBATE_STORAGE__DATA_DIR="${HOME}/.debate-research/dev"
debate-research tub index publish --env prod --newest --confirm-prod
unset DEBATE_ENV DEBATE_STORAGE__DATA_DIR
```

Success is a table whose last row is `reports/tub/search/current.json`, naming the index id, which
is the one the last run's `search_index` row names. A refusal names a parser or fingerprint version:
that index was built by another build than the one on your `PATH`. Or it is the shrink guard's,
naming a store and two counts: see [The shrink guard](#the-shrink-guard). `--newest` and `--index` are
refused together; `--index <directory>` publishes one directory you name instead.

**When `current.json` already names the newest index**, as after a rebuild under a longer suppression
list whose new entries stopped nothing, `--newest` uploads nothing of it again and leaves the pointer
alone (`v1-e39-t25`). It writes only `checked-against.json`, in a table titled `already current`, or
it is refused with `SEARCH_INDEX_ALREADY_CURRENT` when that record already says the same. Either way
the index is published and there is nothing more to do: see the evidence-search runbook's
[When the record means nothing is rebuilt or published again](evidence-search.md#when-the-record-means-nothing-is-rebuilt-or-published-again).

**An index built without a session read this Mac's copy of the suppression list alone.** That is safe
while this Mac is the only machine that imports and removes: every removal writes both copies, so
this Mac's is never behind the bucket's. It is the same condition
`LocalFallbackSuppressionList` names for the pull's own fallback (`v1-e34-t07`), and it is revisited
on the same day: the day a second machine imports or removes, publish a pending index only after a
run with a session has rebuilt it.

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
complete, and every snapshot whose manifest in the bucket the report stage found differing from
this Mac's, once; nothing else. It does not matter what ended the publish stage: an expired
session, a bucket that refused or did not answer, an upload that failed, or the Mac shutting down
part-way. A run writes the file before its first upload and again when the publish stage ends, so
a run that is killed has already written down what it owes. After a killed run the file can name a
snapshot the bucket does hold; the next run finds it complete and takes it off.

**A manifest that drifted is owed again, once** (`v1-e34-t26`, the PM's ruling of 2026-10-16).
This Mac's manifest is the record, and the bucket's copy follows it. So when the report stage finds
a snapshot whose manifest in the bucket differs from this Mac's, and nothing else differs, it adds
the snapshot to the end of the file, and the next run, or `caselist pull --publish-pending`,
publishes it again. Only that: a manifest the bucket has lost, a source with other bytes, or
either beside a manifest mismatch, is a failed report stage for a person, and owes nothing. The
stage's reason ends `owed again, for the next run to publish:` and the snapshots.

It never loops by itself. A snapshot a run owed again for this, that every run since has still
owed, and whose republish the bucket then confirmed, is not owed a third time when the report stage
finds its manifest differing again. The reason ends `drifted again after it was owed again and
published, so not owed a third time; a person should look:` and the snapshots, and the banner is
`caselist pull: a manifest drifted again`
([What a notification says](#what-a-notification-says)). Which of the two a drift is, the run
reads from the run log and the details beside it: the run that owed it again lists it in
`pending_publish` and its report stage's `drift` has it with the kind `manifest` alone. A run whose
details are missing says nothing of drift, so the guard can be one run late, owing a snapshot a
third time; the run after stops it.

The entries are the same shape as every other (below), so a build installed before `v1-e34-t26`
reads them and publishes them as it publishes any snapshot it owes. It never adds one itself.

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
with `not recorded as owed:` and their names. A manifest the report stage would owe again is not
written either; its reason ends `not recorded as owed, because the pending-work file could not be
read:` and the snapshots (`v1-e34-t26`). To repair it:

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

**`pending_publish` is not empty, and `publish` is `completed`.** The report stage found the
bucket's copy of a manifest differing from this Mac's and owed the snapshot again (`v1-e34-t26`):
its reason ends `owed again, for the next run to publish:` and names it. Nothing is needed. The run
is `incomplete`, not `publish_pending`, because no login waits: the next scheduled run publishes it,
or drain it now with the same command. If the reason says instead that it `drifted again`, see
[A manifest that drifted again](#what-a-notification-says).

**`report` is `pending`, and `publish` is not.** The publish finished and the session expired while
the report stage compared it with the bucket; the run is `publish_pending` (`v1-e34-t28`). Log in
and drain it as above, or leave it to the next scheduled run: either compares what the stage had
not reached ([What waits for the login](#what-a-notification-says)).

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
  store. After the fix the hint names, if there is one, run the command the stage names for each
  caselist (`v1-e34-t31`): `caselist parse --caselist <slug> --publish-only` where the rebuild read
  every copy of the suppression list and only the publish is owed, and
  `caselist parse --caselist <slug> --publish` where it names that, which rebuilds first. Or leave it
  to the next run, which parses and publishes what is owed whether or not it imports into that
  caselist (`v1-e40-t08`).
* `CHECKSUM_MISMATCH`: the bucket holds a file of the parsed store with other bytes, which the
  same parser never produces twice at one fingerprint version. A Mac at another fingerprint version
  does: its per-source files carry their own stamp
  ([`parsed-card-store.md`](../data/parsed-card-store.md#fingerprint-versions)), so check which
  build each machine that publishes runs. It needs a person; nothing was overwritten.
* `NEWER_FINGERPRINT_TABLE` (`v1-e34-t29`): the caselist's occurrence table, on this Mac or in the
  bucket, is stamped with a newer fingerprint version than the build that ran, which is usually the
  installed agent's after the checkout moved ahead. The older build would have put its own
  clusters back, so it wrote nothing and sent nothing: the table is as it was in both places. The
  stage's reason and the notification's hint name both versions and the store. Install a build at
  the newer version for the agent ([Reinstalling the agent](#reinstalling-the-agent)), then run
  `caselist parse --caselist <slug> --publish` from it to parse what the refused runs imported.
  Until then every pull fails its parse stage the same way for that caselist, whatever it imports: a
  refused caselist stays owed (`v1-e40-t08`), so each pull parses it again. Each pull still imports
  and publishes. `caselist parse` by hand and its `--publish` are refused by the same
  rule, with exit `1`, and an equal or older stamp is rebuilt and published as before. `store sync`
  moves nothing under `parsed/` either way (`v1-e29-t12`), so it is no way round the refusal and
  no way to publish the parsed store. Never delete the table to get past it.
* `INTERNAL_ERROR`: the parse crashed. Run `caselist parse --caselist <slug>` by hand to see it,
  and report it.

Running `caselist pull` again retries a parse stage whose parsed store was not published: since
`v1-e40-t08` the week stays owed in `caselist-sync-parse-owed.json` until its parsed store is
published complete, and a pull parses what is owed even when it imports nothing. A stage that failed
over its failure rate and published its store owes nothing, and is not retried.

**`report: failed` with a `hint`, and exit `0`.** Everything was published, and the comparison that
confirms it was refused. Nothing is lost and nothing waits for a login, but nothing leaves the inbox
until a run can confirm it. Make the fix the hint names; the next run confirms and clears the inbox.

**The run stopped with `STORE_ACCESS_DENIED` before fetching anything.** This Mac refused the
manifest folder, or one manifest file in it (`v1-e34-t19`), so the run could not tell which weeks
it already holds. It stops there rather than take every listed week for new and fetch them all
again, which is what an unreadable folder used to cause. Fix the permission on the data directory
and run the command again. The banner is `caselist pull failed: retried once fixed`, with the same
fix in its body (`will be retried` before `v1-e34-t23`).

**The banner says `needs a person`, and the run stopped because the AWS profile is not one this
Mac's AWS config defines.** `caselist runs` shows the class, `StoreProfileNotConfigured`. The
profile setting names an AWS profile this Mac's AWS config does not define, so the run was refused
before it fetched anything. Nothing is lost and nothing was spent. The run is in `caselist runs`
as `failed`, and its record waits to be published. Correct the setting or add the profile, confirm
it with `debate-research doctor --evidence-profiles`, and publish the record with
`debate-research caselist pull --publish-pending`, or leave it to next week's run:
[A profile the AWS config does not define](#a-profile-the-aws-config-does-not-define) has each
step. `aws sso login` does not fix it.

**`another caselist sync is already running`**, or the banner `caselist pull skipped: another
was running`. A run holds the lock at `<data_dir>/caselist-sync.lock`. It is an `flock`, so the kernel drops it when the process ends —
if you see this with no `debate-research` process running, something is holding the file open;
`lsof <data_dir>/caselist-sync.lock` says what.

**`the caselist_token has expired or been revoked`.** `debate-research caselist auth login` again.
If it happens immediately after a fresh login, **stop** and do not retry: access may have been
suspended, which is the site's right (policy clause 10), and the next step is to contact the
maintainer, not to work around it.

**The keychain refused the token store** (`v1-e34-t33`). The run failed with exit `1`, and the
banner says `needs a person` with the fix as its hint. It usually stops at the first request, which
reads the token; met later, when a request that worked stamps the token, it fails that stage with
the same code and hint. `caselist auth status`
in Terminal meets the same refusal and prints the same code and hint, with the keychain's OSStatus
under `details`. The keychain's own message is never printed or recorded, since it can quote a
path; the code is chosen from the OSStatus alone. Before `v1-e34-t33` each of these was
`INTERNAL_ERROR`, "a bug in debate-research" (the run of 2026-10-21).

| Code | OSStatus | What happened | Fix |
|---|---|---|---|
| `KEYCHAIN_INTERACTION_NOT_ALLOWED` | -25308 | The keychain needed a person, to be unlocked or to allow this program, and a run under launchd cannot ask | The Mac must be logged in, not only switched on, with its login keychain unlocked. If it is, run `debate-research caselist auth status` once in Terminal and choose Always Allow |
| `NO_KEYCHAIN` | -25291, -25294, -25307 | No keychain was open: nobody was logged in | The Mac must be logged in, not only switched on. Then `caselist auth status` checks the token is there |
| `KEYCHAIN_DENIED` | -128 | The keychain asked to be unlocked, or whether this program may use the item, and was told no. The two answer the same OSStatus, so they share the code | Run `caselist auth status` in Terminal, unlock the keychain and choose Always Allow; or set `caselist.token_backend = "file"` and log in again with `debate-research caselist auth login` |
| `KEYCHAIN_REFUSED_PROGRAM` | -25293, -67030 | The keychain could not confirm this program, or its own password | In Keychain Access, allow this build on the item `debate-research.opencaselist`, or delete the item and log in again; or the file backend, as above |
| `KEYRING_UNAVAILABLE` | none | `keyring` found no keychain backend at all | Set `DEBATE_CASELIST__TOKEN_BACKEND=file` and log in again |
| `CASELIST_TOKEN_MISSING` | none | No caselist_token is stored on this machine for the environment. The banner says so, with the fix as its hint (`v1-e34-t35`) | Log in again with `debate-research caselist auth login` |
| `CASELIST_TOKEN_UNREADABLE` | none | A caselist_token is stored on this machine for the environment, but not as a record this program wrote. The banner says so, with the fix as its hint (`v1-e34-t36`) | Log out with `debate-research caselist auth logout`, which deletes the record without reading it, then log in again with `debate-research caselist auth login` |

`CASELIST_TOKEN_MISSING` is a keychain with no item for the environment (-25300 reads as no token),
or a file backend with no file. Its line in the table is for a run on this Mac, and so is
`CASELIST_TOKEN_UNREADABLE`'s. A cloud run that stops on either names the code and the next cloud
run, as before: its token is the secret the Wednesday
login renews ([caselist-cloud-run.md](caselist-cloud-run.md)). `caselist auth logout` of a token
that is already gone succeeds and says there was nothing to delete. Any other OSStatus is still `INTERNAL_ERROR`; run
the command again by hand with `--verbose` to see the keychain's message, and report it.

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
the inbox *could not be read (PermissionError (errno 13))*, the zip may be whole and this user
cannot open it: fix its permission instead, and the next run imports it from the inbox without a
download. A camp download this Mac will not let be read is the same `UNREADABLE_ARCHIVE`, with the
same fix (`v1-e34-t23`; it used to be recorded as `INTERNAL_ERROR`).
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
