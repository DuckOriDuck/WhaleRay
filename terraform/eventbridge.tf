# EventBridge Rule for CodeBuild State Change
resource "aws_cloudwatch_event_rule" "codebuild_state_change" {
  name        = "${var.project_name}-codebuild-state-change"
  description = "Capture CodeBuild build state changes"

  event_pattern = jsonencode({
    source      = ["aws.codebuild"]
    detail-type = ["CodeBuild Build State Change"]
    detail = {
      build-status = ["SUCCEEDED", "FAILED"]
      project-name = [
        aws_codebuild_project.spring_boot.name,
        aws_codebuild_project.nodejs.name,
        aws_codebuild_project.nextjs.name,
        aws_codebuild_project.python.name
      ]
    }
  })
}

resource "aws_cloudwatch_event_target" "codebuild_to_deployer" {
  rule      = aws_cloudwatch_event_rule.codebuild_state_change.name
  target_id = "EcsDeployerLambda"
  arn       = aws_lambda_function.ecs_deployer.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ecs_deployer.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.codebuild_state_change.arn
}
