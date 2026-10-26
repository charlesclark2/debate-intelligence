"""`debate-research fetch`, through Typer's runner and the real app, over a fake-backed ArticleFetch.

The service is the real ArticleService over the in-memory fakes (a canned fetcher, a blank-line
extractor, in-memory articles and blobs), registered in place of the container's `article_fetch`.
What is tested here is the command-line surface: the exit code for each status, the output in both
modes, `--refresh`, the arguments `--paste` needs and the attestation. The real fetcher and extractors
over recorded responses are `tests/integration/test_fetch_cli.py`'s.

Expected values are written by hand: the page has three paragraphs, its raw hash is SHA-256 of its
bytes, and each failing status's reason is the access classifier's table (v1-e04-t03).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.verify.published_schemas import violations
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.commands import fetch as fetch_command
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.article_fetch import FETCH_RESULT_SCHEMA_FILENAME, ArticleFetch
from debate_core.application.article_service import ArticleService
from debate_core.application.errors import ProviderUnavailable
from debate_core.application.settings import ArticleSettings
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, ProvenanceMode
from debate_core.retrieval.fetch_types import (
    FetchResult,
    RobotsDisallowed,
    RobotsRefusalReason,
    Timeout,
    TimeoutPhase,
)
from debate_core.testing.fakes.clock_and_ids import FixedClock, SequentialIdGenerator
from debate_core.testing.fakes.persistence import InMemoryArticleRepository, InMemorySnapshotStore
from debate_core.testing.fakes.providers import FakeArticleFetcher, FakeContentExtractor

runner = CliRunner()

URL = "https://www.example.org/water/2026/basin-report?utm_campaign=autumn"
CANONICAL = "https://www.example.org/water/2026/basin-report"
SENTINEL = "Quillfeather"
"""A word in every page and every pasted text, which no output may contain."""
PARAGRAPH = (
    f"The {SENTINEL} basin council voted to open the reservoir after a summer in which three of the four "
    "regions drew down their groundwater faster than the aquifer recharged. "
)
BODY = "\n\n".join(PARAGRAPH * 2 for _ in range(3)).encode()
"""Three paragraphs, over the 500-character minimum."""


@dataclass
class Connection:
    closed: int = 0

    async def aclose(self) -> None:
        self.closed += 1


@dataclass
class World:
    fetcher: FakeArticleFetcher
    articles: InMemoryArticleRepository
    blobs: InMemorySnapshotStore
    connection: Connection
    built: list[ArticleFetch] = field(default_factory=list[ArticleFetch])

    def article_fetch(self) -> ArticleFetch:
        """A fresh ArticleFetch over the same stores, as each run of the CLI builds one."""
        clock, ids = FixedClock(), SequentialIdGenerator(prefix=f"0RN{len(self.built)}")
        snapshots = SnapshotService(blobs=self.blobs, clock=clock, id_generator=ids)
        service = ArticleService(
            articles=self.articles,
            snapshots=snapshots,
            fetcher=self.fetcher,
            extractor=FakeContentExtractor(),
            clock=clock,
            id_generator=ids,
            settings=ArticleSettings(),
            max_user_text_bytes=100_000,
        )
        self.built.append(ArticleFetch(articles=service, snapshots=snapshots, connection=self.connection))
        return self.built[-1]

    def snapshot_count(self) -> int:
        return len(self.articles._snapshots)  # pyright: ignore[reportPrivateUsage]


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    built = World(FakeArticleFetcher(), InMemoryArticleRepository(), InMemorySnapshotStore(), Connection())
    monkeypatch.setattr(ServiceContainer, "article_fetch", lambda _self: built.article_fetch())  # pyright: ignore[reportUnknownLambdaType]
    monkeypatch.setattr(fetch_command, "stdin_is_a_terminal", lambda: False)
    for name in [name for name in __import__("os").environ if name.startswith("DEBATE_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("DEBATE_ENV", "test")
    yield built


def invoke(*arguments: str, stdin: str | None = None) -> Result:
    return runner.invoke(create_app(), list(arguments), input=stdin)


def envelope(result: Result) -> dict[str, Any]:
    """The one JSON object a `--json` run prints, checked against the published result schema."""
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"--json must print exactly one line on stdout, got: {result.stdout!r}"
    document: dict[str, Any] = json.loads(lines[0])
    assert violations(FETCH_RESULT_SCHEMA_FILENAME, document) == [], (
        "the output does not fit fetch_result.v1.json"
    )
    return document


# --------------------------------------------------------------------------------------------
# The help
# --------------------------------------------------------------------------------------------


def test_the_help_documents_every_exit_code_and_the_attestation_flag() -> None:
    result = invoke("fetch", "--help")

    assert result.exit_code == ExitCode.OK
    for line in ("0  ACCESSIBLE and stored", "1  refused, nothing stored", "2  usage error", "3  PAYWALLED"):
        assert line in result.stdout
    assert "--i-have-lawful-access" in result.stdout


# --------------------------------------------------------------------------------------------
# A readable page: exit 0, metadata, the snapshot
# --------------------------------------------------------------------------------------------


def test_a_readable_page_prints_its_metadata_snapshot_and_hashes_and_exits_zero(world: World) -> None:
    world.fetcher.add(URL, BODY)

    result = invoke("fetch", URL)

    assert result.exit_code == ExitCode.OK, result.output
    for shown in ("ACCESSIBLE", CANONICAL, "Paragraphs", "fake-extractor/fake-1.0.0", "PUBLISHER_RETRIEVED"):
        assert shown in result.stdout
    assert hashlib.sha256(BODY).hexdigest() in result.stdout.replace("│", "").replace(" ", "").replace(
        "\n", ""
    )
    assert world.snapshot_count() == 1


def test_json_output_carries_the_report_under_data_and_fits_the_schema(world: World) -> None:
    world.fetcher.add(URL, BODY)

    data = envelope(invoke("--json", "fetch", URL))["data"]

    assert (data["access_status"], data["canonical_url"], data["requested_url"]) == (
        "ACCESSIBLE",
        CANONICAL,
        URL,
    )
    assert data["provenance_mode"] == "PUBLISHER_RETRIEVED"
    assert data["snapshot"]["sha256"] == hashlib.sha256(BODY).hexdigest()
    assert data["snapshot"]["paragraph_count"] == 3
    assert data["snapshot"]["extractor_version"] == "fake-extractor/fake-1.0.0"


# --------------------------------------------------------------------------------------------
# Every other status: exit 3, its reason and rules version, and no snapshot
# --------------------------------------------------------------------------------------------


def add_404(fetcher: FakeArticleFetcher) -> FetchResult:
    return fetcher.add(URL, b"<p>Gone.</p>", status_code=404)


def add_402(fetcher: FakeArticleFetcher) -> FetchResult:
    return fetcher.add(URL, b"<p>Pay.</p>", status_code=402)


def add_403(fetcher: FakeArticleFetcher) -> FetchResult:
    return fetcher.add(URL, b"<p>No.</p>", status_code=403)


def add_robots(fetcher: FakeArticleFetcher) -> FetchResult:
    refusal = RobotsDisallowed(
        url=URL,
        message="robots.txt on www.example.org refuses this URL (disallowed)",
        robots_url="https://www.example.org/robots.txt",
        reason=RobotsRefusalReason.DISALLOWED,
    )
    return fetcher.add(
        URL, b"", status_code=None, error=refusal, access_status=AccessStatus.ROBOTS_DISALLOWED
    )


def add_timeout(fetcher: FakeArticleFetcher) -> FetchResult:
    late = Timeout(
        url=URL, message="www.example.org did not answer in time", phase=TimeoutPhase.READ, limit_seconds=30.0
    )
    return fetcher.add(URL, b"", status_code=None, error=late)


def add_image(fetcher: FakeArticleFetcher) -> FetchResult:
    return fetcher.add(URL, b"\x89PNG\r\n\x1a\n" + bytes(600), content_type="image/png")


def add_short(fetcher: FakeArticleFetcher) -> FetchResult:
    return fetcher.add(URL, f"A {SENTINEL} line.".encode())


FAILURES = [
    pytest.param(add_404, "NOT_FOUND", "The server has no document at this URL (404)", id="404"),
    pytest.param(add_402, "PAYWALLED", "The server requires payment (402)", id="402"),
    pytest.param(add_403, "BLOCKED", "The server refused the request (403)", id="403"),
    pytest.param(add_robots, "ROBOTS_DISALLOWED", "robots.txt keeps the platform from this URL", id="robots"),
    pytest.param(add_timeout, "ERROR", "The fetch ran out of time", id="timeout"),
    pytest.param(add_image, "UNSUPPORTED_TYPE", "", id="image"),
    pytest.param(add_short, "ERROR", "", id="too-short"),
]


@pytest.mark.parametrize(("respond", "status", "reason_starts"), FAILURES)
def test_every_status_but_accessible_exits_three_with_its_reason_and_stores_no_snapshot(
    world: World, respond: Any, status: str, reason_starts: str
) -> None:
    respond(world.fetcher)

    result = invoke("fetch", URL)

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.output
    assert "SOURCE_NOT_ACCESSIBLE" in result.stderr
    assert f"{status}: {reason_starts}" in " ".join(result.stderr.replace("│", " ").split())
    assert f"access_status: {status}" in result.stderr
    assert "rules_version: paywall_rules.v1" in result.stderr
    assert world.snapshot_count() == 0
    assert world.blobs.stored_keys() == frozenset()


@pytest.mark.parametrize(("respond", "status", "reason_starts"), FAILURES)
def test_every_status_but_accessible_has_the_report_under_error_details_in_json(
    world: World, respond: Any, status: str, reason_starts: str
) -> None:
    respond(world.fetcher)

    result = invoke("--json", "fetch", URL)

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"]) == ("SOURCE_NOT_ACCESSIBLE", 3)
    details = error["details"]
    assert (details["access_status"], details["snapshot"], details["provenance_mode"]) == (status, None, None)
    assert details["reason"].startswith(reason_starts)
    assert details["rules_version"] == "paywall_rules.v1"


def test_no_output_holds_page_text_for_a_readable_page_or_a_refused_one(world: World) -> None:
    world.fetcher.add(URL, BODY)
    readable = [invoke("fetch", URL), invoke("--json", "--verbose", "fetch", URL)]
    add_short(world.fetcher)
    refused = [invoke("fetch", URL, "--refresh"), invoke("--json", "fetch", URL, "--refresh")]

    for result in [*readable, *refused]:
        assert SENTINEL not in result.stdout + result.stderr


def test_a_fetcher_that_cannot_run_exits_three_as_provider_unavailable(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(url: str) -> FetchResult:
        raise ProviderUnavailable("http-fetcher", "the HTTP client could not start")

    monkeypatch.setattr(world.fetcher, "fetch", unavailable)

    result = invoke("--json", "fetch", URL)

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE
    assert envelope(result)["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert world.connection.closed == 1


def test_a_string_that_is_not_a_source_url_exits_one_and_fetches_nothing(world: World) -> None:
    result = invoke("--json", "fetch", "mailto:desk@example.org")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "INVALID_SOURCE_URL"
    assert world.fetcher.requested_urls == []
    assert world.snapshot_count() == 0


# --------------------------------------------------------------------------------------------
# --refresh, and the connection
# --------------------------------------------------------------------------------------------


def test_a_second_run_answers_from_the_stored_snapshot_and_refresh_asks_the_publisher_again(
    world: World,
) -> None:
    world.fetcher.add(URL, BODY)
    first = envelope(invoke("--json", "fetch", URL))["data"]

    again = envelope(invoke("--json", "fetch", URL))["data"]
    refreshed = envelope(invoke("--json", "fetch", URL, "--refresh"))["data"]

    assert world.fetcher.requested_urls == [URL, URL]
    assert (again["fetched"], refreshed["fetched"]) == (False, True)
    assert again["snapshot"]["snapshot_id"] == first["snapshot"]["snapshot_id"]
    assert again["snapshot"]["reused"] is True
    assert world.snapshot_count() == 1


def test_each_run_closes_the_fetchers_connection(world: World) -> None:
    world.fetcher.add(URL, BODY)

    invoke("fetch", URL)
    invoke("fetch", "https://www.example.org/missing")

    assert world.connection.closed == 2


# --------------------------------------------------------------------------------------------
# The command line: a fetch or a paste, never both, never neither
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        pytest.param(("fetch",), id="nothing-to-do"),
        pytest.param(("fetch", URL, "--paste", "-", "--source-url", URL), id="paste-with-a-url-paste"),
        pytest.param(("fetch", "--paste", "-"), id="paste-without-source-url"),
        pytest.param(("fetch", "--paste", "-", "--source-url", URL, "--refresh"), id="paste-with-refresh"),
        pytest.param(("fetch", URL, "--source-url", URL), id="source-url-without-paste"),
        pytest.param(("fetch", URL, "--i-have-lawful-access"), id="attestation-without-paste"),
    ],
)
def test_a_command_line_that_asks_for_both_or_neither_is_a_usage_error(
    world: World, arguments: tuple[str, ...]
) -> None:
    result = invoke(*arguments, stdin=BODY.decode())

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert world.fetcher.requested_urls == []
    assert world.snapshot_count() == 0


# --------------------------------------------------------------------------------------------
# --paste: USER_SUPPLIED, and only after attestation
# --------------------------------------------------------------------------------------------


def write_text(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "article.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_paste_with_the_attestation_flag_stores_user_supplied_text_and_fetches_nothing(
    world: World, tmp_path: Path
) -> None:
    pasted = write_text(tmp_path, BODY.decode())

    result = invoke("fetch", "--paste", str(pasted), "--source-url", URL, "--i-have-lawful-access")

    assert result.exit_code == ExitCode.OK, result.output
    assert "USER_SUPPLIED" in result.stdout
    assert world.fetcher.requested_urls == []
    (stored,) = world.articles._snapshots.values()  # pyright: ignore[reportPrivateUsage]
    assert stored.provenance_mode is ProvenanceMode.USER_SUPPLIED
    assert SENTINEL not in result.stdout + result.stderr


def test_paste_from_stdin_in_json_reports_user_supplied_in_the_schema(world: World) -> None:
    result = invoke(
        "--json", "fetch", "--paste", "-", "--source-url", URL, "--i-have-lawful-access", stdin=BODY.decode()
    )

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert (data["provenance_mode"], data["snapshot"]["provenance_mode"]) == (
        "USER_SUPPLIED",
        "USER_SUPPLIED",
    )
    assert (data["access_status"], data["fetched"]) == (AccessStatus.UNKNOWN.value, False)
    assert data["snapshot"]["paragraph_count"] == 3
    assert data["snapshot"]["sha256"] == hashlib.sha256(BODY).hexdigest()


def test_paste_where_no_prompt_can_be_shown_and_no_flag_stores_nothing_and_exits_one(
    world: World, tmp_path: Path
) -> None:
    """stdin is not a terminal here (the fixture says so), so nobody can answer a prompt."""
    pasted = write_text(tmp_path, BODY.decode())

    result = invoke("fetch", "--paste", str(pasted), "--source-url", URL)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "USER_TEXT_NOT_ATTESTED" in result.stderr
    assert "--i-have-lawful-access" in result.stderr
    assert "Store this text" not in result.output
    assert world.snapshot_count() == 0


def test_paste_from_stdin_never_prompts_even_at_a_terminal(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The text is stdin, so stdin cannot also answer the question."""
    monkeypatch.setattr(fetch_command, "stdin_is_a_terminal", lambda: True)

    result = invoke("fetch", "--paste", "-", "--source-url", URL, stdin=BODY.decode())

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert "Store this text" not in result.output
    assert world.snapshot_count() == 0


def test_paste_in_json_mode_never_prompts_even_at_a_terminal(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetch_command, "stdin_is_a_terminal", lambda: True)
    pasted = write_text(tmp_path, BODY.decode())

    result = invoke("--json", "fetch", "--paste", str(pasted), "--source-url", URL, stdin="y\n")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "USER_TEXT_NOT_ATTESTED"
    assert world.snapshot_count() == 0


@pytest.mark.parametrize(("answer", "exit_code", "stored"), [("y\n", 0, 1), ("n\n", 1, 0), ("\n", 1, 0)])
def test_paste_at_a_terminal_asks_for_the_attestation_and_stores_only_on_yes(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, answer: str, exit_code: int, stored: int
) -> None:
    monkeypatch.setattr(fetch_command, "stdin_is_a_terminal", lambda: True)
    pasted = write_text(tmp_path, BODY.decode())

    result = invoke("fetch", "--paste", str(pasted), "--source-url", URL, stdin=answer)

    assert f"Store this text as USER_SUPPLIED for {URL}?" in result.stderr
    assert result.exit_code == exit_code, result.output
    assert world.snapshot_count() == stored


def test_paste_of_text_too_short_for_an_article_is_rejected_and_stores_nothing(
    world: World, tmp_path: Path
) -> None:
    pasted = write_text(tmp_path, f"Only a {SENTINEL} line.")

    result = invoke("--json", "fetch", "--paste", str(pasted), "--source-url", URL, "--i-have-lawful-access")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "USER_TEXT_REJECTED"
    assert world.snapshot_count() == 0
    assert SENTINEL not in result.stdout + result.stderr


def test_paste_for_a_string_that_is_not_a_source_url_exits_one(world: World, tmp_path: Path) -> None:
    pasted = write_text(tmp_path, BODY.decode())

    result = invoke(
        "--json", "fetch", "--paste", str(pasted), "--source-url", "news", "--i-have-lawful-access"
    )

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "INVALID_SOURCE_URL"
    assert world.snapshot_count() == 0
