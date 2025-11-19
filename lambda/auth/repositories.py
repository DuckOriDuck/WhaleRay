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

    # 2. Installations 테이블에서 사용자의 모든 설치 정보 조회
    try:
        response = installations_table.query(
            IndexName='userId-index',
            KeyConditionExpression='userId = :userId',
            ExpressionAttributeValues={
                ':userId': user_id
            }
        )
        installations = response.get('Items', [])
        print(f"Found {len(installations)} installation(s) for user {user_id}")

        if not installations:
            return _response(404, {'error': 'No GitHub App installation found for this user', 'repositories': []})

    except Exception as e:
        print(f"Failed to query installations: {str(e)}")
        return _response(500, {'error': 'Failed to query installations', 'repositories': []})

    # 3. 모든 installations에서 repositories 수집
    all_repositories = []
    installations_to_delete = []

    for installation in installations:
        installation_id = installation.get('installationId')
        account_login = installation.get('accountLogin', 'unknown')

        try:
            print(f"Fetching repositories for installation {installation_id} ({account_login})")

            # GitHub App JWT 생성
            app_jwt = _generate_github_app_jwt()

            # Installation Access Token 발급
            token_response = requests.post(
                f'https://api.github.com/app/installations/{installation_id}/access_tokens',
                headers={
                    'Authorization': f'Bearer {app_jwt}',
                    'Accept': 'application/vnd.github+json'
                },
                timeout=10
            )

            if token_response.status_code == 404:
                print(f"Installation {installation_id} not found (404) - marking for deletion")
                installations_to_delete.append(installation_id)
                continue
            elif token_response.status_code == 401:
                print(f"Installation {installation_id} unauthorized (401) - marking for deletion")
                installations_to_delete.append(installation_id)
                continue
            elif token_response.status_code >= 400:
                print(f"Failed to get access token for installation {installation_id}: {token_response.status_code} {token_response.text}")
                installations_to_delete.append(installation_id)
                continue

            token_data = token_response.json()
            access_token = token_data.get('token')

            if not access_token:
                print(f"No access token in response for installation {installation_id}")
                installations_to_delete.append(installation_id)
                continue

            # Installation의 repositories 조회
            repos_response = requests.get(
                'https://api.github.com/installation/repositories',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Accept': 'application/vnd.github+json'
                },
                timeout=10
            )

            if repos_response.status_code == 404 or repos_response.status_code == 401:
                print(f"Repository access failed for installation {installation_id} ({repos_response.status_code}) - marking for deletion")
                installations_to_delete.append(installation_id)
                continue
            elif repos_response.status_code >= 400:
                print(f"Failed to fetch repositories for installation {installation_id}: {repos_response.status_code}")
                continue

            repos_data = repos_response.json()
            repositories = repos_data.get('repositories', [])

            print(f"Found {len(repositories)} repositories for installation {installation_id}")

            # Repository 정보 정규화
            for repo in repositories:
                all_repositories.append({
                    'id': repo['id'],
                    'name': repo['name'],
                    'fullName': repo['full_name'],
                    'private': repo.get('private', False),
                    'defaultBranch': repo.get('default_branch', 'main'),
                    'language': repo.get('language'),
                    'description': repo.get('description'),
                    'owner': repo.get('owner', {}).get('login'),
                    'installationId': installation_id,
                    'accountLogin': account_login
                })

        except requests.exceptions.Timeout:
            print(f"Timeout fetching repositories for installation {installation_id}")
            continue
        except Exception as e:
            print(f"Error fetching repositories for installation {installation_id}: {str(e)}")
            continue

    # 4. 무효한 installations 삭제
    for installation_id in installations_to_delete:
        try:
            installations_table.delete_item(Key={'installationId': installation_id})
            print(f"Deleted invalid installation {installation_id} from DynamoDB")
        except Exception as e:
            print(f"Failed to delete installation {installation_id}: {str(e)}")

    # 5. 결과 반환
    print(f"Returning {len(all_repositories)} total repositories from {len(installations) - len(installations_to_delete)} valid installations")

    return _response(200, {'repositories': all_repositories})


def _generate_github_app_jwt():
    """
    GitHub App private key로 JWT 생성
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

    return jwt.encode(payload, private_key, algorithm='RS256')


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
