# Session report: v1-e07-t07-government-adapters

| | |
|---|---|
| Task | `v1-e07-t07-government-adapters` — Government and policy source adapters |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t07-government-adapters.yaml`](../../plan_specs/v1/e07-discovery-adapters/t07-government-adapters.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t07-government-adapters` |
| Session status | BLOCKED: stopped before building, awaiting the PM's rulings <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Stopped before building, as the brief asked (items 1 and 2). Nothing is implemented yet. The docs
show three differences from the spec, and one of them needs a ruling before any adapter is written:
**Congress.gov API v3 has no keyword search**, so the spec's `CongressGovProvider` "bill search" has
nothing to search with. GovInfo's GAO Reports collection stops in September 2008, and CRS reports
are on Congress.gov, not GovInfo. The Federal Register's official API page can't be read from this
session (the site redirects automated readers to a block page), so its limits aren't confirmed.
No pacing is needed for an 11-query search on any source whose limits could be read. The
topic-enablement proposal is below. The relay to the PM bundles these questions.

### API documentation, read 2026-11-02 (public pages only, no API call)

* **api.data.gov**, [developer manual](https://api.data.gov/docs/developer-manual/) (no page date):
  the key goes in the `X-Api-Key` header or the `api_key` query parameter (or HTTP basic auth). The
  default limit is 1,000 requests an hour, with no daily limit listed. `DEMO_KEY` gets 30 an hour and
  50 a day per IP. `X-RateLimit-Limit` and `X-RateLimit-Remaining` come back on every response.
  Going over the limit returns 429 with code `OVER_RATE_LIMIT`. **No `Retry-After` is documented**;
  the page says a blocked key is lifted after an hour. Not found: whether one key's hourly count is
  shared across every api.data.gov API (Congress.gov and GovInfo would share it).
* **Congress.gov API v3**, the
  [README](https://github.com/LibraryOfCongress/api.congress.gov) says 5,000 requests an hour, a
  required key, `limit` 20 by default and up to 250, and JSON or XML.
  [`Documentation/openapi.yaml`](https://raw.githubusercontent.com/LibraryOfCongress/api.congress.gov/main/Documentation/openapi.yaml)
  (info.version `3`) puts the key in the query as `api_key`. `/bill`, `/bill/{congress}` and
  `/bill/{congress}/{billType}` take only `format`, `offset`, `limit`, `fromDateTime` and
  `toDateTime`. Both dates are described as "The starting/ending timestamp to filter by update
  date" (`YYYY-MM-DDT00:00:00Z`), and `sort` is "Sort by update date … updateDate+asc or
  updateDate+desc". **No path in the whole file has a keyword, query or search parameter.** The
  same holds for `/crsreport`.
  [`BillEndpoint.md`](https://github.com/LibraryOfCongress/api.congress.gov/blob/main/Documentation/BillEndpoint.md):
  the bill types are `HR`, `S`, `HJRES`, `SJRES`, `HCONRES`, `SCONRES`, `HRES` and `SRES`. List
  items carry `congress`, `type`, `number`, `originChamber`, `title`, `latestAction {actionDate,
  text}`, `updateDate` and `url`, and no committee.
* **GovInfo**: the [usgpo/api README](https://github.com/usgpo/api) gives 36,000 requests an hour,
  1,200 a minute and 40 a second, on a rolling hour. It requires an api.data.gov key (`api_key` in
  every example), has `POST /search`, and caps `pageSize` at 1,000.
  [Search service overview](https://www.govinfo.gov/features/search-service-overview) (published
  2023-08-15): the body takes `query` (with field operators), `pageSize`, `offsetMark` (`*` first),
  `sorts`, `resultLevel` and `historical`. Each result carries `title`, `packageId`, `granuleId`,
  `lastModified`, `governmentAuthor`, `dateIssued`, `collectionCode`, `resultLink` and
  `download {pdfLink, xmlLink, …}`, and the response carries `count` and `offsetMark`.
  [Finding information](https://www.govinfo.gov/help/finding-info) (updated 2024-02-28):
  `publishdate:range(2008-05-01, 2008-05-15)`, `collection:bills`, `congress:109`, phrases in
  double quotes. [Hearings help](https://www.govinfo.gov/help/chrg): `chrg` runs from the 104th
  Congress to now, and `publishdate` takes `YYYY`, `YYYY-MM` or `YYYY-MM-DD`.
  [GAO Reports help](https://govinfo.gov/help/gaoreports): **an archive frozen on 2008-09-19**;
  newer reports are on GAO's own site. [GovInfo search help](https://www.govinfo.gov/help/search)
  lists `crpt`, `chrg`, `cdoc`, `cprt`, `bills`, `cmr`, `crec` and `fr`, and **no CRS collection**.
  The [Law Library of Congress (2025-03)](https://blogs.loc.gov/law/2025/03/improved-public-access-to-crs-reports-on-congress-gov/)
  puts CRS products on Congress.gov, through its API's `/crsreport`, which has no keyword parameter.
* **Federal Register**: [the API v1 documentation](https://www.federalregister.gov/developers/documentation/api/v1)
  and the [REST API reader aid](https://www.federalregister.gov/reader-aids/developer-resources/rest-api)
  both answered **302 to `unblock.federalregister.gov`**. That page says requests "flagged as
  potentially automated" are blocked because of scraping, and that "programmatic access … is
  limited to … our extensive developer APIs". The Wayback Machine can't be reached from here. Only
  secondary sources were readable, so nothing here is confirmed: `documents.json`,
  `conditions[term]`, `conditions[publication_date][gte|lte]`, `conditions[type][]`, no key, and
  `per_page` up to 1,000 ([CRAN federalregister manual](https://cran.r-project.org/web/packages/federalregister/refman/federalregister.html)).
  None of them gives a rate-limit figure.

### Pacing for an 11-query search (t03's worst case)

None is needed where limits could be read. GovInfo allows 40 a second and 1,200 a minute. Congress.gov
and api.data.gov state only hourly limits, 5,000 and 1,000. Eleven queries at once is within every
stated limit. The hourly budget is what binds: about 90 eleven-query searches an hour at api.data.gov's
default, fewer if Congress.gov and GovInfo share one key's count (not documented). A 429 comes without
`Retry-After`, so the wrapper's 60 s cool-down holds it, and after three 429s the breaker opens. No
pacer is needed, so the shared-pacer follow-up isn't a blocker. For the Federal Register the answer
is unknown until its page is read.

### Topic enablement: what exists (counted at 3d99d67)

* A search names a topic only through `ExpansionRequest.topic_id` (`federated_search_types.py:74`),
  set by `search --topic`. `--topic` is refused without `--argument` and `--need`
  (`commands/search.py:242`). Its ids are `config/argument_taxonomy.yaml`'s `topics:` presets. Today
  there is one, `policy-2026-27-nhi`, the same id as in `config/landscape/topics.yaml`.
* `config/feeds/<topic>.yaml` (`health-insurance`, `politics`) is a different set of names: subject
  lists, not debate topics. The container loads every file (`container.py:1489-1497`), and the `rss`
  and `google_news` providers read every topic's feeds on every search (`feeds_of`). Nothing picks a
  file per search.
* `stamp_build.py check-wheels` requires every committed `config/feeds/*.yaml` in the wheel,
  whatever its name, so a new file or key is bundled without a script change.
* The data-center PF topic is `pf-2026-sep-oct-data-center-moratorium` in `config/landscape/topics.yaml`.
  It ran 2026-09-01 to 2026-10-31 and **ended two days ago**. It has no taxonomy preset and no feed
  file. The November-December PF topic isn't committed anywhere.
* `ProviderHealth.state` is the breaker's (`closed`/`open`/`half_open`). `NOT_CONFIGURED` exists only
  as a call's `ProviderOutcome`, reported for a requested name the registry didn't build
  (`federated_search.py:215-221`), and the search table already prints it as "not configured".
  `DiscoveryProviders` (`application/ports/providers.py:93`) exposes only `providers` and `health()`.

## Plan nodes

<!-- One row per Plan graph node, in the order they were completed. -->

| Node | Status | Notes |
|---|---|---|
| | | |

## Acceptance criteria

<!-- Goal criteria (ac1…) and every node criterion. Status: PASS / FAIL / NOT RUN. -->

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| | | |

## Files changed

<!-- Group by package or directory; one line on why each group changed. -->

## Deviations from the spec

Open until the PM rules (the session's relay of 2026-11-02 asks each one). Nothing is built yet.

1. **Congress.gov can't search by keyword** (the docs above). Proposed: bills come from GovInfo's
   `collection:bills` search, which matches title and text and takes `congress:` and
   `publishdate:range(...)`. The bill identifier (congress, type, number) is read from the BILLS
   package id (e.g. `BILLS-119hr1234ih`), and `CONGRESS_GOV` isn't added. ac1 and ac2 would then
   name two providers. Congress.gov lookups by bill (latest action, committees) become a follow-up.
   Rejected: filtering the newest-updated bills (at most 250 a page) on their titles. It misses most
   relevant bills and costs a request a page.
2. **GovInfo collections**: GAOREPORTS stops in 2008, and CRS reports aren't on GovInfo. Proposed
   default collections: `crpt`, `chrg`, `cprt`, and `bills` if item 1 is accepted. GAO and CRS
   reports go to a follow-up.
3. **Federal Register docs unread.** Either the operator opens the API v1 documentation page in a
   browser and pastes its rate-limit and `documents` search sections, or the PM rules that the
   adapter is built on the secondary-source parameter names and the live smoke confirms them. In
   either case the adapter will treat a 3xx (the block page's 302) as unavailable, naming the host
   it was redirected to. The shared map reads a 3xx as "read it", which would end as a vague
   "unreadable response".
4. **"Health NOT_CONFIGURED"** has no field in `ProviderHealth`. Proposed: a keyless Congress.gov or
   GovInfo isn't built. The registry records it as enabled but not configured, with the reason, and
   the fan-out reports each call to it as `not_configured`, "govinfo: no api.data.gov key
   (DEBATE_PROVIDERS__API_DATA_GOV_KEY)". `health()` is unchanged. This needs `DiscoveryProviders`
   (`application/ports/providers.py`) and `FanOutStage` (`application/federated_search.py`) in the
   packages, beyond ruling 3's "settings only".
5. **Topic enablement** needs a search to name its topic outside `--argument`/`--need`, which is
   a change to `debate_cli/commands/search.py` and `SearchRequest`. Both are outside the packages.
   The proposal and its alternative are in the relay. Either way, a government provider runs only
   when it is in `providers.enabled` **and** the search's topic lists it **and** its key is set.

## Decisions and assumptions

<!-- Choices the spec left open, with the reasoning. -->

## Operator follow-ups

<!-- Commands the operator must run (anything over ~2 minutes), with where to run them, the exact
command, expected runtime and what success looks like. Also GitHub/AWS settings to change. -->

None.

## Follow-up work

<!-- Bugs, gaps or ideas outside this task's scope, each with the task or epic it belongs to.
The PM decides whether they become spec changes or new tasks. -->

None.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
