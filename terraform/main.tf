terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7.1"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7.2"
    }
  }

  backend "s3" {
    bucket         = "whaleray-tfstate-prod"
    key            = "prod/whaleray.tfstate"
    region         = "ap-northeast-2"
    dynamodb_table = "whaleray-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "WhaleRay"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

provider "archive" {
}

data "aws_caller_identity" "current" {}





