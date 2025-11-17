import json
import os
import boto3
import time
from datetime import datetime
from uuid import uuid4

ecs = boto3.client('ecs')
dynamodb = boto3.resource('dynamodb')

CLUSTER_NAME = os.environ['CLUSTER_NAME']
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
SERVICES_TABLE = os.environ['SERVICES_TABLE']
TASK_EXECUTION_ROLE = os.environ['TASK_EXECUTION_ROLE']
TASK_ROLE = os.environ['TASK_ROLE']
SUBNETS = os.environ['SUBNETS'].split(',')
SECURITY_GROUPS = os.environ['SECURITY_GROUPS']
TARGET_GROUP_ARN = os.environ['TARGET_GROUP_ARN']

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)
services_table = dynamodb.Table(SERVICES_TABLE)


def handler(event, context):
    """
    ECS 서비스 배포를 처리하는 Lambda 함수
    """
    try:
        # Cognito authorizer에서 userId 추출
        user_id = event['requestContext']['authorizer']['jwt']['claims']['sub']

        # 요청 본문 파싱
        body = json.loads(event['body'])

        service_name = body.get('serviceName')
        image_uri = body.get('imageUri')
        port = body.get('port', 3000)
        env_vars = body.get('envVars', {})

        if not service_name or not image_uri:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'serviceName and imageUri are required'})
            }

        # Service ID 생성 또는 조회
        service_id = f"{user_id}-{service_name}"
        deployment_id = str(uuid4())

        # DynamoDB에 배포 정보 저장
        timestamp = int(time.time())
        deployments_table.put_item(Item={
            'deploymentId': deployment_id,
            'userId': user_id,
            'serviceId': service_id,
            'serviceName': service_name,
            'imageUri': image_uri,
            'status': 'PENDING',
            'createdAt': timestamp,
            'updatedAt': timestamp
        })

        # ECS Task Definition 생성
        task_def_name = f"whaleray-{service_name}-{deployment_id[:8]}"

        container_env = [
            {'name': k, 'value': str(v)} for k, v in env_vars.items()
        ]

        task_definition = ecs.register_task_definition(
            family=task_def_name,
            networkMode='bridge',
            requiresCompatibilities=['EC2'],
            executionRoleArn=TASK_EXECUTION_ROLE,
            taskRoleArn=TASK_ROLE,
            containerDefinitions=[
                {
                    'name': service_name,
                    'image': image_uri,
                    'essential': True,
                    'memory': 512,
                    'portMappings': [{
                        'containerPort': port,
                        'hostPort': 0,  # 동적 포트 매핑
                        'protocol': 'tcp'
                    }],
                    'environment': container_env,
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

        # 서비스 정보 업데이트
        services_table.put_item(Item={
            'serviceId': service_id,
            'userId': user_id,
            'serviceName': service_name,
            'imageUri': image_uri,
            'port': port,
            'status': 'ACTIVE',
            'taskDefinitionArn': task_def_arn,
            'latestDeploymentId': deployment_id,
            'createdAt': timestamp,
            'updatedAt': timestamp
        })

        # 배포 상태 업데이트
        deployments_table.update_item(
            Key={'deploymentId': deployment_id},
            UpdateExpression='SET #status = :status, updatedAt = :updatedAt',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'DEPLOYED',
                ':updatedAt': int(time.time())
            }
        )

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': f'Service {action} successfully',
                'deploymentId': deployment_id,
                'serviceId': service_id,
                'taskDefinitionArn': task_def_arn
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")

        # 배포 실패 기록
        if 'deployment_id' in locals():
            deployments_table.update_item(
                Key={'deploymentId': deployment_id},
                UpdateExpression='SET #status = :status, errorMessage = :error, updatedAt = :updatedAt',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':status': 'FAILED',
                    ':error': str(e),
                    ':updatedAt': int(time.time())
                }
            )

        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Deployment failed',
                'message': str(e)
            })
        }
