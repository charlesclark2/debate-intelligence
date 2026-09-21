"""`OpenCaselistClient` against respx, offline, on a simulated clock.

Every request here is answered by respx from the synthetic fixtures in
`packages/debate_core/tests/fixtures/opencaselist/`; the workspace's `--disable-socket` would fail a
test that escaped it. The clock and the sleep are simulated (:class:`SimulatedTime`), so a test
that exercises a ten-minute backoff or a hundred downloads against the rate limit finishes at once
and can check the rule over every window instead of a sample.

What the spec's goal criteria ask for, and where:

* ac1 — listings parse into typed records: `test_lists_*`.
* ac2 — streamed, length-checked, hashed, atomically renamed, no partial left behind:
  `test_download_*`.
* ac3 — no token, password or username in any log record or exception:
  `test_no_token_or_password_reaches_a_log_or_an_exception`, and the cookie only ever goes to the
  API host: `test_the_token_cookie_goes_to_the_api_host_and_never_to_the_file_host`.
* ac4 — the rolling download window, request spacing, Retry-After-aware backoff, and 401/403
  stopping after exactly one request: `test_*window*`, `test_*spaced*`, `test_*retr*`,
  `test_*auth*`.
* ac5's settings gate, at the client: `test_the_client_refuses_*`.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import traceback
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from debate_core.application.errors import (
    ArchiveTooLarge,
    DomainError,
    NotFound,
    ProviderRateLimited,
    ProviderUnavailable,
)
from debate_core.application.ports.caselist_source import (
    ArchiveKind,
    ArchiveListing,
    ArchiveUnavailable,
    CaselistApiDisabled,
    CaselistArchiveSource,
    CaselistAuthExpired,
    CaselistLoginRejected,
    CaselistTokenMissing,
    DownloadConflict,
    DownloadIntegrityError,
    InvalidCaselistSlug,
    OpenEvFile,
    UnsafeDownloadName,
)
from debate_core.application.settings import Settings
from debate_core.integrations.opencaselist import NetworkDisallowed, OpenCaselistClient
from debate_core.integrations.opencaselist.inbox_writer import PARTIAL_DIRECTORY
from debate_core.integrations.opencaselist.pacing import DOWNLOAD_WINDOW_SECONDS
from debate_core.integrations.opencaselist.token_store import CaselistTokenStore, FileTokenBackend

from .conftest import load_fixture

API = "https://api.opencaselist.example.invalid/v1"
FILES = "https://caselist-files.example.invalid"
CASELIST = "testcl26"
ARCHIVE_BYTES = b"PK\x03\x04 synthetic weekly archive bytes " * 64


# ------------------------------------------------------------------------------------------------
# Harness
# ------------------------------------------------------------------------------------------------


class SimulatedTime:
    """A monotonic clock that only moves when the client sleeps."""

    def __init__(self) -> None:
        self.now = 10_000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def make_settings(tmp_path: Path, **caselist: Any) -> Settings:
    return Settings.model_validate(
        {
            "environment": "test",
            "allow_network": caselist.pop("allow_network", True),
            "storage": {"data_dir": tmp_path / "data"},
            "models": {"routing_file": tmp_path / "routing.yaml"},
            "caselist": {"api_enabled": True, "api_base_url": API, **caselist},
        }
    )


@pytest.fixture
def simulated() -> SimulatedTime:
    return SimulatedTime()


@pytest.fixture
def token_store(tmp_path: Path, fake_token: str) -> CaselistTokenStore:
    store = CaselistTokenStore(FileTokenBackend(tmp_path / "secrets" / "caselist_token"))
    store.save(SecretStr(fake_token), expires_at=None)
    return store


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    path = tmp_path / "inbox"
    path.mkdir()
    return path


@pytest.fixture
def api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def build_client(
    tmp_path: Path, token_store: CaselistTokenStore, simulated: SimulatedTime, **caselist: Any
) -> OpenCaselistClient:
    return OpenCaselistClient.from_settings(
        make_settings(tmp_path, **caselist),
        token_store=token_store,
        user_agent_version="0.0.0-test",
        clock=simulated.clock,
        sleep=simulated.sleep,
    )


@pytest.fixture
def client(tmp_path: Path, token_store: CaselistTokenStore, simulated: SimulatedTime) -> OpenCaselistClient:
    return build_client(tmp_path, token_store, simulated)


def run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def weekly_listing(day: int = 15) -> ArchiveListing:
    name = f"{CASELIST}-weekly-2026-09-{day:02d}.zip"
    return ArchiveListing(
        caselist=CASELIST,
        name=name,
        kind=ArchiveKind.WEEKLY,
        archive_date=date(2026, 9, day),
        url=f"{FILES}/weekly/{CASELIST}/{name}",
    )


def archive_response(body: bytes = ARCHIVE_BYTES, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(200, content=body, headers=headers)


def no_partials(inbox: Path) -> bool:
    partial = inbox / PARTIAL_DIRECTORY
    return not partial.exists() or not any(partial.iterdir())


class FailingStream(httpx.AsyncByteStream):
    """Sends some bytes, then drops the connection (or raises whatever it is given)."""

    def __init__(self, failure: BaseException) -> None:
        self.failure = failure

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield ARCHIVE_BYTES[:100]
        raise self.failure


# ------------------------------------------------------------------------------------------------
# ac1: listings
# ------------------------------------------------------------------------------------------------


def test_the_client_satisfies_the_port(client: OpenCaselistClient) -> None:
    source: CaselistArchiveSource = client
    assert source is client


def test_lists_caselists_from_the_fixture(client: OpenCaselistClient, api: respx.MockRouter) -> None:
    route = api.get(f"{API}/caselists").respond(json=load_fixture("caselists.json"))

    caselists = run(client.list_caselists())

    assert [c.slug for c in caselists] == ["testcl26", "testcl25", "testpol26"]
    assert caselists[1].archived
    assert route.calls.last.request.url.params.get("archived") is None


def test_lists_only_archived_caselists_when_asked(client: OpenCaselistClient, api: respx.MockRouter) -> None:
    route = api.get(f"{API}/caselists").respond(json=load_fixture("caselists.json")[1:2])

    run(client.list_caselists(archived=True))

    assert route.calls.last.request.url.params["archived"] == "true"


def test_gets_one_caselist_by_its_slug(client: OpenCaselistClient, api: respx.MockRouter) -> None:
    api.get(f"{API}/caselists/{CASELIST}").respond(json=load_fixture("caselist.json"))

    info = run(client.get_caselist(CASELIST))

    assert info.slug == CASELIST
    assert info.display_name == "Synthetic Test Caselist 2026-27"


def test_an_unknown_caselist_is_not_found(client: OpenCaselistClient, api: respx.MockRouter) -> None:
    api.get(f"{API}/caselists/nosuch26").respond(404, json={"message": "Caselist not found"})

    with pytest.raises(NotFound):
        run(client.get_caselist("nosuch26"))


def test_a_malformed_slug_is_refused_before_any_request(
    client: OpenCaselistClient, api: respx.MockRouter
) -> None:
    route = api.route()
    with pytest.raises(InvalidCaselistSlug):
        run(client.list_archives("../download"))
    assert route.call_count == 0


def test_lists_archives_as_typed_records_oldest_first_with_the_undated_one_last(
    client: OpenCaselistClient, api: respx.MockRouter
) -> None:
    api.get(f"{API}/caselists/{CASELIST}/downloads").respond(json=load_fixture("downloads.json"))

    archives = run(client.list_archives(CASELIST))

    assert [(a.kind, a.archive_date, a.name) for a in archives] == [
        (ArchiveKind.WEEKLY, date(2026, 9, 8), "testcl26-weekly-2026-09-08.zip"),
        (ArchiveKind.FULL, date(2026, 9, 15), "testcl26-all-2026-09-15.zip"),
        (ArchiveKind.WEEKLY, date(2026, 9, 15), "testcl26-weekly-2026-09-15.zip"),
        (ArchiveKind.UNRECOGNISED, None, "testcl26-bundle.zip"),
    ]
    assert all(a.caselist == CASELIST and a.url.startswith(FILES) for a in archives)


def test_lists_openev_files_for_a_year(client: OpenCaselistClient, api: respx.MockRouter) -> None:
    route = api.get(f"{API}/openev").respond(json=load_fixture("openev.json"))

    files = run(client.list_openev(year=2026))

    assert [(f.openev_id, f.camp, f.tags) for f in files] == [
        (7001, "SyntheticCampA", ("neg", "t")),
        (7002, "SyntheticCampB", ("k",)),
    ]
    assert route.calls.last.request.url.params["year"] == "2026"


# ------------------------------------------------------------------------------------------------
# ac2: downloads
# ------------------------------------------------------------------------------------------------


def test_download_streams_into_the_inbox_with_its_sha256_and_size(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    listing = weekly_listing()
    api.get(listing.url).mock(return_value=archive_response())

    downloaded = run(client.download_archive(listing, inbox))

    assert downloaded.path == inbox / listing.name
    assert downloaded.path.read_bytes() == ARCHIVE_BYTES
    assert downloaded.sha256 == hashlib.sha256(ARCHIVE_BYTES).hexdigest()
    assert downloaded.byte_size == len(ARCHIVE_BYTES)
    assert not downloaded.already_present
    assert no_partials(inbox)


def test_download_of_a_short_body_fails_and_leaves_nothing(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    listing = weekly_listing()
    api.get(listing.url).mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Length": str(len(ARCHIVE_BYTES) + 10)},
            stream=httpx.ByteStream(ARCHIVE_BYTES),
        )
    )

    with pytest.raises(DownloadIntegrityError, match="arrived of the"):
        run(client.download_archive(listing, inbox))

    assert not (inbox / listing.name).exists()
    assert no_partials(inbox)


def test_download_of_a_long_body_fails_and_leaves_nothing(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    listing = weekly_listing()
    api.get(listing.url).mock(
        return_value=httpx.Response(
            200, headers={"Content-Length": "10"}, stream=httpx.ByteStream(ARCHIVE_BYTES)
        )
    )

    with pytest.raises(DownloadIntegrityError, match="more than the declared"):
        run(client.download_archive(listing, inbox))

    assert list(inbox.glob("*.zip")) == []
    assert no_partials(inbox)


def test_download_without_a_content_length_is_refused(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    listing = weekly_listing()

    async def chunked() -> AsyncIterator[bytes]:
        yield ARCHIVE_BYTES

    class Chunked(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            async for chunk in chunked():
                yield chunk

    api.get(listing.url).mock(return_value=httpx.Response(200, stream=Chunked()))

    with pytest.raises(DownloadIntegrityError, match="no Content-Length"):
        run(client.download_archive(listing, inbox))
    assert list(inbox.glob("*.zip")) == []


def test_download_of_an_empty_file_is_refused(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    listing = weekly_listing()
    api.get(listing.url).mock(
        return_value=httpx.Response(200, headers={"Content-Length": "0"}, stream=httpx.ByteStream(b""))
    )

    with pytest.raises(DownloadIntegrityError, match="empty"):
        run(client.download_archive(listing, inbox))
    assert list(inbox.glob("*.zip")) == []


def test_download_larger_than_the_archive_ceiling_is_refused_before_reading(
    tmp_path: Path,
    token_store: CaselistTokenStore,
    simulated: SimulatedTime,
    api: respx.MockRouter,
    inbox: Path,
) -> None:
    small = build_client(tmp_path, token_store, simulated, max_archive_bytes=16)
    listing = weekly_listing()
    api.get(listing.url).mock(return_value=archive_response())

    with pytest.raises(ArchiveTooLarge):
        run(small.download_archive(listing, inbox))
    assert list(inbox.glob("*.zip")) == []


def test_download_interrupted_mid_stream_leaves_no_partial_file(
    tmp_path: Path,
    token_store: CaselistTokenStore,
    simulated: SimulatedTime,
    api: respx.MockRouter,
    inbox: Path,
) -> None:
    client = build_client(tmp_path, token_store, simulated, max_attempts=2)
    listing = weekly_listing()
    route = api.get(listing.url).mock(
        return_value=httpx.Response(
            200,
            headers={"Content-Length": str(len(ARCHIVE_BYTES))},
            stream=FailingStream(httpx.ReadError("connection reset")),
        )
    )

    with pytest.raises(ProviderUnavailable, match="mid-download"):
        run(client.download_archive(listing, inbox))

    assert route.call_count == 2, "a dropped connection is retried, and each attempt is a download"
    assert list(inbox.glob("*.zip")) == []
    assert no_partials(inbox)


@pytest.mark.parametrize("interruption", [KeyboardInterrupt(), asyncio.CancelledError()])
def test_download_stopped_by_the_operator_or_a_cancel_leaves_no_partial_file(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path, interruption: BaseException
) -> None:
    listing = weekly_listing()
    api.get(listing.url).mock(
        return_value=httpx.Response(
            200, headers={"Content-Length": str(len(ARCHIVE_BYTES))}, stream=FailingStream(interruption)
        )
    )

    with pytest.raises(type(interruption)):
        run(client.download_archive(listing, inbox))

    assert list(inbox.glob("*.zip")) == []
    assert no_partials(inbox)


def test_download_of_a_file_already_in_the_inbox_is_reported_not_rewritten(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    listing = weekly_listing()
    existing = inbox / listing.name
    existing.write_bytes(ARCHIVE_BYTES)
    before = existing.stat().st_ino
    api.get(listing.url).mock(return_value=archive_response())

    downloaded = run(client.download_archive(listing, inbox))

    assert downloaded.already_present
    assert existing.stat().st_ino == before
    assert no_partials(inbox)


def test_download_never_overwrites_a_different_file_of_the_same_name(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    listing = weekly_listing()
    existing = inbox / listing.name
    existing.write_bytes(b"what the operator already had")
    api.get(listing.url).mock(return_value=archive_response())

    with pytest.raises(DownloadConflict):
        run(client.download_archive(listing, inbox))

    assert existing.read_bytes() == b"what the operator already had"
    assert no_partials(inbox)


@pytest.mark.parametrize("name", ["../escape.zip", "nested/name.zip", ".hidden.zip", ""])
def test_download_under_an_unsafe_name_is_refused(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path, name: str
) -> None:
    route = api.route()
    listing = weekly_listing().model_copy(update={"name": name})

    with pytest.raises(UnsafeDownloadName):
        run(client.download_archive(listing, inbox))
    assert route.call_count == 0


def test_an_archive_the_file_host_no_longer_serves_is_unavailable_not_auth(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    listing = weekly_listing()
    route = api.get(listing.url).respond(403)

    with pytest.raises(ArchiveUnavailable):
        run(client.download_archive(listing, inbox))
    assert route.call_count == 1


def test_openev_download_goes_through_the_api_with_the_path_as_a_query(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path, fake_token: str
) -> None:
    file = OpenEvFile(openev_id=7001, path="/openev/2026/SyntheticCampA/ZZ/Synthetic-Topicality.docx")
    route = api.get(f"{API}/download").mock(return_value=archive_response(b"synthetic docx"))

    downloaded = run(client.download_openev(file, inbox))

    request = route.calls.last.request
    assert request.url.params["path"] == "openev/2026/SyntheticCampA/ZZ/Synthetic-Topicality.docx"
    assert request.headers["Cookie"] == f"caselist_token={fake_token}"
    assert downloaded.path.name == "openev-7001-Synthetic-Topicality.docx"
    assert downloaded.source_name == "openev-7001"


def test_an_openev_path_that_climbs_is_refused_before_any_request(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    route = api.route()
    with pytest.raises(UnsafeDownloadName):
        run(client.download_openev(OpenEvFile(openev_id=7003, path="/openev/../../etc/passwd"), inbox))
    assert route.call_count == 0


# ------------------------------------------------------------------------------------------------
# ac3: the token, the password and paths never leak
# ------------------------------------------------------------------------------------------------


def test_the_token_cookie_goes_to_the_api_host_and_never_to_the_file_host(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path, fake_token: str
) -> None:
    listing = weekly_listing()
    listed = api.get(f"{API}/caselists/{CASELIST}/downloads").respond(json=load_fixture("downloads.json"))
    fetched = api.get(listing.url).mock(
        return_value=archive_response(headers={"Set-Cookie": "caselist_token=from-elsewhere"})
    )

    run(client.list_archives(CASELIST))
    run(client.download_archive(listing, inbox))

    assert listed.calls.last.request.headers["Cookie"] == f"caselist_token={fake_token}"
    assert "Cookie" not in fetched.calls.last.request.headers
    assert fetched.calls.last.request.headers["User-Agent"].startswith("debate-research/0.0.0-test (+")


def test_no_token_or_password_reaches_a_log_or_an_exception(
    tmp_path: Path,
    simulated: SimulatedTime,
    api: respx.MockRouter,
    inbox: Path,
    fake_token: str,
    fake_password: str,
    fake_username: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Login, list, download and a 401, with every record at DEBUG and every exception rendered."""
    store = CaselistTokenStore(FileTokenBackend(tmp_path / "secrets" / "caselist_token"))
    client = build_client(tmp_path, store, simulated)
    openev_path = load_fixture("openev.json")[0]["path"]
    listing = weekly_listing()
    api.post(f"{API}/login").respond(
        201,
        json={
            "message": "Successfully logged in",
            "token": fake_token,
            "expires": "2026-10-04T00:00:00.000Z",
        },
        headers={"Set-Cookie": f"caselist_token={fake_token}; Path=/"},
    )
    api.get(f"{API}/caselists").respond(json=load_fixture("caselists.json"))
    api.get(f"{API}/caselists/{CASELIST}/downloads").respond(json=load_fixture("downloads.json"))
    api.get(f"{API}/openev").respond(json=load_fixture("openev.json"))
    api.get(listing.url).mock(return_value=archive_response())
    api.get(f"{API}/download").mock(return_value=archive_response(b"synthetic docx"))
    api.get(f"{API}/caselists/{CASELIST}").respond(401, json={"message": "Not logged in"})

    rendered: list[str] = []

    def render(exception: BaseException) -> None:
        rendered.extend(
            [
                str(exception),
                repr(exception),
                "".join(traceback.format_exception(exception)),
                str(vars(exception)),
            ]
        )

    with caplog.at_level(logging.DEBUG):
        issued = run(client.login(fake_username, SecretStr(fake_password)))
        store.save(issued.token, expires_at=issued.expires_at)
        rendered.append(repr(issued))
        run(client.list_caselists())
        run(client.list_archives(CASELIST))
        files = run(client.list_openev())
        run(client.download_archive(listing, inbox))
        run(client.download_openev(files[0], inbox))
        with pytest.raises(CaselistAuthExpired) as expired:
            run(client.get_caselist(CASELIST))
        render(expired.value)

    api.post(f"{API}/login").respond(401, json={"message": "Invalid username or password"})
    with pytest.raises(CaselistLoginRejected) as rejected:
        run(client.login(fake_username, SecretStr(fake_password)))
    render(rejected.value)

    logged = "\n".join(
        [caplog.text]
        + [record.getMessage() for record in caplog.records]
        + [str(record.__dict__) for record in caplog.records]
    )
    assert any(record.name == "httpx" for record in caplog.records), "httpx's own request lines were captured"
    everything = logged + "\n".join(rendered)
    for secret in (fake_token, fake_password, fake_username):
        assert secret not in everything
    assert openev_path.lstrip("/") not in logged, (
        "the OpenEv file's path is scrubbed from httpx's request line"
    )
    assert "Synthetic-Topicality" not in logged
    assert "caselist_token=" not in logged.replace("caselist_token=[REDACTED]", "")


def test_login_stores_nothing_itself_and_the_token_file_holds_no_password(
    tmp_path: Path, simulated: SimulatedTime, api: respx.MockRouter, fake_token: str, fake_password: str
) -> None:
    store = CaselistTokenStore(FileTokenBackend(tmp_path / "secrets" / "caselist_token"))
    client = build_client(tmp_path, store, simulated)
    api.post(f"{API}/login").respond(201, json={"token": fake_token, "expires": "2026-10-04T00:00:00.000Z"})

    issued = run(client.login("someone@example.invalid", SecretStr(fake_password)))

    assert store.load() is None, "the client returns the token; storing it is the caller's decision"
    store.save(issued.token, expires_at=issued.expires_at)
    stored_text = (tmp_path / "secrets" / "caselist_token").read_text(encoding="utf-8")
    assert fake_password not in stored_text
    assert issued.expires_at is not None and issued.expires_at.year == 2026


def test_a_successful_authenticated_request_stamps_the_token_as_validated(
    client: OpenCaselistClient, api: respx.MockRouter, token_store: CaselistTokenStore
) -> None:
    before = token_store.load()
    api.get(f"{API}/caselists").respond(json=[])

    run(client.list_caselists())

    after = token_store.load()
    assert before is not None and after is not None
    assert after.last_validated_at is not None
    assert before.last_validated_at is not None and after.last_validated_at >= before.last_validated_at


def test_no_stored_token_is_a_clear_error_and_no_request(
    tmp_path: Path, simulated: SimulatedTime, api: respx.MockRouter
) -> None:
    empty = CaselistTokenStore(FileTokenBackend(tmp_path / "nothing-here"))
    client = build_client(tmp_path, empty, simulated)
    route = api.route()

    with pytest.raises(CaselistTokenMissing):
        run(client.list_caselists())
    assert route.call_count == 0


# ------------------------------------------------------------------------------------------------
# ac4: pacing, the download window, backoff, and 401/403
# ------------------------------------------------------------------------------------------------


def download_starts_within_any_window(starts: list[float]) -> int:
    """The most downloads that started inside any rolling 60-second window."""
    starts = sorted(starts)
    return max(
        sum(1 for other in starts if start <= other < start + DOWNLOAD_WINDOW_SECONDS) for start in starts
    )


def record_starts(
    simulated: SimulatedTime, starts: list[float], respond: Callable[[], httpx.Response]
) -> Callable[[httpx.Request], httpx.Response]:
    """A respx side effect that notes the simulated time each request started at."""

    def answer(request: httpx.Request) -> httpx.Response:
        starts.append(simulated.now)
        return respond()

    return answer


@pytest.mark.parametrize(("configured", "expected_limit"), [(None, 8), (10, 10), (3, 3)])
def test_file_downloads_never_exceed_the_limit_in_any_rolling_window(
    tmp_path: Path,
    token_store: CaselistTokenStore,
    simulated: SimulatedTime,
    api: respx.MockRouter,
    inbox: Path,
    configured: int | None,
    expected_limit: int,
) -> None:
    """Archives and OpenEv files together, against one window."""
    settings = {} if configured is None else {"downloads_per_minute": configured}
    client = build_client(tmp_path, token_store, simulated, min_request_interval_seconds=0.5, **settings)
    starts: list[float] = []
    api.get(url__startswith=f"{FILES}/weekly/").mock(
        side_effect=record_starts(simulated, starts, archive_response)
    )
    api.get(f"{API}/download").mock(
        side_effect=record_starts(simulated, starts, lambda: archive_response(b"docx"))
    )

    async def pull_many() -> None:
        for day in range(1, 21):
            listing = weekly_listing(day)
            await client.download_archive(listing, inbox)
            await client.download_openev(
                OpenEvFile(openev_id=day, path=f"/openev/2026/C/L/f{day}.docx"), inbox
            )

    run(pull_many())

    assert len(starts) == 40
    assert download_starts_within_any_window(starts) == expected_limit
    assert client.transport.pacer.download_starts  # the window was in use


def test_more_than_ten_downloads_a_minute_fails_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="maintainer's limit is 10"):
        make_settings(tmp_path, downloads_per_minute=11)


def test_consecutive_requests_are_spaced_by_at_least_the_interval(
    tmp_path: Path, token_store: CaselistTokenStore, simulated: SimulatedTime, api: respx.MockRouter
) -> None:
    client = build_client(tmp_path, token_store, simulated, min_request_interval_seconds=2.5)
    starts: list[float] = []
    api.get(f"{API}/caselists").mock(
        side_effect=record_starts(simulated, starts, lambda: httpx.Response(200, json=[]))
    )

    async def five() -> None:
        for _ in range(5):
            await client.list_caselists()

    run(five())

    gaps = [later - earlier for earlier, later in zip(starts, starts[1:], strict=False)]
    assert len(gaps) == 4
    assert all(gap >= 2.5 for gap in gaps)


def test_downloads_run_one_at_a_time_even_when_asked_concurrently(
    tmp_path: Path,
    token_store: CaselistTokenStore,
    simulated: SimulatedTime,
    api: respx.MockRouter,
    inbox: Path,
) -> None:
    client = build_client(tmp_path, token_store, simulated)
    in_flight = 0
    most = 0

    async def slow_archive(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, most
        in_flight += 1
        most = max(most, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return archive_response()

    api.get(url__startswith=f"{FILES}/weekly/").mock(side_effect=slow_archive)

    async def together() -> None:
        await asyncio.gather(*(client.download_archive(weekly_listing(day), inbox) for day in range(1, 6)))

    run(together())
    assert most == 1


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_a_transient_status_is_retried_with_backoff_and_then_succeeds(
    client: OpenCaselistClient, api: respx.MockRouter, simulated: SimulatedTime, status: int
) -> None:
    route = api.get(f"{API}/caselists").mock(
        side_effect=[httpx.Response(status), httpx.Response(status), httpx.Response(200, json=[])]
    )

    assert run(client.list_caselists()) == []

    assert route.call_count == 3
    assert [s for s in simulated.sleeps if s >= 2.0] == [2.0, 4.0], "doubling from backoff_base_seconds"


def test_retry_after_is_honoured_in_seconds(
    client: OpenCaselistClient, api: respx.MockRouter, simulated: SimulatedTime
) -> None:
    route = api.get(f"{API}/caselists").mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "37"}), httpx.Response(200, json=[])]
    )

    run(client.list_caselists())

    assert route.call_count == 2
    assert 37.0 in simulated.sleeps


def test_retry_after_as_an_http_date_is_honoured(
    client: OpenCaselistClient, api: respx.MockRouter, simulated: SimulatedTime
) -> None:
    from datetime import UTC, datetime, timedelta
    from email.utils import format_datetime

    when = format_datetime(datetime.now(UTC) + timedelta(seconds=120), usegmt=True)
    api.get(f"{API}/caselists").mock(
        side_effect=[httpx.Response(503, headers={"Retry-After": when}), httpx.Response(200, json=[])]
    )

    run(client.list_caselists())

    assert any(100 <= s <= 121 for s in simulated.sleeps)


def test_a_retry_after_longer_than_the_ceiling_fails_at_once_instead_of_sleeping(
    client: OpenCaselistClient, api: respx.MockRouter, simulated: SimulatedTime, inbox: Path
) -> None:
    """The server's 5-bulk-downloads-a-day limit answers with a day-long Retry-After."""
    listing = weekly_listing()
    route = api.get(listing.url).respond(429, headers={"Retry-After": "86400"})

    with pytest.raises(ProviderRateLimited) as limited:
        run(client.download_archive(listing, inbox))

    assert route.call_count == 1
    assert limited.value.retry_after_seconds == 86400
    assert all(s < 86400 for s in simulated.sleeps)


def test_retries_stop_at_the_attempt_limit(
    tmp_path: Path, token_store: CaselistTokenStore, simulated: SimulatedTime, api: respx.MockRouter
) -> None:
    client = build_client(tmp_path, token_store, simulated, max_attempts=3)
    route = api.get(f"{API}/caselists").respond(503)

    with pytest.raises(ProviderUnavailable, match="after 3 attempts"):
        run(client.list_caselists())
    assert route.call_count == 3


def test_a_rate_limit_that_never_lifts_is_reported_as_rate_limited(
    tmp_path: Path, token_store: CaselistTokenStore, simulated: SimulatedTime, api: respx.MockRouter
) -> None:
    client = build_client(tmp_path, token_store, simulated, max_attempts=2)
    route = api.get(f"{API}/caselists").respond(429, headers={"Retry-After": "5"})

    with pytest.raises(ProviderRateLimited):
        run(client.list_caselists())
    assert route.call_count == 2


def test_a_connection_failure_is_retried_and_reported_without_the_url(
    tmp_path: Path, token_store: CaselistTokenStore, simulated: SimulatedTime, api: respx.MockRouter
) -> None:
    client = build_client(tmp_path, token_store, simulated, max_attempts=2)
    route = api.get(f"{API}/openev").mock(side_effect=httpx.ConnectError("could not reach host"))

    with pytest.raises(ProviderUnavailable) as failed:
        run(client.list_openev())

    assert route.call_count == 2
    assert "example.invalid" not in str(failed.value)
    assert failed.value.__cause__ is None and failed.value.__suppress_context__


@pytest.mark.parametrize("status", [401, 403])
def test_auth_refusal_raises_caselist_auth_expired_after_exactly_one_request(
    client: OpenCaselistClient, api: respx.MockRouter, simulated: SimulatedTime, status: int
) -> None:
    route = api.get(f"{API}/caselists/{CASELIST}/downloads").respond(status)

    with pytest.raises(CaselistAuthExpired) as expired:
        run(client.list_archives(CASELIST))

    assert route.call_count == 1
    assert expired.value.status_code == status
    assert simulated.sleeps == []


def test_auth_refusal_on_an_openev_download_is_never_retried(
    client: OpenCaselistClient, api: respx.MockRouter, inbox: Path
) -> None:
    route = api.get(f"{API}/download").respond(401)

    with pytest.raises(CaselistAuthExpired):
        run(client.download_openev(OpenEvFile(openev_id=7001, path="/openev/2026/C/L/f.docx"), inbox))
    assert route.call_count == 1


def test_a_redirect_is_never_followed(client: OpenCaselistClient, api: respx.MockRouter) -> None:
    api.get(f"{API}/caselists").respond(302, headers={"Location": "https://elsewhere.example.invalid/"})
    elsewhere = api.get("https://elsewhere.example.invalid/")

    with pytest.raises(DomainError, match="redirect"):
        run(client.list_caselists())
    assert elsewhere.call_count == 0


# ------------------------------------------------------------------------------------------------
# ac5: the settings gate, at the client
# ------------------------------------------------------------------------------------------------


def test_the_client_refuses_to_build_unless_the_api_is_enabled(
    tmp_path: Path, token_store: CaselistTokenStore, simulated: SimulatedTime, api: respx.MockRouter
) -> None:
    route = api.route()
    with pytest.raises(CaselistApiDisabled):
        build_client(tmp_path, token_store, simulated, api_enabled=False)
    assert route.call_count == 0


def test_the_api_is_disabled_by_default() -> None:
    from debate_core.application.settings import CaselistSettings

    assert CaselistSettings().api_enabled is False
    assert CaselistSettings().downloads_per_minute == 8


def test_the_client_refuses_to_build_where_the_network_is_forbidden(
    tmp_path: Path, token_store: CaselistTokenStore, simulated: SimulatedTime
) -> None:
    with pytest.raises(NetworkDisallowed):
        build_client(tmp_path, token_store, simulated, allow_network=False)


def test_the_api_base_url_must_be_https(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="https"):
        make_settings(tmp_path, api_base_url="http://api.opencaselist.example.invalid/v1")
