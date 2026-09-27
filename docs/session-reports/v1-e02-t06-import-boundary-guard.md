# Session report: v1-e02-t06-import-boundary-guard

| | |
|---|---|
| Task | `v1-e02-t06-import-boundary-guard` — Import-boundary enforcement |
| Spec | [`plan_specs/v1/e02-domain-core/t06-import-boundary-guard.yaml`](../../plan_specs/v1/e02-domain-core/t06-import-boundary-guard.yaml) |
| Epic / release | `v1-e02-domain-core` / `v1.0` |
| Branch | `task/v1-e02-t06-import-boundary-guard` |
| Session status | COMPLETE |

## Summary

The `import-boundaries` CI job was already green against five contracts, each keeping one library
(boto3, httpx/keyring, lxml/python-docx) inside its adapter. None of them described the architecture
itself. This task adds five contracts that do:

* an exhaustive layers contract inside `debate_core`
* no delivery framework in the domain, evidence or application layers
* no `debate_core` → delivery-package imports
* delivery packages independent of one another
* delivery packages reaching `debate_core.integrations` only through their composition root

Every one of the ten contracts is now proven to fail. `tests/architecture/test_import_contracts.py`
copies the real package trees into `tmp_path`, adds a hand-written violating import (26 cases), and
checks that `lint-imports` exits non-zero and reports that contract BROKEN by name. The suite also
fails if a contract is ever added without such a case.

`scripts/check_thin_handlers.py` covers what import-linter cannot see, how much a CLI command or API
route does, and now runs as a second step of the existing `import-boundaries` job. No required
status checks were added.

**Look at first:** Deviation 1. Two CLI command modules already import adapters directly, which the
new composition-root contract forbids. They are listed edge by edge rather than exempted as a
package, because fixing them means editing `debate_cli`, which is outside this task and has another
task in it this week.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| contracts (import-linter contracts) | Done | Five new contracts in `[tool.importlinter]`; the five existing ones are unchanged apart from one stale comment. |
| negative-tests (tests that contracts fail on violations) | Done | 29 tests: a clean-copy control, 26 violations, a stale-exception case, and a test that every contract has a case. Before accepting the suite, I mutation-tested it by weakening two contracts (next section). |
| thin-handlers (thin-handler AST check) | Done | PEP 723, standard library only, pure functions; 35 tests. |
| ci-wiring (wire into the import-boundaries CI job) | Done | One step added to the `import-boundaries` job; nothing else in `ci.yml` changed. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — forbidden and layers contracts are configured and `uv run lint-imports` passes on main | PASS (on this branch; see Deviation 3) | `uv run lint-imports --no-cache` → `Contracts: 10 kept, 0 broken.`, exit 0. Includes `debate_core layers: integrations and testing above application above evidence above domain KEPT`, plus four `forbidden` contracts and one `independence` contract of this task's. |
| ac2 — adding `import boto3` to debate_core.application makes lint-imports fail, with the contract name in the output | PASS | **Done in this worktree:** wrote `import boto3` to `debate_core/application/boundary_probe.py`, then ran `COLUMNS=200 uv run lint-imports --no-cache --no-logo` → exit 1, `The AWS SDK never reaches the domain, the application layer or the other adapters BROKEN`, `Contracts: 9 kept, 1 broken.`, `-   debate_core.application.boundary_probe -> boto3 (l.1)`. File removed afterwards; `git status` clean. **Kept as a test:** the same case is `test_a_violating_import_breaks_its_contract_by_name[debate_core.application.boundary_probe: import boto3]`, one of 26. |
| ac3 — `scripts/check_thin_handlers.py` fails when a CLI command or API route function goes over the configured statement budget, or imports from debate_core.integrations directly | PASS | `uv run pytest tests/architecture/test_thin_handlers.py` → `35 passed`. These cover: a registered command over budget, decorator/callback commands, API routes (7 decorator methods and `add_api_route`), the `--budget` option, and 5 import forms plus a function-local import. On the repo, `uv run scripts/check_thin_handlers.py --budget 15` → exit 1, naming `caselist.publish` (20), `caselist.status` (18) and `store.sync` (19). |
| ac4 — the import-boundaries CI job runs both checks and is NOT made a required status check of its own | PASS | `.github/workflows/ci.yml` `import-boundaries` job steps: `lint-imports` (existing) and `check_thin_handlers.py` (added, lines 180–181). The job was already in the aggregate `ci` job's `needs` and path-filter map. No ruleset or required check was touched. |
| contracts node: lint-imports passes | PASS | `uv run lint-imports` → `Contracts: 10 kept, 0 broken.` |
| negative-tests node: contract violation tests pass | PASS | `uv run pytest tests/architecture/test_import_contracts.py` → `29 passed in 2.77s` |
| thin-handlers node: thin-handler check tests pass | PASS | `uv run pytest tests/architecture/test_thin_handlers.py` → `35 passed in 1.64s` |
| ci-wiring node: CI runs the thin-handler check | PASS | `grep -n check_thin_handlers.py .github/workflows/ci.yml` → lines 180, 181 |
| ci-wiring node: thin-handler check passes on the repo | PASS | `uv run scripts/check_thin_handlers.py` → `OK: 16 CLI command and API route handlers within 25 statements`, exit 0 |

**Checking the tests themselves.** I weakened `pyproject.toml` twice and ran the negative suite, then
restored the file (empty `git diff` afterwards):

* **The four exact exception edges replaced by `debate_cli.commands.* -> debate_core.integrations.**`:**
  3 failures. Both new-command violations stopped being caught, and the stale-exception case failed.
* **`exhaustive = true` removed from the layers contract:** 1 failure. The unplaced
  `debate_core.unplaced_layer` subpackage stopped being caught.

**Other checks.**

* `uv run pytest -q` (whole suite) → `2809 passed, 1 skipped in 41.47s`.
* `uv run ruff check .` → all passed; `uv run ruff format --check .` → `386 files already formatted`.
* `uv run scripts/validate_specs.py` → `OK: 287 files, 38 epics, 229 tasks, 20 releases`.

## Files changed

* `pyproject.toml`, `[tool.importlinter]` only: five new contracts, and two stale comments rewritten.
  The existing contracts' rules are unchanged.
* `tests/architecture/test_import_contracts.py` (new): the negative tests for every contract.
* `scripts/check_thin_handlers.py` (new) and `tests/architecture/test_thin_handlers.py` (new): the
  thin-handler check and its tests.
* `.github/workflows/ci.yml`: one step added to the `import-boundaries` job and nothing else. v1-e01-t09
  is also editing this file this week, so a merge conflict, if any, will be confined to that job's
  steps.
* `plan_specs/v1/e02-domain-core/t06-import-boundary-guard.yaml`: Goal phase set to `Succeeded`.

## Deviations from the spec

1. **Four existing CLI imports of adapters are listed as exceptions, not fixed.** The spec's rule,
   that delivery packages reach `debate_core.integrations` only through the composition root, is
   already broken in two command modules:
   * `debate_cli.commands.caselist` imports `debate_core.integrations.local.archive_reader`
     (`read_archive`, `archive_digest`) and `...local.fs_object_store` (`FsEvidenceObjectStore`).
     `import_archive`, `import_openev` and `status` construct them inline.
   * `debate_cli.commands.caselist_auth` imports `debate_core.integrations.opencaselist`
     (`OpenCaselistClient`, `StoredCaselistToken`) and `...opencaselist.auth` (`IssuedToken`),
     for type annotations and small async helpers.

   Fixing them means moving construction into `debate_cli.container`, which is a `debate_cli` change.
   That is outside `constraints.packages`, beyond "what the contracts need", and `debate_cli` is being
   edited by v1-e01-t09 this week. So the contract is written as it should be, and those exact four
   edges (`module -> module`, no wildcards) are in its `ignore_imports`, with the same four in the
   thin-handler check's `KNOWN_INTEGRATIONS_IMPORTS`. The only wildcard entry is
   `debate_cli.container -> debate_core.integrations.**`, which is the composition-root exemption the
   spec itself describes. Three things keep the exception honest:
   * A new command importing an adapter, including the same `archive_reader` module from another
     command, fails. Both are tested.
   * An entry that stops matching an import fails `lint-imports` (import-linter's
     `unmatched_ignore_imports_alerting` defaults to error; tested), and fails the thin-handler check
     (tested). Whoever fixes a command therefore has to delete its line.
   * The PM may prefer to treat this as a spec question instead: widen this task's packages to allow
     the `debate_cli` refactor, or leave the edges in place.
2. **One handler is over the statement budget and is recorded at its current size.**
   `debate_cli.commands.caselist_pull.pull` holds 33 statements against a budget of 25. It chooses
   between `--dry-run`, `--publish-pending` and a monitored run itself, which is sequencing that
   belongs in `CaselistSyncService`. It is in `KNOWN_THICK_HANDLERS` at 33. It fails if it grows, and
   the entry has to be lowered if it shrinks and removed once it is within budget (all three tested).
   It was not refactored, for the same reason as Deviation 1.
3. **ac1 says "passes on main".** I can only run `lint-imports` on this branch, which is cut from
   `dev`. I have marked ac1 PASS, not NOT RUN, because this change can only reach `main` through a
   promotion PR. That PR's single required `ci` check includes `import-boundaries`, which runs on any
   change to `pyproject.toml`, `packages/`, `scripts/` or `ci.yml`, so a failing `lint-imports` cannot
   merge into `main`. If the PM reads "on main" as a measurement to be taken after promotion, ac1
   becomes NOT RUN and the phase should go back to InProgress.

## Decisions and assumptions

* **Layers include `evidence`.** The spec's layers were domain < application < integrations.
  `debate_core.evidence` exists and imports only the domain, and the application layer imports it, so
  it sits between them.
* **`testing` is a layer beside `integrations`**, written `integrations | testing`, which makes the two
  independent of each other. The shared fakes may import application and domain but not an adapter,
  and an adapter may not import a fake. Both hold today.
* **`exhaustive = true`.** A new `debate_core` subpackage fails the layers contract until someone
  places it in a layer. Without this, a new subpackage would be unconstrained by default.
* **The delivery-framework contract also forbids `click` and `starlette`**, the frameworks under typer
  and fastapi. It covers `evidence` as well as domain and application. boto3, botocore and httpx were
  already forbidden to those modules by the existing contracts, so they were not listed twice. Both
  `fastapi` and `starlette` are not installed; the negative test shows that `from fastapi import
  APIRouter` in the application layer is still caught.
* **The delivery packages are independent of one another** (a separate `independence` contract, not
  part of the spec's text). Code that the CLI and the API both need belongs in `debate_core`. It holds
  today.
* **Negative tests use the real configuration.** They run `lint-imports --config <repo>/pyproject.toml`
  over a copy of the real package trees, rather than a hand-made mini-package with its own config. A
  mini-package would only test a duplicated config that could drift from the real one. The copy wins
  over the editable installs because `PYTHONPATH` comes before the `.pth` path entries in
  site-packages. `COLUMNS=500` stops rich wrapping a long contract name across lines, which would
  otherwise make a correct failure look like a missing name. The whole file runs in about 3 s.
* **Thin-handler budget: 25 statements, counted at every depth.** The docstring is excluded; nested
  functions, loops and branches count. On the 16 current handlers, the largest outside the exception
  is 20 (`caselist.publish`) and the median is about 10. That leaves room for option handling and
  rendering, while an inline workflow would exceed the limit. The budget can be changed with
  `--budget`.
* **How handlers are found.** CLI commands are functions registered through `<group>.command(...)(fn)`
  or `.callback(...)(fn)`, which is how `register_commands` works, or decorated with those methods.
  API routes are FastAPI route decorators or `add_api_route` endpoints. `debate_api` has no routes yet,
  so the API side is proven only on fixtures. The adapter-import rule applies to any module that
  defines a handler, including imports inside function bodies.
* **Test location.** The spec's node outputs and criterion commands name
  `tests/architecture/test_thin_handlers.py`, so the tests are there rather than under
  `tests/scripts/` as the session notes suggested. `tests/` is not listed in `constraints.packages`,
  but the spec's own outputs put these files there.
* **Pyright.** Run by hand over the new files: 0 errors, except that it cannot resolve the
  `sys.path`-inserted `import check_thin_handlers`. That is the same pattern as
  `tests/scripts/test_check_promotion_source.py`, and CI's pyright includes only `packages/`.

## Operator follow-ups

None. Every command in this report ran in under a minute.

## Follow-up work

* **Move adapter construction out of `debate_cli.commands.caselist` and `caselist_auth` into
  `debate_cli.container`** (Deviation 1). Each fixed import deletes one `ignore_imports` line and one
  `KNOWN_INTEGRATIONS_IMPORTS` entry. This belongs with the caselist CLI owners (E30/E34), or as a small
  debate_cli task once v1-e01-t09 has merged.
* **Move `caselist pull`'s run-mode sequencing into `CaselistSyncService`** (Deviation 2), same owners.
* **debate_api and debate_workers need their composition roots registered.** When one arrives, the
  task adding it needs a `debate_api.<root> -> debate_core.integrations.**` line in the
  composition-root contract. That task should expect `lint-imports` to fail until the line is added;
  the contract's comment says so.
* **An adapter subpackage must still be added by hand to the AWS and httpx contracts' source lists**
  (the existing convention from v1-e29-t04/v1-e34-t01). This task left that unchanged. A new adapter
  missing from those lists would not be caught.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
