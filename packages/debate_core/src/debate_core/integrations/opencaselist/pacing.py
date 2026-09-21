"""How fast the client may ask: a minimum gap between requests, and the maintainer's download limit.

Two rules, both from `docs/policies/caselist-data-use.md` and both enforced here rather than hoped
for:

* **A minimum interval between the start of any two requests** (E34 gate 4), configurable as
  `caselist.min_request_interval_seconds`.
* **At most `downloads_per_minute` file downloads in any rolling 60 seconds** (clause 12: the
  maintainer's limit is 10, the default is 8, and settings refuse anything above 10). Archive and
  OpenEv downloads share this one window, and so does every retry of a download: each attempt is a
  download as far as the server is concerned.

"Rolling" means exactly that: a download may start at time `t` only if fewer than the limit started
in `(t - 60, t]`. A fixed per-minute bucket would allow twice the limit across a bucket boundary.

The clock and the sleep are injected, so the tests run a simulated hour in microseconds and check
the rule over every window rather than trusting a sample.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from typing import Final

__all__ = ["DOWNLOAD_WINDOW_SECONDS", "RequestPacer"]

DOWNLOAD_WINDOW_SECONDS: Final = 60.0
"""The length of the rolling window the download limit is counted over."""

type Clock = Callable[[], float]
"""Monotonic seconds."""

type Sleep = Callable[[float], Awaitable[None]]


class RequestPacer:
    """Grants request slots no faster than the interval and the download window allow.

    Not thread-safe and not meant to be: the transport holds one lock around every request, so one
    request is in flight at a time and slots are taken strictly in order.
    """

    def __init__(
        self,
        *,
        min_interval_seconds: float,
        downloads_per_minute: int,
        clock: Clock,
        sleep: Sleep,
    ) -> None:
        if downloads_per_minute < 1:
            raise ValueError("downloads_per_minute must be at least 1")
        self._interval = min_interval_seconds
        self._download_limit = downloads_per_minute
        self._clock = clock
        self._sleep = sleep
        self._last_start: float | None = None
        self._download_starts: deque[float] = deque()

    @property
    def download_starts(self) -> tuple[float, ...]:
        """When each download still inside the window started. For tests and diagnostics."""
        return tuple(self._download_starts)

    async def slot(self, *, download: bool) -> None:
        """Wait until a request (a download, if `download`) may start, then record that it has."""
        while True:
            now = self._clock()
            wait = 0.0
            if self._last_start is not None:
                wait = max(wait, self._last_start + self._interval - now)
            if download:
                self._forget_downloads_before(now)
                if len(self._download_starts) >= self._download_limit:
                    wait = max(wait, self._download_starts[0] + DOWNLOAD_WINDOW_SECONDS - now)
            if wait <= 0:
                break
            await self._sleep(wait)
        now = self._clock()
        self._last_start = now
        if download:
            self._download_starts.append(now)

    def _forget_downloads_before(self, now: float) -> None:
        while self._download_starts and self._download_starts[0] <= now - DOWNLOAD_WINDOW_SECONDS:
            self._download_starts.popleft()
