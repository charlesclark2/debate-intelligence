"""The one rule a removal, its execution and `caselist status` choose school views by (`v1-e32-t13`).

Every expectation is written by hand from the bundle layout `v1-e32-t04` documents:
`reports/landscape/<caselist>/<snapshot>/<file>`, school views `schools.csv` and `schools.md`, and
five circuit-wide files.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from debate_core.application.caselist.removal_residue import RemovalCompletion
from debate_core.application.caselist.removal_school_views import (
    LANDSCAPE_PREFIX,
    SchoolViewReach,
    UnknownLandscapeFile,
    bundle_of,
    is_school_view,
    reached,
    school_view_cutoffs,
    written_before,
)
from debate_core.application.landscape_bundle_files import SCHOOL_VIEW_FILES
from debate_core.application.ports.suppression import (
    ReasonCode,
    RemovalLogEntry,
    RemovalLogKind,
    RemovalOutcome,
    RemovalScopeEntry,
    RemovalSelectorKind,
)

COMPLETED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
MARGIN = timedelta(minutes=15)


class TestIsSchoolView:
    @pytest.mark.parametrize(
        "key",
        [
            "reports/landscape/hsld26/2026-10-19/schools.csv",
            "reports/landscape/hsld26/2026-10-19/schools.md",
        ],
    )
    def test_a_school_view_of_a_caselist_reached_is_one(self, key: str) -> None:
        assert is_school_view(key, {"hsld26"})

    @pytest.mark.parametrize(
        "name", ["report.md", "positions.csv", "top_cards.csv", "impact_cards.csv", "trends.csv"]
    )
    def test_a_circuit_wide_file_never_is(self, name: str) -> None:
        assert not is_school_view(f"reports/landscape/hsld26/2026-10-19/{name}", {"hsld26"})

    @pytest.mark.parametrize(
        "key",
        [
            "reports/landscape/hspolicy26/2026-10-19/schools.csv",
            "reports/landscape/hsld26b/2026-10-19/schools.csv",
            "reports/landscape/hsld2/2026-10-19/schools.csv",
            "reports/landscape/xhsld26/2026-10-19/schools.csv",
            "reports/landscape/hspolicy26/2026-10-19/notes.txt",
            "reports/tub/search/hsld26/schools.csv",
            "parsed/hsld26/2026-10-19/schools.csv",
        ],
    )
    def test_another_caselists_file_never_is_and_is_never_judged(self, key: str) -> None:
        """Matched on the caselist segment whole: a name that begins or ends like it is another's."""
        assert not is_school_view(key, {"hsld26"})

    @pytest.mark.parametrize(
        "key",
        [
            "reports/landscape/hsld26/2026-10-19/notes.txt",
            "reports/landscape/hsld26/2026-10-19/.schools.csv.incoming",
            "reports/landscape/hsld26/2026-10-19/schools.csv.bak",
            "reports/landscape/hsld26/schools.csv",
            "reports/landscape/hsld26/2026-10-19/old/schools.csv",
            "reports/landscape/hsld26/latest/schools.csv",
            "reports/landscape/hsld26/2026-10-1/schools.csv",
        ],
    )
    def test_anything_else_in_a_caselist_reached_is_an_error_never_a_guess(self, key: str) -> None:
        with pytest.raises(UnknownLandscapeFile) as refused:
            is_school_view(key, {"hsld26"})
        assert refused.value.key == key

    def test_the_bundle_of_a_school_view_is_its_caselist_and_snapshot(self) -> None:
        assert bundle_of("reports/landscape/hsld26/2026-10-19/schools.md") == (
            "hsld26",
            datetime(2026, 10, 19).date(),
        )


class TestTheAgeRule:
    def test_older_by_more_than_the_margin_is_before(self) -> None:
        assert written_before(COMPLETED - MARGIN - timedelta(seconds=1), COMPLETED)

    @pytest.mark.parametrize("offset", [MARGIN, timedelta(minutes=1), timedelta(0), -timedelta(days=1)])
    def test_within_the_margin_or_after_is_not(self, offset: timedelta) -> None:
        assert not written_before(COMPLETED - offset, COMPLETED)

    def test_a_version_with_no_time_is_older_than_nothing(self) -> None:
        assert not written_before(None, COMPLETED)

    def test_a_caselist_touched_now_is_reached_whatever_the_age(self) -> None:
        reach = (SchoolViewReach("hsld26"),)
        assert reached("reports/landscape/hsld26/2026-10-19/schools.csv", None, reach)
        assert reached(
            "reports/landscape/hsld26/2026-10-19/schools.csv", COMPLETED + timedelta(days=9), reach
        )

    def test_one_an_earlier_run_touched_is_reached_only_before_that_run(self) -> None:
        reach = (SchoolViewReach("hsld26", older_than=RemovalCompletion("RM-2026-01", COMPLETED)),)
        key = "reports/landscape/hsld26/2026-10-19/schools.csv"
        assert reached(key, COMPLETED - timedelta(days=1), reach)
        assert not reached(key, COMPLETED + timedelta(minutes=1), reach)
        assert not reached(
            "reports/landscape/hsld26/2026-10-19/report.md", COMPLETED - timedelta(days=1), reach
        )


def entry(
    request_id: str, at: datetime, outcome: RemovalOutcome = RemovalOutcome.COMPLETED
) -> RemovalLogEntry:
    return RemovalLogEntry(
        kind=RemovalLogKind.REMOVAL,
        recorded_at=at,
        request_id=request_id,
        reason=ReasonCode.REQUESTED_BY_TEAM,
        environment="dev",
        outcome=outcome,
        selector=RemovalSelectorKind.TEAM,
        error_code=None if outcome is RemovalOutcome.COMPLETED else "STORE_UNAVAILABLE",
    )


def scope(of: RemovalLogEntry, *caselists: str) -> RemovalScopeEntry:
    return RemovalScopeEntry(
        recorded_at=of.recorded_at,
        request_id=of.request_id,
        environment=of.environment,
        caselists=caselists,
        manifest_rewrites=(),
    )


class TestTheCutoffs:
    def test_a_rerun_that_did_not_touch_a_caselist_leaves_its_cutoff_at_the_run_that_did(self) -> None:
        first = entry("RM-2026-01", COMPLETED)
        rerun = entry("RM-2026-01", COMPLETED + timedelta(days=3))

        cutoffs = school_view_cutoffs([first, rerun], [scope(first, "hsld26"), scope(rerun)], "dev")

        assert cutoffs == {"hsld26": RemovalCompletion("RM-2026-01", COMPLETED)}

    def test_the_latest_run_whose_own_scope_names_it_wins_whichever_request(self) -> None:
        first = entry("RM-2026-01", COMPLETED)
        second = entry("RM-2026-02", COMPLETED + timedelta(days=1))

        cutoffs = school_view_cutoffs(
            [first, second], [scope(first, "hsld26", "hspolicy26"), scope(second, "hsld26")], "dev"
        )

        assert cutoffs == {
            "hsld26": RemovalCompletion("RM-2026-02", COMPLETED + timedelta(days=1)),
            "hspolicy26": RemovalCompletion("RM-2026-01", COMPLETED),
        }
        assert school_view_cutoffs(
            [first, second], [scope(first, "hsld26"), scope(second, "hsld26")], "dev", request_id="RM-2026-01"
        ) == {"hsld26": RemovalCompletion("RM-2026-01", COMPLETED)}

    def test_a_stopped_run_another_environment_or_a_run_with_no_scope_sets_none(self) -> None:
        stopped = entry("RM-2026-01", COMPLETED, RemovalOutcome.INCOMPLETE)
        prod = entry("RM-2026-01", COMPLETED + timedelta(hours=1)).model_copy(update={"environment": "prod"})
        unscoped = entry("RM-2026-03", COMPLETED + timedelta(hours=2))

        assert (
            school_view_cutoffs(
                [stopped, prod, unscoped], [scope(stopped, "hsld26"), scope(prod, "hsld26")], "dev"
            )
            == {}
        )


OPERATOR_ACCESS = (
    Path(__file__).parents[5] / "infrastructure" / "modules" / "evidence_bucket" / "operator_access.tf"
)
"""Where the removal credential is granted the school views. It spells the names; these are their source."""


class TestTheRemovalCredentialsGrant:
    def _local(self, name: str) -> str:
        defined = re.search(
            rf"^\s*{name}\s*=\s*(?P<value>.+?)\s*$", OPERATOR_ACCESS.read_text(encoding="utf-8"), re.MULTILINE
        )
        assert defined is not None, f"operator_access.tf no longer defines {name}"
        return defined.group("value")

    def test_it_names_exactly_the_school_view_files_the_code_deletes(self) -> None:
        """If v1-e32-t04's list or the module's changes alone, this fails here and not at a takedown."""
        assert json.loads(self._local("school_view_files")) == list(SCHOOL_VIEW_FILES)

    def test_it_is_under_the_prefix_the_bundles_are_published_to(self) -> None:
        assert json.loads(self._local("landscape_prefix")) == LANDSCAPE_PREFIX
