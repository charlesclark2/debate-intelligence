"""The token-authorized calls the account and enrolment pages make (ADR-0019 (d) 3 and 5).

`GetUser`, `AssociateSoftwareToken`, `VerifySoftwareToken`, `SetUserMFAPreference`,
`UpdateUserAttributes`, `VerifyUserAttribute` and `DeleteUserAttributes`, each authorized by the
student's own access token through the unsigned client
(:func:`~debate_core.integrations.cognito.client.build_cognito_self_service_client`). The secret
`AssociateSoftwareToken` returns is wrapped at once in an
:class:`~debate_core.application.tub.identity.AuthenticatorSecret`, which prints as a placeholder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from debate_core.application.ports.tub import AccountSelfService, AccountStanding, CodeRefused
from debate_core.application.tub.identity import AuthenticatorSecret
from debate_core.integrations.cognito.errors import mapped_cognito_errors

if TYPE_CHECKING:
    from mypy_boto3_cognito_idp import CognitoIdentityProviderClient
    from mypy_boto3_cognito_idp.type_defs import (
        EmailMfaSettingsTypeTypeDef,
        SoftwareTokenMfaSettingsTypeTypeDef,
    )

__all__ = ["AUTHENTICATOR_DEVICE_NAME", "CognitoSelfService"]

AUTHENTICATOR_DEVICE_NAME: Final = "Authenticator app"
_AUTHENTICATOR: Final = "SOFTWARE_TOKEN_MFA"
_EMAIL_FACTOR: Final = "EMAIL_OTP"


class CognitoSelfService(AccountSelfService):
    """:class:`~debate_core.application.ports.tub.AccountSelfService` over Cognito's token-authorized API."""

    def __init__(self, *, client: CognitoIdentityProviderClient) -> None:
        self._client = client

    def standing(self, access_token: str) -> AccountStanding:
        with mapped_cognito_errors("GetUser", token_authorized=True):
            response = self._client.get_user(AccessToken=access_token)
        attributes = {item["Name"]: item.get("Value", "") for item in response.get("UserAttributes", [])}
        factors = response.get("UserMFASettingList", [])
        email = attributes.get("email") or None
        return AccountStanding(
            has_authenticator=_AUTHENTICATOR in factors,
            email=email,
            email_verified=email is not None and attributes.get("email_verified") == "true",
            email_factor_enabled=_EMAIL_FACTOR in factors,
        )

    def begin_authenticator(self, access_token: str) -> AuthenticatorSecret:
        with mapped_cognito_errors("AssociateSoftwareToken", token_authorized=True):
            response = self._client.associate_software_token(AccessToken=access_token)
        return AuthenticatorSecret(response.get("SecretCode", ""))

    def confirm_authenticator(self, access_token: str, code: str) -> None:
        with mapped_cognito_errors("VerifySoftwareToken", token_authorized=True, code_kind="authenticator"):
            response = self._client.verify_software_token(
                AccessToken=access_token, UserCode=code, FriendlyDeviceName=AUTHENTICATOR_DEVICE_NAME
            )
        if response.get("Status") != "SUCCESS":
            raise CodeRefused("authenticator")

    def set_second_factors(self, access_token: str, *, authenticator: bool, email: bool) -> None:
        """Turn the email factor on or off, and the authenticator on when asked; with both, prefer neither.

        The authenticator's setting is sent only to turn it on. An account with none would be refused a
        setting for a factor it does not have, and "off" for it is never wanted here: the app never
        leaves an account without its authenticator.
        """
        both = authenticator and email
        email_settings: EmailMfaSettingsTypeTypeDef = {"Enabled": email, "PreferredMfa": email and not both}
        with mapped_cognito_errors("SetUserMFAPreference", token_authorized=True):
            if authenticator:
                token_settings: SoftwareTokenMfaSettingsTypeTypeDef = {
                    "Enabled": True,
                    "PreferredMfa": not both,
                }
                self._client.set_user_mfa_preference(
                    AccessToken=access_token,
                    SoftwareTokenMfaSettings=token_settings,
                    EmailMfaSettings=email_settings,
                )
            else:
                self._client.set_user_mfa_preference(
                    AccessToken=access_token, EmailMfaSettings=email_settings
                )

    def set_backup_email(self, access_token: str, email: str) -> None:
        with mapped_cognito_errors("UpdateUserAttributes", token_authorized=True):
            self._client.update_user_attributes(
                AccessToken=access_token, UserAttributes=[{"Name": "email", "Value": email}]
            )

    def confirm_backup_email(self, access_token: str, code: str) -> None:
        with mapped_cognito_errors("VerifyUserAttribute", token_authorized=True, code_kind="email"):
            self._client.verify_user_attribute(AccessToken=access_token, AttributeName="email", Code=code)

    def remove_backup_email(self, access_token: str) -> None:
        with mapped_cognito_errors("DeleteUserAttributes", token_authorized=True):
            self._client.delete_user_attributes(AccessToken=access_token, UserAttributeNames=["email"])
