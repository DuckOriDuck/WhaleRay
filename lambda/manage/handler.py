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
    try:
        # Cognito authorizer에서 userId 추출
        user_id = event['requestContext']['authorizer']['jwt']['claims']['sub']

        # 라우트 정보
        route_key = event['routeKey']
        path_params = event.get('pathParameters', {})
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
