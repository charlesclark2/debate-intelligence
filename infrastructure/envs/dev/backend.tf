terraform {
  # One state bucket per environment (ADR-0010): the DebateMaintainer permission set denies
  # debate-prod-*, so a dev credential is refused this file when the environment is prod. Locking
  # is the S3 backend's native lock object (Terraform >= 1.10) — a second concurrent plan finds
  # ${key}.tflock already there and fails — so there is no DynamoDB table to own.
  backend "s3" {
    bucket       = "debate-dev-tfstate-a7508de8"
    key          = "envs/dev/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
