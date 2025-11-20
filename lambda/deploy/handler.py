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
        try:
            user_id = event['requestContext']['authorizer']['lambda']['sub']
        except (KeyError, TypeError):
            try:
                user_id = event['requestContext']['authorizer']['userId']
            except (KeyError, TypeError):
                return _response(401, {'error': 'Unauthorized'})

        # 요청 본문 파싱
        body = json.loads(event['body'])
        repository_full_name = body.get('repositoryFullName')
        branch = body.get('branch', 'main')

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
        
        # repo_inspector에 전달할 페이로드
        invoke_payload = {
            'deploymentId': deployment_id,
            'userId': user_id,
            'installationId': installation_id,
            'repositoryFullName': repository_full_name,
            'branch': branch,
            'createdAt': timestamp,
            'updatedAt': timestamp
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
