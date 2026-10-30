# Session report: v1-e36-t12-prod-build-before-main

| | |
|---|---|
| Task | `v1-e36-t12-prod-build-before-main` — A pull request into main that touches site/ is built for prod before it merges, and site/ never trips the Python tests |
| Spec | [`plan_specs/v1/e36-team-website/t12-prod-build-before-main.yaml`](../../plan_specs/v1/e36-team-website/t12-prod-build-before-main.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t12-prod-build-before-main` |
| Session status | COMPLETE |

## Summary

ci.yml's `site` job now runs the site's prod build and the export checks against it on every pull
request into `main` (`github.base_ref == 'main'`), after the dev build it already ran. It runs the
same command validate-dev's site lane runs: `SITE_ENV=prod SITE_URL=https://wfbdebate.com
site/scripts/export-checks.sh`. So a `hotfix/*` change to `site/` meets the publishing-policy and
consent guards before it merges, not in `site_deploy.sh` afterwards. `site` is already one of the
`ci` check's needs, and `ci` is what protect-main requires, so no ruleset changes.

ci's python filter no longer matches anything under `site/`. Its `'**/*.md'` is now a
paths-filter step of its own that matches every Markdown file outside `site/`. Excluding a path
needs every pattern to match, which a step-wide option sets. Because site/README.md links into
`docs/` and to its own headings, spec-validate now also runs `scripts/check_links.py` on every trigger. A
site-only pull request still has its links checked without selecting any Python test. The PM
should look first at that addition and at the gap described under
[Follow-up work](#follow-up-work): the single-interpreter scan still reads `site/`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `prod-build-before-main` (Prod build before main) | Done | Red tests committed first (`f4cb30c`). The workflow change is `4cd5d4d`. Seven mutants were each caught by the test written for them. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a pull request into main touching site/ runs the prod build and export checks, shown failing on a planted `[[TBD]]`, by workflow tests shown failing first | **PASS** | **Red first**, on the unchanged ci.yml (`f4cb30c`): `.venv/bin/python -m pytest tests/scripts/test_ci_workflow_site_changes.py -p no:randomly -n 0 --tb=line` gave `6 failed, 20 passed`. Among the failures, `test_a_planted_tbd_fails_the_site_job_on_a_pull_request_into_main` failed with `assert not True`: the site job passed a planted `[[TBD]]` on a pull request into main. Its builds were `['SITE_ENV=dev SITE_URL=']`, a dev build only. **Green** (`4cd5d4d`): `26 passed`. The tests run each `run:` step of ci's site job whose `if:` holds, with bash, in a throwaway checkout that holds the real `site/scripts/pre-commit-checks.sh` and `export-checks.sh`, against stub `pnpm` and `node`. A pull request into main runs `[dev build, SITE_ENV=prod SITE_URL=https://wfbdebate.com]`, and the planted `[[TBD]]` fails the job. A pull request into dev still runs the dev build only, and passes. The prod step's `run` and `env` equal validate-dev's site-lane step. **The real build, planted** (this worktree, `pnpm --dir site install --frozen-lockfile --offline`, 3.7 s): on the clean tree, `SITE_ENV=prod SITE_URL=https://wfbdebate.com site/scripts/export-checks.sh` exited 0 in 13.9 s with `Test Files 12 passed (12)` and `Tests 109 passed (109)`. Then `The [[TBD]] results summary.` was appended to `site/content/pages/results.md`. The dev build ci ran before this change (`SITE_ENV=dev site/scripts/export-checks.sh`) exited 0 and printed `Publishing policy problems, which will fail a prod build:`. The new prod step's command exited 1 with `Error [PublishingPolicyError]: Content breaks docs/policies/website-publishing.md and cannot be published:`. The file was restored and `git status --porcelain` came back empty. |
| ac2: a change only under site/ selects no Python tests, and a change under scripts/ still does, by test | **PASS** | Same file. The `changes` job's outputs are evaluated from its paths-filter steps the way dorny/paths-filter evaluates them (picomatch with `dot: true`, `some`/`every`), for the pattern subset ci.yml uses. A test fails on any pattern outside that subset, and actionlint confirms `predicate-quantifier` is a `dorny/paths-filter@v4` input (below). **Red**: `test_a_change_only_under_site_selects_no_python_tests_and_runs_the_site_job[into-dev]` and `[into-main]` failed with `assert 'true' == 'false'`. **Green**: every one of the 152 tracked files under `site/`, alone and all together, plus a new page, gives `python == 'false'` and `site == 'true'`. `scripts/site_deploy.sh`, `scripts/site_smoke.py` and `scripts/check_promotion_source.py` each give `python == 'true'`, alone and alongside a site page. Every tracked Markdown file outside `site/`, plus a new top-level folder's, still gives `python == 'true'`. A push or a dispatch still runs everything. |
| Node: Prod build before main tests pass (`uv run pytest tests/scripts -k workflow`) | **PASS** | The command selects 181 tests in 16 files. In one invocation (xdist, load average 29 from other sessions) it reached my 115-second hard limit. I re-ran it in parts with the same Python and pytest. `.venv/bin/python -m pytest tests/scripts -k "workflow and not test_ci_workflow_test_job"` gave `151 passed in 17.04s`. `tests/scripts/test_ci_workflow_test_job.py` without its four whole-suite collection tests gave `26 passed in 4.91s`. Those four, one at a time with `-n 0`, gave `1 passed` each (30.2 s, 4.8 s, 0.2 s, 11.3 s). That is 181 of 181. |

**Mutants** (agreement 8: each run had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY`; these tests use
no Hypothesis). Each mutant was applied to the committed ci.yml, the test file was run against it,
and the file was restored. Afterwards `git status --porcelain` was empty.

| Mutant | Result | Caught by |
|---|---|---|
| The prod build back to `SITE_ENV: dev` (spec mutant 1) | CAUGHT, 3 failed | `test_a_planted_tbd_fails…`, `test_a_clean_page_passes_the_dev_build_then_the_prod_build…`, `test_the_prod_build_is_the_one_validate_dev_runs…` |
| `site/` back in the python filter by restoring `'**/*.md'` to it (spec mutant 2) | CAUGHT, 2 failed | `test_a_change_only_under_site_selects_no_python_tests…[into-dev]`, `[into-main]` |
| `site/` back in the python filter by dropping `'!site/**'` (spec mutant 2) | CAUGHT, 2 failed | the same two |
| `'scripts/**'` dropped from the python filter (spec mutant 3) | CAUGHT, 3 failed | `test_a_change_under_scripts_still_selects_the_python_tests[…]`, one for each of the three scripts |
| The prod step's `if` set to `github.base_ref == 'dev'` | CAUGHT, 4 failed | the three in the first row, plus `test_a_pull_request_into_dev_is_still_built_for_dev_only` |
| The `markdown` step dropped from the `python` output | CAUGHT, 1 failed | `test_every_markdown_file_outside_site_still_selects_the_python_tests` |
| The `check_links.py` step removed from spec-validate | CAUGHT, 1 failed | `test_site_markdown_still_has_its_links_checked_on_every_pull_request` |

**Checks before the report**

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | `The whole selection is affected: .github/workflows/ci.yml is shared test ground. CI runs it on the pull request; a session does not (working agreement 10).` Nothing run. Agreement 10's operator exception covers conftest, plugins, pyproject and the lock, not ci.yml, so I am leaving the whole selection to the pull request's `ci`. |
| `.venv/bin/python -m pytest tests/architecture tests/specs tests/docs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py -m "not slow and not live"` (the always-run list, plus the link-check tests) | `515 passed in 19.99s` |
| `scripts/actionlint.sh` | exit 0, actionlint 1.7.12 with shellcheck 0.11.0. To confirm it reads the new step, I linted a copy of ci.yml with the input misspelled `predicate-quantifiers`. It exited 1 with `input "predicate-quantifiers" is not defined in action "dorny/paths-filter@v4". available inputs are "base", "filters", "initial-fetch-depth", "list-files", "predicate-quantifier", …` |
| `uv run --frozen ruff format --check .` / `uv run --frozen ruff check .` | `1614 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright tests/scripts/test_ci_workflow_site_changes.py` (no package changed) | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `uv run --frozen python scripts/check_thin_handlers.py` | `Contracts: 19 kept, 0 broken.` / `OK: 68 CLI command and API route handlers within 25 statements` |
| `uv run --frozen python scripts/check_links.py` | `OK: 2982 relative links and anchors in 457 Markdown files` (this report adds two), 1.2 s |
| `uv run scripts/validate_specs.py` | `OK: 509 files, 40 epics, 447 tasks, 22 releases` |
| `uv run --frozen python scripts/check_command_blocks.py --base origin/dev` / `uv run --frozen python scripts/docs_index.py --check-descriptions` | CHECK_COMMAND_BLOCKS / `All 59 indexed documents under docs/ have a description` |

## Files changed

* `.github/workflows/ci.yml`
  * The `site` job has a new step, for pull requests into main only: the prod build and the export
    checks against it.
  * The `changes` job has a second paths-filter step, `markdown` (`predicate-quantifier: every`,
    `'**/*.md'` and `'!site/**'`). The `python` output is now the `python` filter's or that step's.
    `'**/*.md'` left the `python` filter.
  * spec-validate runs `scripts/check_links.py`.
  * The comments say why for each.
* `.github/workflows/validate-dev.yml`: the site-lane header said, in the present tense, that ci's
  site job builds for dev. It now adds that since this task the job also runs the prod build on
  every pull request into main.
* `tests/scripts/test_ci_workflow_site_changes.py` (new, 26 tests): the site job run with stub tools
  for each event, and the path filters evaluated as dorny does.

## Deviations from the spec

* **One addition the spec did not name:** spec-validate now runs `scripts/check_links.py`.
  * Taking `site/` out of the python filter would otherwise stop
    `tests/docs/test_check_links.py::test_the_repository_has_no_broken_links` from running on a
    site-only pull request.
  * That pull request can break it: site/README.md has 9 checkable links: 7 into `docs/` and
    `plan_specs/` and 2 to its own headings. site/scripts/visual-qa-tools/README.md has 2 more, into `docs/`.
  * The ci.yml comment on the python filter warns about exactly this: such a pull request "skips
    the suite and breaks the next PR instead".
  * The step is the same script, takes about a second, and is in `.github/workflows`, inside
    `constraints.packages`.
  * If the PM rules it out, removing it means deleting that step and its test. A broken site link
    would then show first on main's push run.

## Decisions and assumptions

* **Which required check carries the prod build:** ci's `site` job, counted from the files:
  * ci.yml's header says `ci` is "the single required status check on the protect-dev and
    protect-main rulesets". `site` is in its `needs`, with `"site": "site"` in `PATH_FILTER_OF_JOB`.
  * docs/process/branching-and-environments.md says the site lane left "protect-main's required
    list … unchanged".
  * promotion-guard.yml's two checks are for the source and the back-merge, not the content.
  * No ruleset change is needed. I read no ruleset from GitHub; that would be a live call for the
    operator.
* **The prod build is in addition to the dev build, not instead of it.** The dev build is the one
  that must emit the disallow-everything robots.txt (pre-commit-checks.sh says so), and its
  export checks pin that.
  * On a pull request into main the job now builds twice. Locally the prod build and its export
    checks took 13.9 s.
  * It does not run on a push to main or on a dispatch, because the spec asks for pull requests
    into main.
* **The step is gated on `github.base_ref == 'main'`, not on the head branch.** So it runs for every
  kind of pull request into main: a promotion, a hotfix or a site/<slug> head.
  * A promotion that carries a page with a `[[TBD]]` now fails `ci`. That is the runbook's promotion
    precondition 2 ("The prod build is clean"), enforced before the merge.
* **When it takes effect:** a pull request's `ci` runs from its merge with the base.
  * The dev → main promotion that carries this change runs the new step itself, if it touches
    `site/`.
  * `hotfix/*` and `site/<slug>` heads branch from main, so they get the step only once this ci.yml
    is on main.
* **The dorny exclusion is a separate step**, because `predicate-quantifier` applies to every
  filter in a step.
  * An extglob such as `'!(site)/**/*.md'` would have kept one step. I could not verify picomatch's
    extglob behaviour offline, and the `every` form is the one dorny's README documents.
  * The second step costs one more listing of the pull request's files through the API.
* **What is left reading site/ in Python:**
  * `tests/docs/test_check_links.py`, covered as above.
  * `tests/architecture/test_single_interpreter_source.py`, which scans every tracked file
    (see [Follow-up work](#follow-up-work)).
  * `tests/scripts/test_affected_tests.py`, which uses synthetic paths only.
  * `scripts/affected_tests.py` still selects the docs checks for a site Markdown change. That is
    still true of what they read, and on CI it only matters for a pull request into dev whose
    python filter is already true.
* **The `node` stub in the tests stands in for the publishing-policy guard on one rule**:
  `[[TBD]]` is fatal when `SITE_ENV=prod` and printed otherwise.
  * The real guard was run to show the same behaviour (ac1's evidence).
  * The tests prove what the workflow runs and with which settings. The site's own suite and the
    planted run prove what the guard does with them.

## Operator follow-ups

None. The whole selection that ci.yml's change makes affected runs on the pull request's `ci`
(agreement 10). Before this ci.yml is on main, the first real `hotfix/*` or `site/<slug>` pull request
into main touching `site/` will not show the new step (see Decisions); the promotion that carries
it will, if it touches `site/`.

## Follow-up work

* **The single-interpreter scan still reads `site/` (`tests/architecture/test_single_interpreter_source.py`).**
  * It scans every tracked file, so a Python version written into a site page or a site source
    file would fail it on main's push run, not on the site-only pull request.
  * This is not new for most of `site/`: a change to `site/content/*.yaml` or a `.ts` file has never
    matched the python filter (#616 ran only the site checks). The Markdown under `site/` joins that
    class here.
  * The fix is outside this task's packages (`tests/architecture`). Either add `site/` to the
    test's `PERMITTED_DIRECTORIES` as another ecosystem, which it already treats
    `site/pnpm-lock.yaml` as, or accept the gap. This is for the PM.
* **site/README.md's "Continuous integration" section** describes the site job as six `run:` lines,
  all dev. It is outside this task's packages. Proposed addition after that block: "On a pull
  request into `main` the job then runs `SITE_ENV=prod SITE_URL=https://wfbdebate.com
  site/scripts/export-checks.sh`, the prod build validate-dev's site lane runs, in which the policy
  and consent guards are fatal (`v1-e36-t12`)." That edit is a `site/` change, so it can go through
  the site lane.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
