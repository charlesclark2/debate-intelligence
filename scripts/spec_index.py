# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Regenerate the generated section of ROADMAP.md from plan_specs/.

Everything between the BEGIN/END GENERATED markers in ROADMAP.md is rewritten; the
hand-written sections above it (timeline, notes) are preserved.

Usage:
  uv run scripts/spec_index.py          # rewrite ROADMAP.md
  uv run scripts/spec_index.py --check  # exit 1 if ROADMAP.md is stale (for CI)
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "plan_specs"
ROADMAP = ROOT / "ROADMAP.md"
BEGIN, END = "<!-- BEGIN GENERATED -->", "<!-- END GENERATED -->"


def hours(effort: str | None) -> float:
    if not effort:
        return 0.0
    m = re.fullmatch(r"\s*([\d.]+)\s*([mhd])\s*", str(effort))
    if not m:
        return 0.0
    v, unit = float(m[1]), m[2]
    return v / 60 if unit == "m" else v * 6 if unit == "d" else v


def docs(path: Path) -> dict[str, dict]:
    return {d["kind"]: d for d in yaml.safe_load_all(path.read_text()) if d}


def render() -> str:
    releases = {p.stem: docs(p) for p in sorted((SPECS / "releases").glob("*.yaml"))}
    order = sorted(releases, key=lambda r: tuple(int(x) for x in r[1:].split(".")))
    epics = defaultdict(list)
    for ep in sorted(SPECS.glob("v*/e*/epic.yaml")):
        d = docs(ep)
        tasks = []
        for tf in sorted(ep.parent.glob("t*.yaml")):
            td = docs(tf)
            g, pl = td["Goal"], td["Plan"]
            nodes = pl["spec"]["graph"]["nodes"]
            tasks.append(dict(
                name=g["metadata"]["name"],
                title=g["metadata"]["annotations"]["debate/title"],
                phase=g.get("status", {}).get("phase", "Pending"),
                hours=sum(hours(n.get("estimatedEffort")) for n in nodes),
                prereqs=len(g["spec"].get("context") or []),
                path=tf.relative_to(ROOT).as_posix(),
            ))
        epics[d["Goal"]["metadata"]["labels"]["debate/release"]].append(dict(
            name=d["Goal"]["metadata"]["name"],
            title=d["Goal"]["metadata"]["annotations"]["debate/title"],
            path=ep.relative_to(ROOT).as_posix(),
            tasks=tasks,
        ))

    out = [BEGIN, "", "## Release summary", "",
           "| Release | Theme | Epics | Tasks | Done | Est. hours |", "|---|---|---|---|---|---|"]
    for r in order:
        eps = epics[r]
        ts = [t for e in eps for t in e["tasks"]]
        theme = releases[r]["Goal"]["metadata"]["annotations"]["debate/title"].split(" — ", 1)[1]
        out.append(f"| [{r}](plan_specs/releases/{r}.yaml) | {theme} | {len(eps)} | {len(ts)} | "
                   f"{sum(t['phase'] == 'Succeeded' for t in ts)} | {sum(t['hours'] for t in ts):.0f} |")
    current_major = None
    for r in order:
        major = r.split(".")[0].upper()
        if major != current_major:
            current_major = major
            out += ["", f"## {major}"]
        g = releases[r]["Goal"]
        out += ["", f"### {g['metadata']['annotations']['debate/title']}", "",
                g["spec"]["description"].strip(), ""]
        for e in epics[r]:
            out += [f"#### [{e['title']}]({e['path']})", "",
                    "| Task | Status | Prereqs | Est. hours |", "|---|---|---|---|"]
            for t in e["tasks"]:
                out.append(f"| [{t['title']}]({t['path']}) `{t['name']}` | {t['phase']} | "
                           f"{t['prereqs']} | {t['hours']:.1f} |")
            out.append("")
    out.append(END)
    return "\n".join(out)


def main() -> int:
    text = ROADMAP.read_text() if ROADMAP.exists() else f"# Roadmap\n\n{BEGIN}\n{END}\n"
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    new = head + render() + tail
    if "--check" in sys.argv:
        if new != text:
            print("ROADMAP.md is stale; run `uv run scripts/spec_index.py`")
            return 1
        return 0
    ROADMAP.write_text(new)
    print("ROADMAP.md updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
