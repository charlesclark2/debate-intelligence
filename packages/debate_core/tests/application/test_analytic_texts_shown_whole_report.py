"""The report's CP texts shown whole, from synthetic files read by the reader itself (`v1-e32-t35` ac1).

`tests/fixtures/landscape/cp_texts_shown_whole` holds seven invented States CP blocks of the synthetic
caselist's negative files; its README counts by hand what the report shows of them, and its
`report_section.md` is that part of report.md, written by hand. Here the files are read by
`read_analytic_texts` and `read_back_texts`, as a run reads them, and the report is built over the
synthetic caselist's own rounds.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

from debate_core.application.landscape_report import LandscapeReportInputs, LandscapeReportService
from debate_core.arguments.landscape.analytic_texts import (
    AnalyticTextInputs,
    AnalyticTextRules,
    CounterplanActors,
    SectionParagraph,
    SourceParagraphs,
    read_analytic_texts,
    read_back_texts,
)
from debate_core.arguments.landscape.source_headings import CaselistNames
from debate_core.domain.landscape_classification import OverrideRules
from debate_core.domain.landscape_texts import AnalyticTextKind
from debate_core.domain.style_profile import StructuralUnit
from debate_core.testing.landscape_report import read_synthetic_caselist, synthetic_staleness

REPO = Path(__file__).resolve().parents[4]
SYNTHETIC = REPO / "tests" / "fixtures" / "landscape" / "synthetic_caselist"
WHOLE = REPO / "tests" / "fixtures" / "landscape" / "cp_texts_shown_whole"
HEADING_LEVELS = {StructuralUnit.POCKET: 1, StructuralUnit.HAT: 2, StructuralUnit.BLOCK: 3}
CARD_UNITS = frozenset({StructuralUnit.TAG, StructuralUnit.CITE, StructuralUnit.EVIDENCE})

STEM = "The fifty states and all relevant territories should:"
WHOLE_TEXT = f"{STEM}\nExpand sample clinics in rural areas.\nFund a sample research prize."


def _fixture() -> dict[str, Any]:
    return yaml.safe_load((WHOLE / "sources.yaml").read_text(encoding="utf-8"))


def _source(rows: list[list[Any]]) -> SourceParagraphs:
    """A file's paragraphs, each under the headings above it, and its cards' paragraphs and tags."""
    over: list[tuple[int, str]] = []
    paragraphs: list[SectionParagraph] = []
    for index, unit_name, text in rows:
        unit = StructuralUnit(unit_name)
        level = HEADING_LEVELS.get(unit)
        if level is not None:
            over = [one for one in over if one[0] < level]
        paragraphs.append(SectionParagraph(index, unit, text, tuple(heading for _, heading in over)))
        if level is not None:
            over.append((level, text))
    return SourceParagraphs(
        paragraphs=tuple(paragraphs),
        in_cards=frozenset(one.element_index for one in paragraphs if one.unit in CARD_UNITS),
        tags=frozenset(one.text for one in paragraphs if one.unit is StructuralUnit.TAG),
    )


def _inputs() -> LandscapeReportInputs:
    synthetic = read_synthetic_caselist(SYNTHETIC)
    assert synthetic.analytic_texts is not None
    schools = synthetic.analytic_texts.caselist_names
    fixture = _fixture()
    topic = synthetic.taxonomy.topic_id
    rules = AnalyticTextRules(
        synthetic.taxonomy,
        OverrideRules.model_validate({"topic_id": topic, "overrides": fixture["overrides"]}),
        CounterplanActors(topic_id=topic, cp_text_actors=tuple(fixture["actors"])),
    )
    readings: dict[str, Any] = {}
    texts: dict[tuple[str, int], str] = {}
    for name, rows in fixture["files"].items():
        sha = name * 32
        source = _source(rows)
        found = read_analytic_texts(source, rules, caselist=CaselistNames(schools))
        readings[sha] = found.readings
        texts.update(
            {(sha, index): text for index, text in read_back_texts(source.paragraphs, found.readings).items()}
        )
    return dataclasses.replace(
        synthetic, analytic_texts=AnalyticTextInputs(readings=readings, texts=texts, caselist_names=schools)
    )


def test_the_cp_texts_part_matches_the_hand_written_section() -> None:
    report_md = LandscapeReportService().bundle(_inputs(), synthetic_staleness()).files["report.md"]
    start = report_md.index("### Counterplan texts\n")
    end = report_md.index("### Kritik alternatives\n", start)
    assert report_md[start:end] == (WHOLE / "report_section.md").read_text(encoding="utf-8")


def test_a_text_with_its_planks_and_the_text_alone_are_two_ranked_texts() -> None:
    texts = LandscapeReportService().build(_inputs(), synthetic_staleness()).texts
    assert texts is not None
    (states,) = [one for one in texts.positions if one.kind is AnalyticTextKind.CP_TEXT]
    assert [(row.rank, row.teams, row.text) for row in states.texts] == [(1, 4, WHOLE_TEXT), (2, 3, STEM)]
    assert states.more is None
    coverage = next(one for one in texts.coverage if one.kind is AnalyticTextKind.CP_TEXT)
    assert (coverage.labels, coverage.counted, coverage.withheld_texts, coverage.unread) == (7, 7, 1, 0)
