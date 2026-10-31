# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Spec-aware helpers for scripts/task (the task lifecycle CLI).

Kept in Python so the shell script stays small and portable (macOS ships bash 3.2).
Every subcommand reads the specs of the checkout it is run from.

  info    <task>                 print tab-separated: spec_path, title, epic, release, phase
  prereqs <task>                 list prerequisites and their phase; exit 1 if any is not Succeeded,
                                 2 if any is not a task spec
  ready                          list Pending tasks whose prerequisites are all Succeeded; a task with a
                                 prerequisite that is not a task spec is left out, and stderr says so
  set-phase <task> <phase>       set the task Goal's status.phase in place
  prompt  <task> <worktree>      render the kickoff prompt for the task's Claude session
  prompt-resumed <task> <worktree>
                                 the same, for a partly merged task that scripts/task resume recreated
  new-report <task>              create docs/session-reports/<task>.md from the template (if absent)
  verdict <task>                 print the PM verdict recorded in the session report
  verdict-of <file>              print the PM verdict recorded in a report file (- reads stdin)
  open-items <task>              print the open-item markers in the current session's part of the
                                 session report; exit 1 if there are none
  pr-body <task>                 render the pull request body
  validate-dev-status            print dev's head and its latest validate-dev status, from GitHub's
                                 combined status for dev on stdin (`gh api .../commits/dev/status`)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NoReturn

import yaml

ROOT = Path.cwd()
SPECS = ROOT / "plan_specs"
REPORTS = ROOT / "docs" / "session-reports"
TEMPLATE = ROOT / "docs" / "process" / "session-report-template.md"
PHASES = {"Pending", "Ready", "InProgress", "Blocked", "Succeeded", "Failed", "Cancelled"}
VERDICTS = ("ACCEPTED", "CHANGES_REQUESTED", "PENDING")
VERDICT_LINE = re.compile(r"^\*\*Verdict:\*\*[ \t]*`?([A-Z_]+)`?", re.M)
SECTION_HEADING = re.compile(r"^## ", re.M)
OPEN_ITEM_MARKERS = re.compile(r"NOT RUN|NOT APPLICABLE|PARTIAL|FAIL")


def die(msg: str, code: int = 2) -> NoReturn:
    print(msg, file=sys.stderr)
    sys.exit(code)


def task_files() -> dict[str, Path]:
    out = {}
    for p in SPECS.glob("v*/e*/t*.yaml"):
        m = re.search(r"^  name: (\S+)$", p.read_text(), re.M)
        if m:
            out[m.group(1)] = p
    return out


def goal(path: Path) -> dict:
    for d in yaml.safe_load_all(path.read_text()):
        if d and d.get("kind") == "Goal":
            return d
    die(f"{path}: no Goal document")


def find(task: str) -> tuple[Path, dict]:
    files = task_files()
    if task not in files:
        close = [n for n in files if task in n]
        hint = f" Did you mean: {', '.join(sorted(close)[:5])}?" if close else ""
        die(f"No task spec named '{task}'.{hint}")
    return files[task], goal(files[task])


def phase_of(g: dict) -> str:
    return (g.get("status") or {}).get("phase", "Pending")


def prereq_names(g: dict) -> list[str]:
    return [
        c["name"]
        for c in (g["spec"].get("context") or [])
        if c.get("kind") == "TaskRef" and c.get("relation") == "dependsOn"
    ]


def cmd_info(task: str) -> None:
    path, g = find(task)
    labels = g["metadata"]["labels"]
    print(
        "\t".join(
            [
                path.relative_to(ROOT).as_posix(),
                g["metadata"]["annotations"]["debate/title"],
                labels["debate/epic"],
                labels["debate/release"],
                phase_of(g),
            ]
        )
    )


def unknown_prerequisite(task: str, name: str) -> str:
    return f"{task}'s spec.context names {name}, which no task spec declares"


def cmd_prereqs(task: str) -> None:
    _, g = find(task)
    files = task_files()
    blocked = False
    unknown = [name for name in prereq_names(g) if name not in files]
    for name in prereq_names(g):
        if name in unknown:
            print(f"  UNKNOWN {name} (no task spec declares it)")
            continue
        ph = phase_of(goal(files[name]))
        mark = "ok     " if ph == "Succeeded" else "BLOCKED"
        blocked |= ph != "Succeeded"
        print(f"  {mark} {name} ({ph})")
    if not prereq_names(g):
        print("  (no prerequisites)")
    if unknown:
        # A prerequisite nobody declares is a spec error, never a met prerequisite (v1-e41-t07).
        die("\n".join(unknown_prerequisite(task, name) for name in unknown))
    sys.exit(1 if blocked else 0)


def cmd_ready() -> None:
    files = task_files()
    goals = {n: goal(p) for n, p in files.items()}
    rows = []
    for n, g in goals.items():
        if phase_of(g) not in ("Pending", "Ready"):
            continue
        unknown = [p for p in prereq_names(g) if p not in goals]
        if unknown:
            # Until v1-e41-t07 an unknown prerequisite was skipped, so it counted as met.
            for p in unknown:
                print(
                    f"{n} is not listed: its spec.context names {p}, which no task spec declares",
                    file=sys.stderr,
                )
            continue
        if all(phase_of(goals[p]) == "Succeeded" for p in prereq_names(g)):
            rows.append(
                (g["metadata"]["labels"]["debate/release"], n, g["metadata"]["annotations"]["debate/title"])
            )
    order = lambda r: tuple(int(x) for x in r[0][1:].split("."))  # noqa: E731
    for rel, n, title in sorted(rows, key=lambda r: (order(r), r[1])):
        print(f"{rel}\t{n}\t{title}")


def cmd_set_phase(task: str, phase: str) -> None:
    if phase not in PHASES:
        die(f"phase must be one of {sorted(PHASES)}")
    path, _ = find(task)
    text = path.read_text()
    # The Goal is the first document; its status block is the first `status:\n  phase:` pair.
    new, n = re.subn(r"^status:\n  phase: \S+$", f"status:\n  phase: {phase}", text, count=1, flags=re.M)
    if n != 1:
        die(f"{path}: could not find the Goal status block")
    path.write_text(new)


def cmd_new_report(task: str) -> None:
    path, g = find(task)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{task}.md"
    if out.exists():
        print(out.relative_to(ROOT))
        return
    text = TEMPLATE.read_text()
    text = text.split("<!-- TEMPLATE START -->", 1)[-1].lstrip()
    for k, v in {
        "{{TASK}}": task,
        "{{TITLE}}": g["metadata"]["annotations"]["debate/title"],
        "{{SPEC}}": path.relative_to(ROOT).as_posix(),
        "{{EPIC}}": g["metadata"]["labels"]["debate/epic"],
        "{{RELEASE}}": g["metadata"]["labels"]["debate/release"],
    }.items():
        text = text.replace(k, v)
    out.write_text(text)
    print(out.relative_to(ROOT))


def report_verdict(text: str) -> str:
    """The verdict of the review that belongs to the work being merged: the LAST `**Verdict:**` line.

    A resumed task's report keeps every earlier PM review as it was written, and the resumed session
    appends a new, empty review at the end. Reading the first line would let `scripts/task pr` open on
    an earlier ACCEPTED before anyone has reviewed the new work (v1-e01-t18).
    """
    found = VERDICT_LINE.findall(text)
    return found[-1] if found and found[-1] in VERDICTS else "PENDING"


def current_session(text: str) -> str:
    """The current session's part of a report: everything after the last-but-one PM review.

    The reviews are the `**Verdict:**` lines `report_verdict` reads. With one review or none, the whole
    report is current. Otherwise the last-but-one review ends, as `section()` ends a section, at the
    next `## ` heading, and the current part starts there. Its notes and any `###` record the PM adds
    under it stay with it; a `##` section appended after it is current (v1-e01-t24).
    """
    reviews = list(VERDICT_LINE.finditer(text))
    if len(reviews) < 2:
        return text
    end = SECTION_HEADING.search(text, reviews[-2].end())
    return text[end.start() :] if end else ""


def open_items(text: str) -> list[str]:
    """The open-item markers `scripts/task pr --partial` requires, found in the current session's part."""
    return sorted(set(OPEN_ITEM_MARKERS.findall(current_session(text))))


def cmd_verdict(task: str) -> None:
    rep = REPORTS / f"{task}.md"
    print(report_verdict(rep.read_text()) if rep.exists() else "MISSING")


def cmd_verdict_of(file: str) -> None:
    print(report_verdict(sys.stdin.read() if file == "-" else Path(file).read_text()))


def cmd_open_items(task: str) -> None:
    rep = REPORTS / f"{task}.md"
    if not rep.exists():
        die(f"no session report at {rep.relative_to(ROOT)}")
    found = open_items(rep.read_text())
    if not found:
        sys.exit(1)
    print(", ".join(found))


def section(text: str, heading: str) -> str:
    """The body of the LAST section with this heading: a later review is appended, never edited in."""
    found = re.findall(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return re.sub(r"<!--.*?-->\n?", "", found[-1], flags=re.S).strip() if found else ""


def cmd_pr_body(task: str) -> None:
    path, g = find(task)
    rep = REPORTS / f"{task}.md"
    text = rep.read_text() if rep.exists() else ""
    rel = path.relative_to(ROOT).as_posix()
    labels = g["metadata"]["labels"]
    report = REPORTS.relative_to(ROOT).as_posix() + f"/{task}.md"
    parts = [
        f"Implements **{task}** — {g['metadata']['annotations']['debate/title']}",
        f"Release `{labels['debate/release']}` · epic `{labels['debate/epic']}`",
        f"Spec: [`{rel}`]({rel}) · Session report: [`{report}`]({report})",
        "",
        "## Summary",
        section(text, "Summary") or "_See session report._",
        "",
        "## Acceptance criteria",
        section(text, "Acceptance criteria") or "_See session report._",
        "",
        "## Operator follow-ups",
        section(text, "Operator follow-ups") or "None.",
        "",
        "## PM review",
        section(text, "PM review") or "_Missing._",
        "",
        "---",
        "- [ ] CI (`ci`) is green",
        "- [ ] Spec `status.phase` is `Succeeded` in this PR",
        "- [ ] Squash-merge into `dev`, then run `scripts/task finish " + task + "`",
    ]
    print("\n".join(parts))


PROMPT = """You are the implementation session for ONE PlanSpec task in the Debate Intelligence Platform repo.

Task:      {task} — {title}
Spec:      {spec}
Epic:      plan_specs/{major}/{epic_dir}/epic.yaml  ({epic}, release {release})
Worktree:  {worktree}  (branch task/{task}, created from origin/dev)
{resumed}
Before writing any code, read in this order: CLAUDE.md, docs/process/working-agreements.md,
plan_specs/README.md, the epic.yaml above, and the task spec. The spec is the contract.
{status_line}

How to work:
1. Implement the Plan graph nodes in dependsOn order. A node is done only when every one of its
   acceptanceCriteria passes; run those commands and keep their output for the report.
2. Stay inside this task's scope and this worktree. Do not edit other task specs, other epics,
   or files outside the task's stated packages unless the spec requires it. If the spec is wrong or
   incomplete, stop and write the problem up in the report (Deviations) instead of improvising scope.
3. Keep tests fast and offline (recorded fixtures, fake/replay ModelRouter). Mark anything slow or
   live as outside the PR CI path, per docs/process/working-agreements.md (CI budget).
4. Any command you expect to run longer than about 2 minutes (full test suites, large installs,
   model evaluations, terraform apply, load tests, bulk fixture generation) must NOT be run by you.
   Stop, give the operator a paste-ready command block (where to run it, exact command, expected
   runtime, what success looks like), and wait for the result before continuing.
5. Use descriptive names for files, sections and identifiers. Do not introduce opaque labels such as
   A1/A2/Phase-B unless they are the domain's own terms.
6. Commit to task/{task} with clear messages as you go. Do NOT push, open a pull request, merge, or
   touch dev/main; the operator does that with scripts/task after PM review.
7. A document you add under docs/ starts with a one-line description as its first line,
   `<!-- docs-index: What this document is for -->` (working agreement 3). Do NOT edit or
   regenerate docs/README.md (no scripts/docs_index.py): it is generated, and a workflow refreshes
   it on dev after merge (v1-e01-t16).
8. Operator command blocks contain no `#` comments, because the operator's shell is zsh: pasted
   interactively, zsh passes `#` and the words after it to the command as arguments. Put the
   explanation in the prose around the block (working agreement 9,
   docs/process/working-agreements.md#9-command-blocks-are-safe-to-paste-into-zsh). This holds in
   runbooks, guides, READMEs and your session report; scripts/check_command_blocks.py fails CI on one.
9. Never run the whole test suite, in one command or in parts: CI runs what the pull request's
   changes reach, and everything on dev's push run (working agreement 10). While working, run the
   tests for what you change. Bound every test run you start at 115 seconds with
   `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest ...`, which stops the run
   and every process it started, xdist workers included. Before the report, run the affected set
   once with `uv run scripts/affected_tests.py --run`, plus ruff, pyright on the changed packages,
   lint-imports and scripts/validate_specs.py, and record the commands and results. If it says the
   whole selection is affected, run nothing more; agreement 10 says when to hand the operator one
   whole-selection run.

When the work is complete:
- Set the task Goal status.phase to Succeeded ONLY if every acceptance criterion actually passed
  (`uv run scripts/task_helper.py set-phase {task} Succeeded`). If any criterion is one no session
  can close - a run needing credentials or a device, a GitHub setting, a sign-off, a measurement
  that can only be taken after this branch merges - leave the phase InProgress, say so in the
  report's summary, and mark those criteria NOT RUN with the reason. The phase is the Goal's
  completion, not your verdict on your own work: a task can be finished, reviewed and merged
  `--partial` while staying InProgress. Reporting Succeeded with an open criterion is the one
  mistake that gets past both the PM and `scripts/task pr`.
  Then run `uv run scripts/validate_specs.py`. Do NOT regenerate ROADMAP.md (no
  scripts/spec_index.py) unless ROADMAP.md is in this task's constraints.packages: a workflow
  refreshes it on dev after merge, because every task touching it makes parallel PRs conflict.
{report_step}
- Commit the report and all changes. Finish by printing the report path and a one-paragraph summary.
If you cannot finish, still write the report with status BLOCKED or PARTIAL and commit it.
"""


# What differs between a started task's prompt and a resumed one's (v1-e01-t18).
STARTED_REPORT_STEP = """\
- Fill in the session report at docs/session-reports/{task}.md (already created from the template).
  Every acceptance criterion gets PASS/FAIL/NOT RUN with the evidence (command + result). Leave the
  "PM review" section exactly as it is; the PM fills it in."""

RESUMED_NOTE = """
This is a resumed task: append to the existing report, keep every earlier PM review.
It was merged into dev with `scripts/task pr --partial` and is still InProgress there.
`scripts/task resume` recreated this worktree and branch from origin/dev and committed nothing.
Read the whole existing report first; its last PM review says what is still open.
"""

RESUMED_REPORT_STEP = """\
- Append to the session report at docs/session-reports/{task}.md. Everything already in it,
  including every earlier PM review and its verdict line, stays exactly as it is: never rename,
  edit or delete an earlier review. Add your own dated section after the last one (for example
  "## Resumed <date>: <what this session did>"), in which every acceptance criterion you touched
  gets PASS/FAIL/NOT RUN with the evidence (command + result). End the report with a new, empty
  "## PM review" section copied from docs/process/session-report-template.md. scripts/task pr
  reads the last verdict in the report, so that empty review is what it reads until the PM fills
  it in. A criterion still open is marked NOT RUN (or PARTIAL/FAIL) again in your own section:
  `scripts/task pr --partial` reads open items only after the last-but-one PM review."""

STARTED = {
    "resumed": "",
    "status_line": "The task's Goal status has already been set to InProgress and committed on this branch.",
    "report_step": STARTED_REPORT_STEP,
}

RESUMED = {
    "resumed": RESUMED_NOTE,
    "status_line": (
        "The task's Goal status is already InProgress on origin/dev; "
        "nothing has been committed on this branch."
    ),
    "report_step": RESUMED_REPORT_STEP,
}


def render_prompt(task: str, worktree: str, variant: dict[str, str]) -> str:
    path, g = find(task)
    labels = g["metadata"]["labels"]
    return PROMPT.format(
        task=task,
        title=g["metadata"]["annotations"]["debate/title"],
        spec=path.relative_to(ROOT).as_posix(),
        major=labels["debate/major-version"],
        epic_dir=path.parent.name,
        epic=labels["debate/epic"],
        release=labels["debate/release"],
        worktree=worktree,
        resumed=variant["resumed"],
        status_line=variant["status_line"],
        report_step=variant["report_step"].format(task=task),
    ).rstrip()


def cmd_prompt(task: str, worktree: str) -> None:
    print(render_prompt(task, worktree, STARTED))


def cmd_prompt_resumed(task: str, worktree: str) -> None:
    print(render_prompt(task, worktree, RESUMED))


# protect-main requires validate-dev green on a promotion's head commit. From 2026-10-20 it was red
# on every dev pre-release for days and nobody saw it, so `scripts/task ready` and `list`, the two
# views the operator and the PM read most, print it for dev's head (v1-e01-t34).
VALIDATE_DEV = "validate-dev"
UNREADABLE_STATUS = "validate-dev: unknown (gh could not read dev's commit status)"


def validate_dev_status(document: str) -> str:
    """What scripts/task prints for dev's head, from GitHub's combined status for `dev`."""
    try:
        combined = json.loads(document)
        sha, statuses = combined["sha"], combined["statuses"]
    except (ValueError, KeyError, TypeError):
        return UNREADABLE_STATUS
    if not isinstance(sha, str) or not isinstance(statuses, list):
        return UNREADABLE_STATUS
    head = f"dev {sha[:7]}"
    found = next((s for s in statuses if isinstance(s, dict) and s.get("context") == VALIDATE_DEV), None)
    if found is None:
        return f"validate-dev: none yet on {head} (its pre-release may still be building)"
    state = found.get("state")
    if not isinstance(state, str):
        return UNREADABLE_STATUS
    line = f"validate-dev: {state} on {head}"
    if found.get("target_url"):
        line += f"  {found['target_url']}"
    if state in ("failure", "error"):
        line += "\n  No promotion to main can merge until dev's head validates; the run says what failed."
    return line


def cmd_validate_dev_status() -> None:
    print(validate_dev_status(sys.stdin.read()))


def main() -> None:
    a = sys.argv[1:]
    cmds = {
        "info": (cmd_info, 1),
        "prereqs": (cmd_prereqs, 1),
        "ready": (cmd_ready, 0),
        "set-phase": (cmd_set_phase, 2),
        "prompt": (cmd_prompt, 2),
        "prompt-resumed": (cmd_prompt_resumed, 2),
        "new-report": (cmd_new_report, 1),
        "verdict": (cmd_verdict, 1),
        "verdict-of": (cmd_verdict_of, 1),
        "open-items": (cmd_open_items, 1),
        "pr-body": (cmd_pr_body, 1),
        "validate-dev-status": (cmd_validate_dev_status, 0),
    }
    if not a or a[0] not in cmds or len(a) - 1 != cmds[a[0]][1]:
        die(__doc__ or "usage: task_helper.py <command> ...")
    cmds[a[0]][0](*a[1:])


if __name__ == "__main__":
    main()
