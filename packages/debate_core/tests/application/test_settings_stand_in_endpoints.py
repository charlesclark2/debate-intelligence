"""The endpoints a smoke check's stand-ins are reached through, and the environments that refuse them.

`v1-e01-t21` runs the storage and OpenCaselist smoke checks against an installed build, which
reaches moto in server mode and a local OpenCaselist stand-in over loopback. It is pointed at them
by two settings: `storage.s3.endpoint_url`, added for this, and the existing `caselist.api_base_url`.

Neither may be an endpoint override that prod accepts (the spec's forbidden list). So:

* `storage.s3.endpoint_url` is accepted in `dev` only, and only for a loopback address: a dev
  session's token travels with every request it signs, so the setting cannot send one off the
  machine. `prod` and `test` refuse it, naming the setting and where its value came from.
* `caselist.api_base_url` keeps its documented value in `prod`; any other is refused the same way.
  `dev` still accepts any https URL, as it did before.

Expected messages are written by hand, not read back from the loader.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application.settings import ConfigurationError, load_settings

STAND_IN = "http://127.0.0.1:50123"
STAND_IN_API = "https://127.0.0.1:50124/v1"
DOCUMENTED_API = "https://api.opencaselist.com/v1"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every `DEBATE_*` variable, so a test sees only what it sets itself."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def no_dotenv(tmp_path: Path) -> Path:
    return tmp_path / "absent.env"


def test_dev_accepts_a_loopback_evidence_store_endpoint_and_says_where_it_came_from(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path
) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__S3__ENDPOINT_URL", STAND_IN)

    settings = load_settings(environment="dev", env_file=no_dotenv)

    assert settings.storage.s3.endpoint_url == STAND_IN
    assert settings.field_sources["storage.s3.endpoint_url"] == "env:DEBATE_STORAGE__S3__ENDPOINT_URL"
    assert settings.redacted_dict()["storage.s3.endpoint_url"] == STAND_IN


def test_no_environment_sets_an_evidence_store_endpoint_by_default(no_dotenv: Path) -> None:
    for environment in ("dev", "prod", "test"):
        settings = load_settings(environment=environment, env_file=no_dotenv)
        assert settings.storage.s3.endpoint_url is None, environment
        assert settings.field_sources["storage.s3.endpoint_url"] == "default", environment


@pytest.mark.parametrize("environment", ["prod", "test"])
def test_an_evidence_store_endpoint_is_refused_outside_dev_naming_the_setting(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path, environment: str
) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__S3__ENDPOINT_URL", STAND_IN)

    with pytest.raises(ConfigurationError) as refused:
        load_settings(environment=environment, env_file=no_dotenv)

    assert str(refused.value) == (
        "invalid configuration: storage.s3.endpoint_url (from env:DEBATE_STORAGE__S3__ENDPOINT_URL): "
        f"accepted only in the dev environment, never in {environment} (DEBATE_STORAGE__S3__ENDPOINT_URL). "
        "It points the evidence store at a stand-in, which only a smoke check on a dev installation runs"
    )
    assert refused.value.field == "storage.s3.endpoint_url"
    assert refused.value.source == "env:DEBATE_STORAGE__S3__ENDPOINT_URL"


def test_a_prod_profile_that_names_an_evidence_store_endpoint_is_refused_naming_the_file(
    tmp_path: Path, no_dotenv: Path
) -> None:
    """Not only a variable: whichever layer supplies it, prod refuses it and says which."""
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "prod.toml").write_text(f'[storage.s3]\nendpoint_url = "{STAND_IN}"\n', encoding="utf-8")

    with pytest.raises(ConfigurationError) as refused:
        load_settings(environment="prod", env_file=no_dotenv, profile_dir=profiles)

    assert refused.value.field == "storage.s3.endpoint_url"
    assert f"(from profile:{profiles / 'prod.toml'})" in str(refused.value)
    assert "accepted only in the dev environment, never in prod" in str(refused.value)
    assert "DEBATE_STORAGE__S3__ENDPOINT_URL" in str(refused.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://192.0.2.1:9000",
        "https://s3.example.invalid",
        "http://127.0.0.1.example.invalid:9000",
        "ftp://127.0.0.1:9000",
        "127.0.0.1:9000",
    ],
)
def test_dev_refuses_an_evidence_store_endpoint_that_is_not_loopback(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path, endpoint: str
) -> None:
    """A dev session's token is in every request it signs: it may only go to this machine."""
    monkeypatch.setenv("DEBATE_STORAGE__S3__ENDPOINT_URL", endpoint)

    with pytest.raises(ConfigurationError) as refused:
        load_settings(environment="dev", env_file=no_dotenv)

    assert refused.value.field == "storage.s3.endpoint_url"
    assert "must be an http:// or https:// URL on this machine's loopback address" in str(refused.value)


@pytest.mark.parametrize(
    "endpoint", ["http://127.0.0.1:50123", "http://localhost:50123", "https://[::1]:443"]
)
def test_dev_accepts_every_spelling_of_loopback(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path, endpoint: str
) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__S3__ENDPOINT_URL", endpoint)

    assert load_settings(environment="dev", env_file=no_dotenv).storage.s3.endpoint_url == endpoint


def test_prod_refuses_an_opencaselist_endpoint_other_than_the_documented_one(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__API_BASE_URL", STAND_IN_API)

    with pytest.raises(ConfigurationError) as refused:
        load_settings(environment="prod", env_file=no_dotenv)

    assert str(refused.value) == (
        "invalid configuration: caselist.api_base_url (from env:DEBATE_CASELIST__API_BASE_URL): "
        f"prod reaches OpenCaselist at {DOCUMENTED_API} and nowhere else (DEBATE_CASELIST__API_BASE_URL). "
        "Any other value is an endpoint override, which only a smoke check on a dev installation has a "
        "use for"
    )
    assert refused.value.field == "caselist.api_base_url"


def test_prod_accepts_the_documented_opencaselist_endpoint_spelled_out(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__API_BASE_URL", DOCUMENTED_API + "/")

    assert load_settings(environment="prod", env_file=no_dotenv).caselist.api_base_url == DOCUMENTED_API


def test_dev_still_accepts_another_https_opencaselist_endpoint(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__API_BASE_URL", STAND_IN_API)

    settings = load_settings(environment="dev", env_file=no_dotenv)

    assert settings.caselist.api_base_url == STAND_IN_API
    assert settings.field_sources["caselist.api_base_url"] == "env:DEBATE_CASELIST__API_BASE_URL"
