# Session report: v1-e04-t02-http-fetcher

| | |
|---|---|
| Task | `v1-e04-t02-http-fetcher` — Polite HTTP fetcher |
| Spec | [`plan_specs/v1/e04-article-retrieval/t02-http-fetcher.yaml`](../../plan_specs/v1/e04-article-retrieval/t02-http-fetcher.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t02-http-fetcher` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`HttpArticleFetcher` (`debate_core.integrations.http_fetcher`) implements the `ArticleFetcher` port
and always returns a `FetchResult`; a refusal or failure is a typed `FetchError` value on it, never
an httpx exception. Every request and every redirect hop passes four gates in order: a public
address, robots.txt for the hop's origin (read through the same client, cached per origin), the
per-host minimum interval, and bounded retries (connect failures, 429, 502, 503, 504; `Retry-After`
honoured on 429 and 503). Bodies are streamed and abandoned at `http.max_response_bytes`. The URL is
fetched as given, never its canonical form. All five Goal criteria and every node criterion pass.
**Waiting on the PM:** the packaging proposal (an `http` extra for httpx, and the import-linter
entries) is sent as a relay prompt and not applied; no `pyproject.toml` is touched yet, so the Goal
stays `InProgress` until it is ruled on and done. Look first at the robots.txt reading
(`retrieval/robots_rules.py`), which deliberately refuses more than `urllib.robotparser` alone.

Commits are relative to `dev` at `1b999dc` (v1-e07-t01, #380), synced with `scripts/task sync`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `fetch-types` | Done | `FetchResult` moved from the port to `retrieval/fetch_types.py`, re-exported by the port; eight error types |
| `http-client` | Done | `integrations/http_fetcher.py`; new limits in `HttpSettings` |
| `retry-policy` | Done | Retry-After read with v1-e07-t01's `retry_after_seconds` (imported, not copied) |
| `robots-and-rate-limit` | Done | `retrieval/robots_rules.py` (stdlib plus an RFC 9309 check), `HostRateLimiter` |
| `test-suite` | Done | 101 fetcher tests, 56 retrieval unit tests; pyright and lint-imports clean |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: implements ArticleFetcher, FetchResult with final URL, status, headers, content type, bytes, byte length, elapsed, fetched_at | PASS | `test_the_fetcher_implements_the_article_fetcher_port`, `test_a_page_comes_back_with_its_bytes_and_everything_about_the_response` (elapsed 500.0 ms and `fetched_at` asserted exactly on the simulated clock) |
| ac2: timeouts, max size, max redirects from settings; exceeding any is a typed FetchError | PASS | `uv run pytest …/test_http_fetcher.py -k limits` → `30 passed` |
| ac3: only connect errors, 429, 502/503/504 retried, bounded exponential backoff honouring Retry-After; other 4xx never | PASS | `uv run pytest …/test_http_fetcher.py -k retry` → `30 passed` (11 non-retried statuses parametrized, 400 to 505) |
| ac4: disallowed path refused with ROBOTS_DISALLOWED, no request to the target; robots.txt cached per host | PASS | `test_robots_a_disallowed_path_is_refused_and_never_requested` asserts the target route was never called and the only request was robots.txt; `test_robots_is_read_once_per_origin_and_cached` asserts one robots request per origin over four fetches |
| ac5: per-host minimum interval from settings; identifying User-Agent with contact URL on every request | PASS | `uv run pytest …/test_http_fetcher.py -k "robots or rate"` → `30 passed`; request start times asserted as `[0.0, 2.5, 5.0]` s |
| Node `fetch-types`: `fetch_types.py` exists containing `class FetchResult` | PASS | `grep -c "class FetchResult" packages/debate_core/src/debate_core/retrieval/fetch_types.py` → `1` |
| Node `http-client`: `uv run pytest packages/debate_core/tests/integrations/test_http_fetcher.py -k limits` | PASS | `30 passed in 2.17s` |
| Node `retry-policy`: `… -k retry` | PASS | `30 passed in 2.03s` |
| Node `robots-and-rate-limit`: `… -k "robots or rate"` | PASS | `30 passed in 2.13s` |
| Node `test-suite`: `uv run pytest packages/debate_core/tests/integrations/test_http_fetcher.py` | PASS | `101 passed in 1.97s` |
| Node `test-suite`: `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations` |
| Node `test-suite`: `uv run lint-imports` | PASS | `Contracts: 12 kept, 0 broken.` |

The three `-k` filters each select 30 tests; I checked that with `--co` because the equal counts
looked like a mistake. They are not.

## Checks run before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 305 of 369 test files: `settings.py` and `ports/providers.py` are imported by the root `conftest.py`'s fake router. Over two minutes, so not run here; it is the pull request's `ci` run (agreement 10) |
| `.venv/bin/python -m pytest -q` over `application/test_settings.py`, `test_fakes.py`, `test_port_conformance.py`, `tests/retrieval`, `test_http_fetcher.py`, `tests/architecture`, `tests/specs`, the CLI's `test_app.py`, `test_help_rendering.py`, `test_config_command.py` | `1005 passed in 16.56s` |
| `.venv/bin/python -m pytest -q -n 0 -p no:randomly` over `integrations/opencaselist`, `integrations/discovery`, then `test_http_fetcher.py` (PM's ordering check) | `367 passed` |
| `uv run ruff format --check .` / `uv run ruff check .` | `1027 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_core` | `0 errors` |
| `uv run lint-imports` | `12 kept, 0 broken` |
| `uv run scripts/validate_specs.py` | `OK: 396 files, 39 epics, 336 tasks, 21 releases` |

Two wider runs were stopped by the 115-second limit, not by a failure: the changed packages' whole
test directories (`application`, `retrieval`, `integrations` and the always-run list), and then
`packages/debate_core/tests/application` alone. The machine's load average was about 24 on 11 cores
from another checkout's pytest run at the time. Neither is quoted as a result.

### Mutation run

23 mutants on the retry rule, the backoff bound, Retry-After, the robots refusal and the size limit
(a script in the session scratchpad; each mutant applied, run against `test_http_fetcher.py` and
`test_robots_rules.py` with `-x -n 0 -p no:randomly`, then restored with `git checkout`). No
Hypothesis property is involved, so agreement 8 does not apply.

| Mutant | Result |
|---|---|
| 429 not retryable; 504 not retryable; 500 retryable | killed |
| one retry too many; one too few; a failed connection not retried | killed |
| backoff with no cap; exponent off by one; full jitter instead of the upper half | killed |
| Retry-After honoured on 502 too; ignored on 503; never honoured | killed |
| Retry-After ceiling inclusive; no ceiling | killed |
| robots refusal ignored; no RFC 9309 layer; unreachable robots.txt allows; 401/403 allows; robots.txt not cached | killed |
| RFC 9309 tie between equal-length Allow and Disallow goes to Disallow | **survived**, then killed by the new `test_an_allow_and_a_disallow_of_equal_length_resolve_to_allow` |
| size limit inclusive; declared `Content-Length` ignored; stream read far past the limit | killed |

The log-leak test was also shown red twice: before the log filter existed (httpx's own
`HTTP Request: GET <full URL>` line), and with the filter disarmed (`if _SENDING.get()` → `if False`).

## Files changed

* `packages/debate_core/src/debate_core/retrieval/`: `fetch_types.py` (FetchResult and the
  FetchError types), `robots_rules.py` (robots.txt readings), `content_sniffing.py`. Pure, no
  network; the no-network scan still passes.
* `packages/debate_core/src/debate_core/integrations/http_fetcher.py`: the adapter, the per-host
  limiter and the request-URL log filter.
* `packages/debate_core/src/debate_core/application/ports/providers.py`: `FetchResult` re-exported
  rather than defined.
* `packages/debate_core/src/debate_core/application/settings.py`: `HttpSettings` gains
  `max_response_bytes`, `max_redirects`, `backoff_base_seconds`, `backoff_max_seconds`,
  `max_retry_wait_seconds`.
* Tests: `tests/integrations/test_http_fetcher.py`, `tests/retrieval/test_fetch_types.py`,
  `test_content_sniffing.py`, `test_robots_rules.py`; synthetic fixtures in
  `tests/fixtures/http_fetcher/` (each written by hand, README says so).

## Deviations from the spec

* **`HttpSettings` is in `debate_core.application`, outside `constraints.packages`**
  (`debate_core.retrieval`, `debate_core.integrations`). ac2 requires the size and redirect limits
  to be configurable via settings, and `settings.py` is the only place settings live, so the five
  fields were added there. The spec's package list should name `debate_core.application.settings`.
* **`FetchResult` moved** from `application/ports/providers.py` to `retrieval/fetch_types.py`, as
  the `fetch-types` node's output path requires, and the port re-exports it, so every existing
  import still works (the port's own docstring said this task would extend it).
* **Two error types beyond the node's six:** `UnsupportedScheme` (the PM's note: a hop to anything
  but http or https is a typed error) and `NonPublicAddress` (below). v1-e04-t03's ac1 maps "every
  FetchError subtype", so t03 needs both in its table.
* **Errors are values, not exceptions.** The node says "a FetchError hierarchy … with Pydantic
  models"; the port promises a refused or failed fetch is a `FetchResult`, not an exception. Both
  hold: `FetchResult.error` is a discriminated union of the error models.

## Decisions and assumptions

* **Private and loopback addresses are refused** (`NonPublicAddress`), for the URL asked for and
  every redirect hop, before anything is sent. Why: the URL comes from a student or a search
  result, and a public page can redirect anywhere; without the check, a redirect to
  `http://169.254.169.254/` (the cloud metadata endpoint a V2 worker would have) or a home router
  would be fetched and could be stored as a source. Refused: `localhost` and `*.localhost`, and any
  literal address that is not globally routable (`ipaddress.is_global`), including the legacy
  spellings `127.1`, `0x7f000001`, `2130706433` and IPv4-mapped IPv6. Not covered: a public *name*
  that resolves to a private address (DNS rebinding); that needs a resolver hook in the transport
  and is listed under follow-up work.
* **robots.txt readings.** 2xx: its rules. 401/403: refuse everything (`ROBOTS_ACCESS_DENIED`, as
  `urllib.robotparser.read()` does). Other 4xx: allow everything (RFC 9309 §2.3.1.3). 429, 5xx, a
  timeout, a failed connection or a redirect loop, after the usual retries: refuse everything
  (`ROBOTS_UNREACHABLE`, RFC 9309 §2.3.1.4), the conservative reading the PM named. Redirects on
  robots.txt are followed through the same gates (minus robots), up to `http.max_redirects`. A file
  over 500 KiB is cut at its last whole line. The cache lives as long as the fetcher, keyed by
  scheme, host and port, since RFC 9309 scopes robots.txt to an origin.
* **Two readings of robots.txt, and a URL needs both.** `urllib.robotparser` (given only text, never
  a URL; a test pins that) applies the first matching rule and ignores `*` and `$`, both of which
  make it more permissive than the site meant (`Allow: /` then `Disallow: /private` allows
  `/private/x`). An RFC 9309 longest-match reading of the same text is required to agree. The cost:
  an allow-list written disallow-first (`Disallow: /`, `Allow: /public/`) refuses `/public/a`, as the
  stdlib alone does. `Crawl-delay` is not read.
* **The URL is fetched as given** (the PM's amendment from v1-e04-t01): a test fetches a mixed-case,
  AMP, tracking-parameter URL and asserts its canonical form was never requested.
* **Retries.** `ConnectTimeout` counts as a connect failure and is retried (nothing was sent);
  `ReadTimeout` is not. Backoff is `min(backoff_max, base × 2^(n-1))`, jittered into its upper half,
  so it is never above the cap. `Retry-After` is honoured exactly on 429 and 503 only (the node's
  wording); on 502 and 504 the fetcher's own backoff applies. A `Retry-After` over
  `max_retry_wait_seconds` ends the fetch at once with `HttpStatusError.retry_after_seconds` set.
* **Deadlines.** `connect_timeout_seconds` for connecting; `request_timeout_seconds` for each read and,
  checked against the injected clock while streaming, for one request from send to last byte (a
  server dripping one byte every 29 s is stopped). It is per request, not per fetch: a fetch with
  retries and backoff may take longer in total.
* **Access status.** The fetcher sets only `ROBOTS_DISALLOWED`; everything else is `UNKNOWN` for the
  classifier (t03), which reads `error`, `status_code` and the body, so the mapping is written once.
  A 4xx/5xx keeps its body (a 403 may be a bot challenge); any other error has an empty body, which
  the model enforces.
* **Nothing to bypass with.** No cookies (the jar's policy allows no domain), `trust_env=False` (no
  `~/.netrc` login, no proxy from the environment), and no header but the User-Agent from settings.
* **Logs.** Messages and the fetcher's log lines name the host only. httpx logs each request's full
  URL at INFO; `RequestUrlLogFilter` cuts those records to the origin, but only while the fetcher is
  sending (a context variable), so other adapters' httpx lines and filters are untouched (a test
  shows another client's full URL still logged). Per the PM's note, the leak tests start with bare
  httpx/httpcore loggers and restore them, and passed after the OpenCaselist and discovery suites in
  one process.
* **httpx and redirects.** With `follow_redirects=False` httpx still builds the redirect request
  inside `send` and raises on a `Location` it cannot use (`javascript:`), before the status is seen.
  A response hook moves `Location` into a response extension so the fetcher judges it itself.
* **Retry-After.** v1-e07-t01 merged during the session, so the fetcher imports
  `retry_after_seconds` from `debate_core.integrations.discovery.http_failures`, as the PM's note
  allowed; nothing was moved or copied. (A staged copy in a shared module was dropped before the
  sync.)
* **Content sniffing** records what the first bytes look like (`sniffed_content_type`: PDF, HTML,
  XML and a few binary types, WHATWG signatures) beside the declared type and never replaces it.

## Operator follow-ups

None yet. The packaging change, if the PM approves it, changes `pyproject.toml` and `uv.lock`, which
makes the affected set the whole selection; that run is the pull request's `ci` check.

## Follow-up work

* **A third Retry-After parser** remains in `integrations/opencaselist/transport.py` (`_retry_after`),
  which reads the wall clock rather than an injected one. Moving `retry_after_seconds` to a shared
  `debate_core.integrations` module and using it there is a small task of its own (E34 or E01).
* **DNS-resolved private addresses** are not refused (see Decisions). A resolver check in the
  transport belongs with the V2 worker that fetches in the cloud.
* **`FakeArticleFetcher`** still answers unknown URLs with `access_status=NOT_FOUND` and no `error`;
  t05 may want it to return `HttpStatusError(404)` and `UNKNOWN` like the real fetcher.
* **v1-e04-t03** must map `UnsupportedScheme` and `NonPublicAddress` as well as the node's six.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
