"""A missing or expired session names the hint whoever built the adapter gave it (`v1-e40-t28`).

Every record reason a run writes for a session that is not usable ends with the S3 adapter's login
hint, :attr:`~debate_core.integrations.s3.errors.S3Call.login_hint`: the publish stage's, the parse
stage's, the report stage's, the search index stage's and the suppression list's fallback. It was
`aws sso login …` whatever ran the command, and a cloud run has a task role, not an SSO session. The
composition root now gives the adapters the cloud run's hint (`login_hint=`), and these tests hold
each adapter it builds for a run to it. Given none, every word is as before: the local and hand-run
cases. Which hint the composition root gives is
`packages/debate_cli/tests/bucket_mode/test_bucket_mode_login_hint_names_the_task_role.py`'s.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Final

import pytest
from botocore.exceptions import NoCredentialsError, UnauthorizedSSOTokenError

from debate_core.application.errors import StoreCredentialsExpired
from debate_core.integrations.s3 import (
    S3Call,
    S3EvidenceObjectStore,
    S3EvidenceVersionStore,
    translate_s3_error,
)
from debate_core.integrations.s3.run_lock_object import S3LockObject
from debate_core.integrations.s3.version_directories import S3VersionDirectories

from .test_s3_error_mapping import BLOB_KEY, BUCKET, PROFILE, client_error

if TYPE_CHECKING:  # pragma: no cover - import for the type checker only
    from mypy_boto3_s3.client import S3Client

pytestmark = pytest.mark.anyio

THE_CLOUD_RUNS_HINT: Final = "a hint the composition root gave"
"""What the adapter is given: any sentence; the composition root's own is held where it is chosen."""

THE_PROFILES_LOGIN: Final = f"aws sso login --profile {PROFILE}"
NO_PROFILES_LOGIN: Final = "aws sso login (or set AWS_PROFILE to the evidence profile for this environment)"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ------------------------------------------------------------------------------------------------
# The call's hint
# ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [UnauthorizedSSOTokenError(), NoCredentialsError(), client_error("ExpiredToken", status=403)],
    ids=["unauthorized-sso-token", "no-credentials", "expired-mid-request"],
)
@pytest.mark.parametrize(
    ("profile", "given", "hint"),
    [
        (None, THE_CLOUD_RUNS_HINT, THE_CLOUD_RUNS_HINT),
        (PROFILE, THE_CLOUD_RUNS_HINT, THE_CLOUD_RUNS_HINT),
        (PROFILE, None, THE_PROFILES_LOGIN),
        (None, None, NO_PROFILES_LOGIN),
    ],
    ids=["given-no-profile", "given-a-profile", "the-profiles-login", "no-profiles-login"],
)
def test_a_session_that_is_not_usable_names_the_hint_given_or_else_the_login(
    error: Exception, profile: str | None, given: str | None, hint: str
) -> None:
    call = S3Call(
        operation="GetObject",
        bucket=BUCKET,
        entity="snapshot blob",
        key=BLOB_KEY,
        profile=profile,
        given_login_hint=given,
    )

    refused = translate_s3_error(error, call)

    assert isinstance(refused, StoreCredentialsExpired)
    assert refused.hint == hint
    assert str(refused).endswith(f": {hint}")
    if given is not None:
        assert "aws sso login" not in str(refused)


# ------------------------------------------------------------------------------------------------
# Every adapter the composition root builds for a run carries it
# ------------------------------------------------------------------------------------------------


def no_session(**_: Any) -> None:
    """What botocore raises when it finds no credentials to sign with."""
    raise NoCredentialsError


type Adapter = Callable[[S3Client, str | None], Callable[[], Awaitable[object] | object]]

ADAPTERS: Final[dict[str, Adapter]] = {
    "evidence_object_store": lambda client, hint: (
        lambda: S3EvidenceObjectStore(
            bucket=BUCKET, client=client, profile=PROFILE, login_hint=hint
        ).list_objects("reports/")
    ),
    "version_store": lambda client, hint: (
        lambda: S3EvidenceVersionStore(
            bucket=BUCKET, client=client, profile=PROFILE, login_hint=hint
        ).list_versions("raw/")
    ),
    "version_directories": lambda client, hint: (
        lambda: S3VersionDirectories(
            bucket=BUCKET, client=client, profile=PROFILE, login_hint=hint
        ).caselists()
    ),
    "run_lock_object": lambda client, hint: (
        lambda: S3LockObject(
            bucket=BUCKET, key="reports/sync/run-lock.json", client=client, profile=PROFILE, login_hint=hint
        ).read()
    ),
}
"""One read of each, through its own error mapping: the evidence bucket's object store (the publish,
the report stage, the suppression list's bucket copy), its version store (`caselist status`), the
parsed store's version directories (the retention), and the run lock's object."""


@pytest.mark.parametrize("adapter", list(ADAPTERS))
@pytest.mark.parametrize(
    ("given", "hint"), [(THE_CLOUD_RUNS_HINT, THE_CLOUD_RUNS_HINT), (None, THE_PROFILES_LOGIN)]
)
async def test_each_adapter_names_the_hint_it_was_given_or_else_the_login(
    s3_client: S3Client, adapter: str, given: str | None, hint: str
) -> None:
    s3_client.meta.events.register("before-sign.s3", no_session)
    read = ADAPTERS[adapter](s3_client, given)

    with pytest.raises(StoreCredentialsExpired) as refused:
        answer = read()
        if isinstance(answer, Awaitable):
            await answer

    assert refused.value.hint == hint
