"""
GitHub OAuth Callback Lambda
GitHub OAuth 콜백을 처리하고 JWT 토큰 발급
"""
import json
import os
import time
import base64
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote
import boto3
import requests

# PyJWT는 requirements.txt에 정의되어 Lambda Layer 또는 패키징에 포함
try:
    import jwt
except ImportError:
    print("WARNING: PyJWT not found. Install with: pip install PyJWT")
    jwt = None

dynamodb = boto3.resource('dynamodb')
kms = boto3.client('kms')
secrets_manager = boto3.client('secretsmanager')

states_table = dynamodb.Table(os.environ['OAUTH_STATES_TABLE'])
users_table = dynamodb.Table(os.environ['USERS_TABLE'])

JWT_ALGORITHM = 'HS256'


def handler(event, context):
    """
    GET /auth/github/callback

    쿼리 파라미터:
    - code: GitHub Authorization Code
    - state: CSRF 방지용 state

    Returns:
    - 302 Redirect to frontend with JWT token
    """

    params = event.get('queryStringParameters') or {}
    code = params.get('code')
    state = params.get('state')
    installation_id = params.get('installation_id')
    error = params.get('error')

    # 1. 에러 처리
    if error:
        error_desc = params.get('error_description', error)
        print(f"GitHub OAuth error: {error_desc}")
        return redirect_with_error(f"GitHub OAuth error: {error_desc}")

    # GitHub App 설치 완료 후 setup URL을 통해 installation_id만 돌아오는 경우 처리
    if not code and not state and installation_id:
        print(f"Installation callback without code/state. installation_id={installation_id}")
        return {
            'statusCode': 302,
            'headers': {
                'Location': f"{os.environ.get('FRONTEND_URL', '/')}?github=installed",
                'Cache-Control': 'no-store'
            },
            'body': ''
        }

    if not code or not state:
        return redirect_with_error("Missing code or state parameter")

    # 2. State 검증
    try:
        state_item = states_table.get_item(Key={'state': state})
        if 'Item' not in state_item:
            print(f"Invalid or expired state: {state}")
            return redirect_with_error("Invalid or expired state. Please try again.")

        redirect_uri = state_item['Item']['redirectUri']

        # State 사용 후 즉시 삭제
        states_table.delete_item(Key={'state': state})
        print(f"State validated and deleted: {state}")

    except Exception as e:
        print(f"State validation error: {str(e)}")
        return redirect_with_error(f"State validation failed: {str(e)}")

    # 3. Access Token 교환
    try:
        print("Exchanging code for access token...")
        token_response = requests.post(
            'https://github.com/login/oauth/access_token',
            headers={'Accept': 'application/json'},
            data={
                'client_id': os.environ['GITHUB_CLIENT_ID'],
                'client_secret': os.environ['GITHUB_CLIENT_SECRET'],
                'code': code,
                'redirect_uri': os.environ['GITHUB_CALLBACK_URL']
            },
            timeout=10
        )

        token_data = token_response.json()

        if 'error' in token_data:
            error_msg = token_data.get('error_description', token_data['error'])
            print(f"Token exchange failed: {error_msg}")
            return redirect_with_error(f"Token exchange failed: {error_msg}")

        access_token = token_data.get('access_token')
        if not access_token:
            print(f"No access token in response: {token_data}")
            return redirect_with_error("Failed to get access token from GitHub")

        scopes = token_data.get('scope', '').split(',') if token_data.get('scope') else []
        print(f"Access token obtained with scopes: {scopes}")

    except requests.exceptions.Timeout:
        print("GitHub API timeout")
        return redirect_with_error("GitHub API timeout. Please try again.")
    except Exception as e:
        print(f"Failed to exchange code: {str(e)}")
        return redirect_with_error(f"Failed to exchange code: {str(e)}")

    # 4. GitHub 사용자 정보 조회
    try:
        print("Fetching GitHub user info...")
        user_response = requests.get(
            'https://api.github.com/user',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )

        if user_response.status_code != 200:
            print(f"Failed to fetch user info: {user_response.status_code} {user_response.text}")
            return redirect_with_error("Failed to fetch user info from GitHub")

        github_user = user_response.json()

        # 이메일 정보도 가져오기 (primary email)
        emails_response = requests.get(
            'https://api.github.com/user/emails',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )

        primary_email = github_user.get('email')
        if emails_response.status_code == 200:
            emails = emails_response.json()
            primary_email = next(
                (e['email'] for e in emails if e.get('primary')),
                primary_email
            )

        print(f"GitHub user fetched: {github_user['login']} (ID: {github_user['id']})")

    except Exception as e:
        print(f"Failed to fetch user info: {str(e)}")
        return redirect_with_error(f"Failed to fetch user info: {str(e)}")

    # 5. GitHub Token 암호화
    try:
        encrypted_token = encrypt_token(access_token)
        print("GitHub token encrypted successfully")
    except Exception as e:
        print(f"Failed to encrypt token: {str(e)}")
        return redirect_with_error(f"Failed to encrypt token: {str(e)}")

    # 6. DynamoDB에 사용자 저장/업데이트
    user_id = f"github_{github_user['id']}"
    now = datetime.utcnow().isoformat() + 'Z'

    try:
        # 기존 사용자 확인
        existing_user = users_table.get_item(Key={'userId': user_id})

        user_item = {
            'userId': user_id,
            'githubId': github_user['id'],
            'githubUsername': github_user['login'],
            'githubEmail': primary_email,
            'githubAvatarUrl': github_user.get('avatar_url', ''),
            'githubToken': encrypted_token,
            'githubScopes': scopes,
            'lastLoginAt': now,
            'updatedAt': now,
        }

        # 신규 사용자인 경우에만 createdAt 설정
        if 'Item' not in existing_user:
            user_item['createdAt'] = now
            print(f"Creating new user: {user_id}")
        else:
            user_item['createdAt'] = existing_user['Item'].get('createdAt', now)
            print(f"Updating existing user: {user_id}")

        users_table.put_item(Item=user_item)
        print(f"User saved to DynamoDB: {user_id}")

    except Exception as e:
        print(f"Failed to save user: {str(e)}")
        return redirect_with_error(f"Failed to save user: {str(e)}")

    # 7. JWT 토큰 생성
    try:
        jwt_token = generate_jwt(user_id, github_user['login'])
        print(f"JWT token generated for {github_user['login']}")
    except Exception as e:
        print(f"Failed to generate JWT: {str(e)}")
        return redirect_with_error(f"Failed to generate JWT: {str(e)}")

    # 8. 프론트엔드로 리다이렉트 (토큰 포함)
    redirect_url = f'{redirect_uri}?token={jwt_token}&username={quote(github_user["login"])}'

    print(f"Redirecting to: {redirect_url}")

    return {
        'statusCode': 302,
        'headers': {
            'Location': redirect_url,
            'Cache-Control': 'no-store'
        },
        'body': ''
    }


def encrypt_token(token):
    """KMS로 토큰 암호화"""
    result = kms.encrypt(
        KeyId=os.environ['KMS_KEY_ID'],
        Plaintext=token.encode()
    )
    # Base64 인코딩하여 DynamoDB에 저장
    return base64.b64encode(result['CiphertextBlob']).decode()


def generate_jwt(user_id, username):
    """JWT 토큰 생성"""
    if not jwt:
        raise ImportError("PyJWT library not available")

    # Secrets Manager에서 JWT Secret 가져오기
    secret_response = secrets_manager.get_secret_value(
        SecretId=os.environ['JWT_SECRET_ARN']
    )
    jwt_secret = secret_response['SecretString']

    payload = {
        'sub': user_id,
        'username': username,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(days=7),  # 7일 유효
        'iss': 'whaleray',
        'jti': str(uuid.uuid4())  # JWT ID (revocation용)
    }

    return jwt.encode(payload, jwt_secret, algorithm=JWT_ALGORITHM)


def redirect_with_error(error_message):
    """에러와 함께 프론트엔드로 리다이렉트"""
    redirect_url = f"{os.environ['FRONTEND_URL']}?error={quote(error_message)}"
    return {
        'statusCode': 302,
        'headers': {
            'Location': redirect_url,
            'Cache-Control': 'no-store'
        },
        'body': ''
    }
