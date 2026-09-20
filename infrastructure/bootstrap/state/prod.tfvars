# Inputs for the prod state bucket: terraform apply -var-file=prod.tfvars
# The owner email is not here; it comes from the gitignored terraform.tfvars in this directory.

environment         = "prod"
aws_region          = "us-east-1"
state_bucket_suffix = "a7508de8"
