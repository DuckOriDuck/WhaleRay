resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
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

# Lambda Authorizer (JWT 검증)
resource "aws_apigatewayv2_authorizer" "lambda_jwt" {
  api_id                            = aws_apigatewayv2_api.main.id
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.auth_verify.invoke_arn
  name                              = "lambda-jwt-authorizer"
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = false
  identity_sources                  = ["$request.header.Authorization"]
  authorizer_result_ttl_in_seconds  = 300  # 5분 캐싱
}

# ============================================================================
# Auth Routes (GitHub OAuth)
# ============================================================================

# GitHub OAuth Authorize Integration
resource "aws_apigatewayv2_integration" "auth_github_authorize" {
  api_id             = aws_apigatewayv2_api.main.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.auth_github_authorize.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "auth_github_authorize" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /auth/github/authorize"
  target    = "integrations/${aws_apigatewayv2_integration.auth_github_authorize.id}"
  # No authorization - public endpoint
}

# GitHub OAuth Callback Integration
resource "aws_apigatewayv2_integration" "auth_github_callback" {
  api_id             = aws_apigatewayv2_api.main.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.auth_github_callback.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "auth_github_callback" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /auth/github/callback"
  target    = "integrations/${aws_apigatewayv2_integration.auth_github_callback.id}"
  # No authorization - GitHub redirect endpoint
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

resource "aws_lambda_permission" "manage_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.manage.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "deploy" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.deploy.invoke_arn
}

resource "aws_apigatewayv2_integration" "manage" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.manage.invoke_arn
}

resource "aws_apigatewayv2_route" "deploy" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /deploy"
  target             = "integrations/${aws_apigatewayv2_integration.deploy.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id
}

resource "aws_apigatewayv2_route" "services_list" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /services"
  target             = "integrations/${aws_apigatewayv2_integration.manage.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id
}

resource "aws_apigatewayv2_route" "services_get" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /services/{serviceId}"
  target             = "integrations/${aws_apigatewayv2_integration.manage.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id
}

resource "aws_apigatewayv2_route" "deployments_list" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /deployments"
  target             = "integrations/${aws_apigatewayv2_integration.manage.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id
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
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.logs_api.invoke_arn
}

resource "aws_apigatewayv2_route" "deployment_logs" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "GET /deployments/{deploymentId}/logs"
  target             = "integrations/${aws_apigatewayv2_integration.logs_api.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id
}
