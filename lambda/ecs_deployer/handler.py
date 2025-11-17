import json
import os
import boto3
import time

ecs = boto3.client('ecs')
dynamodb = boto3.resource('dynamodb')

CLUSTER_NAME = os.environ['CLUSTER_NAME']
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
TASK_EXECUTION_ROLE = os.environ['TASK_EXECUTION_ROLE']
TASK_ROLE = os.environ['TASK_ROLE']
TARGET_GROUP_ARN = os.environ['TARGET_GROUP_ARN']

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)


def handler(event, context):
    """
    CodeBuild 빌드 완료 이벤트를 받아서 ECS로 배포하는 Lambda 함수
    """
    print(f"Received event: {json.dumps(event)}")

    try:
        # EventBridge 이벤트에서 정보 추출
        detail = event['detail']
        build_status = detail['build-status']
        project_name = detail['project-name']
        build_id = detail['build-id']

        # 환경 변수에서 DEPLOYMENT_ID 추출
        env_vars = detail.get('additional-information', {}).get('environment', {}).get('environment-variables', [])
        deployment_id = None
        ecr_image_uri = None

        for env in env_vars:
            if env['name'] == 'DEPLOYMENT_ID':
                deployment_id = env['value']
            elif env['name'] == 'ECR_IMAGE_URI':
                ecr_image_uri = env['value']

        if not deployment_id:
            print("No DEPLOYMENT_ID found in build environment variables")
            return {'statusCode': 400, 'body': 'Missing DEPLOYMENT_ID'}

        # Deployments 테이블에서 배포 정보 조회
        response = deployments_table.get_item(Key={'deploymentId': deployment_id})

        if 'Item' not in response:
            print(f"Deployment {deployment_id} not found")
            return {'statusCode': 404, 'body': 'Deployment not found'}

        deployment = response['Item']

        # 빌드 실패 처리
        if build_status == 'FAILED':
            deployments_table.update_item(
                Key={'deploymentId': deployment_id},
                UpdateExpression='SET #status = :status, updatedAt = :updatedAt',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'BUILD_FAILED',
                    ':updatedAt': int(time.time())
                }
            )
            return {'statusCode': 200, 'body': 'Build failed, deployment aborted'}

        # 빌드 성공 - ECS 배포 시작
        service_name = deployment.get('serviceName')
        user_id = deployment.get('userId')
        port = deployment.get('port', 3000)

        if not ecr_image_uri:
            # ECR 이미지 URI 구성
            ecr_repo_url = os.environ['ECR_REPOSITORY_URL']
            ecr_image_uri = f"{ecr_repo_url}:{deployment_id}"

        # ECS Task Definition 생성
        task_def_name = f"whaleray-{service_name}-{deployment_id[:8]}"

        task_definition = ecs.register_task_definition(
            family=task_def_name,
            networkMode='bridge',
            requiresCompatibilities=['EC2'],
            executionRoleArn=TASK_EXECUTION_ROLE,
            taskRoleArn=TASK_ROLE,
            containerDefinitions=[
                {
                    'name': service_name,
                    'image': ecr_image_uri,
                    'essential': True,
                    'memory': 512,
                    'portMappings': [{
                        'containerPort': port,
                        'hostPort': 0,  # 동적 포트 매핑
                        'protocol': 'tcp'
                    }],
                    'environment': deployment.get('envVars', []),
                    'logConfiguration': {
                        'logDriver': 'awslogs',
                        'options': {
                            'awslogs-group': f'/ecs/{task_def_name}',
                            'awslogs-region': os.environ['AWS_REGION'],
                            'awslogs-stream-prefix': 'ecs',
                            'awslogs-create-group': 'true'
                        }
                    }
                }
            ]
        )

        task_def_arn = task_definition['taskDefinition']['taskDefinitionArn']

        # 서비스 ID 구성
        service_id = f"{user_id}-{service_name}"

        # ECS Service 생성 또는 업데이트
        try:
            # 기존 서비스 조회
            existing_services = ecs.describe_services(
                cluster=CLUSTER_NAME,
                services=[service_id]
            )

            if existing_services['services'] and existing_services['services'][0]['status'] == 'ACTIVE':
                # 서비스 업데이트
                ecs.update_service(
                    cluster=CLUSTER_NAME,
                    service=service_id,
                    taskDefinition=task_def_arn,
                    forceNewDeployment=True
                )
                action = 'updated'
            else:
                raise Exception('Service not found or inactive')

        except Exception:
            # 새 서비스 생성
            ecs.create_service(
                cluster=CLUSTER_NAME,
                serviceName=service_id,
                taskDefinition=task_def_arn,
                desiredCount=1,
                launchType='EC2',
                loadBalancers=[{
                    'targetGroupArn': TARGET_GROUP_ARN,
                    'containerName': service_name,
                    'containerPort': port
                }]
            )
            action = 'created'

        # Deployments 테이블 업데이트
        deployments_table.update_item(
            Key={'deploymentId': deployment_id},
            UpdateExpression='SET #status = :status, ecsService = :ecsService, ecsLogGroup = :ecsLogGroup, taskDefinitionArn = :taskDefArn, updatedAt = :updatedAt',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'RUNNING',
                ':ecsService': service_id,
                ':ecsLogGroup': f'/ecs/{task_def_name}',
                ':taskDefArn': task_def_arn,
                ':updatedAt': int(time.time())
            }
        )

        print(f"Service {action}: {service_id}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Service {action} successfully',
                'deploymentId': deployment_id,
                'serviceId': service_id
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

        # 배포 실패 기록
        if 'deployment_id' in locals():
            deployments_table.update_item(
                Key={'deploymentId': deployment_id},
                UpdateExpression='SET #status = :status, errorMessage = :error, updatedAt = :updatedAt',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'DEPLOY_FAILED',
                    ':error': str(e),
                    ':updatedAt': int(time.time())
                }
            )

        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
