# 인증 플로우 정리 (GitHub OAuth + JWT)

## 구성 요소
- 프론트엔드: `frontend/src/config.js`의 `authEndpoint`(기본 `https://api.whaleray.oriduckduck.site/auth/github`)를 사용해 OAuth 시작.
- API Gateway: HTTP API, Lambda authorizer(`auth_verify`)를 거쳐 보호 경로 호출.
- Lambda:
  - `auth/authorize.py` (`/auth/github/start`): OAuth 시작, state 저장.
  - `auth/callback.py` (`/auth/github/callback`): code/state 검증, 사용자 저장, JWT 발급 후 프론트 리다이렉트.
  - `auth/verify.py`: JWT 검증 Lambda authorizer, `userId`/`username`을 컨텍스트로 반환.
  - `auth/me.py` (`/me`): 설치 여부 확인(needInstallation, installUrl).
  - `auth/repositories.py` (`/github/repositories`): GitHub App installation token 발급 후 리포 목록 반환.
  - `auth/installation.py` (`/auth/github/installations`, `/auth/github/install`): 설치 상태 조회/리다이렉트.
  - 서비스/배포: `service` Lambda(`/services`), `manage` Lambda(`/deploy`, `/deployments` 등).

## GitHub App 동작
- OAuth 시작(`authorize.py`): state를 DynamoDB(oauth-states)에 저장 후 GitHub OAuth authorize URL로 302.
- 콜백(`callback.py`):
  - state 검증 실패 시 `/`로 302 + `?error=Invalid or expired state`.
  - code 교환 실패 시 302 + `?error=Token exchange failed: ...`.
  - 사용자 정보/installation 조회 실패 시 302 + `?error=...`.
  - 정상 시 Users/Installations 테이블 저장 → HS256 JWT 발급 → 302로 프론트 리다이렉트(`/?token=...&username=...`).
- installation helpers:
  - `/auth/github/installations`(기본 공개): 상태 조회 및 installUrl 반환. Lambda 없거나 실패하면 프론트는 “GitHub 리포지토리에 접근할 수 없습니다” 메시지.
  - `/auth/github/install`(공개): 설치 대상 선택으로 바로 302. Lambda 없으면 설치 버튼이 작동 안 함.
- 리포 조회(`repositories.py`):
  - authorizer가 `userId` 전달 → Installations 테이블에서 installationId 조회 → GitHub App JWT(RS256)로 installation access token 생성 → `https://api.github.com/installation/repositories` 조회.
  - cryptography/PyJWT 누락 또는 private key 오류 시 500 반환, 프론트는 “Failed to fetch repositories”로 표시.

## 플로우
1) 로그인 시작
   - 프론트 버튼 → `GET {authEndpoint}/start?redirect_uri={frontendUrl}`.
   - Lambda `auth/authorize.py`가 state 생성 후 GitHub OAuth URL로 302 리다이렉트.
2) GitHub 콜백
   - GitHub → `GET /auth/github/callback?code=...&state=...`.
   - `auth/callback.py`가 state 검증, access token 교환, 사용자/installation 저장, HS256 JWT 발급.
   - 프론트엔드로 302 리다이렉트: `https://whaleray.oriduckduck.site/?token=...&username=...`.
3) 프론트 처리
   - `handleAuthCallback()`이 토큰/사용자 저장(localStorage) 후 API 호출 준비.
4) 보호된 API 호출
   - 모든 요청은 `Authorization: Bearer <JWT>` 헤더 포함.
   - API Gateway Lambda authorizer(`auth_verify.py`)가 JWT 검증 후 `userId/username`을 컨텍스트에 넣어 내려보냄.
   - 서비스/배포/리포지토리 Lambda들이 `requestContext.authorizer`에서 `userId`를 읽어 처리.
5) 설치 확인 및 리포지토리 조회
   - `/me`: 설치 여부 확인 후 `needInstallation`/`installUrl` 반환.
   - `/github/repositories`: 설치 테이블에서 installationId 조회 → GitHub App JWT(RS256)로 installation access token 생성 → 리포 목록 반환.

## 프론트 동작 요약
- 로그인: 버튼 클릭 → `/auth/github/start`로 이동. 콜백에서 token/username 세팅 후 `/me` 호출.
- `/me` 결과:
  - `needInstallation=true` → “권한을 부여해주세요” 메시지 + installUrl 버튼.
  - `needInstallation=false` → `/services`, `/github/repositories` 호출.
- API 실패 시:
  - 401/403 → 토큰 삭제/로그아웃 유도.
  - `/github/repositories` 500 → “Failed to fetch repositories” 표시.

## 주요 엔드포인트 요약
- 공개: `GET /auth/github/start`, `GET /auth/github/callback`, `GET /auth/github/install`, `GET /auth/github/installations`(fallback 공개 설정).
- 보호(Authorizer): `/me`, `/services`, `/services/{id}`, `/deploy`, `/deployments`, `/github/repositories`.

## 토큰/서명
- JWT: HS256, 비밀키는 Secrets Manager(`jwt_secret`)에 저장, `auth/callback.py`가 7일 만료 토큰 발급.
- GitHub App JWT: RS256(`PyJWT[crypto]` + `cryptography` 포함)로 서명, 설치 토큰 발급 시 사용.

## 오류 처리 팁
- 403/401인데 Lambda 로그가 없으면: API Gateway에서 authorizer 캐시/도메인 매핑/토큰 누락 여부 확인.
- RS256 관련 에러: `PyJWT[crypto]`/`cryptography` 의존성이 포함됐는지 확인 후 auth 패키지 재배포.
- `/me` Lambda가 없거나 실패하면 프론트는 설치 상태를 알 수 없어 “GitHub 리포지토리에 접근할 수 없습니다”와 설치 버튼만 노출됩니다.
