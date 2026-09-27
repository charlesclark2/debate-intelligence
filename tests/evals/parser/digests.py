"""Keyed digests: how the evaluation names a file without publishing which file it is.

A SHA-256 is not an anonymiser, it is a **join key**. This repository is public and the
OpenCaselist archives are public, so anyone can hash the same corpus and read a committed digest
straight back to `<School>/<TeamCode>/<filename>` — exactly what leaving the file names out was
for. The manifest, the labels and the sampling plan therefore carry an **HMAC-SHA256** over the
file's bytes, or over a paragraph's text, under a key that lives beside the path map in
`~/.debate-intelligence/` and is never committed.

What that costs: nothing CI needs. CI never checks these digests — it has no files to check them
against. The fixture-changed validator still works, because an HMAC over changed content differs
just as a hash does. The operator can still verify, because the operator holds the key.

What it protects: without the key, a committed digest is a random-looking 64 hex characters that
cannot be produced from the public corpus, so it joins to nothing.

**Losing the key** costs the labels' verifiability, not the labels: re-key with
`scripts/select_eval_files.py --rekey`, which rewrites the manifest, the plan and the labels
together. Keep it with the path map; both are the operator's, and neither is in the repository.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from pathlib import Path
from typing import Final

from tests.evals.parser.labels_schema import REPOSITORY_ROOT

__all__ = [
    "DEFAULT_KEY_PATH",
    "KEY_ENVIRONMENT_VARIABLE",
    "MissingDigestKeyError",
    "PlainDigestError",
    "create_key",
    "key_location",
    "keyed_digest",
    "load_key",
    "require_key",
    "refuse_plain_digest",
    "text_digest",
]

KEY_ENVIRONMENT_VARIABLE: Final = "DEBATE_PARSER_EVAL_KEY_FILE"
DEFAULT_KEY_PATH: Final = Path.home() / ".debate-intelligence" / "parser-eval-digest.key"
_KEY_BYTES: Final = 32


class MissingDigestKeyError(RuntimeError):
    """No digest key on this machine. Nothing keyed can be written or checked without it."""


class PlainDigestError(ValueError):
    """A plain hash of corpus content was about to be written somewhere committed."""


def key_location() -> Path:
    configured = os.environ.get(KEY_ENVIRONMENT_VARIABLE)
    return Path(configured).expanduser() if configured else DEFAULT_KEY_PATH


def _inside_repository(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPOSITORY_ROOT)
    except ValueError:
        return False
    return True


def load_key(location: Path | None = None) -> bytes | None:
    """The digest key, or None where this machine has none (a CI runner, a fresh clone)."""
    location = location if location is not None else key_location()
    if _inside_repository(location):
        raise PlainDigestError(
            "the digest key must live outside the repository; a committed key makes every digest "
            "a join key again"
        )
    if not location.is_file():
        return None
    key = bytes.fromhex(location.read_text(encoding="utf-8").strip())
    if len(key) < _KEY_BYTES:
        raise MissingDigestKeyError(f"the digest key at {location.name} is too short to be the one we wrote")
    return key


def create_key(location: Path | None = None) -> Path:
    """Write a new random key, once. Refuses to overwrite: that would orphan every committed digest."""
    location = location if location is not None else key_location()
    if _inside_repository(location):
        raise PlainDigestError("the digest key must live outside the repository")
    if location.exists():
        raise PlainDigestError(
            f"a digest key already exists at {location}; re-keying is deliberate, not a default"
        )
    location.parent.mkdir(parents=True, exist_ok=True)
    location.write_text(secrets.token_hex(_KEY_BYTES) + "\n", encoding="utf-8")
    location.chmod(0o600)
    return location


def require_key(location: Path | None = None) -> bytes:
    key = load_key(location)
    if key is None:
        raise MissingDigestKeyError(
            f"no digest key at {key_location()}; run scripts/select_eval_files.py --rekey on the machine "
            "that holds the corpus, or restore the key from where the path map is kept"
        )
    return key


def keyed_digest(content: bytes, key: bytes) -> str:
    """HMAC-SHA256 of a file's bytes under the evaluation key. Safe to commit."""
    return hmac.new(key, content, hashlib.sha256).hexdigest()


def text_digest(text: str, key: bytes) -> str:
    """HMAC-SHA256 of a paragraph's text. Safe to commit; a plain hash of it would not be."""
    return keyed_digest(text.encode("utf-8"), key)


def refuse_plain_digest(digest: str, content: bytes | str) -> str:
    """Refuse a digest that is the plain hash of the content it names.

    The last gate before anything reaches a committed file. The tooling only ever produces keyed
    digests, so this catches the case where a caller reached for `hashlib` out of habit — the same
    kind of guard as refusing to write the path map inside the repository.
    """
    raw = content.encode("utf-8") if isinstance(content, str) else content
    if digest == hashlib.sha256(raw).hexdigest():
        raise PlainDigestError(
            "refusing to write a plain SHA-256 of corpus content: this repository and the caselist "
            "archives are both public, so a plain digest joins straight back to the file it names. "
            "Use keyed_digest()/text_digest() under the evaluation key."
        )
    return digest
