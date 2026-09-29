# Session report: v1-e01-t13-composition-root-cleanup

| | |
|---|---|
| Task | `v1-e01-t13-composition-root-cleanup` — Empty the import-boundary exception lists |
| Spec | [`plan_specs/v1/e01-repo-foundation/t13-composition-root-cleanup.yaml`](../../plan_specs/v1/e01-repo-foundation/t13-composition-root-cleanup.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t13-composition-root-cleanup` |
| Session status | COMPLETE |

## Summary

Both exception lists are now empty. The only `ignore_imports` entry left on the composition-root
contract is the composition root itself (`debate_cli.container -> debate_core.integrations.**`),
which was never one of the five exceptions. `KNOWN_INTEGRATIONS_IMPORTS` and
`KNOWN_THICK_HANDLERS` are both empty.

The work landed as two commits, so each half can be reviewed on its own:

1. **The container builds the adapters** (`887adcf`). `caselist import` and `import-openev` now get
   the archive reader, the archive digest and the manifest path from `debate_cli.container`.
   `caselist auth` now types against new Protocols in `debate_core.application.ports.caselist_session`
   instead of the OpenCaselist adapter's classes.
2. **`caselist pull` under budget** (`e34f72d`). The dry-run / whole-run / `--publish-pending`
   sequencing moved, statement for statement, into
   `debate_core.application.caselist_sync.run_pull`. `pull` went from 33 statements to 16. It got
   there without a helper extracted just to move statements, and without touching the budget.

What the PM should look at first: behaviour is unchanged. `packages/debate_cli/tests/` has no diff
and passes. A before/after capture of 45 `caselist pull` invocations, covering help, every mode,
every refusal, text/JSON and quiet/verbose, is byte-identical after normalising timestamps, and
that includes the run log the monitor writes.

`caselist_sync.py` is the module the operator's evening backfill runs. Nothing already in it
changed; the new function was added next to the service. The one execution-order difference is
explained under Decisions below. The operator may still choose to hold the merge until the
backfill closes.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `adapters-to-container`: the container builds the four adapters | Done | The four command imports removed; `ServiceContainer.read_archive`, `archive_digest` and `evidence_object_path` added; `caselist_auth` retyped against the new `CaselistLoginSession` / `IssuedToken` / `StoredToken` ports. The four `ignore_imports` entries and `KNOWN_INTEGRATIONS_IMPORTS` are gone. |
| `thin-the-pull-command`: `caselist pull` under budget | Done | `run_pull` + `PulledRun` in `caselist_sync.py`. `pull` holds 16 statements. `KNOWN_THICK_HANDLERS` is empty. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the container builds the four adapters the caselist commands imported directly, and the commands receive them. `KNOWN_INTEGRATIONS_IMPORTS` and the matching `ignore_imports` entries are removed entirely | PASS | `grep -rn "debate_core.integrations" packages/debate_cli/src/debate_cli/commands/` → only a docstring cross-reference in `caselist.py`, no import. `pyproject.toml` `ignore_imports = ["debate_cli.container -> debate_core.integrations.**"]` (the root only). `scripts/check_thin_handlers.py`: `KNOWN_INTEGRATIONS_IMPORTS: Set[tuple[str, str]] = frozenset()` |
| ac2: `caselist pull` is at or under 25 statements, with its run-mode sequencing behind the sync service, and `KNOWN_THICK_HANDLERS` is empty | PASS | `uv run scripts/check_thin_handlers.py --list` → `16  debate_cli.commands.caselist_pull.pull` (was 33). `KNOWN_THICK_HANDLERS: Mapping[str, int] = {}`. The thickest handler is now `caselist.publish` at 20. |
| ac3: behaviour unchanged. The existing CLI tests pass untouched, and `pull --help`, `--dry-run` and `--publish-pending` output is the same as before | PASS | `git diff 763f4f5 -- packages/debate_cli/tests` → empty. `uv run pytest packages/debate_cli/tests/` → `234 passed` (234 before as well). Before/after capture (method under Decisions): `diff before.txt after.txt` → no differences across 45 scenarios, after the container change and again after the pull change. |
| ac4: `uv run lint-imports` keeps every contract with no `ignore_imports` for these cases, and `uv run scripts/check_thin_handlers.py` passes with both lists empty | PASS | `uv run lint-imports` → `Contracts: 10 kept, 0 broken.`; the composition-root contract reports `KEPT (6 ignored imports)`, down from 10, and all 6 are the container's own. `uv run scripts/check_thin_handlers.py` → `OK: 16 CLI command and API route handlers within 25 statements`, exit 0. |
| Node `adapters-to-container`: "Contracts kept with no exceptions for these imports" (`uv run lint-imports`) | PASS | As in ac4: exit 0, 10 kept. |
| Node `thin-the-pull-command`: "Thin-handler check passes with empty exception lists" (`uv run scripts/check_thin_handlers.py`) | PASS | As in ac4: exit 0. |
| Node `thin-the-pull-command`: "CLI behaviour is unchanged" (`uv run pytest packages/debate_cli/tests/`) | PASS | `234 passed in 17.67s` |

Also run: `uv run pytest -q` (whole default suite) → `2912 passed, 1 skipped in 45.30s`. This was
at 02:17 CDT, so the known after-19:00 ledger failures (v1-e34-t06) could not appear.
`uv run pyright` → `0 errors`. `uv run ruff check` and `ruff format --check` are clean.
`uv run scripts/validate_specs.py` → `OK: 288 files, 38 epics, 230 tasks, 20 releases`.

## Files changed

* `packages/debate_cli/src/debate_cli/container.py`: new adapter accessors `read_archive`
  (the local reader bound to `caselist.max_archive_bytes` / `max_unpacked_bytes`), `archive_digest`
  and `evidence_object_path`. `_build_caselist_sync` now passes `self.read_archive` instead of an
  identical inline lambda, so the size ceilings are bound in one place.
* `packages/debate_cli/src/debate_cli/commands/caselist.py`: `import` and `import-openev` call those
  accessors. The adapter imports are gone.
* `packages/debate_cli/src/debate_cli/commands/caselist_auth.py`: its annotations use the new ports.
  It never constructed anything; its adapter imports were for typing only.
* `packages/debate_cli/src/debate_cli/commands/caselist_pull.py`: selects the slugs, calls
  `run_pull`, renders.
* `packages/debate_core/src/debate_core/application/ports/caselist_session.py` (new):
  `CaselistLoginSession`, `IssuedToken`, `StoredToken`. These are Protocols only; pyright confirms
  `OpenCaselistClient` and `StoredCaselistToken` satisfy them structurally. The port index in
  `ports/__init__.py` has a new row.
* `packages/debate_core/src/debate_core/application/caselist_sync.py`: `run_pull`, `PulledRun`, and
  a short "Which run a `caselist pull` is" docstring section. Nothing already in the module changed.
* `pyproject.toml`: the four grandfathered `ignore_imports` lines and their comment are removed.
  The contracts themselves are untouched.
* `scripts/check_thin_handlers.py`: both exception lists are emptied and the docstring and comments
  now say so. The checking logic is untouched.
* `tests/architecture/test_import_contracts.py`: see Deviations.

## Deviations from the spec

* **I edited `tests/architecture/test_import_contracts.py`, which is outside `constraints.packages`.**
  `test_an_exception_that_no_longer_matches_an_import_fails` proved that a stale `ignore_imports`
  entry fails lint-imports. It did that by editing the real grandfathered
  `caselist_auth -> opencaselist.auth` import out of a copy of the tree, and it asserted that the
  import existed. Once ac1 removes that import, the test cannot be written that way. I kept the
  property it proves and changed only where the stale entry comes from: it is now added to a copy of
  `pyproject.toml` (the same edge the last exception named), and the test passes that copy to the
  existing `lint_imports` helper through a new optional `config` argument.
  * Mutation check: with `unmatched_ignore_imports_alerting = "none"` set on the contract in the
    copy, lint-imports exits 0, so the test goes red. It still bites.
  * This is not a CLI test; `packages/debate_cli/tests/` is untouched (ac3).
* **The sequencing is a module-level function beside `CaselistSyncService`, not a method on it.**
  The spec says "behind CaselistSyncService". The sequence has to build the service *inside*
  `SyncRunMonitor.watch`, because building it is where `CaselistApiDisabled` is raised, and the
  command's own comment requires that refusal to be recorded and announced like any other. The
  baseline pins this: `pull --publish-pending` with the API off writes a `failed` run-log record.
  A method on an already-built service would move that refusal outside the monitor, which is a
  behaviour change. So `run_pull` takes a factory for the service and lives in `caselist_sync.py`.
  It has no logic of its own; the statements are the command's, moved verbatim, with
  `cli.output.detail` passed in as `progress`.

## Decisions and assumptions

* **How I proved ac3 beyond the unit tests.** A scratchpad harness (not committed) ran
  `debate-research caselist pull` through `CliRunner` against the real container. The API was
  answered by respx from the synthetic `tests/fixtures/caselist` archives. It ran 45 scenarios:
  * `--help`;
  * for text and `--json`, each with and without `--verbose`:
    * dry run;
    * dry run with no caselist;
    * dry run with the profile's caselists;
    * dry run with the API off;
    * dry run with the API off and no caselist;
    * `--publish-pending`;
    * `--publish-pending` with the API off;
    * both flags together;
    * a whole run;
    * a run with no caselist;
    * a run with the API off.

  For each it recorded the exit code, stdout, stderr, the HTTP requests made, the files left in the
  data directory and every `.jsonl` log. Timestamps, run ids and durations were normalised. I
  captured `before.txt` on the start commit, then diffed after each of the two commits: identical
  both times. The harness can go in the PR thread or into `scripts/` if the PM wants it kept.
* **Error order in the import commands is preserved.** `import` and `import-openev` used to load
  `settings` as their first statement and no longer need the value. Settings load lazily, so
  dropping the line would change which error wins when the profile is broken *and* `--snapshot` is
  malformed. So the load stays as the first statement, as a bare `cli.services.settings`
  (`# noqa: B018`) with a one-line comment saying why.
* **The one execution-order difference in `caselist pull`.** In a dry run the sync service is now
  built inside `asyncio.run`, not just before it. For whole runs, the monitor is likewise built
  inside `asyncio.run`, not just before it. `--publish-pending` and whole runs already built the
  service inside the loop, and nothing either constructor does depends on whether a loop is
  running. The output, exit codes, requests, files and run log are identical.
* **`summary_path` after the run** comes from calling the service factory again, exactly as the
  command did before. The container's `caselist_sync` is a per-run singleton, so nothing is built
  twice.
* **`caselist_auth` needed ports, not container changes.** Its three adapter imports were
  annotations only. The container already built the client and the token store and still returns
  the concrete types. The command now names only application-layer Protocols.
* **`caselist_sync.py` imports `SyncRunMonitor` / `SyncRunRecord` under `TYPE_CHECKING`**, because
  `sync_runs` already imports `caselist_sync` at runtime.

## Operator follow-ups

None required for this task. Because `caselist_sync.py` and the `pull` command are on the
backfill's path, the operator may want one extra check before merging, or after the backfill
closes: run the evening's usual `caselist pull --dry-run` (or `--publish-pending`) from this
worktree and compare it with the same command from the main checkout. It is optional; the offline
capture above already covers every mode.

## Follow-up work

* **`[tool.importlinter] unmatched_ignore_imports_alerting = "error"` appears to be inert at the top
  level** (v1-e02-t06's territory; not changed here). I measured this while mutation-checking the
  rewritten test:
  * With the top-level key set to `"error"`, `"warn"` or `"none"`, a stale entry still exits 1.
  * With `"none"` set *on the contract*, the same stale entry exits 0.

  So the protection comes from import-linter's per-contract default, not from the line whose comment
  calls it "stated rather than inherited". If the intent is to pin the behaviour, the key probably
  belongs on each contract. This belongs with E02 (import-boundary guard) for the PM to decide.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
