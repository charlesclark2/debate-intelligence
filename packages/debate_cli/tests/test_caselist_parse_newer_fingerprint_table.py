"""`caselist parse` by hand, with and without `--publish`, over a table a newer build stamped.

`v1-e34-t29`. Through the real application, composition root and process pool, over the fictional
caselist `test_caselist_parse.py` imports. A refusal ends the command as a domain failure (exit
`1`) whose message names both versions and the store, and leaves the table as it was here and in
the bucket. An equal or older stamp parses and publishes as before. Every version is synthetic:
a store is stamped by running the command as a build at another version first.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import pytest
from tests.fixtures.parse_pipeline.build_parse_world import CASELIST, WEEKS, build_week_zips

from debate_cli.exit_codes import ExitCode
from debate_core.application import caselist_parse as caselist_parse_module
from debate_core.application.caselist import occurrence_table_guard
from debate_core.integrations.docx_parser import DOCX_PARSER_VERSION
from debate_core.integrations.s3 import SHA256_METADATA_NAME

from .test_caselist_parse import DEV_BUCKET, envelope_of, invoke
from .test_caselist_parse import buckets as buckets  # noqa: F401 - a fixture
from .test_caselist_parse import imported as imported  # noqa: F401 - a fixture
from .test_caselist_parse import installation as installation  # noqa: F401 - an autouse fixture

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

BUILD: Final = "synthetic-fingerprint-v7"
NEWER: Final = "synthetic-fingerprint-v8"
OLDER: Final = "synthetic-fingerprint-v6"
TABLE: Final = f"parsed/{CASELIST}/{DOCX_PARSER_VERSION}/occurrences.jsonl"


@pytest.fixture
def as_build(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Run as a build at a fingerprint version: what the pipeline stamps, and what the rule compares."""

    def at(version: str) -> None:
        monkeypatch.setattr(caselist_parse_module, "FINGERPRINT_VERSION", version)
        monkeypatch.setattr(occurrence_table_guard, "FINGERPRINT_VERSION", version)

    return at


def parsed_tree(data_dir: Path) -> dict[str, bytes]:
    root = data_dir / "parsed"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def bucket_objects(client: S3Client) -> dict[str, bytes]:
    listed = client.list_objects_v2(Bucket=DEV_BUCKET).get("Contents", [])
    return {
        str(item.get("Key")): client.get_object(Bucket=DEV_BUCKET, Key=str(item.get("Key")))["Body"].read()
        for item in listed
    }


def refusal(store: str) -> str:
    return (
        f"the occurrence table of {CASELIST} {DOCX_PARSER_VERSION} in {store} is stamped {NEWER}, newer "
        f"than this build's {BUILD}; it was left as it was"
    )


def parse(*options: str) -> tuple[int, dict[str, Any]]:
    result = invoke("--json", "caselist", "parse", "--caselist", CASELIST, *options)
    return result.exit_code, envelope_of(result)


def test_a_parse_by_hand_over_a_table_a_newer_build_stamped_exits_one_and_writes_nothing(
    imported: Path, as_build: Callable[[str], None], tmp_path: Path
) -> None:
    as_build(NEWER)
    assert parse()[0] == ExitCode.OK
    week = WEEKS[2]
    zips = build_week_zips(tmp_path / "later")
    imported_week = invoke(
        "--json", "caselist", "import", str(zips[week.snapshot]),
        "--caselist", CASELIST, "--snapshot", week.snapshot.isoformat(),
    )  # fmt: skip
    assert imported_week.exit_code == ExitCode.OK, imported_week.stdout
    before = parsed_tree(imported)
    as_build(BUILD)

    exit_code, envelope = parse()

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "NEWER_FINGERPRINT_TABLE"
    assert envelope["error"]["message"] == refusal("this machine's parsed store")
    assert parsed_tree(imported) == before


def test_a_parse_with_publish_over_a_table_a_newer_build_stamped_sends_nothing(
    imported: Path, as_build: Callable[[str], None], buckets: S3Client
) -> None:
    as_build(NEWER)
    assert parse()[0] == ExitCode.OK
    as_build(BUILD)

    exit_code, envelope = parse("--publish")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["message"] == refusal("this machine's parsed store")
    assert bucket_objects(buckets) == {}


def test_a_parse_with_publish_over_the_buckets_table_a_newer_build_stamped_sends_nothing(
    imported: Path, as_build: Callable[[str], None], buckets: S3Client
) -> None:
    """Another machine at the newer version published the table; this one parses, then is refused."""
    theirs = b"".join(
        json.dumps({"record": "occurrence", "fingerprint_version": NEWER, "row": row}).encode() + b"\n"
        for row in range(3)
    )
    buckets.put_object(
        Bucket=DEV_BUCKET,
        Key=TABLE,
        Body=theirs,
        Metadata={SHA256_METADATA_NAME: hashlib.sha256(theirs).hexdigest()},
    )
    as_build(BUILD)

    exit_code, envelope = parse("--publish")

    assert exit_code == ExitCode.DOMAIN_FAILURE
    assert envelope["error"]["code"] == "NEWER_FINGERPRINT_TABLE"
    assert envelope["error"]["message"] == refusal("the bucket")
    assert bucket_objects(buckets) == {TABLE: theirs}
    assert TABLE.split("/", 1)[1] in parsed_tree(imported), "parsed here as before"


@pytest.mark.parametrize("stamped", [BUILD, OLDER])
def test_a_parse_with_publish_over_an_equal_or_older_table_publishes_as_before(
    imported: Path, as_build: Callable[[str], None], buckets: S3Client, stamped: str
) -> None:
    as_build(stamped)
    assert parse("--publish")[0] == ExitCode.OK
    as_build(BUILD)

    exit_code, envelope = parse("--reparse", "--publish")

    assert exit_code == ExitCode.OK, envelope
    published = bucket_objects(buckets)
    here = parsed_tree(imported)
    assert {key: body for key, body in published.items() if f"{DOCX_PARSER_VERSION}_reparse" in key} == {
        f"parsed/{name}": body for name, body in here.items() if f"{DOCX_PARSER_VERSION}_reparse" in name
    }
