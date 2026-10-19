"""Assembling a whole evidence file behind the EvidenceFileWriter port (`v1-e33-t02`).

:class:`DocxEvidenceFileWriter` walks a resolved recipe (`v1-e33-t01`) and writes, in order:

1. **One header line**, an analytic naming the source caselists and saying the cards are disclosed
   (FILE_IMPORT) and not verified by the platform.
2. **The recipe's headings**: each pocket, hat and block in the profile's `Heading1` to `Heading3`.
3. **Each card**, copied by :mod:`.run_copier`: its tag (or the coach's override, in the profile's tag
   style), its cite, **the provenance line** below the cite in the Undertag style (data-use policy,
   Attribution rule 2; PM amendment 2026-10-19), then its body.
4. **Each analytic**, in the profile's Analytic style.

That is the only new text: headings, overrides and analytics are the coach's, the header is fixed,
and the provenance line is built from the occurrence and its disclosure record, never from card text.

## Before a card is copied, it is found and checked

The source's bytes come from the blob store by the occurrence's SHA-256 (which re-hashes what it
reads). The E31 parser reads them, and the card it finds at the occurrence's element indices must
have the occurrence's exact fingerprint; a source that has changed under a stored row, or a row
pointing at the wrong paragraphs, is refused as `OCCURRENCE_MISMATCH` rather than copied.

## After the file is written, it is read back

The writer parses what it wrote with the same parser and compares every card with its source card:
tag, cite, evidence text, and formatting (:func:`~debate_core.domain.file_provenance.formatting_sha256`).
A difference refuses the file as `READBACK_MISMATCH`. The CardMirror evaluation found the one way a
writer's success can be untrue, a file that does not read back (ADR-0014; cardmirror-evaluation.md),
and this is the check against it.

## Determinism

The `.docx` depends only on the recipe, the sources, the profile, the base template and the versions
of this writer and the parser: zip entries in a fixed order with fixed dates, a core part holding the
title and nothing else (no creator, no lastModifiedBy, no dates), hyperlink relationships numbered in
the order they are met. The request's `built_at` goes into the sidecar alone.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from lxml import etree

from debate_core.application.errors import BlobIntegrityError, NotFound
from debate_core.application.file_recipes import ResolvedCard, ResolvedRecipe
from debate_core.application.ports.evidence_file_writer import (
    BuiltEvidenceFile,
    CardRefusal,
    CardRefusalCode,
    FileBuildRefusal,
    FileBuildRequest,
)
from debate_core.application.ports.parsed_store import OPENEV_STORE, OccurrenceRecord
from debate_core.application.ports.persistence import SnapshotStore
from debate_core.domain.caselist import Disclosure, Side, SourceDocument, SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedCard, ParsedDocument, ParseFailure
from debate_core.domain.file_provenance import (
    FileProvenanceEntry,
    FileProvenanceManifest,
    formatting_sha256,
    text_sha256,
)
from debate_core.domain.file_recipe import Analytic, CardRef, FileRecipe, TagAuthor, render_location
from debate_core.domain.style_profile import StructuralUnit, StyleProfile
from debate_core.evidence.fingerprints import card_fingerprint
from debate_core.integrations.docx_file_writer.base_template import (
    CONTENT_TYPES,
    PACKAGE_RELATIONSHIPS,
    BaseTemplate,
    core_properties_xml,
    document_relationships_xml,
    load_base_template,
)
from debate_core.integrations.docx_file_writer.package_writer import write_package
from debate_core.integrations.docx_file_writer.run_copier import (
    R_NAMESPACE,
    W14_NAMESPACE,
    CopiedCard,
    HyperlinkTargets,
    OpenedSource,
    UnsupportedCard,
    copy_card,
    open_source,
)
from debate_core.integrations.docx_parser.package import (
    DEFAULT_PACKAGE_LIMITS,
    MC_NAMESPACE,
    W_NAMESPACE,
    DocxPackageError,
    PackageLimits,
    XmlElement,
    qualified_name,
)
from debate_core.integrations.docx_parser.parser import DebateDocxParser

__all__ = [
    "FILE_BUILDER_VERSION",
    "HIGHLIGHTED_CITE_CAUSE",
    "DocxEvidenceFileWriter",
    "header_line",
    "provenance_line",
]

#: The reason a card is refused when the provenance line stands between its highlighted cite and its
#: body (PM ruling, 2026-10-19; the parser moves with `v1-e31-t24`).
HIGHLIGHTED_CITE_CAUSE: Final = "the provenance line stands between a highlighted cite and its body"

#: Version recorded in every sidecar. Bumped whenever the bytes a recipe builds to change.
FILE_BUILDER_VERSION: Final = "2026.10.19-file-writer-1"

_W15_NAMESPACE: Final = "http://schemas.microsoft.com/office/word/2012/wordml"

#: The namespaces a built document declares at its root, as Word declares them, and the two Word
#: extensions a reader that does not know them may ignore.
_DOCUMENT_NAMESPACES: Final = {
    "w": W_NAMESPACE,
    "r": R_NAMESPACE,
    "mc": MC_NAMESPACE,
    "w14": W14_NAMESPACE,
    "w15": _W15_NAMESPACE,
}

_SIDE_LABELS: Final = {Side.AFF: "Aff", Side.NEG: "Neg", Side.PRO: "Pro", Side.CON: "Con"}

#: The path the parser is told a source sat at. It is recorded nowhere the writer keeps; a real
#: disclosure path names a school and a team, and the writer has no use for one.
_SOURCE_PATH_FOR_THE_PARSER: Final = "disclosed-source.docx"


# ------------------------------------------------------------------------------------------------
# The two lines the writer composes
# ------------------------------------------------------------------------------------------------


def provenance_line(occurrence: OccurrenceRecord, disclosure: Disclosure | None) -> str:
    """The line below a card's cite (data-use policy, Attribution rule 2), from the record alone.

    `[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Aff vs. Riverbend Invitational Round 4]`, the
    policy's own example: caselist, the first snapshot that listed the disclosure, then school and team
    code exactly as disclosed, side, tournament and round as far as the disclosure records them. With no
    disclosure on record (t01's ruling lets AUTO fall back to one), the line names no team.
    """
    head = f"Disclosed: {occurrence.caselist} {occurrence.snapshot}"
    if disclosure is None:
        return f"[{head}]"
    side = _SIDE_LABELS.get(disclosure.side)
    event = " ".join(
        part
        for part in (
            disclosure.tournament,
            disclosure.round_label.raw if disclosure.round_label is not None else None,
        )
        if part
    )
    if side and event:
        detail = f", {side} vs. {event}"
    elif side or event:
        detail = f", {side or event}"
    else:
        detail = ""
    return f"[{head} — {disclosure.school} {disclosure.team_code}{detail}]"


def header_line(recipe: ResolvedRecipe) -> str:
    """The file's one header analytic: where its cards came from, and that none of them is verified."""
    caselists = sorted({card.occurrence.caselist for card in recipe.cards} | {recipe.recipe.caselist})
    return (
        f"Disclosed cards (FILE_IMPORT) from {', '.join(caselists)}, each copied from the file that "
        "disclosed it and not verified by this platform. Who disclosed each card is below its cite."
    )


# ------------------------------------------------------------------------------------------------
# Sources
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Source:
    opened: OpenedSource
    parsed: ParsedDocument

    def unit(self, element_index: int) -> StructuralUnit:
        for section in self.parsed.sections:
            if section.element_index == element_index:
                return section.unit
        return StructuralUnit.OTHER


@dataclass(frozen=True, slots=True)
class _Located:
    """One card, found in its source and checked against its occurrence, ready to copy."""

    resolved: ResolvedCard
    source: _Source
    card: ParsedCard


def _source_document(occurrence: OccurrenceRecord, size: int) -> SourceDocument:
    return SourceDocument(
        sha256=occurrence.source_sha256,
        byte_size=size,
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE,
        caselist=occurrence.caselist,
        first_seen_snapshot=date.fromisoformat(occurrence.snapshot),
        last_seen_snapshot=date.fromisoformat(occurrence.last_snapshot),
    )


# ------------------------------------------------------------------------------------------------
# Paragraphs the writer writes
# ------------------------------------------------------------------------------------------------


def _paragraph(style_id: str, text: str) -> XmlElement:
    """A new paragraph in `style_id` holding `text` in one run: a heading, an override, an analytic."""
    paragraph = etree.Element(qualified_name("p"))
    properties = etree.SubElement(paragraph, qualified_name("pPr"))
    etree.SubElement(properties, qualified_name("pStyle")).set(qualified_name("val"), style_id)
    run = etree.SubElement(paragraph, qualified_name("r"))
    text_element = etree.SubElement(run, qualified_name("t"))
    text_element.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_element.text = text
    return paragraph


class _Body:
    """The built document's body, counting paragraphs as the parser numbers them."""

    def __init__(self, profile: StyleProfile) -> None:
        self.root = etree.Element(qualified_name("document"), nsmap=_DOCUMENT_NAMESPACES)
        self.root.set(f"{{{MC_NAMESPACE}}}Ignorable", "w14 w15")
        self.body = etree.SubElement(self.root, qualified_name("body"))
        self.count = 0
        self._styles = {rule.unit: rule.style_id for rule in reversed(profile.paragraph_styles)}

    def style(self, unit: StructuralUnit) -> str:
        return self._styles[unit]

    def append(self, paragraph: XmlElement) -> int:
        """Append a paragraph and return its element index."""
        self.body.append(paragraph)
        self.count += 1
        return self.count - 1

    def write(self, unit: StructuralUnit, text: str) -> int:
        return self.append(_paragraph(self.style(unit), text))

    def to_bytes(self) -> bytes:
        return etree.tostring(self.root, xml_declaration=True, encoding="UTF-8", standalone=True)


# ------------------------------------------------------------------------------------------------
# The writer
# ------------------------------------------------------------------------------------------------


class DocxEvidenceFileWriter:
    """The V1 :class:`~debate_core.application.ports.evidence_file_writer.EvidenceFileWriter`.

    Deterministic and offline: no clock, no model call, no network. Its only inputs beyond the request
    are the blob store it reads sources from, the parser (and through it the style profile) and the
    committed base template.
    """

    def __init__(
        self,
        *,
        snapshots: SnapshotStore,
        parser: DebateDocxParser | None = None,
        base: BaseTemplate | None = None,
        limits: PackageLimits = DEFAULT_PACKAGE_LIMITS,
    ) -> None:
        self._snapshots = snapshots
        self._parser = parser if parser is not None else DebateDocxParser(limits=limits)
        self._profile = self._parser.profile
        self._base = base if base is not None else load_base_template()
        self._base_style_ids = self._base.style_ids
        self._limits = limits

    @property
    def builder_version(self) -> str:
        return FILE_BUILDER_VERSION

    async def build(self, request: FileBuildRequest) -> BuiltEvidenceFile | FileBuildRefusal:
        """Build the file, or refuse it with every card that stopped it."""
        resolved = request.resolved
        by_path = {card.path: card for card in resolved.cards}
        missing = [
            render_location(location)
            for location, _ in resolved.recipe.card_refs()
            if render_location(location) not in by_path
        ]
        if missing:
            raise ValueError(f"the resolved recipe has no occurrence for {len(missing)} card(s)")

        located, refusals = await self._locate(resolved.cards)
        if refusals:
            return FileBuildRefusal(tuple(refusals))

        hyperlinks = HyperlinkTargets()
        copies: dict[str, CopiedCard] = {}
        for item in located:
            copied = copy_card(
                item.source.opened,
                first_element_index=item.card.provenance.first_element_index,
                last_element_index=item.card.provenance.last_element_index,
                units=item.source.unit,
                profile=self._profile,
                base_style_ids=self._base_style_ids,
                hyperlinks=hyperlinks,
            )
            if isinstance(copied, UnsupportedCard):
                refusals.append(
                    CardRefusal(
                        path=item.resolved.path,
                        fingerprint=item.resolved.fingerprint,
                        code=CardRefusalCode.UNSUPPORTED_CONTENT,
                        detail=(
                            "the card holds content that cannot be copied losslessly, in source "
                            f"paragraph(s) {', '.join(str(index) for index in copied.element_indices)}"
                        ),
                        content_kinds=copied.kinds,
                    )
                )
                continue
            copies[item.resolved.path] = copied
        if refusals:
            return FileBuildRefusal(tuple(refusals))

        by_path = {item.resolved.path: item for item in located}
        docx, placed = self._write(resolved, by_path, copies, hyperlinks)
        problems = self._read_back(docx, resolved.recipe, located, placed)
        if problems:
            return FileBuildRefusal(self._explain(resolved, by_path, copies, hyperlinks, problems))

        manifest = self._manifest(request, docx, located, placed, copies)
        return BuiltEvidenceFile(
            docx=docx,
            manifest=manifest,
            manifest_json=manifest.to_json_bytes(),
            warnings=manifest.warnings,
        )

    # -- finding each card --------------------------------------------------------------------

    async def _locate(self, cards: tuple[ResolvedCard, ...]) -> tuple[list[_Located], list[CardRefusal]]:
        sources: dict[str, _Source | tuple[CardRefusalCode, str]] = {}
        located: list[_Located] = []
        refusals: list[CardRefusal] = []
        for resolved in cards:
            occurrence = resolved.occurrence

            def refuse(code: CardRefusalCode, detail: str, resolved: ResolvedCard = resolved) -> None:
                refusals.append(CardRefusal(resolved.path, resolved.fingerprint, code, detail))

            if occurrence.caselist == OPENEV_STORE:
                refuse(
                    CardRefusalCode.SOURCE_UNREADABLE,
                    "a camp (OpenEv) card cannot be referenced by a schema version 1 recipe",
                )
                continue
            sha = occurrence.source_sha256
            if sha not in sources:
                sources[sha] = await self._open(occurrence)
            source = sources[sha]
            if not isinstance(source, _Source):
                refuse(*source)
                continue
            card = next(
                (
                    card
                    for card in source.parsed.cards
                    if card.provenance.first_element_index == occurrence.first_element_index
                    and card.provenance.last_element_index == occurrence.last_element_index
                ),
                None,
            )
            if card is None:
                refuse(
                    CardRefusalCode.OCCURRENCE_MISMATCH,
                    f"no card of parser {self._parser.parser_version} runs from paragraph "
                    f"{occurrence.first_element_index} to {occurrence.last_element_index} of the source",
                )
                continue
            if card_fingerprint(card).exact_fingerprint != resolved.fingerprint or (
                occurrence.exact_fingerprint != resolved.fingerprint
            ):
                refuse(
                    CardRefusalCode.OCCURRENCE_MISMATCH,
                    f"the card at paragraph {occurrence.first_element_index} of the source does not "
                    "have the fingerprint the recipe names",
                )
                continue
            located.append(_Located(resolved=resolved, source=source, card=card))
        return located, refusals

    async def _open(self, occurrence: OccurrenceRecord) -> _Source | tuple[CardRefusalCode, str]:
        try:
            content = await self._snapshots.get(occurrence.source_sha256)
        except NotFound:
            return CardRefusalCode.SOURCE_UNAVAILABLE, "the source's bytes are not in the blob store"
        except BlobIntegrityError:
            return (
                CardRefusalCode.SOURCE_UNAVAILABLE,
                "the stored bytes no longer hash to the source's SHA-256",
            )
        parsed = self._parser.parse(
            content,
            _source_document(occurrence, len(content)),
            source_path=_SOURCE_PATH_FOR_THE_PARSER,
        )
        if isinstance(parsed, ParseFailure):
            return CardRefusalCode.SOURCE_UNREADABLE, f"the parser refuses the source: {parsed.reason}"
        try:
            opened = open_source(content, limits=self._limits)
        except DocxPackageError as error:  # pragma: no cover - the parser above refused it first
            return CardRefusalCode.SOURCE_UNREADABLE, f"the source cannot be opened: {error.reason}"
        return _Source(opened=opened, parsed=parsed)

    # -- writing the body ---------------------------------------------------------------------

    def _write(
        self,
        resolved: ResolvedRecipe,
        located: Mapping[str, _Located],
        copies: Mapping[str, CopiedCard],
        hyperlinks: HyperlinkTargets,
        *,
        without_line: frozenset[str] = frozenset(),
    ) -> tuple[bytes, dict[str, int]]:
        """The built file's bytes, and each card's first element index in it.

        `without_line` names cards to write without their provenance line. Only :meth:`_explain`
        asks for that, to find out whether a card that failed the read-back fails because of it;
        such a file is never handed back.
        """
        body = _Body(self._profile)
        placed = self._assemble(resolved, body, located, copies, without_line)
        docx = write_package(
            (
                ("[Content_Types].xml", CONTENT_TYPES),
                ("_rels/.rels", PACKAGE_RELATIONSHIPS),
                ("word/document.xml", body.to_bytes()),
                ("word/_rels/document.xml.rels", document_relationships_xml(hyperlinks.relationships())),
                ("word/styles.xml", self._base.styles_xml),
                ("word/settings.xml", self._base.settings_xml),
                ("docProps/core.xml", core_properties_xml(resolved.recipe.title)),
            )
        )
        return docx, placed

    def _assemble(
        self,
        resolved: ResolvedRecipe,
        body: _Body,
        located: Mapping[str, _Located],
        copies: Mapping[str, CopiedCard],
        without_line: frozenset[str],
    ) -> dict[str, int]:
        """Write the whole body; return each card's first element index in the built file.

        Copied paragraphs are appended as copies of their own, so the same card can be written
        twice (:meth:`_explain`) without one body taking it from the other.
        """
        recipe = resolved.recipe
        placed: dict[str, int] = {}
        body.write(StructuralUnit.ANALYTIC, header_line(resolved))
        for location, item, headings in _walk(recipe):
            for unit, text in headings:
                body.write(unit, text)
            if isinstance(item, Analytic):
                body.write(StructuralUnit.ANALYTIC, item.analytic)
                continue
            path = render_location(location)
            card = located[path]
            copied = copies[path]
            first: int | None = None
            if card.resolved.tag_override is not None:
                first = body.write(StructuralUnit.TAG, card.resolved.tag_override.text)
            elif copied.tag is not None:
                first = body.append(copy.deepcopy(copied.tag))
            for paragraph in copied.through_cite:
                index = body.append(copy.deepcopy(paragraph))
                first = index if first is None else first
            if path not in without_line:
                line = body.write(
                    StructuralUnit.UNDERTAG,
                    provenance_line(card.resolved.occurrence, card.resolved.disclosure),
                )
                first = line if first is None else first
            for paragraph in copied.after_cite:
                index = body.append(copy.deepcopy(paragraph))
                first = index if first is None else first
            assert first is not None, "a card has a tag, a cite or a body"
            placed[path] = first
        return placed

    # -- reading it back ----------------------------------------------------------------------

    def _read_back(
        self,
        docx: bytes,
        recipe: FileRecipe,
        located: list[_Located],
        placed: Mapping[str, int],
        *,
        without_line: frozenset[str] = frozenset(),
    ) -> dict[str, str]:
        """Each card the built file does not read back as its source, with what differs."""
        built = SourceDocument(
            sha256=hashlib.sha256(docx).hexdigest(),
            byte_size=len(docx),
            source_format=SourceFormat.DOCX,
            origin=SourceOrigin.CASELIST_ARCHIVE,
            caselist=recipe.caselist,
            first_seen_snapshot=date(2000, 1, 1),
            last_seen_snapshot=date(2000, 1, 1),
        )
        parsed = self._parser.parse(docx, built, source_path="built-file.docx")
        if isinstance(parsed, ParseFailure):
            return {item.resolved.path: f"the built file does not parse: {parsed.reason}" for item in located}
        by_first = {card.provenance.first_element_index: card for card in parsed.cards}
        problems: dict[str, str] = {}
        for item in located:
            path = item.resolved.path
            problem = _difference(item, by_first.get(placed[path]), with_line=path not in without_line)
            if problem is None and len(parsed.cards) != len(located):
                problem = f"the built file reads as {len(parsed.cards)} cards, not {len(located)}"
            if problem is not None:
                problems[path] = problem
        return problems

    def _explain(
        self,
        resolved: ResolvedRecipe,
        located: Mapping[str, _Located],
        copies: Mapping[str, CopiedCard],
        hyperlinks: HyperlinkTargets,
        problems: Mapping[str, str],
    ) -> tuple[CardRefusal, ...]:
        """The read-back refusals, each saying whether the provenance line is what changed the card.

        The writer knows none of the parser's rules. It asks the parser instead: the same file with
        the failing cards' lines left out is read back, and a card that then reads as its source was
        changed by its line. Where the cite above that line is highlighted, the reason says so: the
        parser reads a highlighted cite as a cite only with its body directly below it, and the line
        stands between them until `v1-e31-t24` lets the parser step over it (PM ruling, 2026-10-19).
        """
        without = frozenset(problems)
        variant, placed = self._write(resolved, located, copies, hyperlinks, without_line=without)
        still = self._read_back(
            variant, resolved.recipe, list(located.values()), placed, without_line=without
        )
        refusals: list[CardRefusal] = []
        for item in located.values():
            path = item.resolved.path
            if path not in problems:
                continue
            problem = problems[path]
            if path not in still:
                cause = (
                    HIGHLIGHTED_CITE_CAUSE
                    if _is_highlighted(copies[path].through_cite)
                    else "the provenance line below the cite changes how the card reads"
                )
                problem = f"{cause}: {problem}; without the line the card reads as its source"
            refusals.append(
                CardRefusal(path, item.resolved.fingerprint, CardRefusalCode.READBACK_MISMATCH, problem)
            )
        return tuple(refusals)

    # -- the sidecar --------------------------------------------------------------------------

    def _manifest(
        self,
        request: FileBuildRequest,
        docx: bytes,
        located: list[_Located],
        placed: Mapping[str, int],
        copies: Mapping[str, CopiedCard],
    ) -> FileProvenanceManifest:
        resolved = request.resolved
        recipe = resolved.recipe
        entries: list[FileProvenanceEntry] = []
        warnings: list[str] = []
        sections = dict(_section_paths(recipe))
        for position, item in enumerate(
            sorted(located, key=lambda item: placed[item.resolved.path]), start=1
        ):
            card, occurrence, disclosure = item.card, item.resolved.occurrence, item.resolved.disclosure
            override = item.resolved.tag_override
            copied = copies[item.resolved.path]
            warnings.extend(f"{item.resolved.path}: {warning}" for warning in copied.warnings)
            entries.append(
                FileProvenanceEntry(
                    position=position,
                    recipe_path=item.resolved.path,
                    section_path=sections[item.resolved.path],
                    fingerprint=item.resolved.fingerprint,
                    fingerprint_version=occurrence.fingerprint_version,
                    resolution=item.resolved.resolution.value,
                    caselist=occurrence.caselist,
                    camp=occurrence.camp,
                    snapshot=occurrence.snapshot,
                    last_snapshot=occurrence.last_snapshot,
                    disclosure_digest=occurrence.disclosure,
                    school=disclosure.school if disclosure is not None else None,
                    team_code=disclosure.team_code if disclosure is not None else None,
                    side=str(disclosure.side) if disclosure is not None else None,
                    tournament=disclosure.tournament if disclosure is not None else None,
                    round=(
                        disclosure.round_label.raw
                        if disclosure is not None and disclosure.round_label is not None
                        else None
                    ),
                    source_sha256=occurrence.source_sha256,
                    first_element_index=occurrence.first_element_index,
                    last_element_index=occurrence.last_element_index,
                    completeness=card.completeness,
                    evidence_sha256=text_sha256(card.evidence_text),
                    cite_sha256=text_sha256(card.full_cite),
                    formatting_sha256=formatting_sha256(card.formatting_spans, card.font_size_spans),
                    tag_overridden=override is not None,
                    tag_authored_by=TagAuthor.COACH if override is not None else None,
                    original_tag_sha256=(
                        text_sha256(card.tag) if override is not None and card.has_tag else None
                    ),
                    provenance_line=provenance_line(occurrence, disclosure),
                    forbidden_characters_replaced=copied.forbidden_characters_replaced,
                    warnings=copied.warnings,
                )
            )
        return FileProvenanceManifest(
            title=recipe.title,
            topic=recipe.topic,
            format=str(recipe.format),
            caselist=recipe.caselist,
            position=recipe.position,
            side=str(recipe.side),
            recipe_hash=resolved.recipe_hash,
            builder_version=FILE_BUILDER_VERSION,
            parser_version=self._parser.parser_version,
            style_profile_version=self._parser.profile_version,
            fingerprint_version=recipe.fingerprint_version,
            built_at=request.built_at,
            docx_sha256=hashlib.sha256(docx).hexdigest(),
            cards=tuple(entries),
            warnings=tuple(warnings),
        )


def _is_highlighted(through_cite: tuple[XmlElement, ...]) -> bool:
    """Whether the paragraph directly above the provenance line carries a highlight colour."""
    if not through_cite:
        return False
    return any(
        (highlight.get(qualified_name("val")) or "none") != "none"
        for highlight in through_cite[-1].iter(qualified_name("highlight"))
    )


def _difference(item: _Located, built: ParsedCard | None, *, with_line: bool = True) -> str | None:
    """What a re-parsed card says differently from its source card, or None. Names fields, never text."""
    if built is None:
        return "no card starts where the card was written in the built file"
    source = item.card
    expected_tag = item.resolved.tag_override.text if item.resolved.tag_override is not None else source.tag
    line = provenance_line(item.resolved.occurrence, item.resolved.disclosure)
    checks = (
        ("cite", built.full_cite == source.full_cite),
        ("evidence text", built.evidence_text == source.evidence_text),
        (
            "formatting",
            formatting_sha256(built.formatting_spans, built.font_size_spans)
            == formatting_sha256(source.formatting_spans, source.font_size_spans),
        ),
        ("tag", built.tag == expected_tag),
        ("provenance line", not with_line or line in built.undertag.split("\n")),
    )
    differing = [name for name, same in checks if not same]
    if not differing:
        return None
    return f"re-parsing the built file gives a different {', '.join(differing)} from the source card"


def _walk(
    recipe: FileRecipe,
) -> Iterator[tuple[tuple[str | int, ...], CardRef | Analytic, list[tuple[StructuralUnit, str]]]]:
    """Every item with its location, and the headings to write before it (only where one opens)."""
    for p, pocket in enumerate(recipe.structure):
        opening: list[tuple[StructuralUnit, str]] = [(StructuralUnit.POCKET, pocket.pocket)]
        for h, hat in enumerate(pocket.hats or ()):
            opening.append((StructuralUnit.HAT, hat.hat))
            for b, block in enumerate(hat.blocks):
                opening.append((StructuralUnit.BLOCK, block.block))
                for i, item in enumerate(block.items):
                    yield ("structure", p, "hats", h, "blocks", b, "items", i), item, opening
                    opening = []
        for b, block in enumerate(pocket.blocks or ()):
            opening.append((StructuralUnit.BLOCK, block.block))
            for i, item in enumerate(block.items):
                yield ("structure", p, "blocks", b, "items", i), item, opening
                opening = []


def _section_paths(recipe: FileRecipe) -> Iterator[tuple[str, tuple[str, ...]]]:
    """Each card's path in the recipe, and the pocket, hat and block headings above it."""
    for p, pocket in enumerate(recipe.structure):
        for h, hat in enumerate(pocket.hats or ()):
            for b, block in enumerate(hat.blocks):
                for i, _ in enumerate(block.items):
                    path = render_location(("structure", p, "hats", h, "blocks", b, "items", i))
                    yield path, (pocket.pocket, hat.hat, block.block)
        for b, block in enumerate(pocket.blocks or ()):
            for i, _ in enumerate(block.items):
                yield render_location(("structure", p, "blocks", b, "items", i)), (pocket.pocket, block.block)
