"""The boundaries debate_core talks through.

Every use case in the platform reaches storage, a search provider, the web and a model through the
Protocols re-exported here, and through nothing else. That is the rule that lets V1 run on SQLite
and the local filesystem while V2 runs the same use cases on DynamoDB, S3 and Bedrock
(architecture proposal §2, §6, §17).

| Port | Module | What it hides |
|---|---|---|
| `ArticleRepository` | `persistence` | Article and snapshot-metadata records |
| `SnapshotStore` | `persistence` | Immutable, content-addressed blobs |
| `EvidenceObjectStore` | `evidence_store` | Evidence objects stored under a name: manifests, reports |
| `CardRepository` | `persistence` | Card records and their revision checks |
| `SearchRepository` | `persistence` | Searches and their ranked results |
| `CaselistRepository` | `caselist` | Imported caselist and camp-file records (E30) |
| `SearchProvider` | `providers` | One discovery source |
| `ArticleFetcher` | `providers` | HTTP retrieval |
| `ContentExtractor` | `providers` | Readable-text extraction |
| `ModelRouter` | `providers` | Every LLM call |
| `Clock` | `providers` | The current time |
| `IdGenerator` | `providers` | New entity ids |

They are :class:`~typing.Protocol` classes on purpose. An adapter conforms structurally — it never
subclasses, never imports this package at runtime, and therefore cannot drag a dependency of its
own back across the boundary. Conformance is checked statically by pyright and, for the fakes in
:mod:`debate_core.testing.fakes`, at the point where they are assembled into
:class:`~debate_core.testing.fakes.FakePorts`.

How a service takes its ports is written up in `docs/architecture/ports-and-adapters.md`, with
:class:`~debate_core.application.services.article_registration.ArticleRegistrationService` as the
worked example.
"""

from debate_core.application.ports.caselist import CaselistRepository
from debate_core.application.ports.evidence_store import (
    MAX_OBJECT_KEY_BYTES,
    OBJECT_KEY_PATTERN,
    EvidenceObjectStore,
    ObjectInfo,
    ObjectKey,
    validate_object_key,
)
from debate_core.application.ports.persistence import (
    DEFAULT_PAGE_SIZE,
    ArticleRepository,
    BlobKey,
    CardRepository,
    Page,
    SearchRepository,
    SnapshotStore,
)
from debate_core.application.ports.providers import (
    ArticleFetcher,
    CandidateResult,
    Clock,
    ContentExtractor,
    ExtractedContent,
    ExtractionQuality,
    FetchResult,
    IdGenerator,
    ModelInvocation,
    ModelInvocationMetadata,
    ModelRouter,
    ModelTaskClass,
    ProviderQuery,
    ProviderResponse,
    SearchProvider,
    SourceMetadataHints,
)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_OBJECT_KEY_BYTES",
    "OBJECT_KEY_PATTERN",
    "ArticleFetcher",
    "ArticleRepository",
    "BlobKey",
    "CandidateResult",
    "CardRepository",
    "CaselistRepository",
    "Clock",
    "ContentExtractor",
    "EvidenceObjectStore",
    "ExtractedContent",
    "ExtractionQuality",
    "FetchResult",
    "IdGenerator",
    "ModelInvocation",
    "ModelInvocationMetadata",
    "ModelRouter",
    "ModelTaskClass",
    "ObjectInfo",
    "ObjectKey",
    "Page",
    "ProviderQuery",
    "ProviderResponse",
    "SearchProvider",
    "SearchRepository",
    "SnapshotStore",
    "SourceMetadataHints",
    "validate_object_key",
]
