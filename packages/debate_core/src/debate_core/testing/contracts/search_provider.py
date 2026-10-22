"""The contract every discovery adapter passes, on its own recorded fixtures.

v1-e07-t02 to t07 each add a :class:`~debate_core.application.ports.providers.SearchProvider`
(OpenAlex, Crossref, Semantic Scholar, feeds, GDELT, government sources). Each one is held to the
same rules by subclassing :class:`SearchProviderContract` and supplying two fixtures:

* `recording` — a :class:`Recording` loaded with :func:`load_recording`: the query, the HTTP
  exchanges recorded for it, and the :class:`~debate_core.domain.discovery.CandidateResult` list it
  must map to, **written by hand** from the recorded body (working agreement 6);
* `replay` — a :data:`ReplayFactory`: given a recording, build the adapter over a transport that
  serves that recording's exchanges and refuses any other request (respx, in practice), and report
  the requests it sent.

The contract then runs the recording, and versions of it in which the first exchange's answer is
replaced by a refusal or a failure, and checks:

1. **Mapping.** The recorded answer maps to exactly the expected results, under the adapter's
   name, complete, within `max_results`, and the adapter sent exactly the recorded requests.
2. **Rate limits.** A `429` with `Retry-After: 120` is
   :class:`~debate_core.application.errors.ProviderRateLimited` carrying 120 seconds, and the refused
   request is not sent again.
3. **Server errors.** A `503` is :class:`~debate_core.application.errors.ProviderUnavailable`.
4. **Transport failures.** A timeout and a refused connection are `ProviderUnavailable`, never the
   transport library's own exception.
5. **Unreadable bodies.** A `200` whose body the adapter cannot parse is a
   :class:`~debate_core.application.errors.ProviderError`, never a parser's exception.
6. **No resending.** In every failure above, a request that is not idempotent (anything but `GET`,
   `HEAD` and `OPTIONS`) is sent once, and an idempotent one at most `max_attempts` times.
7. **Secrets.** None of the values in the `secrets` fixture appears in any error, any exception it
   was raised from, the adapter's `repr`, or any log record at any level, from any logger. An
   adapter that is handed a credential calls
   :func:`~debate_core.integrations.discovery.redaction.protect_logs` in its constructor, because
   httpx logs request URLs, query strings included, at INFO.

Where the recording has more than one exchange (a feed list, a search followed by a detail
request), an adapter may answer a failure of the first one partially instead of raising: a
:class:`~debate_core.domain.discovery.ProviderResponse` with `partial=True` and an `error`. With one
exchange, nothing was answered, so it must raise.

Each check is also a plain function (:func:`assert_maps_recording` and the five after it), so a
broken adapter can be shown failing one rule at a time; that is how
`packages/debate_core/tests/integrations/discovery/test_fake_provider.py` proves the kit bites.

**No transport here.** `debate_core.testing` may not import httpx (the import-linter contract that
keeps it inside the adapters), so this module describes exchanges as plain data and the binding
turns them into mocked responses. The fake provider's binding in `test_fake_provider.py`
(`replay_with_respx`) is the worked example, and a real adapter's binding can copy it whole. One
thing in it is not obvious: it raises a transport failure in its own transport function rather than
as a respx `side_effect`, because respx re-raises a side effect `from` an error that quotes the
matched route, query string included, and check 7 would find the contact email there.

## The recording format

A recording is a JSON file; bodies and the expected results sit beside it::

    {
      "query": {"query": "methane leakage", "filters": {"max_results": 2}},
      "exchanges": [
        {
          "request": {"method": "GET", "url": "https://api.example.org/search?q=methane+leakage&limit=2"},
          "response": {"status": 200, "headers": {"content-type": "application/json"},
                       "body_file": "search.body.json"}
        }
      ],
      "expected_results_file": "search.expected.json"
    }

`body` may be given inline as text instead of `body_file`. A recording is committed and read in
review: bodies are recorded from a provider's public API or written by hand, never from student
work, and any credential in a recorded URL is a made-up sentinel the binding configures.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Final, NamedTuple, cast
from urllib.parse import quote, quote_plus

import pytest

from debate_core.application.errors import ProviderError, ProviderRateLimited, ProviderUnavailable
from debate_core.application.ports.providers import SearchProvider
from debate_core.domain.discovery import CandidateResult, ProviderQuery, ProviderResponse
from debate_core.testing.contracts.harness import AdapterContract

__all__ = [
    "IDEMPOTENT_METHODS",
    "RATE_LIMIT_RETRY_AFTER_SECONDS",
    "RecordedExchange",
    "RecordedResponse",
    "Recording",
    "ReplayFactory",
    "ReplayedProvider",
    "SearchProviderContract",
    "SentRequest",
    "TransportFailure",
    "assert_maps_recording",
    "assert_no_secret_surfaces",
    "assert_rate_limit_is_reported",
    "assert_server_error_is_reported",
    "assert_transport_failure_is_reported",
    "assert_unreadable_body_is_reported",
    "load_recording",
]

IDEMPOTENT_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})
"""Methods a retry cannot do twice: the only ones an adapter may send again after a failure."""

RATE_LIMIT_RETRY_AFTER_SECONDS: Final = 120
"""The `Retry-After` the rate-limit check sends, and the wait it expects the error to carry."""

UNREADABLE_BODY: Final = b"\x00<<not what this provider sends>>\xff"
"""The body of the unreadable-answer check: valid as nothing an adapter parses."""


class TransportFailure(StrEnum):
    """A request that got no HTTP answer at all."""

    TIMEOUT = "timeout"
    """The provider did not answer in time (httpx's `ReadTimeout`)."""

    CONNECTION_ERROR = "connection_error"
    """The connection was refused or dropped (httpx's `ConnectError`)."""


@dataclass(frozen=True, slots=True)
class RecordedResponse:
    """What came back for one request."""

    status: int
    headers: dict[str, str] = field(default_factory=dict[str, str])
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class RecordedExchange:
    """One request and either its response or the transport failure that took its place."""

    method: str
    url: str
    response: RecordedResponse | None = None
    failure: TransportFailure | None = None

    def __post_init__(self) -> None:
        if (self.response is None) == (self.failure is None):
            raise ValueError("an exchange has exactly one of a response and a transport failure")

    @property
    def idempotent(self) -> bool:
        """Whether sending this request twice is the same as sending it once."""
        return self.method.upper() in IDEMPOTENT_METHODS


@dataclass(frozen=True, slots=True)
class Recording:
    """One recorded search: the query, what crossed the wire, and what it must map to."""

    name: str
    query: ProviderQuery
    exchanges: tuple[RecordedExchange, ...]
    expected: tuple[CandidateResult, ...]

    def __post_init__(self) -> None:
        if not self.exchanges:
            raise ValueError(f"recording {self.name!r} has no exchanges")

    def with_first_answer(
        self, *, response: RecordedResponse | None = None, failure: TransportFailure | None = None
    ) -> Recording:
        """This recording with the first exchange answered differently, and nothing expected."""
        first = replace(self.exchanges[0], response=response, failure=failure)
        return replace(self, exchanges=(first, *self.exchanges[1:]), expected=())


class SentRequest(NamedTuple):
    """A request the adapter sent, as the binding's transport saw it."""

    method: str
    url: str


class ReplayedProvider(NamedTuple):
    """The adapter under test, and a view of the requests it has sent so far."""

    provider: SearchProvider
    sent: Callable[[], Sequence[SentRequest]]


type ReplayFactory = Callable[[Recording], ReplayedProvider]
"""Builds the adapter over a transport that serves `recording`'s exchanges and refuses anything else.

A request that matches an exchange gets that exchange's response (or failure) every time it is
sent, so a retry sees the same answer. A request that matches none must fail loudly: respx's
default `assert_all_mocked=True` raises an `AssertionError`, which fails the check that sent it.
"""


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------


def load_recording(path: Path) -> Recording:
    """Read the recording at `path`, its bodies and its hand-written expected results."""
    document = json.loads(path.read_text(encoding="utf-8"))
    exchanges = tuple(_exchange(entry, path.parent) for entry in document["exchanges"])
    expected_path = path.parent / document["expected_results_file"]
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    return Recording(
        name=path.stem,
        query=ProviderQuery.model_validate(document["query"]),
        exchanges=exchanges,
        expected=tuple(CandidateResult.model_validate(item) for item in expected),
    )


def _exchange(entry: dict[str, object], directory: Path) -> RecordedExchange:
    request = cast(dict[str, str], entry["request"])
    failure = entry.get("failure")
    if failure is not None:
        return RecordedExchange(request["method"], request["url"], failure=TransportFailure(str(failure)))
    answer = cast(dict[str, object], entry["response"])
    if "body_file" in answer:
        body = (directory / str(answer["body_file"])).read_bytes()
    else:
        body = str(answer.get("body", "")).encode("utf-8")
    headers = cast(dict[str, str], answer.get("headers", {}))
    status = answer["status"]
    if not isinstance(status, int):
        raise ValueError(f"a recorded status must be an integer, got {status!r}")
    return RecordedExchange(
        request["method"], request["url"], response=RecordedResponse(status, dict(headers), body)
    )


# --------------------------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------------------------


async def assert_maps_recording(replay: ReplayFactory, recording: Recording) -> None:
    """The recorded answer maps to exactly the expected results, from exactly the recorded requests."""
    replayed = replay(recording)
    response = await replayed.provider.search(recording.query)
    name = replayed.provider.name
    assert response.provider == name, f"the response is named {response.provider!r}, the adapter {name!r}"
    assert not response.partial, f"a fully recorded answer came back partial: {response.error}"
    assert len(response.results) <= recording.query.filters.max_results, (
        f"{len(response.results)} results for max_results={recording.query.filters.max_results}"
    )
    actual = [result.model_dump(mode="json") for result in response.results]
    expected = [result.model_dump(mode="json") for result in recording.expected]
    assert len(actual) == len(expected), f"mapped {len(actual)} results, expected {len(expected)}"
    for index, (got, wanted) in enumerate(zip(actual, expected, strict=True)):
        differing = sorted(key for key in wanted if got.get(key) != wanted[key])
        assert not differing, (
            f"result {index} differs from the expected mapping in {', '.join(differing)}: "
            + "; ".join(f"{key}: got {got.get(key)!r}, expected {wanted[key]!r}" for key in differing)
        )
    recorded = Counter(SentRequest(exchange.method.upper(), exchange.url) for exchange in recording.exchanges)
    sent = Counter(SentRequest(request.method.upper(), request.url) for request in replayed.sent())
    assert sent == recorded, f"sent {sorted(sent.elements())}, recorded {sorted(recorded.elements())}"


async def assert_rate_limit_is_reported(replay: ReplayFactory, recording: Recording) -> None:
    """A 429 is ProviderRateLimited with its Retry-After, and the refused request is not sent again."""
    refused = recording.with_first_answer(
        response=RecordedResponse(429, {"Retry-After": str(RATE_LIMIT_RETRY_AFTER_SECONDS)})
    )
    replayed = replay(refused)
    outcome = await _outcome(replayed, refused)
    if isinstance(outcome, ProviderResponse):
        _assert_partial_is_allowed(outcome, refused, "a 429")
    else:
        assert isinstance(outcome, ProviderRateLimited), (
            f"a 429 must raise ProviderRateLimited, got {type(outcome).__name__}: {outcome}"
        )
        assert outcome.retry_after_seconds == RATE_LIMIT_RETRY_AFTER_SECONDS, (
            f"the 429 said Retry-After: {RATE_LIMIT_RETRY_AFTER_SECONDS}, "
            f"the error carries retry_after_seconds={outcome.retry_after_seconds}"
        )
    times = _times_sent(replayed, refused.exchanges[0])
    assert times == 1, f"the rate-limited request was sent {times} times; a refused request is not sent again"


async def assert_server_error_is_reported(
    replay: ReplayFactory, recording: Recording, max_attempts: int
) -> None:
    """A 503 is ProviderUnavailable, and nothing is resent beyond what the method allows."""
    failing = recording.with_first_answer(response=RecordedResponse(503))
    await _assert_unavailable(replay, failing, max_attempts, "a 503")


async def assert_transport_failure_is_reported(
    replay: ReplayFactory, recording: Recording, max_attempts: int, failure: TransportFailure
) -> None:
    """A transport failure is ProviderUnavailable, never the transport library's exception."""
    failing = recording.with_first_answer(failure=failure)
    await _assert_unavailable(replay, failing, max_attempts, f"a {failure.value.replace('_', ' ')}")


async def assert_unreadable_body_is_reported(
    replay: ReplayFactory, recording: Recording, max_attempts: int
) -> None:
    """A 200 the adapter cannot parse is a ProviderError (or a partial answer), never a parser's exception."""
    first = recording.exchanges[0].response
    headers = dict(first.headers) if first is not None else {}
    garbled = recording.with_first_answer(response=RecordedResponse(200, headers, UNREADABLE_BODY))
    replayed = replay(garbled)
    outcome = await _outcome(replayed, garbled)
    if isinstance(outcome, ProviderResponse):
        _assert_partial_is_allowed(outcome, garbled, "an unreadable body")
    else:
        assert isinstance(outcome, ProviderError), (
            f"an unreadable body must raise a ProviderError, got {type(outcome).__name__}: {outcome}"
        )
    _assert_not_resent(replayed, garbled, max_attempts)


async def assert_no_secret_surfaces(
    replay: ReplayFactory, recording: Recording, secrets: Sequence[str]
) -> None:
    """No secret in any error, its causes, the adapter's repr or any log record, in any scenario.

    A value is looked for in its URL-encoded spellings too, because that is how httpx's request log
    line and a quoted request URL carry it.
    """
    values = sorted(
        {
            spelling
            for value in secrets
            if value
            for spelling in (value, quote(value, safe=""), quote_plus(value))
        }
    )
    if not values:
        return
    scenarios = [
        recording,
        recording.with_first_answer(response=RecordedResponse(429, {"Retry-After": "1"})),
        recording.with_first_answer(response=RecordedResponse(503)),
        recording.with_first_answer(failure=TransportFailure.TIMEOUT),
        recording.with_first_answer(failure=TransportFailure.CONNECTION_ERROR),
        recording.with_first_answer(response=RecordedResponse(200, {}, UNREADABLE_BODY)),
    ]
    surfaces: list[tuple[str, str]] = []
    with _every_log_record() as records:
        for scenario in scenarios:
            replayed = replay(scenario)
            surfaces.append(("repr", repr(replayed.provider)))
            outcome = await _outcome(replayed, scenario)
            if isinstance(outcome, ProviderResponse):
                surfaces.append(("response error", outcome.error or ""))
                continue
            chain: BaseException | None = outcome
            seen: set[int] = set()
            while chain is not None and id(chain) not in seen:
                seen.add(id(chain))
                surfaces.extend(
                    ((f"{type(chain).__name__}", str(chain)), (f"{type(chain).__name__}", repr(chain)))
                )
                chain = chain.__cause__ or chain.__context__
    surfaces.extend((f"log record on {record.name}", record.getMessage()) for record in records)
    leaked = [f"{where}: {text}" for where, text in surfaces if any(value in text for value in values)]
    assert not leaked, "a configured secret surfaced in:\n" + "\n".join(leaked)


async def _outcome(replayed: ReplayedProvider, recording: Recording) -> ProviderResponse | BaseException:
    try:
        return await replayed.provider.search(recording.query)
    except AssertionError:
        raise
    except Exception as error:
        return error


async def _assert_unavailable(
    replay: ReplayFactory, recording: Recording, max_attempts: int, what: str
) -> None:
    replayed = replay(recording)
    outcome = await _outcome(replayed, recording)
    if isinstance(outcome, ProviderResponse):
        _assert_partial_is_allowed(outcome, recording, what)
    else:
        assert isinstance(outcome, ProviderUnavailable), (
            f"{what} must raise ProviderUnavailable, got {type(outcome).__name__}: {outcome}"
        )
    _assert_not_resent(replayed, recording, max_attempts)


def _assert_partial_is_allowed(response: ProviderResponse, recording: Recording, what: str) -> None:
    assert len(recording.exchanges) > 1, (
        f"after {what} on its only request the adapter answered instead of raising "
        f"(partial={response.partial}, {len(response.results)} results)"
    )
    assert response.partial and response.error, f"after {what} the answer must be partial and say why"


def _times_sent(replayed: ReplayedProvider, exchange: RecordedExchange) -> int:
    return sum(
        1
        for request in replayed.sent()
        if request.method.upper() == exchange.method.upper() and request.url == exchange.url
    )


def _assert_not_resent(replayed: ReplayedProvider, recording: Recording, max_attempts: int) -> None:
    first = recording.exchanges[0]
    times = _times_sent(replayed, first)
    if first.idempotent:
        assert times <= max_attempts, (
            f"{first.method} {first.url} was sent {times} times, at most {max_attempts}"
        )
    else:
        assert times == 1, f"the non-idempotent {first.method} was sent {times} times; it may be sent once"


@contextmanager
def _every_log_record() -> Iterator[list[logging.LogRecord]]:
    """Capture every record, at every level, from every logger that propagates to the root."""
    records: list[logging.LogRecord] = []

    class _Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    root = logging.getLogger()
    handler = _Keep(level=logging.DEBUG)
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


# --------------------------------------------------------------------------------------------
# The contract class
# --------------------------------------------------------------------------------------------


class SearchProviderContract(AdapterContract):
    """Subclass in a `Test…` class and supply `replay` and `recording`; see the module docstring."""

    @pytest.fixture
    def replay(self) -> ReplayFactory:
        """Build the adapter over the recording's exchanges. Every binding overrides this."""
        raise NotImplementedError("a SearchProviderContract binding must override the replay fixture")

    @pytest.fixture
    def recording(self) -> Recording:
        """The recorded search to replay. Every binding overrides this."""
        raise NotImplementedError("a SearchProviderContract binding must override the recording fixture")

    @pytest.fixture
    def secrets(self) -> tuple[str, ...]:
        """The credential and contact-email values the binding configured the adapter with."""
        return ()

    @pytest.fixture
    def max_attempts(self) -> int:
        """How many times an idempotent request may be sent in one search: 1 + `http.max_retries`."""
        return 3

    async def test_it_is_a_search_provider_with_a_name(
        self, replay: ReplayFactory, recording: Recording
    ) -> None:
        provider = replay(recording).provider
        assert isinstance(provider, SearchProvider)
        assert provider.name.strip(), "a provider needs the name settings know it by"

    async def test_the_recording_maps_to_the_expected_results(
        self, replay: ReplayFactory, recording: Recording
    ) -> None:
        await assert_maps_recording(replay, recording)

    async def test_a_429_is_rate_limited_with_its_retry_after(
        self, replay: ReplayFactory, recording: Recording
    ) -> None:
        await assert_rate_limit_is_reported(replay, recording)

    async def test_a_server_error_is_unavailable(
        self, replay: ReplayFactory, recording: Recording, max_attempts: int
    ) -> None:
        await assert_server_error_is_reported(replay, recording, max_attempts)

    @pytest.mark.parametrize("failure", list(TransportFailure), ids=lambda failure: failure.value)
    async def test_a_transport_failure_is_unavailable(
        self, replay: ReplayFactory, recording: Recording, max_attempts: int, failure: TransportFailure
    ) -> None:
        await assert_transport_failure_is_reported(replay, recording, max_attempts, failure)

    async def test_an_unreadable_body_is_a_provider_error(
        self, replay: ReplayFactory, recording: Recording, max_attempts: int
    ) -> None:
        await assert_unreadable_body_is_reported(replay, recording, max_attempts)

    async def test_no_secret_surfaces(
        self, replay: ReplayFactory, recording: Recording, secrets: tuple[str, ...]
    ) -> None:
        await assert_no_secret_surfaces(replay, recording, secrets)
