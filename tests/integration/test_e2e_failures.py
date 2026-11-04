"""`cut` on each kind of source, and every way the V1 path fails out loud (`v1-e09-t05` ac2).

Through the CLI's own entry point, over the recordings `e2e_harness.py` names:

* **`cut <URL>`** on a news article, a think-tank report, a government PDF and an open-access journal
  PDF. Three verify. The government PDF (`government-pdf`, added for this suite) names no author,
  title, publication or date a PDF can carry, so its card is cut and exported UNVERIFIED with
  `CITATION_UNVERIFIED`, exit 4: the cite is never filled in from nothing.
* **A paywalled and a robots-disallowed URL**: exit 3, `SOURCE_NOT_ACCESSIBLE`, with the access
  status, no card and no file. The disallowed page is never requested.
* **A provider outage**: OpenAlex answers 503, the publisher feed answers, and the search is PARTIAL,
  exit 6, `SEARCH_PARTIAL`, naming the provider that failed.
* **A hand-edited DOCX**: one evidence word changed in an exported card makes `verify` find it
  UNVERIFIED with `MANUAL_EDIT`, exit 1, while the untouched file still verifies.

Exit codes and codes are the CLI's documented ones (`debate_cli.exit_codes`, the CLI README); each
test asserts the code and the reason, never a message's wording. Expected evidence is the second
paragraph of t04's hand-written extraction, which EveryPageRouter selects whole; the government
PDF's is this task's hand-written `gov-annual-report.expected.json`. Which pages verify is
`packages/debate_cli/tests/fixtures/search/README.md`'s and `tests/fixtures/citation/README.md`'s.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import docx
import pytest
from tests.fixtures.extraction.expected_output import load_expected
from tests.integration.e2e_harness import Boundaries, Cli

from debate_cli.exit_codes import ExitCode
from debate_core.evidence.docx_manifest_part import read_embedded_manifest_bytes

pytestmark = pytest.mark.slow

NEED: Final = "what this source says about the need"
ARGUMENT: Final = "End-to-end suite"


@dataclass(frozen=True)
class Source:
    kind: str
    url: str
    sample: str
    """The t04 (or this task's) sample whose hand-written paragraphs the page extracts to."""
    exit_code: int
    status: str
    reasons: tuple[str, ...]


SOURCES: Final = (
    Source(
        "news",
        "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter",
        "news-article",
        ExitCode.OK,
        "VERIFIED",
        (),
    ),
    Source(
        "think-tank",
        "https://www.harwell-institute.example/research/opportunity-cost-of-de-extinction",
        "think-tank-report",
        ExitCode.OK,
        "VERIFIED",
        (),
    ),
    Source(
        "government PDF",
        "https://www.fosw.example.gov/files/2026/habitat-grants-annual-report.pdf",
        "gov-annual-report",
        ExitCode.CARD_UNVERIFIED,
        "UNVERIFIED",
        ("CITATION_UNVERIFIED",),
    ),
    Source(
        "open-access journal",
        "https://journal.synthetic-conservation.example/doi/pdf/10.5555/jscs.2026.0012",
        "journal-article",
        ExitCode.OK,
        "VERIFIED",
        (),
    ),
)

PAYWALLED: Final = "https://www.harborreview.example/politics/2026/10/inside-the-tariff-talks"
ROBOTS: Final = "https://www.closed-stacks.example/archive/2026/water-rights-ruling"

COURIER_ROWS: Final = {
    "Midterm elections tighten as health insurance costs rise",
    "Policy Center: turnout in the 2026 midterm elections",
}
"""The feed's two items matching `midterm elections` since 2026-09-14 (fixtures/search/README.md)."""

EDITED_WORD: Final = ("surrogate", "synthetic")
"""A word of the news article's second paragraph, and what a student types over it."""


def cut(cli: Cli, url: str, out: Path) -> tuple[Any, dict[str, Any]]:
    return cli.envelope("cut", url, "--need", NEED, "--argument", ARGUMENT, "--output", str(out))


def card_in(path: Path) -> dict[str, Any]:
    (card,) = json.loads(read_embedded_manifest_bytes(path))["cards"]
    found: dict[str, Any] = card
    return found


@pytest.mark.parametrize("source", SOURCES, ids=[source.kind for source in SOURCES])
def test_cut_writes_each_kind_of_sources_card_from_its_snapshot_and_verify_agrees(
    cli: Cli, boundaries: Boundaries, tmp_path: Path, source: Source
) -> None:
    out = tmp_path / "card.docx"

    result, envelope = cut(cli, source.url, out)

    assert result.exit_code == source.exit_code, result.output
    data = envelope["data"] if source.status == "VERIFIED" else envelope["error"]["details"]
    assert (data["status"], data["source"]["access_status"]) == (source.status, "ACCESSIBLE")
    assert tuple(reason["reason"] for reason in data["reasons"]) == source.reasons
    if source.exit_code == ExitCode.CARD_UNVERIFIED:
        assert envelope["error"]["code"] == "CARD_UNVERIFIED"
    card = card_in(out)
    assert card["card_id"] == data["card_id"]
    assert card["evidence_text"] == load_expected(source.sample)["paragraphs"][1]

    verified, report = cli.envelope("verify", str(out))

    if source.status == "VERIFIED":
        assert verified.exit_code == ExitCode.OK, verified.output
        verdicts = report["data"]["cards"]
    else:
        assert verified.exit_code == ExitCode.DOMAIN_FAILURE, verified.output
        assert report["error"]["code"] == "UNVERIFIED"
        verdicts = report["error"]["details"]["cards"]
    assert [(verdict["status"], tuple(verdict["reason_codes"])) for verdict in verdicts] == [
        (source.status, source.reasons)
    ]


@pytest.mark.parametrize(("url", "access_status"), [(PAYWALLED, "PAYWALLED"), (ROBOTS, "ROBOTS_DISALLOWED")])
def test_cut_of_a_paywalled_or_robots_disallowed_url_exits_3_with_its_access_status_and_writes_nothing(
    cli: Cli, boundaries: Boundaries, tmp_path: Path, url: str, access_status: str
) -> None:
    out = tmp_path / "card.docx"

    result, envelope = cut(cli, url, out)
    shown = cli.run("cut", url, "--need", NEED, "--argument", ARGUMENT, "--output", str(out))

    assert result.exit_code == shown.exit_code == ExitCode.RETRIEVAL_FAILURE == 3
    error = envelope["error"]
    assert (error["code"], error["exit_code"], error["details"]["access_status"]) == (
        "SOURCE_NOT_ACCESSIBLE",
        3,
        access_status,
    )
    assert "SOURCE_NOT_ACCESSIBLE" in shown.stderr
    assert access_status in shown.stderr
    assert not out.exists()
    if access_status == "ROBOTS_DISALLOWED":
        assert url not in boundaries.pages.requested


def test_a_provider_outage_makes_the_search_partial_exit_6_naming_the_provider(
    cli: Cli, boundaries: Boundaries
) -> None:
    boundaries.providers.works_body = "openalex_works.body.json"
    boundaries.providers.openalex_status = 503
    arguments = ("search", "midterm elections", "--since", "2026-09-14", "--providers", "openalex,rss")

    result, envelope = cli.envelope(*arguments)
    shown = cli.run(*arguments)

    assert result.exit_code == shown.exit_code == ExitCode.SEARCH_PARTIAL == 6
    error = envelope["error"]
    assert (error["code"], error["exit_code"], error["details"]["status"]) == ("SEARCH_PARTIAL", 6, "PARTIAL")
    outcomes = {entry["provider"]: entry["outcome"] for entry in error["details"]["providers"]}
    assert outcomes == {"openalex": "error", "rss": "ok"}
    assert {item["title"] for item in error["details"]["results"]} == COURIER_ROWS
    assert "SEARCH_PARTIAL" in shown.stderr
    assert "Providers: PARTIAL" in shown.stdout
    assert "openalex: error" in shown.stdout


def hand_edit(exported: Path, edited: Path, word: str, replacement: str) -> None:
    """`exported` with the first run holding `word` changed to `replacement`, as Word would save it."""
    document = docx.Document(io.BytesIO(exported.read_bytes()))
    run = next(run for paragraph in document.paragraphs for run in paragraph.runs if word in run.text)
    run.text = run.text.replace(word, replacement, 1)
    document.save(str(edited))


def test_a_hand_edited_evidence_word_in_an_exported_docx_makes_verify_fail_with_manual_edit(
    cli: Cli, boundaries: Boundaries, tmp_path: Path
) -> None:
    news = SOURCES[0]
    exported = tmp_path / "card.docx"
    assert cut(cli, news.url, exported)[0].exit_code == ExitCode.OK
    word, replacement = EDITED_WORD
    assert word in card_in(exported)["evidence_text"]
    edited = tmp_path / "edited.docx"
    exported_bytes = exported.read_bytes()
    hand_edit(exported, edited, word, replacement)

    untouched, _ = cli.envelope("verify", str(exported))
    result, envelope = cli.envelope("verify", str(edited))
    shown = cli.run("verify", str(edited))

    assert untouched.exit_code == ExitCode.OK, untouched.output
    assert exported.read_bytes() == exported_bytes
    assert result.exit_code == shown.exit_code == ExitCode.DOMAIN_FAILURE == 1
    assert envelope["error"]["code"] == "UNVERIFIED"
    (verdict,) = envelope["error"]["details"]["cards"]
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["MANUAL_EDIT"])
    assert "MANUAL_EDIT" in shown.stdout
