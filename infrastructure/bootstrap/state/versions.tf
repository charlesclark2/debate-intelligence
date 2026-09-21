terraform {
  # 1.10 is the floor because the S3 backend's native state locking (`use_lockfile`) arrives in
  # it. Locking without it means a DynamoDB table per environment, which this project would then
  # own, pay for and have to keep in step with the buckets; the lock object costs nothing and
  # lives beside the state it guards. The exact version the project is tested on is in
  # `.terraform-version` at the repository root.
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # local.tags, not module.tags.tags: tflint's aws_resource_missing_tags rule reads this block
  # and cannot see through a child module's output. main.tf explains it and checks the two
  # against each other.
  default_tags {
    tags = local.tags
  }
}
