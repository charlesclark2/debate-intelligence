"""`debate-research caselist parse --publish-only --dry-run`, through the real application, on moto.

`v1-e31-t40`. The installation of `test_caselist_parse_publish_only.py`: dev and prod profiles
naming two versioned moto buckets over one data directory, as the operator publishes prod from a
copy of dev's store. What each test holds the dry run to:

* a clean dry run's counts are what the real `--publish-only` that follows uploads and skips;
* every check `--publish-only` makes is made, and refused alike: the same code, message, hint,
  details and exit code. The directory whole, written by this build's parser and fingerprint
  versions, its aggregates naming nothing the target's suppression list stops or holds, and
  `--publish`'s environment guard; `--confirm-prod` alone is the real publish's;
* it writes nothing: no version of any object in either bucket, and no file or directory in the
  data directory, byte for byte and by modification time;
* its text and its `--json` give the same figures, and the `--json` keys are pinned whole.

The counts of each kind are written by hand from the fixture's table (`build_parse_world.py`): six
sources through 09-08, each with a per-source file, three aggregates and one placement state. The
bytes are measured on disk here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from tests.fixtures.caselist.publish_expectations import FICTIONAL_IDENTIFIERS
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS, digest_of
from typer.testing import Result

from debate_cli.exit_codes import ExitCode
from debate_core.application.caselist.suppression import PATH_HOLDS_KEY, SUPPRESSION_LIST_KEY
from debate_core.application.ports.suppression import (
    PathHoldEntry,
    ReasonCode,
    SuppressionAction,
    SuppressionEntry,
    disclosure_digest,
)
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION

from .test_caselist_parse_publish_only import DEV_BUCKET, PROD_BUCKET, RECORDED, REMOVED, envelope_of, invoke, plant
from .test_caselist_parse_publish_only import buckets as buckets  # noqa: F401 - a fixture
from .test_caselist_parse_publish_only import imported as imported  # noqa: F401 - a fixture
from .test_caselist_parse_publish_only import installation as installation  # noqa: F401 - an autouse fixture
from .test_caselist_parse_publish_only import published_to_dev as published_to_dev  # noqa: F401 - a fixture

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

SOURCES_THROUGH_0908: Final = 6
AGGREGATES_OF_A_WEEKLY_STORE: Final = 3
KINDS: Final = ("per_source_files", "aggregates", "placement_state")
ACTIONS: Final = ("upload", "present", "suppressed", "blocked")
PREFIX: Final = f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}/"


def dry_run(*extra: str) -> Result:
    return invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish-only", "--dry-run", *extra)


def publish_only(*extra: str) -> Result:
    return invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish-only", *extra)


def parse_here() -> None:
    """`caselist parse` with nothing published: the directory a copy restored would hold."""
    assert invoke("--json", "caselist", "parse", "--caselist", CASELIST).exit_code == ExitCode.OK


def every_version(client: S3Client) -> dict[str, list[tuple[str, str, str]]]:
    """Every version and delete marker in both buckets: any write, even of the same bytes, adds one."""
    found: dict[str, list[tuple[str, str, str]]] = {}
    for bucket in (DEV_BUCKET, PROD_BUCKET):
        listed = client.list_object_versions(Bucket=bucket)
        found[bucket] = sorted(
            (str(one.get("Key")), str(one.get("VersionId")), str(one.get("ETag", "marker")))
            for one in [*listed.get("Versions", []), *listed.get("DeleteMarkers", [])]
        )
    return found


def every_path(data_dir: Path) -> dict[str, tuple[bytes, int]]:
    """Every file and directory of the data directory, with its bytes and modification time."""
    return {
        path.relative_to(data_dir).as_posix(): (
            path.read_bytes() if path.is_file() else b"<directory>",
            path.stat().st_mtime_ns,
        )
        for path in sorted(data_dir.rglob("*"))
    }


def on_disk(data_dir: Path) -> dict[str, int]:
    root = data_dir / "parsed" / CASELIST / DOCX_PARSER_VERSION
    return {
        PREFIX + path.relative_to(root).as_posix(): path.stat().st_size
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def kind_by_hand(key: str) -> str:
    if key.removeprefix(PREFIX).startswith("sha256/"):
        return "per_source_files"
    return "placement_state" if key.endswith("/placement-state.sqlite") else "aggregates"


def bytes_by_kind(data_dir: Path) -> dict[str, int]:
    sizes = on_disk(data_dir)
    return {kind: sum(size for key, size in sizes.items() if kind_by_hand(key) == kind) for kind in KINDS}


def nothing(**but: int) -> dict[str, int]:
    return {action: but.get(action, 0) for action in ACTIONS}


# ------------------------------------------------------------------------------------------------
# A clean dry run, then the publish it plans
# ------------------------------------------------------------------------------------------------


def test_a_dry_run_to_an_empty_bucket_plans_the_whole_directory_writes_nothing_and_the_publish_uploads_it(
    imported: Path, buckets: S3Client
) -> None:
    parse_here()
    versions, paths = every_version(buckets), every_path(imported)
    sizes = bytes_by_kind(imported)

    result = dry_run()

    assert result.exit_code == ExitCode.OK, result.stdout
    assert every_version(buckets) == versions
    assert every_path(imported) == paths
    plan = envelope_of(result)["data"]["plan"]
    assert plan["by_kind"] == {
        "per_source_files": {
            "objects": nothing(upload=SOURCES_THROUGH_0908),
            "bytes": nothing(upload=sizes["per_source_files"]),
        },
        "aggregates": {
            "objects": nothing(upload=AGGREGATES_OF_A_WEEKLY_STORE),
            "bytes": nothing(upload=sizes["aggregates"]),
        },
        "placement_state": {"objects": nothing(upload=1), "bytes": nothing(upload=sizes["placement_state"])},
    }
    assert plan["objects"] == nothing(upload=SOURCES_THROUGH_0908 + AGGREGATES_OF_A_WEEKLY_STORE + 1)
    assert plan["bytes"] == nothing(upload=sum(sizes.values()))
    assert (plan["bucket"], plan["prefix"], plan["aggregates"]) == (DEV_BUCKET, PREFIX, "planned")
    assert (plan["blocked_keys"], plan["blocked_codes"]) == ([], [])

    published = publish_only()

    assert published.exit_code == ExitCode.OK, published.stdout
    counts = envelope_of(published)["data"]["publish"]["counts"]
    assert (counts["uploaded"], counts["skipped"], counts["suppressed"], counts["failed"]) == (
        plan["objects"]["upload"],
        plan["objects"]["present"],
        plan["objects"]["suppressed"],
        plan["objects"]["blocked"],
    )


def test_a_dry_run_to_prod_needs_no_confirmation_and_plans_what_publish_only_then_sends(
    imported: Path, buckets: S3Client, published_to_dev: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "prod")
    versions, paths = every_version(buckets), every_path(imported)

    result = dry_run()

    assert result.exit_code == ExitCode.OK, result.stdout
    assert every_version(buckets) == versions
    assert every_path(imported) == paths
    data = envelope_of(result)["data"]
    assert data["plan"]["bucket"] == PROD_BUCKET
    assert data["plan"]["objects"] == nothing(upload=published_to_dev["counts"]["uploaded"])

    published = publish_only("--confirm-prod")

    assert published.exit_code == ExitCode.OK, published.stdout
    counts = envelope_of(published)["data"]["publish"]["counts"]
    assert (counts["uploaded"], counts["skipped"]) == (data["plan"]["objects"]["upload"], 0)


def test_a_dry_run_over_a_bucket_missing_two_files_plans_those_and_the_rest_present(
    imported: Path, buckets: S3Client, published_to_dev: dict[str, Any]
) -> None:
    lost = [f"{PREFIX}occurrences.jsonl", next(key for key in on_disk(imported) if digest_of("verbatim") in key)]
    for key in lost:
        buckets.delete_object(Bucket=DEV_BUCKET, Key=key)
    sizes = on_disk(imported)
    versions = every_version(buckets)

    result = dry_run()

    assert result.exit_code == ExitCode.OK, result.stdout
    assert every_version(buckets) == versions
    plan = envelope_of(result)["data"]["plan"]
    whole = SOURCES_THROUGH_0908 + AGGREGATES_OF_A_WEEKLY_STORE + 1
    assert plan["objects"] == nothing(upload=2, present=whole - 2)
    assert plan["bytes"] == nothing(
        upload=sum(sizes[key] for key in lost), present=sum(size for key, size in sizes.items() if key not in lost)
    )
    assert plan["by_kind"]["per_source_files"]["objects"] == nothing(upload=1, present=SOURCES_THROUGH_0908 - 1)

    counts = envelope_of(publish_only())["data"]["publish"]["counts"]
    assert (counts["uploaded"], counts["skipped"]) == (2, whole - 2)


def test_the_dry_runs_json_keys_are_pinned_whole(imported: Path, buckets: S3Client) -> None:
    parse_here()

    data = envelope_of(dry_run())["data"]

    assert set(data) == {
        "environment",
        "caselist",
        "version",
        "publish_only",
        "dry_run",
        "fingerprint_version",
        "plan",
    }
    assert (data["environment"], data["caselist"], data["version"]) == ("dev", CASELIST, DOCX_PARSER_VERSION)
    assert (data["publish_only"], data["dry_run"]) == (True, True)
    assert set(data["plan"]) == {
        "bucket",
        "prefix",
        "objects",
        "bytes",
        "by_kind",
        "aggregates",
        "blocked_keys",
        "blocked_codes",
    }
    assert set(data["plan"]["by_kind"]) == set(KINDS)
    for figures in (data["plan"], *data["plan"]["by_kind"].values()):
        assert set(figures["objects"]) == set(figures["bytes"]) == set(ACTIONS)


def figures_in(text: str) -> dict[str, dict[str, tuple[int, int]]]:
    """The table's rows, as `<row>: upload N (B bytes); present ...`."""
    flat = " ".join(text.replace("│", " ").split())
    found: dict[str, dict[str, tuple[int, int]]] = {}
    for row in ("Per-source files", "Aggregates", "Placement state", "Total"):
        match = re.search(
            rf"{row} "
            + "; ".join(rf"{action} (\d+) \((\d+) bytes\)" for action in ACTIONS),
            flat,
        )
        assert match is not None, f"no {row} row in {flat!r}"
        numbers = [int(number) for number in match.groups()]
        found[row] = {action: (numbers[2 * at], numbers[2 * at + 1]) for at, action in enumerate(ACTIONS)}
    return found


def test_the_table_and_the_json_give_the_same_figures_and_name_no_school_team_or_path(
    imported: Path, buckets: S3Client, published_to_dev: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    buckets.delete_object(Bucket=DEV_BUCKET, Key=f"{PREFIX}index.jsonl")
    monkeypatch.setenv("COLUMNS", "200")
    plan = envelope_of(dry_run())["data"]["plan"]

    table = invoke("caselist", "parse", "--caselist", CASELIST, "--publish-only", "--dry-run")

    assert table.exit_code == ExitCode.OK, table.output
    figures = figures_in(table.output)
    for row, figured in (
        ("Per-source files", plan["by_kind"]["per_source_files"]),
        ("Aggregates", plan["by_kind"]["aggregates"]),
        ("Placement state", plan["by_kind"]["placement_state"]),
        ("Total", plan),
    ):
        assert figures[row] == {
            action: (figured["objects"][action], figured["bytes"][action]) for action in ACTIONS
        }, row
    assert figures["Total"]["upload"][0] == 1
    flat = " ".join(table.output.split())
    assert "Dry run: nothing was uploaded or written" in flat
    assert f"{DEV_BUCKET}/{PREFIX}" in flat
    for identifier in (*FICTIONAL_IDENTIFIERS, str(imported)):
        assert identifier not in table.output


def test_a_file_the_bucket_holds_with_other_bytes_is_named_and_the_dry_run_fails_as_blocked(
    imported: Path, buckets: S3Client
) -> None:
    """What the publish would fail on, and why the aggregates would be withheld, before anything is sent."""
    parse_here()
    [wiki] = [key for key in on_disk(imported) if digest_of("wiki") in key]
    buckets.put_object(Bucket=DEV_BUCKET, Key=wiki, Body=b"other bytes under the same key\n")
    versions, paths = every_version(buckets), every_path(imported)

    result = dry_run()

    assert result.exit_code == ExitCode.DOMAIN_FAILURE, result.stdout
    assert every_version(buckets) == versions
    assert every_path(imported) == paths
    error = envelope_of(result)["error"]
    assert error["code"] == "PARSED_PUBLISH_BLOCKED"
    plan = error["details"]["plan"]
    assert (plan["blocked_keys"], plan["blocked_codes"], plan["aggregates"]) == (
        [wiki],
        ["CHECKSUM_MISMATCH"],
        "withheld",
    )
    assert plan["objects"] == nothing(upload=SOURCES_THROUGH_0908 - 1, blocked=1)
    assert error["hint"] == "Nothing was uploaded. A checksum mismatch in the bucket needs a person."


# ------------------------------------------------------------------------------------------------
# Every check `--publish-only` makes, refused alike
# ------------------------------------------------------------------------------------------------


def directory_of(data_dir: Path) -> Path:
    return data_dir / "parsed" / CASELIST / DOCX_PARSER_VERSION


def never_parsed(data_dir: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    return ()


def aggregates_removed(data_dir: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    parse_here()
    for name in ("index.jsonl", "failures.jsonl", "occurrences.jsonl"):
        (directory_of(data_dir) / name).unlink()
    return ()


def a_source_file_lost(data_dir: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch) -> tuple[str, ...]:
    parse_here()
    next((directory_of(data_dir) / "sha256").rglob(f"{digest_of('cardmirror')}.jsonl")).unlink()
    return ()


def parsed_under_another_profile(
    data_dir: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, ...]:
    parse_here()
    path = next((directory_of(data_dir) / "sha256").rglob(f"{digest_of('wiki')}.jsonl"))
    entry, *rest = path.read_text(encoding="utf-8").splitlines(keepends=True)
    path.write_text(json.dumps({**json.loads(entry), "profile_version": "2026.10.01-verbatim-2"}) + "\n" + "".join(rest))
    return ()


def occurrences_stamped_by_another_build(
    data_dir: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, ...]:
    parse_here()
    path = directory_of(data_dir) / "occurrences.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    path.write_text("".join(json.dumps({**row, "fingerprint_version": "card-fingerprint-v1"}) + "\n" for row in rows))
    return ()


def a_removal_only_prods_list_holds(
    data_dir: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, ...]:
    assert invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish").exit_code == ExitCode.OK
    removal = SuppressionEntry(
        action=SuppressionAction.SUPPRESS,
        sha256=digest_of("wiki"),
        recorded_at=RECORDED,
        reason=ReasonCode.POLICY,
        request_id="RM-2026-91",
    )
    plant(client, SUPPRESSION_LIST_KEY, removal.to_line())
    monkeypatch.setenv("DEBATE_ENV", "prod")
    return ("--confirm-prod",)


def a_path_hold_only_prods_list_holds(
    data_dir: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, ...]:
    assert invoke("--json", "caselist", "parse", "--caselist", CASELIST, "--publish").exit_code == ExitCode.OK
    held_path = next(path for path, body in WEEKS[1].members if body == "cardmirror")
    for key, line in (
        (
            SUPPRESSION_LIST_KEY,
            SuppressionEntry(
                action=SuppressionAction.SUPPRESS,
                sha256=REMOVED,
                recorded_at=RECORDED,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-72",
            ).to_line(),
        ),
        (
            PATH_HOLDS_KEY,
            PathHoldEntry(
                caselist=CASELIST,
                disclosure=disclosure_digest(CASELIST, held_path),
                sha256=REMOVED,
                after_snapshot=WEEKS[0].snapshot,
                recorded_at=RECORDED,
                reason=ReasonCode.REQUESTED_BY_TEAM,
                request_id="RM-2026-72",
            ).to_line(),
        ),
    ):
        plant(client, key, line)
    monkeypatch.setenv("DEBATE_ENV", "prod")
    return ("--confirm-prod",)


def from_the_test_environment(
    data_dir: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, ...]:
    parse_here()
    monkeypatch.setenv("DEBATE_ENV", "test")
    return ()


REFUSALS: Final = {
    "PARSED_VERSION_DIRECTORY_MISSING": never_parsed,
    "PARSED_AGGREGATES_MISSING": aggregates_removed,
    "PARSED_SOURCE_FILES_MISSING": a_source_file_lost,
    "PARSED_BY_ANOTHER_PARSER_VERSION": parsed_under_another_profile,
    "PARSED_FINGERPRINT_VERSION_MISMATCH": occurrences_stamped_by_another_build,
    "PARSED_AGGREGATES_NAME_WHAT_THE_LIST_STOPS": a_removal_only_prods_list_holds,
    "PARSED_AGGREGATES_NAME_WHAT_THE_LIST_STOPS-path-hold": a_path_hold_only_prods_list_holds,
    "ENVIRONMENT_NOT_SYNCABLE": from_the_test_environment,
}
"""Each refusal `--publish-only` makes, by its code, and the setup that earns it. The first three are
the directory not whole, the next two not this build's versions, then the target's list, then
`--publish`'s environment guard."""


@pytest.mark.parametrize("refusal", sorted(REFUSALS))
def test_each_refusal_of_publish_only_refuses_the_dry_run_alike_and_neither_writes(
    imported: Path, buckets: S3Client, monkeypatch: pytest.MonkeyPatch, refusal: str
) -> None:
    confirmation = REFUSALS[refusal](imported, buckets, monkeypatch)
    versions, paths = every_version(buckets), every_path(imported)

    refused = dry_run()

    assert every_version(buckets) == versions
    assert every_path(imported) == paths
    real = publish_only(*confirmation)
    assert every_version(buckets) == versions
    assert refused.exit_code == real.exit_code == ExitCode.DOMAIN_FAILURE, refused.stdout
    error = envelope_of(refused)["error"]
    assert error == envelope_of(real)["error"]
    assert error["code"] == refusal.removesuffix("-path-hold")
    for identifier in (*FICTIONAL_IDENTIFIERS, str(imported)):
        assert identifier not in refused.stdout


@pytest.mark.parametrize(
    "beside",
    [("--publish",), ("--reparse",), ("--snapshot", "2026-09-01"), ("--failures",)],
    ids=["publish", "reparse", "snapshot", "failures"],
)
def test_the_dry_run_is_refused_beside_what_publish_only_refuses(
    imported: Path, buckets: S3Client, beside: tuple[str, ...]
) -> None:
    result = dry_run(*beside)

    assert result.exit_code == ExitCode.USAGE_ERROR, result.stdout
    assert f"so it cannot be combined with {beside[0]}" in envelope_of(result)["error"]["message"]
    assert not (imported / "parsed").exists()
