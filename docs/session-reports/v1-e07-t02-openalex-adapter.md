# Session report: v1-e07-t02-openalex-adapter

| | |
|---|---|
| Task | `v1-e07-t02-openalex-adapter` — OpenAlex adapter |
| Spec | [`plan_specs/v1/e07-discovery-adapters/t02-openalex-adapter.yaml`](../../plan_specs/v1/e07-discovery-adapters/t02-openalex-adapter.yaml) |
| Epic / release | `v1-e07-discovery-adapters` / `v1.4` |
| Branch | `task/v1-e07-t02-openalex-adapter` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`OpenAlexProvider` (`debate_core.integrations.discovery.openalex`) searches OpenAlex's `/works`. Each
search sends one `GET` with `search=`, the date window as `from_publication_date`/`to_publication_date`
filters, `per_page` capped at 100, and a `select=` of the fields it maps. It maps works to
`CandidateResult`s: DOI, OpenAlex id, title, author display names, venue, date, a source type from a
one-place table, the rebuilt abstract and the best open-access URL. It passes the contract kit with a
key, without one, and on an empty result. `openalex_factory` builds it for the registry, which wraps it
in `ResilientProvider`.

**Look at this first:** OpenAlex retired its mailto polite pool in February 2026. On the PM's ruling of
2026-10-21 (option C), the adapter sends an optional `providers.openalex_api_key` as
`Authorization: Bearer`, and OpenAlex no longer receives the contact email. The spec was amended to
match.

**Why the Goal stays InProgress:** ac2 asks for `cited_by_count`, but `CandidateResult` has no field for
it. My second question to the PM (add `citation_count` to `CandidateResult` now, or drop it from ac2)
has had no ruling, so that part of ac2 is not done. Everything else passes. The question is repeated
under Deviations, ready to relay.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `record-fixtures` (Record OpenAlex fixtures) | Done | Hand-written from the documented Work object, not captured. They live at the path the PM's ruling set, `packages/debate_core/tests/fixtures/discovery/openalex/`, beside the fake provider's. |
| `request-builder` (Query and filter request builder) | Done | Built after the PM's authentication ruling, as asked: no request code existed before it. |
| `result-mapping` (Work to CandidateResult mapping) | Done except `cited_by_count` | The mapping was written first, while the ruling was pending, because the ruling could not change it. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 (as amended): a query with since/until sends the date filters, and the API key in the Authorization header when configured, verified by respx route assertions | PASS | `test_a_request_with_since_and_until_carries_the_date_filters_and_the_key_header`: a respx route matching `search`, `filter=from_publication_date:2020-01-01,to_publication_date:2024-12-31`, `per_page`, `select` and `Authorization: Bearer <key>` is called exactly once. Keyless: `test_a_request_without_a_key_has_no_authorization_header_and_no_mailto`. A blank key counts as none: `test_a_request_with_a_blank_key_is_sent_keyless`. |
| ac2: recorded fixtures map to CandidateResults with DOI, OpenAlex id, authors, venue, published_at, cited_by_count and best OA URL; abstracts rebuilt in word order | FAIL (cited_by_count only) | Everything but `cited_by_count` passes: `test_the_recorded_works_map_to_the_hand_written_candidates`, the kit's `test_the_recording_maps_to_the_expected_results` and `test_the_abstract_is_rebuilt_in_word_order` (11 cases). `cited_by_count` is not mapped, because `CandidateResult` defines no field for it and the PM's brief says to store only what it defines. The PM's ruling on that is pending (Deviations). |
| ac3: 429 and 5xx map to typed ProviderErrors consumed by the circuit breaker; the kit passes | PASS | 429 with `Retry-After: 30` → `ProviderRateLimited(30)`. A spent daily budget (429, no `Retry-After`) → `ProviderRateLimited(None)`. A date `Retry-After` is read against the injected clock (90 s). 503 with `Retry-After` → `ProviderUnavailable`. Through the registry: two 503s open the breaker and the third call sends nothing (`ProviderCircuitOpen`). A 429 holds the provider for 30 s, a spent budget for the cool-down. Kit: 3 bindings × 8 checks, all pass. |
| ac4 (PM amendment): passes the kit in `debate_core.integrations.discovery` on its recordings; secrets never reach a log line; tests pass in one process after the OpenCaselist and discovery suites | PASS | Kit bindings in `test_openalex.py`. The kit's `test_no_secret_surfaces` runs with `(API_KEY, CONTACT_EMAIL)` in its secrets. `test_no_secret_reaches_a_log_line_an_error_a_repr_or_a_health_snapshot` and `test_the_adapter_alone_protects_the_logs_from_its_key` (7 loggers) cover the rest. One process: `.venv/bin/python -m pytest packages/debate_core/tests/integrations/opencaselist packages/debate_core/tests/integrations/test_http_fetcher.py packages/debate_core/tests/integrations/discovery/test_redaction.py packages/debate_core/tests/integrations/discovery/test_resilience.py packages/debate_core/tests/integrations/discovery/test_registry.py packages/debate_core/tests/integrations/discovery/test_http_failures.py packages/debate_core/tests/integrations/discovery/test_fake_provider.py packages/debate_core/tests/integrations/discovery/test_openalex.py -n 0 -p no:randomly -q` → `507 passed`. Collection confirmed every file ran in that order, OpenAlex's 137 last (139 after the blank-key test was added). |
| Node `record-fixtures`: artifact `packages/debate_core/tests/fixtures/discovery/openalex/works_search.json` exists (path as amended) | PASS | `ls -l` → 717 bytes. |
| Node `request-builder`: `uv run pytest packages/debate_core/tests/integrations/discovery/test_openalex.py -k request` | PASS | `15 passed in 2.23s` |
| Node `result-mapping`: `uv run pytest packages/debate_core/tests/integrations/discovery/test_openalex.py` | PASS | `139 passed in 2.39s`. It passes as a command, but ac2's `cited_by_count` is not in what it checks. |

### Red run, mutation and checks

* **Red run.** The current tests ran against a refuse-nothing skeleton: real signatures, every type
  scholarly, no filters, no header, no error mapping. The skeleton sat in a scratch copy of the source,
  first on `PYTHONPATH`, and its `__file__` was printed to confirm it was the code under test. Result:
  `96 failed, 34 passed`. The 34 pass for these reasons:
  * the 17 scholarly rows of the type table (the skeleton calls everything scholarly);
  * 5 abstract cases whose answer is `None` or plain order;
  * 4 cases whose expected date is `None`, and 3 whose expected OA URL is `None`;
  * "a DOI that is not a DOI is dropped" (the skeleton keeps no DOI);
  * "no ORCID or affiliation" (vacuous: the skeleton stores nothing, so the raw-author-name mutant
    below was run to show this test bites);
  * the kit's three "is a search provider with a name" checks.

  The most common failure lines were `AllMockedAssertionError` (34: the request did not match the
  recorded one) and `SourceType.SCHOLARLY is SourceType.OTHER` (16).
* **Mutation**, capped as asked at the request parameters, the abstract rebuild and the error mapping:
  23 mutants, all killed. Each ran on a scratch copy with a fresh `HYPOTHESIS_STORAGE_DIRECTORY`
  (the file uses no Hypothesis). The whole run took 21 s.

  | Area | Mutant | Killed by |
  |---|---|---|
  | request | `per_page` not capped / cap 200 | `test_the_request_parameters[101 asks for 100]` |
  | request | `since` sent as `to_` / `since` dropped / `until` dropped / filters joined with `\|` | the respx route test |
  | request | `select` drops the abstract | the respx route test |
  | request | key without `Bearer` / key also in the URL | the respx route test |
  | request | header sent without a key | `test_a_request_without_a_key_has_no_authorization_header_and_no_mailto` |
  | logs | constructor skips `protect_logs` | `test_the_adapter_alone_protects_the_logs_from_its_key` |
  | abstract | positions not sorted / no spaces / position 0 refused / bool positions accepted / empty gives `""` | `test_the_abstract_is_rebuilt_in_word_order` cases |
  | errors | status ignored | `test_a_429_with_retry_after_is_rate_limited_for_that_long` |
  | errors | `Retry-After` read on the wall clock | `test_a_retry_after_given_as_a_date_is_read_against_the_injected_clock` |
  | errors | timeout reported as a transport failure | `test_a_transport_failure_is_unavailable_and_keeps_its_cause[timeout]` |
  | errors | parse failure leaks / non-object works accepted / `max_results` not kept | their own tests |
  | mapping | authors from `raw_author_name` | 5 tests, including the "no ORCID or raw author name" test |

  While choosing mutants I saw that the `protect_logs` mutant could not fail any test then in the file:
  the only log test went through the registry, whose wrapper calls `protect_logs` too. So
  `test_the_adapter_alone_protects_the_logs_from_its_key` was added before the run. This is reasoning,
  not a measured survival: the mutant was never run against the file without that test.
* **Blank key.** `test_a_request_with_a_blank_key_is_sent_keyless` was shown failing against the
  previous constructor, which sent `Authorization: Bearer ` with nothing after it, before the fix.
* **Kit bites on this binding.** `test_the_kits_secrets_check_catches_a_key_sent_in_the_url` runs the
  kit's secrets check on an adapter that sends the documented `api_key=` parameter. The check fails it
  with `log record on httpx: HTTP Request: GET`.

### Before the report (working agreement 10)

* `uv run scripts/affected_tests.py` → 310 test files. `settings.py` changed and the root
  `conftest.py` imports it, so almost every test is selected. That is well over two minutes, so as
  agreement 10 says, it is left to the pull request's `ci` check and not handed to the operator.
* Within the two minutes, the changed test directories and the always-run list:
  `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" packages/debate_core/tests/integrations/discovery packages/debate_core/tests/application packages/debate_cli/tests/test_config_command.py tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py -q`
  → `3221 passed in 88.83s` (load average 25 at the time). The first attempt also included
  `tests/smoke/test_cli_smoke.py`; the alarm stopped it at 115 s and its count was not read. The one
  smoke test this branch edited was then run alone:
  `.venv/bin/python -m pytest -n 0 -m "not slow and not live" tests/smoke/test_cli_smoke.py -k config_show_redacts`
  → `1 passed`.
* `uv run ruff format --check .` → `1038 files already formatted`. `uv run ruff check .` → `All checks passed!`
* `.venv/bin/pyright packages/debate_core` → `0 errors` (13.9 s).
* `uv run lint-imports` → `Contracts: 13 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 404 files, 39 epics, 344 tasks, 21 releases`

## Files changed

* `packages/debate_core/src/debate_core/integrations/discovery/openalex.py` (new): the adapter, the
  request parameters, the type table, the abstract rebuild, the mapping and `openalex_factory`.
* `packages/debate_core/src/debate_core/integrations/discovery/__init__.py` and `redaction.py`:
  docstrings now name the adapter and say OpenAlex's key goes in a header.
* `packages/debate_core/src/debate_core/application/settings.py`: `providers.openalex_api_key`
  (`SecretStr | None`). `contact_email`'s description now says Crossref only.
* `.env.example`, `packages/debate_core/tests/application/test_settings.py` and
  `tests/smoke/test_cli_smoke.py`: the new secret is documented (commented out), checked absent from
  committed profiles, and included in `config show`'s redaction smoke test, beside the other provider
  secrets.
* `packages/debate_core/tests/fixtures/discovery/openalex/` (new): hand-written recordings, bodies,
  expected mappings and a README.
* `packages/debate_core/tests/integrations/discovery/test_openalex.py` (new): 139 tests, including
  the three contract-kit bindings and a copy of `replay_with_respx`.
* `plan_specs/v1/e07-discovery-adapters/t02-openalex-adapter.yaml`: the PM's amendments (Deviations).

## Deviations from the spec

* **OpenAlex authentication (PM ruling 2026-10-21, option C).** OpenAlex's deprecations page says the
  mailto polite pool was "replaced by API keys" in February 2026 and "the `mailto` parameter is
  ignored". Its authentication page, updated 2026-10-15, says keyless requests still work, at 10
  requests a second and a $0.10 daily budget. That is about 100 searches a day; a free key gives about
  1,000 (help.openalex.org/api/deprecations, /api/authentication and /access/example-costs, read
  2026-10-21). These spec changes were made, each with the ruling's comment:
  * the description now says the key goes in the Authorization header;
  * ac1 was amended;
  * the forbidden entry is now "Omitting the configured OpenAlex API key";
  * `debate_core.application.settings` was added to `packages`;
  * the `record-fixtures` node's path, outputs and description now point at
    `packages/debate_core/tests/fixtures/discovery/openalex/` and hand-written fixtures;
  * the `request-builder` description now names the key header.

  The ruling also implied three changes outside the listed packages, all made in the same commit:
  `.env.example` and the secret checks in `test_settings.py` and `tests/smoke/test_cli_smoke.py`. An
  existing test requires `.env.example` to document every provider secret.
* **The spec's fixture topics.** The node named "health insurance, AI regulation, space policy
  queries; empty result; 429". The fixtures follow the PM's brief instead: one search body with the
  listed features, an empty result, a 429 with `Retry-After`, a spent-budget 429, a 503 with
  `Retry-After`, and a malformed body.
* **`cited_by_count` (ac2) — awaiting the PM.** I sent the question below while the authentication
  ruling was pending; it was not answered. Paste-ready:

  ```text
  PM: v1-e07-t02, one open item before the Goal can be Succeeded.

  ac2 says works map to CandidateResults "with ... cited_by_count". CandidateResult has no citation
  field, and your brief says "store only what CandidateResult defines", so ac2 can't pass as worded.
  v1-e08-t02 (normalize-dedupe) expects "OpenAlex/S2 for citation counts" in its merge precedence, and
  v1-e08-t03 ranks on "log-scaled citation count".

  A. (Recommended) Add `citation_count: int | None = Field(default=None, ge=0)` to CandidateResult in
     debate_core/domain/discovery.py, add debate_core.domain to this task's packages, select
     cited_by_count and map it. The default is None, so the FakeProvider, its fixtures and
     v1-e08-t01's stored ProviderStatus records are unaffected. About 15 minutes of work, including
     the hand-written expectation.
  B. Drop cited_by_count from ac2, and let v1-e08-t02 or t03 add the field and back-fill the OpenAlex
     mapping later.

  Why A: the adapter already has the number in hand, and E08 needs it. With B, t02 and t04 (Semantic
  Scholar) both drop it now and get reopened later.

  Reply A or B.
  ```

## Decisions and assumptions

* **Venue, page size and type table** are as the PM accepted them.
  * The venue is `primary_location.source.display_name`, since `host_venue` is gone.
  * `per_page = min(max_results, 100)`, one page. The module docstring says a request above 100
    returns at most 100.
  * In the type table, journal, book, conference and thesis types map to scholarly; `report` and
    `standard` map to other; everything else and unknown types map to other.
* **The URL** is the primary location's landing page, then `https://doi.org/<doi>`, then the OpenAlex
  record (`https://openalex.org/W…`), which every work has.
* **The open-access URL** is the best OA location's PDF, then its landing page, and only if that
  location is itself open. Otherwise it is `open_access.oa_url` when the work is open, otherwise none.
* **What a work tolerates.** A work with no title or no OpenAlex id is skipped. A DOI, date or URL that
  doesn't validate is dropped rather than failing the search. A body without a list of work objects,
  or unparseable JSON, is `ProviderUnavailable`.
* **Authors** are only the disambiguated `author.display_name`. An authorship OpenAlex couldn't match
  to an author is left out rather than using `raw_author_name`, per "display names only".
* **No retries.** One request per search. The kit bindings set `max_attempts` to 1 to hold that.
* **A blank key is no key**, so an empty `DEBATE_PROVIDERS__OPENALEX_API_KEY=` line in `.env` does not
  send `Bearer ` with nothing after it.
* **The client** is built from `HttpSettings`: the fetcher's User-Agent and timeouts, no cookies,
  `trust_env=False`. The adapter owns it; `aclose()` closes it.
* **Not applied:** `SearchFilters.source_types` and `language`. The spec names only the date filters,
  and `FederatedSearchService` applies neither today. See Follow-up work.

## Operator follow-ups

1. **Setting the key.** Get a free key at https://openalex.org/signup (Settings, API key). Put it in
   the gitignored `.env` in the directory the CLI runs from, or export it in the shell, as
   `DEBATE_PROVIDERS__OPENALEX_API_KEY=<key>`. Never put it in `config/profiles/*.toml`: those are
   committed, and `test_no_committed_profile_contains_anything_that_looks_like_a_secret` fails on one.
   To confirm it is read and redacted, run this; it takes about a second and should show
   `providers.openalex_api_key` as the redaction placeholder, never the key:

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e07-t02-openalex-adapter
   uv run debate-research config show
   ```

2. **Optional live smoke**, one search with the key and one without. Run it from the worktree whose
   `.env` holds the key. It takes a few seconds per mode and costs about $0.002 of OpenAlex budget. It
   prints only status, counts and field presence: no titles, names or key. Success looks like this
   for both modes:
   * `outcome: answered | HTTP status: 200`;
   * `mailto sent: False`;
   * `authorization sent: True` in the keyed mode and `False` in the keyless one;
   * `works returned: 25` and `candidates mapped: 25`, or close to it;
   * nonzero counts for `doi`, `primary_location`, `authorships` and `abstract_inverted_index`.

   Please paste the output back. The `rate-limit headers present:` line also tells us whether OpenAlex
   sends `Retry-After` on its 429s.

   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e07-t02-openalex-adapter
   for mode in keyed keyless; do uv run python - $mode <<'EOF'
   import asyncio
   import json
   import sys
   from collections import Counter
   from datetime import UTC, datetime

   import httpx

   from debate_core.application.errors import ProviderError
   from debate_core.application.settings import load_settings
   from debate_core.domain.discovery import ProviderQuery
   from debate_core.domain.search import SearchFilters
   from debate_core.integrations.discovery.openalex import SELECTED_FIELDS, openalex_factory


   class WallClock:
       def now(self):
           return datetime.now(UTC)


   seen = {}


   class Watching(httpx.AsyncHTTPTransport):
       async def handle_async_request(self, request):
           response = await super().handle_async_request(request)
           await response.aread()
           seen["status"] = response.status_code
           seen["limit headers"] = sorted(
               name for name in response.headers if name.lower().startswith(("x-ratelimit", "retry-after"))
           )
           seen["authorization sent"] = "authorization" in request.headers
           seen["mailto sent"] = "mailto" in str(request.url)
           seen["body"] = response.content
           return response


   keyless = sys.argv[1:] == ["keyless"]
   settings = load_settings(overrides={"providers": {"openalex_api_key": None}} if keyless else None)
   build = openalex_factory(settings.http, version="smoke", clock=WallClock(), transport=Watching())
   provider = build(settings.providers)
   query = ProviderQuery(
       query="health insurance", filters=SearchFilters(since=datetime(2023, 1, 1, tzinfo=UTC), max_results=25)
   )
   try:
       results = asyncio.run(provider.search(query)).results
       outcome = "answered"
   except ProviderError as error:
       results = ()
       outcome = type(error).__name__
   print("mode:", "keyless" if keyless else "with key", "|", repr(provider))
   print("outcome:", outcome, "| HTTP status:", seen.get("status"))
   print("authorization sent:", seen.get("authorization sent"), "| mailto sent:", seen.get("mailto sent"))
   print("rate-limit headers present:", seen.get("limit headers"))
   try:
       works = json.loads(seen.get("body") or b"{}").get("results", [])
   except ValueError:
       works = []
   print("works returned:", len(works), "| candidates mapped:", len(results))
   for field in SELECTED_FIELDS:
       present = sum(1 for work in works if work.get(field) not in (None, {}, [], ""))
       print(f"  works with {field}: {present}")
   print("candidates with doi:", sum(1 for r in results if r.identifiers.doi))
   print("candidates with venue:", sum(1 for r in results if r.publication))
   print("candidates with date:", sum(1 for r in results if r.published_at))
   print("candidates with abstract:", sum(1 for r in results if r.snippet))
   print("candidates with open access url:", sum(1 for r in results if r.open_access_url))
   print("candidates with authors:", sum(1 for r in results if r.authors))
   print("source types:", dict(Counter(r.source_type.value for r in results)))
   print("work types:", dict(Counter(str(work.get("type")) for work in works)))
   EOF
   done
   ```

   The script was checked offline: a mock transport served `works_search.body.json` in place of the
   network, and it printed 3 works, 3 candidates, 2 with a DOI, 2 with an OA URL and 1 with an
   abstract. In keyless mode it showed `authorization sent: False | mailto sent: False`.

## Follow-up work

* **Wiring OpenAlex into the CLI's registry** (`SearchProviderName.OPENALEX: openalex_factory(...)`)
  and closing adapters' clients when the CLI exits belong to `v1-e08-t05-search-command`, which builds
  `ProviderRegistry.from_settings`. `ProviderRegistry` and `ResilientProvider` have no `aclose`, so
  t05 or the registry will need one for adapters that own a client.
* **`SearchFilters.source_types` and `language`** are applied by neither the adapters nor
  `FederatedSearchService`. OpenAlex supports a `language` filter. Which layer applies them is for E08
  (t01's owner, or t02/t03) to decide.
* **`citation_count`** (Deviations), if the PM chooses B.
* `.venv/bin/pyright tests/smoke/test_cli_smoke.py` reports 7 errors at lines 257 to 265
  (`"__getitem__" method not defined`). They predate this branch; its only change to that file is
  line 151. CI's pyright step covers `packages/`.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on one condition closed in this session before the pull request: your open question on
`cited_by_count`, answered below as **A, widened by one field**. When it is done, ac2 passes. Set the
Goal `Succeeded`, and the pull request opens with no `--partial`. As before, if anything comes out
differently from what you expect, stop and ask for another review.

**The condition: `citation_count` and `open_access` on `CandidateResult`.**

1. Add `citation_count: int | None = Field(default=None, ge=0)` and `open_access: bool | None = None`
   to `CandidateResult` in `debate_core/domain/discovery.py`.
   * v1-e08-t03 (ranking) needs both: log-scaled citations, and open-access status.
   * `open_url` alone cannot say "open but no usable link".
2. Select `cited_by_count` and `open_access` (if `select=` does not already carry the latter), and
   map `cited_by_count` and `open_access.is_oa`. A missing or non-integer count, or a negative one,
   becomes `None` rather than failing the search, as your other fields do.
3. **Tests, shown failing first:**
   * the hand-written expected candidates gain both values;
   * the domain model refuses a negative count;
   * both fields default to `None`;
   * the FakeProvider's kit bindings and v1-e08-t01's stored `ProviderStatus` round trip still pass.
4. Add `debate_core.domain` to the spec's packages with a comment
   `PM ruling 2026-10-22 (v1-e07-t02 Q2: A, with open_access, for v1-e08-t02 ruling 4)`.
5. **Don't touch `federated_dedupe.py`.** v1-e08-t03 adds the precedence rows (OpenAlex, then
   Semantic Scholar) by a PM amendment.

**What is good:**

* **The authentication change was handled the right way.** You read the current docs and stopped
  for a ruling before writing request code. The spec changes carry the ruling's comment and the
  pages and date read.
* **The key never reaches a URL or a log.** The kit's secrets check is shown biting on an adapter
  that sends the documented `api_key=` parameter, with httpx's own log line the failure. A blank key
  is no key: that was shown failing first, and it closed a real `Bearer ` with nothing after it.
* **A spent daily budget is told apart from a per-second limit** by the absence of `Retry-After`,
  and the date form of `Retry-After` is read on the injected clock. Both are tested, and the breaker
  is shown opening through the registry.
* **The red run accounts for its 34 passes one by one,** including the vacuous ORCID test, which a
  separate mutant then shows biting. Your note that the `protect_logs` mutant could not have failed
  is honestly labelled as reasoning, not a measurement.
* **The one-process run** (OpenCaselist, the fetcher, the discovery suites, then OpenAlex last) is
  exactly the check working agreement 10 now asks for.

**Rulings on the rest:**

* **Deviations: accepted.** That covers the authentication changes, `.env.example` and the two
  secret checks outside the packages (an existing test requires them), and the fixture topics
  following the PM's brief.
* **Decisions: accepted.**
  * Leaving out authorships OpenAlex could not match is the conservative choice, and it costs only
    dedupe recall, never a false merge.
  * One request per search is right while the wrapper owns retries.
* **Operator follow-ups:** setting the key is the operator's, whenever convenient. The live smoke
  is optional and does not hold the pull request. If it is run, the `rate-limit headers present`
  line goes into v1-e07-t08's notes.

**Follow-ups, placed by the PM in the next batch:**

* **v1-e08-t05:** register `openalex_factory` in the CLI's registry, and give `ProviderRegistry` (or
  `ResilientProvider`) an `aclose` so adapters that own a client are closed when the CLI exits.
* **E08:** which layer applies `SearchFilters.source_types` and `language`, decided in v1-e08-t03's
  amendment. OpenAlex's `language` filter is noted there.
* **The `tests/smoke/test_cli_smoke.py` pyright errors** are covered by v1-e01-t31, which already
  makes `pyright tests/smoke` clean.
