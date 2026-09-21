"""The domain vocabulary of the Debate Intelligence Platform.

These Pydantic models are the platform's permanent shape. They already match the cloud data model
in architecture proposal §7, so moving from V1's local filesystem/SQLite storage to V2's
DynamoDB/S3 swaps repository implementations, not schemas.

The layer holds data and invariants only. Persistence and provider access live behind ports
(v1-e02-t02-ports); normalization, hashing and verification live in `debate_core.evidence` (E03).
Nothing here imports an I/O library, an AWS SDK, a web framework or an HTTP client.
"""

from debate_core.domain.article import Article, ArticleIdentifiers, SourceSnapshot
from debate_core.domain.base import (
    CROCKFORD_BASE32_ALPHABET,
    SHA256_HEX_PATTERN,
    ULID_PATTERN,
    DomainEntity,
    DomainModel,
    HttpUrlStr,
    IdFactory,
    NonEmptyText,
    Sha256Hex,
    Ulid,
    UtcDatetime,
    new_id,
    use_id_factory,
    utc_now,
)
from debate_core.domain.card import DEFAULT_FORMAT_PROFILE, Card, CardSpan
from debate_core.domain.citation import REQUIRED_CITATION_FIELDS, Citation, CitationField
from debate_core.domain.enums import (
    AccessStatus,
    CitationFieldSource,
    ProvenanceMode,
    SearchStatus,
    SourceType,
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
)
from debate_core.domain.schema_export import EXPORTED_MODELS, render_schemas, schema_filename
from debate_core.domain.search import Search, SearchFilters, SearchResult
from debate_core.domain.style_profile import (
    CardMirrorMarkMapping,
    CardMirrorNodeMapping,
    CharacterStyleRule,
    CiteConvention,
    HeuristicThreshold,
    HighlightColor,
    ParagraphStyleMatch,
    ParagraphStyleRule,
    RunEmphasis,
    RunStyleMatch,
    ShrinkRule,
    StructuralUnit,
    StyleMatchSource,
    StyleProfile,
    UnderlineEncodingRule,
    WriterStyleDefinition,
    normalize_style_key,
    strip_deduplication_suffix,
)

__all__ = [
    "CROCKFORD_BASE32_ALPHABET",
    "DEFAULT_FORMAT_PROFILE",
    "EXPORTED_MODELS",
    "REQUIRED_CITATION_FIELDS",
    "SHA256_HEX_PATTERN",
    "ULID_PATTERN",
    "AccessStatus",
    "Article",
    "ArticleIdentifiers",
    "Card",
    "CardMirrorMarkMapping",
    "CardMirrorNodeMapping",
    "CardSpan",
    "CharacterStyleRule",
    "Citation",
    "CitationField",
    "CitationFieldSource",
    "CiteConvention",
    "DomainEntity",
    "DomainModel",
    "HeuristicThreshold",
    "HighlightColor",
    "HttpUrlStr",
    "IdFactory",
    "NonEmptyText",
    "ParagraphStyleMatch",
    "ParagraphStyleRule",
    "ProvenanceMode",
    "RunEmphasis",
    "RunStyleMatch",
    "Search",
    "SearchFilters",
    "SearchResult",
    "SearchStatus",
    "Sha256Hex",
    "ShrinkRule",
    "SourceSnapshot",
    "SourceType",
    "SpanPurpose",
    "SpanStyle",
    "StructuralUnit",
    "StyleMatchSource",
    "StyleProfile",
    "Ulid",
    "UnderlineEncodingRule",
    "UtcDatetime",
    "VerificationStatus",
    "WriterStyleDefinition",
    "new_id",
    "normalize_style_key",
    "render_schemas",
    "schema_filename",
    "strip_deduplication_suffix",
    "use_id_factory",
    "utc_now",
]
