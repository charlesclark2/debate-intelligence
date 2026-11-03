# Session report: v1-e39-t23-uvicorn-factory-in-the-composition-root

| | |
|---|---|
| Task | `v1-e39-t23-uvicorn-factory-in-the-composition-root` — uvicorn's app factory lives in the composition root, so app.py stops reaching every adapter |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t23-uvicorn-factory-in-the-composition-root.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t23-uvicorn-factory-in-the-composition-root.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t23-uvicorn-factory-in-the-composition-root` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

uvicorn now runs `debate_api.container:create_app_from_environment`. That factory configures the app
log, then builds the function's services from its environment, then returns `create_app(services)`.
`create_app` requires its services and no longer imports the container. For the parser-only merge
`387c961`, the selector now picks **10 API test files instead of 25** (271 → 256 test files in all).
The API suite collects the same 1,066 ids as before plus the two new tests (1,068). All 1,068 pass,
and so do the 27 slow browser tests.

**The Goal stays `InProgress`, and the PM should look at this first.** ac1 also asks that "the
image's smoke check passes". I did not build the image. Docker is running, but this Mac has no cached
Lambda base image, and the image's `pip install` layer would have to reach PyPI. So the operator's
next `scripts/tub_deploy.sh dev` is that check: its `/healthz` step, through CloudFront. That
criterion is NOT RUN. In its place I ran an offline check of the same entry string: uvicorn's own
loader reads the Dockerfile's `ENTRYPOINT`, with Parameter Store stubbed and every socket connect
refused, and `/healthz` answers `200`, `private, no-store`, `{"status":"ok"}`. Against the old entry
point the load fails with `create_app() missing 1 required positional argument: 'services'`.

The affected set (82 files) reached the 115 s limit at 92% (3,338 passed, none failed). It is left to
the pull request's CI, as agreement 10 says. Every test directory this change touches, and the
always-run list, passed within the limit.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `uvicorn-factory-in-the-composition-root` (uvicorn factory) | Done | `0ae86ba`, `e9c9674`. The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the image's entrypoint names the composition root's factory | PASS | `packages/debate_api/Dockerfile:46`: `ENTRYPOINT ["python3", "-m", "uvicorn", "debate_api.container:create_app_from_environment", "--factory", ...]`. `test_the_images_entrypoint_is_the_composition_roots_factory_and_the_app_needs_its_services` (in `test_session_lifetimes.py`) resolves that string with `uvicorn.importer.import_from_string` and checks that the result `is container.create_app_from_environment` and takes no parameters. `test_tub_deploy.py::test_uvicorn_serves_the_app_on_the_adapters_port_with_no_access_log` pins the string. |
| ac1: `create_app` requires its services | PASS | `app.py:51`: `def create_app(services: PilotServices) -> FastAPI`. app.py has no container import anywhere and no `os` import. The same test checks `inspect.signature(create_app).parameters["services"].default is inspect.Parameter.empty`. `test_auth_pages_and_script.py::test_the_app_module_never_imports_the_composition_root` reads app.py's imports at any depth and finds none ending in `container`. |
| ac1: t20's measurement selects fewer API files for a parser change | PASS | See [The measurement](#the-measurement). `affected_tests.py --diff 387c961 --graph <rev>`: before (`1ec099a`) **25** API files, after (`e9c9674`) **10**. |
| ac1: with the collected count unchanged | PASS | `.venv/bin/python -m pytest packages/debate_api/tests --collect-only -q -p no:randomly -p no:cacheprovider`, ids sorted under `LC_ALL=C`. **Default selection:** 1,066 before, 1,068 after. **With `-m "slow or live or not slow"`:** 1,093 before, 1,095 after. `comm`: **0 lost**. The 2 added are the new tests, `test_the_app_module_never_imports_the_composition_root` and `test_the_images_entrypoint_is_the_composition_roots_factory_and_the_app_needs_its_services`. |
| ac1: the image's smoke check passes | **NOT RUN** | The image was not built (no offline build: see the Summary). The operator's `scripts/tub_deploy.sh dev` is the check: it builds the image and then checks `/healthz` through CloudFront. **What ran in its place, offline:** `entrypoint_smoke.py` (scratchpad, below). It reads the Dockerfile's `ENTRYPOINT`, patches `build_ssm_client` and `read_secure_parameter` to synthetic values and `socket.socket.connect` to raise, then calls `uvicorn.Config(<app string>, factory=True).load()` and GETs `/healthz` through Starlette's test client. On the new Dockerfile: `entrypoint: debate_api.container:create_app_from_environment factory: True`, `healthz: 200 private, no-store {"status":"ok"}`, `root handlers: ['_AppLogHandler']`. On the base commit's Dockerfile: `ERROR: Error loading ASGI app factory: create_app() missing 1 required positional argument: 'services'`. |
| Node `uvicorn-factory-in-the-composition-root`: `uv run pytest packages/debate_api/tests` | PASS | `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_api/tests -p no:cacheprovider -q` → `1068 passed in 9.61s`. The same interpreter and arguments as `uv run pytest`, with the time limit on the interpreter. |
| PM: no behaviour change in the running pilot (forbidden) | PASS, except the image itself (above) | **Routes, headers and the gate:** `git diff 1ec099a HEAD -- packages/debate_api/src` changes only `app.py` (the docstring, the signature and the removed no-services branch), `container.py` (the new factory, and its docstring and imports) and a docstring in `app_logging.py`. Everything `create_app` does after building its services (the state, the routes, the error handlers, the gate, `private_no_store`) is byte-for-byte as before. **Logging:** the factory calls `configure_app_logging()` before `build_pilot_services`, as the old branch did. The logging test now also checks that order. **Services:** `build_pilot_services` is unchanged. **The suite:** all 1,066 existing ids are present and pass, and so do the 27 slow browser tests (`.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_api/tests/browser -m slow -n 4 -p no:cacheprovider -q` → `27 passed in 13.69s`). |
| PM: t10's logging test keeps both halves, red against the factory without the call | PASS | `test_the_functions_app_configures_it_and_a_tests_own_app_does_not` still builds a test's own app (`create_app(world.services)`, no handler) and then the function's app, now through `debate_api.container.create_app_from_environment()` with `build_pilot_services` patched (one `_AppLogHandler`, the holder at `INFO`). It now also records, inside the patched builder, whether the handler is there yet. **Red run** (mutant 1): `1 failed` at `test_app_logging.py:105: AssertionError: the log is configured before the services are built`. With that new line taken out as well, the original half fails on its own: `test_app_logging.py:105: ValueError: not enough values to unpack (expected 1, got 0)`, the `[handler] = ours()` line. |
| PM: mutants (factory without logging; `create_app` keeping a default; Dockerfile on the old entry point) | PASS (all caught) | Under [Mutants](#mutants). |
| Forbidden: network or AWS access in any test | PASS | The new tests read the Dockerfile and app.py and import the two modules; they build no client. The logging test patches `build_pilot_services`, and the placeholder-keys test patches the SSM client (as before). |

### The measurement

Run as in v1-e39-t20's report, on its parser-only merge `387c961` (`v1-e31-t19-remaining-cite-shapes`,
22 changed files). Each tree uses its own `affected_tests.py`, which this task does not change.
"API files" means the selected files under `packages/debate_api/tests/` (27 test files today).

```bash
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --diff 387c961 --graph 1ec099a
```

```bash
.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python scripts/affected_tests.py --diff 387c961 --graph e9c9674
```

| Tree | Test files | API files |
|---|---|---|
| Before, `1ec099a` (branch start, today's dev; measured before any edit, with `--graph HEAD`) | 271 of 603 | **25** |
| After, `e9c9674` | 256 of 603 | **10** |

t20 predicted 8 with the edge removed. The other two files arrived with v1-e39-t10 after t20 measured:
`test_app_logging.py` imports the container (it has to, to call the factory) and
`browser/test_tub_dev_journey.py` uses `download_world`. Each of the 10, from `--explain`:

- `test_card_download.py` and `browser/test_tub_dev_journey.py` use `download_world`.
  `test_auth_authorization_matrix.py`, `test_exposure.py` and `browser/test_search_pages_in_chromium.py`
  use `every_surface_world`. Both worlds need the parser.
- `test_card_download_limits.py` imports the parser, and `test_card_download_image.py` names it.
- `test_app_logging.py` and `test_session_lifetimes.py` import `debate_api.container`.
- `test_landscape_image.py` reads every Python file.

**My first after-run gave 11.** `test_auth_pages_and_script.py` was in it, with "reads the Python
source of the files it walks". My new import check used `ast.walk(` next to `ast.parse(`, and the
selector's `DIRECTORY_WALK` pattern (`\b(?:rglob|glob|iterdir|walk)\(`) reads that as a directory walk.
`e9c9674` uses an `ast.NodeVisitor` instead. Follow-up 1 is about the pattern.

### Mutants

Each mutant was made on the committed tree and run against the four files that name the entry point:
`test_app_logging.py`, `test_session_lifetimes.py`, `test_auth_pages_and_script.py` and
`tests/scripts/test_tub_deploy.py`. The command was `pytest <those> -q -p no:randomly --tb=line -n 0`
under `hard_stop.py 115`. Each mutant was then restored with `git checkout HEAD -- <file>`, and
`git status` was clean after each. None of these tests uses Hypothesis. Each run still had a new,
empty `HYPOTHESIS_STORAGE_DIRECTORY` (agreement 8). Every catch is an assertion, not a crash.

| Mutant | Result | Caught by (line) |
|---|---|---|
| 1. The factory without `configure_app_logging()` | `1 failed, 79 passed` | `test_app_logging.py::test_the_functions_app_configures_it_and_a_tests_own_app_does_not`, `:105 AssertionError: the log is configured before the services are built` |
| 1b. The factory configuring the log after it builds the services | `1 failed, 79 passed` | the same test, the same line |
| 2. `create_app` keeping its default: the pre-task body restored (`services: PilotServices \| None = None`, the lazy `from debate_api.container import build_pilot_services`, `configure_app_logging()`) | `2 failed, 78 passed` | `test_session_lifetimes.py::test_the_images_entrypoint_is_the_composition_roots_factory_and_the_app_needs_its_services`, `:315 assert None is <class 'inspect._empty'>`; `test_auth_pages_and_script.py::test_the_app_module_never_imports_the_composition_root`, `:186 AssertionError: assert not {'debate_api.container'}` |
| 2b. A bare default (`services: PilotServices \| None = None` plus `assert services is not None`, no import) | `1 failed, 79 passed` | `test_session_lifetimes.py::test_the_images_entrypoint_…`, `:315` |
| 3. The Dockerfile left on `"debate_api.app:create_app", "--factory"` | `2 failed, 78 passed` | `test_session_lifetimes.py::test_the_images_entrypoint_…`, `:313 assert <function create_app …> is <function create_app_from_environment …>`; `tests/scripts/test_tub_deploy.py::test_uvicorn_serves_the_app_on_the_adapters_port_with_no_access_log`, `:559` |

What mutant 3 would have shipped: the offline entry-point check above shows uvicorn refusing to load
the old entry point. The function would never pass the Web Adapter's readiness check.

### Every place that named the old entry point

`git grep -n -e create_app -e '--factory'`, without `docs/session-reports` and `plan_specs`.
`debate_cli`'s own `create_app` (the Typer app) is a different function. Its hits in
`packages/debate_cli`, `tests/integration/test_fetch_cli.py` and `tests/smoke/test_*.py`, and the
mention in `tests/smoke/README.md:262`, are left out. Before this task:

| Hit | Now |
|---|---|
| `packages/debate_api/Dockerfile:46`, the `ENTRYPOINT` | `debate_api.container:create_app_from_environment` |
| `packages/debate_api/README.md:12` | the container holds uvicorn's factory; `create_app` builds over the services it is given; the module table's `container` row says so too |
| `packages/debate_api/src/debate_api/app.py:10`, the module docstring | names the container's factory, and says app.py never imports the container |
| `packages/debate_api/src/debate_api/app.py:40, 51`, `__all__` and the definition | the definition requires `services` |
| `packages/debate_api/src/debate_api/app_logging.py:23` | "Only uvicorn's factory, `create_app_from_environment`, calls this" |
| `packages/debate_api/src/debate_api/state.py:3, 128` | unchanged: still true (a composition root hands `create_app` its services) |
| `packages/debate_api/tests/conftest.py:69, 1170` | unchanged: a test's own app, `create_app(self.services)` |
| `packages/debate_api/tests/test_app_logging.py:21, 94, 98` | the function's half calls `create_app_from_environment()`; the test's own half still calls `create_app(world.services)` |
| `packages/debate_api/tests/test_auth_pages_and_script.py:152` | the docstring names the container's factory; the new import check is beside it |
| `packages/debate_api/tests/test_session_lifetimes.py:265, 267, 289` | the placeholder-keys test calls `container.create_app_from_environment()`; the new entry-point test follows it |
| `tests/scripts/test_tub_deploy.py:559` | pins the new string |
| `tests/scripts/test_affected_tests_planted_breaks.py:484` | unchanged: a recorded pytest traceback (`CONFTEST_IMPORT_ERROR`), whose line still imports `create_app` from `debate_api.app` |

`ops/` and `docs/runbooks/` name neither `create_app` nor `--factory`.

## Files changed

- `packages/debate_api/src/debate_api/container.py`: `create_app_from_environment()`, uvicorn's
  factory, and a docstring paragraph on why it is here.
- `packages/debate_api/src/debate_api/app.py`: `create_app(services)` with no default, no container
  import, no `os` and no logging call. The module docstring is updated.
- `packages/debate_api/src/debate_api/app_logging.py`: the docstring names the factory.
- `packages/debate_api/Dockerfile`, `packages/debate_api/README.md`, `tests/scripts/test_tub_deploy.py`:
  the new entry point.
- `packages/debate_api/tests/test_app_logging.py`: the function's half goes through the factory and
  checks that the log is configured before the services are built.
- `packages/debate_api/tests/test_session_lifetimes.py`: the placeholder-keys test goes through the
  factory. A new test checks the image's entry point, `create_app`'s missing default, and that
  neither module builds an app at import.
- `packages/debate_api/tests/test_auth_pages_and_script.py`: the docstring, and a new test that
  app.py imports no container module at any depth.
- This report.

## Deviations from the spec

1. **ac1's "the image's smoke check passes" is NOT RUN, so the Goal stays `InProgress`.** The image
   cannot be built offline here: there is no cached `public.ecr.aws/lambda/python` image, and the
   `pip install` layer installs from PyPI. That layer reruns because the wheels it follows change.
   Under the PM's brief, the operator's deploy (`scripts/tub_deploy.sh dev`, which v1-e39-t10's held
   dev deploy will run with v1-e39-t24) is the check. The offline loader check above covers the part
   of it this task changed: the entry string, uvicorn's `--factory` call, start-up and `/healthz`.
   Once that deploy's `/healthz` answers `{"status":"ok"}`, the PM can set the phase.

## Decisions and assumptions

1. **The factory is in `debate_api.container`, not in a module beside it.** The container is already
   the composition root and the only module that builds an adapter. A separate module would have to
   import the container anyway, so it would add a file and no selection gain. The container now
   imports `debate_api.app` and `debate_api.app_logging`, and the reverse edge is gone, so there is no
   cycle. `container.py`'s docstring says why the factory lives there.
2. **The name is `create_app_from_environment`**, as t20's PM question suggested. It takes no
   arguments, as uvicorn's `--factory` calls it, and reads `os.environ`. That is the same environment
   the old branch read.
3. **"t32's measurement" (ac1) is read as the PM's brief reads it:** t20's command, on the one
   parser-only merge `387c961`. I did not re-run all 41 of t32's commits. The edge only made a
   difference in that merge (t20's table, last column), and 41 runs at about 14 s each would take far
   longer than two minutes.
4. **The new entry-point test is in `test_session_lifetimes.py`, beside the placeholder-keys test.**
   That file already imports the container. The other natural place, `test_auth_pages_and_script.py`,
   does not import it, and a container import there would have added it back to the parser
   selection. For the same reason, the import check in that file reads app.py's source rather than
   importing the container.
5. **The added ordering check in the logging test.** The PM's brief says the factory calls
   `configure_app_logging()` "BEFORE building them". The old test could not tell the two orders apart
   (mutant 1b). One recorded boolean inside the patched builder can, and both of the test's original
   halves are kept as they were.
6. **Contracts: one could now be made stricter, and I left it alone.** After this change, no module in
   `debate_api` imports `debate_api.container` except the container itself. A `forbidden` contract
   that keeps `debate_api.container` out of `debate_api.app`, `routes`, `access` and the pages would
   be kept today. It would turn the new import test into a lint-imports rule. The brief said not to
   change contracts. `lint-imports`: 19 kept, 0 broken.
7. **The process-wide logging state** (agreement 10): both the placeholder-keys test and the logging
   test still call `configure_app_logging()` through the factory, as they called it through
   `create_app()` before. The logging test restores the root logger through `bare_logging`. The
   placeholder test never did, before or after; this task neither adds nor removes that.

## Commands run before the report

- **Affected set:** `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run`
  → `82 of 603 test files (13.6%) chosen in 12.6 s from 11 changed files`. The run was stopped at its
  115-second limit at 92%, with 3,338 passed and no failure or error printed (`hard_stop: stopped the
  run at its 115-second limit`, exit 124). Under agreement 10 (over about two minutes), the full
  affected set is left to the pull request's `ci` check. Within the limit I ran:
  - **the changed areas and the always-run list:** the 37 selected files under `tests/scripts`,
    `tests/docs`, `tests/architecture` and `tests/specs`, plus the CLI's `test_app.py`,
    `test_help_rendering.py` and `test_container_factories.py`. Command:
    `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest <those 37> -n auto -m "not slow and not live" -p no:cacheprovider -q`
    → `1726 passed in 60.32s`;
  - **the API tests** → `1068 passed in 9.61s`, and the slow browser tests → `27 passed in 13.69s`
    (above).
- `.venv/bin/ruff format --check .` → `1678 files already formatted`. `.venv/bin/ruff check .` → `All checks passed!`
- `.venv/bin/pyright packages/debate_api` → `0 errors, 0 warnings, 0 informations`
- `.venv/bin/lint-imports` → `Contracts: 19 kept, 0 broken.` `.venv/bin/python scripts/check_thin_handlers.py` → `OK: 68 CLI command and API route handlers within 25 statements`
- `uv run scripts/validate_specs.py` → `OK: 530 files, 41 epics, 467 tasks, 22 releases`
- `.venv/bin/python scripts/check_command_blocks.py --base origin/dev` → ``OK: no `#` comments in 627 shell code blocks in 201 Markdown files (1 session reports changed since origin/dev)``, this report included. `tests/docs` and `test_check_command_blocks.py` → `256 passed in 10.10s`.

Scratchpad files, kept for the review: `entrypoint_smoke.py`, `before_selection.txt`,
`after_selection.txt`, `before_ids*.txt`, `after_ids*.txt` and `mutant_*.txt`. They are in
`/private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e39-t23-uvicorn-factory-in-the-composition-root/78f4bad5-efde-4251-bc40-78427799cfd8/scratchpad/`.

## Operator follow-ups

1. **The image's smoke check is the next dev deploy** (ac1). The operator is already holding
   v1-e39-t10's dev deploy for this task and v1-e39-t24. That deploy, from a worktree on `dev` after
   both merge, follows `docs/runbooks/evidence-search.md`'s deploy steps; the runbook is unchanged by
   this task. Success: the script's last step, `Checking <origin>/healthz through CloudFront`, passes.
   In the function's log group `debate-dev-tub-app`, uvicorn's start-up lines appear and no
   `Error loading ASGI app factory` does. Once it passes, the Goal can be set to `Succeeded` with
   `uv run scripts/task_helper.py set-phase v1-e39-t23-uvicorn-factory-in-the-composition-root Succeeded`.

## Follow-up work

1. **`affected_tests.py` reads `ast.walk(` as a directory walk** (E41, the selector). `DIRECTORY_WALK`
   is `\b(?:rglob|glob|iterdir|walk)\(`, so a test that parses one named file and walks its tree is
   selected by every Python change. I worked around it here with a visitor. `test_card_download_image.py`
   has the same pattern, and is selected for that reason by any Python change, the parser's included.
   Matching `os.walk(` / `Path.walk(` / `.walk(` with no `ast.` before it would narrow it. The rule
   fails toward more tests, so this is a gain, not a bug.
2. **A lint-imports contract for the container's one-way edge** (Decision 6), if the PM wants the
   import test as a contract.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-01

**Notes:**

The edge is gone. A parser-only merge now selects 10 API files instead of 25, and no id was lost.
1. **ac1, the session's halves: pass.** I read the code:
   * `create_app_from_environment` calls `configure_app_logging()` and then
     `create_app(build_pilot_services(os.environ))`;
   * the Dockerfile's `ENTRYPOINT` names it with `--factory`;
   * app.py imports nothing from the container, and `create_app` has no default.

   The collected ids are 1,066 → 1,068 with `comm` showing 0 lost; the two added are the new tests.
   The measurement uses t20's own command on `387c961`: 25 → 10. You explained the two files over
   t20's predicted 8 (both arrived with v1-e39-t10), and the eleventh from your first run, which was
   a selector quirk you worked around and filed rather than hid.
2. **The red run and the mutants.** The added ordering check is the right strengthening: the old test
   could not tell logging-after-build from logging-before (mutant 1b). Every mutant failed at an
   assertion. Mutant 3's offline loader check shows exactly what it would have shipped: a function
   that never passes the Web Adapter's readiness check.
3. **Deviation 1: accepted.** The image's smoke check is the held dev deploy's `/healthz`. The offline
   loader check, the real entry string through uvicorn's own `Config.load()` with Parameter Store
   stubbed and sockets refused, covers what this task changed. The Goal stays `InProgress` until that
   deploy passes. The PM records it and sets the phase in a batch.
4. **Decisions accepted:**
   * the factory in the container;
   * the name;
   * t20's one merge as "the measurement";
   * the entry-point test placed where it adds no selection edge;
   * contracts left alone, as the brief said.
5. **Follow-ups:** one p3 E41 task in the next PM batch, holding both.
   * **1:** the selector's directory-walk pattern stops matching `ast.walk(`, so a test that walks one
     parsed file's tree is no longer selected by every Python change. `test_card_download_image.py`
     is the other known case.
   * **2:** a lint-imports `forbidden` contract keeping `debate_api.container` out of every other
     `debate_api` module. It turns the new import test into a rule, and it is cheap while the edge is
     one-way.
6. **Closing checks:** the affected set stopped at 92% at its limit (3,338 passed, none failed) and is
   left to the PR's `ci` under agreement 10. The changed areas and the always-run list (1,726), the
   API suite (1,068), the browser suite (27), ruff, pyright, lint-imports, thin handlers, the specs
   and the doc checks are clean.
7. **Merge:** `--partial` once `ci` is green. Then the held dev pilot deploy carries this task,
   v1-e39-t24 and v1-e39-t10's logging. Its `/healthz` through CloudFront closes this task's ac1, and
   v1-e39-t10's journey follows.

## Operator records (recorded by the PM, 2026-10-31)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac1: the image's smoke check passes | NOT RUN | PASS | 2026-10-31, `scripts/tub_deploy.sh dev` from the `tub-deploy-dev` worktree at `origin/dev` `66182c0` (this task's merge, with v1-e39-t24 and v1-e39-t10), as `DebateDevTubDeployer`: exit 0, `{"status":"ok"}` from `/healthz` through CloudFront, the function on `debate-dev-tub@sha256:d807ac0c…`. In `debate-dev-tub-app`, no `Error loading ASGI app factory` in the hour after; the first cold start's `Init Duration: 6589.41 ms` (a new image, not yet cached; earlier inits were about 2 s) |

Every criterion passes, so the Goal is `Succeeded`.
