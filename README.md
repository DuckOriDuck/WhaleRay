# WhaleRay

Railway/Vercel 스타일의 컨테이너 배포 플랫폼 - GitHub 레포지토리를 자동으로 빌드하고 배포

## 아키텍처

- **인프라**: Terraform (AWS)
- **인증**: AWS Cognito + GitHub Identity Provider
- **빌드**: AWS CodeBuild (프레임워크별)
- **컨테이너**: ECS on EC2 + ECR
- **로드밸런서**: Application Load Balancer
- **오케스트레이션**: EventBridge + Lambda
- **데이터베이스**: DynamoDB (Users, Deployments, Services)
- **프론트엔드**: React + Vite + Amplify

## 전체 워크플로우

```
1. 사용자 GitHub 로그인 (Cognito)
   ↓
2. GitHub 레포 URL 입력
   ↓
3. Repo Inspector Lambda
   - GitHub API로 레포 분석
   - pom.xml/package.json 검사
   - 프레임워크 감지 (Spring/Node/Next.js/Python)
   ↓
4. CodeBuild 시작
   - 프레임워크별 buildspec 실행
   - Docker 이미지 빌드
   - ECR에 푸시
   ↓
5. EventBridge 이벤트 감지
   - "CodeBuild Build Succeeded"
   ↓
6. ECS Deployer Lambda
   - ECS Task Definition 생성
   - ECS Service 배포/업데이트
   ↓
7. 실행 완료
   - ALB를 통해 서비스 접근
   - CloudWatch Logs에서 로그 확인
```

## 프로젝트 구조

```
WhaleRay/
├── terraform/              # IaC (Infrastructure as Code)
│   ├── main.tf            # Provider 설정
│   ├── variables.tf       # 변수 정의
│   ├── vpc.tf             # VPC, 서브넷, NAT Gateway
│   ├── dynamodb.tf        # Deployments, Services 테이블
│   ├── ecr.tf             # 컨테이너 레지스트리
│   ├── ecs.tf             # ECS 클러스터, Task 정의
│   ├── alb.tf             # 로드 밸런서
│   ├── cognito.tf         # 사용자 인증
│   ├── api-gateway.tf     # HTTP API
│   ├── lambda.tf          # Lambda 함수 배포
│   └── outputs.tf         # 출력 값
│
├── lambda/                # Python Lambda 함수
│   ├── deploy/            # 배포 처리 함수
│   │   ├── handler.py
│   │   └── requirements.txt
│   ├── manage/            # 서비스 관리 API
│   │   ├── handler.py
│   │   └── requirements.txt
│   └── router/            # 동적 라우팅 (선택사항)
│       ├── handler.py
│       └── requirements.txt
│
└── frontend/              # React 웹 애플리케이션
    ├── src/
    │   ├── components/    # UI 컴포넌트
    │   ├── lib/          # API, Auth 유틸리티
    │   ├── App.jsx       # 메인 앱
    │   └── config.js     # 설정 파일
    ├── package.json
    └── vite.config.js
```

## 시작하기

### 사전 요구사항

- AWS CLI 설치 및 설정
- Terraform >= 1.0
- Node.js >= 18
- Python >= 3.11

### 1. AWS 인프라 배포

```bash
cd terraform

# Terraform 초기화
terraform init

# 인프라 계획 검토
terraform plan

# 인프라 배포
terraform apply

# 출력 값 확인
terraform output -json > ../outputs.json
```

### 2. 프론트엔드 설정

Terraform 배포 후 출력된 값들을 프론트엔드 설정에 입력합니다:

```bash
cd frontend

# 의존성 설치
npm install

# src/config.js 파일 수정
# Terraform 출력 값을 채워넣으세요:
# - cognito_user_pool_id
# - cognito_client_id
# - cognito_domain
# - api_endpoint
# - ecr_repository_url
# - alb_dns
```

[frontend/src/config.js](frontend/src/config.js) 파일을 열어 다음 값들을 업데이트:

```javascript
export const config = {
  region: 'ap-northeast-2',
  cognito: {
    userPoolId: 'ap-northeast-2_XXXXXXXXX',     // terraform output
    userPoolClientId: 'XXXXXXXXXXXXXXXXXX',      // terraform output
    domain: 'whaleray-prod'                      // terraform output
  },
  apiEndpoint: 'https://xxxxx.execute-api.ap-northeast-2.amazonaws.com',  // terraform output
  ecrRepositoryUrl: 'XXXX.dkr.ecr.ap-northeast-2.amazonaws.com/whaleray-services',
  albDns: 'whaleray-alb-XXXX.ap-northeast-2.elb.amazonaws.com'
}
```

### 3. 프론트엔드 실행

```bash
cd frontend
npm run dev
```

브라우저에서 http://localhost:3000 접속

## 사용 방법

### 1. 사용자 등록 및 로그인

프론트엔드에서 Cognito 인증을 통해 회원가입/로그인

### 2. Docker 이미지 준비

```bash
# ECR 로그인
aws ecr get-login-password --region ap-northeast-2 | \
  docker login --username AWS --password-stdin <ECR_REPOSITORY_URL>

# 이미지 빌드 및 푸시
docker build -t my-app .
docker tag my-app:latest <ECR_REPOSITORY_URL>:latest
docker push <ECR_REPOSITORY_URL>:latest
```

### 3. 서비스 배포

프론트엔드에서:
1. "새 배포" 탭 클릭
2. 서비스 정보 입력:
   - 서비스 이름
   - Docker 이미지 URI
   - 포트 번호
   - 환경 변수 (선택)
3. "배포하기" 클릭

### 4. 배포 확인

- "서비스" 탭에서 실행 중인 서비스 확인
- "배포 히스토리" 탭에서 배포 기록 확인
- ALB DNS를 통해 서비스 접속

## API 엔드포인트

### POST /deploy
새 서비스 배포 또는 업데이트

```json
{
  "serviceName": "my-app",
  "imageUri": "XXXX.dkr.ecr.ap-northeast-2.amazonaws.com/my-app:latest",
  "port": 3000,
  "envVars": {
    "NODE_ENV": "production",
    "API_KEY": "your-key"
  }
}
```

### GET /services
사용자의 모든 서비스 조회

### GET /services/{serviceId}
특정 서비스 상세 정보 및 배포 히스토리 조회

### GET /deployments
최근 배포 목록 조회

## 주요 기능

- **사용자 인증**: Cognito를 통한 안전한 인증
- **컨테이너 배포**: ECR + ECS on EC2로 간편한 배포
- **자동 스케일링**: ECS Capacity Provider Auto Scaling
- **로드 밸런싱**: ALB를 통한 트래픽 분산 (동적 포트 매핑)
- **배포 히스토리**: DynamoDB에 모든 배포 기록 저장
- **실시간 로그**: CloudWatch Logs로 컨테이너 로그 수집

## 비용 최적화

- **DynamoDB**: Pay-per-request 모드
- **ECS**: EC2 Auto Scaling (기본 t3.small 2대)
  - 인스턴스 타입 변경: `terraform.tfvars`에서 `ecs_instance_type` 조정
  - 인스턴스 수 조정: `ecs_min_size`, `ecs_max_size`, `ecs_desired_size` 변수
- **ECR**: 이미지 라이프사이클 정책 (최근 10개만 유지)
- **NAT Gateway**: 비용 절감을 위해 필요시 제거 가능
- **예상 월 비용**:
  - t3.small 2대: ~$30
  - NAT Gateway 2개: ~$60
  - 기타 (ALB, Lambda, DynamoDB): ~$20
  - **총 약 $110/월**

## 주의사항

1. **리전 설정**: 기본값은 `ap-northeast-2` (서울)
2. **비용**: NAT Gateway와 EC2 인스턴스가 주요 비용 요인
3. **보안**: 프로덕션 환경에서는 HTTPS 설정 필수
4. **도메인**: Route53로 커스텀 도메인 연결 가능
5. **인스턴스 크기**: 기본값 t3.small (2 vCPU, 2GB RAM)
   - 더 많은 컨테이너를 실행하려면 더 큰 인스턴스 타입 사용

## 변수 커스터마이징

[terraform/variables.tf](terraform/variables.tf)에서 다음 값들을 조정 가능:

```hcl
# ECS 인스턴스 타입 (기본: t3.small)
ecs_instance_type = "t3.medium"

# ECS Auto Scaling 설정
ecs_min_size     = 1  # 최소 인스턴스 수
ecs_max_size     = 5  # 최대 인스턴스 수
ecs_desired_size = 2  # 기본 인스턴스 수
```

## 인프라 삭제

```bash
cd terraform
terraform destroy
```

## 라이선스

MIT

## 기여

Pull Request 환영합니다!
