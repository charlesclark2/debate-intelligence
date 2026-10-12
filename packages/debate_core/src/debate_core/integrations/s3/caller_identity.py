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
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from typing import Final, Protocol, cast

from debate_core.integrations.s3.client import build_sts_client
from debate_core.integrations.s3.errors import S3Call, mapped_s3_errors

__all__ = ["StsCallerIdentity"]


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
    """

    def __init__(
        self,
        *,
        bucket: str,
        profile: str | None = None,
        profile_setting: str | None = None,
        client: object | None = None,
        region: str | None = None,
    ) -> None:
        self._bucket = bucket
        self._profile = profile
        self._profile_setting = profile_setting
        self._client = cast(
            "_StsClient",
            client
            if client is not None
            else build_sts_client(region=region, profile=profile, profile_setting=profile_setting),
        )

    async def assumed_role_name(self) -> str | None:
        return await asyncio.to_thread(self._assumed_role_name)

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
