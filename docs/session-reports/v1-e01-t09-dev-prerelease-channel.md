# Session report: v1-e01-t09-dev-prerelease-channel

| | |
|---|---|
| Task | `v1-e01-t09-dev-prerelease-channel` — Dev pre-release channel and environment profiles for the CLI |
| Spec | [`plan_specs/v1/e01-repo-foundation/t09-dev-prerelease-channel.yaml`](../../plan_specs/v1/e01-repo-foundation/t09-dev-prerelease-channel.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t09-dev-prerelease-channel` |
| Session status | PARTIAL — everything buildable is built and passes; three Goal criteria can only run after merge |

## Summary

Built the dev pre-release channel: `.github/workflows/dev-prerelease.yml` publishes `vX.Y.Z-dev.N`
as a GitHub **pre-release** after a green `ci` on a push to `dev` (or on a manual dispatch for a
`hotfix/*` head). `scripts/release_version.py` claims N by pushing the tag *before* building, so
overlapping runs cannot reuse a number. `scripts/stamp_build.py` stamps the version, build info
and a bundled copy of `config/` into the wheel and refuses unpublishable wheels.
`scripts/install_channel.sh` verifies `SHA256SUMS` and installs the tag as a uv tool.
`debate-research --version --json` now reports version, channel, environment and commit, and an
installed build defaults `DEBATE_ENV` from its channel (dev → dev, stable → prod).

**The phase stays `InProgress`.** Goal criteria ac1 (first real pre-release), ac3 (clean-machine
install) and ac5 (hotfix dispatch) need the workflow merged to `dev`, a clean machine, and — for ac5
— a promotion to `main` first. All three are marked NOT RUN, and ac2 is PASS offline only. Merge
with `scripts/task pr --partial`.

**PM, look first at:** the bundled configuration (Decisions §1). Without it, an installed build run
from `$HOME` (the launchd agent's working directory) found no profile and fell back to the built-in
one, where `caselist.api_enabled` is false. Also look at the per-commit concurrency group, which
replaces the spec's single serial group (Deviations §1).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `env-profiles` — Dev and prod channel values | Done | `config/model_routing.{dev,prod}.yaml` written (dev one tier cheaper); `budget_usd_daily` 2.0 / 20.0 already present from v1-e02-t05 and kept; `DEV_DAILY_BUDGET_CAP_USD = 2.0`; build-channel default and bundled config root in `debate_core.application.settings`. `[caselist] api_enabled = true` untouched in both profiles and now guarded by a test. |
| `versioning` — Dev version computation and build info | Done | `scripts/release_version.py`, `scripts/stamp_build.py`, `debate_cli/build_info.py`; `--version` wired in `app.py`. |
| `prerelease-workflow` — dev-prerelease workflow | Done | `.github/workflows/dev-prerelease.yml`. Separate workflow, not in `ci.yml` or the `ci` aggregate. |
| `install-script` — Channel install script and docs | Done | `scripts/install_channel.sh`; channel docs in `docs/process/branching-and-environments.md` and `packages/debate_cli/README.md`. Rehearsed locally end-to-end (see ac3). |
| `first-prerelease` — First dev pre-release installed cleanly | NOT RUN | Needs this branch merged to `dev`; see Operator follow-ups. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** — after a merge to dev with green `ci`, a pre-release `vX.Y.Z-dev.N` exists at the merge commit with both wheels, SHA256SUMS and build-info.json | NOT RUN | Needs a merge to `dev` to trigger the workflow; no session can produce it. The steps it depends on were each exercised locally: stamp + `uv build` (×2) + `check-wheels` on a `git archive HEAD` export → `wheels in dist are publishable as 0.1.0.dev1`, and the dist held exactly `debate_cli-0.1.0.dev1-py3-none-any.whl`, `debate_core-0.1.0.dev1-py3-none-any.whl`, `build-info.json`, `SHA256SUMS`. |
| **ac2** — consecutive merges get dev.N and dev.N+1, never reused even when runs overlap; wheel is PEP 440 `X.Y.Z.devN` sorting before `X.Y.Z` | PASS (offline) / live check NOT RUN | `uv run pytest tests/scripts/test_release_version.py` → `37 passed`. Against a real bare git remote: `test_two_consecutive_merges_get_n_and_n_plus_one`; `test_overlapping_runs_never_reuse_a_number` (B lists tags, A claims B's N, B's push is rejected, B gets N+1); `test_many_simultaneous_runs_get_distinct_consecutive_numbers` (8 threads, one barrier → dev.1…dev.8, no duplicates). That test and the overlap test were looped 25× → `failures: 0 / 25`. `test_the_pep440_form_sorts_before_the_release_and_numerically_between_builds` uses `packaging.version`. The live two-merge check is in Operator follow-ups. |
| **ac3** — on a clean machine, `install_channel.sh <tag>` installs `debate-research`, and `--version --json` reports that version, channel dev, env dev and the tagged SHA | NOT RUN (clean machine) — local rehearsal PASS | Needs a published tag and a clean machine. **Rehearsal** on this Mac: wheels stamped for HEAD `21e186f`, then `install_channel.sh --dir <dist> v0.1.0-dev.1` into a scratch `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, with a PATH free of any `.venv` → installed in 25 s. The script's own check printed `{"version": "0.1.0.dev1", "channel": "dev", "commit": "21e186f0197362c90c5c494b87b7f519b794346f", "tag": "v0.1.0-dev.1", …, "environment": "dev", "environment_source": "build-channel:dev"}`, and `command -v debate-research` resolved to the scratch tool bin. Refusals: a tampered wheel → `SHA256SUMS verification failed`; an extra unlisted wheel → `… is not listed in SHA256SUMS; refusing to install it`; tag `v0.1` → `not a release tag`. Nothing was installed in any refusal case. |
| **ac4** — `config show --json` with DEBATE_ENV=dev / prod reports different data_dir, routing file and budget; dev budget ≤ $2 cap | PASS | Source checkout: `test_the_committed_dev_and_prod_profiles_differ_in_config_show[dev/prod]` (in `test_config_command.py`) → dev `~/.debate-research/dev`, `config/model_routing.dev.yaml`, 2.0; prod `…/prod`, `model_routing.prod.yaml`, 20.0. Installed build: `test_config_show_differs_between_dev_and_prod_in_an_installed_build` (`test_version.py`), same values from the bundled config. The rehearsal install run from a scratch `$HOME` printed `dev build-channel:dev ~/.debate-research/dev …_bundled_config/config/model_routing.dev.yaml 2.0 api_enabled=True` and `prod env:DEBATE_ENV ~/.debate-research/prod …model_routing.prod.yaml 20.0 api_enabled=True`. |
| **ac5** — a manual workflow_dispatch for a `hotfix/*` head publishes a pre-release for exactly that SHA (patch target, channel dev) | NOT RUN | Needs a manual dispatch, and `workflow_dispatch` only offers workflows that exist on the chosen branch. A `hotfix/*` branch is cut from `main`, so this can run only after a promotion carries this workflow to `main`. Patch-target logic is covered offline: `test_a_hotfix_head_is_tagged_with_its_patch_target` (release `v0.1.0`, hotfix commit → `v0.1.1-dev.1` at the hotfix SHA on the remote). |
| env-profiles: Channel default and dev budget tests pass | PASS | `uv run pytest packages/debate_core/tests/application/test_settings_environments.py` → `25 passed` |
| env-profiles: Type check passes for debate_core | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` |
| versioning: Version computation tests pass | PASS | `uv run pytest tests/scripts/test_release_version.py` → `37 passed in 12.82s` |
| versioning: --version reports channel and commit | PASS | `uv run pytest packages/debate_cli/tests/test_version.py` → `12 passed in 10.03s` |
| prerelease-workflow: Workflow publishes a pre-release (`contentMatch: --prerelease`) | PASS | `grep -c -- --prerelease .github/workflows/dev-prerelease.yml` → `2` (the `gh release create … --prerelease` call and its comment) |
| prerelease-workflow: Workflow passes actionlint | PASS | `uvx --from actionlint-py actionlint .github/workflows/dev-prerelease.yml` (actionlint 1.7.12, `shellcheck` on PATH) → exit 0, no findings; `actionlint` over all workflows → clean |
| install-script: Install script verifies checksums (`contentMatch: SHA256SUMS`) | PASS | `grep -c SHA256SUMS scripts/install_channel.sh` → `7`; `shellcheck scripts/install_channel.sh` → clean; verification exercised in the ac3 rehearsal |
| first-prerelease: Latest dev pre-release exists | NOT RUN | `gh release list --limit 1 --json isPrerelease \| jq -e '.[0].isPrerelease == true'`: no release exists until the workflow runs after merge |
| first-prerelease: Clean install reports the dev channel | NOT RUN | Charlie's clean-machine install, after the first pre-release |

Whole-repo checks, run at the end:

* `uv run pytest -q` → `2843 passed, 1 skipped in 121.71s`, no failures. It took **2m21s wall-clock**
  on this machine, not the ~42 s the kickoff notes gave, so it crossed the 2-minute hand-off line
  (see Follow-up work). The four known ledger day-boundary failures did not appear.
* `uv run ruff check .` → `All checks passed!`; `uv run ruff format --check .` → `390 files already formatted`
* `uv run pyright` (CI's invocation) → `0 errors`
* `uv run lint-imports` → `Contracts: 5 kept, 0 broken.`
* `uv run pytest tests/docs` → `51 passed` (links in the edited docs)
* `uv run scripts/validate_specs.py` → `OK: 287 files, 38 epics, 229 tasks, 20 releases`

## Files changed

* **`config/`**: new `model_routing.dev.yaml` and `model_routing.prod.yaml`. Comment-only edits to
  `profiles/dev.toml` and `profiles/prod.toml` around the unchanged values; the `[caselist]`
  sections are untouched.
* **`packages/debate_core/src/debate_core/application/settings.py`**: `DEV_DAILY_BUDGET_CAP_USD`,
  `environment_for_build_channel`, a `build_channel` argument to `resolve_environment` and
  `load_settings`, and a `bundled_config_root` argument to `load_settings` and `profile_path_for`,
  plus the module docs for both.
  **`packages/debate_core/tests/application/test_settings_environments.py`**: new node test.
* **`packages/debate_cli/`**: new `build_info.py`. `app.py` now reports the channel, environment
  and commit in `--version` and passes channel and bundle to the settings loader. New
  `tests/test_version.py`. `test_app.py` relaxes an exact-payload assertion to the fields it owns.
  `test_config_command.py` gains the ac4 checkout test. `README.md` documents the channels.
* **`scripts/`**: new `release_version.py`, `stamp_build.py` and `install_channel.sh`.
  **`tests/scripts/`**: new `test_release_version.py` and `test_stamp_build.py`.
* **`.github/workflows/dev-prerelease.yml`**: new.
* **`.gitignore`**: the two stamp outputs (`debate_cli/_build_info.py`, `debate_cli/_bundled_config/`).
* **`docs/process/branching-and-environments.md`**: new section "The V1 CLI channels: dev
  pre-releases and stable releases".

(The two spec files in `git diff` against the old start commit are the PM's #105, which this branch
was re-based onto mid-session; this task did not edit any spec.)

## Deviations from the spec

1. **Concurrency group is per commit, not one serial group.** The `prerelease-workflow` node asks
   for "a concurrency group so N is allocated serially". GitHub keeps only one *pending* run per
   group and cancels older pending ones. With three merges in quick succession, the middle merge's
   run would be cancelled and its commit would never get a pre-release, which breaks ac1 for that
   merge. The workflow uses `dev-prerelease-<head sha>` instead. That group stops a re-run and the
   original from racing on one commit, and the atomic tag claim keeps N unique across commits (the
   kickoff notes asked for this). Suggested spec wording: "a per-commit concurrency group; N is
   allocated by an atomic tag push".
2. **Two explicit `uv build --package` calls, not `uv build --all-packages`.** `--all-packages`
   would also build `debate_api` and `debate_workers` wheels at the unstamped `0.1.0`, and those
   would be published as assets beside the dev build. The spec text says "builds debate_core and
   debate_cli wheels", so the workflow builds exactly those two, and `check-wheels` refuses any
   other set.
3. **Wheels bundle the committed `config/` (profiles and routing files).** Not written in the task
   spec. `settings.py` (v1-e02-t05) assigned "ships the config files alongside the wheel" to this
   task, and ac3 and ac4 are hollow without it; see Decisions §1.
4. **Additional files in the task's packages.** `scripts/stamp_build.py` and
   `tests/scripts/test_stamp_build.py` are not in any node's `outputs`. The node descriptions call
   for "a build step writes `debate_cli/_build_info.py`" and wheel checks, and this is where that
   step lives.
5. **`model_budget_usd_daily`.** The spec and the kickoff notes name `model_budget_usd_daily`. The
   real key, from v1-e02-t05, is `[models] budget_usd_daily`, already at 2.0 (dev) and 20.0 (prod).
   This task kept that key and added no second one.
6. **`actionlint` run through `uvx --from actionlint-py`** rather than a system install, to avoid
   changing the operator's machine. It is the upstream actionlint 1.7.12 binary.

## Decisions and assumptions

1. **Installed builds read their bundled configuration, not a checkout's.** The launchd agent
   (`ops/launchd/install.sh`) sets `WorkingDirectory` to `$HOME`. From there, an installed build
   finds no `config/profiles`. It then runs on `BUILTIN_PROFILES`, where
   `caselist.api_enabled` defaults to false, so the weekly sync would refuse. `stamp_build.py`
   copies `config/profiles/*.toml` and `config/model_routing.*.yaml` into
   `debate_cli/_bundled_config/config/`. `load_settings(bundled_config_root=…)` reads profiles from
   there and anchors relative routing paths to it, **even when the working directory is inside a
   checkout**, so a tagged build always uses the configuration it was built and validated with.
   Order of precedence: `profile_dir` argument, then `DEBATE_PROFILE_DIR`, then bundle, then
   checkout. `.env` discovery is unchanged: it still walks up from the working directory.
2. **Channel names** are `local` (source checkout), `dev` (pre-release) and `stable` (v1-e09-t06).
   The channel→environment mapping lives in `debate_core` (`environment_for_build_channel`) so the
   rule is tested there. The CLI only reads the stamp. `config show` and `--version` report the
   source as `build-channel:dev`.
3. **`--version` resolves the environment without loading settings.** It calls
   `resolve_environment` (DEBATE_ENV, `.env`, channel) and reads no profile, so
   `test_version_does_not_load_settings` still holds. An invalid `DEBATE_ENV` makes `--version`
   fail with the configuration error, like any other command.
4. **The tag is claimed before building** (kickoff note 3). A build that then fails leaves a tag
   with no release. That number is skipped, never reused. A re-run for the same commit finds its
   tag (`reused=true`): if a release exists it does nothing, otherwise it publishes under that tag
   for the first time. Tags are lightweight and are pushed as `<sha>:refs/tags/<tag>`, never with
   `--force`. A rejection that says "already exists" or "cannot lock ref" (a concurrent push of the
   same tag) counts as "number taken". Any other failure is retried 3 times, then reported.
5. **N follows claim order.** Two overlapping merges are numbered in the order their `ci` runs
   finished, which may differ from merge order. The spec's "dev.N and dev.N+1" holds for
   consecutive claims. Documented in the branching doc.
6. **The dev build refuses an already-released version.** If `vX.Y.Z` (or a later stable tag)
   exists while the pyproject still says `X.Y.Z`, `claim` fails with "bump `version`…". Otherwise
   a dev build would sort *before* what is already published.
7. **Hotfix patch target:** one past the newest stable tag the head contains. With no stable tag
   yet, it is the pyproject version.
8. **`debate_cli` pins `debate-core==<same version>`** in the stamped wheel's metadata, so
   `--find-links` cannot pair a CLI with a different core.
9. **Pruning deletes releases, never tags.** N is computed from tags, so it keeps counting past
   pruned builds.
10. **Token handling.** The checkout sets `persist-credentials: false`. The token reaches git only
    in the claim step, as an `http.extraheader` passed through `GIT_CONFIG_COUNT`/`KEY`/`VALUE`
    variables and masked. `GH_TOKEN` is set only in the steps that call `gh`. The build steps see
    neither. No secrets are used.
11. **The dev cap is documented, not enforced by validation.** `DEV_DAILY_BUDGET_CAP_USD` bounds
    the committed and built-in dev budgets through tests. An operator can still raise it on their
    own machine with `DEBATE_MODELS__BUDGET_USD_DAILY`, and `config show` names the source.

## Operator follow-ups

**1. After this PR merges to dev: the first pre-release (ac1, first-prerelease node).** Takes about
3 min once `ci` on dev is green.
Where: any shell with `gh` authenticated.
```bash
gh run list --workflow dev-prerelease.yml --limit 1
gh release list --limit 1 --json tagName,isPrerelease
TAG=$(gh release list --limit 1 --json tagName --jq '.[0].tagName')
gh release view "$TAG" --json assets --jq '.assets[].name'
git fetch origin dev && git ls-remote --tags origin "$TAG" && git rev-parse origin/dev
```
Success: the run is green. `isPrerelease` is `true` and the tag is `v0.1.0-dev.1`. The assets are
the two `…0.1.0.dev1-py3-none-any.whl` wheels, `SHA256SUMS` and `build-info.json`. The tag's SHA
equals the dev merge commit. If the claim step fails with 403, check **Settings → Actions → General
→ Workflow permissions** and any tag ruleset: the job requests `contents: write` and pushes the tag
with `GITHUB_TOKEN`.

**2. Two quick merges (ac2 live).** Merge two small PRs into dev within a minute of each other.
Success: `gh release list --limit 2` shows consecutive numbers, and each tag points at its own
merge commit (`git ls-remote --tags origin 'v*-dev.*'`).

**3. Clean-machine install (ac3, first-prerelease "clean install").** About 2 min on a machine or
container with no checkout. It needs `uv` and `gh auth login`.
```bash
curl -fsSL https://raw.githubusercontent.com/charlesclark2/debate-intelligence/dev/scripts/install_channel.sh -o install_channel.sh
sh install_channel.sh <tag from step 1>
which debate-research            # must be under $(uv tool dir --bin), not any .venv
cd ~ && debate-research --version --json
cd ~ && DEBATE_ENV=prod debate-research --json config show | jq '.data.settings | {"storage.data_dir", "models.routing_file", "models.budget_usd_daily"}'
```
Success: `--version --json` reports `"version": "0.1.0.devN"`, `"channel": "dev"`,
`"environment": "dev"`, and `"commit"` equal to the tag's SHA. `config show` shows the prod values
(`~/.debate-research/prod`, `…_bundled_config/config/model_routing.prod.yaml`, `20.0`). Then repeat
on the coach's laptop.

**4. Hotfix dispatch (ac5)**, only possible after a promotion puts `dev-prerelease.yml` on `main`:
```bash
git switch -c hotfix/prerelease-dispatch-check origin/main && git commit --allow-empty -m "Check the hotfix pre-release dispatch" && git push -u origin HEAD
gh workflow run dev-prerelease.yml --ref hotfix/prerelease-dispatch-check
gh release list --limit 1 --json tagName,isPrerelease
```
Success: a pre-release tagged with the patch target (`v0.1.1-dev.1` if `v0.1.0` exists, otherwise
the pyproject version) whose tag SHA equals the hotfix head. Delete the branch afterwards.

## Follow-up work

* **Point the launchd agent at an installed tag** (v1-e34-t05). `ops/launchd/install.sh` should
  resolve `debate-research` from `uv tool dir --bin` (or take `--debate-research` pointing there),
  never from a checkout's `.venv/bin`.
* **Package-name squatting on PyPI** (v1-e09-t06). `--find-links` merges the release directory with
  PyPI. `debate-core` is pinned to the exact dev version, so a squatter would have to publish that
  same version. That is unlikely but possible. Reserving `debate-core`/`debate-cli` on PyPI, or
  installing by wheel path, would close it. The spec prescribes `--find-links`, so this task kept it.
* **No `actionlint` in CI** (v1-e01-t04 owns `ci.yml`). A change to `dev-prerelease.yml` gets no
  lint on its PR, and the workflow's first real run is after merge. A small `actionlint` job in the
  `ci` aggregate would catch syntax errors earlier.
* **Full-suite runtime.** `uv run pytest -q` took 2m21s wall-clock here (`--numprocesses=auto`,
  coverage on), against the ~42 s quoted in the kickoff notes. Worth checking whether that is this
  machine's load or a real regression on dev.
* **validate-dev (v1-e01-t10)** can reuse `scripts/install_channel.sh --dir <assets> <tag>` after
  downloading the assets itself, and read `build-info.json` for the commit it validates.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
