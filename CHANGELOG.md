# Changelog

Eco² Backend 프로젝트의 모든 주목할 만한 변경사항을 기록합니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/)를 따르며,
버전 관리는 [Semantic Versioning](https://semver.org/lang/ko/)을 준수합니다.

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

**문서 버전**: 1.0.0
**최종 업데이트**: 2025-11-18
**관리자**: Backend Platform Team
