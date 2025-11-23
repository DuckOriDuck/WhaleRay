# WhaleRay 환경 변수 관리 시스템 구현 문서

**프로젝트:** WhaleRay - Railway/Vercel 스타일 컨테이너 배포 플랫폼  
**브랜치:** `feat/env-secure-setting`  
**작성일:** 2025-11-23  
**작성자:** DuckOriDuck Team

---

## 📋 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [문제 정의 및 목표](#2-문제-정의-및-목표)
3. [아키텍처 설계](#3-아키텍처-설계)
4. [구현 세부사항](#4-구현-세부사항)
5. [인프라 코드 수정](#5-인프라-코드-수정)
6. [검증 및 테스트](#6-검증-및-테스트)
7. [배포 가이드](#7-배포-가이드)
8. [운영 가이드](#8-운영-가이드)

---

## 1. 프로젝트 개요

### 1.1. 배경

WhaleRay는 GitHub OAuth 인증을 통해 사용자의 레포지토리를 자동으로 컨테이너화하여 배포하는 PaaS 플랫폼입니다. 배포 과정에서 사용자의 민감한 환경 변수(.env)를 안전하고 효율적으로 관리하는 것이 핵심 요구사항이었습니다.

### 1.2. 핵심 과제

1. **보안:** Git 리포지토리에 민감한 정보를 저장하지 않을 것
2. **영속성:** 재배포 시 환경 변수를 반복적으로 입력하는 사용자 경험 개선
3. **명확성:** 환경 변수 설정을 유지/갱신/초기화하려는 사용자 의도를 명확히 구분
4. **안정성:** 다양한 .env 파일 형식을 안정적으로 처리

### 1.3. 해결 방안

**Lambda Chaining 아키텍처**를 도입하여 단일 책임 원칙을 준수하고, **ServiceID 기반 영속적 키**와 **Blob 저장 전략**을 통해 환경 변수를 안전하게 관리합니다.

---

## 2. 문제 정의 및 목표

### 2.1. 기존 문제점

#### 시점의 딜레마 (Timing & Race Condition)
- `deploymentId`는 배포 버튼을 누른 후에 생성되어 빌드 시점과 엇갈릴 위험
- 환경 변수를 어느 시점에 저장해야 하는지 모호함

#### 휘발성 문제 (Persistence & UX)
- `deploymentId`는 배포마다 변경되어, 재배포 시 환경 변수를 매번 재입력해야 함
- 최악의 사용자 경험 발생

#### 삭제의 모호성 (Deletion Ambiguity)
- 환경 변수를 완전히 비우고 싶을 때, 빈 문자열을 보내면 시스템이 "기존 값 유지"로 오해
- 좀비 변수 문제 발생 (과거 변수가 계속 남음)

#### 단일 람다의 과부하 (Monolithic Responsibility)
- 기존 `repo_inspector` 람다가 코드 분석, SSM 암호화, CodeBuild 트리거까지 모든 책임을 떠안음
- 코드 복잡도 증가 및 디버깅 어려움

### 2.2. 목표

1. **보안:** AWS KMS로 암호화하여 SSM Parameter Store에 저장
2. **영속성:** `serviceId` 기반 키로 재배포 시 자동 유지
3. **명확성:** `isReset` 플래그로 유지/갱신/초기화 의도 구분
4. **안정성:** Blob 저장 방식으로 파싱 제거, 포맷 100% 보존
5. **유지보수성:** Lambda Chaining으로 단일 책임 원칙 준수

---

## 3. 아키텍처 설계

### 3.1. 전체 데이터 흐름

```
Frontend (사용자)
    ↓ POST /deployments
    │ { repositoryFullName, branch, envFileContent?, isReset? }
    ↓
API Gateway
    ↓
deploy Lambda (배포 요청 접수)
    ↓ DynamoDB.put_item()
    │ { deploymentId, userId, serviceId, envFileContent, isReset, ... }
    ↓
DynamoDB deployments 테이블 (Stream 활성화)
    ↓ INSERT Event
    │ Stream: NEW_AND_OLD_IMAGES
    ↓
repo_inspector Lambda (DynamoDB Stream Trigger)
    ↓ GitHub API 호출
    │ 프레임워크 감지 (Spring Boot, Node.js 등)
    ↓ lambda.invoke(env_builder, Event)
    │ Payload: { deploymentId, userId, serviceId, envFileContent, isReset, detectedFramework }
    ↓
env_builder Lambda (비동기 호출)
    ↓ SSM Blob 처리 (3단 논리)
    │ (1) isReset=true → 빈 공백 덮어쓰기
    │ (2) envFileContent 존재 → 새 값 저장
    │ (3) 둘 다 아님 → 기존 값 유지 (없으면 에러)
    ↓ codebuild.start_build()
    │ 환경 변수: DOTENV_BLOB_SSM_PATH
    ↓
CodeBuild
    ↓ SSM에서 DOTENV_BLOB 가져오기
    │ .env 파일로 복원
    ↓ Docker 빌드 및 ECR 푸시
    ↓
ECS 배포
```

### 3.2. 핵심 설계 원칙

#### ServiceID 기반 영속적 키
- **전략:** `deploymentId` 대신 `userId + repoName` 조합을 `serviceId`로 정의
- **효과:** 배포 전부터 키를 알 수 있어 시점 문제 해결, 재배포 편의성 확보
- **예시:** `github-123-DuckOriDuck-whaleray`

#### Blob 저장 방식
- **전략:** .env 내용을 파싱하지 않고, 전체 텍스트를 암호화된 하나의 덩어리(Blob)로 SSM에 저장
- **효과:** 로직 단순화, 사용자 작성 포맷 100% 보존

#### 명시적 초기화 프로토콜
- **전략:** `isReset` 플래그로 유지와 삭제의 의도를 명확히 구분
- **효과:** 사용자가 원할 때 확실하게 환경 변수를 비운 상태로 배포 가능

#### Lambda Chaining 아키텍처
- **전략:** 거대한 람다를 `repo_inspector`(분석가)와 `env_builder`(건축가)로 분리하고 비동기 호출로 연결
- **효과:** 역할 분리, 단계별 로그 추적, 권한 격리(Security)

---

## 4. 구현 세부사항

### 4.1. deploy Lambda

**파일:** `lambda/deploy/handler.py`

**책임:**
- 사용자 인증 (JWT Authorizer)
- GitHub App Installation 확인
- 배포 정보 DynamoDB에 저장

**핵심 코드:**
```python
# 요청 본문 파싱
body = json.loads(event['body'])
repository_full_name = body.get('repositoryFullName')
branch = body.get('branch', 'main')
env_file_content = body.get('envFileContent', '')
is_reset = body.get('isReset', False)  # isReset 플래그 추출

# serviceId 생성
service_name = repository_full_name.replace('/', '-')
service_id = f"{user_id}-{service_name}"

# DynamoDB에 저장
item_to_store = {
    'deploymentId': deployment_id,
    'userId': user_id,
    'serviceId': service_id,
    'envFileContent': env_file_content,
    'isReset': is_reset,
    'status': 'INSPECTING'
}
deployments_table.put_item(Item=item_to_store)
```

---

### 4.2. repo_inspector Lambda

**파일:** `lambda/repo_inspector/handler.py`

**책임:**
- DynamoDB Stream 이벤트 수신
- GitHub API를 통한 프레임워크 감지
- `env_builder` Lambda 비동기 호출

**핵심 코드:**
```python
# DynamoDB Stream에서 데이터 추출
env_file_content = new_image.get('envFileContent', {}).get('S', '')
is_reset = new_image.get('isReset', {}).get('BOOL', False)

# 프레임워크 감지
framework = detect_framework(repository_full_name, branch, installation_access_token)

# env_builder 호출 페이로드 구성
payload = {
    'deploymentId': deployment_id,
    'userId': user_id,
    'serviceId': service_id,
    'repositoryFullName': repository_full_name,
    'branch': branch,
    'envFileContent': env_file_content,  # 그대로 전달
    'isReset': is_reset,                  # 그대로 전달
    'detectedFramework': framework
}

# 비동기 호출
lambda_client.invoke(
    FunctionName=ENV_BUILDER_FUNCTION_NAME,
    InvocationType='Event',  # 비동기
    Payload=json.dumps(payload)
)
```

---

### 4.3. env_builder Lambda

**파일:** `lambda/env_builder/handler.py`

**책임:**
- SSM Parameter Store에 환경 변수 Blob 저장/관리
- CodeBuild 프로젝트 시작

**핵심 코드 (3단 논리):**
```python
env_blob_ssm_path = f"/{PROJECT_NAME}/{user_id}/{service_id}/DOTENV_BLOB"

# (1) 초기화 확인: isReset이 true 인가?
if is_reset:
    ssm_client.put_parameter(
        Name=env_blob_ssm_path,
        Value=" ",  # 빈 공백으로 덮어쓰기 (삭제 효과)
        Type='SecureString',
        KeyId=SSM_KMS_KEY_ARN,
        Overwrite=True
    )

# (2) 입력 확인: envFileContent가 있는가?
elif env_file_content:
    ssm_client.put_parameter(
        Name=env_blob_ssm_path,
        Value=env_file_content,
        Type='SecureString',
        KeyId=SSM_KMS_KEY_ARN,
        Overwrite=True
    )

# (3) 기존 설정 확인
else:
    try:
        ssm_client.get_parameter(Name=env_blob_ssm_path, WithDecryption=False)
    except ssm_client.exceptions.ParameterNotFound:
        raise Exception("Initial deployment requires .env content")

# CodeBuild 시작
codebuild.start_build(
    projectName=codebuild_project,
    sourceVersion=branch,
    environmentVariablesOverride=[
        {'name': 'DOTENV_BLOB_SSM_PATH', 'value': env_blob_ssm_path, 'type': 'PLAINTEXT'}
    ]
)
```

---

## 5. 인프라 코드 수정

### 5.1. DynamoDB Stream 활성화

**파일:** `terraform/dynamodb.tf`

```hcl
resource "aws_dynamodb_table" "deployments" {
  stream_enabled   = true  # ✅ 추가
  stream_view_type = "NEW_AND_OLD_IMAGES"
}
```

### 5.2. Lambda IAM 권한

**파일:** `terraform/lambda.tf`

```hcl
{
  Effect = "Allow"
  Action = [
    "dynamodb:GetRecords",
    "dynamodb:GetShardIterator",
    "dynamodb:DescribeStream",
    "dynamodb:ListStreams"
  ]
  Resource = aws_dynamodb_table.deployments.stream_arn
}
```

### 5.3. Zip 생성 결정론적 수정

**파일:** `lambda/create_zip.py`

```python
zinfo = zipfile.ZipInfo(arcname)
zinfo.date_time = (2020, 1, 1, 0, 0, 0)  # 고정 타임스탬프
zinfo.compress_type = zipfile.ZIP_DEFLATED
```

---

## 6. 검증 및 테스트

### 6.1. Zip 생성 결정론 검증

**결과:**
```
Hash1: 37BEB57D4AE33376B4842506A052532A519CA8AFB0C1E79E878588F89F1B2F73
Hash2: 37BEB57D4AE33376B4842506A052532A519CA8AFB0C1E79E878588F89F1B2F73
SUCCESS: Hashes match!
```

### 6.2. 로직 정합성

| 항목 | 상태 |
|------|------|
| 데이터 흐름 | ✅ 정상 |
| 3단 논리 구현 | ✅ 정상 |
| 아키텍처 원칙 | ✅ 준수 |
| 보안 | ✅ 정상 |

---

## 7. 배포 가이드

### 7.1. Terraform 배포

```bash
cd terraform
terraform plan -out=tfplan
terraform apply tfplan
```

### 7.2. 배포 후 확인

```bash
# CloudWatch 로그
aws logs tail /aws/lambda/whaleray-repo-inspector --follow
aws logs tail /aws/lambda/whaleray-env-builder --follow

# SSM Parameter
aws ssm get-parameter \
  --name "/whaleray/{userId}/{serviceId}/DOTENV_BLOB" \
  --with-decryption
```

---

## 8. 운영 가이드

### 8.1. 모니터링

- Lambda 실행 시간 및 에러율
- DynamoDB Stream 지연 시간
- SSM Parameter Store 접근 패턴

### 8.2. 보안

- KMS Key 로테이션
- SSM Parameter 접근 로그 감사
- IAM 권한 최소화 검토

---

**문서 종료**
