"""
GitHub App Authorization Start
GitHub App 설치 플로우를 시작하고 installation 선택 페이지로 리다이렉트
"""
import json
import uuid
import os
import time
from urllib.parse import urlencode
import boto3

dynamodb = boto3.resource('dynamodb')
states_table = dynamodb.Table(os.environ['OAUTH_STATES_TABLE'])


def handler(event, context):
    """
    GET /auth/github/start

    쿼리 파라미터:
    - redirect_uri: 인증 후 돌아갈 프론트엔드 URL (선택사항)

    Returns:
    - 302 Redirect to GitHub App installation page with OAuth
    """

    # 1. State 생성 (CSRF 방지)
    state = str(uuid.uuid4())

    # 2. Redirect URI 결정
    params = event.get('queryStringParameters') or {}
    redirect_uri = params.get('redirect_uri', os.environ['FRONTEND_URL'])

    # 3. DynamoDB에 state 저장
    try:
        current_time = int(time.time())
        states_table.put_item(
            Item={
                'state': state,
                'createdAt': current_time,
                'expiresAt': current_time + 600,  # 10분 TTL
                'redirectUri': redirect_uri
            }
        )
        print(f"Created OAuth state: {state}")
    except Exception as e:
        print(f"Failed to save state: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to initialize OAuth flow'})
        }

    # 4. GitHub OAuth URL 생성 (앱 설치 여부와 무관하게 사용자 인증/동의 획득)
    github_oauth_params = {
        'client_id': os.environ['GITHUB_CLIENT_ID'],
        'redirect_uri': os.environ['GITHUB_CALLBACK_URL'],
        'scope': 'repo read:user user:email',
        'state': state,
        'allow_signup': 'true'
    }

    github_oauth_url = 'https://github.com/login/oauth/authorize?' + urlencode(github_oauth_params)

    print(f"Redirecting to GitHub OAuth authorize: {github_oauth_url}")

    # 5. GitHub OAuth 페이지로 리다이렉트
    return {
        'statusCode': 302,
        'headers': {
            'Location': github_oauth_url,
            'Cache-Control': 'no-store'
        },
        'body': ''
    }
