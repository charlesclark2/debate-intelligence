"""A kritikal affirmative's markers, read from an affirmative file (`v1-e32-t17`).

`v1-e32-t09` identifies an aff by its plan text, so a kritikal affirmative, which has an advocacy statement
or a method and no plan, was left among the rounds with no identified aff. The PM's rulings of 2026-10-25
on this task's counts: one generic K-aff position per topic (its id is config,
`config/landscape/kritikal_affs/<topic id>.yaml`), named for a round when a file of it holds no plan
text and one or more of these markers. They are read as `v1-e32-t11` reads its labels, from the file's
own paragraphs, beside t09's plan texts and in the same cache, and only what is derived is kept: the
marker's kind, how it was written, where it is and its unit. Never its words: an advocacy statement is
not quotable under data-use policy 1.13, so it is counted and never shown.

## The markers (:func:`read_kritikal_markers`)

A **label** is a non-evidence paragraph of at most 8 words that t01's normalizer reduces to the label,
with a text under it (a tag, an analytic, an undertag or an unstyled paragraph), as t11's labels are. An
**inline** label opens a longer paragraph and is not a heading; a **sentence** opens the paragraph.

* **Role of the ballot:** t11's labels, inline labels and sentences, read by t11's own rule
  (:func:`~debate_core.arguments.landscape.analytic_texts.role_of_the_ballot_form`).
* **Advocacy statement:** `Advocacy` or `Advocacy statement` as a label; inline `Advocacy:` or `Advocacy
  statement:`; the sentence `Our advocacy is` or `Our advocacy statement is`.
* **The 1AC:** the sentence `The 1AC is`.
* **Method:** `Method` as a label; inline `Method:`; the sentence `Our method is`. Left out: `Methods`,
  which heads a policy aff's study block (8 of 8 control files with it had a plan text naming an aff).

## The K families (:func:`heading_families`)

The report's K-aff group counts the K families its files' headings name: the config's phrases, matched
as whole words in each pocket, hat and block heading as the normalizer writes it, a longer phrase first
so that `racial cap` is not also `cap`. A count of words, never a placement: a family names no position
and identifies no round, and nothing is read from a tag.

Pure and deterministic: no I/O, no model, and nothing returned or logged holds a paragraph's text.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Final, Literal, Protocol

from pydantic import Field, StringConstraints, model_validator

from debate_core.arguments.landscape.analytic_texts import (
    MAX_LABEL_WORDS,
    TEXT_UNITS,
    label_form,
    role_of_the_ballot_form,
)
from debate_core.arguments.landscape.source_headings import CaselistNames, normalize_source_heading
from debate_core.domain.base import DomainModel, NonEmptyText
from debate_core.domain.landscape import POSITION_ID_PATTERN
from debate_core.domain.landscape_texts import TextForm
from debate_core.domain.style_profile import StructuralUnit

__all__ = [
    "ADVOCACY_LABELS",
    "METHOD_LABELS",
    "KritikalAffConfig",
    "KritikalAffInputs",
    "KritikalFamily",
    "KritikalMarker",
    "KritikalMarkerKind",
    "KritikalReading",
    "heading_families",
    "kritikal_rules",
    "read_kritikal_markers",
]

ADVOCACY_LABELS: Final = frozenset({"advocacy", "advocacy statement"})
METHOD_LABELS: Final = frozenset({"method"})
_RULE_VERSION: Final = "kritikal-aff-1"
"""Bumped when how a marker or a family is found changes, so a cached reading is read again."""
_SEPARATOR: Final = r"\s*[:\-–—]\s*(?=\S)"
_ADVOCACY_INLINE: Final = re.compile(r"^\s*advocacy(?:\s+statement)?" + _SEPARATOR, re.IGNORECASE)
_ADVOCACY_SENTENCE: Final = re.compile(r"^\s*our\s+advocacy(?:\s+statement)?\s+is\b", re.IGNORECASE)
_THE_1AC_SENTENCE: Final = re.compile(r"^\s*the\s+1ac\s+is\b", re.IGNORECASE)
_METHOD_INLINE: Final = re.compile(r"^\s*method" + _SEPARATOR, re.IGNORECASE)
_METHOD_SENTENCE: Final = re.compile(r"^\s*our\s+method\s+is\b", re.IGNORECASE)
_HEADING_UNITS: Final = frozenset({StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK})
_NOT_TEXT_UNITS: Final = frozenset({StructuralUnit.EVIDENCE, StructuralUnit.CITE})

Phrase = Annotated[str, StringConstraints(pattern=r"^[0-9a-z]+(?: [0-9a-z]+)*$")]
FamilyId = Annotated[str, StringConstraints(pattern=POSITION_ID_PATTERN)]


class KritikalMarkerKind(StrEnum):
    ROLE_OF_THE_BALLOT = "ROLE_OF_THE_BALLOT"
    ADVOCACY = "ADVOCACY"
    THE_1AC = "THE_1AC"
    METHOD = "METHOD"


class ReadParagraph(Protocol):
    """A paragraph as t09's and t11's readers hold one: where it is, its unit and its text."""

    @property
    def element_index(self) -> int: ...

    @property
    def unit(self) -> StructuralUnit: ...

    @property
    def text(self) -> str: ...


class KritikalFamily(DomainModel):
    """One K family the report's K-aff group counts in headings, and the phrases that name it."""

    id: FamilyId = Field(description="Stable kebab-case id.")
    label: NonEmptyText = Field(description="The name the report prints.")
    phrases: tuple[Phrase, ...] = Field(
        min_length=1, description="Lowercase words, matched whole in a heading."
    )


class KritikalAffConfig(DomainModel):
    """`config/landscape/kritikal_affs/<topic id>.yaml`: the topic's K-aff position and its K families."""

    schema_version: Literal[1] = Field(default=1, description="Version of this file's shape.")
    topic_id: Annotated[str, StringConstraints(pattern=POSITION_ID_PATTERN)] = Field(
        description="The topic, as `topics.yaml` names it."
    )
    position_id: Annotated[str, StringConstraints(pattern=POSITION_ID_PATTERN)] = Field(
        description="The active aff a file with a K-aff marker and no plan text names."
    )
    families: tuple[KritikalFamily, ...] = Field(
        default=(), description="The K families counted in headings."
    )

    @model_validator(mode="after")
    def _check_families(self) -> KritikalAffConfig:
        ids = [one.id for one in self.families]
        if len(ids) != len(set(ids)):
            raise ValueError("a family id is listed twice")
        phrases = [phrase for one in self.families for phrase in one.phrases]
        if len(phrases) != len(set(phrases)):
            raise ValueError("a phrase names two families, or one twice")
        return self


@dataclass(frozen=True, slots=True)
class KritikalMarker:
    """What is kept of one marker: its kind, how it was written, where it is. Never its words."""

    kind: KritikalMarkerKind
    form: TextForm
    element_index: int
    unit: StructuralUnit


@dataclass(frozen=True, slots=True)
class KritikalReading:
    """One file's K-aff markers, in file order, and the K families its headings name, sorted."""

    markers: tuple[KritikalMarker, ...] = ()
    heading_families: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KritikalAffInputs:
    """What the landscape report is given of the caselist's kritikal affirmatives (`v1-e32-t17`)."""

    position_id: str
    marker_sources: frozenset[str] = field(repr=False)
    """The affirmative sources holding a K-aff marker and no plan text, by digest."""
    heading_families: Mapping[str, tuple[str, ...]] = field(repr=False)
    """Each affirmative source's K families named in its headings, by digest; sources naming none left out."""
    families: Mapping[str, str] = field(repr=False)
    """Each family's label, by id, in the config's order."""
    refused_by_advantage: frozenset[str] = field(repr=False)
    """The rounds a K aff was not carried into because their own file reads an advantage."""


def kritikal_rules(config: KritikalAffConfig | None) -> list[object]:
    """What the plan-text vocabulary's digest takes of the K-aff reading: its rules and the config."""
    if config is None:
        return []
    return [
        _RULE_VERSION,
        sorted(ADVOCACY_LABELS),
        sorted(METHOD_LABELS),
        MAX_LABEL_WORDS,
        config.model_dump(mode="json"),
    ]


def kritikal_rules_digest(config: KritikalAffConfig | None) -> str:
    return hashlib.sha256(json.dumps(kritikal_rules(config), sort_keys=True).encode()).hexdigest()


def read_kritikal_markers(
    paragraphs: Sequence[ReadParagraph], config: KritikalAffConfig | None
) -> KritikalReading:
    """One file's K-aff markers, in file order, and the K families its headings name.

    A topic with no K-aff config reads none: its affirmatives are identified as `v1-e32-t09` left them.
    """
    if config is None:
        return KritikalReading()
    written = [one for one in paragraphs if one.text.strip() and one.unit not in _NOT_TEXT_UNITS]
    markers: list[KritikalMarker] = []
    named: set[str] = set()
    for position, one in enumerate(written):
        following = written[position + 1] if position + 1 < len(written) else None
        next_unit = following.unit if following is not None else None
        form = label_form(one.text)
        for kind, how in _markers_of(one, form, next_unit):
            markers.append(
                KritikalMarker(kind=kind, form=how, element_index=one.element_index, unit=one.unit)
            )
        if one.unit in _HEADING_UNITS:
            heading = normalize_source_heading(one.text, (), CaselistNames({})).text
            named.update(heading_families(heading, config.families))
    return KritikalReading(markers=tuple(markers), heading_families=tuple(sorted(named)))


def heading_families(form: str, families: Sequence[KritikalFamily]) -> tuple[str, ...]:
    """The families a normalized heading names, sorted: each phrase whole, a longer phrase first."""
    phrases = sorted(
        ((phrase, one.id) for one in families for phrase in one.phrases),
        key=lambda pair: (-len(pair[0].split()), pair[0]),
    )
    spaced = f" {form} "
    found: set[str] = set()
    for phrase, family in phrases:
        whole = f" {phrase} "
        if whole in spaced:
            found.add(family)
            spaced = spaced.replace(whole, " | ")
    return tuple(sorted(found))


def _markers_of(
    one: ReadParagraph, form: str | None, next_unit: StructuralUnit | None
) -> list[tuple[KritikalMarkerKind, TextForm]]:
    """The markers one paragraph holds, at most one of each kind."""
    found: list[tuple[KritikalMarkerKind, TextForm]] = []
    role = role_of_the_ballot_form(one.text, one.unit, form, next_unit)
    if role is not None:
        found.append((KritikalMarkerKind.ROLE_OF_THE_BALLOT, role))
    over_text = next_unit in TEXT_UNITS
    in_text = one.unit not in _HEADING_UNITS
    if form in ADVOCACY_LABELS:
        if over_text:
            found.append((KritikalMarkerKind.ADVOCACY, TextForm.LABEL))
    elif _ADVOCACY_INLINE.match(one.text) and in_text:
        found.append((KritikalMarkerKind.ADVOCACY, TextForm.INLINE))
    elif _ADVOCACY_SENTENCE.match(one.text):
        found.append((KritikalMarkerKind.ADVOCACY, TextForm.SENTENCE))
    if _THE_1AC_SENTENCE.match(one.text):
        found.append((KritikalMarkerKind.THE_1AC, TextForm.SENTENCE))
    if form in METHOD_LABELS:
        if over_text:
            found.append((KritikalMarkerKind.METHOD, TextForm.LABEL))
    elif _METHOD_INLINE.match(one.text) and in_text:
        found.append((KritikalMarkerKind.METHOD, TextForm.INLINE))
    elif _METHOD_SENTENCE.match(one.text):
        found.append((KritikalMarkerKind.METHOD, TextForm.SENTENCE))
    return found
