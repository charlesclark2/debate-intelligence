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
  Harbor Review page paywalled);
* each card's evidence: EveryPageRouter selects paragraph 2 whole, so it is the second paragraph of
  t04's hand-written `tests/fixtures/extraction/<sample>.expected.json`, and it starts two characters
  (one blank line) after the first paragraph ends, as the stored snapshot document's `text` joins
  paragraphs (`docs/evidence/snapshot-text-format.md`);
* each raw snapshot is the recorded page: its bytes are the cassette's body.
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

SKIPPED: Final = {
    "https://www.closed-stacks.example/archive/2026/water-rights-ruling": "ROBOTS_DISALLOWED",
    "https://www.harborreview.example/politics/2026/10/inside-the-tariff-talks": "PAYWALLED",
}
"""The two results ranked above the verifying pages, each skipped with its access status."""


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


def test_search_auto_cut_3_writes_three_verified_cards_cut_from_their_snapshots_and_verify_passes_the_bundle(
    cli: Cli, boundaries: Boundaries, cli_environment: Path, tmp_path: Path
) -> None:
    out = tmp_path / "research" / "bundle.docx"

    searched = auto_cut_3(cli, out)

    assert searched.exit_code == ExitCode.OK, searched.output
    report = json.loads((out.parent / "report.json").read_text(encoding="utf-8"))
    assert (report["wanted"], report["verified"], report["stop_reason"]) == (3, 3, "COMPLETE")
    skipped = {
        entry["url"]: entry["access_status"] for entry in report["entries"] if entry["status"] == "SKIPPED"
    }
    assert skipped == SKIPPED

    manifest_bytes = (out.parent / "bundle.manifest.json").read_bytes()
    assert read_embedded_manifest_bytes(out) == manifest_bytes
    cards = json.loads(manifest_bytes)["cards"]
    assert [card["verification_status"] for card in cards] == ["VERIFIED"] * 3
    body = [paragraph.text for paragraph in docx.Document(io.BytesIO(out.read_bytes())).paragraphs]
    assert body[0] == BLOCK

    cut_from = set()
    for card in cards:
        snapshot = stored_row(cli_environment, "source_snapshots", "snapshot_id", card["snapshot_id"])
        article = stored_row(cli_environment, "articles", "article_id", snapshot["article_id"])
        cassette, sample = VERIFYING[article["canonical_url"]]
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
    assert cut_from == set(VERIFYING)

    verified, envelope = cli.envelope("verify", str(out))

    assert verified.exit_code == ExitCode.OK, verified.output
    assert [(card["card_id"], card["status"]) for card in envelope["data"]["cards"]] == [
        (card["card_id"], "VERIFIED") for card in cards
    ]


def test_the_bundle_does_not_verify_where_its_snapshots_are_not_stored(
    cli: Cli, boundaries: Boundaries, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same bundle, read on a machine whose data directory never stored its sources (§11.3)."""
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
    ] * 3
    assert "SNAPSHOT_MISSING" in shown.stdout
