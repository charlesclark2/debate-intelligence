# The run's own network (ADR-0020 (1) 5): a small VPC, debate-<env>-caselist-run, with two public
# subnets, an internet gateway, an S3 gateway endpoint so bucket traffic stays inside AWS, and a
# security group with no inbound rule and outbound HTTPS only.
#
# Each task gets a public IPv4 address (the schedules' assign_public_ip), because it must reach
# api.opencaselist.com, Secrets Manager, ECR and CloudWatch Logs, and a NAT gateway would cost more
# a month than dev's whole budget. This is an interim network for one weekly task, not ADR-0011's
# design: v2-e10-t05 moves the tasks into its private subnets and this VPC is destroyed. So there
# are no interface endpoints, no NAT gateway and no flow logs here (ADR-0020, What E40 must not
# build).
#
# HTTPS is all the tasks need: every service above answers on 443, and the S3 gateway endpoint
# carries S3's 443 too, image layers included. The VPC's own DNS resolver is not filtered by a
# security group, so no rule for it is needed.

locals {
  run_network_name = "${var.name_prefix}-run"

  # Two subnets in two zones, each half of the VPC's range.
  public_subnets = {
    for index, zone in slice(sort(data.aws_availability_zones.available.names), 0, 2) :
    zone => cidrsubnet(var.vpc_cidr, 1, index)
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# Tagged by the calling root's provider default_tags, which tflint cannot see from inside the
# module; linting envs/dev or envs/prod follows the module call and checks them there. A resource
# with a Name tag is reported at its tags line, so that is where its ignore goes.
resource "aws_vpc" "run" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  # tflint-ignore: aws_resource_missing_tags
  tags = { Name = local.run_network_name }
}

# The VPC's default security group lets its members reach one another and anything outside.
# Nothing uses it; adopted with no rule, so nothing in this VPC has an inbound rule at all.
resource "aws_default_security_group" "run" {
  vpc_id = aws_vpc.run.id

  # tflint-ignore: aws_resource_missing_tags
  tags = { Name = "${local.run_network_name}-default-unused" }
}

resource "aws_internet_gateway" "run" {
  vpc_id = aws_vpc.run.id

  # tflint-ignore: aws_resource_missing_tags
  tags = { Name = local.run_network_name }
}

resource "aws_subnet" "public" {
  for_each = local.public_subnets

  vpc_id            = aws_vpc.run.id
  availability_zone = each.key
  cidr_block        = each.value
  # The task asks for its own public address; nothing else is launched here to be given one.
  map_public_ip_on_launch = false

  # tflint-ignore: aws_resource_missing_tags
  tags = { Name = "${local.run_network_name}-public-${each.key}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.run.id

  # tflint-ignore: aws_resource_missing_tags
  tags = { Name = "${local.run_network_name}-public" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.run.id
}

resource "aws_route_table_association" "public" {
  for_each = aws_subnet.public

  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# S3 traffic, the evidence bucket's and ECR's image layers alike, stays inside AWS. No charge.
# The default policy: a narrower one would refuse ECR's layer bucket along with everything else.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.run.id
  service_name      = "com.amazonaws.${local.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id]

  # tflint-ignore: aws_resource_missing_tags
  tags = { Name = "${local.run_network_name}-s3" }
}

# No inbound rule, and outbound HTTPS only. The rules are inline, so the group holds exactly these
# and an apply removes any rule added by hand.
resource "aws_security_group" "run" {
  name        = local.run_network_name
  description = "The ${var.environment} caselist login and run tasks: no inbound rule, outbound HTTPS only (ADR-0020 (1) 5)."
  vpc_id      = aws_vpc.run.id

  ingress = []

  egress {
    description = "HTTPS to OpenCaselist, Secrets Manager, ECR, CloudWatch Logs and S3"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }

  # tflint-ignore: aws_resource_missing_tags
  tags = { Name = local.run_network_name }
}
