# ArgoCD 동기화 - kubectl만 사용 (로그인 불필요)

## ✅ kubectl만으로 ArgoCD 조작

ArgoCD CLI 로그인 없이 kubectl로 직접 Application을 조작할 수 있습니다.

---

## 🚀 즉시 사용 가능한 명령어

### **방법 1: 전체 Applications 한번에 Refresh + Sync**

```bash
# 간단 버전 (가장 빠름)
./scripts/sync-argocd-refresh-all.sh dev
```

이 스크립트는:
1. 모든 dev Applications에 Hard Refresh 적용
2. 모든 Applications에 Sync 트리거
3. 실시간 상태 모니터링

---

### **방법 2: 수동으로 하나씩**

#### 단일 Application 동기화
```bash
APP_NAME="dev-postgresql"

# 1. Hard Refresh (변경사항 강제 감지)
kubectl -n argocd annotate application $APP_NAME \
    argocd.argoproj.io/refresh=hard --overwrite

# 2. Sync 트리거
kubectl -n argocd patch application $APP_NAME \
    --type merge \
    -p '{"operation":{"initiatedBy":{"username":"kubectl"},"sync":{"prune":true}}}'

# 3. 상태 확인
kubectl -n argocd get application $APP_NAME
```

#### 전체 Applications 한번에
```bash
# 모든 dev Applications Refresh
kubectl -n argocd get applications -l env=dev -o name | \
    xargs -I {} kubectl -n argocd annotate {} \
    argocd.argoproj.io/refresh=hard --overwrite

# 모든 dev Applications Sync
kubectl -n argocd get applications -l env=dev -o name | \
    xargs -I {} kubectl -n argocd patch {} \
    --type merge \
    -p '{"operation":{"initiatedBy":{"username":"kubectl"},"sync":{"prune":true}}}'
```

---

### **방법 3: sync-wave 순서대로 (스크립트)**

```bash
# 0번부터 순차적으로 (업데이트된 버전)
./scripts/sync-argocd-all.sh dev
```

---

## 📊 상태 확인

### 전체 Applications 상태
```bash
kubectl -n argocd get applications -l env=dev
```

### 실시간 모니터링
```bash
watch -n 3 "kubectl -n argocd get applications -l env=dev -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'"
```

### 특정 Application 상세 정보
```bash
kubectl -n argocd get application dev-postgresql -o yaml
```

### Sync 상태만 확인
```bash
kubectl -n argocd get applications -l env=dev \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.sync.status}{"\t"}{.status.health.status}{"\n"}{end}'
```

---

## 🔧 유용한 kubectl 명령어

### Application 삭제 (재생성)
```bash
kubectl -n argocd delete application dev-postgresql
kubectl apply -f clusters/dev/apps/27-postgresql.yaml
```

### 모든 dev Applications 삭제
```bash
kubectl -n argocd delete applications -l env=dev
```

### Sync 작업 취소
```bash
kubectl -n argocd patch application dev-postgresql \
    --type merge \
    -p '{"operation":null}'
```

### 자동 동기화 활성화/비활성화
```bash
# 비활성화
kubectl -n argocd patch application dev-postgresql \
    --type merge \
    -p '{"spec":{"syncPolicy":{"automated":null}}}'

# 활성화
kubectl -n argocd patch application dev-postgresql \
    --type merge \
    -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
```

---

## 🎯 PostgreSQL 배포 완전 가이드

### 1. 기존 리소스 삭제
```bash
kubectl -n postgres delete postgresql postgres-cluster --ignore-not-found=true --wait=false
kubectl -n postgres delete statefulset postgres-cluster --ignore-not-found=true
kubectl -n postgres delete pod -l cluster-name=postgres-cluster --grace-period=0 --force
kubectl -n postgres delete pvc pgdata-postgres-cluster-0
```

### 2. 코드 푸시
```bash
git push origin develop
```

### 3. 즉시 동기화 (3가지 방법 중 선택)

#### A. PostgreSQL만
```bash
kubectl -n argocd annotate application dev-postgresql \
    argocd.argoproj.io/refresh=hard --overwrite

kubectl -n argocd patch application dev-postgresql \
    --type merge \
    -p '{"operation":{"initiatedBy":{"username":"kubectl"},"sync":{"prune":true}}}'
```

#### B. 전체 한번에
```bash
./scripts/sync-argocd-refresh-all.sh dev
```

#### C. 자동 대기 (3분)
```bash
# 아무것도 안 해도 됨
```

### 4. 배포 확인
```bash
kubectl -n postgres get pods -w
```

---

## 💡 왜 kubectl이 작동하는가?

ArgoCD Application은 Kubernetes Custom Resource입니다:
- `kubectl`로 직접 조작 가능
- ArgoCD 서버 로그인 불필요
- 클러스터 접근 권한만 있으면 됨

```yaml
# Application은 그냥 Kubernetes 리소스
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  annotations:
    argocd.argoproj.io/refresh: hard  # ← annotation으로 제어
  ...
```

---

## ✅ 권장 방법

**가장 간단하고 빠른 방법:**

```bash
# 전체 동기화
./scripts/sync-argocd-refresh-all.sh dev

# 또는 PostgreSQL만
kubectl -n argocd annotate application dev-postgresql argocd.argoproj.io/refresh=hard --overwrite
```

**ArgoCD CLI 로그인 필요 없음!** 🎉

