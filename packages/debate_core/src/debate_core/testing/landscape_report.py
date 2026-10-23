"""The synthetic caselist the landscape report is tested against, read back from its files.

`scripts/make_landscape_fixture.py` writes `tests/fixtures/landscape/synthetic_caselist/`; the
report's service tests and its renderer tests both build their inputs from it with
:func:`read_synthetic_caselist`, so the two read one fixture the same way. Everything in it is
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
from debate_core.domain.caselist import Disclosure
from debate_core.domain.landscape import Taxonomy
from debate_core.domain.landscape_classification import OverrideRules, PositionClassification
from debate_core.domain.landscape_report import AffAssignment, LandscapeCard

__all__ = [
    "SYNTHETIC_CASELIST",
    "SYNTHETIC_PARSER_VERSION",
    "SYNTHETIC_REPORT_DATE",
    "SYNTHETIC_THROUGH",
    "read_synthetic_caselist",
    "synthetic_staleness",
]

SYNTHETIC_CASELIST: Final = "synthpolicy26"
SYNTHETIC_THROUGH: Final = date(2026, 9, 15)
"""The fixture's second snapshot: its third, a week later, is out of the report's range."""
SYNTHETIC_REPORT_DATE: Final = date(2026, 9, 17)
SYNTHETIC_PARSER_VERSION: Final = "2026.10.20-docx-6"


def _rows[ModelT](path: Path, read: Callable[[object], ModelT]) -> tuple[ModelT, ...]:
    return tuple(read(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line)


def read_synthetic_caselist(
    directory: Path, *, aff_assignments: tuple[AffAssignment, ...] = ()
) -> LandscapeReportInputs:
    """The report's inputs as the fixture holds them, through its second snapshot."""
    return LandscapeReportInputs(
        caselist=SYNTHETIC_CASELIST,
        through=SYNTHETIC_THROUGH,
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
    )


def synthetic_staleness(
    *, report_date: date = SYNTHETIC_REPORT_DATE, archives_awaiting_download: int = 0
) -> LandscapeStaleness:
    """What `v1-e34-t03`'s hook says of the fixture: newest snapshot its second, two days old by default."""
    return assess_staleness(
        SYNTHETIC_CASELIST,
        report_date=report_date,
        newest_snapshot=SYNTHETIC_THROUGH,
        archives_awaiting_download=archives_awaiting_download,
    )
