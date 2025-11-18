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
      }
    ]
  })
}

data "archive_file" "deploy_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/deploy"
  output_path = "${path.module}/.terraform/lambda-deploy.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "deploy" {
  filename      = data.archive_file.deploy_lambda.output_path
  function_name = "${var.project_name}-deploy"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 300

  source_code_hash = data.archive_file.deploy_lambda.output_base64sha256

  environment {
    variables = {
      CLUSTER_NAME        = aws_ecs_cluster.main.name
      DEPLOYMENTS_TABLE   = aws_dynamodb_table.deployments.name
      SERVICES_TABLE      = aws_dynamodb_table.services.name
      TASK_EXECUTION_ROLE = aws_iam_role.ecs_task_execution.arn
      TASK_ROLE           = aws_iam_role.ecs_task.arn
      SUBNETS             = join(",", aws_subnet.private[*].id)
      SECURITY_GROUPS     = aws_security_group.ecs_tasks.id
      TARGET_GROUP_ARN    = aws_lb_target_group.default.arn
    }
  }
}

data "archive_file" "manage_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/manage"
  output_path = "${path.module}/.terraform/lambda-manage.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "manage" {
  filename      = data.archive_file.manage_lambda.output_path
  function_name = "${var.project_name}-manage"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 30

  source_code_hash = data.archive_file.manage_lambda.output_base64sha256

  environment {
    variables = {
      DEPLOYMENTS_TABLE = aws_dynamodb_table.deployments.name
      SERVICES_TABLE    = aws_dynamodb_table.services.name
      USERS_TABLE       = aws_dynamodb_table.users.name
    }
  }
}

# ECS Deployer Lambda
data "archive_file" "ecs_deployer_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/ecs_deployer"
  output_path = "${path.module}/.terraform/lambda-ecs-deployer.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "ecs_deployer" {
  filename      = data.archive_file.ecs_deployer_lambda.output_path
  function_name = "${var.project_name}-ecs-deployer"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 300

  source_code_hash = data.archive_file.ecs_deployer_lambda.output_base64sha256

  environment {
    variables = {
      CLUSTER_NAME        = aws_ecs_cluster.main.name
      DEPLOYMENTS_TABLE   = aws_dynamodb_table.deployments.name
      USERS_TABLE         = aws_dynamodb_table.users.name
      TASK_EXECUTION_ROLE = aws_iam_role.ecs_task_execution.arn
      TASK_ROLE           = aws_iam_role.ecs_task.arn
      TARGET_GROUP_ARN    = aws_lb_target_group.default.arn
      ECR_REPOSITORY_URL  = aws_ecr_repository.app_repo.repository_url
    }
  }
}

# Logs API Lambda
data "archive_file" "logs_api_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/logs_api"
  output_path = "${path.module}/.terraform/lambda-logs-api.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "logs_api" {
  filename      = data.archive_file.logs_api_lambda.output_path
  function_name = "${var.project_name}-logs-api"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 30

  source_code_hash = data.archive_file.logs_api_lambda.output_base64sha256

  environment {
    variables = {
      DEPLOYMENTS_TABLE = aws_dynamodb_table.deployments.name
      USERS_TABLE       = aws_dynamodb_table.users.name
    }
  }
}

# Repo Inspector Lambda (선택사항 - GitHub 연동 시 사용)
data "archive_file" "repo_inspector_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/repo_inspector"
  output_path = "${path.module}/.terraform/lambda-repo-inspector.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "*.egg-info"]
}

resource "aws_lambda_function" "repo_inspector" {
  filename      = data.archive_file.repo_inspector_lambda.output_path
  function_name = "${var.project_name}-repo-inspector"
  role          = aws_iam_role.lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.11"
  timeout       = 300

  source_code_hash = data.archive_file.repo_inspector_lambda.output_base64sha256

  environment {
    variables = {
      DEPLOYMENTS_TABLE   = aws_dynamodb_table.deployments.name
      USERS_TABLE         = aws_dynamodb_table.users.name
      ECR_REPOSITORY_URL  = aws_ecr_repository.app_repo.repository_url
      PROJECT_NAME        = var.project_name
    }
  }
}
