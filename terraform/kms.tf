# KMS Key for encrypting GitHub access tokens
resource "aws_kms_key" "github_tokens" {
  description             = "Encryption key for GitHub access tokens"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-github-tokens"
  }
}

resource "aws_kms_alias" "github_tokens" {
  name          = "alias/${var.project_name}-github-tokens"
  target_key_id = aws_kms_key.github_tokens.key_id
}

# KMS Key for encrypting environment variables for SSM Parameter Store
resource "aws_kms_key" "ssm_secure_string" {
  description             = "Encryption key for environment variables in SSM"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-ssm-secure-string"
  }
}

resource "aws_kms_alias" "ssm_secure_string" {
  name          = "alias/${var.project_name}-ssm-secure-string"
  target_key_id = aws_kms_key.ssm_secure_string.key_id
}
