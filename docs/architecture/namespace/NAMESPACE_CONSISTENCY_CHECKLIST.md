# 네임스페이스 일관성 점검 체크리스트

> **문서 버전**: v1.1.0  
> **최종 업데이트**: 2025-11-13  
> **목적**: 네임스페이스 변경 시 전체 스택의 일관성을 보장하기 위한 체계적 점검 메뉴얼

---

## 📋 점검 개요

### 점검 대상
네임스페이스 변경 시 **5개 영역**을 모두 점검해야 합니다:
1. **Kubernetes Manifests** (네임스페이스 정의)
2. **Kustomize Overlays** (서비스 배포 설정)
3. **ArgoCD ApplicationSet** (GitOps 배포 자동화)
4. **Ansible Playbooks** (클러스터 초기 구성)
5. **CI/CD Pipelines** (GitHub Actions - Terraform/Ansible)

### 점검 시점
- 네임스페이스 구조 변경 시 (예: `api` → 도메인별 네임스페이스)
- 새로운 서비스 추가 시
- 인프라 리소스(DB, Cache, MQ) 네임스페이스 변경 시
- Tier 레이블 정책 변경 시

---

## ✅ Kubernetes Manifests

### 1.1 네임스페이스 정의 파일

#### 1.1.1 네임스페이스 기준 표 (Authoritative Matrix)

> `workloads/namespaces/base/namespaces.yaml`과 Terraform 노드 맵핑을 한 번에 확인하기 위한 기준표입니다. 아래 표와 불일치하는 항목이 발견되면 **반드시 수정 및 재검증** 절차를 거칩니다.

| Tier | Namespace | 필수 Label 세트 | 주요 역할/리소스 | 전용 노드 & Taint |
|------|-----------|-----------------|------------------|-------------------|
| business-logic | `auth` | `tier=business-logic`, `domain=auth`, `role=api`, `app.kubernetes.io/part-of=ecoeco-backend` | Auth API Deploy/Service/Secret | `k8s-api-auth`, taint `domain=auth:NoSchedule` |
| business-logic | `my` | `tier=business-logic`, `domain=my`, `role=api`, `app.kubernetes.io/part-of=ecoeco-backend` | My API | `k8s-api-my`, `domain=my:NoSchedule` |
| business-logic | `scan` | `tier=business-logic`, `domain=scan`, `role=api`, `app.kubernetes.io/part-of=ecoeco-backend` | Scan API + 이미지 처리 | `k8s-api-scan`, `domain=scan:NoSchedule` |
| business-logic | `character` | `tier=business-logic`, `domain=character`, `role=api`, `app.kubernetes.io/part-of=ecoeco-backend` | Character/Mission API | `k8s-api-character`, `domain=character:NoSchedule` |
| business-logic | `location` | `tier=business-logic`, `domain=location`, `role=api`, `app.kubernetes.io/part-of=ecoeco-backend` | Location/Map API | `k8s-api-location`, `domain=location:NoSchedule` |
| business-logic | `info` | `tier=business-logic`, `domain=info`, `role=api`, `app.kubernetes.io/part-of=ecoeco-backend` | Recycle-Info API | `k8s-api-info`, `domain=info:NoSchedule` |
| business-logic | `chat` | `tier=business-logic`, `domain=chat`, `role=api`, `app.kubernetes.io/part-of=ecoeco-backend` | Chat/LLM API | `k8s-api-chat`, `domain=chat:NoSchedule` |
| data | `postgres` | `tier=data`, `data-type=postgres`, `role=database`, `app.kubernetes.io/part-of=ecoeco-backend` | `postgresql` CR, DB Secret | `k8s-postgresql`, `node-role.kubernetes.io/infrastructure=true:NoSchedule` |
| data | `redis` | `tier=data`, `data-type=redis`, `role=cache`, `app.kubernetes.io/part-of=ecoeco-backend` | `RedisFailover` CR, Sentinel | `k8s-redis`, `node-role.kubernetes.io/infrastructure=true:NoSchedule` |
| integration | `rabbitmq` | `tier=integration`, `role=messaging`, `app.kubernetes.io/part-of=ecoeco-backend` | RabbitMQ Cluster/Stream | `k8s-rabbitmq`, `node-role.kubernetes.io/infrastructure=true:NoSchedule` |
| observability | `prometheus` | `tier=observability`, `role=metrics`, `app.kubernetes.io/part-of=ecoeco-backend` | kube-prometheus-stack (Prometheus/Alertmanager) | `k8s-monitoring`, `node-role.kubernetes.io/infrastructure=true:NoSchedule` |
| observability | `grafana` | `tier=observability`, `role=dashboards`, `app.kubernetes.io/part-of=ecoeco-backend` | Grafana (helm/grafana) | `k8s-monitoring`, `node-role.kubernetes.io/infrastructure=true:NoSchedule` |
| infrastructure | `platform-system` | `tier=infrastructure`, `app.kubernetes.io/part-of=ecoeco-platform` | External Secrets Operator 등 플랫폼 컨트롤러 | Control Plane (`k8s-master`), toleration `node-role.kubernetes.io/control-plane` |
| infrastructure | `data-system` | `tier=infrastructure`, `app.kubernetes.io/part-of=ecoeco-platform` | Postgres/Redis Operators (Helm) | Control Plane (`k8s-master`), toleration `node-role.kubernetes.io/control-plane` |
| infrastructure | `messaging-system` | `tier=infrastructure`, `app.kubernetes.io/part-of=ecoeco-platform` | RabbitMQ Operator/CRDs | Control Plane (`k8s-master`), toleration `node-role.kubernetes.io/control-plane` |


**점검 항목**:
- [ ] 모든 네임스페이스가 정의되어 있는가?
- [ ] `tier` / `role` 레이블이 올바른가?
  - `business-logic` + `role=api`: auth, my, scan, character, location, info, chat
  - `data`: postgres(`role=database`), redis(`role=cache`)
  - `integration`: rabbitmq(`role=messaging`)
  - `observability`: prometheus(`role=metrics`), grafana(`role=dashboards`)
  - `infrastructure`: platform-system, data-system, messaging-system
- [ ] `app.kubernetes.io/part-of: ecoeco-backend`(or `ecoeco-platform`) 레이블이 맞는가?

**점검 명령**:
```bash
kubectl get namespaces -l app.kubernetes.io/part-of=ecoeco-backend --show-labels
```

**예상 출력**:
```
auth        Active   tier=business-logic,role=api
my          Active   tier=business-logic,role=api
scan        Active   tier=business-logic,role=api
...
redis       Active   tier=data,role=cache
postgres    Active   tier=data,role=database
rabbitmq    Active   tier=integration,role=messaging
prometheus  Active   tier=observability,role=metrics
grafana     Active   tier=observability,role=dashboards
```

---

### 1.2 NetworkPolicy


**점검 항목**:
- [ ] `postgres-ingress-from-business-logic` 정책이 `tier=business-logic` 네임스페이스만 허용하는가?
- [ ] `redis-ingress-from-business-logic` 정책이 동일 조건을 만족하는가?
- [ ] `prometheus-scrape-all` 정책이 모든 네임스페이스에서 9090/8080 접근을 허용하는가?
- [ ] `grafana-allow-from-alb` 정책이 외부 트래픽을 허용하되 3000 포트만 열었는가?

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


**점검 항목**:
- [ ] 모든 도메인 네임스페이스를 대상으로 하는 ServiceMonitor가 있는가?
- [ ] `tier` 레이블이 올바른가?
- [ ] `relabelings`에 `namespace`, `domain`, `tier` 자동 추가 설정이 있는가?
- [ ] `namespaceSelector.matchNames`가 올바른 네임스페이스 목록을 포함하는가?

**점검 명령**:
```bash
kubectl get servicemonitors -n prometheus
kubectl describe servicemonitor api-services-all-domains -n prometheus
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

## ✅ Kustomize Overlays

### 2.1 네임스페이스 참조


**점검 항목**:
- [ ] 각 도메인의 `namespace` 필드가 도메인명과 일치하는가?
- [ ] `commonLabels.domain`이 올바른가?

**점검 명령**:
```bash
```

**예상 출력**:
```
...
```

---

### 2.2 데이터베이스/캐시 연결 문자열


**점검 항목**:
- [ ] `POSTGRES_HOST`가 올바른 네임스페이스를 참조하는가?
- [ ] `REDIS_HOST`가 올바른 네임스페이스를 참조하는가?
- [ ] `RABBITMQ_HOST`가 올바른 네임스페이스를 참조하는가? (chat 서비스)

**점검 명령**:
```bash
```

**예상 출력**:
```
POSTGRES_HOST: postgresql.postgres.svc.cluster.local  # ✅ "db" 아님!
REDIS_HOST: redis.redis.svc.cluster.local             # ✅ "db" 아님!
RABBITMQ_HOST: rabbitmq.rabbitmq.svc.cluster.local    # ✅ "db" 아님!
```

**❌ 잘못된 예**:
```
POSTGRES_HOST: postgresql.db.svc.cluster.local    # ❌ 잘못됨!
REDIS_HOST: redis.default.svc.cluster.local       # ❌ 잘못됨!
```

---

## ✅ ArgoCD ApplicationSet

### 3.1 ApplicationSet 설정


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

# template.metadata.labels
labels:
  tier: business-logic  # ✅ "api" 아님!

# template.spec.destination
namespace: '{{namespace}}'  # ✅ 동적 할당
```

---

### 3.2 Ingress 리소스 (추가)


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
argocd        argocd-ingress        ecoeco-main    21
grafana       grafana-ingress       ecoeco-main    30
prometheus    prometheus-ingress    ecoeco-main    40
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

## ✅ Ansible Playbooks

### 4.1 네임스페이스 변수


**점검 항목**:
- [ ] `postgres_namespace`가 `postgres`인가?
- [ ] `redis_namespace`가 `redis`인가?
- [ ] `rabbitmq_namespace`가 `rabbitmq`인가?
- [ ] `monitoring_namespace`가 `prometheus`인가?
- [ ] `grafana_namespace`가 `grafana`인가?
- [ ] `atlantis_namespace`가 `atlantis`인가? (정의되어 있는가?)

**점검 명령**:
```bash
```

**예상 출력**:
```yaml
postgres_namespace: "postgres"
redis_namespace: "redis"
rabbitmq_namespace: "rabbitmq"
monitoring_namespace: "prometheus"
grafana_namespace: "grafana"
atlantis_namespace: "atlantis"
```

---

### 4.2 네임스페이스 생성 Playbook


**점검 항목**:
- [ ] `workloads/namespaces/base/namespaces.yaml` 적용 태스크가 있는가?
- [ ] `domain-isolation.yaml` 복사 및 적용 태스크가 있는가?
- [ ] `servicemonitors-domain-ns.yaml` 복사 및 적용 태스크가 있는가?

**점검 명령**:
```bash
```

---

### 4.3 데이터베이스/캐시 Role


**점검 항목**:
- [ ] 각 Role에서 `{{ postgres_namespace }}`, `{{ redis_namespace }}`, `{{ rabbitmq_namespace }}` 변수를 올바르게 사용하는가?
- [ ] 네임스페이스 생성 태스크가 있는가?
- [ ] Secret 이름이 일관되게 사용되는가?
  - PostgreSQL: `postgresql-secret` (❌ `postgres-secret` 아님!)
  - RabbitMQ: `rabbitmq-default-user`

**점검 명령**:
```bash

# Secret 이름 확인
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
| AWS Credentials | `aws-credentials` | `workers`, `data`, `scan` | `scripts/create-aws-credentials-secret.sh` |

- [ ] PostgreSQL Secret이 `postgres` 네임스페이스에 `postgresql-secret` 이름으로 생성되는가?
- [ ] RabbitMQ Secret이 `rabbitmq` 네임스페이스에 생성되는가?
- [ ] AWS Credentials Secret이 필요한 네임스페이스에 모두 생성되었는가?
- [ ] Worker Deployments가 올바른 Secret 이름을 참조하는가?

**점검 명령**:
```bash
# Secret 존재 확인
kubectl get secrets -n postgres
kubectl get secrets -n rabbitmq
kubectl get secrets -n workers
kubectl get secrets -n atlantis

# PostgreSQL Secret 확인
kubectl get secret postgresql-secret -n postgres -o yaml

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


**점검 항목**:
- [ ] ~~`api` 네임스페이스 생성 태스크가 제거되었는가?~~ (✅ 제거됨)
- [ ] `workloads/ingress/apps/base/api-ingress.yaml` 적용 태스크가 있는가?
- [ ] `infrastructure-ingress.yaml` 적용 태스크가 있는가?
- [ ] ACM 인증서 ARN 치환이 올바르게 작동하는가?

**점검 명령**:
```bash
# api 네임스페이스 생성 태스크가 없어야 함
# ❌ 결과가 나오면 안됨!

# 도메인별 Ingress 적용 태스크 확인
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
echo "✅ Kustomize Overlays 점검"
echo "---"

for domain in auth my scan character location info chat; do
    echo -n "  $domain overlay... "
    
    # 네임스페이스 확인
    if [ "$NS" != "$domain" ]; then
        echo "❌ FAIL: namespace mismatch (expected: $domain, got: $NS)"
        ((ERRORS++))
    else
        echo "✅ OK"
    fi
    
    # 데이터베이스 연결 문자열 확인
        echo "  ❌ FAIL: deployment-patch.yaml에서 'db' 네임스페이스 발견 (postgres/redis/rabbitmq 중 하나여야 함)"
        ((ERRORS++))
    fi
done

# 2. ArgoCD ApplicationSet 점검
echo ""
echo "✅ ArgoCD ApplicationSet 점검"
echo "---"

echo -n "  tier 레이블... "
    echo "❌ FAIL: 'tier: api' 발견 (business-logic이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 3. Ansible 변수 점검
echo ""
echo "✅ Ansible 변수 점검"
echo "---"

if [ ! -f "$ANSIBLE_VARS" ]; then
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
if [ "$RABBITMQ_NS" != "rabbitmq" ]; then
    echo "❌ FAIL: expected 'rabbitmq', got '$RABBITMQ_NS'"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 4. NetworkPolicy 점검
echo ""
echo "✅ NetworkPolicy 점검"
echo "---"

echo -n "  data-ingress-from-api... "
    echo "❌ FAIL: 'tier: api' 발견 (business-logic이어야 함)"
    ((ERRORS++))
else
    echo "✅ OK"
fi

# 5. ServiceMonitor 점검
echo ""
echo "✅ ServiceMonitor 점검"
echo "---"

echo -n "  api-services-all-domains... "
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
| | | `REDIS_HOST` | `redis.redis.svc.cluster.local` (❌ `.db.` 아님!) |
| | | `RABBITMQ_HOST` | `rabbitmq.rabbitmq.svc.cluster.local` (❌ `.db.` 아님!) |
| | | `template.metadata.labels.tier` | `business-logic` (❌ `api` 아님!) |
| | | `template.spec.destination.namespace` | `'{{namespace}}'` (동적 할당) |
| | | `redis_namespace` | `redis` |
| | | `rabbitmq_namespace` | `rabbitmq` |
| | | `monitoring_namespace` | `prometheus` |
| | | API 노드 | auth, my, scan, character, location, info, chat (7개) |
| | | 제거된 노드 참조 | ❌ api_waste, api_userinfo, api_recycle_info, api_chat_llm |
| | `.github/workflows/infrastructure.yml` | Terraform Plan | PR 생성 시 자동 실행 |
| | | Terraform Validate | 템플릿 변수 검증 |

---

## ✅ CI/CD Pipelines

### 5.1 Terraform 템플릿 (Ansible Inventory)


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

# 변수 개수 확인
```

---

### 5.3 GitHub Actions Workflow


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


**점검 항목**:
- [ ] 모든 API 노드의 `domain` 변수가 올바른가?
- [ ] `[api_nodes]` 그룹에 7개 노드만 있는가?

**점검 명령**:
```bash
# Terraform 실행 후 생성된 Inventory 확인

# API 노드 개수 확인

# Domain 변수 확인
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
- 예: `refactor/namespace-cleanup`, `feat/namespace-standardization`

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
| v1.1.0 | 2025-11-13 | CI/CD Pipelines 점검 항목 추가 (Terraform 템플릿, GitHub Actions) |
| v1.0.0 | 2025-11-13 | 초기 버전 작성 (네임스페이스 일관성 점검 체크리스트) |


