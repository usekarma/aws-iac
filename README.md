# AWS Infrastructure as Code (IaC)

## **Overview**  
This repository contains reusable **Terraform modules** for deploying AWS infrastructure **dynamically** based on configurations stored in AWS Parameter Store.  

### **🔑 Key Features**
- **Decouples infrastructure from deployment** – Terraform only deploys what’s pre-approved in the config repo.  
- **No hardcoded environments** – Everything is dynamically resolved at runtime.  
- **Uses AWS Parameter Store for configurations** – Ensuring deployments are **controlled via Git**.  
- **Works seamlessly with the `aws-config` and `aws-lambda` repos** to enable a fully **Configuration-Driven AWS Deployment Model**.  

---

## **📂 Repository Structure**
```
aws-iac/
│── components/
│   ├── vpc/               # Reusable VPC module
│   ├── aurora-postgres/   # Reusable Aurora RDS module
│   ├── ...
│── modules/
│── README.md
```

---

## **🚀 How It Works**
### **1️⃣ Requires Predefined Configuration**
Terraform **does not deploy anything unless the configuration exists in AWS Parameter Store**.  
Before applying Terraform, the configuration must exist in the **[`aws-config`](https://github.com/your-username/aws-config)** repository and be synced to Parameter Store.

Example: If deploying a VPC with the nickname **`main-vpc`**, Terraform checks for:
```
/aws/vpc/main-vpc/config  ✅ (Required for deployment)
/aws/vpc/main-vpc/runtime ⏳ (Created after deployment)
```
If the **config entry is missing, Terraform fails**.

### **2️⃣ Deploys Only Pre-Approved Components**
Once the config is verified, Terraform dynamically deploys the AWS infrastructure and registers the runtime details.

```sh
terraform init
terraform apply -var="nickname=main-vpc"
```

---

## **📖 Example: Deploying a VPC**
### **1️⃣ Define the VPC Configuration (in `aws-config`)**
Add a JSON entry in the config repo:
```json
{
  "vpc_cidr": "10.0.0.0/16",
  "enable_dns_support": true,
  "private_subnet_cidrs": ["10.0.1.0/24", "10.0.2.0/24"]
}
```

### **2️⃣ Deploy the VPC Using Terraform**
Run Terraform with the nickname matching the configuration:
```sh
terraform apply -var="nickname=main-vpc"
```

### **3️⃣ Terraform Registers the VPC Runtime Info**
After deployment, Terraform stores the **live details** in AWS Parameter Store:
```
/aws/vpc/main-vpc/runtime  ✅ (Contains VPC ID, subnets, security groups)
```
Any dependent component (e.g., an RDS database) **can now resolve this dynamically**.

---

## **🔄 Dynamic Dependency Resolution**
Since all components register their **runtime details** in AWS Parameter Store, dependent components can **dynamically resolve infrastructure settings**.

Example: An Aurora-Postgres database module retrieves its **VPC details dynamically** instead of requiring hardcoded Terraform references.
```hcl
data "aws_ssm_parameter" "vpc_runtime" {
  name = "/aws/vpc/main-vpc/runtime"
}
locals {
  vpc_details = jsondecode(data.aws_ssm_parameter.vpc_runtime.value)
}
```
This means **Terraform does not need to reference state files** for dependencies—everything is discovered dynamically.

---

## **🔐 Security & Compliance**
✅ **Prevents unauthorized deployments** – Terraform will only deploy what’s explicitly defined in the config repo.  
✅ **Ensures full auditability** – Since all changes must go through Git, every deployment is tracked.  
✅ **Uses AWS Secrets Manager for sensitive credentials** – Preventing secrets from being exposed in Terraform state.  

---

## 🧠 Project Background

This repository is part of a broader open-source architecture I’ve developed to support configuration-driven AWS deployment.

While some of these ideas were shaped through years of professional experience and refinement, the implementations here are entirely original — built independently and outside the context of any prior employment.

For the full context and design principles behind this system, see the [aws-deployment-guide](https://github.com/tstrall/aws-deployment-guide).

---

## **📌 Next Steps**
Want to implement this in your AWS environment? Here’s what to do next:  
1️⃣ **Fork this repo and configure your own components.**  
2️⃣ **Connect this repo with `aws-config` and `aws-lambda` to manage full-stack deployments.**  
3️⃣ **Set up a CI/CD pipeline to enforce configuration validation before Terraform runs.**  

📩 **Questions? Reach out or contribute!**  
This is an open-source approach, and improvements are always welcome.  

---

📢 **Like this approach? Star the repo and follow for updates!** 🚀  
