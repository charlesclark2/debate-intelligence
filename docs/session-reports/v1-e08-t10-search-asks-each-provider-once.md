# Session report: v1-e08-t10-search-asks-each-provider-once

| | |
|---|---|
| Task | `v1-e08-t10-search-asks-each-provider-once` — One search asks each provider once, however many queries the expansion gives |
| Spec | [`plan_specs/v1/e08-research-workflows/t10-search-asks-each-provider-once.yaml`](../../plan_specs/v1/e08-research-workflows/t10-search-asks-each-provider-once.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t10-search-asks-each-provider-once` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

An expanded search now asks each provider once. OpenAlex gets the queries that share their filters
joined as `(q1) OR (q2) …` in one request per page, split before 3,500 URL characters, and paged up
to the search's `max_results` (100 works a page). Each publisher feed is read once and every query
is matched against it. On the recorded fixtures the politics DA link search goes from 7 OpenAlex
requests to 1 and from 56 feed requests to 8 on the committed eight-feed lists; the NHI link search
goes from 12 to 1 and from 96 to 8. Ranks, scores, features, explanations, `provider_order` and the
stored expansion are unchanged. The mechanism is a new optional port, `MultiQuerySearchProvider`:
the fan-out asks such a provider once and it still answers per query, so the stored records and
everything after the fan-out keep their shape. The PM ruled on 2026-11-04 (quoted under Decisions):
the OpenAlex facts, pages up to `max_results`, no looser feed match, and the DOI duplicate as a
follow-up. **Look first at** the one visible change on the fixtures, `matched_on` on one result
(Deviations 3), and the **required** post-merge operator check that the ac6 search still finds the
coach's three works (Operator follow-ups).

Commit ids below are relative to `origin/dev` at `65de162`, after `scripts/task sync`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `search-asks-each-provider-once`: One request each | Done | Two red runs: the fan-out, wrapper and feeds against skeletons (committed, `c7c8e60`), then OpenAlex against today's behaviour (run, not committed). Feeds and fan-out `4264e32`, OpenAlex `02de576`, 19 mutants. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: a search with several expanded queries makes one request per provider (per page), the feed read once, with the same ranked results on the recorded fixtures, by tests counting requests and shown failing first | PASS | Request-counting tests: `test_fan_out_asks_a_provider_that_answers_several_queries_once_with_every_query` and five more fan-out tests, five wrapper tests, `test_feeds_answer_every_query_of_a_search_from_one_read_of_each_feed`, `test_every_query_of_a_search_goes_to_openalex_in_one_joined_request`, `test_a_12_or_32_query_search_is_one_request_per_page` (two pages for `--max-results 200`), the split and paging tests, and the CLI's `test_an_expanded_search_reads_each_feed_once_however_many_queries_it_asks` (1 OpenAlex request, 1 feed read for 7 queries). Shown failing first: below. Same ranked results: the before/after measurement below. |
| Node: `uv run pytest packages/debate_core/tests -k "federated or openalex or feed"` | PASS | `677 passed in 14.25s` after the sync (665 before the OpenAlex tests were added) |

### Shown failing first

* **Fan-out, wrapper and feeds** (`c7c8e60`): skeletons that refuse nothing. `search_each` exists on
  the wrapper and the feed provider but asks one query at a time, and the fan-out still calls
  `search` per query. 16 failed out of 466 (`hard_stop.py 115 … pytest` over the six touched files).
  At first two wrapper tests crashed (the scripted adapter's `search` popped an empty list), so I gave
  the adapter a plain per-query answer and re-ran: all 17 then failed at assertions. They were six
  fan-out tests (`assert [] == [[ProviderQuery…]]`, `assert 0 == 1`), five wrapper tests (`DID NOT
  RAISE`, `assert [] == …`), four feed tests (`{RSS: 3, ATOM: 3} == {RSS: 1, ATOM: 1}`, the log
  lines), and the CLI (`assert 7 == 1`). Passing at red, with why: `resilient()` choosing the wrapper
  (written whole), the widened port test, "each query's answer equals asking it alone" (the skeleton
  asks alone), and the two DOI tests (behaviour dedupe already has).
* **OpenAlex** (run before `02de576`, not committed): `search_each` put back to today's behaviour,
  one request of one page per query, with no attribution. 11 of 168 failed: the joined request
  (`too many values to unpack`), attribution, joining per window, a failing request left partial
  (raised instead), every request failing (`DID NOT RAISE`), a later page partial, the split (`392 >
  3500`), and four paging tests by `KeyError: 'page'`, because the old request sends no `page=`.
  Passing at red, with why: the rate-limit test (the old code raises on a 429 too) and the
  `isinstance` check (the method exists in the skeleton).

### Requests before and after, on the recorded fixtures

`packages/debate_cli/tests/test_search_command.py`'s seams, through a temporary measuring test
(never committed). It ran on HEAD and again with the six pre-task source files restored from
`ead7e72`. "Test feed" is the fixture's one Courier feed. "Committed lists" means the container
builds the registry from `config/feeds/` (eight feeds), and every feed answers with the Courier
fixture.

| Search | Queries | OpenAlex | Feed requests (test feed) | Feed requests (committed lists) |
|---|---|---|---|---|
| `midterm elections --since 2026-09-14` | 1 | 1 → 1 | 1 → 1 | 8 → 8 |
| `health insurance --argument politics-da --need link` | 7 | 7 → 1 | 7 → 1 | 56 → 8 |
| `national health insurance … --topic policy-2026-27-nhi` | 12 | 12 → 1 | 12 → 1 | 96 → 8 |

On all six runs, before and after are identical in the JSON's `expansion` and `status` and in every
result's rank, score, features, explanation, identifiers, providers and `provider_order`, apart from
`article_id` (a fresh ULID on every run). Two things differ on the 7-query search only:
`matched_on` on one result, and OpenAlex's footer count, 21 → 15 (Deviations 3).

**Where the URL line is** (httpx's encoding, `--max-results 200`, page 2): the 12-query NHI search is
one request; the 32-query search (today's twelve plus the five subjects × four party-popularity
templates) is one request (`test_a_12_or_32_query_search_is_one_request_per_page`). Of 96 queries of
that shape, 47 fit one request: the split test's 96 go as 47, 47 and 2.

### How often attribution is ambiguous

Each OpenAlex work goes to the queries whose every word is in its title or abstract, or to every
query of its request when none is.

| Works | Queries | Match one | Match several | Match none (go to all) |
|---|---|---|---|---|
| CLI fixture (`openalex_works.body.json`) | 7 politics link | 1 | 0 | 2 |
| CLI fixture | 12 NHI link | 0 | 0 | 3 |
| Joined fixture (`works_joined.body.json`) | 3 | 2 | 1 | 1 |
| The saved ac6 NHI results, **titles only** (no abstracts in the saved file), counts only | its 7 | 0 | 0 | 200 |
| The same 200 | today's 12 | 0 | 0 | 200 |

On real results, attribution almost always falls back to "every query". No title holds a whole
templated query ("… unpopular with Republicans"), and abstracts can add only some. So live, each
query's record of OpenAlex will mostly be the whole joined answer. Each search logs `openalex: N
queries in M requests; works matching one query a, several b, none c`, so the live share can be read.

### Amendment 1: a looser feed match (measured; the PM ruled build nothing)

Four rules were measured, each counting an entry when any query of the search keeps it:

* strict, today's rule: every word of the query;
* subject: every word of what the debater typed, the template's `{query}`;
* subject plus at least one of the template's own words;
* half the query's words, with stop words and "United States" left out.

Entries are counted once per link and inside each query's window.

| Feeds | Entries in window | Strict | Subject | Subject + a template word | Half the words |
|---|---|---|---|---|---|
| Fixtures, politics link on `health insurance` (7 queries) | 16 | 1 | 11 | 1 | 11 |
| Fixtures, politics link on NHI (12 queries) | 16 | 0 | 0 | 0 | 1 |
| Live feeds as cached on 2026-11-02 (7 of 8 feeds), the ac6 search's 7 queries | 115 | 0 | 0 | 0 | 0 |
| The same live feeds, today's 12 queries | 115 | 0 | 1 | 0 | 3 |

Precision on the fixtures was judged by hand for the politics DA's link, meaning an item about the
politics of health insurance. Strict keeps 1 item, and it is a link item ("Health insurance fight
costs the president political capital"). Subject keeps 11, of which 2 are link items: that one and
"Midterm elections tighten as health insurance costs rise". The other 9 are about health insurance
but not its politics: a Senate subsidy bill, an enrollment drop, Medicaid waivers, Nepal's budget,
last year's rules, India's expansion, mergers, costs explained, employers. The live cache was read
for counts only and no title was printed. Four of its seven files were rewritten by the LD search,
six minutes after the NHI search.

Built: each search logs, per feed read, `rss: <publisher>: N of M entries matched a query`. N counts
entries any query kept (words and window); M is every entry the feed listed.

### Amendment 2: the DOI duplicate (the PM ruled a follow-up)

Dedupe never compares DOIs as written. `ArticleIdentifiers` reduces `https://doi.org/`,
`http://doi.org/`, `https://dx.doi.org/`, `http://dx.doi.org/`, `doi:` and any case to the bare
lowercase DOI before any rule reads it. The new test passes with both hosts and both schemes
(`test_exact_doi_merges_a_dx_doi_org_resolver_url_with_a_doi_org_one`). The operator's saved NHI
search (`~/Desktop/search-policy-nhi.json`, read locally) has exactly one DOI twice, at ranks 46 and
47: one DOI under two different OpenAlex work ids, one at a repository PDF and one at its `doi.org`
URL. Its twelve results with a `dx.doi.org` URL each appear once. Dedupe keeps the pair apart by its
rule that different values of one identifier (here the OpenAlex id) win over every other rule.
`test_exact_doi_does_not_merge_two_openalex_works_that_share_it_under_different_work_ids` pins that,
with invented values. Changing it is a dedupe change, which this task's forbidden list rules out.

### Planted breaks

Each was planted on a committed tree, run against the five touched test files plus
`test_openalex.py` for the OpenAlex ones, and restored with `git checkout HEAD --`.

| Planted break | Caught by |
|---|---|
| Fan-out asks a batching provider one query at a time | 7 tests (fan-out and CLI) |
| Fan-out records a batch's failure on its first query only | 2 fan-out tests |
| Fan-out accepts a short answer | the short-answer fan-out test |
| Wrapper accepts a short answer | the wrapper's short-answer test |
| Wrapper asks a batch one query at a time | 7 tests |
| Registry wraps every adapter as single-query | the CLI's read-once test |
| Feeds read every feed once per query | 3 tests |
| Feeds count matches ignoring the window | both per-feed log tests |
| Feeds stop skipping a link listed twice | 11 tests |
| Feeds mark only the first answer partial | the failing-feed test |
| DOI compared without folding case | 7 dedupe tests, the new `dx.doi.org` test among them |
| OpenAlex never splits a long joined search | the split test |
| OpenAlex joins queries whatever their filters | 3 tests |
| OpenAlex drops a work that matches no query | 27 tests |
| OpenAlex gives every work to every query | 3 attribution tests |
| OpenAlex reads every page after a short one | the short-page and split tests (at assertions, after `2efa218` made an unlisted page an HTTP error rather than a `KeyError` in the test's transport) |
| OpenAlex raises when a later page fails | the later-page test |
| OpenAlex joins without parentheses | 11 tests |
| Removing the `dx.doi.org` prefixes | **not counted**: it crashes at `ArticleIdentifiers` validation (`ValidationError`) instead of failing an assertion. The model refuses an unstripped `dx` DOI outright, which is why dedupe cannot compare one as written. |

### Checks before the report

| Command | Result |
|---|---|
| `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run` | 554 test files selected (the provider port is a hub). Stopped at the 115-second limit (exit 124) at 16%, with no failure mark. **Over two minutes, so under agreement 10 it is left to the pull request's `ci` check, not handed over.** |
| The changed test directories and the always-run list: `hard_stop.py 115 … pytest -m "not slow and not live and not partition_proof"` over `packages/debate_core/tests/{application,integrations/discovery,domain}`, the CLI's `test_search_command.py`, `test_search_presenter.py`, `commands/test_doctor.py`, `test_installation.py`, `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py`, `test_container_factories.py` | `7737 passed in 110.02s` |
| `hard_stop.py 115 … pytest -m "slow and not live" tests/integration/test_e2e_research.py tests/integration/test_e2e_failures.py` (v1-e09-t05's suite, merged first) | `10 passed in 3.30s` |
| `uv run ruff format --check .` / `uv run ruff check .` | clean / clean |
| `uv run pyright packages/debate_core packages/debate_cli` | `0 errors, 0 warnings, 0 informations` |
| `uv run lint-imports` | `Contracts: 20 kept, 0 broken.` |
| `uv run --frozen python scripts/check_thin_handlers.py` | `OK: 72 CLI command and API route handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 619 files, 41 epics, 556 tasks, 22 releases` |

## Files changed

* **`debate_core.application`:** `ports/providers.py` adds `MultiQuerySearchProvider`, and
  `ports/__init__.py` adds its row to the ports table. In `federated_search.py`, the fan-out asks a
  batching provider once and records each query's answer, and a batch's failure or cut-off lands on
  every query. Single-query providers share the same error mapping (`_ask`).
* **`debate_core.integrations.discovery`:** `resilience.py` adds `ResilientMultiQueryProvider` and
  `resilient()`: one hold check, one admission, one timeout and one health record per batch, and a
  short answer or a stranger's name is a failure. `registry.py` wraps through `resilient()`.
  `feeds.py` adds `search_each` (one read, every query matched, per-feed counts logged) and
  `text_matches_terms`. `openalex.py` adds the joined search (`works_requests`, `joined_search`,
  `works_url`, `answered_queries`), paging and partial answers.
* **`packages/debate_core/tests`:** tests for the fan-out, the wrapper, the feeds, OpenAlex and
  dedupe; the widened port test (Deviations 1); the hand-written `works_joined.body.json` and its
  README entry.
* **`packages/debate_cli/tests/test_search_command.py`:** OpenAlex pins become one joined request,
  and the read-once test is added.
* **The spec:** phase `Succeeded`.

## Deviations from the spec

1. **`test_discovery.py`'s "only discovery port" test is widened.** v1-e07-t01's ac1 pinned
   `SearchProvider.search` as the only port method taking a `ProviderQuery`. It now also names
   `MultiQuerySearchProvider.search` and `.search_each`, and asserts that the extension subclasses
   `SearchProvider` and inherits its `search`. Recorded here at the PM's ruling.
2. **A single-query search above 100 results now pages.** The PM's ruling (pages up to
   `max_results`, 100 a page) applies to every OpenAlex request, so `test_a_request_above_100_results_returns_at_most_100`
   became `…_asks_for_pages_of_100_until_it_has_them`. The LD ac6 search (one query, `--max-results
   200`) would now be 2 requests where it was 1, and pools up to 200 works where it pooled 100.
3. **On the 7-query fixture search, two values change, because a provider now returns fewer
   copies.** "Political capital and health insurance reform" matches only the first query's words.
   It now arrives once rather than seven times (once per query), so dedupe has nothing to merge and
   its `matched_on` is `[]` where it was `["doi"]`. OpenAlex's footer count, which counts results
   before dedupe, goes from 21 to 15. Rank, score, features, explanation and `provider_order` are
   unchanged. With live results attribution mostly falls back to every query (above), so footer
   counts there will usually rise: 200 works × 12 queries.
4. The fan-out tests' `wrapped()` helper builds its registry through `resilient()`, as
   `ProviderRegistry.from_settings` now does.

## Decisions and assumptions

**The PM's ruling of 2026-11-04, applied as given:**

> Q1: (a) AND, OR and NOT, upper case only. Words with no operator between them are ANDed, and
> parentheses group clauses … (b) A double-quoted phrase is an exact-phrase match … Keep each query
> unquoted inside its group, as today. (c) The whole request URL is limited to about 4 KB … Split
> before 3,500 characters of URL into the fewest requests that fit, and pin the split by a test. …
> (d) page= with per_page 1 to 100 (default 25), and page × per_page ≤ 10,000. Use page=, not
> cursor … (e) A result carries only relevance_score. Attribute by matching each query's words
> against title and abstract the way the feeds do … A work matching no query goes to every query,
> and one matching several to each … Q2: A. Pages up to the search's max_results, per_page 100. Add
> the operator follow-up as a required step … Q3: build nothing. Keep the per-feed "N of M entries
> matched" log. … Q4: A. … FYIs accepted.

* **One record per query, whichever way a provider was asked.** A batching provider still answers per
  query, so `ProviderStatus`, the footer, `provider_calls`, dedupe, ranking, `provider_order` and
  storage keep their shape. I chose this over one record per request because the spec keeps the
  ranked results and the record as they are, and the PM asked that each result keep the query it
  answered.
* **OpenAlex joins per filters.** Queries with different windows or result caps cannot share a
  `filter=`, so each distinct set of filters is its own joined request (or requests).
* **A failure mid-search.** If one OpenAlex request of several fails, its queries get an empty
  partial answer naming why, and the others stand. If all fail, the first failure is raised. A
  failure on a later page keeps the pages already read and marks the answer partial. A **rate limit
  fails the whole call**, so the wrapper's hold engages as OpenAlex asked.
* **A single query is sent as it is**, unparenthesised, so a one-query search's request is unchanged
  (the recorded fixtures' exact URLs still match).
* **Per-feed log counts** count an entry that any query kept (words and window), against every entry
  the feed listed.

## Operator follow-ups

**Operator command: the ac6 NHI search again, after the merge (required by the PM)** (under a minute)

Where: the operator's Mac, in a fresh shell, with the dev build that contains this task installed
(the next dev pre-release after the merge). It is a live search: about 2 OpenAlex requests (12
queries joined, 2 pages for `--max-results 200`) and one read of each feed. It reads the saved ac6
file `~/Desktop/search-policy-nhi.json` and picks the coach's three relevant works from it by their
ac6 rank and provider position (1st/117th, 9th/441st, 10th/257th). It prints their OpenAlex ids,
never a title, and whether each is in the new results and at what rank.

```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && env DEBATE_ENV=dev debate-research --json search "national health insurance" --argument politics-da --need link --topic policy-2026-27-nhi --max-results 200 --save "$HOME/Desktop/search-policy-nhi-t10.json" > /tmp/search-policy-nhi-t10.json; echo "exit $?"; python3 -I -c 'import json, sys; load = lambda p: (lambda e: e.get("data") or (e.get("error") or {}).get("details") or e)(json.load(open(p))); old, new = load(sys.argv[1]), load(sys.argv[2]); marked = {(1, 117): "A", (9, 441): "B", (10, 257): "C"}; keys = {marked[(r["rank"], r["provider_order"])]: (r["identifiers"]["openalex_id"], r["identifiers"]["doi"]) for r in old["results"] if (r["rank"], r["provider_order"]) in marked}; print("status", new["status"], "results", len(new["results"]), "queries", len((new.get("expansion") or {}).get("queries") or [])); print("providers", [(p["provider"], p["outcome"], p["results"]) for p in new["providers"]]); found = {name: [r["rank"] for r in new["results"] if r["identifiers"]["openalex_id"] == oid or (doi and r["identifiers"]["doi"] == doi)] for name, (oid, doi) in sorted(keys.items())}; [print("work", name, keys[name][0], "rank", ranks[0] if ranks else "MISSING") for name, ranks in found.items()]; print("found in ac6 file:", len(keys), "of 3; present now:", sum(1 for ranks in found.values() if ranks), "of", len(keys))' "$HOME/Desktop/search-policy-nhi.json" "$HOME/Desktop/search-policy-nhi-t10.json"; fi
```

Success looks like: `exit 0` or `exit 6` (6 while v1-e07-t14's unreadable feed stands), `queries
12`, both providers answering, and `found in ac6 file: 3 of 3; present now: 3 of 3`. Paste back the
printed lines. If any work prints `MISSING`, the PM revisits the pool size (Q2).

## Follow-up work

* **A shared DOI overrules differing OpenAlex work ids (OpenAlex's own duplicates), with tests
  (E08).** The PM files it (Q4).
* **Topic-specific feeds are the coach's call.** On the feeds as read on 2026-11-02, no match rule
  kept more than 3 of 115 entries for the NHI link queries. They are general politics feeds holding
  their 10 to 30 latest items. The per-feed "N of M entries matched" log line shows it per search.
* **Google News, Crossref, the Federal Register and GovInfo still ask once per query** (accepted by
  the PM). Each needs its own query-syntax facts before it can join queries. Google News is off on
  both topics, Crossref is not enabled in dev or prod, and the government providers run only on
  topics that list them.
* **OpenAlex receives a query's text as written.** A typed query with an upper-case `AND`, `OR` or
  `NOT`, or a parenthesis, keeps that meaning inside its group, as it did when asked alone. An
  unbalanced parenthesis could now change the meaning of the whole joined search. No committed
  template has one. A guard (escaping, or asking such a query alone) is a small E08 item if the PM
  wants it.
* **`tests/integration` (v1-e09-t05) needs nothing.** Its transport answers every `/works` request
  with the same recorded body and the feed URL with its feed, so one joined request and one feed read
  satisfy it. Its research and failure modules pass under the slow marker (`10 passed`). If a later
  scenario pins OpenAlex's `search=`, the expected value is `(q1) OR (q2) …` over the expansion's
  queries, in order.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-05

**Notes:**

The request counts fall as the spec asked (OpenAlex 12 to 1, the feeds 96 to 8 on the NHI search) and
everything after the fan-out keeps its shape, because a batching provider still answers per query.

1. **ac1 passes.** Two red runs, each failure at an assertion after the two crashing wrapper tests were
   given a per-query answer; the before-and-after measurement on HEAD against the six pre-task files
   shows rank, score, features, explanation and `provider_order` unchanged on every fixture search. 19
   planted breaks caught, and the one that crashed rather than failed (the `dx.doi.org` prefixes) was
   not counted, and it explains why dedupe can't compare a DOI as written.
2. **The PM's Q1 facts are applied as given:** joined `(q1) OR (q2)` per set of filters, unquoted inside
   each group, split before 3,500 URL characters (12 and 32 queries are one request; 96 go as 47, 47 and
   2), `page=` with 100 a page up to `max_results`, and a single query sent unchanged so recorded URLs
   still match.
3. **Deviations accepted.** (1) The widened port test. (2) A single-query search above 100 results now
   pages, as the ruling applies to every request. (3) `matched_on` and the footer count on one fixture
   search: a provider returning fewer copies leaves dedupe less to merge; ranks are unchanged.
   (4) The test helper.
4. **The live attribution finding matters most.** On the saved ac6 results no title holds a whole
   templated query, so all 200 works fall back to "every query". Ranking doesn't depend on which query
   a work answered (its features are the result's own, and provider agreement counts providers), which
   is why ranks hold. But each query's record now carries the whole joined answer, so **the footer's
   OpenAlex count can read 200 x 12**. That is misleading to a student. The PM files a follow-up: a
   batching provider's footer counts distinct works (E08, p3).
5. **The required live check** stands as written, with two changes from the PM: run it from
   `~/Documents/debate/crossref-smoke` (where the OpenAlex key's `.env` is), not `$HOME`; and run it
   after Thursday 2026-11-05's v1-e31-t32 copy, on the next dev build. The PM reads the three works'
   presence **and their ranks** against ac6's 1st, 9th and 10th. A missing work, or a fall well out of
   the first page, reopens the pool size (Q2).
6. **Follow-ups the PM files:** a shared DOI overruling differing OpenAlex work ids (E08, Q4); a guard
   for a typed query with an unbalanced parenthesis or a bare `OR`, which now affects the whole joined
   search (E08, p3); the footer count above. Topic feeds are already decided: the coach approved the
   eight feeds and named nine health-policy outlets, which go to v1-e07-t14.
7. **Closing checks:** the affected set (554 files, the provider port is a hub) is left to `ci`
   (agreement 10); the changed directories and the always-run list (7,737 passed), v1-e09-t05's slow
   research and failure modules (10 passed), ruff, pyright, lint-imports, thin handlers and the specs are
   clean.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`; the live check is
   recorded by the PM when it runs.
