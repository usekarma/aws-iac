variable "domain" {
  description = "Domain name to receive email for"
  type        = string
}

variable "forward_to_addresses" {
  description = "List of email addresses to forward incoming email to"
  type        = list(string)
}

variable "from_email" {
  description = "Verified email used as the sender for forwarded messages"
  type        = string
}
