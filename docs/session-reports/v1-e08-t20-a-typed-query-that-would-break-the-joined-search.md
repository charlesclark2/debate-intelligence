# Session report: v1-e08-t20-a-typed-query-that-would-break-the-joined-search

| | |
|---|---|
| Task | `v1-e08-t20-a-typed-query-that-would-break-the-joined-search` — A typed query with an unbalanced parenthesis or a bare operator cannot change or break the joined search |
| Spec | [`plan_specs/v1/e08-research-workflows/t20-a-typed-query-that-would-break-the-joined-search.yaml`](../../plan_specs/v1/e08-research-workflows/t20-a-typed-query-that-would-break-the-joined-search.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t20-a-typed-query-that-would-break-the-joined-search` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The NHI politics DA link search no longer loses OpenAlex. The operator's 12 real requests on
2026-11-12 found what OpenAlex refused on 2026-11-11: a `search=` over **1,500 characters**, by
OpenAlex's own message ("Your search is too long (1536 characters; the limit is 1500)"). It is not the
URL, not the number of OR groups, not the key and not the page. `works_requests` now splits by that
limit (`MAX_SEARCH_CHARS`), keeping the URL cap beside it, so the 37-query search goes as 24 and 13
queries: **two requests a page** where it was one refused request. A joined request OpenAlex still
refuses with 400 is split in halves under the PM's amended ruling, and a query with an unbalanced
parenthesis or double quote, or an upper-case AND, OR or NOT outside a quoted phrase, is sent alone,
as typed, with the footer's OpenAlex line saying so. Tests were shown failing first (three red runs),
and 21 of 22 planted breaks were caught; the one that survived is equivalent (below). **Look first at**
the measurement table and at Deviations 3 and 4: two docstrings in `debate_core.domain`, outside this
task's packages, now say what is no longer true, among them `MAX_QUERIES_PER_SEARCH`'s reason for 42.

Commit ids are on this branch, from `origin/dev` at `308f1e8`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `a-typed-query-that-would-break-the-joine`: Typed query guard | Done | Widened by the PM (2026-11-12). Measurement handed off and returned; tests over a skeleton `a9942ab`, implementation `eea31a7`, CLI `19fe0fc`, the measured rule `23ce710`, checks `0b3cdc3`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the handling is ruled on by the PM, and a typed query with an unbalanced parenthesis or a bare operator cannot change or fail the other queries of a joined search, by tests shown failing first | PASS | Ruled: the PM's rulings 1 to 4 and answers Q1 to Q4 (2026-11-12, under Decisions). Tests: `test_a_query_that_could_reach_outside_its_group_is_asked_alone` (13 cases) and `…_stays_inside_its_group_is_joined` (8), `test_a_query_with_an_open_parenthesis_is_sent_alone_as_typed_and_the_others_joined`, `test_queries_with_a_bare_operator_or_a_lone_quote_are_each_sent_alone_and_never_rewritten`, the two CLI tests; the fallback and rule tests below. Shown failing first: below. |
| Node: `uv run pytest packages/debate_core/tests packages/debate_cli/tests -k "joined or batch"` | PASS | Run as `hard_stop.py 115 .venv/bin/python -m pytest … -k "joined or batch" -n auto` → `92 passed in 27.77s` |

### The measurement (the PM's ruling 1)

The operator ran the probe (its text is in the appendix) from `$HOME` with the installed
`v1.1.0-dev.407`, reading settings as the CLI does, so the key came from the per-user credentials file.
It rebuilt the search's 37 queries with the build's own expansion and sent each request through the
build's own adapter (`OpenAlexProvider._page`), so the parameters and headers were exactly a search's.
The contact email is never sent to OpenAlex, so no request varied it. 12 requests, one at a time.

| Request | N | URL | Search | OR groups | Status |
|---|---|---|---|---|---|
| first N | 12 | 1,041 | 727 | 12 | 200 |
| first N | 20 | 1,566 | 1,220 | 20 | 200 |
| first N | 22 | 1,696 | 1,342 | 22 | 200 |
| first N | 23 | 1,772 | 1,414 | 23 | 200 |
| first N | 24 | 1,835 | 1,473 | 24 | 200 |
| first N | 25 | 1,902 | 1,536 | 25 | 400 "too long (1536 characters; the limit is 1500)" |
| first N | 30 | 2,230 | 1,844 | 30 | 400, same message (1844) |
| first N | 37 | 2,686 | 2,272 | 37 | 400, same message (2272) |
| the 25 queries' words in 13 groups | 25 | 1,794 | 1,476 | 13 | 200 |
| 25 groups of one word each | 25 | 704 | 338 | 25 | 200 |
| the 25, without the key | 25 | 1,902 | 1,536 | 25 | 400, same message |
| the 25, page 2 | 25 | 1,902 | 1,536 | 25 | 400, same message |

So the limit is the search's length, 1,500 characters, as OpenAlex says; the URL is not what is
refused (1,902 refused, 2,686 under t16's 3,500), and neither is the group count (25 one-word groups
answered). The key does not raise it (OpenAlex's message says a paid plan does). The figure counts the
search's characters as Python's `len` counts them, which matched OpenAlex's own count on every refusal.

### The rule (ruling 2)

`MAX_SEARCH_CHARS = 1_500`, with the measured figures and the date in its docstring. `works_requests`
takes a query into a request only while the joined search stays within it **and** the URL within
`MAX_URL_CHARS` (kept: an accented search reaches it first). The split is greedy in order, so it is the
fewest. On the committed taxonomy (1.6.0), `--max-results 200`:

| Search | Queries | Requests a page | Queries per request | Search characters |
|---|---|---|---|---|
| NHI politics DA link, `national health insurance` | 37 | 2 (was 1, refused) | 24, 13 | 1,473, 795 |
| every other DA's link search on the NHI preset | 7 or 8 | 1 | all | 337 to 444 |
| politics DA link, no topic | 7 | 1 | 7 | — |

The 24/1,473 split is the operator's measured accepted request exactly.

### The fallback (ruling 3, as amended by the PM's Q4)

A request whose **first page** is refused with 400 is split in halves (the first half takes the odd
query), each asked. A half refused beside an answered half is split again, until a single query is
refused, which fails as it does today (`HTTP 400: the provider refused the request`). When both halves
are refused the split stops and every query of that request fails as a 400. A later page's 400 keeps
the pages read (partial, as today); any other 4xx is not split; a 429 fails the whole call. Each split
logs one line on the protected logger, counts only:
`openalex: a joined request of 8 queries was refused with HTTP 400 and split in halves: 6 more requests, 7 queries answered, 1 refused`.

**The most requests a page:** one refused query of n costs at most 1 + 2·⌈log₂ n⌉ (pinned for n = 2, 3,
8, 37: 3, 5, 7, 13, the maximum over every position of the refused query); a refusal not about size
costs 3 (pinned for n = 2, 8, 37). With the measured rule a joined request should not be refused for
size at all; the fallback is for a limit not yet measured.

### A query asked alone (ruling 4, Q1 to Q3)

`asked_alone(text)`: an odd number of `"`, a parenthesis unbalanced by count or closed before it opens
(counted inside quotes too: asking alone is never wrong, only dearer), or an upper-case `AND`, `OR` or
`NOT` as a word of its own (bounded by spaces, parentheses, quotes or the ends) outside a quoted phrase.
Such a query is a request of its own, as typed, after its window's joined requests; it applies to every
query, typed, templated or the model's. In a search of more than one query each one carries a note,
and the footer's OpenAlex line reads, for example:

`openalex: ok, 21 results from 7 queries: not counted as partial: 7 queries asked alone, not joined: an unbalanced parenthesis or double quote, or an AND, OR or NOT`

A one-query search is unchanged and carries no note. Other providers are unchanged.

**The cost (Q3), measured with `works_requests` on the committed taxonomy:** every reviewed politics
link template carries the typed query, and the 30 crossed ones carry the resolution's words instead.
So `national health insurance (reform` on the NHI preset is 7 lone requests plus the 30 crossed queries
joined as 23 and 7: **9 requests a page, 18 for `--max-results 200`** (2 a page without the
parenthesis). Without a topic it is 7 a page, where it was 1.

### Shown failing first

* **Detection, lone queries and fallback** (`a9942ab`, a skeleton whose `asked_alone` says never):
  `hard_stop.py 115 … pytest test_openalex.py -n 0` → 27 failed, 180 passed. The 13 "asked alone" cases at
  `assert False is True`; the two lone-query tests on their request lists; the split tests at request
  counts (`assert 1 == 3`, `2 == 4`) or by today's `ProviderUnavailable` on the whole request where the
  test expects answers; the log test (`[] == [...]`). Passing at red, as today's behaviour: the 8 joined
  cases, a one-query search with no note, a single 400 failing in one request, a 403 not split, and a
  later page's 400 kept partial.
* **The CLI** (the two new tests, with `openalex.py` put back to `a9942ab`'s): 2 failed, on the
  requests sent (`['(health ins...h Democrats)'] == ['health insu...blicans', ...]`).
* **The measured rule** (`23ce710`'s tests against HEAD's URL-only `openalex.py` with `MAX_SEARCH_CHARS`
  defined but unused): 5 failed of 440 over `test_openalex.py`, `test_query_expansion.py` and
  `test_search_command.py`: the 32-query search (`['1', '2'] == ['1', '2', '1', '2']`), the 96-query
  split (search over 1,500), the 1,501-character boundary (`1 == 2`), t16's preset pin
  (`('policy-2026-27-nhi', 'politics-da', [37])`) and t16's CLI test. Passing at red: the 1,500 boundary
  (one request either way) and the accented URL (today's URL rule splits it).

### Planted breaks

Each was one replacement in the committed `openalex.py`, run against `test_openalex.py` and
`test_search_command.py` (and `test_query_expansion.py` for the rule), and restored with `git checkout
HEAD --`. No Hypothesis property is involved.

| Planted break | Caught by |
|---|---|
| Detection: an odd number of quotes ignored | 2 detection cases, the lone-quote request test |
| Detection: a parenthesis closed before it opens ignored | `health) insurance (reform` |
| Detection: an unclosed parenthesis ignored | detection, the lone-query request test, the CLI test |
| Detection: operators in any case | `Medicare or Medicaid`, `and not or` |
| Detection: operators inside a quoted phrase counted | `"Medicare OR Medicaid"` |
| Detection: operators inside other words | `Oregon ANDROID NOTICE ORBIT` |
| A query asked alone joined anyway | 2 request tests, both CLI tests |
| No note on a query asked alone | the request tests, both CLI tests |
| The note on every query | 2 request tests |
| Never split | every split test, by today's `ProviderUnavailable` (the behaviour the fallback replaces) |
| Both-halves stop removed, first half | `assert 7 == 3`, `13 == 3`, the deeper-stop and the 503-beside tests |
| Both-halves stop removed, second half | `7 == 3`, `11 == 3`, the deeper-stop test |
| No recursion into a refused half | the order test, the bound tests |
| Any 4xx split, not only 400 | the 403 test (`3 == 1`) |
| A later page's 400 split too | the later-page test |
| The split not logged | the log test |
| Rule: the search length not checked | t16's pins, the 32 and 96 tests |
| Rule: the URL length not checked | the accented test |
| Rule: a search of exactly 1,500 refused | the 1,500 boundary (`2 == 1`) |
| Rule: the limit at 1,400 | t16's pin (`[22, 15]`), the boundary, t16's CLI test |
| Rule: the limit at 1,600 | t16's pin (`[26, 11]`), the 1,501 boundary, t16's CLI test |
| **Halves split at the floor instead of the ceiling** | **not caught: equivalent.** Both of the PM's bounds hold either way (the odd query in the second half instead of the first); only which half is larger differs, which no ruling names. Left unpinned rather than pin an arbitrary choice. |

### Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | 113 test files selected; stopped at the 115-second limit (exit 124 from the stop) at 59% with no failure mark. **Over two minutes, so under agreement 10 it is left to the pull request's `ci` check, not handed over.** |
| The changed test directories and the always-run list: `hard_stop.py 115 … pytest -n auto -m "not slow and not live and not partition_proof"` over `packages/debate_core/tests/integrations/discovery`, `test_query_expansion.py`, `test_federated_search.py`, `test_federated_search_articles.py`, the CLI's `test_search_command.py`, `test_search_presenter.py`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py`, `tests/architecture`, `tests/specs` | `1797 passed in 25.54s` |
| `uv run ruff format --check .` / `uv run ruff check .` | `2061 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 74 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 669 files, 41 epics, 606 tasks, 22 releases` |

## Files changed

* **`debate_core.integrations.discovery.openalex`:** `MAX_SEARCH_CHARS` and the split by it,
  `asked_alone` and `asked_alone_note`, lone requests in `works_requests`, the halving fallback
  (`_ask`, `_halves`, `_attempt`, the private `_Refused` and `_Asked`), the notes, the split's log line,
  and the module docstring. `resilience.py` and `pace.py` (v1-e07-t22's) are untouched.
* **`packages/debate_core/tests/integrations/discovery/test_openalex.py`:** the detection, lone-query,
  fallback, bound, boundary and accented tests; t10's 32-query and 96-query tests (Deviations 1).
* **`packages/debate_core/tests/application/test_query_expansion.py`:** t16's preset pin (Deviations 2).
* **`packages/debate_cli/tests/test_search_command.py`:** the two footer tests; t16's NHI search pin
  (Deviations 2).
* **The spec:** the PM's widening and answers as a comment above the description, priority 1, phase
  `Succeeded`.

## Deviations from the spec

1. **v1-e08-t10's pins change, as ruling 2 requires.** `test_a_12_or_32_query_search_is_one_request_per_page`
   becomes `…_12_query_search_is_one_request_per_page_and_a_32_query_search_two`: t10 held 32 queries
   in one request by the URL alone, which is not what OpenAlex limits. The 96-query split test checks
   greediness by search length.
2. **v1-e08-t16's pins hold against the measured rule.** The preset pin becomes
   `test_every_da_link_search_on_a_committed_preset_is_the_fewest_openalex_requests_per_page`: politics
   DA on NHI `[24, 13]` (first request 1,473 characters, the operator's figure), every other DA one
   request, every request within both limits. Its CLI test expects the two joined requests.
3. **The footer's line goes through `ProviderResponse.notes`**, so it reads "not counted as partial: 7
   queries asked alone, …", the presenter's existing rendering. A field of its own would change
   `debate_core.domain`, outside this task's packages. The `notes` field's docstring there ("today, only
   a feed that has failed on every read for days") is now incomplete; I did not edit it.
4. **`MAX_QUERIES_PER_SEARCH`'s docstring** (`debate_core.domain.argument_taxonomy`) still says 42
   queries fit one OpenAlex request by a 3,500-character URL. Measured, about 24 such queries fit one;
   the 37 are two requests a page. I left the domain file alone (outside the packages); whether 42 still
   stands, and its docstring, is the PM's (Follow-up work).
5. **The measurement ran from a scratchpad script**, not a committed one: it is a one-off with live
   calls, outside the packages. Its full text is in the appendix.
6. **The spec was widened by the PM** (2026-11-12) to fix the regression, at priority 1; recorded in
   the spec's comment, with the PM's answers.

## Decisions and assumptions

**The PM's rulings of 2026-11-12, applied as given** (from the task's start): measure, then stop
once; split by what OpenAlex refuses, each constant with its figures and date; the 400 fallback with
its bound pinned and one log line of counts; a typed query with an unbalanced parenthesis or a bare OR,
AND or NOT sent alone, never joined or rewritten, the footer saying so; other providers unchanged.

**The PM's answers (2026-11-12):**

> Q1: yes. An odd number of double quotes is treated as ruling 4 treats an open parenthesis: asked
> alone, never rewritten. Q2: yes. Any upper-case AND, OR or NOT word outside a double-quoted phrase
> sends the query alone. Q3: yes. The detection applies to every query of a search, typed, templated or
> the model's; the cost (the lone requests plus the joined rest per page) goes in the report. Q4:
> amended. The split recurses only into a half that is refused while its other half is answered. When
> both halves of a split are refused, stop: the refusal is not about size, and every query of that
> request fails as today, as a 400. … The split happens only on a first page's 400, and a later page's
> failure keeps the pages already read … Pin both bounds by tests, with a mutant on the both-halves stop.

* **The URL cap stays** beside the search cap. Both are checked; on plain text the search binds first.
* **Characters, not bytes.** The limit was measured on plain ASCII text, where they agree. If OpenAlex
  counts bytes for accented text, a request near the limit is refused and the fallback splits it.
* **A half refused beside a half that failed some other way** (a 503, a timeout) is not split further:
  its queries fail as a 400 and the other half's with their own error. The PM's rule recurses only
  beside an *answered* half.
* **The note** is on each query asked alone, with the count, so the footer (which shows each distinct
  note once) says how many. Only in a search of more than one query.
* **A lone query's place:** after its window's joined requests. Order changes nothing an answer holds.

## Operator follow-ups

None required by this task. v1-e08-t16's ac3 (the operator's repeated NHI politics link search and the
coach's labels) waits for this merge, on the next dev build. Its command 2 should now show `openalex`
answering, `queries 37`, from two OpenAlex requests a page.

## Follow-up work

* **`MAX_QUERIES_PER_SEARCH` (42) lost its reason (E08, the PM's).** It stood for one OpenAlex request a
  page; with the 1,500-character limit the 37 are already two. Either the cap is restated as
  requests-a-page, or it goes, and its docstring (Deviations 4) changes with it. `ProviderResponse.notes`'s
  docstring (Deviations 3) wants one line.
* **A paid OpenAlex plan takes longer searches**, by OpenAlex's own message. At 1,500 characters the
  joined search costs about one request a page per 24 templated queries.
* **Characters against bytes** for accented text is unmeasured (above).

## Appendix: the measurement probe

The operator ran it as
`"$(uv tool dir)/debate-cli/bin/python" -I openalex_refusal_probe.py` from `$HOME`, after the
`DEBATE_` check, under `DEBATE_ENV=dev`. `--offline` (a stub, no network) is how it was checked
before the hand-off.

```python
"""What OpenAlex refuses in a joined search (v1-e08-t20's measurement, 2026-11-12).

Run by the operator with the installed build's Python. It rebuilds the 37 queries of
`search "national health insurance" --argument politics-da --need link --topic policy-2026-27-nhi
--max-results 200` with the build's own expansion, and sends joined searches of the first N of them
through the build's own OpenAlex adapter (`OpenAlexProvider._page`), so every request carries exactly
the parameters and headers a search sends. Settings are read as the CLI reads them (`settings_loader`),
so the key comes from the per-user credentials file, or wherever `config show` says it does.

Requests go one at a time, a second apart, at most 13. The probe prints, per request: a label, N, the
URL's length, the search parameter's length, the number of OR groups and the HTTP status; OpenAlex's
error message only when it names a limit and none of its words of four or more letters is a word of
any query. A 429 stops the probe. Nothing else is printed and nothing is written.

`--offline` sends nothing: a stub answers 400 above a made-up number of groups, for checking the probe.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import UTC, datetime

import httpx
from pydantic import SecretStr

from debate_cli import package_version
from debate_cli.build_info import bundled_config_root, settings_loader
from debate_core.application.errors import ProviderError, ProviderRateLimited
from debate_core.application.federated_search_types import ExpansionRequest, SearchRequest
from debate_core.application.query_expansion import (
    ARGUMENT_TAXONOMY_PATH,
    expand_with_templates,
    load_argument_taxonomy,
    provider_queries,
)
from debate_core.application.settings import load_settings
from debate_core.domain import SearchFilters
from debate_core.domain.discovery import ProviderQuery
from debate_core.integrations.discovery.openalex import OpenAlexProvider, openalex_factory, page_count

SIZES = (12, 20, 25, 30, 37)
MOST_REQUESTS = 13
LIMIT_WORDS = ("limit", "maximum", "max ", "too many", "too long", "exceed", "length", "clause", "allowed")


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class Recorder(httpx.AsyncBaseTransport):
    """Passes each request on and keeps the last answer's status, URL length and body."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner = inner
        self.status = 0
        self.url_length = 0
        self.body = b""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.url_length = len(str(request.url))
        response = await self.inner.handle_async_request(request)
        self.body = await response.aread()
        self.status = response.status_code
        return httpx.Response(response.status_code, headers=response.headers, content=self.body, request=request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def offline_stub(request: httpx.Request) -> httpx.Response:
    groups = request.url.params["search"].count(") OR (") + 1
    if groups > 26:
        return httpx.Response(400, json={"error": "Invalid query", "message": "too many clauses, maximum 26"})
    return httpx.Response(200, json={"results": [], "meta": {}})


def the_queries() -> tuple[ProviderQuery, ...]:
    root = bundled_config_root()
    if root is None:
        sys.exit("STOP: this Python is not an installed build (no bundled config)")
    taxonomy = load_argument_taxonomy(root / ARGUMENT_TAXONOMY_PATH)
    request = SearchRequest(
        query="national health insurance",
        filters=SearchFilters(max_results=200),
        expansion=ExpansionRequest(
            argument="politics-da", need="link", topic_id="policy-2026-27-nhi", variables={}, use_model=False
        ),
        topic_id="policy-2026-27-nhi",
    )
    expansion = expand_with_templates(taxonomy, request, now=datetime.now(UTC))
    queries = provider_queries(expansion, request.filters)
    if len(queries) != 37 or len({query.filters for query in queries}) != 1:
        sys.exit("STOP: this build does not expand the search into 37 queries sharing one window")
    return queries


def joined(groups: list[str]) -> str:
    """The adapter's own joining (`joined_search`): one group as it is, several parenthesised and ORed."""
    return groups[0] if len(groups) == 1 else " OR ".join(f"({group})" for group in groups)


def shown_message(body: bytes, query_words: set[str]) -> str:
    try:
        document = json.loads(body)
        message = " ".join(str(document.get(key) or "") for key in ("error", "message")).strip()
    except (ValueError, AttributeError):
        return "message unreadable"
    lowered = message.lower()
    if not any(word in lowered for word in LIMIT_WORDS):
        return "message names no limit"
    if {word for word in re.findall(r"[a-z]+", lowered) if len(word) >= 4} & query_words:
        return "message withheld: it holds a query word"
    return f"message: {message[:200]}"


async def main(offline: bool) -> None:
    queries = the_queries()
    texts = [query.query for query in queries]
    filters = queries[0].filters
    query_words = {word for text in texts for word in re.findall(r"[a-z]+", text.lower()) if len(word) >= 4}
    if offline:
        settings = load_settings(environment="test")
        recorder = Recorder(httpx.MockTransport(offline_stub))
        key: SecretStr | None = SecretStr("offline-key")
    else:
        settings = settings_loader()()
        recorder = Recorder(httpx.AsyncHTTPTransport())
        key = settings.providers.openalex_api_key
        if key is None or not key.get_secret_value().strip():
            sys.exit("STOP: no OpenAlex key reaches this build's settings; run `debate-research config show`")
    build = openalex_factory(settings.http, version=package_version(), clock=Clock(), transport=recorder)
    with_key = build(settings.providers.model_copy(update={"openalex_api_key": key}))
    without_key = build(settings.providers.model_copy(update={"openalex_api_key": None}))
    pages = page_count(ProviderQuery(query=texts[0], filters=filters))
    sent = 0
    print("label n url_length search_length or_groups status")

    async def ask(label: str, n: int, groups: list[str], provider: OpenAlexProvider, page: int) -> int:
        nonlocal sent
        if sent >= MOST_REQUESTS:
            sys.exit("STOP: the probe's request limit")
        if sent:
            await asyncio.sleep(1)
        sent += 1
        search = joined(groups)
        recorder.status, recorder.body = 0, b""
        try:
            await provider._page(ProviderQuery(query=search, filters=filters), page if pages > 1 else None)
        except ProviderRateLimited:
            print(label, n, recorder.url_length, len(search), len(groups), 429)
            sys.exit("STOP: OpenAlex rate-limited the probe")
        except ProviderError as error:
            if recorder.status == 0:
                print(label, n, "-", len(search), len(groups), "no answer:", type(error).__name__)
                sys.exit("STOP: OpenAlex did not answer (a timeout or a transport failure)")
        line = [label, n, recorder.url_length, len(search), len(groups), recorder.status]
        if recorder.status >= 400:
            line.append(shown_message(recorder.body, query_words))
        print(*line)
        return recorder.status

    try:
        refused = {n: await ask("first-n", n, texts[:n], with_key, 1) != 200 for n in SIZES}
        failing = [n for n in SIZES if refused[n]]
        if not failing:
            print("result: no refusal at any size")
            return
        first = failing[0]
        below = max((n for n in SIZES if n < first), default=0)
        if below == 0:
            await ask("one-query", 1, texts[:1], with_key, 1)
        else:
            low, high = below, first
            while high - low > 1:
                middle = (low + high) // 2
                if await ask("first-n", middle, texts[:middle], with_key, 1) != 200:
                    high = middle
                else:
                    low = middle
            first = high
        print("result: largest accepted", low if below else "none", "smallest refused", first)
        words = texts[:first]
        pairs = [" ".join(words[i : i + 2]) for i in range(0, len(words), 2)]
        await ask("same-words-half-the-groups", first, pairs, with_key, 1)
        await ask("same-groups-first-word-only", first, [text.split()[0] for text in words], with_key, 1)
        await ask("no-key", first, words, without_key, 1)
        if pages > 1:
            await ask("page-2", first, words, with_key, 2)
    finally:
        await with_key.aclose()
        await without_key.aclose()
        print("requests sent", sent)


if __name__ == "__main__":
    asyncio.run(main("--offline" in sys.argv[1:]))
```

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
