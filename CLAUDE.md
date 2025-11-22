# WhaleRay Inspector Refactoring - Spring Boot Gradle 지원

## 📋 프로젝트 개요

**목표**: WhaleRay repo_inspector를 개선하여 서브디렉토리에 위치한 Spring Boot + Gradle 프로젝트의 Dockerfile을 순차적으로 탐색하고 정확히 빌드할 수 있도록 한다.

**범위**: Spring Boot + Gradle 프로젝트만 집중 (Node.js, Next.js 제외)

## 🎯 핵심 문제점

### 현재 상황
```
repository/
├── README.md
├── frontend/              # 무시
│   └── package.json
├── backend/               # ← Spring Boot 프로젝트
│   ├── build.gradle      # ← 감지 대상
│   ├── Dockerfile        # ← 현재 찾지 못함
│   ├── src/main/java/
│   └── gradlew
└── docs/
```

### 문제점
1. **프레임워크 감지**: `backend/build.gradle` 감지 → `spring-boot:backend` 리턴
2. **Dockerfile 탐색**: 현재 루트에서만 찾음 → `backend/Dockerfile` 놓침
3. **빌드 실행**: 루트 디렉토리에서 `gradle build` → 실패

## 🏗️ 해결 아키텍처

### 1. 순차적 Dockerfile 탐색 전략
```
1순위: 프로젝트 루트 (backend/)
2순위: 리포지토리 루트 (/)  
3순위: 일반적인 Docker 디렉토리들 (docker/, deploy/, .docker/)
```

### 2. 개선된 프로젝트 감지 로직
```python
def detect_spring_project():
    # 1. build.gradle이 있는 디렉토리 찾기
    # 2. 해당 디렉토리에서 Dockerfile 순차 탐색
    # 3. 빌드 컨텍스트와 소스 디렉토리 결정
```

## 🔧 상세 구현 계획

## Phase 1: 분석 및 설계 단계

### Step 1.1: 현재 코드베이스 완전 분석
**목표**: 기존 repo_inspector 동작 방식을 완전히 이해

**작업 내용**:
- [ ] `lambda/repo_inspector/handler.py` 전체 코드 리뷰
- [ ] `detect_framework()` 함수 동작 방식 문서화
- [ ] `select_codebuild_project()` 매핑 확인
- [ ] CodeBuild 환경변수 전달 방식 확인
- [ ] 현재 에러 처리 로직 분석

**검증 기준**:
- 현재 동작하는 프로젝트 구조 예시 3개 이상 수집
- 실패하는 프로젝트 구조 예시 3개 이상 수집
- 각 케이스별 로그 분석 완료

**커밋**: `docs: analyze current repo_inspector implementation`

---

### Step 1.2: Spring Boot + Gradle 프로젝트 패턴 분석
**목표**: 실제 Spring Boot 프로젝트들의 디렉토리 구조 패턴을 파악

**작업 내용**:
- [ ] 일반적인 Spring Boot 모노레포 구조 조사
- [ ] Gradle 멀티모듈 프로젝트 구조 조사  
- [ ] Dockerfile 위치 패턴 분석
- [ ] build.gradle 위치와 Dockerfile 위치 상관관계 분석

**프로젝트 구조 예시**:
```
# 패턴 1: 단일 프로젝트
project/
├── build.gradle
├── Dockerfile
└── src/

# 패턴 2: 백엔드 서브디렉토리
project/
├── backend/
│   ├── build.gradle
│   ├── Dockerfile
│   └── src/
└── frontend/

# 패턴 3: 분리된 Docker 설정
project/
├── backend/
│   ├── build.gradle
│   └── src/
├── docker/
│   └── Dockerfile
└── deploy/
```

**검증 기준**:
- 최소 10개 이상의 실제 GitHub 리포지토리 구조 분석
- 패턴별 빈도수 및 우선순위 결정
- Dockerfile 탐색 우선순위 알고리즘 설계

**커밋**: `docs: analyze spring boot project patterns`

---

### Step 1.3: Dockerfile 순차 탐색 알고리즘 설계
**목표**: 효율적이고 정확한 Dockerfile 탐색 로직 설계

**알고리즘 설계**:
```python
def find_dockerfile_for_gradle_project(gradle_dir: str, repo_structure: dict) -> dict:
    """
    return {
        'dockerfile_path': 'backend/Dockerfile',
        'build_context': 'backend',  # docker build 실행 디렉토리
        'source_dir': 'backend'      # gradle 명령 실행 디렉토리
    }
    """
    search_paths = [
        f"{gradle_dir}/Dockerfile",           # 1순위: gradle 프로젝트 루트
        f"{gradle_dir}/docker/Dockerfile",   # 2순위: docker 서브디렉토리
        "Dockerfile",                        # 3순위: 리포지토리 루트
        "docker/Dockerfile",                 # 4순위: 루트의 docker 디렉토리
        f"deploy/{gradle_dir}/Dockerfile"    # 5순위: 배포용 디렉토리
    ]
```

**작업 내용**:
- [ ] 탐색 우선순위 알고리즘 상세 설계
- [ ] 빌드 컨텍스트 결정 로직 설계
- [ ] 에러 처리 및 폴백 메커니즘 설계
- [ ] 성능 최적화 방안 검토

**검증 기준**:
- 의사 코드 작성 완료
- 엣지 케이스 5개 이상 고려
- 시간 복잡도 O(n) 이하로 설계

**커밋**: `design: dockerfile discovery algorithm for gradle projects`

---

## Phase 2: 핵심 로직 구현 단계

### Step 2.1: GitHub API 탐색 로직 구현
**목표**: GitHub API를 통해 디렉토리 구조를 효율적으로 탐색하는 기능 구현

**구현할 함수**:
```python
def explore_repository_structure(repo_name: str, branch: str, token: str) -> dict:
    """리포지토리의 전체 구조를 탐색하여 트리 구조로 반환"""

def find_gradle_projects(repo_structure: dict) -> list:
    """build.gradle 파일이 있는 모든 디렉토리 반환"""

def find_dockerfile_candidates(base_dir: str, repo_structure: dict) -> list:
    """특정 디렉토리 기준으로 Dockerfile 후보들을 우선순위별로 반환"""
```

**작업 내용**:
- [ ] GitHub API 트리 조회 최적화
- [ ] 디렉토리 구조 캐싱 로직
- [ ] API 호출 제한 고려한 배치 처리
- [ ] 에러 처리 및 재시도 로직

**검증 기준**:
- 단위 테스트 10개 이상 작성
- 실제 GitHub 리포지토리 3개 이상 테스트
- API 호출 횟수 최적화 확인

**커밋**: `feat: implement github api repository exploration`

---

### Step 2.2: Spring Boot Gradle 감지 로직 구현
**목표**: build.gradle 파일을 정확히 감지하고 Spring Boot 프로젝트임을 확인하는 로직

**구현할 함수**:
```python
def detect_spring_boot_gradle(repo_structure: dict) -> dict:
    """
    return {
        'framework': 'spring-boot-gradle',
        'source_directory': 'backend',
        'gradle_file': 'backend/build.gradle',
        'is_multi_module': False
    }
    """

def verify_spring_boot_project(gradle_dir: str, token: str) -> bool:
    """build.gradle 내용을 확인하여 Spring Boot 프로젝트인지 검증"""
```

**작업 내용**:
- [ ] build.gradle 파일 내용 분석 로직
- [ ] Spring Boot 의존성 확인 로직
- [ ] 멀티모듈 프로젝트 감지
- [ ] Gradle Wrapper 존재 확인

**검증 기준**:
- Spring Boot 프로젝트 정확도 95% 이상
- 일반 Java/Kotlin 프로젝트와 구분 가능
- 멀티모듈 프로젝트 지원

**커밋**: `feat: implement spring boot gradle detection`

---

### Step 2.3: Dockerfile 순차 탐색 로직 구현
**목표**: 설계된 알고리즘에 따라 Dockerfile을 순차적으로 탐색하는 로직 구현

**구현할 함수**:
```python
def find_optimal_dockerfile(gradle_dir: str, repo_structure: dict) -> dict:
    """
    return {
        'dockerfile_path': 'backend/Dockerfile',
        'build_context': 'backend',
        'dockerfile_found': True,
        'search_attempts': ['backend/Dockerfile', 'backend/docker/Dockerfile']
    }
    """
```

**작업 내용**:
- [ ] 우선순위별 Dockerfile 탐색
- [ ] 빌드 컨텍스트 자동 결정
- [ ] Dockerfile 유효성 검증
- [ ] 탐색 과정 로깅

**검증 기준**:
- 6가지 패턴의 프로젝트 구조에서 100% 성공
- 평균 API 호출 횟수 5회 이하
- 탐색 시간 3초 이하

**커밋**: `feat: implement dockerfile sequential discovery`

---

## Phase 3: 통합 및 최적화 단계

### Step 3.1: repo_inspector 메인 로직 리팩토링
**목표**: 기존 detect_framework 함수를 새로운 로직으로 완전히 교체

**리팩토링 범위**:
```python
# 기존
def detect_framework(repository_full_name: str, branch: str, github_token: str) -> Optional[str]:
    # 단순한 파일 존재 확인만
    
# 새로운
def analyze_spring_gradle_project(repository_full_name: str, branch: str, github_token: str) -> dict:
    """
    return {
        'framework': 'spring-boot-gradle',
        'source_directory': 'backend',
        'dockerfile_path': 'backend/Dockerfile',
        'build_context': 'backend',
        'gradle_wrapper': True
    }
    """
```

**작업 내용**:
- [ ] 기존 코드 백업 및 호환성 확인
- [ ] 새로운 분석 로직 통합
- [ ] 환경변수 전달 로직 개선
- [ ] 에러 처리 강화

**검증 기준**:
- 기존 기능 100% 호환성 유지
- 새로운 기능 정상 동작 확인
- 로그 가독성 개선

**커밋**: `refactor: integrate new gradle project analysis logic`

---

### Step 3.2: CodeBuild 환경변수 전달 개선
**목표**: 탐색 결과를 CodeBuild에 정확히 전달하는 로직 구현

**환경변수 설계**:
```bash
SOURCE_DIR=backend              # Gradle 명령 실행 디렉토리
BUILD_CONTEXT=backend          # Docker build 실행 디렉토리  
DOCKERFILE_PATH=backend/Dockerfile  # Dockerfile 상대 경로
HAS_GRADLE_WRAPPER=true        # gradlew 존재 여부
```

**작업 내용**:
- [ ] CodeBuild 시작 시 환경변수 전달
- [ ] 환경변수 검증 로직 추가
- [ ] 로깅 개선

**검증 기준**:
- 모든 필수 환경변수 전달 확인
- CodeBuild 로그에서 변수 확인 가능

**커밋**: `feat: enhance codebuild environment variable passing`

---

## Phase 4: 빌드 스펙 개선 단계

### Step 4.1: spring-boot.yml 빌드스펙 리팩토링
**목표**: 환경변수를 활용하여 동적으로 디렉토리를 변경하고 빌드하는 로직 구현

**새로운 빌드스펙**:
```yaml
version: 0.2
phases:
  pre_build:
    commands:
      - echo "=== Spring Boot Gradle Build Started ==="
      - echo "Source Directory: $SOURCE_DIR"
      - echo "Build Context: $BUILD_CONTEXT" 
      - echo "Dockerfile Path: $DOCKERFILE_PATH"
      - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $ECR_REPOSITORY_URI
  build:
    commands:
      - |
        # 소스 디렉토리로 이동
        if [ -n "$SOURCE_DIR" ] && [ "$SOURCE_DIR" != "." ]; then
          echo "Changing to source directory: $SOURCE_DIR"
          cd $SOURCE_DIR
          pwd
        fi
      - |
        # Gradle 빌드 실행
        if [ -f "gradlew" ]; then
          echo "Using Gradle Wrapper"
          chmod +x gradlew
          ./gradlew clean build -x test --no-daemon
        else
          echo "Using system Gradle"
          gradle clean build -x test
        fi
      - |
        # Docker 빌드 (빌드 컨텍스트로 이동)
        if [ -n "$BUILD_CONTEXT" ] && [ "$BUILD_CONTEXT" != "." ]; then
          echo "Changing to build context: $BUILD_CONTEXT"
          cd "$CODEBUILD_SRC_DIR/$BUILD_CONTEXT"
        fi
      - echo "Building Docker image..."
      - docker build -t $ECR_IMAGE_URI .
  post_build:
    commands:
      - echo "Pushing Docker image to ECR..."
      - docker push $ECR_IMAGE_URI
```

**작업 내용**:
- [ ] 동적 디렉토리 변경 로직 구현
- [ ] Gradle Wrapper 자동 감지
- [ ] 빌드 과정 상세 로깅
- [ ] 에러 처리 강화

**검증 기준**:
- 6가지 프로젝트 패턴에서 모두 성공
- 빌드 시간 기존 대비 120% 이하
- 로그 가독성 크게 개선

**커밋**: `feat: enhance spring-boot buildspec for dynamic directory handling`

---

## Phase 5: 테스트 및 검증 단계

### Step 5.1: 통합 테스트 환경 구축
**목표**: 실제 배포 환경과 동일한 조건에서 테스트할 수 있는 환경 구축

**테스트 시나리오**:
1. **패턴 1**: 루트에 build.gradle + Dockerfile
2. **패턴 2**: backend/ 디렉토리에 build.gradle + Dockerfile
3. **패턴 3**: backend/에 build.gradle, docker/에 Dockerfile
4. **패턴 4**: 멀티모듈 Gradle 프로젝트
5. **패턴 5**: Gradle Wrapper 없는 프로젝트
6. **패턴 6**: Dockerfile이 없는 프로젝트 (자동 생성)

**작업 내용**:
- [ ] 각 패턴별 테스트용 GitHub 리포지토리 생성
- [ ] 테스트 자동화 스크립트 작성
- [ ] 로그 수집 및 분석 도구 구성

**검증 기준**:
- 6가지 패턴 모두 성공률 100%
- 평균 분석 시간 10초 이하
- 빌드 성공률 95% 이상

**커밋**: `test: setup integration test environment`

---

### Step 5.2: 성능 및 안정성 검증
**목표**: 대용량 리포지토리와 복잡한 구조에서도 안정적으로 동작하는지 검증

**테스트 케이스**:
- [ ] 파일 1000개 이상 대용량 리포지토리
- [ ] 깊이 5단계 이상 복잡한 디렉토리 구조
- [ ] API 호출 제한 상황 시뮬레이션
- [ ] 네트워크 지연 상황 테스트
- [ ] 동시 배포 요청 처리 테스트

**검증 기준**:
- 메모리 사용량 256MB 이하 유지
- API 호출 타임아웃 0.1% 이하
- 에러 복구율 95% 이상

**커밋**: `test: verify performance and stability`

---

## Phase 6: 문서화 및 배포 단계

### Step 6.1: 사용자 가이드 문서 작성
**목표**: 개발자들이 WhaleRay에서 Spring Boot 프로젝트를 쉽게 배포할 수 있도록 가이드 제공

**문서 내용**:
- [ ] 지원하는 프로젝트 구조 패턴
- [ ] Dockerfile 작성 가이드
- [ ] 빌드 최적화 팁
- [ ] 트러블슈팅 가이드

**커밋**: `docs: add spring boot deployment guide`

---

### Step 6.2: 프로덕션 배포
**목표**: 새로운 기능을 프로덕션 환경에 안전하게 배포

**배포 순서**:
1. [ ] Terraform 코드 검토 및 승인
2. [ ] Lambda 함수 배포 (Blue-Green)
3. [ ] CodeBuild 프로젝트 업데이트
4. [ ] 카나리 배포로 점진적 적용
5. [ ] 모니터링 및 롤백 준비

**검증 기준**:
- 배포 중 다운타임 0초
- 기존 기능 영향도 0%
- 새 기능 성공률 95% 이상

**커밋**: `deploy: release spring boot gradle support to production`

---

## 🔍 현재 해야 할 작업 우선순위

### 🚀 즉시 시작 (이번 주)
1. **Step 1.1**: 현재 코드베이스 완전 분석
2. **Step 1.2**: Spring Boot + Gradle 프로젝트 패턴 분석
3. **Step 1.3**: Dockerfile 순차 탐색 알고리즘 설계

### ⚡ 다음 단계 (다음 주)  
4. **Step 2.1**: GitHub API 탐색 로직 구현
5. **Step 2.2**: Spring Boot Gradle 감지 로직 구현

### 🎯 중기 목표 (2주 후)
6. **Step 2.3**: Dockerfile 순차 탐색 로직 구현
7. **Step 3.1**: repo_inspector 메인 로직 리팩토링

## 💡 개발 방법론

### 커밋 컨벤션
```
feat: 새로운 기능 추가
fix: 버그 수정  
refactor: 코드 리팩토링
test: 테스트 코드 추가/수정
docs: 문서 추가/수정
design: 설계 문서 작성
```

### 브랜치 전략
- `refactor/inspector`: 메인 개발 브랜치
- `feat/dockerfile-discovery`: Dockerfile 탐색 기능
- `feat/gradle-detection`: Gradle 감지 기능

### 검증 방법
- 각 단계별로 최소 3개 이상의 테스트 케이스
- 단위 테스트 커버리지 80% 이상 유지
- 매 커밋마다 기능 검증 완료

---

## 📞 연락처 및 참고자료

- **프로젝트 리포지토리**: `refactor/inspector` 브랜치
- **테스트 환경**: AWS 개발 계정 
- **문서 위치**: `/docs/spring-gradle-support/`

---

*이 문서는 WhaleRay Inspector 리팩토링 프로젝트의 마스터 플랜입니다. 각 단계별 상세 내용과 진행 상황은 지속적으로 업데이트됩니다.*