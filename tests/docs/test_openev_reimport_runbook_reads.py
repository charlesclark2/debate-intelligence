"""The runbook's reads of the bucket-mode OpenEv re-import's result, run over its real JSON (`v1-e40-t34`).

`docs/runbooks/caselist-cloud-run.md`, "A camp table change", reads two `--json` results with a
`grep -oE`: the run's, and the check's dry run after it. The filters are read out of the runbook's
blocks and run by `sh` over the line the CLI writes for an outcome built here, through the command's
own summary, so a key the runbook names and the summary drops fails here. Every count and every
expected line is written by hand: Michigan's refile as the runbook expects it, 105 files with 6
changed. No AWS call, no network.
"""

from __future__ import annotations

import io
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from debate_cli.openev_reimport_in_bucket import bucket_reimport_summary
from debate_cli.output import CliOutput, OutputMode
from debate_core.application.caselist.openev_metadata_reimport import OpenEvMetadataReimport
from debate_core.application.caselist.openev_metadata_reimport_in_bucket import BucketReimport
from debate_core.application.caselist.publish_plan import PublishPlan
from debate_core.application.caselist.publish_service import ManifestOutcome, PublishReport, SnapshotOutcome
from debate_core.application.caselist.run_state import BundleSave, RestoreReport
from debate_core.domain.caselist import Event

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "caselist-cloud-run.md"
SECTION: Final = "## A camp table change: the OpenEv metadata re-import"
KEY: Final = "manifests/openev/2026-policy.jsonl"
RESTORED: Final = RestoreReport(
    started_at=datetime(2026, 11, 5, 15, 0, tzinfo=UTC),
    finished_at=datetime(2026, 11, 5, 15, 0, 4, tzinfo=UTC),
    state_files=("caselist-sync-runs.jsonl",),
)


def filters() -> list[str]:
    """Each `grep -oE '...'` pattern the section applies to the command's output, in order."""
    text = RUNBOOK.read_text(encoding="utf-8")
    section = text[text.index(SECTION) :]
    section = section[: section.index("\n## ", len(SECTION))]
    return [
        match.group(1)
        for line in section.splitlines()
        if "caselist reimport-openev-metadata" in line and "--json" in line
        for match in [re.search(r"\| grep -oE '([^']+)'", line)]
        if match is not None
    ]


def printed(outcome: BucketReimport) -> str:
    """What `--json` writes on stdout for `outcome`: one envelope line."""
    stdout = io.StringIO()
    CliOutput(OutputMode.JSON, stdout=stdout).success(
        "caselist reimport-openev-metadata", bucket_reimport_summary(outcome, environment="dev")
    )
    return stdout.getvalue()


def through(pattern: str, output: str) -> list[str]:
    run = subprocess.run(
        ["sh", "-c", f"grep -oE '{pattern}'"], input=output, capture_output=True, text=True, check=False
    )
    return run.stdout.splitlines()


def reimport(*, applied: bool, rows_changed: int, records: int, changed: bool) -> OpenEvMetadataReimport:
    return OpenEvMetadataReimport(
        year=2026,
        event=Event.POLICY,
        applied=applied,
        manifest_key=KEY,
        manifest_lines=("after",) if changed else ("before",),
        recorded_lines=("before",),
        rows=105,
        camps_before={"Michigan": 40} if changed else {"Michigan": 34},
        camps_after={"Michigan": 34, "Michigan Classic": 5, "MNDI": 1},
        rows_changed=rows_changed,
        camp_files_updated=records,
    )


def test_the_runbook_reads_two_results_of_the_reimport() -> None:
    assert len(filters()) == 2, filters()


def test_the_runs_read_shows_michigans_refile_published_and_saved() -> None:
    published = PublishReport(
        plan=PublishPlan(caselist="openev", snapshots=()),
        applied=True,
        snapshots=(
            SnapshotOutcome(
                caselist="openev",
                snapshot="2026-policy",
                manifest_key=KEY,
                sources=(),
                manifest=ManifestOutcome.UPLOADED,
            ),
        ),
    )
    outcome = BucketReimport(
        reimport=reimport(applied=True, rows_changed=6, records=6, changed=True),
        restored=RESTORED,
        published=published,
        bundle=BundleSave(saved=True, reason="saved, 10 bytes", sha256="a" * 64, version_id="v2"),
    )

    assert through(filters()[0], printed(outcome)) == [
        '"status": "ok"',
        '"applied": true',
        '"rows": 105',
        '"rows_changed": 6',
        '"camp_files_updated": 6',
        '"manifest_published": "uploaded"',
        '"bundle_saved": true',
    ]


def test_the_checks_read_shows_nothing_left_to_change() -> None:
    outcome = BucketReimport(
        reimport=reimport(applied=False, rows_changed=0, records=0, changed=False), restored=RESTORED
    )

    assert through(filters()[1], printed(outcome)) == [
        '"rows": 105',
        '"rows_changed": 0',
        '"camp_files_updated": 0',
        '"manifest_changed": false',
    ]
