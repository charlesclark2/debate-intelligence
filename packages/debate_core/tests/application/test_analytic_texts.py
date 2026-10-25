"""AnalyticTextService: analytic texts read from the sources' bytes, cached as derived fields (`v1-e32-t11`).

The PM's context and rulings of 2026-10-24: reuse `v1-e32-t09`'s raw re-read, in a cache of its own keyed
by source digest, parser version and the digest of the labels, rules, actors, taxonomy positions and
overrides, never text in the cache; read the texts to quote again in memory, each checked against its
digest; never read an overview again. Every source here is a synthetic `.docx` built in memory; every word
in it is invented.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from debate_core.application.analytic_texts import ANALYTIC_TEXT_SOURCE_PATH, AnalyticTextService
from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.landscape_seeding import read_seed_sources
from debate_core.arguments.landscape.analytic_texts import AnalyticTextRules, CounterplanActors
from debate_core.domain.caselist import SourceDocument
from debate_core.domain.landscape import Taxonomy, Topic
from debate_core.domain.landscape_classification import OverrideRules, PositionRole
from debate_core.domain.landscape_texts import AnalyticTextKind, TextForm, TextPlacement
from debate_core.integrations.landscape.analytic_text_store import LocalAnalyticTextStore
from debate_core.integrations.local import FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.docx_builder import build_docx, paragraph_xml, run_xml
from debate_core.testing.landscape_store import PlantedCard, PlantedCaselist

from .test_plan_texts import CASELIST, CountingParser, source_of

CP_TEXT = "The fifty states should establish a sample single payer system."
ALTERNATIVE = "The alternative is to reject sample markets in care."
ROLE = "Vote for the best sample method."
UNPLACED = "The alt is sample refusal."
THEORY = "Our counter interpretation is that we should get one sample advocacy."

CP = AnalyticTextKind.CP_TEXT
ALT = AnalyticTextKind.K_ALTERNATIVE
ROB = AnalyticTextKind.ROLE_OF_THE_BALLOT
OVERVIEW = AnalyticTextKind.OVERVIEW


def _position(identifier: str, kind: str, side: str, aliases: list[str]) -> dict[str, Any]:
    label = identifier.replace("-", " ").capitalize()
    return {"id": identifier, "label": label, "kind": kind, "side": side, "aliases": aliases}


TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            _position("sample-aff", "aff", "aff", ["sample aff"]),
            _position("states-cp", "cp", "neg", ["states cp"]),
            _position("cap-k", "k", "neg", ["cap k"]),
        ],
    }
)
OVERRIDES = OverrideRules(topic_id="policy-sample-topic")
ACTORS = CounterplanActors(topic_id="policy-sample-topic", cp_text_actors=("fifty states", "congress"))


def rules(actors: CounterplanActors | None = ACTORS) -> AnalyticTextRules:
    return AnalyticTextRules(TAXONOMY, OVERRIDES, actors)


def _card(tag: str) -> str:
    return (
        paragraph_xml(run_xml(tag), style="Heading4")
        + paragraph_xml(run_xml("Sample 26", character_style="Style13ptBold") + run_xml(" invented cite"))
        + paragraph_xml(run_xml("An invented body of evidence that goes on.", underline="single"))
    )


def negative(states_hat: str = "States CP", cp_text: str = CP_TEXT) -> bytes:
    """A States CP with its text and a theory block, a Cap K with its alt, overview and ROB, and an OFF."""
    return build_docx(
        "".join(
            [
                paragraph_xml(run_xml(states_hat), style="Heading2"),
                paragraph_xml(run_xml(cp_text), style="Analytic"),
                paragraph_xml(run_xml("Theory"), style="Heading3"),
                paragraph_xml(run_xml(THEORY), style="Analytic"),
                paragraph_xml(run_xml("Cap K"), style="Heading2"),
                _card(ALTERNATIVE),
                paragraph_xml(run_xml("Overview"), style="Heading3"),
                paragraph_xml(run_xml("Role of the ballot"), style="Heading3"),
                paragraph_xml(run_xml(ROLE), style="Analytic"),
                paragraph_xml(run_xml("OFF"), style="Heading2"),
                _card(UNPLACED),
            ]
        )
    )


def nothing_placed() -> bytes:
    return build_docx(paragraph_xml(run_xml("OFF"), style="Heading2") + _card(UNPLACED))


@dataclass
class World:
    data_dir: Path
    parser: CountingParser = field(default_factory=CountingParser)

    def plant(self, content: bytes, *, blob: bytes | None = None) -> SourceDocument:
        source = source_of(content)
        sha = source.sha256
        path = self.data_dir / "blobs" / "sha256" / sha[:2] / sha[2:4] / sha
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if blob is None else blob)
        return source

    @property
    def cache_file(self) -> Path:
        return self.data_dir / "landscape" / "analytic_texts" / f"{CASELIST}.jsonl"

    def files(self) -> list[tuple[Path, bytes]]:
        return sorted((path, path.read_bytes()) for path in self.data_dir.rglob("*") if path.is_file())

    def service(self) -> AnalyticTextService:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=Path("blobs"))
        return AnalyticTextService(
            parser=self.parser,
            runner=InProcessParseRunner(),
            store=LocalAnalyticTextStore(self.data_dir),
            local=LocalEvidence(
                objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
            ),
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def _found(run: Any, sha: str) -> list[tuple[AnalyticTextKind, TextForm, TextPlacement, str | None]]:
    return [(one.kind, one.form, one.placement, one.position_id) for one in run.readings[sha]]


@pytest.mark.anyio
async def test_a_sources_texts_are_read_from_its_bytes_and_placed(world: World) -> None:
    source = world.plant(negative())
    run = await world.service().read(CASELIST, [source], rules())
    assert _found(run, source.sha256) == [
        (CP, TextForm.BY_PLACE, TextPlacement.PLACED, "states-cp"),
        (ALT, TextForm.SENTENCE, TextPlacement.PLACED, "cap-k"),
        (OVERVIEW, TextForm.LABEL, TextPlacement.PLACED, "cap-k"),
        (ROB, TextForm.LABEL, TextPlacement.PLACED, "cap-k"),
        (ALT, TextForm.SENTENCE, TextPlacement.NO_HEADING, None),
    ]
    assert all(one.role in (PositionRole.READS, None) for one in run.readings[source.sha256])
    assert run.refused_by_guard == {source.sha256: 1}
    counts = run.counts
    assert (counts.sources, counts.hits, counts.parsed, counts.refused, counts.unread) == (1, 0, 1, 0, 0)
    assert counts.readings == {"CP_TEXT": 1, "K_ALTERNATIVE": 2, "OVERVIEW": 1, "ROLE_OF_THE_BALLOT": 1}
    assert counts.placed == {"CP_TEXT": 1, "K_ALTERNATIVE": 1, "OVERVIEW": 1, "ROLE_OF_THE_BALLOT": 1}
    assert (counts.refused_by_guard, counts.cache_written) == (1, True)


@pytest.mark.anyio
async def test_a_second_run_parses_nothing_and_writes_nothing(world: World) -> None:
    sources = [world.plant(negative()), world.plant(nothing_placed())]
    first = await world.service().read(CASELIST, sources, rules())
    written = world.cache_file.read_bytes()
    calls = len(world.parser.paths)
    again = await world.service().read(CASELIST, sources, rules())
    assert len(world.parser.paths) == calls
    assert (again.counts.hits, again.counts.parsed, again.counts.cache_written) == (2, 0, False)
    assert (again.readings, again.refused_by_guard) == (first.readings, first.refused_by_guard)
    assert world.cache_file.read_bytes() == written


@pytest.mark.anyio
async def test_new_actors_read_every_source_again_and_drop_the_old_readings(world: World) -> None:
    source = world.plant(negative(cp_text="Congress should establish a sample payment cap."))
    before = await world.service().read(
        CASELIST,
        [source],
        rules(CounterplanActors(topic_id="policy-sample-topic", cp_text_actors=("fifty states",))),
    )
    after = await world.service().read(CASELIST, [source], rules())
    assert CP not in {one.kind for one in before.readings[source.sha256]}
    assert CP in {one.kind for one in after.readings[source.sha256]}
    assert (after.counts.hits, after.counts.parsed) == (0, 1)
    assert len(world.cache_file.read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.anyio
async def test_a_new_parser_version_reads_every_source_again(world: World) -> None:
    source = world.plant(negative())
    await world.service().read(CASELIST, [source], rules())
    world.parser.version = "2099.01.01-docx-99"
    again = await world.service().read(CASELIST, [source], rules())
    assert (again.counts.hits, again.counts.parsed, again.parser_version) == (0, 1, "2099.01.01-docx-99")


@pytest.mark.anyio
async def test_readings_of_sources_not_in_this_run_are_kept(world: World) -> None:
    one, two = world.plant(negative()), world.plant(nothing_placed())
    await world.service().read(CASELIST, [one, two], rules())
    await world.service().read(CASELIST, [one], rules())
    again = await world.service().read(CASELIST, [two], rules())
    assert (again.counts.hits, again.counts.parsed) == (1, 0)


@pytest.mark.anyio
async def test_a_refused_source_is_cached_as_unreadable_and_not_parsed_again(world: World) -> None:
    broken = world.plant(b"not a zip at all, invented bytes")
    run = await world.service().read(CASELIST, [broken], rules())
    assert (run.readings, run.counts.refused, run.counts.cache_written) == ({}, 1, True)
    calls = len(world.parser.paths)
    again = await world.service().read(CASELIST, [broken], rules())
    assert len(world.parser.paths) == calls
    assert (again.counts.hits, again.counts.refused) == (1, 1)


@pytest.mark.anyio
async def test_a_missing_blob_is_unread_not_cached_and_tried_again(world: World) -> None:
    content = negative()
    source = source_of(content)
    missing = await world.service().read(CASELIST, [source], rules())
    assert (missing.readings, missing.counts.unread, missing.counts.cache_written) == ({}, 1, False)
    world.plant(content)
    found = await world.service().read(CASELIST, [source], rules())
    assert found.counts.parsed == 1 and source.sha256 in found.readings


@pytest.mark.anyio
async def test_the_parser_never_gets_a_disclosure_path(world: World) -> None:
    await world.service().read(CASELIST, [world.plant(negative())], rules())
    assert world.parser.paths == [ANALYTIC_TEXT_SOURCE_PATH]


@pytest.mark.anyio
async def test_the_cache_holds_no_word_of_any_source(world: World) -> None:
    await world.service().read(CASELIST, [world.plant(negative()), world.plant(nothing_placed())], rules())
    written = world.cache_file.read_text(encoding="utf-8").casefold()
    for words in (
        "fifty states",
        "sample markets",
        "sample method",
        "counter interpretation",
        "refusal",
        "invented",
    ):
        assert words not in written


@pytest.mark.anyio
async def test_the_teams_own_names_are_taken_out_before_a_heading_is_placed(world: World) -> None:
    source = world.plant(negative(states_hat="Riverside RS States CP"))
    without = await world.service().read(CASELIST, [source], rules())
    assert ("states-cp" in {one.position_id for one in without.readings[source.sha256]}) is False
    world.cache_file.unlink()
    named = await world.service().read(
        CASELIST, [source], rules(), own_names={source.sha256: ("Riverside", "RS")}
    )
    assert "states-cp" in {one.position_id for one in named.readings[source.sha256]}


@pytest.mark.anyio
async def test_a_dry_run_view_reads_and_never_writes_the_cache(world: World) -> None:
    source = world.plant(negative())
    run = await world.service().without_writes().read(CASELIST, [source], rules())
    assert (run.counts.parsed, run.counts.cache_written) == (1, False)
    assert not world.cache_file.exists()


# ------------------------------------------------------------------------------------------------
# Reading the texts to quote again
# ------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_only_sources_with_a_placed_text_to_quote_are_read_again_and_word_for_word(
    world: World,
) -> None:
    placed, unplaced = world.plant(negative()), world.plant(nothing_placed())
    service = world.service()
    run = await service.read(CASELIST, [placed, unplaced], rules())
    calls = len(world.parser.paths)
    quoted = await service.quote(CASELIST, [placed, unplaced], run, TAXONOMY)
    assert len(world.parser.paths) == calls + 1
    assert sorted(quoted.texts.values()) == sorted([CP_TEXT, ALTERNATIVE, ROLE])
    assert {sha for sha, _ in quoted.texts} == {placed.sha256}
    assert (quoted.sources, quoted.wanted, quoted.mismatched, quoted.unread) == (1, 3, 0, 0)


@pytest.mark.anyio
async def test_a_text_that_reads_differently_from_its_reading_is_not_quoted(world: World) -> None:
    source = world.plant(negative())
    service = world.service()
    run = await service.read(CASELIST, [source], rules())
    changed = dataclasses.replace(
        run,
        readings={
            source.sha256: tuple(
                one.model_copy(update={"digest": "0" * 64}) if one.kind is ALT and one.position_id else one
                for one in run.readings[source.sha256]
            )
        },
    )
    quoted = await service.quote(CASELIST, [source], changed, TAXONOMY)
    assert ALTERNATIVE not in quoted.texts.values()
    assert (quoted.wanted, quoted.mismatched) == (3, 1)


@pytest.mark.anyio
async def test_reading_the_texts_again_writes_nothing(world: World) -> None:
    source = world.plant(negative())
    service = world.service()
    run = await service.read(CASELIST, [source], rules())
    before = world.files()
    await service.quote(CASELIST, [source], run, TAXONOMY)
    assert world.files() == before


# ------------------------------------------------------------------------------------------------
# The landscape run's seam
# ------------------------------------------------------------------------------------------------

SEAM_CASELIST = "hspolicy98"
TOPIC = Topic.model_validate(
    {
        "id": "policy-sample-topic",
        "event": "POLICY",
        "taxonomy_version": "1.0.0",
        "caselists": [{"caselist": SEAM_CASELIST, "from": "2026-07-01", "to": "2027-06-30"}],
    }
)


def _path(school: str, side: str, number: int) -> str:
    file = f"School {school}-Code{school}-{side}-Sample Invitational-Round {number}.docx"
    return f"School {school}/Code{school}/{file}"


async def _seam_reading(data_dir: Path) -> tuple[Any, LocalEvidence]:
    store = PlantedCaselist(data_dir, SEAM_CASELIST)
    store.source(
        "neg-one",
        [PlantedCard(("States CP",))],
        disclosures=[("2026-09-15", _path("One", "Neg", 1))],
        content=negative(states_hat="School One States CP"),
    )
    store.source(
        "neg-two",
        [PlantedCard(("OFF",))],
        disclosures=[("2026-09-15", _path("Two", "Neg", 2))],
        content=nothing_placed(),
    )
    objects = FsEvidenceObjectStore(data_dir)
    blobs = FsEvidenceObjectStore(data_dir, subdirectory=Path("blobs"))
    local = LocalEvidence(
        objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
    )
    reading = await read_seed_sources(
        store=LocalParsedStore(data_dir),
        local=local,
        suppression=RecordedSuppressionList(local_suppression_list_file(data_dir)),
        topic=TOPIC,
        caselist=SEAM_CASELIST,
        through=date(2026, 9, 29),
    )
    return reading, local


def _seam_service(data_dir: Path, local: LocalEvidence, parser: CountingParser) -> AnalyticTextService:
    return AnalyticTextService(
        parser=parser, runner=InProcessParseRunner(), store=LocalAnalyticTextStore(data_dir), local=local
    )


@pytest.mark.anyio
async def test_the_seam_gives_the_report_its_readings_texts_schools_and_guard_counts(tmp_path: Path) -> None:
    reading, local = await _seam_reading(tmp_path)
    found = await _seam_service(tmp_path, local, CountingParser()).report_inputs(
        reading=reading, taxonomy=TAXONOMY, overrides=OVERRIDES, actors=ACTORS, writes=True
    )
    inputs = found.inputs
    assert len(inputs.readings) == 2
    # The disclosing team's own school is taken out of `School One States CP`, so the CP is placed.
    assert sorted(inputs.texts.values()) == sorted([CP_TEXT, ALTERNATIVE, ROLE])
    assert dict(inputs.caselist_names) == dict(reading.caselist_names)
    assert sum(inputs.refused_by_guard.values()) == 1
    assert (found.read.sources, found.read.parsed, found.read.cache_written) == (2, 2, True)
    assert (found.quoted.sources, found.quoted.wanted) == (1, 3)


@pytest.mark.anyio
async def test_the_seam_in_a_dry_run_writes_no_cache(tmp_path: Path) -> None:
    reading, local = await _seam_reading(tmp_path)
    before = sorted(path for path in tmp_path.rglob("*") if path.is_file())
    found = await _seam_service(tmp_path, local, CountingParser()).report_inputs(
        reading=reading, taxonomy=TAXONOMY, overrides=OVERRIDES, actors=ACTORS, writes=False
    )
    assert found.read.cache_written is False
    assert sorted(path for path in tmp_path.rglob("*") if path.is_file()) == before


# ------------------------------------------------------------------------------------------------
# A CP's planks (v1-e32-t16): read, cached with their counts, and read again to quote
# ------------------------------------------------------------------------------------------------

PLANK_TAXONOMY = Taxonomy.model_validate(
    {
        "topic_id": "policy-sample-topic",
        "taxonomy_version": "1.0.0",
        "event": "POLICY",
        "positions": [
            _position("states-cp", "cp", "neg", ["states cp"]),
            _position("advantage-cp", "cp", "neg", ["advantage cp"]),
            _position("costs-advantage", "advantage", "aff", ["costs"]),
        ],
    }
)
PLANK = AnalyticTextKind.CP_PLANK


def with_planks() -> bytes:
    """An advantage CP listing two planks after a label, and a States CP whose labelled text has no actor."""
    return build_docx(
        "".join(
            [
                paragraph_xml(run_xml("Advantage CP"), style="Heading2"),
                paragraph_xml(run_xml("The fifty states should:"), style="Analytic"),
                paragraph_xml(run_xml("Costs"), style="Analytic"),
                paragraph_xml(run_xml("Expand sample clinics."), style="Analytic"),
                paragraph_xml(run_xml("Fund a sample prize."), style="Analytic"),
                _card("Sample clinics work"),
                paragraph_xml(run_xml("States CP"), style="Heading2"),
                paragraph_xml(run_xml("Text: The sample panel should:"), style="Analytic"),
                paragraph_xml(run_xml("Ban sample surprise bills."), style="Analytic"),
            ]
        )
    )


@pytest.mark.anyio
async def test_a_sources_planks_and_their_counts_are_read_and_cached(world: World) -> None:
    source = world.plant(with_planks())
    service = world.service()
    plank_rules = AnalyticTextRules(PLANK_TAXONOMY, OVERRIDES, ACTORS)
    run = await service.read(CASELIST, [source], plank_rules)
    planks = [
        (one.form, one.position_id, one.solves) for one in run.readings[source.sha256] if one.kind is PLANK
    ]
    assert planks == [
        (TextForm.LIST, "advantage-cp", ("costs-advantage",)),
        (TextForm.LIST, "advantage-cp", ()),
    ]
    assert (run.plank_labels, run.planks_refused_by_guard) == ({source.sha256: 1}, {source.sha256: 1})
    assert (run.counts.plank_labels, run.counts.planks_refused_by_guard) == (1, 1)
    again = await service.read(CASELIST, [source], plank_rules)
    assert again.counts.parsed == 0
    assert (again.readings, again.plank_labels, again.planks_refused_by_guard) == (
        run.readings,
        run.plank_labels,
        run.planks_refused_by_guard,
    )
    quoted = await service.quote(CASELIST, [source], run, PLANK_TAXONOMY)
    assert sorted(quoted.texts.values()) == [
        "Expand sample clinics.",
        "Fund a sample prize.",
        "The fifty states should:",
        "The sample panel should:",
    ]
    # Words and counts only: no plank's words in the cache.
    held = world.cache_file.read_text(encoding="utf-8")
    assert "clinics" not in held and "prize" not in held and "surprise" not in held


@pytest.mark.anyio
async def test_the_seam_gives_the_report_the_plank_counts(tmp_path: Path) -> None:
    reading, local = await _seam_reading(tmp_path)
    found = await _seam_service(tmp_path, local, CountingParser()).report_inputs(
        reading=reading, taxonomy=TAXONOMY, overrides=OVERRIDES, actors=ACTORS, writes=True
    )
    assert (dict(found.inputs.plank_labels), dict(found.inputs.planks_refused_by_guard)) == ({}, {})
