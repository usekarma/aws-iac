# Route 53 Zone Component

This Terraform component provisions a Route 53 public hosted zone for a custom domain.

It is typically used as part of a multi-account AWS setup, where Route 53 DNS is managed in a central account (e.g. `prod-network` or `shared-network`) and consumed by other components such as ACM certificates, CloudFront distributions, and email forwarding.

---

## Features

- Creates a public Route 53 hosted zone for a given domain name
- Outputs the nameservers (NS records) required for external DNS delegation
- Supports standard tagging for auditing and management

---

## Usage

This component is designed to be used via [Terragrunt](https://terragrunt.gruntwork.io/), with a nickname that matches the root domain name:

```bash
AWS_PROFILE=prod-network ./scripts/deploy.sh route53-zone strall.com
```

This will deploy the component using:

```
/iac/route53-zone/strall.com/config         # SSM config
/iac/route53-zone/strall.com/runtime        # Runtime output
```

---

## Inputs (via SSM `/iac/route53-zone/<nickname>/config`)

```json
{
  "zone_name": "strall.com",
  "root_records": {
    ...
  }
  "tags": {
    "Project": "strall",
    "Environment": "prod"
  }
}
```

---

## Outputs (stored in `/iac/route53-zone/<nickname>/runtime`)

- `zone_id`: The hosted zone ID
- `nameservers`: A list of NS records to configure at your domain registrar

---

## GoDaddy Setup Instructions

To delegate your domain from GoDaddy to AWS Route 53:

1. **Deploy this component first** to create the hosted zone and capture the nameservers.
   
2. **Log in to GoDaddy** and open your domain settings.

3. Scroll to the **"Nameservers"** section and click **"Change"**.

4. Choose **"Enter my own nameservers (advanced)"**.

5. Copy the 4 NS values from the Terraform output (e.g., `ns-####.awsdns-##.org`) and paste them into GoDaddy.

6. Save changes. DNS may take a few minutes to hours to propagate.

⚠️ Make sure to remove any existing default GoDaddy NS entries when pasting the new ones.

---

## Example: Accessing Outputs

```hcl
data "aws_ssm_parameter" "zone_runtime" {
  name = "/iac/route53-zone/strall.com/runtime"
}

locals {
  zone_output = jsondecode(data.aws_ssm_parameter.zone_runtime.value)
  zone_id     = local.zone_output.zone_id
  nameservers = local.zone_output.nameservers
}
```

---

## Best Practices

- Create your Route 53 zones in a dedicated network or DNS account.
- Use strict IAM permissions to limit write access to hosted zones.
- Never mix manual and Terraform changes for DNS records — use a centralized module for record creation if needed.

---

## License

This repository is open source, released under the [Apache 2.0 License](https://www.apache.org/licenses/LICENSE-2.0).
