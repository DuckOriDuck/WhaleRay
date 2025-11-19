"""
Lambda Authorizer for JWT verification
API Gateway의 모든 보호된 엔드포인트에서 JWT 검증
"""
import json
import os
from datetime import datetime
import boto3

# PyJWT는 requirements.txt에 정의되어 Lambda Layer 또는 패키징에 포함
try:
    import jwt
except ImportError:
    print("WARNING: PyJWT not found. Install with: pip install PyJWT")
    jwt = None

secrets_manager = boto3.client('secretsmanager')

JWT_ALGORITHM = 'HS256'
JWT_SECRET_CACHE = {}


def handler(event, context):
    """
    API Gateway Lambda Authorizer
    JWT 토큰을 검증하고 IAM Policy 반환

    event 구조 (HTTP API Lambda Authorizer):
    {
        "type": "REQUEST",
        "methodArn": "arn:aws:execute-api:region:account:api-id/stage/method/path",
        "identitySource": ["Bearer <token>"],
        "headers": {...},
        "queryStringParameters": {...},
        "pathParameters": {...}
    }
    """

    print(f"Lambda Authorizer invoked: {json.dumps(event)}")

    # 1. Authorization 헤더에서 토큰 추출
    token = extract_token(event)

    if not token:
        print("No token provided")
        return generate_deny_policy('unauthorized', event['routeArn'])

    # 2. JWT 검증
    try:
        # Secrets Manager에서 JWT Secret 가져오기 (캐싱)
        jwt_secret = get_jwt_secret()

        # JWT 디코딩 및 검증
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={
                'verify_signature': True,
                'verify_exp': True,
                'verify_iat': True,
                'require': ['sub', 'exp', 'iat', 'iss']
            }
        )

        # Issuer 검증
        if payload.get('iss') != 'whaleray':
            print(f"Invalid issuer: {payload.get('iss')}")
            return generate_deny_policy('invalid_issuer', event['routeArn'])

        user_id = payload['sub']
        username = payload.get('username', '')

        print(f"Token verified for user: {user_id} ({username})")

        # 3. IAM Policy 생성 (Allow)
        return generate_allow_policy(
            user_id,
            event['routeArn'],
            context={
                'userId': user_id,
                'username': username
            }
        )

    except jwt.ExpiredSignatureError:
        print("Token expired")
        return generate_deny_policy('token_expired', event['routeArn'])

    except jwt.InvalidTokenError as e:
        print(f"Invalid token: {str(e)}")
        return generate_deny_policy('invalid_token', event['routeArn'])

    except Exception as e:
        print(f"Token verification error: {str(e)}")
        return generate_deny_policy('verification_error', event['routeArn'])


def extract_token(event):
    """
    Authorization 헤더 또는 identitySource에서 Bearer 토큰 추출

    HTTP API는 event.identitySource에 토큰이 들어옴
    """
    # identitySource 확인 (HTTP API Lambda Authorizer)
    identity_source = event.get('identitySource', [])
    if identity_source and len(identity_source) > 0:
        auth_header = identity_source[0]
        if auth_header and auth_header.startswith('Bearer '):
            return auth_header[7:]

    # headers 확인 (fallback)
    headers = event.get('headers', {})
    auth_header = headers.get('Authorization') or headers.get('authorization', '')

    if auth_header.startswith('Bearer '):
        return auth_header[7:]

    return None


def get_jwt_secret():
    """
    Secrets Manager에서 JWT Secret 가져오기 (캐싱)
    """
    secret_arn = os.environ['JWT_SECRET_ARN']

    # 캐시 확인
    if secret_arn in JWT_SECRET_CACHE:
        return JWT_SECRET_CACHE[secret_arn]

    # Secrets Manager에서 가져오기
    try:
        response = secrets_manager.get_secret_value(SecretId=secret_arn)
        jwt_secret = response['SecretString']

        # 캐시 저장 (Lambda warm start 시 재사용)
        JWT_SECRET_CACHE[secret_arn] = jwt_secret

        return jwt_secret

    except Exception as e:
        print(f"Failed to get JWT secret: {str(e)}")
        raise


def generate_allow_policy(principal_id, resource, context=None):
    """
    Allow IAM Policy 생성

    HTTP API Lambda Authorizer는 간단한 응답 형식 지원:
    {
        "isAuthorized": true,
        "context": {...}
    }
    """
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': 'Allow',
                    'Resource': resource
                }
            ]
        }
    }

    # Context 추가 (API Lambda에서 event.requestContext.authorizer로 접근 가능)
    if context:
        policy['context'] = context

    print(f"Generated ALLOW policy for: {principal_id}")
    return policy


def generate_deny_policy(principal_id, resource):
    """Deny IAM Policy 생성"""
    policy = {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': 'Deny',
                    'Resource': resource
                }
            ]
        }
    }

    print(f"Generated DENY policy for: {principal_id}")
    return policy
