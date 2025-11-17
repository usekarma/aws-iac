PACKER ?= packer
AWS_REGION ?= us-east-1

# Optional version overrides
CLICKHOUSE_VERSION ?=
PROMETHEUS_VERSION ?=
NODE_EXPORTER_VERSION ?=
GRAFANA_VERSION ?=

PACKER_VARS = \
  -var "aws_region=$(AWS_REGION)" \
  -var "clickhouse_version=$(CLICKHOUSE_VERSION)" \
  -var "prometheus_version=$(PROMETHEUS_VERSION)" \
  -var "node_exporter_version=$(NODE_EXPORTER_VERSION)" \
  -var "grafana_version=$(GRAFANA_VERSION)"

validate:
	$(PACKER) validate $(PACKER_VARS) clickhouse-ami.pkr.hcl

build:
	$(PACKER) build $(PACKER_VARS) clickhouse-ami.pkr.hcl

all: validate build
