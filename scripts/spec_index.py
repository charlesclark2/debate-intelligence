# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Regenerate the generated section of ROADMAP.md from plan_specs/.

Everything between the BEGIN/END GENERATED markers in ROADMAP.md is rewritten; the
hand-written sections around it (timeline, notes) are preserved. The output depends only on the
spec files, so running it twice in a row produces no second diff.

Who runs this: the PM, in a `specs/roadmap-refresh` PR of its own. Individual task PRs leave
ROADMAP.md alone, because every task that touched it would conflict with every other task's PR.
That is why `--check` is not a pre-commit hook and is required only on pull requests into main
(see v1-e01-t04); for live status use `uv run scripts/validate_specs.py --status`.

Usage:
  uv run scripts/spec_index.py            # rewrite ROADMAP.md
  uv run scripts/spec_index.py --check    # exit 1 if ROADMAP.md is stale, without writing
  uv run scripts/spec_index.py --root DIR # work on the spec tree and ROADMAP.md under DIR
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

# The version ordering rule lives with the validator, so the roadmap and the validator's
# --status roll-up can never disagree about which release comes first.
from validate_specs import release_order

ROOT = Path(__file__).resolve().parents[1]
BEGIN, END = "<!-- BEGIN GENERATED -->", "<!-- END GENERATED -->"
# One working day of this project is six focused hours, which is what the specs' `1d` estimates mean.
HOURS_PER_DAY = 6
EFFORT = re.compile(r"\s*([\d.]+)\s*([mhd])\s*")


def hours(effort: str | None) -> float:
    """`30m`, `2h`, `1d` as a number of hours; anything unrecognised counts as nothing."""
    if not effort:
        return 0.0
    match = EFFORT.fullmatch(str(effort))
    if not match:
        return 0.0
    value, unit = float(match[1]), match[2]
    if unit == "m":
        return value / 60
    return value * HOURS_PER_DAY if unit == "d" else value


def documents(path: Path) -> dict[str, dict]:
    return {d["kind"]: d for d in yaml.safe_load_all(path.read_text()) if d}


def title_of(doc: dict) -> str:
    return (doc["metadata"].get("annotations") or {}).get("debate/title", doc["metadata"]["name"])


def theme_of(release_goal: dict) -> str:
    """The part of a release title after the em dash: `v1.0 — Foundation` -> `Foundation`."""
    title = title_of(release_goal)
    return title.split(" — ", 1)[1] if " — " in title else title


def read_task(path: Path, root: Path) -> dict:
    task = documents(path)
    goal, plan = task["Goal"], task["Plan"]
    nodes = plan["spec"]["graph"]["nodes"]
    return dict(
        name=goal["metadata"]["name"],
        title=title_of(goal),
        phase=(goal.get("status") or {}).get("phase", "Pending"),
        hours=sum(hours(n.get("estimatedEffort")) for n in nodes),
        prereqs=len(goal["spec"].get("context") or []),
        path=path.relative_to(root).as_posix(),
    )


def read_epics(specs: Path, root: Path) -> dict[str, list[dict]]:
    """Every epic, grouped by its release label, in epic-folder order."""
    epics: dict[str, list[dict]] = defaultdict(list)
    for epic_file in sorted(specs.glob("v*/e*/epic.yaml")):
        goal = documents(epic_file)["Goal"]
        epics[goal["metadata"]["labels"]["debate/release"]].append(
            dict(
                name=goal["metadata"]["name"],
                title=title_of(goal),
                path=epic_file.relative_to(root).as_posix(),
                tasks=[read_task(t, root) for t in sorted(epic_file.parent.glob("t*.yaml"))],
            )
        )
    return epics


def render(root: Path) -> str:
    specs = root / "plan_specs"
    order = release_order(specs)
    releases = {version: documents(specs / "releases" / f"{version}.yaml") for version in order}
    epics = read_epics(specs, root)

    out = [
        BEGIN,
        "",
        "## Release summary",
        "",
        "| Release | Theme | Epics | Tasks | Done | Est. hours |",
        "|---|---|---|---|---|---|",
    ]
    for version in order:
        release_epic_list = epics[version]
        tasks = [t for e in release_epic_list for t in e["tasks"]]
        link = f"[{version}](plan_specs/releases/{version}.yaml)"
        out.append(
            f"| {link} | {theme_of(releases[version]['Goal'])} | {len(release_epic_list)} | "
            f"{len(tasks)} | {sum(t['phase'] == 'Succeeded' for t in tasks)} | "
            f"{sum(t['hours'] for t in tasks):.0f} |"
        )

    current_major = None
    for version in order:
        major = version.split(".")[0].upper()
        if major != current_major:
            current_major = major
            out += ["", f"## {major}"]
        goal = releases[version]["Goal"]
        out += ["", f"### {title_of(goal)}", "", goal["spec"]["description"].strip(), ""]
        for epic in epics[version]:
            out += [
                f"#### [{epic['title']}]({epic['path']})",
                "",
                "| Task | Status | Prereqs | Est. hours |",
                "|---|---|---|---|",
            ]
            for task in epic["tasks"]:
                out.append(
                    f"| [{task['title']}]({task['path']}) `{task['name']}` | {task['phase']} | "
                    f"{task['prereqs']} | {task['hours']:.1f} |"
                )
            out.append("")
    out.append(END)
    return "\n".join(out)


def rewritten(roadmap: Path, root: Path) -> str:
    """The roadmap text with the generated section replaced, raising if the markers are missing."""
    text = roadmap.read_text()
    for marker in (BEGIN, END):
        if marker not in text:
            raise LookupError(f"{roadmap.name} has no {marker} marker")
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    return head + render(root) + tail


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report staleness instead of rewriting")
    ap.add_argument("--root", type=Path, default=ROOT, help="repository root holding plan_specs/")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    roadmap = root / "ROADMAP.md"
    if not roadmap.exists():
        print(f"{roadmap} does not exist", file=sys.stderr)
        return 2
    try:
        new = rewritten(roadmap, root)
    except LookupError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.check:
        if new != roadmap.read_text():
            print("ROADMAP.md is stale; run `uv run scripts/spec_index.py`", file=sys.stderr)
            return 1
        print("ROADMAP.md is up to date")
        return 0
    if new == roadmap.read_text():
        print("ROADMAP.md is already up to date")
        return 0
    roadmap.write_text(new)
    print("ROADMAP.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
