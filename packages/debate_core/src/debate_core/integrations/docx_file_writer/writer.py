"""Assembling a whole evidence file behind the EvidenceFileWriter port (`v1-e33-t02`).

:class:`DocxEvidenceFileWriter` walks a resolved recipe (`v1-e33-t01`) and writes, in order:

1. **One header line**, an analytic naming the source caselists (and OpenEv, for camp cards) and
   saying the cards are disclosed or camp cards (FILE_IMPORT) and not verified by the platform. A
   file built from a draft recipe starts it with `DRAFT` (`v1-e33-t03`). A request with
   `header_line=False`, which only the pilot's download sends, leaves it out (`v1-e39-t24`).
2. **The recipe's headings**: each pocket, hat and block in the profile's `Heading1` to `Heading3`.
3. **Each card**, copied by :mod:`.run_copier`: its tag (or the coach's override, in the profile's tag
   style), its cite, then its body.
4. **Each analytic**, in the profile's Analytic style.

That is the only new text: headings, overrides and analytics are the coach's, and the header is fixed.

## No provenance line in the file; the provenance in the sidecar (`v1-e33-t08`)

A built file carries no provenance line, for disclosed and camp cards alike (data-use policy version
1.11, Attribution rule 2: the team's own files are disclosed on the caselist, and other schools' names
and team codes in them are clutter). Each card's provenance is in the sidecar (rule 3), which is what a
removal request is matched against, and its `provenance_line` is the line the pilot's card page shows:
:func:`~debate_core.domain.evidence_search.occurrence_provenance_line` composes it, from the
occurrence, its disclosure record and, for a camp card, its release, converted at this boundary. It is
built from those records, never from card text.

## Camp (OpenEv) cards (`v1-e33-t06`)

A camp card's sidecar line is the policy's other form, `[OpenEv: <camp> <year> — <event>, <file
title>]`: the camp from its occurrence row, the year, event and file title from its release record
(:attr:`~debate_core.application.file_recipes.ResolvedCard.camp_file`). With no release record, the
year and event are read from the row's release (`2031-policy`) and the title is left out. Its source is
read by its SHA-256 like any other. A writer given `source_stores` reads each source from the store of
its prefix in the evidence layout (:func:`~debate_core.application.caselist.publish_plan.source_prefix`),
`raw/caselist/<slug>` or a camp file's `raw/openev/<year>`, as a bucket keeps them; without it the one
`snapshots` store holds every source, as the local blob store does.

Each camp card's entry carries its row's camp path digests (`v1-e33-t07`), and the built file comes
with :attr:`~debate_core.application.ports.evidence_file_writer.BuiltEvidenceFile.camp_paths_json`
beside its sidecar, so `files check` can tell which release's withdrawal names the card.

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
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from lxml import etree

from debate_core.application.caselist.publish_plan import source_prefix
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
from debate_core.domain.caselist import (
    CampFile,
    Disclosure,
    Event,
    SourceDocument,
    SourceFormat,
    SourceOrigin,
)
from debate_core.domain.debate_files import ParsedCard, ParsedDocument, ParseFailure
from debate_core.domain.evidence_search import occurrence_provenance_line
from debate_core.domain.file_provenance import (
    FileProvenanceEntry,
    FileProvenanceManifest,
    formatting_sha256,
    text_sha256,
)
from debate_core.domain.file_recipe import (
    Analytic,
    CardRef,
    FileRecipe,
    RecipeStatus,
    TagAuthor,
    render_location,
)
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
    "DRAFT_HEADER",
    "FILE_BUILDER_VERSION",
    "DocxEvidenceFileWriter",
    "header_line",
]

#: Version recorded in every sidecar. Bumped whenever the bytes a recipe builds to change: `-2` adds
#: camp cards and the sidecar's camp keys (`v1-e33-t06`); `-3` writes no provenance line and drops the
#: header's last sentence, which pointed to it (`v1-e33-t08`); `-4` starts a draft recipe's header with
#: :data:`DRAFT_HEADER`, and builds a ready recipe to the same bytes as `-3` (`v1-e33-t03`).
FILE_BUILDER_VERSION: Final = "2026.10.24-file-writer-4"

DRAFT_HEADER: Final = "DRAFT: built from a recipe the coach has not marked ready. "
"""What the header analytic of a file built from a `status: draft` recipe starts with (`v1-e33-t03`)."""

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

#: The path the parser is told a source sat at. It is recorded nowhere the writer keeps; a real
#: disclosure path names a school and a team, and the writer has no use for one.
_SOURCE_PATH_FOR_THE_PARSER: Final = "disclosed-source.docx"

#: The day the parser is told a camp file was seen. A release has a year and no day, and nothing the
#: writer keeps reads it; the built file's read-back is told the same.
_UNDATED: Final = date(2000, 1, 1)


# ------------------------------------------------------------------------------------------------
# The header line, and the sidecar's provenance line
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _CampRelease:
    """What a camp card's sidecar entry, and the provenance line in it, say about where it came from."""

    camp: str | None
    year: int
    event: Event | None
    file_title: str | None


def _camp_release(occurrence: OccurrenceRecord, camp_file: CampFile | None) -> _CampRelease:
    """The camp from the occurrence; the year, event and title from the release record, if any.

    Without a record, the year and event are read from the occurrence's release, `2031-policy`, which
    is the importer's own name for it (`openev_release_name`), and there is no title to give.
    """
    event: Event | None
    if camp_file is not None:
        year, event = camp_file.year, camp_file.event
    else:
        year, named = int(occurrence.snapshot[:4]), occurrence.snapshot[5:]
        event = next((one for one in Event if one.value.lower() == named), None)
    return _CampRelease(
        camp=occurrence.camp or (camp_file.camp if camp_file is not None else None),
        year=year,
        event=event,
        file_title=camp_file.file_title if camp_file is not None else None,
    )


def _sidecar_provenance_line(
    occurrence: OccurrenceRecord, disclosure: Disclosure | None, release: _CampRelease | None
) -> str:
    """The sidecar's provenance line (data-use policy, Attribution rules 2 and 3), from the record alone.

    Composed by the card page's own :func:`~debate_core.domain.evidence_search.occurrence_provenance_line`,
    so the sidecar and the pilot say one line: the records are converted here into the fields the
    search index keeps of an occurrence. `[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Aff vs.
    Riverbend Invitational Round 4]`, the policy's own example, or `[Disclosed: hsld26 2026-09-15]` with
    no disclosure on record; a camp card's `[OpenEv: Cascade Institute 2026 — Policy, Climate Adv CP]`.
    """
    line = occurrence_provenance_line(
        caselist=occurrence.caselist,
        snapshot=occurrence.snapshot,
        provenance=True,
        side=disclosure.side.value if disclosure is not None else None,
        school=disclosure.school if disclosure is not None else None,
        team_code=disclosure.team_code if disclosure is not None else None,
        tournament=disclosure.tournament if disclosure is not None else None,
        round_label=(
            disclosure.round_label.raw
            if disclosure is not None and disclosure.round_label is not None
            else None
        ),
        camp=release.camp if release is not None else None,
        camp_year=release.year if release is not None else None,
        camp_event=release.event.value if release is not None and release.event is not None else None,
        camp_file_title=release.file_title if release is not None else None,
    )
    assert line is not None, "an occurrence with its provenance kept always has a line"
    return line


def header_line(recipe: ResolvedRecipe) -> str:
    """The file's one header analytic: where its cards came from, and that none of them is verified.

    A file with a camp card names OpenEv beside its caselists and calls each card copied from its
    source file, not from the file that disclosed it (`v1-e33-t06`). Neither says where to find who
    disclosed a card: a built file carries no provenance line, and a download of it carries no
    sidecar (`v1-e33-t08`, PM ruling 2026-10-22). A file built from a draft recipe says so first
    (`v1-e33-t03`).
    """
    draft = DRAFT_HEADER if recipe.recipe.status is RecipeStatus.DRAFT else ""
    stores = {card.occurrence.caselist for card in recipe.cards}
    if OPENEV_STORE not in stores:
        caselists = sorted(stores | {recipe.recipe.caselist})
        return (
            f"{draft}Disclosed cards (FILE_IMPORT) from {', '.join(caselists)}, each copied from the file "
            "that disclosed it and not verified by this platform."
        )
    caselists = ", ".join(sorted(stores - {OPENEV_STORE}))
    kinds, origins = (
        ("Disclosed and camp cards", f"{caselists} and OpenEv") if caselists else ("Camp cards", "OpenEv")
    )
    return (
        f"{draft}{kinds} (FILE_IMPORT) from {origins}, each copied from its source file and not verified by "
        "this platform."
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
    if occurrence.caselist == OPENEV_STORE:
        return SourceDocument(
            sha256=occurrence.source_sha256,
            byte_size=size,
            source_format=SourceFormat.DOCX,
            origin=SourceOrigin.OPENEV,
            caselist=None,
            first_seen_snapshot=_UNDATED,
            last_seen_snapshot=_UNDATED,
        )
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

    `source_stores`, when given, is the blob store under each source prefix of the evidence layout
    (`raw/caselist/hsld26`, `raw/openev/2031`), for a writer reading a bucket that keeps one store per
    prefix; `snapshots` is then not read. Without it, `snapshots` holds every source.
    """

    def __init__(
        self,
        *,
        snapshots: SnapshotStore,
        parser: DebateDocxParser | None = None,
        base: BaseTemplate | None = None,
        limits: PackageLimits = DEFAULT_PACKAGE_LIMITS,
        source_stores: Callable[[str], SnapshotStore] | None = None,
    ) -> None:
        self._snapshots = snapshots
        self._source_stores = source_stores
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
        docx, placed = self._write(resolved, by_path, copies, hyperlinks, header=request.header_line)
        problems = self._read_back(docx, resolved.recipe, located, placed)
        if problems:
            return FileBuildRefusal(
                tuple(
                    CardRefusal(
                        item.resolved.path,
                        item.resolved.fingerprint,
                        CardRefusalCode.READBACK_MISMATCH,
                        problems[item.resolved.path],
                    )
                    for item in located
                    if item.resolved.path in problems
                )
            )

        manifest = self._manifest(request, docx, located, placed, copies)
        manifest_json = manifest.to_json_bytes()
        camp_paths = manifest.camp_path_sidecar(manifest_json)
        return BuiltEvidenceFile(
            docx=docx,
            manifest=manifest,
            manifest_json=manifest_json,
            warnings=manifest.warnings,
            camp_paths_json=camp_paths.to_json_bytes() if camp_paths is not None else None,
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
        store = (
            self._snapshots
            if self._source_stores is None
            else self._source_stores(source_prefix(occurrence.caselist, occurrence.snapshot))
        )
        try:
            content = await store.get(occurrence.source_sha256)
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
        header: bool,
    ) -> tuple[bytes, dict[str, int]]:
        """The built file's bytes, and each card's first element index in it."""
        body = _Body(self._profile)
        placed = self._assemble(resolved, body, located, copies, header=header)
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
        *,
        header: bool,
    ) -> dict[str, int]:
        """Write the whole body; return each card's first element index in the built file.

        The header line comes first unless `header` is false (`v1-e39-t24`); the pocket, hat and block
        headings are written either way. A card is its tag, then its paragraphs through the cite and
        after it, with no provenance line between them (`v1-e33-t08`). Copied paragraphs are appended as
        copies of their own, so writing a body never takes a paragraph from a
        :class:`~.run_copier.CopiedCard`.
        """
        recipe = resolved.recipe
        placed: dict[str, int] = {}
        if header:
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
            for paragraph in (*copied.through_cite, *copied.after_cite):
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
    ) -> dict[str, str]:
        """Each card the built file does not read back as its source, with what differs."""
        camp = recipe.caselist == OPENEV_STORE
        built = SourceDocument(
            sha256=hashlib.sha256(docx).hexdigest(),
            byte_size=len(docx),
            source_format=SourceFormat.DOCX,
            origin=SourceOrigin.OPENEV if camp else SourceOrigin.CASELIST_ARCHIVE,
            caselist=None if camp else recipe.caselist,
            first_seen_snapshot=_UNDATED,
            last_seen_snapshot=_UNDATED,
        )
        parsed = self._parser.parse(docx, built, source_path="built-file.docx")
        if isinstance(parsed, ParseFailure):
            return {item.resolved.path: f"the built file does not parse: {parsed.reason}" for item in located}
        by_first = {card.provenance.first_element_index: card for card in parsed.cards}
        problems: dict[str, str] = {}
        for item in located:
            path = item.resolved.path
            problem = _difference(item, by_first.get(placed[path]))
            if problem is None and len(parsed.cards) != len(located):
                problem = f"the built file reads as {len(parsed.cards)} cards, not {len(located)}"
            if problem is not None:
                problems[path] = problem
        return problems

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
            camp_file = item.resolved.camp_file
            release = _camp_release(occurrence, camp_file) if occurrence.caselist == OPENEV_STORE else None
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
                    camp=release.camp if release is not None else None,
                    camp_year=release.year if release is not None else None,
                    camp_event=release.event if release is not None else None,
                    camp_file_title=release.file_title if release is not None else None,
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
                        text_sha256(card.tag) if override is not None and card.tag is not None else None
                    ),
                    provenance_line=_sidecar_provenance_line(occurrence, disclosure, release),
                    forbidden_characters_replaced=copied.forbidden_characters_replaced,
                    warnings=copied.warnings,
                    camp_path_disclosures=occurrence.camp_path_disclosures,
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
            recipe_status=recipe.status,
            builder_version=FILE_BUILDER_VERSION,
            parser_version=self._parser.parser_version,
            style_profile_version=self._parser.profile_version,
            fingerprint_version=recipe.fingerprint_version,
            built_at=request.built_at,
            docx_sha256=hashlib.sha256(docx).hexdigest(),
            cards=tuple(entries),
            warnings=tuple(warnings),
        )


def _difference(item: _Located, built: ParsedCard | None) -> str | None:
    """What a re-parsed card says differently from its source card, or None. Names fields, never text."""
    if built is None:
        return "no card starts where the card was written in the built file"
    source = item.card
    expected_tag = item.resolved.tag_override.text if item.resolved.tag_override is not None else source.tag
    checks = (
        ("cite", built.full_cite == source.full_cite),
        ("evidence text", built.evidence_text == source.evidence_text),
        (
            "formatting",
            formatting_sha256(built.formatting_spans, built.font_size_spans)
            == formatting_sha256(source.formatting_spans, source.font_size_spans),
        ),
        ("tag", built.tag == expected_tag),
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
