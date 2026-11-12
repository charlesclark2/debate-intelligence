"""Which backfiles have no parsed-store directory at the running parser version (`v1-e40-t46`).

The store is an in-memory :class:`VersionDirectoryPlace` of the test's own: a caselist slug and the
version directories it holds, nothing else. Every expected value below is written by hand from the
PM's rulings of 2026-11-12, not read back from the code:

* a backfile with a directory at the reference version is not named, whatever older ones it holds;
* one without is named with every parser version it holds, newest first;
* one with no parsed store at all is named as not imported;
* when none is named, one line says all N are at the version;
* the reference is this build's parser version, unless the newest run that did not fail recorded
  the parser version it restored the parsed store at, which is then used and said.

Slugs are caselist slugs only; version names are parser-version labels only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

import pytest

from debate_core.application.caselist.backfile_parser_versions import (
    BackfileParserVersions,
    ReferenceSource,
    ReferenceVersion,
    backfile_parser_versions,
    reference_version,
)
from debate_core.application.ports.version_directories import DirectoryContents, RetirementMethod
from debate_core.application.sync_runs import (
    BucketRunDetails,
    RecordedRun,
    RestoreDetails,
    SyncRunDetails,
    SyncRunOutcome,
    SyncRunRecord,
)

BUILD: Final = "2026.11.03-docx-9"
"""The parser version of the build under test."""
DOCX_8: Final = "2026.10.30-docx-8"
DOCX_7: Final = "2026.10.27-docx-7"
DOCX_6: Final = "2026.10.20-docx-6"

THIS_BUILD: Final = ReferenceVersion(parser_version=BUILD, source=ReferenceSource.THIS_BUILD)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class InMemoryVersionDirectories:
    """`parsed/` as a dict of caselist to version directory names. Records what was listed."""

    def __init__(self, held: Mapping[str, Sequence[str]]) -> None:
        self._held = held
        self.listed: list[str] = []
        self.listed_caselists = False

    @property
    def location(self) -> str:
        return "s3://debate-test-evidence-in-memory"

    @property
    def method(self) -> RetirementMethod:
        return RetirementMethod.TAG

    async def caselists(self) -> tuple[str, ...]:
        self.listed_caselists = True
        return tuple(sorted(self._held))

    async def version_directories(self, caselist: str) -> tuple[str, ...]:
        self.listed.append(caselist)
        return tuple(self._held.get(caselist, ()))

    async def contents(self, caselist: str, version: str, *, count_tagged: bool) -> DirectoryContents:
        raise AssertionError("the check counts nothing in a directory")

    async def retire(self, caselist: str, version: str) -> int:
        raise AssertionError("the check retires nothing")

    async def restore(self, caselist: str, version: str) -> int:
        raise AssertionError("the check restores nothing")


async def check(held: Mapping[str, Sequence[str]], backfiles: Sequence[str]) -> BackfileParserVersions:
    return await backfile_parser_versions(
        InMemoryVersionDirectories(held), backfiles=backfiles, reference=THIS_BUILD
    )


# ------------------------------------------------------------------------------------------------
# Which backfiles are named
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_backfile_at_the_reference_version_only_is_not_named() -> None:
    found = await check({"hspolicy25": [BUILD]}, ["hspolicy25"])

    assert found.named == ()
    assert found.backfiles_checked == 1


@pytest.mark.anyio
async def test_a_backfile_at_an_older_version_only_is_named_with_it() -> None:
    found = await check({"hspolicy25": [DOCX_7]}, ["hspolicy25"])

    assert [(one.caselist, one.parser_versions, one.imported) for one in found.named] == [
        ("hspolicy25", (DOCX_7,), True)
    ]


@pytest.mark.anyio
async def test_a_backfile_holding_the_reference_and_an_older_version_is_not_named() -> None:
    """The state hspolicy25 is in after tonight's rebuild, until the docx-7 directory is retired."""
    found = await check({"hspolicy25": [DOCX_7, BUILD]}, ["hspolicy25"])

    assert found.named == ()


@pytest.mark.anyio
async def test_a_backfile_with_several_older_versions_is_named_with_each_newest_first() -> None:
    """Listed out of order, and with a second generation of one of them: each parser version once."""
    found = await check({"hspolicy24": [DOCX_6, DOCX_8, f"{DOCX_6}_reparse-2", DOCX_7]}, ["hspolicy24"])

    [named] = found.named
    assert named.parser_versions == (DOCX_8, DOCX_7, DOCX_6)


@pytest.mark.anyio
async def test_a_backfile_never_imported_is_named_as_not_imported() -> None:
    found = await check({}, ["hsld24"])

    [named] = found.named
    assert (named.caselist, named.parser_versions, named.imported) == ("hsld24", (), False)


@pytest.mark.anyio
async def test_a_second_generation_of_the_reference_version_is_at_the_reference_version() -> None:
    found = await check({"hsld25": [DOCX_7, f"{BUILD}_reparse-2"]}, ["hsld25"])

    assert found.named == ()


@pytest.mark.anyio
async def test_a_backfile_only_at_a_newer_version_is_named_with_it() -> None:
    """Literal to the rule: no directory at the reference, so named, with what it holds."""
    newer = "2026.12.01-docx-10"
    found = await check({"hsld25": [newer]}, ["hsld25"])

    [named] = found.named
    assert named.parser_versions == (newer,)


@pytest.mark.anyio
async def test_four_backfiles_are_named_in_the_order_the_setting_lists_them() -> None:
    held = {"hspolicy25": [DOCX_7], "hsld25": [BUILD], "hspolicy24": [DOCX_7, BUILD], "hsld24": []}

    found = await check(held, ["hspolicy25", "hsld25", "hspolicy24", "hsld24"])

    assert found.backfiles_checked == 4
    assert [one.caselist for one in found.named] == ["hspolicy25", "hsld24"]


@pytest.mark.anyio
async def test_only_the_backfiles_own_prefixes_are_listed() -> None:
    """The one new bucket read is each backfile's version directories: never every caselist's."""
    place = InMemoryVersionDirectories({"hspolicy25": [DOCX_7], "hspolicy26": [BUILD]})

    await backfile_parser_versions(place, backfiles=["hspolicy25", "hsld24"], reference=THIS_BUILD)

    assert place.listed == ["hspolicy25", "hsld24"]
    assert place.listed_caselists is False


@pytest.mark.anyio
async def test_no_backfiles_lists_nothing_and_says_nothing() -> None:
    place = InMemoryVersionDirectories({"hspolicy26": [BUILD]})

    found = await backfile_parser_versions(place, backfiles=[], reference=THIS_BUILD)

    assert place.listed == []
    assert found.lines() == ()
    assert found.as_json()["backfiles_checked"] == 0


# ------------------------------------------------------------------------------------------------
# What it says
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_lines_name_each_backfile_with_what_it_holds() -> None:
    held = {"hspolicy25": [DOCX_7], "hsld25": [BUILD], "hspolicy24": [DOCX_6, DOCX_7], "hsld24": []}

    found = await check(held, ["hspolicy25", "hsld25", "hspolicy24", "hsld24"])

    assert found.lines() == (
        "3 of 4 backfile(s) have no parsed-store directory at parser 2026.11.03-docx-9 (this build):",
        "  hspolicy25: holds 2026.10.27-docx-7",
        "  hspolicy24: holds 2026.10.27-docx-7, 2026.10.20-docx-6",
        "  hsld24: not imported (no parsed store)",
    )


@pytest.mark.anyio
async def test_one_line_says_all_are_at_the_version_when_none_is_named() -> None:
    held = {"hspolicy25": [DOCX_7, BUILD], "hsld25": [BUILD], "hspolicy24": [BUILD], "hsld24": [BUILD]}

    found = await check(held, ["hspolicy25", "hsld25", "hspolicy24", "hsld24"])

    assert found.lines() == ("All 4 backfile(s) are at parser 2026.11.03-docx-9 (this build).",)


@pytest.mark.anyio
async def test_the_json_gives_the_reference_its_source_and_the_named_backfiles() -> None:
    found = await check(
        {"hspolicy25": [DOCX_6, DOCX_7], "hsld25": [BUILD]}, ["hspolicy25", "hsld25", "hsld24"]
    )

    assert found.as_json() == {
        "reference": {"parser_version": BUILD, "source": "this_build", "run_id": None},
        "backfiles_checked": 3,
        "named": [
            {"caselist": "hspolicy25", "imported": True, "parser_versions": [DOCX_7, DOCX_6]},
            {"caselist": "hsld24", "imported": False, "parser_versions": []},
        ],
    }


# ------------------------------------------------------------------------------------------------
# The reference version
# ------------------------------------------------------------------------------------------------

WEDNESDAY: Final = datetime(2026, 11, 11, 6, 0, tzinfo=UTC)


def a_run(
    started: datetime, *, outcome: SyncRunOutcome = SyncRunOutcome.COMPLETED, restored_at: str | None = None
) -> RecordedRun:
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    record = SyncRunRecord(
        run_id=run_id,
        environment="dev",
        mode="run",
        started_at=started,
        finished_at=started + timedelta(minutes=20),
        outcome=outcome,
    )
    restore = RestoreDetails(started_at=started, finished_at=started, parsed_version=restored_at)
    details = SyncRunDetails(run_id=run_id, bucket_run=BucketRunDetails(restore=restore))
    return RecordedRun(record=record, details=details)


def test_with_no_run_the_reference_is_this_builds_parser_version() -> None:
    assert reference_version([], build_version=BUILD) == THIS_BUILD


def test_the_newest_run_that_recorded_a_parser_version_is_preferred_and_named() -> None:
    runs = [a_run(WEDNESDAY, restored_at=DOCX_8), a_run(WEDNESDAY - timedelta(days=7), restored_at=DOCX_7)]

    chosen = reference_version(runs, build_version=BUILD)

    assert chosen == ReferenceVersion(
        parser_version=DOCX_8, source=ReferenceSource.NEWEST_RUN, run_id="20261111T060000Z"
    )
    assert chosen.described == "parser 2026.10.30-docx-8 (recorded by run 20261111T060000Z)"


def test_a_failed_run_and_a_run_that_restored_no_parsed_store_are_passed_over() -> None:
    """Newest first: a failed run, then a `--publish-pending` that restored no parsed store."""
    runs = [
        a_run(WEDNESDAY + timedelta(days=1), outcome=SyncRunOutcome.FAILED, restored_at="2026.12.01-docx-10"),
        a_run(WEDNESDAY + timedelta(hours=2), outcome=SyncRunOutcome.PUBLISH_PENDING),
        a_run(WEDNESDAY, outcome=SyncRunOutcome.NOTHING_NEW, restored_at=DOCX_8),
    ]

    assert reference_version(runs, build_version=BUILD).run_id == "20261111T060000Z"


def test_runs_in_any_order_give_the_newest() -> None:
    runs = [a_run(WEDNESDAY - timedelta(days=7), restored_at=DOCX_7), a_run(WEDNESDAY, restored_at=DOCX_8)]

    assert reference_version(runs, build_version=BUILD).parser_version == DOCX_8


def test_a_run_without_details_is_passed_over() -> None:
    bare = a_run(WEDNESDAY, restored_at=DOCX_8)

    chosen = reference_version([RecordedRun(record=bare.record, details=None)], build_version=BUILD)

    assert chosen == THIS_BUILD
    assert chosen.described == "parser 2026.11.03-docx-9 (this build)"


@pytest.mark.anyio
async def test_a_reference_from_a_run_is_said_on_the_line_and_in_the_json() -> None:
    reference = ReferenceVersion(
        parser_version=BUILD, source=ReferenceSource.NEWEST_RUN, run_id="20261111T060000Z"
    )

    found = await backfile_parser_versions(
        InMemoryVersionDirectories({"hspolicy25": [BUILD]}), backfiles=["hspolicy25"], reference=reference
    )

    assert found.lines() == (
        "All 1 backfile(s) are at parser 2026.11.03-docx-9 (recorded by run 20261111T060000Z).",
    )
    assert found.as_json()["reference"] == {
        "parser_version": BUILD,
        "source": "newest_run",
        "run_id": "20261111T060000Z",
    }
