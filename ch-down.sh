#!/usr/bin/env bash
set -euo pipefail

./scripts/deploy.sh serverless-api demo-api -d
./scripts/deploy.sh lambda demo-api -d
./scripts/deploy.sh clickhouse usekarma-dev -d
./scripts/deploy.sh ecs-cluster usekarma-dev -d
./scripts/deploy.sh vpc usekarma-dev -d
