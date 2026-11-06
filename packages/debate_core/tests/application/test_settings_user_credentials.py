"""The per-user credentials file, `~/.debate-research/<env>.env` (`v1-e41-t22`, the PM's ruling of 2026-11-05).

Its place in the order of sources: below the variables and the one `.env`, above the profile. It
holds the four credentials in :data:`USER_CREDENTIAL_VARIABLES` and nothing else, and it is not read
at all when its group or others have any permission on it, or on a system that cannot say.

Every home folder here is under `tmp_path`, with `HOME` pointed at it and the settings' one seam,
`user_credentials_directory`, at its `.debate-research`. The workspace's root `conftest.py` points
that seam at a missing folder for every other test. The values are short invented strings, and
every refusal is checked to carry none of them: not its message, its hint, its attributes or the
whole chained traceback. Expected messages are written out by hand.
"""

from __future__ import annotations

import os
import stat
import traceback
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr

from debate_core.application import settings as settings_module
from debate_core.application.settings import (
    USER_CREDENTIAL_EXCLUSIONS,
    USER_CREDENTIAL_VARIABLES,
    ConfigurationError,
    Environment,
    ProviderSettings,
    load_settings,
    user_credentials_file,
)
from debate_core.application.settings import user_credentials_directory as real_user_credentials_directory

#: Short on purpose: a long sentinel can be shortened with "..." in a report that quotes it.
EMAIL = "pu-Em4il-x7Q"
KEY = "pu-K3y-9Zq2"
OTHER = "pu-0th3r-5Lm"
SENTINELS = (EMAIL, KEY, OTHER)

FOUR_NAMES = (
    "DEBATE_PROVIDERS__CONTACT_EMAIL, DEBATE_PROVIDERS__OPENALEX_API_KEY, "
    "DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY and DEBATE_PROVIDERS__API_DATA_GOV_KEY"
)
DEV_FILE = "~/.debate-research/dev.env"
DEV_SOURCE = f"user-env:{DEV_FILE}"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """No `DEBATE_*` variable, and a working folder outside any checkout with no `.env` in it."""
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    yield


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A home folder under tmp_path, whose `.debate-research` is the per-user folder."""
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setattr(settings_module, "user_credentials_directory", lambda: folder / ".debate-research")
    return folder


@pytest.fixture
def profiles(tmp_path: Path) -> Path:
    directory = tmp_path / "profiles"
    directory.mkdir()
    for environment in ("dev", "prod"):
        (directory / f"{environment}.toml").write_text(
            f'[storage]\ndata_dir = "{tmp_path / environment}"\n', encoding="utf-8"
        )
    return directory


def credentials(home: Path, *lines: str, environment: str = "dev", mode: int = 0o600) -> Path:
    """Write the per-user file for `environment` with `lines`, and give it `mode`."""
    folder = home / ".debate-research"
    folder.mkdir(exist_ok=True)
    path = folder / f"{environment}.env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(mode)
    return path


def refusal(**load: object) -> ConfigurationError:
    with pytest.raises(ConfigurationError) as caught:
        load_settings(**load)  # type: ignore[arg-type]
    error = caught.value
    assert_carries_no_value(error)
    return error


def assert_carries_no_value(error: BaseException) -> None:
    written = "".join(traceback.format_exception(error))
    written += " ".join(str(value) for value in vars(error).values())
    for sentinel in SENTINELS:
        assert sentinel not in written


def secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


# ---------------------------------------------------------------------------------------------
# Where the file is, and where it sits in the order of sources
# ---------------------------------------------------------------------------------------------


def test_the_per_user_folder_is_debate_research_in_the_home_folder(home: Path) -> None:
    assert real_user_credentials_directory() == home / ".debate-research"


def test_every_test_s_per_user_folder_is_one_that_does_not_exist() -> None:
    """The root conftest's guard: no test process reads the operator's real file."""
    folder = settings_module.user_credentials_directory()

    assert folder is not None
    assert not folder.exists()
    assert folder != Path.home() / ".debate-research"


def test_each_environment_has_its_own_file_and_test_has_none(home: Path) -> None:
    assert user_credentials_file(Environment.DEV) == home / ".debate-research" / "dev.env"
    assert user_credentials_file(Environment.PROD) == home / ".debate-research" / "prod.env"
    assert user_credentials_file(Environment.TEST) is None


def test_credentials_in_the_per_user_file_are_read_and_named_by_their_source(home: Path, profiles: Path) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", f"DEBATE_PROVIDERS__API_DATA_GOV_KEY={KEY}")

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert secret(settings.providers.contact_email) == EMAIL
    assert secret(settings.providers.api_data_gov_key) == KEY
    assert settings.field_sources["providers.contact_email"] == DEV_SOURCE
    assert settings.field_sources["providers.api_data_gov_key"] == DEV_SOURCE
    assert settings.field_sources["providers.openalex_api_key"] == "default"


def test_every_one_of_the_four_names_is_read(home: Path, profiles: Path) -> None:
    credentials(
        home,
        f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}",
        f"DEBATE_PROVIDERS__OPENALEX_API_KEY={KEY}",
        f"DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY={OTHER}",
        f"DEBATE_PROVIDERS__API_DATA_GOV_KEY={KEY}",
    )

    providers = load_settings(environment="dev", profile_dir=profiles).providers

    assert secret(providers.contact_email) == EMAIL
    assert secret(providers.openalex_api_key) == KEY
    assert secret(providers.semantic_scholar_api_key) == OTHER
    assert secret(providers.api_data_gov_key) == KEY


def test_prod_reads_prod_env_and_never_dev_env(home: Path, profiles: Path) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")
    credentials(home, f"DEBATE_PROVIDERS__OPENALEX_API_KEY={KEY}", environment="prod")

    settings = load_settings(environment="prod", profile_dir=profiles)

    assert settings.providers.contact_email is None
    assert secret(settings.providers.openalex_api_key) == KEY
    assert settings.field_sources["providers.openalex_api_key"] == "user-env:~/.debate-research/prod.env"


def test_the_test_environment_reads_no_per_user_file(home: Path) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", environment="test")
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", environment="dev")

    settings = load_settings(environment="test")

    assert settings.providers.contact_email is None
    assert settings.field_sources["providers.contact_email"] == "default"


def test_an_exported_variable_wins_over_the_file(
    home: Path, profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", OTHER)

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert secret(settings.providers.contact_email) == OTHER
    assert settings.field_sources["providers.contact_email"] == "env:DEBATE_PROVIDERS__CONTACT_EMAIL"


def test_a_blank_exported_variable_wins_over_the_file_too(
    home: Path, profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """How a person forces Crossref's public pool for one command, as v1-e07-t03's smoke did."""
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")
    monkeypatch.setenv("DEBATE_PROVIDERS__CONTACT_EMAIL", "")

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert secret(settings.providers.contact_email) == ""
    assert settings.field_sources["providers.contact_email"] == "env:DEBATE_PROVIDERS__CONTACT_EMAIL"


def test_a_dotenv_wins_over_the_file(home: Path, profiles: Path, tmp_path: Path) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", f"DEBATE_PROVIDERS__API_DATA_GOV_KEY={KEY}")
    dotenv = tmp_path / "work" / ".env"
    dotenv.write_text(f"DEBATE_PROVIDERS__CONTACT_EMAIL={OTHER}\n", encoding="utf-8")

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert secret(settings.providers.contact_email) == OTHER
    assert settings.field_sources["providers.contact_email"] == f"dotenv:{dotenv}"
    assert secret(settings.providers.api_data_gov_key) == KEY
    assert settings.field_sources["providers.api_data_gov_key"] == DEV_SOURCE


def test_the_file_wins_over_the_profile(home: Path, tmp_path: Path) -> None:
    profiles = tmp_path / "profiles-with-a-credential"
    profiles.mkdir()
    (profiles / "dev.toml").write_text(
        f'[storage]\ndata_dir = "{tmp_path / "dev"}"\n[providers]\ncontact_email = "{OTHER}"\n', encoding="utf-8"
    )
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert secret(settings.providers.contact_email) == EMAIL
    assert settings.field_sources["providers.contact_email"] == DEV_SOURCE


def test_comments_blank_lines_export_and_quotes_are_read_as_in_a_dotenv(home: Path, profiles: Path) -> None:
    credentials(
        home,
        "# the contact email Crossref is sent",
        "",
        f"export DEBATE_PROVIDERS__CONTACT_EMAIL='{EMAIL}'",
        f'DEBATE_PROVIDERS__API_DATA_GOV_KEY="{KEY}"',
        f"DEBATE_PROVIDERS__OPENALEX_API_KEY = {OTHER}",
    )

    providers = load_settings(environment="dev", profile_dir=profiles).providers

    assert secret(providers.contact_email) == EMAIL
    assert secret(providers.api_data_gov_key) == KEY
    assert secret(providers.openalex_api_key) == OTHER


def test_no_file_is_no_layer(home: Path, profiles: Path) -> None:
    settings = load_settings(environment="dev", profile_dir=profiles)

    assert settings.providers.contact_email is None
    assert DEV_SOURCE not in settings.field_sources.values()


# ---------------------------------------------------------------------------------------------
# Credentials only
# ---------------------------------------------------------------------------------------------


def test_the_credentials_are_the_four_provider_names() -> None:
    assert USER_CREDENTIAL_VARIABLES == (
        "DEBATE_PROVIDERS__CONTACT_EMAIL",
        "DEBATE_PROVIDERS__OPENALEX_API_KEY",
        "DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY",
        "DEBATE_PROVIDERS__API_DATA_GOV_KEY",
    )
    assert set(USER_CREDENTIAL_EXCLUSIONS) == {"DEBATE_PROVIDERS__CASELIST_TOKEN"}


def test_every_secret_provider_setting_is_a_credential_or_excluded_by_name() -> None:
    """A secret added to the providers group later fails here until someone decides which it is."""
    secret_fields = {
        f"DEBATE_PROVIDERS__{name.upper()}"
        for name, field in ProviderSettings.model_fields.items()
        if "SecretStr" in str(field.annotation)
    }

    assert secret_fields == set(USER_CREDENTIAL_VARIABLES) | set(USER_CREDENTIAL_EXCLUSIONS)
    assert not set(USER_CREDENTIAL_VARIABLES) & set(USER_CREDENTIAL_EXCLUSIONS)


def test_a_name_that_is_not_a_credential_is_refused_by_file_and_line(home: Path, profiles: Path) -> None:
    credentials(
        home,
        "# a comment",
        f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}",
        f"DEBATE_STORAGE__DATA_DIR=/tmp/{OTHER}",
    )

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == (
        f"{DEV_FILE} line 3: DEBATE_STORAGE__DATA_DIR is not a credential; this file holds only "
        f"{FOUR_NAMES}. Put it in a .env or export it."
    )
    assert error.source == DEV_SOURCE


def test_debate_env_in_the_file_is_refused_and_never_picks_the_environment(home: Path, profiles: Path) -> None:
    credentials(home, "DEBATE_ENV=prod")

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == (
        f"{DEV_FILE} line 1: DEBATE_ENV is not a credential; this file holds only {FOUR_NAMES}. "
        "Put it in a .env or export it."
    )


def test_the_caselist_token_is_refused_with_the_login_hint(home: Path, profiles: Path) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CASELIST_TOKEN={KEY}")

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == (
        f"{DEV_FILE} line 1: DEBATE_PROVIDERS__CASELIST_TOKEN is not read from this file. The "
        "caselist_token is kept by `debate-research caselist auth login`, which knows when it expires; a "
        "copy here would outlive a logout and win over every later login."
    )


def test_a_line_without_an_equals_sign_is_named_by_its_line_number_only(home: Path, profiles: Path) -> None:
    """A bare key pasted on its own line would otherwise be printed as the line's "name"."""
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", KEY)

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == f"{DEV_FILE} line 2 is not NAME=value."


@pytest.mark.parametrize("name", [KEY, f"my {OTHER}", f"DEBATE_PROVIDERS__{OTHER}"])
def test_a_line_whose_name_is_not_a_setting_name_is_named_by_its_line_number_only(
    home: Path, profiles: Path, name: str
) -> None:
    credentials(home, f"{name}=value")

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == f"{DEV_FILE} line 1: its name is not a setting name."


def test_a_name_given_twice_is_refused_with_both_line_numbers(home: Path, profiles: Path) -> None:
    credentials(
        home,
        f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}",
        f"DEBATE_PROVIDERS__API_DATA_GOV_KEY={KEY}",
        "",
        f"DEBATE_PROVIDERS__CONTACT_EMAIL={OTHER}",
    )

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == f"{DEV_FILE} lines 1 and 4 both set DEBATE_PROVIDERS__CONTACT_EMAIL."


def test_every_problem_in_the_file_is_named_at_once(home: Path, profiles: Path) -> None:
    credentials(home, OTHER, "DEBATE_HTTP__MAX_RETRIES=2")

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == (
        f"{DEV_FILE} line 1 is not NAME=value. {DEV_FILE} line 2: DEBATE_HTTP__MAX_RETRIES is not a "
        f"credential; this file holds only {FOUR_NAMES}. Put it in a .env or export it."
    )


# ---------------------------------------------------------------------------------------------
# Who may read it
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o620, 0o602, 0o610, 0o601, 0o644, 0o660, 0o666, 0o777])
def test_a_file_its_group_or_others_have_any_permission_on_is_refused_with_the_chmod_fix(
    home: Path, profiles: Path, mode: int
) -> None:
    """The whole of 0o077, as the caselist token file's rule: 0o620 is refused though no one else may read it."""
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", mode=mode)

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == (
        f"{DEV_FILE} has permissions {stat.filemode(stat.S_IFREG | mode)}, so someone other than its "
        f"owner can read or change it, and it was not read. Run: chmod 600 {DEV_FILE}"
    )
    assert error.source == DEV_SOURCE


@pytest.mark.parametrize("mode", [0o600, 0o400, 0o700])
def test_a_file_only_its_owner_has_permissions_on_is_read(home: Path, profiles: Path, mode: int) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", mode=mode)

    assert secret(load_settings(environment="dev", profile_dir=profiles).providers.contact_email) == EMAIL


def test_the_mode_is_judged_before_any_byte_is_read(
    home: Path, profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", mode=0o644)
    read: list[int] = []

    def reading(descriptor: int) -> bytes:
        read.append(descriptor)
        return b""

    monkeypatch.setattr(settings_module, "_read_open_file", reading)

    error = refusal(environment="dev", profile_dir=profiles)

    assert "chmod 600" in str(error)
    assert read == []


def test_a_symlink_is_judged_by_its_target(home: Path, profiles: Path, tmp_path: Path) -> None:
    (home / ".debate-research").mkdir()
    target = tmp_path / "kept-elsewhere.env"
    target.write_text(f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}\n", encoding="utf-8")
    link = home / ".debate-research" / "dev.env"
    link.symlink_to(target)

    target.chmod(0o644)
    refused = refusal(environment="dev", profile_dir=profiles)
    target.chmod(0o600)
    settings = load_settings(environment="dev", profile_dir=profiles)

    assert "has permissions -rw-r--r--" in str(refused)
    assert secret(settings.providers.contact_email) == EMAIL


def test_a_system_that_cannot_say_who_may_read_the_file_refuses_it(
    home: Path, profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}")
    monkeypatch.setattr(settings_module, "_file_modes_are_posix", lambda: False)

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == (
        f"{DEV_FILE} was not read: this system cannot say who else may read it. Set the credentials as "
        "environment variables instead."
    )


def test_such_a_system_with_no_file_loads_as_ever(
    home: Path, profiles: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings_module, "_file_modes_are_posix", lambda: False)

    assert load_settings(environment="dev", profile_dir=profiles).providers.contact_email is None


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="root reads a 0o000 file")
def test_a_file_its_owner_cannot_read_is_reported_without_its_contents(home: Path, profiles: Path) -> None:
    credentials(home, f"DEBATE_PROVIDERS__CONTACT_EMAIL={EMAIL}", mode=0o000)

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == f"could not read {DEV_FILE}."


def test_a_folder_in_the_file_s_place_is_refused(home: Path, profiles: Path) -> None:
    (home / ".debate-research" / "dev.env").mkdir(parents=True)

    error = refusal(environment="dev", profile_dir=profiles)

    assert str(error) == f"{DEV_FILE} is not a file."
