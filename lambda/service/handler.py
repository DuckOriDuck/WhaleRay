import json
import os
import boto3
import decimal
from boto3.dynamodb.conditions import Key

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

SERVICES_TABLE = os.environ['SERVICES_TABLE']
DEPLOYMENTS_TABLE = os.environ['DEPLOYMENTS_TABLE']
FRONTEND_URL = os.environ.get('FRONTEND_URL', '*')

services_table = dynamodb.Table(SERVICES_TABLE)
deployments_table = dynamodb.Table(DEPLOYMENTS_TABLE)


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

    print(f"Determined route_key: {route_key}")
    path_params = event.get('pathParameters', {}) or {}

    if route_key == 'GET /services':
        print("Routing to _list_services")
        return _list_services(user_id)
    if route_key == 'GET /services/{serviceId}':
        print(f"Routing to _get_service with serviceId={path_params.get('serviceId')}")
        return _get_service(user_id, path_params.get('serviceId'))

    print(f"Route not found: {route_key}")
    return _response(404, {'error': 'Route not found'})


def _list_services(user_id):
    print(f"[_list_services] Starting query for user_id={user_id}")

    try:
        services_response = services_table.query(
            IndexName='userId-index',
            KeyConditionExpression=Key('userId').eq(user_id)
        )
        print(f"[_list_services] Query response: {json.dumps(services_response, cls=DecimalEncoder)}")

        services = services_response.get('Items', [])
        print(f"[_list_services] Found {len(services)} services")

        # 각 서비스의 최신 배포 상태를 가져옵니다.
        for idx, service in enumerate(services):
            service_id = service.get('serviceId')
            print(f"[_list_services] Processing service {idx+1}/{len(services)}: {service_id}")

            active_deployment_id = service.get('activeDeploymentId')
            if active_deployment_id:
                print(f"[_list_services] Fetching deployment: {active_deployment_id}")
                deployment_response = deployments_table.get_item(
                    Key={'deploymentId': active_deployment_id}
                )
                deployment = deployment_response.get('Item')
                if deployment:
                    service['status'] = deployment.get('status', 'UNKNOWN')
                    service['updatedAt'] = deployment.get('updatedAt')
                    print(f"[_list_services] Deployment found, status={service['status']}")
                else:
                    service['status'] = 'NO_DEPLOYMENT'
                    print(f"[_list_services] Deployment not found")
            else:
                service['status'] = 'NOT_DEPLOYED'
                print(f"[_list_services] No active deployment")

        print(f"[_list_services] Returning {len(services)} services")
        return _response(200, {'services': services})

    except Exception as e:
        print(f"[_list_services] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return _response(500, {'error': str(e)})

def _get_service(user_id, service_id):
    if not service_id:
        return _response(400, {'error': 'serviceId is required'})

    service_response = services_table.get_item(Key={'serviceId': service_id})
    service = service_response.get('Item')

    if not service or service.get('userId') != user_id:
        return _response(404, {'error': 'Service not found'})

    # 특정 서비스의 최근 배포 목록을 가져옵니다.
    deployments_response = deployments_table.query(
        IndexName='serviceId-createdAt-index', # 이 인덱스가 필요합니다.
        KeyConditionExpression=Key('serviceId').eq(service_id),
        ScanIndexForward=False, # 최신순으로 정렬
        Limit=10
    )

    return _response(200, {
        'service': service,
        'deployments': deployments_response.get('Items', [])
    })


def _response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': FRONTEND_URL,
            'Access-Control-Allow-Credentials': True
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }
