# WhaleRay

Railway/Vercel 스타일의 컨테이너 배포 플랫폼 - GitHub OAuth로 로그인하고 Docker 컨테이너를 빠르게 배포

## 아키텍처

- **인프라**: Terraform (AWS)
- **인증**: GitHub OAuth + Lambda Authorizer (JWT)
- **컨테이너**: ECS on EC2 + ECR
- **로드밸런서**: Application Load Balancer
- **API**: API Gateway HTTP API + Lambda
- **데이터베이스**: DynamoDB (Users, Deployments, Services)
- **프론트엔드**: React + Vite

## 주요 기능

- **GitHub OAuth 인증**: Lambda 기반 커스텀 인증 시스템
- **JWT 토큰**: Secrets Manager 기반 보안 토큰
- **컨테이너 배포**: ECR + ECS로 간편한 배포
- **자동 스케일링**: ECS Auto Scaling
- **로드 밸런싱**: ALB 동적 포트 매핑
- **배포 히스토리**: DynamoDB 기록
- **실시간 로그**: CloudWatch Logs

## 프로젝트 구조

```
WhaleRay/
├── terraform/              # IaC
│   ├── main.tf            # Provider 설정
│   ├── api-gateway.tf     # API Gateway + 커스텀 도메인
│   ├── auth-lambda.tf     # 인증 Lambda 함수
│   ├── dynamodb.tf        # Users, Deployments, Services
│   ├── kms.tf             # GitHub 토큰 암호화
│   ├── secrets.tf         # JWT Secret
│   ├── route53.tf         # DNS 설정
│   └── ...
│
├── lambda/
│   ├── auth/              # 인증 시스템
│   │   ├── authorize.py   # OAuth 시작
│   │   ├── callback.py    # OAuth 콜백 + JWT 발급
│   │   ├── verify.py      # Lambda Authorizer (JWT 검증)
│   │   └── requirements.txt
│   ├── deploy/            # 배포 처리
│   └── manage/            # 서비스 관리
│
└── frontend/              # React 앱
    ├── src/
    │   ├── lib/
    │   │   ├── auth.js    # JWT 관리
    │   │   └── api.js     # API 클라이언트
    │   └── config.js      # 설정
    └── ...
```

## 시작하기

### 사전 요구사항

- AWS CLI 설치 및 설정
- Terraform >= 1.0
- Node.js >= 18
- GitHub OAuth App 생성 필요

### 1. GitHub OAuth App 생성

1. https://github.com/settings/developers
2. New OAuth App 클릭
3. 설정:
   - Application name: `WhaleRay`
   - Homepage URL: `https://whaleray.oriduckduck.site`
   - Authorization callback URL: `https://api.whaleray.oriduckduck.site/auth/github/callback`
4. Client ID와 Client Secret 저장

### 2. Terraform 변수 설정

`terraform/terraform.tfvars` 생성:

```hcl
project_name         = "whaleray"
environment          = "prod"
domain_name          = "whaleray.oriduckduck.site"
github_client_id     = "your-github-client-id"
github_client_secret = "your-github-client-secret"
```

### 3. AWS 인프라 배포

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

배포 후 출력 값 확인:
```bash
terraform output
```

### 4. 프론트엔드 빌드 및 배포

```bash
cd frontend
npm install
npm run build

# S3에 배포
aws s3 sync dist/ s3://whaleray-frontend-<account-id> --delete

# CloudFront 캐시 무효화
aws cloudfront create-invalidation --distribution-id <dist-id> --paths "/*"
```

### 5. 접속

브라우저에서 `https://whaleray.oriduckduck.site` 접속

## API 엔드포인트

### 인증

- `GET /auth/github/start` - GitHub OAuth 시작
- `GET /auth/github/callback` - OAuth 콜백 + JWT 발급

### 서비스 관리 (JWT 필요)

- `POST /deploy` - 새 서비스 배포
- `GET /services` - 서비스 목록
- `GET /services/{serviceId}` - 서비스 상세
- `GET /deployments` - 배포 히스토리
- `GET /deployments/{deploymentId}/logs` - 배포 로그

### 배포 예시

```bash
curl -X POST https://api.whaleray.oriduckduck.site/deploy \
  -H "Authorization: Bearer <your-jwt-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "serviceName": "my-app",
    "imageUri": "xxx.dkr.ecr.ap-northeast-2.amazonaws.com/my-app:latest",
    "port": 3000,
    "envVars": {
      "NODE_ENV": "production"
    }
  }'
```

## 인증 플로우

```
1. 사용자가 "GitHub으로 로그인" 클릭
   ↓
2. Lambda Authorize → GitHub OAuth 페이지로 리다이렉트
   ↓
3. 사용자 GitHub에서 승인
   ↓
4. GitHub → Lambda Callback
   - Access Token 교환
   - GitHub 사용자 정보 조회
   - KMS로 토큰 암호화
   - DynamoDB에 사용자 저장
   - JWT 토큰 생성 (Secrets Manager)
   ↓
5. 프론트엔드로 JWT 전달 (URL 파라미터)
   ↓
6. 프론트엔드가 JWT를 localStorage에 저장
   ↓
7. 모든 API 요청에 Authorization 헤더 포함
   ↓
8. Lambda Authorizer가 JWT 검증
```

## 환경 변수

Terraform이 자동으로 설정하는 Lambda 환경 변수:

- `GITHUB_CLIENT_ID` - GitHub OAuth Client ID
- `GITHUB_CLIENT_SECRET` - GitHub OAuth Client Secret
- `GITHUB_CALLBACK_URL` - OAuth 콜백 URL
- `FRONTEND_URL` - 프론트엔드 URL
- `JWT_SECRET_ARN` - JWT Secret ARN
- `KMS_KEY_ID` - GitHub 토큰 암호화 KMS Key

## 보안

- **JWT 토큰**: 7일 유효기간, HS256 알고리즘
- **GitHub 토큰**: KMS 암호화 후 DynamoDB 저장
- **CSRF 방지**: OAuth state 파라미터 (10분 TTL)
- **Lambda Authorizer**: 모든 API 엔드포인트 보호 (인증 제외)

## 비용 최적화

- **DynamoDB**: Pay-per-request 모드
- **ECS**: t3.small 2대 Auto Scaling
- **Lambda**: 사용량 기반 과금
- **API Gateway**: 요청 수 기반

**예상 월 비용**:
- EC2 (t3.small × 2): ~$30
- NAT Gateway × 2: ~$60
- ALB: ~$20
- 기타 (Lambda, API Gateway, DynamoDB): ~$10
- **총 약 $120/월**

## 인프라 삭제

```bash
cd terraform
terraform destroy
```

## 라이선스

MIT
