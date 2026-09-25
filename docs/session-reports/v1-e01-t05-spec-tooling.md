# Session report: v1-e01-t05-spec-tooling

| | |
|---|---|
| Task | `v1-e01-t05-spec-tooling` — PlanSpec validation and index tooling |
| Spec | [`plan_specs/v1/e01-repo-foundation/t05-spec-tooling.yaml`](../../plan_specs/v1/e01-repo-foundation/t05-spec-tooling.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t05-spec-tooling` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The three setup-time scripts are now maintained tooling with 133 tests behind them.
`scripts/validate_specs.py` was restructured around an injectable repository root — `collect(root)`
returns a `SpecTree` holding the errors and everything the tree said — so every rule can be
exercised against a small spec tree instead of `plan_specs/`. Its release ordering now comes from
the file names in `plan_specs/releases/` rather than a hardcoded list, `--status` reports phase
counts per release *and* per epic and names anything Blocked or Failed, and `scripts/spec_index.py`
renders the ROADMAP tables from the same ordering rule so the two can never disagree.
`scripts/check_links.py` is new: it walks every tracked Markdown file, resolves each relative
target on disk and each `#anchor` against GitHub-style heading slugs, and needs no network. It
passes on the repository as it stands — 1,013 relative links and anchors across 123 files, 273 of
them anchors, with nothing broken.

Two things the PM may want to look at first. **The expectations are hand-written, per working
agreement 6.** Each validator rule has a test that breaks one thing in a committed valid fixture
tree and asserts the error message as a literal string; the roadmap renderer is pinned to
`tests/specs/fixtures/minimal_valid/ROADMAP.md`, whose generated section was written by hand from
the spec files beside it, so `--check` passing on that tree compares the renderer with a hand-built
table rather than with its own output. **Writing the tests first found three bugs** that the
ad-hoc versions of these scripts had been carrying: a spec missing `metadata.name` crashed the
validator with a `KeyError` instead of reporting the error it had already recorded; duplicate node
ids were listed once per occurrence (`['x', 'x']`); and the link checker built heading anchors
after code spans had been blanked out, so `## The \`verify\` command` resolved to the wrong slug.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `validator-tests` | Done | `tests/specs/fixtures/minimal_valid/` (2 releases, 2 epics, 3 tasks) plus 59 tests in `tests/specs/test_validate_specs.py`. Root made injectable via `collect(root)` / `--root`. Found the missing-name crash and the duplicate-id message. |
| `status-report` | Done | `--status` prints per-release and per-epic phase counts and a Blocked/Failed list by name, with the release title and epic/task totals on each line. |
| `spec-index` | Done | `spec_index.py` gained `--root`, refuses a ROADMAP that has lost a marker rather than appending a second copy of the tables, reports when nothing changed, and imports its release ordering from the validator. 23 tests. |
| `link-checker` | Done | `scripts/check_links.py` (PEP 723, standard library only) plus 51 tests in `tests/docs/test_check_links.py`. Found the code-span-in-heading bug. |
| `scripts-lint` | Done | Release order read from `plan_specs/releases/*.yaml`; the `scripts/` exclusion removed from the ruff config and the 9 lint findings and 3 unformatted files fixed. |
| `pre-commit-hooks` | Done | `validate-specs` on `plan_specs/` changes, `check-links` on any Markdown change. `spec_index.py --check` deliberately not hooked, with the reason in the config. |

## Acceptance criteria

All commands were run from the task worktree. The spec's criteria name `uv run scripts/<name>.py`,
which resolves the PEP 723 headers; the pre-commit hooks use `uv run --frozen python scripts/...`
instead (see Decisions).

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** every validator rule has a failing-fixture test asserting the exact message, plus a passing minimal tree | PASS | `uv run pytest tests/specs/test_validate_specs.py` → `59 passed`. All 38 rules covered — one test per `tree.err(...)` site in the validator, with the required-fields rule parametrized over all five criteria types (see the list below); `test_minimal_fixture_tree_is_valid` is the passing tree and `test_the_repository_spec_tree_is_valid` runs the same rules over `plan_specs/`. |
| **ac2** `--status` prints phase counts per release and per epic; `--require-succeeded NAME` exits 0 only for Succeeded | PASS | `uv run scripts/validate_specs.py --status` → `v1.0 — Foundation & verified evidence core: 3 epics, 23 tasks — Pending 11, Succeeded 12` then `  v1-e01-repo-foundation: 11 tasks — Pending 4, Succeeded 7` (one such line per epic), ending `No Blocked or Failed tasks.` `--require-succeeded v1-e01-t05-spec-tooling` → `Succeeded`, exit 0; `--require-succeeded v1-e01-t04-ci-pipeline` → `Pending`, exit 1. |
| **ac3** `spec_index.py` regenerates ROADMAP.md deterministically (no diff on a second run); `--check` exits non-zero when stale | PASS | `uv run scripts/spec_index.py` → `ROADMAP.md updated`, then `uv run scripts/spec_index.py --check` → `ROADMAP.md is up to date`, exit 0. A second `spec_index.py` run → `ROADMAP.md is already up to date` with the file unchanged. Staleness proved on a real stale file, not only a fixture: `--root <the dev checkout>` → `ROADMAP.md is stale; run …`, exit 1. Also `uv run pytest tests/specs/test_spec_index.py` → `23 passed`. |
| **ac4** pre-commit runs the validator whenever `plan_specs/` changes; the ROADMAP check is not a hook | PASS | `.pre-commit-config.yaml` contains `validate_specs.py` (the node's `artifact_exists` contentMatch). `uv run pre-commit run validate-specs --files plan_specs/README.md` → `Passed`; `--files scripts/validate_specs.py` → `Passed`; `--files README.md` → `(no files to check) Skipped`. `uv run pre-commit run check-links --files README.md` → `Passed`; `--files scripts/check_links.py` → `Skipped`. No hook has `spec_index.py` as its entry; the only mention of it in the config is the comment saying why it is not hooked. |
| **ac5** `check_links.py` walks every tracked Markdown file, checks targets and anchors, skips code spans and placeholders, needs no network, exits non-zero listing every broken link, and passes on the repository | PASS | `uv run scripts/check_links.py` → `OK: 1013 relative links and anchors in 123 Markdown files`, exit 0. `uv run pytest tests/docs/test_check_links.py` → `51 passed`, covering a missing file, a missing anchor, code spans, fenced blocks, HTML comments, `{{PLACEHOLDER}}` targets, external URLs, and the non-zero exit listing every broken link. No network: the script imports only the standard library, and the whole test suite runs under pytest's `--disable-socket`. |
| **ac6** release order comes from `plan_specs/releases/*.yaml`; `uv run ruff check scripts` passes with no `scripts/` exclusion in the ruff config | PASS | `grep -c RELEASE_ORDER scripts/validate_specs.py` → `0`; `uv run pytest tests/specs/test_validate_specs.py -k release_order` → `5 passed`. `uv run ruff check scripts` → `All checks passed!`, exit 0; `uv run ruff format --check scripts` → `17 files already formatted`. `pyproject.toml` has no `extend-exclude` at all. |
| node `validator-tests`: validator rule tests pass | PASS | `uv run pytest tests/specs/test_validate_specs.py` → `59 passed` |
| node `status-report`: status output tests pass | PASS | `uv run pytest tests/specs/test_validate_specs.py -k status` → `5 passed` |
| node `spec-index`: index generator is deterministic | PASS | `uv run pytest tests/specs/test_spec_index.py` → `23 passed` |
| node `spec-index`: ROADMAP.md is up to date | PASS | `uv run scripts/spec_index.py --check` → `ROADMAP.md is up to date`, exit 0 |
| node `link-checker`: link checker tests pass | PASS | `uv run pytest tests/docs/test_check_links.py` → `51 passed` |
| node `link-checker`: repository links resolve | PASS | `uv run scripts/check_links.py` → `OK: 1013 relative links and anchors in 123 Markdown files`, exit 0 |
| node `scripts-lint`: scripts/ passes ruff | PASS | `uv run ruff check scripts` → `All checks passed!` |
| node `scripts-lint`: release-order tests pass | PASS | `uv run pytest tests/specs/test_validate_specs.py -k release_order` → `5 passed` |
| node `pre-commit-hooks`: hook registered | PASS | `.pre-commit-config.yaml` contains `validate_specs.py` |
| node `pre-commit-hooks`: full spec tree validates | PASS | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases`, exit 0 |

### Regression checks beyond the criteria

| Check | Result |
|---|---|
| `uv run pytest tests/scripts tests/specs tests/docs` | `278 passed in 17.42s` — `tests/scripts/` is what covers the three scripts `ruff format` reformatted |
| `uv run pytest tests/evals` | `115 passed, 1 skipped` (the skip is the pre-existing "6 of 6 pr-subset files are not yet corrected by a person") |
| `uv run pytest tests/smoke` | `12 passed` |
| Every `task_helper.py` subcommand (`info`, `prereqs`, `ready`, `verdict`, `pr-body`) | Output unchanged after its reformat and the two hand-edited long lines |
| `uv run scripts/export_schemas.py --check` | `OK: 7 schemas in packages/debate_core/schemas are up to date` |
| The new tooling against the specs and Markdown already merged to `dev` (read-only, via `--root`) | validator `OK: 283 files, 38 epics, 225 tasks, 20 releases`; link checker `OK: 1021 relative links and anchors in 125 Markdown files` |

### Which test covers which validator rule (ac1)

Document shape: `apiVersion` (`test_api_version_must_be_the_planspec_alpha_version`), unknown kind,
missing `metadata.name`, unparseable YAML, duplicate `metadata.name`, bad `status.phase`, Goal
without `acceptanceCriteria`, epic/task file not holding exactly one Goal and one Plan, release file
not holding one Goal + one Gate + one Plan, release file name that is not a version.

Labels and names: `debate/major-version` against the folder, identical labels across a file's
documents, a release label with no release file, a release label from another major version, the
task-name prefix rule, the release label equalling the release file name.

Plan graphs: empty graph, duplicate node ids, unknown node kind, unresolved `dependsOn`, cycle,
`goalRef` not naming a Goal in the same file, Gate node without `gateRef.name`.

Typed criteria: unknown criteria type, and the required fields of all five types —
`command_succeeds`, `artifact_exists`, `test_passes`, `endpoint_responds` (parametrized) and the
`name` every type needs.

Epics: an epic with no task files, a task whose release differs from its epic's, a task file
outside its epic's folder, an epic Plan missing one of its task files, an epic Plan naming a task
that has no file, a `debate/epic` label naming no epic.

Cross-task prerequisites: a `TaskRef` that resolves to nothing, a prerequisite from a later release,
a cycle in the prerequisite graph.

Releases: a release referencing an epic that does not exist, a release referencing an epic labelled
with another release, an epic no release references.

## Files changed

**`scripts/` (the tooling this task owns).** `validate_specs.py` restructured around
`collect(root) -> SpecTree` with `--root`, release order read from the release files, the `--status`
roll-up, and a clearer message when `--require-succeeded` is handed a name that is not a Goal.
`spec_index.py` gained `--root`, marker validation, an "already up to date" path and the shared
release ordering. `check_links.py` is new. `compare_docx_roundtrip.py`, `export_schemas.py` and
`task_helper.py` changed only because the ruff exclusion that had been protecting them is gone —
formatting, plus two long lines in `task_helper.py`'s pull-request body rewritten to build the same
string from local bindings.

**`tests/specs/`.** `fixtures/minimal_valid/` is a complete little repository root: two release
files, two epics, three task specs and the hand-written `ROADMAP.md`. `spec_tree.py` holds the
helper both test modules share, `conftest.py` puts `tests/specs/` and `scripts/` on `sys.path`
(the project's pytest import mode is `importlib`, which does not do it), and the two test modules
hold 82 tests.

**`tests/docs/`.** `test_check_links.py` (51 tests) and the same small `conftest.py`.

**`pyproject.toml`.** The `extend-exclude` list removed, `force-exclude` kept with its comment
updated. Nothing else in the file was touched, so the concurrent `v1-e34-t02-scheduled-sync` work
has no reason to conflict here.

**`.pre-commit-config.yaml`.** The two new local hooks.

**`ROADMAP.md`** regenerated and **`t05-spec-tooling.yaml`** set to `Succeeded` — see Deviations.

## Deviations from the spec

* **ROADMAP.md was regenerated in this task**, which the standing rule in `CLAUDE.md` forbids. The
  PM directed this explicitly in the kickoff: `ROADMAP.md` is in this task's
  `constraints.packages` and ac3 asks `spec_index.py` to regenerate it. The order was phase to
  `Succeeded` first, then regenerate, then confirm `--check` exits 0. The diff is a status
  catch-up — t02, t05 and v1-e30-t04, whose phases were set in their own PRs after the last
  refresh — and the v1.1 effort total those PRs' spec edits changed.
* **"A new `scripts/spec_index.py`"** (spec description): the script already existed from setup, so
  this hardened it rather than writing it fresh, as the kickoff directed. Same for
  `validate_specs.py`.
* **No broken links to fix.** The kickoff expected `check_links.py` to surface broken links in
  `docs/`, with the caveat that fixing a genuinely wrong target is in scope anywhere but changing
  prose to make a link stop being checked is not. It found none: 1,013 relative links and anchors
  across 123 files all resolve, and no documentation file was edited. Nothing is being left for the
  PM on that front.
* **One out-of-scope edit reverted.** `uv run pre-commit run end-of-file-fixer --all-files` removes a
  trailing blank line from `docs/session-reports/v1-e30-t01-caselist-data-use-policy.md` — a
  pre-existing nit in another task's report, outside this task's packages. It was reverted rather
  than committed here; the hook will fix it the next time that file is touched.
* **The ruff exclusion covered five files, not a directory.** The spec and the kickoff both describe
  "the `scripts/` exclusion". What v1-e01-t03 actually added was an `extend-exclude` list naming
  `compare_docx_roundtrip.py`, `export_schemas.py`, `spec_index.py`, `task_helper.py` and
  `validate_specs.py` — deliberately file by file so that scripts written later were still linted.
  The whole list is gone, which satisfies ac6 and is what the spec intended. The consequence is that
  `task_helper.py`, owned by `v1-e01-t11`, is reformatted here; the kickoff's "behaviour-preserving
  only" rule was held to, and every one of its subcommands was run to confirm identical output.
  The scripts the kickoff warned about — `prelabel_docx.py`, `run_parser_eval.py`,
  `plan_eval_sampling.py`, `parser_corpus_health.py`, `select_eval_files.py` — needed no change at
  all: they postdate v1-e01-t03 and were never excluded, so ruff was already checking them.

## Decisions and assumptions

* **The pre-commit hooks run the scripts through the project environment**, as
  `uv run --frozen python scripts/validate_specs.py`, not through their PEP 723 headers.
  `uv run --frozen scripts/validate_specs.py` fails outright — *"Unable to find lockfile for Python
  script, but `--frozen` was provided"* — and `uv run` without `--frozen` would resolve a separate
  environment per script, which is what the config's header promises not to do. The headers are
  still what make the scripts runnable on their own, which is the form every acceptance criterion
  uses.
* **Both hooks read the whole tree rather than the changed files.** Most of what they catch lives
  between files: a prerequisite naming a task in a later release, an epic Plan that has stopped
  listing one of its task files, a link into a heading renamed somewhere else. The validator takes
  about a second on 282 files and the link checker about the same on 123, so the cost is affordable;
  `pass_filenames: false` is what keeps them honest.
* **`spec_index.py` imports `release_order` from `validate_specs.py`.** One definition of "which
  release comes first", so the roadmap and the `--status` roll-up cannot drift apart. Both live in
  `scripts/` and both are this task's to own. Versions sort numerically, so a future `v1.10` lands
  after `v1.9` rather than after `v1.1`.
* **What `check_links.py` deliberately leaves alone**, documented in the script itself: absolute
  URLs (that would need the network); root-absolute targets such as `/events/`, which are website
  routes rather than files and are already checked against the published pages by
  `site/tests/content.test.ts` and `site/tests/routes.test.ts`; `{{PLACEHOLDER}}` targets, which are
  filled in when a template is used; anything inside a code span, a fenced block or an HTML comment;
  and anchors into files that are not Markdown, whose headings it cannot read. Shortcut reference
  links (`[text][label]`) are not resolved because no file in the repository uses them —
  reference *definitions* are checked.
* **The anchor rule follows `github-slugger`**: lowercase, ASCII punctuation except `-` and `_`
  removed along with Unicode punctuation, spaces hyphenated, and repeated headings suffixed `-1`,
  `-2`. Em dashes and `§` therefore vanish, which is why `### v1.0 — Foundation & verified evidence
  core` is reached as `#v10--foundation--verified-evidence-core`. The tricky cases are parametrized
  with hand-written expectations.
* **No smoke check was added.** `tests/smoke/` covers user-facing surfaces, and these three scripts
  are contributor tooling — no CLI command, API route, web page or job type changed. The equivalent
  guard is that the tests themselves run the tooling over the real repository
  (`test_the_repository_spec_tree_is_valid`, `test_the_repository_has_no_broken_links`).
* **`check_links.py` prefers `git ls-files`** and falls back to walking the tree when git cannot
  answer, which is what lets the tests point it at a temporary directory. Both paths are tested.

## Operator follow-ups

1. **Sync this branch with `dev` before the PR.** `origin/dev` gained three commits while this task
   ran (`v1-e34-t02-scheduled-sync` and two spec/config PRs), so this branch is behind by
   `4c54893`, `8d763a5`, `25f1270`. Nothing here conflicts with them — `pyproject.toml` was touched
   only to delete the `extend-exclude` list, and the new tooling was run against the merged state
   already (validator `OK: 283 files … 225 tasks`, link checker `OK: 1021 … in 125 Markdown files`).
   Where: your Mac, in this worktree. Expected runtime: seconds.
   ```bash
   scripts/task sync v1-e01-t05-spec-tooling
   ```
   Success looks like: a clean merge or rebase, then `uv run scripts/validate_specs.py` printing
   `OK: 283 files, 38 epics, 225 tasks, 20 releases`.
2. **`ROADMAP.md` will be stale again after that sync**, because `dev` has a task spec
   (`v1-e34-t04-full-archive-refresh`) that this branch's tables do not list. That is the designed
   behaviour, not a regression: the PM refreshes the roadmap in a PR of its own, and v1-e01-t04 will
   require `spec_index.py --check` only on pull requests into `main`. If you would rather this PR
   land with the tables current, run this after the sync and amend:
   ```bash
   uv run scripts/spec_index.py && uv run scripts/spec_index.py --check
   ```
   Success looks like: `ROADMAP.md updated` then `ROADMAP.md is up to date`.
3. **Run the full test suite once** before merging. Every suite that touches this task's code was
   run here (`tests/specs`, `tests/docs`, `tests/scripts`, `tests/evals`, `tests/smoke` — 405 passed and
   1 skipped), but the whole default run was left to you under the 2-minute rule.
   Where: your Mac, in this worktree. Expected runtime: 1–3 minutes.
   ```bash
   uv run pytest
   ```
   Success looks like: no failures; paste the last 20 lines back. The only plausible source of a
   surprise is the three scripts `ruff format` reformatted, and `tests/scripts/` covers those.
4. **Install the new hooks** in any clone that already had pre-commit installed — no action needed
   if you run `uv run pre-commit install` per clone, since the hooks are read from the config each
   time. To see them once:
   ```bash
   uv run pre-commit run validate-specs --all-files && uv run pre-commit run check-links --all-files
   ```
   Success looks like: `validate PlanSpecs…Passed` and `check Markdown links and anchors…Passed`.

## Follow-up work

* **`README.md`'s directory table still lists only `validate_specs.py, spec_index.py`** for
  `scripts/`. Adding `check_links.py` is a one-line change but `README.md` is not in this task's
  `constraints.packages`, so it was left alone. Belongs wherever the PM prefers — a docs PR, or
  v1-e01-t04, which touches the tooling story anyway.
* **`v1-e01-t04-ci-pipeline` is the task that runs these three in CI.** Nothing here presumes how:
  the validator and link checker exit non-zero with a list, and `spec_index.py --check` is the one
  that belongs only on pull requests into `main`, per ac4.
* **Setext headings (`Title` over `===`) are not recognised as anchors** by `check_links.py`. No
  file in the repository uses them, so this is a gap rather than a bug; worth knowing if anyone
  writes one, because links into it would be reported as broken.
* **`docs/session-reports/v1-e30-t01-caselist-data-use-policy.md` has a trailing blank line** that
  `end-of-file-fixer` wants to remove. Left as found (see Deviations).

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

Accepted. One thing to do before the PR, in section 3 below.

**Checked directly rather than from the report.**

* `release_order` sorts on `(int(major), int(minor))` parsed out of the file stem, not on the stem
  itself. "Read from the file names" could have meant a lexical sort, which would put `v1.10`
  before `v1.2` and silently misorder every roll-up the day a tenth minor release exists. The
  docstring says `v1.2 before v1.10` in as many words. This is the detail I went looking for and it
  was already right.
* `scripts/check_links.py` declares `requires-python` and **no** dependencies, so it is standard
  library only as the spec's `forbidden` list requires. `validate_specs.py` and `spec_index.py`
  each declare `pyyaml>=6` and nothing else.
* Both hooks are wired, and the comment above them says `spec_index.py --check` is deliberately not
  one, with the reason and the pointer to `v1-e01-t04` requiring it only on pull requests into
  `main`. That is ac4 and the amendment behind it, honoured rather than paraphrased.
* The `scripts/` exclusion is gone from `[tool.ruff]`, with a comment saying which task removed it
  and why.
* `uv run scripts/spec_index.py --check` exits 0 on the branch as it stands, and
  `validate_specs.py --status` prints the per-release and per-epic roll-up, correctly showing the
  one `InProgress` task in v1.1.

**The ROADMAP fixture is the best thing in this task.** ac3 asks for a deterministic generator, and
the obvious way to test that is to run the generator twice and compare — which proves only that the
code is deterministic, not that it is right. Writing the fixture tree's generated section by hand
from the specs beside it makes `--check` a comparison against an independent expectation instead of
against the renderer's own output. That is working agreement 6 applied where it was least
convenient, and the three bugs the tests-first order turned up — the `KeyError` on a spec missing
`metadata.name`, duplicate node ids counted once per occurrence, and anchors built after code spans
were blanked — are the return on it.

**One correction: regenerate ROADMAP.md after the sync, not after the merge.**

The report frames the post-sync staleness as "the designed PM-refresh behaviour rather than a
regression." That is right for every *other* task's branch and wrong for this one. This task owns
`ROADMAP.md` (it is in `constraints.packages`), and the `spec-index` node carries a
`command_succeeds` criterion that `uv run scripts/spec_index.py --check` passes. Leaving the branch
with that check failing ships a PR whose own acceptance criterion is red. The designed behaviour
begins with the *next* task branch, not this one. So: sync, regenerate, confirm `--check` exits 0,
commit, then open the PR.

Note the branch is behind by **four** commits, not three — a fourth spec PR
(`specs/split-schedule-enablement`, which added `v1-e34-t04` and `v1-e34-t05`) merged after the
report was written, so the regenerated table will carry two tasks the session never saw.

**`scripts/task_helper.py` — accepted, and there is no conflict to manage.**
`v1-e01-t11-task-workflow-cli` is `Succeeded` with no branch and no worktree, so nobody is editing
that file. `scripts/` is in this task's own `constraints.packages`, the changes are
formatting-only, and the session ran every subcommand to confirm identical output. Flagging it was
the right instinct; the risk was nil.

**Concurrency.** `v1-e34-t03-sync-monitoring` is running in the other worktree, in
`debate_core.application` and `debate_cli`. No overlap with this task's packages except the
possibility of `pyproject.toml` and `uv.lock`, both on the conflict table in
`docs/process/task-workflow.md`.

**Outstanding at the time of this verdict:** the full `uv run pytest` run, correctly left to the
operator under the two-minute rule. The five suites touching this task's code came to 405 passed, 1
skipped. This verdict stands unless the post-sync full run is red.
