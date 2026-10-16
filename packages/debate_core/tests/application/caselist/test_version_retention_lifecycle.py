"""A retired directory through the bucket's lifecycle, and back again (`v1-e31-t16`, PM ruling 2026-10-16).

The bucket is moto's, its lifecycle configuration is built from the evidence bucket module's own
values (`infrastructure/modules/evidence_bucket/main.tf`), and the rules are run by
:class:`~.lifecycle_simulation.LifecycleSimulation`, written from AWS's documentation. What is held:

* A retired object's current version expires at the first lifecycle run; its noncurrent version
  is kept for the 30-day grace period and then deleted; the delete marker left behind is removed
  the run after. In prod too, where every other noncurrent version is kept 365 days.
* `caselist retire --bucket --restore` before that first run: the object carries
  `debate-retention=restored`, which no rule matches, and it survives every later run.
* After the first run, the copy-back in `docs/runbooks/parsed-store-retention.md`, **read from the
  runbook and run as written**: the `aws s3api list-object-versions` query is applied with
  `jmespath`, the library the AWS CLI applies `--query` with; its `awk` program is run by `awk`; each
  `copy-object` line is sent with exactly the runbook's flags. The directory reads back byte for
  byte, and survives the next runs.
* Every request the copy-back makes is one the everyday permission set grants, as
  `operator_access.tf` writes it: read from that file, not restated here.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jmespath
import pytest

from debate_core.application.caselist.version_retention import VersionDirectoryRetention
from debate_core.application.ports.version_directories import (
    RESTORED_TAG_VALUE,
    RETIREMENT_TAG_KEY,
    RETIREMENT_TAG_VALUE,
)
from debate_core.integrations.s3.version_directories import S3VersionDirectories

from .lifecycle_simulation import LifecycleSimulation

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

REPOSITORY: Final = Path(__file__).parents[5]
MODULE: Final = REPOSITORY / "infrastructure" / "modules" / "evidence_bucket"
RUNBOOK: Final = REPOSITORY / "docs" / "runbooks" / "parsed-store-retention.md"

CASELIST: Final = "testcl26"
RETIRED: Final = "2026.10.10-docx-2"
BUILD: Final = "2026.10.12-docx-3"
#: The bytes each directory holds, written by hand. `index.jsonl` is published twice before the
#: retirement, as a re-run rewrites an aggregate, so the copy-back has two versions to choose from.
FIRST_INDEX: Final = b'{"record":"source","run":1}\n'
FILES: Final = {
    "sha256/ab/cd/abcd01.jsonl": b'{"record":"source"}\n{"record":"document"}\n',
    "occurrences.jsonl": b'{"record":"occurrence"}\n',
    "index.jsonl": b'{"record":"source","run":2}\n',
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ------------------------------------------------------------------------------------------------
# The module's values, read from its source
# ------------------------------------------------------------------------------------------------


def module_local(name: str) -> str:
    found = re.search(
        rf"^\s*{name}\s*=\s*(.+?)\s*$", (MODULE / "main.tf").read_text(encoding="utf-8"), re.MULTILINE
    )
    assert found is not None, f"main.tf no longer defines {name}"
    return found[1]


def lifecycle_rules(noncurrent_days: int) -> list[Any]:
    """The module's rules that reach `parsed/`, in the S3 API's shape, with this environment's window.

    `noncurrent_days` is the general rule's `noncurrent_version_retention_days`: 30 in dev, 365 in
    prod. The two retention rules' values come from `main.tf`.
    """
    prefix = module_local("retired_parsed_prefix").strip('"')
    tag = re.fullmatch(r'\{\s*"([^"]+)"\s*=\s*"([^"]+)"\s*\}', module_local("retired_parsed_tags"))
    assert tag is not None
    grace = int(module_local("retired_parsed_grace_period_days"))
    main = (MODULE / "main.tf").read_text(encoding="utf-8")
    assert re.search(
        r'id\s*=\s*"remove-orphaned-parsed-delete-markers"[^}]*filter\s*\{\s*prefix\s*=\s*local\.retired_parsed_prefix'
        r"\s*\}\s*expiration\s*\{\s*expired_object_delete_marker\s*=\s*true",
        main,
    ), "main.tf no longer has the prefix-only delete-marker rule on parsed/"
    return [
        {"ID": "age-out-superseded-evidence-versions", "Status": "Enabled", "Filter": {"Prefix": ""},
         "NoncurrentVersionExpiration": {"NoncurrentDays": noncurrent_days}},
        {"ID": "expire-retired-parsed-version-directories", "Status": "Enabled",
         "Filter": {"And": {"Prefix": prefix, "Tags": [{"Key": tag[1], "Value": tag[2]}]}},
         "Expiration": {"Days": int(module_local("retired_parsed_expiration_days"))},
         "NoncurrentVersionExpiration": {"NoncurrentDays": grace}},
        {"ID": "remove-orphaned-parsed-delete-markers", "Status": "Enabled", "Filter": {"Prefix": prefix},
         "Expiration": {"ExpiredObjectDeleteMarker": True}},
    ]  # fmt: skip


# ------------------------------------------------------------------------------------------------
# The everyday permission set, read from operator_access.tf
# ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Grant:
    actions: frozenset[str]
    resource: str
    prefixes: tuple[str, ...] | None
    """The `s3:prefix` values a listing grant is conditioned on, or `None` for no condition."""


def quoted_list(text: str, name: str) -> list[str]:
    found = re.search(rf"{name}\s*=\s*\[(.*?)\]", text, re.DOTALL)
    assert found is not None, f"no list {name}"
    return re.findall(r'"([^"]+)"', found[1])


def everyday_grants(bucket: str) -> list[Grant]:
    access = (MODULE / "operator_access.tf").read_text(encoding="utf-8")
    main = (MODULE / "main.tf").read_text(encoding="utf-8")
    policy = access[
        access.index("operator_policy = jsonencode(") : access.index("removal_policy = jsonencode(")
    ]
    conditions = {
        "local.list_prefix_conditions": quoted_list(main, "evidence_prefixes"),
        "local.removable_list_prefix_conditions": quoted_list(access, "removable_prefixes"),
    }
    substitutions = {
        "${aws_s3_bucket.evidence.arn}": f"arn:aws:s3:::{bucket}",
        "${local.retired_parsed_prefix}": module_local("retired_parsed_prefix").strip('"'),
    }
    grants: list[Grant] = []
    for statement in re.split(r"\n\s*\{\s*\n", policy)[1:]:
        actions = re.search(r"Action\s*=\s*(\[.*?\]|\"[^\"]+\")", statement, re.DOTALL)
        resource = re.search(r"Resource\s*=\s*(\S+)", statement)
        if actions is None or resource is None:
            continue
        target = resource[1].strip('"')
        if target == "aws_s3_bucket.evidence.arn":
            target = f"arn:aws:s3:::{bucket}"
        for placeholder, value in substitutions.items():
            target = target.replace(placeholder, value)
        condition = re.search(r'"s3:prefix"\s*=\s*(local\.\w+)', statement)
        prefixes = None
        if condition is not None:
            prefixes = tuple(p for prefix in conditions[condition[1]] for p in (prefix, f"{prefix}*"))
        grants.append(Grant(frozenset(re.findall(r'"((?:s3|kms):\w+)"', actions[1])), target, prefixes))
    assert grants, "found no statements in operator_policy"
    return grants


def granted(grants: list[Grant], action: str, resource: str, prefix: str | None = None) -> bool:
    return any(
        action in grant.actions
        and fnmatch.fnmatchcase(resource, grant.resource)
        and (
            grant.prefixes is None
            or (prefix is not None and any(fnmatch.fnmatchcase(prefix, p) for p in grant.prefixes))
        )
        for grant in grants
    )


def required_grants(operation: str, params: dict[str, Any], bucket: str) -> list[tuple[str, str, str | None]]:
    """What IAM asks of a request, from the S3 authorization reference. An unknown request fails."""
    if operation == "ListObjectVersions":
        return [("s3:ListBucketVersions", f"arn:aws:s3:::{bucket}", params.get("Prefix", ""))]
    if operation == "CopyObject":
        source = str(params["CopySource"])
        source_key = source.split("?", 1)[0]
        destination = f"arn:aws:s3:::{bucket}/{params['Key']}"
        needed: list[tuple[str, str, str | None]] = [
            (
                "s3:GetObjectVersion" if "versionId=" in source else "s3:GetObject",
                f"arn:aws:s3:::{source_key}",
                None,
            ),
            ("s3:PutObject", destination, None),
        ]
        if params.get("Tagging"):
            needed.append(("s3:PutObjectTagging", destination, None))
        return needed
    raise AssertionError(f"the copy-back sent {operation}, which this test does not know the grants of")


# ------------------------------------------------------------------------------------------------
# The runbook's copy-back, read from the runbook and run as written
# ------------------------------------------------------------------------------------------------


def copy_back_blocks() -> tuple[list[str], str]:
    text = RUNBOOK.read_text(encoding="utf-8")
    section = text[text.index("### After the lifecycle has run") :]
    blocks = re.findall(r"```bash\n(.*?)```", section, re.DOTALL)
    listing = [line for line in blocks[0].splitlines() if line.strip()]
    loop = blocks[1].strip()
    return listing, loop


def aws_arguments(tokens: list[str], operation: str, allowed: set[str]) -> dict[str, str]:
    assert tokens[:3] == ["aws", "s3api", operation], tokens[:3]
    flags = dict(zip(tokens[3::2], tokens[4::2], strict=True))
    assert set(flags) <= allowed, (
        f"the runbook's {operation} has a flag this test does not run: {set(flags) - allowed}"
    )
    assert not flags["--profile"].endswith("-removal"), "the copy-back must run as the everyday profile"
    return flags


def run_runbook_copy_back(client: S3Client, bucket: str, prefix: str, work: Path) -> int:
    """The two blocks under "After the lifecycle has run", with this test's bucket and prefix."""
    listing, loop = copy_back_blocks()
    assert listing[0].startswith("BUCKET=") and listing[1].startswith("PREFIX=")
    assert listing[3] == "wc -l restore-versions.txt"
    expanded = listing[2].replace("${BUCKET}", bucket).replace("${PREFIX}", prefix)
    tokens = shlex.split(expanded)
    pipe = tokens.index("|")
    assert tokens[pipe + 1] == "awk" and tokens[pipe + 3 :] == [">", "restore-versions.txt"]
    flags = aws_arguments(
        tokens[:pipe], "list-object-versions", {"--bucket", "--prefix", "--profile", "--query", "--output"}
    )
    assert flags["--output"] == "text"

    merged: dict[str, list[Any]] = {"Versions": [], "DeleteMarkers": []}
    for page in client.get_paginator("list_object_versions").paginate(
        Bucket=flags["--bucket"], Prefix=flags["--prefix"]
    ):
        merged["Versions"] += page.get("Versions", [])
        merged["DeleteMarkers"] += page.get("DeleteMarkers", [])
    rows: list[list[str]] = jmespath.search(flags["--query"], merged) or []  # pyright: ignore[reportUnknownMemberType]
    text = "".join("\t".join(str(cell) for cell in row) + "\n" for row in rows)
    chosen = subprocess.run(
        ["awk", tokens[pipe + 2]], input=text, capture_output=True, text=True, check=True
    ).stdout
    (work / "restore-versions.txt").write_text(chosen, encoding="utf-8")

    shape = re.fullmatch(
        r"while read -r key version; do (aws .+?) > /dev/null; done < restore-versions\.txt", loop
    )
    assert shape is not None, f"the copy-back loop is not the shape this test runs: {loop!r}"
    copied = 0
    for line in chosen.splitlines():
        key, version = line.split("\t")
        command = shape[1].replace("${BUCKET}", bucket).replace("${key}", key).replace("${version}", version)
        copy = aws_arguments(
            shlex.split(command),
            "copy-object",
            {"--bucket", "--key", "--copy-source", "--tagging-directive", "--tagging", "--profile"},
        )
        client.copy_object(
            Bucket=copy["--bucket"],
            Key=copy["--key"],
            CopySource=copy["--copy-source"],
            TaggingDirective=copy["--tagging-directive"],  # pyright: ignore[reportArgumentType]
            Tagging=copy["--tagging"],
        )
        copied += 1
    return copied


# ------------------------------------------------------------------------------------------------
# Fixtures and readings
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def bucket(s3_client: S3Client, evidence_bucket: str) -> Iterator[str]:
    """The retired directory and the current one, as publishing leaves them."""
    for version in (RETIRED, BUILD):
        s3_client.put_object(
            Bucket=evidence_bucket, Key=f"parsed/{CASELIST}/{version}/index.jsonl", Body=FIRST_INDEX
        )
        for name, content in FILES.items():
            s3_client.put_object(
                Bucket=evidence_bucket, Key=f"parsed/{CASELIST}/{version}/{name}", Body=content
            )
    yield evidence_bucket


def lifecycle(s3_client: S3Client, bucket: str, *, noncurrent_days: int) -> LifecycleSimulation:
    s3_client.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={"Rules": lifecycle_rules(noncurrent_days)},  # pyright: ignore[reportArgumentType]
    )
    simulation = LifecycleSimulation(s3_client, bucket)
    simulation.observe(0)
    return simulation


def retention(s3_client: S3Client, bucket: str) -> VersionDirectoryRetention:
    return VersionDirectoryRetention(
        S3VersionDirectories(bucket=bucket, client=s3_client, threads=2), parser_version=BUILD
    )


async def retire(s3_client: S3Client, bucket: str, *, restore: bool = False) -> None:
    service = retention(s3_client, bucket)
    plan = await service.plan(caselists=[CASELIST], versions=[RETIRED], restore=restore)
    await service.execute(plan, confirmation=plan.confirmation)


def current(s3_client: S3Client, bucket: str, version: str) -> dict[str, bytes]:
    """What a reader of the directory gets: the current object at each key."""
    prefix = f"parsed/{CASELIST}/{version}/"
    keys = [
        item.get("Key", "")
        for item in s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
    ]
    return {key[len(prefix) :]: s3_client.get_object(Bucket=bucket, Key=key)["Body"].read() for key in keys}


def tags_of(s3_client: S3Client, bucket: str, version: str) -> set[tuple[str, str]]:
    prefix = f"parsed/{CASELIST}/{version}/"
    keys = [
        item.get("Key", "")
        for item in s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])
    ]
    return {
        (tag["Key"], tag["Value"])
        for key in keys
        for tag in s3_client.get_object_tagging(Bucket=bucket, Key=key)["TagSet"]
    }


# ------------------------------------------------------------------------------------------------
# The grace period
# ------------------------------------------------------------------------------------------------


def held(simulation: LifecycleSimulation, prefix: str) -> list[tuple[str, str]]:
    """Each version under `prefix` by its key's last part and what it is: `tagged`, `untagged` or `marker`."""
    found: list[tuple[str, str]] = []
    for version in simulation.versions(prefix):
        if version.is_delete_marker:
            found.append((version.key.rsplit("/", 1)[1], "marker"))
            continue
        tag_set = simulation.client.get_object_tagging(
            Bucket=simulation.bucket, Key=version.key, VersionId=version.version_id
        )["TagSet"]
        retired = {(tag["Key"], tag["Value"]) for tag in tag_set} == {
            (RETIREMENT_TAG_KEY, RETIREMENT_TAG_VALUE)
        }
        found.append((version.key.rsplit("/", 1)[1], "tagged" if retired else "untagged"))
    return sorted(found)


@pytest.mark.anyio
@pytest.mark.parametrize("noncurrent_days", [30, 365], ids=["dev", "prod"])
async def test_a_retired_directory_expires_at_the_first_run_and_is_gone_after_the_grace_period(
    s3_client: S3Client, bucket: str, noncurrent_days: int
) -> None:
    """Retired on day 0. Written by hand from the rules: the first run (day 1) expires every tagged
    current version, which leaves a marker and makes it noncurrent; day 31 is 30 days after that,
    when the tagged versions go; day 32 removes the markers left alone. The untagged older version of
    `index.jsonl`, noncurrent since before the retirement, follows the general rule: deleted on day
    30 in dev, kept 365 days in prod, and its marker with it. Kept longer, never deleted sooner."""
    simulation = lifecycle(s3_client, bucket, noncurrent_days=noncurrent_days)
    await retire(s3_client, bucket)
    simulation.observe(0)
    prefix = f"parsed/{CASELIST}/{RETIRED}/"
    names = sorted(name.rsplit("/", 1)[-1] for name in FILES)

    simulation.run(1)
    assert current(s3_client, bucket, RETIRED) == {}
    assert held(simulation, prefix) == sorted(
        [(name, "marker") for name in names]
        + [(name, "tagged") for name in names]
        + [("index.jsonl", "untagged")]
    )

    simulation.run(30)
    untagged = [] if noncurrent_days == 30 else [("index.jsonl", "untagged")]
    assert held(simulation, prefix) == sorted(
        [(name, "marker") for name in names] + [(name, "tagged") for name in names] + untagged
    ), "on the last day of the grace period every retired version can still be copied back"

    simulation.run(31)
    assert held(simulation, prefix) == sorted([(name, "marker") for name in names] + untagged)

    simulation.run(32)
    assert held(simulation, prefix) == (
        [] if noncurrent_days == 30 else [("index.jsonl", "marker"), *untagged]
    )
    assert current(s3_client, bucket, BUILD) == FILES, "the current directory is never touched"


@pytest.mark.anyio
async def test_restore_before_the_first_run_leaves_an_object_no_rule_expires(
    s3_client: S3Client, bucket: str
) -> None:
    simulation = lifecycle(s3_client, bucket, noncurrent_days=30)
    await retire(s3_client, bucket)
    await retire(s3_client, bucket, restore=True)
    simulation.observe(0)

    for day in (1, 2, 31, 40):
        simulation.run(day)

    assert current(s3_client, bucket, RETIRED) == FILES
    assert tags_of(s3_client, bucket, RETIRED) == {(RETIREMENT_TAG_KEY, RESTORED_TAG_VALUE)}


# ------------------------------------------------------------------------------------------------
# The copy-back in the runbook
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def requests(s3_client: S3Client) -> list[tuple[str, dict[str, Any]]]:
    sent: list[tuple[str, dict[str, Any]]] = []

    def record(params: dict[str, Any], model: Any, **_: Any) -> None:
        sent.append((model.name, dict(params)))

    s3_client.meta.events.register("before-parameter-build.s3", record)
    return sent


@pytest.mark.anyio
async def test_the_runbook_copy_back_restores_the_directory_byte_for_byte_with_the_everyday_grants(
    s3_client: S3Client, bucket: str, tmp_path: Path, requests: list[tuple[str, dict[str, Any]]]
) -> None:
    simulation = lifecycle(s3_client, bucket, noncurrent_days=30)
    await retire(s3_client, bucket)
    simulation.observe(0)
    simulation.run(1)
    assert current(s3_client, bucket, RETIRED) == {}
    requests.clear()

    copied = run_runbook_copy_back(s3_client, bucket, f"parsed/{CASELIST}/{RETIRED}/", tmp_path)
    sent = list(requests)
    simulation.observe(3)

    assert copied == len(FILES)
    assert current(s3_client, bucket, RETIRED) == FILES, (
        "the newest version of each object comes back, not an older one"
    )
    assert tags_of(s3_client, bucket, RETIRED) == {(RETIREMENT_TAG_KEY, RESTORED_TAG_VALUE)}
    grants = everyday_grants(bucket)
    needed = [need for operation, params in sent for need in required_grants(operation, params, bucket)]
    assert {operation for operation, _ in sent} == {"ListObjectVersions", "CopyObject"}
    assert [need for need in needed if not granted(grants, *need)] == []
    assert not any(action.startswith("s3:Delete") for action, _, _ in needed)

    for day in (4, 33, 40):
        simulation.run(day)
    assert current(s3_client, bucket, RETIRED) == FILES, "a copied-back object survives every later run"


def test_the_grants_reader_refuses_what_the_everyday_set_does_not_hold(evidence_bucket_name: str) -> None:
    """The check above is only as good as this reader, so it is shown refusing."""
    grants = everyday_grants(evidence_bucket_name)
    arn = f"arn:aws:s3:::{evidence_bucket_name}"

    assert granted(grants, "s3:PutObjectTagging", f"{arn}/parsed/{CASELIST}/{RETIRED}/index.jsonl")
    assert granted(grants, "s3:ListBucketVersions", arn, "parsed/testcl26/")
    assert not granted(grants, "s3:PutObjectTagging", f"{arn}/raw/caselist/{CASELIST}/sha256/ab")
    assert not granted(grants, "s3:DeleteObject", f"{arn}/parsed/{CASELIST}/{RETIRED}/index.jsonl")
    assert not granted(grants, "s3:DeleteObjectVersion", f"{arn}/parsed/{CASELIST}/{RETIRED}/index.jsonl")
    assert not granted(grants, "s3:ListBucketVersions", arn, "reports/")
    assert not granted(grants, "s3:ListBucketVersions", arn, None)


def test_the_retirement_tag_is_not_restored() -> None:
    """The lifecycle filter matches one exact pair, so `restored` is out of its reach."""
    assert (RETIREMENT_TAG_KEY, RETIREMENT_TAG_VALUE) != (RETIREMENT_TAG_KEY, RESTORED_TAG_VALUE)
    assert module_local("retired_parsed_tags") == f'{{ "{RETIREMENT_TAG_KEY}" = "{RETIREMENT_TAG_VALUE}" }}'
