"""Which role a profile is signed in as: the takedown preflight's first question, asked of STS.

The AWS implementation of :class:`~debate_core.application.ports.caller_identity.CallerIdentity`.
It makes one call, `GetCallerIdentity`, which AWS answers for any credential that can sign a
request: it needs no grant, an explicit deny does not stop it, and it changes nothing. That is why
it can come before everything else a takedown does (`v1-e29-t08`): since `v1-e29-t06` the everyday
profile may do every read the takedown profile may, so nothing the bucket allows tells the two
apart short of a delete.

It is in this package, beside the bucket's adapters, although STS is not S3: it is built from the
same profile as the takedown's S3 client, for the same bucket, and this package is the one place
boto3 is imported.

## What leaves this module

The role's name, and nothing else of the answer. STS returns the account, a user id and the
caller's full identifier; the first two are never read, and the identifier is reduced to the role's
name here and dropped. None of the three is logged, returned or put in an error, so no message
built from this adapter can carry one (`v1-e29-t08`, spec forbidden list). A failure to ask is
translated like every other call in this package (:mod:`debate_core.integrations.s3.errors`) and
names the bucket the credential was for, which the caller already had.

## How long it waits

At most :data:`IDENTITY_TIME_LIMIT_SECONDS`, and then it raises
:class:`~debate_core.application.errors.StoreUnavailable`, saying AWS did not answer
(`v1-e29-t09`). botocore has timeouts of its own, but they are per attempt and it retries: with
packets to AWS dropped, a question could outlast the 60 seconds `ops/launchd/install.sh
--check-launchd` waits for `doctor --evidence-profiles`, and the install that runs the same check
before it writes anything would wait as long. The call runs in a thread of its own, marked as a
daemon, so that a question given up on does not keep the command from exiting while botocore is
still waiting: a thread from asyncio's own pool would be waited for at the end of the run.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import threading
from collections.abc import Mapping
from typing import Final, Protocol, cast

from debate_core.application.errors import StoreUnavailable
from debate_core.integrations.s3.client import build_sts_client
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors

__all__ = ["IDENTITY_TIME_LIMIT_SECONDS", "StsCallerIdentity"]

IDENTITY_TIME_LIMIT_SECONDS: Final = 10.0
"""How long the question waits for AWS before it reports that AWS did not answer.

STS answers in well under a second, and a session's credentials are fetched first in a second or
two more. Two profiles unanswered take twenty seconds, a third of the 60 seconds
`ops/launchd/install.sh --check-launchd` waits for the agent's check, and a test holds it there.
"""


class _StsClient(Protocol):
    """The one STS operation this adapter calls. boto3 ships no types for it here."""

    def get_caller_identity(self) -> Mapping[str, object]: ...


#: A session of an assumed role, as STS names its caller: the role's name, then the session's. The
#: name has no path, even for a role kept under one, which every Identity Center role is.
_ASSUMED_ROLE_SESSION: Final = re.compile(r"arn:[^:/]+:sts::[^:/]*:assumed-role/(?P<role>[^/]+)/[^/]+")


class StsCallerIdentity:
    """A :class:`~debate_core.application.ports.caller_identity.CallerIdentity` answered by STS.

    Args:
        bucket: The evidence bucket this credential is for. Used only to say, in an error, which
            store's session could not be asked.
        profile: The profile the client was built with, for the `aws sso login` hint.
        profile_setting: The setting `profile`'s name came from, e.g. `"DEBATE_REMOVAL_PROFILE"`.
        client: An already-built STS client. The tests pass moto's.
        region: Used only when `client` is not given.
        endpoint_url: Where the client sends its request instead of AWS; only when `client` is not
            given. The composition root passes the S3 client's, so the two reach one service.
        ignore_configured_endpoints: Whether botocore's own endpoint routes are ignored, as for the
            S3 client (:func:`~debate_core.integrations.s3.client.build_sts_client`).
        time_limit_seconds: How long the question waits for an answer; :data:`IDENTITY_TIME_LIMIT_SECONDS`
            unless a test says otherwise.
    """

    def __init__(
        self,
        *,
        bucket: str,
        profile: str | None = None,
        profile_setting: str | None = None,
        client: object | None = None,
        region: str | None = None,
        endpoint_url: str | None = None,
        ignore_configured_endpoints: bool = False,
        time_limit_seconds: float = IDENTITY_TIME_LIMIT_SECONDS,
    ) -> None:
        self._bucket = bucket
        self._time_limit_seconds = time_limit_seconds
        self._profile = profile
        self._profile_setting = profile_setting
        self._client = cast(
            "_StsClient",
            client
            if client is not None
            else build_sts_client(
                region=region,
                profile=profile,
                profile_setting=profile_setting,
                endpoint_url=endpoint_url,
                ignore_configured_endpoints=ignore_configured_endpoints,
            ),
        )

    async def assumed_role_name(self) -> str | None:
        loop = asyncio.get_running_loop()
        answer: asyncio.Future[str | None] = loop.create_future()

        def settle(outcome: str | None | BaseException) -> None:
            if answer.done():  # given up on already
                return
            if isinstance(outcome, BaseException):
                answer.set_exception(outcome)
            else:
                answer.set_result(outcome)

        def ask() -> None:
            outcome: str | None | BaseException
            try:
                outcome = self._assumed_role_name()
            except BaseException as failed:  # handed to the waiting coroutine, which raises it
                outcome = failed
            # A RuntimeError here is the run that asked having ended, with nobody left waiting.
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(settle, outcome)

        threading.Thread(target=ask, name="sts-get-caller-identity", daemon=True).start()
        try:
            return await asyncio.wait_for(answer, timeout=self._time_limit_seconds)
        except TimeoutError:
            raise StoreUnavailable(
                "GetCallerIdentity",
                f"s3://{self._bucket}",
                f"AWS did not answer within {self._time_limit_seconds:g} seconds",
            ) from None

    def _assumed_role_name(self) -> str | None:
        with mapped_s3_errors(
            S3Call(
                operation="GetCallerIdentity",
                bucket=self._bucket,
                entity="AWS session",
                key="",
                profile=self._profile,
                profile_setting=self._profile_setting,
            )
        ):
            identifier = self._client.get_caller_identity().get("Arn")
        session = _ASSUMED_ROLE_SESSION.fullmatch(identifier) if isinstance(identifier, str) else None
        return session.group("role") if session is not None else None
