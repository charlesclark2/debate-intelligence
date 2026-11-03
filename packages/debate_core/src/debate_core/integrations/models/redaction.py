"""What is scrubbed from a cassette before it is written: credentials, signatures and account ids.

A cassette is committed and read in review, so nothing that could authenticate as someone or name
an AWS account may reach one (v1-e05-t03-fake-replay-models, ac4). A cassette is built from the
router's own values, which have no field for a header or a key, but a model's answer, a provider's
request id or an inference profile's ARN are free text, so the whole document is scrubbed rather
than the fields where a secret is expected:

* **By key, at any depth**, whatever the value: authorization and proxy-authorization headers,
  cookies, API keys, AWS access keys, secret keys and session tokens, SigV4 query parameters, and
  account ids (`account`, `account_id`, `aws_account_id`). Keys are compared case-insensitively,
  with `-` and `_` treated alike, so `X-Amz-Security-Token` and `x_amz_security_token` both match.
* **By pattern, in every string**: a SigV4 `Authorization` value from `AWS4-HMAC-SHA256` to the end
  of the string, the value of a `Signature=`, `X-Amz-Signature=`, `X-Amz-Credential=` or
  `X-Amz-Security-Token=`, a `Bearer` token, an AWS access key id (`AKIA…`, `ASIA…`), and any
  twelve-digit number with no letter or digit on either side, which is how an account id appears
  in an ARN or a URL. A run of digits inside a hex digest, such as a fixture key, is left alone.

A scrubbed value becomes :data:`REDACTED`. Numbers are never rewritten; a number is redacted only
under one of the keys. The twelve-digit rule can catch a number that was not an account id; a
cassette with a scrubbed value in its answer replays the scrubbed value, which is the safe side.

What this cannot catch is a person's name or a real card's text: those look like any other text.
Every cassette and fixture is therefore invented, never recorded from real student work, and a
reviewer reads each one (`tests/fixtures/model_cassettes/README.md`).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final, cast

from pydantic import JsonValue

__all__ = ["REDACTED", "redact", "redactions"]

REDACTED: Final = "[REDACTED]"
"""What a scrubbed value is replaced with."""

_SECRET_KEYS: Final = frozenset(
    {
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "x_api_key",
        "api_key",
        "aws_access_key_id",
        "access_key_id",
        "aws_secret_access_key",
        "secret_access_key",
        "aws_session_token",
        "session_token",
        "x_amz_security_token",
        "x_amz_credential",
        "x_amz_signature",
        "account",
        "account_id",
        "aws_account_id",
    }
)

_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"AWS4-HMAC-SHA256\b.*", re.DOTALL), REDACTED),
    (
        re.compile(r"((?:X-Amz-)?(?:Signature|Credential|Security-Token)=)[^&\s,;\"']+", re.IGNORECASE),
        rf"\g<1>{REDACTED}",
    ),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+"), rf"\g<1>{REDACTED}"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), REDACTED),
    (re.compile(r"(?<![0-9A-Za-z])\d{12}(?![0-9A-Za-z])"), REDACTED),
)


def redact(document: JsonValue) -> JsonValue:
    """`document` with every credential, signature and account id replaced by :data:`REDACTED`."""
    if isinstance(document, Mapping):
        mapping = cast(Mapping[str, JsonValue], document)
        return {key: REDACTED if _is_secret_key(key) else redact(value) for key, value in mapping.items()}
    if isinstance(document, list):
        return [redact(item) for item in document]
    if isinstance(document, str):
        return _scrub(document)
    return document


def redactions(document: JsonValue, path: str = "") -> list[str]:
    """Where in `document` :func:`redact` would change something, as dotted paths; empty if nowhere.

    A committed cassette or fixture must have none: the guard test over
    `tests/fixtures/model_cassettes/` and `tests/fixtures/model_outputs/` checks every file.
    """
    if isinstance(document, Mapping):
        mapping = cast(Mapping[str, JsonValue], document)
        found: list[str] = []
        for key, value in mapping.items():
            where = f"{path}.{key}" if path else key
            if _is_secret_key(key) and value != REDACTED:
                found.append(where)
            elif not _is_secret_key(key):
                found.extend(redactions(value, where))
        return found
    if isinstance(document, list):
        return [
            where for index, item in enumerate(document) for where in redactions(item, f"{path}[{index}]")
        ]
    if isinstance(document, str) and _scrub(document) != document:
        return [path or "(document)"]
    return []


def _is_secret_key(key: str) -> bool:
    return key.strip().lower().replace("-", "_") in _SECRET_KEYS


def _scrub(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text
