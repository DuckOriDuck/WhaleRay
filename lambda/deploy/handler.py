"""
POST /deployments
GitHub App installation을 사용하여 repository 배포 시작
"""
import json
import os
import boto3
import time
from uuid import uuid4

# Boto3 클라이언트 및 리소스 초기화
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# 환경 변수에서 테이블 및 함수 이름 가져오기
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
INSTALLATIONS_TABLE = os.environ['INSTALLATIONS_TABLE']
REPO_INSPECTOR_FUNCTION_NAME = os.environ['REPO_INSPECTOR_FUNCTION_NAME']
FRONTEND_URL = os.environ.get('FRONTEND_URL', '*') # CORS 헤더용

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)
installations_table = dynamodb.Table(INSTALLATIONS_TABLE)


def handler(event, context):
    """
    POST /deployments

    Body:
    - repositoryFullName: string (e.g., "DuckOriDuck/whaleray")
    - branch: string
    """
    try:
        # JWT authorizer에서 userId 추출
        # API Gateway Payload v1.0 및 v2.0 호환
        auth_ctx = event.get('requestContext', {}).get('authorizer', {}) or {}
        lambda_ctx = auth_ctx.get('lambda', {}) or {}
        
        user_id = lambda_ctx.get('userId') or lambda_ctx.get('sub')

        if not user_id:
            print(f"Unauthorized: userId not found in authorizer context. Context: {json.dumps(auth_ctx)}")
            return _response(401, {'error': 'Unauthorized'})
        print(f"Authorized user: {user_id}")

        # 요청 본문 파싱
        body = json.loads(event['body'])
        repository_full_name = body.get('repositoryFullName')
        branch = body.get('branch', 'main')
        env_file_content = body.get('envFileContent', '') # .env 파일 내용 추가

        if not repository_full_name:
            return _response(400, {'error': 'repositoryFullName is required'})

        # repositoryFullName에서 accountLogin (소유자) 추출
        try:
            repo_owner = repository_full_name.split('/')[0]
        except (IndexError, AttributeError):
            return _response(400, {'error': 'Invalid repositoryFullName format. Expected "owner/repo".'})

        # userId로 installations 조회
        response = installations_table.query(
            IndexName='userId-index',
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={':userId': user_id},
            ScanIndexForward=False  # 최신 순으로 정렬 (createdAt DESC)
        )
        installations = response.get('Items', [])

        if not installations:
            return _response(404, {
                'error': 'No GitHub App installation found',
                'needInstallation': True
            })

        # 올바른 installation 찾기 (최신순 정렬된 결과에서 첫 번째 선택)
        target_installation = None
        for inst in installations:
            if inst.get('accountLogin') == repo_owner:
                target_installation = inst
                break  # 첫 번째가 가장 최신이므로 즉시 선택

        if not target_installation:
            return _response(404, {'error': f'No installation found for repository owner "{repo_owner}". Please install the GitHub App.'})

        installation_id = target_installation['installationId']

        # 배포 정보 생성
        deployment_id = str(uuid4())
        timestamp = int(time.time())
        
        # "owner/repo" 형식을 "owner-repo"로 변환하여 서비스 이름으로 사용
        service_name = repository_full_name.replace('/', '-')
        service_id = f"{user_id}-{service_name}"

        # repo_inspector에 전달할 페이로드
        invoke_payload = {
            'deploymentId': deployment_id,
            'userId': user_id,
            'installationId': installation_id,
            'repositoryFullName': repository_full_name,
            'branch': branch,
            'createdAt': timestamp,
            'updatedAt': timestamp,
            'serviceName': service_name, # 생성된 서비스 이름을 페이로드에 추가
            'serviceId': service_id,      # GSI 및 서비스 식별을 위해 serviceId 추가
            'envFileContent': env_file_content # .env 파일 내용 추가
        }

        # repo_inspector 람다 비동기 호출
        try:
            lambda_client.invoke(
                FunctionName=REPO_INSPECTOR_FUNCTION_NAME,
                InvocationType='Event',
                Payload=json.dumps(invoke_payload)
            )
        except Exception as invoke_error:
            print(f"Failed to invoke repo_inspector: {str(invoke_error)}")
            return _response(500, {'error': 'Failed to start inspection process'})

        # DynamoDB에 배포 정보 저장 (상태: INSPECTING)
        deployments_table.put_item(Item={
            **invoke_payload,
            'status': 'INSPECTING'
        })
        
        # 사용자에게 즉시 응답 반환
        return _response(200, {
            'deploymentId': deployment_id,
            'status': 'INSPECTING'
        })

    except Exception as e:
        print(f"Error: {str(e)}")
        return _response(500, {
            'error': 'Deployment failed',
            'message': str(e)
        })


def _response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': FRONTEND_URL
        },
        'body': json.dumps(body)
    }


def cleanup_orphan_deployments(user_id: str):
    """
    특정 사용자의 배포 중, 30분 이상 진행중인 상태에 머물러 있는 '고아' 배포를 찾아 실패 처리합니다.
    """
    print(f"Starting cleanup of orphan deployments for user: {user_id}...")
    try:
        timeout_threshold = int(time.time()) - 1800  # 30분 전
        in_progress_statuses = ['INSPECTING', 'BUILDING', 'DEPLOYING']

        # GSI를 사용하여 특정 사용자의 배포만 효율적으로 쿼리
        response = deployments_table.query(
            IndexName='userId-index',
            KeyConditionExpression='userId = :userId',
            FilterExpression=boto3.dynamodb.conditions.Attr('status').is_in(in_progress_statuses),
            ExpressionAttributeValues={':userId': user_id}
        )

        orphan_deployments = []
        for item in response.get('Items', []):
            if item.get('updatedAt', 0) < timeout_threshold:
                orphan_deployments.append(item)

        if not orphan_deployments:
            print("No orphan deployments found.")
            return

        print(f"Found {len(orphan_deployments)} orphan deployments to fail.")
        for deployment in orphan_deployments:
            deployment_id = deployment['deploymentId']
            current_status = deployment['status']
            update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, f"{current_status}_TIMEOUT", errorMessage="Deployment timed out.")

    except Exception as e:
        print(f"An error occurred during orphan deployment cleanup: {str(e)}")
