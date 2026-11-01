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
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.card.card_world import MODEL_OUTPUTS, NEWS_ARGUMENT, NEWS_NEED, page_bytes, paragraphs_of
from tests.fixtures.citation.citation_world import load_case
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
