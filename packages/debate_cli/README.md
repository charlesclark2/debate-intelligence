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
| `commands/` | One module per command, all registered in `commands/__init__.py`. |
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

Then register it in `commands/__init__.py`, which also shows how to register a group with
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

| Where it came from | `channel` | `DEBATE_ENV` unset means | Configuration read from |
|---|---|---|---|
| A source checkout (`uv run`) | `local` | `dev` | the checkout's `config/` |
| A dev pre-release | `dev` | `dev` | the `config/` bundled in the wheel |
| A stable release (v1-e09-t06) | `stable` | `prod` | the `config/` bundled in the wheel |

**What an installed build contains.** This package requires `debate-core[aws,docx,opencaselist]`:
the extras behind the adapters `debate_cli.container` wires, so a channel install has boto3, lxml,
httpx and keyring without anything added by hand. `scripts/install_channel.sh` proves it after every
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
| 1 | `DOMAIN_FAILURE` | The command ran and the answer is a failure: a card is `UNVERIFIED`, a record was not found, a write lost its revision check, `doctor` found a failed check (the interpreter's Unicode database is not the normalizer's pin, or a wired integration does not import). Running it again gives the same answer. |
| 2 | `USAGE_ERROR` | The command line was wrong: unknown command or option, missing argument, no command given. Nothing was executed. |
| 3 | `RETRIEVAL_FAILURE` | An external provider — search, fetch, a model — failed or rate-limited the call. The same command may well succeed later. |
| 70 | `INTERNAL_ERROR` | A bug: an exception the CLI does not model. 70 is `EX_SOFTWARE` from `sysexits.h`. |

Exceptions are mapped by `exit_code_for`: `ProviderError` → 3, any other `DomainError` → 1, a
usage error → 2, anything else → 70. A failure that is an *outcome* rather than an exception —
`verify` finding an unverifiable card — is reported with `output.failure(...)` and then
`raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)`.

## `debate-research doctor`

`doctor` reports what this installation is: both package versions, the interpreter and platform,
whether settings are wired, the services the container can build, the running Python's Unicode
database beside the version the evidence normalizer is pinned to (`v1-e01-t14`), and every
`debate_core.integrations` module the composition root wires with whether it imports (`v1-e01-t22`).
It fails on two checks only, the ones it can state precisely:

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
card manifest is reproducible from its stored snapshot. Each card's evidence is cut again from the
snapshot and compared exactly; snapshots are read from this environment's data directory
(`storage.data_dir`, from `DEBATE_ENV` or `DEBATE_STORAGE__DATA_DIR`) and never fetched. The work is
`VerifyManifest`'s, in `debate_core.application.verify_manifest`; the command only reads the file,
renders the report and chooses the exit code.

```console
$ uv run debate-research verify cards.json
$ uv run debate-research --json verify cards.json | jq '.data // .error.details | .cards[] | [.card_id, .status]'
$ DEBATE_ENV=test DEBATE_STORAGE__DATA_DIR=/tmp/verify-data uv run debate-research verify tests/fixtures/verify/mixed.json
```

The manifest is `{"manifest_version": 1, "generated_at": ..., "cards": [<Card>, ...]}`, published as
`packages/debate_core/schemas/card_manifest.v1.json`; each card is the domain `Card` and refers to
`card.schema.json`. A person sees a table of card id, tag, status and reason codes (`--verbose` adds
each reason's detail on stderr). `--json` prints one envelope, published as
`packages/debate_core/schemas/verify_result.v1.json`: the report under `data` on exit 0, under
`error.details` on exit 1.

| Exit | Means |
|---|---|
| `0` | Every card is VERIFIED. |
| `1` | The manifest was read and at least one card is UNVERIFIED. Every card is still listed. |
| `2` | A usage error, or a file that is not a card manifest: not JSON, or not valid against `card_manifest.v1.json`. The failing JSON path is reported and nothing is verified. |
| `3` | Verification could not run, for example because a store could not be read. No card has a verdict. |

Three rules worth knowing:

* A card whose snapshot is not in this data directory is UNVERIFIED with `SNAPSHOT_MISSING`. It is
  never skipped and never assumed.
* A card that passes the schema but is not a valid card, such as one whose `evidence_text` no
  longer fits its envelope (ADR-0018's length invariant, which a JSON Schema cannot express), is one
  UNVERIFIED row with `CARD_INVALID`. The other cards are still verified; the run is not a `2`.
* Exit `3` uses the CLI-wide `RETRIEVAL_FAILURE` number: the same command may succeed once the store
  can be read. It is never reported as `0` or `1`, because no card was judged.

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
