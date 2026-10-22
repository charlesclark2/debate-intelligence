# Session report: v1-e39-t06-search-pages

| | |
|---|---|
| Task | `v1-e39-t06-search-pages` — Search pages: search, results, the card page and Copy card, on a Chromebook |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t06-search-pages.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t06-search-pages.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t06-search-pages` |
| Session status | IN PROGRESS <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The pilot now has its search pages, in `debate_api` over `v1-e39-t03`'s search service. There is a
search page with one box and filters for event, caselist, side and first-seen date. Results show the
tag, short cite, snippet, counts and provenance line, 20 to a page. The card page carries the ADR-0006
label, Copy card, the formatted card and every surviving occurrence's line, and a card over 3,000
words leads with its read-aloud text and keeps the rest behind a native `<details>`.

Copy card writes `text/html` and `text/plain` inside the click, from a fixed style table in
`debate_api`. Under the PM's ruling of 2026-10-20 this task also built the function's index holder:
a new port and S3 adapter, and a use case in `debate_core.application` that fetches, checks, rechecks
and swaps the published index.

ac1, ac2, ac3 and ac5 pass: 107 page and copy tests in the default selection, 12 Chromium tests
marked `slow`, and 33 holder and adapter tests, each set shown red first, with 22 of 22 mutants killed.

**The Goal stays InProgress.** ac4, the operator's Chromebook check on dev, needs the docx-6 store,
which the local stores do not have yet (the re-parse runs on 2026-10-21). Its operator block is
below. The PM should look first at **PM question 1**: validate-dev's slow tier will run the new
Chromium tests on a runner with no Chromium.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `pages` — Search pages | Done | Its criterion passes (below). The index holder the pages need was added to the node's work under the PM's ruling, written into the spec |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `pages`: `uv run pytest packages/debate_api/tests -k "pages or copy"` | PASS | → `107 passed in 2.18s`. Under the default markers this selects the HTTP-level page and copy tests; the Chromium half is `slow` and is the next rows' second command |
| ac1 — Playwright against the app served locally with a synthetic index: search, filter, page, open a card and copy it at 1366x768 and 390x844; axe no serious or critical | PASS | `uv run pytest -m slow packages/debate_api/tests/browser -n 0 -v` → `12 passed in 7.55s`. `test_search_filter_page_open_and_copy_a_card_by_keyboard` runs at **1366x768, 1280x800 and 390x844** (phone: mobile, touch, scale 3), all by keyboard. It tabs to the box and searches, gets 20 results, tabs to *Next results* and gets 5, then filters to Public Forum by typing into the select and gets the one PF card. It searches again, opens a card, and presses *Copy card*: the clipboard holds `text/html` and `text/plain`, equal to the copy route's. On every page there is no CSP violation, no horizontal scroll, and axe-core 4.12.1 finds no serious or critical violation |
| ac2 — copied HTML pasted into a fixture editable region keeps every formatting span, compared as coverage, with the provenance line below the cite | PASS | Chromium, `test_a_pasted_copy_keeps_every_formatting_span_with_the_provenance_line_below_the_cite`: a keyboard paste into an editable region that reads the clipboard's `text/html` in its paste event, as Google Docs does. Read back, the paragraphs are the tag, the cite, then `[Disclosed: hsld26 2026-09-15 — Maple Grove QX, Neg vs. Invented Invitational Round 4]`, then the card. The card's span coverage gives the stored spans' `formatting_sha256` exactly: ten emphasis spans, two highlight colours (one across the line break) and three sizes. `test_the_browsers_own_paste_keeps_how_every_character_of_the_copy_looks`: Chrome's own paste looks the same, character by character, by computed style (Decision 6). In Python, `test_copy_card.py` → the same `formatting_sha256` equality, a negative control that differs, and the table pinned by hand |
| ac3 — no page requests another origin or carries inline script, by a test over every response and its CSP; the page-weight budget holds | PASS | Chromium, `test_no_page_requests_another_origin_or_runs_inline_script_under_the_edges_csp`. Every response carries the CSP `distribution.tf` writes, read from the file. Every request is to the pilot's origin, over 8 pages and a copy, with no other origin recorded. There are no inline scripts and no CSP violations, and the only script is `app.js`. `test_an_inline_script_would_be_refused_by_the_edges_csp` shows that CSP refusing one. HTTP level (`test_search_pages.py`, 12 pages including account and coach): no `style`, `on*=` or `javascript:` in any tag; every `src`, `href`, `action` and `data-tub-copy` is a path or `#main`; each page under 150 KB with `app.js` and `app.css` counted and the card body left out |
| ac4 — on dev, in desktop Chrome with the window at 1366x768 (DevTools device toolbar): search, open a card, Copy card into Google Docs, formatting kept; yes or no each (amended, PM ruling 2026-10-21) | NOT RUN | It needs the docx-6 store, which this Mac does not have yet: `ls ~/.debate-research/dev/parsed/*` lists only `2026.10.18-docx-5` (read 2026-10-20). Operator follow-up 1 is the whole sequence, in order |
| ac5 — a card over 3,000 words shows its read-aloud text first and the rest on request; its result's snippet stays within the page-weight budget | PASS | HTTP: the 3,200-word card's body is *Read aloud* and `Zephyr read aloud stretch`, then `<details class="card-whole">` holding the whole card; a 3,000-word-or-shorter card is shown whole; the results page for a word only that card holds has a snippet of 24 words or fewer, under 150 KB. Chromium, at all three sizes: the read-aloud text is visible and the whole card hidden; Tab to *Show the whole card* and Enter opens it |

### Shown failing first, and the mutants

The red runs:

* Holder, against a skeleton that refuses nothing (every `SearchIndexRefused` a no-op): `17 failed,
  14 passed`. Every refusal test failed: digests, format versions, the manifest, the gzip stream,
  keys outside the index, a refused pointer refetched, a refused index replacing the current one.
* Holder, against a skeleton that never rechecks: `6 failed, 25 passed`. These were the conditional
  GET, the frozen environment, the swap and delete, the deferred delete, the failed recheck and the
  clock that runs backwards.
* Pages: the first run of `test_search_pages.py` against the new pages had 7 failures. They were
  expectations that were mine to fix (Jinja's `&#39;` against `html.escape`'s `&#x27;`, a regex that
  matched escaped text, a hex id with no letters in it) plus one real gap: no `.card-shrunk` rule in
  the stylesheet.
* Chromium: three real findings on the way.
  * Granting `clipboard-read` alone makes Chrome deny writes.
  * Chrome's own paste drops redundant declarations (Decision 6).
  * Chrome reports each inline style of the copied HTML against the page's CSP while it sanitises
    the write (Decision 7).

Mutants, 22, each run against its covering tests with `-x`, then restored from the commit:

| Mutant | Result | Killed by |
|---|---|---|
| Style: underline written as italic | KILLED | `test_the_emphasis_table_is_the_verbatim_templates_styles` |
| Style: `Emphasis` underlined only | KILLED | the same |
| Style: yellow another yellow | KILLED | `test_the_highlight_table_is_words_rgb_colours…` |
| Style: half-points lose the half | KILLED | `test_a_size_in_half_points_is_written_in_points[21-…]` |
| Style: sizes outermost | KILLED | `test_a_runs_spans_nest_its_emphases_then_its_colours_then_its_sizes_innermost` |
| Style: an unknown colour gets yellow | KILLED | `test_a_colour_outside_the_table_gets_no_colour…` |
| Style: the provenance line after the card | KILLED | `test_the_copy_read_back_carries_every_formatting_span…` |
| Style: the short cite not in `Style13ptBold` | KILLED | `test_the_copy_is_the_tag_the_cite_the_provenance_line…` |
| Escape: quotes left as typed | KILLED | `test_hostile_card_text_is_escaped_in_the_copy…` |
| Escape: nothing escaped in the copy | KILLED | the same |
| Escape: the card page's cite `| safe` | KILLED | `test_hostile_card_text_is_escaped_on_the_results_and_card_pages` |
| Escape: a result's tag `| safe` | KILLED | the same |
| Access: the copy route missing from `ROUTE_ACCESS` | KILLED | `test_every_route_says_what_access_it_needs` |
| Access: `/cards/` treated as public | KILLED | `test_without_a_valid_session_only_the_four_session_free_routes_answer[…]` |
| Holder: manifest digest not checked | KILLED | `test_a_manifest_whose_digest_is_not_the_pointers…` |
| Holder: SQLite digest not checked | KILLED | `test_an_object_that_inflates_to_another_file…` |
| Holder: pointer format version not checked | KILLED | `test_a_pointer_of_an_unknown_format_version…` |
| Holder: the file left writable | KILLED | `test_the_checked_file_is_read_only…` |
| Holder: the old file kept after a swap | KILLED | `test_a_new_pointer_is_fetched_to_a_new_path…` |
| Holder: rechecks every ten minutes | KILLED on the second run | It survived the first (the tests advanced by the constant itself); `test_the_recheck_comes_five_minutes_on_as_adr_0019_sets_it`, minutes written out, now kills it |
| Copy: the fetch awaited before the write | KILLED | `test_copy_card_writes_the_clipboard_inside_the_click_before_the_fetch_answers` (Chromium) |
| Long cards: `<details open>` | KILLED | `test_a_card_over_three_thousand_words_leads_with_its_read_aloud_text…` |

### What was run before this report

* `uv run scripts/affected_tests.py --run` → `The whole selection is affected: pyproject.toml is shared
  test ground. CI runs it on the pull request; a session does not.` So the whole selection is CI's.
  Within the two minutes, the changed modules' test directories and the always-run list ran:
  * `.venv/bin/python -m pytest packages/debate_api/tests …/test_search_index_holder.py
    …/test_evidence_search.py …/test_search_index_publish.py packages/debate_core/tests/integrations/s3
    tests/architecture tests/specs packages/debate_cli/tests/test_app.py
    packages/debate_cli/tests/test_help_rendering.py` → `981 passed in 19.19s`;
  * `.venv/bin/python -m pytest packages/debate_core/tests/application
    packages/debate_core/tests/integrations/local tests/docs tests/scripts/test_check_command_blocks.py
    tests/scripts/test_docs_index.py` → `2962 passed in 63.60s`.
* `uv run pytest -m slow packages/debate_api/tests/browser -n 0` → `12 passed in 7.55s`.
* `uv run ruff format --check .` → `1002 files already formatted`.
* `uv run ruff check .` → `All checks passed!`
* `uv run pyright packages/debate_api packages/debate_core` → `0 errors, 0 warnings, 0 informations`.
* `uv run lint-imports` → `Contracts: 12 kept, 0 broken.`
* `uv run python scripts/check_thin_handlers.py` → `OK: 46 CLI command and API route handlers within
  25 statements`.
* `uv run scripts/validate_specs.py` → `OK: 396 files, 39 epics, 336 tasks, 21 releases`.
* `uv run python scripts/check_command_blocks.py` → `OK: no # comments in 332 shell code blocks`.
* `uv export --package debate-api --frozen --no-dev --no-emit-workspace` (what `tub_deploy.sh` stages)
  names no `playwright`, `axe-playwright-python`, `greenlet` or `pyee`: the image gains nothing.

## Files changed

* **`packages/debate_api/src/debate_api/`**: the pages and Copy card.
  * `search_pages.py` (new): the handlers.
  * `copy_card.py` (new): the style table and the copy.
  * `routes.py`: four routes and `ROUTE_ACCESS`. `/static/{digest}/{name}` replaces `/static/{digest}/app.js`.
  * `pages.py`, `app.py`, `state.py`: the stylesheet asset, and the holder in `PilotServices`.
  * `configuration.py`: `TUB_EVIDENCE_BUCKET`, which Terraform already sets.
  * `container.py`: builds the holder over `S3SearchIndexSource` into `/tmp/tub-index`.
  * `templates/`: `base.html` (stylesheet, skip link, landmarks, a *Search* link); `search.html` and
    `card.html` new; `home.html` removed, since `/` is the search page.
  * `static/app.js`: Copy card. `static/app.css` (new): the one stylesheet.
  * `README.md`.
* **`packages/debate_core/src/debate_core/application/`**: the index holder.
  `ports/search_index_source.py` (new) is the port; `search_index_holder.py` (new) is the use case.
* **`packages/debate_core/src/debate_core/integrations/s3/`**: `search_index_source.py` (new), the
  adapter, and its export from the package.
* **`packages/debate_core/src/debate_core/testing/search_index.py`** (new): a published index in
  memory, and a source that serves it as the bucket does, for both packages' tests.
* **Tests.**
  * `packages/debate_api/tests/`: `conftest.py` adds the synthetic corpus, a real holder in
    `PilotWorld`, and the Copy card read-back. `test_search_pages.py` and `test_copy_card.py` are new,
    and so is `browser/test_search_pages_in_chromium.py`.
  * The t05 tests the new pages change: the matrix rows for the three new routes and the renamed
    static route; the GET search form; `app.js`'s second `fetch`; the template list;
    `<main id="main">`; `TUB_EVIDENCE_BUCKET`.
  * `packages/debate_core/tests/`: `application/test_search_index_holder.py` and
    `integrations/s3/test_s3_search_index_source.py`, both new.
* **`pyproject.toml`, `uv.lock`**: `playwright>=1.63` (locked at 1.63.0, whose Chromium is v1243) and
  `axe-playwright-python>=0.1.8` (axe-core 4.12.1), dev only, with a comment.
* **The spec**: the PM's ruling and the packages it needs.

## Deviations from the spec

1. **The packages grew, under the PM's ruling of 2026-10-20.** It is written into the spec's
   `constraints` as a comment. The index holder put `debate_core.application`,
   `debate_core.integrations.s3`, `debate_core.testing` and `packages/debate_core/tests` in, and the
   new dev dependencies put `pyproject.toml` and `uv.lock` in. `debate_core.testing` is mine to
   propose rather than the ruling's: the shared in-memory published index has to live somewhere both
   packages' tests can import, and test directories cannot share modules under importlib mode.
2. **The node's criterion does not run the Playwright tests.** `-k "pages or copy"` runs under the
   default `-m "not slow and not live"`, and the browser tests are `slow` (working agreement 1).
   ac1, ac2, ac3 and ac5 are evidenced by the `-m slow` run as well.
3. **No smoke check was added.** The plan has no smoke node, and `v1-e39-t10` is the epic's dev smoke
   task; `tests/smoke` is not in this task's packages.

## Decisions and assumptions

1. **Routes.**
   * `/` and `/search` with no words are the empty search page; `/search?q=` gives results.
   * `/cards/<caselist>/<cluster id>` is the card page and `/cards/<caselist>/<cluster id>/copy` the
     copy, as JSON.
   * All four are `GET`, so no POST needed the CSRF gate.
   * A malformed address is a 404 without touching the index. A filter value no form writes is a
     400 with a message, and so is a cursor from another search.
2. **The empty search page never waits.** Its caselist list comes from the index already loaded
   (`loaded_caselists()`, which never fetches). On a cold environment, before the first search, it
   offers *Any caselist* only, and the results page has the full list.
3. **Copy card: a ClipboardItem of Promises, written inside the click.** That is the way chosen, and
   `test_copy_card_writes_the_clipboard_inside_the_click_before_the_fetch_answers` proves it. An init
   script records, in order: `click`, then `write called in the click with activation
   text/html,text/plain`, then `fetch answered`, then `write done`. The mutant that awaits the fetch
   first fails it.
   * Measured in Chromium's own headless mode: Chrome allowed a write even 6 s after the click, so
     Chrome alone would not show the difference. Safari on a phone would, and the order is what the
     test holds.
   * The fetch, rather than the copy embedded in the page, keeps a long card's copy out of the page
     and gives `v1-e39-t07` one request per copy to audit.
   * The tests grant no clipboard permission while copying: granting `clipboard-read` alone makes
     Chrome deny writes. Read permission is granted only afterwards, to read the clipboard back.
4. **The style table** follows the E33 writer's `base.docx`:
   * `StyleUnderline` is underlined; `Emphasis` is bold and underlined; `Style13ptBold` is 13-point
     bold; `UndertagChar` is `#385623`; `AnalyticChar` is bold `#1F3864`.
   * `SHRUNK` is `font-size:smaller` and `HEADING` is bold `font-size:larger`. Both are overridden
     by the measured size, which is written innermost.
   * Highlights are OOXML's RGB colours, background only. Word does not change the text's colour
     under a highlight, so neither does the copy, though the card page's CSS puts white text on the
     dark highlights for contrast. An unknown colour gets no colour (PM).
   * No two entries are the same declarations (tested), so the read-back is exact.
   * No `mso-highlight`: Word takes the background as shading, and the colour names Word expects
     there could not be checked here.
5. **The CSP the tests enforce is the deployed one,** read from `distribution.tf`'s `join("; ", [...])`.
   The app sends none of its own: CloudFront's policy has `override = true`, and a second copy in
   Python could drift. Because `default-src 'self'` refuses inline styles too, every look is a
   class in a first-party, content-hashed `app.css`.
6. **Chrome's own paste does not keep emphasis names, and Docs does not use it.** A contenteditable's
   default paste removes a declaration a parent already makes. `Emphasis` inside an underline loses
   its underline and reads back as bold; `Bold` inside `Analytic` is removed. The look is the same.
   Google Docs and Word read the clipboard's HTML themselves, so ac2's region does that and reads
   back exactly. The browser's own paste is checked for what it can keep: how each character looks.
7. **Chrome reports the copy's inline styles against the page's CSP.** When `clipboard.write` takes
   `text/html`, Chrome parses it in the page and reports each `style` attribute (41 for the featured
   card) as `style-src-attr`. It still writes all 41 to the clipboard unchanged, and the test reads
   them back. With no `report-uri` these are console messages only. The journey asserts exactly those
   reports after the copy, one per attribute, and none from the page.
8. **The index holder:**
   * The freshness clock is the app's wall clock, not the monotonic one: an environment Lambda froze
     must count the frozen time.
   * A refused pointer is remembered by its entity tag and not refetched until it changes. A failed
     recheck leaves the current index serving and waits an interval. With no index loaded, every
     request tries again.
   * The checked file is renamed into place read-only (`0444`) under a new name each time. An index
     swapped out under a request is deleted when that request ends.
   * Files a previous process left in `/tmp/tub-index` are deleted when the holder starts, since
     `/tmp` outlives a process in a Lambda environment.
   * The download stops when the inflated bytes pass the manifest's size, and refuses trailing data.
9. **Wording.**
   * A missing team count reads `In 2 files. The number of teams is not known until the next weekly
     update.`, with no number.
   * A camp card's count names no team.
   * Both "caselist cards only" notes sit beside their filters always, and are marked applied when
     the search used that filter.
   * Long means more than 3,000 whitespace-separated words. The read-aloud section shows the
     stored read-aloud text, so the rule stays in `debate_core`.
10. **Synthetic only.** Every tag, cite, word, school, team code and name in the fixtures is
    invented: Maple Grove, Riverbend, `QX`, `ZT`, Cascade Institute, `debater.one`, and the operator
    account below, `chromebook.check`.

## Operator follow-ups

**1. ac4: the check on dev in desktop Chrome at 1366x768, in order.** There is no Chromebook until
Saturday, so ac4 runs in Chrome on the operator's Mac (PM ruling 2026-10-21); the Chromebook check
is `v1-e39-t10`'s. It needs the docx-6 store, so steps 1 and 2 both check it first. About 30 minutes
in all: the build about 4, the publish about 2, the deploy about 3, Chrome about 10. Every block runs in one terminal, so the variables carry on. Never paste back a
password or a code. Paste back the outputs and the yes or no for each question in step 7.

Step 1, v1-e39-t02's operator follow-up 2, the dev listing grant, skipped if it is already applied.
Where: the dev-preview worktree. About 3 minutes. If you use it for the site preview, run
`pnpm install` after the pull as usual. First, the store: if this does not list
`2026.10.20-docx-6` four times, stop, and run nothing below until the re-parse has.
```bash
ls ~/.debate-research/dev/parsed/hsld26 ~/.debate-research/dev/parsed/hspf26 ~/.debate-research/dev/parsed/hspolicy26 ~/.debate-research/dev/parsed/openev
```
Then the grant:
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/dev-preview
git pull --ff-only
aws sso login --sso-session debate
export AWS_PROFILE=debate-admin
grep -c evidence_search infrastructure/envs/dev/owner.auto.tfvars
terraform -chdir=infrastructure/envs/dev init
terraform -chdir=infrastructure/envs/dev plan -out=/tmp/search-listing-dev.tfplan
```
Success looks like: `2`, then either `No changes.` (it is applied; skip the apply) or exactly
`Plan: 0 to add, 1 to change, 0 to destroy.`, the one change being
`module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_operator[0]` gaining
`reports/tub/search/` and `reports/tub/search/*`. On anything else, stop and paste the plan.
```bash
terraform -chdir=infrastructure/envs/dev apply /tmp/search-listing-dev.tfplan
```
Success looks like: `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` Then, still in
dev-preview, the user pool for step 6:
```bash
export TUB_USER_POOL_ID="$(terraform -chdir=infrastructure/envs/dev output -raw evidence_search_user_pool_id)"
echo "$TUB_USER_POOL_ID"
unset AWS_PROFILE
```
Success looks like: `us-east-1_` and the pool's id.

Step 2, the store's version. Where: this task worktree. Seconds, after `uv sync`.
```bash
cd ~/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t06-search-pages
uv sync --all-packages
ls ~/.debate-research/dev/parsed/hsld26 ~/.debate-research/dev/parsed/hspf26 ~/.debate-research/dev/parsed/hspolicy26 ~/.debate-research/dev/parsed/openev
```
Success looks like: `2026.10.20-docx-6` under each of the four. If any shows only
`2026.10.18-docx-5`, the re-parse has not run: stop here and run steps 3 to 9 after it. This branch's
parser is docx-6, so the build would refuse that store with `SEARCH_INDEX_STORE_NOT_READY`.

Step 3, the build. Where: this task worktree. About 4 minutes.
```bash
DEBATE_ENV=dev .venv/bin/debate-research --json tub index build --caselist hsld26 --caselist hspf26 --caselist hspolicy26 --caselist openev > /tmp/tub-index-build-t06.json
INDEX_ID=$(python3 -c "import json; print(json.load(open('/tmp/tub-index-build-t06.json'))['data']['manifest']['index_id'])")
echo "$INDEX_ID"
python3 -c "import json; m = json.load(open('/tmp/tub-index-build-t06.json'))['data']['manifest']; print(m['parser_version'], m['counts']['documents'], m['sqlite_file']['bytes'], m['gzip_object']['bytes'])"
```
Success looks like: a 16-character index id, then `2026.10.20-docx-6`, a document count near
46,658, and the two sizes.

Step 4, the publish to dev. Where: this task worktree. About 2 minutes for some 280 MB.
```bash
DEBATE_ENV=dev .venv/bin/debate-research tub index publish --env dev --index "$HOME/.debate-research/dev/tub-index/${INDEX_ID}"
```
Success looks like: `Search index <INDEX_ID> published`, three keys, and
`current.json names <INDEX_ID>; object sha256 …`.

Step 5, deploy this branch to dev. Where: this task worktree, with Docker Desktop running. About 3
minutes.
```bash
git rev-parse --short HEAD
scripts/tub_deploy.sh dev
```
Success looks like: `{"status":"ok"}`, then `Deployed <sha> to dev: https://tub.dev.wfbdebate.com/`,
the sha being the one printed first.

Step 6, a synthetic student account. Where: this task worktree, the same terminal. About 1 minute.
```bash
STUDENT='chromebook.check'
uv run debate-research tub users add "$STUDENT" --role student --env dev
```
Success looks like: `Created chromebook.check (student).` and a temporary password. Write the
password down for the sign-in in step 7 and do not paste it back; paste back only the first line.

Step 7, in desktop Chrome on your Mac. About 10 minutes.

1. Open `https://tub.dev.wfbdebate.com/` in a new Chrome window. Open DevTools (Cmd+Option+I), turn
   on the device toolbar (Cmd+Shift+M), choose *Dimensions: Responsive*, and set it to `1366` by
   `768`. Leave the device type desktop, with no touch. Then sign in as `chromebook.check` with the
   temporary password. Choose a new password and set up an authenticator app on your phone.
2. Search for a word such as `economy` and press Enter. The first search fetches the index, so
   expect a few seconds. **Yes or no: results appear**, each with a tag, short cite, snippet, counts
   and a provenance line. Roughly how long did the first search take?
3. Open a card. **Yes or no: the card opens**, labelled "Disclosed evidence, not platform-verified",
   its text underlined and highlighted as in the file.
4. Click on the page once (so it, not DevTools, has the focus), press *Copy card*, then paste with
   Cmd+V into a new Google Doc in another tab. **Yes or no: it pasted** as the
   tag, the cite, the provenance line below the cite, then the card.
5. **Yes or no: the formatting was kept**: underlining, the highlight colours, bold, and the small
   shrunk text.
6. Delete the Google Doc afterwards: it holds card text.

Step 8, remove the account. Where: this task worktree, the same terminal. Seconds.
```bash
uv run debate-research tub users remove "$STUDENT" --env dev
```
Success looks like: `Removed chromebook.check. Any open session ends within five minutes.`

## Follow-up work

1. **validate-dev's slow tier needs Chromium** (PM question 1). Without it, the slow tier fails on
   the first dev push after this merges.
2. **The audit records for a card view and a copy** are `v1-e39-t07`'s. `/cards/...` and
   `/cards/.../copy` are the two requests it audits, and the holder's `_refresh` is where its
   suppression re-read goes.
3. **The holder's `INFO` lines do not reach the function's log.** uvicorn configures its own
   loggers, not the root, so `search index <id> loaded` is not written in Lambda; warnings are.
   Seeing cold-start index loads in `debate-dev-tub-app` would need a logging configuration in the
   app (`v1-e39-t10`'s measurements may want it).
4. **The runbook says nothing about the index the function fetches.** `docs/runbooks/evidence-search.md`
   could point at ADR-0019 (c) 3 and 5 and at what a refusal looks like. It is not in this task's
   packages; `v1-e39-t07` or `v1-e39-t10`.
5. **No "previous page" link.** A cursor runs forward only (`v1-e39-t03`), so results offer *First
   page* and *Next results*, and the browser's Back for the rest.
6. **A real Chromebook check is `v1-e39-t10`'s** (PM ruling 2026-10-21): sign-in, search, a card,
   and Copy card into Google Docs, on a Chromebook. ac4 here ran in desktop Chrome at 1366x768;
   the PM adds the Chromebook check to that task's spec.
7. **A worktree cut before a newer migration refuses the shared data directory's database.** Every
   checkout uses `~/.debate-research/<env>/debate.sqlite3`. A command run from a newer one (here the
   main checkout on `dev`) upgrades it, and every older worktree then stops with `MigrationError`.
   **The hint does not say to sync.** `MigrationError` has no mapping in the CLI, so it is reported
   as `INTERNAL_ERROR`. The hint (`debate_cli/output.py`) says "This is a bug in debate-research. Re-run
   with --verbose…", and the error's own sentence ("written by a newer build of debate_core;
   upgrade rather than downgrade") is not printed, since it can quote a path. Proposed for a later
   task: map the newer-schema case to its own code, with the one-line hint *"This data directory's
   database was upgraded by a newer build: update this checkout (`scripts/task sync <task>`, or
   `git pull` and `uv sync --all-packages`) and run the command again."*

## PM questions

```text
PM questions from v1-e39-t06-search-pages (session of 2026-10-20)

1. The Chromium tests and validate-dev's slow tier.
   The new browser suite (packages/debate_api/tests/browser, 12 tests, 7.5 s) is marked slow, per
   working agreement 1, so the PR's ci never runs it. validate-dev's slow job runs
   pytest -m "slow and not live and not eval" after uv sync, on ubuntu-24.04, and installs no
   browser. So after this merges, that tier fails on Playwright's missing executable, and a skip
   would fail it too ("a skipped test fails its tier").
   Options:
   (a) Add one step to .github/workflows/validate-dev.yml's slow job, after "Install the locked
       workspace": uv run --locked playwright install --with-deps chromium (about a minute on the
       runner). This task does it, with .github/workflows/validate-dev.yml added to its packages.
   (b) The same step, done by v1-e39-t10 (the epic's dev smoke task), and this task merges after it.
   (c) Run the browser suite in ci instead, unmarked, with the same install step in ci.yml. That
       costs every PR about a minute, against agreement 1.
   Recommendation: (a). The task that adds the suite should leave validate-dev green, and the change
   is one step. (b) leaves a red tier, or a merge order to manage.

2. ac4 and the docx-6 store.
   ac4's operator block is in the report, in your order. Its second step stops it if the store is
   not yet docx-6. On 2026-10-20 the local stores are 2026.10.18-docx-5 only. The phase stays
   InProgress until the operator's results are in.
   Recommendation: the operator runs it after the 2026-10-21 re-parse, and I record the results and
   set Succeeded. No ruling needed unless you want ac4 run on a docx-5 index first. That would need
   a checkout at docx-5's parser and would test a store this release will not serve.
```

## After the PM review of 2026-10-21

**Condition 1, PM question 1 (a): done.**

* `.github/workflows/validate-dev.yml`'s `slow` job gains one step, after *Install the locked
  workspace*: *Install Playwright's Chromium for the browser tests*, running
  `uv run --locked playwright install --with-deps chromium`.
  * A comment above the step says why it is there.
  * The workflow's header comment, at the `slow` tier, says the tier includes the browser suite and
    why the job installs Chromium first.
* The workflow is in the spec's packages with the comment `PM ruling 2026-10-21 (v1-e39-t06 Q1)`.
* **The slow job's marker selects the browser suite.** `scripts/validate_dev.py`'s `SLOW` tier
  passes `-m "slow and not live and not eval"` and no paths, so pytest reads `pyproject.toml`'s
  `testpaths`, which include `packages/debate_api/tests`. Collected that way from the repository
  root, `.venv/bin/python -m pytest -m "slow and not live and not eval" --collect-only -q -n 0`
  gives `24/11004 tests collected (10980 deselected)`, and 12 of the 24 are
  `packages/debate_api/tests/browser/test_search_pages_in_chromium.py`.
* The installed Chromium is the one the locked Playwright (1.63.0) names, v1243, the build the tests
  ran on here.
* Checks:
  * the workflow parses, and the slow job's steps are, in order: *Install Python*, *Install the
    locked workspace*, *Install Playwright's Chromium…*, *Run pytest…*;
  * `tests/scripts/test_workflow_runners.py`, `tests/scripts/test_validate_dev.py` and
    `tests/specs` → `165 passed`;
  * `uv run scripts/validate_specs.py` → `OK`.
* What this cannot show here: the step runs on the runner only after the merge, in the first
  validate-dev run.

**Condition 2, ac4: waiting for the re-parse, and now in desktop Chrome.** The PM's ruling of
2026-10-21 moves ac4 to Chrome on the operator's Mac at 1366x768 (no Chromebook until Saturday). The
spec's ac4 is amended, with the ruling as a comment; step 7 of Operator follow-up 1 is rewritten for
Chrome on a Mac (the device toolbar at 1366x768, Cmd+V), with the same four questions and the
first-search time; step 1 now checks the docx-6 store before anything else. Follow-up work 6 records
the Chromebook check as `v1-e39-t10`'s. On 2026-10-21, before the session went on,
`ls ~/.debate-research/dev/parsed/*` still listed only `2026.10.18-docx-5` for all four stores. The
operator runs Operator follow-up 1 once the re-parse has written `2026.10.20-docx-6`, and the
results go here.

**ac4's first attempt, 2026-10-21: stopped at step 3, and a second review.**

* **What passed.** Step 1: the store listed `2026.10.20-docx-6` four times; `grep -c` and
  `terraform init` ran; the plan said `No changes.` (the listing grant was already applied), so
  nothing was applied. Step 2: all four stores are `2026.10.20-docx-6`. The re-parse, run from the
  main checkout on `dev`, finished at 22:45 CDT with `status: ok` for each store: hsld26 86,675
  occurrence rows, hspf26 62,292, hspolicy26 116,337, openev 8,081.
* **What stopped.** Step 3's `tub index build` refused with `INTERNAL_ERROR`
  (`exception_type: MigrationError`) before reading any store. Nothing was built, published or
  written.
* **Why.** The re-parse ran on `dev`, which carries migration
  `0003_search_provider_statuses.sql`, `v1-e08-t01`'s (#383). That run applied it to
  `~/.debate-research/dev/debate.sqlite3`. This branch, cut before it, shipped migrations 1 and 2
  only, so it refused a database at schema version 3 rather than read a newer schema. The relay
  message first named the migration `v1-e07-t01`'s; the PM corrected it.
* **The ruling (PM, 2026-10-21): (a), sync.**
  * `scripts/task sync v1-e39-t06-search-pages` rebased the branch's 14 commits onto `origin/dev`
    with no conflict; git merged `pyproject.toml` and `uv.lock` itself, and pushed nothing, since
    the branch is not on the remote.
  * Re-locking: `uv lock --check` passed on the merged lock, and `uv lock` changed nothing (the tree
    stayed clean; playwright is still 1.63.0). `uv sync --all-packages` ran.
  * The branch now ships migrations 1 to 3.
* **The checks again, on the synced branch.**
  * `uv run scripts/affected_tests.py --run` → the whole selection is affected (`pyproject.toml`),
    so that is CI's.
  * Within two minutes each:
    * the debate_api tests, the holder, search, publish and S3 tests, `tests/architecture`,
      `tests/specs`, the CLI's wiring tests and the workflow tests → `1065 passed in 21.76s`;
    * `packages/debate_core/tests/application` → `2729 passed in 90.17s`;
    * `packages/debate_core/tests/integrations/local`, `tests/docs` and the docs-check tests →
      `382 passed in 4.79s`.
  * `uv run pytest -m slow packages/debate_api/tests/browser -n 0` → `12 passed`.
  * ruff format (`1046 files already formatted`), ruff check, pyright on both packages (0 errors),
    `lint-imports` (`13 kept, 0 broken`), the thin-handler check and `validate_specs.py` (`OK`).
  * The slow tier's collection is still `24/11564`, 12 of them the browser suite.
  * Two attempts at the application directory were cut off by my two-minute alarm, with no failure.
    The machine's load average was near 10, with another `python3` from the main checkout's venv
    at about 90% CPU. A serial run showed the tests still passing when it was stopped, and the third
    attempt finished as above.
* ac4 restarts from step 3, unchanged: step 5's `git rev-parse` now prints the rebased head.

**ac4's second attempt, 2026-10-21, in desktop Chrome at 1366x768 on dev: four yes, and a third review.**

* **Steps 3 to 6** ran: the build, the publish, the deploy of the synced branch and the account
  `chromebook.check`. Their outputs are still to be recorded here; the operator is pasting them.
* **Step 7**, the operator's answers:

  | Question | Answer |
  |---|---|
  | Results appear, each with a tag, short cite, snippet, counts and a provenance line | **Yes.** Every result had a tag, a snippet, counts and a provenance line; not every one had a short cite (below) |
  | The first search's time | About 5 to 6 seconds |
  | A card opens, labelled "Disclosed evidence, not platform-verified", underlined and highlighted | **Yes**, in about 4 to 5 seconds |
  | Copy card pasted into Google Docs as the tag, the cite, the provenance line below the cite, then the card | **Yes** |
  | The formatting was kept | **Yes** |

* **Step 8**: `Removed chromebook.check. Any open session ends within five minutes.`
* **What came out differently, raised with the PM before the Goal is set:**
  1. **The operator would rather the copy left the provenance line out.** The spec's description,
     ADR-0019's gate item 6 ("copy and download carry the provenance line") and the data-use
     policy's Attribution rule 2 all require it. That is the PM's ruling to make, not this session's.
  2. **The Copy card button's place reads oddly** (the operator's screenshot): between the counts
     and the card's text, with its help line and status under it.
  3. **Some results have no short cite.** The index stores none when the build could not read one
     from the cite (`docs/data/search-index.md`), and the results page then leaves the line out.
     That is the data, not a fault in the page; a fallback (the cite's first words) would be new
     scope.
  4. **Opening a card took 4 to 5 seconds** after a 5 to 6 second first search. That is consistent
     with a second cold execution environment fetching the index again: CloudFront does not keep a
     viewer on one environment, and reserved concurrency allows ten. `v1-e39-t10` measures the
     function's timings; its logging follow-up (3) would show each load.
  5. **DevTools counted about 160 console errors** on the card page after the copy. These are most
     likely Decision 7's reports: Chrome reports each inline style of the copied HTML against the
     page's CSP while it sanitises the write, and this card has many spans. The paste was whole. Not
     confirmed from the console's text.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-21

**Notes:**

Accepted, on two conditions, both closed in this session before the pull request (no `--partial`,
since v1-e39-t07 and t08 depend on this task):

1. **Question 1: (a).** Add the Chromium install step to `validate-dev.yml`'s slow job, and add
   `.github/workflows/validate-dev.yml` to the spec's packages with a comment
   `PM ruling 2026-10-21 (v1-e39-t06 Q1)`. The task that adds a suite leaves its tier green.
   * Check that the slow job's marker expression actually selects `packages/debate_api/tests/browser`,
     and say so in the report.
   * Add a line to the workflow's comment saying why the step exists.
2. **Question 2: as you recommend.** ac4 runs after today's re-parse to `docx-6`, by the block in
   Operator follow-ups. Record the outputs and each yes or no in your own section, then set the
   Goal `Succeeded`.

As before, if anything comes out differently from what you expect, in ac4 or in the workflow, stop
and ask for another review rather than opening the pull request.

**What is good:**

* **Copy card is right where it is hardest.** The `ClipboardItem` of Promises is written inside the
  click, and an init script records the order (click, write with activation, fetch answered, write
  done). The await-first mutant fails it. You measured that headless Chrome would not have shown
  the difference, and kept the test on the order rather than on Chrome's leniency.
* **ac2 reads back the way Google Docs does,** from the clipboard's `text/html`. The browser's own
  paste is checked separately for what it can keep (Decision 6). Both are honest about what each
  proves.
* **The CSP tested is the deployed one,** read from `distribution.tf`, and every look is a class in
  a hashed `app.css`, because `default-src 'self'` refuses inline styles too. Decision 7 (Chrome
  reporting the copy's inline styles while it sanitises the write) is documented and asserted
  exactly, not ignored.
* **The index holder** follows ADR-0019 (c) 3 and 5:
  * the wall clock, so frozen time counts;
  * a refused pointer remembered by its entity tag;
  * read-only files under new names, deleted after in-flight requests end;
  * startup cleanup of `/tmp`;
  * a download bounded by the manifest's size.

  The ten-minute mutant first survived because the tests advanced by the constant. Writing the
  minutes out is the right fix.
* **The privacy note was met:** `test_the_app_logs_no_query_card_id_or_card_text_for_a_search_a_card_view_and_a_copy`.
* **The image gains nothing from the dev dependencies,** checked against what `tub_deploy.sh`
  stages.

**Rulings on the rest:**

* **Deviations 1 to 3: accepted,** including `debate_core.testing.search_index` for both packages'
  tests.
* **Decisions 1 to 10: accepted.** On Decision 4, the pilot's students paste into Google Docs on
  Chromebooks, which ac4 checks. Word is not checked here, and the coach's beta (v1-e39-t10) notes
  it.

**Follow-ups, placed by the PM in the next batch:**

* **2 (audit of the card view and copy) and 4 (the runbook on the fetched index):** v1-e39-t07's
  amendment, with the suppression re-read in the holder's `_refresh`.
* **3 (the holder's `INFO` lines not reaching the function's log):** v1-e39-t10's amendment, since
  its Lambda measurements need the cold-start index load time. That means logging configuration
  only, with no query, card or user in any line.
* **5 (no previous-page link):** no change for the pilot.
