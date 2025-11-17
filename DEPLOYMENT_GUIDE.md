# WhaleRay 배포 가이드

## 📋 목차
1. [현재 상태](#현재-상태)
2. [아키텍처 개요](#아키텍처-개요)
3. [사전 요구사항](#사전-요구사항)
4. [배포 절차](#배포-절차)
5. [인프라 구성 요소](#인프라-구성-요소)
6. [테스트 방법](#테스트-방법)
7. [문제 해결](#문제-해결)
8. [다음 단계](#다음-단계)

---

## 현재 상태

### ✅ 완료된 작업
- **인증 시스템 재설계**: Cognito → GitHub OAuth + JWT 인증으로 전환
- **Lambda 함수**: 3개의 Auth Lambda 함수 구현 (authorize, callback, verify)
- **DynamoDB**: Users, OAuthStates 테이블 설정
- **보안**: KMS (토큰 암호화), Secrets Manager (JWT Secret)
- **API Gateway**: Lambda Authorizer 통합 및 Auth 엔드포인트 추가
- **인프라 코드**: Terraform으로 모든 리소스 정의 완료

### ⏳ 대기 중인 작업
- **Terraform Apply**: 인프라 배포 (이 가이드의 핵심)
- **프론트엔드 통합**: Auth 유틸리티 및 로그인 UI 개발 (Phase 4)
- **테스트**: E2E 테스트 및 통합 테스트

### 🎯 이 가이드의 목표
Terraform을 사용하여 WhaleRay 인증 시스템을 AWS에 배포

---

## 아키텍처 개요

### 인증 플로우
```
사용자
  ↓
  ① GET /auth/github/authorize
  ↓
GitHub OAuth (권한 승인)
  ↓
  ② GET /auth/github/callback (code)
  ↓
Lambda (callback)
  ├─ Code → Access Token 교환
  ├─ GitHub API로 사용자 정보 조회
  ├─ DynamoDB에 사용자 저장 (토큰 KMS 암호화)
  └─ JWT 토큰 생성 (Secrets Manager Secret 사용)
  ↓
프론트엔드 (JWT 저장)
  ↓
  ③ API 호출 (Authorization: Bearer <JWT>)
  ↓
Lambda Authorizer (verify)
  ├─ JWT 검증
  └─ IAM Policy 반환 (Allow/Deny)
  ↓
API Lambda (deploy, manage, logs)
```

### 주요 구성 요소

| 컴포넌트 | 설명 | 파일 |
|---------|------|------|
| **Lambda Authorizer** | JWT 검증 및 API Gateway 인증 | `lambda/auth/verify.py` |
| **OAuth Authorize** | GitHub OAuth 플로우 시작 | `lambda/auth/authorize.py` |
| **OAuth Callback** | GitHub 콜백 처리 및 JWT 발급 | `lambda/auth/callback.py` |
| **DynamoDB Users** | GitHub 사용자 정보 및 토큰 저장 | `terraform/dynamodb.tf` |
| **DynamoDB OAuthStates** | CSRF 방지용 state (TTL 10분) | `terraform/dynamodb.tf` |
| **KMS Key** | GitHub 토큰 암호화 | `terraform/kms.tf` |
| **Secrets Manager** | JWT 서명 비밀키 (자동 생성) | `terraform/secrets.tf` |

---

## 사전 요구사항

### 1. AWS 계정 및 자격증명

**필수 권한:**
- DynamoDB (테이블 생성, 읽기, 쓰기)
- Lambda (함수 생성, IAM 역할)
- API Gateway (HTTP API 생성, 라우트 설정)
- KMS (키 생성, 암호화/복호화)
- Secrets Manager (시크릿 생성, 읽기)
- S3 (Terraform 상태 저장용)

**AWS CLI 설정:**
```bash
aws configure
# AWS Access Key ID: [입력]
# AWS Secret Access Key: [입력]
# Default region name: ap-northeast-2
# Default output format: json
```

**자격증명 확인:**
```bash
aws sts get-caller-identity
# 출력:
# {
#   "UserId": "...",
#   "Account": "698928390364",
#   "Arn": "arn:aws:iam::698928390364:user/..."
# }
```

### 2. Terraform 설치

**버전:** >= 1.6.0

```bash
# 설치 확인
terraform version
# Terraform v1.13.5 or higher

# 설치되지 않은 경우:
# Windows: choco install terraform
# macOS: brew install terraform
# Linux: https://www.terraform.io/downloads
```

### 3. Python 설치

**버전:** Python 3.11+

```bash
python --version
# Python 3.11.x

pip --version
# pip 24.x
```

### 4. GitHub OAuth App 생성

**중요: 이미 생성되어 있음!**

현재 설정된 OAuth App:
- **Client ID**: `Iv23liclOTgrckm2vJvR` (terraform.tfvars에 설정됨)
- **Client Secret**: `e54cd1370d07f18246c3d884cdf818f894828bd5`

**Callback URL 업데이트 필요:**
1. https://github.com/settings/developers 접속
2. OAuth App "WhaleRay" 선택
3. **Authorization callback URL**을 다음으로 설정:
   ```
   https://api.whaleray.oriduckduck.site/auth/github/callback
   ```

---

## 배포 절차

### Step 1: 프로젝트 클론 및 확인

```bash
cd WhaleRay

# 현재 브랜치 확인
git branch
# * main

# 최신 코드 확인
git log -1 --oneline
# feat: GitHub OAuth 기반 커스텀 인증 시스템 구현
```

### Step 2: Terraform 설정 확인

```bash
cd terraform

# terraform.tfvars 확인 (민감 정보 포함)
cat terraform.tfvars
```

**예상 내용:**
```hcl
github_client_id     = "Iv23liclOTgrckm2vJvR"
github_client_secret = "e54cd1370d07f18246c3d884cdf818f894828bd5"
acm_certificate_arn  = "arn:aws:acm:us-east-1:698928390364:certificate/9632a743-7f7b-4945-a8e5-7c200f2653cb"

ecs_instance_type = "t3.small"
ecs_min_size      = 1
ecs_max_size      = 5
ecs_desired_size  = 2
```

**⚠️ 주의:** `terraform.tfvars`는 Git에 커밋되어 있음. 민감 정보가 포함되어 있으므로 주의!

### Step 3: Terraform 초기화

```bash
# Provider 및 모듈 다운로드
terraform init

# 성공 메시지:
# Terraform has been successfully initialized!
```

**설치되는 Provider:**
- `hashicorp/aws` ~> 6.0
- `hashicorp/archive` ~> 2.4
- `hashicorp/random` ~> 3.6

### Step 4: Terraform Plan 검토

```bash
# 실행 계획 생성 및 확인
terraform plan -out=tfplan

# 주요 변경사항 확인:
# - Create: ~15개 리소스 (Lambda, DynamoDB, KMS, Secrets Manager, API Gateway 라우트)
# - Destroy: ~4개 리소스 (Cognito User Pool, Client, Domain, Authorizer)
# - Modify: ~5개 리소스 (API Gateway 라우트 Authorizer 변경)
```

**예상 생성 리소스:**
- `aws_lambda_function.auth_github_authorize`
- `aws_lambda_function.auth_github_callback`
- `aws_lambda_function.auth_verify`
- `aws_apigatewayv2_authorizer.lambda_jwt`
- `aws_dynamodb_table.oauth_states`
- `aws_kms_key.github_tokens`
- `aws_secretsmanager_secret.jwt_secret`
- 기타...

**예상 삭제 리소스:**
- `aws_cognito_user_pool.main`
- `aws_cognito_user_pool_client.web`
- `aws_cognito_user_pool_domain.main`
- `aws_apigatewayv2_authorizer.cognito`

### Step 5: Terraform Apply 실행

```bash
# 실행 (약 3-5분 소요)
terraform apply tfplan

# 진행 상황:
# aws_kms_key.github_tokens: Creating...
# random_password.jwt_secret: Creating...
# aws_dynamodb_table.oauth_states: Creating...
# aws_lambda_function.auth_verify: Creating...
# ...

# 완료 메시지:
# Apply complete! Resources: 15 added, 5 changed, 4 destroyed.
```

### Step 6: 출력 확인

```bash
# Terraform 출력 확인
terraform output

# 예상 출력:
# api_endpoint = "https://nf73cyilw6.execute-api.ap-northeast-2.amazonaws.com"
# api_domain_url = "https://api.whaleray.oriduckduck.site"
# frontend_url = "https://whaleray.oriduckduck.site"
# ...
```

### Step 7: 배포 검증

```bash
# 1. Lambda 함수 확인
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `whaleray-auth`)].FunctionName'
# 출력:
# [
#   "whaleray-auth-github-authorize",
#   "whaleray-auth-github-callback",
#   "whaleray-auth-verify"
# ]

# 2. DynamoDB 테이블 확인
aws dynamodb list-tables --query 'TableNames[?starts_with(@, `whaleray`)]'
# 출력:
# [
#   "whaleray-users",
#   "whaleray-oauth-states",
#   "whaleray-deployments",
#   "whaleray-services"
# ]

# 3. Secrets Manager 확인
aws secretsmanager list-secrets --query 'SecretList[?Name==`whaleray/jwt-secret`].Name'
# 출력:
# [
#   "whaleray/jwt-secret"
# ]

# 4. KMS Key 확인
aws kms list-aliases --query 'Aliases[?AliasName==`alias/whaleray-github-tokens`]'
```

---

## 인프라 구성 요소

### Lambda 함수 (3개)

#### 1. whaleray-auth-github-authorize
- **핸들러**: `authorize.handler`
- **역할**: GitHub OAuth 플로우 시작
- **엔드포인트**: `GET /auth/github/authorize`
- **응답**: GitHub OAuth 페이지로 302 리다이렉트

#### 2. whaleray-auth-github-callback
- **핸들러**: `callback.handler`
- **역할**: GitHub 콜백 처리, JWT 발급
- **엔드포인트**: `GET /auth/github/callback`
- **작업**:
  1. Authorization Code → Access Token 교환
  2. GitHub API로 사용자 정보 조회
  3. DynamoDB에 사용자 저장 (토큰 KMS 암호화)
  4. JWT 생성 및 프론트엔드로 리다이렉트

#### 3. whaleray-auth-verify (Lambda Authorizer)
- **핸들러**: `verify.handler`
- **역할**: API Gateway에서 JWT 검증
- **작업**:
  1. Authorization 헤더에서 JWT 추출
  2. Secrets Manager에서 JWT Secret 가져오기
  3. JWT 검증 (서명, 만료, issuer)
  4. IAM Policy 반환 (Allow/Deny)

### DynamoDB 테이블 (2개 신규)

#### whaleray-users
- **PK**: `userId` (github_{github_id})
- **GSI**: `GithubUsernameIndex` (githubUsername)
- **용도**: GitHub 사용자 정보 및 암호화된 토큰 저장

**스키마:**
```json
{
  "userId": "github_12345678",
  "githubId": 12345678,
  "githubUsername": "oriduckduck",
  "githubEmail": "user@example.com",
  "githubAvatarUrl": "https://...",
  "githubToken": "encrypted:base64...",
  "githubScopes": ["repo", "read:user"],
  "createdAt": "2025-01-01T00:00:00Z",
  "lastLoginAt": "2025-01-01T00:00:00Z"
}
```

#### whaleray-oauth-states
- **PK**: `state` (UUID)
- **TTL**: `expiresAt` (10분 자동 삭제)
- **용도**: CSRF 방지용 OAuth state 임시 저장

### KMS & Secrets Manager

#### KMS Key: whaleray-github-tokens
- **용도**: GitHub Access Token 암호화/복호화
- **키 회전**: 활성화
- **삭제 대기**: 7일

#### Secret: whaleray/jwt-secret
- **용도**: JWT 서명 비밀키
- **생성**: Terraform의 `random_password`로 자동 생성 (64자)
- **접근**: Lambda 함수만 읽기 가능 (IAM 정책)

### API Gateway 변경사항

#### 신규 라우트
- `GET /auth/github/authorize` → `lambda:auth_github_authorize` (공개)
- `GET /auth/github/callback` → `lambda:auth_github_callback` (공개)

#### 수정된 라우트 (Authorizer 변경)
- `POST /deploy` → Lambda Authorizer (기존: Cognito)
- `GET /services` → Lambda Authorizer
- `GET /services/{serviceId}` → Lambda Authorizer
- `GET /deployments` → Lambda Authorizer
- `GET /deployments/{deploymentId}/logs` → Lambda Authorizer

---

## 테스트 방법

### 1. OAuth 플로우 수동 테스트

```bash
# 1. Authorize URL 생성
AUTHORIZE_URL="https://api.whaleray.oriduckduck.site/auth/github/authorize"

# 2. 브라우저에서 접속
# Windows: start $AUTHORIZE_URL
# macOS: open $AUTHORIZE_URL
# Linux: xdg-open $AUTHORIZE_URL

# 3. GitHub 권한 승인 후 리다이렉트 확인
# 예상 URL: https://whaleray.oriduckduck.site?token=eyJhbGc...&username=oriduckduck

# 4. JWT 토큰 추출 및 디코딩
TOKEN="eyJhbGc..." # 위 URL에서 복사

# JWT 디코딩 (https://jwt.io 사용 또는):
echo $TOKEN | cut -d. -f2 | base64 -d | jq .
# 출력:
# {
#   "sub": "github_12345678",
#   "username": "oriduckduck",
#   "iat": 1234567890,
#   "exp": 1234567890,
#   "iss": "whaleray"
# }
```

### 2. API 호출 테스트

```bash
# JWT 토큰으로 보호된 API 호출
TOKEN="eyJhbGc..." # 위에서 받은 토큰

# Services 목록 조회
curl -H "Authorization: Bearer $TOKEN" \
  https://api.whaleray.oriduckduck.site/services

# 예상 응답 (성공):
# {"services": []}

# 예상 응답 (인증 실패):
# {"message": "Unauthorized"}
```

### 3. DynamoDB 데이터 확인

```bash
# Users 테이블 스캔
aws dynamodb scan --table-name whaleray-users \
  --query 'Items[].{userId:userId.S,username:githubUsername.S}'

# 예상 출력:
# [
#   {
#     "userId": "github_12345678",
#     "username": "oriduckduck"
#   }
# ]
```

### 4. Lambda 로그 확인

```bash
# 최근 로그 확인 (authorize)
aws logs tail /aws/lambda/whaleray-auth-github-authorize --follow

# 최근 로그 확인 (callback)
aws logs tail /aws/lambda/whaleray-auth-github-callback --follow

# 최근 로그 확인 (verify)
aws logs tail /aws/lambda/whaleray-auth-verify --follow
```

---

## 문제 해결

### ❌ Terraform Apply 실패

#### 문제: "Plugin did not respond"
```
Error: Plugin did not respond
```

**해결:**
```bash
rm -rf .terraform .terraform.lock.hcl
terraform init -upgrade
terraform plan
```

#### 문제: Cognito 리소스 참조 에러
```
Error: Reference to undeclared resource
aws_cognito_user_pool.main
```

**원인:** cognito.tf 파일이 삭제되었는데 다른 파일에서 참조
**해결:** 해당 참조 제거 (이미 제거됨, outputs.tf 확인)

### ❌ Lambda 함수 에러

#### 문제: "No module named 'jwt'"
```
[ERROR] Runtime.ImportModuleError: Unable to import module 'callback': No module named 'jwt'
```

**원인:** Lambda 패키지에 PyJWT 미포함
**해결:**
```bash
cd ../lambda/auth
pip install -r requirements.txt -t .
cd ../../terraform
terraform apply
```

#### 문제: JWT Secret 접근 불가
```
[ERROR] AccessDeniedException: User is not authorized to perform: secretsmanager:GetSecretValue
```

**원인:** Lambda IAM 역할에 Secrets Manager 권한 없음
**해결:** `terraform/auth-lambda.tf` 확인 (이미 권한 설정됨)

### ❌ GitHub OAuth 에러

#### 문제: "redirect_uri_mismatch"
```
error=redirect_uri_mismatch
```

**원인:** GitHub OAuth App의 Callback URL이 잘못됨
**해결:**
1. https://github.com/settings/developers
2. OAuth App 설정에서 Callback URL 확인:
   ```
   https://api.whaleray.oriduckduck.site/auth/github/callback
   ```

#### 문제: "Invalid state"
```
{"error": "Invalid or expired state"}
```

**원인:** OAuth state가 만료됨 (10분 TTL) 또는 CSRF 공격
**해결:** 다시 로그인 시도

### ❌ API Gateway 에러

#### 문제: 401 Unauthorized
```
{"message": "Unauthorized"}
```

**원인:** JWT 토큰이 없거나 만료됨
**해결:**
1. Authorization 헤더 확인: `Authorization: Bearer <token>`
2. JWT 만료 확인 (7일)
3. 재로그인

---

## 다음 단계

### Phase 4: 프론트엔드 통합 (진행 필요)

#### 1. Auth 유틸리티 구현
- `frontend/src/lib/auth.js` 작성
- JWT 토큰 관리 (localStorage)
- 로그인/로그아웃 함수

#### 2. 로그인 페이지 개발
- `frontend/src/pages/Login.jsx`
- "Login with GitHub" 버튼
- OAuth 콜백 처리

#### 3. API 클라이언트 수정
- `frontend/src/lib/api.js`
- Authorization 헤더 자동 추가
- 401 에러 처리 (자동 로그아웃)

#### 4. Protected Route 구현
- 인증 필요한 페이지 보호
- 미인증 시 로그인 페이지로 리다이렉트

**참고 문서:**
- `AUTH_IMPLEMENTATION.md` - 상세 구현 가이드
- `GITHUB_OAUTH_STRATEGY.md` - 아키텍처 및 전략

### Phase 5: 배포 및 테스트

1. 프론트엔드 빌드 및 S3 업로드
2. E2E 테스트 (Cypress/Playwright)
3. 성능 테스트
4. 모니터링 설정 (CloudWatch Alarms)

---

## 부록

### 유용한 명령어

```bash
# Terraform 상태 확인
terraform state list

# 특정 리소스 상태 확인
terraform state show aws_lambda_function.auth_verify

# Terraform 출력 다시 보기
terraform output

# Lambda 함수 직접 호출 (테스트)
aws lambda invoke \
  --function-name whaleray-auth-github-authorize \
  --payload '{"queryStringParameters": {}}' \
  response.json

# DynamoDB 테이블 정보
aws dynamodb describe-table --table-name whaleray-users

# API Gateway 엔드포인트 확인
aws apigatewayv2 get-apis --query 'Items[?Name==`whaleray-api`]'
```

### 비용 예상 (월간)

| 서비스 | 예상 비용 |
|--------|----------|
| Lambda (Auth) | ~$0.20 |
| DynamoDB (Users, States) | ~$1.00 |
| KMS | ~$1.30 |
| Secrets Manager | ~$0.40 |
| API Gateway | ~$0.10 |
| **총 추가 비용** | **~$3.00** |

기존 인프라 (ECS, ALB, etc.)는 별도

### 참고 자료

- **Terraform 문서**: https://www.terraform.io/docs
- **AWS Lambda**: https://docs.aws.amazon.com/lambda/
- **API Gateway Authorizers**: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-lambda-authorizer.html
- **GitHub OAuth**: https://docs.github.com/en/developers/apps/building-oauth-apps
- **JWT**: https://jwt.io/introduction

---

## 문의사항

문제가 발생하거나 질문이 있으면:
1. `TROUBLESHOOTING.md` 확인 (향후 작성)
2. CloudWatch Logs 확인
3. Terraform 문서 참조
4. 팀원에게 문의

**작성자**: Claude Code
**마지막 업데이트**: 2025-11-17
**버전**: 1.0.0
