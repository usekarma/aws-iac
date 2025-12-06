#!/usr/bin/env bash
set -euo pipefail

./scripts/deploy.sh vpc usekarma-dev
./scripts/deploy.sh ecs-cluster usekarma-dev
./scripts/deploy.sh clickhouse usekarma-dev
./scripts/deploy.sh lambda demo-api

# finish setting up lambda for serverless-api
cd ../aws-openapi/
./ch-up.sh
cd -

./scripts/deploy.sh serverless-api demo-api
