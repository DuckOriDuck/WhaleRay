# DynamoDB 테이블 개요
모든 테이블은 `PAY_PER_REQUEST` billing을 사용합니다. 테이블별로 키 구조와 용도를 정리했습니다.

## whaleray-users
| 항목 | 값 |
| --- | --- |
| 파티션 키 | `userId` (S) |
| GSI | `GithubUsernameIndex` (PK: `githubUsername`) |
| TTL | 없음 |
| 용도 | OAuth 콜백에서 사용자 정보 저장/업데이트 |

## whaleray-oauth-states
| 항목 | 값 |
| --- | --- |
| 파티션 키 | `state` (S) |
| GSI | 없음 |
| TTL | `expiresAt` (10분) |
| 용도 | `/auth/github/start`에서 생성한 state 저장·콜백 검증 |

## whaleray-deployments
| 항목 | 값 |
| --- | --- |
| 파티션 키 | `deploymentId` (S) |
| GSI | `userId-index` (PK: `userId`, SK: `createdAt`) |
| TTL | 없음 |
| 용도 | 배포 이력 조회(`/deployments`) |

## whaleray-services
| 항목 | 값 |
| --- | --- |
| 파티션 키 | `serviceId` (S) |
| GSI | `userId-index` (PK: `userId`) |
| TTL | 없음 |
| 용도 | 서비스 목록/상세(`/services`, `/services/{id}`) |

## whaleray-installations
| 항목 | 값 |
| --- | --- |
| 파티션 키 | `installationId` (S) |
| GSI | `userId-index` (PK: `userId`) |
| TTL | 없음 |
| 용도 | GitHub App 설치 조회(`/github/repositories`, `/me`) |
