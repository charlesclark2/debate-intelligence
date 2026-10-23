# Session report: v1-e39-t07-removal-audit-and-exposure

| | |
|---|---|
| Task | `v1-e39-t07-removal-audit-and-exposure` — Removal, access audit and exposure: the pilot meets the policy's E39 gate |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t07-removal-audit-and-exposure.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t07-removal-audit-and-exposure.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t07-removal-audit-and-exposure` |
| Session status | PARTIAL — waiting on the operator's dev run (ac4, and the deployed half of the exposure check) <!-- COMPLETE / PARTIAL / BLOCKED --> |

## Summary

The pilot's function now re-reads the suppression list inside the index holder's `_refresh`, in the
same five-minute pass as `current.json` and before it. Every lease hands the request a
`ScreenedSearch` that applies `is_suppressed(source_sha256, disclosure_digest)` to search and card
lookup, so a removed occurrence leaves results, card pages and copies within five minutes, and a
frozen environment rechecks before it answers. A list that cannot be read refuses the request
rather than serving a stale one. Card views and copies write `card-viewed` and `card-copied` before
the card goes out, and fail closed. A first-page search writes one `searched` record carrying its
result count and nothing else. `cards-downloaded` is defined for `v1-e39-t08`. The audit record has
a committed JSON Schema with a drift test. The removal credential may delete under
`reports/tub/search/` and nowhere else under `reports/`. Both runbooks gain the pilot: what the
function fetches and how it refuses, and the removal's rebuild, publish and guarded prune. **What
is left is the operator's dev run:** apply the grant, deploy, the deployed exposure checks, and the
synthetic removal exercise (ac4). The phase stays `InProgress` until those results are in this
report.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `gate` — Removal, audit and exposure | Code, tests and documents done; operator dev run outstanding | Its criterion (`pytest packages/debate_api/tests -k "suppression or audit or exposure"`) passes: 88 passed |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — a suppressed occurrence is gone from results, card pages and downloads within five minutes, by test with a fake clock, shown failing first | PASS (results, card pages, copies); downloads by construction | `packages/debate_api/tests/test_suppression_in_pages.py`: at 4:59 the featured card is in the results, its page and its copy answer 200; at 5:00 it is in none of them (404 twice), and 24 results remain. Frozen for 50 minutes, the first request hides it. Red first: with `_refresh_suppression_list` returning at once, **5 failed in 2.35s**; green, 5 passed. `v1-e39-t08`'s download route does not exist yet. The only way a route reaches the index is `lease()`, which yields a `ScreenedSearch` with no unscreened search on it, so the download goes through the same list; t08's own test should show it |
| ac2 — every audit record validates against a committed schema, and a test over every action shows none of the forbidden fields | PASS | `docs/data/tub-audit-record.schema.json` (`additionalProperties: false`, 8 fields). `test_audit_record_schema.py` (54 passed) holds the schema and `AuditRecord` together from hand-written expectations (actions, fields, card pattern, 30-card maximum). It builds a record for all 16 actions as their writers do (`AccountAdministration` and `AccessAuditService` for 12) and finds no forbidden field or value (fixture school, team code, query, URL, token, username, email, card text, IP address). The schema refuses 17 forbidden field names and 9 out-of-shape records. `conftest.FakeAuditSink` validates every record the app writes in any `debate_api` test: 566 passed with it on, t05's account records included. `test_access_audit.py` (16 passed): exact field sets, no query, filter, cursor or cluster id in a search record for a query naming the fixture school and team code, and nothing written for a next page |
| ac3 — the full Playwright journey with a fixture school, team code and query leaves none of them in the captured app logs | PASS | `test_exposure_a_whole_journey_logs_no_query_school_team_code_or_card_text` (Chromium, `-m slow`). It signs in through the app's callback, searches `zephyr Maple Grove QX`, filters, pages, opens a card, copies it, opens the account page and signs out through `/logout`. Logs are captured from bare loggers at DEBUG, and none holds the school, team codes, query words, card text, username or cluster id. Shown failing: a planted `debug("searched %s", query)` in the search route → `1 failed (AssertionError: zephyr in debate_api.planted)`. Whole Chromium file: `14 passed in 10.42s` |
| ac4 — the removal runbook's pilot steps exercised in dev with a synthetic source, and the operator's record in the report (amended: PM ruling 2026-10-22, prod moves to `v1-e39-t10`) | NOT RUN | Waiting on Operator follow-ups 1 to 4. The runbook's prune script is tested from the runbook itself: `test_removal_runbook_index_prune.py`, 4 passed |
| ac5 — the report maps each item of the policy's E39 gate to the test or operator record that proves it | PASS (the operator records it cites are pending) | [The E39 gate, item by item](#the-e39-gate-item-by-item), below |
| ac6 — the removal credential can delete under `reports/tub/search/` and nowhere else under `reports/`, by the grant-scope test extended, and the layout document says so | PASS | `terraform -chdir=infrastructure/modules/evidence_bucket test` → `13 passed, 0 failed`. The removal run names every object a delete statement may reach (the five prefixes and `reports/tub/search/*`), refuses any other `reports/` resource, and checks the prefix is kept out of `removable_prefixes`. The operator run checks the everyday credential's version listing reaches nothing under `reports/`. Before the old delete-scoping assertion was updated it failed on the new statement (12 passed, 1 failed). `docs/architecture/evidence-store-layout.md` says so. The dev apply is Operator follow-up 1; prod's goes on the PM's promotion list |
| ac7 — the suppression list is re-read in the holder's refresh, at most five minutes apart, and a frozen environment rechecks, by test with an injected clock, shown failing first | PASS | `packages/debate_core/tests/application/test_search_index_holder_suppression.py`, 16 passed: hidden at 5:00 and not at 4:59; read before the pointer; a 304 at five minutes; frozen three hours, rechecked before answering; an unreadable list refuses and the next request retries; an unfinished or unreadable line refuses the list whole. Red first, against the same skeleton: **13 failed, 3 passed in 2.85s**. The 3 that passed assert something stays visible |
| ac8 — the evidence-search runbook says what the function fetches, when, and what an index refusal looks like, and the docs checks pass | PASS | `docs/runbooks/evidence-search.md`: "What the function fetches, and when" and "What a refusal looks like in the app log". `check_command_blocks.py --base origin/dev` → OK, 341 blocks; `check_links.py` → OK, 1942 links; `docs_index.py --check-descriptions` → all 41 described; `docs_index.py --check` → up to date |
| Node `gate`: Removal and audit tests pass | PASS | `uv run pytest packages/debate_api/tests -k "suppression or audit or exposure"` → `88 passed in 2.50s` |

### The E39 gate, item by item

Data-use policy, [E39 gate](../policies/caselist-data-use.md#e39--student-evidence-search-pilot-v17).

| Gate item | Proven by |
|---|---|
| 1. Policy approved; the removal runbook's pilot steps exercised end to end: gone within five minutes, the rebuilt index no longer holds it | Policy 1.10, approved. **Dev:** this report's operator record (Operator follow-up 4, pending). **Prod:** `v1-e39-t10` (PM ruling 2026-10-22). Tests: `test_suppression_in_pages.py`, `test_search_index_holder_suppression.py`, `test_removal_runbook_index_prune.py` |
| 2. Team-only access; coach-created accounts only; password and second factor | `v1-e39-t05`'s `test_auth_authorization_matrix.py` (every route, student and coach, signed in, ended, tampered and absent); `v1-e39-t04`'s `user_pool_admits_only_coach_created_accounts_with_totp` and `app_client_is_confidential_code_flow_only` (`evidence_search.tftest.hcl`); `v1-e39-t05`'s `test_auth_enrolment.py` (no session without an authenticator) |
| 3. No public reachability; only the function reads `raw/` and writes nothing; signed-in responses private and never cached | Plan: `evidence_bucket_keeps_block_public_access_and_grants_cloudfront_nothing`, `cloudfront_reaches_the_function_url_and_nothing_else`, `distribution_sends_the_security_headers_and_caches_nothing` (no access log, `CachingDisabled`), `function_role_is_the_adr_role_table_entry_by_entry`, `function_role_has_no_other_grant`, `bucket_is_private_versioned_and_kms_encrypted`, `bucket_policy_requires_tls_and_this_key`. `test_exposure.py` holds those names, and checks every route's every answer is `private, no-store` for student, coach and nobody. Deployed: Operator follow-up 3 (pending) |
| 4. Every access audited (view, copy, download, account change), with nothing identifying; 400 days | `test_access_audit.py`, `test_audit_record_schema.py`, the schema-validating `FakeAuditSink`; download defined (`cards-downloaded`), written by `v1-e39-t08`; account changes: `v1-e39-t05`. 400 days and append-only: `audit_log_keeps_four_hundred_days_and_the_app_log_thirty`, `function_role_has_no_other_grant`, and the runbook's step 5a (deletion protection). No query in the logs: `v1-e39-t06`'s `test_the_app_logs_no_query_card_id_or_card_text_for_a_search_a_card_view_and_a_copy`, this task's Chromium journey (ac3), `tests/scripts/test_tub_deploy.py` (`--no-access-log`), and Operator follow-up 5's log scan (pending) |
| 5. The suppression list governs: a suppressed occurrence never enters the index, and is hidden by the running function within five minutes | Never enters: `v1-e39-t02`'s `test_search_index_leaves_out_a_suppressed_occurrence_and_an_emptied_cluster`. Hidden within five minutes: ac1 and ac7 above. **Known limit (PM ruling 2026-10-22):** the function reads the suppression list, not `path-holds.jsonl`, and the index keeps no paths. So a removal that only holds a path is followed straight away by a rebuild and publish, and the card is gone in minutes, not at next week's build (`caselist-removal.md`, the student search pilot) |
| 6. No sharing surface leaves the team; a copy or download carries its provenance line | `v1-e39-t06` (no public link or share-by-link route: the authorization matrix lists every route; `test_copy_card.py` for the provenance line); downloads: `v1-e39-t08` |
| 7. Attribution and the "Disclosed evidence, not platform-verified" label | `v1-e39-t06`'s `test_the_card_page_shows_the_label_tag_cite_line_counts_copy_card_and_every_occurrence` |
| 8. Nothing beyond school plus team code; never searchable; no search by debater | `v1-e39-t02`'s `test_search_index_school_and_team_code_match_nothing`; `v1-e39-t03`'s `test_evidence_search_never_matches_a_school_team_tournament_round_camp_or_title` |
| 9. Least personal data; removing a student deletes the account | `v1-e39-t04`'s `user_pool_has_no_sms_and_nothing_beyond_a_username_and_an_optional_email`; `v1-e39-t05`'s accounts tests (`tub users remove` calls `AdminDeleteUser`) |
| 10. School review | Answered: policy open question 6 (version 1.10) |

## Before the report: what was run

- **The affected set is over two minutes.** `uv run scripts/affected_tests.py` chose **233 of 383
  test files (60.8%)**, because `debate_core.application` and its test fixtures are widely imported.
  Under agreement 10 I did not run it; the pull request's `ci` check runs the whole selection.
- **Run instead, within two minutes:** the test directories of what changed and the always-run
  list, with CI's markers:
  `.venv/bin/python -m pytest -m "not slow and not live" packages/debate_api/tests packages/debate_core/tests/application/tub packages/debate_core/tests/integrations/s3 packages/debate_core/tests/application/test_search_index_holder.py packages/debate_core/tests/application/test_search_index_holder_suppression.py packages/debate_core/tests/application/test_evidence_search.py packages/debate_core/tests/application/test_search_index_publish.py packages/debate_core/tests/application/caselist/test_version_retention_lifecycle.py packages/debate_core/tests/application/caselist/test_takedown_preflight_identity.py packages/debate_cli/tests/test_tub_index.py packages/debate_cli/tests/test_app.py packages/debate_cli/tests/test_help_rendering.py tests/architecture tests/specs tests/docs tests/scripts/test_check_command_blocks.py tests/scripts/test_docs_index.py tests/scripts/test_tub_deploy.py`
  → **1405 passed in 23.93s**.
- **The log-asserting suites, in one process** (agreement 10), after the holder's neighbours:
  `-n 0 -p no:randomly` over both holder test files and `packages/debate_api/tests` → **626 passed,
  14 deselected in 5.87s**.
- **Browser:** `-m slow packages/debate_api/tests/browser` → **14 passed in 10.42s**.
- **Terraform:** `terraform test` in `evidence_bucket` → 13 passed; in `evidence_search` → 16
  passed; `terraform fmt -check` clean. `scripts/terraform_checks.sh` → `All Terraform checks passed.` (fmt, validate, tflint, and `terraform test` in all four modules).
- `ruff format --check` and `ruff check` on the 18 changed Python files → clean.
  `pyright packages/debate_api packages/debate_core` → `0 errors, 0 warnings`. `lint-imports` →
  `13 kept, 0 broken`. `uv run scripts/validate_specs.py` → `OK: 404 files, 39 epics, 344 tasks, 21
  releases`.

- **After `scripts/task sync`** (onto `origin/dev` at `2a96979`, a clean rebase): `uv sync
  --all-packages`; the affected set is still over two minutes (233 of 385 files); the same
  changed-directories run → **1405 passed in 23.53s**; pyright `0 errors`; `lint-imports` 13 kept;
  `validate_specs.py` OK; `check_links.py` OK (1946 links); `check_command_blocks.py --base
  origin/dev` OK (349 blocks).

### Mutation run (20 mutants, agreement 8 and 10)

Each mutant ran against only the tests that cover it, with `HYPOTHESIS_STORAGE_DIRECTORY` a new,
empty directory (no Hypothesis property is involved; set anyway). None errored before running. The
three Terraform mutants were run again to read which `run` failed, and each failed on its assertion.

| Mutant | Tests | Result |
|---|---|---|
| The predicate hides nothing | holder and page suppression | caught, 3.3s |
| The predicate ignores the disclosure digest | same | caught, 0.9s |
| The predicate stops any suppression of the bytes (`is_suppressed(sha)`) | same | caught, 0.8s |
| `ScreenedSearch.search` passes no predicate | same | caught, 0.8s |
| The pointer is read before the list | same | caught, 0.8s |
| The recheck is due one tick late (`<=` for `<`) | same | caught, 0.9s |
| An unreadable list serves stale instead of refusing | same | caught, 0.8s |
| An unfinished last line is accepted | same | caught, 0.8s |
| `close()` keeps the list | same | caught, 0.8s |
| A next page is counted | access audit and schema | caught, 0.9s |
| A search with no terms is counted | same | caught, 1.1s |
| A card view fails open | same | caught, 0.8s |
| A copy fails open | same | caught, 0.9s |
| A failed search count fails the search | same | caught, 1.1s |
| Records omit their cards | same | caught, 1.1s |
| Access records carry no actor subject | same | caught, 1.2s |
| The index prefix widened to `reports/` | `evidence_bucket` terraform test | caught (`removal_permission_set_…`), 1.9s |
| The everyday credential lists index versions too | same | caught (`operator_permission_set_…`), 1.3s |
| The takedown cannot list index versions | same | caught (`removal_permission_set_…`), 1.3s |
| The prune deletes the current `current.json` | runbook prune test | caught, 0.8s |

## Files changed

- **`packages/debate_core/src/debate_core/application/`**: `search_index_holder.py` (the list's
  re-read in `_refresh`, `ScreenedSearch`, `SuppressionListUnavailable`), `ports/search_index_source.py`
  (`SuppressionListSource`), `tub/audit.py` (access actions, `cards`, `card_reference`),
  `tub/access_audit.py` (new: the access records, fail closed for cards, open for searches).
- **`packages/debate_core/src/debate_core/integrations/s3/search_index_source.py`** and
  **`packages/debate_core/src/debate_core/testing/search_index.py`**: the list's conditional read, in
  the bucket adapter and the in-memory bucket. Outside the spec's listed packages; see Deviations.
- **`packages/debate_api/src/debate_api/`**: `search_pages.py` (records before the card goes out;
  `searched` on a first page), `state.py` and `container.py` (wiring).
- **`packages/debate_api/tests/`**: `test_suppression_in_pages.py`, `test_access_audit.py`,
  `test_audit_record_schema.py`, `test_exposure.py`, `test_removal_runbook_index_prune.py` (new);
  `conftest.py` (the list source, the access audit, a failing and schema-validating audit sink);
  `browser/test_search_pages_in_chromium.py` (Copy card's 503, the journey's logs, and
  `Sec-Fetch-Site` for same-origin requests; see Decisions).
- **`packages/debate_core/tests/`**: `application/test_search_index_holder_suppression.py` (new),
  `integrations/s3/test_s3_search_index_source.py` (the list's read).
- **`infrastructure/modules/evidence_bucket/`**: `operator_access.tf` (`removable_index_prefix`,
  the takedown's own statement and listing condition), `outputs.tf`, `README.md`,
  `tests/evidence_bucket.tftest.hcl`.
- **`docs/`**: `data/tub-audit-record.schema.json` (new), `architecture/evidence-store-layout.md`,
  `runbooks/evidence-search.md`, `runbooks/caselist-removal.md`.
- **`plan_specs/…/t07-removal-audit-and-exposure.yaml`**: ac4 amended (PM ruling 2026-10-22), phase.

## Deviations from the spec

1. **Two files outside `constraints.packages`.** The function cannot re-read the bucket's list
   without an adapter, so `debate_core.integrations.s3.search_index_source` gains
   `read_suppression_list`. The test bucket in `debate_core.testing.search_index` serves the list
   too. Their tests are in `packages/debate_core/tests`. Both are the minimum the spec's own
   description needs ("wires it to the live suppression list").
2. **ac4 amended** as the PM directed: dev only with a synthetic source; prod is `v1-e39-t10`'s. The
   comment sits above the `- id: ac4` line, outside the folded block, so it stays a comment.
3. **Downloads in ac1** are covered by construction, not by a test, because `v1-e39-t08` has not
   built the route (the PM's brief: stay out of it). See ac1.

## Decisions and assumptions

- **A list that cannot be read refuses; a pointer that cannot be read does not.** A failed pointer
  recheck leaves the loaded index serving (t06). A failed list read refuses every search and card page
  with 503 and leaves the check due, so the next request reads again. ADR-0019 (c) 5 says an
  environment "never serves a stale list", and the five-minute bound is the gate's. Unreadable lines
  (not an entry, not UTF-8, an unfinished last line) refuse the list whole, as every other reader of
  it does.
- **A missing list is a refusal on the function.** Without `s3:ListBucket`, S3 answers a missing key
  with `AccessDenied`. The adapter maps `NoSuchKey` to an empty list for a caller that may list, but
  the function never gets one. Dev has had a list since `RM-2026-90`. The runbook now checks both
  environments and gives the one command that creates an empty list (under the takedown profile,
  with `--if-none-match '*'`). **Prod may have none:** see Operator follow-up 6.
- **No access record for a card that was not found or was hidden.** Nothing was shown, so nothing
  was accessed.
- **`card-viewed` is written for the card page only, not for a results page.** A result row is part
  of a search, which is counted.
- **The 503 for a lost audit record reuses "Search is not available right now".** It's true from
  the student's side and names no internal.
- **The browser harness reconstructs `Sec-Fetch-Site`.** Chromium adds `Sec-Fetch-*` after
  Playwright intercepts a request, so neither `request.headers` nor `all_headers()` carries them,
  and the gate refused the journey's sign-out with 403. The harness now sets `same-origin` only when
  the request's `Origin` is the pilot's, which is what Chrome sends; a request from another origin
  still gets none. The 13 t06 Chromium tests pass with it.
- **The journey signs in through the app's callback in-process.** Playwright routes only the first
  request of a redirect chain, so the hops after a fulfilled 302 would reach the real network. The
  real `/`, managed login's stand-in and the real `/auth/callback` run inside the log capture, and
  the browser is given the session cookie the callback set. Sign-out runs in the browser.
- **The prune keeps the whole current index directory**, noncurrent versions of its own files
  included, as the PM's guard says ("the current index's directory … never in the delete set").
- **Exercise request id `RM-2026-91`.** Ids from `RM-<year>-90` up are for exercises (`v1-e30-t07`);
  `RM-2026-90` is taken.

## Operator follow-ups

Run them in order, in one zsh window, from the task worktree. Before handing these over I ran
`scripts/task sync`, so the code deployed is the code that merges. Blocks 1 to 5 are this task's
dev run; block 6 is for the PM's promotion list.

**1. Apply the removal grant to dev** (expected runtime ~3 min). The worktree is fresh, so it has
no `owner.auto.tfvars`. Copy the dev file from the `dev-preview` worktree (the main clone has none;
PM correction 2026-10-22). It names the pilot's deployer and accounts users, so `grep` prints `2`:
it sets no `evidence_search_budget_emails`, and with none the dev root sends the budget alarm to the
`owner` address, the same one the runbook put in that list, so the plan does not change it. `init -reconfigure` is needed because my
`scripts/terraform_checks.sh` run initialised the roots with `-backend=false`.

Where: the task worktree
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t07-removal-audit-and-exposure
cp ../dev-preview/infrastructure/envs/dev/owner.auto.tfvars infrastructure/envs/dev/owner.auto.tfvars
grep -c evidence_search infrastructure/envs/dev/owner.auto.tfvars
export AWS_PROFILE=debate-admin
aws sso login --sso-session debate
terraform -chdir=infrastructure/envs/dev init -reconfigure
terraform -chdir=infrastructure/envs/dev plan -out=/tmp/t07-dev.tfplan
```
Success looks like `2` from `grep`, then a plan of **`0 to add, 2 to change, 0 to destroy`**: the
`DebateDevEvidenceRemoval` permission set's description and its inline policy, in
`module.evidence_store`. If `grep` prints anything but `2`, or the plan destroys anything (above
all an `aws_ssoadmin_account_assignment`), stop and paste the plan back. If it changes anything
else, paste it back before applying: dev has moved since the last apply, and I would rather read
it than guess. Otherwise:

```bash
terraform -chdir=infrastructure/envs/dev apply /tmp/t07-dev.tfplan
unset AWS_PROFILE
```
Success looks like `Apply complete! Resources: 0 added, 2 changed, 0 destroyed.`

**2. Deploy this branch to dev** (expected runtime ~3 min). Docker Desktop running.

Where: the task worktree
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t07-removal-audit-and-exposure
uv sync --all-packages
aws sso login --profile debate-dev-tub-deployer
scripts/tub_deploy.sh dev
```
Success looks like `{"status":"ok"}` and `Deployed <sha> to dev`, where `<sha>` is this branch's
head after the sync.

**3. The deployed exposure checks, dev** (expected runtime ~1 min; reads only). In Chrome, sign in
to `https://tub.dev.wfbdebate.com/` with your dev account. Open DevTools, then Application, then
Cookies, and copy the value of `__Host-tub_session`; the block reads it from the clipboard with
`pbpaste`, never prints it, and empties the clipboard straight after. It is your own dev session.
(The first version used `read`, which, pasted as part of a block, takes the block's next line as
its input; corrected 2026-10-22.)

Where: the task worktree
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t07-removal-audit-and-exposure
RAW=$(pbpaste)
TUB_SESSION=$(printf '%s' "$RAW" | tr -d '[:space:]')
pbcopy < /dev/null
echo "cookie length: ${#RAW} copied, ${#TUB_SESSION} without whitespace"
unset RAW
for P in / '/search?q=reserve' /account /signed-out /healthz; do
  curl -sS -o /dev/null -H "Cookie: __Host-tub_session=${TUB_SESSION}" \
    -w "%{http_code} ${P} cache-control=%header{cache-control} x-cache=%header{x-cache}\n" "https://tub.dev.wfbdebate.com${P}"
done
unset TUB_SESSION
export AWS_PROFILE=debate-admin
BUCKET=$(terraform -chdir=infrastructure/envs/dev output -raw evidence_bucket_name)
DIST=$(terraform -chdir=infrastructure/envs/dev output -raw evidence_search_distribution_id)
FUNCTION_URL=$(terraform -chdir=infrastructure/envs/dev output -raw evidence_search_function_url)
aws s3api get-public-access-block --bucket "$BUCKET" --query PublicAccessBlockConfiguration --output text
aws s3api get-bucket-policy-status --bucket "$BUCKET" --query PolicyStatus.IsPublic --output text
aws s3api get-bucket-acl --bucket "$BUCKET" --query 'Grants[?Grantee.URI].Grantee.URI' --output text
curl -sS -o /dev/null -w '%{http_code} anonymous s3 current.json\n' "https://${BUCKET}.s3.amazonaws.com/reports/tub/search/current.json"
curl -sS -o /dev/null -w '%{http_code} anonymous s3 suppression list\n' "https://${BUCKET}.s3.amazonaws.com/manifests/_suppression/suppression-list.jsonl"
curl -sS -o /dev/null -w '%{http_code} function url direct\n' "${FUNCTION_URL}healthz"
aws cloudfront get-distribution-config --id "$DIST" \
  --query '[DistributionConfig.Logging.Enabled, DistributionConfig.DefaultCacheBehavior.RealtimeLogConfigArn, length(DistributionConfig.Origins.Items)]' --output text
aws logs describe-deliveries --region us-east-1 --query 'deliveries[].deliverySourceName' --output text
aws s3api head-object --bucket "$BUCKET" --key manifests/_suppression/suppression-list.jsonl --query '[ContentLength,ServerSideEncryption]' --output text
unset AWS_PROFILE
```
Success looks like:
- `200 / cache-control=private, no-store x-cache=Miss from cloudfront`, and the same `private,
  no-store` and `Miss` on `/search`, `/account` and `/signed-out`. `/healthz` may say anything:
  it holds no data. Any `Hit`, or any `cache-control` other than `private, no-store` on the first
  four, is a failure.
- `True True True True` for Block Public Access, `False` for `IsPublic`, and an empty line for public
  ACL grants.
- `403` for both anonymous S3 reads and for the direct function URL.
- `False None 1` for CloudFront: no standard logging, no real-time log configuration, one origin.
- No delivery source naming the pilot's distribution from `describe-deliveries` (an empty line, or
  only names that are not the pilot's).
- A size and `aws:kms` for the suppression list.

Paste the output back.

**4. The removal exercise on dev, with a synthetic source** (expected runtime ~20 min, mostly two
five-minute waits). `RM-2026-91` appends a **permanent synthetic entry** to the dev suppression list
and removal log; record it in the register as the exercise. The store is a scratch one, built from
`tests/fixtures/parse_pipeline`'s fictional `testcl26` archives, whose files parse into cards. The
removed file is the fixture body `direct`, sha256 `058e2b1ce922…`, which one invented team
(Westfield XY) disclosed. Its card is a cluster of six occurrences whose representative is the
`direct` file. So within five minutes the whole card is hidden, and after the rebuild it comes back
from the other five, without Westfield XY. (Corrected 2026-10-22 from the index 4a built; the first
version said the card went whole.) The exercise replaces the dev pilot's current index with the
synthetic one. Block 5's last command puts dev's own index back.

4-pre. **No pull is running** (PM correction 2026-10-22). The weekly agent run started 2026-10-22
may publish a dev index, which would replace the synthetic one in the middle of the exercise.

Where: the task worktree
```bash
pgrep -fl 'caselist pull'
```
Success looks like nothing printed. If it prints a process, wait until it has finished and run
the check again before 4a. (P4's delete block also refuses if `current.json` changed after its dry
run.)

4a. Build and publish the synthetic index.

Where: the task worktree
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t07-removal-audit-and-exposure
aws sso login --sso-session debate
export DEBATE_ENV=dev
export DEBATE_STORAGE__DATA_DIR="$(mktemp -d)/evidence"
X="$(mktemp -d)"
uv run python -c 'import sys; from pathlib import Path; from tests.fixtures.parse_pipeline.build_parse_world import build_week_zips; print(sorted(build_week_zips(Path(sys.argv[1])).values()))' "$X"
uv run debate-research caselist import "$X/testcl26-0901.zip" --caselist testcl26 --snapshot 2026-09-01
uv run debate-research caselist import "$X/testcl26-0908.zip" --caselist testcl26 --snapshot 2026-09-08
uv run debate-research caselist import "$X/testcl26-0915.zip" --caselist testcl26 --snapshot 2026-09-15
uv run debate-research caselist parse --caselist testcl26
uv run debate-research tub index build --caselist testcl26
uv run debate-research tub index publish --env dev --newest
REMOVED=$(uv run python -c 'from tests.fixtures.parse_pipeline.build_parse_world import digest_of; print(digest_of("direct"))')
echo "$REMOVED"
date -u
```
Success looks like three imports, a parse with cards, a build naming an index id, a publish table
ending in `reports/tub/search/current.json` with that id, and `058e2b1ce922…`.

4b. **P1, after five minutes.** Signed in to `https://tub.dev.wfbdebate.com/`, search
`reserve margin`. The card **Data centre demand collapses the reserve margin** is listed. Open it
and note its path (`/cards/testcl26/<cluster id>`).

4c. **The removal**, dry run then execute.

Where: the same window
```bash
uv run debate-research caselist remove --source "$REMOVED" --request RM-2026-91 --reason POLICY
DEBATE_REMOVAL_PROFILE=debate-dev-evidence-removal uv run debate-research caselist remove \
  --source "$REMOVED" --request RM-2026-91 --reason POLICY --execute
date -u
```
Success looks like a plan naming one file to remove and one suppression entry, then `DONE in dev`.

4d. **P2, five minutes after `DONE`.** Open the card's path: **That card is not in the search**.
Search `reserve margin`: the card is not listed. Note both times.

4e. **P3: rebuild, publish, and check the rebuilt index.**

Where: the same window
```bash
uv run debate-research tub index build --caselist testcl26
uv run debate-research tub index publish --env dev --newest
INDEX_DIR=$(ls -td "${DEBATE_STORAGE__DATA_DIR}/tub-index"/*/ | head -1)
echo "$INDEX_DIR"
sqlite3 -readonly "${INDEX_DIR}search-index.sqlite" "select count(*) from occurrences where source_sha256 = '${REMOVED}'"
```
Success looks like a new index id, published, and `0`. Five minutes after the publish, the card's
path answers again, with no Westfield XY line.

4f. **P4: the prune**, exactly as `docs/runbooks/caselist-removal.md` gives it ("P4 — Delete the
superseded index versions"): its dry-run block, then its delete block, then the dry run again. They
need the grant from block 1. Success looks like `would delete` lines for the dev index versions the
synthetic one superseded, noncurrent ones included, and the `keeps` line naming 4e's index id. Then
`0` per request file, the `pruned; kept` line, and a second dry run printing `0 version(s) of 0
key(s) to delete`.

Paste back everything from 4a's import onwards, with the times from 4b to 4d.

**5. The app and audit log scan, then dev's own index back** (expected runtime ~2 min). This reads
what 3 and 4 made the function log, for the school, team code and query words used, and the audit
records' shape. Then it republishes dev's own newest index, which the prune left in place on your Mac
(it deletes only bucket objects).

Where: the same window
```bash
export AWS_PROFILE=debate-admin
SINCE=$(( ($(date +%s) - 7200) * 1000 ))
for WORD in Westfield XY reserve margin Okonkwo testcl26 '"q="'; do
  echo "== $WORD: $(aws logs filter-log-events --region us-east-1 --log-group-name debate-dev-tub-app --start-time "$SINCE" --filter-pattern "$WORD" --query 'length(events)' --output text)"
done
aws logs filter-log-events --region us-east-1 --log-group-name debate-dev-tub-audit --start-time "$SINCE" --query 'events[-6:].message' --output text
unset AWS_PROFILE DEBATE_STORAGE__DATA_DIR X REMOVED
aws sso login --profile debate-dev-evidence
DEBATE_ENV=dev debate-research tub index publish --env dev --newest
unset DEBATE_ENV
BUCKET=$(aws s3api list-buckets --profile debate-dev-evidence --query 'Buckets[?starts_with(Name, `debate-dev-evidence-`)].Name' --output text)
echo "republished: $(aws s3 cp "s3://${BUCKET}/reports/tub/search/current.json" - --profile debate-dev-evidence | python3 -c 'import json, sys; print(json.load(sys.stdin)["index_id"])')"
ls -td "${HOME}/.debate-research/dev/tub-index"/*/ | head -1
```
Success looks like `0` after every word, and audit lines holding only `action`, `actor_role`,
`actor_subject`, `cards` or `count`, `format_version` and `time`: `searched` with a `count`, and
`card-viewed` with one `testcl26/<64 hex>`. Then the publish table, a `republished: <index id>` line,
and the newest local index directory, whose name is that same index id: dev's own index is current
again.

**6. For the PM's promotion list (prod, after the merge).** Apply the grant to prod as
`evidence-store.md` gives it, from a worktree whose `owner.auto.tfvars` prints `3` for
`grep -c evidence_search`. A plan that destroys an account assignment means stop. **Before the pilot
opens in prod**, run the evidence-search runbook's "The list must exist before anyone searches"
check. If prod has no suppression list, the function refuses every search there until the runbook's
create command has run. `v1-e39-t10` exercises the removal steps on prod.

## The operator's dev run

### Block 1 — the dev apply (2026-10-22)

**The plan was `1 to add, 4 to change, 0 to destroy`, not the `0 to add, 2 to change` block 1
expected.** I stopped and asked. Its five resources, read from the pasted plan:

| Resource | Change | From |
|---|---|---|
| `module.evidence_store.aws_ssoadmin_permission_set.evidence_removal[0]` | description names `reports/tub/search/` | this task |
| `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_removal[0]` | `ListBucketVersions` condition gains `reports/tub/search/` and `reports/tub/search/*`; new statement `DeleteSupersededSearchIndexVersions` (`GetObjectVersion`, `DeleteObject`, `DeleteObjectVersion` on `reports/tub/search/*`) | this task |
| `module.evidence_search.aws_cognito_user_group.email_second_factor` | created | `v1-e39-t05` (#371), its operator follow-up C |
| `module.evidence_search.aws_ssoadmin_permission_set_inline_policy.accounts[0]` | gains `cognito-idp:AdminRemoveUserFromGroup` | `v1-e39-t05`, its operator follow-up C |
| `module.evidence_store.aws_ssoadmin_permission_set_inline_policy.evidence_operator[0]` | its `ListBucket` condition gains `reports/tub/search/` and `reports/tub/search/*`; its `ListBucketVersions` statement is unchanged | `v1-e39-t02` (#368), its operator follow-up 2 |

Nothing is destroyed and no `aws_ssoadmin_account_assignment` is touched. The everyday credential's
version listing is unchanged, as the grant-scope test says.

**PM ruling, 2026-10-22: A, apply the plan as it stands.** So this apply also closes, in dev,
`v1-e39-t05`'s operator follow-up C (the `email-second-factor` group and
`AdminRemoveUserFromGroup`) and `v1-e39-t02`'s operator follow-up 2 (the operator's listing grant on
`reports/tub/search/`). The PM records them against those tasks; their prod applies stay on the
promotion list. **A discrepancy, noted at the PM's request:** `v1-e39-t06`'s ac4 step 1 reported
`No changes` for `v1-e39-t02`'s grant on 2026-10-21, most likely because the `dev-preview`
worktree it planned from was not current. It changes nothing now.

Before applying, `terraform show` of the saved plan listed exactly those five resources and
`Plan: 1 to add, 4 to change, 0 to destroy.` Apply result: **`Apply complete! Resources: 1 added,
4 changed, 0 destroyed.`** The outputs name `evidence_removal_permission_set_name =
"DebateDevEvidenceRemoval"` and `evidence_bucket_name = "debate-dev-evidence-a7508de8"`.

### Block 2 — the dev deploy (2026-10-22)

`scripts/tub_deploy.sh dev` pushed `debate-dev-tub@sha256:b43d7462bbdf…`, pointed the function at it
by digest, and `/healthz` through CloudFront answered `{"status":"ok"}`. `Deployed
f8545cc7cc650841ba055982a2a22504b5f7bde3 to dev`, the branch's head at the time; the commits after it
change this report only.

### Block 3 — the deployed exposure checks, dev (2026-10-22)

**Signed-in responses**, read from a HAR the operator saved in Chrome while signed in (the
operator's own dev account, a coach). I read only each request's status, method, path and two
response headers; no cookie, token or body. Every document was **`200`, `cache-control: private,
no-store`, `x-cache: Miss from cloudfront`**: `/` (twice), `/search?q=…`, a card page
(`/cards/hspolicy26/ee37e841…`) and `/account`. The only other response, the content-hashed
`/static/ec32aeae1d1518e4/app.js`, was `public, max-age=31536000, immutable`, as ADR-0019 (a) 5
intends. It holds no data.

**Without a session** (curl): `/`, `/search?q=reserve` and `/account` answered `302` to sign-in,
and `/signed-out` and `/healthz` answered `200`. All five were `private, no-store` and `Miss from
cloudfront`. Two first attempts to send the copied cookie with curl failed: once on whitespace
(curl error 43), once on a value that was not the cookie (a `302`). Block 3 now strips whitespace,
and the signed-in reading came from the HAR instead.

**The bucket, the edge and the function** (`debate-admin`, read only):

| Check | Result |
|---|---|
| Block Public Access, all four flags | `True True True True` |
| Bucket policy status `IsPublic` | `False` |
| ACL grants to a group URI (public or authenticated users) | none |
| Anonymous `GET` of `reports/tub/search/current.json` and of the suppression list | `403`, `403` |
| Unsigned request to the function URL | `403` |
| CloudFront standard logging, real-time log config, origins | `False None 1` |
| CloudWatch log deliveries (vended logs) | none |
| Dev suppression list | exists: 1,239 bytes, `aws:kms` |

## Follow-up work

1. **`tub index prune` (p3).** The PM's ruling names it: a CLI command that does the runbook's P4
   prune (read the pointer, keep the current index and pointer, list-first dry run, delete) instead of
   a pasted script. E39 or its V2 successor (E35).
2. **Prod's suppression list.** Whether prod has `manifests/_suppression/suppression-list.jsonl`
   decides whether the prod pilot can answer a search at all (Decisions). It belongs on `v1-e39-t10`'s
   checklist before the student pilot, beside the removal exercise.
3. **Path holds on the function** (V2, E35). The tub's takedown flow reads the same list. If a
   removal that only holds a path should be hidden live, the index would need each occurrence's path
   digest and the role a read of `path-holds.jsonl`. The pilot covers it with an immediate rebuild.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-22

**Notes:**

Accepted, on one condition closed in this session before the pull request: the operator's dev run
(blocks 1 to 5), with the two corrections below. Record the outputs, set the Goal `Succeeded`, and
open the pull request with no `--partial`, since v1-e39-t08 depends on this task. As before, if
anything comes out differently from what you expect, stop and ask for another review.

**Two corrections to the operator blocks, before they are handed over:**

1. **Block 1's `owner.auto.tfvars`.**
   * The main clone has no `infrastructure/envs/dev/owner.auto.tfvars`, so the `cp` fails. The
     checkout that last applied dev is the **dev-preview** worktree
     (`../dev-preview/infrastructure/envs/dev/owner.auto.tfvars`). Copy from there.
   * Its `grep -c evidence_search` prints **`2`**: the deployer and accounts lines, with no budget
     emails line. Dev's last plan with that file was `No changes`, so `2` is right for dev. Expect
     `2`, not `3`.
   * The PM corrects the evidence-search runbook's "must print 3" in the next batch, to "names the
     deployer and accounts lines".
2. **Block 4 waits until the weekly agent run started on 2026-10-22 has finished.** That run's
   search-index stage may publish a new dev index. If it lands during the exercise, it replaces the
   synthetic pointer, and P1 to P3 read the wrong index.
   * Block 4 starts with a check that no `caselist pull` is running
     (`pgrep -f 'caselist pull'` prints nothing).
   * Block 5's republish says which index id it put back. It should be the newest real dev index
     (the agent's, if it built one), not the synthetic one.

**What is good:**

* **The suppression re-read sits in the holder's `_refresh`, before the pointer.** Every route
  reaches the index only through `lease()`'s `ScreenedSearch`, so a download built later cannot skip
  the list. ac1 and ac7 were red first, at 4:59 and 5:00.
* **A list that cannot be read refuses, while a pointer that cannot be read serves.** ADR-0019 says
  an environment never serves a stale list, and you kept those two failures apart deliberately. Your
  catch that the function, lacking `s3:ListBucket`, sees a missing list as `AccessDenied` is what
  makes the prod check (block 6) necessary.
* **The audit record is a schema, not a convention.** It has a committed JSON Schema with
  `additionalProperties: false`, and a `FakeAuditSink` that validates every record any `debate_api`
  test writes (566 tests). The forbidden values are checked for all 16 actions as their real writers
  build them.
* **ac3's journey was shown failing** on a planted `debug("searched %s", query)`, and the logs are
  captured from bare loggers in one process. That is working agreement 10's new rule, followed.
* **The prune is tested from the runbook's own text,** and the mutant that deletes the current
  `current.json` is caught. The Terraform mutants were re-read to confirm which `run` failed.
* **The gate table (ac5) maps all ten items,** with the known limit on path holds stated beside
  item 5, as ruled.

**Rulings on the rest:**

* **Deviations 1 to 3: accepted.** That covers the S3 adapter's list read and the test bucket, the
  ac4 amendment, and downloads covered by construction. v1-e39-t08 adds the download's own
  suppression test, and the PM's next batch says so in its spec.
* **Decisions: accepted.**
  * No record for a card not found or hidden.
  * `card-viewed` for the card page only.
  * The reused 503 sentence.
  * The browser harness's `Sec-Fetch-Site`, set only for the pilot's own origin.
  * The in-process sign-in.
  * The prune keeping the whole current directory.
  * `RM-2026-91`.

**Follow-ups, placed by the PM:**

* **1 (`tub index prune`):** a p3 task in the next batch.
* **2 (prod's suppression list):** on the promotion list, run before the pilot opens on prod, and
  added to v1-e39-t10's checklist beside the prod removal exercise.
* **3 (path holds on the function):** recorded for V2 (E35).
* **Gate item 6 changes with policy 1.11.** The coach has ruled that copies, downloads and built
  files carry no provenance line. The PM's next batch amends the policy, ADR-0019 and the gate
  table's item 6 together. Nothing changes in this task.
