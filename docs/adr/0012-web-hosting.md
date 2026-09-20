# ADR-0012: Web hosting — a static export on S3 and CloudFront, under one team domain

- Status: Accepted
- Date: 2026-09-20
- Deciders: Charlie Clark (product owner)
- Architecture references:
  - [§4 Technology Stack](../architecture/architecture_proposal.md#4-technology-stack)
  - [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture)
  - [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)
  - [§15 Reliability, Observability, and Cost Controls](../architecture/architecture_proposal.md#15-reliability-observability-and-cost-controls)

## Context

Release v1.6 (epic E36) puts a public website for the Whitefish Bay debate team in front of
parents and prospective students before the parent information session on **October 1, 2026**.
Nothing about it is hosted yet, and the choice has to be made before the site code
(`v1-e36-t03-site-scaffold`) or the deploy flow (`v1-e36-t05-site-deploy`) can be written.

What the decision has to fit:

- **The content is static.** Pages, a coach list, a parent FAQ, later an events calendar and
  announcements (E37) and a donate page that links out to the district's own payment method
  (E38). No accounts, no forms that store anything, no server-side rendering per request.
- **The audience includes minors and their families.** The publishing policy
  (`v1-e36-t01-publishing-policy`) governs what may appear about students at all;
  [§14](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety) and that
  policy also rule out third-party trackers, ad networks and embedded social widgets. Whatever
  hosts the site must not add analytics or beacons of its own, and must not need visitor IP
  addresses to be stored for the site to work.
- **The budget is a school team's.** V1 runs on a single AWS account shared with unrelated
  personal projects, under a $25/$50 monthly budget per environment
  ([ADR-0010](0010-primary-aws-region.md)). A parent site gets a few hundred visits a month.
- **There is one adult maintainer.** Anything with a monthly platform fee, a separate console to
  learn, or a second place where secrets live is a real cost here.
- **The foundation already exists.** `v1-e29-t02-terraform-bootstrap` left two Terraform roots
  (`infrastructure/envs/dev`, `infrastructure/envs/prod`) on per-environment remote state, in
  `us-east-1`, in one account, with a tagging standard and Identity Center permission sets. There
  are two environments and no third ([ADR-0013](0013-two-environments-and-dev-main-promotion.md)).
- **No domain has been bought yet.** The site has to be viewable and reviewable before a domain
  exists, and gaining one later must not mean rebuilding the hosting.
- **V2 needs the same domain.** The authenticated research app (`v2-e14-t03-app-hosting`) is a
  Next.js application with server-side behaviour, and it will live under the same team domain as
  this public site. This ADR's number was reserved for that decision; the public site is simply
  the first thing to land on it, and `v2-e14-t03` amends this record rather than replacing it.

## Decision

**The public team website is a static export served from a private S3 bucket through Amazon
CloudFront, with origin access control, in the existing account and region.** It is defined in
Terraform, in a reusable module called from both environment roots, and applied by the operator.

Specifically:

1. **Origin.** One S3 bucket per environment, `debate-dev-site-*` and `debate-prod-site-*`,
   following ADR-0010's `debate-<environment>-<purpose>` naming. The buckets are private: all four
   block-public-access flags on, `BucketOwnerEnforced` object ownership (so ACLs cannot grant
   anything), SSE-S3 default encryption, versioning on, and a bucket policy that denies
   non-TLS requests and allows `s3:GetObject` to exactly one principal —
   `cloudfront.amazonaws.com`, conditioned on this environment's distribution ARN. **S3 static
   website hosting endpoints are not used**, because they are plain HTTP and public by
   construction.
2. **Delivery.** One CloudFront distribution per environment, with an **origin access control**
   (SigV4), not a legacy origin access identity. `viewer_protocol_policy = redirect-to-https`,
   HTTP/2 and HTTP/3, compression on, `PriceClass_100` (North America and Europe — the audience is
   one Wisconsin suburb), the AWS managed `CachingOptimized` cache policy, and a custom error
   response that turns both 404 and the 403 that a private bucket returns for a missing key into
   the site's own `/404.html`.
3. **Clean URLs.** The site is a Next.js App Router export with trailing slashes
   (`v1-e36-t03-site-scaffold`), so a request for `/parents/faq/` has to reach the object
   `parents/faq/index.html`. A **CloudFront Function** on viewer request appends `index.html` to
   any URI ending in `/`, and `/index.html` to any extensionless URI. A function, not a
   Lambda@Edge: it runs in microseconds at the edge, costs a tenth as much, and this rewrite is
   the entire requirement.
4. **HTTPS and the certificate.** Until a team domain exists the site is served on its
   `*.cloudfront.net` domain with the CloudFront default certificate. Once a domain is bought, the
   environment sets `domain_names` and the module requests an **ACM certificate in `us-east-1`**
   (the only region CloudFront accepts certificates from — which the account already uses for
   everything else under ADR-0010), validated by DNS, and sets the distribution's minimum
   protocol version to `TLSv1.2_2021`.
5. **DNS is not owned here.** `route53_zone_id` is an input. When it is set, the module creates
   the validation records and waits for the certificate to be issued, so one apply is enough. When
   it is `null` — a domain kept at an external registrar — the module outputs the validation
   records for the operator to add by hand, and the apply is run twice. Buying the domain and
   editing DNS are operator steps in [docs/runbooks/team-website.md](../runbooks/team-website.md),
   never Terraform and never an agent session.
6. **Security headers come from the edge, not the pages.** A CloudFront response headers policy
   sets HSTS, a Content-Security-Policy, `X-Content-Type-Options: nosniff`,
   `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY` with
   `frame-ancestors 'none'`, and a `Permissions-Policy` that turns off camera, microphone,
   geolocation and interest-cohort access. A static export cannot set response headers itself, and
   putting them at the distribution means they apply to every object including ones a future task
   uploads.
7. **Dev is a preview, prod is public.** Both environments are real and identical in shape
   (ADR-0013); the dev distribution additionally sends `X-Robots-Tag: noindex, nofollow` so the
   preview cannot be indexed, alongside the `robots.txt` the dev build writes.
8. **No access logging.** Neither CloudFront standard logs nor real-time logs are enabled, so no
   per-request record of visitor IP addresses is created or stored. CloudFront's built-in
   popular-objects and usage reports, which are aggregate and retained by AWS, are the only
   traffic information the team gets. This is a deliberate trade — the site gives up per-page
   analytics — and it follows from the audience being schoolchildren and their families
   ([§14](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)).
   Turning logs on later is a spec change and a publishing-policy change, not a configuration
   tweak.
9. **Deploys are a sync, not a build service.** `v1-e36-t05-site-deploy` builds the export
   locally and syncs it to the environment's bucket, then invalidates the distribution. Until
   keyless GitHub OIDC deploy roles exist (`v2-e10-t03`), that is operator-run, with a
   least-privilege **SitePublisher** Identity Center permission set per environment that can do
   nothing but list, read, write and delete objects in its own site bucket and create
   invalidations on its own distribution. There are no long-lived AWS access keys.
10. **The V2 app mounts under the same domain.** The domain and its certificate are established
    here; `v2-e14-t03-app-hosting` adds the authenticated app on a subdomain (or a path behind the
    same distribution) and records that choice as a dated amendment to this ADR or a superseding
    one. The public site keeps its own bucket and distribution either way, so a problem in the app
    cannot take the parent-facing pages down.

**Revisit trigger.** Move off this design if the site needs server-side rendering, per-request
personalisation or authenticated pages — that is the V2 app's problem, and it is why
`v2-e14-t03` gets to amend this record rather than inherit it unchanged.

## Consequences

- Running cost is effectively the CloudFront free tier: S3 storage for a few megabytes, and
  requests well inside the perpetual free allowance. There is no monthly platform fee and nothing
  new to pay for until a domain is bought (roughly $15/year).
- Everything is in Terraform in the repository, so dev and prod cannot drift, and a rebuild from
  scratch is an `apply`. The module is the only place a change has to be made, and it is unit
  tested offline.
- **Publishing is a deliberate act.** Nothing reaches prod except an operator running the deploy
  script from `main`; there is no git-push-to-deploy that could put an unreviewed page about a
  student in front of the public.
- **No per-page analytics.** Nobody can answer "how many people read the FAQ" beyond CloudFront's
  aggregate reports. Accepted knowingly; the alternative is either a third-party tracker, which
  the publishing policy forbids, or an access log of visitor IPs, which the audience makes a bad
  idea.
- **Cache invalidation is now part of deploying.** A static export behind a CDN serves stale HTML
  until it is invalidated, so the deploy script has to invalidate, and the first 1,000
  invalidation paths a month are free. `t05` handles this by caching hashed `_next/static/`
  assets for a year and HTML not at all.
- **The `*.cloudfront.net` domain is temporary and its TLS floor is AWS's, not ours.** A
  distribution using the CloudFront default certificate is forced to the `TLSv1` security policy —
  AWS rejects any other value — so the TLS 1.2 floor this project wants only takes effect when the
  ACM certificate is attached. That is one more reason to buy the domain promptly, and it is why
  the module asserts `TLSv1.2_2021` whenever a custom certificate is in use.
- **The Content-Security-Policy has to tolerate Next.js's inline bootstrap scripts.** A static
  export has no server to generate a per-request nonce and no middleware to inject one, so
  `script-src` includes `'unsafe-inline'`. `object-src 'none'`, `base-uri 'self'`,
  `frame-ancestors 'none'` and a site with no user input keep the exposure small, and the policy
  is a module input so `t03` can tighten it if the export turns out not to need it.
- **Two applies when DNS lives at an external registrar**, because the certificate cannot be
  issued until records the first apply outputs have been added by hand. With the zone in Route 53
  it is one apply. The runbook covers both.
- **A CloudFront distribution is slow to change.** Creating or updating one takes several minutes
  and a delete takes longer still, which is why applies are operator steps with an expected
  runtime rather than something a session runs.
- The V2 app inherits a domain and a certificate that already exist, and a precedent — private
  origin, OAC, security headers at the edge — but not a solution: server-side rendering needs
  something else behind the same domain, and `v2-e14-t03` has to decide what.

## Alternatives considered

**AWS Amplify Hosting.** The obvious managed answer: connect the repository, get builds, pull
request previews, a global CDN and a one-click custom domain with a managed certificate. Rejected
for the public site on three grounds. It builds and deploys from a git branch, which turns a merge
into a publication — exactly the property this site should not have while its content is about
minors and gated by a publishing policy. Its build minutes and hosting fall outside the free tier
sooner than CloudFront's do, and it introduces a second deployment mechanism alongside the
Terraform the project already uses for everything. And it buys the most where it is needed least:
its value is SSR and preview environments, and this site is eight static pages. It remains a
serious candidate for the V2 app in `v2-e14-t03`, where SSR and previews are the requirement.

**A page on the school district's own website.** Free, already approved, and where parents look
first. Rejected as the primary home because the team does not control the layout, the update
cadence or the URL, and because the V2 app has to live somewhere the district's CMS cannot host
it. The district page is not going away: it should link here, and that link is part of the
publishing policy's approval conditions.

**A third-party site builder (Squarespace, Wix, Google Sites).** A coach could edit pages without
a developer, which is a genuine advantage and the reason `v1-e37-t01-content-editing-decision`
(ADR-0015) is a separate decision still to be made. Rejected here on privacy and cost: the hosted
builders load their own analytics and marketing scripts by default, which the publishing policy
forbids, and the paid tiers needed to remove branding cost more per year than this entire
architecture. Google Sites avoids the fee but not the tracking question, and gives no control over
response headers at all.

**GitHub Pages.** Free, trivially simple, HTTPS with a custom domain. Rejected because the site
would be served from a public repository's build output with no control over response headers
(no HSTS or CSP configuration), no way to keep the dev preview out of search engines except a
`robots.txt`, and no path that the V2 app could ever follow. It is the right answer for a project
without an AWS account; this one has one, already bootstrapped.

**CloudFront in front of the S3 *website* endpoint** (rather than the REST endpoint with OAC).
This is the old way to get directory-index behaviour for free — the website endpoint serves
`index.html` for a directory request. Rejected because it requires the bucket to be public: the
website endpoint is HTTP-only and cannot be restricted to a distribution, so the bucket's objects
stay reachable by URL, bypassing every header and every redirect above. The CloudFront Function
that replaces it is about fifteen lines.

**Lambda@Edge instead of a CloudFront Function** for the URI rewrite. More capable — network
access, more memory, more runtime — and none of it is needed to append `index.html` to a path.
Rejected on cost and latency, and because Lambda@Edge functions must live in `us-east-1` and are
replicated asynchronously, which makes every change slower to roll out and to delete.

**A third environment for previewing content.** Not considered: ADR-0013 allows dev and prod and
no third, and the dev distribution already is the preview.

## References

- [§4 Technology Stack](../architecture/architecture_proposal.md#4-technology-stack),
  [§5 AWS Cloud Architecture](../architecture/architecture_proposal.md#5-aws-cloud-architecture),
  [§14 Security, Privacy, and Student Safety](../architecture/architecture_proposal.md#14-security-privacy-and-student-safety)
- [ADR-0010: Primary AWS region and single-account environment separation](0010-primary-aws-region.md)
- [ADR-0013: Two environments (dev, prod) and dev→main promotion](0013-two-environments-and-dev-main-promotion.md)
- [`plan_specs/v1/e36-team-website/t02-site-hosting.yaml`](../../plan_specs/v1/e36-team-website/t02-site-hosting.yaml)
  — the task that owns this record
- [`plan_specs/v1/e36-team-website/t01-publishing-policy.yaml`](../../plan_specs/v1/e36-team-website/t01-publishing-policy.yaml)
  — the policy that governs what the site may publish
- [`plan_specs/v1/e36-team-website/t03-site-scaffold.yaml`](../../plan_specs/v1/e36-team-website/t03-site-scaffold.yaml)
  — the Next.js static export this hosting serves
- [`plan_specs/v1/e36-team-website/t05-site-deploy.yaml`](../../plan_specs/v1/e36-team-website/t05-site-deploy.yaml)
  — the deploy flow and smoke checks
- [`plan_specs/v2/e14-web-cut-card/t03-app-hosting.yaml`](../../plan_specs/v2/e14-web-cut-card/t03-app-hosting.yaml)
  — the V2 app hosting decision that amends this record
- [docs/runbooks/team-website.md](../runbooks/team-website.md) — the operator steps: applies,
  domain purchase, certificate validation, DNS
- [infrastructure/modules/static_site/README.md](../../infrastructure/modules/static_site/README.md)
  — the module that implements this decision
