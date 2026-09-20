"""The closed vocabularies of the domain.

Every enum here is a :class:`~enum.StrEnum`, so members compare equal to their wire value and
serialize to a bare JSON string.

**On the casing of the values.** The values are the exact tokens the PlanSpecs use, which follow a
consistent split and are kept rather than tidied, because enum values are a persisted wire format
that later releases would have to migrate:

* `SCREAMING_SNAKE_CASE` for the *state* enums — :class:`AccessStatus`,
  :class:`VerificationStatus`, :class:`ProvenanceMode`, :class:`SearchStatus`. The specs write
  these as `PAYWALLED`, `UNVERIFIED`, `provenance_mode=USER_SUPPLIED`, `status COMPLETE | PARTIAL`.
* `lower_snake_case` for the *label* enums — :class:`SourceType`, :class:`SpanStyle`,
  :class:`SpanPurpose`, :class:`CitationFieldSource`. The specs write these as
  `scholarly | news | government | think_tank | other`, `style=underline/highlight`,
  `purpose=claim/warrant/internal_link/impact` and `meta_tag | json_ld | opengraph | crossref`.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AccessStatus",
    "CitationFieldSource",
    "ProvenanceMode",
    "SearchStatus",
    "SourceType",
    "SpanPurpose",
    "SpanStyle",
    "VerificationStatus",
]


class AccessStatus(StrEnum):
    """Whether a source's full text could legitimately be retrieved.

    The retrieval layer (E04) classifies every fetch into exactly one of these. There is no
    "partially readable" state: a metered or truncated page is `PAYWALLED`, never `ACCESSIBLE`,
    and nothing in the platform attempts to work around an access control.
    """

    UNKNOWN = "UNKNOWN"
    """Not fetched yet. The access classifier never returns this; it is the pre-retrieval state of
    an article discovered through search."""

    ACCESSIBLE = "ACCESSIBLE"
    """Full text was retrieved from the publisher without circumventing anything."""

    PAYWALLED = "PAYWALLED"
    """A subscription, metering or registration wall stands between the fetcher and the text."""

    BLOCKED = "BLOCKED"
    """A bot challenge, CAPTCHA or explicit block page was served instead of the article."""

    ROBOTS_DISALLOWED = "ROBOTS_DISALLOWED"
    """The site's robots rules disallow fetching this URL, so the platform does not fetch it."""

    NOT_FOUND = "NOT_FOUND"
    """The URL does not resolve to a document (404/410)."""

    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    """The response was a content type the extractor cannot handle."""

    ERROR = "ERROR"
    """Retrieval failed for a transport or server reason."""


class VerificationStatus(StrEnum):
    """Whether a card's quoted evidence has been reproduced from its stored snapshot.

    `VERIFIED` is set only by the evidence verifier (E03), only after the evidence text has been
    reconstructed byte for byte from the recorded snapshot offsets. Anything else is `UNVERIFIED`
    and must never be presented as a finished card.
    """

    UNVERIFIED = "UNVERIFIED"
    """Not proven reproducible. This is the default and the only safe fallback."""

    VERIFIED = "VERIFIED"
    """Reproduced exactly from the stored snapshot under the recorded normalizer version."""

    FAILED = "FAILED"
    """Verification ran and positively contradicted the card (for example a hash mismatch), as
    opposed to never having been attempted."""


class ProvenanceMode(StrEnum):
    """Where a snapshot's or card's text came from.

    This travels from the snapshot onto every card cut from it, so a reader can always tell
    publisher-retrieved evidence from text a person supplied.
    """

    PUBLISHER_RETRIEVED = "PUBLISHER_RETRIEVED"
    """Fetched by the platform from the publisher or source URL."""

    USER_SUPPLIED = "USER_SUPPLIED"
    """Text a user pasted in and the platform snapshotted; accessibility is only as reported."""

    PASTED = "PASTED"
    """An already-cut card pasted in as text, with no snapshot behind it. Never `VERIFIED`."""

    FILE_IMPORT = "FILE_IMPORT"
    """Imported from a parsed debate file (for example a disclosed caselist document)."""


class SourceType(StrEnum):
    """The kind of publication a source is, used as a ranking feature and a search filter.

    This is a descriptive category, never a quality or credibility score: source quality is
    expressed as named, explainable features (architecture proposal §9).
    """

    SCHOLARLY = "scholarly"
    NEWS = "news"
    GOVERNMENT = "government"
    THINK_TANK = "think_tank"
    OTHER = "other"


class SpanStyle(StrEnum):
    """How a marked region of a card's evidence is rendered on export."""

    UNDERLINE = "underline"
    """Read aloud in the round."""

    HIGHLIGHT = "highlight"
    """Emphasised within the underlined text."""


class SpanPurpose(StrEnum):
    """What argumentative work a marked region of evidence does."""

    CLAIM = "claim"
    WARRANT = "warrant"
    INTERNAL_LINK = "internal_link"
    IMPACT = "impact"


class SearchStatus(StrEnum):
    """The outcome of a federated search across the enabled providers.

    A provider failure never fails the whole search; it downgrades the result to `PARTIAL` and is
    reported per provider, so the user can see what was and was not searched.
    """

    COMPLETE = "COMPLETE"
    """Every selected provider answered."""

    PARTIAL = "PARTIAL"
    """At least one provider answered and at least one timed out, errored or was skipped."""

    FAILED = "FAILED"
    """No provider returned results."""


class CitationFieldSource(StrEnum):
    """Where one citation field's value was harvested from.

    Recorded per field so an export can mark exactly which parts of a cite are unverified. A model
    is never a source: authors, credentials, publications and dates are harvested deterministically
    or left missing (architecture proposal §8).
    """

    META_TAG = "meta_tag"
    """A `citation_*` or `article:*` HTML meta tag."""

    JSON_LD = "json_ld"
    """A JSON-LD `Article`/`ScholarlyArticle` block."""

    OPENGRAPH = "opengraph"
    """An OpenGraph `og:*` tag."""

    CROSSREF = "crossref"
    """Crossref metadata looked up by DOI."""

    BYLINE = "byline"
    """An explicit byline or author bio on the page."""

    HEURISTIC = "heuristic"
    """Inferred from a weaker signal such as a URL slug. Never counts as verified."""

    MISSING = "missing"
    """No value was found. The cite shows the gap instead of inventing a value."""
