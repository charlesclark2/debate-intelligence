output "environment" {
  description = "The environment this root manages."
  value       = var.environment
}

output "aws_region" {
  description = "The region this root creates resources in (ADR-0010)."
  value       = var.aws_region
}

output "standard_tags" {
  description = "The default_tags every resource in this root inherits."
  value       = module.tags.tags
}
