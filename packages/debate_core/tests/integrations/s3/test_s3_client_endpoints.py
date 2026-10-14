"""Where the S3 and STS clients send their requests (`v1-e01-t21`).

The composition root passes an endpoint only when `storage.s3.endpoint_url` names one, which only a
dev installation accepts (`debate_core.application.settings`). It also decides whether the endpoints
botocore configures for itself count: `AWS_ENDPOINT_URL`, `AWS_ENDPOINT_URL_S3`,
`AWS_ENDPOINT_URL_STS` and an `endpoint_url` in the AWS config. A prod installation ignores all of
them, so that no endpoint override reaches prod by a route this project does not control.

No request is made here: a client's endpoint is fixed when it is built, and read from it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from debate_core.integrations.s3 import build_s3_client, build_sts_client

STAND_IN = "http://127.0.0.1:50123"
#: What botocore's own configuration would point the clients at, if it were honoured.
CONFIGURED = "http://127.0.0.1:50999"
#: AWS's endpoints in us-east-1, by hand: botocore asks STS for the regional one by default.
AWS_S3 = "https://s3.amazonaws.com"
AWS_STS = "https://sts.us-east-1.amazonaws.com"


@pytest.fixture
def botocores_own_endpoints(
    fake_aws_credentials: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every route botocore offers for an endpoint override, all pointing at `CONFIGURED`."""
    config = tmp_path / "an-aws-config-written-for-this-test"
    config.write_text(
        f"[profile debate-prod-evidence]\nregion = us-east-1\nendpoint_url = {CONFIGURED}\n", encoding="utf-8"
    )
    monkeypatch.setenv("AWS_CONFIG_FILE", str(config))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials-file"))
    for variable in ("AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3", "AWS_ENDPOINT_URL_STS"):
        monkeypatch.setenv(variable, CONFIGURED)


def endpoints(
    *, endpoint_url: str | None = None, ignore_configured_endpoints: bool = False
) -> tuple[str, str]:
    s3 = build_s3_client(
        region="us-east-1",
        endpoint_url=endpoint_url,
        ignore_configured_endpoints=ignore_configured_endpoints,
    )
    sts = build_sts_client(
        region="us-east-1",
        endpoint_url=endpoint_url,
        ignore_configured_endpoints=ignore_configured_endpoints,
    )
    return s3.meta.endpoint_url, sts.meta.endpoint_url


def test_a_named_endpoint_is_where_both_clients_go(fake_aws_credentials: None) -> None:
    assert endpoints(endpoint_url=STAND_IN) == (STAND_IN, STAND_IN)


def test_without_one_the_clients_go_to_aws(
    fake_aws_credentials: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    for variable in ("AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3", "AWS_ENDPOINT_URL_STS"):
        monkeypatch.delenv(variable, raising=False)

    assert endpoints() == (AWS_S3, AWS_STS)


def test_ignoring_configured_endpoints_ignores_every_route_botocore_offers(
    botocores_own_endpoints: None,
) -> None:
    """What a prod installation builds: the variables and the config's `endpoint_url` count for nothing."""
    assert endpoints(ignore_configured_endpoints=True) == (AWS_S3, AWS_STS)


def test_a_profile_whose_config_names_an_endpoint_is_ignored_too(botocores_own_endpoints: None) -> None:
    s3 = build_s3_client(region="us-east-1", profile="debate-prod-evidence", ignore_configured_endpoints=True)

    assert s3.meta.endpoint_url == AWS_S3


def test_honouring_them_is_what_dev_and_test_still_do(botocores_own_endpoints: None) -> None:
    """Unchanged from before `v1-e01-t21`, which tests that point a run at a dead port rely on."""
    assert endpoints() == (CONFIGURED, CONFIGURED)


def test_a_named_endpoint_wins_over_botocores_own(botocores_own_endpoints: None) -> None:
    assert endpoints(endpoint_url=STAND_IN) == (STAND_IN, STAND_IN)
