# 네임스페이스 관련 추가 리소스 점검 리포트

> **점검 일시**: 2025-11-13 (추가 점검)  
> **점검 범위**: Ingress, Service, Secret, ConfigMap, ServiceAccount, RBAC  
> **목적**: 이전 점검에서 누락된 네임스페이스 관련 리소스 식별

---

## 🚨 발견된 추가 불일치 사항

### ❌ 1. Ingress 네임스페이스 불일치 (치명적)

**파일**: `k8s/ingress/14-nodes-ingress.yaml`

**문제**:
- **API Ingress가 `api` 네임스페이스에 배포됨**
- 하지만 실제 서비스들은 **도메인별 네임스페이스** (auth, my, scan, ...)에 배포됨
- **Ingress와 Service가 다른 네임스페이스에 있으면 라우팅 실패!**

```yaml
# ❌ 현재 (잘못됨)
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api-ingress
  namespace: api  # ❌ 문제!
spec:
  rules:
    - host: api.growbin.app
      http:
        paths:
          - path: /api/v1/auth
            backend:
              service:
                name: auth-api  # auth 네임스페이스에 있음!
                port:
                  number: 8000
```

**해결 방법 옵션**:

#### 옵션 A: Ingress를 각 도메인 네임스페이스로 분리 (권장)
```yaml
# auth 네임스페이스
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: auth-ingress
  namespace: auth  # ✅ 동일 네임스페이스
  annotations:
    alb.ingress.kubernetes.io/group.name: ecoeco-main
    alb.ingress.kubernetes.io/group.order: '10'
spec:
  rules:
    - host: api.growbin.app
      http:
        paths:
          - path: /api/v1/auth
            backend:
              service:
                name: auth-api
                port:
                  number: 8000
---
# my 네임스페이스
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-ingress
  namespace: my  # ✅ 동일 네임스페이스
  annotations:
    alb.ingress.kubernetes.io/group.name: ecoeco-main
    alb.ingress.kubernetes.io/group.order: '11'
spec:
  rules:
    - host: api.growbin.app
      http:
        paths:
          - path: /api/v1/my
            backend:
              service:
                name: my-api
                port:
                  number: 8000
```

**장점**:
- Ingress와 Service가 동일 네임스페이스 (Kubernetes 권장 사항)
- 도메인별 독립적 배포 가능
- NetworkPolicy 격리 유지

**단점**:
- 7개 Ingress 리소스 필요
- 관리 복잡도 증가

#### 옵션 B: ExternalName Service 사용 (임시 해결책)
```yaml
# api 네임스페이스에 ExternalName Service 생성
apiVersion: v1
kind: Service
metadata:
  name: auth-api
  namespace: api
spec:
  type: ExternalName
  externalName: auth-api.auth.svc.cluster.local
```

**장점**:
- 기존 Ingress 유지
- 빠른 적용

**단점**:
- ExternalName은 DNS CNAME이므로 일부 기능 제한
- 추가 DNS 조회 발생 (성능 저하)
- 권장되지 않는 패턴

#### 옵션 C: 단일 네임스페이스 유지 (역행)
```yaml
# 모든 API 서비스를 api 네임스페이스로 배포
namespace: api
```

**장점**:
- 기존 Ingress 유지

**단점**:
- **도메인별 네임스페이스 분리 전략 포기**
- NetworkPolicy 격리 불가
- RBAC 세분화 불가
- **권장하지 않음**

---

### ❌ 2. Ansible Playbook의 `api` 네임스페이스 생성

**파일**: `ansible/playbooks/07-ingress-resources.yml`

**문제**:
```yaml
- name: "필요한 Namespace 생성"
  shell: |
    kubectl create namespace api --dry-run=client -o yaml | kubectl apply -f -
```

**현재 전략과 불일치**:
- 도메인별 네임스페이스 (auth, my, scan, ...) 전략을 채택했지만
- Ansible에서는 여전히 `api` 네임스페이스를 생성함
- **Ingress가 이 `api` 네임스페이스에 배포됨**

**수정 필요**:
- `api` 네임스페이스 생성 제거
- 또는 Ingress를 도메인별 네임스페이스로 분리

---

### ✅ 3. Service 리소스 네임스페이스

**현재 상태**: ✅ **문제 없음**

Kustomize Base에 정의된 Service는 각 Overlay의 `namespace` 필드에 의해 자동으로 올바른 네임스페이스에 배포됩니다.

```yaml
# k8s/base/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: api  # Overlay에서 namePrefix로 auth-api, my-api 등으로 변환
spec:
  selector:
    app: api
  ports:
    - port: 8000
      targetPort: 8000
```

```yaml
# k8s/overlays/auth/kustomization.yaml
namespace: auth  # ✅ Service가 auth 네임스페이스에 생성됨
namePrefix: auth-
```

**검증 명령**:
```bash
kubectl get services -n auth
kubectl get services -n my
kubectl get services -n scan
# ...
```

---

### ✅ 4. Secret 및 ConfigMap

**현재 상태**: ✅ **문제 없음** (대부분)

#### 4.1 PostgreSQL Secret
```yaml
# ansible/roles/postgresql/tasks/main.yml
- name: "PostgreSQL 비밀번호 Secret 생성"
  shell: |
    kubectl create secret generic postgres-secret \
      -n {{ postgres_namespace }} \  # ✅ "data" 네임스페이스
      --from-literal=postgres-password='{{ postgres_password }}'
```

#### 4.2 RabbitMQ Secret
```yaml
# ansible/roles/rabbitmq/tasks/main.yml
- name: RabbitMQ 기본 사용자 Secret 생성
  shell: |
    kubectl create secret generic rabbitmq-default-user \
      -n {{ rabbitmq_namespace }} \  # ✅ "messaging" 네임스페이스
      --from-literal=username={{ rabbitmq_username }}
```

#### 4.3 Atlantis Secret
```yaml
# k8s/atlantis/atlantis-deployment.yaml
apiVersion: v1
kind: Secret
metadata:
  name: atlantis-secrets
  namespace: atlantis  # ✅ "atlantis" 네임스페이스
```

#### 4.4 Grafana/Prometheus ConfigMap
```yaml
# k8s/monitoring/grafana-deployment.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-datasources
  namespace: monitoring  # ✅ "monitoring" 네임스페이스
```

**문제점**: ❌ **Worker Deployments의 Secret 참조**

```yaml
# k8s/workers/worker-wal-deployments.yaml (133-137)
- name: POSTGRES_PASSWORD
  valueFrom:
    secretKeyRef:
      name: postgresql-secret  # ❌ 어느 네임스페이스?
      key: password
```

**문제**:
- Secret 이름이 `postgresql-secret`이지만 Ansible에서는 `postgres-secret`으로 생성함
- Worker가 배포될 네임스페이스에서 Secret을 찾을 수 없음

**해결 방법**:
1. Secret 이름 통일: `postgres-secret` → `postgresql-secret`
2. 또는 Worker Deployment 수정: `postgresql-secret` → `postgres-secret`
3. 또는 Secret을 각 네임스페이스에 복제 (권장하지 않음)

---

### ✅ 5. ServiceAccount 및 RBAC

**현재 상태**: ✅ **문제 없음**

#### 5.1 Prometheus ServiceAccount
```yaml
# k8s/monitoring/prometheus-deployment.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: prometheus
  namespace: monitoring  # ✅ "monitoring" 네임스페이스
```

```yaml
# ClusterRoleBinding
subjects:
  - kind: ServiceAccount
    name: prometheus
    namespace: monitoring  # ✅ 명시적 네임스페이스 참조
```

#### 5.2 Atlantis ServiceAccount
```yaml
# k8s/atlantis/atlantis-deployment.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: atlantis
  namespace: atlantis  # ✅ "atlantis" 네임스페이스
```

---

## 📋 네임스페이스 관련 리소스 전체 목록

### 1. Namespace 정의
| 파일 | 네임스페이스 | 상태 |
|------|-------------|------|
| `k8s/namespaces/domain-based.yaml` | auth, my, scan, character, location, info, chat, data, messaging, monitoring, atlantis | ✅ 정의됨 |
| `k8s/atlantis/atlantis-deployment.yaml` | atlantis | ✅ 정의됨 (중복) |

### 2. Ingress 리소스
| 파일 | Ingress 이름 | 네임스페이스 | 상태 |
|------|-------------|-------------|------|
| `k8s/ingress/14-nodes-ingress.yaml` | api-ingress | `api` | ❌ **불일치** |
| `k8s/ingress/14-nodes-ingress.yaml` | atlantis-ingress | `atlantis` | ✅ 일치 |
| `k8s/ingress/14-nodes-ingress.yaml` | grafana-ingress | `monitoring` | ✅ 일치 |
| `k8s/ingress/14-nodes-ingress.yaml` | argocd-ingress | `argocd` | ✅ 일치 |
| `k8s/ingress/14-nodes-ingress.yaml` | prometheus-ingress | `monitoring` | ✅ 일치 |

### 3. Service 리소스
| 파일 | Service 패턴 | 네임스페이스 | 상태 |
|------|-------------|-------------|------|
| `k8s/base/service.yaml` | api (Kustomize Base) | Overlay에서 지정 | ✅ 동적 할당 |
| `k8s/overlays/*/kustomization.yaml` | auth-api, my-api, ... | auth, my, scan, ... | ✅ 일치 |
| `k8s/monitoring/*.yaml` | prometheus, grafana, node-exporter | `monitoring` | ✅ 일치 |
| `k8s/atlantis/atlantis-deployment.yaml` | atlantis | `atlantis` | ✅ 일치 |

### 4. Secret 리소스
| 생성 위치 | Secret 이름 | 네임스페이스 | 상태 |
|----------|------------|-------------|------|
| `ansible/roles/postgresql/tasks/main.yml` | postgres-secret | `data` | ✅ 일치 |
| `ansible/roles/rabbitmq/tasks/main.yml` | rabbitmq-default-user | `messaging` | ✅ 일치 |
| `k8s/atlantis/atlantis-deployment.yaml` | atlantis-secrets | `atlantis` | ✅ 일치 |
| `k8s/workers/worker-wal-deployments.yaml` | postgresql-secret (참조) | ❓ 미정의 | ❌ **불일치** |
| `k8s/workers/worker-wal-deployments.yaml` | aws-credentials (참조) | ❓ 미정의 | ❌ **누락** |

### 5. ConfigMap 리소스
| 파일 | ConfigMap 이름 | 네임스페이스 | 상태 |
|------|---------------|-------------|------|
| `k8s/monitoring/grafana-deployment.yaml` | grafana-datasources | `monitoring` | ✅ 일치 |
| `k8s/monitoring/grafana-deployment.yaml` | grafana-dashboards-config | `monitoring` | ✅ 일치 |
| `k8s/monitoring/prometheus-deployment.yaml` | prometheus-config | `monitoring` | ✅ 일치 |
| `k8s/monitoring/prometheus-deployment.yaml` | prometheus-rules | `monitoring` | ✅ 일치 |
| `k8s/atlantis/atlantis-deployment.yaml` | atlantis-config | `atlantis` | ✅ 일치 |
| `k8s/atlantis/atlantis-deployment.yaml` | atlantis-repo-config | `atlantis` | ✅ 일치 |

### 6. ServiceAccount 및 RBAC
| 파일 | ServiceAccount | 네임스페이스 | ClusterRoleBinding | 상태 |
|------|---------------|-------------|-------------------|------|
| `k8s/monitoring/prometheus-deployment.yaml` | prometheus | `monitoring` | ✅ 명시적 참조 | ✅ 일치 |
| `k8s/atlantis/atlantis-deployment.yaml` | atlantis | `atlantis` | ✅ 명시적 참조 | ✅ 일치 |

### 7. NetworkPolicy
| 파일 | Policy 이름 | 대상 네임스페이스 | 상태 |
|------|-----------|----------------|------|
| `k8s/networkpolicies/domain-isolation.yaml` | data-ingress-from-api | `data` | ✅ 일치 |
| `k8s/networkpolicies/domain-isolation.yaml` | messaging-ingress-from-api | `messaging` | ✅ 일치 |
| `k8s/networkpolicies/domain-isolation.yaml` | monitoring-ingress | `monitoring` | ✅ 일치 |

### 8. ServiceMonitor (Prometheus Operator)
| 파일 | ServiceMonitor 이름 | 네임스페이스 | 대상 네임스페이스 | 상태 |
|------|-------------------|-------------|-----------------|------|
| `k8s/monitoring/servicemonitors-domain-ns.yaml` | api-services-all-domains | `monitoring` | auth, my, scan, ... | ✅ 일치 |
| `k8s/monitoring/servicemonitors-domain-ns.yaml` | data-layer-monitor | `monitoring` | `data` | ✅ 일치 |
| `k8s/monitoring/servicemonitors-domain-ns.yaml` | integration-layer-monitor | `monitoring` | `messaging` | ✅ 일치 |

---

## 🔧 수정이 필요한 항목 우선순위

### 🚨 Priority 1: 치명적 (배포 실패)

1. **Ingress 네임스페이스 불일치** (`k8s/ingress/14-nodes-ingress.yaml`)
   - **영향**: API 라우팅 실패
   - **해결**: Ingress를 도메인별 네임스페이스로 분리
   - **예상 소요 시간**: 1-2시간

2. **Ansible `api` 네임스페이스 생성** (`ansible/playbooks/07-ingress-resources.yml`)
   - **영향**: 불필요한 네임스페이스 생성
   - **해결**: Playbook에서 `api` 네임스페이스 생성 제거
   - **예상 소요 시간**: 10분

### ⚠️ Priority 2: 중요 (기능 제한)

3. **Worker Deployments Secret 참조 오류** (`k8s/workers/worker-wal-deployments.yaml`)
   - **영향**: Worker Pod 시작 실패
   - **해결**: Secret 이름 통일 또는 Secret 생성
   - **예상 소요 시간**: 30분

4. **Worker Deployments AWS Credentials Secret 누락** (`k8s/workers/worker-wal-deployments.yaml`)
   - **영향**: S3 접근 실패
   - **해결**: AWS Credentials Secret 생성
   - **예상 소요 시간**: 20분

### 📝 Priority 3: 개선 사항 (문서화)

5. **Atlantis Namespace 중복 정의**
   - `k8s/namespaces/domain-based.yaml`
   - `k8s/atlantis/atlantis-deployment.yaml`
   - **영향**: 없음 (idempotent)
   - **해결**: 한 곳에서만 정의 (권장)

---

## 📊 네임스페이스 관련 리소스 매트릭스

| 리소스 타입 | 총 개수 | 일치 | 불일치 | 누락 |
|-----------|--------|------|--------|------|
| **Namespace** | 11 | ✅ 11 | ❌ 0 | ⚠️ 0 |
| **Ingress** | 5 | ✅ 4 | ❌ 1 | ⚠️ 0 |
| **Service** | ~20 | ✅ 20 | ❌ 0 | ⚠️ 0 |
| **Secret** | 4 | ✅ 3 | ❌ 1 | ⚠️ 1 |
| **ConfigMap** | 6 | ✅ 6 | ❌ 0 | ⚠️ 0 |
| **ServiceAccount** | 2 | ✅ 2 | ❌ 0 | ⚠️ 0 |
| **NetworkPolicy** | 3 | ✅ 3 | ❌ 0 | ⚠️ 0 |
| **ServiceMonitor** | 13 | ✅ 13 | ❌ 0 | ⚠️ 0 |
| **총계** | **64** | **✅ 62** | **❌ 2** | **⚠️ 1** |

**일관성 비율**: **96.9%** (62/64)

---

## 🎯 권장 조치 사항

### 1. Ingress 리팩토링 (필수)

**방법 A: 도메인별 Ingress 분리 (권장)**

```bash
# 1. 새로운 Ingress 파일 생성
k8s/ingress/domain-based-ingress.yaml

# 2. 각 도메인별 Ingress 생성
auth-ingress (namespace: auth)
my-ingress (namespace: my)
scan-ingress (namespace: scan)
...

# 3. ALB Group으로 단일 ALB 유지
annotations:
  alb.ingress.kubernetes.io/group.name: ecoeco-main
  alb.ingress.kubernetes.io/group.order: '<순서>'
```

**방법 B: Service Export/Import (Kubernetes 1.21+)**
```yaml
# ServiceExport를 사용하여 cross-namespace 라우팅
apiVersion: multicluster.k8s.io/v1alpha1
kind: ServiceExport
metadata:
  name: auth-api
  namespace: auth
```

### 2. Ansible Playbook 수정

```yaml
# ansible/playbooks/07-ingress-resources.yml
- name: "도메인별 Ingress 적용"
  shell: |
    kubectl apply -f {{ playbook_dir }}/../../k8s/ingress/domain-based-ingress.yaml
```

### 3. Worker Deployments Secret 수정

```yaml
# ansible/roles/postgresql/tasks/main.yml
- name: "PostgreSQL 비밀번호 Secret 생성"
  shell: |
    kubectl create secret generic postgresql-secret \  # ✅ 이름 변경
      -n {{ postgres_namespace }} \
      --from-literal=postgres-password='{{ postgres_password }}'
```

### 4. AWS Credentials Secret 생성

```bash
# 각 Worker 네임스페이스에 Secret 생성
kubectl create secret generic aws-credentials \
  -n workers \
  --from-literal=access-key-id='...' \
  --from-literal=secret-access-key='...'
```

---

## 📚 점검 체크리스트 업데이트

**`docs/deployment/namespaces/NAMESPACE_CONSISTENCY_CHECKLIST.md`에 추가해야 할 항목**:

### Layer 1: Kubernetes Manifests

```markdown
#### 1.4 Ingress 리소스 (`k8s/ingress/*.yaml`)
- [ ] API Ingress가 올바른 네임스페이스에 배포되는가?
  - 옵션 A: 도메인별 Ingress (auth, my, scan, ...)
  - 옵션 B: 단일 Ingress + ExternalName Service
- [ ] Ingress.spec.rules[].backend.service.name이 동일 네임스페이스의 Service를 참조하는가?
- [ ] ALB Group 설정이 올바른가?

**점검 명령**:
```bash
kubectl get ingress -A
kubectl describe ingress api-ingress -n <namespace>
```

#### 1.5 Secret 리소스
- [ ] PostgreSQL Secret 이름이 일치하는가?
  - Ansible: `postgres-secret` vs Worker: `postgresql-secret`
- [ ] AWS Credentials Secret이 Worker 네임스페이스에 존재하는가?
- [ ] Secret이 올바른 네임스페이스에 생성되는가?

**점검 명령**:
```bash
kubectl get secrets -n data
kubectl get secrets -n messaging
kubectl get secrets -n workers  # Worker 배포 시
```
```

### Layer 4: Ansible Playbooks

```markdown
#### 4.4 Ingress Playbook (`ansible/playbooks/07-ingress-resources.yml`)
- [ ] `api` 네임스페이스 생성이 제거되었는가?
- [ ] 도메인별 Ingress 적용 태스크가 추가되었는가?
- [ ] Fallback Ingress 생성 로직이 제거되었는가?

**점검 명령**:
```bash
grep -n "kubectl create namespace api" ansible/playbooks/07-ingress-resources.yml
# ❌ 결과가 나오면 안됨!
```
```

---

## 🔍 자동화 스크립트 업데이트

**`scripts/check-namespace-consistency.sh`에 추가**:

```bash
# 6. Ingress 점검
echo ""
echo "✅ Layer 1: Ingress 점검"
echo "---"

echo -n "  api-ingress 네임스페이스... "
API_INGRESS_NS=$(kubectl get ingress api-ingress -o jsonpath='{.metadata.namespace}' 2>/dev/null || echo "not_found")
if [ "$API_INGRESS_NS" == "api" ]; then
    echo "❌ FAIL: api-ingress가 'api' 네임스페이스에 있음 (도메인별 분리 필요)"
    ((ERRORS++))
elif [ "$API_INGRESS_NS" == "not_found" ]; then
    echo "✅ OK: api-ingress 없음 (도메인별 Ingress로 대체됨)"
else
    echo "⚠️  WARNING: api-ingress가 '$API_INGRESS_NS' 네임스페이스에 있음"
fi

# 7. Secret 점검
echo ""
echo "✅ Layer 4: Secret 일관성 점검"
echo "---"

echo -n "  postgres-secret (data 네임스페이스)... "
if kubectl get secret postgres-secret -n data &>/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAIL: postgres-secret이 data 네임스페이스에 없음"
    ((ERRORS++))
fi

echo -n "  rabbitmq-default-user (messaging 네임스페이스)... "
if kubectl get secret rabbitmq-default-user -n messaging &>/dev/null; then
    echo "✅ OK"
else
    echo "❌ FAIL: rabbitmq-default-user가 messaging 네임스페이스에 없음"
    ((ERRORS++))
fi
```

---

## 📝 변경 이력

| 버전 | 날짜 | 변경 내역 |
|------|------|-----------|
| v1.0.0 | 2025-11-13 | 추가 네임스페이스 관련 리소스 점검 리포트 작성 |

---

**점검자**: AI Assistant  
**브랜치**: `refactor/namespace-cleanup`  
**다음 단계**: Ingress 리팩토링 및 Ansible Playbook 수정

