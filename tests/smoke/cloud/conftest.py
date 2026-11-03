"""The cloud smoke checks' one fixture: a plain HTTPS client for the pilot's own origin (`v1-e39-t10`).

Every check here is marked `live` and `dev`, so the default selection (`not slow and not live`), PR
CI's and every validate-dev tier but its cloud one leave it out; tests/smoke's conftest opens the
network only to a check marked `live`. The client holds no cookie, no token and no credential, follows
no redirect, and says who it is.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest
from tests.smoke.cloud.pilot_checks import BASE_URL_VARIABLE, DEV_PILOT_URL


@pytest.fixture
def pilot() -> Iterator[httpx.Client]:
    base_url = os.environ.get(BASE_URL_VARIABLE) or DEV_PILOT_URL
    with httpx.Client(
        base_url=base_url,
        follow_redirects=False,
        timeout=30,
        headers={"User-Agent": "debate-research-validate-dev-cloud-smoke"},
    ) as client:
        yield client
