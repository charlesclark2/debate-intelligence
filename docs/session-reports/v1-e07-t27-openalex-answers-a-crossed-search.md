# Session report: v1-e07-t27-openalex-answers-a-crossed-search

| | |
|---|---|
| Task | `v1-e07-t27-openalex-answers-a-crossed-search` — OpenAlex answers a crossed search instead of refusing every query with HTTP 400 |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t27-openalex-answers-a-crossed-search.yaml`](../../plan_specs/v1/e07-discovery-adapters/t27-openalex-answers-a-crossed-search.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t27-openalex-answers-a-crossed-search` |
| Session status | PARTIAL: the ac3 search ran on dev.413, and its refusal is the one v1-e08-t20 fixed. On dev.445 the probe's seven requests were all answered. Stopped for the PM's second ruling. The Goal stays `InProgress` <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The refused requests were not too long, and the crossed templates add no special characters. Since
v1-e08-t20, the ac3 search goes to OpenAlex as two joined requests per page. They are 24 and 13
queries: 1,473 and 795 search characters, 1,846 and 1,124 URL characters. Their only added
characters are the joiner's own `(`, `)` and ` OR `. The first half the split then sent, 12 queries
and 727 characters, is exactly the request v1-e08-t20's probe saw answered on 2026-11-12. Two things
differ from that day:

- the `select=` now names `keywords`, which v1-e08-t15 added after that measurement;
- OpenAlex's searching documentation was rewritten on 2026-11-13. It now gives one limit only, 8,190
  bytes of URL. The 1,500-character search limit that OpenAlex's own message named on 2026-11-12 is
  gone from it.

The documentation states nothing that explains this refusal, and the old adapter threw away the one
thing that would: OpenAlex's message. So the adapter now keeps that message in the provider's
reasons. It is sanitized (no URL query, no key, one line) and cut to 200 characters, and tests on two
hand-written recordings in OpenAlex's documented `{error, message}` shape pin it. They were shown
failing first, and 8 mutants were run against it. I propose a 7-request probe from the installed
build, which reads the message and isolates the cause, and the fix that follows from each answer.
I stopped there for the PM's ruling.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `openalex-answers-a-crossed-search`: OpenAlex crossed search | In progress | Offline measurement, documentation and the kept message done (`f70b680` red, `54c436a`, `3856438`). The fix waits for the PM's ruling. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the offline measurement and the documentation's limits are recorded, and the proposal is ruled on by the PM before code | NOT RUN | The measurement and the documentation are recorded below. The proposal is under [The proposal](#the-proposal-item-4-for-the-pms-ruling), awaiting the ruling. No fix code is written. The kept message (item 3) is code the PM's brief asked for before the stop ([Deviations](#deviations-from-the-spec) 1). |
| ac2: the ruled fix holds by tests on recorded-shape fixtures shown failing first, and the operator's repeat of v1-e08-t16's ac3 search records openalex with an outcome other than error and results above zero (operator) | NOT RUN | No new fix is needed: the refusal was dev.413's, and t20 fixed it ([The probe on dev.445](#the-probe-on-dev445-operator-2026-11-19)). The mutant that rebuilds the refused request fails 5 existing tests. How ac2 closes, and the repeat, are for the PM's second ruling. |
| Node: `uv run pytest packages/debate_core/tests/integrations/discovery -k openalex` | PASS for today's code | `hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/discovery -k openalex -q` → `232 passed in 2.68s`. Run again once the fix is in. |

## 1. The offline measurement (no call)

I built the search with the committed taxonomy (1.6.0) and the code's own path, as v1-e08-t16's pin
builds it: `expand_with_templates` → `provider_queries` → `works_requests` → `works_parameters` /
`works_url`. The search is `national health insurance`, `--argument politics-da --need link --topic
policy-2026-27-nhi --max-results 200`, at 2026-11-14 18:00 UTC. The discovery and config code is
identical between v1.1.0-dev.439 and this branch's base (`git diff --stat v1.1.0-dev.439 HEAD` over
`integrations/discovery/` and `config/` prints nothing). The script is
`scratchpad/ac3_requests.py`. Its output is shapes only, no topic text.

**The queries.** There are 37, and 30 of them are crossed. All share one window,
`from_publication_date:2021-11-14`. They run 43 to 72 characters (2,054 in all) and 5 to 9 words
(17 have 8, 10 have 7, 6 have 6, 3 have 9 and 1 has 5). **No query has any character other than
letters, digits and spaces.** The crossed templates (`{query} popular with Republicans` and the
like) add words only, with no quotes, parentheses, slashes, colons or commas. `asked_alone` names
none of them.

**The requests**, endpoint `GET https://api.openalex.org/works`, the query riding in `search=` (not
a filter's `.search`):

| Request | Queries carried | Page | `search=` characters | OR groups | Parens | Quotes | URL characters | Other parameters |
|---|---|---|---|---|---|---|---|---|
| 1 | 24 | 1 of 2 | 1,473 | 24 | 24 / 24 | 0 | 1,846 | `filter=from_publication_date:2021-11-14`, `per_page=100`, `page=1`, `select=` 12 fields incl. `keywords` |
| 1 | 24 | 2 of 2 | 1,473 | 24 | 24 / 24 | 0 | 1,846 | as above, `page=2` |
| 2 | 13 | 1 of 2 | 795 | 13 | 13 / 13 | 0 | 1,124 | as above, `page=1` |
| 2 | 13 | 2 of 2 | 795 | 13 | 13 / 13 | 0 | 1,124 | as above, `page=2` |

The special characters in a joined search are only the joiner's: `(` and `)` once per group, and
` OR ` between groups. The largest URL is 1,846 bytes (all ASCII), 23% of the 8,190 bytes the
documentation now states.

**What was sent on 2026-11-14, from the code** (`OpenAlexProvider._ask` / `_halves`). Each request's
first page was refused with `400`, so each was split in halves. Both halves were refused, and the
split stops there by the PM's ruling on v1-e08-t20 ("when both halves are refused the refusal is not
about size"). So six requests went out, all refused, and no page 2 was ever asked:

| Request | Sent | `search=` characters | URL characters |
|---|---|---|---|
| 1 | 24 queries | 1,473 | 1,846 |
| 1, first half | 12 | 727 | 1,052 |
| 1, second half | 12 | 742 | 1,067 |
| 2 | 13 | 795 | 1,124 |
| 2, first half | 7 | 423 | 728 |
| 2, second half | 6 | 368 | 669 |

**Request 1's first half is v1-e08-t20's answered "first 12" exactly.** Its 727 characters match
t20's table row (`first N`, 12, URL 1,041, search 727, status 200) from 2026-11-12. The URL is 11
characters longer now: `%2Ckeywords` in `select=`.

**Why the footer counts 37 failed.** `search_each` records each refused request's reason against
every query it carries. When every request fails it raises the first failure
(`if failures and len(failures) == len(requests): raise failures[0]`).
`FederatedSearchService._ask` catches the `ProviderUnavailable` and gives each of the 37 queries a
status of its own, outcome `error`, with that one reason (`_failed_each`). So yes: **one refused
request fails every query it carries**, and when all of a provider's requests fail, the provider is
`error` for all its queries. The footer counts statuses, one per query, not HTTP requests.

**What v1-e08-t14's search sent when OpenAlex last answered it** (code at t14's merge, `5cbaab2`,
taxonomy 1.3.0, the same search; script `scratchpad/dev342_requests.py` run over a `git archive` of
that commit). That was **12 requests, one query each**: 43 to 57 search characters, 302 to 316 URL
characters, no `OR`, no parentheses, no `page=`, and a `select=` of 11 fields without `keywords`.
The window filter and `per_page=100` were the same. Joining came with v1-e08-t10 (`24daa28`) after
t14, paging with it, and `keywords` with v1-e08-t15 (`2d4a097`). (t14's report says its ac3 ran on
`v1.1.0-dev.342`. That tag, local and on origin, is `f15fd7f`, which predates t14's merge;
`v1.1.0-dev.358` is the merge itself. The label looks like a slip, and the comparison above uses the
merge's code, as the PM asked.)

**What answered and what was refused, side by side:**

| Request | Date | `OR` groups | `page=` | `keywords` selected | Window | Status |
|---|---|---|---|---|---|---|
| t14's 12 single queries | 2026-11-08 | 1 | no | no | yes | 200 |
| t20's probe, first 12 to 24 joined | 2026-11-12 | 12 to 24 | `page=1` | no | yes | 200 |
| t20's probe, 25 or more joined | 2026-11-12 | 25+ | `page=1` | no | yes | 400 "too long (… the limit is 1500)" |
| ac3: 24, 12, 12, 13, 7, 6 joined | 2026-11-14 | 6 to 24 | `page=1` | **yes** | yes | **400** |
| plain `national health insurance`, `--max-results 5` | 2026-11-14 | 1 | no | **yes** | no | 200 |

Offline, the refusal is consistent with four causes, and the operator's probe below tells them apart:

1. `keywords` in `select=` together with a joined search, the one parameter change since 2026-11-12;
2. `page=` with a joined search (the answered plain search sent no `page`, but t20's answered
   requests did);
3. a change OpenAlex made between 2026-11-12 and 2026-11-14 to how it reads `(a) OR (b)` searches
   (its search pages were rewritten on 2026-11-13);
4. a limit OpenAlex added that its documentation does not state.

### The ac3 search ran on dev.413 (found 2026-11-19)

The spec records the ac3 search as run on `v1.1.0-dev.439`. On 2026-11-19 the operator's installed
build was `v1.1.0-dev.413`, installed on 2026-11-12 for v1-e07-t20's Semantic Scholar smoke. Nothing
records an install since then. The probe, run on that build, stopped before sending anything:
`STOP: the first joined request carries 37 queries, not 24`.

dev.413's own code and taxonomy (`git archive v1.1.0-dev.413`, `scratchpad/dev413_requests.py`, no
call) send the ac3 search like this:

| | dev.413 | dev.439 to dev.445 |
|---|---|---|
| Taxonomy, queries, windows | 1.6.0, 37, 1 | 1.6.0, 37, 1 |
| Requests per page | **1**, carrying all 37 | 2, carrying 24 and 13 |
| Search characters | **2,272** (37 OR groups) | 1,473 and 795 |
| URL characters | 2,686 | 1,846 and 1,124 |
| Split limit | `MAX_URL_CHARS` 3,500 only | `MAX_SEARCH_CHARS` 1,500 and `MAX_URL_CHARS` 3,500 |
| A 400 | fails the one request, so all 37 queries | halved, then stops when both halves are refused |
| `keywords` in `select=` | no | yes |
| Added characters | 37 `(` and 37 `)` | the same per request |

On dev.413, then, the search is 2,272 characters, over the 1,500 that OpenAlex's own message named on
2026-11-12. That is the refusal v1-e08-t20 (`daa5563`, first in `v1.1.0-dev.423`) fixed by
splitting, and it gives exactly the recorded `queries 37, failed 37`. If the ac3 search ran there,
the cause is already fixed on dev, and the repeat on dev.445 is the test of it. Which build ran it is
for the operator's saved files to say. `--save` writes the search payload, and from dev.423 on (v1-e08-t15,
`2d4a097`) that payload carries a `narrowing` key that dev.413 never writes. The block is under
[Operator follow-ups](#operator-follow-ups).

**The saved file's answer (operator, 2026-11-19):** `~/Desktop/search-policy-nhi-crossing.json` was
written on `2026-11-14T23:21` and has `narrowing key False`. Its OpenAlex entry reads `outcome error`,
`queries 37`, `failed 37`, `results 0`, `reasons ['HTTP 400: the provider refused the request']`.
The `/tmp` copy is gone. In `v1.1.0-dev.439`, `search.py:262` and `search.py:265` write
`search_payload(...)` to `--save`, and `search_presenter.py:359` always puts `narrowing` in it.
dev.413's presenter has no `narrowing` at all. So a build older than dev.423 wrote the file: the
installed dev.413. The refused request was dev.413's single 2,272-character search, the refusal t20
fixed. The 24-query and 13-query requests measured above for dev.439 have never been sent.

## 2. OpenAlex's documentation (read 2026-11-15)

`docs.openalex.org` answers `301 Moved Permanently` to `help.openalex.org` (its own host), so the
pages below are help.openalex.org. Nothing was fetched from api.openalex.org.

| Page (read 2026-11-15) | Last updated | What it says |
|---|---|---|
| [help.openalex.org/api/searching](https://help.openalex.org/api/searching) and its `.md` source | **13 November 2026** | Boolean `AND`, `OR`, `NOT`, upper case only; words with no operator between them are ANDed; parentheses group; double quotes for an exact phrase; a minus sign does not exclude. **The only stated limit:** "the API accepts at most 8,190 bytes" of the URL (path and query string, percent-encoded); "a long `search=` value … with hundreds of `OR` terms, can go over and return a `400`"; past about 64 KB Cloudflare refuses the request first. The 400's body is shown as JSON: `{"error": "Request URL too long", "message": "Your request URL is 8291 bytes, over the 8190-byte limit … See https://help.openalex.org/api/searching/#large-boolean-queries"}`. The cures are `POST /` with the query as OQL in a JSON body ("no length limit, and returns the same results as the GET"), or splitting the `OR` list and taking the union of IDs. **No limit on characters of `search=`, on OR terms, groups or clauses, or on nesting**; "1,200 `OR` terms in about 3 seconds" is described as speed, not a cap. "1,500" and "plan" do not appear. |
| [help.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities](https://help.openalex.org/how-to-use-the-api/get-lists-of-entities/search-entities) | **13 November 2026** | The same rules. A wildcard on the default stemmed `search` is refused with `400`; `rerank=true` with another `sort`, `group_by`, `sample` or `search.semantic` is `400`; at least 3 characters before a wildcard or `~`; hyphenated and slashed terms are split into words; "a very large search over full text (`search=` …) can still time out". No escaping list. Special characters such as `(`, `)`, `"` and `:` are counted at three bytes each once encoded. "Pages and cursors work as usual." |
| [help.openalex.org/api/paging](https://help.openalex.org/api/paging) | 14 October 2026 | `page` defaults to 1, with no cap of its own; `per_page` is 1 to 100 (200 is deprecated); `page × per_page` ≤ 10,000; cursor paging with `cursor=*`, and "without a key … following `next_cursor` returns a 401". It says nothing of what returns a `400`. |
| [help.openalex.org/api/deprecations](https://help.openalex.org/api/deprecations) | **14 November 2026** | "A `select` that names [a removed field] now returns HTTP 400." Removed: `sustainable_development_goals_aurora` (2 November 2026), and **`volume` on works (14 November 2026)**, the day of the refused search. **None of the 12 fields the adapter selects is listed**, `keywords` included. |
| help.openalex.org/api/select-fields | — | `404 Not Found`, so I could not read what `select=` accepts. |

**So the documentation states no limit that explains the refusal.** Our largest URL is 1,846 bytes,
no field we select is removed, and no query uses a wildcard, `rerank` or a removed parameter. The
1,500-character search limit in `MAX_SEARCH_CHARS` came from OpenAlex's own error message on
2026-11-12 (v1-e08-t20), and the rewritten pages no longer mention it. OpenAlex's message is the
evidence that will say what changed.

## 3. A refusal keeps OpenAlex's own message

`OpenAlexProvider._page` now passes every refusal other than a 429 through `_saying_why`, which
appends OpenAlex's message: `HTTP 400: the provider refused the request; OpenAlex said: <message>`.
`refusal_message(content, secrets=…)` builds it:

- it keeps the JSON `message`, or the `error` when the message is missing or blank;
- a body that is not a JSON object (a proxy's HTML page, nothing at all) gives `None`, and the
  reason stays exactly as before;
- every URL loses its query string (scheme, host and path kept), `api_key=`/`mailto=`/`key=`/`token=`
  parameters and `Bearer` tokens become `***`, and the configured key becomes `***` in any URL
  spelling (`redaction.redact`);
- whitespace runs become single spaces and other control characters are dropped;
- the result is cut at a word boundary to at most `MAX_REFUSAL_MESSAGE_CHARS = 200` characters,
  ending in `...` when cut.

A 429's reason is unchanged (`HTTP 429`), because the backoff and hold pins read it. The halving
logic is unchanged. A refused half now carries the message, so the next refusal of the ac3 search
would print why in the footer, for all 37 queries.

**Fixtures** (hand-written, `packages/debate_core/tests/fixtures/discovery/openalex/`, described in
its README):

- `works_refused_url_too_long.json`: a 400 whose body is the documentation's example: a 324-character
  message, which must be cut to 197 characters plus `...`;
- `works_refused_quoting_the_request.json`: a 400 in the same shape whose message quotes a request
  URL with `search=` and `api_key=`, names the test key bare, and carries a tab and a line break.

**Tests** (`test_openalex.py`, expected strings written by hand from those bodies):

- `test_a_400_keeps_openalexs_message_cut_to_about_200_characters`
- `test_a_400_message_loses_any_url_query_the_key_and_its_line_breaks`
- `test_a_refusal_says_openalexs_message_when_its_body_has_one`, with 9 cases: HTML, error only,
  blank message, runs of whitespace, message not text, not an object, empty, 403, 503
- `test_every_query_of_a_refused_crossed_search_carries_openalexs_message`: the ac3 shape, 37
  queries all refused, so three requests, and the raised reason carries the message
- the secrecy test now also replays the key-quoting refusal across every surface (error, `repr`,
  cause, health snapshot, log lines)

**Shown failing first** (`f70b680`, the tests alone against the unchanged adapter):
`hard_stop.py 115 .venv/bin/python -m pytest …/test_openalex.py -q -n 0 -k "message or refusal_says
or secret_reaches"` → `7 failed, 5 passed`. The 7 are every case that expects a message; the 5 are
the cases that keep today's reason, and the secrecy test. Green after `54c436a`: `12 passed`.

**Mutants** (8, each against the whole of `test_openalex.py`, `-n 0`, bytecode cleared and
`PYTHONDONTWRITEBYTECODE=1`, the file restored and byte-compared after each):

| Mutant | Result |
|---|---|
| URL query not stripped | caught (1 failed) |
| configured key not redacted | caught (1) |
| key not handed to the sanitizer | caught (1) |
| no cut | caught (1) |
| cut at 300 | caught (1) |
| `message` only, no fallback to `error` | caught (2) |
| message not kept at all | caught (7) |
| whitespace runs not collapsed | **survived** the first set (the fixture's tab and line break are single characters). The `runs of whitespace` case was added (`3856438`), and then it was caught (1). |

## The proposal (item 4), for the PM's ruling

**First, read the cause.** I recommend the operator runs the probe below on the installed
v1.1.0-dev.439, before the ruling. It sends seven requests, one second apart, through the build's own
adapter, each changing one thing from the ac3 search's first request. It prints the status and, for a
refusal, OpenAlex's message, sanitized and cut as item 3 does. Its offline run against a stub
(`--offline`) printed the seven rows, and its first row matched the measured request (24 groups,
1,473 characters, 1,846 URL). Each row answers one question:

| Row | Changes | If it alone answers 200 |
|---|---|---|
| `ac3-first-request` | nothing | (it should be refused, with the message) |
| `no-page-parameter` | no `page=1` | cause 2: `page` with a joined search |
| `select-without-keywords` | `select=` without `keywords` | cause 1: `keywords` with a joined search |
| `no-date-window` | no `from_publication_date` | the filter |
| `one-crossed-query` | one crossed query alone, `page=1` | joined searches as such are refused (cause 3) |
| `two-queries-joined` | 2 queries joined, `page=1` | (refused here and answered alone: also cause 3) |
| `plain-control` | the answered plain search | (it should answer 200) |

**Then the fix, by what the probe shows.** Every option keeps the rule that a query that cannot be
sent is counted and named in the reasons, never dropped.

- **A. The message names a limit** (characters, bytes, groups or clauses). Set it in
  `works_requests` as a measured constant beside `MAX_SEARCH_CHARS`, and split under it. This is
  t20's pattern, and the cheapest option.
- **B. `keywords` is refused with a joined search.** Joined requests select without `keywords`, and
  single-query requests keep it. A joined search's results then carry no subjects, so v1-e08-t15's
  narrowing suggestions would come only from single-query searches. That trade-off is the PM's call.
- **C. `page=` is refused with a joined search.** Page 1 is sent with no `page` parameter (OpenAlex's
  default is 1). Later pages use cursor paging (`cursor=*`, then `next_cursor`). The documentation
  says that returns 401 without a key, so without a key a joined search stops at page 1 and names
  the shortfall in its reasons ("page 2 of 2 not asked: cursor paging needs a key").
- **D. OpenAlex refuses `(a) OR (b)` as such now.** Send the joined search as OQL in a `POST /` body,
  which the documentation says "returns the same results as the GET" with no length limit. This is
  a new request shape, and its OQL syntax needs its own reading first (help.openalex.org/api/oql).
  Or, as a stopgap, ask each query alone. For this search that is 37 × 2 = 74 requests, 7.4 times
  today's billed searches. I would not recommend it as more than a stopgap.

**Independent of the cause, and smaller.** When both halves of a request are refused, the split stops
and every query fails with one reason. With the message kept, that reason now says why. I don't
propose changing the stop: asking further would cost requests on a refusal that is not about size.

### Relay to the PM

```text
v1-e07-t27 (OpenAlex refuses the crossed search): stopped for your ruling.

Measured offline (no call): the ac3 search sends 2 joined requests per page, 24 and 13 queries,
1,473 and 795 search characters, 1,846 and 1,124 URL characters. The crossed templates add no
special characters at all; the only ones are the joiner's ( ) and " OR ". Each request was refused,
split in halves, both halves refused, so 6 requests went out and every query failed with one reason.
The first half (12 queries, 727 characters) is exactly t20's probe request answered 200 on 2026-11-12.
The only parameter difference since then: select= now names keywords (v1-e08-t15).
OpenAlex's searching pages were rewritten 2026-11-13: the only stated limit is now 8,190 bytes of
URL (ours: 1,846); the 1,500-character search limit is no longer documented; no OR/group/clause limit;
no selected field is deprecated (deprecations page, 2026-11-14). The docs do not explain the refusal.

Done (your item 3): a refusal now keeps OpenAlex's own message, sanitized (no URL query, no key, one
line) and cut to 200 characters; tests red first, 8 mutants (one survivor, fixed with a case).

Q1. Run the 7-request probe first (seconds; the operator block is in the report), so the fix is
    ruled on OpenAlex's own message rather than on a guess?
    Recommended: yes. It separates keywords-in-select, page=, the date filter and joining as such.
Q2. The fix, by the probe's answer:
    A. a limit named in the message: a measured constant and split under it (t20's pattern);
    B. keywords refused with joined searches: joined requests select without keywords
       (narrowing suggestions then come only from single-query searches);
    C. page= refused with joined searches: page 1 without page=, later pages by cursor, and
       without a key a joined search stops at page 1 with the shortfall named;
    D. joining refused as such: OQL by POST (needs its own docs reading), or each query alone as
       a stopgap (74 requests for this search; not recommended beyond a stopgap).
    Recommended: rule after Q1; A, B or C fit this task's scope; D is likely its own task.
Q3. Keep the split's stop when both halves are refused (no further asking)? Recommended: yes; the
    reason now says why.
```

### The PM's ruling (2026-11-16)

- **Q1: yes.** The operator runs the probe first. It prints OpenAlex's own messages, sanitized as built,
  and each request's status. It never prints a key or a URL query.
- **Q2: decided in advance by the probe's answer.** The session builds without stopping again:
  - a message that names a limit: **A**;
  - `keywords` refused with joined searches: **B**. The guide's narrowing section says suggestions come
    from single-query searches only, and so does the footer when a joined search is why there are none;
  - `page=` refused with joined searches: **C**, with the shortfall named;
  - joining refused as such: **D is its own task**. The session stops and reports, the PM files the
    task, and this one ends at item 3's message and the probe's record;
  - an ambiguous probe, or two causes at once: the session stops for the PM.
- **Q3: yes.** The stop stays when both halves are refused, and the reason now says why.

How I'll read the probe's rows against the ruling:

| Probe rows | Reading | Next |
|---|---|---|
| `ac3-first-request` 400 with a message naming a size, group or clause limit | a limit | A |
| 400, and only `select-without-keywords` answers 200 | `keywords` with joining | B |
| 400, and only `no-page-parameter` answers 200 | `page=` with joining | C |
| 400, `one-crossed-query` 200, `two-queries-joined` 400, and the variants of the 24-query request still 400 | joining as such | stop: D is the PM's new task |
| more than one variant answers 200, only `no-date-window` does, `ac3-first-request` answers 200, or `plain-control` is refused | ambiguous, two causes, or OpenAlex has changed again | stop for the PM |

## The probe on dev.445 (operator, 2026-11-19)

The operator installed `v1.1.0-dev.445`. The installer's last line was `Installed debate-research
1.1.0.dev445 from v1.1.0-dev.445 at /Users/charlesclark/.local/bin/debate-research.`, and the check
table read `Integrations failing none`. The tag check then printed `v1.1.0-dev.445`. The probe:

```text
label or_groups search_length url_length status
ac3-first-request 24 1473 1846 200
no-page-parameter 24 1473 1839 200
select-without-keywords 24 1473 1835 200
no-date-window 24 1473 1804 200
one-crossed-query 1 72 349 200
two-queries-joined 2 100 385 200
plain-control 1 25 251 200
requests sent 7
exit 0
```

**Every request was answered, the ac3 search's own first request included.** Today's code sends a
request OpenAlex accepts. The refusal of 2026-11-14 was dev.413's single 2,272-character request (see
[The ac3 search ran on dev.413](#the-ac3-search-ran-on-dev413-found-2026-11-19)), which v1-e08-t20's
split already fixed. None of the ruling's branches A to D applies, so, as my reading table says, the
session stops for the PM.

**The mutant that rebuilds the refused request** (item 5). I deleted `_fits`' search-length check
(`openalex.py:526` to `527`), so the ac3 search is again dev.413's one request of 37 queries. Its
2,686 URL characters still fit `MAX_URL_CHARS`. I ran `hard_stop.py 115 pytest
packages/debate_core/tests/integrations/discovery packages/debate_core/tests/application/test_query_expansion.py
packages/debate_cli/tests/test_search_command.py`, and got `5 failed, 1456 passed in 8.45s`:

| Test (line) | Failure |
|---|---|
| `test_openalex.py:975` | `assert 1 == 2` |
| `test_openalex.py:935` | `['1', '2'] == ['1', '2', '1', '2']` |
| `test_openalex.py:954` | `assert False` |
| `test_query_expansion.py:1819`, the per-preset pin of every DA's link search | `('policy-2026-27-nhi', 'politics-da', [37])`, which is the ac3 search itself |
| `test_search_command.py:860` | the joined `search=` list differs |

Then I restored the file with `git checkout --` and checked it with `git diff --quiet`. So t20's tests already
refuse the request OpenAlex refused, on recorded-shape and hand-written data. No new fix code is
needed for it.

### Second relay to the PM (2026-11-19)

```text
v1-e07-t27 (OpenAlex refuses the crossed search): second stop. The refusal was dev.413's, and t20 fixed it.

Found: the ac3 search of 2026-11-14 ran on dev.413, not dev.439. Its saved file (written 2026-11-14
23:21) has no "narrowing" key, which every build from dev.423 writes into --save, and the Mac stayed
on dev.413 (installed 2026-11-12) until today. On dev.413 the search is ONE request of all 37 queries,
2,272 search characters, over the 1,500 OpenAlex named on 2026-11-12, with no halving, so one 400
failed all 37. v1-e08-t20's split (dev.423 on) is the fix, and the 24/13 requests I measured had
never been sent.
Probe on dev.445 (installed today): all 7 requests answered 200, including the ac3 search's own
first request (24 groups, 1,473 characters, 1,846 URL). None of your branches A to D applies.
Mutant that rebuilds the refused request (_fits' search-length check deleted): 5 existing tests fail,
including the per-preset pin ('policy-2026-27-nhi', 'politics-da', [37]). Restored.
Item 3 (OpenAlex's message kept, sanitized and cut) is done and stays.

Q1. Close this task with no new fix code: item 3, this record, and the mutant against t20's tests
    standing for ac2's "tests shown failing first"? That means amending ac2 to say so, and the spec's
    description to say dev.413.
    Recommended: yes. A new fix would guard a request that is already guarded.
Q2. The closing repeat (v1-e08-t16's ac3 search, OpenAlex's entry and the result count only): run it
    now on dev.445, or after this merge?
    Recommended: now. dev.445 carries the split, and item 3 changes only a refusal's text. If OpenAlex
    answers, ac2 is recorded before the PR. The block is in the report.
Q3. v1-e08-t16's ac3 sheet was built from a dev.413 search with OpenAlex at error and 0 results. Make it
    again from the dev.445 repeat? Its command 3 takes the new file names.
    Recommended: yes. The repeat saves to a new Desktop file and keeps the dev.413 one.
Q4. Small items:
    (a) MAX_SEARCH_CHARS' docstring: say the 2026-11-13 pages no longer state 1,500, and that a
        1,473-character request was answered on 2026-11-19;
    (b) the cutover runbook's install success text is stale (the installer now ends with
        "Installed debate-research ... at ...");
    (c) t14's report names dev.342 for its ac3, but dev.358 is the merge;
    (d) a record's build comes from the operator's printed tag, never from the newest release.
    Recommended: (a) in this task, since it is a docstring in scope; (b) and (c) filed or folded in;
    (d) yours.
```

## Files changed

- `packages/debate_core/src/debate_core/integrations/discovery/openalex.py`: `refusal_message`,
  `MAX_REFUSAL_MESSAGE_CHARS` and `_saying_why`, so a refusal keeps OpenAlex's message. The module
  docstring says so.
- `packages/debate_core/tests/integrations/discovery/test_openalex.py`: the tests above.
- `packages/debate_core/tests/fixtures/discovery/openalex/`: the two refusal recordings and their
  README entries.
- `openalex.py`'s `MAX_SEARCH_CHARS` docstring: the rewritten pages no longer state the limit, which still binds (ruling Q4a).
- `docs/session-reports/v1-e07-t27-openalex-answers-a-crossed-search.md`: this report.

## Checks run before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` | 128 test files |
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run --slow` | Stopped at its 115-second limit (exit 124) at 53%, with no failure mark. **Over two minutes, so under agreement 10 it is left to the pull request's `ci` check**, not handed over. |
| `hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/discovery packages/debate_core/tests/application/test_query_expansion.py tests/architecture tests/specs -n auto -m "not live"` | `1676 passed in 10.42s` (the changed test directory, the expansion tests that pin the OpenAlex split, and the always-run list) |
| `hard_stop.py 115 .venv/bin/python -m pytest packages/debate_cli/tests/test_search_command.py packages/debate_cli/tests/commands/test_doctor_providers.py packages/debate_cli/tests/test_daily_command.py packages/debate_cli/tests/test_search_narrowing_presenter.py -n auto -m "not live"` | `202 passed in 7.37s` |
| `uv run ruff format --check packages` / `uv run ruff check packages` | `1200 files already formatted` / `All checks passed!` |
| `uv run pyright packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run scripts/validate_specs.py` | `OK: 690 files, 41 epics, 627 tasks, 22 releases` (the Goal left `InProgress`) |
| `uv run scripts/check_command_blocks.py --base HEAD` | `OK: no # comments in 736 shell code blocks in 262 Markdown files (1 session reports changed since HEAD)` |

## Deviations from the spec

1. **The kept message (item 3) is code written before the PM's ruling.** ac1 says "ruled on by the PM
   before code". The PM's brief of 2026-11-15 orders item 3 before item 4's stop, and the spec's
   description asks for it before "Propose the fix … and stop". I read "code" in ac1 as the fix's
   code, and wrote none of it.
2. **The session read OpenAlex's documentation itself** (WebFetch, help.openalex.org only), as the
   PM's brief asked. My standing note says every live fetch is the operator's; the brief's explicit
   instruction is narrower and later. `docs.openalex.org` redirects to `help.openalex.org`, so the
   citations are that host. Nothing was fetched from api.openalex.org.
3. **The message falls back to the JSON `error`** when `message` is missing or blank. The brief says
   "its JSON message field when there is one". The error is a short title ("Invalid query"), and it
   still says more than the bare status.
4. **The spec's premise names the wrong build.** The spec says the ac3 search of 2026-11-14 ran on
   `v1.1.0-dev.439`. Its saved file has no `narrowing` key, so a build older than dev.423 wrote it,
   and the Mac was on dev.413 until at least 2026-11-19
   ([The ac3 search ran on dev.413](#the-ac3-search-ran-on-dev413-found-2026-11-19)). The refusal it
   recorded is the one v1-e08-t20 already fixed. Whether this task still needs a fix beyond item 3
   is for the PM, once the probe has run on dev.445. The spec text is left as it is, for the PM to
   amend. The PM's ruling of 2026-11-19 (Q1): the PM amends the description's dev.439 to dev.413 in
   the next batch.
5. **ac2's "ruled fix … shown failing first" is met with no new fix code** (PM ruling, 2026-11-19,
   Q1). The refused request was dev.413's, and v1-e08-t20's split already refuses it. Three things
   stand for ac2's tests:
   - item 3 (OpenAlex's message kept, sanitized and cut; red first in `f70b680`);
   - this record;
   - the mutant against t20's tests: with `_fits`' search-length check deleted, 5 existing tests fail,
     the per-preset pin among them ([The probe on dev.445](#the-probe-on-dev445-operator-2026-11-19)).

   The PM amends ac2's wording in the next batch. Its operator half, the repeat on dev.445, is
   recorded under the closing check.

## Decisions and assumptions

- **Only a non-429 refusal carries the message.** A 429's reason is pinned by the backoff, hold and
  daily-budget tests. A spent budget already reads as a rate limit.
- **The cut is at a word boundary**, at most 197 characters plus `...`, so at most 200 characters.
- **A URL's path is kept and only its query dropped.** A key travels in the query (`api_key=`), never
  in the path, and the documentation's own links (`…/api/searching/#large-boolean-queries`) stay
  readable.
- **Sanitizing is in the adapter as well as the wrapper.** `ResilientProvider` already redacts
  configured values, but the adapter's own tests run it unwrapped.

## Operator follow-ups

**First: which build wrote the ac3 search's files** (seconds, reads two local files, sends nothing)

Where: your Mac, any terminal. It prints each file's time, whether it has the `narrowing` key
(`True` means dev.423 or later, `False` dev.413 or earlier) and OpenAlex's provider entry. It prints no
titles and no queries.

```bash
cd "$HOME" && python3 -I -c 'import datetime, json, os, sys; [print(p, "missing") if not os.path.exists(p) else (lambda e: (lambda d: print(p, "written", datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="minutes"), "narrowing key", "narrowing" in d, "openalex", [x for x in d.get("providers") or [] if x.get("provider") == "openalex"]))(e.get("data") or (e.get("error") or {}).get("details") or e))(json.load(open(p))) for p in sys.argv[1:]]' "$HOME/Desktop/search-policy-nhi-crossing.json" /tmp/search-policy-nhi-crossing.json
```

**Now (ruled, Q1): the refusal probe** (seconds, 7 OpenAlex requests)

Where: your Mac, any terminal, with the installed v1.1.0-dev.439 or later. The probe is
`openalex_crossed_refusal_probe.py` in this session's scratchpad. Its full text is in the
[appendix](#appendix-the-refusal-probe), in case the scratchpad has been cleared. It prints, per
request, a label, the OR groups, the search length, the URL length and the status, and for a
refusal, OpenAlex's message with any URL query and the key removed. It writes nothing and stops on a
429. The first command checks the build:

On 2026-11-19 the installed build was `v1.1.0-dev.413`. That build predates v1-e08-t15's `keywords`
(`2d4a097`) and v1-e08-t20's split, so it does not send the measured request. The newest dev
pre-release, `v1.1.0-dev.445`, does. `git diff --stat v1.1.0-dev.439 v1.1.0-dev.445` over
`integrations/discovery/`, `config/`, `query_expansion.py`, `federated_search.py` and `build_info.py`
prints nothing. It is installed first, the runbook's way (`scripts/install_channel.sh`,
[caselist-scheduled-sync.md](../runbooks/caselist-scheduled-sync.md), "Checking an installed
build"), from this task's worktree, whose installer is the same as dev.445's:

```bash
cd "$HOME/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e07-t27-openalex-answers-a-crossed-search" && scripts/install_channel.sh v1.1.0-dev.445 2>&1 | tail -5
```

Then the check, which should print `v1.1.0-dev.445`:

```bash
debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])'
```

Then the probe:

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && env DEBATE_ENV=dev "$(uv tool dir)/debate-cli/bin/python" -I /private/tmp/claude-501/-Users-charlesclark-Documents-debate-debate-intelligence-tool-debate-intelligence-worktrees-v1-e07-t27-openalex-answers-a-crossed-search/38734070-724b-4af5-8dc6-512fa87922e2/scratchpad/openalex_crossed_refusal_probe.py; echo "exit $?"; fi
```

Success looks like seven rows and then `requests sent 7`, with `ac3-first-request` at `400`
followed by OpenAlex's message, and `plain-control` at `200`. Paste the rows back. A `STOP:` line
ends the probe early: paste it as it is.

**The closing check (ac2): v1-e08-t16's ac3 search repeated, on dev.445 or later** (under a minute)

Ruled (Q2, 2026-11-19): now, on dev.445, before the PR. Only OpenAlex's entry and the result count are recorded. It makes the same
live calls as v1-e08-t16's ac3: OpenAlex, the publisher feeds, Crossref, the Federal Register and
GovInfo. It writes only to dev's local data directory, to a new Desktop file (the dev.413 file is
kept as evidence) and to `/tmp`. It prints the error code, whether the payload has `narrowing` (a
build from dev.423 on), the result count and OpenAlex's provider entry. It prints no titles. Where:
your Mac, any terminal.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && env DEBATE_ENV=dev debate-research --json search "national health insurance" --argument politics-da --need link --topic policy-2026-27-nhi --max-results 200 --save "$HOME/Desktop/search-policy-nhi-crossing-dev445.json" > /tmp/search-policy-nhi-crossing-dev445.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); r = e.get("error") or {}; d = e.get("data") or r.get("details") or {}; print("code", r.get("code"), "narrowing key", "narrowing" in d, "results", len(d.get("results") or [])); print("openalex", [p for p in d.get("providers") or [] if p.get("provider") == "openalex"])' /tmp/search-policy-nhi-crossing-dev445.json; fi
```

Success looks like `exit 0` or `exit 6`, then `narrowing key True` and `results` above zero, and
OpenAlex's entry with an outcome other than `error` and `results` above zero. `exit 6` with
`SEARCH_PARTIAL` is expected, because Crossref cannot reach all 37 queries (v1-e08-t16 ruling 3A).
The summary line was run on two invented envelopes in the session scratchpad.

**v1-e08-t16's ac3 sheet, made again from the dev.445 repeat** (ruling Q3, seconds, then the coach's
time)

Where: the same terminal, after the closing check saved its file. It is v1-e08-t16's command 3 with
new file names. The dev.413 files stay as they are. It writes `labels-policy-nhi-crossing-dev445.csv`,
for the coach, and `key-policy-nhi-crossing-dev445.csv`, for the scoring session only.

```bash
python3 -I -c 'import csv, json, sys; d = json.load(open(sys.argv[1])); r = d["results"]; top = {x["rank"] for x in sorted(r, key=lambda x: x["rank"])[:10]} | {x["rank"] for x in sorted(r, key=lambda x: x["provider_order"])[:10]}; rows = sorted((x for x in r if x["rank"] in top), key=lambda x: ((x["title"] or "").casefold(), x["url"] or "")); s = csv.writer(open(sys.argv[2], "w", newline="")); k = csv.writer(open(sys.argv[3], "w", newline="")); s.writerow(["item", "title", "url", "relevant"]); k.writerow(["item", "rank", "provider_order"]); [(s.writerow([i, x["title"], x["url"], ""]), k.writerow([i, x["rank"], x["provider_order"]])) for i, x in enumerate(rows, start=1)]; print(sys.argv[2], len(rows), "rows; key", sys.argv[3])' "$HOME/Desktop/search-policy-nhi-crossing-dev445.json" "$HOME/Desktop/labels-policy-nhi-crossing-dev445.csv" "$HOME/Desktop/key-policy-nhi-crossing-dev445.csv"
```

Success looks like one line naming the labels file, with between 10 and 20 rows, and the key file. The
coach gets the labels file only, under the criterion of 2026-11-08. The key stays with you until the
coach has answered. The filled labels, the key and the saved search then go to the PM for t16's ac3.

## Follow-up work

- **The cutover runbook's install success text is stale.** [caselist-cutover.md](../runbooks/caselist-cutover.md)
  says `install_channel.sh … | tail -5` ends with a `complete` line and `The build runs on the Python
  at …, which uv manages.` dev.445's installer ends with `Installed debate-research <version> from
  <tag> at <path>.` (`scripts/install_channel.sh:344`), after the check table. I copied the stale text
  into this session's hand-off. The PM edits the runbook in the next batch (ruling 2026-11-19, Q4b).
- **v1-e08-t16's ac3 has to be done again.** Its saved search was written by dev.413 with OpenAlex at
  `error` and 0 results, so the coach's sheet from it had no OpenAlex works, and its nDCG cannot be
  set against v1-e08-t14's. The repeat on dev.445 below serves t16's ac3 and this task's ac2. Ruling
  Q3: t16's sheet is made again from the dev.445 repeat, with new file names. The dev.413 file stays
  as it is, and the dev.413 search's sheet is not labelled.

- **t14's report names the wrong build for its ac3** (`v1.1.0-dev.342`, which predates t14's merge;
  `dev.358` is the merge). The PM adds a correction note in the next batch (ruling 2026-11-19, Q4c).
- **`MAX_SEARCH_CHARS`' docstring** now says that the rewritten pages of 2026-11-13 no longer state
  the limit, and that a 1,473-character request was answered on 2026-11-19 (`72413e6`, ruling Q4a).
- **A recorded build comes from the operator's printed tag** (Q4d), accepted as the PM's practice.

## Appendix: the refusal probe

The operator runs it as `"$(uv tool dir)/debate-cli/bin/python" -I openalex_crossed_refusal_probe.py`
from `$HOME`, after the `DEBATE_` check, under `DEBATE_ENV=dev`. `--offline <checkout>` (a stub, no
network) is how it was checked before the hand-off.

```python
"""Why OpenAlex refuses the crossed search (v1-e07-t27's probe, for the operator).

Run with the installed build's Python (v1.1.0-dev.439 or later). It rebuilds the 37 queries of
`search "national health insurance" --argument politics-da --need link --topic policy-2026-27-nhi
--max-results 200` with the build's own expansion, and sends seven requests through the build's own
OpenAlex adapter (`OpenAlexProvider._page`), so each carries exactly the parameters and headers a
search sends, except for the one thing its label says it changes:

1. ac3-first-request: the first joined request the search sends (24 queries, page=1), as sent.
2. no-page-parameter: the same, without `page=1`.
3. select-without-keywords: the same, without `keywords` in `select=` (v1-e08-t15 added it).
4. no-date-window: the same, without the `from_publication_date` filter.
5. one-crossed-query: the first crossed query alone, page=1.
6. two-queries-joined: the first two queries joined, page=1.
7. plain-control: `national health insurance` alone, per_page=5, no window, as the answered search.

Requests go one at a time, a second apart. A 429 stops the probe. It prints, per request: the label,
the OR groups, the search's length, the URL's length and the HTTP status; for a refusal, OpenAlex's
own `message` (or `error`), with any URL query and the key removed, on one line, cut to 200
characters. Nothing else is printed and nothing is written.

`--offline <repository>` sends nothing and reads the taxonomy from a checkout: a stub refuses every request with `page=` and more than one group, for
checking the probe.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import SecretStr

from debate_cli import package_version
from debate_cli.build_info import bundled_config_root, settings_loader
from debate_core.application.errors import ProviderRateLimited
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
from debate_core.integrations.discovery import openalex

URL_QUERY = re.compile(r"""(\b[a-z][a-z0-9+.-]*://[^\s?#"'<>]*)\?[^\s#"'<>]*""", re.IGNORECASE)
CREDENTIAL = re.compile(r"\b(api_key|mailto|key|token)=[^\s&\"'<>]+", re.IGNORECASE)


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
    search = request.url.params["search"]
    if "page" in request.url.params and ") OR (" in search:
        return httpx.Response(400, json={"error": "Invalid query", "message": "stub: page with OR groups"})
    return httpx.Response(200, json={"results": [], "meta": {}})


def said(body: bytes, key: str | None) -> str:
    try:
        document = json.loads(body)
    except ValueError:
        return "message: none (not JSON)"
    if not isinstance(document, dict):
        return "message: none (not an object)"
    for field in ("message", "error"):
        value = document.get(field)
        if isinstance(value, str) and value.strip():
            text = CREDENTIAL.sub(r"\1=***", URL_QUERY.sub(r"\1", value))
            if key:
                text = text.replace(key, "***")
            text = " ".join("".join(c if c.isprintable() else " " for c in text).split())
            return f"{field}: {text[:200]}"
    return "message: none"


def the_queries() -> tuple[tuple[ProviderQuery, ...], list[str]]:
    root = bundled_config_root()
    if root is None and "--offline" in sys.argv[1:] and len(sys.argv) > 2:
        root = Path(sys.argv[-1])
    if root is None:
        sys.exit("STOP: this Python is not an installed build (no bundled config)")
    taxonomy = load_argument_taxonomy(root / ARGUMENT_TAXONOMY_PATH)
    request = SearchRequest(
        query="national health insurance",
        filters=SearchFilters(max_results=200),
        expansion=ExpansionRequest(argument="politics-da", need="link", topic_id="policy-2026-27-nhi"),
    )
    expansion = expand_with_templates(taxonomy, request, now=datetime.now(UTC))
    queries = provider_queries(expansion, request.filters)
    if len(queries) != 37 or len({query.filters for query in queries}) != 1:
        sys.exit("STOP: this build does not expand the search into 37 queries sharing one window")
    crossed = [q.query for q, e in zip(queries, expansion.queries, strict=True) if (e.template_id or "").count("/") == 3]
    return queries, crossed


async def main(offline: bool) -> None:
    queries, crossed = the_queries()
    first = openalex.works_requests(queries)[0]
    if len(first.answers) != 24:
        sys.exit(f"STOP: the first joined request carries {len(first.answers)} queries, not 24")
    window = first.query.filters
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
    build = openalex.openalex_factory(settings.http, version=package_version(), clock=Clock(), transport=recorder)
    provider = build(settings.providers.model_copy(update={"openalex_api_key": key}))
    plain_key = key.get_secret_value() if key is not None else None
    selected = openalex.SELECTED_FIELDS
    sent = 0
    print("label or_groups search_length url_length status")

    async def ask(label: str, search: str, filters: SearchFilters, page: int | None, groups: int) -> None:
        nonlocal sent
        if sent:
            await asyncio.sleep(1)
        sent += 1
        recorder.status, recorder.body = 0, b""
        try:
            await provider._page(ProviderQuery(query=search, filters=filters), page)
        except ProviderRateLimited:
            print(label, groups, len(search), recorder.url_length, 429)
            sys.exit("STOP: OpenAlex rate-limited the probe")
        except Exception as error:  # noqa: BLE001 - the adapter's private refusal is not a ProviderError
            if recorder.status == 0:
                print(label, groups, len(search), "-", "no answer:", type(error).__name__)
                sys.exit("STOP: OpenAlex did not answer (a timeout or a transport failure)")
        line: list[object] = [label, groups, len(search), recorder.url_length, recorder.status]
        if recorder.status >= 400:
            line.append(said(recorder.body, plain_key))
        print(*line)

    joined = first.query.query
    try:
        await ask("ac3-first-request", joined, window, 1, 24)
        await ask("no-page-parameter", joined, window, None, 24)
        openalex.SELECTED_FIELDS = tuple(field for field in selected if field != "keywords")
        try:
            await ask("select-without-keywords", joined, window, 1, 24)
        finally:
            openalex.SELECTED_FIELDS = selected
        await ask("no-date-window", joined, window.evolve(since=None), 1, 24)
        await ask("one-crossed-query", crossed[0], window, 1, 1)
        await ask("two-queries-joined", openalex.joined_search(queries[:2]), window, 1, 2)
        await ask("plain-control", "national health insurance", SearchFilters(max_results=5), None, 1)
    finally:
        await provider.aclose()
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
