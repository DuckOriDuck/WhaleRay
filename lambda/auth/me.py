"""
GET /me endpoint
사용자 정보 및 GitHub App installation 상태 확인
"""
import json
import os
import boto3

dynamodb = boto3.resource('dynamodb')

installations_table = dynamodb.Table(os.environ['INSTALLATIONS_TABLE'])


def handler(event, context):
    """
    GET /me

    Requires JWT authorization.

    Returns:
    - needInstallation: bool
    - installUrl: GitHub App installation URL
    - installations: list (if needInstallation is false)
    """

    # JWT authorizer에서 userId 추출
    print(f"Event received: {json.dumps(event)}")

    auth_ctx = event.get('requestContext', {}).get('authorizer', {}) or {}

    user_id = auth_ctx.get('userId')
    username = auth_ctx.get('username')

    # HTTP API의 Lambda authorizer 응답은 authorizer.lambda.<key>에 들어오는 경우가 있음
    lambda_ctx = auth_ctx.get('lambda', {}) or {}
    if not user_id:
        user_id = lambda_ctx.get('userId') or lambda_ctx.get('sub')
    if not username:
        username = lambda_ctx.get('username')

    if not user_id:
        print(f"Failed to extract userId. authorizer keys: {list(auth_ctx.keys())}")
        return {
            'statusCode': 401,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Unauthorized'})
        }

    print(f"Using authorizer context user_id={user_id}, username={username}")

    github_app_slug = os.environ.get('GITHUB_APP_SLUG', 'whaleray')
    install_url = f"https://github.com/apps/{github_app_slug}/installations/select_target"

    # userId로 installations 조회
    try:
        print(f"Querying installations for userId: {user_id}")
        response = installations_table.query(
            IndexName='userId-index',
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={
                ':userId': user_id
            }
        )

        installations = response.get('Items', [])
        # DynamoDB Numbers are Decimal; convert to string for safe logging
        print(f"Found {len(installations)} installations: {json.dumps(installations, default=str)}")

        if not installations:
            # installation이 없는 경우
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'needInstallation': True,
                    'installUrl': install_url
                })
            }

        # installation이 있는 경우
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'needInstallation': False,
                'installations': [
                    {
                        'installationId': item['installationId'],
                        'accountLogin': item.get('accountLogin', ''),
                        'accountType': item.get('accountType', 'User')
                    }
                    for item in installations
                ]
            })
        }

    except Exception as e:
        print(f"Failed to query installations: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Failed to check installation status',
                'installUrl': install_url
            })
        }
