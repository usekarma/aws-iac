# SQS Queue Component (Adage)

## Summary

This component provisions an Amazon SQS queue using Adage-style configuration. It is designed to be consumed by Kubernetes workloads (or any AWS-integrated system) for asynchronous message processing.

* Queue metadata is stored in AWS Parameter Store
* Optional IAM policy is output for consumers to assume via IRSA
* Supports both standard and FIFO queue types

## What This Component Does

* Provisions an SQS queue (standard or FIFO depending on config)
* Stores queue metadata in Parameter Store:

  * `/iac/sqs-queue/<nickname>/runtime/queue_url`
  * `/iac/sqs-queue/<nickname>/runtime/queue_arn`
* Outputs an IAM policy document for consumption via IRSA
* Optionally adds tags, DLQ configuration, or encryption based on input config

## Consuming the Queue

To use the queue in an application, retrieve the runtime metadata:

```bash
QUEUE_URL=$(aws ssm get-parameter --name /iac/sqs-queue/${SQS_NICKNAME}/runtime/queue_url --query 'Parameter.Value' --output text)
QUEUE_ARN=$(aws ssm get-parameter --name /iac/sqs-queue/${SQS_NICKNAME}/runtime/queue_arn --query 'Parameter.Value' --output text)
```

Use these values in Kubernetes config, Helm charts, or directly in your application.

## IRSA Integration

If running in EKS, use the output IAM policy with an IRSA-bound role:

* Grant only `sqs:SendMessage`, `sqs:ReceiveMessage`, etc. based on need
* Reference the policy output and attach to an IRSA role using the `irsa-role` component

## Best Practices

* Use FIFO only if ordering is required
* Apply dead-letter queues (DLQs) for long-term durability
* Rotate credentials or review access policies regularly

## Related Components

| Component       | Purpose                                                      |
| --------------- | ------------------------------------------------------------ |
| `eks-cluster/`  | Needed if queue is consumed by EKS-based workloads           |
| `irsa-role/`    | Secure, per-service IAM role for queue access in Kubernetes  |
| `rds-postgres/` | If queue consumers transform and persist messages downstream |

This component is generic and compatible with any AWS consumer. It does not require or assume a specific processing stack.
