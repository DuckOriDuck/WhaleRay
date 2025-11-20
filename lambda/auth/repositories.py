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

# Lambda Layer에서 공통 유틸리티 함수 가져오기
from github_utils import get_installation_access_token

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

    # 1. Installations 테이블에서 사용자의 모든 설치 정보 조회
    try:
        from boto3.dynamodb.conditions import Key
        response = installations_table.query(
            IndexName='userId-index',
            KeyConditionExpression=Key('userId').eq(user_id)
        )
        installations = response.get('Items', [])
        print(f"Found {len(installations)} installations for user {user_id}")

        if not installations:
            return _response(404, {'error': 'No GitHub App installation found for this user', 'repositories': []})

    except Exception as e:
        print(f"Failed to query installations: {str(e)}")
        return _response(500, {'error': 'Failed to query installations', 'repositories': []})

    # 2. 모든 installations에서 repositories 수집
    all_repositories = []
    installations_to_delete = []

    for installation in installations:
        installation_id = installation.get('installationId')
        account_login = installation.get('accountLogin', 'unknown')

        try:
            print(f"Fetching repositories for installation {installation_id} ({account_login})")

            # 레이어 함수를 사용하여 Installation Access Token 발급
            access_token = get_installation_access_token(
                installation_id=installation_id,
                github_app_id=os.environ['GITHUB_APP_ID'],
                private_key_secret_arn=os.environ['GITHUB_APP_PRIVATE_KEY_ARN']
            )

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
        except ValueError as e: # get_installation_access_token에서 발생 가능
            # 토큰 발급 실패 시 (e.g., 401, 404), 해당 installation을 삭제 목록에 추가
            print(f"Failed to get access token for installation {installation_id}: {str(e)}")
            if '401' in str(e) or '404' in str(e):
                installations_to_delete.append(installation_id)
            continue
        except Exception as e:
            print(f"Error fetching repositories for installation {installation_id}: {str(e)}")
            continue

    # 3. 무효한 installations 삭제
    for installation_id in installations_to_delete:
        try:
            installations_table.delete_item(Key={'installationId': installation_id})
            print(f"Deleted invalid installation {installation_id} from DynamoDB")
        except Exception as e:
            print(f"Failed to delete installation {installation_id}: {str(e)}")

    # 4. 결과 반환
    print(f"Returning {len(all_repositories)} total repositories from {len(installations) - len(installations_to_delete)} valid installations")

    return _response(200, {'repositories': all_repositories})


def _response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }