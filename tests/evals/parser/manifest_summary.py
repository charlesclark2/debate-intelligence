"""The tables in `MANIFEST.md` and the labeling guide, written from the data rather than by hand.

`manifest.json`, `rejections.json` and `sampling-plan.json` are the record. The tables people read
are generated from them between marker comments, so a rejection run from the coach's machine leaves
nothing to edit by hand: `scripts/select_eval_files.py` and `scripts/plan_eval_sampling.py` both
rewrite them as their last step. Prose outside the markers is left alone, so a number that can
change belongs inside a block, never in the prose around it.

A block is delimited by

    <!-- generated:NAME (written by the evaluation scripts; do not edit by hand) -->
    ...
    <!-- end generated:NAME -->

Nothing here reads a corpus file: every input is already keyed and committed.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from tests.evals.parser.labels_schema import (
    Category,
    DebateFormat,
    Manifest,
    ManifestEntry,
    RejectionList,
    SamplingPlan,
    TemplateFamily,
    load_manifest,
    load_rejections,
    load_sampling_plan,
)

__all__ = [
    "GUIDE_BLOCKS",
    "MANIFEST_BLOCKS",
    "render_blocks",
    "replace_blocks",
    "write_summaries",
]

#: The blocks each document must carry.
MANIFEST_BLOCKS = ("selection", "coverage", "rejections", "sampling-plan")
GUIDE_BLOCKS = ("pr-subset",)

_SEASONS = ("2024-25", "2025-26", "2026-27")


def _ordered(manifest: Manifest) -> list[ManifestEntry]:
    categories = list(Category)
    return sorted(
        manifest.entries,
        key=lambda e: (
            categories.index(e.category),
            e.season,
            e.debate_format.value,
            e.template_family.value,
            e.digest,
        ),
    )


def _selection(manifest: Manifest) -> str:
    lines = [
        "| digest | Category | Season | Format | Template family | PR subset |",
        "|---|---|---|---|---|---|",
    ]
    for e in _ordered(manifest):
        subset = "yes" if e.pr_subset else ""
        lines.append(
            f"| `{e.digest[:16]}` | {e.category.value} | {e.season} | {e.debate_format.value} | "
            f"{e.template_family.value} | {subset} |"
        )
    return "\n".join(lines)


def _coverage(manifest: Manifest) -> str:
    def of(category: Category) -> list[ManifestEntry]:
        return [e for e in manifest.entries if e.category is category]

    team, caselist, camp = of(Category.TEAM), of(Category.CASELIST), of(Category.CAMP)
    formats = Counter(e.debate_format for e in team)
    seasons = Counter(e.season for e in team)
    team_other = [e for e in team if not e.is_verbatim]
    team_families = Counter(e.template_family.value for e in team_other)
    caselist_families = Counter(e.template_family for e in caselist)
    subset = Counter(e.category.value for e in manifest.pr_subset)
    rows = [
        ("At least 30 files", f"{len(manifest.entries)}"),
        (
            "At least 12 team files, all three formats",
            f"{len(team)}: " + ", ".join(f"{f.value} {formats[f]}" for f in DebateFormat),
        ),
        ("Team files across all three seasons", ", ".join(f"{s} {seasons[s]}" for s in _SEASONS)),
        (
            "At least 3 team files not on the Verbatim template",
            f"{len(team_other)} (" + ", ".join(f"{n} {f}" for f, n in sorted(team_families.items())) + ")",
        ),
        (
            "At least 12 caselist files, 4 non-Verbatim, 2 wiki-converted",
            f"{len(caselist)}: {caselist_families[TemplateFamily.OTHER_HEURISTIC]} other-heuristic, "
            f"{caselist_families[TemplateFamily.WIKI_CONVERTED]} wiki-converted, "
            f"{sum(1 for e in caselist if e.is_verbatim)} Verbatim-family",
        ),
        ("At least 6 camp files", f"{len(camp)}"),
        (
            "The PR subset: six files, every category",
            f"{len(manifest.pr_subset)}: " + ", ".join(f"{c.value} {subset[c.value]}" for c in Category),
        ),
    ]
    return "\n".join(["| Requirement | Selected |", "|---|---|", *(f"| {a} | {b} |" for a, b in rows)])


def _rejections(rejections: RejectionList) -> str:
    if not rejections.rejections:
        return "No file has been rejected."
    lines = ["| Rejected | Reason | On | Stratum | Replaced by |", "|---|---|---|---|---|"]
    for r in rejections.rejections:
        stratum = f"{r.category.value} {r.season} {r.debate_format.value} {r.template_family.value}"
        stratum += ", PR subset" if r.pr_subset else ""
        replaced = f"`{r.replaced_by[:16]}`" if r.replaced_by else "nothing (the selection was made again)"
        lines.append(f"| `{r.digest[:16]}` | `{r.reason.value}` | {r.rejected_on} | {stratum} | {replaced} |")
    return "\n".join(lines)


def _blocks_text(plan: SamplingPlan, digest: str) -> str:
    file_plan = plan.of(digest)
    if file_plan.full:
        return "whole file"
    return ", ".join(f"{first}-{last}" for first, last in file_plan.blocks)


def _out_of_date(manifest: Manifest, plan: SamplingPlan) -> list[str]:
    planned = {f.digest for f in plan.files}
    return [e.digest for e in manifest.entries if e.digest not in planned]


def _sampling_plan(manifest: Manifest, plan: SamplingPlan | None) -> str:
    if plan is None:
        return "No sampling plan yet. Run `uv run python scripts/plan_eval_sampling.py`."
    full = [f for f in plan.files if f.full]
    sampled = [f for f in plan.files if not f.full]
    sampled_rows = sum(f.labeled_rows for f in sampled)
    sampled_total = sum(f.paragraphs for f in sampled)
    lines = [
        f"Plan `{plan.plan_id}` (generated {plan.generated_on}) labels **{plan.labeled_rows:,} of "
        f"{plan.total_rows:,} paragraphs, {plan.rate:.1%}**: the {len(full)} PR-subset files in full "
        f"({sum(f.labeled_rows for f in full):,} rows) and {sampled_rows:,} of the other "
        f"{sampled_total:,} rows, {sampled_rows / sampled_total if sampled_total else 0:.1%}, in "
        "contiguous blocks.",
        "",
    ]
    stale = _out_of_date(manifest, plan)
    if stale:
        lines += [
            f"**This plan is out of date:** {len(stale)} file(s) in the manifest are not in it. Run "
            "`uv run python scripts/plan_eval_sampling.py`.",
            "",
        ]
    lines += [
        "| digest | Category | Paragraphs | Labeled | Rate | Blocks |",
        "|---|---|---|---|---|---|",
    ]
    planned = {f.digest: f for f in plan.files}
    for e in _ordered(manifest):
        f = planned.get(e.digest)
        if f is None:
            lines.append(f"| `{e.digest[:16]}` | {e.category.value} | | | | not in the plan yet |")
            continue
        lines.append(
            f"| `{e.digest[:16]}` | {e.category.value} | {f.paragraphs} | {f.labeled_rows} | "
            f"{f.rate:.0%} | {_blocks_text(plan, e.digest)} |"
        )
    return "\n".join(lines)


def _pr_subset(manifest: Manifest, plan: SamplingPlan | None) -> str:
    planned = {f.digest: f for f in plan.files} if plan is not None else {}
    lines: list[str] = []
    if plan is not None:
        subset_rows = sum(planned[e.digest].labeled_rows for e in manifest.pr_subset if e.digest in planned)
        lines += [
            f"Sampling plan `{plan.plan_id}`: **{plan.labeled_rows:,} rows** to label across "
            f"{len(manifest.entries)} files, **{subset_rows:,}** of them in the {len(manifest.pr_subset)} "
            "PR-subset files below.",
            "",
        ]
        if _out_of_date(manifest, plan):
            lines += ["**The plan is out of date**: run `uv run python scripts/plan_eval_sampling.py`.", ""]
    lines += ["| digest | Category | Format | Template family | Rows |", "|---|---|---|---|---|"]
    for e in _ordered(Manifest(entries=manifest.pr_subset)):
        rows = planned[e.digest].labeled_rows if e.digest in planned else "not planned"
        lines.append(
            f"| `{e.digest[:16]}` | {e.category.value} | {e.debate_format.value} | "
            f"{e.template_family.value} | {rows} |"
        )
    return "\n".join(lines)


def render_blocks(manifest: Manifest, rejections: RejectionList, plan: SamplingPlan | None) -> dict[str, str]:
    """Every generated block's body, by name."""
    return {
        "selection": _selection(manifest),
        "coverage": _coverage(manifest),
        "rejections": _rejections(rejections),
        "sampling-plan": _sampling_plan(manifest, plan),
        "pr-subset": _pr_subset(manifest, plan),
    }


def _pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(<!-- generated:{re.escape(name)} [^>]*-->\n)(.*?)(\n<!-- end generated:{re.escape(name)} -->)",
        re.DOTALL,
    )


def replace_blocks(text: str, blocks: Mapping[str, str], names: tuple[str, ...]) -> str:
    """`text` with each named block's body replaced. A missing marker is an error, not a skip."""
    for name in names:
        pattern = _pattern(name)
        if len(pattern.findall(text)) != 1:
            raise ValueError(f"expected exactly one generated:{name} block")
        text = pattern.sub(lambda m, body=blocks[name]: m.group(1) + body + m.group(3), text)
    return text


def write_summaries(manifest_path: Path, rejections_path: Path, plan_path: Path) -> list[Path]:
    """Rewrite the generated blocks of `MANIFEST.md` and `labels/README.md` beside the manifest.

    Returns the documents that changed. A document that is absent is skipped; one that is present
    without its markers is an error, because silently skipping it is how a table goes stale.
    """
    manifest = load_manifest(manifest_path)
    rejections = load_rejections(rejections_path)
    plan = load_sampling_plan(plan_path) if plan_path.is_file() else None
    blocks = render_blocks(manifest, rejections, plan)
    directory = manifest_path.parent
    changed: list[Path] = []
    for path, names in (
        (directory / "MANIFEST.md", MANIFEST_BLOCKS),
        (directory / "labels" / "README.md", GUIDE_BLOCKS),
    ):
        if not path.is_file():
            continue
        before = path.read_text(encoding="utf-8")
        after = replace_blocks(before, blocks, names)
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed.append(path)
    return changed
