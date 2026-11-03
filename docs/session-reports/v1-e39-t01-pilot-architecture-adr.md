# Session report: v1-e39-t01-pilot-architecture-adr

| | |
|---|---|
| Task | `v1-e39-t01-pilot-architecture-adr` — ADR-0019: the student search pilot's stack, sign-in and hosting |
| Spec | [`plan_specs/v1/e39-evidence-search-pilot/t01-pilot-architecture-adr.yaml`](../../plan_specs/v1/e39-evidence-search-pilot/t01-pilot-architecture-adr.yaml) |
| Epic / release | `v1-e39-evidence-search-pilot` / `v1.7` |
| Branch | `task/v1-e39-t01-pilot-architecture-adr` |
| Session status | COMPLETE |

## Summary

[ADR-0019](../adr/0019-student-search-pilot-stack-sign-in-and-hosting.md) is written as Accepted
and indexed in [docs/adr/README.md](../adr/README.md); the reservation row is gone. It confirms
most of the PM's proposed stack. It changes or adds five things that current AWS documentation
forced:

- **POST requests.** CloudFront's OAC in front of a function URL requires every POST to carry the
  SHA-256 of its body. The pages' one first-party script sends it.
- **The authenticator.** Managed login offers emailed codes as well as an authenticator at first
  setup. The app starts no session until an authenticator is registered, and has its own
  enrolment page for that case.
- **Index transfer.** Lambda caps one execution environment at 625 Mbps, so the index is published
  gzipped.
- **SQLite version.** The Lambda image's SQLite is 3.40.0, below the operator's 3.50.4, so the
  index is pinned to 3.40's features.
- **Runbook steps.** The repository's AWS provider (5.100.0) has no managed login branding
  resource and no log-group deletion protection, so both become runbook CLI steps.

The phase is Succeeded, as the PM directed: the coach's acceptance under ac1 is his merge after
review. Look first at the eight questions in [PM questions](#pm-questions). Several are wording
amendments to later E39 specs and to `v2-e12-t01` that the ADR's decisions imply.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `adr` — ADR-0019 written and accepted | Done | ADR written, README moved, docs checks green; acceptance is the coach's merge |

## Acceptance criteria

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| ac1 — ADR-0019 in the template's form records (a) to (g), each with the alternative considered and the AWS documentation by URL and date read; the coach accepts it in the PR | PASS (acceptance by merge) | The ADR has the template's sections: Status, Context, Decision, Consequences, Alternatives considered, References. Decision subsections (a) to (g) are each answered. *Alternatives considered* has 19 entries covering each of (a) to (g). *AWS documentation relied on, read 2026-10-19* lists 22 claims with their URLs, plus two run checks. The coach's acceptance is his merge, per the PM's note |
| ac2 — expected index size from the stored-card count, how the function gets it, the cold start, why acceptable on a Chromebook | PASS | Decision (c) 6 to 8. About 46,000 documents (233,643 cards, 46,069 clusters), 280 to 550 MB, planned to 1 GB. Downloaded gzipped to `/tmp` on the first request that needs it. About 1 to 2 s init plus 2 to 4 s index at the 625 Mbps cap. The reasons it is acceptable, and a revisit trigger at 400 MB gzipped. `v1-e39-t02` measures |
| ac3 — the account lifecycle end to end | PASS | Decision (d), *The account lifecycle*, steps 1 to 7: create, first sign-in with a temporary password, password change, TOTP enrolment (and the email-at-setup case), optional backup email, the coach's reset for a lost password or phone, remove and disable |
| ac4 — README indexes ADR-0019 and moves the reservation; `docs_index.py --check-descriptions` and `check_links.py` pass | PASS | `uv run scripts/check_links.py` → `OK: 1769 relative links and anchors in 258 Markdown files`. `uv run --frozen scripts/docs_index.py --check-descriptions` → `All 36 indexed documents under docs/ have a description` |
| Node `adr` — Docs index and links pass (`uv run scripts/check_links.py`) | PASS | As ac4 |
| Epic node t01 — `uv run scripts/validate_specs.py --require-succeeded v1-e39-t01-pilot-architecture-adr` | PASS | → `v1-e39-t01-pilot-architecture-adr: Succeeded`, exit 0 |

**Making the link check fail.** I changed one in-page anchor in the ADR to
`#c-the-index-broken-anchor` and re-ran the checker. It reported `1 broken link(s) in 258 Markdown
files` and named the line. Restoring it gave the pass above.

`check_links.py` reads tracked files only. Its first run, before the ADR was committed, covered
257 files and so had not yet seen the ADR. The figures above are from after the commit.

**Other checks run before this report (working agreement 10; a docs task, no test suite):**

- `uv run --frozen scripts/check_command_blocks.py` → `OK: no # comments in 280 shell code blocks
  in 123 Markdown files`.
- `uv run scripts/validate_specs.py` → `OK: 392 files, 39 epics, 332 tasks, 21 releases`.
- A scan of the ADR and README for a school name or email address found nothing:
  `grep -n -i -E "whitefish|@[a-z0-9-]+\.[a-z]|gmail|ctcb"`, apart from the `repository@sha256`
  digest syntax.

## Files changed

- `docs/adr/0019-student-search-pilot-stack-sign-in-and-hosting.md`: new, the record.
- `docs/adr/README.md`: the 0019 row added to the Index, the reservation row removed, and 0019
  named in the list of reservations that moved.
- `plan_specs/v1/e39-evidence-search-pilot/t01-pilot-architecture-adr.yaml`: Goal phase
  `Succeeded`.
- This report.

## Deviations from the spec

- **The ADR's date is 2026-10-19, the day it was written.** The PM asked for the date the pull
  request merges, which a session cannot know. If it merges on another day, the date in the ADR's
  header and in the README row changes at merge.
- **The architecture proposal is not extended.** The README's ADR process says to extend it when a
  decision is not covered. The pilot is a V1-scoped piece the proposal does not describe. Like
  ADR-0012 and ADR-0013, the ADR records the change and leaves the proposal's text alone.
- **The ADR decides things later specs word differently.** The details are in the
  [PM questions](#pm-questions). No other spec was edited.

## Decisions and assumptions

Summarised here; the reasoning is in the ADR.

- **(a) Hosting.** A function URL with `AWS_IAM` behind an OAC. Every POST is sent by the
  first-party script with `x-amz-content-sha256`, as the CloudFront documentation requires.
  arm64, 2,048 MB of memory, 4,096 MB of ephemeral storage, 30 s, reserved concurrency 10. The
  login host is `auth.tub.wfbdebate.com` (dev: `auth.tub.dev.wfbdebate.com`).
- **Lambda Web Functions.** Launched 2026-10-12, they would avoid the body hash. Rejected: `/tmp`
  is fixed at 512 MB and memory at 2 GB, the service is a week old, and the repository's provider
  has no resource for it.
- **(b) The app.** The Lambda Web Adapter, not Mangum, so `debate_api` stays a plain ASGI app that
  also runs under `uvicorn` and later in V2's container. `uvicorn --no-access-log`, because access
  lines hold client addresses and query strings.
- **(c) The index.** Downloaded from S3 on the first request that needs it, never baked into the
  image: ECR is not one of the places the policy allows personal data. Published gzipped, with the
  sha256 of the object and of the file. Pinned to SQLite 3.40.0's features; FTS5 was confirmed by
  running the Lambda image itself on amd64 and arm64.
- **(d) The session.** An AES-GCM encrypted `__Host-` cookie holding the refresh token and claims,
  not a DynamoDB store. Revalidated at most every five minutes, so a coach's removal ends a session
  within five minutes. Lifetimes: idle 60 minutes, absolute 12 hours, refresh token 12 hours,
  access and ID tokens 5 minutes. CSRF: SameSite=Lax, a synchronizer token in a header, `Origin`
  and `Sec-Fetch-Site` checks, `state` and PKCE.
- **(d) The pool.** Essentials, username only, case-insensitive, nothing required, admin-only
  creation and recovery, MFA `ON`, a password of 12 characters or more, no custom attribute.
- **(e) The audit.** The groups are named `debate-<env>-tub-audit` and `debate-<env>-tub-app` so
  that ADR-0010's `debate-prod-*` denies reach them. Deletion protection is set by CLI in the
  runbook.
- **(f) Deploys.** Two new permission sets per environment, `TubDeployer` and `TubAccounts`. The
  function is updated by image digest, and Terraform ignores the image URI.
- **(g) Cost.** About $0.40 a month for both environments, and under $2 if every free tier ended.
  Two lines had no price read on this date: S3 requests and CloudWatch Logs. The ADR says so for
  each, and either is under a cent at any published rate.
- **The index size is an estimate, not a measurement.** The PM offered a sizes-only command
  against the operator's store. I did not use it: the parsed store's file sizes include document
  records that the index does not hold, so they would bound the size without measuring it.
  `v1-e39-t02`'s ac6 records the real figure.
- **The managed login asset host.** The documentation does not say which hosts the managed login
  pages load assets from. The ADR has `v1-e39-t04` record them in dev before the request goes to
  school IT, rather than guess.
- **Running the base image.** I pulled `public.ecr.aws/lambda/python:3.12` (both architectures)
  and ran a probe in it. This made no AWS call on the operator's profiles; the image is public.
- **The provider schema.** Read offline from the 5.100.0 binary already cached in the main
  checkout's `.terraform`, in a scratch directory with no state.

## PM questions

```text
PM questions from v1-e39-t01-pilot-architecture-adr (ADR-0019), 2026-10-19

1. A student with no phone. TOTP is the fixed main factor, and managed school Chromebooks generally
   cannot install an authenticator, so a debater without a smartphone cannot finish enrolment. The
   ADR raises this rather than working around it.
   Options:
   (a) Such a student does not join the pilot.
   (b) The coach puts them in a Cognito group, for example email-second-factor, and the app accepts
       a verified email as their only factor. That is a group, not a personal attribute.
   (c) The student uses a desktop authenticator at home only.
   Recommendation: ask Charlie how many of the 3 to 5 pilot debaters lack a phone. Build (b) only
   if any do.

2. v1-e39-t04's description of the function role says "write only to its audit log group". The
   ADR also gives the function:
   - its own app log group, debate-<env>-tub-app, kept 30 days;
   - ssm:GetParameter on two SecureString parameters, the client secret and the cookie keys.
   It also adds two permission sets per environment, TubDeployer and TubAccounts, and a runbook
   CLI step each for the managed login branding and the audit group's deletion protection.
   Recommendation: amend t04's description and ac2 to match ADR-0019's role table.

3. v1-e39-t05 says a session is required on every route except the health check and the sign-in
   callback. The ADR adds /signed-out and /static/, which holds only content-hashed assets with
   no data. The ADR also puts two things on the app side:
   - an account page: add, verify and remove the backup email; replace the authenticator;
   - the app's own authenticator-enrolment page, for a student who chose email at managed login's
     first setup.
   Neither is named in any spec, and t05 is the natural owner. t05 also has to move debate_api
   from the boto3 contract's even-indirectly list to the direct form the CLI uses.
   Recommendation: amend t05's description and criteria for all three.

4. v2-e12-t01 on the kept pool:
   - ac1's "requires verified email" can never hold: Cognito fixes required attributes at
     creation.
   - ac1's "threat protection in audit mode" needs the Plus plan, which can be switched on at any
     time.
   - ac3's immutable custom:organization_id cannot be written for any account the pilot created,
     because Cognito writes immutable custom attributes only at user creation.
   Recommendation: ac1 reads "email optional and verified when present, Plus when V2 wants threat
   protection". ac3 puts organization_id in the User record v2-e12-t03 already provisions, or in a
   mutable custom attribute that no app client may write.

5. v1-e39-t07 and the store layout. Pruning superseded index versions needs delete on
   reports/tub/search/. The layout document deliberately gives the removal credential nothing
   under reports/, because reports hold no evidence; the pilot's index holds card text.
   Recommendation: t07 adds reports/tub/search/ alone to the EvidenceRemoval side, in the layout
   document and the IAM policy.

6. v1-e39-t02 picks up three things from the ADR:
   - a gzip object (level 6, mtime 0, no name), with the sha256 of the object and of the SQLite
     file in the manifest;
   - no SQLite or FTS5 feature newer than 3.40.0, the Lambda image's version;
   - the building SQLite version and an index format version recorded in the manifest.
   Recommendation: a one-line amendment to t02's description. Its byte-identical criterion still
   holds.

7. The ADR's date. It is 2026-10-19. If the PR merges on another day, change the ADR header and
   the README row at merge.

8. Moving the AWS provider from 5.100.0 to 6.x would let Terraform own the managed login branding
   and the log group's deletion protection. That is not in E39's scope.
   Recommendation: file it as a separate infrastructure task after the pilot.
```

## Operator follow-ups

None for this task. The operator steps the ADR implies are owned by later tasks:

- the applies and deploys, the managed login branding and the deletion-protection CLI steps, and
  the SES production-access request: `v1-e39-t04`;
- the index build and publish: `v1-e39-t02`.

## Follow-up work

- An AWS provider 6.x upgrade, to bring the managed login branding and log-group deletion
  protection into Terraform. Question 8; no task exists.
- The spec amendments in questions 2 to 6, which are the PM's to make.

## CI fix after review

PR #344's `test (5)` part failed one test:
`tests/architecture/test_single_interpreter_source.py::test_no_python_version_is_named_outside_the_one_declaration`
(1 failed, 1897 passed). The ADR named the supported Python in seven lines: the base image's tag,
the `requires-python` value, the image's patch release, and the runtime row in the documentation
table. That test allows the version in one place, `packages/debate_core/pyproject.toml`'s
`requires-python`. The aggregate `ci` check failed only because `test (5)` did.

**Why it reached CI.** Before the report I ran the docs checks and no tests, reading "no test suite
at all" as excluding `tests/architecture` too. That suite reads every tracked file, docs included,
and running it would have caught this. For a docs task it belongs with the docs checks.

**The fix.** The ADR now points at the declaration and repeats no version:

- the base image is AWS's Lambda Python image at the tag of the Python that `requires-python`
  allows;
- (c) 1 states the image's SQLite version without the patch release;
- the consequence about the SQLite pin says a change to the declared Python re-checks SQLite and
  FTS5;
- the runtime row and the run-check line name "the declared Python".

No decision changed. The exact facts the probe found are recorded here, where the test permits
them: `public.ecr.aws/lambda/python:3.12`, image created 2026-10-15, Python 3.12.15, SQLite 3.40.0,
`ENABLE_FTS5`, on `linux/amd64` and `linux/arm64`.

**Run after the fix:**

- `uv run pytest -q tests/architecture/test_single_interpreter_source.py` → red before the edit
  (`1 failed, 22 passed`, naming the seven ADR lines), then `23 passed`.
- `uv run pytest -q tests/architecture tests/specs` → `181 passed`.
- `uv run scripts/check_links.py`, `uv run --frozen scripts/docs_index.py --check-descriptions`,
  `uv run --frozen scripts/check_command_blocks.py --base origin/dev` and
  `uv run scripts/validate_specs.py` → all pass.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless the last Verdict in
this report is ACCEPTED. A later review is appended after this one; this one is never edited. -->

**Verdict:** ACCEPTED
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:** PM, 2026-10-19

**Notes:**

Accepted, with the phase `Succeeded`. The coach's merge is the ADR's acceptance.

**The work itself:**

* **Decisive, as asked.** Each of (a) to (g) is decided, with its alternatives and the documentation
  read, and the five places current AWS documentation overrode my proposal are named up front.
* **The claims that would have bitten later were checked, not assumed:**
  * OAC's body hash on POST;
  * managed login offering email at first setup, closed by "no session without an authenticator";
  * the 625 Mbps cap that makes gzip worth it;
  * SQLite 3.40.0, confirmed by running the Lambda image on both architectures;
  * the provider's missing resources.
* **The index stays out of the image** because ECR is not a place the policy lets personal data
  live. That is reading the policy, not just the AWS docs.
* **The log group names fall under ADR-0010's prod denies.**
* **Turning down the sizes-only command was the right call.** File sizes would have bounded the
  index, not measured it, and t02 measures it.

**Rulings on the PM questions:**

1. **(b).** Charlie believes every debater has a phone and asked for a fallback anyway. The coach
   puts a phoneless student in an `email-second-factor` group, and the app accepts a verified email
   as that student's only second factor. It is a group, not an attribute, and the email is the one
   policy 1.10's E39 gate item 9 already allows. It goes into `v1-e39-t05` by PM amendment.
2. **Amend `v1-e39-t04`** to ADR-0019's role table, app log group, two SSM parameters, the
   `TubDeployer` and `TubAccounts` permission sets and the two runbook CLI steps.
3. **Amend `v1-e39-t05`** for `/signed-out` and `/static/`, the account page, the app's own
   authenticator enrolment page, and `debate_api` in the boto3 contract's direct form.
4. **Amend `v2-e12-t01`** as recommended: email optional and verified when present; Plus when V2
   wants threat protection; `organization_id` in the User record `v2-e12-t03` provisions, not an
   immutable custom attribute.
5. **Amend `v1-e39-t07`:** `reports/tub/search/` alone is added to the removal credential's delete
   side, in the layout document and the IAM policy.
6. **Amend `v1-e39-t02`** with the gzip object, both sha256 values, the 3.40.0 feature ceiling, and
   the building SQLite version and index format version in the manifest.
7. **The date** stays 2026-10-19 if it merges today. Otherwise the coach corrects the header and
   README row in the merge.
8. **The provider 6.x upgrade** goes on the deferred infrastructure list, after the pilot.

One more amendment of my own: **`v1-e39-t08`** keeps a downloaded file under the function's 6 MB
buffered response, or streams it, since a cart of 30 cards must never fail at the response limit.
