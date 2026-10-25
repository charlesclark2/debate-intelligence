"""Compare a dev cloud run with the Mac's offline reproduction of its parse and index (`v1-e40-t06`, ac1).

ADR-0020 (4): the comparison is not a second run of the same week, which would download the week's
archives again and publish twice. After a cloud run, the Mac restores that run's working copy into a
scratch data directory under the bucket's run lock, re-parses every store the run's index was built
from and rebuilds the index from the re-parse, into the same scratch directory, and the two are
compared. Run by the operator, on the Mac, with the installed build that has `caselist
restore-run-state` (the cutover runbook, docs/runbooks/caselist-cutover.md):

    python3 -I ops/caselist_run/compare_cloud_run.py --run-id 20261029T110002Z \\
        --scratch ~/.debate-research/dev-comparison-20261029T110002Z \\
        --record docs/data/caselist-cloud-run-comparison.md

What it does, in order, each step a `debate-research` command run as the installed build, in an
environment built from nothing but `HOME`, a `PATH` of the build's directory and the system's, and
`DEBATE_ENV=dev` (working agreement 11: no `DEBATE_*` override of the shell's reaches it):

1. **Restore**, `caselist restore-run-state --into <scratch>`: the bundle, the state files, the
   published index's manifest and the parsed store's current version of each store, under the lock.
2. **The run is the one named.** The restored run log's newest record must be `--run-id`; otherwise
   the bucket's state is some other run's, and nothing is compared.
3. **The cloud's side**, read from the restored files: each store's source records (`index.jsonl`)
   and occurrence records (`occurrences.jsonl`) in the version directory the cloud's index read, and
   the cloud's index manifest.
4. **Re-parse**, `caselist parse --caselist <store> --reparse` for each store, in the scratch
   directory: every source parsed again, into a new generation beside the restored one. Raw sources
   the copy lacks are read from the dev bucket's `raw/`, as a cloud run reads them. Nothing is
   downloaded from OpenCaselist, and nothing is published: the parse takes no `--publish`, and in
   bucket mode every write to the bucket needs the lock, which it does not hold.
5. **Rebuild the index**, `tub index build` over the same stores with the cloud's provenance limit,
   into `<scratch>/comparison-index`, from the re-parse.
6. **Compare** each store's source records and occurrence records, by count and by a digest of the
   sorted lines, and the two indexes' counts, and print the result.

**Counts only.** What it prints, and the record it writes for `docs/data/`, are counts, store slugs,
version and index ids, digests compared as equal or not, and run ids. It never reads a manifest
row's path, and no school, team code or file name is in anything it writes. The scratch directory
does hold a copy of the corpus: the runbook removes it once the record is committed.

Exit `0` when the two agree, `1` when they differ (the record says where), `2` when the comparison
could not be made (it says why, and writes no record).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
RUN_ID = re.compile(r"^\d{8}T\d{6}Z$")
RUN_LOG = "caselist-sync-runs.jsonl"
RUN_DETAILS = "caselist-sync-run-details.jsonl"
COMPARISON_INDEX = "comparison-index"
OUTCOMES = ("PARSED", "UNSUPPORTED", "FAILED")
INDEX_COUNTS = (
    "documents",
    "occurrences",
    "occurrence_rows_read",
    "suppressed_occurrences",
    "clusters_left_out",
    "provenance_rows",
)
DOCS_INDEX_LINE = (
    "<!-- docs-index: The cutover's comparison of a dev cloud run with the Mac's offline reproduction of "
    "its parse and index: counts only (v1-e40-t06) -->"
)


class ComparisonStopped(Exception):
    """The comparison could not be made. The message says why; nothing is written."""


@dataclass(frozen=True)
class RecordsOf:
    """One store's records in one version directory: counts, and digests of the sorted lines."""

    version_directory: str
    sources: int
    outcomes: dict[str, int]
    cards: int
    occurrence_rows: int
    sources_sha256: str
    occurrences_sha256: str


@dataclass
class Comparison:
    run_id: str
    restored: dict[str, object]
    record: dict[str, object]
    details: dict[str, object]
    cloud_index: dict[str, object]
    mac_index: dict[str, object] = field(default_factory=dict)
    cloud: dict[str, RecordsOf] = field(default_factory=dict)
    mac: dict[str, RecordsOf] = field(default_factory=dict)
    mac_build: str = ""

    def differences(self) -> list[str]:
        """Each way the two disagree, in words: empty when they agree."""
        found: list[str] = []
        for store in sorted(self.cloud):
            cloud, mac = self.cloud[store], self.mac.get(store)
            if mac is None:
                found.append(f"{store}: not re-parsed")
                continue
            for name, there, here in (
                ("sources", cloud.sources, mac.sources),
                *(
                    (f"{outcome} sources", cloud.outcomes[outcome], mac.outcomes[outcome])
                    for outcome in OUTCOMES
                ),
                ("cards", cloud.cards, mac.cards),
                ("occurrence rows", cloud.occurrence_rows, mac.occurrence_rows),
            ):
                if there != here:
                    found.append(f"{store}: {name}, cloud {there}, Mac {here}")
            if cloud.sources_sha256 != mac.sources_sha256:
                found.append(f"{store}: the source records differ")
            if cloud.occurrences_sha256 != mac.occurrences_sha256:
                found.append(f"{store}: the occurrence records differ")
        cloud_counts, mac_counts = _counts(self.cloud_index), _counts(self.mac_index)
        for name in INDEX_COUNTS:
            if cloud_counts.get(name) != mac_counts.get(name):
                found.append(f"index: {name}, cloud {cloud_counts.get(name)}, Mac {mac_counts.get(name)}")
        if cloud_counts.get("documents_by_store") != mac_counts.get("documents_by_store"):
            found.append("index: documents by store differ")
        if _suppression(self.cloud_index) != _suppression(self.mac_index):
            found.append("index: the suppression lists applied differ")
        return found


# ------------------------------------------------------------------------------------------------
# Running the installed build
# ------------------------------------------------------------------------------------------------


def child_environment(build: Path, data_dir: Path | None = None) -> dict[str, str]:
    """The environment every command runs in: nothing of this shell's but HOME (agreement 11)."""
    environment = {
        "HOME": os.environ["HOME"],
        "PATH": f"{build.parent}:{SYSTEM_PATH}",
        "DEBATE_ENV": "dev",
    }
    if data_dir is not None:
        environment["DEBATE_STORAGE__DATA_DIR"] = str(data_dir)
    return environment


def run_build(
    build: Path, *arguments: str, data_dir: Path | None = None, accept: tuple[str, ...] = ()
) -> dict[str, object]:
    """One `debate-research --json` command; its envelope's `data`, or a stop naming its error code.

    `accept` names error codes that still carry what the comparison needs, in the error's details.
    """
    print(f"compare: debate-research {' '.join(arguments)}", file=sys.stderr, flush=True)
    finished = subprocess.run(
        [str(build), "--json", *arguments],
        env=child_environment(build, data_dir),
        cwd=os.environ["HOME"],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in finished.stdout.splitlines() if line.strip()]
    try:
        envelope = json.loads(lines[-1])
    except (IndexError, ValueError):
        raise ComparisonStopped(
            f"`debate-research {' '.join(arguments[:2])}` printed no JSON (exit {finished.returncode})"
        ) from None
    if envelope.get("status") == "ok":
        return envelope["data"]
    error = envelope.get("error") or {}
    if error.get("code") in accept and isinstance(error.get("details"), dict):
        return error["details"]
    raise ComparisonStopped(
        f"`debate-research {' '.join(arguments[:2])}` failed with {error.get('code')}: {error.get('message')}"
    )


# ------------------------------------------------------------------------------------------------
# Reading the copy: counts and digests, never a row's words
# ------------------------------------------------------------------------------------------------


def records_of(directory: Path) -> RecordsOf:
    """The source and occurrence records of one version directory."""
    index, occurrences = directory / "index.jsonl", directory / "occurrences.jsonl"
    if not index.is_file() or not occurrences.is_file():
        raise ComparisonStopped(f"a version directory, {directory.name}, has no aggregates")
    source_lines = _lines(index)
    outcomes: Counter[str] = Counter()
    cards = 0
    for line in source_lines:
        record = json.loads(line)
        outcomes[str(record.get("outcome"))] += 1
        cards += int(record.get("cards") or 0)
    occurrence_lines = _lines(occurrences)
    return RecordsOf(
        version_directory=directory.name,
        sources=len(source_lines),
        outcomes={outcome: outcomes[outcome] for outcome in OUTCOMES},
        cards=cards,
        occurrence_rows=len(occurrence_lines),
        sources_sha256=_digest(source_lines),
        occurrences_sha256=_digest(occurrence_lines),
    )


def _lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _digest(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def _counts(manifest: dict[str, object]) -> dict[str, object]:
    counts = manifest.get("counts")
    return counts if isinstance(counts, dict) else {}


def _suppression(manifest: dict[str, object]) -> object:
    suppression = manifest.get("suppression")
    return suppression.get("sha256") if isinstance(suppression, dict) else None


def _stores(manifest: dict[str, object]) -> list[dict[str, object]]:
    stores = manifest.get("stores")
    if not isinstance(stores, list) or not stores:
        raise ComparisonStopped("the cloud's index manifest names no store")
    return [store for store in stores if isinstance(store, dict)]


def newest_line_for(path: Path, run_id: str | None) -> dict[str, object]:
    """The newest line of a run log or its details, or the newest for `run_id`; empty when absent."""
    if not path.is_file():
        return {}
    for line in reversed(_lines(path)):
        record = json.loads(line)
        if run_id is None or record.get("run_id") == run_id:
            return record
    return {}


# ------------------------------------------------------------------------------------------------
# The comparison
# ------------------------------------------------------------------------------------------------


def compare(build: Path, run_id: str, scratch: Path) -> Comparison:
    shown = run_build(build, "config", "show")
    settings = shown.get("settings") if isinstance(shown.get("settings"), dict) else {}
    assert isinstance(settings, dict)
    if settings.get("caselist.run_state") != "bucket":
        raise ComparisonStopped(
            "the installed build keeps its run state locally; install the cutover's build, whose dev "
            "profile sets caselist.run_state = bucket"
        )
    version = run_build(build, "--version")
    mac_build = str(version.get("tag") or version.get("version"))

    restored = run_build(build, "caselist", "restore-run-state", "--into", str(scratch))
    record = newest_line_for(scratch / RUN_LOG, None)
    if record.get("run_id") != run_id:
        raise ComparisonStopped(
            f"the bucket's newest run is {record.get('run_id')}, not {run_id}: its state is another run's, "
            "so this copy is not that run's inputs"
        )
    index_id = restored.get("index_id")
    manifest_path = scratch / "tub-index" / str(index_id) / "manifest.json"
    if not index_id or not manifest_path.is_file():
        raise ComparisonStopped("the restore brought no published index manifest")
    comparison = Comparison(
        run_id=run_id,
        restored=restored,
        record=record,
        details=newest_line_for(scratch / RUN_DETAILS, run_id),
        cloud_index=json.loads(manifest_path.read_text(encoding="utf-8")),
        mac_build=mac_build,
    )

    stores = _stores(comparison.cloud_index)
    for store in stores:
        slug, version = str(store["caselist"]), str(store["version_directory"])
        comparison.cloud[slug] = records_of(scratch / "parsed" / slug / version)

    for slug in sorted(comparison.cloud):
        parsed = run_build(
            build,
            "caselist",
            "parse",
            "--caselist",
            slug,
            "--reparse",
            data_dir=scratch,
            accept=("PARSE_FAILURE_RATE_EXCEEDED",),
        )
        version = str(parsed.get("version") or "")
        if not version or version == comparison.cloud[slug].version_directory:
            raise ComparisonStopped(f"{slug}: the re-parse did not write a new generation")
        comparison.mac[slug] = records_of(scratch / "parsed" / slug / version)

    built = run_build(
        build,
        "tub",
        "index",
        "build",
        *(argument for slug in sorted(comparison.cloud) for argument in ("--caselist", slug)),
        "--out",
        str(scratch / COMPARISON_INDEX),
        "--provenance-limit",
        str(comparison.cloud_index.get("provenance_limit")),
        data_dir=scratch,
    )
    manifest = built.get("manifest")
    if not isinstance(manifest, dict):
        raise ComparisonStopped("tub index build reported no manifest")
    comparison.mac_index = manifest
    for store in _stores(manifest):
        slug = str(store["caselist"])
        if slug in comparison.mac and store["version_directory"] != comparison.mac[slug].version_directory:
            raise ComparisonStopped(f"{slug}: the rebuilt index did not read the re-parse")
    return comparison


# ------------------------------------------------------------------------------------------------
# What it says: counts only
# ------------------------------------------------------------------------------------------------


def report(comparison: Comparison, *, today: str) -> str:
    """The record, in Markdown: printed, and written for `docs/data/`."""
    differences = comparison.differences()
    record, details = comparison.record, comparison.details
    parse = details.get("parse") if isinstance(details.get("parse"), dict) else {}
    assert isinstance(parse, dict)
    cloud_counts, mac_counts = _counts(comparison.cloud_index), _counts(comparison.mac_index)
    same_suppression = _suppression(comparison.cloud_index) == _suppression(comparison.mac_index)
    verdict = "AGREE" if not differences else "DIFFER"
    lines = [
        DOCS_INDEX_LINE,
        "# The cutover's comparison: a dev cloud run and the Mac's reproduction of it",
        "",
        f"Measured {today} by `ops/caselist_run/compare_cloud_run.py` (`v1-e40-t06`, ac1; ADR-0020 (4)).",
        "The Mac restored the cloud run's working copy under the dev bucket's run lock, re-parsed every",
        "store the run's index was built from, and rebuilt the index from the re-parse, offline: nothing",
        "was downloaded from OpenCaselist and nothing was published. Counts, store slugs and ids only.",
        "",
        f"**Verdict: {verdict}.**",
        "",
        "## The cloud run",
        "",
        "| | |",
        "|---|---|",
        f"| Run | `{comparison.run_id}` |",
        f"| Outcome | `{record.get('outcome')}` |",
        f"| Archives downloaded | {record.get('archives_downloaded')} |",
        f"| Files imported | {record.get('files_imported')} |",
        f"| Objects published | {record.get('objects_published')} |",
        f"| Sources its parse stage parsed | {parse.get('attempted')} (cards {parse.get('cards')}) |",
        f"| Index | `{comparison.cloud_index.get('index_id')}` |",
        f"| Restored | {comparison.restored.get('manifests')} manifests, "
        f"{comparison.restored.get('parsed_objects')} parsed-store objects at "
        f"`{comparison.restored.get('parsed_version')}`, in {comparison.restored.get('seconds')} s |",
        f"| The Mac's build | `{comparison.mac_build}` |",
        "",
        "## Parse records, by store",
        "",
        "| Store | | Sources | Parsed | Unsupported | Failed | Cards | Occurrence rows | Source records "
        "| Occurrence records |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for slug in sorted(comparison.cloud):
        cloud, mac = comparison.cloud[slug], comparison.mac.get(slug)
        lines.append(_records_row(slug, "cloud", cloud, None))
        if mac is not None:
            lines.append(_records_row(slug, "Mac", mac, cloud))
    lines += [
        "",
        "## The index",
        "",
        "| | Cloud | Mac |",
        "|---|---:|---:|",
        f"| Index id | `{comparison.cloud_index.get('index_id')}` "
        f"| `{comparison.mac_index.get('index_id')}` |",
        *(f"| {name} | {cloud_counts.get(name)} | {mac_counts.get(name)} |" for name in INDEX_COUNTS),
        *(
            f"| documents, {slug} | {_by_store(cloud_counts, slug)} | {_by_store(mac_counts, slug)} |"
            for slug in sorted(comparison.cloud)
        ),
        f"| Suppression list applied | {_entries(comparison.cloud_index)} entries | "
        f"{_entries(comparison.mac_index)} entries, "
        f"{'the same' if same_suppression else 'another'} |",
        "",
        "## Where they differ",
        "",
        *([f"* {difference}" for difference in differences] or ["Nowhere."]),
        "",
    ]
    return "\n".join(lines)


def _records_row(slug: str, side: str, records: RecordsOf, against: RecordsOf | None) -> str:
    sources = occurrences = ""
    if against is not None:
        sources = "the same" if records.sources_sha256 == against.sources_sha256 else "**differ**"
        occurrences = "the same" if records.occurrences_sha256 == against.occurrences_sha256 else "**differ**"
    return (
        f"| {slug} | {side} | {records.sources} | {records.outcomes['PARSED']} | "
        f"{records.outcomes['UNSUPPORTED']} | {records.outcomes['FAILED']} | {records.cards} | "
        f"{records.occurrence_rows} | {sources} | {occurrences} |"
    )


def _by_store(counts: dict[str, object], slug: str) -> object:
    by_store = counts.get("documents_by_store")
    return by_store.get(slug) if isinstance(by_store, dict) else None


def _entries(manifest: dict[str, object]) -> object:
    suppression = manifest.get("suppression")
    return suppression.get("entries") if isinstance(suppression, dict) else None


# ------------------------------------------------------------------------------------------------
# The command line
# ------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare a dev cloud run with the Mac's reproduction of it.")
    parser.add_argument(
        "--run-id", required=True, help="The cloud run's id, as `caselist runs --remote` gives it."
    )
    parser.add_argument("--scratch", required=True, type=Path, help="A new directory for the restored copy.")
    parser.add_argument("--record", type=Path, help="Where to write the record for docs/data/.")
    parser.add_argument("--debate-research", type=Path, help="The installed build. Default: the one on PATH.")
    arguments = parser.parse_args(argv)

    found = arguments.debate_research or (Path(shutil.which("debate-research") or ""))
    if not RUN_ID.match(arguments.run_id):
        print(f"compare: STOP: {arguments.run_id!r} is not a run id (YYYYMMDDTHHMMSSZ)")
        return 2
    if not found.name or not found.is_file():
        print("compare: STOP: no installed debate-research; give --debate-research")
        return 2
    try:
        comparison = compare(found, arguments.run_id, arguments.scratch.expanduser())
    except ComparisonStopped as stopped:
        print(f"compare: STOP: {stopped}")
        return 2
    written = report(comparison, today=datetime.now(UTC).date().isoformat())
    print(written)
    if arguments.record is not None:
        arguments.record.write_text(written, encoding="utf-8")
    differences = comparison.differences()
    print(f"compare: {'AGREE' if not differences else 'DIFFER'}: {len(differences)} difference(s)")
    return 0 if not differences else 1


if __name__ == "__main__":
    sys.exit(main())
