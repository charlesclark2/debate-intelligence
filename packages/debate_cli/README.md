# debate_cli

The `debate-research` command line: a Typer app with Rich output, and **no business logic**.
Commands parse arguments, ask the composition root for a service, and render what it returns;
everything a command actually *does* lives in `debate_core` (architecture proposal §4, §6, §11).

```console
$ uv run debate-research --version
debate-research 0.1.0 (local channel, dev environment, 8bfde67d2a41)
$ uv run debate-research doctor
$ uv run debate-research --json doctor | jq .data.cli_version
```

Today the app ships `--version` and `doctor`. The commands this skeleton exists for arrive with
their own tasks: `verify` (E03), `fetch` (E04), `search` and `cut` (E08), `daily` and `config`,
`store` (v1-e29-t05), `caselist` (E30; `caselist auth login|status|logout` from v1-e34-t01 and
`caselist pull` from v1-e34-t02), `landscape` (E32), `files` (E33).

`caselist pull` is the one command something other than a person runs: the weekly launchd
agent in [`ops/launchd/`](../../ops/launchd/) invokes it with `--json` and collects one object
per run ([`docs/runbooks/caselist-scheduled-sync.md`](../../docs/runbooks/caselist-scheduled-sync.md)).
That is why the envelope below is a contract rather than a convenience.

## The modules

| Module | What it is |
|---|---|
| `app.py` | The root Typer app: global options, the callback that builds the run's context, and `DebateResearchGroup`, which turns any failure into a reported error and an exit code. |
| `commands/` | One module per command. A command module imports no other command module; what two share lives in `options/` or beside it. |
| `command_registry.py` | Attaches every command to the root app. Only `app.py` imports it, so a test of one command does not import the rest. |
| `container.py` | The composition root: the only place a command obtains a service. |
| `context.py` | `CliContext` — the run's output and services — and how a command gets it. |
| `output.py` | Rich tables and error panels, the `--json` envelope, and the stdout/stderr split. |
| `exit_codes.py` | `ExitCode` and the mapping from an exception to one. |

## Writing a command

```python
def verify(ctx: typer.Context, path: Path) -> None:
    """One line of help text; the rest of the docstring is the command's long help."""
    cli = cli_context(ctx)  # the run's output and services
    report = cli.services.verification.verify(path)  # the work, done by debate_core
    cli.output.success(  # the result, rendered for both surfaces
        command_name(ctx),
        {"verified": report.verified, "unverified": report.unverified},
        display=TableSpec(columns=("Card", "Status"), rows=report.rows()),
    )
```

Then register it in `command_registry.py`, which also shows how to register a group with
subcommands (`debate-research store sync`).

Three things a command never does: catch a `DomainError` (the root group reports it and picks the
exit code), call `print` or `sys.exit` (that is `output.py` and `exit_codes.py`), or build a
service for itself (that is `container.py`).

## Global options

| Option | Effect |
|---|---|
| `--verbose`, `-v` | Progress and diagnostics on stderr, including the traceback when a command hits a bug. |
| `--json` | stdout carries exactly one JSON object — see below — and nothing else. |
| `--version` | Print the version, release channel, environment and commit, and exit 0. Works with `--json`. |
| `--help`, `-h` | Usage for the app or for a command. |

## Installed builds and release channels

A merge to `dev` publishes a GitHub pre-release `vX.Y.Z-dev.N` of this package
(`.github/workflows/dev-prerelease.yml`). Install one, outside any checkout, with:

```console
$ scripts/install_channel.sh v0.1.0-dev.3
$ debate-research --version --json | jq .data
{"package": "debate-cli", "version": "0.1.0.dev3", "channel": "dev", "commit": "…",
 "tag": "v0.1.0-dev.3", "built_at": "…", "run_id": "…",
 "environment": "dev", "environment_source": "build-channel:dev"}
```

A stable release `vX.Y.Z` is the build the team uses. It is published by
`.github/workflows/release.yml` when its tag is pushed on `main`, and only for the merge commit of
a validated dev → main promotion (v1-e09-t06). Install it the same way, by its tag:

```console
$ scripts/install_channel.sh v1.1.0
$ debate-research --version
```

`--version` names the tag's version, channel `stable` and environment `prod`. The script is the
one-line install. It verifies the release's `SHA256SUMS` before installing anything, installs both
wheels by their file URLs, so no package index can supply either name, and holds uv to the Python
`debate_core` declares. Plain `uv tool install` of the two downloaded wheels also works, from a
checkout of the tag, but checks none of that; it reads the Python from `debate_core`'s pyproject,
because uv ignores the upper bound of a wheel's `Requires-Python`:

```console
$ gh release download v1.1.0 --repo charlesclark2/debate-intelligence --pattern '*.whl' --dir debate-research-v1.1.0
$ uv tool install --managed-python --python "$(sed -n 's/^requires-python = "\(.*\)"$/\1/p' packages/debate_core/pyproject.toml)" "debate-cli @ file://$PWD/debate-research-v1.1.0/debate_cli-1.1.0-py3-none-any.whl" --with "debate-core @ file://$PWD/debate-research-v1.1.0/debate_core-1.1.0-py3-none-any.whl"
```

No extra is optional at install time. The CLI's own requirement names every `debate-core` extra
its commands wire, Bedrock's boto3 (`aws`) among them, so either command installs all of them.

| Where it came from | `channel` | `DEBATE_ENV` unset means | Configuration read from |
|---|---|---|---|
| A source checkout (`uv run`) | `local` | `dev` | the checkout's `config/` |
| A dev pre-release | `dev` | `dev` | the `config/` bundled in the wheel |
| A stable release (v1-e09-t06) | `stable` | `prod` | the `config/` bundled in the wheel |

**What an installed build contains.** This package requires
`debate-core[aws,docx,extraction,feeds,http,opencaselist,tub]`: the extras behind the adapters
`debate_cli.container` wires, so a channel install has boto3, lxml, trafilatura, readability-lxml,
pypdf, httpx, defusedxml, keyring and cryptography without anything added by hand. `scripts/install_channel.sh` proves it after every
install with `python -m debate_cli.installation`. That check reads the list of
`debate_core.integrations` modules from the installed container's own import statements, imports
each one, and fails unless it tried and imported them all. It also confirms that every distribution
behind the declared extras is installed. An adapter wired with an ordinary import is checked from the
day it is wired; a dynamic import makes the check refuse rather than skip it (v1-e01-t17). `doctor`
runs the same import check on any installed build, at any time (below).

**What an installed build resolved.** The installer resolves the third-party dependencies once, in
a rehearsal install that every check runs against. The real install is held to exactly what the
rehearsal installed: the rehearsal's `uv pip freeze` is passed to it as `--constraints`, and
afterwards the two environments must list the same distributions at the same versions
(v1-e01-t22). A release published to PyPI between the two installs therefore cannot reach the
build the launchd agent runs. uv records those pins in the tool's `uv-receipt.toml`.

If a command still meets a missing optional dependency, the failure says how to fix *this* kind
of installation, judged from the build's channel. An installed build is told to reinstall with
`scripts/install_channel.sh` at a fixed tag. A source checkout is told to run
`uv sync --all-packages --extra <extra>` from the workspace root. The exit status stays 70.

An explicit `DEBATE_ENV` always wins, and `DEBATE_PROFILE_DIR` overrides the bundled profiles.
`debate_cli/build_info.py` reads the stamp that `scripts/stamp_build.py` writes into a published
build (`_build_info.py` and `_bundled_config/`, both gitignored), and passes the channel and the
bundled directory to `load_settings`. The channel rules themselves are in
[`docs/process/branching-and-environments.md`](../../docs/process/branching-and-environments.md#the-v1-cli-channels-dev-pre-releases-and-stable-releases).

## Exit codes

`debate_cli.exit_codes.ExitCode` is the single source for these numbers; a command imports it
rather than writing an integer.

| Code | Name | Means |
|---|---|---|
| 0 | `OK` | The command did what it was asked to do. |
| 1 | `DOMAIN_FAILURE` | The command ran and the answer is a failure: `verify` found a card `UNVERIFIED`, a record was not found, a write lost its revision check, a profile setting names a profile the AWS config does not define, `DEBATE_REMOVAL_PROFILE` names a profile that is not signed in as the takedown role, `doctor` found a failed check (the interpreter's Unicode database is not the normalizer's pin, a wired integration does not import, or with `--evidence-profiles` a configured evidence profile is not defined). Running it again gives the same answer. |
| 2 | `USAGE_ERROR` | The command line was wrong: unknown command or option, missing argument, no command given. Nothing was executed. |
| 3 | `RETRIEVAL_FAILURE` | Something the command depends on did not answer, so there is no answer yet. An external provider — search, fetch, a model — failed or rate-limited the call, or a store could not be read or written: it was unavailable, the SSO session for it expired, or it refused access (the operating system refusing a data directory included). The same command may well succeed later. |
| 4 | `CARD_UNVERIFIED` | `cut` made a card and the evidence verifier did not pass it: the card was saved and written `UNVERIFIED`, with its banner, and each reason was printed. Never `0`, and not `1`, so a script can tell a card that needs a person's look from a cut that could not run (`v1-e06-t06`). |
| 6 | `SEARCH_PARTIAL` | `search` returned what it found while at least one provider it asked did not answer in full: it failed, timed out, was rate-limited, had its breaker open, was not configured or answered only partly. The footer names each one. A partial search with no rows is a `6` too (`v1-e08-t05`). `daily` exits `6` the same way, with its digest written (`v1-e08-t07`). |
| 7 | `NO_RESULTS` | `search` asked every provider, every one answered in full, and nothing matched. |
| 8 | `AUTO_CUT_SHORT` | `search --auto-cut N` (or `daily --auto-cut N`) made fewer than N VERIFIED cards: every result was tried, and the rest were inaccessible, not verified or could not be cut. What was cut is written (`v1-e08-t06`). |
| 9 | `BUDGET_EXCEEDED` | `search --auto-cut N` stopped short of N VERIFIED cards because the budget guard refused a model call (`--max-cost`, a daily or monthly limit, or a model with no price while a limit is set). The cards already cut are written. |
| 70 | `INTERNAL_ERROR` | A bug: an exception the CLI does not model. It is reported by its class, never its message (below). 70 is `EX_SOFTWARE` from `sysexits.h`. |

Exceptions are mapped by `exit_code_for`: `ProviderError` → 3; `StoreUnavailable`,
`StoreCredentialsExpired` and `StoreAccessDenied` (`RETRYABLE_STORE_FAILURES`) → 3 in every
command, and so are `caselist remove`'s `TakedownPreflightFailed` and `RemovalIncomplete` when one
of those three is what stopped them (`v1-e01-t20`); any other `DomainError` → 1, including
`NotFound`; a usage error → 2, and so is `search`'s `UnknownExpansionChoice` (`v1-e08-t05`);
anything else → 70. `search` takes its code from `exit_code_for_search`: 6 and 7 above, 3 when no
provider answered, 1 when none it selected is enabled. A failure that is an *outcome* rather than an
exception — `verify` finding an unverifiable card — is reported with `output.failure(...)` and then
`raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)`; `cut` exporting an `UNVERIFIED` card does the same
with `ExitCode.CARD_UNVERIFIED`.

**Exit 70 names the exception's class, never its message** (`v1-e01-t25`). An exception the CLI
does not model did not get its message from this project: an `OSError` quotes the path it failed
on, which carries the home directory and, for a file in the inbox, a camp file's title. So the
panel on stderr, and the envelope with `--json`, say only which class it was and how to see more:

```json
{"schema_version": 1, "status": "error", "command": "caselist pull", "data": null,
 "error": {"code": "INTERNAL_ERROR",
           "message": "debate-research stopped on an unexpected PermissionError. Its message is not printed, because it can quote a path on this machine.",
           "exit_code": 70, "details": {"exception_type": "PermissionError"},
           "hint": "This is a bug in debate-research. Re-run with --verbose for the traceback, which includes the error's message."}}
```

The detail is in the traceback, and `--verbose` is the only thing that prints it, on stderr. Run
the same command again with the flag; with `--json` too, stdout still carries the envelope above
and nothing else:

```bash
debate-research --verbose caselist pull --dry-run
```

The scheduled agent (`ops/launchd/`) runs `--json caselist pull` without `--verbose`, so its logs
hold the class and no traceback; the same command by hand with `--verbose` shows it. Errors the CLI
models keep their own messages and exit codes: every `DomainError`, every usage error, and the
incomplete-installation message for a missing optional dependency (`v1-e01-t17`), which is exit 70
with its own fix.

**A profile the AWS config does not define is a `1`, not a `3`** (`v1-e29-t07`). When the
environment's profile setting (`storage.s3.aws_profile`), `DEBATE_REMOVAL_PROFILE` for a takedown,
or `AWS_PROFILE` names a profile that this machine's AWS config does not define, every command that
reaches the bucket ends with `STORE_PROFILE_NOT_CONFIGURED` (`StoreProfileNotConfigured`) and exit
1. It means a setting has to be corrected, or the profile added on this machine: no login and no
retry defines a profile, so it is on neither retryable list. The message and the hint name the
setting the profile's name came from, and `error.details` carries `profile` and `setting`; they
never name the AWS config's path, and the hint points at
[`docs/runbooks/evidence-store.md`](../../docs/runbooks/evidence-store.md), which lists the
evidence profiles and how they are added. Until this task it was reported as
`STORE_CREDENTIALS_EXPIRED`, exit 3, with a command to run. An expired, unavailable or refused store
is unchanged: exit 3.

**A bucket's refusal carries its fix in every command** (`v1-e29-t07`). `STORE_ACCESS_DENIED` from
the bucket keeps its exit 3, and its `hint` is written by the S3 adapter: the profile is signed in
and lacks a grant, with the profile's name and a pointer to the same runbook, and never
`aws sso login`. `store`, `caselist publish`, `caselist status` and `caselist remove` show it, where
only `caselist pull` did; `caselist remove --execute` used to offer the takedown profile's login for
it.

A failure's **error code**, the `error.code` of the `--json` envelope, is its class name in upper
snake case: `StoreUnavailable` → `STORE_UNAVAILABLE`. The word is defined once, in
`debate_core.application.errors.error_code_of`, and `error_code_for` reads it from there
(`v1-e34-t13`), because the services below record failures by the same code the CLI reports them
under. `LocalStoreAccessDenied`, which the filesystem stores raise when the operating system refuses
a directory, is reported as `STORE_ACCESS_DENIED` like its parent.

Three commands record failures by error code rather than raising them, and all three decide their
exit code with `exit_code_for_failure_codes`: 3 only when **every** recorded code is one a retry
may cure, 1 as soon as one is not. A code on neither list, and a failure with no code, count as not
retryable, so nothing exits 3 because nobody classified it. The retryable codes are those of
`RETRYABLE_STORE_FAILURES` and of `RETRYABLE_PROVIDER_FAILURES` (`PROVIDER_UNAVAILABLE`,
`PROVIDER_RATE_LIMITED`).

* `store sync --apply` and `caselist publish` carry on past one object's failure and record each
  object's code. A checksum mismatch or a file missing locally makes the run a 1: running the
  command again cannot fix that one. `caselist publish` takes a failed manifest's code from the
  publish result's `manifest_error_code`, which `--json` prints beside `manifest_error`; the
  sentence in `manifest_error` is never read for it.
* `caselist pull` records, on each failed stage, the code of every failure behind it
  (`stages[].error_codes`), and the codes of the stages that had to finish (select, download,
  import, publish) decide: 3 when the bucket or this machine's store did not answer or refused, or
  an OpenCaselist download got a 5xx, a timeout or a rate limit that is not the daily cap; 1 for a
  refused or unreadable archive, a size ceiling, an expired OpenCaselist token, a checksum mismatch,
  the daily cap on a camp file, or a profile the AWS config does not define
  (`STORE_PROFILE_NOT_CONFIGURED`). `error.code` is `CASELIST_PULL_INCOMPLETE` either way. An
  *expired* AWS session during publish is still a *pending* publish and exits 0, because what was
  captured is safe and the next run finishes it. A session that is signed in and *refused* is not
  pending: the stage fails, exits 3, and its `hint` names the fix, a permission under
  `storage.data_dir` or a grant the profile lacks, never `aws sso login`. The grant's sentence is
  the S3 adapter's, read from the error (`v1-e29-t07`).
  A profile setting that names no profile in the AWS config stops the bucket's adapter being built,
  so on a real installation it refuses the pull before any stage, with `STORE_PROFILE_NOT_CONFIGURED`
  as `error.code` and exit 1, and nothing is fetched. The run is still recorded and announced
  (`v1-e34-t22`): a `failed` record in this machine's run log, details beside it with that code
  and the fix, which names the setting, and one notification that a person should look. The
  record is owed to the bucket and the next run that can reach it publishes it.
  `doctor --evidence-profiles` finds the setting before a run does.
  Whatever ended the publish stage, the pending-work file under `storage.data_dir` then holds every
  snapshot the bucket did not confirm complete, and `--publish-pending` takes one off only when the
  bucket has (`v1-e34-t18`). A pending-work file that cannot be read fails the stage with
  `PENDING_WORK_UNREADABLE`, exit 1, and is never written over.

## `debate-research doctor`

`doctor` reports what this installation is: both package versions, the interpreter and platform,
whether settings are wired, the services the container can build, the running Python's Unicode
database beside the version the evidence normalizer is pinned to (`v1-e01-t14`), and every
`debate_core.integrations` module the composition root wires with whether it imports (`v1-e01-t22`).

With `--evidence-profiles` it also reports each AWS profile this environment is configured to reach
the evidence bucket with, `storage.s3.aws_profile` and `DEBATE_REMOVAL_PROFILE` when it is set:
whether this machine's AWS config defines it, and which permission set it is signed in as
(`v1-e34-t22`). It fails on a profile that is not defined, with `STORE_PROFILE_NOT_CONFIGURED`,
naming the profile and its setting; an expired session is reported as expired, with the login, and
does not fail it. The profile Bedrock calls are signed with, `models.aws_profile`, is reported beside
them in the same words, on a `Model profile` row, and never fails the check (`v1-e05-t08`). The option reads the AWS config and asks AWS who each defined profile is. Plain
`doctor` does neither, which is why the installer and `validate-dev` can run it on a machine with
no AWS config. `ops/launchd/install.sh --check-launchd` runs it under launchd, as the weekly agent
will run. It names a permission set and never an account, a role's full identifier or the AWS
config's path.

With `--providers` it also reports the per-user credentials file, `~/.debate-research/<env>.env`
(read, not there, or not read in the test environment), and one row for each enabled discovery
provider: whether its key or the contact email is set and which source set it, never its value, or
what a search does without it, for example `Crossref | no contact email: Crossref's public pool` and
`GovInfo | no GovInfo key: GovInfo not asked` (`v1-e41-t22`). A blank value counts as missing. It
never fails on a row; a per-user file that is refused stops it as it stops every command that loads
settings. Plain `doctor` loads no settings and reads no per-user file.

Without the options it fails on two checks only, the ones it can state precisely:

* **The Unicode database.** Under any database but the pin, `normalize` refuses to run, so every
  command that touches evidence text would fail on first use.
* **The wired integrations.** Each one that does not import is named, with why, and every command
  that uses it would fail. The list and the imports are `debate_cli.installation`'s, the same logic
  as the installer's post-install check, so the list is still read from the container's own imports.

| Exit | Means |
|---|---|
| 0 | The report was produced, the interpreter's Unicode database is the normalizer's pin, and every wired integration imports. |
| 1 | A check failed. The databases differ (`UNICODE_DATABASE_MISMATCH`, naming both versions and `docs/evidence/normalization.md`), or wired integrations do not import (`INTEGRATIONS_DO_NOT_IMPORT`, naming each module and why), or both (`INSTALLATION_CHECKS_FAILED`, with both messages). `--json` carries the whole report in `error.details`. |
| 70 | A check could not be made at all: the normalizer's pinned version is unknown, or the container wires an integration in a way an import statement does not show. That is a bug in the build, reported through the root handler like any unmodelled exception, never as 1. |

**Whether uv manages the interpreter** (`v1-e01-t23`). `python_uv_managed` says whether the running
Python is one uv manages, which only uv changes: a `conda update` or `brew upgrade` cannot move it
under the installed build. It is decided by place, as uv decides it: the base prefix
(`python_base_prefix`, from `sys.base_prefix`), links followed, lies strictly inside
`uv_python_directory`, the directory `uv python dir` would name. That directory is worked out from
doctor's own environment: `UV_PYTHON_INSTALL_DIR` when it is set and not empty, otherwise
`$XDG_DATA_HOME/uv/python` when `XDG_DATA_HOME` is absolute, otherwise
`$HOME/.local/share/uv/python` (on Windows, `%APPDATA%\uv\data\python`). A checkout's `.venv` can
report `no`; that is expected, and never a failure.

Every other fact is description and never changes the exit status. That includes whether uv
manages the interpreter, and a declared `debate-core` extra whose distributions are not installed
(`extras_missing_distributions`): nothing fails until a wired integration needs one, and then the
integration check names it. The installer is stricter. Its own check, `python -m debate_cli.installation`, holds a build to everything it
declares and refuses one with a distribution missing, so it stays a separate step beside `doctor`.

`scripts/install_channel.sh` runs both in its rehearsal install, so a build that fails either is
refused before it replaces anything. Which interpreter is right is not written here: it is the
`debate_core` wheel's `Requires-Python`, which the installer reads from the wheel itself, and one
that uv manages (`--managed-python`), which the installer checks after each install.

## `--json` output

One object on stdout per run, success or failure, with the same five keys:

```json
{"schema_version": 1, "status": "ok", "command": "doctor",
 "data": {"cli_version": "0.1.0", "python_version": "3.12.7"}, "error": null}
```

```json
{"schema_version": 1, "status": "error", "command": "store sync", "data": null,
 "error": {"code": "PROVIDER_UNAVAILABLE", "message": "s3: no credentials",
           "exit_code": 3, "details": {"provider": "s3"}, "hint": null}}
```

What a scheduled consumer (v1-e34-t02's caselist sync is the first) can rely on:

* the five envelope keys and the five `error` keys are always present, `null` rather than absent;
* a command's own payload is under `data` and nowhere else, so a command may add fields there
  without breaking a consumer that reads two of them;
* branch on `status`, `error.code` and `error.exit_code`; `error.code` is the `DomainError`
  subclass name in upper snake case (`NOT_FOUND`, `REVISION_MISMATCH`, `PROVIDER_RATE_LIMITED`),
  and `error.exit_code` equals the process's exit status;
* everything else — progress, warnings, help, `--verbose` diagnostics, the human-readable form of
  an error — goes to **stderr**;
* a change that breaks any of the above bumps `schema_version`.

Evidence text never appears in the payload: `data` carries offsets, paragraph ids, counts and
metadata, which is the same rule the rest of the platform follows (architecture proposal §8).

## `debate-research verify`

`debate-research verify <manifest.json>` (`v1-e03-t06-verify-command`) checks that every card in a
card manifest is reproducible from its stored snapshot, and `debate-research verify evidence.docx`
(`v1-e06-t07`) does the same for a .docx debate-research exported, then checks its body. Each card's evidence is cut again from the
snapshot and compared exactly; snapshots are read from this environment's data directory
(`storage.data_dir`, from `DEBATE_ENV` or `DEBATE_STORAGE__DATA_DIR`) and never fetched. The work is
`VerifyManifest`'s, in `debate_core.application.verify_manifest`; the command only reads the file,
renders the report and chooses the exit code.

```console
$ uv run debate-research verify cards.json
$ uv run debate-research --json verify cards.json | jq '.data // .error.details | .cards[] | [.card_id, .status]'
$ DEBATE_ENV=test DEBATE_STORAGE__DATA_DIR=/tmp/verify-data uv run debate-research verify tests/fixtures/verify/mixed.json
$ uv run debate-research verify evidence.docx
```

The manifest is `{"manifest_version": 1, "generated_at": ..., "cards": [<Card>, ...]}`, published as
`packages/debate_core/schemas/card_manifest.v1.json`; each card is the domain `Card` and refers to
`card.schema.json`. A person sees a table of card id (with its snapshot id beneath), tag, status and
reason codes (`--verbose` adds each reason's detail on stderr). `--json` prints one envelope, published as
`packages/debate_core/schemas/verify_result.v1.json`: the report under `data` on exit 0, under
`error.details` on exit 1.

| Exit | Means |
|---|---|
| `0` | Every card is VERIFIED. |
| `1` | The manifest was read and at least one card is UNVERIFIED. Every card is still listed. |
| `1` (`BODY_CARD_NOT_IN_MANIFEST`) | A .docx's body holds a card its manifest does not list, such as one pasted in by hand. It is listed as UNVERIFIED, by its place in the body. |
| `2` | A usage error, or a file that is not a card manifest this build reads: not JSON, not valid against `card_manifest.v1.json`, or written by a newer build of debate-research. The failing JSON path is reported and nothing is verified. |
| `2` (`NO_MANIFEST`) | A .docx with no embedded manifest, such as a hand-cut team file. verify reads only files debate-research exported; nothing is verified. |
| `3` | Verification could not run, for example because a store could not be read. No card has a verdict. |

Three rules worth knowing:

* A card whose snapshot is not in this data directory is UNVERIFIED with `SNAPSHOT_MISSING`. It is
  never skipped and never assumed.
* A card that passes the schema but is not a valid card, such as one whose `evidence_text` no
  longer fits its envelope (ADR-0018's length invariant, which a JSON Schema cannot express), is one
  UNVERIFIED row with `CARD_INVALID`. The other cards are still verified; the run is not a `2`.
* Exit `3` uses the CLI-wide `RETRIEVAL_FAILURE` number: the same command may succeed once the store
  can be read. It is never reported as `0` or `1`, because no card was judged.
* A version-2 manifest's snapshot references (`sha256`, normalized text hash, normalizer and
  extractor versions, `retrieved_at`, `canonical_url`) are checked against the stored snapshot
  record. One that differs is `SNAPSHOT_REFERENCE_MISMATCH` on every card cut from that snapshot, in
  a JSON manifest and an embedded one alike.

### A .docx

A document `debate-research cut` wrote carries its manifest, so verify needs nothing beside it. The
cards in the manifest are verified as above, then the body is read in the format profile the cards
name and each card's evidence paragraph is compared with its `evidence_text` under the edit policy:

* deleting whole words or sentences, with or without the profile's ` … ` marker, and changing
  underlining, highlighting or sizes leave the card VERIFIED;
* a bracketed interpolation, `[like this]`, leaves it VERIFIED with the warning
  `INTERPOLATION_PRESENT` and the offset it is read before;
* any other change to the quoted words (a word changed or added, letters taken out of a word, two
  words joined, a paragraph added under the evidence) makes it UNVERIFIED with `MANUAL_EDIT`, the
  `evidence_text` range it replaced and the body range that replaced it, and the run exits `1`;
* a card whose tag is no longer in the body is UNVERIFIED with `BODY_CARD_MISSING`;
* a card in the body that the manifest does not list, such as one pasted in by hand, is a row of its
  own, named by its place in the body ("body card 2"), UNVERIFIED with `BODY_CARD_NOT_IN_MANIFEST`,
  and the run exits `1`. In `--json` it is an entry of `document.unclaimed_body_card_verdicts`, beside
  the positions in `document.unclaimed_body_cards`, and it counts in `total` and `unverified`.

The body is read as Word shows it: tracked insertions count, tracked deletions and hidden text do
not. Neither output quotes the evidence or an interpolation's words, and the file is only read.

## Not here yet

* **Settings** are v1-e02-t05. `ServiceContainer` takes a `settings_loader` and that task passes
  one in; `doctor` reports whether settings are configured.
* **Smoke checks** for the CLI surface land with the `validate-dev` gate, v1-e01-t10.

## Tests

```bash
uv run pytest packages/debate_cli/tests
```

`tests/test_output.py` covers the output contract in isolation; `tests/test_app.py` runs the real
command line through Typer's `CliRunner`, including commands that stand in for the ones later
tasks add, so the skeleton's promises are checked rather than described.

## `debate-research fetch`

`debate-research fetch <URL>` (`v1-e04-t06-fetch-command`) retrieves an article or open-access PDF
into a hashed snapshot in this environment's data directory, or says exactly why it cannot. The work
is `ArticleService`'s (`debate_core.application.article_service`), asked through `ArticleFetch`
(`debate_core.application.article_fetch`): the polite fetcher reads robots.txt and waits between
requests to one host, the access classifier decides the status, and a snapshot is stored only for an
ACCESSIBLE page. Paywalls are never bypassed.

```console
$ uv run debate-research fetch https://www.example.org/news/2026/10/some-story
$ uv run debate-research fetch https://www.example.org/news/2026/10/some-story --refresh
$ uv run debate-research --json fetch https://www.example.org/report.pdf | jq '.data.snapshot // .error.details.reason'
$ uv run debate-research fetch --paste my-copy.txt --source-url https://www.example.org/paywalled-story
$ uv run debate-research fetch --paste my-copy.txt --source-url https://www.example.org/paywalled-story --title "The story's title" --author "First Author" --author "Second Author" --date 2026-09-14 --publication "The Example Review"
```

A person sees the canonical URL, title, identifiers, access status and reason, provenance, and the
snapshot's id, both SHA-256 hashes, paragraph count, extractor and normalizer versions; a refusal is
a panel with the status, reason, status code, marker and rules version. `--json` prints one envelope,
published as `packages/debate_core/schemas/fetch_result.v1.json`. Neither ever holds page text.

`--refresh` asks the publisher again even when a snapshot younger than `articles.refetch_after_hours`
is stored. `--paste FILE` (or `-` for stdin) with `--source-url` stores text the user lawfully has,
such as a subscriber's copy, as USER_SUPPLIED, and fetches nothing. It is stored only after the user
attests lawful access, at a prompt in a terminal or with `--i-have-lawful-access` where no prompt can
be shown (`--json`, text on stdin, no terminal).

With `--paste`, `--title`, `--author` (once per author, in order), `--date` and `--publication` state
the copy's cite (`v1-e06-t12`), because a pasted copy has no markup to read one from. They are stored
with the copy, never as verified, and `cut URL --from-paste` cites the card with them. The card stays
UNVERIFIED for its cite (`CITATION_UNVERIFIED`), as a card cut from text a user supplied always is,
and the cite marks each field `[… unverified]`. The date is a full date, `YYYY-MM-DD`; a year alone or a
year and month is refused. A person sees the stored fields as `Stated …` rows, and `--json` as the
snapshot's `stated_cite`. Storing the same text again with none of these options, or with the same
ones, reuses the stored copy and its fields. With other options it stores a new copy holding exactly
the fields that command states, nothing carried over, so restate `--title` when you add `--author`.
A copy stored with stated cite fields needs this build or later: an older build cannot read its
record.

| Exit | Means |
|---|---|
| `0` | ACCESSIBLE and stored (or answered by a recent stored snapshot), or pasted text stored as USER_SUPPLIED. |
| `1` | Refused, nothing stored: not a source URL, pasted text not attested, or pasted text rejected (blank, too short, too large). |
| `2` | A usage error, for example `--paste` without `--source-url`, a URL and `--paste` together, a cite option without `--paste` or with an empty value, or a `--date` that is not `YYYY-MM-DD`. |
| `3` | PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND, UNSUPPORTED_TYPE or ERROR (`SOURCE_NOT_ACCESSIBLE`), or the fetcher could not run. No snapshot is stored. |

## `debate-research cut`

`debate-research cut <URL> --need "<research need>" --output evidence.docx` (`v1-e06-t06-cut-command`)
turns one article into one card. `ArticleFetch` retrieves the page, or uses a snapshot stored within
`articles.refetch_after_hours`; `CardService` asks the model (`card.select`, `card.markup`) where the
evidence for the need is and what to underline, cuts that passage from the stored text, cites it
(`CitationService`, with Crossref for a DOI) and verifies it; `ExportService` writes it in the
`--format` profile (`team-default`, `flow` or `plain`, from `config/format_profiles/`) with its
manifest embedded. The command only parses options, runs the three in order and reports what came
back; the words are `debate_cli.presenters.cut_presenter`'s.

```console
$ uv run debate-research cut https://www.example.org/news/2026/10/some-story --need "revival diverts conservation money" --argument "Conservation DA" --output evidence.docx
$ uv run debate-research --json cut https://www.example.org/report.pdf --need "habitat protection is cheaper" --output card.docx | jq '.data // .error.details | [.card_id, .status]'
$ DEBATE_MODEL_MODE=live uv run debate-research cut https://www.example.org/news/2026/10/some-story --need "revival diverts conservation money" --output evidence.docx
```

The model is called only in `live` or `record` mode (`DEBATE_MODEL_MODE`); otherwise its answers are
replayed from `<data dir>/cards/model-cassettes/`, and the `test` profile's fixture fake answers from
`tests/fixtures/model_outputs/`. Cassettes hold the articles' numbered text, so they stay on this machine.
Progress is one line per stage on stderr: `fetch`, `extract`, `select`, `verify`, `export`, as event
objects under `--json`. A person then sees a table of the card id, status, file, source, snapshot,
model calls and the manifest's SHA-256. `--json` prints one envelope: the card id and status, the file,
the source, each failure reason, each model call's provenance and the embedded manifest's identity,
under `data` on exit 0 and under `error.details` on exit 4. Neither holds evidence text; the manifest,
evidence included, is the one in the .docx. Cards belong to one fixed local owner id until V2's accounts.

| Exit | Means |
|---|---|
| `0` | The card is VERIFIED and was written to `--output`. |
| `1` | The cut could not run, and nothing was saved or written: the model provider refused the call (`MODEL_ACCESS_DENIED`, `MODEL_REQUEST_REJECTED`), the snapshot is missing or damaged, a prompt is not registered, no answer was recorded for a replayed call, or the URL names no source. |
| `2` | A usage error: no `--need`, a `--format` no profile has, an `--output` in a directory that does not exist. Nothing is fetched. |
| `3` | The source is PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND, UNSUPPORTED_TYPE or ERROR (`SOURCE_NOT_ACCESSIBLE`, with the status and the canonical URL), or the model provider did not answer or throttled the call. No card is saved and nothing is written. |
| `4` | The card is UNVERIFIED (`CARD_UNVERIFIED`): saved, written with its banner, and each reason printed. |

## `debate-research search`

`debate-research search "<query>"` (`v1-e08-t05-search-command`) asks every enabled discovery provider
at once and ranks what they find. `FederatedSearchService` in `debate_core` does the work: with
`--argument` and `--need` it expands the query into the taxonomy's queries for that pair
(`config/argument_taxonomy.yaml`, `v1-e08-t04`), asks each provider each query under
`providers.search_deadline_seconds`, merges what comes back into distinct sources (`v1-e08-t02`), ranks
them by seven explainable features (`config/federated_ranking.yaml`, `v1-e08-t03`), matches each to an
Article without fetching it, and stores the search. The providers are the ones `providers.enabled`
names that this build has adapters for: `openalex`, `crossref`, `rss` (the publisher feeds in
`config/feeds/`), `google_news`, and the government sources `federal_register` and `govinfo`. The
committed dev and prod profiles enable `openalex`, `crossref`, `rss`, `federal_register` and `govinfo`,
the providers whose live smoke has passed on the operator's machine (`v1-e07-t13`). The words are
`debate_cli.presenters.search_presenter`'s.

**Without a contact email or a key** a search still runs, and its footer says what is missing. Neither
goes in a profile. Each machine keeps its own in the per-user file `~/.debate-research/<env>.env`
(`~/.debate-research/dev.env` for dev), which every command reads whatever folder it runs in
(`v1-e41-t22`): [docs/guides/provider-credentials.md](../../docs/guides/provider-credentials.md) says
how to write it. It holds only `DEBATE_PROVIDERS__CONTACT_EMAIL`, `DEBATE_PROVIDERS__OPENALEX_API_KEY`,
`DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY` and `DEBATE_PROVIDERS__API_DATA_GOV_KEY`, and it is
refused unless only its owner can read it (`chmod 600`). An exported variable, or a `.env` in the
checkout or folder a command runs in, still wins over it. `debate-research config show` names where
each credential came from, with its value masked, and `debate-research doctor --providers` says, for
each enabled provider, whether its key or the email is set and what a search does without it.

* Crossref without `DEBATE_PROVIDERS__CONTACT_EMAIL` uses its public pool, which takes one query a
  second instead of three. A search of one query looks the same either way. An expanded search sends
  its queries one a second, and any it cannot send before its timeout come back not asked. The footer
  then says, for example, `crossref: partial, 9 results from 12 queries: not asked: the public pool
  allows 1 query a second; set a contact email for the polite pool`, and the search exits `6`. On the
  recorded fixtures the twelve-query NHI link search sends nine of its twelve Crossref queries in about
  9 seconds without an email, and all twelve in about 4 seconds with one.
* GovInfo without `DEBATE_PROVIDERS__API_DATA_GOV_KEY` is `not configured` on a topic that lists it,
  as below, and that search exits `6` too.

**Government sources** (`v1-e07-t07`) are asked only by a search on a topic that lists them:
`--topic policy-2026-27-nhi` asks the Federal Register's rules, proposed rules and notices and GovInfo's
bills, committee reports, hearings and committee prints, because `config/feeds/health-insurance.yaml`
lists both for that topic. A search with no `--topic` never asks them, and neither does one where
`providers.enabled` does not list them; enabling them in the profiles changed neither rule. The Federal
Register takes no key. GovInfo needs a free
api.data.gov key in `DEBATE_PROVIDERS__API_DATA_GOV_KEY`, from https://api.data.gov/signup/. Without one,
a search on the topic reports `govinfo: not configured: govinfo: no api.data.gov key
(DEBATE_PROVIDERS__API_DATA_GOV_KEY)` and exits `6`. GovInfo and the Federal Register are each asked
once per query, so the twelve-query NHI link search sends each twelve requests. api.data.gov allows a
key 1,000 requests an hour, which is about 80 such searches an hour, and then answers `429` for the
rest of the hour; the footer says so.

```console
$ uv run debate-research search "midterm elections" --since 2026-09-14 --max-results 20
$ uv run debate-research search "national health insurance" --argument politics-da --need link --topic policy-2026-27-nhi
$ uv run debate-research search "de-extinction" --format json | jq '.data // .error.details | .results[] | [.rank, .title, .explanation]'
$ uv run debate-research search "health insurance" --argument ptx --need uq --var bill=reconciliation --expand-llm
$ uv run debate-research search "marketplace enrollment" --topic policy-2026-27-nhi --since 2025-01-01
```

A person sees a table of rank, title, publisher or venue, date, source type, access and the ranking's
explanation, then the expansion's line and a footer with one line per provider: `openalex: ok, 12
results`, `rss: partial, 4 results: 1 of 6 feeds failed: …`, `openalex: timeout: no answer within 10s`.
`--format json` (or `--json`) prints one envelope whose search object carries, for each result, its
rank, score, seven features and their contributions, explanation, identifiers, the providers that found
it and its Article id and access status. Neither surface prints a snippet or an abstract: search
returns sources, not cards, and access stays `UNKNOWN` until `fetch` or `cut` reads the page.
`--save PATH` writes the same search object to a file. `--expand-llm` also asks a model for up to three
extra queries, replayed from `<data dir>/search/model-cassettes/` unless `DEBATE_MODEL_MODE` is `live`
or `record`; it is off unless given, and a model that cannot be asked leaves a warning on stderr and the
template queries alone.

| Exit | Means |
|---|---|
| `0` | Every provider answered in full, with results. |
| `1` | No provider was asked: none of those selected is enabled (`NO_PROVIDER_ENABLED`). |
| `2` | A usage error: an unknown `--argument`, `--need`, `--topic` or `--var` (the valid ones are listed), `--since` after `--until`, a provider this build does not have. Nothing is searched. |
| `3` | No provider answered (`SEARCH_FAILED`). |
| `6` | Partial (`SEARCH_PARTIAL`): results from the providers that answered, and the footer names each one that did not. |
| `7` | Every provider answered, and nothing matched (`NO_RESULTS`). |

## `debate-research daily`

`debate-research daily <preset> --date YYYY-MM-DD` (`v1-e08-t07-daily-command`) writes one day's digest
of new research for a preset in `config/daily_presets.yaml`: `politics` (politics DA and midterms DA
uniqueness, from the politics feeds) and `nhi` (the NHI topic's spending, federalism and economy DA
uniqueness). `DigestService` in `debate_core` runs each of the preset's queries, expanded for each of
its argument/need pairs, through `search`'s federated search for the window (`--window 1d` to `31d`,
ending with `--date`, in UTC; `--date` defaults to today). The feed and Google News providers are built
for the preset's own feed topics, so a politics digest never reads the health-insurance feeds. A
preset is added by adding it to the file: every preset there is checked when `daily` runs, and an
unknown preset exits `2` listing the presets.

The digest is `digests/<preset>-<date>.md` (`--format json` writes `.json` and prints it; `--digest-dir`
names another directory): each new result under its argument and need, with its title, publisher,
date, the ranking's explanation and its URL, then `search`'s provider footer. A feed topic with a feed
still `awaiting_coach_review` is read, and the digest says so. Results a digest of the same preset
listed on another date are left out; running a date again lists its own again. What each preset has
listed is kept by canonical URL and DOI in `<data dir>/daily/seen/<preset>.json`, written only after
the digest file is, so a run that fails marks nothing seen. `--auto-cut N` then cuts the new results
as `search --auto-cut` does, each group's top result first and each card cut for its own argument and
need, into `<preset>-<date>.docx` beside the digest.

```console
$ uv run debate-research daily politics --date 2026-09-17
$ uv run debate-research daily nhi --window 3d --format json | jq '.data // .error.details | .groups[] | [.heading, (.results | length)]'
```

| Exit | Means |
|---|---|
| `0` | Every provider answered; the digest is written, with new results or none. |
| `1` | None of the preset's providers is enabled (`NO_PROVIDER_ENABLED`); nothing is written. |
| `2` | A usage error: an unknown preset (the presets are listed) or a `--window` that is not `1d` to `31d`. |
| `3` | No provider answered (`SEARCH_FAILED`); nothing is written and nothing is marked listed. |
| `6` | Partial (`SEARCH_PARTIAL`): the digest is written, and the footer names each provider that did not answer. |
| `8`, `9` | With `--auto-cut`, as for `search --auto-cut`. |
