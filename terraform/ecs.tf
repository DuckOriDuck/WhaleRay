resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-cluster"
  }
}

# Security Group for Fargate Tasks
resource "aws_security_group" "fargate_tasks" {
  name        = "${var.project_name}-fargate-tasks"
  description = "Security group for Fargate tasks"
  vpc_id      = aws_vpc.main.id

  # Allow inbound from router security group
  ingress {
    description     = "Allow traffic from router"
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.router.id]
  }

  # Allow inbound from ALB for health checks and traffic
  ingress {
    description     = "Allow PostgreSQL traffic from ALB"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  ingress {
    description     = "Allow pgAdmin traffic from ALB"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # Allow all outbound traffic
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-fargate-tasks"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  # Fargate capacity providers
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ============================================
# EC2-based ECS resources removed - Using Fargate only
# ============================================

# ============================================
# Fargate EBS Infrastructure Role
# ============================================
# Fargate가 EBS 볼륨을 관리(생성, 연결, 태그)하는 데 사용하는 전용 역할입니다.
resource "aws_iam_role" "ecs_infra_role" {
  name = "${var.project_name}-ecs-infra-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs.amazonaws.com"
      }
    }]
  })
}

# AWS에서 제공하는 Fargate EBS 관리용 관리형 정책 연결
resource "aws_iam_role_policy_attachment" "ecs_infra_ebs" {
  role       = aws_iam_role.ecs_infra_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRolePolicyForVolumes"
}

# [FIX] Fargate EBS 볼륨 생성을 위해 ecs-infra-role에 ec2:DescribeAvailabilityZones 권한 추가
resource "aws_iam_role_policy" "ecs_infra_describe_az" {
  name = "${var.project_name}-ecs-infra-describe-az"
  role = aws_iam_role.ecs_infra_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ec2:DescribeAvailabilityZones"]
        Resource = "*"
      }
    ]
  })
}
# ============================================
# Data source for current AWS account ID
# ============================================
#data "aws_caller_identity" "current" {}

# ============================================
# ECS Task Execution Role
# ============================================

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ecs-tasks.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task Execution Role에 로그 그룹 생성 권한 추가
# (기존 관리형 정책에는 CreateLogStream만 있고 CreateLogGroup은 없음)
resource "aws_iam_role_policy" "ecs_task_execution_custom" {
  name = "${var.project_name}-ecs-task-execution-custom"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/${var.project_name}-*:*"
      }
    ]
  })
}

# ============================================
# ECS Task Role
# ============================================

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = ["ecs-tasks.amazonaws.com", "ecs.amazonaws.com"]
      }
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task_ebs" {
  name = "${var.project_name}-ecs-task-ebs"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateVolume",
          "ec2:AttachVolume",
          "ec2:DeleteVolume",
          "ec2:DescribeVolumes",
          "ec2:DescribeVolumeStatus",
          "ec2:DescribeAvailabilityZones",
          "ec2:CreateTags"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks"
  description = "Security group for ECS tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-ecs-tasks"
  }
}

# ============================================
# Database Task Definition (Postgres + pgAdmin)
# ============================================

resource "aws_ecs_task_definition" "database" {
  family                   = "${var.project_name}-database"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024" # 1 vCPU
  memory                   = "2048" # 2 GB

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "postgres"
      image     = "postgres:15"
      essential = true
      portMappings = [
        {
          containerPort = 5432
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "POSTGRES_DB"
          value = "whaleray"
        }
        # POSTGRES_USER and POSTGRES_PASSWORD will be injected by ECS RunTask overrides
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-database"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "postgres"
          "awslogs-create-group"  = "true"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "pg_isready"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
      # Mount point for EBS volume (if attached)
      # mountPoints = [
      #   {
      #     sourceVolume  = "db-storage"
      #     containerPath = "/var/lib/postgresql/data"
      #     readOnly      = false
      #   }
      # ]
    },
    {
      name      = "pgadmin"
      image     = "dpage/pgadmin4"
      essential = true
      portMappings = [
        {
          containerPort = 80
          protocol      = "tcp"
        }
      ]
      environment = [
        {
          name  = "PGADMIN_DEFAULT_EMAIL"
          value = "admin@whaleray.local"
        },
        {
          name  = "PGADMIN_DEFAULT_PASSWORD"
          value = "admin" # Should be changed or managed better in prod
        },
        {
          name  = "PGADMIN_LISTEN_PORT"
          value = "80"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/${var.project_name}-database"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "pgadmin"
          "awslogs-create-group"  = "true"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "wget --spider -q http://localhost:80/misc/ping || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  # Volume configuration will be handled dynamically or via attachment
}
