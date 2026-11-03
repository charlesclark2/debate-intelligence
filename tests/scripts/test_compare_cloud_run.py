"""Tests for `ops/caselist_run/compare_cloud_run.py`, the cutover's comparison (`v1-e40-t06`, ac1).

The script drives the installed build as a process, so here the build is a stand-in: a
`debate-research` that records each call and its environment, and answers as the real commands
answer. Its `caselist restore-run-state` copies a synthetic "cloud run's working copy" into the
scratch directory; its `caselist parse --reparse` copies a store's version directory into the next
generation, changed as a test asks; its `tub index build` writes the cloud's manifest back with the
re-parse's directories, changed as a test asks. Nothing here reaches a bucket or a network, and
every record is invented: no real caselist file, school or team is in it.

What is worth asserting, and why:

* the two sides agreeing is `AGREE`, exit 0, and a record of counts only;
* a source parsed differently on the Mac, or an index count that differs, is `DIFFER`, exit 1, and
  the record says where;
* a copy that is not the named run's, a restore the lock refused and a build that keeps its state
  locally each stop the comparison, exit 2, with nothing parsed and no record written;
* every command runs in an environment of HOME, PATH and DEBATE_ENV alone (working agreement 11),
  and none of them pulls or publishes.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "ops" / "caselist_run" / "compare_cloud_run.py"

RUN: Final = "20261029T110002Z"
VERSION: Final = "2026.10.20-docx-6"
INDEX_ID: Final = "0123456789abcdef"
STORES: Final = ("openev", "testcl26")
FICTIONAL_PATH: Final = "Fictional Prep/Fictional Prep AB Aff Estuaries.docx"
"""An invented disclosure path, in a manifest of the copy: what no record may ever repeat."""

FAKE_BUILD = '''#!@PYTHON@
"""A stand-in for the installed debate-research: records each call, answers as the real one does."""
import json, os, shutil, sys
from pathlib import Path

world = Path(@WORLD@)
control = json.loads((world / "control.json").read_text())
with open(world / "calls.jsonl", "a") as calls:
    calls.write(json.dumps({"argv": sys.argv[1:], "environment": dict(os.environ)}) + "\\n")
arguments = sys.argv[2:]
data_dir = Path(os.environ.get("DEBATE_STORAGE__DATA_DIR", "/nowhere"))


def ok(command, data):
    print(json.dumps({"schema_version": 1, "status": "ok", "command": command, "data": data, "error": None}))
    sys.exit(0)


def refused(command, code, message, details=None):
    print(json.dumps({"schema_version": 1, "status": "error", "command": command, "data": None,
                      "error": {"code": code, "message": message, "exit_code": 1, "details": details or {}}}))
    sys.exit(1)


if arguments == ["--version"]:
    ok("version", {"version": "1.1.0", "tag": "v1.1.0-dev.150"})
if arguments[:2] == ["config", "show"]:
    ok("config show", {"environment": "dev", "settings": {"caselist.run_state": control["run_state"],
                                                          "caselist.sync_caselists": ["testcl26"]},
                       "sources": {}})
if arguments[:2] == ["caselist", "restore-run-state"]:
    if control.get("restore_refused"):
        refused("caselist restore-run-state", control["restore_refused"], "another runner holds the lock")
    into = Path(arguments[arguments.index("--into") + 1])
    shutil.copytree(world / "cloud", into, dirs_exist_ok=True)
    ok("caselist restore-run-state", {"manifests": 2, "parsed_objects": 6, "parsed_version": "@VERSION@",
                                      "index_id": "@INDEX_ID@", "seconds": 12.5, "caselists": ["testcl26"]})
if arguments[:2] == ["caselist", "parse"]:
    store = arguments[arguments.index("--caselist") + 1]
    source = data_dir / "parsed" / store / "@VERSION@"
    target = data_dir / "parsed" / store / "@VERSION@_reparse-2"
    shutil.copytree(source, target)
    for name, lines in control.get("reparse", {}).get(store, {}).items():
        (target / name).write_text("".join(line + "\\n" for line in lines))
    ok("caselist parse", {"caselist": store, "version": "@VERSION@_reparse-2", "applied": True})
if arguments[:3] == ["tub", "index", "build"]:
    out = Path(arguments[arguments.index("--out") + 1])
    manifest = json.loads((world / "cloud" / "tub-index" / "@INDEX_ID@" / "manifest.json").read_text())
    for store in manifest["stores"]:
        store["version_directory"] = "@VERSION@_reparse-2"
    manifest["counts"].update(control.get("index_counts", {}))
    manifest["suppression"] = control.get("index_suppression", manifest["suppression"])
    manifest["index_id"] = "fedcba9876543210"
    (out / manifest["index_id"]).mkdir(parents=True)
    ok("tub index build", {"directory": str(out / manifest["index_id"]), "manifest": manifest})
refused(" ".join(arguments[:2]), "UNEXPECTED", "the stand-in was asked something it does not answer")
'''


def source(sha: str, outcome: str = "PARSED", cards: int = 2) -> str:
    return json.dumps(
        {
            "schema_version": 2,
            "record": "source",
            "caselist": "testcl26",
            "snapshot": "2026-10-28",
            "source_sha256": sha * 64,
            "parser_version": VERSION,
            "outcome": outcome,
            "reason": None if outcome == "PARSED" else "TIMEOUT",
            "cards": cards if outcome == "PARSED" else 0,
        },
        sort_keys=True,
    )


def occurrence(sha: str, element: int) -> str:
    return json.dumps(
        {
            "record": "occurrence",
            "source_sha256": sha * 64,
            "first_element_index": element,
            "cluster_id": sha * 64,
        },
        sort_keys=True,
    )


SOURCES: Final = {
    "testcl26": [source("a"), source("b", cards=3), source("c", outcome="UNSUPPORTED")],
    "openev": [source("d", cards=1)],
}
OCCURRENCES: Final = {
    "testcl26": [
        occurrence("a", 1),
        occurrence("a", 4),
        occurrence("b", 2),
        occurrence("b", 5),
        occurrence("b", 9),
    ],
    "openev": [occurrence("d", 1)],
}


def cloud_copy(root: Path) -> None:
    """The cloud run's working copy as the bucket would give it back: synthetic throughout."""
    (root / "objects" / "manifests" / "testcl26").mkdir(parents=True)
    (root / "objects" / "manifests" / "testcl26" / "2026-10-28.jsonl").write_text(
        json.dumps({"path": FICTIONAL_PATH, "sha256": "a" * 64}) + "\n", encoding="utf-8"
    )
    (root / "caselist-sync-runs.jsonl").write_text(
        json.dumps({"run_id": "20261021T110001Z", "outcome": "completed"})
        + "\n"
        + json.dumps(
            {
                "run_id": RUN,
                "outcome": "completed",
                "archives_downloaded": 1,
                "files_imported": 3,
                "objects_published": 4,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "caselist-sync-run-details.jsonl").write_text(
        json.dumps({"run_id": RUN, "parse": {"attempted": 3, "cards": 5}}) + "\n", encoding="utf-8"
    )
    for store in STORES:
        directory = root / "parsed" / store / VERSION
        directory.mkdir(parents=True)
        (directory / "index.jsonl").write_text(
            "".join(f"{line}\n" for line in SOURCES[store]), encoding="utf-8"
        )
        (directory / "occurrences.jsonl").write_text(
            "".join(f"{line}\n" for line in OCCURRENCES[store]), encoding="utf-8"
        )
    index = root / "tub-index" / INDEX_ID
    index.mkdir(parents=True)
    (index / "restored-from-bucket").write_text("restored\n", encoding="utf-8")
    (index / "manifest.json").write_text(
        json.dumps(
            {
                "index_id": INDEX_ID,
                "provenance_limit": 25,
                "stores": [
                    {
                        "caselist": store,
                        "version_directory": VERSION,
                        "occurrence_rows": len(OCCURRENCES[store]),
                    }
                    for store in STORES
                ],
                "suppression": {"entries": 1, "path_holds": 0, "sha256": "e" * 64},
                "counts": {
                    "documents": 4,
                    "documents_by_store": {"openev": 1, "testcl26": 3},
                    "occurrences": 6,
                    "provenance_rows": 6,
                    "occurrence_rows_read": 6,
                    "suppressed_occurrences": 0,
                    "clusters_left_out": 0,
                },
            }
        ),
        encoding="utf-8",
    )


class World:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.home.mkdir()
        self.fake = root / "build"
        self.fake.mkdir()
        cloud_copy(root / "cloud")
        self.control: dict[str, Any] = {"run_state": "bucket"}
        self.save()
        build = self.fake / "debate-research"
        build.write_text(
            FAKE_BUILD.replace("@PYTHON@", sys.executable)
            .replace("@WORLD@", repr(str(root)))
            .replace("@VERSION@", VERSION)
            .replace("@INDEX_ID@", INDEX_ID),
            encoding="utf-8",
        )
        build.chmod(0o755)
        self.build = build
        self.scratch = self.home / "dev-comparison"
        self.record = root / "record.md"

    def save(self) -> None:
        (self.root / "control.json").write_text(json.dumps(self.control), encoding="utf-8")

    def compare(self, run_id: str = RUN) -> subprocess.CompletedProcess[str]:
        self.save()
        environment = {
            "HOME": str(self.home),
            "PATH": f"{self.fake}:{os.environ['PATH']}",
            # A leftover override in the operator's shell: it must reach no command.
            "DEBATE_STORAGE__DATA_DIR": str(self.root / "the-operators-other-store"),
            "DEBATE_CASELIST__RUN_STATE": "local",
        }
        return subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPT),
                "--run-id",
                run_id,
                "--scratch",
                str(self.scratch),
                "--record",
                str(self.record),
                "--debate-research",
                str(self.build),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

    def calls(self) -> list[dict[str, Any]]:
        log = self.root / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    def commands(self) -> list[list[str]]:
        return [call["argv"][1:] for call in self.calls()]


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_the_two_sides_agreeing_is_agree_and_a_record_of_counts(world: World) -> None:
    compared = world.compare()

    assert compared.returncode == 0, compared.stdout + compared.stderr
    assert "compare: AGREE: 0 difference(s)" in compared.stdout
    record = world.record.read_text(encoding="utf-8")
    assert record.startswith("<!-- docs-index: ")
    assert "**Verdict: AGREE.**" in record
    assert f"| Run | `{RUN}` |" in record
    assert "| testcl26 | cloud | 3 | 2 | 1 | 0 | 5 | 5 |  |  |" in record
    assert "| testcl26 | Mac | 3 | 2 | 1 | 0 | 5 | 5 | the same | the same |" in record
    assert "| openev | Mac | 1 | 1 | 0 | 0 | 1 | 1 | the same | the same |" in record
    assert "| documents | 4 | 4 |" in record
    assert "| documents, testcl26 | 3 | 3 |" in record
    assert "| The Mac's build | `v1.1.0-dev.150` |" in record
    assert "Nowhere." in record


def test_no_record_or_line_printed_names_a_school_a_team_or_a_file(world: World) -> None:
    compared = world.compare()

    for said in (compared.stdout, world.record.read_text(encoding="utf-8")):
        for word in ("Fictional", "Prep", ".docx", str(world.scratch), str(world.home)):
            assert word not in said, word


def test_a_source_the_mac_parsed_differently_is_differ_and_the_record_says_where(world: World) -> None:
    """A per-file timeout on one machine and not the other is the likeliest real difference."""
    world.control["reparse"] = {
        "testcl26": {
            "index.jsonl": [source("a"), source("b", outcome="FAILED"), source("c", outcome="UNSUPPORTED")]
        }
    }

    compared = world.compare()

    assert compared.returncode == 1, compared.stdout + compared.stderr
    record = world.record.read_text(encoding="utf-8")
    assert "**Verdict: DIFFER.**" in record
    assert "* testcl26: PARSED sources, cloud 2, Mac 1" in record
    assert "* testcl26: FAILED sources, cloud 0, Mac 1" in record
    assert "* testcl26: cards, cloud 5, Mac 2" in record
    assert "* testcl26: the source records differ" in record
    assert "openev" not in record.split("## Where they differ")[1]


def test_records_with_the_same_counts_but_other_rows_differ(world: World) -> None:
    """Counts alone would pass two stores that hold different cards in the same numbers."""
    rows = list(OCCURRENCES["testcl26"])
    rows[0] = occurrence("a", 2)
    world.control["reparse"] = {"testcl26": {"occurrences.jsonl": rows}}

    compared = world.compare()

    assert compared.returncode == 1
    assert "* testcl26: the occurrence records differ" in world.record.read_text(encoding="utf-8")


def test_an_index_count_that_differs_is_differ(world: World) -> None:
    world.control["index_counts"] = {"documents": 5, "documents_by_store": {"openev": 1, "testcl26": 4}}

    compared = world.compare()

    assert compared.returncode == 1
    record = world.record.read_text(encoding="utf-8")
    assert "* index: documents, cloud 4, Mac 5" in record
    assert "* index: documents by store differ" in record


def test_a_copy_that_is_not_the_named_runs_stops_before_anything_is_parsed(world: World) -> None:
    compared = world.compare(run_id="20261104T110003Z")

    assert compared.returncode == 2
    assert f"the bucket's newest run is {RUN}, not 20261104T110003Z" in compared.stdout
    assert [command for command in world.commands() if command[:2] == ["caselist", "parse"]] == []
    assert not world.record.exists()


def test_a_restore_the_lock_refused_stops_with_its_code(world: World) -> None:
    """The cloud run still holds the lock: nothing is restored, parsed or written."""
    world.control["restore_refused"] = "RUN_LOCK_HELD"

    compared = world.compare()

    assert compared.returncode == 2
    assert "failed with RUN_LOCK_HELD" in compared.stdout
    assert [command[:2] for command in world.commands()] == [
        ["config", "show"],
        ["--version"],
        ["caselist", "restore-run-state"],
    ]
    assert not world.record.exists()


def test_a_build_that_keeps_its_state_locally_is_not_used(world: World) -> None:
    world.control["run_state"] = "local"

    compared = world.compare()

    assert compared.returncode == 2
    assert "keeps its run state locally" in compared.stdout
    assert [command[:2] for command in world.commands()] == [["config", "show"]]


def test_every_command_runs_in_an_environment_of_its_own_and_none_pulls_or_publishes(world: World) -> None:
    assert world.compare().returncode == 0

    for call in world.calls():
        environment = call["environment"]
        # The stand-in is a Python process: its own interpreter, and macOS's shell, add these to what it
        # was given.
        added = {"PWD", "SHLVL", "_", "__CF_USER_TEXT_ENCODING", "LC_CTYPE"}
        named = {name for name in environment if name not in added}
        assert named <= {"HOME", "PATH", "DEBATE_ENV", "DEBATE_STORAGE__DATA_DIR"}, named
        assert environment["DEBATE_ENV"] == "dev"
        assert environment.get("DEBATE_STORAGE__DATA_DIR") in (None, str(world.scratch))
        assert "DEBATE_CASELIST__RUN_STATE" not in environment
    commands = world.commands()
    assert not [command for command in commands if "pull" in command or any("publish" in a for a in command)]
    parses = [command for command in commands if command[:2] == ["caselist", "parse"]]
    assert sorted(command[command.index("--caselist") + 1] for command in parses) == sorted(STORES)
    assert all("--reparse" in command for command in parses)
    [build] = [command for command in commands if command[:3] == ["tub", "index", "build"]]
    assert build[build.index("--provenance-limit") + 1] == "25"
    assert build[build.index("--out") + 1] == str(world.scratch / "comparison-index")


def test_the_script_runs_on_the_standard_library_alone() -> None:
    """The operator runs it with `python3 -I`, outside any environment this repository makes."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    imported += [str(node.module) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]

    assert imported, "the script imports nothing"
    for module in imported:
        assert module.split(".")[0] in sys.stdlib_module_names, module


def test_a_scratch_directory_is_never_removed_by_the_script(world: World) -> None:
    """Removing the copy is the runbook's step, once the record is committed: the script only writes."""
    assert world.compare().returncode == 0

    assert (world.scratch / "parsed").is_dir()
    assert "rmtree" not in SCRIPT.read_text(encoding="utf-8")
    shutil.rmtree(world.scratch)


# ------------------------------------------------------------------------------------------------
# An identical rebuild under a longer list: the record beside the manifest (v1-e39-t19, ac2)
# ------------------------------------------------------------------------------------------------

LONGER_LIST: Final = {"entries": 2, "path_holds": 0, "sha256": "f" * 64}
"""The list both rebuilds read: one entry longer than the manifest's, stopping nothing."""


def checked_against(world: World, *, manifest_sha256: str | None = None) -> dict[str, Any]:
    """A record of the longer list beside the cloud's manifest, as the restore brings it back."""
    index = world.root / "cloud" / "tub-index" / INDEX_ID
    manifest = json.loads((index / "manifest.json").read_text(encoding="utf-8"))
    record = {
        "record_version": 1,
        "index_id": INDEX_ID,
        "manifest_sha256": manifest_sha256
        or hashlib.sha256((index / "manifest.json").read_bytes()).hexdigest(),
        "parser_version": VERSION,
        "stores": manifest["stores"],
        "snapshot": "2026-10-28",
        "suppression": LONGER_LIST,
        "counts": manifest["counts"],
    }
    (index / "checked-against.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def test_a_longer_list_the_manifest_does_not_name_differs_as_at_the_cutover(world: World) -> None:
    """The cutover's case: the published manifest names the list the index was first built from."""
    world.control["index_suppression"] = LONGER_LIST

    compared = world.compare()

    assert compared.returncode == 1, compared.stdout + compared.stderr
    record = world.record.read_text(encoding="utf-8")
    assert "* index: the suppression lists applied differ" in record
    assert "| Suppression list applied | 1 entries | 2 entries, another |" in record
    assert "| Index checked against | its manifest |" in record


def test_an_identical_rebuild_under_a_longer_list_agrees_by_the_record_beside_the_manifest(
    world: World,
) -> None:
    world.control["index_suppression"] = LONGER_LIST
    checked_against(world)

    compared = world.compare()

    assert compared.returncode == 0, compared.stdout + compared.stderr
    assert "compare: AGREE: 0 difference(s)" in compared.stdout
    record = world.record.read_text(encoding="utf-8")
    assert "**Verdict: AGREE.**" in record
    assert "| Index checked against | the record beside its manifest, `checked-against.json` |" in record
    assert "| Suppression list applied | 2 entries | 2 entries, the same |" in record
    assert "Nowhere." in record


def test_the_record_beside_the_manifest_is_read_for_the_list_and_still_compared_for_counts(
    world: World,
) -> None:
    """The record says what the cloud's rebuild read: a count it differs from the Mac's in is a difference."""
    world.control["index_suppression"] = LONGER_LIST
    world.control["index_counts"] = {"suppressed_occurrences": 1}
    checked_against(world)

    compared = world.compare()

    assert compared.returncode == 1
    record = world.record.read_text(encoding="utf-8")
    assert "* index: suppressed_occurrences, cloud 0, Mac 1" in record
    assert "the suppression lists applied differ" not in record


def test_a_record_beside_another_manifest_is_not_read(world: World) -> None:
    """A record names its manifest by digest; one naming another says nothing of this one."""
    world.control["index_suppression"] = LONGER_LIST
    checked_against(world, manifest_sha256="0" * 64)

    compared = world.compare()

    assert compared.returncode == 1
    record = world.record.read_text(encoding="utf-8")
    assert "* index: the suppression lists applied differ" in record
    assert "| Index checked against | its manifest; the record beside it names another manifest |" in record


def test_a_record_that_is_not_json_is_not_read(world: World) -> None:
    world.control["index_suppression"] = LONGER_LIST
    (world.root / "cloud" / "tub-index" / INDEX_ID / "checked-against.json").write_text("{", encoding="utf-8")

    compared = world.compare()

    assert compared.returncode == 1
    record = world.record.read_text(encoding="utf-8")
    assert (
        "| Index checked against | its manifest; the record beside it is not one this script reads |"
        in record
    )
