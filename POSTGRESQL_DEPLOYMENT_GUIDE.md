# ✅ PostgreSQL Helm 전환 완료 - 실행 가이드

## 🎯 준비 완료!

### ✅ 로컬 작업 완료
- sync-wave: 27 추가
- ArgoCD 동기화 스크립트 추가
- 기존 PostgreSQL 정리 스크립트 추가
- 커밋 완료 (d4a4307)

---

## 🚀 클러스터에서 실행할 명령어

### **1단계: 기존 PostgreSQL 완전 삭제**

```bash
# 간단 버전 (추천)
kubectl -n postgres delete postgresql postgres-cluster --ignore-not-found=true --wait=false
kubectl -n postgres delete statefulset postgres-cluster --ignore-not-found=true
kubectl -n postgres delete pod -l cluster-name=postgres-cluster --grace-period=0 --force
kubectl -n postgres delete service postgres-cluster postgres-cluster-repl --ignore-not-found=true
kubectl -n postgres delete pvc pgdata-postgres-cluster-0
kubectl -n data-system delete deployment postgres-operator --ignore-not-found=true

# 또는 스크립트 사용 (저장소 clone 필요)
# ./scripts/cleanup-old-postgres.sh
```

### **2단계: 코드 푸시**

```bash
cd /Users/mango/workspace/SeSACTHON/backend
git push origin develop
```

### **3단계: ArgoCD 즉시 동기화 (선택)**

#### 방법 A: PostgreSQL만 빠르게 동기화
```bash
# kubectl로 직접 트리거
kubectl -n argocd annotate application dev-postgresql \
    argocd.argoproj.io/refresh=hard --overwrite

# Pod 생성 확인
kubectl -n postgres get pods -w
```

#### 방법 B: 전체 Applications sync-wave 순서대로
```bash
# 0번부터 순차 동기화 (저장소에서 실행)
./scripts/sync-argocd-all.sh dev
```

#### 방법 C: 자동 동기화 대기
```bash
# 3분 이내 ArgoCD가 자동으로 감지하고 동기화
# 아무것도 안 해도 됨!
```

---

## 📊 예상 타임라인

```
T+0분:   git push origin develop
         └─ GitHub에 변경사항 반영

T+0-3분: ArgoCD 변경 감지 (automated: true)
         └─ 또는 수동 트리거 (즉시)

T+3-5분: PostgreSQL 배포 시작
         ├─ StatefulSet 생성
         ├─ dev-postgresql-0 Pod 생성
         └─ initdb 스크립트 실행 (auth 스키마)

T+5-8분: ✅ 배포 완료
         └─ dev-postgresql-0 Running
```

---

## 🔍 배포 확인

### Pod 상태
```bash
kubectl -n postgres get pods
# 예상: dev-postgresql-0   1/1   Running
```

### Service 확인
```bash
kubectl -n postgres get svc
# 예상: dev-postgresql   ClusterIP   ...   5432/TCP
```

### 데이터베이스 접속
```bash
kubectl -n postgres exec -it dev-postgresql-0 -- psql -U sesacthon -d ecoeco

# 스키마 확인
ecoeco=> \dn
         List of schemas
  Name  |    Owner
--------+-------------
 auth   | sesacthon      ← 자동 생성됨!
 public | pg_database_owner
```

### auth-api 재시작
```bash
kubectl -n auth rollout restart deployment auth-api

# 로그 확인
kubectl -n auth logs -f deployment/auth-api | grep -i database
```

---

## 🛠️ 트러블슈팅

### ArgoCD Application이 안 보임
```bash
# Application 확인
kubectl -n argocd get application dev-postgresql

# 없으면 수동 생성
kubectl apply -f clusters/dev/apps/27-postgresql.yaml
```

### Pod이 Pending
```bash
# Events 확인
kubectl -n postgres describe pod dev-postgresql-0

# PVC 상태 확인
kubectl -n postgres get pvc
```

### auth-api 연결 실패
```bash
# DATABASE_URL 확인
kubectl -n auth get secret auth-secret -o jsonpath='{.data.AUTH_DATABASE_URL}' | base64 -d

# 정상: postgresql+asyncpg://sesacthon:***@dev-postgresql.postgres.svc.cluster.local:5432/ecoeco
```

---

## 📋 체크리스트

- [ ] 1. 기존 PostgreSQL 리소스 삭제
- [ ] 2. git push origin develop
- [ ] 3. ArgoCD 동기화 (자동 또는 수동)
- [ ] 4. dev-postgresql-0 Running 확인
- [ ] 5. 데이터베이스 접속 테스트
- [ ] 6. auth 스키마 존재 확인
- [ ] 7. auth-api 재시작
- [ ] 8. API 동작 확인

---

## 🎉 완료!

**지금 푸시하면 자동으로 배포됩니다!** 🚀

```bash
git push origin develop
```

또는 즉시 동기화:
```bash
kubectl -n argocd annotate application dev-postgresql argocd.argoproj.io/refresh=hard --overwrite
```

