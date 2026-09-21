variable "name_prefix" {
  description = "Resource-name prefix for this redirect, following ADR-0010's debate-<environment>-<purpose> rule: `debate-prod-site-redirect`."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,50}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 3-51 characters, starting with a letter."
  }
}

variable "domain_names" {
  description = <<-EOT
    The names this distribution answers on, only to redirect them: wfbdebate.org and
    www.wfbdebate.org. They need a certificate of their own, because a certificate covers the
    names on it and these are a different registrable domain from the site's.
  EOT
  type        = list(string)

  validation {
    condition     = length(var.domain_names) > 0
    error_message = "domain_names must not be empty: a redirect distribution with no names has nothing to redirect."
  }

  validation {
    condition     = alltrue([for domain in var.domain_names : can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", domain))])
    error_message = "Each entry in domain_names must be a lowercase hostname such as wfbdebate.org."
  }
}

variable "target_host" {
  description = <<-EOT
    Where every request is sent: the canonical host of the real site, for example wfbdebate.com.
    The path and query string are preserved, so a bookmarked .com page lands on the same .org
    page rather than on the home page.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$", var.target_host))
    error_message = "target_host must be a lowercase hostname such as wfbdebate.com."
  }

  validation {
    condition     = !contains(var.domain_names, var.target_host)
    error_message = "target_host must not be one of domain_names, or the distribution would redirect to itself forever."
  }
}

variable "route53_zone_id" {
  description = <<-EOT
    Hosted zone holding domain_names — the .com zone, not the site's. Set: Terraform writes the
    certificate validation records and the alias records and waits for ACM. Null: the records come
    out of `certificate_validation_records` for the operator to add at the registrar, and the
    apply runs a second time.
  EOT
  type        = string
  default     = null
}

variable "price_class" {
  description = "CloudFront price class. A redirect is a few hundred bytes; the cheapest class that covers the audience is the right one."
  type        = string
  default     = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "price_class must be PriceClass_100, PriceClass_200 or PriceClass_All."
  }
}

variable "minimum_tls_version" {
  description = "CloudFront security policy for viewer connections. This distribution always has a certificate of its own, so this always applies."
  type        = string
  default     = "TLSv1.2_2021"

  validation {
    condition     = can(regex("^TLSv1\\.2_", var.minimum_tls_version))
    error_message = "minimum_tls_version must be a TLS 1.2 or later policy (the task spec forbids anything below 1.2)."
  }
}

variable "strict_transport_security" {
  description = "Strict-Transport-Security sent on the redirect. A redirect is often the first response a browser ever gets for these names, so it is where the header does the most good."
  type        = string
  default     = "max-age=31536000; includeSubDomains"
}
