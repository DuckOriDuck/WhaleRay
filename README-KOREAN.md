# WhaleRay : Github와 호환되는 원클릭 배포 PaaS
WhaleRay의 원활한 GitHub App 통합으로 단 몇 초만에 AWS에 배포하세요. 리포지토리를 연결하고, 배포를 클릭하면 나머지는 저희가 처리합니다

*TODO: 현재 Whaleray 서버는 일시적으로 오프라인 상태입니다. '[Ducksnest](https://github.com/DuckOriDuck/ducksnest-homelab)' 하이브리드 클라우드 쿠버네티스 클러스터와 통합해 제 홈랩 인프라에서 임시 배포를 가능하게 할 예정입니다.*

#### You can see english docs in [here](README.md)

#### Preliminary entry for Softbank Hackathon 2025 in Korea
<img width="1987" height="334" alt="image" src="https://github.com/user-attachments/assets/4a3c9ec5-53b3-4166-80b7-9b3d95e0676f" />

---
# 주요 기능
## 1. 안전한 GitHub App 연동 - 토큰 입력 불필요

원클릭 GitHub OAuth 인증으로 개인 액세스 토큰이 필요 없습니다. WhaleRay는 사용자 자격 증명을 저장하지 않아 토큰 노출 위험을 제거하면서 안전한 리포지토리 액세스를 제공합니다.

---

## 2. 원클릭 배포
- Dockerfile이나 빌드 스크립트를 한 줄도 작성하지 않고 Spring Boot 애플리케이션을 배포하세요. 시스템이 자동으로 리포지토리를 분석하고 최적의 빌드 환경을 구성합니다.
<img width="2069" height="1482" alt="image" src="https://github.com/user-attachments/assets/15e7ae2f-bb84-4b5d-b220-ca82eb242d9a" />

### 자동 감지 전략

- **프레임워크 감지**: 리포지토리에서 `build.gradle` 또는 `pom.xml`을 감지하여 Spring Boot 프로젝트를 자동으로 식별합니다
- **스마트 이미지 생성**: `Dockerfile`이 없는 경우, 시스템이 Eclipse Temurin JDK 17(Alpine) 기반의 최적화된 이미지를 자동으로 주입합니다
- **커스텀 Dockerfile 지원**: 커스텀 `Dockerfile`이 포함된 경우, 우선적으로 사용되어 빌드 프로세스에 적용됩니다

### 빌드 프로세스 주입

- `deployment_id` 및 `ECR_IMAGE_URI`와 같은 필수 메타데이터가 빌드 프로세스 중에 환경 변수로 동적으로 주입됩니다
- Gradle Wrapper(`gradlew`)의 존재 여부를 자동으로 감지하고 그에 따라 빌드 명령을 조정합니다

### 실시간 배포 모니터링

**INSPECTING**, **BUILDING**, **RUNNING**, **FAILED** 등의 여러 상태를 통해 배포 진행 상황을 추적하세요.

<img width="2094" height="504" alt="image" src="https://github.com/user-attachments/assets/4ae51dc3-8122-4daf-b965-03c76858025f" />

*배포 탭에서 실시간으로 배포 상태 모니터링*

<img width="2091" height="1556" alt="image" src="https://github.com/user-attachments/assets/d821a214-2fb5-4ecd-8566-f3d932584cef" />

*AWS CodeBuild에서 직접 가져온 실시간 로그 확인*

<img width="2077" height="490" alt="image" src="https://github.com/user-attachments/assets/bd703bb9-fbc7-4630-994b-23a7d3aa4850" />

*빌드 성공 시 배포 상태가 자동으로 "RUNNING"으로 업데이트*

- 서비스의 고유한 서브도메인에서 배포된 서비스를 확인할 수 있으며, 각 서비스는 하나의 리포지토리와 고유하게 연결되어 고정된 도메인을 소유합니다


---

## 3. 동적 라우팅 및 무중단 업데이트

각 서비스는 고유한 서브도메인과 경로를 받으며, 배포 중에 무중단을 보장하는 버전 업데이트를 제공합니다.

### 고유한 서비스 URL 구조

모든 배포된 서비스는 고정된 고유 도메인을 통해 액세스할 수 있습니다:
```
https://service.whaleray.oriduckduck.site/{user-id}-{organization-name}-{repository-name}
```

<img width="2119" height="391" alt="image" src="https://github.com/user-attachments/assets/3f5d52a1-7e4b-4500-81f8-39849b336a6b" />
<img width="2879" height="1636" alt="image" src="https://github.com/user-attachments/assets/932da05a-84bb-4106-aa08-59e090509621" />

*고유한 서브도메인을 통해 배포된 서비스에 액세스*

WhaleRay는 리포지토리당 하나의 서비스만 유지합니다. 이미 배포된 리포지토리를 재배포할 경우, 기존 인스턴스가 종료되고 새로운 빌드 버전으로 교체됩니다.

### 동적 트래픽 라우팅
- WhaleRay는 서브 도메인 내부에서 배포된 서비스들을 즉시 확인할 수 있도록 하고자 했습니다.
- 기존의 AWS ALB 규칙(Rule) 기반 라우팅은 서비스가 늘어날 때마다 인프라 리소스(ALB Listening Rule, Target Group)를 변경해야 하는 **구조적 한계(Hard coupling)**가 있었습니다. 이를 극복하고 100개 이상의 서비스를 유연하고 빠르게 수용하기 위해, Nginx와 AWS Cloud Map을 결합한 동적 서비스 디스커버리(Dynamic Service Discovery) 패턴을 설계했습니다.
<img width="1593" height="602" alt="image" src="https://github.com/user-attachments/assets/fdbe746f-cec2-4f48-b77f-9d39b2b40f53" />

- **ALB 제한 극복**: 배포되는 서비스별로 ALB 규칙을 생성하는 대신, 모든 트래픽을 Nginx 라우터로 전달하여 인프라 제약 없는 확장성을 확보했습니다.
- **Nginx 라우터**: 정규 표현식 패턴(`^/(?<deployment_id>github_[^/]+)`)을 사용하여 URL 경로에서 Service ID를 추출하고, 이를 기반으로 트래픽을 라우팅합니다.
- **서비스 디스커버리(AWS Cloud Map)**: ECS 태스크가 실행되면 자신의 프라이빗 IP를 `whaleray.local` 네임스페이스에 고유 Service ID와 매핑하여 자동 등록합니다. Nginx는 내부 DNS 리졸버를 통해 이 IP를 동적으로 조회하여 사용자 요청을 연결합니다.

- **Perks**:
  - **Managed Security**: ALB 레벨에서 TLS Termination을 처리하여, 컨테이너는 가벼운 HTTP 통신에만 집중하도록 설계했습니다. 이를 통해 사용자는 별도의 설정 없이 HTTPS 서비스를 제공받습니다.
  - **Deterministic Routing**: 서비스 식별을 위한 고정 Path 정책을 통해 사용자는 배포 환경과 무관하게 **불변의 서비스 엔드포인트**를 확보합니다. 이는 Google/Facebook/Naver 로그인(OAuth)의 Redirect URI 구성을 간소화하여 운영 효율을 높입니다.

### 배포 전략

- 배포 ECS 서비스는 **최소 정상 비율: 100%** 및 **최대 비율: 200%**로 구성해, 신규 빌드 컨테이너가 100% 정상(실행 중) 상태에 도달한 후 기존 컨테이너가 종료되도록 설계했습니다.
- 이를 통해 새 빌드 적용 시 무중단 업데이트를 보장하여 지속적인 서비스 가용성을 유지합니다

---

## 4. AI 기반 빌드 로그 분석

배포가 실패하면 수천 줄의 로그를 수동으로 분석할 필요가 없습니다. AWS Bedrock과 통합된 AI 에이전트가 근본 원인을 진단해줍니다.

<img width="2030" height="521" alt="image" src="https://github.com/user-attachments/assets/a1ac66ed-4da4-4291-8f18-8f04b3629b4f" />

*단 한 번의 클릭으로 AI 기반 분석 실행*

### 스마트 로그 필터링

- **비용 및 속도 최적화**: 전체 로그를 LLM에 전송하는 대신, Lambda 전처리기가 데이터를 지능적으로 필터링합니다
- **노이즈 감소**: 정규 표현식 패턴을 사용하여 불필요한 메타데이터(예: `START RequestId`)를 제거합니다
- **컨텍스트 추출**: 오류 컨텍스트가 가장 집중된 로그의 마지막 50줄에 초점을 맞춥니다

### Claude 3 Haiku 통합

<img width="2051" height="1490" alt="image" src="https://github.com/user-attachments/assets/9f22da89-2876-44d6-b62f-c4c9227ec647" />
<img width="2032" height="1485" alt="image" src="https://github.com/user-attachments/assets/6fbd0782-61b1-4ee0-8cd2-fd1c6b664060" />
*식별된 문제와 실행 가능한 권장 사항이 포함된 구조화된 분석 수신*

- 추출된 로그는 DevOps 엔지니어 페르소나가 주입된 프롬프트와 함께 Claude 3 haiku로 전송됩니다
- 평문 대신 구조화된 JSON 출력(`status`, `issues`, `recommendations`)을 반환하여 프론트엔드에서 즉시 시각화해 유저에게 보여줍니다.
- 전체 프로세스는 동기적으로 실행되어 버튼 클릭 후 몇 초 내에 분석 보고서를 제공합니다


## Tech Stack:
- **Cloud**: AWS
- **IaC**: Terraform
- **Authentication**: GitHub App
- **Backend**: API Gateway HTTP API + Lambda + Bedrock
- **User Deployment Platform**: ECS Fargate
- **Subnet Domain Routing**: Application Load Balancer + NginX + CloudMap
- **Database(Server State Management)**: DynamoDB (Users, Deployments, Services)
- **Frontend**: React + Vite

## Architecture
<img width="1100" height="935" alt="image" src="https://github.com/user-attachments/assets/4daa2cfc-395b-4c48-9c8a-9c7939dcac7d" />


## 라이선스

MIT
