#!/usr/bin/env python3
"""Measure how the team formats its cards, from its own files, without reading a word of them.

The card format profiles in `config/format_profiles/` choose the sizes and colours a cut card is
rendered in. Those choices are only worth anything if they are the team's, so this script
measures them over the team's own season folders, **in place on the machine that holds them**.
No team file is copied into this repository in any form: a team file routinely carries cards
another program cut, so scrubbing cannot make one committable
(`tests/fixtures/team_samples/MANIFEST.md`).

**It never reads document text.** Every `w:t`, `w:delText` and `w:instrText` element is removed
from a part as soon as it is parsed, before anything looks at it, so nothing downstream can use
the words, their length or their count. What is left is style and run formatting: paragraph and
character style references, outline levels, underline, bold, highlight colour and font size. A
test builds the same files over different words and checks the results are identical.

What it measures, for the profile:

* the structural units the shared style profile resolves each paragraph to, with their outline
  levels and the (published) style ids that carried them;
* the cite block: whether a cite paragraph opens with a short cite in the cite character style,
  whether that is bold, and the size of the rest of the cite;
* the evidence: the size of underlined runs (the read text), the size of the runs that are not
  underlined (condensed text, where the team shrinks it), highlight colours and bold.

Evidence is found by position, as Verbatim lays it out: the paragraphs after a cite, up to the
next heading. A cite is a paragraph carrying a run in the cite character style (or the cite
paragraph style). Every value is resolved the way Word resolves it: direct formatting, then the
run's character style and its `basedOn` ancestors, then the paragraph's style, then the document
defaults.

## What it writes

* A Markdown report of counts (`--output`, or standard output). No file name, path, school, team
  code, debater name or document text. A style id is named only when it is published vocabulary,
  by the style survey's own rule; every other id is counted as "custom".
* Optionally the manifest of the files it read (`--manifest`): season, event and the first 16 hex
  digits of a keyed digest of each file's bytes, under the parser evaluation's key. Nothing else.

## Which files

Every `.docx` below the inputs, except Word lock files, files under a folder named by
`--exclude-dir` (a caselist or camp folder inside a season folder holds other programs' files),
byte-identical duplicates, files that are not readable packages and files whose folders name no
season or event. The season is the nearest folder named like `2025-2026`; the event is the
outermost folder naming LD, PF or Policy, by `scripts/select_eval_files.py`'s rules. The folders
read are the input folder and those below it, never the path above it.

    uv run python scripts/analyze_team_formatting.py \\
        ~/Documents/debate/2024-2025 ~/Documents/debate/2025-2026 ~/Documents/debate/2026-2027 \\
        --exclude-dir Opencaselist --exclude-dir "Camp Files" \\
        --output docs/data/team-format-survey.md \\
        --manifest tests/fixtures/team_samples/MANIFEST.md

Owned by `v1-e06-t03-format-profiles`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final
from zipfile import BadZipFile, ZipFile

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "debate_core" / "src"))

from select_eval_files import infer_format, infer_season  # noqa: E402
from survey_docx_styles import derived_from_published, read_file_usage  # noqa: E402
from tests.evals.parser.digests import keyed_digest, require_key  # noqa: E402

from debate_core.domain.style_profile import RunEmphasis, StructuralUnit, StyleProfile  # noqa: E402
from debate_core.evidence.style_profile_loader import load_style_profile, resolve_based_on_chain  # noqa: E402

__all__ = [
    "DIGEST_PREFIX_LENGTH",
    "FileFormatting",
    "ManifestRow",
    "SelectedFile",
    "Selection",
    "TeamFormatSurvey",
    "collect",
    "main",
    "read_file_formatting",
    "render_manifest",
    "render_report",
    "select_files",
]

W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

#: How many hex digits of each keyed digest the manifest shows, as the evaluation manifest does.
DIGEST_PREFIX_LENGTH: Final = 16

#: Elements that carry document text. Removed from every part before it is looked at.
TEXT_ELEMENTS: Final = tuple(f"{{{W_NS}}}{tag}" for tag in ("t", "delText", "instrText"))

#: The units that end a card's evidence: anything structural except the undertag, which belongs
#: to the tag above it and sits between the tag and its cite.
_CARD_ENDING_UNITS: Final = frozenset(
    {StructuralUnit.POCKET, StructuralUnit.HAT, StructuralUnit.BLOCK, StructuralUnit.TAG, StructuralUnit.ANALYTIC}
)
_REPORTED_UNITS: Final = (
    StructuralUnit.POCKET,
    StructuralUnit.HAT,
    StructuralUnit.BLOCK,
    StructuralUnit.TAG,
    StructuralUnit.CITE,
    StructuralUnit.EVIDENCE,
    StructuralUnit.ANALYTIC,
    StructuralUnit.UNDERTAG,
)
_UNDERLINED_EMPHASES: Final = frozenset({RunEmphasis.UNDERLINE, RunEmphasis.EMPHASIS})
_OFF_VALUES: Final = frozenset({"0", "false", "off"})

SKIPPED_EXCLUDED: Final = "in an excluded folder"
SKIPPED_DUPLICATE: Final = "duplicate bytes"
SKIPPED_NO_SEASON_OR_EVENT: Final = "no season or event in the folder names"
SKIPPED_UNREADABLE: Final = "not a readable .docx"


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


# --------------------------------------------------------------------------------------------
# Choosing the files
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectedFile:
    """One file to read. The path stays in memory; it never reaches an output."""

    path: Path
    season: str
    event: str
    content: bytes


@dataclass
class Selection:
    files: list[SelectedFile] = field(default_factory=list)
    skipped: Counter[str] = field(default_factory=Counter)


def select_files(inputs: Sequence[Path], exclude_dirs: Iterable[str] = ()) -> Selection:
    """Every `.docx` below `inputs`, by the rule in the module docstring, in path order."""
    del exclude_dirs  # red skeleton: every file is read
    selection = Selection()
    for root in inputs:
        for path in sorted(root.rglob("*.docx")):
            folders = (root.name, *path.relative_to(root).parts[:-1])
            event = infer_format(folders)
            selection.files.append(
                SelectedFile(
                    path=path,
                    season=infer_season(folders) or "unknown",
                    event=event.value if event else "unknown",
                    content=path.read_bytes(),
                )
            )
    return selection


# --------------------------------------------------------------------------------------------
# Reading one file
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _StyleFormatting:
    """What one `w:style` defines, and what it is based on."""

    style_type: str
    name: str
    based_on: str | None
    half_points: int | None
    bold: bool | None
    underlined: bool | None
    highlight: str | None
    outline_level: int | None


@dataclass
class FileFormatting:
    """Everything one file contributes. Holds no path, no name and no text."""

    season: str
    event: str
    template_family: str
    unit_paragraphs: Counter[str] = field(default_factory=Counter)
    unit_outline_levels: Counter[tuple[str, int | None]] = field(default_factory=Counter)
    unit_style_ids: Counter[tuple[str, str]] = field(default_factory=Counter)
    cite_paragraphs: int = 0
    cite_paragraphs_led_by_short_cite: int = 0
    short_cite_sizes: Counter[int | None] = field(default_factory=Counter)
    short_cite_bold_runs: int = 0
    full_cite_sizes: Counter[int | None] = field(default_factory=Counter)
    full_cite_bold_runs: int = 0
    evidence_paragraphs: int = 0
    condensed_evidence_paragraphs: int = 0
    underlined_sizes: Counter[int | None] = field(default_factory=Counter)
    not_underlined_sizes: Counter[int | None] = field(default_factory=Counter)
    highlight_colors: Counter[str] = field(default_factory=Counter)
    highlighted_not_underlined_runs: int = 0
    bold_evidence_runs: int = 0


def _parse_without_text(archive: ZipFile, part_name: str) -> etree._Element | None:
    """Parse a part and remove every text-bearing element before returning it."""
    try:
        data = archive.read(part_name)
    except KeyError:
        return None
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
    except etree.XMLSyntaxError:
        return None
    return root


def _value(element: etree._Element | None) -> str | None:
    return None if element is None else element.get(_w("val"))


def _toggle(element: etree._Element | None) -> bool | None:
    if element is None:
        return None
    value = element.get(_w("val"))
    return value is None or value.lower() not in _OFF_VALUES


def _underline(element: etree._Element | None) -> bool | None:
    if element is None:
        return None
    return (element.get(_w("val")) or "single") != "none"


def _half_points(element: etree._Element | None) -> int | None:
    value = _value(element)
    return int(value) if value is not None and value.isdigit() else None


def _highlight(element: etree._Element | None) -> str | None:
    value = _value(element)
    return value if value and value != "none" else None


@dataclass(frozen=True)
class _RunProperties:
    half_points: int | None
    bold: bool | None
    underlined: bool | None
    highlight: str | None


def _run_properties(properties: etree._Element | None) -> _RunProperties:
    if properties is None:
        return _RunProperties(None, None, None, None)
    return _RunProperties(
        half_points=_half_points(properties.find(_w("sz"))),
        bold=_toggle(properties.find(_w("b"))),
        underlined=_underline(properties.find(_w("u"))),
        highlight=_highlight(properties.find(_w("highlight"))),
    )


def _read_styles(root: etree._Element | None) -> tuple[dict[str, _StyleFormatting], _RunProperties]:
    if root is None:
        return {}, _RunProperties(None, None, None, None)
    styles: dict[str, _StyleFormatting] = {}
    for style in root.findall(_w("style")):
        style_id = style.get(_w("styleId"))
        if not style_id:
            continue
        run = _run_properties(style.find(_w("rPr")))
        paragraph = style.find(_w("pPr"))
        outline = _value(paragraph.find(_w("outlineLvl"))) if paragraph is not None else None
        styles[style_id] = _StyleFormatting(
            style_type=style.get(_w("type")) or "",
            name=_value(style.find(_w("name"))) or "",
            based_on=_value(style.find(_w("basedOn"))),
            half_points=run.half_points,
            bold=run.bold,
            underlined=run.underlined,
            highlight=run.highlight,
            outline_level=int(outline) if outline is not None and outline.isdigit() else None,
        )
    defaults = root.find(f"{_w('docDefaults')}/{_w('rPrDefault')}/{_w('rPr')}")
    return styles, _run_properties(defaults)


class _StyleTable:
    """A document's styles, with Word's inheritance resolved and cached."""

    def __init__(self, styles: dict[str, _StyleFormatting], defaults: _RunProperties, profile: StyleProfile) -> None:
        self._styles = styles
        self._defaults = defaults
        self._profile = profile
        self._based_on = {style_id: style.based_on for style_id, style in styles.items()}
        self._chains: dict[str, tuple[_StyleFormatting, ...]] = {}

    def chain(self, style_id: str | None) -> tuple[_StyleFormatting, ...]:
        """The style and its ancestors, nearest first; empty when it is not defined."""
        if style_id is None or style_id not in self._styles:
            return ()
        if style_id not in self._chains:
            ancestors = resolve_based_on_chain(style_id, self._based_on)
            self._chains[style_id] = tuple(
                self._styles[name] for name in (style_id, *ancestors) if name in self._styles
            )
        return self._chains[style_id]

    def paragraph_unit(self, style_id: str | None) -> StructuralUnit | None:
        if style_id is None:
            return None
        style = self._styles.get(style_id)
        match = self._profile.resolve_paragraph_style(
            style_id,
            style.name if style else None,
            resolve_based_on_chain(style_id, self._based_on),
        )
        return match.unit if match is not None else None

    def run_emphasis(self, style_id: str | None) -> RunEmphasis | None:
        if style_id is None:
            return None
        style = self._styles.get(style_id)
        match = self._profile.resolve_character_style(
            style_id,
            style.name if style else None,
            resolve_based_on_chain(style_id, self._based_on),
        )
        return match.emphasis if match is not None else None

    def outline_level(self, direct: int | None, style_id: str | None) -> int | None:
        if direct is not None:
            return direct
        return next((style.outline_level for style in self.chain(style_id) if style.outline_level is not None), None)

    def effective(self, direct: _RunProperties, run_style: str | None, paragraph_style: str | None) -> _RunProperties:
        """Direct formatting, then the run's style chain, then the paragraph's, then the defaults."""
        run_layers = (direct, *(_as_run(style) for style in self.chain(run_style)))
        layers = (*run_layers, *(_as_run(style) for style in self.chain(paragraph_style)), self._defaults)
        return _RunProperties(
            half_points=next((layer.half_points for layer in layers if layer.half_points is not None), None),
            bold=next((layer.bold for layer in layers if layer.bold is not None), None),
            underlined=next((layer.underlined for layer in layers if layer.underlined is not None), None),
            # Highlighting is direct formatting or a character style's; a paragraph style's
            # highlight is not how a debater marks a word.
            highlight=next((layer.highlight for layer in run_layers if layer.highlight), None),
        )


def _as_run(style: _StyleFormatting) -> _RunProperties:
    return _RunProperties(style.half_points, style.bold, style.underlined, style.highlight)


def _reported_style_id(style_id: str, table: _StyleTable) -> str:
    chain = table.chain(style_id)
    name = chain[0].name if chain else ""
    return style_id if derived_from_published(style_id, name) is not None else "custom"


def _own_runs(paragraph: etree._Element) -> list[etree._Element]:
    """The runs of `paragraph`, not those of a paragraph nested inside it (a text box)."""
    paragraph_tag = _w("p")
    return [
        run
        for run in paragraph.iter(_w("r"))
        if next(run.iterancestors(paragraph_tag), None) is paragraph
    ]


def _measure_body(body: etree._Element, table: _StyleTable, profile: StyleProfile, formatting: FileFormatting) -> None:
    return  # red skeleton: measures nothing
    shrink_maximum = profile.shrink.maximum_half_points
    in_card = False
    for paragraph in body.iter(_w("p")):
        properties = paragraph.find(_w("pPr"))
        paragraph_style = _value(properties.find(_w("pStyle"))) if properties is not None else None
        direct_outline = _value(properties.find(_w("outlineLvl"))) if properties is not None else None
        unit = table.paragraph_unit(paragraph_style)
        if unit in _REPORTED_UNITS and paragraph_style is not None:
            outline = table.outline_level(
                int(direct_outline) if direct_outline is not None and direct_outline.isdigit() else None,
                paragraph_style,
            )
            formatting.unit_paragraphs[unit.value] += 1
            formatting.unit_outline_levels[(unit.value, outline)] += 1
            formatting.unit_style_ids[(unit.value, _reported_style_id(paragraph_style, table))] += 1
        if unit in _CARD_ENDING_UNITS:
            in_card = False
            continue
        if unit is StructuralUnit.UNDERTAG:
            continue
        runs = _own_runs(paragraph)
        if not runs:
            continue
        measured = []
        for run in runs:
            run_properties = run.find(_w("rPr"))
            run_style = _value(run_properties.find(_w("rStyle"))) if run_properties is not None else None
            emphasis = table.run_emphasis(run_style)
            effective = table.effective(_run_properties(run_properties), run_style, paragraph_style)
            underlined = effective.underlined if effective.underlined is not None else emphasis in _UNDERLINED_EMPHASES
            measured.append((emphasis, effective, underlined))
        is_cite = unit is StructuralUnit.CITE or any(emphasis is RunEmphasis.CITE for emphasis, _, _ in measured)
        if is_cite:
            formatting.cite_paragraphs += 1
            if measured[0][0] is RunEmphasis.CITE:
                formatting.cite_paragraphs_led_by_short_cite += 1
            for emphasis, effective, _ in measured:
                if emphasis is RunEmphasis.CITE:
                    formatting.short_cite_sizes[effective.half_points] += 1
                    formatting.short_cite_bold_runs += bool(effective.bold)
                else:
                    formatting.full_cite_sizes[effective.half_points] += 1
                    formatting.full_cite_bold_runs += bool(effective.bold)
            in_card = True
            continue
        if not in_card:
            continue
        formatting.evidence_paragraphs += 1
        condensed = False
        for _, effective, underlined in measured:
            if underlined:
                formatting.underlined_sizes[effective.half_points] += 1
            else:
                formatting.not_underlined_sizes[effective.half_points] += 1
                if effective.half_points is not None and effective.half_points <= shrink_maximum:
                    condensed = True
                if effective.highlight:
                    formatting.highlighted_not_underlined_runs += 1
            if effective.highlight:
                formatting.highlight_colors[effective.highlight] += 1
            formatting.bold_evidence_runs += bool(effective.bold)
        formatting.condensed_evidence_paragraphs += condensed


def read_file_formatting(selected: SelectedFile, profile: StyleProfile) -> FileFormatting | None:
    """Measure one file, or return None when it is not a readable package."""
    family = read_file_usage(selected.path, "team").template_family
    if family == "unreadable":
        return None
    formatting = FileFormatting(season=selected.season, event=selected.event, template_family=family)
    try:
        with ZipFile(io.BytesIO(selected.content)) as archive:
            styles, defaults = _read_styles(_parse_without_text(archive, "word/styles.xml"))
            body = _parse_without_text(archive, "word/document.xml")
    except (BadZipFile, OSError):
        return None
    if body is None:
        return None
    _measure_body(body, _StyleTable(styles, defaults, profile), profile, formatting)
    return formatting


# --------------------------------------------------------------------------------------------
# The aggregate
# --------------------------------------------------------------------------------------------


@dataclass
class TeamFormatSurvey:
    """The aggregate over every file read. Every field is a count and safe to commit."""

    files_by_season_event: Counter[tuple[str, str]] = field(default_factory=Counter)
    families: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    unit_paragraphs: Counter[str] = field(default_factory=Counter)
    unit_files: Counter[str] = field(default_factory=Counter)
    unit_outline_levels: Counter[tuple[str, int | None]] = field(default_factory=Counter)
    unit_style_ids: Counter[tuple[str, str]] = field(default_factory=Counter)
    cite_paragraphs: int = 0
    cite_paragraphs_led_by_short_cite: int = 0
    short_cite_sizes: Counter[int | None] = field(default_factory=Counter)
    short_cite_bold_runs: int = 0
    full_cite_sizes: Counter[int | None] = field(default_factory=Counter)
    full_cite_size_modes: Counter[int | None] = field(default_factory=Counter)
    full_cite_bold_runs: int = 0
    evidence_paragraphs: int = 0
    condensed_evidence_paragraphs: int = 0
    underlined_sizes: Counter[int | None] = field(default_factory=Counter)
    underlined_size_modes: Counter[int | None] = field(default_factory=Counter)
    not_underlined_sizes: Counter[int | None] = field(default_factory=Counter)
    not_underlined_size_modes: Counter[int | None] = field(default_factory=Counter)
    highlight_colors: Counter[str] = field(default_factory=Counter)
    highlight_color_modes: Counter[str] = field(default_factory=Counter)
    highlighted_not_underlined_runs: int = 0
    bold_evidence_runs: int = 0
    season_highlight_colors: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    season_underlined_sizes: dict[str, Counter[int | None]] = field(default_factory=lambda: defaultdict(Counter))
    season_not_underlined_sizes: dict[str, Counter[int | None]] = field(default_factory=lambda: defaultdict(Counter))
    season_full_cite_sizes: dict[str, Counter[int | None]] = field(default_factory=lambda: defaultdict(Counter))

    @property
    def files(self) -> int:
        return sum(self.files_by_season_event.values())


def most_common[T](counts: Counter[T]) -> T | None:
    """The value with the highest count; a tie goes to the smaller value, `None` last."""
    if not counts:
        return None
    return min(counts, key=lambda value: (-counts[value], value is None, value if value is not None else 0))


def _mode_with_runs[T](modes: Counter[T], runs: Counter[T]) -> T | None:
    """The value most files favour; ties go to more runs, then to the smaller value."""
    if not modes:
        return None
    return min(modes, key=lambda value: (-modes[value], -runs[value], value is None, value if value is not None else 0))


def collect(files: Sequence[FileFormatting], skipped: Counter[str] | None = None) -> TeamFormatSurvey:
    """Fold per-file formatting into the aggregate."""
    survey = TeamFormatSurvey(skipped=Counter(skipped or {}))
    for formatting in files:
        survey.files_by_season_event[(formatting.season, formatting.event)] += 1
        survey.families[formatting.template_family] += 1
        survey.unit_paragraphs.update(formatting.unit_paragraphs)
        survey.unit_files.update(formatting.unit_paragraphs.keys())
        survey.unit_outline_levels.update(formatting.unit_outline_levels)
        survey.unit_style_ids.update(formatting.unit_style_ids)
        survey.cite_paragraphs += formatting.cite_paragraphs
        survey.cite_paragraphs_led_by_short_cite += formatting.cite_paragraphs_led_by_short_cite
        survey.short_cite_sizes.update(formatting.short_cite_sizes)
        survey.short_cite_bold_runs += formatting.short_cite_bold_runs
        survey.full_cite_sizes.update(formatting.full_cite_sizes)
        survey.full_cite_bold_runs += formatting.full_cite_bold_runs
        survey.evidence_paragraphs += formatting.evidence_paragraphs
        survey.condensed_evidence_paragraphs += formatting.condensed_evidence_paragraphs
        survey.underlined_sizes.update(formatting.underlined_sizes)
        survey.not_underlined_sizes.update(formatting.not_underlined_sizes)
        survey.highlight_colors.update(formatting.highlight_colors)
        survey.highlighted_not_underlined_runs += formatting.highlighted_not_underlined_runs
        survey.bold_evidence_runs += formatting.bold_evidence_runs
        for modes, counts in (
            (survey.full_cite_size_modes, formatting.full_cite_sizes),
            (survey.underlined_size_modes, formatting.underlined_sizes),
            (survey.not_underlined_size_modes, formatting.not_underlined_sizes),
        ):
            if counts:
                modes[most_common(counts)] += 1
        if formatting.highlight_colors:
            survey.highlight_color_modes[most_common(formatting.highlight_colors) or ""] += 1
        survey.season_highlight_colors[formatting.season].update(formatting.highlight_colors)
        survey.season_underlined_sizes[formatting.season].update(formatting.underlined_sizes)
        survey.season_not_underlined_sizes[formatting.season].update(formatting.not_underlined_sizes)
        survey.season_full_cite_sizes[formatting.season].update(formatting.full_cite_sizes)
    return survey


# --------------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------------

DOCS_INDEX_LINE: Final = (
    "<!-- docs-index: How the team formats its cards (sizes, highlight colours, cite layout), "
    "measured from its own files without reading their text -->"
)


def size_label(half_points: int | None) -> str:
    """`16` → `16 half-points (8 pt)`; None → `not set`."""
    if half_points is None:
        return "not set"
    return f"{half_points} half-points ({half_points / 2:g} pt)"


def _value_label(value: int | str | None) -> str:
    if value is None or isinstance(value, int):
        return size_label(value)
    return f"`{value}`"


def _summary_line[T: (int | None, str)](label: str, modes: Counter[T], runs: Counter[T], denominator: str) -> str:
    if not modes:
        return f"- {label}: none found"
    value = _mode_with_runs(modes, runs)
    return f"- {label}: {_value_label(value)}, most common in {modes[value]} of {sum(modes.values())} {denominator}"


def _distribution[T: (int | None, str)](title: str, runs: Counter[T], modes: Counter[T] | None = None) -> list[str]:
    header = f"| {title} | Runs |" + (" Files where most common |" if modes is not None else "")
    rule = "|---|---|" + ("---|" if modes is not None else "")
    lines = [header, rule]
    for value in sorted(runs, key=lambda key: (-runs[key], key is None, key if key is not None else 0)):
        row = f"| {_value_label(value)} | {runs[value]} |"
        if modes is not None:
            row += f" {modes.get(value, 0)} |"
        lines.append(row)
    if not runs:
        lines.append("| none | 0 |" + (" 0 |" if modes is not None else ""))
    return lines


def render_report(survey: TeamFormatSurvey, *, run_on: date, excluded_folders: Sequence[str]) -> str:
    """The committed Markdown report: counts only."""
    excluded = ", ".join(f"`{name}`" for name in excluded_folders) or "none"
    lines = [
        DOCS_INDEX_LINE,
        "# Team card formatting survey",
        "",
        "How the team formats its cards, measured from its own season folders in place by",
        "`scripts/analyze_team_formatting.py`. It reads style and run formatting only: every `w:t`",
        "is removed from a part before anything looks at it. No file name, path, school, team code,",
        "debater name or document text appears here. The format profiles in",
        "`config/format_profiles/` cite the lines of the summary below.",
        "",
        "| | |",
        "|---|---|",
        f"| Files analysed | {survey.files} |",
        f"| Run on | {run_on.isoformat()} |",
        f"| Folders excluded | {excluded} |",
        "| Selection | every `.docx` below the inputs, by rule; none chosen by hand |",
        "",
        "Sizes are `w:sz` values in half-points. Counts of runs weigh a long file more than a short",
        "one, so each table also says in how many files a value is the most common.",
        "",
        "## Summary",
        "",
        "Each line is the value most files favour, among the files that have one.",
        "",
        _summary_line(
            "Evidence highlight colour", survey.highlight_color_modes, survey.highlight_colors, "files with highlighting"
        ),
        _summary_line(
            "Underlined evidence size", survey.underlined_size_modes, survey.underlined_sizes, "files with underlining"
        ),
        _summary_line(
            "Not-underlined evidence size",
            survey.not_underlined_size_modes,
            survey.not_underlined_sizes,
            "files with text that is not underlined",
        ),
        _summary_line("Full cite size", survey.full_cite_size_modes, survey.full_cite_sizes, "files with cites"),
        f"- Evidence paragraphs holding text at or below the shrink maximum: "
        f"{survey.condensed_evidence_paragraphs} of {survey.evidence_paragraphs}",
        f"- Cite paragraphs led by a short cite in the cite style: "
        f"{survey.cite_paragraphs_led_by_short_cite} of {survey.cite_paragraphs}",
        f"- Short cite runs that are bold: {survey.short_cite_bold_runs} of {sum(survey.short_cite_sizes.values())}",
        f"- Full cite runs that are bold: {survey.full_cite_bold_runs} of {sum(survey.full_cite_sizes.values())}",
        "",
        "## Files",
        "",
        "| Season | Event | Files |",
        "|---|---|---|",
        *(
            f"| {season} | {event} | {count} |"
            for (season, event), count in sorted(survey.files_by_season_event.items())
        ),
        "",
        "Skipped:",
        "",
        "| Reason | Files |",
        "|---|---|",
        *(f"| {reason} | {count} |" for reason, count in sorted(survey.skipped.items())),
        *(["| none | 0 |"] if not survey.skipped else []),
        "",
        "Template families, by the style survey's classifier:",
        "",
        "| Family | Files |",
        "|---|---|",
        *(f"| {family} | {count} |" for family, count in sorted(survey.families.items())),
        "",
        "## Structural units",
        "",
        "What the shared style profile resolves each paragraph's style to. A style id is named only",
        "when it is published vocabulary; any other id is counted as `custom`.",
        "",
        "| Unit | Paragraphs | Files | Outline levels | Style ids |",
        "|---|---|---|---|---|",
    ]
    for unit in _REPORTED_UNITS:
        if not survey.unit_paragraphs[unit.value]:
            continue
        levels = ", ".join(
            f"{'none' if level is None else level} ({count})"
            for (name, level), count in sorted(
                survey.unit_outline_levels.items(), key=lambda item: (item[0][1] is None, item[0][1] or 0)
            )
            if name == unit.value
        )
        style_ids = ", ".join(
            f"`{style_id}` ({count})"
            for (name, style_id), count in sorted(survey.unit_style_ids.items(), key=lambda item: (-item[1], item[0][1]))
            if name == unit.value
        )
        lines.append(
            f"| {unit.value} | {survey.unit_paragraphs[unit.value]} | {survey.unit_files[unit.value]} | {levels} | {style_ids} |"
        )
    lines += [
        "",
        "## Cite block",
        "",
        f"{survey.cite_paragraphs} cite paragraphs, {survey.cite_paragraphs_led_by_short_cite} of them led by a run in",
        "the cite character style (the short cite). Runs in the cite style:",
        "",
        *_distribution("Short cite size", survey.short_cite_sizes),
        "",
        "The rest of the cite paragraph (the full cite):",
        "",
        *_distribution("Full cite size", survey.full_cite_sizes, survey.full_cite_size_modes),
        "",
        "## Evidence",
        "",
        f"{survey.evidence_paragraphs} evidence paragraphs: the paragraphs after a cite, up to the next heading.",
        "",
        "Underlined runs (the text that is read):",
        "",
        *_distribution("Underlined size", survey.underlined_sizes, survey.underlined_size_modes),
        "",
        "Runs that are not underlined (condensed, where the team shrinks them):",
        "",
        *_distribution("Not-underlined size", survey.not_underlined_sizes, survey.not_underlined_size_modes),
        "",
        "Highlight colours on evidence runs:",
        "",
        *_distribution("Colour", survey.highlight_colors, survey.highlight_color_modes),
        "",
        f"Highlighted runs that are not underlined: {survey.highlighted_not_underlined_runs}. "
        f"Bold evidence runs: {survey.bold_evidence_runs}.",
        "",
        "## By season",
        "",
        "The most common value in each season's runs.",
        "",
        "| Season | Files | Highlight | Underlined size | Not-underlined size | Full cite size |",
        "|---|---|---|---|---|---|",
    ]
    seasons = sorted({season for season, _ in survey.files_by_season_event})
    for season in seasons:
        files = sum(count for (name, _), count in survey.files_by_season_event.items() if name == season)
        highlight = most_common(survey.season_highlight_colors[season])
        lines.append(
            f"| {season} | {files} | {'none' if highlight is None else f'`{highlight}`'} "
            f"| {_season_size(survey.season_underlined_sizes[season])} "
            f"| {_season_size(survey.season_not_underlined_sizes[season])} "
            f"| {_season_size(survey.season_full_cite_sizes[season])} |"
        )
    lines += [
        "",
        "## Organization names in short cites",
        "",
        "Not counted, and not countable here. Whether a short cite names an organization whole",
        "(`Federal Office of ... 26`) or by its last word is a fact about the cite's words; the",
        "style of the run that carries it is the same either way, and this survey does not read",
        "words.",
        "",
    ]
    return "\n".join(lines)


def _season_size(counts: Counter[int | None]) -> str:
    return "none" if not counts else size_label(most_common(counts))


# --------------------------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, order=True)
class ManifestRow:
    digest: str
    season: str
    event: str


def manifest_rows(files: Sequence[SelectedFile], key: bytes) -> list[ManifestRow]:
    """One row per file read, sorted by digest: the order says nothing about the files."""
    return sorted(
        ManifestRow(digest=hashlib.sha256(selected.content).hexdigest()[:DIGEST_PREFIX_LENGTH], season=selected.season, event=selected.event)
        for selected in files
    )


def render_manifest(rows: Sequence[ManifestRow], *, run_on: date, excluded_folders: Sequence[str]) -> str:
    excluded = ", ".join(f"`{name}`" for name in excluded_folders) or "none"
    lines = [
        "# Team format samples",
        "",
        "This is a manifest of files held elsewhere, not a fixture directory. **There is no `.docx`",
        "here, and that is correct.** The team files the card format profiles are measured on stay",
        "in the operator's season folders. None of them is copied into this repository in any form,",
        "scrubbed or otherwise.",
        "",
        "Why: a team file routinely carries cards another program cut, so scrubbing does not make it",
        "committable. Scrubbing removes authorship metadata; it does not remove somebody else's cards.",
        "`docs/policies/caselist-data-use.md` prohibitions 1, 9 and 10 and the rulings behind",
        "`v1-e31-t02` and `v1-e31-t03` settle it, as",
        "[the parser evaluation's manifest](../debate_files/eval/MANIFEST.md) explains.",
        "",
        "What the repository holds instead:",
        "",
        "* this list: season, event and the first 16 hex digits of a keyed digest (HMAC-SHA256 under",
        "  the parser evaluation's key, never a plain hash) of each file read, and nothing else;",
        "* the counts measured from them, in",
        "  [`docs/data/team-format-survey.md`](../../../docs/data/team-format-survey.md);",
        "* synthetic files laid out the same way, in",
        "  [`../debate_files/team_format/`](../debate_files/team_format/), for the tests.",
        "",
        "## How the files were chosen",
        "",
        "By rule, not by hand: every `.docx` in the operator's 2024-2025, 2025-2026 and 2026-2027",
        f"season folders, except Word lock files, files under {excluded} (other programs' files",
        "kept inside a season folder), byte-identical duplicates, unreadable packages and files whose",
        "folders name no event. No sample was drawn: reading every file takes seconds.",
        "`scripts/analyze_team_formatting.py` wrote this list.",
        "",
        f"Run on {run_on.isoformat()}: {len(rows)} files.",
        "",
        "| Season | Event | Digest |",
        "|---|---|---|",
        *(f"| {row.season} | {row.event} | `{row.digest}` |" for row in rows),
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def analyze(inputs: Sequence[Path], exclude_dirs: Sequence[str], profile: StyleProfile) -> tuple[Selection, TeamFormatSurvey, list[SelectedFile]]:
    """Select, read and fold. Returns the selection, the aggregate and the files actually read."""
    selection = select_files(inputs, exclude_dirs)
    skipped = Counter(selection.skipped)
    read: list[FileFormatting] = []
    read_files: list[SelectedFile] = []
    for selected in selection.files:
        formatting = read_file_formatting(selected, profile)
        if formatting is None:
            skipped[SKIPPED_UNREADABLE] += 1
            continue
        read.append(formatting)
        read_files.append(selected)
    return selection, collect(read, skipped), read_files


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="analyze_team_formatting.py",
        description="Measure the team's card formatting from its own files, reading no text.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Season folders, or a folder holding them.")
    parser.add_argument("--exclude-dir", action="append", default=[], help="A folder name to leave out.")
    parser.add_argument("--output", type=Path, help="Write the report here instead of standard output.")
    parser.add_argument("--manifest", type=Path, help="Also write the manifest of the files read here.")
    parser.add_argument("--run-on", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD; default today.")
    arguments = parser.parse_args(argv)

    key = b""  # red skeleton: no key needed
    inputs = [path.expanduser() for path in arguments.inputs]
    _, survey, read_files = analyze(inputs, arguments.exclude_dir, load_style_profile())
    report = render_report(survey, run_on=arguments.run_on, excluded_folders=arguments.exclude_dir)
    if arguments.output is None:
        print(report)
    else:
        arguments.output.write_text(report, encoding="utf-8")
    if arguments.manifest is not None and key is not None:
        arguments.manifest.parent.mkdir(parents=True, exist_ok=True)
        arguments.manifest.write_text(
            render_manifest(manifest_rows(read_files, key), run_on=arguments.run_on, excluded_folders=arguments.exclude_dir),
            encoding="utf-8",
        )
    print(
        f"{survey.files} files read, {sum(survey.skipped.values())} skipped",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
