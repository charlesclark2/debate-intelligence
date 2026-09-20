terraform {
  # Identical in both environment roots. The floor is 1.10 because the S3 backend's native state
  # locking (`use_lockfile`, in backend.tf) arrives in it; the ceiling keeps a Terraform 2.x from
  # being picked up silently. The exact version this repository is tested on is in
  # `.terraform-version` at the repository root.
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
  }
}
