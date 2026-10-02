"""Every path that can store or publish a caselist source consults the suppression list.

A removal is undone by the next cumulative archive unless *every* import path checks the list, and
the failure mode the project has learned to fear is not a path that checks wrongly but a fourth
path, added later, that never checks at all and reports success. So the guarantee is made
structural rather than conventional, and this module fails when the structure is broken:

1. **No service can be built without the list.** Each class that stores, publishes or syncs a
   source takes `suppression` as a required keyword argument with no default; so do the manifest
   row renderer and the publish planner. Re-adding a default — the shape the list had before
   `v1-e30-t07`, `suppressed_hashes=frozenset()` — fails here.
2. **Nothing writes caselist records except through the pipeline.** Source documents,
   disclosures and camp files are written in exactly the modules listed below, each of which builds
   a :class:`~debate_core.application.caselist.pipeline.SourceImportPipeline` with the list. A
   module anywhere else in the source tree that calls one of the record writes fails here, with a
   message saying what to do instead.

The scan reads the source with :mod:`ast`, so a call is found however it is spelled across lines,
and a mention in a docstring or a comment is not mistaken for one.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.caselist.import_service import CaselistImportService
from debate_core.application.caselist.manifest import render_rows
from debate_core.application.caselist.openev_import_service import OpenEvImportService
from debate_core.application.caselist.openev_manifest import merged_manifest_lines
from debate_core.application.caselist.pipeline import SourceImportPipeline
from debate_core.application.caselist.publish_plan import build_publish_plan
from debate_core.application.caselist.publish_service import CaselistPublishService
from debate_core.application.caselist.status_service import CaselistStatusService
from debate_core.application.caselist_sync import CaselistSyncService
from debate_core.application.evidence_sync import EvidenceSyncService

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
SOURCE_TREES = (REPOSITORY_ROOT / "packages",)

#: The record writes of `CaselistRepository` that put a source, or a record of one, into the store.
RECORD_WRITES = frozenset({"put_source", "record_disclosure", "record_camp_file", "file_source"})

#: The only modules that may call them: the pipeline and the two importers built on it. A module
#: that implements the port (an adapter, a fake) defines these methods and never calls them.
IMPORT_PATHS = frozenset(
    {
        "packages/debate_core/src/debate_core/application/caselist/pipeline.py",
        "packages/debate_core/src/debate_core/application/caselist/import_service.py",
        "packages/debate_core/src/debate_core/application/caselist/openev_import_service.py",
    }
)

GUARDED: tuple[tuple[str, Callable[..., Any]], ...] = (
    ("SourceImportPipeline", SourceImportPipeline),
    ("CaselistImportService", CaselistImportService),
    ("OpenEvImportService", OpenEvImportService),
    ("CaselistPublishService", CaselistPublishService),
    ("CaselistStatusService", CaselistStatusService),
    ("EvidenceSyncService", EvidenceSyncService),
    # Stores nothing itself, but skips a removed camp file on the list's word (v1-e34-t07): a
    # default here would let a composition root build a pull that skips nothing.
    ("CaselistSyncService", CaselistSyncService),
    ("render_rows", render_rows),
    ("merged_manifest_lines", merged_manifest_lines),
    ("build_publish_plan", build_publish_plan),
)


@pytest.mark.parametrize(("name", "guarded"), GUARDED, ids=[name for name, _ in GUARDED])
def test_the_suppression_list_is_a_required_argument_with_no_default(
    name: str, guarded: Callable[..., Any]
) -> None:
    parameter = inspect.signature(guarded).parameters.get("suppression")
    assert parameter is not None, f"{name} no longer takes the suppression list"
    assert parameter.default is inspect.Parameter.empty, (
        f"{name}(suppression=...) has a default, so a caller can leave the list off and suppress nothing"
    )
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def _production_modules() -> Iterator[Path]:
    for tree in SOURCE_TREES:
        for path in tree.rglob("*.py"):
            parts = path.relative_to(REPOSITORY_ROOT).parts
            if "tests" in parts or "src" not in parts:
                continue
            yield path


def _record_write_calls(path: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if not isinstance(node, ast.Call):
            continue
        called = node.func
        name = (
            called.attr
            if isinstance(called, ast.Attribute)
            else called.id
            if isinstance(called, ast.Name)
            else None
        )
        if name in RECORD_WRITES:
            found.append((node.lineno, name))
    return found


def test_only_the_import_pipeline_writes_caselist_records() -> None:
    offenders = [
        f"{path.relative_to(REPOSITORY_ROOT)}:{line} calls {name}()"
        for path in _production_modules()
        for line, name in _record_write_calls(path)
        if path.relative_to(REPOSITORY_ROOT).as_posix() not in IMPORT_PATHS
    ]
    assert not offenders, (
        "a module outside the import pipeline writes caselist records, so nothing makes it consult the "
        "removal suppression list. Store sources through SourceImportPipeline (which requires the list) "
        "and add the module to IMPORT_PATHS only once it does:\n" + "\n".join(offenders)
    )


def test_every_import_path_builds_its_pipeline_with_the_list() -> None:
    """The allow-list is only safe if every module on it really does go through the pipeline."""
    for relative in sorted(
        IMPORT_PATHS - {"packages/debate_core/src/debate_core/application/caselist/pipeline.py"}
    ):
        tree = ast.parse((REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))
        builds = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "SourceImportPipeline"
        ]
        assert builds, f"{relative} writes caselist records but never builds a SourceImportPipeline"
        for build in builds:
            assert "suppression" in {keyword.arg for keyword in build.keywords}, (
                f"{relative}:{build.lineno} builds a SourceImportPipeline without the suppression list"
            )


def test_the_scan_finds_a_record_write_when_there_is_one(tmp_path: Path) -> None:
    """The scan above passing proves nothing unless it can fail: here it is shown a call to find."""
    module = tmp_path / "new_importer.py"
    module.write_text(
        '"""record_disclosure() in a docstring is not a call."""\n'
        "async def store(caselists, disclosure):\n"
        "    await caselists.record_disclosure(\n"
        "        disclosure,\n"
        "    )\n",
        encoding="utf-8",
    )
    assert _record_write_calls(module) == [(3, "record_disclosure")]


def test_the_row_renderer_refuses_a_row_the_list_stops_whoever_built_it() -> None:
    """The backstop under every manifest writer: a row for a suppressed file is never rendered."""
    from datetime import UTC, datetime

    from debate_core.application.caselist.manifest import SuppressedRowRefused
    from debate_core.application.ports.suppression import (
        ReasonCode,
        SuppressionAction,
        SuppressionEntry,
        SuppressionState,
        disclosure_digest,
    )

    digest = "c" * 64
    row = {"kind": "member", "sha256": digest, "path": "Maple Grove/QX/a.docx", "classification": "NEW"}
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=digest,
        recorded_at=datetime(2026, 9, 30, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )
    whole = SuppressionState.from_entries([entry])
    one_disclosure = SuppressionState.from_entries(
        [entry.evolve(disclosure=disclosure_digest("hsld26", "Maple Grove/QX/a.docx"))]
    )

    assert render_rows([row], suppression=SuppressionState(), disclosure_scope="hsld26")
    with pytest.raises(SuppressedRowRefused) as refused:
        render_rows([row], suppression=whole, disclosure_scope=None)
    assert "Maple Grove" not in str(refused.value)
    with pytest.raises(SuppressedRowRefused):
        render_rows([row], suppression=one_disclosure, disclosure_scope="hsld26")
    other_team = {**row, "path": "Cedar Hollow/ZaLu/a.docx"}
    assert render_rows([other_team], suppression=one_disclosure, disclosure_scope="hsld26")
