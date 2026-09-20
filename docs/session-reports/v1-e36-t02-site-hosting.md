# Session report: v1-e36-t02-site-hosting

| | |
|---|---|
| Task | `v1-e36-t02-site-hosting` — Site hosting infrastructure (ADR-0012) |
| Spec | [`plan_specs/v1/e36-team-website/t02-site-hosting.yaml`](../../plan_specs/v1/e36-team-website/t02-site-hosting.yaml) |
| Epic / release | `v1-e36-team-website` / `v1.6` |
| Branch | `task/v1-e36-t02-site-hosting` |
| Session status | PARTIAL — everything in the repository is done and checked. The two `terraform apply` runs and the live-site checks are operator steps that have not been run yet. The canonical domain changed mid-task from `wfbdebate.org` to `wfbdebate.com` after three failed registrations; see **Deviations** |

## Summary

ADR-0012 now records how the public team website is hosted: a Next.js static export in a private
S3 bucket served through CloudFront with origin access control, HTTPS only, security headers set
at the edge, **no access logging**, dev as a non-indexable preview and prod as the public site,
with the V2 app later mounting under the same domain. Two Terraform modules implement it —
`static_site` (bucket, OAC, distribution, viewer-request function, headers policy, certificate,
DNS, and the least-privilege `SitePublisher` permission set) and `domain_redirect` (the `.com`
names, which hold no content and 301 to the canonical `.org` site). Both are wired into
`envs/dev` and `envs/prod` from a `site.tf` that is character-for-character identical in the two
roots; the environments differ only in `terraform.tfvars`, as every other file in those roots
already did.

Mid-task the operator supplied the real domains and new requirements — a preview host that is
never indexed, `www` redirecting to the apex, and a second registrable domain 301ing to the first.
That was a scope change, so it went into the spec first (ac6, ac7, the `domain-redirect-module`
plan node and two new forbidden rules) and then into the code. The intended canonical name,
`wfbdebate.org`, then turned out not to be registrable: three `REGISTER_DOMAIN` attempts failed in
under a second each with no reason given, an AWS Support case is open, and the canonical name moved
to `wfbdebate.com`, which is registered and delegated. `modules/domain_redirect` is built, tested
and simply not instantiated: if `.org` is ever issued it becomes the redirect, by two lines of
tfvars. See **Deviations**.

The PM should look first at two things: the **`.com` redirect is a CloudFront Function, not an S3
website redirect bucket**, because that endpoint is plain HTTP and public and the spec forbids
both — the module creates no bucket at all; and **both site applies have to run as
`debate-admin`**, because the roots now create an Identity Center permission set and
`DebateMaintainer` is denied `sso:Create*` by the guardrail that separates dev from prod. The
runbook says so and proves it with `simulate-principal-policy` before anything is applied.

## Plan nodes

| Node | Status | Notes |
|---|---|---|
| `adr-0012` — ADR-0012 web hosting | DONE | `docs/adr/0012-web-hosting.md`, Accepted 2026-09-20. Moved 0012 from the reserved-numbers table into the ADR index. Four alternatives recorded with why each lost: Amplify Hosting, a district page, a hosted site builder, GitHub Pages, plus the two build-level ones (S3 website endpoint, Lambda@Edge) |
| `static-site-module` — bucket, OAC, distribution, headers | DONE | `infrastructure/modules/static_site/`. Also grew the certificate, DNS records and canonical-host redirect the operator's domains require |
| `module-tests` — offline `terraform test` | DONE | 11 runs, `mock_provider "aws"`, no credentials and no network |
| `domain-redirect-module` — the `.com` names | DONE | Added by the spec amendment. `infrastructure/modules/domain_redirect/`, 5 offline runs |
| `env-wiring` — dev/prod wiring and `SitePublisher` | DONE | `site.tf` identical in both roots; the redirect module is a `count` driven by tfvars, so dev does not instantiate it |
| `operator-apply` — applies and the domain steps | **PENDING OPERATOR** | The runbook is written with a paste-ready block per AWS action and its record tables left as `_pending_`. Nothing has been applied |

## Acceptance criteria

Terraform commands were run with every AWS environment variable unset and
`AWS_EC2_METADATA_DISABLED=true`, to show they need no account.

| Criterion | Status | Evidence (command → result) |
|---|---|---|
| **ac1** ADR-0012 accepted and indexed | PASS | `grep -m1 '^- Status: Accepted' docs/adr/0012-web-hosting.md` → `- Status: Accepted`; `grep -c '0012-web-hosting.md' docs/adr/README.md` → `1` |
| **ac2** `static_site` tests pass without credentials and assert the four PAB flags, OAC-only access, redirect-to-https, the headers policy and no logging | PASS | `terraform -chdir=infrastructure/modules/static_site test` → `Success! 11 passed, 0 failed.` Runs: `bucket_is_private_and_encrypted`, `bucket_policy_grants_only_this_distribution`, `viewers_are_on_https_and_nothing_is_logged`, `security_headers_are_sent`, `no_domain_means_the_cloudfront_domain_and_no_certificate`, `the_index_rewrite_is_published_at_the_edge`, `prod_serves_the_team_domain_and_redirects_www`, `an_external_registrar_gets_the_validation_records_as_an_output`, `dev_preview_is_not_indexable`, `publisher_permission_set_can_publish_and_nothing_else`, `no_identity_center_instance_means_no_permission_set` |
| **ac3** both roots instantiate the module with their own prefix, domains and noindex; the roots stay identical apart from tfvars and backend; both validate and the checks pass | PASS | `diff` of `main.tf`, `providers.tf`, `versions.tf`, `variables.tf`, `outputs.tf`, `site.tf` between `envs/dev` and `envs/prod` → no output; `terraform -chdir=infrastructure/envs/dev validate` and `…/prod validate` → `Success! The configuration is valid.` twice; `bash scripts/terraform_checks.sh` → `All Terraform checks passed.` (fmt, validate on all seven directories, tflint clean) |
| **ac4** `SitePublisher` allows only ListBucket, GetObject, PutObject, DeleteObject on its bucket and CreateInvalidation on its distribution, with the two SSO profiles | PASS | Test run `publisher_permission_set_can_publish_and_nothing_else` asserts the action set is exactly those five, that every statement is an `Allow`, that every resource is this environment's own bucket or distribution, and that the named publisher is assigned. Profile names come from `publisher_profile_name` (= `name_prefix`), so `debate-dev-site` / `debate-prod-site`; the runbook's step 7 carries the `~/.aws/config` stanzas |
| **ac5** the operator has applied dev and prod, and the runbook records dates, names, domains, DNS and certificate status, with every permission check via `simulate-principal-policy` | **NOT RUN** (runbook PASS, applies pending) | `docs/runbooks/team-website.md` exists with eight steps, fifteen paste-ready blocks, and four `simulate-principal-policy` checks and no attempted-action permission tests (`grep -c 'debate-prod-site'` → `8`). Every bash block parses (`bash -n`, 15/15). The record tables read `_pending_`: **no apply has been run** |
| **ac6** prod on `wfbdebate.com` with `www` redirecting, dev on `dev.wfbdebate.com` with noindex, per-environment ACM certificates in us-east-1, DNS validated | **NOT RUN** live; configuration PASS | Configured in `envs/*/terraform.tfvars` and asserted offline by `prod_serves_the_team_domain_and_redirects_www` and `dev_preview_is_not_indexable`. `wfbdebate.com` is registered (2026-09-20T17:11:33Z, Amazon Registrar) and delegated to four `awsdns` name servers, confirmed at the `.com` registry and at 1.1.1.1 and 8.8.8.8, so nothing blocks the apply. The live check is the runbook's steps 4 and 6 |
| **ac7** `domain_redirect` 301s a second registrable domain to the canonical host, with its own certificate and no S3 website endpoint; tests pass offline | Offline PASS; **not instantiated** | `terraform -chdir=infrastructure/modules/domain_redirect test` → `Success! 5 passed, 0 failed.` including `the_origin_is_never_a_public_bucket_or_a_website_endpoint`. `redirect_domain_names` is empty in both roots while there is only one registrable domain; ac7 as amended says wiring it up when `.org` is issued is a tfvars change and an apply, not new code |
| Node `adr-0012` — ADR accepted; index lists it | PASS | As ac1 |
| Node `static-site-module` — `main.tf` contains `aws_cloudfront_origin_access_control` and `aws_cloudfront_response_headers_policy` | PASS | `grep -c` → `2` and `2` |
| Node `module-tests` — `terraform -chdir=infrastructure/modules/static_site test` | PASS | `Success! 11 passed, 0 failed.` |
| Node `domain-redirect-module` — tests pass; `main.tf` contains `aws_cloudfront_function` | PASS | `Success! 5 passed, 0 failed.`; `grep -c aws_cloudfront_function` → `2` |
| Node `env-wiring` — dev validates, prod validates, `scripts/terraform_checks.sh` passes | PASS | As ac3 |
| Node `operator-apply` — runbook contains `debate-prod-site` | PASS | `grep -c` → `8` |
| Node `operator-apply` — custom: Charlie confirms private buckets, HTTPS, the three 301s and dev's noindex | **NOT RUN** | Awaiting the operator; the checks are runbook steps 4, 6 and 8 |

## Files changed

**`docs/adr/`** — `0012-web-hosting.md` (the decision) and a row in `README.md` moving 0012 out of
the reserved-numbers table.

**`docs/runbooks/team-website.md`** — new. Eight operator steps, each AWS action a paste-ready
block with where to run it, the exact command, expected runtime and what success looks like; four
`simulate-principal-policy` checks; record tables to fill in. Indexed in `docs/README.md`.

**`infrastructure/modules/static_site/`** — new module. `main.tf` (bucket and its six
configuration resources, bucket policy, OAC, viewer-request function, cache and headers policies,
distribution), `certificate.tf` (ACM certificate, validation records, validation wait, A/AAAA
aliases, a `check` that the region can serve CloudFront certificates), `publisher_access.tf` (the
`SitePublisher` permission set, its inline policy and assignments), `variables.tf`, `outputs.tf`,
`versions.tf`, `functions/site_request.js.tftpl`, `tests/static_site.tftest.hcl`, `README.md`,
`.tflint.hcl`.

**`infrastructure/modules/domain_redirect/`** — new module, same shape, for the `.com` names.

**`infrastructure/envs/dev/`, `infrastructure/envs/prod/`** — `site.tf` (new, identical in both),
plus the site variables and outputs appended to `variables.tf` and `outputs.tf` (also identical),
the per-environment values in `terraform.tfvars`, and `site_publisher_user_names` added to
`owner.auto.tfvars.example`.

**`infrastructure/README.md`** — the two new modules in the layout table and a section on how the
website is wired, which domain is canonical and why the zones are data sources.

**`plan_specs/v1/e36-team-website/t02-site-hosting.yaml`** — the scope change; see below.

## Deviations from the spec

**1. The spec was amended mid-task for the real domains, and the amendment was committed before
the code.** The operator supplied `wfbdebate.org` and `wfbdebate.com` and four requirements the
spec did not cover: a preview host carrying noindex, `www` redirecting to one canonical name, a
second registrable domain 301ing to the first with its own certificate, and hosted zones read by
data source rather than created. The spec's original text made the domain optional ("the default
`*.cloudfront.net` domain until then") and had no redirect at all. Changed, in commit
`Spec: wire the real team domains…`:

* Goal description records the domains, the canonical choice, the preview host, the redirect
  module and that zones are read, never managed.
* `constraints.packages` gained `infrastructure/modules/domain_redirect`.
* `constraints.forbidden` gained two rules: no creating, importing or destroying hosted zones or
  registrar settings from Terraform; no testing a permission by attempting the action instead of
  `simulate-principal-policy`.
* New `ac6` (the domains and certificates) and `ac7` (the redirect).
* New plan node `domain-redirect-module`; `env-wiring` and `operator-apply` re-described.

**1b. The spec was amended a second time when `wfbdebate.org` proved unregistrable**, in commit
`Spec: wfbdebate.com is the canonical domain…`. `ac6` now names the `.com` hosts; `ac7` no longer
requires the redirect to be *running*, only to be built, tested and wireable by tfvars, since
there is currently only one registrable domain to redirect from. The Goal description records why.
The modules did not change.

**2. The apex is canonical, and `www` redirects to it — but the apex is now `wfbdebate.com`, not
`wfbdebate.org`.** The operator asked for a choice of apex-vs-`www` and to say which: the apex is
shorter on a flyer and in a parent's address bar, and it leaves `www` free to be a plain alias.
The cost is that an apex cannot be a CNAME, which does not matter here because Route 53 alias
records point at CloudFront directly. Which *domain* is the apex then changed for the reason in
the follow-ups above: `.org` could not be registered, and the October 1 date is not worth risking
on an AWS Support queue. If `.org` arrives later it becomes a redirect rather than taking the
canonical spot back — moving a canonical URL after parents have it is worse than having the
second-choice TLD.

**3. The redirect is a CloudFront Function, not an S3 redirect bucket.** The spec offered either.
The bucket version needs the S3 **website** endpoint, which is plain HTTP, has to be public, and
cannot be restricted to a distribution — three things this task's `forbidden` list rules out.
`domain_redirect` therefore creates no bucket at all. Its distribution still names an
origin because CloudFront requires one; it names the real site over HTTPS, so a missing function
degrades to serving the site from the wrong name rather than to an error page.

**4. The TLS floor is AWS's, not ours, until the certificate is attached.** The spec forbids "TLS
below 1.2". A distribution using the CloudFront default certificate is forced by AWS to the
`TLSv1` security policy and rejects any other value, so `minimum_protocol_version` is set only
when a certificate of our own is in use — where the tests assert `TLSv1.2_2021`. This affects only
the `-var 'site_domain_names=[]'` escape hatch and is recorded in ADR-0012's consequences.

**5. `script-src` includes `'unsafe-inline'`.** A Next.js App Router static export emits inline
bootstrap scripts and has no server or middleware to issue a per-request nonce. `object-src
'none'`, `base-uri 'self'`, `frame-ancestors 'none'` and a site with no user input keep the
exposure small, and the policy is a module input so `v1-e36-t03-site-scaffold` can tighten it
without a module change. Recorded in ADR-0012.

**6. Two files outside the spec's `packages` list were touched**, both because
`docs/process/working-agreements.md` section 3 requires it: `docs/README.md` (a new document gets
a line in the index) and `infrastructure/README.md` (the module index the new modules belong in).

## Decisions and assumptions

* **The publisher permission set lives in the `static_site` module**, as the spec's
  `publisher_access.tf` output implies, rather than in `bootstrap/organization`. It is scoped to
  one environment's bucket and distribution, which are module resources, so this is the only place
  the scope can be written without naming those resources twice. The cost is that both site
  applies now create an Identity Center resource and so must run as `debate-admin`, since
  `DebateMaintainer` is denied `sso:Create*`. The runbook opens with that and step 2 proves it.
* **Policies are `jsonencode`, not `aws_iam_policy_document`.** A policy document data source
  renders to an opaque value under a mocked provider, and the bucket policy and the publisher
  policy are exactly what the tests need to read back. `bootstrap/` still uses data sources; it
  has no `terraform test`.
* **`s3:ListBucketVersions` was removed from the publisher policy** after first including it.
  ac4 says "only" those five actions, and `aws s3 sync --delete` does not need it.
* **The `bucket_suffix` reuses the state buckets' `a7508de8`.** S3 is a global namespace and the
  runbook and the deploy script have to be able to name the bucket without reading state, so it is
  a committed constant, as `v1-e29-t02` established.
* **Both 404 and 403 map to `/404.html`.** A private bucket answers a missing key with 403,
  because the distribution is deliberately not granted `s3:ListBucket`; without the mapping a
  mistyped URL would show CloudFront's XML error document.
* **`tflint`'s `aws_resource_missing_tags` is annotated away on five resources in the two
  modules.** The rule reads the provider's `default_tags`, which a module directory linted on its
  own does not have; linting `envs/dev` or `envs/prod` follows the module call and does check the
  tags. A `# tflint-ignore` with that reason was preferred over relaxing the module's
  `.tflint.hcl` (which `scripts/terraform_checks.sh` would then have to treat as an exception) or
  tagging every resource by hand against the convention in `infrastructure/README.md`.
* **Certificate validation waits 30 minutes, not the default 75.** A domain registered the same
  day needs time to delegate; an hour of a stuck apply teaches nobody anything, and re-running is
  free.

## Operator follow-ups

All of these are in [`docs/runbooks/team-website.md`](../runbooks/team-website.md), which has the
full block for each with its expected runtime and success criteria. In order:

0. ~~**Register `wfbdebate.org`.**~~ **Done as far as it can be: it cannot be registered, and the
   canonical name has moved to `wfbdebate.com`.** Nothing below is blocked any more. Checked
   2026-09-20 from public DNS, whois and `route53domains`:

   | Domain | Registry | Registration | Delegation |
   |---|---|---|---|
   | `wfbdebate.com` | Registered 2026-09-20T17:11:33Z, Amazon Registrar | `SUCCESSFUL` after 10m 12s | Four `awsdns` name servers, at the registry and at 1.1.1.1 and 8.8.8.8 |
   | `wfbdebate.org` | `Domain not found` at `whois.publicinterestregistry.org`; `check-domain-availability` → `AVAILABLE` | **`FAILED` three times**, in 0.90 s, 0.89 s and 0.70 s | None |

   The three failed operations are `4cb18c5e-dc01-4b99-8cff-b782eecf8cd5` (12:11:28),
   `f79d71d2-7ce8-47b4-825b-644a83fdc3bc` (13:03:20) and
   `cc87fa96-df2f-4004-8637-67211510a714` (13:04:26), all CDT, each carrying only the generic
   "We can't finish registering your domain. Contact AWS Support" message with no reason code.

   The timings are what identify the problem. A registration that reaches the registry takes
   minutes on this account — `wfbdebate.com` took 10m 12s and `credencesports.com` took 11m 34s —
   so a sub-second failure never left Amazon Registrar and was not PIR declining. The contact
   details, privacy settings and auto-renew were identical to the `.com` that succeeded 1.1
   seconds earlier in the same request, which rules out the contact data. **An AWS Support case
   was filed on 2026-09-20.**

   **Decision (operator, 2026-09-20): make `wfbdebate.com` the canonical name rather than wait on
   Support**, because the parent information session is on October 1. Prod now serves
   `https://wfbdebate.com/` with `www.wfbdebate.com` 301ing to it, and dev serves
   `https://dev.wfbdebate.com/`. `modules/domain_redirect` is unchanged in substance, built and
   tested, and instantiated by nothing: if `.org` is ever issued, uncommenting two lines in
   `envs/prod/terraform.tfvars` points the `.org` names at the `.com` site. The switch cost two
   `terraform.tfvars` files and prose — nothing in the modules or their 16 tests depends on which
   name is canonical, which is what the module inputs were for.

1. **Confirm both hosted zones are delegated** (~1 min) — runbook step 1, which now tells an
   unregistered domain apart from a slow delegation and includes `aws sso login`, because an
   expired token fails the `aws` calls while `dig` still answers.
2. **Confirm `debate-admin` can apply and `DebateMaintainer` cannot** (~2 min) — step 2, four
   `simulate-principal-policy` calls. `explicitDeny` on the Identity Center actions and on
   `debate-prod-*`; `allowed` on `debate-dev-*`.
3. **Write the two `owner.auto.tfvars`** (~1 min) — the "Before you start" block, with the email
   and your Identity Center user name. Without the user name the publisher permission set exists
   but nobody can assume it.
4. **Apply dev without the domain** (~8 min) — step 3a,
   `terraform -chdir=infrastructure/envs/dev apply -var 'site_domain_names=[]'`. **This one needs
   no DNS at all**, so it can be run today regardless of step 0, and it proves the bucket, the
   distribution, the function, the headers and the publisher permission set before a domain is in
   the picture.
5. **Apply dev with the preview host** (~10 min) — step 3b, plain `apply`. Needs step 0.
6. **Check dev** (~2 min) — step 4: four `True` flags, `AccessDenied` from a direct S3 URL, a 301
   from `http://`, and `x-robots-tag: noindex, nofollow`.
7. **Apply prod** (~15 min) — step 5. Two distributions and two certificates. Needs step 0; to
   bring prod up on its CloudFront domain meanwhile, empty both name lists together —
   `apply -var 'site_domain_names=[]' -var 'redirect_domain_names=[]'` — because a redirect with
   no canonical host to point at is refused by a `check` block in `site.tf`.
8. **Check prod and the three redirects** (~3 min) — step 6. All of `www.wfbdebate.org`,
   `wfbdebate.com` and `www.wfbdebate.com` must answer 301 with
   `location: https://wfbdebate.org/`, and a deep link must keep its path.
9. **Add the two publisher SSO profiles** (~3 min) — step 7, `~/.aws/config` stanzas plus
   `aws sso login`.
10. **Confirm the publishers are least-privilege** (~3 min) — step 8,
    `simulate-principal-policy` per publisher: `allowed` only against its own site bucket,
    `implicitDeny` against the other environment's bucket, the state bucket, IAM and CloudFront
    management.
11. **Fill in the runbook's two record tables** and paste the results back, so ac5, ac6, ac7 and
    the `operator-apply` node's custom criterion can be marked PASS and the Goal set to
    `Succeeded`.

Nothing here may be run from an agent session or from CI.

## Follow-up work

* **`v1-e36-t05-site-deploy` cannot use one profile for the whole deploy.** The `SitePublisher`
  permission set cannot read Terraform state, so `terraform output` has to run under
  `debate-admin` (or `debate-dev`) while the sync runs under the publisher profile. Worth writing
  into that task's spec before it is implemented.
* **`v1-e36-t05-site-deploy` cannot poll an invalidation.** ac4 lists five actions and
  `cloudfront:GetInvalidation` is not one, so `aws cloudfront wait invalidation-completed` will be
  denied. Either the script creates the invalidation and moves on, or ac4 gains a sixth action in
  a spec change. The PM decides which.
* **`v1-e36-t03-site-scaffold` may be able to tighten the CSP.** `content_security_policy` is a
  module input precisely so that it can. If the export turns out not to need `'unsafe-inline'` in
  `script-src`, tightening it is a tfvars change in both roots.
* **The dev preview is unauthenticated, only unindexed.** `dev.wfbdebate.org` is guessable.
  Nothing about students is published there before prod under the publishing policy, so this is
  acceptable now; if the preview ever holds real names or photos ahead of prod, it needs a basic
  auth CloudFront Function. That belongs to E36 or E37 as a small follow-up task, not here.
* **`v2-e14-t03-app-hosting` inherits a domain and a certificate.** The apex is taken by the
  public site, so the app needs a subdomain or a path behind the same distribution. ADR-0012 says
  that task amends it rather than superseding it.

## PM review

<!-- Completed by the PM only. scripts/task pr refuses to open a PR unless Verdict is ACCEPTED. -->

**Verdict:** PENDING
<!-- ACCEPTED / CHANGES_REQUESTED -->

**Reviewed by / date:**

**Notes:**
