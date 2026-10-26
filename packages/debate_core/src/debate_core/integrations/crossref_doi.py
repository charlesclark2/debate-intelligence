"""Crossref DOI lookups for cites (v1-e06-t01).

:class:`CrossrefDoiClient` is the :class:`~debate_core.application.ports.doi_metadata.DoiMetadataSource`
adapter: one `GET https://api.crossref.org/works/{doi}` per DOI, mapped to a
:class:`~debate_core.application.ports.doi_metadata.DoiWork`. It looks works up by DOI and does
nothing else: searching Crossref is discovery's (`v1-e07-t03`).

**Once per DOI.** An answer is kept in a :class:`DoiCache` by the DOI asked for, and the next lookup
of that DOI is answered from it without a request. :class:`FileDoiCache` keeps one JSON file per DOI
under `<storage.data_dir>/crossref/`, named by the SHA-256 of the DOI, because the CLI is one process
per command and a cache in memory would almost never be asked twice. A cache file that cannot be
read, or that was written for another DOI, is treated as absent. A DOI Crossref does not hold (`404`)
and a failed lookup are not kept, so either is asked for again next time.

**Politely.** The client identifies the platform with the article fetcher's User-Agent, keeps no
cookies, reads nothing from the environment and follows no redirect, with the HTTP settings'
timeouts. When `providers.contact_email` is set it is sent as `mailto=`, which is how Crossref
admits a caller to its polite pool. That address is a person's (§14): the client registers it with
:func:`~debate_core.integrations.discovery.redaction.protect_logs`, so httpx's request log line
carries it masked, and no error this module raises quotes a URL or chains an exception that does.

**Failures** are :class:`~debate_core.application.errors.ProviderUnavailable`: a timeout, a
transport failure, any status but `200` and `404`, a body that is not JSON, and an answer that is
not Crossref's `ok` envelope around one `work`. The caller (the citation service) catches it and
cites from the page.

**Mapping** keeps what the deposit says: the first title and container title, with Crossref's
inline face markup (`<i>`, `<sub>` and the like) taken out and whitespace runs made one space; each
author's given and family names, or a name given whole, with their affiliations and ORCID iD; and
the dates `published`, `published-online`, `published-print` and `issued`, in that order, each to
the precision deposited. Anything in a shape this module does not read is left out rather than
failing the lookup.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Mapping
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path
from typing import Any, Final, Protocol, cast
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from debate_core.application.errors import ProviderUnavailable
from debate_core.application.ports.doi_metadata import DoiAuthor, DoiDate, DoiWork
from debate_core.application.settings import HttpSettings, ProviderSettings
from debate_core.integrations.discovery.redaction import protect_logs

__all__ = [
    "CROSSREF_CACHE_DIRECTORY",
    "CROSSREF_WORKS_URL",
    "PROVIDER_NAME",
    "CrossrefDoiClient",
    "DoiCache",
    "FileDoiCache",
    "InMemoryDoiCache",
    "crossref_doi_client",
    "work_from_message",
]

PROVIDER_NAME: Final = "crossref"
"""The provider name every failure carries."""

CROSSREF_WORKS_URL: Final = "https://api.crossref.org/works/"
"""The works endpoint; the DOI follows, escaped."""

CROSSREF_CACHE_DIRECTORY: Final = "crossref"
"""The directory inside `storage.data_dir` the composition root gives :class:`FileDoiCache`."""

_DATE_KINDS: Final = ("published", "published-online", "published-print", "issued")
_FACE_MARKUP: Final = re.compile(r"</?(?:i|b|em|strong|sub|sup|scp|u|sc)>", re.IGNORECASE)


# --------------------------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------------------------


class DoiCache(Protocol):
    """Where the client keeps each DOI's work."""

    def get(self, doi: str) -> DoiWork | None:
        """The work kept for `doi`, or `None`."""
        ...

    def put(self, doi: str, work: DoiWork) -> None:
        """Keep `work` as the answer for `doi`, replacing any earlier one."""
        ...


class InMemoryDoiCache:
    """A :class:`DoiCache` that lasts as long as the object."""

    def __init__(self) -> None:
        self._works: dict[str, DoiWork] = {}

    def get(self, doi: str) -> DoiWork | None:
        return self._works.get(doi)

    def put(self, doi: str, work: DoiWork) -> None:
        self._works[doi] = work


class _CachedWork(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_doi: str = Field(description="The DOI this answer was asked for.")
    work: DoiWork = Field(description="What Crossref answered.")


class FileDoiCache:
    """A :class:`DoiCache` of JSON files in one directory, created on first write."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @property
    def directory(self) -> Path:
        return self._directory

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self._directory)!r})"

    def get(self, doi: str) -> DoiWork | None:
        path = self._directory / _cache_file_name(doi)
        try:
            cached = _CachedWork.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValidationError):
            return None
        return cached.work if cached.requested_doi == doi else None

    def put(self, doi: str, work: DoiWork) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / _cache_file_name(doi)
        handle, temporary = tempfile.mkstemp(dir=self._directory, prefix=".", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(_CachedWork(requested_doi=doi, work=work).model_dump_json())
            Path(temporary).replace(path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


def _cache_file_name(doi: str) -> str:
    return hashlib.sha256(doi.encode("utf-8")).hexdigest() + ".json"


# --------------------------------------------------------------------------------------------
# Mapping a work
# --------------------------------------------------------------------------------------------


def work_from_message(message: Mapping[str, Any], *, requested_doi: str) -> DoiWork:
    """A Crossref work `message` as a :class:`DoiWork`; see the module docstring for what is kept."""
    doi = _text(message.get("DOI"))
    return DoiWork(
        doi=doi.lower() if doi is not None else requested_doi,
        title=_first_text(message.get("title")),
        container_title=_first_text(message.get("container-title")),
        authors=tuple(
            author for item in _list(message.get("author")) if (author := _author(item)) is not None
        ),
        dates=tuple(found for kind in _DATE_KINDS if (found := _date(kind, message.get(kind))) is not None),
    )


def _author(value: object) -> DoiAuthor | None:
    author = _mapping(value)
    if author is None:
        return None
    given, family, name = _text(author.get("given")), _text(author.get("family")), _text(author.get("name"))
    if given is None and family is None and name is None:
        return None
    affiliations = (
        _text(entry.get("name")) for item in _list(author.get("affiliation")) if (entry := _mapping(item))
    )
    return DoiAuthor(
        given=given,
        family=family,
        name=name,
        affiliations=tuple(affiliation for affiliation in affiliations if affiliation is not None),
        orcid=_text(author.get("ORCID")),
    )


def _date(kind: str, value: object) -> DoiDate | None:
    stated = _mapping(value)
    rows = _list(stated.get("date-parts")) if stated is not None else []
    parts = _list(rows[0]) if rows else []
    if not parts or not all(isinstance(part, int) and not isinstance(part, bool) for part in parts):
        return None
    numbers = cast(list[int], parts)
    try:
        return DoiDate(
            kind=kind,
            year=numbers[0],
            month=numbers[1] if len(numbers) > 1 else None,
            day=numbers[2] if len(numbers) > 2 else None,
        )
    except ValidationError:
        return None


def _first_text(value: object) -> str | None:
    return next((text for item in _list(value) if (text := _text(item)) is not None), None)


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return " ".join(_FACE_MARKUP.sub("", value).split()) or None


def _mapping(value: object) -> Mapping[str, Any] | None:
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else None


def _list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


# --------------------------------------------------------------------------------------------
# The client
# --------------------------------------------------------------------------------------------


class CrossrefDoiClient:
    """Looks DOIs up in Crossref, each once: the DOI metadata port's adapter.

    Owns `client`; close it with :meth:`aclose`.
    """

    def __init__(
        self, client: httpx.AsyncClient, *, contact_email: SecretStr | None, cache: DoiCache
    ) -> None:
        self._client = client
        email = contact_email.get_secret_value().strip() if contact_email is not None else ""
        self._contact_email = email or None
        """The address, or `None` when none is set: an empty `DEBATE_PROVIDERS__CONTACT_EMAIL=` is none."""
        self._cache = cache
        if self._contact_email is not None:
            protect_logs((self._contact_email,))

    def __repr__(self) -> str:
        contact = "configured" if self._contact_email is not None else "none"
        return f"{type(self).__name__}(contact_email={contact}, cache={self._cache!r})"

    async def aclose(self) -> None:
        """Close the HTTP client and its connections."""
        await self._client.aclose()

    async def lookup(self, doi: str) -> DoiWork | None:
        cached = self._cache.get(doi)
        if cached is not None:
            return cached
        parameters = {"mailto": self._contact_email} if self._contact_email is not None else {}
        try:
            response = await self._client.get(CROSSREF_WORKS_URL + quote(doi, safe="/"), params=parameters)
        except httpx.TimeoutException:
            raise ProviderUnavailable(PROVIDER_NAME, "timed out") from None
        except httpx.HTTPError as error:
            raise ProviderUnavailable(PROVIDER_NAME, f"transport failure: {type(error).__name__}") from None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ProviderUnavailable(PROVIDER_NAME, f"answered HTTP {response.status_code}")
        work = work_from_message(self._message(response), requested_doi=doi)
        self._cache.put(doi, work)
        return work

    def _message(self, response: httpx.Response) -> Mapping[str, Any]:
        try:
            document: object = response.json()
        except ValueError:
            raise ProviderUnavailable(PROVIDER_NAME, "unreadable response: not JSON") from None
        envelope = _mapping(document)
        message = _mapping(envelope.get("message")) if envelope is not None else None
        if envelope is None or envelope.get("status") != "ok" or envelope.get("message-type") != "work":
            raise ProviderUnavailable(PROVIDER_NAME, "unreadable response: not one work")
        if message is None:
            raise ProviderUnavailable(PROVIDER_NAME, "unreadable response: the work is not an object")
        return message


def crossref_doi_client(
    http: HttpSettings,
    providers: ProviderSettings,
    *,
    version: str,
    cache: DoiCache,
    transport: httpx.AsyncBaseTransport | None = None,
) -> CrossrefDoiClient:
    """The client the composition root builds: the HTTP settings' identity and timeouts, no cookies.

    `cache` is a :class:`FileDoiCache` over `<storage.data_dir>/crossref/` in the CLI. `transport` is
    for tests, which pass a mock.
    """
    client = httpx.AsyncClient(
        headers={"User-Agent": http.user_agent(version)},
        timeout=httpx.Timeout(http.request_timeout_seconds, connect=http.connect_timeout_seconds),
        follow_redirects=False,
        cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
        trust_env=False,
        transport=transport,
    )
    return CrossrefDoiClient(client, contact_email=providers.contact_email, cache=cache)
