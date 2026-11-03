# Session report: v1-e08-t05-search-command

| | |
|---|---|
| Task | `v1-e08-t05-search-command` — `debate-research search` command |
| Spec | [`plan_specs/v1/e08-research-workflows/t05-search-command.yaml`](../../plan_specs/v1/e08-research-workflows/t05-search-command.yaml) |
| Epic / release | `v1-e08-research-workflows` / `v1.4` |
| Branch | `task/v1-e08-t05-search-command` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

`debate-research search "<query>"` is built. It has every flag in the spec and the PM's amendments:
`--since`, `--until`, `--max-results`, `--argument`, `--need`, `--topic`, `--var NAME=VALUE`,
`--providers`, `--expand-llm`, `--format table|json` (and `--json`), and `--save`. The container is the
composition root. It builds `FederatedSearchService` over `ProviderRegistry.from_settings` with the
OpenAlex, feed and Google News factories, under the new `providers.search_deadline_seconds` (15 s), and
closes every provider when the search ends. The stages are the taxonomy's `QueryExpansionStage` (with a
guard only under `--expand-llm`), `DedupeStage`, and the rank stage followed by a new
`ArticleMatchingStage`. That stage turns the ranking into stored results through Articles and never
fetches. The table and the JSON carry rank, score, the seven features, the explanation, identifiers
and provider sources, and never a snippet or abstract. A provider status footer names every provider
and why it did not answer.

Exit codes follow the PM's ruling, written into the spec as a dated amendment: 0, 6 (`SEARCH_PARTIAL`),
7 (`NO_RESULTS`), 3 and 2, plus 1 when no selected provider is enabled. ac1 to ac5 and every node
criterion pass on recorded fixtures. ac6, the coach's labels with nDCG@10, is **NOT RUN**: it needs real
searches after the merge and the coach's labels. **The phase stays InProgress, so expect `--partial`.**

Look at these first:

1. The dev and prod profiles. They enabled `crossref`, and prod also `semantic_scholar`, which have no
   adapter yet (E07 t03/t04 are Pending). The registry refuses to build any search while they are
   enabled, so `search` could not have run on dev or prod at all. I changed both profiles to
   `["openalex", "rss"]`, outside the packages first listed, and the new smoke check ran red on it
   first. See Deviations 3.
2. Questions 1 to 4 for the PM, bundled under Follow-up work.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `command-options`: Typer command, options and validation | Done | `commands/search.py`. Date parsing; choice validation for `--providers` from `SearchProviderName` and for the expansion from the taxonomy (through `UnknownExpansionChoice`); the container's `federated_search` and `discovery_providers`. Core pieces: `ArticleMatchingStage`, `StagesInOrder`, `SearchOutcome.ranked_candidates`/`articles`, `aclose` on `ResilientProvider` and `ProviderRegistry`, and the deadline setting. |
| `presenters`: Rich table, JSON output and provider footer | Done | `presenters/search_presenter.py`. The table and footer go to stdout. With no rows, the footer goes to stderr above the failure panel. Progress goes to stderr as event lines. JSON mode prints one envelope on stdout. |
| `cli-fixture-tests`: CLI tests on recorded provider fixtures | Done | `packages/debate_cli/tests/test_search_command.py`, 37 tests over synthetic recorded fixtures in `packages/debate_cli/tests/fixtures/search/`, through the registry override. Also core tests and an installed-build smoke check. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `search "midterm elections" --since 2026-09-14 --max-results 20` on recorded fixtures prints at most 20 ranked, deduped rows and a provider status footer, exiting 0 | PASS | `test_presenter_table_shows_ranked_deduplicated_rows_and_the_provider_footer`: exit 0. The 4 rows written by hand from the fixtures: OpenAlex's three works plus two Courier items, of which one is the second work's URL. The turnout source appears once, the out-of-window and non-matching items are absent, and the footer is exactly `Providers: COMPLETE` / `openalex: ok, 3 results` / `rss: ok, 2 results`. `test_presenter_max_results_caps_the_rows` covers the cap (`--max-results 2` gives ranks `[1, 2]`). |
| ac2: `search "health insurance" --argument politics-da --need link --format json` emits a JSON array whose items include rank, score, features, explanation, identifiers and provider sources | PASS (the array is `data.results` in the CLI's envelope: Deviations 2) | `test_presenter_json_items_carry_rank_score_features_explanation_identifiers_and_sources`. Each item has `rank` (1..n), a float `score`, `features` naming the seven in order, an `explanation`, `identifiers` (DOI and OpenAlex id written by hand) and `providers`. The expansion is recorded with the seven link queries of taxonomy 1.1.0, and OpenAlex was asked exactly those seven. |
| ac3: a fixture provider timing out marks the output PARTIAL, the footer names the provider and reason, and the exit code is 6 | PASS | `test_a_provider_that_times_out_makes_the_results_partial_and_exits_6`: exit 6, title `PARTIAL: 2 results for "midterm elections"`, footer `openalex: timeout: no answer within 0.2s`, and `SEARCH_PARTIAL` on stderr. The JSON form (`test_a_partial_search_in_json_carries_its_results_and_the_failed_provider`) has `error.code SEARCH_PARTIAL`, `exit_code 6`, the two rows, and `openalex` with outcome `timeout` and its reason. |
| ac4: invalid `--argument`/`--need` values or since > until exit 2 with the list of valid choices, and `search --help` documents every flag | PASS | `test_an_unknown_expansion_choice_exits_2_listing_the_valid_ones` covers an unknown argument, need, topic and variable: 4 cases, each exits 2, names a valid choice and asks no provider. `test_a_wrong_command_line_exits_2_and_searches_nothing` covers 10 cases, including `--since` after `--until`, half an argument/need pair and an unknown provider. `test_help_documents_every_flag` checks all 12 flags. |
| ac5: the container registers the OpenAlex, feed and Google News providers and closes them; ranked candidates become stored results through Article matching without a fetch; the JSON carries each result's features and explanation (recorded fixtures) | PASS | `test_the_container_registers_openalex_feeds_and_google_news_and_closes_them`: the container's own registry from `DEBATE_PROVIDERS__ENABLED`, providers `openalex, rss, google_news`, and the shared transport closed 3 times. `test_ranked_candidates_become_stored_results_through_articles_without_a_fetch`: a seeded ACCESSIBLE Article is reused unchanged, the three others are saved `UNKNOWN`, 0 snapshot rows, `search_results` ranks and article ids equal the JSON's, and requests went only to the two provider hosts. Core: `test_federated_search_articles.py` (7) and the two `aclose` tests in `test_registry.py`. |
| ac6: the coach's labels on one real query per format, with nDCG@10 ranked against provider order (operator) | **NOT RUN** | Needs real searches after the merge and the coach's labels. The operator blocks below produce the labelling sheets. Each JSON result now carries `provider_order`, its place in raw provider order, so nDCG@10 can be computed from the saved search. |
| Node: search help renders (`uv run debate-research search --help`) | PASS | exit 0 |
| Node: presenter tests pass (`uv run pytest packages/debate_cli/tests/test_search_command.py -k presenter`) | PASS | `6 passed in 3.98s` |
| Node: search command tests pass offline (`uv run pytest packages/debate_cli/tests/test_search_command.py`) | PASS | `37 passed in 4.40s` |
| Node: import boundaries hold (`uv run lint-imports`) | PASS | `Contracts: 20 kept, 0 broken.` |

### Red first

* **The CLI tests, against a refuse-nothing skeleton.** The command had its full signature, an empty
  body and presenter stubs. Result: **31 failed, 3 passed** (`--tb=line`, 34 tests then). The three
  that passed are `test_help_documents_every_flag` and two usage cases Typer checks from the signature
  alone (`--since "October 1"` and `--max-results 0`). Every other test failed at its assertion: no
  stdout line, exit 0 where 2, 3, 6 or 7 was expected, an empty stderr.
* **The smoke check, before the profile change.** 2 of 4 failed for the reason it exists:
  `error.code` was `CONFIGURATION_ERROR` ("discovery provider 'crossref' is enabled, but this build has
  no adapter for it"), not `NO_PROVIDER_ENABLED`. The unknown-argument run exited 1, not 2. With the
  profiles changed, 4 passed.
* **The lock check.** `uv lock --check --offline` exits 1 on the unedited lock and 0 on the edited one.
* **Pyright.** A probe file assigning a property to an `int` in `debate_cli` reported `1 error`. The
  clean run therefore read this package.

### Mutants

The PM's six. Each was planted in the committed tree and run against `test_search_command.py`
(`-n 0 -p no:randomly`), then restored with `git checkout HEAD --`. No Hypothesis property is
involved.

| Mutant | Caught by |
|---|---|
| A partial result exiting 0 (`PARTIAL` → `OK` in `exit_code_for_search`) | 4 tests: the timeout table and JSON, the not-configured partial, and the partial with no rows |
| A failed provider missing from the footer (footer keeps only `ok` lines) | 3 tests: the timeout, all-failed and not-configured footers, each at its `footer(...) ==` assertion |
| `--expand-llm` on by default (`use_model=True` always) | 2 tests: `test_no_model_is_asked_without_expand_llm` and the stored expansion's `model_requested` |
| An unknown argument exiting 1 (the `UnknownExpansionChoice` mapping removed) | 5 tests: the four expansion choices at `exit_code == 2`, and the unit test of the mapping |
| A discovery-only Article fetched (the command retrieves each result's URL after the search) | at assertions: the seeded Article's access became `ROBOTS_DISALLOWED`, and the shared transport was closed 4 times where the 3 providers close it 3; the fixture's last check named the unrecorded requests in 14 more. The tests route the article fetcher to the recorded transport, so the plant failed at assertions, not by crashing on the network |
| Progress on stdout under `--format json` (a `print` in the progress line) | 14 tests at the one-line envelope check |

### Before the report

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py` (measured before the pyproject edit) | 443 of 658 test files (67.3%). `settings.py` gains `search_deadline_seconds` and the root conftest imports it. That is well over two minutes, so it is left to the PR's `ci` (agreement 10). |
| `uv run scripts/affected_tests.py --run` (after it) | `The whole selection is affected: packages/debate_cli/pyproject.toml is shared test ground. CI runs it on the pull request.` Nothing run, and no operator hand-off. |
| always-run list: `hard_stop.py 115 … pytest tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_container_factories.py -m "not slow and not live"` | `377 passed in 19.09s` |
| the changed areas: `hard_stop.py 115 … pytest` over `test_search_command.py`, `test_installation.py`, `commands/test_doctor.py`, `bucket_mode/test_bucket_mode_lock.py`, `test_cut_command.py`, `test_fetch_command.py`, `test_recorded_failure_codes.py`, `test_retryable_store_failures.py`, `test_unmodelled_error_prints_no_text.py`, `test_config_command.py`, core `test_federated_search_articles.py`, `test_federated_search.py`, `test_federated_ranking.py`, `test_federated_dedupe.py`, `test_query_expansion.py`, `test_settings.py`, `test_settings_environments.py`, `integrations/discovery/`, `tests/smoke/test_search_smoke.py`, `tests/scripts/test_stamp_build.py`, `tests/config` | `1324 passed in 109.29s`. `provider_order` came after this run, and its file was run again: `37 passed`. |
| earlier, the same session: `packages/debate_cli/tests/test_smoke.py test_version.py bucket_mode/` | `282 passed in 114.09s` (at the edge of the limit, under a load near 12 from a parallel session) |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1824 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_cli packages/debate_core` | `0 errors, 0 warnings, 0 informations` (48 s) |
| `uv run --frozen lint-imports` / `scripts/check_thin_handlers.py` | `20 kept, 0 broken` / `72 … handlers within 25 statements` |
| `uv run scripts/validate_specs.py` | `OK: 578 files, 41 epics, 515 tasks, 22 releases` |
| `scripts/check_command_blocks.py`, `check_links.py`, `docs_index.py --check-descriptions` | all OK |

## Files changed

* **`packages/debate_cli/src/debate_cli/`**
  * `commands/search.py` (new): the command.
  * `presenters/search_presenter.py` (new): table, footer, JSON, failures, progress.
  * `container.py`: `discovery_providers`, `federated_search`, the search model router and `FederatedSearching`.
  * `exit_codes.py`: `SEARCH_PARTIAL` 6, `NO_RESULTS` 7, `exit_code_for_search`, and `UnknownExpansionChoice` → 2.
  * `command_registry.py`: registers `search`.
* **`packages/debate_core/src/debate_core/application/`**
  * `federated_search_articles.py` (new): `ArticleMatchingStage`.
  * `federated_search_types.py`: `StagesInOrder`; `articles` on the state; `ranked_candidates` and `articles` on the outcome.
  * `federated_search.py`: returns both.
  * `settings.py`: `providers.search_deadline_seconds`.
* **`packages/debate_core/src/debate_core/integrations/discovery/`**: `aclose` on `ResilientProvider` and `ProviderRegistry`.
* **Tests**
  * `packages/debate_cli/tests/test_search_command.py` and `fixtures/search/` (new, synthetic, with a README).
  * `packages/debate_core/tests/application/test_federated_search_articles.py` (new); the `aclose` and setting tests in `test_registry.py`.
  * Pins moved by the new integrations, services and command: `test_installation.py` (wired list 35 → 41, httpx gaps, declared extras), `commands/test_doctor.py`, `test_app.py`, `test_container_factories.py` (`model_expansion: bool`), `bucket_mode/test_bucket_mode_lock.py` (`search` never writes a bucket), and `tests/scripts/test_stamp_build.py` (the dependency string).
* **`tests/smoke/test_search_smoke.py`** (new): the installed-build smoke check (agreement 5).
* **`packages/debate_cli/pyproject.toml` and `uv.lock`**: `debate-core[…,feeds,…]`. The lock entry was edited by hand because offline resolution cannot see fastapi in the cache; `uv lock --check --offline` accepts it.
* **`config/profiles/dev.toml`, `prod.toml`**: `providers.enabled = ["openalex", "rss"]` (Deviations 3).
* **`packages/debate_cli/README.md`**: the extras, the exit-code table and a `search` section.
* **`plan_specs/…/t05-search-command.yaml`**: the PM's dated amendment and the scope additions.

## Deviations from the spec

1. **Exit codes, by the PM's ruling of 2026-11-02, written into the spec as a dated amendment.** The
   original text's "7 … or all providers failed" is now 3. 6 and 7 are new `ExitCode` members.
   `UnknownExpansionChoice` maps to 2 in `exit_code_for`. **The session added one rule:** a search
   that asked no provider, because none of those selected is enabled, is a 1 (`NO_PROVIDER_ENABLED`),
   not a 3. No retry enables a provider, and 3 means "try again later". A partial
   search with no rows is a 6, not a 7: 7 promises that every provider answered.
2. **ac2's "JSON array" is `data.results`** (or `error.details.results` on 6, 7 and 3) inside the
   CLI's envelope. `output.py` promises a scheduled consumer one five-key envelope for every command,
   so search does not print a bare array.
3. **`config/profiles/dev.toml` and `prod.toml`, outside the packages first listed.** Both enabled
   `crossref`, and prod also `semantic_scholar`. This build has no adapters for them, and
   `ProviderRegistry.from_settings` refuses a name it cannot build (v1-e07-t01's contract). Every dev
   or prod search would have stopped with `CONFIGURATION_ERROR` before asking anyone. Both now enable
   `["openalex", "rss"]`, with a comment saying t03 and t04 add their names back. Nothing pins these
   values (`test_settings_environments.py`, `tests/config` and `test_config_command.py` pass). The
   alternative was to leave the profiles alone and have the operator set `DEBATE_PROVIDERS__ENABLED`
   on every search. Question 1.
4. **New files outside the first list:** `tests/smoke/test_search_smoke.py` (agreement 5 asks for it)
   and the one-line pin in `tests/scripts/test_stamp_build.py`, which reads the CLI's dependency string.
   Both are added to `constraints.packages` with a comment, for the PM to keep or undo.
5. **`--save PATH` writes the JSON search object to a file.** The spec lists `--save` without saying
   what it does, and every search is stored anyway (v1-e08-t01). Question 2.
6. **A guard the spec does not mention:** the container refuses to build an enabled provider when
   `allow_network` is false and no test transport was given. The `test` profile promises "no search
   provider may leave the process", and until now nothing in the discovery path read that setting.

## Decisions and assumptions

* **A canonical URL is the platform's, not an owner's.** `ArticleMatchingStage` looks up by URL
   alone and saves a discovery-only Article with the request's owner, which is None in V1's CLI. This
   is the rule `ArticleService.retrieve` and `ArticleRegistrationService` already follow. It means
   the Article a search registers is the one a later `fetch` of that URL finds and fills in, rather
   than a second record of the same public source. An Article is a shared description of a public
   source (the port's `save` is last-writer-wins for that reason). The searches and cards are what
   carry an owner. If V2's accounts partition Articles, the change is in that one lookup. The rule is
   written in the module docstring.
* **A stored Article is reused as it stands.** Its access status and metadata may come from a
   retrieval, which knows more than a search result. The table's Access column shows a measured
   status when there is one, otherwise `UNKNOWN` (with "open access" when a provider says so).
* **Stored searches across builds: no installed build reads them.** Outside tests, the only code
   that builds `SqliteSearchRepository` is this branch's container. It only writes: `save` reads the
   stored `revision`, never the document, then `save_provider_statuses` and `save_results`. `get` and
   `list_results`, the only calls that decode a stored `Search`, are called by nothing. No earlier
   build has a command that touches the `searches` table, and this task adds no migration. So no
   earlier build's wheel needs to prove it tolerates `expansion`; the first command that reads a
   stored search back must.
* **Dates.** `--since` is the start of its day and `--until` the end of its day, in UTC.
   `--since` after `--until` is refused before anything is built.
* **The footer** sits on stdout below the table. When there are no rows (exit 7, 3 or 1), it goes to
   stderr above the failure panel, so stdout stays empty on a failure as it does for every command.
* **`--expand-llm`** builds the guard only when given, over its own router (`search_model_router`),
   chosen as `cut`'s is: replay unless `DEBATE_MODEL_MODE` is live or record. Cassettes go in
   `<data dir>/search/model-cassettes/`. The call is routed by `high_volume`, which a test asserts.
* **`provider_order`** on each JSON result is its first place among the raw candidates in fan-out
   order: t03's "raw provider order" baseline, needed for ac6.
* **Snippets and abstracts are never printed or put in the JSON.** Two sentinel words in the fixtures
   prove it in both modes.
* **An unknown `--argument` is refused when the expansion stage runs**, after the container is built
   but before any provider is asked. On a profile that cannot build its providers, the configuration
   error therefore shows first; the smoke check's red run showed exactly that.

## Operator follow-ups

**After this merges and a dev pre-release containing it is installed: one real search per format.**
These are live calls to OpenAlex (no key needed) and to the publisher feeds in `config/feeds/`. They
write only to dev's local data directory and two files on your Desktop, and print only exit codes and
counts. No model is called. Runtime: under a minute each.

**Operator command 1: check the installed build** (seconds)
Where: your Mac, any terminal
```bash
debate-research --json --version | python3 -I -c 'import json, sys; print(json.load(sys.stdin)["data"]["tag"])'
debate-research search --help | grep -c -- '6  partial'
```
Success looks like: the tag of a dev pre-release built after this merge, then `1`. A `0` means the
installed build has no `search`: install the newer pre-release first.

**Operator command 2: the Policy NHI search, politics DA link** (under a minute)
Where: the same terminal
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && env DEBATE_ENV=dev debate-research --json search "national health insurance" --argument politics-da --need link --topic policy-2026-27-nhi --max-results 200 --save "$HOME/Desktop/search-policy-nhi.json" > /tmp/search-policy-nhi.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); r = e.get("error") or {}; d = e.get("data") or r.get("details") or {}; x = d.get("expansion") or {}; print("code", r.get("code"), "exit_code", r.get("exit_code")); print("status", d.get("status"), "results", len(d.get("results") or [])); print("queries", len(x.get("queries") or []), "warning", x.get("warning")); print("providers", [(p["provider"], p["outcome"], p["results"]) for p in d.get("providers") or []])' /tmp/search-policy-nhi.json; fi
```
Success looks like `exit 0`, `code None exit_code None`, `status COMPLETE`, `results` above zero,
`queries 7`, `warning None`, and `providers` listing `openalex` and `rss` as `ok`, each with a count.
`exit 6` with a provider marked `timeout` or `error` is worth pasting back as it is. Paste back these
four lines only. The titles stay in the saved file.

**Operator command 3: the LD de-extinction search** (under a minute)
Where: the same terminal
```bash
if env | grep -q '^DEBATE_'; then echo "STOP: DEBATE_ overrides are set in this shell"; else cd "$HOME" && env DEBATE_ENV=dev debate-research --json search "de-extinction" --max-results 200 --save "$HOME/Desktop/search-ld-de-extinction.json" > /tmp/search-ld-de-extinction.json; echo "exit $?"; python3 -I -c 'import json, sys; e = json.load(open(sys.argv[1])); r = e.get("error") or {}; d = e.get("data") or r.get("details") or {}; print("code", r.get("code"), "exit_code", r.get("exit_code")); print("status", d.get("status"), "results", len(d.get("results") or [])); print("providers", [(p["provider"], p["outcome"], p["results"]) for p in d.get("providers") or []])' /tmp/search-ld-de-extinction.json; fi
```
Success looks like `exit 0`, `status COMPLETE` and `results` above zero. `exit 7` (`NO_RESULTS`) is
also an answer: OpenAlex found nothing and no configured feed carries the topic. Paste back the
three lines.

**Operator command 4: the coach's labelling sheets for ac6** (seconds, then the coach's time)
Where: the same terminal, after commands 2 and 3 saved their files. This writes one CSV per search to
your Desktop. Each holds the top 10 by the ranking and the top 10 by raw provider order (up to 20
rows), with columns `rank`, `title`, `url` and an empty `relevant`.
```bash
for name in policy-nhi ld-de-extinction; do python3 -I -c 'import csv, json, sys; d = json.load(open(sys.argv[1])); r = d["results"]; top = {x["rank"] for x in sorted(r, key=lambda x: x["rank"])[:10]} | {x["rank"] for x in sorted(r, key=lambda x: x["provider_order"])[:10]}; w = csv.writer(open(sys.argv[2], "w", newline="")); w.writerow(["rank", "title", "url", "relevant"]); [w.writerow([x["rank"], x["title"], x["url"], ""]) for x in sorted(r, key=lambda x: x["rank"]) if x["rank"] in top]; print(sys.argv[2], len(top), "rows")' "$HOME/Desktop/search-$name.json" "$HOME/Desktop/labels-$name.csv"; done
```
Success looks like two lines, each naming a `labels-….csv` with between 10 and 20 rows. The coach marks
`relevant` with `y` or `n` on each row: "would you want this in the first page for a debater
researching this query?" The filled CSVs and the two saved `search-….json` files then go to the session
that records ac6. It computes nDCG@10 for the ranking against raw provider order. A lower ranked figure
opens a weight-tuning ticket and does not fail this task (v1-e08-t03's PM review).

## Follow-up work

* **v1-e07-t03 (Crossref) and v1-e07-t04 (Semantic Scholar):** each adds its name back to
  `providers.enabled` in `config/profiles/dev.toml` (and `prod.toml`) in the same change as its
  adapter, as the comment there says.
* **Each expanded query asks each provider once.** The politics DA's link need has 7 templates, so one
  search is 7 OpenAlex requests and 7 reads of every feed (the feed cache makes the repeats
  conditional requests). Without a key, OpenAlex allows about 100 searches a day, which is about 14
  expanded searches. Worth a ticket: E07 (one OpenAlex request with `OR`ed queries) or E08 (read each
  feed once per search and match every query against it).
* **The LD de-extinction topic preset** is still v1-e32-t06's (from v1-e08-t04's follow-ups). Command 3
  searches the bare query until it exists.
* **Google News is off on both committed topics** (`config/feeds/*.yaml`, `google_news.enabled: false`).
  Turning it on is the coach's decision. Until then, enabling `google_news` makes no request.

### Questions for the PM

````text
PM questions from v1-e08-t05 (debate-research search), session of 2026-11-02. Four, all small.

1. Dev/prod profiles. Both enabled crossref (prod also semantic_scholar), which have no adapter yet;
   ProviderRegistry refuses every search while they are enabled, so search could not run on dev or
   prod. I changed both to ["openalex", "rss"] (outside the task's packages; the smoke check ran red
   on it first).
   Options: (a) keep the change, and t03/t04 add their names back with their adapters;
   (b) revert it, and have the registry skip an enabled name with no adapter and report it as
   "not configured" in the footer (every dev search would then exit 6);
   (c) revert it, and have the operator set DEBATE_PROVIDERS__ENABLED for every search.
   Recommendation: (a). It keeps v1-e07-t01's rule that an enabled name must build, and a search
   that is always "partial" would teach people to ignore 6.

2. --save. The spec lists it without a meaning, and every search is stored anyway. I made
   --save PATH write the JSON search object (the same as --format json's data) to a file.
   Options: (a) keep; (b) drop the flag; (c) make it mean something else.
   Recommendation: (a). It gives t06/t07 and the ac6 labelling a file to work from.

3. Exit 1 for a search that asked no provider, because none of those selected is enabled
   (NO_PROVIDER_ENABLED). Your ruling covered 0/6/7/3/2. I made this case 1, not 3, because no
   retry enables a provider.
   Options: (a) keep 1; (b) make it 3 like every other all-failed search.
   Recommendation: (a).

4. ac6 labelling sheet. You asked for a CSV of rank, title and URL. Showing the rank may lean the
   coach toward the ranking; v1-e08-t03's sheet listed items alphabetically for that reason.
   The CSV holds the top 10 by rank and the top 10 by raw provider order (up to 20 rows).
   Options: (a) keep the rank column as asked; (b) replace it with an item number, rows in title order.
   Recommendation: (b), if the coach's labels are to be the measurement.
````

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-11-02

**Notes:**

`search` is built as a thin command over the federated service, with the expansion wired in. It
never fetches and never prints a snippet. The Goal stays `InProgress` for ac6, the coach's labels.
The profile find, that dev and prod could not have run a single search, is the most useful thing in
this report.

1. **ac1–ac5:**
   * The rows and the footer are written by hand from the fixtures.
   * ac2's seven expanded link queries come from taxonomy 1.1.0.
   * The timeout gives PARTIAL and exit 6 in the table and in JSON.
   * 14 usage cases exit 2.
   * The container registers and closes all three providers.
   * Article matching makes no snapshot row and no request beyond the two provider hosts.
2. **Red first and mutants:** 31 of 34 tests failed against the skeleton, and the smoke check was red
   on the old profiles. All six of the PM's mutants were caught at assertions. The fetch mutant was
   caught without touching the network.
3. **Exit codes:** the PM's ruling is in the spec as a dated amendment. The session's rule for a
   search that asked no provider (`NO_PROVIDER_ENABLED`, exit 1) and its partial-with-no-rows → 6 are
   both accepted.
4. **The rulings on your questions:**
   * **Q1, (a).** Keep `["openalex", "rss"]` in dev and prod. v1-e07-t03 and t04 add their names
     back with their adapters. A search that always exits 6 would teach people to ignore 6.
   * **Q2, (a).** `--save PATH` writes the JSON search object.
   * **Q3, (a).** Keep exit 1.
   * **Q4, (b).** The labelling sheet uses an item number with rows in title order, so the rank
     doesn't lean the coach. Before the PR, change operator command 4 to write two files per search:
     the coach's CSV (`item`, `title`, `url`, `relevant`) and a key file (`item`, `rank`,
     `provider_order`) that the scoring session uses and the coach never needs to open.
5. **Deviations accepted:**
   * the envelope's `data.results` as ac2's array;
   * the two profiles;
   * the smoke check and the stamp-build pin, added to the packages;
   * `--save`;
   * the `allow_network` guard the test profile always promised.
6. **Decisions accepted:**
   * a canonical URL is the platform's, not an owner's, as `ArticleService` already treats it;
   * stored Articles reused as they stand;
   * no installed build reads stored searches, so the first command that reads one back owns the
     cross-build proof;
   * the UTC day bounds for dates;
   * the footer's placement;
   * `--expand-llm`'s own router, in replay by default;
   * `provider_order` for ac6.
7. **Follow-ups the PM files:**
   * one p3 task for the request count: each expanded query asks every provider once, so OpenAlex can
     take one request with OR'd queries, and each feed can be read once per search;
   * the LD preset stays with v1-e32-t06;
   * Google News stays off until the coach turns it on.
8. **Closing checks:** the affected set is the whole selection (the pyproject edit), so it is left to
   `ci` (agreement 10). The bounded runs (377, 1,324 and 282 passed), ruff, pyright, lint-imports, thin
   handlers, the specs and the doc checks are clean. The hand-edited lock passes `uv lock --check
   --offline`.
9. **Merge:** after the command-4 edit, `scripts/task pr --partial` once `ci` is green. The PM
   records ac6 in a batch and sets the Goal `Succeeded` when the coach's labels are scored.

## Operator records (recorded by the PM, 2026-11-03)

Added by the PM. Nothing above is changed, and this section is not a review.

| Criterion | Was | Now | Record |
|---|---|---|---|
| ac6: the coach's labels on one real query per format, nDCG@10 ranked against provider order | NOT RUN (operator) | PASS | 2026-11-02, `v1.1.0-dev.342`, live searches saved by the operator and labelled blind by the coach (each sheet the top 10 by the ranking and the top 10 by provider order, merged and sorted by title, with no rank shown; the key kept apart until he had answered). Policy, the politics DA's link on national health insurance: 3 relevant of 20 rows, nDCG@10 **0.746** ranked against **0.000** in provider order, 3 relevant in the ranking's top 10 against 0 (the ranking placed them 1st, 9th and 10th; provider order had them 117th, 441st and 257th). LD, de-extinction: 10 relevant of 16 rows, **0.552** against **0.452**, 6 in the top 10 against 5 (three the coach marked relevant at provider positions 2, 3 and 10 were ranked 50th, 48th and 72nd). Both searches `exit 6`, rss `partial` because one feed was unreadable (below) |

Every criterion passes, so the Goal is `Succeeded` in this batch. The ranking beats provider order on both formats, so no weight-tuning ticket is opened; the LD rows ranked down are noted for the next tuning. The coach's two observations are filed in this batch: DA link queries that name the plan's mechanism in the United States (`v1-e08-t14`, p2), and LD research that starts broad and narrows from the first page (`v1-e08-t15`, p3, proposal first). The feed findings go to `v1-e07-t14` and `v1-e08-t10`.
