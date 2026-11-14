"""search → `--auto-cut 3` → DOCX bundle → `verify bundle.docx`, end to end on recordings (`v1-e09-t05` ac1).

One student's research run through the CLI's own entry point: OpenAlex answers with v1-e08-t06's six
recorded works, whose landing pages are the HTTP cassettes; each page is fetched through the real
fetcher and its robots.txt gate, extracted, stored as a snapshot, cut by CardService from
:class:`~tests.fixtures.card.every_page_router.EveryPageRouter`'s offsets, cited (Crossref's recorded
answer for the one DOI), verified, and exported to one bundle. Then `verify` reads the bundle back
against the snapshots in the same data directory.

Expected values are written by hand from the fixtures (working agreement 6):

* which pages verify: `packages/debate_cli/tests/fixtures/search/README.md` (the news article, the
  think-tank report and the open-access PDF; the Closed Stacks page is robots-disallowed and the
  Harbor Review page paywalled; the government press release names no author, so its card is
  UNVERIFIED with `CITATION_UNVERIFIED`);
* which pages are cut: since v1-e08-t24 the politics DA's link queries, which all ask five years,
  rank with no recency, so the press release (term match 0.2365) comes fifth, before the news
  article (0.0346), and `--auto-cut 3` cuts it before its third VERIFIED card. Its card is kept in
  the bundle's own section under "UNVERIFIED — not finished cards", never counted toward the three
  (v1-e08-t26);
* each card's evidence: EveryPageRouter selects paragraph 2 whole, so it is the second paragraph of
  t04's hand-written `tests/fixtures/extraction/<sample>.expected.json`, and it starts two characters
  (one blank line) after the first paragraph ends, as the stored snapshot document's `text` joins
  paragraphs (`docs/evidence/snapshot-text-format.md`);
* each raw snapshot is the recorded page: its bytes are the cassette's body.

`--auto-cut 2` on the same search is the clean bundle (v1-e08-t28, the architecture's §11 criterion
2): the two VERIFIED pages ranked above the press release, the think-tank report (3rd, 0.2933) and
the open-access PDF (4th, 0.2213, against the press release's 0.1464; v1-e08-t26's report has the
scores), fill it before the press release is reached, so its bundle holds VERIFIED cards only and
`verify` exits 0.
"""

from __future__ import annotations

import gc
import hashlib
import io
import json
import sqlite3
from pathlib import Path
from typing import Any, Final

import docx
import pytest
from tests.fixtures.extraction.expected_output import load_expected
from tests.fixtures.http.cassettes import load_cassette
from tests.integration.e2e_harness import Boundaries, Cli
from typer.testing import Result

from debate_cli.exit_codes import ExitCode
from debate_core.evidence.docx_manifest_part import read_embedded_manifest_bytes
from debate_core.integrations.local import FsSnapshotStore

pytestmark = pytest.mark.slow

BLOCK: Final = "Politics DA — Link: health insurance"

VERIFYING: Final = {
    "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away": (
        "news-article",
        "news-article",
    ),
    "https://www.harwell-institute.example/research/opportunity-cost-of-de-extinction": (
        "think-tank-report",
        "think-tank-report",
    ),
    "https://journal.synthetic-conservation.example/doi/pdf/10.5555/jscs.2026.0012": (
        "open-access-pdf",
        "journal-article",
    ),
}
"""Canonical URL → (cassette, t04 sample) of the three pages whose cards verify."""

PRESS_RELEASE: Final = "https://www.fosw.example.gov/news/2026/06/agency-announces-grants"
UNVERIFYING: Final = {PRESS_RELEASE: ("government-press-release", "gov-press-release")}
"""Canonical URL → (cassette, t04 sample) of the one page cut whose card does not verify: no author."""

UNVERIFIED_SECTION: Final = "UNVERIFIED — not finished cards"
PRESS_RELEASE_BANNER: Final = "UNVERIFIED — not a finished card: CITATION_UNVERIFIED"

SKIPPED: Final = {
    "https://www.closed-stacks.example/archive/2026/water-rights-ruling": "ROBOTS_DISALLOWED",
    "https://www.harborreview.example/politics/2026/10/inside-the-tariff-talks": "PAYWALLED",
}
"""The two results ranked above the verifying pages, each skipped with its access status."""

BEFORE_THE_PRESS_RELEASE: Final = (
    "https://www.harwell-institute.example/research/opportunity-cost-of-de-extinction",
    "https://journal.synthetic-conservation.example/doi/pdf/10.5555/jscs.2026.0012",
)
"""The two verifying pages ranked above the press release, in rank order: `--auto-cut 2`'s cards."""

SNAPSHOT_CHECKS: Final = {
    "snapshot_integrity",
    "article_matches_snapshot",
    "provenance_matches_snapshot",
    "card_matches_snapshot",
    "evidence_reconstructed",
    "evidence_text_exact",
}
"""The verifier's checks that read a card against its stored snapshot (`evidence-verifier-v2`)."""


def stored_row(data_dir: Path, table: str, key: str, value: str) -> dict[str, Any]:
    """The JSON document of the one `table` row whose `key` is `value`, read from the SQLite file."""
    gc.collect()
    with sqlite3.connect(f"file:{data_dir / 'debate.sqlite3'}?mode=ro", uri=True) as connection:
        (document,) = connection.execute(f"SELECT document FROM {table} WHERE {key} = ?", (value,)).fetchone()
    row: dict[str, Any] = json.loads(document)
    return row


def blob(data_dir: Path, key: str) -> bytes:
    body = FsSnapshotStore(data_dir).path_for(key).read_bytes()
    assert hashlib.sha256(body).hexdigest() == key, "a content-addressed blob holds other bytes than its key"
    return body


def auto_cut_3(cli: Cli, out: Path) -> Result:
    out.parent.mkdir()
    return cli.run(
        "search",
        "health insurance",
        "--argument",
        "politics-da",
        "--need",
        "link",
        "--providers",
        "openalex",
        "--auto-cut",
        "3",
        "--output",
        str(out),
    )


def auto_cut(cli: Cli, out: Path, size: int) -> Result:
    """The same search as :func:`auto_cut_3`, cut to `size` VERIFIED cards."""
    out.parent.mkdir()
    return cli.run(
        "search",
        "health insurance",
        "--argument",
        "politics-da",
        "--need",
        "link",
        "--providers",
        "openalex",
        "--auto-cut",
        str(size),
        "--output",
        str(out),
    )


def test_search_auto_cut_3_writes_three_verified_cards_and_a_bannered_unverified_one_and_verify_agrees(
    cli: Cli, boundaries: Boundaries, cli_environment: Path, tmp_path: Path
) -> None:
    """Each of the four cards is cut from its stored snapshot; verify passes the three VERIFIED ones
    and names the bannered one's CITATION_UNVERIFIED (until v1-e08-t26 the name ended
    `..._cut_from_their_snapshots_and_verify_passes_the_bundle`, when the bundle held three cards)."""
    out = tmp_path / "research" / "bundle.docx"

    searched = auto_cut_3(cli, out)

    assert searched.exit_code == ExitCode.OK, searched.output
    report = json.loads((out.parent / "report.json").read_text(encoding="utf-8"))
    assert (report["wanted"], report["verified"], report["stop_reason"]) == (3, 3, "COMPLETE")
    assert report["unverified"] == 1
    skipped = {
        entry["url"]: entry["access_status"] for entry in report["entries"] if entry["status"] == "SKIPPED"
    }
    assert skipped == SKIPPED
    unverified = {
        entry["url"]: (entry["section"], entry["reasons"])
        for entry in report["entries"]
        if entry["status"] == "UNVERIFIED"
    }
    assert unverified == {PRESS_RELEASE: ("unverified", ["CITATION_UNVERIFIED"])}

    manifest_bytes = (out.parent / "bundle.manifest.json").read_bytes()
    assert read_embedded_manifest_bytes(out) == manifest_bytes
    cards = json.loads(manifest_bytes)["cards"]
    assert [card["verification_status"] for card in cards] == ["VERIFIED"] * 3 + ["UNVERIFIED"]
    body = [paragraph.text for paragraph in docx.Document(io.BytesIO(out.read_bytes())).paragraphs]
    assert body[0] == BLOCK
    section = body.index(UNVERIFIED_SECTION)
    assert body[section + 2] == PRESS_RELEASE_BANNER

    cut_from = set()
    for card in cards:
        snapshot = stored_row(cli_environment, "source_snapshots", "snapshot_id", card["snapshot_id"])
        article = stored_row(cli_environment, "articles", "article_id", snapshot["article_id"])
        cassette, sample = {**VERIFYING, **UNVERIFYING}[article["canonical_url"]]
        is_verified = card["verification_status"] == "VERIFIED"
        assert (article["canonical_url"] in VERIFYING) == is_verified
        cut_from.add(article["canonical_url"])
        page = load_cassette(cassette).page
        assert page is not None
        assert blob(cli_environment, snapshot["raw_blob_key"]) == page.body

        paragraphs = load_expected(sample)["paragraphs"]
        start = len(paragraphs[0]) + 2
        assert (card["evidence_start_offset"], card["evidence_end_offset"]) == (
            start,
            start + len(paragraphs[1]),
        )
        stored = json.loads(blob(cli_environment, snapshot["normalized_blob_key"]))
        assert stored["format"] == "debate-snapshot-text/1"
        assert stored["text"][card["evidence_start_offset"] : card["evidence_end_offset"]] == paragraphs[1]
        assert card["evidence_text"] == paragraphs[1]
        assert paragraphs[1] in body
        # VERIFIED evidence is above the bannered section, the UNVERIFIED card's inside it.
        assert (body.index(paragraphs[1]) < section) == is_verified
    assert cut_from == set(VERIFYING) | set(UNVERIFYING)

    verified, envelope = cli.envelope("verify", str(out))

    # The bundle holds the bannered card, so verify agrees card by card and fails the bundle for it.
    assert verified.exit_code == ExitCode.DOMAIN_FAILURE == 1, verified.output
    assert envelope["error"]["code"] == "UNVERIFIED"
    assert [
        (verdict["card_id"], verdict["status"], verdict["reason_codes"])
        for verdict in envelope["error"]["details"]["cards"]
    ] == [(card["card_id"], "VERIFIED", []) for card in cards[:3]] + [
        (cards[3]["card_id"], "UNVERIFIED", ["CITATION_UNVERIFIED"])
    ]


def test_search_auto_cut_2_stops_before_the_press_release_and_verify_passes_the_whole_bundle(
    cli: Cli, boundaries: Boundaries, cli_environment: Path, tmp_path: Path
) -> None:
    """A whole auto-cut bundle verifies with exit 0 (§11 criterion 2): both cards are VERIFIED, each
    is cut from its stored snapshot, and verify reads each against that snapshot and passes it."""
    out = tmp_path / "research" / "bundle.docx"

    searched = auto_cut(cli, out, 2)

    assert searched.exit_code == ExitCode.OK, searched.output
    report = json.loads((out.parent / "report.json").read_text(encoding="utf-8"))
    assert (report["wanted"], report["verified"], report["stop_reason"]) == (2, 2, "COMPLETE")
    # By page and reason first, so a card that stops verifying is named with its reason codes.
    unverified = {
        entry["url"]: (entry["section"], entry["reasons"])
        for entry in report["entries"]
        if entry["status"] == "UNVERIFIED"
    }
    assert unverified == {}, unverified
    assert report["unverified"] == 0
    skipped = {
        entry["url"]: entry["access_status"] for entry in report["entries"] if entry["status"] == "SKIPPED"
    }
    assert skipped == SKIPPED
    # The search stops before the press release: it is not fetched, cut or reported.
    assert [entry["url"] for entry in report["entries"]] == [*SKIPPED, *BEFORE_THE_PRESS_RELEASE]
    assert [entry["status"] for entry in report["entries"]] == ["SKIPPED"] * 2 + ["VERIFIED"] * 2

    manifest_bytes = (out.parent / "bundle.manifest.json").read_bytes()
    assert read_embedded_manifest_bytes(out) == manifest_bytes
    cards = json.loads(manifest_bytes)["cards"]
    assert [card["verification_status"] for card in cards] == ["VERIFIED"] * 2
    body = [paragraph.text for paragraph in docx.Document(io.BytesIO(out.read_bytes())).paragraphs]
    assert body[0] == BLOCK
    assert UNVERIFIED_SECTION not in body
    assert not [paragraph for paragraph in body if paragraph.startswith("UNVERIFIED")]

    cut_from = []
    for card in cards:
        snapshot = stored_row(cli_environment, "source_snapshots", "snapshot_id", card["snapshot_id"])
        article = stored_row(cli_environment, "articles", "article_id", snapshot["article_id"])
        cassette, sample = VERIFYING[article["canonical_url"]]
        cut_from.append(article["canonical_url"])
        page = load_cassette(cassette).page
        assert page is not None
        assert blob(cli_environment, snapshot["raw_blob_key"]) == page.body

        paragraphs = load_expected(sample)["paragraphs"]
        start = len(paragraphs[0]) + 2
        assert (card["evidence_start_offset"], card["evidence_end_offset"]) == (
            start,
            start + len(paragraphs[1]),
        )
        stored = json.loads(blob(cli_environment, snapshot["normalized_blob_key"]))
        assert stored["format"] == "debate-snapshot-text/1"
        assert stored["text"][card["evidence_start_offset"] : card["evidence_end_offset"]] == paragraphs[1]
        assert card["evidence_text"] == paragraphs[1]
        assert paragraphs[1] in body
    assert cut_from == list(BEFORE_THE_PRESS_RELEASE)

    verified, envelope = cli.envelope("verify", str(out))

    assert verified.exit_code == ExitCode.OK == 0, verified.output
    assert (envelope["status"], envelope["error"]) == ("ok", None)
    result = envelope["data"]
    assert (result["total"], result["verified"], result["unverified"]) == (2, 2, 0)
    assert [
        (verdict["card_id"], verdict["snapshot_id"], verdict["status"], verdict["reason_codes"])
        for verdict in result["cards"]
    ] == [(card["card_id"], card["snapshot_id"], "VERIFIED", []) for card in cards]
    # verify read each card against its stored snapshot, not only its citation.
    for verdict in result["cards"]:
        assert set(verdict["checks_run"]) >= SNAPSHOT_CHECKS, verdict["checks_run"]
    assert (result["document"]["body_cards"], result["document"]["unclaimed_body_cards"]) == (2, [])


def test_the_bundle_does_not_verify_where_its_snapshots_are_not_stored(
    cli: Cli, boundaries: Boundaries, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same bundle, read on a machine whose data directory never stored its sources (§11.3).

    The bannered press release card keeps its own reason as well: verify checks the citation before
    it looks for the snapshot."""
    out = tmp_path / "research" / "bundle.docx"
    assert auto_cut_3(cli, out).exit_code == ExitCode.OK
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(tmp_path / "another-machine"))

    result, envelope = cli.envelope("verify", str(out))
    shown = cli.run("verify", str(out))

    assert result.exit_code == shown.exit_code == ExitCode.DOMAIN_FAILURE == 1
    assert envelope["error"]["code"] == "UNVERIFIED"
    verdicts = envelope["error"]["details"]["cards"]
    assert [(verdict["status"], verdict["reason_codes"]) for verdict in verdicts] == [
        ("UNVERIFIED", ["SNAPSHOT_MISSING"])
    ] * 3 + [("UNVERIFIED", ["CITATION_UNVERIFIED", "SNAPSHOT_MISSING"])]
    assert "SNAPSHOT_MISSING" in shown.stdout
    assert "CITATION_UNVERIFIED" in shown.stdout
