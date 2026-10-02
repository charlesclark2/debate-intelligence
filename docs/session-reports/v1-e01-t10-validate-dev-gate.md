# Session report: v1-e01-t10-validate-dev-gate

| | |
|---|---|
| Task | `v1-e01-t10-validate-dev-gate` — validate-dev smoke gate for promotions |
| Spec | [`plan_specs/v1/e01-repo-foundation/t10-validate-dev-gate.yaml`](../../plan_specs/v1/e01-repo-foundation/t10-validate-dev-gate.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t10-validate-dev-gate` |
| Session status | PARTIAL — the smoke suite, driver and workflow are built and pass; ac1, ac3 and the `require-and-prove` node need this merged and the operator's steps |

## Summary

`validate-dev` is now a commit status that only one path can turn green.
[`.github/workflows/validate-dev.yml`](../../.github/workflows/validate-dev.yml) runs
[`scripts/validate_dev.py`](../../scripts/validate_dev.py) in four jobs:

1. **resolve** posts `pending`, then finds the published `vX.Y.Z-dev.N` pre-release whose tag
   points at exactly the commit.
2. **smoke** installs that tag with `scripts/install_channel.sh` into a scratch tool directory and
   asserts the installed `--version --json` (with `DEBATE_ENV` unset) reports that commit, tag and
   channel `dev`. It then runs `tests/smoke` against **that binary**, offline.
3. **slow** runs `pytest -m "slow and not live and not eval"` from a checkout of the same commit.
4. **conclude** posts `success` only on the commit the installed build reported, and only if every
   job passed with nothing skipped.

`dev-prerelease.yml` now dispatches validate-dev for every build it publishes. It has to:
a release created with `GITHUB_TOKEN` starts no workflow, so the spec's `release: prereleased`
trigger would never have fired.

`tests/smoke` now reaches the CLI through one fixture, `installed_cli`, which runs the binary as a
process in a scratch home. A guard loaded into the CLI's own interpreter refuses and logs every
outbound call, and a logged attempt fails the check. New recorded checks cover `--version`,
`doctor`, `config show` (redaction and environment selection) and `verify` on v1-e03-t06's fixture
manifests. `caselist import`, `cards` and `auth` now run the binary too.

**Rehearsed against a real pre-release.** `v0.1.0-dev.49` (dev's head, `4e925d0`) was installed
into the session scratchpad through the driver. It reported that commit, tag and channel, and
27 recorded checks passed against it, in 10 s wall-clock overall. The operator's real install was
untouched (receipt hash unchanged).

**The phase stays `InProgress`.** ac1 (the first real status on a dev head), ac3 (protect-main
requires it, and a stale promotion is blocked) and the `require-and-prove` node need this branch
merged, a ruleset change and a promotion. All three are marked NOT RUN and are written out under
Operator follow-ups. Merge with `scripts/task pr --partial`.

**PM, look first at:**

* **Deviation 1:** the `dev-prerelease.yml` dispatch and the `actions: write` it needs on that
  workflow's publish job. validate-dev itself holds `contents: read` and `statuses: write` only.
* **Decision 1:** the `validate-dev run:` line is removed from the promotion and hotfix templates
  and from `promotion-source`. That makes t08's ac2 text stale (Deviation 6).
* **Deviation 5:** four in-process smoke modules (moto, respx) cannot run against an installed
  binary, so validate-dev does not run them; `ci` still does.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `smoke-suite` — Recorded smoke suite | Done | `tests/smoke/conftest.py`, `installed_build.py`, `network_guard/sitecustomize.py`, `test_cli_smoke.py`, `test_network_guard.py`, `test_smoke_harness.py`, `test_live_canary.py`; `README.md` rewritten. The caselist import, cards and auth checks now run the binary; the moto/respx modules and `test_store_cli.py` are marked `in_process`. No `tests/smoke/fixtures/verify_manifest.json` (Deviation 2). |
| `driver-script` — validate_dev.py install-and-verify driver | Done | `scripts/validate_dev.py` (subcommands, Deviation 3), `tests/scripts/test_validate_dev.py` (70 tests, offline). Every `gh` call goes through `GhCli` behind the `GitHub` protocol. No installer change was needed: `install_channel.sh` already honours `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR`. |
| `workflow` — validate-dev workflow | Done | `.github/workflows/validate-dev.yml`; `dev-prerelease.yml` dispatches it (Deviation 1). |
| `require-and-prove` — Require validate-dev on main and prove the gate | NOT RUN | A ruleset change and a real promotion, so the operator's. Steps 1–4 under Operator follow-ups. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — after each dev pre-release, the dev head commit shows a `validate-dev` status linking to the run, and the run log shows the installed version and SHA equal to the tag's | **NOT RUN** (needs this merged to `dev`) | The workflow cannot run before it is on `dev`. **Rehearsal of everything it runs, against the real `v0.1.0-dev.49`:** `uv run scripts/validate_dev.py resolve --sha 4e925d0feecb0eae2152424248cb93ec089bf4c0` → `… is the commit of the published pre-release v0.1.0-dev.49` (1.1 s, real GitHub API, no status posted). With `--tag v0.1.0-dev.48` → `v0.1.0-dev.48 points at a0f64285…, not at 4e925d0…`, exit 1. `smoke --sha 4e925d0… --tag v0.1.0-dev.49 --rehearsal --work-dir <scratchpad>` → install_channel.sh verified the assets and installed into the scratchpad (`7/7 wired integrations import … complete`). The run log then showed the lines ac1 asks for: `== installed build: {… "commit": "4e925d0feecb0eae2152424248cb93ec089bf4c0", "environment_source": "build-channel:dev", "tag": "v0.1.0-dev.49", "version": "0.1.0.dev49"}` and `== installed 0.1.0.dev49 from v0.1.0-dev.49: commit 4e925d0…, validating 4e925d0…`. Then `27 passed in 5.55s`, `validate-dev smoke: passed`. Posting is covered offline (`test_conclude_posts_success_on_exactly_the_commit_that_was_installed`, `test_resolve_posts_pending_before_it_looks_…`). Operator follow-up 1 closes it. |
| **ac2** — recorded tier passes offline in under 5 minutes, with a `verify` check where a tampered card is UNVERIFIED with exit 1; the slow tier runs for the same SHA, and validate-dev is green only if both pass | **PASS** (locally and against the installed `dev.49`); the first workflow run is follow-up 1 | **Recorded tier, installed build:** 27 passed in 5.55 s in the rehearsal, and 11.75 s in a later run with the real dev.49 binary. Against the local build: `uv run pytest tests/smoke -m "not live and not in_process" -q` → `27 passed in 8.53s`. Offline is enforced, not assumed (ac4). **verify:** `test_verify_reports_the_tampered_card_unverified_and_exits_one` asserts exit 1 and `[("VERIFIED", []), ("VERIFIED", []), ("UNVERIFIED", ["TEXT_MISMATCH"])]`; `test_verify_shows_a_person_the_tampered_row` checks the table; `test_verify_exits_zero_when_every_card_verifies` checks the all-VERIFIED manifest. The data directory is built into each run's `tmp_path` by `build_fixture_data_dir`. **Slow tier, same SHA:** `uv run scripts/validate_dev.py slow --sha $(git rev-parse HEAD)` → `1 passed in 12.19s` (the 300-page docx parse), `validate-dev slow: passed`. It refuses another commit (`test_the_slow_tier_refuses_a_checkout_of_another_commit`). **Green only if both:** `conclude` needs `resolve`, `smoke` and `slow` all `success`, and the installed, smoke-tree and slow-tree commits all equal to the requested one (7 parametrized failure cases plus cancelled → `error`). A rehearsal smoke report fed to `conclude` → `failure … the smoke tests came from 8c1a55f…, not this commit`. |
| **ac3** — protect-main requires `validate-dev`; a promotion whose head has no or a failing status cannot merge | **NOT RUN** (ruleset change and a real promotion) | Operator follow-ups 2 and 3. |
| **ac4** — the live canary tier runs only when explicitly enabled, uses DEBATE_ENV=dev, and a run with it disabled makes no outbound network requests (socket-blocking fixture) | **PASS** | **Disabled means no network, in both processes.** In pytest's process the conftest calls `pytest_socket.disable_socket` itself: `test_pytests_own_process_has_no_network_in_an_offline_check` passes even under `--force-enable-socket`. In the CLI's process, `network_guard/sitecustomize.py` refuses and logs. `test_the_builds_interpreter_cannot_open_a_connection` → `refused: OutboundNetworkBlocked`, log `["getaddrinfo"]`. `test_a_request_the_cli_itself_makes_is_refused_and_logged` → `caselist auth login` against 192.0.2.1 logs `connect(('192.0.2.1', 443))`. Both run inside the recorded tier, so every validate-dev run proves the guard on the installed build. A request the check itself ignores still fails it at teardown (`NetworkAttempted: 1 outbound network call(s) refused …`), shown with a temporary probe check that passes once the teardown check is removed. **Only when enabled:** the default selection is `not live`; the driver adds `-m "live and canary"` only with `--live` (`test_the_live_tier_runs_only_when_asked`); the workflow passes `--live` only when `inputs.live == true \|\| vars.VALIDATE_DEV_LIVE == 'true'`. **DEBATE_ENV=dev:** every smoke run sets it, and the canary first asserts `environment == "dev"` and a budget ≤ 2.0. Canary run: `1 passed` against the local build and `1 passed` against the installed dev.49 (one HEAD request each). Mutants 5–8 below. |
| **ac5** — tests/smoke/README.md explains the tiers, markers and how a task adding a command adds its smoke check, and the task PR template links to it | **PASS** | README sections: "How validate-dev runs this directory", "The tiers", "How a smoke check reaches the CLI", "Markers", "The checks", "Running it", "Adding a smoke check" (`grep -c "Adding a smoke check" tests/smoke/README.md` → 1). `.github/pull_request_template.md`'s smoke checklist item links `…/tests/smoke/README.md#adding-a-smoke-check`. `uv run python scripts/check_links.py` → `OK: 1225 relative links and anchors in 164 Markdown files`. |
| smoke-suite: Recorded smoke tier passes against the local build (`uv run pytest tests/smoke -m "not live"`) | PASS | → `55 passed, 1 warning in 16.00s` (the warning is pytest-socket noting the blocked call in the harness test) |
| smoke-suite: Smoke README documents how to add checks (`contentMatch: Adding a smoke check`) | PASS | present, as above |
| driver-script: Driver tests pass offline (`uv run pytest tests/scripts/test_validate_dev.py`) | PASS | → `70 passed in 4.10s` |
| workflow: Workflow posts the validate-dev context (`contentMatch: validate-dev`) | PASS | `grep -c validate-dev .github/workflows/validate-dev.yml` → 10 |
| workflow: Workflow runs the offline slow tier (`contentMatch: slow and not live`) | PASS | → 2; the selection is `slow and not live and not eval` (Deviation 4) |
| workflow: Workflow passes actionlint | PASS | `uvx --from actionlint-py actionlint .github/workflows/validate-dev.yml` (1.7.12, shellcheck from the workspace) → exit 0, no output. On a copy with an unquoted `$@` and a misspelt `needs.slower`, it reported SC2068, SC2086 and `property "slower" is not defined`, so both its checks were live. All workflows → clean. |
| require-and-prove: Latest validate-dev run on dev succeeded | NOT RUN | Follow-up 3, last command. |
| require-and-prove: Stale promotion blocked, fresh promotion merged | NOT RUN | Follow-ups 2–4. |
| Forbidden: posting validate-dev for any SHA other than the one installed and tested | PASS | `success` is posted on `conclusion.sha`, the installed build's commit, after it is compared with the requested one. Failure goes on the requested commit. Mutants 3 and 4. |
| Forbidden: running the smoke suite from the source checkout | PASS | With `DEBATE_SMOKE_BIN` set, the harness exits on a binary or interpreter inside the checkout (`tests/smoke cannot run: the binary …/.venv/bin/debate-research is inside this checkout …`). It refuses any selected check that does not use `installed_cli` (`ERROR: DEBATE_SMOKE_BIN is set, so every selected smoke check must run the installed binary …`, listing the in-process checks). Mutant 9. |
| Forbidden: live network or model calls in the recorded tier | PASS | See ac4. |
| Forbidden: real student data or prod data dirs in smoke fixtures | PASS | Every fixture is a synthetic builder in `tests/fixtures/`; every run's data directory is under `tmp_path` with a scratch `HOME` (`test_config_show_uses_the_scratch_data_directory_it_was_given`). |
| Forbidden: success when a smoke test is skipped for a missing fixture | PASS | `test_a_skipped_smoke_check_fails_the_tier` runs **real pytest** on a suite with a skip: pytest exits 0 and the driver fails the tier with the skip's reason. Expected failures and empty tiers fail too. Shown on real repository data: the spec's literal `slow and not live` selects the parser eval, which skipped here (`30 of 30 full files are not yet corrected by a person`), and the driver failed the tier. Mutants 1 and 2. |
| Forbidden: validating any head (including hotfix/*) from source | PASS | One path for every head: `resolve` needs a published pre-release at the commit, `smoke` installs it. A hotfix gets the same dispatch from `dev-prerelease.yml`, with `--ref hotfix/<slug>`. |

### Mutation runs

A scratchpad runner applies one exact-string mutant to the committed file and runs the named tests
with `-n0 --no-cov`. **Every run used a fresh, empty `HYPOTHESIS_STORAGE_DIRECTORY`**, although none
of these tests uses Hypothesis, so there are no property statistics to report. Each file was
restored from its saved bytes and its hash checked, and `git status` was clean after the batch.
Only pytest exit 1 counts as a catch; no mutant errored.

| # | Mutant | Result |
|---|---|---|
| 0 | SHA assertion: `identity_problems` no longer compares the commit | **Caught**, 2 tests, incl. `test_a_build_reporting_another_commit_is_never_tested` |
| 1 | Skip rule: a skipped test no longer fails a tier | **Caught**, 4 tests, incl. the real-pytest `test_a_skipped_smoke_check_fails_the_tier` and `test_a_skip_in_the_slow_tier_fails_it_too` |
| 2 | Skip rule: a tier that ran nothing passes | **Caught**, 3 tests |
| 3 | Status target: post on `GITHUB_SHA` (the workflow's own commit) | **Caught** by `test_conclude_posts_success_on_exactly_the_commit_that_was_installed` |
| 4 | Status target: success without comparing the installed commit | **Caught**, 4 tests |
| 5 | Socket block: the CLI-process guard does nothing | **Caught**, both `test_network_guard.py` tests |
| 6 | Socket block: the guard raises but never logs | **Caught**, both |
| 7 | Socket block: the harness stops reading the guard's log | **Caught** by `test_a_logged_attempt_fails_the_check_even_though_the_command_carried_on`. The fixture's teardown wiring was shown separately with the probe check (ac4). |
| 8 | Socket block: the conftest stops blocking pytest's own sockets | **Caught** under `--force-enable-socket`. Without that flag the repository's `--disable-socket` addopt covers it, so it survives; the conftest's block exists for runs that override addopts. |
| 9 | Source refusal: a binary inside the checkout is accepted | **Caught**, 2 tests |

The smoke suite's own commit check was also shown against the real dev.49 binary. With
`DEBATE_SMOKE_EXPECT_SHA` set to another commit,
`test_the_build_reports_the_commit_tag_and_channel_it_was_installed_for` failed, `1 failed,
26 passed`.

**The guard's template change was shown failing first.** The rewritten template tests were run
against the unchanged `check_promotion_source.py` → `22 failed, 90 passed`. After the change →
`112 passed`.

### Whole-repo checks

* **Whole suite, run by the operator** (2026-10-02, this worktree after `scripts/task sync`): `uv run pytest -q` → `1 failed, 3944 passed, 1 skipped in 166.27s`. The failure was this task's: `test_a_request_the_cli_itself_makes_is_refused_and_logged` timed out (`subprocess.TimeoutExpired`), because the CLI waited on the operator's terminal for a password. Fixed; see "Fixed after the operator's full-suite run". The skip is the known parser eval at `test_parser_eval.py:279`.
* **Whole suite again, after the fix, run by the operator** (2026-10-02, at `339ad42`): `uv run pytest -q` → `3946 passed, 1 skipped, 1 warning in 64.05s`. 3946 = the first run's 3944 passed + its 1 failure + the new terminal check, so every test ran. The skip is the same parser eval (`6 of 6 pr-subset files are not yet corrected by a person`), and total coverage is 96%.
* `uv run --frozen pytest tests/smoke tests/scripts tests/docs tests/integration packages/debate_cli/tests -q --no-cov` → `795 passed in 32.78s` (before the fix).
* `uv run --frozen ruff check .` → `All checks passed!`; `ruff format --check .` → `491 files already formatted`.
* `uv run --frozen pyright` → `0 errors`. The new files pass pyright when named explicitly, too. `tests/smoke/test_site.py`'s `site_smoke` import error was already there.
* `uv run --frozen lint-imports` → `Contracts: 11 kept, 0 broken.`
* `shellcheck scripts/install_channel.sh` → clean; `actionlint` over every workflow → clean.
* `uv run scripts/validate_specs.py` → `OK: 305 files, 38 epics, 247 tasks, 20 releases`.

## Files changed

* **`.github/workflows/validate-dev.yml`** (new): the workflow.
* **`.github/workflows/dev-prerelease.yml`**: dispatches validate-dev after publishing, so the publish job gains `actions: write`. Header updated.
* **`.github/workflows/promotion-guard.yml`**: comment and step name only; the `validate-dev run:` line is no longer checked.
* **`scripts/validate_dev.py`** (new): the driver.
* **`scripts/check_promotion_source.py`**: `REQUIRED_FIELDS = ("Dev build",)`, and its docstring.
* **`scripts/site_smoke.py`**: docstring only. It said validate-dev runs the site check, which it does not and cannot (Decision 9).
* **`tests/smoke/`**: new `conftest.py`, `installed_build.py`, `network_guard/sitecustomize.py`, `test_cli_smoke.py`, `test_network_guard.py`, `test_smoke_harness.py` and `test_live_canary.py`. `test_caselist_import_smoke.py`, `test_caselist_cards.py` and `test_caselist_auth.py` now run the binary; their assertions are unchanged. `test_caselist_publish_smoke.py`, `_remove_smoke.py`, `_pull.py`, `_runs.py` and `test_store_cli.py` are marked `in_process`, with a comment saying why. `README.md` is rewritten, and its command blocks no longer carry `#` comments.
* **`tests/scripts/test_validate_dev.py`** (new) and **`tests/scripts/test_check_promotion_source.py`** (the template section rewritten for the new rule).
* **`.github/PULL_REQUEST_TEMPLATE/promotion.md`, `hotfix.md`**: the `validate-dev run:` line and the "none yet" paragraphs are gone, replaced by a pointer to the required status. **`.github/pull_request_template.md`**: links "Adding a smoke check".
* **`docs/process/branching-and-environments.md`**: a new section, "validate-dev: the status protect-main requires". Also updated: "What validated in dev means", the template paragraph, the guard table, the protect-main required checks and the t10 line.

## Deviations from the spec

1. **validate-dev is dispatched by `dev-prerelease.yml`; `release: prereleased` alone would never
   fire.** `dev-prerelease.yml` creates releases with `GITHUB_TOKEN`. GitHub starts no workflow for
   an event that token causes, except `workflow_dispatch` and `repository_dispatch`, and that
   workflow's own header already relies on this for its tags. So the publish job now ends with
   `gh workflow run validate-dev.yml --ref <dev or the hotfix branch> -f sha=… -f tag=…`, which
   needs `actions: write` on that one job. validate-dev keeps `release: prereleased` for a release a
   person publishes. A commit from before validate-dev.yml existed gets a notice, not a failure. The
   alternatives were worse. `workflow_run` on dev-prerelease cannot say which tag was built. A PAT
   or App token for the release would be a new secret, and would also re-trigger validate-dev for
   every prune. Suggested wording for the `workflow` node: "…on workflow_dispatch from
   dev-prerelease.yml after each publish (a GITHUB_TOKEN release starts no workflow), on release:
   prereleased for a manually published one, …".
2. **No `tests/smoke/fixtures/verify_manifest.json`** (PM decision). The verify checks reuse
   v1-e03-t06's committed manifests and `build_fixture_data_dir`, building the data directory into
   each run's `tmp_path`.
3. **The driver takes subcommands.** The spec writes `validate_dev.py --sha [--tag] [--live]
   [--post-status]`. The driver has `resolve`, `smoke`, `slow` and `conclude`, which the workflow
   runs as separate jobs, plus `run`, the spec's all-in-one form. Splitting the jobs keeps
   `statuses: write` out of every job that runs the validated commit's tests, and lets the slow tier
   run in parallel. Suggested wording: "scripts/validate_dev.py resolve | smoke | slow | conclude
   (or `run` for all four) --sha <sha> [--tag] [--live] [--post-status]".
4. **The slow tier is `slow and not live and not eval`** (PM decision), not `slow and not live`.
   It is recorded in the workflow, the driver, the smoke README and the branching doc, and shown
   failing on real data with the literal selection.
5. **Four in-process smoke modules do not run against the installed binary.** The PM asked for
   "against the installed binary where they can". `test_caselist_publish_smoke.py`,
   `_remove_smoke.py`, `_pull.py` and `_runs.py` cannot: moto and respx patch the process they run
   in, and the binary is another process. They are marked `in_process`; `ci` runs them on every PR
   and on the push to `dev` that produces the pre-release, and validate-dev does not. Converting
   them needs a moto server and a local stand-in for OpenCaselist over loopback (Follow-up work).
   `test_store_cli.py` (a real bucket, operator-run) is also `in_process`. The offline checks that
   could move (import, cards, auth status) did.
6. **t08's ac2 no longer describes the guard.** `v1-e01-t08`'s ac2 says `promotion-source` fails
   while "Dev build or validate-dev is blank". After Decision 1 it fails only on a blank
   `Dev build:`. I did not edit another task's spec. Suggested wording: "…fails while the Dev build
   line is blank; the validate-dev status itself is required by protect-main (v1-e01-t10)".
7. **Files outside `constraints.packages`:** the PR templates under `.github/` and
   `docs/process/branching-and-environments.md`, at the PM's direction;
   `tests/scripts/test_validate_dev.py`, a node output; and `tests/scripts/test_check_promotion_source.py`,
   the existing tests of the guard this task changes.
8. **`actionlint` through `uvx --from actionlint-py`**, as in v1-e01-t09, rather than a system
   install. It is the upstream 1.7.12 binary.

## Decisions and assumptions

1. **The `validate-dev run:` line goes.** Once protect-main requires the `validate-dev` status, that
   status *is* the record:
   * it sits on the exact head commit, links the run, and its description names the pre-release;
   * GitHub re-reads it every time the head moves, which is the stale-promotion case this task
     exists to block.

   A line in the description can do none of that. Keeping it as a pointer leaves two sources of
   truth that disagree the moment `dev` moves. Checking it against the status would need
   `statuses: read` in `promotion-guard.yml`, plus a re-run whenever a status arrives, and no
   `pull_request` event does that. All of it would only re-derive what the required check already
   enforces. So `promotion-source` requires only `Dev build:`. The templates say the status is the
   validation, and the branching doc records why (section "One record, not two"). `Dev build:`
   stays as the human-readable name of what is promoted. It is free text that could disagree with
   the status's named pre-release, which is noted for the PM in Follow-up work.
2. **Two layers of network blocking.** pytest-socket only patches pytest's own process. The smoke
   checks run the CLI as a child process, so a `sitecustomize` on that child's `PYTHONPATH` refuses
   internet connects, sends and host lookups, and logs each one. The fixture fails any offline check
   whose log is not empty, so a command that swallows the refusal is still caught. Unix sockets and
   `bind` are allowed: asyncio needs the first, and urllib3's IPv6 probe uses the second. The
   refusal is a `RuntimeError`, so an HTTP client does not retry it quietly as a network error.
3. **Who holds `statuses: write`.** Only `resolve` and `conclude`, which run the workflow's own copy
   of the driver. `smoke` and `slow` run the validated commit's code with `contents: read`, and the
   driver withholds `GH_TOKEN` from pytest, so the code under test cannot post its own status. No
   job is named `validate-dev`. A check run is attached to the workflow's own commit, which for a
   dispatch from dev is dev's head, so a job of that name could satisfy the requirement for the
   wrong commit.
4. **Where each status goes.** `success` goes on the commit the installed build reported, after it
   is compared with the requested one and with both test trees. `failure` and `error` go on the
   requested commit, so a run never leaves `pending` behind, cancellation included
   (`conclude` runs `if: always()`).
5. **The skip rule lives in the driver, read from pytest's JUnit report.** It decides the status, so
   it does not depend on the suite's own hooks. An expected failure counts as a skip, a tier with no
   tests fails, and pytest's exit code must also be 0.
6. **Tests come from the validated commit; the driver that posts comes from the workflow's ref.**
   `smoke` and `slow` refuse a test tree that is not the requested commit (`-dirty` included).
   `--rehearsal` relaxes that for a local check only, and `conclude` refuses its result.
7. **The suite also runs against the workspace's console script.** Without `DEBATE_SMOKE_BIN`, the
   same checks run against `.venv/bin/debate-research`, so `ci` exercises them on every PR and the
   node's `uv run pytest tests/smoke -m "not live"` passes on a laptop.
8. **The canary.** No command has a live call worth running unattended today. OpenCaselist is
   excluded by the PM, `store` needs AWS credentials a runner lacks, and nothing calls a model yet.
   So the canary is one HEAD request from the installed build's own interpreter and httpx to the
   public page of its release. That shows the installed environment can make HTTPS requests, and
   costs one call to GitHub. Later tasks add theirs with `live` and `canary`.
9. **The site smoke is not in validate-dev.** The site is deployed by hand, not per dev commit, so
   its `version.json` is never the commit being validated. `test_site.py` stays operator-run, and
   `site_smoke.py`'s docstring, which said otherwise, is corrected.
10. **The identity check runs with `DEBATE_ENV` unset and a scratch `HOME`**, per v1-e01-t09's
    closing note. The rehearsal showed why. install_channel.sh's own `--version` printout reported
    `environment_source: env:DEBATE_ENV`, inherited from my shell, while the driver's check, seconds
    later, reported `build-channel:dev`.
11. **The nightly can turn a validated head red.** That is deliberate: a commit that no longer
    validates should not be promoted. Runs for one commit share a concurrency group and queue
    rather than race.
12. **`live` marks a test, not a `-m` option.** The node says sockets are blocked "unless -m live".
    The fixtures read the test's own `live` marker instead, which is the same rule applied per test:
    a live check is never run with the guard on, and nothing else is ever run with it off.

## Operator follow-ups

Run them in order. Steps 2 to 4 belong in one sitting. While `validate-dev` is required on `main`
but this task is not yet on `main`, a hotfix branch (cut from `main`) has no validate-dev to run,
so a hotfix would be blocked until the promotion in step 3 merges.

**0. The whole suite** (about 1 minute on your Mac; it crossed 2 minutes in some sessions).
**Done.** First run: `1 failed, 3944 passed, 1 skipped in 166.27s`, a defect in this task's harness. After the fix: `3946 passed, 1 skipped, 1 warning in 64.05s`.
Where: this task's worktree.

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e01-t10-validate-dev-gate
git branch --show-current
uv run pytest -q
```

`git branch --show-current` must print `task/v1-e01-t10-validate-dev-gate`. Success: everything
passes apart from the known `tests/evals/parser/test_parser_eval.py` skip. Paste the last 5 lines.

**1. After this merges to `dev`: the first validate-dev status (ac1).** About 12 minutes after the
merge: `ci`, then `dev-prerelease` (which now dispatches validate-dev), then validate-dev itself.

```bash
TAG=$(gh release list --limit 1 --json tagName --jq '.[0].tagName')
SHA=$(gh api "repos/charlesclark2/debate-intelligence/git/ref/tags/${TAG}" --jq .object.sha)
echo "${TAG} ${SHA}"
git ls-remote origin refs/heads/dev
RUN=$(gh run list --workflow validate-dev.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "${RUN}" --json event,conclusion,url --jq '[.event, .conclusion, .url] | @tsv'
gh run view "${RUN}" --log | grep -E "== installed"
gh api "repos/charlesclark2/debate-intelligence/commits/${SHA}/statuses" --jq '.[] | select(.context == "validate-dev") | [.state, .target_url, .description] | @tsv'
```

Success looks like this:

* `TAG` is the new `v0.1.0-dev.N`, and `SHA` equals the `dev` head that `git ls-remote` prints.
* The run's event is `workflow_dispatch`, its conclusion `success`, and its URL is the run.
* The log shows `== installed build: {… "commit": "<SHA>" … "tag": "<TAG>" …}` and
  `== installed 0.1.0.devN from <TAG>: commit <SHA>, validating <SHA>`.
* The statuses list, newest first, shows `success` with that run's URL and a description naming
  `<TAG>`, then `pending` with the same URL.

If dev-prerelease's last step failed with HTTP 403, the token could not dispatch: check Settings →
Actions → General → Workflow permissions, and paste the step's log.

**2. Require `validate-dev` on protect-main (ac3, `require-and-prove`).** In the GitHub UI:
Settings → Rules → Rulesets → **protect-main** → *Require status checks to pass* → **Add checks**.
Type `validate-dev`; it is listed once step 1 has posted one. Choose the **GitHub Actions** source
and save. Leave *Require branches to be up to date* unticked. Then read it back:

```bash
gh api repos/charlesclark2/debate-intelligence/rulesets/23638829 --jq '.rules[] | select(.type == "required_status_checks") | .parameters'
```

Success: `required_status_checks` lists `ci`, `promotion-source`, `back-merge` and `validate-dev`,
each with `integration_id` 15368, and `strict_required_status_checks_policy` is `false`. Export it
for the PM to commit with the closing spec PR:

```bash
gh api repos/charlesclark2/debate-intelligence/rulesets/23638829 | jq 'del(._links, .node_id, .created_at, .updated_at, .current_user_can_bypass)' > "${TMPDIR}protect-main.json"
```

**3. Prove a promotion whose head moved is blocked, then merge it (ac3).** About 25 minutes,
mostly CI waits.

a. Open the promotion in the browser, with the template:
   `https://github.com/charlesclark2/debate-intelligence/compare/main...dev?template=promotion.md`.
   Fill in `Dev build:` with the tag from step 1, and the other sections as usual. This promotion
   carries this task to `main`. Then:

```bash
PR=$(gh pr list --base main --head dev --json number --jq '.[0].number')
gh pr checks "${PR}"
```

   Success: `ci`, `promotion-source`, `back-merge` and `validate-dev` all pass.

b. **While the promotion is open, merge any small pull request into `dev`**, for example the PM's
   ROADMAP refresh. The promotion's head becomes that new merge commit. Wait about 6 minutes, until
   `ci` on the new head is green but validate-dev has not finished, and run:

```bash
gh pr view "${PR}" --json headRefOid,mergeStateStatus --jq '[.headRefOid, .mergeStateStatus] | @tsv'
gh pr checks "${PR}"
```

   Success: `headRefOid` is the new `dev` head and `mergeStateStatus` is `BLOCKED`. `ci`,
   `promotion-source` and `back-merge` pass, while `validate-dev` is pending or not yet reported:
   validate-dev is the only thing holding the merge. A screenshot of "Merging is blocked" helps the
   PM.

c. When validate-dev has posted `success` on the new head (about 6 minutes more):

```bash
gh pr view "${PR}" --json mergeStateStatus --jq .mergeStateStatus
gh pr merge "${PR}" --merge
gh run list --workflow validate-dev.yml --limit 1 --json conclusion | jq -e '.[0].conclusion == "success"'
```

   Success: `CLEAN` before the merge, the merge goes through as a merge commit, and the last command
   prints `true` (the node's criterion).

   If step b shows `validate-dev` as "Expected — Waiting for status to be reported" even after the
   commit has a green `validate-dev` status, the ruleset's source does not match how GitHub
   attributes statuses posted by the workflow token. Edit the check in protect-main to accept any
   source, and tell the PM.

**4. Hand the results to the PM**: the output of steps 1–3. The PM records ac1 and ac3, commits the
ruleset export, and sets the Goal to `Succeeded`.

**Optional: the canary on a runner.** Run this once, if you want to see the live tier run on
GitHub's machines rather than only here:

```bash
SHA=$(git ls-remote origin refs/heads/dev | cut -f1)
gh workflow run validate-dev.yml --repo charlesclark2/debate-intelligence --ref dev -f sha="${SHA}" -f live=true
```

Success: the run's smoke job log ends with `== live canary tier: passed`.

## Follow-up work

* **Run the moto and respx smoke checks against the installed binary** (an E01 hardening task, or
  the owning E30/E34 epics). The checks are `caselist publish`, `remove`, `pull` and `runs`. They
  would need moto in server mode and a local stand-in for the OpenCaselist API, reached over
  loopback, with the network guard extended to allow loopback for those checks only. Until then
  validate-dev does not cover those commands against the build (Deviation 5).
* **`Dev build:` is free text too** (PM decision). It could disagree with the pre-release named by
  the `validate-dev` status. Checking it against the status has the same problem as the run line
  (Decision 1); dropping it would leave a promotion description without a build name.
* **t08's ac2 wording** (Deviation 6).
* **`install_channel.sh` warns about `PATH` in every automated install.** Its "`debate-research` on
  this PATH is …" warning is right for a person and noise in validate-dev's and dev-prerelease's
  logs. `v1-e01-t14`, which already reworks the install into a temporary directory, could add a
  quiet mode.
* **No `actionlint` in `ci`** (v1-e01-t09 noted it too). validate-dev.yml's first real run is after
  the merge.
* **The site smoke stays out of validate-dev** until a site deploy is tied to a commit (E36, or
  `v2-e12-t07` for the V2 web app).

## Fixed after the operator's full-suite run

**What failed.** `test_a_request_the_cli_itself_makes_is_refused_and_logged` timed out after 120 s on
the operator's Mac (`subprocess.TimeoutExpired`), and the suite took 2:46 instead of about a minute.
The check drives `caselist auth login`, which asks for a password with `getpass`. `getpass` reads
from the controlling terminal (`/dev/tty`) whenever the process has one, not from stdin. The
operator's shell has one and the smoke harness's child process inherited it, so the CLI waited on the
keyboard. This session and GitHub's runners have no terminal, so `getpass` fell back to the stdin the
check supplied, and the check passed in both places. The harness had a hole: a smoke run could read
the keyboard of whoever started it.

**Shown first.** A reproduction script ran the same `login` command under a pseudo-terminal
(`script -q /dev/null …`) → `TIMED OUT waiting on the terminal`. With `start_new_session=True` →
`exit 70`, the guard's refusal, as intended. I added
`test_the_build_can_never_read_the_operators_terminal` (`test_smoke_harness.py`): the build's
interpreter must fail to open `/dev/tty`. Under a pseudo-terminal, before the fix, it and the guard
check → `2 failed … in 120.24s`.

**The fix.** `InstalledCli.run_program` starts every process in a session of its own
(`start_new_session=True`), so it has no controlling terminal and a prompt reads the stdin the check
gives it. Under a pseudo-terminal after the fix: the two checks → `2 passed in 0.53s`;
`tests/smoke -m "not live"` → `56 passed in 11.68s` (and `56 passed` without a terminal); the recorded
tier against the installed `v0.1.0-dev.49` → `27 passed in 5.30s`. `ruff check`, `ruff format --check`
and pyright are clean.

The new check only tells the two cases apart when run from a terminal. In CI it passes either way,
because there is no terminal to inherit. The operator's re-run of the whole suite, run from a terminal, exercised
it for real: `3946 passed, 1 skipped in 64.05s`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
