output "tag_keys" {
  description = "The tag keys this module keeps Active, for the organization root's check that the anomaly monitor's tag is one of them."
  value       = sort(keys(aws_ce_cost_allocation_tag.this))
}
