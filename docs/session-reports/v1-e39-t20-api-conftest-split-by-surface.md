# Session report: v1-e39-t20-api-conftest-split-by-surface

| | |
|---|---|
| Task | `v1-e39-t20-api-conftest-split-by-surface` — The pilot API's test world split by surface, so a change selects only the tests it reaches |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t20-api-conftest-split-by-surface.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t20-api-conftest-split-by-surface.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t20-api-conftest-split-by-surface` |
| Session status | COMPLETE <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The API conftest is split by surface. `PilotWorld` is now sign-in alone, and `SearchWorld`,
`DownloadWorld`, `LandscapeWorld` and `EverySurfaceWorld` add their own pieces, each behind a
fixture of its own. Each test file names its surface in a four-line `world` fixture of its own, so
no test body changed. The corpora, the parser and the download's sources are session-scoped
fixtures, and the conftest's module code now needs no repository file (it needed the parser, the
writer, Cognito and the index modules). The collected ids are unchanged: 1,064 before and after,
none lost or added. All 1,041 API tests and the 23 slow browser tests pass.

**Look at this first: the narrowing is mostly masked by an edge outside this task's packages.**
`debate_api/app.py` imports `debate_api/container.py` lazily inside `create_app`, for uvicorn's
`--factory`. To the selector, that edge brings the whole Lambda composition root (the parser, the
writer, the index reader, Cognito, CloudWatch, S3) to every test that builds the app, whichever
world it uses. So over t32's 41 commits the API files selected fall only from 408 to 386: fewer in
14 commits, more in none. That meets ac1 as written, and the Goal is `Succeeded` on that basis. With
that one edge removed as well, the split takes the parser-only merge `387c961` from 24 API files to
8. Most of what remains comes through services that `PilotServices` requires of every world, which
is the floor for any test of the app. Deviation 1 and the PM question give the measured options.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `api-world-split` (API world split) | Done | `5668dce`. The node criterion passes. |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1: the collected ids are unchanged | PASS | **Default selection:** `.venv/bin/python -m pytest packages/debate_api/tests --collect-only -q -p no:randomly -p no:cacheprovider`, ids sorted. Before (base `6f3fe35`, today's dev, taken before any edit): 1,041. After (`5668dce`): 1,041. `comm`: 0 lost, 0 added. **With the slow browser suite:** the same with `-m "slow or live or not slow"`, the base's test files checked out over the committed branch and restored from HEAD afterwards: 1,064 before, 1,064 after, 0 lost, 0 added. `test_removal_runbook_index_prune.py`, which v1-e39-t15 deleted, is in neither list. |
| ac1: t32's measurement over the same merges selects fewer API files, recorded in the report | PASS, with Deviation 1 | Under [The measurement](#the-measurement). t32's 41 commits (t27's merge, t38's 20 and t28's 20), `--diff <commit> --graph <rev>` with today's dev's `affected_tests.py`. Before is `6f3fe35`, after is `5668dce`. Of the 37 that are not whole: 408 API files before, 386 after. 14 commits select fewer and none selects more. |
| Node `api-world-split`: `uv run pytest packages/debate_api/tests` | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_api/tests -p no:cacheprovider -q` → `1041 passed in 15.77s` (the same interpreter and arguments as `uv run pytest`, with the time limit on the interpreter). |
| PM: no assertion changed and no test removed (forbidden) | PASS | `git diff -U0 6f3fe35 5668dce -- packages/debate_api/tests ':!packages/debate_api/tests/conftest.py' \| grep '^-[^-]'` → five lines, each a module docstring's `conftest.CORPUS`, now `conftest.search_corpus`. Every other change in the test files is an added fixture. The ids are unchanged (above). |
| PM: the slow browser suite still passes | PASS | `perl -e 'alarm 115; exec @ARGV' .venv/bin/python -m pytest packages/debate_api/tests/browser -m slow -n 4 -p no:cacheprovider -q` → `23 passed in 18.37s`. It uses `every_surface_world`. |
| PM: mutant 1, the corpus built at import again | PASS (caught) | Under [Mutants](#mutants). The API tests pass it (`1041 passed`); the narrowing check fails it in both readings. |
| PM: mutant 2, one surface fixture pulling in another's pieces | PASS (caught, by the blocked reading only) | Under [Mutants](#mutants). The API tests pass it (`1041 passed`); the real graph cannot see it, and the reading without `app.py`'s edge fails it. |

### The measurement

**Method.** t32's `measure.py`, copied from its scratchpad, run as t39 ran it: one process per batch
of seven commits, each under a 118 s alarm, the graph built once per process. Both columns use
today's dev's `affected_tests.py` (this task does not change it), each over its own tree:
`6f3fe35` before, `5668dce` after. "API files" counts the selected files under
`packages/debate_api/tests/` (24 test files). The last two columns are the same runs with one edge
taken out of the graph, `debate_api/app.py` → `debate_api/container.py` (`measure_blocked.py`), to
show what that edge hides. Nothing in the repository runs that way.

| Commit | API files before | After | Before, without `app.py`'s edge | After, without it |
|---|---|---|---|---|
| `8051c77` v1-e32-t27-branches-and-mechanisms-counted-first | 2 | 2 | 2 | 2 |
| `a077632` PM batch 2026-10-26s | 0 | 0 | 0 | 0 |
| `9c99f03` Refresh ROADMAP.md and docs/README.md | 0 | 0 | 0 | 0 |
| `030cc4c` v1-e05-t07-usage-telemetry | 24 | 23 | 24 | 23 |
| `1ace4e5` v1-e32-t25-readable-impact-chains | 2 | 2 | 2 | 2 |
| `65f56d7` v1-e40-t13-bucket-mode-report-counts-held-sources | 2 | 2 | 2 | 2 |
| `8a597db` Refresh ROADMAP.md and docs/README.md | 0 | 0 | 0 | 0 |
| `8cf5e91` PM batch 2026-10-26r | 0 | 0 | 0 | 0 |
| `7e271ed` v1-e06-t01-citation-service | 24 | 23 | 24 | 23 |
| `57e3060` Refresh ROADMAP.md and docs/README.md | 0 | 0 | 0 | 0 |
| `321b5ee` v1-e32-t22-scenario-vocabulary | 24 | 23 | 24 | 23 |
| `f5a8221` v1-e33-t09-style-profile-version-refusal | 24 | 22 | 24 | 22 |
| `ad7f5a1` Refresh ROADMAP.md and docs/README.md | 0 | 0 | 0 | 0 |
| `206f2ec` v1-e04-t06-fetch-command | whole | whole | whole | whole |
| `b3273fb` v1-e32-t24-unlabelled-plan-affs | 2 | 2 | 2 | 2 |
| `d0cc9c3` Refresh ROADMAP.md and docs/README.md | 0 | 0 | 0 | 0 |
| `af7052e` v1-e05-t08-bedrock-invoke-access | 22 | 22 | 22 | 22 |
| `ec02c33` v1-e32-t07-model-classification-stage | 2 | 2 | 2 | 2 |
| `2a33947` v1-e32-t17-kritikal-affirmatives | 2 | 2 | 2 | 2 |
| `987fa89` Refresh ROADMAP.md and docs/README.md | 0 | 0 | 0 | 0 |
| `2110c13` v1-e04-t05-article-service | 22 | 22 | 22 | 22 |
| `9101764` v1-e30-t24-status-residue-and-held-digests | 24 | 22 | 24 | 22 |
| `9f11fe1` v1-e30-t25-store-sync-withholding | 24 | 22 | 24 | 22 |
| `29f074d` v1-e33-t02-lossless-card-writer | 24 | 23 | 24 | 23 |
| `edf8eba` v1-e04-t01-url-canonicalization | whole | whole | whole | whole |
| `30c5157` v1-e31-t20-long-cuts-and-limits | 24 | 22 | 24 | 22 |
| `29c8293` v1-e33-t01-file-recipe-format | 24 | 23 | 24 | 23 |
| `387c961` v1-e31-t19-remaining-cite-shapes | 24 | 22 | 24 | **8** |
| `9877884` v1-e31-t15-zip-guard-and-exporter-quirks | 24 | 23 | 24 | 23 |
| `72c1d05` v1-e30-t20-removal-output-loose-ends | 2 | 2 | 2 | 2 |
| `3f2530b` v1-e30-t23-held-digests-and-manifest-fsync | 24 | 22 | 24 | 22 |
| `801883a` v1-e34-t27-wrapper-and-check-launchd-options | 2 | 2 | 2 | 2 |
| `993063c` v1-e30-t19-residue-clearing-gaps | 24 | 22 | 24 | 22 |
| `8bbe1cd` v1-e34-t16-dry-run-names-no-home-path | 2 | 2 | 2 | 2 |
| `ea09eb1` v1-e34-t26-pending-work-and-banner-words | 2 | 2 | 2 | 2 |
| `0a43e88` v1-e30-t22-held-rows-publish-nothing | 24 | 22 | 24 | 22 |
| `d730de0` v1-e05-t04-prompt-registry | whole | whole | whole | whole |
| `55d0b4b` v1-e05-t02-bedrock-adapter | whole | whole | whole | whole |
| `1e63363` v1-e34-t25-reinstall-keeps-every-setting | 2 | 2 | 2 | 2 |
| `b0820cf` v1-e31-t21-cluster-shapes-and-sampler | 2 | 2 | 2 | 2 |
| `4c5a766` v1-e31-t16-version-directory-retention | 4 | 4 | 4 | 4 |
| **Sum over the 37 not whole** | **408** | **386** | **408** | **372** |

**How to read it:**

- **What dropped:** the files that use no fixture. Before, the conftest's module code
  (`CORPUS = _corpus()`, `ISSUER = issuer_for(...)`) reached the parser, the writer, Cognito, the
  index modules and the domain. Every file beneath it, `test_smoke.py` and
  `test_audit_record_schema.py` among them, was selected by a change to any of them. Now module code
  needs nothing, and those two files drop out of 14 commits.
- **Why the world users did not drop:** `--explain` over the branch graph. For a parser change, all 19
  files that use a world come through `debate_api.app`, which imports `debate_api.container`, which
  imports the parser. Five of them (`test_auth_pages_and_script.py`, `test_copy_card.py`,
  `test_search_pages.py`, `test_landscape_pages.py`, `test_exposure.py`) also import `debate_api.app`
  themselves for `PRIVATE_NO_STORE`, and `test_session_lifetimes.py` imports the container.
- **Why most rows stay at 22 or 23 even without that edge:** those merges change modules that the
  services every world must build import. `--diff f5a8221 --graph 5668dce --explain`:
  `test_auth_csrf.py <- uses the auth_world fixture …, which needs debate_core.application.card_download, which imports debate_core.application.ports.parsed_store, which changed`.
  `9101764`: `… auth_world … needs debate_core.application.search_index_holder, which imports … ports.suppression`.
  `PilotServices` takes every surface's service, so even the sign-in world builds them. That is the
  floor for any test of the app.
- **The rows of 2** are the two image tests, `test_card_download_image.py` and
  `test_landscape_image.py`, which read every Python file.
- **Where the split does narrow on the real graph:** for modules the container does not import. A
  change to `debate_core/testing/search_index.py` selects 22 API files at base and 13 on the branch,
  from the narrowing check below. None of the 41 commits changed one alone.

### Mutants

No test in the repository can catch either mutant. The API tests pass whatever the conftest
needs, and `tests/scripts` tests the selector on synthetic trees. So, as the PM's brief said, the
narrowing test is in the evidence rather than in `tests/scripts`: `selection_check.py`, kept in the
scratchpad. It takes a revision, builds that revision's graph with that revision's
`affected_tests.py`, and changes one probe file at a time:

- **the parser** and **the E33 writer**, the download's pieces;
- **the index reader** and **the in-memory index source**, the search's;
- **the Cognito adapter**, every world's.

The API files each probe must select are written by hand. They come from the surface each test file
names in its `world` fixture, plus the files that reach the probe by themselves: the two image tests
read every Python file, `test_card_download_limits.py` imports the parser, writer and index modules,
and `test_session_lifetimes.py` imports the container. It reads the graph two ways: as the script
builds it, and `--blocked`, without `app.py`'s edge to the container. The blocked reading is the
conftest's own narrowing. Each mutant was committed, run, and dropped with `git reset --hard 5668dce`.
Neither involves Hypothesis, so agreement 8's database rule has nothing to isolate.

| Tree | Real graph | Without `app.py`'s edge |
|---|---|---|
| Base `6f3fe35` (shows the check fails) | fails 3 of 5: parser 24 (expected 22), in-memory source 22 (13), Cognito 24 (21) | fails 5 of 5: parser 24 (8), writer 22 (8), reader 22 (14), source 22 (13), Cognito 24 (21) |
| Branch `5668dce` | **all 5 ok** (22, 22, 22, 13, 21) | **all 5 ok** (8, 8, 14, 13, 21) |
| Mutant 1 `5572044`: `CORPUS: Final = corpus_documents(download_documents(build_download_sources(DebateDocxParser())))` at module level | **caught**: parser 24 (expected 22), adding `test_audit_record_schema.py` and `test_smoke.py` through "module code … needs … docx_parser.parser" | **caught**: parser 24 (expected 8) |
| Mutant 2 `b8b7844`: `search_corpus_index` takes `download_parser` and publishes under its version | not caught: every world already reaches the parser through `app.py` | **caught**: parser 14 (expected 8), adding the six search files through "uses the search_world fixture …, which needs … docx_parser.parser" |

Both mutants pass the API tests: `1041 passed in 9.69s` and `1041 passed in 9.14s`. Mutant 2 is the
shortcut that fixes the one red test this split hit (Decision 4): it would have passed every test and
quietly undone the search surface's narrowing.

## Files changed

- `packages/debate_api/tests/conftest.py`: the split. `PilotWorld` (sign-in alone, with stand-ins
  for the other surfaces' services), `SearchWorld`, `DownloadWorld`, `LandscapeWorld` and
  `EverySurfaceWorld`. Their fixtures are `auth_world`, `search_world`, `download_world`,
  `landscape_world`, `every_surface_world`, and `make_search_world`, `make_download_world`,
  `make_landscape_world` for the tests that build their own. The session-scoped `search_corpus`,
  `search_corpus_index`, `download_parser`, `download_sources`, `download_corpus` and
  `download_corpus_index` replace the import-time `CORPUS` and the `@cache` functions. The fakes,
  the corpus's documents and the download's sources are as they were.
- The 19 test files that used `world`: a `world` fixture naming their surface, and `make_world` in
  the four that use it. Five module docstrings say `conftest.search_corpus` for `conftest.CORPUS`.
- This report and the spec's Goal phase.

## Deviations from the spec

1. **The spec's premise holds only partly: most of the narrowing is hidden by `debate_api/app.py`.**
   The description says the split lets `affected_tests.py` narrow the API tests. The conftest now
   narrows: the selector reads each world as needing only its own surface's files, and the blocked
   reading proves it. But `create_app` imports `debate_api.container` inside the function, for
   uvicorn's `--factory` (`app.py:59`, `Dockerfile:46`). grimp counts that import, so every test that
   builds the app reaches the whole composition root. ac1's wording is met: 408 → 386 API files,
   fewer in 14 commits, more in none. Its intent ("a change selects only the tests it reaches") is
   met for module code and for modules the container does not import, but not for the integrations.
   Removing the edge is a change to `packages/debate_api/src`, its Dockerfile and a pinned test, all
   outside `constraints.packages`, so it was measured and not made. The PM question below has the
   options.

## Decisions and assumptions

1. **Each test file chooses its world with its own `world` fixture**, and no conftest fixture is
   called `world` or `make_world`. The selector finds a fixture's users by its name as a word in a
   test file's text, so a conftest `world` would still be "used" by all 19 files. Renaming the
   parameter in every test instead would have touched every test body, assertions included.
2. **`every_surface_world` for three files:** `test_auth_authorization_matrix.py` and
   `test_exposure.py` walk every route (a card, `/download` of card 27, the landscape pages), and the
   browser suite searches and downloads. The PM's four surfaces are four fixtures; this is their
   union, built by `EverySurfaceWorld(DownloadWorld, LandscapeWorld)`.
3. **The search world's corpus leaves out the download's seven cards (27 to 33)**, as the PM's "each
   surface fixture builds only what its surface needs" asks. Without them the search surface needs
   no parser and no Verbatim builder. The download world's corpus is today's `CORPUS`, in the same
   order, and the linked card is last in both, so `corpus[:-1]` means the same. No search test names a
   download card, and every search test passes unchanged.
4. **The search world's stand-in download service reports its own index's parser version.** The
   first run had one failure, `test_the_card_page_shows_the_label_tag_cite_line_counts_copy_card_and_every_occurrence`:
   the card page offers Download only when `CardDownloadService.is_on`, that is when the index's
   parser version is the service's. A search world is the pilot with an index this function's parser
   built and no source stored, so its service takes `index.manifest.parser_version`, and nothing can
   be downloaded through it. The sign-in world's service reports a placeholder, so its pages say
   download is off. Publishing the search index under the real parser's version would also have
   passed, and is mutant 2.
5. **What the sign-in world has in the other surfaces' places.** `NothingPublished` (the index's
   prefix of a bucket nothing was published to), a reader opener, a writer and a document-size
   function that raise `AssertionError`, and an empty landscape shelf. A test that uses a surface its
   world lacks fails loudly instead of quietly reading nothing. No sign-in test needed any of them.
6. **Shared pieces are session-scoped fixtures, as the PM asked.** The download world and
   `every_surface_world` share the parser, the sources and the download corpus's index through
   `download_parser`, `download_sources`, `download_corpus` and `download_corpus_index`. The search
   world has its own corpus and index (`search_corpus`, `search_corpus_index`). The per-key RSA key
   cache, `_PRIVATE_KEYS`, stays as it was: an empty dict at import, filled the first time a key signs.
   It holds no repository file, and threading it through `FakeManagedLogin` from a fixture would
   change every sign-in fake for no selection gain.
7. **`ISSUER` is written out**, as `issuer_for` builds it
   (`https://cognito-idp.{REGION}.amazonaws.com/{POOL_ID}`). A module-level call made every file
   beneath the conftest need the Cognito adapter.
8. **The landscape world adds no file over sign-in.** Its pieces are the conftest's own
   `InMemoryLandscapeObjects` and modules the app imports anyway. A change to the bundles under
   `fixtures/landscape/` still selects every test beneath the conftest, because the conftest builds
   that folder's path and the selector counts a named folder for all of them. Moving that path into
   a helper module would narrow it, but helper modules beside these tests are not importable under
   `--import-mode=importlib`.

## Commands run before the report

- **Affected set:** `uv run scripts/affected_tests.py --run` → `Affected set: 69 test files, pytest exited 0 after 110 s.` (`3127 passed in 108.32s`; 2 min 2 s wall-clock with uv's start)
- `.venv/bin/ruff format --check .` → `1604 files already formatted`. `.venv/bin/ruff check .` → `All checks passed!`
- `.venv/bin/pyright packages/debate_api` → `0 errors, 0 warnings, 0 informations`
- `.venv/bin/lint-imports` → `Contracts: 18 kept, 0 broken.` `scripts/check_thin_handlers.py` → `OK: 68 CLI command and API route handlers within 25 statements`
- `uv run scripts/validate_specs.py` → `OK: 494 files, 40 epics, 432 tasks, 22 releases`
- `.venv/bin/python scripts/check_command_blocks.py --base origin/dev` → OK, no comment in 578 shell code blocks in 198 Markdown files, this report included. `tests/docs` and `test_check_command_blocks.py` → `229 passed in 8.38s`

## Operator follow-ups

None. The conftest is shared test ground only for the tests beneath it. All of them ran: the default
selection's 1,041, the 23 slow browser tests, and the affected set above.

## Follow-up work

- **Move uvicorn's app factory out of `debate_api/app.py`** (E39, or E01's selection work). This is
  the PM question below.
- **`PilotServices` requires every surface's service.** Even the sign-in world builds
  `CardDownloadService` and `SearchIndexHolder`, so a change to what they import selects every
  API test that builds the app (most rows of the table). Optional services per surface would lower
  that floor, but they change the app's composition. Worth it only if the API tests become a slow
  part of CI; today they take about 10 s.

### PM question (paste-ready)

> **v1-e39-t20: `debate_api/app.py` imports the composition root, which hides most of the conftest
> split's narrowing.** `create_app(services=None)` imports `debate_api.container` inside the function
> for uvicorn's `--factory` (`Dockerfile` `ENTRYPOINT … "debate_api.app:create_app", "--factory"`).
> The selector counts that import, so every API test that builds the app reaches the parser, the
> writer, the index reader, Cognito, CloudWatch and S3. Over t32's 41 commits the split took API files
> from 408 to 386; with that edge gone as well it would be 372, all of the extra drop in the
> parser-only merge `387c961` (24 → 8). Options:
>
> 1. **A small follow-up task:** point uvicorn at a factory in the composition root (for example
>    `debate_api.container:create_app_from_environment`), and have `create_app` require its services.
>    It touches `app.py`, the `Dockerfile` entrypoint, `packages/debate_api/README.md` and the pinned
>    entrypoint in `tests/scripts/test_tub_deploy.py` (line 554), and needs an image build and deploy
>    to dev.
> 2. **Teach `affected_tests.py` that an import inside a function a test never takes** does not
>    count. That is general and risky: the selector's rule is to fail toward more tests.
> 3. **Leave it.** The measured gain is one merge in 41, and the API tests take about 10 s.
>
> **Recommendation: 3 now, 1 when E39 next touches the image.** The gain is real but small, and
> option 1 costs a deploy. Option 2 trades a safety rule for little.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
