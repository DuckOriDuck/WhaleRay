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
