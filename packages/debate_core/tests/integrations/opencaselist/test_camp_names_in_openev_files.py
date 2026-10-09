"""The camp, read from OpenEv camp files named the way the real ones are (`v1-e30-t08`, ac1).

The v1-e30-t06 backfill imported 105 real camp files and recorded every one as camp `UNKNOWN`: the
importer looked for the camp in the folder or at the start of the filename, and the real files name
it after the title, before the year, with the lab's initials last, in folders named for the kind
of argument. This is the fixture set that would have caught it, one case per naming shape.

**Synthetic, in the real shapes.** The shapes were read from the real files' names in the
operator's store; none of those names, titles or initials is reproduced here
(`docs/policies/caselist-data-use.md`, rule 5). Every title and every set of initials below is
invented. The only real names are camps, and each is an entry of the packaged
`camp_aliases.yaml`; `Zephyr` and `ZQDI` are invented camps that the table does not list.

**Both ways a file arrives.** A camp file downloaded by hand keeps its folder; one the scheduled
sync fetched is saved flat under :func:`openev_inbox_name`, which turns its spaces into
underscores. Both must parse to the same camp. Every expected value is written by hand from the
name in the same row (working agreements §6).
"""

from __future__ import annotations

import pytest

from debate_core.application.caselist.camp_metadata import (
    UNKNOWN_CAMP,
    CampAliases,
    ParsedCampPath,
    load_camp_aliases,
    parse_camp_path,
)
from debate_core.application.ports.caselist_source import OpenEvFile
from debate_core.integrations.opencaselist.openev import openev_inbox_name

PACKAGED_TABLE: CampAliases = load_camp_aliases()

#: (case, path as the operator's download holds it, camp, title). One row per real naming shape.
CAMP_NAME_SHAPES: list[tuple[str, str, str, str]] = [
    (
        "camp at the end, then the year and four initials",
        "Disadvantages/Lantern Shipping DA - Michigan 2026 QRSV.docx",
        "Michigan",
        "Lantern Shipping DA",
    ),
    (
        "camp at the end after a title that starts with a side, three initials",
        "Counterplans/NEG Orchard Grants CP - DDI 2026 JKT.docx",
        "DDI",
        "NEG Orchard Grants CP",
    ),
    (
        "camp at the end after a numbered title",
        "Kritiks/Tidewater Kritik 2 - Michigan 2026 WXYZ.docx",
        "Michigan",
        "Tidewater Kritik 2",
    ),
    (
        "camp at the end with no initials after the year",
        "Topicality/Saltmarsh T - UTNIF 2026.docx",
        "UTNIF",
        "Saltmarsh T",
    ),
    (
        "camp at the end, then a browser's copy marker",
        "Topicality/AB Saltmarsh T - UTNIF 2026 (1).docx",
        "UTNIF",
        "AB Saltmarsh T (1)",
    ),
    (
        "camp at the end, spelled as a listed alias",
        "Affirmatives/Basalt Advantage - Northwestern 2026.docx",
        "NHSI",
        "Basalt Advantage",
    ),
    (
        "camp at the end, spelled in two words",
        "Affirmatives/Ferry Aff - Michigan Classic 2026 PQR.docx",
        "Michigan",
        "Ferry Aff",
    ),
    (
        "camp at the start",
        "GDI - Ferry Politics DA.docx",
        "Gonzaga",
        "Ferry Politics DA",
    ),
    (
        "camp in the folder",
        "2026/Spartan Debate Institute/Seniors Lab/Ferry Politics DA.docx",
        "SDI",
        "Ferry Politics DA",
    ),
    (
        "camp absent: the camp position names a camp the table does not list",
        "Disadvantages/Glacier Tariffs DA - Zephyr 2026.docx",
        UNKNOWN_CAMP,
        "Glacier Tariffs DA - Zephyr 2026",
    ),
    (
        "camp absent: unlisted initials at the camp position",
        "Disadvantages/Reef Neg - ZQDI 2026.docx",
        UNKNOWN_CAMP,
        "Reef Neg - ZQDI 2026",
    ),
    (
        "camp absent: nothing at all names one",
        "Impacts/Glacier Impact Turns.docx",
        UNKNOWN_CAMP,
        "Glacier Impact Turns",
    ),
]


def parse(path: str) -> ParsedCampPath:
    return parse_camp_path(path, aliases=PACKAGED_TABLE)


@pytest.mark.parametrize(
    ("path", "camp", "title"),
    [row[1:] for row in CAMP_NAME_SHAPES],
    ids=[row[0] for row in CAMP_NAME_SHAPES],
)
def test_each_real_naming_shape_gives_its_camp_and_title(path: str, camp: str, title: str) -> None:
    parsed = parse(path)

    assert (parsed.camp, parsed.file_title) == (camp, title)


#: The shapes whose camp is in the filename. The sync saves a file flat, so a camp folder is gone.
FILENAME_SHAPES = [row for row in CAMP_NAME_SHAPES if row[0] != "camp in the folder"]


@pytest.mark.parametrize(
    ("path", "camp"),
    [(row[1], row[2]) for row in FILENAME_SHAPES],
    ids=[row[0] for row in FILENAME_SHAPES],
)
def test_a_camp_file_the_sync_fetched_parses_to_the_same_camp_as_the_one_downloaded_by_hand(
    path: str, camp: str
) -> None:
    filename = path.rsplit("/", 1)[-1]
    fetched = OpenEvFile(openev_id=41, path=f"/2026/somewhere/{filename}", filename=filename)

    parsed = parse(openev_inbox_name(fetched))

    assert parsed.camp == camp


def test_the_sync_inbox_name_keeps_its_underscores_in_the_title_but_loses_the_camp_block() -> None:
    fetched = OpenEvFile(
        openev_id=41, path="/2026/x/y.docx", filename="Lantern Shipping DA - Michigan 2026 QRSV.docx"
    )

    parsed = parse(openev_inbox_name(fetched))

    assert (parsed.camp, parsed.file_title) == ("Michigan", "Lantern_Shipping_DA")


def test_an_absent_camp_is_unknown_with_a_warning_and_never_a_guess() -> None:
    parsed = parse("Disadvantages/Glacier Tariffs DA - Zephyr 2026.docx")

    assert parsed.camp == UNKNOWN_CAMP
    assert parsed.camp_resolved is False
    assert parsed.warnings == (
        "no folder and no word of the filename names a camp in the alias table; camp recorded as UNKNOWN",
    )


def test_a_camp_spelling_inside_a_longer_word_is_not_a_camp() -> None:
    parsed = parse("Affirmatives/Michiganders Aff - Zephyr 2026.docx")

    assert parsed.camp == UNKNOWN_CAMP


def test_two_different_camps_in_one_filename_is_unknown_with_a_warning_naming_both() -> None:
    parsed = parse("Kritiks/Dartmouth Rebuttals - Michigan 2026 ABC.docx")

    assert parsed.camp == UNKNOWN_CAMP
    assert parsed.file_title == "Dartmouth Rebuttals - Michigan 2026 ABC"
    assert parsed.warnings == (
        "the filename names more than one camp in the alias table (DDI, Michigan); camp recorded as UNKNOWN",
    )
