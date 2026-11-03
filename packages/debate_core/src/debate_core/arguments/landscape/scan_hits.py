"""Where the name scan's hits are, for the operator's terminal only (`v1-e32-t39`).

:func:`~debate_core.arguments.landscape.model_stage.name_scan` counts the texts holding a school of the
caselist, a word of a team code, or one of the other names (the disclosing teams' school, code and
tournament), and names none of them. To tell a name the scrub missed from an ordinary word, the
operator needs each hit: the text it is in (an input batch, a cassette, a repair cassette), the field
(:class:`HitField`), the kind (:class:`HitKind`), the matched words and a few words either side.

This module finds them by the scan's own rule, the same three lists matched as whole lowercase words
(:func:`~debate_core.arguments.landscape.matcher.tag_words`), field by field. A text the scan counts for a
kind always has a hit of that kind listed: a match no named field holds, such as one in a text that is not
JSON, is listed as :attr:`HitField.ACROSS_FIELDS` from the text's values.

Since `v1-e32-t40`, as the scan does (:func:`~debate_core.arguments.landscape.model_stage.name_scan`), it
reads field values and never a JSON key, leaves out the committed positions text the prompt sends (a
cassette's `positions`, and the same text in a repair cassette's copy of the failed prompt), and the third
list holds the disclosing teams' tournaments only.

**A hit is for the terminal.** A :class:`ScanHit` withholds its words from its `repr`, and nothing here
logs or writes. Only :func:`hit_counts`, by kind and field, may be written down.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
from collections import Counter
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, cast

from debate_core.arguments.landscape.matcher import tag_words
from debate_core.arguments.landscape.model_stage import json_values, scanned_values

__all__ = [
    "CONTEXT_WORDS",
    "HitField",
    "HitKind",
    "ScanHit",
    "ScanNames",
    "cassette_hits",
    "hit_counts",
    "input_batch_hits",
    "mark_counts",
    "repair_cassette_hits",
]

CONTEXT_WORDS: Final = 4
"""Words shown either side of a hit."""


class HitKind(StrEnum):
    """Which of the scan's lists a hit's words are on."""

    SCHOOL = "school"
    TEAM_CODE = "team-code word"
    TOURNAMENT = "tournament"
    """The scan's third list: every disclosing team's tournament (`name_scan`'s `other_names`). Until
    `v1-e32-t40` each team's school and code were on it too (:attr:`ScanHit.team_name`)."""


class HitField(StrEnum):
    """Where in a text a hit is."""

    HEADINGS = "heading path"
    TAG = "tag"
    CITE = "short cite"
    EXCERPT = "excerpt"
    RATIONALE = "model rationale"
    TAXONOMY = "taxonomy positions"
    """The prompt's `positions` variable, less the committed taxonomy's text
    (:attr:`ScanNames.taxonomy_text`): a cassette recorded under another taxonomy shows what differs."""
    REPAIRED_PROMPT = "repaired prompt"
    """A repair cassette's copy of the failed call's prompt, as rendered: its cards and its taxonomy."""
    METADATA = "cassette metadata"
    """Anything else of a cassette: its key, caselists, route, usage, schema, ids and JSON keys."""
    ACROSS_FIELDS = "across fields"
    """A match the scan finds in a value of the text that no named field holds."""


_ITEM_FIELDS: Final = {"tag": HitField.TAG, "cite": HitField.CITE, "excerpt": HitField.EXCERPT}

_PROMPT_KEYS: Final = frozenset(
    tag_words(
        "item headings under_an_answer_heading tag cite excerpt id kind label side parent description"
    ).split()
)
"""The words of the keys of a card and of a position as `prompt_variables` writes them."""


@dataclass(frozen=True, slots=True)
class ScanNames:
    """The scan's three lists, as words: schools, team-code words, and the other names."""

    schools: tuple[str, ...] = field(repr=False)
    codes: frozenset[str] = field(repr=False)
    others: tuple[str, ...] = field(repr=False)
    taxonomy_words: str = field(default="", repr=False)
    """The committed taxonomy's words, padded: a hit's words found here are ordinary vocabulary."""
    taxonomy_text: str = field(default="", repr=False)
    """The committed positions text as the prompt sends it, left out of every value (`v1-e32-t40`)."""

    @classmethod
    def of(
        cls,
        caselist_names: Mapping[str, Sequence[str]],
        other_names: Iterable[str] = (),
        *,
        taxonomy_text: str = "",
    ) -> ScanNames:
        """The lists :func:`~debate_core.arguments.landscape.model_stage.name_scan` reads, built alike."""
        return cls(
            schools=tuple(words for words in map(tag_words, caselist_names) if words),
            codes=frozenset(
                word
                for codes in caselist_names.values()
                for code in codes
                for word in tag_words(code).split()
            ),
            others=tuple(words for words in map(tag_words, other_names) if words),
            taxonomy_words=f" {tag_words(taxonomy_text)} ",
            taxonomy_text=taxonomy_text,
        )

    @property
    def leave_out(self) -> tuple[str, ...]:
        """The committed text no value is read with."""
        return (self.taxonomy_text,) if self.taxonomy_text else ()

    def phrases(self) -> Iterator[tuple[HitKind, str]]:
        yield from ((HitKind.SCHOOL, one) for one in dict.fromkeys(self.schools))
        yield from ((HitKind.TEAM_CODE, one) for one in sorted(self.codes))
        yield from ((HitKind.TOURNAMENT, one) for one in dict.fromkeys(self.others))

    def is_team_name(self, phrase: str) -> bool:
        """Whether `phrase` is a school of the caselist, or wholly words of its team codes."""
        return phrase in self.schools or all(word in self.codes for word in phrase.split())


@dataclass(frozen=True, slots=True)
class ScanHit:
    """One match of the scan: where, of what kind, and the words. For the operator's terminal only."""

    text: str
    """Which text: `input batch 2`, `cassette 1`, `repair cassette 1`. A label, never a file name."""
    where: HitField
    """The field of the text it is in."""
    kind: HitKind
    matched: str = field(repr=False)
    before: str = field(repr=False)
    """Up to :data:`CONTEXT_WORDS` words before the match, in the field."""
    after: str = field(repr=False)
    team_name: bool = False
    """A :attr:`HitKind.TOURNAMENT` hit whose words are also a school or team code of the caselist."""
    in_taxonomy: bool = False
    """The matched words are words of the committed taxonomy too: vocabulary, not only a name."""
    json_key: bool = False
    """Every matched word is a word of a JSON key of the text (`tag`, `item`...): structure, not content."""
    in_input: bool = False
    """The matched words occur in the cards the text sent (their heading paths, tags, cites and
    excerpts; a repair cassette's repaired prompt): a rationale or metadata hit marked so repeats them."""


def _matches(words: Sequence[str], phrase: str) -> Iterator[int]:
    wanted = phrase.split()
    size = len(wanted)
    for start in range(len(words) - size + 1):
        if list(words[start : start + size]) == wanted:
            yield start


def _hits_in(text_label: str, where: HitField, value: str, names: ScanNames) -> list[ScanHit]:
    words = tag_words(value).split()
    found: list[ScanHit] = []
    for kind, phrase in names.phrases():
        size = len(phrase.split())
        for start in _matches(words, phrase):
            found.append(
                ScanHit(
                    text=text_label,
                    where=where,
                    kind=kind,
                    matched=phrase,
                    before=" ".join(words[max(0, start - CONTEXT_WORDS) : start]),
                    after=" ".join(words[start + size : start + size + CONTEXT_WORDS]),
                    team_name=kind is HitKind.TOURNAMENT and names.is_team_name(phrase),
                    in_taxonomy=f" {phrase} " in names.taxonomy_words,
                )
            )
    return found


def _across(text_label: str, whole: str, found: list[ScanHit], names: ScanNames) -> list[ScanHit]:
    """The scan's matches in `whole`'s values of a kind no field's hit has: the scan counts them, so they
    show."""
    listed = {hit.kind for hit in found}
    return [
        hit
        for value in scanned_values(whole, names.leave_out)
        for hit in _hits_in(text_label, HitField.ACROSS_FIELDS, value, names)
        if hit.kind not in listed
    ]


def _key_words(value: object) -> set[str]:
    """The words of every key of a JSON value, and of the JSON a string in it holds."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, inner in cast(dict[str, object], value).items():
            found |= set(tag_words(key).split()) | _key_words(inner)
    elif isinstance(value, list):
        for inner in cast(list[object], value):
            found |= _key_words(inner)
    elif isinstance(value, str) and value.startswith(("[", "{")):
        with contextlib.suppress(json.JSONDecodeError):
            found |= _key_words(json.loads(value))
    return found


def _marked(hits: list[ScanHit], *, keys: Collection[str], sent: str) -> list[ScanHit]:
    """`hits` with :attr:`ScanHit.json_key` and :attr:`ScanHit.in_input` set, against one text's keys
    and the words of the cards it sent."""
    padded = f" {sent} "
    return [
        dataclasses.replace(
            hit,
            json_key=all(word in keys for word in hit.matched.split()),
            in_input=f" {hit.matched} " in padded,
        )
        for hit in hits
    ]


def _sent_words(items: object) -> str:
    return " ".join(tag_words(value) for _, value in _fields_of_items(items))


def _fields_of_items(value: object) -> Iterator[tuple[HitField, str]]:
    """The free-text fields of a batch's `items` variable: each card's heading path, tag, cite, excerpt."""
    try:
        items: object = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return
    if not isinstance(items, list):
        return
    for item in cast(list[object], items):
        if not isinstance(item, dict):
            continue
        card = cast(dict[str, object], item)
        headings = card.get("headings")
        if isinstance(headings, list):
            yield HitField.HEADINGS, " ".join(str(one) for one in cast(list[object], headings))
        for key, where in _ITEM_FIELDS.items():
            text = card.get(key)
            if isinstance(text, str):
                yield where, text


def input_batch_hits(text_label: str, items: str, names: ScanNames) -> list[ScanHit]:
    """The hits in one batch's `items` variable as sent, field by field."""
    found = [
        hit for where, value in _fields_of_items(items) for hit in _hits_in(text_label, where, value, names)
    ]
    return _marked(
        found + _across(text_label, items, found, names),
        keys=_PROMPT_KEYS | _key_words(items),
        sent=_sent_words(items),
    )


def _rationales(response: Mapping[str, object]) -> list[str]:
    output = response.get("output")
    answers = cast(dict[str, object], output).get("answers") if isinstance(output, dict) else None
    found: list[str] = []
    for answer in cast(list[object], answers) if isinstance(answers, list) else []:
        if isinstance(answer, dict):
            rationale = cast(dict[str, object], answer).get("rationale")
            if isinstance(rationale, str):
                found.append(rationale)
                cast(dict[str, object], answer)["rationale"] = None
    return found


def _document(text: str) -> dict[str, object] | None:
    try:
        loaded: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return cast(dict[str, object], loaded) if isinstance(loaded, dict) else None


def _variables(document: Mapping[str, object]) -> dict[str, object]:
    request = document.get("request")
    prompt = cast(dict[str, object], request).get("prompt") if isinstance(request, dict) else None
    variables = cast(dict[str, object], prompt).get("variables") if isinstance(prompt, dict) else None
    return cast(dict[str, object], variables) if isinstance(variables, dict) else {}


def _response(document: Mapping[str, object]) -> dict[str, object]:
    response = document.get("response")
    return cast(dict[str, object], response) if isinstance(response, dict) else {}


def cassette_hits(text_label: str, cassette: str, names: ScanNames) -> list[ScanHit]:
    """The hits in one `landscape.classify_position` cassette, as the file reads.

    Its cards' fields as the request sent them, the taxonomy it sent, the model's rationales, and
    everything else as metadata. A file that is not a cassette's JSON is read whole, across fields.
    """
    document = _document(cassette)
    if document is None:
        return _hits_in(text_label, HitField.ACROSS_FIELDS, cassette, names)
    keys = _PROMPT_KEYS | _key_words(document)
    variables = _variables(document)
    items = variables.pop("items", None)
    found = [
        hit for where, value in _fields_of_items(items) for hit in _hits_in(text_label, where, value, names)
    ]
    positions = variables.pop("positions", None)
    if isinstance(positions, str):
        found += [
            hit
            for value in json_values(positions, names.leave_out)
            for hit in _hits_in(text_label, HitField.TAXONOMY, value, names)
        ]
    found += _rationale_and_metadata(text_label, document, names)
    return _marked(found + _across(text_label, cassette, found, names), keys=keys, sent=_sent_words(items))


def repair_cassette_hits(text_label: str, cassette: str, names: ScanNames) -> list[ScanHit]:
    """The hits in one `model.repair` cassette: the failed call's prompt it carries, the rationales, the rest.

    The evaluation's scan does not read these (it reads the classify prompt's cassettes alone), but each
    holds the failed call's rendered prompt, its cards with it.
    """
    document = _document(cassette)
    if document is None:
        return _hits_in(text_label, HitField.ACROSS_FIELDS, cassette, names)
    keys = _PROMPT_KEYS | _key_words(document)
    variables = _variables(document)
    found: list[ScanHit] = []
    repaired: list[str] = []
    for key in ("failed_system", "failed_user"):
        value = variables.pop(key, None)
        if isinstance(value, str):
            for part in json_values(value, names.leave_out):
                found += _hits_in(text_label, HitField.REPAIRED_PROMPT, part, names)
                repaired.append(tag_words(part))
    found += _rationale_and_metadata(text_label, document, names)
    return _marked(found + _across(text_label, cassette, found, names), keys=keys, sent=" ".join(repaired))


def _rationale_and_metadata(text_label: str, document: dict[str, object], names: ScanNames) -> list[ScanHit]:
    """The rationales' hits, then the rest's: `document` has had its read fields taken out (set to None)."""
    found = [
        hit
        for rationale in _rationales(_response(document))
        for hit in _hits_in(text_label, HitField.RATIONALE, rationale, names)
    ]
    for value in json_values(document, names.leave_out):
        found += _hits_in(text_label, HitField.METADATA, value, names)
    return found


def mark_counts(hits: Iterable[ScanHit]) -> dict[str, dict[str, int]]:
    """By field, how many hits carry each mark: counts only, which may be written down."""
    found: dict[str, Counter[str]] = {}
    for hit in hits:
        marks = found.setdefault(hit.where.value, Counter())
        marks["hits"] += 1
        for name in ("team_name", "in_taxonomy", "json_key", "in_input"):
            marks[name] += getattr(hit, name)
    return {where: dict(marks) for where, marks in sorted(found.items())}


def hit_counts(hits: Iterable[ScanHit]) -> dict[str, dict[str, int]]:
    """Hits by kind, then by field: counts only, which may be written down and committed."""
    found: dict[str, Counter[str]] = {}
    for hit in hits:
        found.setdefault(hit.kind.value, Counter())[hit.where.value] += 1
    return {kind: dict(sorted(fields.items())) for kind, fields in sorted(found.items())}
