"""The Crossref DOI lookup, offline: respx serves synthetic `/works/{doi}` answers (v1-e06-t01 ac2).

Every answer is written by hand under the 10.5555 test prefix (`tests/fixtures/citation/README.md`);
nothing is recorded from Crossref, and a request no route answers fails the test that made it. The
expected work below is written from the fixture, not saved from a run (working agreement 6).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from typing import Any, Final

import httpx
import pytest
import respx
from pydantic import SecretStr

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.doi_metadata import DoiAuthor, DoiDate, DoiMetadataSource, DoiWork
from debate_core.application.settings import HttpSettings, ProviderSettings
from debate_core.integrations.crossref_doi import (
    CROSSREF_WORKS_URL,
    CrossrefDoiClient,
    DoiCache,
    FileDoiCache,
    InMemoryDoiCache,
    crossref_doi_client,
    work_from_message,
)
from debate_core.integrations.discovery.redaction import PROTECTED_LOGGERS

pytestmark = pytest.mark.anyio

FIXTURES: Final = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "citation" / "crossref"
DOI: Final = "10.5555/jscs.2026.0012"
WORK_URL: Final = f"{CROSSREF_WORKS_URL}{DOI}"
VERSION: Final = "0.0.0-test"

EXPECTED_WORK: Final = DoiWork(
    doi=DOI,
    title="Moral Hazard and the Return of Lost Species",
    container_title="Journal of Synthetic Conservation Studies",
    authors=(
        DoiAuthor(
            given="Rhea",
            family="Okonkwo-Hale",
            affiliations=("Department of Ecology, University of Synthetic Studies",),
        ),
        DoiAuthor(given="Tomas", family="Lindqvist"),
    ),
    dates=(
        DoiDate(kind="published", year=2026, month=4, day=20),
        DoiDate(kind="published-online", year=2026, month=4, day=20),
        DoiDate(kind="published-print", year=2026, month=6),
        DoiDate(kind="issued", year=2026, month=4, day=20),
    ),
)


def contact_email() -> str:
    """Built at run time, so a traceback quoting this file's source cannot be what leaks it."""
    return "-".join(("crossref", "coach")) + "@example.org"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def bare_protected_loggers() -> Iterator[None]:
    """The protected loggers start with no filters, and get theirs back afterwards (agreement 10)."""
    saved = {name: list(logging.getLogger(name).filters) for name in PROTECTED_LOGGERS}
    for name in PROTECTED_LOGGERS:
        logging.getLogger(name).filters.clear()
    yield
    for name, filters in saved.items():
        logging.getLogger(name).filters[:] = filters


def works_body() -> bytes:
    return (FIXTURES / "works-10.5555-jscs.2026.0012.json").read_bytes()


type Failure = Callable[[httpx.Request], Awaitable[httpx.Response]]


class Served:
    """A respx router for the answers, every request kept, transport failures raised by hand.

    Failures are raised here rather than as respx side effects, because respx re-raises a side effect
    `from` an error quoting the matched route, query string and contact email included.
    """

    def __init__(self) -> None:
        self.router = respx.MockRouter(assert_all_called=False, assert_all_mocked=True)
        self.requests: list[httpx.Request] = []
        self.failure: type[httpx.TransportError] | None = None

    def answer(self, url: str, status: int = 200, content: bytes = b"") -> None:
        self.router.get(url__startswith=url).return_value = httpx.Response(
            status, content=content, headers={"content-type": "application/json"}
        )

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure("failed", request=request)
        return await self.router.async_handler(request)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


def client_over(
    served: Served, *, cache: DoiCache | None = None, email: str | None = None
) -> CrossrefDoiClient:
    settings = ProviderSettings(contact_email=SecretStr(email) if email is not None else None)
    return crossref_doi_client(
        HttpSettings(), settings, version=VERSION, cache=cache or InMemoryDoiCache(), transport=served.transport()
    )


@pytest.fixture
def served() -> Served:
    served = Served()
    served.answer(WORK_URL, content=works_body())
    return served


# --------------------------------------------------------------------------------------------
# A work, mapped
# --------------------------------------------------------------------------------------------


async def test_a_registered_doi_comes_back_as_the_work_its_deposit_describes(served: Served) -> None:
    client = client_over(served)

    assert await client.lookup(DOI) == EXPECTED_WORK
    await client.aclose()


async def test_the_client_is_a_doi_metadata_source(served: Served) -> None:
    assert isinstance(client_over(served), DoiMetadataSource)


def test_a_deposit_with_a_name_given_whole_an_orcid_and_markup_in_its_title_is_mapped_as_stated() -> None:
    message = {
        "DOI": "10.5555/X",
        "title": ["  The <i>Mammuthus</i>   revival  "],
        "container-title": [],
        "author": [
            {"name": "Synthetic Consortium", "affiliation": [{"name": " "}, "not a mapping"]},
            {"family": "Ruiz", "ORCID": "https://orcid.org/0000-0000-0000-0001"},
            {"given": "Nobody"},
            "not a mapping",
        ],
        "issued": {"date-parts": [[2026]]},
        "published-online": {"date-parts": [["2026", 4, 1]]},
    }

    assert work_from_message(message, requested_doi="10.5555/x") == DoiWork(
        doi="10.5555/x",
        title="The Mammuthus revival",
        authors=(
            DoiAuthor(name="Synthetic Consortium"),
            DoiAuthor(family="Ruiz", orcid="https://orcid.org/0000-0000-0000-0001"),
            DoiAuthor(given="Nobody"),
        ),
        dates=(DoiDate(kind="issued", year=2026),),
    )


def test_a_message_that_is_not_a_work_maps_to_nothing() -> None:
    assert work_from_message({"title": "a string, not a list"}, requested_doi=DOI) == DoiWork(doi=DOI)
    assert work_from_message({"DOI": 7, "author": "x", "issued": {"date-parts": "x"}}, requested_doi=DOI) == (
        DoiWork(doi=DOI)
    )


def test_a_year_only_date_is_no_whole_date() -> None:
    assert DoiDate(kind="issued", year=2026).whole_date is None
    assert DoiDate(kind="issued", year=2026, month=2, day=30).whole_date is None
    assert DoiDate(kind="issued", year=2026, month=4, day=20).whole_date is not None


def test_a_display_name_is_given_then_family_or_the_whole_name() -> None:
    assert DoiAuthor(given="Rhea", family="Okonkwo-Hale").display_name == "Rhea Okonkwo-Hale"
    assert DoiAuthor(family="Ruiz").display_name == "Ruiz"
    assert DoiAuthor(name="Synthetic Consortium").display_name == "Synthetic Consortium"
    assert DoiAuthor(given="Nobody").display_name is None


# --------------------------------------------------------------------------------------------
# The request: polite, and once per DOI
# --------------------------------------------------------------------------------------------


async def test_the_request_names_the_platform_and_asks_for_the_polite_pool(served: Served) -> None:
    await client_over(served, email=contact_email()).lookup(DOI)

    (request,) = served.requests
    assert request.method == "GET"
    assert str(request.url).split("?", 1)[0] == WORK_URL
    assert request.url.params["mailto"] == contact_email()
    assert request.headers["user-agent"] == HttpSettings().user_agent(VERSION)
    assert "cookie" not in request.headers


async def test_without_a_contact_email_no_mailto_is_sent(served: Served) -> None:
    await client_over(served).lookup(DOI)

    (request,) = served.requests
    assert "mailto" not in request.url.params


async def test_a_doi_with_reserved_characters_is_escaped_in_the_path() -> None:
    served = Served()
    served.answer(f"{CROSSREF_WORKS_URL}10.1016/s0140-6736%2820%2930183-5%3Fx", status=404)

    await client_over(served).lookup("10.1016/s0140-6736(20)30183-5?x")

    (request,) = served.requests
    assert request.url.raw_path.decode() == "/works/10.1016/s0140-6736%2820%2930183-5%3Fx"


async def test_a_doi_is_asked_for_once_and_then_answered_from_the_cache(served: Served) -> None:
    client = client_over(served)

    first = await client.lookup(DOI)
    second = await client.lookup(DOI)

    assert first == second == EXPECTED_WORK
    assert len(served.requests) == 1


async def test_the_file_cache_outlives_the_client(served: Served, tmp_path: Path) -> None:
    """The CLI is one process per command, so the cache that makes "once" true is on disk."""
    await client_over(served, cache=FileDoiCache(tmp_path)).lookup(DOI)
    again = await client_over(served, cache=FileDoiCache(tmp_path)).lookup(DOI)

    assert again == EXPECTED_WORK
    assert len(served.requests) == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


async def test_an_unreadable_cache_file_is_treated_as_absent(served: Served, tmp_path: Path) -> None:
    cache = FileDoiCache(tmp_path)
    await client_over(served, cache=cache).lookup(DOI)
    (cached,) = tmp_path.glob("*.json")
    cached.write_text("{not json", encoding="utf-8")

    assert await client_over(served, cache=FileDoiCache(tmp_path)).lookup(DOI) == EXPECTED_WORK
    assert len(served.requests) == 2


async def test_a_cache_file_for_another_doi_is_not_this_dois_answer(tmp_path: Path) -> None:
    cache = FileDoiCache(tmp_path)
    cache.put(DOI, EXPECTED_WORK)
    (cached,) = tmp_path.glob("*.json")
    stored: dict[str, Any] = json.loads(cached.read_text(encoding="utf-8"))
    stored["requested_doi"] = "10.5555/another"
    cached.write_text(json.dumps(stored), encoding="utf-8")

    assert cache.get(DOI) is None


async def test_an_unregistered_doi_is_none_and_is_asked_again_next_time() -> None:
    served = Served()
    served.answer(WORK_URL, status=404)
    client = client_over(served)

    assert await client.lookup(DOI) is None
    assert await client.lookup(DOI) is None
    assert len(served.requests) == 2


# --------------------------------------------------------------------------------------------
# Failures are ProviderUnavailable, and never carry the contact email
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "content"),
    [
        (500, b"{}"),
        (429, b"{}"),
        (403, b"{}"),
        (200, b"<html>not json</html>"),
        (200, b'{"status": "ok", "message-type": "work-list", "message": {}}'),
        (200, b'{"status": "failed", "message-type": "work", "message": {}}'),
        (200, b'{"status": "ok", "message-type": "work", "message": []}'),
    ],
)
async def test_an_answer_that_is_not_a_work_is_provider_unavailable(status: int, content: bytes) -> None:
    served = Served()
    served.answer(WORK_URL, status=status, content=content)
    client = client_over(served, email=contact_email())

    with pytest.raises(ProviderUnavailable) as raised:
        await client.lookup(DOI)

    assert raised.value.provider == "crossref"
    assert contact_email() not in str(raised.value)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
async def test_a_transport_failure_is_provider_unavailable_with_no_chain_to_quote_the_url(
    served: Served, failure: type[httpx.TransportError]
) -> None:
    served.failure = failure
    client = client_over(served, email=contact_email())

    with pytest.raises(ProviderUnavailable) as raised:
        await client.lookup(DOI)

    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
    assert contact_email() not in str(raised.value)


async def test_a_failed_lookup_caches_nothing(served: Served) -> None:
    client = client_over(served)
    served.failure = httpx.ConnectError
    with pytest.raises(ProviderUnavailable):
        await client.lookup(DOI)
    served.failure = None

    assert await client.lookup(DOI) == EXPECTED_WORK
    assert len(served.requests) == 2


@pytest.mark.usefixtures("bare_protected_loggers")
async def test_httpx_logs_the_request_without_the_contact_email(
    served: Served, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await client_over(served, email=contact_email()).lookup(DOI)

    request_lines = [record for record in caplog.records if record.name == "httpx"]
    assert request_lines, "httpx logged no request line, so this test checked nothing"
    assert all(contact_email() not in record.getMessage() for record in caplog.records)
