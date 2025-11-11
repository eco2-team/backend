# ArgoCD 접속 정보

## 📋 접속 정보

### Web UI

```
URL:      https://argocd.growbin.app
Username: admin
Password: TLybIfgEpRr7rC8G
```

### CLI 로그인

```bash
# ArgoCD CLI 로그인
argocd login argocd.growbin.app \
  --username admin \
  --password TLybIfgEpRr7rC8G \
  --insecure

# 또는 환경변수 사용
export ARGOCD_SERVER=argocd.growbin.app
export ARGOCD_AUTH_TOKEN=$(argocd account generate-token --account admin)
```

---

## 🔐 비밀번호 변경

### 방법 1: Web UI에서 변경

1. https://argocd.growbin.app 로그인
2. User Info → Update Password

### 방법 2: CLI로 변경

```bash
# 현재 비밀번호로 로그인 후
argocd account update-password \
  --current-password TLybIfgEpRr7rC8G \
  --new-password YOUR_NEW_PASSWORD
```

### 방법 3: kubectl로 비밀번호 리셋

```bash
# Master 노드에서 실행
kubectl patch secret argocd-secret -n argocd -p '{
  "stringData": {
    "admin.password": "'$(htpasswd -bnBC 10 "" newpassword | tr -d ":\n")'"
  }
}'

# ArgoCD Server Pod 재시작
kubectl rollout restart deployment argocd-server -n argocd
```

---

## 📊 현재 등록된 Application

### Infrastructure Application

```bash
# Application 목록
kubectl get applications -n argocd

# Application 상세 정보
kubectl describe application infrastructure -n argocd

# Application Sync 상태
argocd app get infrastructure
```

---

## 🪝 Hooks 확인

### PreSync Hook (Ansible)

```bash
# Job 상태
kubectl get job presync-ansible -n argocd

# 로그 확인
kubectl logs -n argocd -l job-name=presync-ansible
```

### PostSync Hook (Health Check)

```bash
# Job 상태
kubectl get job postsync-healthcheck -n argocd

# 로그 확인
kubectl logs -n argocd -l job-name=postsync-healthcheck
```

---

## 🔧 유용한 명령어

### Application 관리

```bash
# Application Sync
argocd app sync infrastructure

# Application 삭제
argocd app delete infrastructure

# Application 생성
argocd app create infrastructure \
  --repo https://github.com/SeSACTHON/backend.git \
  --path k8s/ \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace default
```

### Repository 관리

```bash
# Repository 추가
argocd repo add https://github.com/SeSACTHON/backend.git \
  --type git \
  --name backend

# Repository 목록
argocd repo list
```

### Project 관리

```bash
# Project 목록
argocd proj list

# Project 생성
argocd proj create myproject
```

---

## 📝 참고사항

- **초기 비밀번호**: `argocd-initial-admin-secret` Secret에서 자동 생성
- **비밀번호 변경 권장**: 초기 비밀번호는 보안을 위해 변경하는 것을 권장
- **Secret 삭제 금지**: `argocd-initial-admin-secret`을 삭제하면 비밀번호 복구 불가

---

**최종 업데이트**: 2025-11-11  
**버전**: v1.0.0

