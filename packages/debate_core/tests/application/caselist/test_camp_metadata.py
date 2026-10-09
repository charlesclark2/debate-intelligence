"""Reading a camp, a lab and a file title out of an OpenEv path.

Every expected value below is written by hand from the path in the same test. The camps are
invented (`Quillfeather`, `Tamarack`, `Brightwater`) and so are the file names; the only real camp
names in this file are the entries of the packaged table, checked as entries and nothing else.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.application.caselist.camp_metadata import (
    UNKNOWN_CAMP,
    CampAliases,
    InvalidCampAliases,
    ParsedCampPath,
    load_camp_aliases,
    parse_camp_path,
)
from debate_core.application.settings import ConfigurationError
from debate_core.domain.caselist import SourceFormat

INVENTED_CAMPS = CampAliases.from_document(
    {
        "camps": {
            "QDI": ["Quillfeather", "Quillfeather Debate Institute"],
            "TSF": ["Tamarack", "Tamarack Summer Forum"],
            "BWW": ["Brightwater", "Brightwater Workshop"],
        }
    },
    source="test table",
)


def parse(path: str) -> ParsedCampPath:
    return parse_camp_path(path, aliases=INVENTED_CAMPS)


# ------------------------------------------------------------------------------------------------
# Where the camp comes from
# ------------------------------------------------------------------------------------------------


def test_a_camp_folder_gives_the_camp_and_the_folder_below_it_gives_the_lab() -> None:
    parsed = parse("Quillfeather/Juniors Lab/Lighthouse Politics DA.docx")

    assert parsed.camp == "QDI"
    assert parsed.lab == "Juniors Lab"
    assert parsed.file_title == "Lighthouse Politics DA"
    assert parsed.source_format is SourceFormat.DOCX
    assert parsed.warnings == ()


def test_a_file_directly_in_a_camp_folder_has_no_lab() -> None:
    parsed = parse("Tamarack/Canal Subsidies Counterplan.docx")

    assert (parsed.camp, parsed.lab, parsed.file_title) == ("TSF", None, "Canal Subsidies Counterplan")


def test_the_outermost_camp_folder_wins_and_folders_above_it_are_ignored() -> None:
    parsed = parse("2026/Tamarack/Seniors/Spillway Advantage.docx")

    assert (parsed.camp, parsed.lab, parsed.file_title) == ("TSF", "Seniors", "Spillway Advantage")


def test_a_filename_prefix_gives_the_camp_and_is_taken_off_the_title() -> None:
    parsed = parse("TSF-Canal Subsidies Counterplan.docx")

    assert (parsed.camp, parsed.lab, parsed.file_title) == ("TSF", None, "Canal Subsidies Counterplan")
    assert parsed.warnings == ()


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("QDI - Harbor Tariffs Aff.docx", "Harbor Tariffs Aff"),
        ("QDI_Harbor Tariffs Aff.docx", "Harbor Tariffs Aff"),
        ("qdi.Harbor Tariffs Aff.docx", "Harbor Tariffs Aff"),
        ("QDI – Harbor Tariffs Aff.docx", "Harbor Tariffs Aff"),
        ("QDI 2026 Harbor Tariffs Aff.docx", "Harbor Tariffs Aff"),
    ],
)
def test_any_separator_after_the_prefix_is_taken_off_and_nothing_else(path: str, title: str) -> None:
    """The year directly after the camp is part of the camp block (`v1-e30-t08`), so it goes too."""
    parsed = parse(path)

    assert (parsed.camp, parsed.file_title) == ("QDI", title)


def test_the_longest_spelling_is_matched_first() -> None:
    parsed = parse("Brightwater Workshop - Orchard Kritik.docx")

    assert (parsed.camp, parsed.file_title) == ("BWW", "Orchard Kritik")


def test_a_spelling_matches_whole_words_only() -> None:
    parsed = parse("QDIX Harbor Tariffs Aff.docx")

    assert parsed.camp == UNKNOWN_CAMP
    assert parsed.file_title == "QDIX Harbor Tariffs Aff"


def test_matching_ignores_case_and_how_the_words_are_separated() -> None:
    assert parse("quillfeather-debate_institute/Tidewater Impact Turns.docx").camp == "QDI"


def test_a_prefix_in_a_camp_folder_is_taken_off_the_title_without_a_warning() -> None:
    parsed = parse("Quillfeather/Juniors Lab/QDI - Harbor Tariffs Neg.docx")

    assert (parsed.camp, parsed.lab, parsed.file_title) == ("QDI", "Juniors Lab", "Harbor Tariffs Neg")
    assert parsed.warnings == ()


def test_when_the_folder_and_the_prefix_disagree_the_folder_is_recorded_with_a_warning() -> None:
    parsed = parse("Brightwater/QDI-Tidewater Impact Turns.docx")

    assert (parsed.camp, parsed.file_title) == ("BWW", "Tidewater Impact Turns")
    assert parsed.warnings == (
        "the filename names camp QDI but the folder names BWW; the folder's camp is recorded",
    )


# ------------------------------------------------------------------------------------------------
# v1-e30-t08: the camp anywhere in the filename, by whole word, and only one of them
# ------------------------------------------------------------------------------------------------


def test_a_camp_at_the_end_of_the_filename_is_found() -> None:
    parsed = parse("Kritiks/Orchard Kritik - TSF 2026 MNO.docx")

    assert (parsed.camp, parsed.lab, parsed.file_title) == ("TSF", None, "Orchard Kritik")
    assert parsed.warnings == ()


def test_a_camp_in_the_middle_of_the_filename_is_found() -> None:
    parsed = parse("Orchard Kritik Tamarack Neg Blocks.docx")

    assert (parsed.camp, parsed.file_title) == ("TSF", "Orchard Kritik Neg Blocks")


def test_a_multi_word_spelling_at_the_end_is_one_match() -> None:
    parsed = parse("Orchard Kritik - Brightwater Workshop 2026 MN.docx")

    assert (parsed.camp, parsed.file_title, parsed.warnings) == ("BWW", "Orchard Kritik", ())


@pytest.mark.parametrize(
    "path",
    [
        "Orchard Kritik - QDIX 2026.docx",
        "Orchard Kritik - XQDI 2026.docx",
        "Quillfeathers Orchard Kritik.docx",
        "Orchard Kritik - TamarackSummer 2026.docx",
    ],
)
def test_a_spelling_inside_a_longer_word_is_never_a_camp(path: str) -> None:
    parsed = parse(path)

    assert parsed.camp == UNKNOWN_CAMP
    assert parsed.file_title == path.removesuffix(".docx")


def test_two_different_camps_in_the_filename_are_unknown_with_a_warning_never_a_guess() -> None:
    parsed = parse("Tamarack Rebuttals - QDI 2026 MNO.docx")

    assert parsed.camp == UNKNOWN_CAMP
    assert parsed.file_title == "Tamarack Rebuttals - QDI 2026 MNO"
    assert parsed.warnings == (
        "the filename names more than one camp in the alias table (QDI, TSF); camp recorded as UNKNOWN",
    )


def test_two_spellings_of_one_camp_are_that_camp_and_the_one_before_the_year_comes_off() -> None:
    parsed = parse("Quillfeather Rebuttals - QDI 2026 MNO.docx")

    assert (parsed.camp, parsed.file_title, parsed.warnings) == ("QDI", "Quillfeather Rebuttals", ())


def test_a_camp_folder_wins_over_a_different_camp_at_the_end_of_the_filename() -> None:
    parsed = parse("Brightwater/Orchard Kritik - TSF 2026 MNO.docx")

    assert (parsed.camp, parsed.file_title) == ("BWW", "Orchard Kritik")
    assert parsed.warnings == (
        "the filename names camp TSF but the folder names BWW; the folder's camp is recorded",
    )


def test_a_camp_folder_wins_over_a_filename_naming_two_other_camps_and_keeps_the_stem() -> None:
    parsed = parse("Brightwater/Tamarack Rebuttals - QDI 2026.docx")

    assert (parsed.camp, parsed.file_title) == ("BWW", "Tamarack Rebuttals - QDI 2026")
    assert parsed.warnings == (
        "the filename names camp QDI, TSF but the folder names BWW; the folder's camp is recorded",
    )


def test_two_folders_naming_different_camps_are_unknown_with_a_warning() -> None:
    parsed = parse("Tamarack/Brightwater/Orchard Kritik.docx")

    assert (parsed.camp, parsed.lab) == (UNKNOWN_CAMP, None)
    assert parsed.warnings == (
        "the folders name more than one camp in the alias table (BWW, TSF); camp recorded as UNKNOWN",
    )


# ------------------------------------------------------------------------------------------------
# v1-e30-t08: the title is what is left once the camp block is taken off
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("Orchard Kritik - TSF 2026 MNOP.docx", "Orchard Kritik"),
        ("Orchard Kritik - TSF 2026 M.docx", "Orchard Kritik"),
        ("Orchard Kritik - TSF 2026.docx", "Orchard Kritik"),
        ("Orchard Kritik - TSF.docx", "Orchard Kritik"),
        ("Orchard_Kritik_-_TSF_2026_MNO.docx", "Orchard_Kritik"),
        ("Orchard Kritik - TSF 2026 MNO (1).docx", "Orchard Kritik (1)"),
        ("Orchard Kritik - TSF 2026 (2).docx", "Orchard Kritik (2)"),
    ],
)
def test_the_camp_the_year_after_it_and_trailing_initials_come_off(path: str, title: str) -> None:
    assert parse(path).file_title == title


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("Orchard Kritik - TSF 2026 MNOPQ.docx", "Orchard Kritik MNOPQ"),
        ("Orchard Kritik - TSF 2026 Aff.docx", "Orchard Kritik Aff"),
        ("Orchard Kritik - TSF 2026 MNO Neg.docx", "Orchard Kritik MNO Neg"),
        ("Orchard Kritik 2026 - TSF MNO.docx", "Orchard Kritik 2026 MNO"),
        ("Orchard Kritik - TSF 26 MNO.docx", "Orchard Kritik 26 MNO"),
        ("Orchard Kritik - TSF (2026) MNO.docx", "Orchard Kritik (2026) MNO"),
    ],
)
def test_a_year_or_initials_not_directly_after_the_camp_stay_in_the_title(path: str, title: str) -> None:
    """Five letters are not initials, nor is `Aff`; initials that do not end the name stay; a year
    that is not the next word after the camp is not the camp's year."""
    assert parse(path).file_title == title


def test_an_unknown_camp_keeps_its_year_and_initials() -> None:
    assert parse("Orchard Kritik - Zephyr 2026 MNO.docx").file_title == "Orchard Kritik - Zephyr 2026 MNO"


def test_a_filename_that_is_only_a_camp_block_keeps_its_stem() -> None:
    assert parse("Tamarack/TSF 2026 MNO.docx").file_title == "TSF 2026 MNO"


# ------------------------------------------------------------------------------------------------
# ac1: an unresolved camp is UNKNOWN with a warning, never a failure
# ------------------------------------------------------------------------------------------------


def test_a_camp_nobody_listed_is_unknown_with_a_warning_and_keeps_its_whole_stem() -> None:
    parsed = parse("Zephyr Scholars - Glacier Case Neg.docx")

    assert parsed.camp == UNKNOWN_CAMP
    assert parsed.camp_resolved is False
    assert parsed.lab is None
    assert parsed.file_title == "Zephyr Scholars - Glacier Case Neg"
    assert parsed.warnings == (
        "no folder and no word of the filename names a camp in the alias table; camp recorded as UNKNOWN",
    )


def test_an_unknown_folder_is_not_a_lab() -> None:
    parsed = parse("Zephyr Scholars/Glacier Case Neg.docx")

    assert (parsed.camp, parsed.lab) == (UNKNOWN_CAMP, None)


def test_a_warning_never_quotes_the_path() -> None:
    parsed = parse("Zephyr Scholars/Glacier Case Neg.docx")

    assert all("Zephyr" not in warning and "Glacier" not in warning for warning in parsed.warnings)


# ------------------------------------------------------------------------------------------------
# Titles, formats and the sync's inbox names
# ------------------------------------------------------------------------------------------------


def test_the_inbox_prefix_the_scheduled_sync_adds_is_taken_off_first() -> None:
    parsed = parse("openev-417-TSF-Spillway Advantage.docx")

    assert (parsed.camp, parsed.file_title) == ("TSF", "Spillway Advantage")


def test_a_filename_that_is_only_a_camp_keeps_its_stem_as_the_title() -> None:
    assert parse("Tamarack/TSF.docx").file_title == "TSF"


def test_only_the_last_extension_is_taken_off() -> None:
    assert parse("Tamarack/Canal v1.2 Update.docx").file_title == "Canal v1.2 Update"


@pytest.mark.parametrize(
    ("path", "source_format"),
    [
        ("Tamarack/Reservoir Topicality.pdf", SourceFormat.PDF),
        ("Tamarack/Reservoir Topicality.DOC", SourceFormat.DOC),
        ("Tamarack/Reservoir Topicality.rtf", SourceFormat.OTHER),
    ],
)
def test_the_format_comes_from_the_extension(path: str, source_format: SourceFormat) -> None:
    assert parse(path).source_format is source_format


# ------------------------------------------------------------------------------------------------
# The alias table
# ------------------------------------------------------------------------------------------------


def test_the_packaged_table_loads_and_lists_the_camps_the_spec_names() -> None:
    aliases = load_camp_aliases()

    assert set(aliases.camps) >= {"DDI", "Michigan", "Gonzaga", "SDI", "NHSI", "UTNIF"}


def test_the_packaged_table_resolves_a_prefix_and_a_folder() -> None:
    aliases = load_camp_aliases()

    assert parse_camp_path("GDI_Topicality.docx", aliases=aliases).camp == "Gonzaga"
    assert parse_camp_path("Spartan Debate Institute/Lab/K.docx", aliases=aliases).camp == "SDI"


def test_an_edited_table_is_read_from_the_path_given(tmp_path: Path) -> None:
    table = tmp_path / "camp_aliases.yaml"
    table.write_text("camps:\n  TSF:\n    - Tamarack\n", encoding="utf-8")

    assert parse_camp_path("Tamarack/K.docx", aliases=load_camp_aliases(table)).camp == "TSF"


def test_a_camp_listed_with_no_spellings_still_matches_its_own_name(tmp_path: Path) -> None:
    table = tmp_path / "camp_aliases.yaml"
    table.write_text("camps:\n  TSF:\n", encoding="utf-8")

    assert parse_camp_path("TSF - K.docx", aliases=load_camp_aliases(table)).camp == "TSF"


def test_two_camps_sharing_a_spelling_are_refused() -> None:
    with pytest.raises(InvalidCampAliases, match="listed for both QDI and TSF"):
        CampAliases.from_document({"camps": {"QDI": ["Pines"], "TSF": ["pines"]}}, source="t")


@pytest.mark.parametrize(
    "document",
    [
        None,
        [],
        {"camps": {}},
        {"camps": ["QDI"]},
        {"camps": {"QDI": "Quillfeather"}},
        {"camps": {"QDI": [3]}},
        {"camps": {"QDI": ["--"]}},
    ],
)
def test_a_malformed_table_is_a_configuration_error(document: object) -> None:
    with pytest.raises(ConfigurationError):
        CampAliases.from_document(document, source="t")


def test_a_table_that_is_not_yaml_is_a_configuration_error(tmp_path: Path) -> None:
    table = tmp_path / "camp_aliases.yaml"
    table.write_text("camps: [unclosed\n", encoding="utf-8")

    with pytest.raises(InvalidCampAliases, match="not valid YAML"):
        load_camp_aliases(table)


def test_a_missing_table_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(InvalidCampAliases, match="could not be read"):
        load_camp_aliases(tmp_path / "absent.yaml")
