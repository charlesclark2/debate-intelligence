"""The enum values are a persisted wire format, so they are pinned to the tokens the specs use."""

from __future__ import annotations

from debate_core.domain import (
    AccessStatus,
    CitationFieldSource,
    ProvenanceMode,
    SearchStatus,
    SourceType,
    SpanPurpose,
    SpanStyle,
    VerificationStatus,
)


def test_access_status_values() -> None:
    assert [status.value for status in AccessStatus] == [
        "UNKNOWN",
        "ACCESSIBLE",
        "PAYWALLED",
        "BLOCKED",
        "ROBOTS_DISALLOWED",
        "NOT_FOUND",
        "UNSUPPORTED_TYPE",
        "ERROR",
    ]


def test_verification_status_values() -> None:
    assert [status.value for status in VerificationStatus] == ["UNVERIFIED", "VERIFIED", "FAILED"]


def test_provenance_mode_values() -> None:
    assert [mode.value for mode in ProvenanceMode] == [
        "PUBLISHER_RETRIEVED",
        "USER_SUPPLIED",
        "PASTED",
        "FILE_IMPORT",
    ]


def test_search_status_values() -> None:
    assert [status.value for status in SearchStatus] == ["COMPLETE", "PARTIAL", "FAILED"]


def test_source_type_values() -> None:
    assert [source_type.value for source_type in SourceType] == [
        "scholarly",
        "news",
        "government",
        "think_tank",
        "other",
    ]


def test_span_style_values() -> None:
    assert [style.value for style in SpanStyle] == ["underline", "highlight"]


def test_span_purpose_values() -> None:
    assert [purpose.value for purpose in SpanPurpose] == ["claim", "warrant", "internal_link", "impact"]


def test_citation_field_source_values() -> None:
    assert [source.value for source in CitationFieldSource] == [
        "meta_tag",
        "json_ld",
        "opengraph",
        "crossref",
        "byline",
        "heuristic",
        "missing",
    ]


def test_enums_serialize_as_bare_strings() -> None:
    assert f"{AccessStatus.PAYWALLED}" == "PAYWALLED"
    assert SpanStyle.UNDERLINE == "underline"
