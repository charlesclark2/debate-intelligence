# The cluster both tasks run on, and the repository their image comes from (ADR-0020 (1)).
#
#   debate-<env>-caselist-run   an ECS cluster with nothing in it but Fargate tasks: no capacity
#                               provider strategy and no Container Insights (ADR-0020, What E40
#                               must not build). v2-e10-t05's cluster replaces it.
#   debate-<env>-caselist-run   the image repository, created the way v2-e10-t05's ecr module
#                               creates one, so that E10 adopts it rather than recreating it:
#                               immutable tags, a scan on every push, encryption with KMS.
#
# An image is pushed by scripts/caselist_run_deploy.sh, tagged with the release it was built from,
# and run by digest. Tags are immutable, so a tag in the repository is one build forever.

locals {
  cluster_name    = "${var.name_prefix}-run"
  repository_name = "${var.name_prefix}-run"

  # Five images at about 0.5 GB each (ADR-0020 (8)). A task definition pins a digest, so the
  # runbook applies the newest digest after each push, before five more pushes could expire it.
  images_kept = 5
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ecs_cluster" "run" {
  name = local.cluster_name

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

# tflint-ignore: aws_resource_missing_tags
resource "aws_ecr_repository" "run" {
  name                 = local.repository_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  # ECR's AWS-managed key: encrypted with KMS from the start, as v2-e10-t05 requires, at no cost.
  encryption_configuration {
    encryption_type = "KMS"
  }
}

resource "aws_ecr_lifecycle_policy" "run" {
  repository = aws_ecr_repository.run.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the ${local.images_kept} newest images; a task definition pins one by digest."
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = local.images_kept
        }
        action = { type = "expire" }
      },
    ]
  })
}
