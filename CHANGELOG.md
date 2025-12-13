# Changelog

Eco² Backend 프로젝트의 모든 주목할 만한 변경사항을 기록합니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/)를 따르며,
버전 관리는 [Semantic Versioning](https://semver.org/lang/ko/)을 준수합니다.

---

## [1.0.6] - 2025-12-13

### Added
- **ext-authz Go gRPC 서버 구현 (Auth Offloading)**
  - Envoy `ext_authz` 프로토콜 기반 외부 인가 서버
  - JWT 검증 (HS256) + Redis 블랙리스트 조회
  - 인증 성공 시 `x-user-id`, `x-auth-provider` 헤더 주입
  - 환경 변수 기반 설정 (`config.go`)
  - 의존성 역전 원칙(DIP) 적용: Redis 클라이언트 인터페이스 추상화
- **ext-authz Go 서버 Prometheus 메트릭**
  - `ext_authz_request_duration_seconds`: 전체 요청 처리 시간 (Histogram)
  - `ext_authz_jwt_verify_duration_seconds`: JWT 검증 시간 (Histogram)
  - `ext_authz_redis_lookup_duration_seconds`: Redis 블랙리스트 조회 시간 (Histogram)
  - `ext_authz_requests_total`: 총 요청 수 (Counter, by result/reason)
  - `ext_authz_requests_in_flight`: 동시 처리 요청 수 (Gauge)
  - ServiceMonitor 리소스로 Prometheus 자동 스크래핑 지원
- **도메인별 독립 `metrics.py`**
  - 각 FastAPI 도메인에 자체 Prometheus Registry 및 `/metrics/status` 엔드포인트 구현
  - scan 도메인: 파이프라인/gRPC 비즈니스 메트릭 유지

### Changed
- **Auth 공통 모듈 완전 제거 (Auth Offloading 완료)**
  - `domains/_shared/security/` 삭제 (jwt.py, dependencies.py)
  - ext-authz가 `x-user-id`, `x-auth-provider` 헤더 주입
  - 각 도메인에서 헤더 기반 사용자 정보 추출 (`UserInfo` 모델)
  - `TokenPayload`는 auth 도메인 전용으로 이관 (`domains/auth/core/jwt.py`)
- **Observability 공통 모듈 제거**
  - `domains/_shared/observability/` 삭제
  - 각 도메인에 독립적인 `metrics.py` 구현
- **Dockerfile 멀티스테이지 빌드 최적화**
  - Builder stage: gcc, libpq-dev 설치 및 pip install
  - Runtime stage: libpq5만 포함, non-root 사용자(appuser) 실행
  - Healthcheck: httpx → urllib.request (stdlib)로 의존성 제거
  - auth, my, location, image, character: `_shared` 의존성 제거
- **CI/CD 개선**
  - `ci-services.yml`: `domains/**` 와일드카드를 명시적 도메인 목록으로 변경
  - `domains/ext-authz` 경로 제외 (별도 Go CI에서 처리)
  - observability 변경 시 전체 재배포 트리거 제거
- **ext-authz 서버 로깅 강화**
  - ALLOW/DENY 모두 구조화된 로그 출력
  - method, path, host, user_id, jti, provider, duration 포함

### Fixed
- **my 도메인 provider 처리 단순화**
  - `MyService.get_current_user()`, `update_current_user()`: provider를 Optional에서 필수로 변경
  - ext-authz 헤더에서 provider가 항상 전달되므로 로직 단순화

---

## [1.0.5] - 2025-12-09

### Added
- **Istio Service Mesh 전면 도입**
  - **Ingress Gateway Migration:** 기존 ALB + K8s Ingress 구조에서 Istio Gateway + VirtualService 구조로 전환하여 L7 라우팅 및 보안 제어 강화
  - **Auth Offloading:** 애플리케이션 레벨의 JWT 검증 로직을 제거하고, Istio `RequestAuthentication`과 `EnvoyFilter`로 위임하여 인증 구조 단순화
  - **External Authorization (gRPC):** Istio의 `CUSTOM` Authorization 정책을 적용하여, `auth-api` gRPC 서버(Port 9001)를 통해 블랙리스트 및 만료 여부를 중앙 집중적으로 검사
- **Observability Offloading**
  - 애플리케이션 내부의 HTTP 메트릭 수집 미들웨어를 제거하고, Envoy Sidecar가 수집하는 표준 메트릭으로 전환하여 성능 부하 감소

### Changed
- **JWT 보안 알고리즘 강화**
  - 서명 알고리즘을 `HS256` (대칭키)에서 `RS256` (비대칭키)으로 전환하고, `auth-api`에 JWKS (`/.well-known/jwks.json`) 엔드포인트 구현
- **Secret 관리 최적화**
  - `auth-api` 외 타 도메인 서비스들의 환경 변수 및 External Secret에서 불필요한 `JWT_SECRET_KEY` 제거
- **인프라 프로비저닝 자동화**
  - Istio Ingress Gateway를 위한 전용 노드(`k8s-ingress-gateway`, t3.medium)를 Terraform으로 프로비저닝하고, Ansible로 자동 조인 및 Taint 적용

### Fixed
- **사용자 정보 조회 오류 수정** (`user/me`)
  - 다중 소셜 계정 연동 시 특정 상황에서 잘못된 Provider 정보를 반환하던 문제를 해결 (`last_login_at` 기준 최신 계정 우선 선택 로직 적용)
- **배포 및 네트워크 안정성 확보**
  - `my` 서비스의 DB 연결 오류(`ConnectionRefused`) 및 라우팅 경로(`404`) 문제 해결
  - `image` 서비스의 불필요한 Secret 참조로 인한 배포 실패 수정
  - `NetworkPolicy` 적용으로 인한 타 Namespace 서비스(DB, DNS) 접근 차단 문제 해결 (`Egress` 정책 확장)
  - ArgoCD와 Istio 간의 리소스 상태 불일치(Sync Drift) 문제 해결 (`ignoreDifferences` 적용)

---

## [1.0.0] - 2025-12-02

### Added
- **API 연동 완료**
  - Auth, Scan, Chat, Character, Frontend 간 REST 호출 경로를 표준화하고 서비스 간 토큰 규약을 확정
  - Frontend 배포 파이프라인이 develop → main 릴리스 플로우에 자동 연계되도록 GitHub Actions 조정
- **풀 파이프라인 Chat/Scan 대응**
  - Chat 이미지 메시지가 Scan과 동일한 Vision → Lite RAG → Answer 파이프라인을 실행하도록 통합
  - 텍스트-only 요청도 Waste 텍스트 분류 → 규정 매칭 → 답변 생성 플로우를 그대로 사용

### Changed
- **파이프라인 성능 향상**
  - Vision/텍스트 파이프라인을 `asyncio.to_thread`로 감싸 FastAPI 이벤트 루프 블로킹 제거
  - Prompt 포맷과 Lite RAG 캐시 경로 정리로 평균 응답 시간 18% 단축
- **릴리스 전략**
  - main 브랜치에 README만 유지하고 나머지는 develop 내용을 그대로 반영하도록 배포 규칙 명문화
  - Git Tag `v1.0.0` 생성 후 frontend 정적 자산을 즉시 배포

### Fixed
- Chat 이미지 요청 실패 시 사용자 안내 문구를 개선해 재시도 유도
- Presigned URL 업로드 시 Content-Type 서명 검증 로깅 보강

---

## [0.9.0] - 2025-11-30

### Added
- **도메인 API 1차 완성**
  - Scan API: `/api/v1/scan/classify`, `/task/{id}`, `/categories` 구현으로 Vision→RAG→Answer 파이프라인을 서비스화
  - Character API: `/api/v1/character/catalog` 및 내부 보상/온보딩 엔드포인트 정비
  - My 서비스에서 Character 소유권을 직접 조회할 수 있도록 Repository 계층 연동
- **이미지/AI 워크플로우 통합**
  - `_shared/waste_pipeline` 모듈을 각 도메인에서 공통으로 사용
  - 서비스 간 presigned URL, CDN 정규화 전략 정립

### Changed
- **Auth 세션 정책 조정**
  - Access Token 3일, Refresh Token 6일로 연장해 사용자 경험 개선
  - App-of-Apps 기반 GitOps로 dev/prod에 자동 반영
- **Document/Release 프로세스 개선**
  - develop 전체를 main에 동기화하여 API 개발 결과물을 릴리스
  - README는 main 버전을 유지해 배포 안내 일관성 확보

### Security
- **서비스 간 토큰 검증**
  - Character 내부 엔드포인트(`/api/v1/internal/characters/**`)에 `Authorization: Bearer <CHARACTER_SERVICE_TOKEN_SECRET>` 검증 추가
  - Scan ↔ Character 간 공유 토큰을 SSM Parameter + ExternalSecret으로 관리

---

## [0.8.0] - 2025-11-24

### Added
- **API 연동 준비**
  - Character ↔ Scan 보상 인터페이스 초안 및 `CharacterRewardRequest/Response` 스키마 정비
  - Chat 서비스에 `_shared/waste_pipeline`을 도입해 향후 Vision 파이프라인 통합 기반 마련
- **Frontend 배포 파이프라인 초석**
  - GitHub Actions에 frontend 빌드/배포 Job을 추가하고 환경별 Artefact 저장소 지정

### Changed
- develop 브랜치를 main에 릴리스할 때 README는 main 버전을 유지하고 나머지 파일은 develop을 덮어쓰도록 문서화
- Waste 파이프라인 Prompt를 Markdown 기반으로 정리해 diff/리뷰 편의성 향상

### Fixed
- Character Catalog CSV 필드 검증 로직을 강화해 누락된 match 값이 DB로 저장되지 않도록 방지

---

## [0.7.5] - 2025-11-19

### Fixed
- **ArgoCD Deployment CrashLoopBackOff 문제 해결**
  - Ansible의 Deployment 직접 패치 방식이 command/args 충돌 유발
  - ConfigMap(`argocd-cmd-params-cm`) 기반 설정으로 전환
  - `server.insecure=true` 표준 방식 적용
  - `docs/troubleshooting/ARGOCD_DEPLOYMENT_ISSUES.md` 추가

- **ArgoCD ERR_TOO_MANY_REDIRECTS 문제 해결**
  - ALB HTTPS 종료 환경에서 무한 리디렉션 루프 발생
  - insecure 모드 적용으로 HTTP 트래픽 정상 처리
  - Ingress `backend-protocol: HTTP` annotation 문서화

### Changed
- **Ansible ArgoCD Role 전면 개선** (`ansible/roles/argocd/tasks/main.yml`)
  - Deployment 직접 패치 제거 (비표준 방식)
  - ConfigMap 생성/패치/검증 단계 추가
  - 멱등성 보장 및 에러 핸들링 강화
  - 재시작 프로세스 명시화 (rollout restart + rollout status)

### Added
- ArgoCD insecure 모드 설정 검증 단계
- ConfigMap 존재 여부 확인 및 자동 생성 로직
- 트러블슈팅 가이드 참조 (`LOCAL_CLUSTER_BOOTSTRAP.md`)

---

## [0.7.4] - 2025-11-18

### Added
- **Security Group 아키텍처 단순화**
  - Master/Worker SG 분리 구조를 단일 Cluster SG로 통합
  - 순환 참조 완전 제거 (312줄 → 155줄, 50% 감소)
  - 계층별 책임 분리 (SG: 노드 레벨, NetworkPolicy: Pod 레벨)
  - `docs/architecture/SECURITY_GROUP_SIMPLIFICATION.md` 추가

- **Helm/Kustomize 구조 재확립**
  - Platform 계층: Helm Chart 중심 (`platform/helm/`)
  - Workload 계층: Kustomize base/overlay 패턴 (`workloads/`)
  - CRDs 독립 관리: `platform/crds/` 분리
  - 환경별 patch 방식 통일 (JSON → YAML)
  - `docs/gitops/ARGOCD_HELM_KUSTOMIZE_STRUCTURE.md` 최종 확립

### Changed
- Terraform Security Group 모듈 전면 개편
  - `aws_security_group.k8s_cluster` 통합 생성
  - 14개 노드 모두 `cluster_sg_id` 사용
  - SSM Parameter: `cluster-sg-id` 신규 생성

### Fixed
- `terraform destroy` 시 Security Group DependencyViolation 에러 해결
- SG 삭제 15분+ 대기 문제 완전 제거
- Calico CNI 배포 전략 확립
  - Operator 방식 시도 실패 (Ansible Operator + ArgoCD Operator 충돌)
  - Helm Chart 단일 방식으로 통일 (Ansible에서 1회 설치)
  - VXLAN Always + BGP Disabled 설정 고정
  - `docs/troubleshooting/calico-operator-helm-conflict.md` 추가
- Calico Typha 포트 5473 통신 문제 해결
  - Master ↔ Worker Typha 통신 Security Group 규칙 추가
  - Cluster 내부 통신 self 규칙으로 완전 보장
  - `docs/troubleshooting/CALICO_TYPHA_PORT_5473_ISSUE.md` 추가

### Deprecated
- `master_sg_id`, `worker_sg_id` outputs (하위 호환성 유지, `cluster_sg_id` 사용 권장)

---

## [0.7.3] - 2025-11-17

### Added
- **GitOps Architecture 2.0**
  - ArgoCD App-of-Apps 패턴 전면 도입
  - Sync Wave 기반 계층적 배포 (Wave 0~70)
  - Helm + Kustomize 통합 관리

- **Atlantis 통합**
  - PR 기반 Terraform plan/apply 자동화
  - SSH Unification (단일 키 관리)
  - Terraform 워크플로우 표준화

- **문서 체계 재정립**
  - `docs/architecture/` 구조 개편
  - `docs/gitops/` GitOps 전용 문서
  - `docs/deployment/` 배포 가이드 통합

### Changed
- Ansible 역할 최소화 (부트스트랩 전용)
  - kubeadm init/join
  - Calico CNI (VXLAN)
  - ArgoCD Core 설치
  - 이후 모든 리소스는 ArgoCD 관리

- Namespace 전략 정비
  - 13개 Namespace (tier, domain 레이블)
  - NetworkPolicy 기반 격리
  - RBAC 최소 권한 원칙

### Fixed
- ArgoCD ApplicationSet 패턴 안정화
- ExternalSecrets SSM Parameter 주입 최적화

---

## [0.7.2] - 2025-11-14

### Added
- **도메인별 Ingress 분리**
  - API, ArgoCD, Grafana 독립 Ingress
  - Path 기반 라우팅 최적화
  - ACM Certificate 통합 관리

- **Namespace 전략 문서화**
  - `NAMESPACE_STRATEGY_ANALYSIS.md`
  - Tier 기반 격리 정책
  - 도메인 경계 명확화

### Changed
- Terraform S3 Backend 활성화
  - State 원격 저장
  - 협업 환경 개선
  - State Lock 적용

### Fixed
- Helm template name 생성 오류
- Environment variable optional 처리

---

## [0.7.1] - 2025-11-12

### Added
- **Kustomize 전면 도입**
  - base/overlay 패턴 적용
  - 환경별 설정 분리 (dev/staging/prod)
  - ConfigMap/Secret 관리 개선

- **문서 업데이트**
  - `KUSTOMIZE_BASE_OVERLAY_GUIDE.md`
  - README v0.7.1 반영

### Changed
- ArgoCD Application 구조 Kustomize 기반으로 전환
- Helm Values를 Kustomize patch로 관리

---

## [0.7.0] - 2025-11-08

### Added
- **14-Node 아키텍처 완성**
  - Master: 1 (Control Plane + Monitoring)
  - API Nodes: 7 (auth, my, scan, character, location, info, chat)
  - Worker Nodes: 2 (storage, ai)
  - Infrastructure: 4 (postgresql, redis, rabbitmq, monitoring)

- **Phase별 배포 전략**
  - Phase 1: MVP (auth, my, postgresql, redis)
  - Phase 2: Core (scan, character, location)
  - Phase 3: Extended (info, chat)
  - Phase 4: Workers + RabbitMQ + Monitoring

- **모니터링 스택 강화**
  - Prometheus + Grafana 독립 노드
  - 14-Node 최적화 설정
  - ServiceMonitor CRD 활용

### Changed
- Terraform 14-Node 전용 구성
- Ansible 14-Node 지원
- Helm Charts 14-Node 템플릿

### Fixed
- Node labeling 일관성 확보
- Provider ID 자동 설정 (ALB Controller)

---

## [0.6.0] - 2025-11-05

### Added
- **13-Node 아키텍처**
  - 8GB t3.large Master (Control Plane 전용)
  - 도메인별 전용 노드 (auth, my, scan)
  - RabbitMQ 독립 노드

- **WAL (Write-Ahead Logging)**
  - Celery Worker Storage/AI 분리
  - Eventlet Pool (I/O Bound)
  - Prefork Pool (Network Bound)

- **Eco² 브랜딩**
  - 프로젝트명 확정
  - 비전 및 목표 정립

### Changed
- PostgreSQL 메모리 최적화 (4GB → 도메인별 DB)
- Redis 독립 노드화
- 리소스 비용 최적화 ($253 → $245/월)

---

## [0.5.0] - 2025-11-02

### Added
- **13-Node 기준 문서화**
  - 아키텍처 다이어그램
  - 리소스 배분 전략
  - 노드별 역할 정의

- **FastAPI Health Check**
  - `/health` 엔드포인트
  - Liveness/Readiness Probe
  - Kubernetes 통합

### Changed
- Helm Charts 13-Node 템플릿
- ArgoCD 도메인별 Application
- Ansible 13-Node 지원

---

## [0.4.4] - 2025-10-31

### Added
- **분석 및 계획 문서 재구성**
  - Design Reviews 컬렉션
  - Self-Managed K8s 최종 결정
  - EKS vs Self-Managed 비용 분석

### Changed
- 문서 디렉토리 구조 개편
- `docs/archive/design-reviews/` 아카이브

---

## [0.4.2] - 2025-10-29

### Added
- **Troubleshooting 통합**
  - `docs/troubleshooting/TROUBLESHOOTING.md`
  - Rapid Diagnostics Runbook
  - 실측 사례 기반 가이드

### Changed
- 구식 문서 정리
- 중복 문서 아카이브

### Fixed
- PV cleanup for Released/Failed volumes
- VPC 삭제 지연 문제

---

## [0.4.0] - 2025-10-25

### Added
- **Self-Managed Kubernetes 기반 확립**
  - kubeadm 클러스터 구성
  - Terraform + Ansible IaC
  - Calico CNI (VXLAN)

- **마이크로서비스 아키텍처**
  - 7개 도메인 서비스 분리
  - PostgreSQL 도메인별 DB
  - Redis JWT Blacklist

### Changed
- Self-Managed K8s로 확정
- 비용 최적화 ($253 → $180/월)

---

## [0.3.0] - 2025-10-20

### Added
- **GitOps 기반 구축**
  - ArgoCD 도입
  - GitHub Actions CI/CD
  - GHCR 이미지 레지스트리

- **인프라 자동화**
  - Terraform AWS 프로비저닝
  - Ansible 클러스터 설정
  - Infrastructure as Code

### Changed
- Docker Compose에서 Kubernetes로 전환

---

## [0.2.0] - 2025-10-15

### Added
- **초기 서비스 개발**
  - Auth API (JWT 인증)
  - My Page API
  - Scan API (AI 폐기물 분류)

- **데이터 계층**
  - PostgreSQL 멀티 스키마
  - Redis 캐시
  - RabbitMQ 메시지 큐

### Changed
- FastAPI 프레임워크 표준화
- Pydantic V2 마이그레이션

---

## [0.1.0] - 2025-10-10

### Added
- **프로젝트 초기화**
  - Repository 생성
  - 기본 디렉토리 구조
  - README 작성

- **개발 환경 설정**
  - Poetry 의존성 관리
  - Pre-commit hooks
  - Ruff linter

### Changed
- Python 3.11 기준 설정

---

## 버전 관리 정책

### 버전 번호 체계 (MAJOR.MINOR.PATCH)

- **MAJOR**: 호환성이 깨지는 대규모 변경
  - 아키텍처 전면 개편
  - API 하위 호환성 제거

- **MINOR**: 하위 호환 기능 추가
  - 새로운 서비스/기능 추가
  - 인프라 확장
  - 주요 문서 업데이트

- **PATCH**: 하위 호환 버그 수정
  - 설정 최적화
  - 문서 오류 수정
  - 경미한 리팩토링

### 브랜치 전략

- `main`: 프로덕션 안정 버전
- `develop`: 개발 통합 브랜치
- `feature/*`: 기능 개발
- `refactor/*`: 리팩토링
- `hotfix/*`: 긴급 수정

### 릴리스 프로세스

1. `develop` 브랜치에서 기능 개발
2. PR 리뷰 및 테스트
3. `main` 브랜치 머지
4. Git Tag 생성 (v0.x.x)
5. CHANGELOG.md 업데이트
6. GitHub Release 발행

---

**문서 버전**: 1.0.6
**최종 업데이트**: 2025-12-13
**관리자**: Backend Platform Team
