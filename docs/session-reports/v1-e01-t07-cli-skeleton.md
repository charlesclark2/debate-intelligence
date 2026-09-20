# Session report: v1-e01-t07-cli-skeleton

| | |
|---|---|
| Task | `v1-e01-t07-cli-skeleton` — debate_cli Typer + Rich skeleton |
| Spec | [`plan_specs/v1/e01-repo-foundation/t07-cli-skeleton.yaml`](../../plan_specs/v1/e01-repo-foundation/t07-cli-skeleton.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t07-cli-skeleton` |
| Session status | COMPLETE |

## Summary

`debate-research` now exists as an installed console script. It is a Typer group with
`--verbose`, `--json` and `--version`, a `doctor` command, and the four modules every later
command task plugs into: `output.py` (Rich tables and error panels for people, one JSON envelope
for programs), `exit_codes.py` (`ExitCode`, and the mapping from an exception to one),
`container.py` (the composition root) and `context.py` (what a command receives).

The decision worth the PM's attention first is where failures are handled. Rather than a decorator
each command has to remember, the root group itself (`DebateResearchGroup`) wraps the whole
invocation: any exception from any command at any depth — including the subcommand groups `store`,
`caselist`, `landscape` and `files` will add — is reported exactly once through `output.py` and
exits with the code `exit_code_for` gives it. A command author writes no error handling at all,
and the `--json` envelope and the exit codes cannot drift between commands written months apart.
The `--json` contract is stronger than "print JSON": stdout carries exactly one object per run,
success *or* failure, including usage errors and the bare `debate-research --json`, with every
diagnostic on stderr. That is asserted in the tests, not just documented, because
v1-e34-t02's scheduled caselist sync will parse it unattended.

Three things the PM's notes asked for are in place: the exit-code numbers are exactly the spec's
and live only in `ExitCode` (later tasks import it); the envelope has a `schema_version` and a
`data` object that commands own, so adding a field cannot break a consumer; and the container
takes a `settings_loader`, which is the one line v1-e02-t05 fills in. `commands/__init__.py`
documents registering a subcommand group as well as a plain command, and both paths are covered by
tests.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `entry-point` — Typer root app and console script | Done | `app.py`, and `debate-research = "debate_cli.app:main"` in `packages/debate_cli/pyproject.toml`. `--version` is handled in the root callback rather than in an eager option callback, so `--json --version` gets an envelope like any other result; see Decisions. Added `typer>=0.15` and `rich>=13.9` to the package's dependencies. |
| `output-helpers` — Rich output and exit codes | Done | `output.py`, `exit_codes.py`, and the package README's exit-code table and envelope contract. |
| `composition-root` — Composition root and placeholder doctor | Done | `container.py` (lazy per-run singletons, settings seam, `override` for tests) and `commands/doctor.py`, which reports versions, interpreter, platform, whether settings are configured and which services are wired. |
| `cli-tests` — CliRunner tests and type check | Done | `tests/test_app.py` (31 tests through Typer's `CliRunner`) and `tests/test_output.py` (29 unit tests); pyright clean. |

## Acceptance criteria

All commands run from the task worktree on `task/v1-e01-t07-cli-skeleton`, Python 3.12.7,
typer 0.27.2, rich 15.0.0, pytest 8.x, ruff 0.x, pyright 1.1.x.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Goal ac1: `--version` prints the package version and exits 0; `--help` lists `--verbose` and `--json` | PASS | `uv run debate-research --version` → `debate-research 0.1.0`, `exit=0`. `uv run debate-research --help` → exit 0, lists `--verbose  -v`, `--json`, `--version`, `--help  -h` and the `doctor` command. Asserted by `test_version_prints_the_package_version` and `test_help_lists_the_global_options_and_the_commands`. |
| Goal ac2: `output` renders success tables and typed error panels in Rich mode, and emits a single JSON object on stdout (diagnostics on stderr) in `--json` mode | PASS | `uv run pytest packages/debate_cli/tests/test_output.py` → `29 passed`. Rich mode: table on stdout (`test_rich_success_renders_the_table_on_stdout`), error panel with code, details, hint and `exit 1` on **stderr** with stdout empty (`test_rich_failure_renders_a_panel_on_stderr_and_leaves_stdout_clean`). JSON mode: every test parses stdout with a helper that asserts it is exactly one line of JSON; `test_json_success_emits_one_envelope_and_no_table`, `test_verbose_diagnostics_do_not_break_the_json_envelope`, `test_json_failure_after_a_result_stays_off_stdout`. End to end: `uv run debate-research --json doctor 2>/dev/null` → one object; `uv run debate-research --json --verbose doctor` puts `collecting environment facts` on stderr only. |
| Goal ac3: exit codes (0, 1, 2, 3, 70) defined in one module and documented in the CLI README | PASS | `packages/debate_cli/src/debate_cli/exit_codes.py` defines `ExitCode` with exactly those five values and `exit_code_for`/`error_code_for`; no other module writes a status number (`grep -rn "Exit(code=" packages/debate_cli/src` → only `ExitCode.*` members). Documented in `packages/debate_cli/README.md` under "Exit codes". Behaviour asserted: `test_a_domain_error_exits_one_and_keeps_its_facts` (1), `test_no_command_is_a_usage_error` / `test_unknown_command_is_a_usage_error` (2), `test_a_provider_failure_exits_three` (3), `test_an_unmodelled_exception_exits_seventy` (70), `test_an_outcome_failure_reports_itself_and_exits_one` (the `UNVERIFIED` shape, 1). |
| Goal ac4: `debate_cli.container` is the only place commands obtain services, and CliRunner tests cover `--version`, `--help` and `--json` output shape | PASS | Commands reach services only through `cli_context(ctx).services`; `doctor` is the worked example and `test_a_command_gets_its_service_from_the_container` / `test_a_test_can_replace_a_service_before_the_command_runs` exercise the seam. the only module-level object in the package is the `app` itself, so there is no global for a command to reach for. CliRunner coverage: `--version` (plain and `--json`), `--help`, `-h`, and the envelope shape for `doctor`, a group subcommand, and every failure class. |
| `entry-point`: command_succeeds `uv run debate-research --version` | PASS | → `debate-research 0.1.0`, exit 0 |
| `output-helpers`: test_passes `uv run pytest packages/debate_cli/tests/test_output.py` | PASS | → `29 passed in 1.11s` |
| `composition-root`: command_succeeds `uv run debate-research --json doctor` | PASS | → `{"schema_version": 1, "status": "ok", "command": "doctor", "data": {"cli_version": "0.1.0", "core_version": "0.1.0", "python_version": "3.12.7", …, "settings_configured": false, "services": []}, "error": null}`, exit 0 |
| `cli-tests`: test_passes `uv run pytest packages/debate_cli/tests` | PASS | → `62 passed in 2.07s` (31 in `test_app.py`, 29 in `test_output.py`, 2 pre-existing smoke tests); `debate_cli` statement coverage 99% (`output.py` and `exit_codes.py` 100%) |
| `cli-tests`: command_succeeds `uv run pyright packages/debate_cli` | PASS | → `0 errors, 0 warnings, 0 informations` |

Repo-wide gates, run after the last code commit:

| Gate | Status | Evidence |
|---|---|---|
| Full test suite | PASS | `uv run pytest` → `334 passed in 10.18s` (was 274 before this task; 60 new) |
| Lint | PASS | `uv run ruff check` → `All checks passed!` |
| Format | PASS | `uv run ruff format --check` → `132 files already formatted` |
| Type check (repo) | PASS | `uv run pyright` → `0 errors, 0 warnings, 0 informations` |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 278 files, 38 epics, 220 tasks, 20 releases`; `--require-succeeded v1-e01-t07-cli-skeleton` → `Succeeded` |

## Files changed

**`packages/debate_cli/src/debate_cli/`** — the CLI itself.
`app.py` holds the root Typer app, the callback that turns `--verbose`/`--json`/`--version` into
the run's `CliContext`, and `DebateResearchGroup`, the single error handler. `output.py` is the
only module that writes anything: Rich tables and panels, the JSON envelope, and the rule that
diagnostics go to stderr. `exit_codes.py` is the single source for the status numbers.
`container.py` is the composition root, with the lazy-singleton mechanism, the settings seam and a
test override. `context.py` carries the run's output and services to commands and records which
command is running so a failure can name it. `commands/__init__.py` registers the surface and
documents both registration patterns; `commands/doctor.py` is the first command. `__init__.py`
gained the version lookup `--version` and `doctor` report.

**`packages/debate_cli/tests/`** — `test_output.py` (the output contract in isolation) and
`test_app.py` (the real command line through `CliRunner`, including stand-ins for commands later
epics add). `test_smoke.py` is unchanged.

**`packages/debate_cli/pyproject.toml`** — the `debate-research` console script, plus `typer` and
`rich` dependencies. **`uv.lock`** — the resolved additions (typer 0.27.2, rich 15.0.0 and their
dependencies).

**`packages/debate_cli/README.md`** — rewritten: module map, how to write and register a command
or a command group, global options, the exit-code table, the `--json` envelope contract, and what
is deliberately not here yet.

**`plan_specs/v1/e01-repo-foundation/t07-cli-skeleton.yaml`** — Goal status to `Succeeded`.

## Deviations from the spec

**The spec's "`--version` eager option" is handled in the root callback instead.** A Click eager
option callback fires during parsing, before `--json` has been read, so `debate-research --json
--version` would have printed bare text and broken the one-object-on-stdout rule the same spec
asks for. The option is still declared `is_eager=True`; the callback body decides what to print.
Behaviour a user sees is unchanged: `--version` prints the version and exits 0, with or without a
command.

**Three modules the spec does not name were added**, none of them new scope: `context.py` (the
`CliContext` the spec's "context object" refers to, kept out of `app.py` so commands can import it
without importing the app), `commands/__init__.py` (the registration point and the documented
group pattern the PM asked for) and `commands/doctor.py`'s `environment_report`, which is the
command's own payload rather than a service.

**Observation, no action taken:** `plan_specs/README.md` says every task that adds a user-facing
surface includes a plan node adding its checks to `tests/smoke/`. This task adds a CLI surface but
its Plan has no such node, and `tests/smoke/` does not exist yet — it arrives with
v1-e01-t10-validate-dev-gate, which depends on this task. Nothing was invented here; see
*Follow-up work*.

## Decisions and assumptions

**Failures are handled by the root group, not by each command.** `DebateResearchGroup` overrides
`invoke` (and `make_context`, for a root command line that fails to parse). Every command and
subcommand group runs inside it, so nothing has to be remembered per command and there is one
place where an exception becomes a reported failure plus an exit code. `typer.Exit` and
`typer.Abort` pass through untouched; usage errors keep Click's own message and exit status and
only gain the JSON envelope. The alternative — a decorator on each command — would have been
forgotten by some task in E03–E34 and produced an inconsistent surface.

**The bare `debate-research` is a usage error (exit 2).** Help is printed and the run exits 2
rather than 0, so that "no command given" has an exit code a script can see and, in `--json` mode,
an envelope like every other failure. In Rich mode the help still goes to stdout, as it does for
`--help`.

**The envelope carries `schema_version` and a `data` object.** Per the PM's note about the
scheduled caselist sync: five fixed envelope keys, five fixed `error` keys, `null` rather than
absent, and per-command payloads confined to `data` so a command can grow a field safely. Anything
that breaks that bumps `schema_version`, which is why the number is there from the start.

**`error.code` is the `DomainError` subclass name in upper snake case.** `NotFound` →
`NOT_FOUND`, `ProviderRateLimited` → `PROVIDER_RATE_LIMITED`, with the exception's own attributes
(the ones `debate_core.application.errors` deliberately keeps) copied into `error.details`. A
consumer reads `details["key"]` rather than parsing English, and a new error class needs no
mapping table.

**`details` only carries JSON scalars.** Attributes are filtered to `str`/`int`/`float`/`bool`/
`None`, and `json.dumps(..., default=str)` is a backstop, so a stray object in a payload degrades
to a string instead of failing the run after the work is done.

**Shell completion is off (`add_completion=False`).** It adds `--install-completion` and
`--show-completion` to every help screen and a shell dependency, for no V1 benefit. Turning it on
later is one argument.

**Typer 0.27 vendors Click** (there is no `click` distribution in the lock). Nothing here imports
`typer._click`: the group class comes from the public `typer.core.TyperGroup`, and Click's
exception family is caught as `typer.TyperException`, which every `ClickException` derives from.
If a future Typer changes that, the tests for usage-error exit codes fail loudly rather than
silently mis-reporting.

**`Settings` is `Any` until v1-e02-t05.** The container takes a `settings_loader` callable and
caches its result; `doctor` reports whether one was supplied, and `SettingsNotConfigured` names
the task when something asks too early. That task replaces the alias and passes the loader in
`create_app`; nothing else in the container changes.

## Operator follow-ups

None. Everything in this task runs in seconds; the longest command was the full test suite at
10 seconds.

## Follow-up work

* **CLI smoke checks.** `tests/smoke/` does not exist yet. When v1-e01-t10-validate-dev-gate
  creates it, the first checks should be this surface: `debate-research --version`, `--json
  doctor` parsing as one JSON object, and a usage error exiting 2. Belongs to
  v1-e01-t10, not to a new task.
* **`--version` channel and commit.** v1-e01-t09 extends `--version`; the JSON payload is
  `{"package", "version"}` today and gaining `channel` and `commit` is a `data` addition the
  envelope contract already allows.
* **A `-q`/`--quiet` counterpart to `--verbose`** may be wanted once commands print progress.
  Not added speculatively; whoever needs it should add it with the command that does.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
