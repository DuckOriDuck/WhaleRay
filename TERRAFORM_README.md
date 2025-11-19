# Terraform 작업 가이드

WhaleRay 프로젝트의 Terraform 인프라 관리 방법

## 기본 명령어

### 초기 설정

```bash
# Provider 초기화 및 플러그인 다운로드
terraform init

# Backend 재설정 (S3 위치 변경 시)<<-이건 거의 쓸 필요 없음
terraform init -reconfigure
```

### 인프라 배포

```bash
# 변경사항 미리보기
terraform plan

# 변경사항 적용 <<-이것도 본인이 단순 작업할 땐 쓸 일 없음
terraform apply

# 자동 승인 (CI/CD용)
terraform apply -auto-approve
```

### 인프라 삭제

```bash
# 전체 인프라 삭제 <<- 이것도
terraform destroy

# 특정 리소스만 삭제
terraform destroy -target=aws_lambda_function.deploy
```

## 특정 리소스만 작업하기 이거 중요

전체 인프라를 apply하지 않고 **변경한 특정 리소스만** 배포하고 싶을 때 사용합니다.

### 1. 리소스 주소 확인

```bash
# 현재 State의 모든 리소스 목록 확인
terraform state list

# 특정 이름으로 필터링 (리눅스 기준)
terraform state list | grep lambda
terraform state list | grep ecs
```

### 2. 특정 리소스만 Plan

```bash
# 단일 리소스
terraform plan -target=aws_lambda_function.deploy

# 여러 리소스
terraform plan \
  -target=aws_lambda_function.deploy \
  -target=aws_lambda_function.manage
```

### 3. 특정 리소스만 Apply

```bash
# 단일 리소스 배포
terraform apply -target=aws_lambda_function.deploy

# 여러 리소스 동시 배포
terraform apply \
  -target=aws_lambda_function.deploy \
  -target=aws_lambda_function.manage \
  -target=aws_ecs_service.app
```

## 자주 사용하는 예시

### Lambda 함수 업데이트

```bash
# 단일 Lambda 함수
terraform apply -target=aws_lambda_function.deploy

# 여러 Lambda 함수
terraform apply \
  -target=aws_lambda_function.deploy \
  -target=aws_lambda_function.manage \
  -target=aws_lambda_function.ecs_deployer
```

### ECS 서비스 업데이트

```bash
# ECS 서비스 + 태스크 정의
terraform apply \
  -target=aws_ecs_service.app \
  -target=aws_ecs_task_definition.app

# ECS 클러스터 전체
terraform apply -target=aws_ecs_cluster.main
```

### API Gateway 업데이트

```bash
# API Gateway
terraform apply -target=aws_apigatewayv2_api.main

# 특정 Route
terraform apply -target=aws_apigatewayv2_route.deployment_logs

# Stage
terraform apply -target=aws_apigatewayv2_stage.main
```

### DynamoDB 테이블 업데이트

```bash
# 단일 테이블
terraform apply -target=aws_dynamodb_table.services

# 여러 테이블
terraform apply \
  -target=aws_dynamodb_table.users \
  -target=aws_dynamodb_table.deployments \
  -target=aws_dynamodb_table.services
```

```

### GitHub OAuth Lambda 업데이트

```bash
# GitHub OAuth 관련 Lambda
terraform apply \
  -target=aws_lambda_function.github_oauth_authorize \
  -target=aws_lambda_function.github_oauth_callback \
  -target=aws_lambda_function.github_oauth_verify
```

## State 관리

### State 확인

```bash
# 전체 리소스 목록
terraform state list

# 특정 리소스 상세 정보
terraform state show aws_lambda_function.deploy

# State 파일 위치 확인
terraform state pull
```

### State 조작 (주의!)

```bash
# 리소스를 State에서 제거 (실제 AWS 리소스는 유지)
terraform state rm aws_lambda_function.deploy

# 리소스를 State로 가져오기
terraform import aws_lambda_function.deploy whaleray-deploy

# State에서 리소스 이름 변경
terraform state mv aws_lambda_function.old aws_lambda_function.new
```

## 주의사항

### ⚠️ `-target` 사용 시 주의점

1. **의존성 문제**: `-target`은 명시한 리소스만 처리하므로, 의존성이 있는 리소스는 자동으로 포함되지 않을 수 있습니다.

2. **Drift 발생 가능**: 일부 리소스만 apply하면 실제 인프라와 State가 불일치할 수 있습니다.

3. **권장 사항**:
   - 개발/테스트 환경에서 먼저 테스트
   - 가능하면 전체 `terraform apply` 사용
   - `-target`은 긴급 상황이나 특정 리소스만 변경이 확실할 때 사용

### 예시: 의존성 포함 배포

Lambda와 API Gateway Route를 함께 업데이트:
```bash
terraform apply \
  -target=aws_lambda_function.deploy \
  -target=aws_apigatewayv2_integration.deploy \
  -target=aws_apigatewayv2_route.deploy \
  -target=aws_lambda_permission.deploy
```

## Secrets Manager 사용

JWT Secret은 Secrets Manager에서 관리됩니다:

```bash
# Secret 값 확인
aws secretsmanager get-secret-value \
  --secret-id whaleray/jwt-secret \
  --query SecretString \
  --output text

# Secret 값 업데이트
aws secretsmanager update-secret \
  --secret-id whaleray/jwt-secret \
  --secret-string "new-secret-value"
```

## 트러블슈팅

### State Lock 걸렸을 때
#### 본인이 apply 중에 강제정지하거나 했을때 생기는 문제입니다. 만약 갑자기 push했는데 state lock 걸려있다는 게 나와있다면 누군가가 terraform apply를 하고 있다는 의미이니 이땐 임의로 lock 풀지 마세요. 무조건 팀원에게 물어보기 무조건. 테라폼 상태 꼬이면 귀찮습니다
```bash
# Lock 정보 확인 후 강제 해제 
terraform force-unlock <LOCK_ID>

# 또는 DynamoDB에서 직접 삭제
aws dynamodb delete-item \
  --table-name whaleray-terraform-locks \
  --key '{"LockID":{"S":"whaleray-tfstate-prod/prod/whaleray.tfstate"}}'
```

### Provider Plugin 문제

```bash
# Provider 재설치
rm -rf .terraform
rm .terraform.lock.hcl
terraform init
```

### Import 필요 시

기존 AWS 리소스를 Terraform State로 가져오기:

```bash
# 예시: Lambda 함수
terraform import aws_lambda_function.deploy whaleray-deploy

# 예시: DynamoDB 테이블
terraform import aws_dynamodb_table.services whaleray-services

# 예시: ECS 서비스
terraform import aws_ecs_service.app whaleray-ecs/app
```

## Backend 설정

현재 Backend 구성:
- **S3 Bucket**: `whaleray-tfstate-prod`
- **Key**: `prod/whaleray.tfstate`
- **Region**: `ap-northeast-2`
- **DynamoDB Lock Table**: `whaleray-terraform-locks`

Backend 리소스는 Terraform으로 관리하지 않고 수동으로 생성/관리합니다.
