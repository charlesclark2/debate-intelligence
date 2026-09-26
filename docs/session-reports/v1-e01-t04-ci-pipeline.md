# Session report: v1-e01-t04-ci-pipeline

| | |
|---|---|
| Task | `v1-e01-t04-ci-pipeline` — GitHub Actions CI pipeline |
| Spec | [`plan_specs/v1/e01-repo-foundation/t04-ci-pipeline.yaml`](../../plan_specs/v1/e01-repo-foundation/t04-ci-pipeline.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t04-ci-pipeline` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`.github/workflows/ci.yml` is written, passes actionlint (with shellcheck over every `run:` script),
and every command it runs passes locally on this branch. It has the five jobs the spec names (`lint`,
`typecheck`, `test`, `import-boundaries`, `spec-validate`), plus `terraform-checks` and `site`, which
v1-e29-t02 and v1-e36-t03 handed over. A `changes` job path-filters the heavier jobs on pull requests,
and the aggregate `ci` job is the single check the rulesets will require.

The `workflow` and `caching` nodes are done. `green-run` and `gate-proof` are **NOT RUN** by design:
they need the workflow on `dev`, a throwaway PR and a ruleset change, which only the operator can do.
The Goal stays `InProgress`. Merge with `scripts/task pr --partial`, then follow the steps under
**Operator follow-ups**.

Three things for the PM to look at first, all under **Deviations**:

* the `python` path filter is wider than the spec's list, because the test suite reads far more of
  the repository than `packages/` and `tests/`;
* the `site` job is added, although this spec doesn't mention it;
* `lint` and `spec-validate` run on every trigger, with no path filter.

**After CI's first run: the test fix.** The PM fixed the `uv sync` step (`--all-packages`), and
three CLI tests then still failed on the runner. They are not tests this task wrote. They come from
tasks that are already merged and `Succeeded`, so this is a fix to their work:
* `test_help_lists_the_global_options_and_the_commands` is from `v1-e01-t07-cli-skeleton`;
* `test_the_command_is_registered` is from `v1-e30-t03-archive-importer`;
* `test_the_help_names_the_three_things_a_run_can_be_asked_to_do` is from
  `v1-e34-t02-scheduled-sync`.

The briefing had all three as E30 and E34 work; the first is E01's.

The cause is **colour, not width**. `COLUMNS=80 uv run pytest -q` passes everything on this machine
(2629 passed, before the fix). Under pytest, stdout is not a TTY, so Rich already falls back to 80
columns locally. What differs on the runner is `GITHUB_ACTIONS=true`: Typer reads it at import and
forces a terminal, so help panels arrive full of ANSI escapes. `GITHUB_ACTIONS=true uv run pytest -q`
reproduces exactly CI's 3 failures.

**Measured, 16 tests in 9 modules depended on the terminal; CI caught 3 of them.** The measurement
covered forced colour and widths from 20 to 400 columns. The 16 include one smoke check, and they come
from nine tasks across E01, E02, E29, E30, E31 and E34 (listed under Deviations).

One autouse fixture in the root `conftest.py` now pins every test to plain text at 200 columns.
`test_help_rendering.py` proves it holds at 20 and at 400 columns with colour forced. Neither ci.yml
nor the CLI changed.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `workflow` — CI workflow with stable job names | Done | Commit `c58349c` (after the rebase onto #88). All 7 node criteria pass. The PM's `uv sync --locked --all-packages` fix is `f53f37f`. |
| `caching` — uv caching and Python setup | Done | Same commit. `astral-sh/setup-uv` with `enable-cache: true` and `cache-dependency-glob: uv.lock`; `uv python install` reads `.python-version`; `uv sync --locked` in every Python job. |
| `green-run` — Green run on dev | NOT RUN | Needs ci.yml on `dev`, which only happens when this PR merges. Operator follow-ups, steps 1–2. |
| `gate-proof` — Prove required checks block bad PRs | NOT RUN | Needs a throwaway PR and a ruleset change (GitHub settings). Operator follow-ups, steps 3–4. |

## Acceptance criteria

### Goal criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — ci.yml runs on pull_request and push for dev and main with lint, typecheck, test, import-boundaries, spec-validate and an aggregate `ci` that fails if any of them fails or is skipped other than by its path filter; `validate_specs.py` on every trigger, `spec_index.py --check` only when the PR's base is main; lint runs `check-merge-conflict` over every tracked file | PASS (definition) | `on:` has `pull_request` and `push`, each `branches: [dev, main]`, and all five jobs are present. **Aggregate logic:** the `ci` step's script and env were taken from the parsed YAML and run against 7 simulated `needs` payloads. All green → exit 0. Docs-only PR with the filtered jobs skipped and their filters `false` → exit 0. `test` failed → exit 1. `lint` skipped (it has no filter) → exit 1. `changes` failed with everything downstream skipped → exit 1. `test` skipped while `python` was `true` → exit 1. `site` cancelled → exit 1. **spec-validate:** `validate_specs.py` has no condition. `spec_index.py --check` has `if: github.base_ref == 'main'`, and `base_ref` is empty on push. On this branch that check exits 1 with `ROADMAP.md is stale`, which is exactly the task-PR case the guard keeps out of the PR path into `dev`. **Merge markers:** `uv run --frozen pre-commit run check-merge-conflict --all-files` → `Passed` in 0.8s. That is the same hook as `.pre-commit-config.yaml`, run over every tracked text file. The criterion is only confirmed live once the workflow has run: `green-run` and `gate-proof`. |
| ac2 — astral-sh/setup-uv with dependency caching keyed on uv.lock | PASS (configuration) | `astral-sh/setup-uv@v10.2.0` with `enable-cache: true` and `cache-dependency-glob: uv.lock`, shared by every Python job through one YAML anchor. The warm-cache runtime is part of ac5 and is NOT RUN. |
| ac3 — a PR with a ruff error, a failing test or an invalid PlanSpec is blocked by a red required `ci`; `ci` required on dev and main | NOT RUN | Needs the `gate-proof` node (throwaway PR plus ruleset change). The planted defects were checked locally. `sed … phase: NotAPhase` on a spec → `validate_specs.py` exits 1 with `status.phase 'NotAPhase' not in [...]`. A module containing only `import os` → `ruff check` reports `F401`. Both files restored. |
| ac4 — permissions default to contents read; no secrets referenced | PASS | Top-level `permissions: contents: read`. The only job-level grant is `pull-requests: read` on `changes`, which dorny/paths-filter needs to list a PR's files. `grep -n "secrets\." .github/workflows/ci.yml` → no matches. The tflint step uses `github.token`, the workflow's own token, not a repository secret. |
| ac5 — `ci` on a PR into dev finishes in under 5 minutes; path filters for python, web/clients and infrastructure; pytest excludes slow and live; no heavy suite on PRs | NOT RUN (timing) | Timing needs a real run (the `green-run` PR-duration criterion). The configuration is in place. Filters: `python`, `infrastructure`, `site`, `web` (`web/`, `clients/`), `api`. pytest runs `-m "not slow and not live"`. No evals, e2e, canaries, plan/apply or load tests appear anywhere. Local timings of the same commands: pytest 41s wall (`2476 passed, 1 skipped`), pyright 6.5s (`0 errors`), lint-imports 0.6s (`5 kept, 0 broken`), validate_specs 1.5s, ruff check plus format 0.6s, site checks 18s. The jobs run in parallel, so wall-clock is roughly the slowest job plus setup. |

### Plan node criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `workflow` — Workflow defines the spec-validate job | PASS | `grep -cF "spec-validate" .github/workflows/ci.yml` → 2 |
| `workflow` — Workflow fails a stale ROADMAP.md on the promotion PR only | PASS | `grep -cF "spec_index.py --check"` → 2 (the step name and the command, under `if: github.base_ref == 'main'`) |
| `workflow` — Workflow fails a committed conflict marker | PASS | `grep -cF "check-merge-conflict"` → 2 |
| `workflow` — Workflow runs for dev and main | PASS | `grep -cF "branches: [dev, main]"` → 2 (pull_request and push) |
| `workflow` — Path filters use dorny/paths-filter | PASS | `grep -cF "dorny/paths-filter"` → 2 (`dorny/paths-filter@v4` plus a comment) |
| `workflow` — Test job excludes slow and live markers | PASS | `grep -cF "not slow and not live"` → 1: `uv run --frozen pytest -n auto --cov -m "not slow and not live"` |
| `workflow` — Workflow passes actionlint | PASS | `actionlint -verbose .github/workflows/ci.yml` (v1.7.12, checksum-verified release binary in the session scratchpad, shellcheck from `uv run` on PATH) → `Found total 0 errors`, exit 0. Shellcheck was confirmed active: a scratch copy with an unquoted `$VAR` was reported as `SC2086`. |
| `caching` — setup-uv caching is configured | PASS | `grep -cF "enable-cache: true"` → 1 (one anchored step, reused by `lint`, `typecheck`, `test`, `import-boundaries` and `spec-validate`) |
| `green-run` — Latest CI run on dev succeeded | NOT RUN | ci.yml is not on `dev` until this PR merges. Operator follow-ups, step 2. |
| `green-run` — Latest PR run of CI finished in under 5 minutes | NOT RUN | Needs this PR's own run. Operator follow-ups, step 2. |
| `gate-proof` — Failing PR is blocked from merge (custom) | NOT RUN | Needs the throwaway PR and the ruleset change. Operator follow-ups, steps 3–4. |

## Files changed

* `.github/workflows/ci.yml` (new): the whole task. After this session wrote it, the only change
  is the PM's `--all-packages` line.
* `conftest.py` (root): an autouse fixture that pins rendering for every test, added below the
  existing `sys.path` setup, which is unchanged. The module docstring's first line now names both
  jobs.
* `packages/debate_cli/tests/test_help_rendering.py` (new): three tests that hold the pin.
* `plan_specs/v1/e01-repo-foundation/t04-ci-pipeline.yaml`: the PM's widening of
  `constraints.packages`, committed as written (`8f33388`).
* `docs/session-reports/v1-e01-t04-ci-pipeline.md`: this report.

None of the 16 terminal-sensitive tests was edited, and nothing under `tests/smoke` was either. The
one fixture covers both trees, so no module needed a change. `status.phase` stays `InProgress`.

## Deviations from the spec

1. **The `python` path filter covers what the test suite reads, not only the four paths in the spec.**
   The spec lists `packages/`, `tests/`, `pyproject.toml` and `uv.lock`. The suite also reads:
   * every tracked Markdown file (`tests/docs/test_check_links.py::test_the_repository_has_no_broken_links`);
   * the real `plan_specs/` tree and `ROADMAP.md` (`tests/specs`);
   * `scripts/` and `ops/`, whose scripts it drives;
   * `config/`;
   * `infrastructure/envs/*/variables.tf` (`test_settings.py`);
   * `docs/architecture/cardmirror-evaluation.md`;
   * what `.gitignore` covers (`test_token_store.py`).

   With the spec's list, a docs-only PR with a broken link would skip `test`, merge green, and then
   fail the next Python PR, which did nothing wrong. That is the same shape as the #53 formatting
   defect the lint job exists to stop. The filter therefore adds `conftest.py`, `.python-version`,
   `scripts/**`, `ops/**`, `config/**`, `plan_specs/**`, `**/*.md`, `infrastructure/envs/**`,
   `.gitignore` and `.github/workflows/ci.yml`. A comment in the workflow says a test that starts
   reading another path must add it there. The `infrastructure` filter likewise adds
   `scripts/terraform_checks.sh` and `.terraform-version`, as v1-e29-t02's hand-off asked. **PM:**
   please amend the spec's filter list to match. It is the one place in the description that
   enumerates paths.
2. **A `site` job and a `site` filter were added.** This task's spec never mentions `site/`.
   `v1-e36-t03-site-scaffold` (`Succeeded`) says in its description that "the site job in
   .github/workflows/ci.yml is added by v1-e01-t04", and its accepted report hands the job over. The
   job is in `.github/workflows`, is path-filtered on `site/**`, runs the same script as the
   `site-checks` pre-commit hook, and took 18s locally. **PM:** please add it to this spec's
   description beside `terraform-checks`.
3. **`lint` and `spec-validate` have no path filter.** The `workflow` node says the jobs are "gated on
   those outputs". Two criteria require these two to run everywhere: ac1 says `check-merge-conflict`
   runs "over every tracked file", and `validate_specs.py` runs "on every trigger". A filtered lint
   job would have skipped the Markdown-table conflict markers of #56 on a PR that touched only
   Markdown. Both jobs finish in seconds after setup.

4. **This task now touches test code outside `.github/workflows`:** the root `conftest.py` and
   `packages/debate_cli/tests/test_help_rendering.py`. The PM widened `constraints.packages` to
   `[.github/workflows, conftest.py, packages/debate_cli/tests, tests/smoke]` after CI's first run.
   The scope used is **2 files**: one modified (`conftest.py`), one new (`test_help_rendering.py`).
   None of the 9 affected test modules and none of `tests/smoke` needed an edit.

   *Why.* A hermetic gate needs hermetic tests. Before the fix, these 16 tests passed or failed
   depending on the terminal:

   | Test | From | Fails when |
   |---|---|---|
   | `test_app.py::test_help_lists_the_global_options_and_the_commands` | v1-e01-t07 | **CI** (`GITHUB_ACTIONS`), `FORCE_COLOR`, ≤ 30 cols |
   | `test_caselist_import.py::test_the_command_is_registered` | v1-e30-t03 | **CI**, `FORCE_COLOR`, ≤ 40 cols |
   | `commands/test_caselist_pull.py::test_the_help_names_the_three_things_a_run_can_be_asked_to_do` | v1-e34-t02 | **CI**, `FORCE_COLOR`, ≤ 50 cols |
   | `test_caselist_import.py::test_a_dry_run_says_so_in_the_table` | v1-e30-t03 | `FORCE_COLOR`, ≤ 20 cols |
   | `commands/test_caselist_runs.py::test_runs_calls_out_a_schedule_that_has_stopped` | v1-e34-t03 | `FORCE_COLOR` |
   | `commands/test_caselist_runs.py::test_a_truncated_pull_states_wanted_and_deferred_and_the_next_run_carries_the_backlog` | v1-e34-t03 | `FORCE_COLOR` |
   | `test_caselist_cards.py::test_cards_prints_totals_and_the_top_clusters` | v1-e31-t04 (#88) | ≤ 60 cols |
   | `tests/smoke/test_caselist_cards.py::test_caselist_cards_by_team_and_table` | v1-e31-t04 (#88) | ≤ 60 cols |
   | `commands/test_store.py::TestListing::test_ls_lists_the_bucket` | v1-e29-t05 | ≤ 40 cols |
   | `commands/test_store.py::TestFailures::test_an_expired_sso_session_is_one_line_and_not_a_traceback` | v1-e29-t05 | ≤ 40 cols |
   | `commands/test_store.py::TestFailures::test_a_person_still_sees_the_table_when_the_run_failed` | v1-e29-t05 | ≤ 30 cols |
   | `test_config_command.py::test_config_show_renders_a_table` | v1-e02-t05 | ≤ 50 cols |
   | `commands/test_caselist_auth.py::test_status_after_login_reports_the_token_without_printing_it` | v1-e34-t01 | ≤ 30 cols |
   | `test_app.py::test_doctor_renders_a_table` | v1-e01-t07 | 20 cols |
   | `test_caselist_import.py::test_importing_one_week_succeeds_and_prints_a_summary_table` | v1-e30-t03 | 20 cols |
   | `test_caselist_import.py::test_an_older_archive_is_refused_with_a_domain_failure` | v1-e30-t03 | 20 cols |

   *Method.* Unfixed tree, rebased onto dev with #88. Runs:
   * the full suite under `COLUMNS=80` (0 failed), `GITHUB_ACTIONS=true` (3), `FORCE_COLOR=1` (6),
     60 columns (2) and 40 columns (7), each run once;
   * the CLI and smoke trees at 20, 30, 50, 70, 90 and 120 columns, with and without
     `FORCE_COLOR=1`.

   Width runs set both `COLUMNS` and `TERMINAL_WIDTH`. The union is 16. So, of the tests that
   depended on the terminal, CI's runner tripped **3 of 16**. The other 13 were latent: they
   would have fired on the first runner, laptop or narrow editor pane that differed the right way.

   *Against the briefing's list.* `test_caselist_import.py:357` is
   `test_an_older_archive_is_refused_with_a_domain_failure`, and it fails at 20 columns.
   `test_caselist_import.py:444` and `:484` (`--event` and `--snapshot` in a domain-failure hint)
   have the same shape but did not fail in any environment measured. They are covered by the pin
   anyway. `test_caselist_cards.py:243` (`--snapshot` in help) did not fail by itself.
   `test_caselist_cards.py::test_cards_prints_totals_and_the_top_clusters`, a table-width
   assertion in the same module, did.

   *Why the root conftest and every test.* This follows the amended spec: one fixture covers both
   trees, and no test should depend on the terminal. Measured cost: none. The full suite is
   2632 passed, 1 skipped in 33s either way.

   *Correction to the spec's comment.* The comment on `constraints.packages` says the tests hold
   "only on a wide terminal". The cause CI hit was forced colour (`GITHUB_ACTIONS`); width is the
   second, latent cause. The spec text is the PM's, so I have not edited it.

## Decisions and assumptions

* **Pushes to dev and main run every job.** Path filters apply only to `pull_request`. The `changes`
  outputs are `true` on push, so the post-merge run on `dev` is a full verdict: it is what `green-run`
  and the next task branch rely on. The 5-minute budget is written for PRs.
* **A change to ci.yml turns on every filter,** so a workflow edit is always exercised by its own PR.
  This PR's run therefore includes `terraform-checks` and `site`.
* **The aggregate `ci` job decides from `toJSON(needs)` and a job→filter map (`PATH_FILTER_OF_JOB`).**
  A job missing from the map has to succeed. A skipped job passes only if its filter output is the
  string `false`. A new path-filtered job therefore needs two edits: `needs` and the map. The workflow
  header says so.
* **check-merge-conflict runs as `pre-commit run check-merge-conflict --all-files`.** This is the same
  hook definition, including `--assume-in-merge`, over every tracked file of type `text`. Binary files
  such as `.docx` fixtures are skipped, as the hook skips them; git never writes conflict markers into
  a binary file.
* **Concurrency:** a newer push to a PR cancels the older run. Pushes to `dev` and `main` are never
  cancelled, so each merge commit keeps its own result.
* **Action versions:** the current majors are `actions/checkout@v7`, `dorny/paths-filter@v4`,
  `hashicorp/setup-terraform@v4`, `terraform-linters/setup-tflint@v6`, `pnpm/action-setup@v6` and
  `actions/setup-node@v7`. `astral-sh/setup-uv` publishes no major-version tag, so it is pinned to
  `v10.2.0`. Versions were read from `gh api repos/<repo>/releases/latest` on 2026-09-25. Checkout
  uses `persist-credentials: false`.
* **Repeated setup steps are YAML anchors** (`*checkout`, `*setup-uv`, `*install-python`,
  `*uv-sync`). A composite action would sit in `.github/actions/`, outside this task's packages.
  actionlint 1.7.12 resolves the anchors.
* **Terraform version** is read from `.terraform-version` at run time rather than written into the
  workflow a second time. tflint is pinned at `v0.64.0`, as in v1-e29-t02's hand-off.
* **The site job uses Node 22.** It is the major that `site/package.json` `engines` (`>=22.13.0`)
  allows and that the operator runs locally (22.13.0). pnpm's version comes from the `packageManager`
  field.
* `uv run --frozen` after `uv sync --locked`: the sync verifies the lockfile, and later steps don't
  re-resolve it. `ruff check` uses `--output-format=github`, so violations show as PR annotations.
* The `web` and `api` outputs exist, as the spec asks, but no job consumes them yet (v2-e14-t01,
  v2-e12-t06).
* **Not run locally:** `terraform-checks`. This machine has Terraform 1.7.3, while the repository
  pins 1.16.3 and needs ≥ 1.10. v1-e29-t02 verified the script itself. Its first CI run is this PR's.

* **How the pin works.** The fixture deletes `FORCE_COLOR`, `PY_COLORS`, `TTY_COMPATIBLE`,
  `TTY_INTERACTIVE` and `TERMINAL_WIDTH`, and sets `NO_COLOR=1` and `COLUMNS=200`: that is what
  Rich reads when `debate_cli.output.CliOutput` builds a console with no width. It also
  monkeypatches `typer.rich_utils.FORCE_TERMINAL = False`, `COLOR_SYSTEM = None` and
  `MAX_WIDTH = 200`.
  * Typer reads its environment variables once, at import, so setting the environment alone would
    come too late for help output. The module attributes are what it reads each time it builds a
    help console.
  * `monkeypatch.setattr` raises if a Typer upgrade renames them, so the pin cannot silently stop
    applying.
  * 200 columns is wide enough that nothing the tests look for wraps. With colour off, every option
    name in all 19 commands is intact from 80 columns up.
* **The proof has to run in a fresh process.** `test_help_rendering.py` runs the 16 tests in a
  nested pytest with `GITHUB_ACTIONS=true FORCE_COLOR=1` at `COLUMNS=TERMINAL_WIDTH=20` and at `400`.
  * In-process it could not show anything, because Typer has already been imported.
  * With the pin removed, the narrow run fails 15 of the 16 and the wide run 6. With it, both
    pass: about 4.7s each, run in parallel under xdist.
  * A third test renders `--help` for all 19 commands and asserts that every option name appears
    intact and that there is no escape code. A new long flag is covered without anyone editing a
    list.
* **Sync without the push.** `scripts/task sync` rebases and then force-pushes a branch that is
  already on the remote. CLAUDE.md keeps pushes with the operator, and a push mid-fix would have run
  CI on a half-finished tree. The session therefore did the local half: it fetched `origin/dev` and
  rebased onto it (#88 and #89, no conflicts). It did not push; see Operator follow-ups, step 0.

## Operator follow-ups

0. **Push the rebased branch.** Where: the task worktree. Runtime: seconds.

   ```bash
   scripts/task sync v1-e01-t04-ci-pipeline
   ```

   The rebase is already done, so this only force-pushes with lease. Success looks like this: the
   PR's CI run starts on `fd134b2` or the later report commit, `test` is green, and every other job
   is green as before.

1. **Merge this task partially** after PM review (`--partial`, because `green-run` and `gate-proof`
   are open by design). Where: your Mac, main clone.

   ```bash
   scripts/task pr v1-e01-t04-ci-pipeline --partial
   gh pr checks --watch        # from the worktree, on the new PR; expected ~2-4 min
   ```

   Success looks like this: every job is green, including `terraform-checks` and `site`, which run
   because the PR changes ci.yml, and `ci` is green. This is the workflow's first ever run, so a red
   job here is expected iteration, not a surprise. Paste
   `gh run view <run-id> --log-failed | tail -80` back into a session on this branch and it will be
   fixed in the same PR. After the merge: `scripts/task finish v1-e01-t04-ci-pipeline --partial`.

2. **Check the green-run criteria** once the squash merge has pushed to `dev` and its run has
   finished (about 3 minutes). Where: any clone. Runtime: seconds.

   ```bash
   gh run list --workflow ci.yml --branch dev --limit 1 --json conclusion \
     | jq -e '.[0].conclusion == "success"'
   gh run list --workflow ci.yml --event pull_request --limit 1 \
     --json conclusion,startedAt,updatedAt \
     | jq -e '.[0] | .conclusion == "success" and (.updatedAt | fromdate) - (.startedAt | fromdate) < 300'
   ```

   Success looks like this: both print `true` and exit 0. The second one measures the latest PR run,
   so run it before another PR's CI starts, or note which run it measured.

3. **Require `ci` on both rulesets** (a GitHub settings change). GitHub offers `ci` in the check
   search only after it has run once, so do this after step 1. Where: github.com → repository
   Settings → Rules → Rulesets.
   * Open **protect-dev** (id 23638856) → tick **Require status checks to pass** → **Add checks** →
     type `ci` → choose the one from **GitHub Actions** → **Save changes**.
   * Repeat on **protect-main** (id 23638829).
   * Recommended: leave **Require branches to be up to date before merging** off on protect-dev.
     Otherwise every parallel task PR would need a rebase after each merge into `dev`.
   * Require only `ci`, not the individual jobs. That is what lets later tasks add jobs without
     touching the rulesets.

   Verify (read-only):

   ```bash
   for id in 23638856 23638829; do
     gh api "repos/{owner}/{repo}/rulesets/$id" \
       --jq '.name + ": " + ([.rules[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context] | join(","))'
   done
   ```

   Success looks like: `protect-dev: ci` and `protect-main: ci`.

4. **Prove the gate with a throwaway PR** (the `gate-proof` custom criterion). Where: a scratch clone
   or worktree off `origin/dev`, not a task worktree. Runtime: ~3 min, mostly waiting for CI.

   ```bash
   git fetch origin && git switch -c ci-gate-proof origin/dev
   printf 'import os\n' > packages/debate_core/src/debate_core/ci_gate_probe.py          # ruff F401
   printf 'def test_ci_gate_probe() -> None:\n    assert False\n' > tests/test_ci_gate_probe.py   # failing test
   sed -i '' 's/^  phase: Succeeded$/  phase: NotAPhase/' \
     plan_specs/v1/e01-repo-foundation/t01-init-local-repo.yaml                          # invalid spec
   git add -A && git commit --no-verify -m "DO NOT MERGE: prove the ci check blocks bad PRs"
   git push -u origin ci-gate-proof
   gh pr create --base dev --title "DO NOT MERGE: ci gate proof" --body "Throwaway PR for v1-e01-t04 gate-proof."
   gh pr checks --watch
   gh pr view --json mergeStateStatus --jq .mergeStateStatus
   gh pr close --delete-branch
   ```

   Success looks like this:
   * `lint` fails with `F401`, `test` fails on `test_ci_gate_probe`, `spec-validate` fails naming
     `NotAPhase`, and `ci` fails and lists all three as `FAIL`;
   * `mergeStateStatus` is `BLOCKED`, and the PR page says **Merging is blocked**;
   * both rulesets still list `ci` from step 3.

   Note the PR number in the spec PR below.

5. **Close the task.** When steps 2–4 have passed, open a small spec PR that sets
   `v1-e01-t04-ci-pipeline` to `Succeeded`, per `docs/process/task-workflow.md`, and records the two
   `gh run` results and the gate-proof PR number.

## Follow-up work

* **`site/README.md` § Continuous integration is now stale.** It says ci.yml does not exist and that
  the job belongs to v1-e01-t04. It is outside this task's packages; a one-paragraph edit in the next
  `site/` task (v1-e36-t04) or a docs PR should point it at the `site` job.
* **The link check also runs as a pre-commit hook, but there is no dedicated CI job for it.** In CI it
  runs only inside the test suite (`tests/docs`), which is why `**/*.md` is in the `python` filter.
  If the filter grows unwieldy, a small unfiltered `docs-links` job running
  `scripts/check_links.py` would let `**/*.md` come out of `python`. That is a PM call, for whichever
  task next touches ci.yml.
* **Terraform provider downloads are not cached.** Each root and module `init` fetches the AWS
  provider. It only runs on infrastructure PRs, and the lock files carry only a `darwin_arm64` `h1:`
  hash (v1-e29-t02 follow-up), which stops a plugin cache from being reused on Linux. Worth
  revisiting only if the first run shows `terraform-checks` near the budget.
* **The rulesets are not in code.** Step 3 is a click-path. If they ever move into Terraform or a
  script, `ci` is the only context to require.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

Accepted, merging `--partial`. `green-run` and `gate-proof` are correctly NOT RUN: the first needs
ci.yml to exist on dev, the second needs a ruleset change, and neither is a session's to make. This
is the first session to reach that conclusion on its own rather than reporting `Succeeded` with
criteria open — the kickoff template now names the partial case, and it worked.

**All three deviations are accepted, and two of them are my spec being wrong.**

1. **The wider `python` filter is the important one, and the reasoning is exactly right.** The
   default pytest selection validates every spec, checks links and anchors across every tracked
   Markdown file, lints the shell under `ops/` and reads the profile TOMLs under `config/`. The four
   paths the spec named would have let a docs-only pull request merge green and fail the next Python
   one — which is how a gate stops being believed, and this repository already has the scar: a
   `ruff format --check` failure rode on dev from #53 to #70 because pre-commit only sees staged
   files. Amended.
2. **The `site` job.** I checked `v1-e36-t03`: it says the site job in `.github/workflows/ci.yml`
   "is added by v1-e01-t04 (or by this task if ci.yml exists)". The hand-off was written down; t04's
   spec just never mentioned it. Amended to name it alongside `terraform-checks`.
3. **`lint` and `spec-validate` unfiltered.** ac1 requires `check-merge-conflict` over every tracked
   file and `validate_specs.py` on every trigger; a path-filtered job cannot honour either. The
   description generalised "each job runs only when its area changed" one step too far. Amended, with
   the exception stated rather than left to be rediscovered.

In all three the session read the criteria against the description, found the description weaker,
and implemented the criteria while writing the conflict up. That is the right order every time.

**Verified rather than taken on trust.** actionlint 1.7.12 with shellcheck; the aggregate `ci`
job's logic exercised against seven simulated outcomes, which is the part most likely to be subtly
wrong — an `if: always()` aggregate that treats "skipped" as "passed" is a gate that passes when a
job crashes before its filter is evaluated. `spec_index.py --check` guarded on `github.base_ref`,
not `github.ref`, which is the amendment from `v1-e01-t05` ac4 honoured correctly.

**`terraform-checks` not run locally is fine and correctly disclosed** — the machine has Terraform
1.7.3 against a pinned 1.16.3. That job is path-filtered on `infrastructure/`, so it will not run
on this PR either; its first real exercise is the next infrastructure change, and that is worth
knowing rather than papering over.

**What remains, in order, and the order matters.** Merge first, because GitHub only offers `ci` as
a required check once it has run at least once — requiring it before then is not possible, not
merely awkward. Then the two `gh run list` checks on dev, then the rulesets, then the throwaway PR.
The throwaway PR is the only one of the four that proves the gate rather than the workflow: a green
`ci` proves the jobs run, and only a blocked merge proves they matter.
