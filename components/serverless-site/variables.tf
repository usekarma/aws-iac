variable "nickname" {
  description = "Unique name for this site deployment"
  type        = string
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}
