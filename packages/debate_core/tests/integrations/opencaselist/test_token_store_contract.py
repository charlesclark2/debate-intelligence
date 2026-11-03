"""The token store's contract, held by every backend: the keychain, the 0600 file and Secrets Manager.

One suite, run once per backend, so that what `caselist auth`, the client and the weekly run rely on
is the same whichever backend an installation names (`v1-e40-t02`, ac1). The Secrets Manager backend
runs over a stubbed client: :class:`InMemorySecretsManager` answers the three calls
:class:`~debate_core.integrations.secrets_manager.ManagedSecret` makes, and refuses as Secrets
Manager does, with botocore's own `ClientError`, so the real translation runs. Nothing reaches AWS.

Where a backend's behaviour differs by design, the difference is the contract: Secrets Manager keeps
no validation stamp (the run's role may not write the token) and is never deleted from here.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError
from pydantic import SecretStr

from debate_core.application.settings import CaselistTokenBackend
from debate_core.integrations.opencaselist.token_store import (
    KEYRING_SERVICE,
    CaselistTokenStore,
    CaselistTokenUnreadable,
    FileTokenBackend,
    KeyringTokenBackend,
    SecretsManagerTokenBackend,
    TokenBackend,
    TokenSecretNotConfigured,
    TokenSecretNotDeletable,
)
from debate_core.integrations.secrets_manager import ManagedSecret

from .conftest import InMemoryKeyring

NOW = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)
TOKEN_SECRET = "debate-test-caselist-token"


class InMemorySecretsManager:
    """`get_secret_value`, `put_secret_value` and `describe_secret`, from a dict, counting calls."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.calls: list[str] = []

    def __repr__(self) -> str:
        return "InMemorySecretsManager()"

    def get_secret_value(self, *, SecretId: str) -> Mapping[str, Any]:  # noqa: N803
        self.calls.append("GetSecretValue")
        if SecretId not in self.values:
            raise _refusal("ResourceNotFoundException", "GetSecretValue")
        return {"Name": SecretId, "SecretString": self.values[SecretId], "VersionId": "v1"}

    def put_secret_value(self, *, SecretId: str, SecretString: str) -> Mapping[str, Any]:  # noqa: N803
        self.calls.append("PutSecretValue")
        self.values[SecretId] = SecretString
        return {"Name": SecretId, "VersionId": f"v{len(self.calls)}"}

    def describe_secret(self, *, SecretId: str) -> Mapping[str, Any]:  # noqa: N803
        self.calls.append("DescribeSecret")
        return {"Name": SecretId}


def _refusal(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": f"synthetic {code}"}}, operation)


@dataclass
class BackendWorld:
    """One backend's storage, and a way to open it again as a new process would."""

    kind: str
    open_backend: Callable[[], TokenBackend]
    raw: Callable[[], str | None]
    put_raw: Callable[[str], None]
    secrets_manager: InMemorySecretsManager | None = None

    def store(self, clock: Callable[[], datetime] = lambda: NOW) -> CaselistTokenStore:
        return CaselistTokenStore(self.open_backend(), clock=clock)


@pytest.fixture(params=["keyring", "file", "secretsmanager"])
def world(request: pytest.FixtureRequest, tmp_path: Path) -> BackendWorld:
    kind: str = request.param
    if kind == "keyring":
        keyring = InMemoryKeyring()
        return BackendWorld(
            kind,
            lambda: KeyringTokenBackend(account="test", keyring=keyring),
            lambda: keyring.items.get((KEYRING_SERVICE, "test")),
            lambda text: keyring.set_password(KEYRING_SERVICE, "test", text),
        )
    if kind == "file":
        path = tmp_path / "secrets" / "caselist_token"
        return BackendWorld(
            kind,
            lambda: FileTokenBackend(path),
            lambda: path.read_text(encoding="utf-8") if path.exists() else None,
            lambda text: FileTokenBackend(path).write(text),
        )
    client = InMemorySecretsManager()
    return BackendWorld(
        kind,
        lambda: SecretsManagerTokenBackend(ManagedSecret(client, TOKEN_SECRET)),
        lambda: client.values.get(TOKEN_SECRET),
        lambda text: client.values.__setitem__(TOKEN_SECRET, text),
        secrets_manager=client,
    )


# ------------------------------------------------------------------------------------------------
# What every backend does
# ------------------------------------------------------------------------------------------------


def test_nothing_stored_loads_as_none(world: BackendWorld) -> None:
    assert world.store().load() is None


def test_a_saved_token_is_read_back_by_the_next_process_as_a_secret(
    world: BackendWorld, fake_token: str
) -> None:
    world.store().save(SecretStr(fake_token), expires_at=NOW + timedelta(days=14))

    loaded = world.store().load()

    assert loaded is not None
    round_tripped = loaded.token.get_secret_value() == fake_token
    assert round_tripped, "the token read back is not the token saved"
    shown = fake_token in repr(loaded)
    assert not shown, "the stored token's repr shows the token"
    assert loaded.expires_at == NOW + timedelta(days=14)
    assert loaded.backend == world.kind


def test_the_record_holds_the_token_and_its_times_and_nothing_else(
    world: BackendWorld, fake_token: str, fake_password: str, fake_username: str
) -> None:
    world.store().save(SecretStr(fake_token), expires_at=None)

    raw = world.raw()

    assert raw is not None
    assert set(json.loads(raw)) == {"token", "stored_at", "expires_at", "last_validated_at"}
    credential_kept = fake_password in raw or fake_username in raw
    assert not credential_kept, "the token record holds the Tabroom password or username"


def test_a_new_login_replaces_the_token_before_it(world: BackendWorld, fake_token: str) -> None:
    store = world.store()
    store.save(SecretStr("fixture-token-superseded"), expires_at=None)
    store.save(SecretStr(fake_token), expires_at=None)

    loaded = world.store().load()

    assert loaded is not None
    replaced = loaded.token.get_secret_value() == fake_token
    assert replaced, "the second login's token did not replace the first"


def test_an_unreadable_record_says_so_without_quoting_it(world: BackendWorld, fake_token: str) -> None:
    world.put_raw(f'{{"token": "{fake_token}", "stored_at": "not a date"}}')

    with pytest.raises(CaselistTokenUnreadable) as unreadable:
        world.store().load()

    quoted = fake_token in str(unreadable.value)
    assert not quoted, "the unreadable-record error quotes the token"
    assert unreadable.value.__cause__ is None
    assert unreadable.value.__suppress_context__


def test_the_location_names_where_and_never_what(world: BackendWorld, fake_token: str) -> None:
    store = world.store()
    store.save(SecretStr(fake_token), expires_at=None)

    shown = fake_token in store.location
    assert not shown, "the location shows the token"
    assert store.location


def test_a_validation_stamp_is_kept_exactly_where_the_backend_keeps_stamps(
    world: BackendWorld, fake_token: str
) -> None:
    times = iter([NOW, NOW, NOW + timedelta(hours=3)])
    store = world.store(clock=lambda: next(times))
    store.save(SecretStr(fake_token), expires_at=None)
    before = world.raw()

    store.record_validation()

    loaded = world.store().load()
    assert loaded is not None
    if world.kind == "secretsmanager":
        assert world.raw() == before, "a validation stamp was written to the token secret"
        assert loaded.last_validated_at == NOW
    else:
        assert loaded.last_validated_at == NOW + timedelta(hours=3)
    kept = loaded.token.get_secret_value() == fake_token
    assert kept, "stamping changed the token"


def test_logout_forgets_the_token_where_a_backend_may_and_refuses_where_it_may_not(
    world: BackendWorld, fake_token: str
) -> None:
    store = world.store()
    store.save(SecretStr(fake_token), expires_at=None)

    if world.kind == "secretsmanager":
        with pytest.raises(TokenSecretNotDeletable, match=TOKEN_SECRET):
            store.delete()
        assert world.store().load() is not None
        return
    assert store.delete() is True
    assert world.store().load() is None
    assert store.delete() is False


# ------------------------------------------------------------------------------------------------
# What only the Secrets Manager backend promises
# ------------------------------------------------------------------------------------------------


@pytest.fixture
def secrets_manager() -> InMemorySecretsManager:
    return InMemorySecretsManager()


def test_a_run_reads_the_token_secret_once_and_never_writes_it(
    secrets_manager: InMemorySecretsManager, fake_token: str
) -> None:
    """What the client does on every request: load the token, then stamp it as having worked."""
    CaselistTokenStore(
        SecretsManagerTokenBackend(ManagedSecret(secrets_manager, TOKEN_SECRET)), clock=lambda: NOW
    ).save(SecretStr(fake_token), expires_at=None)
    secrets_manager.calls.clear()
    run = CaselistTokenStore(
        SecretsManagerTokenBackend(ManagedSecret(secrets_manager, TOKEN_SECRET)), clock=lambda: NOW
    )

    for _ in range(5):
        run.load()
        run.record_validation()

    assert secrets_manager.calls == ["GetSecretValue"]


def test_the_login_writes_the_token_secret_and_never_reads_it(
    secrets_manager: InMemorySecretsManager, fake_token: str
) -> None:
    """The login role may write the token and not read it, so a save is one write and no read."""
    store = CaselistTokenStore(
        SecretsManagerTokenBackend(ManagedSecret(secrets_manager, TOKEN_SECRET)), clock=lambda: NOW
    )

    store.save(SecretStr(fake_token), expires_at=None)

    assert secrets_manager.calls == ["PutSecretValue"]
    assert store.backend_name == "secretsmanager"
    assert store.location == f"Secrets Manager secret {TOKEN_SECRET}"


def test_secretsmanager_is_built_only_when_named(tmp_path: Path, memory_keyring: InMemoryKeyring) -> None:
    built: list[str] = []

    def token_secret() -> ManagedSecret:
        built.append("built")
        return ManagedSecret(InMemorySecretsManager(), TOKEN_SECRET)

    for choice in (CaselistTokenBackend.AUTO, CaselistTokenBackend.KEYRING, CaselistTokenBackend.FILE):
        store = CaselistTokenStore.for_settings(
            choice,
            account="test",
            secret_file=tmp_path / "caselist_token",
            keyring=memory_keyring,
            token_secret=token_secret,
        )
        assert store.backend_name != "secretsmanager"
    assert built == [], "a backend other than secretsmanager built a Secrets Manager client"

    store = CaselistTokenStore.for_settings(
        CaselistTokenBackend.SECRETSMANAGER,
        account="test",
        secret_file=tmp_path / "caselist_token",
        token_secret=token_secret,
    )
    assert store.backend_name == "secretsmanager"
    assert built == ["built"]


def test_secretsmanager_without_a_secret_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TokenSecretNotConfigured):
        CaselistTokenStore.for_settings(
            CaselistTokenBackend.SECRETSMANAGER, account="test", secret_file=tmp_path / "caselist_token"
        )
