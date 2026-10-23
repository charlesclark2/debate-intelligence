"""Fake AWS credentials, so the Bedrock router's tests cannot reach a real account.

Defined in `tests/fixtures/moto_evidence_bucket.py` and imported here rather than at the package
root, so only the tests beneath this directory are beneath them (`v1-e01-t30`). Each is imported as
itself, the explicit re-export: pytest finds a fixture by its name in this module.
"""

from __future__ import annotations

from tests.fixtures.moto_evidence_bucket import aws_region as aws_region
from tests.fixtures.moto_evidence_bucket import fake_aws_credentials as fake_aws_credentials
