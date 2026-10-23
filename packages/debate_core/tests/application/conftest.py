"""The moto evidence bucket, for the application tests that publish to one or read from one.

Defined in `tests/fixtures/moto_evidence_bucket.py` and imported here rather than at the package
root, so only the tests beneath this directory are beneath them (`v1-e01-t30`). `__all__` lists them
because pytest finds a fixture by its name in this module: they are imported to be found here.
"""

from __future__ import annotations

from tests.fixtures.moto_evidence_bucket import (
    aws_region,
    evidence_bucket,
    evidence_bucket_name,
    fake_aws_credentials,
    s3_client,
)

__all__ = ["aws_region", "evidence_bucket", "evidence_bucket_name", "fake_aws_credentials", "s3_client"]
