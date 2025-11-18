import json
import os
import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')

SERVICES_TABLE = os.environ['SERVICES_TABLE']

services_table = dynamodb.Table(SERVICES_TABLE)


def handler(event, context):
    """
    서비스 조회 전용 Lambda
    - GET /services
    - GET /services/{serviceId}
    지원: HTTP API v2 (routeKey 존재)와 REST 형식(httpMethod/resource)
    """
    print(f"Event received: {json.dumps(event)}")

    # Authorizer 컨텍스트에서 userId 추출
    auth_ctx = event.get('requestContext', {}).get('authorizer', {}) or {}
    user_id = auth_ctx.get('userId')
    if not user_id:
        lambda_ctx = auth_ctx.get('lambda', {}) or {}
        user_id = lambda_ctx.get('userId') or lambda_ctx.get('sub')
    if not user_id:
        jwt_ctx = auth_ctx.get('jwt', {}) or {}
        claims = jwt_ctx.get('claims', {}) or {}
        user_id = claims.get('sub')

    if not user_id:
        print(f"Unauthorized: authorizer keys={list(auth_ctx.keys())}")
        return _response(401, {'error': 'Unauthorized'})

    print(f"Using authorizer user_id={user_id}")

    # route 결정
    route_key = event.get('routeKey')
    if not route_key:
        method = event.get('httpMethod')
        path = event.get('resource') or event.get('path')
        if method and path:
            route_key = f"{method} {path}"

    path_params = event.get('pathParameters', {}) or {}

    if route_key == 'GET /services':
        return _list_services(user_id)
    if route_key == 'GET /services/{serviceId}':
        return _get_service(user_id, path_params.get('serviceId'))

    return _response(404, {'error': 'Route not found'})


def _list_services(user_id):
    response = services_table.query(
        IndexName='userId-index',
        KeyConditionExpression=Key('userId').eq(user_id)
    )
    return _response(200, {'services': response.get('Items', [])})


def _get_service(user_id, service_id):
    if not service_id:
        return _response(400, {'error': 'serviceId is required'})

    service_response = services_table.get_item(Key={'serviceId': service_id})
    service = service_response.get('Item')

    if not service or service.get('userId') != user_id:
        return _response(404, {'error': 'Service not found'})

    return _response(200, {'service': service})


def _response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }
