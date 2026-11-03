"""The two Cognito clients the pilot uses, and the one place each is built.

* **Administrative**, signed with the coach's `TubAccounts` profile, for `tub users`.
* **Token-authorized**, unsigned, for the function's account and enrolment pages. Those calls are
  authorized by the student's access token and Cognito evaluates no IAM policy for them, so the
  function's role holds no Cognito permission (ADR-0019, The function's role) and the client sends
  no AWS signature at all.

A new :class:`boto3.session.Session` per client, so a profile cannot leak from one to another.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from debate_core.integrations.cognito.errors import mapped_cognito_errors

if TYPE_CHECKING:
    from mypy_boto3_cognito_idp import CognitoIdentityProviderClient

__all__ = ["PILOT_REGION", "build_cognito_admin_client", "build_cognito_self_service_client"]

PILOT_REGION: Final = "us-east-1"
"""The pilot's one region (ADR-0010)."""

_TIMEOUTS: Final = Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"})


def build_cognito_admin_client(
    *, profile: str | None, region: str = PILOT_REGION
) -> CognitoIdentityProviderClient:
    """A client for the administrative API, signed with `profile`."""
    with mapped_cognito_errors("CreateSession", profile=profile):
        session = boto3.session.Session(profile_name=profile, region_name=region)
        # `Session.client` is overloaded per service; the stubs installed type cognito-idp, but strict
        # mode still reports the overload set as partly unknown. Narrowed to this line.
        return session.client("cognito-idp", config=_TIMEOUTS)  # pyright: ignore[reportUnknownMemberType]


def build_cognito_self_service_client(*, region: str = PILOT_REGION) -> CognitoIdentityProviderClient:
    """A client for the token-authorized calls, which sends no AWS signature."""
    session = boto3.session.Session(region_name=region)
    return session.client(  # pyright: ignore[reportUnknownMemberType]
        "cognito-idp", config=_TIMEOUTS.merge(Config(signature_version=UNSIGNED))
    )
