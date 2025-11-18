import json
import os
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')

DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
SERVICES_TABLE = os.environ['SERVICES_TABLE']

deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)
services_table = dynamodb.Table(SERVICES_TABLE)


def handler(event, context):
    """
    서비스 및 배포 정보를 조회하는 Lambda 함수
    """
    print(f"Event received: {json.dumps(event)}")

    try:
        # Authorizer 컨텍스트에서 userId 추출 (Lambda authorizer or JWT authorizer 모두 대응)
        auth_ctx = event.get('requestContext', {}).get('authorizer', {}) or {}

        user_id = None
        # Lambda authorizer (our verify.py) puts values under authorizer.userId or authorizer.lambda.*
        user_id = auth_ctx.get('userId')
        if not user_id:
            lambda_ctx = auth_ctx.get('lambda', {}) or {}
            user_id = lambda_ctx.get('userId') or lambda_ctx.get('sub')

        # JWT (Cognito/HTTP API JWT) 형태 fallback
        if not user_id:
            jwt_ctx = auth_ctx.get('jwt', {}) or {}
            claims = jwt_ctx.get('claims', {}) or {}
            user_id = claims.get('sub')

        if not user_id:
            print(f"Unauthorized: userId not found in authorizer context: keys={list(auth_ctx.keys())}")
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Unauthorized'})
            }

        print(f"Using authorizer user_id={user_id}")

        # 라우트 정보 (HTTP API v2는 routeKey, REST 배포/호출 시에는 resource+path/httpMethod 조합)
        route_key = event.get('routeKey')
        if not route_key:
            method = event.get('httpMethod')
            path = event.get('resource') or event.get('path')
            if method and path:
                route_key = f"{method} {path}"
        path_params = event.get('pathParameters', {}) or {}
        query_params = event.get('queryStringParameters', {}) or {}

        # GET /services - 모든 서비스 조회
        if route_key == 'GET /services':
            response = services_table.query(
                IndexName='userId-index',
                KeyConditionExpression=Key('userId').eq(user_id)
            )

            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'services': response.get('Items', [])
                })
            }

        # GET /services/{serviceId} - 특정 서비스 조회
        elif route_key == 'GET /services/{serviceId}':
            service_id = path_params.get('serviceId')

            if not service_id:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'serviceId is required'})
                }

            # 서비스 정보 조회
            service_response = services_table.get_item(
                Key={'serviceId': service_id}
            )

            service = service_response.get('Item')

            if not service or service.get('userId') != user_id:
                return {
                    'statusCode': 404,
                    'body': json.dumps({'error': 'Service not found'})
                }

            # 해당 서비스의 배포 히스토리 조회
            deployments_response = deployments_table.query(
                IndexName='userId-index',
                KeyConditionExpression=Key('userId').eq(user_id),
                FilterExpression='serviceId = :serviceId',
                ExpressionAttributeValues={':serviceId': service_id},
                ScanIndexForward=False,  # 최신순 정렬
                Limit=10
            )

            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'service': service,
                    'deployments': deployments_response.get('Items', [])
                })
            }

        # GET /deployments - 모든 배포 조회
        elif route_key == 'GET /deployments':
            limit = int(query_params.get('limit', 20))

            response = deployments_table.query(
                IndexName='userId-index',
                KeyConditionExpression=Key('userId').eq(user_id),
                ScanIndexForward=False,  # 최신순 정렬
                Limit=limit
            )

            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'deployments': response.get('Items', [])
                })
            }

        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Route not found'})
            }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }
