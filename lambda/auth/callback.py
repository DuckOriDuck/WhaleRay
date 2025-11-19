"""
GitHub App OAuth Callback Lambda
GitHub App 설치 후 OAuth 콜백을 처리하고 JWT 토큰 발급
"""
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote
import boto3
import requests

try:
    import jwt
except ImportError:
    print("WARNING: PyJWT not found. Install with: pip install PyJWT")
    jwt = None

dynamodb = boto3.resource('dynamodb')
secrets_manager = boto3.client('secretsmanager')

states_table = dynamodb.Table(os.environ['OAUTH_STATES_TABLE'])
users_table = dynamodb.Table(os.environ['USERS_TABLE'])
installations_table = dynamodb.Table(os.environ['INSTALLATIONS_TABLE'])

JWT_ALGORITHM = 'HS256'


def handler(event, context):
    """
    GET /auth/github/callback

    쿼리 파라미터:
    - code: GitHub Authorization Code
    - state: CSRF 방지용 state (OAuth만 필요)
    - installation_id: GitHub App Installation ID
    - setup_action: "install" or "update" (GitHub App 설치 콜백시)

    Returns:
    - 302 Redirect to frontend with JWT token (OAuth)
    - 302 Redirect to frontend with installation params (GitHub App 설치)
    """
    print(f"Callback received: {json.dumps(event)}")

    params = event.get('queryStringParameters') or {}
    
    # GitHub App installation callback 처리
    # setup_action이 있거나, installation_id는 있지만 state가 없으면 GitHub App 설치 콜백
    setup_action = params.get('setup_action')
    installation_id = params.get('installation_id')
    state = params.get('state')
    
    if setup_action or (installation_id and not state):
        print(f"GitHub App installation callback detected: installation_id={installation_id}, setup_action={setup_action}")
        redirect_url = f"{os.environ['FRONTEND_URL']}?installation_id={installation_id or ''}&setup_action={setup_action or 'install'}"
        return {
            'statusCode': 302,
            'headers': {
                'Location': redirect_url,
                'Cache-Control': 'no-store'
            },
            'body': ''
        }

    # OAuth 콜백 처리
    code = params.get('code')
    error = params.get('error')

    print(f"OAuth callback: code={bool(code)}, state={state}, installation_id={installation_id}, setup_action={setup_action}")

    # 1. 에러 처리
    if error:
        error_desc = params.get('error_description', error)
        print(f"GitHub OAuth error: {error_desc}")
        return redirect_with_error(f"GitHub OAuth error: {error_desc}")

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

        print(f"Access token obtained")

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
        print(f"GitHub user fetched: {github_user['login']} (ID: {github_user['id']})")

    except Exception as e:
        print(f"Failed to fetch user info: {str(e)}")
        return redirect_with_error(f"Failed to fetch user info: {str(e)}")

    # 5. GitHub App installations 조회
    try:
        print("Fetching user installations...")
        installations_response = requests.get(
            'https://api.github.com/user/installations',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/vnd.github+json'
            },
            timeout=10
        )

        if installations_response.status_code != 200:
            print(f"Failed to fetch installations: {installations_response.status_code}")
            installations_list = []
        else:
            installations_data = installations_response.json()
            installations_list = installations_data.get('installations', [])
            print(f"Found {len(installations_list)} installations")

    except Exception as e:
        print(f"Failed to fetch installations: {str(e)}")
        installations_list = []

    # GitHub 설치 완료 후 installation_id만 콜백 파라미터로 넘어오는 경우 보정
    if not installations_list and installation_id:
        print(f"No installations from API, but installation_id param provided: {installation_id}")
        # 최소 필드만 채워서 저장 가능하도록 구조 보정
        installations_list = [{
            'id': installation_id,
            'target_type': 'User',
            'account': {},
            'app_id': github_app_id or ''
        }]

    # 6. DynamoDB에 사용자 저장/업데이트
    user_id = f"github_{github_user['id']}"
    current_timestamp = int(time.time())

    try:
        # 기존 사용자 확인
        existing_user = users_table.get_item(Key={'userId': user_id})

        user_item = {
            'userId': user_id,
            'githubUserId': github_user['id'],
            'githubUsername': github_user['login'],
            'updatedAt': current_timestamp,
        }

        # 신규 사용자인 경우에만 createdAt 설정
        if 'Item' not in existing_user:
            user_item['createdAt'] = current_timestamp
            print(f"Creating new user: {user_id}")
        else:
            user_item['createdAt'] = existing_user['Item'].get('createdAt', current_timestamp)
            print(f"Updating existing user: {user_id}")

        users_table.put_item(Item=user_item)
        print(f"User saved to DynamoDB: {user_id}")

    except Exception as e:
        print(f"Failed to save user: {str(e)}")
        return redirect_with_error(f"Failed to save user: {str(e)}")

    # 7. Installations 저장/업데이트
    github_app_id = os.environ.get('GITHUB_APP_ID', '')

    for installation in installations_list:
        # 우리 앱의 installation만 저장
        if github_app_id and str(installation.get('app_id')) != str(github_app_id):
            continue

        try:
            install_id = str(installation['id'])
            account = installation.get('account', {}) or {}

            installation_item = {
                'installationId': install_id,
                'userId': user_id,
                'accountLogin': account.get('login', ''),
                'accountType': installation.get('target_type', 'User'),
                'createdAt': current_timestamp,
            }

            installations_table.put_item(Item=installation_item)
            print(f"Installation saved: {install_id} for {account.get('login')}")

        except Exception as e:
            print(f"Failed to save installation {installation.get('id')}: {str(e)}")

    # 8. JWT 토큰 생성
    try:
        jwt_token = generate_jwt(user_id, github_user['login'])
        print(f"JWT token generated for {github_user['login']}")
    except Exception as e:
        print(f"Failed to generate JWT: {str(e)}")
        return redirect_with_error(f"Failed to generate JWT: {str(e)}")

    # 9. 프론트엔드로 리다이렉트 (토큰 포함)
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
