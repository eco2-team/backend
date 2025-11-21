# PostgreSQL Helm 충돌 가능성 점검

## ✅ Ingress 분석 결과

### 기존 Ingress 확인
```yaml
# workloads/ingress/base/api-ingress.yaml
spec:
  rules:
    - host: api.dev.growbin.app
      paths:
        - /api/v1/auth → auth-api:8000
        - /api/v1/my → my-api:8000
        - /api/v1/scan → scan-api:8000
        - /api/v1/character → character-api:8000
        - /api/v1/location → location-api:8000
        - /api/v1/info → info-api:8000
        - /api/v1/chat → chat-api:8000
        - /health → health:8000
```

**결론:** ✅ **PostgreSQL은 Ingress에 노출되지 않음**
- Ingress는 API 서비스만 노출
- PostgreSQL은 내부 ClusterIP Service만 사용
- **충돌 없음!**

---

## 🔍 예상 충돌 시나리오 및 해결

### 1. **Service 이름 충돌** ⚠️

#### 문제
```yaml
# 기존 (Zalando Operator)
Service: postgres-cluster.postgres.svc.cluster.local

# 새로운 (Bitnami Helm)
Service: dev-postgresql.postgres.svc.cluster.local
```

#### 해결책
✅ **이름이 다르므로 충돌 없음!**
- 하지만 기존 `postgres-cluster` Service는 삭제 필요
- 애플리케이션의 DATABASE_URL은 이미 `dev-postgresql`로 변경됨

#### 확인 방법
```bash
# postgres namespace의 모든 Service 확인
kubectl -n postgres get svc

# 예상 결과:
# NAME               TYPE        CLUSTER-IP       PORT(S)
# postgres-cluster   ClusterIP   (기존 - 삭제 필요)
# dev-postgresql     ClusterIP   (새로 생성됨)
```

---

### 2. **PVC 충돌** ⚠️

#### 문제
```yaml
# 기존
PVC: pgdata-postgres-cluster-0

# 새로운
PVC: data-dev-postgresql-0
```

#### 해결책
✅ **이름이 다르므로 충돌 없음!**
- 기존 PVC는 수동으로 삭제하거나 보관 가능

#### 확인 방법
```bash
kubectl -n postgres get pvc

# 예상 결과:
# NAME                        STATUS   VOLUME      CAPACITY
# pgdata-postgres-cluster-0   Bound    pvc-xxx     20Gi  (기존)
# data-dev-postgresql-0       Bound    pvc-yyy     20Gi  (새로)
```

---

### 3. **StatefulSet 충돌** ⚠️

#### 문제
```yaml
# 기존
StatefulSet: postgres-cluster

# 새로운
StatefulSet: dev-postgresql
```

#### 해결책
✅ **이름이 다르므로 충돌 없음!**

---

### 4. **포트 충돌** ❌

#### 문제
둘 다 5432 포트 사용

#### 해결책
✅ **ClusterIP Service이므로 충돌 없음!**
- 각 Service가 독립적인 Cluster IP 할당
- 내부 DNS로 구분됨

---

### 5. **ConfigMap/Secret 충돌** ⚠️

#### 문제
```yaml
# 기존
Secret: postgresql-secret (External Secrets가 생성)

# 새로운
Secret: postgresql-secret (동일!)  ← 같은 Secret 재사용 ✅
```

#### 해결책
✅ **동일한 Secret을 재사용하므로 문제없음!**
- External Secrets Operator가 관리
- 양쪽 모두 같은 비밀번호 사용

---

### 6. **Operator CRD 충돌** ❌

#### 문제
Zalando Postgres Operator CRD가 남아있을 수 있음

#### 해결책
```bash
# CRD 확인
kubectl get crd | grep postgres

# Zalando Operator CRD가 있다면:
kubectl get crd postgresqls.acid.zalan.do

# 필요시 삭제 (주의!)
kubectl delete crd postgresqls.acid.zalan.do
```

---

## 🚨 실제 충돌 가능성: **거의 없음!**

### ✅ 충돌하지 않는 이유

| 리소스 | 기존 이름 | 새 이름 | 충돌 |
|--------|----------|---------|------|
| StatefulSet | postgres-cluster | dev-postgresql | ❌ |
| Service | postgres-cluster | dev-postgresql | ❌ |
| PVC | pgdata-postgres-cluster-0 | data-dev-postgresql-0 | ❌ |
| Secret | postgresql-secret | postgresql-secret | ✅ 재사용 |
| Pod | postgres-cluster-0 | dev-postgresql-0 | ❌ |
| Port | 5432 | 5432 | ❌ (ClusterIP) |

---

## ⚠️ 주의해야 할 점

### 1. 동시에 두 PostgreSQL이 실행되면
```
기존: postgres-cluster-0 (Running)
새로: dev-postgresql-0 (Running)

문제:
- 리소스 중복 사용 (CPU, Memory, Storage)
- 혼란 가능
```

**해결:**
```bash
# 기존 PostgreSQL 완전 삭제 후 새로 배포
kubectl -n postgres delete postgresql postgres-cluster
kubectl -n postgres delete statefulset postgres-cluster
kubectl -n postgres delete pod postgres-cluster-0 --force
```

### 2. 애플리케이션의 DATABASE_URL

**이미 변경 완료:** ✅
```yaml
# workloads/secrets/external-secrets/dev/api-secrets.yaml
AUTH_DATABASE_URL: "postgresql+asyncpg://sesacthon:***@dev-postgresql.postgres.svc.cluster.local:5432/ecoeco"
```

---

## 🎯 안전한 마이그레이션 순서

```bash
# 1. 기존 PostgreSQL 완전 삭제
kubectl -n postgres delete postgresql postgres-cluster --wait=false
kubectl -n postgres delete statefulset postgres-cluster
kubectl -n postgres delete pod postgres-cluster-0 --force --grace-period=0
kubectl -n postgres delete service postgres-cluster postgres-cluster-repl

# 2. 잠시 대기 (완전 종료 확인)
kubectl -n postgres get all

# 3. ArgoCD Sync (새 PostgreSQL 배포)
kubectl -n argocd annotate application dev-postgresql \
    argocd.argoproj.io/refresh=hard --overwrite

# 4. 새 Pod 생성 확인
kubectl -n postgres get pods -w
```

---

## ✅ 결론

**PostgreSQL Helm Chart는 기존 Ingress와 충돌하지 않습니다!**

- ✅ Ingress는 API만 노출
- ✅ PostgreSQL은 내부 ClusterIP만 사용
- ✅ 리소스 이름이 모두 다름
- ✅ Secret만 재사용 (의도된 동작)

**충돌 걱정 없이 배포하세요!** 🚀

단, **기존 PostgreSQL을 먼저 삭제**하는 것이 깔끔합니다.


