# Inputs for the dev state bucket: terraform apply -var-file=dev.tfvars
# The owner email is not here; it comes from the gitignored terraform.tfvars in this directory.

environment         = "dev"
aws_region          = "us-east-1"
state_bucket_suffix = "a7508de8"
