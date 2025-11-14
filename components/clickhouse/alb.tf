locals {
  # Domain + hosts (derive sensible defaults if missing)
  domain_name = try(local.config.domain_name, "usekarma.dev")
  alb_name    = try(local.config.alb_name, "usekarma-observability")

  cognito_sso = jsondecode(nonsensitive(data.aws_ssm_parameter.cognito_runtime.value))

  grafana_host     = try(local.config.grafana_host, format("grafana.%s", local.domain_name))
  prometheus_host  = try(local.config.prometheus_host, format("prometheus.%s", local.domain_name))
  clickhouse_host  = try(local.config.clickhouse_host, format("clickhouse.%s", local.domain_name))
  mongo_express    = try(local.config.mongo_express, format("mongo.%s", local.domain_name))
  redpanda_console = try(local.config.redpanda_console, format("redpanda.%s", local.domain_name))

  # Versions
  prometheus_ver = try(local.config.prometheus_ver, "2.54.1")
  nodeexp_ver    = try(local.config.nodeexp_ver, "1.8.1")

  # zone_id is optional in config; if omitted, we’ll look it up by domain
  zone_id_opt = try(local.config.zone_id, null)

  # Hosted UI base host, e.g. "usekarma-obs.auth.us-east-1.amazoncognito.com"
  cognito_hosted_ui_host = format(
    "%s.auth.%s.amazoncognito.com",
    local.cognito_sso.user_pool_domain,
    local.cognito_sso.region
  )

  # Where Cognito should send the user after logout (Grafana as canonical landing page)
  cognito_logout_redirect_uri = format("https://%s/", local.grafana_host)
}

data "aws_ssm_parameter" "cognito_runtime" {
  name = "${var.iac_prefix}/cognito-sso/${local.config.cognito_sso_nickname}/runtime"
}

# Auto-lookup public hosted zone only when zone_id isn’t provided
data "aws_route53_zone" "this" {
  count        = local.zone_id_opt == null ? 1 : 0
  name         = local.domain_name
  private_zone = false
}

locals {
  zone_id = local.zone_id_opt != null ? local.zone_id_opt : data.aws_route53_zone.this[0].zone_id

  # Include hosts in SANs; only add mongo/redpanda when enabled
  alt_names = compact(distinct(concat(
    [
      local.grafana_host,
      local.prometheus_host,
      local.clickhouse_host,
    ],
    local.enable_mongo ? [local.mongo_express] : [],
    local.enable_redpanda ? [local.redpanda_console] : []
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
  name_prefix = "${local.alb_name}-sg-"
  description = "ALB for Grafana/Prometheus/ClickHouse/Mongo/Redpanda"
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

  lifecycle {
    create_before_destroy = true
  }

  tags = local.tags
}

# ---------- Allow ALB → instance / task app ports ----------
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
resource "aws_lb_target_group" "grafana" {
  name_prefix = "gf-"
  port        = 3000
  protocol    = "HTTP"
  target_type = "instance"
  vpc_id      = local.vpc_id

  health_check {
    path                = "/api/health"
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
    path                = "/ping"
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
  target_type = "ip" # Fargate tasks register IPs
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

# ---------- Attach instances to TGs (ECS auto-registers mongo-express) ----------
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

# NOTE: no target_group_attachment for mongo_express; ECS service registers tasks.

# ---------- Listeners ----------
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.obs.arn
  port              = 443
  protocol          = "HTTPS"

  certificate_arn = aws_acm_certificate_validation.this.certificate_arn
  ssl_policy      = "ELBSecurityPolicy-TLS13-1-2-2021-06"

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

# ---------- Global logout endpoint ----------
# /logout -> logout ECS service (which then calls Cognito /logout and redirects back)
resource "aws_lb_listener_rule" "logout" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 5 # must be lower than 10 so it matches before grafana/prom/clickhouse/etc.

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.logout.arn
  }

  condition {
    path_pattern {
      values = ["/logout"]
    }
  }
}

# ---------- Host-based routing ----------
resource "aws_lb_listener_rule" "grafana_host" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  # Cognito SSO gate
  action {
    type = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn       = local.cognito_sso.user_pool_arn
      user_pool_client_id = local.cognito_sso.client_id
      user_pool_domain    = local.cognito_sso.user_pool_domain

      scope                      = "openid email"
      session_cookie_name        = "alb_auth"
      on_unauthenticated_request = "authenticate"
    }
  }

  # After auth, forward to Grafana
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
    type = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn       = local.cognito_sso.user_pool_arn
      user_pool_client_id = local.cognito_sso.client_id
      user_pool_domain    = local.cognito_sso.user_pool_domain

      scope                      = "openid email"
      session_cookie_name        = "alb_auth"
      on_unauthenticated_request = "authenticate"
    }
  }

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
    type = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn       = local.cognito_sso.user_pool_arn
      user_pool_client_id = local.cognito_sso.client_id
      user_pool_domain    = local.cognito_sso.user_pool_domain

      scope                      = "openid email"
      session_cookie_name        = "alb_auth"
      on_unauthenticated_request = "authenticate"
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.clickhouse.arn
  }

  condition {
    host_header { values = [local.clickhouse_host] }
  }
}

resource "aws_lb_listener_rule" "mongo_express" {
  count        = local.enable_mongo ? 1 : 0
  listener_arn = aws_lb_listener.https.arn
  priority     = 40

  action {
    type = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn       = local.cognito_sso.user_pool_arn
      user_pool_client_id = local.cognito_sso.client_id
      user_pool_domain    = local.cognito_sso.user_pool_domain

      scope                      = "openid email"
      session_cookie_name        = "alb_auth"
      on_unauthenticated_request = "authenticate"
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.mongo_express[0].arn
  }

  condition {
    host_header {
      values = [local.mongo_express] # defaults to "mongo.usekarma.dev"
    }
  }
}

resource "aws_lb_listener_rule" "redpanda_console" {
  count        = local.enable_redpanda ? 1 : 0
  listener_arn = aws_lb_listener.https.arn
  priority     = 277 # adjust to fit your rule set

  action {
    type = "authenticate-cognito"

    authenticate_cognito {
      user_pool_arn       = local.cognito_sso.user_pool_arn
      user_pool_client_id = local.cognito_sso.client_id
      user_pool_domain    = local.cognito_sso.user_pool_domain

      scope                      = "openid email"
      session_cookie_name        = "alb_auth"
      on_unauthenticated_request = "authenticate"
    }
  }

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.redpanda_console[0].arn
  }

  condition {
    host_header {
      values = [local.redpanda_console]
    }
  }

  tags = local.tags
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
  count   = local.enable_mongo ? 1 : 0
  zone_id = local.zone_id
  name    = local.mongo_express # "mongo.usekarma.dev"
  type    = "A"
  alias {
    name                   = aws_lb.obs.dns_name
    zone_id                = aws_lb.obs.zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "redpanda_console_record" {
  count   = local.enable_redpanda ? 1 : 0
  zone_id = local.zone_id
  name    = local.redpanda_console # defaults to "redpanda.usekarma.dev" or similar
  type    = "A"
  alias {
    name                   = aws_lb.obs.dns_name
    zone_id                = aws_lb.obs.zone_id
    evaluate_target_health = false
  }
}
