"""The dev and prod channel values, and the environment an installed build defaults to.

v1-e02-t05 built the profile mechanism; v1-e01-t09 supplies what the dev and prod channels put in
it. These tests pin three things:

* the **committed** dev and prod profiles and routing files differ where the task spec says they
  must (data directory, routing file), carry the model budgets the PM set on 2026-10-27
  (v1-e05-t15), dev's daily budget stays under the documented cap, no budget is above the coach's
  monthly ceiling, and both keep the E34 `[caselist] api_enabled` gate an operator recorded in them;
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

from debate_core.application.settings import (
    BUILTIN_PROFILES,
    DEV_DAILY_BUDGET_CAP_USD,
    MONTHLY_MODEL_BUDGET_CEILING_USD,
    Environment,
    environment_for_build_channel,
    find_repository_root,
    load_settings,
    resolve_environment,
)
from debate_core.domain.model_contracts import TaskClass
from debate_core.integrations.models import RoutingPolicy


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


def test_the_coach_s_monthly_ceiling_is_fifty_dollars() -> None:
    assert MONTHLY_MODEL_BUDGET_CEILING_USD == 50.0


def test_committed_dev_and_prod_profiles_differ_in_data_dir_and_routing_file_and_set_their_budgets(
    no_dotenv: Path,
) -> None:
    development = load_settings(environment="dev", env_file=no_dotenv)
    production = load_settings(environment="prod", env_file=no_dotenv)

    assert development.storage.data_dir == Path("~/.debate-research/dev").expanduser().absolute()
    assert production.storage.data_dir == Path("~/.debate-research/prod").expanduser().absolute()
    assert development.models.routing_file == CONFIG / "model_routing.dev.yaml"
    assert production.models.routing_file == CONFIG / "model_routing.prod.yaml"
    # Dev's $2 a day is the capped sample's allowance (the PM's ruling of 2026-10-27); prod's $1.50
    # is the coach's $50 a month over thirty days, rounded down. Both hold the month to the $50
    # itself until the promotion, because only one environment calls models today (v1-e05-t15).
    assert development.models.budget_usd_daily == 2.0
    assert production.models.budget_usd_daily == 1.5
    assert development.models.budget_usd_monthly == 50.0
    assert production.models.budget_usd_monthly == 50.0
    assert development.field_sources["models.budget_usd_daily"] == "profile:config/profiles/dev.toml"
    assert production.field_sources["models.budget_usd_monthly"] == "profile:config/profiles/prod.toml"
    assert production.field_sources["models.routing_file"] == "profile:config/profiles/prod.toml"


def test_the_dev_budget_never_exceeds_the_documented_cap(no_dotenv: Path) -> None:
    committed = load_settings(environment="dev", env_file=no_dotenv).models.budget_usd_daily
    built_in = BUILTIN_PROFILES[Environment.DEV]["models"]["budget_usd_daily"]

    assert committed is not None
    assert 0 < committed <= DEV_DAILY_BUDGET_CAP_USD
    assert 0 < built_in <= DEV_DAILY_BUDGET_CAP_USD


@pytest.mark.parametrize("environment", [Environment.DEV, Environment.PROD])
def test_no_committed_or_built_in_budget_is_above_the_coach_s_ceiling(
    environment: Environment, no_dotenv: Path
) -> None:
    """Every model budget dev and prod carry, bundled and built in, is within $50, and the month is $50."""
    committed = load_settings(environment=environment.value, env_file=no_dotenv).models
    built_in = BUILTIN_PROFILES[environment]["models"]

    for budget in (
        committed.budget_usd_daily,
        committed.budget_usd_monthly,
        committed.budget_usd_per_run,
        built_in["budget_usd_daily"],
        built_in["budget_usd_monthly"],
        built_in.get("budget_usd_per_run"),
    ):
        assert budget is None or budget <= MONTHLY_MODEL_BUDGET_CEILING_USD
    assert committed.budget_usd_monthly == MONTHLY_MODEL_BUDGET_CEILING_USD
    assert built_in["budget_usd_monthly"] == MONTHLY_MODEL_BUDGET_CEILING_USD


def test_the_built_in_profiles_carry_the_committed_budgets(no_dotenv: Path) -> None:
    """A wheel built without config/profiles still gets dev's $2 and prod's $1.50 a day, and $50 a month."""
    assert BUILTIN_PROFILES[Environment.DEV]["models"]["budget_usd_daily"] == 2.0
    assert BUILTIN_PROFILES[Environment.PROD]["models"]["budget_usd_daily"] == 1.5


def test_both_routing_files_exist_and_load() -> None:
    development = RoutingPolicy.load(CONFIG / "model_routing.dev.yaml")
    production = RoutingPolicy.load(CONFIG / "model_routing.prod.yaml")

    assert set(development.routes) == set(TaskClass)
    assert set(production.routes) == set(TaskClass)


def test_dev_routes_every_text_class_to_a_cheaper_model_than_prod() -> None:
    development = RoutingPolicy.load(CONFIG / "model_routing.dev.yaml").routes
    production = RoutingPolicy.load(CONFIG / "model_routing.prod.yaml").routes

    # Hand-written from the two files: dev drops each class one tier. Families, not identifiers,
    # so the next model release changes the files and not this test (PM ruling, 2026-10-16).
    assert "claude-haiku" in development[TaskClass.COMPLEX_REASONING].model_id
    assert "claude-sonnet" in production[TaskClass.COMPLEX_REASONING].model_id
    assert "claude-sonnet" in development[TaskClass.DEEP_AUDIT].model_id
    assert "claude-opus" in production[TaskClass.DEEP_AUDIT].model_id
    # Embeddings and rerank stay the same model, so a dev index is comparable with a prod one.
    assert development[TaskClass.EMBEDDINGS] == production[TaskClass.EMBEDDINGS]
    assert development[TaskClass.RERANK] == production[TaskClass.RERANK]


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
        '[models]\nrouting_file = "config/model_routing.dev.yaml"\nbudget_usd_daily = 1.75\n'
        "[caselist]\napi_enabled = true\n",
        encoding="utf-8",
    )
    (root / "config" / "profiles" / "prod.toml").write_text(
        '[storage]\ndata_dir = "~/bundled-prod"\n'
        '[models]\nrouting_file = "config/model_routing.prod.yaml"\nbudget_usd_daily = 1.25\n',
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
    assert settings.models.budget_usd_daily == 1.75
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


def test_bundled_dev_and_prod_each_read_their_own_data_dir_routing_file_and_budget(
    bundled_root: Path, no_dotenv: Path
) -> None:
    """The bundle's $1.75 and $1.25 a day are in no committed profile, so each is read from it."""
    development = load_settings(environment="dev", env_file=no_dotenv, bundled_config_root=bundled_root)
    production = load_settings(environment="prod", env_file=no_dotenv, bundled_config_root=bundled_root)

    assert development.storage.data_dir == Path("~/bundled-dev").expanduser().absolute()
    assert production.storage.data_dir == Path("~/bundled-prod").expanduser().absolute()
    assert development.models.routing_file == bundled_root / "config" / "model_routing.dev.yaml"
    assert production.models.routing_file == bundled_root / "config" / "model_routing.prod.yaml"
    assert (development.models.budget_usd_daily, production.models.budget_usd_daily) == (1.75, 1.25)


# ---------------------------------------------------------------------------------------------
# The search pilot's weekly index is on where the agent runs (v1-e39-t09, PM ruling Q6)
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("channel", "environment"), [("dev", Environment.DEV), ("stable", Environment.PROD)])
def test_the_bundled_dev_and_prod_profiles_leave_the_weekly_index_refresh_on(
    channel: str, environment: Environment, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_dotenv: Path
) -> None:
    """The committed `config/` as the wheel bundles it, read from `$HOME` as the launchd agent reads it."""
    bundled = tmp_path / "bundled"
    shutil.copytree(CONFIG, bundled / "config")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(home)

    settings = load_settings(env_file=no_dotenv, build_channel=channel, bundled_config_root=bundled)

    assert settings.environment is environment
    assert settings.caselist.refresh_search_index is True


def test_a_bundled_profile_is_what_decides_the_weekly_index_refresh(
    bundled_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, no_dotenv: Path
) -> None:
    """The check above can fail: a profile that turns the stage off is read as off."""
    profile = bundled_root / "config" / "profiles" / "dev.toml"
    profile.write_text(
        profile.read_text("utf-8").replace(
            "api_enabled = true\n", "api_enabled = true\nrefresh_search_index = false\n"
        ),
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(home)

    settings = load_settings(env_file=no_dotenv, build_channel="dev", bundled_config_root=bundled_root)

    assert settings.caselist.refresh_search_index is False


# ---------------------------------------------------------------------------------------------
# The weekly run's caselists and its state are dev's profile's, from the cutover (v1-e40-t06)
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def committed_root(tmp_path: Path) -> Path:
    """The committed `config/`, as the wheel bundles it."""
    bundled = tmp_path / "committed"
    shutil.copytree(CONFIG, bundled / "config")
    return bundled


def test_the_committed_dev_profile_names_the_runs_three_caselists_and_keeps_its_state_in_the_bucket(
    committed_root: Path, no_dotenv: Path
) -> None:
    """ADR-0020 (5): the run's command names no caselist, so the build it runs must.

    The three are the Mac agent's `--caselist` arguments as its plist held them at the cutover, in
    that order. Bucket mode is the Mac's as well as the cloud task's from the cutover (ADR-0020 (4)).
    """
    development = load_settings(environment="dev", env_file=no_dotenv, bundled_config_root=committed_root)

    assert development.caselist.sync_caselists == ("hsld26", "hspolicy26", "hspf26")
    assert development.caselist.run_state.value == "bucket"


def test_the_committed_prod_profile_follows_no_caselist_and_keeps_its_state_locally(
    committed_root: Path, no_dotenv: Path
) -> None:
    """Until the run's home moves at the pilot's promotion (ADR-0020 (7)), prod is published by hand."""
    production = load_settings(environment="prod", env_file=no_dotenv, bundled_config_root=committed_root)

    assert production.caselist.sync_caselists == ()
    assert production.caselist.run_state.value == "local"
