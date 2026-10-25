# Session report: v1-e39-t17-landscape-pages

| | |
|---|---|
| Task | `v1-e39-t17-landscape-pages` — The landscape report and its school view on the pilot, for signed-in team members |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t17-landscape-pages.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t17-landscape-pages.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t17-landscape-pages` |
| Session status | PARTIAL <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The pilot has a Landscape area for any signed-in member: `/landscape` lists each caselist's newest
bundle, `/landscape/<caselist>` shows its `report.md` on one page with one contents list, and the
school view is a front page with one page per school and one per position (the PM's layout A). Pages
are rendered on the server with markdown-it-py (raw HTML escaped, linkify off, every link checked)
from bundles held at most five minutes. Each view writes a `landscape-viewed` audit record of its kind,
caselist and snapshot. The function's role gains the read of `reports/landscape/*` and a listing
limited to that prefix, tested in the module, and the runbook has the plan, apply, deploy and check
blocks. The Goal stays **InProgress**: ac4's apply, deploy and coach's check are the operator's. **Look
first at** three open items, all in Deviations: the report was republished after the counts and now
weighs 92% of the page line as one page; ADR-0019's role table says "no list"; and the Lambda Web
Adapter's documentation still has to be read, which is a live fetch, so it is handed to the operator.

## Counts before building (ac1)

Measured 2026-10-25, read-only, from the operator's local copy of the newest hspolicy26 bundle,
`~/.debate-research/dev/reports/landscape/hspolicy26/2026-10-20/` (the PM named it; the bucket copy
was not read, since every AWS call is the operator's). Rendered with markdown-it-py 4.2.0 as the
pages will render it: `MarkdownIt("commonmark", {"html": False}).enable("table")`. Gzip at level 6.
Two scratch scripts, under one second each, no network.

This report.md predates `v1-e32-t20`: it has one `#` heading and no contents list. `t20` adds the
three `#` parts (Affirmative, Negative, Neither side) and a `## Contents` list of about 1 KB (from
the golden fixture's diff), and moves sections but adds none, so the sizes below hold within about
1 KB. The hspolicy26 report was not re-rendered in the `t20` shape.

**The line.** ADR-0019 (b) 1: one HTML page under 150 KB. `v1-e39-t06` measures it as the page's
uncompressed bytes plus `app.js` (12,828 B) and `app.css` (10,090 B), against 150 × 1024 = 153,600 B
(`PAGE_BUDGET` in `packages/debate_api/tests/test_search_pages.py`). That leaves about 128 KB for a
page's HTML, the base template's chrome (about 2 KB) included.

| File | Markdown | Rendered HTML | Gzipped HTML | Headings `#` / `##` / `###` / `####` | Tables | Table data rows | Links out |
|---|---|---|---|---|---|---|---|
| report.md | 41,881 B | 66,015 B | 12,571 B | 1 / 11 / 18 / 10 | 70 | 329 | 0 |
| schools.md | 330,863 B | 568,067 B | 41,400 B | 1 / 2 / 164 / 97 | 253 | 4,226 | 2,109 |

report.md as one page: 66,015 B of HTML plus the two assets is about 89 KB, about 91 KB with the
chrome and 94 KB with a contents list: about 61% of the line. Its largest `##` section, Negative
positions, renders to 18,341 B; by `t20`'s parts, Affirmative is about 24 KB, Negative about 29 KB,
Neither side about 9 KB.

schools.md as one page is 3.7 times the line uncompressed, though 41 KB gzipped. Neither of its two
`##` sections fits on its own:

| schools.md piece | Count | Rendered HTML |
|---|---|---|
| Header and metadata table | 1 | 1,221 B |
| `## By school` | 1 | 205,546 B |
| One school under By school (`###`) | 155 | median 761 B, largest 10,082 B (117 rows) |
| `## By position` | 1 | 361,300 B |
| One kind under By position (`###`) | 9 | largest 135,124 B (Affirmative side: Advantages, 810 rows), next 80,733 B (Disadvantages) |
| One position under By position (`####`) | 97 | largest 34,302 B |

Every school's 2,109 rows appear twice, once by school and once by position. All 475 team codes
have a team-page link (the view's own count), and every link is on a By position row. Rendering
takes 17 ms for report.md and 203 ms for schools.md on the operator's Mac.

### After the counts: the report was republished

At 02:11 on 2026-10-25, after the counts above went to the PM, the operator's machine rewrote the
hspolicy26 bundle in `v1-e32-t20`'s shape. `schools.md` is byte for byte the same size (330,863 B),
but `report.md` grew:

| | At the counts | Republished |
|---|---|---|
| report.md | 41,881 B | 77,168 B |
| Rendered HTML | 66,015 B | 115,492 B (21,221 gzipped) |
| Headings `#` / `##` / `###` / `####` | 1 / 11 / 18 / 10 | 4 / 13 / 18 / 10 |
| Tables, rows with header rows | 71, 398 | 112, 669 |

The impact-card tables under `### Disadvantages` (12,026 B to 30,180 B) and `### Advantages`
(10,463 B to 30,177 B) grew, and a new `## Counterplan planks` section (9,506 B) appeared. Measured
through the app over the local bundle (a scratch script putting it in the test world's in-memory
store, printing sizes only), each page with `app.js` and `app.css`:

| Page | Bytes with the assets, of 153,600 |
|---|---|
| The report, one page | 141,796 (92%) |
| The school view's front page | 48,670 |
| The largest school | 34,719 |
| The largest position | 78,567 (its 2,109 links gained `target`, `rel` and "(opens in a new tab)") |

The first request (list, read and render both files) took 494 ms in process and a held page 3 ms.
Rendering alone took 17 ms (report.md) and 203 ms (schools.md) at the counts, as the PM asked to
record. The page-weight test is now sized to the republished report (`HSPOLICY26_REPORT_HTML =
115_492`) and passes at 140,207 bytes. Whether the report stays one page is the PM's question (see
Deviations).

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `landscape-pages` | Built; ac4 open | Counts sent and ruled; routes, shelf, rendering, audit, Terraform grant and runbook built and tested; apply, deploy and the coach's check are the operator's |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — counts before building, sent to the PM with the proposed layout | PASS | The tables above, measured read-only with markdown-it-py 4.2.0 (two scratch scripts, under 1 s); sent as a relay prompt; ruled 2026-10-25 (layout A), recorded as a `# PM rulings` comment above the spec's `acceptanceCriteria` |
| ac2 — with a moto bucket holding synthetic bundles, student and coach see the list, report and school view with contents and anchors; signed-out, expired and tampered sessions refused on every new route, in the matrix; private and uncached; failing first | PASS | `packages/debate_api/tests/test_landscape_pages.py` (87 passed, both roles): hand-written expectations for the list, the report's contents and its twelve heading ids (one `-2`), the front page's school and position links, a school page, a position page. `test_landscape_bundles.py` reads the same fixtures from a versioned moto bucket through the real `S3EvidenceObjectStore`. `test_auth_authorization_matrix.py` has the five routes: 319 passed over valid, expired, idle, tampered, foreign-key, other-cookie and absent sessions; before the rows were added, `test_the_matrix_covers_every_route_the_app_serves` failed listing the five routes. `test_exposure.py` has them too, 404s included: `private, no-store` for student, coach and nobody. Red run below |
| ac3 — re-read after five minutes (deleted school view, republished report); raw HTML escaped; a refused team page renders as text; one audit record per view, naming caselist, snapshot and page and no school or team code | PASS | `test_landscape_bundles.py` (26 passed): in moto, a deleted `schools.md` still shows at 4 min 59 s and is gone at 5 min, with no older view; a republished `report.md` likewise; a newer snapshot likewise. A failing bucket after five minutes gives 503, not the old bundle. Planted `<script>`, `<img onerror>`, raw `<a>`, a `javascript:` link, a `data:` image, an off-site link, an autolink, a bare URL and a team page in `report.md` render as text, as do another caselist's team page, a query, a display name, a deeper path and plain http in `schools.md`. Six page kinds each write one record, compared whole; none names a school, team code or position; a 404 writes none; a failed write gives 503 with no page. A log test at `NOTSET` over moto finds no school, anchor, position id or team code in any record but the test client's own httpx lines |
| ac4 — the role's read granted by Terraform, tested, applied in dev after the PM reads the plan; the deployed dev pilot shows the hspolicy26 report to a signed-in coach | NOT RUN (Terraform tested: PASS) | `terraform test` for `evidence_search`: 17 passed, including the new `function_role_lists_only_the_landscape_bundles_and_reads_them`; `scripts/terraform_checks.sh` passed in full, offline (30 s). The plan, apply, deploy and coach's check are operator steps after the merge (Operator follow-ups) |
| Node: `uv run pytest packages/debate_api/tests` | PASS | `.venv/bin/python -m pytest packages/debate_api/tests` → `966 passed in 9.65s` |

**Failing first.** The new tests were run against a refuse-nothing skeleton, then the committed code
was restored with `git checkout` and run green. The skeleton held bundles for a year, linked every
link, turned raw HTML and linkify on, kept images, kept the bundle's own contents list, numbered no
repeated anchor and wrote no audit record. Over `test_landscape_pages.py`, `test_landscape_bundles.py`
and `packages/debate_core/tests/domain/test_landscape_pages.py`: **43 failed, 112 passed**. What still
passed holds without any of those rules: the routes, the gate, the caching headers, the base template's
missing search and cart, and the page weight. Then: 155 passed.

**Mutants** (each run with the three files above, `-x`, then restored; no Hypothesis here):

| Mutant | Caught by |
|---|---|
| A handler logs `request.url.path` at DEBUG | `test_no_log_record_at_any_level_holds_...` |
| The shelf re-reads only after more than five minutes (`>` for `>=`) | `test_a_deleted_school_view_shows_within_five_minutes_...` |
| An older snapshot's school view fills a removed one | the same |
| A failed read keeps serving the old shelf | `test_a_bucket_that_stops_answering_after_five_minutes_...` |
| A refused link keeps its markup | `test_every_link_but_a_same_page_heading_is_text_in_the_report` |
| The team-page check skips its caselist comparison | **not caught, 155 passed**: the rebuilt-URL equality already refuses another caselist, so the comparison was deleted (agreement 8) |
| Terraform: the listing statement without its `s3:prefix` condition | `function_role_lists_only_...` (1 failed, 16 passed); a first version of the assertion *errored* on the missing attribute (15 skipped), which is not a catch, so it reads `try(statement.Condition, null)` |
| Terraform: GetObject on `reports/*` instead of `reports/landscape/*` | the role-table run and `function_role_lists_only_...` (2 failed) |

**Before the report** (working agreement 10):

| Command | Result |
|---|---|
| `uv run scripts/affected_tests.py --run` | `The whole selection is affected: packages/debate_api/pyproject.toml is shared test ground.` Nothing run; left to the PR's `ci` with no operator hand-off (PM ruling). Before the pyproject edit it chose 226 of 482 files |
| `.venv/bin/python -m pytest packages/debate_api/tests packages/debate_core/tests/domain packages/debate_core/tests/application/tub packages/debate_core/tests/integrations/cognito tests/architecture tests/specs packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py tests/scripts/test_tub_deploy.py -q -m "not slow and not live"` | `2630 passed in 32.14s` (before the last test-size commit; the landscape files ran again after it, 87 passed) |
| `uv run --frozen ruff format --check .` / `ruff check .` | `1346 files already formatted` / `All checks passed!` |
| `uv run --frozen pyright packages/debate_api packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `uv run --frozen lint-imports` | `Contracts: 16 kept, 0 broken.` |
| `uv run scripts/check_thin_handlers.py` | `OK: 59 CLI command and API route handlers within 25 statements` |
| `uv run python scripts/check_command_blocks.py --base origin/dev` | `OK: no '#' comments in 432 shell code blocks in 164 Markdown files` |
| `TF_CLI_CONFIG_FILE=<mirror> bash scripts/terraform_checks.sh` | `All Terraform checks passed.`, offline; the `.terraform` directories it left were removed; no lock file changed |
| `uv run scripts/validate_specs.py` | `OK: 457 files, 40 epics, 395 tasks, 22 releases` |

## Files changed

* **`packages/debate_core/src/debate_core/domain/landscape_pages.py`** (new): page kinds, bundle keys,
  heading anchors with `-2` for a repeat, position ids, and the link rule over
  `search_source_links.team_page_url`.
* **`packages/debate_core/src/debate_core/application/tub/landscape_pages.py`** (new):
  `LandscapeShelf`, the newest bundles held at most five minutes, re-read when changed, prepared once.
* **`application/tub/audit.py`, `access_audit.py`**: `landscape-viewed`, its `caselist`, `snapshot`
  and `page` fields and their rules; `AccessAuditService.landscape_viewed`.
* **`packages/debate_api`**: `landscape_markdown.py` and `landscape_pages.py` (new), five routes in
  `routes.py`, the shelf in `state.py` and `container.py`, four templates, `base.html` and
  `refused.html` taking a `landscape` flag, a few lines of `app.css`, the README, and
  `pyproject.toml` declaring `markdown-it-py>=4.0` (committed last, with `uv.lock`).
* **`packages/debate_api/tests`**: `test_landscape_pages.py`, `test_landscape_bundles.py`,
  `test_landscape_image.py` (new), the hand-written synthetic bundles under `fixtures/landscape/`,
  `conftest.py`'s in-memory bundle store, and new rows in the matrix, exposure and audit-schema tests.
* **`packages/debate_core/tests/domain/test_landscape_pages.py`** (new).
* **`docs/data/tub-audit-record.schema.json`**: the new action, its three fields and its branch.
* **`infrastructure/modules/evidence_search`**: the role's read of `reports/landscape/*` and its
  prefix-limited listing; the role table in the module test, and a new run.
* **`docs/runbooks/evidence-search.md`**: "The landscape pages" section, step 9's new checks, a
  refusal row and two rows of "What to record".
* **The spec**: the PM's rulings as a comment above `acceptanceCriteria`.

## Deviations from the spec

1. **`docs/data/tub-audit-record.schema.json` changed**, outside `constraints.packages`, as the PM
   ruled; the PM adds `docs/data` in a PM batch.
2. **The role may list `reports/landscape/`, and ADR-0019's role table says "no list".** The bundles
   have no pointer like the index's `current.json`, and E32 is not to change, so each caselist's newest
   snapshot can be found only by listing. The listing is `s3:ListBucket` on the bucket, limited by
   `StringLike` `s3:prefix` to `reports/landscape/*`. `docs/adr` is outside this task's packages, so
   ADR-0019 is not edited. A proposed amendment for its role table's `s3:GetObject` row, and a new row:
   *"`reports/tub/search/*`, `reports/landscape/*` (the landscape pages, `v1-e39-t17`), current
   objects under `raw/`, and `manifests/_suppression/suppression-list.jsonl`, in its own environment's
   evidence bucket only. No `GetObjectVersion`, no write"* and *"`s3:ListBucket` | the evidence bucket,
   for the prefix `reports/landscape/` only (`s3:prefix`), so the landscape pages can find each
   caselist's newest bundle. No `ListBucketVersions`"*.
3. **The Lambda Web Adapter's documentation has not been read.** Reading it is a live fetch, which is
   the operator's (the PM's rule since `v1-e07-t05`), so it is a one-line hand-off below. The test
   the ruling asked for exists: no record the app writes, at any level, holds a school's anchor or a
   position id. What is open is whether the adapter itself logs request paths, and so whether
   `infrastructure/modules/evidence_search/main.tf` needs a setting to stop it. Until that is read,
   the ruling's condition is not met.
4. **The report outgrew the size layout A was ruled on.** One page is 141,796 of 153,600 bytes, not
   about 94 KB, and the report grew 75% in one republish. It passes today. Options are in the
   message to the PM.

## Decisions and assumptions

* **The newest bundle** is the latest snapshot holding `report.md`, as ruled. A listing that shows the
  held files with the same size and time keeps what was rendered; otherwise both files are read
  and rendered again. If the bucket fails, the shelf is dropped and the next request lists again.
* **No search, download or share link** is read as the forbidden list writes it (the list wins over
  prose). On landscape pages the header has no Search link and no cart, the site name is plain text,
  and a refusal links back to the landscape list, not the search. Every other signed-in page gains a
  **Landscape** link. If the PM reads the rule as being about the reports alone, the Search link can
  come back with one template change.
* **What is audited.** A record is written before the page is sent, and a failed write gives 503, as
  for a card page. A 404 writes nothing, because nothing of a bundle was shown. A removed school
  view's message page is recorded as the kind asked for (`school-view`, `school` or `position`).
* **Paths.** A school's path is its heading's anchor by GitHub's rule, which keeps Unicode letters.
  Jinja URL-encodes it and Starlette decodes it. A position's path is its id, checked against the
  taxonomy's pattern; a `####` heading that is not one is listed as text with no page. A school view
  not in `v1-e32-t04`'s shape is shown whole on its front page.
* **Contents.** The report's list holds its `#` parts with their `##` sections. A `##` before the first
  part (About this report) stands alone; `###` and `####` get anchors but no entry.
* **Team-page links** carry the card page's `(opens in a new tab)` span. The span is fixed markup from
  the renderer, never text from a bundle.
* **The shelf's lock** is an `asyncio.Lock` used inside the one event loop uvicorn runs. Rendering runs
  in a worker thread (`asyncio.to_thread`), so a 200 ms render does not block the loop.

## Operator follow-ups

All of these are in [the runbook's "The landscape pages"](../runbooks/evidence-search.md#the-landscape-pages).
They run after the merge, from a checkout of `dev` (`$WT`) with its `owner.auto.tfvars` in place.

**1. The Lambda Web Adapter's logging** (live read, seconds; before the PM's review closes). This
prints only the README lines about logging, at the pinned release first and the main branch if that
tag's file is missing.

```bash
{ curl -fsSL https://raw.githubusercontent.com/awslabs/aws-lambda-web-adapter/v1.1.0/README.md || curl -fsSL https://raw.githubusercontent.com/awslabs/aws-lambda-web-adapter/main/README.md; } | grep -n -i -E 'log'
```
Paste the output back. If the adapter logs request paths at its default level, the session adds the
setting that stops it to the function's environment in `main.tf`, with a module test.

**2. The plan** (about 1 min), for the PM to read before the apply:

```bash
cd "$WT"
if env | grep -q '^DEBATE_'; then echo "STOP: unset these first: $(env | grep '^DEBATE_' | cut -d= -f1 | tr '\n' ' ')"; elif [ "$(grep -c -E 'evidence_search_(deployer|accounts)_user_names' infrastructure/envs/dev/owner.auto.tfvars)" != 2 ]; then echo "STOP: owner.auto.tfvars lacks the pilot's two lines"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev init -input=false > /dev/null && AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev plan -input=false -out=landscape-read.tfplan; fi
```
**Expected:** `Plan: 0 to add, 1 to change, 0 to destroy.` The one change is
`module.evidence_search.aws_iam_role_policy.function`, updated in place. In its policy, the GetObject
statement gains `reports/landscape/*` and its `Sid` becomes
`ReadThePilotIndexLandscapeBundlesCurrentRawEvidenceAndTheSuppressionList`. There is one new statement,
`ListTheLandscapeBundlesOnly`: `s3:ListBucket` on the bucket, `StringLike` `s3:prefix`
`reports/landscape/*`. Stop on anything else, a destroy or an account assignment above all, and send
the plan to the PM.

**3. The apply** (about 1 min), only after the plan was read:

```bash
cd "$WT"
if env | grep -q '^DEBATE_'; then echo "STOP: unset the DEBATE_ overrides first"; else AWS_PROFILE=debate-admin terraform -chdir=infrastructure/envs/dev apply -input=false landscape-read.tfplan && rm landscape-read.tfplan; fi
```
Success looks like `Apply complete! Resources: 0 added, 1 changed, 0 destroyed.` Then the runbook's
step 9 first block. It prints `allowed` for the landscape read and the `reports/landscape/` listing,
and `implicitDeny` for a listing with no prefix or of `raw/`.

**4. The deploy** (about 4 min), after the apply. The pilot's image build takes `markdown-it-py` from
`uv.lock`, as it does every other debate-api dependency:

```bash
cd "$WT"
uv sync --all-packages
scripts/tub_deploy.sh dev
```
Success looks like `{"status":"ok"}` through CloudFront and `Deployed <sha> to dev`.

**5. The check that the landscape page renders** (seconds signed out, then by hand signed in):

```bash
for P in /landscape /landscape/hspolicy26 /landscape/hspolicy26/schools; do curl -sS -o /dev/null -w "$P %{http_code} %header{cache-control}\n" "https://tub.dev.wfbdebate.com$P"; done
```
Success looks like three lines ending `302 private, no-store`. Then, signed in as the coach:
**Landscape** lists hspolicy26 with its date. The report shows one contents list (Affirmative,
Negative, Neither side and their sections) whose links jump. There is no Search link or cart. In
positions by school, one school's page and one position's page each render, and a team page opens
openCaselist in a new tab. Last, the audit lines, which name no school, team code or position:

```bash
aws logs filter-log-events --profile debate-admin --region us-east-1 --log-group-name debate-dev-tub-audit --filter-pattern '"landscape-viewed"' --query 'events[-5:].message' --output text
```
Success looks like up to five lines with `"action":"landscape-viewed"`, each with the page's kind, and
`"caselist":"hspolicy26"` with the snapshot date on all but the `caselists` page. Record the results
in the runbook's "What to record" table. This check is ac4's evidence.

## Follow-up work

* **ADR-0019's role table** (Deviation 2): the PM's amendment, in a PM batch.
* **A pointer for the landscape bundles.** If E32's run wrote a
  `reports/landscape/<caselist>/current.json` last, as `tub index publish` does, the role could drop
  its only listing. That belongs to E32, not here.
* **The report's growth.** If the report keeps growing, the layout can switch to one page per `#` part
  (Affirmative about 45 KB, Negative about 57 KB, Neither side about 9 KB rendered), keeping the
  contents list as the index. That is the PM's question now.
* **`v1-e39-t10`'s pilot review** may want the landscape pages in the coach's beta checklist.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
