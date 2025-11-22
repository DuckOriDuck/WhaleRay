# Secrets Manager for JWT signing secret
resource "aws_secretsmanager_secret" "jwt_secret" {
  name = "${var.project_name}/jwt-secret-v3"

  tags = {
    Name = "${var.project_name}-jwt-secret"
  }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = random_password.jwt_secret.result
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

# GitHub OAuth App credentials
resource "aws_secretsmanager_secret" "github_oauth" {
  name = "${var.project_name}/github-oauth"

  tags = {
    Name = "${var.project_name}-github-oauth"
  }
}

resource "aws_secretsmanager_secret_version" "github_oauth" {
  secret_id = aws_secretsmanager_secret.github_oauth.id
  secret_string = jsonencode({
    client_id     = var.github_client_id
    client_secret = var.github_client_secret
  })
}

# GitHub App Private Key
resource "aws_secretsmanager_secret" "github_app_private_key" {
  name = "${var.project_name}/github-app-private-key"

  tags = {
    Name = "${var.project_name}-github-app-private-key"
  }
}

resource "aws_secretsmanager_secret_version" "github_app_private_key" {
  secret_id     = aws_secretsmanager_secret.github_app_private_key.id
  secret_string = var.github_app_private_key
}