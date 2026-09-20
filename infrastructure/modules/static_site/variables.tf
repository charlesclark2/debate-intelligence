variable "name_prefix" {
  description = <<-EOT
    Full resource-name prefix for this environment's site, following ADR-0010's
    debate-<environment>-<purpose> rule: `debate-dev-site` or `debate-prod-site`. It names the
    bucket, the distribution comment, the CloudFront Function, the policies and the SSO profile
    the operator deploys with, so the two environments can never share a resource.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,40}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 3-41 characters, starting with a letter."
  }

  validation {
    # ADR-0010 rule 2: the environment is part of every resource name, so an IAM policy can
    # separate dev from prod by prefix and not only by tag. A prefix that does not carry its
    # environment silently removes half of that boundary.
    condition     = strcontains(var.name_prefix, "-${var.environment}-")
    error_message = "name_prefix must contain the environment, as in debate-${var.environment}-site (ADR-0010: debate-<environment>-<purpose>)."
  }
}

variable "environment" {
  description = "Which environment this site belongs to: dev (preview) or prod (public). ADR-0013 allows no third."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod (ADR-0013: there is no stage environment)."
  }
}

variable "bucket_suffix" {
  description = <<-EOT
    Suffix that makes the bucket name unique in S3's global namespace, as the state buckets of
    v1-e29-t02 already do. A committed constant, not an account id and not a `random_id`: the
    deploy script and the runbook have to be able to name the bucket without reading state.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{4,16}$", var.bucket_suffix))
    error_message = "bucket_suffix must be 4-16 lowercase letters and digits."
  }
}

variable "domain_names" {
  description = <<-EOT
    Domain names the distribution answers on, for example ["wbdebate.org", "www.wbdebate.org"].
    Empty — the state until a team domain is bought — serves the site on its own
    *.cloudfront.net domain with the CloudFront default certificate and requests no ACM
    certificate. The first entry is the certificate's common name and the site's canonical URL.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for domain in var.domain_names : can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", domain))])
    error_message = "Each entry in domain_names must be a lowercase hostname such as wbdebate.org or www.wbdebate.org."
  }
}

variable "canonical_domain_name" {
  description = <<-EOT
    The one name in domain_names the site really answers on. Every other name is answered with a
    301 to the same path on this one, by the viewer-request function, so parents, search engines
    and the V2 app all see a single address. Null uses the first entry of domain_names.
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.canonical_domain_name == null ? true : contains(var.domain_names, var.canonical_domain_name)
    error_message = "canonical_domain_name must be one of domain_names, or null to use the first of them."
  }
}

variable "route53_zone_id" {
  description = <<-EOT
    Route 53 hosted zone holding domain_names. When it is set the module creates the certificate's
    DNS validation records and waits for ACM to issue, so one apply is enough. When it is null —
    the domain is at an external registrar — the records come out of the
    `certificate_validation_records` output for the operator to add by hand, and the apply is run
    a second time once the certificate is issued (docs/runbooks/team-website.md).
  EOT
  type        = string
  default     = null
}

variable "noindex" {
  description = <<-EOT
    Send `X-Robots-Tag: noindex, nofollow` on every response. True in dev, so the preview cannot
    be indexed even if someone links to its CloudFront domain, and false in prod. The dev build
    also writes a disallow-all robots.txt (v1-e36-t03-site-scaffold); this is the half that a
    stale robots.txt in the CDN cache cannot undo.
  EOT
  type        = bool
  default     = false
}

variable "price_class" {
  description = <<-EOT
    CloudFront price class. The default covers North America and Europe, which is where a
    Wisconsin high-school team's parents are; the cheapest class that serves them is the right
    one for a site on a $25-a-month budget (ADR-0010).
  EOT
  type        = string
  default     = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "price_class must be PriceClass_100, PriceClass_200 or PriceClass_All."
  }
}

variable "minimum_tls_version" {
  description = <<-EOT
    CloudFront security policy for viewer connections, used only when domain_names is non-empty.
    A distribution on the CloudFront default certificate is forced by AWS to the `TLSv1` policy
    and this value is ignored there, which ADR-0012 records as a reason to buy the domain
    promptly.
  EOT
  type        = string
  default     = "TLSv1.2_2021"

  validation {
    condition     = can(regex("^TLSv1\\.2_", var.minimum_tls_version))
    error_message = "minimum_tls_version must be a TLS 1.2 or later policy (the task spec forbids anything below 1.2)."
  }
}

variable "content_security_policy" {
  description = <<-EOT
    Content-Security-Policy sent on every response. The default suits the Next.js static export
    of v1-e36-t03: everything comes from this origin, and `script-src` has to tolerate the inline
    bootstrap scripts the App Router export emits, because a static export has no server and no
    middleware to issue a per-request nonce. `object-src 'none'`, `base-uri 'self'` and
    `frame-ancestors 'none'` keep what that allows small. Override it here to tighten the policy
    without changing the module.
  EOT
  type        = string
  # A literal, not a join(): a variable default cannot call a function. The order matches the
  # order a reader checks these in — what may load, where it may load from, what may embed us.
  default = "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; manifest-src 'self'; upgrade-insecure-requests"

  validation {
    condition     = strcontains(var.content_security_policy, "frame-ancestors 'none'")
    error_message = "content_security_policy must keep frame-ancestors 'none': the task spec forbids the site being framed."
  }
}

variable "permissions_policy" {
  description = <<-EOT
    Permissions-Policy header. The site asks for no device capability at all, so every feature a
    page could request is turned off; a feature that is off cannot be turned on by content a
    coach adds later without this module changing.
  EOT
  type        = string
  default     = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), interest-cohort=(), magnetometer=(), microphone=(), payment=(), usb=()"
}

variable "hsts_max_age_seconds" {
  description = "Strict-Transport-Security max-age. One year, applied to the domain and its subdomains; not preloaded, because preloading is a commitment that outlives the domain."
  type        = number
  default     = 31536000

  validation {
    condition     = var.hsts_max_age_seconds >= 31536000
    error_message = "hsts_max_age_seconds must be at least a year (31536000)."
  }
}

variable "noncurrent_version_retention_days" {
  description = "How long superseded object versions are kept. Versioning is what makes a bad `aws s3 sync --delete` recoverable; the window only has to outlast noticing."
  type        = number
  default     = 30

  validation {
    condition     = var.noncurrent_version_retention_days >= 7
    error_message = "Keep at least a week of superseded versions: a deploy mistake found on Monday was often made on Friday."
  }
}

variable "identity_center_instance_arn" {
  description = <<-EOT
    IAM Identity Center instance that owns the SitePublisher permission set, read by the calling
    root from `aws_ssoadmin_instances`. Null creates no permission set, which is what the module's
    own tests and any reuse outside this account want. The ARN carries no account id.
  EOT
  type        = string
  default     = null
}

variable "identity_store_id" {
  description = "Identity store behind identity_center_instance_arn, used to resolve publisher_user_names. Required when publisher_user_names is non-empty."
  type        = string
  default     = null

  validation {
    condition     = var.identity_store_id == null ? length(var.publisher_user_names) == 0 : true
    error_message = "identity_store_id is required when publisher_user_names is set: user names are resolved through the identity store."
  }
}

variable "publisher_user_names" {
  description = <<-EOT
    Identity Center user names assigned the SitePublisher permission set — adult maintainers
    only, never students. Empty by default and supplied through the gitignored
    owner.auto.tfvars, because these are people's names and the repository is public.
  EOT
  type        = list(string)
  default     = []
}
