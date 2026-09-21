"""Turning a `w:p` into text and character-offset formatting, without changing a character of it.

This is the module the evidence-integrity rule lands on. A card's `evidence_text` is the
concatenated text of the runs it came from — not normalized, not re-flowed, not corrected — and
every :class:`~debate_core.domain.debate_files.FormattingSpan` is a pair of offsets into that
exact string. If the text and the offsets were derived from two different readings of the
paragraph, every underline in every card would be quietly wrong, so text and spans are built here
in one pass over one walk of the tree.

## What contributes text, and what does not

A paragraph's text is its runs' text in document order. Inside a run, `w:t` contributes its
characters exactly (including the spaces a `xml:space="preserve"` run holds), `w:tab` contributes
a tab, `w:br` and `w:cr` contribute a newline, and a drawing or an embedded object contributes
nothing.

Around the runs, the walk descends through the wrappers that hold them — hyperlinks, smart tags,
content controls, Markup Compatibility choices — and makes two decisions that are editorial
rather than mechanical:

* **A tracked insertion is text.** `w:ins` is descended into and its runs are kept. Somebody
  accepted-in-advance is still what the file says.
* **A tracked deletion is not.** `w:del` and `w:moveFrom` are skipped whole. Their text lives in
  `w:delText`, which nothing here reads: a card must be what the file would read as, not what it
  used to read as.
* **A text box is not part of the paragraph that holds it.** `w:txbxContent` is skipped here and
  its paragraphs are emitted separately, as `OTHER`, by the parser. Where Word writes a text box
  twice — a `mc:Choice` rendering and a `mc:Fallback` one — the fallback is skipped, so the box
  is read once.

## Underline, counted once

`classify_run` is the style profile's, not this module's. It is what collapses Verbatim's two
underline encodings into one `UNDERLINE`, which matters because CardMirror writes both the
`StyleUnderline` character style and a direct `<w:u>` on body runs when it exports, and 63% of
the surveyed corpus has been through CardMirror at least once. Two spans there would double the
underlining of most of the corpus. Adjacent spans that agree in every respect are then merged, so
a sentence underlined across four runs is one span rather than four.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final

from debate_core.domain.debate_files import FontSizeSpan, FormattingSpan
from debate_core.domain.style_profile import (
    RunEmphasis,
    StructuralUnit,
    StyleProfile,
)
from debate_core.evidence.style_classifier import (
    ParagraphDescription,
    RunDescription,
    classify_run,
)
from debate_core.integrations.docx_parser.package import (
    MC_NAMESPACE,
    DocxPackage,
    XmlElement,
    qualified_name,
)

__all__ = [
    "ReadParagraph",
    "SpannedText",
    "concatenate_spanned_text",
    "font_size_spans_for",
    "formatting_spans_for",
    "iter_text_box_paragraphs",
    "merge_adjacent_font_size_spans",
    "merge_adjacent_formatting_spans",
    "read_paragraph",
    "shift_font_size_spans",
    "shift_formatting_spans",
]

# -- the tags this module knows -----------------------------------------------------------------

W_PARAGRAPH: Final = qualified_name("p")
W_RUN: Final = qualified_name("r")
W_TEXT: Final = qualified_name("t")
W_TAB: Final = qualified_name("tab")
W_BREAK: Final = qualified_name("br")
W_CARRIAGE_RETURN: Final = qualified_name("cr")
W_NO_BREAK_HYPHEN: Final = qualified_name("noBreakHyphen")
W_SOFT_HYPHEN: Final = qualified_name("softHyphen")
W_INSERTED: Final = qualified_name("ins")
W_DELETED: Final = qualified_name("del")
W_MOVED_FROM: Final = qualified_name("moveFrom")
W_MOVED_TO: Final = qualified_name("moveTo")
W_TEXT_BOX_CONTENT: Final = qualified_name("txbxContent")
W_PARAGRAPH_PROPERTIES: Final = qualified_name("pPr")
W_RUN_PROPERTIES: Final = qualified_name("rPr")
W_PARAGRAPH_STYLE: Final = qualified_name("pStyle")
W_RUN_STYLE: Final = qualified_name("rStyle")
W_OUTLINE_LEVEL: Final = qualified_name("outlineLvl")
W_BOLD: Final = qualified_name("b")
W_ITALIC: Final = qualified_name("i")
W_ALL_CAPS: Final = qualified_name("caps")
W_UNDERLINE: Final = qualified_name("u")
W_HIGHLIGHT: Final = qualified_name("highlight")
W_SIZE: Final = qualified_name("sz")
W_VALUE: Final = qualified_name("val")
MC_ALTERNATE_CONTENT: Final = qualified_name("AlternateContent", MC_NAMESPACE)
MC_CHOICE: Final = qualified_name("Choice", MC_NAMESPACE)
MC_FALLBACK: Final = qualified_name("Fallback", MC_NAMESPACE)

#: Wrappers that hold runs without being one. The walk descends through them and they contribute
#: nothing of their own.
DESCEND_INTO: Final = frozenset(
    {
        qualified_name("hyperlink"),
        qualified_name("smartTag"),
        qualified_name("sdt"),
        qualified_name("sdtContent"),
        qualified_name("customXml"),
        qualified_name("fldSimple"),
        qualified_name("bdo"),
        qualified_name("dir"),
        MC_ALTERNATE_CONTENT,
        MC_CHOICE,
    }
)

#: What a run element contributes to the paragraph's text, beside `w:t`.
SUBSTITUTE_CHARACTERS: Final = {
    W_TAB: "\t",
    W_BREAK: "\n",
    W_CARRIAGE_RETURN: "\n",
    W_NO_BREAK_HYPHEN: "-",
    W_SOFT_HYPHEN: "",
}

#: `w:val` spellings of "off". OOXML allows all of them, and a bold-off on a heading run is lost
#: by a reader that treats any `w:b` element as bold.
FALSE_VALUES: Final = frozenset({"0", "false", "off"})


def _on_off(element: XmlElement | None) -> bool | None:
    """Read an OOXML on/off property as a tri-state.

    `None` means the run says nothing and inherits from its style, which is a different fact from
    "not bold" and is carried as such into the classifier.
    """
    if element is None:
        return None
    value = element.get(W_VALUE)
    if value is None:
        return True
    return value.strip().lower() not in FALSE_VALUES


def _integer(element: XmlElement | None) -> int | None:
    """Read a `w:val` that holds a number, or None when it is absent or not a number."""
    if element is None:
        return None
    value = element.get(W_VALUE)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _string(element: XmlElement | None) -> str | None:
    """Read a `w:val` that holds a token, or None when it is absent."""
    if element is None:
        return None
    return element.get(W_VALUE)


# --------------------------------------------------------------------------------------------
# Walking a paragraph
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class _TrackedChanges:
    """What the walk met on its way through a paragraph."""

    insertions_kept: int = 0
    deletions_dropped: int = 0


def _iter_runs(element: XmlElement, tracked: _TrackedChanges) -> Iterator[XmlElement]:
    """Yield the `w:r` elements under `element` in document order, in one pass.

    The rules the walk applies are the ones written up at the top of this module: keep `w:ins`,
    drop `w:del` and `w:moveFrom`, skip `w:txbxContent` and `mc:Fallback`, descend through every
    other wrapper, and let anything else contribute nothing.

    Comments and processing instructions need no guard here: the loader's parser is built with
    `remove_comments` and `remove_pis` on, so every node in the tree is an element.
    """
    for child in element:
        tag = child.tag
        if tag in (W_DELETED, W_MOVED_FROM):
            tracked.deletions_dropped += 1
            continue
        if tag in (W_TEXT_BOX_CONTENT, MC_FALLBACK):
            continue
        if tag == W_RUN:
            yield child
            continue
        if tag in (W_INSERTED, W_MOVED_TO):
            tracked.insertions_kept += 1
            yield from _iter_runs(child, tracked)
            continue
        if tag in DESCEND_INTO:
            yield from _iter_runs(child, tracked)


def _run_text(run: XmlElement) -> str:
    """The text one run contributes, exactly.

    `w:delText` is not read here and cannot reach this function: a deleted run is skipped whole by
    :func:`_iter_runs`. A drawing, an embedded object or a symbol contributes nothing.
    """
    pieces: list[str] = []
    for child in run:
        tag = child.tag
        if tag == W_TEXT:
            pieces.append(child.text or "")
        elif tag in SUBSTITUTE_CHARACTERS:
            pieces.append(SUBSTITUTE_CHARACTERS[tag])
    return "".join(pieces)


def _describe_run(run: XmlElement, package: DocxPackage) -> RunDescription:
    """Read one run's formatting into the neutral description the classifier takes."""
    properties = run.find(W_RUN_PROPERTIES)
    if properties is None:
        return RunDescription(text=_run_text(run))
    style_id = _string(properties.find(W_RUN_STYLE))
    return RunDescription(
        text=_run_text(run),
        character_style_id=style_id,
        character_style_name=package.style_name(style_id),
        character_style_based_on=package.based_on_chain(style_id),
        bold=_on_off(properties.find(W_BOLD)),
        italic=_on_off(properties.find(W_ITALIC)),
        all_caps=_on_off(properties.find(W_ALL_CAPS)),
        underline=_underline_value(properties.find(W_UNDERLINE)),
        highlight=_string(properties.find(W_HIGHLIGHT)),
        half_points=_integer(properties.find(W_SIZE)),
    )


def _underline_value(element: XmlElement | None) -> str | None:
    """Read `w:u`. A `w:u` with no `w:val` is a single underline, which is how Word writes one."""
    if element is None:
        return None
    return element.get(W_VALUE) or "single"


@dataclass(frozen=True, slots=True)
class ReadParagraph:
    """One paragraph, read: its text, its runs' formatting, and where each run sits in the text.

    `run_offsets` is aligned index for index with `description.runs`, so a span over a run is a
    slice of :attr:`text` and nothing has to re-derive where a run began. Runs that contributed
    no characters keep their place in both, with an empty range, because the classifier reads
    every run's formatting whether or not it carried text.
    """

    element_index: int
    text: str
    description: ParagraphDescription
    run_offsets: tuple[tuple[int, int], ...]
    in_table: bool = False
    insertions_kept: int = 0
    deletions_dropped: int = 0


def read_paragraph(
    element: XmlElement, package: DocxPackage, *, element_index: int, in_table: bool = False
) -> ReadParagraph:
    """Read one `w:p` into text, run descriptions and run offsets.

    The offsets are built as the text is, in the same loop, which is what makes them impossible
    to disagree with it.
    """
    tracked = _TrackedChanges()
    properties = element.find(W_PARAGRAPH_PROPERTIES)
    mark_properties = None if properties is None else properties.find(W_RUN_PROPERTIES)

    runs: list[RunDescription] = []
    offsets: list[tuple[int, int]] = []
    pieces: list[str] = []
    position = 0
    for run in _iter_runs(element, tracked):
        description = _describe_run(run, package)
        runs.append(description)
        offsets.append((position, position + len(description.text)))
        pieces.append(description.text)
        position += len(description.text)

    description = ParagraphDescription(
        runs=tuple(runs),
        style_id=None if properties is None else _string(properties.find(W_PARAGRAPH_STYLE)),
        style_name=package.style_name(
            None if properties is None else _string(properties.find(W_PARAGRAPH_STYLE))
        ),
        style_based_on=package.based_on_chain(
            None if properties is None else _string(properties.find(W_PARAGRAPH_STYLE))
        ),
        outline_level=_outline_level(properties),
        paragraph_bold=None if mark_properties is None else _on_off(mark_properties.find(W_BOLD)),
        paragraph_half_points=None if mark_properties is None else _integer(mark_properties.find(W_SIZE)),
        element_index=element_index,
        in_table=in_table,
    )
    return ReadParagraph(
        element_index=element_index,
        text="".join(pieces),
        description=description,
        run_offsets=tuple(offsets),
        in_table=in_table,
        insertions_kept=tracked.insertions_kept,
        deletions_dropped=tracked.deletions_dropped,
    )


def _outline_level(properties: XmlElement | None) -> int | None:
    """Read `w:outlineLvl`, keeping it inside the zero-to-eight range Word allows."""
    if properties is None:
        return None
    level = _integer(properties.find(W_OUTLINE_LEVEL))
    if level is None:
        # `w:outlineLvl w:val="0"` is level zero, which `_integer` rejects as non-positive.
        element = properties.find(W_OUTLINE_LEVEL)
        if element is not None and (element.get(W_VALUE) or "").strip() == "0":
            return 0
        return None
    return level if 0 <= level <= 8 else None


def iter_text_box_paragraphs(element: XmlElement) -> Iterator[XmlElement]:
    """Yield the paragraphs inside any text box in `element`, in document order.

    Word writes a text box twice — an `mc:Choice` rendering for modern Word and an `mc:Fallback`
    for older ones — and the two hold the same paragraphs. Only the first is yielded, so the box
    is read once. They become `OTHER` sections: a text box in a debate file is a page banner or a
    note in the margin, not a card.
    """
    seen_in_choice = False
    for container in element.iter(MC_ALTERNATE_CONTENT):
        choice = container.find(MC_CHOICE)
        source = choice if choice is not None else container.find(MC_FALLBACK)
        if source is None:
            continue
        seen_in_choice = True
        for content in source.iter(W_TEXT_BOX_CONTENT):
            yield from content.iter(W_PARAGRAPH)
    if seen_in_choice:
        return
    for content in element.iter(W_TEXT_BOX_CONTENT):
        yield from content.iter(W_PARAGRAPH)


# --------------------------------------------------------------------------------------------
# Spans
# --------------------------------------------------------------------------------------------


def formatting_spans_for(
    read: ReadParagraph, profile: StyleProfile, *, slot: StructuralUnit
) -> tuple[FormattingSpan, ...]:
    """Build the emphasis spans for one paragraph, merged, in offset order.

    `slot` is the structural unit the paragraph turned out to be, which is why this is called
    after classification rather than during the walk: the profile records which underline
    encoding is expected in which slot, and `classify_run` uses it to say whether a direct
    `<w:u>` here is the ordinary encoding or CardMirror's export writing both.
    """
    spans: list[FormattingSpan] = []
    for run, (start, end) in zip(read.description.runs, read.run_offsets, strict=True):
        if start == end:
            continue
        for match in classify_run(run, profile, slot=slot):
            spans.append(
                FormattingSpan(
                    emphasis=match.emphasis,
                    start_offset=start,
                    end_offset=end,
                    highlight_color=run.highlight if match.emphasis is RunEmphasis.HIGHLIGHT else None,
                    rule_id=match.rule_id,
                    match_source=match.match_source,
                )
            )
    return merge_adjacent_formatting_spans(spans)


def font_size_spans_for(read: ReadParagraph) -> tuple[FontSizeSpan, ...]:
    """Build the font-size spans for one paragraph, merged, in offset order.

    A run that declares no size inherits one from its style, and this records nothing for it
    rather than inventing the inherited number: `v1-e33-t02`'s writer needs to know which runs
    actually carried a `w:sz`.
    """
    spans: list[FontSizeSpan] = []
    for run, (start, end) in zip(read.description.runs, read.run_offsets, strict=True):
        if start == end or run.half_points is None:
            continue
        spans.append(FontSizeSpan(start_offset=start, end_offset=end, half_points=run.half_points))
    return merge_adjacent_font_size_spans(spans)


def merge_adjacent_formatting_spans(spans: Sequence[FormattingSpan]) -> tuple[FormattingSpan, ...]:
    """Join spans that touch and agree in every respect.

    A sentence underlined across four runs — which is what Word writes after somebody edits the
    middle of it — is one underline to a reader, and four spans would make a card's formatting
    depend on its editing history.
    """
    ordered = sorted(spans, key=lambda span: (span.start_offset, span.end_offset, span.emphasis))
    merged: list[FormattingSpan] = []
    for span in ordered:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.emphasis is span.emphasis
            and previous.highlight_color == span.highlight_color
            and previous.rule_id == span.rule_id
            and previous.match_source is span.match_source
            and previous.end_offset == span.start_offset
        ):
            merged[-1] = previous.evolve(end_offset=span.end_offset)
            continue
        merged.append(span)
    return tuple(merged)


def merge_adjacent_font_size_spans(spans: Sequence[FontSizeSpan]) -> tuple[FontSizeSpan, ...]:
    """Join size spans that touch and carry the same size."""
    ordered = sorted(spans, key=lambda span: (span.start_offset, span.end_offset))
    merged: list[FontSizeSpan] = []
    for span in ordered:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.half_points == span.half_points
            and previous.end_offset == span.start_offset
        ):
            merged[-1] = previous.evolve(end_offset=span.end_offset)
            continue
        merged.append(span)
    return tuple(merged)


def shift_formatting_spans(spans: Sequence[FormattingSpan], offset: int) -> tuple[FormattingSpan, ...]:
    """Move every span `offset` characters to the right, for text joined onto something else."""
    return tuple(
        span.evolve(start_offset=span.start_offset + offset, end_offset=span.end_offset + offset)
        for span in spans
    )


def shift_font_size_spans(spans: Sequence[FontSizeSpan], offset: int) -> tuple[FontSizeSpan, ...]:
    """Move every size span `offset` characters to the right."""
    return tuple(
        span.evolve(start_offset=span.start_offset + offset, end_offset=span.end_offset + offset)
        for span in spans
    )


@dataclass(frozen=True, slots=True)
class SpannedText:
    """Text with formatting at offsets into it: one paragraph, or several joined into a card.

    The unit a card's body is built from, and the unit `v2-e18-t01` will reuse for a card pasted
    into the web editor, which arrives as the same thing: text plus offsets.
    """

    text: str
    formatting_spans: tuple[FormattingSpan, ...] = field(default=())
    font_size_spans: tuple[FontSizeSpan, ...] = field(default=())


def concatenate_spanned_text(parts: Sequence[SpannedText], *, separator: str = "\n") -> SpannedText:
    """Join several spanned texts into one, moving every span onto the joined string.

    The separator is inserted between parts and belongs to no span, so a card body built from
    three paragraphs reads as three lines and no underline runs across the break.
    """
    if not parts:
        return SpannedText(text="")
    pieces: list[str] = []
    formatting: list[FormattingSpan] = []
    sizes: list[FontSizeSpan] = []
    position = 0
    for index, part in enumerate(parts):
        if index:
            pieces.append(separator)
            position += len(separator)
        formatting.extend(shift_formatting_spans(part.formatting_spans, position))
        sizes.extend(shift_font_size_spans(part.font_size_spans, position))
        pieces.append(part.text)
        position += len(part.text)
    return SpannedText(
        text="".join(pieces),
        formatting_spans=merge_adjacent_formatting_spans(formatting),
        font_size_spans=merge_adjacent_font_size_spans(sizes),
    )
