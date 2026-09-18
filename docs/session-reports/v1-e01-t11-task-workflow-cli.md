# Session report: v1-e01-t11-task-workflow-cli

| | |
|---|---|
| Task | `v1-e01-t11-task-workflow-cli` — Task lifecycle CLI and session workflow |
| Spec | [`plan_specs/v1/e01-repo-foundation/t11-task-workflow-cli.yaml`](../../plan_specs/v1/e01-repo-foundation/t11-task-workflow-cli.yaml) |
| Epic / release | `v1-e01-repo-foundation` / `v1.0` |
| Branch | `task/v1-e01-t11-task-workflow-cli` |
| Session status | COMPLETE |

## Summary

Bootstrap task done in the PM session, since the tooling it creates didn't exist yet. It adds
`scripts/task` and `scripts/task_helper.py` for the one-worktree-per-task lifecycle, plus
the working agreements (light CI, operator hand-off for commands over ~2 minutes,
documentation locations, descriptive naming), the session report template and the
documentation index. The same change aligns the task specs with the new rules: heavy suites
run outside the PR path, long commands are marked as operator steps, and there is one
`DEBATE_MODEL_MODE` switch.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| Spec-aware helper | Done | `info`, `prereqs`, `ready`, `set-phase`, `prompt`, `new-report`, `verdict`, `pr-body` |
| scripts/task lifecycle commands | Done | Written for bash 3.2 (the macOS default) |
| Workflow, working agreements and report template | Done | Linked from docs/README.md, CLAUDE.md, CONTRIBUTING.md, README.md |
| End-to-end run against a throwaway remote | Done | See below |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| `start` creates the worktree, refuses unmet prerequisites, commits InProgress + report, writes the prompt | PASS | `task start v1-e01-t04-ci-pipeline` → refused, nothing left behind; `task start v1-e01-t03-uv-workspace-tooling` → worktree, branch, commit "Start …", `.task/prompt.md` |
| `pr` gating | PASS | refused with verdict PENDING; after ACCEPTED it validated the specs, pushed the branch and printed the compare URL (no `gh`) |
| `finish` merge confirmation and clean-up | PASS | after a squash merge on the remote: refused while an untracked file existed, then removed the worktree plus local and remote branches; `--abandon` discarded an unmerged task |
| Docs exist and are linked | PASS | `docs/README.md` index |
| Specs valid | PASS | `uv run scripts/validate_specs.py` → OK (219 files, 174 tasks) |

## Deviations from the spec

None.

## Operator follow-ups

1. Optional: install the GitHub CLI so `scripts/task pr` opens PRs directly:
   `brew install gh && gh auth login`.
2. GitHub → Settings → General → Pull Requests: enable **Automatically delete head branches**.

## Follow-up work

- Terraform `plan` criteria (E10–E19) remain session-run; revisit if they exceed 2 minutes once the dev account has real infrastructure.

## PM review

**Verdict:** ACCEPTED

**Reviewed by / date:** PM (Claude), 2026-09-18

**Notes:** Bootstrap task; implemented and verified in the PM session.
