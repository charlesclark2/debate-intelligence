# Session report: v1-e01-t16-generated-docs-index

| | |
|---|---|
| Task | `v1-e01-t16-generated-docs-index` — Generate the docs index instead of hand-editing it |
| Spec | [`plan_specs/v1/e01-repo-foundation/t16-generated-docs-index.yaml`](../../plan_specs/v1/e01-repo-foundation/t16-generated-docs-index.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t16-generated-docs-index` |
| Session status | PARTIAL. Everything a session can run passed. The Goal stays `InProgress`: ac5's proof ("a promotion PR no longer failing for this reason") needs the workflow running on `dev` and then a real promotion, which only exist after this merges (operator follow-ups 1 to 3). Merge with `scripts/task pr --partial` |

## Summary

`scripts/docs_index.py` now generates the table in `docs/README.md` from the files under `docs/`,
on the model of `scripts/spec_index.py`: the same BEGIN/END GENERATED markers, `--check`, and
`--root`. Each row's description is the document's own first line,
`<!-- docs-index: <one line> -->`. That line is invisible when rendered and is copied verbatim. A
document without it fails every mode of the generator, which names the file.

The 27 descriptions were seeded verbatim from today's rows, and all 27 rows come out byte-identical.
Six rows change, each explained under ac3. Three documents in `docs/data/` never had a row, which
is the staleness this task exists to end, found by the generator on its first run.

For ac5 I chose a bot pull request. `.github/workflows/refresh-generated-files.yml` runs on every
push to `dev`, regenerates `ROADMAP.md` and `docs/README.md`, and keeps one **Refresh generated
files** pull request open while either is stale. It gets its required `ci` the way
`dev-prerelease.yml` starts `validate-dev`: a second job holding only `actions: write`
dispatches `ci.yml` on the branch. `ci.yml` gains a `workflow_dispatch` trigger for that.

On pull requests, `docs_index.py --check` runs exactly where `spec_index.py --check` does: pull
requests into main. A new `--check-descriptions` runs on every trigger. It never compares against
the committed index, so it cannot make two task PRs conflict or ask a session to regenerate
anything.

Working agreement 3 and the kickoff prompt now ask for the comment instead of an index line, and
both cite this task. The promotion checklist row now points at the refresh PR.

**PM, look first at:**

* The forbidden entry "Regenerating in a commit hook or in CI" against the workflow ac5 asked for
  (Deviations, first item). I think the property holds and the wording needs amending.
* The force-push fallback in the workflow (Decisions, ac5). I could not verify whether GitHub
  refuses a workflow-token force-push that moves the branch across a change to
  `.github/workflows/`, so the workflow handles both answers.
* The residual human step: someone still merges the refresh PR. Auto-merge would break `dev`'s
  pre-release chain (Decisions, ac5).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| Generator and check (`describe-and-generate`) | Done | Tests written first. The four drift tests, plus the changed-description and never-writes tests, were shown failing against a `--check` stubbed to report "up to date" (commit `bff1a68`), then the comparison went in. 28 tests in `tests/scripts/test_docs_index.py` |
| Reconcile with the committed index (`reconcile`) | Done | Comments seeded by script from the committed rows, so no description was retyped. The set comparison and the six changed rows are under ac3 |
| Correct the agreement and the kickoff prompt (`agreement-and-prompt`) | Done | With ac5's workflow and `ci.yml` wiring in the same commit, because the agreement has to describe the mechanism. 8 workflow-shape tests in `tests/scripts/test_refresh_generated_files_workflow.py` |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — the table is generated from `docs/`, descriptions come from the documents, the source is stated in the docstring, and a document without one fails naming the file | PASS | `scripts/docs_index.py`'s docstring states the convention: first line, exact form, verbatim, `\|` for a pipe; a directory with a `README.md` gets one row; hidden files are skipped. The script contains no description. `uv run --frozen python scripts/docs_index.py --check-descriptions` with an undescribed `docs/runbooks/zz-scratch.md` → `docs/runbooks/zz-scratch.md: the first line must be ...`, exit 1. Tests `test_a_document_without_a_description_fails_naming_the_file[mode0-2]` (all three modes), `test_every_document_without_a_description_is_named_in_one_run`, `..._below_the_first_line_is_reported_where_it_is`, `test_an_empty_description_fails`, `test_an_unescaped_pipe_fails_...`. The mutant that accepts a missing description is caught by 5 tests (Mutation) |
| ac2 — `--check` exits non-zero on drift, is wired into CI like `spec_index.py --check`, and each of the four drift cases has its own test | PASS | `test_check_catches_an_added_document`, `..._a_renamed_document`, `..._a_moved_document`, `..._a_deleted_document`. Each was shown failing first (`assert 0 == 1` against the stub), and each is the only test that catches the mutant blind to its case (Mutation). CI: `spec-validate`'s step `if: github.base_ref == 'main'` runs both `--check`s and reports both before failing. Run locally as CI runs it, on a tree with an added document: both stale messages, the `+\| [runbooks/zz-scratch.md]...` diff line, exit 1. `test_docs_index_check_runs_exactly_where_spec_index_check_runs` holds the wiring. The step itself first runs in CI on the next promotion (follow-up 3) |
| ac3 — run against today's tree, the generator reproduces the committed index apart from ordering, and every changed row is explained | PASS | Committed table wrapped in markers unchanged, then a set comparison of rows: `committed rows 30, generated rows 30, identical 27`. The six differences are explained row by row under **Reconciling the index** below. Ordering is now by the linked file's path. `uv run scripts/docs_index.py --check` → `docs/README.md is up to date` |
| ac4 — working agreement 3 and the kickoff prompt stop asking for a hand-written line, say what they ask instead, and cite this task | PASS | Agreement 3 now asks for the first-line comment, says not to edit or regenerate `docs/README.md` in a task, says CI enforces the comment, and links `v1-e01-t16`. `PROMPT` item 7 says the same and cites `v1-e01-t16`; its ROADMAP line now says a workflow refreshes it. `test_the_agreement_and_the_kickoff_prompt_ask_for_the_same_thing` reads both. It failed before the edit (`assert '<!-- docs-index:' in ...`) and passes after |
| ac5 — both generated files stay fresh on dev, the choice is justified, and a promotion PR no longer fails for this reason | NOT RUN (proof); mechanism built and checked statically | The workflow, the dispatch and the justification are under **Decisions**. Static evidence: actionlint clean across every workflow (with shellcheck); 8 shape tests (triggers, `permissions: {}`, each write held by one job, no checkout in the `actions: write` job, no credentials persisted for the generators, `ci` dispatchable, no CI step regenerating). Read-only facts: "Allow GitHub Actions to create and approve pull requests" is on (`can_approve_pull_request_reviews: true`), `delete_branch_on_merge: true`, and `origin/dev` at `9458fb2` has a stale `ROADMAP.md` (`spec_index.py --check` exit 1), so the first push after this merges should open a refresh PR. The proof needs that push and then a real promotion: follow-ups 1 to 3 |
| Node: Docs index tests pass (`uv run pytest tests/scripts/test_docs_index.py`) | PASS | `28 passed in 0.30s` |
| Node: The committed index matches the generated one (`uv run scripts/docs_index.py --check`) | PASS | `docs/README.md is up to date` |
| Node: Repository links still resolve (`uv run scripts/check_links.py`) | PASS | `OK: 1252 relative links and anchors in 168 Markdown files` |

### Reconciling the index (ac3)

Every row in today's table points at a file. The seeded comment is that row's description,
character for character, `\|` included. Rows that differ:

| Row | Change | Why |
|---|---|---|
| `data/2026-27-tournament-schedule.md` | Added | Added in #144 without a row. Description written from its opening paragraph |
| `data/academic-case-sources.md` | Added | Added in #51 without a row |
| `data/caselist-removal-requests.md` | Added | Added in #138 (`v1-e30-t07`) without a row. The description keeps the file's own rule: no school, team code, filename or name |
| `runbooks/` → `runbooks/` (a directory link) | Removed | No document carries it, and adding `docs/runbooks/README.md` would be new content, which is not authorised. Its seven runbooks each have a row, so nothing becomes unreachable. Adding that README later would restore one row, and the seven would then collapse under it |
| `../plan_specs/README.md`, `../ROADMAP.md` | Moved out of the generated table, unchanged, into a hand-written **Outside `docs/`** table below the markers | ac1 scopes the generator to files under `docs/`. Generating them would mean comments in `plan_specs/README.md` and in `ROADMAP.md`'s hand-written head, or a list in the generator, which the forbidden list rules out |

`adr/` and `session-reports/` keep their single rows under a rule rather than a special case: a
directory with its own `README.md` is indexed by that README alone. Their individual records need
no comment. Ordering is by the linked file's path, so `adr/` now comes first and directories are
alphabetical. The hand-written paragraph at the foot is kept, and a new paragraph at the head says
the table is generated and must not be edited.

### Mutation

Each mutant was applied to `scripts/docs_index.py` by `mutate.py` in the session scratchpad, which
ran `pytest tests/scripts/test_docs_index.py -n0 -p no:randomly`, restored the file and asserted
its bytes. The tree was clean after all seven. These tests use no Hypothesis, but each run still
had a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` (working agreement 8). Each batch took under 1.1 s.

| Mutant | Caught by |
|---|---|
| `--check` notices only committed rows that are no longer generated (blind to additions) | `test_check_catches_an_added_document` only |
| `--check` notices only generated rows that are not committed (blind to deletions) | `test_check_catches_a_deleted_document` (and `test_check_never_writes_the_index`, which drifts by deleting) |
| `--check` compares rows by (directory, description) (blind to renames) | `test_check_catches_a_renamed_document` only |
| `--check` compares rows by (file name, description) (blind to moves) | `test_check_catches_a_moved_document` only |
| A document without a comment gets an empty description | 5 tests: the three modes of `..._fails_naming_the_file`, `..._named_in_one_run`, `..._reported_where_it_is` |
| `--check` regenerates the index and reports it fresh (writing instead of checking) | 6 tests: the four drift tests, `..._a_changed_description`, `test_check_never_writes_the_index` |
| `--check` writes the regenerated index and still reports the drift | 5 tests: the four drift tests' "index unchanged" assertion and `test_check_never_writes_the_index` |

No survivors. The four drift mutants are each caught by their own test and by no other drift
test, so the four tests are independent, which is what ac2 asks of them.

### Whole-repo checks

* `uv run --frozen pytest -n auto --cov -m "not slow and not live"` →
  `4215 passed, 1 skipped, 1 warning in 80.22s` (1:22 wall). The skip is
  `tests/evals/parser/test_parser_eval.py:279`, not this task's.
* `uv run --frozen ruff check .` → `All checks passed!`; `ruff format --check .` → `508 files already formatted`;
  `pre-commit run check-merge-conflict --all-files` → Passed.
* `uvx --from actionlint-py actionlint` → no output, exit 0, over all six workflows (shellcheck on PATH, so `run:` blocks are checked too).
* `uv run scripts/validate_specs.py` → `OK: 308 files, 38 epics, 250 tasks, 20 releases`.

## Files changed

* `scripts/docs_index.py` (new): the generator, `--check`, `--check-descriptions`, `--root`.
* `scripts/spec_index.py`: the docstring says who runs it now, and the stale message points at the refresh PR.
* `scripts/task_helper.py`: `PROMPT` item 7 and the corrected ROADMAP line (ac4).
* `tests/scripts/test_docs_index.py`, `tests/scripts/test_refresh_generated_files_workflow.py` (new).
* `.github/workflows/refresh-generated-files.yml` (new) and `.github/workflows/ci.yml`: `workflow_dispatch`, `--check-descriptions` on every trigger, and `docs_index.py --check` in the main-only step.
* `docs/README.md`: markers, the generated table, the **Outside `docs/`** table, and a sentence saying the table is generated.
* The first line of 30 documents under `docs/`: the `docs-index` comment, the one authorised content change.
* `docs/process/working-agreements.md` §3 (ac4); `docs/runbooks/team-website.md`, promotion checklist row 1.
* The spec: `constraints.packages` amended with `docs/runbooks` and `tests/scripts`, under the comment "added on the PM's instruction, 2026-10-07". `scripts/task_helper.py` is covered by `scripts`.

## Deviations from the spec

* **The forbidden entry "Regenerating in a commit hook or in CI, which hides drift rather than
  reporting it" against ac5's first option.** Read literally, the refresh workflow regenerates "in
  CI", and when the forbidden list and the prose disagree, the forbidden list wins. I built it
  anyway, for three reasons:
  * ac5, added by the PM after the forbidden list, names this mechanism, and the PM's brief for
    this session endorses it.
  * The property the entry protects holds, and is tested. Every check in `ci.yml` is read-only
    (`test_no_check_in_ci_regenerates_a_generated_file`, and two mutants in which `--check` writes,
    both caught).
  * The workflow posts no status and passes nothing. It publishes the regenerated files as a pull
    request a person reads and merges, and until then the promotion's `--check` still reports the
    drift.

  I suggest the PM amend the entry to "Regenerating inside a check or a commit hook, which hides
  drift rather than reporting it".
* **`docs/process/task-workflow.md` is left stale.** Its "Changes that are not a task" section
  still says the PM refreshes `ROADMAP.md` by hand in `specs/roadmap-refresh`. The brief authorised
  only the comments, agreement 3 and the runbook row as content changes in `docs/`, so I drafted
  the replacement and reverted it (Follow-up work). The sentence is out of date, not dangerous: a
  hand refresh still works, and the workflow then closes its own PR.
* **ac2's "wired into CI the way spec_index.py --check is"** was carried out, and widened as the
  brief allowed: `--check-descriptions` also runs on every trigger. Without it, a document missing
  its comment would pass its own PR and first fail inside the refresh workflow on `dev`.

## Decisions and assumptions

* **Where the description lives (ac1).** The PM chose the comment. I put it on the **first line**,
  because "near the top" needs a rule that anyone can apply without asking. If the comment is
  further down, the error gives its line number. An unescaped `|` is refused rather than escaped,
  so what the author wrote is exactly what the table shows. The session-report template's comment
  sits above its `TEMPLATE START` marker, so new reports do not inherit it.
* **Directories with a README collapse to one row.** This keeps today's `adr/` and
  `session-reports/` rows as a convention rather than an exception list in the generator. The
  outermost such directory wins.
* **Ordering is by path.** Where a new row lands then depends on the document's path, not on who
  added it.
* **ac5: why a bot pull request and not a check on dev pull requests.**
  * A freshness check on dev PRs fails each task that leaves a generated file stale, which is
    every task that finishes, and so asks sessions to regenerate. That is forbidden, and it is the
    conflict this task exists to remove.
  * The only dev-PR check that is safe is one that never compares against the committed files,
    and that is `--check-descriptions`.
  * A direct push to `dev` is impossible: protect-dev requires a pull request and `ci`, and has no
    bypass list.
* **ac5: how the bot PR gets its checks.** `docs/process/rulesets/protect-dev.json` requires one
  status check, `ci`, from integration 15368 (GitHub Actions), on the head commit. A pull request
  opened or pushed with `GITHUB_TOKEN` starts no `pull_request` workflow, so `ci` would never
  report. `workflow_dispatch` is the one event that token may start, which is how
  `dev-prerelease.yml` already starts `validate-dev`.
  * So `dispatch-ci` (only `actions: write`, no checkout) runs `gh workflow run ci.yml --ref
    bot/refresh-generated-files`. The run's `ci` check lands on the branch head, which is the
    PR's head.
  * On a dispatch, `ci.yml` behaves like a push: every job runs, and the main-only `--check` step
    is skipped because `github.base_ref` is empty.
  * `dev-prerelease.yml` ignores the dispatched run: it requires `event == 'push'` and `head_branch
    == 'dev'`.
* **ac5: why a person still merges the refresh PR.** Auto-merge is off in this repository, and
  enabling it would not help. A merge made with `GITHUB_TOKEN` starts no workflow, so the merge
  commit on `dev` would get no `ci` push run, no dev pre-release and no `validate-dev`, and
  protect-main would block the next promotion from it.
  * What is now mechanical: noticing, regenerating, and opening and updating the PR.
  * What is not: one merge click, which the promotion checklist's first row now asks for.
* **ac5: the force-push fallback.** `back-merge.yml` records that GitHub refuses a workflow-token
  push that would create or update a file under `.github/workflows/`. I don't know whether
  force-moving an existing branch from an older `dev` to a newer one counts, when the workflows
  changed in between.
  * If it does, a plain force-push would jam the branch for good. So on a refusal the workflow
    closes the PR, deletes the branch and pushes a new one. The new branch's only new commit
    touches two Markdown files.
  * `delete_branch_on_merge` is on, so after each merge the next run starts from a new branch
    anyway. The fallback should only matter while a refresh PR stays open across a workflow change.
* **The generators run without a token.** The checkout persists no credentials, and the token
  reaches git only in the push step, through `GIT_CONFIG_*` variables as in `dev-prerelease.yml`.
  The workflow runs only on push to `dev` and on dispatch from `dev`, so it only executes merged
  code.

## Operator follow-ups

These are observations, not long-running commands. None changes anything except the merge in
follow-up 2, which is the ordinary merge of a pull request into `dev`.

**1. After this task's PR merges into `dev`** (expected within ~2 min of the merge): the first
refresh run opens a pull request, and `ci` reports on it.
Where: any terminal with `gh` signed in.

```bash
gh run list --repo charlesclark2/debate-intelligence --workflow refresh-generated-files.yml --branch dev --limit 3
gh pr list --repo charlesclark2/debate-intelligence --base dev --head bot/refresh-generated-files
```

Success looks like: the newest run is `completed success`, and one open pull request titled
`Refresh generated files`. Its diff touches only `ROADMAP.md` (stale on `dev` today), and
`docs/README.md` too if another document landed in the meantime. Then, with that PR's number:

```bash
gh pr checks NUMBER --repo charlesclark2/debate-intelligence --required --watch
gh pr view NUMBER --repo charlesclark2/debate-intelligence --json mergeStateStatus,statusCheckRollup
```

Success looks like: `ci` listed and passing (~5 min, from the dispatched run), and
`mergeStateStatus` `CLEAN`. If `ci` never appears on the PR, the dispatch did not satisfy protect-dev,
and ac5 needs another route. Paste both outputs back. If the run failed instead, paste
`gh run view RUN_ID --repo charlesclark2/debate-intelligence --log-failed`.

**2. Merge the refresh PR**, then confirm the next run finds `dev` fresh.

```bash
gh pr merge NUMBER --repo charlesclark2/debate-intelligence --squash
gh run list --repo charlesclark2/debate-intelligence --workflow refresh-generated-files.yml --branch dev --limit 1
gh pr list --repo charlesclark2/debate-intelligence --base dev --head bot/refresh-generated-files
```

Success looks like: once the newest run completes, it is `success`, and the list prints nothing.
The run's log says `ROADMAP.md and docs/README.md are fresh on dev`.

**3. At the next promotion** (`dev` → `main`), after the checklist's first row: the promotion's
`spec-validate` job passes. Its step `spec_index.py --check and docs_index.py --check (pull
requests into main only)` ran and printed `ROADMAP.md is up to date` and `docs/README.md is up to
date`. That is ac5's "a promotion PR no longer failing for this reason". Record the promotion's PR
number in this report's PM review, or in the PR that sets this Goal to `Succeeded`.

## Follow-up work

* **`docs/process/task-workflow.md`, "Changes that are not a task"**, still describes a hand
  refresh by the PM. Proposed replacement, for a `docs/` PR:
  "`ROADMAP.md` and the table in `docs/README.md` are generated, and task sessions never
  regenerate them. After every merge into `dev`, `.github/workflows/refresh-generated-files.yml`
  regenerates both and keeps one pull request, **Refresh generated files**, open while either is
  stale; it dispatches `ci` on its own branch because a pull request the workflow opens starts no
  checks. Merge it like any other change into `dev`, and always before a promotion (`v1-e01-t16`)."
* **`CLAUDE.md`** still says "the PM refreshes it separately". The instruction it gives, don't
  regenerate ROADMAP in a task, is still right. Only the reason is out of date, and `CLAUDE.md` is
  outside this task's packages.
* **Rollout:** a task PR into `dev` whose `ci` passed before this merges, and which adds a document
  without the comment, can still merge, because "require branches to be up to date" is off. The
  refresh run on `dev` then fails, naming the file, and the fix is one comment line in a `docs/` PR.
  Open task branches that add documents should add the comment before their PR.
* The `runbooks/website-content-accounts.md` row (verbatim from today's index) describes a team
  Google account that ADR-0015 moved away from. That is document content, which this task leaves
  alone.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-08

**Notes:**

Accepted as a partial merge (`scripts/task pr --partial`). The phase stays `InProgress` until
operator follow-ups 1 to 3 have run, and the PM has recorded the promotion that proves ac5.

* **The forbidden entry: amended, as you suggested.** It now reads "Regenerating inside a check or a
  commit hook, which hides drift rather than reporting it". The old wording predates ac5. A workflow
  that publishes the regeneration as a pull request someone reads reports drift; it does not hide
  it. Your tests showing every CI check is read-only are what make that true.
* **ac5's design: accepted.**
  * Choosing a bot pull request over a freshness check on dev PRs is right. A dev-PR freshness check
    fails every task that finishes, which is the conflict this task exists to remove.
  * Dispatching `ci` with `workflow_dispatch` is the pattern dev-prerelease already uses for
    validate-dev.
  * Refusing auto-merge is right: a `GITHUB_TOKEN` merge would leave the merge commit with no `ci`
    push run and no pre-release, and protect-main would block the next promotion from it.
  * One merge click before a promotion is the honest residual.
* **The force-push fallback: accepted.** You could not settle the workflow-file question
  read-only, so handling both answers was the right call. If follow-up 1 or 2 ever shows the
  fallback firing, record it here.
* **ac3:** the reconciliation is exact (27 of 30 identical, each change explained), and the three
  undocumented `docs/data/` files it found are the staleness this task set out to end.
* **The deviations are fixed by the PM in this branch:**
  * `docs/process/task-workflow.md`, "Changes that are not a task", now carries your proposed text;
  * `CLAUDE.md` says why tasks don't regenerate either file, and asks for the `docs-index` comment.

  Both paths are added to `constraints.packages`. `docs_index.py --check` and `validate_specs.py`
  pass on the branch.
* **Not filed:** the `website-content-accounts.md` description. That document's content is what is
  out of date, and it is left for whoever next touches the website accounts.

**Before the PR:** `scripts/task sync`. v1-e34-t10 may have merged and edited
`docs/runbooks/caselist-scheduled-sync.md`. Keep this task's first-line comment and its content
when resolving, and give any document that arrived from `dev` without the comment one, so
`docs_index.py --check-descriptions` passes. Then run `docs_index.py --check`, `check_links.py`,
`validate_specs.py` and the two new test files. Leave `ROADMAP.md` alone: it is stale on `dev`,
and the first refresh PR after this merges is follow-up 1.

### Close-out (PM, 2026-10-08)

All three operator follow-ups have run. ac5 and the remaining node pass, and the Goal is
`Succeeded`.

* **Follow-up 1:** the first push after this merged opened the bot's "Refresh generated files" pull
  request (#174). Its `ci` ran from the `workflow_dispatch`, and it was merged by hand.
* **Follow-up 2:** the next merge into `dev` (#175) made the workflow open the next refresh pull
  request (#176), which was merged the same way. Every refresh since (#179, #181, #183, #188,
  #190, #192) has followed the same path. The force-push fallback has not been seen firing.
* **Follow-up 3:** promotion #184 (2026-10-08, `dev` at `cee3587`) was the first promotion with the
  new step. Its `spec-validate` job's step "spec_index.py --check and docs_index.py --check (pull
  requests into main only)" printed `ROADMAP.md is up to date` and `docs/README.md is up to date`
  at 07:50:14Z, and the promotion merged as `4948961` with no ROADMAP-only pull request before it.
  That is the first of five promotions not to need one.
