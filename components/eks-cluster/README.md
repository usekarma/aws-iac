# EKS Cluster Component (Adage)

## Summary

* This component provisions a reusable Kubernetes control plane on Amazon EKS
* It is deployment-agnostic and works with Helm, ArgoCD, kubectl, or any other tool
* All configuration and runtime values are stored in AWS Parameter Store

## Deploying to This Cluster

Once this component is applied, any Kubernetes deployment tool can target the cluster.
To configure your local environment to interact with the EKS cluster:

```bash
./use.sh ${EKS_CLUSTER_NICKNAME}
```

This script will fetch the `cluster_name` and `region` from:

```
/iac/eks-cluster/${EKS_CLUSTER_NICKNAME}/runtime/
```

It then runs `aws eks update-kubeconfig` to set your current kube context.

From there, use any tooling to deploy workloads:

```bash
kubectl apply -f my-deployment.yaml
# or
helm upgrade --install my-app my-chart/ -n my-namespace
# or
argocd app create ...
```

This cluster is intentionally generic and does not impose a specific workload strategy.

## What This Component Does

* Provisions an EKS cluster with optional managed node groups
* Configures OIDC provider for IAM Roles for Service Accounts (IRSA)
* Outputs values needed for any Kubernetes deployment method (e.g. cluster name, region)
* Integrates with `aws-config` for Adage-style value injection

## Required Supporting Components (For a Real System)

| Component    | Why It’s Required                                                                                                                 |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `irsa-role/` | To grant applications secure access to AWS services like SQS/S3 via pod-level IAM roles. Never use long-lived IAM users.          |
| `s3-bucket/` | Real ETL pipelines or apps often need durable, auditable storage for logs, artifacts, or data.                                    |
| `vpc/`       | The default AWS VPC is not production-safe. Multi-AZ, subnet segmentation, and custom routing are often needed.                   |
| `keda/`      | If any workload must scale with queue depth, API volume, or schedule, autoscaling is not optional.                                |
