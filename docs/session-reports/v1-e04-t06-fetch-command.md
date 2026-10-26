# Session report: v1-e04-t06-fetch-command

| | |
|---|---|
| Task | `v1-e04-t06-fetch-command` — `debate-research fetch` command and recorded fixtures |
| Spec | [`plan_specs/v1/e04-article-retrieval/t06-fetch-command.yaml`](../../plan_specs/v1/e04-article-retrieval/t06-fetch-command.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t06-fetch-command` |
| Session status | COMPLETE |

## Summary

`debate-research fetch <URL> [--refresh] [--json]` exposes ArticleService (t05). A readable page
prints its canonical URL, title, identifiers, access status with reason, provenance, and the
snapshot's id, both SHA-256 hashes, paragraph count, extractor and normalizer versions, and exits 0.
Every other status prints a failure panel (status, reason, status code, marker, rules version),
stores no snapshot, and exits 3. `--paste` stores text the user lawfully has as USER_SUPPLIED, but
only after attestation: a prompt in a terminal, or `--i-have-lawful-access` where no prompt can be
shown. The fixture corpus is eight cassettes built from t03's and t04's synthetic samples, per the
PM's amendment; nothing was recorded from a real site. A replay transport serves them to the real
fetcher, extractors and classifier. All four Goal criteria and every node criterion pass, so the
phase is `Succeeded`.

**For the PM to look at first:**

* The `--json` schema is in `packages/debate_core/schemas/`, beside `verify_result.v1.json`, not
  under `docs/data` (Deviation 2).
* The end-to-end tests run the real app in pytest's process, not the installed console script
  (Deviation 4).
* `uv.lock` was edited by hand (Deviation 5).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `fetch-command`: fetch command and wiring | Done | `ArticleFetch` in `debate_core.application.article_fetch`; the command in `debate_cli.commands.fetch` (14 statements); the composition root as t05's report and the PM's note describe it, with the new `articles.html_max_bytes`. Built first: the order of the two nodes with no `dependsOn` is open. |
| `record-fixtures`: record and scrub HTTP cassettes | Done | Built, not recorded (PM amendment): `tests/fixtures/http/build_cassettes.py` writes eight cassettes from t03/t04 samples, with scrub rules and a hygiene test. |
| `paste-mode`: `--paste` USER_SUPPLIED mode | Done | File or stdin; `--source-url` required; prompt only in a terminal; the flag otherwise. |
| `e2e-offline`: offline end-to-end integration tests | Done | `tests/integration/test_fetch_cli.py`, 22 tests; the installed binary is checked offline by `tests/smoke/test_fetch_smoke.py`. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: `fetch <fixture-url>` against replayed cassettes prints metadata, ACCESSIBLE, the snapshot id and sha256, and exits 0 | PASS | `test_a_readable_fixture_prints_its_metadata_accessible_and_the_snapshot_and_exits_zero`, for the news, think-tank, government and PDF cassettes. Each checks exit 0, the canonical URL, the title, the snapshot id read back from the data dir's SQLite file, and the SHA-256 of the sample's own bytes. The JSON twin checks identifiers (the PDF's DOI `10.5555/jscs.2026.0012`), paragraph counts (5, 10, 4, 16, the lengths of t04's hand-written paragraph lists) and extractor names. |
| ac2: paywalled, robots-disallowed and 404 fixtures print the specific AccessStatus and reason, exit 3, and create no snapshot | PASS | `test_a_refused_fixture_prints_its_status_and_reason_exits_three_and_stores_no_snapshot`, for PAYWALLED, ROBOTS_DISALLOWED, NOT_FOUND and (beyond the criterion) BLOCKED. Each checks exit 3, `STATUS: reason` from t03's tables, `rules_version: paywall_rules.v1`, the marker (`extractor-is-accessible-for-free`, `cloudflare-interstitial-title`), no snapshot row and no blob file. The robots page is never requested (`replay.requested` is only the robots.txt). |
| ac3: at least seven cassettes (news, think-tank, .gov, open-access PDF, paywalled, robots-disallowed, 404) under `tests/fixtures/http/` with a README recording source, date and scrub rules | PASS, as amended | Eight cassettes. Per the 2026-10-25 amendment, the README records how each was made instead of a source and date, plus the scrub rules. `test_at_least_seven_cassettes_cover_every_kind_the_spec_names` passes. ac3's own text still says "source, date" (Deviation 6). |
| ac4: `--json` validates against a published schema, and `--paste` creates a USER_SUPPLIED snapshot only after attestation | PASS | Every `--json` run in `test_fetch_command.py` and `test_fetch_cli.py` is validated against the committed `fetch_result.v1.json`. `test_the_schema_takes_each_outcome_…_and_refuses_a_mismatch` shows it refuses a NOT_FOUND report as success and a wrong exit code. Paste: stored with the flag or a "y" answer. Refused, nothing stored, exit 1: no flag where no prompt can be shown, "n", an empty answer (default no), `--json`, and text on stdin. Shown on the real store (`test_a_paywalled_page_can_then_be_stored_from_the_coachs_own_copy_as_user_supplied`) and on the installed build (`test_fetch_smoke.py`). |
| Node `record-fixtures`: README contains `Set-Cookie` | PASS | `grep -c "Set-Cookie" tests/fixtures/http/README.md` → `1` |
| Node `record-fixtures`: `uv run pytest tests/fixtures/test_cassette_hygiene.py` | PASS | `36 passed in 1.77s` |
| Node `fetch-command`: `uv run pytest packages/debate_cli/tests/test_fetch_command.py` | PASS | `38 passed in 2.98s` (39 after the `--json` test was added: `68 passed` with the e2e, help and smoke files) |
| Node `paste-mode`: `… test_fetch_command.py -k paste` | PASS | `15 passed in 3.73s` |
| Node `e2e-offline`: `uv run pytest tests/integration/test_fetch_cli.py` | PASS | `21 passed in 4.80s`; 22 after the log test |
| Node `e2e-offline`: `uv run pyright packages/debate_cli` | PASS | `0 errors, 0 warnings, 0 informations` |

### Mutation runs (agreement 8)

20 mutants of `commands/fetch.py`, `article_fetch.py` and the container's new factory. Each ran
against `test_fetch_command.py`, `test_fetch_cli.py` and `test_article_fetch.py`, with a fresh
`HYPOTHESIS_STORAGE_DIRECTORY`. These tests use no Hypothesis properties, so that only follows the
agreement. Every run ran its tests to a result (no collection errors), and each source file was
restored and byte-checked after its mutant. 19 were caught:

| Mutant | Caught by |
|---|---|
| exit 1 instead of 3 for a status that is not ACCESSIBLE | 24 tests: every failing-status case, both modes, and the e2e refusals |
| only PAYWALLED, ROBOTS_DISALLOWED and NOT_FOUND exit 3 | 11 tests: the 403, timeout, image and too-short cases, and the BLOCKED cassette |
| the status rule also applied to pasted text (UNKNOWN would exit 3) | 4 paste tests |
| **exit 3 decided by a missing snapshot instead of the status** | **survived, equivalent.** A retrieval holds a snapshot exactly when it is ACCESSIBLE (RetrievalOutcome's invariant, t05), and pasted text always holds one. |
| `--refresh` not passed by the command | `test_a_second_run_answers_from_the_stored_snapshot_and_refresh_asks_the_publisher_again` |
| `--refresh` not passed by ArticleFetch | that test, the core refresh test and the schema test |
| pasted text always attested | 7 tests |
| "no prompt can be shown" counted as attested | 4 tests |
| prompt shown in `--json` mode | `test_paste_in_json_mode_never_prompts_even_at_a_terminal` |
| prompt shown when the text is stdin | `test_paste_from_stdin_never_prompts_even_at_a_terminal` |
| prompt defaults to yes | the empty-answer case |
| `--paste` without `--source-url`, `--paste --refresh`, a URL beside `--paste` accepted | one usage-error case each |
| paragraph count off by one | 8 tests |
| connection never closed | 3 tests |
| pasted text bounded by `pdf_max_bytes` instead of `http.max_response_bytes` | `test_pasted_text_is_bounded_by_http_max_response_bytes` |
| HTML extractor left at its own default size limit | `test_the_html_extractors_size_limit_comes_from_articles_html_max_bytes` |
| the no-prompt hint never names `--i-have-lawful-access` | `test_paste_where_no_prompt_can_be_shown_and_no_flag_stores_nothing_and_exits_one` |
| pasted text reported as PUBLISHER_RETRIEVED | 4 tests |

Planted faults in the cassettes, each restored and byte-checked afterwards:
`test_cassette_hygiene.py` → `2 failed, 34 passed` each time. In every case one failure was the
builder-drift check and the other was the fault's own check:

* a `set-cookie` response header → the header check;
* a recorded request `cookie` header → the request-shape check;
* a paywalled cassette serving t03's full open article → the teaser check.

A planted `debug` log of the snapshot's text failed
`test_no_log_record_holds_a_sentence_of_the_page_whatever_the_level` (`1 failed`).

### Checks before the report (agreement 10)

* `uv run scripts/affected_tests.py` → "The whole selection is affected:
  packages/debate_cli/pyproject.toml is shared test ground." That run is the pull request's `ci`.
  The groups below ran within the two-minute line. Each ran under
  `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live" -p no:randomly`.
  Another session's suite held the load average between 8 and 27 throughout.
  * `tests/architecture tests/specs packages/debate_cli/tests/test_*.py packages/debate_cli/tests/commands`
    → `1 failed, 1310 passed in 70.45s`. The failure was real: import-linter counted the container's
    `TYPE_CHECKING` import of httpx. Fixed in `c03f972`. Then `tests/architecture`, the e2e file,
    `test_installation.py` and `test_doctor.py` → `297 passed in 27.69s`.
  * `packages/debate_cli/tests/bucket_mode` → `99 passed in 111.59s`.
  * `packages/debate_core/tests/application`, its 163 files in two halves → `1508 passed in 101.51s`
    and `2455 passed in 39.18s`.
  * `tests/integration tests/fixtures/test_cassette_hygiene.py tests/smoke/test_fetch_smoke.py tests/smoke/test_cli_smoke.py packages/debate_core/tests/domain/test_schemas.py packages/debate_core/tests/retrieval tests/scripts/test_check_command_blocks.py tests/docs packages/debate_core/tests/integrations/test_html_extractor.py packages/debate_core/tests/integrations/test_pdf_extractor.py`
    → `1269 passed in 75.77s`.
  * After the last commit (`--json` after the command): `test_fetch_command.py test_fetch_cli.py test_help_rendering.py tests/smoke/test_fetch_smoke.py` → `68 passed in 28.39s`.
* **Process-wide state.** The real fetcher installs its URL filter on the httpx loggers, so the e2e
  file and `test_http_fetcher.py` ran in one process (`-n 0 -p no:randomly`) in both orders:
  `164 passed` (with `test_fetch_command.py`) and `126 passed`.
* `uv run ruff format --check .` → `1444 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_core packages/debate_cli`, and CI's whole-repo `uv run --frozen pyright` → `0 errors, 0 warnings, 0 informations`
* `uv run lint-imports` → `Contracts: 18 kept, 0 broken.`
* `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 66 CLI command and API route handlers within 25 statements`
* `uv run scripts/export_schemas.py --check` → `OK: 10 schemas in packages/debate_core/schemas are up to date`
* `uv run python scripts/check_command_blocks.py` → OK; `scripts/docs_index.py --check-descriptions` → OK
* `uv lock --check --offline` → `Resolved 151 packages`, exit 0
* `uv run scripts/validate_specs.py` → `OK: 469 files, 40 epics, 407 tasks, 22 releases`;
  `--require-succeeded v1-e04-t06-fetch-command` → `Succeeded`

## Files changed

* **`debate_core.application`:**
  * `article_fetch.py` (new): `ArticleFetch`, `FetchReport`, `SnapshotSummary`,
    `render_fetch_result_schema`.
  * `settings.py`: `articles.html_max_bytes`, default 10 MiB.
* **`debate_cli`:**
  * `commands/fetch.py` (new) and its registration in `commands/__init__.py`.
  * `container.py`: `article_fetch()`, in `SERVICE_NAMES`.
  * `pyproject.toml`: the `extraction` extra.
  * `README.md`: a `fetch` section.
* **Schema:** `packages/debate_core/schemas/fetch_result.v1.json` (generated) and
  `scripts/export_schemas.py`.
* **Fixtures:** `tests/fixtures/http/` (README, `build_cassettes.py`, `cassettes.py`, eight
  cassettes, `expected_fetches.json`) and `tests/fixtures/test_cassette_hygiene.py`.
* **New tests:** `packages/debate_cli/tests/test_fetch_command.py` (39),
  `packages/debate_core/tests/application/test_article_fetch.py` (10),
  `tests/integration/test_fetch_cli.py` (22), `tests/smoke/test_fetch_smoke.py` (4), and a row in
  `tests/smoke/README.md`.
* **Pinned lists:**
  * `test_doctor.py`: wired integrations, and the count 29 → 32;
  * `test_installation.py`: wired list and count; the extras tests gain `extraction`, plus a new
    test for dropping it;
  * `test_app.py`: doctor's service names;
  * `test_bucket_mode_lock.py`: `fetch` never writes a bucket;
  * `test_article_service.py`: the new default pinned to the extractor's.
* `uv.lock`: debate-cli's entry.

## Deviations from the spec

1. **Files outside `constraints.packages`** (`debate_cli.commands.fetch`, `tests/fixtures/http`,
   `tests/integration`).
   * The PM's note expected the composition root, the pyproject and lock, the two pinned lists, the
     smoke check and the schema.
   * Also changed:
     * `debate_core.application.article_fetch` (new) and `settings.py`;
     * `commands/__init__.py` (registration);
     * two more pinned lists, `test_app.py` (services) and `test_bucket_mode_lock.py` (command
       classification);
     * `test_article_service.py` (one line);
     * `scripts/export_schemas.py`;
     * the CLI README and the smoke README;
     * the two test files the spec itself names outside those packages:
       `packages/debate_cli/tests/test_fetch_command.py` and
       `tests/fixtures/test_cassette_hygiene.py`.
   * `ArticleFetch` is in `debate_core` because the report (the paragraph count from the checked
     snapshot, the published schema) is logic, which the rules keep out of the CLI.

   **Proposed amendment:** add `debate_core.application`, `debate_cli` (the container, the
   registration, `pyproject.toml` and the CLI's tests), `uv.lock`, `scripts/export_schemas.py`,
   `packages/debate_core/schemas` and `tests/smoke`.
2. **The `--json` schema is `packages/debate_core/schemas/fetch_result.v1.json`, not under
   `docs/data`.**
   * `verify_result.v1.json`, the only other published CLI result schema, is there.
   * It is generated by `scripts/export_schemas.py`, whose `--check` already guards drift. A drift
     test is in `test_article_fetch.py`.
   * `docs/data` holds the schemas of stored data files (sidecars, reports, manifests).
   * Moving it is a one-line change to the filename constant if the PM prefers `docs/data`.
3. **The builder is `tests/fixtures/http/build_cassettes.py`, not
   `scripts/record_http_fixtures.py`.** Under the amendment it records nothing, so "record" would
   misname it (agreement 4). It sits in the fixture package, as t04's `build_pdf_fixtures.py` does,
   inside `constraints.packages`.
4. **The end-to-end tests run the real app in pytest's process, not the installed console script**
   (the e2e node's description).
   * A separate process could be handed the replay only by patching the build.
   * The fetcher refuses a loopback stand-in by design.
   * The smoke tier's network guard refuses every host.
   * The test uses the real app, container and adapters, and replaces only the transport, through
     the container's `"article_fetch_transport"` seam.
   * The installed binary is checked by `tests/smoke/test_fetch_smoke.py` on the paths that need no
     request: help, paste with and without attestation, and the refusals. The network guard's empty
     log there shows that `--paste` fetches nothing.
5. **`uv.lock` was edited by hand.**
   * `uv lock --offline` could not resolve `fastapi` from this machine's uv cache.
   * The only change is debate-cli's own entry gaining `extraction` in its two lines. Every
     extraction distribution was already locked through debate-core's extra.
   * `uv lock --check --offline` passes on the edited lock and fails on the old one, and
     `uv sync --locked --offline --all-packages` accepted it.
   * CI's `uv sync --locked` checks it again.
6. **ac3's text still says "a README recording source, date and scrub rules".** The amendment
   replaced source and date with how each fixture was made, and the README does that. The PM may
   want to amend ac3's wording to match.
7. **The paywalled body is not "truncated to the teaser"** (record-fixtures node). t03's sample is
   already a one-paragraph teaser, so there is no body to truncate. The hygiene test enforces it
   instead: a paywalled cassette serves fewer than 200 visible words.

## Decisions and assumptions

1. **One error code for every status that is not ACCESSIBLE: `SOURCE_NOT_ACCESSIBLE`.** The status
   is in `error.details.access_status` and in the panel's message (`PAYWALLED: <reason>`). The
   statuses' own names cannot be codes: `NOT_FOUND` is already `NotFound`'s code (a record this
   machine lacks).
2. **Exit 3 is a retrieval's rule only.** Pasted text that is stored exits 0, whatever status it
   carries: UNKNOWN, since the command exposes no option to report one (Follow-up 1).
3. **Where the attestation prompt is shown.**
   * Only when a person can answer it: not `--json`, the text not read from stdin, and stdin a
     terminal (`stdin_is_a_terminal`, replaced in tests as `caselist auth` does).
   * It defaults to no.
   * Anywhere else, the flag is required. Without it, the service's own `UserTextNotAttested`
     refuses (exit 1), with a hint naming the flag.
4. **`--paste` and a URL are exclusive** (exit 2). `--source-url` and `--i-have-lawful-access`
   without `--paste` are usage errors, and so is `--paste --refresh`.
5. **The paragraph count is read from the stored snapshot through `SnapshotService.load`**, which
   re-hashes both blobs. A report therefore names only a snapshot that is on this machine and
   intact; a tampered one is the integrity error.
6. **The report carries the classifier's `evidence`.** It holds status codes, counts and marker ids
   only (t03), and that is what t07's measurement will want. It never carries page or pasted text;
   two tests check every output, and one checks every log record at DEBUG over the real pipeline.
7. **The title is the article's stored title.** The PDF fixture's title is its URL, because pypdf
   finds no title hint in it; citation metadata is E06's.
8. **Fixture hosts are invented `example` hosts.** The government host is t04's own
   `www.fosw.example.gov`, so its same-site `rel=canonical` is honoured. The news URL is fetched
   with `?utm_source=newsletter`, to show the canonical form dropping it.
9. **Tests set `DEBATE_HTTP__PER_HOST_INTERVAL_SECONDS=0`.** robots.txt and the page are two
   requests to one host, and the polite interval would otherwise sleep a real second between them.
10. **The e2e test imports `html_extractor` at module top.** urllib3, through trafilatura, opens a
    socket at first import to probe for IPv6, and pytest-socket warned about it when the container
    did the import inside a test.
11. **The container's transport seam is typed `Any`.** import-linter forbids the CLI from importing
    httpx even under `TYPE_CHECKING`.
12. **`--json` is accepted after the command as well as before it**, as `caselist cards` does, so
    the spec's `fetch <URL> [--json]` works as written.
13. **`fetch` writes this machine's data directory only**, so it is classified as never writing a
    bucket.
14. **A bot-challenge cassette (BLOCKED, 403) was added**, beyond the seven the spec names, because
    t03's sample made it free.
15. **The expectations in `expected_fetches.json` were written from t04's `*.expected.json`** (titles,
    paragraph counts, canonical URL) and from t03's tables and `expected_statuses.json` (reasons,
    markers). In honesty: one exploratory run of the pipeline over the cassettes came before they
    were written, to confirm that each sample classifies as its task said it would. The values come
    from those tasks' hand-written files, not from that run.

## Operator follow-ups

None. The whole selection is affected (pyproject.toml), so that run is the pull request's `ci`
under agreement 10. It is not a hand-off.

## Follow-up work

1. **Reporting a status for pasted text** (`v1-e04` or E06). ArticleService takes
   `reported_access_status` (for example PAYWALLED for a subscriber's copy). The command leaves it
   UNKNOWN, since the spec asks for no option.
2. **`v1-e04-t07`** can drive its measurement through `fetch --json`. `evidence` carries the counts
   and marker ids it needs.
3. **`test_once_the_docx_parser_is_wired_dropping_the_docx_extra_is_caught`**'s first docstring line
   ("the container does not wire the parser yet") predates this task and is stale. I left it and
   noted the lxml overlap below it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-26

**Notes:**

The command that closes E04's chain, built to the 2026-10-25 amendment: synthetic cassettes, the real
pipeline behind a replay transport, and attestation that can't be skipped by accident.
1. **ac1 to ac4 and every node criterion pass.**
   * ac1's snapshot is read back from the data directory's SQLite file, with the SHA-256 of the
     sample's own bytes.
   * ac2 checks no snapshot row and no blob for four statuses. The robots page is never requested.
   * Every `--json` run is validated against the committed schema, which refuses a mismatch.
   * Attestation is shown storing on the flag or a "y", and refusing on "n", an empty answer,
     `--json` and stdin.
2. **Mutants: 20, with 19 caught.** The survivor (exit 3 decided by a missing snapshot) is equivalent
   by t05's invariant, and is honestly called that. The cassette faults and the planted debug log are
   caught by the hygiene and log tests.
3. **Deviations accepted:**
   * The packages: the PM adds `debate_core.application`, `debate_cli`, `uv.lock`, `scripts`,
     `packages/debate_core/schemas` and `tests/smoke` in the next batch. `ArticleFetch` belongs in
     core.
   * The schema beside `verify_result.v1.json`, with `export_schemas.py --check` guarding drift.
   * `build_cassettes.py`, named for what it does.
   * The end-to-end tests in process, with only the transport replaced through the container's seam,
     and the installed binary covered by the smoke check on the no-request paths.
   * **`uv.lock` edited by hand** is accepted because the change is debate-cli's own two lines,
     `uv lock --check` passes on it and fails on the old one, and CI's `uv sync --locked` checks it
     again. A lock edited by hand stays the exception.
   * ac3's wording: the PM amends it to match the README.
   * No teaser to truncate, with the 200-word rule enforced instead.
4. **Decisions 1 to 15 accepted,** including:
   * `SOURCE_NOT_ACCESSIBLE` with the status in the details;
   * exit 3 for a retrieval only;
   * the prompt only where a person can answer, defaulting to no;
   * the paragraph count from a re-hashed snapshot;
   * the classifier's evidence in the report, never page text;
   * `fetch` classified as never writing a bucket;
   * the honest note that one exploratory run preceded the expectations, whose values came from t03's
     and t04's hand-written files.
5. **Follow-ups:**
   * A `--reported-status` for pasted text is filed by the PM (E04, p3).
   * t07 drives its measurement through `fetch --json`.
   * The stale docstring line goes to whoever next edits that test.
6. **The affected set** is the whole selection (`pyproject.toml`), left to the PR's `ci` under
   agreement 10. The groups run within the line, the one real import-linter failure (fixed in
   `c03f972`), and both process orders with `test_http_fetcher.py` are on record.

No re-review is needed. The Goal is `Succeeded`, so the PR merges in full.
