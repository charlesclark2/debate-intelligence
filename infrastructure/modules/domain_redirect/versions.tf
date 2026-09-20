terraform {
  # The same pin every root and module in this repository carries. The floor of 1.10 also covers
  # what this module's tests need: `terraform test` with `mock_provider`.
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
  }
}
