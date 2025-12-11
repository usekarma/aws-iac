locals {
  vpc_cidr             = try(local.config.cidr, "10.42.0.0/16")
  az_count             = try(local.config.az_count, 2)
  enable_ssm_endpoints = try(local.config.enable_ssm_endpoints, true)
  single_nat_gateway   = try(local.config.single_nat_gateway, true)

  # optional DHCP options
  dhcp_domain_name         = try(local.config.dhcp_domain_name, null) # e.g. "svc.usekarma.local"
  dhcp_domain_name_servers = try(local.config.dhcp_domain_name_servers, ["AmazonProvidedDNS"])

  # AZ slice
  azs = slice(data.aws_availability_zones.available.names, 0, local.az_count)

  # Subnet CIDRs derived from VPC CIDR
  public_subnet_cidrs  = [for i in range(local.az_count) : cidrsubnet(local.vpc_cidr, 4, i)]
  private_subnet_cidrs = [for i in range(local.az_count) : cidrsubnet(local.vpc_cidr, 4, i + 8)]

  default_sg_name                = "${var.nickname}-sg-default"
  default_sg_allow_self          = try(local.config.default_sg_allow_self, false)
  default_sg_extra_ingress_cidrs = try(local.config.default_sg_extra_ingress_cidrs, [])
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_vpc_endpoint_service" "ssm" {
  service = "ssm"
}

data "aws_vpc_endpoint_service" "ssmmessages" {
  service = "ssmmessages"
}

data "aws_vpc_endpoint_service" "ec2messages" {
  service = "ec2messages"
}

data "aws_region" "current" {}

resource "aws_vpc" "this" {
  cidr_block           = local.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = merge(
    local.tags,
    {
      Name = var.nickname
    }
  )
}

###############################################
# Optional DHCP option set (per-VPC)
###############################################

resource "aws_vpc_dhcp_options" "this" {
  count = local.dhcp_domain_name == null ? 0 : 1

  domain_name         = local.dhcp_domain_name
  domain_name_servers = local.dhcp_domain_name_servers

  tags = merge(
    local.tags,
    {
      Name = "${var.nickname}-dhcp-options"
    }
  )
}

resource "aws_vpc_dhcp_options_association" "this" {
  count = local.dhcp_domain_name == null ? 0 : 1

  vpc_id          = aws_vpc.this.id
  dhcp_options_id = aws_vpc_dhcp_options.this[0].id
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Name = "${var.nickname}-igw" })
}

resource "aws_subnet" "public" {
  for_each                = { for idx, az in local.azs : idx => { az = az, cidr = local.public_subnet_cidrs[idx] } }
  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value.cidr
  availability_zone       = each.value.az
  map_public_ip_on_launch = true
  tags                    = merge(local.tags, { Tier = "public", AZ = each.value.az, Name = "${var.nickname}-public" })
}

resource "aws_subnet" "private" {
  for_each          = { for idx, az in local.azs : idx => { az = az, cidr = local.private_subnet_cidrs[idx] } }
  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az
  tags              = merge(local.tags, { Tier = "private", AZ = each.value.az, Name = "${var.nickname}-private" })
}

# Routing (single NAT by default to save $)
resource "aws_eip" "nat" {
  count      = local.single_nat_gateway ? 1 : local.az_count
  domain     = "vpc"
  depends_on = [aws_internet_gateway.igw]
  tags       = merge(local.tags, { Name = "${var.nickname}-nat" })
}

resource "aws_nat_gateway" "nat" {
  for_each = local.single_nat_gateway ? {
    "0" = {
      subnet_id         = aws_subnet.public["0"].id
      eip_allocation_id = aws_eip.nat[0].id
    }
    } : {
    for idx, s in aws_subnet.public : tostring(idx) => {
      subnet_id         = s.id
      eip_allocation_id = aws_eip.nat[idx].id
    }
  }

  allocation_id = each.value.eip_allocation_id
  subnet_id     = each.value.subnet_id
  tags          = merge(local.tags, { Name = "${var.nickname}-nat" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags   = merge(local.tags, { Tier = "public", Name = "${var.nickname}-public" })
}

resource "aws_route" "public_igw" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "public_assoc" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  for_each = aws_subnet.private
  vpc_id   = aws_vpc.this.id
  tags     = merge(local.tags, { Tier = "private", AZ = each.value.availability_zone, Name = "${var.nickname}-private" })
}

resource "aws_route" "private_nat" {
  for_each               = aws_route_table.private
  route_table_id         = each.value.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = local.single_nat_gateway ? aws_nat_gateway.nat["0"].id : aws_nat_gateway.nat[each.key].id
}

resource "aws_route_table_association" "private_assoc" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}

resource "aws_vpc_endpoint" "ssm" {
  count               = local.enable_ssm_endpoints ? 1 : 0
  vpc_id              = aws_vpc.this.id
  service_name        = data.aws_vpc_endpoint_service.ssm.service_name
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for s in aws_subnet.private : s.id]
  security_group_ids  = [aws_security_group.sg_default.id]
  tags                = merge(local.tags, { Name = "${var.nickname}-ssm" })
}

resource "aws_vpc_endpoint" "ssmmessages" {
  count               = local.enable_ssm_endpoints ? 1 : 0
  vpc_id              = aws_vpc.this.id
  service_name        = data.aws_vpc_endpoint_service.ssmmessages.service_name
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for s in aws_subnet.private : s.id]
  security_group_ids  = [aws_security_group.sg_default.id]
  tags                = merge(local.tags, { Name = "${var.nickname}-ssmmessages" })
}

resource "aws_vpc_endpoint" "ec2messages" {
  count               = local.enable_ssm_endpoints ? 1 : 0
  vpc_id              = aws_vpc.this.id
  service_name        = data.aws_vpc_endpoint_service.ec2messages.service_name
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for s in aws_subnet.private : s.id]
  security_group_ids  = [aws_security_group.sg_default.id]
  tags                = merge(local.tags, { Name = "${var.nickname}-ec2messages" })
}

resource "aws_security_group" "sg_default" {
  name        = local.default_sg_name
  description = "General-purpose default SG for app instances in VPC ${aws_vpc.this.id}"
  vpc_id      = aws_vpc.this.id

  # No broad ingress by default (secure baseline)
  # Optional self-ingress and CIDR ingress rules defined below.

  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "all egress"
    from_port        = 0
    to_port          = 0
    ipv6_cidr_blocks = null
    prefix_list_ids  = null
    protocol         = "-1"
    security_groups  = null
    self             = null
  }]

  tags = merge(local.tags, { Role = "default-app", Name = "${var.nickname}-sg-default" })
}

# Narrow self-allow for HTTPS within the default SG,
# created only when SSM endpoints are enabled and you haven't enabled broad self-allow.
resource "aws_vpc_security_group_ingress_rule" "default_self_https_443" {
  count                        = local.enable_ssm_endpoints ? 1 : 0
  security_group_id            = aws_security_group.sg_default.id
  referenced_security_group_id = aws_security_group.sg_default.id
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  description                  = "HTTPS within default SG (for SSM interface endpoints)"
}

resource "aws_vpc_security_group_ingress_rule" "default_self_https_443_cidr" {
  count             = local.enable_ssm_endpoints ? 1 : 0
  security_group_id = aws_security_group.sg_default.id
  cidr_ipv4         = local.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "TEMP DEBUG: HTTPS from VPC to SSM endpoints"
}

# Optional: allow traffic among members of this default SG (east-west)
resource "aws_vpc_security_group_ingress_rule" "default_self" {
  count                        = local.default_sg_allow_self ? 1 : 0
  security_group_id            = aws_security_group.sg_default.id
  referenced_security_group_id = aws_security_group.sg_default.id
  ip_protocol                  = "-1"
  description                  = "Allow all east-west within default SG"
}

# Optional: allow extra CIDRs (e.g., office/VPN)
resource "aws_vpc_security_group_ingress_rule" "default_extra_cidrs" {
  for_each          = toset(local.default_sg_extra_ingress_cidrs)
  security_group_id = aws_security_group.sg_default.id
  cidr_ipv4         = each.value
  ip_protocol       = "-1"
  description       = "Extra ingress CIDR allowed by config"
}

resource "aws_ssm_parameter" "runtime" {
  name = local.runtime_path
  type = "String"
  value = jsonencode({
    vpc_id             = aws_vpc.this.id,
    vpc_cidr           = local.vpc_cidr,
    public_subnet_ids  = [for s in aws_subnet.public : s.id],
    private_subnet_ids = [for s in aws_subnet.private : s.id],
    default_sg_id      = aws_security_group.sg_default.id,
    has_nat            = local.single_nat_gateway,
    ssm_endpoints = compact([
      try(aws_vpc_endpoint.ssm[0].id, null),
      try(aws_vpc_endpoint.ssmmessages[0].id, null),
      try(aws_vpc_endpoint.ec2messages[0].id, null)
    ])
  })

  overwrite = true
  tier      = "Standard"
  tags      = local.tags
}
