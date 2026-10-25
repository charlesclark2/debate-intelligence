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
  with `--allow-draft`.

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
from tests.fixtures.file_builder.example_corpus import EXAMPLES, ExampleCorpus, example_corpus
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import CliRun, InstalledCli

from debate_cli.exit_codes import ExitCode

EXAMPLE = "policy-nhi-politics-da-answers"


@pytest.fixture
def world(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[tuple[ExampleCorpus, Path]]:
    """The policy example imported and parsed into a dev profile of this check's own."""
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
    corpus = example_corpus(EXAMPLES / f"{EXAMPLE}.yaml", tmp_path / "corpus")
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
    yield corpus, data_dir


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
