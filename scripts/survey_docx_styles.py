#!/usr/bin/env python3
"""Survey which Word styles real debate files actually use.

The style profile in `debate_core.domain.style_profile` claims to know what a pocket, a hat, a
block, a tag, a cite and an underlined run look like in a `.docx`. That claim is only worth
anything if it was measured. This script measures it: it walks a directory of real team, caselist
and camp files, reads **only** style information out of each one, and writes an aggregate
Markdown report.

**It never reads document text.** `w:t` is not touched. What comes out is counts of style ids,
style names, `basedOn` links, outline levels and highlight colours — plus, per file, which
template family it belongs to. What goes into the committed report is aggregate only: no file
names, no schools, no team codes, no paragraph text.

Two privacy guards back that up:

* A style id or name is only named in the report if it appears in at least `--min-files` distinct
  files (two by default). A style a team named after itself — `WFBTag` — is a real thing, and a
  one-off custom style is exactly where such a name would sit. Everything below the threshold is
  counted in an "appears in one file only" bucket instead.
* File names, directory names below the category level and paths never reach the output.

**The full aggregate is always written**, to `docs/data/debate-file-style-survey.full.json`, which
is gitignored. It holds every style id, including the ones the report withholds, and it is what
you read to find a new alias worth adding to the profile. The report is a summary of that file;
keeping the file beside it is what makes the summary checkable rather than merely trusted.

## Template families

Each file is placed in exactly one family, from its style *references* rather than its style
*definitions* — most debate files define the whole Verbatim style set whether or not they use it.

| Family | How it is recognised |
|---|---|
| `verbatim` | References at least one Verbatim paragraph style *and* one Verbatim character style. |
| `cardmirror` | A `verbatim` file that also carries CardMirror's `pmd-heading-` bookmark ids. |
| `wiki-converted` | Verbatim styles are *defined* but never referenced: everything is direct
  formatting, which is what the caselist wiki-to-docx conversion produces. |
| `other-heuristic` | No Verbatim style references. Structure has to come from the heuristic classifier. |
| `unreadable` | Not a readable `.docx` package. |

## Running it

This runs against files that stay on the machine holding them and never enter this repository.

    uv run python scripts/survey_docx_styles.py \
        --input ~/debate-files \
        --input team=~/season-2026-2027 \
        --output docs/data/debate-file-style-survey.md

`--input` is repeatable. A bare path takes its categories from its immediate subdirectories, the
layout `scripts/cardmirror-roundtrip/` uses; files sitting directly in it take `--category`.
`CATEGORY=PATH` puts everything under one category instead, which is how several directories
holding the same kind of file are surveyed together. A file reachable from two inputs is counted
once. Reading style information only, it manages roughly 80 files a second — a few thousand files
is seconds, not minutes.

Owned by `v1-e31-t02-verbatim-style-profile`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from zipfile import BadZipFile, ZipFile

from lxml import etree

__all__ = [
    "CARDMIRROR_BOOKMARK_PREFIX",
    "DEFAULT_AGGREGATE_PATH",
    "FileStyleUsage",
    "StyleSurvey",
    "SurveyError",
    "collect_usage",
    "derived_from_published",
    "elide_style_id",
    "published_style_ids",
    "main",
    "read_file_usage",
    "render_report",
    "survey_directory",
    "survey_inputs",
]

W_NS: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

#: Paragraph style ids Verbatim and CardMirror write, normalized. Matching any of these is what
#: makes a file "a Verbatim file" for the purposes of this survey.
VERBATIM_PARAGRAPH_STYLE_IDS: Final = frozenset(
    {"heading1", "heading2", "heading3", "heading4", "analytic", "undertag"}
)

#: Character style ids Verbatim and CardMirror write, normalized.
VERBATIM_CHARACTER_STYLE_IDS: Final = frozenset(
    {
        "style13ptbold",
        "styleunderline",
        "emphasis",
        "undertagchar",
        "analyticchar",
        "heading1char",
        "heading2char",
        "heading3char",
        "heading4char",
    }
)

#: Style ids that are published vocabulary: Verbatim's and CardMirror's own ids, Word's built-in
#: ids, and the ids the Google Docs and wiki-to-docx converters emit. A style id is only *named*
#: in the committed report if it is one of these or is mechanically derived from one — see
#: `derived_from_published`. Everything else is counted but not named, because a style id a
#: person chose is a place a person's name ends up: `MaggieTag` and `JordanAnalytics` are both
#: real ids in the corpus this survey was first run against. The operator sees the full list in
#: the `--json` aggregate, which is not committed.
WORD_BUILT_IN_STYLE_IDS: Final = frozenset(
    {
        "normal",
        "normalweb",
        "nospacing",
        "defaultparagraphfont",
        "listparagraph",
        "bodytext",
        "bodytextchar",
        "title",
        "titlechar",
        "subtitle",
        "subtitlechar",
        "header",
        "headerchar",
        "footer",
        "footerchar",
        "hyperlink",
        "followedhyperlink",
        "strong",
        "intenseemphasis",
        "quote",
        "intensequote",
        "caption",
        "booktitle",
        "footnotereference",
        "footnotetext",
        "endnotereference",
        "endnotetext",
        "commentreference",
        "commenttext",
        "annotationreference",
        "annotationtext",
        "pagenumber",
        "linenumber",
        "tablenormal",
        "tablegrid",
        "balloontext",
        "placeholdertext",
        "tocheading",
        "heading5",
        "heading6",
        "heading7",
        "heading8",
        "heading9",
        "heading5char",
        "heading6char",
        "heading7char",
        "heading8char",
        "heading9char",
    }
    | {f"toc{level}" for level in range(1, 10)}
)

#: Ids the Google Docs, Office-web and wiki-to-docx exporters emit. They are machine-generated
#: and carry no one's name, but they are worth naming because a caselist upload full of them is
#: a file the heuristic classifier has to handle.
CONVERTER_STYLE_IDS: Final = frozenset(
    {"normaltextrun", "eop", "applestylespan", "appleconvertedspace", "uiprovider", "contentcontrol"}
)

#: Verbatim's own further vocabulary, beyond the ids the family test keys on.
VERBATIM_EXTRA_STYLE_IDS: Final = frozenset(
    {"cite", "citechar", "cardbody", "citeparagraph", "pocket", "hat", "block", "tag"}
)

#: CardMirror stamps every heading with a bookmark named `pmd-heading-<uuid>`, which is how its
#: stable heading ids survive a round-trip. Its presence means the file has been through
#: CardMirror at least once.
CARDMIRROR_BOOKMARK_PREFIX: Final = "pmd-heading-"

#: Parts whose style references are counted. Headers and footers carry styled text too.
BODY_PARTS: Final = ("word/document.xml",)
BODY_PART_PREFIXES: Final = ("word/header", "word/footer")

DEFAULT_MINIMUM_FILES: Final = 2

#: Where the full, unredacted aggregate is written on every run. It sits beside the committed
#: report so whoever refreshes one reads the other, and it is gitignored because it carries every
#: style id the report withholds — including the ones a team named after a person. It is always
#: written: the report is a summary of this file, and a summary nobody can check is a summary
#: nobody should trust.
DEFAULT_AGGREGATE_PATH: Final = Path("docs/data/debate-file-style-survey.full.json")

#: Repository root, so the default aggregate path resolves the same from any working directory.
REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]


class SurveyError(RuntimeError):
    """The corpus directory is missing or unusable."""


def _qualified(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def published_style_ids() -> frozenset[str]:
    """Every normalized style id this report is allowed to name outright."""
    return (
        VERBATIM_PARAGRAPH_STYLE_IDS
        | VERBATIM_CHARACTER_STYLE_IDS
        | VERBATIM_EXTRA_STYLE_IDS
        | WORD_BUILT_IN_STYLE_IDS
        | CONVERTER_STYLE_IDS
    )


def derived_from_published(style_id: str, style_name: str = "") -> str | None:
    """Return the published style this id or name is a Word-deduplicated spelling of, if any.

    Word appends a digit whenever it imports a style whose name collides with one already in the
    document, one digit per collision: `Heading 4` becomes `Heading 41`, then `Heading 411`. Both
    the id and the display name are tried, because the drift shows up in either.
    """
    published = published_style_ids()
    for candidate in (style_id, style_name):
        normalized = normalize_style_id(candidate or "")
        if normalized in published:
            return normalized
        while normalized and normalized[-1].isdigit():
            normalized = normalized[:-1]
            if normalized in published:
                return normalized
    return None


def normalize_style_id(style_id: str) -> str:
    """Lower-case and drop separators, so `Style 13pt Bold` and `Style13ptBold` are one id.

    The same normalization `scripts/compare_docx_roundtrip.py` uses, and the same one the style
    profile's alias resolution uses, because they are all looking at the same files.
    """
    return style_id.replace(" ", "").replace("-", "").replace("_", "").lower()


@dataclass
class FileStyleUsage:
    """Everything one file contributes to the survey. Deliberately holds no path and no text."""

    category: str
    template_family: str = "other-heuristic"
    defined_styles: dict[str, tuple[str, str, str | None]] = field(default_factory=dict)
    """`styleId -> (type, name, basedOn)` from `word/styles.xml`."""
    paragraph_style_references: Counter[str] = field(default_factory=Counter)
    character_style_references: Counter[str] = field(default_factory=Counter)
    outline_levels: Counter[int] = field(default_factory=Counter)
    highlight_colors: Counter[str] = field(default_factory=Counter)
    cardmirror_heading_bookmarks: int = 0
    error: str | None = None


def _parse_part(archive: ZipFile, part_name: str) -> etree._Element | None:
    try:
        data = archive.read(part_name)
    except KeyError:
        return None
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    try:
        return etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError:
        return None


def _read_style_definitions(root: etree._Element) -> dict[str, tuple[str, str, str | None]]:
    definitions: dict[str, tuple[str, str, str | None]] = {}
    for style in root.findall(_qualified("style")):
        style_id = style.get(_qualified("styleId"))
        if not style_id:
            continue
        style_type = style.get(_qualified("type")) or "unknown"
        name_element = style.find(_qualified("name"))
        name = (name_element.get(_qualified("val")) or "") if name_element is not None else ""
        based_on_element = style.find(_qualified("basedOn"))
        based_on = based_on_element.get(_qualified("val")) if based_on_element is not None else None
        definitions[style_id] = (style_type, name, based_on)
    return definitions


def _count_body_references(root: etree._Element, usage: FileStyleUsage) -> None:
    """Count style references, outline levels, highlights and heading bookmarks.

    `w:t` is never visited: the loop dispatches on tag name and no branch reads element text.
    """
    paragraph_style_tag = _qualified("pStyle")
    run_style_tag = _qualified("rStyle")
    outline_tag = _qualified("outlineLvl")
    highlight_tag = _qualified("highlight")
    bookmark_tag = _qualified("bookmarkStart")
    value_attribute = _qualified("val")
    bookmark_name_attribute = _qualified("name")

    for element in root.iter():
        tag = element.tag
        if tag == paragraph_style_tag:
            value = element.get(value_attribute)
            if value:
                usage.paragraph_style_references[value] += 1
        elif tag == run_style_tag:
            value = element.get(value_attribute)
            if value:
                usage.character_style_references[value] += 1
        elif tag == outline_tag:
            value = element.get(value_attribute)
            if value and value.isdigit():
                usage.outline_levels[int(value)] += 1
        elif tag == highlight_tag:
            value = element.get(value_attribute)
            if value and value != "none":
                usage.highlight_colors[value] += 1
        elif tag == bookmark_tag:
            name = element.get(bookmark_name_attribute) or ""
            if name.startswith(CARDMIRROR_BOOKMARK_PREFIX):
                usage.cardmirror_heading_bookmarks += 1


def classify_template_family(usage: FileStyleUsage) -> str:
    """Place one file in exactly one template family. See the module docstring for the rules."""
    paragraph_hits = {
        normalize_style_id(style) for style in usage.paragraph_style_references
    } & VERBATIM_PARAGRAPH_STYLE_IDS
    character_hits = {
        normalize_style_id(style) for style in usage.character_style_references
    } & VERBATIM_CHARACTER_STYLE_IDS
    defined = {normalize_style_id(style) for style in usage.defined_styles}

    if paragraph_hits and character_hits:
        return "cardmirror" if usage.cardmirror_heading_bookmarks else "verbatim"
    if not paragraph_hits and not character_hits and defined & VERBATIM_CHARACTER_STYLE_IDS:
        return "wiki-converted"
    return "other-heuristic"


def read_file_usage(path: Path, category: str) -> FileStyleUsage:
    """Read one `.docx` and return its style usage. Never raises for a bad file."""
    usage = FileStyleUsage(category=category)
    try:
        with ZipFile(path) as archive:
            styles_root = _parse_part(archive, "word/styles.xml")
            if styles_root is not None:
                usage.defined_styles = _read_style_definitions(styles_root)
            body_parts = [
                name
                for name in archive.namelist()
                if name in BODY_PARTS or name.startswith(BODY_PART_PREFIXES)
            ]
            if not body_parts:
                usage.error = "no document body"
                usage.template_family = "unreadable"
                return usage
            for part_name in sorted(body_parts):
                body_root = _parse_part(archive, part_name)
                if body_root is not None:
                    _count_body_references(body_root, usage)
    except (BadZipFile, OSError) as error:
        usage.error = type(error).__name__
        usage.template_family = "unreadable"
        return usage
    usage.template_family = classify_template_family(usage)
    return usage


def iter_corpus(root: Path, default_category: str) -> Iterator[tuple[Path, str]]:
    """Yield `(path, category)` for every `.docx` under `root`.

    The immediate subdirectories of `root` name the categories; anything sitting directly in
    `root` takes `default_category`. Word's lock files (`~$…`) are skipped.
    """
    if not root.is_dir():
        raise SurveyError(f"corpus directory not found: {root}")
    for path in sorted(root.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        relative = path.relative_to(root)
        category = relative.parts[0] if len(relative.parts) > 1 else default_category
        yield path, category


def iter_labelled_corpus(root: Path, category: str) -> Iterator[tuple[Path, str]]:
    """Yield `(path, category)` for every `.docx` under `root`, all in one category."""
    if not root.is_dir():
        raise SurveyError(f"corpus directory not found: {root}")
    for path in sorted(root.rglob("*.docx")):
        if not path.name.startswith("~$"):
            yield path, category


def parse_input_argument(value: str, default_category: str) -> Iterator[tuple[Path, str]]:
    """Expand one `--input`, which is either `PATH` or `CATEGORY=PATH`.

    `PATH` takes its categories from the immediate subdirectories, the layout
    `scripts/cardmirror-roundtrip/` uses. `CATEGORY=PATH` puts everything under `PATH` in one
    category, which is how several directories holding the same kind of file — a team's files
    across three seasons, say — are surveyed as one category.
    """
    category, separator, path_text = value.partition("=")
    if separator and category and not category.startswith((".", "/", "~")):
        return iter_labelled_corpus(Path(path_text).expanduser(), category)
    return iter_corpus(Path(value).expanduser(), default_category)


# --------------------------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------------------------


@dataclass
class StyleSurvey:
    """The aggregate. Every field here is safe to commit."""

    files_by_category: Counter[str] = field(default_factory=Counter)
    families_by_category: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    paragraph_style_files: Counter[str] = field(default_factory=Counter)
    paragraph_style_occurrences: Counter[str] = field(default_factory=Counter)
    character_style_files: Counter[str] = field(default_factory=Counter)
    character_style_occurrences: Counter[str] = field(default_factory=Counter)
    defined_style_files: Counter[str] = field(default_factory=Counter)
    style_names: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    based_on_links: Counter[tuple[str, str]] = field(default_factory=Counter)
    outline_levels: Counter[int] = field(default_factory=Counter)
    highlight_colors: Counter[str] = field(default_factory=Counter)
    cardmirror_files: int = 0
    unreadable_files: int = 0

    @property
    def total_files(self) -> int:
        return sum(self.files_by_category.values())


def collect_usage(usages: Sequence[FileStyleUsage]) -> StyleSurvey:
    """Fold per-file usage into the aggregate."""
    survey = StyleSurvey()
    for usage in usages:
        survey.files_by_category[usage.category] += 1
        survey.families_by_category[usage.category][usage.template_family] += 1
        if usage.template_family == "unreadable":
            survey.unreadable_files += 1
            continue
        if usage.cardmirror_heading_bookmarks:
            survey.cardmirror_files += 1
        for style_id, (_, name, based_on) in usage.defined_styles.items():
            survey.defined_style_files[style_id] += 1
            if name:
                survey.style_names[style_id][name] += 1
            if based_on:
                survey.based_on_links[(style_id, based_on)] += 1
        for style_id, count in usage.paragraph_style_references.items():
            survey.paragraph_style_files[style_id] += 1
            survey.paragraph_style_occurrences[style_id] += count
        for style_id, count in usage.character_style_references.items():
            survey.character_style_files[style_id] += 1
            survey.character_style_occurrences[style_id] += count
        survey.outline_levels.update(usage.outline_levels)
        survey.highlight_colors.update(usage.highlight_colors)
    return survey


def survey_directory(root: Path, default_category: str = "uncategorized") -> StyleSurvey:
    """Read every `.docx` under `root` and return the aggregate."""
    return survey_inputs([str(root)], default_category)


def survey_inputs(inputs: Sequence[str], default_category: str = "uncategorized") -> StyleSurvey:
    """Read every `.docx` named by the `--input` arguments and return one aggregate.

    A file reachable from two inputs is counted once, under the first category that claims it.
    """
    seen: set[Path] = set()
    usages: list[FileStyleUsage] = []
    for value in inputs:
        for path, category in parse_input_argument(value, default_category):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            usages.append(read_file_usage(path, category))
    return collect_usage(usages)


# --------------------------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------------------------

FAMILY_ORDER: Final = ("verbatim", "cardmirror", "wiki-converted", "other-heuristic", "unreadable")


#: Word builds a style id by concatenating every name a style has ever had, so a style that has
#: been merged across a few files grows into something like
#: `StyleHeading1Heading1Char1<name>HeadingHeading1CharChar` — and the fragment in the middle is
#: sometimes the first name of whoever created it. Anything longer than this is elided in the
#: middle: the head and tail carry the signal (what it was based on), the middle carries the risk.
MAXIMUM_REPORTED_STYLE_ID: Final = 40


def elide_style_id(style_id: str) -> str:
    """Shorten an over-long Word-concatenated style id, keeping its head and tail."""
    if len(style_id) <= MAXIMUM_REPORTED_STYLE_ID:
        return style_id
    return f"{style_id[:20]}…{style_id[-12:]}"


def elide_style_name(name: str) -> str:
    """The same treatment for a style's display name."""
    if len(name) <= MAXIMUM_REPORTED_STYLE_ID:
        return name
    return f"{name[:20]}…{name[-12:]}"


def _share(count: int, total: int) -> str:
    return f"{100 * count / total:.0f}%" if total else "—"


def _first_name(survey: StyleSurvey, style_id: str) -> str:
    """The most common display name recorded for `style_id`, or an empty string."""
    names = survey.style_names.get(style_id)
    return names.most_common(1)[0][0] if names else ""


def _style_reference_table(
    files: Counter[str],
    occurrences: Counter[str],
    style_names: dict[str, Counter[str]],
    minimum_files: int,
) -> list[str]:
    """One style-reference table, naming only published or mechanically derived ids."""
    rows = ["| Style id | Style name(s) | Files | References |", "|---|---|---|---|"]
    withheld_ids = 0
    withheld_files = 0
    for style_id, file_count in files.most_common():
        if file_count < minimum_files:
            continue
        display_name = style_names.get(style_id, Counter()).most_common(1)
        first_name = display_name[0][0] if display_name else ""
        if derived_from_published(style_id, first_name) is None:
            withheld_ids += 1
            withheld_files += file_count
            continue
        names = ", ".join(elide_style_name(name) for name, _ in style_names[style_id].most_common(2)) or "—"
        rows.append(f"| `{elide_style_id(style_id)}` | {names} | {file_count} | {occurrences[style_id]} |")
    below_threshold = sum(1 for count in files.values() if count < minimum_files)
    if withheld_ids:
        rows.append(
            f"| _(custom or team-specific ids, not named)_ | — | {withheld_ids} distinct ids, "
            f"{withheld_files} file references | — |"
        )
    if below_threshold:
        rows.append(f"| _(below the reporting threshold)_ | — | {below_threshold} distinct ids | — |")
    return rows


def render_report(
    survey: StyleSurvey,
    *,
    minimum_files: int = DEFAULT_MINIMUM_FILES,
    generated_at: datetime | None = None,
    corpus_description: str = "",
) -> str:
    """Render the committed Markdown report. Aggregates only — see the module docstring."""
    moment = (generated_at or datetime.now(UTC)).date().isoformat()
    total = survey.total_files
    lines: list[str] = [
        "# Debate file style survey",
        "",
        "What Word styles real debate files actually use, measured rather than assumed. The style",
        "profile in [`style_profile.py`](../../packages/debate_core/src/debate_core/domain/style_profile.py)",
        "and the heuristic classifier in",
        "[`style_classifier.py`](../../packages/debate_core/src/debate_core/evidence/style_classifier.py)",
        "are grounded in these numbers.",
        "",
        "Produced by `scripts/survey_docx_styles.py`, which reads only style information — `w:t` is",
        "never touched — against files that stay on the machine holding them and never enter this",
        "repository.",
        "",
        "| | |",
        "|---|---|",
        f"| Files surveyed | {total} |",
        f"| Run on | {moment} |",
        f"| Reporting threshold | a style is named only if it appears in {minimum_files} or more files |",
    ]
    if corpus_description:
        lines.append(f"| Corpus | {corpus_description} |")
    lines += [
        "",
        "No file names, schools, team codes, debater names or document text appear below, and none",
        "are collected in the first place. Style ids longer than "
        f"{MAXIMUM_REPORTED_STYLE_ID} characters are elided in the",
        "middle: Word builds a style id by concatenating every name the style has ever had, and the",
        "fragment in the middle is occasionally the first name of whoever created it.",
        "",
        "## Template families",
        "",
        "Each file lands in exactly one template family, decided from its style *references* rather",
        "than its style *definitions*: most debate files define the whole Verbatim style set whether",
        "they use it or not.",
        "",
        "A category name says which corpus a file came from, not who cut the cards in it. Teams",
        "read cards other teams cut and disclosed, so a file in the `team` corpus routinely holds",
        "evidence from elsewhere; the split below is about provenance of the *file*, not the cards.",
        "",
        "`cardmirror` files are Verbatim files that also carry CardMirror's `pmd-heading-` bookmark",
        "ids, so they have been through that editor at least once. `wiki-converted` files define the",
        "Verbatim styles and reference none of them — everything is direct formatting, which is what",
        "the caselist wiki-to-docx conversion produces.",
        "",
        "| Category | Files | " + " | ".join(FAMILY_ORDER) + " |",
        "|---|---|" + "---|" * len(FAMILY_ORDER),
    ]
    for category in sorted(survey.files_by_category):
        counts = survey.families_by_category[category]
        category_total = survey.files_by_category[category]
        cells = [f"{counts[family]} ({_share(counts[family], category_total)})" for family in FAMILY_ORDER]
        lines.append(f"| {category} | {category_total} | " + " | ".join(cells) + " |")
    overall = Counter()
    for counts in survey.families_by_category.values():
        overall.update(counts)
    lines.append(
        "| **all** | **"
        + str(total)
        + "** | "
        + " | ".join(f"**{overall[family]} ({_share(overall[family], total)})**" for family in FAMILY_ORDER)
        + " |"
    )

    lines += [
        "",
        "## Which style ids this report names",
        "",
        "A style id is named below only if it is published vocabulary — Verbatim's and CardMirror's",
        "own ids, Word's built-in ids, or the ids the Google Docs and wiki-to-docx converters emit —",
        "or is one of those with Word's numeric de-duplication suffix on it (`Heading4` →",
        "`Heading411`, `Emphasis` → `Emphasis1`). Every other id is counted and not named, because a",
        "style id a person chose is a place a person's name ends up; the corpus this survey was",
        "first run against contains styles named after individual debaters.",
        "",
        "**Every id is in the full aggregate**, written beside this file on every run at",
        "`docs/data/debate-file-style-survey.full.json` and gitignored. That is the file to read",
        "when looking for an alias worth adding to the style profile; this one is its summary.",
        "",
        "## Paragraph styles referenced in the body",
        "",
        "`files` is how many files reference the style at least once; `references` is the total",
        "number of paragraphs carrying it.",
        "",
    ]
    lines += _style_reference_table(
        survey.paragraph_style_files,
        survey.paragraph_style_occurrences,
        survey.style_names,
        minimum_files,
    )

    lines += [
        "",
        "## Character styles referenced in the body",
        "",
    ]
    lines += _style_reference_table(
        survey.character_style_files,
        survey.character_style_occurrences,
        survey.style_names,
        minimum_files,
    )

    lines += [
        "",
        "## Alias candidates: styles that inherit from a Verbatim style",
        "",
        "A style defined with its own id but `basedOn` a Verbatim style is how template drift shows",
        "up. Two shapes matter, and the profile handles them differently. Word's numeric",
        "de-duplication (`Heading411`, `Emphasis1`) is mechanical, so the profile resolves it by",
        "stripping the suffix. A style somebody named themselves is not mechanical, so the profile",
        "resolves it by following `basedOn` to a style it does know — which is why the count below",
        "matters more than any individual id.",
        "",
        "| Verbatim style inherited from | Distinct ids | Files |",
        "|---|---|---|",
    ]
    verbatim_bases = VERBATIM_PARAGRAPH_STYLE_IDS | VERBATIM_CHARACTER_STYLE_IDS
    inherited_ids: dict[str, set[str]] = defaultdict(set)
    inherited_files: Counter[str] = Counter()
    named_rows: list[tuple[str, str, int]] = []
    for (style_id, based_on), count in survey.based_on_links.most_common():
        base = normalize_style_id(based_on)
        if base not in verbatim_bases or normalize_style_id(style_id) in verbatim_bases:
            continue
        inherited_ids[based_on].add(style_id)
        inherited_files[based_on] += count
        if count >= minimum_files and derived_from_published(style_id, _first_name(survey, style_id)):
            named_rows.append((style_id, based_on, count))
    for based_on, _ in inherited_files.most_common():
        lines.append(f"| `{based_on}` | {len(inherited_ids[based_on])} | {inherited_files[based_on]} |")
    if not inherited_files:
        lines.append("| _(none)_ | — | — |")

    lines += [
        "",
        "Of those, the ones that are Word's numeric de-duplication of a style id we already know:",
        "",
        "| Style id | basedOn | Resolves to | Files |",
        "|---|---|---|---|",
    ]
    for style_id, based_on, count in named_rows:
        resolved = derived_from_published(style_id, _first_name(survey, style_id))
        lines.append(f"| `{elide_style_id(style_id)}` | `{based_on}` | `{resolved}` | {count} |")
    if not named_rows:
        lines.append("| _(none above the reporting threshold)_ | — | — | — |")

    lines += [
        "",
        "## Outline levels",
        "",
        "Outline level is the only structural signal a file with no Verbatim styles carries, and it",
        "is what the heuristic classifier keys on. Level 0 is Heading 1.",
        "",
        "| Outline level | Paragraphs |",
        "|---|---|",
    ]
    for level in sorted(survey.outline_levels):
        lines.append(f"| {level} | {survey.outline_levels[level]} |")
    if not survey.outline_levels:
        lines.append("| _(none)_ | — |")

    lines += [
        "",
        "## Highlight colours",
        "",
        "`w:highlight` values, which the profile lists so the parser and the writer agree on what a",
        "debater's highlighting means.",
        "",
        "| Colour | Runs |",
        "|---|---|",
    ]
    for color, count in survey.highlight_colors.most_common():
        lines.append(f"| `{color}` | {count} |")
    if not survey.highlight_colors:
        lines.append("| _(none)_ | — |")

    lines += [
        "",
        "## Refreshing this report",
        "",
        "```bash",
        "uv run python scripts/survey_docx_styles.py \\",
        "    --input caselist=<newest hsld26 snapshot directory> \\",
        "    --input camp=<camp files directory> \\",
        "    --input team=<team files directory> \\",
        "    --min-files 3 \\",
        '    --corpus-description "<one line naming the corpus>" \\',
        "    --output docs/data/debate-file-style-survey.md \\",
        "    --json <a path outside this repository>",
        "```",
        "",
        "`--input` is repeatable. `CATEGORY=PATH` puts everything under `PATH` in one category; a",
        "bare path takes its categories from its immediate subdirectories, the layout",
        "[`scripts/cardmirror-roundtrip/`](../../scripts/cardmirror-roundtrip/README.md) uses. Point",
        "`caselist` at the newest snapshot only: successive hsld26 snapshots are cumulative, so",
        "surveying all of them counts most files several times.",
        "",
        "The command overwrites this file, and writes the full unredacted aggregate beside it at",
        "`docs/data/debate-file-style-survey.full.json` — always, and gitignored, so it is there to",
        "read and cannot be committed. **Read the aggregate** after a refresh: a style id that has",
        "spread to enough files to matter belongs in the profile's alias list, and the aggregate is",
        "the only place it appears. Read the diff of this file too, because a style id is the one",
        "field here a person could have put a name in.",
        "",
    ]
    return "\n".join(lines)


def survey_to_json(survey: StyleSurvey, minimum_files: int) -> dict[str, object]:
    """The aggregate as JSON, with **nothing** withheld.

    This is the counterpart to :func:`render_report`, and the difference between them is the
    point. The report withholds a style id that a person chose and one that falls below the
    reporting threshold, because it is committed to a public repository. This file is gitignored,
    so it holds every id, every display name, every `basedOn` link and every count — which is what
    makes it the place to look when deciding whether a new alias belongs in the style profile.

    `report_minimum_files` records the threshold the report beside it was rendered at, so the two
    can be compared without guessing.
    """
    return {
        "total_files": survey.total_files,
        "report_minimum_files": minimum_files,
        "files_by_category": dict(survey.files_by_category),
        "families_by_category": {
            category: dict(counts) for category, counts in survey.families_by_category.items()
        },
        "paragraph_style_files": dict(survey.paragraph_style_files),
        "paragraph_style_occurrences": dict(survey.paragraph_style_occurrences),
        "character_style_files": dict(survey.character_style_files),
        "character_style_occurrences": dict(survey.character_style_occurrences),
        "defined_style_files": dict(survey.defined_style_files),
        "style_names": {style_id: dict(names) for style_id, names in survey.style_names.items() if names},
        "based_on_links": {
            f"{style_id}<-{based_on}": count for (style_id, based_on), count in survey.based_on_links.items()
        },
        "outline_levels": {str(level): count for level, count in sorted(survey.outline_levels.items())},
        "highlight_colors": dict(survey.highlight_colors),
        "cardmirror_files": survey.cardmirror_files,
        "unreadable_files": survey.unreadable_files,
    }


# --------------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="survey_docx_styles.py",
        description="Aggregate the Word styles a corpus of debate .docx files uses.",
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        metavar="PATH|CATEGORY=PATH",
        help=(
            "Corpus directory to walk; repeatable. A bare PATH takes its categories from its "
            "immediate subdirectories; CATEGORY=PATH puts everything under PATH in one category."
        ),
    )
    parser.add_argument("--output", type=Path, required=True, help="Markdown report to write.")
    parser.add_argument(
        "--aggregate",
        type=Path,
        default=None,
        help=(
            "Where to write the full unredacted JSON aggregate. Always written; defaults to "
            f"{DEFAULT_AGGREGATE_PATH}, which is gitignored. Any path given here must stay out of "
            "version control: the aggregate names every style id, including team-specific ones."
        ),
    )
    parser.add_argument(
        "--category",
        default="uncategorized",
        help="Category for files sitting directly in the corpus directory.",
    )
    parser.add_argument(
        "--min-files",
        type=int,
        default=DEFAULT_MINIMUM_FILES,
        help=(
            "A style is named in the report only if it appears in at least this many files. "
            "Keeps a style a team named after itself out of a committed document."
        ),
    )
    parser.add_argument(
        "--corpus-description",
        default="",
        help="One line describing the corpus, recorded in the report header.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    if arguments.min_files < 1:
        print("survey_docx_styles: --min-files must be at least 1", file=sys.stderr)
        return 1
    try:
        survey = survey_inputs(arguments.input, arguments.category)
    except SurveyError as error:
        print(f"survey_docx_styles: {error}", file=sys.stderr)
        return 1
    if survey.total_files == 0:
        print("survey_docx_styles: no .docx files found under any --input", file=sys.stderr)
        return 1

    report = render_report(
        survey,
        minimum_files=arguments.min_files,
        corpus_description=arguments.corpus_description,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(report + "\n" if not report.endswith("\n") else report, encoding="utf-8")
    aggregate_path = arguments.aggregate or (REPOSITORY_ROOT / DEFAULT_AGGREGATE_PATH)
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(
        json.dumps(survey_to_json(survey, arguments.min_files), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"surveyed {survey.total_files} files -> {arguments.output}")
    print(f"  full unredacted aggregate -> {aggregate_path}")
    for category in sorted(survey.files_by_category):
        families = survey.families_by_category[category]
        breakdown = ", ".join(f"{family} {families[family]}" for family in FAMILY_ORDER if families[family])
        print(f"  {category}: {survey.files_by_category[category]} ({breakdown})")
    if survey.unreadable_files:
        print(f"  unreadable: {survey.unreadable_files}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
