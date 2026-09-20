output "state_bucket_name" {
  description = "Name of this environment's state bucket. Record it in docs/runbooks/terraform-bootstrap.md."
  value       = aws_s3_bucket.state.id
}

output "state_bucket_arn" {
  description = "ARN of this environment's state bucket, for the permission-set policies that separate dev from prod."
  value       = aws_s3_bucket.state.arn
}

output "state_bucket_region" {
  description = "Region of the state bucket (ADR-0010)."
  value       = aws_s3_bucket.state.region
}

output "backend_config" {
  description = <<-EOT
    The backend block a root in this environment should use, with the key left to the caller.
    Printed so that a new root is configured by copying a value that came from the apply rather
    than by retyping a bucket name.
  EOT
  value = {
    bucket       = aws_s3_bucket.state.id
    region       = var.aws_region
    encrypt      = true
    use_lockfile = true
  }
}
