"""What a failure panel prints in place of a whole record: counts, digest prefixes, one closing line.

`caselist status`'s panels were the first to print a summary instead of their `--json` details
(`v1-e30-t24`), and these helpers lived in :mod:`debate_cli.commands.caselist` until `caselist
publish`, `verify`, `caselist parse` and `caselist pull` printed theirs the same way (`v1-e30-t27`).
A panel says what differs by count, names at most :data:`PREFIXES_SHOWN` digests of a kind by their
first twelve characters, and ends with a line saying where every value is in full. The panel is
:attr:`~debate_cli.output.CommandFailure.panel_details`; the envelope's `details` are unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Final

from debate_cli.output import JsonValue
from debate_core.application.caselist.removal_residue import RESIDUE_DIGEST_PREFIX_LENGTH

__all__ = [
    "PREFIXES_SHOWN",
    "by_count",
    "digest_of_key",
    "digest_prefix",
    "every_value_in_full",
    "shorten_digests",
    "some_prefixes",
]

PREFIXES_SHOWN: Final = 3
"""How many digests a line of the failure panel names by prefix before it counts the rest."""

_IN_FULL: Final = "in full under error.details of --json"
_WHOLE_DIGESTS: Final = re.compile(r"\b[0-9a-f]{64}(?:, [0-9a-f]{64})*\b")
"""One whole sha256, or a run of them joined by `, `, as a sentence lists them."""


def digest_prefix(digest: str) -> str:
    """A file's name in a report or a panel: the first twelve characters of its digest."""
    return digest[:RESIDUE_DIGEST_PREFIX_LENGTH]


def digest_of_key(key: str) -> str:
    """The digest a source key ends in: `…/sha256/ab/cd/<digest>`."""
    return key.rsplit("/", 1)[-1]


def some_prefixes(digests: Sequence[str]) -> str:
    """`(sha256 <prefix>, <prefix>, <prefix> and N more)`: the first few, and how many are not named."""
    named = ", ".join(digest_prefix(digest) for digest in digests[:PREFIXES_SHOWN])
    more = len(digests) - PREFIXES_SHOWN
    return f"(sha256 {named} and {more} more)" if more > 0 else f"(sha256 {named})"


def shorten_digests(sentence: str) -> str:
    """`sentence` with each run of whole digests in it replaced by :func:`some_prefixes` of the run.

    For a sentence another layer wrote for the run's record, such as a `caselist pull` stage's
    reason, which names a publish's failed sources whole.
    """
    return _WHOLE_DIGESTS.sub(lambda found: some_prefixes(found.group().split(", ")), sentence)


def by_count(codes: Iterable[str]) -> str:
    """`CHECKSUM_MISMATCH 1, STORE_UNAVAILABLE 30`: each code once, sorted, with how often it came."""
    counts: dict[str, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    return ", ".join(f"{code} {count}" for code, count in sorted(counts.items()))


def every_value_in_full(panel: dict[str, JsonValue], *, every: str = "every value") -> dict[str, JsonValue]:
    """`panel`, ending with the line that says where everything it summarises is: `--json`'s details."""
    panel[every] = _IN_FULL
    return panel
