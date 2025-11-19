# Task #2 구현 요약: Repo Inspector와 배포 연동

## 1. 목표 (Goal)
프론트엔드에서 '배포하기' 버튼을 눌렀을 때, 실제 백엔드 배포 프로세스(CodeBuild 실행)가 시작되는 E2E(End-to-End) 흐름을 완성합니다.

## 2. 핵심 변경 사항

이 목표를 달성하기 위해, 기존에 분리되어 있던 `deploy` 람다(배포 요청 접수)와 `repo_inspector` 람다(리포지토리 분석 및 빌드 시작)를 **이벤트 기반 아키텍처**로 연결했습니다.

### 2.1. API Gateway 라우팅 (`terraform/api-gateway.tf`)
- **`POST /deployments` 경로 추가**: 프론트엔드의 '배포하기' 버튼 클릭 시, 배포 요청을 `deploy` 람다(`lambda/deploy/handler.py`)로 전달하는 API 경로를 추가했습니다.

### 2.2. 이벤트 기반 아키텍처 구축

1.  **DynamoDB Stream 활성화 (`terraform/dynamodb.tf`)**:
    -   `deployments` 테이블에 스트림을 활성화했습니다.
    -   이제 이 테이블에 새로운 배포 요청이 `PENDING` 상태로 기록되면, 해당 변경 사항이 '이벤트'로 발생합니다.

2.  **Lambda 트리거 연결 (`terraform/lambda.tf`)**:
    -   `deployments` 테이블에서 발생한 스트림 이벤트를 감지하여, `repo_inspector` 람다(`lambda/repo_inspector/handler.py`)가 **자동으로 실행**되도록 `aws_lambda_event_source_mapping` 리소스를 추가했습니다.

### 2.3. `repo_inspector` 람다 리팩토링 및 기능 구현 (`lambda/repo_inspector/handler.py`)

-   **이벤트 핸들러 변경**: 기존의 API Gateway 이벤트가 아닌, **DynamoDB Stream 이벤트**를 처리하도록 핸들러의 전체 구조를 변경했습니다.
-   **GitHub 인증 로직 구현**:
    -   `userId`를 기반으로 `installations` 테이블에서 `installationId`를 조회합니다.
    -   GitHub App의 Private Key (Secrets Manager에서 가져옴)를 사용하여 **설치 액세스 토큰(`installation_access_token`)**을 발급받습니다.
-   **프레임워크 감지 (`detect_framework`)**: 발급받은 토큰으로 GitHub API를 호출하여, 리포지토리 내의 `pom.xml`, `package.json` 등 핵심 파일을 확인하고 프로젝트의 프레임워크를 감지합니다.
-   **배포 상태 업데이트**: 처리 시작(`PROCESSING`), 빌드 시작(`BUILDING`), 오류 발생(`FAILED`) 등 각 단계마다 `deployments` 테이블의 상태를 업데이트하여 진행 상황을 추적할 수 있도록 구현했습니다.

### 2.4. Terraform 인프라 설정 (`terraform/*.tf`)
-   `repo_inspector` 람다가 GitHub App 인증에 필요한 값(`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_ARN`)을 환경 변수로 참조하도록 설정했습니다.
-   해당 람다의 IAM 역할에 Secrets Manager의 Private Key에 접근할 수 있는 권한을 추가했습니다.

## 3. 전체 흐름 요약

```
1. [FE] '배포하기' 클릭
   -> POST /deployments API 호출
2. [API Gateway] 요청을 'deploy' 람다로 전달
3. [deploy Lambda] 'deployments' DDB 테이블에 배포 정보를 'PENDING' 상태로 저장
4. [DynamoDB Stream] 테이블 변경 감지 -> 이벤트 발생
5. [Lambda Trigger] 'repo_inspector' 람다 호출 (이벤트 정보 전달)
6. [repo_inspector Lambda]
   - 상태를 'PROCESSING'으로 변경
   - GitHub 인증 후 리포지토리 프레임워크 감지
   - 감지된 프레임워크에 맞는 CodeBuild 프로젝트 실행
   - 상태를 'BUILDING'으로 변경
```
