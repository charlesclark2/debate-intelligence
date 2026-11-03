"""The function's two SecureString parameters, read once per cold start (ADR-0019 (d), Keys and the secret).

`/debate-<env>-tub/client-secret` and `/debate-<env>-tub/cookie-keys`, by name, with
`ssm:GetParameter`, which is all the function's role grants on Parameter Store. The value is
returned to the composition root and never logged; an error names the parameter and never its
value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from debate_core.application.errors import NotFound, StoreAccessDenied, StoreUnavailable

if TYPE_CHECKING:
    from mypy_boto3_ssm import SSMClient

__all__ = ["build_ssm_client", "read_secure_parameter"]


def build_ssm_client(*, region: str) -> SSMClient:
    """A Parameter Store client signed with the function's role."""
    return boto3.session.Session(region_name=region).client("ssm")  # pyright: ignore[reportUnknownMemberType]


def read_secure_parameter(client: SSMClient, name: str) -> str:
    """The decrypted value of the SecureString parameter `name`."""
    try:
        response = client.get_parameter(Name=name, WithDecryption=True)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        if code == "ParameterNotFound":
            raise NotFound("parameter", name) from error
        if code == "AccessDeniedException":
            raise StoreAccessDenied("GetParameter", name) from error
        raise StoreUnavailable("GetParameter", name, code or "an unknown response") from error
    except BotoCoreError as error:
        raise StoreUnavailable("GetParameter", name, type(error).__name__) from error
    return response["Parameter"].get("Value", "")
