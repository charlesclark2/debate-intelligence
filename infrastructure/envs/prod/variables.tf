variable "aws_region" {
  description = "Region for every resource in this root. ADR-0010 pins this to us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = <<-EOT
    Which environment this root is: dev or prod. Set in terraform.tfvars beside this file, and
    checked against the directory name in main.tf, because in a single-account setup (ADR-0010)
    this value is half of what keeps prod resources apart from dev ones.
  EOT
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be dev or prod (ADR-0013: there is no stage environment)."
  }
}

variable "project" {
  description = "Project tag applied to every resource in this root."
  type        = string
  default     = "debate-intelligence"
}

variable "owner" {
  description = <<-EOT
    Owner tag: the email of the adult maintainer accountable for these resources. Not committed;
    supply it through a gitignored owner.auto.tfvars beside this file or TF_VAR_owner.
  EOT
  type        = string
}

variable "cost_center" {
  description = "CostCenter tag, used to separate this project's spend from others in the account."
  type        = string
  default     = "debate-intelligence"
}

# --- The public team website (v1-e36-t02-site-hosting, ADR-0012) -----------------------------
#
# Identical in both roots; the values are in each root's terraform.tfvars.

variable "name_prefix" {
  description = "Short prefix for resource names. ADR-0010 requires debate-<environment>-<purpose> so that IAM policies can separate environments by name and not only by tag."
  type        = string
  default     = "debate"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 2-21 characters."
  }
}

variable "site_bucket_suffix" {
  description = <<-EOT
    Suffix making the site bucket name unique in S3's global namespace. The same committed
    constant the state buckets use (v1-e29-t02), so the runbook and the deploy script can name the
    bucket without reading state.
  EOT
  type        = string
  default     = "a7508de8"
}

variable "site_domain_names" {
  description = <<-EOT
    The names this environment's site answers on: dev.wfbdebate.com in dev, wfbdebate.com and
    www.wfbdebate.com in prod. Empty serves the site on its *.cloudfront.net domain and requests
    no certificate, which is the escape hatch for applying while DNS is still settling:
    `terraform apply -var 'site_domain_names=[]'`.
  EOT
  type        = list(string)
  default     = []
}

variable "site_canonical_domain_name" {
  description = "The one name the site really answers on; every other name 301s to it. Null uses the first of site_domain_names."
  type        = string
  default     = null
}

variable "site_dns_zone_name" {
  description = "Name of the existing Route 53 hosted zone holding site_domain_names, for example wfbdebate.com. The zone is read, never created. Null leaves the DNS records to the operator."
  type        = string
  default     = null
}

variable "site_noindex" {
  description = "Send `X-Robots-Tag: noindex, nofollow` from the edge. True in dev, where the preview must never appear in search results; false in prod."
  type        = bool
  default     = false
}

variable "redirect_domain_names" {
  description = "Names that exist only to 301 to the canonical site host: wfbdebate.org and www.wfbdebate.org in prod, empty in dev."
  type        = list(string)
  default     = []
}

variable "redirect_dns_zone_name" {
  description = "Name of the existing Route 53 hosted zone holding redirect_domain_names, for example wfbdebate.org. Read, never created."
  type        = string
  default     = null
}

variable "site_publisher_user_names" {
  description = <<-EOT
    Identity Center user names assigned this environment's SitePublisher permission set — adult
    maintainers only, never students. Supplied through the gitignored owner.auto.tfvars, because
    these are people's names and the repository is public.
  EOT
  type        = list(string)
  default     = []
}
