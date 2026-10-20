"""The pilot app's configuration: environment variables, and the two secrets read at cold start.

v1-e39-t04's Terraform sets these on the function (`infrastructure/modules/evidence_search/main.tf`):

| Variable | Used for |
|---|---|
| `TUB_ENVIRONMENT` | `dev` or `prod`: the authenticator's label, and nothing that decides access |
| `TUB_PUBLIC_ORIGIN` | the pilot's own origin: redirect URIs, the `Origin` check (ADR-0019 (b) 3) |
| `TUB_LOGIN_ORIGIN` | managed login's origin |
| `TUB_USER_POOL_ID`, `TUB_CLIENT_ID` | the ID token's issuer and audience |
| `TUB_CLIENT_SECRET_PARAMETER`, `TUB_COOKIE_KEYS_PARAMETER` | the two SecureString parameters |
| `TUB_AUDIT_LOG_GROUP` | where the account page's audit records go |

The app never reads its origin from a `Host` or `X-Forwarded-*` header: CloudFront's origin request
policy drops the viewer's `Host`, and a forwarded one is the viewer's to choose.

**The cookie keys** are a JSON object `{"current": ..., "previous": ...}`, each 32 random bytes in
base64. Terraform creates the parameter with `{"placeholder": ...}` and the operator replaces it
(the runbook's step 6). :func:`parse_cookie_keys` refuses the placeholder, and anything else that
is not two 32-byte keys, so an app started before that step does not start at all: the Lambda Web
Adapter's readiness check never answers and the deploy script's `/healthz` check fails.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import urlsplit

__all__ = [
    "COOKIE_KEY_BYTES",
    "ConfigurationMissing",
    "CookieKeys",
    "CookieKeysNotSet",
    "PilotConfiguration",
    "parse_cookie_keys",
]

COOKIE_KEY_BYTES: Final = 32
_DEFAULT_REGION: Final = "us-east-1"


class ConfigurationMissing(RuntimeError):
    """A variable the app needs is unset or malformed. Names the variable, never a value."""

    def __init__(self, variable: str, problem: str = "is not set") -> None:
        self.variable = variable
        super().__init__(f"{variable} {problem}")


class CookieKeysNotSet(RuntimeError):
    """The cookie-keys parameter does not hold two 32-byte keys: often still Terraform's placeholder."""

    def __init__(self, problem: str) -> None:
        super().__init__(
            f"the session cookie keys are not usable: {problem}. Write them with the runbook's "
            "put-parameter step (docs/runbooks/evidence-search.md, step 6)"
        )


@dataclass(frozen=True, slots=True)
class CookieKeys:
    """The key cookies are sealed with, and the one before it, which still opens older cookies."""

    current: bytes = field(repr=False)
    previous: bytes = field(repr=False)


def parse_cookie_keys(raw: str) -> CookieKeys:
    """The keys in the parameter's value, or :class:`CookieKeysNotSet` saying what is wrong."""
    try:
        document = json.loads(raw)
    except ValueError as error:
        raise CookieKeysNotSet("the value is not JSON") from error
    if not isinstance(document, dict):
        raise CookieKeysNotSet("the value is not a JSON object")
    if "placeholder" in document:
        raise CookieKeysNotSet("the parameter still holds Terraform's placeholder")
    if set(document) != {"current", "previous"}:
        raise CookieKeysNotSet('the value must have exactly the keys "current" and "previous"')
    keys: dict[str, bytes] = {}
    for name in ("current", "previous"):
        value = document[name]
        if not isinstance(value, str):
            raise CookieKeysNotSet(f"{name} is not a string")
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise CookieKeysNotSet(f"{name} is not base64") from error
        if len(decoded) != COOKIE_KEY_BYTES:
            raise CookieKeysNotSet(f"{name} is not {COOKIE_KEY_BYTES} bytes")
        keys[name] = decoded
    return CookieKeys(current=keys["current"], previous=keys["previous"])


@dataclass(frozen=True, slots=True)
class PilotConfiguration:
    """Everything the app is told by its environment, checked once."""

    environment: str
    public_origin: str
    login_origin: str
    user_pool_id: str
    client_id: str
    client_secret_parameter: str
    cookie_keys_parameter: str
    audit_log_group: str
    region: str = _DEFAULT_REGION

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> PilotConfiguration:
        def required(name: str) -> str:
            value = environ.get(name, "").strip()
            if not value:
                raise ConfigurationMissing(name)
            return value

        configuration = cls(
            environment=required("TUB_ENVIRONMENT"),
            public_origin=_origin(required("TUB_PUBLIC_ORIGIN"), "TUB_PUBLIC_ORIGIN"),
            login_origin=_origin(required("TUB_LOGIN_ORIGIN"), "TUB_LOGIN_ORIGIN"),
            user_pool_id=required("TUB_USER_POOL_ID"),
            client_id=required("TUB_CLIENT_ID"),
            client_secret_parameter=required("TUB_CLIENT_SECRET_PARAMETER"),
            cookie_keys_parameter=required("TUB_COOKIE_KEYS_PARAMETER"),
            audit_log_group=required("TUB_AUDIT_LOG_GROUP"),
            region=environ.get("AWS_REGION", "").strip() or _DEFAULT_REGION,
        )
        return configuration

    @property
    def authenticator_issuer(self) -> str:
        """The name an authenticator app shows beside the code."""
        return (
            "Team evidence search"
            if self.environment == "prod"
            else f"Team evidence search ({self.environment})"
        )


def _origin(value: str, variable: str) -> str:
    """`value` as a bare `https://host` origin, or :class:`ConfigurationMissing`."""
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query:
        raise ConfigurationMissing(variable, "is not an https origin")
    return f"https://{parts.netloc}"
