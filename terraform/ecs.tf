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

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = [
    aws_ecs_capacity_provider.app_instances.name,
    aws_ecs_capacity_provider.router_instances.name
  ]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = aws_ecs_capacity_provider.app_instances.name
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ECS 최적화 AMI 조회
data "aws_ssm_parameter" "app_ami" {
  name = "/aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id"
}

# EC2 인스턴스를 위한 IAM Role
resource "aws_iam_role" "ec2_instance_role" {
  name = "${var.project_name}-ec2-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_instance_role" {
  role       = aws_iam_role.ec2_instance_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEC2ContainerServiceforEC2Role"
}

resource "aws_iam_instance_profile" "ec2_instance_profile" {
  name = "${var.project_name}-ec2-instance-profile"
  role = aws_iam_role.ec2_instance_role.name
}

# Launch Template for ECS instances
resource "aws_launch_template" "app_instances" {
  name_prefix   = "${var.project_name}-app-"
  image_id      = data.aws_ssm_parameter.app_ami.value
  instance_type = var.ecs_instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2_instance_profile.name
  }

  vpc_security_group_ids = [aws_security_group.ecs_instances.id]

  user_data = base64encode(templatefile("${path.module}/scripts/user-data.sh", {
    cluster_name = aws_ecs_cluster.main.name
  }))

  monitoring {
    enabled = true
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-app-instance"
    }
  }
}

# Auto Scaling Group
# Managed by ECS Capacity Provider for infrastructure-level scaling
resource "aws_autoscaling_group" "app_instances" {
  name                  = "${var.project_name}-app-asg"
  vpc_zone_identifier   = aws_subnet.private[*].id
  min_size              = 1    # Minimum 1 instance for availability
  max_size              = 5    # Maximum 5 instances for cost control
  protect_from_scale_in = true # Required for ECS managed scaling

  launch_template {
    id      = aws_launch_template.app_instances.id
    version = "$Latest"
  }

  health_check_type         = "EC2"
  health_check_grace_period = 300

  tag {
    key                 = "Name"
    value               = "${var.project_name}-app-instance"
    propagate_at_launch = true
  }

  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }
}

# ECS Capacity Provider
# Implements 2-Stage Auto Scaling: Infrastructure scales when task demand increases
resource "aws_ecs_capacity_provider" "app_instances" {
  name = "${var.project_name}-app-capacity-provider"

  auto_scaling_group_provider {
    auto_scaling_group_arn         = aws_autoscaling_group.app_instances.arn
    managed_termination_protection = "DISABLED" # Allow ECS to terminate instances

    managed_scaling {
      status                    = "ENABLED"
      target_capacity           = 90 # Scale out when cluster utilization reaches 90%
      minimum_scaling_step_size = 1
      maximum_scaling_step_size = 5
    }
  }
}

# ============================================
# Router Infrastructure
# ============================================

# Launch Template for Router instances
resource "aws_launch_template" "router_instances" {
  name_prefix   = "${var.project_name}-router-"
  image_id      = data.aws_ssm_parameter.app_ami.value # 동일한 ECS 최적화 AMI 사용
  instance_type = "t3.micro"                           # 라우터는 더 작은 인스턴스 사용 가능

  iam_instance_profile {
    name = aws_iam_instance_profile.ec2_instance_profile.name
  }

  vpc_security_group_ids = [aws_security_group.ecs_instances.id]

  user_data = base64encode(templatefile("${path.module}/scripts/user-data.sh", {
    cluster_name = aws_ecs_cluster.main.name
  }))

  monitoring {
    enabled = true
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-router-instance"
    }
  }
}

# Auto Scaling Group for Router
resource "aws_autoscaling_group" "router_instances" {
  name                  = "${var.project_name}-router-asg"
  vpc_zone_identifier   = aws_subnet.private[*].id
  min_size              = 2 # 라우터는 고가용성을 위해 최소 2대 유지
  max_size              = 4
  desired_capacity      = 2
  protect_from_scale_in = false # 라우터는 ECS가 직접 관리하지 않으므로 false

  launch_template {
    id      = aws_launch_template.router_instances.id
    version = "$Latest"
  }

  # 라우터 ASG는 ECS Capacity Provider로 관리하지 않으므로, ALB 타겟 그룹에 직접 연결
  target_group_arns = [aws_lb_target_group.router.arn]

  health_check_type         = "ELB" # ALB 헬스체크 사용
  health_check_grace_period = 300

  tag {
    key                 = "Name"
    value               = "${var.project_name}-router-instance"
    propagate_at_launch = true
  }
}

# ECS Capacity Provider for Router
resource "aws_ecs_capacity_provider" "router_instances" {
  name = "${var.project_name}-router-capacity-provider"
  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.router_instances.arn
  }
}

# Security Group for ECS EC2 instances
resource "aws_security_group" "ecs_instances" {
  name        = "${var.project_name}-ecs-instances"
  description = "Security group for ECS EC2 instances"
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
    Name = "${var.project_name}-ecs-instances"
  }
}

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
