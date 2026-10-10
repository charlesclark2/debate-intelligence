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
| `full_archive` | What the complete-archive rotation decided and why (`reason`), what the weeklies left of the day's allowance, and for a complete archive imported, its `bytes` and its `withdrawn` and `superseded` counts. See [The complete archive](#the-complete-archive) |
| `openev_selections[]` | Each camp file OpenEv listed: its `openev_id`, the run's `decision`, and `inbox_file`, the first twelve hex digits of the download's sha256 once the run had its bytes (the name `inbox_retention` gives the same file) |
| `stages[]` | One entry per stage, each with the sentence saying why it ended that way (`reason`). A failed stage also carries `error_codes`, the code of each failure behind it, and, when a store refused it, `hint`, the fix that applies (`v1-e34-t13`). See [What the exit code says](#what-the-exit-code-says) |
| `schema_version` | `4` since `v1-e34-t13`, which added the two fields above to every stage. A summary written by an older build says `3` and has neither. Nothing reads a summary back; `caselist runs` reads the run log, which builds of both kinds read and write alike |

Nothing in that object is a school, a team code, a debater's initials, a disclosure path, a camp
file's title or the `caselist_token` — the policy forbids all of them in a log, and the summary is
built to the same rule, so these logs can be pasted into an issue as they are. A camp download is
named by its OpenEv id, `openev-777`, with `(sha256 2b912c191a8a)` once the run has its bytes, and
never by its file name, which is its title (`v1-e34-t12`). Summaries and logs written before that
change may still name camp files, so check older ones before pasting them. A failed stage's reason,
codes and hint name no path on this Mac either: a folder the operating system refused is named by
what it is for, and the data directory and the inbox by those names (`v1-e34-t13`).

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
| `70` | A bug | Report it |

The agent never runs again on any exit code: launchd records the number and waits for next week's
slot. A `3` on Wednesday therefore means "next Wednesday's run, or the same command by hand now".

Which failure is which:

| The stage failed because | `error_codes` | Exit |
|---|---|---|
| The bucket did not answer: a 5xx, a throttle, a timeout | `STORE_UNAVAILABLE` | `3` |
| The bucket refused the profile: it is signed in and lacks a grant | `STORE_ACCESS_DENIED` | `3`, with a `hint` |
| This Mac refused a folder under the data directory | `STORE_ACCESS_DENIED` | `3`, with a `hint` |
| OpenCaselist answered a download with a 5xx, or the connection failed or timed out, and the client's retries ran out | `PROVIDER_UNAVAILABLE` | `3` |
| OpenCaselist rate-limited a download, and it was not the daily cap | `PROVIDER_RATE_LIMITED` | `3` |
| The daily cap, on a weekly archive | none: the stage completes and the week is deferred | `0` |
| The daily cap, on a camp file | `DAILY_DOWNLOAD_LIMIT_REACHED` | `1`: a verdict for the day |
| OpenCaselist answered `401` or `403`: the `caselist_token` expired. Never retried, by policy | `CASELIST_AUTH_EXPIRED` | `1` |
| The file host no longer serves an archive it listed | `ARCHIVE_UNAVAILABLE` | `1` |
| An archive is over `caselist.max_archive_bytes` | `ARCHIVE_TOO_LARGE` | `1` |
| A download did not arrive whole | `DOWNLOAD_INTEGRITY_ERROR` | `1` |
| A zip cannot be read | `UNREADABLE_ARCHIVE` | `1` |
| A copy of the suppression list has a line nobody can read | `UNREADABLE_APPEND_ONLY_RECORD` | `1` |
| A source's bytes in the bucket are not the ones its key names | `CHECKSUM_MISMATCH` | `1` |
| `--full-archive` cannot be covered by the day's allowance | none: the run is refused before any stage, with `error.code` `FULL_ARCHIVE_REFUSED` | `1` |
| Anything with a code that is on neither list, or with no code | for example `INTERNAL_ERROR` | `1` |

One failure of the second kind among any number of the first makes the run a `1`: a week that
cannot be read is not fixed by the bucket coming back. A failure that ends the run before any stage
records it, such as OpenCaselist not answering the listing, exits as it does in every other command:
`3` for a store or a provider that did not answer, with that failure's own `error.code`.

**A `hint` on a failed stage is the fix that applies, and it is never a login.** Two refusals have
one, and they are told apart by where the refusal came from:

* *This Mac refused a folder.* The hint names the folder by what it is for ("the blob directory",
  "the manifest directory") and the setting `storage.data_dir`. Check that the user the agent runs
  as can read and write the data directory, then run the command again.
* *The bucket refused the profile.* The hint says the profile lacks a grant and points at
  [`evidence-store.md`](evidence-store.md), which lists what each profile is granted and how to
  check it. `aws sso login` does not change a grant.

Before `v1-e34-t13` both were reported as `publish: pending` with a notification naming
`aws sso login`, and a failed stage exited `1` whatever it failed on.

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

**`pending_publish` is not empty, and `publish` is `pending`.** The SSO session expired. Log in
and drain it:

```bash
aws sso login --profile debate-prod-evidence
debate-research caselist pull --publish-pending
```

**`pending_publish` is not empty, and `publish` is `failed`.** The snapshots are imported and still
owed, and logging in is not the fix. If the stage has a `hint`, a store refused it: make the fix the
hint names (a permission on the data directory, or a grant; see
[What the exit code says](#what-the-exit-code-says)). If its code is `STORE_UNAVAILABLE`, the bucket
did not answer and there is nothing to fix. Either way the next scheduled run publishes them, or
drain them now:

```bash
debate-research caselist pull --publish-pending
```

**`report: failed` with a `hint`, and exit `0`.** Everything was published, and the comparison that
confirms it was refused. Nothing is lost and nothing waits for a login, but nothing leaves the inbox
until a run can confirm it. Make the fix the hint names; the next run confirms and clears the inbox.

**The run stopped with `STORE_ACCESS_DENIED` before fetching anything.** This Mac refused the
manifest folder, so the run could not tell which weeks it already holds. It stops there rather than
take every listed week for new and fetch them all again, which is what an unreadable folder used to
cause. Fix the permission on the data directory and run the command again.

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
hand: remove it from the inbox, and the next run downloads it again. A camp download is named in the
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
