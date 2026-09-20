# This environment's evidence store: the private, versioned, KMS-encrypted bucket that is the
# system of record for disclosed caselist evidence, camp files, parsed cards, built team files and
# reports (ADR-0003, spec v1-e29-t03-evidence-buckets). The key layout is
# docs/architecture/evidence-store-layout.md.
#
# This file is character-for-character the same in envs/dev and envs/prod, like every other file
# in these roots except terraform.tfvars and backend.tf. The environments differ only in what
# their tfvars say: dev keeps superseded versions for 30 days and holds synthetic or sample data,
# prod keeps them for a year and holds the real corpus. Copying a resource block between the two
# roots instead of putting it in infrastructure/modules is what this layout exists to prevent —
# see infrastructure/README.md.
#
# The Identity Center instance and identity store come from the data source and locals in site.tf,
# which every root already has; the evidence permission sets and the site publisher set read the
# same instance.
#
# Applies are operator-run (docs/runbooks/evidence-store.md), and prod is applied only after dev
# has been applied and checked. There are no GitHub OIDC roles until v2-e10-t03, so CI never runs
# plan or apply against this root, and neither does an agent session.

module "evidence_store" {
  source = "../../modules/evidence_bucket"

  name_prefix   = "${var.name_prefix}-${var.environment}-evidence"
  environment   = var.environment
  bucket_suffix = var.evidence_bucket_suffix

  noncurrent_version_retention_days = var.evidence_noncurrent_version_retention_days

  # Empty in V1. The V2 worker and API roles add themselves here rather than by editing the
  # module, and get read and presign access only.
  additional_reader_principal_arns = var.evidence_additional_reader_principal_arns

  identity_center_instance_arn = local.identity_center_instance_arn
  identity_store_id            = local.identity_store_id

  evidence_operator_user_names = var.evidence_operator_user_names
  evidence_removal_user_names  = var.evidence_removal_user_names
}

# A store nobody can reach is a store nobody can publish to, and the operator user names live in a
# gitignored file — so an empty list is easy to end up with by accident and invisible until a sync
# fails with AccessDenied. This says so at plan time instead. A `check` block warns rather than
# failing, which is the right strength: a root with nobody assigned is still applyable.
check "someone_can_operate_the_evidence_store" {
  assert {
    condition = length(var.evidence_operator_user_names) > 0
    error_message = join(" ", [
      "evidence_operator_user_names is empty, so the EvidenceOperator permission set for",
      "${var.environment} would exist with nobody assigned to it and no way to publish evidence.",
      "Set it in the gitignored owner.auto.tfvars beside this file (see owner.auto.tfvars.example).",
    ])
  }
}
