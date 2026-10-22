# Session report: v1-e04-t02-http-fetcher

| | |
|---|---|
| Task | `v1-e04-t02-http-fetcher` — Polite HTTP fetcher |
| Spec | [`plan_specs/v1/e04-article-retrieval/t02-http-fetcher.yaml`](../../plan_specs/v1/e04-article-retrieval/t02-http-fetcher.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t02-http-fetcher` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`HttpArticleFetcher` (`debate_core.integrations.http_fetcher`) implements the `ArticleFetcher` port
and always returns a `FetchResult`; a refusal or failure is a typed `FetchError` value on it, never
an httpx exception. Every request and every redirect hop passes four gates in order: a public
address, robots.txt for the hop's origin (read through the same client, by RFC 9309 alone, used for
at most 24 hours), the per-host minimum interval, and bounded retries (connect failures, 429, 502,
503, 504; `Retry-After` honoured on 429 and 503). Bodies are streamed and abandoned at
`http.max_response_bytes`. The URL is fetched as given, never its canonical form. httpx now has its
own `http` extra, and its import contract is split from keyring's, as the PM ruled. All five Goal
criteria and every node criterion pass, and the Goal is `Succeeded`. Look first at
`retrieval/robots_rules.py`, rewritten to the PM's ruling (e).

Commits are relative to `dev` at `b85babc` (the ROADMAP refresh after v1-e07-t01, #380 and #381),
synced with `scripts/task sync`. The checks below ran on `1b999dc`; the last sync brought in only
`ROADMAP.md` and `docs/README.md`.

## PM rulings applied (2026-10-21)

1. Packaging, option A: the `http` extra holds httpx; `opencaselist` keeps keyring, with a comment
   that it needs `http`; the CLI declares `debate-core[aws,docx,http,opencaselist,tub]`; `uv.lock`
   re-locked; `test_installation.py`'s pinned extras and drop cases updated; the import-linter
   contract split into an httpx contract and a keyring contract, the CLI contract renamed;
   `debate_core.integrations.http_fetcher` on the boto3 and lxml lists. The spec's
   `constraints.packages` now names the three `pyproject.toml` files and `uv.lock`, each with the
   comment `PM ruling 2026-10-21 (v1-e04-t02 packaging)`. No operator whole-selection run.
2. Retry-After: settled by the import from `discovery.http_failures`; OpenCaselist's own
   `_retry_after` stays a follow-up.
3. FYIs a, b, c, d and f accepted; `debate_core.application.settings` added to the spec's packages
   with the same comment. FYI e changed: RFC 9309 alone decides robots.txt, `urllib.robotparser` is
   dropped, 401/403 keep refusing everything (stricter than the RFC, said in a docstring), 429, 5xx
   and unreachable still refuse after retries, and the per-origin cache is capped at 24 hours on the
   injected clock. Shown failing first: the allow-list case was refused by the old reading.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `fetch-types` | Done | `FetchResult` moved from the port to `retrieval/fetch_types.py`, re-exported by the port; eight error types |
| `http-client` | Done | `integrations/http_fetcher.py`; new limits in `HttpSettings` |
| `retry-policy` | Done | Retry-After read with v1-e07-t01's `retry_after_seconds` (imported, not copied) |
| `robots-and-rate-limit` | Done | `retrieval/robots_rules.py` (RFC 9309, 24-hour cache), `HostRateLimiter` |
| `test-suite` | Done | 103 fetcher tests, 81 retrieval unit tests; pyright and lint-imports clean |
| Packaging (PM ruling) | Done | `http` extra, contract split, installation and architecture tests |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: implements ArticleFetcher, FetchResult with final URL, status, headers, content type, bytes, byte length, elapsed, fetched_at | PASS | `test_the_fetcher_implements_the_article_fetcher_port`, `test_a_page_comes_back_with_its_bytes_and_everything_about_the_response` (elapsed 500.0 ms and `fetched_at` asserted exactly on the simulated clock) |
| ac2: timeouts, max size, max redirects from settings; exceeding any is a typed FetchError | PASS | `uv run pytest …/test_http_fetcher.py -k limits` → `30 passed` |
| ac3: only connect errors, 429, 502/503/504 retried, bounded exponential backoff honouring Retry-After; other 4xx never | PASS | `uv run pytest …/test_http_fetcher.py -k retry` → `30 passed` (11 non-retried statuses parametrized, 400 to 505) |
| ac4: disallowed path refused with ROBOTS_DISALLOWED, no request to the target; robots.txt cached per host | PASS | `test_robots_a_disallowed_path_is_refused_and_never_requested` asserts the target route was never called and the only request was robots.txt; `test_robots_is_read_once_per_origin_and_cached` asserts one robots request per origin over four fetches; `test_robots_rules_are_read_again_once_they_are_24_hours_old` asserts no re-read at 23:59:59 and one at 24:00 |
| ac5: per-host minimum interval from settings; identifying User-Agent with contact URL on every request | PASS | `uv run pytest …/test_http_fetcher.py -k "robots or rate"` → `30 passed`; request start times asserted as `[0.0, 2.5, 5.0]` s |
| Node `fetch-types`: `fetch_types.py` exists containing `class FetchResult` | PASS | `grep -c "class FetchResult" packages/debate_core/src/debate_core/retrieval/fetch_types.py` → `1` |
| Node `http-client`: `uv run pytest packages/debate_core/tests/integrations/test_http_fetcher.py -k limits` | PASS | `30 passed in 3.91s` |
| Node `retry-policy`: `… -k retry` | PASS | `30 passed in 2.57s` |
| Node `robots-and-rate-limit`: `… -k "robots or rate"` | PASS | `32 passed in 2.56s` |
| Node `test-suite`: `uv run pytest packages/debate_core/tests/integrations/test_http_fetcher.py` | PASS | `103 passed in 2.28s` |
| Node `test-suite`: `uv run pyright packages/debate_core` | PASS | `0 errors, 0 warnings, 0 informations` |
| Node `test-suite`: `uv run lint-imports` | PASS | `Contracts: 13 kept, 0 broken.` (one more since the split) |
| Goal phase | PASS | `uv run scripts/validate_specs.py --require-succeeded v1-e04-t02-http-fetcher` → `Succeeded` |

Before the robots change the first three `-k` filters each selected 30 tests; I checked that with
`--co` because the equal counts looked like a mistake. They were not. The robots change added two
fetcher tests, both under `robots`.

## Checks run before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | Before the packaging change: 305 of 369 test files (`settings.py` and `ports/providers.py` reach the root `conftest.py`'s fake router), over two minutes, so not run. After it: "The whole selection is affected: packages/debate_cli/pyproject.toml is shared test ground." Both are the pull request's `ci` run (agreement 10; the PM ruled out an operator run) |
| `.venv/bin/python -m pytest -q` over `tests/retrieval`, `test_http_fetcher.py`, `application/test_settings.py`, `test_fakes.py`, `test_port_conformance.py`, `tests/architecture`, `tests/specs`, the CLI's `test_app.py`, `test_help_rendering.py`, `test_installation.py`, `commands/test_doctor.py`, `test_config_command.py` | `1101 passed in 26.04s`, after the packaging commit |
| `.venv/bin/python -m pytest -q -n 0 -p no:randomly` over `integrations/opencaselist`, `integrations/discovery`, then `test_http_fetcher.py` (the PM's ordering check) | `369 passed`, after the last fetcher change |
| `uv run ruff format --check .` / `uv run ruff check .` | `1027 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 13 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 396 files, 39 epics, 336 tasks, 21 releases` |
| `uv run scripts/check_command_blocks.py --base origin/dev` | `OK`, this report included |

Earlier, two wider runs were stopped by the 115-second limit, not by a failure: the changed
packages' whole test directories, and then `packages/debate_core/tests/application` alone. The
machine's load average was about 24 on 11 cores from another checkout's pytest run at the time.
Neither is quoted as a result.

### Import contracts, shown biting

Each new list entry for `http_fetcher` was checked by appending an import to
`integrations/http_fetcher.py` and running `uv run lint-imports` with the new `pyproject.toml` and
then with the one from before the change:

| Planted import | Before the change | After it |
|---|---|---|
| `import boto3` | `12 kept, 0 broken` | the AWS SDK contract BROKEN |
| `import lxml` | `12 kept, 0 broken` | "Document libraries stay inside debate_core.integrations.docx_parser" BROKEN |
| `import keyring` | `12 kept, 0 broken` | "The keychain library stays inside debate_core.integrations.opencaselist" BROKEN |

`tests/architecture/test_import_contracts.py` carries the renamed contracts and a new permanent
probe, `import keyring` in `debate_core.integrations.discovery`, which only the new keyring contract
catches (`111 passed`).

The installation tests were run red first: with the extras changed and the tests not yet updated,
3 failed (the pinned extras, and the two drop cases that left out `http`).

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

After the robots change (ruling e), a second run of 13 mutants on the new reading, all killed:
expiry exclusive at 24 hours; rules never expire; the fetcher ignoring expiry; first match instead
of longest; a tie going to Disallow; a group matched by a substring of the token; `*` ignored; `$`
ignored; percent-encoding not normalised; the rules ignored; 401/403 allowing; an unreachable
robots.txt allowing; the refusal ignored by the fetcher.

The robots change itself was shown red first, against the old two-reading code with a skeleton
`robots_rules_expired` that never expires: `7 failed, 46 passed`. The failures were the
disallow-first allow-list, the §5.1 answers for `foobot` (two) and `quxbot`, the group named only
by part of the token, the 24-hour expiry, and the stdlib still being imported.

The log-leak test was also shown red twice: before the log filter existed (httpx's own
`HTTP Request: GET <full URL>` line), and with the filter disarmed (`if _SENDING.get()` → `if False`).

## Files changed

* `packages/debate_core/src/debate_core/retrieval/`: `fetch_types.py` (FetchResult and the
  FetchError types), `robots_rules.py` (RFC 9309 reading, 24-hour age), `content_sniffing.py`. Pure,
  no network; the no-network scan still passes.
* `packages/debate_core/src/debate_core/integrations/http_fetcher.py`: the adapter, the per-host
  limiter and the request-URL log filter.
* `packages/debate_core/src/debate_core/application/ports/providers.py`: `FetchResult` re-exported
  rather than defined.
* `packages/debate_core/src/debate_core/application/settings.py`: `HttpSettings` gains
  `max_response_bytes`, `max_redirects`, `backoff_base_seconds`, `backoff_max_seconds`,
  `max_retry_wait_seconds`.
* Packaging: `packages/debate_core/pyproject.toml` (the `http` extra), `packages/debate_cli/pyproject.toml`,
  `uv.lock`, the root `pyproject.toml` (contract split, list entries);
  `packages/debate_cli/tests/test_installation.py` and `tests/architecture/test_import_contracts.py`
  follow them.
* Spec: `constraints.packages` amended as the PM ruled; Goal set to `Succeeded`.
* Tests: `tests/integrations/test_http_fetcher.py`, `tests/retrieval/test_fetch_types.py`,
  `test_content_sniffing.py`, `test_robots_rules.py`; synthetic fixtures in
  `tests/fixtures/http_fetcher/` (each written by hand, README says so).

## Deviations from the spec

* **`HttpSettings` is in `debate_core.application`, which `constraints.packages` did not name.**
  ac2 requires the size and redirect limits to be configurable via settings, and `settings.py` is
  the only place settings live, so the five fields were added there. The PM added
  `debate_core.application.settings` to the spec's packages (ruling 2026-10-21), and the packaging
  files with it.
* **Outside the amended packages:** `packages/debate_cli/tests/test_installation.py` and
  `tests/architecture/test_import_contracts.py`, which pin the extras and the contract names the
  ruling changed.
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
* **robots.txt readings.** 2xx: its rules. 401/403: refuse everything (`ROBOTS_ACCESS_DENIED`),
  deliberately stricter than RFC 9309, as the module docstring says. Other 4xx: allow everything
  (RFC 9309 §2.3.1.3). 429, 5xx, a timeout, a failed connection or a redirect loop, after the usual
  retries: refuse everything (`ROBOTS_UNREACHABLE`, RFC 9309 §2.3.1.4), the conservative reading the
  PM named. Redirects on robots.txt are followed through the same gates (minus robots), up to
  `http.max_redirects`. A file over 500 KiB is cut at its last whole line. Rules are kept per origin
  (scheme, host and port, since RFC 9309 scopes robots.txt to an origin) with the time they were
  read, and read again once 24 hours old by the injected clock (RFC 9309 §2.4).
* **RFC 9309 alone decides** (the PM's ruling e). The group naming the whole product token
  (`http.user_agent_product`, matched without regard to case, repeated groups merged), else the `*`
  groups; the longest matching pattern wins, a tie goes to Allow, `*` and a final `$` are
  understood, and paths and patterns are compared in one percent-encoded form. `urllib.robotparser`
  is not imported (a test pins that). The tests' expected answers are the RFC's own examples
  (§2.2.2, §2.2.3, §5.1, §5.2) and the stdlib-gap cases, written by hand. `Crawl-delay` is not read.
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

None. The packaging change makes the affected set the whole selection; per the PM's ruling, that run
is the pull request's `ci` check.

## Follow-up work

* **A third Retry-After parser** remains in `integrations/opencaselist/transport.py` (`_retry_after`),
  which reads the wall clock rather than an injected one. Moving `retry_after_seconds` to a shared
  `debate_core.integrations` module and using it there is a small task of its own (E34 or E01).
* **Public names that resolve to private addresses are not refused** (the PM's ruling d keeps this
  open). Only literal addresses and `localhost` are checked today; a resolver check in the transport,
  so the address actually connected to is the one judged (DNS rebinding included), belongs with the
  V2 worker that fetches in the cloud.
* **`FakeArticleFetcher`** still answers unknown URLs with `access_status=NOT_FOUND` and no `error`;
  t05 may want it to return `HttpStatusError(404)` and `UNKNOWN` like the real fetcher.
* **v1-e04-t03** must map `UnsupportedScheme` and `NonPublicAddress` as well as the node's six.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-21

**Notes:**

Accepted, with nothing more to do before the pull request. Every criterion passes, the Goal is
`Succeeded`, and the pull request opens with no `--partial`. Its `ci` check runs the whole
selection, since `pyproject.toml` and `uv.lock` changed. Paste any failure back here.

**What is good:**

* **Every hop passes the same four gates, in a sensible order:** public address, robots.txt for
  that origin, the per-host interval, bounded retries. The tests assert both the request times
  (`[0.0, 2.5, 5.0]`) and that a refused target was never requested.
* **Ruling (e) is implemented and shown.** The RFC's own §2.2.2, §2.2.3, §5.1 and §5.2 examples,
  plus the stdlib-gap cases, are written by hand. The red run caught the allow-list case and the
  `foobot` and `quxbot` answers. A test pins that `urllib.robotparser` is gone. The 24-hour expiry
  is tested at 23:59:59 and 24:00.
* **The mutation run found a real gap** (an equal-length Allow and Disallow tie), and it now has a
  test. 36 mutants in all.
* **The import contracts were shown biting,** before and after the split, for boto3, lxml and
  keyring, and the architecture test carries a permanent keyring probe.
* **Nothing to bypass with:** no cookies, `trust_env=False`, only the User-Agent header. The
  non-public address refusal covers the odd spellings (`127.1`, `0x7f000001`, IPv4-mapped IPv6).
  That is the right posture for URLs that come from students and search results.
* **The log filter cuts httpx's full-URL lines only while this fetcher sends.** Other adapters'
  lines and filters are untouched (tested), and the leak tests start with bare loggers and passed
  after the OpenCaselist and discovery suites in one process, as the CI note asked.
* **The httpx `follow_redirects=False` finding,** which still raises on a `javascript:` Location
  inside `send`, is handled by moving `Location` into a response extension so the fetcher judges it.
  That is careful work.

**Rulings:**

* **The deviations are accepted:** `test_installation.py` and `test_import_contracts.py` follow the
  ruling's changes, `FetchResult` moved and re-exported, the two extra error types, and errors as
  values.
* **Decisions are accepted.** The per-request rather than per-fetch deadline is fine for now; a
  caller wanting a total bound wraps the call.

**Follow-ups, placed by the PM in the next batch:**

* **The third Retry-After parser** (OpenCaselist's `_retry_after`, on the wall clock) joins the
  E01 follow-up task: move `retry_after_seconds` to a shared `debate_core.integrations` module and
  use it in all three places.
* **Names resolving to private addresses (DNS rebinding):** recorded for the V2 cloud worker, where
  it matters most. Not a V1 task.
* **v1-e04-t03:** an amendment to map `UnsupportedScheme` and `NonPublicAddress` with the node's six.
* **v1-e04-t05:** an amendment for `FakeArticleFetcher` to answer an unknown URL as the real fetcher
  does (`HttpStatusError(404)`, `UNKNOWN`).
