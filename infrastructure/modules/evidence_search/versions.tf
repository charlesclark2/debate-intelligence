terraform {
  # The same pin every root and module in this repository carries. The floor of 1.10 also covers
  # what this module's own tests need: `terraform test` with `mock_provider`, which is what lets
  # them run with no AWS credentials and no network.
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
  }
}
