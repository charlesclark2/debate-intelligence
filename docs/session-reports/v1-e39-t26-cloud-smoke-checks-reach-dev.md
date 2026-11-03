# Session report: v1-e39-t26-cloud-smoke-checks-reach-dev

| | |
|---|---|
| Task | `v1-e39-t26-cloud-smoke-checks-reach-dev` — The cloud smoke checks reach dev: a check marked live is let through pytest-socket, and validate-dev's cloud job proves it |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t26-cloud-smoke-checks-reach-dev.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t26-cloud-smoke-checks-reach-dev.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t26-cloud-smoke-checks-reach-dev` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

tests/smoke's conftest now turns pytest-socket off for a check marked `live`, for that check only.
Before this, its live branch skipped the conftest's own extra block but left pyproject's
`--disable-socket` in force, so the cloud checks' httpx calls to dev failed on `socket.getaddrinfo`.
Plain checks and stand-in checks are blocked exactly as before, with and without
`--force-enable-socket`. A new test, `tests/smoke/test_live_checks_reach_the_network.py`, runs a
`live` check and then a plain one in a real child pytest that reads the repository's own options,
against a loopback HTTP server inside that child. It covers three shapes: the runbook's (`-n 0`),
`--force-enable-socket`, and xdist workers (the driver's shape). At the start commit it fails with
the operator's exact `SocketBlockedError: A test tried to use socket.getaddrinfo.` After the fix,
the cloud tier's own command against dev gave `3 passed in 4.22s`.

**The Goal stays `InProgress`.** ac1 ends "the cloud tier passes against dev (operator, on the
next validate-dev run)", and that run can only happen after this branch merges. Everything else in
ac1 passes. The operator follow-up below says how to confirm it.

**For the PM to look at first:** the deviation below. I dropped the "restored after the check"
you preferred, because a mutant without it passed every run.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `cloud-smoke-checks-reach-dev` (Live checks reach the network) | Done | Its criterion passes (16 passed). Mutants 1 and 3 are caught. The PM's mutant 2 turned out to be equivalent in the form first written (see Deviations). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1, first part: a `live` check reaches a loopback server through real pytest with the repository's options, while a non-live check is still refused, with and without `--force-enable-socket`, by tests shown failing first | **PASS** | **Red at the start.** At `6a9f4b9` (tests only, conftest as at `8ceeebe`): `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/smoke/test_live_checks_reach_the_network.py -n 0 -p no:randomly` gave `1 failed, 2 passed`. The child's line: `FAILED tests/smoke/socket_probes/live_then_plain_checks.py::test_a_live_check_reaches_the_loopback_server - pytest_socket.SocketBlockedError: A test tried to use socket.getaddrinfo.` The `--force-enable-socket` case passed, as it did for the operator. I re-ran it with the three-case test against the start commit's conftest (`git show 8ceeebe:tests/smoke/conftest.py`). With `test_smoke_harness.py` included: `2 failed, 14 passed`. `[as-the-runbook-runs-it]` and `[in-xdist-workers]` failed with that same `SocketBlockedError`, and the plain check was refused in every case. **Green:** after the fix, the same files gave `15 passed` under `-n 0`, and `15 passed` again with `--force-enable-socket` on the outer run, before the xdist case was added. The final file gives `4 passed in 8.07s`. The child reads pyproject itself: it runs from the repository root, and `test_the_child_run_starts_from_blocked_sockets` asserts pyproject's `addopts` still contain `--disable-socket`. |
| ac1, last part: the cloud tier passes against dev (operator, on the next validate-dev run) | **NOT RUN** | This can only be confirmed by the first validate-dev run on a dev pre-release that contains this branch, so after the merge (operator follow-up below). In this session I made the one live call the PM allowed: `.venv/bin/python scripts/hard_stop.py 115 uv run pytest tests/smoke/cloud -m "live and dev" -n 0 -p no:randomly`, with no extra flag, gave `3 passed in 4.22s` (2026-10-31 18:39 CDT). These are read-only GETs to `https://tub.dev.wfbdebate.com/`. `TUB_SMOKE_BASE_URL` and `PYTEST_ADDOPTS` were not set. |
| Node `cloud-smoke-checks-reach-dev`: `uv run pytest tests/smoke -k "harness or socket or live"` | **PASS** | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest tests/smoke -k "harness or socket or live"`, which is the same pytest with the time limit (agreement 10) → `16 passed, 1 warning in 12.34s`. The warning is pytest-socket's own `UserWarning` from the existing harness test's expected refusal. |

### Mutants (agreement 8)

Every mutant run used a fresh `HYPOTHESIS_STORAGE_DIRECTORY`. No Hypothesis property is involved
here; I set it anyway. Each run covered `tests/smoke/test_live_checks_reach_the_network.py` and
`tests/smoke/test_smoke_harness.py` with `-n 0 -p no:randomly`. The script and its logs are in the
session scratchpad. I checked each failure in the child run's output to make sure it was the
intended reason, not a crash.

| Mutant | Result |
|---|---|
| 1. The live branch does not turn the network on (the start commit's behaviour) | **Caught** by `[as-the-runbook-runs-it]` and `[in-xdist-workers]`: the child's live check raised `SocketBlockedError: A test tried to use socket.getaddrinfo.` The `--force-enable-socket` case passes under it, as it should, because that flag opens the network anyway. |
| 2, as first written: the live branch's restore deleted (`socket.socket`, `getaddrinfo`, `gethostbyname` not put back after the check) | **Survived**: `15 passed` both with and without `--force-enable-socket`. A probe showed why. pytest-socket opens the socket module after every check in its own `pytest_runtest_teardown`, and decides afresh in `pytest_runtest_setup` for the next one. On top of that, the plain branch blocks itself whatever came before. A missing restore cannot make "the next plain check reach the network", so I removed the restore (Deviations). |
| 2, as the property it protects: the plain check after a live one is left with the network (the plain branch blocks nothing) | **Caught** by `[force-enable-socket]`: the child's plain check reported `Failed: DID NOT RAISE SocketBlockedError`. The other two cases still refuse it, because without the flag pytest-socket's own `--disable-socket` blocks it. That is the layering the harness test's docstring describes. |
| 3a. Every check given the network (the live condition always true) | **Caught** by all three cases (`DID NOT RAISE SocketBlockedError` for the plain check) and by `test_pytests_own_process_has_no_network_in_an_offline_check` → `4 failed, 12 passed`. |
| 3b. A plain check given the network (the plain branch enables instead of disabling) | **Caught** the same way → `4 failed, 12 passed`. |

### Before the report (agreement 10)

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | **Stopped at its 115-second limit** at 34%, every test so far passing. The selection is `80 of 604 test files (13.2%) chosen in 25.1 s from 6 changed files`. It includes all of tests/smoke, because the conftest changed, and each smoke check runs the CLI. The machine's load was 23 to 39, from the operator's `tub-deploy-dev` parse pool. As agreement 10 says, I leave the affected set to the pull request's `ci` check and ran the following within the limit instead. |
| `... pytest tests/smoke -q` (the changed directory alone) | Also stopped at 115 s, at 43%, all passing so far. Left to `ci` with the rest. |
| `... pytest tests/smoke/test_live_checks_reach_the_network.py tests/smoke/test_smoke_harness.py tests/smoke/test_stand_ins.py tests/smoke/test_network_guard.py tests/smoke/cloud` (the network gate: new test, harness, stand-ins' loopback-only, the build's guard; cloud deselected by marker) | `26 passed, 3 warnings in 7.64s` |
| `... pytest tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py` (the always-run list) | `369 passed in 27.00s` |
| `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `1684 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright tests/smoke/conftest.py tests/smoke/test_live_checks_reach_the_network.py tests/smoke/socket_probes/live_then_plain_checks.py` | `0 errors, 0 warnings, 0 informations` (no package source changed) |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `Contracts: 19 kept, 0 broken.` / `OK: 68 ... within 25 statements` |
| `scripts/docs_index.py --check-descriptions` / `scripts/check_links.py` / `scripts/check_command_blocks.py` | all OK (`3152 relative links and anchors in 488 Markdown files`) |
| `uv run scripts/validate_specs.py` | `OK: 539 files, 41 epics, 476 tasks, 22 releases` |

## Files changed

* **`tests/smoke/conftest.py`**: `_sockets_blocked_unless_live` calls `pytest_socket.enable_socket()`
  in its live branch. The plain and stand-in branches are unchanged. The module docstring and the
  fixture's docstring say so.
* **`tests/smoke/test_live_checks_reach_the_network.py`** (new, `in_process`): runs the probes
  below in a child pytest from the repository root, in three cases, and reads the outcomes from the
  child's JUnit XML. It also asserts that pyproject's `addopts` still hold `--disable-socket`.
* **`tests/smoke/socket_probes/live_then_plain_checks.py`** (new): a `live` check and then a plain
  check, each a `GET` with httpx in pytest's own process to a `ThreadingHTTPServer` on 127.0.0.1
  that starts when the child imports the file. Its name does not start with `test_`, so only a
  command line that names it collects it.
* **`tests/smoke/README.md`**: the `live` marker row says pytest's own process has the network for
  such a check, and the checks table lists the new test.
* **`docs/runbooks/evidence-search.md`**: **no change needed**. "Dev's smoke checks" gives
  `uv run pytest tests/smoke/cloud -m "live and dev" -n 0 -p no:randomly`, and that command now
  passes as written.
* `scripts/validate_dev.py`, `.github/workflows/validate-dev.yml`: unchanged. The cloud job gets no
  new flag, secret, token or credential.

## Deviations from the spec

* **No restore after a live check.** The PM preferred turning pytest-socket on in the fixture's live
  branch, "restored after the check". I wrote that first (`f1e1cfd`). It saved `socket.socket`,
  `getaddrinfo` and `gethostbyname` and put them back in a `finally`. The mutant that deletes the
  restore passed every run, with and without `--force-enable-socket`. pytest-socket already
  restores the socket module after every check (`pytest_runtest_teardown` → `_remove_restrictions`)
  and re-applies the command line's choice at the next check's setup. The plain branch then
  blocks itself either way. Per agreement 8, code that mutation cannot tell from its absence is
  removed (`71f32a2`). A comment in the live branch says why nothing needs undoing. What the PM's
  mutant 2 protects, that the plain check after a live one is refused, is tested directly: the
  child runs the live check first, and the plain-branch mutant is caught. If the PM wants the
  restore anyway, it is the six lines in `f1e1cfd`.

## Decisions and assumptions

* **The fixture, not a flag.** `--force-enable-socket` on the driver's command line would also have
  been the only thing between the network and every check pytest-socket alone governs. It would also
  leave the runbook's command and every hand run broken. The fixture decides per check, wherever
  the checks are run from.
* **Not the `enable_socket` marker either.** That marker is the repository's existing pattern:
  `test_site.py`, `test_store_cli.py`, `test_caselist_auth.py` and `test_caselist_pull_in_process.py`
  put `@pytest.mark.enable_socket` on each live check. Adding it to t10's checks would have fixed
  these three only, and the next live check that forgot it would fail the same way. Now `live` is
  enough. The existing markers are redundant but harmless, and I left them alone (Follow-up work).
* **The loopback server is a thread in the child pytest's own process,** started at import. That is
  "an in-process loopback HTTP server" as asked. It is up before pytest-socket blocks anything, so
  only each check's own client is subject to the gate, the same as a cloud check's call to dev. The
  README's rule that a stand-in is "never a thread in pytest's process" is about stand-ins that the
  installed CLI talks to. This probe is not one, and its docstring says what it is.
* **Nothing can leave the machine.** The probe's client uses `trust_env=False`, so a proxy variable
  cannot route it anywhere, and it only ever asks for `http://127.0.0.1:<port>/`. The child run's
  environment drops `PYTEST_ADDOPTS`, `PYTEST_XDIST_*` and `DEBATE_SMOKE_*`, so the outer run's
  options and an installed build's variables cannot change what it tests.
* **Three cases:** `-n 0` (the runbook's command), `-n 0 --force-enable-socket`, and `-n 2`.
  validate-dev's driver passes no `-n`, so pyproject's `--numprocesses=auto` runs the cloud checks
  in xdist workers. `-n 2` covers workers at about 4.5 s, against 1.6 s for each `-n 0` case.

## Operator follow-ups

**Confirm ac1's last part on the next validate-dev run** (seconds). After this branch merges into
`dev`, dev's push run publishes a pre-release and validate-dev runs against it. List the latest runs:

```bash
gh run list -R charlesclark2/debate-intelligence --workflow validate-dev.yml --limit 3
```

Then, using the run id of the first run on a commit at or after the merge:

```bash
gh run view RUN_ID -R charlesclark2/debate-intelligence --log | grep "dev cloud tier"
```

Success looks like `== dev cloud tier: passed`, the run's `cloud` job green, and its summary saying
"dev pilot up". If you see `SocketBlockedError` in the job's log, this fix did not take; paste the
log into the session. Once the run is green, the PM can set the Goal to `Succeeded`.

## Follow-up work

* **The `enable_socket` markers on the four older live checks are now redundant.** Their module
  docstrings in `test_site.py` and `test_store_cli.py` say the marker "is what lets these ... reach
  the network". That is still true, but the `live` marker now does it too. A small tidy-up for
  whichever task next touches tests/smoke: remove the markers and the sentence, or leave them as
  belt and braces.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-31

**Notes:**

A one-line fix with the test that should have existed: a `live` check through real pytest, with the
repository's own options. That test fails at the start commit with the operator's exact error.
1. **ac1's first part passes.**
   * Red at the start: `SocketBlockedError: A test tried to use socket.getaddrinfo.` in the runbook's
     shape and in xdist workers, with `--force-enable-socket` passing, which is exactly the
     operator's observation. Green in all three shapes.
   * The plain check is refused in every case, and the stand-in and harness tests are unchanged.
   * The child reads pyproject from the root, and a test asserts `--disable-socket` is still in
     `addopts`, so the test cannot pass by the option being removed.
   * The node criterion passes (16).
2. **The live call:** `3 passed in 4.22s` with no extra flag. These are read-only, unauthenticated
   GETs, as allowed.
3. **The deviation, no restore: accepted.**
   * pytest-socket removes its restrictions in its own teardown and re-applies the command line's
     choice at the next setup.
   * The plain branch blocks itself either way.
   * The restore mutant surviving every run is agreement 8 working as intended. You then tested the
     property mutant 2 stood for (the plain check after a live one is refused), and it is caught.
4. **Decisions accepted:**
   * the fixture rather than a driver flag or per-check markers, so `live` alone is enough wherever
     the checks run;
   * the loopback probe as a thread in the child, with `trust_env=False` and the outer run's
     options dropped;
   * three shapes, including the driver's xdist workers.
5. **Follow-up (redundant `enable_socket` markers):** not filed. Leave them as belt and braces, and
   the next task to touch tests/smoke may tidy them.
6. **Closing checks:** the affected set (80 files, all of tests/smoke) stopped at 34% at its limit
   under a load of 23 to 39 with nothing failing, and is left to the PR's `ci` under agreement 10.
   The network-gate files (26), the always-run list (369), ruff, pyright, lint-imports, the doc
   checks and the specs are clean.
7. **Merge:** `--partial`, as soon as `ci` is green, ideally before Monday 2026-11-02's image
   deploy. The first validate-dev run on a pre-release with this branch is ac1's last part. Once its
   cloud job is green (`== dev cloud tier: passed`), the PM records it and sets the Goal. That run's
   release is then green, and Monday's deploy takes it.

## Operator records (recorded by the PM, 2026-10-31)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac1, last part: the cloud tier passes against dev on the next validate-dev run | NOT RUN | PASS | validate-dev run `41255710332` on `a21bb68` (the ROADMAP refresh after this task's merge `f58eb04`; pre-release `v1.1.0-dev.251`): green, every job `success`, the cloud job included. The three runs before it (on `caf1708` and `31e533e`, before the merge) failed on the cloud job alone, every other job passing |

Every criterion passes, so the Goal is `Succeeded`. `v1.1.0-dev.251` is the release Monday 2026-11-02's image deploy is pinned to.
