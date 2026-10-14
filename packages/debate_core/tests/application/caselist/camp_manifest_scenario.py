"""The history every build writes a camp release manifest from, for `stored_camp_manifests/` (`v1-e30-t14`).

Two pulls through the real sync, as the weekly agent runs them, on the synthetic camp files of
`tests/fixtures/openev/`: 512 first; then 512 deleted upstream and uploaded again as 640 at the same
path, with 700, another camp's file of the same name, listed beside it. It uses nothing a build from
before `v1-e30-t14` lacks, so the same function runs against the installed build's source, the start
commit's and this build's (`stored_camp_manifests/README.md`).

Not a test module, and never collected.
"""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.openev.build_synthetic_openev import DOCUMENT_BODIES

from debate_core.application.caselist.manifest import read_manifest_lines
from debate_core.application.caselist.openev_manifest import openev_manifest_key
from debate_core.application.ports.caselist_source import OpenEvFile
from debate_core.domain.caselist import Event
from debate_core.integrations.local import FsEvidenceObjectStore

from .conftest import RemovalWorld
from .test_sync_skips_suppressed_downloads import ESTUARY, YEAR, FakeOpenEvSource, pull

RELEASE_KEY = openev_manifest_key(YEAR, Event.POLICY)
STORED = Path(__file__).parent / "stored_camp_manifests"
MANIFEST_NAME = "2026-policy.jsonl"

REVISION = ESTUARY.model_copy(update={"openev_id": 640})
OTHER_CAMP = ESTUARY.model_copy(
    update={"openev_id": 700, "path": f"openev/{YEAR}/Quillfeather/TSF-Estuary Solvency Advocate.docx"}
)
#: A camp file listed after the history: what the next pull an older build makes imports into it.
NEXT_WEEK = OpenEvFile(
    openev_id=900,
    path=f"openev/{YEAR}/Juniper/JDI-Harbor Tariffs Neg.docx",
    filename="JDI-Harbor Tariffs Neg.docx",
    year=YEAR,
    tags=("policy",),
)

ESTUARY_BODY = DOCUMENT_BODIES["estuary-solvency"]
REVISED_BODY = DOCUMENT_BODIES["canal-counterplan-revised"]
OTHER_CAMP_BODY = DOCUMENT_BODIES["harbor-tariffs-aff"]
NEXT_WEEK_BODY = DOCUMENT_BODIES["harbor-tariffs-neg"]

ROWS = (
    "openev-512-TSF-Estuary_Solvency_Advocate.docx",
    "openev-640-TSF-Estuary_Solvency_Advocate.docx",
    "openev-700-TSF-Estuary_Solvency_Advocate.docx",
)
NEXT_WEEK_ROW = "openev-900-JDI-Harbor_Tariffs_Neg.docx"


async def two_pulls(world: RemovalWorld) -> FakeOpenEvSource:
    """512 pulled; then 640 and 700 pulled. Each pull imports, writes the manifest and publishes it."""
    source = FakeOpenEvSource([(ESTUARY, ESTUARY_BODY)])
    await pull(world, source)
    source.files = [(REVISION, REVISED_BODY), (OTHER_CAMP, OTHER_CAMP_BODY)]
    await pull(world, source)
    return source


def release_manifest(world: RemovalWorld) -> Path:
    """Where this machine keeps the release manifest the history writes."""
    return FsEvidenceObjectStore(world.data_dir).path_for(RELEASE_KEY)


def release_lines(world: RemovalWorld) -> list[str]:
    return read_manifest_lines(release_manifest(world))
