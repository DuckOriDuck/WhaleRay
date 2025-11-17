# WhaleRay 인증 시스템 설계 (GitHub OAuth Only)

## 개요
Cognito 없이 **GitHub OAuth + DynamoDB + JWT**로 완전한 커스텀 인증 시스템 구축

## 왜 이 방식이 더 나은가?

### WhaleRay 서비스 특성
1. **GitHub 리포지토리 배포**가 핵심 기능
2. 모든 사용자가 GitHub 계정 필요
3. Private repo 접근 위해 어차피 GitHub Token 필요
4. Cognito는 불필요한 복잡도만 추가

### 장점
- ✅ 단순한 인증 플로우 (GitHub 로그인 1번만)
- ✅ 외부 의존성 제거 (Cognito 불필요)
- ✅ 완전한 제어권 (커스텀 로직 자유롭게)
- ✅ 비용 절감 (Cognito MAU 비용 없음)
- ✅ GitHub Token을 인증과 리포지토리 접근 모두에 사용

---

## 아키텍처

```
┌──────────┐
│  사용자  │
└────┬─────┘
     │
     ├─── 1. "Login with GitHub" 버튼 클릭
     │    └─> Lambda: auth/github/authorize
     │         └─> GitHub OAuth URL 생성 및 리다이렉트
     │
     ├─── 2. GitHub에서 권한 승인
     │    └─> GitHub가 콜백 URL로 리다이렉트 (code 포함)
     │
     ├─── 3. Lambda: auth/github/callback
     │    ├─> Code를 Access Token으로 교환
     │    ├─> GitHub API로 사용자 정보 조회
     │    ├─> DynamoDB에 사용자 저장/업데이트
     │    └─> JWT 토큰 생성 및 반환
     │
     └─── 4. 이후 모든 API 요청
          └─> Header: Authorization: Bearer <JWT>
               └─> Lambda Authorizer가 JWT 검증
                    └─> userId를 API Lambda로 전달
```

---

## 1. DynamoDB 스키마

### Users 테이블
```python
{
  "userId": "github_12345678",           # PK - github_{github_user_id}

  # GitHub 정보
  "githubId": 12345678,                  # GitHub User ID (숫자)
  "githubUsername": "oriduckduck",       # GitHub 사용자명
  "githubEmail": "user@example.com",     # GitHub 이메일
  "githubAvatarUrl": "https://...",      # 프로필 이미지

  # GitHub Access Token (암호화)
  "githubToken": "encrypted:gho_xxx",    # KMS로 암호화된 토큰
  "githubScopes": ["repo", "read:user"], # 부여받은 권한

  # 메타데이터
  "createdAt": "2025-01-01T00:00:00Z",
  "lastLoginAt": "2025-01-01T00:00:00Z",
  "updatedAt": "2025-01-01T00:00:00Z"
}
```

### Sessions 테이블 (선택사항 - JWT만으로 충분하면 불필요)
```python
{
  "sessionId": "uuid-xxx",               # PK
  "userId": "github_12345678",           # GSI
  "jti": "jwt-token-id",                 # JWT ID (revocation용)
  "expiresAt": 1234567890,               # TTL
  "createdAt": "2025-01-01T00:00:00Z"
}
```

### OAuthStates 테이블 (CSRF 방지)
```python
{
  "state": "random-uuid-xxx",            # PK
  "createdAt": 1234567890,
  "expiresAt": 1234567890,               # TTL - 10분
  "redirectUri": "https://whaleray.oriduckduck.site"
}
```

---

## 2. Lambda 함수 구현

### A. `auth_github_authorize` - OAuth 시작

**경로**: `GET /auth/github/authorize`
**인증**: 불필요 (공개)

```python
# lambda/auth/github/authorize.py
import json
import uuid
import os
import time
from urllib.parse import urlencode
import boto3

dynamodb = boto3.resource('dynamodb')
states_table = dynamodb.Table(os.environ['OAUTH_STATES_TABLE'])

def handler(event, context):
    # 1. State 생성 (CSRF 방지)
    state = str(uuid.uuid4())

    # 2. Redirect URI 결정 (쿼리 파라미터에서 가져오거나 기본값)
    params = event.get('queryStringParameters', {}) or {}
    redirect_uri = params.get('redirect_uri', os.environ['FRONTEND_URL'])

    # 3. DynamoDB에 state 저장
    states_table.put_item(
        Item={
            'state': state,
            'createdAt': int(time.time()),
            'expiresAt': int(time.time()) + 600,  # 10분 TTL
            'redirectUri': redirect_uri
        }
    )

    # 4. GitHub OAuth URL 생성
    github_oauth_url = 'https://github.com/login/oauth/authorize?' + urlencode({
        'client_id': os.environ['GITHUB_CLIENT_ID'],
        'redirect_uri': os.environ['GITHUB_CALLBACK_URL'],
        'scope': 'repo read:user user:email',
        'state': state,
        'allow_signup': 'true'
    })

    # 5. 리다이렉트
    return {
        'statusCode': 302,
        'headers': {
            'Location': github_oauth_url
        }
    }
```

### B. `auth_github_callback` - OAuth 콜백 처리

**경로**: `GET /auth/github/callback`
**인증**: 불필요 (GitHub에서 리다이렉트)

```python
# lambda/auth/github/callback.py
import json
import os
import time
import jwt
import boto3
import requests
from datetime import datetime, timedelta

dynamodb = boto3.resource('dynamodb')
kms = boto3.client('kms')

states_table = dynamodb.Table(os.environ['OAUTH_STATES_TABLE'])
users_table = dynamodb.Table(os.environ['USERS_TABLE'])

JWT_SECRET = os.environ['JWT_SECRET']  # Secrets Manager에서 가져오기
JWT_ALGORITHM = 'HS256'

def handler(event, context):
    params = event['queryStringParameters']
    code = params.get('code')
    state = params.get('state')
    error = params.get('error')

    # 1. 에러 처리
    if error:
        return redirect_with_error(f"GitHub OAuth error: {error}")

    # 2. State 검증
    try:
        state_item = states_table.get_item(Key={'state': state})
        if 'Item' not in state_item:
            return redirect_with_error("Invalid or expired state")

        redirect_uri = state_item['Item']['redirectUri']
        states_table.delete_item(Key={'state': state})
    except Exception as e:
        return redirect_with_error(f"State validation failed: {str(e)}")

    # 3. Access Token 교환
    try:
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
            return redirect_with_error(f"Token exchange failed: {token_data['error_description']}")

        access_token = token_data['access_token']
        scopes = token_data.get('scope', '').split(',')

    except Exception as e:
        return redirect_with_error(f"Failed to exchange code: {str(e)}")

    # 4. GitHub 사용자 정보 조회
    try:
        user_response = requests.get(
            'https://api.github.com/user',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        github_user = user_response.json()

        # 이메일 정보도 가져오기 (primary email)
        emails_response = requests.get(
            'https://api.github.com/user/emails',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        emails = emails_response.json()
        primary_email = next(
            (e['email'] for e in emails if e['primary']),
            github_user.get('email')
        )

    except Exception as e:
        return redirect_with_error(f"Failed to fetch user info: {str(e)}")

    # 5. GitHub Token 암호화
    encrypted_token = encrypt_token(access_token)

    # 6. DynamoDB에 사용자 저장/업데이트
    user_id = f"github_{github_user['id']}"
    now = datetime.utcnow().isoformat() + 'Z'

    users_table.put_item(
        Item={
            'userId': user_id,
            'githubId': github_user['id'],
            'githubUsername': github_user['login'],
            'githubEmail': primary_email,
            'githubAvatarUrl': github_user['avatar_url'],
            'githubToken': encrypted_token,
            'githubScopes': scopes,
            'lastLoginAt': now,
            'updatedAt': now,
            # createdAt는 존재하지 않을 때만 설정 (attribute_not_exists 사용)
        },
        ConditionExpression='attribute_not_exists(userId) OR attribute_exists(userId)'
    )

    # createdAt 설정 (신규 사용자인 경우)
    try:
        users_table.update_item(
            Key={'userId': user_id},
            UpdateExpression='SET createdAt = if_not_exists(createdAt, :now)',
            ExpressionAttributeValues={':now': now}
        )
    except:
        pass

    # 7. JWT 토큰 생성
    jwt_token = generate_jwt(user_id, github_user['login'])

    # 8. 프론트엔드로 리다이렉트 (토큰 포함)
    return {
        'statusCode': 302,
        'headers': {
            'Location': f'{redirect_uri}?token={jwt_token}&username={github_user["login"]}'
        }
    }


def encrypt_token(token):
    """KMS로 토큰 암호화"""
    result = kms.encrypt(
        KeyId=os.environ['KMS_KEY_ID'],
        Plaintext=token.encode()
    )
    # Base64 인코딩하여 DynamoDB에 저장
    import base64
    return base64.b64encode(result['CiphertextBlob']).decode()


def generate_jwt(user_id, username):
    """JWT 토큰 생성"""
    payload = {
        'sub': user_id,
        'username': username,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(days=7),  # 7일 유효
        'iss': 'whaleray',
        'jti': str(uuid.uuid4())  # JWT ID (revocation용)
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def redirect_with_error(error_message):
    """에러와 함께 프론트엔드로 리다이렉트"""
    from urllib.parse import quote
    return {
        'statusCode': 302,
        'headers': {
            'Location': f"{os.environ['FRONTEND_URL']}?error={quote(error_message)}"
        }
    }
```

### C. `auth_verify` - JWT 검증 (Lambda Authorizer)

**API Gateway Lambda Authorizer**

```python
# lambda/auth/verify.py
import json
import os
import jwt
from datetime import datetime

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = 'HS256'

def handler(event, context):
    """
    API Gateway Lambda Authorizer
    JWT 토큰을 검증하고 사용자 정보를 반환
    """

    # 1. Authorization 헤더에서 토큰 추출
    token = extract_token(event)

    if not token:
        return generate_policy(None, 'Deny', event['methodArn'])

    # 2. JWT 검증
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={
                'verify_signature': True,
                'verify_exp': True,
                'verify_iat': True,
                'require': ['sub', 'exp', 'iat']
            }
        )

        user_id = payload['sub']
        username = payload.get('username', '')

        # 3. IAM Policy 생성 (Allow)
        return generate_policy(
            user_id,
            'Allow',
            event['methodArn'],
            context={
                'userId': user_id,
                'username': username
            }
        )

    except jwt.ExpiredSignatureError:
        print("Token expired")
        return generate_policy(None, 'Deny', event['methodArn'])
    except jwt.InvalidTokenError as e:
        print(f"Invalid token: {str(e)}")
        return generate_policy(None, 'Deny', event['methodArn'])


def extract_token(event):
    """Authorization 헤더에서 Bearer 토큰 추출"""
    auth_header = event.get('headers', {}).get('Authorization', '')

    if not auth_header:
        auth_header = event.get('headers', {}).get('authorization', '')

    if auth_header.startswith('Bearer '):
        return auth_header[7:]

    return None


def generate_policy(principal_id, effect, resource, context=None):
    """IAM Policy 생성"""
    policy = {
        'principalId': principal_id or 'user',
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        }
    }

    # Context 추가 (API Lambda에서 event.requestContext.authorizer에서 접근 가능)
    if context:
        policy['context'] = context

    return policy
```

### D. `auth_logout` - 로그아웃 (선택사항)

**경로**: `POST /auth/logout`
**인증**: JWT 필요

```python
# lambda/auth/logout.py
def handler(event, context):
    """
    JWT는 stateless이므로 서버에서 강제로 무효화 불가능
    프론트엔드에서 토큰 삭제하는 것으로 충분

    만약 토큰 revocation이 필요하면:
    1. Sessions 테이블에 JTI 저장
    2. Lambda Authorizer에서 JTI 블랙리스트 확인
    """

    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Logged out successfully'})
    }
```

---

## 3. Terraform 구성

### A. DynamoDB 테이블

```hcl
# terraform/dynamodb.tf

# Users 테이블
resource "aws_dynamodb_table" "users" {
  name           = "${var.project_name}-users"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "userId"

  attribute {
    name = "userId"
    type = "S"
  }

  attribute {
    name = "githubUsername"
    type = "S"
  }

  # GSI: GitHub 사용자명으로 검색
  global_secondary_index {
    name            = "GithubUsernameIndex"
    hash_key        = "githubUsername"
    projection_type = "ALL"
  }

  tags = {
    Name = "${var.project_name}-users"
  }
}

# OAuth States 테이블
resource "aws_dynamodb_table" "oauth_states" {
  name           = "${var.project_name}-oauth-states"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "state"

  attribute {
    name = "state"
    type = "S"
  }

  # TTL 설정 (10분 후 자동 삭제)
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-oauth-states"
  }
}
```

### B. KMS Key (토큰 암호화)

```hcl
# terraform/kms.tf

resource "aws_kms_key" "github_tokens" {
  description             = "Encryption key for GitHub access tokens"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = {
    Name = "${var.project_name}-github-tokens"
  }
}

resource "aws_kms_alias" "github_tokens" {
  name          = "alias/${var.project_name}-github-tokens"
  target_key_id = aws_kms_key.github_tokens.key_id
}
```

### C. Secrets Manager (JWT Secret)

```hcl
# terraform/secrets.tf

resource "aws_secretsmanager_secret" "jwt_secret" {
  name = "${var.project_name}/jwt-secret"

  tags = {
    Name = "${var.project_name}-jwt-secret"
  }
}

resource "aws_secretsmanager_secret_version" "jwt_secret" {
  secret_id     = aws_secretsmanager_secret.jwt_secret.id
  secret_string = random_password.jwt_secret.result
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}
```

### D. Lambda 함수

```hcl
# terraform/auth-lambda.tf

# GitHub OAuth Authorize
resource "aws_lambda_function" "auth_github_authorize" {
  filename         = data.archive_file.auth_lambda.output_path
  function_name    = "${var.project_name}-auth-github-authorize"
  role            = aws_iam_role.lambda_auth.arn
  handler         = "authorize.handler"
  runtime         = "python3.11"
  timeout         = 30

  environment {
    variables = {
      OAUTH_STATES_TABLE   = aws_dynamodb_table.oauth_states.name
      GITHUB_CLIENT_ID     = var.github_client_id
      GITHUB_CALLBACK_URL  = "https://api.${var.domain_name}/auth/github/callback"
      FRONTEND_URL         = "https://${var.domain_name}"
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256
}

# GitHub OAuth Callback
resource "aws_lambda_function" "auth_github_callback" {
  filename         = data.archive_file.auth_lambda.output_path
  function_name    = "${var.project_name}-auth-github-callback"
  role            = aws_iam_role.lambda_auth.arn
  handler         = "callback.handler"
  runtime         = "python3.11"
  timeout         = 30

  environment {
    variables = {
      OAUTH_STATES_TABLE   = aws_dynamodb_table.oauth_states.name
      USERS_TABLE          = aws_dynamodb_table.users.name
      GITHUB_CLIENT_ID     = var.github_client_id
      GITHUB_CLIENT_SECRET = var.github_client_secret
      GITHUB_CALLBACK_URL  = "https://api.${var.domain_name}/auth/github/callback"
      FRONTEND_URL         = "https://${var.domain_name}"
      KMS_KEY_ID          = aws_kms_key.github_tokens.id
      JWT_SECRET_ARN      = aws_secretsmanager_secret.jwt_secret.arn
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256
}

# Lambda Authorizer (JWT 검증)
resource "aws_lambda_function" "auth_verify" {
  filename         = data.archive_file.auth_lambda.output_path
  function_name    = "${var.project_name}-auth-verify"
  role            = aws_iam_role.lambda_auth.arn
  handler         = "verify.handler"
  runtime         = "python3.11"
  timeout         = 10

  environment {
    variables = {
      JWT_SECRET_ARN = aws_secretsmanager_secret.jwt_secret.arn
    }
  }

  source_code_hash = data.archive_file.auth_lambda.output_base64sha256
}

# Lambda 패키징
data "archive_file" "auth_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/auth"
  output_path = "${path.module}/../build/auth.zip"
}
```

### E. API Gateway 설정

```hcl
# terraform/api-gateway.tf 수정

# Lambda Authorizer 생성 (Cognito 대체)
resource "aws_apigatewayv2_authorizer" "lambda_jwt" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "REQUEST"
  authorizer_uri   = aws_lambda_function.auth_verify.invoke_arn
  name             = "lambda-jwt-authorizer"

  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = false

  identity_sources = ["$request.header.Authorization"]

  authorizer_result_ttl_in_seconds = 300  # 5분 캐싱
}

# Lambda Authorizer 권한
resource "aws_lambda_permission" "auth_verify_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_verify.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# OAuth Authorize Route
resource "aws_apigatewayv2_integration" "auth_github_authorize" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.auth_github_authorize.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "auth_github_authorize" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /auth/github/authorize"
  target    = "integrations/${aws_apigatewayv2_integration.auth_github_authorize.id}"
  # No authorization - public endpoint
}

resource "aws_lambda_permission" "auth_github_authorize_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_github_authorize.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# OAuth Callback Route
resource "aws_apigatewayv2_integration" "auth_github_callback" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.auth_github_callback.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "auth_github_callback" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /auth/github/callback"
  target    = "integrations/${aws_apigatewayv2_integration.auth_github_callback.id}"
  # No authorization - GitHub redirect endpoint
}

resource "aws_lambda_permission" "auth_github_callback_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_github_callback.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

# 기존 라우트들 - Cognito Authorizer 대신 Lambda Authorizer 사용
resource "aws_apigatewayv2_route" "deploy" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /deploy"
  target             = "integrations/${aws_apigatewayv2_integration.deploy.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = aws_apigatewayv2_authorizer.lambda_jwt.id
}

# ... 다른 라우트들도 동일하게 수정
```

### F. IAM 역할

```hcl
# terraform/iam.tf 추가

resource "aws_iam_role" "lambda_auth" {
  name = "${var.project_name}-lambda-auth-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_auth" {
  name = "${var.project_name}-lambda-auth-policy"
  role = aws_iam_role.lambda_auth.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.users.arn,
          aws_dynamodb_table.oauth_states.arn,
          "${aws_dynamodb_table.users.arn}/index/*"
        ]
      },
      # KMS
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.github_tokens.arn
      },
      # Secrets Manager
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = aws_secretsmanager_secret.jwt_secret.arn
      }
    ]
  })
}
```

---

## 4. 프론트엔드 구현

### A. Auth 유틸리티

```javascript
// frontend/src/lib/auth.js

export class Auth {
  constructor() {
    this.tokenKey = 'whaleray_token'
    this.userKey = 'whaleray_user'
  }

  /**
   * GitHub 로그인 시작
   */
  async loginWithGitHub(redirectUri = window.location.origin) {
    const params = new URLSearchParams({ redirect_uri: redirectUri })
    window.location.href = `${API_URL}/auth/github/authorize?${params}`
  }

  /**
   * OAuth 콜백 처리
   */
  handleCallback() {
    const params = new URLSearchParams(window.location.search)
    const token = params.get('token')
    const username = params.get('username')
    const error = params.get('error')

    if (error) {
      throw new Error(error)
    }

    if (token && username) {
      this.setToken(token)
      this.setUser({ username })

      // URL에서 토큰 제거
      window.history.replaceState({}, document.title, window.location.pathname)

      return { token, username }
    }

    return null
  }

  /**
   * 로그아웃
   */
  logout() {
    localStorage.removeItem(this.tokenKey)
    localStorage.removeItem(this.userKey)
    window.location.href = '/'
  }

  /**
   * 토큰 저장
   */
  setToken(token) {
    localStorage.setItem(this.tokenKey, token)
  }

  /**
   * 토큰 가져오기
   */
  getToken() {
    return localStorage.getItem(this.tokenKey)
  }

  /**
   * 사용자 정보 저장
   */
  setUser(user) {
    localStorage.setItem(this.userKey, JSON.stringify(user))
  }

  /**
   * 사용자 정보 가져오기
   */
  getUser() {
    const user = localStorage.getItem(this.userKey)
    return user ? JSON.parse(user) : null
  }

  /**
   * 로그인 여부 확인
   */
  isAuthenticated() {
    const token = this.getToken()
    if (!token) return false

    // JWT 디코딩하여 만료 확인
    try {
      const payload = JSON.parse(atob(token.split('.')[1]))
      return payload.exp * 1000 > Date.now()
    } catch {
      return false
    }
  }

  /**
   * Authorization 헤더
   */
  getAuthHeader() {
    const token = this.getToken()
    return token ? { Authorization: `Bearer ${token}` } : {}
  }
}

export const auth = new Auth()
```

### B. API 클라이언트

```javascript
// frontend/src/lib/api.js
import { auth } from './auth'

const API_URL = import.meta.env.VITE_API_URL || 'https://api.whaleray.oriduckduck.site'

class ApiClient {
  async request(endpoint, options = {}) {
    const url = `${API_URL}${endpoint}`

    const config = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...auth.getAuthHeader(),
        ...options.headers,
      },
    }

    try {
      const response = await fetch(url, config)

      // 401 Unauthorized - 토큰 만료
      if (response.status === 401) {
        auth.logout()
        throw new Error('Session expired. Please login again.')
      }

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.message || 'API request failed')
      }

      return data
    } catch (error) {
      console.error('API Error:', error)
      throw error
    }
  }

  get(endpoint) {
    return this.request(endpoint, { method: 'GET' })
  }

  post(endpoint, data) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  put(endpoint, data) {
    return this.request(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' })
  }
}

export const api = new ApiClient()
```

### C. 로그인 페이지

```jsx
// frontend/src/pages/Login.jsx
import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth } from '../lib/auth'

export function Login() {
  const navigate = useNavigate()

  useEffect(() => {
    // 이미 로그인되어 있으면 대시보드로
    if (auth.isAuthenticated()) {
      navigate('/dashboard')
    }

    // OAuth 콜백 처리
    try {
      const result = auth.handleCallback()
      if (result) {
        console.log('Logged in as:', result.username)
        navigate('/dashboard')
      }
    } catch (error) {
      console.error('Login error:', error)
      alert(error.message)
    }
  }, [navigate])

  const handleLogin = () => {
    auth.loginWithGitHub()
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <h1>WhaleRay</h1>
        <p>Deploy your GitHub repositories to AWS ECS</p>

        <button onClick={handleLogin} className="github-login-btn">
          <GitHubIcon />
          Login with GitHub
        </button>

        <p className="description">
          WhaleRay uses GitHub OAuth to:
          <ul>
            <li>Access your repositories</li>
            <li>Deploy your code to AWS ECS</li>
            <li>Monitor deployments</li>
          </ul>
        </p>
      </div>
    </div>
  )
}
```

### D. Protected Route

```jsx
// frontend/src/components/ProtectedRoute.jsx
import { Navigate } from 'react-router-dom'
import { auth } from '../lib/auth'

export function ProtectedRoute({ children }) {
  if (!auth.isAuthenticated()) {
    return <Navigate to="/login" replace />
  }

  return children
}
```

### E. App 라우팅

```jsx
// frontend/src/App.jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { ProtectedRoute } from './components/ProtectedRoute'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" />} />
      </Routes>
    </BrowserRouter>
  )
}
```

---

## 5. 배포 Lambda 수정

기존 `lambda/deploy/handler.py`를 수정하여 새로운 인증 방식 사용:

```python
# lambda/deploy/handler.py

def handler(event, context):
    # 1. Lambda Authorizer에서 전달된 사용자 정보
    user_id = event['requestContext']['authorizer']['userId']
    username = event['requestContext']['authorizer']['username']

    # 2. DynamoDB에서 사용자 정보 (GitHub Token) 조회
    user = users_table.get_item(Key={'userId': user_id})

    if 'Item' not in user:
        return error_response('User not found', 404)

    github_token = decrypt_token(user['Item']['githubToken'])

    # 3. 요청 본문 파싱
    body = json.loads(event['body'])
    repo_url = body['repositoryUrl']

    # 4. GitHub API로 리포지토리 접근
    owner, repo = parse_repo_url(repo_url)

    repo_info = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}',
        headers={'Authorization': f'Bearer {github_token}'}
    )

    if repo_info.status_code == 404:
        return error_response('Repository not found or access denied', 404)

    # 5. 기존 배포 로직 계속...
```

---

## 6. Cognito 제거

```bash
# Cognito 관련 리소스 제거
terraform destroy -target=aws_cognito_user_pool.main
terraform destroy -target=aws_cognito_user_pool_client.web
terraform destroy -target=aws_cognito_user_pool_domain.main

# 파일 제거
rm terraform/cognito.tf
```

---

## 7. 구현 순서

### Phase 1: 인프라 구축 ✅
1. DynamoDB 테이블 생성 (users, oauth_states)
2. KMS Key 생성
3. Secrets Manager에 JWT Secret 생성
4. IAM 역할 및 정책 생성

### Phase 2: Lambda 함수 개발 ✅
1. `lambda/auth/authorize.py` 작성
2. `lambda/auth/callback.py` 작성
3. `lambda/auth/verify.py` 작성 (Lambda Authorizer)
4. PyJWT 라이브러리 패키징

### Phase 3: API Gateway 설정 ✅
1. Lambda Authorizer 생성
2. Auth 라우트 추가 (/auth/github/authorize, /auth/github/callback)
3. 기존 라우트 Authorizer 변경 (Cognito → Lambda)

### Phase 4: 프론트엔드 개발 ✅
1. Auth 유틸리티 작성
2. API 클라이언트 작성
3. 로그인 페이지 개발
4. Protected Route 구현

### Phase 5: 기존 Lambda 수정 ✅
1. Deploy Lambda에서 새로운 인증 방식 사용
2. Manage Lambda 수정
3. 기타 Lambda 함수 업데이트

### Phase 6: Cognito 제거 ✅
1. Cognito 리소스 삭제
2. 관련 파일 제거
3. 문서 업데이트

### Phase 7: 테스트 & 배포 ✅
1. 로컬 개발 환경 테스트
2. 스테이징 환경 배포
3. 프로덕션 배포
4. 모니터링 설정

---

## 8. 보안 고려사항

### ✅ 구현된 보안
1. **GitHub Token 암호화**: KMS로 암호화하여 DynamoDB 저장
2. **CSRF 방지**: State 파라미터 사용 및 TTL 설정
3. **JWT 서명**: HS256 알고리즘으로 토큰 무결성 보장
4. **JWT 만료**: 7일 후 자동 만료
5. **HTTPS Only**: 모든 통신 HTTPS 강제
6. **최소 권한**: Lambda IAM 역할에 필요한 권한만 부여

### 🔒 추가 권장사항
1. **JWT Refresh Token**: 더 긴 유효기간의 Refresh Token 구현
2. **Token Revocation**: Sessions 테이블로 강제 로그아웃 구현
3. **Rate Limiting**: API Gateway에서 Rate Limiting 설정
4. **MFA**: 중요 작업 시 GitHub MFA 확인

---

## 9. 예상 비용

| 서비스 | 사용량 | 월 비용 |
|--------|--------|---------|
| DynamoDB | 1M reads, 100K writes | ~$1 |
| Lambda (Auth) | 10K invocations | ~$0.20 |
| KMS | 10K requests | ~$1.30 |
| Secrets Manager | 1 secret | ~$0.40 |
| API Gateway | 10K requests | ~$0.04 |
| **총계** | | **~$3** |

**Cognito 대비 절감**: ~$10/month (100 MAU 기준)

---

## 10. 마이그레이션 가이드

### 기존 사용자 (없음 - 신규 서비스)
WhaleRay는 신규 서비스이므로 마이그레이션 불필요

### 첫 사용자 플로우
1. https://whaleray.oriduckduck.site 접속
2. "Login with GitHub" 버튼 클릭
3. GitHub 권한 승인
4. 자동으로 사용자 생성 및 JWT 발급
5. 대시보드로 리다이렉트

---

## 11. 모니터링 & 로깅

### CloudWatch Logs
- `/aws/lambda/whaleray-auth-github-authorize`
- `/aws/lambda/whaleray-auth-github-callback`
- `/aws/lambda/whaleray-auth-verify`

### 주요 메트릭
- 로그인 성공/실패 비율
- JWT 검증 성공/실패 비율
- GitHub API 응답 시간
- DynamoDB 쿼리 성능

### 알람 설정
- Lambda 에러율 > 5%
- Lambda Duration > 5초
- DynamoDB Throttling

---

## FAQ

**Q: JWT Secret이 노출되면?**
A: Secrets Manager에서 새로운 Secret 생성 후 Lambda 환경변수 업데이트. 모든 사용자 재로그인 필요.

**Q: GitHub Token이 만료되면?**
A: GitHub OAuth Token은 기본적으로 만료되지 않음. 사용자가 revoke하면 다음 API 호출 시 401 에러 → 재로그인 유도.

**Q: 여러 GitHub 계정 지원?**
A: 현재는 1명의 사용자 = 1개의 GitHub 계정. Organization 지원은 추후 고려.

**Q: 프론트엔드 없이 API만 사용?**
A: 가능. `/auth/github/authorize`로 리다이렉트 → 콜백에서 JWT 받음 → API 호출 시 `Authorization: Bearer <JWT>` 헤더 사용.

---

## 다음 단계

1. ✅ 이 설계 검토 및 승인
2. ⏳ Phase 1 시작: Terraform 인프라 구축
3. ⏳ Lambda 함수 개발
4. ⏳ 프론트엔드 통합
5. ⏳ Cognito 제거
