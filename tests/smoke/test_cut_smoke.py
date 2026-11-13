"""`debate-research cut` on the build under test, offline (v1-e06-t06, ac5).

The recorded tier cannot fetch (the network guard refuses every host) and calls no model, so the
check gives the build what a fetch and a recorded run would have left in its data directory:

* the news article of v1-e04-t04 stored as ArticleService stores a retrieval: its article, and a
  PUBLISHER_RETRIEVED snapshot of the committed page with t04's hand-written paragraphs, taken now, so
  it is within the re-fetch age and `cut` answers from it without asking the publisher;
* the committed `card.select` and `card.markup` answers for that article, written as replay cassettes
  in `<data dir>/cards/model-cassettes/`, where the build's router replays from in its default mode.

Then the build cuts the card. Its prompt registry comes from the build itself: an installed build's
bundled `prompts/` (`scripts/stamp_build.py`), and the checkout's console script the checkout's own. A
replayed call is matched on its prompt id, version and every variable, the numbered snapshot among
them, so a build whose prompts or numbering differ finds no cassette and exits 1. The guard's log
staying empty is the proof that nothing was fetched.
"""

from __future__ import annotations

import asyncio
import gc
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import docx
import pytest
from tests.fixtures.card.card_world import MODEL_OUTPUTS, NEWS_ARGUMENT, NEWS_NEED, page_bytes, paragraphs_of
from tests.fixtures.citation.citation_world import load_case
from tests.fixtures.verify.docx_world import edited, replace_in_evidence
from tests.smoke.installed_build import InstalledCli

from debate_cli.container import CARD_CASSETTES_DIRECTORY
from debate_cli.exit_codes import ExitCode
from debate_core.application.snapshot_service import SnapshotService
from debate_core.domain import AccessStatus, Article, ArticleIdentifiers, ProvenanceMode
from debate_core.domain.model_contracts import ModelPrompt, ModelRequest, TaskClass
from debate_core.evidence.docx_manifest_part import read_embedded_manifest_bytes
from debate_core.integrations.local import FsSnapshotStore, SqliteArticleRepository, SqliteDatabase
from debate_core.integrations.models.record_replay import CassetteDirectory
from debate_core.testing.fakes.clock_and_ids import SequentialIdGenerator

NEWS_URL: Final = (
    "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away?utm_source=newsletter"
)
EVIDENCE: Final = (
    "The delay follows two years of failed attempts to grow edited elephant embryos to term in surrogate "
    "animals.Conservation biologists who have criticized the project said the timeline was never "
    "realistic. “Every year this slips, the money raised for it is money that did not go to elephants "
    "that are alive now,” said Priya Ramaswamy, who studies elephant populations and was not involved "
    "in the work."
)
"""P2's first sentence and all of P3, joined with nothing: v1-e06-t02's hand-written `EVIDENCE`."""
RECORDED_MODEL: Final = "recorded-model"


class _Now:
    def now(self) -> datetime:
        return datetime.now(UTC)


async def _store_news(data_dir: Path) -> None:
    database = SqliteDatabase.open(data_dir)
    try:
        articles = SqliteArticleRepository(database)
        snapshots = SnapshotService(
            blobs=FsSnapshotStore(data_dir), clock=_Now(), id_generator=SequentialIdGenerator("SMKE")
        )
        stated = load_case("news-article")
        article = await articles.save(
            Article(
                canonical_url=stated["article"]["canonical_url"],
                title=stated["article"]["title"],
                access_status=AccessStatus.ACCESSIBLE,
                identifiers=ArticleIdentifiers(doi=None),
            )
        )
        snapshot = await snapshots.create(
            article_id=article.article_id,
            raw_bytes=page_bytes("news-article"),
            extracted_text="\n\n".join(paragraphs_of("news-article")),
            canonical_url=stated["retrieved_url"],
            retrieved_at=datetime.now(UTC),
            extractor_version="fixture-extractor/1",
            provenance_mode=ProvenanceMode.PUBLISHER_RETRIEVED,
            access_status=AccessStatus.ACCESSIBLE,
            content_type=stated["content_type"],
        )
        await articles.save_snapshot(snapshot)
    finally:
        database.close()
        gc.collect()


def _plant_cassettes(data_dir: Path) -> list[Path]:
    """The committed news-article answers, as the replay cassettes of the calls `cut` makes for them."""
    directory = CassetteDirectory(data_dir / CARD_CASSETTES_DIRECTORY)
    planted: list[Path] = []
    for prompt_id in ("card.select", "card.markup"):
        for path in sorted((MODEL_OUTPUTS / prompt_id).glob("*.json")):
            fixture: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            if fixture["variables"]["research_need"] != f"{NEWS_ARGUMENT}: {NEWS_NEED}":
                continue
            request = ModelRequest(
                task_class=TaskClass.COMPLEX_REASONING,
                prompt=ModelPrompt(
                    prompt_id=fixture["prompt_id"],
                    prompt_version=fixture["prompt_version"],
                    variables=fixture["variables"],
                ),
                output_schema=fixture["output_schema"],
            )
            planted.append(directory.write_structured(request, _recorded_response(fixture)))
    return planted


def _recorded_response(fixture: dict[str, Any]) -> dict[str, Any]:
    """A response as record mode writes one, around the committed answer; every other value invented."""
    return {
        "invoked_at": "2026-10-26T15:00:00Z",
        "output": fixture["output"],
        "prompt_id": fixture["prompt_id"],
        "prompt_version": fixture["prompt_version"],
        "provider_request_id": "smoke-request",
        "route": {
            "inference_profile": None,
            "max_tokens": 4096,
            "model_id": RECORDED_MODEL,
            "provider": "bedrock",
            "region": "example-region-1",
            "task_class": TaskClass.COMPLEX_REASONING.value,
            "temperature": None,
            "timeout_seconds": 60.0,
        },
        "usage": {"input_tokens": 700, "latency_ms": 2000.0, "output_tokens": 200},
    }


@pytest.fixture
def stored_news(installed_cli: InstalledCli) -> Path:
    """The news article's snapshot and its two recorded answers, in the build's scratch data directory."""
    asyncio.run(_store_news(installed_cli.data_dir))
    assert len(_plant_cassettes(installed_cli.data_dir)) == 2, "one cassette for each of the two calls"
    return installed_cli.data_dir


def test_cut_is_installed_with_its_options_and_exit_codes(installed_cli: InstalledCli) -> None:
    run = installed_cli.run("cut", "--help")

    assert run.exit_code == 0, run.output
    for line in (
        "0  the card is VERIFIED",
        "1  could not run",
        "3  PAYWALLED",
        "4  the card is UNVERIFIED",
        "--need",
        "--format",
    ):
        assert line in run.stdout


def test_an_installed_build_carries_the_prompts_and_format_profiles_it_cuts_with(
    installed_cli: InstalledCli,
) -> None:
    probe = (
        "import json\n"
        "from debate_cli.build_info import bundled_config_root\n"
        "root = bundled_config_root()\n"
        "names = ['prompts/card/select.md', 'prompts/card/markup.md', "
        "'config/format_profiles/team-default.yaml']\n"
        "print(json.dumps(None if root is None else {name: (root / name).is_file() for name in names}))\n"
    )

    run = installed_cli.run_program([str(installed_cli.build.interpreter), "-c", probe])

    assert run.exit_code == 0, run.output
    bundled = json.loads(run.stdout)
    if installed_cli.build.installed:
        assert bundled == {
            "prompts/card/select.md": True,
            "prompts/card/markup.md": True,
            "config/format_profiles/team-default.yaml": True,
        }
    else:
        assert bundled is None, "the checkout's console script is not stamped: it reads the checkout's copy"


def test_cut_writes_a_verified_docx_from_a_stored_snapshot_and_replayed_answers_offline(
    installed_cli: InstalledCli, stored_news: Path
) -> None:
    out = installed_cli.workdir / "evidence.docx"

    run = installed_cli.run(
        "--json", "cut", NEWS_URL, "--need", NEWS_NEED, "--argument", NEWS_ARGUMENT, "--output", str(out)
    )

    assert run.exit_code == ExitCode.OK, run.output
    data = run.envelope()["data"]
    assert isinstance(data, dict)
    assert (data["status"], data["reasons"], data["format_profile"]) == (
        "VERIFIED",
        [],
        "team-default",
    )
    assert data["source"]["fetched"] is False, "the stored snapshot answered; nothing was fetched"
    assert [(call["prompt_id"], call["route"]["model_id"]) for call in data["model_calls"]] == [
        ("card.select", RECORDED_MODEL),
        ("card.markup", RECORDED_MODEL),
    ]
    [card] = json.loads(read_embedded_manifest_bytes(out))["cards"]
    assert (card["card_id"], card["verification_status"], card["evidence_text"]) == (
        data["card_id"],
        "VERIFIED",
        EVIDENCE,
    )
    events = [json.loads(line)["event"] for line in run.stderr.splitlines() if line.startswith("{")]
    assert events == ["fetch", "extract", "select", "verify", "export"]


def test_verify_reads_the_docx_cut_wrote_and_finds_its_card_verified_offline(
    installed_cli: InstalledCli, stored_news: Path
) -> None:
    """`verify evidence.docx` on the build under test (v1-e06-t07): the manifest `cut` embedded is read,
    its card checked against the snapshot in the data directory and its body against the card. The
    build reads the body in its own bundled format profile, so a build missing it fails here."""
    out = installed_cli.workdir / "evidence.docx"
    cut = installed_cli.run(
        "cut", NEWS_URL, "--need", NEWS_NEED, "--argument", NEWS_ARGUMENT, "--output", str(out)
    )
    assert cut.exit_code == ExitCode.OK, cut.output
    written = out.read_bytes()

    run = installed_cli.run("--json", "verify", str(out))

    assert run.exit_code == ExitCode.OK, run.output
    data = run.envelope()["data"]
    assert isinstance(data, dict)
    [card] = data["cards"]
    [embedded] = json.loads(read_embedded_manifest_bytes(out))["cards"]
    assert (card["card_id"], card["status"], card["reason_codes"], card["snapshot_id"]) == (
        embedded["card_id"],
        "VERIFIED",
        [],
        embedded["snapshot_id"],
    )
    assert data["document"] == {
        "format_profile": "team-default",
        "body_cards": 1,
        "unclaimed_body_cards": [],
        "unclaimed_body_card_verdicts": [],
    }
    assert out.read_bytes() == written, "verify only reads the document"


def test_verify_warns_negation_removed_on_a_docx_whose_body_deletes_never_and_exits_0_offline(
    installed_cli: InstalledCli, stored_news: Path
) -> None:
    """`verify` on the build under test, after a student deleted "never " from the body (v1-e06-t10,
    v1-e06-t15). The edit is made as Word would, through python-docx. "never " is evidence [186, 192):
    the critics' sentence starts at 108 and "never" is its 78th character. In the snapshot, t04's
    paragraphs joined with a blank line, the third paragraph starts at 210 + 2 + 208 + 2 = 422, so the
    deletion is snapshot [500, 506). The card stays VERIFIED and the warning is all the report says."""
    out = installed_cli.workdir / "evidence.docx"
    cut = installed_cli.run(
        "cut", NEWS_URL, "--need", NEWS_NEED, "--argument", NEWS_ARGUMENT, "--output", str(out)
    )
    assert cut.exit_code == ExitCode.OK, cut.output
    out.write_bytes(edited(out.read_bytes(), replace_in_evidence("was never realistic", "was realistic")))

    run = installed_cli.run("--json", "verify", str(out))

    assert run.exit_code == ExitCode.OK, run.output
    data = run.envelope()["data"]
    assert isinstance(data, dict)
    [card] = data["cards"]
    assert (card["status"], card["reason_codes"]) == ("VERIFIED", [])
    assert [
        (warning["code"], warning["evidence_range"], warning["snapshot_range"])
        for warning in card.get("warnings", [])
    ] == [("NEGATION_REMOVED", {"start": 186, "end": 192}, {"start": 500, "end": 506})]
    assert "never" not in run.stdout, "the report holds offsets, never the evidence's words"


# --------------------------------------------------------------------------------------------
# --from-paste: the coach's own stored copy (v1-e06-t08)
# --------------------------------------------------------------------------------------------

PASTED_CITE_FIELDS: Final = ["authors", "title", "publication", "published_at", "canonical_url"]
"""Every required cite field: the citation rules verify none of text a user supplied (v1-e06-t01)."""


def _paste_news(installed_cli: InstalledCli) -> dict[str, Any]:
    """t04's paragraphs of the news article stored with the build's own `fetch --paste`; the snapshot."""
    pasted = installed_cli.workdir / "library-copy.txt"
    pasted.write_text("\n\n".join(paragraphs_of("news-article")), encoding="utf-8")
    run = installed_cli.run(
        "--json", "fetch", "--paste", str(pasted), "--source-url", NEWS_URL, "--i-have-lawful-access"
    )
    assert run.exit_code == ExitCode.OK, run.output
    data = run.envelope()["data"]
    assert isinstance(data, dict)
    snapshot: dict[str, Any] = data["snapshot"]
    return snapshot


def test_cut_from_paste_cuts_the_stored_copy_as_user_supplied_and_verify_reads_it_offline(
    installed_cli: InstalledCli,
) -> None:
    """Paste, cut and verify on the build under test, nothing fetched (the guard's log stays empty).

    The pasted copy is the news article's text, so the replayed answers are the ones `cut` asks for.
    The evidence verifies against the copy; the cite of user-supplied text never does, so the card is
    UNVERIFIED for that alone (exit 4), and `verify` finds the same (exit 1)."""
    snapshot = _paste_news(installed_cli)
    assert len(_plant_cassettes(installed_cli.data_dir)) == 2
    out = installed_cli.workdir / "evidence.docx"

    cut = installed_cli.run(
        "--json",
        "cut",
        NEWS_URL,
        "--from-paste",
        "--need",
        NEWS_NEED,
        "--argument",
        NEWS_ARGUMENT,
        "--output",
        str(out),
    )

    assert cut.exit_code == ExitCode.CARD_UNVERIFIED, cut.output
    error = cut.envelope()["error"]
    assert isinstance(error, dict)
    details = error["details"]
    assert (details["source"]["provenance_mode"], details["source"]["fetched"]) == ("USER_SUPPLIED", False)
    assert [(r["reason"], r["fields"]) for r in details["reasons"]] == [
        ("CITATION_UNVERIFIED", PASTED_CITE_FIELDS)
    ]
    manifest = json.loads(read_embedded_manifest_bytes(out))
    [card] = manifest["cards"]
    assert (card["provenance_mode"], card["snapshot_id"], card["evidence_text"]) == (
        "USER_SUPPLIED",
        snapshot["snapshot_id"],
        EVIDENCE,
    )
    assert [(s["snapshot_id"], s["extractor_version"]) for s in manifest["snapshots"]] == [
        (snapshot["snapshot_id"], "user-supplied-text-1")
    ]

    verify = installed_cli.run("--json", "verify", str(out))

    assert verify.exit_code == ExitCode.DOMAIN_FAILURE, verify.output
    verified = verify.envelope()["error"]
    assert isinstance(verified, dict)
    [verdict] = verified["details"]["cards"]
    assert (verdict["card_id"], verdict["status"], verdict["reason_codes"]) == (
        card["card_id"],
        "UNVERIFIED",
        ["CITATION_UNVERIFIED"],
    )


def test_cut_from_paste_with_no_stored_copy_exits_1_naming_fetch_paste_offline(
    installed_cli: InstalledCli,
) -> None:
    out = installed_cli.workdir / "evidence.docx"

    run = installed_cli.run(
        "--json", "cut", NEWS_URL, "--from-paste", "--need", NEWS_NEED, "--output", str(out)
    )

    assert run.exit_code == ExitCode.DOMAIN_FAILURE, run.output
    error = run.envelope()["error"]
    assert isinstance(error, dict)
    assert error["code"] == "NO_USER_SUPPLIED_COPY"
    assert isinstance(error["hint"], str) and "fetch --paste FILE --source-url" in error["hint"]
    assert not out.exists()


# --------------------------------------------------------------------------------------------
# --from-paste with cite fields stated at `fetch --paste` (v1-e06-t12)
# --------------------------------------------------------------------------------------------


def test_cut_from_paste_cites_the_fields_stated_at_fetch_paste_unverified_offline(
    installed_cli: InstalledCli,
) -> None:
    """The build's own `fetch --paste` stores invented cite fields; its `cut --from-paste` cites them,
    none verified, and the card is UNVERIFIED for its cite alone; `verify` finds the same."""
    pasted = installed_cli.workdir / "library-copy.txt"
    pasted.write_text("\n\n".join(paragraphs_of("news-article")), encoding="utf-8")
    stored = installed_cli.run(
        "--json",
        "fetch",
        "--paste",
        str(pasted),
        "--source-url",
        NEWS_URL,
        "--i-have-lawful-access",
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
    assert stored.exit_code == ExitCode.OK, stored.output
    data = stored.envelope()["data"]
    assert isinstance(data, dict)
    assert data["snapshot"]["stated_cite"] == {
        "authors": ["Mara Okonkwo-Lindqvist", "Teodor Brannigan"],
        "title": "Mammoth Money and the Elephants Left Waiting",
        "publication": "The Synthetic Science Weekly",
        "published_at": "2026-09-15",
    }
    assert len(_plant_cassettes(installed_cli.data_dir)) == 2
    out = installed_cli.workdir / "evidence.docx"

    cut = installed_cli.run(
        "--json",
        "cut",
        NEWS_URL,
        "--from-paste",
        "--need",
        NEWS_NEED,
        "--argument",
        NEWS_ARGUMENT,
        "--output",
        str(out),
    )

    assert cut.exit_code == ExitCode.CARD_UNVERIFIED, cut.output
    error = cut.envelope()["error"]
    assert isinstance(error, dict)
    assert [(r["reason"], r["fields"]) for r in error["details"]["reasons"]] == [
        ("CITATION_UNVERIFIED", PASTED_CITE_FIELDS)
    ]
    [card] = json.loads(read_embedded_manifest_bytes(out))["cards"]
    citation = card["citation"]
    assert (card["provenance_mode"], card["snapshot_id"]) == (
        "USER_SUPPLIED",
        data["snapshot"]["snapshot_id"],
    )
    assert citation["authors"]["value"] == ["Mara Okonkwo-Lindqvist", "Teodor Brannigan"]
    assert (
        citation["title"]["value"],
        citation["publication"]["value"],
        citation["published_at"]["value"],
    ) == (
        "Mammoth Money and the Elephants Left Waiting",
        "The Synthetic Science Weekly",
        "2026-09-15T00:00:00Z",
    )
    assert [
        name for name, value in citation.items() if isinstance(value, dict) and value.get("verified")
    ] == []

    verify = installed_cli.run("--json", "verify", str(out))

    assert verify.exit_code == ExitCode.DOMAIN_FAILURE, verify.output
    verified = verify.envelope()["error"]
    assert isinstance(verified, dict)
    [verdict] = verified["details"]["cards"]
    assert (verdict["status"], verdict["reason_codes"]) == ("UNVERIFIED", ["CITATION_UNVERIFIED"])


# --------------------------------------------------------------------------------------------
# A stated year: stored, cited and exported as a year, never a day (v1-e06-t13)
# --------------------------------------------------------------------------------------------


def test_cut_from_paste_cites_a_stated_year_as_a_year_offline(installed_cli: InstalledCli) -> None:
    """The build's own `fetch --paste --date 2025` stores a year; its `cut --from-paste` prints "2025" in
    the .docx cite where the URL's path names a day, and the card's manifest keeps the year's precision."""
    pasted = installed_cli.workdir / "library-copy.txt"
    pasted.write_text("\n\n".join(paragraphs_of("news-article")), encoding="utf-8")
    stored = installed_cli.run(
        "--json",
        "fetch",
        "--paste",
        str(pasted),
        "--source-url",
        NEWS_URL,
        "--i-have-lawful-access",
        "--date",
        "2025",
    )
    assert stored.exit_code == ExitCode.OK, stored.output
    data = stored.envelope()["data"]
    assert isinstance(data, dict)
    assert data["snapshot"]["stated_cite"] == {
        "authors": [],
        "title": None,
        "publication": None,
        "published_at": "2025",
        "date_precision": "year",
    }
    assert len(_plant_cassettes(installed_cli.data_dir)) == 2
    out = installed_cli.workdir / "evidence.docx"

    cut = installed_cli.run(
        "--json",
        "cut",
        NEWS_URL,
        "--from-paste",
        "--need",
        NEWS_NEED,
        "--argument",
        NEWS_ARGUMENT,
        "--output",
        str(out),
    )

    assert cut.exit_code == ExitCode.CARD_UNVERIFIED, cut.output
    [card] = json.loads(read_embedded_manifest_bytes(out))["cards"]
    published = card["citation"]["published_at"]
    assert (published["value"], published["raw"], published["source"], published["verified"]) == (
        "2025-01-01T00:00:00Z",
        "2025",
        "heuristic",
        False,
    )
    assert card["citation"]["published_at_precision"] == "year"
    cite = docx.Document(io.BytesIO(out.read_bytes())).paragraphs[2].text
    assert cite.startswith(
        "[no author] 25 [2025; "
        "https://www.dailymeridian.example/science/2026/09/14/mammoth-revival-years-away; accessed "
    ), cite
    assert "September 14" not in cite
