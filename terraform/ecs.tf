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

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-ecs-task"

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
      name  = "postgres"
      image = "postgres:15"
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
      name  = "pgadmin"
      image = "dpage/pgadmin4"
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
    }
  ])

  # Volume configuration will be handled dynamically or via attachment
}
