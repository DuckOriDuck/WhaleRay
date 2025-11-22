# ============================================
# Service Discovery (Cloud Map)
# ============================================
# Creates a private DNS namespace for service-to-service communication
# Services can discover each other using {deploymentId}.whaleray.local

resource "aws_service_discovery_private_dns_namespace" "whaleray" {
  name        = "whaleray.local"
  description = "Private DNS namespace for WhaleRay service discovery"
  vpc         = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-service-discovery"
  }
}

# [추가] ECS 서비스 등록을 위한 Cloud Map 서비스 생성
resource "aws_service_discovery_service" "app_services" {
  name = "apps" # 서비스 이름 (예: apps.whaleray.local)

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.whaleray.id

    dns_records {
      ttl  = 10
      type = "A" # Fargate with awsvpc network mode uses A records
    }

    routing_policy = "MULTIVALUE"
  }
}

resource "aws_service_discovery_service" "db_services" {
  name = "db"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.whaleray.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }
}

# Output the namespace ID for use in ECS services
output "service_discovery_namespace_id" {
  description = "Cloud Map namespace ID for service registration"
  value       = aws_service_discovery_private_dns_namespace.whaleray.id
}

output "service_discovery_namespace_name" {
  description = "Cloud Map namespace name"
  value       = aws_service_discovery_private_dns_namespace.whaleray.name
}
