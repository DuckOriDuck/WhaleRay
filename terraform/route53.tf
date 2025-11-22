# Route53 Hosted Zone (이미 존재한다고 가정)
data "aws_route53_zone" "main" {
  name         = var.domain_name
  private_zone = false
}

# us-east-1 provider for ACM certificate lookup (CloudFront requires us-east-1)
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "WhaleRay"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Route53 Record for Frontend (CloudFront)
resource "aws_route53_record" "frontend" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }
}

# Route53 Record for API subdomain (API Gateway)
resource "aws_route53_record" "api" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].target_domain_name
    zone_id                = aws_apigatewayv2_domain_name.api.domain_name_configuration[0].hosted_zone_id
    evaluate_target_health = false
  }
}

# ============================================================================
# ACM Certificate for API Gateway
# ============================================================================
resource "aws_acm_certificate" "api_gateway" {
  domain_name       = "api.${var.domain_name}"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.project_name}-api-gateway-cert"
  }
}

resource "aws_route53_record" "api_gateway_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.api_gateway.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main.zone_id
}

resource "aws_acm_certificate_validation" "api_gateway" {
  certificate_arn         = aws_acm_certificate.api_gateway.arn
  validation_record_fqdns = [for record in aws_route53_record.api_gateway_cert_validation : record.fqdn]
}

# ============================================================================
# ACM Certificate for ALB
# ============================================================================
# ACM Certificate for ALB (ap-northeast-2)
resource "aws_acm_certificate" "alb" {
  domain_name       = "${var.service_domain_prefix}.${var.domain_name}"
  validation_method = "DNS"

  subject_alternative_names = [
    "${var.service_domain_prefix}.${var.domain_name}"
    "*.${var.service_domain_prefix}.${var.domain_name}",
    "${var.db_domain_prefix}.${var.domain_name}",
    "*.${var.db_domain_prefix}.${var.domain_name}"
  ]

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.project_name}-alb-cert"
  }
}

# ACM Certificate Validation DNS Records for ALB
resource "aws_route53_record" "alb_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.alb.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.aws_route53_zone.main.zone_id
}

# Wait for ALB certificate validation
resource "aws_acm_certificate_validation" "alb" {
  certificate_arn         = aws_acm_certificate.alb.arn
  validation_record_fqdns = [for record in aws_route53_record.alb_cert_validation : record.fqdn]
}

# Route53 Record for Service subdomain (ALB)
resource "aws_route53_record" "service" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "${var.service_domain_prefix}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
# DB Subdomain Record
resource "aws_route53_record" "db" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "${var.db_domain_prefix}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
