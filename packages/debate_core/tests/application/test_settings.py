"""Settings: layer precedence, environment selection, validation and redaction.

Every test here points the loader at its own fixture directory rather than at the repository's
real `config/profiles/`, and clears `DEBATE_*` from the environment first. Otherwise the suite
would pass or fail depending on what the person running it happens to have exported, which is the
exact class of bug this module exists to make visible.

The profile files this task ships are checked separately, at the bottom, against the real
`config/profiles/` — those are the values acceptance criterion 4 is about.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application.settings import (
    ENVIRONMENT_VARIABLE,
    PROFILE_DIRECTORY_VARIABLE,
    SECRET_PLACEHOLDER,
    ConfigurationError,
    Environment,
    HttpSettings,
    ModelSettings,
    SearchProviderName,
    Settings,
    StorageSettings,
    find_repository_root,
    load_settings,
    profile_path_for,
    resolve_environment,
)

REPOSITORY_ROOT = find_repository_root(Path(__file__).parent)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every `DEBATE_*` variable, so a test sees only what it sets itself."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def profiles(tmp_path: Path) -> Path:
    """A profile directory with one file per environment, each setting distinguishable values."""
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "dev.toml").write_text(
        "\n".join(
            [
                "allow_network = true",
                "[storage]",
                'data_dir = "~/fixture-dev"',
                "[http]",
                "per_host_interval_seconds = 2.0",
                "[providers]",
                'enabled = ["openalex"]',
                "[models]",
                'routing_file = "config/routing-dev.yaml"',
                "budget_usd_daily = 2.0",
            ]
        ),
        encoding="utf-8",
    )
    (directory / "prod.toml").write_text(
        "\n".join(
            [
                "[storage]",
                'data_dir = "~/fixture-prod"',
                "[models]",
                'routing_file = "config/routing-prod.yaml"',
                "budget_usd_daily = 25.0",
            ]
        ),
        encoding="utf-8",
    )
    (directory / "test.toml").write_text(
        "\n".join(
            [
                "allow_network = false",
                "[providers]",
                "enabled = []",
                "[models]",
                'routing_file = "config/routing-test.yaml"',
                "budget_usd_daily = 0.0",
            ]
        ),
        encoding="utf-8",
    )
    return directory


# ---------------------------------------------------------------------------------------------
# Precedence (acceptance criterion 1)
# ---------------------------------------------------------------------------------------------


def test_a_profile_supplies_what_nothing_else_does(profiles: Path) -> None:
    settings = load_settings(environment="dev", profile_dir=profiles)

    assert settings.http.per_host_interval_seconds == 2.0
    assert settings.field_sources["http.per_host_interval_seconds"].startswith("profile:")


def test_the_builtin_profile_fills_in_what_the_profile_file_omits(profiles: Path) -> None:
    # The fixture's test.toml deliberately sets no data_dir, the way the real one does not.
    settings = load_settings(environment="test", profile_dir=profiles)

    assert settings.storage.data_dir.is_absolute()
    assert settings.field_sources["storage.data_dir"] == "built-in:test"


def test_a_field_no_layer_sets_keeps_its_declared_default(profiles: Path) -> None:
    settings = load_settings(environment="dev", profile_dir=profiles)

    assert settings.http.user_agent_product == "debate-research"
    assert settings.field_sources["http.user_agent_product"] == "default"


def test_dotenv_beats_the_profile(profiles: Path, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS=4.5\n", encoding="utf-8")

    settings = load_settings(environment="dev", profile_dir=profiles, env_file=env_file)

    assert settings.http.per_host_interval_seconds == 4.5
    assert settings.field_sources["http.per_host_interval_seconds"] == f"dotenv:{env_file}"


def test_the_environment_beats_dotenv(
    profiles: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS=4.5\n", encoding="utf-8")
    monkeypatch.setenv("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS", "6.5")

    settings = load_settings(environment="dev", profile_dir=profiles, env_file=env_file)

    assert settings.http.per_host_interval_seconds == 6.5
    assert (
        settings.field_sources["http.per_host_interval_seconds"]
        == "env:DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS"
    )


def test_an_explicit_override_beats_the_environment(profiles: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS", "6.5")

    settings = load_settings(
        environment="dev",
        profile_dir=profiles,
        overrides={"http": {"per_host_interval_seconds": 9.0}},
    )

    assert settings.http.per_host_interval_seconds == 9.0
    assert settings.field_sources["http.per_host_interval_seconds"] == "cli"


def test_layers_merge_per_field_rather_than_per_group(
    profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One environment variable must not wipe out the rest of its group."""
    monkeypatch.setenv("DEBATE_HTTP__MAX_RETRIES", "5")

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert settings.http.max_retries == 5
    assert settings.http.per_host_interval_seconds == 2.0  # still the profile's


def test_the_whole_precedence_chain_holds_at_once(
    profiles: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DEBATE_HTTP__MAX_RETRIES=1\nDEBATE_HTTP__CONNECT_TIMEOUT_SECONDS=3.0\n", encoding="utf-8"
    )
    monkeypatch.setenv("DEBATE_HTTP__MAX_RETRIES", "2")

    settings = load_settings(
        environment="dev",
        profile_dir=profiles,
        env_file=env_file,
        overrides={"http": {"request_timeout_seconds": 11.0}},
    )
    sources = settings.field_sources

    assert (settings.http.request_timeout_seconds, sources["http.request_timeout_seconds"]) == (
        11.0,
        "cli",
    )
    assert (settings.http.max_retries, sources["http.max_retries"]) == (
        2,
        "env:DEBATE_HTTP__MAX_RETRIES",
    )
    assert (settings.http.connect_timeout_seconds, sources["http.connect_timeout_seconds"]) == (
        3.0,
        f"dotenv:{env_file}",
    )
    assert settings.http.per_host_interval_seconds == 2.0
    assert sources["http.per_host_interval_seconds"].startswith("profile:")
    assert sources["http.user_agent_product"] == "default"


def test_every_field_has_a_source(profiles: Path) -> None:
    settings = load_settings(environment="dev", profile_dir=profiles)

    assert set(settings.field_sources) == set(settings.redacted_dict())
    assert all(source for source in settings.field_sources.values())


# ---------------------------------------------------------------------------------------------
# Validation fails fast, naming the field (acceptance criterion 1)
# ---------------------------------------------------------------------------------------------


def test_an_out_of_range_value_names_the_field_and_where_it_came_from(
    profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_HTTP__MAX_RETRIES", "99")

    with pytest.raises(ConfigurationError) as raised:
        load_settings(environment="dev", profile_dir=profiles)

    assert raised.value.field == "http.max_retries"
    assert raised.value.source == "env:DEBATE_HTTP__MAX_RETRIES"
    assert "http.max_retries" in str(raised.value)


def test_a_misspelled_key_in_a_profile_is_rejected_by_name(tmp_path: Path) -> None:
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "dev.toml").write_text(
        '[http]\nper_host_interval_second = 2.0\n[storage]\ndata_dir = "~/x"\n'
        '[models]\nrouting_file = "r.yaml"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="per_host_interval_second"):
        load_settings(environment="dev", profile_dir=directory)


def test_an_unknown_provider_name_is_rejected(profiles: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__ENABLED", '["openalexx"]')

    with pytest.raises(ConfigurationError, match="providers.enabled"):
        load_settings(environment="dev", profile_dir=profiles)


def test_a_contact_url_that_is_not_a_url_is_rejected(profiles: Path) -> None:
    with pytest.raises(ConfigurationError, match="http.contact_url"):
        load_settings(
            environment="dev", profile_dir=profiles, overrides={"http": {"contact_url": "me@example.org"}}
        )


def test_a_profile_that_is_not_valid_toml_says_so(tmp_path: Path) -> None:
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "dev.toml").write_text("this is not = = toml\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not valid TOML"):
        load_settings(environment="dev", profile_dir=directory)


def test_a_profile_directory_that_does_not_exist_says_so(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="does not exist"):
        load_settings(environment="dev", profile_dir=tmp_path / "nowhere")


def test_a_missing_profile_file_is_not_a_failure(tmp_path: Path) -> None:
    """An installed build has no `config/profiles/`; it runs on the built-in profile."""
    empty = tmp_path / "profiles"
    empty.mkdir()

    settings = load_settings(environment="prod", profile_dir=empty)

    assert profile_path_for(Environment.PROD, empty) is None
    assert settings.field_sources["storage.data_dir"] == "built-in:prod"


# ---------------------------------------------------------------------------------------------
# DEBATE_ENV (acceptance criterion 4)
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["dev", "prod", "test"])
def test_the_three_environments_are_accepted(name: str, profiles: Path) -> None:
    settings = load_settings(environment=name, profile_dir=profiles)

    assert settings.environment == Environment(name)


@pytest.mark.parametrize("name", ["stage", "staging", "production", "local", "dev,prod"])
def test_any_other_environment_fails_fast_naming_what_is_allowed(
    name: str, profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, name)

    with pytest.raises(ConfigurationError) as raised:
        load_settings(profile_dir=profiles)

    message = str(raised.value)
    assert "dev, prod, test" in message
    assert raised.value.field == "environment"


@pytest.mark.parametrize(("written", "expected"), [("DEV", "dev"), (" prod ", "prod"), ("Test", "test")])
def test_case_and_surrounding_space_are_forgiven(
    written: str, expected: str, profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shell variable picks up stray whitespace; the three names are still unambiguous."""
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, written)

    assert load_settings(profile_dir=profiles).environment == Environment(expected)


def test_an_empty_debate_env_is_the_same_as_an_unset_one(
    profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "")

    assert load_settings(profile_dir=profiles).environment is Environment.DEV


def test_debate_env_is_read_from_the_environment(profiles: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "prod")

    settings = load_settings(profile_dir=profiles)

    assert settings.environment is Environment.PROD
    assert settings.field_sources["environment"] == f"env:{ENVIRONMENT_VARIABLE}"


def test_an_unset_debate_env_in_a_source_checkout_resolves_to_dev(profiles: Path) -> None:
    resolved, source = resolve_environment()

    assert resolved is Environment.DEV
    assert source == "default"
    assert load_settings(profile_dir=profiles).environment is Environment.DEV


def test_dev_and_prod_resolve_to_different_data_dirs(profiles: Path) -> None:
    development = load_settings(environment="dev", profile_dir=profiles)
    production = load_settings(environment="prod", profile_dir=profiles)

    assert development.storage.data_dir != production.storage.data_dir
    assert development.models.routing_file != production.models.routing_file


def test_the_test_environment_is_offline_and_writes_to_a_temporary_directory(profiles: Path) -> None:
    settings = load_settings(environment="test", profile_dir=profiles)

    assert settings.allow_network is False
    assert settings.providers.enabled == ()
    assert settings.models.budget_usd_daily == 0.0
    assert settings.storage.data_dir == Path(tempfile.gettempdir()).absolute() / "debate-research-test"


def test_debate_env_can_come_from_the_dotenv_file(profiles: Path, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# a comment\nDEBATE_ENV='prod'\n", encoding="utf-8")

    settings = load_settings(profile_dir=profiles, env_file=env_file)

    assert settings.environment is Environment.PROD
    assert settings.field_sources["environment"] == f"dotenv:{env_file}"


def test_the_environment_variable_beats_the_dotenv_file(
    profiles: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEBATE_ENV=prod\n", encoding="utf-8")
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "dev")

    assert load_settings(profile_dir=profiles, env_file=env_file).environment is Environment.DEV


def test_a_stray_debate_environment_variable_cannot_disagree_with_the_loaded_profile(
    profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The profile that was read and the environment that is reported are always the same one."""
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, "dev")
    monkeypatch.setenv("DEBATE_ENVIRONMENT", "prod")

    settings = load_settings(profile_dir=profiles)

    assert settings.environment is Environment.DEV
    assert settings.storage.data_dir == Path("~/fixture-dev").expanduser().absolute()


def test_the_profile_directory_can_be_named_by_a_variable(
    profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(PROFILE_DIRECTORY_VARIABLE, str(profiles))

    assert load_settings(environment="dev").storage.data_dir == Path("~/fixture-dev").expanduser().absolute()


# ---------------------------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------------------------


def test_secrets_come_from_the_environment_and_are_redacted(
    profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__CASELIST_TOKEN", "a-real-looking-session-cookie")
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", "coach@example.org")

    settings = load_settings(environment="dev", profile_dir=profiles)
    rendered = settings.redacted_dict()

    assert settings.providers.caselist_token is not None
    assert settings.providers.caselist_token.get_secret_value() == "a-real-looking-session-cookie"
    assert rendered["providers.caselist_token"] == SECRET_PLACEHOLDER
    assert rendered["providers.contact_email"] == SECRET_PLACEHOLDER
    assert "a-real-looking-session-cookie" not in repr(rendered)
    assert "coach@example.org" not in repr(rendered)


def test_a_secret_never_appears_in_the_models_own_repr(
    profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY", "sk-not-a-real-key")

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert "sk-not-a-real-key" not in repr(settings)
    assert "sk-not-a-real-key" not in str(settings)


def test_an_unset_secret_renders_as_null_rather_than_as_stars(profiles: Path) -> None:
    rendered = load_settings(environment="dev", profile_dir=profiles).redacted_dict()

    assert rendered["providers.semantic_scholar_api_key"] is None


def test_redacted_values_are_json_ready(profiles: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__CASELIST_TOKEN", "x")

    rendered = load_settings(environment="dev", profile_dir=profiles).redacted_dict()

    for key, value in rendered.items():
        assert isinstance(value, str | int | float | bool | list | type(None)), key


# ---------------------------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------------------------


def test_the_user_agent_identifies_the_tool_and_carries_a_contact_url() -> None:
    agent = HttpSettings().user_agent("1.2.3")

    assert agent.startswith("debate-research/1.2.3 ")
    assert "https://" in agent


def test_a_data_dir_written_with_a_tilde_is_expanded(profiles: Path) -> None:
    settings = load_settings(environment="dev", profile_dir=profiles)

    assert "~" not in str(settings.storage.data_dir)
    assert settings.storage.data_dir.is_absolute()


def test_a_relative_routing_file_is_anchored_to_the_repository(profiles: Path) -> None:
    """`config/routing-dev.yaml` in a committed profile must not depend on the working directory."""
    settings = load_settings(environment="dev", profile_dir=profiles)

    assert settings.models.routing_file.is_absolute()
    assert settings.models.routing_file.name == "routing-dev.yaml"


def test_settings_built_by_hand_report_every_source_as_default(tmp_path: Path) -> None:
    settings = Settings(
        storage=StorageSettings(data_dir=tmp_path),
        models=ModelSettings(routing_file=tmp_path / "r.yaml"),
    )

    assert set(settings.field_sources.values()) == {"default"}


def test_settings_are_frozen(profiles: Path) -> None:
    settings = load_settings(environment="dev", profile_dir=profiles)

    with pytest.raises(Exception, match="frozen|immutable"):
        settings.allow_network = False  # type: ignore[misc]


# ---------------------------------------------------------------------------------------------
# The profile files this task ships (acceptance criterion 4)
# ---------------------------------------------------------------------------------------------


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
def test_every_environment_has_a_committed_profile() -> None:
    assert REPOSITORY_ROOT is not None
    for environment in Environment:
        assert profile_path_for(environment, REPOSITORY_ROOT / "config" / "profiles") is not None


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
def test_the_committed_profiles_give_dev_and_prod_different_everything() -> None:
    assert REPOSITORY_ROOT is not None
    profiles = REPOSITORY_ROOT / "config" / "profiles"
    development = load_settings(environment="dev", profile_dir=profiles)
    production = load_settings(environment="prod", profile_dir=profiles)

    assert development.storage.data_dir != production.storage.data_dir
    assert development.models.routing_file != production.models.routing_file
    assert development.models.budget_usd_daily < production.models.budget_usd_daily


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
def test_the_committed_test_profile_is_offline() -> None:
    assert REPOSITORY_ROOT is not None
    settings = load_settings(environment="test", profile_dir=REPOSITORY_ROOT / "config" / "profiles")

    assert settings.allow_network is False
    assert settings.providers.enabled == ()
    assert settings.models.budget_usd_daily == 0.0
    assert settings.storage.data_dir != Path.home() / ".debate-research" / "test"


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
def test_no_committed_profile_contains_anything_that_looks_like_a_secret() -> None:
    """A profile file is committed, so a secret in one is a secret published."""
    assert REPOSITORY_ROOT is not None
    secret_fields = ("contact_email", "semantic_scholar_api_key", "caselist_token")
    for path in sorted((REPOSITORY_ROOT / "config" / "profiles").glob("*.toml")):
        body = "\n".join(
            line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
        )
        for field in secret_fields:
            assert f"{field} =" not in body, f"{path.name} assigns the secret {field}"


@pytest.mark.skipif(REPOSITORY_ROOT is None, reason="not running from a source checkout")
def test_the_example_env_file_documents_every_secret_without_setting_one() -> None:
    assert REPOSITORY_ROOT is not None
    body = (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")

    for variable in (
        "DEBATE_PROVIDERS__CASELIST_TOKEN",
        "DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY",
        "DEBATE_PROVIDERS__CONTACT_EMAIL",
    ):
        assert variable in body
        # Documented, but commented out: copying the example must not configure anything.
        assert f"\n{variable}=" not in body


def test_the_provider_names_configuration_accepts_are_the_ones_e07_builds() -> None:
    assert {member.value for member in SearchProviderName} == {
        "openalex",
        "crossref",
        "semantic_scholar",
        "rss",
        "gdelt",
    }
