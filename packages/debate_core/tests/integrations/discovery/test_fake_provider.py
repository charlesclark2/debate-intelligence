"""The search provider contract kit passes a correct adapter and fails each broken one for its reason.

:class:`FakeProvider` is a minimal HTTP discovery adapter written the way v1-e07-t02 to t07 will
write theirs: httpx for the transport, :func:`provider_error_for_status` for refusals,
:func:`protect_logs` for its credentials. It is bound to
:class:`~debate_core.testing.contracts.search_provider.SearchProviderContract` exactly as a real
adapter is, over respx, so this file is also the worked example of a binding.

Then each rule of the kit is shown biting: a fake that breaks one rule, and only that one, is run
through the check for that rule and must fail it, with the check's own message.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
import respx
from pydantic import SecretStr

from debate_core.application.errors import ProviderError, ProviderRateLimited, ProviderUnavailable
from debate_core.application.ports.providers import SearchProvider
from debate_core.domain.article import ArticleIdentifiers
from debate_core.domain.discovery import CandidateResult, ProviderQuery, ProviderResponse
from debate_core.domain.enums import SourceType
from debate_core.integrations.discovery.http_failures import provider_error_for_status
from debate_core.integrations.discovery.redaction import protect_logs
from debate_core.testing.contracts.search_provider import (
    Recording,
    ReplayedProvider,
    ReplayFactory,
    SearchProviderContract,
    SentRequest,
    TransportFailure,
    assert_maps_recording,
    assert_no_secret_surfaces,
    assert_rate_limit_is_reported,
    assert_server_error_is_reported,
    assert_transport_failure_is_reported,
    assert_unreadable_body_is_reported,
    load_recording,
)

FIXTURES: Final = Path(__file__).resolve().parents[2] / "fixtures" / "discovery" / "fake_provider"
SEARCH_URL: Final = "https://fake-discovery.example.org/v1/search"
API_KEY: Final = "fake-key-0123456789abcdef"
CONTACT_EMAIL: Final = "coach@example.org"
MAX_ATTEMPTS: Final = 3

fake_logger = logging.getLogger("tests.fake_discovery_provider")

_KINDS: Final = {"journal-article": SourceType.SCHOLARLY, "news": SourceType.NEWS}


def run[ResultT](awaitable: Coroutine[Any, Any, ResultT]) -> ResultT:
    return asyncio.run(awaitable)


# --------------------------------------------------------------------------------------------
# The fake adapter
# --------------------------------------------------------------------------------------------


class FakeProvider:
    """A correct discovery adapter for an invented JSON search API."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        api_key: SecretStr,
        contact_email: SecretStr,
        method: str = "GET",
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._contact_email = contact_email
        self._method = method
        protect_logs((api_key.get_secret_value(), contact_email.get_secret_value()))

    @property
    def name(self) -> str:
        return "fake"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(method={self._method!r})"

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        started = time.perf_counter()
        try:
            response = await self._send(query)
        except httpx.TimeoutException as error:
            raise ProviderUnavailable(self.name, "timed out") from error
        except httpx.TransportError as error:
            raise ProviderUnavailable(self.name, f"transport failure: {type(error).__name__}") from error
        failure = self._classify(response)
        if failure is not None:
            raise failure
        results = self._read(response, query)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return ProviderResponse(provider=self.name, results=results, elapsed_ms=elapsed_ms)

    async def _send(self, query: ProviderQuery) -> httpx.Response:
        parameters = {
            "q": query.query,
            "limit": str(query.filters.max_results),
            "mailto": self._contact_email.get_secret_value(),
        }
        headers = {"x-api-key": self._api_key.get_secret_value()}
        if self._method == "POST":
            return await self._client.post(SEARCH_URL, json=parameters, headers=headers)
        return await self._client.get(SEARCH_URL, params=parameters, headers=headers)

    def _classify(self, response: httpx.Response) -> ProviderError | None:
        return provider_error_for_status(
            self.name, response.status_code, response.headers, now=datetime.now(UTC)
        )

    def _read(self, response: httpx.Response, query: ProviderQuery) -> tuple[CandidateResult, ...]:
        try:
            items = response.json()["items"]
            return tuple(self._map(item) for item in items[: query.filters.max_results])
        except (ValueError, KeyError, TypeError) as error:
            raise ProviderUnavailable(self.name, f"unreadable response: {type(error).__name__}") from error

    def _map(self, item: dict[str, Any]) -> CandidateResult:
        return CandidateResult(
            provider=self.name,
            provider_record_id=item["id"],
            title=item["title"],
            url=item["link"],
            identifiers=ArticleIdentifiers(doi=item.get("doi")),
            source_type=_KINDS.get(item.get("kind", ""), SourceType.OTHER),
            authors=tuple(item.get("authors", ())),
            publication=item.get("venue"),
            published_at=item.get("published"),
            snippet=item.get("abstract"),
            raw_ref=f"fake/{item['id']}",
        )


def build_fake(
    provider_class: type[FakeProvider] = FakeProvider, **options: Any
) -> Callable[[httpx.AsyncClient], SearchProvider]:
    def build(client: httpx.AsyncClient) -> SearchProvider:
        return provider_class(
            client, api_key=SecretStr(API_KEY), contact_email=SecretStr(CONTACT_EMAIL), **options
        )

    return build


def replay_with_respx(build: Callable[[httpx.AsyncClient], SearchProvider]) -> ReplayFactory:
    """Serve a recording's exchanges through respx, and nothing else. A real adapter's binding is this.

    Transport failures are raised here, in the transport, rather than as respx side effects: respx
    re-raises a side effect `from` an error that quotes the matched route, query string and all, so
    a contact email in the recorded URL would surface in the exception chain the kit inspects.
    """

    def replay(recording: Recording) -> ReplayedProvider:
        router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
        failures: dict[SentRequest, TransportFailure] = {}
        for exchange in recording.exchanges:
            if exchange.failure is not None:
                failures[SentRequest(exchange.method.upper(), exchange.url)] = exchange.failure
            elif exchange.response is not None:
                answer = exchange.response
                router.route(method=exchange.method, url=exchange.url).return_value = httpx.Response(
                    answer.status, headers=answer.headers, content=answer.body
                )
        sent: list[SentRequest] = []

        async def transport(request: httpx.Request) -> httpx.Response:
            this = SentRequest(request.method, str(request.url))
            sent.append(this)
            failure = failures.get(this)
            if failure is TransportFailure.TIMEOUT:
                raise httpx.ReadTimeout("timed out", request=request)
            if failure is TransportFailure.CONNECTION_ERROR:
                raise httpx.ConnectError("connection refused", request=request)
            return await router.async_handler(request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        return ReplayedProvider(build(client), lambda: tuple(sent))

    return replay


# --------------------------------------------------------------------------------------------
# A correct adapter passes the kit
# --------------------------------------------------------------------------------------------


class TestFakeProvider(SearchProviderContract):
    """The binding a real adapter writes: a recording, a replay, and the secrets it configured."""

    @pytest.fixture
    def recording(self) -> Recording:
        return load_recording(FIXTURES / "search.json")

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(build_fake())

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        return (API_KEY, CONTACT_EMAIL)


class TestFakeProviderOverPost(TestFakeProvider):
    """The same adapter searching with a `POST`, which it must never send twice."""

    @pytest.fixture
    def recording(self) -> Recording:
        return load_recording(FIXTURES / "search_by_post.json")

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(build_fake(method="POST"))


class RetriesAGetOnce(FakeProvider):
    """Retries an idempotent `GET` once after a server error or a transport failure: allowed."""

    async def search(self, query: ProviderQuery) -> ProviderResponse:
        try:
            return await super().search(query)
        except ProviderRateLimited:
            raise
        except ProviderUnavailable:
            return await super().search(query)


class TestFakeProviderThatRetriesAGetOnce(TestFakeProvider):
    """An idempotent request may be sent again, up to `max_attempts` times in one search."""

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        return replay_with_respx(build_fake(RetriesAGetOnce))


def test_the_recording_loads_with_its_hand_written_expectations() -> None:
    recording = load_recording(FIXTURES / "search.json")
    assert recording.name == "search"
    assert recording.query.filters.max_results == 2
    assert [exchange.method for exchange in recording.exchanges] == ["GET"]
    assert recording.exchanges[0].response is not None
    assert recording.exchanges[0].response.status == 200
    assert [result.provider_record_id for result in recording.expected] == ["FK-0001", "FK-0002"]
    assert recording.expected[0].identifiers.doi == "10.5555/fake.0001"


# --------------------------------------------------------------------------------------------
# Each rule fails a fake that breaks it
# --------------------------------------------------------------------------------------------


class DropsAuthors(FakeProvider):
    def _map(self, item: dict[str, Any]) -> CandidateResult:
        return super()._map(item).evolve(authors=())


class IgnoresMaxResults(FakeProvider):
    def _read(self, response: httpx.Response, query: ProviderQuery) -> tuple[CandidateResult, ...]:
        return tuple(self._map(item) for item in response.json()["items"])


class SendsAnExtraRequest(FakeProvider):
    async def search(self, query: ProviderQuery) -> ProviderResponse:
        answer = await super().search(query)
        await self._client.get(SEARCH_URL, params={"q": query.query, "page": "2"})
        return answer


class CallsARateLimitUnavailable(FakeProvider):
    def _classify(self, response: httpx.Response) -> ProviderError | None:
        if response.status_code == 429:
            return ProviderUnavailable(self.name, "HTTP 429")
        return super()._classify(response)


class ForgetsRetryAfter(FakeProvider):
    def _classify(self, response: httpx.Response) -> ProviderError | None:
        if response.status_code == 429:
            return ProviderRateLimited(self.name, "HTTP 429")
        return super()._classify(response)


class RetriesARateLimit(FakeProvider):
    async def search(self, query: ProviderQuery) -> ProviderResponse:
        try:
            return await super().search(query)
        except ProviderRateLimited:
            return await super().search(query)


class AnswersEmptyOnAServerError(FakeProvider):
    def _classify(self, response: httpx.Response) -> ProviderError | None:
        return None if response.status_code >= 500 else super()._classify(response)

    def _read(self, response: httpx.Response, query: ProviderQuery) -> tuple[CandidateResult, ...]:
        return () if response.status_code >= 500 else super()._read(response, query)


class RetriesAPost(FakeProvider):
    async def search(self, query: ProviderQuery) -> ProviderResponse:
        try:
            return await super().search(query)
        except ProviderUnavailable:
            return await super().search(query)


class RetriesAGetFourTimes(FakeProvider):
    async def search(self, query: ProviderQuery) -> ProviderResponse:
        for _ in range(3):
            try:
                return await super().search(query)
            except ProviderUnavailable:
                continue
        return await super().search(query)


class LeaksTheTransportError(FakeProvider):
    async def search(self, query: ProviderQuery) -> ProviderResponse:
        response = await self._send(query)
        failure = self._classify(response)
        if failure is not None:
            raise failure
        return ProviderResponse(provider=self.name, results=self._read(response, query), elapsed_ms=1.0)


class LeaksTheParserError(FakeProvider):
    def _read(self, response: httpx.Response, query: ProviderQuery) -> tuple[CandidateResult, ...]:
        items = response.json()["items"]
        return tuple(self._map(item) for item in items[: query.filters.max_results])


class QuotesTheUrlInItsError(FakeProvider):
    async def search(self, query: ProviderQuery) -> ProviderResponse:
        try:
            return await super().search(query)
        except ProviderUnavailable as error:
            raise ProviderUnavailable(
                self.name, f"{error} calling {SEARCH_URL}?mailto={CONTACT_EMAIL}"
            ) from error


class LogsItsKey(FakeProvider):
    async def search(self, query: ProviderQuery) -> ProviderResponse:
        fake_logger.debug("searching with key %s", self._api_key.get_secret_value())
        return await super().search(query)


class ShowsItsKeyInItsRepr(FakeProvider):
    def __repr__(self) -> str:
        return f"ShowsItsKeyInItsRepr(api_key={self._api_key.get_secret_value()!r})"


UNPROTECTED_EMAIL: Final = "someone.else@example.net"


class SkipsLogProtection(FakeProvider):
    """Never calls protect_logs, so httpx's own `HTTP Request:` line carries its mailto."""

    def __init__(self, client: httpx.AsyncClient, **_: Any) -> None:
        self._client = client
        self._api_key = SecretStr("unprotected-key")
        self._contact_email = SecretStr(UNPROTECTED_EMAIL)
        self._method = "GET"


def broken(
    provider_class: type[FakeProvider], *, recording: str = "search.json", **options: Any
) -> tuple[ReplayFactory, Recording]:
    return replay_with_respx(build_fake(provider_class, **options)), load_recording(FIXTURES / recording)


@pytest.mark.parametrize(
    ("provider_class", "message"),
    [
        (DropsAuthors, "result 0 differs from the expected mapping in authors"),
        (IgnoresMaxResults, "3 results for max_results=2"),
        (SendsAnExtraRequest, "not mocked"),
    ],
)
def test_the_mapping_check_fails_an_adapter_that_maps_or_requests_wrongly(
    provider_class: type[FakeProvider], message: str
) -> None:
    replay, recording = broken(provider_class)
    with pytest.raises(AssertionError, match=message):
        run(assert_maps_recording(replay, recording))


@pytest.mark.parametrize(
    ("provider_class", "message"),
    [
        (CallsARateLimitUnavailable, "a 429 must raise ProviderRateLimited, got ProviderUnavailable"),
        (ForgetsRetryAfter, "the error carries retry_after_seconds=None"),
        (RetriesARateLimit, "the rate-limited request was sent 2 times"),
    ],
)
def test_the_rate_limit_check_fails_an_adapter_that_ignores_a_429(
    provider_class: type[FakeProvider], message: str
) -> None:
    replay, recording = broken(provider_class)
    with pytest.raises(AssertionError, match=message):
        run(assert_rate_limit_is_reported(replay, recording))


def test_the_server_error_check_fails_an_adapter_that_answers_a_503_as_if_nothing_happened() -> None:
    replay, recording = broken(AnswersEmptyOnAServerError)
    with pytest.raises(AssertionError, match="after a 503 on its only request the adapter answered"):
        run(assert_server_error_is_reported(replay, recording, MAX_ATTEMPTS))


def test_the_server_error_check_fails_an_adapter_that_sends_a_post_twice() -> None:
    replay, recording = broken(RetriesAPost, recording="search_by_post.json", method="POST")
    with pytest.raises(AssertionError, match="the non-idempotent POST was sent 2 times"):
        run(assert_server_error_is_reported(replay, recording, MAX_ATTEMPTS))


def test_the_server_error_check_fails_an_adapter_that_retries_a_get_past_max_attempts() -> None:
    replay, recording = broken(RetriesAGetFourTimes)
    with pytest.raises(AssertionError, match=r"was sent 4 times, at most 3"):
        run(assert_server_error_is_reported(replay, recording, MAX_ATTEMPTS))


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (TransportFailure.TIMEOUT, "a timeout must raise ProviderUnavailable, got ReadTimeout"),
        (
            TransportFailure.CONNECTION_ERROR,
            "a connection error must raise ProviderUnavailable, got ConnectError",
        ),
    ],
)
def test_the_transport_check_fails_an_adapter_that_leaks_httpx(
    failure: TransportFailure, message: str
) -> None:
    replay, recording = broken(LeaksTheTransportError)
    with pytest.raises(AssertionError, match=message):
        run(assert_transport_failure_is_reported(replay, recording, MAX_ATTEMPTS, failure))


def test_the_unreadable_body_check_fails_an_adapter_that_leaks_its_parser() -> None:
    replay, recording = broken(LeaksTheParserError)
    with pytest.raises(
        AssertionError, match="an unreadable body must raise a ProviderError, got JSONDecodeError"
    ):
        run(assert_unreadable_body_is_reported(replay, recording, MAX_ATTEMPTS))


@pytest.mark.parametrize(
    ("provider_class", "secrets", "where"),
    [
        (QuotesTheUrlInItsError, (API_KEY, CONTACT_EMAIL), "ProviderUnavailable: fake: fake: HTTP 503"),
        (LogsItsKey, (API_KEY, CONTACT_EMAIL), "log record on tests.fake_discovery_provider"),
        (ShowsItsKeyInItsRepr, (API_KEY, CONTACT_EMAIL), "repr: ShowsItsKeyInItsRepr"),
        (SkipsLogProtection, (UNPROTECTED_EMAIL,), "log record on httpx: HTTP Request: GET"),
    ],
)
def test_the_secrets_check_fails_an_adapter_that_lets_one_out(
    provider_class: type[FakeProvider], secrets: tuple[str, ...], where: str
) -> None:
    replay, recording = broken(provider_class)
    if provider_class is SkipsLogProtection:
        recording = recording_for(UNPROTECTED_EMAIL, recording)
    with pytest.raises(AssertionError, match="a configured secret surfaced in") as caught:
        run(assert_no_secret_surfaces(replay, recording, secrets))
    assert where in str(caught.value)


def recording_for(email: str, recording: Recording) -> Recording:
    """The same recording, requested with another contact email."""
    encoded = email.replace("@", "%40")
    exchanges = tuple(
        replace(exchange, url=exchange.url.replace("coach%40example.org", encoded))
        for exchange in recording.exchanges
    )
    return replace(recording, exchanges=exchanges)


def test_the_secrets_check_has_nothing_to_find_without_secrets() -> None:
    replay, recording = broken(ShowsItsKeyInItsRepr)
    run(assert_no_secret_surfaces(replay, recording, ()))
