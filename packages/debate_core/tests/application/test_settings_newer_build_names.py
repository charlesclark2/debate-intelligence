"""A setting this build does not know is refused, and one a newer build may define says so (`v1-e41-t01`).

An installed build runs beside checkouts that move daily, and a `.env` in the folder a command runs
from is read on every run. When a newer build adds a provider's credential and the `.env` gains it,
the older build refuses the name, as it refuses a typo: an unknown setting is never accepted. What
changes is the hint. A name in a pattern this build reserves (:data:`RESERVED_SETTING_PATTERNS`) gets
one saying a newer build may define it, and how to get past it; any other unknown name gets none.

The values set here are distinctive strings, and every test that sets one asserts it appears nowhere:
not in the message, the hint, the error's attributes or the whole chained traceback. Messages and
hints are written out whole, by hand.
"""

from __future__ import annotations

import os
import traceback
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application.settings import (
    RESERVED_SETTING_PATTERNS,
    ConfigurationError,
    ProviderSettings,
    load_settings,
)

VALUE = "value-of-a-newer-setting-that-must-never-be-printed"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every `DEBATE_*` variable, so a test sees only what it sets itself."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def profiles(tmp_path: Path) -> Path:
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "dev.toml").write_text(
        '[storage]\ndata_dir = "~/fixture-dev"\n[models]\nrouting_file = "config/routing-dev.yaml"\n',
        encoding="utf-8",
    )
    return directory


def dotenv(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def refusal(profiles: Path, env_file: Path) -> ConfigurationError:
    with pytest.raises(ConfigurationError) as refused:
        load_settings(environment="dev", profile_dir=profiles, env_file=env_file)
    return refused.value


def assert_value_appears_nowhere(error: ConfigurationError) -> None:
    everything = "".join(traceback.format_exception(error)) + repr(vars(error)) + str(error.hint)
    assert VALUE not in everything


def test_an_unknown_name_outside_the_reserved_patterns_is_refused_with_no_newer_build_hint(
    profiles: Path, tmp_path: Path
) -> None:
    """The typo protection stays: refused, named with where it came from, and no hint to upgrade."""
    env_file = dotenv(tmp_path, f"DEBATE_HTTP__MAX_RETRIESS={VALUE}")

    error = refusal(profiles, env_file)

    assert str(error) == (
        f"invalid configuration: http.max_retriess (from dotenv:{env_file}): Extra inputs are not permitted"
    )
    assert (error.field, error.source, error.hint) == ("http.max_retriess", f"dotenv:{env_file}", None)
    assert_value_appears_nowhere(error)


def test_a_reserved_name_from_dotenv_is_refused_with_the_newer_build_hint(
    profiles: Path, tmp_path: Path
) -> None:
    env_file = dotenv(tmp_path, f"DEBATE_PROVIDERS__CORE_API_KEY={VALUE}")

    error = refusal(profiles, env_file)

    assert str(error) == (
        f"invalid configuration: providers.core_api_key (from dotenv:{env_file}): "
        "Extra inputs are not permitted"
    )
    assert error.hint == (
        "A newer build may define providers.core_api_key: this build keeps names matching "
        "providers.*_api_key for settings added after it, and refuses each one it does not know. "
        "The .env file is read from the checkout or folder a command runs in, so run the command from "
        "another folder, or install the newer build."
    )
    assert_value_appears_nowhere(error)


def test_a_reserved_name_from_the_process_environment_names_the_variable_to_unset(
    profiles: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEBATE_PROVIDERS__TUB_TOKEN", VALUE)

    error = refusal(profiles, tmp_path / "no.env")

    assert str(error) == (
        "invalid configuration: providers.tub_token (from env:DEBATE_PROVIDERS__TUB_TOKEN): "
        "Extra inputs are not permitted"
    )
    assert error.hint == (
        "A newer build may define providers.tub_token: this build keeps names matching "
        "providers.*_token for settings added after it, and refuses each one it does not know. "
        "Unset DEBATE_PROVIDERS__TUB_TOKEN in this shell, or install the newer build."
    )
    assert_value_appears_nowhere(error)


def test_a_reserved_name_in_a_profile_file_names_the_file(profiles: Path, tmp_path: Path) -> None:
    """A profile directory a newer checkout wrote, read through `DEBATE_PROFILE_DIR` (no secret's value)."""
    profile = profiles / "dev.toml"
    profile.write_text(
        profile.read_text(encoding="utf-8") + "[providers]\ncore_api_key = 'x'\n", encoding="utf-8"
    )

    error = refusal(profiles, tmp_path / "no.env")

    assert error.hint == (
        "A newer build may define providers.core_api_key: this build keeps names matching "
        "providers.*_api_key for settings added after it, and refuses each one it does not know. "
        f"Remove it from the profile file {profile}, or install the newer build."
    )


def test_several_reserved_names_and_a_typo_are_refused_together_and_only_the_reserved_ones_are_hinted(
    profiles: Path, tmp_path: Path
) -> None:
    env_file = dotenv(
        tmp_path,
        f"DEBATE_PROVIDERS__CORE_API_KEY={VALUE}",
        f"DEBATE_PROVIDERS__TUB_TOKEN={VALUE}",
        f"DEBATE_HTTP__MAX_RETRIESS={VALUE}",
    )

    error = refusal(profiles, env_file)

    assert str(error) == (
        f"invalid configuration: http.max_retriess (from dotenv:{env_file}): Extra inputs are not permitted; "
        f"providers.core_api_key (from dotenv:{env_file}): Extra inputs are not permitted; "
        f"providers.tub_token (from dotenv:{env_file}): Extra inputs are not permitted"
    )
    assert error.hint == (
        "A newer build may define providers.core_api_key and providers.tub_token: this build keeps names "
        "matching providers.*_api_key and providers.*_token for settings added after it, and refuses each "
        "one it does not know. The .env file is read from the checkout or folder a command runs in, so run "
        "the command from another folder, or install the newer build."
    )
    assert_value_appears_nowhere(error)


@pytest.mark.parametrize(
    "variable",
    [
        "DEBATE_HTTP__CORE_API_KEY",  # the pattern is the providers group's, not every group's
        "DEBATE_PROVIDERS__OPENALEX_APIKEY",  # a typo of a real key, not the reserved spelling
        "DEBATE_PROVIDERS__CORE_API_KEY_FILE",  # the pattern is matched whole
    ],
)
def test_a_name_near_a_reserved_pattern_but_outside_it_gets_no_hint(
    profiles: Path, tmp_path: Path, variable: str
) -> None:
    error = refusal(profiles, dotenv(tmp_path, f"{variable}={VALUE}"))

    assert error.hint is None
    assert_value_appears_nowhere(error)


def test_a_reserved_spelling_this_build_defines_is_an_ordinary_setting(
    profiles: Path, tmp_path: Path
) -> None:
    env_file = dotenv(tmp_path, f"DEBATE_PROVIDERS__OPENALEX_API_KEY={VALUE}")

    settings = load_settings(environment="dev", profile_dir=profiles, env_file=env_file)

    assert settings.providers.openalex_api_key is not None
    assert settings.providers.openalex_api_key.get_secret_value() == VALUE


def test_the_reserved_patterns_are_few_and_each_is_a_spelling_this_build_already_uses() -> None:
    """Written out, so adding one is a decision a reviewer sees: each follows the providers group's
    own credentials, `openalex_api_key` and `semantic_scholar_api_key`, and `caselist_token`."""
    assert RESERVED_SETTING_PATTERNS == ("providers.*_api_key", "providers.*_token")
    known = set(ProviderSettings.model_fields)
    assert {"openalex_api_key", "semantic_scholar_api_key", "caselist_token"} <= known
