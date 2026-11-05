# Session report: v1-e07-t14-an-unreadable-feed-found-and-fixed-or-dropped

| | |
|---|---|
| Task | `v1-e07-t14-an-unreadable-feed-found-and-fixed-or-dropped` — Roll Call's unreadable feed is fixed or dropped, and one feed that keeps failing no longer marks every search partial |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t14-an-unreadable-feed-found-and-fixed-or-dropped.yaml`](../../plan_specs/v1/e07-discovery-adapters/t14-an-unreadable-feed-found-and-fixed-or-dropped.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t14-an-unreadable-feed-found-and-fixed-or-dropped` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Roll Call's feed is broken at the publisher. The operator's feed check had it answer `HTTP 200` as
`application/rss+xml`, valid UTF-8, opening with an XML declaration, and the XML parser stopped at
`duplicate attribute: line 5, column 3`: an element near the top of the document gives one attribute
twice, which XML 1.0 forbids (§3.1). Our parser was right to refuse it. Roll Call is dropped, as the
PM ruled. The feed check now explains, in counts and statuses only, why a feed that answered could
not be parsed. It also prints each feed's newest date and takes `--url` for candidate feeds.

Built as the PM ruled (option C, three days): a feed failing on every read for three days stops
marking searches partial. It stays named in the footer, `rss: ok, … : not counted as partial: <publisher>
failing since <date>: <reason>`.

The coach's eight starter feeds became `coach_reviewed`, and Roll Call has since been dropped.
Three of the nine health-policy outlets the coach asked for passed the check and were added: Healthcare
Dive, KFF and The Hill's health section. The other six are listed below for the coach, The
Commonwealth Fund as pending.

**Look at first:**

* The `notes` field added to `ProviderResponse` (`debate_core.domain`). The PM approved it, but it makes
  the affected set 544 test files, so that run is left to the pull request's CI (agreement 10).
* KFF's feed covers the whole site, so it carries more than health policy; the coach decides whether
  to keep it.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `an-unreadable-feed-found-and-fixed-or-dr`: Feed fixed | Done | Feed check diagnosis (`c43afa0`). Coach's reviews (`91c6665`). Roll Call dropped and the spec's packages amended (`e5b8471`). The ruled three-day rule (`a470fe0`). Three NHI feeds added (`3c62f10`). |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the cause is found by the operator's feed check, and the feed is fixed, dropped or replaced, by tests on recorded feeds | PASS | The operator ran `feed_check --feeds-dir /tmp/t14-feeds` over `politics.yaml` as it stood at `a6de6ca` (2026-11-05). Roll Call: `unreadable feed: not well-formed XML: ParseError`, with `why: content-type application/rss+xml; charset=UTF-8; content-encoding none; 132718 bytes; starts with an XML declaration; XML error duplicate attribute: line 5, column 3; 0 forbidden control characters; 0 bare ampersands; UTF-8 yes`. The other four feeds answered `HTTP 200` with every entry dated. Cause: a duplicate attribute, invalid XML at the publisher. The entry is dropped, as the PM ruled (whatever the check showed, since its dates carry no zone). `test_the_coach_reviewed_every_committed_feed_and_google_news_is_off` pins the committed list without Roll Call. The diagnosis is covered by `test_feed_check.py` on invented bodies: blank line before the declaration, an HTML page, a control character and a bare `&`, Latin-1, and nine openings. Red against the old check with stubs for the new names: 19 failed, 1 passed (the no-feed-words guard, which an empty stub passes). |
| ac2: what the PM rules for a failing feed's effect on a search's outcome is built with tests shown failing first | PASS | Ruling: option C, N = 3 days, footer and JSON as proposed. `test_feed_failing_since.py` red against the skeleton (`notes` and `failing_since` fields only): **11 failed, 3 passed**, all at assertions. The 3 that passed describe behaviour that already held: every feed failing raises, an unkept failure stays partial, an old cache file reads. `test_search_presenter_standing_feed.py` red against the old presenter: **2 failed** at the footer assertion. The two domain tests, red against the old model: 2 failed (the field did not exist). Green: 190 feed/rss tests, 2 presenter, 66 domain. Planted breaks, each caught: `<` → `<=` at the threshold (3 failed), a `304` keeping the date (1), the note dated by now instead of the first failure (6), the failure date never kept (6). |
| Node: `uv run pytest packages/debate_core/tests/integrations/discovery -k "feed or rss"` | PASS | Run as `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest -q packages/debate_core/tests/integrations/discovery -k "feed or rss"` → `190 passed in 1.86s` |

### Checks before the report

* **Affected set:** `uv run scripts/affected_tests.py` lists **544 test files**, because `debate_core.domain.discovery` reaches almost everything. That is well over two minutes, so it is **not run here** and is left to the pull request's `ci` (agreement 10).
* **Changed test directories and the always-run list**, within the limit: `packages/debate_core/tests/integrations/discovery`, `packages/debate_core/tests/domain`, the CLI's search presenter and command tests, `tests/architecture`, `tests/specs`, `test_app.py`, `test_help_rendering.py` and `test_container_factories.py` → `2500 passed in 23.79s`.
* **Also run:**
  * the application layer's federated search and search index tests → `794 passed in 4.76s`;
  * the SQLite repository's search tests (stored provider statuses) → `22 passed in 2.39s`.
* **Stopped at the limit:** `packages/debate_cli/tests` with `packages/debate_core/tests/application` together hit the 115-second limit and were stopped by `hard_stop` with no result. CI runs them.
* **Static checks:**
  * `ruff format --check .` → 1939 files already formatted
  * `ruff check .` → All checks passed
  * `pyright packages/debate_core packages/debate_cli` → 0 errors
  * `lint-imports` → 20 kept, 0 broken
  * `validate_specs.py` → OK
  * `check_command_blocks.py` → OK
  * `check_thin_handlers.py` → OK
  * `docs_index.py --check-descriptions` → OK

## Files changed

* `packages/debate_core/src/debate_core/integrations/discovery/`
  * `feed_check.py`: the `why:` diagnosis, the newest-date column and `--url`.
  * `feeds.py`: `FeedFetcher` split into `fetch_body` and `read`, so the check keeps a failing body without a second fetch. Also `failing_since` and the three-day rule (`STANDING_FAILURE_AFTER`).
  * `feed_cache.py`: `CachedFeed.failing_since`.
* `packages/debate_core/src/debate_core/domain/discovery.py`: `ProviderResponse.notes`, empty by default.
* `packages/debate_cli/src/debate_cli/presenters/search_presenter.py`: notes become the provider's reasons after `not counted as partial:`, in the footer and the JSON.
* `config/feeds/`
  * `politics.yaml`: Roll Call dropped.
  * `health-insurance.yaml`: three feeds added, plus the outlets left out and why.
  * Every remaining feed is `coach_reviewed`.
  * `README.md`: the check's new output, `--url`, and what a failing feed does to a search.
* Tests:
  * `test_feed_check.py` and `test_feed_config.py`, changed;
  * `test_feed_failing_since.py` and `packages/debate_cli/tests/test_search_presenter_standing_feed.py`, new;
  * two tests in `packages/debate_core/tests/domain/test_discovery.py`.
* The spec: `constraints.packages`, under the PM's dated ruling.

## Deviations from the spec

* **`constraints.packages` amended** as the PM ruled on 2026-11-05: `debate_core.domain`, `packages/debate_cli/src/debate_cli/presenters` and `packages/debate_cli/tests`. A dated comment sits above the list.
* **Work from the PM's context that the spec does not describe:**
  * the coach's reviews (`coach_reviewed` on the starter feeds);
  * the nine requested NHI outlets.

  Both changed only `config/feeds/` and its test, inside the spec's `config` and `packages/debate_core/tests`. The spec's description does not mention them; the PM may want to write them in.

## Decisions and assumptions

* **The diagnosis prints only counts, statuses and the parser's own message.** Expat's messages never quote the document. Its column counts characters, not bytes: a measured multi-byte character before the error shifted a byte lookup. So the check does not name the byte at the position. It counts the usual culprits instead: forbidden control characters, and bare `&` outside CDATA and comments.
* **Where `failing_since` is kept:** in the feed's existing cache entry, so a failing feed's validators and entries are kept with it. A `304` that clears the date rewrites the entry.
  * A `304` to a request that sent no validators (possible once a failure-only entry exists) is still the "nothing cached" failure.
  * An older build reading a cache file with the new key refuses it as not a cached feed and fetches afresh. That costs one unconditional request, nothing more.
* **Only the `rss` provider dates failures.** Google News shares the fetcher but not the rule.
* **Counting failures:**
  * the partial error counts only the new failures (`1 of 3 feeds failed: …`), and each standing failure is its own note;
  * when every feed fails, the first failure is raised however long they have failed, as before;
  * a failure the cache cannot keep is dated now, so it stays new and partial.
* **The per-call JSON (`provider_calls`) is unchanged.** The standing failure is named in the provider's `reasons`, as ruled, so no JSON key is added.
* **The date of the 2026-11-05 feed checks** comes from the PM's dating and the newest entries the check printed (UTC). The operator ran both checks in this session.

## Operator follow-ups

* **Done:** the feed check of the five politics feeds (Roll Call's diagnosis) and of the four candidate URLs, both quoted above and below.
* **Pending: The Commonwealth Fund.** When the operator has the link from its RSS page, run the feed check with that link as the one `--url` value, as in `config/feeds/README.md`, and paste the output back. A pass (200, parsed, dated) adds it as a follow-up change to `health-insurance.yaml`.

## Follow-up work

**For the coach: health-policy outlets asked for and not added** (feed check of 2026-11-05):

| Outlet | Result |
|---|---|
| Healthcare Dive (`https://www.healthcaredive.com/feeds/news/`) | Added: HTTP 200, 10 entries, 10 dated, newest 2026-11-04T19:12Z |
| KFF policy analyses (`https://www.kff.org/feed/`) | Added: HTTP 200, 20 entries, 20 dated, newest 2026-11-05T00:30Z. **KFF's whole site** (polls, fact sheets, analyses), not only health insurance: the coach decides whether that breadth is wanted |
| The Hill, health (`https://thehill.com/policy/healthcare/feed/`) | Added: HTTP 200, 15 entries, 15 dated, newest 2026-11-04T23:26Z |
| Fierce Healthcare (`https://www.fiercehealthcare.com/rss/xml`) | Not added: **HTTP 403** (the publisher refused the request) |
| The Commonwealth Fund | **Pending**: its feed's URL not yet given to the session or checked |
| Health Affairs (Forefront) | Not added: **no public feed** (the PM found only third-party generated feeds) |
| Modern Healthcare | Not added: **no public feed** (only generated feeds; a subscription trade publication) |
| Axios Vitals | Not added: **no public feed** (an email newsletter) |
| Politico Pulse | Not added: **no public feed** (an email newsletter; "Pulse Check" is a podcast) |

No feed was substituted for any of them.

**For the PM:**

* The other four politics feeds all answered `HTTP 200` with every entry dated on 2026-11-05: NPR 10/10, PBS NewsHour 20/20, Politico 30/30, The Hill 15/15. Without Roll Call, the politics topic has four feeds.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
