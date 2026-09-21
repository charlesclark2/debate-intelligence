terraform {
  # Deliberately partial. This root creates the bucket it later stores its own state in, so the
  # first apply of each environment runs on local state and the values below arrive from
  # `-backend-config=<environment>.s3.tfbackend` at `init -migrate-state` time. The sequence is
  # in README.md and in docs/runbooks/terraform-bootstrap.md; it is an operator step.
  backend "s3" {}
}
