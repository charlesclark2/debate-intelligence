# Session report: v1-e07-t05-rss-news-adapter

| | |
|---|---|
| Task | `v1-e07-t05-rss-news-adapter` — Publisher RSS/Atom and Google News RSS adapter |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t05-rss-news-adapter.yaml`](../../plan_specs/v1/e07-discovery-adapters/t05-rss-news-adapter.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t05-rss-news-adapter` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Two news discovery providers now live in `debate_core.integrations.discovery`, both wrapped in
`ResilientProvider` by the registry and both passing the shared contract kit on hand-written fixtures:

* **`FeedProvider`** (`rss`) reads the coach's per-topic feed lists in `config/feeds/`. It keeps the
  entries that match the query and fall in its window and returns them as news candidates.
* **`GoogleNewsRssProvider`** (`google_news`) searches Google News's RSS feed for the topics that
  enable it. It returns only items whose publisher URL can be decoded offline.

Feeds are parsed with defusedxml over the standard library's ElementTree, with entities and
external references refused (PM ruling 2026-10-22). Conditional GET keeps each feed's validators and
already-trimmed entries in one JSON file per feed under `<storage.data_dir>/feeds/`. The starter feed
lists (politics, and the Policy 2026-27 health-insurance topic) all await the coach's review, and
Google News is off in both. The operator's feed check of 2026-10-22 had all eight starter feeds
answer `HTTP 200`. Seven dated every entry; Roll Call's dates carry no time zone, so its entries are
undated (Operator follow-ups). The PM should look first at the Google News resolution rule
(`google_news_rss.py`), which drops most current items by design, and at the three edits outside
`debate_core.integrations` listed under Deviations. Every acceptance criterion passed, so the phase
is `Succeeded`.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `feed-config` — Topic feed config and fixtures | Done | `FeedConfig` (`feed_config.py`), `config/feeds/politics.yaml` and `health-insurance.yaml`, the fixtures in `packages/debate_core/tests/fixtures/discovery/feeds/` |
| `feed-provider` — FeedProvider with filtering and conditional GET | Done | `feed_parsing.py` (safe parser, dates, snippets), `feed_cache.py`, `feeds.py`; also the operator's `feed_check.py` |
| `google-news-rss` — Google News RSS provider | Done | `google_news_rss.py`; `GOOGLE_NEWS` added to `SearchProviderName` and to the dedupe precedence table (PM rulings) |
| `contract-run` — Contract kit and snippet-limit checks | Done | Contract bindings for both providers, the discovery-fields-only check, snippet limit |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — From RSS 2.0 and Atom fixtures, FeedProvider returns candidates filtered to the terms and window, with aware `published_at` and source type news | PASS | `test_the_feed_recording_maps_to_news_candidates_newest_first` and `TestFeedProviderContract::test_the_recording_maps_to_the_expected_results`: eight candidates from `feeds_search.json`, matching the hand-written `feeds_search.expected.json` |
| ac2 — Google News search URL with query and date operators, entries mapped to publisher URL and name, can be disabled per topic | PASS | `test_google_news_search_url_carries_the_query_the_widened_window_and_the_edition`, `test_google_news_recording_maps_to_publisher_urls_and_names`, `test_google_news_off_for_every_topic_sends_nothing`, `test_google_news_asks_once_per_edition_of_the_topics_that_enable_it` (met on a fixture, as the PM ruled) |
| ac3 — Conditional GET headers on repeat fetches; a 304 returns cached entries without re-parsing | PASS | `test_feed_conditional_get_sends_validators_and_a_304_reuses_the_entries_unparsed` (`parse_feed` replaced by one that fails the test), `test_feed_conditional_get_survives_a_new_process_through_the_file_cache` |
| ac4 — No candidate carries feed body beyond a snippet of at most 500 characters; both providers pass the contract kit | PASS | `test_feed_snippets_never_carry_feed_content_and_never_pass_500_characters`, `test_feed_and_google_news_candidates_carry_discovery_fields_only[feeds/google-news]`, `test_feed_content_is_never_read_into_an_entry`; `pytest test_feeds.py -k Contract` → `16 passed` |
| ac5 — In `debate_core.integrations.discovery`, passes the contract kit on recorded fixtures, secrets never in a log line, tests pass in one process after the OpenCaselist and discovery suites | PASS | Both contract bindings run check 7 with the contact email and an OpenAlex key configured. One-process run, OpenCaselist first: `.venv/bin/python -m pytest -n 0 -p no:randomly -m "not slow and not live" packages/debate_core/tests/integrations/opencaselist <every discovery test file, test_feeds.py last>` → `569 passed in 0.99s` |
| Node `feed-config` — Politics feed config exists | PASS | `ls config/feeds/politics.yaml` → present |
| Node `feed-provider` — `uv run pytest .../test_feeds.py -k feed` | PASS | `79 passed in 8.92s`. `-k feed` also matches the module name, so it selects every test in the file |
| Node `google-news-rss` — `uv run pytest .../test_feeds.py -k google` | PASS | `32 passed in 1.99s` |
| Node `contract-run` — `uv run pytest .../test_feeds.py` | PASS | `79 passed in 2.22s` |

### Checks before the report

* `uv run scripts/affected_tests.py --run` → "The whole selection is affected:
  packages/debate_core/pyproject.toml is shared test ground. CI runs it on the pull request; a session
  does not (working agreement 10)." Before the pyproject edit it listed 321 of the repository's 384
  test files, because `application/settings.py` changed. That is over the two-minute line either
  way, so the PR's `ci` check is the whole run.
* Within the two minutes: the changed test directories, the always-run list, the CLI's installation
  test and the docs checks:
  `.venv/bin/python -m pytest -n auto -m "not slow and not live" tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_installation.py packages/debate_core/tests/integrations/discovery packages/debate_core/tests/application tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py`
  → `3720 passed in 76.30s`.
* `uv run ruff format --check .` → `1067 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` (11 s)
* `uv run lint-imports` → `Contracts: 15 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 404 files, 39 epics, 344 tasks, 21 releases`
* `uv run scripts/check_command_blocks.py` → `OK: no # comments in 335 shell code blocks in 135 Markdown files`

### Red run and mutation

* **Red run.** A skeleton that refuses nothing was put in place:
  * entities and external references allowed;
  * no snippet trimming;
  * every entry matching the terms and every date inside the window;
  * no conditional headers;
  * every Google link returned as it came.

  Against it, `test_feeds.py`, `test_feed_parsing.py` and `test_feed_check.py` gave
  `40 failed, 86 passed`, and the tree was then restored from the commit.
  `test_an_external_dtd_is_never_read` stayed green. The standard library's expat never reads an
  external DTD subset whatever `forbid_external` says, so that test pins behaviour rather than the
  switch.
* **Mutation**: 20 mutants on the PM's five areas, each against `test_feeds.py`,
  `test_feed_parsing.py` and `test_feed_cache.py`, with `-x` and a fresh, empty
  `HYPOTHESIS_STORAGE_DIRECTORY` per run (working agreement 8; no test here uses Hypothesis).
  **19 of 20 caught**, each in under a second:

| Area | Mutant | Caught by |
|---|---|---|
| XML safety | entities allowed | `test_a_hostile_feed_is_refused_as_unreadable[entity_expansion.xml]` |
| XML safety | external references allowed | **survived**, see below |
| XML safety | every DOCTYPE refused | `test_a_hostile_feed_is_refused_as_unreadable[entity_expansion.xml]` (the refusal message changes) |
| XML safety | refusal not caught as such | same test |
| Keyword filter | no left word boundary | `…whole_word…[Reinsurance pool and health costs-…]` |
| Keyword filter | any term instead of all | same |
| Keyword filter | title only | `…whole_word…[Subsidies-Health and dental insurance-health insurance-True]` |
| Keyword filter | quoted phrase also split | `test_feed_query_terms_are_quoted_phrases_then_words_folded` |
| Date filter | `since` exclusive / `until` exclusive | `test_a_feed_window_includes_both_ends_and_never_an_undated_entry` |
| Date filter | undated kept inside a window | same, `[None-False]` |
| Date parsing | `-0000` not UTC; naive ISO guessed UTC; unknown RFC zone guessed UTC | `test_the_feed_recording_maps_to_news_candidates_newest_first` |
| Date parsing | numeric offset sign ignored | `test_a_feed_date_becomes_utc[… -09:30 …]` |
| URL resolution | decoded Google URL accepted | `test_google_news_links_resolve_offline_or_not_at_all[id-holding-a-google-url]` |
| URL resolution | lookalike host counted as Google | `test_google_news_hosts_are_google_and_lookalikes_are_not` |
| URL resolution | unresolved item falls back to the `<source url>` | `test_google_news_recording_maps_to_publisher_urls_and_names` |
| Conditional GET | 304 not recognised; answer never cached | `test_feed_conditional_get_sends_validators_and_a_304_reuses_the_entries_unparsed` |

The survivor is `forbid_external=False`, and the PM accepted it. With `forbid_entities=True` a
document that declares an external entity is refused for the declaration (`EntitiesForbidden`)
before the external switch is consulted, and expat does not read an external DTD subset at all. So
no test can observe the setting while `forbid_entities` refuses first. Probed directly on
`external_entity.xml`:

| Settings | Result |
|---|---|
| entities forbidden, external forbidden | `EntitiesForbidden` |
| entities forbidden, external allowed | `EntitiesForbidden` |
| entities allowed, external forbidden | `ExternalReferenceForbidden` |
| entities allowed, external allowed | `ParseError` |

The setting stays, as defence in depth.

## Files changed

* **`packages/debate_core/src/debate_core/integrations/discovery/`** — the adapter:
  * `feed_config.py` — the topic file model and loader;
  * `feed_parsing.py` — the defusedxml parse, RSS 2.0 and Atom 1.0 mapping, dates, snippets;
  * `feed_cache.py` — `FeedCache`, the in-memory and file caches;
  * `feeds.py` — `FeedFetcher`, `FeedProvider`, the filters, `feed_factory`;
  * `google_news_rss.py` — `GoogleNewsRssProvider`, offline link decoding, `google_news_factory`;
  * `feed_check.py` — the operator's live check;
  * `__init__.py` — the docstring lists the new modules.
* **`config/feeds/`** — `politics.yaml`, `health-insurance.yaml` and a README describing the file
  and the operator's check.
* **`packages/debate_core/tests/integrations/discovery/`** — `test_feeds.py` (both providers, both
  contract bindings, with a copy of `replay_with_respx`), `test_feed_parsing.py`,
  `test_feed_config.py`, `test_feed_cache.py`, `test_feed_check.py`.
* **`packages/debate_core/tests/fixtures/discovery/feeds/`** — hand-written feeds, recordings,
  hand-written expectations and a README.
* **`packages/debate_core/src/debate_core/application/settings.py`** — `GOOGLE_NEWS = "google_news"`
  (PM ruling).
* **`packages/debate_core/src/debate_core/application/federated_dedupe.py`** and its test —
  `google_news` immediately after `rss` in every precedence row (PM ruling).
* **`packages/debate_core/tests/application/test_settings.py`** — the pinned provider names include
  `google_news`.
* **Packaging**:
  * `packages/debate_core/pyproject.toml` — the `feeds` extra (`defusedxml>=0.7.1`);
  * root `pyproject.toml` — `defusedxml` and `types-defusedxml` in the dev group, a forbidden
    contract keeping defusedxml inside discovery, its direct-form CLI contract, and discovery added
    to the lxml/docx contract's sources;
  * `uv.lock`.
* **`tests/architecture/test_import_contracts.py`** — a failing probe for each new or widened
  contract.
* **`plan_specs/v1/e07-discovery-adapters/t05-rss-news-adapter.yaml`** — the PM's amendments and
  `Succeeded`.

## Deviations from the spec

* **Fixture path** (accepted by the PM): fixtures are in
  `packages/debate_core/tests/fixtures/discovery/feeds/`, beside the other adapters', not the
  feed-config node's `tests/fixtures/providers/feeds/`.
* **Seeded topics** (accepted by the PM): only politics and the Policy health-insurance topic. The
  LD and PF topics change on 2026-11-01 and are left for the coach.
* **defusedxml, not feedparser**: the feed-provider node, `constraints.packages` and the Google News
  forbidden entry were amended in the spec with the PM's comments. The forbidden entry's comment uses
  the feedparser wording, as "the same comment" was read literally.
* **Two edits outside the amended packages**, both forced by a ruled change:
  * `packages/debate_core/tests/application/test_settings.py` pins the set of provider names, so it
    gains `google_news`;
  * `tests/architecture/test_import_contracts.py` must prove every configured contract fails
    (`test_every_configured_contract_is_proven_to_fail`), so it gains a probe for each new contract
    and for discovery on the lxml contract.
* **The dedupe URL fallback test** (`test_precedence_url_falls_back_to_crossref_when_no_feed_found_the_source`)
  now leaves out both feeds, since `google_news` is a feed too. Its hand-written "next" for `url`
  becomes `google_news`.
* **The node criterion `-k feed`** selects every test in `test_feeds.py`, Google's included, because
  pytest matches the module name. It is recorded as run.

## Decisions and assumptions

* **Which entries are kept** (accepted by the PM):
  * every query term appears as a whole word or quoted phrase in the title or snippet, ignoring case
    and with no stemming;
  * the window is inclusive at both ends;
  * an undated entry is dropped only when the search has a window;
  * an exact repeat of a link within one answer is dropped. Canonical-URL merging stays E08's.
* **Dates** (accepted by the PM, each tested in `test_feed_parsing.py`):
  * a zone that cannot be placed (`BST`, or none at all) gives no date, never a guessed UTC;
  * `-0000` is UTC, and numeric offsets, `+05:30` included, are applied;
  * Atom without `<published>` uses `<updated>`;
  * a bare `YYYY-MM-DD` is midnight UTC, as OpenAlex's dates are.
* **Order** is newest first with undated last, then cut to `max_results`. That is the provider's
  order, not a ranking.
* **Several feeds, one answer**: feeds are fetched four at a time. Some failing gives a partial answer
  naming the publishers. All failing raises the first failure, as a single-request adapter would.
* **Fetching**:
  * redirects are followed (up to `http.max_redirects`), because publishers move feeds;
  * bodies are capped at 5 MiB, and a larger one is abandoned, never truncated;
  * no cookies, nothing from the environment, the platform's User-Agent;
  * a cache that cannot be written logs a warning and costs only the next 304.
* **RSS `<author>`** is an email address by the standard. Only the name in brackets is kept, and a
  bare address is dropped.
* **Google News**:
  * the query keeps the user's text; `after:` and `before:` are widened by a day, and the exact
    window is applied locally;
  * terms are not re-matched, because Google matched them against the article;
  * the title loses only its own ` - Publisher` suffix;
  * there is no snippet, because Google's description is the headline and outlet again;
  * one request goes out per distinct edition of the enabling topics;
  * each search logs `google_news: N of M items dropped, publisher URL not resolvable without
    asking Google`.
* **The operator's check** (`python -m debate_core.integrations.discovery.feed_check`) follows
  `bedrock.first_call`'s pattern. It uses its own wall clock rather than `debate_core.testing`, which
  the layers contract keeps integrations away from.

## Operator follow-ups

### Done: the feed check, 2026-10-22

The operator ran the feed check once in the task worktree. It fetches each configured feed once,
one after another, and prints per feed only the topic, publisher, status, entry count, how many
entries carried a date, and the URL: no titles.

```bash
uv run python -m debate_core.integrations.discovery.feed_check --feeds-dir config/feeds
```

The result, as printed:

| Topic | Publisher | Status | Entries | Dated |
|---|---|---|---|---|
| health-insurance | KFF Health News | HTTP 200 | 10 | 10 |
| health-insurance | NPR | HTTP 200 | 10 | 10 |
| health-insurance | STAT | HTTP 200 | 20 | 20 |
| politics | NPR | HTTP 200 | 10 | 10 |
| politics | PBS NewsHour | HTTP 200 | 20 | 20 |
| politics | Politico | HTTP 200 | 30 | 30 |
| politics | The Hill | HTTP 200 | 15 | 15 |
| politics | Roll Call | HTTP 200 | 10 | 0 |

`8 feeds checked, 0 failed`. Every starter feed answers and parses through the safe parser, so seven
of the eight can now be called verified as reachable and dated. None has been reviewed by the coach,
so every `review:` stays `awaiting_coach_review`.

**Roll Call answers but carries no date this platform can place.** To see why, the session fetched
`https://rollcall.com/feed/` once and printed only its date elements. Every `<pubDate>` is in the form
`2026-10-21 20:18:41`: not RFC 822, and with no time zone, so it cannot be told apart as UTC or
Washington time. The parser therefore gives no date, as the PM ruled ("a zone that can't be placed
gives no date, never a guessed UTC"). The result is that every Roll Call entry is dropped from a
search with a date window and kept only in one without. Both feed files now record the check's
result in a comment, and Roll Call's entry says why it is undated.

No operator commands remain for this task beyond the review, PR and finish steps of the task workflow.

## Follow-up work

* **Match Google News items by title against the configured publisher feeds** (p3, as the PM ruled;
  the PM files it). An item whose id cannot be decoded offline could still be resolved when its
  `<source url>` host is a configured publisher and that publisher's own feed carries the same
  headline. That is the only offline route to most current items.
* **Roll Call's undated feed** (for the coach, or the PM if it should become a task). Roll Call's
  dates have no zone, so its entries never fall in a search window. There are two ways forward:
  * the coach replaces it with another politics feed (no code), which is the simpler choice;
  * a per-feed `timezone:` key in `config/feeds/` declares the zone a feed's zoneless dates are in.
    That is a change to the date rule the PM ruled on, so it is the PM's to open.
* **Wire topics into searches: v1-e08-t07's presets** (the PM amends that spec). `ProviderQuery` has
  no topic. The providers read the topics they were built with, and choosing those per preset belongs
  to the daily-digest presets.
* **Compose the feed providers in the CLI** (whichever task wires discovery into
  `debate_cli.container`). It needs:
  * `feed_factory` and `google_news_factory` over `load_feed_directory(config/feeds)`;
  * a `FileFeedCache` on `<storage.data_dir>/feeds/` (`FEED_CACHE_DIRECTORY`);
  * debate-cli's requirement on `debate-core[http,feeds]`, so `debate_cli.installation` reports a
    missing defusedxml. This task left debate-cli unchanged, as ruled.
* **v1-e08-t03's new precedence rows**: if it adds `citation_count` and `open_access` rows to
  `FIELD_PRECEDENCE` and merges first, this branch syncs and gives `google_news` its place in them.
  `test_precedence_table_has_one_row_per_merged_field_naming_every_configured_provider_once` will
  say so.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on two spec corrections closed in this session before the pull request, plus one
optional step if the coach gives his feed review now. Then open the pull request with no
`--partial`. If anything comes out differently from what is written here, stop and ask for another
review.

**What the PM checked.** The branch is clean, 10 commits on origin/dev at `9e89869`. The one dev
commit since then, #392, is a docs refresh, so no sync is needed. The diff is the 38 files listed.
Every fixture URL is on an example domain or is Google's own host, in the form the provider
decodes, and no fixture carries a real headline. `feed_check` prints counts and URLs, no titles.
The spec amendments match the rulings, except for the two points below.

**Spec corrections (conditions):**

1. **The forbidden entry's comment names the wrong ruling.** The entry defines "resolvable" for
   Google News links, but its comment cites "feedparser falls back to a loose parser on a hostile
   feed". "The same comment" meant the same form of comment, not the same text. Change it to
   `# PM ruling 2026-10-22 (v1-e07-t05: a Google News link counts as resolvable only offline).`
   Also check that the `constraints.packages` comment on the pyproject and lock lines names the
   defusedxml ruling, which it does, and leave it.
2. **Name the two outside edits in `constraints.packages`.**
   * Add `packages/debate_core/tests/application/test_settings.py` under the provider-name ruling's
     comment.
   * Add `tests/architecture/test_import_contracts.py` with
     `# PM ruling 2026-10-22: each new import contract needs its failing probe.`

   Both edits were forced by ruled changes, and the PM accepts them. The spec should still list
   every path the diff touches. Re-run `scripts/validate_specs.py` afterwards.

**Optional, only if the coach gives it in this session: his review of the starter feeds.** If he
approves a feed list, set its `review:` to approved, with his name and date, and record it in the
report. If he gives no review, every list stays `awaiting_coach_review`, which does not block the
merge.

**Rulings on the report's open points:**

* **Roll Call.** No code change now. The coach decides at his review: replace it with another
  politics feed (the simpler route), or keep it for searches with no date window. A per-feed
  `timezone:` key, where the zone is declared and never guessed, is acceptable in principle. The PM
  files it as a p3 only if the coach wants to keep Roll Call dated.
* **Google News dropping most current items** is the ruled behaviour, and it is off in both topics.
  The PM files the title-match follow-up (p3) in the next batch, as already planned.
* **CLI composition** (`feed_factory`, `google_news_factory`, `FileFeedCache` on
  `<storage.data_dir>/feeds/`, debate-cli requiring `debate-core[http,feeds]`) goes into the PM's
  v1-e08-t05 amendment, alongside the OpenAlex factory. **Topic wiring** goes into v1-e08-t07's
  presets amendment.
* **v1-e08-t03's precedence rows.** Whichever merges second gives `google_news` its place after
  `rss` in the `open_access` and `citation_count` rows. The table test enforces it.
* **The survived mutant** (`forbid_external=False`) is accepted as unobservable while
  `forbid_entities` refuses first. The probe table is good evidence. Keep the setting.

**Noted, no action.**

* The session's one live fetch of Roll Call's feed (date elements only, nothing kept) was a
  reasonable diagnostic. Next time, give the operator the one-line command instead, so that every
  live call in a task runs on the operator's side.
* The `-k feed` node criterion selects the whole module, as t03's `-k feature` did. It is the
  spec's wording, recorded as run.
* The pyproject edit makes the whole selection the PR's `ci`, under agreement 10.
