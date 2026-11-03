# Session report: v1-e07-t07-government-adapters

| | |
|---|---|
| Task | `v1-e07-t07-government-adapters` — Government and policy source adapters |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t07-government-adapters.yaml`](../../plan_specs/v1/e07-discovery-adapters/t07-government-adapters.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t07-government-adapters` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

Two government discovery providers, each asked only by a search on a topic that lists it.
`FederalRegisterProvider` searches the Register's rules, proposed rules and notices, and needs no
key. `GovInfoProvider` searches GovInfo's bills, committee reports, hearings and committee prints,
with one api.data.gov key; bills come from here because Congress.gov's API has no keyword search.
Without the key, GovInfo is not built, and a search on its topic reports `govinfo: not configured: no
api.data.gov key (DEBATE_PROVIDERS__API_DATA_GOV_KEY)` instead of an error. A search names its topic
with `search --topic`, which now works on its own. A feed file's `search_topics` and
`government_providers` say which government providers a topic asks, and `health-insurance.yaml`
enables both for `policy-2026-27-nhi`. A government provider runs only when it is enabled, on the
search's topic and (GovInfo) keyed. Both adapters pass the contract kit on hand-written fixtures,
and all 18 mutants were caught. The affected set (468 of 666 files) is left to the pull request's
`ci`, as the PM's 2026-10-19 ruling says. Look first at the selection rule (`SearchTopics` and
`selected_providers` in `application/federated_search.py`), then at two consequences under
Decisions: a keyless GovInfo makes every NHI search PARTIAL (exit 6), and the two new names go last
in the dedupe precedence table.

The session stopped before building, as the brief asked, and the PM ruled on 2026-11-02. The
findings from that stop are kept below, as written then.

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

| Node | Status | Notes |
|---|---|---|
| `federal-register` (Federal Register adapter) | Done | `federal_register.py`; fixtures hand-written under `packages/debate_core/tests/fixtures/discovery/federal_register/` (ruling 5). |
| `data-gov-key` (api.data.gov key handling) | Done | `data_gov.py`; `ProviderNotConfigured` in the registry; `not_configured` on the `DiscoveryProviders` port; the fan-out reports it. |
| `topic-enablement` (Per-topic enablement) | Done | Moved before GovInfo (ruling 7). `SearchTopics`, `SearchRequest.topic_id`, `search --topic` alone, the feed files' two keys, the container. |
| `govinfo` (GovInfo adapter) | Done | `govinfo.py`; BILLS, CRPT, CHRG, CPRT (ruling 2); fixtures under `.../fixtures/discovery/govinfo/`. |
| `congress-gov` | Removed | Ruling 1: Congress.gov has no keyword search. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: FederalRegisterProvider and GovInfoProvider each pass the contract kit on hand-written fixtures (amended: two providers) | PASS | `TestFederalRegisterProvider`, `TestFederalRegisterProviderOnAnEmptyResult`, `TestGovInfoProvider`, `TestGovInfoProviderOnAnEmptyResult` in `test_government.py`, inside the 184 below. |
| ac2: source_type government, the issuing agency or committee as publisher, the official identifier as provider_record_id | PASS | `test_federal_register_recorded_documents_map_to_the_hand_written_candidates`, `…_document_number_is_the_record_id_as_the_register_prints_it`, `…_issuing_agencies_are_the_publication` (7 cases), `…_every_document_is_a_free_to_read_government_source`; `test_govinfo_bill_congress_type_and_number_are_read_from_its_package_id` (6), `…_package_id_that_is_not_a_bills_one_gives_no_bill` (8), `…_issuing_committee_is_the_publication` (6), `…_url_is_the_package_details_page_and_no_api_link_is_offered`, and the kit's mapping check on both recordings. |
| ac3: a missing api.data.gov key leaves GovInfo NOT_CONFIGURED, not an error; the Federal Register works keyless (amended: GovInfo only) | PASS | `test_key_missing_leaves_govinfo_unbuilt_and_recorded_not_configured` (unset, empty, spaces), `test_govinfo_key_missing_builds_no_adapter_and_records_it_not_configured` (3), `test_key_missing_is_reported_not_configured_for_every_query_not_as_an_error`, `test_key_is_never_the_shared_demo_key`, `test_federal_register_is_built_and_answers_with_no_key_configured`; CLI: `test_govinfo_without_an_api_data_gov_key_is_reported_not_configured_on_its_topic`. |
| ac4: topic config controls which government providers run, verified by a registry test | PASS | Over a real `ProviderRegistry` and `FanOutStage`: `test_topic_that_lists_the_government_providers_asks_them_beside_the_others`, `…_absent_leaves_the_government_providers_neither_asked_nor_reported`, `…_that_lists_only_govinfo_does_not_ask_the_federal_register`, `…_lists_a_provider_settings_do_not_enable_so_it_is_not_asked`, `…_known_with_no_government_providers_asks_none_of_them`, `…_gate_reports_a_government_provider_named_by_providers_as_not_configured` (2), `…_unknown_is_refused_with_the_valid_ones_before_any_provider_is_asked`, `test_topic_committed_feed_files_enable_both_government_providers_for_nhi_only`; CLI: `test_the_federal_register_is_asked_only_by_a_search_on_a_topic_that_lists_it`. |
| ac5: in `debate_core.integrations.discovery`, passes the kit, secrets never in a log line, passes in one process after the OpenCaselist and discovery suites | PASS | Kit as ac1, with the api.data.gov key and the contact email in `secrets`; `test_govinfo_key_reaches_no_log_line_error_repr_or_snapshot`, `test_federal_register_no_configured_secret_reaches_a_log_line_an_error_or_a_snapshot`, `test_key_is_masked_in_every_protected_log_line_once_govinfo_is_built` (7 loggers, from bare loggers). One process: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/opencaselist packages/debate_core/tests/integrations/test_http_fetcher.py packages/debate_core/tests/integrations/test_crossref_doi.py packages/debate_core/tests/integrations/discovery/test_redaction.py packages/debate_core/tests/integrations/discovery/test_resilience.py packages/debate_core/tests/integrations/discovery/test_registry.py packages/debate_core/tests/integrations/discovery/test_http_failures.py packages/debate_core/tests/integrations/discovery/test_fake_provider.py packages/debate_core/tests/integrations/discovery/test_openalex.py packages/debate_core/tests/integrations/discovery/test_feeds.py packages/debate_core/tests/integrations/discovery/test_crossref.py packages/debate_core/tests/integrations/discovery/test_government.py -n 0 -p no:randomly -q` → `1116 passed in 2.66s`; `--collect-only` puts `test_government.py` last. |
| Node `federal-register`: `uv run pytest …/test_government.py -k federal_register` | PASS | `56 passed in 1.57s`. |
| Node `data-gov-key`: `uv run pytest …/test_government.py -k key` | PASS | `16 passed in 1.54s`. |
| Node `govinfo`: `uv run pytest …/test_government.py -k govinfo` | PASS | `92 passed in 2.09s`. |
| Node `topic-enablement`: `uv run pytest …/test_government.py` | PASS | `184 passed in 2.17s`. |

### Red runs, then green

Each set was written first and run against a skeleton with the public names and no behaviour, as the
PM asks. The runs used `--tb=line`, with the reasons grouped.

* **Settings** (`test_settings.py`, 7 selected): 3 failed: the two names missing, `.env.example`
  missing the variable, no `api_data_gov_key` attribute. The profile guard passed, as it should with
  no profile assigning the key.
* **Dedupe precedence**: 2 failed: the table names 6 providers, not 8, and the two new names are not
  last. `test_a_government_record_gives_way_to_every_other_provider_in_a_merge` passed red, because
  a provider outside the table already comes last. It is kept as the behaviour the table must keep.
* **Federal Register** (55): 46 failed against a do-nothing skeleton (`assert None is not None` ×19,
  `DID NOT RAISE ProviderUnavailable` ×15, empty lists, `repr`). The 7 refusal cases passed against
  it, because it refused everything. Against a refuse-nothing mapping all 7 failed. Two stay green
  against any skeleton: the URL constant, and the zero-count answer with no `results` key.
* **Key and topic** (29): 22 failed (`DID NOT RAISE FeedConfigError` ×5, `DID NOT RAISE
  UnknownExpansionChoice`, `DID NOT RAISE ProviderNotConfigured`, wrong selections, `DEMO_KEY`
  built, the key unmasked, `topic_id` in the JSON). The 7 that passed are cases where asking
  everything is the right answer: an enabled provider on its topic, a keyed factory, the
  Federal Register keyless, and an unknown name the enum already refused.
* **CLI** (`test_search_command.py`): 3 failed: a bare `--topic` was a usage error, an unknown one had
  no topic list, and the Federal Register was not wired.
* **GovInfo** (92 under `-k govinfo`): 71 failed against a refuse-nothing skeleton. The 21 that passed
  were the already-built key and topic tests whose names mention govinfo, the `None`-expecting date
  and publication cases, the empty-words case, and the kit's name and secrets checks.

### Mutants

All 18 ran against `HEAD` with the files that cover them (`test_government.py`, plus
`test_search_command.py` for the selection rule). Each was restored with `git checkout HEAD --`. No
Hypothesis is involved.

| Mutant | Caught by |
|---|---|
| PM: the key logged (no `protect_logs` in `require_api_data_gov_key`) | `test_key_is_masked_in_every_protected_log_line_once_govinfo_is_built` |
| PM: a missing key reported as an error (`ERROR` outcome for an unbuilt provider) | `test_key_missing_is_reported_not_configured_for_every_query_not_as_an_error`, and the CLI footers (7 failed) |
| PM: a government provider run for a topic that does not list it (`allows` true for any topic) | `test_topic_that_lists_only_govinfo_does_not_ask_the_federal_register`, `…_known_with_no_government_providers_asks_none_of_them`, `…_gate_reports_…[topic-without-it]` |
| PM: an identifier dropped (GovInfo `provider_record_id`) | the kit's mapping check, `test_govinfo_bill_whose_package_id_names_no_bill_is_not_a_candidate`, the per-package test |
| PM: an identifier dropped (Federal Register document number) | `…_document_number_is_the_record_id…`, the recorded mapping, `max_results` (6 failed) |
| PM: a year date given a day (GovInfo) | `…_date_issued_keeps_its_precision…[year]`, the kit's mapping check |
| A month date given a day | `…[month]`, the kit's mapping check |
| `DEMO_KEY` used when no key is set | the three missing-key cases and the fan-out test (8 failed) |
| The key sent as `api_key=` in the URL | `…_request_is_one_post_with_the_key_in_its_header…` and the kit's recorded-request checks (15 failed) |
| Every granule of a package kept | `…_answer_keeps_one_candidate_per_package…`, the kit's mapping check |
| A BILLS id that names no bill kept | `…_bill_whose_package_id_names_no_bill…`, the kit's mapping check |
| Field syntax searched as typed | `…_query_words_that_would_read_as_search_syntax_are_cleared` (2), `…_query_of_nothing_but_search_syntax…` |
| The Federal Register reads a 3xx | the redirect tests and the `304` test (6 failed) |
| The Federal Register asks for every document type | the exact-URL and parameter tests, every recorded exchange (22 failed) |
| A feed file may enable a non-government provider per topic | `test_topic_feed_file_mistake_fails_the_load[a-news-provider]`, `[a-scholarly-provider]` |
| A keyless GovInfo left out instead of reported | the fan-out test, `test_topic_selection_is_the_providers_the_stored_search_records`, the CLI footer test. First skipped by the harness: after formatting, its target line no longer matched. Rerun alone. |
| An unknown topic searched | `test_topic_unknown_is_refused…`, `test_an_unknown_topic_alone_exits_2…` |
| `topic_id` always in a request's JSON | `test_topic_id_is_left_out_of_a_requests_json_when_none` |

### Before the report

* Affected set: `uv run scripts/affected_tests.py` → `468 of 666 test files (70.3%) chosen in 27.4 s
  from 54 changed files`. The `DiscoveryProviders` port reaches the root conftest, through
  `fake_router`. That is well past two minutes, so it is left to the pull request's `ci`, as
  working agreement 10 and the PM's ruling of 2026-10-19 say. Nothing is handed to the operator.
* The changed areas and the always-run list, in one run: `.venv/bin/python scripts/hard_stop.py 115
  .venv/bin/python -m pytest packages/debate_core/tests/integrations/discovery
  packages/debate_core/tests/application/test_settings.py …/test_federated_search.py
  …/test_federated_dedupe.py …/test_federated_ranking.py …/test_federated_search_articles.py
  …/test_query_expansion.py packages/debate_cli/tests/test_search_command.py
  …/test_search_presenter.py …/test_installation.py …/commands/test_doctor.py …/test_app.py
  …/test_help_rendering.py …/test_container_factories.py tests/architecture tests/specs
  tests/smoke/test_search_smoke.py tests/scripts/test_stamp_build.py
  tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py -q -m "not slow and
  not live"` → `1969 passed in 32.66s`.
* `uv run --frozen ruff check .` → `All checks passed!`; `uv run --frozen ruff format --check .` →
  `1874 files already formatted`; `uv run --frozen pyright` (the whole configuration, as CI runs it)
  → `0 errors, 0 warnings, 0 informations`; `uv run --frozen lint-imports` → `Contracts: 20 kept, 0
  broken.`; `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 72 … within 25
  statements`; `scripts/docs_index.py --check-descriptions` → `All 68 indexed documents under docs/
  have a description`; `scripts/check_links.py` → `OK: 3461 relative links and anchors in 581
  Markdown files`; `scripts/check_command_blocks.py --base origin/dev` → `OK: no # comments in 661
  shell code blocks in 241 Markdown files (1 session reports changed since origin/dev)`;
  `uv run scripts/validate_specs.py` → `OK: 585 files, 41 epics, 522 tasks, 22 releases` (after the
  phase change).

## Files changed

* **`packages/debate_core/src/debate_core/integrations/discovery/`**:
  * `federal_register.py`, `govinfo.py` and `data_gov.py` (new): the two adapters and the key.
  * `registry.py`: `ProviderNotConfigured` and `not_configured`.
  * `feed_config.py`: `search_topics`, `government_providers`, `topic_providers`, `search_topic_ids`.
  * `http_failures.py`: `redirect_failure`, shared by both adapters.
  * `__init__.py`: the docstring.
* **`packages/debate_core/src/debate_core/application/`**:
  * `settings.py`: two names, `TOPIC_ENABLED_PROVIDERS` and `api_data_gov_key`.
  * `ports/providers.py`: `DiscoveryProviders.not_configured`.
  * `federated_search.py`: `SearchTopics`, the selection rule, the fan-out gate and the service's
    topic check.
  * `federated_search_types.py`: `SearchRequest.topic_id`.
  * `federated_dedupe.py`: the two names last in every row.
* **`packages/debate_cli/`**:
  * `commands/search.py`: `--topic` alone.
  * `container.py`: both factories, one shared feed-list load, `SearchTopics`.
  * `README.md`: the search section's government sources and the key's setup note.
  * Tests: `test_search_command.py` (new tests), `test_installation.py` and `commands/test_doctor.py`
    (the pinned lists, 42 → 44), `test_search_presenter.py` (its fake).
* **`config/feeds/`**: `health-insurance.yaml` (the two keys, for NHI), `README.md`.
* **Tests**:
  * `packages/debate_core/tests/integrations/discovery/test_government.py` (new, 184 tests).
  * Fixtures: `packages/debate_core/tests/fixtures/discovery/federal_register/` and `govinfo/` (new,
    with READMEs).
  * `test_settings.py` and `test_federated_dedupe.py` (new tests).
  * Four application test files' fakes.
  * `tests/smoke/test_search_smoke.py` (two checks).
* **Other**: `.env.example` (the variable, commented out), the spec, this report.

## Deviations from the spec

The PM's rulings of 2026-11-02, written into the spec's description, criteria, packages and nodes:

1. No Congress.gov adapter and no `CONGRESS_GOV`; bills come from GovInfo's BILLS collection. ac1 and
   ac2 name two providers, and ac3 GovInfo only. The `congress-gov` node is removed.
2. GovInfo searches BILLS, CRPT, CHRG and CPRT. GAO and CRS reports are a follow-up the PM files.
3. The Federal Register is built on the API spec the PM read (`documentation.json`, 2026-11-02). No
   pacer, and a 3xx is unavailable, naming its host.
4. A keyless GovInfo is not built, is recorded not configured and is reported `not_configured`;
   `health()` is unchanged.
5. `--topic` stands alone; the rule is enabled AND on the topic AND (GovInfo) keyed.
6. NHI only. The PF topic's file waits for the coach's November-December resolution.
7. The fixtures are hand-written, under `packages/debate_core/tests/fixtures/discovery/<source>/`.
   The node order is now Federal Register, then the key and the topic enablement, then GovInfo.

Found while building, added to the spec's packages with a comment on each:

8. **`application/federated_dedupe.py` and its test.** A test pins that every row of the dedupe
   precedence table names every `SearchProviderName`, so the two names had to go somewhere. They
   went last in every row, where no existing merge changes.
9. **Six test fakes of `DiscoveryProviders`** (four application test files, `test_search_presenter.py`,
   and `test_query_expansion.py`'s, which the first count missed) gained `not_configured`.
10. **`.env.example` and `test_settings.py`.** A test pins every secret's variable in the example
    file, and another the provider names.
11. **`config/feeds/README.md`** documents the two keys. `http_failures.py` gained
    `redirect_failure`, inside the spec's `debate_core.integrations`.

## Decisions and assumptions

* **A keyless GovInfo makes every NHI search PARTIAL (exit 6)** until a key is set. That follows
  from ruling 4: a reported `not_configured` call counts against COMPLETE, as a requested provider
  that is not enabled already does. A search with no `--topic` is untouched.
* **Where the topic is stored.** `SearchRequest` is never persisted. The stored `Search` is
  unchanged, and its `provider_set` already records the government providers a topic chose. So an
  older build reads every search this build stores exactly as before. `topic_id` is left out of a
  request's JSON when None (`exclude_if`), as the ruling asks; a request with one would be refused
  by an older build's `extra="forbid"`, but no request is stored. Storing the topic on `Search`
  (domain, schema regeneration) is a follow-up if the PM wants it for audit.
* **Identifiers.**
  * The Federal Register's `provider_record_id` is the document number as printed. Its shape is
    not checked, because older and correction numbers differ (`E9-1234`).
  * GovInfo's is the package id. A bill's Congress, type, number and version are read from it with
    `bill_number` (`BillNumber`), and a BILLS id that names no bill is skipped. The parsed number
    is kept as a function, not a field: `CandidateResult` has none, and ruling 4 keeps
    `ArticleIdentifiers` unchanged.
  * One candidate per package: a granule is its package.
* **URLs and access.**
  * The Federal Register: `html_url`, else `pdf_url`; the PDF is the open copy.
  * GovInfo: the public details page, `https://www.govinfo.gov/app/details/<id>`, a pattern seen
    on govinfo.gov's own pages. The `download` links are API URLs that need the key, so they are
    never stored or handed to the fetcher, and GovInfo results have no `open_access_url`.
  * Every government document is `open_access: true`.
* **Publication.** Agencies or authors in the provider's order, each once, joined by `; `
  (`Health and Human Services Department; Centers for Medicare & Medicaid Services`).
* **GovInfo's query.**
  * `(<words>) AND collection:(BILLS OR CRPT OR CHRG OR CPRT) AND publishdate:range(<since>,<until>)`.
  * The documentation shows `range(2008-05-01, 2008-05-15)` and `lastModified:range(<time>,)`, but
    no open start. `range(,<until>)` is unconfirmed, and the live smoke will show it.
  * Brackets, colons and an unpaired quote are cleared from the words, and words that clear to
    nothing are not sent.
  * Upper-case collection codes, as the API's sample uses.
* **The Federal Register's empty answer.** A body with `count: 0` and no `results` key is an empty
  answer, not an unreadable one. The PM's reading shows only a `200`, so this is defensive.
* **The gate's place.** `TOPIC_ENABLED_PROVIDERS` lives in `application/settings.py`, beside the
  names, so that the feed-file check (integrations) and the fan-out (application) share one list.
* **Feed lists on every search.** The container now reads `config/feeds/` for every search, for the
  topic list, not only when `rss` or `google_news` is enabled. A broken committed file then fails
  every search instead of only feed searches. CI loads every file on every pull request.
* **A requested government provider off its topic** (`--providers federal_register` with no
  `--topic`) is reported `not_configured` with why, from the proposal the PM accepted with option A.

## Operator follow-ups

Both after the merge, on a machine with network access. They make live calls, so they are the
operator's, as the brief and the forbidden list say.

**1. An api.data.gov key** (one time, about 2 minutes). Sign up at https://api.data.gov/signup/ with
any name and email. The key arrives by email. Open `.env` in the root of the checkout you run
`debate-research` from (it is git-ignored) and add the line
`DEBATE_PROVIDERS__API_DATA_GOV_KEY=<the key>`. Don't type it on the command line, where the shell
history would keep it. The key allows 1,000 requests an hour, which is about 90 searches an hour
expanded to eleven queries; past that, GovInfo answers `429` for the rest of the hour and the footer
says `govinfo: rate_limited`. Never use `DEMO_KEY`: the platform refuses to fall back to it.

**2. Optional live smoke** (expected runtime ~10 s). It asks both providers one search, stores it in a
throwaway data directory, and prints each provider's status and counts only: no titles, no reasons,
no key.

Where: your Mac, in a checkout of `dev` after the merge (this worktree works until
`scripts/task finish`).

```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e07-t07-government-adapters
```

```bash
env DEBATE_ENV=dev DEBATE_STORAGE__DATA_DIR="$(mktemp -d)" DEBATE_PROVIDERS__ENABLED='["federal_register","govinfo"]' uv run debate-research search "health insurance marketplace" --topic policy-2026-27-nhi --since 2025-01-01 --format json | jq '(.data // .error.details).providers | map({provider, outcome, queries, failed, results})'
```

Success looks like two entries, `federal_register` and `govinfo`, each `"outcome": "ok"` with
`results` above zero. Paste the printed list back. What the other answers would mean:

* `govinfo` `not configured`: the key is not in `.env`.
* `federal_register` `error`: the Register may be sending its block page. Rerun with `.providers`
  in place of the `map(...)` to see the reason, which names the redirect host.
* `govinfo` `error` with `HTTP 400`: GovInfo refused the query syntax, probably the date range.
  That is a fix for a follow-up session.

## Follow-up work

* **Congress.gov lookups by bill** (latest action, committees) from `BillNumber`. The PM files it
  (ruling 1).
* **GAO reports** (GAO's own site) **and CRS reports** (Congress.gov's `/crsreport`, which has no
  keyword search). The PM files it (ruling 2).
* **The data-center PF topic's file**, once the coach gives the November-December resolution.
* **`--topic` with `--argument`** on an id that only a feed file names (not a taxonomy preset):
  the expansion stage would refuse it as an unknown preset. No such id exists today (NHI is both).
  A later topic file could need the expansion to fall back to the query for `{topic}`.
  Belongs with E08.
* **Storing the topic on `Search`**, if the PM wants the topic itself kept for audit, not only the
  providers it chose. Belongs with E08.
* **The shared pacer** stays as filed. Neither provider needed one.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-02

**Notes:**

The stop before building saved a wrong adapter: Congress.gov has no keyword search, and the report
shows it from the API's own openapi file. What was built follows the rulings exactly.

1. **ac1 to ac5 pass.** Both adapters pass the kit on hand-written fixtures; identifiers, publishers
   and government source type are pinned case by case; a missing key leaves GovInfo unbuilt and
   reported `not_configured`, never `DEMO_KEY`; the topic rule is tested over a real registry and
   fan-out; the key reaches no log line, and the one-process run (1,116) ends with this file.
2. **Red first and mutants:** every set run against a skeleton first, with the passes explained; 18 of
   18 mutants caught, the PM's five among them.
3. **Deviations 1 to 11 accepted.** 1 to 7 are the rulings. 8 to 11 (the dedupe table's two names, last
   in every row; the six test fakes; `.env.example`; the feeds README) are what those rulings require.
4. **Decisions accepted.** The PARTIAL point is acceptable because neither profile enables a
   government provider (dev and prod enable `openalex` and `rss`), so only a deliberately enabled,
   keyless GovInfo makes an NHI search PARTIAL, and that is a configuration to fix. The topic isn't
   stored, so older builds read every stored search as before. GovInfo's API download links are never
   stored, since they carry the key's need.
5. **Follow-ups the PM files:** Congress.gov lookups by bill; GAO and CRS reports; the PF topic's file
   when the coach gives the November-December resolution; `--topic` with `--argument` on an id only a
   feed file names (E08); and enabling `federal_register` (and later `govinfo`) in the profiles once
   the live smoke passes. Storing the topic on `Search` is not needed now.
6. **Operator follow-ups:** the key and the live smoke, after the merge. Run the smoke from a checkout
   of `dev` once this worktree is finished. The open-start `range(,until)` and the Register's
   automated-reader block are what it confirms; paste the printed list.
7. **Closing checks:** the affected set (468 files) is left to `ci` (agreement 10). The changed areas
   with the always-run list (1,969), ruff, pyright over the whole configuration, lint-imports, thin
   handlers, the docs index, the links, the command blocks and the specs are clean.
8. **Merge:** a plain `scripts/task pr` once `ci` is green. The Goal is `Succeeded`.
