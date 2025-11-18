# IAM Role for Auth Lambda functions
resource "aws_iam_role" "lambda_auth" {
  name = "${var.project_name}-lambda-auth-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-lambda-auth-role"
  }
}

# IAM Policy for Auth Lambda functions
resource "aws_iam_role_policy" "lambda_auth" {
  name = "${var.project_name}-lambda-auth-policy"
  role = aws_iam_role.lambda_auth.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.users.arn,
          aws_dynamodb_table.oauth_states.arn,
          "${aws_dynamodb_table.users.arn}/index/*"
        ]
      },
      # KMS
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.github_tokens.arn
      },
      # Secrets Manager
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.jwt_secret.arn
      }
    ]
  })
}

# Lambda 패키징
data "archive_file" "auth_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/auth"
  output_path = "${path.module}/../build/auth.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "*.egg-info", "tests"]
}

# GitHub OAuth Authorize Lambda
resource "aws_lambda_function" "auth_github_authorize" {
  filename         = data.archive_file.auth_lambda.output_path
  function_name    = "${var.project_name}-auth-github-authorize"
  role            = aws_iam_role.lambda_auth.arn
  handler         = "authorize.handler"
  runtime         = "python3.11"
  timeout         = 30

  environment {
    variables = {
      OAUTH_STATES_TABLE  = aws_dynamodb_table.oauth_states.name
      GITHUB_CLIENT_ID    = var.github_client_id
      GITHUB_CALLBACK_URL = "https://api.${var.domain_name}/auth/github/callback"
      FRONTEND_URL        = "https://${var.domain_name}"
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256

  tags = {
    Name = "${var.project_name}-auth-github-authorize"
  }
}

# GitHub OAuth Callback Lambda
resource "aws_lambda_function" "auth_github_callback" {
  filename         = data.archive_file.auth_lambda.output_path
  function_name    = "${var.project_name}-auth-github-callback"
  role            = aws_iam_role.lambda_auth.arn
  handler         = "callback.handler"
  runtime         = "python3.11"
  timeout         = 30

  environment {
    variables = {
      OAUTH_STATES_TABLE   = aws_dynamodb_table.oauth_states.name
      USERS_TABLE          = aws_dynamodb_table.users.name
      GITHUB_CLIENT_ID     = var.github_client_id
      GITHUB_CLIENT_SECRET = var.github_client_secret
      GITHUB_CALLBACK_URL  = "https://api.${var.domain_name}/auth/github/callback"
      FRONTEND_URL         = "https://${var.domain_name}"
      KMS_KEY_ID          = aws_kms_key.github_tokens.id
      JWT_SECRET_ARN      = aws_secretsmanager_secret.jwt_secret.arn
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256

  tags = {
    Name = "${var.project_name}-auth-github-callback"
  }
}

# Lambda Authorizer (JWT 검증)
resource "aws_lambda_function" "auth_verify" {
  filename         = data.archive_file.auth_lambda.output_path
  function_name    = "${var.project_name}-auth-verify"
  role            = aws_iam_role.lambda_auth.arn
  handler         = "verify.handler"
  runtime         = "python3.11"
  timeout         = 10

  environment {
    variables = {
      JWT_SECRET_ARN = aws_secretsmanager_secret.jwt_secret.arn
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256

  tags = {
    Name = "${var.project_name}-auth-verify"
  }
}

# Lambda 권한 - API Gateway가 호출할 수 있도록
resource "aws_lambda_permission" "auth_github_authorize_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_github_authorize.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "auth_github_callback_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_github_callback.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "auth_verify_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_verify.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
