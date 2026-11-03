"""Whole test files dealt to ci.yml's `test` parts by the durations dev's push run recorded
(v1-e41-t17): `scripts/ci_test_durations.py`, `scripts/ci_test_selection.py`'s `files_to_parts`
output, and run_in_parts.py's `--files-to-parts` and `--record-durations`.

Until v1-e41-t17 every file's tests were dealt round all the parts, so each part built a file's
module-scoped fixtures again. Now `test-selection` deals whole files, heaviest first onto the
lightest part, by the seconds each file took on dev's last push run, and hands every part the same
deal. Each of the PM's mutants is checked by what it does:

* **Tests dealt rather than files:** every file in the deal has all its tests in its one part, by a
  real collection of an invented suite.
* **A file in two parts:** the deal names each file once, in one part of 1 to N, at every size, and
  every test of a collection is in exactly one part.
* **A missing record failing the run:** a missing, unreadable or stale record is a reason for the
  old dealing, written in the job summary, and the script still exits 0 with every output.
* **The fallback not reported:** each reason is read back out of the summary.

The expected deals are worked out by hand from the invented durations (working agreement 6). The
workflow's side, that only `test-selection` restores the record and the parts read the deal it
made, is tests/scripts/test_ci_workflow_durations_recorded_and_restored.py; the proof that the
real suite's parts are a partition under both dealings is tests/scripts/test_ci_workflow_test_job.py.
Nothing here uses the network.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from tests.scripts.test_ci_workflow_test_selection import BASE, pull_request, run

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci_test_durations.py"
PLUGINS = REPO_ROOT / "tests" / "pytest_plugins"
NOW = datetime(2026, 11, 2, 20, 0, tzinfo=UTC)
COMMIT = "4c1fc6e0123456789abcdef0123456789abcdef0"


def the_script() -> Any:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import ci_test_durations

    return ci_test_durations


def the_plugin() -> Any:
    return importlib.import_module("run_in_parts")


def write_record(
    path: Path, files: dict[str, Any], *, recorded_at: datetime = NOW - timedelta(hours=3), **more: Any
) -> Path:
    record = {"format": 1, "recorded_at": recorded_at.isoformat(), "commit": COMMIT, "files": files, **more}
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def dealt(tmp_path: Path, files: list[str], parts: int, record: dict[str, Any] | None, **written: Any) -> Any:
    path = tmp_path / "test-durations.json"
    if record is not None:
        write_record(path, record, **written)
    return the_script().deal(files, parts, path, NOW)


# --------------------------------------------------------------------------------------------
# the deal: whole files, heaviest first onto the lightest part
# --------------------------------------------------------------------------------------------

SEVEN_FILES = {"a.py": 50, "b.py": 40, "c.py": 30, "d.py": 20, "e.py": 20, "f.py": 10, "g.py": 5}


def test_whole_files_go_heaviest_first_onto_the_part_that_holds_least(tmp_path: Path) -> None:
    """By hand: a, b and c open the three parts; d joins c (30), e joins b (40), f the first of the
    two parts at 50 (part 1), and g the lighter part 3."""
    deal = dealt(tmp_path, sorted(SEVEN_FILES), 3, SEVEN_FILES)

    assert deal.by_durations, deal.why
    assert deal.part_of_file == {"a.py": 1, "b.py": 2, "c.py": 3, "d.py": 3, "e.py": 2, "f.py": 1, "g.py": 3}
    assert deal.loads == (60.0, 60.0, 55.0)
    assert deal.spread == ()


def test_a_file_heavier_than_a_parts_share_is_dealt_test_by_test(tmp_path: Path) -> None:
    """No deal of whole files can make h's part lighter than h, 100 s of 160 s over three parts
    (53.3 s each). So h is left out of the deal, the plugin spreads its tests round every part as
    before, and a third of it is counted in each part before the rest are dealt."""
    files = {"h.py": 100, "i.py": 30, "j.py": 20, "k.py": 10}
    deal = dealt(tmp_path, sorted(files), 3, files)

    assert deal.part_of_file == {"i.py": 1, "j.py": 2, "k.py": 3}
    assert deal.spread == ("h.py",)
    assert [round(load, 2) for load in deal.loads] == [63.33, 53.33, 43.33]


def test_a_file_with_no_record_counts_as_the_median_of_the_record(tmp_path: Path) -> None:
    """The record's median, over every file it names: 10, 20, 60 and 1000 give 40 for new.py. (The
    median of the chosen files alone, 20, would put new.py and a.py both beside b.py in part 2.)"""
    record = {"a.py": 10, "b.py": 20, "c.py": 60, "elsewhere.py": 1000}
    deal = dealt(tmp_path, ["a.py", "b.py", "c.py", "new.py"], 2, record)

    assert deal.by_durations, deal.why
    assert deal.default == 40.0
    assert deal.unrecorded == 1
    assert deal.part_of_file == {"c.py": 1, "new.py": 2, "b.py": 2, "a.py": 1}
    assert deal.loads == (70.0, 60.0)


def test_files_the_record_names_and_the_selection_does_not_are_left_out(tmp_path: Path) -> None:
    deal = dealt(tmp_path, ["a.py", "b.py", "c.py"], 2, {"a.py": 3, "b.py": 2, "c.py": 2, "gone.py": 500})

    assert deal.part_of_file == {"a.py": 1, "b.py": 2, "c.py": 2}


@pytest.mark.parametrize("parts", range(1, 9))
def test_every_file_is_in_exactly_one_part_at_every_size(tmp_path: Path, parts: int) -> None:
    """The PM's mutant, a file in two parts: a long tail and a few heavy files, as the costs page
    measured, and some files with no record."""
    files = [f"tests/area_{number % 7}/test_{number}.py" for number in range(120)]
    record = {name: (300.0 if number < 3 else 0.5 + number % 13) for number, name in enumerate(files[:100])}
    deal = dealt(tmp_path, files, parts, record)

    assert deal.by_durations, deal.why
    assert set(deal.part_of_file) | set(deal.spread) == set(files)
    assert not set(deal.part_of_file) & set(deal.spread)
    assert set(deal.part_of_file.values()) == set(range(1, parts + 1))
    assert len(deal.loads) == parts
    # The JSON every part reads names each file once, in a part of 1 to N.
    handed = json.loads(the_script().as_output(deal))
    assert handed == {"parts": parts, "part_of_file": deal.part_of_file}


# --------------------------------------------------------------------------------------------
# missing, unreadable or stale: the old dealing, and the summary says why
# --------------------------------------------------------------------------------------------

THREE_FILES = {"a.py": 3.0, "b.py": 2.0, "c.py": 1.0}


@pytest.mark.parametrize(
    ("written", "reason"),
    [
        (None, "no durations record was restored"),
        ("{not json", "could not be read"),
        ('{"format": 2, "files": {}}', "not a format 1 record"),
        ("[]", "not a format 1 record"),
        ({"files": {}}, "names no test file"),
        ({"files": {"a.py": -1}}, "gives 'a.py' -1 seconds"),
        ({"files": {"a.py": True}}, "gives 'a.py' True seconds"),
        ({"files": {"a.py": "3"}}, "gives 'a.py' '3' seconds"),
        (
            '{"format": 1, "recorded_at": "2026-11-02T10:00:00+00:00", "commit": "x", '
            '"files": {"a.py": NaN}}',
            "gives 'a.py' nan seconds",
        ),
        ({"files": THREE_FILES, "recorded_at": "yesterday"}, "says no time it was recorded"),
        ({"files": THREE_FILES, "recorded_at": "2026-11-02T10:00:00"}, "says no time it was recorded"),
        ({"files": THREE_FILES, "commit": 7}, "names no commit"),
    ],  # fmt: skip
    ids=[
        "missing",
        "not-json",
        "another-format",
        "not-an-object",
        "no-files",
        "negative",
        "a-bool",
        "a-string",
        "not-a-number",
        "no-time",
        "no-timezone",
        "no-commit",
    ],  # fmt: skip
)
def test_a_missing_or_unreadable_record_deals_test_by_test_and_says_why(
    tmp_path: Path, written: str | dict[str, Any] | None, reason: str
) -> None:
    path = tmp_path / "test-durations.json"
    if isinstance(written, str):
        path.write_text(written, encoding="utf-8")
    elif written is not None:
        record = {"format": 1, "recorded_at": NOW.isoformat(), "commit": COMMIT, **written}
        path.write_text(json.dumps(record), encoding="utf-8")
    script = the_script()

    deal = script.deal(sorted(THREE_FILES), 2, path, NOW)

    assert not deal.by_durations
    assert deal.part_of_file == {}
    assert reason in deal.why
    assert script.as_output(deal) == ""
    summary = script.summary(deal)
    assert "dealt test by test" in summary
    assert reason in summary


def test_a_record_fourteen_days_old_is_dealt_by_and_one_a_minute_older_is_stale(tmp_path: Path) -> None:
    fresh = dealt(tmp_path, sorted(THREE_FILES), 2, THREE_FILES, recorded_at=NOW - timedelta(days=14))
    stale = dealt(
        tmp_path, sorted(THREE_FILES), 2, THREE_FILES, recorded_at=NOW - timedelta(days=14, minutes=1)
    )

    assert fresh.by_durations, fresh.why
    assert not stale.by_durations
    assert "14 days old, older than the 14 days" in stale.why


def test_a_quarter_of_the_files_unrecorded_is_dealt_by_and_more_is_stale(tmp_path: Path) -> None:
    files = [f"test_{number}.py" for number in range(20)]
    recorded = {name: 1.0 + number for number, name in enumerate(files)}
    a_quarter = dealt(tmp_path, files, 2, {name: recorded[name] for name in files[5:]})
    more = dealt(tmp_path, files, 2, {name: recorded[name] for name in files[6:]})

    assert a_quarter.by_durations, a_quarter.why
    assert a_quarter.unrecorded == 5
    assert not more.by_durations
    assert "6 of the 20 test files chosen have no recorded duration, more than a quarter" in more.why


def test_a_part_left_with_no_recorded_file_deals_test_by_test(tmp_path: Path) -> None:
    """Files that all took no time pile into part 1, and a part of nothing would collect no test,
    which fails pytest."""
    deal = dealt(tmp_path, ["a.py", "b.py"], 2, {"a.py": 0, "b.py": 0})

    assert not deal.by_durations
    assert "a part would hold no test file with a recorded duration" in deal.why


def test_files_all_heavier_than_a_parts_share_are_dealt_test_by_test(tmp_path: Path) -> None:
    """One file in two parts is heavier than either's share, so nothing is left to deal whole."""
    deal = dealt(tmp_path, ["a.py"], 2, {"a.py": 4})

    assert not deal.by_durations
    assert "every test file chosen is heavier than a part's share" in deal.why


def test_the_summary_of_a_deal_by_durations_says_where_the_record_came_from(tmp_path: Path) -> None:
    files = {"h.py": 100, "i.py": 30, "j.py": 20}
    deal = dealt(tmp_path, ["h.py", "i.py", "j.py", "new.py"], 3, {**files, "k.py": 10})
    summary = the_script().summary(deal)

    assert "whole test files" in summary
    assert COMMIT[:12] in summary
    assert "2026-11-02 17:00 UTC" in summary
    assert "1 of the 4 test files chosen has no record" in summary
    assert "median, 25.0 s" in summary
    assert "`h.py`" in summary
    assert "heavier than a part's share" in summary
    assert "dealt test by test" not in summary


# --------------------------------------------------------------------------------------------
# combine: the push run's parts added up into one record
# --------------------------------------------------------------------------------------------


def combine(tmp_path: Path, parts: dict[str, Any]) -> tuple[subprocess.CompletedProcess[str], Path]:
    made = tmp_path / "parts"
    made.mkdir()
    paths = []
    for name, content in parts.items():
        path = made / name
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        paths.append(str(path))
    out = tmp_path / "record" / "test-durations.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "combine", "--commit", COMMIT, "--out", str(out), *paths],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return completed, out


def test_combine_adds_every_parts_seconds_per_file_into_a_record_the_deal_reads(tmp_path: Path) -> None:
    """Under the old dealing a file's tests are in every part, so its seconds are added up."""
    before = datetime.now(UTC)
    completed, out = combine(
        tmp_path,
        {
            "test-durations-part-1-of-2.json": {"x.py": 1.5, "y.py": 2},
            "test-durations-part-2-of-2.json": {"x.py": 0.25, "z.py": 3},
        },
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    record = json.loads(out.read_text(encoding="utf-8"))
    assert record["format"] == 1
    assert record["commit"] == COMMIT
    assert record["files"] == {"x.py": 1.75, "y.py": 2.0, "z.py": 3.0}
    assert before - timedelta(seconds=1) <= datetime.fromisoformat(record["recorded_at"]) <= datetime.now(UTC)
    read = the_script().read_record(out)
    assert read.files == {"x.py": 1.75, "y.py": 2.0, "z.py": 3.0}


@pytest.mark.parametrize(
    ("parts", "named"),
    [
        (
            {"test-durations-part-1-of-3.json": {"x.py": 1}, "test-durations-part-3-of-3.json": {"y.py": 1}},
            "missing: 2",
        ),
        (
            {"test-durations-part-1-of-2.json": {"x.py": 1}, "test-durations-part-2-of-3.json": {"y.py": 1}},
            "of different matrices",
        ),
        ({"test-durations-part-1-of-1.json": "{not json"}, "test-durations-part-1-of-1.json"),
        ({"test-durations-part-1-of-1.json": {"x.py": -2}}, "test-durations-part-1-of-1.json"),
        ({"test-durations-part-1-of-1.json": {}}, "no part timed a test"),
        ({"durations.json": {"x.py": 1}}, "durations.json"),
    ],  # fmt: skip
    ids=["a-part-missing", "another-matrix", "not-json", "negative", "nothing-timed", "no-part-in-the-name"],
)
def test_combine_writes_no_record_unless_every_part_timed_its_tests(
    tmp_path: Path, parts: dict[str, Any], named: str
) -> None:
    """A part missing would leave its files to the median; the record before it stays instead."""
    completed, out = combine(tmp_path, parts)

    assert completed.returncode != 0
    assert named in completed.stderr
    assert not out.exists()


# --------------------------------------------------------------------------------------------
# scripts/ci_test_selection.py: the deal in its outputs and its summary
# --------------------------------------------------------------------------------------------

MANY = {f"tests/many/test_file_{number}.py": "def test_it():\n    pass\n" for number in range(64)}
A_REPOSITORY_OF_MANY_FILES = {**BASE, **MANY}
EVERY_FILE_OF_IT = sorted(
    path for path in A_REPOSITORY_OF_MANY_FILES if path.rpartition("/")[2].startswith("test_")
)


def a_push(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    pull_request(root, {"docs/process/notes.md": "# Notes, changed\n"}, A_REPOSITORY_OF_MANY_FILES)
    return root


def test_the_whole_selection_is_dealt_by_durations_every_test_file_once(tmp_path: Path) -> None:
    root = a_push(tmp_path)
    record = write_record(
        tmp_path / "record.json",
        {path: 1.0 + number for number, path in enumerate(EVERY_FILE_OF_IT)},
        recorded_at=datetime.now(UTC) - timedelta(days=1),
    )

    ran = run(root, tmp_path, event="push", ref_name="dev", durations=record)

    assert ran.parts == list(range(1, 9))
    handed = json.loads(ran.files_to_parts)
    assert handed["parts"] == 8
    assert sorted(handed["part_of_file"]) == EVERY_FILE_OF_IT
    assert set(handed["part_of_file"].values()) == set(range(1, 9))
    assert "whole test files" in ran.summary
    assert COMMIT[:12] in ran.summary


@pytest.mark.parametrize("record", ["missing", "stale"])
def test_a_missing_or_stale_record_still_runs_every_part_dealt_test_by_test(
    tmp_path: Path, record: str
) -> None:
    """The PM's mutant: a pull request's run failing because the durations are missing."""
    root = a_push(tmp_path)
    path = tmp_path / "record.json"
    if record == "stale":
        write_record(
            path, dict.fromkeys(EVERY_FILE_OF_IT, 1.0), recorded_at=datetime.now(UTC) - timedelta(days=30)
        )

    ran = run(root, tmp_path, event="push", ref_name="dev", durations=path)

    assert ran.run_parts == "true"
    assert ran.parts == list(range(1, 9))
    assert ran.files_to_parts == ""
    assert "dealt test by test" in ran.summary
    assert ("no durations record was restored" if record == "missing" else "30 days old") in ran.summary


def test_no_test_part_means_no_deal(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    base_sha = pull_request(root, {"ROADMAP.md": "# Roadmap, regenerated\n"})
    record = write_record(tmp_path / "record.json", dict.fromkeys(EVERY_FILE_OF_IT, 1.0))

    ran = run(root, tmp_path, base_sha=base_sha, durations=record)

    assert ran.run_parts == "false"
    assert ran.files_to_parts == ""


# --------------------------------------------------------------------------------------------
# run_in_parts.py: the deal followed in a real collection, and the durations recorded
# --------------------------------------------------------------------------------------------

INVENTED_SUITE = {
    "test_alpha.py": "".join(f"def test_alpha_{number}():\n    pass\n\n\n" for number in range(4)),
    "test_beta.py": "".join(f"def test_beta_{number}():\n    pass\n\n\n" for number in range(3)),
    "test_gamma.py": "".join(f"def test_gamma_{number}():\n    pass\n\n\n" for number in range(5)),
}


def an_invented_suite(tmp_path: Path, files: dict[str, str] = INVENTED_SUITE) -> Path:
    root = tmp_path / "suite"
    root.mkdir()
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def run_pytest_in(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """pytest over the invented suite with this repository's plugin, and nothing this run set."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("PYTEST_", "COV_CORE_", "COVERAGE_"))
    }
    environment["PYTHONPATH"] = str(PLUGINS)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            str(root / "pytest.ini"),
            "--rootdir",
            str(root),
            "-p",
            "run_in_parts",
            "-p",
            "no:cacheprovider",
            "--color=no",
            *arguments,
        ],  # fmt: skip
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def collected_in_part(root: Path, part: int, parts: int, deal: Path) -> list[str]:
    completed = run_pytest_in(
        root, "--collect-only", "-q", "--part", f"{part}/{parts}", "--files-to-parts", str(deal)
    )
    assert completed.returncode in (0, 5), completed.stdout + completed.stderr
    return [line for line in completed.stdout.splitlines() if "::" in line]


def held(parts: list[list[str]], test_file: str) -> list[int]:
    return [sum(node_id.startswith(f"{test_file}::") for node_id in part) for part in parts]


def test_a_part_collects_whole_files_as_the_deal_says_and_the_rest_test_by_test(tmp_path: Path) -> None:
    """The PM's mutant, tests dealt rather than files: alpha's four tests are all in part 3, beta's
    three in part 1; gamma is in no deal, so its five go round the parts as before."""
    root = an_invented_suite(tmp_path)
    deal = tmp_path / "files-to-parts.json"
    deal.write_text(json.dumps({"parts": 3, "part_of_file": {"test_alpha.py": 3, "test_beta.py": 1}}))

    parts = [collected_in_part(root, part, 3, deal) for part in (1, 2, 3)]

    assert held(parts, "test_alpha.py") == [0, 0, 4]
    assert held(parts, "test_beta.py") == [3, 0, 0]
    assert sorted(held(parts, "test_gamma.py")) == [1, 2, 2]
    every = [node_id for part in parts for node_id in part]
    assert len(every) == len(set(every)) == 12


def test_an_empty_deal_deals_every_file_test_by_test(tmp_path: Path) -> None:
    root = an_invented_suite(tmp_path)
    deal = tmp_path / "files-to-parts.json"
    deal.write_text("")

    parts = [collected_in_part(root, part, 3, deal) for part in (1, 2, 3)]

    assert sorted(held(parts, "test_alpha.py")) == [1, 1, 2]
    assert sorted(held(parts, "test_beta.py")) == [1, 1, 1]
    assert sorted(held(parts, "test_gamma.py")) == [1, 2, 2]
    plugin = the_plugin()
    unsplit = [node_id for part in parts for node_id in part]
    assert plugin.parts_dealt(sorted(unsplit), 3, {}) == plugin.parts_dealt(sorted(unsplit), 3)


@pytest.mark.parametrize(
    ("deal", "named"),
    [
        ("{not json", "not JSON"),
        ('{"parts": 4, "part_of_file": {"test_alpha.py": 1}}', "into 3 parts"),
        ('{"parts": 3, "part_of_file": {"test_alpha.py": 0}}', "into 3 parts"),
        ('{"parts": 3, "part_of_file": {"test_alpha.py": 4}}', "into 3 parts"),
        ('{"parts": 3, "part_of_file": {"test_alpha.py": true}}', "into 3 parts"),
        ('{"parts": 3}', "into 3 parts"),
    ],
    ids=["not-json", "another-size", "part-zero", "part-past-the-last", "a-bool", "no-files"],
)
def test_a_deal_that_is_not_one_of_these_parts_is_refused(tmp_path: Path, deal: str, named: str) -> None:
    """test-selection writes the deal; one that cannot be followed is a fault there, not a reason to
    collect some other split."""
    root = an_invented_suite(tmp_path)
    path = tmp_path / "files-to-parts.json"
    path.write_text(deal)

    completed = run_pytest_in(root, "--collect-only", "-q", "--part", "1/3", "--files-to-parts", str(path))

    assert completed.returncode == 4, completed.stdout + completed.stderr
    assert named in completed.stderr


A_SLOW_FILE = """import time

import pytest


@pytest.fixture(scope="module")
def built():
    time.sleep(0.3)


def test_one(built):
    time.sleep(0.05)


def test_two(built):
    time.sleep(0.05)
"""
A_QUICK_FILE = "def test_one():\n    pass\n\n\ndef test_two():\n    pass\n"


@pytest.mark.parametrize("workers", ["0", "2"])
def test_a_part_records_each_files_setup_call_and_teardown_seconds(tmp_path: Path, workers: str) -> None:
    """Summed per file on the controller, which xdist's workers report to."""
    root = an_invented_suite(tmp_path, {"test_slow.py": A_SLOW_FILE, "test_quick.py": A_QUICK_FILE})
    record = tmp_path / "test-durations-part-1-of-1.json"

    completed = run_pytest_in(root, "-q", "-n", workers, "--part", "1/1", "--record-durations", str(record))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    seconds = json.loads(record.read_text(encoding="utf-8"))
    assert sorted(seconds) == ["test_quick.py", "test_slow.py"]
    assert seconds["test_slow.py"] >= 0.4
    assert seconds["test_quick.py"] < 0.3


def test_a_part_records_only_the_files_it_ran(tmp_path: Path) -> None:
    root = an_invented_suite(tmp_path, {"test_slow.py": A_SLOW_FILE, "test_quick.py": A_QUICK_FILE})
    deal = tmp_path / "files-to-parts.json"
    deal.write_text(json.dumps({"parts": 2, "part_of_file": {"test_slow.py": 2, "test_quick.py": 1}}))
    record = tmp_path / "test-durations-part-1-of-2.json"

    completed = run_pytest_in(
        root, "-q", "--part", "1/2", "--files-to-parts", str(deal), "--record-durations", str(record)
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert sorted(json.loads(record.read_text(encoding="utf-8"))) == ["test_quick.py"]


def test_a_record_that_cannot_be_written_does_not_fail_the_part(tmp_path: Path) -> None:
    root = an_invented_suite(tmp_path, {"test_quick.py": A_QUICK_FILE})
    nowhere = tmp_path / "no-such-directory" / "test-durations.json"

    completed = run_pytest_in(root, "-q", "--record-durations", str(nowhere))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "2 passed" in completed.stdout
    assert f"could not record the test durations in {nowhere}" in completed.stderr


def test_the_deal_and_the_old_dealing_agree_on_files_in_no_deal() -> None:
    """A file the deal does not name is dealt exactly as before, so a deal of no files is the old
    dealing, and a part's tests of such a file are level with every other part's."""
    plugin = the_plugin()
    node_ids = [f"t_{file}.py::test_{test}" for file in range(5) for test in range(7)]

    with_a_deal = plugin.parts_dealt(node_ids, 4, {"t_0.py": 2})
    without = plugin.parts_dealt(node_ids, 4)

    assert with_a_deal[:7] == [1] * 7
    assert with_a_deal[7:] == without[7:]
    assert Counter(without[:7]) != Counter({1: 7})
