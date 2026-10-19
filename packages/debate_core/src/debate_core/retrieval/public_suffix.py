"""Registrable domains from a pinned Public Suffix List snapshot (skeleton for the red run)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "PUBLIC_SUFFIX_LIST_COMMIT",
    "PUBLIC_SUFFIX_LIST_SHA256",
    "PUBLIC_SUFFIX_LIST_VERSION",
    "PublicSuffixRules",
    "bundled_public_suffix_rules",
    "parse_public_suffix_list",
    "registrable_domain",
]

PUBLIC_SUFFIX_LIST_VERSION = "2026-10-17_18-52-06_UTC"
PUBLIC_SUFFIX_LIST_COMMIT = "52b71b3c4576ff77450cc7ebcfc7f34a916af3f9"
PUBLIC_SUFFIX_LIST_SHA256 = "3e6ca639b7ef33f86ec0e6fe9a475857cf2585f28fdf485f38f14d5f00c1c2a4"


@dataclass(frozen=True, slots=True)
class PublicSuffixRules:
    exact: frozenset[str]
    wildcards: frozenset[str]
    exceptions: frozenset[str]
    version: str | None
    commit: str | None


def parse_public_suffix_list(text: str) -> PublicSuffixRules:
    return PublicSuffixRules(frozenset(), frozenset(), frozenset(), None, None)


def bundled_public_suffix_rules() -> PublicSuffixRules:
    return parse_public_suffix_list("")


def registrable_domain(host: str, rules: PublicSuffixRules | None = None) -> str | None:
    return host
