# Task #2 구현 요약: Repo Inspector와 배포 연동

## 1. 목표 (Goal)
프론트엔드에서 '배포하기' 버튼을 눌렀을 때, 실제 백엔드 배포 프로세스(CodeBuild 실행)가 시작되는 E2E(End-to-End) 흐름을 완성합니다.

## 2. 핵심 변경 사항

팀원의 피드백에 따라, 기존의 DynamoDB 스트림 기반 이벤트 처리 방식에서 **`deploy` 람다가 `repo_inspector` 람다를 직접 호출하는 방식**으로 아키텍처를 변경하여 플로우를 간소화했습니다.

### 2.1. `deploy` 람다 코드 수정 (`lambda/deploy/handler.py`)

-   **`repo_inspector` 람다 직접 호출**: `deploy` 람다가 배포 정보를 담아 `repo_inspector` 람다를 **비동기적으로 직접 호출(invoke)**하도록 변경했습니다.
-   **DynamoDB 상태 관리**: `repo_inspector` 람다 호출 성공 시, `deployments` 테이블에 배포 정보를 `'INSPECTING'` 상태로 저장하도록 수정했습니다.
-   **CORS 헤더 동적 설정**: `_response` 헬퍼 함수에서 `FRONTEND_URL` 환경 변수를 사용하여 `Access-Control-Allow-Origin` 헤더를 동적으로 설정하도록 변경했습니다.

### 2.2. `repo_inspector` 람다 코드 수정 (`lambda/repo_inspector/handler.py`)

-   **직접 호출 이벤트 처리**: DynamoDB 스트림 이벤트 대신, `deploy` 람다로부터 직접 전달받은 JSON 페이로드를 처리하도록 핸들러를 변경했습니다.
-   **DynamoDB 상태 업데이트**: 프레임워크 감지 후, `deployments` 테이블의 배포 상태를 `'BUILDING'` 또는 `'NOT_SUPPORTED'`로 업데이트하도록 수정했습니다. 오류 발생 시 `'FAILED'`로 업데이트합니다.

### 2.3. Terraform 인프라 설정 변경 (`terraform/*.tf`)

-   **`terraform/dynamodb.tf`**:
    -   더 이상 사용하지 않는 `deployments` 테이블의 `stream_enabled` 및 `stream_view_type` 설정을 제거했습니다.
-   **`terraform/lambda.tf`**:
    -   `aws_lambda_event_source_mapping` 리소스를 삭제하여 DynamoDB 스트림과 `repo_inspector` 람다 간의 연결을 끊었습니다.
    -   `aws_lambda_function.deploy` 리소스에 `repo_inspector` 람다의 이름을 전달하는 `REPO_INSPECTOR_FUNCTION_NAME` 환경 변수를 추가했습니다.
    -   `aws_lambda_function.deploy` 리소스에 `FRONTEND_URL` 환경 변수를 추가하여, 람다가 CORS 응답 헤더에 사용할 프론트엔드 URL을 전달하도록 했습니다.
    -   `aws_iam_role_policy.lambda` 리소스에, `deploy` 람다가 `repo_inspector` 람다를 호출할 수 있는 `lambda:InvokeFunction` 권한과 `whaleray-installations` 테이블을 조회할 수 있는 `dynamodb:Query` 권한을 추가했습니다.
-   **`terraform/api-gateway.tf`**:
    -   `aws_apigatewayv2_api.main` 리소스의 `cors_configuration`에서 `allow_origins = ["*"]` 설정을 `allow_origins = ["https://${var.domain_name}", "http://localhost:5173"]` 로 변경하여, 인증된 요청에 대한 CORS 문제를 해결했습니다.

## 3. 새로운 E2E 흐름 요약

```
1. [FE] '배포하기' 클릭 -> POST /deployments API 호출
2. [API Gateway] 요청을 'deploy' 람다로 전달
3. [deploy Lambda]
   - 'repo_inspector' 람다를 배포 정보를 담아 비동기적으로 직접 호출
   - 'deployments' DDB 테이블에 배포 정보를 'INSPECTING' 상태로 저장
   - 사용자에게 응답 (deploymentId, status: INSPECTING)
4. [repo_inspector Lambda] (deploy 람다의 호출로 실행)
   - 전달받은 배포 정보 처리 (GitHub 인증, 리포지토리 프레임워크 감지)
   - 감지 결과에 따라 'deployments' DDB 테이블의 상태를 'BUILDING', 'NOT_SUPPORTED', 'FAILED' 중 하나로 업데이트
```