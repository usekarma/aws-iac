#############################################
# Grafana + Kafka Connect EC2 behind HTTPS ALB
# - No variables; all config via locals.config (header.tf)
# - Reads VPC + ClickHouse runtime from SSM
# - ALB 443 -> / (Grafana:3000), /connect/* (Connect:8083)
# - Cross-SG rules to ClickHouse:8123 and (optional) MSK:9098
# - Single runtime SSM parameter
#############################################

locals {
  cfg          = try(local.config, {})
  nickname     = try(local.cfg.nickname, "default")
  iac_prefix   = trim(try(local.cfg.iac_prefix, "/iac"), "/")

  # Runtime inputs
  vpc_runtime_path        = try(local.cfg.vpc_runtime_path, "/${local.iac_prefix}/vpc/${local.nickname}/runtime")
  clickhouse_runtime_path = try(local.cfg.clickhouse_runtime_path, "/${local.iac_prefix}/clickhouse/${local.nickname}/runtime")

  # Runtime output
  runtime_path = try(local.runtime_path, "/${local.iac_prefix}/grafana-connect/${local.nickname}/runtime")

  # EC2 instance
  instance_type = try(local.cfg.instance_type, "t3.large")
  ami_owner     = "137112412989" # AL2023
  key_name      = try(local.cfg.key_name, null)

  # Networking
  public_subnet_ids  = jsondecode(nonsensitive(data.aws_ssm_parameter.vpc_runtime.value)).public_subnet_ids
  private_subnet_ids = jsondecode(nonsensitive(data.aws_ssm_parameter.vpc_runtime.value)).private_subnet_ids
  vpc_id             = jsondecode(nonsensitive(data.aws_ssm_parameter.vpc_runtime.value)).vpc_id
  default_sg_id      = jsondecode(nonsensitive(data.aws_ssm_parameter.vpc_runtime.value)).default_sg_id

  # ALB + TLS
  domain_name     = try(local.cfg.domain_name, "grafana.example.com")   # e.g., grafana.usekarma.dev
  hosted_zone_id  = try(local.cfg.hosted_zone_id, null)                 # if R53 record desired
  acm_cert_arn    = try(local.cfg.acm_cert_arn, null)                   # required for HTTPS
  create_dns      = try(local.cfg.create_dns_record, true)

  # Ports
  grafana_port    = try(local.cfg.grafana_port, 3000)
  connect_port    = try(local.cfg.connect_port, 8083)

  # Kafka Connect bits (MSK + MongoDB CDC)
  # CH runtime includes msk_bootstrap_sasl_iam; we’ll use that
  connect_group_id  = try(local.cfg.connect_group_id, "${local.nickname}-connect")
  mongo_uri         = try(local.cfg.mongo_uri, null)           # e.g. "mongodb://user:pass@host:27017/?replicaSet=rs0"
  mongo_connector_class = try(local.cfg.mongo_connector_class, "io.debezium.connector.mongodb.MongoDbConnector")
  connector_name    = try(local.cfg.connector_name, "mongo-cdc")
  connector_config  = try(local.cfg.connector_config, {})      # free-form map merged into JSON

  # ClickHouse runtime (needed for Grafana datasource + cross-SG)
  ch_runtime = jsondecode(nonsensitive(data.aws_ssm_parameter.ch_runtime.value))

  # Optional: MSK SG name discovery if you want to add Connect->MSK ingress on MSK SG
  discover_msk_sg_by_name = try(local.cfg.discover_msk_sg_by_name, true)
  msk_sg_name             = try(local.cfg.msk_sg_name, "${local.nickname}-sg-msk-srvless")

  # Choose first private subnet for the instance (simple)
  subnet_id = local.private_subnet_ids[0]
}

############################
# Read VPC + ClickHouse runtime JSON
############################
data "aws_ssm_parameter" "vpc_runtime" {
  name = local.vpc_runtime_path
}
data "aws_ssm_parameter" "ch_runtime" {
  name = local.clickhouse_runtime_path
}

############################
# AMI AL2023
############################
data "aws_ami" "al2023" {
  owners      = [local.ami_owner]
  most_recent = true
  filter { name = "name"; values = ["al2023-ami-*-x86_64"] }
  filter { name = "architecture"; values = ["x86_64"] }
  filter { name = "root-device-type"; values = ["ebs"] }
}

############################
# IAM role / instance profile
############################
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service"; identifiers = ["ec2.amazonaws.com"] }
  }
}
resource "aws_iam_role" "this" {
  name               = "${local.nickname}-grafana-connect-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = local.tags
}
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
# Allow Connect to talk to MSK (IAM auth) and basic describe
data "aws_iam_policy_document" "msk_client" {
  statement {
    actions   = ["kafka-cluster:Connect","kafka:GetBootstrapBrokers","kafka:DescribeCluster"]
    resources = ["*"]
  }
}
resource "aws_iam_policy" "msk_client" {
  name   = "${local.nickname}-grafana-connect-msk-client"
  policy = data.aws_iam_policy_document.msk_client.json
  tags   = local.tags
}
resource "aws_iam_role_policy_attachment" "msk_client" {
  role       = aws_iam_role.this.name
  policy_arn = aws_iam_policy.msk_client.arn
}
resource "aws_iam_instance_profile" "this" {
  name = "${local.nickname}-grafana-connect-profile"
  role = aws_iam_role.this.name
}

############################
# Security Groups
############################

# ALB SG: allow 443 from internet
resource "aws_security_group" "alb" {
  name        = "${local.nickname}-sg-alb"
  description = "ALB for Grafana+Connect"
  vpc_id      = local.vpc_id
  ingress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = "HTTPS"
    from_port        = 443
    to_port          = 443
    ipv6_cidr_blocks = null
    prefix_list_ids  = null
    protocol         = "tcp"
    security_groups  = null
    self             = null
  }]
  egress = [{
    cidr_blocks = ["0.0.0.0/0"]
    description = "all egress"
    from_port = 0
    to_port = 0
    ipv6_cidr_blocks = null
    prefix_list_ids = null
    protocol = "-1"
    security_groups = null
    self = null
  }]
  tags = merge(local.tags, { Role = "alb", Name = "${local.nickname}-sg-alb" })
}

# Instance SG: no inbound from internet (ALB only); allow ALB SG to 3000/8083
resource "aws_security_group" "app" {
  name        = "${local.nickname}-sg-grafana-connect"
  description = "EC2 running Grafana and Kafka Connect"
  vpc_id      = local.vpc_id
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
  tags = merge(local.tags, { Role = "grafana-connect", Name = "${local.nickname}-sg-grafana-connect" })
}

resource "aws_vpc_security_group_ingress_rule" "alb_to_grafana" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = local.grafana_port
  to_port                      = local.grafana_port
  description                  = "ALB -> Grafana"
}
resource "aws_vpc_security_group_ingress_rule" "alb_to_connect" {
  security_group_id            = aws_security_group.app.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = local.connect_port
  to_port                      = local.connect_port
  description                  = "ALB -> Kafka Connect REST"
}

# Cross-component SG: allow this app SG to query ClickHouse HTTP (8123)
resource "aws_vpc_security_group_ingress_rule" "app_to_clickhouse_8123" {
  security_group_id            = local.ch_runtime.security_group_id   # the CH SG
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = try(local.ch_runtime.http_port, 8123)
  to_port                      = try(local.ch_runtime.http_port, 8123)
  description                  = "Grafana -> ClickHouse HTTP"
}

# Optional: add this app SG to MSK SG (9098) using Name tag lookup
data "aws_security_group" "msk" {
  count  = (try(local.ch_runtime.msk_enabled, false) && local.discover_msk_sg_by_name) ? 1 : 0
  filter { name = "vpc-id"; values = [local.vpc_id] }
  filter { name = "tag:Name"; values = [local.msk_sg_name] }
}
resource "aws_vpc_security_group_ingress_rule" "app_to_msk_9098" {
  count                       = (try(local.ch_runtime.msk_enabled, false) && local.discover_msk_sg_by_name) ? 1 : 0
  security_group_id           = data.aws_security_group.msk[0].id
  referenced_security_group_id= aws_security_group.app.id
  ip_protocol                 = "tcp"
  from_port                   = 9098
  to_port                     = 9098
  description                 = "Kafka Connect -> MSK brokers (SASL/IAM)"
}

############################
# EC2 instance
############################
data "aws_subnet" "chosen" { id = local.subnet_id }

resource "aws_instance" "app" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = local.instance_type
  subnet_id                   = local.subnet_id
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.this.name
  vpc_security_group_ids      = [aws_security_group.app.id]
  key_name                    = local.key_name

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 20
  }

  user_data = base64encode(templatefile("${path.module}/userdata.sh.tmpl", {
    GRAFANA_PORT     = local.grafana_port
    CONNECT_PORT     = local.connect_port
    CH_HTTP_URL      = "http://${local.ch_runtime.private_ip}:${try(local.ch_runtime.http_port,8123)}"
    CH_NAME          = "clickhouse"
    # MSK bootstrap for sink/source connectors if needed
    MSK_BOOTSTRAP    = try(local.ch_runtime.msk_bootstrap_sasl_iam, "")
    CONNECT_GROUP_ID = local.connect_group_id
    MONGO_URI        = coalesce(local.mongo_uri, "")
    CONNECTOR_NAME   = local.connector_name
    CONNECTOR_JSON   = jsonencode(local.connector_config)
  }))

  tags = merge(local.tags, {
    Name     = "${local.nickname}-grafana-connect"
    Nickname = local.nickname
    Role     = "grafana-connect"
  })
}

############################
# ALB (HTTPS)
############################
resource "aws_lb" "this" {
  name               = "${local.nickname}-grafana"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = local.public_subnet_ids
  idle_timeout       = 60
  tags               = local.tags
}

# Target groups (instance target type; attach with per-target port)
resource "aws_lb_target_group" "grafana" {
  name        = "${local.nickname}-tg-grafana"
  port        = 80
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = local.vpc_id
  health_check {
    path                = "/login"
    matcher             = "200-399"
    healthy_threshold   = 2
    unhealthy_threshold = 5
    interval            = 30
    timeout             = 5
  }
  tags = local.tags
}
resource "aws_lb_target_group" "connect" {
  name        = "${local.nickname}-tg-connect"
  port        = 80
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = local.vpc_id
  health_check {
    path                = "/connectors"
    matcher             = "200,204,401" # connect often 401s; treat as alive
    healthy_threshold   = 2
    unhealthy_threshold = 5
    interval            = 30
    timeout             = 5
  }
  tags = local.tags
}

# Register the same instance twice, each with a different port
resource "aws_lb_target_group_attachment" "grafana" {
  target_group_arn = aws_lb_target_group.grafana.arn
  target_id        = aws_instance.app.id
  port             = local.grafana_port
}
resource "aws_lb_target_group_attachment" "connect" {
  target_group_arn = aws_lb_target_group.connect.arn
  target_id        = aws_instance.app.id
  port             = local.connect_port
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = local.acm_cert_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.grafana.arn
  }
}

# Path rule to route /connect/* to Kafka Connect
resource "aws_lb_listener_rule" "connect" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action { type = "forward"; target_group_arn = aws_lb_target_group.connect.arn }
  condition { path_pattern { values = ["/connect/*"] } }
}

# Optional DNS record
resource "aws_route53_record" "dns" {
  count   = local.create_dns && local.hosted_zone_id != null ? 1 : 0
  zone_id = local.hosted_zone_id
  name    = local.domain_name
  type    = "A"
  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = false
  }
}

############################
# Runtime SSM output
############################
resource "aws_ssm_parameter" "runtime" {
  name  = local.runtime_path
  type  = "String"
  value = jsonencode({
    instance_id       = aws_instance.app.id,
    instance_sg_id    = aws_security_group.app.id,
    alb_dns           = aws_lb.this.dns_name,
    https_url         = "https://${local.domain_name}",
    connect_base_path = "/connect",
    grafana_port      = local.grafana_port,
    connect_port      = local.connect_port,
    vpc_id            = local.vpc_id,
    subnet_id         = local.subnet_id
  })
  overwrite = true
  tier      = "Standard"
  tags      = local.tags
}
