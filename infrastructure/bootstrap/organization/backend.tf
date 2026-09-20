terraform {
  # This root held local state until v1-e29-t02-terraform-bootstrap created the state buckets.
  # Its resources are account-wide and admin-applied — permission sets, the organization trail,
  # budgets — so its state belongs with the other shared, prod-scoped state: in the prod bucket,
  # under its own key, where DebateMaintainer's deny on debate-prod-* keeps a dev session out of
  # it. That state names every permission set and policy in the account.
  #
  # Moving it is an operator step run from the main clone, where the local state file lives:
  # docs/runbooks/terraform-bootstrap.md, "Migrate the organization root".
  backend "s3" {
    bucket       = "debate-prod-tfstate-a7508de8"
    key          = "bootstrap/organization/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
