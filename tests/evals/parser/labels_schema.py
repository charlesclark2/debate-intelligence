"""The labels the parser evaluation grades against, and the checks that keep them honest.

`v1-e31-t05-parser-eval` measures the `v1-e31-t03` parser on real team, caselist and camp files.
**None of those files is in this repository**, scrubbed or otherwise: a team file can carry another
program's disclosed cards, and `docs/policies/caselist-data-use.md` prohibitions 1, 9 and 10 keep
the corpus on the operator's machine. What the repository holds is described here:

* a **manifest** (`tests/fixtures/debate_files/eval/manifest.json`) naming each evaluation file by
  SHA-256, category, season, format and template family — never by file name, because a caselist
  file name is `<School>/<TeamCode>/<...>`;
* one **label file** per evaluation file (`labels/<sha256>.jsonl`) saying what each paragraph *is*,
  keyed by the paragraph's index in the document body and the SHA-256 of its text. No paragraph
  text is stored. The hash is what lets a label be checked against the file it describes, on the
  machine that holds the file, without the text leaving it.

A label file is JSON Lines, one record per line, in this order:

1. one `file` record: the file's SHA-256, paragraph count, review status and span sample fraction;
2. one `paragraph` record per paragraph: index, text length, text SHA-256, unit, and the card the
   paragraph belongs to (or none);
3. one `card` record per labeled card: its id and completeness;
4. zero or more `spans` records, for the sampled paragraphs only: underline and highlight as
   half-open character ranges into the paragraph's text.

**Labels are written by a person.** `scripts/prelabel_docx.py` seeds a label file from the
parser's output so the person has something to correct, and marks it `PRELABELED`. The evaluation
refuses a `PRELABELED` file: a pre-label nobody corrected is the parser grading its own homework,
which is the failure this whole evaluation exists to prevent (working agreements §6). A file
becomes `CORRECTED` only by importing a worksheet in which every row was marked checked, and
`COACH_REVIEWED` when the coach has spot-checked it end to end.

Two layers of validation:

* :func:`validate_label_file` needs nothing but the label file. It runs in the PR `ci` check,
  where the corpus never is.
* :func:`validate_against_texts` needs the file itself and runs only where the file is. It fails
  when the file has changed under its labels — a different SHA-256, a different paragraph count,
  or a paragraph whose text no longer hashes to what was labeled.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.style_profile import StructuralUnit

__all__ = [
    "CARD_UNITS",
    "EVAL_FIXTURE_DIRECTORY",
    "LABELS_DIRECTORY",
    "MANIFEST_PATH",
    "PR_SUBSET_SIZE",
    "REPOSITORY_ROOT",
    "VERBATIM_FAMILIES",
    "CardLabel",
    "Category",
    "DebateFormat",
    "FileLabelHeader",
    "LabelFile",
    "LabelStatus",
    "Manifest",
    "ManifestEntry",
    "ParagraphLabel",
    "ReviewerRole",
    "SpanLabel",
    "TemplateFamily",
    "coverage_shortfalls",
    "label_path_for",
    "load_label_file",
    "load_label_files",
    "load_manifest",
    "status_counts",
    "text_sha256",
    "validate_against_texts",
    "validate_label_file",
    "write_label_file",
]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVAL_FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "debate_files" / "eval"
MANIFEST_PATH = EVAL_FIXTURE_DIRECTORY / "manifest.json"
LABELS_DIRECTORY = EVAL_FIXTURE_DIRECTORY / "labels"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEASON = re.compile(r"^20\d\d-\d\d$")

Sha256 = Annotated[str, Field(pattern=_SHA256.pattern)]


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------------------------


class Category(StrEnum):
    """Which corpus a file came from. Says nothing about who cut the cards inside it."""

    TEAM = "team"
    CASELIST = "caselist"
    CAMP = "camp"


class DebateFormat(StrEnum):
    """The event a file was written for."""

    LD = "LD"
    PF = "PF"
    POLICY = "Policy"


class TemplateFamily(StrEnum):
    """The template families `scripts/survey_docx_styles.py` places a file in.

    `unreadable` is not here: a file the survey cannot open cannot be labeled, and belongs in the
    corpus health run's failure counts instead.
    """

    VERBATIM = "verbatim"
    CARDMIRROR = "cardmirror"
    WIKI_CONVERTED = "wiki-converted"
    OTHER_HEURISTIC = "other-heuristic"


#: Files whose structure comes from Verbatim styles. The rest are read by the heuristic classifier.
VERBATIM_FAMILIES: frozenset[TemplateFamily] = frozenset({TemplateFamily.VERBATIM, TemplateFamily.CARDMIRROR})


class ManifestEntry(_Record):
    """One evaluation file, identified by its bytes. No name, school or team code."""

    sha256: Sha256
    category: Category
    season: str = Field(pattern=_SEASON.pattern, description="Season, e.g. `2026-27`.")
    debate_format: DebateFormat
    template_family: TemplateFamily
    pr_subset: bool = Field(default=False, description="Part of the small subset run on every PR.")

    @property
    def is_verbatim(self) -> bool:
        return self.template_family in VERBATIM_FAMILIES


class Manifest(_Record):
    """Every evaluation file, and nothing that names one."""

    description: str = ""
    entries: tuple[ManifestEntry, ...] = ()

    @model_validator(mode="after")
    def _unique(self) -> Manifest:
        duplicates = [sha for sha, count in Counter(e.sha256 for e in self.entries).items() if count > 1]
        if duplicates:
            raise ValueError(f"manifest lists {len(duplicates)} file(s) twice: {duplicates[0][:12]}…")
        return self

    def entry(self, sha256: str) -> ManifestEntry:
        for entry in self.entries:
            if entry.sha256 == sha256:
                return entry
        raise KeyError(sha256)

    @property
    def pr_subset(self) -> tuple[ManifestEntry, ...]:
        return tuple(entry for entry in self.entries if entry.pr_subset)


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


#: The PR subset is "about 6 files" in the spec; exactly six keeps the PR run's cost predictable.
PR_SUBSET_SIZE = 6


def coverage_shortfalls(manifest: Manifest) -> list[str]:
    """What the manifest is missing against Goal criterion ac1. Empty when it is complete.

    ac1: at least 30 files; at least 12 team files covering all three formats and all three seasons,
    at least 3 of them not built on the Verbatim template; at least 12 caselist files, at least 4
    non-Verbatim and 2 wiki-converted; at least 6 camp files. The PR subset is six files and
    reaches all three categories.
    """
    shortfalls: list[str] = []
    entries = manifest.entries

    def of(category: Category) -> list[ManifestEntry]:
        return [entry for entry in entries if entry.category is category]

    def require(condition: bool, message: str) -> None:
        if not condition:
            shortfalls.append(message)

    team, caselist, camp = of(Category.TEAM), of(Category.CASELIST), of(Category.CAMP)
    require(len(entries) >= 30, f"at least 30 files are labeled; the manifest has {len(entries)}")
    require(len(team) >= 12, f"at least 12 team files; the manifest has {len(team)}")
    team_formats = {entry.debate_format for entry in team}
    require(
        team_formats == set(DebateFormat),
        f"team files cover LD, PF and Policy; missing {sorted(set(DebateFormat) - team_formats)}",
    )
    team_seasons = {entry.season for entry in team}
    for season in ("2024-25", "2025-26", "2026-27"):
        require(season in team_seasons, f"team files cover the {season} season")
    team_non_verbatim = sum(1 for entry in team if not entry.is_verbatim)
    require(
        team_non_verbatim >= 3, f"at least 3 team files not on the Verbatim template; {team_non_verbatim}"
    )
    require(len(caselist) >= 12, f"at least 12 caselist files; the manifest has {len(caselist)}")
    caselist_heuristic = sum(1 for e in caselist if e.template_family is TemplateFamily.OTHER_HEURISTIC)
    require(caselist_heuristic >= 4, f"at least 4 non-Verbatim caselist files; {caselist_heuristic}")
    caselist_wiki = sum(1 for e in caselist if e.template_family is TemplateFamily.WIKI_CONVERTED)
    require(caselist_wiki >= 2, f"at least 2 wiki-converted caselist files; {caselist_wiki}")
    require(len(camp) >= 6, f"at least 6 camp files; the manifest has {len(camp)}")
    subset = manifest.pr_subset
    require(len(subset) == PR_SUBSET_SIZE, f"the PR subset is {PR_SUBSET_SIZE} files; it has {len(subset)}")
    subset_categories = {entry.category for entry in subset}
    require(
        subset_categories == set(Category),
        f"the PR subset reaches every category; missing {sorted(set(Category) - subset_categories)}",
    )
    return shortfalls


# --------------------------------------------------------------------------------------------
# Label files
# --------------------------------------------------------------------------------------------


class LabelStatus(StrEnum):
    """How far a label file has got from the parser's opinion to a person's."""

    PRELABELED = "PRELABELED"
    """Seeded from parser output and not yet corrected. The evaluation refuses it."""

    CORRECTED = "CORRECTED"
    """A person went through every paragraph against the file and corrected what was wrong."""

    COACH_REVIEWED = "COACH_REVIEWED"
    """Corrected, and then spot-checked end to end by the coach."""


class ReviewerRole(StrEnum):
    """Who corrected or reviewed a label file. A role, never a name."""

    OPERATOR = "operator"
    COACH = "coach"


class FileLabelHeader(_Record):
    record: Literal["file"] = "file"
    sha256: Sha256
    paragraph_count: int = Field(ge=0)
    status: LabelStatus
    prelabel_parser_version: str = Field(min_length=1, description="Parser that seeded the pre-labels.")
    corrected_by: ReviewerRole | None = None
    reviewed_by: ReviewerRole | None = None
    rows_changed_from_prelabel: int | None = Field(
        default=None,
        ge=0,
        description="How many paragraph rows the correction changed. Recorded, not judged.",
    )
    span_sample_fraction: float = Field(default=0.2, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _status_is_backed(self) -> FileLabelHeader:
        if self.status is LabelStatus.PRELABELED and (self.corrected_by or self.reviewed_by):
            raise ValueError("a PRELABELED file has not been corrected or reviewed by anybody")
        if self.status is not LabelStatus.PRELABELED and self.corrected_by is None:
            raise ValueError(f"a {self.status} file must say which role corrected it")
        if self.status is LabelStatus.COACH_REVIEWED and self.reviewed_by is not ReviewerRole.COACH:
            raise ValueError("a COACH_REVIEWED file must be reviewed_by the coach")
        if self.status is not LabelStatus.COACH_REVIEWED and self.reviewed_by is not None:
            raise ValueError("reviewed_by is set only on a COACH_REVIEWED file")
        return self


class ParagraphLabel(_Record):
    record: Literal["paragraph"] = "paragraph"
    index: int = Field(ge=0, description="The paragraph's element_index in the parser's body walk.")
    length: int = Field(ge=0, description="Length of the paragraph's text, in characters.")
    text_sha256: Sha256
    unit: StructuralUnit
    card: int | None = Field(default=None, ge=0, description="The card this paragraph belongs to.")


class CardLabel(_Record):
    record: Literal["card"] = "card"
    card: int = Field(ge=0)
    completeness: CardCompleteness


class SpanLabel(_Record):
    """Underline and highlight on one sampled paragraph, as half-open ranges into its text.

    Underline means underlined however it was encoded — a character style, a direct `w:u`, or both,
    which CardMirror writes and which is still one underline. Highlight ignores the colour.
    """

    record: Literal["spans"] = "spans"
    index: int = Field(ge=0)
    underline: tuple[tuple[int, int], ...] = ()
    highlight: tuple[tuple[int, int], ...] = ()


_AnyRecord = Annotated[
    FileLabelHeader | ParagraphLabel | CardLabel | SpanLabel, Field(discriminator="record")
]
_RECORD_ADAPTER: TypeAdapter[FileLabelHeader | ParagraphLabel | CardLabel | SpanLabel] = TypeAdapter(
    _AnyRecord
)

#: Units a card is built from. Headings and analytics are never inside a card.
CARD_UNITS: frozenset[StructuralUnit] = frozenset(
    {StructuralUnit.TAG, StructuralUnit.UNDERTAG, StructuralUnit.CITE, StructuralUnit.EVIDENCE}
)


@dataclass(frozen=True)
class LabelFile:
    """One evaluation file's labels, as read from `labels/<sha256>.jsonl`."""

    header: FileLabelHeader
    paragraphs: tuple[ParagraphLabel, ...]
    cards: tuple[CardLabel, ...]
    spans: tuple[SpanLabel, ...]

    @property
    def sha256(self) -> str:
        return self.header.sha256

    def card_ranges(self) -> dict[int, tuple[int, int]]:
        """Each labeled card's first and last paragraph index."""
        ranges: dict[int, tuple[int, int]] = {}
        for paragraph in self.paragraphs:
            if paragraph.card is None:
                continue
            first, last = ranges.get(paragraph.card, (paragraph.index, paragraph.index))
            ranges[paragraph.card] = (min(first, paragraph.index), max(last, paragraph.index))
        return ranges

    def to_jsonl(self) -> str:
        records: list[_Record] = [self.header, *self.paragraphs, *self.cards, *self.spans]
        return "".join(record.model_dump_json() + "\n" for record in records)


def label_path_for(sha256: str, directory: Path = LABELS_DIRECTORY) -> Path:
    return directory / f"{sha256}.jsonl"


def load_label_file(path: Path) -> LabelFile:
    """Read a label file. Structural problems raise; use :func:`validate_label_file` for the rest."""
    header: FileLabelHeader | None = None
    paragraphs: list[ParagraphLabel] = []
    cards: list[CardLabel] = []
    spans: list[SpanLabel] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = _RECORD_ADAPTER.validate_python(json.loads(line))
        if isinstance(record, FileLabelHeader):
            if header is not None or line_number != 1:
                raise ValueError(f"{path.name}:{line_number}: the file record comes first, and once")
            header = record
        elif isinstance(record, ParagraphLabel):
            paragraphs.append(record)
        elif isinstance(record, CardLabel):
            cards.append(record)
        else:
            spans.append(record)
    if header is None:
        raise ValueError(f"{path.name}: no file record")
    return LabelFile(header=header, paragraphs=tuple(paragraphs), cards=tuple(cards), spans=tuple(spans))


def load_label_files(directory: Path = LABELS_DIRECTORY) -> dict[str, LabelFile]:
    """Every label file in a directory, keyed by the SHA-256 it labels."""
    files = {}
    for path in sorted(directory.glob("*.jsonl")):
        label_file = load_label_file(path)
        files[label_file.sha256] = label_file
    return files


def write_label_file(
    label_file: LabelFile, directory: Path = LABELS_DIRECTORY, *, check_cards: bool = True
) -> Path:
    """Write a label file. Pre-labels may skip the card rules; nothing else may."""
    if check_cards is False and label_file.header.status is not LabelStatus.PRELABELED:
        raise ValueError("only a PRELABELED file may be written without checking its cards")
    problems = validate_label_file(label_file, check_cards=check_cards)
    if problems:
        raise ValueError("refusing to write an invalid label file:\n  " + "\n  ".join(problems))
    path = label_path_for(label_file.sha256, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(label_file.to_jsonl(), encoding="utf-8")
    return path


def text_sha256(text: str) -> str:
    """The hash a paragraph label carries: SHA-256 of the paragraph's text, UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_ranges(
    name: str, index: int, ranges: Sequence[tuple[int, int]], length: int, problems: list[str]
) -> None:
    previous_end = -1
    for start, end in ranges:
        if not 0 <= start < end <= length:
            problems.append(
                f"paragraph {index}: {name} span {start}-{end} is outside its {length} characters"
            )
        if start < previous_end:
            problems.append(f"paragraph {index}: {name} spans overlap or are out of order at {start}")
        previous_end = max(previous_end, end)


def validate_label_file(
    label_file: LabelFile, manifest: Manifest | None = None, *, check_cards: bool = True
) -> list[str]:
    """Everything that can be wrong with a label file without looking at the file it labels.

    `check_cards=False` skips the rules about what a card is made of, for pre-labels only.
    """
    problems: list[str] = []
    header = label_file.header
    indices = [paragraph.index for paragraph in label_file.paragraphs]
    if indices != list(range(header.paragraph_count)):
        problems.append(
            f"paragraph records must be indices 0..{header.paragraph_count - 1} in order, once each; "
            f"got {len(indices)} record(s)"
        )
    by_index = {paragraph.index: paragraph for paragraph in label_file.paragraphs}

    card_ids = [card.card for card in label_file.cards]
    duplicate_cards = [card for card, count in Counter(card_ids).items() if count > 1]
    if duplicate_cards:
        problems.append(f"card record(s) repeated: {sorted(duplicate_cards)}")
    completeness = {card.card: card.completeness for card in label_file.cards}
    units_by_card: dict[int, list[StructuralUnit]] = {}
    for paragraph in label_file.paragraphs:
        if paragraph.card is None:
            continue
        if check_cards and paragraph.unit not in CARD_UNITS:
            problems.append(f"paragraph {paragraph.index}: a {paragraph.unit} is never part of a card")
        units_by_card.setdefault(paragraph.card, []).append(paragraph.unit)
    for card, units in sorted(units_by_card.items()) if check_cards else ():
        if card not in completeness:
            problems.append(f"card {card} has paragraphs but no card record")
            continue
        if StructuralUnit.CITE not in units:
            problems.append(f"card {card} has no CITE paragraph")
        has_body = StructuralUnit.EVIDENCE in units
        if completeness[card] is CardCompleteness.CITE_ONLY and has_body:
            problems.append(f"card {card} is CITE_ONLY but has EVIDENCE paragraphs")
        if completeness[card] is not CardCompleteness.CITE_ONLY and not has_body:
            problems.append(f"card {card} is {completeness[card]} but has no EVIDENCE paragraph")
    for card in completeness:
        if card not in units_by_card:
            problems.append(f"card {card} has a card record but no paragraphs")

    span_indices = [span.index for span in label_file.spans]
    if len(span_indices) != len(set(span_indices)):
        problems.append("a paragraph has more than one spans record")
    for span in label_file.spans:
        paragraph = by_index.get(span.index)
        if paragraph is None:
            problems.append(f"spans record for paragraph {span.index}, which is not labeled")
            continue
        _check_ranges("underline", span.index, span.underline, paragraph.length, problems)
        _check_ranges("highlight", span.index, span.highlight, paragraph.length, problems)

    if manifest is not None:
        try:
            manifest.entry(header.sha256)
        except KeyError:
            problems.append(f"labels {header.sha256[:12]}… are for a file the manifest does not list")
    return problems


def validate_against_texts(
    label_file: LabelFile, file_sha256: str, paragraph_texts: Sequence[str]
) -> list[str]:
    """Whether the file on disk is still the file these labels describe.

    `paragraph_texts` is every paragraph's text in body order, as the parser read it. Fails on a
    different file, a different paragraph count, or any paragraph whose text hash has moved — the
    last catches both an edited file and a parser whose paragraph walk changed under the labels.
    """
    if file_sha256 != label_file.sha256:
        return [f"file hashes to {file_sha256[:12]}…, labels are for {label_file.sha256[:12]}…"]
    problems: list[str] = []
    if len(paragraph_texts) != label_file.header.paragraph_count:
        problems.append(
            f"file has {len(paragraph_texts)} paragraphs, labels have {label_file.header.paragraph_count}"
        )
    for paragraph, text in zip(label_file.paragraphs, paragraph_texts, strict=False):
        if text_sha256(text) != paragraph.text_sha256 or len(text) != paragraph.length:
            problems.append(f"paragraph {paragraph.index}: text changed under its label")
    return problems


def status_counts(label_files: Iterable[LabelFile]) -> Mapping[LabelStatus, int]:
    counts: Counter[LabelStatus] = Counter(label.header.status for label in label_files)
    return {status: counts.get(status, 0) for status in LabelStatus}
