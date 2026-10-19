"""Canonical URLs and the page's rel=canonical (skeleton for the red run)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "InvalidUrlError",
    "RelCanonicalDecision",
    "RelCanonicalRule",
    "apply_rel_canonical",
    "canonicalize_url",
]


class InvalidUrlError(ValueError):
    """The input is not an absolute http(s) URL that can be canonicalized."""


def canonicalize_url(url: str) -> str:
    return url


class RelCanonicalRule(StrEnum):
    ABSENT = "absent"
    UNUSABLE = "unusable"
    SAME_SITE = "same_site"
    AMP_CACHE_ORIGIN = "amp_cache_origin"
    CROSS_SITE_REFUSED = "cross_site_refused"


@dataclass(frozen=True, slots=True)
class RelCanonicalDecision:
    canonical_url: str
    rule: RelCanonicalRule
    declared_url: str | None

    @property
    def accepted(self) -> bool:
        return True


def apply_rel_canonical(fetched_url: str, html_canonical: str | None) -> RelCanonicalDecision:
    return RelCanonicalDecision(html_canonical or fetched_url, RelCanonicalRule.SAME_SITE, html_canonical)
