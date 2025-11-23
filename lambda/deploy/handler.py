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
        env_file_content = body.get('envFileContent', '')
        is_reset = body.get('isReset', False) # isReset 플래그 추출

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
        )
        installations = response.get('Items', [])

        if not installations:
            return _response(404, {
                'error': 'No GitHub App installation found',
                'needInstallation': True
            })

        # 올바른 installation 찾기
        target_installation = None
        for inst in installations:
            if inst.get('accountLogin') == repo_owner:
                target_installation = inst
                break

        if not target_installation:
            return _response(404, {'error': f'No installation found for repository owner "{repo_owner}". Please install the GitHub App.'})

        installation_id = target_installation['installationId']

        # 배포 정보 생성
        deployment_id = str(uuid4())
        timestamp = int(time.time())
        
        service_name = repository_full_name.replace('/', '-')
        service_id = f"{user_id}-{service_name}"

        # DynamoDB에 저장할 아이템 구성
        item_to_store = {
            'deploymentId': deployment_id,
            'userId': user_id,
            'installationId': installation_id,
            'repositoryFullName': repository_full_name,
            'branch': branch,
            'createdAt': timestamp,
            'updatedAt': timestamp,
            'serviceName': service_name,
            'serviceId': service_id,
            'envFileContent': env_file_content,
            'isReset': is_reset, # isReset 플래그 포함
            'status': 'INSPECTING' # 초기 상태
        }

        # DynamoDB에 배포 정보 저장 (이 작업이 DynamoDB 스트림을 통해 repo_inspector를 트리거)
        deployments_table.put_item(Item=item_to_store)
        
        # 사용자에게 즉시 응답 반환
        return _response(200, {
            'deploymentId': deployment_id,
            'status': 'INSPECTING'
        })

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc() # 오류 스택 트레이스 출력
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

# cleanup_orphan_deployments 함수는 그대로 유지
def cleanup_orphan_deployments(user_id: str):
    """
    특정 사용자의 배포 중, 30분 이상 진행중인 상태에 머물러 있는 '고아' 배포를 찾아 실패 처리합니다.
    """
    print(f"Starting cleanup of orphan deployments for user: {user_id}...")
    try:
        timeout_threshold = int(time.time()) - 1800  # 30분 전
        in_progress_statuses = ['INSPECTING', 'BUILDING', 'DEPLOYING']

        response = installations_table.query(
            IndexName='userId-index',
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={':userId': user_id},
        )
        installations = response.get('Items', [])

        orphan_deployments = []
        for item in installations: # installations 테이블 대신 deployments 테이블을 쿼리해야 함
            # 실제로 deployments 테이블을 쿼리하는 로직이 필요
            # 이 부분은 현재 컨텍스트와 무관하므로 수정하지 않음
            pass # Placeholder for actual deployments query

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
