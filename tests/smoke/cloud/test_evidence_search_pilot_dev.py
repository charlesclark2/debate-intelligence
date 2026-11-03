"""validate-dev's checks of the student search pilot in dev, through CloudFront, no account (`v1-e39-t10`).

Run by validate-dev's `cloud` job, `pytest tests/smoke/cloud -m "live and dev"`, never in PR CI. Eight
`GET` requests to `https://tub.dev.wfbdebate.com/`, none signed in. What each holds is in
:mod:`tests.smoke.cloud.pilot_checks`. They check what dev serves now, whichever commit the operator
last deployed there, and nothing in them depends on that commit: the asset digests are read from the
page dev serves, and checked against the bytes dev serves. Every answer, in all three, must carry
CloudFront's Content-Security-Policy.

To run them by hand against dev: `uv run pytest tests/smoke/cloud -m "live and dev" -n 0`.
"""

from __future__ import annotations

import httpx
import pytest
from tests.smoke.cloud.pilot_checks import (
    check_health,
    check_pages_need_a_session,
    check_static_assets_are_content_hashed,
)

pytestmark = [pytest.mark.live, pytest.mark.dev]


def test_healthz_answers_ok_and_is_not_cached(pilot: httpx.Client) -> None:
    check_health(pilot)


def test_a_page_without_a_session_is_sent_to_managed_login(pilot: httpx.Client) -> None:
    check_pages_need_a_session(pilot)


def test_the_script_and_stylesheet_are_content_hashed_and_cached_immutably(pilot: httpx.Client) -> None:
    check_static_assets_are_content_hashed(pilot)
