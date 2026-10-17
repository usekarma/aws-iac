mock_provider "aws" {}
mock_provider "awscc" {}
run "reject_wrong_region" {
  command = plan
  variables {
    region = "us-west-2"
    account_id = "000000000000"
    partition = "aws"
    config = {
      region = "us-east-1"
      expected_account = "000000000000"
      expected_principal = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
      cloudformation_role_arn = "arn:aws:iam::000000000000:role/synthetic"
    }
  }
  expect_failures = [awscc_iotsitewise_asset_model.model]
}
