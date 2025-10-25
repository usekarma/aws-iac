output "alb_dns" {
  description = "DNS name of the public ALB"
  value       = aws_lb.this.dns_name
}

output "https_url" {
  description = "Public HTTPS URL (using custom domain if configured)"
  value       = "https://${local.domain_name}"
}

output "instance_id" {
  description = "EC2 instance ID for Grafana + Kafka Connect"
  value       = aws_instance.app.id
}

output "instance_sg_id" {
  description = "Security Group ID attached to Grafana + Kafka Connect instance"
  value       = aws_security_group.app.id
}

output "runtime_parameter_path" {
  description = "SSM Parameter Store path where runtime data is written"
  value       = aws_ssm_parameter.runtime.name
}
