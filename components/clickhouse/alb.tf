locals {
  # Domain + hosts (derive sensible defaults if missing)
  domain_name = try(local.config.domain_name, "usekarma.dev")
  alb_name    = try(local.config.alb_name, "usekarma-observability")

  grafana_host    = try(local.config.grafana_host,    format("grafana.%s",    local.domain_name))
  prometheus_host = try(local.config.prometheus_host, format("prometheus.%s", local.domain_name))
  clickhouse_host = try(local.config.clickhouse_host, format("clickhouse.%s", local.domain_name))
  mongo_host      = try(local.config.mongo_host,      format("mongo.%s",      local.domain_name))

  # Versions
  prometheus_ver = try(local.config.prometheus_ver, "2.54.1")
  nodeexp_ver    = try(local.config.nodeexp_ver,    "1.8.1")

  # zone_id is optional in config; if omitted, we’ll look it up by domain
  zone_id_opt = try(local.config.zone_id, null)
}

# Auto-lookup public hosted zone only when zone_id isn’t provided
data "aws_route53_zone" "this" {
  count        = local.zone_id_opt == null ? 1 : 0
  name         = local.domain_name
  private_zone = false
}

locals {
  zone_id = local.zone_id_opt != null ? local.zone_id_opt : data.aws_route53_zone.this[0].zone_id

  # Include hosts in SANs; only add mongo when enabled
  alt_names = compact(distinct(concat(
    [
      local.grafana_host,
      local.prometheus_host,
      local.clickhouse_host,
    ],
    local.enable_mongo ? [local.mongo_host] : []
  )))
}

# ---------- ACM certificate + DNS validation ----------
resource "aws_acm_certificate" "this" {
  domain_name               = local.domain_name
  subject_alternative_names = local.alt_names
  validation_method         = "DNS"
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.this.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = local.zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.value]
  ttl     = 60

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# ---------- ALB Security Group ----------
resource "aws_security_group" "alb" {
  name        = "${local.alb_name}-sg"
  description = "ALB for Grafana/Prometheus/ClickHouse/Mongo"
  vpc_id      = local.vpc_id

  # HTTPS + HTTP (for redirect)
  ingress = [
    {
      description      = "HTTPS"
      from_port        = 443
      to_port          = 443
      protocol         = "tcp"
      cidr_blocks      = ["0.0.0.0/0"]
      ipv6_cidr_blocks = null
      prefix_list_ids  = null
      security_groups  = null
      self             = null
    },
    {
      description      = "HTTP (redirect to HTTPS)"
      from_port        = 80
      to_port          = 80
      protocol         = "tcp"
      cidr_blocks      = ["0.0.0.0/0"]
      ipv6_cidr_blocks = null
      prefix_list_ids  = null
      security_groups  = null
      self             = null
    }
  ]

  egress = [{
    description      = "all egress"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = null
    prefix_list_ids  = null
    security_groups  = null
    self             = null
  }]

  tags = local.tags
}

# ---------- Allow ALB → instance app ports ----------
resource "aws_vpc_security_group_ingress_rule" "from_alb_grafana" {
  security_group_id            = aws_security_group.clickhouse.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 3000
  description                  = "ALB to Grafana"
}

resource "aws_vpc_security_group_ingress_rule" "from_alb_prometheus" {
  security_group_id            = aws_security_group.clickhouse.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 9090
  to_port                      = 9090
  description                  = "ALB to Prometheus"
}

resource "aws_vpc_security_group_ingress_rule" "from_alb_clickhouse" {
  security_group_id            = aws_security_group.clickhouse.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = local.clickhouse_http_port
  to_port                      = local.clickhouse_http_port
  description                  = "ALB to ClickHouse HTTP"
}

# Allow ALB → Mongo instance (mongo-express) on 8081
resource "aws_vpc_security_group_ingress_rule" "from_alb_mongo_express" {
  count = local.enable_mongo ? 1 : 0

  security_group_id            = aws_security_group.mongo[0].id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8081
  to_port                      = 8081
  description                  = "ALB to mongo-express"
}

# ---------- ALB ----------
resource "aws_lb" "obs" {
  name               = local.alb_name
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = local.vpc.public_subnet_ids
  ip_address_type    = "ipv4"
  tags               = local.tags
}

# ---------- Target Groups (HTTP; ALB terminates TLS) ----------
# Use name_prefix to avoid 32-char TG name limit. Explicit matchers & target_type.
resource "aws_lb_target_group" "grafana" {
  name_prefix = "gf-" # AWS appends unique suffix
  port        = 3000
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = local.vpc_id

  health_check {
    path                = "/api/health" # 200 OK on Grafana ≥8
    protocol            = "HTTP"
    matcher             = "200-399"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }

  deregistration_delay = 10
}

resource "aws_lb_target_group" "prometheus" {
  name_prefix = "pr-"
  port        = 9090
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = local.vpc_id

  health_check {
    path                = "/-/ready"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }

  deregistration_delay = 10
}

resource "aws_lb_target_group" "clickhouse" {
  name_prefix = "ch-"
  port        = local.clickhouse_http_port
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = local.vpc_id

  health_check {
    path                = "/ping" # ClickHouse returns 200 OK
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 5
  }

  deregistration_delay = 10
}

resource "aws_lb_target_group" "mongo_express" {
  count       = local.enable_mongo ? 1 : 0
  name_prefix = "mg-"
  port        = 8081
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = local.vpc_id

  health_check {
    path                = "/"
    protocol            = "HTTP"
    port                = "8081"
    healthy_threshold   = 2
    unhealthy_threshold = 5
    timeout             = 5
    interval            = 30
    matcher             = "200-399"
  }

  deregistration_delay = 10
}

# ---------- Attach instances to TGs ----------
resource "aws_lb_target_group_attachment" "grafana" {
  target_group_arn = aws_lb_target_group.grafana.arn
  target_id        = aws_instance.clickhouse.id
  port             = 3000
}

resource "aws_lb_target_group_attachment" "prometheus" {
  target_group_arn = aws_lb_target_group.prometheus.arn
  target_id        = aws_instance.clickhouse.id
  port             = 9090
}

resource "aws_lb_target_group_attachment" "clickhouse" {
  target_group_arn = aws_lb_target_group.clickhouse.arn
  target_id        = aws_instance.clickhouse.id
  port             = local.clickhouse_http_port
}

resource "aws_lb_target_group_attachment" "mongo_express" {
  count = local.enable_mongo ? 1 : 0

  target_group_arn = aws_lb_target_group.mongo_express[0].arn
  target_id        = aws_instance.mongo[0].id
  port             = 8081
}

# ---------- Listeners ----------
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.obs.arn
  port              = 443
  protocol          = "HTTPS"

  certificate_arn = aws_acm_certificate_validation.this.certificate_arn
  ssl_policy      = "ELBSecurityPolicy-TLS13-1-2-2021-06" # modern TLS1.2/1.3

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Not Found"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.obs.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# ---------- Host-based routing ----------
resource "aws_lb_listener_rule" "grafana_host" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.grafana.arn
  }

  condition {
    host_header { values = [local.grafana_host] }
  }
}

resource "aws_lb_listener_rule" "prometheus_host" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 20

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.prometheus.arn
  }

  condition {
    host_header { values = [local.prometheus_host] }
  }
}

resource "aws_lb_listener_rule" "clickhouse_host" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 30

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.clickhouse.arn
  }

  condition {
    host_header { values = [local.clickhouse_host] }
  }
}

resource "aws_lb_listener_rule" "mongo_host" {
  count        = local.enable_mongo ? 1 : 0
  listener_arn = aws_lb_listener.https.arn
  priority     = 40

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mongo_express[0].arn
  }

  condition {
    host_header {
      values = [local.mongo_host] # defaults to "mongo.usekarma.dev"
    }
  }
}

# ---------- Route53 A-records to ALB ----------
resource "aws_route53_record" "grafana" {
  zone_id = local.zone_id
  name    = local.grafana_host
  type    = "A"
  alias {
    name                   = aws_lb.obs.dns_name
    zone_id                = aws_lb.obs.zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "prometheus" {
  zone_id = local.zone_id
  name    = local.prometheus_host
  type    = "A"
  alias {
    name                   = aws_lb.obs.dns_name
    zone_id                = aws_lb.obs.zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "clickhouse" {
  zone_id = local.zone_id
  name    = local.clickhouse_host
  type    = "A"
  alias {
    name                   = aws_lb.obs.dns_name
    zone_id                = aws_lb.obs.zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "mongo" {
  count  = local.enable_mongo ? 1 : 0
  zone_id = local.zone_id
  name    = local.mongo_host    # "mongo.usekarma.dev"
  type    = "A"
  alias {
    name                   = aws_lb.obs.dns_name
    zone_id                = aws_lb.obs.zone_id
    evaluate_target_health = false
  }
}
