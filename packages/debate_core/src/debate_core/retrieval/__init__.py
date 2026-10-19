"""Article retrieval: the pure procedures between a URL and a verified snapshot (E04).

This package holds what ArticleService (`debate_core.application`, v1-e04-t05) composes and what can
be decided without a network: canonical URLs and the page's rel=canonical, scholarly identifiers in
URLs and text. Like `debate_core.evidence` it sees only the domain layer, and it makes no network
calls; fetching is an adapter's business (`debate_core.integrations`, v1-e04-t02).
"""

from debate_core.retrieval.canonical_url import (
    InvalidUrlError,
    RelCanonicalDecision,
    RelCanonicalRule,
    apply_rel_canonical,
    canonicalize_url,
)
from debate_core.retrieval.identifiers import ScholarlyIdentifiers, detect_identifiers
from debate_core.retrieval.public_suffix import registrable_domain

__all__ = [
    "InvalidUrlError",
    "RelCanonicalDecision",
    "RelCanonicalRule",
    "ScholarlyIdentifiers",
    "apply_rel_canonical",
    "canonicalize_url",
    "detect_identifiers",
    "registrable_domain",
]
