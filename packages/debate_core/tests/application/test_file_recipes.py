"""Loading, hashing and resolving file recipes (`v1-e33-t01` ac2, ac3, ac4, ac5 and the PM's amendment).

* **load**: a recipe is read from YAML text, and every error is reported with its YAML line and its
  path in the recipe, not just the first.
* **hash**: `recipe_hash` is the SHA-256 of a canonical JSON form, so how the YAML is written does
  not change it and what the file holds does.
* **resolve**: each card reference is mapped to exactly one occurrence in the E31 occurrence store,
  through the parsed-store, caselist and suppression ports, all in memory here.
* **examples**: the three synthetic recipes the guide walks through load, validate and resolve.

Every fingerprint, source hash, school and team code here is invented (`Maple Grove`, `QX`,
`Cedar Hollow`, `ZaLu`). Each expected line number and path is counted by hand from the YAML text
above it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from debate_core.application import file_recipes
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.application.ports.suppression import (
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import CampFile, Disclosure, Event, RoundLabel, Side
from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.file_recipe import FileRecipe
from debate_core.evidence import fingerprints
from debate_core.testing.fakes import (
    InMemoryAppendOnlyRecord,
    InMemoryCaselistRepository,
    InMemoryParsedStore,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
EXAMPLES = REPO_ROOT / "tests" / "fixtures" / "file_builder" / "recipes"
GUIDE = REPO_ROOT / "docs" / "guides" / "file-recipes.md"
SCHEMA = REPO_ROOT / "docs" / "data" / "file-recipe.schema.json"

CASELIST = "hsld26"
PARSER = "2026.10.18-docx-4"
PROFILE = "2026.09.20-verbatim-1"

CARD_A = "a0" * 32
CARD_B = "b1" * 32
CARD_C = "c2" * 32
SOURCE_1 = "1a" * 32
SOURCE_2 = "2b" * 32
SOURCE_3 = "3c" * 32


# ------------------------------------------------------------------------------------------------
# Recipes as text
# ------------------------------------------------------------------------------------------------

HEADER = """\
schema_version: 1
title: Synthetic test file
topic: synthetic-topic
format: LD
caselist: hsld26
position: synthetic-position
side: NEG
fingerprint_version: card-fingerprint-v3
"""


def recipe_text(*items: str, header: str = HEADER) -> str:
    """A one-pocket, one-block recipe holding `items`, each a YAML list entry at block indent."""
    body = "".join(f"          {item}\n" for item in items)
    return f"{header}structure:\n  - pocket: P\n    blocks:\n      - block: B\n        items:\n{body}"


def card(fingerprint: str, *, pin: Mapping[str, object] | None = None, tag: str | None = None) -> str:
    """A card item in flow style, so a test reads as a list of items."""
    fields: dict[str, object] = {"fingerprint": fingerprint}
    if tag is not None:
        fields["tag_override"] = tag
    if pin is not None:
        fields["pin"] = pin
    return "- " + json.dumps(fields)


def load_ok(text: str) -> FileRecipe:
    result = file_recipes.load_recipe(text)
    assert result.errors == ()
    assert result.recipe is not None
    return result.recipe


def where(result: Any) -> list[tuple[str, int | None]]:
    """(path, line) of every error, in the order reported."""
    return [(error.path, error.line) for error in result.errors]


# ------------------------------------------------------------------------------------------------
# load
# ------------------------------------------------------------------------------------------------

SEVERAL_DEPTHS = """\
schema_version: 1
title: Synthetic test file
topic: synthetic-topic
format: LDX
caselist: hsld26
position: synthetic-position
side: NEG
fingerprint_version: card-fingerprint-v3
structure:
  - pocket: First pocket
    colour: blue
    hats:
      - hat: Empty hat
        blocks: []
      - hat: Second hat
        blocks:
          - block: B0
            items:
              - analytic: one
          - block: B1
            items:
              - analytic: one
          - block: B2
            items:
              - analytic: first
              - analytic: second
              - analytic: third
              - fingerprint: NOT-A-FINGERPRINT
                pin:
                  caselist: hsld26
                  source_sha256: 1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a
                  element_index: -1
"""


def test_load_reports_every_error_with_its_line_and_path_at_several_depths() -> None:
    result = file_recipes.load_recipe(SEVERAL_DEPTHS)

    assert result.recipe is None
    assert sorted(where(result), key=lambda pair: pair[1] or 0) == [
        ("format", 4),
        ("structure[0].colour", 11),
        ("structure[0].hats[0].blocks", 14),
        ("structure[0].hats[1].blocks[2].items[3].fingerprint", 28),
        ("structure[0].hats[1].blocks[2].items[3].pin.element_index", 32),
    ]
    assert {error.code for error in result.errors} == {file_recipes.RecipeErrorCode.INVALID}


FLOW_STYLE = """\
schema_version: 1
title: Flow test
topic: synthetic-topic
format: LD
caselist: hsld26
position: synthetic-position
side: NEG
fingerprint_version: card-fingerprint-v3
structure:
  - {pocket: P, blocks: [{block: B, items: [
      {analytic: fine},
      {fingerprint: zz, tag_override: ""},
      {fingerprint: a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0, pin: {caselist: openev,
                     source_sha256: 1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a,
                     element_index: true}},
      {analytic: fine, extra: 1}
    ]}]}
"""


def test_load_reports_errors_inside_flow_style_mappings_on_their_own_lines() -> None:
    result = file_recipes.load_recipe(FLOW_STYLE)

    assert sorted(where(result), key=lambda pair: (pair[1] or 0, pair[0])) == [
        ("structure[0].blocks[0].items[1].fingerprint", 12),
        ("structure[0].blocks[0].items[1].tag_override", 12),
        ("structure[0].blocks[0].items[2].pin.caselist", 13),
        ("structure[0].blocks[0].items[2].pin.element_index", 15),
        ("structure[0].blocks[0].items[3].extra", 16),
    ]


def test_load_reports_a_missing_field_at_the_line_of_the_mapping_that_lacks_it() -> None:
    text = recipe_text("- pin: {caselist: hsld26, source_sha256: " + SOURCE_1 + ", element_index: 3}")
    result = file_recipes.load_recipe(text)
    # Line 14 is the item; it has a pin and no fingerprint, so it is read as neither kind of item.
    assert where(result) == [("structure[0].blocks[0].items[0]", 14)]

    text = recipe_text(
        "- " + json.dumps({"fingerprint": CARD_A, "pin": {"caselist": "hsld26", "element_index": 3}})
    )
    assert where(file_recipes.load_recipe(text)) == [
        ("structure[0].blocks[0].items[0].pin.source_sha256", 14)
    ]


def test_load_reports_cross_section_errors_beside_field_errors() -> None:
    text = HEADER.replace("side: NEG", "side: PRO") + (
        "structure:\n"  # 9
        "  - pocket: With hats\n"  # 10
        "    hats:\n"  # 11
        "      - hat: H\n"  # 12
        "        blocks:\n"  # 13
        "          - block: B\n"  # 14
        "            items:\n"  # 15
        "              - fingerprint: bad\n"  # 16
        "  - pocket: Without hats\n"  # 17
        "    blocks:\n"  # 18
        "      - block: B\n"  # 19
        "        items:\n"  # 20
        "          - analytic: x\n"  # 21
    )
    assert sorted(where(file_recipes.load_recipe(text)), key=lambda pair: pair[1] or 0) == [
        ("side", 7),
        ("structure[0].hats[0].blocks[0].items[0].fingerprint", 16),
        ("structure[1].blocks", 18),
    ]


def test_load_reports_a_yaml_syntax_error_with_its_line() -> None:
    text = HEADER + "structure:\n  - pocket: P\n    blocks: x: y\n"
    (error,) = file_recipes.load_recipe(text).errors
    assert (error.code, error.path, error.line) == (file_recipes.RecipeErrorCode.YAML_SYNTAX, "", 11)
    assert "x: y" not in error.message


def test_load_reports_an_explicit_key_beside_a_merge_at_its_own_line() -> None:
    text = recipe_text(
        "- fingerprint: " + CARD_A + "\n"  # line 14
        "            pin:\n"  # line 15
        "              <<: {caselist: hsld26, source_sha256: " + SOURCE_1 + ", element_index: 4}\n"  # line 16
        "              element_index: -1"  # line 17
    )
    assert where(file_recipes.load_recipe(text)) == [
        ("structure[0].blocks[0].items[0].pin.element_index", 17)
    ]


def test_load_reports_each_duplicate_key_with_its_line() -> None:
    text = (
        HEADER
        + "title: A second title\nstructure:\n  - pocket: P\n    pocket: Q\n    blocks:\n"
        + ("      - block: B\n        items:\n          - analytic: x\n")
    )
    result = file_recipes.load_recipe(text)
    duplicates = [
        error for error in result.errors if error.code is file_recipes.RecipeErrorCode.DUPLICATE_KEY
    ]
    assert [(error.path, error.line) for error in duplicates] == [("title", 9), ("structure[0].pocket", 12)]


def test_load_refuses_more_than_one_document() -> None:
    text = recipe_text("- analytic: x") + "---\n" + recipe_text("- analytic: y")
    (error,) = file_recipes.load_recipe(text).errors
    assert error.code is file_recipes.RecipeErrorCode.YAML_SYNTAX


@pytest.mark.parametrize(
    ("text", "line"),
    [("", None), ("# only a comment\n", None), ("- a list\n", 1), ("# a comment first\njust text\n", 2)],
)
def test_load_refuses_a_recipe_that_is_not_a_mapping(text: str, line: int | None) -> None:
    result = file_recipes.load_recipe(text)
    assert result.recipe is None
    assert where(result) == [("", line)]


def test_load_refuses_aliases_that_expand_past_the_node_budget() -> None:
    lines = ["a0: &a0 [x, x, x, x, x, x, x, x, x, x]"]
    lines += [f"a{n}: &a{n} [{', '.join([f'*a{n - 1}'] * 10)}]" for n in range(1, 7)]
    result = file_recipes.load_recipe("\n".join(lines) + "\n")
    (error,) = result.errors
    assert error.code is file_recipes.RecipeErrorCode.TOO_LARGE


def test_load_refuses_text_past_the_size_limit() -> None:
    text = recipe_text("- analytic: x") + "#" * (file_recipes.RECIPE_MAX_BYTES + 1) + "\n"
    (error,) = file_recipes.load_recipe(text).errors
    assert error.code is file_recipes.RecipeErrorCode.TOO_LARGE


@pytest.mark.parametrize("version", ["card-fingerprint-v9", "card-fingerprint", "v3"])
def test_load_reports_a_fingerprint_version_whose_digests_are_not_todays(version: str) -> None:
    text = recipe_text("- analytic: x", header=HEADER.replace("card-fingerprint-v3", version))
    assert where(file_recipes.load_recipe(text)) == [("fingerprint_version", 8)]


@pytest.mark.parametrize("version", sorted(fingerprints.EXACT_FINGERPRINT_VERSIONS))
def test_load_takes_every_fingerprint_version_with_todays_digests(version: str) -> None:
    load_ok(recipe_text("- analytic: x", header=HEADER.replace("card-fingerprint-v3", version)))


def test_the_current_fingerprint_version_is_one_a_recipe_can_name() -> None:
    assert fingerprints.FINGERPRINT_VERSION in fingerprints.EXACT_FINGERPRINT_VERSIONS


def test_load_never_repeats_a_rejected_value_in_a_message() -> None:
    pin = {"caselist": "hsld26", "source_sha256": SOURCE_1, "element_index": 3, "team_code": "Jane Rivera"}
    text = recipe_text(
        card(CARD_A, pin=pin), header=HEADER.replace("title: Synthetic test file", "title: ''")
    )
    result = file_recipes.load_recipe(text)
    assert len(result.errors) == 2
    for error in result.errors:
        assert "Jane" not in error.message and "Rivera" not in error.message


def test_load_returns_the_recipe_its_hash_and_the_line_of_every_item() -> None:
    text = recipe_text("- analytic: x", card(CARD_A, tag="Coach tag"))
    result = file_recipes.load_recipe(text)

    assert result.ok
    assert result.recipe is not None
    assert result.recipe_hash == file_recipes.recipe_hash(result.recipe)
    assert result.lines["structure[0].blocks[0].items[0]"] == 14
    assert result.lines["structure[0].blocks[0].items[1]"] == 15
    assert result.lines["structure[0].blocks[0].items[1].fingerprint"] == 15


def test_load_reads_yaml_scalars_strictly() -> None:
    """`side: no` is a boolean in YAML 1.1 and a quoted number is a string: neither is coerced."""
    text = recipe_text("- analytic: x", header=HEADER.replace("side: NEG", "side: no"))
    assert where(file_recipes.load_recipe(text)) == [("side", 7)]

    pin = '{caselist: hsld26, source_sha256: "' + SOURCE_1 + '", element_index: "3"}'
    text = recipe_text("- fingerprint: " + CARD_A + "\n            pin: " + pin)
    assert where(file_recipes.load_recipe(text)) == [
        ("structure[0].blocks[0].items[0].pin.element_index", 15)
    ]


def test_load_says_to_quote_a_hash_that_yaml_read_as_a_number() -> None:
    digits = "1" * 64
    text = recipe_text("- fingerprint: " + digits)
    (error,) = file_recipes.load_recipe(text).errors
    assert (error.path, error.line) == ("structure[0].blocks[0].items[0].fingerprint", 14)
    assert "put it in quotes" in error.message
    load_ok(recipe_text(f'- fingerprint: "{digits}"'))


def test_a_recipe_error_prints_its_line_path_message_and_code() -> None:
    error = file_recipes.RecipeError(
        file_recipes.RecipeErrorCode.UNKNOWN_CARD, "structure[0]", 12, "no such card"
    )
    assert str(error) == "line 12: structure[0]: no such card [UNKNOWN_CARD]"
    whole = file_recipes.RecipeError(file_recipes.RecipeErrorCode.TOO_LARGE, "", None, "too big")
    assert str(whole) == "recipe: (recipe): too big [TOO_LARGE]"


def test_load_refuses_a_python_tag_without_running_it() -> None:
    text = recipe_text(
        "- analytic: x",
        header=HEADER.replace("title: Synthetic test file", "title: !!python/object/apply:os.system [echo]"),
    )
    (error,) = file_recipes.load_recipe(text).errors
    assert (error.code, error.line) == (file_recipes.RecipeErrorCode.YAML_SYNTAX, 2)


def test_load_refuses_a_character_yaml_cannot_read() -> None:
    (error,) = file_recipes.load_recipe(HEADER + "structure: \x07\n").errors
    assert (error.code, error.line) == (file_recipes.RecipeErrorCode.YAML_SYNTAX, 9)
    assert "0x0007" in error.message


def test_load_refuses_a_list_used_as_a_key() -> None:
    (error,) = file_recipes.load_recipe(HEADER + "? [a, b]\n: x\nstructure: []\n").errors
    assert error.code is file_recipes.RecipeErrorCode.YAML_SYNTAX


def test_load_says_which_heading_level_an_out_of_place_key_skips() -> None:
    text = HEADER + "structure:\n  - pocket: P\n    items:\n      - analytic: x\n"
    result = file_recipes.load_recipe(text)
    assert where(result) == [("structure[0]", 10), ("structure[0].items", 11)]
    assert "skips or repeats a heading level" in result.errors[1].message


def test_load_names_the_fields_a_pin_has() -> None:
    pin = {"caselist": "hsld26", "source_sha256": SOURCE_1, "element_index": 3, "team": "QX"}
    (error,) = file_recipes.load_recipe(recipe_text(card(CARD_A, pin=pin))).errors
    assert error.path == "structure[0].blocks[0].items[0].pin.team"
    assert "not a field of a pin; a pin has caselist, source_sha256, element_index" in error.message


def test_load_takes_a_camp_pin_with_its_release_unquoted() -> None:
    """`v1-e33-t06`: YAML reads `2031-policy` as text, and the pin keeps it as the release."""
    text = recipe_text(
        "- fingerprint: " + CARD_A,
        "  pin: {caselist: openev, source_sha256: " + SOURCE_1 + ", element_index: 5, snapshot: 2031-policy}",
    )
    ((_, ref),) = load_ok(text).card_refs()
    assert ref.pin is not None and (ref.pin.caselist, ref.pin.snapshot) == ("openev", "2031-policy")


@pytest.mark.parametrize(
    ("pin", "field", "says"),
    [
        ({"caselist": "openev", "source_sha256": SOURCE_1, "element_index": 5}, "snapshot", "release"),
        (
            {"caselist": "openev", "source_sha256": SOURCE_1, "element_index": 5, "snapshot": "2031-09-15"},
            "snapshot",
            "release",
        ),
        (
            {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5, "snapshot": "2031-policy"},
            "snapshot",
            "caselist: openev",
        ),
        (
            {
                "caselist": "openev",
                "source_sha256": SOURCE_1,
                "element_index": 5,
                "snapshot": "2031-policy",
                "team_code": "QX",
            },
            "team_code",
            "no disclosure",
        ),
    ],
    ids=["no-release", "a-date", "a-release-in-a-caselist-pin", "a-team"],
)
def test_load_says_what_a_camp_pin_needs_at_the_field_and_line(
    pin: dict[str, object], field: str, says: str
) -> None:
    result = file_recipes.load_recipe(recipe_text(card(CARD_A, pin=pin)))
    assert [(str(error.code), error.path, error.line) for error in result.errors] == [
        ("INVALID", f"structure[0].blocks[0].items[0].pin.{field}", 14)
    ]
    assert says in result.errors[0].message
    assert "QX" not in result.errors[0].message


# ------------------------------------------------------------------------------------------------
# hash
# ------------------------------------------------------------------------------------------------

TINY = """\
schema_version: 1
title: T
topic: t
format: LD
caselist: hsld26
position: p
side: NEG
fingerprint_version: card-fingerprint-v3
structure:
  - pocket: T
    blocks:
      - block: B
        items:
          - fingerprint: a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0
            tag_override: Coach tag
          - analytic: Coach words
"""

TINY_CANONICAL = (
    '{"caselist":"hsld26","fingerprint_version":"card-fingerprint-v3","format":"LD","position":"p",'
    '"schema_version":1,"side":"NEG","status":"ready","structure":[{"blocks":[{"block":"B","items":['
    '{"fingerprint":"a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0",'
    '"tag_override":"Coach tag"},{"analytic":"Coach words"}]}],"pocket":"T"}],"title":"T","topic":"t"}'
)


def test_the_hash_is_the_sha256_of_the_canonical_json_written_out_by_hand() -> None:
    recipe = load_ok(TINY)
    assert file_recipes.canonical_recipe_json(recipe) == TINY_CANONICAL
    assert file_recipes.recipe_hash(recipe) == hashlib.sha256(TINY_CANONICAL.encode("ascii")).hexdigest()


def test_the_canonical_json_escapes_non_ascii_text() -> None:
    recipe = load_ok(TINY.replace("title: T", "title: Débat"))
    assert '"title":"D\\u00e9bat"' in file_recipes.canonical_recipe_json(recipe)


TINY_REWRITTEN = """\
# The same recipe: keys in another order, comments, an anchor and its alias, quoting, flow style.
title: &shared "T"
structure:
  - blocks:   # a pocket without hats
      - items:
          - {tag_override: Coach tag,
             fingerprint: a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0}
          - analytic: 'Coach words'
        block: B
    pocket: *shared
side: NEG       # negative
position: p
fingerprint_version: card-fingerprint-v3
caselist: hsld26
format: LD
topic: t
schema_version: 1
status: ready
"""


def test_the_hash_ignores_key_order_comments_anchors_aliases_quoting_and_flow_style() -> None:
    assert file_recipes.recipe_hash(load_ok(TINY_REWRITTEN)) == file_recipes.recipe_hash(load_ok(TINY))


def test_the_hash_is_the_same_through_a_merge_key() -> None:
    with_pin = recipe_text(
        "- fingerprint: "
        + CARD_A
        + "\n            pin: {caselist: hsld26, source_sha256: "
        + SOURCE_1
        + ", element_index: 4, team_code: QX}"
    )
    merged = with_pin.replace(
        "structure:",
        "x_defaults: &pin_defaults {caselist: hsld26, source_sha256: " + SOURCE_1 + "}\nstructure:",
    ).replace("pin: {caselist: hsld26, source_sha256: " + SOURCE_1 + ", ", "pin: {<<: *pin_defaults, ")
    # A merge key is a convenience for writing pins; a key the recipe does not know is still refused.
    assert where(file_recipes.load_recipe(merged)) == [("x_defaults", 9)]
    merged_inline = with_pin.replace(
        "pin: {caselist: hsld26, source_sha256: " + SOURCE_1 + ", ",
        "pin: {<<: {caselist: hsld26, source_sha256: " + SOURCE_1 + "}, ",
    )
    assert file_recipes.recipe_hash(load_ok(merged_inline)) == file_recipes.recipe_hash(load_ok(with_pin))


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("tag_override: Coach tag", "tag_override: Coach tag, revised"),
        ("            tag_override: Coach tag\n", ""),
        ("analytic: Coach words", "analytic: Other words"),
        ("a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0", "b1" * 32),
        ("block: B", "block: Another block"),
        ("title: T", "title: Another title"),
        ("side: NEG", "side: AFF"),
        ("fingerprint_version: card-fingerprint-v3", "fingerprint_version: card-fingerprint-v2"),
    ],
    ids=[
        "tag-override-edited",
        "tag-override-removed",
        "analytic",
        "card",
        "block-title",
        "title",
        "side",
        "version",
    ],
)
def test_the_hash_changes_with_what_the_file_holds(old: str, new: str) -> None:
    assert old in TINY
    assert file_recipes.recipe_hash(load_ok(TINY.replace(old, new))) != file_recipes.recipe_hash(
        load_ok(TINY)
    )


def test_the_hash_changes_when_items_are_reordered() -> None:
    card_item = (
        "          - fingerprint: a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0a0\n"
        "            tag_override: Coach tag\n"
    )
    analytic_item = "          - analytic: Coach words\n"
    reordered = TINY.replace(card_item + analytic_item, analytic_item + card_item)
    assert reordered != TINY
    assert file_recipes.recipe_hash(load_ok(reordered)) != file_recipes.recipe_hash(load_ok(TINY))


def test_the_hash_changes_when_a_pin_is_added() -> None:
    plain = recipe_text(card(CARD_A))
    pinned = recipe_text(
        card(CARD_A, pin={"caselist": "hsld26", "source_sha256": SOURCE_1, "element_index": 0})
    )
    assert file_recipes.recipe_hash(load_ok(plain)) != file_recipes.recipe_hash(load_ok(pinned))


def test_the_hash_ignores_whitespace_the_model_strips() -> None:
    assert file_recipes.recipe_hash(
        load_ok(TINY.replace("title: T", "title: '  T  '"))
    ) == file_recipes.recipe_hash(load_ok(TINY))


# ------------------------------------------------------------------------------------------------
# resolve: an in-memory occurrence store, caselist records and suppression list
# ------------------------------------------------------------------------------------------------


def path_of(
    source: str, team_code: str = "QX", round_raw: str = "Round 4", school: str = "Maple Grove"
) -> str:
    return (
        f"{school}/{team_code}/{school}-{team_code}-Neg-Invented Invitational-{round_raw}-{source[:4]}.docx"
    )


def occurrence(
    fingerprint: str,
    source: str,
    element: int,
    *,
    path: str | None = None,
    first: str = "2026-09-01",
    last: str = "2026-09-08",
    caselist: str = CASELIST,
    version: str = fingerprints.FINGERPRINT_VERSION,
) -> OccurrenceRecord:
    return OccurrenceRecord(
        caselist=caselist,
        snapshot=first,
        last_snapshot=last,
        source_sha256=source,
        parser_version=PARSER,
        profile_version=PROFILE,
        fingerprint_version=version,
        disclosure=disclosure_digest(caselist, path or path_of(source)),
        first_element_index=element,
        last_element_index=element + 2,
        exact_fingerprint=fingerprint,
        cluster_id=fingerprint,
        membership=ClusterMembership.NEAR_DUPLICATE,
        completeness=CardCompleteness.FULL,
    )


def disclosure(
    source: str,
    *,
    snapshot: str = "2026-09-08",
    school: str = "Maple Grove",
    team_code: str = "QX",
    round_raw: str = "Round 4",
    caselist: str = CASELIST,
    path: str | None = None,
) -> Disclosure:
    return Disclosure(
        source_sha256=source,
        caselist=caselist,
        snapshot=date.fromisoformat(snapshot),
        event=Event.LD,
        school=school,
        team_code=team_code,
        side=Side.NEG,
        tournament="Invented Invitational",
        round_label=RoundLabel.from_raw(round_raw),
        source_path=path or path_of(source, team_code, round_raw, school),
    )


def suppress(
    source: str, *, path: str | None = None, caselist: str = CASELIST, at: int = 1
) -> SuppressionEntry:
    """A suppression of the whole source, or with `path` of one disclosure of it."""
    return SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=source,
        disclosure=disclosure_digest(caselist, path) if path is not None else None,
        recorded_at=datetime(2026, 10, at, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-01",
    )


def unsuppress(source: str, *, at: int) -> SuppressionEntry:
    return SuppressionEntry(
        action=SuppressionAction.UNSUPPRESS,
        sha256=source,
        recorded_at=datetime(2026, 10, at, tzinfo=UTC),
        reason=ReasonCode.REMOVED_IN_ERROR,
    )


@dataclass
class World:
    """The three ports a resolver reads, in memory."""

    store: InMemoryParsedStore = field(default_factory=InMemoryParsedStore)
    caselists: InMemoryCaselistRepository = field(default_factory=InMemoryCaselistRepository)
    suppression_record: InMemoryAppendOnlyRecord = field(default_factory=InMemoryAppendOnlyRecord)

    def resolver(self) -> file_recipes.RecipeResolver:
        return file_recipes.RecipeResolver(
            parsed_store=self.store,
            caselists=self.caselists,
            suppression=RecordedSuppressionList(self.suppression_record),
            parser_version=PARSER,
        )

    def resolve(self, text: str) -> file_recipes.ResolvedRecipe:
        loaded = file_recipes.load_recipe(text)
        assert loaded.errors == ()
        assert loaded.recipe is not None
        return asyncio.run(self.resolver().resolve(loaded.recipe, lines=loaded.lines))


def world(
    rows: Sequence[OccurrenceRecord],
    disclosures: Sequence[Disclosure] = (),
    suppressions: Sequence[SuppressionEntry] = (),
    *,
    caselist: str = CASELIST,
    version: str = PARSER,
) -> World:
    built = World()
    asyncio.run(built.store.write_aggregates(caselist, version, index=(), failures=(), occurrences=rows))
    for one in disclosures:
        asyncio.run(built.caselists.record_disclosure(one))
    built.suppression_record.lines.extend(entry.to_line() for entry in suppressions)
    return built


def chosen(resolved: file_recipes.ResolvedRecipe) -> list[tuple[str, int, str]]:
    """(source, element index, resolution) of every resolved card, in recipe order."""
    return [
        (card.occurrence.source_sha256, card.occurrence.first_element_index, str(card.resolution))
        for card in resolved.cards
    ]


def codes(resolved: file_recipes.ResolvedRecipe) -> list[tuple[str, str]]:
    return [(str(error.code), error.path) for error in resolved.errors]


ITEM = "structure[0].blocks[0].items[0]"


def test_resolve_takes_the_occurrence_seen_in_the_latest_snapshot() -> None:
    rows = [
        occurrence(CARD_A, SOURCE_1, 5, last="2026-09-29"),
        occurrence(CARD_A, SOURCE_2, 9, last="2026-10-06"),
        occurrence(CARD_A, SOURCE_3, 2, last="2026-09-15"),
    ]
    resolved = world(rows).resolve(recipe_text(card(CARD_A)))
    assert resolved.errors == ()
    assert chosen(resolved) == [(SOURCE_2, 9, "AUTO")]


def test_resolve_breaks_a_tie_in_one_snapshot_by_the_lowest_source_sha256() -> None:
    # Two files, both last seen on 2026-10-06; the higher digest is first in the store.
    rows = [
        occurrence(CARD_A, SOURCE_3, 1, last="2026-10-06"),
        occurrence(CARD_A, SOURCE_2, 7, last="2026-10-06"),
    ]
    assert chosen(world(rows).resolve(recipe_text(card(CARD_A)))) == [(SOURCE_2, 7, "AUTO")]


def test_resolve_breaks_a_tie_in_one_file_by_the_lowest_element_index() -> None:
    rows = [
        occurrence(CARD_A, SOURCE_2, 30, last="2026-10-06"),
        occurrence(CARD_A, SOURCE_2, 4, last="2026-10-06"),
    ]
    assert chosen(world(rows).resolve(recipe_text(card(CARD_A)))) == [(SOURCE_2, 4, "AUTO")]


def test_resolve_breaks_a_tie_between_two_disclosures_of_one_file_by_the_disclosure_digest() -> None:
    first_path, second_path = path_of(SOURCE_2, "QX"), path_of(SOURCE_2, "ZaLu", school="Cedar Hollow")
    rows = [
        occurrence(CARD_A, SOURCE_2, 4, path=first_path, last="2026-10-06"),
        occurrence(CARD_A, SOURCE_2, 4, path=second_path, last="2026-10-06"),
    ]
    lower = min(disclosure_digest(CASELIST, first_path), disclosure_digest(CASELIST, second_path))
    for order in (rows, rows[::-1]):
        resolved = world(order).resolve(recipe_text(card(CARD_A)))
        assert [card.occurrence.disclosure for card in resolved.cards] == [lower]


def test_resolve_does_not_depend_on_the_order_of_the_store() -> None:
    rows = [
        occurrence(CARD_A, source, element, last=last)
        for source in (SOURCE_1, SOURCE_2, SOURCE_3)
        for element, last in ((3, "2026-10-06"), (8, "2026-10-06"), (1, "2026-09-29"))
    ]
    expected = [(SOURCE_1, 3, "AUTO")]
    generator = random.Random(20261018)
    for _ in range(5):
        shuffled = list(rows)
        generator.shuffle(shuffled)
        assert chosen(world(shuffled).resolve(recipe_text(card(CARD_A)))) == expected


def test_resolve_a_pin_that_matches_one_occurrence_is_pinned_where_auto_would_choose_another() -> None:
    rows = [
        occurrence(CARD_A, SOURCE_1, 5, last="2026-09-15"),
        occurrence(CARD_A, SOURCE_2, 9, last="2026-10-06"),
    ]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5, "team_code": "QX"}
    resolved = world(rows, [disclosure(SOURCE_1)]).resolve(recipe_text(card(CARD_A, pin=pin), card(CARD_B)))
    assert chosen(resolved) == [(SOURCE_1, 5, "PINNED")]
    assert codes(resolved) == [("UNKNOWN_CARD", "structure[0].blocks[0].items[1].fingerprint")]


@pytest.mark.parametrize(
    ("narrowing", "matches"),
    [
        ({}, True),
        ({"snapshot": "2026-09-01"}, True),
        ({"snapshot": "2026-09-08"}, True),
        ({"snapshot": "2026-09-04"}, True),
        ({"snapshot": "2026-08-31"}, False),
        ({"snapshot": "2026-09-09"}, False),
        ({"school": "Maple Grove", "team_code": "QX", "side": "NEG"}, True),
        ({"team_code": "ZaLu"}, False),
        ({"school": "Cedar Hollow"}, False),
        ({"side": "AFF"}, False),
        ({"tournament": "Invented Invitational", "round": "Round 4"}, True),
        ({"tournament": "Another Invitational"}, False),
        ({"round": "Round 5"}, False),
        ({"round": "round 4"}, False),
    ],
)
def test_resolve_a_pin_matches_on_every_field_it_names(narrowing: dict[str, object], matches: bool) -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5, first="2026-09-01", last="2026-09-08")]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5, **narrowing}
    resolved = world(rows, [disclosure(SOURCE_1)]).resolve(recipe_text(card(CARD_A, pin=pin)))
    if matches:
        assert (chosen(resolved), resolved.errors) == ([(SOURCE_1, 5, "PINNED")], ())
    else:
        assert (chosen(resolved), codes(resolved)) == ([], [("PIN_MISMATCH", f"{ITEM}.pin")])


@pytest.mark.parametrize(
    "pin",
    [
        {"source_sha256": SOURCE_1, "element_index": 6},
        {"source_sha256": SOURCE_2, "element_index": 5},
        {"source_sha256": SOURCE_1, "element_index": 5, "caselist": "hspf26"},
    ],
    ids=["another-paragraph", "another-file", "a-caselist-with-no-store"],
)
def test_resolve_a_pin_to_no_occurrence_fails_with_pin_mismatch(pin: dict[str, object]) -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5)]
    resolved = world(rows, [disclosure(SOURCE_1)]).resolve(
        recipe_text(card(CARD_A, pin={"caselist": CASELIST, **pin}))
    )
    assert (chosen(resolved), codes(resolved)) == ([], [("PIN_MISMATCH", f"{ITEM}.pin")])


def test_resolve_a_pin_to_another_card_fails_with_pin_mismatch() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5), occurrence(CARD_B, SOURCE_1, 9)]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 9}
    resolved = world(rows, [disclosure(SOURCE_1)]).resolve(recipe_text(card(CARD_A, pin=pin)))
    assert codes(resolved) == [("PIN_MISMATCH", f"{ITEM}.pin")]
    assert "another card" in resolved.errors[0].message


def test_resolve_a_pin_two_teams_match_is_refused_until_it_says_which() -> None:
    qx, zalu = path_of(SOURCE_1, "QX"), path_of(SOURCE_1, "ZaLu", school="Cedar Hollow")
    rows = [occurrence(CARD_A, SOURCE_1, 5, path=qx), occurrence(CARD_A, SOURCE_1, 5, path=zalu)]
    disclosures = [
        disclosure(SOURCE_1, path=qx),
        disclosure(SOURCE_1, school="Cedar Hollow", team_code="ZaLu", path=zalu),
    ]
    pin: dict[str, object] = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5}

    ambiguous = world(rows, disclosures).resolve(recipe_text(card(CARD_A, pin=pin)))
    assert codes(ambiguous) == [("PIN_MISMATCH", f"{ITEM}.pin")]
    assert "2 disclosures" in ambiguous.errors[0].message
    assert "QX" not in ambiguous.errors[0].message and "ZaLu" not in ambiguous.errors[0].message

    narrowed = world(rows, disclosures).resolve(recipe_text(card(CARD_A, pin={**pin, "team_code": "ZaLu"})))
    assert [card.occurrence.disclosure for card in narrowed.cards] == [disclosure_digest(CASELIST, zalu)]


def test_resolve_one_team_at_two_paths_is_one_occurrence_not_an_ambiguous_pin() -> None:
    """A re-upload under a browser's `(1)` name is the same occurrence (E31 t04's occurrence key)."""
    original, reupload = path_of(SOURCE_1), path_of(SOURCE_1).replace(".docx", " (1).docx")
    rows = [
        occurrence(CARD_A, SOURCE_1, 5, path=original, last="2026-09-08"),
        occurrence(CARD_A, SOURCE_1, 5, path=reupload, last="2026-09-15"),
    ]
    disclosures = [
        disclosure(SOURCE_1, path=original),
        disclosure(SOURCE_1, path=reupload, snapshot="2026-09-15"),
    ]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5}
    resolved = world(rows, disclosures).resolve(recipe_text(card(CARD_A, pin=pin)))
    assert [card.occurrence.disclosure for card in resolved.cards] == [disclosure_digest(CASELIST, reupload)]


def test_resolve_an_unknown_fingerprint_fails_with_unknown_card() -> None:
    resolved = world([occurrence(CARD_A, SOURCE_1, 5)]).resolve(recipe_text(card(CARD_B)))
    assert (chosen(resolved), codes(resolved)) == ([], [("UNKNOWN_CARD", f"{ITEM}.fingerprint")])


def test_resolve_a_card_known_only_in_another_caselist_is_unknown_here() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5, caselist="hspf26", path="Maple Grove/QX/x.docx")]
    built = world([occurrence(CARD_B, SOURCE_2, 1)])
    asyncio.run(built.store.write_aggregates("hspf26", PARSER, index=(), failures=(), occurrences=rows))
    assert codes(built.resolve(recipe_text(card(CARD_A)))) == [("UNKNOWN_CARD", f"{ITEM}.fingerprint")]


def test_resolve_the_same_fingerprint_twice_is_a_duplicate_ref_for_every_repeat() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5)]
    resolved = world(rows).resolve(
        recipe_text(card(CARD_A), "- analytic: x", card(CARD_A), card(CARD_A, tag="t"))
    )
    assert chosen(resolved) == [(SOURCE_1, 5, "AUTO")]
    assert codes(resolved) == [
        ("DUPLICATE_REF", "structure[0].blocks[0].items[2].fingerprint"),
        ("DUPLICATE_REF", "structure[0].blocks[0].items[3].fingerprint"),
    ]
    assert "items[0]" in resolved.errors[0].message


def test_resolve_collects_every_error_in_the_recipe_with_its_line() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5), occurrence(CARD_C, SOURCE_2, 1)]
    text = recipe_text(
        card(CARD_A, pin={"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 6}),  # line 14
        card(CARD_B),  # line 15
        card(CARD_C),  # line 16
        card(CARD_C),  # line 17
    )
    resolved = world(rows).resolve(text)
    assert chosen(resolved) == [(SOURCE_2, 1, "AUTO")]
    assert [(str(error.code), error.path, error.line) for error in resolved.errors] == [
        ("PIN_MISMATCH", "structure[0].blocks[0].items[0].pin", 14),
        ("UNKNOWN_CARD", "structure[0].blocks[0].items[1].fingerprint", 15),
        ("DUPLICATE_REF", "structure[0].blocks[0].items[3].fingerprint", 17),
    ]


def test_resolve_carries_the_disclosure_for_provenance_and_keeps_it_out_of_repr() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5)]
    resolved = world(rows, [disclosure(SOURCE_1, team_code="QX", round_raw="Round 4")]).resolve(
        recipe_text(card(CARD_A, tag="Coach tag"))
    )
    (resolved_card,) = resolved.cards
    assert resolved_card.disclosure is not None
    assert (resolved_card.disclosure.school, resolved_card.disclosure.team_code) == ("Maple Grove", "QX")
    assert resolved_card.tag_override is not None and resolved_card.tag_override.text == "Coach tag"
    assert resolved_card.path == ITEM
    assert "Maple Grove" not in repr(resolved_card) and "Maple Grove" not in repr(resolved)


def test_resolve_takes_the_latest_disclosure_record_of_the_occurrence() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5, first="2026-09-01", last="2026-09-15")]
    disclosures = [disclosure(SOURCE_1, snapshot=day) for day in ("2026-09-15", "2026-09-01", "2026-09-08")]
    (resolved_card,) = world(rows, disclosures).resolve(recipe_text(card(CARD_A))).cards
    assert resolved_card.disclosure is not None
    assert resolved_card.disclosure.snapshot == date(2026, 9, 15)


def test_resolve_an_occurrence_with_no_disclosure_on_record_resolves_without_one() -> None:
    (resolved_card,) = world([occurrence(CARD_A, SOURCE_1, 5)]).resolve(recipe_text(card(CARD_A))).cards
    assert resolved_card.disclosure is None


def test_resolve_a_pin_naming_a_team_needs_a_disclosure_on_record() -> None:
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5, "team_code": "QX"}
    resolved = world([occurrence(CARD_A, SOURCE_1, 5)]).resolve(recipe_text(card(CARD_A, pin=pin)))
    assert (resolved.ok, codes(resolved)) == (False, [("PIN_MISMATCH", f"{ITEM}.pin")])
    assert "team_code" in resolved.errors[0].message


def test_resolve_reads_every_page_of_a_sources_disclosures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_recipes, "_DISCLOSURE_PAGE", 1)
    others = [disclosure(SOURCE_1, school="Cedar Hollow", team_code=f"Z{n}") for n in range(3)]
    mine = disclosure(SOURCE_1, team_code="QX")
    rows = [occurrence(CARD_A, SOURCE_1, 5, path=mine.source_path)]
    resolved = world(rows, [*others, mine]).resolve(recipe_text(card(CARD_A)))
    assert resolved.ok
    assert [card.disclosure for card in resolved.cards] == [mine]


def test_resolve_ignores_a_disclosure_of_the_same_bytes_at_another_path() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5, path=path_of(SOURCE_1, "QX"))]
    other = disclosure(SOURCE_1, school="Cedar Hollow", team_code="ZaLu")
    (resolved_card,) = world(rows, [other]).resolve(recipe_text(card(CARD_A))).cards
    assert resolved_card.disclosure is None


def test_resolve_reports_the_version_directory_it_read() -> None:
    resolved = world([occurrence(CARD_A, SOURCE_1, 5)]).resolve(recipe_text(card(CARD_A)))
    assert dict(resolved.versions) == {CASELIST: PARSER}
    assert resolved.recipe_hash == file_recipes.recipe_hash(resolved.recipe)


# -- the suppression list (PM amendment 2026-10-18) ----------------------------------------------


def test_resolve_auto_skips_a_source_the_suppression_list_stops_and_takes_the_next() -> None:
    rows = [
        occurrence(CARD_A, SOURCE_1, 5, last="2026-10-06"),
        occurrence(CARD_A, SOURCE_2, 9, last="2026-09-29"),
    ]
    resolved = world(rows, suppressions=[suppress(SOURCE_1)]).resolve(recipe_text(card(CARD_A)))
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_2, 9, "AUTO")], ())


def test_resolve_auto_skips_a_withdrawn_disclosure_and_takes_the_next() -> None:
    withdrawn, kept = path_of(SOURCE_1, "QX"), path_of(SOURCE_1, "ZaLu", school="Cedar Hollow")
    rows = [
        occurrence(CARD_A, SOURCE_1, 5, path=withdrawn, last="2026-10-06"),
        occurrence(CARD_A, SOURCE_1, 5, path=kept, last="2026-09-29"),
    ]
    resolved = world(rows, suppressions=[suppress(SOURCE_1, path=withdrawn)]).resolve(
        recipe_text(card(CARD_A))
    )
    assert [card.occurrence.disclosure for card in resolved.cards] == [disclosure_digest(CASELIST, kept)]


def test_resolve_auto_with_every_occurrence_stopped_reports_suppressed_occurrence() -> None:
    withdrawn = path_of(SOURCE_2)
    rows = [occurrence(CARD_A, SOURCE_1, 5), occurrence(CARD_A, SOURCE_2, 9, path=withdrawn)]
    suppressions = [suppress(SOURCE_1), suppress(SOURCE_2, path=withdrawn)]
    resolved = world(rows, suppressions=suppressions).resolve(recipe_text(card(CARD_A)))
    assert (chosen(resolved), codes(resolved)) == ([], [("SUPPRESSED_OCCURRENCE", f"{ITEM}.fingerprint")])


def test_resolve_a_pin_to_a_suppressed_source_is_refused_not_repointed() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5), occurrence(CARD_A, SOURCE_2, 9)]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5}
    resolved = world(rows, suppressions=[suppress(SOURCE_1)]).resolve(recipe_text(card(CARD_A, pin=pin)))
    assert (chosen(resolved), codes(resolved)) == ([], [("SUPPRESSED_OCCURRENCE", f"{ITEM}.pin")])


def test_resolve_a_pin_to_a_withdrawn_disclosure_is_refused() -> None:
    withdrawn, kept = path_of(SOURCE_1, "QX"), path_of(SOURCE_1, "ZaLu", school="Cedar Hollow")
    rows = [occurrence(CARD_A, SOURCE_1, 5, path=withdrawn), occurrence(CARD_A, SOURCE_1, 5, path=kept)]
    disclosures = [
        disclosure(SOURCE_1, path=withdrawn),
        disclosure(SOURCE_1, school="Cedar Hollow", team_code="ZaLu", path=kept),
    ]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5, "team_code": "QX"}
    resolved = world(rows, disclosures, [suppress(SOURCE_1, path=withdrawn)]).resolve(
        recipe_text(card(CARD_A, pin=pin))
    )
    assert (chosen(resolved), codes(resolved)) == ([], [("SUPPRESSED_OCCURRENCE", f"{ITEM}.pin")])


def test_resolve_a_pin_to_a_removed_source_the_store_no_longer_holds_is_refused_as_suppressed() -> None:
    """After `caselist parse` rebuilds the store, a removed source has no row left to match."""
    rows = [occurrence(CARD_A, SOURCE_2, 9)]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5}
    resolved = world(rows, suppressions=[suppress(SOURCE_1)]).resolve(recipe_text(card(CARD_A, pin=pin)))
    assert (chosen(resolved), codes(resolved)) == ([], [("SUPPRESSED_OCCURRENCE", f"{ITEM}.pin")])


def test_resolve_a_source_suppressed_and_then_restored_resolves_again() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5)]
    resolved = world(rows, suppressions=[suppress(SOURCE_1, at=1), unsuppress(SOURCE_1, at=2)]).resolve(
        recipe_text(card(CARD_A))
    )
    assert chosen(resolved) == [(SOURCE_1, 5, "AUTO")]


def test_resolve_messages_name_no_school_team_or_path() -> None:
    withdrawn = path_of(SOURCE_1)
    rows = [occurrence(CARD_A, SOURCE_1, 5, path=withdrawn)]
    pin = {
        "caselist": CASELIST,
        "source_sha256": SOURCE_1,
        "element_index": 5,
        "team_code": "QX",
        "school": "Maple Grove",
    }
    text = recipe_text(card(CARD_A, pin=pin), card(CARD_B, pin={**pin, "element_index": 7}))
    resolved = world(
        rows, [disclosure(SOURCE_1, path=withdrawn)], [suppress(SOURCE_1, path=withdrawn)]
    ).resolve(text)
    assert len(resolved.errors) == 2
    for error in resolved.errors:
        assert not re.search(r"Maple|Grove|QX|Invented|\.docx", error.message), error.message


# -- the store itself -----------------------------------------------------------------------------


def test_resolve_without_occurrences_built_says_the_store_is_not_ready() -> None:
    """Between a removal and the next `caselist parse` a version directory has no aggregates."""
    built = World()
    built.store.sources[(CASELIST, PARSER, SOURCE_1)] = (_entry(SOURCE_1), None)
    with pytest.raises(file_recipes.OccurrenceStoreNotReady, match="caselist parse"):
        built.resolve(recipe_text(card(CARD_A)))


def test_resolve_without_a_directory_of_this_parser_version_says_the_store_is_not_ready() -> None:
    built = world([occurrence(CARD_A, SOURCE_1, 5)], version="2026.10.12-docx-3")
    with pytest.raises(file_recipes.OccurrenceStoreNotReady, match=PARSER):
        built.resolve(recipe_text(card(CARD_A)))


def test_resolve_reads_the_newest_generation_of_its_parser_version() -> None:
    built = world([occurrence(CARD_A, SOURCE_1, 5)])
    newer = f"{PARSER}_reparse-2"
    asyncio.run(
        built.store.write_aggregates(
            CASELIST, newer, index=(), failures=(), occurrences=[occurrence(CARD_A, SOURCE_2, 8)]
        )
    )
    resolved = built.resolve(recipe_text(card(CARD_A)))
    assert chosen(resolved) == [(SOURCE_2, 8, "AUTO")]
    assert dict(resolved.versions) == {CASELIST: newer}


def test_resolve_refuses_rows_whose_fingerprint_version_has_other_digests() -> None:
    built = world([occurrence(CARD_A, SOURCE_1, 5, version="card-fingerprint-v9")])
    with pytest.raises(file_recipes.OccurrenceStoreNotReady, match="card-fingerprint-v9"):
        built.resolve(recipe_text(card(CARD_A)))


def test_resolve_takes_rows_of_every_version_with_todays_digests() -> None:
    rows = [occurrence(CARD_A, SOURCE_1, 5, version="card-fingerprint-v1")]
    assert chosen(world(rows).resolve(recipe_text(card(CARD_A)))) == [(SOURCE_1, 5, "AUTO")]


def test_resolve_a_pin_reads_the_store_of_the_caselist_it_names() -> None:
    built = world([occurrence(CARD_B, SOURCE_2, 1)])
    other = [occurrence(CARD_A, SOURCE_1, 5, caselist="hsld25", path="Maple Grove/QX/old.docx")]
    asyncio.run(built.store.write_aggregates("hsld25", PARSER, index=(), failures=(), occurrences=other))
    pin = {"caselist": "hsld25", "source_sha256": SOURCE_1, "element_index": 5}
    resolved = built.resolve(recipe_text(card(CARD_A, pin=pin)))
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_1, 5, "PINNED")], ())
    assert dict(resolved.versions) == {CASELIST: PARSER, "hsld25": PARSER}


def test_resolve_refuses_a_recipe_whose_fingerprint_version_has_other_digests() -> None:
    recipe = load_ok(recipe_text(card(CARD_A))).evolve(fingerprint_version="card-fingerprint-v9")
    resolved = asyncio.run(world([occurrence(CARD_A, SOURCE_1, 5)]).resolver().resolve(recipe))
    assert (chosen(resolved), codes(resolved)) == ([], [("INVALID", "fingerprint_version")])


def test_resolve_needs_no_model_and_no_network() -> None:
    """The task's second forbidden item, held by what the module can reach."""
    source = Path(file_recipes.__file__).read_text(encoding="utf-8")
    for forbidden in ("model_router", "ModelRouter", "httpx", "boto3", "urllib", "socket"):
        assert forbidden not in source


# -- camp (OpenEv) cards, `v1-e33-t06` -----------------------------------------------------------

OPENEV = "openev"
CAMP = "Lanternfield Institute"
CAMP_HEADER = HEADER.replace("caselist: hsld26", "caselist: openev")


def camp_occurrence(
    fingerprint: str, source: str, element: int, *, release: str = "2031-policy", camp: str | None = CAMP
) -> OccurrenceRecord:
    """A camp file's card as the parse pipeline records it: one row per release, no disclosure."""
    return OccurrenceRecord(
        caselist=OPENEV,
        snapshot=release,
        last_snapshot=release,
        source_sha256=source,
        parser_version=PARSER,
        profile_version=PROFILE,
        fingerprint_version=fingerprints.FINGERPRINT_VERSION,
        disclosure=None,
        camp=camp,
        first_element_index=element,
        last_element_index=element + 2,
        exact_fingerprint=fingerprint,
        cluster_id=fingerprint,
        membership=ClusterMembership.UNLINKED,
        completeness=CardCompleteness.FULL,
    )


def camp_file(
    source: str, *, year: int = 2031, event: Event = Event.POLICY, title: str = "Synthetic CP"
) -> CampFile:
    """What the OpenEv importer records for the release: invented camp, title and year."""
    return CampFile(
        source_sha256=source, camp=CAMP, year=year, event=event, file_title=title, snapshot=date(2026, 7, 30)
    )


def camp_world(
    camp_rows: Sequence[OccurrenceRecord],
    camp_files: Sequence[CampFile] = (),
    suppressions: Sequence[SuppressionEntry] = (),
    *,
    caselist_rows: Sequence[OccurrenceRecord] = (),
) -> World:
    """The recipe's caselist store (`caselist_rows`) and the openev store (`camp_rows`)."""
    built = world(caselist_rows, suppressions=suppressions)
    asyncio.run(built.store.write_aggregates(OPENEV, PARSER, index=(), failures=(), occurrences=camp_rows))
    for one in camp_files:
        asyncio.run(built.caselists.record_camp_file(one))
    return built


CAMP_PIN: dict[str, object] = {
    "caselist": OPENEV,
    "source_sha256": SOURCE_1,
    "element_index": 5,
    "snapshot": "2031-policy",
}


def test_resolve_a_camp_pin_naming_its_release_resolves_to_that_camp_occurrence() -> None:
    built = camp_world(
        [camp_occurrence(CARD_A, SOURCE_1, 5)],
        [camp_file(SOURCE_1)],
        caselist_rows=[occurrence(CARD_B, SOURCE_2, 1)],
    )
    resolved = built.resolve(recipe_text(card(CARD_A, pin=CAMP_PIN), card(CARD_B)))
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_1, 5, "PINNED"), (SOURCE_2, 1, "AUTO")], ())
    camp_card = resolved.cards[0]
    assert (camp_card.occurrence.caselist, camp_card.occurrence.snapshot, camp_card.occurrence.camp) == (
        OPENEV,
        "2031-policy",
        CAMP,
    )
    assert camp_card.disclosure is None
    assert camp_card.camp_file == camp_file(SOURCE_1)
    assert dict(resolved.versions) == {CASELIST: PARSER, OPENEV: PARSER}


def test_resolve_a_camp_pin_takes_the_release_it_names_when_the_file_is_in_two() -> None:
    rows = [
        camp_occurrence(CARD_A, SOURCE_1, 5, release="2030-policy"),
        camp_occurrence(CARD_A, SOURCE_1, 5, release="2031-policy"),
    ]
    files = [camp_file(SOURCE_1, year=2030, title="Earlier title"), camp_file(SOURCE_1, title="Later title")]
    for release, title in (("2030-policy", "Earlier title"), ("2031-policy", "Later title")):
        pin = {**CAMP_PIN, "snapshot": release}
        resolved = camp_world(rows, files).resolve(recipe_text(card(CARD_A, pin=pin)))
        (camp_card,) = resolved.cards
        assert camp_card.occurrence.snapshot == release
        assert camp_card.camp_file is not None and camp_card.camp_file.file_title == title


@pytest.mark.parametrize(
    "pin",
    [
        {**CAMP_PIN, "snapshot": "2030-policy"},
        {**CAMP_PIN, "snapshot": "2031-ld"},
        {**CAMP_PIN, "element_index": 6},
        {**CAMP_PIN, "source_sha256": SOURCE_2},
    ],
    ids=["another-year", "another-event", "another-paragraph", "another-file"],
)
def test_resolve_a_camp_pin_that_matches_no_camp_occurrence_is_a_pin_mismatch(pin: dict[str, object]) -> None:
    resolved = camp_world([camp_occurrence(CARD_A, SOURCE_1, 5)]).resolve(recipe_text(card(CARD_A, pin=pin)))
    assert (chosen(resolved), codes(resolved)) == ([], [("PIN_MISMATCH", f"{ITEM}.pin")])


def test_resolve_a_camp_pin_needs_the_openev_store() -> None:
    resolved = world([occurrence(CARD_B, SOURCE_2, 1)]).resolve(recipe_text(card(CARD_A, pin=CAMP_PIN)))
    assert codes(resolved) == [("PIN_MISMATCH", f"{ITEM}.pin")]
    assert "openev" in resolved.errors[0].message


def test_resolve_a_camp_pin_to_a_suppressed_camp_file_is_refused_not_repointed() -> None:
    rows = [camp_occurrence(CARD_A, SOURCE_1, 5), camp_occurrence(CARD_A, SOURCE_2, 9)]
    resolved = camp_world(rows, suppressions=[suppress(SOURCE_1)]).resolve(
        recipe_text(card(CARD_A, pin=CAMP_PIN))
    )
    assert (chosen(resolved), codes(resolved)) == ([], [("SUPPRESSED_OCCURRENCE", f"{ITEM}.pin")])


def test_resolve_a_camp_pin_is_not_stopped_by_a_teams_withdrawn_disclosure_of_the_same_bytes() -> None:
    """A withdrawal of one team's disclosure stops that disclosure, not the camp's release of the file."""
    withdrawn = path_of(SOURCE_1)
    rows = [camp_occurrence(CARD_A, SOURCE_1, 5)]
    resolved = camp_world(rows, suppressions=[suppress(SOURCE_1, path=withdrawn)]).resolve(
        recipe_text(card(CARD_A, pin=CAMP_PIN))
    )
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_1, 5, "PINNED")], ())


def test_resolve_a_camp_occurrence_with_no_release_record_resolves_without_one() -> None:
    other_release = camp_file(SOURCE_1, year=2030)
    resolved = camp_world([camp_occurrence(CARD_A, SOURCE_1, 5)], [other_release]).resolve(
        recipe_text(card(CARD_A, pin=CAMP_PIN))
    )
    (camp_card,) = resolved.cards
    assert camp_card.camp_file is None


def test_resolve_auto_in_a_camp_recipe_takes_the_latest_release() -> None:
    rows = [
        camp_occurrence(CARD_A, SOURCE_1, 5, release="2030-policy"),
        camp_occurrence(CARD_A, SOURCE_3, 2, release="2031-policy"),
        camp_occurrence(CARD_A, SOURCE_2, 9, release="2029-policy"),
    ]
    built = camp_world(rows, [camp_file(SOURCE_3)])
    asyncio.run(built.store.write_aggregates(CASELIST, PARSER, index=(), failures=(), occurrences=()))
    resolved = built.resolve(recipe_text(card(CARD_A), header=CAMP_HEADER))
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_3, 2, "AUTO")], ())
    assert resolved.cards[0].camp_file == camp_file(SOURCE_3)


def test_resolve_auto_breaks_a_tie_in_one_camp_year_by_the_release_then_the_lowest_source() -> None:
    rows = [
        camp_occurrence(CARD_A, SOURCE_3, 1, release="2031-policy"),
        camp_occurrence(CARD_A, SOURCE_2, 7, release="2031-policy"),
        camp_occurrence(CARD_A, SOURCE_1, 4, release="2031-pf"),
    ]
    for order in (rows, rows[::-1]):
        resolved = camp_world(order).resolve(recipe_text(card(CARD_A), header=CAMP_HEADER))
        assert chosen(resolved) == [(SOURCE_1, 4, "AUTO")], "2031-pf before 2031-policy, by name"
    resolved = camp_world(rows[:2]).resolve(recipe_text(card(CARD_A), header=CAMP_HEADER))
    assert chosen(resolved) == [(SOURCE_2, 7, "AUTO")]


def test_resolve_auto_never_picks_a_suppressed_camp_occurrence() -> None:
    rows = [
        camp_occurrence(CARD_A, SOURCE_1, 5, release="2031-policy"),
        camp_occurrence(CARD_A, SOURCE_2, 9, release="2030-policy"),
    ]
    skipped = camp_world(rows, suppressions=[suppress(SOURCE_1)]).resolve(
        recipe_text(card(CARD_A), header=CAMP_HEADER)
    )
    assert (chosen(skipped), skipped.errors) == ([(SOURCE_2, 9, "AUTO")], ())

    stopped = camp_world(rows, suppressions=[suppress(SOURCE_1), suppress(SOURCE_2)]).resolve(
        recipe_text(card(CARD_A), header=CAMP_HEADER)
    )
    assert (chosen(stopped), codes(stopped)) == ([], [("SUPPRESSED_OCCURRENCE", f"{ITEM}.fingerprint")])


def test_resolve_auto_in_a_caselist_recipe_never_reaches_a_camp_occurrence() -> None:
    """AUTO reads only the recipe's own store: a camp card enters a caselist recipe by a pin."""
    built = camp_world(
        [camp_occurrence(CARD_A, SOURCE_1, 5)], caselist_rows=[occurrence(CARD_B, SOURCE_2, 1)]
    )
    resolved = built.resolve(recipe_text(card(CARD_A)))
    assert codes(resolved) == [("UNKNOWN_CARD", f"{ITEM}.fingerprint")]


def test_resolve_a_caselist_pin_in_a_camp_recipe_reads_the_caselist_it_names() -> None:
    built = camp_world(
        [camp_occurrence(CARD_B, SOURCE_2, 1)], caselist_rows=[occurrence(CARD_A, SOURCE_1, 5)]
    )
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5}
    resolved = built.resolve(recipe_text(card(CARD_A, pin=pin), card(CARD_B), header=CAMP_HEADER))
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_1, 5, "PINNED"), (SOURCE_2, 1, "AUTO")], ())


def test_resolve_camp_messages_name_no_camp_or_file_title() -> None:
    rows = [camp_occurrence(CARD_A, SOURCE_1, 5)]
    text = recipe_text(card(CARD_A, pin=CAMP_PIN), card(CARD_B, pin={**CAMP_PIN, "element_index": 7}))
    resolved = camp_world(rows, [camp_file(SOURCE_1)], [suppress(SOURCE_1)]).resolve(text)
    assert len(resolved.errors) == 2
    for error in resolved.errors:
        assert not re.search(r"Lanternfield|Synthetic CP", error.message), error.message


def _entry(source: str) -> Any:
    from debate_core.application.ports.parsed_store import SourceEntry, SourceOutcome
    from debate_core.domain.caselist import SourceFormat

    return SourceEntry(
        caselist=CASELIST,
        snapshot="2026-09-01",
        source_sha256=source,
        parser_version=PARSER,
        profile_version=PROFILE,
        fingerprint_version=fingerprints.FINGERPRINT_VERSION,
        source_format=SourceFormat.DOCX,
        byte_size=10,
        outcome=SourceOutcome.PARSED,
        cards=1,
    )


# ------------------------------------------------------------------------------------------------
# examples
# ------------------------------------------------------------------------------------------------

EXAMPLE_NAMES = (
    "policy-nhi-politics-da-answers.yaml",
    "ld-space-colonization-nc.yaml",
    "pf-data-center-moratorium-con-blocks.yaml",
)
SYNTHETIC_SCHOOLS = {"Maple Grove", "Cedar Hollow"}
SYNTHETIC_TEAM_CODES = {"QX", "ZaLu", "AB"}


def test_examples_are_the_three_the_spec_names_and_cover_every_format() -> None:
    assert sorted(path.name for path in EXAMPLES.glob("*.yaml")) == sorted(EXAMPLE_NAMES)
    formats = {load_ok((EXAMPLES / name).read_text(encoding="utf-8")).format for name in EXAMPLE_NAMES}
    assert formats == {Event.POLICY, Event.LD, Event.PF}


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_examples_load_and_validate(name: str) -> None:
    recipe = load_ok((EXAMPLES / name).read_text(encoding="utf-8"))
    assert any(ref.pin is not None for _, ref in recipe.card_refs())
    assert any(ref.pin is None for _, ref in recipe.card_refs())
    assert any(ref.tag_override is not None for _, ref in recipe.card_refs())


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_examples_validate_against_the_published_schema(name: str) -> None:
    data = yaml.safe_load((EXAMPLES / name).read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(json.loads(json.dumps(data, default=str)), schema)


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_examples_use_only_synthetic_schools_and_team_codes(name: str) -> None:
    recipe = load_ok((EXAMPLES / name).read_text(encoding="utf-8"))
    pins = [ref.pin for _, ref in recipe.card_refs() if ref.pin is not None]
    assert {pin.school for pin in pins if pin.school is not None} <= SYNTHETIC_SCHOOLS
    assert {pin.team_code for pin in pins if pin.team_code is not None} <= SYNTHETIC_TEAM_CODES


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_examples_resolve_against_a_synthetic_store(name: str) -> None:
    recipe = load_ok((EXAMPLES / name).read_text(encoding="utf-8"))
    rows: list[OccurrenceRecord] = []
    disclosures: list[Disclosure] = []
    for number, (_, ref) in enumerate(recipe.card_refs()):
        pin = ref.pin
        if pin is None:
            source = hashlib.sha256(f"auto source {number}".encode()).hexdigest()
            rows.append(
                occurrence(
                    ref.fingerprint, source, number, caselist=recipe.caselist, path=f"S/T/{number}.docx"
                )
            )
            continue
        school, team = pin.school or "Maple Grove", pin.team_code or "QX"
        round_raw = pin.round or "Round 1"
        day = pin.snapshot.isoformat() if isinstance(pin.snapshot, date) else "2026-09-08"
        path = path_of(pin.source_sha256, team, round_raw, school)
        rows.append(
            occurrence(
                ref.fingerprint,
                pin.source_sha256,
                pin.element_index,
                path=path,
                first=day,
                last=day,
                caselist=pin.caselist,
            )
        )
        disclosures.append(
            disclosure(
                pin.source_sha256,
                snapshot=day,
                school=school,
                team_code=team,
                round_raw=round_raw,
                caselist=pin.caselist,
                path=path,
            )
        )
    built = World()
    for caselist in {row.caselist for row in rows}:
        mine = [row for row in rows if row.caselist == caselist]
        asyncio.run(built.store.write_aggregates(caselist, PARSER, index=(), failures=(), occurrences=mine))
    for one in disclosures:
        asyncio.run(
            built.caselists.record_disclosure(
                one.model_copy(update={"event": recipe.format, "side": _side(one, recipe)})
            )
        )
    resolved = asyncio.run(built.resolver().resolve(recipe))
    assert resolved.errors == ()
    assert len(resolved.cards) == len(list(recipe.card_refs()))
    assert {card.resolution for card in resolved.cards} == {
        file_recipes.Resolution.PINNED,
        file_recipes.Resolution.AUTO,
    }


def _side(one: Disclosure, recipe: FileRecipe) -> Side:
    pins = [
        ref.pin
        for _, ref in recipe.card_refs()
        if ref.pin is not None and ref.pin.source_sha256 == one.source_sha256
    ]
    for pin in pins:
        if pin.side is not None:
            return pin.side
    return Side.CON if recipe.format is Event.PF else Side.NEG


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_examples_are_each_walked_through_in_the_guide(name: str) -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    assert (EXAMPLES / name).read_text(encoding="utf-8") in guide
