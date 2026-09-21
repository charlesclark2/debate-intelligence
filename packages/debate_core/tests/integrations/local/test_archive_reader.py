"""The archive reader refuses what it should, counts what it skips, and reads the rest.

This is the module that handles a file downloaded from the internet, so most of these tests are
about what it will *not* do: escape the archive, follow a symlink, or open something far larger
than a weekly archive has any business being. The rest pin the two properties the importer
depends on — one entry per member, in path order, with the digest of the bytes actually read.

Every archive here is built by `tests/fixtures/caselist/build_synthetic_archives.py` or by the
`malformed_zip` helper below. Nothing real is read.
"""

from __future__ import annotations

import stat
import zipfile
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    EXPECTED_SNAPSHOTS,
    SNAPSHOTS,
    build_snapshot_directories,
    build_snapshot_zips,
)

from debate_core.integrations.local.archive_reader import (
    ArchiveMember,
    ArchiveTooLarge,
    SkippedMember,
    SkipReason,
    UnreadableArchive,
    archive_digest,
    common_root_to_strip,
    read_archive,
)

#: Ceilings well above anything the fixture builds, for the tests that are not about limits.
GENEROUS_LIMITS = {"max_archive_bytes": 64 * 1024 * 1024, "max_unpacked_bytes": 64 * 1024 * 1024}

LAST_SNAPSHOT = SNAPSHOTS[-1].snapshot


def entries_of(source: Path, **limits: int) -> list[ArchiveMember | SkippedMember]:
    return list(read_archive(source, **(GENEROUS_LIMITS | limits)))


def members_of(source: Path, **limits: int) -> list[ArchiveMember]:
    return [entry for entry in entries_of(source, **limits) if isinstance(entry, ArchiveMember)]


def skips_of(source: Path, **limits: int) -> list[SkippedMember]:
    return [entry for entry in entries_of(source, **limits) if isinstance(entry, SkippedMember)]


def malformed_zip(destination: Path, members: Mapping[str, bytes], *, symlinks: tuple[str, ...] = ()) -> Path:
    """A zip built entry by entry, so a test can put a name in it that no tool would write."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as archive:
        for name, content in members.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = ((stat.S_IFLNK | 0o777) << 16) if name in symlinks else (0o644 << 16)
            archive.writestr(info, content)
    return destination


@pytest.fixture
def snapshot_zips(tmp_path: Path) -> dict[date, Path]:
    return build_snapshot_zips(tmp_path / "zips")


@pytest.fixture
def snapshot_directories(tmp_path: Path) -> dict[date, Path]:
    return build_snapshot_directories(tmp_path / "directories")


# ------------------------------------------------------------------------------------------------
# Nothing lands outside the archive
# ------------------------------------------------------------------------------------------------


def test_a_member_climbing_out_of_the_archive_is_skipped_and_counted(
    snapshot_zips: dict[date, Path],
) -> None:
    """The zip-slip shape. The fixture's last archive carries one on purpose (ac5)."""
    skipped = skips_of(snapshot_zips[LAST_SNAPSHOT])

    escaping = [skip for skip in skipped if skip.reason is SkipReason.PATH_OUTSIDE_ARCHIVE]
    assert [skip.path for skip in escaping] == ["../escaped.docx"]


@pytest.mark.parametrize(
    "name",
    [
        "../escaped.docx",
        "../../escaped.docx",
        "nested/../../escaped.docx",
        "/absolute/escaped.docx",
        "C:/windows/escaped.docx",
        "..\\windows-style.docx",
        "school/team/../../../escaped.docx",
    ],
)
def test_every_shape_of_escaping_name_is_refused(tmp_path: Path, name: str) -> None:
    archive = malformed_zip(tmp_path / "hostile.zip", {name: b"x", "School/Team/real.docx": b"y"})

    skipped = skips_of(archive)

    assert [skip.reason for skip in skipped] == [SkipReason.PATH_OUTSIDE_ARCHIVE]
    assert [member.path for member in members_of(archive)] == ["School/Team/real.docx"]


def test_an_escaping_member_is_never_read(tmp_path: Path) -> None:
    """A skip carries no bytes, so nothing about the member reaches the importer or the disk."""
    archive = malformed_zip(tmp_path / "hostile.zip", {"../escaped.docx": b"payload"})

    (skipped,) = skips_of(archive)

    assert not hasattr(skipped, "data")
    assert not (tmp_path / "escaped.docx").exists()


def test_reading_an_archive_writes_nothing_at_all(tmp_path: Path, snapshot_zips: dict[date, Path]) -> None:
    """The reader hands bytes to its caller; it never unpacks to a staging directory."""
    before = sorted(path.name for path in tmp_path.rglob("*"))

    entries_of(snapshot_zips[LAST_SNAPSHOT])

    assert sorted(path.name for path in tmp_path.rglob("*")) == before


# ------------------------------------------------------------------------------------------------
# Symlinks are skipped, never followed
# ------------------------------------------------------------------------------------------------


def test_a_symlink_in_a_zip_is_skipped(snapshot_zips: dict[date, Path]) -> None:
    skipped = skips_of(snapshot_zips[LAST_SNAPSHOT])

    links = [skip for skip in skipped if skip.reason is SkipReason.SYMLINK]
    assert [skip.path for skip in links] == ["Cedar Hollow/ZaLu/latest-aff.docx"]


def test_a_symlink_in_an_unpacked_directory_is_skipped(
    snapshot_directories: dict[date, Path],
) -> None:
    skipped = skips_of(snapshot_directories[LAST_SNAPSHOT])

    links = [skip for skip in skipped if skip.reason is SkipReason.SYMLINK]
    assert [skip.path for skip in links] == ["Cedar Hollow/ZaLu/latest-aff.docx"]


def test_a_symlinked_directory_is_not_descended_into(tmp_path: Path) -> None:
    """Following one would import files the archive does not contain."""
    outside = tmp_path / "outside"
    (outside / "Secret" / "AB").mkdir(parents=True)
    (outside / "Secret" / "AB" / "Secret-AB-Aff-Cup-Round 1.docx").write_bytes(b"not in the archive")
    root = tmp_path / "archive"
    (root / "Maple Grove" / "QX").mkdir(parents=True)
    (root / "Maple Grove" / "QX" / "Maple Grove-QX-Aff-Cup-Round 1.docx").write_bytes(b"real")
    (root / "linked").symlink_to(outside, target_is_directory=True)

    paths = [member.path for member in members_of(root)]

    assert paths == ["Maple Grove/QX/Maple Grove-QX-Aff-Cup-Round 1.docx"]


# ------------------------------------------------------------------------------------------------
# Size is checked before anything is read
# ------------------------------------------------------------------------------------------------


def test_a_zip_over_the_archive_ceiling_is_refused_before_it_is_opened(
    snapshot_zips: dict[date, Path],
) -> None:
    archive = snapshot_zips[LAST_SNAPSHOT]

    with pytest.raises(ArchiveTooLarge) as raised:
        entries_of(archive, max_archive_bytes=16)

    assert raised.value.measured == "archive"
    assert raised.value.limit_bytes == 16
    assert raised.value.source == archive.name


def test_a_zip_claiming_to_unpack_over_the_ceiling_is_refused(
    snapshot_zips: dict[date, Path],
) -> None:
    """The zip-bomb guard: read from the zip's own directory, before a member is extracted."""
    with pytest.raises(ArchiveTooLarge) as raised:
        entries_of(snapshot_zips[LAST_SNAPSHOT], max_unpacked_bytes=32)

    assert raised.value.measured == "unpacked"


def test_a_refused_archive_yields_no_member_at_all(snapshot_zips: dict[date, Path]) -> None:
    """`read_archive` is a generator, so this checks the refusal happens before the first yield."""
    stream = read_archive(snapshot_zips[LAST_SNAPSHOT], max_archive_bytes=16, max_unpacked_bytes=16)

    with pytest.raises(ArchiveTooLarge):
        next(stream)


def test_an_unpacked_directory_over_the_ceiling_is_refused(
    snapshot_directories: dict[date, Path],
) -> None:
    with pytest.raises(ArchiveTooLarge) as raised:
        entries_of(snapshot_directories[LAST_SNAPSHOT], max_unpacked_bytes=32)

    assert raised.value.measured == "unpacked"


def test_an_archive_inside_both_ceilings_is_read(snapshot_zips: dict[date, Path]) -> None:
    assert members_of(snapshot_zips[LAST_SNAPSHOT])


def test_the_error_names_the_archive_and_no_member_of_it(
    snapshot_zips: dict[date, Path],
) -> None:
    """`docs/policies/caselist-data-use.md`: no disclosure path in an error message."""
    with pytest.raises(ArchiveTooLarge) as raised:
        entries_of(snapshot_zips[LAST_SNAPSHOT], max_archive_bytes=16)

    assert "Maple Grove" not in str(raised.value)
    assert "QX" not in str(raised.value)


# ------------------------------------------------------------------------------------------------
# Junk is skipped with a reason
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("__MACOSX/School/Team/._real.docx", SkipReason.MACOS_METADATA),
        ("School/Team/._real.docx", SkipReason.MACOS_METADATA),
        (".DS_Store", SkipReason.DESKTOP_SERVICES_STORE),
        ("School/Team/.DS_Store", SkipReason.DESKTOP_SERVICES_STORE),
        ("School/Team/~$real.docx", SkipReason.WORD_LOCK_FILE),
    ],
)
def test_every_kind_of_junk_member_is_skipped_with_its_own_reason(
    tmp_path: Path, name: str, reason: SkipReason
) -> None:
    archive = malformed_zip(tmp_path / "junk.zip", {name: b"junk", "School/Team/real.docx": b"y"})

    assert [skip.reason for skip in skips_of(archive)] == [reason]


def test_the_fixture_skips_exactly_what_the_expected_summary_says_it_does(
    snapshot_zips: dict[date, Path], snapshot_directories: dict[date, Path]
) -> None:
    """ac5's count, for both forms of every week.

    The zip form carries one member more than the directory form — the `../` entry a directory
    cannot hold — which is why the fixture states the two separately. `EXPECTED_SNAPSHOTS` is the
    typed form of the committed `expected_summary.json`; the fixture's own test pins the two
    equal, so asserting against either asserts against both.
    """
    for expected in EXPECTED_SNAPSHOTS:
        assert len(skips_of(snapshot_zips[expected.snapshot])) == expected.skipped_zip, expected
        assert len(skips_of(snapshot_directories[expected.snapshot])) == expected.skipped_directory, expected


# ------------------------------------------------------------------------------------------------
# What a caller gets
# ------------------------------------------------------------------------------------------------


def test_members_arrive_in_path_order(snapshot_zips: dict[date, Path]) -> None:
    """Path order, not archive order: it is what makes a re-import reproduce its manifest."""
    entries = entries_of(snapshot_zips[LAST_SNAPSHOT])

    paths = [entry.path for entry in entries]
    assert paths == sorted(paths)


def test_every_member_carries_the_digest_of_the_bytes_that_were_read(
    snapshot_zips: dict[date, Path],
) -> None:
    import hashlib

    for member in members_of(snapshot_zips[LAST_SNAPSHOT]):
        assert member.sha256 == hashlib.sha256(member.data).hexdigest()
        assert member.byte_size == len(member.data)


def test_a_zip_and_the_directory_it_unpacks_to_yield_the_same_members(
    snapshot_zips: dict[date, Path], snapshot_directories: dict[date, Path]
) -> None:
    """The property the manifest depends on: which form the operator used leaves no trace."""
    for snapshot in SNAPSHOTS:
        from_zip = {member.path: member.sha256 for member in members_of(snapshot_zips[snapshot.snapshot])}
        from_directory = {
            member.path: member.sha256 for member in members_of(snapshot_directories[snapshot.snapshot])
        }

        assert from_zip == from_directory, snapshot.archive_name


def test_the_wrapper_directory_is_taken_off_a_zip(snapshot_zips: dict[date, Path]) -> None:
    paths = [member.path for member in members_of(snapshot_zips[LAST_SNAPSHOT])]

    assert not any(path.startswith("testcl26-") for path in paths)
    assert "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx" in paths


# ------------------------------------------------------------------------------------------------
# Which wrapper directory gets stripped, and which does not
# ------------------------------------------------------------------------------------------------


def test_a_directory_named_after_the_archive_is_stripped() -> None:
    paths = ["hsld26-0915/Maple Grove/QX/a.docx", "hsld26-0915/Cedar Hollow/ZaLu/b.docx"]

    assert common_root_to_strip(paths, archive_stem="hsld26-0915") == "hsld26-0915"


def test_a_wrapper_deep_enough_to_spare_is_stripped_even_when_it_is_not_the_stem() -> None:
    """An operator who renamed the download still gets the same paths."""
    paths = ["whatever/Maple Grove/QX/a.docx", "whatever/Cedar Hollow/ZaLu/b.docx"]

    assert common_root_to_strip(paths, archive_stem="renamed") == "whatever"


def test_a_lone_school_is_not_mistaken_for_a_wrapper_directory() -> None:
    """The case worth being careful about: stripping here would delete the school."""
    paths = ["Maple Grove/QX/a.docx", "Maple Grove/ZaLu/b.docx"]

    assert common_root_to_strip(paths, archive_stem="hsld26-0915") is None


def test_nothing_is_stripped_when_the_members_do_not_share_a_root() -> None:
    paths = ["Maple Grove/QX/a.docx", "Cedar Hollow/ZaLu/b.docx"]

    assert common_root_to_strip(paths, archive_stem="hsld26-0915") is None


def test_an_unpacked_directory_never_has_a_root_stripped(tmp_path: Path) -> None:
    """The directory the operator points at is the archive root, one school or fifty."""
    root = tmp_path / "hsld26-0915"
    (root / "Maple Grove" / "QX").mkdir(parents=True)
    (root / "Maple Grove" / "QX" / "Maple Grove-QX-Aff-Cup-Round 1.docx").write_bytes(b"a")

    assert [member.path for member in members_of(root)] == [
        "Maple Grove/QX/Maple Grove-QX-Aff-Cup-Round 1.docx"
    ]


# ------------------------------------------------------------------------------------------------
# The archive's own digest
# ------------------------------------------------------------------------------------------------


def test_a_zip_hashes_to_its_own_bytes(snapshot_zips: dict[date, Path]) -> None:
    import hashlib

    archive = snapshot_zips[LAST_SNAPSHOT]

    assert archive_digest(archive) == hashlib.sha256(archive.read_bytes()).hexdigest()


def test_a_directory_hashes_the_same_way_twice(snapshot_directories: dict[date, Path]) -> None:
    directory = snapshot_directories[LAST_SNAPSHOT]

    assert archive_digest(directory) == archive_digest(directory)


def test_two_different_weeks_hash_differently(snapshot_zips: dict[date, Path]) -> None:
    digests = {archive_digest(path) for path in snapshot_zips.values()}

    assert len(digests) == len(snapshot_zips)


# ------------------------------------------------------------------------------------------------
# Refusals that are not about size
# ------------------------------------------------------------------------------------------------


def test_a_path_that_is_neither_a_zip_nor_a_directory_is_refused(tmp_path: Path) -> None:
    with pytest.raises(UnreadableArchive):
        entries_of(tmp_path / "nothing-here.zip")


def test_a_file_that_is_not_a_zip_is_refused(tmp_path: Path) -> None:
    not_a_zip = tmp_path / "hsld26-0915.zip"
    not_a_zip.write_bytes(b"this is not a zip file")

    with pytest.raises(UnreadableArchive):
        entries_of(not_a_zip)


def test_an_empty_directory_reads_as_no_members(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    assert entries_of(empty) == []
