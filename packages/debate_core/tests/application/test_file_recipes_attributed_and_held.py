"""AUTO prefers an attributed occurrence, and a path hold stops an occurrence (`v1-e33-t03` ac7, ac9).

The PM's amendments of 2026-10-19 and 2026-10-20 to the resolver of `v1-e33-t01`:

* **Attributed first.** AUTO takes an occurrence with a disclosure on record before one without, and
  falls back to an unattributed one only when no attributed one remains. A camp occurrence with its
  release record counts as attributed: a camp file has no disclosure, and its sidecar entry names
  the camp from that record. Within each group the order is t01's: latest snapshot, lowest source
  SHA-256, lowest element index, lowest disclosure digest.
* **Holds.** An occurrence at a path a removal holds is never resolved, by AUTO or by a pin, before
  the next rebuild leaves it out of the table. The resolver asks the publisher's one rule,
  :func:`~debate_core.application.caselist.publish_plan.stored_row_hold`, for each disclosure record
  of the row, as the search index build does: a hold merged from another machine stops the row at
  once.

Every school, team code, camp and digest here is invented. The expected choices are worked out by
hand from the rows each test plants.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from debate_core.application import file_recipes
from debate_core.application.caselist import publish_plan
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.ports.parsed_store import OccurrenceRecord
from debate_core.application.ports.suppression import (
    PATH_HOLDS_FILENAME,
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    SuppressionState,
    disclosure_digest,
)
from debate_core.domain.card_occurrence import ClusterMembership
from debate_core.domain.caselist import CampFile, Disclosure, Event, RoundLabel, Side
from debate_core.domain.debate_files import CardCompleteness
from debate_core.evidence import fingerprints
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.fakes.parsed_store import InMemoryParsedStore
from debate_core.testing.fakes.suppression import InMemoryAppendOnlyRecord

CASELIST = "hsld26"
OPENEV = "openev"
PARSER = "2026.10.18-docx-4"
PROFILE = "2026.09.20-verbatim-1"
CAMP = "Lanternfield Institute"

CARD = "a0" * 32
SOURCE_1 = "1a" * 32
SOURCE_2 = "2b" * 32
SOURCE_3 = "3c" * 32
REMOVED = "4d" * 32
"""The file a removal took from a path. No row holds it: the hold covers a later upload there."""

ITEM = "structure[0].blocks[0].items[0]"

HEADER = """\
schema_version: 1
title: Synthetic test file
topic: synthetic-topic
format: LD
caselist: {caselist}
position: synthetic-position
side: NEG
fingerprint_version: card-fingerprint-v3
structure:
  - pocket: Pocket
    blocks:
      - block: Block
        items:
"""


def recipe(*, caselist: str = CASELIST, pin: Mapping[str, object] | None = None) -> str:
    item = f"          - fingerprint: {CARD}\n"
    if pin is not None:
        item += "            pin:\n" + "".join(
            f"              {key}: {value}\n" for key, value in pin.items()
        )
    return HEADER.format(caselist=caselist) + item


def path_of(source: str, team_code: str, school: str) -> str:
    return f"{school}/{team_code}/{school}-{team_code}-Neg-Invented Invitational-Round 4-{source[:4]}.docx"


QX = ("QX", "Maple Grove")
ZALU = ("ZaLu", "Cedar Hollow")


def row(
    source: str, element: int, *, team: tuple[str, str] = QX, last: str = "2026-09-08"
) -> OccurrenceRecord:
    return OccurrenceRecord(
        caselist=CASELIST,
        snapshot="2026-09-01",
        last_snapshot=last,
        source_sha256=source,
        parser_version=PARSER,
        profile_version=PROFILE,
        fingerprint_version=fingerprints.FINGERPRINT_VERSION,
        disclosure=disclosure_digest(CASELIST, path_of(source, *team)),
        first_element_index=element,
        last_element_index=element + 2,
        exact_fingerprint=CARD,
        cluster_id=CARD,
        membership=ClusterMembership.NEAR_DUPLICATE,
        completeness=CardCompleteness.FULL,
    )


def record(source: str, *, team: tuple[str, str] = QX, snapshot: str = "2026-09-08") -> Disclosure:
    """The importer's record of one disclosure of `source` by `team`, listed in `snapshot`."""
    team_code, school = team
    return Disclosure(
        source_sha256=source,
        caselist=CASELIST,
        snapshot=date.fromisoformat(snapshot),
        event=Event.LD,
        school=school,
        team_code=team_code,
        side=Side.NEG,
        tournament="Invented Invitational",
        round_label=RoundLabel.from_raw("Round 4"),
        source_path=path_of(source, team_code, school),
    )


def camp_row(source: str, element: int, *, release: str) -> OccurrenceRecord:
    return OccurrenceRecord(
        caselist=OPENEV,
        snapshot=release,
        last_snapshot=release,
        source_sha256=source,
        parser_version=PARSER,
        profile_version=PROFILE,
        fingerprint_version=fingerprints.FINGERPRINT_VERSION,
        disclosure=None,
        camp=CAMP,
        first_element_index=element,
        last_element_index=element + 2,
        exact_fingerprint=CARD,
        cluster_id=CARD,
        membership=ClusterMembership.UNLINKED,
        completeness=CardCompleteness.FULL,
    )


def release_record(source: str, *, year: int) -> CampFile:
    return CampFile(
        source_sha256=source,
        camp=CAMP,
        year=year,
        event=Event.POLICY,
        file_title="Synthetic CP",
        snapshot=date(2026, 7, 30),
    )


def hold_on(team: tuple[str, str], source: str, *, after: str = "2026-09-01") -> PathHoldEntry:
    """A `--source` removal of :data:`REMOVED` from the path `team` disclosed `source` at."""
    return PathHoldEntry(
        caselist=CASELIST,
        disclosure=disclosure_digest(CASELIST, path_of(source, *team)),
        sha256=REMOVED,
        after_snapshot=date.fromisoformat(after),
        recorded_at=datetime(2026, 10, 1, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-07",
    )


REMOVAL = SuppressionEntry(
    action=SuppressionAction.SUPPRESS,
    sha256=REMOVED,
    recorded_at=datetime(2026, 10, 1, tzinfo=UTC),
    reason=ReasonCode.REQUESTED_BY_TEAM,
    request_id="RM-2026-07",
)


class RecordWithHolds(InMemoryAppendOnlyRecord):
    """An in-memory copy of the list that keeps records beside it, as the local file and the bucket do."""

    def __init__(self) -> None:
        super().__init__("in-memory suppression list")
        self.besides: dict[str, InMemoryAppendOnlyRecord] = {}

    def beside(self, filename: str, *, called: str) -> InMemoryAppendOnlyRecord:
        return self.besides.setdefault(filename, InMemoryAppendOnlyRecord(called))


@dataclass
class World:
    store: InMemoryParsedStore = field(default_factory=InMemoryParsedStore)
    caselists: InMemoryCaselistRepository = field(default_factory=InMemoryCaselistRepository)
    record: RecordWithHolds = field(default_factory=RecordWithHolds)

    def resolve(self, text: str) -> file_recipes.ResolvedRecipe:
        loaded = file_recipes.load_recipe(text)
        assert loaded.recipe is not None, loaded.errors
        resolver = file_recipes.RecipeResolver(
            parsed_store=self.store,
            caselists=self.caselists,
            suppression=RecordedSuppressionList(self.record),
            parser_version=PARSER,
        )
        return asyncio.run(resolver.resolve(loaded.recipe, lines=loaded.lines))


def world(
    rows: Sequence[OccurrenceRecord],
    records: Sequence[Disclosure] = (),
    *,
    holds: Sequence[PathHoldEntry] = (),
    camp_rows: Sequence[OccurrenceRecord] = (),
    camp_files: Sequence[CampFile] = (),
) -> World:
    built = World()
    asyncio.run(built.store.write_aggregates(CASELIST, PARSER, index=(), failures=(), occurrences=rows))
    if camp_rows:
        asyncio.run(
            built.store.write_aggregates(OPENEV, PARSER, index=(), failures=(), occurrences=camp_rows)
        )
    for one in records:
        asyncio.run(built.caselists.record_disclosure(one))
    for one in camp_files:
        asyncio.run(built.caselists.record_camp_file(one))
    if holds:
        built.record.lines.append(REMOVAL.to_line())
        beside = built.record.beside(PATH_HOLDS_FILENAME, called="the path-hold record")
        beside.lines.extend(hold.to_line() for hold in holds)
    return built


def chosen(resolved: file_recipes.ResolvedRecipe) -> list[tuple[str, int, str]]:
    return [
        (card.occurrence.source_sha256, card.occurrence.first_element_index, str(card.resolution))
        for card in resolved.cards
    ]


def codes(resolved: file_recipes.ResolvedRecipe) -> list[tuple[str, str]]:
    return [(str(error.code), error.path) for error in resolved.errors]


# ------------------------------------------------------------------------------------------------
# ac7: AUTO prefers an attributed occurrence
# ------------------------------------------------------------------------------------------------


def test_auto_takes_an_attributed_occurrence_over_a_later_unattributed_one() -> None:
    # SOURCE_1 is seen latest, but nothing on record says who disclosed it; SOURCE_2 is on record.
    rows = [row(SOURCE_1, 5, last="2026-10-06"), row(SOURCE_2, 9, last="2026-09-15")]
    resolved = world(rows, [record(SOURCE_2)]).resolve(recipe())
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_2, 9, "AUTO")], ())
    assert resolved.cards[0].disclosure == record(SOURCE_2)


def test_auto_takes_an_unattributed_occurrence_only_when_no_attributed_one_remains() -> None:
    rows = [row(SOURCE_1, 5, last="2026-09-15"), row(SOURCE_2, 9, last="2026-10-06")]
    resolved = world(rows).resolve(recipe())
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_2, 9, "AUTO")], ())
    assert resolved.cards[0].disclosure is None


def test_auto_among_attributed_occurrences_keeps_the_latest_snapshot_first() -> None:
    rows = [
        row(SOURCE_1, 5, last="2026-09-15"),
        row(SOURCE_2, 9, last="2026-10-06"),
        row(SOURCE_3, 2, last="2026-10-13"),
    ]
    resolved = world(rows, [record(SOURCE_1), record(SOURCE_2)]).resolve(recipe())
    assert chosen(resolved) == [(SOURCE_2, 9, "AUTO")]


def test_auto_falls_back_to_unattributed_when_the_attributed_occurrence_is_withdrawn() -> None:
    withdrawn = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=SOURCE_2,
        disclosure=disclosure_digest(CASELIST, path_of(SOURCE_2, *QX)),
        recorded_at=datetime(2026, 10, 2, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-08",
    )
    built = world([row(SOURCE_1, 5), row(SOURCE_2, 9, last="2026-10-06")], [record(SOURCE_2)])
    built.record.lines.append(withdrawn.to_line())
    assert chosen(built.resolve(recipe())) == [(SOURCE_1, 5, "AUTO")]


def test_auto_counts_a_camp_occurrence_with_its_release_record_as_attributed() -> None:
    # The 2031 release is later but has no record; the 2030 release's record says what it is.
    camp_rows = [camp_row(SOURCE_1, 5, release="2031-policy"), camp_row(SOURCE_2, 9, release="2030-policy")]
    built = world((), camp_rows=camp_rows, camp_files=[release_record(SOURCE_2, year=2030)])
    resolved = built.resolve(recipe(caselist=OPENEV))
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_2, 9, "AUTO")], ())
    assert resolved.cards[0].camp_file == release_record(SOURCE_2, year=2030)


def test_auto_takes_the_latest_camp_release_when_both_have_their_records() -> None:
    camp_rows = [camp_row(SOURCE_1, 5, release="2031-policy"), camp_row(SOURCE_2, 9, release="2030-policy")]
    records = [release_record(SOURCE_1, year=2031), release_record(SOURCE_2, year=2030)]
    resolved = world((), camp_rows=camp_rows, camp_files=records).resolve(recipe(caselist=OPENEV))
    assert chosen(resolved) == [(SOURCE_1, 5, "AUTO")]


def test_a_pin_still_reaches_an_unattributed_occurrence_auto_would_pass_over() -> None:
    rows = [row(SOURCE_1, 5, last="2026-10-06"), row(SOURCE_2, 9)]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5}
    resolved = world(rows, [record(SOURCE_2)]).resolve(recipe(pin=pin))
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_1, 5, "PINNED")], ())


# ------------------------------------------------------------------------------------------------
# ac9: a hold stops an occurrence, by AUTO or by a pin, before a rebuild
# ------------------------------------------------------------------------------------------------


def test_auto_passes_over_an_occurrence_at_a_held_path_and_takes_the_next() -> None:
    rows = [row(SOURCE_1, 5, last="2026-10-06"), row(SOURCE_2, 9, team=ZALU)]
    records = [record(SOURCE_1, snapshot="2026-10-06"), record(SOURCE_2, team=ZALU)]
    resolved = world(rows, records, holds=[hold_on(QX, SOURCE_1)]).resolve(recipe())
    assert (chosen(resolved), resolved.errors) == ([(SOURCE_2, 9, "AUTO")], ())


def test_auto_with_every_occurrence_held_reports_suppressed_occurrence() -> None:
    rows = [row(SOURCE_1, 5, last="2026-10-06")]
    resolved = world(rows, [record(SOURCE_1, snapshot="2026-10-06")], holds=[hold_on(QX, SOURCE_1)]).resolve(
        recipe()
    )
    assert (chosen(resolved), codes(resolved)) == ([], [("SUPPRESSED_OCCURRENCE", f"{ITEM}.fingerprint")])


def test_a_pin_to_an_occurrence_at_a_held_path_is_refused_not_repointed() -> None:
    rows = [row(SOURCE_1, 5, last="2026-10-06"), row(SOURCE_2, 9, team=ZALU)]
    records = [record(SOURCE_1, snapshot="2026-10-06"), record(SOURCE_2, team=ZALU)]
    pin = {"caselist": CASELIST, "source_sha256": SOURCE_1, "element_index": 5}
    resolved = world(rows, records, holds=[hold_on(QX, SOURCE_1)]).resolve(recipe(pin=pin))
    assert (chosen(resolved), codes(resolved)) == ([], [("SUPPRESSED_OCCURRENCE", f"{ITEM}.pin")])
    assert "Maple Grove" not in resolved.errors[0].message and "QX" not in resolved.errors[0].message


def test_a_hold_dated_after_the_disclosure_does_not_stop_it() -> None:
    """A hold covers uploads in snapshots after the removed file first appeared at the path."""
    rows = [row(SOURCE_1, 5)]
    resolved = world(
        rows, [record(SOURCE_1, snapshot="2026-09-08")], holds=[hold_on(QX, SOURCE_1, after="2026-09-08")]
    )
    assert chosen(resolved.resolve(recipe())) == [(SOURCE_1, 5, "AUTO")]


def test_one_held_record_of_a_row_stops_the_row() -> None:
    """A row is one path over several weeks: a hold on any week's record of it stops the row."""
    rows = [row(SOURCE_1, 5, last="2026-09-15"), row(SOURCE_2, 9, team=ZALU)]
    records = [
        record(SOURCE_1, snapshot="2026-09-01"),
        record(SOURCE_1, snapshot="2026-09-15"),
        record(SOURCE_2, team=ZALU),
    ]
    resolved = world(rows, records, holds=[hold_on(QX, SOURCE_1, after="2026-09-08")]).resolve(recipe())
    assert chosen(resolved) == [(SOURCE_2, 9, "AUTO")]


def test_the_resolver_asks_stored_row_hold_for_each_record_of_a_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Through the publisher's one rule, not a copy of it: the question is asked of that function."""
    asked: list[tuple[str, str, str, str]] = []
    rule = publish_plan.stored_row_hold

    def recording(
        caselist: str, snapshot: str, digest: str, path: str, suppression: SuppressionState
    ) -> PathHoldEntry | None:
        asked.append((caselist, snapshot, digest, path))
        return rule(caselist, snapshot, digest, path, suppression)

    monkeypatch.setattr(file_recipes, "stored_row_hold", recording, raising=False)
    rows = [row(SOURCE_1, 5)]
    records = [record(SOURCE_1, snapshot="2026-09-01"), record(SOURCE_1, snapshot="2026-09-08")]
    resolved = world(rows, records).resolve(recipe())
    assert chosen(resolved) == [(SOURCE_1, 5, "AUTO")]
    path = path_of(SOURCE_1, *QX)
    assert sorted(asked) == [
        (CASELIST, "2026-09-01", SOURCE_1, path),
        (CASELIST, "2026-09-08", SOURCE_1, path),
    ]


# ------------------------------------------------------------------------------------------------
# ac7: t01's guide states the rule
# ------------------------------------------------------------------------------------------------

GUIDE = Path(__file__).resolve().parents[4] / "docs" / "guides" / "file-recipes.md"


def test_the_guide_puts_an_attributed_occurrence_first_in_the_auto_order() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    section = guide.split("### Unpinned: chosen for you (AUTO)", 1)[1].split("###", 1)[0]
    steps = re.findall(r"^\d\. (.+?)(?=^\d\. |^\n)", section, flags=re.MULTILINE | re.DOTALL)
    assert len(steps) == 5
    assert steps[0].startswith("an **attributed** occurrence before an unattributed one")
    assert "release is on record" in steps[0]
    assert "**latest snapshot**" in steps[1]
    assert "names every card that was resolved to one before it builds" in section
