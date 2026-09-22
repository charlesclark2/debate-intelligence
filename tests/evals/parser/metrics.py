"""Scoring the parser against hand-corrected labels.

Everything here is arithmetic over two descriptions of one file: what a person labeled
(:class:`~tests.evals.parser.labels_schema.LabelFile`) and what the parser said
(:class:`Prediction`, built from a :class:`~debate_core.domain.debate_files.ParsedDocument` by
:func:`prediction_from_document`). Nothing reads a `.docx`, so every function can be tested on
invented numbers, and is (`test_metrics.py`).

What is measured, per Goal criterion ac2:

* **Per-unit precision, recall and F1** over paragraphs. A paragraph labeled `TAG` that the parser
  called `ANALYTIC` is a missed tag and a false analytic.
* **Card-boundary exact match**: the share of labeled cards whose first and last paragraph the
  parser got exactly right. Card precision is reported beside it, so a parser that splits one card
  into two is seen twice over.
* **Completeness accuracy**: of the cards whose boundaries matched, how many carry the right
  `FULL` / `ABBREVIATED` / `CITE_ONLY`.
* **Character-level underline and highlight F1**, on the sampled paragraphs only.

Counts are summed before a ratio is taken (micro-averaging), so a group's score is the score of
its paragraphs, not the average of its files' scores — a two-paragraph file does not weigh as much
as a two-hundred-paragraph one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from tests.evals.parser.labels_schema import (
    VERBATIM_FAMILIES,
    LabelFile,
    ManifestEntry,
)

from debate_core.domain.debate_files import CardCompleteness, ParsedDocument
from debate_core.domain.style_profile import RunEmphasis, StructuralUnit

__all__ = [
    "EVALUATED_UNITS",
    "GATE_TOLERANCE",
    "SPAN_KINDS",
    "TARGETS",
    "Counts",
    "FileScore",
    "GroupScore",
    "Prediction",
    "Target",
    "check_against_baseline",
    "evaluate_targets",
    "group_scores",
    "prediction_from_document",
    "render_markdown",
    "report_json",
    "score_file",
]

#: The units ac2 names. OTHER is scored too, but carries no target.
EVALUATED_UNITS: Final = (
    StructuralUnit.POCKET,
    StructuralUnit.HAT,
    StructuralUnit.BLOCK,
    StructuralUnit.TAG,
    StructuralUnit.CITE,
    StructuralUnit.EVIDENCE,
    StructuralUnit.ANALYTIC,
    StructuralUnit.UNDERTAG,
)
SCORED_UNITS: Final = (*EVALUATED_UNITS, StructuralUnit.OTHER)

SPAN_KINDS: Final = ("underline", "highlight")

#: Emphasis that a reader sees as underlined. Verbatim's `Emphasis` style is underlined as well as
#: bold, so emphasised text counts as underlined text; see the labeling guide.
_UNDERLINED: Final = frozenset({RunEmphasis.UNDERLINE, RunEmphasis.EMPHASIS})

#: ac4: the gate fails when a unit F1 drops by more than this below the baseline.
GATE_TOLERANCE: Final = 0.01


# --------------------------------------------------------------------------------------------
# What the parser said, reduced to what the labels can be compared with
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Prediction:
    units: Mapping[int, StructuralUnit]
    """Paragraph index → the unit the parser gave it."""

    cards: Sequence[tuple[int, int, CardCompleteness]]
    """Each parsed card's first and last paragraph index, and its completeness."""

    underline: Mapping[int, Sequence[tuple[int, int]]] = field(default_factory=dict)
    highlight: Mapping[int, Sequence[tuple[int, int]]] = field(default_factory=dict)


def prediction_from_document(document: ParsedDocument) -> Prediction:
    underline: dict[int, list[tuple[int, int]]] = {}
    highlight: dict[int, list[tuple[int, int]]] = {}
    for section in document.sections:
        for span in section.formatting_spans:
            if span.emphasis in _UNDERLINED:
                underline.setdefault(section.element_index, []).append((span.start_offset, span.end_offset))
            elif span.emphasis is RunEmphasis.HIGHLIGHT:
                highlight.setdefault(section.element_index, []).append((span.start_offset, span.end_offset))
    return Prediction(
        units={section.element_index: section.unit for section in document.sections},
        cards=[
            (card.provenance.first_element_index, card.provenance.last_element_index, card.completeness)
            for card in document.cards
        ],
        underline=underline,
        highlight=highlight,
    )


# --------------------------------------------------------------------------------------------
# Counts and ratios
# --------------------------------------------------------------------------------------------


@dataclass
class Counts:
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0

    def __iadd__(self, other: Counts) -> Counts:
        self.true_positive += other.true_positive
        self.false_positive += other.false_positive
        self.false_negative += other.false_negative
        return self

    @property
    def support(self) -> int:
        """How many labeled items of this kind there were."""
        return self.true_positive + self.false_negative

    @property
    def precision(self) -> float | None:
        predicted = self.true_positive + self.false_positive
        return self.true_positive / predicted if predicted else None

    @property
    def recall(self) -> float | None:
        return self.true_positive / self.support if self.support else None

    @property
    def f1(self) -> float | None:
        """None when there is nothing to measure: no labels and no predictions of this kind."""
        denominator = 2 * self.true_positive + self.false_positive + self.false_negative
        return 2 * self.true_positive / denominator if denominator else None

    def as_json(self) -> dict[str, Any]:
        return {
            "tp": self.true_positive,
            "fp": self.false_positive,
            "fn": self.false_negative,
            "support": self.support,
            "precision": _round(self.precision),
            "recall": _round(self.recall),
            "f1": _round(self.f1),
        }


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


@dataclass
class FileScore:
    """Additive counts for one file. Groups are sums of these."""

    units: dict[StructuralUnit, Counts] = field(default_factory=lambda: {u: Counts() for u in SCORED_UNITS})
    labeled_cards: int = 0
    predicted_cards: int = 0
    boundary_matches: int = 0
    completeness_correct: int = 0
    spans: dict[str, Counts] = field(default_factory=lambda: {kind: Counts() for kind in SPAN_KINDS})
    span_paragraphs: int = 0

    def __iadd__(self, other: FileScore) -> FileScore:
        for unit in SCORED_UNITS:
            self.units[unit] += other.units[unit]
        for kind in SPAN_KINDS:
            self.spans[kind] += other.spans[kind]
        self.labeled_cards += other.labeled_cards
        self.predicted_cards += other.predicted_cards
        self.boundary_matches += other.boundary_matches
        self.completeness_correct += other.completeness_correct
        self.span_paragraphs += other.span_paragraphs
        return self

    @property
    def boundary_exact_match(self) -> float | None:
        return self.boundary_matches / self.labeled_cards if self.labeled_cards else None

    @property
    def card_precision(self) -> float | None:
        return self.boundary_matches / self.predicted_cards if self.predicted_cards else None

    @property
    def completeness_accuracy(self) -> float | None:
        return self.completeness_correct / self.boundary_matches if self.boundary_matches else None

    @property
    def span_f1(self) -> float | None:
        combined = Counts()
        for kind in SPAN_KINDS:
            combined += self.spans[kind]
        return combined.f1

    def as_json(self) -> dict[str, Any]:
        return {
            "units": {unit.value: self.units[unit].as_json() for unit in SCORED_UNITS},
            "cards": {
                "labeled": self.labeled_cards,
                "predicted": self.predicted_cards,
                "boundary_matches": self.boundary_matches,
                "boundary_exact_match": _round(self.boundary_exact_match),
                "card_precision": _round(self.card_precision),
                "completeness_correct": self.completeness_correct,
                "completeness_accuracy": _round(self.completeness_accuracy),
            },
            "spans": {
                "paragraphs": self.span_paragraphs,
                **{kind: self.spans[kind].as_json() for kind in SPAN_KINDS},
                "combined_f1": _round(self.span_f1),
            },
        }


def _characters(ranges: Iterable[tuple[int, int]]) -> set[int]:
    return {offset for start, end in ranges for offset in range(start, end)}


def score_file(labels: LabelFile, prediction: Prediction) -> FileScore:
    """Compare one file's labels with what the parser said about it."""
    score = FileScore()

    for paragraph in labels.paragraphs:
        predicted = prediction.units.get(paragraph.index)
        if predicted == paragraph.unit:
            score.units[paragraph.unit].true_positive += 1
            continue
        score.units[paragraph.unit].false_negative += 1
        if predicted is not None:
            score.units[predicted].false_positive += 1

    labeled_ranges = labels.card_ranges()
    completeness = {card.card: card.completeness for card in labels.cards}
    predicted_by_range = {(first, last): kind for first, last, kind in prediction.cards}
    score.labeled_cards = len(labeled_ranges)
    score.predicted_cards = len(prediction.cards)
    for card, card_range in labeled_ranges.items():
        predicted_completeness = predicted_by_range.get(card_range)
        if predicted_completeness is None:
            continue
        score.boundary_matches += 1
        if predicted_completeness is completeness.get(card):
            score.completeness_correct += 1

    for span in labels.spans:
        score.span_paragraphs += 1
        for kind, labeled, predicted in (
            ("underline", span.underline, prediction.underline.get(span.index, ())),
            ("highlight", span.highlight, prediction.highlight.get(span.index, ())),
        ):
            expected, got = _characters(labeled), _characters(predicted)
            score.spans[kind] += Counts(
                true_positive=len(expected & got),
                false_positive=len(got - expected),
                false_negative=len(expected - got),
            )
    return score


# --------------------------------------------------------------------------------------------
# Groups
# --------------------------------------------------------------------------------------------


@dataclass
class GroupScore:
    name: str
    files: int
    score: FileScore

    def as_json(self) -> dict[str, Any]:
        return {"files": self.files, **self.score.as_json()}


VERBATIM_GROUP: Final = "template:verbatim"
NON_VERBATIM_GROUP: Final = "template:non-verbatim"


def _groups_of(entry: ManifestEntry) -> list[str]:
    template = VERBATIM_GROUP if entry.template_family in VERBATIM_FAMILIES else NON_VERBATIM_GROUP
    return [
        "overall",
        template,
        f"source:{entry.category.value}",
        f"family:{entry.template_family.value}",
        f"format:{entry.debate_format.value}",
    ]


def group_scores(scored: Iterable[tuple[ManifestEntry, FileScore]]) -> dict[str, GroupScore]:
    """Sum file scores into the breakdowns ac2 asks for: source, template family and format.

    `template:verbatim` and `template:non-verbatim` are the two groups ac3's targets are stated on.
    """
    groups: dict[str, GroupScore] = {}
    for entry, score in scored:
        for name in _groups_of(entry):
            group = groups.setdefault(name, GroupScore(name=name, files=0, score=FileScore()))
            group.files += 1
            group.score += score
    return dict(sorted(groups.items(), key=lambda item: (item[0] != "overall", item[0])))


# --------------------------------------------------------------------------------------------
# Targets (ac3)
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    group: str
    metric: str
    """A unit name for a unit F1, or `span` for combined underline/highlight F1."""
    threshold: float

    def measured(self, groups: Mapping[str, GroupScore]) -> float | None:
        group = groups.get(self.group)
        if group is None:
            return None
        if self.metric == "span":
            return group.score.span_f1
        return group.score.units[StructuralUnit(self.metric)].f1


def _targets() -> tuple[Target, ...]:
    targets: list[Target] = []
    for unit, threshold in (
        ("TAG", 0.97), ("CITE", 0.97), ("EVIDENCE", 0.97),
        ("POCKET", 0.95), ("HAT", 0.95), ("BLOCK", 0.95),
        ("ANALYTIC", 0.85),
    ):  # fmt: skip
        targets.append(Target(VERBATIM_GROUP, unit, threshold))
    targets.append(Target(VERBATIM_GROUP, "span", 0.99))
    for unit in ("TAG", "CITE", "EVIDENCE"):
        targets.append(Target(NON_VERBATIM_GROUP, unit, 0.90))
    return tuple(targets)


#: Goal criterion ac3, as written in the spec.
TARGETS: Final = _targets()


def evaluate_targets(groups: Mapping[str, GroupScore]) -> list[dict[str, Any]]:
    results = []
    for target in TARGETS:
        value = target.measured(groups)
        status = "NOT MEASURED" if value is None else ("MET" if value >= target.threshold else "MISSED")
        results.append(
            {
                "group": target.group,
                "metric": target.metric,
                "threshold": target.threshold,
                "measured": _round(value),
                "status": status,
            }
        )
    return results


# --------------------------------------------------------------------------------------------
# The regression gate (ac4)
# --------------------------------------------------------------------------------------------

#: The groups whose unit F1 the gate holds. Overall alone would let a regression on the
#: non-Verbatim minority hide inside a Verbatim-dominated average.
GATED_GROUPS: Final = ("overall", VERBATIM_GROUP, NON_VERBATIM_GROUP)


def baseline_scores(groups: Mapping[str, GroupScore]) -> dict[str, dict[str, float]]:
    """The unit F1 values a baseline records, for the gated groups."""
    recorded: dict[str, dict[str, float]] = {}
    for name in GATED_GROUPS:
        group = groups.get(name)
        if group is None:
            continue
        recorded[name] = {
            unit.value: value
            for unit in EVALUATED_UNITS
            if (value := _round(group.score.units[unit].f1)) is not None
        }
    return recorded


def check_against_baseline(
    groups: Mapping[str, GroupScore],
    baseline: Mapping[str, Any],
    *,
    tier: str,
    parser_version: str,
) -> tuple[list[str], list[str]]:
    """Regressions against the committed baseline for one tier, and notes that are not failures.

    Returns `(failures, notes)`. A tier with no established baseline is a failure: a gate that
    passes because there is nothing to compare against is not a gate.
    """
    tier_baseline = (baseline.get("tiers") or {}).get(tier)
    if not tier_baseline:
        return (
            [
                f"no baseline is established for the {tier} tier; run scripts/run_parser_eval.py "
                "--write-baseline and commit it with a coach-reviewed report"
            ],
            [],
        )
    notes: list[str] = []
    if baseline.get("parser_version") != parser_version:
        notes.append(
            f"the baseline was recorded for parser {baseline.get('parser_version')}; "
            f"this is {parser_version}. "
            "Regressions are still checked against it; refresh it with a coach-reviewed report."
        )
    failures: list[str] = []
    current = baseline_scores(groups)
    for group_name, units in tier_baseline.items():
        for unit, recorded in units.items():
            measured = current.get(group_name, {}).get(unit)
            if measured is None:
                failures.append(f"{group_name} {unit}: baseline {recorded:.4f}, now not measurable")
            elif measured < recorded - GATE_TOLERANCE:
                failures.append(
                    f"{group_name} {unit}: F1 {measured:.4f} is more than {GATE_TOLERANCE} below "
                    f"the baseline {recorded:.4f}"
                )
    return failures, notes


# --------------------------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------------------------


def report_json(
    *,
    tier: str,
    parser_version: str,
    profile_version: str,
    groups: Mapping[str, GroupScore],
    per_file: Mapping[str, FileScore],
    gate_failures: Sequence[str],
    gate_notes: Sequence[str],
    label_status: Mapping[str, int],
) -> dict[str, Any]:
    """The machine-readable report. Keyed by SHA-256; no file name, school or text appears."""
    return {
        "tier": tier,
        "parser_version": parser_version,
        "profile_version": profile_version,
        "files": len(per_file),
        "label_status": dict(label_status),
        "groups": {name: group.as_json() for name, group in groups.items()},
        "targets": evaluate_targets(groups),
        "gate": {"passed": not gate_failures, "failures": list(gate_failures), "notes": list(gate_notes)},
        "per_file": {sha: score.as_json() for sha, score in sorted(per_file.items())},
    }


def _cell(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def render_markdown(report: Mapping[str, Any]) -> str:
    """A human-readable summary of :func:`report_json`. Aggregates only; no per-file rows."""
    lines = [
        f"# Parser evaluation — {report['tier']} tier",
        "",
        "| | |",
        "|---|---|",
        f"| Parser version | `{report['parser_version']}` |",
        f"| Profile version | `{report['profile_version']}` |",
        f"| Files | {report['files']} |",
        "| Label status | "
        + ", ".join(f"{status} {count}" for status, count in report["label_status"].items())
        + " |",
        f"| Gate | {'PASSED' if report['gate']['passed'] else 'FAILED'} |",
        "",
        "Scores are micro-averaged: counts are summed over every paragraph in a group before a ratio is",
        "taken. `—` means nothing to measure (no labels and no predictions of that kind).",
        "",
        "## Targets",
        "",
        "| Group | Metric | Target | Measured | Status |",
        "|---|---|---|---|---|",
    ]
    for target in report["targets"]:
        metric = "span F1" if target["metric"] == "span" else f"{target['metric']} F1"
        lines.append(
            f"| {target['group']} | {metric} | {target['threshold']:.2f} | {_cell(target['measured'])} | "
            f"{target['status']} |"
        )
    if report["gate"]["failures"] or report["gate"]["notes"]:
        lines += ["", "## Gate", ""]
        lines += [f"- FAIL: {failure}" for failure in report["gate"]["failures"]]
        lines += [f"- Note: {note}" for note in report["gate"]["notes"]]

    groups: Mapping[str, Any] = report["groups"]
    unit_names = [unit.value for unit in SCORED_UNITS]
    lines += ["", "## Unit F1 by group", "", "| Group | Files | " + " | ".join(unit_names) + " |"]
    lines.append("|---|---|" + "---|" * len(unit_names))
    for name, group in groups.items():
        cells = [_cell(group["units"][unit]["f1"]) for unit in unit_names]
        lines.append(f"| {name} | {group['files']} | " + " | ".join(cells) + " |")

    lines += ["", "## Precision and recall, overall", "", "| Unit | Support | Precision | Recall | F1 |"]
    lines.append("|---|---|---|---|---|")
    overall = groups.get("overall")
    if overall is not None:
        for unit in unit_names:
            counts = overall["units"][unit]
            lines.append(
                f"| {unit} | {counts['support']} | {_cell(counts['precision'])} | "
                f"{_cell(counts['recall'])} | {_cell(counts['f1'])} |"
            )

    lines += [
        "",
        "## Cards and spans by group",
        "",
        "| Group | Labeled cards | Boundary exact match | Card precision | Completeness accuracy "
        "| Span paragraphs | Underline F1 | Highlight F1 | Span F1 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, group in groups.items():
        cards, spans = group["cards"], group["spans"]
        lines.append(
            f"| {name} | {cards['labeled']} | {_cell(cards['boundary_exact_match'])} | "
            f"{_cell(cards['card_precision'])} | {_cell(cards['completeness_accuracy'])} | "
            f"{spans['paragraphs']} | {_cell(spans['underline']['f1'])} | "
            f"{_cell(spans['highlight']['f1'])} | "
            f"{_cell(spans['combined_f1'])} |"
        )
    return "\n".join(lines) + "\n"
