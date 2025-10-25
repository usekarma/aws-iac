output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.ch.id
}

output "private_ip" {
  description = "Private IP of ClickHouse"
  value       = aws_instance.ch.private_ip
}

output "security_group_id" {
  description = "ClickHouse security group ID"
  value       = aws_security_group.ch.id
}

output "data_volume_id" {
  description = "EBS data volume ID"
  value       = aws_ebs_volume.data.id
}

output "runtime_parameter_path" {
  description = "SSM path for ClickHouse runtime JSON"
  value       = aws_ssm_parameter.runtime.name
}

output "msk_cluster_arn" {
  description = "ARN of the MSK Serverless cluster (if enabled)"
  value       = local.msk_arn
}

output "msk_bootstrap_sasl_iam" {
  description = "Bootstrap brokers (SASL/IAM) for MSK Serverless (if enabled)"
  value       = local.msk_bootstrap
}
