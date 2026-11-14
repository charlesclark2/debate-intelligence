"""No golden-card fixture carries author metadata, and every case is attested (ac4 of `v1-e09-t01`).

The product owner's ruling of 2026-11-14 replaced the roster denylist with the coach's per-card
attestation: the corpus takes only cards the coach cut or re-cut, and the coach reviews each for
names. The denylist is optional and off by default.

* **The committed fixtures.** Every `.docx` under `tests/fixtures/golden_cards/` carries no author,
  last editor, company or manager, no comment or people part, and no tracked-change author but
  `Redacted`, and every case carries the coach's attestation, checked here on every run.
* **The tooling, on invented files.** A team file built in memory hides an invented name in every
  place Word hides one. With no denylist the importer still strips the metadata, comments and
  tracked-change authors, and `check` still fails on a file that keeps them. With an (invented)
  denylist given, the names on it are removed as well. No test here reads `~/Documents/debate` or
  any path outside the repository: every file is built under `tmp_path`.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import import_golden_card as golden  # noqa: E402
from tests.golden.synthetic_team_files import (  # noqa: E402
    FILLER,
    METADATA_AUTHOR,
    METADATA_COMPANY,
    ROSTER_NAME,
    ROSTER_SURNAME,
    TEAM_CODE,
    SyntheticCard,
    coach_attests,
    team_file,
    write_denylist,
)

from debate_core.integrations.docx_file_writer.package_writer import write_package  # noqa: E402
from debate_core.integrations.docx_parser import DebateDocxParser  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "golden_cards"
TEST_KEY = b"a test key that is not the operator's".ljust(32, b".")
IMPORTED_ON = date(2026, 11, 13)

#: Words that would mean a name leaked, checked in every byte of every output part.
LEAKS = (ROSTER_NAME, ROSTER_SURNAME, METADATA_AUTHOR, METADATA_COMPANY)


def _cards(event: str) -> list[SyntheticCard]:
    return [
        SyntheticCard(
            tag=f"{event} demand growth strains the reserve margin",
            short_cite="Okonkwo 26",
            cite_rest=" [Ada Okonkwo, senior analyst, Brookings Institution, 3-4-2026, {link}] //MQ",
            link=f"https://www.brookings.edu/articles/{event.lower()}-grid",
            body=[
                f"Plain words {FILLER} {{warrant}} and more … after the cut.",
                f"A second paragraph {FILLER} {{warrant}}.",
            ],
            tracked_insertion="inserted words ",
            commented=True,
        ),
        SyntheticCard(
            tag=f"{ROSTER_NAME} says the {event} grid holds",
            short_cite="Lindqvist 25",
            cite_rest=" [Lena Lindqvist, Reuters, 5-6-2025, https://www.reuters.com/world/grid] [QZX MQ]",
            body=[f"Only paragraph {FILLER} {{warrant}}."],
        ),
    ]


def _season_folders(root: Path) -> list[Path]:
    layout = (
        ("2025-2026", "Policy Debate", "Policy"),
        ("2024-2025", "LD", "LD"),
        ("2026-2027", "Public Forum", "PF"),
    )
    for season, folder, event in layout:
        target = root / season / folder
        target.mkdir(parents=True)
        (target / "team file.docx").write_bytes(team_file(_cards(event), heading=f"{event} block"))
    return [root / season for season, _, _ in layout]


@pytest.fixture
def imported(tmp_path: Path) -> tuple[Path, Path]:
    """Every candidate of an invented three-season tree, imported into a fixtures folder under tmp."""
    denylist = write_denylist(tmp_path / "outside the repo" / "denylist.txt")
    listing = golden.list_candidates(_season_folders(tmp_path / "debate"), (), TEST_KEY)
    shortlist = golden.choose_shortlist(listing.candidates)
    assert len(shortlist) == 6
    fixtures = tmp_path / "golden_cards"
    cases, refused = golden.import_candidates(
        shortlist,
        [candidate.candidate_id for candidate in shortlist],
        golden.load_denylist(denylist),
        fixtures,
        today=IMPORTED_ON,
        attest=coach_attests,
    )
    assert refused == []
    assert len(cases) == 6
    return fixtures, denylist


def _all_bytes(package: Path) -> bytes:
    with zipfile.ZipFile(package) as archive:
        return b"".join(archive.read(name) + name.encode() for name in archive.namelist())


# ------------------------------------------------------------------------------------------------
# The committed fixtures
# ------------------------------------------------------------------------------------------------


def test_every_committed_fixture_docx_carries_no_author_metadata() -> None:
    packages = sorted(FIXTURES.rglob("*.docx"))
    cases = sorted(FIXTURES.glob(f"*/{golden.CASE_NAME}"))

    # Not vacuous by accident: every case has its excerpt, and no excerpt is outside a case. Until
    # the coach's picks are imported both lists are empty, and the index says "0 cases".
    assert [path.parent for path in packages] == [path.parent for path in cases]
    assert [(path.parent.name, golden.metadata_problems(path.read_bytes())) for path in packages] == [
        (path.parent.name, []) for path in packages
    ]


def test_the_committed_index_is_what_the_importer_writes() -> None:
    assert (FIXTURES / golden.INDEX_NAME).read_text(encoding="utf-8") == golden.render_index(FIXTURES)


def test_every_committed_case_carries_the_coachs_attestation() -> None:
    cases = sorted(FIXTURES.glob(f"*/{golden.CASE_NAME}"))
    assert sorted(path.parent for path in cases) == sorted(
        path for path in FIXTURES.iterdir() if path.is_dir()
    )
    assert [
        path.parent.name
        for path in cases
        if json.loads(path.read_text(encoding="utf-8")).get("coach_cut_and_reviewed_for_names") is not True
    ] == []


# ------------------------------------------------------------------------------------------------
# The importer, on invented files
# ------------------------------------------------------------------------------------------------


def test_imported_excerpts_carry_no_author_metadata(imported: tuple[Path, Path]) -> None:
    fixtures, _ = imported
    packages = sorted(fixtures.glob(f"*/{golden.EXCERPT_NAME}"))

    assert len(packages) == 6
    for package in packages:
        assert golden.metadata_problems(package.read_bytes()) == []
        content = _all_bytes(package)
        assert METADATA_AUTHOR.encode() not in content
        assert METADATA_COMPANY.encode() not in content


def test_no_roster_name_survives_the_import(imported: tuple[Path, Path]) -> None:
    fixtures, denylist = imported

    report = golden.check_fixtures(fixtures, golden.load_denylist(denylist))

    assert report.docx_checked == 6
    assert report.denylist_hits == []
    for path in sorted(fixtures.rglob("*")):
        if path.is_file():
            content = _all_bytes(path) if path.suffix == ".docx" else path.read_bytes()
            assert ROSTER_SURNAME.encode() not in content, path.name
            assert TEAM_CODE.encode() not in content, path.name


def test_a_tracked_change_keeps_its_text_and_loses_its_author(imported: tuple[Path, Path]) -> None:
    fixtures, _ = imported
    (case,) = [
        path.parent
        for path in fixtures.glob("policy-*/case.json")
        if json.loads(path.read_text(encoding="utf-8"))["source_type"] == "think tank"
    ]
    with zipfile.ZipFile(case / golden.EXCERPT_NAME) as archive:
        document = archive.read("word/document.xml").decode("utf-8")

    assert "inserted words" in document
    assert f'w:author="{golden.REDACTED}"' in document
    assert "w:date=" not in document


def test_the_research_need_is_the_tag_with_the_roster_name_removed(imported: tuple[Path, Path]) -> None:
    fixtures, _ = imported
    needs = sorted(
        json.loads(path.read_text(encoding="utf-8"))["research_need"] for path in fixtures.glob("*/case.json")
    )

    assert needs == sorted(
        [f"{event} demand growth strains the reserve margin" for event in ("Policy", "LD", "PF")]
        + [f"{golden.REDACTED} says the {event} grid holds" for event in ("Policy", "LD", "PF")]
    )


# ------------------------------------------------------------------------------------------------
# The checker
# ------------------------------------------------------------------------------------------------


def test_the_checker_flags_a_team_file_that_was_never_scrubbed(tmp_path: Path) -> None:
    fixtures = tmp_path / "golden_cards"
    (fixtures / "policy-001").mkdir(parents=True)
    (fixtures / "policy-001" / golden.EXCERPT_NAME).write_bytes(team_file(_cards("Policy")))
    denylist = golden.load_denylist(write_denylist(tmp_path / "outside" / "denylist.txt"))

    report = golden.check_fixtures(fixtures, denylist)

    assert sorted(problem for _, problem in report.metadata_problems) == [
        "docProps/app.xml Company is set",
        "docProps/core.xml creator is set",
        "docProps/core.xml lastModifiedBy is set",
        "word/comments.xml carries an author name",
        "word/comments.xml carries initials",
        "word/comments.xml is present",
        "word/document.xml carries an author name",
        "word/people.xml carries an author name",
        "word/people.xml is present",
    ]
    assert [path for path, _ in report.denylist_hits] == ["policy-001/team-card.docx"]
    assert not report.clean


def test_the_checker_finds_a_roster_name_in_a_text_file(tmp_path: Path) -> None:
    fixtures = tmp_path / "golden_cards"
    (fixtures / "ld-001").mkdir(parents=True)
    (fixtures / "ld-001" / "case.json").write_text(
        json.dumps({"research_need": f"{ROSTER_NAME} wins"}), encoding="utf-8"
    )
    denylist = golden.load_denylist(write_denylist(tmp_path / "outside" / "denylist.txt"))

    report = golden.check_fixtures(fixtures, denylist)

    assert report.denylist_hits == [("ld-001/case.json", 2)]


def test_check_prints_where_a_name_is_and_never_the_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = tmp_path / "golden_cards"
    (fixtures / "pf-001").mkdir(parents=True)
    (fixtures / "pf-001" / golden.EXCERPT_NAME).write_bytes(team_file(_cards("PF")))
    denylist = write_denylist(tmp_path / "outside" / "denylist.txt")

    status = golden.main(["check", "--denylist", str(denylist), "--fixtures", str(fixtures)])

    printed = capsys.readouterr()
    assert status == 1
    assert "pf-001/team-card.docx" in printed.out
    assert "NOT CLEAN" in printed.out
    for leak in (*LEAKS, TEAM_CODE):
        assert leak not in printed.out + printed.err


# ------------------------------------------------------------------------------------------------
# The denylist is optional, off by default (product owner's ruling, 2026-11-14)
# ------------------------------------------------------------------------------------------------


def test_import_and_check_run_without_a_denylist_and_still_strip_the_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_denylist_is_read(path: Path) -> object:
        raise AssertionError(f"a denylist was read with none given: {path}")

    monkeypatch.setattr(golden, "load_denylist", no_denylist_is_read)
    listing = golden.list_candidates(_season_folders(tmp_path / "debate"), (), TEST_KEY)
    shortlist_dir = tmp_path / "shortlist"
    golden.write_shortlist(shortlist_dir, listing.candidates)
    fixtures = tmp_path / "golden_cards"
    ids = [candidate.candidate_id for candidate in listing.candidates]

    imported = golden.main(
        ["import", "--shortlist", str(shortlist_dir), "--fixtures", str(fixtures), "--ids", *ids],
        today=IMPORTED_ON,
        attest=coach_attests,
    )
    checked = golden.main(["check", "--fixtures", str(fixtures)])

    printed = capsys.readouterr().out.splitlines()
    assert (imported, checked) == (0, 0)
    assert "imported 6, refused 0" in printed
    assert printed[-3:] == ["docx checked: 6, other files checked: 7", "denylist: off", "clean"]
    packages = sorted(fixtures.glob(f"*/{golden.EXCERPT_NAME}"))
    assert len(packages) == 6
    assert [golden.metadata_problems(path.read_bytes()) for path in packages] == [[]] * 6
    for path in packages:
        everything = _all_bytes(path)
        assert METADATA_AUTHOR.encode() not in everything
        assert METADATA_COMPANY.encode() not in everything


def test_check_without_a_denylist_still_fails_on_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = tmp_path / "golden_cards"
    (fixtures / "policy-001").mkdir(parents=True)
    (fixtures / "policy-001" / golden.EXCERPT_NAME).write_bytes(team_file(_cards("Policy")))

    status = golden.main(["check", "--fixtures", str(fixtures)])

    printed = capsys.readouterr().out
    assert status == 1
    assert "metadata: policy-001/team-card.docx: docProps/core.xml creator is set" in printed
    assert "denylist: off" in printed
    assert printed.splitlines()[-1] == "NOT CLEAN"


@pytest.mark.parametrize("command", ["check", "import"])
def test_a_denylist_named_but_missing_is_an_error(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "outside" / "no-denylist.txt"
    arguments = ["--denylist", str(missing), "--fixtures", str(tmp_path / "golden_cards")]
    if command == "import":
        arguments += ["--shortlist", str(tmp_path / "shortlist"), "--ids", "policy-0000000000"]

    status = golden.main([command, *arguments])

    assert status == 2
    assert "no denylist" in capsys.readouterr().err
    assert not (tmp_path / "golden_cards").exists()


def test_an_empty_denylist_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "outside" / "denylist.txt"
    empty.parent.mkdir()
    empty.write_text("\n  \n", encoding="utf-8")

    with pytest.raises(golden.DenylistError, match="lists nothing"):
        golden.load_denylist(empty)


def test_a_denylist_inside_the_repository_is_refused() -> None:
    with pytest.raises(golden.DenylistError, match="outside the repository"):
        golden.load_denylist(REPO_ROOT / "tests" / "golden" / "denylist.txt")


def test_a_card_whose_body_names_someone_on_the_roster_is_refused(tmp_path: Path) -> None:
    card = SyntheticCard(
        tag="The grid holds",
        short_cite="Okonkwo 26",
        cite_rest=" [Okonkwo, Reuters, https://www.reuters.com/grid]",
        body=[f"Plain words {FILLER} as {ROSTER_NAME} put it {{warrant}}."],
    )
    folder = tmp_path / "debate" / "2025-2026" / "LD"
    folder.mkdir(parents=True)
    (folder / "file.docx").write_bytes(team_file([card]))
    listing = golden.list_candidates([tmp_path / "debate" / "2025-2026"], (), TEST_KEY)
    denylist = golden.load_denylist(write_denylist(tmp_path / "outside" / "denylist.txt"))

    cases, refused = golden.import_candidates(
        listing.candidates,
        [listing.candidates[0].candidate_id],
        denylist,
        tmp_path / "golden",
        today=IMPORTED_ON,
        attest=coach_attests,
    )

    assert cases == []
    assert [refusal.reason for refusal in refused] == [golden.REFUSED_DENYLIST_IN_BODY]
    assert not list((tmp_path / "golden").glob("*/team-card.docx"))


def test_every_imported_cite_has_lost_its_cutter_mark(imported: tuple[Path, Path]) -> None:
    fixtures, _ = imported
    cites = []
    for package in sorted(fixtures.glob(f"*/{golden.EXCERPT_NAME}")):
        document = golden._parse(DebateDocxParser(), package.read_bytes())  # noqa: SLF001
        assert document is not None
        (card,) = document.cards
        cites.append(card.full_cite)

    # The cutter's initials were MQ behind `//`, and MQ beside the team code in a bracket.
    assert len(cites) == 6
    assert [cite for cite in cites if "MQ" in cite] == []
    assert sorted({cite.rsplit("]", 1)[1] for cite in cites}) == [""]


def test_an_excerpt_that_does_not_reread_as_the_card_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    building = golden.build_excerpt

    def without_the_underline(*arguments: Any, **keywords: Any) -> Any:
        excerpt = building(*arguments, **keywords)
        source = zipfile.ZipFile(BytesIO(excerpt.content))
        parts = [
            (name, source.read(name).replace(b'w:val="StyleUnderline"', b'w:val="Normal"'))
            for name in source.namelist()
        ]
        return dataclasses.replace(excerpt, content=write_package(parts))

    monkeypatch.setattr(golden, "build_excerpt", without_the_underline)
    listing = golden.list_candidates(_season_folders(tmp_path / "debate"), (), TEST_KEY)
    denylist = golden.load_denylist(write_denylist(tmp_path / "outside" / "denylist.txt"))

    cases, refused = golden.import_candidates(
        listing.candidates,
        [listing.candidates[0].candidate_id],
        denylist,
        tmp_path / "golden",
        today=IMPORTED_ON,
        attest=coach_attests,
    )

    assert cases == []
    assert [refusal.reason for refusal in refused] == [golden.REFUSED_REREAD_DIFFERS]
    assert not list((tmp_path / "golden").glob("*/team-card.docx"))
