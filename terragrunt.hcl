locals {
  account_id     = get_env("TF_ACCOUNT_ID", "")
  region         = get_env("TF_REGION", "")
  component_name = get_env("TF_COMPONENT", "")
  nickname       = get_env("TF_NICKNAME", "")

  source_path    = "${get_repo_root()}/components/${local.component_name}"

  s3_bucket      = "${local.account_id}-tf-state"
  dynamodb_table = "${local.account_id}-tf-locks"
  tfstate_key    = "${local.component_name}/${local.nickname}/terraform.tfstate"
}

terraform {
  source = local.source_path
}

inputs = {
  nickname = local.nickname
  region   = local.region
}

remote_state {
  backend = "s3"
  config = {
    bucket         = local.s3_bucket
    key            = local.tfstate_key
    region         = local.region
    dynamodb_table = local.dynamodb_table
    encrypt        = true
  }
}
