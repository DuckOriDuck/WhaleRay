resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.users.arn,
          "${aws_dynamodb_table.users.arn}/index/*",
          aws_dynamodb_table.deployments.arn,
          "${aws_dynamodb_table.deployments.arn}/index/*",
          aws_dynamodb_table.services.arn,
          "${aws_dynamodb_table.services.arn}/index/*"
          ,
          # [ADDED] installations 테이블 접근 권한 추가
          aws_dynamodb_table.installations.arn,
          "${aws_dynamodb_table.installations.arn}/index/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:whaleray/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask",
          "ecs:DescribeTasks",
          "ecs:StopTask",
          "ecs:ListTasks"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.ecs_task_execution.arn,
          aws_iam_role.ecs_task.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:RegisterTaskDefinition",
          "ecs:DescribeServices",
          "ecs:CreateService",
          "ecs:UpdateService"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/codebuild/*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/ecs/*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "codebuild:StartBuild",
          "codebuild:BatchGetBuilds"
        ]
        Resource = "arn:aws:codebuild:*:*:project/${var.project_name}-*"
      },
      # [ADDED] repo_inspector 람다를 호출할 수 있는 권한 추가
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.repo_inspector.arn
      }
    ]
  })
}

# --- Lambda Layers ---

# PyJWT, cryptography, requests 등 외부 라이브러리를 포함하는 공통 레이어
resource "null_resource" "common_layer_dependencies" {
  triggers = {
    requirements_sha = filesha256("${path.module}/../lambda/layers/common_requirements.txt")
  }

  provisioner "local-exec" {
    command     = <<-EOT
      set -euo pipefail
      DEST="${path.module}/../build/layers/common/python"
      rm -rf "$DEST"
      mkdir -p "$DEST"
      python3 -m pip install \
        --platform manylinux2014_x86_64 \
        --implementation cp \
        --python-version 3.11 \
        --abi cp311 \
        --only-binary=:all: \
        -r "${path.module}/../lambda/layers/common_requirements.txt" \
        -t "$DEST" \
        --no-cache-dir
    EOT
    interpreter = ["/bin/bash", "-c"]
  }
}

locals {
  common_layer_zip_path = "${path.module}/../build/common_layer.zip"
}

resource "null_resource" "archive_common_layer" {
  depends_on = [null_resource.common_layer_dependencies]

  triggers = {
    # Re-create zip when dependencies change
    requirements_sha = filesha256("${path.module}/../lambda/layers/common_requirements.txt")
  }

  provisioner "local-exec" {
    command     = "python3 ${path.module}/../lambda/create_zip.py ${path.module}/../build/layers/common ${local.common_layer_zip_path}"
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "aws_lambda_layer_version" "common_libs_layer" {
  depends_on = [null_resource.archive_common_layer]

  layer_name          = "${var.project_name}-common-libs"
  description         = "Common Python libraries like PyJWT, requests, cryptography"
  filename            = local.common_layer_zip_path
  source_code_hash    = try(filebase64sha256(local.common_layer_zip_path), null)
  compatible_runtimes = ["python3.11"]
}

# github_utils.py와 같은 공유 코드를 포함하는 레이어
locals {
  github_utils_layer_zip_path = "${path.module}/../build/github_utils_layer.zip"
}

resource "null_resource" "archive_github_utils_layer" {
  triggers = {
    # Re-create when source files change
    source_hash = sha1(join("", [for f in fileset("${path.module}/../lambda/layers/github_utils", "**") : filesha1("${path.module}/../lambda/layers/github_utils/${f}")]))
  }

  provisioner "local-exec" {
    command     = "python3 ${path.module}/../lambda/create_zip.py ${path.module}/../lambda/layers/github_utils ${local.github_utils_layer_zip_path}"
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "aws_lambda_layer_version" "github_utils_layer" {
  depends_on = [null_resource.archive_github_utils_layer]

  layer_name          = "${var.project_name}-github-utils"
  description         = "Shared utility functions for GitHub interaction"
  filename            = local.github_utils_layer_zip_path
  source_code_hash    = try(filebase64sha256(local.github_utils_layer_zip_path), null)
  compatible_runtimes = ["python3.11"]
}

locals {
  deploy_lambda_zip_path = "${path.module}/../build/deploy.zip"
}

resource "null_resource" "archive_deploy_lambda" {
  depends_on = [null_resource.clean_lambda_pycache]

  triggers = {
    source_hash = sha1(join("", [for f in fileset("${path.module}/../lambda/deploy", "**") : filesha1("${path.module}/../lambda/deploy/${f}")]))
  }

  provisioner "local-exec" {
    command     = "python3 ${path.module}/../lambda/create_zip.py ${path.module}/../lambda/deploy ${local.deploy_lambda_zip_path}"
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "aws_lambda_function" "deploy" {
  depends_on    = [null_resource.archive_deploy_lambda]
  filename      = local.deploy_lambda_zip_path
  function_name = "${var.project_name}-deploy"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 300

  source_code_hash = try(filebase64sha256(local.deploy_lambda_zip_path), null)

  environment {
    variables = {
      FRONTEND_URL                 = "https://${var.domain_name}"
      REPO_INSPECTOR_FUNCTION_NAME = aws_lambda_function.repo_inspector.function_name
      INSTALLATIONS_TABLE          = aws_dynamodb_table.installations.name
      CLUSTER_NAME                 = aws_ecs_cluster.main.name
      DEPLOYMENTS_TABLE            = aws_dynamodb_table.deployments.name
      SERVICES_TABLE               = aws_dynamodb_table.services.name
      TASK_EXECUTION_ROLE          = aws_iam_role.ecs_task_execution.arn
      TASK_ROLE                    = aws_iam_role.ecs_task.arn
      SUBNETS                      = join(",", aws_subnet.private[*].id)
      SECURITY_GROUPS              = aws_security_group.ecs_tasks.id
      TARGET_GROUP_ARN             = aws_lb_target_group.default.arn
    }
  }
}

locals {
  deployments_api_lambda_zip_path = "${path.module}/../build/deployments_api.zip"
  service_lambda_zip_path         = "${path.module}/../build/service.zip"
}

resource "null_resource" "archive_deployments_api_lambda" {
  depends_on = [null_resource.clean_lambda_pycache]

  triggers = {
    source_hash = sha1(join("", [for f in fileset("${path.module}/../lambda/deployments_api", "**") : filesha1("${path.module}/../lambda/deployments_api/${f}")]))
  }

  provisioner "local-exec" {
    command     = "python3 ${path.module}/../lambda/create_zip.py ${path.module}/../lambda/deployments_api ${local.deployments_api_lambda_zip_path}"
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "null_resource" "archive_service_lambda" {
  depends_on = [null_resource.clean_lambda_pycache]

  triggers = {
    source_hash = sha1(join("", [for f in fileset("${path.module}/../lambda/service", "**") : filesha1("${path.module}/../lambda/service/${f}")]))
  }

  provisioner "local-exec" {
    command     = "python3 ${path.module}/../lambda/create_zip.py ${path.module}/../lambda/service ${local.service_lambda_zip_path}"
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "aws_lambda_function" "deployments_api" {
  depends_on    = [null_resource.archive_deployments_api_lambda]
  filename      = local.deployments_api_lambda_zip_path
  function_name = "${var.project_name}-deployments-api"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 30

  layers = [
    aws_lambda_layer_version.common_libs_layer.arn,
    aws_lambda_layer_version.github_utils_layer.arn
  ]

  source_code_hash = try(filebase64sha256(local.deployments_api_lambda_zip_path), null)

  environment {
    variables = {
      FRONTEND_URL      = "https://${var.domain_name}"
      DEPLOYMENTS_TABLE = aws_dynamodb_table.deployments.name
      SERVICES_TABLE    = aws_dynamodb_table.services.name
      USERS_TABLE       = aws_dynamodb_table.users.name
    }
  }
}

resource "aws_lambda_function" "service" {
  depends_on    = [null_resource.archive_service_lambda]
  filename      = local.service_lambda_zip_path
  function_name = "${var.project_name}-service"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 20

  layers = [
    aws_lambda_layer_version.common_libs_layer.arn,
    aws_lambda_layer_version.github_utils_layer.arn
  ]

  source_code_hash = try(filebase64sha256(local.service_lambda_zip_path), null)

  environment {
    variables = {
      SERVICES_TABLE    = aws_dynamodb_table.services.name
      DEPLOYMENTS_TABLE = aws_dynamodb_table.deployments.name
      FRONTEND_URL      = "https://${var.domain_name}"
    }
  }
}

# ECS Deployer Lambda
locals {
  ecs_deployer_lambda_zip_path = "${path.module}/../build/ecs_deployer.zip"
}

resource "null_resource" "archive_ecs_deployer_lambda" {
  depends_on = [null_resource.clean_lambda_pycache]

  triggers = {
    source_hash = sha1(join("", [for f in fileset("${path.module}/../lambda/ecs_deployer", "**") : filesha1("${path.module}/../lambda/ecs_deployer/${f}")]))
  }

  provisioner "local-exec" {
    command     = "python3 ${path.module}/../lambda/create_zip.py ${path.module}/../lambda/ecs_deployer ${local.ecs_deployer_lambda_zip_path}"
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "aws_lambda_function" "ecs_deployer" {
  depends_on    = [null_resource.archive_ecs_deployer_lambda]
  filename      = local.ecs_deployer_lambda_zip_path
  function_name = "${var.project_name}-ecs-deployer"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 300

  layers = [
    # 외부 라이브러리 (requests 등)
    aws_lambda_layer_version.common_libs_layer.arn,
    aws_lambda_layer_version.github_utils_layer.arn
  ]

  source_code_hash = try(filebase64sha256(local.ecs_deployer_lambda_zip_path), null)

  environment {
    variables = {
      CLUSTER_NAME        = aws_ecs_cluster.main.name
      DEPLOYMENTS_TABLE   = aws_dynamodb_table.deployments.name
      SERVICES_TABLE      = aws_dynamodb_table.services.name
      USERS_TABLE         = aws_dynamodb_table.users.name
      TASK_EXECUTION_ROLE = aws_iam_role.ecs_task_execution.arn
      TASK_ROLE           = aws_iam_role.ecs_task.arn
      TARGET_GROUP_ARN    = aws_lb_target_group.default.arn
      ECR_REPOSITORY_URL  = aws_ecr_repository.app_repo.repository_url
      FRONTEND_URL        = "https://${var.domain_name}"
    }
  }
}

# Logs API Lambda
locals {
  logs_api_lambda_zip_path = "${path.module}/../build/logs_api.zip"
}

resource "null_resource" "archive_logs_api_lambda" {
  depends_on = [null_resource.clean_lambda_pycache]

  triggers = {
    source_hash = sha1(join("", [for f in fileset("${path.module}/../lambda/logs_api", "**") : filesha1("${path.module}/../lambda/logs_api/${f}")]))
  }

  provisioner "local-exec" {
    command     = "python3 ${path.module}/../lambda/create_zip.py ${path.module}/../lambda/logs_api ${local.logs_api_lambda_zip_path}"
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "aws_lambda_function" "logs_api" {
  depends_on    = [null_resource.archive_logs_api_lambda]
  filename      = local.logs_api_lambda_zip_path
  function_name = "${var.project_name}-logs-api"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 30

  source_code_hash = try(filebase64sha256(local.logs_api_lambda_zip_path), null)

  environment {
    variables = {
      DEPLOYMENTS_TABLE = aws_dynamodb_table.deployments.name
      USERS_TABLE       = aws_dynamodb_table.users.name
    }
  }
}

# --- Repo Inspector Lambda ---

locals {
  repo_inspector_lambda_zip_path = "${path.module}/../build/repo_inspector.zip"
}

resource "null_resource" "archive_repo_inspector_lambda" {
  depends_on = [null_resource.clean_lambda_pycache]

  triggers = {
    source_hash = sha1(join("", [for f in fileset("${path.module}/../lambda/repo_inspector", "**") : filesha1("${path.module}/../lambda/repo_inspector/${f}")]))
  }

  provisioner "local-exec" {
    command     = "python3 ${path.module}/../lambda/create_zip.py ${path.module}/../lambda/repo_inspector ${local.repo_inspector_lambda_zip_path}"
    interpreter = ["/bin/bash", "-c"]
  }
}

resource "aws_lambda_function" "repo_inspector" {
  depends_on    = [null_resource.archive_repo_inspector_lambda]
  filename      = local.repo_inspector_lambda_zip_path
  function_name = "${var.project_name}-repo-inspector"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 300

  layers = [
    aws_lambda_layer_version.common_libs_layer.arn,
    aws_lambda_layer_version.github_utils_layer.arn
  ]

  source_code_hash = try(filebase64sha256(local.repo_inspector_lambda_zip_path), null)

  environment {
    variables = {
      DEPLOYMENTS_TABLE          = aws_dynamodb_table.deployments.name
      USERS_TABLE                = aws_dynamodb_table.users.name
      ECR_REPOSITORY_URL         = aws_ecr_repository.app_repo.repository_url
      PROJECT_NAME               = var.project_name
      GITHUB_APP_PRIVATE_KEY_ARN = aws_secretsmanager_secret.github_app_private_key.arn
      GITHUB_APP_ID              = var.github_app_id
    }
  }
}