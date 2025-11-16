# refactor/gitops-sync-wave 브랜치 작업 체크리스트

> **브랜치**: `refactor/gitops-sync-wave`  
> **목적**: ArgoCD Sync Wave 기반 GitOps 구조 재정립 및 Helm/Kustomize 통합  
> **시작일**: 2025-11-16

---

## 진행 상황 요약

- [x] 1. 문서화 (Architecture Guides)
- [x] 2. Terraform 인프라 Output 확장
- [x] 3. Platform Helm 구조 생성
- [x] 4. Platform CRDs 구조 생성
- [x] 5. Workloads Ingress Kustomize 생성
- [x] 6. ExternalSecrets 구조 생성
- [x] 7. Workloads Namespaces Kustomize 생성
- [x] 8. Workloads NetworkPolicy Kustomize 생성
- [x] 9. Workloads Data CR Kustomize 생성
- [x] 10. Workloads APIs Kustomize 생성
- [x] 10-1. RBAC/Storage Kustomize 생성
- [x] 10-2. IRSA Roles (Terraform)
- [x] 10-3. JSON → YAML patch 전환
- [x] 10-4. overlays 플랫 구조로 변경
- [x] 11. Clusters App-of-Apps 생성
- [x] 11-1. Wave 번호 파일명 일치화
- [ ] 12. Ansible 부트스트랩 전용 정리
- [ ] 13. 최종 검증 및 문서 동기화

---

## 1. 문서화 (Architecture Guides) ✅

### 완료 항목
- [x] `ARGOCD_SYNC_WAVE_PLAN.md`: Wave -1~70+ 정의
- [x] `SYNC_WAVE_SECRET_MATRIX.md`: Wave별 CM/Secret 선행 조건
- [x] `TERRAFORM_SECRET_INJECTION.md`: SSM Parameter 주입 전략
- [x] `ENVIRONMENT_DEPLOYMENT_STRATEGY.md`: dev/staging/prod 환경 분리
- [x] `KUSTOMIZE_BASE_OVERLAY_GUIDE.md`: base/overlay 패턴
- [x] `HELM_PLATFORM_STACK_GUIDE.md`: Helm multi-source 패턴
- [x] `ARGOCD_HELM_KUSTOMIZE_STRUCTURE.md`: 통합 디렉터리 구조
- [x] `NETWORK_ISOLATION_POLICY.md`: L3/L4 격리 정책
- [x] `RBAC_NAMESPACE_POLICY.md`: Tier 기반 RBAC
- [x] `OPERATOR_SOURCE_SPEC.md`: Operator 소스 카탈로그

### 커밋
- `af490de` docs: reorganize architecture guides and sync-wave plan

---

## 2. Terraform 인프라 Output 확장 ✅

### 완료 항목
- [x] `terraform/modules/vpc`: Private Subnet 추가
- [x] `terraform/modules/security-groups`: ALB Security Group 추가
- [x] `terraform/outputs.tf`: Subnet/SG ID outputs 추가
- [x] `terraform/ssm-parameters.tf`: SSM Parameter Store 리소스 생성

### 커밋
- `79ec6d4` infra: add subnet and security group outputs
- `802cc13` infra: add ssm parameters for secret injection

---

## 3. Platform Helm 구조 생성 ✅

### 완료 항목
- [x] `platform/helm/kube-prometheus-stack/`: app.yaml + values/dev|prod.yaml
- [x] `platform/helm/postgres-operator/`: app.yaml (Zalando GitHub source)
- [x] `platform/helm/redis-operator/`: app.yaml (Spotahome GitHub source)
- [x] `platform/helm/rabbitmq-operator/`: app.yaml (RabbitMQ Official GitHub)
- [x] `platform/helm/alb-controller/`: app.yaml + values/dev|prod.yaml
- [x] `platform/helm/calico/`: app.yaml + values/dev|prod.yaml (VXLAN, BGP disabled)
- [x] `platform/helm/README.md`: Multi-source 패턴 가이드

### 커밋
- `6fe49c7` feat: add helm application sets for data/monitoring operators
- `aebbac9` chore: align rabbitmq operator source with spec
- `53c3ead` chore: align redis operator source with spec
- `f227744` chore: align postgres operator source with spec
- `d9694ca` chore: quote applicationsets and update operator sources
- `6715a7e` feat: add calico cni helm applicationset
- `70f4f19` docs: add platform helm multi-source pattern guide
- `f20db2b` feat: add alb controller helm applicationset
- `aaeb2ab` docs: annotate alb values with externalsecret ssm paths
- `f401e37` docs: record alb controller source and update helm apps

---

## 4. Platform CRDs 구조 생성 ✅

### 완료 항목
- [x] `platform/crds/alb-controller/`: kustomization.yaml + README
- [x] `platform/crds/prometheus-operator/`: 7종 CRD kustomization
- [x] `platform/crds/postgres-operator/`: Zalando CRD kustomization
- [x] `platform/crds/external-secrets/`: ESO bundle kustomization

### 커밋
- `9a6be58` feat: add crd kustomizations for platform operators
- `c38eaf2` fix: correct alb controller crd path

---

## 5. Workloads Ingress Kustomize 생성 ✅

### 완료 항목
- [x] `workloads/ingress/apps/base/`: api/argocd/grafana Ingress + default-backend
- [x] `workloads/ingress/apps/overlays/dev/`: JSON6902 patch (host, cert)
- [x] `workloads/ingress/apps/overlays/prod/`: JSON6902 patch

### 커밋
- `3da4fdd` feat: add kustomize ingress overlays

---

## 6. ExternalSecrets 구조 생성 ✅

### 완료 항목
- [x] `workloads/secrets/external-secrets/base/cluster-secret-store.yaml`: AWS SSM 연동
- [x] `workloads/secrets/external-secrets/overlays/dev/alb-controller-secret.yaml`: dev SSM 참조
- [x] `workloads/secrets/external-secrets/overlays/prod/alb-controller-secret.yaml`: prod SSM 참조

### 커밋
- `64bb053` feat: add externalsecrets for alb controller ssm params

---

## 7. Workloads Namespaces Kustomize 생성 ✅

### 작업 항목
- [x] `workloads/namespaces/base/`: 모든 네임스페이스 정의 (tier, domain 레이블)
- [x] `workloads/namespaces/overlays/dev/`: dev 환경 레이블/어노테이션 패치
- [x] `workloads/namespaces/overlays/prod/`: prod 환경 레이블/어노테이션 패치
- [x] `workloads/namespaces/README.md`: 구조 설명

### 완료된 네임스페이스
- `auth`, `my`, `scan`, `character`, `location`, `info`, `chat` (tier: business-logic)
- `postgres`, `redis` (tier: data, data 네임스페이스를 분리)
- `messaging` (tier: integration)
- `monitoring` (tier: observability)
- `platform-system`, `data-system`, `messaging-system` (Operator 네임스페이스)

### 커밋
- `e890116` refactor: split data tier into postgres/redis namespaces
- `a056c69` refactor: use base+overlay pattern for data CRs

### 참고 문서
- `docs/architecture/namespace/NAMESPACE_CONSISTENCY_CHECKLIST.md`
- `docs/architecture/operations/RBAC_NAMESPACE_POLICY.md`

---

## 8. Workloads NetworkPolicy Kustomize 생성 ✅

### 작업 항목
- [x] `workloads/network-policies/base/default-deny-all.yaml`: 기본 거부 정책
- [x] `workloads/network-policies/base/allow-dns.yaml`: CoreDNS 허용
- [x] `workloads/network-policies/base/data-ingress.yaml`: tier=business-logic → postgres/redis 허용
- [x] `workloads/network-policies/base/monitoring-ingress.yaml`: 모든 NS → monitoring 허용
- [x] `overlays/dev/`: base 참조
- [x] `overlays/prod/`: base 참조
- [x] `workloads/network-policies/README.md`: 정책 설명

### 커밋
- `d09b8ee` feat: add workloads namespaces/networkpolicies/data CRs

### 참고 문서
- `docs/architecture/networking/NETWORK_ISOLATION_POLICY.md`
- `docs/architecture/networking/NAMESPACE_NETWORKPOLICY_INGRESS.md`

### 주의사항
- ALB Controller egress 차단 금지 (ImagePullBackOff 이슈 기록됨)

---

## 9. Workloads Data CR Kustomize 생성 ✅

### 작업 항목
- [x] `workloads/data/postgres/base/`: PostgresCluster CR 기본 템플릿
- [x] `workloads/data/postgres/overlays/dev/`: dev 환경 (replicas: 1)
- [x] `workloads/data/postgres/overlays/prod/`: prod 환경 (replicas: 1, backup)
- [x] `workloads/data/redis/base/`: RedisFailover CR 기본
- [x] `workloads/data/redis/overlays/dev/`: dev 환경
- [x] `workloads/data/redis/overlays/prod/`: prod 환경
- [x] `workloads/data/postgres/base/README.md`: Postgres CR 가이드
- [x] `workloads/data/redis/base/README.md`: Redis Failover 가이드
- [x] `workloads/data/README.md`: Data layer 개요

### 커밋
- `a056c69` refactor: use base+overlay pattern for data CRs
- `8b7b8be` chore: set prod data instances to 1 replica

### 참고
- Zalando Postgres Operator: `acid.zalan.do/v1` `postgresql` CR
- Spotahome Redis Operator: `databases.spotahome.com/v1` `RedisFailover` CR

---

## 10. Workloads APIs Kustomize 생성 ✅

### 작업 항목
- [x] `workloads/apis/auth/base/`: Deployment + Service + ConfigMap
- [x] `workloads/apis/auth/overlays/dev/`: 환경변수, replicas, image tag
- [x] `workloads/apis/auth/overlays/prod/`: 동일 구조
- [x] 나머지 API: my, scan, character, location, info, chat (동일 패턴)
- [x] 각 API 디렉터리에 README.md 추가 (7개)

### 커밋
- `7796b6d` feat: add auth api kustomize base+overlays
- `dfb28e0` feat: add all api services kustomize structure

### 필수 요소
- GHCR pull secret: `imagePullSecrets: [name: ghcr-secret]`
- DB 연결: ExternalSecret 참조 (`postgresql.data.svc.cluster.local`)
- Tier label: `tier=business-logic`, `domain={service}`

---

## 11. Clusters App-of-Apps 생성 ✅

### 작업 항목
- [x] `clusters/dev/root-app.yaml`: Dev 환경 루트 Application
- [x] `clusters/dev/apps/00-crds.yaml`: Wave 0, platform/crds 참조
- [x] `clusters/dev/apps/02-namespaces.yaml`: Wave 2, workloads/namespaces/dev
- [x] `clusters/dev/apps/03-rbac-storage.yaml`: Wave 3, RBAC + StorageClass
- [x] `clusters/dev/apps/05-calico.yaml`: Wave 5, Calico CNI
- [x] `clusters/dev/apps/06-network-policies.yaml`: Wave 6, NetworkPolicy
- [x] `clusters/dev/apps/10-secrets-operator.yaml`: Wave 10, ExternalSecrets Operator
- [x] `clusters/dev/apps/11-secrets-cr.yaml`: Wave 11, ExternalSecret CR
- [x] `clusters/dev/apps/15-alb-controller.yaml`: Wave 15, ALB Helm
- [x] `clusters/dev/apps/20-monitoring-operator.yaml`: Wave 20, kube-prometheus-stack
- [x] `clusters/dev/apps/25-data-operators.yaml`: Wave 25, Postgres/Redis/RabbitMQ
- [x] `clusters/dev/apps/35-data-cr.yaml`: Wave 35, DB Instance CR
- [x] `clusters/dev/apps/60-apis-appset.yaml`: Wave 60, API ApplicationSet
- [x] `clusters/dev/apps/70-ingress.yaml`: Wave 70, Ingress
- [x] `clusters/dev/README.md`: Dev 환경 가이드
- [x] `clusters/prod/`: 동일 구조 (13개 Application)
- [x] `clusters/prod/README.md`: Prod 환경 가이드

### 커밋
- `4303d13` feat: add dev cluster app-of-apps structure
- `f9e66ae` feat: complete dev/prod cluster app-of-apps
- `bfb718a` fix: correct prod cluster structure
- `ddb97c5` feat: add prod cluster apps
- `9576289` docs: update clusters readme with complete wave list
- `d8c18da` refactor: rename platform to secrets-operator, move secrets to wave 11
- `91cda51` fix: ensure calico before network policies
- `9caed4c` refactor: align filenames with wave numbers
- `e4a0230` docs: update wave plan with actual numbers and filenames

### 참고
- `ARGOCD_SYNC_WAVE_PLAN.md` 표 기준
- ApplicationSet generators로 환경 자동 매핑

---

## 10-1. RBAC/Storage Kustomize 생성 ✅

### 완료 항목
- [x] `terraform/irsa-roles.tf`: ExternalSecrets, Postgres Operator IAM Roles
- [x] `workloads/rbac-storage/base/`: ServiceAccounts, ClusterRoles, Roles, StorageClass
- [x] `workloads/rbac-storage/dev/`: cluster-admin 전체 권한
- [x] `workloads/rbac-storage/prod/`: SA별 최소 권한 RoleBindings
- [x] `workloads/rbac-storage/README.md`
- [x] `docs/architecture/operations/RBAC_NAMESPACE_POLICY.md`: 환경별 전략 추가

### 커밋
- `761fa55` feat: add irsa roles and rbac/storage kustomize
- `af8c30f` feat: add dev/prod rbac strategy and bindings

---

## 10-2. Kustomize 구조 개선 ✅

### 완료 항목
- [x] JSON6902 patch → YAML Strategic Merge Patch 전환
- [x] overlays/ 디렉터리 제거, dev/prod를 base와 같은 레벨로 플랫화
- [x] `resources: ../../base` → `resources: ../base` 경로 수정
- [x] clusters/dev/apps 경로 업데이트 (`overlays/dev` → `dev`)

### 커밋
- `63d2a3f` refactor: convert json patches to yaml strategic merge
- `77d694c` refactor: flatten overlay structure to follow k8s best practice

---

## 12. Ansible 부트스트랩 전용 정리 ⏳

### 작업 항목
- [ ] `ansible/` 디렉터리 검토: 클러스터 구성 + ArgoCD 설치만 남기기
- [ ] DB/Redis/RabbitMQ/Monitoring 설치 role 제거 (Helm/Operator로 대체)
- [ ] Ingress 생성 playbook 제거 (Kustomize로 대체)
- [ ] `ansible/site.yml` 간소화
- [ ] `docs/architecture/deployment/ANSIBLE-TASK-CLASSIFICATION.md` 업데이트

### 유지할 항목
- Kubernetes 클러스터 초기화 (kubeadm init/join)
- ArgoCD 설치
- SSM Parameter 조회 (IRSA, VPC ID 등)
- ArogCD Root App 배포

---

## 13. 최종 검증 및 문서 동기화 ⏳

### 작업 항목
- [ ] 모든 `platform/helm/*/app.yaml` YAML 문법 검증
- [ ] `workloads/` 하위 모든 kustomization.yaml 파싱 검증
- [ ] Wave 번호 일관성 체크 (문서 vs 실제 app.yaml)
- [ ] ExternalSecret `remoteRef.key` 경로와 SSM Parameter 이름 일치 확인
- [ ] RBAC/Tier 레이블 일관성 검증
- [ ] `tmp/` 디렉터리 정리 (`.gitignore` 추가)
- [ ] 문서 링크 검증 (상호 참조 깨진 곳 없는지)
- [ ] README 업데이트 (새 구조 반영)

---

## 작업 순서 (중요)

1. **문서 → 인프라 → 플랫폼 → 워크로드 → 클러스터** 순서 준수
2. 각 단계마다 YAML 문법 검증 후 커밋
3. Secrets 선행 조건 만족 여부 체크 (Wave 의존성)
4. Ansible 정리는 **새 구조 검증 완료 후** 마지막에 진행

---

## 참고 문서
- `docs/architecture/gitops/ARGOCD_SYNC_WAVE_PLAN.md`
- `docs/architecture/gitops/SYNC_WAVE_SECRET_MATRIX.md`
- `docs/architecture/gitops/ARGOCD_HELM_KUSTOMIZE_STRUCTURE.md`
- `docs/architecture/deployment/ENVIRONMENT_DEPLOYMENT_STRATEGY.md`

---

> 각 항목 완료 시 체크 표시하고, 관련 커밋 SHA를 기록한다.

