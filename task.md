# Google Antigravity Task Guidelines

> **Note:** 이 파일은 AI(Antigravity)에게 프로젝트의 맥락과 규칙을 부여하는 기준 문서입니다. `.gitignore`에 포함하여 관리합니다.
> **Context:** 현재 `feat/env-secure-setting` 브랜치에서 작업 중이며, `repo_inspector`의 환경 변수 처리 로직을 별도 람다(`env_builder`)로 분리하는 리팩토링 단계입니다.

## 1. 핵심 행동 수칙 (Rules of Engagement)

### 1.0. 기본 운영 수칙 (Standard Operating Procedures) [MANDATORY]
1.  **언어 준수:** 모든 답변, 주석, 커밋 메시지 설명 등은 반드시 **한국어**로 작성한다.
2.  **단계별 승인 (Step-by-Step Approval):** 모든 작업 절차는 **단일 단계**로 나누어 진행하며, 각 단계마다 사용자의 **명시적 승인**을 받은 후 다음 단계로 넘어간다. 절대 임의로 여러 단계를 한 번에 처리하거나 코드를 실행하지 않는다.

### 1.1. 보수적 리팩토링 원칙 (Conservative Refactoring) [CRITICAL]
1.  **Main Branch 기준 유지:** 기존 `repo_inspector`의 핵심 로직(GitHub 분석, 프레임워크 감지 등)은 **`main` 브랜치의 코드를 100% 신뢰하고 유지**한다. 불필요한 스타일 변경이나 로직 개선을 시도하지 않는다.
2.  **최소한의 개입:** 수정 범위는 **"환경 변수 처리 로직의 이동"**과 **"다음 람다 호출(Invoke) 로직 추가"**로 엄격히 제한한다.
3.  **코드 이동 시 원형 보존:** `env_builder`로 코드를 옮길 때, 기존에 검증된 로직(SSM 저장 등)을 새로 짜지 않고 **그대로 잘라내어 이동(Cut & Paste)**하는 것을 원칙으로 한다.

### 1.2. 보안 원칙 (Security First)
1.  모든 환경 변수는 평문으로 저장하지 않으며, **AWS KMS**로 암호화하여 **SSM Parameter Store**에 저장한다.
2.  Git에는 `.env` 파일이나 민감 정보를 절대 올리지 않는다.

### 1.3. 아키텍처 원칙 (Lambda Chaining)
1.  **단일 책임:** `repo_inspector`는 '분석'만 하고, `env_builder`는 '구축'만 한다.
2.  **비동기 연결:** 두 람다는 `Event` 방식(비동기)으로 연결하여 결합도를 낮춘다.

---

## 2. 기술 전략 및 아키텍처 (Architecture Strategy)

### 2.1. 환경 변수 처리 전략 (ServiceId + Blob)
* **식별자:** `userId` + `repoName` (`serviceId`) 조합 사용.
* **저장 방식:** 파싱 없이 **전체 텍스트(Blob)**를 암호화 저장.
* **초기화:** 초기화 요청 시 **빈 공백**으로 덮어쓰기 (삭제 X).

### 2.2. 람다 체이닝 아키텍처 (Target Structure)
* **Step 1: `repo_inspector` (탐정)**
    * **유지:** 기존 `main` 브랜치의 GitHub 분석 로직.
    * **변경:** 분석 결과를 가지고 `codebuild.start_build`를 호출하던 부분을 **`lambda.invoke(env_builder)`로 교체**.
* **Step 2: `env_builder` (건축가)**
    * **신설:** 기존 `repo_inspector`에 있던 **SSM 저장 로직**과 **CodeBuild 시작 로직**을 이관받음.
    * **동작:** 전달받은 `envFileContent` 처리 후 빌드 트리거.

---

## 3. Todo List (Execution Plan)

### 🚧 Phase 2: 람다 리팩토링 (수술 진행)
**목표:** `main` 브랜치의 안정성을 유지하며 환경 변수 로직만 외과 수술처럼 분리한다.

- [ ] **Step 2.1: 코드 베이스 동기화 (Baseline)**
    - [ ] `git pull origin main`으로 최신 코드를 가져온다. (이것이 기준점이 됨)
- [ ] **Step 2.2: 함수 복제 (Duplicate)**
    - [ ] `lambda/repo_inspector` 폴더 전체를 `lambda/env_builder`로 복사한다. (의존성 및 설정 보존 목적)
- [ ] **Step 2.3: 가지치기 (Prune & Connect)**
    - [ ] `repo_inspector`: **SSM/CodeBuild 로직만 삭제**하고, 끝부분에 `invoke` 코드를 심는다. (나머지 로직 건드리지 않음)
    - [ ] `env_builder`: **GitHub/분석 로직만 삭제**하고, `event`에서 데이터를 꺼내도록 진입점을 수정한다.
- [ ] **Step 2.4: 인프라 수정 (Terraform)**
    - [ ] `lambda.tf`: `env_builder` 리소스 정의.
    - [ ] `iam.tf`: 권한을 기능에 맞게 정확히 분리(Split).

### ⏳ Phase 3: 통합 및 배포 [대기]
- [ ] **Step 3.1: 타겟 배포 (Target Apply)**
    - [ ] 영향 범위를 최소화하기 위해 `-target` 옵션 사용.
- [ ] **Step 3.2: 최종 E2E 테스트**