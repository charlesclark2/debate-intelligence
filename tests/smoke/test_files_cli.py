"""`debate-research files build`, `files check` and `files suggest`, offline, as `validate-dev` runs them.

t01's policy example recipe is filed as one synthetic weekly archive
(:mod:`tests.fixtures.file_builder.example_corpus`), imported with `caselist import` and parsed with
`caselist parse`, both through the installed command, with two workers in the process pool. Then the
installed build:

* **builds** the rewritten recipe into a fresh installation's data directory: a `.docx`, its
  `.provenance.json` and a PASS quality report, five cards from five sources with two tag overrides,
  counted by hand from the recipe (`packages/debate_cli/tests/commands/test_files.py`);
* **checks** the built file, PASS, and then a copy with one word of its evidence changed, FAIL;
* **suggests** a draft for the recipe's position from the landscape, with no model, and builds it
  with `--allow-draft`;
* **suggests a counterplan's draft** (`v1-e33-t15`) from the synthetic counterplan recipe in
  `tests/fixtures/file_builder/counterplans/`, filed and parsed the same way with its position a
  counterplan: the draft's first block opens with the CP text slot. Marked `status: ready` and
  nothing else, it builds, and the build and `files check` warn of the slot on that block, PASS.

Nothing is published and no stand-in is needed: nothing in these commands reaches a bucket, a model
or the network, and the harness's network guard fails the check if anything tries. Unmarked, like the
other offline caselist smoke checks. Every school, team code and card is invented, and none of them
may appear in what the commands print.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
import yaml
from tests.fixtures.file_builder.example_corpus import COUNTERPLANS, EXAMPLES, ExampleCorpus, example_corpus
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import CliRun, InstalledCli

from debate_cli.exit_codes import ExitCode
from debate_core.application.file_suggest_service import CP_TEXT_SLOT

EXAMPLE = "policy-nhi-politics-da-answers"
COUNTERPLAN = "policy-nhi-states-cp"


@pytest.fixture
def world(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[tuple[ExampleCorpus, Path]]:
    """The policy example imported and parsed into a dev profile of this check's own."""
    yield planted(installed_cli, tmp_path, EXAMPLES / f"{EXAMPLE}.yaml", kind="da")


@pytest.fixture
def counterplan_world(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[tuple[ExampleCorpus, Path]]:
    """The synthetic counterplan recipe, its position a counterplan, imported and parsed the same way."""
    yield planted(installed_cli, tmp_path, COUNTERPLANS / f"{COUNTERPLAN}.yaml", kind="cp")


def planted(
    installed_cli: InstalledCli, tmp_path: Path, recipe: Path, *, kind: str
) -> tuple[ExampleCorpus, Path]:
    data_dir = tmp_path / "data"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{data_dir}"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n'
        "[parse]\nworkers = 2\nfailure_rate_threshold = 0.0\n",
        encoding="utf-8",
    )
    installed_cli.configure(DEBATE_PROFILE_DIR=str(profiles), DEBATE_ENV="dev", DEBATE_STORAGE__DATA_DIR=None)
    corpus = example_corpus(recipe, tmp_path / "corpus", kind=kind)
    imported = installed_cli.run(
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
    parsed = installed_cli.run("--json", "caselist", "parse", "--caselist", corpus.caselist)
    assert parsed.exit_code == ExitCode.OK, parsed.output
    return corpus, data_dir


def data_of(result: CliRun) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    found: dict[str, Any] = json.loads(lines[0])
    return found


def tampered(docx: bytes) -> bytes:
    """The built file with one word of the first card's evidence changed."""
    source, target = BytesIO(docx), BytesIO()
    with zipfile.ZipFile(source) as package, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as out:
        for info in package.infolist():
            body = package.read(info.filename)
            if info.filename == "word/document.xml":
                body = body.replace(b"Synthetic evidence 1 begins", b"Synthetic evidence 9 begins")
            out.writestr(info, body)
    return target.getvalue()


def test_files_build_then_check_writes_a_pass_file_and_catches_a_tampered_copy(
    installed_cli: InstalledCli, world: tuple[ExampleCorpus, Path], tmp_path: Path
) -> None:
    corpus, data_dir = world
    built = installed_cli.run("--json", "files", "build", str(corpus.recipe))

    assert built.exit_code == ExitCode.OK, built.output
    data = data_of(built)["data"]
    docx = data_dir / "files" / "built" / "nhi" / f"{EXAMPLE}.docx"
    assert data["files"]["docx"] == str(docx)
    for written in data["files"].values():
        assert Path(written).is_file()
    assert (
        data["counts"]["cards_placed"],
        data["counts"]["sources_used"],
        data["counts"]["tag_overrides"],
    ) == (
        5,
        5,
        2,
    )
    assert data["quality"]["status"] == "PASS"

    checked = installed_cli.run("--json", "files", "check", str(docx))
    assert checked.exit_code == ExitCode.OK, checked.output
    assert data_of(checked)["data"]["quality"]["status"] == "PASS"

    copy = tmp_path / "tampered" / docx.name
    copy.parent.mkdir()
    copy.write_bytes(tampered(docx.read_bytes()))
    sidecar = docx.with_name(f"{docx.name}.provenance.json")
    copy.with_name(sidecar.name).write_bytes(sidecar.read_bytes())
    failed = installed_cli.run("--json", "files", "check", str(copy))
    assert failed.exit_code == ExitCode.DOMAIN_FAILURE, failed.output
    error = data_of(failed)["error"]
    assert error["code"] == "QUALITY_FAILED"
    assert "evidence-identity" in error["details"]["quality"]["failing_checks"]

    for identity in ("Maple Grove", "Cedar Hollow", '"QX"', "ZaLu", "Synthetic evidence"):
        assert identity not in built.stdout + checked.stdout + failed.stdout


def test_files_suggest_writes_a_draft_that_builds_with_allow_draft_offline_with_no_model(
    installed_cli: InstalledCli, world: tuple[ExampleCorpus, Path]
) -> None:
    corpus, data_dir = world
    suggested = installed_cli.run(
        "--json",
        "files",
        "suggest",
        "--caselist",
        corpus.caselist,
        "--position",
        "politics-da",
        "--top",
        "10",
        "--config-dir",
        str(corpus.config_dir),
    )

    assert suggested.exit_code == ExitCode.OK, suggested.output
    data = data_of(suggested)["data"]
    draft = Path(data["path"])
    assert draft == data_dir / "files" / "recipes" / "nhi" / "politics-da-aff-draft.yaml"
    document = yaml.safe_load(draft.read_text(encoding="utf-8"))
    assert document["status"] == "draft"
    fingerprints = {
        item["fingerprint"] for block in document["structure"][0]["blocks"] for item in block["items"]
    }
    assert fingerprints == {card.fingerprint for card in corpus.cards}

    refused = installed_cli.run("--json", "files", "build", str(draft))
    assert refused.exit_code == ExitCode.USAGE_ERROR, refused.output
    built = installed_cli.run("--json", "files", "build", str(draft), "--allow-draft")
    assert built.exit_code == ExitCode.OK, built.output
    assert data_of(built)["data"]["counts"]["cards_placed"] == len(corpus.cards)


def test_files_suggest_drafts_a_counterplan_with_the_slot_first_and_a_build_of_it_unchanged_warns(
    installed_cli: InstalledCli, counterplan_world: tuple[ExampleCorpus, Path]
) -> None:
    corpus, data_dir = counterplan_world
    suggested = installed_cli.run(
        "--json",
        "files",
        "suggest",
        "--caselist",
        corpus.caselist,
        "--position",
        "states-cp",
        "--top",
        "10",
        "--config-dir",
        str(corpus.config_dir),
    )

    assert suggested.exit_code == ExitCode.OK, suggested.output
    data = data_of(suggested)["data"]
    assert data["other_positions_left_out"] == {"blocks": 0, "cards": 0}
    draft = Path(data["path"])
    assert draft == data_dir / "files" / "recipes" / "nhi" / "states-cp-neg-draft.yaml"
    text = draft.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    assert document["status"] == "draft"
    pocket = document["structure"][0]
    first_block = pocket["blocks"][0]
    assert first_block["items"][0] == {"analytic": CP_TEXT_SLOT}
    fingerprints = {item.get("fingerprint") for block in pocket["blocks"] for item in block["items"]}
    assert fingerprints - {None} == {card.fingerprint for card in corpus.cards}

    assert text.count("status: draft\n") == 1
    draft.write_text(text.replace("status: draft\n", "status: ready\n"), encoding="utf-8")
    built = installed_cli.run("--json", "files", "build", str(draft))

    assert built.exit_code == ExitCode.OK, built.output
    quality = data_of(built)["data"]["quality"]
    assert quality["status"] == "PASS" and quality["failing_checks"] == []
    assert [
        (one["status"], one["check"], one["paragraph_index"], one["section_path"])
        for one in quality["findings"]
    ] == [("WARN", "placeholders-replaced", 3, [pocket["pocket"], first_block["block"]])]

    docx = Path(data_of(built)["data"]["files"]["docx"])
    checked = installed_cli.run("files", "check", str(docx))
    assert checked.exit_code == ExitCode.OK, checked.output
    shown = " ".join(checked.stdout.split())
    assert (
        f"WARN placeholders-replaced paragraph 3, under {pocket['pocket']} > {first_block['block']}: "
        in shown
    )
    for identity in ("Maple Grove", "Cedar Hollow", '"QX"', "ZaLu", "Synthetic evidence"):
        assert identity not in suggested.stdout + built.stdout + checked.stdout
