"""Reading `expected_publish.json`, and turning its body names into the keys a test asserts on.

`expected_publish.json` is written by hand from the member tables in `build_synthetic_archives.py`
(working agreements §6). It names each snapshot's sources by :data:`DOCUMENT_BODIES` entry rather
than by digest, so a reader can check it against the fixture's tables without running anything;
the helpers here do the one mechanical step left — hashing a body's bytes and spelling out the key
it must be published under — without calling any code from `debate_core`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tests.fixtures.caselist.build_synthetic_archives import DOCUMENT_BODIES, SYNTHETIC_CASELIST

__all__ = [
    "EXPECTED_PUBLISH_PATH",
    "FICTIONAL_IDENTIFIERS",
    "digest_of_body",
    "expected_publish",
    "expected_source_key",
]

EXPECTED_PUBLISH_PATH = Path(__file__).parent / "expected_publish.json"

FICTIONAL_IDENTIFIERS: tuple[str, ...] = (
    # Schools, as the synthetic archives' directories name them.
    "Maple Grove",
    "Cedar Hollow",
    "Northgate Prep",
    "Riverbend Academy",
    "Westfield",
    # Team codes.
    "QX",
    "ZaLu",
    "BeCo",
    "MnPr",
    # Tournaments, which with a team code place two students at one round.
    "Grove City Invitational",
    "Harbor Classic",
    "Ridgeline Round Robin",
    "Seaside Cup",
    "Bayview Open",
    # Filename fragments no digest or date can contain.
    ".docx",
    ".pdf",
    "notes about the harbor round",
)
"""Everything in the synthetic archives that personal-data rule 3 and 4 keep out of keys, object
metadata, logs and error messages (`docs/policies/caselist-data-use.md`). The real equivalents are
exactly what a leak would expose; these are invented and safe to write in a test."""


def expected_publish() -> dict[str, Any]:
    """The hand-written expectation for publishing the three synthetic weeks."""
    loaded = json.loads(EXPECTED_PUBLISH_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded  # pyright: ignore[reportUnknownVariableType]


def digest_of_body(name: str) -> str:
    """The SHA-256 of one synthetic document body, from the fixture's own bytes."""
    return hashlib.sha256(DOCUMENT_BODIES[name]).hexdigest()


def expected_source_key(name: str) -> str:
    """The bucket key one synthetic body must be published under, spelled out in full."""
    digest = digest_of_body(name)
    return f"raw/caselist/{SYNTHETIC_CASELIST}/sha256/{digest[0:2]}/{digest[2:4]}/{digest}"
