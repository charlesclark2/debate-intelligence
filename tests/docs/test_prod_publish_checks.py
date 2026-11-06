"""The hand publish to prod's three checks, run on synthetic inputs (`v1-e40-t16`).

`docs/runbooks/caselist-cutover.md`, "Until the promotion", publishes prod's parsed store and search
index from a copy restored from dev only after three checks, each a Python heredoc in the runbook:

* `PRODCHECKS` (step 1) reads the parser versions (installed build, `origin/main`, prod's function),
  dev's last run, dev's current index manifest and dev's removal log. It says whether the raw sources
  and manifests go on (always, unless dev's index holds the `testcl26` seed) and whether the parsed
  store and index go on.
* `PARSECHECK` (step 3) reads each store's `caselist parse --dry-run` in the copy. It writes
  `parse-checked.txt` only when nothing is to parse.
* `COMPARE` (step 4) compares the index built from the copy with dev's current manifest. It writes
  `prod-index-compared.txt` only on a match. The PM's must-match set is every store's
  `version_directory`, `occurrence_rows`, `occurrences_sha256` and documents, plus the parser and
  fingerprint versions, the suppression list, the document count and the stores. The index id and
  the SQLite version are reported, not compared.

The code is read out of the runbook between its heredoc markers and run as the operator runs it
(`python3 -I -` with the runbook's arguments), so a change to the runbook is what is tested. The
blocks that write to prod are checked to refuse without the comparison's file. Every value here is
invented: no bucket, no real digest, no school or team.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pytest

RUNBOOK: Final = Path(__file__).resolve().parents[2] / "docs" / "runbooks" / "caselist-cutover.md"
NEW: Final = "2026.11.03-docx-9"
OLD: Final = "2026.10.27-docx-7"
FOLLOWED: Final = ("hsld26", "hspf26", "hspolicy26", "openev")
WRITTEN: Final = "2026-11-11T14:00:00+00:00"


def check_code(marker: str) -> str:
    """The Python between `<<'MARKER'` and its closing `MARKER` line in the runbook."""
    text = RUNBOOK.read_text(encoding="utf-8")
    [found] = re.findall(rf"<<'{marker}'\n(.*?)\n{marker}\n", text, flags=re.DOTALL)
    return found


def run_code(marker: str, *arguments: str | Path) -> list[str]:
    ran = subprocess.run(
        [sys.executable, "-I", "-", *map(str, arguments)],
        input=check_code(marker),
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    return ran.stdout.splitlines()


def section() -> str:
    text = RUNBOOK.read_text(encoding="utf-8")
    start = text.index("\n## Until the promotion: prod is published by hand\n")
    return text[start : text.index("\n## ", start + 1)]


def bash_blocks() -> list[str]:
    return re.findall(r"^```bash\n(.*?)^```$", section(), flags=re.DOTALL | re.MULTILINE)


# ------------------------------------------------------------------------------------------------
# Synthetic inputs
# ------------------------------------------------------------------------------------------------


def manifest(**changed: Any) -> dict[str, Any]:
    """Dev's current index manifest, in `SearchIndexManifest`'s shape (the fields the checks read)."""
    stores = [
        {
            "caselist": name,
            "version_directory": NEW,
            "latest_snapshot": "2026-11-11",
            "occurrence_rows": 1000 + number,
            "occurrences_sha256": f"{number + 1}" * 64,
        }
        for number, name in enumerate(FOLLOWED)
    ]
    documents = {name: 100 + number for number, name in enumerate(FOLLOWED)}
    body: dict[str, Any] = {
        "manifest_version": 1,
        "format_version": 3,
        "index_id": "a" * 16,
        "parser_version": NEW,
        "fingerprint_version": "card-fingerprint-v3",
        "sqlite_version": "3.50.4",
        "stores": stores,
        "suppression": {"entries": 6, "path_holds": 1, "sha256": "5" * 64},
        "counts": {"documents": sum(documents.values()), "documents_by_store": documents},
    }
    body.update(changed)
    return body


def runs(outcome: str = "completed", full_parses: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "status": "ok",
        "data": {
            "runs": [{"run_id": "20261111T110002Z", "outcome": outcome}],
            "parses_owed": {"full_parses": full_parses or [], "snapshots": []},
        },
    }


def removal_log(*recorded_at: str) -> str:
    return "".join(
        json.dumps({"schema_version": 1, "kind": "remove", "recorded_at": at, "environment": "dev"}) + "\n"
        for at in recorded_at
    )


class Checks:
    """The step 1 checks' inputs, written to files as the process substitutions hand them over."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.parsers = {"installed": NEW, "main": NEW, "function": NEW}
        self.written = WRITTEN
        self.runs: str = json.dumps(runs())
        self.manifest: str = json.dumps(manifest())
        self.log = removal_log("2026-11-02T10:00:00Z")

    def run(self) -> list[str]:
        files = []
        for name in ("runs", "manifest", "log"):
            path = self.tmp_path / f"{name}.txt"
            path.write_text(getattr(self, name), encoding="utf-8")
            files.append(path)
        return run_code(
            "PRODCHECKS",
            self.parsers["installed"],
            self.parsers["main"],
            self.parsers["function"],
            self.written,
            *files,
        )


def verdicts(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith(("STOP", "RAW", "PARSED"))]


# ------------------------------------------------------------------------------------------------
# Step 1: the checks
# ------------------------------------------------------------------------------------------------


def test_the_checks_send_everything_when_every_version_agrees(tmp_path: Path) -> None:
    lines = Checks(tmp_path).run()

    assert verdicts(lines) == ["RAW SOURCES AND MANIFESTS: go on", "PARSED STORE AND INDEX: go on"]
    assert "removals recorded after dev's index was written: 0" in lines


def test_a_function_behind_a_main_that_carries_the_installed_parser_is_deployed_first(tmp_path: Path) -> None:
    checks = Checks(tmp_path)
    checks.parsers["function"] = OLD

    assert verdicts(checks.run())[-1] == (
        "PARSED STORE AND INDEX: go on, with prod's function deployed from main first (step 7)"
    )


def test_a_main_without_the_installed_parser_waits_for_the_promotion(tmp_path: Path) -> None:
    checks = Checks(tmp_path)
    checks.parsers["function"] = checks.parsers["main"] = OLD

    said = verdicts(checks.run())

    assert said[0] == "RAW SOURCES AND MANIFESTS: go on"
    assert said[1:] == [
        f"PARSED STORE AND INDEX: not in this session: prod's function parses at {OLD} and main at {OLD}, "
        f"not {NEW}: the promotion first"
    ]


def test_the_seed_in_devs_index_stops_the_whole_session(tmp_path: Path) -> None:
    checks = Checks(tmp_path)
    seeded = manifest()
    seeded["stores"].append({**seeded["stores"][0], "caselist": "testcl26"})
    checks.manifest = json.dumps(seeded)

    said = verdicts(checks.run())

    assert said == [
        "STOP: dev's index holds testcl26: the journey is between J5 and J9, and no prod session runs then",
        "STOP: nothing goes to prod in this session",
    ]


def test_an_unreadable_manifest_stops_the_whole_session(tmp_path: Path) -> None:
    checks = Checks(tmp_path)
    checks.manifest = ""

    assert verdicts(checks.run())[-1] == "STOP: nothing goes to prod in this session"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (
            lambda checks: setattr(
                checks, "log", removal_log("2026-11-02T10:00:00Z", "2026-11-11T15:00:00Z")
            ),
            "a removal is newer than dev's index: wait for the next weekly run's index",
        ),
        (
            lambda checks: setattr(checks, "log", ""),
            "dev's removal log or the index's write time could not be read",
        ),
        (
            lambda checks: setattr(checks, "runs", json.dumps(runs(outcome="failed"))),
            "dev's last run is failed, not completed",
        ),
        (
            lambda checks: setattr(
                checks, "runs", json.dumps(runs(full_parses=[{"caselist": "hsld26", "parser_version": NEW}]))
            ),
            "dev's run owes a full parse, or its record of them could not be read",
        ),
        (
            lambda checks: setattr(
                checks,
                "manifest",
                json.dumps(
                    manifest(
                        stores=[
                            {**one, "version_directory": OLD} if one["caselist"] == "hspf26" else one
                            for one in manifest()["stores"]
                        ]
                    )
                ),
            ),
            f"hspf26 is {OLD} in dev's index, not {NEW}",
        ),
        (
            lambda checks: setattr(checks, "manifest", json.dumps(manifest(parser_version=OLD))),
            f"dev's index is at parser {OLD}, not the installed {NEW}",
        ),
        (
            lambda checks: setattr(checks, "manifest", json.dumps(manifest(stores=manifest()["stores"][:3]))),
            "dev's index holds hsld26 hspf26 hspolicy26, not the four stores step 6 publishes",
        ),
        (
            lambda checks: checks.parsers.update(installed=""),
            "the installed build's parser version could not be read",
        ),
    ],
    ids=[
        "removal",
        "no-log",
        "failed-run",
        "parse-owed",
        "store-version",
        "index-parser",
        "store-missing",
        "no-installed",
    ],
)
def test_each_failed_check_holds_the_parsed_store_back_and_sends_the_raw_sources(
    tmp_path: Path, change: Any, reason: str
) -> None:
    checks = Checks(tmp_path)
    change(checks)

    said = verdicts(checks.run())

    assert said[0] == "RAW SOURCES AND MANIFESTS: go on"
    assert f"PARSED STORE AND INDEX: not in this session: {reason}" in said
    assert "PARSED STORE AND INDEX: go on" not in said


def test_a_removal_older_than_the_index_holds_nothing_back(tmp_path: Path) -> None:
    checks = Checks(tmp_path)
    checks.log = removal_log("2026-11-02T10:00:00Z", "2026-11-11T13:59:59Z")

    assert verdicts(checks.run())[-1] == "PARSED STORE AND INDEX: go on"


# ------------------------------------------------------------------------------------------------
# Step 3: the parse check in the copy
# ------------------------------------------------------------------------------------------------


def dry_run(store: str, **changed: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "environment": "dev",
        "caselist": store,
        "applied": False,
        "version": NEW,
        "new_version": False,
        "parser_version": NEW,
        "sources": 400,
        "skipped": 400,
        "suppressed": 0,
        "to_parse": 0,
        "store": None,
    }
    data.update(changed)
    return {"schema_version": 1, "status": "ok", "command": "caselist parse", "data": data, "error": None}


def parse_check(tmp_path: Path, answers: dict[str, dict[str, Any] | str]) -> tuple[list[str], Path]:
    paths = []
    for store in ("hsld26", "hspolicy26", "hspf26", "openev"):
        path = tmp_path / f"parse-check-{store}.json"
        answer = answers.get(store, dry_run(store))
        path.write_text(answer if isinstance(answer, str) else json.dumps(answer), encoding="utf-8")
        paths.append(path)
    passed = tmp_path / "parse-checked.txt"
    return run_code("PARSECHECK", NEW, passed, *paths), passed


def test_the_parse_check_passes_when_every_store_is_parsed_already(tmp_path: Path) -> None:
    lines, passed = parse_check(tmp_path, {})

    assert lines[-1] == f"OK: every store's sources are parsed in the restored {NEW}; nothing is parsed here"
    assert passed.read_text(encoding="utf-8") == NEW + "\n"


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (dry_run("hspf26", to_parse=3), "STOP: hspf26: 3 to parse; dev's directory lacks them"),
        (dry_run("hspf26", new_version=True), f"STOP: hspf26: the directory is not the restored {NEW}"),
        (
            dry_run("hspf26", version=OLD, parser_version=OLD),
            f"STOP: hspf26: the directory is not the restored {NEW}",
        ),
        (dry_run("hspf26", sources=0), "STOP: hspf26: no sources"),
        (
            {"schema_version": 1, "status": "error", "data": None, "error": {"code": "RUN_LOCK_HELD"}},
            "STOP: hspf26.json: RUN_LOCK_HELD",
        ),
        ("", "STOP: hspf26.json: no answer"),
    ],
    ids=["to-parse", "new-version", "other-version", "no-sources", "error", "empty"],
)
def test_the_parse_check_stops_and_writes_nothing_on_any_store_that_is_not_parsed_already(
    tmp_path: Path, answer: dict[str, Any] | str, said: str
) -> None:
    lines, passed = parse_check(tmp_path, {"hspf26": answer})

    assert said in lines
    assert not passed.exists()


# ------------------------------------------------------------------------------------------------
# Step 4: the comparison
# ------------------------------------------------------------------------------------------------


def compare(tmp_path: Path, built: dict[str, Any]) -> tuple[list[str], Path]:
    before, build = tmp_path / "manifest.json", tmp_path / "prod-index-build.json"
    before.write_text(json.dumps(manifest()), encoding="utf-8")
    build.write_text(
        json.dumps({"status": "ok", "data": {"directory": "x", "manifest": built}}), encoding="utf-8"
    )
    compared = tmp_path / "prod-index-compared.txt"
    return run_code("COMPARE", before, build, compared), compared


def test_an_index_with_devs_counts_and_digests_passes_whatever_its_id_and_sqlite(tmp_path: Path) -> None:
    built = manifest(index_id="b" * 16, sqlite_version="3.43.2")

    lines, compared = compare(tmp_path, built)

    assert lines[0] == (
        f"built {'b' * 16} sqlite 3.43.2 / dev's {'a' * 16} sqlite 3.50.4 (reported, not compared)"
    )
    assert lines[-1] == "OK: every store, count and digest equals dev's index"
    assert compared.read_text(encoding="utf-8") == "b" * 16 + "\n"


def changed_store(field: str, value: Any) -> dict[str, Any]:
    built = manifest()
    built["stores"][1][field] = value
    return built


def changed_documents() -> dict[str, Any]:
    built = manifest()
    built["counts"]["documents_by_store"]["hspf26"] += 1
    built["counts"]["documents_by_store"]["hspolicy26"] -= 1
    return built


def changed_suppression(field: str, value: Any) -> dict[str, Any]:
    built = manifest()
    built["suppression"][field] = value
    return built


def dropped_store() -> dict[str, Any]:
    built = manifest()
    del built["stores"][3]
    built["counts"]["documents_by_store"].pop("openev")
    return built


@pytest.mark.parametrize(
    ("built", "said"),
    [
        (
            changed_store("version_directory", OLD),
            f"STOP: hspf26 version_directory: {OLD} built, {NEW} in dev's index",
        ),
        (changed_store("occurrence_rows", 7), "STOP: hspf26 occurrence_rows: 7 built, 1001 in dev's index"),
        (
            changed_store("occurrences_sha256", "9" * 64),
            "STOP: hspf26 occurrences_sha256: 999999999999 built, 222222222222 in dev's index",
        ),
        (changed_documents(), "STOP: hspf26 documents: 102 built, 101 in dev's index"),
        (manifest(parser_version=OLD), f"STOP: parser_version: {OLD} built, {NEW} in dev's index"),
        (
            manifest(fingerprint_version="card-fingerprint-v4"),
            "STOP: fingerprint_version: card-fingerprint-v4 built, card-fingerprint-v3 in dev's index",
        ),
        (changed_suppression("entries", 5), "STOP: suppression entries: 5 built, 6 in dev's index"),
        (changed_suppression("path_holds", 0), "STOP: suppression path_holds: 0 built, 1 in dev's index"),
        (
            changed_suppression("sha256", "6" * 64),
            "STOP: suppression sha256: 666666666666 built, 555555555555 in dev's index",
        ),
        (
            dropped_store(),
            "STOP: stores: hsld26 hspf26 hspolicy26 built, hsld26 hspf26 hspolicy26 openev in dev's index",
        ),
    ],
    ids=[
        "version-directory",
        "occurrence-rows",
        "occurrences-digest",
        "store-documents",
        "parser",
        "fingerprint",
        "suppression-entries",
        "path-holds",
        "suppression-digest",
        "stores",
    ],
)
def test_any_difference_in_the_must_match_set_stops_and_writes_nothing(
    tmp_path: Path, built: dict[str, Any], said: str
) -> None:
    lines, compared = compare(tmp_path, built)

    assert said in lines
    assert lines[-1].startswith("STOP: ")
    assert not compared.exists()


def test_a_total_that_differs_with_every_store_equal_still_stops(tmp_path: Path) -> None:
    built = copy.deepcopy(manifest())
    built["counts"]["documents"] += 1

    lines, compared = compare(tmp_path, built)

    total = built["counts"]["documents"]
    assert lines[-1] == f"STOP: documents: {total} built, {total - 1} in dev's index"
    assert not compared.exists()


# ------------------------------------------------------------------------------------------------
# The blocks around the checks
# ------------------------------------------------------------------------------------------------


def test_every_block_that_writes_to_prod_refuses_without_the_comparisons_ok() -> None:
    writers = [block for block in bash_blocks() if "--publish-only" in block or "tub index publish" in block]

    assert len(writers) == 2
    for block in writers:
        assert '[[ ! -f "${COPY}/prod-index-compared.txt" ]]' in block
        assert "--confirm-prod" in block
    [comparison] = [block for block in bash_blocks() if "tub index build" in block]
    assert '[[ ! -f "${COPY}/parse-checked.txt" ]]' in comparison


def test_the_parsed_store_is_never_parsed_or_rebuilt_in_the_copy() -> None:
    for block in bash_blocks():
        for line in block.splitlines():
            if "caselist parse" in line:
                assert "--dry-run" in line or "--publish-only" in line, line
            assert "--reparse" not in line and "--publish " not in line + " ", line


def test_every_block_but_the_deletion_refuses_an_override_a_pull_and_a_wednesday() -> None:
    blocks = bash_blocks()
    deletion = [block for block in blocks if "rm -rf" in block]

    assert len(deletion) == 1
    for block in blocks:
        if block in deletion:
            continue
        assert "pgrep -fl 'debate-research( --json)? caselist pull'" in block
        assert "env | grep '^DEBATE_'" in block
        assert '"$(TZ=America/Chicago date +%u)" = 3' in block


def test_the_restore_stops_on_a_copy_that_exists_and_the_deletion_names_only_prod_publish_copies() -> None:
    [restore] = [block for block in bash_blocks() if "restore-run-state" in block]
    [deletion] = [block for block in bash_blocks() if "rm -rf" in block]

    assert '[[ -e "$COPY" ]]' in restore
    assert 'case "$COPY" in "$HOME/.debate-research/prod-publish-2"*) rm -rf "$COPY"' in deletion
