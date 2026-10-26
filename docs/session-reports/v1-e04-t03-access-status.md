# Session report: v1-e04-t03-access-status

| | |
|---|---|
| Task | `v1-e04-t03-access-status` — Access-status and paywall detection |
| Spec | [`plan_specs/v1/e04-article-retrieval/t03-access-status.yaml`](../../plan_specs/v1/e04-article-retrieval/t03-access-status.yaml) |
| Epic / release | `v1-e04-article-retrieval` / `v1.3` |
| Branch | `task/v1-e04-t03-access-status` |
| Session status | COMPLETE |

## Summary

`AccessClassifier` (`debate_core.retrieval.access`) takes what the fetcher returned (`FetchResult`,
t02) and, for a 2xx document, what extraction made of it (`ExtractedContent` or the
`ExtractionError` it raised, t04). It answers with one `AccessDecision`: the status, a sentence, the
evidence (status code, error kind, refusal type, matched marker, counts, thresholds) and the version
of the marker rules. Markers live in the versioned `retrieval/paywall_rules.v1.json`, pinned by hash.
The classifier makes no request and tries nothing a second time. A page is ACCESSIBLE only when it
is a whole 2xx HTML or PDF document with no marker and enough extracted text. All four goal criteria
and every node criterion pass, and the Goal is `Succeeded`. Worth reading first: the proposed status
for an encrypted PDF (Decisions), the three deviations, and the mutation table.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `status-mapping` — Error and status-code mapping | Done | `AccessDecision`, `AccessEvidence` and the mapping in `retrieval/access.py`: all eight fetch errors, every 4xx/5xx, the 2xx/non-2xx edges, and each of t04's refusals. |
| `paywall-markers` — Paywall and challenge markers | Done | `retrieval/paywall_rules.v1.json`: 8 challenge markers and 22 paywall markers, of seven kinds (header, script src, inline script, class or id, meta, title, visible text). Read with the standard library's `html.parser` (Deviation 1). |
| `truncation-heuristic` — Truncated-text heuristic | Done | Declared length from JSON-LD `wordCount` or `articleBody`; `AccessThresholds` (minimum characters 500, ratio 0.5). The thresholds are passed to the classifier, not read from settings (Deviation 2). |
| `sample-suite` — Saved-sample suite and type check | Done | `tests/fixtures/access/`: seven synthetic pages served as eight responses, with hand-written `expected_statuses.json`. Each 200 page goes through the real `TrafilaturaExtractor` before it is classified, as ArticleService will do it. |

The four nodes share one module and one test file, so they were written together, run red together
(`a43f88d`), then implemented in one commit (`184012d`). Each node's criterion was then run in
`dependsOn` order.

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — every FetchError subtype and HTTP status class maps to a documented AccessStatus | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_access.py -k mapping` → `67 passed`. The mapping is written as a table in the module docstring. `test_mapping_table_covers_every_fetch_error_type` reads t02's `FetchError` union, and `test_mapping_table_covers_every_extraction_refusal` reads t04's `ExtractionError` subclasses, so a ninth error or a new refusal fails a test until it is mapped. The property draws every one of the 32 combinations of a named status (401, 402, 403, 404, 410, 429, 451, 503) with each of four bodies (empty, plain, challenge, paywall), plus about 160 other codes from 400 to 599, against a hand-written copy of the table. |
| ac2 — a 200 response carrying isAccessibleForFree=false or a known overlay marker is PAYWALLED, with the matched marker recorded in the reason | PASS | `-k marker` → `77 passed`. Every one of the 30 markers in the file is planted in an open page and must give its own id, in the reason and in `evidence.marker`. t04's `PaywallMarkerFound` gives PAYWALLED with id `extractor-is-accessible-for-free` and t04's own description of what it found (`isAccessibleForFree=false in JSON-LD`). Twelve near misses (a `no-paywall` class, a newsletter's "subscribe", a phrase inside a script, a comment or a `<template>`, "Just a moment... of silence", a reCAPTCHA script) stay ACCESSIBLE. |
| ac3 — extracted text below a configurable threshold relative to the declared article length is PAYWALLED or ERROR, never ACCESSIBLE | PASS | `-k truncat` → `31 passed`. 499, 500 and 501 words against a declared 1000 give PAYWALLED, ACCESSIBLE and ACCESSIBLE; 499, 500 and 501 characters with nothing declared give ERROR, ACCESSIBLE and ACCESSIBLE. t04's empty extraction gives ERROR, or PAYWALLED when a length is declared. Other thresholds change the outcome as expected. The property draws a declared length (or none), the extracted words, the ratio and the minimum, and requires the status the rule gives (72.5% ACCESSIBLE, 19.0% PAYWALLED, 8.5% ERROR of 200 cases). The threshold can be configured: it is an `AccessThresholds` value given to the classifier. It is not read from settings yet (Deviation 2). |
| ac4 — paywall marker rules live in a versioned data file and classifier results carry the rules version | PASS | `paywall_rules.v1.json`, version `paywall_rules.v1`. `test_marker_rules_file_is_versioned_and_pinned` checks that the version equals the file's name and pins the file's SHA-256, so an edit without a new version fails. `test_marker_rules_version_is_on_every_result` shows that other rules' version reaches every decision. Nine malformed files are refused: upper case, double spaces, leading space, a bad id, an unknown kind, an unknown key, a duplicate id, an empty list, a blank version. |
| Node `status-mapping`: Mapping tests pass | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_access.py -k mapping` → `67 passed in 1.69s` |
| Node `paywall-markers`: Marker detection tests pass | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_access.py -k marker` → `77 passed in 1.65s` |
| Node `truncation-heuristic`: Truncation tests pass | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_access.py -k truncat` → `31 passed in 1.63s` (this includes the `truncated-teaser` sample, whose id matches) |
| Node `sample-suite`: Sample suite passes | PASS | `uv run pytest packages/debate_core/tests/retrieval/test_access.py` → `175 passed in 1.69s` |
| Node `sample-suite`: pyright passes | PASS | `uv run pyright packages/debate_core` → `0 errors, 0 warnings, 0 informations` |

### Red before green

The tests, the samples, `expected_statuses.json` and the rules file were committed against a
skeleton (`a43f88d`). The skeleton had the real models and loader, and a `classify` that answered
ACCESSIBLE with empty evidence and the rules version `skeleton`. Command:
`pytest test_access.py -n 0 -p no:randomly`. Result: **128 failed, 44 passed**.

* Failures: 117 because the status was ACCESSIBLE, the rest because evidence, marker or version was
  missing. Two were `DID NOT RAISE`: an UNKNOWN decision was accepted, and a rules pattern with a
  leading space was accepted. The second was a real bug in the skeleton's model: `NonEmptyText`
  strips the space before my check sees it. The pattern type is now a plain `str` checked as
  written. The hash pin failed as expected.
* The 44 that passed: twelve near misses and the near-miss property, which want ACCESSIBLE and got
  it from a skeleton that answers ACCESSIBLE; the two table-completeness checks over t02's and t04's
  types; eight unusable `wordCount` values and malformed JSON-LD, which want ACCESSIBLE; eight
  malformed rules files and four nonsense thresholds, already refused by the skeleton's models; the
  five "a challenge marker does not change 404/410/402/451/500" cases, which compare two equal
  skeleton answers; and two that want ACCESSIBLE (an open PDF, and 500 or 501 words of 1000). The
  mutants below are what show these checks can fail.

### Mutation runs

Driver: one mutant at a time in `access.py`, the whole of `test_access.py` with `-n 0 -p no:randomly`,
and **a new, empty `HYPOTHESIS_STORAGE_DIRECTORY` for every run** (agreement 8). The file was
restored after each run and its SHA-256 checked after each group. The groups are the three the PM
named.

| Group | Mutant | Result | Caught by |
|---|---|---|---|
| status mapping | RobotsDisallowed → ERROR | killed | robots tests, per-error mapping |
| status mapping | 410 dropped from NOT_FOUND | killed | status table, 404-with-meter test, **mapping property** |
| status mapping | 503 bodies not read for challenge markers | killed | challenge-on-refusal test, **mapping property** |
| status mapping | plain 403 → ERROR | killed | status table, **mapping property** |
| status mapping | `code >= 400` → `code > 400` | **survived**, then killed | a 400 fell through to "not a document", which is also ERROR, so only the sentence changed. The status test now also requires the reason to start "The server" (`c436690`). On re-run the mutant was killed. |
| status mapping | 206 partial content no longer refused | killed | whole-document test |
| status mapping | unlisted extraction refusal → ACCESSIBLE | killed | unknown-refusal test |
| marker match | class token matched as a substring | killed | near misses, **both marker properties** |
| marker match | `<template>` text counted as visible | killed | near misses |
| marker match | script and style text counted as visible (JSON-LD lost with it) | killed | 13 tests, both marker properties and the truncation property among them |
| marker match | title matched by containment | killed | near misses ("Just a moment... of silence", "Access denied to the archives") |
| marker match | header looked up under the wrong name | killed | per-marker test, PDF header test, samples, **planted-marker property** |
| marker match | `property=` of `<meta>` ignored | killed | per-marker test, publisher examples, **planted-marker property** |
| marker match | last match recorded instead of first | killed | 403-overlay test, samples |
| threshold | ratio boundary inclusive | killed | 499/500/501-of-1000 boundary test |
| threshold | minimum boundary inclusive | killed | 499/500/501-character test |
| threshold | characters compared with declared words | killed | 6 tests, **truncation property** among them |
| threshold | shortest declared length taken | killed | longest-length test |
| threshold | boolean `wordCount` counted as 1 | killed | unusable-length test |
| threshold | default ratio 0.4 | killed | boundary and longest-length tests |
| threshold | `articleBody` length ignored | killed | articleBody test |

21 mutants. 20 were killed on the first pass. The survivor was killed after the test change. Each
run took 1.1 to 6.3 s. Every row marked with a property had that property fail on a cold database.
No mutant errored at collection.

What the properties generate (`--hypothesis-show-statistics`, one run each, 200 passing cases each):

* Mapping: all 32 named combinations, the rest drawn from 400 to 599. Statuses are 83.5% ERROR,
  6.5% BLOCKED, 6.0% NOT_FOUND and 4.0% PAYWALLED. Before `bb83da8` it drew codes uniformly and
  93% of cases were "any other status".
* Planted marker: 200 passing cases and 19 invalid. As shares of the 200: visible text 41%, class
  or id 22.5%, header 11.5%, title 9.5%, script src 9%, meta 5.5%, inline script 1% (one of 30
  markers). The parametrized test covers every marker once; this property adds near misses around
  the marker and any amount of text.
* Near misses alone: 200 passing cases and 31 invalid; 198 of them carry at least one near miss.
* Truncation: 72.5% ACCESSIBLE, 19.0% PAYWALLED, 8.5% ERROR expected; 0 invalid.

Coverage of `access.py` under `test_access.py`: 360 statements, 0 missed. 2 partial branches remain:
the fall-through exits of two `match` statements that cover every marker kind.

### Checks before the report

* `uv run --frozen ruff format --check` and `ruff check` on the changed files → clean.
* `uv run pyright packages/debate_core` → 0 errors, run after the last code and test change and the
  last format.
* `uv run --frozen lint-imports` → `Contracts: 18 kept, 0 broken.`
* `uv run scripts/validate_specs.py` → `OK: 464 files, 40 epics, 402 tasks, 22 releases`;
  `--require-succeeded v1-e04-t03-access-status` → `Succeeded`.
* `test_no_network.py` scans every `.py` in `debate_core.retrieval` for network modules, so it
  covers `access.py`. It passes. `html.parser` is not a network module.
* **Affected set (agreement 10).** `uv run scripts/affected_tests.py` chose 45 files. Run with CI's
  command (`python -m pytest -n auto -m "not slow and not live"` over that list) under
  `perl -e 'alarm 115'`, it was stopped at 115 s at 97%. No failure appeared in the output before
  the stop, and no pytest process was left behind. That is past the two-minute line, so the full
  set is left to the pull request's `ci`, as agreement 10 says. Within the line, I ran
  `packages/debate_core/tests/retrieval`, `test_html_extractor.py`, `tests/architecture`,
  `tests/specs` and the always-run list (`test_app.py`, `test_help_rendering.py`,
  `test_import_contracts.py`, `test_thin_handlers.py`) → **1172 passed in 21.79s**. Most of the
  other selections come from quoted-word edges to this task's name and the fixture folder (below),
  not from code this task changed.
* An edit to a sample page selects `test_access.py`, through the import of
  `tests/fixtures/access/samples.py`. To show it, I committed a one-line edit to `open-article.html`,
  ran `affected_tests.py --diff HEAD --explain`, then undid the commit.

## Files changed

* `packages/debate_core/src/debate_core/retrieval/access.py` (new): the classifier, the decision
  and rules models, the page reader and the truncation heuristic. Its docstring holds the full
  mapping.
* `packages/debate_core/src/debate_core/retrieval/paywall_rules.v1.json` (new): the marker rules.
* `packages/debate_core/tests/retrieval/test_access.py` (new): 175 tests.
* `tests/fixtures/access/` (new): seven synthetic pages, `expected_statuses.json` (hand-written),
  `samples.py` (loads them, as t04's `expected_output.py` does) and a `README.md`.
* `plan_specs/v1/e04-article-retrieval/t03-access-status.yaml`: Goal phase `Succeeded`.
* This report.

## Deviations from the spec

1. **`html.parser`, not selectolax or lxml.** The `paywall-markers` node says the markers are
   "parsed with selectolax/lxml". The import contract "Document libraries stay inside
   debate_core.integrations.docx_parser" forbids lxml in `debate_core.retrieval`. That package is
   this task's only one in `constraints.packages`. selectolax is not a dependency. The
   classifier uses the standard library's `html.parser`. It needs no dependency and makes no network
   call, and it never raised on 200,000 fuzzed fragments (probe run before choosing). The markers
   only need attributes, titles and visible text, not a tree.
2. **The thresholds are passed to the classifier, not read from settings.** The `truncation-heuristic`
   node says "a minimum-length threshold from settings". Settings live in
   `debate_core.application.settings`, outside this task's packages, and `retrieval` may not import
   the application layer. `AccessThresholds` (defaults: 500 characters, ratio 0.5) is a constructor
   argument, which meets ac3's "configurable". ArticleService (t05, which owns
   `debate_core.application`) builds it from settings. t04 handled its own limits the same way.
3. **Synthetic samples, not "anonymized saved HTML samples".** The PM asked for synthetic fixtures
   only, and the caselist policy ruling keeps real pages out of the repo. Every page is invented
   (README). Vendor hosts and challenge signatures appear only where a marker matches them. The
   folder also holds `samples.py` and a README beside the pages and their expectations.

## Decisions and assumptions

### Proposed: an encrypted PDF is UNSUPPORTED_TYPE

t04 refuses every encrypted PDF (`EncryptedDocument`), even one an empty password opens. I map it to
**UNSUPPORTED_TYPE**. The other candidates:

| Status | For | Against |
|---|---|---|
| **UNSUPPORTED_TYPE** (proposed) | The platform will not take text out of this form of document, by policy, and trying again will not change that. The status already means "we do not read this", and the reason names encryption. | The enum's docstring says "a content type the extractor cannot handle", and an encrypted PDF is still `application/pdf`. Its docstring would need a clause. |
| PAYWALLED | Encryption is an access control, and the user-supplied-text path (t05/t06) is what a reader with lawful access would use. | No subscription, meter or login is involved. It would sit in the same counts as real paywalls and mix the two. |
| ERROR | Nothing is claimed about the document. | ERROR suggests a transient failure and a retry, and a retry gives the same answer. |
| BLOCKED | | BLOCKED means a challenge or block page was served instead of the document, which is not what happened. |

It is one entry in `_REFUSALS`, and one test case checks it. If the PM chooses differently, both
change in one line each.

### Declared article length (ac3)

* **Where it comes from:** the page's JSON-LD, read from the top-level nodes and `@graph` members:
  `wordCount` (an integer, or digits with optional thousands commas such as `"1,450"`), and the
  number of words in `articleBody`. When there are several, the largest wins, since a larger
  declared length is the stricter test. The articleBody's text is counted and dropped. A test
  checks that none of it reaches the decision. Only HTML pages are read; a PDF declares nothing.
* **Not a declaration:** zero, a negative number, a boolean, a fraction, a word, a list or object,
  or JSON-LD that does not parse.
* **When nothing is declared:** the only length test left is `minimum_characters`. Below it the
  status is ERROR: too little text to be an article, and nothing on the page to say why. At or
  above it, with no marker, the page is ACCESSIBLE. A length is never estimated, for example from
  the boilerplate ratio. ACCESSIBLE without a declaration means a whole 2xx document, no challenge
  or paywall marker, no refusal from the extractor, and at least the minimum of extracted text.
* **Units:** a declared length is in words, so it is compared with extracted words (whitespace
  split). The minimum is in characters, so it is compared with t04's `character_count`.
* **t04's empty extraction** (0 characters, `fallback_used` true) is ERROR, or PAYWALLED when the
  page declares a length. It is never ACCESSIBLE. A test confirms that `text_of_words(0)` matches
  t04's shape.

### The mapping's choices

* **401 → PAYWALLED** (a login wall) unless its body is a challenge. **402 → PAYWALLED.**
  **451 → BLOCKED.** **403 → BLOCKED**, or PAYWALLED when its body carries a paywall marker.
* **429 and 503 → ERROR** unless the body is a challenge page, which makes them BLOCKED. A bare
  throttle or outage says nothing about the document, and ERROR is the status that tells the user
  to try later. The reason gives the status code.
* **404 and 410 are NOT_FOUND whatever the page carries.** A site-wide metering script or "subscribe"
  line on a 404 page does not make it a paywall (the `not-found` sample).
* **`UnsupportedScheme` and `NonPublicAddress` → ERROR.** Neither is a fact about the document. The
  platform refused the hop, and the reason says why, using t02's message (which names a host, never
  a URL).
* **204/205 (no content), 206 (partial content), 1xx/3xx and "no status and no error" → ERROR.** A
  206 is part of a document, and part of a document is never ACCESSIBLE.
* **A metering script makes a page PAYWALLED even when the full text was served.** This follows the
  enum's own rule ("a metered or truncated page is PAYWALLED, never ACCESSIBLE"). It means a metered
  site's free articles are PAYWALLED too.
* **Order on a 2xx:** a challenge marker comes first, then an unsupported type, then t04's
  `PaywallMarkerFound`, then the rules' paywall markers, then any other refusal, then a missing
  extraction, then the truncation heuristic. Within each list the first marker in file order is
  recorded.

### The rules file

* **Kinds:** response header, `<script src>`, inline script (compared case-sensitively, as script
  is), class token or id, `<meta name|property>` with its exact content, whole title, and a
  visible-text phrase. Visible text leaves out scripts, styles, `<template>` and the title. It keeps
  `<noscript>`, which is what a client without JavaScript, like the fetcher, is shown.
* **Not included:** reCAPTCHA and hCaptcha scripts (they appear on ordinary pages' sign-up forms),
  Cloudflare's `/cdn-cgi/challenge-platform/` script (it is on ordinary pages under Cloudflare bot
  management), and `isAccessibleForFree` (t04 reads it, per the PM's context).
* **Versioning:** a change to the markers is a new file name, a new `version` and a new pinned
  hash. The version is the file's name without `.json`. A test pins the hash, so the file cannot be
  edited without a new version.
* **Accuracy on real pages is not measured.** The markers are vendor signatures and common
  phrasings, tested on synthetic pages only. Under the caselist ruling that is measured in place,
  not with saved real pages (Follow-up work).

### Smaller choices

* **The page is decoded for markers only.** It is decoded by its UTF-16 byte-order mark, else as
  UTF-8 with undecodable bytes replaced. All markers are ASCII, so a windows-1252 page reads the
  same. No text from this decoding leaves the classifier.
* **Reasons quote only the platform's own words:** t02's error messages, t04's refusal messages,
  status codes, counts, and the marker's id and description. The sample test checks that no
  extracted paragraph appears in a decision.
* **`AccessDecision` refuses UNKNOWN.** That status is the state before a fetch.
* **The JSON-LD node walk** (top-level, list, `@graph`) is a small copy of the shape t04's private
  `_json_ld_nodes` reads, because t04's lives in an adapter `retrieval` may not import. It reads
  only `wordCount` and `articleBody`. `isAccessibleForFree` is not read again.
* **The sample suite runs the real HTML extractor**, so it checks that t04's output (including its
  refusal on the hard-paywall page) and this classifier fit together the way t05 will combine them.

## Operator follow-ups

None. The affected set was past the two-minute line, so under agreement 10 it is left to the pull
request's `ci` check, not handed to the operator.

## Follow-up work

* **v1-e04-t05-article-service:** read `AccessThresholds` from settings, which needs a settings
  entry for the minimum characters and the ratio. Then call `classify(fetched, outcome)`, where
  `outcome` is the `ExtractedContent` or the caught `ExtractionError` for a 2xx, and None
  otherwise. The decision's reason and `rules_version` are what t05's outcome and log event need.
  t05's spec says it extracts, then classifies, and that order is what this API expects.
* **Measuring the markers on real pages:** count how the bundled rules classify a set of real
  pages, in place, never committing the pages. Count false PAYWALLED and BLOCKED results in
  particular. This belongs to the epic's release validation, or a task the PM names.
* **Optional, t04's area:** t04's extractor already parses JSON-LD. Exposing the declared word
  count as an unverified hint would remove the second, smaller JSON-LD reader here. That would be a
  change to `debate_core.integrations`, outside this task.
* **`affected_tests.py` edges:** the folder name `access` (from the spec's path) matches a quoted
  `"access"` in `packages/debate_api/tests/test_auth_callback.py`. A change to these fixtures
  therefore selects that one extra file. Harmless; noted in case it matters for selection
  measurements.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM (Claude), 2026-10-25

**Notes:**

A classifier that errs the right way: ACCESSIBLE only for a whole 2xx document with no marker and
enough text, and every decision says why.
1. **ac1 to ac4 and every node criterion pass.**
   * The tests were red against a skeleton: 128 failed, with the 44 passes explained one by one. The
     skeleton's leading-space bug was found by its own test.
   * The two table-completeness tests, over t02's `FetchError` union and t04's refusals, are the
     right guard: a ninth error or a new refusal fails until it is mapped.
   * The hash-pinned, versioned rules file meets ac4 exactly.
2. **Mutants: 21.** The one first-pass survivor (`>= 400` to `> 400`) was killed by a sharper test,
   not explained away. Every property was checked on a cold database, and its generation statistics
   are reported. Re-weighting the mapping property after 93% of cases fell in "any other status" is a
   good catch.
3. **Rulings:**
   * **An encrypted PDF is UNSUPPORTED_TYPE,** as proposed: the platform will not read that form of
     document, and a retry changes nothing. Add the clause to the enum's docstring in the same line
     of change.
   * **A metered page is PAYWALLED even when the full text was served.** That is accepted, as the
     enum's own rule and the conservative side of the spec's forbidden list. A metered site's free
     articles go through t05/t06's user-supplied-text path. How often this happens on real pages is
     part of the measurement below.
4. **Deviations 1 to 3 accepted:**
   * `html.parser` under the import contract, fuzzed before it was chosen;
   * the thresholds as a constructor value for t05 to build from settings, as t04 did with its
     limits;
   * synthetic samples only.
5. **Accepted as made:**
   * the declared length from JSON-LD `wordCount` and `articleBody`, largest wins, and nothing ever
     estimated;
   * the units kept apart (words to words, characters to characters);
   * the mapping's choices (401 and 402, 403 with a marker, 451, 429 and 503, 404 and 410 whatever
     the page carries, 206 and the other non-documents);
   * the order of checks on a 2xx;
   * the left-out reCAPTCHA, hCaptcha and Cloudflare scripts;
   * decoding for markers only;
   * reasons quoting only the platform's own words;
   * UNKNOWN refused;
   * the small JSON-LD walk copied rather than imported across the boundary.
6. **Follow-ups:**
   * The real-page measurement joins the E04 measurement the PM files from `v1-e04-t04`'s review, in
     place and never committed. It covers false PAYWALLED and BLOCKED decisions, metered sites'
     free articles, the UNDETERMINED joins and refused PDFs.
   * Exposing the declared word count as a t04 hint is optional, for t05 to take if it touches that
     adapter.
   * The `access` quoted-word edge is noted for t01's selection work.
7. **The affected set** (45 files) stopped at 97% with no failure, and is left to the PR's `ci` under
   agreement 10. Retrieval, the extractor, the architecture and spec checks and the always-run list
   passed: 1,172 tests.

No re-review is needed. The Goal is `Succeeded`, so the PR merges in full once the docstring clause is
committed.
