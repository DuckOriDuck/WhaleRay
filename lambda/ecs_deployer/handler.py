import json
import os
import boto3
import time

ecs = boto3.client('ecs')
# Lambda Layer에서 공통 유틸리티 함수 가져오기
from github_utils import update_deployment_status

dynamodb = boto3.resource('dynamodb')

CLUSTER_NAME = os.environ['CLUSTER_NAME']
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
SERVICES_TABLE = os.environ['SERVICES_TABLE']
TASK_EXECUTION_ROLE = os.environ['TASK_EXECUTION_ROLE']
TASK_ROLE = os.environ['TASK_ROLE']
FRONTEND_URL = os.environ['FRONTEND_URL']
SERVICE_DISCOVERY_REGISTRY_ARN = os.environ['SERVICE_DISCOVERY_REGISTRY_ARN']
# Fargate network configuration
PRIVATE_SUBNETS = os.environ['PRIVATE_SUBNETS']
FARGATE_TASK_SG = os.environ['FARGATE_TASK_SG']

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)
services_table = dynamodb.Table(SERVICES_TABLE)


def handler(event, context):
    """
    CodeBuild 빌드 완료 이벤트를 받아서 ECS로 배포하는 Lambda 함수
    """
    print("invoked!")
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
            update_deployment_status(
                DEPLOYMENTS_TABLE,
                deployment_id,
                'BUILDING_FAIL'
            )
            print(f"Deployment {deployment_id} status updated to BUILD_FAILED.")
            return {'statusCode': 200, 'body': 'Build failed, deployment aborted'}

        # 빌드 성공 - ECS 배포 시작
        service_name = deployment['serviceName'] # 이제 deployments 테이블에 serviceName이 항상 존재합니다.
        service_id = deployment['serviceId'] # 배포 정보에서 serviceId를 직접 가져옵니다.
        port = deployment.get('port', 3000)

        # 실제 배포 시작 전 상태를 DEPLOYING으로 변경
        update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'DEPLOYING')

        print("Build Succeeded! Starting deployment process...")
        print(f"Deployment ID: {deployment_id}")
        print(f"Image to deploy: {ecr_image_uri}")

        # ECS Task Definition 생성 : 쉬운 로그 풀링을 위해
        task_def_name = f"whaleray-{service_name}-{deployment_id[:8]}"

        task_definition = ecs.register_task_definition(
            family=task_def_name,
            cpu='256',  # Fargate requires explicit CPU
            memory='512',  # Fargate requires explicit memory
            networkMode='awsvpc',  # Fargate requires awsvpc
            requiresCompatibilities=['FARGATE'],
            executionRoleArn=TASK_EXECUTION_ROLE,
            taskRoleArn=TASK_ROLE,
            containerDefinitions=[
                {
                    'name': service_name,
                    'image': ecr_image_uri,
                    'essential': True,
                    'portMappings': [{
                        'containerPort': port,
                        'protocol': 'tcp'
                        # No hostPort for Fargate with awsvpc
                    }],
                    'environment': deployment.get('envVars', []),
                    'logConfiguration': {
                        'logDriver': 'awslogs',
                        'options': {
                            # 로그 그룹을 중앙화하고, 스트림 접두사로 로그를 격리합니다.
                            'awslogs-group': f'/ecs/{CLUSTER_NAME}',
                            'awslogs-region': os.environ['AWS_REGION'],
                            'awslogs-stream-prefix': deployment_id,
                            'awslogs-create-group': 'true'
                        }
                    }
                }
            ]
        )

        task_def_arn = task_definition['taskDefinition']['taskDefinitionArn']

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
            # 새 서비스 생성 (Fargate)
            ecs.create_service(
                cluster=CLUSTER_NAME,
                serviceName=service_id,
                taskDefinition=task_def_arn,
                desiredCount=1,
                launchType='FARGATE',
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': os.environ['PRIVATE_SUBNETS'].split(','),
                        'securityGroups': [os.environ['FARGATE_TASK_SG']],
                        'assignPublicIp': 'DISABLED'
                    }
                },
                # Cloud Map 서비스 검색 등록 (A 레코드)
                # awsvpc 네트워크 모드에서는 containerName만 사용
                serviceRegistries=[{
                    'registryArn': SERVICE_DISCOVERY_REGISTRY_ARN,
                    'containerName': service_name
                }]
            )
            action = 'created'

        # Deployments 테이블 업데이트
        # 배포 성공 시점에 엔드포인트가 확정되므로 여기가 더 적합합니다.
        service_endpoint = f"https://{os.environ['API_DOMAIN']}/{service_id}"

        update_deployment_status(
            DEPLOYMENTS_TABLE,
            deployment_id,
            'RUNNING',
            ecsService=service_id,
            ecsLogGroup=f'/ecs/{CLUSTER_NAME}',
            taskDefinitionArn=task_def_arn
        )

        # 이전 RUNNING 상태의 배포를 SUPERSEDED로 변경
        supersede_previous_deployment(deployment, service_id, service_endpoint)

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
            update_deployment_status(
                DEPLOYMENTS_TABLE,
                deployment_id,
                'DEPLOYING_FAIL'
            )

        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def supersede_previous_deployment(current_deployment: dict, service_id: str, service_endpoint: str):
    """
    services 테이블을 사용하여 이전 활성 배포를 SUPERSEDED로 만들고,
    새로운 배포 ID로 activeDeploymentId를 업데이트
    """
    print(f"Superseding previous deployment for service '{service_id}'...")
    try:
        current_deployment_id = current_deployment['deploymentId']
        user_id = current_deployment['userId']
        service_name = current_deployment.get('serviceName', service_id)

        # Cloud Map DNS는 내부 통신용이므로 저장하지 않음

        # 1. services 테이블에서 이전 activeDeploymentId를 가져옵니다.
        service_response = services_table.get_item(Key={'serviceId': service_id})
        old_active_deployment_id = service_response.get('Item', {}).get('activeDeploymentId')

        # 2. 이전 배포가 존재하면 SUPERSEDED로 상태를 변경합니다.
        if old_active_deployment_id and old_active_deployment_id != current_deployment_id:
            print(
                f"Found previous active deployment {old_active_deployment_id}, updating to SUPERSEDED."
            )
            update_deployment_status(
                DEPLOYMENTS_TABLE,
                old_active_deployment_id,
                'SUPERSEDED'
            )

        # 3. services 테이블의 activeDeploymentId를 현재 배포 ID로 업데이트합니다.
        update_expression_parts = [
            'activeDeploymentId = :did',
            'userId = :uid', # GSI용
            'serviceName = :sname',
            'serviceEndpoint = :endpoint'
        ]
        expression_attr_values = {
            ':did': current_deployment_id,
            ':uid': user_id,
            ':sname': service_name,
            ':endpoint': service_endpoint
        }

        services_table.update_item(
            Key={'serviceId': service_id},
            UpdateExpression='SET ' + ', '.join(update_expression_parts),
            ExpressionAttributeValues=expression_attr_values
        )
        print(f"Service {service_id} active deployment updated to {current_deployment_id}.")
        print(f"Service endpoint: {service_endpoint}")

    except Exception as e:
        # 이 로직은 메인 배포 흐름에 영향을 주지 않도록 오류를 로깅만 합니다.
        print(f"Warning: Failed to supersede previous deployments. Error: {str(e)}")
