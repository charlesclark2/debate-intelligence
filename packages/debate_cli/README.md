# debate_cli

The `debate-research` command line: a Typer app with Rich output, and **no business logic**.
Commands parse arguments, ask the composition root for a service, and render what it returns;
everything a command actually *does* lives in `debate_core` (architecture proposal §4, §6, §11).

```console
$ uv run debate-research --version
debate-research 0.1.0
$ uv run debate-research doctor
$ uv run debate-research --json doctor | jq .data.cli_version
```

Today the app ships `--version` and `doctor`. The commands this skeleton exists for arrive with
their own tasks: `verify` (E03), `fetch` (E04), `search` and `cut` (E08), `daily` and `config`,
`store` (v1-e29-t05), `caselist` (E30; `caselist auth login|status|logout` from v1-e34-t01), `landscape` (E32), `files` (E33).

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
| `--version` | Print the installed version and exit 0. Works with `--json`. |
| `--help`, `-h` | Usage for the app or for a command. |

## Exit codes

`debate_cli.exit_codes.ExitCode` is the single source for these numbers; a command imports it
rather than writing an integer.

| Code | Name | Means |
|---|---|---|
| 0 | `OK` | The command did what it was asked to do. |
| 1 | `DOMAIN_FAILURE` | The command ran and the answer is a failure: a card is `UNVERIFIED`, a record was not found, a write lost its revision check. Running it again gives the same answer. |
| 2 | `USAGE_ERROR` | The command line was wrong: unknown command or option, missing argument, no command given. Nothing was executed. |
| 3 | `RETRIEVAL_FAILURE` | An external provider — search, fetch, a model — failed or rate-limited the call. The same command may well succeed later. |
| 70 | `INTERNAL_ERROR` | A bug: an exception the CLI does not model. 70 is `EX_SOFTWARE` from `sysexits.h`. |

Exceptions are mapped by `exit_code_for`: `ProviderError` → 3, any other `DomainError` → 1, a
usage error → 2, anything else → 70. A failure that is an *outcome* rather than an exception —
`verify` finding an unverifiable card — is reported with `output.failure(...)` and then
`raise typer.Exit(code=ExitCode.DOMAIN_FAILURE)`.

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

## Not here yet

* **Settings** are v1-e02-t05. `ServiceContainer` takes a `settings_loader` and that task passes
  one in; `doctor` reports whether settings are configured.
* **Release channel and commit** in `--version` are v1-e01-t09.
* **Smoke checks** for the CLI surface land with the `validate-dev` gate, v1-e01-t10.

## Tests

```console
uv run pytest packages/debate_cli/tests
```

`tests/test_output.py` covers the output contract in isolation; `tests/test_app.py` runs the real
command line through Typer's `CliRunner`, including commands that stand in for the ones later
tasks add, so the skeleton's promises are checked rather than described.
