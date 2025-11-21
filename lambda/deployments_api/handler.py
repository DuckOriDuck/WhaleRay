import json
import os
import boto3
from boto3.dynamodb.conditions import Key
import decimal
import time

# Lambda Layer에서 공통 유틸리티 함수 가져오기
from github_utils import update_deployment_status

# --- Helper for JSON serialization ---
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)
# -------------------------------------

dynamodb = boto3.resource('dynamodb')

# 환경 변수
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
FRONTEND_URL = os.environ.get('FRONTEND_URL', '*')

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)


def _response(status_code, body):
    """중앙 집중식 응답 헬퍼"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': FRONTEND_URL
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }


def handler(event, context):
    """
    배포 정보를 조회하는 Lambda 함수
    """
    print(f"Event received: {json.dumps(event)}")

    try:
        # Authorizer 컨텍스트에서 userId 추출
        auth_ctx = event.get('requestContext', {}).get('authorizer', {}) or {}
        user_id = None
        lambda_ctx = auth_ctx.get('lambda', {}) or {}
        user_id = lambda_ctx.get('userId') or lambda_ctx.get('sub')

        if not user_id:
            return _response(401, {'error': 'Unauthorized'})

        print(f"Using authorizer user_id={user_id}")

        route_key = event.get('routeKey')
        query_params = event.get('queryStringParameters', {}) or {}

        # GET /deployments - 모든 배포 조회
        if route_key == 'GET /deployments':
            limit = int(query_params.get('limit', 20))

            response = deployments_table.query(
                IndexName='userId-index',
                KeyConditionExpression=Key('userId').eq(user_id),
                ScanIndexForward=False,
                Limit=limit
            )
            deployments = response.get('Items', [])

            updated_deployments = cleanup_orphan_deployments(deployments)
            return _response(200, {'deployments': updated_deployments})

        else:
            return _response(404, {'error': 'Route not found'})

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return _response(500, {'error': 'Internal server error', 'message': str(e)})


def cleanup_orphan_deployments(deployments: list) -> list:
    """
    주어진 배포 목록에서 30분 이상 진행중인 orphan deployment를 찾아 상태를 업데이트하고,
    업데이트된 목록을 반환합니다.
    """
    timeout_threshold = int(time.time()) - 1800  # 30분 전
    in_progress_statuses = ['INSPECTING', 'BUILDING', 'DEPLOYING']
    
    for item in deployments:
        if item.get('status') in in_progress_statuses and item.get('updatedAt', 0) < timeout_threshold:
            deployment_id = item['deploymentId']
            new_status = f"{item['status']}_TIMEOUT"
            print(f"Found orphan deployment: {deployment_id}. Updating to {new_status}.")
            
            update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, new_status)
            item['status'] = new_status
    
    return deployments