"""FileSuggestService: a draft recipe from the landscape's most-read cards for a position (`v1-e33-t03` ac3).

The world is planted by hand under `tmp_path`, in the shapes `caselist parse` and the importer
write (:class:`~debate_core.testing.landscape_store.PlantedCaselist`): weekly manifests, the parsed
store with its occurrence table, `config/landscape/` beside it, and the caselist records that say who
disclosed each file. The landscape is the real run service, dry, with no model.

## The caselist, `synthfile26`, by hand

Five neg files, every card under `1NC` and then the heading below. Each card is three paragraphs, so
card `n` of a file starts at paragraph `3n`.

| File | Disclosed | By | Cards (heading: card) |
|---|---|---|---|
| `alpha` | 09-15 | Maple Grove QX **and** Cedar Hollow ZaLu (one file) | Politics DA: capital, drain |
| `bravo` | 09-08 | Northgate BeCo | Politics DA: capital; Politics Links: drain |
| `charlie` | 09-08 | Westfield XY | Politics Links: drain, agenda |
| `delta` | 09-08 | Riverbend MnPr | Politics DA: capital |
| `echo` | 09-08 | Lakeside RQ | Politics DA: capital |

`politics da` and `politics links` are both aliases of `politics-da`, so every card reads it. Teams:

* `capital`: QX, ZaLu, BeCo, MnPr, RQ = **5**, every copy under `politics da`;
* `drain`: QX, ZaLu, BeCo, XY = **4**; one copy under `politics da` (alpha), two under
  `politics links` (bravo, charlie), so its block is `politics links`;
* `agenda`: XY = **1**, under `politics links`.

So the draft holds two blocks: `politics da` with `capital`, then `politics links` with `drain` and
`agenda`, in that order. AUTO puts `capital` and `drain` in `alpha`, the only file seen in 09-15, and
alpha's bytes are disclosed by two teams, so each pin names the team it means; `agenda` is only in
`charlie`, whose pin needs nothing but its key. Every school and team code here is invented.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

import jsonschema
import pytest
import yaml

from debate_core.application.caselist.evidence_listing import LocalEvidence
from debate_core.application.caselist.suppression import RecordedSuppressionList
from debate_core.application.file_recipes import RecipeResolver, load_recipe
from debate_core.application.file_suggest_service import (
    FileSuggestService,
    SuggestRefused,
    SuggestRequest,
    SuggestResult,
)
from debate_core.application.landscape_run import LandscapeRunRequest, LandscapeRunService
from debate_core.application.landscape_scan import ScanAcceptanceLog
from debate_core.application.ports.parsed_store import OCCURRENCES_NAME, PARSED_PREFIX, OccurrenceRecord
from debate_core.application.ports.suppression import disclosure_digest
from debate_core.domain.caselist import Disclosure, Event, RoundLabel, Side
from debate_core.evidence.fingerprints import FINGERPRINT_VERSION
from debate_core.integrations.landscape.classification_store import LocalClassificationStore
from debate_core.integrations.landscape.yaml_taxonomy_repository import YamlTaxonomyRepository
from debate_core.integrations.local import BLOB_DIRECTORY, FsEvidenceObjectStore
from debate_core.integrations.local.parsed_store import LocalParsedStore
from debate_core.integrations.local.suppression_list import local_suppression_list_file
from debate_core.testing.fakes.caselist import InMemoryCaselistRepository
from debate_core.testing.landscape_store import PARSER_VERSION, PROFILE_VERSION, PlantedCard, PlantedCaselist

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
SCHEMA: Final = REPO_ROOT / "docs" / "data" / "file-recipe.schema.json"

CASELIST: Final = "synthfile26"
TOPIC: Final = "policy-synthetic-files"
TODAY: Final = date(2026, 9, 17)

TOPICS: Final = f"""\
schema_version: 1
topics:
  - id: {TOPIC}
    event: POLICY
    taxonomy_version: 1.0.0
    caselists:
      - {{caselist: {CASELIST}, from: 2026-09-01, to: 2026-12-31}}
"""

TAXONOMY: Final = f"""\
schema_version: 1
topic_id: {TOPIC}
taxonomy_version: 1.0.0
event: POLICY
positions:
  - {{id: politics-da, label: Politics DA, kind: da, side: neg, aliases: [politics da, politics links]}}
  - {{id: states-cp, label: States CP, kind: cp, side: neg, aliases: [states cp]}}
  - {{id: framing, label: Framing, kind: theory, side: both, aliases: [framing]}}
"""

#: Each card by name: its tag, cite and cluster. Copies of one card share all three.
CARDS: Final = {
    "capital": ("Political capital is finite", "Okafor 26", "capital"),
    "drain": ("The plan drains capital", "Lindgren 25", "drain"),
    "agenda": ("Losing hurts the agenda", "Mbatha 26", "agenda"),
}


@dataclass(frozen=True, slots=True)
class Team:
    school: str
    code: str
    round: str = "Round 1"

    def path(self, name: str) -> str:
        named = f"{self.school}-{self.code}-Neg-Lantern Classic-{self.round}-{name}.docx"
        return f"{self.school}/{self.code}/{named}"


QX, ZALU, BECO = Team("Maple Grove", "QX"), Team("Cedar Hollow", "ZaLu"), Team("Northgate", "BeCo")
XY, MNPR, RQ = Team("Westfield", "XY"), Team("Riverbend", "MnPr"), Team("Lakeside", "RQ")

#: (file, snapshot, teams disclosing it, cards as (heading, card name)).
FILES: Final[tuple[tuple[str, str, tuple[Team, ...], tuple[tuple[str, str], ...]], ...]] = (
    ("alpha", "2026-09-15", (QX, ZALU), (("Politics DA", "capital"), ("Politics DA", "drain"))),
    ("bravo", "2026-09-08", (BECO,), (("Politics DA", "capital"), ("Politics Links", "drain"))),
    ("charlie", "2026-09-08", (XY,), (("Politics Links", "drain"), ("Politics Links", "agenda"))),
    ("delta", "2026-09-08", (MNPR,), (("Politics DA", "capital"),)),
    ("echo", "2026-09-08", (RQ,), (("Politics DA", "capital"),)),
)


def fingerprint_of(card: str) -> str:
    tag, cite, _ = CARDS[card]
    return hashlib.sha256(f"{tag}|{cite}".encode()).hexdigest()


@dataclass
class World:
    root: Path
    data_dir: Path
    config_dir: Path
    digests: dict[str, str]
    caselists: InMemoryCaselistRepository

    @property
    def files_dir(self) -> Path:
        return self.root / "files"

    def landscape(self) -> LandscapeRunService:
        objects = FsEvidenceObjectStore(self.data_dir)
        blobs = FsEvidenceObjectStore(self.data_dir, subdirectory=BLOB_DIRECTORY.parent)
        return LandscapeRunService(
            taxonomies=YamlTaxonomyRepository.load(self.config_dir),
            config_dir=self.config_dir,
            parsed_store=LocalParsedStore(self.data_dir),
            local=LocalEvidence(
                objects=objects, blobs=blobs, object_path_for=objects.path_for, blob_path_for=blobs.path_for
            ),
            suppression=self.suppression(),
            classifications=LocalClassificationStore(self.data_dir),
            objects=objects,
            run_log=None,
            reports_dir=self.data_dir / "reports" / "landscape",
            acceptances=ScanAcceptanceLog(self.data_dir / "landscape" / "scan-acceptances"),
            today=lambda: TODAY,
        )

    def suppression(self) -> RecordedSuppressionList:
        return RecordedSuppressionList(local_suppression_list_file(self.data_dir))

    def service(self) -> FileSuggestService:
        return FileSuggestService(
            landscape=self.landscape(),
            parsed_store=LocalParsedStore(self.data_dir),
            caselists=self.caselists,
            suppression=self.suppression(),
            parser_version=PARSER_VERSION,
            files_dir=self.files_dir,
        )

    def suggest(self, **request: Any) -> SuggestResult:
        return asyncio.run(self.service().suggest(SuggestRequest(caselist=CASELIST, **request)))


def plant(
    root: Path,
    *,
    on_record: Sequence[Team] = (QX, ZALU, BECO, XY, MNPR, RQ),
    files: Sequence[tuple[str, str, tuple[Team, ...], tuple[tuple[str, str], ...]]] = FILES,
) -> World:
    """The table above under `root`. Only the teams in `on_record` have their disclosures recorded."""
    data_dir = root / "data"
    store = PlantedCaselist(data_dir, CASELIST)
    caselists = InMemoryCaselistRepository()
    digests: dict[str, str] = {}
    rows: list[OccurrenceRecord] = []
    for name, snapshot, teams, cards in files:
        digest = store.source(
            name,
            [
                PlantedCard(("1NC", heading), tag=CARDS[card][0], short_cite=CARDS[card][1])
                for heading, card in cards
            ],
            disclosures=[(snapshot, team.path(name)) for team in teams],
        )
        digests[name] = digest
        for team in teams:
            if team in on_record:
                asyncio.run(caselists.record_disclosure(_disclosure(digest, snapshot, team, name)))
            for index, (_, card) in enumerate(cards):
                rows.append(_row(digest, snapshot, team.path(name), index, card))
    table = data_dir / PARSED_PREFIX / CASELIST / PARSER_VERSION / OCCURRENCES_NAME
    table.write_text("".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8")
    config_dir = root / "config"
    (config_dir / "taxonomies").mkdir(parents=True)
    (config_dir / "topics.yaml").write_text(TOPICS, encoding="utf-8")
    (config_dir / "taxonomies" / f"{TOPIC}.yaml").write_text(TAXONOMY, encoding="utf-8")
    return World(root=root, data_dir=data_dir, config_dir=config_dir, digests=digests, caselists=caselists)


def _disclosure(digest: str, snapshot: str, team: Team, name: str) -> Disclosure:
    return Disclosure(
        source_sha256=digest,
        caselist=CASELIST,
        snapshot=date.fromisoformat(snapshot),
        event=Event.POLICY,
        school=team.school,
        team_code=team.code,
        side=Side.NEG,
        tournament="Lantern Classic",
        round_label=RoundLabel.from_raw(team.round),
        source_path=team.path(name),
    )


def _row(digest: str, snapshot: str, path: str, index: int, card: str) -> OccurrenceRecord:
    return OccurrenceRecord.model_validate(
        {
            "caselist": CASELIST,
            "snapshot": snapshot,
            "last_snapshot": snapshot,
            "source_sha256": digest,
            "parser_version": PARSER_VERSION,
            "profile_version": PROFILE_VERSION,
            "fingerprint_version": FINGERPRINT_VERSION,
            "disclosure": disclosure_digest(CASELIST, path),
            "first_element_index": index * 3,
            "last_element_index": index * 3 + 2,
            "exact_fingerprint": fingerprint_of(card),
            "cluster_id": hashlib.sha256(CARDS[card][2].encode()).hexdigest(),
            "membership": "NEAR_DUPLICATE",
            "completeness": "FULL",
        }
    )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return plant(tmp_path)


def items_of(text: str) -> list[tuple[str, list[dict[str, Any]]]]:
    """Each block's heading and items, in file order."""
    document = yaml.safe_load(text)
    (pocket,) = document["structure"]
    return [(block["block"], block["items"]) for block in pocket["blocks"]]


def lower_digest_team(name: str, *teams: Team) -> Team:
    """Of two disclosures of one file, the one AUTO takes when all else ties: the lowest disclosure digest."""
    return min(teams, key=lambda team: disclosure_digest(CASELIST, team.path(name)))


# ------------------------------------------------------------------------------------------------
# ac3: the draft validates, pins every card to an existing occurrence, orders cards by read count
# ------------------------------------------------------------------------------------------------


def test_the_draft_holds_the_positions_most_read_cards_grouped_by_their_commonest_heading(
    world: World,
) -> None:
    result = world.suggest(position="politics-da", top=10)
    text = result.path.read_text(encoding="utf-8")

    assert [(block, [item["fingerprint"] for item in items]) for block, items in items_of(text)] == [
        ("politics da", [fingerprint_of("capital")]),
        ("politics links", [fingerprint_of("drain"), fingerprint_of("agenda")]),
    ]
    assert [(card.rank, card.teams_reading) for card in result.cards] == [(1, 5), (2, 4), (3, 1)]


def test_the_draft_is_a_draft_with_one_pocket_for_the_position(world: World) -> None:
    document = yaml.safe_load(world.suggest(position="politics-da").path.read_text(encoding="utf-8"))
    assert document["status"] == "draft"
    assert (document["caselist"], document["topic"], document["position"]) == (CASELIST, TOPIC, "politics-da")
    assert (document["format"], document["side"], document["fingerprint_version"]) == (
        "POLICY",
        "NEG",
        FINGERPRINT_VERSION,
    )
    assert [pocket["pocket"] for pocket in document["structure"]] == ["Politics DA"]


def test_the_draft_validates_against_the_published_schema_and_loads(world: World) -> None:
    text = world.suggest(position="politics-da").path.read_text(encoding="utf-8")
    schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(yaml.safe_load(text), schema)
    loaded = load_recipe(text)
    assert loaded.ok, loaded.errors


def test_every_pin_resolves_to_an_existing_occurrence(world: World) -> None:
    text = world.suggest(position="politics-da").path.read_text(encoding="utf-8")
    loaded = load_recipe(text)
    assert loaded.recipe is not None
    resolver = RecipeResolver(
        parsed_store=LocalParsedStore(world.data_dir),
        caselists=world.caselists,
        suppression=world.suppression(),
        parser_version=PARSER_VERSION,
    )
    resolved = asyncio.run(resolver.resolve(loaded.recipe, lines=loaded.lines))
    assert resolved.errors == ()
    assert [str(card.resolution) for card in resolved.cards] == ["PINNED"] * 3
    assert [
        (card.occurrence.source_sha256, card.occurrence.first_element_index) for card in resolved.cards
    ] == [
        (world.digests["alpha"], 0),
        (world.digests["alpha"], 3),
        (world.digests["charlie"], 3),
    ]


def test_a_pin_names_the_team_only_where_two_teams_disclosed_the_same_bytes(world: World) -> None:
    text = world.suggest(position="politics-da").path.read_text(encoding="utf-8")
    pins = [item["pin"] for _, items in items_of(text) for item in items]
    chosen = lower_digest_team("alpha", QX, ZALU)
    # Both of alpha's teams were Neg in Round 1 of the Lantern Classic, so side, tournament and round
    # are added and do not tell them apart; the school and team code, added last, do.
    alpha = {
        "caselist": CASELIST,
        "source_sha256": world.digests["alpha"],
        "side": "NEG",
        "tournament": "Lantern Classic",
        "round": "Round 1",
        "school": chosen.school,
        "team_code": chosen.code,
    }
    assert pins == [
        {**alpha, "element_index": 0},
        {**alpha, "element_index": 3},
        {"caselist": CASELIST, "source_sha256": world.digests["charlie"], "element_index": 3},
    ]


def test_a_pin_names_no_team_when_the_round_tells_two_disclosures_apart(tmp_path: Path) -> None:
    """With ZaLu's copy of alpha read in Round 2, side and tournament tie, and the round settles it."""
    zalu_r2 = Team("Cedar Hollow", "ZaLu", "Round 2")
    files = ((FILES[0][0], FILES[0][1], (QX, zalu_r2), FILES[0][3]), *FILES[1:])
    built = plant(tmp_path, on_record=(QX, zalu_r2, BECO, XY, MNPR, RQ), files=files)
    text = built.suggest(position="politics-da").path.read_text(encoding="utf-8")
    chosen = lower_digest_team("alpha", QX, zalu_r2)
    (first, *_) = [item["pin"] for _, items in items_of(text) for item in items]
    assert first == {
        "caselist": CASELIST,
        "source_sha256": built.digests["alpha"],
        "element_index": 0,
        "side": "NEG",
        "tournament": "Lantern Classic",
        "round": chosen.round,
    }
    assert "Maple Grove" not in text and "Cedar Hollow" not in text and "ZaLu" not in text


def test_top_n_keeps_the_n_most_read(world: World) -> None:
    result = world.suggest(position="politics-da", top=2)
    text = result.path.read_text(encoding="utf-8")
    assert [item["fingerprint"] for _, items in items_of(text) for item in items] == [
        fingerprint_of("capital"),
        fingerprint_of("drain"),
    ]


def test_read_counts_are_yaml_comments_above_each_card(world: World) -> None:
    lines = world.suggest(position="politics-da").path.read_text(encoding="utf-8").splitlines()
    fingerprints = [index for index, line in enumerate(lines) if line.strip().startswith("- fingerprint:")]
    assert [lines[index - 1].strip() for index in fingerprints] == [
        "# rank 1: read by 5 teams through 2026-09-15",
        "# rank 2: read by 4 teams through 2026-09-15",
        "# rank 3: read by 1 team through 2026-09-15",
    ]


def test_the_draft_holds_no_tag_override_and_no_card_text(world: World) -> None:
    text = world.suggest(position="politics-da").path.read_text(encoding="utf-8")
    assert "tag_override" not in text
    for tag, cite, _ in CARDS.values():
        assert tag not in text and cite not in text
    for team in (QX, ZALU, BECO, XY, MNPR, RQ):
        assert team.path("alpha") not in text


def test_no_school_or_team_is_named_where_a_pin_does_not_need_one(world: World) -> None:
    text = world.suggest(position="politics-da").path.read_text(encoding="utf-8")
    for team in (BECO, XY, MNPR, RQ):
        assert team.school not in text and team.code not in text


def test_auto_prefers_an_attributed_occurrence_when_it_pins(tmp_path: Path) -> None:
    """With alpha's disclosures not on record, `capital` is pinned to an attributed 09-08 copy instead."""
    built = plant(tmp_path, on_record=(BECO, XY, MNPR, RQ))
    text = built.suggest(position="politics-da").path.read_text(encoding="utf-8")
    pins = {item["fingerprint"]: item["pin"] for _, items in items_of(text) for item in items}
    expected = min(built.digests[name] for name in ("bravo", "delta", "echo"))
    assert pins[fingerprint_of("capital")]["source_sha256"] == expected
    assert "Maple Grove" not in text and "Cedar Hollow" not in text


# ------------------------------------------------------------------------------------------------
# Where the draft goes, and what is refused
# ------------------------------------------------------------------------------------------------


def test_the_draft_goes_to_the_recipes_directory_by_default(world: World) -> None:
    result = world.suggest(position="politics-da")
    assert result.path == world.files_dir / "recipes" / TOPIC / "politics-da-neg-draft.yaml"


def test_an_existing_draft_is_not_overwritten(world: World) -> None:
    first = world.suggest(position="politics-da")
    first.path.write_text("# the coach's edits\n", encoding="utf-8")
    with pytest.raises(SuggestRefused, match="already"):
        world.suggest(position="politics-da")
    assert first.path.read_text(encoding="utf-8") == "# the coach's edits\n"


def test_a_draft_inside_a_git_working_tree_is_refused(world: World, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    with pytest.raises(SuggestRefused, match="git working tree"):
        world.suggest(position="politics-da", out=checkout / "draft.yaml")
    assert not (checkout / "draft.yaml").exists()


def test_an_unknown_position_is_refused_naming_the_known_ones(world: World) -> None:
    with pytest.raises(SuggestRefused) as refused:
        world.suggest(position="spending-da")
    assert refused.value.known == ("framing", "politics-da", "states-cp")


def test_a_position_both_sides_read_needs_a_side(world: World) -> None:
    with pytest.raises(SuggestRefused, match="--side"):
        world.suggest(position="framing")


def test_a_position_no_team_read_has_nothing_to_suggest(world: World) -> None:
    with pytest.raises(SuggestRefused, match="no card"):
        world.suggest(position="states-cp")


def test_the_landscape_run_writes_nothing(world: World) -> None:
    before = sorted(path for path in world.data_dir.rglob("*"))
    world.suggest(position="politics-da")
    assert sorted(path for path in world.data_dir.rglob("*")) == before


def test_the_ranks_and_counts_are_the_ones_the_landscape_report_lists_in_top_cards(world: World) -> None:
    """The same rows `top_cards.csv` is rendered from, asked of the run service and not of a file."""
    report = asyncio.run(
        world.landscape().run(LandscapeRunRequest(caselist=CASELIST, dry_run=True, top_cards=10))
    ).report
    listed = [(one.rank, one.teams_reading) for one in report.top_cards if one.position_id == "politics-da"]
    suggested = world.suggest(position="politics-da", top=10).cards
    assert sorted((one.rank, one.teams_reading) for one in suggested) == listed == [(1, 5), (2, 4), (3, 1)]
