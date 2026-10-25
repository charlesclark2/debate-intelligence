"""The synthetic caselist the landscape report is tested against, read back from its files.

`scripts/make_landscape_fixture.py` writes `tests/fixtures/landscape/synthetic_caselist/`; the
report's service tests and its renderer tests both build their inputs from it with
:func:`read_synthetic_caselist`, so the two read one fixture the same way. Its `analytic_texts.json`,
`v1-e32-t11`'s readings of CP texts, alternatives, roles of the ballot and overviews, is written by hand,
not by the script, and read with the rest (:func:`read_synthetic_analytic_texts`). Everything in it is
invented: see the directory's README.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Final

import yaml

from debate_core.application.landscape_report import LandscapeReportInputs
from debate_core.application.landscape_staleness import LandscapeStaleness, assess_staleness
from debate_core.arguments.landscape.analytic_texts import AnalyticTextInputs, text_digest
from debate_core.domain.caselist import Disclosure
from debate_core.domain.landscape import Taxonomy, TopicMap
from debate_core.domain.landscape_classification import OverrideRules, PositionClassification
from debate_core.domain.landscape_report import AffAssignment, LandscapeCard
from debate_core.domain.landscape_texts import AnalyticTextReading

__all__ = [
    "SYNTHETIC_CASELIST",
    "SYNTHETIC_PARSER_VERSION",
    "SYNTHETIC_REPORT_DATE",
    "SYNTHETIC_THIRD_SNAPSHOT",
    "SYNTHETIC_THROUGH",
    "TOPIC_CHANGE_CASELIST",
    "TOPIC_CHANGE_SNAPSHOT",
    "read_synthetic_analytic_texts",
    "read_synthetic_caselist",
    "read_topic_change_caselist",
    "synthetic_staleness",
    "topic_change_snapshot_topics",
]

SYNTHETIC_CASELIST: Final = "synthpolicy26"
SYNTHETIC_THROUGH: Final = date(2026, 9, 15)
"""The fixture's second snapshot, the t03 golden bundle's: its third, a week later, is out of range."""
SYNTHETIC_THIRD_SNAPSHOT: Final = date(2026, 9, 22)
"""The fixture's third snapshot, which `v1-e32-t04`'s trends are tested through."""
TOPIC_CHANGE_CASELIST: Final = "synthld26"
TOPIC_CHANGE_SNAPSHOT: Final = date(2026, 9, 1)
"""The topic-change caselist's second snapshot: the first on its new topic."""
SYNTHETIC_REPORT_DATE: Final = date(2026, 9, 17)
SYNTHETIC_PARSER_VERSION: Final = "2026.10.20-docx-6"
ANALYTIC_TEXTS_FILE: Final = "analytic_texts.json"


def _rows[ModelT](path: Path, read: Callable[[object], ModelT]) -> tuple[ModelT, ...]:
    return tuple(read(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line)


def read_synthetic_analytic_texts(directory: Path) -> AnalyticTextInputs | None:
    """`analytic_texts.json`'s readings, texts, guard and plank counts; None when there is no such file.

    A source is named as the fixture names it (`b1`, the digest `b1b1…b1`). A reading's digest is computed
    from its `words`, as the reader computes one, and its `quoted` text, when not null, is what reading the
    source again returns. A plank (`v1-e32-t16`) names its CP text's paragraph (`stem`) and the advantages it
    solves. The caselist's schools, a text naming one of which is withheld, are the fixture's.
    """
    path = directory / ANALYTIC_TEXTS_FILE
    if not path.is_file():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    readings: dict[str, tuple[AnalyticTextReading, ...]] = {}
    texts: dict[tuple[str, int], str] = {}
    refused: dict[str, int] = {}
    planks_refused: dict[str, int] = {}
    plank_labels: dict[str, int] = {}
    for name, held in document["sources"].items():
        sha = name * 32
        found: list[AnalyticTextReading] = []
        for row in held["readings"]:
            found.append(
                AnalyticTextReading(
                    kind=row["kind"],
                    form=row["form"],
                    label_element_index=row["label"],
                    element_index=row["paragraph"],
                    unit=row["unit"],
                    kept=row["kept"],
                    digest=text_digest(row["words"]) if "words" in row else None,
                    placement=row["placement"],
                    position_id=row.get("position"),
                    role=row.get("role"),
                    stem_element_index=row.get("stem"),
                    solves=tuple(row.get("solves", ())),
                    solves_other_words=row.get("solves_other_words", 0),
                )
            )
            if row.get("quoted") is not None:
                texts[(sha, row["paragraph"])] = row["quoted"]
        readings[sha] = tuple(found)
        if held.get("refused_by_guard"):
            refused[sha] = held["refused_by_guard"]
        if held.get("planks_refused_by_guard"):
            planks_refused[sha] = held["planks_refused_by_guard"]
        if held.get("plank_labels"):
            plank_labels[sha] = held["plank_labels"]
    names: dict[str, set[str]] = {}
    for one in _rows(directory / "disclosures.jsonl", Disclosure.model_validate):
        names.setdefault(one.school, set()).add(one.team_code)
    return AnalyticTextInputs(
        readings=readings,
        texts=texts,
        caselist_names={school: tuple(sorted(codes)) for school, codes in sorted(names.items())},
        refused_by_guard=refused,
        planks_refused_by_guard=planks_refused,
        plank_labels=plank_labels,
    )


def read_synthetic_caselist(
    directory: Path, *, aff_assignments: tuple[AffAssignment, ...] = (), through: date = SYNTHETIC_THROUGH
) -> LandscapeReportInputs:
    """The report's inputs as the fixture holds them, through its second snapshot unless told otherwise."""
    return LandscapeReportInputs(
        caselist=SYNTHETIC_CASELIST,
        through=through,
        taxonomy=Taxonomy.model_validate(
            yaml.safe_load((directory / "taxonomy.yaml").read_text(encoding="utf-8"))
        ),
        overrides=OverrideRules.model_validate(
            yaml.safe_load((directory / "overrides.yaml").read_text(encoding="utf-8"))
        ),
        parser_version=SYNTHETIC_PARSER_VERSION,
        classifications=_rows(directory / "classifications.jsonl", PositionClassification.model_validate),
        disclosures=_rows(directory / "disclosures.jsonl", Disclosure.model_validate),
        cards=_rows(directory / "cards.jsonl", LandscapeCard.model_validate),
        aff_assignments=aff_assignments,
        analytic_texts=read_synthetic_analytic_texts(directory),
    )


def topic_change_snapshot_topics(directory: Path) -> dict[date, str]:
    """Each snapshot of the topic-change caselist, with the topic its `topics.yaml` puts it on."""
    topics = TopicMap.model_validate(yaml.safe_load((directory / "topics.yaml").read_text(encoding="utf-8")))
    snapshots = {one.snapshot for one in _rows(directory / "disclosures.jsonl", Disclosure.model_validate)}
    resolved = {day: topics.resolve(TOPIC_CHANGE_CASELIST, day) for day in snapshots}
    return {day: found.topic_id for day, found in sorted(resolved.items()) if found is not None}


def read_topic_change_caselist(directory: Path, *, with_the_old_topic: bool = False) -> LandscapeReportInputs:
    """The topic-change caselist's report inputs on its new topic, through its second snapshot.

    Its disclosures are the new topic's, as a run reads them, unless `with_the_old_topic`, which keeps
    the old topic's too. Its overrides are none, and its topic range the new topic's in `topics.yaml`.
    """
    taxonomy = Taxonomy.model_validate(
        yaml.safe_load((directory / "taxonomy.yaml").read_text(encoding="utf-8"))
    )
    on = topic_change_snapshot_topics(directory)
    topics = TopicMap.model_validate(yaml.safe_load((directory / "topics.yaml").read_text(encoding="utf-8")))
    covering = next(
        one
        for one in topics.topic(taxonomy.topic_id).caselists
        if one.covers(TOPIC_CHANGE_CASELIST, TOPIC_CHANGE_SNAPSHOT)
    )
    disclosures = tuple(
        one
        for one in _rows(directory / "disclosures.jsonl", Disclosure.model_validate)
        if with_the_old_topic or on[one.snapshot] == taxonomy.topic_id
    )
    return LandscapeReportInputs(
        caselist=TOPIC_CHANGE_CASELIST,
        through=TOPIC_CHANGE_SNAPSHOT,
        taxonomy=taxonomy,
        overrides=OverrideRules(topic_id=taxonomy.topic_id, overrides=()),
        parser_version=SYNTHETIC_PARSER_VERSION,
        classifications=_rows(directory / "classifications.jsonl", PositionClassification.model_validate),
        disclosures=disclosures,
        cards=_rows(directory / "cards.jsonl", LandscapeCard.model_validate),
        snapshot_topics=on,
        topic_range=(covering.effective_from, covering.effective_to),
    )


def synthetic_staleness(
    *,
    report_date: date = SYNTHETIC_REPORT_DATE,
    archives_awaiting_download: int = 0,
    caselist: str = SYNTHETIC_CASELIST,
    newest_snapshot: date = SYNTHETIC_THROUGH,
) -> LandscapeStaleness:
    """What `v1-e34-t03`'s hook says of the fixture: newest snapshot its second, two days old by default."""
    return assess_staleness(
        caselist,
        report_date=report_date,
        newest_snapshot=newest_snapshot,
        archives_awaiting_download=archives_awaiting_download,
    )
