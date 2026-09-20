# Identical in both environment roots: the region comes from tfvars (ADR-0010 pins it to
# us-east-1) and the tags come from local.tags in main.tf, which the shared tags module is checked
# against, so that nothing here has to be kept in step by hand when the standard changes.

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.tags
  }
}
