# Makefile for ClickHouse / Mongo / Redpanda AMI builds
# - Builds AMIs with Packer
# - Writes JSON SSM parameters under /iac/clickhouse/ami/*

AWS_REGION  ?= us-east-1
AWS_PROFILE ?= prod-iac

ROOT_VOLUME_SIZE_GB ?= 30

CLICKHOUSE_VERSION    ?=
PROMETHEUS_VERSION    ?=
NODE_EXPORTER_VERSION ?=
GRAFANA_VERSION       ?=

MONGO_MAJOR ?= 7

# Where Terraform expects AMI metadata
SSM_AMI_PREFIX ?= /iac/clickhouse/ami

PACKER ?= packer

.PHONY: all clickhouse mongo redpanda fmt clean-logs

all: clickhouse mongo redpanda

fmt:
	@$(PACKER) fmt clickhouse-ami.pkr.hcl
	@$(PACKER) fmt mongo-ami.pkr.hcl
	@$(PACKER) fmt redpanda-ami.pkr.hcl

clean-logs:
	@rm -f build-clickhouse.log build-mongo.log build-redpanda.log

# ----------------------------
# ClickHouse AMI + SSM
# ----------------------------
clickhouse:
	@echo "=== Building ClickHouse AMI ==="
	@$(PACKER) fmt clickhouse-ami.pkr.hcl
	@$(PACKER) validate \
	  -var "aws_region=$(AWS_REGION)" \
	  -var "root_volume_size_gb=$(ROOT_VOLUME_SIZE_GB)" \
	  -var "clickhouse_version=$(CLICKHOUSE_VERSION)" \
	  -var "prometheus_version=$(PROMETHEUS_VERSION)" \
	  -var "node_exporter_version=$(NODE_EXPORTER_VERSION)" \
	  -var "grafana_version=$(GRAFANA_VERSION)" \
	  clickhouse-ami.pkr.hcl

	@set -e; \
	  LOG=build-clickhouse.log; \
	  echo "[clickhouse] Running packer build..."; \
	  AWS_REGION=$(AWS_REGION) AWS_PROFILE=$(AWS_PROFILE) \
	    $(PACKER) build \
	      -var "aws_region=$(AWS_REGION)" \
	      -var "root_volume_size_gb=$(ROOT_VOLUME_SIZE_GB)" \
	      -var "clickhouse_version=$(CLICKHOUSE_VERSION)" \
	      -var "prometheus_version=$(PROMETHEUS_VERSION)" \
	      -var "node_exporter_version=$(NODE_EXPORTER_VERSION)" \
	      -var "grafana_version=$(GRAFANA_VERSION)" \
	      clickhouse-ami.pkr.hcl | tee $$LOG; \
	  AMI_ID=$$(awk '/^us-.*: ami-/{print $$2}' $$LOG | tail -1); \
	  if [ -z "$$AMI_ID" ]; then \
	    echo "[clickhouse] ERROR: Could not parse AMI ID from $$LOG"; \
	    exit 1; \
	  fi; \
	  echo "[clickhouse] Built AMI $$AMI_ID"; \
	  VERSION="$(CLICKHOUSE_VERSION)"; \
	  if [ -z "$$VERSION" ]; then VERSION="latest"; fi; \
	  BUILT_AT=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	  JSON="$$(cat <<EOF \
{
  \"ami_id\": \"$$AMI_ID\",
  \"component\": \"clickhouse\",
  \"version\": \"$$VERSION\",
  \"os\": \"Amazon Linux 2023\",
  \"arch\": \"x86_64\",
  \"root_volume_size_gb\": $(ROOT_VOLUME_SIZE_GB),
  \"built_at\": \"$$BUILT_AT\"
}
EOF
)"; \
	  echo "[clickhouse] Writing SSM parameter $(SSM_AMI_PREFIX)/base"; \
	  aws ssm put-parameter \
	    --region "$(AWS_REGION)" \
	    --profile "$(AWS_PROFILE)" \
	    --name "$(SSM_AMI_PREFIX)/base" \
	    --type "String" \
	    --overwrite \
	    --value "$$JSON" >/dev/null; \
	  echo "[clickhouse] SSM update complete."

# ----------------------------
# Mongo AMI + SSM
# ----------------------------
mongo:
	@echo "=== Building Mongo AMI ==="
	@$(PACKER) fmt mongo-ami.pkr.hcl
	@$(PACKER) validate \
	  -var "aws_region=$(AWS_REGION)" \
	  -var "root_volume_size_gb=$(ROOT_VOLUME_SIZE_GB)" \
	  -var "mongo_major=$(MONGO_MAJOR)" \
	  mongo-ami.pkr.hcl

	@set -e; \
	  LOG=build-mongo.log; \
	  echo "[mongo] Running packer build..."; \
	  AWS_REGION=$(AWS_REGION) AWS_PROFILE=$(AWS_PROFILE) \
	    $(PACKER) build \
	      -var "aws_region=$(AWS_REGION)" \
	      -var "root_volume_size_gb=$(ROOT_VOLUME_SIZE_GB)" \
	      -var "mongo_major=$(MONGO_MAJOR)" \
	      mongo-ami.pkr.hcl | tee $$LOG; \
	  AMI_ID=$$(awk '/^us-.*: ami-/{print $$2}' $$LOG | tail -1); \
	  if [ -z "$$AMI_ID" ]; then \
	    echo "[mongo] ERROR: Could not parse AMI ID from $$LOG"; \
	    exit 1; \
	  fi; \
	  echo "[mongo] Built AMI $$AMI_ID"; \
	  VERSION="$(MONGO_MAJOR).x"; \
	  BUILT_AT=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	  JSON="$$(cat <<EOF \
{
  \"ami_id\": \"$$AMI_ID\",
  \"component\": \"mongo\",
  \"version\": \"$$VERSION\",
  \"os\": \"Amazon Linux 2023\",
  \"arch\": \"x86_64\",
  \"root_volume_size_gb\": $(ROOT_VOLUME_SIZE_GB),
  \"built_at\": \"$$BUILT_AT\"
}
EOF
)"; \
	  echo "[mongo] Writing SSM parameter $(SSM_AMI_PREFIX)/mongo"; \
	  aws ssm put-parameter \
	    --region "$(AWS_REGION)" \
	    --profile "$(AWS_PROFILE)" \
	    --name "$(SSM_AMI_PREFIX)/mongo" \
	    --type "String" \
	    --overwrite \
	    --value "$$JSON" >/dev/null; \
	  echo "[mongo] SSM update complete."

# ----------------------------
# Redpanda AMI + SSM
# ----------------------------
redpanda:
	@echo "=== Building Redpanda AMI ==="
	@$(PACKER) fmt redpanda-ami.pkr.hcl
	@$(PACKER) validate \
	  -var "aws_region=$(AWS_REGION)" \
	  -var "root_volume_size_gb=$(ROOT_VOLUME_SIZE_GB)" \
	  redpanda-ami.pkr.hcl

	@set -e; \
	  LOG=build-redpanda.log; \
	  echo "[redpanda] Running packer build..."; \
	  AWS_REGION=$(AWS_REGION) AWS_PROFILE=$(AWS_PROFILE) \
	    $(PACKER) build \
	      -var "aws_region=$(AWS_REGION)" \
	      -var "root_volume_size_gb=$(ROOT_VOLUME_SIZE_GB)" \
	      redpanda-ami.pkr.hcl | tee $$LOG; \
	  AMI_ID=$$(awk '/^us-.*: ami-/{print $$2}' $$LOG | tail -1); \
	  if [ -z "$$AMI_ID" ]; then \
	    echo "[redpanda] ERROR: Could not parse AMI ID from $$LOG"; \
	    exit 1; \
	  fi; \
	  echo "[redpanda] Built AMI $$AMI_ID"; \
	  VERSION="latest"; \
	  BUILT_AT=$$(date -u +%Y-%m-%dT%H:%M:%SZ); \
	  JSON="$$(cat <<EOF \
{
  \"ami_id\": \"$$AMI_ID\",
  \"component\": \"redpanda\",
  \"version\": \"$$VERSION\",
  \"os\": \"Amazon Linux 2023\",
  \"arch\": \"x86_64\",
  \"root_volume_size_gb\": $(ROOT_VOLUME_SIZE_GB),
  \"built_at\": \"$$BUILT_AT\"
}
EOF
)"; \
	  echo "[redpanda] Writing SSM parameter $(SSM_AMI_PREFIX)/redpanda"; \
	  aws ssm put-parameter \
	    --region "$(AWS_REGION)" \
	    --profile "$(AWS_PROFILE)" \
	    --name "$(SSM_AMI_PREFIX)/redpanda" \
	    --type "String" \
	    --overwrite \
	    --value "$$JSON" >/dev/null; \
	  echo "[redpanda] SSM update complete."
