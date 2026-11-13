"""`debate-research cut`, offline, through Typer's runner, the real app and the real composition root.

Everything is the production wiring (`v1-e06-t06`): the polite HTTP fetcher, the extractors and the
access classifier, ArticleService, CardService with the production selector and structured-output
guard, CitationService, the evidence verifier, ExportService with the DOCX renderer, the SQLite file
and the blob store, in a data directory of each test's own. Three seams are replaced, each by its
container name:

* `article_fetch_transport`: v1-e04-t06's :class:`~tests.fixtures.http.cassettes.ReplayTransport`
  over the committed cassettes, which answers from them and sends nothing;
* `crossref_transport`: v1-e06-t01's respx-backed `CrossrefAnswers`, which answers only the DOIs a
  test serves and keeps every request, so no lookup leaves;
* `card_model_router`, only where a test says so: a counting wrapper, or scripted answers for a
  refused markup or a refused call. Otherwise the container builds the `test` profile's router, the
  fixture fake over the committed `tests/fixtures/model_outputs/`.

Expected values are written by hand: the tag is the committed `card.select` answer's, the cite is
`tests/fixtures/citation/news-article.expected.json`'s with this test's clock as the accessed date,
the evidence is v1-e06-t02's `EVIDENCE` (P2's first sentence and all of P3), and the underlined
passages are the committed `card.markup` answer's offsets read off t04's paragraphs by hand.
"""

from __future__ import annotations

import gc
import hashlib
import io
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import docx
import httpx
import pytest
from tests.fixtures.card.card_world import (
    MODEL_OUTPUTS,
    NEWS_ARGUMENT,
    NEWS_NEED,
    CountingRouter,
    paragraphs_of,
)
from tests.fixtures.citation.citation_world import CrossrefAnswers
from tests.fixtures.http.cassettes import ReplayTransport, cassette_names, load_cassette
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.errors import (
    ModelAccessDenied,
    ModelRequestRejected,
    ProviderRateLimited,
    ProviderUnavailable,
)
from debate_core.application.ports.model_router import ModelRouter
from debate_core.evidence.docx_manifest_part import read_embedded_manifest_bytes

# Imported here, before pytest-socket is armed: urllib3 (through trafilatura) probes for IPv6 with a
# socket when it is first imported, which the container would otherwise do inside a test.
from debate_core.integrations import html_extractor as html_extractor
from debate_core.integrations.models.fake_router import FakeModelRouter
from debate_core.testing.fakes.model_router import ScriptedModelRouter

runner = CliRunner()

NOW: Final = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
"""The container's clock in every test: the retrieval time, so the cite's accessed date."""

NEWS_URL: Final = (
    "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter"
)
NEWS_CANONICAL: Final = "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away"
PAYWALLED_URL: Final = "https://www.harborreview.example/politics/2026/10/inside-the-tariff-talks"

TAG: Final = "Each delay in reviving the mammoth costs living elephants funding"
"""The committed `card.select` answer's tag for the news article."""
SHORT_CITE: Final = "Whitfield 26"
FULL_CITE: Final = (
    'Whitfield 26 [Dana Whitfield; "Scientists Say Mammoth Revival Is Years Away"; The Daily Meridian; '
    f"September 14, 2026; {NEWS_CANONICAL}; accessed October 26, 2026]"
)
EVIDENCE: Final = (
    "The delay follows two years of failed attempts to grow edited elephant embryos to term in surrogate "
    "animals.Conservation biologists who have criticized the project said the timeline was never "
    "realistic. “Every year this slips, the money raised for it is money that did not go to elephants "
    "that are alive now,” said Priya Ramaswamy, who studies elephant populations and was not involved "
    "in the work."
)
UNDERLINED: Final = [
    "failed attempts to grow edited elephant embryos to term",
    "the timeline was never realistic",
    "the money raised for it is money that did not go to elephants that are alive now",
]
"""P2 31-86, P3 61-93 and P3 119-199 of the committed `card.markup` answer, read off t04's paragraphs."""
EVIDENCE_WORD: Final = "surrogate"
"""A word of the evidence that is in neither the tag nor the cite: no stdout may contain it."""

STAGES: Final = ["fetch", "extract", "select", "verify", "export"]

REFUSED_MARKUP: Final[dict[str, Any]] = {
    "spans": [
        {"paragraph": 3, "start_offset": 119, "end_offset": 199, "style": "highlight", "purpose": "impact"}
    ],
    "rationale": "The highlight carries the lost funding.",
}
"""A highlight with no underline beneath it, which the markup guard refuses (v1-e06-t02's e2e test)."""
UNVERIFIED_BANNER: Final = (
    "UNVERIFIED — not a finished card: MODEL_OUTPUT_INVALID, EVIDENCE_UNVERIFIED, CARD_INCOMPLETE"
)
"""Each failure's code, then the verifier's code it carries, once each (ExportService, `v1-e06-t04`)."""


def committed_selection() -> dict[str, Any]:
    """The committed `card.select` answer for the news article."""
    path = next((MODEL_OUTPUTS / "card.select").glob("8ad9c020*.json"))
    output: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))["output"]
    return output


@dataclass
class Seams:
    """What each container the app builds is given in place of the network and, if set, the model."""

    transport: ReplayTransport
    router: ModelRouter | None = None
    crossref: CrossrefAnswers = field(default_factory=CrossrefAnswers)
    expected_lookups: list[str] = field(default_factory=list[str])
    """The Crossref requests a test expects, in order; none unless it says so."""


@pytest.fixture
def seams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Seams]:
    for name in [name for name in __import__("os").environ if name.startswith("DEBATE_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(tmp_path / "data"))
    # robots.txt and the page are two requests to one host; the polite interval would sleep between them.
    monkeypatch.setenv("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS", "0")
    seams = Seams(ReplayTransport(load_cassette(name) for name in cassette_names()))
    build = ServiceContainer.__init__

    def with_seams(self: ServiceContainer, **arguments: Any) -> None:
        build(self, **arguments)
        self.override("article_fetch_transport", seams.transport)
        self.override("crossref_transport", httpx.MockTransport(seams.crossref.handle))
        self.override("clock", lambda: NOW)
        if seams.router is not None:
            self.override("card_model_router", seams.router)

    monkeypatch.setattr(ServiceContainer, "__init__", with_seams)
    yield seams
    assert seams.transport.unrecorded == [], "a request no cassette recorded"
    assert [str(request.url) for request in seams.crossref.requests] == seams.expected_lookups


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "out.docx"


def cut(*arguments: str, json_output: bool = False) -> Result:
    return runner.invoke(create_app(), [*(["--json"] if json_output else []), "cut", *arguments])


def cut_news(out: Path, *options: str, json_output: bool = False) -> Result:
    return cut(
        NEWS_URL,
        "--need",
        NEWS_NEED,
        "--argument",
        NEWS_ARGUMENT,
        "--format",
        "team-default",
        "--output",
        str(out),
        *options,
        json_output=json_output,
    )


def envelope(result: Result) -> dict[str, Any]:
    lines = result.stdout.splitlines()
    assert len(lines) == 1, f"--json must print exactly one line on stdout, got: {result.stdout!r}"
    document: dict[str, Any] = json.loads(lines[0])
    return document


def stored_cards(data_dir: Path) -> list[dict[str, Any]]:
    """Every card row in the data directory's SQLite file."""
    gc.collect()
    database = data_dir / "debate.sqlite3"
    if not database.exists():
        return []
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        return [json.loads(row[0]) for row in connection.execute("SELECT document FROM cards")]


@dataclass(frozen=True)
class ReadParagraph:
    style_id: str
    text: str
    underlined: list[str]
    """Each stretch of consecutive runs in the underline character style, joined."""


def read_paragraphs(path: Path) -> list[ReadParagraph]:
    document = docx.Document(io.BytesIO(path.read_bytes()))
    paragraphs: list[ReadParagraph] = []
    for paragraph in document.paragraphs:
        stretches: list[str] = []
        previous = False
        for run in paragraph.runs:
            properties = run.element.rPr
            style = (
                properties.rStyle.val if properties is not None and properties.rStyle is not None else None
            )
            underlined = style == "StyleUnderline"
            if underlined and previous:
                stretches[-1] += run.text
            elif underlined:
                stretches.append(run.text)
            previous = underlined
        style = paragraph.style
        assert style is not None
        paragraphs.append(ReadParagraph(style.style_id, paragraph.text, stretches))
    return paragraphs


def embedded_manifest(path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(read_embedded_manifest_bytes(path))
    return manifest


# --------------------------------------------------------------------------------------------
# The help
# --------------------------------------------------------------------------------------------


def test_the_help_documents_every_option_and_exit_code() -> None:
    result = runner.invoke(create_app(), ["cut", "--help"])

    assert result.exit_code == ExitCode.OK
    for option in ("--need", "--argument", "--format", "--output", "--json"):
        assert option in result.stdout
    for line in (
        "0  the card is VERIFIED",
        "1  could not run, nothing saved",
        "2  usage error",
        "3  PAYWALLED, BLOCKED, ROBOTS_DISALLOWED, NOT_FOUND",
        "4  the card is UNVERIFIED",
    ):
        assert line in result.stdout


# --------------------------------------------------------------------------------------------
# A verified card: exit 0, and the .docx (ac1)
# --------------------------------------------------------------------------------------------


def test_a_verified_card_exit_code_is_0_and_the_docx_holds_tag_cite_underlined_evidence_and_manifest(
    seams: Seams, data_dir: Path, out: Path
) -> None:
    result = cut_news(out)

    assert result.exit_code == ExitCode.OK, result.output
    paragraphs = read_paragraphs(out)
    assert [(p.style_id, p.text) for p in paragraphs[:2]] == [("Heading4", TAG), ("Normal", FULL_CITE)]
    assert paragraphs[2].underlined == UNDERLINED
    assert len(paragraphs) == 3, "a VERIFIED card has no banner"

    [card] = stored_cards(data_dir)
    manifest = embedded_manifest(out)
    [embedded] = manifest["cards"]
    assert (embedded["card_id"], embedded["verification_status"]) == (card["card_id"], "VERIFIED")
    assert (embedded["tag"], embedded["evidence_text"], embedded["format_profile"]) == (
        TAG,
        EVIDENCE,
        "team-default",
    )
    assert [snapshot["snapshot_id"] for snapshot in manifest["snapshots"]] == [embedded["snapshot_id"]]
    assert card["card_id"] in result.stdout


def test_the_embedded_manifest_verifies_against_the_stored_snapshot(
    seams: Seams, out: Path, tmp_path: Path
) -> None:
    assert cut_news(out).exit_code == ExitCode.OK
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(read_embedded_manifest_bytes(out))

    result = runner.invoke(create_app(), ["verify", str(manifest)])

    assert result.exit_code == ExitCode.OK, result.output


@pytest.mark.parametrize("profile", ["team-default", "flow", "plain"])
def test_every_shipped_format_profile_writes_the_card(seams: Seams, tmp_path: Path, profile: str) -> None:
    out = tmp_path / f"{profile}.docx"

    result = cut(
        NEWS_URL, "--need", NEWS_NEED, "--argument", NEWS_ARGUMENT, "--format", profile, "--output", str(out)
    )

    assert result.exit_code == ExitCode.OK, result.output
    assert embedded_manifest(out)["cards"][0]["format_profile"] == profile


JOURNAL_PDF_URL: Final = "https://journal.synthetic-conservation.example/doi/pdf/10.5555/jscs.2026.0012"
JOURNAL_DOI: Final = "10.5555/jscs.2026.0012"
JOURNAL_FULL_CITE: Final = (
    "Okonkwo-Hale et al. 26 [Rhea Okonkwo-Hale and Tomas Lindqvist (Rhea Okonkwo-Hale, Department of "
    'Ecology, University of Synthetic Studies); "Moral Hazard and the Return of Lost Species"; Journal of '
    f"Synthetic Conservation Studies; April 20, 2026; {JOURNAL_PDF_URL}; accessed October 26, 2026]"
)
"""`tests/fixtures/citation/open-access-pdf.expected.json`'s full cite: every field from Crossref's answer."""
JOURNAL_SELECTION: Final[dict[str, Any]] = {
    "passages": [{"first_paragraph": 13, "last_paragraph": 13, "start_offset": 0, "end_offset": None}],
    "tag": {
        "text": "Revival funding cannot replace habitat protection",
        "argument_role": "link",
        "need_alignment": "direct",
        "confidence": 0.8,
    },
    "rationale": "Paragraph 13 concludes that revival is no replacement for protection.",
    "confidence": 0.75,
}
JOURNAL_MARKUP: Final[dict[str, Any]] = {
    "spans": [
        {"paragraph": 13, "start_offset": 0, "end_offset": 50, "style": "underline", "purpose": "claim"}
    ],
    "rationale": "The underline is the conclusion.",
}
"""P13 whole, underlined 0-50: "De-extinction is not a substitute for conservation", t04's paragraph."""


def test_a_journal_pdf_is_cited_from_crossref_through_the_file_cache_and_asked_once(
    seams: Seams, data_dir: Path, tmp_path: Path
) -> None:
    seams.crossref.serve(JOURNAL_DOI, "works-10.5555-jscs.2026.0012.json")
    seams.expected_lookups = [f"https://api.crossref.org/works/{JOURNAL_DOI}"]
    seams.router = ScriptedModelRouter([JOURNAL_SELECTION, JOURNAL_MARKUP, JOURNAL_SELECTION, JOURNAL_MARKUP])
    first, again = tmp_path / "first.docx", tmp_path / "again.docx"

    results = [cut(JOURNAL_PDF_URL, "--need", NEWS_NEED, "--output", str(path)) for path in (first, again)]

    assert [result.exit_code for result in results] == [ExitCode.OK, ExitCode.OK], results[0].output
    for path in (first, again):
        paragraphs = read_paragraphs(path)
        assert (paragraphs[1].text, paragraphs[2].underlined) == (
            JOURNAL_FULL_CITE,
            ["De-extinction is not a substitute for conservation"],
        )
    assert [path.name for path in (data_dir / "crossref").iterdir()] != [], "the answer is kept on disk"


def test_progress_names_each_stage_in_order_on_stderr(seams: Seams, out: Path) -> None:
    result = cut_news(out)

    assert result.exit_code == ExitCode.OK, result.output
    words = [line.split()[0] for line in result.stderr.splitlines() if line.strip()]
    assert [word for word in words if word in STAGES] == STAGES
    for stage in STAGES:
        assert stage not in [line.split()[0] for line in result.stdout.splitlines() if line.strip()]


# --------------------------------------------------------------------------------------------
# A source that cannot be retrieved: exit 3, nothing written (ac2)
# --------------------------------------------------------------------------------------------


def test_a_paywalled_url_exit_code_is_3_with_its_status_and_canonical_url_and_no_docx(
    seams: Seams, data_dir: Path, out: Path
) -> None:
    counting = CountingRouter(FakeModelRouter(MODEL_OUTPUTS))
    seams.router = counting

    result = cut(PAYWALLED_URL, "--need", NEWS_NEED, "--output", str(out))

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.output
    assert "PAYWALLED" in result.stderr
    assert PAYWALLED_URL in result.stderr.replace("\n", "").replace("│", "").replace(" ", "")
    assert not out.exists()
    assert stored_cards(data_dir) == []
    assert counting.calls == [], "no model is asked about a source that cannot be cut"


@pytest.mark.parametrize(
    ("url", "status"),
    [
        ("https://www.northwindpost.example/world/2026/10/ferry-strike-ends", "BLOCKED"),
        ("https://www.closed-stacks.example/archive/2026/water-rights-ruling", "ROBOTS_DISALLOWED"),
        ("https://www.prairiedispatch.example/news/2026/10/county-fair-moved", "NOT_FOUND"),
    ],
)
def test_every_other_retrieval_status_exit_code_is_3_and_writes_nothing(
    seams: Seams, data_dir: Path, out: Path, url: str, status: str
) -> None:
    result = cut(url, "--need", NEWS_NEED, "--output", str(out), json_output=True)

    assert result.exit_code == ExitCode.RETRIEVAL_FAILURE, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"], error["details"]["access_status"]) == (
        "SOURCE_NOT_ACCESSIBLE",
        3,
        status,
    )
    assert error["details"]["canonical_url"] == url
    assert not out.exists()
    assert stored_cards(data_dir) == []


# --------------------------------------------------------------------------------------------
# An UNVERIFIED card: exit 4, every reason, the banner (ac3)
# --------------------------------------------------------------------------------------------


def test_an_unverified_card_exit_code_is_4_with_each_reason_printed_and_the_banner_in_the_docx(
    seams: Seams, data_dir: Path, out: Path
) -> None:
    seams.router = ScriptedModelRouter([committed_selection(), REFUSED_MARKUP, REFUSED_MARKUP])

    result = cut_news(out)

    assert result.exit_code == ExitCode.CARD_UNVERIFIED, result.output
    for code in ("MODEL_OUTPUT_INVALID", "EVIDENCE_UNVERIFIED", "CARD_INCOMPLETE"):
        assert code in result.stderr
    assert "card.markup@1.0.0 was refused" in result.stderr
    paragraphs = read_paragraphs(out)
    assert UNVERIFIED_BANNER in [p.text for p in paragraphs]
    [card] = stored_cards(data_dir)
    assert card["verification_status"] == "UNVERIFIED"
    assert embedded_manifest(out)["cards"][0]["verification_status"] == "UNVERIFIED"


def test_an_unverified_card_under_json_exit_code_is_4_with_the_reasons_in_the_error(
    seams: Seams, out: Path
) -> None:
    seams.router = ScriptedModelRouter([committed_selection(), REFUSED_MARKUP, REFUSED_MARKUP])

    result = cut_news(out, json_output=True)

    assert result.exit_code == ExitCode.CARD_UNVERIFIED, result.output
    document = envelope(result)
    assert (document["status"], document["data"]) == ("error", None)
    error = document["error"]
    assert (error["code"], error["exit_code"]) == ("CARD_UNVERIFIED", 4)
    details = error["details"]
    assert details["status"] == "UNVERIFIED"
    assert [(reason["reason"], reason["verifier_code"]) for reason in details["reasons"]] == [
        ("MODEL_OUTPUT_INVALID", None),
        ("EVIDENCE_UNVERIFIED", "CARD_INCOMPLETE"),
    ]
    assert details["output"] == str(out)
    assert EVIDENCE_WORD not in result.stdout


# --------------------------------------------------------------------------------------------
# --json: one object on stdout, progress on stderr (ac4)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("placement", ["before the command", "after it"])
def test_json_writes_one_object_to_stdout_and_progress_to_stderr(
    seams: Seams, data_dir: Path, out: Path, placement: str
) -> None:
    result = cut_news(out, json_output=True) if placement == "before the command" else cut_news(out, "--json")

    assert result.exit_code == ExitCode.OK, result.output
    document = envelope(result)
    assert (document["status"], document["command"], document["error"]) == ("ok", "cut", None)
    data = document["data"]
    [card] = stored_cards(data_dir)
    assert (data["card_id"], data["status"], data["reasons"]) == (
        card["card_id"],
        "VERIFIED",
        [],
    )
    assert (data["output"], data["format_profile"]) == (str(out), "team-default")
    assert data["source"]["canonical_url"] == NEWS_CANONICAL
    assert [call["prompt_id"] for call in data["model_calls"]] == ["card.select", "card.markup"]
    manifest = data["manifest"]
    assert manifest["card_ids"] == [card["card_id"]]
    assert manifest["manifest_version"] == embedded_manifest(out)["manifest_version"]
    assert [snapshot["snapshot_id"] for snapshot in manifest["snapshots"]] == [card["snapshot_id"]]
    events = [json.loads(line) for line in result.stderr.splitlines() if line.strip()]
    assert [event["event"] for event in events] == STAGES
    assert {event["command"] for event in events} == {"cut"}
    assert EVIDENCE_WORD not in result.stdout


# --------------------------------------------------------------------------------------------
# A cut that could not run: nothing saved, no card id (ac5 and the PM's exit-code ruling)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("failure", "code", "exit_code"),
    [
        (ModelAccessDenied("bedrock", "planted-model", "no credentials"), "MODEL_ACCESS_DENIED", 1),
        (
            ModelRequestRejected("bedrock", "planted-model", "ValidationException", "temperature refused"),
            "MODEL_REQUEST_REJECTED",
            1,
        ),
        (ProviderUnavailable("bedrock"), "PROVIDER_UNAVAILABLE", 3),
        (ProviderRateLimited("bedrock", "throttled"), "PROVIDER_RATE_LIMITED", 3),
    ],
)
def test_a_model_call_that_failed_exit_code_is_its_own_and_saves_and_writes_nothing(
    seams: Seams, data_dir: Path, out: Path, failure: Exception, code: str, exit_code: int
) -> None:
    seams.router = ScriptedModelRouter([failure])

    result = cut_news(out, json_output=True)

    assert result.exit_code == exit_code, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"]) == (code, exit_code)
    assert not out.exists()
    assert stored_cards(data_dir) == []


def test_a_need_no_model_answer_was_recorded_for_exit_code_is_1_and_saves_nothing(
    seams: Seams, data_dir: Path, out: Path
) -> None:
    result = cut(NEWS_URL, "--need", "an answer nobody recorded", "--output", str(out), json_output=True)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert envelope(result)["error"]["code"] == "MISSING_FIXTURE_ERROR"
    assert not out.exists()
    assert stored_cards(data_dir) == []


# --------------------------------------------------------------------------------------------
# Usage errors: exit 2, nothing fetched
# --------------------------------------------------------------------------------------------


def test_an_unknown_format_profile_exit_code_is_2_names_the_profiles_and_fetches_nothing(
    seams: Seams, out: Path
) -> None:
    result = cut(NEWS_URL, "--need", NEWS_NEED, "--format", "fancy", "--output", str(out))

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert "flow, plain, team-default" in result.stderr.replace("\n", " ")
    assert seams.transport.requested == []
    assert not out.exists()


def test_a_cut_without_a_need_exit_code_is_2(seams: Seams, out: Path) -> None:
    result = cut(NEWS_URL, "--output", str(out))

    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert seams.transport.requested == []


# --------------------------------------------------------------------------------------------
# --from-paste: a card cut from the user's own stored copy (v1-e06-t08)
# --------------------------------------------------------------------------------------------

PASTED_TEXT: Final = "\n\n".join(paragraphs_of("news-article"))
"""t04's hand-written paragraphs of the news article, as a coach would paste their library copy.

The model is shown only the numbered text and the need, so the committed answers for the news article
answer for this copy too: the same tag, evidence and underlines as a publisher-retrieved cut."""
PASTED_FULL_CITE: Final = (
    f"[no author] 26 [September 14, 2026; {NEWS_CANONICAL}; accessed October 26, 2026; user-supplied text]"
)
"""By the citation rules (v1-e06-t01): a pasted copy holds no markup, so only its URL is read. The date
is the URL path's, the URL and accessed date the platform's record of what the user said, and nothing
names an author, title or publication (`fetch --paste` titles the article with its URL, which is never
taken as a title). The short cite falls back to "[no author]"; the note says whose text it is."""
PASTED_CITE_MARKS: Final = (
    "[author unverified] [title unverified] [publication unverified] [date unverified] [URL unverified] "
    "[accessed date unverified]"
)
"""The renderer's mark for each cite field shown unverified, or required and missing, in cite order
(v1-e06-t04): the credentials are neither shown nor required, so they have none."""
PASTED_CITE_FIELDS: Final = ["authors", "title", "publication", "published_at", "canonical_url"]
"""Every required cite field: none is verified for user-supplied text, missing or not."""
PASTED_BANNER: Final = "UNVERIFIED — not a finished card: CITATION_UNVERIFIED"


def paste(url: str, tmp_path: Path) -> dict[str, Any]:
    """Store `PASTED_TEXT` for `url` as the coach does, `fetch --paste`; the stored snapshot's summary."""
    pasted = tmp_path / "library-copy.txt"
    pasted.write_text(PASTED_TEXT, encoding="utf-8")
    result = runner.invoke(
        create_app(),
        ["--json", "fetch", "--paste", str(pasted), "--source-url", url, "--i-have-lawful-access"],
    )
    assert result.exit_code == ExitCode.OK, result.output
    snapshot: dict[str, Any] = envelope(result)["data"]["snapshot"]
    assert snapshot["provenance_mode"] == "USER_SUPPLIED"
    return snapshot


def cut_pasted(url: str, out: Path, *options: str, json_output: bool = False) -> Result:
    return cut(
        url,
        "--need",
        NEWS_NEED,
        "--argument",
        NEWS_ARGUMENT,
        "--output",
        str(out),
        "--from-paste",
        *options,
        json_output=json_output,
    )


def test_the_help_documents_from_paste_and_the_exit_code_for_no_pasted_copy() -> None:
    result = runner.invoke(create_app(), ["cut", "--help"])

    assert result.exit_code == ExitCode.OK
    flat = " ".join(result.stdout.split())
    assert "--from-paste" in flat
    assert "fetch --paste" in flat
    assert "no copy stored with fetch --paste" in flat


def test_a_card_cut_from_a_stored_pasted_copy_is_user_supplied_and_nothing_is_fetched(
    seams: Seams, data_dir: Path, out: Path, tmp_path: Path
) -> None:
    pasted = paste(NEWS_URL, tmp_path)

    result = cut_pasted(NEWS_URL, out, json_output=True)

    assert result.exit_code == ExitCode.CARD_UNVERIFIED, result.output
    assert seams.transport.requested == [], "cutting from a pasted copy asks no publisher"
    details = envelope(result)["error"]["details"]
    assert details["source"] == {
        "requested_url": NEWS_URL,
        "canonical_url": NEWS_CANONICAL,
        "access_status": "UNKNOWN",
        "provenance_mode": "USER_SUPPLIED",
        "fetched": False,
        "snapshot_id": pasted["snapshot_id"],
        "snapshot_reused": True,
    }
    [card] = stored_cards(data_dir)
    assert (card["provenance_mode"], card["snapshot_id"]) == ("USER_SUPPLIED", pasted["snapshot_id"])
    assert EVIDENCE_WORD not in result.stdout


def test_a_card_cut_from_a_pasted_copy_is_unverified_for_its_cite_alone(
    seams: Seams, data_dir: Path, out: Path, tmp_path: Path
) -> None:
    paste(NEWS_URL, tmp_path)

    result = cut_pasted(NEWS_URL, out, json_output=True)

    assert result.exit_code == ExitCode.CARD_UNVERIFIED, result.output
    details = envelope(result)["error"]["details"]
    assert details["status"] == "UNVERIFIED"
    assert [(r["reason"], r["verifier_code"], r["fields"]) for r in details["reasons"]] == [
        ("CITATION_UNVERIFIED", "CITATION_UNVERIFIED", PASTED_CITE_FIELDS)
    ]
    paragraphs = read_paragraphs(out)
    assert [(p.style_id, p.text) for p in paragraphs[:3]] == [
        ("Heading4", TAG),
        ("Normal", PASTED_BANNER),
        ("Normal", f"{PASTED_FULL_CITE} {PASTED_CITE_MARKS}"),
    ]
    assert paragraphs[3].underlined == UNDERLINED
    assert len(paragraphs) == 4
    [embedded] = embedded_manifest(out)["cards"]
    assert (embedded["evidence_text"], embedded["verification_status"]) == (EVIDENCE, "UNVERIFIED")


def test_the_manifest_of_a_card_cut_from_a_pasted_copy_records_user_supplied_and_references_that_copy(
    seams: Seams, out: Path, tmp_path: Path
) -> None:
    pasted = paste(NEWS_URL, tmp_path)

    assert cut_pasted(NEWS_URL, out).exit_code == ExitCode.CARD_UNVERIFIED

    manifest = embedded_manifest(out)
    [embedded] = manifest["cards"]
    assert (embedded["provenance_mode"], embedded["snapshot_id"]) == ("USER_SUPPLIED", pasted["snapshot_id"])
    assert manifest["snapshots"] == [
        {
            "snapshot_id": pasted["snapshot_id"],
            "sha256": hashlib.sha256(PASTED_TEXT.encode("utf-8")).hexdigest(),
            "normalized_text_hash": pasted["normalized_text_hash"],
            "normalizer_version": pasted["normalizer_version"],
            "extractor_version": "user-supplied-text-1",
            "retrieved_at": "2026-10-26T15:00:00Z",
            "canonical_url": NEWS_CANONICAL,
        }
    ]


def test_verify_finds_a_card_cut_from_a_pasted_copy_true_to_that_copy_and_unverified_for_its_cite_alone(
    seams: Seams, out: Path, tmp_path: Path
) -> None:
    paste(NEWS_URL, tmp_path)
    assert cut_pasted(NEWS_URL, out).exit_code == ExitCode.CARD_UNVERIFIED

    result = runner.invoke(create_app(), ["--json", "verify", str(out)])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    [card] = envelope(result)["error"]["details"]["cards"]
    assert (card["status"], card["reason_codes"]) == ("UNVERIFIED", ["CITATION_UNVERIFIED"])


def test_the_paste_progress_says_the_stored_copy_answered_and_nothing_was_fetched(
    seams: Seams, out: Path, tmp_path: Path
) -> None:
    paste(NEWS_URL, tmp_path)

    result = cut_pasted(NEWS_URL, out, json_output=True)

    events = [json.loads(line) for line in result.stderr.splitlines() if line.strip()]
    assert [event["event"] for event in events] == STAGES
    [fetched] = [event for event in events if event["event"] == "fetch"]
    assert (fetched["data"]["fetched"], fetched["data"]["provenance_mode"]) == (False, "USER_SUPPLIED")


def test_a_paywalled_source_can_be_pasted_and_cut_from_the_paste_as_the_fetch_hint_says(
    seams: Seams, data_dir: Path, out: Path, tmp_path: Path
) -> None:
    fetched = runner.invoke(create_app(), ["--json", "fetch", PAYWALLED_URL])
    assert fetched.exit_code == ExitCode.RETRIEVAL_FAILURE, fetched.output
    hint = envelope(fetched)["error"]["hint"]
    assert "--paste" in hint
    assert f"cut {PAYWALLED_URL} --from-paste" in hint
    requested = list(seams.transport.requested)
    pasted = paste(PAYWALLED_URL, tmp_path)

    result = cut_pasted(PAYWALLED_URL, out, json_output=True)

    assert result.exit_code == ExitCode.CARD_UNVERIFIED, result.output
    assert seams.transport.requested == requested, "the cut asked the publisher nothing"
    details = envelope(result)["error"]["details"]
    assert [reason["reason"] for reason in details["reasons"]] == ["CITATION_UNVERIFIED"]
    [card] = stored_cards(data_dir)
    assert (card["provenance_mode"], card["snapshot_id"]) == ("USER_SUPPLIED", pasted["snapshot_id"])


@pytest.mark.parametrize("stored", ["nothing", "only the publisher's snapshot"])
def test_from_paste_with_no_pasted_copy_stored_exits_1_with_the_fetch_paste_hint_and_fetches_nothing(
    seams: Seams, data_dir: Path, out: Path, stored: str
) -> None:
    counting = CountingRouter(FakeModelRouter(MODEL_OUTPUTS))
    seams.router = counting
    if stored == "only the publisher's snapshot":
        assert runner.invoke(create_app(), ["fetch", NEWS_URL]).exit_code == ExitCode.OK
    requested = list(seams.transport.requested)

    result = cut_pasted(NEWS_URL, out, json_output=True)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert (error["code"], error["exit_code"]) == ("NO_USER_SUPPLIED_COPY", 1)
    assert error["details"]["canonical_url"] == NEWS_CANONICAL
    assert f"fetch --paste FILE --source-url '{NEWS_URL}' --i-have-lawful-access" in error["hint"]
    assert seams.transport.requested == requested, "no fetch stands in for a missing pasted copy"
    assert counting.calls == []
    assert not out.exists()
    assert stored_cards(data_dir) == []


# --------------------------------------------------------------------------------------------
# --from-paste with cite fields stated at `fetch --paste` (v1-e06-t12)
# --------------------------------------------------------------------------------------------

STATED_OPTIONS: Final = (
    "--title",
    "Mammoth Money and the Elephants Left Waiting",
    "--author",
    "Mara Okonkwo-Lindqvist",
    "--author",
    "Teodor Brannigan",
    "--date",
    "2026-09-15",
    "--publication",
    "The Synthetic Science Weekly",
)
"""Invented cite fields, as a coach states them from their library copy."""
STATED_FULL_CITE: Final = (
    "Okonkwo-Lindqvist et al. 26 [Mara Okonkwo-Lindqvist and Teodor Brannigan; "
    '"Mammoth Money and the Elephants Left Waiting"; The Synthetic Science Weekly; September 15, 2026; '
    f"{NEWS_CANONICAL}; accessed October 26, 2026; user-supplied text]"
)
"""By the citation rules (v1-e06-t01) with the stated fields in place of the derived ones: the first
author's last name and "et al." for two, the authors joined with "and", the title quoted, the stated
date (not the URL path's 14th), then the URL, the accessed date and whose text it is."""
STATED_FIELDS: Final = ("authors", "title", "publication", "published_at")


def paste_stating(url: str, tmp_path: Path, *options: str) -> dict[str, Any]:
    """`PASTED_TEXT` stored for `url` with `fetch --paste` and `options`; the stored snapshot's summary."""
    pasted = tmp_path / "library-copy.txt"
    pasted.write_text(PASTED_TEXT, encoding="utf-8")
    result = runner.invoke(
        create_app(),
        ["--json", "fetch", "--paste", str(pasted), "--source-url", url, "--i-have-lawful-access", *options],
    )
    assert result.exit_code == ExitCode.OK, result.output
    snapshot: dict[str, Any] = envelope(result)["data"]["snapshot"]
    return snapshot


def cite_paragraph(out: Path) -> str:
    """The card's cite line, as written: the third paragraph, after the tag and the banner."""
    paragraphs = read_paragraphs(out)
    assert [(p.style_id, p.text) for p in paragraphs[:2]] == [("Heading4", TAG), ("Normal", PASTED_BANNER)]
    return paragraphs[2].text


def test_a_card_cut_from_a_paste_with_stated_fields_shows_them_in_its_cite_and_unverified_for_it_alone(
    seams: Seams, data_dir: Path, out: Path, tmp_path: Path
) -> None:
    paste_stating(NEWS_URL, tmp_path, *STATED_OPTIONS)

    result = cut_pasted(NEWS_URL, out, json_output=True)

    assert result.exit_code == ExitCode.CARD_UNVERIFIED, result.output
    details = envelope(result)["error"]["details"]
    assert details["status"] == "UNVERIFIED"
    assert [(r["reason"], r["verifier_code"], r["fields"]) for r in details["reasons"]] == [
        ("CITATION_UNVERIFIED", "CITATION_UNVERIFIED", PASTED_CITE_FIELDS)
    ]
    assert cite_paragraph(out) == f"{STATED_FULL_CITE} {PASTED_CITE_MARKS}"
    assert read_paragraphs(out)[3].underlined == UNDERLINED


def test_the_card_and_manifest_cut_from_a_paste_record_each_stated_field_unverified(
    seams: Seams, data_dir: Path, out: Path, tmp_path: Path
) -> None:
    paste_stating(NEWS_URL, tmp_path, *STATED_OPTIONS)

    assert cut_pasted(NEWS_URL, out).exit_code == ExitCode.CARD_UNVERIFIED

    [card] = stored_cards(data_dir)
    [embedded] = embedded_manifest(out)["cards"]
    for recorded in (card, embedded):
        assert recorded["verification_status"] == "UNVERIFIED"
        citation = recorded["citation"]
        assert [
            name for name, value in citation.items() if isinstance(value, dict) and value.get("verified")
        ] == []
        assert citation["authors"]["value"] == ["Mara Okonkwo-Lindqvist", "Teodor Brannigan"]
        assert {name: citation[name]["source"] for name in STATED_FIELDS} == dict.fromkeys(
            STATED_FIELDS, "heuristic"
        )
        assert citation["published_at"]["value"] == "2026-09-15T00:00:00Z"


def test_verify_finds_a_card_cut_from_a_paste_with_stated_fields_unverified_for_its_cite_alone(
    seams: Seams, out: Path, tmp_path: Path
) -> None:
    paste_stating(NEWS_URL, tmp_path, *STATED_OPTIONS)
    assert cut_pasted(NEWS_URL, out).exit_code == ExitCode.CARD_UNVERIFIED

    result = runner.invoke(create_app(), ["--json", "verify", str(out)])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    [card] = envelope(result)["error"]["details"]["cards"]
    assert (card["status"], card["reason_codes"]) == ("UNVERIFIED", ["CITATION_UNVERIFIED"])


def test_a_paste_stored_again_with_no_cite_options_is_cut_with_the_fields_stated_before(
    seams: Seams, out: Path, tmp_path: Path
) -> None:
    first = paste_stating(NEWS_URL, tmp_path, *STATED_OPTIONS)
    again = paste_stating(NEWS_URL, tmp_path)
    assert again["snapshot_id"] == first["snapshot_id"]

    assert cut_pasted(NEWS_URL, out).exit_code == ExitCode.CARD_UNVERIFIED

    assert cite_paragraph(out) == f"{STATED_FULL_CITE} {PASTED_CITE_MARKS}"


def test_a_paste_stored_again_with_other_cite_options_is_cut_with_exactly_those(
    seams: Seams, data_dir: Path, out: Path, tmp_path: Path
) -> None:
    paste_stating(NEWS_URL, tmp_path, *STATED_OPTIONS)
    newer = paste_stating(NEWS_URL, tmp_path, "--author", "Teodor Brannigan")

    assert cut_pasted(NEWS_URL, out).exit_code == ExitCode.CARD_UNVERIFIED

    [card] = stored_cards(data_dir)
    assert card["snapshot_id"] == newer["snapshot_id"]
    assert cite_paragraph(out) == (
        f"Brannigan 26 [Teodor Brannigan; September 14, 2026; {NEWS_CANONICAL}; accessed October 26, 2026; "
        f"user-supplied text] {PASTED_CITE_MARKS}"
    ), "the newest copy's fields alone: no title or publication carried over, the URL path's date"


# --------------------------------------------------------------------------------------------
# A stated year or month: printed and exported at its precision in every profile (v1-e06-t13)
# --------------------------------------------------------------------------------------------

STATED_BEFORE_THE_DATE: Final = (
    'Mara Okonkwo-Lindqvist and Teodor Brannigan; "Mammoth Money and the Elephants Left Waiting"; '
    "The Synthetic Science Weekly"
)
STATED_AFTER_THE_DATE: Final = f"{NEWS_CANONICAL}; accessed October 26, 2026; user-supplied text"
DATED_CITES: Final = {
    "2025": f"Okonkwo-Lindqvist et al. 25 [{STATED_BEFORE_THE_DATE}; 2025; {STATED_AFTER_THE_DATE}]",
    "2024-11": (
        f"Okonkwo-Lindqvist et al. 24 [{STATED_BEFORE_THE_DATE}; November 2024; {STATED_AFTER_THE_DATE}]"
    ),
    "2026-09-15": STATED_FULL_CITE,
}
"""The cite for `STATED_OPTIONS` with each `--date`, written by hand. A year prints as the year alone and a
month as its name and year, never a day; the short cite's two digits are the year at any precision. The
day is t12's cite unchanged. Every committed profile prints the same text: a profile sizes the cite and
never words it (`config/format_profiles/`)."""
DATED_PRECISIONS: Final = {"2025": "year", "2024-11": "month", "2026-09-15": None}
DATED_VALUES: Final = {
    "2025": "2025-01-01T00:00:00Z",
    "2024-11": "2024-11-01T00:00:00Z",
    "2026-09-15": "2026-09-15T00:00:00Z",
}


def stating_date(date_text: str) -> tuple[str, ...]:
    """`STATED_OPTIONS` with `date_text` as the `--date`."""
    options = list(STATED_OPTIONS)
    options[options.index("--date") + 1] = date_text
    return tuple(options)


@pytest.mark.parametrize("profile", ["team-default", "flow", "plain"])
@pytest.mark.parametrize("date_text", list(DATED_CITES), ids=["year", "month", "day"])
def test_a_stated_year_month_or_day_date_prints_at_its_precision_in_every_profiles_docx(
    seams: Seams, out: Path, tmp_path: Path, profile: str, date_text: str
) -> None:
    paste_stating(NEWS_URL, tmp_path, *stating_date(date_text))

    result = cut_pasted(NEWS_URL, out, "--format", profile)

    assert result.exit_code == ExitCode.CARD_UNVERIFIED, result.output
    assert cite_paragraph(out) == f"{DATED_CITES[date_text]} {PASTED_CITE_MARKS}"
    assert embedded_manifest(out)["cards"][0]["format_profile"] == profile


@pytest.mark.parametrize("date_text", list(DATED_CITES), ids=["year", "month", "day"])
def test_a_stated_date_is_stored_on_the_card_and_in_its_manifest_at_its_precision(
    seams: Seams, data_dir: Path, out: Path, tmp_path: Path, date_text: str
) -> None:
    paste_stating(NEWS_URL, tmp_path, *stating_date(date_text))

    assert cut_pasted(NEWS_URL, out).exit_code == ExitCode.CARD_UNVERIFIED

    [card] = stored_cards(data_dir)
    [embedded] = embedded_manifest(out)["cards"]
    for recorded in (card, embedded):
        citation = recorded["citation"]
        assert citation["published_at"]["value"] == DATED_VALUES[date_text]
        assert citation["published_at"]["raw"] == date_text
        assert citation.get("published_at_precision") == DATED_PRECISIONS[date_text]
        assert "published_at_precision" in citation or DATED_PRECISIONS[date_text] is None


def test_verify_finds_a_card_with_a_stated_year_unverified_for_its_cite_alone(
    seams: Seams, out: Path, tmp_path: Path
) -> None:
    paste_stating(NEWS_URL, tmp_path, *stating_date("2025"))
    assert cut_pasted(NEWS_URL, out).exit_code == ExitCode.CARD_UNVERIFIED

    result = runner.invoke(create_app(), ["--json", "verify", str(out)])

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    [card] = envelope(result)["error"]["details"]["cards"]
    assert (card["status"], card["reason_codes"]) == ("UNVERIFIED", ["CITATION_UNVERIFIED"])
