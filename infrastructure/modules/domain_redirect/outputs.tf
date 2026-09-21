output "distribution_id" {
  description = "The redirect distribution."
  value       = aws_cloudfront_distribution.redirect.id
}

output "distribution_domain_name" {
  description = "The *.cloudfront.net domain the redirect answers on before the alias records exist."
  value       = aws_cloudfront_distribution.redirect.domain_name
}

output "domain_names" {
  description = "The names being redirected."
  value       = var.domain_names
}

output "target_url" {
  description = "Where they are redirected to."
  value       = "https://${var.target_host}/"
}

output "certificate_arn" {
  description = "The ACM certificate for the redirected names."
  value       = aws_acm_certificate.redirect.arn
}

output "certificate_validation_records" {
  description = "The DNS records that prove ownership of the redirected names, for an operator to add by hand when route53_zone_id is null."
  value = [
    for option in aws_acm_certificate.redirect.domain_validation_options : {
      domain_name = option.domain_name
      name        = option.resource_record_name
      type        = option.resource_record_type
      value       = option.resource_record_value
    }
  ]
}
