resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = false
  }

  tags = {
    Name = "${var.project_name}-users"
  }
}

resource "aws_cognito_identity_provider" "github" {
  user_pool_id  = aws_cognito_user_pool.main.id
  provider_name = "GitHub"
  provider_type = "OIDC"

  provider_details = {
    authorize_scopes              = "read:user user:email"
    attributes_request_method     = "GET"
    oidc_issuer                   = "https://github.com"
    authorize_url                 = "https://github.com/login/oauth/authorize"
    token_url                     = "https://github.com/login/oauth/access_token"
    attributes_url                = "https://api.github.com/user"
    client_id                     = var.github_client_id
    client_secret                 = var.github_client_secret
    attributes_url_add_attributes = "true"
  }

  attribute_mapping = {
    email    = "email"
    name     = "name"
    preferred_username = "login"
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.project_name}-web-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH"
  ]

  # OAuth 2.0 settings for Hosted UI
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]

  # Callback URLs
  callback_urls = [
    "http://localhost:3000",
    "http://localhost:3000/callback",
    "http://localhost:5173",
    "http://localhost:5173/callback",
    "https://${var.domain_name}",
    "https://${var.domain_name}/",
    "https://${var.domain_name}/callback"
  ]

  logout_urls = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://${var.domain_name}",
    "https://${var.domain_name}/"
  ]

  # Enable Cognito native login + GitHub
  supported_identity_providers = [
    "COGNITO",
    aws_cognito_identity_provider.github.provider_name
  ]

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-${var.environment}"
  user_pool_id = aws_cognito_user_pool.main.id
}
