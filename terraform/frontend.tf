# S3 버킷 for 프론트엔드 호스팅
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${var.project_name}-frontend"
  }
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"  # SPA 라우팅을 위해
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.frontend.arn}/*"
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

# CloudFront Distribution with Custom Domain
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"  # 북미, 유럽만
  aliases             = [var.domain_name]

  origin {
    domain_name = aws_s3_bucket_website_configuration.frontend.website_endpoint
    origin_id   = "S3-${aws_s3_bucket.frontend.id}"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "S3-${aws_s3_bucket.frontend.id}"
    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # SPA 라우팅을 위한 에러 페이지 처리
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.acm_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = {
    Name = "${var.project_name}-frontend"
  }
}

# 프론트엔드 빌드 및 배포를 위한 null_resource
# Windows 환경에서는 수동 배포를 권장합니다
# terraform apply 후 아래 명령어로 수동 배포:
# 1. cd frontend
# 2. terraform output로 값 확인 후 src/config.js 수정
# 3. npm install && npm run build
# 4. aws s3 sync dist/ s3://버킷이름/ --delete
# 5. aws cloudfront create-invalidation --distribution-id 배포ID --paths "/*"

# resource "null_resource" "frontend_build_deploy" {
#   triggers = {
#     api_endpoint      = aws_apigatewayv2_api.main.api_endpoint
#     cognito_pool_id   = aws_cognito_user_pool.main.id
#     cognito_client_id = aws_cognito_user_pool_client.web.id
#   }
#
#   provisioner "local-exec" {
#     working_dir = "${path.module}/../frontend"
#
#     command = <<-EOT
#       cat > src/config.js <<EOF
# export const config = {
#   region: '${var.aws_region}',
#   cognito: {
#     userPoolId: '${aws_cognito_user_pool.main.id}',
#     userPoolClientId: '${aws_cognito_user_pool_client.web.id}',
#     domain: '${aws_cognito_user_pool_domain.main.domain}'
#   },
#   apiEndpoint: '${aws_apigatewayv2_api.main.api_endpoint}',
#   ecrRepositoryUrl: '${aws_ecr_repository.app_repo.repository_url}',
#   albDns: '${aws_lb.main.dns_name}'
# }
# EOF
#       npm install
#       npm run build
#       aws s3 sync dist/ s3://${aws_s3_bucket.frontend.bucket}/ --delete
#       aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.frontend.id} --paths "/*"
#     EOT
#
#     interpreter = ["bash", "-c"]
#   }
#
#   depends_on = [
#     aws_s3_bucket.frontend,
#     aws_cloudfront_distribution.frontend,
#     aws_apigatewayv2_api.main,
#     aws_cognito_user_pool.main,
#     aws_cognito_user_pool_client.web
#   ]
# }
