output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = aws_apigatewayv2_api.main.api_endpoint
}

output "alb_dns" {
  description = "Application Load Balancer DNS name"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.app_repo.repository_url
}

output "ecs_cluster_name" {
  description = "ECS Cluster name"
  value       = aws_ecs_cluster.main.name
}

output "frontend_url" {
  description = "Frontend Custom Domain URL"
  value       = "https://${var.domain_name}"
}

output "frontend_cloudfront_url" {
  description = "Frontend CloudFront Default URL"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "frontend_s3_url" {
  description = "Frontend S3 website URL"
  value       = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}

output "api_domain_url" {
  description = "API Custom Domain URL"
  value       = "https://api.${var.domain_name}"
}
