"""A working folder that no longer exists is read as "no working-folder `.env`", never a crash (`v1-e41-t22`).

On 2026-11-05 a command run from a removed worktree stopped on `FileNotFoundError` from `Path.cwd()`,
which `find_repository_root` and `_default_dotenv_path` called on every startup. Each test here runs
in a folder it has created and removed (`monkeypatch.chdir` puts the process back afterwards).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from debate_core.application import settings as settings_module
from debate_core.application.settings import (
    ConfigurationError,
    Environment,
    find_repository_root,
    load_settings,
    resolve_environment,
    working_folder,
)

KEY = "wf-K3y-4Rt8"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.startswith("DEBATE_"):
            monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def deleted_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run in a folder, then remove it from under the process."""
    folder = tmp_path / "removed-worktree"
    folder.mkdir()
    monkeypatch.chdir(folder)
    folder.rmdir()
    return folder


@pytest.fixture
def profiles(tmp_path: Path) -> Path:
    directory = tmp_path / "profiles"
    directory.mkdir()
    (directory / "dev.toml").write_text(f'[storage]\ndata_dir = "{tmp_path / "dev"}"\n', encoding="utf-8")
    return directory


def test_the_working_folder_is_the_current_folder_while_it_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    assert working_folder() == tmp_path


@pytest.mark.usefixtures("deleted_folder")
def test_a_deleted_working_folder_is_none() -> None:
    assert working_folder() is None


def test_a_working_folder_that_cannot_be_read_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused() -> str:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(os, "getcwd", refused)

    assert working_folder() is None


@pytest.mark.usefixtures("deleted_folder")
def test_no_checkout_is_found_around_a_deleted_folder() -> None:
    assert find_repository_root() is None


@pytest.mark.usefixtures("deleted_folder")
def test_the_environment_resolves_from_a_deleted_folder() -> None:
    assert resolve_environment() == (Environment.DEV, "default")


@pytest.mark.usefixtures("deleted_folder")
def test_settings_load_from_a_deleted_folder(profiles: Path) -> None:
    settings = load_settings(environment="dev", profile_dir=profiles)

    assert settings.environment is Environment.DEV
    assert settings.field_sources["storage.data_dir"] == f"profile:{profiles / 'dev.toml'}"


@pytest.mark.usefixtures("deleted_folder")
def test_the_per_user_file_is_still_read_from_a_deleted_folder(
    profiles: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "home" / ".debate-research"
    folder.mkdir(parents=True)
    (folder / "dev.env").write_text(f"DEBATE_PROVIDERS__API_DATA_GOV_KEY={KEY}\n", encoding="utf-8")
    (folder / "dev.env").chmod(0o600)
    monkeypatch.setattr(settings_module, "user_credentials_directory", lambda: folder)

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert settings.providers.api_data_gov_key is not None
    assert settings.providers.api_data_gov_key.get_secret_value() == KEY


@pytest.mark.parametrize(
    ("variable", "field"),
    [
        ("DEBATE_STORAGE__DATA_DIR", "storage.data_dir"),
        ("DEBATE_CASELIST__INBOX_DIR", "caselist.inbox_dir"),
        ("DEBATE_CASELIST__SECRET_FILE", "caselist.secret_file"),
    ],
)
@pytest.mark.usefixtures("deleted_folder")
def test_a_relative_path_setting_from_a_deleted_folder_is_refused_by_name(
    profiles: Path, monkeypatch: pytest.MonkeyPatch, variable: str, field: str
) -> None:
    monkeypatch.setenv(variable, "relative/place")

    with pytest.raises(ConfigurationError) as caught:
        load_settings(environment="dev", profile_dir=profiles)

    assert str(caught.value) == (
        f"invalid configuration: {field} (from env:{variable}): Value error, is a relative path, and the "
        "folder this command was run from no longer exists, so it is relative to nothing; give an "
        "absolute path"
    )
    assert caught.value.field == field


@pytest.mark.usefixtures("deleted_folder")
def test_an_absolute_or_home_path_setting_from_a_deleted_folder_is_kept(
    profiles: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEBATE_CASELIST__INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("DEBATE_CASELIST__SECRET_FILE", "~/token-file")

    settings = load_settings(environment="dev", profile_dir=profiles)

    assert settings.caselist.inbox_dir == tmp_path / "inbox"
    assert settings.caselist.secret_file == Path.home() / "token-file"
