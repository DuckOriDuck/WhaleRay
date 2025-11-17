# GitHub OAuth2 통합 전략

## 목표
Cognito 기본 인증과 별개로 GitHub OAuth2를 통해 사용자의 리포지토리 접근 권한을 얻고, 이를 활용하여 배포 시 리포지토리 정보를 가져올 수 있도록 구현

## 현재 상태
- ✅ Cognito User Pool (이메일/비밀번호 기본 인증)
- ✅ API Gateway + Lambda 배포 파이프라인
- ✅ DynamoDB 테이블 구조
- ❌ GitHub 리포지토리 접근 권한 없음

## 아키텍처 개요

```
┌─────────────┐
│   사용자    │
└──────┬──────┘
       │
       ├─── 1. Cognito 로그인 (이메일/비밀번호)
       │    └─> JWT 토큰 받음
       │
       ├─── 2. 프론트엔드에서 "GitHub 연동" 버튼 클릭
       │    └─> GitHub OAuth2 플로우 시작
       │
       ├─── 3. GitHub에서 권한 승인
       │    └─> Authorization Code 받음
       │
       ├─── 4. Lambda에서 Code를 Access Token으로 교환
       │    └─> DynamoDB에 저장 (Cognito sub와 매핑)
       │
       └─── 5. 배포 시 저장된 Token으로 리포지토리 접근
            └─> GitHub API 호출하여 repo 정보 가져오기
```

## 데이터 플로우

### 1단계: GitHub 연동 시작
```
Frontend → API Gateway → Lambda (github_oauth_init)
                          ├─> GitHub OAuth URL 생성
                          └─> state 파라미터 생성 (CSRF 방지)
                               └─> DynamoDB에 state 임시 저장
```

### 2단계: GitHub 콜백 처리
```
GitHub → API Gateway → Lambda (github_oauth_callback)
          (code, state)   ├─> state 검증
                          ├─> code를 access_token으로 교환
                          ├─> GitHub API로 사용자 정보 조회
                          └─> DynamoDB Users 테이블 업데이트
                               {
                                 userId: "cognito-sub-xxx",
                                 githubToken: "encrypted-token",
                                 githubUsername: "oriduckduck",
                                 tokenExpiresAt: timestamp
                               }
```

### 3단계: 배포 시 리포지토리 접근
```
Frontend → API Gateway → Lambda (deploy)
  (repo URL)              ├─> Cognito JWT에서 userId 추출
                          ├─> DynamoDB에서 githubToken 조회
                          ├─> GitHub API 호출
                          │   └─> GET /repos/{owner}/{repo}
                          │   └─> GET /repos/{owner}/{repo}/contents
                          └─> CodeBuild 트리거
```

---

## 구현 세부사항

### A. DynamoDB 스키마 수정

#### Users 테이블 (기존 수정)
```python
{
  "userId": "cognito-sub-12345",           # PK - Cognito User Pool의 sub
  "email": "user@example.com",
  "createdAt": "2024-01-01T00:00:00Z",

  # GitHub 연동 정보 추가
  "githubToken": "encrypted:gho_xxx",      # 암호화된 GitHub Access Token
  "githubUsername": "oriduckduck",         # GitHub 사용자명
  "githubUserId": 123456,                  # GitHub User ID
  "githubConnectedAt": "2024-01-01T00:00:00Z",
  "githubTokenExpiresAt": null,            # Fine-grained token인 경우 만료일
  "githubScopes": ["repo"]                 # 부여받은 권한 목록
}
```

#### OAuthStates 테이블 (신규 생성)
```python
{
  "state": "random-uuid-xxx",              # PK - CSRF 방지용 state
  "userId": "cognito-sub-12345",           # 요청한 사용자
  "createdAt": "2024-01-01T00:00:00Z",
  "expiresAt": 1234567890,                 # TTL - 10분 후 자동 삭제
  "redirectUri": "https://whaleray.oriduckduck.site/oauth/callback"
}
```

### B. 새로운 Lambda 함수

#### 1. `github_oauth_init` - OAuth 시작
**경로**: `POST /oauth/github/authorize`
**인증**: Cognito JWT 필수

```python
# lambda/github_oauth/init.py
import json
import uuid
import os
import time
from urllib.parse import urlencode

def handler(event, context):
    # 1. Cognito JWT에서 userId 추출
    user_id = event['requestContext']['authorizer']['jwt']['claims']['sub']

    # 2. State 생성 (CSRF 방지)
    state = str(uuid.uuid4())

    # 3. DynamoDB에 state 저장
    states_table.put_item(Item={
        'state': state,
        'userId': user_id,
        'createdAt': int(time.time()),
        'expiresAt': int(time.time()) + 600,  # 10분 TTL
        'redirectUri': os.environ['FRONTEND_URL'] + '/oauth/callback'
    })

    # 4. GitHub OAuth URL 생성
    github_oauth_url = 'https://github.com/login/oauth/authorize?' + urlencode({
        'client_id': os.environ['GITHUB_CLIENT_ID'],
        'redirect_uri': os.environ['GITHUB_CALLBACK_URL'],
        'scope': 'repo read:user',
        'state': state
    })

    return {
        'statusCode': 200,
        'body': json.dumps({
            'authUrl': github_oauth_url,
            'state': state
        })
    }
```

#### 2. `github_oauth_callback` - OAuth 콜백 처리
**경로**: `GET /oauth/github/callback`
**인증**: 없음 (GitHub에서 리다이렉트)

```python
# lambda/github_oauth/callback.py
import json
import os
import boto3
import requests
from aws_encryption_sdk import encrypt, decrypt

def handler(event, context):
    # 1. Query 파라미터 추출
    code = event['queryStringParameters']['code']
    state = event['queryStringParameters']['state']

    # 2. State 검증
    state_item = states_table.get_item(Key={'state': state})
    if 'Item' not in state_item:
        return error_response('Invalid state')

    user_id = state_item['Item']['userId']
    redirect_uri = state_item['Item']['redirectUri']

    # 3. Access Token 교환
    token_response = requests.post(
        'https://github.com/login/oauth/access_token',
        headers={'Accept': 'application/json'},
        data={
            'client_id': os.environ['GITHUB_CLIENT_ID'],
            'client_secret': os.environ['GITHUB_CLIENT_SECRET'],
            'code': code,
            'redirect_uri': os.environ['GITHUB_CALLBACK_URL']
        }
    )

    access_token = token_response.json()['access_token']

    # 4. GitHub 사용자 정보 조회
    user_response = requests.get(
        'https://api.github.com/user',
        headers={'Authorization': f'Bearer {access_token}'}
    )
    github_user = user_response.json()

    # 5. Token 암호화 (KMS 사용)
    encrypted_token = encrypt_token(access_token)

    # 6. DynamoDB 업데이트
    users_table.update_item(
        Key={'userId': user_id},
        UpdateExpression='''
            SET githubToken = :token,
                githubUsername = :username,
                githubUserId = :github_id,
                githubConnectedAt = :connected_at,
                githubScopes = :scopes
        ''',
        ExpressionAttributeValues={
            ':token': encrypted_token,
            ':username': github_user['login'],
            ':github_id': github_user['id'],
            ':connected_at': int(time.time()),
            ':scopes': ['repo', 'read:user']
        }
    )

    # 7. State 삭제
    states_table.delete_item(Key={'state': state})

    # 8. 프론트엔드로 리다이렉트
    return {
        'statusCode': 302,
        'headers': {
            'Location': f'{redirect_uri}?success=true&username={github_user["login"]}'
        }
    }

def encrypt_token(token):
    # KMS를 사용한 토큰 암호화 구현
    kms = boto3.client('kms')
    result = kms.encrypt(
        KeyId=os.environ['KMS_KEY_ID'],
        Plaintext=token.encode()
    )
    return result['CiphertextBlob']
```

#### 3. `deploy` Lambda 수정 - GitHub Token 사용
```python
# lambda/deploy/handler.py 수정
import boto3
import requests

def handler(event, context):
    body = json.loads(event['body'])
    repo_url = body['repositoryUrl']  # https://github.com/owner/repo

    # 1. Cognito JWT에서 userId 추출
    user_id = event['requestContext']['authorizer']['jwt']['claims']['sub']

    # 2. DynamoDB에서 GitHub Token 조회
    user = users_table.get_item(Key={'userId': user_id})
    if 'githubToken' not in user['Item']:
        return error_response('GitHub not connected. Please connect your GitHub account.')

    # 3. Token 복호화
    github_token = decrypt_token(user['Item']['githubToken'])

    # 4. Repository 정보 추출
    owner, repo = parse_repo_url(repo_url)

    # 5. GitHub API로 리포지토리 정보 조회
    repo_info = requests.get(
        f'https://api.github.com/repos/{owner}/{repo}',
        headers={'Authorization': f'Bearer {github_token}'}
    )

    if repo_info.status_code == 404:
        return error_response('Repository not found or no access')

    # 6. Repo Inspector Lambda 호출하여 프레임워크 감지
    # 7. CodeBuild 프로젝트 트리거
    # ... 기존 로직 계속
```

### C. Terraform 변경사항

#### 1. DynamoDB 테이블 추가
```hcl
# terraform/dynamodb.tf에 추가

resource "aws_dynamodb_table" "oauth_states" {
  name           = "${var.project_name}-oauth-states"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "state"

  attribute {
    name = "state"
    type = "S"
  }

  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  tags = {
    Name = "${var.project_name}-oauth-states"
  }
}
```

#### 2. KMS Key 추가 (Token 암호화용)
```hcl
# terraform/kms.tf (신규)

resource "aws_kms_key" "github_tokens" {
  description             = "KMS key for encrypting GitHub tokens"
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

#### 3. Lambda 함수 추가
```hcl
# terraform/lambda.tf에 추가

resource "aws_lambda_function" "github_oauth_init" {
  filename         = data.archive_file.github_oauth_lambda.output_path
  function_name    = "${var.project_name}-github-oauth-init"
  role            = aws_iam_role.lambda_exec.arn
  handler         = "init.handler"
  runtime         = "python3.11"
  timeout         = 30

  environment {
    variables = {
      USERS_TABLE         = aws_dynamodb_table.users.name
      STATES_TABLE        = aws_dynamodb_table.oauth_states.name
      GITHUB_CLIENT_ID    = var.github_client_id
      GITHUB_CALLBACK_URL = "https://api.${var.domain_name}/oauth/github/callback"
      FRONTEND_URL        = "https://${var.domain_name}"
    }
  }
}

resource "aws_lambda_function" "github_oauth_callback" {
  filename         = data.archive_file.github_oauth_lambda.output_path
  function_name    = "${var.project_name}-github-oauth-callback"
  role            = aws_iam_role.lambda_exec.arn
  handler         = "callback.handler"
  runtime         = "python3.11"
  timeout         = 30

  environment {
    variables = {
      USERS_TABLE          = aws_dynamodb_table.users.name
      STATES_TABLE         = aws_dynamodb_table.oauth_states.name
      GITHUB_CLIENT_ID     = var.github_client_id
      GITHUB_CLIENT_SECRET = var.github_client_secret
      GITHUB_CALLBACK_URL  = "https://api.${var.domain_name}/oauth/github/callback"
      KMS_KEY_ID          = aws_kms_key.github_tokens.id
    }
  }
}
```

#### 4. API Gateway 라우트 추가
```hcl
# terraform/api-gateway.tf에 추가

# OAuth Init (인증 필요)
resource "aws_apigatewayv2_integration" "github_oauth_init" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.github_oauth_init.invoke_arn
}

resource "aws_apigatewayv2_route" "github_oauth_init" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "POST /oauth/github/authorize"
  target             = "integrations/${aws_apigatewayv2_integration.github_oauth_init.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}

# OAuth Callback (인증 불필요 - GitHub에서 리다이렉트)
resource "aws_apigatewayv2_integration" "github_oauth_callback" {
  api_id           = aws_apigatewayv2_api.main.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.github_oauth_callback.invoke_arn
}

resource "aws_apigatewayv2_route" "github_oauth_callback" {
  api_id     = aws_apigatewayv2_api.main.id
  route_key  = "GET /oauth/github/callback"
  target     = "integrations/${aws_apigatewayv2_integration.github_oauth_callback.id}"
  # No authorization - public endpoint for GitHub redirect
}

# GitHub 연동 해제
resource "aws_apigatewayv2_route" "github_oauth_disconnect" {
  api_id             = aws_apigatewayv2_api.main.id
  route_key          = "DELETE /oauth/github"
  target             = "integrations/${aws_apigatewayv2_integration.github_oauth_init.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.cognito.id
}
```

#### 5. IAM 권한 추가
```hcl
# terraform/lambda.tf의 IAM 정책에 추가

data "aws_iam_policy_document" "lambda_kms" {
  statement {
    actions = [
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey"
    ]
    resources = [aws_kms_key.github_tokens.arn]
  }
}

resource "aws_iam_policy" "lambda_kms" {
  name   = "${var.project_name}-lambda-kms"
  policy = data.aws_iam_policy_document.lambda_kms.json
}

resource "aws_iam_role_policy_attachment" "lambda_kms" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_kms.arn
}
```

### D. 프론트엔드 변경사항

#### 1. GitHub 연동 버튼 추가
```jsx
// frontend/src/components/GitHubConnect.jsx
import { useState } from 'react';
import { api } from '../lib/api';

export function GitHubConnect() {
  const [loading, setLoading] = useState(false);
  const [connected, setConnected] = useState(false);
  const [username, setUsername] = useState(null);

  const handleConnect = async () => {
    setLoading(true);
    try {
      // 1. OAuth 초기화 API 호출
      const response = await api.post('/oauth/github/authorize');
      const { authUrl } = response.data;

      // 2. GitHub OAuth 페이지로 리다이렉트
      window.location.href = authUrl;
    } catch (error) {
      console.error('Failed to connect GitHub:', error);
      alert('GitHub 연동에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('GitHub 연동을 해제하시겠습니까?')) return;

    try {
      await api.delete('/oauth/github');
      setConnected(false);
      setUsername(null);
    } catch (error) {
      console.error('Failed to disconnect GitHub:', error);
    }
  };

  return (
    <div className="github-connect">
      {connected ? (
        <div>
          <p>연동된 GitHub 계정: @{username}</p>
          <button onClick={handleDisconnect}>연동 해제</button>
        </div>
      ) : (
        <button onClick={handleConnect} disabled={loading}>
          {loading ? '연동 중...' : 'GitHub 연동하기'}
        </button>
      )}
    </div>
  );
}
```

#### 2. OAuth 콜백 페이지
```jsx
// frontend/src/pages/OAuthCallback.jsx
import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

export function OAuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const success = searchParams.get('success');
    const username = searchParams.get('username');
    const error = searchParams.get('error');

    if (success === 'true') {
      // 성공 메시지 표시
      alert(`GitHub 계정 @${username}이(가) 연동되었습니다!`);
      navigate('/dashboard');
    } else if (error) {
      alert(`GitHub 연동 실패: ${error}`);
      navigate('/settings');
    }
  }, [navigate, searchParams]);

  return <div>GitHub 연동 처리 중...</div>;
}
```

#### 3. 배포 폼에서 GitHub Token 사용 여부 확인
```jsx
// frontend/src/components/DeployForm.jsx
const handleDeploy = async () => {
  // GitHub 연동 확인
  const user = await api.get('/user/profile');

  if (!user.githubUsername) {
    if (confirm('Private 리포지토리를 배포하려면 GitHub 연동이 필요합니다. 연동하시겠습니까?')) {
      navigate('/settings?tab=github');
      return;
    }
  }

  // 배포 진행
  await api.post('/deploy', {
    repositoryUrl: repoUrl,
    // ...
  });
};
```

---

## 구현 순서

### Phase 1: 인프라 구축
1. ✅ DynamoDB `oauth_states` 테이블 생성
2. ✅ KMS Key 생성 및 IAM 권한 설정
3. ✅ `Users` 테이블에 GitHub 관련 필드 추가 확인

### Phase 2: Lambda 함수 개발
1. ✅ `lambda/github_oauth/init.py` 작성
2. ✅ `lambda/github_oauth/callback.py` 작성
3. ✅ Token 암호화/복호화 유틸리티 함수 작성
4. ✅ API Gateway 라우트 연결

### Phase 3: 기존 Lambda 수정
1. ✅ `lambda/deploy/handler.py` - GitHub Token 사용 로직 추가
2. ✅ `lambda/repo_inspector/handler.py` - GitHub API 인증 추가
3. ✅ 에러 핸들링 (Token 만료, 권한 없음 등)

### Phase 4: 프론트엔드 개발
1. ✅ GitHub 연동 컴포넌트 개발
2. ✅ OAuth 콜백 페이지 개발
3. ✅ 사용자 설정 페이지에 통합
4. ✅ 배포 폼에서 GitHub 연동 여부 확인

### Phase 5: 테스트 & 배포
1. ✅ GitHub OAuth App 생성 및 설정
2. ✅ 로컬/스테이징 환경 테스트
3. ✅ 프로덕션 배포
4. ✅ 모니터링 및 로깅 설정

---

## GitHub OAuth App 설정

### GitHub에서 OAuth App 생성
1. https://github.com/settings/developers 접속
2. "New OAuth App" 클릭
3. 설정값:
   - **Application name**: WhaleRay
   - **Homepage URL**: `https://whaleray.oriduckduck.site`
   - **Authorization callback URL**: `https://api.whaleray.oriduckduck.site/oauth/github/callback`
   - **Enable Device Flow**: 체크 해제

4. Client ID와 Client Secret을 `terraform.tfvars`에 추가 (이미 있음)

---

## 보안 고려사항

### 1. Token 암호화
- ✅ KMS를 사용한 GitHub Token 암호화 저장
- ✅ Lambda 함수에서만 복호화 가능하도록 IAM 권한 제한

### 2. CSRF 방지
- ✅ State 파라미터 사용 및 DynamoDB 검증
- ✅ TTL 10분 설정으로 자동 만료

### 3. Token 만료 처리
- ⚠️ GitHub Token은 기본적으로 만료되지 않음
- ✅ 사용자가 직접 연동 해제 가능
- ✅ GitHub에서 Token revoke 시 에러 핸들링

### 4. 최소 권한 원칙
- ✅ `repo` 스코프만 요청 (읽기 권한)
- ❌ `admin:repo_hook`, `delete_repo` 등 불필요한 권한 요청 안 함

### 5. Rate Limiting
- ✅ GitHub API Rate Limit: 5000 requests/hour (인증된 요청)
- ✅ Lambda에서 Rate Limit 초과 시 에러 핸들링
- ✅ CloudWatch Logs로 API 사용량 모니터링

---

## 예상 비용
- DynamoDB (oauth_states): ~$0 (요청 적음)
- KMS: $1/month + $0.03/10,000 requests
- Lambda 실행: OAuth 플로우당 ~$0.0001
- **총 예상**: 월 ~$2 추가

---

## 마이그레이션 가이드

기존 사용자 (GitHub 연동 없음):
1. 로그인 후 설정 페이지 방문
2. "GitHub 연동하기" 버튼 클릭
3. GitHub 권한 승인
4. Private 리포지토리 배포 가능

새로운 사용자:
1. Cognito로 회원가입/로그인
2. 바로 Public 리포지토리 배포 가능 (연동 불필요)
3. Private 리포지토리는 GitHub 연동 필요

---

## FAQ

**Q: Public 리포지토리도 GitHub 연동이 필요한가요?**
A: 아니요. Public 리포지토리는 인증 없이 접근 가능합니다. Private 리포지토리만 GitHub 연동이 필요합니다.

**Q: GitHub Token이 만료되면 어떻게 되나요?**
A: GitHub Personal Access Token은 기본적으로 만료되지 않습니다. 사용자가 GitHub에서 직접 revoke하거나 연동 해제하지 않는 한 계속 사용 가능합니다.

**Q: 여러 GitHub 계정을 연동할 수 있나요?**
A: 현재 설계는 1명의 사용자당 1개의 GitHub 계정만 연동 가능합니다. 필요시 나중에 확장 가능합니다.

**Q: Cognito와 GitHub 로그인을 완전히 통합할 수 있나요?**
A: 가능하지만, 현재는 의도적으로 분리했습니다:
- Cognito: 사용자 인증 (이메일/비밀번호)
- GitHub OAuth: 리포지토리 접근 권한만 (Cognito와 별개)

이렇게 하면 외부 패키지 의존성 없이 간단하게 구현 가능합니다.

---

## 다음 단계

1. ✅ 이 문서 검토 및 승인
2. ⏳ Phase 1 시작: Terraform 인프라 구축
3. ⏳ GitHub OAuth App 생성
4. ⏳ Lambda 함수 개발
5. ⏳ 프론트엔드 통합