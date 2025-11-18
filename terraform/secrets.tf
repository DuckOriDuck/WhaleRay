# Data source for existing JWT secret in Secrets Manager
data "aws_secretsmanager_secret" "jwt_secret" {
  name = "${var.project_name}/jwt-secret-v2"
}

data "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id = data.aws_secretsmanager_secret.jwt_secret.id
}
