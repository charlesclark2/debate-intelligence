"""Each camp's OpenEv address word, in the alias table's `openev` section (`v1-e39-t28`).

A camp's page on OpenEv is `https://opencaselist.com/openev/<year>/<word>`, and the word is OpenEv's
own, not the canonical name the importer records. The section maps a canonical camp to it, filled only
with the words the operator confirmed by opening the page. Every camp and word in the invented tables
here is invented (data-use policy, rule 5); the packaged table's are its own entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from debate_core.application.caselist.camp_metadata import (
    CampAliases,
    InvalidCampAliases,
    load_camp_aliases,
    parse_camp_path,
)
from debate_core.application.settings import ConfigurationError

CAMPS = {"Cascade Institute": ["Cascade", "CDI"], "Ridgeline": ["RLI"], "Lakeshore": None}


def table(openev: object) -> CampAliases:
    return CampAliases.from_document({"camps": CAMPS, "openev": openev}, source="t")


def test_the_packaged_table_holds_the_words_the_operator_confirmed() -> None:
    """Written by hand from the operator's checks of 2026-10-31: a word only for a page that opened."""
    assert dict(load_camp_aliases().openev_words) == {"UTNIF": "UTNIF"}


def test_the_section_maps_a_canonical_camp_to_its_word() -> None:
    words = table({"Cascade Institute": "CASCADE", "Ridgeline": "RDI7"}).openev_words
    assert dict(words) == {"Cascade Institute": "CASCADE", "Ridgeline": "RDI7"}


@pytest.mark.parametrize(
    "document", [{"camps": CAMPS}, {"camps": CAMPS, "openev": None}, {"camps": CAMPS, "openev": {}}]
)
def test_a_table_without_words_has_none(document: dict[str, Any]) -> None:
    assert dict(CampAliases.from_document(document, source="t").openev_words) == {}


def test_the_words_change_nothing_the_importer_reads() -> None:
    """The same file's camp, lab and title, with and without the section."""
    without = CampAliases.from_document({"camps": CAMPS}, source="t")
    with_words = table({"Cascade Institute": "CASCADE"})
    assert with_words.by_words == without.by_words
    path = "CDI/Lab A/Politics DA - CDI 2026 AB.docx"
    assert parse_camp_path(path, aliases=with_words) == parse_camp_path(path, aliases=without)


@pytest.mark.parametrize(
    ("openev", "message"),
    [
        (["CASCADE"], "`openev` must map a camp to its OpenEv word"),
        ("CASCADE", "`openev` must map a camp to its OpenEv word"),
        ({"Cascade": "CASCADE"}, "'Cascade' is not a camp of the table"),
        ({"Elsewhere": "ELSE"}, "'Elsewhere' is not a camp of the table"),
        ({"UNKNOWN": "UNKNOWN"}, "'UNKNOWN' is not a camp of the table"),
        ({"Cascade Institute": "Cascade Inst"}, "'Cascade Inst' is not one OpenEv address word"),
        ({"Cascade Institute": "CASCADE/.."}, "is not one OpenEv address word"),
        ({"Cascade Institute": "CASCADE\n"}, "is not one OpenEv address word"),
        ({"Cascade Institute": ""}, "is not one OpenEv address word"),
        ({"Cascade Institute": "Cäscade"}, "is not one OpenEv address word"),
        ({"Cascade Institute": "UNKNOWN"}, "is not one OpenEv address word"),
        ({"Cascade Institute": 7}, "is not one OpenEv address word"),
        ({"Cascade Institute": None}, "is not one OpenEv address word"),
        ({"Cascade Institute": "CASCADE", "Ridgeline": "CASCADE"}, "both Cascade Institute and Ridgeline"),
    ],
    ids=lambda value: repr(value)[:30],
)
def test_a_section_that_is_not_camps_to_words_is_refused(openev: object, message: str) -> None:
    """Refused when the table is loaded, so a bad word stops the import and the app, never a link."""
    with pytest.raises(InvalidCampAliases, match=message) as refused:
        table(openev)
    assert isinstance(refused.value, ConfigurationError)


def test_an_edited_tables_words_are_read_from_the_path_given(tmp_path: Path) -> None:
    edited = tmp_path / "aliases.yaml"
    edited.write_text("camps:\n  Ridgeline:\n    - RLI\nopenev:\n  Ridgeline: RDI7\n", encoding="utf-8")
    assert dict(load_camp_aliases(edited).openev_words) == {"Ridgeline": "RDI7"}
