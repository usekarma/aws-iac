output "vpc_id" {
  description = "ID of the created VPC"
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "CIDR block of the VPC"
  value       = local.vpc_cidr
}

output "public_subnet_ids" {
  description = "List of public subnet IDs"
  value       = [for s in aws_subnet.public : s.id]
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = [for s in aws_subnet.private : s.id]
}

output "default_sg_id" {
  description = "ID of the default general-purpose security group"
  value       = aws_security_group.sg_default.id
}

output "has_nat" {
  description = "Boolean indicating whether the VPC has a NAT gateway (true if single_nat_gateway enabled)"
  value       = local.single_nat_gateway
}

output "runtime_parameter_path" {
  description = "SSM Parameter Store path where VPC runtime data was written (downstream components jsondecode this for service discovery)"
  value       = aws_ssm_parameter.runtime.name
}
