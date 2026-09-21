"""The wire models read the synthetic fixtures, tolerate unknown fields, and translate to port values."""

from __future__ import annotations

from datetime import date

from pydantic import SecretStr

from debate_core.application.ports.caselist_source import ArchiveKind
from debate_core.integrations.opencaselist.models import (
    CaselistRecord,
    DownloadRecord,
    LoginResponse,
    OpenEvRecord,
    parse_archive_name,
)

from .conftest import load_fixture


def test_caselists_parse_with_unknown_fields_ignored_and_name_as_the_slug() -> None:
    infos = [CaselistRecord.model_validate(raw).to_info() for raw in load_fixture("caselists.json")]

    assert [info.slug for info in infos if info] == ["testcl26", "testcl25", "testpol26"]
    assert infos[1] is not None and infos[1].archived is True
    assert infos[0] is not None and infos[0].event == "ld"


def test_a_caselist_whose_name_is_not_a_slug_translates_to_nothing() -> None:
    assert CaselistRecord(name="Not A Slug", slug=None).to_info() is None
    info = CaselistRecord(name=None, slug="/hsld26").to_info()
    assert info is not None and info.slug == "hsld26"


def test_a_mysql_integer_archived_flag_reads_as_a_boolean() -> None:
    assert CaselistRecord.model_validate({"name": "testcl26", "archived": 1}).archived is True


def test_archive_listings_are_dated_and_kinded_from_their_names() -> None:
    listings = [
        DownloadRecord.model_validate(raw).to_listing("testcl26") for raw in load_fixture("downloads.json")
    ]

    assert [(item.kind, item.archive_date) for item in listings] == [
        (ArchiveKind.WEEKLY, date(2026, 9, 8)),
        (ArchiveKind.WEEKLY, date(2026, 9, 15)),
        (ArchiveKind.FULL, date(2026, 9, 15)),
        (ArchiveKind.UNRECOGNISED, None),
    ]
    assert all(item.caselist == "testcl26" and item.size_bytes is None for item in listings)


def test_an_archive_named_for_another_caselist_or_an_impossible_date_is_unrecognised() -> None:
    assert parse_archive_name("otherc26-weekly-2026-09-15.zip", "testcl26") == (
        ArchiveKind.UNRECOGNISED,
        None,
    )
    assert parse_archive_name("testcl26-weekly-2026-02-30.zip", "testcl26") == (
        ArchiveKind.UNRECOGNISED,
        None,
    )


def test_openev_files_parse_tags_from_an_object_or_from_json_text() -> None:
    files = [OpenEvRecord.model_validate(raw).to_file() for raw in load_fixture("openev.json")]

    assert [(item.openev_id, item.tags) for item in files] == [(7001, ("neg", "t")), (7002, ("k",))]
    assert files[1].filename == "Synthetic-Kritik.docx", "falls back to the table's `name` column"


def test_an_openev_path_never_appears_in_a_repr() -> None:
    raw = load_fixture("openev.json")[0]
    record = OpenEvRecord.model_validate(raw)

    assert raw["path"] not in repr(record)
    assert raw["path"] not in repr(record.to_file())


def test_the_login_response_holds_the_token_as_a_secret(fake_token: str) -> None:
    response = LoginResponse.model_validate({"message": "Successfully logged in", "token": fake_token})

    assert isinstance(response.token, SecretStr)
    assert fake_token not in repr(response)
    assert fake_token not in str(response)
