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
- [ ] 7. Workloads Namespaces Kustomize 생성
- [ ] 8. Workloads NetworkPolicy Kustomize 생성
- [ ] 9. Workloads Data CR Kustomize 생성
- [ ] 10. Workloads APIs Kustomize 생성
- [ ] 11. Clusters App-of-Apps 생성
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

## 7. Workloads Namespaces Kustomize 생성 ⏳

### 작업 항목
- [ ] `workloads/namespaces/base/`: 모든 네임스페이스 정의 (tier, domain 레이블)
- [ ] `workloads/namespaces/overlays/dev/`: dev 환경 레이블/어노테이션 패치
- [ ] `workloads/namespaces/overlays/prod/`: prod 환경 레이블/어노테이션 패치

### 필요 네임스페이스
- `auth`, `my`, `scan`, `character`, `location`, `info`, `chat` (tier: business-logic)
- `data` (tier: data)
- `messaging` (tier: integration)
- `monitoring` (tier: observability)
- `platform-system`, `data-system`, `messaging-system` (Operator 네임스페이스)

### 참고 문서
- `docs/architecture/namespace/NAMESPACE_CONSISTENCY_CHECKLIST.md`
- `docs/architecture/operations/RBAC_NAMESPACE_POLICY.md`

---

## 8. Workloads NetworkPolicy Kustomize 생성 ⏳

### 작업 항목
- [ ] `workloads/network-policies/base/default-deny-all.yaml`: 기본 거부 정책
- [ ] `workloads/network-policies/base/allow-dns.yaml`: CoreDNS 허용
- [ ] `workloads/network-policies/base/data-ingress.yaml`: tier=business-logic → data 허용
- [ ] `workloads/network-policies/base/monitoring-ingress.yaml`: 모든 NS → monitoring 허용
- [ ] `overlays/dev/`: 개발 환경용 느슨한 정책 (선택)
- [ ] `overlays/prod/`: 프로덕션 엄격 정책

### 참고 문서
- `docs/architecture/networking/NETWORK_ISOLATION_POLICY.md`
- `docs/architecture/networking/NAMESPACE_NETWORKPOLICY_INGRESS.md`

### 주의사항
- ALB Controller egress 차단 금지 (ImagePullBackOff 이슈 기록됨)

---

## 9. Workloads Data CR Kustomize 생성 ⏳

### 작업 항목
- [ ] `workloads/data/postgres/base/`: PostgresCluster CR 기본 템플릿
- [ ] `workloads/data/postgres/overlays/dev/`: dev 환경 (replicas: 1)
- [ ] `workloads/data/postgres/overlays/prod/`: prod 환경 (replicas: 3, backup)
- [ ] `workloads/data/redis/base/`: RedisFailover CR 기본
- [ ] `workloads/data/redis/overlays/dev/`: dev 환경
- [ ] `workloads/data/redis/overlays/prod/`: prod 환경

### 참고
- Zalando Postgres Operator: `acid.zalan.do/v1` `postgresql` CR
- Spotahome Redis Operator: `databases.spotahome.com/v1` `RedisFailover` CR

---

## 10. Workloads APIs Kustomize 생성 ⏳

### 작업 항목
- [ ] `workloads/apis/auth/base/`: Deployment + Service + ConfigMap
- [ ] `workloads/apis/auth/overlays/dev/`: 환경변수, replicas, image tag
- [ ] `workloads/apis/auth/overlays/prod/`: 동일 구조
- [ ] 나머지 API: my, scan, character, location, info, chat (동일 패턴)

### 필수 요소
- GHCR pull secret: `imagePullSecrets: [name: ghcr-secret]`
- DB 연결: ExternalSecret 참조 (`postgresql.data.svc.cluster.local`)
- Tier label: `tier=business-logic`, `domain={service}`

---

## 11. Clusters App-of-Apps 생성 ⏳

### 작업 항목
- [ ] `clusters/dev/root-app.yaml`: Dev 환경 루트 Application
- [ ] `clusters/dev/apps/00-crds.yaml`: Wave -1, platform/crds 참조
- [ ] `clusters/dev/apps/05-namespaces.yaml`: Wave 0, workloads/namespaces/overlays/dev
- [ ] `clusters/dev/apps/08-rbac-storage.yaml`: Wave 0, RBAC + StorageClass
- [ ] `clusters/dev/apps/10-platform.yaml`: Wave 10, ExternalSecrets + cert-manager
- [ ] `clusters/dev/apps/15-alb-controller.yaml`: Wave 15, ALB Helm
- [ ] `clusters/dev/apps/20-monitoring-operator.yaml`: Wave 20, kube-prometheus-stack
- [ ] `clusters/dev/apps/25-data-operators.yaml`: Wave 25, Postgres/Redis/RabbitMQ
- [ ] `clusters/dev/apps/30-monitoring-cr.yaml`: Wave 30, Prometheus CR
- [ ] `clusters/dev/apps/35-data-cr.yaml`: Wave 35, DB Instance CR
- [ ] `clusters/dev/apps/58-secrets.yaml`: Wave 58, ExternalSecrets
- [ ] `clusters/dev/apps/60-apis-appset.yaml`: Wave 60+, API ApplicationSet
- [ ] `clusters/dev/apps/70-applications-ingress.yaml`: Wave 70+, Ingress
- [ ] `clusters/prod/`: 동일 구조

### 참고
- `ARGOCD_SYNC_WAVE_PLAN.md` 표 기준
- ApplicationSet generators로 환경 자동 매핑

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
- Root App 배포

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

