"""The caselist_token store: keychain and 0600 file backends, and the gitignore that covers the file.

`docs/policies/caselist-data-use.md` E34 gate 3: the token lives in the macOS keychain or a 0600
gitignored file, and the password is never stored. Checked here rather than trusted.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from debate_core.application.settings import CaselistTokenBackend
from debate_core.integrations.opencaselist.token_store import (
    DEFAULT_SECRET_FILE,
    KEYRING_SERVICE,
    CaselistTokenStore,
    CaselistTokenUnreadable,
    FileTokenBackend,
    InsecureTokenFile,
    KeyringTokenBackend,
    KeyringUnavailable,
    default_secret_file,
)

from .conftest import InMemoryKeyring

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def file_store(path: Path) -> CaselistTokenStore:
    return CaselistTokenStore(FileTokenBackend(path), clock=lambda: NOW)


def test_the_token_file_is_created_0600_in_a_0700_directory(tmp_path: Path, fake_token: str) -> None:
    path = default_secret_file(tmp_path / "data")
    file_store(path).save(SecretStr(fake_token), expires_at=NOW + timedelta(days=14))

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["caselist_token"], "no temporary file left behind"


def test_a_saved_token_round_trips_as_a_secret(tmp_path: Path, fake_token: str) -> None:
    store = file_store(tmp_path / "secrets" / "caselist_token")
    store.save(SecretStr(fake_token), expires_at=NOW + timedelta(days=14))

    loaded = store.load()

    assert loaded is not None
    assert loaded.token.get_secret_value() == fake_token
    assert fake_token not in repr(loaded)
    assert loaded.expires_at == NOW + timedelta(days=14)
    assert loaded.backend == "file"
    assert not loaded.expired(NOW)
    assert loaded.expired(NOW + timedelta(days=15))


def test_the_token_file_holds_no_password_or_username(
    tmp_path: Path, fake_token: str, fake_password: str, fake_username: str
) -> None:
    path = tmp_path / "secrets" / "caselist_token"
    file_store(path).save(SecretStr(fake_token), expires_at=None)

    stored = path.read_text(encoding="utf-8")
    assert fake_password not in stored
    assert fake_username not in stored
    assert set(__import__("json").loads(stored)) == {"token", "stored_at", "expires_at", "last_validated_at"}


def test_a_token_file_others_can_read_is_refused_not_used(tmp_path: Path, fake_token: str) -> None:
    path = tmp_path / "secrets" / "caselist_token"
    file_store(path).save(SecretStr(fake_token), expires_at=None)
    os.chmod(path, 0o644)

    with pytest.raises(InsecureTokenFile) as refused:
        file_store(path).load()

    assert fake_token not in str(refused.value)
    assert "0600" in str(refused.value)


def test_an_unreadable_token_record_says_so_without_quoting_it(tmp_path: Path, fake_token: str) -> None:
    path = tmp_path / "secrets" / "caselist_token"
    FileTokenBackend(path).write(f'{{"token": "{fake_token}", "stored_at": "not a date"}}')

    with pytest.raises(CaselistTokenUnreadable) as unreadable:
        file_store(path).load()

    assert fake_token not in str(unreadable.value)
    assert unreadable.value.__cause__ is None
    assert unreadable.value.__suppress_context__


def test_no_token_stored_loads_as_none_and_logout_reports_nothing_deleted(tmp_path: Path) -> None:
    store = file_store(tmp_path / "secrets" / "caselist_token")
    assert store.load() is None
    assert store.delete() is False


def test_logout_deletes_the_token(tmp_path: Path, fake_token: str) -> None:
    store = file_store(tmp_path / "secrets" / "caselist_token")
    store.save(SecretStr(fake_token), expires_at=None)

    assert store.delete() is True
    assert store.load() is None


def test_recording_a_validation_stamps_the_stored_token(tmp_path: Path, fake_token: str) -> None:
    times = iter([NOW, NOW, NOW + timedelta(hours=3)])
    store = CaselistTokenStore(FileTokenBackend(tmp_path / "caselist_token"), clock=lambda: next(times))
    store.save(SecretStr(fake_token), expires_at=None)

    store.record_validation()

    loaded = store.load()
    assert loaded is not None
    assert loaded.last_validated_at == NOW + timedelta(hours=3)
    assert loaded.token.get_secret_value() == fake_token


def test_the_keyring_backend_keeps_one_item_per_environment(
    memory_keyring: InMemoryKeyring, fake_token: str
) -> None:
    dev = CaselistTokenStore(KeyringTokenBackend(account="dev", keyring=memory_keyring), clock=lambda: NOW)
    prod = CaselistTokenStore(KeyringTokenBackend(account="prod", keyring=memory_keyring), clock=lambda: NOW)
    dev.save(SecretStr(fake_token), expires_at=None)

    loaded = dev.load()
    assert loaded is not None and loaded.token.get_secret_value() == fake_token
    assert loaded.backend == "keyring"
    assert prod.load() is None
    assert set(memory_keyring.items) == {(KEYRING_SERVICE, "dev")}
    assert dev.delete() is True
    assert memory_keyring.items == {}


def test_auto_uses_the_keychain_when_one_is_usable(tmp_path: Path, memory_keyring: InMemoryKeyring) -> None:
    store = CaselistTokenStore.for_settings(
        CaselistTokenBackend.AUTO,
        account="dev",
        secret_file=tmp_path / "caselist_token",
        keyring=memory_keyring,
    )
    assert store.backend_name == "keyring"


def test_auto_falls_back_to_the_file_when_no_keychain_is_usable(tmp_path: Path) -> None:
    store = CaselistTokenStore.for_settings(
        CaselistTokenBackend.AUTO,
        account="dev",
        secret_file=tmp_path / "caselist_token",
        keyring_usable=lambda: False,
    )
    assert store.backend_name == "file"
    assert store.location == str(tmp_path / "caselist_token")


def test_an_explicit_keyring_choice_with_no_keychain_is_refused(tmp_path: Path) -> None:
    with pytest.raises(KeyringUnavailable):
        CaselistTokenStore.for_settings(
            CaselistTokenBackend.KEYRING,
            account="dev",
            secret_file=tmp_path / "caselist_token",
            keyring_usable=lambda: False,
        )


def test_an_explicit_file_choice_never_touches_the_keychain(tmp_path: Path) -> None:
    def keyring_consulted() -> bool:
        raise AssertionError("the keychain was consulted for a file-backed store")

    store = CaselistTokenStore.for_settings(
        CaselistTokenBackend.FILE,
        account="dev",
        secret_file=tmp_path / "caselist_token",
        keyring_usable=keyring_consulted,
    )
    assert store.backend_name == "file"


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git to ask what .gitignore covers")
@pytest.mark.parametrize(
    "relative",
    [
        str(DEFAULT_SECRET_FILE),
        str(Path(".data") / "dev" / DEFAULT_SECRET_FILE),
        str(Path("config") / DEFAULT_SECRET_FILE),
        str(Path("anywhere") / "caselist_token"),
    ],
)
def test_the_token_file_path_is_covered_by_gitignore(relative: str) -> None:
    """Wherever a data directory points inside a checkout, its token file is ignored.

    `--no-index` asks what the ignore rules say about a path whether or not it exists, which is the
    question: the file must be unaddable before anyone has made it.
    """
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", relative],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert result.returncode == 0, f"{relative} is not covered by .gitignore"
