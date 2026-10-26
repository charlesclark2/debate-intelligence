"""`models.aws_profile`: the AWS profile every Bedrock call is signed with (v1-e05-t08, ac2).

A setting per environment, like `storage.s3.aws_profile`, so that a model call never depends on
whatever `AWS_PROFILE` the shell holds. The committed dev and prod profiles name the SSO profile of
their environment's `Debate<Env>BedrockInvoker` permission set, as the environment root names it
(`infrastructure/envs/<env>/bedrock_access.tf`); `test`, which routes to the offline fake, names
none.

Expected values are written by hand from the committed files, not read back from the loader.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application.settings import ConfigurationError, find_repository_root, load_settings


def _repository_root() -> Path:
    root = find_repository_root(Path(__file__).parent)
    assert root is not None, "these tests read the committed config/ and infrastructure/ directories"
    return root


REPOSITORY_ROOT = _repository_root()


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every `DEBATE_*` variable, and `AWS_PROFILE`, so a test sees only what it sets."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    yield


@pytest.fixture
def no_dotenv(tmp_path: Path) -> Path:
    """A `.env` path that does not exist, so a developer's own `.env` cannot decide a test."""
    return tmp_path / "absent.env"


def test_the_committed_dev_and_prod_profiles_name_their_bedrock_profiles(no_dotenv: Path) -> None:
    development = load_settings(environment="dev", env_file=no_dotenv)
    production = load_settings(environment="prod", env_file=no_dotenv)

    assert development.models.aws_profile == "debate-dev-bedrock"
    assert production.models.aws_profile == "debate-prod-bedrock"
    assert development.field_sources["models.aws_profile"] == "profile:config/profiles/dev.toml"
    assert production.field_sources["models.aws_profile"] == "profile:config/profiles/prod.toml"


def test_the_test_profile_names_no_bedrock_profile(no_dotenv: Path) -> None:
    assert load_settings(environment="test", env_file=no_dotenv).models.aws_profile is None


def test_aws_profile_in_the_shell_does_not_change_the_setting(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path
) -> None:
    monkeypatch.setenv("AWS_PROFILE", "debate-prod-evidence")

    assert load_settings(environment="dev", env_file=no_dotenv).models.aws_profile == "debate-dev-bedrock"


def test_the_setting_is_overridden_like_any_other(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path) -> None:
    monkeypatch.setenv("DEBATE_MODELS__AWS_PROFILE", "debate-dev-bedrock-elsewhere")

    settings = load_settings(environment="dev", env_file=no_dotenv)

    assert settings.models.aws_profile == "debate-dev-bedrock-elsewhere"
    assert settings.field_sources["models.aws_profile"] == "env:DEBATE_MODELS__AWS_PROFILE"


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_value_is_no_profile(monkeypatch: pytest.MonkeyPatch, no_dotenv: Path, blank: str) -> None:
    """An environment variable can override a committed value but never remove it, so an empty one
    is how a run with a role of its own (a task, an instance) says it names no profile, as
    `DEBATE_STORAGE__S3__AWS_PROFILE=` does for the bucket (ADR-0020 (5))."""
    monkeypatch.setenv("DEBATE_MODELS__AWS_PROFILE", blank)

    assert load_settings(environment="prod", env_file=no_dotenv).models.aws_profile is None


def test_a_profile_that_is_not_a_string_is_refused(no_dotenv: Path) -> None:
    with pytest.raises(ConfigurationError, match=r"models\.aws_profile"):
        load_settings(environment="dev", env_file=no_dotenv, overrides={"models": {"aws_profile": 7}})


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_the_committed_profile_is_the_one_terraform_names(no_dotenv: Path, environment: str) -> None:
    """The root names the profile `${var.name_prefix}-${var.environment}-bedrock`, and name_prefix
    defaults to `debate`: if either moves, the committed profile names nobody's permission set."""
    root = REPOSITORY_ROOT / "infrastructure" / "envs" / environment
    module_call = (root / "bedrock_access.tf").read_text(encoding="utf-8")
    variables = (root / "variables.tf").read_text(encoding="utf-8")

    assert 'name_prefix = "${var.name_prefix}-${var.environment}-bedrock"' in module_call
    name_prefix = re.search(r'variable "name_prefix" \{.*?default\s*=\s*"([^"]+)"', variables, re.DOTALL)
    assert name_prefix is not None and name_prefix.group(1) == "debate"
    settings = load_settings(environment=environment, env_file=no_dotenv)
    assert settings.models.aws_profile == f"debate-{environment}-bedrock"
