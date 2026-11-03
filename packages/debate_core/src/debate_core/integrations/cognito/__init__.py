"""The pilot's Cognito adapters (ADR-0019 (d), `v1-e39-t05`).

* :class:`CognitoAccountDirectory`: the administrative API, for the coach's `tub users`.
* :class:`CognitoSelfService`: the token-authorized API, for the account and enrolment pages.
* :class:`CognitoOAuthClient`: managed login's OAuth endpoints, with every ID token checked by
  :class:`CognitoIdTokenVerifier` against the pool's :class:`PublishedKeySet`.

Each translates its failures into :mod:`debate_core.application.errors` and the tub ports'
errors (:mod:`.errors`); no botocore or urllib exception leaves this package.
"""

from debate_core.integrations.cognito.accounts import CognitoAccountDirectory
from debate_core.integrations.cognito.client import (
    PILOT_REGION,
    build_cognito_admin_client,
    build_cognito_self_service_client,
)
from debate_core.integrations.cognito.id_tokens import CognitoIdTokenVerifier, PublishedKeySet, issuer_for
from debate_core.integrations.cognito.oauth import CognitoOAuthClient
from debate_core.integrations.cognito.self_service import CognitoSelfService
from debate_core.integrations.cognito.transport import HttpResponse, HttpTransport, UrllibTransport

__all__ = [
    "PILOT_REGION",
    "CognitoAccountDirectory",
    "CognitoIdTokenVerifier",
    "CognitoOAuthClient",
    "CognitoSelfService",
    "HttpResponse",
    "HttpTransport",
    "PublishedKeySet",
    "UrllibTransport",
    "build_cognito_admin_client",
    "build_cognito_self_service_client",
    "issuer_for",
]
