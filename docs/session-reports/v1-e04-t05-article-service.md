# Session report: v1-e04-t05-article-service

| | |
|---|---|
| Task | `v1-e04-t05-article-service` — ArticleService orchestration |
| Spec | [`plan_specs/v1/e04-article-retrieval/t05-article-service.yaml`](../../plan_specs/v1/e04-article-retrieval/t05-article-service.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t05-article-service` |
| Session status | COMPLETE |

## Summary

`ArticleService` (`debate_core/application/article_service.py`) composes E04's earlier tasks
through ports and pure procedures: canonicalize (t01), fetch (t02's port), extract for a 2xx (t04's
port), classify (t03's `AccessClassifier`, thresholds from settings), apply rel=canonical, then
snapshot (E03's `SnapshotService`) and upsert the Article. Every non-ACCESSIBLE status,
UNSUPPORTED_TYPE included, records the status on the Article and stores no snapshot and no blob; the
outcome and its log event carry the classifier's reason and rules version. Dedupe works by canonical
URL and by the newest publisher snapshot's normalized-text hash, under a re-fetch age from settings
with a `refresh` override. `ingest_user_text` stores attested text as USER_SUPPLIED. All six Goal
criteria and every node criterion pass, so the phase is `Succeeded`.

**For the PM to look at first:** the 2026-10-19 rules needed two small additions to
`debate_core.retrieval`, which is outside `constraints.packages` (Deviation 1). They are a public
`fetch_target_url` and a new rule member, `RelCanonicalRule.SITE_ROOT_REFUSED`. Second, the
re-fetch age of 168 hours is my own number (Decision 3).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `outcome-types`: RetrievalOutcome and service skeleton | Done | `RetrievalOutcome` (a frozen dataclass whose construction refuses a publisher snapshot on any status but ACCESSIBLE) and `ArticleService(articles, snapshots, fetcher, extractor, clock, id_generator, settings, max_user_text_bytes)`. |
| `pipeline`: accessible-path pipeline | Done | Includes the 2026-10-19 rules, shown failing first (see the red runs below). |
| `failure-paths`: explicit failure outcomes | Done | Twelve failure cases, each with a hand-written reason; one `INFO` event per outcome. |
| `dedupe-refetch`: dedupe and re-fetch policy | Done | |
| `user-supplied`: USER_SUPPLIED text ingestion | Done | Attestation, source URL and quality gates; nothing is stored on a refusal. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: an accessible URL gives an Article (canonical URL, identifiers, ACCESSIBLE) and a snapshot with both hashes and both versions | PASS | `test_an_accessible_page_becomes_an_article_and_a_snapshot_with_both_hashes`: the DOI comes from the URL; the raw hash is SHA-256 of the literal body; the normalized hash is SHA-256 of the paragraphs as typed; the versions are `fake-extractor/fake-1.0.0` and `evidence-normalizer-v1`. |
| ac2: paywalled, blocked, robots-disallowed and 404 fixtures give the matching status with a reason and no snapshot | PASS | `test_failure_outcomes_carry_the_status_and_reason_and_store_no_snapshot`, 12 cases: 404, 402, a metered page served whole, a bot challenge, 403, robots, timeout, 500, too short, an image, a `text/plain` page the extractor read, and an encrypted PDF. Each case checks the status, the reason, `rules_version`, no snapshot record and an empty blob store. |
| ac3: two tracking variants are one Article; inside max age no fetch; after it the snapshot is reused when the hash is unchanged | PASS | `test_dedupe_two_tracking_variants_are_one_article`, `…within_the_refetch_age_makes_no_fetch_call`, `…after_the_refetch_age_fetches_and_reuses_the_snapshot_when_the_text_is_unchanged`. In the last one the bytes differ and the text does not, and no new blob is written. |
| ac4: `ingest_user_text` stores a USER_SUPPLIED snapshot and requires the source URL and an attestation flag | PASS | `test_user_text_*`, 14 tests: no attestation and a truthy non-`True` attestation both refuse; a blank, invalid or `mailto:` source URL refuses; the quality gates refuse; nothing is stored on any refusal. |
| ac5: every outcome logs a structured event with correlation id, canonical URL, access status, elapsed time and no page content | PASS | `test_log_event_*`: a readable page, four refusals, a stored-snapshot answer and user text. Each checks the fields exactly (elapsed 250 ms from the fetcher fake advancing the clock), and checks that neither a sentinel phrase nor page text is in the message or any `extra` field. The same tests also ran in one process after the structured-output, search-index-holder and HTTP-fetcher suites (`-n 0 -p no:randomly`): 250 passed. |
| ac6: a site-root canonical on a deeper page is refused; no fetch to a guessed host; both URLs stored; tests shown failing first | PASS | Red at `1dc4516`, and each rule red on its own against the final tests (below). Green at `475f7cb` and after. |
| Node `outcome-types`: service module exists, contains `class ArticleService` | PASS | `grep -c 'class ArticleService' …/article_service.py` → `1` |
| Node `pipeline`: `uv run pytest …/test_article_service.py -k accessible` | PASS | `8 passed in 5.65s` |
| Node `failure-paths`: `… -k failure` | PASS | `15 passed in 3.75s` |
| Node `dedupe-refetch`: `… -k dedupe` | PASS | `11 passed in 2.40s` |
| Node `user-supplied`: `uv run pytest …/test_article_service.py` | PASS | `58 passed in 2.72s` |
| Node `user-supplied`: `uv run lint-imports` | PASS | `Contracts: 18 kept, 0 broken.` |

### The 2026-10-19 rules, shown failing first

`1dc4516` committed the service and every test with the three rules in naive form:
`fetch_target_url` returned `canonicalize_url(url)`, `apply_rel_canonical` had no site-root rule,
and the snapshot stored the identity key. Against it,
`.venv/bin/python -m pytest -p no:randomly -n 0 --tb=line -q packages/debate_core/tests/application/test_article_service.py packages/debate_core/tests/retrieval/test_canonical_url.py`
gave `19 failed, 351 passed in 0.61s`:

* 6 `test_fetch_target_*` cases (as given ×3, wrapper destination ×3) and 5 `test_rel_canonical_site_root_*` cases;
* `test_rel_canonical_rules_are_stable_storable_values`, t01's pin of the rule values, which gains
  `site_root_refused`;
* 7 service tests, all failing on the fetch rule: the fake 404s the canonical form it was asked
  for. They are the AMP host, the wrapper destination, the site root, the same-site and both-URLs
  test, and three tests whose URL carries tracking parameters (the ac1 test, the tracking variants,
  and user text after a paywalled retrieval).

At `1dc4516` the fetch rule failed first, so the site-root and both-URLs assertions were never
reached in the service tests. Each naive rule was therefore also restored **alone** against the
final tests (`655f42a`), in both files:

| Rule restored to its naive form | Result | Failing tests |
|---|---|---|
| fetch the canonical form | 12 failed | the 6 `fetch_target` cases; the AMP-host, wrapper, ac1, same-site/both-URLs, tracking-variant and paywalled-then-user-text service tests |
| accept a site-root canonical | 6 failed | `test_an_accessible_page_naming_the_site_root_as_canonical_keeps_its_own_url` and the 5 retrieval site-root cases |
| snapshot stores the identity key | 2 failed | the AMP-host test and the same-site/both-URLs test, at their `snapshot.canonical_url` assertions |

### Mutation runs (agreement 8)

23 mutants of `article_service.py` were run against `test_article_service.py`. Each run used a
fresh `HYPOTHESIS_STORAGE_DIRECTORY`; these tests use no Hypothesis properties, so that only follows
the agreement. Every run ran its tests to a result (exit 1, no collection errors), and the source
was restored after each. All were caught:

| Mutant | Caught by |
|---|---|
| snapshot on PAYWALLED, the outcome guard disabled too | the metered-page failure case |
| snapshot on BLOCKED, guard disabled | the bot-challenge failure case |
| snapshot on ERROR, guard disabled | the too-short failure case, the settings-threshold test |
| snapshot on UNSUPPORTED_TYPE, guard disabled | the `text/plain` failure case. It was added after the first run, where only the guard's own test caught this mutant. |
| snapshot on NOT_FOUND / ROBOTS_DISALLOWED, guard disabled | only the guard's own test. These two are **equivalent** in the service: extraction runs only for a 2xx with no error, so no text exists for either status. |
| the outcome guard removed alone | its own test (`test_failure_outcome_cannot_carry_a_publisher_snapshot`) |
| no lookup by canonical URL before the fetch | 10 tests, the tracking variants among them |
| identity key = the URL as given | the tracking variants; paywalled-then-user-text |
| no lookup under the rel=canonical identity | `test_dedupe_finds_an_article_stored_under_its_rel_canonical` |
| dedupe on raw size instead of the normalized hash | the reflowed-bytes test; the normalizer-version test |
| any text counts as unchanged | changed text; newest-only |
| normalizer version not compared | `test_dedupe_never_reuses_a_snapshot_made_under_another_normalizer_version` |
| compared with the oldest snapshot | newest-only; normalizer version |
| provenance ignored when picking the snapshot | the user-text-only article is fetched; user text distinguishable |
| max age boundary `>=` → `>` | the after-age test; the settings age test |
| freshness ignores the last status | the failure-after-a-readable-retrieval test |
| max age not read from settings | the settings age test |
| `refresh` ignored | 5 tests |
| a readable re-fetch does not reset the age | the after-age test's follow-up call |
| attestation not required | both attestation tests |
| attestation read as truthy | the truthy-attestation test |
| source URL not checked | 7 user-text tests |

### Checks before the report (agreement 10)

* `uv run scripts/affected_tests.py`: **361 of 501 test files (72.1%)**. The root `conftest.py`
  imports `settings.py` through `ports/model_router.py`, so changing settings selects everything that
  uses its fixtures. That set is well past two minutes, so it is left to the pull request's `ci`, as
  agreement 10 says, and not handed over. Instead these ran, each under `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest -n auto -m "not slow and not live"`:
  * the test directories of what changed, the always-run list, and the config command tests:
    `packages/debate_core/tests/retrieval tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py packages/debate_cli/tests/test_config_command.py`
    → `1166 passed in 28.18s`;
  * `packages/debate_core/tests/application` → `3824 passed in 97.17s`.

  A first attempt ran both groups as one command and was stopped by its alarm at 92%, with no
  failure in what had run (load average about 7 on 11 cores). No pytest workers were left behind.
* `uv run ruff format --check .` → `1393 files already formatted`; `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations`
* `uv run lint-imports` → `Contracts: 18 kept, 0 broken.`
* `uv run --frozen python scripts/check_thin_handlers.py` → `OK: 61 CLI command and API route handlers within 25 statements`
* `uv run scripts/validate_specs.py` → `OK: 464 files, 40 epics, 402 tasks, 22 releases`;
  `--require-succeeded v1-e04-t05-article-service` → `Succeeded`

## Files changed

* `packages/debate_core/src/debate_core/application/article_service.py` (new): the service, the
  outcome, `access_thresholds(settings)`, and three refusals (`InvalidSourceUrl`,
  `UserTextNotAttested`, `UserTextRejected`, all `DomainError`s).
* `packages/debate_core/src/debate_core/application/settings.py`: the `articles` group
  (`ArticleSettings`): `refetch_after_hours`, `access_minimum_characters`, `access_truncation_ratio`,
  `html_fallback_minimum_characters`, `pdf_max_bytes`, `pdf_max_pages`, `pdf_max_stream_bytes`.
* `packages/debate_core/src/debate_core/retrieval/canonical_url.py` and `__init__.py`:
  `fetch_target_url`, plus the site-root rule in `apply_rel_canonical` with its rule member
  (Deviation 1).
* `packages/debate_core/src/debate_core/testing/fakes/providers.py`: the 2026-10-21 amendment, and
  more (Deviation 2).
* Tests: `tests/application/test_article_service.py` (new, 58 tests);
  `tests/retrieval/test_canonical_url.py` (+15 cases, and `site_root_refused` added to the rule-value
  pin); `tests/application/test_fakes.py` (the 404 answer, and the extractor's refusal type).

## Deviations from the spec

1. **Two additions to `debate_core.retrieval`, outside `constraints.packages`
   (`[debate_core.application]`).**
   * `fetch_target_url(url)`: the URL as given, or the destination a link wrapper or AMP cache
     carries literally. The spec asks the service to fetch "the URL as given (or a wrapper's literal
     destination)", and the unwrapping lives in private functions of `canonical_url.py`. The
     service could only have done it by importing private names or by copying the wrapper parsing.
   * `RelCanonicalRule.SITE_ROOT_REFUSED` and its check in `apply_rel_canonical`. The rule could
     have been written in the service. But `RelCanonicalDecision` is the value t01 designed to
     record which rule decided ("a new rule is a new member"), and the check is pure URL logic
     beside the other rel=canonical rules. No other caller of `apply_rel_canonical` exists, so no
     behaviour changed elsewhere.

   **Proposed amendment:** add `debate_core.retrieval` to this task's `constraints.packages`.
2. **The fakes in `debate_core.testing` changed beyond the amendment's sentence.**
   * Done per the amendment: an unknown URL is answered with `HttpStatusError(404)` and `UNKNOWN`.
   * Also: `FakeArticleFetcher.add` attaches the `HttpStatusError` a real 4xx/5xx carries, and takes
     `error=` for transport failures (`status_code=None`).
   * Also: `FakeContentExtractor` raises `UnsupportedContentType`, the refusal its port names,
     instead of a bare `ValueError`, which the service's `except ExtractionError` would not catch.
   * `test_fakes.py` was updated for these and gained one test.

## Decisions and assumptions

1. **An Article is upserted for every outcome.** A non-ACCESSIBLE outcome writes its status onto the
   Article (`access_status` is "most recent retrieval outcome") and nothing else. A user who later
   supplies text for that URL lands on the same Article. A new Article's title is the page's title
   hint, or failing that its canonical URL, since `title` is required. A later readable retrieval
   replaces a URL-only title with the page's hint, and otherwise never changes a title (metadata is
   E06's).
2. **Both URLs:**
   * `Article.canonical_url` is the identity key. When the page's rel=canonical is accepted, that is
     the declared URL; otherwise it is the canonical form of the URL that answered.
   * `SourceSnapshot.canonical_url` is the URL that answered, after redirects. That is what the
     field's own description says it holds ("The URL actually retrieved, after redirects").
   * The outcome also carries the URL as given (`requested_url`) and the URL fetched (`fetch_url`).
   * rel=canonical is applied only on the readable path, after classification, in the spec's order.
3. **Re-fetch age: 168 hours (7 days), `articles.refetch_after_hours`.** The spec leaves the number
   open. A week keeps a coach's repeated lookups off the publisher, and articles rarely change in a
   week. Easy to change in a profile.
4. **"Last readable retrieval" is `Article.updated_at` while its status is ACCESSIBLE.** A snapshot
   is immutable, so its `retrieved_at` cannot mark a re-fetch that reused it. Without this, every
   call after the first expiry would fetch again. The service sets `updated_at` on every readable
   retrieval, reused snapshot or not. A fresh answer also needs a publisher snapshot to exist.
5. **Unchanged means "the same as the newest publisher snapshot, under the same normalizer
   version".** It is never compared with an older snapshot (A, then B, then A makes a third
   snapshot), and never with a user-supplied one. The raw bytes may differ.
6. **The site root is path `/` with no query** (`/?p=123` names a page). Both sides are judged in
   canonical form, so an AMP home page (`/amp`) is the root. The rule is checked only for a canonical
   that SAME_SITE or AMP_CACHE_ORIGIN would accept; another site's root stays CROSS_SITE_REFUSED.
7. **The fetch target is the URL as given, whitespace stripped and nothing else**: no case folding,
   no tracking parameters dropped. Wrappers and AMP caches whose destination is literal are
   unwrapped, nested ones included. An AMP cache URL's origin counts as literal, since the cache
   spells it out in its path.
8. **`extractor_version` on a publisher snapshot is `<extractor_name>/<extractor_version>`.** t04's
   versions (`html-1+trafilatura-…`) do not say whether the readability fallback produced the text;
   the name does.
9. **User-supplied text:**
   * `attested` must be exactly `True`, and is checked first.
   * `reported_access_status` defaults to `UNKNOWN` and goes on the snapshot. It goes on the Article
     only when this call creates it: a report never overwrites a status the platform measured.
   * The quality gates are the same bar as a fetched page: non-blank, at least
     `access_minimum_characters` (500), at most `max_user_text_bytes` of UTF-8, and valid Unicode.
     The composition root passes `http.max_response_bytes` as that limit.
   * The raw blob is the text in UTF-8 (`text/plain; charset=utf-8`), and `extractor_version` is
     `user-supplied-text-1`.
   * Identical text supplied again reuses its snapshot. Blobs are written before a new Article is
     saved, so a refusal leaves nothing behind.
   * Cards take `provenance_mode` from the snapshot (`evidence/card_mapping.py`, E03), so
     USER_SUPPLIED reaches them.
10. **Logging:**
    * One `INFO` event per outcome from `debate_core.application.article_service`:
      `article retrieval` or `user text ingested`.
    * Fields: `correlation_id` (the caller's, or minted from the `IdGenerator`), `canonical_url`,
      `access_status`, `elapsed_ms` (by the injected clock), `fetched`, `snapshot_id`,
      `snapshot_reused`, `provenance_mode`, `reason`, `rules_version`.
    * The fetched URL is not logged. Its query can carry a token, which is t02's reason for naming
      hosts only.
11. **Identifiers come from the URLs only** (as given, fetched, answered, canonical), never from page
    text, whose references name other works. A known identifier is never replaced.
12. Extraction runs synchronously inside the async `retrieve`, as the port expects of a single
    caller. `ProviderUnavailable` from the fetcher propagates; it is not an outcome.

## Operator follow-ups

None. The affected set is past the two-minute line and is left to the pull request's `ci` under
agreement 10; that is not a hand-off.

## Follow-up work

* **v1-e04-t06-fetch-command (wiring):**
  * build `ContentTypeDispatcher(html=TrafilaturaExtractor(minimum_characters=settings.articles.html_fallback_minimum_characters), pdf=PdfExtractor(max_bytes=…pdf_max_bytes, max_pages=…pdf_max_pages, max_stream_bytes=…pdf_max_stream_bytes))`
    and `HttpArticleFetcher` in the composition root;
  * pass `settings.articles` and `max_user_text_bytes=settings.http.max_response_bytes` to the
    service, and `refresh` from `--refresh`;
  * map `InvalidSourceUrl`, `UserTextNotAttested` and `UserTextRejected` to exit 1, which they get
    as `DomainError`s;
  * the two pinned integration lists will change (t04's note).
* **The HTML extractor's `max_bytes` (10 MiB) has no setting.** The PM's list named the fallback
  minimum and the PDF limits, so I stopped there. `http.max_response_bytes` (25 MiB) bounds the
  body before it.
* **Freshness before a fetch is found only under the input's canonical form** (E04 or a later
  task). A short link whose rel=canonical is a different path is fetched on every call. The
  canonical URL itself is not: it finds the Article directly
  (`test_dedupe_finds_an_article_stored_under_its_rel_canonical`). Fixing the short-link case needs
  a repository lookup by a snapshot's fetched URL, which is a port change.
* **Dedupe by DOI** (architecture §9, mentioned in t01) is not done. `ArticleRepository` has no
  lookup by identifier, and this task's criteria ask for canonical URL and text hash only.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
