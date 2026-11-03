"""The fixture key: one call, one key, on every run and platform and in any dict order (ac2).

The golden digests below were not produced by this code. Each canonical text was written by hand
and hashed with `printf '%s' '<text>' | shasum -a 256` (working agreement 6), so a change to how
the key is built fails here rather than quietly re-keying every committed fixture.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import unicodedata
from typing import cast

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, JsonValue

from debate_core.domain.model_contracts import ModelParams, ModelPrompt, ModelRequest, TaskClass
from debate_core.integrations.models.fixture_key import (
    FIXTURE_KEY_LENGTH,
    canonical_json,
    embedding_key,
    fixture_key,
    rerank_key,
)

PROPERTY_SETTINGS = settings(
    max_examples=int(os.environ.get("FIXTURE_KEY_PROPERTY_EXAMPLES", "200")),
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

GOLDEN_SCHEMA = "example.schemas.Passage"


def request(
    variables: dict[str, JsonValue],
    *,
    prompt_id: str = "golden.select-passage",
    prompt_version: str = "1.2.0",
    schema: str = GOLDEN_SCHEMA,
    task_class: TaskClass = TaskClass.HIGH_VOLUME,
    params: ModelParams | None = None,
) -> ModelRequest:
    return ModelRequest(
        task_class=task_class,
        prompt=ModelPrompt(prompt_id=prompt_id, prompt_version=prompt_version, variables=variables),
        output_schema=schema,
        params=params or ModelParams(),
    )


# ---------------------------------------------------------------------------------------------
# Golden keys, hashed by hand
# ---------------------------------------------------------------------------------------------


def test_the_key_is_the_sha256_of_the_hand_written_canonical_text() -> None:
    # {"inputs":{"paragraphs":[1,2],"tag":"Warming kills"},"prompt_id":"golden.select-passage",
    #  "prompt_version":"1.2.0","schema":"example.schemas.Passage"}
    key = fixture_key(request({"tag": "Warming kills", "paragraphs": [1, 2]}))

    assert key == "258e91587822684e1fc6c842b21b9f0c938bc2327f356056d965d3d8bed47ae7"


def test_unicode_is_hashed_as_utf_8_without_escapes() -> None:
    # {"inputs":{"tag":"Café ☕ 𝄞"},"prompt_id":"golden.unicode","prompt_version":"1.0.0",
    #  "schema":"example.schemas.Passage"}, with é as the one code point U+00E9.
    key = fixture_key(
        request({"tag": "Café ☕ \U0001d11e"}, prompt_id="golden.unicode", prompt_version="1.0.0")
    )

    assert key == "9601c2c7acce1f3529782ce43a1216c07f08200865479220ae3d22c35cd6660a"


def test_embedding_and_rerank_keys_are_hashed_the_same_way() -> None:
    # {"call":"embed","texts":["one","two"]} and {"call":"rerank","documents":["a","b"],"query":"q"}
    assert embedding_key(["one", "two"]) == "037ca413879a604ee51f8754721bfcc13122f4a60cb89e4d9c888942ada2183b"
    assert rerank_key("q", ["a", "b"]) == "426f1385f249a6030eea142e0a7cb7ecc0d884fdb1844cc2363273500b5a7208"


@pytest.mark.parametrize("hash_seed", ["0", "4242"])
def test_the_key_does_not_depend_on_the_process(hash_seed: str) -> None:
    """A fresh interpreter, with another string-hash seed, computes the golden key."""
    program = (
        "from debate_core.domain.model_contracts import ModelPrompt, ModelRequest, TaskClass\n"
        "from debate_core.integrations.models.fixture_key import fixture_key\n"
        "prompt = ModelPrompt(prompt_id='golden.select-passage', prompt_version='1.2.0',\n"
        "                     variables={'paragraphs': [1, 2], 'tag': 'Warming kills'})\n"
        "print(fixture_key(ModelRequest(task_class=TaskClass.HIGH_VOLUME, prompt=prompt,\n"
        "                               output_schema='example.schemas.Passage')))\n"
    )
    environment = {**os.environ, "PYTHONHASHSEED": hash_seed}
    result = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, env=environment, check=True
    )

    assert result.stdout.strip() == "258e91587822684e1fc6c842b21b9f0c938bc2327f356056d965d3d8bed47ae7"


# ---------------------------------------------------------------------------------------------
# What the key covers, and what it does not
# ---------------------------------------------------------------------------------------------


BASE_VARIABLES: dict[str, JsonValue] = {"tag": "Warming kills", "paragraphs": [1, 2]}


@pytest.mark.parametrize(
    "changed",
    [
        request(BASE_VARIABLES, prompt_id="golden.select-other-passage"),
        request(BASE_VARIABLES, prompt_version="1.2.1"),
        request({"tag": "Warming kills", "paragraphs": [2, 1]}),
        request({"tag": "Warming kills", "paragraphs": [1, 2], "extra": None}),
        request(BASE_VARIABLES, schema="example.other_schemas.Passage"),
    ],
    ids=["prompt_id", "prompt_version", "list-order", "extra-variable", "schema-module"],
)
def test_each_of_the_four_parts_changes_the_key(changed: ModelRequest) -> None:
    assert fixture_key(changed) != fixture_key(request(BASE_VARIABLES))


def test_two_schemas_with_one_class_name_get_different_keys() -> None:
    first = type("Passage", (BaseModel,), {"__module__": "example.cards", "__annotations__": {"n": int}})
    second = type("Passage", (BaseModel,), {"__module__": "example.audits", "__annotations__": {"n": int}})
    prompt = ModelPrompt(prompt_id="golden.select-passage", prompt_version="1.2.0", variables=BASE_VARIABLES)

    keys = {
        fixture_key(ModelRequest.build(TaskClass.HIGH_VOLUME, prompt, cast(type[BaseModel], schema)))
        for schema in (first, second)
    }

    assert len(keys) == 2


def test_the_task_class_and_parameters_are_not_part_of_the_key() -> None:
    """ac2 names four parts; a replay router compares the rest before serving (test_record_replay)."""
    other = request(
        BASE_VARIABLES,
        task_class=TaskClass.COMPLEX_REASONING,
        params=ModelParams(temperature=0.3, max_tokens=12, timeout_seconds=9),
    )

    assert fixture_key(other) == fixture_key(request(BASE_VARIABLES))


def test_integers_and_floats_are_different_inputs() -> None:
    assert fixture_key(request({"n": 1})) != fixture_key(request({"n": 1.0}))


def test_text_is_not_normalized() -> None:
    composed = unicodedata.normalize("NFC", "café")
    decomposed = unicodedata.normalize("NFD", "café")

    assert fixture_key(request({"tag": composed})) != fixture_key(request({"tag": decomposed}))


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_a_number_json_cannot_carry_is_refused(number: float) -> None:
    with pytest.raises(ValueError, match="NaN or infinite"):
        fixture_key(request({"score": number}))


def test_text_that_is_not_valid_unicode_is_refused() -> None:
    with pytest.raises(ValueError, match="not valid Unicode"):
        fixture_key(request({"tag": "lone \udcff surrogate"}))


# ---------------------------------------------------------------------------------------------
# Properties: dict ordering and unicode
# ---------------------------------------------------------------------------------------------

# Every character Hypothesis can produce except lone surrogates, which the key refuses (above).
TEXT = st.text(st.characters(exclude_categories=["Cs"]), max_size=12)
SCALARS = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False, allow_infinity=False) | TEXT
JSON_VALUES = st.recursive(
    SCALARS,
    lambda children: st.lists(children, max_size=4) | st.dictionaries(TEXT, children, max_size=4),
    max_leaves=16,
)
VARIABLES = st.dictionaries(TEXT, JSON_VALUES, max_size=5)


def reordered(value: JsonValue, rng: random.Random) -> JsonValue:
    """`value` rebuilt with every mapping's keys inserted in a shuffled order, at every depth."""
    if isinstance(value, dict):
        items = list(value.items())
        rng.shuffle(items)
        return {key: reordered(item, rng) for key, item in items}
    if isinstance(value, list):
        return [reordered(item, rng) for item in value]
    return value


def largest_mapping(value: JsonValue, depth: int = 0) -> tuple[int, int]:
    """(keys in the largest mapping anywhere in `value`, the deepest depth a mapping sits at)."""
    if isinstance(value, dict):
        found = [largest_mapping(item, depth + 1) for item in value.values()]
        return max([len(value), *(size for size, _ in found)]), max([depth, *(deep for _, deep in found)])
    if isinstance(value, list):
        found = [largest_mapping(item, depth) for item in value]
        return max([0, *(size for size, _ in found)]), max([0, *(deep for _, deep in found)])
    return 0, 0


@PROPERTY_SETTINGS
@given(variables=VARIABLES, seed=st.integers())
def test_insertion_order_never_changes_the_key(variables: dict[str, JsonValue], seed: int) -> None:
    size, depth = largest_mapping(cast(JsonValue, variables))
    event(f"largest mapping has {min(size, 3)}{'+' if size >= 3 else ''} keys")
    event(f"a mapping is nested {min(depth, 2)}{'+' if depth >= 2 else ''} deep")
    shuffled = cast(dict[str, JsonValue], reordered(variables, random.Random(seed)))

    assert fixture_key(request(shuffled)) == fixture_key(request(variables))


@PROPERTY_SETTINGS
@given(variables=VARIABLES)
def test_the_key_survives_a_round_trip_through_a_cassette(variables: dict[str, JsonValue]) -> None:
    """A request written to a UTF-8 JSON file and read back has the key it was written under."""
    original = request(variables)
    restored = ModelRequest.model_validate_json(original.model_dump_json().encode("utf-8"))

    assert fixture_key(restored) == fixture_key(original)


@PROPERTY_SETTINGS
@given(text=TEXT)
def test_any_unicode_text_gets_a_well_formed_key(text: str) -> None:
    event("non-ASCII text" if any(ord(c) > 127 for c in text) else "ASCII text")
    event("astral-plane text" if any(ord(c) > 0xFFFF for c in text) else "no astral-plane character")
    key = fixture_key(request({"tag": text}))

    assert len(key) == FIXTURE_KEY_LENGTH
    assert set(key) <= set("0123456789abcdef")
    assert json.loads(canonical_json({"tag": text})) == {"tag": text}
