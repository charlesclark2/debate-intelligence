"""A build's own code reading a manifest whose `.cmir` row this build recorded as `CMIR` (`v1-e30-t26`).

Not collected: its name is not a test module's, and it is only ever run by its path, with a build's
source first on `PYTHONPATH` and `CMIR_MANIFEST_FILES` naming what `write_cmir_manifest_files.py`
wrote. It writes nothing outside pytest's temporary directory: the data directory is copied there
first.

With that copy it does what the weekly run and the Mac's agent do with a manifest: reads it with the
build's manifest reader, plans and runs `caselist parse` over it with the build's parser, publishes
it to a moto bucket as `store sync` does, and asks `caselist status` whether the two agree. A build
that refused `CMIR` would fail the parse's reading of the manifest (`UnreadableManifest`, "a stored
member with no size or format").
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.manifest import manifest_key, read_manifest_file
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_card_stats import CaselistCardStatsService
from debate_core.application.caselist_parse import CaselistParseService
from debate_core.integrations.docx_parser import DebateDocxParser
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.s3 import S3EvidenceObjectStore
from debate_core.testing.fakes.caselist import build_fake_caselist_repository
from debate_core.testing.fakes.suppression import empty_suppression_list

from .test_a_cmir_file_is_imported_as_cmir import CASELIST, CMIR_PATH, SNAPSHOT

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio


def _source() -> str:
    import debate_core

    return str(Path(debate_core.__file__).parents[4])


async def test_this_source_reads_a_manifest_carrying_cmir(
    tmp_path: Path, s3_client: S3Client, evidence_bucket: str, capsys: pytest.CaptureFixture[str]
) -> None:
    written = os.environ.get("CMIR_MANIFEST_FILES")
    if not written:
        pytest.fail("set CMIR_MANIFEST_FILES to what write_cmir_manifest_files.py wrote")
    data_dir = tmp_path / "evidence"
    shutil.copytree(Path(written) / "evidence", data_dir)
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    local = LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )

    rows = read_manifest_file(objects.path_for(manifest_key(CASELIST, SNAPSHOT)))
    (cmir_row,) = [json.loads(row) for row in rows if json.loads(row).get("path") == CMIR_PATH]

    stats = CaselistCardStatsService(build_fake_caselist_repository())
    # This build places cards given one at a time (`v1-e40-t36`); an earlier build takes them all.
    placing: dict[str, Any] = (
        {"card_placer": stats.placer} if hasattr(stats, "placer") else {"place_cards": stats.place}
    )
    parse = CaselistParseService(
        local=local,
        store=LocalParsedStore(data_dir),
        parser=DebateDocxParser(),
        runner=InProcessParseRunner(),
        suppression=empty_suppression_list(),
        **placing,
        failure_rate_threshold=0.5,
        failure_rate_minimum_sources=1,
    )
    plan = await parse.plan(CASELIST)
    parsed = await parse.run(plan)

    remote = S3EvidenceObjectStore(bucket=evidence_bucket, client=s3_client)
    publisher = CaselistPublishService(local=local, remote=remote, suppression=empty_suppression_list())
    published = await publisher.execute(await publisher.plan(CASELIST))
    status = await CaselistStatusService(
        local=local, remote=remote, suppression=empty_suppression_list()
    ).status()

    with capsys.disabled():
        print()
        print(f"reader: the debate_core source at {_source()}")
        print(f"manifest row read: format {cmir_row['format']}")
        formats = sorted(str(source.source_format) for source in plan.sources)
        print(f"caselist parse plan: {len(plan.sources)} sources, formats {formats}")
        print(
            f"caselist parse run: parsed {parsed.parsed}, unsupported {parsed.unsupported}, "
            f"failed {parsed.failed}"
        )
        print(f"store sync publish: succeeded {published.succeeded}")
        print(f"caselist status: in sync {status.in_sync}")
    assert published.succeeded
    assert status.in_sync
