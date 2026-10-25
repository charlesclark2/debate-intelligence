"""`debate-research files build`, `files check` and `files suggest` through the CLI (`v1-e33-t03`).

Each of t01's three example recipes is filed as one synthetic weekly archive
(:mod:`tests.fixtures.file_builder.example_corpus`), imported with `caselist import` and parsed with
`caselist parse` through this CLI, in a `test` environment of the test's own. The parse runs in
process. The world is planted once per example and copied into each test's own data directory.

The counts each build prints are worked out by hand from the example recipes in
`tests/fixtures/file_builder/recipes/`:

| Example | Cards | Sources | Tag overrides | Analytics |
|---|---|---|---|---|
| `policy-nhi-politics-da-answers` | 5 | 5 | 2 | 2 |
| `pf-data-center-moratorium-con-blocks` | 4 | 4 | 1 | 1 |
| `ld-space-colonization-nc` | 4 | 4 | 1 | 2 |

One source per card, so sources equal cards; every synthetic card has a cite and copies without a
warning. Every school, team code and card is invented.
"""

from __future__ import annotations

import json
import os
import shutil
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import pytest
import yaml
from lxml import etree
from tests.fixtures.file_builder.example_corpus import EXAMPLES, ExampleCorpus, example_corpus
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.file_build_service import UnattributedCard
from debate_core.application.file_quality_service import FileQualityService
from debate_core.domain.file_provenance import provenance_sidecar_name
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser
from debate_core.testing.fakes.persistence import InMemorySnapshotStore
from debate_core.testing.fakes.suppression import empty_suppression_list

runner = CliRunner()

POLICY: Final = "policy-nhi-politics-da-answers"
W: Final = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
RECORDED: Final = (
    Path(__file__).resolve().parents[3]
    / "debate_core"
    / "tests"
    / "integrations"
    / "docx_file_writer"
    / "files_built_with_the_provenance_line"
)

#: (cards placed, sources used, tag overrides), by hand from each example (module docstring).
EXPECTED_COUNTS: Final = {
    POLICY: (5, 5, 2),
    "pf-data-center-moratorium-con-blocks": (4, 4, 1),
    "ld-space-colonization-nc": (4, 4, 1),
}


@dataclass(frozen=True)
class Planted:
    corpus: ExampleCorpus
    data_dir: Path


def _environment(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> None:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEBATE_ENV", "test")
    monkeypatch.setenv("DEBATE_STORAGE__DATA_DIR", str(data_dir))
    monkeypatch.setattr("debate_cli.container.ProcessPoolParseRunner", lambda **_: InProcessParseRunner())


def invoke(*arguments: str) -> Result:
    return runner.invoke(create_app(), list(arguments))


def envelope(result: Result) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    found = json.loads(lines[0])
    assert isinstance(found, dict)
    return found  # pyright: ignore[reportUnknownVariableType]


def _plant(name: str, root: Path) -> Planted:
    corpus = example_corpus(EXAMPLES / f"{name}.yaml", root / "corpus")
    data_dir = root / "data"
    with pytest.MonkeyPatch.context() as patch:
        _environment(patch, data_dir)
        imported = invoke(
            "--json",
            "caselist",
            "import",
            str(corpus.archive),
            "--caselist",
            corpus.caselist,
            "--snapshot",
            corpus.snapshot.isoformat(),
        )
        assert imported.exit_code == ExitCode.OK, imported.output
        parsed = invoke("--json", "caselist", "parse", "--caselist", corpus.caselist)
        assert parsed.exit_code == ExitCode.OK, parsed.output
    return Planted(corpus=corpus, data_dir=data_dir)


@pytest.fixture(scope="module")
def planted_examples(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Planted]:
    return {name: _plant(name, tmp_path_factory.mktemp(name)) for name in EXPECTED_COUNTS}


@pytest.fixture
def world(
    planted_examples: dict[str, Planted], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Planted]:
    """The policy example's world, copied into this test's own data directory."""
    yield _copied(planted_examples[POLICY], tmp_path, monkeypatch)


def _copied(planted: Planted, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Planted:
    data_dir = tmp_path / "data"
    shutil.copytree(planted.data_dir, data_dir)
    corpus_dir = tmp_path / "corpus"
    shutil.copytree(planted.corpus.recipe.parent, corpus_dir)
    corpus = ExampleCorpus(
        caselist=planted.corpus.caselist,
        snapshot=planted.corpus.snapshot,
        archive=corpus_dir / planted.corpus.archive.name,
        recipe=corpus_dir / planted.corpus.recipe.name,
        config_dir=corpus_dir / "config" / "landscape",
        cards=planted.corpus.cards,
        analytics=planted.corpus.analytics,
    )
    _environment(monkeypatch, data_dir)
    return Planted(corpus=corpus, data_dir=data_dir)


def built_dir(world: Planted, topic: str = "nhi") -> Path:
    return world.data_dir / "files" / "built" / topic


def header_of(docx: Path) -> str:
    with zipfile.ZipFile(BytesIO(docx.read_bytes())) as package:
        body = etree.fromstring(package.read("word/document.xml")).find(f"{W}body")
    assert body is not None
    first = body.find(f"{W}p")
    assert first is not None
    return "".join(str(part) for part in first.itertext())


def tamper(docx: bytes) -> bytes:
    """The built file with one word of a card's evidence changed, every other part as it was."""
    source, target = BytesIO(docx), BytesIO()
    with zipfile.ZipFile(source) as package, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for info in package.infolist():
            body = package.read(info.filename)
            if info.filename == "word/document.xml":
                changed = body.replace(b"Synthetic evidence 1 begins", b"Synthetic evidence 9 begins")
                assert changed != body
                body = changed
            out.writestr(info, body)
    return target.getvalue()


# ------------------------------------------------------------------------------------------------
# ac1: a build writes three files, prints its counts, and lists every RecipeError on failure
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(EXPECTED_COUNTS))
def test_files_build_writes_the_docx_sidecar_and_a_pass_report_for_each_example(
    planted_examples: dict[str, Planted], name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _copied(planted_examples[name], tmp_path, monkeypatch)
    result = invoke("--json", "files", "build", str(world.corpus.recipe))

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    topic = yaml.safe_load(world.corpus.recipe.read_text(encoding="utf-8"))["topic"]
    docx = built_dir(world, topic) / f"{name}.docx"
    assert data["files"]["docx"] == str(docx)
    assert docx.is_file() and docx.with_name(provenance_sidecar_name(docx.name)).is_file()
    assert json.loads(Path(data["files"]["quality_json"]).read_text(encoding="utf-8"))["status"] == "PASS"
    cards, sources, overrides = EXPECTED_COUNTS[name]
    assert data["counts"] == {
        "cards_placed": cards,
        "sources_used": sources,
        "tag_overrides": overrides,
        "analytics": world.corpus.analytics,
        "warnings": 0,
    }
    assert (data["status"], data["quality"]["status"], data["quality"]["failing_checks"]) == (
        "BUILT",
        "PASS",
        [],
    )


def test_files_build_prints_cards_sources_overrides_warnings_and_each_check(world: Planted) -> None:
    result = invoke("files", "build", str(world.corpus.recipe))
    assert result.exit_code == ExitCode.OK, result.output
    shown = " ".join(result.stdout.split())
    assert "5 card(s) placed from 5 source(s), 2 tag override(s), 0 warning(s)" in shown
    for check in ("sidecar", "evidence-identity", "provenance-complete", "suppression"):
        assert check in shown
    assert "PASS" in shown


def test_files_build_lists_every_recipe_error_and_exits_1(world: Planted) -> None:
    recipe = world.corpus.recipe
    text = recipe.read_text(encoding="utf-8")
    for card in world.corpus.cards[:2]:
        text = text.replace(card.fingerprint, "e5" * 32 if card.number == 1 else "f6" * 32)
    recipe.write_text(text, encoding="utf-8")
    result = invoke("--json", "files", "build", str(recipe))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert error["code"] == "RECIPE_UNRESOLVED"
    assert [one["code"] for one in error["details"]["recipe_errors"]] == ["UNKNOWN_CARD", "UNKNOWN_CARD"]
    assert not built_dir(world).exists()

    shown = invoke("files", "build", str(recipe))
    panel = " ".join(shown.stderr.split())
    assert shown.exit_code == ExitCode.DOMAIN_FAILURE
    assert panel.count("[UNKNOWN_CARD]") == 2


# ------------------------------------------------------------------------------------------------
# ac2: a draft is refused unless --allow-draft, and then its header says DRAFT
# ------------------------------------------------------------------------------------------------


def test_files_build_refuses_a_draft_without_allow_draft_and_builds_it_with(world: Planted) -> None:
    recipe = world.corpus.recipe
    recipe.write_text(recipe.read_text(encoding="utf-8") + "status: draft\n", encoding="utf-8")

    refused = invoke("--json", "files", "build", str(recipe))
    assert refused.exit_code == ExitCode.USAGE_ERROR, refused.output
    assert envelope(refused)["error"]["code"] == "DRAFT_NOT_ALLOWED"
    assert "--allow-draft" in envelope(refused)["error"]["hint"]
    assert not built_dir(world).exists()

    built = invoke("--json", "files", "build", str(recipe), "--allow-draft")
    assert built.exit_code == ExitCode.OK, built.output
    assert header_of(Path(envelope(built)["data"]["files"]["docx"])).startswith("DRAFT: ")


# ------------------------------------------------------------------------------------------------
# ac4: a missing source blob fails its card with SOURCE_MISSING and `store get`, building nothing
# ------------------------------------------------------------------------------------------------


def test_files_build_with_a_missing_source_names_store_get_and_builds_nothing(world: Planted) -> None:
    missing = world.corpus.cards[2]
    sha = missing.source_sha256
    (world.data_dir / "blobs" / "sha256" / sha[:2] / sha[2:4] / sha).unlink()
    result = invoke("--json", "files", "build", str(world.corpus.recipe))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert error["code"] == "SOURCE_MISSING"
    (problem,) = error["details"]["card_problems"]
    assert (problem["code"], problem["fingerprint"]) == ("SOURCE_MISSING", missing.fingerprint)
    key = f"raw/caselist/{world.corpus.caselist}/sha256/{sha[:2]}/{sha[2:4]}/{sha}"
    assert problem["hint"] == f"debate-research store get {key}"
    assert not built_dir(world).exists()


# ------------------------------------------------------------------------------------------------
# ac5 and ac10: a FAIL names its checks; `files check` reports a tampered file without rebuilding
# ------------------------------------------------------------------------------------------------


def test_files_build_runs_the_wired_quality_check_and_exits_1_naming_the_failing_checks(
    world: Planted, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The container's `file_quality` is replaced by one whose blob store is empty: the build runs it."""
    blind = FileQualityService(
        parser=DebateDocxParser(), snapshots=InMemorySnapshotStore(), suppression=empty_suppression_list()
    )
    monkeypatch.setattr(ServiceContainer, "file_quality", lambda _self: blind)  # pyright: ignore[reportUnknownLambdaType]
    result = invoke("--json", "files", "build", str(world.corpus.recipe))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert error["code"] == "QUALITY_FAILED"
    assert "evidence-identity" in error["message"]
    assert error["details"]["quality"]["failing_checks"] == ["evidence-identity"]
    assert Path(error["details"]["files"]["docx"]).is_file()


def test_files_check_reports_a_tampered_built_file_as_fail_without_rebuilding(world: Planted) -> None:
    built = invoke("--json", "files", "build", str(world.corpus.recipe))
    assert built.exit_code == ExitCode.OK, built.output
    docx = Path(envelope(built)["data"]["files"]["docx"])
    sidecar = docx.with_name(provenance_sidecar_name(docx.name))
    tampered = tamper(docx.read_bytes())
    docx.write_bytes(tampered)
    sidecar_before = sidecar.read_bytes()

    result = invoke("--json", "files", "check", str(docx))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert error["code"] == "QUALITY_FAILED"
    failing = error["details"]["quality"]["failing_checks"]
    assert "sidecar" in failing and "evidence-identity" in failing
    assert docx.read_bytes() == tampered and sidecar.read_bytes() == sidecar_before
    assert (
        json.loads(docx.with_name(f"{docx.name}.quality.json").read_text(encoding="utf-8"))["status"]
        == "FAIL"
    )


def test_files_check_passes_an_untouched_built_file(world: Planted) -> None:
    built = invoke("--json", "files", "build", str(world.corpus.recipe))
    docx = envelope(built)["data"]["files"]["docx"]
    result = invoke("--json", "files", "check", docx)
    assert result.exit_code == ExitCode.OK, result.output
    assert envelope(result)["data"]["quality"]["status"] == "PASS"


def test_files_check_says_why_a_file_built_by_file_writer_2_fails_provenance_complete(
    world: Planted, tmp_path: Path
) -> None:
    name = "no-disclosure-on-record.docx"
    old = tmp_path / "old"
    old.mkdir()
    shutil.copy(RECORDED / name, old / name)
    shutil.copy(RECORDED / provenance_sidecar_name(name), old / provenance_sidecar_name(name))
    result = invoke("--json", "files", "check", str(old / name))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert "provenance-complete" in error["details"]["quality"]["failing_checks"]
    (note,) = error["details"]["notes"]
    assert "2026.10.19-file-writer-2" in note and "debate-research files build" in note
    assert error["hint"] == note


# ------------------------------------------------------------------------------------------------
# ac7, ac8, ac10: unattributed cards named first; another parser's store refused; no git tree
# ------------------------------------------------------------------------------------------------


def test_files_build_notes_each_unattributed_card_before_its_result(
    world: Planted, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The service tells the command of unattributed cards before the writer runs; the command notes each."""
    original = ServiceContainer.file_build

    def heard_first(self: Any) -> Any:
        service = original(self)
        build = service.build

        async def announcing(request: Any, *, on_unattributed: Any = None) -> Any:
            on_unattributed(
                [UnattributedCard("structure[0].hats[0].blocks[0].items[1]", "ab" * 32, "hspolicy26")]
            )
            return await build(request, on_unattributed=on_unattributed)

        service.build = announcing
        return service

    monkeypatch.setattr(ServiceContainer, "file_build", heard_first)
    result = invoke("files", "build", str(world.corpus.recipe))
    assert result.exit_code == ExitCode.OK, result.output
    notes = " ".join(result.stderr.split())
    assert "1 card(s) resolved to an occurrence with nothing on record" in notes
    assert f"structure[0].hats[0].blocks[0].items[1]: {'ab' * 6} (hspolicy26)" in notes


def test_files_build_refuses_a_store_another_parser_made_naming_both_versions(world: Planted) -> None:
    parsed = world.data_dir / "parsed" / world.corpus.caselist
    (parsed / DOCX_PARSER_VERSION).rename(parsed / "2026.10.18-docx-4")
    result = invoke("--json", "files", "build", str(world.corpus.recipe))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert error["code"] == "STORE_PARSED_BY_ANOTHER_VERSION"
    assert "2026.10.18-docx-4" in error["message"] and DOCX_PARSER_VERSION in error["message"]
    assert f"debate-research caselist parse --caselist {world.corpus.caselist}" in error["hint"]
    assert error["details"]["recipe_errors"] == []


def test_files_build_refuses_an_out_inside_a_git_working_tree(world: Planted, tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    result = invoke("--json", "files", "build", str(world.corpus.recipe), "--out", str(checkout / "built"))
    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert envelope(result)["error"]["code"] == "OUTPUT_IN_A_GIT_WORKING_TREE"
    assert not (checkout / "built").exists()


# ------------------------------------------------------------------------------------------------
# ac3: files suggest writes a draft that validates, pins every card, and builds with --allow-draft
# ------------------------------------------------------------------------------------------------


def test_files_suggest_writes_a_draft_that_files_build_builds_with_allow_draft(world: Planted) -> None:
    result = invoke(
        "--json",
        "files",
        "suggest",
        "--caselist",
        world.corpus.caselist,
        "--position",
        "politics-da",
        "--top",
        "10",
        "--config-dir",
        str(world.corpus.config_dir),
    )
    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    draft = Path(data["path"])
    assert draft == world.data_dir / "files" / "recipes" / "nhi" / "politics-da-aff-draft.yaml"
    document = yaml.safe_load(draft.read_text(encoding="utf-8"))
    assert document["status"] == "draft"
    suggested = {
        item["fingerprint"] for block in document["structure"][0]["blocks"] for item in block["items"]
    }
    assert suggested == {card.fingerprint for card in world.corpus.cards}
    assert [card["rank"] for card in data["cards"]] == sorted(card["rank"] for card in data["cards"])

    refused = invoke("--json", "files", "build", str(draft))
    assert refused.exit_code == ExitCode.USAGE_ERROR
    built = invoke("--json", "files", "build", str(draft), "--allow-draft")
    assert built.exit_code == ExitCode.OK, built.output
    assert envelope(built)["data"]["counts"]["cards_placed"] == len(world.corpus.cards)


def test_files_suggest_refuses_an_unknown_position_with_exit_2_naming_the_known_ones(world: Planted) -> None:
    result = invoke(
        "--json",
        "files",
        "suggest",
        "--caselist",
        world.corpus.caselist,
        "--position",
        "spending-da",
        "--config-dir",
        str(world.corpus.config_dir),
    )
    assert result.exit_code == ExitCode.USAGE_ERROR, result.output
    assert envelope(result)["error"]["details"]["known"] == ["politics-da"]


def test_files_help_names_its_three_commands_and_build_documents_its_exit_codes() -> None:
    group = invoke("files", "--help")
    assert group.exit_code == ExitCode.OK
    for command in ("build", "check", "suggest"):
        assert command in group.stdout
    help_text = " ".join(invoke("files", "build", "--help").stdout.split())
    for code in ("Exit 0:", "Exit 1:", "Exit 2:"):
        assert code in help_text
