"""`config/daily_templates.yaml`: what `daily` asks in place of the taxonomy's templates (v1-e08-t25).

The PM's ruling of 2026-11-12: two-word digest templates, the first list being the four filled queries
that kept a feed item on the operator's run of 2026-11-12T23:21Z (`bill Congress`, `Senate Congress`,
`Senate Republicans`, `Senate election`), with `search`, the feed provider's every-word rule and every
coach-reviewed template unchanged. Expected queries are written by hand from the committed file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

from debate_core.application.daily_preset_config import DAILY_PRESETS_PATH, load_daily_presets
from debate_core.application.digest_templates import (
    DAILY_TEMPLATES_PATH,
    DigestTemplateError,
    check_digest_templates,
    load_digest_templates,
)
from debate_core.application.query_expansion import ARGUMENT_TAXONOMY_PATH, load_argument_taxonomy
from debate_core.domain.argument_taxonomy import ReviewStatus

REPOSITORY: Final = Path(__file__).resolve().parents[4]
TAXONOMY: Final = load_argument_taxonomy(REPOSITORY / ARGUMENT_TAXONOMY_PATH)
PRESETS: Final = load_daily_presets(REPOSITORY / DAILY_PRESETS_PATH)


def committed_document() -> dict[str, Any]:
    document: dict[str, Any] = yaml.safe_load((REPOSITORY / DAILY_TEMPLATES_PATH).read_text(encoding="utf-8"))
    return document


def written(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "daily_templates.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


# ------------------------------------------------------------------------------------------------
# The committed file
# ------------------------------------------------------------------------------------------------


def test_the_committed_file_asks_the_ruled_four_of_the_politics_preset() -> None:
    templates = check_digest_templates(
        load_digest_templates(REPOSITORY / DAILY_TEMPLATES_PATH), PRESETS, TAXONOMY, source="committed"
    )

    asked = {
        (pair, query): [(found.template_id, found.query) for found in templates.queries_for(*pair, query)]
        for pair in (("politics-da", "uniqueness"), ("midterms-da", "uniqueness"))
        for query in ("bill", "Senate")
    }
    assert asked == {
        (("politics-da", "uniqueness"), "bill"): [("digest/politics-da/uniqueness/1", "bill Congress")],
        (("politics-da", "uniqueness"), "Senate"): [
            ("digest/politics-da/uniqueness/1", "Senate Congress"),
            ("digest/politics-da/uniqueness/2", "Senate Republicans"),
        ],
        (("midterms-da", "uniqueness"), "bill"): [],
        (("midterms-da", "uniqueness"), "Senate"): [("digest/midterms-da/uniqueness/1", "Senate election")],
    }


@pytest.mark.parametrize("argument", ["spending-da", "federalism-da", "economy-da"])
def test_the_nhi_presets_pairs_have_none_and_ask_the_taxonomys_templates(argument: str) -> None:
    """The PM's ruling C (2026-11-12): no digest templates of its own, so the search asks the
    taxonomy's, and there is no digest query for it."""
    templates = load_digest_templates(REPOSITORY / DAILY_TEMPLATES_PATH)

    assert templates.asks_taxonomy(argument, "uniqueness")
    assert templates.queries_for(argument, "uniqueness", "health insurance") == ()


def test_a_pair_with_digest_templates_does_not_ask_the_taxonomys() -> None:
    templates = load_digest_templates(REPOSITORY / DAILY_TEMPLATES_PATH)

    assert not templates.asks_taxonomy("politics-da", "uniqueness")
    assert not templates.asks_taxonomy("midterms-da", "uniqueness")


# ------------------------------------------------------------------------------------------------
# What the file may say
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "{query} vote count",
        "{query}",
        "Congress",
        "Senate Congress",
        "{query} {query}",
        "{query}  Congress",
        "a {query} b",
    ],
    ids=[
        "three words",
        "the query alone",
        "no query",
        "a filled query",
        "the query twice",
        "two spaces",
        "around",
    ],
)
def test_a_template_that_is_not_the_query_and_one_word_is_refused(tmp_path: Path, text: str) -> None:
    document = committed_document()
    document["groups"][0]["templates"].append({"text": text})

    with pytest.raises(DigestTemplateError, match="a digest template is the query and one word"):
        load_digest_templates(written(tmp_path, document))


@pytest.mark.parametrize("text", ["{query} Congress", "Congress {query}", "{query} U.S."])
def test_the_query_and_one_word_either_way_round_loads(tmp_path: Path, text: str) -> None:
    document = committed_document()
    document["groups"][0]["templates"] = [{"text": text}]

    templates = load_digest_templates(written(tmp_path, document))

    assert templates.groups[0].templates[0].text == text


def test_a_key_the_file_does_not_define_is_refused(tmp_path: Path) -> None:
    document = committed_document()
    document["groups"][0]["templates"][0]["recency_days"] = 30

    with pytest.raises(DigestTemplateError, match="recency_days"):
        load_digest_templates(written(tmp_path, document))


def test_a_pair_listed_twice_is_refused(tmp_path: Path) -> None:
    document = committed_document()
    document["groups"].append(document["groups"][0])

    with pytest.raises(DigestTemplateError, match="listed more than once: politics-da/uniqueness"):
        load_digest_templates(written(tmp_path, document))


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (
            {"argument": "ptx"},
            "group ptx/uniqueness: the taxonomy has no argument with the id 'ptx'; did you mean "
            "'politics-da'",
        ),
        ({"argument": "space-da"}, "group space-da/uniqueness: the taxonomy has no argument with the id"),
        ({"need": "uq"}, "group politics-da/uq: politics-da has no need with the id 'uq'"),
    ],
    ids=["an alias", "an argument there is not", "a need alias"],
)
def test_a_group_must_name_a_taxonomy_pair_by_its_ids(
    tmp_path: Path, change: dict[str, str], problem: str
) -> None:
    document = committed_document()
    document["groups"][0].update(change)
    templates = load_digest_templates(written(tmp_path, document))

    with pytest.raises(DigestTemplateError, match=problem.replace("(", r"\(")):
        check_digest_templates(templates, PRESETS, TAXONOMY, source="config/daily_templates.yaml")


def test_a_query_no_preset_with_the_pair_asks_is_refused(tmp_path: Path) -> None:
    """`health insurance` is a query, but of nhi, which has no politics DA pair."""
    document = committed_document()
    document["groups"][0]["templates"][0]["queries"] = ["bill", "health insurance"]
    templates = load_digest_templates(written(tmp_path, document))

    with pytest.raises(
        DigestTemplateError, match="is for the query 'health insurance', which no preset with this pair asks"
    ):
        check_digest_templates(templates, PRESETS, TAXONOMY, source="config/daily_templates.yaml")


def test_a_file_that_is_not_yaml_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "daily_templates.yaml"
    path.write_text("groups: [unclosed\n", encoding="utf-8")

    with pytest.raises(DigestTemplateError, match="cannot be read"):
        load_digest_templates(path)


# ------------------------------------------------------------------------------------------------
# The coach-reviewed templates stay as they are
# ------------------------------------------------------------------------------------------------

REVIEWED_TEMPLATES_SHA256: Final = "b12d306a486999eb4de5f874fc5b4ec55217dd9da84ca8e5c5c5300398cc191d"
"""Every coach-reviewed argument's templates, each text and window, as on dev before this task (taxonomy
1.6.0, 35 arguments, 456 templates): sha256 of the canonical JSON below. A change to any byte of any
reviewed template's text changes it."""


def test_every_coach_reviewed_template_is_byte_for_byte_as_it_was() -> None:
    reviewed = {
        argument.id: {
            need: [[template.text, template.recency_days] for template in templates]
            for need, templates in argument.templates.items()
        }
        for argument in TAXONOMY.arguments
        if argument.review is ReviewStatus.COACH_REVIEWED
    }
    canonical = json.dumps(reviewed, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    assert (
        len(reviewed),
        sum(len(need) for argument in reviewed.values() for need in argument.values()),
    ) == (
        35,
        456,
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == REVIEWED_TEMPLATES_SHA256


def test_the_uniqueness_templates_daily_used_to_ask_are_unchanged_for_search() -> None:
    """Written by hand from the taxonomy as the coach reviewed it (2026-11-02)."""
    texts = {
        argument.id: [template.text for template in argument.templates["uniqueness"]]
        for argument in TAXONOMY.arguments
        if argument.id in ("politics-da", "midterms-da")
    }

    assert texts == {
        "politics-da": [
            "{query} vote count Senate",
            "{query} likely to pass Congress",
            "{query} will not pass",
            "{bill} whip count",
        ],
        "midterms-da": ["{topic} midterms polling", "{query} election forecast"],
    }
