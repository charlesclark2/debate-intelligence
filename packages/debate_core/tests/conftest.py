"""One moto-backed evidence bucket per test, for every test in this package that needs one.

These fixtures are at the root of `packages/debate_core/tests/` rather than beside the S3 adapter's
own tests because two directories ask for the same bucket: the adapter tests in
`tests/integrations/s3/`, and the shared-contract bindings in `tests/contracts/`, where the S3 and
filesystem implementations of one port are held to one suite. Defining them twice would be two
chances to make one of them reach something real.

**Nothing here opens a socket, and nothing here can.** `moto` answers botocore in-process, and the
workspace's pytest configuration passes `--disable-socket`, so a test that somehow escaped moto fails
instead of quietly billing an account (`docs/process/working-agreements.md`). No test in this
repository's PR path touches AWS; a real-bucket check belongs with the CLI that resolves a real
bucket (`v1-e29-t05-evidence-sync-cli`), marked `live` and run on request.

The credentials the fixtures set are the string `"testing"`. botocore refuses to sign a request
without *some* credentials, and setting deliberately fake ones is also what stops a developer's real
SSO session from being picked up by the credential chain by a test that had a bug in it.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

import boto3
import pytest
from moto import mock_aws

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client


@pytest.fixture
def aws_region() -> str:
    """The region every evidence bucket is in (ADR-0010), so the tests use the one the adapters will."""
    return "us-east-1"


@pytest.fixture
def evidence_bucket_name() -> str:
    """Obviously not a real bucket.

    The real names are in `docs/architecture/evidence-store-layout.md` and are read from the
    environment root's `evidence_bucket_name` Terraform output, never typed into code — which is
    exactly why no test may name one.
    """
    return "debate-test-evidence-moto"


@pytest.fixture
def blob_prefix() -> str:
    """Where a test store's content-addressed blobs go.

    A real prefix from the layout document, so the keys a test asserts on are the keys the store will
    really build in the real bucket.
    """
    return "raw/caselist/hsld26"


@pytest.fixture
def fake_aws_credentials(monkeypatch: pytest.MonkeyPatch, aws_region: str) -> None:
    """Fake credentials and no profile, so the credential chain cannot reach a real account.

    `AWS_PROFILE` is unset rather than overridden: an operator running this suite on a laptop with an
    SSO session for `debate-prod-evidence` in the environment must not have it consulted at all.
    """
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": aws_region,
        # Without this, botocore may reach for the instance-metadata endpoint before giving up.
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def s3_client(fake_aws_credentials: None, aws_region: str) -> Iterator[S3Client]:
    """A client onto moto's in-process S3, for the whole of one test."""
    with mock_aws():
        # boto3-stubs types `client` once per AWS service and only for the services whose stub
        # package is installed, so the symbol is partly Unknown to strict mode even though this call
        # resolves to `S3Client`. Narrowed to the one line rather than turned off for the suite.
        yield boto3.client("s3", region_name=aws_region)  # pyright: ignore[reportUnknownMemberType]


@pytest.fixture
def evidence_bucket(s3_client: S3Client, evidence_bucket_name: str) -> str:
    """An empty, versioned bucket, and its name.

    Versioned like the real ones (`v1-e29-t03`), because two of this task's rules are about versions:
    a repeat `put` of identical bytes must leave one version, and a content-addressed key that has two
    is the signal that something went wrong.

    us-east-1 is the one region `CreateBucket` takes no `LocationConstraint` for, which is why there
    is none here; ADR-0010 puts every evidence bucket there.
    """
    s3_client.create_bucket(Bucket=evidence_bucket_name)
    s3_client.put_bucket_versioning(
        Bucket=evidence_bucket_name, VersioningConfiguration={"Status": "Enabled"}
    )
    return evidence_bucket_name
