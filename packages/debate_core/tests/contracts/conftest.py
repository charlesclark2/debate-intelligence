"""Fixtures shared by the contract bindings in this directory.

The SQLite database the three local repository bindings hand out handles onto. It lives under
`tmp_path`, so every test gets an empty store and nothing here can reach a real data directory.

And the moto evidence bucket the S3 binding of the evidence object store runs against, defined in
`tests/fixtures/moto_evidence_bucket.py` and imported here rather than at the package root, so only
the tests beneath this directory are beneath them (`v1-e01-t30`). Each is imported as itself,
the explicit re-export: pytest finds a fixture by its name in this module.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.moto_evidence_bucket import aws_region as aws_region
from tests.fixtures.moto_evidence_bucket import evidence_bucket as evidence_bucket
from tests.fixtures.moto_evidence_bucket import evidence_bucket_name as evidence_bucket_name
from tests.fixtures.moto_evidence_bucket import fake_aws_credentials as fake_aws_credentials
from tests.fixtures.moto_evidence_bucket import s3_client as s3_client

from debate_core.integrations.local import SqliteDatabase


@pytest.fixture
def sqlite_database(tmp_path: Path) -> Iterator[SqliteDatabase]:
    """One migrated, empty database per test, closed afterwards.

    The three SQLite repositories share it, exactly as the composition root wires them: one
    connection, one set of pragmas, one migration run. It is also what makes a repository factory
    able to hand out two handles onto the *same* storage, which the optimistic-concurrency
    contract needs.
    """
    with SqliteDatabase.open(tmp_path) as opened:
        yield opened
