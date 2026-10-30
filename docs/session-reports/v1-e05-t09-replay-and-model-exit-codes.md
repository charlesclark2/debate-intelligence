# Session report: v1-e05-t09-replay-and-model-exit-codes

| | |
|---|---|
| Task | `v1-e05-t09-replay-and-model-exit-codes` — Replay tolerates a new optional parameter, a refused model call is not retryable, and doctor can check the routing file |
| Spec | [`plan_specs/v1/e05-model-router/t09-replay-and-model-exit-codes.yaml`](../../plan_specs/v1/e05-model-router/t09-replay-and-model-exit-codes.yaml) |
| Epic / release | `v1-e05-model-router` / `v1.2` |
| Branch | `task/v1-e05-t09-replay-and-model-exit-codes` |
| Session status | COMPLETE |

## Summary

All five parts are done.

1. **Replay.** Replay now compares a cassette's recorded request as a parsed `ModelRequest`. A field the cassette lacks takes its default, so a new optional `ModelParams` field no longer breaks every cassette. A recorded value that differs from the call's is still refused. The committed cassettes need no edit.
2. **Exit codes.** `ModelAccessDenied` and `ModelRequestRejected` now end a command with exit 1. Throttling and an unavailable model still exit 3.
3. **Routing check.** `doctor --routing-file` is a new opt-in check. It names a bad routing file's key and exits 1 with `ROUTING_CONFIG_ERROR`. Plain `doctor` still loads no settings.
4. **Doctor's socket.** The socket plain `doctor` opens turned out to be urllib3's IPv6 probe when it is imported: one bind to `::1`, loopback only. The PM ruled option A (2026-10-30): keep doctor's real import check, and prove instead that plain `doctor` makes no network call and binds nothing but loopback. A fresh-interpreter guard does that. **ac4 as written is superseded by that ruling** (Deviation 1).
5. **jinja2 contract.** An import contract keeps `jinja2` out of `debate_core.domain` and `debate_core.application`.

Every PM-listed mutant is caught. The Goal is `Succeeded`, on the PM's instruction with the ruling.

**What to look at first:**

1. **Deviation 1**, part (4): the strict pytest-socket guard fails on both the start commit and the branch, for one reason.
2. **The affected set** was stopped at the two-minute line at 46%, with no failure up to that point. It is left to the pull request's `ci` check, per the PM's ruling of 2026-10-19.
3. **The landscape and weekly-run answer** to the PM's exit-3 question (Decisions 3). Nothing there assumed the old behaviour.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `replay-exit-doctor` — Replay, exit codes and doctor | Done | Parts (1)–(4) in `record_replay.py`, `exit_codes.py`, `routing_policy.py`, `container.py`, `doctor.py`; part (5) in `pyproject.toml` (Deviation 2). Six commits, each one part. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a cassette recorded before a new optional field replays, and one whose recorded value differs does not, by tests shown failing first; the committed cassette needs no hand edit | PASS | **Red first**, tests written before the change: `.venv/bin/python -m pytest packages/debate_core/tests/integrations/models/test_record_replay.py -k "optional_parameter or any_parameter or before_effort or recorded_value_differs or parameter_the_cassette_lacks or not_a_request" -n0` → `9 failed, 9 passed`. The failures were the four optional fields each removed from a cassette, the whole `params` object removed, the committed example cassette with `effort` removed (its state before v1-e05-t02's hand edit), and three requests that do not parse. All 9 raised `MissingFixtureError` ("the cassette at this key recorded …"). The 9 that passed were the refusals of changed values, which held before and still hold. **Green**: the whole file → `173 passed`. No file under `tests/fixtures/model_cassettes/` changed: `git diff --stat cf93758 HEAD -- tests/fixtures/model_cassettes` lists only `README.md`. |
| ac2: `ModelAccessDenied` and `ModelRequestRejected` exit 1, and throttling still exits 3, by test | PASS | **Red first**: `pytest packages/debate_cli/tests/test_output.py -k model_call -n0` → `3 failed, 2 passed`. Each failure was `assert <ExitCode.RETRIEVAL_FAILURE: 3> is <ExitCode.DOMAIN_FAILURE: 1>`. **Green**: `test_output.py` and `test_recorded_failure_codes.py` → `98 passed`. The cases are no credentials, not granted and a rejected parameter (exit 1, codes `MODEL_ACCESS_DENIED` / `MODEL_REQUEST_REJECTED`), and throttled and unavailable (exit 3). |
| ac3: the opt-in check names a bad routing file's key and exits 1; plain doctor is unchanged, by test | PASS | `pytest packages/debate_cli/tests/commands/test_doctor_routing_file.py -n0` → `9 passed`. Each of `routes.card_selection`, `routes.high_volume.model_id` and `routes.high_volume.temperature` gives exit 1, code `ROUTING_CONFIG_ERROR`, the key in the message, in `details.routing_file.field` and in the hint. A missing file names its path. Plain `doctor` with a bad file exits 0, and with `ServiceContainer.settings` set to fail it never asks for settings; it has no `routing_file` key and no row. **Red** against the pre-change code (`git checkout HEAD~1 --` the three source files, then restored, tree clean): `7 failed, 2 passed`. The 2 that passed are the plain-doctor tests, which pass both ways by design. |
| ac4: plain doctor opens no socket, shown by the socket guard failing on the start commit and passing after | SUPERSEDED by the PM's ruling (Deviation 1) | **Strict pytest-socket guard**, plain `doctor` in a fresh interpreter (scratch probe: `pytest_socket.disable_socket(allow_unix_socket=True)`, then `CliRunner().invoke(create_app(), ["doctor"])`). On the start commit `cf93758` → `exit 0 socket attempts 1`, at `urllib3/util/connection.py:137` → `:126` (`socket.socket(socket.AF_INET6)`). On the branch `50e3c06` → identical. The one attempt is urllib3's `HAS_IPV6 = _has_ipv6("::1")`, run when doctor's integration check imports the boto3-backed adapters. **The guard as amended by the PM** is `test_plain_doctor_reaches_no_network.py`, below. |
| ac4 as amended by the PM: plain doctor makes no network call and binds nothing but loopback, shown by a guard that fails on either | PASS | `pytest packages/debate_cli/tests/commands/test_plain_doctor_reaches_no_network.py -n0` → `13 passed`. Plain `doctor` → `{"attempts": [], "exit_code": 0, "urllib3_imported": true}`: urllib3 was imported and its `::1` probe was allowed. **Red, twice**, each planted in `environment_report`, swallowed as urllib3 swallows its own: a lookup → `{'attempts': ["getaddrinfo 'example.invalid'"]} != {'attempts': []}`; a bind to `0.0.0.0` → `{'attempts': ["bind ('0.0.0.0', 0)"]} != {'attempts': []}`. The guard alone: each of the six refused calls and three non-loopback binds is reported; binds to `127.0.0.1`, `127.8.9.10` and `::1` are not. The guard also passes on the start commit (`13 passed`): plain `doctor` never reached the network. |
| ac5: `lint-imports` has a contract that fails when `debate_core.domain` or `debate_core.application` imports `jinja2`, shown failing on a deliberate import | PASS | `uv run lint-imports` → `Contracts: 19 kept, 0 broken.` With `import jinja2` written to `debate_core/application/jinja2_boundary_probe.py` → `The template engine never reaches the domain or the application layer BROKEN`, `debate_core.application.jinja2_boundary_probe -> jinja2 (l.1)`, `18 kept, 1 broken`, exit 1. The same in `debate_core/domain/` → BROKEN, `debate_core.domain.jinja2_boundary_probe -> jinja2`. Both probes removed. `tests/architecture/test_import_contracts.py` (two new cases) → `55 passed`. |
| Node `replay-exit-doctor`: `uv run pytest packages/debate_core/tests/integrations/models packages/debate_cli/tests -k "replay or exit or doctor"` | PASS | Run as written, on the interpreter with a 115 s alarm → `443 passed in 25.63s`. |

### Mutants (working agreement 8)

The tree was committed before each batch. Each mutant was applied to one file and its covering test file was run with `-n0 -p no:randomly`, each run with a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`. Then the file was restored from a byte copy and compared. `git status --porcelain` was empty before and after every batch. No run errored at collection. The numbers in brackets are the PM's.

| # | Mutant | Caught by | Result |
|---|---|---|---|
| (1) | Replay compares raw fields again (`as_recorded=_parsed_request` removed) | the 6 optional-field tests and the 3 not-a-request tests | CAUGHT, `9 failed` |
| (2) | A changed recorded value replays: recorded `params` ignored | `…recorded_value_differs…[max-tokens, temperature, timeout, effort]`, `…differs_…outside_the_key…[other-parameters]`, `…parameter_the_cassette_lacks` | CAUGHT, `6 failed` |
| (2b) | Recorded task class ignored | `[task-class]`, `[another-task-class]` | CAUGHT, `2 failed` |
| (2c) | Recorded prompt variables ignored | `[variables]`, `[added-variable]` | CAUGHT, `2 failed` |
| (3) | `ModelAccessDenied` back to exit 3 | `test_a_refused_model_call_exits_as_a_domain_failure[no-credentials, not-granted]` | CAUGHT, `2 failed` |
| (3b) | The refused-call check removed entirely | the same test, all 3 cases | CAUGHT, `3 failed` |
| (4) | Throttling sent to exit 1 | `…a_retry_may_cure…[throttled]`, `test_provider_failures_are_retrieval_failures` | CAUGHT, `2 failed` |
| (5) | The routing check computed in plain doctor too (loads settings) | `test_plain_doctor_loads_no_settings_and_passes_with_a_bad_routing_file` | CAUGHT, `1 failed` |
| (5b) | A routing file that does not load does not fail doctor | the 3 key tests, the missing-file test, the person's view | CAUGHT, `5 failed` |
| (6) | The jinja2 contract removed from `pyproject.toml` | both new architecture cases, `test_every_configured_contract_is_proven_to_fail` | CAUGHT, `3 failed`; file restored byte-identical (`cmp`), `lint-imports` 19 kept |
| part (4) mutant 1 | The guard's `getaddrinfo` check removed | the doctor test **passes** with the planted lookup in place (`1 passed`); the guard's own `[getaddrinfo]` case catches it | CAUGHT by the self-test, `1 failed` |
| part (4) mutant 2 | The loopback allowance widened to any address | the doctor test **passes** with the planted `0.0.0.0` bind (`1 passed`); `[bind-any-ipv4]`, `[bind-any-ipv6]`, `[bind-a-name]` catch it | CAUGHT by the self-test, `3 failed` |

The two part (4) mutants show what the guard's self-tests are for. With either mutant in place, the plant it was meant to catch reaches plain `doctor` unnoticed. The self-tests are what fail.

### Checks before the report (agreement 10)

| Check | Result |
|---|---|
| Affected set: `uv run scripts/affected_tests.py` → `237 of 573 test files (41.4%) chosen … from 13 changed files` (measured before the `pyproject.toml` edit; 15 changed files after it, the same 237). It is wide because the root `conftest.py` imports `record_replay`. Run as `--run` runs it, with `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" $(cat list)` | **Stopped at the two-minute line**: alarm at 116 s, at 46%, every test so far passing. That projects to about 4 minutes, so it is left to the pull request's `ci` check under the PM's 2026-10-19 ruling, not handed over. `pgrep` found no orphaned workers. |
| Within two minutes instead: the node's command (above) → `443 passed`; the always-run list plus the changed CLI files (`tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`, `test_output.py`, `test_routing_file_checked_at_startup.py`, `test_installation.py`, `commands/test_doctor*.py`) | `561 passed in 23.35s` |
| `tests/architecture/test_import_contracts.py` after the contract | `55 passed in 8.76s` |
| `uv run ruff format --check .` / `uv run ruff check .` | `1607 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_core packages/debate_cli`; `uv run --frozen pyright` (CI's form) | `0 errors, 0 warnings, 0 informations` both |
| `uv run lint-imports` | `Contracts: 19 kept, 0 broken.` |
| `scripts/check_thin_handlers.py`, `scripts/check_command_blocks.py`, `scripts/docs_index.py --check-descriptions` | OK: 68 handlers within 25 statements; no `#` comments in 578 blocks; 58 documents described |
| `uv run scripts/validate_specs.py` | `OK: 494 files, 40 epics, 432 tasks, 22 releases` |

## Files changed

- **`debate_core.integrations.models`**
  - `record_replay.py`: a structured cassette's recorded request is compared parsed. A request that does not parse is a `FixtureFileError`.
  - `routing_policy.py`: `RoutingFileFinding` and `check_routing_file`.
- **`debate_cli`**
  - `exit_codes.py`: `REFUSED_MODEL_CALLS` exit 1.
  - `container.py`: `routing_file_finding()`, a plain method rather than a service.
  - `commands/doctor.py`: `--routing-file`, its row and failure, and the "reaches no network" paragraph.
- **Tests**
  - `packages/debate_core/tests/integrations/models/test_record_replay.py`.
  - `packages/debate_cli/tests/test_output.py`.
  - `packages/debate_cli/tests/commands/test_doctor_routing_file.py` and `test_plain_doctor_reaches_no_network.py` (new).
  - `tests/architecture/test_import_contracts.py` (Deviation 2).
- **Docs**
  - `tests/fixtures/model_cassettes/README.md`: replay's comparison.
  - `docs/runbooks/bedrock-access.md`: `doctor --routing-file`, and a refused model call's exit code.
- **`pyproject.toml`**: the jinja2 contract (Deviation 2).
- **The spec**: phase only.

## Deviations from the spec

1. **ac4 superseded by the PM's ruling of 2026-10-30, option A.**
   - **What spec item (4) assumed.** The socket plain `doctor` opens is not a network call. Doctor's integration check (v1-e01-t22) imports every wired adapter. Eight import boto3 (`integrations.s3` and three submodules, `cloudwatch_audit`, `cognito`, `secrets_manager`, `sns`), and `html_extractor` reaches urllib3 through its extraction libraries. On import, urllib3 binds an AF_INET6 socket to `::1` port 0 to learn whether the machine has IPv6. It sends nothing and looks nothing up, and it swallows the failure. urllib3 has no switch for it.
   - **The ruling.** Keep the real import check, because it is what catches an adapter installed but broken on import. Prove the contract the installer and `validate-dev` depend on instead: no connect, `connect_ex`, `sendto`, `getaddrinfo`, `gethostbyname` or `gethostbyname_ex`, and no bind except to loopback (127.0.0.0/8, `::1`). Show it red on a planted lookup and on a planted `0.0.0.0` bind, and green on the branch.
   - **Done.** The strict pytest-socket guard fails on both the start commit and the branch, for that one reason (ac4's row). The PM's next batch amends (4) and ac4 to "plain doctor makes no network call and binds nothing but loopback, shown by a guard that fails on either". The spec was not edited here. Option C, running the check where the guard cannot see it, was ruled out.
2. **Edits outside `constraints.packages`, by the PM's allowance** for the jinja2 contract. The operator confirmed both files on 2026-10-30, and the PM repeated it in the ruling.
   - `pyproject.toml` (`[tool.importlinter]`) holds every contract.
   - `tests/architecture/test_import_contracts.py`, whose `test_every_configured_contract_is_proven_to_fail` fails on a contract with no case.
   - The `pyproject.toml` change was committed last (`9c4d9da`), after the affected set was measured.

## Decisions and assumptions

1. **Replay: which comparison, and what a bad recorded request is.**
   - Only the `generate_structured` comparison parses; `embed` and `rerank` record plain lists, which have no optional fields, so they still compare as JSON.
   - A recorded request that does not parse is a `FixtureFileError` ("its recorded request is not valid"), not an unrecorded call. That covers a parameter this build does not know (a field since removed), an invalid value, or a scoring task class. Under `extra="forbid"` such a cassette cannot mean any call, and the fix is to record it again.
   - The fake router's fixtures under `tests/fixtures/model_outputs/` are keyed without parameters and compare nothing else, so they were not touched.
2. **Exit codes: a named list.** `REFUSED_MODEL_CALLS` is a named tuple, like `RETRYABLE_STORE_FAILURES`, and it is checked before the provider rule. A plain `ProviderError` and every other provider failure stay exit 3. An expired model session (`ModelAccessDenied` with the login hint) exits 1 as well, because the spec names the class: a retry without a login does not cure it.
3. **The PM's question: what the landscape command and the weekly run do with exit 3.**
   - **Landscape.** The model stage (`landscape_model_stage.py`) catches every `ProviderError`, throttling included, and the run ends with `ModelStageInterrupted`, a plain `DomainError`. So a model failure inside the stage already exits 1, before and after this task. Nothing there assumed the old behaviour, and the landscape command was not touched. One consequence the PM may want to know before 2026-11-06: a throttled classification run also exits 1 there, not 3. See Follow-up work.
   - **Weekly run.** It makes no model calls. `run-caselist-sync.sh` never reads the exit code, and launchd does not re-run on any code. Its recorded failure codes go through `exit_code_for_failure_codes`, where `MODEL_ACCESS_DENIED` and `MODEL_REQUEST_REJECTED` were never retryable.
4. **The routing check is not a service.** `routing_file_finding()` builds and keeps nothing, so it is not in `SERVICE_NAMES`, and the doctor `services` list pinned in `test_app.py` is unchanged. The container's settings already validate the routing file (`validating_routing`), so the check catches the `RoutingConfigError` that loading them raises and reports it as found. A file that loads is read once more to list its routes. With `--routing-file --evidence-profiles` and a bad file, the evidence check's own settings load still raises the same `ROUTING_CONFIG_ERROR` (exit 1), as it did before this task.
5. **The guard runs in a fresh interpreter**, because urllib3 probes once per process. In the suite, whichever test imports boto3 first takes the probe, so an in-process guard's verdict would depend on test order. The guard records each refusal as well as raising it, because urllib3 swallows the error. The doctor test also checks that urllib3 was imported, so a green run means the probe ran and was allowed, not that it never happened.

## Operator follow-ups

1. **Sync before the PR.** Dev moved after this branch started (`8e11f34`, PM batch 2026-10-30c). It changed no file this task changed, and no shared test ground. `scripts/task sync` pushes, so it is yours. Running it is not required for this branch to be correct.

## Follow-up work

1. **Landscape (v1-e40 or v1-e32, the PM decides):** a throttled model stage exits 1. `ModelStageInterrupted` wraps every `ProviderError`, so a run stopped by throttling on 2026-11-06 reads as a verdict, not a "try again later". The fix would be to keep the cause's class, or exit 3 when the cause is on `RETRYABLE_PROVIDER_FAILURES`. Out of scope: the landscape command was not to be touched.
2. **`ops/launchd/install.sh --check-launchd` (v1-e05 or v1-e34):** it could add `--routing-file` to the `doctor --evidence-profiles --search-index` it runs, once a model stage runs under launchd. Not needed today, because the weekly run calls no model.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
