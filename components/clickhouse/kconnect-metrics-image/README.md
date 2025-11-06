# clickhouse kconnect JMX exporter image

Build and push the JMX exporter image to ECR:

```bash
cd components/clickhouse/kconnect-metrics-image
chmod +x build.sh
./build.sh
```

This script will:

1. Fetch your AWS **account ID** automatically using the AWS CLI.
2. Build the `clickhouse-kconnect-jmx-exporter` Docker image.
3. Log in to ECR for the current AWS account and region.
4. Push the image to your ECR repository.
5. Print the full ECR image URI and the JSON snippet to add to your SSM config.

---

### Example output

```bash
[build.sh] Building Docker image...
[build.sh] Logging into ECR...
[build.sh] Pushing image to 580801917120.dkr.ecr.us-east-1.amazonaws.com/clickhouse-kconnect-jmx-exporter:latest ...
[build.sh] Done!
Image pushed: 580801917120.dkr.ecr.us-east-1.amazonaws.com/clickhouse-kconnect-jmx-exporter:latest

Next step: add this to your SSM config JSON:

  "kconnect_metrics_image": "580801917120.dkr.ecr.us-east-1.amazonaws.com/clickhouse-kconnect-jmx-exporter:latest"
```

---

### SSM Configuration

Once pushed, add the image URI to your SSM config JSON (under the clickhouse component):

```json
{
  "kconnect_metrics_image": "<account>.dkr.ecr.us-east-1.amazonaws.com/clickhouse-kconnect-jmx-exporter:latest"
}
```

This ensures the ECS task definition for `kconnect` uses your ECR-hosted JMX exporter image.

---

### Repository structure

```text
components/
  clickhouse/
    metrics-image/
      Dockerfile
      kconnect-jmx.yml
      build.sh
      README.md  ← this file
```
