output "tags" {
  description = "The standard tag map, for a provider `default_tags` block."
  value       = local.tags
}

output "required_tag_keys" {
  description = "The tag keys every resource must carry, matching the tflint aws_resource_missing_tags rule."
  value       = sort(keys(local.standard_tags))
}
