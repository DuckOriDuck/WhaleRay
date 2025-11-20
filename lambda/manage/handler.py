import json
import os
import boto3
from boto3.dynamodb.conditions import Key
import decimal

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
            return _response(200, {'deployments': response.get('Items', [])})

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