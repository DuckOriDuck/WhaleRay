"""
POST /deployments
GitHub App installation을 사용하여 repository 배포 시작
"""
import json
import os
import boto3
import time
from uuid import uuid4

dynamodb = boto3.resource('dynamodb')

DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
INSTALLATIONS_TABLE = os.environ['INSTALLATIONS_TABLE']

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

        # userId로 installations 조회
        response = installations_table.query(
            IndexName='userId-index',
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={
                ':userId': user_id
            },
            Limit=1
        )

        installations = response.get('Items', [])

        if not installations:
            return _response(404, {
                'error': 'No GitHub App installation found',
                'needInstallation': True
            })

        installation = installations[0]
        installation_id = installation['installationId']

        # Deployment ID 생성
        deployment_id = str(uuid4())
        timestamp = int(time.time())

        # DynamoDB에 배포 정보 저장
        deployments_table.put_item(Item={
            'deploymentId': deployment_id,
            'userId': user_id,
            'installationId': installation_id,
            'repositoryFullName': repository_full_name,
            'branch': branch,
            'status': 'PENDING',
            'createdAt': timestamp,
            'updatedAt': timestamp
        })

        # TODO: 실제 배포는 CodeBuild나 별도 Lambda에서 처리
        # EventBridge나 SQS로 배포 이벤트 전송 필요

        return _response(200, {
            'deploymentId': deployment_id,
            'status': 'PENDING'
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
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }
