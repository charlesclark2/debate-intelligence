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
| `TUB_EVIDENCE_BUCKET` | the evidence bucket the search index is fetched from (`v1-e39-t06`) |
| `TUB_RESULT_COUNT_CAP` | optional: how far a search counts its results, 1,000 when unset (`v1-e39-t11`) |
| `TUB_PASSAGE_SHARE_PERCENT` | optional: percent of a passage's words a card holds, 66 unset (`v1-e39-t13`) |
| `TUB_DOWNLOAD_CARD_CAP` | optional: the most cards a download holds, 1 to 30, 8 unset (`v1-e39-t08`) |
| `TUB_DOWNLOAD_SOURCE_XML_BYTES` | optional: the most `document.xml` bytes one download parses, 20,000,000 |

The passage share is the PM's "about two thirds" (`v1-e39-t13`), and is not set by Terraform either.
The two download caps were set from measurements (:mod:`debate_core.application.card_download`
says which); neither variable is set by Terraform, so changing one is an environment override on the
function, and the defaults hold until someone measures otherwise.

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

from debate_core.application.card_download import DEFAULT_DOWNLOAD_CARD_CAP, DEFAULT_DOWNLOAD_SOURCE_XML_BYTES
from debate_core.application.tub.audit import MAX_DOWNLOAD_CARDS
from debate_core.domain.evidence_search import (
    DEFAULT_PASSAGE_SHARE_PERCENT,
    DEFAULT_RESULT_COUNT_CAP,
    MAX_CURSOR_OFFSET,
)

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
_COUNT_CAP_VARIABLE: Final = "TUB_RESULT_COUNT_CAP"
_PASSAGE_SHARE_VARIABLE: Final = "TUB_PASSAGE_SHARE_PERCENT"
_DOWNLOAD_CARD_CAP_VARIABLE: Final = "TUB_DOWNLOAD_CARD_CAP"
_DOWNLOAD_SOURCE_XML_BYTES_VARIABLE: Final = "TUB_DOWNLOAD_SOURCE_XML_BYTES"
_MOST_SOURCE_XML_BYTES: Final = 100_000_000
"""Far above anything the function could read and parse in a request: a bound on a typo, not a setting."""


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
    evidence_bucket: str
    region: str = _DEFAULT_REGION
    result_count_cap: int = DEFAULT_RESULT_COUNT_CAP
    passage_share_percent: int = DEFAULT_PASSAGE_SHARE_PERCENT
    download_card_cap: int = DEFAULT_DOWNLOAD_CARD_CAP
    download_source_xml_bytes: int = DEFAULT_DOWNLOAD_SOURCE_XML_BYTES

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
            evidence_bucket=required("TUB_EVIDENCE_BUCKET"),
            region=environ.get("AWS_REGION", "").strip() or _DEFAULT_REGION,
            result_count_cap=_count_cap(environ.get(_COUNT_CAP_VARIABLE, "").strip()),
            passage_share_percent=_whole_number(
                environ, _PASSAGE_SHARE_VARIABLE, DEFAULT_PASSAGE_SHARE_PERCENT, 100
            ),
            download_card_cap=_whole_number(
                environ, _DOWNLOAD_CARD_CAP_VARIABLE, DEFAULT_DOWNLOAD_CARD_CAP, MAX_DOWNLOAD_CARDS
            ),
            download_source_xml_bytes=_whole_number(
                environ,
                _DOWNLOAD_SOURCE_XML_BYTES_VARIABLE,
                DEFAULT_DOWNLOAD_SOURCE_XML_BYTES,
                _MOST_SOURCE_XML_BYTES,
            ),
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


def _count_cap(value: str) -> int:
    """`TUB_RESULT_COUNT_CAP` as a whole number from 1 to the cursor limit; the default when unset."""
    if not value:
        return DEFAULT_RESULT_COUNT_CAP
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= MAX_CURSOR_OFFSET:
        raise ConfigurationMissing(
            _COUNT_CAP_VARIABLE, f"is not a whole number from 1 to {MAX_CURSOR_OFFSET}"
        )
    return int(value)


def _whole_number(environ: Mapping[str, str], variable: str, default: int, most: int) -> int:
    """`variable` as a whole number from 1 to `most`; `default` when it is unset."""
    value = environ.get(variable, "").strip()
    if not value:
        return default
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= most:
        raise ConfigurationMissing(variable, f"is not a whole number from 1 to {most}")
    return int(value)


def _origin(value: str, variable: str) -> str:
    """`value` as a bare `https://host` origin, or :class:`ConfigurationMissing`."""
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query:
        raise ConfigurationMissing(variable, "is not an https origin")
    return f"https://{parts.netloc}"
