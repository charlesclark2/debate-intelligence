"""Each of ci.yml's `test` parts collects only its own test files (v1-e41-t18).

Until v1-e41-t18 every part collected the whole selection and kept its share: about 8 s of collection
a part on the operator's Mac, and four times that in CPU, because each of a part's xdist workers
collects for itself (docs/process/ci-test-part-costs.md). Since v1-e41-t17 the deal names a part for
almost every file, so run_in_parts.py now never imports a file the deal gives another part, whether
pytest is handed the file by name (an affected set, as `@FILE`) or finds it walking a directory (the
whole selection's `testpaths`). Each case here is checked by what it does:

* **A part importing another part's file:** every module of the invented suite writes its name down
  when it is imported, and each part's imports are compared with the files the deal gives it.
* **A file the deal does not name lost:** it is imported by every part and dealt test by test.
* **A missing or empty deal:** every part imports every file, as before.
* **A test in no part, or in two:** the parts of an invented suite are collected for real at every
  size the rule gives, under the deal ci_test_durations.py makes for that size.

The expected imports and parts are worked out by hand from the deals written here (working agreement
6). The proof against the real suite is tests/scripts/test_ci_workflow_test_job.py's partition proof.
Nothing here uses the network.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from tests.scripts.test_parts_dealt_by_durations import REPO_ROOT, an_invented_suite, run_pytest_in

# Every module of the invented suite appends its own file name to the file this names when imported.
WRITES_DOWN_ITS_IMPORT = """import os
import pathlib

with open(os.environ["IMPORTS_WRITTEN_TO"], "a", encoding="utf-8") as imports:
    imports.write(pathlib.Path(__file__).name + "\\n")

"""


def a_module(tests: int, name: str) -> str:
    return WRITES_DOWN_ITS_IMPORT + "".join(
        f"\n\ndef test_{name}_{number}():\n    pass\n" for number in range(tests)
    )


# Three files into three parts: alpha whole in part 3, beta whole in part 1, gamma in no deal.
SUITE = {
    "test_alpha.py": a_module(4, "alpha"),
    "test_beta.py": a_module(3, "beta"),
    "test_gamma.py": a_module(5, "gamma"),
}
DEAL = {"parts": 3, "part_of_file": {"test_alpha.py": 3, "test_beta.py": 1}}
# By hand: a part imports its own files and gamma, which every part deals test by test.
IMPORTED_BY_PART = {
    1: ["test_beta.py", "test_gamma.py"],
    2: ["test_gamma.py"],
    3: ["test_alpha.py", "test_gamma.py"],
}


def the_plugin() -> Any:
    return importlib.import_module("run_in_parts")


def a_part(
    root: Path, tmp_path: Path, part: int, parts: int, deal: str | None, *arguments: str, workers: str = "0"
) -> tuple[list[str], list[str], str]:
    """Part `part` of `parts` under `deal` (None: no `--files-to-parts`): its node ids, the files its
    processes imported, and pytest's output. With no workers it is collected; with workers it is run,
    because xdist starts none for `--collect-only`, and its node ids are read from its PASSED lines."""
    imports = tmp_path / f"imports-{part}-of-{parts}-{workers}.txt"
    imports.write_text("", encoding="utf-8")
    dealing: list[str] = []
    if deal is not None:
        written = tmp_path / f"files-to-parts-{part}-of-{parts}.json"
        written.write_text(deal, encoding="utf-8")
        dealing = [f"--files-to-parts={written}"]
    how = ["--collect-only", "-q"] if workers == "0" else ["-v"]
    completed = run_pytest_in(
        root,
        *how,
        "-n",
        workers,
        "--part",
        f"{part}/{parts}",
        *dealing,
        *arguments,
        environment={"IMPORTS_WRITTEN_TO": str(imports)},
    )
    assert completed.returncode in (0, 5), completed.stdout + completed.stderr
    lines = completed.stdout.splitlines()
    if workers == "0":
        node_ids = [line for line in lines if "::" in line]
    else:
        assert f"created: {workers}/{workers} workers" in completed.stdout or not node_ids_in(lines), (
            completed.stdout
        )
        node_ids = node_ids_in(lines)
    return node_ids, sorted(set(imports.read_text(encoding="utf-8").split())), completed.stdout


def node_ids_in(lines: list[str]) -> list[str]:
    """The tests a run under xdist passed, from `-v`'s `[gw0] [ 50%] PASSED test_a.py::test_a_0`."""
    return sorted(line.split(" PASSED ")[1].split()[0] for line in lines if " PASSED " in line)


def held(node_ids: list[str], test_file: str) -> int:
    return sum(node_id.startswith(f"{test_file}::") for node_id in node_ids)


def named_in_a_file(root: Path, tmp_path: Path, names: list[str]) -> str:
    """The files given as CI gives an affected set: one a line, in a file read as `@FILE`."""
    listing = tmp_path / "test-selection.txt"
    listing.write_text("".join(f"{name}\n" for name in names), encoding="utf-8")
    return f"@{listing}"


@pytest.mark.parametrize("workers", ["0", "2"])
@pytest.mark.parametrize("given", ["walked", "named", "named-in-a-file", "node-ids"])
def test_a_part_imports_only_its_own_files_and_every_file_the_deal_does_not_name(
    tmp_path: Path, given: str, workers: str
) -> None:
    """The PM's case: a part importing another part's file. The whole selection reaches pytest as
    directories it walks; an affected set as files named in `@FILE`; a rerun as node ids."""
    root = an_invented_suite(tmp_path, SUITE)
    arguments = {
        "walked": [],
        "named": sorted(SUITE),
        "named-in-a-file": [named_in_a_file(root, tmp_path, sorted(SUITE))],
        "node-ids": ["test_alpha.py::test_alpha_0", "test_beta.py::test_beta_2", "test_gamma.py"],
    }[given]

    parts = [
        a_part(root, tmp_path, part, 3, json.dumps(DEAL), *arguments, workers=workers) for part in (1, 2, 3)
    ]

    for part, (_, imported, _) in enumerate(parts, start=1):
        assert imported == IMPORTED_BY_PART[part], f"part {part} of 3 imported {imported}"
    node_ids = [part[0] for part in parts]
    if given == "node-ids":
        assert [held(part, "test_alpha.py") for part in node_ids] == [0, 0, 1]
        assert [held(part, "test_beta.py") for part in node_ids] == [1, 0, 0]
    else:
        assert [held(part, "test_alpha.py") for part in node_ids] == [0, 0, 4]
        assert [held(part, "test_beta.py") for part in node_ids] == [3, 0, 0]
    assert sorted(held(part, "test_gamma.py") for part in node_ids) == [1, 2, 2]
    every = [node_id for part in node_ids for node_id in part]
    assert len(every) == len(set(every)) == (7 if given == "node-ids" else 12)


@pytest.mark.parametrize("deal", [None, ""], ids=["no-deal-given", "an-empty-deal"])
def test_with_no_deal_every_part_imports_every_file_as_before(tmp_path: Path, deal: str | None) -> None:
    """A record missing or stale hands the parts an empty deal; a local `--part K/N` gives none."""
    root = an_invented_suite(tmp_path, SUITE)

    parts = [a_part(root, tmp_path, part, 3, deal) for part in (1, 2, 3)]

    for _, imported, _ in parts:
        assert imported == sorted(SUITE)
    for test_file, tests in (("test_alpha.py", 4), ("test_beta.py", 3), ("test_gamma.py", 5)):
        counts = sorted(held(node_ids, test_file) for node_ids, _, _ in parts)
        assert sum(counts) == tests and counts[-1] - counts[0] <= 1, (test_file, counts)


def test_a_part_given_only_other_parts_files_imports_none_rather_than_everything(tmp_path: Path) -> None:
    """Every named file trimmed away leaves pytest no path: it must collect nothing, not the rootdir.
    The deal never leaves a part without a file of its own; this is the edge the trimming has."""
    root = an_invented_suite(tmp_path, SUITE)

    node_ids, imported, output = a_part(
        root, tmp_path, 2, 3, json.dumps(DEAL), "test_alpha.py", "test_beta.py"
    )

    assert node_ids == []
    assert imported == []
    assert "no tests collected" in output or "no tests ran" in output


def test_a_file_outside_the_rootdir_is_collected_and_dealt_test_by_test(tmp_path: Path) -> None:
    """No deal names a file outside the rootdir, so every part collects it, as any file in no deal."""
    root = an_invented_suite(tmp_path, SUITE)
    outside = tmp_path / "elsewhere" / "test_outside.py"
    outside.parent.mkdir()
    outside.write_text(a_module(3, "outside"), encoding="utf-8")

    parts = [a_part(root, tmp_path, part, 3, json.dumps(DEAL), str(outside)) for part in (1, 2, 3)]

    assert [imported for _, imported, _ in parts] == [["test_outside.py"]] * 3
    assert sorted(len(node_ids) for node_ids, _, _ in parts) == [1, 1, 1]


# Nine files of 1 to 9 tests, and seconds for eight of them: test_i.py is in no record and counts as
# the record's median (5.5 s). By hand: 70.5 s in all, so test_h.py's 30 s is heavier than a part's
# share from three parts on (23.5 s), and is dealt test by test there.
SIZED_SUITE = {
    f"test_{letter}.py": a_module(tests, letter)
    for tests, letter in zip(range(1, 10), "abcdefghi", strict=True)
}
SECONDS = {
    "test_a.py": 4,
    "test_b.py": 6,
    "test_c.py": 3,
    "test_d.py": 8,
    "test_e.py": 5,
    "test_f.py": 7,
    "test_g.py": 2,
    "test_h.py": 30,
}


def the_deal_at(tmp_path: Path, parts: int) -> Any:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    durations = importlib.import_module("ci_test_durations")
    record = tmp_path / "test-durations.json"
    record.write_text(
        json.dumps(
            {
                "format": 1,
                "recorded_at": datetime.now(UTC).isoformat(),
                "commit": "invented",
                "files": SECONDS,
            }
        ),
        encoding="utf-8",
    )
    return durations.deal(sorted(SIZED_SUITE), parts, record, datetime.now(UTC))


SIZES = list(range(1, 9))


def test_every_test_is_in_exactly_one_part_at_every_size_and_each_part_imports_only_its_own(
    tmp_path: Path,
) -> None:
    """Every part at every size from one to eight, collected for real under the deal ci_test_durations.py
    makes for that size, named in a file as CI names an affected set. 36 collections, side by side."""
    root = an_invented_suite(tmp_path, SIZED_SUITE)
    listing = named_in_a_file(root, tmp_path, sorted(SIZED_SUITE))
    deals = {parts: the_deal_at(tmp_path, parts) for parts in SIZES}
    # The deal is by durations at every size; from three parts on test_h.py is spread.
    assert all(deals[parts].by_durations for parts in SIZES), {parts: deals[parts].why for parts in SIZES}
    assert [parts for parts in SIZES if "test_h.py" in deals[parts].spread] == list(range(3, 9))
    commands = [(parts, part) for parts in SIZES for part in range(1, parts + 1)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        collected = dict(
            zip(
                commands,
                pool.map(
                    lambda command: a_part(
                        root,
                        tmp_path,
                        command[1],
                        command[0],
                        json.dumps({"parts": command[0], "part_of_file": deals[command[0]].part_of_file}),
                        listing,
                    ),
                    commands,
                ),
                strict=True,
            )
        )

    every_test = sorted(
        f"{name}::test_{name[5]}_{number}"
        for name, tests in zip(sorted(SIZED_SUITE), range(1, 10), strict=True)
        for number in range(tests)
    )
    for parts in SIZES:
        part_of_file = deals[parts].part_of_file
        in_parts = Counter(node_id for part in range(1, parts + 1) for node_id in collected[(parts, part)][0])
        assert sorted(in_parts) == every_test, f"{parts} parts: {sorted(set(every_test) ^ set(in_parts))}"
        assert set(in_parts.values()) == {1}, (
            f"{parts} parts: in two parts: {[n for n, c in in_parts.items() if c > 1]}"
        )
        for part in range(1, parts + 1):
            expected = sorted(name for name in SIZED_SUITE if part_of_file.get(name, part) == part)
            assert collected[(parts, part)][1] == expected, f"part {part} of {parts}"


def test_the_part_every_test_is_dealt_to_collects_its_file_at_every_size() -> None:
    """The rule the partition rests on: `parts_dealt` gives a test to exactly one part, and that part
    is one that collects the test's file, so trimming what a part collects loses no test."""
    plugin = the_plugin()
    node_ids = [f"t_{file}.py::test_{test}" for file in range(11) for test in range(file % 4 + 1)]
    for parts in SIZES:
        part_of_file = {f"t_{file}.py": file % parts + 1 for file in range(0, 11, 2)}
        for node_id, dealt_to in zip(
            node_ids, plugin.parts_dealt(node_ids, parts, part_of_file), strict=True
        ):
            test_file = node_id.partition("::")[0]
            collecting = [
                part for part in range(1, parts + 1) if plugin.collects(test_file, part, part_of_file)
            ]
            assert dealt_to + 1 in collecting, (node_id, parts, dealt_to + 1, collecting)
            assert collecting == (
                [part_of_file[test_file]] if test_file in part_of_file else list(range(1, parts + 1))
            )


@pytest.mark.parametrize("workers", ["0", "2"])
def test_a_part_says_how_long_it_took_to_collect(tmp_path: Path, workers: str) -> None:
    """A runner's log cannot time a part's collection: pytest's output to a pipe is buffered, so its
    timestamps are its flushes'. The part says it in its summary instead."""
    root = an_invented_suite(tmp_path, SUITE)

    _, _, output = a_part(root, tmp_path, 1, 3, json.dumps(DEAL), workers=workers)
    _, _, unsplit = a_part(root, tmp_path, 1, 1, None)

    workers_named = ", the last of 2 workers" if workers == "2" else ""
    lines = [line for line in output.splitlines() if line.startswith("part 1 of 3 collected in ")]
    assert len(lines) == 1, output
    [line] = lines
    assert line.endswith(f" s{workers_named} (tests/pytest_plugins/run_in_parts.py)"), line
    seconds = float(line.removeprefix("part 1 of 3 collected in ").partition(" s")[0])
    assert 0 <= seconds < 60
    assert "part 1 of 1 collected in " in unsplit
    # Without `--part` the plugin does nothing, and says nothing.
    plain = run_pytest_in(
        root, "--collect-only", "-q", environment={"IMPORTS_WRITTEN_TO": str(tmp_path / "x")}
    )
    assert "tests/pytest_plugins/run_in_parts.py" not in plain.stdout
