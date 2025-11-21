resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["https://${var.domain_name}", "http://localhost:3000"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["*"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "main" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true
}

# API Gateway Custom Domain
resource "aws_apigatewayv2_domain_name" "api" {
  domain_name = "api.${var.domain_name}"

  domain_name_configuration {
    certificate_arn = aws_acm_certificate.alb.arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  depends_on = [aws_acm_certificate_validation.alb]
}

# API Mapping
resource "aws_apigatewayv2_api_mapping" "api" {
  api_id      = aws_apigatewayv2_api.main.id
  domain_name = aws_apigatewayv2_domain_name.api.id
  stage       = aws_apigatewayv2_stage.main.id
}

# Lambda Authorizer (JWT 검증)
resource "aws_apigatewayv2_authorizer" "lambda_jwt" {
  api_id                            = aws_apigatewayv2_api.main.id
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.auth_verify.invoke_arn
  name                              = "lambda-jwt-authorizer"
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = false
  identity_sources                  = ["$request.header.Authorization"]
  # 0으로 두어 실패 캐시로 인한 오동작을 방지
  authorizer_result_ttl_in_seconds = 0
}

# ============================================================================
# Auth Routes (GitHub OAuth)
# ============================================================================

# GitHub OAuth Authorize Integration
resource "aws_apigatewayv2_integration" "auth_github_authorize" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.auth_github_authorize.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_route" "auth_github_start" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /auth/github/start"
  target    = "integrations/${aws_apigatewayv2_integration.auth_github_authorize.id}"
  # No authorization - public endpoint

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.auth_github_authorize.id]
  }
}

# GitHub OAuth Callback Integration
resource "aws_apigatewayv2_integration" "auth_github_callback" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.auth_github_callback.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_route" "auth_github_callback" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /auth/github/callback"
  target    = "integrations/${aws_apigatewayv2_integration.auth_github_callback.id}"
  # No authorization - GitHub redirect endpoint

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.auth_github_callback.id]
  }
}

resource "aws_apigatewayv2_integration" "auth_github_install_status" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.auth_github_install_status.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_route" "auth_github_install_status" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /auth/github/installations"
  target             = "integrations/${aws_apigatewayv2_integration.auth_github_install_status.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.auth_github_install_status.id]
  }
}

resource "aws_apigatewayv2_integration" "auth_github_install_redirect" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.auth_github_install_redirect.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_route" "auth_github_install_redirect" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /auth/github/install"
  target             = "integrations/${aws_apigatewayv2_integration.auth_github_install_redirect.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.auth_github_install_redirect.id]
  }
}

# ============================================================================
# Deploy & Manage Routes
# ============================================================================

resource "aws_lambda_permission" "deploy_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.deploy.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "deployments_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.deployments_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "service_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.service.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "deploy" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.deploy.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_integration" "deployments_api" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.deployments_api.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_integration" "service" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.service.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_route" "deploy" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /deploy"
  target             = "integrations/${aws_apigatewayv2_integration.deploy.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.deploy.id]
  }
}

resource "aws_apigatewayv2_route" "services_list" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /services"
  target             = "integrations/${aws_apigatewayv2_integration.service.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.service.id]
  }
}

resource "aws_apigatewayv2_route" "services_get" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /services/{serviceId}"
  target             = "integrations/${aws_apigatewayv2_integration.service.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.service.id]
  }
}

resource "aws_apigatewayv2_route" "deployments_list" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /deployments"
  target             = "integrations/${aws_apigatewayv2_integration.deployments_api.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.deployments_api.id]
  }
}

resource "aws_apigatewayv2_route" "deployments_create" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /deployments"
  target             = "integrations/${aws_apigatewayv2_integration.deploy.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.deploy.id]
  }
}

# Logs API Integration
resource "aws_lambda_permission" "logs_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.logs_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "logs_api" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.logs_api.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_route" "deployment_logs" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /deployments/{deploymentId}/logs"
  target             = "integrations/${aws_apigatewayv2_integration.logs_api.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.logs_api.id]
  }
}

# GET /me Integration
resource "aws_apigatewayv2_integration" "auth_me" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.auth_me.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_route" "auth_me" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /me"
  target             = "integrations/${aws_apigatewayv2_integration.auth_me.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.auth_me.id]
  }
}

# GET /github/repositories Integration
resource "aws_apigatewayv2_integration" "github_repositories" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.github_repositories.invoke_arn
  payload_format_version = "2.0"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_apigatewayv2_route" "github_repositories" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /github/repositories"
  target             = "integrations/${aws_apigatewayv2_integration.github_repositories.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_apigatewayv2_integration.github_repositories.id]
  }
}
