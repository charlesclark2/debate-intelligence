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
on the seconds form. OpenCaselist's read it with `float()`, under which `Retry-After: nan` hung the
transport with its lock held. Under the PM's rulings (see PM conditions), every adapter now reads it
as ASCII digits only, as RFC 9110 writes it. A non-integer header, or digits from another script
such as `²`, is unreadable, and the adapter falls back to its own backoff. That closes the `nan` hang
and a `ValueError` the digits-only form raised on `²`.

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

* `packages/debate_core/src/debate_core/integrations/retry_after.py` (new): the one reader. The
  seconds form is ASCII digits only (`text.isascii() and text.isdigit()`), and the date form is
  measured from `now`.
* `.../integrations/discovery/http_failures.py`: its reader is removed. It imports the shared one and
  still exports the name, because `test_http_failures.py` imports it from there. The header now goes
  straight into the reader (`retry_after_seconds(_header(headers, "retry-after"), now=now)`), which
  the guard requires.
* `.../integrations/http_fetcher.py`: imports the shared module instead of `http_failures`.
* `.../integrations/opencaselist/transport.py`: `_retry_after` removed; a required `wall_clock: Clock`
  is added; the reader is called with `now=self._wall_clock.now()`.
* `.../integrations/opencaselist/client.py`: `from_settings` takes a required `wall_clock` and passes
  it to the transport.
* `packages/debate_cli/src/debate_cli/container.py`: one line, `wall_clock=_PortClock(self.clock())`,
  the container's existing clock as the port.
* Tests: `packages/debate_core/tests/integrations/test_retry_after.py` and
  `test_one_retry_after_reader.py` (new). `opencaselist/test_client.py` gets a wall clock on its
  `SimulatedTime` harness and three new tests: the date measured from the injected clock; a
  non-integer header falling back to the backoff while an integer and a date wait as before; and
  `nan` not hanging the transport on the real event loop. `discovery/test_http_failures.py` and
  `test_http_fetcher.py` each gain one test: non-ASCII digits give no wait instead of a
  `ValueError`.
* `tests/smoke/test_caselist_auth.py`: the live test passes a `WallClock()`.
* `plan_specs/v1/e07-discovery-adapters/t08-shared-retry-after.yaml`: `debate_cli` and `tests/smoke`
  added to `constraints.packages`, and the forbidden entry annotated. Each change sits under the
  PM's `# PM ruling 2026-10-22` comment, placed above what it annotates so YAML keeps it as a
  comment. The Goal is set to `Succeeded`.

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

* **One grammar for the seconds form: ASCII digits only** (the PM's rulings on questions 1 and 2).
  The two readers disagreed. Measured before any change (`scratchpad/probe.py`):

  | Header | discovery and fetcher | OpenCaselist transport | Now, every adapter |
  |---|---|---|---|
  | `1.5`, `+5`, `1e2` | `None` | `1.5`, `5.0`, `100.0` | `None`, so the backoff |
  | `-5` | `None` | `0.0` | `None` |
  | `inf` / `nan` | `None` | gave up / hung forever | `None` |
  | `²` | `ValueError` | `None` | `None` |
  | `١٢٠` (Arabic-Indic) | `120.0` | `120.0` | `None` |

  The first review kept the transport's `float()` reading behind a flag, to honour the forbidden
  entry. The PM ruled the `nan` hang a defect the entry was not protecting, and the flag is gone. No
  recorded OpenCaselist answer sends a non-integer, and every existing test sends an integer or a
  date, so no recorded wait changed.
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

None. The two defects this task found, `Retry-After: nan` hanging the OpenCaselist transport and the
digits-only form raising `ValueError` on `²`, were fixed here under PM conditions 1 and 2.

### PM questions (paste-ready relay prompt)

Sent with the first review. The PM review answered all three, and the PM conditions section records
how each was closed.

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

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on three conditions closed in this session before the pull request. The first two
answer your PM questions 1 and 2 by fixing them here rather than in a follow-up task. Record them
under "PM conditions", keep the phase `Succeeded`, and open the pull request with no `--partial`.
If anything comes out differently from what is written here, stop and ask for another review.

**What the PM checked.**
* The branch is clean, 5 commits on origin/dev at `649fc66`, and the diff is the 12 files listed.
* There is one reader, and the guard was shown red against both re-added copies.
* The adapters' existing Retry-After tests are unchanged, proven by `git diff` and, for
  `test_client.py`, by an AST comparison.
* The transport's clock is required, with no default, and the composition root passes it.

**Rulings on the PM questions.**

1. **Question 1: (b), now, in this session.** Drop `any_number`, so OpenCaselist reads the
   seconds form as digits only, as RFC 9110 and the other adapters do. A non-integer header falls
   back to the transport's doubling backoff.
   * **Why now:** `Retry-After: nan` hanging the transport forever with its lock held is a defect,
     not a wait the forbidden entry was protecting. Keeping it to honour "no change to waits" would
     read the entry against its purpose.
   * **The record:** no recorded OpenCaselist answer carries a non-integer header, and every
     existing test sends an integer or a date, so no recorded wait changes. Add above the forbidden
     entry: `# PM ruling 2026-10-22: OpenCaselist's float() reading of Retry-After is dropped for the
     digits-only form; "nan" hung the transport, and no recorded answer sends a non-integer.`
   * **Tests, red first:**
     * `nan`, `inf`, `1.5`, `-5` and `1e2` on the transport each fall back to its backoff, with no
       hang (`wait_for`-bounded);
     * an integer and a date wait exactly as before.
   * **The existing tests:** the transport's three existing Retry-After tests must still pass
     unchanged. If one cannot, stop and ask.
2. **Question 2: (a), now.** A header that `isdigit()` accepts but is not ASCII digits (`²`) is
   unreadable and gives `None`, never a `ValueError`. Test it red first through
   `provider_error_for_status` and the fetcher.
3. **Question 3: (a).** Add `tests/smoke` to `constraints.packages`, with `# PM ruling
   2026-10-22: the live smoke test builds the client and passes its required clock.`

**Accepted as written.**
* The reader taking `now: datetime`, read by every caller from its injected clock.
* The guard as an AST test beside the integrations tests.
* The pacer's monotonic clock left alone.
* The harness change to `SimulatedTime`.
* **The surviving "and calls it" mutant:** only a real adapter can fail that assertion, and the
  red run showed it failing against the re-added transport copy.

**Condition 3, the sync:** v1-e39-t07 (#407) and the PM batch (#405) merged after your base. Run
`scripts/task sync`, then re-run:
* the integrations directory and the always-run list;
* the guard;
* pyright, `lint-imports`, ruff and `validate_specs.py`.

Record the results. No operator follow-up.

## PM conditions

The three conditions of the 2026-10-22 review, closed in this session on top of `origin/dev` at
`8eb149a`. Nothing came out differently from the review's notes, so the verdict above stands and the
phase stays `Succeeded`. Commit ids are the ones after the sync; the task's code commits before it
were `a218857`, `6bd4175`, `e8c7a3a` and `1b64a8b` on `649fc66`.

### Condition 1: OpenCaselist reads the seconds form as digits only (question 1, ruling (b))

* `any_number` is gone from `retry_after_seconds` and from the transport's call. Every adapter now
  reads `delay-seconds` as ASCII digits, and a non-integer header gives `None`, so the transport
  takes its doubling backoff.
* The forbidden entry in the spec carries the PM's comment, above the entry so YAML keeps it as a
  comment. The parsed `forbidden` list is unchanged, checked by loading the spec.
* **Red first** (`.venv/bin/python -m pytest packages/debate_core/tests/integrations/opencaselist/test_client.py -k "falls_back or does_not_hang" -n 0 -p no:randomly`,
  against the code before the fix) → `6 failed, 3 passed`:
  * `test_a_retry_after_that_is_not_digits_or_a_date_falls_back_to_the_backoff`, each run bounded by
    `asyncio.wait_for(..., timeout=5)`: `nan`, `inf`, `1.5`, `-5` and `1e2` failed. `nan` recorded a
    `nan` sleep, `inf` gave up with "asked for infs", and `1.5`, `-5` and `1e2` waited 1.5 s, 0 s and
    100 s. Words, an integer (`37` → `[37.0]`) and a date (`[120.0]` from a fixed 2030 clock)
    passed, as before.
  * `test_a_retry_after_of_nan_does_not_hang_the_transport`, on the real event loop with a 0.01 s
    backoff: failed with `TimeoutError` after 5 s. That is the hang.
  * The first red run also failed the date case. That was a fault in the test, not the code: it used
    the `client` fixture, which is built before the test sets its 2030 clock. It now builds its
    client after setting the clock.
* **Green:** both tests pass. The real-loop `nan` test finishes in about half a second (the pacer's
  minimum interval).
* **The three existing transport tests are unchanged.** An AST comparison of every function in
  `test_client.py`, `test_http_failures.py` and `test_http_fetcher.py` against `649fc66` reports one
  changed function, `build_client` (accepted in the review). Nothing was removed; only the new tests
  were added. The earlier test pinning the `float()` reading, which this session wrote, is replaced.

### Condition 2: non-ASCII digits give `None`, never a `ValueError` (question 2, ruling (a))

* The seconds form needs `text.isascii() and text.isdigit()`. So `²` gives `None`, where it raised
  `ValueError`. So do Arabic-Indic `١٢٠` and full-width `１２０`, which `float()` used to read as
  120: the ruling says any non-ASCII digits.
* **Red first**, against the code before the fix:
  * `test_429_with_digits_that_are_not_ascii_is_rate_limited_with_no_stated_wait` (through
    `provider_error_for_status`) → both cases failed. `²` raised `ValueError`, and `١٢٠` gave 120.
  * `test_retry_after_in_digits_that_are_not_ascii_falls_back_to_the_backoff` (through the fetcher,
    the header sent as UTF-8 bytes) → both failed. `²` raised `ValueError` out of `fetch`, and `١٢٠`
    waited 120 s.
  * `test_anything_but_ascii_digits_or_a_date_is_unreadable` failed for `²`, Arabic-Indic and
    full-width digits.
  * Altogether, that first red run of the new tests gave `14 failed, 13 passed`. Green after the fix.

### Condition 3: `tests/smoke` in the packages, then the sync

* The spec's `constraints.packages` gains `tests/smoke`, under the PM's comment.
* `scripts/task sync v1-e07-t08-shared-retry-after` rebased the six task commits onto `origin/dev`
  `8eb149a` (#405, #406, #407, #408) with no conflicts. The branch was not on origin, so nothing was
  pushed. Dev touched none of this task's files and added no `Retry-After` reader. `uv sync
  --all-packages` was run after it. `git ls-remote origin refs/heads/dev` still gave `8eb149a` before
  this report was committed.

### Checks after the sync and the conditions

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest packages/debate_core/tests/integrations tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py -n auto -m "not slow and not live"` | exit 0, `3120 passed, 2 xfailed in 19.04s` |
| The guard: `.venv/bin/python -m pytest packages/debate_core/tests/integrations/test_one_retry_after_reader.py -n 0 -p no:randomly` | exit 0, `11 passed` |
| `tests/smoke/test_caselist_auth.py` with the CLI's `test_caselist_auth.py` and `test_caselist_pull.py` | exit 0, `84 passed` |
| `uv run pytest packages/debate_core/tests/integrations` (the node's criterion, through the interpreter) | `2841 passed, 2 xfailed` |
| `uv run --frozen ruff check .` / `ruff format --check .` | exit 0 / exit 0 |
| `.venv/bin/pyright` (the whole repository) | exit 0, `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | exit 0 / exit 0 |
| `uv run scripts/validate_specs.py` / `--require-succeeded v1-e07-t08-shared-retry-after` | `OK: 420 files, 40 epics, 358 tasks, 22 releases` / `Succeeded` |

* **Mutants, re-run on the new code:** 19, of which 18 were killed. New ones killed: digits not
  required to be ASCII; the `float()` reading put back; a negative number read as no wait. The
  survivor is the guard's "and calls it" assertion, which the review accepted.
* **Two slips, both caught and corrected before this report:**
  * The mutation harness restores each file with `git checkout`, and its first run started before
    this round was committed. Its byte check stopped it after one mutant. Only `retry_after.py` had
    been reverted; it was re-applied and the integrations directory re-run (`2841 passed`), then
    everything was committed before the harness ran again.
  * One commit was made while pyright reported an error: a `| tail` before `&&` hid it. The error was
    a `dict[str, bytes]` header in the new fetcher test, which now uses a bytes key. The commit was
    amended (it is `02e2d3a`), and every check above was run with its exit code shown.
