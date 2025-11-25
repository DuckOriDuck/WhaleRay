# CodeBuild용 IAM Role
resource "aws_iam_role" "codebuild" {
  name = "${var.project_name}-codebuild-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "codebuild.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "codebuild" {
  name = "${var.project_name}-codebuild-policy"
  role = aws_iam_role.codebuild.id

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
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.codebuild_cache.arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:whaleray/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ],
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/*"
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ],
        Resource = aws_kms_key.ssm_secure_string.arn
      }
    ]
  })
}

# CodeBuild 캐시용 S3 버킷
resource "aws_s3_bucket" "codebuild_cache" {
  bucket = "${var.project_name}-codebuild-cache-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name = "${var.project_name}-codebuild-cache"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "codebuild_cache" {
  bucket = aws_s3_bucket.codebuild_cache.id

  rule {
    id     = "delete-old-cache"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = 7
    }
  }
}

# Spring Boot CodeBuild 프로젝트
resource "aws_codebuild_project" "spring_boot" {
  name          = "${var.project_name}-spring-boot"
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = 30

  artifacts {
    type = "NO_ARTIFACTS"
  }

  cache {
    type     = "S3"
    location = "${aws_s3_bucket.codebuild_cache.bucket}/spring-boot"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = true

    environment_variable {
      name  = "ECR_REPOSITORY_URI"
      value = aws_ecr_repository.app_repo.repository_url
    }

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.aws_region
    }
  }

  source {
    type     = "GITHUB"
    location = "https://github.com/placeholder/repo.git"
    # buildspec을 외부 파일에서 읽어옵니다.
    buildspec = file("${path.module}/buildspecs/spring-boot.yml")
  }

  logs_config {
    cloudwatch_logs {
      group_name = "/aws/codebuild/${var.project_name}-spring-boot"
    }
  }

  tags = {
    Name = "${var.project_name}-spring-boot"
  }
}

# Node.js CodeBuild 프로젝트
resource "aws_codebuild_project" "nodejs" {
  name          = "${var.project_name}-nodejs"
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = 30

  artifacts {
    type = "NO_ARTIFACTS"
  }

  cache {
    type     = "S3"
    location = "${aws_s3_bucket.codebuild_cache.bucket}/nodejs"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = true

    environment_variable {
      name  = "ECR_REPOSITORY_URI"
      value = aws_ecr_repository.app_repo.repository_url
    }

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.aws_region
    }
  }

  source {
    type     = "GITHUB"
    location = "https://github.com/placeholder/repo.git"
    # buildspec을 외부 파일에서 읽어옵니다.
    buildspec = file("${path.module}/buildspecs/nodejs.yml")
  }

  logs_config {
    cloudwatch_logs {
      group_name = "/aws/codebuild/${var.project_name}-nodejs"
    }
  }

  tags = {
    Name = "${var.project_name}-nodejs"
  }
}

# Next.js CodeBuild 프로젝트
resource "aws_codebuild_project" "nextjs" {
  name          = "${var.project_name}-nextjs"
  service_role  = aws_iam_role.codebuild.arn
  build_timeout = 30

  artifacts {
    type = "NO_ARTIFACTS"
  }

  cache {
    type     = "S3"
    location = "${aws_s3_bucket.codebuild_cache.bucket}/nextjs"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:7.0"
    type                        = "LINUX_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = true

    environment_variable {
      name  = "ECR_REPOSITORY_URI"
      value = aws_ecr_repository.app_repo.repository_url
    }

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.aws_region
    }
  }

  source {
    type     = "GITHUB"
    location = "https://github.com/placeholder/repo.git"
    # buildspec을 외부 파일에서 읽어옵니다.
    buildspec = file("${path.module}/buildspecs/nextjs.yml")
  }

  logs_config {
    cloudwatch_logs {
      group_name = "/aws/codebuild/${var.project_name}-nextjs"
    }
  }

  tags = {
    Name = "${var.project_name}-nextjs"
  }
}
