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
TASK_EXECUTION_ROLE = os.environ['TASK_EXECUTION_ROLE']
TASK_ROLE = os.environ['TASK_ROLE']
TARGET_GROUP_ARN = os.environ['TARGET_GROUP_ARN']

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)


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
        service_name = deployment.get('serviceName')
        user_id = deployment.get('userId')
        port = deployment.get('port', 3000)

        # 실제 배포 시작 전 상태를 DEPLOYING으로 변경
        update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, 'DEPLOYING')

        print("Build Succeeded! Starting deployment process...")
        print(f"Deployment ID: {deployment_id}")
        print(f"Image to deploy: {ecr_image_uri}")

        # TODO: 여기에 실제 ECS 배포 로직이 들어갑니다.

        return {
            'statusCode': 200,
            'body': json.dumps(
                {'message': 'Deployment process triggered successfully', 'deploymentId': deployment_id}
            )
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
