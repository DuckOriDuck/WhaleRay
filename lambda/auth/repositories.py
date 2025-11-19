"""
GET /github/repositories endpoint
GitHub App installation을 사용하여 사용자의 repositories 조회
"""
import json
import os
import time
from datetime import datetime, timedelta
import boto3
import requests

try:
    import jwt
except ImportError:
    print("WARNING: PyJWT not found")
    jwt = None

dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')

installations_table = dynamodb.Table(os.environ['INSTALLATIONS_TABLE'])


def handler(event, context):
    """
    GET /github/repositories

    Requires JWT authorization.

    Returns:
    - repositories: list of repository objects
    """

    print(f"Event received: {json.dumps(event)}")

    # JWT authorizer에서 userId 추출
    auth_ctx = event.get('requestContext', {}).get('authorizer', {}) or {}

    user_id = None
    # HTTP API Lambda authorizer can return both top-level and lambda.* contexts
    user_id = auth_ctx.get('userId')
    if not user_id:
        lambda_ctx = auth_ctx.get('lambda', {}) or {}
        user_id = lambda_ctx.get('userId') or lambda_ctx.get('sub')

    if not user_id:
        print("Unauthorized: userId not found in authorizer context")
        return _response(401, {'error': 'Unauthorized'})

    print(f"Using authorizer context user_id={user_id}")

    # userId로 installations 조회
    try:
        response = installations_table.query(
            IndexName='userId-index',
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={
                ':userId': user_id
            },
            Limit=1  # 첫 번째 installation만 사용
        )

        installations = response.get('Items', [])
        print(f"Found {len(installations)} installations for {user_id}: {json.dumps(installations, default=str)}")

        if not installations:
            return _response(404, {
                'error': 'No GitHub App installation found',
                'needInstallation': True
            })

        installation = installations[0]
        installation_id = installation['installationId']

    except Exception as e:
        print(f"Failed to query installations: {str(e)}")
        return _response(500, {'error': 'Failed to query installations'})

    # GitHub App installation access token 생성
    try:
        installation_token = get_installation_access_token(installation_id)
    except Exception as e:
        print(f"Failed to get installation token: {str(e)}")
        return _response(500, {
            'error': 'Failed to authenticate with GitHub',
            'details': str(e)
        })

    # GitHub API로 repositories 조회
    try:
        repos_response = requests.get(
            'https://api.github.com/installation/repositories',
            headers={
                'Authorization': f'Bearer {installation_token}',
                'Accept': 'application/vnd.github+json'
            },
            timeout=10
        )

        if repos_response.status_code != 200:
            print(f"GitHub API error: {repos_response.status_code} {repos_response.text}")
            return _response(502, {
                'error': 'Failed to fetch repositories from GitHub',
                'statusCode': repos_response.status_code
            })

        repos_data = repos_response.json()
        repositories = repos_data.get('repositories', [])

        # 필요한 정보만 추출
        simplified_repos = [
            {
                'id': repo['id'],
                'name': repo['name'],
                'fullName': repo['full_name'],
                'private': repo['private'],
                'defaultBranch': repo.get('default_branch', 'main'),
                'language': repo.get('language'),
                'description': repo.get('description', ''),
            }
            for repo in repositories
        ]

        return _response(200, {
            'repositories': simplified_repos,
            'totalCount': len(simplified_repos)
        })

    except requests.exceptions.Timeout:
        return _response(504, {'error': 'GitHub API timeout'})
    except Exception as e:
        print(f"Failed to fetch repositories: {str(e)}")
        return _response(500, {'error': f'Failed to fetch repositories: {str(e)}'})


def get_installation_access_token(installation_id):
    """
    GitHub App installation access token 생성

    1. GitHub App private key로 JWT 생성
    2. JWT를 사용하여 installation access token 요청
    """
    if not jwt:
        raise ImportError("PyJWT library not available")

    # Secrets Manager에서 GitHub App private key 가져오기
    secret_response = secrets_manager.get_secret_value(
        SecretId=os.environ['GITHUB_APP_PRIVATE_KEY_ARN']
    )
    private_key = secret_response['SecretString']

    github_app_id = os.environ['GITHUB_APP_ID']

    # GitHub App JWT 생성
    now = int(time.time())
    payload = {
        'iat': now - 60,  # 1분 전으로 설정 (clock skew 대응)
        'exp': now + 600,  # 10분 후 만료
        'iss': github_app_id
    }

    app_jwt = jwt.encode(payload, private_key, algorithm='RS256')

    # Installation access token 요청
    token_response = requests.post(
        f'https://api.github.com/app/installations/{installation_id}/access_tokens',
        headers={
            'Authorization': f'Bearer {app_jwt}',
            'Accept': 'application/vnd.github+json'
        },
        timeout=10
    )

    if token_response.status_code != 201:
        raise Exception(
            f"Failed to create installation token: {token_response.status_code} {token_response.text}"
        )

    token_data = token_response.json()
    return token_data['token']


def _response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }
