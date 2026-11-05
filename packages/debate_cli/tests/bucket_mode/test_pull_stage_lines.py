"""The weekly run's log as the cloud task writes it: a line per step, and its result last (`v1-e40-t43`).

`debate-research --json caselist pull`, through the real command, composition root and bucket-mode
bracket, over moto and the fictional site (`conftest.py`). Each test pulls week three in bucket mode,
as the cloud task does, after the Mac pulled weeks one and two and seeded the bucket.

* Each step's start and end line comes in order: the restore, every stage, the bundle's saves and the
  state files' save. The parse's progress lines fall between its start and its end.
* The end lines' seconds, counts and memory figures, and their agreement with the result.
* No line holds a school, a team, a tournament, a file name, the caselist or a path.
* **The `RunsRecorded` metric filter** (`infrastructure/modules/caselist_run/alerts.tf`,
  `runs_recorded`) still counts exactly one line of a run, its result, and that line keeps its
  form. The filter's pattern is read out of the Terraform and evaluated here by
  :func:`runs_recorded`, a reader of CloudWatch's JSON filter syntax that refuses any part of a
  pattern it does not know, so a changed filter fails these tests instead of being misread.

No AWS call, no network: moto and respx.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

import pytest
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS
from typer.testing import Result

from debate_cli.exit_codes import ExitCode

World = Any
"""`conftest.py`'s world, which a test module cannot import by name."""

WEEK_1, WEEK_2, WEEK_3 = (week.snapshot for week in WEEKS)
FILE_HOST: Final = "https://files.opencaselist.example.invalid"
REPO_ROOT: Final = Path(__file__).resolve().parents[4]
ALERTS: Final = REPO_ROOT / "infrastructure" / "modules" / "caselist_run" / "alerts.tf"


# ------------------------------------------------------------------------------------------------
# The RunsRecorded filter, read out of the Terraform
# ------------------------------------------------------------------------------------------------


def runs_recorded_pattern() -> str:
    """The `runs_recorded` metric filter's pattern, as Terraform hands it to CloudWatch."""
    text = ALERTS.read_text(encoding="utf-8")
    block = text[text.index('resource "aws_cloudwatch_log_metric_filter" "runs_recorded"') :]
    block = block[: block.index("\n}\n")]
    [quoted] = re.findall(r'^\s*pattern\s*=\s*"((?:[^"\\]|\\.)*)"\s*$', block, re.MULTILINE)
    assert "${" not in quoted, "an interpolated pattern is not one this reader can evaluate"
    return re.sub(r"\\(.)", r"\1", quoted)


class UnreadablePattern(AssertionError):
    """A part of the filter's pattern this reader does not know: read the filter again by hand."""


_TOKEN: Final = re.compile(r'\s*(\{|\}|\(|\)|&&|\|\||!=|=|"(?:[^"\\]|\\.)*"|\$(?:\.[A-Za-z_][A-Za-z0-9_]*)+)')


def _tokens(pattern: str) -> list[str]:
    tokens: list[str] = []
    at = 0
    while at < len(pattern.rstrip()):
        found = _TOKEN.match(pattern, at)
        if found is None:
            raise UnreadablePattern(f"cannot read the pattern from {pattern[at:]!r}")
        tokens.append(found.group(1))
        at = found.end()
    return tokens


Test = Callable[[object], bool]


def runs_recorded(pattern: str) -> Callable[[str], bool]:
    """Whether CloudWatch's JSON filter `pattern` matches one log event, the line as written.

    Only what this pattern uses: `{ … }` around `&&`, `||` and parentheses, and `$.a.b = "text"` or
    `!=`, where `*` in the text stands for any characters. Mixing `&&` and `||` without parentheses
    is refused rather than given a precedence. A selector that names nothing, or a value that is not a
    string, does not equal a string.
    """
    tokens = _tokens(pattern)
    if tokens[:1] != ["{"] or tokens[-1:] != ["}"]:
        raise UnreadablePattern("a JSON filter pattern is wrapped in { }")
    position = 1

    def take(expected: str | None = None) -> str:
        nonlocal position
        token = tokens[position]
        if expected is not None and token != expected:
            raise UnreadablePattern(f"expected {expected!r}, read {token!r}")
        position += 1
        return token

    def expression() -> Test:
        first = term()
        operator = tokens[position]
        if operator not in {"&&", "||"}:
            return first
        terms = [first]
        while tokens[position] in {"&&", "||"}:
            if take() != operator:
                raise UnreadablePattern("&& and || mixed without parentheses")
            terms.append(term())
        if operator == "&&":
            return lambda event: all(one(event) for one in terms)
        return lambda event: any(one(event) for one in terms)

    def term() -> Test:
        if tokens[position] == "(":
            take("(")
            inner = expression()
            take(")")
            return inner
        selector = take()
        if not selector.startswith("$."):
            raise UnreadablePattern(f"expected a selector, read {selector!r}")
        operator = take()
        if operator not in {"=", "!="}:
            raise UnreadablePattern(f"expected = or !=, read {operator!r}")
        quoted = take()
        if not quoted.startswith('"'):
            raise UnreadablePattern(f"expected a quoted string, read {quoted!r}")
        wanted = re.compile(
            "".join(".*" if part == "*" else re.escape(part) for part in re.split(r"(\*)", quoted[1:-1])),
            re.DOTALL,
        )
        path = selector[2:].split(".")

        def equal(event: object) -> bool:
            value = event
            for name in path:
                if not isinstance(value, dict) or name not in value:
                    return False
                value = value[name]  # pyright: ignore[reportUnknownVariableType]
            return isinstance(value, str) and wanted.fullmatch(value) is not None

        return equal if operator == "=" else (lambda event: not equal(event))

    test = expression()
    take("}")
    if position != len(tokens):
        raise UnreadablePattern("text after the closing }")

    def matches(line: str) -> bool:
        try:
            event = json.loads(line)
        except ValueError:
            return False
        return isinstance(event, dict) and test(event)

    return matches


# ------------------------------------------------------------------------------------------------
# The run
# ------------------------------------------------------------------------------------------------


def the_week_the_cloud_run_finds(world: World) -> None:
    """Weeks one and two pulled on the Mac, the bucket seeded, a week passes, and week three is out."""
    world.listing(WEEK_1, WEEK_2)
    assert world.pull()["exit_code"] == ExitCode.OK
    world.seed()
    world.clock.advance(timedelta(days=7))
    world.listing(WEEK_1, WEEK_2, WEEK_3)


def pulled(world: World, *arguments: str) -> Result:
    return world.invoke("--json", "caselist", "pull", "--caselist", CASELIST, *arguments)


def step_lines(result: Result) -> list[dict[str, Any]]:
    """Every line on stderr, each of which must be a step line of `caselist pull`."""
    lines = [json.loads(line) for line in result.stderr.splitlines() if line.strip()]
    assert all(set(line) == {"schema_version", "command", "event", "data"} for line in lines), lines
    assert {line["command"] for line in lines} == {"caselist pull"}
    return lines


def events(lines: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(line["event"], line["data"]["step"]) for line in lines]


def start_and_end(*steps: str) -> list[tuple[str, str]]:
    return [pair for step in steps for pair in (("step_started", step), ("step_ended", step))]


def ended(lines: list[dict[str, Any]], step: str) -> list[dict[str, Any]]:
    return [line["data"] for line in lines if line["event"] == "step_ended" and line["data"]["step"] == step]


A_BUCKET_MODE_RUN: Final = [
    *start_and_end("restore", "select", "download", "import", "publish", "save_bundle"),
    ("step_started", "parse"),
    ("parse_progress", "parse"),
    ("parse_progress", "parse"),
    ("step_ended", "parse"),
    *start_and_end("search_index", "report", "retention", "save_bundle", "save_state_files"),
]
"""Week three's run: the restore, the stages in order (no landscape service is installed), the
bundle's save after the publish and after the run, and the state files' save at its end. The
parse's two progress lines are its one caselist's start (0 done of 1) and its end (1 done)."""


def test_each_step_of_a_bucket_mode_run_logs_its_start_and_its_end_in_order(world: World) -> None:
    the_week_the_cloud_run_finds(world)

    result = pulled(world)

    assert result.exit_code == ExitCode.OK, result.output
    lines = step_lines(result)
    assert events(lines) == A_BUCKET_MODE_RUN
    progress = [line["data"]["counts"] for line in lines if line["event"] == "parse_progress"]
    assert progress == [
        {"sources_done": 0, "sources_left": 1, "caselists_done": 0, "caselists_left": 1},
        {"sources_done": 1, "sources_left": 0, "caselists_done": 0, "caselists_left": 1},
    ], "week three adds one source, `direct`, to the one caselist"


def test_the_end_lines_carry_the_seconds_counts_and_memory_the_result_records(world: World) -> None:
    the_week_the_cloud_run_finds(world)
    world.clock.advance(timedelta(minutes=1))

    result = pulled(world)

    lines = step_lines(result)
    data = json.loads(result.stdout)["data"]
    times = {one["stage"]: one["duration_seconds"] for one in data["stage_times"]}
    for stage, seconds in times.items():
        for line in ended(lines, stage):
            assert line["seconds"] == round(seconds, 1), stage
    restored = data["run_details"]["bucket_run"]["restore"]
    [restore] = ended(lines, "restore")
    assert restore["counts"] == {
        "state_files": 6,
        "parsed_objects": restored["parsed_objects"],
        "parsed_bytes": restored["parsed_bytes"],
        "parsed_kept": restored["parsed_kept"],
    }, "the five state files and the parse-owed file, as the restore test counts them"
    [parse] = ended(lines, "parse")
    assert parse["counts"] == data["parse"]
    assert parse["counts"]["attempted"] == 1, "week three's one new source"
    assert parse["outcome"] == "completed"
    [download] = ended(lines, "download")
    assert download["counts"]["archives_downloaded"] == data["archives_downloaded"] == 1
    [publish] = ended(lines, "publish")
    assert publish["counts"]["objects_published"] == data["objects_published"]
    for line in lines:
        if line["event"] == "step_started":
            assert set(line["data"]) == {"step", "counts"} and line["data"]["counts"] == {}
        else:
            assert "main_process_peak_bytes" in line["data"]["memory"], line


def test_no_line_names_a_school_a_team_a_tournament_a_file_the_caselist_or_a_path(world: World) -> None:
    the_week_the_cloud_run_finds(world)

    result = pulled(world)

    said = result.stderr
    assert said.count("\n") == len(A_BUCKET_MODE_RUN)
    names = [*FICTIONAL_IDENTIFIERS, CASELIST, ".docx", ".zip", str(world.root), str(world.root.resolve())]
    assert [name for name in names if name.lower() in said.lower()] == []
    assert "/" not in said and "\\" not in said


def test_on_a_terminal_each_step_is_a_sentence_on_stderr(world: World) -> None:
    the_week_the_cloud_run_finds(world)

    result = world.invoke("caselist", "pull", "--caselist", CASELIST)

    assert result.exit_code == ExitCode.OK, result.output
    said = result.stderr.splitlines()
    assert said[:1] == ["caselist pull: restore step started"]
    assert any(
        line.startswith("caselist pull: parse step ended at 0.0 s (completed); caselists 1, ")
        for line in said
    )
    assert said[-1:] and said[-1].startswith("caselist pull: save_state_files step ended at ")


# ------------------------------------------------------------------------------------------------
# ac2: the result is still the one line RunsRecorded counts, and keeps its form
# ------------------------------------------------------------------------------------------------

RESULT_KEYS: Final = {"schema_version", "status", "command", "data", "error"}
SUMMARY_KEYS: Final = {
    "schema_version",
    "run_id",
    "started_at",
    "finished_at",
    "duration_seconds",
    "dry_run",
    "succeeded",
    "nothing_new",
    "caselists",
    "stages",
    "archives_seen",
    "archives_wanted",
    "archives_downloaded",
    "archives_deferred",
    "openev_seen",
    "openev_downloaded",
    "openev_skipped_as_removed",
    "files_imported",
    "files_duplicate",
    "files_skipped",
    "blobs_stored",
    "parse",
    "parsed_stores_owed",
    "search_index",
    "objects_published",
    "manifests_published",
    "reports_written",
    "snapshots_imported",
    "pending_publish",
    "bulk_downloads_allowed",
    "bulk_downloads_spent_in_window",
    "bulk_download_window_start",
    "suppression_list_local_copy_only",
    "inbox_retention",
    "full_archive",
    "full_archive_recounted",
    "held_by_request",
    "stage_times",
    "data_volume",
    "selections",
    "openev_selections",
    "environment",
    "bucket",
    "summary_written_to",
    "run_record",
    "run_details",
}
"""The result's `data` at this task's start commit (3d86209), written out from `RunSummary.as_json` and
`pull_summary`, neither of which this task changed."""


def counted(result: Result) -> list[str]:
    """Every line the run wrote, stdout and stderr in the order written, that RunsRecorded counts."""
    matches = runs_recorded(runs_recorded_pattern())
    return [line for line in result.output.splitlines() if matches(line)]


def test_the_filter_reader_counts_a_recorded_pull_and_nothing_else() -> None:
    """The reader against hand-written lines, so that a reader matching everything, or nothing, fails."""
    matches = runs_recorded(runs_recorded_pattern())
    ok = {"schema_version": 1, "status": "ok", "command": "caselist pull", "error": None}
    failed = {"schema_version": 1, "status": "error", "command": "caselist pull", "data": None}

    assert matches(json.dumps({**ok, "data": {"run_record": {"run_id": "20261111T090000Z"}}}))
    assert matches(
        json.dumps({**failed, "error": {"details": {"run_record": {"run_id": "20261111T090000Z"}}}})
    )
    assert not matches(json.dumps({**ok, "data": {"run_record": None}})), "a dry run records nothing"
    assert not matches(
        json.dumps({**ok, "command": "caselist backfile-import", "data": {"run_record": {"run_id": "x"}}})
    )
    assert not matches(json.dumps({**failed, "error": {"details": {"run_record": {"run_id": 7}}}}))
    assert not matches(
        json.dumps(
            {
                "schema_version": 1,
                "command": "caselist pull",
                "event": "step_ended",
                "data": {"step": "save_state_files", "seconds": 1.2, "counts": {}},
            }
        )
    )
    assert not matches("caselist pull: restore step started")
    with pytest.raises(UnreadablePattern):
        runs_recorded('{ $.command = "caselist pull" && $.a = "b" || $.c = "d" }')
    with pytest.raises(UnreadablePattern):
        runs_recorded("{ $.count > 3 }")


def test_a_runs_result_is_the_one_line_runs_recorded_counts_and_the_last_it_writes(world: World) -> None:
    the_week_the_cloud_run_finds(world)

    result = pulled(world)

    assert result.exit_code == ExitCode.OK, result.output
    assert len(step_lines(result)) == len(A_BUCKET_MODE_RUN)
    [result_line] = result.stdout.splitlines()
    assert counted(result) == [result_line]
    assert result.output.splitlines()[-1] == result_line, "every step line comes before the result"
    envelope = json.loads(result_line)
    assert set(envelope) == RESULT_KEYS
    assert set(envelope["data"]) == SUMMARY_KEYS
    assert envelope["status"] == "ok" and envelope["command"] == "caselist pull" and envelope["error"] is None
    assert envelope["data"]["run_record"]["run_id"] == envelope["data"]["run_id"]


def test_a_failed_runs_result_is_the_one_line_runs_recorded_counts(world: World) -> None:
    """Week three's archive gone from the file host: the download fails, and the run records it."""
    the_week_the_cloud_run_finds(world)
    world.site.get(f"{FILE_HOST}/{CASELIST}-weekly-{WEEK_3.isoformat()}.zip").respond(404)

    result = pulled(world)

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.output
    lines = step_lines(result)
    assert [line["outcome"] for line in ended(lines, "download")] == ["failed"]
    [result_line] = result.stdout.splitlines()
    assert counted(result) == [result_line]
    assert result.output.splitlines()[-1] == result_line
    envelope = json.loads(result_line)
    assert set(envelope) == RESULT_KEYS
    assert envelope["error"]["code"] == "CASELIST_PULL_INCOMPLETE"
    assert set(envelope["error"]["details"]) == SUMMARY_KEYS
    assert envelope["error"]["details"]["run_record"]["run_id"] == envelope["error"]["details"]["run_id"]


def test_a_dry_runs_lines_are_counted_by_nothing(world: World) -> None:
    """A dry run restores, selects and judges retention, and records nothing: no line is counted."""
    the_week_the_cloud_run_finds(world)

    result = pulled(world, "--dry-run")

    assert result.exit_code == ExitCode.OK, result.output
    assert events(step_lines(result)) == start_and_end("restore", "select", "retention")
    assert counted(result) == []
