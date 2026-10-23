# ADR-0019: The student search pilot — one function behind CloudFront, a weekly SQLite index, and coach-created Cognito accounts

- Status: Accepted
- Date: 2026-10-19
- Deciders: Charlie Clark (coach and product owner), on the PM's review
- Architecture references:
  - [§9 Search and Retrieval Architecture](../architecture/architecture_proposal.md#9-search-and-retrieval-architecture)
  - [§12 V2 Detailed Architecture](../architecture/architecture_proposal.md#12-v2-detailed-architecture) (authentication and authorization)
  - [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)
  - [§15 Reliability, Observability, and Cost Controls](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls)
  - [§17 Deployment and Evolution Plan](../architecture/architecture_proposal.md#17-deployment-and-evolution-plan)

## Context

Release v1.7 (epic [E39](../../plan_specs/v1/e39-evidence-search-pilot/epic.yaml)) gives the team's
debaters a signed-in page for searching the disclosed and camp cards in the evidence store, before
the fall semester ends in December 2026. Every later E39 task builds against this record, so it
decides rather than lists options.

**Fixed inputs** (the coach's decisions of 2026-10-19, not reopened here):

- A web app that works on a school Chromebook and from home.
- No Google sign-in and no school account of any kind.
- A username, a password and a second factor, on accounts only the coach creates.
- Authenticator-app (TOTP) codes as the main second factor; emailed codes as an opt-in fallback for
  a student who adds an email address; no SMS.
- The coach resets a lost password or a lost phone.
- The only step for school IT is allowing the pilot's hostnames through the web filter.
- The activities director and IT approved the tool for students
  ([data-use policy](../policies/caselist-data-use.md) 1.10, open question 6).

**What the decision has to fit.**

- **The data-use policy's [E39 gate](../policies/caselist-data-use.md#e39--student-evidence-search-pilot-v17),
  items 1 to 10.** Every choice below has to let each item be met and proven by a named test or
  operator record. The section [How each gate item is met](#how-each-gate-item-is-met) maps them.
- **One account, one region, two environments.** Everything is in the existing account in
  `us-east-1`, named `debate-<environment>-<purpose>` and tagged per
  [ADR-0010](0010-primary-aws-region.md), in `dev` and `prod` only
  ([ADR-0013](0013-two-environments-and-dev-main-promotion.md)). The dev pool holds the maintainer
  and synthetic users, never a student.
- **The team domain.** [ADR-0012](0012-web-hosting.md) put the public site on CloudFront with
  security headers at the edge, no access logging, and one team domain. The `wfbdebate.com` zone in
  Route 53 is read and never created. dev lives under `dev.wfbdebate.com`.
- **The store.** The parsed store held **233,643 cards** at parser version `2026.10.18-docx-5`
  ([v1-e31-t19's count](../data/caselist-parse-report.md)). The same 233,643 cards formed
  **46,069 card clusters** in the parse of 2026-10-12
  ([parse report](../data/caselist-parse-report.md)). The
  [store layout](../architecture/evidence-store-layout.md) reserves `reports/tub/` for the tub's
  index. The suppression list is `manifests/_suppression/suppression-list.jsonl`.
- **V2 keeps the pool.** [`v2-e12-t01`](../../plan_specs/v2/e12-identity-api/t01-cognito-user-pool.yaml)'s
  PM amendment of 2026-10-19 starts V2's identity from the pilot's user pool rather than building a
  second one. So settings Cognito fixes at pool creation are chosen here for V2 as well.
- **One adult maintainer and a school team's budget.** ADR-0010's monthly budget is $25 for dev
  and $50 for prod, and the account is shared with unrelated projects. There are no GitHub OIDC
  deploy roles until `v2-e10-t03`, so every apply and deploy is operator-run, as the website's are.
- **Students' Chromebooks.** They are managed devices that can run little beyond Chrome. A
  student's phone, if they have one, holds the authenticator app.

Every claim about an AWS service below was checked against its current documentation on
**2026-10-19**. The URLs are listed in
[AWS documentation relied on](#aws-documentation-relied-on-read-2026-10-19).

## Decision

**The pilot is one container-image Lambda function running a server-rendered FastAPI app.** It sits
behind its own CloudFront distribution at `tub.wfbdebate.com` (dev: `tub.dev.wfbdebate.com`), and
CloudFront reaches it only through a function URL signed by origin access control. The function
searches a SQLite FTS5 index that the operator builds weekly from the parsed store and publishes to
the evidence bucket. Students sign in through Cognito managed login, on accounts the coach creates,
with a password and an authenticator app.

This record covers release v1.7 and its two environments. It decides the pilot only.
[ADR-0004](0004-opensearch-is-derived-not-authoritative.md) still governs V2's search (see
[What V2 replaces and what it keeps](#what-v2-replaces-and-what-it-keeps)).

### (a) Hosting: one function behind CloudFront, reachable only through it

1. **Function.** Each environment has one Lambda function, `debate-<env>-tub`, built from a
   container image in the ECR repository `debate-<env>-tub`. Its base image is AWS's
   `public.ecr.aws/lambda/python` image, on Amazon Linux 2023, at the tag of the one Python that
   `requires-python` in
   [`packages/debate_core/pyproject.toml`](../../packages/debate_core/pyproject.toml) allows. The
   image follows that declaration; it does not state a version of its own. Its settings:
   - **Architecture:** `arm64`, so the operator's Apple-silicon Mac builds the image without
     emulation.
   - **Memory:** 2,048 MB.
   - **Ephemeral storage:** 4,096 MB, sized in [(c)](#c-the-index-one-sqlite-fts5-file-fetched-at-cold-start).
   - **Timeout:** 30 s, matching CloudFront's default origin response timeout.
   - **Reserved concurrency:** 10, a ceiling on cost and on how many copies of the index can be
     live at once.
2. **Function URL with `AWS_IAM` auth, behind origin access control.** CloudFront signs every origin
   request with SigV4 (an OAC of origin type `lambda`, signing behaviour `always`). The function's
   resource policy grants `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction` to
   `cloudfront.amazonaws.com`, conditioned on this environment's distribution ARN. A direct request
   to the function URL is refused by Lambda's IAM check before the function runs. The invoke mode
   is `BUFFERED`, since a download of 30 cards is far below the 6 MB response limit.
   **Amended 2026-10-22 (PM rulings, `v1-e39-t08`):** the file's size was never the limit (30
   cards measured 118 KB); the build's time is, and it grows with the sources a cart reads, not
   its cards. A download holds up to 8 cards, the sources' `word/document.xml` may add up to
   20,000,000 bytes as their zip directories declare them, and the files fetched to 52,000,000
   bytes. A built file is held under 3 MB, so the base64-encoded response stays within the
   buffered limit.
3. **Every POST carries the hash of its body.** The CloudFront documentation states that, through
   OAC, "if you use PUT or POST methods with your Lambda function URL, your users must compute the
   SHA256 of the body and include the payload hash value of the request body in the
   `x-amz-content-sha256` header". Lambda does not accept unsigned payloads. So the pages' one
   first-party script, `/static/<hash>/app.js`, sends every state-changing request with `fetch`.
   It sets `x-amz-content-sha256` from `crypto.subtle.digest('SHA-256', body)` and the CSRF header
   from [(d)](#d-sign-in-cognito-managed-login-coach-created-accounts-totp-required). The pages
   need that script anyway: Copy card puts `text/html` on the clipboard, and only script can do
   that. A plain form post that skips the script is refused at the origin with 403. That also
   blocks a cross-site form post before the app sees it.
4. **CloudFront.** One distribution per environment, separate from the website's, so a problem in
   the pilot cannot reach the parents' pages:
   - **TLS:** an ACM certificate in `us-east-1` for the pilot host and its login host, with
     `TLSv1.2_2021`.
   - **Delivery:** HTTP/2 and HTTP/3, compression on, `PriceClass_100`.
   - **One behaviour:** all seven methods allowed; the managed `CachingDisabled` cache policy; the
     managed `AllViewerExceptHostHeader` origin request policy, since the function URL expects its
     own `Host`.
   - **Security headers** from a response headers policy, as in ADR-0012 decision 6:
     - a Content-Security-Policy of `default-src 'self'` with `frame-ancestors 'none'`,
       `object-src 'none'`, `base-uri 'none'`, and `form-action 'self'` plus the login host;
     - HSTS;
     - `X-Content-Type-Options: nosniff`;
     - `Referrer-Policy: no-referrer`;
     - `X-Frame-Options: DENY`;
     - a `Permissions-Policy` that turns devices off;
     - `X-Robots-Tag: noindex, nofollow` on dev.
   - **No standard or real-time access logging**, and no AWS WAF.
5. **The app sends the caching rules.** Every signed-in response says `Cache-Control: private,
   no-store`. Static assets live at content-hashed paths under `/static/` and say `public,
   max-age=31536000, immutable`. They hold no data and are the same for every viewer.
6. **Names and DNS.**
   - **Pilot host:** `tub.wfbdebate.com` in prod, `tub.dev.wfbdebate.com` in dev.
   - **Login host:** `auth.tub.wfbdebate.com` in prod, `auth.tub.dev.wfbdebate.com` in dev.
   - **DNS records:** `A` and `AAAA` alias records in the existing `wfbdebate.com` zone. The zone is
     read through a data source, as `site.tf` reads it, and never created.
   - **Ordering:** Cognito requires the login host's parent to have an `A` record, so the pilot
     host's record is created before the user pool domain.
7. **What school IT allows.** IT allows the prod hostnames and nothing else:
   - `tub.wfbdebate.com`;
   - `auth.tub.wfbdebate.com`;
   - any other host the managed login pages load assets from. The documentation does not name one.
     Before the request goes to IT, `v1-e39-t04` signs in once on dev with the browser's network
     panel open and lists every host it sees.

   The authenticator app runs on the student's phone and needs no hostname. No cookie is
   third-party: the pilot's cookies belong to the pilot host, and the managed login's to the login
   host, which the student visits directly.

### (b) The app: server-rendered pages from FastAPI, through the Lambda Web Adapter

1. **Pages are HTML rendered on the server from Jinja templates** in `debate_api`. The only script
   is the one first-party file in (a) 3: no third-party scripts, fonts or analytics, and no inline
   script. No Next.js. A Chromebook downloads one HTML page under 150 KB before the card body
   (`v1-e39-t06`). It runs no client-side index or framework.
2. **The [AWS Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter), not
   Mangum.** The adapter is copied into the image as a Lambda extension (`/opt/extensions`), pinned
   by digest. Version 1.1.0 was current on 2026-10-19. It forwards function URL events to `uvicorn`
   on port 8080, with a readiness check on `/healthz`. `debate_api` stays a plain ASGI app with no
   Lambda code in it. The same app runs under `uvicorn` locally and in tests, and later in
   `v2-e12-t02`'s Fargate container. `uvicorn` runs with `--no-access-log`, because an access log
   line holds the client's address and the query string (gate item 4).
3. **The public origin is configuration.** The origin request policy drops the viewer's `Host`, so
   the app takes its own origin and the login host from environment variables. It uses them for
   redirect URIs, the `Origin` check and cookies. It never trusts a forwarded host header.

### (c) The index: one SQLite FTS5 file, fetched at cold start

1. **Format.** One SQLite file with FTS5, one document per card cluster, built by `tub index build`
   (`v1-e39-t02`) from the operator's local parsed store. It is published by `tub index publish`
   under `reports/tub/search/<index id>/` with its JSON manifest, and `current.json` is written
   last. The base image's Python is built against **SQLite 3.40.0**, and `PRAGMA compile_options`
   lists `ENABLE_FTS5`. This was checked on 2026-10-19 by running the image itself (built
   2026-10-15) for both `linux/amd64` and `linux/arm64`. The operator's Python has SQLite 3.50.4.
   So the index uses no SQLite or FTS5 feature added after 3.40.0. The manifest records the
   building SQLite version and an index format version, and the function refuses an index whose
   format version it does not know.
2. **Published compressed.** The SQLite file is uploaded as one gzip object (level 6, `mtime` 0,
   no file name in the header), so the same store still gives the same bytes. The manifest carries
   the sha256 of the compressed object and of the SQLite file.
3. **The function downloads it to ephemeral storage the first time a request needs it.** It reads
   `current.json` and the manifest, then streams the object through `gunzip` and `sha256` into
   `/tmp`. It refuses the file on a digest mismatch and opens it read-only. Sign-in, the callback,
   the health check and the empty search page do not need the index, so they never wait for it.
4. **The index is not carried in the image.** That would put school, team code and card text in
   ECR. ECR is not one of the places the policy lets that data live: the local store, the
   buckets' `manifests/`, built files' provenance, the per-school view, and the pilot's index in
   `reports/tub/search/` plus the copy its function holds while it runs. It would also tie the
   weekly refresh (`v1-e39-t09`) and every removal to an image build and a deploy.
5. **Freshness.** At most five minutes apart, before serving a request, an environment re-reads
   the suppression list and `current.json`, by conditional GET. A newly suppressed occurrence is
   hidden from that request on (gate item 5). An environment that has been frozen longer than five
   minutes checks before it answers, so it never serves a stale list. A new pointer makes that
   environment download the new index, swap to it and delete the old file. That is one
   cold-start-length wait per environment per weekly publish.
6. **Expected size.** One document per cluster gives about **46,000 documents** at 233,643 cards.
   This is an estimate for `v1-e39-t02` to measure (its criterion ac6). Each document holds:
   - the representative's text, about 3 to 6 KB;
   - its read-aloud text, about 1 KB;
   - its formatting spans, about 1 to 3 KB;
   - its tag and cite, about 0.4 KB;
   - the provenance of up to five occurrences, about 0.5 KB.

   The FTS5 index adds roughly a third of the indexed text, about 1.5 to 2.5 KB. That is **6 to
   12 KB a document, so about 280 to 550 MB**, or roughly 110 to 220 MB gzipped. The plan allows
   for growth to **1 GB uncompressed** during the season. Ephemeral storage of 4,096 MB holds the
   live copy, the incoming copy at a weekly swap, and headroom.

   **Amended 2026-10-22 (PM ruling, `v1-e39-t14`): storage, not 1 GB, is the size line.** A swap
   holds the live SQLite file and the incoming one, and nothing else: the gzip object streams
   through `gunzip` into the new file and never lands on disk, and the old file is deleted at the
   swap. So the 4,096 MB allows **about 2 GB of SQLite at a same-size swap**. The weekly stage
   warns at **1,700,000,000 SQLite bytes**, where two copies fill 79% and leave headroom for a
   week's growth. The 1 GB figure stood in for the cold start, and the **400 MB gzip trigger** in 8
   below, which measures that directly, is unchanged. The storage stays at 4,096 MB. On
   2026-10-22 the index was 839,438,336 SQLite bytes, a peak of 1,678,876,672 at a swap (39.1%).
   The working is in [the search index data model](../data/search-index.md#the-functions-temporary-storage-while-one-index-replaces-another)
   and [the task's session report](../session-reports/v1-e39-t14-index-shrink-guard.md#the-storage-measurement).
7. **Expected cold start.** Lambda caps one execution environment at 625 Mbps, about 78 MB/s.
   - **A request to a new environment:** about 1 to 2 s to start Python, FastAPI and the adapter.
   - **The first search on that environment:** a further 2 to 4 s to download 110 to 220 MB at
     that cap, with decompression and hashing overlapped. That is 6 to 8 s at the 1 GB ceiling.
   - **A warm search:** `v1-e39-t03`'s measured 95th-percentile query time, plus the network.

   `v1-e39-t04` records the init duration from the function's `REPORT` lines, and `v1-e39-t02`
   records the index size.
8. **Why that is acceptable on a Chromebook.** The wait is on the server: the Chromebook only waits
   for one HTML response, so a low-end machine sees the same delay as a fast one. It happens once
   per execution environment, and an environment then serves every request until Lambda retires
   it. It usually lands on the first search after sign-in, a few seconds after the student spent
   longer than that typing a password and a code. **Revisit trigger:** if `v1-e39-t02` measures
   the gzipped index above 400 MB, about 5 s at the cap, `v1-e39-t04` asks for a higher bandwidth
   quota. The quotas page says functions outside a VPC can request one, scaling from 2,048 MB of
   memory. Only if that is refused does it weigh one provisioned environment.

### (d) Sign-in: Cognito managed login, coach-created accounts, TOTP required

**The pool,** `debate-<env>-tub`, one per environment.

- **Feature plan: Essentials.** Email MFA needs Essentials or Plus; Lite has neither email MFA nor
  managed login. Essentials includes 10,000 monthly active users that do not expire, so 30 users
  cost nothing. Plus, at $0.020 a user with no free tier, adds threat protection the pilot does not
  need. The plan can be switched later.
- **Sign-in by username.** No username attributes and no alias attributes: email can never be a
  sign-in name. Usernames are case-insensitive. Cognito fixes both settings at creation, so they
  hold for V2 too.
- **No required attribute.** In particular, email is not required, and Cognito never lets that
  change after creation. No custom attribute, and nothing beyond the username, the group and an
  email the student adds (gate item 9).
- **Administrator-created users only.** Temporary passwords are valid for 7 days, and the
  invitation message is suppressed, since there is no address to send it to.
- **Account recovery: `admin_only`.** There is no forgot-password flow; the coach resets.
- **Passwords:** at least 12 characters, with no character-class rules.
- **MFA:** `ON` (required). The authenticator app (software token) and email messages are enabled;
  no SMS configuration exists. Device remembering is off.
- **Email:** sent through the pool's own SES identity (`DEVELOPER` sending account), which is what
  makes email MFA available.
- **Email verification:** a new email is held unverified until confirmed
  (`attributes_require_verification_before_update`).
- **Groups:** `coach` and `student`. V2 adds `administrator`.
- **Deletion protection:** on in prod.

**Managed login,** not the classic hosted UI. It is served at the login host as a custom domain,
with managed login version 2 and a `TLS_V1_2_2021` security policy. Cognito creates no branding for
an app client made through the API, and provider 5.100.0 has no resource for one. So
`v1-e39-t04`'s runbook creates the branding once with the CLI's
`create-managed-login-branding --use-cognito-provided-values`. Managed login handles the password,
the first-sign-in password change, TOTP setup with a QR code, and the MFA prompts. It does not do
profile changes such as adding an email or choosing a second factor, so the app's account page
does those.

**One confidential app client,** `debate-<env>-tub-web`.

- **Secret and flow:** a generated client secret; authorization code with PKCE (`S256`) only;
  provider `COGNITO` only.
- **Scopes:** `openid` and `aws.cognito.signin.user.admin`. The second lets the server call the
  token-authorized self-service APIs for the account page.
- **Attributes:** reads `email` and `email_verified`; writes `email` only.
- **URLs:** the callback is `https://<pilot host>/auth/callback`; sign-out returns to
  `https://<pilot host>/signed-out`.
- **Token settings:** token revocation on; user-existence errors suppressed; refresh token rotation
  off. Token validities are in [Lifetimes](#lifetimes).
- **No password flow:** no explicit auth flow lets the app accept a password. The app never sees a
  password.

**The flow.**

1. An unsigned request is redirected to the managed login `/oauth2/authorize`. The redirect carries
   `state` and a PKCE challenge whose verifier is kept in a short-lived `__Host-tub_signin` cookie.
2. The callback checks `state` and exchanges the code at `/oauth2/token` with the client secret and
   the verifier. It verifies the ID token's signature, issuer, audience, expiry and `token_use`,
   then reads the role from `cognito:groups`.
3. It calls `GetUser` with the access token. **If the account has no authenticator registered,
   the app starts no session.** Managed login offers email as well as an authenticator at first
   setup when email MFA is enabled. A student who picked email is sent to the app's own
   *Set up your authenticator app* page instead (`AssociateSoftwareToken`,
   `VerifySoftwareToken`). That page renders the QR code on the server as inline SVG and never
   logs the secret. This keeps TOTP the main factor and email the fallback, as the fixed inputs
   say.
4. The app then sets the session cookie and discards the ID and access tokens.

**Where the session lives: an encrypted cookie, not a server-side store.**

- **The cookie.** `__Host-tub_session` is `HttpOnly`, `Secure`, `SameSite=Lax` and `Path=/`, with
  no `Domain`. It is encrypted and authenticated with AES-GCM under a key only the function holds.
- **Its contents:** the pool subject, the username, the role, the session's start and last-seen
  times, the time of the last revalidation, a CSRF token and the Cognito refresh token. No ID or
  access token is kept.
- **The download cart.** `v1-e39-t08`'s cart of up to 30 cluster ids is held in a second cookie of
  the same kind, `__Host-tub_cart`, so neither cookie nears the 4 KB limit. **Amended 2026-10-22
  (PM ruling, `v1-e39-t08`):** the cart is held in the browser's `sessionStorage`, not a cookie.
  It holds only card references, the server checks every one at download, and nothing about it
  needs to reach the server before then. It holds up to 8 cards, and is emptied on sign-out.
- **Why the token is still on the server's side.** No token is readable in the browser. The
  refresh token inside the cookie can be redeemed only with the client secret, which only the
  function holds.
- **Revalidation.** At most every five minutes the app redeems the refresh token at
  `/oauth2/token`. A coach's disable, reset or removal signs the user out globally, so the next
  revalidation fails and the session ends within five minutes, the gate's own standard.
- **Sign-out.** It revokes the refresh token at `/oauth2/revoke`, clears both cookies, and
  redirects through the pool's `/logout` endpoint. That endpoint clears the managed login's own
  session cookie, which would otherwise sign the next person on a shared Chromebook straight back
  in.
- **Keys and the secret.** The cookie key, a current and a previous one for rotation, and the
  client secret are SSM Parameter Store `SecureString` parameters under `/debate-<env>-tub/`. They
  are read once per cold start.

#### Lifetimes

| Lifetime | Value | Enforced by |
|---|---|---|
| Idle timeout | 60 minutes without a request | The app, from the cookie's last-seen time |
| Absolute session lifetime | 12 hours from sign-in | The app, and Cognito: the refresh token is valid 12 hours, so it cannot outlive the session |
| Revalidation (refresh) | At most every 5 minutes | The app, through the refresh grant |
| Access and ID tokens | 5 minutes, the minimum | Cognito. They are used once and discarded |
| Sign-in transaction (`state`, PKCE verifier) | 5 minutes | The app's `__Host-tub_signin` cookie, matching managed login's five-minute prompt timeout |
| Temporary password | 7 days | Cognito. After that the coach resets |
| Managed login's own session cookie | 1 hour, Cognito's fixed value | Cleared on sign-out through `/logout` |

The idle timeout matches the managed login cookie's hour: a session that ends from idleness leaves
no live managed login session behind it.

#### CSRF

- **The session cookie is `SameSite=Lax`.**
- **Every state-changing request is a POST** carrying the session's CSRF token in an
  `X-CSRF-Token` header. The app compares it in constant time.
- **Its `Origin` must equal the pilot's origin,** and `Sec-Fetch-Site` must be `same-origin`.
- **GET never changes state.** Recording a card-page view in the audit log is a record, not a
  state change.
- **The OAuth `state` parameter** guards the callback, and PKCE binds the code to the browser that
  asked for it.
- **The body-hash rule in (a) 3** means a request that did not come from the pilot's own script
  never reaches the app.
- **The app sends no CORS headers,** so a cross-origin script's preflight fails.

#### The account lifecycle

1. **The coach creates the account.** `tub users add <username> --role student` (`v1-e39-t05`, in
   `debate_cli`) calls `AdminCreateUser` with the username alone and the invitation suppressed. It
   adds the user to the group, writes the audit record, and prints a generated temporary password
   once, never logging it. The coach gives the username and temporary password to the student in
   person.
2. **First sign-in with the temporary password.** On the Chromebook the student opens the pilot.
   They are redirected to managed login, enter the username and the temporary password, and are
   asked for a new one.
3. **The password change.** The new password is at least 12 characters, set on managed login's
   page. The app never handles it.
4. **TOTP enrolment.** Because MFA is required, managed login next shows the setup step. The
   student chooses the authenticator app, scans the QR code with any authenticator app on their
   phone (HMAC-SHA1, six digits, 30 seconds), and enters a code. They are returned to the pilot
   and signed in. A student who chose email instead is sent to the app's enrolment page before any
   other page. Every later sign-in is username, password and a code.
5. **The optional backup email.** On the account page the student enters an address. The app calls
   `UpdateUserAttributes` with the access token, and Cognito emails a code through SES. The
   student enters it, the app calls `VerifyUserAttribute`, and then it enables both factors with no
   preferred one (`SetUserMFAPreference`). From then on managed login asks at each sign-in which
   factor to use. The account page can also remove the address. The audit record says an email was
   added or removed, never which. Until SES production access is granted, the fallback works only
   for verified test addresses.
6. **A coach's reset, for a lost password or a lost phone.** `tub users reset <username>` sets a
   new temporary password (`AdminSetUserPassword` with `Permanent` false), shown once. It removes
   the authenticator (`AdminDeleteSoftwareToken`, which the TOTP documentation names for a lost or
   reset phone) and signs the user out everywhere (`AdminUserGlobalSignOut`). At the next sign-in
   the student sets a password and enrols an authenticator again. A student with a new phone also
   goes to the coach for a reset: the account page offers no self-service replacement (corrected
   by the PM, 2026-10-21; see Consequences).
7. **Removing a student who leaves.** `tub users remove <username>` signs them out everywhere and
   calls `AdminDeleteUser`, which deletes the account and every attribute on it, the email
   included (gate item 9). Any session still open ends at its next revalidation, within five
   minutes. `tub users disable` is the reversible form, for a suspension. Each command writes the
   audit record. At the end of the season the coach removes everyone who has graduated or left the
   team, from `tub users list`.

### (e) The access audit: an append-only CloudWatch Logs group kept 400 days

1. **The group.** `debate-<env>-tub-audit`, with retention **400 days**, a value `PutRetentionPolicy`
   accepts. It is named so that ADR-0010's `debate-prod-*` deny reaches it, unlike the default
   `/aws/lambda/...` path. The function's own application log goes to a second group,
   `debate-<env>-tub-app`, kept 30 days, through the function's logging configuration.
2. **Append-only.**
   - **No API edits or deletes a single log event,** so a written record cannot be changed.
   - **The function role** may call only `logs:CreateLogStream` and `logs:PutLogEvents` on the
     audit group. It holds no delete, retention or policy action.
   - **Deletion protection is on for the group,** which blocks deleting it or its streams until
     someone turns the protection off. Provider 5.100.0, the version this repository locks, has no
     argument for it (checked from its schema on 2026-10-19). So `v1-e39-t04`'s runbook turns it on
     once with `aws logs put-log-group-deletion-protection`, and a check there reads it back.
   - **The organization trail** records any change to the group's protection or retention.
3. **Records** are one JSON object per event: format version, time, the actor's pool subject, role,
   action, and cluster ids or a count. Nothing else (gate item 4). Searches are counted, never
   recorded with their words (`v1-e39-t07`). The coach's `tub users` commands write their
   account-change records to the same group, in their own stream, under the coach's permission set.

### (f) Applies and deploys are operator-run

1. **Terraform.** A new module, `infrastructure/modules/evidence_search`, is called the same way
   from `envs/dev` and `envs/prod`, and the two roots differ only in their tfvars, as the website's
   do. It holds:
   - the ECR repository, the function, its URL and role, and the two log groups;
   - the CloudFront distribution and the certificate;
   - the user pool, its domain and app client, and the SES identity;
   - the parameters and the budget alarm;
   - two Identity Center permission sets per environment, below.

   The operator reads the plan and applies dev, then prod, as `debate-admin`. That is because
   creating permission sets needs break-glass, as it did for the website
   ([team-website runbook](../runbooks/team-website.md)).
2. **Terraform owns the configuration; the deploy script owns the code.** The function ignores
   changes to its image URI in Terraform. The first apply creates the repository, and the first
   deploy pushes an image before the function is created. `v1-e39-t04`'s runbook gives the order.
3. **`scripts/tub_deploy.sh dev|prod`,** run by the operator under the `TubDeployer` permission set:
   1. builds the `linux/arm64` image locally, with provenance attestations off;
   2. pushes it;
   3. points the function at the pushed image by digest (`repository@sha256:…`), never by tag;
   4. waits for `function-updated`;
   5. checks `/healthz` through CloudFront.

   Prod deploys run from a `main` worktree, as the site's do. `TubDeployer` may push to its own
   repository and update its own function's code, and nothing else. The repository keeps the last
   five images and scans on push.
4. **The index and the accounts.** `tub index publish` runs under the existing `EvidenceOperator`
   profile (`v1-e39-t02`, weekly through `v1-e39-t09`). `tub users` runs under the `TubAccounts`
   permission set: the administrative Cognito actions on its own pool, and `logs:PutLogEvents` on
   its own audit group.
5. **CI** builds and tests and never deploys. There are no GitHub OIDC roles until `v2-e10-t03`,
   and no long-lived keys (ADR-0012 decision 9).
6. **SES production access** is requested once, by the operator, after the first prod apply.
   - **Why it is needed:** the sandbox sends only to verified addresses, 200 messages a day.
   - **The request:** transactional mail, the pilot's URL, and the coach as contact.
   - **When:** right after the first prod apply, because AWS's first answer can take up to 96 hours.
   - **Scope:** sandbox status is per account and Region, so one grant covers dev and prod.

### (g) Monthly cost at 30 users

Assumptions, both environments together: about 40,000 requests a month, which is 30 debaters at
about three half-hour sessions a week plus the coach. About 300 cold environments a month. One prod
index of up to 0.5 GB kept in up to three versions. Up to 500 emails.

| Line | Usage | Price used | $/month |
|---|---|---|---|
| Cognito, Essentials | 30 monthly active users | 10,000 free, not expiring; then $0.015 each | 0.00 |
| SES | ≤ 500 emails (MFA codes, verification) | $0.10 per 1,000 | 0.05 |
| Lambda requests | 40,000 | $0.20 per million; 1M a month free | 0.00 |
| Lambda compute | 40,000 × 0.25 s × 2 GB, plus 300 cold loads × 6 s × 2 GB ≈ 24,000 GB-s | x86 rate $0.0000166667 per GB-s as an upper bound for arm64; 400,000 GB-s free | 0.00 |
| Lambda ephemeral storage | 3.5 GB above the included 512 MB, for ≈ 12,000 billed seconds | $0.0000000309 per GB-s | 0.01 |
| CloudFront | 40,000 requests, ≈ 4 GB out | Within the free allowances (the flat-rate Free plan lists 1M requests and 100 GB) | 0.00 |
| S3 storage | ≈ 1 GB of index versions in prod; a small synthetic one in dev | $0.023 per GB-month ([ADR-0010](0010-primary-aws-region.md), 2026-09-19) | 0.03 |
| S3 requests and KMS | ≈ 6,000 GETs (pointer and suppression checks, index downloads); the buckets use S3 Bucket Keys | Not read on this date; well under a cent at any published rate | 0.01 |
| ECR storage | Two repositories, up to five images of ≈ 0.3 GB each | $0.10 per GB-month | 0.30 |
| CloudWatch Logs | Audit and app logs, well under 1 GB | Not read on this date; inside the 5 GB free ingestion either way | 0.00 |
| Parameter Store, ACM, Route 53 records, the budget alarm | Standard parameters, public certificates, alias records in the existing zone, a budget with no actions | No charge (budgets: "monitor and receive notifications … free of charge") | 0.00 |
| **Total** | | | **≈ 0.40** |

**If every free tier ended, the total would be under $2 a month:** Cognito $0.45, Lambda about
$0.50, CloudFront about $0.40, the rest unchanged. Either way it fits ADR-0010's $25 and $50
budgets. The pilot's own budget alarm is set at $10 a month per environment.

### Where the code goes

- **`debate_core.domain` and `debate_core.application`.** Pure search logic, safe queries and
  ranking (`v1-e39-t03`), the index build (`v1-e39-t02`), the audit record, the session and
  lifetime rules, and the use cases behind these ports:
  - an index reader;
  - an index source;
  - a suppression-list reader;
  - an audit sink;
  - an account directory;
  - an identity-provider token client.

  No `fastapi`, `starlette`, `boto3`, `httpx` or `typer`, per the import contracts in
  `pyproject.toml`.
- **`debate_core.integrations`.** The adapters:
  - the SQLite FTS5 reader (stdlib `sqlite3`);
  - the index fetcher and suppression-list reader, in the existing `s3` adapter;
  - a new `cognito` adapter for the administrative and token-authorized APIs and the OAuth token
    and revoke endpoints;
  - a new `cloudwatch_audit` adapter.

  Each new adapter subpackage goes on the right side of the boto3 and httpx contracts in the pull
  request that creates it, as those contracts' comments require.
- **`packages/debate_api`.** An empty skeleton today. It gets the app factory, routes, Jinja
  templates, the static files, the session and CSRF middleware, and its composition root,
  `debate_api.container`. `debate_api` is on the boto3 contract's even-indirectly list today, which
  would forbid a composition root that builds S3 and Cognito adapters. `v1-e39-t05` moves it to the
  direct form the CLI is held to ("reaches the AWS SDK only through `debate_core.integrations`").
- **`debate_cli`.** `tub index build|publish` (`v1-e39-t02`) and the coach's `tub users
  add|list|reset|disable|remove` (`v1-e39-t05`).
- **`infrastructure/modules/evidence_search`** and both environment roots (`v1-e39-t04`).
  `docs/runbooks/evidence-search.md` holds the operator steps.

### The function's role, exactly

| May | On |
|---|---|
| `s3:GetObject` | `reports/tub/search/*`, current objects under `raw/`, and `manifests/_suppression/suppression-list.jsonl`, in its own environment's evidence bucket only. No `GetObjectVersion`, no list, no write |
| `kms:Decrypt` | That bucket's key, through S3 only (`kms:ViaService`) |
| `logs:CreateLogStream`, `logs:PutLogEvents` | Its audit group, and its application log group |
| `ssm:GetParameter` | Its own `/debate-<env>-tub/` parameters |

It holds no Cognito permission: the self-service calls are authorized by the user's access token,
and the token endpoint by the client secret. The evidence buckets' Block Public Access settings and
bucket policies are not touched (gate item 3).

### What V2 replaces and what it keeps

| Pilot piece | V2 | Fate |
|---|---|---|
| The user pools, their users, the `coach` and `student` groups, username sign-in, MFA required, the login host | E12 (`v2-e12-t01`) | **Kept.** V2 adds an `administrator` group and its own app clients to the same pool. Settings fixed at creation (username sign-in, case-insensitivity, no required email) bind V2 |
| The access-audit group and record shape | E35 (`v2-e35-t05`) | **Kept**, with V2's actions added. The 400-day append-only rule is the tub gate's item 4 too |
| The suppression-list wiring and the five-minute hide | E35 (`v2-e35-t05`) | **Kept**. The tub's takedown flow reads the same list |
| The search ports, query parsing, ranking rules, card rendering and provenance line in `debate_core` | E15, E35 | **Kept** behind the same ports; the SQLite reader is replaced |
| The SQLite FTS5 index | E15 | **Replaced** by OpenSearch Serverless, built from the store by indexer workers ([ADR-0004](0004-opensearch-is-derived-not-authoritative.md)) |
| The Lambda function, the cookie session and the server-rendered pages | E12 (`v2-e12-t02`–`t04`), E14, E35 (`v2-e35-t04`) | **Replaced** by the FastAPI service on API Gateway and Fargate, bearer tokens checked by `v2-e12-t03`, and the Next.js app. Whether `tub.wfbdebate.com` redirects there or retires is `v2-e14-t03`'s choice |

**How this record relates to ADR-0004.** ADR-0004 governs V2's search, and this record does not
change it. The pilot's index follows ADR-0004's rule: derived, rebuildable from the store, never
written to as truth, and swapped atomically by a pointer. Its SQLite reader is the kind of local
`SearchIndex` implementation ADR-0004 allows for V1.

**How this record relates to ADR-0012.** It adds a second distribution and two hostnames under the
team domain, and follows ADR-0012's rules: a private origin through OAC, headers at the edge, no
access logging, and operator-run deploys. It leaves the website's module and distribution as they
are. It is not an amendment to ADR-0012. `v2-e14-t03` still records the V2 app's hosting against
it.

### How each gate item is met

| Gate item | Met by | Proven by |
|---|---|---|
| 1. Policy approved; removal steps exercised | Suppression list read at most five minutes apart; rebuild, publish and prune after `caselist remove` | `v1-e39-t07`'s operator record in dev and prod |
| 2. Team-only access; coach-created accounts; password and second factor | Admin-only creation, no identity provider but `COGNITO`, MFA required, no session without an authenticator, a session on every route except `/healthz`, `/auth/callback`, `/signed-out` and `/static/` | `v1-e39-t05`'s authorization matrix; `v1-e39-t04`'s pool test |
| 3. No public reachability; only the function reads `raw/`, writing nothing; private, uncached responses | The role above; Block Public Access untouched; OAC; `private, no-store` | `v1-e39-t04`'s mocked plan test; `v1-e39-t07`'s exposure check |
| 4. Every access audited, nothing identifying, 400 days | (e); `uvicorn` access log off | `v1-e39-t07`'s audit tests and log scan |
| 5. Suppression governs the pilot | (c) 5; the index build drops suppressed occurrences | `v1-e39-t02` ac3; `v1-e39-t07` |
| 6. No sharing surface | No public links or share-by-link; since policy version 1.11, copy and download carry no provenance line and their audit record names the card | `v1-e39-t06`, `v1-e39-t08`, `v1-e39-t11` |
| 7. Attribution and the "Disclosed evidence, not platform-verified" label | Rendered by `debate_core`, the provenance line and the label shown on every card page | `v1-e39-t06` |
| 8. Nothing beyond school plus team code; never searchable | Provenance in stored, unindexed columns; the query parser has no field for them | `v1-e39-t02` ac2; `v1-e39-t03` ac1 |
| 9. Least personal data; removal deletes the account | (d): username, group, optional email; `AdminDeleteUser` | `v1-e39-t04` ac3; `v1-e39-t05` |
| 10. School review | Answered (open question 6) | The policy |

### Dev

The dev pool holds the maintainer and synthetic users only (ADR-0013). The dev pilot serves
`v1-e39-t10`'s synthetic seed index. Under the policy's
[dev exception](../policies/caselist-data-use.md#dev-environment-exception) the operator may also
publish a real-corpus index to dev for validation, because only operators have accounts there.

## Consequences

- **The pilot costs well under a dollar a month** and adds nothing that runs when no one is using
  it. Idle means no charge beyond ECR storage.
- **The first search after a quiet spell waits a few seconds** while an environment fetches the
  index. That is the price of not running a server. It is bounded by the index's size, which
  `v1-e39-t02` measures, with a revisit trigger in (c) 8.
- **Every POST depends on the one first-party script.** A browser with script turned off can read
  but not copy, download, sign out or change its account. On the managed Chromebooks the pilot is
  for, script is on, and the Copy card feature needs it regardless. `v1-e39-t06` tests that every
  POST path sends the hash.
- **The app does some sign-in work itself.** Because managed login offers email at first setup,
  the app has its own authenticator-enrolment page, and that page handles a TOTP secret once. The
  secret is never stored or logged, and `v1-e39-t05`'s forbidden list already covers it.
- **A student without a phone cannot finish enrolment.** The fixed inputs make the authenticator
  the main factor, and school Chromebooks generally cannot install an authenticator. This is
  raised with the PM in the session report rather than worked around here.
- **Revocation is bounded, not instant.** A removed or disabled student's open session lasts up to
  five minutes, the same bound the gate sets for a removed card. A server-side store would make it
  instant, at the cost of a table, a read on every request and more IAM.
- **Three settings are runbook steps, not Terraform,** until the repository's AWS provider moves past
  5.100.0: the managed login branding, the audit group's deletion protection, and the login
  domain's minimum TLS version (`v1-e39-t04` found the third; corrected by the PM, 2026-10-20).
  Each has a read-back check in the runbook. Moving to provider 6 is a separate change, not part of the pilot.
- **The index is pinned to SQLite 3.40.0's features** for as long as the function runs on that
  base image. A newer FTS5 option needs a different base image first. A change to the declared
  Python also changes the base image, so it re-checks the SQLite version and FTS5 as (c) 1 did.
- **The kept pool binds V2.** It can never require email, sign in by email or be case-sensitive,
  and an immutable custom attribute can be written only at user creation. So V2's organization id
  cannot be an immutable attribute on accounts the pilot created. It belongs in the User record
  `v2-e12-t03` already provisions, or in a mutable attribute that no app client may write.
  `v2-e12-t01`'s criteria ac1 and ac3 need reading through this; it is raised with the PM.
- **Pruning superseded index versions needs a delete grant on `reports/tub/search/`.** The removal
  credential deliberately holds none on `reports/`, because a report holds no evidence. The pilot's
  index does hold card text. `v1-e39-t07` adds that one prefix to the removal side, in the store
  layout document and its IAM policy.
- **No self-service replacement of an authenticator in the pilot** (PM ruling, 2026-10-21, from
  `v1-e39-t05`'s dev runs). A new phone goes to the coach for a reset. On dev, Cognito's
  `AssociateSoftwareToken` behaved two ways. For an account whose authenticator was set up on the
  managed login page alone, starting a new association removed the old one at once
  (`AdminGetUser` listed no MFA setting before any confirm). For an account whose authenticator was
  registered through the app's page with `SetUserMFAPreference`, the old one was still listed six
  minutes later. The first is the common case. A replacement begun and not finished would leave
  enrolment open to anyone holding the student's password, and a reset's temporary password comes
  from the coach, so enrolment after a reset is never open to a password alone. A test holds that
  no route a full session can reach calls `AssociateSoftwareToken`. Re-allowing self-service
  replacement means measuring Cognito's behaviour first.
- **A copied or downloaded card carries no provenance line** (data-use policy version 1.11,
  Charlie's decision of 2026-10-22). The card page still shows it below the cite, and the copy's or
  download's audit record names the card cluster, so removal and attribution are unchanged. Copy
  card (`v1-e39-t11`), download (`v1-e39-t08`) and E33's built files (`v1-e33-t08`) follow the
  rule; `occurrence_provenance_line` stays in `debate_core` for the card page (added by the PM,
  2026-10-22).
- **SES production access is an AWS decision on AWS's clock.** Until it is granted, the email
  fallback reaches no student. TOTP sign-in and the coach's reset do not depend on it.

## Alternatives considered

**Lambda Web Functions,** announced 2026-10-12. CloudFront signs requests to them with
`UNSIGNED-PAYLOAD`, so a POST needs no body hash, which would remove (a) 3. Rejected because:
- their `/tmp` is fixed at 512 MB and their memory at 2 GB, so the index would not fit or would
  have to live in memory;
- they are a week old;
- the repository's provider has no resource for them.

They are the first thing to revisit if the index stays small or moves out of the function.

**A function URL with `AuthType NONE` and a secret header CloudFront adds.** This avoids the body
hash too. Rejected because the function would be callable from the internet and would run, at our
cost, to refuse each such call. OAC makes Lambda refuse it before the function is invoked.

**Lambda@Edge to compute the body hash at the edge.** Plain HTML forms would work without script.
Rejected because it is a second function, replicated worldwide and slow to change or delete
(ADR-0012 rejected it for the same reasons). The pilot needs script for Copy card anyway.

**API Gateway in front of the function.** It cannot be restricted to CloudFront except with the
same shared-secret header. It adds a per-request charge and a second place where timeouts and
payload limits are set. The function URL with OAC does what the pilot needs with nothing between.

**Fargate behind a load balancer,** the V2 shape. The load balancer alone costs more each month
than this whole design, and it needs the VPC egress design (ADR-0011) that V2 has not made yet.

**Next.js.** A static export cannot render per-user pages, and server rendering needs a Node
runtime beside the Python core, a second stack for one adult maintainer. A single-page app would
put tokens in the browser and more script on a Chromebook. Server-rendered HTML from the Python
that already holds the search logic is the smallest thing that works.

**Mangum.** An in-process ASGI adapter, mature, with a slightly faster cold start than the
adapter's separate process. Rejected because it ties `debate_api`'s entry point to Lambda's event
format. The Web Adapter keeps the app a plain ASGI server that runs the same way locally, in tests
and in V2's container.

**The index in the image.** The fastest cold start, since Lambda lazily loads image layers. It
would put personal data in ECR, outside the places the policy allows, and tie every weekly refresh
and every removal to a deploy.

**EFS.** It would need the function in a VPC, with NAT or endpoints to reach S3, Cognito and
CloudWatch, at several dollars a month each, and ADR-0011's undecided egress design.

**Reading SQLite pages straight from S3 by range request.** Every FTS5 query touches many pages,
and each would be a round trip of tens of milliseconds.

**OpenSearch Serverless now.** ADR-0004's eventual engine. At ADR-0010's $0.24 per OCU-hour even
two half-OCUs cost about $175 a month, many times the budget, for 46,000 documents.

**Custom sign-in pages calling `InitiateAuth`.** These would control the MFA setup offer exactly.
Rejected because the app would then handle every password and every TOTP secret, which is more
code to get wrong for no gain in what the student sees.

**The classic hosted UI on the Lite plan.** Lite has no email MFA, so the fixed fallback rules it
out. Essentials costs nothing at our size.

**A public app client with tokens in the browser.** More script, and tokens a cross-site scripting
bug could read. The confidential client keeps them away from the page.

**A server-side session store in DynamoDB.** It gives instant revocation and a tiny cookie, and fits
ADR-0002. Rejected for the pilot because it adds a table, a read on every request and more IAM,
for a revocation bound the gate already accepts at five minutes.

**The Plus plan.** Threat protection and compromised-password checks, at $0.020 a user with no free
tier. Not needed for 30 coach-created accounts behind MFA. The plan can be switched at any time,
so V2 can take it.

**An S3 bucket with Object Lock, or a DynamoDB table, for the audit.** Both can be made
append-only, with more to build and check. A log group's events cannot be edited by any API, and
retention is a single setting.

**A GitHub Actions deploy before OIDC.** It would need long-lived keys, which ADR-0012 decision 9
forbids. The operator deploys, as for the website, until `v2-e10-t03`.

## References

- [§9](../architecture/architecture_proposal.md#9-search-and-retrieval-architecture),
  [§12](../architecture/architecture_proposal.md#12-v2-detailed-architecture),
  [§14](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety),
  [§15](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls),
  [§17](../architecture/architecture_proposal.md#17-deployment-and-evolution-plan) of the
  architecture proposal
- [ADR-0004: OpenSearch is a derived index](0004-opensearch-is-derived-not-authoritative.md):
  unchanged, and still governs V2's search
- [ADR-0006: Exact-source evidence verification](0006-exact-source-evidence-verification.md): the
  label on every card page
- [ADR-0010: One account in us-east-1](0010-primary-aws-region.md),
  [ADR-0012: Web hosting](0012-web-hosting.md),
  [ADR-0013: Two environments](0013-two-environments-and-dev-main-promotion.md)
- [The caselist data-use policy, E39 gate](../policies/caselist-data-use.md#e39--student-evidence-search-pilot-v17)
- [The evidence store layout](../architecture/evidence-store-layout.md)
- [The epic](../../plan_specs/v1/e39-evidence-search-pilot/epic.yaml) and its tasks
  [`t02`](../../plan_specs/v1/e39-evidence-search-pilot/t02-search-index-build.yaml) to
  [`t10`](../../plan_specs/v1/e39-evidence-search-pilot/t10-pilot-smoke-and-review.yaml);
  [`v2-e12-t01`](../../plan_specs/v2/e12-identity-api/t01-cognito-user-pool.yaml) and its PM
  amendment
- [The task that owns this record](../../plan_specs/v1/e39-evidence-search-pilot/t01-pilot-architecture-adr.yaml)

### AWS documentation relied on, read 2026-10-19

| Claim | Source |
|---|---|
| Email MFA needs Essentials or Plus; managed login is Essentials and Plus, the classic hosted UI every plan; the plan can be switched | [User pool feature plans](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-sign-in-feature-plans.html) |
| Essentials $0.015 a user beyond 10,000 free, not expiring; Plus $0.020 with no free tier | [Amazon Cognito pricing](https://aws.amazon.com/cognito/pricing/) |
| MFA required; with email and TOTP both enabled, setup offers both and managed login collects the email; `SELECT_MFA_TYPE` with no preference; email MFA needs the pool's own SES configuration | [Adding MFA to a user pool](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa.html) |
| Managed login prompts TOTP setup with a QR code; `AdminDeleteSoftwareToken` for a lost or reset phone; HMAC-SHA1 codes | [TOTP software token MFA](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa-totp.html) |
| Managed login versus the classic hosted UI; no self-service profile changes; the one-hour session cookie; no branding for an API-created client until one is created | [User pool managed login](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-managed-login.html) |
| Custom domain: ACM certificate in us-east-1, the parent domain's `A` record, managed login needs `TLS_V1_2_2021` or higher | [Using your own domain for managed login](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-add-custom-domain.html) |
| Administrator-only creation, `FORCE_CHANGE_PASSWORD`, suppressed invitations | [Creating user accounts as administrator](https://docs.aws.amazon.com/cognito/latest/developerguide/how-to-create-user-accounts.html) |
| Required attributes and sign-in attributes fixed at creation; immutable custom attributes written only at creation | [Working with user attributes](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-attributes.html) |
| Username case sensitivity immutable; `MfaConfiguration`; `AccountRecoverySetting`; `DeletionProtection`; `UserPoolTier` | [CreateUserPool](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_CreateUserPool.html) |
| Refresh token 60 minutes to 10 years; rotation; global sign-out and the `/logout` endpoint | [Refresh tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html) |
| SES sandbox limits, per Region; production access by console or `put-account-details`; first response within 96 hours | [Request production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html) |
| SES $0.10 per 1,000 emails | [Amazon SES pricing](https://aws.amazon.com/ses/pricing/) |
| Container image 10 GB; `/tmp` 512 to 10,240 MB; 6 MB buffered response; 625 Mbps per environment, raisable outside a VPC; Web Functions' fixed 512 MB `/tmp` and 2 GB memory | [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html) |
| The Lambda runtime for the declared Python is on Amazon Linux 2023, deprecated 2028-10-31 | [Lambda runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html) |
| Lambda request, compute and ephemeral-storage prices and free tier | [Lambda pricing](https://aws.amazon.com/lambda/pricing/) |
| The Web Adapter's current version, extension install, function URL support, readiness check, invoke modes | [aws-lambda-web-adapter](https://github.com/awslabs/aws-lambda-web-adapter) |
| Mangum's function URL support | [Mangum](https://github.com/Kludex/mangum) |
| OAC for a function URL: `AWS_IAM`, both invoke permissions, and the `x-amz-content-sha256` requirement for PUT and POST | [Restrict access to a Lambda function URL origin](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-lambda.html) |
| Web Function origins signed with `UNSIGNED-PAYLOAD`; `AllViewerExceptHostHeader` | [Restrict access to a Lambda Web Function origin](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-lambda-web.html) |
| CloudFront flat-rate Free plan allowances | [CloudFront pricing](https://aws.amazon.com/cloudfront/pricing/) |
| 400 is an accepted retention value | [PutRetentionPolicy](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_PutRetentionPolicy.html) |
| Log group deletion protection | [Protecting log groups from deletion](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/protecting-log-groups-from-deletion.html) |
| ECR $0.10 per GB-month; free transfer to Lambda in the Region | [Amazon ECR pricing](https://aws.amazon.com/ecr/pricing/) |
| Budgets without actions are free | [AWS Budgets pricing](https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/) |

Checked by running rather than reading, 2026-10-19:
- **FTS5 in the base image.** The base image at the declared Python's tag, created 2026-10-15, run
  on `linux/amd64` and `linux/arm64`. It reports SQLite 3.40.0 and `ENABLE_FTS5`, and a `bm25()`
  and `highlight()` query over an FTS5 table succeeded. The exact tag and patch release are in the
  [session report](../session-reports/v1-e39-t01-pilot-architecture-adr.md).
- **The repository's AWS provider.** Its 5.100.0 schema has no managed login branding resource and
  no log group deletion-protection argument. It does have `user_pool_tier`,
  `email_mfa_configuration`, `deletion_protection`, the domain's `managed_login_version` and
  `aws_lambda_function_url`.
