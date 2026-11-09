"""A repair cassette's scan hit is in the input only when its words come from the cards the failed call sent
(`v1-e32-t59`, the PM's ruling of 2026-11-06 on `v1-e32-t55`).

A `model.repair` cassette records the repair call's request, which carries the failed call's whole rendered
prompt (`failed_system`, `failed_user`): the classify prompt's own instructions, its user turn's preamble,
and the cards as a JSON list with their keys. It never records the failed answer. Until this task every word
of that prompt counted as sent, so a JSON key's name or a taxonomy word in the instructions, or in the
repair call's own answer that repeated them, kept its hit. Now only the cards' heading paths, tags, cites
and excerpts count, found in the cassette's own recorded request, as a first-call cassette's `items` do. A
repair cassette whose prompt holds no card list keeps the old rule, so a hit in cards the scan could not
read is never set aside.

Every cassette here is invented and written as the recorder writes one (`repair_prompt` and a
`ModelRequest`): invented card text, positions, schools, team codes (`OR`, `WB`) and tournament.
`Confidence` is a school spelled like a key of every answer, and `or` a team-code word of the taxonomy's
description, as in `v1-e32-t44`'s tests.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel

from debate_core.application.errors import OutputProblem
from debate_core.application.structured_output import repair_prompt
from debate_core.arguments.landscape.headings import NormalizedHeading
from debate_core.arguments.landscape.model_stage import (
    ModelCandidate,
    ModelItem,
    NameScan,
    prompt_variables,
)
from debate_core.arguments.landscape.scan_hits import (
    HitField,
    HitKind,
    ScanHit,
    ScanNames,
    cassette_hits,
    mark_counts,
    marked_scan,
    repair_cassette_hits,
)
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.model_contracts import ModelPrompt, ModelRequest, RenderedPrompt, TaskClass
from debate_core.integrations.models.prompt_registry import PromptRegistry

REPOSITORY = Path(__file__).resolve().parents[5]
CASELIST_NAMES = {"Confidence": ("OR",), "Willow Bend": ("WB",)}
TOURNAMENTS = ("Pinecrest Open",)
TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            {
                "id": "localities-cp",
                "label": "Localities CP",
                "kind": "cp",
                "side": "neg",
                "description": "The states or the localities act instead",
            },
        ],
    }
)
POSITIONS = str(prompt_variables(TAXONOMY, ())["positions"])
NAMES = ScanNames.of(CASELIST_NAMES, TOURNAMENTS, taxonomy_text=POSITIONS)
CLASSIFY = "landscape.classify_position"
FAILED_VERSION = "1.3.1"
SYSTEM = "Sort each card into a position. Give a confidence and a rationale, one or two short sentences."
"""The invented failed prompt's instructions: a JSON key's name (`confidence`) and a taxonomy word (`or`)."""
PROBLEMS = (OutputProblem(loc=("answers", 0, "rationale"), type="string_too_long", msg="String too long"),)


class InventedAnswer(BaseModel):
    item: str
    position_id: str | None
    confidence: float
    rationale: str


# The invented failed call's schema. A docstring would be its JSON schema's description, so it has none:
# the schema names `confidence` twice, as its field's title and in its `required` list.
class InventedAnswers(BaseModel):
    answers: list[InventedAnswer]


class PlainAnswer(BaseModel):
    item: str
    rationale: str


# An invented schema naming nothing on the scan's lists.
class PlainAnswers(BaseModel):
    answers: list[PlainAnswer]


def card(
    tag: str = "Spending tradeoff",
    *,
    headings: Sequence[str] = ("Budget",),
    cite: str = "Smith 2024",
    excerpt: str = "the states act first",
) -> ModelItem:
    """One invented card, as the stage sends it."""
    return ModelItem(
        candidate=ModelCandidate(
            fingerprint="f" * 64,
            source_sha256="a" * 64,
            first_element_index=0,
            headings=tuple(NormalizedHeading(text=one, answer=False) for one in headings),
            tag=tag,
            short_cite=cite,
            own_names=(),
        ),
        excerpt=excerpt,
    )


def failed_call(cards: Sequence[ModelItem]) -> ModelPrompt:
    return ModelPrompt(
        prompt_id=CLASSIFY, prompt_version=FAILED_VERSION, variables=prompt_variables(TAXONOMY, cards)
    )


def rendered_as_invented(failed: ModelPrompt) -> RenderedPrompt:
    """The failed call rendered as the classify prompt lays it out: instructions and positions in the system
    turn, a preamble and the cards' JSON list in the user turn. The instructions are invented."""
    variables = failed.variables
    return RenderedPrompt(
        system=f"{SYSTEM}\n\nThe positions:\n\n{variables['positions']}",
        user=f"The cards, as a JSON list.\n\n{variables['items']}",
    )


def repair_cassette(
    rationale: str,
    cards: Sequence[ModelItem] = (),
    *,
    rendered: RenderedPrompt | None = None,
    schema: type[BaseModel] = InventedAnswers,
) -> str:
    """A `model.repair` cassette as the recorder writes it: the repair call's request, then its answer."""
    failed = failed_call(cards or (card(),))
    repair = repair_prompt(failed, rendered or rendered_as_invented(failed), schema, PROBLEMS)
    request = ModelRequest(
        task_class=TaskClass.COMPLEX_REASONING, prompt=repair, output_schema="example.InventedAnswers"
    )
    return json.dumps(
        {
            "call": "generate_structured",
            "caselists": ["hspolicy99"],
            "cassette_format": 1,
            "key": "0" * 64,
            "request": request.model_dump(mode="json"),
            "response": {
                "output": {
                    "answers": [
                        {
                            "item": "item-1",
                            "position_id": "localities-cp",
                            "confidence": 0.8,
                            "rationale": rationale,
                        }
                    ]
                },
                "prompt_id": "model.repair",
                "route": {"model_id": "recorded-model"},
            },
        },
        indent=2,
        sort_keys=True,
    )


def first_call_cassette(rationale: str, cards: Sequence[ModelItem] = ()) -> str:
    """A `landscape.classify_position` cassette: its request's variables are the cards and the positions."""
    request = ModelRequest(
        task_class=TaskClass.COMPLEX_REASONING,
        prompt=failed_call(cards or (card(),)),
        output_schema="example.InventedAnswers",
    )
    return json.dumps(
        {
            "call": "generate_structured",
            "caselists": ["hspolicy99"],
            "request": request.model_dump(mode="json"),
            "response": {
                "output": {"answers": [{"item": "item-1", "confidence": 0.8, "rationale": rationale}]},
                "route": {"model_id": "recorded-model"},
            },
        },
        sort_keys=True,
    )


def marks(hits: Sequence[ScanHit]) -> set[tuple[HitField, HitKind, str, bool, bool, bool]]:
    """Each hit's field, kind and words, and its marks: in the input, a JSON key, a taxonomy word."""
    return {(hit.where, hit.kind, hit.matched, hit.in_input, hit.json_key, hit.in_taxonomy) for hit in hits}


def repair_scan(
    texts: Sequence[str], names: ScanNames = NAMES, others: Sequence[str] = TOURNAMENTS
) -> NameScan:
    """The evaluation's repair cassette scan of `texts`, judged by their hits' marks."""
    return marked_scan(
        texts,
        lambda text: repair_cassette_hits("repair cassette", text, names),
        CASELIST_NAMES,
        others,
        leave_out=(POSITIONS,),
    )


MODEL_WORDS = "read with confidence: the states or the localities act"
"""The repair call's answer: a JSON key's name and a taxonomy word, neither in the invented card."""

R = HitField.REPAIRED_PROMPT
SCHOOL, CODE = HitKind.SCHOOL, HitKind.TEAM_CODE


def test_repair_cassette_scan_marks_no_hit_outside_its_cards_as_in_the_input() -> None:
    """The instructions' and the answer's `confidence` and `or` are not the card's words: not in the input,
    each set aside by its trusted mark. The schema's `Confidence` title and `required` entry are metadata, set
    aside alike."""
    hits = repair_cassette_hits("repair cassette 1", repair_cassette(MODEL_WORDS), NAMES)

    assert marks(hits) == {
        (R, SCHOOL, "confidence", False, True, False),
        (R, CODE, "or", False, False, True),
        (HitField.RATIONALE, SCHOOL, "confidence", False, True, False),
        (HitField.RATIONALE, CODE, "or", False, False, True),
        (HitField.METADATA, SCHOOL, "confidence", False, True, False),
    }
    assert len(hits) == 6


def test_repair_cassette_scan_of_model_words_not_in_its_cards_is_clean() -> None:
    scan = repair_scan([repair_cassette(MODEL_WORDS)])

    assert scan.clean
    assert (scan.texts, scan.schools, scan.team_codes, scan.other_names, scan.texts_left) == (1, 1, 1, 0, 0)
    assert scan.set_aside == {"texts": 1, "hits": 6, "json_key": 4, "in_taxonomy": 2}


@pytest.mark.parametrize(
    "sent",
    [
        card(tag="The states or the center"),
        card(headings=("Budget", "States or center")),
        card(cite="Lee or Smith 2024"),
        card(excerpt="the states or the center act"),
    ],
    ids=["tag", "heading", "cite", "excerpt"],
)
def test_repair_cassette_scan_keeps_a_word_its_cards_sent(sent: ModelItem) -> None:
    """The taxonomy word `or` in a card's field: every `or` hit is in the input, the card's own among them,
    and its text is left. `confidence` is still in no card."""
    text = repair_cassette(MODEL_WORDS, (sent,))
    hits = repair_cassette_hits("repair cassette 1", text, NAMES)

    assert {(hit.matched, hit.in_input) for hit in hits} == {("or", True), ("confidence", False)}
    assert (R, CODE, "or", True, False, True) in marks(hits)
    scan = repair_scan([text])
    assert not scan.clean
    assert (scan.team_codes, scan.texts_left) == (1, 1)
    assert scan.set_aside == {"texts": 0, "hits": 0, "json_key": 0, "in_taxonomy": 0}


def test_repair_cassette_scan_keeps_a_school_spelled_like_a_key_when_a_card_sent_it() -> None:
    text = repair_cassette(MODEL_WORDS, (card(tag="Confidence in the states"),))
    hits = repair_cassette_hits("repair cassette 1", text, NAMES)

    assert {(hit.matched, hit.in_input) for hit in hits} == {("confidence", True), ("or", False)}
    assert not repair_scan([text]).clean


def test_repair_cassette_scan_reads_the_cards_in_every_card_of_the_list() -> None:
    """The word in the second card of a batch counts as much as the first's."""
    text = repair_cassette(MODEL_WORDS, (card(), card(tag="The states or the center")))
    hits = repair_cassette_hits("repair cassette 1", text, NAMES)

    assert {hit.in_input for hit in hits if hit.matched == "or"} == {True}
    assert not repair_scan([text]).clean


def test_repair_cassette_scan_counts_a_cards_key_as_structure_not_a_card_sent() -> None:
    """A school spelled like a card's key (`cite`) is in the rendered cards' JSON, but only as a key."""
    names = ScanNames.of({"Cite": ("CT",)}, (), taxonomy_text=POSITIONS)
    text = repair_cassette("a plain reason")
    hits = repair_cassette_hits("repair cassette 1", text, names)

    assert marks(hits) == {(R, SCHOOL, "cite", False, True, False)}
    scan = marked_scan(
        [text],
        lambda one: repair_cassette_hits("repair cassette", one, names),
        {"Cite": ("CT",)},
        leave_out=(POSITIONS,),
    )
    assert scan.clean
    assert (scan.schools, scan.set_aside["hits"]) == (1, len(hits))


def test_repair_cassette_scan_keeps_a_team_code_in_the_model_words() -> None:
    """`wb` carries no trusted mark: it is no card's, and still kept."""
    text = repair_cassette("as the wb team reads the states")
    hits = repair_cassette_hits("repair cassette 1", text, NAMES)

    assert (HitField.RATIONALE, CODE, "wb", False, False, False) in marks(hits)
    scan = repair_scan([text])
    assert not scan.clean
    assert scan.texts_left == 1


def test_repair_cassette_scan_keeps_a_team_name_in_the_model_words() -> None:
    """A tournament spelled like the school `Confidence`: a team's name, kept though a key and no card's."""
    names = ScanNames.of(CASELIST_NAMES, ("Confidence",), taxonomy_text=POSITIONS)
    hits = repair_cassette_hits("repair cassette 1", repair_cassette(MODEL_WORDS), names)

    team_names = {(hit.where, hit.json_key, hit.in_input) for hit in hits if hit.team_name}
    assert (HitField.RATIONALE, True, False) in team_names
    scan = repair_scan([repair_cassette(MODEL_WORDS)], names, others=("Confidence",))
    assert not scan.clean


def test_repair_cassette_scan_with_no_card_list_counts_its_whole_failed_prompt_as_sent() -> None:
    """A failed prompt the scan cannot read cards from keeps the rule before `v1-e32-t59`: every word of it
    is in the input, so no hit whose words it holds is set aside."""
    prose = RenderedPrompt(system=f"{SYSTEM}\n\n{POSITIONS}", user="The cards: the states or the center act")
    hits = repair_cassette_hits("repair cassette 1", repair_cassette(MODEL_WORDS, rendered=prose), NAMES)

    assert {(hit.matched, hit.in_input) for hit in hits} == {("or", True), ("confidence", True)}
    assert not repair_scan([repair_cassette(MODEL_WORDS, rendered=prose)]).clean


def test_repair_cassette_scan_with_only_the_positions_list_counts_its_whole_failed_prompt_as_sent() -> None:
    """The positions are a JSON list too, but not cards: a prompt holding no other list has no cards read."""
    listed = POSITIONS.replace("localities", "towns")
    prose = RenderedPrompt(system=f"{SYSTEM}\n\n{listed}", user="The cards: none readable")
    hits = repair_cassette_hits("repair cassette 1", repair_cassette(MODEL_WORDS, rendered=prose), NAMES)

    assert {hit.in_input for hit in hits} == {True}
    assert not repair_scan([repair_cassette(MODEL_WORDS, rendered=prose)]).clean


def test_repair_cassette_scan_clean_flag_and_counts_over_several_cassettes() -> None:
    """One set aside, one left for the word its card sent, one naming nothing."""
    texts = [
        repair_cassette(MODEL_WORDS),
        repair_cassette(MODEL_WORDS, (card(tag="The states or the center"),)),
        repair_cassette(
            "a plain reason",
            rendered=RenderedPrompt(system="Sort the cards.", user="[]"),
            schema=PlainAnswers,
        ),
    ]

    scan = repair_scan(texts)

    assert not scan.clean
    assert (scan.texts, scan.schools, scan.team_codes, scan.other_names, scan.texts_left) == (3, 2, 2, 0, 1)
    assert scan.set_aside == {"texts": 1, "hits": 6, "json_key": 4, "in_taxonomy": 2}
    assert repair_scan([texts[0], texts[2]]).clean
    hits = repair_cassette_hits("repair cassette 1", texts[0], NAMES)
    assert mark_counts(hits) == {
        "cassette metadata": {"hits": 2, "team_name": 0, "in_taxonomy": 0, "json_key": 2, "in_input": 0},
        "model rationale": {"hits": 2, "team_name": 0, "in_taxonomy": 1, "json_key": 1, "in_input": 0},
        "repaired prompt": {"hits": 2, "team_name": 0, "in_taxonomy": 1, "json_key": 1, "in_input": 0},
    }


def test_repair_cassette_scan_of_the_classify_prompt_as_its_registry_renders_it() -> None:
    """The failed prompt rendered by the committed classify prompt and the stage's own answer schema: the
    cards are found in its user turn, so its instructions' words are not in the input, and a card's are."""
    prompts = PromptRegistry.load(REPOSITORY / "prompts")
    schema = prompts.get(CLASSIFY, FAILED_VERSION).schema

    def recorded(cards: Sequence[ModelItem]) -> str:
        return repair_cassette(MODEL_WORDS, cards, rendered=prompts.render(failed_call(cards)), schema=schema)

    plain = repair_cassette_hits("repair cassette 1", recorded((card(),)), NAMES)
    assert {hit.where for hit in plain} >= {R, HitField.RATIONALE}
    assert {hit.in_input for hit in plain} == {False}
    assert repair_scan([recorded((card(),))]).clean

    sent = repair_cassette_hits("repair cassette 1", recorded((card(tag="The states or the center"),)), NAMES)
    assert {hit.in_input for hit in sent if hit.matched == "or"} == {True}
    assert {hit.in_input for hit in sent if hit.matched == "confidence"} == {False}


def test_first_call_cassette_scan_marks_as_before_t59() -> None:
    """A classify cassette's input is its `items` variable, as before: a rationale's word is in the input
    only when the card sent it, and the positions it sent are left out."""
    plain = cassette_hits("cassette 1", first_call_cassette(MODEL_WORDS), NAMES)
    assert marks(plain) == {
        (HitField.RATIONALE, SCHOOL, "confidence", False, True, False),
        (HitField.RATIONALE, CODE, "or", False, False, True),
    }

    sent = cassette_hits(
        "cassette 1", first_call_cassette(MODEL_WORDS, (card(tag="The states or the center"),)), NAMES
    )
    assert marks(sent) == {
        (HitField.TAG, CODE, "or", True, False, True),
        (HitField.RATIONALE, SCHOOL, "confidence", False, True, False),
        (HitField.RATIONALE, CODE, "or", True, False, True),
    }


def test_first_call_cassette_scan_clean_flag_as_before_t59() -> None:
    def scanned(texts: Sequence[str]) -> NameScan:
        return marked_scan(
            texts,
            lambda text: cassette_hits("cassette", text, NAMES),
            CASELIST_NAMES,
            TOURNAMENTS,
            leave_out=(POSITIONS,),
        )

    clean = scanned([first_call_cassette(MODEL_WORDS)])
    assert clean.clean
    assert clean.set_aside == {"texts": 1, "hits": 2, "json_key": 1, "in_taxonomy": 1}
    kept = scanned([first_call_cassette(MODEL_WORDS, (card(tag="The states or the center"),))])
    assert (kept.clean, kept.texts_left) == (False, 1)
