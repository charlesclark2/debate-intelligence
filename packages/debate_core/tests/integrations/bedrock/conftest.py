"""Fake AWS credentials, so the Bedrock router's tests cannot reach a real account.

Defined in `tests/fixtures/moto_evidence_bucket.py` and imported here rather than at the package
root, so only the tests beneath this directory are beneath them (`v1-e01-t30`). `__all__` lists them
because pytest finds a fixture by its name in this module: they are imported to be found here.
"""

from __future__ import annotations

from tests.fixtures.moto_evidence_bucket import aws_region, fake_aws_credentials

__all__ = ["aws_region", "fake_aws_credentials"]
