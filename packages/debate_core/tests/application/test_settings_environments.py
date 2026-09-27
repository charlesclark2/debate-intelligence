"""The dev and prod channel values, and the environment an installed build defaults to.

v1-e02-t05 built the profile mechanism; v1-e01-t09 supplies what the dev and prod channels put in
it. These tests pin three things:

* the **committed** dev and prod profiles and routing files differ where the task spec says they
  must (data directory, routing file, daily budget), dev's budget stays under the documented cap,
  and both keep the E34 `[caselist] api_enabled` gate an operator recorded in them;
* an installed build picks its environment from its **build channel** when `DEBATE_ENV` is unset,
  and an explicit choice still wins;
* an installed build reads the configuration **bundled in its wheel**, not whatever checkout the
  working directory happens to be inside.

Expected values are written by hand from the committed files, not read back from the loader.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application.ports.providers import ModelTaskClass
from debate_core.application.routing_config import load_routing_config
from debate_core.application.settings import (
    BUILTIN_PROFILES,
    DEV_DAILY_BUDGET_CAP_USD,
    Environment,
    environment_for_build_channel,
    find_repository_root,
    load_settings,
    resolve_environment,
)


def _repository_root() -> Path:
    root = find_repository_root(Path(__file__).parent)
    assert root is not None, "these tests read the committed config/ directory"
    return root


REPOSITORY_ROOT = _repository_root()
CONFIG = REPOSITORY_ROOT / "config"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every `DEBATE_*` variable, so a test sees only what it sets itself."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def no_dotenv(tmp_path: Path) -> Path:
    """A `.env` path that does not exist, so a developer's own `.env` cannot decide a test."""
    return tmp_path / "absent.env"


# ---------------------------------------------------------------------------------------------
# The committed channel values
# ---------------------------------------------------------------------------------------------


def test_the_documented_dev_cap_is_two_dollars_a_day() -> None:
    assert DEV_DAILY_BUDGET_CAP_USD == 2.0


def test_committed_dev_and_prod_profiles_differ_in_data_dir_routing_file_and_budget(
    no_dotenv: Path,
) -> None:
    development = load_settings(environment="dev", env_file=no_dotenv)
    production = load_settings(environment="prod", env_file=no_dotenv)

    assert development.storage.data_dir == Path("~/.debate-research/dev").expanduser().absolute()
    assert production.storage.data_dir == Path("~/.debate-research/prod").expanduser().absolute()
    assert development.models.routing_file == CONFIG / "model_routing.dev.yaml"
    assert production.models.routing_file == CONFIG / "model_routing.prod.yaml"
    assert development.models.budget_usd_daily == 2.0
    assert production.models.budget_usd_daily == 20.0
    assert development.field_sources["models.budget_usd_daily"] == "profile:config/profiles/dev.toml"
    assert production.field_sources["models.routing_file"] == "profile:config/profiles/prod.toml"


def test_the_dev_budget_never_exceeds_the_documented_cap(no_dotenv: Path) -> None:
    committed = load_settings(environment="dev", env_file=no_dotenv).models.budget_usd_daily
    built_in = BUILTIN_PROFILES[Environment.DEV]["models"]["budget_usd_daily"]

    assert 0 < committed <= DEV_DAILY_BUDGET_CAP_USD
    assert 0 < built_in <= DEV_DAILY_BUDGET_CAP_USD


def test_both_routing_files_exist_and_load() -> None:
    development = load_routing_config(CONFIG / "model_routing.dev.yaml")
    production = load_routing_config(CONFIG / "model_routing.prod.yaml")

    assert set(development.routes) == set(ModelTaskClass)
    assert set(production.routes) == set(ModelTaskClass)


def test_dev_routes_every_text_class_to_a_cheaper_model_than_prod() -> None:
    development = load_routing_config(CONFIG / "model_routing.dev.yaml").routes
    production = load_routing_config(CONFIG / "model_routing.prod.yaml").routes

    # Hand-written from the two files: dev drops each class one tier.
    assert development[ModelTaskClass.COMPLEX_REASONING].model_id == "anthropic.claude-haiku-4-5"
    assert production[ModelTaskClass.COMPLEX_REASONING].model_id == "anthropic.claude-sonnet-5"
    assert development[ModelTaskClass.DEEP_AUDIT].model_id == "anthropic.claude-sonnet-5"
    assert production[ModelTaskClass.DEEP_AUDIT].model_id == "anthropic.claude-opus-5"
    # Embeddings stay the same model, so a dev index is comparable with a prod one.
    assert development[ModelTaskClass.EMBEDDINGS] == production[ModelTaskClass.EMBEDDINGS]


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_the_committed_profiles_keep_the_caselist_policy_gate(environment: str, no_dotenv: Path) -> None:
    """`[caselist] api_enabled = true` is an operator's E34 decision recorded in the profile."""
    settings = load_settings(environment=environment, env_file=no_dotenv)

    assert settings.caselist.api_enabled is True
    assert settings.field_sources["caselist.api_enabled"] == f"profile:config/profiles/{environment}.toml"


# ---------------------------------------------------------------------------------------------
# The build channel picks the environment when nothing else does
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("channel", "expected"),
    [
        ("dev", Environment.DEV),
        ("stable", Environment.PROD),
        ("  Stable ", Environment.PROD),
        ("local", None),
        ("", None),
        (None, None),
        ("nightly", None),
    ],
)
def test_each_build_channel_names_its_environment(channel: str | None, expected: Environment | None) -> None:
    assert environment_for_build_channel(channel) is expected


def test_a_dev_prerelease_defaults_to_dev(no_dotenv: Path) -> None:
    assert resolve_environment(env_file=no_dotenv, build_channel="dev") == (
        Environment.DEV,
        "build-channel:dev",
    )


def test_a_stable_build_defaults_to_prod(no_dotenv: Path) -> None:
    assert resolve_environment(env_file=no_dotenv, build_channel="stable") == (
        Environment.PROD,
        "build-channel:stable",
    )


def test_a_source_checkout_keeps_the_dev_default(no_dotenv: Path) -> None:
    assert resolve_environment(env_file=no_dotenv, build_channel="local") == (Environment.DEV, "default")


def test_an_explicit_debate_env_beats_the_build_channel(
    monkeypatch: pytest.MonkeyPatch, no_dotenv: Path
) -> None:
    monkeypatch.setenv("DEBATE_ENV", "dev")

    assert resolve_environment(env_file=no_dotenv, build_channel="stable") == (
        Environment.DEV,
        "env:DEBATE_ENV",
    )


def test_debate_env_in_dotenv_beats_the_build_channel(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEBATE_ENV=prod\n", encoding="utf-8")

    assert resolve_environment(env_file=env_file, build_channel="dev") == (
        Environment.PROD,
        f"dotenv:{env_file}",
    )


def test_a_command_line_environment_beats_the_build_channel(no_dotenv: Path) -> None:
    assert resolve_environment("test", env_file=no_dotenv, build_channel="stable") == (
        Environment.TEST,
        "cli",
    )


def test_load_settings_reports_the_build_channel_as_the_source_of_the_environment(
    no_dotenv: Path,
) -> None:
    settings = load_settings(env_file=no_dotenv, build_channel="stable")

    assert settings.environment is Environment.PROD
    assert settings.field_sources["environment"] == "build-channel:stable"
    assert settings.storage.data_dir == Path("~/.debate-research/prod").expanduser().absolute()


# ---------------------------------------------------------------------------------------------
# An installed build reads the configuration bundled in its wheel
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def bundled_root(tmp_path: Path) -> Path:
    """A bundled configuration laid out as the wheel carries it: `config/profiles`, routing files."""
    root = tmp_path / "bundled"
    (root / "config" / "profiles").mkdir(parents=True)
    (root / "config" / "profiles" / "dev.toml").write_text(
        '[storage]\ndata_dir = "~/bundled-dev"\n'
        '[models]\nrouting_file = "config/model_routing.dev.yaml"\nbudget_usd_daily = 1.5\n'
        "[caselist]\napi_enabled = true\n",
        encoding="utf-8",
    )
    (root / "config" / "profiles" / "prod.toml").write_text(
        '[storage]\ndata_dir = "~/bundled-prod"\n'
        '[models]\nrouting_file = "config/model_routing.prod.yaml"\nbudget_usd_daily = 20.0\n',
        encoding="utf-8",
    )
    shutil.copy(CONFIG / "model_routing.dev.yaml", root / "config" / "model_routing.dev.yaml")
    shutil.copy(CONFIG / "model_routing.prod.yaml", root / "config" / "model_routing.prod.yaml")
    return root


def test_an_installed_build_reads_its_bundled_profile_even_inside_a_checkout(
    bundled_root: Path, monkeypatch: pytest.MonkeyPatch, no_dotenv: Path
) -> None:
    # The working directory is the repository, whose own dev.toml says data_dir ~/.debate-research/dev.
    monkeypatch.chdir(REPOSITORY_ROOT)

    settings = load_settings(env_file=no_dotenv, build_channel="dev", bundled_config_root=bundled_root)

    assert settings.environment is Environment.DEV
    assert settings.storage.data_dir == Path("~/bundled-dev").expanduser().absolute()
    assert settings.models.budget_usd_daily == 1.5
    assert settings.caselist.api_enabled is True
    assert settings.field_sources["storage.data_dir"] == (
        f"profile:{bundled_root / 'config' / 'profiles' / 'dev.toml'}"
    )


def test_a_bundled_relative_routing_file_is_anchored_to_the_bundle(
    bundled_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_dotenv: Path
) -> None:
    # Run from somewhere that is not a checkout: the launchd agent's working directory is $HOME.
    elsewhere = tmp_path / "home"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    settings = load_settings(env_file=no_dotenv, build_channel="stable", bundled_config_root=bundled_root)

    assert settings.models.routing_file == bundled_root / "config" / "model_routing.prod.yaml"
    assert settings.models.routing_file.is_file()


def test_debate_profile_dir_still_beats_the_bundled_configuration(
    bundled_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_dotenv: Path
) -> None:
    override = tmp_path / "operator-profiles"
    override.mkdir()
    (override / "dev.toml").write_text('[storage]\ndata_dir = "~/operator-dev"\n', encoding="utf-8")
    monkeypatch.setenv("DEBATE_PROFILE_DIR", str(override))

    settings = load_settings(env_file=no_dotenv, build_channel="dev", bundled_config_root=bundled_root)

    assert settings.storage.data_dir == Path("~/operator-dev").expanduser().absolute()


def test_bundled_dev_and_prod_never_share_a_data_dir_routing_file_or_budget(
    bundled_root: Path, no_dotenv: Path
) -> None:
    development = load_settings(environment="dev", env_file=no_dotenv, bundled_config_root=bundled_root)
    production = load_settings(environment="prod", env_file=no_dotenv, bundled_config_root=bundled_root)

    assert development.storage.data_dir != production.storage.data_dir
    assert development.models.routing_file != production.models.routing_file
    assert development.models.budget_usd_daily != production.models.budget_usd_daily
