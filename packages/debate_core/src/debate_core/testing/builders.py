"""Builders that produce valid domain entities from a handful of keyword arguments.

Every domain model in `debate_core.domain` validates hard: a `Card` that holds evidence must name
the snapshot it was cut from and the offsets it was taken at, a `SourceSnapshot` needs two blob
keys and two digests, a verified `CitationField` needs a value from a source that actually
verifies it. Spelling all of that out at the top of a test buries the one field the test is
actually about.

Each builder here fills in a complete, realistic entity and lets a caller override exactly the
fields under test::

    article = build_article(title="Arctic methane release is accelerating")
    stale = build_card(owner_id=owner, article_id=article.article_id, revision=3)

The builders are deliberately plain functions with explicit keyword parameters rather than a
factory library: the parameter list is the documentation, and a renamed or retyped domain field
fails type checking here, in this package, instead of in every test that uses it. Every parameter
defaults to a real value, so `None` always means "this entity genuinely has no such value" and
never "give me the default".

**Everything is deterministic.** Ids come from :func:`readable_id` rather than from a real ULID,
timestamps default to :data:`~debate_core.testing.fakes.FAKE_EPOCH`, and digests are computed from
the fixed text the builder itself supplies. Two runs produce byte-identical entities, which is
what lets the repository contract suite assert on listing order and on stored documents.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from debate_core.domain import (
    CROCKFORD_BASE32_ALPHABET,
    DEFAULT_FORMAT_PROFILE,
    AccessStatus,
    Article,
    ArticleIdentifiers,
    Card,
    CardSpan,
    Citation,
    CitationField,
    CitationFieldSource,
    HttpUrlStr,
    NonEmptyText,
    ProvenanceMode,
    Search,
    SearchFilters,
    SearchResult,
    SearchStatus,
    Sha256Hex,
    SourceSnapshot,
    SourceType,
    SpanPurpose,
    SpanStyle,
    Ulid,
    UtcDatetime,
    VerificationStatus,
)
from debate_core.testing.fakes import FAKE_EPOCH

__all__ = [
    "DEFAULT_ARTICLE_ID",
    "DEFAULT_CANONICAL_URL",
    "DEFAULT_CARD_ID",
    "DEFAULT_EVIDENCE_TEXT",
    "DEFAULT_EXTRACTOR_VERSION",
    "DEFAULT_NORMALIZED_TEXT",
    "DEFAULT_NORMALIZER_VERSION",
    "DEFAULT_ORGANIZATION_ID",
    "DEFAULT_OWNER_ID",
    "DEFAULT_PUBLISHED_AT",
    "DEFAULT_RAW_BYTES",
    "DEFAULT_SEARCH_ID",
    "DEFAULT_SNAPSHOT_ID",
    "build_article",
    "build_card",
    "build_card_span",
    "build_citation",
    "build_search",
    "build_search_result",
    "build_source_snapshot",
    "readable_id",
    "sha256_of",
]


# --------------------------------------------------------------------------------------------
# Deterministic ids and digests
# --------------------------------------------------------------------------------------------


def readable_id(label: str, number: int = 1) -> Ulid:
    """Return a valid ULID that says what it identifies: `readable_id("CARD", 7)` → `0CARD…0007`.

    Real ULIDs are time-ordered and random, so a test that prints one, sorts by one or checks one
    against a golden file is unreadable and unstable. These are genuine ULIDs — 26 Crockford
    base32 characters whose first character is below `8` — that a reader can tell apart at a
    glance, and whose lexicographic order is the numeric order of `number`, which is what the
    listing-order contracts depend on.

    Uses the same construction as :class:`~debate_core.testing.fakes.SequentialIdGenerator`, so
    ids minted by a fake service run and ids written by hand in a test sort into one sequence.
    """
    text = label.upper()
    unusable = sorted(set(text) - set(CROCKFORD_BASE32_ALPHABET))
    if unusable:
        raise ValueError(
            f"label must use the Crockford base32 alphabet ({CROCKFORD_BASE32_ALPHABET}); "
            f"cannot use {''.join(unusable)}"
        )
    digits = 25 - len(text)
    if digits < 1:
        raise ValueError(f"label must be at most 24 characters, got {len(text)}")
    rendered = str(number)
    if len(rendered) > digits:
        raise ValueError(f"number {number} does not fit in {digits} characters after {text!r}")
    return f"0{text}{rendered.zfill(digits)}"


def sha256_of(data: bytes) -> Sha256Hex:
    """Return the lowercase hex SHA-256 of `data`, the form every digest field and blob key takes."""
    return hashlib.sha256(data).hexdigest()


#: Owner every builder attributes its entity to unless told otherwise, so `list_by_owner` finds it.
DEFAULT_OWNER_ID = readable_id("WNER")

#: Organization every builder attributes its entity to unless told otherwise.
DEFAULT_ORGANIZATION_ID = readable_id("TEAM")

#: Article the default snapshot and the default card belong to.
DEFAULT_ARTICLE_ID = readable_id("ART")

#: Snapshot the default card was cut from.
DEFAULT_SNAPSHOT_ID = readable_id("SNAP")

#: Card :func:`build_card` produces unless a test names its own.
DEFAULT_CARD_ID = readable_id("CARD")

#: Search :func:`build_search` produces unless a test names its own.
DEFAULT_SEARCH_ID = readable_id("SRCH")

#: Span :func:`build_card_span` produces unless a test names its own.
DEFAULT_SPAN_ID = readable_id("SPAN")

#: Canonical URL of the source the default article describes.
DEFAULT_CANONICAL_URL = "https://example.org/arctic-methane-release"

#: The bytes the default snapshot records a retrieval of.
DEFAULT_RAW_BYTES = b"<html><body><p>Arctic methane release is accelerating.</p></body></html>"

#: Normalized text the default snapshot, and the default card's offsets, refer to.
DEFAULT_NORMALIZED_TEXT = "Arctic methane release is accelerating."

#: Verbatim quotation the default card carries. Long enough to hold two non-overlapping spans.
DEFAULT_EVIDENCE_TEXT = DEFAULT_NORMALIZED_TEXT

#: Publication date the default article and the default cite state: a year before the fake epoch,
#: so a card cut from the source is retrieved after the source was published, as a real one is.
DEFAULT_PUBLISHED_AT = FAKE_EPOCH - timedelta(days=365)

#: Extractor version the default snapshot was produced under.
DEFAULT_EXTRACTOR_VERSION = "builder-extractor-1.0.0"

#: Normalizer version the default snapshot, and the default card's offsets, were taken under.
DEFAULT_NORMALIZER_VERSION = "builder-normalizer-1.0.0"

#: External identifiers the default article carries.
DEFAULT_IDENTIFIERS = ArticleIdentifiers(doi="10.1038/nature12373")

#: Author list shared by the default article and the default cite.
DEFAULT_AUTHORS: tuple[NonEmptyText, ...] = ("Rivera, J.", "Okonkwo, A.")

#: Title shared by the default article and the default cite.
DEFAULT_TITLE = "Arctic methane release is accelerating"

#: Publication shared by the default article and the default cite.
DEFAULT_PUBLICATION = "Journal of Climate Systems"

#: Filters the default search was run with.
DEFAULT_SEARCH_FILTERS = SearchFilters(
    since=datetime(2020, 1, 1, tzinfo=UTC),
    until=FAKE_EPOCH,
    source_types=(SourceType.SCHOLARLY,),
    max_results=20,
    language="en",
)


# --------------------------------------------------------------------------------------------
# Source-side entities
# --------------------------------------------------------------------------------------------


def build_article(
    *,
    article_id: Ulid = DEFAULT_ARTICLE_ID,
    owner_id: Ulid | None = DEFAULT_OWNER_ID,
    organization_id: Ulid | None = DEFAULT_ORGANIZATION_ID,
    canonical_url: HttpUrlStr = DEFAULT_CANONICAL_URL,
    title: NonEmptyText = DEFAULT_TITLE,
    authors: tuple[NonEmptyText, ...] = DEFAULT_AUTHORS,
    publication: NonEmptyText | None = DEFAULT_PUBLICATION,
    published_at: UtcDatetime | None = DEFAULT_PUBLISHED_AT,
    source_type: SourceType = SourceType.SCHOLARLY,
    access_status: AccessStatus = AccessStatus.ACCESSIBLE,
    identifiers: ArticleIdentifiers = DEFAULT_IDENTIFIERS,
    created_at: UtcDatetime = FAKE_EPOCH,
    updated_at: UtcDatetime = FAKE_EPOCH,
    revision: int = 1,
) -> Article:
    """Build a complete, accessible scholarly article with a DOI and a publication date."""
    return Article(
        article_id=article_id,
        owner_id=owner_id,
        organization_id=organization_id,
        canonical_url=canonical_url,
        title=title,
        authors=authors,
        publication=publication,
        published_at=published_at,
        source_type=source_type,
        access_status=access_status,
        identifiers=identifiers,
        created_at=created_at,
        updated_at=updated_at,
        revision=revision,
    )


def build_source_snapshot(
    *,
    snapshot_id: Ulid = DEFAULT_SNAPSHOT_ID,
    article_id: Ulid = DEFAULT_ARTICLE_ID,
    owner_id: Ulid | None = DEFAULT_OWNER_ID,
    organization_id: Ulid | None = DEFAULT_ORGANIZATION_ID,
    canonical_url: HttpUrlStr = DEFAULT_CANONICAL_URL,
    retrieved_at: UtcDatetime = FAKE_EPOCH,
    access_status: AccessStatus = AccessStatus.ACCESSIBLE,
    provenance_mode: ProvenanceMode = ProvenanceMode.PUBLISHER_RETRIEVED,
    raw_bytes: bytes = DEFAULT_RAW_BYTES,
    normalized_text: str = DEFAULT_NORMALIZED_TEXT,
    extractor_version: NonEmptyText = DEFAULT_EXTRACTOR_VERSION,
    normalizer_version: NonEmptyText = DEFAULT_NORMALIZER_VERSION,
    content_type: NonEmptyText | None = "text/html; charset=utf-8",
    created_at: UtcDatetime = FAKE_EPOCH,
    updated_at: UtcDatetime = FAKE_EPOCH,
) -> SourceSnapshot:
    """Build a snapshot whose blob keys, digests and byte size all really describe `raw_bytes`.

    Taking the bytes rather than the keys is what keeps the record honest: both blob keys and both
    digests are computed here, so a snapshot built by this function can be stored in a
    `SnapshotStore` and read back under exactly the keys it claims.

    `revision` is not a parameter. Snapshots are immutable, so theirs stays at 1.
    """
    return SourceSnapshot(
        snapshot_id=snapshot_id,
        article_id=article_id,
        owner_id=owner_id,
        organization_id=organization_id,
        canonical_url=canonical_url,
        retrieved_at=retrieved_at,
        access_status=access_status,
        provenance_mode=provenance_mode,
        raw_blob_key=sha256_of(raw_bytes),
        normalized_blob_key=sha256_of(normalized_text.encode("utf-8")),
        sha256=sha256_of(raw_bytes),
        normalized_text_hash=sha256_of(normalized_text.encode("utf-8")),
        extractor_version=extractor_version,
        normalizer_version=normalizer_version,
        content_type=content_type,
        byte_size=len(raw_bytes),
        created_at=created_at,
        updated_at=updated_at,
        revision=1,
    )


# --------------------------------------------------------------------------------------------
# Cards and their cites
# --------------------------------------------------------------------------------------------


def build_citation(
    *,
    verified: bool = True,
    authors: tuple[NonEmptyText, ...] = DEFAULT_AUTHORS,
    title: str = DEFAULT_TITLE,
    publication: str = DEFAULT_PUBLICATION,
    published_at: UtcDatetime = DEFAULT_PUBLISHED_AT,
    canonical_url: str = DEFAULT_CANONICAL_URL,
    accessed_at: UtcDatetime = FAKE_EPOCH,
) -> Citation:
    """Build a cite whose every required field carries a value and the provenance it came from.

    With `verified=False` the same values are recorded as `heuristic` guesses, which is the state
    a cite is in before the citation service has confirmed it — and the state in which
    :attr:`~debate_core.domain.Citation.is_fully_verified` must stay false.
    """
    source = CitationFieldSource.CROSSREF if verified else CitationFieldSource.HEURISTIC
    return Citation(
        authors=CitationField[tuple[NonEmptyText, ...]](
            value=authors,
            source=CitationFieldSource.BYLINE if verified else source,
            verified=verified,
        ),
        author_credentials=CitationField[str](
            value="Professor of Atmospheric Science" if verified else None,
            source=CitationFieldSource.CROSSREF if verified else CitationFieldSource.MISSING,
            verified=verified,
        ),
        title=CitationField[str](value=title, source=source, verified=verified),
        publication=CitationField[str](value=publication, source=source, verified=verified),
        published_at=CitationField[UtcDatetime](value=published_at, source=source, verified=verified),
        canonical_url=CitationField[str](
            value=canonical_url,
            source=CitationFieldSource.META_TAG if verified else source,
            verified=verified,
        ),
        accessed_at=CitationField[UtcDatetime](
            value=accessed_at, source=CitationFieldSource.META_TAG, verified=False
        ),
    )


#: The fully verified cite :func:`build_card` attaches unless a test supplies its own.
DEFAULT_CITATION = build_citation()


def build_card_span(
    *,
    span_id: Ulid = DEFAULT_SPAN_ID,
    start_offset: int = 0,
    end_offset: int = 22,
    style: SpanStyle = SpanStyle.UNDERLINE,
    purpose: SpanPurpose | None = SpanPurpose.CLAIM,
) -> CardSpan:
    """Build one marked region of a card's evidence. Offsets are into `evidence_text`.

    The default span underlines `"Arctic methane release"`, the first 22 characters of
    :data:`DEFAULT_EVIDENCE_TEXT`.
    """
    return CardSpan(
        span_id=span_id,
        start_offset=start_offset,
        end_offset=end_offset,
        style=style,
        purpose=purpose,
    )


#: The single underlined span :func:`build_card` marks up its evidence with.
DEFAULT_SPANS: tuple[CardSpan, ...] = (build_card_span(),)


def build_card(
    *,
    card_id: Ulid = DEFAULT_CARD_ID,
    owner_id: Ulid = DEFAULT_OWNER_ID,
    organization_id: Ulid | None = DEFAULT_ORGANIZATION_ID,
    article_id: Ulid = DEFAULT_ARTICLE_ID,
    snapshot_id: Ulid | None = DEFAULT_SNAPSHOT_ID,
    tag: NonEmptyText = "Arctic methane feedback is already measurable",
    citation: Citation = DEFAULT_CITATION,
    evidence_text: str = DEFAULT_EVIDENCE_TEXT,
    evidence_start_offset: int | None = 0,
    evidence_end_offset: int | None = len(DEFAULT_EVIDENCE_TEXT),
    normalized_text_hash: Sha256Hex | None = None,
    normalizer_version: NonEmptyText | None = DEFAULT_NORMALIZER_VERSION,
    spans: tuple[CardSpan, ...] = DEFAULT_SPANS,
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED,
    provenance_mode: ProvenanceMode = ProvenanceMode.PUBLISHER_RETRIEVED,
    format_profile: NonEmptyText = DEFAULT_FORMAT_PROFILE,
    created_at: UtcDatetime = FAKE_EPOCH,
    updated_at: UtcDatetime = FAKE_EPOCH,
    revision: int = 1,
) -> Card:
    """Build a card that holds real evidence: a quotation, its location, and one underlined span.

    The offsets, the normalized-text hash and the span are all consistent with
    :data:`DEFAULT_EVIDENCE_TEXT`, so the card satisfies every invariant in
    :class:`~debate_core.domain.Card` without the caller restating them. `normalized_text_hash`
    is the one parameter whose `None` means "derive it", because the digest of
    :data:`DEFAULT_NORMALIZED_TEXT` is not something a caller should have to write out.

    `verification_status` stays `UNVERIFIED`: only the evidence verifier (E03) promotes a card,
    and a builder that handed out `VERIFIED` cards would let a test assert on a status nothing
    had checked. Pass it explicitly when the test is *about* a verified card.

    For a tag-only card — one nothing has been cut for yet — evolve the result::

        bare = build_card().evolve(
            snapshot_id=None, evidence_text="", evidence_start_offset=None,
            evidence_end_offset=None, spans=(),
        )
    """
    return Card(
        card_id=card_id,
        owner_id=owner_id,
        organization_id=organization_id,
        article_id=article_id,
        snapshot_id=snapshot_id,
        tag=tag,
        citation=citation,
        evidence_text=evidence_text,
        evidence_start_offset=evidence_start_offset,
        evidence_end_offset=evidence_end_offset,
        normalized_text_hash=(
            sha256_of(DEFAULT_NORMALIZED_TEXT.encode("utf-8"))
            if normalized_text_hash is None
            else normalized_text_hash
        ),
        normalizer_version=normalizer_version,
        spans=spans,
        verification_status=verification_status,
        provenance_mode=provenance_mode,
        format_profile=format_profile,
        created_at=created_at,
        updated_at=updated_at,
        revision=revision,
    )


# --------------------------------------------------------------------------------------------
# Search-side entities
# --------------------------------------------------------------------------------------------


def build_search(
    *,
    search_id: Ulid = DEFAULT_SEARCH_ID,
    owner_id: Ulid | None = DEFAULT_OWNER_ID,
    organization_id: Ulid | None = DEFAULT_ORGANIZATION_ID,
    query: NonEmptyText = "arctic methane feedback",
    filters: SearchFilters = DEFAULT_SEARCH_FILTERS,
    provider_set: tuple[NonEmptyText, ...] = ("openalex", "crossref"),
    status: SearchStatus = SearchStatus.COMPLETE,
    created_at: UtcDatetime = FAKE_EPOCH,
    updated_at: UtcDatetime = FAKE_EPOCH,
    revision: int = 1,
) -> Search:
    """Build a complete federated search across two providers, with a date-windowed filter."""
    return Search(
        search_id=search_id,
        owner_id=owner_id,
        organization_id=organization_id,
        query=query,
        filters=filters,
        provider_set=provider_set,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        revision=revision,
    )


def build_search_result(
    *,
    search_id: Ulid = DEFAULT_SEARCH_ID,
    article_id: Ulid | None = None,
    rank: int = 1,
    total_score: float | None = 0.91,
    lexical_score: float | None = 0.74,
    semantic_score: float | None = None,
    rerank_score: float | None = None,
    source_quality_features: dict[str, float] | None = None,
    explanation: str | None = "recent (3 days), peer-reviewed, two providers agree",
    providers: tuple[NonEmptyText, ...] = ("openalex", "crossref"),
) -> SearchResult:
    """Build one ranked result of `search_id`, with named quality features rather than a score.

    Two parameters take `None` to mean "derive it", because both defaults would otherwise be
    shared mutable or rank-dependent state: `article_id` becomes `readable_id("ART", rank)`, so a
    ranking built by comprehension names a different article at every rank, and
    `source_quality_features` becomes a fresh dictionary per result rather than one shared by
    every result ever built.
    """
    return SearchResult(
        search_id=search_id,
        article_id=readable_id("ART", rank) if article_id is None else article_id,
        rank=rank,
        total_score=total_score,
        lexical_score=lexical_score,
        semantic_score=semantic_score,
        rerank_score=rerank_score,
        source_quality_features=(
            {"recency": 0.8, "peer_reviewed": 1.0, "provider_agreement": 1.0}
            if source_quality_features is None
            else source_quality_features
        ),
        explanation=explanation,
        providers=providers,
    )
