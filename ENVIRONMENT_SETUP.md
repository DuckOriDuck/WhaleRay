# WhaleRay 환경변수 설정 가이드

## 🔧 필수 환경변수 설정

WhaleRay가 정상적으로 동작하려면 다음 환경변수들을 `terraform/terraform.tfvars` 파일에 설정해야 합니다.

### 1. GitHub App 설정

GitHub App 설정 페이지에서 다음 정보를 가져와서 설정:

```bash
# GitHub App 정보 (https://github.com/settings/apps/whaleray)
github_app_slug = "whaleray"
github_app_id = "2314094"  # 이미 설정됨
github_app_private_key = """-----BEGIN RSA PRIVATE KEY-----
여기에 GitHub App Private Key 내용을 붙여넣기
-----END RSA PRIVATE KEY-----"""
```

**GitHub App Private Key 가져오는 방법:**
1. https://github.com/settings/apps/whaleray 접속
2. "Private keys" 섹션에서 "Generate a private key" 클릭
3. 다운로드된 `.pem` 파일 내용을 복사해서 `github_app_private_key`에 설정

### 2. GitHub OAuth App 설정

OAuth App 설정 페이지에서 다음 정보 가져오기:

```bash
# GitHub OAuth 정보 (https://github.com/settings/applications)
github_client_id = "YOUR_OAUTH_CLIENT_ID"
github_client_secret = "YOUR_OAUTH_CLIENT_SECRET"
```

**GitHub OAuth App 설정 방법:**
1. https://github.com/settings/applications/new 접속
2. 다음 설정으로 OAuth App 생성:
   - **Application name**: `WhaleRay`
   - **Homepage URL**: `https://whaleray.oriduckduck.site`
   - **Authorization callback URL**: `https://api.whaleray.oriduckduck.site/auth/github/callback`
3. 생성 후 Client ID와 Client Secret 복사

### 3. SSL 인증서 (선택사항)

커스텀 도메인을 사용하려면 ACM 인증서 ARN 설정:

```bash
# AWS ACM Certificate ARN (us-east-1 리전에 있어야 함)
acm_certificate_arn = "arn:aws:acm:us-east-1:698928390364:certificate/YOUR-CERTIFICATE-ID"
```

## 🚀 환경변수 적용

### 1. terraform.tfvars 파일 작성

```bash
cd /Users/gimdonghyeon/Desktop/softbank/terraform
vi terraform.tfvars  # 위의 값들을 설정
```

### 2. Terraform 적용

```bash
# 환경변수 변경사항 확인
terraform plan

# 환경변수 적용
terraform apply
```

### 3. 설정 검증

Lambda 함수가 올바르게 환경변수를 받았는지 확인:

```bash
# Lambda 환경변수 확인
aws lambda get-function-configuration --function-name whaleray-repo-inspector \
  --query 'Environment.Variables' --output table
```

## 🔍 문제 해결

### GitHub App Private Key 오류
- Private Key가 올바른 PEM 형식인지 확인
- 키 앞뒤에 공백이나 특수문자가 없는지 확인

### OAuth App 설정 오류
- Callback URL이 정확한지 확인: `https://api.whaleray.oriduckduck.site/auth/github/callback`
- Client ID/Secret에 특수문자가 포함되어 있다면 따옴표로 감싸기

### SSL 인증서 오류
- ACM 인증서가 `us-east-1` 리전에 있는지 확인 (CloudFront 요구사항)
- 인증서 상태가 "Issued"인지 확인

## 📝 현재 상태

- ✅ GitHub App 존재함: https://github.com/apps/whaleray
- ✅ App ID 확인됨: 2314094
- ❌ Private Key 미설정
- ❌ OAuth App 미설정

## 다음 단계

1. GitHub App Private Key 설정
2. GitHub OAuth App 생성 및 설정
3. `terraform apply`로 환경변수 적용
4. keyboard-arena 프로젝트로 테스트