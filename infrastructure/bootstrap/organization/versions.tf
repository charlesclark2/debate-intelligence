terraform {
  # State lives in the prod state bucket; see backend.tf. The floor is 1.10 because that is
  # where the S3 backend's native state locking (`use_lockfile`) arrives, and every root in this
  # repository is pinned the same way.
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # The tagging standard of ADR-0010: nothing in this account is separated by an account
  # boundary, so every resource must be identifiable by tag. v1-e29-t02-terraform-bootstrap
  # makes this the standard for the environment roots as well.
  default_tags {
    tags = {
      Project    = var.project
      Owner      = var.owner
      CostCenter = var.cost_center
      ManagedBy  = "terraform"
      SpecRef    = "v1-e29-t01-aws-account-baseline"
    }
  }
}
