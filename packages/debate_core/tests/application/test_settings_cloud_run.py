"""The settings the weekly cloud run's task definition sets, read as the run reads them (`v1-e40-t03`).

ADR-0020 (5): the task definition's environment holds no secret, only what makes the CLI the cloud
run. Two settings needed something new to say it:

* `storage.s3.aws_profile`: the committed dev and prod profiles name the operator's SSO profile,
  and an environment variable can only override a value. An empty value now means no profile, so
  the SDK signs with the task role.
* `storage.volume_warning_percent`: the 70% warning on the run's ephemeral volume. Unset, reading
  no volume, everywhere else.

`RUN_ENVIRONMENT` is the run's environment as `infrastructure/modules/caselist_run/run_task.tf`
writes it for dev, copied by hand; the module's Terraform tests pin the same names and values.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application.settings import (
    CaselistTokenBackend,
    ConfigurationError,
    load_settings,
)

COMMITTED_PROFILES = Path(__file__).resolve().parents[4] / "config" / "profiles"

RUN_ENVIRONMENT = {
    "DEBATE_ENV": "dev",
    "DEBATE_ALLOW_NETWORK": "true",
    "DEBATE_CASELIST__API_ENABLED": "true",
    "DEBATE_CASELIST__TOKEN_BACKEND": "secretsmanager",
    "DEBATE_CASELIST__TOKEN_SECRET_ID": "debate-dev-caselist-token",
    "DEBATE_CASELIST__SECRETS_REGION": "us-east-1",
    "DEBATE_STORAGE__DATA_DIR": "/var/lib/debate-research/dev",
    "DEBATE_STORAGE__S3__AWS_PROFILE": "",
    "DEBATE_STORAGE__VOLUME_WARNING_PERCENT": "70",
    "DEBATE_PARSE__WORKERS": "8",
}


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every `DEBATE_*` variable, so a test sees only what it sets itself."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


def test_the_run_reads_its_settings_from_the_bundled_dev_profile_and_its_task_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in RUN_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    settings = load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)

    assert settings.storage.s3.aws_profile is None, "the task role, not the operator's SSO profile"
    assert settings.field_sources["storage.s3.aws_profile"] == "env:DEBATE_STORAGE__S3__AWS_PROFILE"
    assert settings.storage.s3.bucket == "debate-dev-evidence-a7508de8", "the dev bucket, from the profile"
    assert settings.storage.volume_warning_percent == 70
    assert settings.storage.data_dir == Path("/var/lib/debate-research/dev")
    assert settings.parse.worker_count(cpu_count=8) == 8
    assert settings.caselist.token_backend is CaselistTokenBackend.SECRETSMANAGER
    assert settings.caselist.token_secret_id == "debate-dev-caselist-token"


def test_the_committed_dev_profile_names_the_operators_sso_profile_and_no_volume_warning() -> None:
    settings = load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)

    assert settings.storage.s3.aws_profile == "debate-dev-evidence"
    assert settings.storage.volume_warning_percent is None, "a laptop's disk is not the run's to judge"


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_aws_profile_is_no_profile(blank: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", blank)

    settings = load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)

    assert settings.storage.s3.aws_profile is None


def test_a_named_aws_profile_is_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__S3__AWS_PROFILE", "debate-dev-evidence-removal")

    settings = load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)

    assert settings.storage.s3.aws_profile == "debate-dev-evidence-removal"


@pytest.mark.parametrize("percent", ["0", "100", "seventy"])
def test_a_volume_warning_outside_one_to_ninety_nine_percent_is_refused(
    percent: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_STORAGE__VOLUME_WARNING_PERCENT", percent)

    with pytest.raises(ConfigurationError, match="volume_warning_percent"):
        load_settings(environment="dev", profile_dir=COMMITTED_PROFILES, env_file=None)
