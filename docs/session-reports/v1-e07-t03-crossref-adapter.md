# Session report: v1-e07-t03-crossref-adapter

| | |
|---|---|
| Task | `v1-e07-t03-crossref-adapter` — Crossref adapter |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t03-crossref-adapter.yaml`](../../plan_specs/v1/e07-discovery-adapters/t03-crossref-adapter.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t03-crossref-adapter` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`CrossrefProvider` (`debate_core.integrations.discovery.crossref`) searches Crossref's `/works` with
`query.bibliographic`, the date filters, `rows` and `select`, on the polite pool when
`providers.contact_email` is set (`mailto=` and the User-Agent) and on the public pool otherwise. It
paces itself at Crossref's documented list limits since 2025-12-01 (public 1 a second, 1 at a time;
polite 3 a second, 3 at a time), tightened by each answer's `x-rate-limit-*` and
`x-concurrency-limit` headers. A query whose turn comes too late to be answered inside the wrapper's
timeout is never sent; it gets an empty partial answer that names the pool's rate, and the breaker
counts nothing. Partial dates keep their precision: `CandidateResult` gains `date_precision`, dedupe
lets a day-precise date win whatever the provider order, no Article stores a year or a month as a
day, and the search table shows `2021` or `2021-03`. The factory is wired into the CLI and not
enabled by default. Look first at the pacer (`_Pacer` in `crossref.py`) and at
`test_eleven_queries_on_the_public_pool_send_what_fits_and_leave_the_breaker_closed`.

The session stopped twice before building, as the brief asked: once on the documentation
differences and once on the public-pool case. The PM ruled on both on 2026-11-02, and those rulings
are in the spec. The findings from both stops are kept below, as written then.

### Crossref documentation, read 2026-11-02 (public pages only, no API call)

* [Access and authentication](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
  (last updated 2025-10-16): public pool 5 requests, concurrency 1; polite pool 10 requests,
  concurrency 3; Plus 150. Polite means "your email address in the `mailto` parameter or `agent`
  header". Limits are sent in `x-rate-limit-limit` and `x-rate-limit-interval`, and the
  concurrency limit in a third header, `x-concurrency-limit`, which the spec does not name. Over
  the limit is a 429; manual blocks are a 403. No `Retry-After` is documented; the page says to
  wait "a short while" and retry slower or with fewer simultaneous requests.
* [Announcing changes to REST API rate limits](https://crossref.org/blog/announcing-changes-to-rest-api-rate-limits/)
  (2025-11-05, effective 2025-12-01): rates are per second and split by request type. List and
  query requests, which is what `/works?query.bibliographic=` is: public 1 per second,
  concurrency 1; polite 3 per second, concurrency 3. Single-record requests: public 5/1, polite
  10/3. The access page has not been updated with the split.
* [Tips for using the REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)
  (2025-10-24): back off on 429; rows default 20, maximum 1000.
* [rest-api-doc README](https://github.com/CrossRef/rest-api-doc/blob/master/README.md)
  (marked deprecated): the User-Agent format `Tool/1.1 (https://example.org/tool/; mailto:tool@example.org)`,
  and `X-Rate-Limit-Interval` "always expressed in seconds" (`1s`). The current pages give no
  User-Agent format. The same README says `from-pub-date`/`until-pub-date` take `YYYY-MM-DD`.
* Work types: Crossref's thirty `/types` ids as Crossref staff listed them on
  [community.crossref.org](https://community.crossref.org/t/api-filter-exclude-type/4285)
  (2023-11-03). The `/types` endpoint itself was not called.
* Not found in any page read: the list of field names `select=` accepts. The twelve used are all
  fields of a Crossref work record; the operator's live smoke below is what confirms Crossref
  accepts them (a wrong one is a 400, which the smoke prints).

### Where CandidateResult.published_at is read (counted at 6343be2)

| Where | What it does with the date |
|---|---|
| `application/federated_dedupe.py:294` | Precedence for the merged date: Crossref first, then RSS, Google News, OpenAlex, Semantic Scholar, GDELT |
| `application/federated_dedupe.py:375`, `:396` | Copies the chosen member's date into `MergedCandidate.published_at` (no precision field) |
| `application/federated_dedupe.py:671-677` | Same-work match: two scholarly candidates by year; any other pair by calendar day and site |
| `application/federated_ranking.py:320` | Recency phrase in the score explanation (`age_in_days`) |
| `application/federated_ranking.py:361` | Tie order: newest first, undated last |
| `application/federated_ranking.py:402`, `federated_ranking_features.py:180-201` | Recency feature and age in days |
| `application/federated_search_articles.py:64` | `discovery_article`: the date becomes `Article.published_at` |
| `debate_cli/presenters/search_presenter.py:208` | `search --json`: the full timestamp |
| `debate_cli/presenters/search_presenter.py:270` | Search table: the calendar day |

No cite reads it: CitationService takes its date from the Crossref deposit (`DoiWork`, with its
own precision) and the page harvest, and nothing reads `Article.published_at` into a cite.
Re-checked after the sync onto v1-e06-t12: its new path reads a date the user states on a pasted
copy (`article_fetch.py:98`), never a candidate's or an Article's.

What changed, by the PM's ruling 2 of 2026-11-02: dedupe (precedence, the merged precision and the
same-work match), `discovery_article` (no year or month date) and the table. Ranking still reads the
period's start, as ruling 3 of the brief allows. `--json` is unchanged.

### The largest search on the public pool (PM ruling 1, 2026-11-02)

* **The wrapper's timeout** is `providers.timeout_seconds`, 10 s by default; no profile overrides
  it. Each query is its own wrapped call, and the fan-out starts them all at once, so every query's
  10 s starts at the same moment. The whole search's deadline is `providers.search_deadline_seconds`, 15 s.
* **The most queries one search sends** is 11 with today's taxonomy: `heg`/`answers` has 8
  templates (the largest pair of 127) and `--expand-llm` adds at most `DEFAULT_MAX_MODEL_QUERIES`,
  3. `ArgumentTaxonomy` sets no limit on templates per pair, so a taxonomy edit can raise it.
* **What happened with a plain pacer** (before the ruling), from a scratch simulation through the
  real `ResilientProvider` (time scaled down 10 times; 11 queries at once; a pacer of the pool's
  rate and concurrency and nothing else):

| Pool | Crossref's answer time | Answered | Timed out by the wrapper | Breaker afterwards |
|---|---|---|---|---|
| public | 0 s | 10 | 1 | closed |
| public | 0.5 s | 10 | 1 | closed |
| public | 1.5 s | 6 | 5 | open for the 60 s cool-down |
| public | 2.5 s | 3 | 8 | open for the 60 s cool-down |
| polite | 1.5 s | 11 | 0 | closed |
| polite | 2.5 s | 9 | 2 | closed |

  That was the case the ruling asked about, and the session stopped there.
* **What happens now** (the ruling's option A), from the committed tests on virtual time, 11
  queries at once through the registry's wrapper and the real `FanOutStage`:

| Pool | Crossref's answer time | Asked | Not asked | Breaker | Search |
|---|---|---|---|---|---|
| public | 0.5 s | 9 | 2 | closed, 0 errors | PARTIAL |
| public | 1.5 s | 6 | 5 | closed, 0 errors | PARTIAL |
| public | 2.5 s | 3 | 8 | closed, 0 errors | PARTIAL |
| polite | 1.5 s | 11 | 0 | closed, 0 errors | COMPLETE, last answer at 6.333 s |

  Each "not asked" answer says `crossref: not asked: the public pool allows 1 query a second; set a
  contact email for the polite pool`. A query is sent only while the clock is before its deadline,
  the timeout less the reserve. So at 2.5 s the fourth query, whose turn comes at 7.5 s exactly, is
  not sent: its answer would arrive at the 10 s timeout itself.
* **The order** (ruling 3): `FanOutStage.run` creates its calls query by query, in the expansion's
  order, and nothing awaits between a call's start and the pacer's queue, so Crossref sees them
  first come, first served in that order. An expansion's queries are its templates in the taxonomy's
  order, then a model's (`provider_queries`). No pair starts with the student's bare query: all 127
  pairs' first template already adds words to `{query}`, and an unexpanded search sends the bare
  query alone. The test asserts the queries not asked are the last ones.
* **Downstream** (ruling 4), from `packages/debate_cli/tests/test_search_presenter.py`, with three
  queries of which Crossref answered the first:
  * status `PARTIAL`, exit code `SEARCH_PARTIAL`, table title `PARTIAL: 4 results for "carbon capture subsidies"`;
  * footer: `Providers: PARTIAL, results may be missing` and
    `  crossref: partial, 4 results from 3 queries: not asked: the public pool allows 1 query a second; set a contact email for the polite pool`;
  * `--json` `providers`: `{"provider": "crossref", "outcome": "partial", "queries": 3, "failed": 0, "results": 4, "reasons": ["not asked: …"]}`;
    `provider_calls`: every call `"outcome": "ok"`, the two not sent `"partial": true` with the error;
  * `provider_health`: `state` closed, `error_count` 0, `consecutive_failures` 0, `last_error`
    null, `success_count` 3. A query never sent is counted by the wrapper as an answer, so it is
    in `success_count` and its wait is in the wrapper's latency median, and it is nowhere a failure.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `record-fixtures` (Record Crossref fixtures) | Done | Hand-written, not recorded (brief item 5): `packages/debate_core/tests/fixtures/discovery/crossref/`, with a README saying what each holds. |
| `request-etiquette` (Request builder with polite-pool etiquette) | Done | `works_parameters`, `user_agent`, `advertised_limits`, the pacer. |
| `item-mapping` (Item to CandidateResult mapping) | Done | `candidate_from_item` through the DOI client's `work_from_message`; the kit bound three times. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: requests include query.bibliographic, date filters, rows and a User-Agent with mailto, verified by respx | PASS | `test_a_request_carries_the_query_the_date_filters_rows_select_and_mailto` (respx route on every parameter, and the exact URL), `test_a_request_with_a_contact_email_names_it_in_the_user_agent` (respx header match), `test_a_request_without_a_contact_email_goes_to_the_public_pool`. |
| ac2: partial issued dates map to published_at with an explicit date_precision, never an invented day | PASS | `CandidateResult.date_precision` with its validator (`test_discovery.py`, 64 passed); `test_the_date_is_issued_then_online_then_print_at_its_deposited_precision` (12 cases), `test_a_year_only_date_is_never_given_a_day`; the fixture's year and month items in `works_query.expected.json`; the guard downstream (dedupe, Article, table). |
| ac3: X-Rate-Limit headers read into the resilience layer; fixtures map to expected CandidateResults; passes the kit | PASS | Headers go to the adapter's own pacer, as the PM ruled (option A), and a 429's `Retry-After` goes to the wrapper's hold: `test_each_requests_rate_limit_headers_tighten_the_pace_and_never_loosen_it` (11 cases), `test_a_request_after_an_answer_advertising_one_every_two_seconds_waits_two_seconds`, `test_a_429_advertising_a_tighter_limit_tightens_the_pace`, `test_a_429_holds_crossref_for_its_retry_after_and_one_without_for_the_cooldown`. Mapping: `test_the_recorded_items_map_to_the_hand_written_candidates`. Kit: `TestCrossrefProviderOnThePolitePool`, `…OnThePublicPool`, `…OnAnEmptyResult`. |
| ac4: in `debate_core.integrations.discovery`, passes the kit on its recordings, secrets never in a log line, passes in one process after the OpenCaselist and discovery suites | PASS | Kit as above with the contact email in `secrets`; `test_no_contact_email_reaches_a_log_line_an_error_a_repr_or_a_health_snapshot`; `test_the_adapter_alone_protects_the_logs_from_its_contact_email` (7 loggers). One process: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/opencaselist packages/debate_core/tests/integrations/test_http_fetcher.py packages/debate_core/tests/integrations/test_crossref_doi.py packages/debate_core/tests/integrations/discovery/test_redaction.py packages/debate_core/tests/integrations/discovery/test_resilience.py packages/debate_core/tests/integrations/discovery/test_registry.py packages/debate_core/tests/integrations/discovery/test_http_failures.py packages/debate_core/tests/integrations/discovery/test_fake_provider.py packages/debate_core/tests/integrations/discovery/test_openalex.py packages/debate_core/tests/integrations/discovery/test_feeds.py packages/debate_core/tests/integrations/discovery/test_crossref.py -n 0 -p no:randomly -q` → `932 passed in 4.06s`, after the sync. `--collect-only` confirmed Crossref's 195 ran last. |
| Node `record-fixtures`: artifact `packages/debate_core/tests/fixtures/discovery/crossref/works_query.json` exists | PASS | `ls -la` → 852 bytes. |
| Node `request-etiquette`: `uv run pytest packages/debate_core/tests/integrations/discovery/test_crossref.py -k request` | PASS | `24 passed in 1.67s` (after the sync). |
| Node `item-mapping`: `uv run pytest packages/debate_core/tests/integrations/discovery/test_crossref.py` | PASS | `195 passed in 1.72s` (after the sync). |

### Red runs, then green

* Domain: the field without its validator → `6 failed, 58 passed` (the six refusals did not raise); green `64 passed`.
* Adapter: `test_crossref.py` against a skeleton that maps nothing, sends a bare request and paces
  nothing → `144 failed, 50 passed`. Reasons grouped: 45 `assert None is not None` (no mapping),
  29 respx `AllMockedAssertionError` (a request with no parameters), 14 source type `OTHER` for a
  scholarly type, 8 `DID NOT RAISE ProviderUnavailable`, 7 secrets checks, the rest pace, reserve
  and limits assertions. Green `194 passed`, then 195 with the case the mutation run added.
* Guard: `11 failed, 152 passed` (dedupe and Article tests), green after.
* Presenter: the date test failed (`'2021-01-01' != '2021'`); the partial-answer test passed
  before any change, because the presenter already reports a partial answer correctly. It stays as
  the pin for ruling 4.

### Mutation run

Twenty mutants, each applied to the committed tree, run against its own test file with `-n 0 -p
no:randomly -x` and a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (no property here uses Hypothesis), then
restored; `git status` was clean after. Every one was caught by an assertion in the test aimed at it:

| Mutant | Caught by |
|---|---|
| PM: a year-only date given a day precision | `test_the_recorded_items_map_to_the_hand_written_candidates` |
| PM: X-Rate-Limit headers ignored | `test_a_request_after_an_answer_advertising_one_every_two_seconds_waits_two_seconds` (`[0.0, 0.333333, 0.666666] != [0.0, 2.0, 4.0]`) |
| PM: mailto logged (the constructor protects no log) | `test_the_adapter_alone_protects_the_logs_from_its_contact_email` |
| PM: a link entry read as open access | `test_the_recorded_items_map_to_the_hand_written_candidates` |
| PM: an unknown type mapped to scholarly | `test_an_unknown_or_missing_work_type_maps_to_other` |
| The deadline a day away: every query sent | `test_eleven_queries_on_the_public_pool…[answers in 0.5 s]` |
| A query too late raises instead of a partial answer | `test_eleven_queries_on_the_public_pool…` (outcomes) |
| Concurrency ignored | `test_the_public_pool_sends_one_request_at_a_time_and_one_a_second` |
| Spacing ignored | `test_a_request_after_an_answer_advertising_one_every_two_seconds…` |
| A finished query never frees its slot | the same |
| Reserve without its 1 s floor | `test_the_reserve_is_the_median_answer_time_clamped[at least 1 s]` |
| Reserve without its half-timeout ceiling | `…[at most half the timeout]` |
| Headers may loosen the documented pace | `test_each_requests_rate_limit_headers…[looser is ignored]` |
| An embargoed licence counts as in force | `test_the_recorded_items_map_to_the_hand_written_candidates` |
| A host that ends in `creativecommons.org` counts | `test_open_access_comes_only_from…[a host that ends like it]` |
| No mailto in the User-Agent | `test_a_request_with_a_contact_email_names_it_in_the_user_agent` |
| Dedupe: provider order alone picks the date | `test_openalexs_exact_day_is_never_replaced_by_crossrefs_year_or_month` |
| Dedupe: dates compared to the day whatever the precision | `test_fuzzy_title_outside_scholarship_compares_dates_at_the_coarser_precision` |
| Articles: a year date stored as a day | `test_a_discovery_only_article_never_turns_a_year_or_a_month_into_a_day[year]` |
| Presenter: every date shown as a day | `test_the_table_shows_a_year_or_a_month_and_never_an_invented_day` |

Three first attempts did not count, and were redone. The first "no deadline" mutant left a pacer
that never finished, and it was caught by the test harness's own deadlock assertion rather than by
a count; it became "the deadline a day away". The look-alike-host mutant survived, because the
test's look-alike, `creativecommons.org.example.org`, does not end in `creativecommons.org`; a case
for `notcreativecommons.org` was added (commit "Test a licence host that only ends like Creative
Commons'"). The first Article mutant was a syntax error (exit 2), not a catch.

### Checks before the report (after `scripts/task sync`, rebased onto dev at 1c93c91)

* Affected set: `uv run scripts/affected_tests.py` → `514 of 665 test files (77.3%) chosen in 17.0 s
  from 27 changed files`. `debate_core.domain.discovery` changed, and the root conftest reaches it
  through `fake_router` → `ports.providers`. That is well past two minutes, so by agreement 10 it is
  left to the pull request's `ci` check and not run here.
* Within the limit instead: the test directories of what changed and the always-run list:
  `tests/architecture/ tests/specs/ packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py packages/debate_core/tests/domain/ packages/debate_core/tests/integrations/discovery/ packages/debate_core/tests/integrations/test_crossref_doi.py packages/debate_core/tests/application/test_federated_dedupe.py packages/debate_core/tests/application/test_federated_search_articles.py packages/debate_core/tests/application/test_federated_ranking.py packages/debate_core/tests/application/test_federated_search.py packages/debate_core/tests/application/test_citation_service.py packages/debate_cli/tests/test_search_command.py packages/debate_cli/tests/test_search_presenter.py packages/debate_cli/tests/commands/test_doctor.py packages/debate_cli/tests/test_installation.py`
  with `-m "not slow and not live"` → `2784 passed in 34.93s`.
* The whole `packages/debate_core/tests/application` directory in one run hit the 115-second limit
  at about 98%, with the machine's load average at 20 from other sessions. Run in three parts it
  passed: the first half of its top-level files `1628 passed in 18.97s`, the second half `1562
  passed in 10.35s`, and `caselist/` with `tub/` `1935 passed in 86.52s`. So it was the time, not a
  hang.
* `uv run --frozen ruff check .` → `All checks passed!`; `uv run --frozen ruff format --check .` →
  `1843 files already formatted`; `uv run --frozen pyright packages/debate_core packages/debate_cli`
  → `0 errors, 0 warnings, 0 informations`; `uv run --frozen lint-imports` → `Contracts: 20 kept, 0
  broken.`; `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 72 CLI command and API
  route handlers within 25 statements`; `uv run scripts/validate_specs.py` → `OK: 585 files, 41
  epics, 522 tasks, 22 releases`; `uv run --frozen python scripts/docs_index.py
  --check-descriptions` → `All 68 indexed documents under docs/ have a description`; `uv run
  --frozen python scripts/check_links.py` → `OK: 3440 relative links and anchors in 554 Markdown
  files`; `.venv/bin/python scripts/export_schemas.py --check` → `OK: 10 schemas in
  packages/debate_core/schemas are up to date`.

## Files changed

* `packages/debate_core/src/debate_core/integrations/discovery/crossref.py` (new): the adapter, its
  pacer, its type table and its factory.
* `packages/debate_core/src/debate_core/domain/discovery.py`: `DatePrecision` and
  `CandidateResult.date_precision`, with the rule that a year or month date starts its period.
* `packages/debate_core/src/debate_core/application/federated_dedupe.py`: `MergedCandidate.date_precision`;
  a more precise date first in the date's precedence; the same-work date match at the coarser
  precision.
* `packages/debate_core/src/debate_core/application/federated_search_articles.py`: no year or month
  date on a discovery-only Article.
* `packages/debate_cli/src/debate_cli/presenters/search_presenter.py`: the Date column at the
  precision known.
* `packages/debate_cli/src/debate_cli/container.py`: `crossref_factory` in the discovery factory map.
* Tests: `packages/debate_core/tests/integrations/discovery/test_crossref.py` (new),
  `packages/debate_cli/tests/test_search_presenter.py` (new), and additions to `test_discovery.py`,
  `test_federated_dedupe.py`, `test_federated_search_articles.py`, `test_search_command.py`; the
  pinned integration lists in `test_doctor.py` and `test_installation.py`.
* Fixtures: `packages/debate_core/tests/fixtures/discovery/crossref/` (new, with its README).
* `plan_specs/v1/e07-discovery-adapters/t03-crossref-adapter.yaml`: the PM's rulings (packages,
  forbidden entries, the fixture path), the Deviation below, and the phase.

## Deviations from the spec

* **Packages, by the PM's rulings of 2026-11-02**, written into the spec with each ruling above it:
  `debate_core.domain`; `federated_dedupe` and `federated_search_articles` for the guard only, and
  their tests; `packages/debate_core/schemas`; `container.py` and `test_search_command.py`;
  `search_presenter.py` and `test_search_presenter.py`. Two forbidden entries were added for the
  pace.
* **The fixture path**: `packages/debate_core/tests/fixtures/discovery/crossref/` instead of
  `tests/fixtures/providers/crossref/` (brief item 5), and they are hand-written, not "recorded".
* **For the PM to confirm**: `packages/debate_cli/tests/commands/test_doctor.py` and
  `packages/debate_cli/tests/test_installation.py` were not in any ruling. They pin by hand the
  integrations the container imports, so wiring the factory adds
  `debate_core.integrations.discovery.crossref` to both lists, makes 41 into 42, and adds it to the
  modules that take httpx from the http extra. Without these edits the wiring ruling cannot pass
  CI. The spec lists them with a session comment, not a PM ruling.
* **The schema** (brief item 3, ruling 4): `scripts/export_schemas.py` was run and changed nothing,
  because `CandidateResult` is in no exported schema. `--check` → `OK: 10 schemas … are up to date`.
  No new export.
* **ac3's "into the resilience layer"**: the headers set the adapter's own pacer, not
  `ResilientProvider`. That is the PM's ruling 1 (option A); option B, the wrapper, is a follow-up.

## Decisions and assumptions

* **The pace** is one start every `interval/limit` seconds (a third of a second on the polite
  pool) and no more than the concurrency at once, rather than a burst of the whole limit and then a
  pause. That is never faster than Crossref's limit in any one-second window.
* **Header tightening**: each answer's headers are read against the documented limits, so a later
  answer can relax a temporary tightening back to the documented pace, and never past it. Headers
  that cannot be read, or that are only half there (a limit without an interval), are ignored. A 429
  advertising a tighter pace tightens it too.
* **The reserve** is the median of the last 50 answer times this adapter has seen (any status), so
  per process in the CLI. It is read again on each loop of the wait, so a query's deadline moves as
  answers arrive. When half the timeout is under 1 s, half wins (a 1.5 s timeout gives 0.75 s);
  tested.
* **A "not asked" answer** returns at its deadline, not at once. It is logged at INFO on the
  protected discovery logger without the address. Its message names the pool's current rate, so a
  tightened pace reads `1 query every 2 seconds`.
* **The 403** maps through `provider_error_for_status` to
  `ProviderUnavailable("crossref", "HTTP 403: the provider refused the request")`. It is sent once
  and never retried, like every request here. It counts as a breaker failure, as any refusal does.
* **The date** is `issued`, then `published-online`, then `published-print`, the first that is a
  real date (an impossible day such as 2024-02-30 or `[[null]]` moves on to the next). `issued` is
  Crossref's earliest known publication date. `published` was left out of `select`, because no doc
  read lists it as selectable.
* **Mapping reuse**: `work_from_message` from the DOI client reads title, venue, authors and date
  parts (with its face-markup removal), and `DoiAuthor.display_name` assembles names as
  CitationService does. The DOI goes through `ArticleIdentifiers` (ruling 7): it does more than the
  DOI client's `.lower()`, since it strips resolver prefixes and refuses a non-DOI.
* **Open access**: a licence counts when its URL is `http(s)://creativecommons.org/licenses/…` or
  `/publicdomain/…` (also `www.`), its `start.date-time` is on or before the clock's date, and its
  content version is not `tdm`. Otherwise it is `None`, never `False`. The open copy is a `link` with
  a licensed content version and an intended application of `text-mining` or `unspecified`,
  preferring `application/pdf`; similarity-checking links never count.
* **The User-Agent** with an address is `debate-research/<version> (+<contact_url>; mailto:<address>)`,
  from `http.user_agent_product` and `http.contact_url`; without one it is exactly the fetcher's
  `http.user_agent(version)`. The DOI client is unchanged.
* **Types**: the table is in `SOURCE_TYPE_BY_WORK_TYPE`, and reproduced here:

| Crossref type | source_type |
|---|---|
| journal-article, proceedings-article, posted-content, book, monograph, edited-book, reference-book, book-chapter, book-section, book-part, book-track, reference-entry, dissertation, peer-review | scholarly |
| report, report-component, standard, dataset, database, component, grant, other, journal, journal-volume, journal-issue, proceedings, proceedings-series, book-series, book-set, report-series | other |
| any other value, or none | other |

* **Rows**: `rows` is `max_results`, which `SearchFilters` caps at 200, so Crossref's 1,000 is never
  reached and one page is enough.
* **Virtual time in the tests**: `VirtualTime` in `test_crossref.py` drives the pacer on a
  `FixedClock` and a sleep that wakes when every task is waiting. The wrapper's own timeout is the
  event loop's, so the virtual-time tests do not exercise it. A separate real-time test
  (`test_a_sent_query_that_runs_slow_still_times_out`, 0.05 s) shows a sent query still times out.

## Operator follow-ups

Both are optional and for after the merge, once an installed build carries this change.

1. **The polite pool.** Crossref treats a caller with a contact address better: 3 queries a second
   rather than 1. Put the address you want Crossref to reach in the gitignored `.env` of the folder
   you run `debate-research` from, as a line `DEBATE_PROVIDERS__CONTACT_EMAIL=` followed by the
   address, or export the same variable in your shell profile. Never put it in
   `config/profiles/*.toml`: those files are committed. The same setting already reaches the DOI
   lookups behind `cut`. To check it is read and masked, run this from that folder; it takes about a
   second, and `providers.contact_email` should show the redaction placeholder, never the address:

   ```bash
   debate-research config show
   ```

2. **Live smoke search through the installed build.** Run it from the folder with the `.env`. It
   makes two searches with Crossref alone enabled: one on the polite pool for a single query, and one
   on the public pool for an expanded search of up to 8 queries (`heg`/`answers`). Each takes a few
   seconds and costs nothing. It writes each search, and up to 20 discovery-only Articles, to your
   local store, as any search does. It prints only statuses, counts and the providers' reasons, never
   a title, a name or the address. Success looks like this:
   * polite run: `status: COMPLETE`, `crossref: ok`, `results: ` above zero, `with a DOI` equal to
     `results`, `breaker: closed, errors 0`;
   * public run: `status: COMPLETE` or `PARTIAL`, `crossref: ok` or `partial`, `results:` above zero,
     and, if partial, the reason `not asked: the public pool allows 1 query a second; set a contact
     email for the polite pool`, never an `HTTP` reason;
   * `HTTP 400` in any reason means Crossref refused a `select` field; `HTTP 429` means the pace is
     wrong. Either way, please paste the output back.

   ```bash
   env -u DEBATE_STORAGE__DATA_DIR -u DEBATE_ENV DEBATE_PROVIDERS__ENABLED='["crossref"]' debate-research search "carbon capture subsidies" --format json > crossref-smoke-polite.json
   env -u DEBATE_STORAGE__DATA_DIR -u DEBATE_ENV DEBATE_PROVIDERS__ENABLED='["crossref"]' DEBATE_PROVIDERS__CONTACT_EMAIL= debate-research search "us hegemony" --argument heg --need answers --format json > crossref-smoke-public.json
   for run in polite public; do python3 - "crossref-smoke-$run.json" "$run" <<'EOF'
   import json
   import sys

   document = json.load(open(sys.argv[1]))
   body = document.get("data") or (document.get("error") or {}).get("details") or {}
   results = body.get("results") or []
   print(f"--- {sys.argv[2]} run")
   print(f"status: {body.get('status')}")
   for provider in body.get("providers") or []:
       print(f"{provider['provider']}: {provider['outcome']}, {provider['queries']} queries, {provider['failed']} failed, {provider['results']} results")
       for reason in provider["reasons"]:
           print(f"  reason: {reason}")
   print(f"results: {len(results)}")
   print(f"with a DOI: {sum(1 for item in results if item['identifiers'].get('doi'))}")
   print(f"dated: {sum(1 for item in results if item['published_at'])}")
   calls = body.get("provider_calls") or []
   print(f"calls not asked: {sum(1 for call in calls if call['partial'])} of {len(calls)}")
   for health in body.get("provider_health") or []:
       print(f"breaker: {health['state']}, errors {health['error_count']}")
   EOF
   done
   rm crossref-smoke-polite.json crossref-smoke-public.json
   ```

## Follow-up work

* **The wrapper should not count time spent waiting in a pacer as a failure, for every provider**
  (the PM's ruling 6: option B, for when Semantic Scholar, `v1-e07-t04`, paces itself). Today only
  Crossref paces itself, and it avoids the wrapper's timeout by answering "not asked" before it.
  A shared pacer, or a way for an adapter to tell the wrapper it is still queued, would let every
  provider pace without its own deadline arithmetic. The PM files it.
* **A `date_precision` key in `search --json`** (the PM's ruling 3). `results[].published_at` is
  still the period's first instant, `2021-01-01T00:00:00+00:00` for a year. A key beside it, from
  `MergedCandidate.date_precision`, would let a JSON reader tell a year from a first of January.
  `tests/smoke` pins `--json` key sets whole, so the follow-up adds the key there too. The PM files it.
* **A partial date on an Article and in a cite**, once the Citation date follow-up from
  `v1-e06-t12` lands: a year or month precision is stored as no date today
  (`discovery_article`).
* **The taxonomy's queries per pair are uncapped.** On the public pool a search sends what fits in
  about 8 to 9 seconds, so a pair with more templates gets more "not asked" answers. A cap in
  `ArgumentTaxonomy`, or a note in the taxonomy's README, would keep the worst case where it is
  measured here (11 queries).
* **A "not asked" answer counts as a wrapper success** and adds its wait to the wrapper's latency
  median in `provider_health`. That is not a failure anywhere, as ruling 4 asked, but the median can
  read high after a large public-pool search. It is worth settling with the wrapper follow-up above.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
