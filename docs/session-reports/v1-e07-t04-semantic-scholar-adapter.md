# Session report: v1-e07-t04-semantic-scholar-adapter

| | |
|---|---|
| Task | `v1-e07-t04-semantic-scholar-adapter` — Semantic Scholar adapter |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t04-semantic-scholar-adapter.yaml`](../../plan_specs/v1/e07-discovery-adapters/t04-semantic-scholar-adapter.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t04-semantic-scholar-adapter` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`SemanticScholarProvider` (`debate_core.integrations.discovery.semantic_scholar`) asks the Academic
Graph API's `/graph/v1/paper/search` with the spec's twelve fields, the `publicationDateOrYear`
window and a `limit` of at most 100. It sends a configured key as the `x-api-key` header, and no such
header without one. It paces at one request a second, one at a time, keyed and keyless alike (PM
ruling 1), on the shared `Pacer` from v1-e07-t10, with Crossref's answer reserve deciding when a
query is too late to send (ruling 2). The reserve now lives in `pace.py`, and Crossref's tests pass
unchanged on that commit alone. Papers map with their DOI, arXiv and PubMed ids, the paper id, the
citation count and the open-access PDF link, and a date is a day or a year, never an invented day
(ruling 4). The factory is wired into the CLI and enabled in no profile (ruling 5). The live smoke is
the operator's after the merge. **Look first at** Deviation 3 (three files beyond the ruling's
list) and Decisions 1 to 3 (one request per query, the URL, the hyphen rule).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `record-fixtures` (Record Semantic Scholar fixtures) | Done | Hand-written from the public API documentation (ruling 3), under `packages/debate_core/tests/fixtures/discovery/semantic_scholar/` with a README saying what each holds. The spec's path is amended with a comment. |
| `keyed-client` (Keyed/unkeyed client with redaction) | Done | `paper_search_parameters`, `searchable_query`, the header, the pace, `protect_logs` in the constructor. |
| `result-mapping` (Paper to CandidateResult mapping) | Done | `candidate_from_paper`, `source_type_for`; the kit bound four times. |

The wiring (ruling 5) is not a plan node; it is its own commit, `1600c26`.

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: with a key the x-api-key header is sent; without it no header is sent and the interval defaults to the unauthenticated limit | PASS | `test_a_request_with_a_key_sends_it_as_the_x_api_key_header` (a respx route that matches only with the header; two searches, both carry it, no URL does). `test_a_request_without_a_key_sends_no_key_header` (none, empty, spaces). `test_the_pace_with_a_key_and_without_one_is_the_published_one_request_a_second` (`Pace(requests=1, interval_seconds=1.0, concurrency=1)` written by hand, against both constants and both built adapters). `test_queries_with_a_key_or_without_are_sent_one_a_second_and_one_at_a_time`, on virtual time: starts at 0, 1, 2, 3 s with quick answers and 0, 1.5, 3, 4.5 s with 1.5 s answers. The interval is the ruled pace, not a different keyless one (Deviation 1). |
| ac2: fixtures map to CandidateResults including externalIds (DOI, ArXiv, PubMed), citationCount and openAccessPdf.url | PASS | `test_the_recorded_papers_map_to_the_hand_written_candidates[paper_search]` and `[paper_search_without_pdfs]` against the hand-written `*.expected.json`. Also `test_every_external_id_kind_is_read_and_the_others_are_ignored`, the DOI, PubMed and arXiv cases, `test_the_open_copy_is_the_pdf_link_…` (10 cases) and `test_the_citation_count_is_citation_count` (7 cases). |
| ac3: passes the contract kit; a redaction test confirms the key never appears in logs or errors | PASS | Kit: `TestSemanticScholarProviderWithAKey` (the key in `secrets`), `…WithoutAKey`, `…OnAPageWithoutPdfs`, `…OnAnEmptyResult`, 8 tests each. Redaction: `test_no_key_reaches_a_log_line_an_error_a_repr_or_a_health_snapshot`. It runs through the wrapper on the recorded search, the 429 with Retry-After, the empty search, a 403 whose body quotes the key, a transport failure whose message quotes it (shown as `refused for x-api-key: ***`) and a "not asked" answer, at DEBUG on every logger, starting from bare loggers. Also `test_the_adapter_alone_protects_the_logs_from_its_key` (7 loggers) and `test_every_recorded_request_carries_its_key_only_in_the_header` (no fixture file holds the key). |
| ac4: in `debate_core.integrations.discovery`, passes the kit on its recorded fixtures, secrets never in a log line, passes in one process after the OpenCaselist and discovery suites | PASS | As above. One process: `.venv/bin/python scripts/hard_stop.py 115 .venv/bin/python -m pytest packages/debate_core/tests/integrations/opencaselist packages/debate_core/tests/integrations/test_http_fetcher.py packages/debate_core/tests/integrations/test_crossref_doi.py` followed by every discovery test file (`test_redaction`, `test_resilience`, `test_registry`, `test_http_failures`, `test_pace`, `test_fake_provider`, `test_openalex`, `test_feeds`, the five `test_feed_*`, `test_government`, `test_crossref`) and `test_semantic_scholar.py` last, with `-n 0 -p no:randomly -q` → `1449 passed in 4.83s`. `--collect-only` puts Semantic Scholar's 184 at positions 1,266 to 1,449, last. |
| Node `record-fixtures`: artifact `packages/debate_core/tests/fixtures/discovery/semantic_scholar/paper_search.json` exists | PASS | `ls -la` → 746 bytes. |
| Node `keyed-client`: `uv run pytest packages/debate_core/tests/integrations/discovery/test_semantic_scholar.py -k "key or request"` | PASS | `55 passed in 2.22s`. |
| Node `result-mapping`: `uv run pytest packages/debate_core/tests/integrations/discovery/test_semantic_scholar.py` | PASS | `184 passed in 2.18s`. |

### Red runs, then green

* **Adapter.** `test_semantic_scholar.py` was run against a skeleton with the right names that sends a
  bare GET, maps nothing, paces nothing and sends no key. Result: `170 failed, 14 passed`, committed
  alone as `c4d02cb` without the skeleton. Grouped reasons, one line per failure (`--tb=line`):
  * 63 `assert None is not None` (no mapping);
  * 35 respx `AllMockedAssertionError` (a request with no parameters or no header);
  * 19 wrong source type;
  * 10 `DID NOT RAISE ProviderUnavailable`;
  * 7 request-parameter mismatches;
  * 7 log lines still carrying the key;
  * 7 `KeyError: 'query'` in the pace tests' transports (a request with no `query`): test code
    failing because the skeleton sent nothing to read, not an assertion;
  * 2 raw httpx exceptions and 3 wrapper errors saying the adapter raised one;
  * the rest are single pace, reserve, repr, hyphen, field-list and mapping assertions.

  The 14 that passed are what such a skeleton should pass: 7 untitled or id-less papers skipped, 2
  empty answers, 4 kit "is a provider with a name", and the kit's secrets check with no secret.
  Green: `184 passed`. One expectation of mine was wrong, not the code: `ProviderRateLimited`
  appends `(retry after 30.0s)` to its message (errors.py:601), so that test now expects
  `semantic_scholar: HTTP 429 (retry after 30.0s)`.
* **Wiring.**
  * `test_doctor_providers.py`: `2 failed, 9 passed`; the row read `Semantic Scholar no adapter in
    this build`.
  * `test_doctor.py` with `test_installation.py`: `4 failed, 65 passed`, at the two pinned lists and
    the httpx gaps.
  * The container test failed with the registry's no-adapter error.
  * Green after the code: `174 passed`, with `test_container_factories.py` and all of
    `test_search_command.py`. Two count pins also moved, 44 to 45 (Deviation 4).

### Mutation run

21 mutants, run by a scratch script. Each one replaces one place in the committed
`semantic_scholar.py` and runs `test_semantic_scholar.py` with `-n 0 -p no:randomly -x` and a fresh
`HYPOTHESIS_STORAGE_DIRECTORY` (no test here uses Hypothesis). Each file is then restored from HEAD
and its bytes compared. `git status` was clean after. All 21 were caught, each at an assertion in the
test aimed at it:

| Mutant | Caught by |
|---|---|
| Key: the header never sent | `test_a_request_with_a_key_sends_it_as_the_x_api_key_header` (its route matches only with the header) |
| Key: an empty header sent without a key | `test_a_request_without_a_key_sends_no_key_header[none]` |
| Key: sent as a query parameter instead of a header | `test_a_request_carries_the_query_the_date_window_the_limit_and_the_fields` (the URL gained `api_key=`) |
| Key: the constructor protects no log | `test_the_adapter_alone_protects_the_logs_from_its_key` |
| Key: a blank key counts as a key | `test_a_request_without_a_key_sends_no_key_header[spaces]` |
| Pace: keyless with no concurrency limit | `test_the_pace_with_a_key_and_without_one_is_the_published_one_request_a_second` |
| Pace: keyed at two a second | the same |
| Pace: no deadline, every query sent | `test_eleven_queries_send_what_fits_…[with a key]` (all eleven asked) |
| Pace: a query too late raises instead of answering partial | the same (outcomes) |
| Pace: the keyless "not asked" without what a key does | `test_eleven_queries_send_what_fits_…[without a key]` |
| Pace: answer times never kept, so the reserve stays 2 s | `test_eleven_queries_send_what_fits_…` (not asked at 8.0 s, not 8.5 s) |
| Mapping: a year-only date given day precision | `test_the_recorded_papers_map_to_the_hand_written_candidates[paper_search]` |
| Mapping: publicationDate ignored, the year always | the same |
| Mapping: the arXiv id dropped | the same |
| Mapping: the PubMed id dropped | the same |
| Mapping: open access read from the PDF link | `…[paper_search_without_pdfs]` (the open dataset with no PDF) |
| Mapping: an untyped paper is other | `test_the_publication_types_map_to_a_source_type[an empty list]` |
| Mapping: the first listed type decides | `…[a dataset that is also an article]` |
| Mapping: the influential citation count taken as the count | `test_the_recorded_papers_map_to_the_hand_written_candidates[paper_search]` |
| Request: hyphens sent as they are | `test_a_request_sends_hyphens_as_spaces_…[one hyphen]` |
| Request: limit not capped at 100 | `test_the_request_parameters_carry_the_window_and_at_most_a_hundred[a hundred and one]` |

One mutant was not run because it is equivalent: swapping `KEYED_PACE` and `KEYLESS_PACE`. The PM
ruled them equal, so no test can tell them apart (Decision 9).

### Checks before the report

* **Dev had not moved** past the generated `ROADMAP.md` refresh (`7216931`), so no sync was needed.
* **Affected set.** `uv run scripts/affected_tests.py` → `143 of 736 test files (19.4%) chosen in
  22.5 s from 26 changed files`. Run once with
  `.venv/bin/python scripts/hard_stop.py 115 uv run scripts/affected_tests.py --run`, it was stopped at
  its 115-second limit at 56% with no failure up to then. It is over two minutes, so by agreement 10
  it is left to the pull request's `ci` check.
* **Within the limit instead**, the changed areas and the always-run list: `tests/architecture
  tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py
  packages/debate_cli/tests/test_container_factories.py packages/debate_core/tests/integrations/discovery
  packages/debate_cli/tests/commands/test_doctor.py packages/debate_cli/tests/commands/test_doctor_providers.py
  packages/debate_cli/tests/test_installation.py packages/debate_cli/tests/test_search_command.py
  packages/debate_cli/tests/test_config_command.py tests/smoke/test_search_smoke.py`, with
  `-m "not slow and not live" -n 6` → `1670 passed in 37.46s`. The machine's load average was 40
  from other sessions.
* **Whole-repo checks.**
  * `uv run --frozen ruff check .` → `All checks passed!`
  * `uv run --frozen ruff format --check .` → `2039 files already formatted`
  * `uv run --frozen pre-commit run check-merge-conflict --all-files` → `Passed`
  * `uv run --frozen pyright` (as CI runs it, 42 s) → `0 errors, 0 warnings, 0 informations`
  * `uv run --frozen lint-imports` → `Contracts: 20 kept, 0 broken.`
  * `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 73 CLI command and API route
    handlers within 25 statements`
  * `uv run --frozen python scripts/validate_specs.py` → `OK: 655 files, 41 epics, 592 tasks, 22
    releases`
  * `uv run --frozen python scripts/docs_index.py --check-descriptions` → `All 69 indexed documents
    under docs/ have a description`
  * `uv run --frozen python scripts/check_links.py` → `OK: 3733 relative links and anchors in 637
    Markdown files`
  * `.venv/bin/python scripts/export_schemas.py --check` → `OK: 10 schemas … are up to date`
  * `uv run --frozen python scripts/check_command_blocks.py --base origin/dev`, with this report →
    `OK: no # comments in 698 shell code blocks in 256 Markdown files (1 session reports changed
    since origin/dev)`

## Files changed

* **The adapter.** `packages/debate_core/src/debate_core/integrations/discovery/semantic_scholar.py`
  (new): the adapter, its request, its type table, its pace constants and its factory.
* **The shared reserve.** `packages/debate_core/src/debate_core/integrations/discovery/pace.py`
  gains `answer_reserve_seconds`, its two constants, `ANSWER_WINDOW` and `AnswerTimes`, moved from
  `crossref.py`. `crossref.py` uses them and still exports the three names; its tests are unchanged
  (commit `feee177`, `223 passed` with `test_pace.py`). `__init__.py`'s index names the new module.
* **Credentials.** `packages/debate_core/src/debate_core/application/provider_credentials.py`:
  Semantic Scholar's credential words, and `PROVIDERS_WITHOUT_AN_ADAPTER` is GDELT alone.
* **The container.** `packages/debate_cli/src/debate_cli/container.py`: `semantic_scholar_factory`
  in the discovery factory map, and its docstring.
* **Tests.**
  * `packages/debate_core/tests/integrations/discovery/test_semantic_scholar.py` (new, 184 tests).
  * `test_doctor.py` and `test_installation.py`: the two pinned lists, the httpx gap, and the two
    counts.
  * `test_doctor_providers.py`: the changed row and a new keyed/blank row test.
  * `test_search_command.py`: the recorded Semantic Scholar route and the container test.
* **Fixtures.** `packages/debate_core/tests/fixtures/discovery/semantic_scholar/` (new: 4
  recordings, 3 bodies, 4 expected lists, README).
* **The guide.** `docs/guides/provider-credentials.md`: the key's row.
* **The spec.** `plan_specs/v1/e07-discovery-adapters/t04-semantic-scholar-adapter.yaml`: the PM's
  rulings as comments (packages, the pace, the fixture path), the session's three files, and the
  phase.

## Deviations from the spec

1. **"A stricter default rate limit without a key"** is, by the PM's ruling 1 of 2026-11-09, the
   published pace with 429 handling. That pace is one request a second, one at a time, keyed and
   keyless alike. The ruling is written above `forbidden:` in the spec. ac1's "per-host interval"
   is likewise the adapter's own `Pacer` at that pace (ruling 2), not `http.per_host_interval_seconds`.
2. **The fixtures** are hand-written from the public documentation, not "recorded", and live at
   `packages/debate_core/tests/fixtures/discovery/semantic_scholar/` instead of
   `tests/fixtures/providers/semantic_scholar/` (ruling 3). The node's path is amended with a
   comment.
3. **Three files beyond ruling 5's list, for the PM to confirm.** Each is in the spec's packages
   with a session comment.
   * `packages/debate_cli/tests/commands/test_doctor_providers.py` pins the row "Semantic Scholar no
     adapter in this build", which taking the provider out of `PROVIDERS_WITHOUT_AN_ADAPTER`
     changes.
   * `packages/debate_cli/tests/test_search_command.py` holds the container test that
     `providers.enabled` naming `semantic_scholar` builds it, with its key in the header. That is
     the proof of the wiring Crossref's ruling asked for (t03), and where Crossref's lives.
   * `docs/guides/provider-credentials.md` said the key does "nothing yet: this build has no
     Semantic Scholar adapter".
4. **The pinned counts.** `test_doctor.py` and `test_installation.py` pin the number of wired
   integrations as well as the list, so 44 becomes 45 in each (`5 of the 45 integrations`, `== 45`).
5. **`test_container_factories.py` needed no change.** It is in ruling 5's list, but building the
   discovery registry imports every factory's module whatever is enabled, so the existing builds
   import the new one. It passes unchanged (in the 174 and 1,670 above).

## Decisions and assumptions

1. **One request per query, at most 100 results.** The endpoint's `limit` must be at most 100, and
   `SearchFilters.max_results` allows 200. A query asking for more gets at most 100 from Semantic
   Scholar, not a second page, because a second page would take a second paced turn for the same
   query. The answer is not marked partial: `max_results` is a ceiling.
2. **The URL** is `https://doi.org/<doi>` when there is a DOI, as for OpenAlex and Crossref, so
   dedupe sees one URL across the three. Otherwise it is the paper's page,
   `https://www.semanticscholar.org/paper/<paperId>` (the id percent-encoded), which is what the
   documented `url` field holds. `url` is not in the spec's field list, so it is not asked for.
3. **Hyphens are sent as spaces.** The documentation says "Hyphenated query terms yield no matches
   (replace it with space to find matches)". Runs of whitespace become one space, and a query that
   would be left empty is sent as it was. Pinned by the `direct air-capture costs` recording.
4. **Source types.**
   * All thirteen documented `publicationTypes` are mapped: News is news, Dataset is other, and
     the rest are scholarly.
   * A paper is scholarly if any of its types is, otherwise news if any is, otherwise other.
   * A paper with no readable type is scholarly. Semantic Scholar indexes papers and leaves many
     untyped (often preprints), and calling those "other" would mislabel most of them.
   * Types are compared without spaces or case, because the documentation's field example spells
     `Journal Article` where the filter says `JournalArticle`.
5. **Dates** follow ruling 4 strictly.
   * A `publicationDate` that is a real `YYYY-MM-DD` is a day.
   * Anything else (`null`, an impossible day, `2022-05`, words) falls to `year` at year precision.
   * A year that is not an integer from 1 to 9999 gives no date. A `2022-05` is not given month
     precision, because the documented format is a full date only.
6. **Open access.**
   * `open_access` is `isOpenAccess` when it is a boolean, and unknown otherwise.
   * The open copy is `openAccessPdf.url` when it is an absolute http(s) URL with no spaces.
   * Semantic Scholar sends `"url": ""` for an open paper it knows no PDF for; that is open access
     with no copy (the fixture's dataset).
7. **`influentialCitationCount`** is in `fields=`, as the spec lists it, but `CandidateResult` has no
   field for it and the domain is outside this task, so it is read nowhere (Follow-up 2).
8. **Identifiers.**
   * The DOI goes through `ArticleIdentifiers`, the one DOI rule (lower case, resolver prefixes
     stripped, a non-DOI dropped).
   * `PubMed` is kept only as a string of digits.
   * `ArXiv` is kept as given, whitespace trimmed.
   * `MAG`, `DBLP`, `ACL`, `PubMedCentral` and `CorpusId` are not kept: `ArticleIdentifiers` has no
     field for them.
9. **Two pace constants of equal value.** `KEYED_PACE` and `KEYLESS_PACE` are both
   `Pace(requests=1, interval_seconds=1.0, concurrency=1)`, each with the source and date in a
   comment. A later ruling can then change one without touching the other. Swapping them is an
   equivalent mutant.
10. **The "not asked" words.**
    * With a key: `semantic_scholar: not asked: the pace is 1 query a second`.
    * Without one, it adds `; an API key would identify this caller but raises nothing today`.
    * As Crossref's, it is logged at INFO on the protected discovery logger, and answered at the
      deadline.
11. **A `3xx`** is `redirect_failure`, naming only the host, as the government adapters do, rather
    than an unreadable body. A `403` (a key Semantic Scholar refuses) is the shared refusal,
    `HTTP 403: the provider refused the request`, and counts as a breaker failure like any refusal.
12. **An answer with no `data`** is an empty answer only when `total` is 0; any other answer without
    a list of paper objects is `unreadable response: not a paper list`.
13. **The credential words**:
    * with a key: `API key set (<source>)`;
    * without one: `no Semantic Scholar key: the shared pool, paced at one request a second`.
14. **The shared reserve** is a small class, `AnswerTimes` (the last 50 answers' median, clamped),
    rather than a moved function alone. Both adapters then keep the same window and the same clamp,
    and Crossref's `reserve_seconds` is unchanged in value.
15. **Documentation read.** The API docs page (api.semanticscholar.org/api-docs/graph) is rendered
    by script. I read the OpenAPI description it loads, `api.semanticscholar.org/graph/v1/swagger.json`,
    on 2026-11-09: a documentation file, fetched by a docs reader, with no search, no key and no
    other request to the API. It is served from the API's host, so the PM may prefer that a session
    leaves it to the operator next time. The rate limits are the PM's reading of
    semanticscholar.org/product/api; the session did not re-read that page.

## Operator follow-ups

Optional, for after the merge, once an installed build carries this change. It is the live smoke
ruling 3 leaves to the operator; Semantic Scholar stays enabled in no profile until it passes.

1. **Live smoke without a key.** Run from any folder: the per-user credentials file is read from
   wherever you are. The block makes two searches with Semantic Scholar alone enabled and its key
   blanked for these commands only: one query, and an expanded search of up to 8 (`heg`/`answers`).
   Each takes a few seconds and costs nothing. Like any search, it writes the searches, and up to 20
   discovery-only Articles, to your local dev store. It prints only statuses, counts and the
   providers' reasons, never a title, a name or a key. Success looks like this:
   * single run: `status: COMPLETE`, `semantic_scholar: ok`, `results:` above zero, `with an S2
     id` equal to `results`, `breaker: closed, errors 0`;
   * expanded run: `status: COMPLETE` or `PARTIAL`, `results:` above zero, and if partial, only the
     reason `not asked: the pace is 1 query a second; an API key would identify this caller but
     raises nothing today`.

   What a failure says:
   * `HTTP 400` in a reason means Semantic Scholar refused a field or the date window;
   * `HTTP 429` means the shared keyless pool throttled us, which its page says can happen under
     heavy use.

   Either way, please paste the output back.

   ```bash
   env -u DEBATE_STORAGE__DATA_DIR -u DEBATE_ENV DEBATE_PROVIDERS__ENABLED='["semantic_scholar"]' DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY= debate-research search "carbon capture subsidies" --format json > s2-smoke-single.json
   env -u DEBATE_STORAGE__DATA_DIR -u DEBATE_ENV DEBATE_PROVIDERS__ENABLED='["semantic_scholar"]' DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY= debate-research search "us hegemony" --argument heg --need answers --format json > s2-smoke-expanded.json
   for run in single expanded; do python3 - "s2-smoke-$run.json" "$run" <<'EOF'
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
   print(f"with an S2 id: {sum(1 for item in results if item['identifiers'].get('semantic_scholar_id'))}")
   print(f"with a DOI: {sum(1 for item in results if item['identifiers'].get('doi'))}")
   print(f"dated: {sum(1 for item in results if item['published_at'])}")
   calls = body.get("provider_calls") or []
   print(f"calls not asked: {sum(1 for call in calls if call['partial'])} of {len(calls)}")
   for health in body.get("provider_health") or []:
       print(f"breaker: {health['state']}, errors {health['error_count']}")
   EOF
   done
   rm s2-smoke-single.json s2-smoke-expanded.json
   ```

2. **Live smoke with a key**, only if `~/.debate-research/dev.env` holds a
   `DEBATE_PROVIDERS__SEMANTIC_SCHOLAR_API_KEY` line. `debate-research doctor --providers` says
   whether it does, naming the file, never the key. This is one search with the key sent. Success is
   the single run's lines above, and the reason `not asked: the pace is 1 query a second` if any.
   `HTTP 403` means Semantic Scholar refused the key.

   ```bash
   env -u DEBATE_STORAGE__DATA_DIR -u DEBATE_ENV DEBATE_PROVIDERS__ENABLED='["semantic_scholar"]' debate-research search "carbon capture subsidies" --format json > s2-smoke-keyed.json
   python3 - s2-smoke-keyed.json keyed <<'EOF'
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
   print(f"with an S2 id: {sum(1 for item in results if item['identifiers'].get('semantic_scholar_id'))}")
   for health in body.get("provider_health") or []:
       print(f"breaker: {health['state']}, errors {health['error_count']}")
   EOF
   rm s2-smoke-keyed.json
   ```

## Follow-up work

1. **Enable Semantic Scholar in the committed profiles** once the live smoke passes, as v1-e07-t13
   did for the providers that passed theirs. The PM files it, or folds it into that task's
   successor.
2. **`influentialCitationCount` has nowhere to go.** `CandidateResult` has one `citation_count`. If
   ranking should weigh influential citations, that is a domain field (E07 or E08). Until then the
   adapter could stop asking for it; the spec lists it, so it is asked for today.
3. **More than 100 results from one query** would need a second page (`offset=100`) and a second
   paced turn. `SearchFilters.max_results` defaults to 20, so this only matters if searches for more
   than 100 per query become common.
4. **v1-e07-t17** (providers without an adapter pinned to the factories) now starts from GDELT
   alone in `PROVIDERS_WITHOUT_AN_ADAPTER`.
5. **The breaker and a key Semantic Scholar refuses.** A refused key (`403`) is a refusal like any
   other, so three in a row bench Semantic Scholar for the cool-down. A clearer answer, such as
   "key refused: unset it or replace it", would need a wording choice for every keyed provider
   (OpenAlex, GovInfo too). It may fit beside v1-e07-t15 (a provider without its key); the PM
   decides.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
