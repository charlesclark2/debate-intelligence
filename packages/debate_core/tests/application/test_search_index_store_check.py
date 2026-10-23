"""Has every store the weekly run's search index stage will index been parsed by this build?

`v1-e34-t30`. The stage (`v1-e39-t09`) indexes the run's caselists plus `openev` from the running
parser version's directory, and a store without one leaves the run without a current index.
:class:`SearchIndexStoreCheck` says so before the run, and `doctor --search-index` renders it.

Each test lays out version directories under `tmp_path` as `caselist parse` names them, through the
real local parsed store; nothing else of a store is needed, because the check lists directories and
reads no file. Each expected value is written out by hand. Nothing reaches a network.

The module under test is new, so it is looked up when a test runs: against a source without it
every test here fails by itself.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

from debate_core.application import caselist_sync
from debate_core.application.ports.parsed_store import ParsedStore
from debate_core.integrations.local.parsed_store import LocalParsedStore

pytestmark = pytest.mark.anyio

INSTALLED = "2026.10.20-docx-6"
OLDER = "2026.09.30-docx-5"
NEWER = "2026.11.02-docx-7"
TURNED_OFF = (
    "turned off by setting (caselist.refresh_search_index); `tub index build` and "
    "`tub index publish` do it by hand"
)
NO_BUCKET = "no search index stage is wired in: an environment that names no evidence bucket has none"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def module() -> Any:
    return importlib.import_module("debate_core.application.search_index_store_check")


def parsed_as(data_dir: Path, **stores: tuple[str, ...]) -> LocalParsedStore:
    """A parsed store holding, for each store named, exactly the version directories given."""
    for store, versions in stores.items():
        for version in versions:
            (data_dir / "parsed" / store / version).mkdir(parents=True)
    return LocalParsedStore(data_dir)


class ListsNothing:
    """A parsed store that fails the test if the check lists it."""

    async def version_directories(self, caselist: str) -> tuple[str, ...]:
        pytest.fail(f"the check listed {caselist}'s version directories where it does not apply")


def check(
    parsed_store: ParsedStore | ListsNothing,
    *caselists: str,
    bucket_named: bool = True,
    refresh_search_index: bool = True,
) -> Any:
    return module().SearchIndexStoreCheck(
        caselists=caselists,
        bucket_named=bucket_named,
        refresh_search_index=refresh_search_index,
        parsed_store=parsed_store,
        parser_version=INSTALLED,
    )


# ------------------------------------------------------------------------------------------------
# The stores: the stage's own list
# ------------------------------------------------------------------------------------------------


def test_the_stores_are_the_runs_caselists_each_once_in_order_then_openev() -> None:
    assert caselist_sync.search_index_stores(["hsld26", "hspolicy26", "hsld26"]) == (
        "hsld26",
        "hspolicy26",
        "openev",
    )
    assert caselist_sync.search_index_stores([]) == ("openev",)


async def test_every_store_parsed_by_the_installed_parser_passes(tmp_path: Path) -> None:
    store = parsed_as(tmp_path, hsld26=(OLDER, INSTALLED), hspolicy26=(INSTALLED,), openev=(INSTALLED,))

    found = await check(store, "hsld26", "hspolicy26").run()

    assert found.applies is True
    assert found.does_not_apply is None
    assert found.unparsed == ()
    assert found.as_json() == {
        "applies": True,
        "does_not_apply": None,
        "parser_version": "2026.10.20-docx-6",
        "caselists": ["hsld26", "hspolicy26"],
        "stores": [
            {"store": "hsld26", "parsed": True, "fix": None},
            {"store": "hspolicy26", "parsed": True, "fix": None},
            {"store": "openev", "parsed": True, "fix": None},
        ],
        "unparsed": [],
    }


# ------------------------------------------------------------------------------------------------
# What counts as parsed
# ------------------------------------------------------------------------------------------------


async def test_a_store_with_no_version_directory_is_unparsed_and_named_with_its_parse_command(
    tmp_path: Path,
) -> None:
    store = parsed_as(tmp_path, hsld26=(INSTALLED,))

    found = await check(store, "hsld26", "hspolicy26").run()

    assert [one.as_json() for one in found.stores] == [
        {"store": "hsld26", "parsed": True, "fix": None},
        {
            "store": "hspolicy26",
            "parsed": False,
            "fix": "debate-research caselist parse --caselist hspolicy26",
        },
        {"store": "openev", "parsed": False, "fix": "debate-research caselist parse --caselist openev"},
    ]
    assert found.as_json()["unparsed"] == ["hspolicy26", "openev"]


async def test_a_store_parsed_only_by_an_older_parser_is_unparsed(tmp_path: Path) -> None:
    store = parsed_as(tmp_path, hsld26=(OLDER, f"{OLDER}_reparse-2"), openev=(INSTALLED,))

    found = await check(store, "hsld26").run()

    assert [(one.store, one.parsed) for one in found.stores] == [("hsld26", False), ("openev", True)]


async def test_a_store_parsed_only_by_a_newer_parser_is_unparsed_by_this_build(tmp_path: Path) -> None:
    store = parsed_as(tmp_path, hsld26=(NEWER,), openev=(INSTALLED,))

    found = await check(store, "hsld26").run()

    assert [(one.store, one.parsed) for one in found.stores] == [("hsld26", False), ("openev", True)]


async def test_a_later_generation_of_the_installed_parser_counts_as_parsed(tmp_path: Path) -> None:
    """A forced re-parse writes `<version>_reparse-<n>` beside the first; the stage reads the newest."""
    store = parsed_as(
        tmp_path, hsld26=(f"{INSTALLED}_reparse-2",), openev=(INSTALLED, f"{INSTALLED}_reparse-3")
    )

    found = await check(store, "hsld26").run()

    assert found.unparsed == ()


async def test_a_version_that_only_begins_with_the_installed_one_is_not_it(tmp_path: Path) -> None:
    """`2026.10.20-docx-60` is another parser version, not a generation of `2026.10.20-docx-6`."""
    store = parsed_as(tmp_path, hsld26=(f"{INSTALLED}0", f"{INSTALLED}-rc1"), openev=(INSTALLED,))

    found = await check(store, "hsld26").run()

    assert [one.store for one in found.unparsed] == ["hsld26"]


async def test_with_no_caselist_configured_openev_alone_is_checked(tmp_path: Path) -> None:
    found = await check(parsed_as(tmp_path)).run()

    assert found.as_json()["caselists"] == []
    assert [(one.store, one.parsed) for one in found.stores] == [("openev", False)]


# ------------------------------------------------------------------------------------------------
# When it applies: when the run has the stage at all
# ------------------------------------------------------------------------------------------------


async def test_with_the_setting_off_it_does_not_apply_says_why_and_reads_nothing() -> None:
    found = await check(ListsNothing(), "hsld26", refresh_search_index=False).run()

    assert found.applies is False
    assert found.does_not_apply == TURNED_OFF
    assert found.stores == ()
    assert found.unparsed == ()
    assert found.as_json()["stores"] == []


async def test_with_no_bucket_it_does_not_apply_says_why_and_reads_nothing() -> None:
    found = await check(ListsNothing(), "hsld26", bucket_named=False).run()

    assert found.applies is False
    assert found.does_not_apply == NO_BUCKET
    assert found.unparsed == ()


async def test_with_neither_it_names_the_setting_first_as_the_run_does() -> None:
    found = await check(ListsNothing(), "hsld26", bucket_named=False, refresh_search_index=False).run()

    assert found.does_not_apply == TURNED_OFF


@pytest.mark.parametrize(
    ("bucket_named", "refresh_search_index", "reason"),
    [(True, True, None), (True, False, TURNED_OFF), (False, True, NO_BUCKET), (False, False, TURNED_OFF)],
)
def test_the_rule_the_stage_is_wired_by(
    bucket_named: bool, refresh_search_index: bool, reason: str | None
) -> None:
    assert (
        caselist_sync.why_no_search_index_stage(
            bucket_named=bucket_named, refresh_search_index=refresh_search_index
        )
        == reason
    )


# ------------------------------------------------------------------------------------------------
# What a finding may hold
# ------------------------------------------------------------------------------------------------


async def test_the_findings_name_no_path(tmp_path: Path) -> None:
    store = parsed_as(tmp_path, hsld26=(OLDER,))

    found = await check(store, "hsld26").run()

    said = repr(found.as_json())
    assert str(tmp_path) not in said
    assert "parsed/" not in said
