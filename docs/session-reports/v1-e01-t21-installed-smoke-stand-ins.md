# Session report: v1-e01-t21-installed-smoke-stand-ins

| | |
|---|---|
| Task | `v1-e01-t21-installed-smoke-stand-ins` — The storage and OpenCaselist smoke checks run against the installed build |
| Spec | [`plan_specs/v1/e01-repo-foundation/t21-installed-smoke-stand-ins.yaml`](../../plan_specs/v1/e01-repo-foundation/t21-installed-smoke-stand-ins.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t21-installed-smoke-stand-ins` |
| Session status | COMPLETE. The Goal is `Succeeded`, as the brief asked. The validate-dev parts of ac1 and ac4 were rehearsed locally against an installed build; the first real run is Operator follow-up 1 |

## Summary

The `caselist publish`, `remove`, `pull` and `runs` smoke checks now run the installed build. They
reach two **stand-ins** over loopback, each a server in a process of its own on `127.0.0.1` and an
ephemeral port:

* **S3:** moto in server mode, reached through a new dev-only setting, `storage.s3.endpoint_url`.
* **OpenCaselist:** a small https API and file host, serving synthetic responses and reached
  through `caselist.api_base_url`.

Nothing patches the build.

The network guard now lets a check connect only to the stand-in addresses it declared. Every other
check is refused loopback, as before, and the refusal is logged. Against a locally built,
`install_channel.sh`-installed pre-release, the recorded tier is **85 passed in 96 s** (load 15 to
23), or **84 passed in 64 s** at load 3 to 5. t10 recorded 27 checks in 8.5 s.

**Four things to look at first.**

1. **Prod now refuses an endpoint override it used to accept (Deviation 2).** Today a prod
   installation accepts any https `caselist.api_base_url`. The red run shows `DID NOT RAISE`. The
   spec forbids an endpoint override that prod accepts, and the OpenCaselist stand-in depends on
   this setting, so prod now refuses anything but the documented API, naming the setting. The new S3
   endpoint is dev only. Prod also builds its S3 and STS clients with botocore's own
   `AWS_ENDPOINT_URL*` and `endpoint_url` settings ignored, so the brief's point 1 does not rest on
   the variable being unset. The installed build itself shows this: in prod, with those variables
   aimed at the stand-in, the stand-in gets nothing and the guard logs the attempt to reach
   `amazonaws.com`.
2. **Not every in-process pull check could move (ac1, Deviation 4).** 14 of the pull module's
   checks replace part of the CLI, not the world: an expired session raised inside the adapter,
   botocore's own client-side exceptions, the notifier, the clock. They are kept, unchanged, in
   `ci`, as `test_caselist_pull_in_process.py`. The four named modules are no longer `in_process`.
   Every remove check moved, t16's four included, with all their assertions.
3. **`ci`'s test job now runs in five parts (Deviation 3).** The converted checks cost about 66
   more worker-seconds than the in-process ones, which is about 16 s per part. Part 1's pytest step
   was already 112 to 118 s on the three latest `ci` runs. Working agreement 1's remedy is one more
   part, so `ci.yml` changed by one line.
4. **Two dev dependencies are added, and no runtime dependency changes (Deviation 1).** `flask` and
   `flask-cors` are moto's server mode. moto's own `server` extra would add cfn-lint, docker and a
   dozen more packages.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `stand-ins`: Loopback stand-ins and the installed-binary checks | Done | The two stand-ins as fixtures; the guard's scoped loopback allowance; the four converted modules; the endpoint settings and prod refusals. Its criterion passes: `111 passed`. |

## Acceptance criteria

The commit ids are those on this branch, from start commit `6cabc6d`. The red runs are at
`ecbd7f8`, `ac33bbc` and `daa8440` (ac2), and before `7a6a992` (ac3). Their outputs are quoted
below.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1**: `caselist publish`, `remove`, `pull` and `runs` each have a recorded smoke check that runs the installed binary through `installed_cli` and passes in validate-dev's smoke job; none of the four is `in_process` any more; the report says what became of the in-process versions | **PASS** (against a locally installed pre-release; the first validate-dev run is follow-up 1) | `git grep -n in_process` on the four modules finds only prose. The installed build was stamped and built from `eb6b0fd` exactly as `dev-prerelease.yml` does, and installed with `sh scripts/install_channel.sh --no-path-warning --dir <dist> v0.1.0-dev.9021` into scratch `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` (7 s). Its packages are identical to `HEAD`'s. The recorded tier was then run as validate-dev runs it: `DEBATE_SMOKE_BIN=…/bin/debate-research DEBATE_SMOKE_EXPECT_SHA=eb6b0fd… DEBATE_SMOKE_EXPECT_TAG=v0.1.0-dev.9021 uv run --frozen pytest tests/smoke -m "not live and not in_process" -n 4 --no-cov -p no:cacheprovider -rfEs` → `85 passed in 96.41s`, nothing skipped. That includes publish (2 checks), remove (31), pull (9) and runs (1). The same environment with `-m "not live"` stops with exit 4, naming each check in `test_caselist_pull_in_process.py`, so the harness still refuses an in-process check against a build. **What became of each in-process version** is under "What became of the in-process checks" below. |
| **ac2**: the guard permits loopback only for a check that uses a stand-in fixture; a check without one that connects to 127.0.0.1 is refused and logged, and a check with one that tries a non-loopback address is refused and logged; both shown failing first | **PASS** | Four checks in `test_network_guard.py`, run on the build under test. Three red runs, each against a naive guard, are under "ac2, red then green" below. **Green:** `uv run --frozen pytest -n 0 tests/smoke/test_network_guard.py tests/smoke/test_smoke_harness.py` → `17 passed`. Against the installed build, they pass inside the 85. **Mutation:** G1 to G4 below are all caught. |
| **ac3**: if the CLI needed a new endpoint setting, a prod environment refuses it with a message naming the setting, shown by test, and `config show` reports it | **PASS** | A new setting was needed for S3 (`storage.s3.endpoint_url`). OpenCaselist uses the existing `caselist.api_base_url`, which prod now refuses unless it is the documented API. **Red first:** `uv run --frozen pytest packages/debate_core/tests/application/test_settings_stand_in_endpoints.py packages/debate_core/tests/integrations/s3/test_s3_client_endpoints.py` → `20 failed, 2 passed`. The reasons: `Extra inputs are not permitted` (no setting), `build_s3_client() got an unexpected keyword argument 'endpoint_url'`, and for prod's OpenCaselist endpoint `Failed: DID NOT RAISE ConfigurationError`. **Green:** the same → `22 passed` (with the existing settings and OpenCaselist client tests, `165 passed`). **On the build**, `test_cli_smoke.py`: `test_config_show_reports_the_stand_in_endpoints_and_where_each_came_from` (value and `env:DEBATE_…` source for both; `None`/`default` unset), and `test_prod_refuses_each_stand_in_endpoint_with_a_message_naming_the_setting`. The second runs both settings through `config show` and `caselist status`: exit 1, `CONFIGURATION_ERROR`, `details == {"field": <setting>, "source": "env:<variable>"}`, and a message naming the setting and its variable. `test_caselist_publish_smoke.py::test_prod_sends_the_evidence_store_to_aws_whatever_endpoint_botocore_is_given` covers botocore's route. **Mutation:** P1 to P5 below are all caught. |
| **ac4**: the recorded tier still runs in under 5 minutes in validate-dev, every stand-in binds an ephemeral port and is torn down, and tests/smoke/README.md says how a later check adds a stand-in | **PASS** (timed locally against the installed build; validate-dev's own time is follow-up 1) | **Time:** `85 passed in 96.41s` at load 15 to 23, and `84 passed in 64.44s` at load 3 to 5, before the last guard check was added. Both used 4 workers, as on validate-dev's 4-vCPU runner. On 11 workers the node's command takes `78.38s`. **Ephemeral and torn down:** `test_stand_ins.py`. Two S3 stand-ins at once get two ports, both in the system's ephemeral range (read from `sysctl` or `/proc`). The OpenCaselist stand-in binds two. A stopped one of each has exited and its ports refuse connections. `conftest.py`'s `_no_stand_in_outlives_its_check` fails any check after which a stand-in is still running. **README:** "How a smoke check reaches S3 and OpenCaselist" and "Adding a stand-in" (five steps) are new sections. The checks table, the guard section and step 6 of "Adding a smoke check" are updated. |
| Node criterion: `uv run pytest tests/smoke -m "not live"` | **PASS** | → `111 passed, 3 warnings in 78.38s`, against this checkout's console script. |
| Forbidden: loopback, or any other network, for a check that has not declared a stand-in | PASS | ac2; mutants G3 and G4. |
| Forbidden: real OpenCaselist responses, real caselist data, or any credential in a fixture | PASS | Every response is built at run time from `tests/fixtures/caselist/` and `tests/fixtures/openev/`. The listing shapes follow the client's recorded synthetic fixtures. The token is the existing `fixture-token-not-a-real-one`. AWS keys are moto's documented `testing`, plus keys moto's own STS issues at run time into `tmp_path`. The TLS certificate is made per run, under `tmp_path_factory`. Nothing new is committed under `tests/fixtures/` except a client parameter on `sign_in`. |
| Forbidden: an endpoint override that a prod environment accepts | PASS | ac3; mutants P1, P2 and P3. |
| Forbidden: patching the installed build's code from the test side | PASS | No converted module imports `create_app`, `CliRunner`, `mock_aws` or respx, or patches a class. Faults, the request record and backdating are done by the stand-in server, from outside the build. |

### What became of the in-process checks

| Module | In-process before | Now |
|---|---|---|
| `test_caselist_publish_smoke.py` | 1 check under `mock_aws()` | **Replaced.** The same check runs the installed build against `s3_stand_in`, plus ac3's prod check. |
| `test_caselist_runs.py` | 1 check under respx and `mock_aws()` | **Replaced.** It runs against both stand-ins, with the same assertions. |
| `test_caselist_remove_smoke.py` | 31 checks under `mock_aws()` | **Replaced, all 31**, t16's four included. Every `assert` line is kept. The only changes are plumbing: `result.output` for the failure message, the build's environment for `os.environ`, and the stand-in's record for the spies. Four checks patched the adapter, and the stand-in now does that work instead. The refused version listing is a real 403 `AccessDenied`. The takedown that loses the bucket uses a 503 `SlowDown` on every later-upload delete after the first. The check of what `status` asked for, and with which profile, reads the request record, by access key. The older manifest version is backdated in moto by the stand-in. Each replacement assertion is at least as strong as the spy it replaces. |
| `test_caselist_pull.py` | 23 checks (one live) under respx and `mock_aws()` | **Replaced for 7 checks (9 items).** The weekly pull; the complete-archive fetch order; the camp file removed elsewhere; the suppression-list copy refused (403), unavailable (503) or torn; the listing outage (503); the unreadable blob directory; the unreadable pending-work file. **Kept in `ci`, unchanged, for 14** (the live one included), in the new `test_caselist_pull_in_process.py`, marked `in_process`. Its docstring says why each stays. They patch the S3 adapter's methods mid-run, botocore's `_make_api_call` (`ProfileNotFound`, `UnauthorizedSSOTokenError`), `CaselistStatusService.status`, `ServiceContainer.sync_notifier` and `.clock`, and `OpenCaselistClient.download_archive`. None of those can be done to an installed build from outside it. The union of the two modules is the original's 23 tests and every one of its assertions; only plumbing lines differ. |

### ac2, red then green

The checks were written first, then run against the guard as committed and against two naive
versions of it. Each version was applied to the committed `sitecustomize.py` and restored with `git
checkout`, and `cmp` against a saved copy confirmed the restore.

`uv run --frozen pytest -n 0 -p no:randomly tests/smoke/test_network_guard.py -q`:

| Guard | Result |
|---|---|
| As committed: refuses everything | `1 failed, 4 passed`. `{'127.0.0.1:53602': 'refused: OutboundNetworkBlocked'} != {'127.0.0.1:53602': 'connected'}`: the build could not reach its own stand-in. |
| Loopback for every check | `2 failed, 3 passed`. `test_a_check_without_a_stand_in_is_refused_loopback_and_the_refusal_is_logged`: `{'127.0.0.1:53607': 'connected'} != {… 'refused: OutboundNetworkBlocked'}`. The other-loopback-port check failed the same way. |
| A declared stand-in switches the connect guard off | `2 failed, 3 passed`. `test_a_check_with_a_stand_in_reaches_it_and_is_refused_an_address_off_this_machine`: `{'192.0.2.1:9': 'reached the network stack: timed out'} != {'192.0.2.1:9': 'refused: OutboundNetworkBlocked'}`. The other-port check also failed. |
| Final: the declared `host:port` pairs, loopback ones only | `17 passed` with `test_smoke_harness.py`. |

The first two red attempts at those runs failed for my test's own reasons. `create_connection`
resolves `192.0.2.1` before connecting, and the guard refuses a lookup first, so the `connect` rule
was never reached. The checks now use a plain `connect`, and the runs above are the redone ones.

### Mutation run

`python3 mutation_run.py guard|prod` (scratchpad). It applies each mutant to the committed source,
runs the checks aimed at it with `HYPOTHESIS_STORAGE_DIRECTORY` set to a fresh, empty temporary
directory (no check here uses Hypothesis), restores the file with `git checkout`, and asserts
`git status --porcelain` is empty. The tree was clean after each mutant and after each batch. All
nine are caught.

| Mutant | Caught by | Time |
|---|---|---|
| G1: a declared stand-in opens every port on its host | `…_is_refused_any_other_loopback_port_and_it_is_logged` | 2.7 s |
| G2: a declaration naming an address off this machine is kept | `test_a_stand_in_declared_off_this_machine_opens_nothing` | 3.7 s |
| G3: loopback for every check, declared or not | `…_without_a_stand_in_is_refused_loopback…` and `…any_other_loopback_port…` | 2.0 s |
| G4: pytest's process opened to every host for a stand-in check | `…_reaches_it_and_is_refused_an_address_off_this_machine` | 77.1 s (the socket had no timeout; it now has one) |
| P1: prod accepts `storage.s3.endpoint_url` | 2 unit checks and `test_prod_refuses_each_stand_in_endpoint…` on the build | 3.8 s |
| P2: prod accepts any `caselist.api_base_url` | 1 unit check and the same build check | 4.0 s |
| P3: prod honours botocore's own endpoint settings | `test_prod_sends_the_evidence_store_to_aws_whatever_endpoint_botocore_is_given` | 6.1 s |
| P4: dev accepts an endpoint off this machine | 3 unit checks | 4.5 s |
| P5: the refusal does not name the variable | 4 unit checks | 4.4 s |

**G2 would have survived** the checks I first wrote. I found the gap while planning this run, and
`test_a_stand_in_declared_off_this_machine_opens_nothing` (`15e2dcd`) was added before the run.
**P5 is caught by the unit checks only.** The build check still finds the variable's name in the
message's `(from env:…)` source label, which is true of the message as printed.

### The whole suite, the checks, and the `ci` split

Each part was its own command, `uv run --frozen pytest -n auto -m "not slow and not live" --part
K/4`, on 11 cores:

| Part | Result | Time | Load at start |
|---|---|---|---|
| 1/4 | `1707 passed` | 48 s | 3.40 |
| 2/4 | `1713 passed, 1 xfailed` | 42 s | 9.99 |
| 3/4 | `1715 passed, 1 skipped` | 60 s | 10.34 |
| 4/4 | `1713 passed, 1 xfailed` | 40 s | 15.95 |

The xfails (the small-print cite line) and the skip (the parser evaluation's uncorrected pr-subset
files) were there before this task.

* **The split balances.** Collected with `--part K/4`, `tests/smoke` gives the four parts 32, 27, 25
  and 27 items. The stand-in modules give them 14, 10, 11 and 12.
* **The union proof holds:** `uv run --frozen pytest -n 0 tests/scripts/test_ci_workflow_test_job.py`
  → `17 passed`, at four parts and again at five.
* **Cost, measured:** the four original in-process modules from `6cabc6d`, run as temporary copies,
  took `55 passed in 51.16s` (4 workers, load 11). Their converted counterparts with
  `test_caselist_pull_in_process.py` took `56 passed in 116.65s` (4 workers, load 10 to 11).
  `ci`'s whole smoke selection is `111 passed in 103.78s` on 4 workers.
* **The latest `ci` pytest steps on GitHub, before this change** (runs 38529026357, 38529357943 and
  38529766278, read with `gh run view`): part 1 was 113, 112 and 118 s; part 2 99, 98 and 99 s;
  part 3 92, 91 and 93 s; part 4 70, 95 and 96 s. Hence Deviation 3.

**The other checks:**

| Check | Result |
|---|---|
| `uv run --frozen ruff format --check .` | `673 files already formatted` |
| `uv run --frozen ruff check .` | `All checks passed!` |
| `uv run --frozen pyright` | `0 errors` |
| `uv run --frozen lint-imports` | `Contracts: 12 kept, 0 broken` |
| `sh scripts/actionlint.sh` | exit 0 |
| `scripts/check_command_blocks.py` | OK, 249 blocks |
| `scripts/check_links.py` | OK, 1531 links |
| `scripts/check_thin_handlers.py` | OK |
| `uv run scripts/validate_specs.py` | `OK: 348 files, 38 epics, 290 tasks, 20 releases` |

## Files changed

* **`tests/smoke/stand_ins/`** (new). `process.py` starts and stops a stand-in process and records
  every one, so none can outlive its check. `s3_server.py` is moto's WSGI app with a request record,
  fault rules and a backdating hook in front of it; `s3.py` is the check's handle on it.
  `opencaselist_server.py` serves the TLS API and file host from a site file; `opencaselist.py` is
  its handle and makes the run's certificate. `__init__.py` holds the stand-in fixtures' names.
* **`tests/smoke/conftest.py`, `installed_build.py`, `network_guard/sitecustomize.py`.** The two
  fixtures, and pytest's process opened to 127.0.0.1 alone for a stand-in check. A stand-in that
  outlives its check is an error. `InstalledCli.allow_stand_in` is passed to the guard through
  `DEBATE_SMOKE_STAND_INS`, and the guard allows exactly those loopback `host:port` pairs.
* **The four modules**, converted; **`test_caselist_pull_in_process.py`**, which is new and holds
  the 14 pull checks that stay; **`test_stand_ins.py`**, which is new; **`test_network_guard.py`**,
  with four ac2 checks; **`test_cli_smoke.py`**, with two ac3 checks.
* **`tests/smoke/README.md`:** the guard's loopback rule, how a check reaches S3 and OpenCaselist,
  the checks table, step 6, and "Adding a stand-in".
* **`tests/fixtures/identity_center_roles.py`:** `sign_in` takes IAM and STS clients for a moto
  server.
* **`debate_core.application.settings`:** `storage.s3.endpoint_url`, dev and loopback only, and the
  prod refusal of both endpoint settings, named in the error. (Deviation 1.)
* **`debate_core.integrations.s3`:** `build_s3_client`, `build_sts_client` and `StsCallerIdentity`
  take `endpoint_url` and `ignore_configured_endpoints`.
* **`debate_cli/container.py`:** every S3 client is built by one `_s3_client`, which passes the
  setting, and ignores botocore's configured endpoints in prod. The STS adapter is built the same
  way. One debate_cli test docstring is updated.
* **`packages/debate_core/tests/`:** `test_settings_stand_in_endpoints.py` (16 checks) and
  `integrations/s3/test_s3_client_endpoints.py` (6).
* **`pyproject.toml`, `uv.lock`:** `flask` and `flask-cors` in the dev group. (Deviation 1.)
* **`.github/workflows/ci.yml`:** `part: [1, 2, 3, 4, 5]`. (Deviation 3.)

## Deviations from the spec

1. **Files outside `constraints.packages`.**
   * `debate_core.application.settings` holds the new setting. The spec names "an endpoint setting
     this task adds", and every setting lives in that module, so the spec's package list missed it.
   * `pyproject.toml` and `uv.lock` gain `flask>=3.0` and `flask-cors>=5.0`, in the dev group only,
     as the brief allowed. These are moto's server-mode imports, chosen over `moto[server]`, which
     pulls in cfn-lint, docker, aws-xray-sdk and more for services the store never calls. The
     debate-core and debate-cli runtime dependencies are unchanged.
   * `.github/workflows/ci.yml`: see 3.
   * The spec could list `debate_core.application.settings`, `pyproject.toml`, `uv.lock` and
     `.github/workflows/ci.yml`. I have not edited it.
2. **Prod refuses a `caselist.api_base_url` other than `https://api.opencaselist.com/v1`.** Before
   this change prod accepted any https URL, so the OpenCaselist stand-in would have relied on an
   override prod accepts, which the forbidden list rules out. Dev and test accept any https URL, as
   before. Nothing committed sets the URL in prod. The full suite passes.
3. **`ci`'s test job is split five ways instead of four.** Part 1 was already at 112 to 118 s, and
   the stand-in checks add about 16 s to each part. Working agreement 1 says to append a part when
   one passes two minutes. The PR's own `ci` run is the measurement. If it shows four parts would
   still fit, revert that line.
4. **The pull command keeps 14 in-process checks beside its recorded ones.** ac1's "none of the four
   is `in_process` any more" holds for the four modules. The checks that patch the CLI itself moved
   to `test_caselist_pull_in_process.py`, as the spec's "the in-process tests may stay in `ci` as
   they are" allows. Turning, for example, the expired-session checks into stand-in faults would
   test something else: an expired SSO session is caught by botocore before any request is sent,
   and S3 answers a `HEAD` with an expired token as a bare `400`, which the adapter reads as
   unavailable.

## Decisions and assumptions

* **Stand-ins are processes, never threads in pytest.** pytest-socket replaces `socket.socket`
  during a check, so a server thread's `accept()` would fail. pytest's process gets
  `socket_allow_hosts(["127.0.0.1"])` and a resolver for loopback names only, and only for a check
  that takes a stand-in fixture.
* **The guard allows `host:port` pairs, not loopback as a whole.** This is stricter than the spec's
  wording: a stand-in opens its own address, and no other process listening on the machine.
* **The OpenCaselist stand-in speaks https**, with a CA and leaf made per run. The build trusts it
  through `SSL_CERT_FILE`, which httpx reads. The transport's two rules, https only and the token to
  the API host only, are not loosened. The API stand-in answers 401 without the `caselist_token`
  cookie, and its record says only whether the cookie came.
* **The new setting is loopback-only even in dev.** A dev SSO session's token travels in every
  request it signs, so the setting cannot send one off the machine.
* **Prod ignores botocore's configured endpoints; dev and test keep honouring them.**
  `tests/integration/test_launchd_install.py` relies on `AWS_ENDPOINT_URL=http://127.0.0.1:9`, in
  dev and test, as its "a request, were one made, would go nowhere" net. Ignoring the variable
  everywhere would have disarmed that net.
* **Faults never apply to the check's own requests.** These are the ones signed with moto's
  `testing` key, so a check can still read the bucket it broke. A check that faults the build signs
  its profiles in as roles, as remove and pull already did. A 503 a check means to last is used with
  `AWS_MAX_ATTEMPTS=1`, so botocore's retries do not add seconds.
* **A module-level `THE_BUILD` in the remove and pull modules** gives their helpers (`run`,
  `invoke`, `environment`) the check's build, so that 100-odd call sites stayed unchanged. A pytest
  process runs one check at a time, and `installation` sets and clears it.
* **Following the brief, the Goal is `Succeeded`.** ac1 and ac4 name validate-dev, which runs only
  after the merge. The brief asked for them to be timed against a locally installed build, and for
  what validate-dev must show to go in the follow-ups; both are done. If you read them as needing
  the real run, set the phase back to `InProgress` until follow-up 1.
* **The working commits are marked `WIP:`.** They keep the red sequence in the history; the PR
  squashes them.

## Operator follow-ups

**1. After the merge into `dev`: validate-dev's first run with the stand-ins (ac1, ac4).** This
takes about 4 minutes after `dev-prerelease` publishes. It covers what ac1 and ac4 say of
validate-dev itself; until now that was rehearsed against a locally installed build. Where: your Mac,
in this task's worktree.

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t21-installed-smoke-stand-ins
RUN=$(gh run list --workflow validate-dev.yml --branch dev --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "${RUN}" --log | grep -E "== installed|== recorded tier|passed|failed|skipped|tier: "
```

In the log, look for:

* `== installed build:`, naming the merge commit and its `v0.1.0-dev.N` tag.
* `== recorded tier: … tests/smoke -m not live and not in_process …`, followed by
  `85 passed` (or more, if another merge added checks), `== recorded tier: passed`, and no
  `skipped` line.
* The smoke job's pytest summary under 5 minutes. Locally it took 64 to 96 s on 4 workers.
* A failure naming `NetworkAttempted`, or `refused: OutboundNetworkBlocked` for a `127.0.0.1`
  address, means a stand-in check reached something other than its stand-in. Paste the lines back.

**2. On this task's PR: the five `test` parts.** The `ci` run is already in the PR path. On the PR
page, open each `test (K)` job and read the duration of its "pytest (one part of the default
selection…)" step. Success is each part under 2 minutes. If all five are well under, and four
would fit too, the PM may revert Deviation 3's one line.

**3. Every checkout that runs `tests/smoke`, after pulling this change: sync the environment once.**
This installs `flask` and `flask-cors`, which the S3 stand-in needs. Without them the stand-in
checks fail to start, with `When using MotoServer, ensure that you install moto[server]`. Run it in
whichever checkout you use.

```bash
uv sync --all-packages
```

## Follow-up work

* **The 14 in-process pull checks are CLI tests, not smoke checks** (E01 or E34). They patch the
  composition root and its adapters, which is what `packages/debate_cli/tests/commands/` does for
  the other commands. Moving them there would leave `tests/smoke` holding only checks of a build,
  plus the harness's own.
* **`ci` part 1 has been the slowest part for some time** (E01, working agreement 1, "One part
  steadily slower"). It was 15 to 20 s behind the others before this change, and its `--durations`
  should name the reason.
* **The guard's `connect_ex` and `sendto` rules have no check of their own** (E01, a gap from
  v1-e01-t10). Every check here uses `connect`.
* **A rehearsal against a pre-release built before this change fails the stand-in checks**, because
  the build has no `storage.s3.endpoint_url`. The README says so. Once the first pre-release with
  it is published, the newest one rehearses as before.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-14

**Notes:**

Accepted in full, with the phase `Succeeded`. The spec is unchanged.

**On the phase.** ac1 and ac4 name validate-dev, which runs only after the merge. My brief asked
for them to be rehearsed against a locally installed build and for the real run to be an operator
follow-up, and the rehearsal is the same command validate-dev runs, against a build stamped and
installed the way `dev-prerelease.yml` does. The check is also self-enforcing: if the stand-in
tier fails in validate-dev, the `validate-dev` status is red and no promotion can merge. So
`Succeeded` stands, and I record follow-up 1's run at the next close-out.

**Deviation 2 is the most important line in this report.** Prod accepted any https
`caselist.api_base_url`, which is an endpoint override prod accepts, and nothing had noticed. Prod
now refuses anything but the documented API, naming the setting, and prod builds its S3 and STS
clients with botocore's configured endpoints ignored. Shown on the installed build, with the
variables aimed at the stand-in and the stand-in hearing nothing. That closes the trap the brief
named without relying on a variable being unset.

**The work itself:**

* **Stand-ins as processes, and the guard allowing declared `host:port` pairs only,** is stricter
  than the spec asked, and right: a stand-in opens its own address and nothing else listening on
  the machine.
* **Every remove check moved with every assertion,** t16's four included, and the four that patched
  the adapter now get the same faults from the stand-in's side, as real 403s and 503s.
* **The 14 pull checks kept in-process (Deviation 4)** are kept for the right reason: each replaces
  part of the CLI, not the world, and an expired SSO session cannot be produced from outside the
  build.
* **The red runs for ac2** were redone after the first attempts failed for the test's own reason,
  and the report says so.
* **The mutation run:** 9 of 9 caught; G2 found before the run and given its check.

**Rulings:**

* **Deviations 1 to 4:** accepted. `flask` and `flask-cors` over `moto[server]` is the right
  trade. The five-part split stands unless follow-up 2 shows four would fit.
* **Decisions:** accepted, including dev keeping botocore's configured endpoints so that
  `test_launchd_install.py`'s net still holds.

**Follow-up work:** the 14 in-process pull checks moving to the CLI tests, part 1's durations, and
the guard's `connect_ex` and `sendto` checks are E01 tooling, filed **after the v1.0 tag** so they
do not hold the release.

**Merge note.** `v1-e30-t14` is open and its branch also edits `tests/smoke/README.md`'s checks
table and `container.py`. A trial merge shows one conflict, in the README table only. This task
merges first; t14 then syncs and keeps both rows. t14's new smoke module is `in_process` with
moto, which the harness allows.

**Operator follow-ups:** 1 (validate-dev's first run with the stand-ins), 2 (the five parts'
times on this PR) and 3 (`uv sync --all-packages` in every checkout that runs `tests/smoke`).

### validate-dev with the stand-ins, recorded (PM, 2026-10-15)

Operator follow-up 1, from the validate-dev run the operator listed at the v1.0 close-out: run
38790399896, for `dev` at `16cc21e`, succeeded. The four runs before it, back to `0d64c1b`, all
succeeded too.

* `== installed build:` names `v0.1.0-dev.151`, commit `16cc21e`, channel and environment `dev`,
  and the run validates that same commit.
* `== recorded tier: … tests/smoke -m not live and not in_process …`, then
  `85 passed, 2 warnings in 141.44s (0:02:21)` and `== recorded tier: passed`. No `skipped` line,
  and no `NetworkAttempted` or `OutboundNetworkBlocked`.
* The slow tier, from the same commit: `1 passed in 27.62s`.

So validate-dev's half of ac1 and ac4 holds: the four commands' checks pass against the installed
build, and the recorded tier takes under 5 minutes on validate-dev's runner (141 s, against 64 to
96 s locally on 4 workers).

Follow-up 2, the five parts' times, was not taken: the `ci` run listed was still running. The five
parts stand, as ruled.

