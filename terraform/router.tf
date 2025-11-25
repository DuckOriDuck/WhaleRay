# ============================================
# WhaleRay Router - Dynamic Nginx Proxy
# ============================================
# This router receives requests from ALB and dynamically proxies them
# to backend services using Cloud Map service discovery

# ============================================
# ALB Target Group for Router
# ============================================
resource "aws_lb_target_group" "router" {
  name_prefix = "wrrt-" # WhaleRay Router
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip" # Fargate with awsvpc uses IP target type

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200,404" # 404 is ok since /health may not exist
  }

  deregistration_delay = 30

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${var.project_name}-router-tg"
  }
}

# ============================================
# ALB Listener Rule for /services/* routing
# ============================================
resource "aws_lb_listener_rule" "service_domain" {
  listener_arn = aws_lb_listener.https.arn # HTTPS 리스너에 규칙을 적용합니다.
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.router.arn
  }

  condition {
    host_header {
      values = ["${var.service_domain_prefix}.${var.domain_name}"]
    }
  }

  tags = {
    Name = "${var.project_name}-service-domain-rule"
  }

  lifecycle {
    replace_triggered_by = [
      aws_lb_target_group.router.id
    ]
  }
}

# ============================================
# ECR Repository for Router Image
# ============================================
resource "aws_ecr_repository" "router" {
  name                 = "${var.project_name}/router"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

locals {
  router_image_tag = sha1(file("${path.module}/../router/nginx.conf"))
  router_image_uri = "${aws_ecr_repository.router.repository_url}:${local.router_image_tag}"
}

# ============================================
# Build and Push Router Docker Image
# ============================================
resource "null_resource" "build_and_push_router_image" {
  # Re-build when nginx.conf or Dockerfile changes
  triggers = {
    nginx_conf_sha = filesha1("${path.module}/../router/nginx.conf")
    dockerfile_sha = filesha1("${path.module}/../router/Dockerfile")
  }

  provisioner "local-exec" {
    command     = <<-EOT
      set -e
      echo "Logging in to Amazon ECR..."
      aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com
      
      echo "Building and pushing router image: ${local.router_image_uri}"
      docker build -t ${local.router_image_uri} ${path.module}/../router
      docker push ${local.router_image_uri}
    EOT
    interpreter = ["/bin/bash", "-c"]
  }

  # Ensure ECR repository exists before trying to push
  depends_on = [aws_ecr_repository.router]
}


# ============================================
# Router Security Group
# ============================================
resource "aws_security_group" "router" {
  name        = "${var.project_name}-router"
  description = "Security group for WhaleRay Router (Nginx)"
  vpc_id      = aws_vpc.main.id

  # Allow incoming traffic from ALB only
  ingress {
    description     = "Allow HTTP from ALB"
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # Allow all outbound traffic to reach backend services
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-router"
  }
}

# ============================================
# Router ECS Task Definition (Fargate)
# ============================================
resource "aws_ecs_task_definition" "router" {
  family                   = "${var.project_name}-router"
  network_mode             = "awsvpc" # Required for Fargate
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  cpu                      = "256"
  memory                   = "512"

  container_definitions = jsonencode([{
    name      = "nginx"
    image     = local.router_image_uri # Use our custom image
    essential = true

    portMappings = [{
      containerPort = 80
      protocol      = "tcp"
      # No hostPort for Fargate
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs_router.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "router"
        "awslogs-create-group"  = "true"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:80/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = {
    Name = "${var.project_name}-router-task"
  }

  # Re-create task definition when the image changes
  depends_on = [null_resource.build_and_push_router_image]
}

# ============================================
# Router ECS Service (Fargate)
# ============================================
resource "aws_ecs_service" "router" {
  name            = "${var.project_name}-router"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.router.arn
  desired_count   = 2 # High availability with minimum 2 tasks
  launch_type     = "FARGATE"

  # Network configuration for Fargate
  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.router.id]
    assign_public_ip = false
  }

  # Load balancer configuration
  load_balancer {
    target_group_arn = aws_lb_target_group.router.arn
    container_name   = "nginx"
    container_port   = 80
  }

  # Deploy configuration
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100
  force_new_deployment               = true

  # Health check grace period
  health_check_grace_period_seconds = 60

  # Enable ECS Exec for debugging
  enable_execute_command = true

  tags = {
    Name = "${var.project_name}-router-service"
  }

  depends_on = [
    aws_lb_listener_rule.service_domain,
    null_resource.build_and_push_router_image # Ensure image is pushed before service is created/updated
  ]
}

# ============================================
# Router Auto Scaling (Task-level scaling)
# ============================================
resource "aws_appautoscaling_target" "router" {
  max_capacity       = 5 # Maximum 5 tasks
  min_capacity       = 2 # Minimum 2 tasks for HA
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.router.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Scale out when CPU > 60%
resource "aws_appautoscaling_policy" "router_cpu" {
  name               = "${var.project_name}-router-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.router.resource_id
  scalable_dimension = aws_appautoscaling_target.router.scalable_dimension
  service_namespace  = aws_appautoscaling_target.router.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    target_value       = 60.0 # Scale when CPU > 60%
    scale_in_cooldown  = 300  # Wait 5 minutes before scaling in
    scale_out_cooldown = 60   # Wait 1 minute before scaling out again
  }
}

# ============================================
# ALB Listener Rule for DB routing
# ============================================
resource "aws_lb_listener_rule" "db_domain" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 110 # Lower priority than service domain rule (100) or higher? 
  # Let's use 110 to avoid conflict if needed, but they are distinct domains.

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.router.arn
  }

  condition {
    host_header {
      values = ["${var.db_domain_prefix}.${var.domain_name}"]
    }
  }

  tags = {
    Name = "${var.project_name}-db-domain-rule"
  }
}
