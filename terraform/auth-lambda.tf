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
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.users.arn,
          aws_dynamodb_table.oauth_states.arn,
          aws_dynamodb_table.installations.arn,
          "${aws_dynamodb_table.users.arn}/index/*",
          "${aws_dynamodb_table.installations.arn}/index/*"
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
        Resource = [
          aws_secretsmanager_secret.jwt_secret.arn,
          aws_secretsmanager_secret.github_app_private_key.arn
        ]
      }
    ]
  })
}

# Lambda 패키징 전 cleanup (전체 lambda 폴더 - 크로스 플랫폼 지원)
# 이 resource는 모든 Lambda 패키징에서 공통으로 사용됩니다
resource "null_resource" "clean_lambda_pycache" {
  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    command     = "python3 ../lambda/clean_pycache.py"
    working_dir = path.module
  }
}

resource "null_resource" "auth_lambda_dependencies" {
  # Re-run when requirements change
  triggers = {
    requirements_sha = filesha256("${path.module}/../lambda/auth/requirements.txt")
    always_run       = timestamp()
  }

  provisioner "local-exec" {
    # venv-free install of auth lambda deps into build/auth_package
    command     = <<EOT
set -euo pipefail
WORKDIR="${path.module}"
SRC="$WORKDIR/../lambda/auth"
DEST="$WORKDIR/../build/auth_package"

rm -rf "$DEST"
mkdir -p "$DEST"

# copy source
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' --exclude '*.egg-info' --exclude 'tests' "$SRC/" "$DEST/"

# install dependencies targeting Lambda runtime (python3.11 manylinux2014)
python3 -m pip install \
  --no-compile \
  --no-cache-dir \
  --only-binary=":all:" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --abi cp311 \
  -r "$SRC/requirements.txt" \
  -t "$DEST"

# cleanup pycache from deps
find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$DEST" -name '*.pyc' -delete
EOT
    interpreter = ["/bin/bash", "-c"]
    working_dir = path.module
  }
}

# Lambda 패키징
data "archive_file" "auth_lambda" {
  depends_on = [
    null_resource.clean_lambda_pycache,
    null_resource.auth_lambda_dependencies
  ]
  type        = "zip"
  source_dir  = "${path.module}/../build/auth_package"
  output_path = "${path.module}/../build/auth.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "*.egg-info", "tests"]
}

# GitHub OAuth Authorize Lambda
resource "aws_lambda_function" "auth_github_authorize" {
  filename      = data.archive_file.auth_lambda.output_path
  function_name = "${var.project_name}-auth-github-authorize"
  role          = aws_iam_role.lambda_auth.arn
  handler       = "authorize.handler"
  runtime       = "python3.11"
  timeout       = 30

  environment {
    variables = {
      OAUTH_STATES_TABLE  = aws_dynamodb_table.oauth_states.name
      GITHUB_APP_SLUG     = var.github_app_slug
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
  filename      = data.archive_file.auth_lambda.output_path
  function_name = "${var.project_name}-auth-github-callback"
  role          = aws_iam_role.lambda_auth.arn
  handler       = "callback.handler"
  runtime       = "python3.11"
  timeout       = 30

  environment {
    variables = {
      OAUTH_STATES_TABLE   = aws_dynamodb_table.oauth_states.name
      USERS_TABLE          = aws_dynamodb_table.users.name
      INSTALLATIONS_TABLE  = aws_dynamodb_table.installations.name
      GITHUB_CLIENT_ID     = var.github_client_id
      GITHUB_CLIENT_SECRET = var.github_client_secret
      GITHUB_CALLBACK_URL  = "https://api.${var.domain_name}/auth/github/callback"
      FRONTEND_URL         = "https://${var.domain_name}"
      GITHUB_APP_ID        = var.github_app_id
      JWT_SECRET_ARN       = aws_secretsmanager_secret.jwt_secret.arn
      KMS_KEY_ID           = aws_kms_key.github_tokens.id
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256

  tags = {
    Name = "${var.project_name}-auth-github-callback"
  }
}

resource "aws_lambda_function" "auth_github_install_status" {
  filename      = data.archive_file.auth_lambda.output_path
  function_name = "${var.project_name}-auth-github-install-status"
  role          = aws_iam_role.lambda_auth.arn
  handler       = "installation.check_installation"
  runtime       = "python3.11"
  timeout       = 20

  environment {
    variables = {
      USERS_TABLE     = aws_dynamodb_table.users.name
      KMS_KEY_ID      = aws_kms_key.github_tokens.id
      GITHUB_APP_SLUG = var.github_app_slug
      GITHUB_APP_ID   = var.github_app_id
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256

  tags = {
    Name = "${var.project_name}-auth-github-install-status"
  }
}

resource "aws_lambda_function" "auth_github_install_redirect" {
  filename      = data.archive_file.auth_lambda.output_path
  function_name = "${var.project_name}-auth-github-install-redirect"
  role          = aws_iam_role.lambda_auth.arn
  handler       = "installation.redirect_to_install"
  runtime       = "python3.11"
  timeout       = 10

  environment {
    variables = {
      GITHUB_APP_SLUG = var.github_app_slug
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256

  tags = {
    Name = "${var.project_name}-auth-github-install-redirect"
  }
}

# Lambda Authorizer (JWT 검증)
resource "aws_lambda_function" "auth_verify" {
  filename      = data.archive_file.auth_lambda.output_path
  function_name = "${var.project_name}-auth-verify"
  role          = aws_iam_role.lambda_auth.arn
  handler       = "verify.handler"
  runtime       = "python3.11"
  timeout       = 10

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

resource "aws_lambda_permission" "auth_github_install_status_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_github_install_status.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "auth_github_install_redirect_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_github_install_redirect.function_name
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

# GET /me Lambda
resource "aws_lambda_function" "auth_me" {
  filename      = data.archive_file.auth_lambda.output_path
  function_name = "${var.project_name}-auth-me"
  role          = aws_iam_role.lambda_auth.arn
  handler       = "me.handler"
  runtime       = "python3.11"
  timeout       = 20

  environment {
    variables = {
      INSTALLATIONS_TABLE = aws_dynamodb_table.installations.name
      GITHUB_APP_SLUG     = var.github_app_slug
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256

  tags = {
    Name = "${var.project_name}-auth-me"
  }
}

resource "aws_lambda_permission" "auth_me_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_me.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# GET /github/repositories Lambda
resource "aws_lambda_function" "github_repositories" {
  filename      = data.archive_file.auth_lambda.output_path
  function_name = "${var.project_name}-github-repositories"
  role          = aws_iam_role.lambda_auth.arn
  handler       = "repositories.handler"
  runtime       = "python3.11"
  timeout       = 30

  environment {
    variables = {
      INSTALLATIONS_TABLE        = aws_dynamodb_table.installations.name
      GITHUB_APP_ID              = var.github_app_id
      GITHUB_APP_PRIVATE_KEY_ARN = aws_secretsmanager_secret.github_app_private_key.arn
      USERS_TABLE                = aws_dynamodb_table.users.name
      KMS_KEY_ID                 = aws_kms_key.github_tokens.id
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256

  tags = {
    Name = "${var.project_name}-github-repositories"
  }
}

resource "aws_lambda_permission" "github_repositories_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.github_repositories.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}
