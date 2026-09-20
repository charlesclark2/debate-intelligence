# The two credentials the evidence store is reached with, as Identity Center permission sets.
#
#   EvidenceOperator - everyday work: list the documented prefixes, read, write, use the key.
#                      No DeleteObject at all. This is what the operator and
#                      `debate-research store sync|ls|get` (v1-e29-t05) run as.
#   EvidenceRemoval  - takedowns only: delete objects and their noncurrent versions under the five
#                      prefixes that hold disclosed material, and append to the suppression list.
#                      Assigned to one accountable person.
#
# Why two sets rather than one that can do everything: a removal under
# docs/policies/caselist-data-use.md is irreversible — the noncurrent versions go too, so there is
# nothing to restore from — while a sync happens every week. Everyday work must not be carrying
# the ability to do the irreversible thing by accident, and the weekly profile is the one that is
# left signed in.
#
# Neither set exists without an Identity Center instance, so the module stays usable (and
# testable) without one. Neither carries a long-lived access key: the operator signs in with SSO
# and assumes the set through the profile named after it (task spec: forbidden).
#
# Both policies are built with jsonencode rather than aws_iam_policy_document data sources, so
# that the module's tests can read them back under a mocked provider. What these two sets may and
# may not do is exactly what is worth asserting on, and a data source's rendered JSON is opaque
# there.

locals {
  create_permission_sets = var.identity_center_instance_arn != null

  # DebateDevEvidenceOperator / DebateProdEvidenceOperator, and the matching removal sets.
  operator_permission_set_name = "Debate${title(var.environment)}EvidenceOperator"
  removal_permission_set_name  = "Debate${title(var.environment)}EvidenceRemoval"

  # The SSO profile names the runbook tells the operator to configure. Named after name_prefix,
  # like the site publisher profiles of v1-e36-t02, so that the profile says which resources it
  # unlocks: debate-dev-evidence, debate-prod-evidence, and -removal beside each.
  operator_profile_name = var.name_prefix
  removal_profile_name  = "${var.name_prefix}-removal"

  # `aws s3 ls s3://bucket/raw/` sends prefix=raw/; a bare listing of the bucket root sends none,
  # and an absent condition key matches no StringLike, so the root listing is refused. That is the
  # scoping the task spec asks for, and the runbook says so in as many words: list a prefix.
  list_prefix_conditions = flatten([
    for prefix in local.evidence_prefixes : [prefix, "${prefix}*"]
  ])

  # The prefixes a takedown may delete from. reports/ is not among them: a report is derived,
  # regenerable and cites evidence rather than holding it, and leaving it out is what makes "this
  # credential deletes disclosed material and nothing else" a statement IAM can enforce.
  removable_prefixes = [
    "raw/",
    "parsed/",
    "files/",
    "manifests/",
    "quarantine/",
  ]

  removable_object_arns = [
    for prefix in local.removable_prefixes : "${aws_s3_bucket.evidence.arn}/${prefix}*"
  ]

  removable_list_prefix_conditions = flatten([
    for prefix in local.removable_prefixes : [prefix, "${prefix}*"]
  ])

  # manifests/_suppression/suppression-list.jsonl and removal-log.jsonl (v1-e30-t07). Appending to
  # an append-only list means reading it first, so this prefix — and only this prefix — is
  # readable and writable by the removal credential.
  suppression_prefix = "manifests/_suppression/"

  operator_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListDocumentedEvidencePrefixes"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.evidence.arn
        Condition = {
          StringLike = { "s3:prefix" = local.list_prefix_conditions }
        }
      },
      {
        # No s3:DeleteObject and no s3:DeleteObjectVersion, by design (task spec: forbidden).
        # Publishing is idempotent and content-addressed (v1-e29-t04, v1-e30-t05): a correct
        # everyday operation never needs to remove an object, and a mistake that would have
        # removed one is caught by an AccessDenied instead of by a restore.
        Sid    = "ReadAndPublishEvidenceObjects"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:PutObject",
        ]
        Resource = "${aws_s3_bucket.evidence.arn}/*"
      },
      {
        # Encrypt and GenerateDataKey for writes, Decrypt for reads. No kms:* and no key or
        # grant administration: this set cannot change who else may read the evidence.
        Sid    = "UseEvidenceKey"
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]
        Resource = aws_kms_key.evidence.arn
      },
    ]
  })

  removal_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # list-object-versions, which is how a takedown finds the noncurrent versions it has to
        # delete as well as the current one.
        Sid      = "ListEvidenceObjectVersionsForTakedown"
        Effect   = "Allow"
        Action   = "s3:ListBucketVersions"
        Resource = aws_s3_bucket.evidence.arn
        Condition = {
          StringLike = { "s3:prefix" = local.removable_list_prefix_conditions }
        }
      },
      {
        Sid    = "DeleteDisclosedMaterialOnRequest"
        Effect = "Allow"
        Action = [
          "s3:GetObjectVersion",
          "s3:DeleteObject",
          "s3:DeleteObjectVersion",
        ]
        Resource = local.removable_object_arns
      },
      {
        Sid    = "MaintainSuppressionList"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
        ]
        Resource = "${aws_s3_bucket.evidence.arn}/${local.suppression_prefix}*"
      },
      {
        # Decrypt to read what is about to be removed, GenerateDataKey to write the suppression
        # list back. No Encrypt beyond that, no kms:* and nothing that touches the key policy.
        Sid    = "UseEvidenceKeyForTakedown"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]
        Resource = aws_kms_key.evidence.arn
      },
    ]
  })
}

# Tagged through the calling root's provider `default_tags`, which tflint cannot see from here;
# README.md explains the annotation.
# tflint-ignore: aws_resource_missing_tags
resource "aws_ssoadmin_permission_set" "evidence_operator" {
  count = local.create_permission_sets ? 1 : 0

  name             = local.operator_permission_set_name
  description      = "Reads and publishes ${var.environment} evidence in ${local.bucket_name}. No DeleteObject, no bucket-policy or KMS-policy changes (v1-e29-t03)."
  instance_arn     = var.identity_center_instance_arn
  session_duration = "PT8H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "evidence_operator" {
  count = local.create_permission_sets ? 1 : 0

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.evidence_operator[0].arn
  inline_policy      = local.operator_policy
}

# A short session, unlike the operator's working day: this credential is assumed to run one
# takedown and then let go of.
# tflint-ignore: aws_resource_missing_tags
resource "aws_ssoadmin_permission_set" "evidence_removal" {
  count = local.create_permission_sets ? 1 : 0

  name             = local.removal_permission_set_name
  description      = "Takedowns only: deletes ${var.environment} evidence and its versions under raw/, parsed/, files/, manifests/ and quarantine/ (docs/policies/caselist-data-use.md)."
  instance_arn     = var.identity_center_instance_arn
  session_duration = "PT1H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "evidence_removal" {
  count = local.create_permission_sets ? 1 : 0

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.evidence_removal[0].arn
  inline_policy      = local.removal_policy
}

# Assignments. Students are never assigned a permission set; both lists hold adult maintainers
# only, and they come from the gitignored owner.auto.tfvars because they are people's names.

data "aws_identitystore_user" "evidence_operators" {
  for_each = local.create_permission_sets ? toset(var.evidence_operator_user_names) : toset([])

  identity_store_id = var.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = each.value
    }
  }
}

resource "aws_ssoadmin_account_assignment" "evidence_operators" {
  for_each = local.create_permission_sets ? toset(var.evidence_operator_user_names) : toset([])

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.evidence_operator[0].arn

  principal_id   = data.aws_identitystore_user.evidence_operators[each.value].user_id
  principal_type = "USER"

  target_id   = data.aws_caller_identity.current.account_id
  target_type = "AWS_ACCOUNT"
}

data "aws_identitystore_user" "evidence_removers" {
  for_each = local.create_permission_sets ? toset(var.evidence_removal_user_names) : toset([])

  identity_store_id = var.identity_store_id

  alternate_identifier {
    unique_attribute {
      attribute_path  = "UserName"
      attribute_value = each.value
    }
  }
}

resource "aws_ssoadmin_account_assignment" "evidence_removers" {
  for_each = local.create_permission_sets ? toset(var.evidence_removal_user_names) : toset([])

  instance_arn       = var.identity_center_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.evidence_removal[0].arn

  principal_id   = data.aws_identitystore_user.evidence_removers[each.value].user_id
  principal_type = "USER"

  target_id   = data.aws_caller_identity.current.account_id
  target_type = "AWS_ACCOUNT"
}
