"""Property tests: every domain model survives `model_dump_json` -> `model_validate_json` unchanged.

A repository writes a model as JSON and reads it back; a stale or lossy round-trip would silently
corrupt provenance. Hypothesis generates the awkward cases (astral-plane characters, microsecond
timestamps, empty collections, values at the edge of every constraint) that hand-written examples
miss.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from debate_core.domain import (
    AccessStatus,
    Article,
    ArticleIdentifiers,
    Card,
    CardSpan,
    Citation,
    CitationField,
    CitationFieldSource,
    DomainModel,
    ProvenanceMode,
    Search,
    SearchFilters,
    SearchResult,
    SearchStatus,
    SourceSnapshot,
    SourceType,
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
)

# Text without lone surrogates or control characters: what a normalizer actually emits.
safe_characters = st.characters(min_codepoint=32, max_codepoint=0x2FFF, exclude_categories=("Cs", "Cc"))
non_empty_text = st.text(safe_characters, min_size=1, max_size=40).map(str.strip).filter(bool)
optional_text = st.none() | non_empty_text

ulids = st.from_regex(r"[0-7][0-9ABCDEFGHJKMNPQRSTVWXYZ]{25}", fullmatch=True)
sha256_hexes = st.from_regex(r"[0-9a-f]{64}", fullmatch=True)
urls = st.from_regex(
    r"https://[a-z][a-z0-9-]{1,12}\.(com|org|gov|edu)(/[a-z0-9-]{1,10}){0,3}", fullmatch=True
)
utc_datetimes = st.datetimes(
    min_value=datetime(1900, 1, 1),
    max_value=datetime(2200, 1, 1),
    timezones=st.just(UTC),
)
optional_utc_datetimes = st.none() | utc_datetimes
scores = st.none() | st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)

dois = st.from_regex(r"10\.[0-9]{4,9}/[a-z0-9.-]{1,20}", fullmatch=True)


def assert_json_round_trip(model: DomainModel) -> None:
    """The model must survive a JSON round-trip byte for byte and compare equal."""
    as_json = model.model_dump_json()
    restored = type(model).model_validate_json(as_json)
    assert restored == model
    assert restored.model_dump_json() == as_json


article_identifiers = st.builds(
    ArticleIdentifiers,
    doi=st.none() | dois,
    arxiv_id=optional_text,
    pmid=st.none() | st.from_regex(r"[0-9]{1,9}", fullmatch=True),
    openalex_id=optional_text,
    semantic_scholar_id=optional_text,
)

articles = st.builds(
    Article,
    article_id=ulids,
    owner_id=st.none() | ulids,
    organization_id=st.none() | ulids,
    canonical_url=urls,
    title=non_empty_text,
    authors=st.lists(non_empty_text, max_size=4).map(tuple),
    publication=optional_text,
    published_at=optional_utc_datetimes,
    source_type=st.sampled_from(SourceType),
    access_status=st.sampled_from(AccessStatus),
    identifiers=article_identifiers,
    revision=st.integers(min_value=1, max_value=1000),
)

source_snapshots = st.builds(
    SourceSnapshot,
    snapshot_id=ulids,
    article_id=ulids,
    owner_id=st.none() | ulids,
    canonical_url=urls,
    retrieved_at=utc_datetimes,
    access_status=st.sampled_from(AccessStatus),
    provenance_mode=st.sampled_from(ProvenanceMode),
    raw_blob_key=non_empty_text,
    normalized_blob_key=non_empty_text,
    sha256=sha256_hexes,
    normalized_text_hash=sha256_hexes,
    extractor_version=non_empty_text,
    normalizer_version=non_empty_text,
    content_type=optional_text,
    byte_size=st.none() | st.integers(min_value=0, max_value=10**9),
)


@st.composite
def search_filters(draw: st.DrawFn) -> SearchFilters:
    """Filters whose window, when both bounds are set, runs forwards."""
    bounds = sorted(draw(st.lists(utc_datetimes, max_size=2)))
    since = bounds[0] if bounds else draw(st.none() | utc_datetimes)
    until = bounds[1] if len(bounds) == 2 else None
    return SearchFilters(
        since=since,
        until=until,
        source_types=tuple(draw(st.lists(st.sampled_from(SourceType), max_size=3))),
        max_results=draw(st.integers(min_value=1, max_value=200)),
        language=draw(optional_text),
    )


searches = st.builds(
    Search,
    search_id=ulids,
    owner_id=st.none() | ulids,
    query=non_empty_text,
    filters=search_filters(),
    provider_set=st.lists(non_empty_text, max_size=4).map(tuple),
    status=st.sampled_from(SearchStatus),
)

search_results = st.builds(
    SearchResult,
    search_id=ulids,
    article_id=ulids,
    rank=st.integers(min_value=1, max_value=500),
    total_score=scores,
    lexical_score=scores,
    semantic_score=scores,
    rerank_score=scores,
    source_quality_features=st.dictionaries(
        non_empty_text,
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        max_size=5,
    ),
    explanation=optional_text,
    providers=st.lists(non_empty_text, max_size=3).map(tuple),
)


def citation_fields[T](values: st.SearchStrategy[T]) -> st.SearchStrategy[CitationField[T]]:
    """Citation fields that satisfy the provenance invariants: missing, present or verified."""
    missing = st.just(CitationField[T]())
    harvested = st.builds(
        CitationField[T],
        value=values,
        source=st.sampled_from(
            [source for source in CitationFieldSource if source is not CitationFieldSource.MISSING]
        ),
        verified=st.just(False),
        raw=optional_text,
    )
    verified = st.builds(
        CitationField[T],
        value=values,
        source=st.sampled_from(
            [
                source
                for source in CitationFieldSource
                if source not in (CitationFieldSource.MISSING, CitationFieldSource.HEURISTIC)
            ]
        ),
        verified=st.just(True),
        raw=optional_text,
    )
    return missing | harvested | verified


citations = st.builds(
    Citation,
    authors=citation_fields(st.lists(non_empty_text, min_size=1, max_size=3).map(tuple)),
    author_credentials=citation_fields(non_empty_text),
    title=citation_fields(non_empty_text),
    publication=citation_fields(non_empty_text),
    published_at=citation_fields(utc_datetimes),
    canonical_url=citation_fields(urls),
    accessed_at=citation_fields(utc_datetimes),
)


@st.composite
def cards(draw: st.DrawFn) -> Card:
    """Cards in every legal state: empty, cut but unverified, and fully verified."""
    evidence_text = draw(st.text(safe_characters, min_size=0, max_size=60))
    if not evidence_text:
        return Card(
            card_id=draw(ulids),
            owner_id=draw(ulids),
            organization_id=draw(st.none() | ulids),
            article_id=draw(ulids),
            snapshot_id=draw(st.none() | ulids),
            tag=draw(non_empty_text),
            citation=draw(citations),
            provenance_mode=draw(st.sampled_from(ProvenanceMode)),
            format_profile=draw(non_empty_text),
            revision=draw(st.integers(min_value=1, max_value=1000)),
        )

    start = draw(st.integers(min_value=0, max_value=10_000))
    # Spans of a single style, laid out left to right, so the no-overlap rule cannot be tripped.
    style = draw(st.sampled_from(SpanStyle))
    cuts = sorted(draw(st.lists(st.integers(min_value=0, max_value=len(evidence_text)), max_size=6)))
    spans = tuple(
        CardSpan(
            span_id=draw(ulids),
            start_offset=left,
            end_offset=right,
            style=style,
            purpose=draw(st.none() | st.sampled_from(SpanPurpose)),
        )
        for left, right in zip(cuts[::2], cuts[1::2], strict=False)
        if left < right
    )

    verified = bool(spans) and draw(st.booleans())
    return Card(
        card_id=draw(ulids),
        owner_id=draw(ulids),
        organization_id=draw(st.none() | ulids),
        article_id=draw(ulids),
        snapshot_id=draw(ulids),
        tag=draw(non_empty_text),
        citation=draw(citations),
        evidence_text=evidence_text,
        evidence_start_offset=start,
        evidence_end_offset=start + len(evidence_text),
        normalized_text_hash=draw(sha256_hexes),
        normalizer_version=draw(non_empty_text),
        spans=spans,
        verification_status=(
            VerificationStatus.VERIFIED
            if verified
            else draw(st.sampled_from([VerificationStatus.UNVERIFIED, VerificationStatus.FAILED]))
        ),
        provenance_mode=draw(st.sampled_from(ProvenanceMode)),
        format_profile=draw(non_empty_text),
        revision=draw(st.integers(min_value=1, max_value=1000)),
    )


@st.composite
def card_spans(draw: st.DrawFn) -> CardSpan:
    """Spans with a well-ordered, non-empty range."""
    start = draw(st.integers(min_value=0, max_value=999))
    return CardSpan(
        span_id=draw(ulids),
        start_offset=start,
        end_offset=draw(st.integers(min_value=start + 1, max_value=1000)),
        style=draw(st.sampled_from(SpanStyle)),
        purpose=draw(st.none() | st.sampled_from(SpanPurpose)),
    )


@settings(max_examples=100)
@given(articles)
def test_article_round_trips(article: Article) -> None:
    assert_json_round_trip(article)


@settings(max_examples=100)
@given(source_snapshots)
def test_source_snapshot_round_trips(snapshot: SourceSnapshot) -> None:
    assert_json_round_trip(snapshot)


@settings(max_examples=100)
@given(searches)
def test_search_round_trips(search: Search) -> None:
    assert_json_round_trip(search)


@settings(max_examples=100)
@given(search_results)
def test_search_result_round_trips(result: SearchResult) -> None:
    assert_json_round_trip(result)


@settings(max_examples=100)
@given(citations)
def test_citation_round_trips(citation: Citation) -> None:
    assert_json_round_trip(citation)


@settings(max_examples=100)
@given(card_spans())
def test_card_span_round_trips(span: CardSpan) -> None:
    assert_json_round_trip(span)


@settings(max_examples=150)
@given(cards())
def test_card_round_trips(card: Card) -> None:
    assert_json_round_trip(card)


@settings(max_examples=100)
@given(cards())
def test_evolve_preserves_validity(card: Card) -> None:
    """A revision bump goes through full validation and leaves everything else untouched."""
    bumped = card.evolve(revision=card.revision + 1)
    assert bumped.revision == card.revision + 1
    assert bumped.evolve(revision=card.revision) == card
