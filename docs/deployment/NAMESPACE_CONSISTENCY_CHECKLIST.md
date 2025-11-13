# 네임스페이스 일관성 점검 체크리스트

> **문서 버전**: v1.1.0  
> **최종 업데이트**: 2025-11-13  
> **목적**: 네임스페이스 변경 시 전체 스택의 일관성을 보장하기 위한 체계적 점검 메뉴얼

---

## 📋 점검 개요

### 점검 대상
네임스페이스 변경 시 **5개 레이어**를 모두 점검해야 합니다:
1. **Kubernetes Manifests** (네임스페이스 정의)
2. **Kustomize Overlays** (서비스 배포 설정)
3. **ArgoCD ApplicationSet** (GitOps 배포 자동화)
4. **Ansible Playbooks** (클러스터 초기 구성)
5. **CI/CD Pipelines** (GitHub Actions - Terraform/Ansible)

### 점검 시점
- 네임스페이스 구조 변경 시 (예: `api` → 도메인별 네임스페이스)
- 새로운 서비스 추가 시
- 인프라 리소스(DB, Cache, MQ) 네임스페이스 변경 시
- Tier/Layer 레이블 정책 변경 시

---

## ✅ Layer 1: Kubernetes Manifests

### 1.1 네임스페이스 정의 파일

**파일**: `k8s/namespaces/domain-based.yaml`

**점검 항목**:
- [ ] 모든 네임스페이스가 정의되어 있는가?
- [ ] `tier` 레이블이 올바른가?
  - `business-logic`: auth, my, scan, character, location, info, chat
  - `integration`: messaging
  - `data`: data
  - `observability`: monitoring
  - `infrastructure`: atlantis
- [ ] `layer` 레이블이 올바른가?
  - Layer 0: observability, infrastructure
  - Layer 2: business-logic
  - Layer 3: integration
  - Layer 4: data
- [ ] `phase` 레이블이 올바른가? (Phase 1/2/3)
- [ ] `app.kubernetes.io/part-of: ecoeco-backend` 레이블이 있는가?

**점검 명령**:
```bash
kubectl get namespaces -l app.kubernetes.io/part-of=ecoeco-backend --show-labels
```

**예상 출력**:
```
auth          Active   layer=2,tier=business-logic,phase=1
my            Active   layer=2,tier=business-logic,phase=1
scan          Active   layer=2,tier=business-logic,phase=1
...
data          Active   layer=4,tier=data
messaging     Active   layer=3,tier=integration
monitoring    Active   layer=0,tier=observability
atlantis      Active   layer=0,tier=infrastructure
```

---

### 1.2 NetworkPolicy

**파일**: `k8s/networkpolicies/domain-isolation.yaml`

**점검 항목**:
- [ ] `data-ingress-from-api` PolicyTier 2 (`business-logic`)에서만 접근 허용하는가?
- [ ] `messaging-ingress-from-api` Policy: Tier 2에서만 접근 허용하는가?
- [ ] `monitoring-ingress` Policy: 모든 네임스페이스에서 접근 가능한가?

**점검 명령**:
```bash
kubectl get networkpolicies -A
kubectl describe networkpolicy data-ingress-from-api -n data
```

**검증 포인트**:
```yaml
# data-ingress-from-api에서
from:
  - namespaceSelector:
      matchLabels:
        tier: business-logic  # ✅ "api" 아님!
```

---

### 1.3 ServiceMonitor (Prometheus)

**파일**: `k8s/monitoring/servicemonitors-domain-ns.yaml`

**점검 항목**:
- [ ] 모든 도메인 네임스페이스를 대상으로 하는 ServiceMonitor가 있는가?
- [ ] `tier` 및 `layer` 레이블이 올바른가?
- [ ] `relabelings`에 `namespace`, `domain`, `phase`, `tier`, `layer` 자동 추가 설정이 있는가?
- [ ] `namespaceSelector.matchNames`가 올바른 네임스페이스 목록을 포함하는가?

**점검 명령**:
```bash
kubectl get servicemonitors -n monitoring
kubectl describe servicemonitor api-services-all-domains -n monitoring
```

**검증 포인트**:
```yaml
# api-services-all-domains ServiceMonitor
selector:
  matchLabels:
    tier: business-logic  # ✅ "api" 아님!

namespaceSelector:
  matchNames:
    - auth
    - my
    - scan
    # ... (모든 도메인 네임스페이스)
```

---

## ✅ Layer 2: Kustomize Overlays

### 2.1 네임스페이스 참조

**파일**: `k8s/overlays/*/kustomization.yaml`

**점검 항목**:
- [ ] 각 도메인의 `namespace` 필드가 도메인명과 일치하는가?
- [ ] `commonLabels.domain`이 올바른가?
- [ ] `commonLabels.phase`가 올바른가?

**점검 명령**:
```bash
grep -r "namespace:" k8s/overlays/*/kustomization.yaml
```

**예상 출력**:
```
k8s/overlays/auth/kustomization.yaml:namespace: auth
k8s/overlays/my/kustomization.yaml:namespace: my
k8s/overlays/scan/kustomization.yaml:namespace: scan
...
```

---

### 2.2 데이터베이스/캐시 연결 문자열

**파일**: `k8s/overlays/*/deployment-patch.yaml`

**점검 항목**:
- [ ] `POSTGRES_HOST`가 올바른 네임스페이스를 참조하는가?
- [ ] `REDIS_HOST`가 올바른 네임스페이스를 참조하는가?
- [ ] `RABBITMQ_HOST`가 올바른 네임스페이스를 참조하는가? (chat 서비스)

**점검 명령**:
```bash
grep -r "POSTGRES_HOST" k8s/overlays/*/deployment-patch.yaml
grep -r "REDIS_HOST" k8s/overlays/*/deployment-patch.yaml
grep -r "RABBITMQ_HOST" k8s/overlays/*/deployment-patch.yaml
```

**예상 출력**:
```
POSTGRES_HOST: postgresql.data.svc.cluster.local  # ✅ "db" 아님!
REDIS_HOST: redis.data.svc.cluster.local          # ✅ "db" 아님!
RABBITMQ_HOST: rabbitmq.messaging.svc.cluster.local  # ✅ "db" 아님!
```

**❌ 잘못된 예**:
```
POSTGRES_HOST: postgresql.db.svc.cluster.local    # ❌ 잘못됨!
REDIS_HOST: redis.default.svc.cluster.local       # ❌ 잘못됨!
```

---

## ✅ Layer 3: ArgoCD ApplicationSet

### 3.1 ApplicationSet 설정

**파일**: `argocd/applications/ecoeco-appset-kustomize.yaml`

**점검 항목**:
- [ ] `generators.list.elements`에 모든 도메인이 정의되어 있는가?
- [ ] 각 도메인의 `namespace` 필드가 도메인명과 일치하는가?
- [ ] `template.metadata.labels.tier`가 `business-logic`인가?
- [ ] `template.spec.destination.namespace`가 `{{namespace}}`로 동적 할당되는가?
- [ ] `syncPolicy.syncOptions`에 `CreateNamespace=true`가 있는가?

**점검 명령**:
```bash
kubectl get applications -n argocd
kubectl describe application ecoeco-api-auth -n argocd
```

**검증 포인트**:
```yaml
# generators.list.elements
- domain: auth
  namespace: auth  # ✅ 도메인명과 일치
  phase: "1"

# template.metadata.labels
labels:
  tier: business-logic  # ✅ "api" 아님!

# template.spec.destination
namespace: '{{namespace}}'  # ✅ 동적 할당
```

---

### 3.2 Ingress 리소스 (추가)

**파일**: 
- `k8s/ingress/domain-based-api-ingress.yaml` (API Services)
- `k8s/ingress/infrastructure-ingress.yaml` (Atlantis, ArgoCD, Grafana, Prometheus)

**점검 항목**:
- [ ] 각 API Ingress가 해당 도메인 네임스페이스에 배포되는가?
  - `auth-ingress` → `auth` 네임스페이스
  - `my-ingress` → `my` 네임스페이스
  - `scan-ingress` → `scan` 네임스페이스
  - ...
- [ ] Ingress.spec.rules[].backend.service.name이 동일 네임스페이스의 Service를 참조하는가?
- [ ] 모든 Ingress가 동일한 ALB Group (`ecoeco-main`)을 사용하는가?
- [ ] ALB Group Order가 올바르게 설정되어 있는가?
  - Health Check: 9
  - API Services: 10-16
  - Infrastructure: 20-40

**점검 명령**:
```bash
# 모든 Ingress 조회
kubectl get ingress -A

# ALB Group 확인
kubectl get ingress -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.metadata.annotations.alb\.ingress\.kubernetes\.io/group\.name}{"\t"}{.metadata.annotations.alb\.ingress\.kubernetes\.io/group\.order}{"\n"}{end}'

# 특정 Ingress 상세 확인
kubectl describe ingress auth-ingress -n auth
```

**예상 출력**:
```
auth          auth-ingress          ecoeco-main    10
my            my-ingress            ecoeco-main    11
scan          scan-ingress          ecoeco-main    12
...
atlantis      atlantis-ingress      ecoeco-main    20
argocd        argocd-ingress        ecoeco-main    21
monitoring    grafana-ingress       ecoeco-main    30
monitoring    prometheus-ingress    ecoeco-main    40
```

**검증 포인트**:
```yaml
# ✅ 올바른 예: Ingress와 Service가 동일 네임스페이스
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: auth-ingress
  namespace: auth  # ✅ Service와 동일
spec:
  rules:
    - path: /api/v1/auth
      backend:
        service:
          name: auth-api  # auth 네임스페이스의 Service
```

```yaml
# ❌ 잘못된 예: Ingress와 Service가 다른 네임스페이스
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  namespace: api  # ❌ 문제!
spec:
  rules:
    - path: /api/v1/auth
      backend:
        service:
          name: auth-api  # auth 네임스페이스의 Service (다른 네임스페이스!)
```

---

## ✅ Layer 4: Ansible Playbooks

### 4.1 네임스페이스 변수

**파일**: `ansible/inventory/group_vars/all.yml` (또는 `terraform/group_vars/all.yml`)

**점검 항목**:
- [ ] `postgres_namespace`가 `data`인가?
- [ ] `redis_namespace`가 `data`인가?
- [ ] `rabbitmq_namespace`가 `messaging`인가?
- [ ] `monitoring_namespace`가 `monitoring`인가?
- [ ] `atlantis_namespace`가 `atlantis`인가? (정의되어 있는가?)

**점검 명령**:
```bash
grep -E "(postgres_namespace|redis_namespace|rabbitmq_namespace|monitoring_namespace|atlantis_namespace)" ansible/inventory/group_vars/all.yml
```

**예상 출력**:
```yaml
postgres_namespace: "data"       # ✅ "db" 아님!
redis_namespace: "data"          # ✅ "db" 아님!
rabbitmq_namespace: "messaging"  # ✅
monitoring_namespace: "monitoring"
atlantis_namespace: "atlantis"
```

---

### 4.2 네임스페이스 생성 Playbook

**파일**: `ansible/playbooks/10-namespaces.yml`

**점검 항목**:
- [ ] `domain-based.yaml` 복사 및 적용 태스크가 있는가?
- [ ] `domain-isolation.yaml` 복사 및 적용 태스크가 있는가?
- [ ] `servicemonitors-domain-ns.yaml` 복사 및 적용 태스크가 있는가?

**점검 명령**:
```bash
grep -A 5 "네임스페이스 YAML 복사" ansible/playbooks/10-namespaces.yml
```

---

### 4.3 데이터베이스/캐시 Role

**파일**: `ansible/roles/{postgresql,redis,rabbitmq}/tasks/main.yml`

**점검 항목**:
- [ ] 각 Role에서 `{{ postgres_namespace }}`, `{{ redis_namespace }}`, `{{ rabbitmq_namespace }}` 변수를 올바르게 사용하는가?
- [ ] 네임스페이스 생성 태스크가 있는가?
- [ ] Secret 이름이 일관되게 사용되는가?
  - PostgreSQL: `postgresql-secret` (❌ `postgres-secret` 아님!)
  - RabbitMQ: `rabbitmq-default-user`

**점검 명령**:
```bash
grep "postgres_namespace" ansible/roles/postgresql/tasks/main.yml
grep "redis_namespace" ansible/roles/redis/tasks/main.yml
grep "rabbitmq_namespace" ansible/roles/rabbitmq/tasks/main.yml

# Secret 이름 확인
grep "kubectl create secret" ansible/roles/postgresql/tasks/main.yml
```

**예상 출력**:
```bash
# PostgreSQL Role
kubectl create secret generic postgresql-secret \  # ✅ "postgres-secret" 아님!
  -n {{ postgres_namespace }} \
  --from-literal=postgres-password='{{ postgres_password }}' \
  --from-literal=username='{{ postgres_username }}' \
  --from-literal=password='{{ postgres_password }}'
```

---

### 4.4 Secret 일관성 (추가)

**Secret 이름 규칙**:
| 서비스 | Secret 이름 | 네임스페이스 | 생성 위치 |
|--------|------------|-------------|----------|
| PostgreSQL | `postgresql-secret` | `data` | `ansible/roles/postgresql/tasks/main.yml` |
| RabbitMQ | `rabbitmq-default-user` | `messaging` | `ansible/roles/rabbitmq/tasks/main.yml` |
| Atlantis | `atlantis-secrets` | `atlantis` | `k8s/atlantis/atlantis-deployment.yaml` |
| AWS Credentials | `aws-credentials` | `workers`, `data`, `scan` | `scripts/create-aws-credentials-secret.sh` |

**점검 항목**:
- [ ] PostgreSQL Secret이 `data` 네임스페이스에 `postgresql-secret` 이름으로 생성되는가?
- [ ] RabbitMQ Secret이 `messaging` 네임스페이스에 생성되는가?
- [ ] AWS Credentials Secret이 필요한 네임스페이스에 모두 생성되었는가?
- [ ] Worker Deployments가 올바른 Secret 이름을 참조하는가?

**점검 명령**:
```bash
# Secret 존재 확인
kubectl get secrets -n data
kubectl get secrets -n messaging
kubectl get secrets -n workers
kubectl get secrets -n atlantis

# PostgreSQL Secret 확인
kubectl get secret postgresql-secret -n data -o yaml

# AWS Credentials Secret 확인
kubectl get secret aws-credentials -n workers -o yaml
kubectl get secret aws-credentials -n data -o yaml
kubectl get secret aws-credentials -n scan -o yaml
```

**Secret 생성 방법**:
```bash
# PostgreSQL Secret (Ansible에서 자동 생성)
# RabbitMQ Secret (Ansible에서 자동 생성)

# AWS Credentials Secret (수동 생성 필요)
export AWS_ACCESS_KEY_ID='your-access-key'
export AWS_SECRET_ACCESS_KEY='your-secret-key'
./scripts/create-aws-credentials-secret.sh
```

---

### 4.5 Ingress Playbook (추가)

**파일**: `ansible/playbooks/07-ingress-resources.yml`

**점검 항목**:
- [ ] ~~`api` 네임스페이스 생성 태스크가 제거되었는가?~~ (✅ 제거됨)
- [ ] `domain-based-api-ingress.yaml` 적용 태스크가 있는가?
- [ ] `infrastructure-ingress.yaml` 적용 태스크가 있는가?
- [ ] ACM 인증서 ARN 치환이 올바르게 작동하는가?

**점검 명령**:
```bash
# api 네임스페이스 생성 태스크가 없어야 함
grep -n "kubectl create namespace api" ansible/playbooks/07-ingress-resources.yml
# ❌ 결과가 나오면 안됨!

# 도메인별 Ingress 적용 태스크 확인
grep -A 5 "도메인별 API Ingress" ansible/playbooks/07-ingress-resources.yml
```

---

## 🔍 통합 점검 스크립트

다음 스크립트를 실행하여 전체 일관성을 자동 점검할 수 있습니다:

```bash
#!/bin/bash
# check-namespace-consistency.sh

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 네임스페이스 일관성 점검 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ERRORS=0

# 1. Kustomize Overlay 점검
echo ""
echo "✅ Layer 2: Kustomize Overlays 점검"
echo "---"

for domain in auth my scan character location info chat; do
    echo -n "  $domain overlay... "
    
    # 네임스페이스 확인
    NS=$(grep "^namespace:" k8s/overlays/$domain/kustomization.yaml | awk '{print $2}')
    if [ "$NS" != "$domain" ]; then
        echo "❌ FAIL: namespace mismatch (expected: $domain, got: $NS)"
        ((ERRORS++))
    else
        echo "✅ OK"
    fi
    
    # 데이터베이스 연결 문자열 확인
    if grep -q "\.db\.svc\.cluster\.local" k8s/overlays/$domain/deployment-patch.yaml 2>/dev/null; then
        echo "  ❌ FAIL: deployment-patch.yaml에서 'db' 네임스페이스 발견 (data 또는 messaging이어야 함)"
        ((ERRORS++))
    fi
done

# 2. ArgoCD ApplicationSet 점검
echo ""
echo "✅ Layer 3: ArgoCD ApplicationSet 점검"
echo "---"

echo -n "  tier 레이블... "
if grep -q "tier: api" argocd/applications/ecoeco-appset-kustomize.yaml; then
    echo "❌ FAIL: 'tier: api' 발견 (business-logic이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 3. Ansible 변수 점검
echo ""
echo "✅ Layer 4: Ansible 변수 점검"
echo "---"

ANSIBLE_VARS="ansible/inventory/group_vars/all.yml"
if [ ! -f "$ANSIBLE_VARS" ]; then
    ANSIBLE_VARS="terraform/group_vars/all.yml"
fi

echo -n "  postgres_namespace... "
PG_NS=$(grep "^postgres_namespace:" $ANSIBLE_VARS | awk '{print $2}' | tr -d '"')
if [ "$PG_NS" != "data" ]; then
    echo "❌ FAIL: expected 'data', got '$PG_NS'"
    ((ERRORS++))
else
    echo "✅ OK"
fi

echo -n "  redis_namespace... "
REDIS_NS=$(grep "^redis_namespace:" $ANSIBLE_VARS | awk '{print $2}' | tr -d '"')
if [ "$REDIS_NS" != "data" ]; then
    echo "❌ FAIL: expected 'data', got '$REDIS_NS'"
    ((ERRORS++))
else
    echo "✅ OK"
fi

echo -n "  rabbitmq_namespace... "
RABBITMQ_NS=$(grep "^rabbitmq_namespace:" $ANSIBLE_VARS | awk '{print $2}' | tr -d '"')
if [ "$RABBITMQ_NS" != "messaging" ]; then
    echo "❌ FAIL: expected 'messaging', got '$RABBITMQ_NS'"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 4. NetworkPolicy 점검
echo ""
echo "✅ Layer 1: NetworkPolicy 점검"
echo "---"

echo -n "  data-ingress-from-api... "
if grep -A 5 "data-ingress-from-api" k8s/networkpolicies/domain-isolation.yaml | grep -q "tier: api"; then
    echo "❌ FAIL: 'tier: api' 발견 (business-logic이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 5. ServiceMonitor 점검
echo ""
echo "✅ Layer 1: ServiceMonitor 점검"
echo "---"

echo -n "  api-services-all-domains... "
if grep -A 10 "api-services-all-domains" k8s/monitoring/servicemonitors-domain-ns.yaml | grep -q "tier: api"; then
    echo "❌ FAIL: 'tier: api' 발견 (business-logic이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 최종 결과
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $ERRORS -eq 0 ]; then
    echo "✅ 모든 점검 통과! 네임스페이스 일관성 확인 완료."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
else
    echo "❌ $ERRORS개 오류 발견! 위 내용을 확인하고 수정하세요."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi
```

**사용법**:
```bash
chmod +x scripts/check-namespace-consistency.sh
./scripts/check-namespace-consistency.sh
```

---

## 📊 점검 매트릭스

| 레이어 | 파일 | 점검 항목 | 예상 값 |
|--------|------|-----------|---------|
| **Layer 1** | `k8s/namespaces/domain-based.yaml` | `tier` 레이블 | `business-logic`, `data`, `integration`, `observability`, `infrastructure` |
| | `k8s/networkpolicies/domain-isolation.yaml` | `namespaceSelector.matchLabels.tier` | `business-logic` (❌ `api` 아님!) |
| | `k8s/monitoring/servicemonitors-domain-ns.yaml` | `selector.matchLabels.tier` | `business-logic`, `data`, `integration`, `observability` |
| **Layer 2** | `k8s/overlays/*/kustomization.yaml` | `namespace` | 도메인명 (auth, my, scan, ...) |
| | `k8s/overlays/*/deployment-patch.yaml` | `POSTGRES_HOST` | `postgresql.data.svc.cluster.local` (❌ `.db.` 아님!) |
| | | `REDIS_HOST` | `redis.data.svc.cluster.local` (❌ `.db.` 아님!) |
| | | `RABBITMQ_HOST` | `rabbitmq.messaging.svc.cluster.local` (❌ `.db.` 아님!) |
| **Layer 3** | `argocd/applications/ecoeco-appset-kustomize.yaml` | `elements[].namespace` | 도메인명 (auth, my, scan, ...) |
| | | `template.metadata.labels.tier` | `business-logic` (❌ `api` 아님!) |
| | | `template.spec.destination.namespace` | `'{{namespace}}'` (동적 할당) |
| **Layer 4** | `ansible/inventory/group_vars/all.yml` | `postgres_namespace` | `data` (❌ `db` 아님!) |
| | | `redis_namespace` | `data` (❌ `db` 아님!) |
| | | `rabbitmq_namespace` | `messaging` |
| | | `monitoring_namespace` | `monitoring` |
| | `ansible/playbooks/10-namespaces.yml` | 네임스페이스 생성 | ✅ 있음 |
| | `ansible/roles/{postgresql,redis,rabbitmq}/tasks/main.yml` | 네임스페이스 변수 사용 | `{{ postgres_namespace }}`, `{{ redis_namespace }}`, `{{ rabbitmq_namespace }}` |
| **Layer 5** | `terraform/templates/hosts.tpl` | `[api_nodes]` 섹션 | 중복 없이 1번만 정의 |
| | | API 노드 | auth, my, scan, character, location, info, chat (7개) |
| | | 제거된 노드 참조 | ❌ api_waste, api_userinfo, api_recycle_info, api_chat_llm |
| | `terraform/outputs.tf` | `ansible_inventory` templatefile 변수 | hosts.tpl과 일치 (7개 API 노드) |
| | `.github/workflows/infrastructure.yml` | Terraform Plan | PR 생성 시 자동 실행 |
| | | Terraform Validate | 템플릿 변수 검증 |

---

## ✅ Layer 5: CI/CD Pipelines

### 5.1 Terraform 템플릿 (Ansible Inventory)

**파일**: `terraform/templates/hosts.tpl`

**점검 항목**:
- [ ] `[api_nodes]` 섹션이 중복되지 않았는가?
- [ ] 모든 API 노드가 현재 14-node 구조와 일치하는가?
  - auth, my, scan, character, location, info, chat (7개)
- [ ] 제거된 노드를 참조하지 않는가?
  - ❌ `api_waste`, `api_userinfo`, `api_recycle_info`, `api_chat_llm`
- [ ] 각 노드의 `domain` 변수가 올바른가?
- [ ] Worker 노드의 `domain` 변수가 올바른가?
  - `worker-storage`: domain=scan
  - `worker-ai`: domain=scan,chat

**점검 명령**:
```bash
# Terraform 템플릿 검증
cd terraform
terraform init
terraform validate

# 템플릿에서 참조하는 변수 확인
grep -n "api_.*_public_ip" templates/hosts.tpl
grep -n "\[api_nodes\]" templates/hosts.tpl  # 중복 확인
```

**예상 결과**:
```
✅ terraform validate: Success! The configuration is valid.
✅ [api_nodes] 섹션은 1번만 나타나야 함
```

---

### 5.2 Terraform Outputs

**파일**: `terraform/outputs.tf`

**점검 항목**:
- [ ] `ansible_inventory` output의 templatefile 변수가 `hosts.tpl`과 일치하는가?
- [ ] 모든 API 노드 변수가 정의되어 있는가?
  - `api_auth_public_ip`, `api_auth_private_ip`
  - `api_my_public_ip`, `api_my_private_ip`
  - `api_scan_public_ip`, `api_scan_private_ip`
  - `api_character_public_ip`, `api_character_private_ip`
  - `api_location_public_ip`, `api_location_private_ip`
  - `api_info_public_ip`, `api_info_private_ip`
  - `api_chat_public_ip`, `api_chat_private_ip`
- [ ] 제거된 노드 변수가 없는가?
  - ❌ `api_waste_*`, `api_userinfo_*`, `api_recycle_info_*`, `api_chat_llm_*`

**점검 명령**:
```bash
# outputs.tf에서 templatefile 변수 확인
grep -A 30 'templatefile.*hosts.tpl' terraform/outputs.tf

# 변수 개수 확인
grep "api_.*_public_ip" terraform/outputs.tf | wc -l  # 7개 (API nodes)
```

---

### 5.3 GitHub Actions Workflow

**파일**: `.github/workflows/infrastructure.yml`

**점검 항목**:
- [ ] Terraform Plan 단계가 정상 실행되는가?
- [ ] Terraform Validate가 통과하는가?
- [ ] PR 생성 시 Terraform Plan이 자동 실행되는가?
- [ ] `main` 브랜치 머지 시 Terraform Apply가 실행되는가?

**점검 명령**:
```bash
# PR 생성 시 자동 실행되는 CI 확인
gh pr checks <PR_NUMBER>

# 실패한 workflow 로그 확인
gh run view <RUN_ID> --log-failed

# 특정 job 로그 확인
gh run view <RUN_ID> --job=<JOB_ID>
```

**예상 결과**:
```
✅ 📋 Terraform Plan      pass
✅ 📊 Deployment Summary  pass
⏭️ ⚙️ Ansible Bootstrap   skipping (main 브랜치만)
⏭️ 🚀 Terraform Apply     skipping (main 브랜치만)
⏭️ 🔄 ArgoCD Sync         skipping (main 브랜치만)
```

**트러블슈팅**:
```bash
# Terraform 템플릿 오류 (변수 누락)
Error: Invalid function argument
  on outputs.tf line 254, in output "ansible_inventory":
 254:   value = templatefile("${path.module}/templates/hosts.tpl", {
Invalid value for "vars" parameter: vars map does not contain key
"api_waste_public_ip", referenced at ./templates/hosts.tpl:33,30-49.

# 해결: hosts.tpl에서 제거된 노드 참조 제거
```

---

### 5.4 Ansible Inventory 자동 생성

**파일**: `ansible/inventory/hosts` (Terraform에서 자동 생성)

**점검 항목**:
- [ ] Terraform Apply 후 `ansible/inventory/hosts` 파일이 올바르게 생성되는가?
- [ ] 모든 API 노드의 `domain` 변수가 올바른가?
- [ ] `[api_nodes]` 그룹에 7개 노드만 있는가?

**점검 명령**:
```bash
# Terraform 실행 후 생성된 Inventory 확인
cat ansible/inventory/hosts

# API 노드 개수 확인
grep -A 10 "\[api_nodes\]" ansible/inventory/hosts | grep "k8s-api" | wc -l  # 7개

# Domain 변수 확인
grep "domain=" ansible/inventory/hosts | grep "k8s-api"
```

**예상 출력**:
```
[api_nodes]
k8s-api-auth ansible_host=... domain=auth
k8s-api-my ansible_host=... domain=my
k8s-api-scan ansible_host=... domain=scan
k8s-api-character ansible_host=... domain=character
k8s-api-location ansible_host=... domain=location
k8s-api-info ansible_host=... domain=info
k8s-api-chat ansible_host=... domain=chat
```

---

## 🚨 주의사항

### 1. Git 브랜치 전략
- 네임스페이스 변경은 **반드시 별도 브랜치에서 작업**하세요.
- 예: `refactor/namespace-cleanup`, `feat/domain-based-namespaces`

### 2. 배포 전 검증
- 네임스페이스 변경 후 **main 브랜치에 머지하기 전** 이 체크리스트를 실행하세요.
- ArgoCD Sync는 `main` 브랜치 머지 즉시 실행되므로, 머지 전에 모든 불일치를 해결해야 합니다.

### 3. 배포 순서
네임스페이스 변경 시 다음 순서를 따르세요:
1. **Ansible Playbook 실행** (클러스터에 새 네임스페이스 생성)
2. **ArgoCD Sync** (자동 또는 수동)
3. **서비스 배포 확인**
4. **네트워크 연결 테스트** (DB, Cache, MQ)

### 4. 롤백 계획
- 변경 전 현재 상태를 Git Tag로 저장하세요.
- 문제 발생 시 즉시 이전 버전으로 롤백하세요.

---

## 📚 참고 문서

- [네임스페이스 전략 분석](../architecture/09-NAMESPACE_STRATEGY_ANALYSIS.md)
- [네임스페이스 마이그레이션 전략](./NAMESPACE_MIGRATION_STRATEGY.md)
- [Telco vs Service 네임스페이스 비교](../architecture/10-TELCO_VS_SERVICE_NAMESPACE.md)
- [GitOps 파이프라인 (Kustomize)](../development/GITOPS_PIPELINE_KUSTOMIZE.md)

---

## 📝 변경 이력

| 버전 | 날짜 | 변경 내역 |
|------|------|-----------|
| v1.1.0 | 2025-11-13 | Layer 5 추가: CI/CD Pipelines (Terraform 템플릿, GitHub Actions) |
| v1.0.0 | 2025-11-13 | 초기 버전 작성 (네임스페이스 일관성 점검 체크리스트) |


