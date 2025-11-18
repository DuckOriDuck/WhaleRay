# Users 테이블 - GitHub 사용자 정보 및 토큰 저장
resource "aws_dynamodb_table" "users" {
  name         = "${var.project_name}-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userId"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "githubUsername"
    type = "S"
  }

  # GSI: GitHub 사용자명으로 검색
  global_secondary_index {
    name            = "GithubUsernameIndex"
    hash_key        = "githubUsername"
    projection_type = "ALL"
  }

  tags = {
    Name = "${var.project_name}-users"
  }
}

# OAuth States 테이블 - CSRF 방지용 state 저장
resource "aws_dynamodb_table" "oauth_states" {
  name         = "${var.project_name}-oauth-states"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "state"

  attribute {
    name = "state"
    type = "S"
  }

  # TTL 설정 (10분 후 자동 삭제)
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-oauth-states"
  }
}

# Deployments 테이블 - 배포 정보, 리소스 매핑, 로그 추적
resource "aws_dynamodb_table" "deployments" {
  name         = "${var.project_name}-deployments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "deploymentId"

  attribute {
    name = "deploymentId"
    type = "S"
  }

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "createdAt"
    type = "N"
  }

  global_secondary_index {
    name            = "userId-index"
    hash_key        = "userId"
    range_key       = "createdAt"
    projection_type = "ALL"
  }

  tags = {
    Name = "${var.project_name}-deployments"
  }
}

resource "aws_dynamodb_table" "services" {
  name         = "${var.project_name}-services"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "serviceId"

  attribute {
    name = "serviceId"
    type = "S"
  }

  attribute {
    name = "userId"
    type = "S"
  }

  global_secondary_index {
    name            = "userId-index"
    hash_key        = "userId"
    projection_type = "ALL"
  }

  tags = {
    Name = "${var.project_name}-services"
  }
}
