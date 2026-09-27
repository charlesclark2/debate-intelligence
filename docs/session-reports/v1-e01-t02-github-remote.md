# Session report: v1-e01-t02-github-remote

| | |
|---|---|
| Task | `v1-e01-t02-github-remote` — Create GitHub repository, push, and protect main |
| Spec | [`plan_specs/v1/e01-repo-foundation/t02-github-remote.yaml`](../../plan_specs/v1/e01-repo-foundation/t02-github-remote.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t02-github-remote` |
| Session status | COMPLETE |

## Summary

The repository, default branch, both rulesets, merge-method restrictions and secret scanning were
already in place. This session read them through `gh api` and changed no GitHub setting. The new
work is `.github/CODEOWNERS`, the Bug and Task issue forms, an issue-chooser `config.yml`, and a
CONTRIBUTING.md that describes the `task/<task-name>` flow and the no-real-data rule. **The PM
should look at the deviation first.** `protect-main` has 0 required approvals and no bypass actors.
That matches `docs/process/branching-and-environments.md` and the plan's `rulesets` node. It does
not match the Goal's ac2, which asks for 1 approval with admin-only bypass. The live setting is the
correct one, and the spec text should be amended. The one criterion that needs a push, a direct
push to `main` or `dev` being rejected, was not run and is an operator follow-up.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `confirm-remote` (Confirm remote, branches and default branch) | Done | Verification only. `origin` is set; `main` and `dev` exist; default branch is `dev`; public; secret scanning and push protection are enabled |
| `hygiene-files` (CODEOWNERS, issue templates and CONTRIBUTING) | Done | Four files under `.github/`; CONTRIBUTING.md extended after reading the existing version |
| `rulesets` (protect-main and protect-dev rulesets, secret scanning) | Done, with one criterion NOT RUN | Verification only. The rulesets exist and are active; the manual direct-push test is handed to the operator |

## Acceptance criteria

Live state read on 2026-09-21. Each command took about 1 s.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `confirm-remote`: Remote origin is configured | PASS | `git remote get-url origin` → `https://github.com/charlesclark2/debate-intelligence.git` |
| Node `confirm-remote`: Repository is public, with secret scanning and push protection on | PASS | the spec's `gh repo view … \| jq -e '.visibility == "PUBLIC"' && gh api repos/… \| jq -e '…secret_scanning… and …push_protection…'` → `true`, `true`, rc=0 |
| Node `confirm-remote`: Default branch is dev | PASS | `gh repo view … --json defaultBranchRef \| jq -e '.defaultBranchRef.name == "dev"'` → `true`, rc=0 |
| Node `hygiene-files`: CODEOWNERS exists | PASS | `test -f .github/CODEOWNERS` → rc=0 |
| Node `hygiene-files`: Task issue template asks for the spec path | PASS | `grep -c "plan_specs/" .github/ISSUE_TEMPLATE/task.yml` → 4 (a required `spec-path` input) |
| Node `hygiene-files`: CONTRIBUTING links the process doc | PASS | `grep -c "branching-and-environments.md" CONTRIBUTING.md` → 1 |
| Node `rulesets`: Both rulesets are readable via the API | PASS | `gh api 'repos/{owner}/{repo}/rulesets' \| jq -e 'map(.name) \| index("protect-main") != null and index("protect-dev") != null'` → `true`, rc=0 |
| Node `rulesets`: Protection verified by attempting direct pushes (custom) | NOT RUN | A push leaves the worktree, so it is an operator hand-off (see Operator follow-ups). What the configuration shows: both rulesets are `enforcement: active` with a `pull_request` rule, `bypass_actors: []`, and `current_user_can_bypass: "never"`. The last five merged PRs (#65–#69) all arrived by pull request, #66 being `dev`→`main` |
| ac1: main and dev with full history, origin configured, default dev, public, secret scanning and push protection | PASS | Covered by the node checks above. `git ls-remote --heads origin` → `dev 7203e75`, `main 113c722`. `origin/dev` has 71 commits, and `main`'s only commit that `dev` lacks is the promotion merge commit `113c722 Merge pull request #66 from charlesclark2/dev`, which is expected with merge-commit promotions |
| ac2: protect-main requires a PR with 1 approval, dismisses stale approvals, conversation resolution, blocks force-push and deletion, restricts pushes, bypass only for admin | FAIL as worded; the live state matches the process doc | `gh api repos/…/rulesets/23638829` → target `refs/heads/main`, rules `deletion`, `non_fast_forward`, `pull_request` {`required_approving_review_count: 0`, `dismiss_stale_reviews_on_push: true`, `required_review_thread_resolution: true`, `allowed_merge_methods: ["merge"]`}, `bypass_actors: []`. Differences: 0 approvals instead of 1, and no bypass instead of admin bypass. See Deviations |
| ac3: protect-dev requires a PR and blocks force-push and deletion; a direct push to dev or main is rejected | PASS (configuration); push test NOT RUN | `gh api repos/…/rulesets/23638856` → target `refs/heads/dev`, rules `deletion`, `non_fast_forward`, `pull_request` {`required_approving_review_count: 0`, `required_review_thread_resolution: true`, `allowed_merge_methods: ["merge","squash"]`}, `bypass_actors: []`. `gh api repos/…/rules/branches/{main,dev}` → `["deletion","non_fast_forward","pull_request"]` for both. The push test is in Operator follow-ups |
| ac4: CODEOWNERS, bug and task issue templates (spec path field) on dev; CONTRIBUTING links the process doc and the task/<task-name> flow | PASS on this branch | The files are committed here and reach `dev` when this PR merges. `python3 -c "yaml.safe_load(...)"` on all three `ISSUE_TEMPLATE/*.yml` files → `yaml ok`. CONTRIBUTING.md has a "Branches and the task flow" section naming `task/<task-name>` |
| ac5: Secret scanning and push protection enabled | PASS | `gh api repos/charlesclark2/debate-intelligence --jq .security_and_analysis` → `secret_scanning: enabled`, `secret_scanning_push_protection: enabled` |
| Spec validation | PASS | `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases` |

Other settings read, for the record: `deleteBranchOnMerge: true`, as the process doc requires. The
repository allows merge, squash and rebase merges, and the rulesets narrow these per branch.
`protect-main` also has `require_extra_approval_for_unattributed_changes: true`, which the process
doc does not mention. It has no effect while 0 approvals are required.

## Files changed

* `.github/CODEOWNERS`: `@charlesclark2` owns `*`, and `/plan_specs/` and `/.github/` are listed
  explicitly.
* `.github/ISSUE_TEMPLATE/bug.yml`, `task.yml`: GitHub issue forms. Each opens with a notice that
  the repository is public and ends with a required checkbox confirming the issue contains no real
  file, excerpt, disclosure path, school, team code or debater name. The bug form asks for a
  reproduction with invented data and tells the contributor to strip identifying paths from logs.
  The task form requires the `plan_specs/` spec path.
* `.github/ISSUE_TEMPLATE/config.yml`: turns off blank issues and adds a contact link that sends
  corpus-removal requests to the email process in the policy's Removal section.
* `CONTRIBUTING.md`: kept the existing content. Added the no-real-data section, the numbered
  `task/<task-name>` → `dev` → promotion → `main` flow with hotfixes, a note on the rulesets, and
  an Issues section.
* `plan_specs/v1/e01-repo-foundation/t02-github-remote.yaml`: Goal phase set to `Succeeded`.

## Deviations from the spec

1. **protect-main approvals and bypass (ac2 and the Goal description).** The Goal asks for "PR with
   1 approval … admin-only emergency bypass". The live ruleset has 0 approvals and an empty bypass
   list. That is what `docs/process/branching-and-environments.md` "Set now" specifies, and the
   plan's `rulesets` node says to follow that list exactly. The process doc explains the choice:
   GitHub does not let an author approve their own PR, so on a solo-owner repository 1 required
   approval blocks every promotion unless someone uses the bypass. The manual approval is the
   promotion checklist, and from V2 the `production` environment approval. I recorded the
   difference and did not edit the repository. Suggested amendment: change ac2 and the Goal
   description to "0 approvals, empty bypass list, merge method Merge only".
2. **"Restricts pushes" (ac2).** No separate restrict-updates rule exists. Direct pushes are
   blocked by the `pull_request` rule with no bypass actors. That meets the intent, and the spec
   wording could say so.
3. **Extra file.** `.github/ISSUE_TEMPLATE/config.yml` is not in the `hygiene-files` outputs. It is
   inside the task's `.github` package. I added it because a public issue is the wrong place for a
   removal request, which by the policy's own description names a school and team code.

## Decisions and assumptions

* Issue-form links are absolute `github.com/.../blob/dev/...` URLs, so they resolve from the
  new-issue page.
* The forms apply labels `bug` and `task`. GitHub creates `bug` by default. If `task` does not
  exist, GitHub ignores that label. I did not create it, because that is a repository change.
* CODEOWNERS only requests reviews. `require_code_owner_review` is `false` on both rulesets, so
  CODEOWNERS adds no merge gate and cannot block the owner.
* The Goal phase is set to `Succeeded` as the kickoff prompt instructs, although the manual
  direct-push test is still NOT RUN. If the PM wants that test closed before the task counts as
  done, the Goal can go back to `InProgress` and merge with `scripts/task pr --partial`.

## Operator follow-ups

1. **Confirm that direct and force pushes are rejected** (custom criterion on the `rulesets` node;
   expected runtime under 1 minute). This touches nothing on GitHub if the rules work, because
   every push is refused.

   Where: your Mac, any clone of the repository (the main clone is fine).
   ```bash
   cd "$(mktemp -d)" && git clone -q https://github.com/charlesclark2/debate-intelligence.git probe && cd probe
   git commit -q --allow-empty -m "ruleset probe - must be rejected"
   git push origin HEAD:dev;  echo "dev push rc=$?"
   git push origin HEAD:main; echo "main push rc=$?"
   git push --force origin HEAD~1:dev; echo "dev force-push rc=$?"
   cd .. && rm -rf probe
   ```
   Success looks like this: each push prints `remote: error: GH013: Repository rule violations
   found` (or "Changes must be made through a pull request" / "Cannot force-push") and ends with
   `rc=1`. If any push reports `rc=0`, stop and tell the PM. Revert it through a PR, not with
   another force-push.
2. **Optional:** create the `task` label (Issues → Labels → New label) so the Task form's label
   sticks.
3. **PM:** amend ac2 and the Goal description as described in Deviation 1.

## Follow-up work

* `plan_specs/v1/e01-repo-foundation/epic.yaml`, node `t02`, still says "Create the private GitHub
  repo" and "required status checks". Both are out of date: the repository is public, and required
  checks belong to t04, t08 and t10. The epic's ac1 also says "PR template", which is t08. This is
  for the PM; I did not edit the epic.
* `protect-main` has `require_extra_approval_for_unattributed_changes: true`, which is not in the
  process doc. It is harmless at 0 approvals. The process doc could mention it, or it could be
  turned off, when t08 wires the promotion checks.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-09-23

**Notes:**

**The ac2 mismatch is the session's best work and the criterion was wrong.** ac2 asked protect-main
for one required approval with an admin bypass; `docs/process/branching-and-environments.md`,
authoritative since ADR-0013, specifies zero approvals and an empty bypass list, and explains why -
GitHub does not let an author approve their own pull request, so on a solo-owner repository a
required approval deadlocks every promotion. The live ruleset matches the document and is *stricter*
than the criterion besides, because an empty bypass list binds the owner where an admin bypass would
not. Reading the live settings, changing nothing, and reporting the difference was right twice over:
the document was right, and a session should never quietly rewrite branch protection on production.
Amended in `b88c1a5`, along with the epic step that still called the repository private and listed
required status checks as t02's rather than t04's, t08's and t10's.

**`config.yml` is a deviation worth more than the file it adds.** Routing removal requests away from
public issues, because a removal request necessarily names a school and a team code, is the
data-use policy correctly applied to a surface the policy never mentions. Nobody asked for that, and
a public issue tracker on a repository about minors' disclosures is exactly where that gap would
first have been found by someone else. Turning off blank issues belongs with it.

**The issue forms' required no-real-data checkbox** is the same instinct: the repository is public,
an issue is the one place a stranger can put text into it, and a form is the only point where that
can be refused before it is published.

**The Goal should not be `Succeeded` yet, and the session said so.** ac3 requires that *a direct push
to dev or main is rejected*, and the node carries an operator criterion confirming it against a
scratch commit. Reading a ruleset's configuration is not the same as observing it refuse a push -
rulesets can be configured against the wrong target pattern and still look correct in the API. The
push test is two minutes; it runs before the PR, and if it cannot be run the task merges with
`scripts/task pr --partial` and closes when it has.

Everything else - CODEOWNERS scoped to review rather than required approval, CONTRIBUTING.md keeping
what was there and adding the flow, the `task` label left uncreated because it is a repository
change - is correct and correctly bounded.
