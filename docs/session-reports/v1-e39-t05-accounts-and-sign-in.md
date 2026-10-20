# Session report: v1-e39-t05-accounts-and-sign-in

| | |
|---|---|
| Task | `v1-e39-t05-accounts-and-sign-in` — Accounts and sign-in: the session flow, roles, and the coach's tub users commands |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t05-accounts-and-sign-in.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t05-accounts-and-sign-in.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t05-accounts-and-sign-in` |
| Session status | COMPLETE: every criterion PASS, ac5 on the operator's first dev run; the Goal is `Succeeded` (corrected after ruling (d), 2026-10-20) |

## Summary

The pilot now has ADR-0019 (d)'s sign-in, built as the PM's notes set out. In `debate_api`:

- **The flow:** the authorization-code flow with PKCE (`S256`), which the app enforces itself. The
  callback checks `state`, the transaction's five-minute life and the OIDC `nonce`, and checks the
  ID token's RS256 signature, issuer, audience, expiry and use.
- **The session:** an AES-GCM `__Host-` cookie that also authenticates its own name. Its lifetimes
  are ADR-0019's: one idle hour, twelve hours absolute, revalidation at most every five minutes.
- **CSRF:** a synchronizer token in `X-CSRF-Token`, plus `Origin` and `Sec-Fetch-Site` checks.
- **The gate:** exactly four session-free routes, enforced when a route is registered. No session
  until an authenticator is registered, through the app's own enrolment page, except for an
  `email-second-factor` account with a verified email.
- **The account page:** add, verify and remove the backup email; for a new phone, it sends the
  student to the coach for a reset, as there is no self-service replacement in the pilot (corrected
  after ruling (d), 2026-10-20).
- **The script:** the one first-party `/static/<hash>/app.js`, which sends every POST with the body
  hash and the CSRF header.

The rules and use cases are in `debate_core.application.tub`. The adapters are in
`debate_core.integrations`: `cognito`, `cloudwatch_audit` and `parameter_store`. `debate_api`
moves to the direct boto3 contract, as ADR-0019 says. The coach gets `debate-research tub users
add|list|reset|disable|enable|remove|email-second-factor`. The `evidence_search` module gains the
`email-second-factor` group and `AdminRemoveUserFromGroup`, and its test now lists TubAccounts'
Cognito actions exactly. There is a guide for the coach and students, and the runbook's step 10
now uses `tub users add`.

**For the PM to look at first:** the package-list deviation, which is recorded in the spec
([Deviations](#deviations-from-the-spec) 1), and the whole-selection test run left to CI because
the package pyprojects changed ([Checks](#checks-run)). ac5 is NOT RUN: it is the operator's dev
run, and its block is under [Operator follow-ups](#operator-follow-ups). The Goal stays
`InProgress` until that run is recorded.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `sign-in` (Accounts and sign-in) | Done | Node criterion PASS (480 passed). Goal criteria ac1–ac4 and ac6 PASS; ac5 NOT RUN (operator) |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| Node `sign-in`: sign-in and account tests pass | PASS | `uv run pytest packages/debate_api/tests packages/debate_cli/tests -k "auth or session or tub_users"` → `480 passed in 4.70s` |
| ac1: the authorization matrix (both roles; valid, expired, tampered or absent session): only the health check and the callback answer without a session, and coach routes refuse a student | PASS | See note 1 below. `uv run pytest packages/debate_api/tests/test_auth_authorization_matrix.py` → `193 passed` |
| ac2: the callback refuses a mismatched state or PKCE verifier, and an ID token from another pool or client, by tests with locally signed tokens | PASS | See note 2 below. `uv run pytest packages/debate_api/tests/test_auth_callback.py` → `29 passed`; `packages/debate_core/tests/integrations/cognito/test_cognito_adapters.py` → `44 passed` |
| ac3: `tub users` calls the pool's administrator API with the expected parameters (stubbed), never shows a password except `add`'s and `reset`'s one display, and refuses an email-shaped username | PASS | See note 3 below. `uv run pytest packages/debate_cli/tests/commands/test_tub_users.py` → `81 passed` |
| ac4: `docs/guides/evidence-search-accounts.md` walks the coach and a student through first sign-in, TOTP, the backup email and a reset; the two docs checks pass | PASS | The guide covers each in its own section. `uv run scripts/check_command_blocks.py` → `OK: no # comments in 320 shell code blocks in 126 Markdown files`; `uv run scripts/check_links.py` → `OK: 1847 relative links and anchors in 269 Markdown files` |
| ac5: on dev, the operator signs in as a synthetic user, enrols TOTP, signs out, and a reset forces enrolment again | NOT RUN | It needs the operator's AWS credentials, a deploy and a phone. The block is under [Operator follow-ups](#operator-follow-ups) A, with what success looks like at each step |
| ac6 (PM amendment): exactly four session-free routes; no session without an authenticator unless `email-second-factor` with a verified email; the account page adds, verifies and removes the email and replaces the authenticator; a disabled account's session ends within five minutes; each shown failing first | PASS | See note 4 below |

**Note 1, ac1.** The matrix runs every route the app serves (13 method and path pairs; a test fails
if a route is added without a row) for a student and a coach. Each runs with a valid session and six
others:

- **expired:** twelve hours since sign-in;
- **idle:** an hour since the last request;
- **tampered:** one ciphertext character changed;
- **foreign keys:** sealed under keys the app does not hold;
- **another cookie:** a session's fields sealed as the sign-in cookie;
- **absent.**

ac1's text names `/healthz` and the callback. ac6's PM amendment widens that to the four
session-free routes, and the matrix checks the four.

**Note 2, ac2.** The callback tests run the real `CognitoOAuthClient` and `CognitoIdTokenVerifier`.
The ID tokens are RS256, signed with keys generated for the run. The callback refuses:

- a mismatched or missing `state`, a browser that started no sign-in, an answer after five minutes,
  managed login's `error`, and a reused code;
- **PKCE:** a code issued for another browser's challenge;
- **the ID token:** from another pool (`iss`), for another client (`aud`), expired, an access token
  (`token_use`), for another sign-in (`nonce`), with no subject, signed by an unpublished key, naming
  the pool's key but signed by another, claims altered after signing, and `alg` `none` or `HS256`.

**Note 3, ac3.** The real command, container and adapters run against boto3 clients under botocore's
`Stubber`, which asserts every call's parameters. Each command is checked:

- `AdminCreateUser` with `MessageAction=SUPPRESS`;
- the groups;
- the reset sequence;
- sign-out before disable and remove;
- the `email-second-factor` group;
- `ListUsers` asking for `sub` alone;
- one `PutLogEvents` to `tub-users` per command, whose record carries the subject and no name.

**Passwords.** The password sent appears exactly once, in `add`'s and `reset`'s stdout or `--json`
data. It is never in stderr, `--verbose`, an error or a `DEBUG` log, and no other command shows
one.

**Names refused before any call:** nine of them across six commands, including two email shapes,
capitals, 2 and 33 characters, `_`, `-`, a space and the empty name.

**Note 4, ac6.** Each part is tested:

- **four session-free routes:** `test_exactly_four_routes_are_session_free`, and
  `test_no_other_route_can_be_registered_as_session_free` (six paths);
- **no session without an authenticator:** `test_auth_enrolment.py`, 17 passed;
- **the account page:** `test_auth_account_page.py`, 20 passed;
- **the disable bound:** `test_a_disabled_accounts_session_ends_within_five_minutes`. The session
  is still valid at 4:59 after the disable and over at 5:00. The test file is
  `test_session_lifetimes.py`, 26 passed.

**Shown failing first:** the red run (340 failed against a refuse-nothing skeleton) and 23 of 23
mutants caught, under [Shown failing first](#shown-failing-first).

### Shown failing first

**The red run.** The skeleton is this branch's source at `4dda1f0` with every refusal taken out
and every signature kept, built in the scratchpad with `git archive HEAD` and run first on
`PYTHONPATH` (`debate_api.access.__file__` printed the scratch copy). It differs from the tested
code in these ways:

- any name is a username;
- every session, transaction and enrolment is current, and any return path is kept;
- the callback checks no state, nonce or role;
- every account gets a session, and revalidation trusts the session;
- the account page accepts any email and code, and lets the last second factor go;
- the ID token's claims are believed unchecked;
- the cookie's name is not authenticated;
- the placeholder keys are accepted;
- the gate refuses nothing, and any route may be session-free.

This is the honest limit of the evidence: the skeleton was made from the finished code, after the
tests were written, rather than before the implementation. Command:

```bash
uv run --frozen pytest packages/debate_api/tests packages/debate_cli/tests/commands/test_tub_users.py packages/debate_core/tests/application/tub -q -p no:cacheprovider -rf
```

Result: `340 failed, 185 passed, 2 errors in 8.83s`.

| File | Failed on the skeleton | Passed on it, and why |
|---|---|---|
| `test_auth_authorization_matrix.py` | 117 | 76: the session-free routes answering without a session, and valid sessions reaching their routes. These are "must still answer" cases |
| `test_auth_callback.py` | 29 | 0 |
| `test_auth_csrf.py` | 57 | 9: GET is 405 on POST routes, the page carries the token, no CORS headers, sign-out and `/signed-out` clear the cookies |
| `test_auth_enrolment.py` | 17 | 0 |
| `test_session_lifetimes.py` | 16 | 10: activity keeps a session alive, no early refresh, rotation's previous key, cookie size, and five key-shape refusals the skeleton kept (it removed only the placeholder refusal) |
| `test_auth_account_page.py` | 10 | 10: the happy paths (add, verify, remove, replace) |
| `test_auth_pages_and_script.py` | 1 | 15: rules about the script and headers that no refusal touches. The 2 errors are the `pages` fixture, which signs an enrolling account in, failing in setup. They are not counted as red |
| `test_tub_users.py` | 54 | 27: each command's happy path and its exact parameters |
| `test_tub_rules.py` | 39 | 36: valid usernames, roles, secrets' reprs, passwords, the audit shape, and call order |

**Mutants.** 23 mutants, each applied alone to the committed tree. Each was run against
`packages/debate_api/tests`, plus `test_tub_rules.py` where it touches a lifetime or the decision.
Each run used `-n 0`, a fresh `HYPOTHESIS_STORAGE_DIRECTORY` (none of these tests use Hypothesis),
and the file was restored byte for byte. `git status --porcelain` was empty after every batch.

| Mutant | Result | First test to catch it |
|---|---|---|
| Unclaimed paths are public | CAUGHT (1) | `test_a_path_no_route_claims_needs_a_session_too` |
| Any route may be registered session-free | CAUGHT (6) | `test_no_other_route_can_be_registered_as_session_free` |
| `/static` prefix without its slash | CAUGHT (1) | `test_a_path_no_route_claims_needs_a_session_too` |
| Coach routes open to students | CAUGHT (2) | `test_with_a_valid_session_every_route_answers_and_coach_routes_refuse_a_student` |
| A pending enrolment opens every page | CAUGHT (6) | `test_a_pending_enrolment_opens_no_page_but_the_authenticator_page` |
| An ended session is kept | CAUGHT (46) | the matrix's expired and idle rows |
| `Origin` not checked | CAUGHT (20) | `test_a_forged_state_changing_request_is_refused_before_the_route_runs` |
| `Sec-Fetch-Site` not checked | CAUGHT (20) | the same |
| CSRF token not compared | CAUGHT (16) | the same |
| POST treated as a safe method | CAUGHT (119) | the matrix and the CSRF tests |
| Cookie name not authenticated | CAUGHT (148) | the account page and the matrix |
| `state` not compared | CAUGHT (1) | `test_a_mismatched_state_is_refused` |
| `nonce` not compared | CAUGHT (1) | `test_an_id_token_that_fails_a_check_is_refused[for another sign-in]` |
| The transaction lasts five minutes inclusive | CAUGHT (2) | `test_an_answer_after_five_minutes_is_refused` |
| An account with no role becomes a student | CAUGHT (1) | `test_an_account_in_no_role_group_is_not_signed_in` |
| The email fallback without a verified email | CAUGHT (2) | `test_an_email_second_factor_account_without_a_verified_email_must_enrol` |
| A verified email suffices outside the group | CAUGHT (4) | `test_a_verified_email_alone_is_not_enough_outside_the_group` and others |
| ID-token audience not checked | CAUGHT (1) | `...[for another app client]` |
| ID-token issuer not checked | CAUGHT (1) | `...[from another pool]` |
| ID-token signature not verified | CAUGHT (2) | `test_an_id_token_naming_the_pools_key_but_signed_by_another_is_refused` |
| ID-token expiry not checked | CAUGHT (1) | `...[already expired]` |
| ID-token use not checked | CAUGHT (1) | `...[an access token]` |
| Revalidation every ten minutes | CAUGHT (10) | `test_after_five_minutes_the_refresh_token_is_redeemed_again` |

The signature mutant first did not apply: the formatter had wrapped the line. The driver reported
it as `DID NOT APPLY` rather than counting it. It was rewritten and run alone, and was caught.

**Terraform.** The two new assertions were broken three ways in `evidence_search`, and each run
failed for its reason (`15 passed, 1 failed`):

- `AdminRemoveUserFromGroup` removed;
- an extra `AdminListDevices` added;
- the group renamed `email-fallback`.

Restored, the module gave `16 passed, 0 failed`.

## Checks run

`uptime` load was 4 to 10 throughout.

| Check | Command | Result |
|---|---|---|
| The affected set | `uv run scripts/affected_tests.py` | `The whole selection is affected: packages/debate_api/pyproject.toml is shared test ground.` Not run, per working agreement 10 and the PM's note: the PR's CI runs it |
| What the session changed | `uv run pytest packages/debate_api/tests` | `371 passed` |
| | `uv run --frozen pytest packages/debate_cli/tests` | `822 passed in 29.23s` (the whole directory: its container and command registry changed) |
| | `uv run pytest packages/debate_core/tests/application/tub packages/debate_core/tests/integrations/cognito` | `119 passed` |
| | `uv run --frozen pytest tests/architecture tests/specs` | `182 passed` (the import-contract test's new cases included) |
| | `uv run --frozen pytest tests/scripts/test_tub_deploy.py tests/scripts/test_affected_tests_planted_breaks.py tests/architecture/test_thin_handlers.py tests/scripts/test_stamp_build.py tests/smoke/test_cli_smoke.py` | `91 passed` |
| Formatting and lint | `uv run ruff format --check .`, `uv run ruff check .` | exit 0, exit 0 |
| Types | `uv run pyright packages/debate_api packages/debate_cli packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| Import contracts | `uv run lint-imports` | exit 0: `Contracts: 12 kept, 0 broken` |
| Thin handlers | `uv run scripts/check_thin_handlers.py` | exit 0; the thickest new handler is `callback`, at 15 statements |
| Specs | `uv run scripts/validate_specs.py` | `OK: 394 files, 39 epics, 334 tasks, 21 releases` |
| Docs | `check_command_blocks.py`, `check_links.py`, `docs_index.py --check-descriptions` | all exit 0. `docs_index.py --check` reports `docs/README.md` stale for this guide and for v1-e39-t04's runbook: the post-merge workflow regenerates it, and CI runs `--check` only on pull requests into `main` |
| Terraform | `bash scripts/terraform_checks.sh` | Stopped by the 110 s alarm after `fmt` and every `validate` printed `ok`. It goes to the operator (follow-up B) |
| | `terraform -chdir=infrastructure/modules/evidence_search test` | `Success! 16 passed, 0 failed.` (1.9 s) |
| | `tflint --chdir=infrastructure/modules/evidence_search`; `terraform fmt -check -recursive infrastructure/modules/evidence_search` | exit 0; exit 0 |

**One slip.** Commit `e498f67` went in with two pyright errors in `test_tub_users.py`, because I
piped pyright to `tail` in the same command as the commit. `cf4d930` fixes them. Every check
recorded above was run bare and its exit status read.

## Files changed

- **`packages/debate_core/src/debate_core/application/tub/`** (new) and
  **`application/ports/tub.py`**: the rules and use cases.
  - `identity`: usernames, roles, and the temporary password and authenticator secret, which print
    as placeholders.
  - `audit`: the record.
  - `sessions`: the session, the sign-in transaction, the pending enrolment and the lifetimes.
  - `sign_in`: `SignInService`.
  - `account_page`: `AccountPageService`.
  - `accounts`: `AccountAdministration`, which is `tub users`.
  - The ports: `AccountDirectory`, `IdentityProvider`, `AccountSelfService` and `AuditSink`.
- **`packages/debate_core/src/debate_core/integrations/`**: three new adapters.
  - `cognito`: the administrative and token-authorized APIs, the OAuth endpoints over `urllib`, and
    RS256 ID-token checks with `cryptography`.
  - `cloudwatch_audit`.
  - `parameter_store`.
- **`packages/debate_api/`**: everything the app does.
  - `access`: the gate and CSRF.
  - `routes`: the routes, and `ROUTE_ACCESS`.
  - `cookies`, `configuration`, `state`, `errors`, `pages`, `container` and `app`.
  - The `templates/` and `static/app.js`; the README.
  - `pyproject.toml`: `cryptography`, `debate-core[aws,tub]`, `jinja2` and `segno`.
- **`packages/debate_cli/`**: the commands and their wiring.
  - `commands/tub_users.py`, and the `tub users` group in `commands/__init__.py`.
  - `container.tub_account_administration`.
  - `pyproject.toml`: the `tub` extra.
- **`packages/debate_core/pyproject.toml`**: the new `tub` extra, which holds `cryptography`.
- **Root `pyproject.toml`:**
  - the dev group gains `httpx2` and the `cognito-idp`, `logs` and `ssm` stubs;
  - in the import contracts, `debate_api` moves to the direct boto3 form, the new adapters join
    the httpx and document-library lists, and `debate_api.container` becomes a composition root.
- **`uv.lock`**: relocked. It adds `segno`, `httpx2` (with `httpcore2` and `httpx2-jsfetch`),
  `truststore` and the three stub packages.
- **Tests:**
  - `packages/debate_api/tests/`: a `conftest.py` world and seven `test_auth_*` and `test_session_*`
    files, which replace `test_pilot_placeholder_app.py`;
  - `packages/debate_cli/tests/commands/test_tub_users.py`;
  - `packages/debate_core/tests/application/tub/` and `integrations/cognito/`;
  - updates to `test_app.py`, `test_installation.py` and `test_doctor.py` (the new service, the
    wired integrations and the extra), `tests/architecture/test_import_contracts.py` (the renamed
    contract and a second API probe) and `tests/scripts/test_stamp_build.py` (the extra).
- **`infrastructure/modules/evidence_search/`**:
  - `user_pool.tf`: the `email-second-factor` group;
  - `pilot_access.tf`: `AdminRemoveUserFromGroup`;
  - `tests/evidence_search.tftest.hcl`: TubAccounts' Cognito actions listed exactly, and the
    group.
- **Docs:**
  - `docs/guides/evidence-search-accounts.md`: new.
  - `docs/runbooks/evidence-search.md`: step 10 through `tub users add`. Steps 8, 11e and 12 now
    expect the redirect to managed login, and step 6 warns that the app refuses the placeholder
    keys.
- **The spec:** `constraints.packages`, below.

## Deviations from the spec

1. **The package list.** The spec's `constraints.packages` omitted paths that ADR-0019's code
   placement and the PM's notes need. I wrote them into the spec, with a comment for each:
   - `infrastructure/modules/evidence_search`: the PM's amendment.
   - `docs/runbooks`: the PM's notes say to update step 10.
   - `debate_core.integrations`: "Where the code goes" puts the `cognito` and `cloudwatch_audit`
     adapters there.
   - `packages/debate_core/tests`: those adapters' and the rules' tests.
   - `tests/architecture`: the contract `debate_api` moves to is named in
     `test_import_contracts.py`.
   - `tests/scripts`: `test_stamp_build.py` pins the CLI's extras.

   `packages/debate_core/pyproject.toml` gained the `tub` extra. I read the spec's
   `pyproject.toml` entry as covering it, but it is not certain, so the PM should rule.
2. **A `/coach` route.** ac1 asks that coach routes refuse a student, and this task had none, so I
   added a minimal coach-only page. It says where accounts are managed. `v1-e39-t06` or `t07` may
   give it real content.
3. **`tub users enable`.** The ADR calls `disable` "the reversible form", and TubAccounts already
   held `AdminEnableUser`, so the undo is a command of its own.
4. **Revalidation re-reads the account.** Every five minutes the app redeems the refresh token, as
   ADR-0019 says. It also calls `GetUser` and ends the session if the account no longer has a
   second factor it may sign in with. Without that, the coach withdrawing `email-second-factor`
   would not end an email-only session, and "no session without an authenticator" would hold only
   at sign-in. The cost is one extra Cognito call per session every five minutes.
5. **The runbook beyond step 10.** Steps 8 and 11e expected `200` and the placeholder's title for
   `/`, and step 12 expected the placeholder page on a Chromebook. After this deploy, all three get
   a redirect to managed login, so I changed their expected output. Step 6 now says the app refuses
   the placeholder keys.
6. **No smoke check.** `plan_specs/README.md` asks a task that changes a user-facing surface to add
   `tests/smoke/` checks, and this spec has no node for one. I added none; see Follow-up work.

## Decisions and assumptions

- **The enrolment cookie lasts 15 minutes.** ADR-0019 sets no lifetime for the state between
  sign-in and an enrolled authenticator. The cookie holds the subject, the role, a CSRF token and
  the refresh token, and opens only the authenticator page and sign-out. Fifteen minutes is long
  enough to install an app, and the absolute lifetime counts from sign-in.
- **The app does not check `x-amz-content-sha256` itself.** Lambda refuses a POST without it before
  the function runs (ADR-0019 (a) 3). I did not confirm that the header reaches the app through the
  Web Adapter, and an app-side check that failed on every POST in AWS was a worse risk than the
  missing duplicate. `app.js` sends it, and a test reads the script for it.
- **`GET /account/authenticator` calls `AssociateSoftwareToken`.** The ADR describes the enrolment
  *page* rendering the QR code. Association makes a pending secret that changes nothing until
  `VerifySoftwareToken`, which is a POST with CSRF.
  - **Assumption:** that is Cognito's documented behaviour, and the account page's copy relies on
    it ("your old one keeps working until you confirm"). I could not exercise it offline. The
    operator's block includes a check of it (A, step 4).
- **The pool id comes from `--pool-id` or `TUB_USER_POOL_ID`.** Finding the pool by name needs
  `ListUserPools`, which cannot be scoped to one pool, and TubAccounts holds nothing on `*`. A prod
  profile given the dev pool's id is refused by IAM before anything changes.
- **The `tub` extra holds `cryptography` only.** The adapters take boto3 from `aws`. That keeps
  each distribution in one extra, which is how `debate_cli.installation` names the extra a missing
  module needs, and it keeps the existing drop-an-extra tests meaningful.
- **Usernames with capitals are refused, not folded**, so the name the coach typed is the name the
  student types.
- **Temporary passwords** are 4 groups of 4 from 31 unambiguous characters (about 79 bits), 19
  characters in all, which the pool's 12-character rule accepts.
- **Audit records** carry `actor_subject` (none for the coach's command line) and
  `account_subject`. Neither is a name. `v1-e39-t07` may rename the fields when it adds access
  records.
  - **Failed audit writes:** if the record cannot be written, the command fails with exit 3 after
    the change, and `add` and `reset` do not print the password. The coach runs `reset` once AWS
    answers. The guide says so.
- **The app writes its audit records** to one stream per execution environment, created on first
  write. The function's role already allows `CreateLogStream` on its audit group.
- **The function's role is unchanged**, as the PM said. Everything the app calls is covered:
  - the two parameters, by `ssm:GetParameter`;
  - the audit group, by its log grants;
  - the token-authorized Cognito calls, which go through an **unsigned** client, so no IAM policy
    is involved;
  - the OAuth endpoints, which take the client secret;
  - the key set, which is public.
- **botocore logs request parameters at `DEBUG`**, the temporary password included. Nothing in the
  CLI or the function turns that logger on, so nothing reaches a log. A test confirms nothing the
  commands do appears in a `DEBUG` capture.
- **The test world** runs the real app, use cases, OAuth adapter and verifier. Only managed login's
  HTTPS (a fake transport) and the token-authorized API stand in. RSA keys are generated once per
  run, which took the matrix from 17 s to 0.7 s.

## Operator follow-ups

**A. ac5: the dev check** (expected runtime ~15 min, most of it in the browser)

This is one sequence, run in order, from the task worktree. It needs Docker Desktop running and
your phone. The synthetic account is removed at the end. **Never paste a temporary password, a
password or a code back into the session**; paste the other lines.

1. Deploy this branch to dev, and check that the pilot now sends a request without a session to
   managed login.

   **Operator command** (expected runtime ~4 min)
   Where: your Mac, in the task worktree
   ```bash
   cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t05-accounts-and-sign-in
   uv sync --all-packages
   aws sso login --sso-session debate
   scripts/tub_deploy.sh dev
   curl -sS -o /dev/null -w '%{http_code} %header{cache-control}\n' https://tub.dev.wfbdebate.com/
   curl -sS -o /dev/null -w '%{redirect_url}\n' https://tub.dev.wfbdebate.com/ | cut -d '?' -f 1
   ```
   Success looks like the deploy ending `Deployed <sha> to dev: https://tub.dev.wfbdebate.com/` after
   `{"status":"ok"}`, then `302 private, no-store`, then
   `https://auth.tub.dev.wfbdebate.com/oauth2/authorize`. If `/healthz` never answers, the app
   refused to start. Check `aws logs tail debate-dev-tub-app --profile debate-admin --region
   us-east-1 --since 10m` for `CookieKeysNotSet` or `ConfigurationMissing`.

2. Make the synthetic account.

   **Operator command** (expected runtime ~1 min)
   Where: the same shell
   ```bash
   export TUB_USER_POOL_ID="$(aws cognito-idp list-user-pools --max-results 20 --profile debate-admin --region us-east-1 --query "UserPools[?Name=='debate-dev-tub'].Id" --output text)"
   echo "$TUB_USER_POOL_ID"
   uv run debate-research tub users add synthetic.student.one --role student --env dev
   ```
   Success looks like `us-east-1_` and letters and digits, then `Created synthetic.student.one
   (student).` and a temporary password shown once.

3. **Sign in and enrol TOTP.** In Chrome, open a new **Incognito** window and go to
   `https://tub.dev.wfbdebate.com/account`. Success looks like this:
   - the managed login page at `auth.tub.dev.wfbdebate.com`;
   - after the username and the temporary password, a page asking for a new password (use at
     least 12 characters);
   - an MFA setup step. Choose the **authenticator app**, scan the QR code, and enter the code;
   - you land on `https://tub.dev.wfbdebate.com/account`, which says *Signed in as
     synthetic.student.one* and *Your authenticator app is set up*.

4. **The account page.** On the same page, choose **Set up a new authenticator app**. Success looks
   like a page with a QR code, a typed-in setup key and a code box. **Do not scan it or confirm it.**
   Go back to *Your account*. This checks the assumption that beginning a new authenticator leaves
   the old one working; step 5's sign-in uses the old one.

5. **Sign out.** Choose **Sign out**. Success looks like `https://tub.dev.wfbdebate.com/signed-out`
   saying *You are signed out*. Then open `https://tub.dev.wfbdebate.com/` in the same window.
   Success looks like the managed login page asking for a username, not you signed straight back in.
   Sign in with the new password and **the code from the app you set up in step 3**. Success looks
   like *Signed in as synthetic.student.one*; that is step 4's check passing. Sign out again.

6. Reset the account.

   **Operator command** (expected runtime ~1 min)
   Where: the same shell
   ```bash
   uv run debate-research tub users reset synthetic.student.one --env dev
   ```
   Success looks like `Reset synthetic.student.one (student).` and a new temporary password.

7. **The reset forces enrolment again.** Open a new Incognito window, go to
   `https://tub.dev.wfbdebate.com/`, and sign in with the new temporary password. Success looks
   like a new-password page and then **the MFA setup step again** (a new QR code), not a request for
   the old app's code. Enrol, and success looks like *Signed in as synthetic.student.one*.
   Optionally, the old authenticator entry in your app no longer signs you in. Sign out.

8. Read the account changes from the audit log, then remove the synthetic account.

   **Operator command** (expected runtime ~1 min)
   Where: the same shell
   ```bash
   aws logs filter-log-events --profile debate-admin --region us-east-1 --log-group-name debate-dev-tub-audit --log-stream-names tub-users --query 'events[-2:].message' --output text
   uv run debate-research tub users remove synthetic.student.one --env dev
   ```
   Success looks like two JSON lines, `"action":"account-added"` and then `"action":"account-reset"`.
   Each has an `account_subject` and `"actor_role":"coach"`, and neither holds a username. Then
   `Removed synthetic.student.one. Any open session ends within five minutes.`

Paste back the output of steps 1, 2 (without the password), 6 (without the password) and 8, and a
line for each of steps 3, 4, 5 and 7: as described, or what you saw instead. I then record ac5 and
set the Goal to `Succeeded`.

**B. The full Terraform checks** (expected runtime ~3 min)

Here the script ran past the 110 s alarm after `fmt` and `validate` passed. The module's
`terraform test` and `tflint` passed on their own.

**Operator command** (expected runtime ~3 min)
Where: your Mac, in the task worktree
```bash
cd /Users/charlesclark/Documents/debate/debate-intelligence-tool/debate-intelligence-worktrees/v1-e39-t05-accounts-and-sign-in
bash scripts/terraform_checks.sh
```
Success looks like every line starting `ok` and a zero exit. If you have run `terraform init` in
this worktree's `envs/dev`, `validate` fails there on credentials. That is a known effect of the
saved backend, not of this change.

**C. Apply the module change, dev then prod, after the merge** (expected runtime ~2 min each)

The `email-second-factor` group and TubAccounts' `AdminRemoveUserFromGroup` exist only after an
apply. Until then, `tub users list` (which reads the group's members) and `tub users
email-second-factor` fail with `STORE_UNAVAILABLE`; ac5's steps do not use them. Follow the
runbook's *Before you start* (the checkout, `owner.auto.tfvars`, `debate-admin`), then:

**Operator command** (expected runtime ~2 min)
Where: the checkout holding the merged Terraform
```bash
cd "$WT"
export AWS_PROFILE=debate-admin
terraform -chdir=infrastructure/envs/dev apply
```
Read the plan first. It should be `1 to add, 1 to change, 0 to destroy`, all under
`module.evidence_search`: `aws_cognito_user_group.email_second_factor`, and
`aws_ssoadmin_permission_set_inline_policy.accounts[0]` gaining `AdminRemoveUserFromGroup`. Then
the same with `infrastructure/envs/prod`.

## Follow-up work

- **`v1-e39-t02`** registers `tub index` in the same `tub` group in `debate_cli/commands/__init__.py`.
  Whichever merges second gets a small conflict there, resolved by keeping both subgroups under one
  `tub` group.
- **`v1-e39-t06`** builds on this task:
  - it extends `static/app.js` for Copy card;
  - it adds its routes to `ROUTE_ACCESS` and rows to the matrix's `ROUTE_REQUESTS` (a test fails
    until both are done);
  - it can use `packages/debate_api/tests/conftest.py`'s `PilotWorld` for its signed-in tests.
- **`v1-e39-t07`** writes access records in `debate_core.application.tub.audit`'s shape, and may
  rename `actor_subject` and `account_subject` (format version 1).
- **Smoke checks for `validate-dev`.** A check that needs no account is possible: `/healthz`, the
  `302` to managed login, and the hashed script with its cache header. A signed-in check would need
  a TOTP secret in CI, which it should not have. The PM decides whether this task or `v1-e39-t10`
  owns it.
- **Cookie size.** The session cookie measured under 3,800 bytes with a 2,000-character refresh
  token in the test. Cognito's real refresh tokens are about 1,800 characters; ac5's sign-in proves
  it in a browser.
- **`tub users list` shows no disabled marker**, because the spec says "usernames and roles only".
  If the coach wants one, it is a spec change.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** CHANGES_REQUESTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-20

**Notes:**

The work is strong and nearly done. There is one small change, and then ac5 closes in this session.
I review again after both; the pull request opens with no `--partial`, because v1-e39-t06 depends on
this task.

**What is good:**

* **The evidence is real.** The callback tests run the real OAuth client and verifier on RS256
  tokens signed for the run, including `alg` `none` and `HS256`. The matrix fails when a route has no
  row. 23 of 23 mutants were caught, and the one that did not apply was reported, not counted. The
  red run says plainly that the skeleton was made from the finished code.
* **Deviation 4 is the right call.** Re-reading the account at revalidation is what makes "no
  session without an authenticator" hold after sign-in, not only at it. One extra call every five
  minutes is cheap.
* **The password handling** (shown once, never in stderr, `--verbose`, errors or a `DEBUG` capture),
  the username refusals before any call, and audit records with subjects and no names are what the
  E39 gate needs.

**The change: replacing an authenticator starts with a POST.**

`GET /account/authenticator` calls `AssociateSoftwareToken` for a full session. The session cookie
is `SameSite=Lax`, which is right for the return from managed login, but it means a cross-site link
to that page, clicked by a signed-in student, starts an association. Two consequences:

* **It may break the old authenticator.** The page's copy relies on the old authenticator working
  until the new one is confirmed. AWS's API reference has described both behaviours over time:
  older text says association disassociates the existing token at once, newer text says this happens
  at verification. ac5 step 4 tests it, but the design should not depend on the answer.
* **Your own deviation 4 makes it worse.** If association does drop the old token, the next
  revalidation's `GetUser` finds no second factor and ends the session. The student must then enrol
  again at sign-in, with only the password standing between that and someone else's phone.

**What to change:**

1. **For a full session,** `GET /account/authenticator` renders a page with a *Start* button and
   calls nothing in Cognito. The button is a form POST (say `POST /account/authenticator/begin`)
   through the CSRF, `Origin` and `Sec-Fetch-Site` checks. That POST calls `begin_authenticator`
   and renders the QR page. `POST /account/authenticator` (confirm) is unchanged.
2. **A pending enrolment keeps today's GET.** It has no authenticator to lose, and the 303 from the
   callback lands there.
3. **Tests, shown failing first:**
   * a GET with a full session makes no self-service call (the stub asserts none);
   * the begin POST without the CSRF token, or cross-site, is refused before the route runs;
   * the matrix gains the new route's row and its `ROUTE_ACCESS` entry;
   * a mutant that lets the GET begin for a full session is caught.
4. **The copy follows ac5 step 4's answer.**
   * If the old app still signs in after *Start* without confirming, keep "your old one keeps
     working until you confirm".
   * If not, say on the *Start* page and in the guide that the old app stops working once you
     start, and that you should finish in one sitting.
   * The `authenticator-replaced` message is right either way.
5. **ac5's operator block:** step 4 now presses *Start* and then goes back without scanning. Give
   the operator the corrected block (A and B together) in this session after the change. Then
   record the outputs, set ac5 PASS and the Goal `Succeeded` in your own sections, and ask for a
   second review.

**Rulings on the deviations and decisions** (all accepted):

* **D1, the package list:** accepted, including `packages/debate_core/pyproject.toml` for the `tub`
  extra. Writing the additions into the spec, with a reason for each, is the right way to do it.
* **D2, the `/coach` page:** accepted. v1-e39-t07 or t06 gives it content.
* **D3, `tub users enable`:** accepted.
* **D5, runbook steps 6, 8, 11e and 12:** accepted. They would have been wrong after this deploy.
* **D6, smoke checks:** v1-e39-t10 owns them. I am adding an amendment for the checks that need no
  account (`/healthz`, the `302` to managed login, and the hashed script with its cache header).
  There is no signed-in smoke check and no TOTP secret in CI.
* **Not checking `x-amz-content-sha256` in the app:** accepted. Lambda refuses the POST first, and a
  check that failed on every POST in AWS was the worse risk.
* **The 15-minute enrolment cookie,** the pool id from `--pool-id` or `TUB_USER_POOL_ID`, refusing
  capitals rather than folding them, the password shape, and a failed audit write as exit 3 with no
  password shown: all accepted.
* **The whole selection to CI:** accepted, under working agreement 10.

**Operator follow-up C** (the module apply, dev then prod) goes on the PM's promotion list after the
merge. The prod apply runs from `prod-deploy` after its `owner.auto.tfvars` gains the pilot lines.

**The conflict with v1-e39-t02** in `debate_cli/commands/__init__.py`: whichever merges second keeps
both subgroups under one `tub` group, as you say.

---

## Second session: the PM's change, and ac5 (2026-10-20)

**Status:** COMPLETE. Every criterion passes, ac5 included. The Goal is `Succeeded`. One question
for the PM came out of ac5 step 4; it is in [Question for the PM](#question-for-the-pm), and it
does not hold up the review.

### The change: replacing an authenticator starts with a POST

These follow the review's points 1 to 5:

- **Point 1, the full session:** `GET /account/authenticator` renders `authenticator_start.html`
  and calls nothing in Cognito. Its **Start** button is a form POST to
  `/account/authenticator/begin`, which is `Access.SIGNED_IN`. That route goes through the gate's
  CSRF, `Origin` and `Sec-Fetch-Site` checks, calls `begin_authenticator`, and answers with the QR
  page.
  - `app.js` puts an HTML answer's `<main>` in place of the page's, with `DOMParser` and
    `importNode`. There is still no `innerHTML` and no `document.write`.
  - Confirming the new code (`POST /account/authenticator`) is unchanged.
- **Point 2, the pending enrolment:** its GET is unchanged and still begins the secret.
- **Point 4, the wording:** it follows ac5 step 4's answer, which was that the old app stops at
  once. The *Start* page, the QR page after *Start*, the account page and the guide now say the old
  app stops working as soon as you choose *Start*, so finish in one sitting. They also say what to
  do if you are signed out first. The `authenticator-replaced` message is unchanged.
- **The test fake:** `FakeSelfService.begin_authenticator` now drops the authenticator, as Cognito
  did.
- **Docstrings:** the port's and `AccountPageService`'s say the same.

### Shown failing first

| Run | Commit | Command | Result |
|---|---|---|---|
| Red, *Start*: the tests against the code before the change | `25c0a7b` | `uv run pytest packages/debate_api/tests -n 0` | `8 failed, 401 passed` |
| Green | `ffa50c3` | the same | `409 passed` |
| Red, the wording, with the fake dropping the authenticator at *Start* | `5c44a93` | the same | `3 failed, 408 passed` |
| Green | `d18b3a2` | `uv run pytest packages/debate_api/tests packages/debate_core/tests/application/tub` | `486 passed` |

**The 8 that failed:**
- `test_the_page_for_a_full_session_calls_nothing_in_cognito`;
- `test_start_begins_a_new_secret_and_shows_its_qr_code`;
- the two account-page tests moved to *Start*;
- the matrix's coverage test (the new route had no row yet);
- the CSRF test's GET on `/begin`;
- the page rules, now including the *Start* answer;
- the script's HTML-answer test.

**The ones that passed on the old code:** the six forged-*Start* tests and the
pending-enrolment-*Start* test, because the gate already refuses a forged or pending-enrolment POST
to any path. They now hold the new route to that. The pending-enrolment GET test passed too, since
that GET is unchanged.

**Mutants** (same driver, `-n 0`, fresh Hypothesis directory, byte restore, clean tree after):

| Mutant | Result | Caught by |
|---|---|---|
| The GET begins for a full session (the review's mutant) | CAUGHT (1) | `test_the_page_for_a_full_session_calls_nothing_in_cognito` |
| A pending enrolment may press *Start* (`/begin` as `ENROLMENT`) | CAUGHT (1) | `test_start_is_for_a_full_session_only` |

The matrix gained the row `POST /account/authenticator/begin`, `ROUTE_ACCESS` gained its entry,
and the CSRF tests gained the route.

### ac5, the operator's dev run, 2026-10-20

The run was from this worktree at `329a082`. The operator reported these results; no password or
code was pasted. The deploy's own output (step 1) and the account's creation (step 2) were not
pasted. Steps 3 to 8 are the evidence they ran: the *Start* page and the PKCE redirect exist only in
this branch's code.

| Step | Result |
|---|---|
| 1. Deploy to dev | Ran. The deployed app is this branch: step 4's *Start* page and step 7's redirect are its code |
| 2. Synthetic account `synthetic.student.one` | Created (step 8's audit record `account-added`, 04:18:53Z) |
| 3. Sign in and enrol TOTP | Done: signed in, authenticator set up, on *Your account* |
| 4. *Start*, without scanning | *Start* worked. The next page load landed on managed login's *Set up authenticator app MFA*. `admin-get-user` then returned `CONFIRMED None None`: **the authenticator was dropped at *Start*** |
| 5. Sign out, then sign back in | Asked to sign in again, so managed login's own session had been cleared. Then asked to set up a second factor (email or authenticator app): outcome (b), the same finding as step 4 |
| 6. `tub users reset` | Done (audit record `account-reset`, 04:26:44Z) |
| 7. Sign in after the reset | Redirected to `https://auth.tub.dev.wfbdebate.com/login?response_type=code&...&redirect_uri=https%3A%2F%2Ftub.dev.wfbdebate.com%2Fauth%2Fcallback&scope=openid+aws.cognito.signin.user.admin&state=...&nonce=...&code_challenge=...&code_challenge_method=S256` (client id and values elided). Asked for a new password and a second factor, then signed in, then signed out |
| 8. The audit log, then `tub users remove` | Two events on the `tub-users` stream. `account-added`, `actor_role` `coach`, `account_subject` `94787458-…`, `format_version` 1, at 04:18:53Z; then `account-reset` with the same subject at 04:26:44Z. No username in either. Then `Removed synthetic.student.one. Any open session ends within five minutes.` |
| B. `bash scripts/terraform_checks.sh` | Every line `ok`: fmt, validate for 9 roots and modules, tflint for 9 configs and the recursive run, `terraform test` for 4 modules. `All Terraform checks passed.` |

**ac5 is PASS:** a synthetic user signed in on dev, enrolled TOTP and signed out, and a reset forced
enrolment again.

### Acceptance criteria, as of this session

| Criterion | Status | Evidence |
|---|---|---|
| Node `sign-in` | PASS | `uv run pytest packages/debate_api/tests packages/debate_cli/tests -k "auth or session or tub_users"` (the first session: 480 passed; this session's runs below) |
| ac1, ac2, ac3, ac4, ac6 | PASS | As in the first session, with the matrix and CSRF rows for `/begin`. The guide's new-phone steps now name *Start* and its consequence |
| ac5 | PASS | The table above |

### Checks run

| Check | Result |
|---|---|
| `uv run pytest packages/debate_api/tests packages/debate_cli/tests/commands/test_tub_users.py packages/debate_core/tests/application/tub packages/debate_core/tests/integrations/cognito tests/architecture tests/specs` | `793 passed in 7.30s` |
| `uv run scripts/affected_tests.py` | The whole selection is affected (the package pyprojects), so the PR's CI runs it (working agreement 10, accepted in the review) |
| `ruff check .`, `ruff format --check .` | exit 0, exit 0 |
| `pyright packages/debate_api packages/debate_cli packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` | exit 0 |
| `scripts/check_thin_handlers.py` | `OK: 43 CLI command and API route handlers within 25 statements` |
| `scripts/validate_specs.py` (after setting `Succeeded`) | `OK: 394 files, 39 epics, 334 tasks, 21 releases` |
| `scripts/check_links.py`, `scripts/check_command_blocks.py` | `OK: 1872 relative links and anchors in 270 Markdown files`; `OK: no # comments in 327 shell code blocks in 127 Markdown files` |
| `bash scripts/terraform_checks.sh` (the operator) | `All Terraform checks passed.` |

**Two commits stopped before they went in.** Pyright found an `Optional` access in a new test, and
the commit chained after it did not run. The mutant driver refused a file that was not yet
committed. Both were fixed and the commands re-run.

### Question for the PM

ac5 step 4 showed a gap the wording cannot close:

1. Between *Start* and confirming the new code, the account has no second factor.
2. Revalidation (deviation 4) ends such a session at its next due check.
3. *Start* does not reset the revalidation clock, so that check can be seconds away. That is what
   happened in the operator's run.
4. The student then lands on managed login's setup page, where the password alone lets anyone
   register a phone. That fallback is inherent once Cognito has dropped the token. The question is
   how short the window before it should be.

The options:
- **(a)** *Start* counts as a revalidation. It has just redeemed the refresh token and read the
  account, so it writes the session back with `revalidated_at` set to now, giving the student a
  full five minutes. About 6 lines and 2 tests.
- **(b)** A session that pressed *Start* may lack an authenticator for up to 15 minutes. That needs
  a new cookie field and an exception to the invariant.
- **(c)** Leave it as it is.

**Recommendation: (a).** Scanning and confirming take a minute or two. It adds nothing to the cookie
and no exception to the invariant, and a slower student falls back to the path the *Start* page
already describes. If the PM chooses (a) or (b), I make it with its test shown failing first.

### Operator follow-ups still open

- **C, the module apply, dev then prod.** It is on the PM's promotion list after the merge. The prod
  apply runs from `prod-deploy` once its `owner.auto.tfvars` has the pilot lines.

## Third session: the PM's ruling on Start (2026-10-20)

The PM ruled **(a), plus two small additions**, in a relay message:

- *Start* counts as a revalidation;
- *Start* and a session ended for want of a second factor are both written to the audit log;
- the *Start* page and the guide say what to do if signed out partway, or if asked to set up an
  authenticator unprompted.

### The change

- **Start counts as a revalidation.** `AccountPageService.begin_replacement` makes revalidation's
  own checks, through `refreshed_account` in `sign_in.py`, which `_revalidated` now uses too:
  - the refresh grant;
  - the subject;
  - the role.

  It then returns the session with `revalidated_at` set to now, and the role and the
  `email-second-factor` group re-read. The begin route writes that session back. It skips only the
  second-factor check, which *Start* fails on purpose.
- **`authenticator-replacement-started`.** Written by the begin POST, after the refresh and
  **before** `AssociateSoftwareToken`. A start that cannot be recorded answers 503 and leaves the old
  authenticator working.
- **`session-ended-no-second-factor`.** Written by revalidation when it ends a session for that
  reason, and for no other reason. A record that cannot be written does not keep the session open:
  the session ends either way.
- **Both records** follow `debate_core.application.tub.audit`'s shape, with the student's subject as
  `actor_subject` and `account_subject`, and no name. `SignInService` now takes the audit sink; the
  container passes it the app's existing CloudWatch sink. The function's role is unchanged: it
  already has `logs:PutLogEvents` on its audit group.
- **The copy.** The *Start* page, the guide's student section and its coach section carry the PM's
  two lines.

### Decisions in this session

1. **The record comes before Cognito is asked.** The other way round, a failed audit write after
   *Start* would leave the student with no authenticator and no QR code. This way the log shows a
   start only after the refresh has said the account is still there. If `AssociateSoftwareToken`
   then fails, the log shows a start with no registration, which reads as abandoned. That is true:
   the student did not get a new authenticator.
2. **A lost `session-ended-no-second-factor` record is dropped, not raised.** Raising it would turn
   the end of a session into a 500 on every request until CloudWatch answers. Neither case lets the
   session continue, so the choice is between an error page and a lost record.
3. **The *Start* page says "The coach's fix is a reset."** The PM's wording is
   "tub users reset". That command means nothing to a student, so the page says "a reset" and the
   guide's two sections name the command. The page also says "choose **Start**" where the PM wrote
   "press", to match every other page and the guide.
4. **Two sentences beyond the ruling.** The *Start* page and the guide's new-phone step say the
   student has five minutes to enter the new code. The coach's section says the audit log shows each
   replacement as `authenticator-replacement-started`, then `authenticator-registered`. Both follow
   from the ruling; neither changes behaviour.

### Shown failing first

The tests were committed with a skeleton (`1a9bdcc`). The skeleton had:

- the two audit actions;
- the `audit` argument on `SignInService`;
- a `begin_replacement` that returned the session unchanged and wrote no record.

Run against that skeleton, **10 failed, 35 passed**, each for its reason:

| Test | How it failed |
|---|---|
| `test_a_revalidation_due_seconds_after_start_does_not_end_the_session` | `302 == 200`: signed out 10 s after *Start* |
| `test_a_confirm_4_59_after_start_succeeds` | answered `{"message": …, "location": "/"}`: signed out before the confirm |
| `test_with_no_confirm_the_session_ends_at_the_first_revalidation_after_five_minutes` | `302 == 200` at 4:59: ended too early |
| `test_start_rechecks_the_role_as_a_revalidation_does` | `200 == 401`: *Start* went ahead without a role |
| `test_start_records_authenticator_replacement_started` | no record |
| `test_a_session_ended_for_want_of_a_second_factor_is_recorded` | no records |
| `test_a_start_that_cannot_be_recorded_keeps_the_old_authenticator` | `200 == 503`: *Start* went ahead |
| `test_start_then_a_confirmed_code_replaces_the_authenticator` (record list) | only `authenticator-registered` |
| `test_a_confirmed_new_authenticator_replaces_the_old_one` (record list) | the same |
| `test_the_start_page_says_what_to_do_if_signed_out_or_asked_unexpectedly` | the sentences were not on the page |

Four new tests passed on the skeleton, and they now hold their behaviour:

- `test_a_forged_start_does_not_count_as_a_revalidation`: a forged *Start* is refused before the
  route runs, so the clock was never reset;
- `test_start_on_an_account_signed_out_elsewhere_changes_nothing`;
- `test_a_session_ended_for_another_reason_records_nothing`;
- `test_a_session_end_that_cannot_be_recorded_still_ends_the_session`: the skeleton wrote no record,
  so it had none to lose.

The CSRF and cross-site refusals on the begin route still hold: the six forged-*Start* cases pass,
and the forged-*Start* revalidation test is new.

**Mutants** (same driver, `-n 0`, fresh Hypothesis directory, byte restore, `git status
--porcelain` empty after):

| Mutant | Result | Caught by |
|---|---|---|
| *Start* returns the session without resetting `revalidated_at` | CAUGHT (3) | `test_a_revalidation_due_seconds_after_start_does_not_end_the_session` |
| *Start* writes no record | CAUGHT (5) | `test_a_confirmed_new_authenticator_replaces_the_old_one` |
| *Start* records after `AssociateSoftwareToken` | CAUGHT (1) | `test_a_start_that_cannot_be_recorded_keeps_the_old_authenticator` |
| Revalidation writes no `session-ended-no-second-factor` | CAUGHT (1) | `test_a_session_ended_for_want_of_a_second_factor_is_recorded` |
| A lost session-end record is raised, not dropped | CAUGHT (1) | `test_a_session_end_that_cannot_be_recorded_still_ends_the_session` |

### ac5: the step 4 facts

From the operator's run on 2026-10-20 (the table under [ac5, the operator's dev
run](#ac5-the-operators-dev-run-2026-10-20)):

1. After *Start*, with the new QR code not scanned, the operator ran this at 04:23:29Z:

   ```text
   aws cognito-idp admin-get-user --profile debate-dev-tub-accounts --region us-east-1 --user-pool-id "$TUB_USER_POOL_ID" --username synthetic.student.one --query '[UserStatus,UserMFASettingList,PreferredMfaSetting]' --output text
   ```

   It returned `CONFIRMED None None`: no MFA setting at all and no preferred factor. The old
   authenticator was gone, though the new one had never been confirmed.
2. At the next page load the app sent the browser to managed login, which showed *Set up
   authenticator app MFA*. At the next full sign-in (step 5), managed login asked for a second
   factor to be set up, email or authenticator app, not for a code from the old app.

### ac5: the re-run this change needs

The change is in the deployed path, so the operator re-runs steps 4 and 5 on dev with it. That
covers three things: a replacement that finishes, a replacement left unfinished, and the two new
records in CloudWatch. The reset steps (6 and 7) and the Terraform checks do not depend on this
change and are not re-run.

**Results: PENDING the operator's run.** They will be recorded here.

### Acceptance criteria, as of this session

| Criterion | Status | Evidence |
|---|---|---|
| Node `sign-in` | PASS | The tests and mutants above; checks below |
| ac1, ac2, ac3, ac4, ac6 | PASS | As before, with the new tests for *Start* and the two records |
| ac5 | PASS on the first run; the re-run of steps 4 and 5 is PENDING | [the step 4 facts](#ac5-the-step-4-facts) and the re-run above |

### Checks run

| Check | Result |
|---|---|
| `uv run pytest packages/debate_api/tests packages/debate_cli/tests/commands/test_tub_users.py packages/debate_core/tests/application/tub packages/debate_core/tests/integrations/cognito tests/architecture tests/specs` | `805 passed in 6.26s` (793, plus the 12 new tests) |
| `ruff check .`, `ruff format --check .` | `All checks passed!`, `940 files already formatted` |
| `pyright packages/debate_api packages/debate_cli packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `scripts/check_thin_handlers.py` | `OK: 43 CLI command and API route handlers within 25 statements` |
| `scripts/validate_specs.py` | `OK: 394 files, 39 epics, 334 tasks, 21 releases` |
| `scripts/check_links.py`, `scripts/check_command_blocks.py` | `OK: 1875 relative links and anchors in 270 Markdown files`; `OK: no # comments in 327 shell code blocks in 127 Markdown files` |

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-20

**Notes:**

Accepted, on three conditions, all closed in this session before the pull request (no `--partial`):

1. **A dropped `session-ended-no-second-factor` record leaves a trace.** Decision 2 is right: the
   session ends whether or not the record is written. But `contextlib.suppress` drops the record
   silently. Write one `WARNING` to the app log saying an audit record was lost, with its action and
   no name or subject. Add a test, shown failing first.
2. **The re-run of ac5 steps 4 and 5 on dev,** with condition 1 in the deployed code. Give the
   operator one block: the deploy, a synthetic account, sign-in and enrolment, then:
   * *Start* and confirm a new code: a finished replacement;
   * *Start* again and wait past five minutes without confirming: the session ends at the next page
     load after 5:00, and not before;
   * the CloudWatch read of both new records alongside `authenticator-registered`;
   * removing the account.

   Record the outputs in your own section, keeping the rule against pasting passwords and codes.
3. **If the re-run shows anything other than what you expect,** stop and ask for another review
   rather than opening the pull request.

**What I checked:**

* **The step 4 finding is recorded well.** `admin-get-user` returned `CONFIRMED None None` before
  any confirm. That settles the AWS behaviour question, and the wording now tells students the
  truth.
* **Start as a revalidation reuses revalidation's own checks** (`refreshed_account`) and skips
  only the second-factor check, which is the one *Start* fails on purpose. The role re-check is
  tested. A forged *Start* cannot reset the clock.
* **Recording before `AssociateSoftwareToken`, with a 503 that keeps the old authenticator,** is
  the right order (decision 1). Each mutant on the order and the clock was caught.
* **Decisions 3 and 4 on the wording** are accepted: "a reset" for students, the command name for
  the coach, and "choose **Start**".
* **ac5's first run** covered sign-in, enrolment, a reset forcing re-enrolment, the PKCE redirect,
  audit records with subjects and no names, and the full Terraform checks. ac5 passes on that run.
  The re-run covers the code changed since.

**After the merge**, operator follow-up C (the module apply, dev then prod) goes on the PM's
promotion list. Whichever of this task and v1-e39-t02 merges second keeps both sides of the `tub`
group, the container and the service lists.

## Fourth session: the second review's conditions (2026-10-20)

### Condition 1: a dropped record leaves a trace

When revalidation cannot write `session-ended-no-second-factor`, the session still ends, and
`debate_core.application.tub.sign_in` logs one `WARNING`:

```text
tub audit: a session-ended-no-second-factor record was not written; the session ended anyway
```

It names the action and nothing else: no username and no subject. `contextlib.suppress` is gone from
that path; `sign_out`'s use of it is unchanged. The app configures no log handler, so Python's
last-resort handler writes the line to stderr, which Lambda sends to the function's log group.

**Shown failing first.** `test_a_lost_session_end_record_is_logged_once_without_a_name_or_subject`
was committed alone (`7f6fc63`). It failed for its reason, finding no WARNING
(`ValueError: not enough values to unpack (expected 1, got 0)`); the other 22 tests in its file
passed. After the change (`61aa4d2`), all 23 passed.

**Mutants** (same driver; byte restore; `git status --porcelain` empty after):

| Mutant | Result | Caught by |
|---|---|---|
| A lost record is raised (`except ZeroDivisionError`) | CAUGHT (2) | `test_a_session_end_that_cannot_be_recorded_still_ends_the_session` |
| No WARNING is written | CAUGHT (1) | `test_a_lost_session_end_record_is_logged_once_without_a_name_or_subject` |
| The WARNING names the account's subject | CAUGHT (1) | the same |
| Revalidation writes no record (re-run) | CAUGHT (2) | `test_a_session_ended_for_want_of_a_second_factor_is_recorded` |

The third session's mutant "a lost session-end record is not suppressed" no longer applies, because
its text is gone. "A lost record is raised" replaces it.

### Checks run

| Check | Result |
|---|---|
| The same affected selection as the third session | `806 passed in 18.64s` (805, plus the new test) |
| `ruff check .`, `ruff format --check .` | `All checks passed!`, `940 files already formatted` |
| `pyright packages/debate_api packages/debate_cli packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `scripts/check_thin_handlers.py` | `OK: 43 CLI command and API route handlers within 25 statements` |
| `scripts/validate_specs.py` | `OK: 394 files, 39 epics, 334 tasks, 21 releases` |

### Condition 2: the ac5 re-run of steps 4 and 5 on dev

The operator ran it from this worktree at `93ed3f1` on 2026-10-20. Local times were UTC−5 and match
the audit log. No password or code was pasted.

**The result differs from what was expected, so this task stops and asks for another review
(condition 3).**

| Step | Expected | Seen |
|---|---|---|
| 2. `tub users add` | `account-added` | `account-added` at 05:01:10Z, `account_subject` `44e854b8-…`, `actor_role` `coach` |
| 3. Sign-in and enrolment | Enrolment at managed login, so no app record | `authenticator-registered` at 05:03:31Z, `actor_role` `student`: the account was enrolled through **the app's own** enrolment page |
| 4. *Start*, then confirm | `authenticator-replacement-started`, then `authenticator-registered` | One *Start*, at 05:04:16Z (`authenticator-replacement-started`). No second `authenticator-registered` |
| 5. *Start* again, wait past 5:00, reload | A second `authenticator-replacement-started`; at the reload after 5:00, the sign-in page and `session-ended-no-second-factor` | Six minutes after *Start*, the reload **did not** go to the sign-in page. No `session-ended-no-second-factor` |
| 6. The CloudWatch read since step 2 | Five records | Three: the three above. Every record has the same subject and no username |
| 7. `tub users remove` | `Removed synthetic.student.one. …` | As expected |

**What the records establish:**

- The account went through the app's pending enrolment in step 3. Managed login let it in without
  an authenticator, which happens when email is chosen at its first setup.
  `confirm_authenticator` then turned on both factors. When *Start* ran, the account therefore had
  the authenticator and a verified email factor. The first run's account had only the
  authenticator.
- One *Start* was recorded, and nothing after it: neither a registration nor a session end.

**Two readings fit, and they need different fixes:**

- **(R1)** With an email factor also on, `AssociateSoftwareToken` did not remove
  `SOFTWARE_TOKEN_MFA` from `GetUser`'s `UserMFASettingList`. Revalidation then found an
  authenticator and kept the session, correctly by its rules, so no record was written.
- **(R2)** Revalidation did end the session, but the record was not written. Managed login still had
  its own session from 05:02 and the account still had a second factor (email), so it sent the
  browser straight back without a sign-in page. The callback found no authenticator and opened the
  app's enrolment page. That looks like still being signed in. The lost record would have left this
  session's WARNING in `debate-dev-tub-app`.

To tell them apart: what the reload after six minutes showed, and the app log for 05:00 to 05:30Z.

### The diagnosis: R1, and a second finding

**The operator's answers:**

1. The reload after six minutes showed *Set up a new authenticator app* with a **Start** button and
   no QR code: still signed in.
2. At managed login's first setup, the operator chose the **authenticator app**, not email.
3. The operator entered a code from a new authenticator entry, and the page said it was set up.

**The app log** (`debate-dev-tub-app`, 05:00 to 05:30Z). The request log is off, so each request is
one `START`/`REPORT` pair. A request that calls Cognito takes about 400 ms or more; one that calls
nothing takes about 4 ms. There is no `tub audit:` line, no warning and no error.

| Time (UTC) | Duration | Request, from its timing and the audit log |
|---|---|---|
| 05:02:45.2 | 484 ms | `/auth/callback`: code exchange, then `GetUser` found **no** authenticator, so a pending enrolment |
| 05:02:45.8 | 495 ms | The pending enrolment's `GET /account/authenticator`: refresh and `AssociateSoftwareToken` |
| 05:03:30.4 | 1037 ms | Its confirm: `authenticator-registered` at 05:03:31Z |
| 05:03:31.5 | 418 ms | `GET /account` |
| 05:03:58.6 | 7 ms | The *Start* page, which calls nothing, as the first review required |
| 05:04:15.8 | 899 ms | *Start*: `authenticator-replacement-started` at 05:04:16Z |
| 05:08:11.7 | 6 ms | The reload at 3:56 after *Start*: not yet due, so the *Start* page |
| 05:10:36.2 | 851 ms | The reload at 6:20 after *Start*: revalidation (refresh, `GetUser`) **passed**, then the *Start* page |
| 05:11:59 to 05:13:03 | 3 to 7 ms each | 16 more requests, none calling Cognito (revalidated at 05:10:36) |

After 05:10:36 there is no callback, so the browser did not go through managed login: **R2 is
ruled out.** No record was lost, and the WARNING path never ran.

**What this run found:**

1. **At this account's first sign-in, managed login's authenticator setup did not register
   with the app.** The operator chose the authenticator app at managed login, yet the callback's
   `GetUser` did not list `SOFTWARE_TOKEN_MFA`. The app then showed its own enrolment page, and the
   student scanned a second QR code. The confirm the operator describes under answer 3 is that page,
   at 05:03:30. So a student may be asked to set up the app twice at a first sign-in.
2. **This time, *Start* did not drop the authenticator.** Six minutes after `AssociateSoftwareToken`,
   `GetUser` still listed `SOFTWARE_TOKEN_MFA`. In the first run, `AdminGetUser` after *Start*
   listed none.

   The two accounts differ in how their authenticator was registered:
   - **This run:** by the app (`VerifySoftwareToken`, then `SetUserMFAPreference`), as the audit
     record shows.
   - **The first run:** not known. That run read only the `tub-users` stream.
3. **The code did what its rules say.** Revalidation found an authenticator and kept the session.
   Only the copy is wrong for this case: the *Start* page says the old app stops working at once.
4. **A replacement through *Start* and confirm has not yet run on dev.** The only confirm in this run
   was the first-sign-in enrolment.

### Two read-only checks, and what they change

**The first run's audit records** (`debate-dev-tub-audit`, 04:15 to 04:35Z, all streams):
`account-added` 04:18:53Z, `account-reset` 04:26:44Z, `account-removed` 04:29:20Z, all with
`actor_role` `coach` and the same subject. There is **no app record.** The code at `329a082`
already wrote `authenticator-registered` on the app's enrolment page, so the first run never
reached that page. Its authenticator was set up at managed login alone, and the callback found
`SOFTWARE_TOKEN_MFA`.

**The pool's MFA configuration** (`get-user-pool-mfa-config`): `MfaConfiguration` `ON`, software
token MFA enabled, email MFA configured. This is as the module sets it.

**What this changes:**

- **Finding 1 is not established.** In the first run, the authenticator chosen at managed login
  reached the app. In this run it did not, though the operator recalls choosing the authenticator
  app. Choosing **email** at managed login would explain this run exactly, since that is the
  guide's own email path. Managed login sometimes not registering a TOTP would explain it too. Only
  a run with screenshots can tell them apart.
- **Finding 2 now has a likely cause.** The two accounts went into *Start* in different states:

  | Run | How the authenticator was set up | Factors when *Start* ran | After `AssociateSoftwareToken` |
  |---|---|---|---|
  | First | Managed login only (no app record) | the authenticator alone | `AdminGetUser`: no MFA setting at all |
  | This | The app's enrolment page (`authenticator-registered`) | the authenticator, and email too if email was chosen at managed login | `GetUser` 6 minutes later: `SOFTWARE_TOKEN_MFA` still listed |

  Two rules would explain both rows:
  - Cognito drops the old authenticator only when it is the account's only factor;
  - or it drops one set up in managed login's challenge, but not one turned on with
    `SetUserMFAPreference`.

  The page and guide wording depend on which rule holds.

**The question for the PM** is in the review request: measure first, then fix the wording to match.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-20

**Notes:**

Accepted, with a different answer from the three offered: **(d) withdraw self-service
replacement for the pilot.** A student with a new phone asks the coach for a reset. The conditions
below close in this session; then the pull request opens with no `--partial`. As before, if
anything comes out differently from what you expect, stop and ask for another review.

**Stopping the PR under condition 3, and the diagnosis, were exactly right.** The app log's request
timings ruled out R2 without guessing. The audit streams showed the first run never reached the
app's enrolment page.

**Why (d), not (a):**

* **The common path is the dangerous one.** Students set up the authenticator at managed login at
  first sign-in, as the first run's account did. There, *Start* dropped the authenticator at once. A
  *Start* left unfinished then leaves enrolment open to anyone with the student's password, for as
  long as the student stays away. The audit record makes that visible, but it does not close it.
* **Measuring would settle the wording, not the risk.** Cognito's effect depends on undocumented
  account state. Under either rule, the case students would hit most is the one that drops.
* **A reset is already built, tested on dev and audited.** Its temporary password comes from the
  coach, so enrolment after a reset is never open to a password alone. In a one-team pilot, a new
  phone is rare, and a lost phone needs the coach anyway.

**Conditions:**

1. **Remove *Start*:**
   * the `POST /account/authenticator/begin` route and the *Start* page;
   * `begin_replacement`, and *Start*'s revalidation path;
   * the `authenticator-replacement-started` action;
   * the `authenticator-replaced` message.

   **Keep:**
   * the pending enrolment's GET and confirm, unchanged;
   * `session-ended-no-second-factor` and its WARNING;
   * revalidation's second-factor check (deviation 4).
2. **For a full session,** `GET /account/authenticator` calls nothing in Cognito and goes to
   `/account`. The account page's authenticator section says: for a new phone, ask your coach for a
   reset; you then sign in with the temporary password and set up the app again. The route's
   `ROUTE_ACCESS` entry becomes enrolment only.
3. **Tests:**
   * the route list and matrix lose `/begin`, and the coverage test still fails on an unlisted route;
   * a full session's GET makes no self-service call and renders no QR code;
   * no route a full session can reach calls `AssociateSoftwareToken`. That is the test that holds
     the decision.

   Show the new tests failing on the current code where they can, and catch one mutant that brings
   back a full session's association.
4. **The guide:**
   * Replace the student's new-phone steps with the reset path, and the coach's section with when to
     reset.
   * Add one line on first sign-in: choose the authenticator app at managed login. If you chose
     email, the app asks you to set up the authenticator app as well; that is expected.
5. **The spec:** amend ac6's "replaces the authenticator" to "for a new phone, sends the student
   to the coach for a reset (no self-service replacement in the pilot)". Add a comment
   `PM ruling 2026-10-20 (ac5 re-run)`.
6. **The report:**
   * Keep both runs' facts as they are.
   * ac5 stays PASS on the first run, which covered sign-in, enrolment, sign-out and a reset forcing
     enrolment again. The re-run tested *Start*, which is withdrawn.
   * No further dev run is needed.

**Filed by the PM in the next batch:**

* an ADR-0019 consequence recording why self-service replacement was withdrawn, with both runs'
  `AssociateSoftwareToken` results;
* a v1-e39-t10 amendment: the coach's beta records each tester's first sign-in with screenshots
  (which factor managed login offered, which was chosen, and whether the app's enrolment page then
  appeared). That settles finding 1 with real accounts.

**Re-allowing self-service replacement,** if a later version wants it, means measuring Cognito's
behaviour first, as option (a) set out.

## Fifth session: ruling (d), no self-service replacement (2026-10-20)

The third review accepted with ruling (d): self-service authenticator replacement is withdrawn for
the pilot, and a new phone goes to the coach for a reset. Conditions 1 to 6 are closed below. No
dev run was made (condition 6). Both runs' facts above are unchanged.

### Condition 1: *Start* removed

**Removed:**
- the `POST /account/authenticator/begin` route and its `ROUTE_ACCESS` entry;
- `authenticator_start.html`;
- `AccountPageService.begin_replacement`;
- `refreshed_account` and `RefreshedAccount` (*Start*'s revalidation path); `_revalidated` has its
  first-session shape again;
- the `authenticator-replacement-started` action;
- the `authenticator-replaced` notice;
- the replacement wording in `authenticator.html`;
- `app.js`'s HTML-answer branch, which only *Start* used.

**Kept:**
- the pending enrolment's GET and confirm, unchanged in behaviour;
- revalidation's second-factor check (deviation 4);
- `session-ended-no-second-factor`, now written by a small helper, `_record_no_second_factor`;
- the WARNING when that record is lost.

`AccountPageService.begin_authenticator` and `confirm_authenticator` now take a `PendingEnrolment`
only, so the type checker holds the rule too.

### Condition 2: a full session's GET goes to `/account`

`ROUTE_ACCESS` gives `/account/authenticator` a new access level, `PENDING_ENROLMENT`: a pending
enrolment only. Sign-out keeps `ENROLMENT` (a session or a pending enrolment). The gate answers a
full session on that path before any route runs:
- a GET gets `303` to `/account`;
- a POST gets `403`, with `{"message": "Your authenticator app is already set up.", "location":
  "/account"}`.

Neither calls Cognito. The account page's authenticator section reads *For a new phone, ask your
coach for a reset. You then sign in with the temporary password and set up the app again.*

### Condition 3: tests, shown failing first

The tests were committed before the change (`2ebb134`). Run against the code with *Start*:
**14 failed, 361 passed** (`packages/debate_api/tests`). Each failed for its reason:

| Test | How it failed |
|---|---|
| `test_no_route_a_full_session_can_reach_calls_associate_software_token[student]`, `[coach]`, `[email-second-factor]` | `AssociateSoftwareToken` in the calls (from `/begin`) |
| `test_a_full_sessions_get_goes_to_the_account_page_and_calls_nothing` | `200 == 303`: the *Start* page |
| `test_a_full_sessions_confirm_is_refused_and_calls_nothing` | `400 == 403`: the route ran |
| `test_there_is_no_route_to_begin_a_replacement` | `200 == 404` |
| The matrix's valid-session rows for `GET` and `POST /account/authenticator`, student and coach (4) | `(200, None) == (303, '/account')`; `400 == 403` |
| `test_the_matrix_covers_every_route_the_app_serves` | `/begin` served but not listed: the coverage test still fails on an unlisted route |
| `test_the_script_answers_only_with_a_place_to_go_or_a_message` | `DOMParser` still in `app.js` |
| `test_the_account_page_sends_a_new_phone_to_the_coach` | the sentence was not on the page |
| `test_an_account_with_no_authenticator_is_sent_to_the_coach_too` | the same |

Tests that passed before the change and now hold their behaviour:
- `test_a_forged_confirm_is_refused_before_cognito_is_asked`: three forgeries of a pending
  enrolment's confirm. The CSRF list for full sessions dropped `/account/authenticator`, which a
  full session can no longer reach, so the confirm's CSRF checks are held here.
- `test_a_pending_enrolment_still_begins_on_the_get`.
- The four `session-ended-no-second-factor` tests. The account now loses its authenticator directly
  instead of through *Start*.

`test_no_route_a_full_session_can_reach_calls_associate_software_token` is the test that holds the
decision. It sends every route the app serves, read from `app.routes`, as a full session with a
fresh session per request and a valid CSRF token, and asserts that no request was refused for want
of a session. It does this for a student, a coach, and an `email-second-factor` account with no
authenticator.

**Mutants** (same driver; byte restore; `git status --porcelain` empty after):

| Mutant | Result | Caught by |
|---|---|---|
| The gate lets a full session reach the authenticator page | CAUGHT (9) | the decision test for all three accounts, the two full-session tests, the matrix's four rows |
| `/account/authenticator` back to `ENROLMENT` | CAUGHT (9) | the same |
| Revalidation writes no record | CAUGHT (2) | `test_a_session_ended_for_want_of_a_second_factor_is_recorded` |
| A lost record is raised | CAUGHT (2) | `test_a_session_end_that_cannot_be_recorded_still_ends_the_session` |
| A lost record leaves no WARNING | CAUGHT (1) | `test_a_lost_session_end_record_is_logged_once_without_a_name_or_subject` |

The last three first reported `DID NOT APPLY`: moving the code into the helper changed its
indentation. They were rewritten and run again, and are counted only from that run.

### Condition 4: the guide

- **First sign-in.** Step 4 says to choose the authenticator app *here*. The email paragraph says
  that after email, the search asks for the authenticator app as well, and that this is expected.
- **Students.** The new-phone steps are now the reset path: a new phone, a lost phone (a backup email
  still signs in until the reset), a forgotten password.
- **Coach.** *Resetting a password or a phone* (renamed from *…a lost password or a lost phone*,
  with its link) lists when to reset.

### Condition 5: the spec

ac6 reads "…the account page adds, verifies and removes the backup email and, for a new phone,
sends the student to the coach for a reset (no self-service replacement in the pilot)…", with the
comment `PM ruling 2026-10-20 (ac5 re-run)` above it. `spec.description` said the same thing ("and
replace the authenticator"), so it was amended to match, under the same comment. That edit is
beyond the condition's wording. `validate_specs.py`: `OK: 394 files, 39 epics, 334 tasks, 21
releases`.

### Decisions in this session

1. **A full session's POST to `/account/authenticator` is refused by the gate,** not answered by
   the route. "Enrolment only" then holds for both methods in one place, and a full session's
   request never reaches `confirm_authenticator`.
2. **An `email-second-factor` account with no authenticator** is also told "To set one up, ask your
   coach", and its link to the authenticator page is gone. The page would now send it straight back.
   The coach's fix already exists: `email-second-factor --withdraw`, after which managed login asks
   for the app.
3. **One line kept from the third session's guide wording**, in both sections: being asked to set
   up an authenticator app unexpectedly (not a first sign-in, and no reset just made) means telling
   the coach, because someone may have the password. It no longer mentions *Start*.
4. **ADR-0019 line 369** still says a student with a backup email can "replace the authenticator
   from the account page". It is left for the PM's ADR consequence, which the review says is filed
   in the next batch.

### ac5, and dev

**ac5 stays PASS on the first run** (condition 6), which covered sign-in, enrolment, sign-out and a
reset forcing enrolment again. The re-run's facts stay above as recorded. **Dev still runs
`93ed3f1`, with *Start***, until the next deploy of the pilot app to dev. No synthetic account is
left: both were removed.

### Checks run

| Check | Result |
|---|---|
| The same affected selection as before | `757 passed in 8.70s` (the *Start* tests removed, the new ones added) |
| `uv run scripts/affected_tests.py` | The whole selection is affected (`packages/debate_api/pyproject.toml`), so the PR's CI runs it (working agreement 10) |
| `ruff check .`, `ruff format --check .` | `All checks passed!`, `940 files already formatted` |
| `pyright packages/debate_api packages/debate_cli packages/debate_core` | `0 errors, 0 warnings, 0 informations` |
| `lint-imports` | `Contracts: 12 kept, 0 broken.` |
| `scripts/check_thin_handlers.py` | `OK: 42 CLI command and API route handlers within 25 statements` (one fewer: the begin route) |
| `scripts/validate_specs.py` | `OK: 394 files, 39 epics, 334 tasks, 21 releases` |
| `scripts/check_links.py`, `scripts/check_command_blocks.py` | `OK: 1875 relative links and anchors in 270 Markdown files`; `OK: no # comments in 327 shell code blocks in 127 Markdown files` |

Nothing came out differently from what was expected, so the task is ready for the pull request
under the third review's ACCEPTED verdict.

## PM review, fourth

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-20

**Notes:**

The third review's six conditions are closed as asked, and nothing came out differently. Open the
pull request with no `--partial`, after the sync.

**What I checked:**

* **The decision test holds the ruling at the right level.** It walks every route in `app.routes`
  as a full session (student, coach, and an `email-second-factor` account with no authenticator) and
  asserts that no request calls `AssociateSoftwareToken`. It failed against the *Start* code for all
  three. The two mutants that reopen the route were caught nine times each.
* **Refusing a full session's POST in the gate, not the route** (decision 1), and narrowing
  `begin_authenticator` and `confirm_authenticator` to `PendingEnrolment` so the type checker holds
  the rule as well: both good.
* **Decisions 2 and 3 are accepted.** An email-only account goes to the coach, and the "set up
  unexpectedly, tell the coach" line stays. Amending `spec.description` to match ac6 is accepted.
* **Re-applied mutants that first did not apply are counted only from the run that applied.**
  That is the right practice again.

**Before the pull request, two lines of this report to correct**, since a reader starts at the top:

* the header's *Session status*, which still says ac5 is not run;
* the Summary's account-page bullet, which still says "replace the authenticator".

Fix them in place with a note that they were corrected after ruling (d). This is no change to the
verdict.

**After the merge:**

* **ADR-0019's line on replacing from the account page** (decision 4): the PM's next batch amends it
  with the consequence.
* **Dev still runs `93ed3f1`, with *Start*.** Nothing reaches it but synthetic accounts, so the next
  pilot deploy to dev (v1-e39-t06, or before) replaces it. No separate deploy is needed.
* **Operator follow-up C,** the module apply dev then prod, stays on the promotion list.
