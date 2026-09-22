"""Finding the evaluation files where they live, and running the evaluation over them.

The evaluation files are never in the repository (see `labels_schema`). On the operator's machine
a **path map** — a JSON object from SHA-256 to an absolute path — says where each one is. The
path map is written by `scripts/select_eval_files.py`, lives **outside the repository**
(`~/.debate-intelligence/parser-eval-paths.json` by default, or `$DEBATE_PARSER_EVAL_PATHS`), and
is refused if it is pointed inside it: a path carries a school and a team code.

Where there is no path map — a CI runner, a fresh clone — the evaluation has nothing to run
against, and the tests that need it skip with a message saying so. The policy is explicit that the
real corpus never reaches a CI runner (`caselist-data-use.md`, dev environment exception, limit 4).
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Final

from tests.evals.parser.labels_schema import (
    REPOSITORY_ROOT,
    Category,
    LabelFile,
    LabelStatus,
    Manifest,
    ManifestEntry,
    status_counts,
    validate_against_texts,
    validate_label_file,
)
from tests.evals.parser.metrics import (
    FileScore,
    check_against_baseline,
    group_scores,
    prediction_from_document,
    report_json,
    score_file,
)

from debate_core.domain.caselist.entities import SourceDocument
from debate_core.domain.caselist.values import SourceFormat, SourceOrigin
from debate_core.domain.debate_files import ParsedDocument
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION, DebateDocxParser

__all__ = [
    "DEFAULT_PATH_MAP",
    "PATH_MAP_ENVIRONMENT_VARIABLE",
    "TIERS",
    "EvaluationSetupError",
    "load_evaluation_document",
    "load_path_map",
    "parse_evaluation_file",
    "path_map_location",
    "run_evaluation",
]

PATH_MAP_ENVIRONMENT_VARIABLE: Final = "DEBATE_PARSER_EVAL_PATHS"
DEFAULT_PATH_MAP: Final = Path.home() / ".debate-intelligence" / "parser-eval-paths.json"

#: `pr-subset` runs in the default pytest run; `full` in the `eval and slow` tier.
TIERS: Final = ("pr-subset", "full")

#: Provenance the parser needs and the evaluation does not use. The domain model has no origin for
#: a team's own file, so team files are parsed as if from a camp; parsing does not depend on origin.
_EVAL_SNAPSHOT: Final = date(2026, 9, 15)
_TEAM_FILE_CAMP: Final = "team-files"


class EvaluationSetupError(RuntimeError):
    """The evaluation cannot be run honestly: a file is missing, changed, or not yet labeled."""


def path_map_location() -> Path:
    configured = os.environ.get(PATH_MAP_ENVIRONMENT_VARIABLE)
    return Path(configured).expanduser() if configured else DEFAULT_PATH_MAP


def _inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPOSITORY_ROOT)
    except ValueError:
        return False
    return True


def load_path_map(location: Path | None = None) -> dict[str, Path] | None:
    """SHA-256 → local path, or None when this machine has no evaluation corpus."""
    location = location if location is not None else path_map_location()
    if _inside_repository(location):
        raise EvaluationSetupError(
            "the evaluation path map must live outside the repository: its paths name schools and team codes"
        )
    if not location.is_file():
        return None
    raw: dict[str, str] = json.loads(location.read_text(encoding="utf-8"))
    return {sha: Path(path) for sha, path in raw.items()}


def _source_for(entry: ManifestEntry, content: bytes) -> tuple[SourceDocument, str | None]:
    caselist = entry.category is Category.CASELIST
    source = SourceDocument(
        sha256=entry.sha256,
        byte_size=len(content),
        source_format=SourceFormat.DOCX,
        origin=SourceOrigin.CASELIST_ARCHIVE if caselist else SourceOrigin.OPENEV,
        caselist="hsld26" if caselist else None,
        first_seen_snapshot=_EVAL_SNAPSHOT,
        last_seen_snapshot=_EVAL_SNAPSHOT,
    )
    camp = None if caselist else (_TEAM_FILE_CAMP if entry.category is Category.TEAM else "camp")
    return source, camp


def parse_evaluation_file(parser: DebateDocxParser, entry: ManifestEntry, content: bytes) -> ParsedDocument:
    """Parse one evaluation file. A refusal is an error here: every evaluation file is readable."""
    source, camp = _source_for(entry, content)
    result = parser.parse(content, source, source_path=f"eval/{entry.sha256}.docx", camp=camp)
    if not isinstance(result, ParsedDocument):
        raise EvaluationSetupError(f"{entry.sha256[:12]}…: the parser refused the file ({result.reason})")
    return result


def load_evaluation_document(
    entry: ManifestEntry, path_map: Mapping[str, Path], parser: DebateDocxParser | None = None
) -> ParsedDocument:
    """Read one evaluation file from where the path map says it is, check its bytes, and parse it."""
    path = path_map.get(entry.sha256)
    if path is None or not path.is_file():
        raise EvaluationSetupError(f"{entry.sha256[:12]}…: not found on this machine (see the path map)")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != entry.sha256:
        raise EvaluationSetupError(f"{entry.sha256[:12]}…: the file at its mapped path has changed")
    return parse_evaluation_file(parser if parser is not None else DebateDocxParser(), entry, content)


def run_evaluation(
    *,
    tier: str,
    manifest: Manifest,
    labels: Mapping[str, LabelFile],
    path_map: Mapping[str, Path],
    baseline: Mapping[str, Any],
    parser: DebateDocxParser | None = None,
) -> dict[str, Any]:
    """Parse, check and score every file in one tier, and return the report.

    Raises :class:`EvaluationSetupError` listing every problem at once — a missing label file, a
    pre-label nobody corrected, a file that is not where the path map says, or a file that has
    changed under its labels — rather than scoring what it could and reporting a number that
    silently covers less than it claims to.
    """
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIERS}")
    parser = parser if parser is not None else DebateDocxParser()
    entries = manifest.pr_subset if tier == "pr-subset" else manifest.entries
    if not entries:
        raise EvaluationSetupError(f"the manifest has no files in the {tier} tier")

    problems: list[str] = []
    scored: list[tuple[ManifestEntry, FileScore]] = []
    per_file: dict[str, FileScore] = {}
    for entry in entries:
        short = f"{entry.sha256[:12]}…"
        label_file = labels.get(entry.sha256)
        if label_file is None:
            problems.append(f"{short}: no label file")
            continue
        if label_file.header.status is LabelStatus.PRELABELED:
            problems.append(f"{short}: labels are uncorrected pre-labels; the parser cannot grade itself")
            continue
        problems += [f"{short}: {problem}" for problem in validate_label_file(label_file, manifest)]
        path = path_map.get(entry.sha256)
        if path is None or not path.is_file():
            problems.append(f"{short}: not found on this machine (see the path map)")
            continue
        content = path.read_bytes()
        document = parse_evaluation_file(parser, entry, content)
        mismatches = validate_against_texts(
            label_file, hashlib.sha256(content).hexdigest(), [section.text for section in document.sections]
        )
        if mismatches:
            problems += [f"{short}: {problem}" for problem in mismatches]
            continue
        score = score_file(label_file, prediction_from_document(document))
        scored.append((entry, score))
        per_file[entry.sha256] = score
    if problems:
        raise EvaluationSetupError("the evaluation cannot run:\n  " + "\n  ".join(problems))

    groups = group_scores(scored)
    failures, notes = check_against_baseline(groups, baseline, tier=tier, parser_version=DOCX_PARSER_VERSION)
    return report_json(
        tier=tier,
        parser_version=DOCX_PARSER_VERSION,
        profile_version=parser.profile.profile_version,
        groups=groups,
        per_file=per_file,
        gate_failures=failures,
        gate_notes=notes,
        label_status={
            status.value: count for status, count in status_counts(labels[e.sha256] for e in entries).items()
        },
    )
