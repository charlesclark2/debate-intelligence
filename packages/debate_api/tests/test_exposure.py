"""Exposure: nothing the pilot answers is cached, and the plan checks the gate rests on exist (`v1-e39-t07`).

The data-use policy's E39 gate item 3 has two halves.

* **What the app sends.** Every response to a signed-in browser says `Cache-Control: private,
  no-store` (ADR-0019 (a) 5), on every route, every method, every status: the 404 of a card that is
  gone and the 503 of an unwritten audit record as much as a results page. Only the two
  content-hashed files under `/static/` say anything else, and they hold no data.
* **What the plan builds.** The buckets' Block Public Access, the bucket policy that grants nobody,
  CloudFront's one origin and no access log, and the function's read-only role are proven by
  `terraform test` runs (`infrastructure/modules/*/tests`, run by CI's `terraform-checks` job under
  a mocked provider). This file holds the names of the runs the report's gate table cites, so a run
  renamed or removed fails here as well as there.

What a deployed environment answers is the operator's record (the session report's operator block),
not a test: no test reaches a network.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Final

import pytest

from debate_api.app import PRIVATE_NO_STORE
from debate_api.pages import IMMUTABLE
from debate_api.routes import ROUTE_ACCESS

REPOSITORY: Final = Path(__file__).resolve().parents[3]
FEATURED: Final = f"/cards/hsld26/{1:064x}"

CONCRETE_PATHS: Final = {
    "/healthz": ["/healthz"],
    "/static/{digest}/{name}": ["/static/0000000000000000/app.js"],
    "/auth/callback": ["/auth/callback", "/auth/callback?state=x&code=y"],
    "/signed-out": ["/signed-out"],
    "/auth/sign-out": ["/auth/sign-out"],
    "/account/authenticator": ["/account/authenticator"],
    "/": ["/"],
    "/search": ["/search", "/search?q=zephyr", "/search?q=zephyr&event=Debate", "/search?q=zephyr&cursor=x"],
    "/cards/{caselist}/{cluster_id}": [FEATURED, f"/cards/hsld26/{999:064x}", "/cards/hsld26/not-a-cluster"],
    "/cards/{caselist}/{cluster_id}/copy": [FEATURED + "/copy", f"/cards/hsld26/{999:064x}/copy"],
    "/download": ["/download"],
    "/account": ["/account"],
    "/account/email": ["/account/email"],
    "/account/email/verify": ["/account/email/verify"],
    "/account/email/remove": ["/account/email/remove"],
    "/landscape": ["/landscape"],
    "/landscape/{caselist}": ["/landscape/synthpolicy26", "/landscape/nocaselist26"],
    "/landscape/{caselist}/report/{part}": [
        "/landscape/synthpolicy26/report/negative",
        "/landscape/synthpolicy26/report/no-such-part",
    ],
    "/landscape/{caselist}/schools": ["/landscape/synthpolicy26/schools", "/landscape/synthld26/schools"],
    "/landscape/{caselist}/schools/{school}": [
        "/landscape/synthpolicy26/schools/ashgrove",
        "/landscape/synthpolicy26/schools/oldfield",
    ],
    "/landscape/{caselist}/positions/{position_id}": [
        "/landscape/synthpolicy26/positions/invented-da",
        "/landscape/synthpolicy26/positions/no-such-position",
    ],
    "/coach": ["/coach"],
}
"""At least one real path for every route in `ROUTE_ACCESS`, including the ones that answer an error."""

PLAN_CHECKS: Final = {
    "infrastructure/modules/evidence_search/tests/evidence_search.tftest.hcl": [
        "evidence_bucket_keeps_block_public_access_and_grants_cloudfront_nothing",
        "cloudfront_reaches_the_function_url_and_nothing_else",
        "distribution_sends_the_security_headers_and_caches_nothing",
        "function_role_is_the_adr_role_table_entry_by_entry",
        "function_role_has_no_other_grant",
        "audit_log_keeps_four_hundred_days_and_the_app_log_thirty",
    ],
    "infrastructure/modules/evidence_bucket/tests/evidence_bucket.tftest.hcl": [
        "bucket_is_private_versioned_and_kms_encrypted",
        "bucket_policy_requires_tls_and_this_key",
        "removal_permission_set_deletes_disclosed_material_and_nothing_else",
        "operator_permission_set_reads_and_publishes_but_cannot_delete",
    ],
}
"""The Terraform runs the session report's gate table (ac5) cites, for gate item 3 and the removal grant."""


@pytest.fixture
def world(every_surface_world: Any) -> Any:
    """This file's world: every surface at once (`v1-e39-t20`)."""
    return every_surface_world


def test_exposure_every_route_has_a_path_here() -> None:
    assert set(CONCRETE_PATHS) == set(ROUTE_ACCESS)


def answers(world: Any, csrf_token: str | None) -> list[tuple[str, str, int, str | None]]:
    """Every route's paths, by GET and by POST, as `(method, path, status, Cache-Control)`."""
    seen = []
    for paths in CONCRETE_PATHS.values():
        for path in paths:
            for method in ("GET", "POST"):
                if method == "GET":
                    response = world.browser.get(path)
                else:
                    response = world.post(
                        path, {"email": "synthetic@example.test", "code": "135790"}, csrf_token=csrf_token
                    )
                seen.append((method, path, response.status_code, response.headers.get("cache-control")))
    return seen


@pytest.mark.parametrize("who", ["student", "coach", "nobody"])
def test_exposure_every_answer_but_a_static_file_is_private_and_never_stored(world: Any, who: str) -> None:
    if who == "student":
        session = world.signed_in_student()
    elif who == "coach":
        world.login.add_account("coach.one", "coach")
        session = world.use_session(world.session_for("coach.one"))
    else:
        session = None

    seen = answers(world, session.csrf_token if session is not None else None)

    statuses = {status for _, _, status, _ in seen}
    assert len(seen) == 2 * sum(len(paths) for paths in CONCRETE_PATHS.values())
    assert statuses >= ({200, 302, 404, 405} if who != "nobody" else {200, 302, 405}), statuses
    wrong = [answer for answer in seen if answer[3] != PRIVATE_NO_STORE]
    assert wrong == [], wrong


def test_exposure_a_503_for_an_unwritten_audit_record_is_private_and_never_stored(world: Any) -> None:
    world.signed_in_student()
    world.audit.failing = True

    page = world.browser.get(FEATURED)
    copy = world.browser.get(FEATURED + "/copy")

    assert (page.status_code, page.headers["cache-control"]) == (503, PRIVATE_NO_STORE)
    assert (copy.status_code, copy.headers["cache-control"]) == (503, PRIVATE_NO_STORE)
    landscape = world.browser.get("/landscape/synthpolicy26")
    assert (landscape.status_code, landscape.headers["cache-control"]) == (503, PRIVATE_NO_STORE)


def test_exposure_only_the_hashed_static_files_may_be_cached_and_they_hold_no_data(world: Any) -> None:
    state = world.app.state.pilot
    for asset in state.static_assets:
        response = world.browser.get(f"/static/{asset.digest}/{asset.name}")
        assert (response.status_code, response.headers["cache-control"]) == (200, IMMUTABLE)
        assert b"zephyr" not in response.content.lower()
        assert b"maple grove" not in response.content.lower()


@pytest.mark.parametrize(("test_file", "runs"), list(PLAN_CHECKS.items()), ids=list(PLAN_CHECKS))
def test_exposure_the_plan_checks_the_gate_table_cites_exist(test_file: str, runs: list[str]) -> None:
    named = set(
        re.findall(r'^run "([a-z_]+)"', (REPOSITORY / test_file).read_text(encoding="utf-8"), re.MULTILINE)
    )

    assert set(runs) <= named, sorted(set(runs) - named)
