"""A landscape report over a copy restored from the bucket: the refusals (`v1-e40-t17`, the PM's ruling of 2026-10-30).

:func:`restored_copy_refusal` and :func:`publish_refusal` are the command's guards, and
:class:`LandscapeRunService`'s `parser_version` is the guard against a copy no build of this version has
parsed. The run over a copy, with its state in the data directory, is the CLI's test
(`test_landscape_command.py`): the wiring that keeps the state apart is the container's.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_restored_copy import (
    LANDSCAPE_RUNBOOK,
    publish_refusal,
    restored_copy_refusal,
)
from debate_core.application.landscape_run import (
    LandscapeRunRequest,
    LandscapeRunService,
    ParsedVersionNotInStore,
    UnknownCaselist,
)
from debate_core.application.landscape_scan import ScanAcceptanceLog
from debate_core.application.settings import RunStateMode
from debate_core.integrations.landscape.classification_store import LocalClassificationStore
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.landscape_run import (
    SYNTHETIC_RUN_CASELIST,
    SYNTHETIC_RUN_TODAY,
    SyntheticRun,
    plant_synthetic_run,
)
from debate_core.testing.landscape_store import PARSER_VERSION

CASELIST = SYNTHETIC_RUN_CASELIST
THIS_BUILD = "2026.10.27-docx-7"
"""The parser version the service is told it runs: not the planted store's `2026.10.20-docx-6`."""
LATER_BUILD = "2026.11.03-docx-8"


# ------------------------------------------------------------------------------------------------
# restored_copy_refusal: never the data directory, never in a checkout
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "home" / ".debate-research" / "dev"
    directory.mkdir(parents=True)
    return directory


def test_a_copy_beside_the_data_directory_is_accepted(data_dir: Path) -> None:
    copy = data_dir.parent / "landscape-copy-2026-11-05"
    copy.mkdir()

    assert restored_copy_refusal(copy, data_dir=data_dir) is None


def test_the_data_directory_itself_is_refused(data_dir: Path) -> None:
    reason = restored_copy_refusal(data_dir, data_dir=data_dir)

    assert reason is not None
    assert "data directory" in reason


def test_a_link_to_the_data_directory_is_the_data_directory(data_dir: Path) -> None:
    link = data_dir.parent / "link-to-dev"
    link.symlink_to(data_dir, target_is_directory=True)

    assert restored_copy_refusal(link, data_dir=data_dir) is not None


def test_a_directory_inside_the_data_directory_is_refused(data_dir: Path) -> None:
    inside = data_dir / "copy"
    inside.mkdir()

    reason = restored_copy_refusal(inside, data_dir=data_dir)

    assert reason is not None
    assert "inside" in reason


def test_a_directory_holding_the_data_directory_is_refused(data_dir: Path) -> None:
    reason = restored_copy_refusal(data_dir.parent, data_dir=data_dir)

    assert reason is not None
    assert "holds" in reason


def test_a_directory_inside_a_checkout_is_refused(tmp_path: Path, data_dir: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "config" / "profiles").mkdir(parents=True)
    copy = checkout / "landscape-copy"
    copy.mkdir()

    reason = restored_copy_refusal(copy, data_dir=data_dir)

    assert reason is not None
    assert "checkout" in reason


def test_a_path_that_is_no_directory_is_refused(data_dir: Path) -> None:
    missing = data_dir.parent / "never-restored"

    reason = restored_copy_refusal(missing, data_dir=data_dir)

    assert reason is not None
    assert "restore-run-state" in reason
    assert not missing.exists()


def test_no_reason_names_the_copys_path(tmp_path: Path, data_dir: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / "config" / "profiles").mkdir(parents=True)
    (checkout / "copy").mkdir()
    (data_dir / "copy").mkdir()
    for copy in (data_dir, data_dir / "copy", data_dir.parent, checkout / "copy", tmp_path / "missing"):
        reason = restored_copy_refusal(copy, data_dir=data_dir)
        assert reason is not None
        assert str(tmp_path) not in reason


# ------------------------------------------------------------------------------------------------
# publish_refusal: in bucket mode a publish reads a copy
# ------------------------------------------------------------------------------------------------


def test_a_publish_in_bucket_mode_without_a_copy_is_refused_naming_the_runbook() -> None:
    reason = publish_refusal(run_state=RunStateMode.BUCKET, publish=True, dry_run=False, restored_copy=False)

    assert reason is not None
    assert "--restored-copy" in reason
    assert LANDSCAPE_RUNBOOK == "docs/runbooks/landscape-report-from-the-cloud-run.md"


@pytest.mark.parametrize(
    ("run_state", "publish", "dry_run", "restored_copy"),
    [
        pytest.param(RunStateMode.BUCKET, True, False, True, id="bucket mode, publish from a copy"),
        pytest.param(RunStateMode.BUCKET, True, True, False, id="bucket mode, a publish's dry run"),
        pytest.param(RunStateMode.BUCKET, False, False, False, id="bucket mode, no publish"),
        pytest.param(RunStateMode.LOCAL, True, False, False, id="local mode, publish"),
    ],
)
def test_everything_else_goes_ahead(
    run_state: RunStateMode, publish: bool, dry_run: bool, restored_copy: bool
) -> None:
    assert (
        publish_refusal(run_state=run_state, publish=publish, dry_run=dry_run, restored_copy=restored_copy)
        is None
    )


# ------------------------------------------------------------------------------------------------
# LandscapeRunService(parser_version=...): a copy this build has parsed, or a refusal
# ------------------------------------------------------------------------------------------------

def _service(copy: SyntheticRun, state: Path, *, parser_version: str | None) -> LandscapeRunService:
    """The cards from `copy`, the landscape's state under `state`: as the container wires a copy."""
    cards = copy.data_dir
    objects = FsEvidenceObjectStore(cards)
    blobs = FsEvidenceObjectStore(cards, subdirectory=BLOB_DIRECTORY.parent)
    return LandscapeRunService(
        taxonomies=YamlTaxonomyRepository.load(copy.config_dir),
        config_dir=copy.config_dir,
        parsed_store=LocalParsedStore(cards),
        local=LocalEvidence(
            objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
        ),
        suppression=RecordedSuppressionList(local_suppression_list_file(cards)),
        classifications=LocalClassificationStore(state),
        objects=objects,
        run_log=None,
        reports_dir=state / "reports" / "landscape",
        acceptances=ScanAcceptanceLog(state / "landscape" / "scan-acceptances"),
        today=lambda: SYNTHETIC_RUN_TODAY,
        parser_version=parser_version,
    )


def _versions(copy: SyntheticRun, *names: str) -> None:
    """Give the planted parsed store these version directories, each a copy of the planted one."""
    parsed = copy.data_dir / "parsed" / CASELIST
    planted = parsed / PARSER_VERSION
    for name in names:
        if name != PARSER_VERSION:
            shutil.copytree(planted, parsed / name)
    if PARSER_VERSION not in names:
        shutil.rmtree(planted)


@pytest.fixture
def copy(tmp_path: Path) -> SyntheticRun:
    return plant_synthetic_run(tmp_path / "copy-root")


@pytest.mark.anyio
async def test_a_copy_parsed_only_by_an_older_build_is_refused_before_anything_is_written(
    copy: SyntheticRun, tmp_path: Path
) -> None:
    state = tmp_path / "dev"

    with pytest.raises(ParsedVersionNotInStore) as refused:
        await _service(copy, state, parser_version=THIS_BUILD).run(LandscapeRunRequest(caselist=CASELIST))

    message = str(refused.value)
    assert THIS_BUILD in message
    assert CASELIST in message
    assert "caselist parse" in message
    assert refused.value.known == (PARSER_VERSION,)
    assert not state.exists(), "no cache, queue or bundle"


@pytest.mark.anyio
async def test_a_copy_with_no_parsed_store_of_the_caselist_is_refused(copy: SyntheticRun, tmp_path: Path) -> None:
    shutil.rmtree(copy.data_dir / "parsed")

    with pytest.raises(ParsedVersionNotInStore) as refused:
        await _service(copy, tmp_path / "dev", parser_version=THIS_BUILD).run(
            LandscapeRunRequest(caselist=CASELIST)
        )

    assert refused.value.known == ()


@pytest.mark.anyio
async def test_a_copy_whose_newest_directory_is_a_later_builds_is_refused(copy: SyntheticRun, tmp_path: Path) -> None:
    _versions(copy, THIS_BUILD, LATER_BUILD)

    with pytest.raises(ParsedVersionNotInStore) as refused:
        await _service(copy, tmp_path / "dev", parser_version=THIS_BUILD).run(
            LandscapeRunRequest(caselist=CASELIST)
        )

    assert refused.value.known == (THIS_BUILD, LATER_BUILD)


@pytest.mark.anyio
async def test_a_copy_this_build_parsed_is_read_at_its_version_beside_an_older_one(
    copy: SyntheticRun, tmp_path: Path
) -> None:
    _versions(copy, PARSER_VERSION, THIS_BUILD)

    result = await _service(copy, tmp_path / "dev", parser_version=THIS_BUILD).run(
        LandscapeRunRequest(caselist=CASELIST)
    )

    assert (result.parsed_version, result.snapshot) == (THIS_BUILD, date(2026, 9, 15))
    assert result.classification.counts.cards == 9


@pytest.mark.anyio
async def test_an_unknown_caselist_is_refused_as_before_the_version_is_asked(
    copy: SyntheticRun, tmp_path: Path
) -> None:
    with pytest.raises(UnknownCaselist):
        await _service(copy, tmp_path / "dev", parser_version=THIS_BUILD).run(
            LandscapeRunRequest(caselist="hsnope26")
        )


@pytest.mark.anyio
async def test_without_a_parser_version_the_newest_directory_is_read_whatever_its_version(
    copy: SyntheticRun, tmp_path: Path
) -> None:
    result = await _service(copy, tmp_path / "dev", parser_version=None).run(
        LandscapeRunRequest(caselist=CASELIST)
    )

    assert result.parsed_version == PARSER_VERSION
