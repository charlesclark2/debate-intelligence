# Session report: v1-e07-t08-shared-retry-after

| | |
|---|---|
| Task | `v1-e07-t08-shared-retry-after` — One Retry-After reader for every HTTP adapter, on an injected clock |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t08-shared-retry-after.yaml`](../../plan_specs/v1/e07-discovery-adapters/t08-shared-retry-after.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t08-shared-retry-after` |
| Session status | COMPLETE |

## Summary

`retry_after_seconds` now lives in `debate_core/integrations/retry_after.py` (PM ruling), and it is
the only Retry-After reader in `debate_core.integrations`. The discovery mapping (`http_failures`,
which feeds, Google News and OpenAlex all reach through `provider_error_for_status`), the article
fetcher and OpenCaselist's transport all call it. The transport's own `_retry_after`, which measured
a date from `datetime.now(UTC)`, is gone. The transport now takes a required `wall_clock: Clock` with
no default, and `debate_cli`'s container passes it the container's clock.
`packages/debate_core/tests/integrations/test_one_retry_after_reader.py` parses every module in the
package and fails on a second reader. It was shown failing against the transport's old reader and
the old `http_failures` copy, both re-added. **What to look at first:** the two readers did not agree
on the seconds form. To keep every wait unchanged (the forbidden entry), the shared reader takes
`any_number=True` from the transport only. That flag keeps an existing hang on `Retry-After: nan`,
and the PM questions below ask whether to drop it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `retry-after` (Shared Retry-After) | Done | Shared module, injected clock, three adapters pointed at it, guard, new tests; criterion passes |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: one `retry_after_seconds` in a shared integrations module, used by the discovery mapping, the article fetcher and the OpenCaselist transport; an architecture test fails on a second copy | PASS | `.venv/bin/python -m pytest packages/debate_core/tests/integrations/test_one_retry_after_reader.py -n 0 -p no:randomly` → `11 passed`. `test_each_adapter_reads_retry_after_through_the_shared_reader` checks that each of the three modules' `retry_after_seconds` *is* the shared function and that each module calls it. **Red, against a re-added copy:** the transport's old `_retry_after` restored into `transport.py` and called → `2 failed, 8 passed`, the package test listing 3 violations starting `opencaselist.transport:457: defines _retry_after(), a second Retry-After reader`, and the adapter test failing with `imports the shared reader but never calls it`. Then `http_failures.py` restored to its pre-task text, with its own `retry_after_seconds` → `2 failed, 8 passed`, 4 violations starting `discovery.http_failures:25: parses an HTTP date outside the shared reader`, and the identity check failing. Both files were restored with `git checkout`. |
| ac2: the date form reads an injected clock, by test, and the three adapters' existing Retry-After tests pass unchanged | PASS | `test_retry_after.py`, 30 tests: every date read from a `FixedClock` set years ahead of the real now, so a wall-clock reader answers differently. Covers dates ahead, past, exactly now, with another zone and with none; the same date asking for less as the clock moves on; seconds not reading the clock. Two new transport tests in `test_client.py` (`test_a_retry_after_date_is_measured_from_the_injected_wall_clock`) sleep exactly `[120.0]`, and `[0.0, 1.0]` for a past date. **Unchanged:** `git diff 5b6be10 -- packages/debate_core/tests` touches no line of `test_http_failures.py`, `test_http_fetcher.py`, `test_feeds.py`, `test_openalex.py` or `test_resilience.py`. In `test_client.py` an AST comparison of every function against `5b6be10` reports `functions changed: ['build_client']`, so all three of the transport's Retry-After tests are byte-identical (see Deviations for the harness). `.venv/bin/python -m pytest packages/debate_core/tests/integrations/opencaselist/test_client.py packages/debate_core/tests/integrations/discovery/test_http_failures.py packages/debate_core/tests/integrations/test_http_fetcher.py packages/debate_core/tests/integrations/test_retry_after.py packages/debate_core/tests/integrations/test_one_retry_after_reader.py -n auto` → `231 passed`. |
| Node `retry-after`: Integration tests pass (`uv run pytest packages/debate_core/tests/integrations`) | PASS | The exact command → `2836 passed, 2 xfailed in 10.52s`. Before the change it gave `2790 passed, 2 xfailed`; the 46 new tests account for the difference. |

### Red run, then mutants

* **Refuse-nothing skeleton** (`retry_after_seconds` returning `None` for everything) against the new
  tests and the transport's Retry-After tests: `24 failed, 15 passed`. The 15 that pass are the
  cases whose correct answer is `None`.
* **20 mutants** (`/private/tmp/.../scratchpad/mutants.py`; each one is applied, its covering test
  files run with `-x`, and the file is restored from git and byte-checked). **19 killed.** Killed:

  | Where | Mutant |
  |---|---|
  | shared reader | date measured from `datetime.now(UTC)`; date distance always 0; a past date goes negative; a date with no zone not read as UTC; `any_number` ignored; `any_number` not clamping a negative; digits-only form reading any number; header not stripped |
  | transport | date measured from the real now instead of `wall_clock`; `any_number=True` dropped |
  | guard | function-name rule off; literal rule off; literal allowed inside *any* call; literal matched case-sensitively; date-parser rule off; date-parser allowlist ignored; date parser seen only as a plain name; docstrings not exempt; scan skipping every module |

  The first run left the function-name rule off as a survivor, because every synthetic copy also
  tripped another rule. The copy `def _retry_after(raw): return max(float(raw), 0.0)` was added
  (commit `6bd4175`) and the mutant is now killed.
  **Survivor:** deleting the guard's "and calls it" assertion. That assertion can only fail when a
  real adapter stops calling the reader, so no synthetic test can kill it. The red run above shows it
  failing against the re-added transport copy.

### Closing checks (working agreement 10)

* **Affected set:** `uv run scripts/affected_tests.py` selects 147 files from 12 changed files. Run
  once under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest <the 147> -n auto -m "not slow and not live"`,
  it **reached the alarm at 115 s**, so the full set is past two minutes and is left to the PR's
  `ci`. A second whole-set try without `tests/smoke` also hit the alarm. Neither left a worker
  running (checked with `pgrep`). To show that the overrun is the set's size and not a hang, I ran
  it in parts:
  * the 47 `packages/debate_cli` files → `857 passed in 31.85s`;
  * the other 82 files, not `tests/smoke` → `3072 passed in 109.10s`. The slowest are
    `tests/scripts/test_tub_deploy.py` and `tests/integration/test_launchd_install.py`, at about 8 s
    each;
  * the one smoke file this task edits, `tests/smoke/test_caselist_auth.py` → `4 passed`, its live
    test deselected by marker. The other 17 selected `tests/smoke` files were not run.
* **Changed test directories plus the always-run list:** `.venv/bin/python -m pytest packages/debate_core/tests/integrations tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/commands/test_caselist_auth.py -n auto -m "not slow and not live"`
  → `3130 passed, 2 xfailed in 18.51s`.
* `uv run --frozen ruff check .` → `All checks passed!`; `uv run --frozen ruff format --check .` →
  `1101 files already formatted`.
* `.venv/bin/pyright` (whole repository, as CI runs it) → `0 errors, 0 warnings, 0 informations`.
* `uv run --frozen lint-imports` → `Contracts: 15 kept, 0 broken.`;
  `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 46 CLI command and API route handlers within 25 statements`.
* `uv run scripts/validate_specs.py` → `OK: 404 files, 39 epics, 344 tasks, 21 releases`;
  `--require-succeeded v1-e07-t08-shared-retry-after` → `Succeeded`.
* Prerequisites, checked before starting: `v1-e07-t01-search-provider-contract` and
  `v1-e04-t02-http-fetcher` both report `Succeeded`.

## Files changed

* `packages/debate_core/src/debate_core/integrations/retry_after.py` (new): the one reader, with the
  digits-only seconds form, the `any_number` seconds form, and the date form measured from `now`.
* `.../integrations/discovery/http_failures.py`: its reader is removed. It imports the shared one and
  still exports the name, because `test_http_failures.py` imports it from there. The header now goes
  straight into the reader (`retry_after_seconds(_header(headers, "retry-after"), now=now)`), which
  the guard requires.
* `.../integrations/http_fetcher.py`: imports the shared module instead of `http_failures`.
* `.../integrations/opencaselist/transport.py`: `_retry_after` removed; a required `wall_clock: Clock`
  is added; the reader is called with `now=self._wall_clock.now(), any_number=True`.
* `.../integrations/opencaselist/client.py`: `from_settings` takes a required `wall_clock` and passes
  it to the transport.
* `packages/debate_cli/src/debate_cli/container.py`: one line, `wall_clock=_PortClock(self.clock())`,
  the container's existing clock as the port.
* Tests: `packages/debate_core/tests/integrations/test_retry_after.py` and
  `test_one_retry_after_reader.py` (new). `opencaselist/test_client.py` gets a wall clock on its
  `SimulatedTime` harness and two new parametrised tests.
* `tests/smoke/test_caselist_auth.py`: the live test passes a `WallClock()` (see Deviations).
* `plan_specs/v1/e07-discovery-adapters/t08-shared-retry-after.yaml`: `debate_cli` added to
  `constraints.packages` under the PM's `# PM ruling 2026-10-22` comment, which sits above the list so
  YAML keeps it as a comment; the Goal is set to `Succeeded`.

## Deviations from the spec

* **`tests/smoke/test_caselist_auth.py` is outside `constraints.packages`.** Its live test builds
  `OpenCaselistClient.from_settings` directly. With no default clock (the PM's rule), it needs one
  argument, so it gains a three-line `WallClock` and passes it. The spec is not amended: if the PM
  accepts the edit, `tests/smoke` joins the packages.
* **The OpenCaselist test harness changed; its Retry-After tests did not.** `SimulatedTime` in
  `test_client.py` gains a `wall_clock`, which `build_client` passes on. It starts at the real now,
  because `test_retry_after_as_an_http_date_is_honoured` writes its header date from
  `datetime.now(UTC)` and is unchanged. The clock is not a `build_client` keyword, because one test
  spreads a `dict[str, int]` of settings into `build_client` and pyright would type it against the
  clock.

## Decisions and assumptions

* **The shared reader keeps OpenCaselist's seconds form behind `any_number`.** The two readers
  disagreed. Measured before any change (`scratchpad/probe.py`):

  | Header | discovery and fetcher | OpenCaselist transport |
  |---|---|---|
  | `1.5`, `+5`, `1e2` | `None` (RFC 9110 `delay-seconds` is digits only) | `1.5`, `5.0`, `100.0` |
  | `-5` | `None` | `0.0` |
  | `inf` / `nan` | `None` | `inf` / `nan` |

  Unifying either way would change some adapter's wait, which the forbidden entry and the PM's
  "same waits" rule rule out. So there is one function with one keyword, `any_number`, which only the
  transport passes, and its behaviour is pinned by tests on both the reader and the transport. The
  question of dropping it is asked below.
* **The reader takes `now: datetime`, not a `Clock`,** because `test_http_failures.py` calls
  `retry_after_seconds(header, now=NOW)` and must pass unchanged. Every caller reads `now` from its
  injected `Clock`. The guard's literal rule makes the header value go straight into the reader, so
  there is no place left to pass anything but a clock reading.
* **Every reader in the package**, as the PM asked: the grep finds only the three. `feeds.py`
  (`FeedFetcher`, which `google_news_rss.py` uses) and `openalex.py` reach the reader through
  `provider_error_for_status` with their injected clock. `resilience.py` reads
  `ProviderRateLimited.retry_after_seconds`, not a header, and is unchanged; `test_resilience.py`
  passes. `feed_check.py`'s `_SystemClock` is the clock that script's own entry point injects.
  `feed_parsing.py` parses RFC 822 dates for an RSS `pubDate`; the guard allows it, with that reason
  written down.
* **The guard is an AST test, not an import-linter contract.** "A function that parses
  `Retry-After`" is a property of code, not of imports. The test lives in
  `packages/debate_core/tests/integrations`, inside this task's packages and the node's criterion
  command, rather than `tests/architecture`.
* **The transport reads the clock on every retryable status,** not only when a date arrives. That
  costs one `now()` per refusal and keeps the call a single expression.
* The monotonic `clock` that the transport's pacer reads keeps its `time.monotonic` default. It is
  not the wall clock and is outside this task.

## Operator follow-ups

None.

## Follow-up work

* **`Retry-After: nan` hangs the OpenCaselist transport (existing, kept by the forbidden entry).**
  `float("nan")` gets past the ceiling check (`nan > max` is false), and `asyncio.sleep(nan)` never
  returns. A 3 s `wait_for` around it timed out. The transport holds its lock throughout. `inf`
  instead gives up at once, saying the server "asked for infs". Dropping `any_number`, or rejecting
  non-finite numbers, fixes both.
* **The digits-only form raises on a Unicode digit `float()` cannot read (existing since
  `v1-e07-t01`).** `"²".isdigit()` is true and `float("²")` raises `ValueError`. httpx decodes a
  UTF-8 header to `²`, so a `Retry-After: ²` on a 429 escapes `provider_error_for_status` and the
  fetcher as a `ValueError` instead of `None`. The fix is one line (`text.isascii() and
  text.isdigit()`, or catch the `ValueError`). It changes behaviour, so I did not make it.

### PM questions (paste-ready relay prompt)

```text
v1-e07-t08 PM questions (bundled). The task is complete and every criterion passes; these decide follow-ups.

1. OpenCaselist's seconds form. Before this task the transport read Retry-After with float(), so
   "1.5" waited 1.5s, "-5" waited 0s, and "nan" hangs the transport forever (asyncio.sleep(nan)
   never returns, lock held). The discovery mapping and fetcher read digits only, as RFC 9110 says.
   To keep every wait unchanged I kept the transport's reading behind retry_after_seconds(...,
   any_number=True).
   Options: (a) keep any_number as is; (b) a follow-up task drops any_number, so OpenCaselist reads
   digits only like the other adapters (a non-integer header then falls back to the doubling
   backoff); (c) keep any_number but read a non-finite number as unreadable.
   Recommendation: (b). One grammar for one header, and the nan hang goes with it. No recorded
   OpenCaselist answer in the repo carries a Retry-After; every test sends an integer or a date,
   and both read the same either way.

2. The digits-only form raises ValueError on a header like "²" (isdigit() true, float() fails),
   since v1-e07-t01. Options: (a) fix it in the same follow-up, so it is unreadable and gives None;
   (b) leave it. Recommendation: (a). It is a crash on a malformed header, and the reader's own
   contract says "None when unreadable".

3. tests/smoke/test_caselist_auth.py is outside constraints.packages but had to pass the transport's
   new required clock (three lines). Options: (a) add tests/smoke to the spec's packages; (b) accept
   it as a recorded deviation. Recommendation: (a). It keeps the spec true to the diff.
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
