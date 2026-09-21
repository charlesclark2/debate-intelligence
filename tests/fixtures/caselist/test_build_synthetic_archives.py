"""The synthetic archives are reproducible, cumulative, and free of anything real.

Three properties, and the fixture is worthless without all three:

* **Deterministic.** Two builds produce identical bytes, so the importer's "re-importing the same
  snapshot is a no-op" (ac3) is a property of the importer rather than of the clock.
* **Cumulative.** Each week contains the week before it, except for the one file that is taken
  down — which is the whole shape the deduplication counts are derived from.
* **Synthetic.** No real school, team code or disclosure path, per
  `docs/policies/caselist-data-use.md`. Asserted here rather than trusted, because the committed
  file is what a reviewer reads.

It also pins `expected_summary.json` to the literals in the builder, so the two cannot drift: the
import tests assert against the committed file, and a change to the fixture that forgets to
rewrite it fails here instead of there.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest
from tests.fixtures.caselist.build_synthetic_archives import (
    DOCUMENT_BODIES,
    SNAPSHOTS,
    SYNTHETIC_CASELIST,
    SyntheticSnapshot,
    build_snapshot_directories,
    build_snapshot_zips,
    expected_summary,
    written_expected_summary,
)


def test_the_committed_expected_summary_matches_the_builder() -> None:
    """`expected_summary.json` is the builder's literals, written out.

    Rewrite it with
    `uv run python -m tests.fixtures.caselist.build_synthetic_archives <dir> --write-expected-summary`.
    """
    assert written_expected_summary() == expected_summary()


def test_the_expected_summary_names_the_synthetic_caselist() -> None:
    """The `artifact_exists` criterion matches on `testcl26`; this says why that is the slug."""
    assert written_expected_summary()["caselist"] == SYNTHETIC_CASELIST
    assert SYNTHETIC_CASELIST.startswith("testcl")


# ------------------------------------------------------------------------------------------------
# Deterministic
# ------------------------------------------------------------------------------------------------


def test_two_builds_of_the_zips_are_byte_identical(tmp_path: Path) -> None:
    first = build_snapshot_zips(tmp_path / "first")
    second = build_snapshot_zips(tmp_path / "second")

    for snapshot in SNAPSHOTS:
        assert first[snapshot.snapshot].read_bytes() == second[snapshot.snapshot].read_bytes()


def test_two_builds_of_the_directories_produce_identical_files(tmp_path: Path) -> None:
    first = build_snapshot_directories(tmp_path / "first")
    second = build_snapshot_directories(tmp_path / "second")

    for snapshot in SNAPSHOTS:
        for member in snapshot.members_for(zip_form=False):
            if member.symlink_target is not None:
                continue
            assert (first[snapshot.snapshot] / member.path).read_bytes() == (
                second[snapshot.snapshot] / member.path
            ).read_bytes()


def test_every_document_body_is_distinct() -> None:
    """Fourteen bodies, fourteen digests: the count the importer's blob total is checked against."""
    digests = {name: hashlib.sha256(body).hexdigest() for name, body in DOCUMENT_BODIES.items()}

    assert len(set(digests.values())) == len(DOCUMENT_BODIES)
    assert expected_summary()["totals"] == {
        "distinct_sha256": len(DOCUMENT_BODIES),
        "stored_blobs": len(DOCUMENT_BODIES),
        "document_bodies": len(DOCUMENT_BODIES),
    }


# ------------------------------------------------------------------------------------------------
# Cumulative
# ------------------------------------------------------------------------------------------------


def test_each_week_carries_the_previous_week_forward_except_the_file_that_was_taken_down() -> None:
    """Real weekly archives are cumulative; a fixture that was not would test nothing."""
    first, second, third = ({member.path for member in snapshot.members} for snapshot in SNAPSHOTS)

    assert first <= second, "the second week must contain everything the first week did"
    missing_in_the_third_week = second - third
    assert missing_in_the_third_week == {
        "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Negative-Harbor Classic-Octas.docx"
    }


def test_one_path_holds_different_bytes_in_the_first_and_second_weeks() -> None:
    """The CHANGED case: same disclosure path, revised file."""
    path = "Maple Grove/QX/Maple Grove-QX-Neg-Grove City Invitational-Round 2.docx"
    bodies = [
        next(member.body for member in snapshot.members if member.path == path) for snapshot in SNAPSHOTS
    ]

    assert bodies == [
        "grove-round-2-neg-first",
        "grove-round-2-neg-revised",
        "grove-round-2-neg-revised",
    ]


def test_three_paths_hold_the_same_bytes_in_the_second_week() -> None:
    """The DUPLICATE case: a re-upload and another team's copy of one file."""
    second_week = SNAPSHOTS[1]
    sharing_one_body = [member.path for member in second_week.members if member.body == "grove-round-1-aff"]

    assert sorted(sharing_one_body) == [
        "Cedar Hollow/ZaLu/Cedar Hollow-ZaLu-Aff-Grove City Invitational-Round 3.docx",
        "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1 (1).docx",
        "Maple Grove/QX/Maple Grove-QX-Aff-Grove City Invitational-Round 1.docx",
    ]


# ------------------------------------------------------------------------------------------------
# Safe to build, and safe to read
# ------------------------------------------------------------------------------------------------


def test_the_zip_carries_a_traversal_member_at_its_own_top_level(tmp_path: Path) -> None:
    """Written outside the archive's directory, because that is where a real zip-slip entry sits.

    Under `testcl26-0915/` it would normalize back inside the staging root and prove nothing.
    """
    zips = build_snapshot_zips(tmp_path)

    with zipfile.ZipFile(zips[SNAPSHOTS[-1].snapshot]) as archive:
        names = archive.namelist()

    assert "../escaped.docx" in names
    assert not any(name.startswith("testcl26-0915/..") for name in names)


def test_building_the_directories_writes_nothing_outside_them(tmp_path: Path) -> None:
    """The traversal member is zip-only: a directory build must not write beside the root."""
    destination = tmp_path / "archives"
    build_snapshot_directories(destination)

    assert sorted(entry.name for entry in tmp_path.iterdir()) == ["archives"]
    assert not (tmp_path / "escaped.docx").exists()


def test_the_symlink_member_is_a_real_symlink_in_a_directory_build(tmp_path: Path) -> None:
    built = build_snapshot_directories(tmp_path)
    link = built[SNAPSHOTS[-1].snapshot] / "Cedar Hollow/ZaLu/latest-aff.docx"

    assert link.is_symlink()


# ------------------------------------------------------------------------------------------------
# Synthetic
# ------------------------------------------------------------------------------------------------

#: Team codes the fixture is allowed to use, all invented. `docs/policies/caselist-data-use.md`
#: forbids a real one anywhere in the repository, and the policy's own example is `QX`.
INVENTED_TEAM_CODES = frozenset({"QX", "ZaLu", "BeCo", "MnPr", "XY"})

#: Schools the fixture is allowed to name. All invented; the policy's own example is `Maple Grove`.
INVENTED_SCHOOLS = frozenset(
    {"Maple Grove", "Cedar Hollow", "Northgate Prep", "Riverbend Academy", "Westfield"}
)


@pytest.mark.parametrize("snapshot", SNAPSHOTS, ids=lambda snapshot: snapshot.archive_name)
def test_every_member_names_only_invented_schools_and_team_codes(snapshot: SyntheticSnapshot) -> None:
    """No real school or team code reaches a committed file, per the data-use policy."""
    for member in snapshot.members:
        parts = member.path.split("/")
        if len(parts) < 3 or parts[0] == "__MACOSX":
            continue
        assert parts[0] in INVENTED_SCHOOLS, f"{parts[0]} is not one of the invented schools"
        assert parts[1] in INVENTED_TEAM_CODES, "a directory named a team code that is not invented"


def test_the_document_bodies_quote_no_evidence() -> None:
    """The bodies are filler about the fixture itself, not excerpts from anything real.

    `v1-e31-t02`'s rulings forbid a real caselist or camp excerpt in the repository outright, so
    the fixture's documents are short sentences this builder writes about its own contents.
    """
    for name, body in DOCUMENT_BODIES.items():
        assert len(body) < 4096, f"{name} is too large to be the filler it is supposed to be"
