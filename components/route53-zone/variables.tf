variable "aws_region" {
  type        = string
  description = "The AWS region to use"
  default     = "us-east-1"
}

variable "nickname" {
  type        = string
  description = "Logical nickname (used for config path and resource resolution)"
}

variable "iac_prefix" {
  default = "/iac"
}
