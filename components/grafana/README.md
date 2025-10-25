# Grafana Component

This component provisions a **Grafana + Kafka Connect EC2 instance** inside a VPC.  
It exposes Grafana via a **public HTTPS Application Load Balancer (ALB)** and allows Kafka Connect tasks to run alongside Grafana for integration with MSK (e.g., MongoDB CDC → Kafka → ClickHouse).  

The component follows the [aws-iac](https://github.com/usekarma/aws-iac) conventions:
- **Configuration-first**: All values come from `config.json` in [aws-config](https://github.com/usekarma/aws-config).
- **Runtime discovery**: Outputs are written to SSM Parameter Store for downstream components.

---

## Features

- EC2 instance running **Grafana** and **Kafka Connect**
- Instance placed in a **private subnet** of a referenced VPC
- Public **HTTPS ALB** terminates TLS for `grafana.<domain>`
- Security group rules to allow inbound ALB → instance traffic
- IAM role + instance profile for SSM access (Session Manager)
- Optional DNS record in Route53 for the Grafana URL
- Runtime data published to SSM Parameter Store

---

## Configuration

Example `aws-config/iac/prod/grafana/grafana-usekarma-dev/config.json`:

```json
{
  "record_name": "grafana.usekarma.dev.",
  "hosted_zone_id": "Z123456ABCDEFG",
  "instance_type": "t3.medium",
  "key_name": null,
  "allowed_security_group_ids": [],
  "allowed_cidrs": ["203.0.113.42/32"],
  "tags": {
    "Environment": "prod",
    "Project": "grafana",
    "Owner": "usekarma"
  }
}
