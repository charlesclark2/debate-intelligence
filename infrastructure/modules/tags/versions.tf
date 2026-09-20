terraform {
  # This module computes a value; it declares no providers and creates no resources, so it
  # constrains only the Terraform version. The pin matches every root in this repository.
  required_version = ">= 1.10.0, < 2.0.0"
}
