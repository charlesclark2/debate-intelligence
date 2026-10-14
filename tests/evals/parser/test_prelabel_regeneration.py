"""Regenerating the pre-labels of the files nobody has corrected (v1-e31-t18 ac6).

The operator's sequence, run here on three invented files exactly as the follow-up gives it:

1. `worksheet --all --remove-untouched`: remove every worksheet that is still exactly as written;
2. `prelabel --all`: regenerate every PRELABELED file's pre-labels with the current parser;
3. `worksheet --all`: write the worksheets that are now missing.

A CORRECTED or COACH_REVIEWED label file, the sampling plan and its id come through byte for byte.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from tests.evals.parser.corpus import parse_evaluation_file
from tests.evals.parser.digests import create_key, keyed_digest, load_key
from tests.evals.parser.labels_schema import (
    REPOSITORY_ROOT,
    Category,
    DebateFormat,
    FileSamplingPlan,
    LabelStatus,
    Manifest,
    ManifestEntry,
    SamplingPlan,
    TemplateFamily,
    label_path_for,
    load_label_file,
)
from tests.evals.parser.synthetic import build_invented_corpus_file

from debate_core.domain.style_profile import StructuralUnit
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser

sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import prelabel_docx as prelabel  # noqa: E402

PLAN_ID = "0123456789abcdef"
OLDER_PARSER = "an-older-parser"


@dataclass(frozen=True)
class _Evaluation:
    options: list[str]
    entries: tuple[ManifestEntry, ...]
    labels: Path
    worksheets: Path
    plan: Path

    def run(self, *arguments: str) -> int:
        return prelabel.main([*self.options, *arguments])

    def label_file(self, number: int) -> Path:
        return label_path_for(self.entries[number].digest, self.labels)

    def worksheet(self, number: int) -> Path:
        return self.worksheets / f"{self.entries[number].digest[:16]}.csv"

    def prefix(self, number: int) -> str:
        return self.entries[number].digest[:16]

    def texts(self, number: int) -> list[str]:
        content = build_invented_corpus_file(number)
        return [
            s.text for s in parse_evaluation_file(DebateDocxParser(), self.entries[number], content).sections
        ]


@pytest.fixture
def evaluation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Evaluation:
    monkeypatch.setenv("DEBATE_PARSER_EVAL_KEY_FILE", str(create_key(tmp_path / "private" / "digest.key")))
    key = load_key()
    assert key is not None
    paths: dict[str, str] = {}
    entries = []
    for number in range(3):
        content = build_invented_corpus_file(number)
        path = tmp_path / "corpus" / f"invented {number}.docx"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        digest = keyed_digest(content, key)
        paths[digest] = str(path)
        entries.append(
            ManifestEntry(
                digest=digest,
                category=Category.CAMP,
                season="2026-27",
                debate_format=DebateFormat.POLICY,
                template_family=TemplateFamily.VERBATIM,
            )  # fmt: skip
        )
    (tmp_path / "private" / "paths.json").write_text(json.dumps(paths), encoding="utf-8")
    monkeypatch.setenv("DEBATE_PARSER_EVAL_PATHS", str(tmp_path / "private" / "paths.json"))
    directory = tmp_path / "eval"
    (directory / "labels").mkdir(parents=True)
    (directory / "manifest.json").write_text(
        Manifest(entries=tuple(entries)).model_dump_json(), encoding="utf-8"
    )
    whole = tuple(
        FileSamplingPlan(digest=e.digest, paragraphs=12, blocks=((0, 11),), full=True) for e in entries
    )
    plan = SamplingPlan(plan_id=PLAN_ID, generated_on="2026-10-14", parser_version="test", files=whole)
    (directory / "sampling-plan.json").write_text(plan.model_dump_json(), encoding="utf-8")
    made = _Evaluation(
        options=[
            "--manifest",
            str(directory / "manifest.json"),
            "--plan",
            str(directory / "sampling-plan.json"),
            "--labels-dir",
            str(directory / "labels"),
        ],  # fmt: skip
        entries=tuple(entries),
        labels=directory / "labels",
        worksheets=tmp_path / "worksheets",
        plan=directory / "sampling-plan.json",
    )
    assert made.run("prelabel", "--all") == 0
    assert made.run("worksheet", "--all", "--out-dir", str(made.worksheets)) == 0
    return made


def _correct(evaluation: _Evaluation, number: int) -> None:
    """A person checks every row as pre-labeled, and the worksheet is imported and deleted."""
    path = evaluation.worksheet(number)
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({**row, "checked": "y"} for row in rows)
    imported = ["import", evaluation.prefix(number), "--worksheet", str(path), "--corrected-by", "coach"]
    assert evaluation.run(*imported) == 0
    path.unlink()


def _as_if_from_an_older_parser(evaluation: _Evaluation, number: int) -> None:
    """Rewrite a pre-label as an older parser might have left it, and its worksheet from that."""
    labels = load_label_file(evaluation.label_file(number))
    header = labels.header.model_copy(update={"prelabel_parser_version": OLDER_PARSER})
    first = labels.paragraphs[0].model_copy(update={"unit": StructuralUnit.HAT})
    older = replace(labels, header=header, paragraphs=(first, *labels.paragraphs[1:]))
    evaluation.label_file(number).write_text(older.to_jsonl(), encoding="utf-8")
    evaluation.worksheet(number).write_bytes(prelabel.worksheet_csv_bytes(older, evaluation.texts(number)))


def _regenerate(evaluation: _Evaluation) -> None:
    """Operator follow-up: the three commands, in order."""
    out = ["--out-dir", str(evaluation.worksheets)]
    assert evaluation.run("worksheet", "--all", "--remove-untouched", *out) == 0
    assert evaluation.run("prelabel", "--all") == 0
    assert evaluation.run("worksheet", "--all", *out) == 0


def test_regeneration_rewrites_only_prelabeled_files_and_keeps_the_plan(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str]
) -> None:
    _correct(evaluation, 1)
    _correct(evaluation, 2)
    assert evaluation.run("mark-reviewed", evaluation.prefix(2), "--reviewer", "coach") == 0
    _as_if_from_an_older_parser(evaluation, 0)
    stale_worksheet = evaluation.worksheet(0).read_bytes()
    kept = {n: evaluation.label_file(n).read_bytes() for n in (1, 2)}
    plan_before = evaluation.plan.read_bytes()
    capsys.readouterr()

    _regenerate(evaluation)

    printed = capsys.readouterr().out
    assert load_label_file(evaluation.label_file(1)).header.status is LabelStatus.CORRECTED
    assert load_label_file(evaluation.label_file(2)).header.status is LabelStatus.COACH_REVIEWED
    for number, content in kept.items():
        assert evaluation.label_file(number).read_bytes() == content
        assert f"{evaluation.prefix(number)}: already corrected; left alone" in printed
    assert evaluation.plan.read_bytes() == plan_before
    regenerated = load_label_file(evaluation.label_file(0))
    assert regenerated.header.status is LabelStatus.PRELABELED
    assert regenerated.header.prelabel_parser_version == DOCX_PARSER_VERSION
    assert regenerated.paragraphs[0].unit is StructuralUnit.POCKET
    assert {load_label_file(evaluation.label_file(n)).header.plan_id for n in range(3)} == {PLAN_ID}
    assert evaluation.worksheet(0).read_bytes() == prelabel.worksheet_csv_bytes(
        regenerated, evaluation.texts(0)
    )
    assert evaluation.worksheet(0).read_bytes() != stale_worksheet
    assert not evaluation.worksheet(1).exists() and not evaluation.worksheet(2).exists()


@pytest.mark.parametrize("started", ["edited", "numbers", "progress"])
def test_a_worksheet_someone_has_started_is_kept_and_named(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str], started: str
) -> None:
    path = evaluation.worksheet(0)
    if started == "edited":
        path.write_bytes(path.read_bytes().replace(b",POCKET,", b",HAT,", 1))
    elif started == "numbers":
        path.with_suffix(".numbers").mkdir()
    else:
        path.with_name(f"{evaluation.prefix(0)}.progress.json").write_text("{}", encoding="utf-8")
    before = path.read_bytes()
    capsys.readouterr()

    assert (
        evaluation.run("worksheet", "--all", "--remove-untouched", "--out-dir", str(evaluation.worksheets))
        == 0
    )

    printed = capsys.readouterr().out
    assert path.read_bytes() == before
    assert f"{evaluation.prefix(0)}: " in printed and "kept" in printed
    assert not evaluation.worksheet(1).exists() and not evaluation.worksheet(2).exists()
    assert "2 untouched worksheet(s) removed, 1 kept" in printed


def test_removing_untouched_worksheets_writes_none_and_refuses_the_repository(
    evaluation: _Evaluation,
) -> None:
    inside = REPOSITORY_ROOT / "build" / "worksheets"
    with pytest.raises(prelabel.WorksheetError, match="outside the repository"):
        evaluation.run("worksheet", "--all", "--remove-untouched", "--out-dir", str(inside))
    with pytest.raises(SystemExit):
        evaluation.run(
            "worksheet", evaluation.prefix(0), "--remove-untouched", "--out-dir", str(evaluation.worksheets)
        )


@pytest.mark.parametrize("planned", [13, 11])
def test_a_file_the_parser_now_reads_into_other_paragraphs_than_the_plan_is_left_alone(
    evaluation: _Evaluation, capsys: pytest.CaptureFixture[str], planned: int
) -> None:
    """The plan does not move, so a pre-label that no longer fits it is not written. With fewer
    paragraphs planned than read, the old command wrote one silently; with more, it crashed."""
    plan = SamplingPlan.model_validate_json(evaluation.plan.read_text(encoding="utf-8"))
    changed = plan.files[0].model_copy(update={"paragraphs": planned, "blocks": ((0, planned - 1),)})
    files = (changed, *plan.files[1:])
    evaluation.plan.write_text(plan.model_copy(update={"files": files}).model_dump_json(), encoding="utf-8")
    before = {n: evaluation.label_file(n).read_bytes() for n in range(3)}
    capsys.readouterr()

    assert evaluation.run("prelabel", "--all") == 1

    printed = capsys.readouterr().out
    expected = (
        f"{evaluation.prefix(0)}: REFUSED; the parser reads 12 paragraphs and the sampling plan has {planned}"
    )
    assert expected in printed
    assert evaluation.label_file(0).read_bytes() == before[0]
