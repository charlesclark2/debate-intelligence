"""Which other files sit at a removed file's path, and which of them came later (`v1-e30-t11`).

:func:`~debate_core.application.caselist.removal_path_versions.other_versions` is a function of
the manifest rows it is given, so every case here is a handful of rows written out in the test and
an answer written beside them. None of the answers was read back from a run.

The first test is the whole fixture of `tests/fixtures/caselist/build_revised_path_archives.py`,
whose docstring works the same answer out in a table; the rest are one rule each.
"""

from __future__ import annotations

from tests.fixtures.caselist.build_revised_path_archives import (
    COMPLETE_ARCHIVES,
    EXPECTED,
    REVISED_PATH,
    WEEKLY_WINDOWS,
    digest_of,
)

from debate_core.application.caselist.removal_path_versions import (
    PathHolding,
    PathVersion,
    SamePathEvidence,
    VersionRelation,
    other_versions,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
PATH = "Alder Point/KR/Alder Point-KR-Aff-Lakeshore Open-Round 2.docx"
OTHER_PATH = "Alder Point/KR/Alder Point-KR-Neg-Lakeshore Open-Round 5.docx"
RELEASE = "2026-policy"


def held(snapshot: str, sha256: str, *, path: str = PATH, caselist: str = "testcl26") -> PathHolding:
    return PathHolding(caselist=caselist, snapshot=snapshot, path=path, sha256=sha256)


def camp_row(name: str, sha256: str, *, release: str = RELEASE) -> PathHolding:
    return PathHolding(caselist="openev", snapshot=release, path=name, sha256=sha256)


def versions_of_a(
    rows: list[PathHolding], *, upstream_path_digests: dict[int, str] | None = None
) -> dict[str, tuple[VersionRelation, tuple[str, ...]]]:
    """What removing `A` from every path it is held at finds: `{sha256: (relation, snapshots)}`."""
    found = other_versions(rows, {A: None}, named={A}, upstream_path_digests=upstream_path_digests or {})
    return {one.sha256: (one.relation, one.snapshots) for one in found}


def fixture_rows() -> list[PathHolding]:
    return [
        held(snapshot, digest_of(body), path=path, caselist=caselist)
        for prefix, archives in (("", WEEKLY_WINDOWS), ("full/", COMPLETE_ARCHIVES))
        for (caselist, day), members in archives.items()
        for path, body in members.items()
        for snapshot in [f"{prefix}{day.isoformat()}"]
    ]


# ------------------------------------------------------------------------------------------------
# The fixture's table
# ------------------------------------------------------------------------------------------------


def test_the_fixtures_later_uploads_and_earlier_versions_are_the_ones_its_table_gives() -> None:
    named = digest_of(EXPECTED.named)

    found = other_versions(fixture_rows(), {named: None}, named={named}, upstream_path_digests={})

    later = {one.sha256: list(one.snapshots) for one in found if one.relation is VersionRelation.LATER}
    earlier = {one.sha256: list(one.snapshots) for one in found if one.relation is VersionRelation.EARLIER}
    assert later == {digest_of(body): snapshots for body, snapshots in EXPECTED.later_uploads.items()}
    assert earlier == {digest_of(body): snapshots for body, snapshots in EXPECTED.earlier_versions.items()}
    assert len(found) == 4, "nothing of the same date, and nothing from another path or caselist"
    assert {(one.caselist, one.path, one.of_sha256) for one in found} == {("testcl26", REVISED_PATH, named)}
    assert {one.evidence for one in found} == {SamePathEvidence.CASELIST_PATH}


# ------------------------------------------------------------------------------------------------
# What "later" means
# ------------------------------------------------------------------------------------------------


def test_a_file_in_a_snapshot_dated_after_the_named_files_earliest_is_later() -> None:
    rows = [held("2026-09-08", A), held("2026-09-15", B)]

    assert versions_of_a(rows) == {B: (VersionRelation.LATER, ("2026-09-15",))}


def test_a_file_only_in_snapshots_dated_before_it_is_an_earlier_version() -> None:
    rows = [held("2026-09-01", B), held("2026-09-08", A), held("2026-09-15", A)]

    assert versions_of_a(rows) == {B: (VersionRelation.EARLIER, ("2026-09-01",))}


def test_it_is_the_named_files_earliest_snapshot_that_counts_so_a_revert_still_makes_it_later() -> None:
    """`A`, then `B`, then `A` again: `B` is before `A`'s latest snapshot and after its earliest."""
    rows = [held("2026-09-08", A), held("2026-09-15", B), held("2026-09-22", A)]

    assert versions_of_a(rows) == {B: (VersionRelation.LATER, ("2026-09-15",))}


def test_a_file_held_both_before_and_after_is_later() -> None:
    rows = [held("2026-09-01", B), held("2026-09-08", A), held("2026-09-15", B)]

    assert versions_of_a(rows) == {B: (VersionRelation.LATER, ("2026-09-01", "2026-09-15"))}


def test_a_complete_archive_is_ordered_by_its_date_not_by_its_name() -> None:
    """As strings `full/2026-09-05` sorts after `2026-09-08`, and `full/2026-09-12` after `2026-09-15`."""
    rows = [
        held("full/2026-09-05", B),
        held("2026-09-08", A),
        held("full/2026-09-12", C),
        held("2026-09-15", D),
    ]

    assert versions_of_a(rows) == {
        B: (VersionRelation.EARLIER, ("full/2026-09-05",)),
        C: (VersionRelation.LATER, ("full/2026-09-12",)),
        D: (VersionRelation.LATER, ("2026-09-15",)),
    }


def test_a_file_in_another_snapshot_of_the_same_date_is_neither_later_nor_earlier() -> None:
    """A weekly and the complete archive of one day that disagree: the dates cannot say which came first."""
    rows = [
        held("2026-09-08", A),
        held("full/2026-09-08", B),
        held("2026-09-01", C),
        held("full/2026-09-08", C),
    ]

    assert versions_of_a(rows) == {
        B: (VersionRelation.SAME_DATE, ("full/2026-09-08",)),
        C: (VersionRelation.SAME_DATE, ("2026-09-01", "full/2026-09-08")),
    }


def test_the_same_row_read_from_this_machine_and_from_the_bucket_is_one_holding() -> None:
    rows = [held("2026-09-08", A), held("2026-09-15", B), held("2026-09-15", B), held("2026-09-08", A)]

    assert versions_of_a(rows) == {B: (VersionRelation.LATER, ("2026-09-15",))}


def test_a_row_whose_snapshot_is_not_a_date_is_left_out() -> None:
    """The planner never builds one: a manifest's key is checked before it is read."""
    rows = [held("2026-09-08", A), held("not-a-snapshot", B), held("full/2026-13-45", C)]

    assert versions_of_a(rows) == {}


# ------------------------------------------------------------------------------------------------
# What "the same path" means
# ------------------------------------------------------------------------------------------------


def test_a_path_is_a_caselist_and_a_path_so_the_same_spelling_elsewhere_is_another_path() -> None:
    rows = [held("2026-09-08", A), held("2026-09-15", B, caselist="testclb26")]

    assert versions_of_a(rows) == {}


def test_a_file_at_another_path_of_the_same_caselist_is_not_a_version() -> None:
    rows = [held("2026-09-08", A), held("2026-09-15", B, path=OTHER_PATH)]

    assert versions_of_a(rows) == {}


def test_a_file_is_reported_once_for_each_removed_path_it_is_at() -> None:
    rows = [
        held("2026-09-08", A),
        held("2026-09-08", A, path=OTHER_PATH),
        held("2026-09-15", B),
        held("2026-09-01", B, path=OTHER_PATH),
    ]

    found = other_versions(rows, {A: None}, named={A}, upstream_path_digests={})

    assert [(one.sha256, one.path, one.relation) for one in found] == [
        (B, PATH, VersionRelation.LATER),
        (B, OTHER_PATH, VersionRelation.EARLIER),
    ]


def test_a_withdrawal_is_asked_only_about_the_paths_it_takes_the_file_from() -> None:
    """`A` is withdrawn from `PATH` alone, so what came later at `OTHER_PATH` is nothing to it."""
    rows = [
        held("2026-09-08", A),
        held("2026-09-08", A, path=OTHER_PATH),
        held("2026-09-15", B),
        held("2026-09-15", C, path=OTHER_PATH),
    ]

    found = other_versions(rows, {A: frozenset({("testcl26", PATH)})}, named={A}, upstream_path_digests={})

    assert [(one.sha256, one.path) for one in found] == [(B, PATH)]


def test_a_file_the_selector_names_is_never_a_version_of_another_named_file() -> None:
    rows = [held("2026-09-08", A), held("2026-09-15", B), held("2026-09-22", C)]

    found = other_versions(rows, {A: None, B: None}, named={A, B}, upstream_path_digests={})

    assert [(one.sha256, one.relation) for one in found] == [(C, VersionRelation.LATER)]


def test_a_file_the_removal_leaves_alone_has_no_later_uploads() -> None:
    """A shared file named by `--source` without `--include-shared` is taken from nowhere."""
    rows = [held("2026-09-08", A), held("2026-09-15", B)]

    assert other_versions(rows, {}, named={A}, upstream_path_digests={}) == ()


# ------------------------------------------------------------------------------------------------
# A camp file: the revision identity v1-e34-t08 uses
# ------------------------------------------------------------------------------------------------

OLD_ROW = "openev-512-TSF-Estuary_Solvency_Advocate.docx"
NEW_ROW = "openev-640-TSF-Estuary_Solvency_Advocate.docx"
OLDEST_ROW = "openev-400-TSF-Estuary_Solvency_Advocate.docx"


def camp_versions_of_a(
    rows: list[PathHolding], *, upstream_path_digests: dict[int, str] | None = None
) -> list[tuple[str, VersionRelation, tuple[int, ...], SamePathEvidence]]:
    found: tuple[PathVersion, ...] = other_versions(
        rows, {A: None}, named={A}, upstream_path_digests=upstream_path_digests or {}
    )
    return [(one.sha256, one.relation, one.openev_ids, one.evidence) for one in found]


def test_a_higher_openev_id_at_the_same_camp_path_is_a_later_upload_and_a_lower_one_earlier() -> None:
    rows = [camp_row(OLD_ROW, A), camp_row(NEW_ROW, B), camp_row(OLDEST_ROW, C)]

    assert sorted(camp_versions_of_a(rows)) == [
        (B, VersionRelation.LATER, (640,), SamePathEvidence.ROW_NAME),
        (C, VersionRelation.EARLIER, (400,), SamePathEvidence.ROW_NAME),
    ]


def test_camp_paths_are_compared_as_names_as_the_sync_compares_them() -> None:
    """Case, spacing and punctuation aside: how `v1-e34-t08` matches a revision to its old row."""
    rows = [camp_row(OLD_ROW, A), camp_row("openev-640-tsf-estuary solvency-advocate.docx", B)]

    assert camp_versions_of_a(rows) == [(B, VersionRelation.LATER, (640,), SamePathEvidence.ROW_NAME)]


def test_a_camp_row_that_names_no_openev_id_is_not_a_later_upload_and_has_none() -> None:
    """A hand import cannot say which upload it was, in either direction."""
    hand_import = "Tamarack/TSF-Estuary Solvency Advocate.docx"

    assert camp_versions_of_a([camp_row(OLD_ROW, A), camp_row(hand_import, B)]) == []
    assert camp_versions_of_a([camp_row(hand_import, A), camp_row(NEW_ROW, B)]) == []


def test_another_camp_file_and_another_release_are_other_camp_paths() -> None:
    rows = [
        camp_row(OLD_ROW, A),
        camp_row("openev-640-TSF-Canal_Counterplan.docx", B),
        camp_row(NEW_ROW, C, release="2026-ld"),
    ]

    assert camp_versions_of_a(rows) == []


def test_the_delivery_record_tells_two_camps_files_of_one_name_apart() -> None:
    """A release's rows do not keep the camp's folder. Where the record knows both ids, it decides."""
    rows = [
        camp_row(OLD_ROW, A),
        camp_row(NEW_ROW, B),
        camp_row("openev-700-TSF-Estuary_Solvency_Advocate.docx", C),
    ]
    one_path, another = "1" * 64, "2" * 64

    assert camp_versions_of_a(rows, upstream_path_digests={512: one_path, 640: one_path, 700: another}) == [
        (B, VersionRelation.LATER, (640,), SamePathEvidence.UPSTREAM_PATH_DIGEST)
    ]


def test_without_the_delivery_record_the_rows_names_are_all_there_is_and_the_match_says_so() -> None:
    """A machine that never pulled, such as prod: both are matched, and marked as matched by name."""
    rows = [
        camp_row(OLD_ROW, A),
        camp_row(NEW_ROW, B),
        camp_row("openev-700-TSF-Estuary_Solvency_Advocate.docx", C),
    ]

    assert sorted(camp_versions_of_a(rows)) == [
        (B, VersionRelation.LATER, (640,), SamePathEvidence.ROW_NAME),
        (C, VersionRelation.LATER, (700,), SamePathEvidence.ROW_NAME),
    ]
    assert sorted(camp_versions_of_a(rows, upstream_path_digests={512: "1" * 64, 640: "1" * 64})) == [
        (B, VersionRelation.LATER, (640,), SamePathEvidence.UPSTREAM_PATH_DIGEST),
        (C, VersionRelation.LATER, (700,), SamePathEvidence.ROW_NAME),
    ]
    assert sorted(camp_versions_of_a(rows, upstream_path_digests={640: "1" * 64, 700: "2" * 64})) == [
        (B, VersionRelation.LATER, (640,), SamePathEvidence.ROW_NAME),
        (C, VersionRelation.LATER, (700,), SamePathEvidence.ROW_NAME),
    ]
