"""AWS profiles signed in as Identity Center roles, under moto, for tests that run a takedown.

`caselist remove --execute` asks the account which role its takedown profile is signed in as before
it does anything (`v1-e29-t08`), and carries on only for the takedown role. A test that runs the
command through the real composition root therefore needs profiles that *are* roles. moto answers
`GetCallerIdentity` with the role a credential assumed, so :func:`sign_in` creates a role named the
way the account names a permission set's, assumes it, and writes the temporary credentials moto
issued into the test's own credentials file under the profile's name.

Moto does not enforce IAM: these roles hold no policy, and a profile signed in as the everyday role
could delete from moto's bucket if the command let it. What a test gets from this module is who a
profile is, not what it may do.

The suffixes are made up, and nothing here names an account: moto invents one and it is never read.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import boto3

__all__ = ["EVERYDAY_ROLE", "TAKEDOWN_ROLE", "sign_in"]

TAKEDOWN_ROLE = "AWSReservedSSO_DebateDevEvidenceRemoval_0123456789abcdef"
"""The role of dev's `DebateDevEvidenceRemoval` permission set, as the account would name it."""

EVERYDAY_ROLE = "AWSReservedSSO_DebateDevEvidenceOperator_fedcba9876543210"
"""The role of dev's `DebateDevEvidenceOperator` permission set."""


def sign_in(credentials_file: Path, roles: Mapping[str, str], *, region: str = "us-east-1") -> None:
    """Rewrite `credentials_file` so that each profile in `roles` is signed in as its role.

    Call it inside `mock_aws()`: the roles live in moto's account for as long as that does. A role
    two profiles share is created once.
    """
    untyped: Any = boto3  # boto3's types cover `s3` alone here
    iam, sts = untyped.client("iam", region_name=region), untyped.client("sts", region_name=region)
    created: dict[str, str] = {}
    sections: list[str] = []
    for profile, role_name in roles.items():
        if role_name not in created:
            created[role_name] = iam.create_role(
                RoleName=role_name,
                Path="/aws-reserved/sso.amazonaws.com/",
                AssumeRolePolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": []}),
            )["Role"]["Arn"]
        issued = sts.assume_role(RoleArn=created[role_name], RoleSessionName="an-operator")["Credentials"]
        sections.append(
            f"[{profile}]\n"
            f"aws_access_key_id = {issued['AccessKeyId']}\n"
            f"aws_secret_access_key = {issued['SecretAccessKey']}\n"
            f"aws_session_token = {issued['SessionToken']}\n"
        )
    credentials_file.write_text("".join(sections), encoding="utf-8")
