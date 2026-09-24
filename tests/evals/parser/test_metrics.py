"""The evaluation's arithmetic, on invented labels and predictions with the answers worked by hand.

Every expected number below is computed in the comment beside it, not taken from the code.
"""

from __future__ import annotations

import pytest
from tests.evals.parser.corpus import parse_evaluation_file
from tests.evals.parser.labels_schema import (
    CardLabel,
    Category,
    DebateFormat,
    FileLabelHeader,
    LabelFile,
    LabelStatus,
    ManifestEntry,
    ParagraphLabel,
    ReviewerRole,
    SpanLabel,
    TemplateFamily,
)
from tests.evals.parser.metrics import (
    TARGETS,
    Counts,
    Prediction,
    check_against_baseline,
    evaluate_targets,
    group_scores,
    prediction_from_document,
    render_markdown,
    report_json,
    score_file,
)
from tests.evals.parser.synthetic import build_synthetic_file

from debate_core.domain.debate_files import CardCompleteness
from debate_core.domain.style_profile import StructuralUnit
from debate_core.integrations.docx_parser import DebateDocxParser

U = StructuralUnit
SHA = "d" * 64


def _labels(
    units: list[tuple[StructuralUnit, int | None]], lengths: dict[int, int] | None = None, **kw
) -> LabelFile:  # type: ignore[no-untyped-def]
    """Labels over a whole invented file, unless `blocks` says otherwise."""
    lengths = lengths or {}
    blocks = kw.get("blocks", ((0, len(units) - 1),))
    indices = [i for first, last in blocks for i in range(first, last + 1)]
    return LabelFile(
        header=FileLabelHeader(
            digest=SHA,
            blocks=blocks,
            paragraph_count=len(units),
            status=LabelStatus.CORRECTED,
            prelabel_parser_version="p",
            corrected_by=ReviewerRole.OPERATOR,
        ),  # fmt: skip
        paragraphs=tuple(
            ParagraphLabel(
                index=i, length=lengths.get(i, 0), text_digest=SHA, unit=units[i][0], card=units[i][1]
            )
            for i in indices
        ),
        cards=kw.get("cards", ()),
        spans=kw.get("spans", ()),
    )


#: Six paragraphs: a block, one full card (1-3), a blank, and an analytic.
LABELS = _labels(
    [(U.BLOCK, None), (U.TAG, 0), (U.CITE, 0), (U.EVIDENCE, 0), (U.OTHER, None), (U.ANALYTIC, None)],
    lengths={3: 20},
    cards=(CardLabel(card=0, completeness=CardCompleteness.FULL),),
    spans=(SpanLabel(index=3, underline=((0, 10),), highlight=((2, 5),)),),
)

#: The parser got everything right except calling the analytic a tag, and built a second card from it.
PREDICTION = Prediction(
    units={0: U.BLOCK, 1: U.TAG, 2: U.CITE, 3: U.EVIDENCE, 4: U.OTHER, 5: U.TAG},
    cards=[(1, 3, CardCompleteness.FULL), (5, 5, CardCompleteness.CITE_ONLY)],
    underline={3: [(0, 8), (12, 14)]},
    highlight={3: [(2, 5)]},
)


# --------------------------------------------------------------------------------------------
# Ratios
# --------------------------------------------------------------------------------------------


def test_counts_give_precision_recall_and_f1() -> None:
    counts = Counts(true_positive=3, false_positive=1, false_negative=2)
    assert counts.precision == pytest.approx(3 / 4)
    assert counts.recall == pytest.approx(3 / 5)
    assert counts.f1 == pytest.approx(6 / 9)  # 2*3 / (2*3 + 1 + 2)
    assert counts.support == 5


def test_nothing_to_measure_is_none_not_zero_or_one() -> None:
    assert Counts().f1 is None and Counts().precision is None and Counts().recall is None


def test_all_missed_is_zero() -> None:
    assert Counts(false_negative=4).f1 == 0.0


# --------------------------------------------------------------------------------------------
# One file
# --------------------------------------------------------------------------------------------


def test_unit_counts() -> None:
    score = score_file(LABELS, PREDICTION)
    tag = score.units[U.TAG]
    assert (tag.true_positive, tag.false_positive, tag.false_negative) == (1, 1, 0)
    assert tag.f1 == pytest.approx(2 / 3)  # 2*1 / (2 + 1 + 0)
    analytic = score.units[U.ANALYTIC]
    assert (analytic.true_positive, analytic.false_positive, analytic.false_negative) == (0, 0, 1)
    assert analytic.f1 == 0.0
    for unit in (U.BLOCK, U.CITE, U.EVIDENCE, U.OTHER):
        assert score.units[unit].f1 == 1.0
    assert score.units[U.POCKET].f1 is None


def test_a_labeled_paragraph_the_parser_never_emitted_is_a_miss() -> None:
    score = score_file(LABELS, Prediction(units={0: U.BLOCK}, cards=[]))
    assert score.units[U.TAG].false_negative == 1
    assert score.units[U.TAG].false_positive == 0


def test_card_boundaries_and_completeness() -> None:
    score = score_file(LABELS, PREDICTION)
    assert (score.labeled_cards, score.predicted_cards, score.boundary_matches) == (1, 2, 1)
    assert score.boundary_exact_match == 1.0
    assert score.card_precision == 0.5
    assert score.completeness_accuracy == 1.0


def test_a_card_one_paragraph_short_is_not_a_match() -> None:
    short = Prediction(units=dict(PREDICTION.units), cards=[(1, 2, CardCompleteness.FULL)])
    score = score_file(LABELS, short)
    assert score.boundary_matches == 0
    assert score.boundary_exact_match == 0.0
    assert score.completeness_accuracy is None


def test_wrong_completeness_on_a_matched_card() -> None:
    wrong = Prediction(units=dict(PREDICTION.units), cards=[(1, 3, CardCompleteness.ABBREVIATED)])
    score = score_file(LABELS, wrong)
    assert (score.boundary_matches, score.completeness_correct) == (1, 0)
    assert score.completeness_accuracy == 0.0


def test_character_level_span_f1() -> None:
    score = score_file(LABELS, PREDICTION)
    underline = score.spans["underline"]
    # Labeled 0-9 (10 characters); predicted 0-7 and 12-13 (10 characters); 8 in common.
    assert (underline.true_positive, underline.false_positive, underline.false_negative) == (8, 2, 2)
    assert underline.f1 == pytest.approx(0.8)  # 16 / 20
    assert score.spans["highlight"].f1 == 1.0  # 2-4 both ways
    assert score.span_f1 == pytest.approx(22 / 26)  # tp 11, fp 2, fn 2
    assert score.span_paragraphs == 1


def test_spans_on_unsampled_paragraphs_are_not_scored() -> None:
    extra = Prediction(units=dict(PREDICTION.units), cards=[], underline={3: [(0, 10)], 1: [(0, 5)]})
    score = score_file(LABELS, extra)
    assert score.spans["underline"].false_positive == 0


# --------------------------------------------------------------------------------------------
# Sampling: a score says what it was computed over, and judges only what it can see
# --------------------------------------------------------------------------------------------


#: The same six paragraphs, but only 0-3 are labeled: the card (1-3) is inside, the analytic is not.
SAMPLED = _labels(
    [(U.BLOCK, None), (U.TAG, 0), (U.CITE, 0), (U.EVIDENCE, 0), (U.OTHER, None), (U.ANALYTIC, None)],
    cards=(CardLabel(card=0, completeness=CardCompleteness.FULL),),
    blocks=((0, 3),),
)


def test_a_score_records_the_rows_it_was_computed_over() -> None:
    score = score_file(SAMPLED, PREDICTION)
    assert (score.labeled_rows, score.total_rows) == (4, 6)
    assert score.sampling_rate == pytest.approx(4 / 6)
    assert score.units[U.ANALYTIC].support == 0  # paragraph 5 is outside the block, so not counted


def test_a_card_the_parser_found_outside_the_labeled_block_is_not_a_false_positive() -> None:
    """The parser's second card (5-5) sits in unlabeled text. It is unjudged, not wrong."""
    score = score_file(SAMPLED, PREDICTION)
    assert (score.labeled_cards, score.predicted_cards, score.boundary_matches) == (1, 1, 1)
    assert score.card_precision == 1.0


def test_a_card_only_half_inside_a_block_is_not_counted_either() -> None:
    half = _labels(
        [
            (U.BLOCK, None),
            (U.TAG, None),
            (U.CITE, None),
            (U.EVIDENCE, None),
            (U.OTHER, None),
            (U.ANALYTIC, None),
        ],
        blocks=((0, 2),),
    )
    score = score_file(half, PREDICTION)
    assert (score.labeled_cards, score.predicted_cards) == (0, 0)
    assert score.boundary_exact_match is None


def test_group_sampling_counts_add_up() -> None:
    groups = group_scores(
        [
            (_entry(TemplateFamily.VERBATIM), score_file(SAMPLED, PREDICTION)),
            (_entry(TemplateFamily.CARDMIRROR), score_file(LABELS, PREDICTION)),
        ]
    )
    overall = groups["overall"].score
    assert (overall.labeled_rows, overall.total_rows) == (10, 12)
    assert groups["overall"].as_json()["sampling"] == {
        "labeled_rows": 10,
        "total_rows": 12,
        "rate": 0.8333,
    }


# --------------------------------------------------------------------------------------------
# Groups: counts are summed, then divided
# --------------------------------------------------------------------------------------------


def _entry(family: TemplateFamily, category: Category = Category.CASELIST) -> ManifestEntry:
    return ManifestEntry(
        digest=SHA, category=category, season="2026-27", debate_format=DebateFormat.LD, template_family=family
    )


def test_groups_micro_average() -> None:
    """File one has TAG 1/1/0 (tp/fp/fn); file two 3/0/1.

    Summed: 4/1/1, so F1 = 8/10 — not the mean of 2/3 and 6/7.
    """
    second = _labels(
        [
            (U.TAG, 0),
            (U.CITE, 0),
            (U.EVIDENCE, 0),
            (U.TAG, 1),
            (U.CITE, 1),
            (U.EVIDENCE, 1),
            (U.TAG, 2),
            (U.CITE, 2),
            (U.EVIDENCE, 2),
            (U.TAG, None),
        ],
    )
    second_prediction = Prediction(
        units={i: p.unit for i, p in enumerate(second.paragraphs)} | {9: U.ANALYTIC}, cards=[]
    )
    groups = group_scores(
        [
            (_entry(TemplateFamily.VERBATIM), score_file(LABELS, PREDICTION)),
            (_entry(TemplateFamily.OTHER_HEURISTIC, Category.CAMP), score_file(second, second_prediction)),
        ]
    )
    assert groups["overall"].files == 2
    assert groups["overall"].score.units[U.TAG].f1 == pytest.approx(0.8)
    assert groups["template:verbatim"].score.units[U.TAG].f1 == pytest.approx(2 / 3)
    assert groups["template:non-verbatim"].score.units[U.TAG].f1 == pytest.approx(6 / 7)
    assert set(groups) == {
        "overall", "template:verbatim", "template:non-verbatim", "source:caselist", "source:camp",
        "family:verbatim", "family:other-heuristic", "format:LD",
    }  # fmt: skip


def test_cardmirror_counts_as_verbatim_and_wiki_converted_does_not() -> None:
    groups = group_scores(
        [
            (_entry(TemplateFamily.CARDMIRROR), score_file(LABELS, PREDICTION)),
            (_entry(TemplateFamily.WIKI_CONVERTED), score_file(LABELS, PREDICTION)),
        ]
    )
    assert groups["template:verbatim"].files == 1
    assert groups["template:non-verbatim"].files == 1


# --------------------------------------------------------------------------------------------
# Targets (ac3) and the gate (ac4)
# --------------------------------------------------------------------------------------------


def test_the_targets_are_the_ones_ac3_states() -> None:
    stated = {(t.group, t.metric, t.threshold) for t in TARGETS}
    assert stated == {
        ("template:verbatim", "TAG", 0.97), ("template:verbatim", "CITE", 0.97),
        ("template:verbatim", "EVIDENCE", 0.97), ("template:verbatim", "POCKET", 0.95),
        ("template:verbatim", "HAT", 0.95), ("template:verbatim", "BLOCK", 0.95),
        ("template:verbatim", "ANALYTIC", 0.85), ("template:verbatim", "span", 0.99),
        ("template:non-verbatim", "TAG", 0.90), ("template:non-verbatim", "CITE", 0.90),
        ("template:non-verbatim", "EVIDENCE", 0.90),
    }  # fmt: skip


def test_targets_are_met_missed_or_not_measured() -> None:
    results = {
        (r["group"], r["metric"]): r["status"]
        for r in evaluate_targets(
            group_scores([(_entry(TemplateFamily.VERBATIM), score_file(LABELS, PREDICTION))])
        )
    }
    assert results[("template:verbatim", "CITE")] == "MET"  # 1.0
    assert results[("template:verbatim", "TAG")] == "MISSED"  # 0.667
    assert results[("template:verbatim", "POCKET")] == "NOT MEASURED"
    assert results[("template:non-verbatim", "TAG")] == "NOT MEASURED"


def _groups_with_tag_f1(tp: int, fp: int, fn: int):  # type: ignore[no-untyped-def]
    labels = _labels([(U.TAG, None)] * (tp + fn) + [(U.OTHER, None)] * fp)
    units = {i: U.TAG for i in range(tp)} | {i: U.OTHER for i in range(tp, tp + fn)}
    units |= {i: U.TAG for i in range(tp + fn, tp + fn + fp)}
    return group_scores(
        [(_entry(TemplateFamily.VERBATIM), score_file(labels, Prediction(units=units, cards=[])))]
    )


BASELINE = {
    "parser_version": "v1",
    "sampling_plan_id": "plan0001",
    "tiers": {"full": {"overall": {"TAG": 0.98}}},
}


def _check(groups, baseline=BASELINE, *, tier="full", parser_version="v1", plan_id="plan0001"):  # type: ignore[no-untyped-def]
    return check_against_baseline(groups, baseline, tier=tier, parser_version=parser_version, plan_id=plan_id)


def test_a_drop_within_tolerance_passes() -> None:
    groups = _groups_with_tag_f1(tp=97, fp=3, fn=2)  # F1 = 194 / 199 = 0.9749, 0.0051 below
    assert _check(groups) == ([], [])


def test_a_drop_of_more_than_one_point_fails() -> None:
    groups = _groups_with_tag_f1(tp=96, fp=4, fn=4)  # F1 = 192 / 200 = 0.96, 0.02 below
    failures, _ = _check(groups)
    assert failures == ["overall TAG: F1 0.9600 is more than 0.01 below the baseline 0.9800"]


def test_a_tier_with_no_baseline_fails_rather_than_passing_vacuously() -> None:
    failures, _ = _check(_groups_with_tag_f1(1, 0, 0), tier="pr-subset")
    assert "no baseline is established for the pr-subset tier" in failures[0]


def test_a_newer_parser_is_still_held_to_the_old_baseline() -> None:
    failures, notes = _check(_groups_with_tag_f1(96, 4, 4), parser_version="v2")
    assert failures and "recorded for parser v1" in notes[0]


def test_a_different_sampling_plan_refuses_rather_than_comparing() -> None:
    """Two samples are two measurements. Comparing them would report a regression that is not one."""
    failures, _ = _check(_groups_with_tag_f1(tp=100, fp=0, fn=0), plan_id="plan0002")
    assert len(failures) == 1
    assert "two samples are two measurements" in failures[0]


def test_a_baseline_with_no_plan_recorded_still_compares() -> None:
    """An older baseline that predates the plan is not refused; there is nothing to disagree with."""
    older = {"parser_version": "v1", "tiers": BASELINE["tiers"]}
    assert _check(_groups_with_tag_f1(tp=97, fp=3, fn=2), older) == ([], [])


# --------------------------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------------------------


def test_reports_carry_every_breakdown_and_no_file_detail_in_markdown() -> None:
    score = score_file(LABELS, PREDICTION)
    groups = group_scores([(_entry(TemplateFamily.VERBATIM), score)])
    report = report_json(
        tier="full", parser_version="v1", profile_version="p1", plan_id="plan0001", groups=groups,
        per_file={SHA: score}, gate_failures=[], gate_notes=[], label_status={"CORRECTED": 1},
    )  # fmt: skip
    assert report["sampling"] == {"plan_id": "plan0001", "labeled_rows": 6, "total_rows": 6, "rate": 1.0}
    assert set(report["groups"]["overall"]["units"]) == {u.value for u in StructuralUnit}
    assert report["groups"]["overall"]["cards"]["boundary_exact_match"] == 1.0
    assert report["groups"]["overall"]["spans"]["underline"]["f1"] == 0.8
    markdown = render_markdown(report)
    for heading in ("## Targets", "## Unit F1 by group", "## Cards and spans by group"):
        assert heading in markdown
    assert "Labeled rows" in markdown and "6 labeled paragraphs" in markdown
    assert "source:caselist" in markdown and "family:verbatim" in markdown and "format:LD" in markdown
    assert SHA[:12] not in markdown


# --------------------------------------------------------------------------------------------
# From a real ParsedDocument
# --------------------------------------------------------------------------------------------


def test_prediction_reads_units_card_ranges_and_spans_from_a_parse() -> None:
    synthetic = build_synthetic_file()
    document = parse_evaluation_file(DebateDocxParser(), _entry(TemplateFamily.VERBATIM), synthetic.content)
    prediction = prediction_from_document(document)
    assert prediction.units == {s.element_index: s.unit for s in document.sections}
    assert [(first, last) for first, last, _ in prediction.cards] == [
        (c.provenance.first_element_index, c.provenance.last_element_index) for c in document.cards
    ]
    assert all(0 <= start < end for ranges in prediction.underline.values() for start, end in ranges)
