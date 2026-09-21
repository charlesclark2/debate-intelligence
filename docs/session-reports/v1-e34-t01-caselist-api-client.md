# Session report: v1-e34-t01-caselist-api-client

| | |
|---|---|
| Task | `v1-e34-t01-caselist-api-client` — OpenCaselist API client |
| Spec | [`plan_specs/v1/e34-caselist-sync/t01-caselist-api-client.yaml`](../../plan_specs/v1/e34-caselist-sync/t01-caselist-api-client.yaml) |
| Epic / release | `v1-e34-caselist-sync` / `v1.1` |
| Branch | `task/v1-e34-t01-caselist-api-client` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

This task adds the `CaselistArchiveSource` port and `OpenCaselistClient`, its httpx adapter in
`debate_core.integrations.opencaselist`. The adapter has one shared transport (the token cookie,
request pacing, backoff and typed errors) and one small module per resource group: caselists,
downloads, OpenEv and login. V3 can add schools, teams, rounds and cites without touching the
transport. Also added: `debate-research caselist auth login|status|logout`, a token store (macOS
keychain, or a 0600 gitignored file), and a log filter that removes the token and download paths.
The client refuses to build unless `caselist.api_enabled` is true, and the setting defaults to
false. All five plan nodes pass their criteria, and the full default suite passes (1,788 tests,
25 s).

**What to look at first:** Deviations 1–3. The upstream OpenCaselist source differs from the
spec's picture of the API in ways that affect ADR-0016 and t02.

- Archives are served from the site's object store, not from `/download`.
- The archive listing has no size and no date.
- The site builds **two** archives per caselist. Besides the weekly window, it builds a
  `<caselist>-all-<date>.zip` of every open-source file still attached to a round. That is exactly
  the "complete caselist" ADR-0016 says does not exist.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `policy-gate-and-fixtures` — Policy gate check and scrubbed API fixtures | Done | Checked the policy rather than assuming it: it reads **Approved**, v1.1 (2026-09-19), and clause 12 records the maintainer's 10-per-minute limit. The fixtures are synthetic. Their shapes come from the upstream OpenAPI definitions (`server/v1/routes/definitions/schemas/*.js` in `ashtarcommunications/caselist`, which generate `/v1/docs`) plus the columns the controllers return. `fixtures/opencaselist/README.md` records where each shape comes from. No token or password is committed; tests generate them at run time. |
| `token-store` — caselist_token storage with redaction | Done | Built before any client code, as the plan requires. Two backends: the keychain through `keyring` (one item per environment), and a file created 0600 inside a 0700 `secrets/` directory. A file anyone else can read is refused with `InsecureTokenFile`, not used. The token is a `SecretStr` from the moment it is read. The redaction filter covers this package's logger and the httpx/httpcore loggers. `.gitignore` covers `secrets/` and `caselist_token`. |
| `port-and-models` — CaselistArchiveSource port and response models | Done | The port's value models are strict `DomainModel`s. The wire models (`models.py`) ignore unknown fields. An OpenEv `path` is `repr=False`, and the login token is parsed straight into a `SecretStr`. |
| `http-client` — Polite httpx client with rate limiting and backoff | Done | Covered in detail under Decisions. |
| `auth-commands` — caselist auth login, status and logout | Done | Adds offline smoke checks and one opt-in `live` check that only lists. Adds two import-linter contracts that check what this node's criterion names ("httpx only in integrations"). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node: Data-use policy is approved | PASS | `grep -m1 -n Approved docs/policies/caselist-data-use.md` → `6:\| Status \| **Approved**, version 1.1, 2026-09-19.` |
| Node: Downloads fixture exists | PASS | `ls -l packages/debate_core/tests/fixtures/opencaselist/downloads.json` → 636 bytes |
| Node: Token storage and redaction tests pass | PASS | `uv run pytest packages/debate_core/tests/integrations/opencaselist -k "token or redact"` → `29 passed in 5.08s` |
| Node: CaselistArchiveSource port exists | PASS | `grep -n "class CaselistArchiveSource(Protocol)" …/application/ports/caselist_source.py` → line 150 |
| Node: Client tests pass offline with respx | PASS | `uv run pytest packages/debate_core/tests/integrations/opencaselist/test_client.py` → `55 passed in 4.15s` |
| Node: Auth command tests pass | PASS | `uv run pytest packages/debate_cli/tests/commands/test_caselist_auth.py` → `15 passed in 3.10s` |
| Node: Import boundaries hold (httpx only in integrations) | PASS | `uv run lint-imports` → `Contracts: 4 kept, 0 broken.` (two of the four are new: httpx/keyring stay in `integrations.opencaselist`, and the CLI reaches them only through it) |
| Epic node: task reports phase Succeeded | PASS | `uv run scripts/validate_specs.py --require-succeeded v1-e34-t01-caselist-api-client` → `v1-e34-t01-caselist-api-client: Succeeded`; `uv run scripts/validate_specs.py` → `OK: 282 files, 38 epics, 224 tasks, 20 releases` |
| ac1 — lists caselists, a caselist's archives as typed `ArchiveListing`s, and OpenEv files, parsed from respx fixtures into models that tolerate unknown fields | PASS, with Deviation 2 | `test_client.py::test_lists_*` and `test_models.py` (every fixture carries an undeclared field). `ArchiveListing` has the slug, date, name, URL, kind and `size_bytes`. The API supplies no size (Deviation 2). |
| ac2 — `download_archive` streams to a temp file, verifies byte length, records sha256, renames atomically into the inbox; an interrupted download leaves no partial file | PASS | `test_client.py::test_download_*` (14 cases). They cover: a short body, a long body, no `Content-Length`, an empty body, over the size ceiling, a connection dropped mid-stream (retried, then fails), `KeyboardInterrupt` and `CancelledError` mid-stream, an identical file already in the inbox, a different file already in the inbox (never overwritten), unsafe names. Each asserts no final file and no `.partial/*.part` left. |
| ac3 — no token or password in any log or exception text across login, list, download and a 401; token read from keyring or the 0600 file; the file path is gitignored | PASS | `test_client.py::test_no_token_or_password_reaches_a_log_or_an_exception` covers login, list caselists, list archives, list OpenEv, both kinds of download, a 401 and a rejected login. It captures every record at DEBUG (httpx's own request lines included) plus `str`, `repr`, full traceback and `vars()` of each exception. It asserts the token, password, username and the OpenEv path never appear. Also: `test_the_token_cookie_goes_to_the_api_host_and_never_to_the_file_host`, and `test_token_store.py` (keyring and file backends, 0600, gitignore coverage via `git check-ignore --no-index` on four paths). |
| ac4 — ≤10 file downloads in any rolling 60 s (default 8); >10 fails validation; requests spaced ≥ the interval; 429 and 503 retried honouring Retry-After up to a max attempt count; 401/403 raise `CaselistAuthExpired` after exactly one request | PASS | `test_file_downloads_never_exceed_the_limit_in_any_rolling_window[None-8 / 10-10 / 3-3]`: 40 downloads, archives and OpenEv together, checked over every window on a simulated clock. The observed maximum equals the limit. Also: `test_more_than_ten_downloads_a_minute_fails_validation`; `test_consecutive_requests_are_spaced_by_at_least_the_interval`; `test_a_transient_status_is_retried_…[429/502/503/504]`; `test_retry_after_is_honoured_in_seconds`, `…_as_an_http_date…`; `test_retries_stop_at_the_attempt_limit`; `test_a_retry_after_longer_than_the_ceiling_fails_at_once…`; `test_auth_refusal_raises_caselist_auth_expired_after_exactly_one_request[401/403]` (`call_count == 1`, no sleeps); `test_downloads_run_one_at_a_time_even_when_asked_concurrently` |
| ac5 — `caselist auth login\|status\|logout` work against respx; the client refuses unless `settings.caselist.api_enabled` (default false) | PASS | `test_caselist_auth.py` (15 tests): login is refused **before prompting** while the API is off (`CASELIST_API_DISABLED`, no request). Also covered: `status --check` is refused while the API is off, `test_the_api_is_disabled_by_default`, and `tests/smoke/test_caselist_auth.py` (4 offline checks, 1 live opt-in). |
| Full default suite (no regressions) | PASS | `uv run pytest -q` → `1788 passed in 24.18s` |
| Lint, format, types | PASS | `uv run ruff check packages tests/smoke/test_caselist_auth.py` → all passed; `uv run ruff format --check packages tests` → 159 files already formatted; `uv run pyright packages` → 0 errors (strict over `debate_core`, tests included); `pre-commit run --files <changed>` → all hooks passed |
| Live check against the real API | NOT RUN | It needs the operator's Tabroom login. See Operator follow-ups. |

## Files changed

- **`packages/debate_core/src/debate_core/integrations/opencaselist/`** (new): the adapter.
  - `client.py` is the port implementation and settings gate.
  - `transport.py`, `pacing.py` and `inbox_writer.py` are the shared base.
  - `caselists.py`, `downloads.py`, `openev.py` and `auth.py` are the per-resource modules.
  - `models.py` holds the wire models; `token_store.py` and `redaction.py` are described above.
- **`packages/debate_core/src/debate_core/application/ports/caselist_source.py`** (new) and
  `ports/__init__.py`: the port, its value models and its errors.
- **`packages/debate_core/src/debate_core/application/settings.py`**: `CaselistSettings` gains
  these fields:
  - `api_enabled` (default false) and `api_base_url` (https only).
  - `downloads_per_minute` (default 8; above `MAX_CASELIST_DOWNLOADS_PER_MINUTE = 10` is refused,
    and the error cites clause 12).
  - `min_request_interval_seconds`, `max_attempts`, `backoff_base_seconds` and
    `max_retry_wait_seconds`.
  - `token_backend` and `secret_file`.
- **`packages/debate_cli/`**:
  - New `commands/caselist_auth.py`, registered in `commands/__init__.py` as the `caselist auth`
    subgroup.
  - `container.py` gains `caselist_token_store()` and `opencaselist_client()`, imported lazily as
    the S3 adapters are.
  - `tests/test_app.py`: the doctor services list now includes the two new services. The test's
    own comment asks for exactly this update.
  - `README.md`: one line.
- **Tests:**
  - `packages/debate_core/tests/integrations/opencaselist/` (conftest, `test_client.py`,
    `test_models.py`, `test_token_store.py`, `test_redaction.py`).
  - `packages/debate_core/tests/fixtures/opencaselist/` (four JSON fixtures and a provenance
    README).
  - `packages/debate_cli/tests/commands/test_caselist_auth.py`.
  - `tests/smoke/test_caselist_auth.py`, and a row plus commands in `tests/smoke/README.md`.
- **Workspace:**
  - `packages/debate_core/pyproject.toml`: new `opencaselist` extra (httpx, keyring).
  - `packages/debate_cli/pyproject.toml`: now depends on `debate-core[opencaselist]`.
  - Root `pyproject.toml`: `keyring` in the dev group; `integrations.opencaselist` added to the
    boto3 contract's list, as that contract's comment asks every new adapter to do; the two new
    httpx/keyring contracts.
  - `uv.lock`: adds keyring and its dependencies.
- **`.gitignore`**: `secrets/` and `caselist_token`.
- **`plan_specs/…/t01-caselist-api-client.yaml`**: phase set to Succeeded.

## Deviations from the spec

I did not edit the spec's text. Each item below is the rule as built, for the PM to amend the
spec to. The first three come from reading the upstream source
(`ashtarcommunications/caselist`, read 2026-09-20). The last change to its archive code was
2025-01-05. **The deployed site may differ from that repository**, and one live listing would
settle all three (see Operator follow-ups).

1. **Archives are not downloaded through `GET /download?path=…`.**
   - Upstream, `GET /caselists/{caselist}/downloads` (`getBulkDownloads.js`) lists
     `weekly/<caselist>/*.zip` in the site's S3-compatible object store. Each entry is
     `{name, url}`, and the url points at that store, not at `api.opencaselist.com`.
   - `weeklyArchives.js` deletes each zip from the API server's disk after uploading it, so
     `/download?path=weekly/…` would find nothing.
   - The client therefore fetches an archive from the URL the listing gives. It **never sends the
     token to that host**; the cookie is attached only to requests for the API's own host.
   - OpenEv files still go through `GET /download?path=`. The leading `/` of the listed path is
     removed, because upstream `getDownload.js` rejects paths starting with `/` or containing `..`.
   - Consequence: a 403/404 from the file host raises `ArchiveUnavailable`, not
     `CaselistAuthExpired`. The token was never sent there, so logging in again cannot fix it.
     401/403 from the API host raise `CaselistAuthExpired` after exactly one request, as specified.
   - **For the PM:** confirm that fetching the listed URL counts as "through the documented API"
     under the policy's E34 gate. I read it as yes: the URL is what the documented endpoint returns.
2. **`ArchiveListing` has no `path` or listing-time `size`.**
   - ac1 lists "(caselist slug, archive date, path, size)", but the OpenAPI `Download` schema is
     only `{name, url}`.
   - The record carries the slug, `name`, `url`, a `kind`, and `archive_date` parsed from the name
     (`<caselist>-weekly-<YYYY-MM-DD>.zip` or `<caselist>-all-<YYYY-MM-DD>.zip`). A name that
     follows neither pattern stays undated and is marked `UNRECOGNISED`, with a warning; the client
     does not guess a date.
   - `size_bytes` is `None` in a listing. A download is checked against its `Content-Length`,
     which is required: a download without one is refused. It is also checked against
     `size_bytes` when a future listing supplies one.
   - The port's `download(path, dest)` became `download_archive(listing, inbox)` and
     `download_openev(file, inbox)`, because the two are fetched from different places.
3. **Two archive kinds exist upstream, and one of them is a complete caselist.** This affects
   ADR-0016, not just this client.
   - `weeklyArchives.js` builds `<caselist>-weekly-<date>.zip`: files whose round was updated in
     the last week. That matches ADR-0016's measurements exactly.
   - It also builds `<caselist>-all-<date>.zip`: every open-source file still attached to a round
     in the current season, deleting the previous `-all-` each time.
   - If the live site still publishes `-all-` archives, ADR-0016's premise ("no endpoint returns a
     complete caselist") and its daily-cadence reasoning need revisiting with the maintainer.
   - Two related facts from the same source, both for t02:
     - The archives are rebuilt only when that job runs, so a daily pull fetches the same weekly
       file several days running.
     - The data-use policy's E34 gate 4 still says "weekly cadence at most — no polling faster
       than archives are published", which conflicts with ADR-0016's daily sync.
   - The client handles both kinds (`ArchiveKind.WEEKLY` / `FULL`) and does not choose between
     them. That choice belongs to t02.
4. **Upstream also limits each user to 5 bulk (weekly-path) downloads per day**
   (`weeklyLimiter`), separate from the 10-per-minute limit. The client does not sleep through a
   day-long `Retry-After`. Any `Retry-After` above `caselist.max_retry_wait_seconds` (300 s) is
   reported at once as `ProviderRateLimited` carrying the stated wait. t02 needs to budget for this
   limit.
5. **Files outside the stated packages.** The spec lists `integrations.opencaselist`,
   `application.ports` and `debate_cli.commands`. These were also changed:
   - `application/settings.py`: required by ac5's `settings.caselist.api_enabled`.
   - `debate_cli/container.py`: the composition root is the only place a command may get a service.
   - Dependency files: `pyproject.toml` ×3 and `uv.lock`.
   - Import-linter contracts in the root `pyproject.toml`.
   - The doctor services assertion in `test_app.py`, and the smoke and CLI READMEs.
6. **A rejected login raises `CaselistLoginRejected`, not `CaselistAuthExpired`.** A 401 from
   `/login` means wrong credentials, not an expired token. It is still never retried, and it names
   neither the username nor the password.
7. **The live test lives in `tests/smoke/test_caselist_auth.py`** (the node's named output) and
   **only lists**: `auth status --check` plus one archive listing. A live download would spend the
   operator's daily bulk allowance for no benefit a respx test lacks.

## Decisions and assumptions

- **Async throughout**, like the other I/O ports. The CLI runs each command in `asyncio.run`.
- **The download window is rolling:** a download may start at *t* only if fewer than the limit
  started in (*t* − 60, *t*]. Every attempt counts, retries included, because each attempt is a
  download as far as the server is concerned. One lock is held across every request, including a
  whole streamed download, so nothing runs concurrently.
- **Defaults:**
  - `min_request_interval_seconds` 1.0 (floor 0.5).
  - `max_attempts` 4 (at most 8).
  - `backoff_base_seconds` 2.0, doubling.
  - `max_retry_wait_seconds` 300.
- **Retry-After** is honoured in seconds or as an HTTP date. Without it, the wait doubles. Retried:
  429, 502, 503, 504 and connection failures. Not retried: 500 and other 4xx, which follows the
  spec's list.
- **Failing loudly (ADR-0016).** Nothing reaches the inbox under its final name unless it is
  complete. In order:
  1. The body is streamed into `<inbox>/.partial/`, with `Accept-Encoding: identity` so the byte
     count is meaningful.
  2. The count is checked against `Content-Length`.
  3. The file is fsynced, then **hard-linked** to its final name, which fails rather than
     overwriting.
  4. The directory is fsynced.

  An identical file already present is reported as `already_present`. A different one raises
  `DownloadConflict`, and both files are left alone. The partial file is removed on any exception,
  `KeyboardInterrupt` and cancellation included. `.part` files older than an hour, left by a killed
  process, are swept when the next download starts.
- **Where the token goes:**
  - It is attached as a per-request header, and only for the API host.
  - httpx's cookie jar is cleared after every response, so a `Set-Cookie` from `/login` is never
    replayed.
  - Redirects are never followed, so a cookie cannot follow one.
  - Every httpx exception is translated and raised `from None`, because httpx's messages quote the
    URL, and a `/download?path=` URL names a file.
- **Which token is used:** `providers.caselist_token` (an environment variable, already declared
  in settings) wins over the store. It is reported as `token_in_settings` and never printed.
  `caselist.token_backend=auto` uses the keychain when one is usable and otherwise the file. The
  keychain account is the environment name, so a dev login never authenticates prod.
- **Nothing is sent where the network is forbidden:** the client also refuses with
  `NetworkDisallowed` when `allow_network` is false, which is what the `test` profile sets.
- **Rule 4 (no school, team code, filename or disclosure path in logs or errors).** Errors and log
  records name an archive by its own name (`<slug>-weekly-<date>.zip`, which carries no school or
  team) and an OpenEv file only by `openev-<id>`. `DownloadConflict` keeps the inbox path as an
  attribute and leaves it out of the message.
- **Dependencies:** httpx and keyring are a `debate-core[opencaselist]` extra, like `aws`, and the
  CLI depends on that extra.
- **Test artifact, not a leak:** `CliRunner` echoes simulated *visible* input (the username) onto
  stdout. A real terminal echoes keystrokes to the terminal, not the pipe, and the prompts go to
  stderr. The tests read the `--json` envelope from stdout's last line, and assert that the username
  is absent from stderr and from the envelope. Hidden input (the password) is not echoed at all, and
  that is asserted too.
- **Shape source:** the spec says "the /v1/docs OpenAPI spec". I read the definitions that generate
  it in the upstream repository, and cross-checked the `/v1/docs` schema list.

## Operator follow-ups

Only when you decide to turn the API on. Each command runs in seconds; they are hand-offs only
because they need your Tabroom credentials and reach the live site.

**Operator command** (expected runtime under 30 s)
Where: your Mac, in the task worktree `debate-intelligence-worktrees/v1-e34-t01-caselist-api-client`
```bash
# 1. Log in once. You are prompted for your Tabroom username and (hidden) password. Only the token
#    is stored. macOS may ask whether python may use the keychain; choose "Always Allow".
DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true uv run debate-research caselist auth login

# 2. Confirm it works (one request) and see what is stored. The token is never printed.
DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true uv run debate-research caselist auth status --check

# 3. The opt-in live check: lists only, downloads nothing.
DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true CASELIST_LIVE_SLUG=hsld26 \
    uv run pytest tests/smoke/test_caselist_auth.py -m live

# 4. Which archive kinds the live site publishes (Deviation 3). Prints archive names only
#    (<slug>-weekly|all-<date>.zip), which carry no school or team.
DEBATE_ENV=dev DEBATE_CASELIST__API_ENABLED=true uv run python -c "
import asyncio
from debate_core.application.settings import load_settings
from debate_core.integrations.opencaselist import OpenCaselistClient, CaselistTokenStore, default_secret_file
s = load_settings()
store = CaselistTokenStore.for_settings(s.caselist.token_backend, account=s.environment.value,
    secret_file=s.caselist.secret_file or default_secret_file(s.storage.data_dir))
async def main():
    async with OpenCaselistClient.from_settings(s, token_store=store, user_agent_version='manual') as c:
        for a in await c.list_archives('hsld26'): print(a.kind, a.archive_date, a.name)
asyncio.run(main())"
```
Success looks like this:
- Step 1 prints `Logged in. … The password was not stored.`
- Step 2 shows `Checked just now: True`.
- Step 3 ends with `1 passed`.
- Step 4 prints one line per archive. Paste step 4's output back: whether any `FULL` (`-all-`)
  lines appear decides Deviation 3.

To keep the API on for your machine afterwards, put `DEBATE_CASELIST__API_ENABLED=true` in your
`.env`, never in a committed profile. That is the policy decision the setting records.

## Follow-up work

- **ADR-0016 and the maintainer (PM):** does the live site publish `<caselist>-all-<date>.zip`?
  If it does, the "no complete caselist" premise and the daily-cadence reasoning need revisiting
  before t02 is specified further (Deviation 3).
- **Policy vs ADR-0016 (PM, `docs/policies/caselist-data-use.md` E34 gate 4):** the policy says
  "weekly cadence at most", while ADR-0016 says daily. One of them needs amending before t02
  schedules anything.
- **v1-e34-t02-scheduled-sync:**
  - Skip `<inbox>/.partial/` when reading the inbox.
  - Check the inbox for an archive's name before downloading it, to save the site's 5-per-day bulk
    allowance (the client reports an identical file as `already_present` but still fetches it).
  - Treat `ProviderRateLimited` with a day-long `retry_after_seconds` as "skip today", not as a
    failure to retry.
  - Decide how `UNRECOGNISED` listings are handled.
- **Spec text (PM):** amend ac1's "(caselist slug, archive date, path, size)" and the description's
  "`/download?path=` for archives" to match Deviations 1–2.
- **v1-e02-t06-import-boundary-guard:** absorb the two httpx/keyring contracts added here into the
  full contract set it owns.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
