"""The labels the parser evaluation grades against, and the checks that keep them honest.

`v1-e31-t05-parser-eval` measures the `v1-e31-t03` parser on real team, caselist and camp files.
**None of those files is in this repository**, scrubbed or otherwise: a team file can carry another
program's disclosed cards, and `docs/policies/caselist-data-use.md` prohibitions 1, 9 and 10 keep
the corpus on the operator's machine. What the repository holds is described here:

* a **manifest** (`tests/fixtures/debate_files/eval/manifest.json`) naming each evaluation file by
  **keyed digest**, category, season, format and template family — never by file name, and never by
  a plain SHA-256, which over a public corpus in a public repository is a join key rather than an
  anonymiser (see :mod:`tests.evals.parser.digests`);
* a **sampling plan** (`sampling-plan.json`) saying which paragraphs of each file are labeled;
* one **label file** per evaluation file (`labels/<digest>.jsonl`) saying what each labeled
  paragraph *is*, keyed by its index in the document body and a keyed digest of its text. No
  paragraph text is stored.

A label file is JSON Lines, one record per line, in this order:

1. one `file` record: the file's digest, its total paragraph count, the labeled blocks, the
   sampling plan they came from, the review status and the span sample fraction;
2. one `paragraph` record per **labeled** paragraph: index, text length, text digest, unit, and the
   card it belongs to (or none);
3. one `card` record per labeled card: its id and completeness;
4. zero or more `spans` records, for the sampled labeled paragraphs only.

**Labeling is sampled.** The six-file PR subset is labeled in full, because it gates every pull
request. Every other file is labeled over contiguous blocks covering about a quarter of it —
contiguous because card-boundary exact match needs unbroken runs, and a card straddling a sampling
gap cannot be scored at all.

**Labels are written by a person.** `scripts/prelabel_docx.py` seeds a label file from the parser's
output so the person has something to correct, and marks it `PRELABELED`. The evaluation refuses a
`PRELABELED` file: a pre-label nobody corrected is the parser grading its own homework, which is
the failure this whole evaluation exists to prevent (working agreements §6).

Two layers of validation:

* :func:`validate_label_file` needs nothing but the label file and the plan. It runs in the PR `ci`
  check, where the corpus never is.
* :func:`validate_against_texts` needs the file itself and the digest key, and runs only where both
  are. It fails when the file has changed under its labels.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
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
    "MINIMUM_BLOCK_PARAGRAPHS",
    "PR_SUBSET_SIZE",
    "RARE_UNITS",
    "REPOSITORY_ROOT",
    "SAMPLING_PLAN_PATH",
    "TARGET_SAMPLING_RATE",
    "VERBATIM_FAMILIES",
    "Block",
    "CardLabel",
    "Category",
    "DebateFormat",
    "FileLabelHeader",
    "FileSamplingPlan",
    "LabelFile",
    "LabelStatus",
    "Manifest",
    "ManifestEntry",
    "ParagraphLabel",
    "ReviewerRole",
    "SamplingPlan",
    "SpanLabel",
    "TemplateFamily",
    "coverage_shortfalls",
    "label_path_for",
    "load_label_file",
    "load_label_files",
    "load_manifest",
    "load_sampling_plan",
    "status_counts",
    "validate_against_texts",
    "validate_label_file",
    "write_label_file",
]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVAL_FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "debate_files" / "eval"
MANIFEST_PATH = EVAL_FIXTURE_DIRECTORY / "manifest.json"
SAMPLING_PLAN_PATH = EVAL_FIXTURE_DIRECTORY / "sampling-plan.json"
LABELS_DIRECTORY = EVAL_FIXTURE_DIRECTORY / "labels"

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SEASON = re.compile(r"^20\d\d-\d\d$")

Digest = Annotated[str, Field(pattern=_DIGEST.pattern)]

#: A labeled block: first and last paragraph index, both inclusive.
Block = tuple[int, int]

#: ac1: about a quarter of every file outside the PR subset.
TARGET_SAMPLING_RATE = 0.25

#: A block is never shorter than this, so a card inside one can be scored whole.
MINIMUM_BLOCK_PARAGRAPHS = 20

#: The units the sampling plan weights blocks towards: the sparsest, and the ones the parser is
#: weakest on. An even sample leaves their F1 too noisy to gate on.
RARE_UNITS: frozenset[StructuralUnit] = frozenset(
    {StructuralUnit.POCKET, StructuralUnit.UNDERTAG, StructuralUnit.ANALYTIC}
)


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
    """The template families `scripts/survey_docx_styles.py` places a file in."""

    VERBATIM = "verbatim"
    CARDMIRROR = "cardmirror"
    WIKI_CONVERTED = "wiki-converted"
    OTHER_HEURISTIC = "other-heuristic"


#: Files whose structure comes from Verbatim styles. The rest are read by the heuristic classifier.
VERBATIM_FAMILIES: frozenset[TemplateFamily] = frozenset({TemplateFamily.VERBATIM, TemplateFamily.CARDMIRROR})


class ManifestEntry(_Record):
    """One evaluation file, identified by a keyed digest. No name, school or team code."""

    digest: Digest = Field(description="HMAC-SHA256 of the file's bytes under the evaluation key.")
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
        duplicates = [d for d, count in Counter(e.digest for e in self.entries).items() if count > 1]
        if duplicates:
            raise ValueError(f"manifest lists {len(duplicates)} file(s) twice: {duplicates[0][:12]}…")
        return self

    def entry(self, digest: str) -> ManifestEntry:
        for entry in self.entries:
            if entry.digest == digest:
                return entry
        raise KeyError(digest)

    @property
    def pr_subset(self) -> tuple[ManifestEntry, ...]:
        return tuple(entry for entry in self.entries if entry.pr_subset)


def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


#: The PR subset is "about 6 files" in the spec; exactly six keeps the PR run's cost predictable.
PR_SUBSET_SIZE = 6


def coverage_shortfalls(manifest: Manifest) -> list[str]:
    """What the manifest is missing against Goal criterion ac1. Empty when it is complete."""
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
# The sampling plan
# --------------------------------------------------------------------------------------------


class FileSamplingPlan(_Record):
    """Which paragraphs of one file are labeled."""

    digest: Digest
    paragraphs: int = Field(ge=0, description="How many paragraphs the file has in total.")
    blocks: tuple[Block, ...] = Field(description="Labeled blocks, inclusive, in order, disjoint.")
    full: bool = Field(default=False, description="True for the PR subset: the whole file is labeled.")

    @model_validator(mode="after")
    def _check_blocks(self) -> FileSamplingPlan:
        previous = -1
        for first, last in self.blocks:
            if first <= previous:
                raise ValueError(f"blocks must be disjoint and in order; {first} follows {previous}")
            if last < first:
                raise ValueError(f"block {first}-{last} ends before it starts")
            if last >= self.paragraphs:
                raise ValueError(f"block {first}-{last} runs past the file's {self.paragraphs} paragraphs")
            previous = last
        if self.full and self.paragraphs and self.blocks != ((0, self.paragraphs - 1),):
            raise ValueError("a fully labeled file is one block covering every paragraph")
        return self

    @property
    def labeled_rows(self) -> int:
        return sum(last - first + 1 for first, last in self.blocks)

    @property
    def rate(self) -> float:
        return self.labeled_rows / self.paragraphs if self.paragraphs else 0.0

    def indices(self) -> list[int]:
        return [index for first, last in self.blocks for index in range(first, last + 1)]

    def contains(self, index: int) -> bool:
        return any(first <= index <= last for first, last in self.blocks)


class SamplingPlan(_Record):
    """Which paragraphs of every file are labeled, and how they were chosen.

    Generated once, before any labeling, and committed. `plan_id` is a digest of the plan's own
    content — not of any corpus file — and the baseline records it: metrics from two different
    samples are two measurements, not a regression, so the gate refuses rather than compares when
    the plan has moved.
    """

    plan_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    generated_on: str
    parser_version: str = Field(description="Parser whose pre-labels the rare-unit weighting used.")
    target_rate: float = Field(gt=0.0, le=1.0, default=TARGET_SAMPLING_RATE)
    minimum_block: int = Field(ge=1, default=MINIMUM_BLOCK_PARAGRAPHS)
    rare_units: tuple[StructuralUnit, ...] = Field(default_factory=lambda: tuple(sorted(RARE_UNITS)))
    files: tuple[FileSamplingPlan, ...] = ()

    def of(self, digest: str) -> FileSamplingPlan:
        for plan in self.files:
            if plan.digest == digest:
                return plan
        raise KeyError(digest)

    @property
    def labeled_rows(self) -> int:
        return sum(plan.labeled_rows for plan in self.files)

    @property
    def total_rows(self) -> int:
        return sum(plan.paragraphs for plan in self.files)

    @property
    def rate(self) -> float:
        return self.labeled_rows / self.total_rows if self.total_rows else 0.0


def load_sampling_plan(path: Path = SAMPLING_PLAN_PATH) -> SamplingPlan:
    return SamplingPlan.model_validate_json(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------------
# Label files
# --------------------------------------------------------------------------------------------


class LabelStatus(StrEnum):
    """How far a label file has got from the parser's opinion to a person's."""

    PRELABELED = "PRELABELED"
    """Seeded from parser output and not yet corrected. The evaluation refuses it."""

    CORRECTED = "CORRECTED"
    """A person went through every labeled paragraph and corrected what was wrong."""

    COACH_REVIEWED = "COACH_REVIEWED"
    """Corrected, and then spot-checked end to end by the coach."""


class ReviewerRole(StrEnum):
    """Who corrected or reviewed a label file. A role, never a name."""

    OPERATOR = "operator"
    COACH = "coach"


class FileLabelHeader(_Record):
    record: Literal["file"] = "file"
    digest: Digest = Field(description="Keyed digest of the file these labels describe.")
    paragraph_count: int = Field(ge=0, description="Paragraphs in the whole file, labeled or not.")
    blocks: tuple[Block, ...] = Field(default=(), description="Labeled blocks, from the sampling plan.")
    plan_id: str = Field(default="", description="The sampling plan these blocks came from.")
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

    @property
    def labeled_rows(self) -> int:
        return sum(last - first + 1 for first, last in self.blocks)

    def block_of(self, index: int) -> Block | None:
        for block in self.blocks:
            if block[0] <= index <= block[1]:
                return block
        return None


class ParagraphLabel(_Record):
    record: Literal["paragraph"] = "paragraph"
    index: int = Field(ge=0, description="The paragraph's element_index in the parser's body walk.")
    length: int = Field(ge=0, description="Length of the paragraph's text, in characters.")
    text_digest: Digest = Field(description="Keyed digest of the paragraph's text.")
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
    """One evaluation file's labels, as read from `labels/<digest>.jsonl`."""

    header: FileLabelHeader
    paragraphs: tuple[ParagraphLabel, ...]
    cards: tuple[CardLabel, ...]
    spans: tuple[SpanLabel, ...]

    @property
    def digest(self) -> str:
        return self.header.digest

    @property
    def blocks(self) -> tuple[Block, ...]:
        return self.header.blocks

    def card_ranges(self) -> dict[int, Block]:
        """Each labeled card's first and last paragraph index."""
        ranges: dict[int, Block] = {}
        for paragraph in self.paragraphs:
            if paragraph.card is None:
                continue
            first, last = ranges.get(paragraph.card, (paragraph.index, paragraph.index))
            ranges[paragraph.card] = (min(first, paragraph.index), max(last, paragraph.index))
        return ranges

    def to_jsonl(self) -> str:
        records: list[_Record] = [self.header, *self.paragraphs, *self.cards, *self.spans]
        return "".join(record.model_dump_json() + "\n" for record in records)


def label_path_for(digest: str, directory: Path = LABELS_DIRECTORY) -> Path:
    return directory / f"{digest}.jsonl"


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
    """Every label file in a directory, keyed by the digest it labels."""
    files = {}
    for path in sorted(directory.glob("*.jsonl")):
        label_file = load_label_file(path)
        files[label_file.digest] = label_file
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
    path = label_path_for(label_file.digest, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(label_file.to_jsonl(), encoding="utf-8")
    return path


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
    label_file: LabelFile,
    manifest: Manifest | None = None,
    plan: SamplingPlan | None = None,
    *,
    check_cards: bool = True,
) -> list[str]:
    """Everything that can be wrong with a label file without looking at the file it labels.

    `check_cards=False` skips the rules about what a card is made of, for pre-labels only.
    """
    problems: list[str] = []
    header = label_file.header
    expected = [index for first, last in header.blocks for index in range(first, last + 1)]
    indices = [paragraph.index for paragraph in label_file.paragraphs]
    if indices != expected:
        problems.append(
            f"paragraph records must be exactly the {len(expected)} labeled indices of the blocks, "
            f"in order; got {len(indices)}"
        )
    if header.blocks and header.blocks[-1][1] >= header.paragraph_count:
        problems.append(f"labeled blocks run past the file's {header.paragraph_count} paragraphs")
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
    if check_cards:
        for card, (first, last) in sorted(label_file.card_ranges().items()):
            if header.block_of(first) != header.block_of(last):
                problems.append(
                    f"card {card} straddles a sampling-block edge ({first}-{last}); a card is labeled "
                    "only when the whole of it is inside one block"
                )

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
            manifest.entry(header.digest)
        except KeyError:
            problems.append(f"labels {header.digest[:12]}… are for a file the manifest does not list")
    if plan is not None:
        try:
            file_plan = plan.of(header.digest)
        except KeyError:
            problems.append(f"labels {header.digest[:12]}… are for a file the sampling plan does not cover")
        else:
            if header.plan_id != plan.plan_id:
                problems.append(f"labels were made under plan {header.plan_id!r}, not {plan.plan_id!r}")
            if header.blocks != file_plan.blocks:
                problems.append("labeled blocks do not match the sampling plan's blocks for this file")
            if header.paragraph_count != file_plan.paragraphs:
                problems.append(
                    f"labels say the file has {header.paragraph_count} paragraphs, the plan says "
                    f"{file_plan.paragraphs}"
                )
    return problems


def validate_against_texts(
    label_file: LabelFile,
    file_digest: str,
    paragraph_texts: Sequence[str],
    text_digest_of: Callable[[str], str],
) -> list[str]:
    """Whether the file on disk is still the file these labels describe.

    `paragraph_texts` is every paragraph's text in body order, as the parser read it, and
    `text_digest_of` turns one paragraph's text into its keyed digest. Fails on a different file, a
    different paragraph count, or any labeled paragraph whose text digest has moved — the last
    catches both an edited file and a parser whose paragraph walk changed under the labels.
    """
    if file_digest != label_file.digest:
        return [f"file digests to {file_digest[:12]}…, labels are for {label_file.digest[:12]}…"]
    if len(paragraph_texts) != label_file.header.paragraph_count:
        return [
            f"file has {len(paragraph_texts)} paragraphs, labels have {label_file.header.paragraph_count}"
        ]
    problems: list[str] = []
    for paragraph in label_file.paragraphs:
        text = paragraph_texts[paragraph.index]
        if text_digest_of(text) != paragraph.text_digest or len(text) != paragraph.length:
            problems.append(f"paragraph {paragraph.index}: text changed under its label")
    return problems


def status_counts(label_files: Iterable[LabelFile]) -> Mapping[LabelStatus, int]:
    counts: Counter[LabelStatus] = Counter(label.header.status for label in label_files)
    return {status: counts.get(status, 0) for status in LabelStatus}
