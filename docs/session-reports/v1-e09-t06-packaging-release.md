# Session report: v1-e09-t06-packaging-release

| | |
|---|---|
| Task | `v1-e09-t06-packaging-release` — Packaging and release workflow |
| Spec | [`plan_specs/v1/e09-v1-quality-pilot/t06-packaging-release.yaml`](../../plan_specs/v1/e09-v1-quality-pilot/t06-packaging-release.yaml) |
| Epic / release | `v1-e09-v1-quality-pilot` / `v1.5` |
| Branch | `task/v1-e09-t06-packaging-release` |
| Session status | PARTIAL: the work is done; ac2, publication under ac3 and the install-check node wait for the first stable tag <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

A stable release now has a workflow, `.github/workflows/release.yml`. It starts only on a `vX.Y.Z`
tag, by the tag's shape and by excluding `!v*-dev.*` by name. Before anything is built, the new
`scripts/check_stable_release.py` refuses the tag unless all of these hold, naming each check that
fails:

* the commit is on main's first-parent line;
* it is the merge commit of a pull request from this repository's `dev` into `main`;
* that pull request's dev parent has a green `validate-dev` status posted by GitHub Actions;
* the tag names the version source;
* the release's epics are Succeeded, by `validate_specs.py --require-succeeded`;
* CHANGELOG's section for the tag is written;
* CI's push run on `main` for that commit passed.

That last check is how the full suite is "run": the run that already happened is required, not
repeated. The build reuses `stamp_build.py` with channel `stable`, a `check-wheels` that now also
refuses fixtures, test modules, SQLite sidecars and debate `.docx` files, and the
`install_channel.sh` rehearsal. Only the publish job holds `contents: write`, and it runs no
repository code.

The single version source stays `packages/debate_cli/pyproject.toml`, with a test that names any
workspace pyproject off it, because uv_build reads only static versions. CHANGELOG has
"Not yet released" sections for v1.1 to v1.5.

No tag was pushed and no release was created. ac2 and the publication half of ac3 can only run
after the first stable tag, so the Goal stays **InProgress**. **Look first at** the full-suite
decision and the PM questions at the end.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `version-source` | Done | Static version in five pyprojects plus a consistency check (PM ruling 2). `check-wheels` extended (ruling 6). Real stable wheels built offline in `tests/scripts/test_wheel_contents.py`. |
| `changelog` | Done | v1.1.0 to v1.5.0 sections, newest first, each linking its release spec and saying "Not yet released" (ruling 7). |
| `release-workflow` | Done | `release.yml` and `check_stable_release.py`, with tests on fixtures (ruling 4). |
| `install-check` | Not done; waits for the first stable tag | The README's stable and dev install commands are written. The install itself is the operator's, after the first stable release (ruling 8). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `uv build` makes debate_core and debate_cli wheels at the single version source, and a test inspects their file lists for fixtures, `.env` and data files | PASS | `uv run --frozen pytest tests/scripts/test_wheel_contents.py` → 14 passed in 3.31 s. It copies the tracked build inputs, stamps them for channel stable at `read_version_source()`, and runs `uv build --package debate-core/debate-cli --wheel` with `UV_OFFLINE=1`. Then it asserts: exactly the two wheels at 1.1.0; `check_wheels(...) == []`; no member for which `forbidden_member` names a reason (both wheels hold more than 50 members); every member sits under the package or its dist-info; and the stamped build info says channel stable. The member rules themselves: `tests/scripts/test_stamp_build.py` → 63 passed (10 new refusals, 7 new allowed members). |
| ac2: on a clean machine, installing from the stable tag installs `debate-research`, whose `--version` prints the tag's version, channel stable and env prod | NOT RUN | No stable tag exists, and this session pushes none (ruling 8). The operator block is below. |
| ac3 (refusals): the workflow fails when the commit is not a validated promotion on main, when tag and package version differ, or when the release's epics are not Succeeded; `-dev.N` tags never trigger it | PASS | `tests/scripts/test_check_stable_release.py` → 56 passed. Each check refuses with a hand-written message: a non-`vX.Y.Z` tag (6 shapes); a commit off main's first-parent line; one parent; no merged pull request; a hotfix, site, fork or task head; a head that is not the second parent; no `validate-dev`, or a failure, pending or non-Actions newest status; a version mismatch; an epic InProgress, Pending or Blocked; no release spec; a spec with no epics; a missing or unwritten CHANGELOG section; no CI push run, or one that failed, was cancelled or ran past the wait. Real git covers the first-parent line, a merge's parents and a shallow clone; canned JSON covers the `gh api` client. `tests/scripts/test_release_workflow.py` → 31 passed. Stable tags start it. `v1.5.0-dev.3`, `v1.1.0-dev.137`, `v1.0.1-dev.1`, `v1.5`, `v1.5.0-rc.1`, `v1.5.0.1`, `vnext` and `1.5.0` don't, checked by a matcher that first passes GitHub's documented filter examples. It also covers the permissions per job, no secret, OIDC or PyPI, no expression in a `run:` block, and the job order. |
| ac3 (publication): otherwise the workflow publishes a stable GitHub Release with the changelog notes and the built artifacts | NOT RUN (live) | The YAML is tested: `gh release create "$TAG"` with the wheels, `SHA256SUMS` and `build-info.json`, plus `--verify-tag` and `--notes-file`; no `--prerelease`; and a guard that refuses a moved or already-released tag. It runs for real only on the first stable tag. |
| ac4: CHANGELOG.md has entries for v1.0 to v1.5 referencing their release specs | PASS | `test_the_committed_changelog_has_a_section_for_each_v1_release`: each `## v1.N.0` section exists and links `plan_specs/releases/v1.N.yaml`; only v1.0.0 lacks "Not yet released". |
| Node `version-source`: wheels build | PASS | `uv build --offline --all-packages --out-dir <scratchpad>` → 4 wheels and 4 sdists at 1.1.0, in 0.34 s. Written to the scratchpad, not `dist/` in the worktree. |
| Node `version-source`: wheel contents test passes | PASS | `uv run --frozen pytest tests/scripts/test_wheel_contents.py` → 14 passed. |
| Node `changelog`: CHANGELOG has a v1.5 section | PASS | `grep -c "v1.5" CHANGELOG.md` → 2 |
| Node `release-workflow`: release.yml contains `require-succeeded` | PASS | `grep -n require-succeeded .github/workflows/release.yml` → lines 17 and 102 (the header, and the comment on the check step) |
| Node `release-workflow`: release.yml contains `!v*-dev.*` | PASS | line 56, the trigger's exclusion |
| Node `install-check`: installed CLI reports version | NOT RUN | waits for the first stable tag |
| Node `install-check`: clean install confirmed on a student's macOS laptop | NOT RUN | waits for the first stable tag; operator block below |

**Red runs**, written before the code was right:

* **Version source and wheel members.** The tests ran against `workspace_version_mismatches`
  returning `[]` and the old `forbidden_member`: 13 failed and 64 passed. The 13 were the 3 mismatch
  tests and the 10 new refusals. The real-build tests already passed, since the current wheels hold
  nothing forbidden.
* **Release checks.** I drafted `check_stable_release.py` before its tests, so its red run used a
  copy where every `check_*` function returned a pass first: 39 failed and 16 passed. The 16 are
  pass-path, parsing and plumbing tests: the happy path, `release_of`, `notes`, the committed
  changelog, outputs, SHA validation, git history and the gh client. After this run I added the
  empty-epic test (see the mutants below).

**Mutants**: 23, each a string replacement in a committed file, run against its own test file and
restored with `git checkout HEAD --`. None of these tests uses Hypothesis.

* **22 caught**, every one by an assertion. To make sure of that I changed seven test lookups to
  `.get()`, which turned five of them from a KeyError in the test into an assertion. The 22:
  * on-main always passes;
  * the parent count unchecked, with the dev parent read as `parents[-1]`;
  * an unmerged pull request counted;
  * the head branch, the fork, or the head SHA unchecked;
  * the validate-dev creator unchecked, the oldest status read, or only `failure` refused;
  * tag versus version not compared;
  * an epic's phase not required, or an empty epic list accepted;
  * a "Not yet released" section accepted, or a heading prefix match;
  * CI runs on other branches counted, the oldest CI run read, or only `failure` refused;
  * fixture and tests directories allowed, or the template `.docx` refused;
  * the workspace version not compared;
  * `--prerelease` added to the publish step;
  * the trigger widened to `v*`.
* **The empty-epic mutant survived at first.** No test had a release spec with no epics. I added
  `test_a_release_spec_that_lists_no_epics_is_refused` and it is now caught.
* **1 crashed, not counted:** "stable-tag never refuses". Without that check, every non-stable tag
  raises ValueError in `release_of`, so it is still refused, but by a traceback instead of a named
  refusal. The check's value is the message the PM asked for (ruling 4), and the tests pin it.

## Files changed

* `.github/workflows/release.yml` (new): the stable release workflow.
* `scripts/check_stable_release.py` (new): the pre-build checks and the release-notes extractor.
* `scripts/stamp_build.py`: `forbidden_member` also refuses `tests/` and `fixtures/` directories,
  `conftest.py`, `test_*.py` and `*_test.py`, SQLite sidecars (`-wal`, `-shm`, `-journal`), and any
  `.docx` outside a `templates/` directory. The dev channel's `check-wheels` gains the same refusals.
* `scripts/release_version.py`: `WORKSPACE_PYPROJECTS` and `workspace_version_mismatches()`.
* `tests/scripts/test_wheel_contents.py`, `test_check_stable_release.py` and
  `test_release_workflow.py` (new); `test_stamp_build.py` (new cases).
* `tests/scripts/test_back_merge_workflow.py`: its repo-wide pin of `contents: write` holders gains
  `("release.yml", "publish", "contents")`. My change tripped that check on purpose, and the pin
  records the new holder.
* `CHANGELOG.md`: sections for v1.1.0 to v1.5.0, and an intro saying how the workflow uses them.
* `packages/debate_cli/README.md`: stable install by `install_channel.sh` or by plain
  `uv tool install`.
* The spec: amended per rulings 1 and 2 (below).

## Deviations from the spec

1. **Packages gain `scripts` and `tests/scripts`** (PM ruling 1), recorded in the spec's
   `constraints.packages` with its ruling comment.
2. **No `__about__.py` and no dynamic version** (ruling 2). uv_build reads only a static
   `[project] version`, so one file would need a build-backend change, which the PM asked to be
   consulted on first. Instead:
   * the source stays `packages/debate_cli/pyproject.toml`, where `release_version.py`, the docs
     and `install_channel.sh` already point;
   * every workspace pyproject carries the same number, as #275 bumped all five together;
   * `workspace_version_mismatches()` names any that differ, and the version check and a test use
     it.

   The node's outputs and its test path (`tests/scripts/test_wheel_contents.py`, under ruling 1)
   are amended in the spec. The dev channel, the stamp and `install_channel.sh` are unchanged.
3. **"Runs the full test suite" is a required run, not a new one** (ruling 5). The check job
   requires CI's push run on `main` for the tagged commit to have passed, waiting up to 50 minutes
   if it is still running. A push to main runs the whole default selection (agreement 10), and
   `validate-dev` ran the slow and smoke tiers on the dev parent. That costs no extra test minutes.
   The alternatives were:
   * a `workflow_call` of ci.yml, which needs a `workflow_call:` trigger added to ci.yml (the PM's
     batch), and which on a tag push would rerun the eight-part matrix with coverage;
   * a second copy of the matrix.

   The 50 minutes is ci.yml's push chain (changes, test-selection, test, coverage, ci) at its
   10-minute job limits. I did not measure a real push run's duration.
4. **Wheels only; no sdists are published.** `uv build` makes sdists, but the install path uses
   wheels. `check-wheels` reads only wheels, and an sdist listed in `SHA256SUMS` would break
   `install_channel.sh`'s `sha256sum -c`, since it downloads only wheels, `SHA256SUMS` and
   `build-info.json`. So the release carries exactly what the dev channel's pre-releases carry.
5. **"With the bedrock extra optional" does not match the packages.** No `bedrock` extra exists.
   Bedrock's boto3 comes with `aws`, which debate-cli requires along with every other extra its
   commands wire. The README says no extra is optional at install time. The spec's description
   still says otherwise (question 3 below).
6. **The release check also refuses** an unwritten CHANGELOG section, a moved tag (in the publish
   job) and an already-released tag. The spec does not ask for these. They keep placeholder notes,
   and a tag that changed after its check, from reaching a GitHub Release (its forbidden list:
   "Tag/version mismatches reaching a GitHub Release").
7. **Patch and hotfix releases** must also be promotion merges. The forbidden list says "Stable tags
   on commits not on main or not reached through a validated dev → main promotion", so a `v1.1.1`
   after a hotfix waits for the back-merge and the next promotion.

## Decisions and assumptions

* **"On main" means main's first-parent line.** Every dev commit a promotion merged is reachable
  from main, so reachability alone would let a tag on a dev commit through.
* **The promotion comes from GitHub's own record**, read with `commits/{sha}/pulls`: the merged pull
  request whose merge commit is the tag, with base `main`, head `dev` from this repository, and
  head equal to the second parent. A merge commit's message can be edited, so it is not trusted.
* **`validate-dev` is the newest status of that context on the dev parent, posted by
  `github-actions[bot]`.** A later red nightly status, or one posted by a person, is refused.
* **The release check and the notes** run with `uv run`, because of pyyaml for `validate_specs`.
  The stamp and `check-wheels` stay on `python3`, as in dev-prerelease. The inline metadata states
  no `requires-python`: the single-interpreter check refuses one in a new script, and uv takes
  `.python-version`.
* **The build doesn't restore uv's cache** (`enable-cache: false`), because other refs write that
  cache and a release resolves its rehearsal fresh. The publish job downloads the build's artifact
  and checks out nothing.
* **GitHub picks "Latest" for a release by itself.** `--latest` tripped
  `test_workflow_runners.py`'s `-latest` runner-label guard, and an explicit flag was not needed.
* **actionlint was not run here.** `scripts/actionlint.sh` downloads it and it isn't cached. CI's
  `workflow-lint` job runs it on this pull request, because a workflow changed. ShellCheck 0.11.0,
  actionlint's shell pass, is clean over all 13 `run:` blocks, each extracted with `set -e` under
  bash.
* **A risk in CI:** the offline build in `test_wheel_contents.py` needs uv's built-in build backend,
  which uv uses only when its own version falls inside the pyprojects'
  `uv_build>=0.11.7,<0.12`. Locally that is uv 0.11.7. setup-uv installs the newest uv, and I could
  not find its version here. If it is 0.12 or later, the fixture fails with a message saying so.
  The fix would be to pin uv in setup-uv, which is a ci.yml edit.

Checks run before this report, all on the final commit unless noted:

* **The affected set.** `uv run --frozen python scripts/affected_tests.py` chose 69 of 668 files.
  `--run` reached its 115-second limit at 97%. One `F` in that partial output was
  `test_single_interpreter_source`, caused by my README and inline metadata; I fixed it in
  `c3f0362`. Agreement 10 leaves the full run to the PR's `ci`, and I also ran all 69 files in three
  bounded runs:
  * 34 `tests/scripts` files: 2,027 passed in 49 s;
  * 34 other files: 1,028 passed in 46 s;
  * `test_backfile_import.py`, which held the tail of the run, on its own: 33 passed in 41 s.

  After those runs, the last commit changed only `DEFAULT_WAIT_MINUTES` and the workflow's comments
  and timeout. Its tests were re-run: 102 passed.
* `ruff format --check .`: 1,872 files already formatted. `ruff check .`: all checks passed.
* `pyright packages/debate_cli` (the README is the only change there): 0 errors.
* `lint-imports`: 20 kept, 0 broken.
* `check_thin_handlers.py`: OK, 72 handlers.
* `check_links.py`: 3,466 links OK. `check_command_blocks.py`: OK.
* `uv run scripts/validate_specs.py`: OK, 585 files.

## Operator follow-ups

1. **Dry run of the checks, once this task has reached `main` and before the first stable tag**
   (expected runtime ~30 s). Where: your Mac, in a scratch worktree of main. It only reads GitHub
   through your `gh` login, and it builds nothing. Before the release close-out, expect
   `epics` and `changelog` to be refused. That shows what is left to do. Every other line should
   say `pass`; any other refusal is a problem to fix before tagging. Replace `v1.1.0` with the
   release being cut.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e09-t06-packaging-release
   git fetch origin main dev
   git worktree add --detach ../release-dry-run origin/main
   cd ../release-dry-run
   uv run scripts/check_stable_release.py check --tag v1.1.0 --sha "$(git rev-parse HEAD)" --repository charlesclark2/debate-intelligence --wait-minutes 0
   ```

   Keep the worktree: the tag in item 2 goes on its commit.

2. **Cutting the release** (seconds to push; the workflow then takes minutes, plus up to 50 minutes
   waiting for main's CI push run). Do this only after the dry run says `pass` on every line, at the
   same commit. The tag is immutable once released. Where: the dry run's worktree. Success looks
   like the run's three jobs green and a release `debate-research v1.1.0` without the pre-release
   badge.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/release-dry-run
   git tag -a v1.1.0 -m "debate-research v1.1.0" "$(git rev-parse HEAD)"
   git push origin v1.1.0
   gh run list --workflow release.yml --limit 1
   ```

   Once the run has finished, remove the scratch worktree:

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e09-t06-packaging-release
   git worktree remove ../release-dry-run
   ```

3. **ac2 and the install-check node, after the first stable release** (expected runtime 2 to 4
   minutes, mostly uv's downloads). Where: a student's macOS laptop with `uv` and `gh` installed and
   no checkout. Don't run it on your Mac without the two `UV_TOOL_*` variables pointing at scratch
   directories: a plain install replaces the build the launchd agent runs. Success looks like
   `"version": "1.1.0"`, `"channel": "stable"`, `"environment": "prod"`, then the help text. Paste
   the `--version --json` line back for the report.

   ```bash
   cd "$(mktemp -d)"
   gh api -H "Accept: application/vnd.github.raw" "repos/charlesclark2/debate-intelligence/contents/scripts/install_channel.sh?ref=v1.1.0" > install_channel.sh
   sh install_channel.sh v1.1.0
   debate-research --version --json
   debate-research --help
   ```

4. **Optional, a GitHub setting:** a tag ruleset on `v*` that restricts updates and deletions. Both
   channels already treat tags as immutable; this makes GitHub enforce it. Pruning deletes only
   releases, never tags, so dev-prerelease is unaffected.

## Follow-up work

* **A student's one-line install still needs `install_channel.sh`**, which lives in the repository
  (operator block 3 fetches it with `gh api`). Where students get it, perhaps a release asset or the
  guide's command, is for `v1-e09-t07-team-pilot`'s guide.
* **`docs/process/branching-and-environments.md`, "Releases"**, still says "the release workflow
  (v1-e09-t06)" in its channel table and has no paragraph on cutting a stable release. It is outside
  this task's packages (question 4 below).
* **Pinning uv's version in ci.yml's setup-uv**, if the offline build risk above shows up in CI: the
  PM's ci.yml batch.

**Questions for the PM**, paste-ready:

```text
v1-e09-t06 (packaging and release) — four questions, each with my recommendation.

1. Full suite (ruling 5). release.yml requires CI's push run on main for the tagged commit to have
   passed (the whole default selection, agreement 10), waiting up to 50 min, instead of running it
   again. Options: (a) keep that [recommended: same tests, same commit, zero extra runners];
   (b) add `workflow_call:` to ci.yml in your batch and call it from release.yml (eight more parts
   with coverage on every tag); (c) a second matrix in release.yml.
2. Single version source (ruling 2). Kept static versions in all five workspace pyprojects with a
   test naming any that differ, since uv_build has no dynamic version. Options: (a) keep
   [recommended: no backend change, dev channel untouched]; (b) move to hatchling with one version
   file. A release bump stays a five-file edit under (a).
3. Spec wording. It says "with the bedrock extra optional", but no bedrock extra exists and
   debate-cli requires every extra its commands wire (boto3 comes with aws). Options: (a) amend the
   description to drop it [recommended]; (b) add an optional extra (a packaging change).
4. Docs. branching-and-environments.md's Releases section still names "the release workflow
   (v1-e09-t06)" and doesn't say how to cut a stable release. Options: (a) let this task add a short
   paragraph pointing at release.yml and the dry run (add docs/process to packages) [recommended];
   (b) leave it for t07 or your own edit.
Also confirm: sdists are not published (wheels only, as the dev channel); a patch release after a
hotfix waits for the next promotion (the forbidden list); the check refuses a CHANGELOG section that
still says "Not yet released", so you write it before tagging.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-02

**Notes:**

A stable release can now only come from a validated promotion, checked from GitHub's own records
rather than from anything a person can edit, and refused with a named reason at each step.

1. **ac1, ac3's refusals and ac4 pass.** Real stable wheels are built offline and inspected (14);
   the release checks refuse every case with a hand-written message (56); the trigger is pinned
   against GitHub's documented filter examples, with eight non-stable shapes that never start it
   (31). Red first (13 and 39 failing), and 22 of 23 mutants caught by assertions, the empty-epic
   survivor closed with a test.
2. **The PM read release.yml's triggers and permissions.** Stable tags only, `-dev.N` excluded by
   name; `contents: read` at the top; the check job adds only `pull-requests`, `statuses` and
   `actions` read; only the publish job holds `contents: write`, and it checks out nothing.
3. **Questions answered:** (1) (a), the required CI push run on main, at no extra runner cost.
   (2) (a), static versions with the consistency test. (3) (a), the PM amends the description to
   drop the bedrock extra. (4) (b), the PM writes the Releases paragraph in
   `docs/process/branching-and-environments.md` in the next batch, so this task isn't reopened.
   **Confirmed:** wheels only, as the dev channel; a patch after a hotfix waits for the next
   promotion; the CHANGELOG section is written at the release close-out, before the tag.
4. **Deviations 1 to 7 accepted.** The extra refusals (an unwritten CHANGELOG section, a moved or
   already-released tag) follow the forbidden list.
5. **Watch on this pull request's `ci`:** the offline build needs uv inside `uv_build>=0.11.7,<0.12`,
   and setup-uv installs the newest uv. If `test_wheel_contents.py` fails with that message, the PM
   pins uv in ci.yml in the batch before this merges.
6. **Operator follow-ups wait for v1.1's close-out:** the dry run on main, the tag, and ac2 on a clean
   machine with scratch `UV_TOOL_*` directories. The tag ruleset (item 4) is the coach's choice.
7. **Closing checks:** the affected set (69 files) reached 97% and its files then passed in three bounded
   runs (2,027, 1,028 and 33); ruff, pyright, lint-imports, thin handlers, the links, the command
   blocks and the specs are clean. actionlint runs in this pull request's `workflow-lint` job.
8. **Merge:** `scripts/task pr --partial` once `ci` is green. The Goal stays `InProgress` until the
   first stable release and ac2.
