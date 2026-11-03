"""The pool's administrative API, as the coach's `tub users` uses it (ADR-0019 (d), The account lifecycle).

Every call is one the `TubAccounts` permission set grants, on its own pool, and nothing else:
`AdminCreateUser`, `AdminAddUserToGroup`, `AdminRemoveUserFromGroup`, `ListUsers`,
`ListUsersInGroup`, `AdminGetUser`, `AdminListGroupsForUser`, `AdminSetUserPassword`,
`AdminDeleteSoftwareToken`, `AdminUserGlobalSignOut`, `AdminDisableUser`, `AdminEnableUser` and
`AdminDeleteUser` (`infrastructure/modules/evidence_search/pilot_access.tf`). No call reads or
writes an email: the listing asks for the subject alone, and a group's member list is read for
usernames only.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Final

from debate_core.application.ports.tub import AccountDirectory, DirectoryAccount
from debate_core.application.tub.identity import EMAIL_SECOND_FACTOR_GROUP, Role, TemporaryPassword
from debate_core.integrations.cognito.errors import mapped_cognito_errors

if TYPE_CHECKING:
    from mypy_boto3_cognito_idp import CognitoIdentityProviderClient
    from mypy_boto3_cognito_idp.type_defs import AttributeTypeTypeDef

__all__ = ["KNOWN_GROUPS", "CognitoAccountDirectory"]

KNOWN_GROUPS: Final = (Role.COACH.value, Role.STUDENT.value, EMAIL_SECOND_FACTOR_GROUP)
"""The pool's groups. A listing reads each one's members rather than asking every account for its groups."""

_AUTHENTICATOR: Final = "SOFTWARE_TOKEN_MFA"


class CognitoAccountDirectory(AccountDirectory):
    """:class:`~debate_core.application.ports.tub.AccountDirectory` over one Cognito user pool."""

    def __init__(
        self, *, client: CognitoIdentityProviderClient, user_pool_id: str, profile: str | None
    ) -> None:
        self._client = client
        self._pool = user_pool_id
        self._profile = profile

    def create(self, username: str, temporary_password: TemporaryPassword) -> str:
        with mapped_cognito_errors("AdminCreateUser", profile=self._profile, username=username):
            response = self._client.admin_create_user(
                UserPoolId=self._pool,
                Username=username,
                TemporaryPassword=temporary_password.reveal(),
                MessageAction="SUPPRESS",
            )
        return _subject_of(response["User"].get("Attributes", []))

    def add_to_group(self, username: str, group: str) -> None:
        with mapped_cognito_errors("AdminAddUserToGroup", profile=self._profile, username=username):
            self._client.admin_add_user_to_group(UserPoolId=self._pool, Username=username, GroupName=group)

    def remove_from_group(self, username: str, group: str) -> None:
        with mapped_cognito_errors("AdminRemoveUserFromGroup", profile=self._profile, username=username):
            self._client.admin_remove_user_from_group(
                UserPoolId=self._pool, Username=username, GroupName=group
            )

    def get(self, username: str) -> DirectoryAccount:
        with mapped_cognito_errors("AdminGetUser", profile=self._profile, username=username):
            response = self._client.admin_get_user(UserPoolId=self._pool, Username=username)
        return DirectoryAccount(
            username=response["Username"],
            subject=_subject_of(response.get("UserAttributes", [])),
            groups=frozenset(self._groups_of(response["Username"])),
            enabled=response.get("Enabled", True),
        )

    def list_accounts(self) -> Sequence[DirectoryAccount]:
        members = {group: set(self._members_of(group)) for group in KNOWN_GROUPS}
        accounts: list[DirectoryAccount] = []
        token: str | None = None
        while True:
            with mapped_cognito_errors("ListUsers", profile=self._profile):
                if token is None:
                    page = self._client.list_users(UserPoolId=self._pool, AttributesToGet=["sub"])
                else:
                    page = self._client.list_users(
                        UserPoolId=self._pool, AttributesToGet=["sub"], PaginationToken=token
                    )
            for user in page.get("Users", []):
                username = user.get("Username", "")
                accounts.append(
                    DirectoryAccount(
                        username=username,
                        subject=_subject_of(user.get("Attributes", [])),
                        groups=frozenset(group for group, names in members.items() if username in names),
                        enabled=user.get("Enabled", True),
                    )
                )
            token = page.get("PaginationToken")
            if not token:
                return accounts

    def set_temporary_password(self, username: str, temporary_password: TemporaryPassword) -> None:
        with mapped_cognito_errors("AdminSetUserPassword", profile=self._profile, username=username):
            self._client.admin_set_user_password(
                UserPoolId=self._pool,
                Username=username,
                Password=temporary_password.reveal(),
                Permanent=False,
            )

    def remove_authenticator(self, username: str) -> None:
        """Delete the TOTP factor if `AdminGetUser` lists one; an account that never enrolled has none."""
        with mapped_cognito_errors("AdminGetUser", profile=self._profile, username=username):
            response = self._client.admin_get_user(UserPoolId=self._pool, Username=username)
        if _AUTHENTICATOR not in response.get("UserMFASettingList", []):
            return
        with mapped_cognito_errors("AdminDeleteSoftwareToken", profile=self._profile, username=username):
            self._client.admin_delete_software_token(UserPoolId=self._pool, Username=username)

    def sign_out_everywhere(self, username: str) -> None:
        with mapped_cognito_errors("AdminUserGlobalSignOut", profile=self._profile, username=username):
            self._client.admin_user_global_sign_out(UserPoolId=self._pool, Username=username)

    def disable(self, username: str) -> None:
        with mapped_cognito_errors("AdminDisableUser", profile=self._profile, username=username):
            self._client.admin_disable_user(UserPoolId=self._pool, Username=username)

    def enable(self, username: str) -> None:
        with mapped_cognito_errors("AdminEnableUser", profile=self._profile, username=username):
            self._client.admin_enable_user(UserPoolId=self._pool, Username=username)

    def delete(self, username: str) -> None:
        with mapped_cognito_errors("AdminDeleteUser", profile=self._profile, username=username):
            self._client.admin_delete_user(UserPoolId=self._pool, Username=username)

    def _groups_of(self, username: str) -> Iterable[str]:
        token: str | None = None
        while True:
            with mapped_cognito_errors("AdminListGroupsForUser", profile=self._profile, username=username):
                if token is None:
                    page = self._client.admin_list_groups_for_user(UserPoolId=self._pool, Username=username)
                else:
                    page = self._client.admin_list_groups_for_user(
                        UserPoolId=self._pool, Username=username, NextToken=token
                    )
            yield from (group.get("GroupName", "") for group in page.get("Groups", []))
            token = page.get("NextToken")
            if not token:
                return

    def _members_of(self, group: str) -> Iterable[str]:
        token: str | None = None
        while True:
            with mapped_cognito_errors("ListUsersInGroup", profile=self._profile):
                if token is None:
                    page = self._client.list_users_in_group(UserPoolId=self._pool, GroupName=group)
                else:
                    page = self._client.list_users_in_group(
                        UserPoolId=self._pool, GroupName=group, NextToken=token
                    )
            yield from (user.get("Username", "") for user in page.get("Users", []))
            token = page.get("NextToken")
            if not token:
                return


def _subject_of(attributes: Sequence[AttributeTypeTypeDef]) -> str:
    for attribute in attributes:
        if attribute["Name"] == "sub":
            return attribute.get("Value", "")
    return ""
