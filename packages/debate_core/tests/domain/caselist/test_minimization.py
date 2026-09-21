"""The data-minimization guard: no caselist model may grow a field that identifies a person.

Caselist data is about other people's children. The platform stores a school name and the team
code a team disclosed under — usually initials — and nothing else about who they are (architecture
proposal §14, and the removal process in `docs/policies/caselist-data-use.md`).

That is a rule nobody remembers under deadline, so it is pinned here two ways:

* **Field sets are exact.** Every model's fields are listed below. Adding, renaming or removing one
  fails this test, which forces the change to be a deliberate edit to a file that says why the
  rule exists rather than a line slipped into an entity.
* **Name-shaped field names are banned outright.** Even a field pinned in the list above cannot be
  called `debater_name` or `email`, so a future entity cannot pass by being added to both places
  without anyone reading them.

`School.name` and `Caselist.display_name` are the deliberate exceptions to the second rule: an
institution's name is not a person's, and both are checked explicitly below.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from debate_core.domain.caselist import (
    CASELIST_MODELS,
    ArchiveSnapshot,
    CampFile,
    Caselist,
    Disclosure,
    RoundLabel,
    School,
    SourceDocument,
    TeamCode,
)

#: The exact field set of every caselist model. Changing one is a deliberate edit, right here.
EXPECTED_FIELDS: dict[type[BaseModel], frozenset[str]] = {
    Caselist: frozenset({"slug", "event", "level", "season", "display_name"}),
    School: frozenset({"caselist", "name"}),
    TeamCode: frozenset({"caselist", "school", "code"}),
    ArchiveSnapshot: frozenset({"caselist", "snapshot", "archive_sha256", "acquisition", "file_count"}),
    SourceDocument: frozenset(
        {
            "sha256",
            "byte_size",
            "source_format",
            "origin",
            "caselist",
            "first_seen_snapshot",
            "last_seen_snapshot",
            "provenance_mode",
        }
    ),
    Disclosure: frozenset(
        {
            "source_sha256",
            "caselist",
            "snapshot",
            "event",
            "school",
            "team_code",
            "side",
            "tournament",
            "round_label",
            "source_path",
            "parse_warnings",
            "provenance_mode",
        }
    ),
    CampFile: frozenset(
        {
            "source_sha256",
            "camp",
            "year",
            "event",
            "file_title",
            "snapshot",
            "parse_warnings",
            "provenance_mode",
        }
    ),
    RoundLabel: frozenset({"raw", "normalized"}),
}

#: Field-name fragments that would mean the platform had started collecting personal data.
#: `name` alone is not among them: a school has a name and a person is not a school.
BANNED_FIELD_NAME_FRAGMENTS = (
    "debater",
    "student",
    "competitor",
    "first_name",
    "last_name",
    "full_name",
    "given_name",
    "family_name",
    "surname",
    "person",
    "email",
    "phone",
    "address",
    "tabroom",
    "birth",
    "gender",
    "photo",
)


def test_every_caselist_model_is_covered_by_this_guard() -> None:
    """A new entity added to `CASELIST_MODELS` must be pinned here before CI will pass."""
    uncovered = [model.__name__ for model in CASELIST_MODELS if model not in EXPECTED_FIELDS]
    assert not uncovered, f"add these models to EXPECTED_FIELDS: {uncovered}"


@pytest.mark.parametrize("model", list(EXPECTED_FIELDS), ids=lambda model: model.__name__)
def test_a_models_field_set_is_exactly_what_was_pinned(model: type[BaseModel]) -> None:
    actual = frozenset(model.model_fields)
    expected = EXPECTED_FIELDS[model]
    added = sorted(actual - expected)
    removed = sorted(expected - actual)
    assert actual == expected, (
        f"{model.__name__} field set changed — added {added}, removed {removed}. "
        "If this is deliberate, update EXPECTED_FIELDS and check the new field stores no "
        "personal data (architecture proposal §14)."
    )


@pytest.mark.parametrize("model", list(EXPECTED_FIELDS), ids=lambda model: model.__name__)
def test_no_field_name_suggests_personal_data(model: type[BaseModel]) -> None:
    offending = [
        field
        for field in model.model_fields
        if any(fragment in field.lower() for fragment in BANNED_FIELD_NAME_FRAGMENTS)
    ]
    assert not offending, (
        f"{model.__name__} has field(s) that look like personal data: {offending}. "
        "The platform stores a school name and a disclosed team code, nothing about who debated."
    )


def test_the_only_name_fields_are_an_institutions_name_and_a_caselist_label() -> None:
    """A field called `name` is allowed only where it names a school or labels a caselist.

    Matched on the suffix rather than anywhere in the word, because `tournament` contains the
    letters `name` and a tournament is not a person.
    """
    name_fields = {
        (model.__name__, field)
        for model in EXPECTED_FIELDS
        for field in model.model_fields
        if field.lower() == "name" or field.lower().endswith("_name")
    }
    assert name_fields == {("School", "name"), ("Caselist", "display_name")}


def test_a_team_code_is_the_only_place_a_team_is_identified() -> None:
    """The team-identifying fields, enumerated: a school, a team code, nothing else."""
    team_fields = {
        (model.__name__, field)
        for model in EXPECTED_FIELDS
        for field in model.model_fields
        if field in {"school", "team_code", "code"}
    }
    assert team_fields == {
        ("TeamCode", "school"),
        ("TeamCode", "code"),
        ("Disclosure", "school"),
        ("Disclosure", "team_code"),
    }


def test_no_caselist_model_accepts_an_unknown_field() -> None:
    """`extra="forbid"` is what stops a name arriving in stored JSON and being kept."""
    for model in EXPECTED_FIELDS:
        assert model.model_config.get("extra") == "forbid", model.__name__
