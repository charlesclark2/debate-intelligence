# Session report: v1-e07-t03-crossref-adapter

| | |
|---|---|
| Task | `v1-e07-t03-crossref-adapter` — Crossref adapter |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t03-crossref-adapter.yaml`](../../plan_specs/v1/e07-discovery-adapters/t03-crossref-adapter.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t03-crossref-adapter` |
| Session status | BLOCKED <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

BLOCKED before building, as the PM's brief asked (item 1): Crossref's current documentation
differs from the spec's description of its rate limits, pools and 429 behaviour. The differences,
with their URLs, and the published_at read count (item 2) are below; the questions went to the PM
as one relay prompt on 2026-11-02. No code has been written.

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
  User-Agent format.

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

None.

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
