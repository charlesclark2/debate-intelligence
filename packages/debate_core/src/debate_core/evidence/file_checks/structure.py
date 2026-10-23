"""The checks on a built file's shape: sidecar, cites, duplicates, headings, alignment, provenance, removals.

Each is a function of the built file re-parsed by the E31 parser, the provenance sidecar, and for the
last one the suppressions in force. None of them reads a byte, calls a model or changes anything: a
check reports, and fixing a file is rebuilding it (the task's forbidden list).

## Which findings warn and which fail (PM ruling, 2026-10-19)

The writer copies a card as it was disclosed. A card the store holds with no cite or no short cite
(19,547 and about 84,000 of them, `v1-e31-t19`'s counts) is built that way, so a missing cite or short
cite is a WARN naming the card. So is a near duplicate, and a disclosure on record that names no
tournament or round. Everything else here is a FAIL: a fingerprint twice, a heading out of place or
out of the profile's styles, the sidecar and the document disagreeing, provenance missing what the
policy needs, and a card under a suppression.

## Provenance is in the sidecar, never in the file's text (`v1-e33-t08`)

Data-use policy version 1.11 (Attribution rules 2, 3 and 5): a built file carries no provenance line,
and a card's provenance is its sidecar entry. So the provenance check fails a document card with no
sidecar entry at its position (whether the entry is that card is the alignment check's question), and
a file whose text holds a provenance line: a paragraph opening in the policy's form (`[Disclosed: `,
`[OpenEv: `) or holding a sidecar entry's line anywhere in it. A line inside a
card is reported on that card; one outside every card by its paragraph index. The report names the
paragraph, never the line, which names a school and a team code.

## Headings

Verbatim's levels are pocket > hat > block > tag (`Heading1` to `Heading4`), and `v1-e33-t01` lets a
file leave hats out altogether: its blocks then sit straight in a pocket. So a heading is out of place
when the nearest level above it *that the file uses* is not open: a tag outside any block in a file
that has blocks, a block straight under a pocket in a file that has hats. Only that nearest level is
asked, so one misplaced block is reported once and not again for each tag under it. A heading must
also be in its unit's profile style, matched by its exact id: an alias or a heuristic match is a
heading the profile does not name.

A violation is reported with its paragraph index and the headings above it. A heading the sidecar
names (the coach's, from the recipe) is given by its text; any other by its level and paragraph, so
a report never carries text the coach did not write.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from debate_core.domain.debate_files import FileSection, ParsedCard, ParsedDocument
from debate_core.domain.file_provenance import FileProvenanceEntry
from debate_core.domain.file_recipe import CAMP_STORE
from debate_core.domain.style_profile import StructuralUnit, StyleProfile
from debate_core.evidence.file_checks.report import CheckResult, CheckStatus, QualityCheck
from debate_core.evidence.fingerprints import card_fingerprint
from debate_core.evidence.near_duplicates import cluster_near_duplicates

__all__ = [
    "SuppressionsInForce",
    "card_fingerprints",
    "check_alignment",
    "check_cites",
    "check_duplicates",
    "check_headings",
    "check_provenance",
    "check_sidecar",
    "check_suppression",
]

_LEVELS: Final = (StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK)
_HEADINGS: Final = (*_LEVELS, StructuralUnit.TAG)


def card_fingerprints(cards: Sequence[ParsedCard]) -> list[str]:
    """Each card's exact fingerprint, recomputed from the card as parsed."""
    return [card_fingerprint(card).exact_fingerprint for card in cards]


def _result(
    check: QualityCheck,
    status: CheckStatus,
    message: str,
    position: int | None = None,
    fingerprint: str | None = None,
    *,
    section_path: tuple[str, ...] | None = None,
    paragraph_index: int | None = None,
) -> CheckResult:
    return CheckResult(
        check=check,
        status=status,
        card_position=position,
        fingerprint=fingerprint,
        section_path=section_path,
        paragraph_index=paragraph_index,
        message=message,
    )


def _positions(positions: Sequence[int]) -> str:
    return ", ".join(str(position) for position in positions)


# ------------------------------------------------------------------------------------------------
# The sidecar
# ------------------------------------------------------------------------------------------------


def check_sidecar(
    *,
    problems: Sequence[str],
    recorded_docx_sha256: str | None,
    docx_sha256: str,
    sidecar_parser_version: str | None,
    parser_version: str,
) -> list[CheckResult]:
    """The sidecar is readable and valid (`problems` says how it is not), and describes these bytes.

    A sidecar written under another parser version is a WARN: the checks re-read both files with the
    running parser, and a card that reads differently under it fails the identity check by itself.
    """
    check = QualityCheck.SIDECAR
    results = [
        _result(check, CheckStatus.FAIL, f"the sidecar is not valid: {problem}") for problem in problems
    ]
    if recorded_docx_sha256 is not None and recorded_docx_sha256 != docx_sha256:
        results.append(
            _result(
                check,
                CheckStatus.FAIL,
                f"the sidecar describes a file with SHA-256 {recorded_docx_sha256[:12]}…, "
                f"and this file is {docx_sha256[:12]}…",
            )
        )
    if sidecar_parser_version is not None and sidecar_parser_version != parser_version:
        results.append(
            _result(
                check,
                CheckStatus.WARN,
                f"the sidecar was written under parser {sidecar_parser_version}; the files were re-read "
                f"with {parser_version}",
            )
        )
    return results or [_result(check, CheckStatus.PASS, "the sidecar is valid and describes this file")]


# ------------------------------------------------------------------------------------------------
# Cites and duplicates
# ------------------------------------------------------------------------------------------------


def check_cites(cards: Sequence[ParsedCard]) -> list[CheckResult]:
    """Each card has a cite with a short cite. A missing one is a WARN, never a FAIL (PM, 2026-10-19)."""
    results: list[CheckResult] = []
    for position, (card, fingerprint) in enumerate(
        zip(cards, card_fingerprints(cards), strict=True), start=1
    ):
        if not card.full_cite.strip():
            results.append(
                _result(
                    QualityCheck.CITE_PRESENT, CheckStatus.WARN, "the card has no cite", position, fingerprint
                )
            )
        elif card.short_cite is None:
            results.append(
                _result(
                    QualityCheck.CITE_PRESENT,
                    CheckStatus.WARN,
                    "the card has no short cite",
                    position,
                    fingerprint,
                )
            )
        else:
            results.append(
                _result(
                    QualityCheck.CITE_PRESENT,
                    CheckStatus.PASS,
                    "the card has a cite with a short cite",
                    position,
                    fingerprint,
                )
            )
    return results


def check_duplicates(cards: Sequence[ParsedCard]) -> list[CheckResult]:
    """No fingerprint twice (FAIL); cards in one near-duplicate cluster (E31's clustering) are WARNs."""
    check = QualityCheck.DUPLICATE_CARDS
    fingerprints = card_fingerprints(cards)
    places: dict[str, list[int]] = {}
    for position, fingerprint in enumerate(fingerprints, start=1):
        places.setdefault(fingerprint, []).append(position)
    bodies = {
        fingerprint: card.evidence_text
        for fingerprint, card in zip(fingerprints, cards, strict=True)
        if card.evidence_text.strip()
    }
    clusters = cluster_near_duplicates(bodies) if len(bodies) > 1 else {}
    results: list[CheckResult] = []
    for position, fingerprint in enumerate(fingerprints, start=1):
        same = places[fingerprint]
        if len(same) > 1:
            results.append(
                _result(
                    check,
                    CheckStatus.FAIL,
                    f"the card's fingerprint appears {len(same)} times, at cards {_positions(same)}",
                    position,
                    fingerprint,
                )
            )
            continue
        cluster = clusters.get(fingerprint)
        near = [
            other
            for other, other_fingerprint in enumerate(fingerprints, start=1)
            if other_fingerprint != fingerprint
            and cluster is not None
            and clusters.get(other_fingerprint) == cluster
        ]
        if near:
            noun = "card" if len(near) == 1 else "cards"
            message = f"the card is a near duplicate of {noun} {_positions(near)}"
            results.append(_result(check, CheckStatus.WARN, message, position, fingerprint))
        else:
            results.append(
                _result(check, CheckStatus.PASS, "no other card is this card", position, fingerprint)
            )
    return results


# ------------------------------------------------------------------------------------------------
# Headings
# ------------------------------------------------------------------------------------------------


def _nearest_level_above(unit: StructuralUnit, used: set[StructuralUnit]) -> StructuralUnit | None:
    above = _LEVELS[: _LEVELS.index(unit)] if unit in _LEVELS else _LEVELS
    return next((level for level in reversed(above) if level in used), None)


def check_headings(
    document: ParsedDocument, profile: StyleProfile, known_headings: frozenset[str]
) -> list[CheckResult]:
    """Headings nest pocket > hat > block > tag with no level skipped, each in its profile style.

    `known_headings` are the coach's headings the sidecar records; a heading above a violation is
    named by its text only if it is one of them, and otherwise by its unit and paragraph.
    """
    check = QualityCheck.HEADING_STRUCTURE
    style_ids: dict[StructuralUnit, str] = {}
    for rule in profile.paragraph_styles:
        style_ids.setdefault(rule.unit, rule.style_id)
    used = {section.unit for section in document.sections if section.unit in _LEVELS}
    card_starts = {card.provenance.first_element_index for card in document.cards}
    opened: dict[StructuralUnit, FileSection] = {}

    def path(unit: StructuralUnit) -> tuple[str, ...]:
        """The open headings above a paragraph of `unit`: for a heading, only the levels above its own."""
        above = _LEVELS[: _LEVELS.index(unit)] if unit in _LEVELS else _LEVELS
        return tuple(
            opened[level].text
            if opened[level].text in known_headings
            else f"{opened[level].unit.lower()} at paragraph {opened[level].element_index}"
            for level in above
            if level in opened
        )

    results: list[CheckResult] = []

    def violation(section: FileSection, message: str) -> None:
        results.append(
            _result(
                check,
                CheckStatus.FAIL,
                message,
                section_path=path(section.unit),
                paragraph_index=section.element_index,
            )
        )

    for section in document.sections:
        unit = section.unit
        if unit in _HEADINGS:
            expected = style_ids[unit]
            match = section.match
            # The exact style id's rule, and only it, is a VERBATIM match: an alias, a display name,
            # a `basedOn` ancestor or a heuristic each has a rule id of its own.
            if match.rule_id != f"verbatim-style-id:{expected}":
                violation(
                    section,
                    f"a {unit.lower()} heading not in the profile's {expected} style ({match.rule_id})",
                )
            parent = _nearest_level_above(unit, used)
            if parent is not None and parent not in opened:
                violation(
                    section,
                    f"a {unit.lower()} with no {parent.lower()} above it, "
                    f"in a file that has {parent.lower()}s",
                )
            if unit in _LEVELS:
                for level in _LEVELS[_LEVELS.index(unit) :]:
                    opened.pop(level, None)
                opened[unit] = section
        elif section.element_index in card_starts:
            parent = _nearest_level_above(StructuralUnit.TAG, used)
            if parent is not None and parent not in opened:
                violation(
                    section, f"a card with no {parent.lower()} above it, in a file that has {parent.lower()}s"
                )
    return results or [_result(check, CheckStatus.PASS, "every heading is in place and in its profile style")]


# ------------------------------------------------------------------------------------------------
# The sidecar against the document
# ------------------------------------------------------------------------------------------------


def check_alignment(entries: Sequence[FileProvenanceEntry], cards: Sequence[ParsedCard]) -> list[CheckResult]:
    """The sidecar and the document hold the same cards, in the same order, under the same headings.

    A card the sidecar lists more often than the document holds it is missing from the document at
    its extra places, and the other way round; a card in both but at another place is out of order.
    """
    check = QualityCheck.MANIFEST_ALIGNMENT
    in_document = card_fingerprints(cards)
    in_sidecar = [entry.fingerprint for entry in entries]
    document_count, sidecar_count = Counter(in_document), Counter(in_sidecar)
    results: list[CheckResult] = []
    if len(in_document) != len(in_sidecar):
        results.append(
            _result(
                check,
                CheckStatus.FAIL,
                f"the sidecar lists {len(in_sidecar)} cards and the document reads as {len(in_document)}",
            )
        )
    seen: Counter[str] = Counter()
    for entry in entries:
        fingerprint = entry.fingerprint
        seen[fingerprint] += 1
        problems: list[str] = []
        here = in_document[entry.position - 1] if entry.position <= len(in_document) else None
        if seen[fingerprint] > document_count[fingerprint]:
            problems.append("the sidecar's card is not in the document")
        elif here != fingerprint:
            problems.append("the document holds another card of the sidecar here: the cards are out of order")
        elif cards[entry.position - 1].section_path != entry.section_path:
            problems.append("the card is under other headings in the document than the sidecar says")
        if problems:
            results.extend(
                _result(check, CheckStatus.FAIL, problem, entry.position, fingerprint) for problem in problems
            )
        else:
            results.append(
                _result(
                    check,
                    CheckStatus.PASS,
                    "the document holds this card here, under the same headings",
                    entry.position,
                    fingerprint,
                )
            )
    seen = Counter()
    for position, fingerprint in enumerate(in_document, start=1):
        seen[fingerprint] += 1
        if fingerprint not in sidecar_count:
            results.append(
                _result(
                    check,
                    CheckStatus.FAIL,
                    "the document's card is not in the sidecar",
                    position,
                    fingerprint,
                )
            )
        elif seen[fingerprint] > sidecar_count[fingerprint]:
            results.append(
                _result(
                    check,
                    CheckStatus.FAIL,
                    "the document holds this card more times than the sidecar lists it",
                    position,
                    fingerprint,
                )
            )
    return results


# ------------------------------------------------------------------------------------------------
# Provenance
# ------------------------------------------------------------------------------------------------


#: How a provenance line opens, in either of the policy's forms (Attribution rule 2).
_LINE_OPENINGS: Final = ("[Disclosed: ", "[OpenEv: ")


def _holds_a_provenance_line(text: str, lines: frozenset[str]) -> bool:
    """Whether a paragraph opens in the policy's form of a provenance line, or holds a sidecar line."""
    return text.lstrip().startswith(_LINE_OPENINGS) or any(line in text for line in lines)


def _camp_provenance(entry: FileProvenanceEntry) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    for value, name in (
        (entry.camp_year, "camp year"),
        (entry.camp_event, "camp event"),
        (entry.camp_file_title, "camp file title"),
    ):
        if value is None:
            problems.append(f"a camp card names no {name}")
    if entry.camp is None:
        warnings.append("a camp card names no camp")
    line = entry.provenance_line
    named = [str(part) for part in (entry.camp, entry.camp_year, entry.camp_file_title) if part is not None]
    if not (line.startswith("[OpenEv: ") and line.endswith("]") and all(part in line for part in named)):
        problems.append("the provenance line does not name the card's camp release")
    return problems, warnings


def _caselist_provenance(entry: FileProvenanceEntry) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    if entry.disclosure_digest is None:
        problems.append("a caselist card names no disclosure digest")
    disclosed = (entry.school, entry.team_code, entry.side, entry.tournament, entry.round)
    if any(value is not None for value in disclosed):
        if entry.school is None:
            problems.append("the disclosure on record names no school")
        elif entry.team_code is None:
            problems.append("the disclosure on record names a school and no team code")
        if entry.side is None:
            problems.append("the disclosure on record names no side")
        if entry.tournament is None:
            warnings.append("the disclosure on record names no tournament")
        if entry.round is None:
            warnings.append("the disclosure on record names no round")
    line = entry.provenance_line
    if not (line.startswith(f"[Disclosed: {entry.caselist} {entry.snapshot}") and line.endswith("]")):
        problems.append("the provenance line does not name the card's caselist and first snapshot")
    if (
        entry.school is not None
        and entry.team_code is not None
        and f"{entry.school} {entry.team_code}" not in line
    ):
        problems.append("the provenance line does not name the school and team code on record")
    return problems, warnings


def check_provenance(entries: Sequence[FileProvenanceEntry], document: ParsedDocument) -> list[CheckResult]:
    """Each card's provenance is its complete sidecar entry, and the file's text holds no provenance line.

    Complete (PM ruling, 2026-10-19): a camp card names its camp year, event and file title; a caselist
    card names its disclosure, which is either on record (school, team code and side, and a tournament
    and round where the disclosure records them, warned where it does not) or not on record at all.
    The source SHA-256, the snapshot and `provenance_mode` FILE_IMPORT the sidecar's own schema
    requires, so a sidecar without them fails the sidecar check. A document card with no sidecar entry
    has no provenance on record and fails (Attribution rule 5); so does a provenance line in the file's
    text (rule 2, since policy version 1.11).
    """
    check = QualityCheck.PROVENANCE_COMPLETE
    results: list[CheckResult] = []
    lines = frozenset(entry.provenance_line for entry in entries)
    held = [section for section in document.sections if _holds_a_provenance_line(section.text, lines)]
    reported: set[int] = set()
    for entry in entries:
        if entry.caselist == CAMP_STORE:
            problems, warnings = _camp_provenance(entry)
        else:
            problems, warnings = _caselist_provenance(entry)
        card = document.cards[entry.position - 1] if entry.position <= len(document.cards) else None
        if card is not None:
            first, last = card.provenance.first_element_index, card.provenance.last_element_index
            inside = {section.element_index for section in held if first <= section.element_index <= last}
            if inside:
                problems.append("the card's text holds a provenance line, which a built file never carries")
                reported |= inside
        found = [(CheckStatus.FAIL, problem) for problem in problems] + [
            (CheckStatus.WARN, warning) for warning in warnings
        ]
        if not found:
            found = [
                (CheckStatus.PASS, "the card's provenance is complete and the file's text holds no line")
            ]
        results.extend(
            _result(check, status, message, entry.position, entry.fingerprint) for status, message in found
        )
    covered = {entry.position for entry in entries}
    for position, card in enumerate(document.cards, start=1):
        if position not in covered:
            results.append(
                _result(
                    check,
                    CheckStatus.FAIL,
                    "the document's card has no sidecar entry, so no provenance on record",
                    position,
                    card_fingerprint(card).exact_fingerprint,
                )
            )
    results.extend(
        _result(
            check,
            CheckStatus.FAIL,
            "the file's text holds a provenance line, which a built file never carries",
            paragraph_index=section.element_index,
        )
        for section in held
        if section.element_index not in reported
    )
    return results


# ------------------------------------------------------------------------------------------------
# The suppression list (ac6)
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SuppressionsInForce:
    """The suppressions in force, each with the request id it honours.

    `sources` maps a suppressed source's SHA-256 to its request id; `disclosures` maps a
    `(sha256, disclosure digest)` pair to the request id of that one disclosure's suppression.
    """

    sources: Mapping[str, str] = field(default_factory=lambda: {})
    disclosures: Mapping[tuple[str, str], str] = field(default_factory=lambda: {})


def check_suppression(
    entries: Sequence[FileProvenanceEntry], suppressions: SuppressionsInForce
) -> list[CheckResult]:
    """No card from a suppressed source or disclosure (ac6). Names the card and the request, nothing else.

    A caselist card is flagged by a suppression of its whole source or of its own disclosure. A camp
    card records no disclosure, and its sidecar entry no camp path, so a suppression of one camp path
    (`v1-e30-t14`) cannot be told apart from another path of the same bytes: any suppression of one
    path of its source flags it, for a person to look at, rather than letting a removed card through.
    """
    check = QualityCheck.SUPPRESSION
    results: list[CheckResult] = []
    for entry in entries:
        sha = entry.source_sha256
        message: str | None = None
        if sha in suppressions.sources:
            request = suppressions.sources[sha]
            message = f"the card's source is on the suppression list (request {request}, the whole source)"
        elif entry.caselist != CAMP_STORE:
            digest = entry.disclosure_digest
            if digest is not None and (sha, digest) in suppressions.disclosures:
                request = suppressions.disclosures[sha, digest]
                message = f"the card's disclosure is on the suppression list (request {request})"
        else:
            requests = sorted(
                request for (source, _), request in suppressions.disclosures.items() if source == sha
            )
            if requests:
                message = (
                    f"a suppression of one path of the card's source is in force (request {requests[0]}); "
                    "the sidecar records no camp path to say whether it is this card's"
                )
        if message is None:
            results.append(
                _result(
                    check,
                    CheckStatus.PASS,
                    "no suppression in force covers the card",
                    entry.position,
                    entry.fingerprint,
                )
            )
        else:
            results.append(_result(check, CheckStatus.FAIL, message, entry.position, entry.fingerprint))
    return results
