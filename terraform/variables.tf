variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "whaleray"
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
}

variable "ecs_instance_type" {
  description = "ECS EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "ecs_min_size" {
  description = "Minimum number of ECS instances"
  type        = number
  default     = 1
}

variable "ecs_max_size" {
  description = "Maximum number of ECS instances"
  type        = number
  default     = 5
}

variable "ecs_desired_size" {
  description = "Desired number of ECS instances"
  type        = number
  default     = 2
}

variable "domain_name" {
  description = "Custom domain name for the application"
  type        = string
  default     = "whaleray.oriduckduck.site"
}

variable "acm_certificate_arn" {
  description = "ACM Certificate ARN for CloudFront (must be in us-east-1)"
  type        = string
  default     = "" # terraform.tfvars에서 설정
}

variable "github_client_id" {
  description = "GitHub OAuth App Client ID"
  type        = string
  sensitive   = true
  default     = "" # terraform.tfvars에서 설정
}

variable "github_client_secret" {
  description = "GitHub OAuth App Client Secret"
  type        = string
  sensitive   = true
  default     = "" # terraform.tfvars에서 설정
}

variable "github_app_slug" {
  description = "GitHub App slug for installation redirect (e.g., whaleray)"
  type        = string
  default     = ""
}

variable "github_app_id" {
  description = "GitHub App ID (used to match installations)"
  type        = string
  default     = ""
}

variable "github_app_private_key" {
  description = "GitHub App Private Key (PEM format)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "service_domain_prefix" {
  description = "Subdomain prefix for deployed services (e.g., 'service' for service.domain.com)"
  type        = string
  default     = "service"
}

variable "db_domain_prefix" {
  description = "Subdomain prefix for database access (e.g., db -> db.domain.com)"
  type        = string
  default     = "db"
}
