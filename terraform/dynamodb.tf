# Users 테이블 - Cognito sub <-> GitHub 계정 매핑
resource "aws_dynamodb_table" "users" {
  name           = "${var.project_name}-users"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "userId"

  attribute {
    name = "userId"
    type = "S"
  }

  tags = {
    Name = "${var.project_name}-users"
  }
}

# Deployments 테이블 - 배포 정보, 리소스 매핑, 로그 추적
resource "aws_dynamodb_table" "deployments" {
  name           = "${var.project_name}-deployments"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "deploymentId"

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
  name           = "${var.project_name}-services"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "serviceId"

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
