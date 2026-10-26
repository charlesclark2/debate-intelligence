"""`debate-research files publish --dry-run`, offline, against a dev configuration, as `validate-dev` runs it.

t01's policy example recipe is filed as one synthetic weekly archive
(:mod:`tests.fixtures.file_builder.example_corpus`), imported with `caselist import`, parsed with
`caselist parse` and built with `files build`, all through the installed command, into a dev profile of
this check's own that names an evidence bucket. Then the installed build:

* **plans a publish** of the built file with `--dry-run`: the dev environment and bucket named, the
  file `WOULD_PUBLISH`, and its five keys under `files/nhi/aff/politics-da/<slug>/<recipe hash>/`,
  `metadata.json` last;
* **refuses** a file built from a draft recipe, though its quality report is PASS, and a file whose
  quality report is gone, each with exit 1 and its reason.

A dry run builds no bucket client, so no stand-in is needed: the harness's network guard fails the
check if the command tries to reach S3 or anything else. Unmarked, like the other offline file builder
smoke checks. Every school, team code and card is invented, and none of them may appear in what the
command prints.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.file_builder.example_corpus import EXAMPLES, ExampleCorpus, example_corpus
from tests.fixtures.model_routing import EXAMPLE_ROUTING_FILE
from tests.smoke.installed_build import CliRun, InstalledCli

from debate_cli.exit_codes import ExitCode

EXAMPLE = "policy-nhi-politics-da-answers"
BUCKET = "debate-dev-evidence-smoke"


@pytest.fixture
def world(installed_cli: InstalledCli, tmp_path: Path) -> Iterator[tuple[ExampleCorpus, Path]]:
    """The policy example imported, parsed and built in a dev profile of this check's own; the built file."""
    data_dir = tmp_path / "data"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{data_dir}"\n'
        f'[storage.s3]\nbucket = "{BUCKET}"\nregion = "us-east-1"\n'
        f'[models]\nrouting_file = "{EXAMPLE_ROUTING_FILE}"\nbudget_usd_daily = 1.0\n'
        "[parse]\nworkers = 2\nfailure_rate_threshold = 0.0\n",
        encoding="utf-8",
    )
    installed_cli.configure(DEBATE_PROFILE_DIR=str(profiles), DEBATE_ENV="dev", DEBATE_STORAGE__DATA_DIR=None)
    corpus = example_corpus(EXAMPLES / f"{EXAMPLE}.yaml", tmp_path / "corpus")
    for step in (
        ("caselist", "import", str(corpus.archive), "--caselist", corpus.caselist),
        ("caselist", "parse", "--caselist", corpus.caselist),
    ):
        arguments = (*step, "--snapshot", corpus.snapshot.isoformat()) if step[1] == "import" else step
        ran = installed_cli.run("--json", *arguments)
        assert ran.exit_code == ExitCode.OK, ran.output
    built = installed_cli.run("--json", "files", "build", str(corpus.recipe))
    assert built.exit_code == ExitCode.OK, built.output
    yield corpus, Path(data_of(built)["data"]["files"]["docx"])


def data_of(result: CliRun) -> dict[str, Any]:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected one line of JSON on stdout; got {lines!r}\n{result.stderr}"
    found: dict[str, Any] = json.loads(lines[0])
    return found


def publish(installed_cli: InstalledCli, corpus: ExampleCorpus, path: Path, *extra: str) -> CliRun:
    return installed_cli.run(
        "files",
        "publish",
        "--env",
        "dev",
        str(path),
        "--dry-run",
        "--recipes",
        str(corpus.recipe.parent),
        *extra,
    )


def test_files_publish_dry_run_names_the_dev_bucket_and_the_five_keys_and_writes_nothing(
    installed_cli: InstalledCli, world: tuple[ExampleCorpus, Path]
) -> None:
    corpus, docx = world
    planned = publish(installed_cli, corpus, docx, "--json")

    assert planned.exit_code == ExitCode.OK, planned.output
    data = data_of(planned)["data"]
    assert (data["environment"], data["bucket"], data["dry_run"]) == ("dev", BUCKET, True)
    (one,) = data["files"]
    assert one["status"] == "WOULD_PUBLISH"
    recipe_hash = json.loads(docx.with_name(f"{docx.name}.provenance.json").read_text(encoding="utf-8"))[
        "recipe_hash"
    ]
    prefix = f"files/nhi/aff/politics-da/{EXAMPLE}/{recipe_hash[:12]}/"
    assert one["keys"] == [
        f"{prefix}{EXAMPLE}.docx",
        f"{prefix}{EXAMPLE}.docx.provenance.json",
        f"{prefix}{EXAMPLE}.docx.quality.json",
        f"{prefix}recipe.yaml",
        f"{prefix}metadata.json",
    ]
    assert one["written"] == []

    shown = publish(installed_cli, corpus, docx)
    assert shown.exit_code == ExitCode.OK, shown.output
    assert f"Dry run: would publish to the dev evidence bucket {BUCKET}" in " ".join(shown.stdout.split())
    for identity in ("Maple Grove", "Cedar Hollow", '"QX"', "ZaLu", "Synthetic evidence"):
        assert identity not in planned.stdout + shown.stdout


def test_files_publish_dry_run_refuses_a_draft_and_a_file_with_no_quality_report(
    installed_cli: InstalledCli, world: tuple[ExampleCorpus, Path]
) -> None:
    corpus, docx = world
    corpus.recipe.write_text(corpus.recipe.read_text(encoding="utf-8") + "status: draft\n", encoding="utf-8")
    drafted = installed_cli.run("--json", "files", "build", str(corpus.recipe), "--allow-draft")
    assert drafted.exit_code == ExitCode.OK, drafted.output
    assert data_of(drafted)["data"]["quality"]["status"] == "PASS"

    draft = publish(installed_cli, corpus, docx, "--json")
    assert draft.exit_code == ExitCode.DOMAIN_FAILURE, draft.output
    assert data_of(draft)["error"]["code"] == "BUILT_FROM_A_DRAFT"

    docx.with_name(f"{docx.name}.quality.json").unlink()
    unchecked = publish(installed_cli, corpus, docx, "--json")
    assert unchecked.exit_code == ExitCode.DOMAIN_FAILURE, unchecked.output
    assert data_of(unchecked)["error"]["code"] == "QUALITY_REPORT_MISSING"
