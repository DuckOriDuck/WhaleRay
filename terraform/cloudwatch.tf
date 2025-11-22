# CloudWatch Log Groups for ECS Services
resource "aws_cloudwatch_log_group" "ecs_router" {
  name              = "/ecs/${var.project_name}-router"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "ecs_services" {
  name              = "/ecs/${var.project_name}-cluster"
  retention_in_days = 7
}

# CloudWatch Log Groups for Lambda Functions
resource "aws_cloudwatch_log_group" "lambda_deploy" {
  name              = "/aws/lambda/${aws_lambda_function.deploy.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "lambda_deployments_api" {
  name              = "/aws/lambda/${aws_lambda_function.deployments_api.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "lambda_service" {
  name              = "/aws/lambda/${aws_lambda_function.service.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "lambda_ecs_deployer" {
  name              = "/aws/lambda/${aws_lambda_function.ecs_deployer.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "lambda_logs_api" {
  name              = "/aws/lambda/${aws_lambda_function.logs_api.function_name}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "lambda_repo_inspector" {
  name              = "/aws/lambda/${aws_lambda_function.repo_inspector.function_name}"
  retention_in_days = 14
}

# CloudWatch Log Groups for CodeBuild Projects
resource "aws_cloudwatch_log_group" "codebuild_spring_boot" {
  name              = "/aws/codebuild/${var.project_name}-spring-boot"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "codebuild_nodejs" {
  name              = "/aws/codebuild/${var.project_name}-nodejs"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "codebuild_nextjs" {
  name              = "/aws/codebuild/${var.project_name}-nextjs"
  retention_in_days = 7
}

# CloudWatch Dashboard
/*
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project_name}-overview"

  dashboard_body = jsonencode({
    widgets = [
      # Lambda Functions Invocations
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.deploy.function_name],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.deployments_api.function_name],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.service.function_name],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.ecs_deployer.function_name],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.logs_api.function_name],
            ["AWS/Lambda", "Invocations", "FunctionName", aws_lambda_function.repo_inspector.function_name]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Lambda Invocations"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # Lambda Errors
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.deploy.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.deployments_api.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.service.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.ecs_deployer.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.logs_api.function_name],
            ["AWS/Lambda", "Errors", "FunctionName", aws_lambda_function.repo_inspector.function_name]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Lambda Errors"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # Lambda Duration
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.deploy.function_name],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.deployments_api.function_name],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.service.function_name],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.ecs_deployer.function_name],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.logs_api.function_name],
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.repo_inspector.function_name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "Lambda Duration (ms)"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # Lambda Throttles
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.deploy.function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.deployments_api.function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.service.function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.ecs_deployer.function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.logs_api.function_name],
            ["AWS/Lambda", "Throttles", "FunctionName", aws_lambda_function.repo_inspector.function_name]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "Lambda Throttles"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # ECS Cluster CPU Utilization
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 8
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "CPUUtilization", "ClusterName", aws_ecs_cluster.main.name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ECS Cluster CPU Utilization (%)"
          yAxis = {
            left = {
              min = 0
              max = 100
            }
          }
        }
      },
      # ECS Cluster Memory Utilization
      {
        type   = "metric"
        x      = 8
        y      = 12
        width  = 8
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "MemoryUtilization", "ClusterName", aws_ecs_cluster.main.name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ECS Cluster Memory Utilization (%)"
          yAxis = {
            left = {
              min = 0
              max = 100
            }
          }
        }
      },
      # ECS Running Tasks Count
      {
        type   = "metric"
        x      = 16
        y      = 12
        width  = 8
        height = 6
        properties = {
          metrics = [
            ["AWS/ECS", "TaskCount", "ClusterName", aws_ecs_cluster.main.name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ECS Running Tasks"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # CodeBuild Success/Failure
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/CodeBuild", "SuccessfulBuilds", "ProjectName", aws_codebuild_project.spring_boot.name],
            [".", "FailedBuilds", ".", aws_codebuild_project.spring_boot.name],
            [".", "SuccessfulBuilds", ".", aws_codebuild_project.nodejs.name],
            [".", "FailedBuilds", ".", aws_codebuild_project.nodejs.name],
            [".", "SuccessfulBuilds", ".", aws_codebuild_project.nextjs.name],
            [".", "FailedBuilds", ".", aws_codebuild_project.nextjs.name]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "CodeBuild Success/Failure"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # CodeBuild Duration
      {
        type   = "metric"
        x      = 12
        y      = 18
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/CodeBuild", "Duration", "ProjectName", aws_codebuild_project.spring_boot.name],
            ["AWS/CodeBuild", "Duration", "ProjectName", aws_codebuild_project.nodejs.name],
            ["AWS/CodeBuild", "Duration", "ProjectName", aws_codebuild_project.nextjs.name]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "CodeBuild Duration (seconds)"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # Recent Lambda Logs - Deploy
      {
        type   = "log"
        x      = 0
        y      = 24
        width  = 12
        height = 6
        properties = {
          query   = "SOURCE '/aws/lambda/${aws_lambda_function.deploy.function_name}'\n| fields @timestamp, @message\n| filter @message like /ERROR/ or @message like /Exception/ or @message like /error/\n| sort @timestamp desc\n| limit 20"
          region  = var.aws_region
          title   = "Deploy Lambda - Recent Errors"
          stacked = false
        }
      },
      # Recent Lambda Logs - ECS Deployer
      {
        type   = "log"
        x      = 12
        y      = 24
        width  = 12
        height = 6
        properties = {
          query   = "SOURCE '/aws/lambda/${aws_lambda_function.ecs_deployer.function_name}'\n| fields @timestamp, @message\n| filter @message like /ERROR/ or @message like /Exception/ or @message like /error/\n| sort @timestamp desc\n| limit 20"
          region  = var.aws_region
          title   = "ECS Deployer Lambda - Recent Errors"
          stacked = false
        }
      },
      # Recent Lambda Logs - Repo Inspector
      {
        type   = "log"
        x      = 0
        y      = 30
        width  = 12
        height = 6
        properties = {
          query   = "SOURCE '/aws/lambda/${aws_lambda_function.repo_inspector.function_name}'\n| fields @timestamp, @message\n| filter @message like /ERROR/ or @message like /Exception/ or @message like /error/\n| sort @timestamp desc\n| limit 20"
          region  = var.aws_region
          title   = "Repo Inspector Lambda - Recent Errors"
          stacked = false
        }
      },
      # ALB Request Count
      {
        type   = "metric"
        x      = 12
        y      = 30
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", replace(aws_lb.main.arn, "/^.*:loadbalancer\\//", "")]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "ALB Request Count"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # ALB Target Response Time
      {
        type   = "metric"
        x      = 0
        y      = 36
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", replace(aws_lb.main.arn, "/^.*:loadbalancer\\//", "")]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "ALB Target Response Time (seconds)"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      },
      # ALB HTTP Errors
      {
        type   = "metric"
        x      = 12
        y      = 36
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_4XX_Count", "LoadBalancer", replace(aws_lb.main.arn, "/^.*:loadbalancer\\//", "")],
            [".", "HTTPCode_Target_5XX_Count", ".", replace(aws_lb.main.arn, "/^.*:loadbalancer\\//", "")]
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "ALB HTTP Error Count"
          yAxis = {
            left = {
              min = 0
            }
          }
        }
      }
    ]
  })
}
*/

# CloudWatch Alarms for critical issues

# Lambda Error Alarm - Deploy
resource "aws_cloudwatch_metric_alarm" "lambda_deploy_errors" {
  alarm_name          = "${var.project_name}-lambda-deploy-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "This metric monitors deploy lambda errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.deploy.function_name
  }
}

# Lambda Error Alarm - ECS Deployer
resource "aws_cloudwatch_metric_alarm" "lambda_ecs_deployer_errors" {
  alarm_name          = "${var.project_name}-lambda-ecs-deployer-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "This metric monitors ecs deployer lambda errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.ecs_deployer.function_name
  }
}

# ECS CPU Alarm
resource "aws_cloudwatch_metric_alarm" "ecs_cpu_high" {
  alarm_name          = "${var.project_name}-ecs-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "This metric monitors ECS cluster CPU utilization"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
  }
}

# ECS Memory Alarm
resource "aws_cloudwatch_metric_alarm" "ecs_memory_high" {
  alarm_name          = "${var.project_name}-ecs-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  alarm_description   = "This metric monitors ECS cluster memory utilization"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
  }
}

# ALB 5XX Errors Alarm
resource "aws_cloudwatch_metric_alarm" "alb_5xx_errors" {
  alarm_name          = "${var.project_name}-alb-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "This metric monitors ALB 5XX errors"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = replace(aws_lb.main.arn, "/^.*:loadbalancer\\//", "")
  }
}
