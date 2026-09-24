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
        ("QDI 2026 Harbor Tariffs Aff.docx", "2026 Harbor Tariffs Aff"),
    ],
)
def test_any_separator_after_the_prefix_is_taken_off_and_nothing_else(path: str, title: str) -> None:
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
        "the filename prefix names camp QDI but the folder names BWW; the folder's camp is recorded",
    )


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
        "no folder and no filename prefix names a camp in the alias table; camp recorded as UNKNOWN",
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
