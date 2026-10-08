# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Spec-aware helpers for scripts/task (the task lifecycle CLI).

Kept in Python so the shell script stays small and portable (macOS ships bash 3.2).
Every subcommand reads the specs of the checkout it is run from.

  info    <task>                 print tab-separated: spec_path, title, epic, release, phase
  prereqs <task>                 list prerequisites and their phase; exit 1 if any is not Succeeded
  ready                          list Pending tasks whose prerequisites are all Succeeded
  set-phase <task> <phase>       set the task Goal's status.phase in place
  prompt  <task> <worktree>      render the kickoff prompt for the task's Claude session
  prompt-resumed <task> <worktree>
                                 the same, for a partly merged task that scripts/task resume recreated
  new-report <task>              create docs/session-reports/<task>.md from the template (if absent)
  verdict <task>                 print the PM verdict recorded in the session report
  verdict-of <file>              print the PM verdict recorded in a report file (- reads stdin)
  pr-body <task>                 render the pull request body
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path.cwd()
SPECS = ROOT / "plan_specs"
REPORTS = ROOT / "docs" / "session-reports"
TEMPLATE = ROOT / "docs" / "process" / "session-report-template.md"
PHASES = {"Pending", "Ready", "InProgress", "Blocked", "Succeeded", "Failed", "Cancelled"}
VERDICTS = ("ACCEPTED", "CHANGES_REQUESTED", "PENDING")


def die(msg: str, code: int = 2) -> None:
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


def cmd_prereqs(task: str) -> None:
    _, g = find(task)
    files = task_files()
    blocked = False
    for name in prereq_names(g):
        ph = phase_of(goal(files[name])) if name in files else "MISSING"
        mark = "ok     " if ph == "Succeeded" else "BLOCKED"
        blocked |= ph != "Succeeded"
        print(f"  {mark} {name} ({ph})")
    if not prereq_names(g):
        print("  (no prerequisites)")
    sys.exit(1 if blocked else 0)


def cmd_ready() -> None:
    files = task_files()
    goals = {n: goal(p) for n, p in files.items()}
    rows = []
    for n, g in goals.items():
        if phase_of(g) not in ("Pending", "Ready"):
            continue
        if all(phase_of(goals[p]) == "Succeeded" for p in prereq_names(g) if p in goals):
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
    found = re.findall(r"^\*\*Verdict:\*\*[ \t]*`?([A-Z_]+)`?", text, re.M)
    return found[-1] if found and found[-1] in VERDICTS else "PENDING"


def cmd_verdict(task: str) -> None:
    rep = REPORTS / f"{task}.md"
    print(report_verdict(rep.read_text()) if rep.exists() else "MISSING")


def cmd_verdict_of(file: str) -> None:
    print(report_verdict(sys.stdin.read() if file == "-" else Path(file).read_text()))


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return re.sub(r"<!--.*?-->\n?", "", m.group(1), flags=re.S).strip() if m else ""


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
  it in."""

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
        "pr-body": (cmd_pr_body, 1),
    }
    if not a or a[0] not in cmds or len(a) - 1 != cmds[a[0]][1]:
        die(__doc__)
    cmds[a[0]][0](*a[1:])


if __name__ == "__main__":
    main()
