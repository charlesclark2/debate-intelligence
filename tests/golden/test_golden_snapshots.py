"""The golden corpus's snapshot half: `record`, `check --snapshots` and `scripts/golden_snapshots.py`.

Every page, card and store here is invented and built under `tmp_path`: a real SQLite database and
filesystem blob store, filled by the platform's own `SnapshotService` exactly as
`debate-research fetch` fills the operator's, and fetch reports in the shape the fetch command's
`--json` envelope has. No test reads the operator's store, snapshot folder or fetch reports, and
no test reads git metadata outside the repository (the one test of the worktree rule makes a git
repository of its own). Every expected value is written by hand from the invented inputs (working
agreement 6): offsets by finding the invented words in the invented page, digests by `hashlib`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import golden_snapshots as snaps  # noqa: E402
import import_golden_card as golden  # noqa: E402
from tests.golden.synthetic_team_files import FILLER, SyntheticCard, coach_attests, team_file  # noqa: E402

from debate_core.application.article_fetch import FetchReport, SnapshotSummary  # noqa: E402
from debate_core.application.snapshot_service import SnapshotService  # noqa: E402
from debate_core.domain import AccessStatus, ProvenanceMode, SourceSnapshot  # noqa: E402
from debate_core.integrations.local import (  # noqa: E402
    DATABASE_FILENAME,
    FsSnapshotStore,
    SqliteArticleRepository,
    SqliteDatabase,
)
from debate_core.testing.builders import build_article, readable_id  # noqa: E402
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator  # noqa: E402

TEST_KEY = b"a test key that is not the operator's".ljust(32, b".")
IMPORTED_ON = date(2026, 11, 14)
FETCHED_AT = datetime(2026, 11, 14, 15, 30, tzinfo=UTC)
MARKERS = ("…", "...", "[…]", "[...]", "***")

#: A word only the invented page holds, outside the card: it must never reach the terminal.
SENTINEL = "Quorvexalind"

WARRANT = "the warrant the card is read for"

#: The card the corpus is built around: two paragraphs, an omission cut in the first.
CARD_BODY = (
    f"Plain words {FILLER} {{warrant}} and more … after the cut.",
    f"A second paragraph {FILLER} {{warrant}}.",
)

#: The page it was cut from, as the extractor would give it: already normalized, so the stored text
#: is this string exactly. The card skips its first and last paragraphs and, where its `…` stands,
#: the words "words the cutter skipped"; the card runs the page's second and third paragraphs
#: together as one paragraph's line break.
PAGE = (
    f"A {SENTINEL} preamble the card leaves out.\n\n"
    f"Plain words {FILLER} {WARRANT} and more words the cutter skipped after the cut.\n\n"
    f"A second paragraph {FILLER} {WARRANT}.\n\n"
    "A closing line the card leaves out."
)
PAGE_BYTES = f"<html><body><p>{PAGE}</p></body></html>".encode()

#: The card's two segments of PAGE, found by hand: from "Plain words" to "and more", and from
#: "after the cut." to the end of the third paragraph.
SEGMENTS = [
    [PAGE.index("Plain words"), PAGE.index(" words the cutter skipped")],
    [PAGE.index("after the cut."), PAGE.index("\n\nA closing line")],
]

LINKS = {
    "accessible": "https://www.brookings.edu/articles/accessible-grid",
    "paywalled": "https://www.nytimes.com/2026/01/02/us/paywalled-grid.html",
    "errored": "https://www.reuters.com/world/errored-grid",
    "unreported": "https://www.rand.org/pubs/unreported-grid.html",
    "mislinked": "https://www.cfr.org/article/mislinked-grid",
}


def run[ResultT](coroutine: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(coroutine)


# ------------------------------------------------------------------------------------------------
# Comparison form
# ------------------------------------------------------------------------------------------------


def test_comparison_form_reads_every_whitespace_gap_as_one_space() -> None:
    assert snaps.comparison_form("One  two\nthree\n\nfour ") == "One two three four"


@pytest.mark.parametrize("marker", MARKERS)
def test_the_team_card_splits_at_each_omission_marker(marker: str) -> None:
    body = f"Before the cut {marker} after the cut.\nNext paragraph."

    assert snaps.team_segments(body, MARKERS) == ["Before the cut", "after the cut. Next paragraph."]


def test_a_longer_marker_is_read_whole_not_as_the_shorter_one_inside_it() -> None:
    # "[...]" holds "...": read as "..." first, it would leave "[" and "]" in the text.
    assert snaps.team_segments("Before [...] after.", MARKERS) == ["Before", "after."]


def test_the_team_card_is_put_through_the_evidence_normalizer() -> None:
    # A no-break space and a tab are whitespace gaps; a zero-width space is removed (rule 4).
    assert snaps.team_comparison_text("One two\tthree four​five", MARKERS) == "One two three fourfive"


def test_segments_reproduce_the_card_across_a_cut_and_a_run_together_paragraph() -> None:
    evidence = "Plain words and more … after the cut.\nA second paragraph."
    page = "Plain words and more words skipped after the cut.\n\nA second paragraph.\n\nNot quoted."
    segments = [[0, len("Plain words and more")], [page.index("after"), page.index("\n\nNot")]]

    assert snaps.reproduces(page, segments, evidence, MARKERS)


@pytest.mark.parametrize(
    "evidence",
    [
        "Plain “words” stay.",  # curly quotes are not folded to straight ones
        'plain "words" stay.',  # nor is case
        'Plain "words" stay',  # nor is a full stop dropped
    ],
)
def test_nothing_but_whitespace_is_read_loosely(evidence: str) -> None:
    page = 'Plain "words" stay.'

    assert not snaps.reproduces(page, [[0, len(page)]], evidence, MARKERS)


def test_no_segments_reproduce_nothing() -> None:
    assert not snaps.reproduces("Some text.", [], "", MARKERS)


# ------------------------------------------------------------------------------------------------
# Fetch reports
# ------------------------------------------------------------------------------------------------


def _envelope(
    requested_url: str,
    status: str,
    *,
    snapshot_id: str | None = None,
    provenance: str = "PUBLISHER_RETRIEVED",
) -> dict[str, Any]:
    """The fetch command's `--json` envelope: the report under `data`, or under `error.details`."""
    report: dict[str, Any] = {
        "requested_url": requested_url,
        "canonical_url": requested_url,
        "final_url": requested_url if snapshot_id else None,
        "title": f"{SENTINEL} page title",
        "access_status": status,
        "provenance_mode": provenance if snapshot_id else None,
        "snapshot": {"snapshot_id": snapshot_id, "sha256": "0" * 64} if snapshot_id else None,
    }
    if status == "ACCESSIBLE":
        return {"ok": True, "data": report}
    return {"ok": False, "error": {"code": "SOURCE_NOT_ACCESSIBLE", "exit_code": 3, "details": report}}


def _write(path: Path, envelope: dict[str, Any] | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(envelope if isinstance(envelope, str) else json.dumps(envelope), encoding="utf-8")
    return path


def test_the_reader_uses_only_fields_the_fetch_report_has() -> None:
    # The reader is written against the fetch command's report; a renamed field would read as no report.
    assert {"requested_url", "final_url", "access_status", "provenance_mode", "snapshot"} <= set(
        FetchReport.model_fields
    )
    assert "snapshot_id" in SnapshotSummary.model_fields


LINK = "https://www.example.org/a"


@pytest.mark.parametrize(
    ("envelope", "outcome"),
    [
        (_envelope(LINK, "ACCESSIBLE", snapshot_id="snap-1"), snaps.FetchOutcome.RECORD),
        (_envelope(LINK, "PAYWALLED"), snaps.FetchOutcome.DROP),
        (_envelope(LINK, "BLOCKED"), snaps.FetchOutcome.DROP),
        (_envelope(LINK, "ROBOTS_DISALLOWED"), snaps.FetchOutcome.DROP),
        (_envelope(LINK, "NOT_FOUND"), snaps.FetchOutcome.DROP),
        (_envelope(LINK, "UNSUPPORTED_TYPE"), snaps.FetchOutcome.DROP),
        (_envelope(LINK, "ERROR"), snaps.FetchOutcome.FETCH_AGAIN),
        (
            _envelope("https://www.example.org/b", "ACCESSIBLE", snapshot_id="snap-1"),
            snaps.FetchOutcome.ANOTHER_LINK,
        ),
        (
            _envelope(LINK, "ACCESSIBLE", snapshot_id="snap-1", provenance="USER_SUPPLIED"),
            snaps.FetchOutcome.NOT_RETRIEVED,
        ),
        (
            {"ok": False, "error": {"code": "USAGE", "details": {"param": "URL"}}},
            snaps.FetchOutcome.NO_REPORT,
        ),
        ("not json at all", snaps.FetchOutcome.NO_REPORT),
    ],
)
def test_each_fetch_report_reads_as_its_outcome(
    tmp_path: Path, envelope: dict[str, Any] | str, outcome: snaps.FetchOutcome
) -> None:
    assert snaps.read_fetch_report(_write(tmp_path / "case.json", envelope), LINK).outcome is outcome


def test_a_missing_fetch_report_is_no_report(tmp_path: Path) -> None:
    assert snaps.read_fetch_report(tmp_path / "absent.json", LINK).outcome is snaps.FetchOutcome.NO_REPORT


def test_the_dropped_statuses_are_every_status_that_says_the_page_is_not_readable() -> None:
    assert (
        set(AccessStatus)
        - {
            AccessStatus.ACCESSIBLE,
            AccessStatus.ERROR,
            AccessStatus.UNKNOWN,
        }
        == snaps.ACCESS_STATUSES_DROPPED
    )


# ------------------------------------------------------------------------------------------------
# A store, a corpus and the fetch reports, all invented
# ------------------------------------------------------------------------------------------------


def _cards(names: list[str]) -> list[SyntheticCard]:
    return [
        SyntheticCard(
            tag=f"Demand growth strains the {name} reserve margin",
            short_cite="Okonkwo 26",
            cite_rest=" [Ada Okonkwo, senior analyst, 3-4-2026, {link}]",
            link=LINKS[name],
            body=list(CARD_BODY),
        )
        for name in names
    ]


@dataclass
class World:
    root: Path
    store: Path
    fetches: Path
    snapshots: Path
    fixtures: Path
    ids: SequentialIdGenerator

    def case_for(self, name: str) -> str:
        """The case ID the importer gave the card whose link is `name`'s."""
        (case,) = [c for c in golden._existing_cases(self.fixtures) if c["source_link"] == LINKS[name]]
        return case["case_id"]

    def store_page(self, url: str, page_bytes: bytes = PAGE_BYTES, text: str = PAGE) -> SourceSnapshot:
        """Store a page the way `debate-research fetch` does: an article, its snapshot, its blobs."""
        database = SqliteDatabase.open(self.store)
        try:
            articles = SqliteArticleRepository(database)
            article_id = readable_id("ART", len(self.ids_used) + 1)
            run(articles.save(build_article(article_id=article_id, canonical_url=url)))
            service = SnapshotService(
                blobs=FsSnapshotStore(self.store), clock=FixedClock(), id_generator=self.ids
            )
            snapshot = run(
                service.create(
                    article_id=article_id,
                    raw_bytes=page_bytes,
                    extracted_text=text,
                    canonical_url=url,
                    retrieved_at=FETCHED_AT,
                    extractor_version="invented-extractor/1",
                    provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
                    access_status=AccessStatus.ACCESSIBLE,
                    content_type="text/html",
                )
            )
            run(articles.save_snapshot(snapshot))
        finally:
            database.close()
        self.ids_used.append(snapshot.snapshot_id)
        return snapshot

    ids_used: list[str]

    def report(self, name: str, envelope: dict[str, Any]) -> None:
        _write(self.fetches / f"{self.case_for(name)}.json", envelope)

    def record(self, *extra: str) -> int:
        return golden.main(
            [
                "record",
                "--fetches",
                str(self.fetches),
                "--store",
                str(self.store),
                "--snapshots",
                str(self.snapshots),
                "--fixtures",
                str(self.fixtures),
                *extra,
            ]
        )

    def check(self) -> int:
        return golden.main(["check", "--fixtures", str(self.fixtures), "--snapshots", str(self.snapshots)])


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """Five invented cases, imported; a store holding the accessible one's page; and its reports.

    One case per outcome: accessible (recorded), paywalled (dropped), errored (kept, fetch again),
    no report (kept), and a report for another link (kept).
    """
    # The repository's own worktree list is git metadata outside the repository; no test reads it.
    monkeypatch.setattr(snaps, "_checkouts", lambda repository: [REPO_ROOT.resolve()])
    debate = tmp_path / "debate"
    layout = (
        ("2025-2026", "Policy", ["accessible", "paywalled"]),
        ("2024-2025", "LD", ["errored", "unreported"]),
        ("2026-2027", "PF", ["mislinked"]),
    )
    for season, event, names in layout:
        (debate / season / event).mkdir(parents=True)
        (debate / season / event / "team file.docx").write_bytes(team_file(_cards(names)))
    listing = golden.list_candidates([debate / season for season, _, _ in layout], (), TEST_KEY)
    fixtures = tmp_path / "golden_cards"
    imported, refused = golden.import_candidates(
        listing.candidates,
        [c.candidate_id for c in listing.candidates],
        golden.NO_DENYLIST,
        fixtures,
        today=IMPORTED_ON,
        attest=coach_attests,
    )
    assert (len(imported), refused) == (5, [])
    built = World(
        root=tmp_path,
        store=tmp_path / "store",
        fetches=tmp_path / "fetches",
        snapshots=tmp_path / "golden-snapshots",
        fixtures=fixtures,
        ids=SequentialIdGenerator(),
        ids_used=[],
    )
    snapshot = built.store_page(LINKS["accessible"])
    built.report("accessible", _envelope(LINKS["accessible"], "ACCESSIBLE", snapshot_id=snapshot.snapshot_id))
    built.report("paywalled", _envelope(LINKS["paywalled"], "PAYWALLED"))
    built.report("errored", _envelope(LINKS["errored"], "ERROR"))
    built.report("mislinked", _envelope(LINKS["accessible"], "ACCESSIBLE", snapshot_id=snapshot.snapshot_id))
    return built


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# ------------------------------------------------------------------------------------------------
# record
# ------------------------------------------------------------------------------------------------


def test_the_dry_run_reads_everything_and_writes_nothing(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    before = (_tree(world.fixtures), _tree(world.store))

    assert world.record() == 1  # two cases are not recorded: no report, and another link
    out = capsys.readouterr().out

    assert (_tree(world.fixtures), _tree(world.store)) == before
    assert not world.snapshots.exists()
    assert "would record: 1" in out
    assert f"would drop: 1\n  {world.case_for('paywalled')}: PAYWALLED" in out
    assert "dry run: nothing written" in out


def test_record_copies_the_accessible_snapshot_and_records_its_digests(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    case_id = world.case_for("accessible")

    world.record("--execute")
    capsys.readouterr()

    copy = world.snapshots / case_id
    assert (copy / snaps.RAW_NAME).read_bytes() == PAGE_BYTES
    document = (copy / snaps.NORMALIZED_NAME).read_bytes()
    assert json.loads(document)["text"] == PAGE
    case = json.loads((world.fixtures / case_id / golden.CASE_NAME).read_text(encoding="utf-8"))
    assert case["snapshot"] == {
        "url": LINKS["accessible"],
        "canonical_url": LINKS["accessible"],
        "final_url": LINKS["accessible"],
        "fetched_on": "2026-11-14",
        "access_status": "ACCESSIBLE",
        "provenance_mode": "PUBLISHER_RETRIEVED",
        "raw_sha256": hashlib.sha256(PAGE_BYTES).hexdigest(),
        "raw_byte_size": len(PAGE_BYTES),
        "normalized_text_sha256": hashlib.sha256(PAGE.encode()).hexdigest(),
        "normalized_document_sha256": hashlib.sha256(document).hexdigest(),
        "normalizer_version": "evidence-normalizer-v1",
        "extractor_version": "invented-extractor/1",
        "content_type": "text/html",
        "paragraph_count": 4,
    }
    assert snaps.case_structure_problems(case, case_id) == []


def test_record_drops_the_unreadable_case_and_keeps_the_ones_to_fetch_again(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    kept = {name: world.case_for(name) for name in ("errored", "unreported", "mislinked")}
    dropped = world.case_for("paywalled")

    assert world.record("--execute") == 1
    out = capsys.readouterr().out

    remaining = sorted(path.parent.name for path in world.fixtures.glob(f"*/{golden.CASE_NAME}"))
    assert remaining == sorted([world.case_for("accessible"), *kept.values()])
    assert dropped not in (world.fixtures / golden.INDEX_NAME).read_text(encoding="utf-8")
    assert "4 cases." in (world.fixtures / golden.INDEX_NAME).read_text(encoding="utf-8")
    for case_id in kept.values():
        assert "snapshot" not in json.loads((world.fixtures / case_id / golden.CASE_NAME).read_text())
    assert f"  {kept['errored']}: fetch again" in out
    assert f"  {kept['unreported']}: no fetch report" in out
    assert f"  {kept['mislinked']}: the report is for another link" in out
    assert "recorded: 1\ndropped: 1" in out


def test_record_reads_the_store_without_writing_to_it(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    database = world.store / DATABASE_FILENAME
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    blobs = _tree(world.store / "blobs")

    world.record("--execute")
    capsys.readouterr()

    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert _tree(world.store / "blobs") == blobs


def test_record_reads_a_store_a_writer_still_holds_open(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    # An open writer keeps a -wal file; the read must go through it, and still write nothing.
    writer = SqliteDatabase.open(world.store)
    try:
        assert (world.store / f"{DATABASE_FILENAME}-wal").exists()
        world.record("--execute")
    finally:
        writer.close()

    assert "recorded: 1" in capsys.readouterr().out
    assert (world.snapshots / world.case_for("accessible") / snaps.RAW_NAME).read_bytes() == PAGE_BYTES


def test_record_prints_no_page_text_title_or_link(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    world.record("--execute")
    out = capsys.readouterr()

    assert SENTINEL not in out.out + out.err
    assert not any(link in out.out + out.err for link in LINKS.values())


def test_a_snapshot_the_store_does_not_hold_is_not_recorded(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    case_id = world.case_for("accessible")
    world.report(
        "accessible", _envelope(LINKS["accessible"], "ACCESSIBLE", snapshot_id=readable_id("SNAP", 99))
    )

    assert world.record("--execute") == 1

    assert (
        f"  {case_id}: snapshot {readable_id('SNAP', 99)} cannot be loaded: NotFound"
        in capsys.readouterr().out
    )
    assert "snapshot" not in json.loads((world.fixtures / case_id / golden.CASE_NAME).read_text())


def test_a_damaged_stored_blob_is_not_recorded(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    raw = FsSnapshotStore(world.store).path_for(hashlib.sha256(PAGE_BYTES).hexdigest())
    raw.chmod(0o644)
    raw.write_bytes(PAGE_BYTES.replace(b"preamble", b"Preamble"))

    assert world.record("--execute") == 1

    assert "cannot be loaded: SnapshotIntegrityError" in capsys.readouterr().out
    assert not (world.snapshots / world.case_for("accessible")).exists()


def test_record_refuses_a_snapshot_folder_or_fetch_folder_inside_the_repository(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    inside = REPO_ROOT / "tests" / "fixtures" / "golden_cards" / "snapshots-here"
    assert (
        golden.main(
            [
                "record",
                "--fetches",
                str(world.fetches),
                "--store",
                str(world.store),
                "--snapshots",
                str(inside),
                "--fixtures",
                str(world.fixtures),
            ]
        )
        == 2
    )
    assert (
        golden.main(
            [
                "record",
                "--fetches",
                str(REPO_ROOT / "tests"),
                "--store",
                str(world.store),
                "--snapshots",
                str(world.snapshots),
                "--fixtures",
                str(world.fixtures),
            ]
        )
        == 2
    )

    err = capsys.readouterr().err
    assert "the snapshot folder must be outside the repository and every worktree" in err
    assert "the fetch reports name pages; keep them outside the repository" in err
    assert not inside.exists()


def test_a_folder_inside_any_worktree_is_inside_a_checkout(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    worktree = tmp_path / "elsewhere" / "a-worktree"
    git = [
        "git",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "-c",
        "init.defaultBranch=main",
    ]
    subprocess.run([*git, "init", "-q", str(repository)], check=True)
    subprocess.run([*git, "-C", str(repository), "commit", "-q", "--allow-empty", "-m", "start"], check=True)
    subprocess.run([*git, "-C", str(repository), "worktree", "add", "-q", str(worktree)], check=True)

    assert not snaps.outside_every_checkout(repository / "snapshots", repository)
    assert not snaps.outside_every_checkout(worktree / "deep" / "snapshots", repository)
    assert not snaps.outside_every_checkout(worktree, repository)
    assert snaps.outside_every_checkout(tmp_path / "elsewhere" / "snapshots", repository)


# ------------------------------------------------------------------------------------------------
# check --snapshots
# ------------------------------------------------------------------------------------------------


def _expected(case_id: str, segments: list[list[int]]) -> dict[str, Any]:
    return {
        "format": snaps.EXPECTED_FORMAT,
        "case_id": case_id,
        "tag": "Demand growth strains the accessible reserve margin",
        "cite": {},
        "research_need": "Demand growth strains the accessible reserve margin",
        "segments": segments,
        "spans": [],
    }


@pytest.fixture
def recorded(world: World, capsys: pytest.CaptureFixture[str]) -> tuple[World, str]:
    """The world after `record --execute`, with only the recorded case left and its offsets written."""
    world.record("--execute")
    for name in ("errored", "unreported", "mislinked"):
        golden.shutil.rmtree(world.fixtures / world.case_for(name))
    case_id = world.case_for("accessible")
    _write(world.fixtures / case_id / golden.EXPECTED_NAME, _expected(case_id, SEGMENTS))
    capsys.readouterr()
    return world, case_id


def test_check_is_clean_when_every_digest_holds_and_the_offsets_reproduce_the_card(
    recorded: tuple[World, str], capsys: pytest.CaptureFixture[str]
) -> None:
    world, _ = recorded

    assert world.check() == 0

    out = capsys.readouterr().out
    assert "snapshots verified: 1 of 1\nevidence reproduced: 1 of 1\nclean" in out
    assert SENTINEL not in out


def _break_raw(world: World, case_id: str) -> None:
    raw = world.snapshots / case_id / snaps.RAW_NAME
    raw.write_bytes(raw.read_bytes().replace(b"preamble", b"Preamble"))


def _break_size(world: World, case_id: str) -> None:
    path = world.fixtures / case_id / golden.CASE_NAME
    case = json.loads(path.read_text())
    case["snapshot"]["raw_byte_size"] += 1
    path.write_text(json.dumps(case))


def _break_document(world: World, case_id: str) -> None:
    document = world.snapshots / case_id / snaps.NORMALIZED_NAME
    document.write_bytes(document.read_bytes().replace(b"preamble", b"Preamble"))


def _break_text_digest(world: World, case_id: str) -> None:
    path = world.fixtures / case_id / golden.CASE_NAME
    case = json.loads(path.read_text())
    case["snapshot"]["normalized_text_sha256"] = "0" * 64
    path.write_text(json.dumps(case))


def _remove_copy(world: World, case_id: str) -> None:
    (world.snapshots / case_id / snaps.RAW_NAME).unlink()


def _remove_record(world: World, case_id: str) -> None:
    path = world.fixtures / case_id / golden.CASE_NAME
    case = json.loads(path.read_text())
    del case["snapshot"]
    path.write_text(json.dumps(case))


def _remove_offsets(world: World, case_id: str) -> None:
    (world.fixtures / case_id / golden.EXPECTED_NAME).unlink()


def _shift_offsets(world: World, case_id: str) -> None:
    shifted = [[SEGMENTS[0][0] + 1, SEGMENTS[0][1]], SEGMENTS[1]]
    _write(world.fixtures / case_id / golden.EXPECTED_NAME, _expected(case_id, shifted))


def _drop_the_cut(world: World, case_id: str) -> None:
    # One segment over the whole passage: it quotes the words the card's "…" left out.
    whole = [[SEGMENTS[0][0], SEGMENTS[1][1]]]
    _write(world.fixtures / case_id / golden.EXPECTED_NAME, _expected(case_id, whole))


@pytest.mark.parametrize(
    ("damage", "problem"),
    [
        (_break_raw, "the raw bytes do not hash to the recorded SHA-256"),
        (_break_size, "the raw bytes are not the recorded size"),
        (_break_document, "the normalized document does not hash to the recorded SHA-256"),
        (_break_text_digest, "the normalized text does not hash to the recorded SHA-256"),
        (_remove_copy, "the snapshot copy is missing"),
        (_remove_record, "no snapshot record in case.json"),
        (_remove_offsets, "no expected.json offsets yet"),
        (_shift_offsets, "the offsets do not reproduce the team card's evidence"),
        (_drop_the_cut, "the offsets do not reproduce the team card's evidence"),
    ],
)
def test_check_fails_outright_on_each_damage(
    recorded: tuple[World, str], capsys: pytest.CaptureFixture[str], damage: Any, problem: str
) -> None:
    world, case_id = recorded
    damage(world, case_id)

    assert world.check() == 1

    out = capsys.readouterr().out
    assert f"snapshot: {case_id}: {problem}\nNOT CLEAN" in out


def test_check_refuses_a_text_the_current_normalizer_would_change(
    recorded: tuple[World, str], capsys: pytest.CaptureFixture[str]
) -> None:
    world, case_id = recorded
    # A document whose digests are all recorded, but whose text holds a double space the normalizer
    # turns into one: a copy no current fetch could have produced.
    path = world.fixtures / case_id / golden.CASE_NAME
    case = json.loads(path.read_text())
    text = PAGE.replace("Plain words", "Plain  words")
    document = json.dumps(
        {
            "format": "debate-snapshot-text/1",
            "normalizer_version": "evidence-normalizer-v1",
            "paragraphs": [],
            "text": text,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    (world.snapshots / case_id / snaps.NORMALIZED_NAME).write_bytes(document)
    case["snapshot"]["normalized_document_sha256"] = hashlib.sha256(document).hexdigest()
    case["snapshot"]["normalized_text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    path.write_text(json.dumps(case))

    assert world.check() == 1

    assert (
        f"snapshot: {case_id}: the text is not what the current normalizer makes of it"
        in capsys.readouterr().out
    )


def test_check_without_snapshots_is_the_metadata_check_alone(
    recorded: tuple[World, str], capsys: pytest.CaptureFixture[str]
) -> None:
    world, case_id = recorded
    _remove_copy(world, case_id)

    assert golden.main(["check", "--fixtures", str(world.fixtures)]) == 0
    assert "snapshots verified" not in capsys.readouterr().out


def test_check_of_an_empty_corpus_against_snapshots_is_not_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "golden_cards").mkdir()

    assert (
        golden.main(
            ["check", "--fixtures", str(tmp_path / "golden_cards"), "--snapshots", str(tmp_path / "s")]
        )
        == 1
    )
    assert "snapshots verified: 0 of 0" in capsys.readouterr().out
