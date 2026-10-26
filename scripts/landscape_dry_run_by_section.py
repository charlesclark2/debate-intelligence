#!/usr/bin/env python3
"""A landscape report's dry run, printing its scan's hits by section and counts only (`v1-e32-t16`).

`debate-research landscape report --caselist <caselist> --dry-run` prints each scan hit with its line,
for the operator's terminal only, and writes nothing, so its report.md is not on disk for anyone to say
which section a hit is in. This runs the same landscape service, built by the CLI's own container, as a
dry run without `--publish`, and prints only counts:

* that nothing was written, and how many files a publish would upload;
* the affirmative rounds by identification method, and the kritikal affirmatives (`v1-e32-t17`): rounds
  by own marker and by carry, those the advantage guard refused, the control (rounds another method
  identifies whose files hold a marker) and the K families in the K-aff files' headings, by id;
* per DA and advantage kind, the impact rows, those with a scenario and the scenario names withheld, and
  the documents with no scenario heading and no role label (`v1-e32-t14`, under the coach's scenario
  lists of `v1-e32-t22`), never a name; and per kind the words two or more teams use as a scenario under
  a position with a list that its list does not hold, and how many of them hold a caselist word, so the
  coach knows when to look at the lists again (the PM's ruling of 2026-10-26), never the words;
* per DA and advantage kind, the impact ranks each source names under "What each impact runs through",
  those left out and the tags withheld (`v1-e32-t25`, the PM's brief of 2026-10-26), never a name;
* the CPs' planks: how many, under how many CPs, in how many groups by the advantage they solve, how many
  withheld for naming a school, and where every plank found went;
* the scan's hits by file, report.md's section (its nearest heading, and each CP's plank table apart) and
  kind, with how many are not yet accepted, and the digest a publish would ask for.

It never prints a hit's term or line, a text or a plank. Read the CLI's dry run in the terminal for those.

    uv run python scripts/landscape_dry_run_by_section.py --caselist hspolicy26
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from debate_core.application.errors import DomainError
from debate_core.application.landscape_run import LandscapeRunRequest, LandscapeRunResult
from debate_core.application.landscape_scan import hits_by_section
from debate_core.domain.landscape_report import LeadInSource
from debate_core.domain.landscape_texts import AnalyticTextKind

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = REPO_ROOT / "config" / "landscape"
PLANK_TABLE: str = ": plank table"
NAMED_BY: dict[LeadInSource, str] = {
    LeadInSource.SCENARIO: "a scenario",
    LeadInSource.INTERNAL_LINK: "an internal link",
    LeadInSource.TAG: "a tag",
    LeadInSource.CARD_ABOVE: "the card above",
}


def report_lines(result: LandscapeRunResult) -> list[str]:
    """What the dry run prints: counts only."""
    planned = len(result.publish.planned) if result.publish is not None else 0
    lines = [
        f"Dry run of {result.caselist} through {result.snapshot.isoformat()}, taxonomy "
        f"{result.taxonomy_version}: {'files written' if result.written else 'nothing written'}; "
        f"{planned} files planned.",
    ]
    unclassified = result.report.unclassified
    methods = "; ".join(f"{one.method} {one.rounds}" for one in result.report.aff_identification)
    lines.append(
        f"Affirmative rounds by method: {methods + '; ' if methods else ''}not identified "
        f"{unclassified.aff_rounds_unidentified} of {unclassified.aff_rounds}."
    )
    kritikal = result.report.kritikal_affs
    if kritikal is None:
        lines.append("Kritikal affirmatives: no K-aff markers were read.")
    else:
        families = ", ".join(
            f"{one.family_id} {one.files} files ({one.teams} teams)" for one in kritikal.families
        )
        lines += [
            f"Kritikal affirmatives ({kritikal.position_id}): {kritikal.rounds} rounds by "
            f"{kritikal.teams} teams, {kritikal.by_marker} by their own marker, "
            f"{kritikal.by_carry} by carry; "
            f"{kritikal.refused_by_advantage} refused by the advantage guard, still unidentified.",
            f"Control: {kritikal.control_rounds} rounds identified another way hold a K-aff marker, in "
            f"{kritikal.control_files} files; by method: "
            + (
                ", ".join(f"{method} {count}" for method, count in kritikal.control_by_method.items())
                or "none"
            )
            + ".",
            f"K families in the K-aff files' headings: {families or 'none'}.",
        ]
    transition = result.report.transition_plans
    if transition is None:
        lines.append("Plans under Thus: none were read.")
    else:
        lines.append(
            f"Plans under Thus: the K-aff carry refused in {transition.refused_kritikal_carry} rounds; "
            f"{transition.control_rounds} rounds identified another way hold one naming another aff; by "
            "method: "
            + (
                ", ".join(f"{method} {count}" for method, count in transition.control_by_method.items())
                or "none"
            )
            + "."
        )
    lines += [
        f"Scenarios, {one.kind.value} ({one.positions} positions): {one.impact_rows} impact rows, "
        f"{one.rows_with_scenario} with a scenario, {one.withheld_names} names withheld; "
        f"{one.unstructured_documents} of {one.documents} documents with no scenario heading and no role "
        "label."
        for one in result.report.chain_coverage
    ]
    lines += [
        f"Scenario words no list holds, {one.kind.value}: {one.unlisted_words} that two or more teams use "
        f"under a position with a list, {one.unlisted_words_withheld} of them holding a caselist word."
        for one in result.report.chain_coverage
    ]
    lines += [
        f"Impact ranks named, {one.kind.value}: "
        + ", ".join(f"{named.rows} by {NAMED_BY[named.source]}" for named in one.named_rows)
        + f"; {one.rows_left_out} left out; {one.withheld_tags} tags withheld."
        for one in result.report.chain_coverage
    ]
    texts = result.report.texts
    if texts is None:
        lines.append("Planks: no analytic texts were read.")
    else:
        planks = texts.planks
        groups = sum(len(one.groups) for one in planks)
        shown = sum(len(group.planks) for one in planks for group in one.groups)
        total = sum(one.planks for one in planks)
        withheld = sum(one.withheld for one in planks)
        lines.append(
            f"Planks: {total} under {len(planks)} CPs, in {groups} groups by what they solve, {shown} rows "
            f"shown, {withheld} withheld for naming a school."
        )
        lines += [
            f"  {one.position_id}: {one.planks} planks, {one.teams} teams, {len(one.groups)} groups, "
            f"{one.withheld} withheld"
            for one in planks
        ]
        found = next(one for one in texts.coverage if one.kind is AnalyticTextKind.CP_PLANK)
        lines.append(
            f"Planks found: {found.labels} in {found.documents} files; {found.counted} counted, "
            f"{found.elsewhere} elsewhere, {found.headings_place_nothing} under headings that place nothing, "
            f"{found.no_heading} under no heading; {found.refused_by_guard} refused with their CP text, "
            f"{found.plank_labels} alias-only labels, {found.solves_other_words} cards saying solves with "
            f"other words, {found.unread} not read again."
        )
    scan = result.scan
    lines.append(
        f"Scan: {len(scan.hits)} hits, {len(scan.pending)} not yet accepted"
        + (f" (digest {scan.digest})." if scan.pending else ".")
    )
    sections = hits_by_section(scan.hits, scan.pending, result.bundle_files)
    lines += [
        f"  {one.file} | {one.section} | {one.kind.value}: {one.hits} "
        f"({one.not_yet_accepted} not yet accepted)"
        for one in sections
    ]
    in_planks = sum(one.hits for one in sections if one.section.endswith(PLANK_TABLE))
    lines.append(f"Hits in report.md's plank tables: {in_planks}.")
    return lines


async def _run(arguments: argparse.Namespace) -> int:
    started = time.perf_counter()
    # Imported here: the CLI's container is the one place the landscape service is wired.
    from debate_cli.build_info import settings_loader
    from debate_cli.container import ServiceContainer, validating_routing

    services = ServiceContainer(settings_loader=validating_routing(settings_loader()))
    service = services.landscape_run(config_dir=arguments.config_dir, with_bucket=False)
    result = await service.run(
        LandscapeRunRequest(caselist=arguments.caselist, snapshot=arguments.snapshot, dry_run=True)
    )
    if result.written:
        print("FAILED: the dry run wrote its files.", file=sys.stderr)
        return 1
    for line in report_lines(result):
        print(line)
    print(f"Runtime {time.perf_counter() - started:.1f} s.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--caselist", required=True, help="The caselist slug.")
    parser.add_argument(
        "--snapshot", type=date.fromisoformat, help="YYYY-MM-DD. Default: the newest weekly snapshot."
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        help="The directory holding topics.yaml. Default: config/landscape.",
    )
    arguments = parser.parse_args(argv)
    try:
        return asyncio.run(_run(arguments))
    except (DomainError, ValueError, OSError) as error:
        print(f"Refused: {type(error).__name__}: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
