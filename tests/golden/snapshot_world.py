"""An invented store, corpus and fetch reports for the golden corpus's snapshot tests.

What `debate-research fetch` would leave on the operator's machine, built under `tmp_path`: a real
SQLite database and filesystem blob store filled by the platform's own `SnapshotService`, a corpus
imported from invented team files by `import_golden_card.py`, and fetch reports in the shape of the
fetch command's `--json` envelope. Nothing here reads the operator's files.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import import_golden_card as golden  # noqa: E402
from tests.golden.synthetic_team_files import FILLER, SyntheticCard, coach_attests, team_file  # noqa: E402

from debate_core.application.snapshot_service import SnapshotService  # noqa: E402
from debate_core.domain import AccessStatus, ProvenanceMode, SourceSnapshot  # noqa: E402
from debate_core.integrations.local import (  # noqa: E402
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


def envelope(
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


def write_json(path: Path, envelope: dict[str, Any] | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(envelope if isinstance(envelope, str) else json.dumps(envelope), encoding="utf-8")
    return path


def card(name: str, link: str, body: Sequence[str] = CARD_BODY, **options: Any) -> SyntheticCard:
    """An invented card whose tag names `name`, citing `link`, with `body`'s paragraphs."""
    return SyntheticCard(
        tag=f"Demand growth strains the {name} reserve margin",
        short_cite="Okonkwo 26",
        cite_rest=" [Ada Okonkwo, senior analyst, 3-4-2026, {link}]",
        link=link,
        body=list(body),
        **options,
    )


@dataclass
class World:
    root: Path
    store: Path
    fetches: Path
    snapshots: Path
    fixtures: Path
    ids: SequentialIdGenerator

    links: dict[str, str] = field(default_factory=lambda: dict(LINKS))
    ids_used: list[str] = field(default_factory=list)

    def case_for(self, name: str) -> str:
        """The case ID the importer gave the card whose link is `name`'s."""
        (case,) = [c for c in golden._existing_cases(self.fixtures) if c["source_link"] == self.links[name]]
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

    def report(self, name: str, envelope: dict[str, Any]) -> None:
        write_json(self.fetches / f"{self.case_for(name)}.json", envelope)

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


def build_world(
    tmp_path: Path, layout: Sequence[tuple[str, str, Sequence[SyntheticCard]]], links: dict[str, str]
) -> World:
    """Import `layout`'s cards (season, event folder, cards) into a corpus under `tmp_path`."""
    debate = tmp_path / "debate"
    for season, event, cards in layout:
        (debate / season / event).mkdir(parents=True)
        (debate / season / event / "team file.docx").write_bytes(team_file(cards))
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
    assert (len(imported), refused) == (sum(len(cards) for _, _, cards in layout), [])
    return World(
        root=tmp_path,
        store=tmp_path / "store",
        fetches=tmp_path / "fetches",
        snapshots=tmp_path / "golden-snapshots",
        fixtures=fixtures,
        ids=SequentialIdGenerator(),
        links=links,
    )


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}
