# RDS Postgres Component (Adage)

## Summary

This component provisions a PostgreSQL database on Amazon RDS using Adage-style configuration. It is intended to be a standalone, reusable database layer that can be consumed by any application running inside or outside EKS.

* Database credentials and connection details are stored in AWS Parameter Store
* Security group allows ingress from the EKS cluster
* Compatible with any Kubernetes or non-Kubernetes deployment

## What This Component Does

* Provisions an Amazon RDS Postgres instance (e.g., `t4g.micro` for low cost)
* Stores `jdbc_url`, `username`, and `password` in Parameter Store at:

  * `/iac/rds-postgres/<nickname>/runtime/jdbc_url`
  * `/iac/rds-postgres/<nickname>/runtime/username`
  * `/iac/rds-postgres/<nickname>/runtime/password`
* Creates a security group to allow access from EKS-managed nodes
* Outputs connection values for runtime wiring

## Connecting to the Database

Any application or deployment process can consume the connection values from Parameter Store:

```bash
JDBC_URL=$(aws ssm get-parameter --name /iac/rds-postgres/${RDS_NICKNAME}/runtime/jdbc_url --with-decryption --query 'Parameter.Value' --output text)
USERNAME=$(aws ssm get-parameter --name /iac/rds-postgres/${RDS_NICKNAME}/runtime/username --with-decryption --query 'Parameter.Value' --output text)
PASSWORD=$(aws ssm get-parameter --name /iac/rds-postgres/${RDS_NICKNAME}/runtime/password --with-decryption --query 'Parameter.Value' --output text)
```

Use these in Helm charts, Kubernetes Secrets, or direct application config.

## Best Practices

* Rotate credentials periodically and redeploy dependent consumers
* Ensure only required subnets and ports are opened via the security group
* Backup policies and storage type should be adjusted for production workloads

## Related Components

| Component      | Purpose                                                             |
| -------------- | ------------------------------------------------------------------- |
| `eks-cluster/` | If the database is consumed from workloads inside EKS               |
| `irsa-role/`   | If consumers use IRSA to access config or SSM securely              |
| `s3-bucket/`   | Optional: for backup exports, logs, or intermediate data from flows |

This component assumes no specific workload or tool. It exists to provide a consistent, infrastructure-managed PostgreSQL backend accessible via AWS Parameter Store.
