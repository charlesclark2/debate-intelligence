# Session report: v1-e01-t08-branch-promotion-workflow

| | |
|---|---|
| Task | `v1-e01-t08-branch-promotion-workflow` — dev→main promotion workflow and guards |
| Spec | [`plan_specs/v1/e01-repo-foundation/t08-branch-promotion-workflow.yaml`](../../plan_specs/v1/e01-repo-foundation/t08-branch-promotion-workflow.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t08-branch-promotion-workflow` |
| Session status | COMPLETE — the code nodes shipped in #95 (merged `--partial`); the operator closed `ruleset-wiring` and `negative-proof` on 2026-09-26, and the Goal is `Succeeded` in the follow-up spec PR |

## Summary

This task turns the dev→main promotion rule into GitHub mechanics. `scripts/check_promotion_source.py`
has three pure checks: `source`, `template` and `back-merge`. Two workflows run them.
`promotion-guard.yml` posts the `promotion-source` and `back-merge` checks on pull requests into
`main`, with `contents: read` only. `back-merge.yml` runs on push to `main` and opens a labelled
main → dev back-merge PR after a hotfix. There are also three PR templates (task, promotion,
hotfix), and `branching-and-environments.md` now describes all of it.

The code shipped in #95, merged `--partial` after PM acceptance. The operator then closed the two
remaining nodes on 2026-09-26. They tightened protect-main (exports merged in #98, both rulesets
confirmed in the UI) and ran the negative proof: two throwaway PRs in the real repository (#99,
#100) and a full hotfix cycle in a sandbox repository. Every Goal criterion now passes with real
runs, so the Goal is `Succeeded`, in a spec PR of its own as `task-workflow.md` asks.

**For the PM:**

* **Your one open question is answered.** The auto-opened back-merge PR had a green `ci` from the
  push to `main`, and it merged.
* **The sandbox found one gap.** A promotion PR that is already open keeps a stale green
  `back-merge` after a hotfix lands (Follow-up work). It needs a ruling before the first real
  hotfix, but it doesn't block this Goal.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `guard-script` — Promotion guard script | Done | `source`, `template` and `back-merge` subcommands. Exit 0 = pass, 1 = check failed, 2 = could not run. The last one covers a git error and a shallow clone, which the script refuses. 113 hand-written tests. |
| `pr-templates` — Task, promotion and hotfix PR templates | Done | The guidance sits in HTML comments, so an untouched `Dev build:` line reads as blank to the guard. The tests run the real template files through the parser. |
| `guard-workflows` — promotion-guard and back-merge workflows | Done | actionlint is clean, with shellcheck on the run blocks. Neither workflow has had a real run yet (see Operator follow-ups). |
| `ruleset-wiring` — Tighten protect-main and protect-dev | Done (operator, 2026-09-26) | protect-main gained `promotion-source` and `back-merge` as required checks, with strict off, as the PM amended. protect-dev needed no change. Exports merged in #98, and Charlie confirmed both rulesets in the UI. |
| `negative-proof` — Prove the guards with throwaway PRs | Done (operator, 2026-09-26) | Real repository: #99 (task branch into main) and #100 (blank validate-dev). Sandbox `charlesclark2/promotion-guard-sandbox`: hotfix #1, auto-opened back-merge #3, promotion #2. Evidence below. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — task/* → main shows a red `promotion-source` and merging is blocked; dev and hotfix/* pass | PASS | **#99** (`task/throwaway-promotion-guard` → `main`): `promotion-source` failed with ``FAILED: `task/throwaway-promotion-guard` → `main` is not allowed. Only `dev` … or `hotfix/<slug>` …``. `ci` and `back-merge` were green, and the API reported `mergeStateStatus: BLOCKED`, with `promotion-source` the only failing required check. The check runs come from GitHub Actions (app 15368), the source the ruleset requires. **Passing heads:** the real promotion #96 (`dev`) had its source step report `` `dev` → `main`: a promotion``, and sandbox #1 (`hotfix/sandbox-fix`) passed `promotion-source`. |
| ac2 — promotion/hotfix templates have the sections, and `promotion-source` fails while Dev build or validate-dev is blank | PASS | The templates have the sections listed under the `pr-templates` node. **#100** (dev → main, with `Dev build:` filled and `validate-dev run:` blank): `promotion-source` went red, then green after the line was filled in and the description saved, which re-ran it on `edited`. Charlie confirmed this as "fully successful". **#96** was first opened with the default task template, and its template step failed with both lines `missing`. **#99** used an untouched `promotion.md`, and its template step failed with both lines `blank`. The hotfix template's two lines were exercised by sandbox #1 (filled, green). |
| ac3 — an un-back-merged hotfix turns `back-merge` red on the next promotion, and merging a hotfix opens a main → dev PR | PASS | **Sandbox run.** Merging hotfix #1 pushed to `main`, and back-merge.yml run 36287123219 then ran its "Open the back-merge pull request" step. It opened **#3 "Back-merge main → dev"**: author `app/github-actions`, head `main`, base `dev`, label `back-merge`, and the token created that label itself. On promotion #2, the re-run `back-merge` (run 36286890861) failed with ``FAILED: `main` has 1 non-merge commit(s) that `dev` lacks`` and named `378e124c… Sandbox hotfix`. **The PM's question:** #3's required `ci` was satisfied by the push run on `main`'s head commit (app 15368, merge state `UNSTABLE`, not `BLOCKED`), and #3 merged. **After the merge:** `dev` head `0f40bd3` is a two-parent merge commit containing `378e124`, and `main` still exists at `c2184af`. #2's `back-merge` re-ran by itself on `0f40bd3` and passed at 02:01:59Z, 15 s after #3 merged at 02:01:44Z. No second back-merge PR was opened. |
| ac4 — protect-main is merge-only and requires `ci`, `promotion-source`, `back-merge`; protect-dev requires `ci` and allows squash + merge | PASS | Exports in `docs/process/rulesets/` (#98). **protect-main:** `allowed_merge_methods: ["merge"]`; required `ci`, `promotion-source`, `back-merge`; `strict_required_status_checks_policy: false` (strict off, as the PM amended); `bypass_actors: []`. **protect-dev:** `["merge","squash"]`, required `ci`, strict off, `bypass_actors: []`. Charlie confirmed both in the UI. |
| ac5 — the guard script has offline unit tests for every head/base combination and the empty-field cases | PASS | `uv run pytest tests/scripts/test_check_promotion_source.py` → `113 passed in 2.00s`. The tests cover heads into `main` (4 accepted, 21 rejected), 5 heads × 4 bases other than main, empty base and empty head, forks, and half-known repositories. For the template they cover missing, blank, comment-only, CRLF, bold/list forms, first-occurrence and honest "none yet" values. |
| guard-script: Guard script tests pass offline | PASS | `uv run pytest tests/scripts/test_check_promotion_source.py` → `113 passed in 2.00s` (default options: xdist, coverage, `--disable-socket`) |
| guard-script: A dev head into main is accepted | PASS | `uv run scripts/check_promotion_source.py source --base main --head dev` → `OK: \`dev\` → \`main\`: a promotion.`, exit 0 |
| pr-templates: Promotion template asks for the validate-dev run | PASS | `grep -n "validate-dev run:" .github/PULL_REQUEST_TEMPLATE/promotion.md` → line 26 `validate-dev run: <!-- link ... -->` |
| pr-templates: Task template asks for the spec path | PASS | `grep -n "^Spec:" .github/pull_request_template.md` → line 12 |
| guard-workflows: Guard workflow defines the promotion-source job | PASS | `grep -n promotion-source .github/workflows/promotion-guard.yml` → line 38 `  promotion-source:` (job `name: promotion-source`) |
| guard-workflows: Workflows pass actionlint | PASS | `uvx --from actionlint-py actionlint .github/workflows/promotion-guard.yml .github/workflows/back-merge.yml` (actionlint 1.7.12, shellcheck 0.11.0 on PATH) → no output, exit 0. actionlint is not installed on this Mac, so uvx fetched the release binary. |
| ruleset-wiring: Rulesets are readable via the API | PASS | `gh api repos/{owner}/{repo}/rulesets/<id>` after the tightening: that is how the exports in #98 were made, and both files hold the settings listed under ac4. |
| ruleset-wiring: Ruleset settings confirmed in the UI | PASS | Charlie confirmed protect-main (merge commit only, the three required checks) and protect-dev (`ci` required, squash and merge allowed) in the UI, 2026-09-26. |
| negative-proof: Blocked merges observed | PASS | #99: red `promotion-source`, `BLOCKED`. #100: red `promotion-source` on a blank validate-dev line. Sandbox #2: red `back-merge` naming the un-back-merged hotfix. Sandbox #3: opened automatically by back-merge.yml. All throwaway PRs were closed (#99 and #100 closed, sandbox #1–#3 merged). |

Also run: `uv run scripts/validate_specs.py` → `OK: 284 files, 38 epics, 226 tasks, 20 releases`.
`uv run pytest tests/docs tests/specs tests/scripts` → `391 passed`. pre-commit on the changed
files: all hooks pass, including check-links (`OK: 1042 relative links and anchors in 134 Markdown files`).

Back-merge baseline, as briefed: `git rev-list --no-merges --count origin/dev..origin/main` → **0**,
with `origin/main` at `113c722`. `uv run scripts/check_promotion_source.py back-merge --head dev` in
this worktree → `OK`, exit 0. A promotion from the current `dev` passes `back-merge`.

## Files changed

* `scripts/check_promotion_source.py` (new): the guard. Standard library only, PEP 723 header,
  pure checks, and one thin git wrapper (`unmerged_commits`).
* `tests/scripts/test_check_promotion_source.py` (new): 113 tests. All are pure except four
  real-git tests on throwaway repositories under `tmp_path` (local only, no network).
* `.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE/promotion.md`,
  `.github/PULL_REQUEST_TEMPLATE/hotfix.md` (new): task, promotion and hotfix templates.
* `.github/workflows/promotion-guard.yml` (new): `promotion-source` and `back-merge` jobs on
  `pull_request` into `main`, `contents: read`.
* `.github/workflows/back-merge.yml` (new): on push to `main`, opens the back-merge PR.
  `pull-requests: write` on its one job.
* `.github/workflows/ci.yml`: header comment only. It said every PR check lives in this file; it
  now records the promotion-guard carve-out from #92, so the file and the t04 spec agree. Because
  this touches ci.yml, the task PR runs every CI job.
* `docs/process/branching-and-environments.md`: links the three templates, adds "Guards on pull
  requests into `main`", lists the required checks per ruleset, and updates the t08 line under
  "Added as the tasks land".

## Deviations from the spec

1. **Resolved by the PM in 086c798 (strict off).** `ruleset-wiring` asked for "strict: branch must
   be up to date" on protect-main. I recommended against it and did not write it into the operator steps. A promotion merges `dev` into
   `main` with a merge commit, and `dev` never receives that commit. So after the first promotion,
   GitHub reports every later promotion PR as out of date with `main`. The only way to clear that
   is "Update branch", which pushes a merge commit to `dev`, and protect-dev forbids direct pushes.
   The deadlock only breaks with a back-merge after every promotion. The `back-merge` check already
   does what strict mode was meant to do, without the deadlock: it requires every *non-merge*
   commit on `main` to be in `dev`. Strict mode is off today
   (`strict_required_status_checks_policy: false`). The PM amended `ruleset-wiring` to say strict
   is OFF.
2. **Resolved by the PM in 086c798 (the spec now grants `pull-requests: write` only).**
   `back-merge.yml` holds `pull-requests: write` and `contents: read`, not the `contents: write`
   the spec originally granted, and the PR's head is `main` itself rather than a branch copied from it.**
   * *Why not a copied branch:* pushing a copy with the workflow token is refused whenever the new
     commits touch `.github/workflows/`, and that permission can never be given to the token.
   * *What head `main` gains:* the head commit already carries the green `ci` from the push to
     `main`. That matters because PRs opened by the workflow token start no workflows of their
     own, so a copied branch would sit waiting for a `ci` that never comes.
   * *Why merging can't delete `main`:* protect-main restricts deletion with an empty bypass list.
     I still ask the operator to confirm this in the sandbox, because `delete_branch_on_merge` is on.
   * *In short:* less privilege than the spec allows, not more.
3. **Resolved by the PM in 086c798, and now implemented.** The original spec said "with gh using
   the hotfix template label" without naming one, so the first version applied none. The amended
   spec names a `back-merge` label, created if absent. The workflow runs
   `gh label create back-merge --force` (idempotent; the labels API accepts `pull-requests: write`,
   so no `issues: write` is needed). It passes `--label back-merge` on create and adds the label to
   an already-open back-merge PR. The label description, the PR body and
   branching-and-environments.md all say to use a merge commit and never squash. The sandbox run
   (operator follow-up 4c) is the first real check that the token can create the label.
4. **The `back-merge` subcommand checks every non-hotfix head, not only `dev`.** The spec
   describes `dev` heads. A `task/*` head into `main` is already stopped by `promotion-source`, and
   reporting `back-merge` for it too costs nothing. The hotfix exemption is exactly as specified:
   a `hotfix/*` head passes without running git (`test_cli_back_merge_does_not_run_git_for_a_hotfix`).

## Decisions and assumptions

* **A fork can name its branch `dev`.** `source` compares
  `github.event.pull_request.head.repo.full_name` with `github.repository` and rejects a pull
  request from another repository, whatever its branch is called. When the fork has been deleted,
  `head.repo` is null and arrives as an empty string. Empty or half-given repositories fail rather
  than skip.
* **"Blank" means blank after removing HTML comments, not "not a real link".** Pre-releases
  (`v1-e01-t09`) and `validate-dev` (`v1-e01-t10`) are both built after this task. The first
  promotions after t08 therefore have no build id or run link to give. Rejecting "n/a" or
  requiring a URL would block every promotion until t10 merges. The templates tell the author to
  write what exists and what was checked instead; the guard refuses only an empty line.
* **A shallow clone exits 2 instead of answering.** `rev-list` on a depth-1 clone says "nothing
  missing" rather than failing. The script checks `git rev-parse --is-shallow-repository` first,
  so a future edit that drops `fetch-depth: 0` turns the check red, not silently green. Both
  workflows also fetch `main` and `dev` explicitly.
* **Untrusted strings travel through `env`.** Branch names and the PR description never go through
  `${{ }}` inside a `run` block (the script-injection pattern).
* **The guard runs on the runner's `python3`,** with no uv setup: the script is standard library
  only, and this keeps both checks well under a minute.
* **`template` runs even when `source` failed** (`if: ${{ !cancelled() }}`), so a single run
  reports every problem.
* **Known limit: the guard is advisory against a determined PR author.** On `pull_request`, the
  workflow file and the script both come from the PR's own merge commit. A PR that edits them can
  turn its own checks green. That is inherent to `pull_request`. The fix, running from the base
  branch, would mean `pull_request_target`, which the task forbids for good reason. What stops a
  hostile PR is that only the repo admin can merge into `main` and the diff shows the edit. See
  Follow-up work.
* **Real-git tests alongside the pure ones.** The brief asks for ac5 to be pure functions with no
  git, and those tests are. I added four more that run real git on throwaway repositories under
  `tmp_path`. They are the only offline evidence that `rev-list --no-merges` reads each history
  shape correctly, and none of them touches a network. They clear `GIT_*` variables and use
  `GIT_CONFIG_GLOBAL=/dev/null`, so neither the surrounding worktree nor user config leaks in.

## Operator follow-ups

**All done on 2026-09-26.** Everything below was run by the operator: the promotion (#96), the
Actions setting, the ruleset change, the exports (#98) and the negative proof (#99, #100, sandbox
#1–#3). It is kept as the record of what was run. One step is still open: deleting the sandbox
repository needs a `gh` token with the `delete_repo` scope (see Follow-up work).

Two corrections to the commands, learned during the run. **`gh pr checks --watch` straight after
`gh pr create`** returns at once with "no checks reported", because GitHub hasn't registered the
checks yet, so a `gh pr merge` that follows it is refused. Wait about 15 seconds, or re-run the
watch. The same applies to `gh run list --limit 1` straight after a push; filter it with
`--commit <sha>`.

Run these in order. Steps 2–4 depend on this task being on `main`, not only on `dev`.

**1. Merge this task into `dev`, then promote `dev` → `main` as usual.** `hotfix/*` branches are
cut from `main`. Until `promotion-guard.yml` is on `main`, a hotfix PR's merge ref has no such
workflow, so a required `promotion-source` would wait forever and block the hotfix. The promotion
that carries this task runs both checks on itself, which is a free first run. Its body needs the
two lines filled, e.g. `Dev build: none yet, v1-e01-t09 has not merged` and
`validate-dev run: none yet, v1-e01-t10 has not merged; <what you checked by hand>`. Watch that
both checks report on that PR. If they don't, stop before step 2.

**2. Tighten protect-main (the `ruleset-wiring` node).** GitHub → Settings → Rules → Rulesets →
**protect-main** → *Require status checks to pass* → **Add checks**. Type `promotion-source` and
choose source *GitHub Actions*, then do the same for `back-merge`. Keep `ci`. Leave **Require
branches to be up to date before merging unchecked**, pending the PM's ruling on Deviation 1.
Merge methods stay *Merge* only. **protect-dev needs no change:** it already requires `ci` and
allows squash and merge. The same change from the terminal, if you prefer (a mutation, so yours
to run):

```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence   # the main checkout
gh api repos/{owner}/{repo}/rulesets/23638829 \
  | jq '{name, target, enforcement, conditions, bypass_actors, rules: [.rules[]
         | if .type == "required_status_checks"
           then .parameters.required_status_checks += [
                  {"context": "promotion-source", "integration_id": 15368},
                  {"context": "back-merge", "integration_id": 15368}]
           else . end]}' > /tmp/protect-main.json
gh api -X PUT repos/{owner}/{repo}/rulesets/23638829 --input /tmp/protect-main.json --jq '.rules'
```

Then export both rulesets for review (the node's outputs) and commit them in a follow-up PR into `dev`:

```bash
mkdir -p docs/process/rulesets
for pair in protect-main:23638829 protect-dev:23638856; do
  gh api "repos/{owner}/{repo}/rulesets/${pair#*:}" \
    | jq 'del(._links, .node_id, .created_at, .updated_at, .current_user_can_bypass)' \
    > "docs/process/rulesets/${pair%%:*}.json"
done
jq '.rules[] | select(.type=="required_status_checks").parameters' docs/process/rulesets/*.json
```

Success looks like: protect-main shows `ci`, `promotion-source`, `back-merge` and
`"strict_required_status_checks_policy": false`, and protect-dev shows `ci`.

**3. Let Actions open pull requests.** Settings → Actions → General → Workflow permissions:
keep *Read repository contents* and tick **Allow GitHub Actions to create and approve pull
requests**. Today it is off (`can_approve_pull_request_reviews: false`). Until it is on,
`back-merge.yml` fails at `gh pr create`, and that failure is the signal to back-merge by hand.
The setting also lets Actions approve PRs. Both rulesets require 0 approvals, so that grants
nothing new.

**4. Negative proof (the `negative-proof` node), about 30–40 minutes including CI waits.**

*a. A task branch into main must be blocked* (real repository):

```bash
git fetch origin && git switch -c task/throwaway-promotion-guard origin/dev
git commit --allow-empty -m "Throwaway: promotion-source must fail"
git push -u origin task/throwaway-promotion-guard
gh pr create --base main --head task/throwaway-promotion-guard \
  --title "Throwaway: task branch into main" --body-file .github/PULL_REQUEST_TEMPLATE/promotion.md
```

Expect a red `promotion-source` that says ``... → `main` is not allowed``, with both template lines
blank, and "Merging is blocked". Then run
`gh pr close --delete-branch task/throwaway-promotion-guard`.

*b. A promotion with a blank validate-dev line must be blocked:* open the next real promotion
`dev` → `main` with `?template=promotion.md` and only `Dev build:` filled. Expect a red
`promotion-source` with `"validate-dev run:" is blank`. Fill the line and save: the check re-runs
on `edited` and goes green. (If you'd rather not use a real promotion, do this in the sandbox in c.)

*c. An un-back-merged hotfix* (sandbox repository, so production `main` is never touched):

```bash
SANDBOX=charlesclark2/promotion-guard-sandbox
gh repo create "$SANDBOX" --public --description "Throwaway for v1-e01-t08 negative proof; delete afterwards"
git push "https://github.com/$SANDBOX.git" origin/main:refs/heads/main origin/dev:refs/heads/dev
gh repo edit "$SANDBOX" --default-branch dev --delete-branch-on-merge
gh api -X PUT "repos/$SANDBOX/actions/permissions/workflow" \
  -f default_workflow_permissions=read -F can_approve_pull_request_reviews=true
for id in 23638829 23638856; do   # copy protect-main and protect-dev as they are after step 2
  gh api "repos/{owner}/{repo}/rulesets/$id" | jq '{name, target, enforcement, conditions, bypass_actors, rules}' \
    | gh api -X POST "repos/$SANDBOX/rulesets" --input - --jq .name
done
git switch -c hotfix/sandbox-fix origin/main && echo sandbox > SANDBOX_HOTFIX.txt
git add SANDBOX_HOTFIX.txt && git commit -m "Sandbox hotfix"
git push "https://github.com/$SANDBOX.git" hotfix/sandbox-fix
gh pr create --repo "$SANDBOX" --base main --head hotfix/sandbox-fix --title "Sandbox hotfix" \
  --body $'Dev build: sandbox\nvalidate-dev run: sandbox'
gh pr checks --repo "$SANDBOX" hotfix/sandbox-fix --watch     # ci, promotion-source, back-merge all green
gh pr merge --repo "$SANDBOX" hotfix/sandbox-fix --merge
gh run list --repo "$SANDBOX" --workflow back-merge.yml --limit 1   # wait for it to finish
gh pr list --repo "$SANDBOX" --base dev --head main                 # expect "Back-merge main → dev"
gh pr create --repo "$SANDBOX" --base main --head dev --title "Sandbox promotion" \
  --body $'Dev build: sandbox\nvalidate-dev run: sandbox'
gh pr checks --repo "$SANDBOX" dev --watch    # expect back-merge red, naming the "Sandbox hotfix" SHA
```

The back-merge PR must carry the `back-merge` label. If the job failed at `gh label create` with a
403, the token cannot create labels: create it once with `gh label create back-merge --repo "$SANDBOX"`
(and in the real repository), re-run the job, and tell the PM.

Then merge the back-merge PR in the sandbox with **Create a merge commit**. Expect four things:

* its `ci` requirement is already satisfied by the push run on `main`'s head commit (Deviation 2
  relies on this);
* the sandbox's `main` branch still exists afterwards;
* the promotion PR's `back-merge` turns green on the re-run triggered by the push to `dev`;
* no second back-merge PR opens.

Clean up with `gh repo delete "$SANDBOX" --yes` and `git branch -D hotfix/sandbox-fix`. Paste the
`gh pr checks` outputs, or screenshots of "Merging is blocked", back into the task.

Once Charlie confirms steps 2 and 4, set the Goal to `Succeeded`:
`uv run scripts/task_helper.py set-phase v1-e01-t08-branch-promotion-workflow Succeeded`.

## Follow-up work

* **v1-e01-t09 / v1-e01-t10:** once pre-releases and `validate-dev` exist, `template` could
  require `validate-dev run:` to be a link to a run of that workflow. That also needs the
  "none yet" paragraphs removed from both templates and from branching-and-environments.md.
* **v2-e12-t07-promotion-pipeline** (or an E01 hardening task): the guard runs the PR's own copy of
  itself (see Decisions, "Known limit"). If that ever matters beyond an admin-only merge, the
  options are a GitHub App token check run from the base branch, or the ruleset "require
  workflows" feature where the plan allows it.
* **PM ruling needed before the first real hotfix: a stale green `back-merge` on an open
  promotion PR.** The sandbox reproduced it. Promotion #2 was open before hotfix #1 merged, and
  it kept `back-merge pass` after the hotfix landed. Merging into `main` doesn't re-run the checks
  on PRs already open against it, GitHub has no "base branch moved" event, and strict mode is
  (rightly) off. Until something re-runs the check, that promotion can merge with prod running a
  combination dev never validated. No content is lost, and the next promotion's `back-merge`
  catches it, but it is exactly what the check is meant to stop. Two options:
  * **Process only:** after a hotfix merges, re-run the checks on every open promotion PR (re-run
    the job, or edit the description). Say so in the hotfix template and
    branching-and-environments.md.
  * **Mechanical:** give `back-merge.yml` `actions: write` on its push-to-main job, and have it
    re-run `promotion-guard.yml` for open PRs into `main`. The job never runs PR code, so the
    permission is as safe as the existing `pull-requests: write`. It is a spec change to
    `guard-workflows`, so an E01 hardening task.

  I'd take the mechanical option. It is about ten lines, and the process-only option depends on
  remembering it during an incident.
* **Operator: delete the sandbox repository** `charlesclark2/promotion-guard-sandbox`. It is
  public and holds a copy of the repository as of 2026-09-26.
  `gh auth refresh -h github.com -s delete_repo`, then
  `gh repo delete charlesclark2/promotion-guard-sandbox --yes`, or delete it from Settings →
  Danger Zone in the browser.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**

Accepted. Merging `--partial`: `ruleset-wiring` and `negative-proof` are a GitHub settings change
and throwaway pull requests, so the Goal stays `InProgress` until the operator has run them. The
verdict is my review of the session's work, which is complete; the phase is the Goal's completion,
which is not. They disagree here on purpose.

**All three decisions go the session's way, and one of them corrects the spec.**

1. **"Require branches to be up to date" stays OFF on protect-main.** The spec's `ruleset-wiring`
   node asked for strict and the session found it unusable: a dev-to-main promotion leaves a merge
   commit on main that dev never receives, so GitHub calls every subsequent promotion out of date,
   and its "Update branch" button pushes straight to dev, which protect-dev forbids. `back-merge` is
   the better guarantee anyway - it asks whether main holds real content dev lacks and ignores the
   promotion merge commits that are inherent to the flow. Amended, with the reasoning, so nobody
   turns it on later thinking it was an oversight.
2. **`pull-requests: write` alone, no `contents: write`.** A PR whose head is `main` creates no
   branch. The sharper half of the argument is the one I would not have thought of: the workflow
   token cannot push a commit touching `.github/workflows/`, so a copied-branch design would fail on
   exactly the hotfixes most likely to touch CI. Asking for less than the spec grants is the right
   instinct and I want more of it.
3. **Yes to a `back-merge` label, and not for the reason the question implied.** The label is a
   warning sign, not organisation. A back-merge must be completed with a merge commit and never
   squashed: a squash writes a new SHA into dev while main's original commit stays unreachable from
   it, so the `back-merge` check goes permanently red and every future promotion is blocked with no
   obvious cause. protect-dev allows both merge methods, so nothing mechanical prevents it. The
   label, the PR body and branching-and-environments.md now all say so.

**Two additions beyond the spec, both accepted and both the right kind.** Rejecting a fork pull
request whose branch is named `dev` closes the hole the `source` check would otherwise wave
through - the repository is public, so that is a live attack and not a hypothetical. Refusing a
shallow clone with exit 2 rather than returning a silent wrong answer is the same instinct that
made the `uv sync` defect visible on the first CI run: a check that is quietly wrong is worse than
one that fails.

**One thing added to `negative-proof` for the operator to confirm.** The session observed that
workflow-token pull requests do not start new workflow runs, and concluded the green `ci` already
attached to main's head SHA covers the back-merge PR. That is probably right, since required checks
are evaluated against the head SHA whatever event produced it. But if it is wrong, the back-merge PR
is unmergeable: `ci` is required on dev and protect-dev's bypass list is empty, so there would be no
way to land it. Cheap to confirm in the sandbox, expensive to discover during a real hotfix.

**The operator ordering is right and worth preserving.** Promote this task to main *before* making
the new checks required. Hotfix branches are cut from main, main does not carry the guard workflows
yet, and a required check that never runs would block the next hotfix - which is precisely the
moment nobody wants to be debugging branch protection.

**Honest note on the guard's self-reference.** The session flagged that a pull request changing the
guard's own files can turn its checks green. That is inherent to `pull_request` triggers and the
alternative - `pull_request_target` - is the privilege escalation this task's forbidden list exists
to prevent. What protects main is that only the repository owner merges into it and the edit is
visible in the diff. Accepted as a documented property rather than a defect.
