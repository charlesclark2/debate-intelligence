"""`debate-research files build`, `check`, `suggest` (`v1-e33-t03`) and `publish` (`v1-e33-t05`), by CLI.

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
import re
import shutil
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import boto3
import pytest
import yaml
from lxml import etree
from moto import mock_aws
from tests.fixtures.file_builder.example_corpus import EXAMPLES, ExampleCorpus, example_corpus
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from typer.testing import CliRunner, Result

from debate_cli.app import create_app
from debate_cli.container import ServiceContainer
from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.parse_workers import InProcessParseRunner
from debate_core.application.file_build_service import UnattributedCard
from debate_core.application.file_quality_service import FileQualityService
from debate_core.application.file_suggest_service import CP_TEXT_SLOT
from debate_core.application.ports.suppression import ReasonCode, SuppressionAction, SuppressionEntry
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


def test_files_build_refuses_a_store_another_style_profile_made_naming_both_profiles(world: Planted) -> None:
    """Every row of the occurrence table restamped with another profile, as its parse would have written."""
    table = world.data_dir / "parsed" / world.corpus.caselist / DOCX_PARSER_VERSION / "occurrences.jsonl"
    rows = [json.loads(line) for line in table.read_text(encoding="utf-8").splitlines()]
    assert rows
    table.write_text(
        "".join(json.dumps({**row, "profile_version": "2026.11.02-verbatim-2"}) + "\n" for row in rows),
        encoding="utf-8",
    )
    result = invoke("--json", "files", "build", str(world.corpus.recipe))

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    error = envelope(result)["error"]
    assert error["code"] == "STORE_PARSED_BY_ANOTHER_VERSION"
    assert "2026.11.02-verbatim-2" in error["message"]
    assert DebateDocxParser().profile_version in error["message"]
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


# ------------------------------------------------------------------------------------------------
# The removal runbook's step 8: `files check` over the built files finds a removed card
# ------------------------------------------------------------------------------------------------

RUNBOOK: Final = Path(__file__).resolve().parents[4] / "docs" / "runbooks" / "caselist-removal.md"


def test_the_removal_runbooks_step_8_runs_files_check_over_each_environments_built_files() -> None:
    step = RUNBOOK.read_text(encoding="utf-8").split("## Step 8 — Suppression and built files", 1)[1]
    step = step.split("\n## ", 1)[0]
    blocks = [block.strip() for block in step.split("```bash")[1:]]
    commands = [block.split("```", 1)[0].strip() for block in blocks]
    assert commands == [
        f"find ~/.debate-research/{env}/files/built -name '*.docx' -print0 | DEBATE_ENV={env} xargs -0 -n 1 "
        "uv run debate-research files check"
        for env in ("dev", "prod")
    ]


def test_files_check_fails_the_suppression_check_of_a_built_file_once_its_source_is_removed(
    world: Planted,
) -> None:
    built = invoke("--json", "files", "build", str(world.corpus.recipe))
    assert built.exit_code == ExitCode.OK, built.output
    docx = envelope(built)["data"]["files"]["docx"]
    removed = world.corpus.cards[0].source_sha256
    entry = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=removed,
        recorded_at=datetime(2026, 10, 24, 9, 0, tzinfo=UTC),
        reason=ReasonCode.REQUESTED_BY_TEAM,
        request_id="RM-2026-90",
    )
    listed = world.data_dir / "suppression" / "suppression-list.jsonl"
    listed.parent.mkdir(parents=True, exist_ok=True)
    with listed.open("a", encoding="utf-8") as stream:
        stream.write(entry.to_line() + "\n")

    result = invoke("--json", "files", "check", docx)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    assert envelope(result)["error"]["details"]["quality"]["failing_checks"] == ["suppression"]
    report = json.loads(Path(f"{docx}.quality.json").read_text(encoding="utf-8"))
    (finding,) = [
        one for one in report["results"] if one["check"] == "suppression" and one["status"] == "FAIL"
    ]
    assert "RM-2026-90" in finding["message"]


# ------------------------------------------------------------------------------------------------
# files publish (v1-e33-t05): the gate's refusals, the environment and bucket shown, a dry run with
# no S3, and a publish to moto's dev bucket that a second run skips
# ------------------------------------------------------------------------------------------------

DEV_BUCKET: Final = "debate-dev-evidence-moto"
PROD_BUCKET: Final = "debate-prod-evidence-moto"


def as_dev(world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, environment: str = "dev") -> None:
    """The planted world's data directory under a dev and a prod profile of this test's own, local mode.

    The built-in profiles name the evidence AWS profiles, so an AWS config of the test's own defines
    them, with credentials that are the string `testing` and cannot reach an account.
    """
    profiles = tmp_path / "profiles"
    profiles.mkdir(exist_ok=True)
    for name, bucket in (("dev", DEV_BUCKET), ("prod", PROD_BUCKET)):
        (profiles / f"{name}.toml").write_text(
            f'[storage]\ndata_dir = "{world.data_dir}"\n'
            f'[storage.s3]\nbucket = "{bucket}"\nregion = "us-east-1"\n'
            '[caselist]\nrun_state = "local"\n'
            f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n',
            encoding="utf-8",
        )
    evidence_profiles = ("debate-dev-evidence", "debate-prod-evidence")
    config, credentials = tmp_path / "aws-config", tmp_path / "aws-credentials"
    config.write_text("".join(f"[profile {one}]\nregion = us-east-1\n" for one in evidence_profiles))
    credentials.write_text(
        "".join(
            f"[{one}]\naws_access_key_id = testing\naws_secret_access_key = testing\n"
            for one in evidence_profiles
        )
    )
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": str(config),
        "AWS_SHARED_CREDENTIALS_FILE": str(credentials),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(profiles))
    monkeypatch.setenv("DEBATE_ENV", environment)
    monkeypatch.delenv("DEBATE_STORAGE__DATA_DIR", raising=False)


@pytest.fixture
def dev_bucket() -> Iterator[Any]:
    """moto's dev and prod buckets, versioned like the real ones, for the whole of one test."""
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")  # pyright: ignore[reportUnknownMemberType]
        for bucket in (DEV_BUCKET, PROD_BUCKET):
            client.create_bucket(Bucket=bucket)
            client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
        yield client


def built_policy_file(world: Planted) -> Path:
    built = invoke("--json", "files", "build", str(world.corpus.recipe))
    assert built.exit_code == ExitCode.OK, built.output
    return Path(envelope(built)["data"]["files"]["docx"])


def keys_in(client: Any, bucket: str) -> list[str]:
    return sorted(str(one["Key"]) for one in client.list_objects_v2(Bucket=bucket).get("Contents", []))


def test_files_publish_dry_run_lists_the_five_keys_names_env_and_bucket_and_calls_no_s3(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No moto here: a dry run that built a bucket client and called it would fail on the disabled socket."""
    docx = built_policy_file(world)
    as_dev(world, monkeypatch, tmp_path)
    recipes = str(world.corpus.recipe.parent)

    result = invoke(
        "--json", "files", "publish", "--env", "dev", str(docx), "--dry-run", "--recipes", recipes
    )

    assert result.exit_code == ExitCode.OK, result.output
    data = envelope(result)["data"]
    assert (data["environment"], data["bucket"], data["dry_run"]) == ("dev", DEV_BUCKET, True)
    (one,) = data["files"]
    assert one["status"] == "WOULD_PUBLISH"
    sidecar = json.loads(docx.with_name(provenance_sidecar_name(docx.name)).read_text(encoding="utf-8"))
    prefix = f"files/nhi/aff/politics-da/{POLICY}/{sidecar['recipe_hash'][:12]}/"
    assert one["keys"] == [
        f"{prefix}{POLICY}.docx",
        f"{prefix}{POLICY}.docx.provenance.json",
        f"{prefix}{POLICY}.docx.quality.json",
        f"{prefix}recipe.yaml",
        f"{prefix}metadata.json",
    ]
    assert one["written"] == []

    shown = invoke("files", "publish", "--env", "dev", str(docx), "--dry-run", "--recipes", recipes)
    table = " ".join(shown.stdout.split())
    assert f"Dry run: would publish to the dev evidence bucket {DEV_BUCKET}" in table
    assert "WOULD_PUBLISH" in table


def test_files_publish_to_dev_publishes_then_skips_and_writes_only_under_files(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dev_bucket: Any
) -> None:
    docx = built_policy_file(world)
    as_dev(world, monkeypatch, tmp_path)
    arguments = (
        "files",
        "publish",
        "--env",
        "dev",
        str(docx.parent),
        "--recipes",
        str(world.corpus.recipe.parent),
    )

    first = invoke("--json", *arguments)
    assert first.exit_code == ExitCode.OK, first.output
    (one,) = envelope(first)["data"]["files"]
    assert one["status"] == "PUBLISHED" and len(one["written"]) == 5
    keys = keys_in(dev_bucket, DEV_BUCKET)
    assert keys == sorted(one["keys"])
    assert all(key.startswith("files/nhi/aff/politics-da/") for key in keys)
    assert keys_in(dev_bucket, PROD_BUCKET) == []

    again = invoke(*arguments)
    assert again.exit_code == ExitCode.OK, again.output
    shown = " ".join(again.stdout.split())
    assert f"Published to the dev evidence bucket {DEV_BUCKET}" in shown
    assert "SKIPPED" in shown and "1 SKIPPED" in shown
    for identity in ("Maple Grove", "Cedar Hollow", "ZaLu"):
        assert identity not in first.stdout + again.stdout + again.stderr


def test_files_publish_refuses_a_stale_or_failing_file_exit_1_naming_its_failing_checks(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dev_bucket: Any
) -> None:
    docx = built_policy_file(world)
    docx.write_bytes(tamper(docx.read_bytes()))
    as_dev(world, monkeypatch, tmp_path)
    arguments = ("files", "publish", "--env", "dev", str(docx), "--recipes", str(world.corpus.recipe.parent))

    stale = invoke("--json", *arguments)
    assert stale.exit_code == ExitCode.DOMAIN_FAILURE, stale.output
    assert envelope(stale)["error"]["code"] == "QUALITY_REPORT_STALE"

    checked = invoke("--json", "files", "check", str(docx))
    assert checked.exit_code == ExitCode.DOMAIN_FAILURE
    failed = invoke("--json", *arguments)
    assert failed.exit_code == ExitCode.DOMAIN_FAILURE, failed.output
    error = envelope(failed)["error"]
    assert error["code"] == "QUALITY_FAILED"
    (refused,) = error["details"]["files"]
    assert "evidence-identity" in refused["refusal"]["failing_checks"]
    assert "evidence-identity" in error["message"]

    panel = " ".join(invoke(*arguments).stderr.split())
    assert "[QUALITY_FAILED]" in panel and "failing: " in panel and "evidence-identity" in panel
    assert keys_in(dev_bucket, DEV_BUCKET) == []


def test_files_publish_refuses_another_environment_and_prod_without_confirm_prod(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    docx = built_policy_file(world)
    as_dev(world, monkeypatch, tmp_path, environment="prod")

    mismatch = invoke("--json", "files", "publish", "--env", "dev", str(docx))
    assert envelope(mismatch)["error"]["code"] == "ENVIRONMENT_MISMATCH"
    unconfirmed = invoke("--json", "files", "publish", "--env", "prod", str(docx))
    assert unconfirmed.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(unconfirmed)["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert PROD_BUCKET in envelope(unconfirmed)["error"]["message"]
    dry = invoke(
        "--json", "files", "publish", "--env", "prod", str(docx), "--dry-run",
        "--recipes", str(world.corpus.recipe.parent),
    )  # fmt: skip
    assert dry.exit_code == ExitCode.OK, dry.output
    assert envelope(dry)["data"]["files"][0]["status"] == "WOULD_PUBLISH"


def test_files_publish_of_a_directory_with_no_built_file_says_so(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "nothing-built"
    empty.mkdir()
    as_dev(world, monkeypatch, tmp_path)

    result = invoke("--json", "files", "publish", "--env", "dev", str(empty), "--dry-run")

    assert result.exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope(result)["error"]["code"] == "NO_BUILT_FILES"


def test_files_publish_help_documents_its_exit_codes() -> None:
    assert "publish" in invoke("files", "--help").stdout
    help_text = " ".join(invoke("files", "publish", "--help").stdout.split())
    for words in ("Exit 0:", "Exit 1:", "--dry-run", "--confirm-prod", "--recipes"):
        assert words in help_text


# ------------------------------------------------------------------------------------------------
# v1-e33-t12: `files check` and `files build` name each warned or failed card, its check and why
# ------------------------------------------------------------------------------------------------

#: Card 2's tag and the rest of its cite, replaced in the built file by words no card has.
PLANTED_TAG: Final = "Quillmarsh zephyr tag"
PLANTED_CITE: Final = "Brindlewick Observatory"


def without_card_twos_short_cite(docx: bytes) -> bytes:
    """The built file with card 2's short cite blanked, and its tag and cite holding the planted words."""
    source, target = BytesIO(docx), BytesIO()
    with zipfile.ZipFile(source) as package, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for info in package.infolist():
            body = package.read(info.filename)
            if info.filename == "word/document.xml":
                changed = (
                    body.replace(b"Achterberg 22", b"")
                    .replace(b"Politics DA answers: synthetic claim number 2", PLANTED_TAG.encode())
                    .replace(b"Synthetic Institute 2,", f"{PLANTED_CITE},".encode())
                )
                assert changed.count(PLANTED_TAG.encode()) == changed.count(PLANTED_CITE.encode()) == 1
                body = changed
            out.writestr(info, body)
    return target.getvalue()


def named_after_the_table(stdout: str) -> list[str]:
    """The lines below the checks table's bottom border."""
    lines = stdout.splitlines()
    bottom = max(index for index, line in enumerate(lines) if line.startswith("└"))
    return [line.strip() for line in lines[bottom + 1 :] if line.strip()]


def test_files_check_names_each_warned_and_failed_card_its_check_and_why(world: Planted) -> None:
    """Card 2 has no short cite (a WARN), a cite and tag that are not its source's (two FAILs), and the
    file is not the bytes its sidecar describes (a FAIL with no card). Each sentence is the check's own."""
    built = invoke("--json", "files", "build", str(world.corpus.recipe))
    docx = Path(envelope(built)["data"]["files"]["docx"])
    docx.write_bytes(without_card_twos_short_cite(docx.read_bytes()))
    second = world.corpus.cards[1].fingerprint

    shown = invoke("files", "check", str(docx))
    assert shown.exit_code == ExitCode.DOMAIN_FAILURE, shown.output
    named = named_after_the_table(shown.stdout)
    digest, short = "[0-9a-f]{12}…", second[:12]
    expected = [
        r"Failures and warnings:",
        rf"FAIL sidecar: the sidecar describes a file with SHA-256 {digest}, and this file is {digest}",
        rf"FAIL evidence-identity card 2 \({short}\): the built card's cite differs from the source card's "
        rf"\(built {digest}, source {digest}\)",
        rf"FAIL evidence-identity card 2 \({short}\): the built card's tag differs from the source card's, "
        r"and the sidecar records no override",
        rf"WARN cite-present card 2 \({short}\): the card has no short cite",
    ]
    assert len(named) == len(expected), named
    for line, pattern in zip(named, expected, strict=True):
        assert re.fullmatch(pattern, line), (line, pattern)

    as_json = envelope(invoke("--json", "files", "check", str(docx)))
    findings = as_json["error"]["details"]["quality"]["findings"]
    assert [(one["status"], one["check"], one["card_position"], one["fingerprint"]) for one in findings] == [
        ("FAIL", "sidecar", None, None),
        ("FAIL", "evidence-identity", 2, second),
        ("FAIL", "evidence-identity", 2, second),
        ("WARN", "cite-present", 2, second),
    ]
    assert findings[-1]["message"] == "the card has no short cite"


def test_no_named_line_or_finding_holds_the_warned_cards_tag_cite_or_evidence(world: Planted) -> None:
    built = invoke("--json", "files", "build", str(world.corpus.recipe))
    docx = Path(envelope(built)["data"]["files"]["docx"])
    docx.write_bytes(without_card_twos_short_cite(docx.read_bytes()))

    shown = invoke("files", "check", str(docx))
    as_json = invoke("--json", "files", "check", str(docx))
    assert "card 2 (" in shown.stdout and '"card_position": 2' in as_json.stdout
    for output in (shown.stdout, shown.stderr, as_json.stdout, as_json.stderr):
        for words in (
            PLANTED_TAG,
            PLANTED_CITE,
            "Synthetic Institute",
            "synthetic claim",
            "Synthetic evidence",
        ):
            assert words not in output


def test_files_build_names_each_failed_card_after_the_table_and_in_json(
    world: Planted, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As the wired-quality test above: an empty blob store fails every card's evidence-identity."""
    blind = FileQualityService(
        parser=DebateDocxParser(), snapshots=InMemorySnapshotStore(), suppression=empty_suppression_list()
    )
    monkeypatch.setattr(ServiceContainer, "file_quality", lambda _self: blind)  # pyright: ignore[reportUnknownLambdaType]
    why = "the source card cannot be read: the source's bytes are not in the blob store"

    shown = invoke("files", "build", str(world.corpus.recipe))
    assert shown.exit_code == ExitCode.DOMAIN_FAILURE, shown.output
    assert named_after_the_table(shown.stdout) == [
        "Failures and warnings:",
        *(
            f"FAIL evidence-identity card {card.number} ({card.fingerprint[:12]}): {why}"
            for card in world.corpus.cards
        ),
    ]

    shutil.rmtree(built_dir(world))
    findings = envelope(invoke("--json", "files", "build", str(world.corpus.recipe)))["error"]["details"][
        "quality"
    ]["findings"]
    assert [(one["card_position"], one["fingerprint"], one["message"]) for one in findings] == [
        (card.number, card.fingerprint, why) for card in world.corpus.cards
    ]


def test_files_build_and_check_of_a_clean_file_print_nothing_after_the_table(world: Planted) -> None:
    built = invoke("files", "build", str(world.corpus.recipe))
    assert built.exit_code == ExitCode.OK, built.output
    docx = next(built_dir(world).glob("*.docx"))
    checked = invoke("files", "check", str(docx))
    assert checked.exit_code == ExitCode.OK, checked.output
    for stdout in (built.stdout, checked.stdout):
        assert stdout.rstrip("\n").splitlines()[-1].startswith("└"), stdout
        assert "Failures and warnings" not in stdout
    assert envelope(invoke("--json", "files", "check", str(docx)))["data"]["quality"]["findings"] == []


#: The policy example's first analytic (paragraph 4: the header, the pocket, the hat, the block) put
#: back to the CP text slot, as a coach who marked a counterplan's draft ready unchanged would build it.
SLOT_LEFT: Final = (
    "WARN placeholders-replaced paragraph 4, under Politics DA answers > Uniqueness > Non-unique - the "
    "agenda is already stalled: the analytic is still the placeholder for the counterplan's text that "
    "`files suggest` drafts: write the text the team reads in its place, then build again"
)


def recipe_with_the_slot(world: Planted) -> Path:
    """The policy example, its first analytic the slot, beside it as a recipe of its own, status ready."""
    document = yaml.safe_load(world.corpus.recipe.read_text(encoding="utf-8"))
    items = document["structure"][0]["hats"][0]["blocks"][0]["items"]
    assert "analytic" in items[0]
    items[0] = {"analytic": CP_TEXT_SLOT}
    document["status"] = "ready"
    path = world.corpus.recipe.with_name("politics-da-slot-left.yaml")
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def test_files_build_check_and_publish_warn_of_the_cp_text_slot_and_publish_goes_ahead(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, dev_bucket: Any
) -> None:
    """`v1-e33-t15`: a WARN naming the block, printed as any other finding, and never a refusal."""
    recipe = recipe_with_the_slot(world)

    built = invoke("files", "build", str(recipe))
    assert built.exit_code == ExitCode.OK, built.output
    assert named_after_the_table(built.stdout) == ["Failures and warnings:", SLOT_LEFT]
    docx = built_dir(world) / "politics-da-slot-left.docx"

    checked = invoke("files", "check", str(docx))
    assert checked.exit_code == ExitCode.OK, checked.output
    assert named_after_the_table(checked.stdout) == ["Failures and warnings:", SLOT_LEFT]
    quality = envelope(invoke("--json", "files", "check", str(docx)))["data"]["quality"]
    assert quality["status"] == "PASS" and quality["failing_checks"] == []
    assert [(one["status"], one["check"]) for one in quality["findings"]] == [
        ("WARN", "placeholders-replaced")
    ]

    as_dev(world, monkeypatch, tmp_path)
    published = invoke("files", "publish", "--env", "dev", str(docx), "--recipes", str(recipe.parent))
    assert published.exit_code == ExitCode.OK, published.output
    shown = " ".join(published.stdout.split())
    assert "1 PUBLISHED. Warned, not blocked: politics-da-slot-left: placeholders-replaced" in shown
    assert named_after_the_table(published.stdout)[-2:] == [
        "Warned, not blocked in politics-da-slot-left:",
        SLOT_LEFT,
    ]
    assert len(keys_in(dev_bucket, DEV_BUCKET)) == 5


# ------------------------------------------------------------------------------------------------
# v1-e33-t10: a sidecar written under another style profile is warned of, by check and by publish
# ------------------------------------------------------------------------------------------------

#: The profile a file built before a profile change records (t09's), and the WARN it gets, by hand.
OTHER_PROFILE: Final = "2026.11.02-verbatim-2"


def other_profile_warning(running: str) -> str:
    return (
        f"the sidecar was written under style profile {OTHER_PROFILE}; the files were re-read with "
        f"{running}, and a card the two profiles read differently fails evidence-identity"
    )


def rewrite_sidecar(docx: Path, change: Any) -> None:
    """The built file's sidecar with `change` applied to its JSON; the `.docx` left as built."""
    sidecar = docx.with_name(provenance_sidecar_name(docx.name))
    document = json.loads(sidecar.read_text(encoding="utf-8"))
    change(document)
    sidecar.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def test_files_check_warns_once_of_a_sidecar_from_another_style_profile_naming_both(
    world: Planted,
) -> None:
    """The same profile gives no warning; another gives one, which never fails the file."""
    docx = built_policy_file(world)
    running = DebateDocxParser().profile_version
    assert running != OTHER_PROFILE
    same = invoke("--json", "files", "check", str(docx))
    assert same.exit_code == ExitCode.OK, same.output
    assert envelope(same)["data"]["quality"]["findings"] == []

    rewrite_sidecar(docx, lambda document: document.update(style_profile_version=OTHER_PROFILE))

    shown = invoke("files", "check", str(docx))
    assert shown.exit_code == ExitCode.OK, shown.output
    assert named_after_the_table(shown.stdout) == [
        "Failures and warnings:",
        f"WARN sidecar: {other_profile_warning(running)}",
    ]
    quality = envelope(invoke("--json", "files", "check", str(docx)))["data"]["quality"]
    assert quality["status"] == "PASS" and quality["failing_checks"] == []
    assert [(one["status"], one["check"], one["message"]) for one in quality["findings"]] == [
        ("WARN", "sidecar", other_profile_warning(running))
    ]


def test_files_check_fails_a_sidecar_with_no_style_profile_as_not_valid_and_names_no_profile(
    world: Planted,
) -> None:
    """Every sidecar ever written records its profile (required since `v1-e33-t02`); one without is
    not a sidecar this build reads, so the file FAILs, as for any other field it requires."""
    docx = built_policy_file(world)
    rewrite_sidecar(docx, lambda document: document.pop("style_profile_version"))

    quality = envelope(invoke("--json", "files", "check", str(docx)))["error"]["details"]["quality"]
    sidecar = [one for one in quality["findings"] if one["check"] == "sidecar"]
    assert [(one["status"], one["message"]) for one in sidecar] == [
        ("FAIL", "the sidecar is not valid: style_profile_version: Field required")
    ]
    assert not any("style profile" in one["message"] for one in quality["findings"])


def test_files_publish_re_check_warns_of_another_style_profile_and_its_refusal_says_so(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The quality report beside the file is `files build`'s, from before the sidecar changed, so the
    warning can only come from publish's own re-check. A dry run: no bucket client, no S3 call.

    Then card 1's sidecar entry ends a paragraph later, as another profile might have bounded it: its
    `evidence-identity` FAILs, and the refusal says the profiles differ.
    """
    docx = built_policy_file(world)
    running = DebateDocxParser().profile_version
    rewrite_sidecar(docx, lambda document: document.update(style_profile_version=OTHER_PROFILE))
    as_dev(world, monkeypatch, tmp_path)
    arguments = (
        "files",
        "publish",
        "--env",
        "dev",
        str(docx),
        "--dry-run",
        "--recipes",
        str(world.corpus.recipe.parent),
    )

    warned = invoke("--json", *arguments)
    assert warned.exit_code == ExitCode.OK, warned.output
    (one,) = envelope(warned)["data"]["files"]
    assert (one["status"], one["warned_checks"]) == ("WOULD_PUBLISH", ["sidecar"])

    def bounded_otherwise(document: dict[str, Any]) -> None:
        document["cards"][0]["last_element_index"] += 1

    rewrite_sidecar(docx, bounded_otherwise)
    refused = invoke("--json", *arguments)
    assert refused.exit_code == ExitCode.DOMAIN_FAILURE, refused.output
    error = envelope(refused)["error"]
    assert error["code"] == "QUALITY_FAILED"
    (file,) = error["details"]["files"]
    assert file["refusal"]["failing_checks"] == ["evidence-identity"]
    assert other_profile_warning(running) in file["refusal"]["message"]
    assert other_profile_warning(running) in error["message"]

    panel = " ".join(invoke(*arguments).stderr.replace("│", " ").split())
    assert other_profile_warning(running) in panel


# ------------------------------------------------------------------------------------------------
# v1-e33-t16: publish names a report from an older version of the checks, and prints each warning
# ------------------------------------------------------------------------------------------------

#: The checks' version before `v1-e33-t15`'s bump, by hand; its reports had no `placeholders-replaced`.
OLDER_CHECKER: Final = "2026.10.27-file-checks-2"


def publish_dry_run(world: Planted, docx: Path) -> tuple[str, ...]:
    return (
        "files",
        "publish",
        "--env",
        "dev",
        str(docx),
        "--dry-run",
        "--recipes",
        str(world.corpus.recipe.parent),
    )


def test_files_publish_refuses_a_report_from_an_older_version_of_the_checks_naming_both(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """As t15's bump left every built, unpublished file: its report is older, not missing. A dry run."""
    docx = built_policy_file(world)
    report = docx.with_name(f"{docx.name}.quality.json")
    document = json.loads(report.read_text(encoding="utf-8"))
    current = document["checker_version"]
    assert current != OLDER_CHECKER
    document["checker_version"] = OLDER_CHECKER
    document["checks"] = [one for one in document["checks"] if one["check"] != "placeholders-replaced"]
    document["results"] = [one for one in document["results"] if one["check"] != "placeholders-replaced"]
    report.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    as_dev(world, monkeypatch, tmp_path)

    refused = invoke("--json", *publish_dry_run(world, docx))

    assert refused.exit_code == ExitCode.DOMAIN_FAILURE, refused.output
    error = envelope(refused)["error"]
    assert error["code"] == "QUALITY_REPORT_OUTDATED"
    (file,) = error["details"]["files"]
    message = file["refusal"]["message"]
    assert OLDER_CHECKER in message and current in message
    assert "/" not in message and docx.name not in message
    assert (
        file["refusal"]["hint"] == f"Check it with `debate-research files check {docx}`, then publish again."
    )

    panel = " ".join(invoke(*publish_dry_run(world, docx)).stderr.replace("│", " ").split())
    assert "[QUALITY_REPORT_OUTDATED]" in panel and OLDER_CHECKER in panel and current in panel
    assert "debate-research files check" in panel


def test_files_publish_prints_each_warning_of_a_file_it_lets_through_as_files_check_does(
    world: Planted, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PM amendment 2026-10-31, from t10's follow-up: the profile WARN's own line, not only `sidecar`."""
    docx = built_policy_file(world)
    running = DebateDocxParser().profile_version
    rewrite_sidecar(docx, lambda document: document.update(style_profile_version=OTHER_PROFILE))
    as_dev(world, monkeypatch, tmp_path)

    shown = invoke(*publish_dry_run(world, docx))

    assert shown.exit_code == ExitCode.OK, shown.output
    assert named_after_the_table(shown.stdout)[-2:] == [
        f"Warned, not blocked in {docx.stem}:",
        f"WARN sidecar: {other_profile_warning(running)}",
    ]
    (one,) = envelope(invoke("--json", *publish_dry_run(world, docx)))["data"]["files"]
    assert [(found["status"], found["check"], found["message"]) for found in one["warnings"]] == [
        ("WARN", "sidecar", other_profile_warning(running))
    ]
