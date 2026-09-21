# `static_site` module

One environment's public static website: a private S3 bucket served through CloudFront with
origin access control. Spec:
[`v1-e36-t02-site-hosting`](../../../plan_specs/v1/e36-team-website/t02-site-hosting.yaml).
Decision: [ADR-0012](../../../docs/adr/0012-web-hosting.md).
Operator steps: [docs/runbooks/team-website.md](../../../docs/runbooks/team-website.md).

Called once from [`envs/dev`](../../envs/dev/) and once from [`envs/prod`](../../envs/prod/) with
different inputs. It holds no account id, region or domain name: the region comes from the calling
root's provider, and the domains are inputs.

## What it creates

| Resource | Why it is the way it is |
|---|---|
| `aws_s3_bucket` + public access block, ownership controls, encryption, versioning, lifecycle | Private, ACLs disabled, SSE-S3, versioned so a wrong `sync --delete` is recoverable |
| `aws_s3_bucket_policy` | One `Allow`: `s3:GetObject` for `cloudfront.amazonaws.com`, conditioned on this distribution's ARN. Plus a deny on non-TLS requests |
| `aws_cloudfront_origin_access_control` | SigV4 origin signing, so the bucket needs no public grant and no origin access identity |
| `aws_cloudfront_function` (viewer request) | Redirects non-canonical hosts with a 301, then maps `/path/` to `/path/index.html` for the Next.js export |
| `aws_cloudfront_response_headers_policy` | HSTS, CSP, nosniff, Referrer-Policy, `X-Frame-Options: DENY`, Permissions-Policy, and `X-Robots-Tag: noindex, nofollow` when `noindex` is set |
| `aws_cloudfront_distribution` | `redirect-to-https`, HTTP/2 and /3, compression, `PriceClass_100`, 403 and 404 both answered with `/404.html`, **no logging** |
| `aws_acm_certificate` (+ validation records and wait) | Only when `domain_names` is non-empty; DNS validated; `TLSv1.2_2021` on the viewer connection |
| `aws_route53_record` | Validation records and A/AAAA aliases for every name — only when `route53_zone_id` is set |
| `aws_ssoadmin_permission_set` + inline policy + assignments | The `SitePublisher` credential, below |

There is deliberately **no CloudFront logging** and no real-time log config. ADR-0012 decision 8:
the audience is schoolchildren and their families, so no per-request record of visitor IP
addresses is created. Turning it on is a spec and publishing-policy change.

## Inputs worth knowing about

| Variable | Notes |
|---|---|
| `name_prefix` | The full prefix, `debate-dev-site` or `debate-prod-site`. Must contain the environment (ADR-0010 rule 2), which a variable validation enforces |
| `bucket_suffix` | Makes the bucket name globally unique. A committed constant, as the state buckets use, so the runbook and the deploy script can name the bucket without reading state |
| `domain_names` | Empty until a team domain exists. Empty means the `*.cloudfront.net` domain and **no certificate**, which is how a first apply goes out while DNS is still settling |
| `canonical_domain_name` | The one name the site answers on; every other name 301s to it. Null uses the first of `domain_names` |
| `route53_zone_id` | Set: Terraform writes the validation records and waits for ACM, so one apply is enough. Null: the records come out of `certificate_validation_records` for the operator to add at the registrar, and the apply runs twice |
| `noindex` | True in dev. Sends `X-Robots-Tag: noindex, nofollow` from the edge, which a stale cached `robots.txt` cannot undo |
| `content_security_policy` | Defaults to a policy that suits the Next.js export. `script-src` includes `'unsafe-inline'`, because a static export has no server and no middleware to issue a per-request nonce; override this input to tighten it |
| `identity_center_instance_arn`, `identity_store_id`, `publisher_user_names` | Optional. Null creates no permission set, which is what the tests and any reuse outside this account want. User names are people, so they come from the gitignored `owner.auto.tfvars` |

The hosted zones are **inputs, never resources**. They came with the domain registration, and a
`terraform destroy` that took one with it would strand the domain.

## The SitePublisher permission set

[`publisher_access.tf`](publisher_access.tf) defines `DebateDevSitePublisher` /
`DebateProdSitePublisher`: an Identity Center permission set whose inline policy allows exactly
six actions — `s3:ListBucket` on the site bucket, `s3:GetObject`, `s3:PutObject` and
`s3:DeleteObject` on its objects, and `cloudfront:CreateInvalidation` and
`cloudfront:GetInvalidation` on its distribution — and nothing else. The operator's SSO profile
for it is named after `name_prefix` (`debate-dev-site`, `debate-prod-site`).

Prod is why it exists: the everyday `debate-prod` profile is `DebateReadOnly`, and
`DebateMaintainer` is denied every `debate-prod-*` resource by ADR-0010 rule 4, so without this
the only way to publish the site would be break-glass administrator access for a routine act.

One thing it deliberately cannot do, which
[`v1-e36-t05-site-deploy`](../../../plan_specs/v1/e36-team-website/t05-site-deploy.yaml) works
around:

* **Read Terraform state.** `t05` reads the bucket and distribution from Terraform outputs; that
  read needs a maintainer profile, not this one. `scripts/site_deploy.sh` runs `terraform output`
  under `debate-<env>` (overridable to `debate-admin`) and everything else under the publisher
  profile.

`cloudfront:GetInvalidation` was added by `v1-e36-t05`. `v1-e36-t02` granted
`CreateInvalidation` alone, which made `aws cloudfront wait invalidation-completed` an
`AccessDenied` and left a deploy unable to say whether the edge was actually serving the new
files. That confirmation is what
[`docs/policies/website-publishing.md`](../../../docs/policies/website-publishing.md) leans on
when it promises that something about a student comes down within 24 hours of a request, so the
policy was widened by one read action on the distribution the publisher may already invalidate.

## Tests

[`tests/static_site.tftest.hcl`](tests/static_site.tftest.hcl) runs with `mock_provider "aws"`:
no credentials, no network, no AWS account.

```bash
terraform -chdir=infrastructure/modules/static_site init -backend=false
terraform -chdir=infrastructure/modules/static_site test
```

`init` first — `terraform test` does not initialise for you, and
[`scripts/terraform_checks.sh`](../../../scripts/terraform_checks.sh) has usually done it
already.

The bucket policy and the publisher policy are built with `jsonencode` rather than
`aws_iam_policy_document` data sources, because a data source's rendered JSON is opaque under a
mocked provider and those two policies are exactly what the tests need to read back.

## Two things tflint cannot see from here

* The five standard tags reach every resource through the calling root's provider `default_tags`
  ([infrastructure/README.md](../../README.md)). `aws_resource_missing_tags` reads that block and
  cannot see it when it lints this directory alone, so the two taggable resources carry a
  `# tflint-ignore` with that reason. Linting `envs/dev` or `envs/prod` follows the module call and
  does check the tags.
* The certificate must be in `us-east-1`, which is where CloudFront reads certificates from. A
  `check` block in [`certificate.tf`](certificate.tf) says so at plan time rather than letting the
  distribution fail.
