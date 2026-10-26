"""`debate-research fetch` end to end, offline: every cassette through the real pipeline (v1-e04-t06).

The app, the composition root and every adapter are the production ones: the polite HTTP fetcher with
its robots.txt, interval and redirect gates, the HTML and PDF extractors, the access classifier,
ArticleService, the SQLite file and the blob store, in a data directory of this test's own. One thing
is replaced: the fetcher's transport, registered under the container's `"article_fetch_transport"`
seam, is :class:`~tests.fixtures.http.cassettes.ReplayTransport`, which answers from the committed
cassettes and sends nothing. A request no cassette recorded fails the test.

It runs in pytest's process rather than as the installed console script, unlike
`test_verify_cli.py`: a separate process could only be handed the replay by patching the build, and
the fetcher refuses a loopback stand-in by design. The installed binary is checked offline by
`tests/smoke/test_fetch_smoke.py`, on the paths that need no network.

What each cassette must give is `tests/fixtures/http/expected_fetches.json`, written by hand.
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.http.cassettes import ReplayTransport, cassette_names, load_cassette
from tests.fixtures.verify.published_schemas import violations
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_core.application.article_fetch import FETCH_RESULT_SCHEMA_FILENAME

# Imported here, before pytest-socket is armed: urllib3 (through trafilatura) probes for IPv6 with a
# socket when it is first imported, which the container would otherwise do inside a test.
from debate_core.integrations import html_extractor as html_extractor

EXPECTED: dict[str, dict[str, Any]] = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "http" / "expected_fetches.json").read_text(encoding="utf-8")
)
runner = CliRunner()


@pytest.fixture
def replay(monkeypatch: pytest.MonkeyPatch) -> Iterator[ReplayTransport]:
    """Every cassette, handed to each container the app builds; no request may go unanswered."""
    transport = ReplayTransport(load_cassette(name) for name in cassette_names())
    build = ServiceContainer.__init__

    def with_replay(self: ServiceContainer, **arguments: Any) -> None:
        build(self, **arguments)
        self.override("article_fetch_transport", transport)

    monkeypatch.setattr(ServiceContainer, "__init__", with_replay)
    yield transport
    assert transport.unrecorded == [], "a request no cassette recorded"


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "data"
    for name in [name for name in __import__("os").environ if name.startswith("DEBATE_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(directory))
    # robots.txt and the page are two requests to one host; the polite interval would sleep between them.
    monkeypatch.setenv("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS", "0")
    return directory


def fetch(*arguments: str) -> Result:
    return runner.invoke(create_app(), ["fetch", *arguments])


def fetch_json(*arguments: str) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(create_app(), ["--json", "fetch", *arguments])
    lines = result.stdout.splitlines()
    assert len(lines) == 1, result.output
    document: dict[str, Any] = json.loads(lines[0])
    assert violations(FETCH_RESULT_SCHEMA_FILENAME, document) == []
    return result.exit_code, document


def stored_snapshots(data_dir: Path) -> list[tuple[str, str, str]]:
    """(snapshot id, raw hash, provenance) of every snapshot record in the data directory's SQLite file."""
    gc.collect()
    database = data_dir / "debate.sqlite3"
    if not database.exists():
        return []
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        documents = [row[0] for row in connection.execute("SELECT document FROM source_snapshots")]
    records = [json.loads(document) for document in documents]
    return sorted((record["snapshot_id"], record["sha256"], record["provenance_mode"]) for record in records)


def stored_blobs(data_dir: Path) -> set[str]:
    return {path.name for path in (data_dir / "blobs").rglob("*") if path.is_file()}


def page_bytes(name: str) -> bytes:
    page = load_cassette(name).page
    assert page is not None
    return page.body


ACCESSIBLE = [name for name in cassette_names() if EXPECTED[name]["exit_code"] == 0]
REFUSED = [name for name in cassette_names() if EXPECTED[name]["exit_code"] != 0]


def test_every_cassette_has_a_hand_written_expectation() -> None:
    assert set(cassette_names()) == set(EXPECTED)
    assert len(ACCESSIBLE) == 4
    assert {EXPECTED[name]["access_status"] for name in REFUSED} >= {
        "PAYWALLED",
        "ROBOTS_DISALLOWED",
        "NOT_FOUND",
    }


@pytest.mark.parametrize("name", ACCESSIBLE)
def test_a_readable_fixture_prints_its_metadata_accessible_and_the_snapshot_and_exits_zero(
    name: str, replay: ReplayTransport, data_dir: Path
) -> None:
    """ac1: metadata, ACCESSIBLE, the snapshot id and sha256, exit 0; and the snapshot is stored."""
    expected = EXPECTED[name]
    raw_hash = hashlib.sha256(page_bytes(name)).hexdigest()

    result = fetch(load_cassette(name).url)

    assert result.exit_code == 0, result.output
    flat = "".join(result.stdout.replace("│", "").split())
    for shown in (
        "ACCESSIBLE",
        expected["canonical_url"],
        expected["title"],
        raw_hash,
        "PUBLISHER_RETRIEVED",
    ):
        assert "".join(shown.split()) in flat, shown
    ((snapshot_id, stored_hash, provenance),) = stored_snapshots(data_dir)
    assert snapshot_id in flat
    assert (stored_hash, provenance) == (raw_hash, "PUBLISHER_RETRIEVED")
    assert raw_hash in stored_blobs(data_dir)


@pytest.mark.parametrize("name", ACCESSIBLE)
def test_a_readable_fixtures_json_report_matches_its_hand_written_expectation(
    name: str, replay: ReplayTransport, data_dir: Path
) -> None:
    expected = EXPECTED[name]

    exit_code, document = fetch_json(load_cassette(name).url)

    assert exit_code == 0
    report = document["data"]
    assert report["access_status"] == "ACCESSIBLE"
    assert (report["canonical_url"], report["title"]) == (expected["canonical_url"], expected["title"])
    assert {key: value for key, value in report["identifiers"].items() if value is not None} == expected[
        "identifiers"
    ]
    assert report["reason"].startswith(expected["reason_starts"])
    snapshot = report["snapshot"]
    assert snapshot["sha256"] == hashlib.sha256(page_bytes(name)).hexdigest()
    assert snapshot["paragraph_count"] == expected["paragraph_count"]
    assert snapshot["extractor_version"].startswith(f"{expected['extractor']}/")
    assert snapshot["normalizer_version"] == "evidence-normalizer-v1"
    assert [row[0] for row in stored_snapshots(data_dir)] == [snapshot["snapshot_id"]]


@pytest.mark.parametrize("name", REFUSED)
def test_a_refused_fixture_prints_its_status_and_reason_exits_three_and_stores_no_snapshot(
    name: str, replay: ReplayTransport, data_dir: Path
) -> None:
    """ac2: the specific AccessStatus and reason, exit 3, and no snapshot in the data dir."""
    expected = EXPECTED[name]

    result = fetch(load_cassette(name).url)

    assert result.exit_code == 3, result.output
    panel = " ".join(result.stderr.replace("│", " ").split())
    assert f"{expected['access_status']}: {expected['reason_starts']}" in panel
    assert f"access_status: {expected['access_status']}" in panel
    assert "rules_version: paywall_rules.v1" in panel
    assert f"marker: {expected['marker_id']}" in panel
    assert stored_snapshots(data_dir) == []
    assert stored_blobs(data_dir) == set()


@pytest.mark.parametrize("name", REFUSED)
def test_a_refused_fixtures_json_report_matches_its_hand_written_expectation(
    name: str, replay: ReplayTransport, data_dir: Path
) -> None:
    expected = EXPECTED[name]

    exit_code, document = fetch_json(load_cassette(name).url)

    assert exit_code == 3
    error = document["error"]
    assert (error["code"], error["exit_code"]) == ("SOURCE_NOT_ACCESSIBLE", 3)
    report = error["details"]
    assert (report["access_status"], report["snapshot"]) == (expected["access_status"], None)
    assert (report["canonical_url"], report["title"]) == (expected["canonical_url"], expected["title"])
    assert report["reason"].startswith(expected["reason_starts"])
    marker = (report["evidence"] or {}).get("marker")
    assert (marker["marker_id"] if marker else None) == expected["marker_id"]
    assert stored_snapshots(data_dir) == []


def test_robots_txt_is_read_and_the_page_it_refuses_is_never_requested(
    replay: ReplayTransport, data_dir: Path
) -> None:
    fetch(load_cassette("robots-disallowed").url)

    assert replay.requested == ["https://www.closed-stacks.example/robots.txt"]


def test_a_paywalled_page_can_then_be_stored_from_the_coachs_own_copy_as_user_supplied(
    replay: ReplayTransport, data_dir: Path, tmp_path: Path
) -> None:
    """ac4's other half on the real store: refused by the publisher, then attested and pasted."""
    url = load_cassette("paywalled").url
    copy = tmp_path / "my-copy.txt"
    copy.write_text(
        "\n\n".join(
            ["Negotiators from two invented trading partners met for a fourth round of talks. " * 4] * 3
        ),
        encoding="utf-8",
    )
    assert fetch(url).exit_code == 3

    refused = fetch("--paste", str(copy), "--source-url", url)
    exit_code, document = fetch_json("--paste", str(copy), "--source-url", url, "--i-have-lawful-access")

    assert refused.exit_code == 1
    assert exit_code == 0
    report = document["data"]
    assert (report["provenance_mode"], report["canonical_url"]) == ("USER_SUPPLIED", url)
    ((snapshot_id, _, provenance),) = stored_snapshots(data_dir)
    assert (snapshot_id, provenance) == (report["snapshot"]["snapshot_id"], "USER_SUPPLIED")
    assert replay.requested == ["https://www.harborreview.example/robots.txt", url]


# --------------------------------------------------------------------------------------------
# The composition root passes the settings through
# --------------------------------------------------------------------------------------------


def test_the_html_extractors_size_limit_comes_from_articles_html_max_bytes(
    replay: ReplayTransport, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The news page is 4,920 bytes: refused under a 4 KiB limit, read under the default."""
    monkeypatch.setenv("DEBATE_ARTICLES__HTML_MAX_BYTES", "4096")

    exit_code, document = fetch_json(load_cassette("news-article").url)

    assert exit_code == 3
    report = document["error"]["details"]
    assert report["access_status"] == "ERROR"
    assert report["evidence"]["extraction_refusal"] == "DocumentTooLarge"


def test_pasted_text_is_bounded_by_http_max_response_bytes(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """2,100 bytes of text: rejected under a 2,048-byte limit, as a fetch of that size would be."""
    monkeypatch.setenv("DEBATE_HTTP__MAX_RESPONSE_BYTES", "2048")
    copy = tmp_path / "copy.txt"
    copy.write_text(
        "\n\n".join(["An invented paragraph about the basin council's vote. " * 10] * 4)[:2100],
        encoding="utf-8",
    )

    exit_code, document = fetch_json(
        "--paste", str(copy), "--source-url", "https://www.example.org/a", "--i-have-lawful-access"
    )

    assert exit_code == 1
    assert document["error"]["code"] == "USER_TEXT_REJECTED"
    assert "over the 2048-byte limit" in document["error"]["message"]


# --------------------------------------------------------------------------------------------
# No page text in any log record
# --------------------------------------------------------------------------------------------

STANDARD_RECORD_FIELDS = set(vars(logging.LogRecord("n", logging.INFO, "p", 1, "m", None, None)))


def test_no_log_record_holds_a_sentence_of_the_page_whatever_the_level(
    replay: ReplayTransport, data_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The message and every `extra` field of every record, at DEBUG, against t04's own paragraphs."""
    expected = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "extraction" / "news-article.expected.json").read_text(
            "utf-8"
        )
    )
    sentences = [paragraph[:60] for paragraph in expected["paragraphs"]]
    caplog.set_level(logging.DEBUG)

    fetch(load_cassette("news-article").url)
    fetch(load_cassette("paywalled").url)

    assert caplog.records, "nothing was logged, so nothing was checked"
    for record in caplog.records:
        extras = {name: value for name, value in vars(record).items() if name not in STANDARD_RECORD_FIELDS}
        logged = record.getMessage() + " " + " ".join(str(value) for value in extras.values())
        for sentence in [*sentences, "Negotiators from two invented trading partners"]:
            assert sentence not in logged, (record.name, sentence)
