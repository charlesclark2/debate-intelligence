"""The card selection contract: schemas, prompts, the anti-authoring guard and the round trip (v1-e05-t06).

Sections, as the spec's plan selects them: ``-k schema`` (ac1), ``-k prompt`` (ac2), ``-k guard``
(ac3), ``-k round_trip`` (ac4) and ``-k artifact`` (ac5).

Every router is offline: ``ScriptedModelRouter`` for answers a test writes inline, ``FakeModelRouter``
over ``tests/fixtures/model_outputs/`` and ``RecordReplayModelRouter`` in replay mode over
``tests/fixtures/model_cassettes/``, whose ``card.select`` and ``card.markup`` files were written
by hand. Every expected text and offset is worked out by hand from ``SOURCE`` and written down
(`docs/process/working-agreements.md` §6). The source is invented, and not ASCII: curly quotes, em
and en dashes, accented letters and two emoji sit before the offsets that matter.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import unicodedata
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from debate_core.application.card_selection import (
    SELECTION_POLICY,
    SELECTION_TASK_CLASS,
    CardSelector,
)
from debate_core.application.errors import InvalidModelOutput
from debate_core.application.model_errors import ModelOutputError
from debate_core.application.snapshot_service import LoadedSnapshot, SnapshotService
from debate_core.application.structured_output import StructuredOutputGuard, validate_model_output
from debate_core.domain import AccessStatus, CardSpan, ProvenanceMode, SpanPurpose, SpanStyle
from debate_core.domain.model_contracts import ModelPrompt, ModelProvider, TaskClass
from debate_core.domain.provenance import GeneratedArtifactMetadata, SourcedArtifactMetadata
from debate_core.evidence.extractor import EvidenceExtractor
from debate_core.evidence.markup import CardMarkup
from debate_core.evidence.numbered_snapshot import NumberedSnapshot
from debate_core.evidence.selection_contract import (
    ArgumentRole,
    CardSelection,
    GeneratedCardMarkup,
    GeneratedCardSelection,
    MarkupSpan,
    MarkupSuggestion,
    NeedAlignment,
    SelectedPassage,
    TagSuggestion,
)
from debate_core.evidence.selection_guard import (
    QUOTED_RUN_WORDS,
    GuardProblem,
    GuardProblemType,
    SnapshotWords,
    markup_problems,
    selection_problems,
)
from debate_core.integrations.models.fake_router import FakeModelRouter
from debate_core.integrations.models.model_mode import ModelMode
from debate_core.integrations.models.prompt_lock import PromptLock
from debate_core.integrations.models.prompt_registry import PromptRegistry
from debate_core.integrations.models.record_replay import RecordReplayModelRouter
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.model_router import ScriptedModelRouter
from debate_core.testing.fakes.persistence import InMemorySnapshotStore

pytestmark = pytest.mark.anyio

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures"

# ---------------------------------------------------------------------------------------------
# The source. Lengths by hand: P1 109 characters (0-109), P2 127 (111-238), P3 121 (240-361),
# P4 91 (363-454), with a two-character paragraph break before each of P2, P3 and P4.
# ---------------------------------------------------------------------------------------------

P1 = (
    "The Senate’s “clean grid” bill—passed 52–48 on Tuesday—spends political capital the majority "
    "will need later."
)
P2 = (
    "Analysts at the Café Économique institute warn that the fight leaves no room for a budget deal "
    "this spring 🌍 before the recess."
)
P3 = (
    "If the budget deal fails—and “fails” is the word staff use—a shutdown follows within weeks 😬 "
    "and the grid program stalls."
)
P4 = "Violet harbor engines quietly folded seven paper lanterns beneath the northern quarry wall."
SOURCE = "\n\n".join((P1, P2, P3, P4))

SENTINEL = P4.removesuffix(".")
"""Thirteen invented words in the snapshot: a tag that repeats them is refused, and nothing may echo them."""

SENTINEL_WORDS = ("violet", "harbor", "lanterns", "quarry")
"""Words of the sentinel that no message, error, log record or repair problem may contain."""

NEED = "Politics DA link: an energy fight costs the majority the budget"

RECORDED_SELECTION: dict[str, JsonValue] = {
    "passages": [
        {"first_paragraph": 2, "last_paragraph": 2, "start_offset": 52, "end_offset": None},
        {"first_paragraph": 3, "last_paragraph": 3, "start_offset": 59, "end_offset": 120},
    ],
    "tag": {
        "text": "An energy fight leaves no time for a budget, so a shutdown follows",
        "argument_role": "link",
        "need_alignment": "direct",
        "confidence": 0.8,
    },
    "rationale": (
        "Paragraph 2 says the fight crowds out the budget; paragraph 3 says a failed deal brings a shutdown."
    ),
    "confidence": 0.75,
}
"""The answer the committed `card.select` fixture and cassette hold, written by hand."""

RECORDED_MARKUP: dict[str, JsonValue] = {
    "spans": [
        {"paragraph": 2, "start_offset": 62, "end_offset": 126, "style": "underline", "purpose": "claim"},
        {"paragraph": 2, "start_offset": 69, "end_offset": 94, "style": "highlight", "purpose": "claim"},
        {"paragraph": 3, "start_offset": 59, "end_offset": 90, "style": "underline", "purpose": "impact"},
        {"paragraph": 3, "start_offset": 61, "end_offset": 69, "style": "highlight", "purpose": "impact"},
        {
            "paragraph": 3,
            "start_offset": 93,
            "end_offset": 120,
            "style": "underline",
            "purpose": "internal_link",
        },
    ],
    "rationale": (
        "The underlines carry the claim and the shutdown impact; the highlights are what a judge must hear."
    ),
}
"""The answer the committed `card.markup` fixture and cassette hold, written by hand."""

#: The evidence RECORDED_SELECTION selects, by hand: P2 from offset 52 to its end, and P3 from 59 to
#: 120, which is P2's 163-238 and P3's 299-360 in the snapshot, with 238-299 omitted between them.
SEGMENT_ONE = "the fight leaves no room for a budget deal this spring 🌍 before the recess."
SEGMENT_TWO = "a shutdown follows within weeks 😬 and the grid program stalls"

#: The marked words, by hand, at snapshot offsets: P2 62-126 is 173-237, 69-94 is 180-205; P3 59-90
#: is 299-330, 61-69 is 301-309 and 93-120 is 333-360.
MARKED = [
    (
        173,
        237,
        SpanStyle.UNDERLINE,
        SpanPurpose.CLAIM,
        "leaves no room for a budget deal this spring 🌍 before the recess",
    ),
    (180, 205, SpanStyle.HIGHLIGHT, SpanPurpose.CLAIM, "no room for a budget deal"),
    (299, 330, SpanStyle.UNDERLINE, SpanPurpose.IMPACT, "a shutdown follows within weeks"),
    (301, 309, SpanStyle.HIGHLIGHT, SpanPurpose.IMPACT, "shutdown"),
    (333, 360, SpanStyle.UNDERLINE, SpanPurpose.INTERNAL_LINK, "and the grid program stalls"),
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def registry() -> PromptRegistry:
    """The committed prompts: `card.select`, `card.markup` and `model.repair` among them."""
    return PromptRegistry.load(REPOSITORY_ROOT / "prompts")


@pytest.fixture
def loaded() -> LoadedSnapshot:
    """The source as production holds it: created through the snapshot service, then loaded, checked."""
    return asyncio.run(_create_and_load())


async def _create_and_load() -> LoadedSnapshot:
    service = SnapshotService(
        blobs=InMemorySnapshotStore(), clock=FixedClock(), id_generator=SequentialIdGenerator("SNAP")
    )
    snapshot = await service.create(
        article_id="0ART0000000000000000000001",
        raw_bytes=SOURCE.encode("utf-8"),
        extracted_text=SOURCE,
        canonical_url="https://example.org/politics/clean-grid-vote",
        retrieved_at=datetime(2026, 10, 20, 9, 30, tzinfo=UTC),
        extractor_version="fake-extractor/1.0",
        provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
        access_status=AccessStatus.ACCESSIBLE,
    )
    loaded = await service.load(snapshot)
    assert loaded.normalized.text == SOURCE  # the source is already normalized
    return loaded


@pytest.fixture
def numbered(loaded: LoadedSnapshot) -> NumberedSnapshot:
    return NumberedSnapshot(loaded.normalized)


def selection_with(**changes: JsonValue) -> CardSelection:
    """RECORDED_SELECTION with top-level `changes`, validated as the guard validates it."""
    return CardSelection.model_validate_json(json.dumps({**RECORDED_SELECTION, **changes}), strict=True)


VALID: tuple[tuple[int, int, int, int | None], ...] = ((3, 3, 59, 120),)
"""A valid passage, beside an invalid one, so the schema's other refusal (an empty tuple) stays quiet."""


def passages(*ranges: tuple[int, int, int, int | None]) -> list[JsonValue]:
    return [
        {"first_paragraph": first, "last_paragraph": last, "start_offset": start, "end_offset": end}
        for first, last, start, end in ranges
    ]


def tagged(text: str) -> CardSelection:
    tag = cast("dict[str, JsonValue]", RECORDED_SELECTION["tag"])
    return selection_with(tag={**tag, "text": text})


def markup_of(*spans: Mapping[str, JsonValue], rationale: str = "A rationale of my own.") -> MarkupSuggestion:
    return MarkupSuggestion.model_validate_json(
        json.dumps({"spans": list(spans), "rationale": rationale}), strict=True
    )


def span(paragraph: int, start: int, end: int, style: str = "underline") -> dict[str, JsonValue]:
    return {"paragraph": paragraph, "start_offset": start, "end_offset": end, "style": style}


def kinds(problems: tuple[GuardProblem, ...]) -> list[tuple[tuple[str | int, ...], GuardProblemType]]:
    return [(problem.loc, problem.type) for problem in problems]


def selector(
    router: ScriptedModelRouter | FakeModelRouter | RecordReplayModelRouter, registry: PromptRegistry
) -> CardSelector:
    return CardSelector(StructuredOutputGuard(router, registry))


# =============================================================================================
# ac1: the schemas hold ids, offsets, enums, tag text, rationale and confidence, nothing else
# =============================================================================================

CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    SelectedPassage,
    TagSuggestion,
    CardSelection,
    MarkupSpan,
    MarkupSuggestion,
)


def test_schema_fields_are_only_ids_offsets_enums_tag_rationale_and_confidence() -> None:
    assert {model.__name__: set(model.model_fields) for model in CONTRACT_MODELS} == {
        "SelectedPassage": {"first_paragraph", "last_paragraph", "start_offset", "end_offset"},
        "TagSuggestion": {"text", "argument_role", "need_alignment", "confidence"},
        "CardSelection": {"passages", "tag", "rationale", "confidence"},
        "MarkupSpan": {"paragraph", "start_offset", "end_offset", "style", "purpose"},
        "MarkupSuggestion": {"spans", "rationale"},
    }


def _string_fields(schema: Mapping[str, Any]) -> Iterator[tuple[str, str]]:
    """`(model, field)` for every property of the JSON schema a model may fill with free text."""
    for model_name, definition in {**schema.get("$defs", {}), schema["title"]: schema}.items():
        for field_name, property_schema in definition.get("properties", {}).items():
            options = property_schema.get("anyOf", [property_schema])
            if any(option.get("type") == "string" and "enum" not in option for option in options):
                yield model_name, field_name


def test_schema_free_text_is_only_the_tag_and_the_rationales() -> None:
    free_text = {
        *_string_fields(CardSelection.model_json_schema()),
        *_string_fields(MarkupSuggestion.model_json_schema()),
    }

    assert free_text == {
        ("TagSuggestion", "text"),
        ("CardSelection", "rationale"),
        ("MarkupSuggestion", "rationale"),
    }


def test_schema_no_field_is_named_for_evidence_or_quotes() -> None:
    names = {name for model in CONTRACT_MODELS for name in model.model_fields}
    forbidden = (
        "evidence",
        "quote",
        "quotation",
        "excerpt",
        "verbatim",
        "snippet",
        "passage_text",
        "content",
    )

    assert [name for name in names if any(word in name for word in forbidden)] == []


@pytest.mark.parametrize(
    ("document", "location"),
    [
        ({**RECORDED_SELECTION, "evidence_text": "Words copied from the source."}, ("evidence_text",)),
        (
            {
                **RECORDED_SELECTION,
                "tag": {**cast("dict[str, JsonValue]", RECORDED_SELECTION["tag"]), "quote": "Copied."},
            },
            ("tag", "quote"),
        ),
        (
            {
                **RECORDED_SELECTION,
                "passages": [
                    *passages(*VALID),
                    {"first_paragraph": 2, "last_paragraph": 2, "text": "Copied."},
                ],
            },
            ("passages", 1, "text"),
        ),
    ],
    ids=["top-level", "in-the-tag", "in-a-passage"],
)
def test_schema_refuses_an_evidence_field_at_every_depth(
    document: dict[str, JsonValue], location: tuple[str | int, ...]
) -> None:
    with pytest.raises(ValidationError) as by_the_schema:
        CardSelection.model_validate(document)
    with pytest.raises(InvalidModelOutput) as by_the_guard:
        validate_model_output(
            CardSelection,
            document,
            prompt=ModelPrompt(prompt_id="card.select", prompt_version="1.0.0"),
            model_id=None,
        )

    assert [(error["loc"], error["type"]) for error in by_the_schema.value.errors()] == [
        (location, "extra_forbidden")
    ]
    assert [(problem.loc, problem.type) for problem in by_the_guard.value.problems] == [
        (location, "extra_forbidden")
    ]


def test_schema_refuses_an_evidence_field_in_a_markup_span() -> None:
    document = {"spans": [span(2, 62, 126), {**span(2, 62, 126), "text": "Copied."}], "rationale": "Mine."}

    with pytest.raises(ValidationError) as raised:
        MarkupSuggestion.model_validate(document)

    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [
        (("spans", 1, "text"), "extra_forbidden")
    ]


def test_schema_style_and_purpose_are_the_card_span_enums() -> None:
    assert MarkupSpan.model_fields["style"].annotation is SpanStyle
    assert CardSpan.model_fields["style"].annotation is SpanStyle
    assert MarkupSpan.model_fields["purpose"].annotation == SpanPurpose | None
    assert CardSpan.model_fields["purpose"].annotation == SpanPurpose | None
    assert [style.value for style in SpanStyle] == ["underline", "highlight"]
    assert [purpose.value for purpose in SpanPurpose] == ["claim", "warrant", "internal_link", "impact"]
    assert [role.value for role in ArgumentRole] == ["uniqueness", "link", "internal_link", "impact"]
    assert [fit.value for fit in NeedAlignment] == ["direct", "partial", "tangential"]


@pytest.mark.parametrize(
    ("changes", "location", "error_type"),
    [
        ({"confidence": 1.01}, ("confidence",), "less_than_equal"),
        ({"confidence": -0.01}, ("confidence",), "greater_than_equal"),
        ({"confidence": "0.5"}, ("confidence",), "float_type"),
        ({"rationale": "   "}, ("rationale",), "string_pattern_mismatch"),
        ({"rationale": "x" * 1001}, ("rationale",), "string_too_long"),
        ({"passages": []}, ("passages",), "too_short"),
        (
            {"passages": passages((0, 2, 0, None), *VALID)},
            ("passages", 0, "first_paragraph"),
            "greater_than_equal",
        ),
        (
            {"passages": passages((2, 2, -1, None), *VALID)},
            ("passages", 0, "start_offset"),
            "greater_than_equal",
        ),
        ({"passages": passages((2, 2, 0, 0), *VALID)}, ("passages", 0, "end_offset"), "greater_than_equal"),
        (
            {"passages": [{"first_paragraph": "2", "last_paragraph": 2}, *passages(*VALID)]},
            ("passages", 0, "first_paragraph"),
            "int_type",
        ),
        (
            {"passages": [{"first_paragraph": 2.0, "last_paragraph": 2}, *passages(*VALID)]},
            ("passages", 0, "first_paragraph"),
            "int_type",
        ),
    ],
    ids=[
        "confidence-above-one",
        "confidence-below-zero",
        "confidence-as-string",
        "blank-rationale",
        "long-rationale",
        "no-passages",
        "paragraph-zero",
        "negative-offset",
        "end-zero",
        "paragraph-as-string",
        "paragraph-as-float",
    ],
)
def test_schema_bounds_are_refused_strictly(
    changes: dict[str, JsonValue], location: tuple[str | int, ...], error_type: str
) -> None:
    with pytest.raises(ValidationError) as raised:
        selection_with(**changes)

    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [(location, error_type)]


@pytest.mark.parametrize(
    ("text", "error_type"),
    [("", "string_too_short"), (" \n ", "string_pattern_mismatch"), ("x" * 301, "string_too_long")],
    ids=["empty", "blank", "too-long"],
)
def test_schema_refuses_an_empty_blank_or_essay_tag(text: str, error_type: str) -> None:
    with pytest.raises(ValidationError) as raised:
        tagged(text)

    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [
        (("tag", "text"), error_type)
    ]


def test_schema_accepts_the_recorded_answers_and_whole_number_confidence() -> None:
    selection = selection_with(confidence=1)

    assert selection.passages[0] == SelectedPassage(first_paragraph=2, last_paragraph=2, start_offset=52)
    assert selection.tag.argument_role is ArgumentRole.LINK
    assert selection.confidence == 1.0
    assert MarkupSuggestion.model_validate(RECORDED_MARKUP).spans[4].purpose is SpanPurpose.INTERNAL_LINK


def test_schema_models_are_frozen() -> None:
    selection = selection_with()

    with pytest.raises(ValidationError):
        selection.rationale = "Changed."  # pyright: ignore[reportAttributeAccessIssue]


# =============================================================================================
# ac2: the prompts are registered, numbered, and route to complex_reasoning
# =============================================================================================


@pytest.mark.parametrize(
    ("prompt_id", "schema", "variables"),
    [
        ("card.select", CardSelection, {"research_need", "numbered_snapshot"}),
        ("card.markup", MarkupSuggestion, {"research_need", "tag", "passages", "numbered_passages"}),
    ],
)
def test_prompt_is_registered_released_and_routed_to_complex_reasoning(
    registry: PromptRegistry, prompt_id: str, schema: type[BaseModel], variables: set[str]
) -> None:
    prompt = registry.get(prompt_id, "1.0.0")

    assert prompt.spec.version == "1.0.0"
    assert prompt.spec.is_released
    assert prompt.spec.task_class is TaskClass.COMPLEX_REASONING
    assert prompt.schema is schema
    assert prompt.variables == variables
    assert SELECTION_TASK_CLASS is TaskClass.COMPLEX_REASONING


def test_prompt_versions_are_locked() -> None:
    lock = PromptLock.read(REPOSITORY_ROOT / "prompts" / "prompts.lock.json")

    assert {("card.select", "1.0.0"), ("card.markup", "1.0.0")} <= set(lock.versions)


async def test_prompt_select_renders_the_numbered_snapshot_and_the_need(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    router = ScriptedModelRouter([RECORDED_SELECTION])

    await selector(router, registry).select(loaded, NEED)

    [request] = router.calls
    assert request.task_class is TaskClass.COMPLEX_REASONING
    assert (
        request.prompt.variables["numbered_snapshot"] == f"[P1] {P1}\n\n[P2] {P2}\n\n[P3] {P3}\n\n[P4] {P4}"
    )
    rendered = registry.render(request.prompt)
    assert (
        rendered.user
        == f"Research need: {NEED}\n\nThe source:\n\n[P1] {P1}\n\n[P2] {P2}\n\n[P3] {P3}\n\n[P4] {P4}"
    )
    assert rendered.system is not None and "[P3]" in rendered.system


async def test_prompt_markup_shows_only_the_selected_paragraphs_with_their_own_numbers(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    router = ScriptedModelRouter([RECORDED_SELECTION, RECORDED_MARKUP])
    cards = selector(router, registry)

    await cards.mark_up(loaded, await cards.select(loaded, NEED), NEED)

    variables = router.calls[1].prompt.variables
    assert router.calls[1].task_class is TaskClass.COMPLEX_REASONING
    assert variables["numbered_passages"] == f"[P2] {P2}\n\n[P3] {P3}"
    assert variables["tag"] == "An energy fight leaves no time for a budget, so a shutdown follows"
    assert json.loads(cast("str", variables["passages"])) == [
        {"first_paragraph": 2, "last_paragraph": 2, "start_offset": 52, "end_offset": 127},
        {"first_paragraph": 3, "last_paragraph": 3, "start_offset": 59, "end_offset": 120},
    ]


# =============================================================================================
# ac3: the guard. Offsets first: out of bounds, outside the selection, or inconsistent
# =============================================================================================


def test_guard_accepts_the_recorded_selection_and_markup(numbered: NumberedSnapshot) -> None:
    selection = selection_with()

    assert selection_problems(selection, numbered) == ()
    assert markup_problems(MarkupSuggestion.model_validate(RECORDED_MARKUP), selection, numbered) == ()


@pytest.mark.parametrize(
    ("ranges", "expected"),
    [
        (((5, 5, 0, None),), [(("passages", 0), GuardProblemType.PARAGRAPH_OUT_OF_BOUNDS)]),
        (((3, 2, 0, None),), [(("passages", 0), GuardProblemType.REVERSED_RANGE)]),
        (((2, 2, 127, None),), [(("passages", 0), GuardProblemType.OFFSET_OUT_OF_BOUNDS)]),
        (((2, 2, 0, 128),), [(("passages", 0), GuardProblemType.OFFSET_OUT_OF_BOUNDS)]),
        (((2, 3, 0, 122),), [(("passages", 0), GuardProblemType.OFFSET_OUT_OF_BOUNDS)]),
        (((2, 2, 40, 40),), [(("passages", 0), GuardProblemType.EMPTY_RANGE)]),
        (((2, 2, 40, 30),), [(("passages", 0), GuardProblemType.REVERSED_RANGE)]),
        (((2, 2, 0, 60), (2, 2, 59, None)), [(("passages", 1), GuardProblemType.OVERLAPPING_PASSAGES)]),
        (((2, 3, 0, None), (3, 3, 10, 20)), [(("passages", 1), GuardProblemType.OVERLAPPING_PASSAGES)]),
    ],
    ids=[
        "no-such-paragraph",
        "reversed-paragraphs",
        "starts-at-the-end",
        "end-one-past-the-end",
        "end-one-past-the-last-paragraph",
        "empty",
        "reversed-offsets",
        "overlapping",
        "one-inside-another",
    ],
)
def test_guard_refuses_a_selection_whose_offsets_name_no_characters_or_overlap(
    numbered: NumberedSnapshot,
    ranges: tuple[tuple[int, int, int, int | None], ...],
    expected: list[tuple[tuple[str | int, ...], GuardProblemType]],
) -> None:
    assert kinds(selection_problems(selection_with(passages=passages(*ranges)), numbered)) == expected


@pytest.mark.parametrize(
    "ranges",
    [((2, 2, 0, 127),), ((2, 2, 0, 60), (2, 2, 60, None)), ((1, 4, 0, None),), ((4, 4, 90, None),)],
    ids=["end-exactly-at-the-end", "touching", "whole-snapshot", "last-character"],
)
def test_guard_accepts_offsets_up_to_and_at_the_paragraph_end_and_touching_passages(
    numbered: NumberedSnapshot, ranges: tuple[tuple[int, int, int, int | None], ...]
) -> None:
    assert selection_problems(selection_with(passages=passages(*ranges)), numbered) == ()


@pytest.mark.parametrize(
    ("spans", "expected"),
    [
        ((span(1, 0, 10),), [(("spans", 0), GuardProblemType.OUTSIDE_SELECTION)]),
        ((span(4, 0, 10),), [(("spans", 0), GuardProblemType.OUTSIDE_SELECTION)]),
        ((span(2, 40, 60),), [(("spans", 0), GuardProblemType.OUTSIDE_SELECTION)]),
        ((span(2, 51, 53),), [(("spans", 0), GuardProblemType.OUTSIDE_SELECTION)]),
        ((span(3, 50, 70),), [(("spans", 0), GuardProblemType.OUTSIDE_SELECTION)]),
        ((span(3, 100, 121),), [(("spans", 0), GuardProblemType.OUTSIDE_SELECTION)]),
        ((span(9, 0, 10),), [(("spans", 0), GuardProblemType.PARAGRAPH_OUT_OF_BOUNDS)]),
        ((span(2, 100, 128),), [(("spans", 0), GuardProblemType.OFFSET_OUT_OF_BOUNDS)]),
        ((span(2, 70, 70),), [(("spans", 0), GuardProblemType.EMPTY_RANGE)]),
        ((span(2, 80, 70),), [(("spans", 0), GuardProblemType.REVERSED_RANGE)]),
        ((span(2, 60, 80), span(2, 79, 90)), [(("spans", 1), GuardProblemType.OVERLAPPING_SAME_STYLE)]),
        (
            (span(2, 60, 90), span(2, 62, 70, "highlight"), span(2, 69, 75, "highlight")),
            [(("spans", 2), GuardProblemType.OVERLAPPING_SAME_STYLE)],
        ),
        (
            (span(2, 60, 80), span(2, 75, 85, "highlight")),
            [(("spans", 1), GuardProblemType.HIGHLIGHT_NOT_UNDERLINED)],
        ),
        ((span(3, 70, 80, "highlight"),), [(("spans", 0), GuardProblemType.HIGHLIGHT_NOT_UNDERLINED)]),
    ],
    ids=[
        "paragraph-before-the-selection",
        "paragraph-after-the-selection",
        "partly-before-the-selection",
        "one-character-before",
        "across-the-cut",
        "past-the-selection-end",
        "no-such-paragraph",
        "end-one-past-the-paragraph",
        "empty",
        "reversed",
        "two-underlines-overlap",
        "two-highlights-overlap",
        "highlight-runs-past-its-underline",
        "highlight-with-no-underline",
    ],
)
def test_guard_refuses_markup_outside_the_selection_or_inconsistent_with_itself(
    numbered: NumberedSnapshot,
    spans: tuple[dict[str, JsonValue], ...],
    expected: list[tuple[tuple[str | int, ...], GuardProblemType]],
) -> None:
    assert kinds(markup_problems(markup_of(*spans), selection_with(), numbered)) == expected


@pytest.mark.parametrize(
    "spans",
    [
        (span(2, 52, 127),),
        (span(2, 52, 127), span(3, 59, 120)),
        (span(2, 60, 80), span(2, 80, 90), span(2, 75, 85, "highlight")),
        (span(2, 60, 80), span(2, 60, 80, "highlight")),
    ],
    ids=[
        "the-whole-first-passage",
        "both-passages-whole",
        "highlight-across-touching-underlines",
        "same-range-both-styles",
    ],
)
def test_guard_accepts_markup_inside_the_selection_with_highlights_underlined(
    numbered: NumberedSnapshot, spans: tuple[dict[str, JsonValue], ...]
) -> None:
    assert markup_problems(markup_of(*spans), selection_with(), numbered) == ()


def test_guard_markup_may_cross_touching_passages_as_extraction_joins_them(
    numbered: NumberedSnapshot,
) -> None:
    selection = selection_with(passages=passages((2, 2, 0, 60), (2, 2, 60, None)))

    assert markup_problems(markup_of(span(2, 50, 70)), selection, numbered) == ()


def test_guard_problem_messages_name_numbers_never_text(numbered: NumberedSnapshot) -> None:
    problems = markup_problems(markup_of(span(1, 0, 10)), selection_with(), numbered)

    assert [problem.msg for problem in problems] == [
        "span 0 (paragraph 1, offsets 0 to 10) is not wholly inside one selected passage"
    ]


# =============================================================================================
# ac3: the guard. Quoted text: 12 consecutive snapshot words in any free-text field
# =============================================================================================

#: The sentinel's words one by one, so a tag can repeat exactly N of them.
SENTINEL_SPLIT = SENTINEL.split()


def repeating(count: int) -> str:
    """A tag repeating the sentinel's first `count` words, between words the snapshot does not hold."""
    return "Experts note " + " ".join(SENTINEL_SPLIT[:count]) + " overnight, a new claim"


def test_guard_threshold_is_twelve_words() -> None:
    assert QUOTED_RUN_WORDS == 12
    assert len(SENTINEL_SPLIT) == 13


def test_guard_allows_eleven_consecutive_snapshot_words(numbered: NumberedSnapshot) -> None:
    assert selection_problems(tagged(repeating(11)), numbered) == ()


@pytest.mark.parametrize("count", [12, 13])
def test_guard_refuses_twelve_or_more_consecutive_snapshot_words_and_counts_them(
    numbered: NumberedSnapshot, count: int
) -> None:
    [problem] = selection_problems(tagged(repeating(count)), numbered)

    assert (problem.loc, problem.type) == (("tag", "text"), GuardProblemType.QUOTED_SNAPSHOT_TEXT)
    # The run is the sentinel's first `count` words, which start at P4's first character, 363.
    end = 363 + len(" ".join(SENTINEL_SPLIT[:count]))
    assert problem.msg.startswith(f"{count} consecutive words of this field are the snapshot's own words")
    assert f"snapshot offsets 363 to {end})" in problem.msg


@pytest.mark.parametrize(
    "text",
    [
        SENTINEL.upper(),
        "VIOLET harbor, engines — quietly “folded” seven paper lanterns; beneath the northern quarry!",
        "violet\n\nharbor\tengines  quietly folded seven paper lanterns beneath the northern quarry",
        "Says: the Senate's clean grid bill passed 52 48 on Tuesday spends political capital",
        "the majority will need later Analysts at the Café Économique institute warn",
        unicodedata.normalize(
            "NFD", "the majority will need later Analysts at the Café Économique institute warn"
        ),
    ],
    ids=[
        "case",
        "punctuation",
        "whitespace",
        "straight-apostrophe-and-dash",
        "across-a-paragraph-break",
        "decomposed",
    ],
)
def test_guard_word_runs_ignore_case_punctuation_and_whitespace(
    numbered: NumberedSnapshot, text: str
) -> None:
    assert kinds(selection_problems(tagged(text), numbered)) == [
        (("tag", "text"), GuardProblemType.QUOTED_SNAPSHOT_TEXT)
    ]


def test_guard_counts_whole_words_only(numbered: NumberedSnapshot) -> None:
    # "iolet" is not the snapshot's word "violet", so only eleven whole words follow it.
    assert selection_problems(tagged("iolet " + " ".join(SENTINEL_SPLIT[1:12])), numbered) == ()


def test_guard_checks_every_free_text_field_of_a_selection(numbered: NumberedSnapshot) -> None:
    selection = selection_with(rationale=f"Because {SENTINEL}.")

    assert kinds(selection_problems(selection, numbered)) == [
        (("rationale",), GuardProblemType.QUOTED_SNAPSHOT_TEXT)
    ]


def test_guard_checks_the_markup_rationale(numbered: NumberedSnapshot) -> None:
    markup = markup_of(span(2, 62, 126), rationale=f"Underlined: {SENTINEL}")

    assert kinds(markup_problems(markup, selection_with(), numbered)) == [
        (("rationale",), GuardProblemType.QUOTED_SNAPSHOT_TEXT)
    ]


def test_guard_quoted_text_problem_never_holds_the_words(numbered: NumberedSnapshot) -> None:
    [problem] = selection_problems(tagged(SENTINEL), numbered)

    assert not any(word in problem.msg.casefold() for word in SENTINEL_WORDS)


def test_guard_snapshot_words_finds_the_longest_run_from_its_first_match() -> None:
    run = SnapshotWords(SOURCE).quoted_run(f"Intro {SENTINEL} trailing words")

    assert run is not None
    assert (run.words, run.start, run.end) == (13, 363, 453)


# =============================================================================================
# ac3: through the structured-output guard, fail-closed: repaired once, then ModelOutputError
# =============================================================================================


def _strings_in(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in cast("Mapping[object, object]", value).items():
            yield from _strings_in(key)
            yield from _strings_in(item)
    elif isinstance(value, list | tuple):
        for item in cast("list[object]", value):
            yield from _strings_in(item)


_STANDARD_RECORD_KEYS = frozenset(vars(logging.makeLogRecord({})))


def _sentinel_in(text: str) -> bool:
    return any(word in text.casefold() for word in SENTINEL_WORDS)


async def test_guard_quoted_tag_is_refused_after_one_repair_and_nothing_quotes_it(
    registry: PromptRegistry, loaded: LoadedSnapshot, caplog: pytest.LogCaptureFixture
) -> None:
    quoting = {
        **RECORDED_SELECTION,
        "tag": {**cast("dict[str, JsonValue]", RECORDED_SELECTION["tag"]), "text": SENTINEL},
    }
    router = ScriptedModelRouter([quoting, quoting])
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ModelOutputError) as raised:
        await selector(router, registry).select(loaded, NEED)

    error = raised.value
    assert error.attempts == 2
    assert error.fail_closed is True
    assert error.prompt_id == "card.select"
    assert [(problem.loc, problem.type) for problem in error.problems] == [
        (("tag", "text"), "quoted_snapshot_text")
    ]
    for attempt in error.attempt_records:
        assert not any(_sentinel_in(problem.msg) for problem in attempt.problems)
    assert not _sentinel_in(str(error))
    assert not _sentinel_in(repr(error))
    assert not any(
        _sentinel_in(text)
        for text in _strings_in([[problem.loc, problem.type, problem.msg] for problem in error.problems])
    )
    for record in caplog.records:
        extras = {key: value for key, value in vars(record).items() if key not in _STANDARD_RECORD_KEYS}
        assert not _sentinel_in(record.getMessage())
        assert not any(_sentinel_in(text) for text in _strings_in(list(extras.values())))
    # The repair resends the call's own prompt, numbered snapshot and all, so the snapshot's words
    # are in it (the PM's note of 2026-10-25); the problems it lists never are.
    repair = router.calls[1].prompt
    assert repair.prompt_id == "model.repair"
    assert SENTINEL in cast("str", repair.variables["failed_user"])
    assert not any(_sentinel_in(text) for text in _strings_in(repair.variables["problems"]))


async def test_guard_out_of_bounds_selection_is_repaired_once_and_a_good_repair_is_kept(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    out_of_bounds = {**RECORDED_SELECTION, "passages": passages((2, 2, 0, 128))}
    router = ScriptedModelRouter([out_of_bounds, RECORDED_SELECTION])

    generated = await selector(router, registry).select(loaded, NEED)

    assert generated.selection == selection_with()
    assert generated.metadata.repair_attempted is True
    assert generated.metadata.prompt_id == "card.select"
    assert [call.prompt.prompt_id for call in router.calls] == ["card.select", "model.repair"]
    assert cast("list[dict[str, Any]]", router.calls[1].prompt.variables["problems"]) == [
        {
            "loc": ["passages", 0],
            "type": "offset_out_of_bounds",
            "msg": "offset 128 is outside paragraph 2, which has 127 characters",
        }
    ]


async def test_guard_markup_outside_the_selection_is_refused_fail_closed(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    outside = {"spans": [span(1, 0, 10)], "rationale": "Mine."}
    router = ScriptedModelRouter([RECORDED_SELECTION, outside, outside])
    cards = selector(router, registry)
    selected = await cards.select(loaded, NEED)

    with pytest.raises(ModelOutputError) as raised:
        await cards.mark_up(loaded, selected, NEED)

    assert raised.value.fail_closed is True
    assert raised.value.attempts == 2
    assert raised.value.prompt_id == "card.markup"
    assert [(problem.loc, problem.type) for problem in raised.value.problems] == [
        (("spans", 0), "outside_selection")
    ]


async def test_guard_an_answer_that_does_not_fit_the_schema_is_refused_fail_closed(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    quoting_field = {**RECORDED_SELECTION, "evidence_text": "Copied from the source."}
    router = ScriptedModelRouter([quoting_field, quoting_field])

    with pytest.raises(ModelOutputError) as raised:
        await selector(router, registry).select(loaded, NEED)

    assert raised.value.fail_closed is True
    assert [(problem.loc, problem.type) for problem in raised.value.problems] == [
        (("evidence_text",), "extra_forbidden")
    ]


def test_guard_policy_for_selection_and_markup_is_fail_closed() -> None:
    assert SELECTION_POLICY.fail_closed is True


async def test_guard_markup_of_a_selection_from_another_snapshot_is_refused_before_any_call(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    router = ScriptedModelRouter([RECORDED_SELECTION])
    cards = selector(router, registry)
    selected = await cards.select(loaded, NEED)
    other = selected.model_copy(update={"snapshot_id": "0SNAP000000000000000000099"})

    with pytest.raises(ValueError, match="from snapshot"):
        await cards.mark_up(loaded, other, NEED)

    assert len(router.calls) == 1


async def test_guard_refuses_a_blank_research_need_before_any_call(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    router = ScriptedModelRouter([])

    with pytest.raises(ValueError, match="research need"):
        await selector(router, registry).select(loaded, "  ")

    assert router.calls == []


# =============================================================================================
# ac4: recorded answers, through span extraction, give the snapshot's own bytes
# =============================================================================================

RouterFactory = Callable[[], FakeModelRouter | RecordReplayModelRouter]

ROUTERS: dict[str, RouterFactory] = {
    "fake-router-fixture": lambda: FakeModelRouter(FIXTURES / "model_outputs"),
    "replayed-cassette": lambda: RecordReplayModelRouter(
        None, mode=ModelMode.REPLAY, cassette_dir=FIXTURES / "model_cassettes"
    ),
}


@pytest.mark.parametrize("router_name", list(ROUTERS))
async def test_round_trip_selection_and_markup_extract_byte_identical_evidence(
    registry: PromptRegistry, loaded: LoadedSnapshot, router_name: str
) -> None:
    cards = selector(ROUTERS[router_name](), registry)
    numbered = NumberedSnapshot(loaded.normalized)

    selected = await cards.select(loaded, NEED)
    marked = await cards.mark_up(loaded, selected, NEED)
    evidence = EvidenceExtractor().extract(
        loaded.snapshot, loaded.normalized, numbered.evidence_selection(selected.selection)
    )
    card_markup = CardMarkup(evidence, numbered.markup_spans(marked.markup))

    assert selected.selection == selection_with()
    assert [(segment.start, segment.end) for segment in evidence.segments] == [(163, 238), (299, 360)]
    assert [(omitted.start, omitted.end) for omitted in evidence.omitted_ranges] == [(238, 299)]
    assert [segment.text.encode("utf-8") for segment in evidence.segments] == [
        SEGMENT_ONE.encode("utf-8"),
        SEGMENT_TWO.encode("utf-8"),
    ]
    assert [segment.text.encode("utf-8") for segment in evidence.segments] == [
        SOURCE[163:238].encode("utf-8"),
        SOURCE[299:360].encode("utf-8"),
    ]
    assert [
        (mark.start, mark.end, mark.style, mark.purpose, SOURCE[mark.start : mark.end])
        for mark in card_markup.spans
    ] == MARKED
    # The offsets are code points. In UTF-8 the first segment starts 14 bytes later: P1's ’ “ ” — – —
    # are three bytes each (12 extra) and P2's é and É two each (2 extra).
    assert len(SOURCE[:163].encode("utf-8")) == 177


@pytest.mark.parametrize("router_name", list(ROUTERS))
async def test_round_trip_artifacts_carry_the_route_and_the_snapshot_they_came_from(
    registry: PromptRegistry, loaded: LoadedSnapshot, router_name: str
) -> None:
    cards = selector(ROUTERS[router_name](), registry)

    selected = await cards.select(loaded, NEED)
    marked = await cards.mark_up(loaded, selected, NEED)

    # Replay reports provider `fake` too, so a recorded answer never passes for a billed one (t03),
    # and keeps the model id the cassette recorded.
    model_id = "fake-fixture-model" if router_name == "fake-router-fixture" else "example-recorded-model"
    for generated, prompt_id in ((selected, "card.select"), (marked, "card.markup")):
        assert generated.snapshot_id == loaded.snapshot.snapshot_id
        assert generated.metadata.snapshot_ids == (loaded.snapshot.snapshot_id,)
        assert generated.metadata.retrieval_ids == ()
        assert generated.metadata.prompt_id == prompt_id
        assert generated.metadata.prompt_version == "1.0.0"
        assert generated.metadata.route.task_class is TaskClass.COMPLEX_REASONING
        assert generated.metadata.route.provider is ModelProvider.FAKE
        assert generated.metadata.model_id == model_id
        assert generated.metadata.repair_attempted is False


# =============================================================================================
# ac5: an artifact cannot be built or stored without its response metadata and inputs
# =============================================================================================


async def generated_selection(registry: PromptRegistry, loaded: LoadedSnapshot) -> GeneratedCardSelection:
    return await selector(ScriptedModelRouter([RECORDED_SELECTION]), registry).select(loaded, NEED)


async def test_artifact_refuses_the_bare_response_metadata(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    generated = await generated_selection(registry, loaded)
    bare = GeneratedArtifactMetadata.model_validate(
        generated.metadata.model_dump(exclude={"snapshot_ids", "retrieval_ids"})
    )

    with pytest.raises(ValidationError) as raised:
        GeneratedCardSelection(
            snapshot_id=generated.snapshot_id,
            selection=generated.selection,
            metadata=bare,  # pyright: ignore[reportArgumentType]  # the type refuses it too
        )

    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [
        (("metadata",), "model_type")
    ]


async def test_artifact_cannot_be_built_without_metadata(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    generated = await generated_selection(registry, loaded)

    with pytest.raises(ValidationError) as raised:
        GeneratedCardSelection.model_validate(
            {"snapshot_id": generated.snapshot_id, "selection": RECORDED_SELECTION}
        )

    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [(("metadata",), "missing")]


@pytest.mark.parametrize("dropped", ["snapshot_ids", "retrieval_ids"])
async def test_artifact_stored_without_its_inputs_does_not_load(
    registry: PromptRegistry, loaded: LoadedSnapshot, dropped: str
) -> None:
    stored = json.loads((await generated_selection(registry, loaded)).model_dump_json())
    del stored["metadata"][dropped]

    with pytest.raises(ValidationError) as raised:
        GeneratedCardSelection.model_validate_json(json.dumps(stored))

    assert [(error["loc"], error["type"]) for error in raised.value.errors()] == [
        (("metadata", dropped), "missing")
    ]


@pytest.mark.parametrize(
    "snapshot_ids",
    [[], ["0SNAP000000000000000000099"], ["0SNAP000000000000000000001", "0SNAP000000000000000000099"]],
)
async def test_artifact_metadata_must_record_exactly_its_snapshot(
    registry: PromptRegistry, loaded: LoadedSnapshot, snapshot_ids: list[str]
) -> None:
    stored = json.loads((await generated_selection(registry, loaded)).model_dump_json())
    assert stored["metadata"]["snapshot_ids"] == [loaded.snapshot.snapshot_id]
    stored["metadata"]["snapshot_ids"] = snapshot_ids

    with pytest.raises(ValidationError, match="exactly the snapshot"):
        GeneratedCardSelection.model_validate_json(json.dumps(stored))


async def test_artifact_metadata_must_be_for_its_own_prompt(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    generated = await generated_selection(registry, loaded)

    with pytest.raises(ValidationError, match="not card.markup"):
        GeneratedCardMarkup(
            snapshot_id=generated.snapshot_id,
            markup=MarkupSuggestion.model_validate(RECORDED_MARKUP),
            metadata=generated.metadata,
        )


async def test_artifact_round_trips_through_its_stored_form(
    registry: PromptRegistry, loaded: LoadedSnapshot
) -> None:
    generated = await generated_selection(registry, loaded)

    assert GeneratedCardSelection.model_validate_json(generated.model_dump_json()) == generated
    assert isinstance(generated.metadata, SourcedArtifactMetadata)


def test_artifact_with_inputs_requires_both_inputs() -> None:
    assert [
        (name, parameter.kind.name, parameter.default is parameter.empty)
        for name, parameter in inspect.signature(GeneratedArtifactMetadata.with_inputs).parameters.items()
    ] == [
        ("self", "POSITIONAL_OR_KEYWORD", True),
        ("snapshot_ids", "KEYWORD_ONLY", True),
        ("retrieval_ids", "KEYWORD_ONLY", True),
    ]
