"""The discovery values: ProviderQuery, CandidateResult, ProviderResponse, ProviderHealth and ProviderStatus.

Every expected value here is written out by hand from the input beside it (working agreement 6).
"""

from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import typing
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from debate_core.application import ports
from debate_core.application.ports import providers
from debate_core.domain import discovery
from debate_core.domain.discovery import (
    BreakerState,
    CandidateResult,
    ProviderHealth,
    ProviderOutcome,
    ProviderQuery,
    ProviderResponse,
    ProviderStatus,
)


def make_candidate(**overrides: object) -> CandidateResult:
    """A CandidateResult with every required field filled in."""
    fields: dict[str, object] = {
        "provider": "openalex",
        "title": "Methane leakage from US natural gas supply chains",
        "url": "https://example.org/methane",
    }
    fields.update(overrides)
    return CandidateResult.model_validate(fields)


# --------------------------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("10.1126/science.aar7204", "10.1126/science.aar7204"),
        ("10.1126/SCIENCE.AAR7204", "10.1126/science.aar7204"),
        ("https://doi.org/10.1126/Science.AAR7204", "10.1126/science.aar7204"),
        ("http://dx.doi.org/10.1126/science.aar7204", "10.1126/science.aar7204"),
        ("HTTPS://DOI.ORG/10.1126/science.aar7204", "10.1126/science.aar7204"),
        ("doi:10.1126/science.aar7204", "10.1126/science.aar7204"),
        ("  10.1126/science.aar7204  ", "10.1126/science.aar7204"),
    ],
)
def test_a_candidate_stores_a_doi_bare_and_lowercase_however_the_provider_spelled_it(
    given: str, stored: str
) -> None:
    candidate = make_candidate(identifiers={"doi": given})
    assert candidate.identifiers.doi == stored


@pytest.mark.parametrize(
    "not_a_doi",
    ["science.aar7204", "https://example.org/10.1126/science.aar7204", "10.12/too-short-prefix", "10.1126/"],
)
def test_a_candidate_refuses_a_doi_it_cannot_normalize(not_a_doi: str) -> None:
    with pytest.raises(ValidationError, match="not a DOI"):
        make_candidate(identifiers={"doi": not_a_doi})


def test_a_candidate_refuses_a_pmid_that_is_not_digits() -> None:
    with pytest.raises(ValidationError, match="PMID must be digits only"):
        make_candidate(identifiers={"pmid": "PMC123"})


def test_a_candidate_carries_every_identifier_slot() -> None:
    candidate = make_candidate(
        identifiers={
            "doi": "10.1126/science.aar7204",
            "openalex_id": "W2803461512",
            "semantic_scholar_id": "0f3e2c3c0b",
            "arxiv_id": "2301.00234",
            "pmid": "29930092",
        }
    )
    assert candidate.identifiers.openalex_id == "W2803461512"
    assert candidate.identifiers.semantic_scholar_id == "0f3e2c3c0b"
    assert candidate.identifiers.arxiv_id == "2301.00234"
    assert candidate.identifiers.pmid == "29930092"


def test_a_provider_specific_field_has_nowhere_to_go() -> None:
    """Forbidden: provider-specific fields outside the identifiers and raw_ref slots."""
    with pytest.raises(ValidationError, match="cited_by_count"):
        make_candidate(cited_by_count=12)
    with pytest.raises(ValidationError, match="mag_id"):
        make_candidate(identifiers={"mag_id": "2803461512"})


def test_raw_ref_is_an_opaque_reference_to_a_stored_record() -> None:
    assert make_candidate().raw_ref is None
    assert (
        make_candidate(raw_ref="openalex/works/W2803461512.json").raw_ref == "openalex/works/W2803461512.json"
    )
    with pytest.raises(ValidationError):
        make_candidate(raw_ref="   ")


# --------------------------------------------------------------------------------------------
# Publication time
# --------------------------------------------------------------------------------------------


def test_citation_count_and_open_access_default_to_none() -> None:
    candidate = make_candidate()

    assert candidate.citation_count is None
    assert candidate.open_access is None


def test_a_record_stored_before_citation_count_and_open_access_loads_with_none() -> None:
    stored = {"provider": "openalex", "title": "Methane leakage", "url": "https://example.org/methane"}

    candidate = CandidateResult.model_validate_json(json.dumps(stored))

    assert (candidate.citation_count, candidate.open_access) == (None, None)


def test_a_candidate_refuses_a_negative_citation_count() -> None:
    with pytest.raises(ValidationError, match="citation_count"):
        make_candidate(citation_count=-1)


def test_a_candidate_keeps_a_citation_count_and_whether_it_is_open() -> None:
    candidate = make_candidate(citation_count=0, open_access=False)

    assert (candidate.citation_count, candidate.open_access) == (0, False)
    assert CandidateResult.model_validate_json(candidate.model_dump_json()) == candidate


def test_a_candidate_refuses_a_naive_publication_time() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_candidate(published_at=datetime(2018, 6, 21, 14, 0))  # deliberately naive


def test_a_candidate_stores_an_offset_publication_time_in_utc() -> None:
    eastern_summer = timezone(timedelta(hours=-4))
    candidate = make_candidate(published_at=datetime(2018, 6, 21, 10, 0, tzinfo=eastern_summer))
    assert candidate.published_at == datetime(2018, 6, 21, 14, 0, tzinfo=UTC)
    assert candidate.published_at is not None
    assert candidate.published_at.utcoffset() == timedelta(0)


def test_a_candidate_parses_an_iso_publication_time_with_its_offset() -> None:
    candidate = make_candidate(published_at="2018-06-21T10:00:00-04:00")
    assert candidate.published_at == datetime(2018, 6, 21, 14, 0, tzinfo=UTC)


def test_a_candidate_refuses_an_iso_publication_time_without_an_offset() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_candidate(published_at="2018-06-21T10:00:00")


# --------------------------------------------------------------------------------------------
# ProviderQuery
# --------------------------------------------------------------------------------------------


def test_a_query_carries_text_window_cap_and_language() -> None:
    query = ProviderQuery.model_validate(
        {
            "query": "  methane leakage  ",
            "filters": {
                "since": "2018-01-01T00:00:00Z",
                "until": "2018-12-31T00:00:00Z",
                "max_results": 5,
                "language": "en",
            },
        }
    )
    assert query.query == "methane leakage"
    assert query.filters.since == datetime(2018, 1, 1, tzinfo=UTC)
    assert query.filters.until == datetime(2018, 12, 31, tzinfo=UTC)
    assert query.filters.max_results == 5
    assert query.filters.language == "en"


def test_a_query_needs_text() -> None:
    with pytest.raises(ValidationError):
        ProviderQuery(query="   ")


# --------------------------------------------------------------------------------------------
# ProviderResponse
# --------------------------------------------------------------------------------------------


def test_a_response_carries_results_provider_elapsed_partial_and_error() -> None:
    response = ProviderResponse(
        provider="openalex",
        results=(make_candidate(),),
        elapsed_ms=412.0,
        partial=True,
        error="page 2 timed out",
    )
    assert response.provider == "openalex"
    assert len(response.results) == 1
    assert response.elapsed_ms == 412.0
    assert response.partial is True
    assert response.error == "page 2 timed out"


def test_a_response_with_an_error_must_say_it_is_partial() -> None:
    with pytest.raises(ValidationError, match="must be marked partial"):
        ProviderResponse(provider="openalex", elapsed_ms=1.0, error="timed out")


def test_a_response_refuses_a_result_from_another_provider() -> None:
    with pytest.raises(ValidationError, match="from 'openalex' carries results from 'crossref'"):
        ProviderResponse(
            provider="openalex",
            results=(make_candidate(), make_candidate(provider="crossref")),
            elapsed_ms=1.0,
        )


def test_a_response_refuses_a_negative_elapsed_time() -> None:
    with pytest.raises(ValidationError):
        ProviderResponse(provider="openalex", elapsed_ms=-1.0)


# --------------------------------------------------------------------------------------------
# ProviderHealth
# --------------------------------------------------------------------------------------------


def test_health_reports_state_last_error_latency_and_counts() -> None:
    health = ProviderHealth(
        provider="crossref",
        state=BreakerState.OPEN,
        consecutive_failures=3,
        success_count=10,
        error_count=4,
        skipped_count=2,
        last_error="crossref: unavailable",
        last_error_at=datetime(2026, 10, 21, 12, 0, tzinfo=UTC),
        p50_latency_ms=380.0,
        open_until=datetime(2026, 10, 21, 12, 1, tzinfo=UTC),
    )
    assert health.state is BreakerState.OPEN
    assert (health.success_count, health.error_count, health.skipped_count) == (10, 4, 2)
    assert health.p50_latency_ms == 380.0
    assert health.model_dump(mode="json")["state"] == "open"


def test_an_open_breaker_must_say_when_it_half_opens() -> None:
    with pytest.raises(ValidationError, match="open_until is set exactly when the breaker is open"):
        ProviderHealth(
            provider="crossref",
            state=BreakerState.OPEN,
            consecutive_failures=3,
            success_count=0,
            error_count=3,
            skipped_count=0,
        )


@pytest.mark.parametrize("state", [BreakerState.CLOSED, BreakerState.HALF_OPEN])
def test_only_an_open_breaker_has_an_end(state: BreakerState) -> None:
    with pytest.raises(ValidationError, match="open_until is set exactly when the breaker is open"):
        ProviderHealth(
            provider="crossref",
            state=state,
            consecutive_failures=0,
            success_count=0,
            error_count=0,
            skipped_count=0,
            open_until=datetime(2026, 10, 21, 12, 1, tzinfo=UTC),
        )


def test_the_breaker_states_have_stable_values() -> None:
    assert [state.value for state in BreakerState] == ["closed", "open", "half_open"]


# --------------------------------------------------------------------------------------------
# ProviderStatus
# --------------------------------------------------------------------------------------------


def test_an_answered_call_keeps_the_query_and_the_response_as_returned() -> None:
    query = ProviderQuery(query="methane leakage")
    response = ProviderResponse(
        provider="openalex",
        results=(make_candidate(), make_candidate(citation_count=42, open_access=True)),
        elapsed_ms=212.0,
    )

    status = ProviderStatus(
        provider="openalex", query=query, outcome=ProviderOutcome.OK, elapsed_ms=215.0, response=response
    )

    assert status.response == response
    assert status.query.query == "methane leakage"
    assert status.error is None
    assert ProviderStatus.model_validate_json(status.model_dump_json()) == status


def test_a_failed_call_keeps_its_reason_and_no_response() -> None:
    status = ProviderStatus(
        provider="crossref",
        query=ProviderQuery(query="methane leakage"),
        outcome=ProviderOutcome.TIMEOUT,
        elapsed_ms=10_000.0,
        error="crossref: no answer within 10s",
    )

    assert status.response is None
    assert status.model_dump(mode="json")["outcome"] == "timeout"


def test_an_ok_call_must_carry_its_response() -> None:
    with pytest.raises(ValidationError, match="carries a response exactly when its outcome is ok"):
        ProviderStatus(
            provider="openalex",
            query=ProviderQuery(query="methane leakage"),
            outcome=ProviderOutcome.OK,
            elapsed_ms=1.0,
        )


@pytest.mark.parametrize(
    "outcome", [outcome for outcome in ProviderOutcome if outcome is not ProviderOutcome.OK]
)
def test_a_call_that_did_not_answer_carries_no_response(outcome: ProviderOutcome) -> None:
    with pytest.raises(ValidationError, match="carries a response exactly when its outcome is ok"):
        ProviderStatus(
            provider="openalex",
            query=ProviderQuery(query="methane leakage"),
            outcome=outcome,
            elapsed_ms=1.0,
            response=ProviderResponse(provider="openalex", elapsed_ms=1.0),
            error="openalex: unavailable",
        )


@pytest.mark.parametrize(
    "outcome", [outcome for outcome in ProviderOutcome if outcome is not ProviderOutcome.OK]
)
def test_a_call_that_did_not_answer_must_say_why(outcome: ProviderOutcome) -> None:
    with pytest.raises(ValidationError, match="carries an error exactly when its outcome is not ok"):
        ProviderStatus(
            provider="openalex",
            query=ProviderQuery(query="methane leakage"),
            outcome=outcome,
            elapsed_ms=1.0,
        )


def test_an_answered_call_carries_no_error() -> None:
    with pytest.raises(ValidationError, match="carries an error exactly when its outcome is not ok"):
        ProviderStatus(
            provider="openalex",
            query=ProviderQuery(query="methane leakage"),
            outcome=ProviderOutcome.OK,
            elapsed_ms=1.0,
            response=ProviderResponse(provider="openalex", elapsed_ms=1.0),
            error="openalex: unavailable",
        )


def test_a_status_refuses_another_providers_response() -> None:
    with pytest.raises(ValidationError, match="for 'openalex' carries a response from 'crossref'"):
        ProviderStatus(
            provider="openalex",
            query=ProviderQuery(query="methane leakage"),
            outcome=ProviderOutcome.OK,
            elapsed_ms=1.0,
            response=ProviderResponse(provider="crossref", elapsed_ms=1.0),
        )


def test_the_provider_outcomes_have_stable_values() -> None:
    """Stored with every search, so a renamed value would strand the searches already kept."""
    assert [outcome.value for outcome in ProviderOutcome] == [
        "ok",
        "timeout",
        "error",
        "rate_limited",
        "breaker_open",
        "not_configured",
    ]


# --------------------------------------------------------------------------------------------
# The port
# --------------------------------------------------------------------------------------------


def test_the_port_names_the_discovery_values_rather_than_restating_them() -> None:
    """The port's signature is the domain's own classes, and callers import them from the domain.

    Until `v1-e01-t30` the port module and `debate_core.application.ports` re-exported them; now
    neither does, so a caller cannot reach the values through a port it does not use.
    """
    hints = typing.get_type_hints(providers.SearchProvider.search)
    assert hints["query"] is discovery.ProviderQuery
    assert hints["return"] is discovery.ProviderResponse
    assert not {"CandidateResult", "ProviderQuery", "ProviderResponse"} & set(providers.__all__)


def test_search_provider_is_the_only_port_that_answers_a_provider_query() -> None:
    """ac1: `SearchProvider.search(ProviderQuery) -> ProviderResponse` is the only discovery port."""
    answering: list[str] = []
    for name, port in port_protocols():
        for method_name, method in inspect.getmembers(port, inspect.isfunction):
            annotations = " ".join(str(value) for value in inspect.get_annotations(method).values())
            if "ProviderQuery" in annotations or "ProviderResponse" in annotations:
                answering.append(f"{name}.{method_name}")
    assert answering == ["SearchProvider.search"]
    signature = inspect.signature(providers.SearchProvider.search)
    assert list(signature.parameters) == ["self", "query"]
    assert inspect.iscoroutinefunction(providers.SearchProvider.search)


def port_protocols() -> list[tuple[str, type]]:
    """Every Protocol class defined in a module of `debate_core.application.ports`, by name."""
    found: list[tuple[str, type]] = []
    for module_info in pkgutil.iter_modules(ports.__path__):
        module = importlib.import_module(f"{ports.__name__}.{module_info.name}")
        for name, value in vars(module).items():
            if (
                inspect.isclass(value)
                and getattr(value, "_is_protocol", False)
                and value.__module__ == module.__name__
            ):
                found.append((name, value))
    return sorted(found, key=lambda pair: pair[0])
