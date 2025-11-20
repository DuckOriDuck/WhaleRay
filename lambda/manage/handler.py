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
SERVICES_TABLE = os.environ['SERVICES_TABLE']
FRONTEND_URL = os.environ.get('FRONTEND_URL', '*')

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)
services_table = dynamodb.Table(SERVICES_TABLE)


def _response(status_code, body):
    """중앙 집중식 응답 헬퍼"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': FRONTEND_URL
        },
        'body': json.dumps(body, cls=DecimalEncoder) # DecimalEncoder 사용
    }


def handler(event, context):
    """
    서비스 및 배포 정보를 조회하는 Lambda 함수
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
        path_params = event.get('pathParameters', {}) or {}
        query_params = event.get('queryStringParameters', {}) or {}

        # GET /services - 모든 서비스 조회
        if route_key == 'GET /services':
            response = services_table.query(
                IndexName='userId-index',
                KeyConditionExpression=Key('userId').eq(user_id)
            )
            return _response(200, {'services': response.get('Items', [])})

        # GET /services/{serviceId} - 특정 서비스 조회
        elif route_key == 'GET /services/{serviceId}':
            service_id = path_params.get('serviceId')
            if not service_id:
                return _response(400, {'error': 'serviceId is required'})

            service_response = services_table.get_item(Key={'serviceId': service_id})
            service = service_response.get('Item')

            if not service or service.get('userId') != user_id:
                return _response(404, {'error': 'Service not found'})

            deployments_response = deployments_table.query(
                IndexName='userId-index',
                KeyConditionExpression=Key('userId').eq(user_id),
                FilterExpression='serviceId = :serviceId',
                ExpressionAttributeValues={':serviceId': service_id},
                ScanIndexForward=False,
                Limit=10
            )
            
            return _response(200, {
                'service': service,
                'deployments': deployments_response.get('Items', [])
            })

        # GET /deployments - 모든 배포 조회
        elif route_key == 'GET /deployments':
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
        return _response(500, {
            'error': 'Internal server error',
            'message': str(e)
        })


def cleanup_orphan_deployments(deployments: list) -> list:
    """
    주어진 배포 목록에서 30분 이상 진행중인 orphan deployment resource를 찾아 상태를 업데이트하고,
    업데이트된 목록을 반환합.
    """
    print(f"Starting cleanup of orphan deployments for {len(deployments)} items...")
    try:
        timeout_threshold = int(time.time()) - 1800  # 30분 전
        in_progress_statuses = ['INSPECTING', 'BUILDING', 'DEPLOYING']
        
        for item in deployments:
            current_status = item.get('status')
            updated_at = item.get('updatedAt', 0)
            
            if current_status in in_progress_statuses and updated_at < timeout_threshold:
                deployment_id = item['deploymentId']
                new_status = f"{current_status}_TIMEOUT"
                print(f"Found orphan deployment: {deployment_id}. Current status: {current_status}. Updating to {new_status}.")
                
                # DynamoDB의 상태를 업데이트.
                update_deployment_status(DEPLOYMENTS_TABLE, deployment_id, new_status)
                # 메모리에 있는 목록의 상태도 즉시 업데이트합니다.
                item['status'] = new_status
        
        return deployments

    except Exception as e:
        print(f"An error occurred during orphan deployment cleanup: {str(e)}")
        return deployments # 오류가 발생하더라도 원본 목록을 반환합니다.