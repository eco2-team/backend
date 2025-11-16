# 아키텍처 검증 보고서
**작성일:** 2025-11-16  
**대상:** Terraform + Ansible + ArgoCD + Kustomize + Helm  
**브랜치:** develop

---

## 📋 검증 범위

1. ✅ Terraform 인프라 정의 (14 노드)
2. ✅ Ansible 부트스트랩 + ArgoCD root-app 배포
3. ✅ ArgoCD App-of-Apps 구조
4. ⚠️ Kustomize 구조 (경로 중복 발견)
5. ✅ Helm Charts 정의

---

## ✅ 1. Terraform 검증

### 인프라 정의
```hcl
Master: 1대 (t3.large, 8GB)
API Nodes: 7대
  - auth: t3.micro (Phase 1)
  - my: t3.micro (Phase 1)
  - scan: t3.small (Phase 2)
  - character: t3.micro (Phase 2)
  - location: t3.micro (Phase 2)
  - info: t3.micro (Phase 3)
  - chat: t3.small (Phase 3)

Workers: 2대
  - worker-storage: t3.small (Phase 4)
  - worker-ai: t3.small (Phase 4)

Infrastructure: 4대
  - postgresql: t3.medium (Phase 1)
  - redis: t3.small (Phase 1)
  - rabbitmq: t3.small (Phase 4)
  - monitoring: t3.medium (Phase 4)
```

**결과:** ✅ 정상
- **총 14대** 노드
- Phase별 구분 명확
- IAM Role, VPC, Security Groups 정의됨

---

## ✅ 2. Ansible 검증

### Playbook 구조 (site.yml)
```yaml
1. SSH & Cloud-init 대기
2. Common (OS 설정)
3. Docker 설치
4. Kubernetes 설치
5. Master 초기화
6. Workers join (모든 노드)
7. Provider ID 설정 (ALB Controller용)
8. CNI 설치 (Calico)
9. Node 라벨링
10. Addons (cert-manager, metrics-server)
11. EBS CSI Driver
12. ALB Controller
13. IngressClass
14. ✅ ArgoCD 설치
15. ✅ root-app.yaml 자동 배포 ← 핵심!
16. Namespaces 생성 (Ansible roles)
17. Monitoring (Prometheus Operator)
18. RabbitMQ, Redis, PostgreSQL (Ansible roles)
19. Atlantis
20. Ingress 리소스
21. Route53 업데이트
```

### ArgoCD Role 검증
```yaml
# ansible/roles/argocd/tasks/main.yml (51-60번 줄)
- name: root-app.yaml 복사 (Master 노드로)
  copy:
    src: "{{ playbook_dir }}/../../argocd/root-app.yaml"
    dest: /tmp/root-app.yaml
    mode: '0644'

- name: ArgoCD Root App 배포
  command: kubectl apply -f /tmp/root-app.yaml
```

**결과:** ✅ 정상
- root-app.yaml이 **자동 배포**됨
- develop 브랜치 참조
- Wave 기반 순차 배포 트리거

---

## ✅ 3. ArgoCD App-of-Apps 구조

### Root App 정의
```yaml
# argocd/root-app.yaml
metadata:
  name: root-app
  annotations:
    argocd.argoproj.io/sync-wave: "-2"  # 최우선
spec:
  source:
    repoURL: https://github.com/SeSACTHON/backend
    targetRevision: develop
    path: argocd/apps  # ← 하위 Application 자동 발견
```

### Wave 기반 Application 구조
| Wave | Application | Type | Source Path |
|------|-------------|------|-------------|
| -1 | namespaces | Kustomize | `k8s/namespaces` |
| 0 | infrastructure | Kustomize | `k8s/infrastructure` |
| 20 | alb-controller | Helm | `charts/platform/aws-lb-controller` (external) |
| 40 | monitoring | Helm | `charts/observability/kube-prometheus-stack` |
| 60 | data-clusters | Helm | `charts/data/databases` |
| 70 | gitops-tools | Helm | `charts/platform/atlantis` |
| 80 | api-services | ApplicationSet | `k8s/overlays/{domain}` |
| 80 | workers | Kustomize | `argocd/apps/apis/workers` |

**결과:** ✅ 정상
- App-of-Apps 패턴 완성
- 모든 Application이 develop 브랜치 참조
- Wave 순서대로 배포됨

---

## ⚠️ 4. Kustomize 구조 검증

### 최신 구조

```
k8s/
├── namespaces/          ← Wave 00 (모든 Namespace 단일 관리)
│   ├── kustomization.yaml
│   └── domain-based.yaml
└── infrastructure/
    └── networkpolicies/ ← Wave 01 (보안 리소스)
```

### 검증 결과

