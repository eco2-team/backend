# ArgoCD 모니터링 가이드

## 📊 ArgoCD로 클러스터 배포 상태 모니터링하기

ArgoCD는 GitOps 배포의 **실시간 모니터링 대시보드**를 제공합니다.

---

## 🎯 1. ArgoCD 접속 방법

### 방법 1: Port Forward (로컬 개발)

```bash
# Master 노드에서
kubectl port-forward svc/argocd-server -n argocd 8080:443

# 로컬에서 접속
https://localhost:8080
```

### 방법 2: Ingress (프로덕션)

```bash
# Ingress를 통한 접속 (DNS 설정 후)
https://argocd.growbin.site
```

### 로그인 정보

```bash
# Username
admin

# Password 조회
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

---

## 🔍 2. 모니터링 가능한 항목들

### ✅ Applications 탭에서 확인

| 항목 | 설명 |
|------|------|
| **Sync Status** | Git 저장소와 클러스터 상태 동기화 여부 |
| **Health Status** | 배포된 리소스의 건강 상태 (Healthy/Progressing/Degraded) |
| **Last Sync** | 마지막 동기화 시간 |
| **Auto-Sync** | 자동 동기화 활성화 여부 |

### 📦 App of Apps 패턴에서 볼 수 있는 것들

```
root-app (부모)
├── infrastructure (인프라)
│   ├── namespaces ✅ Synced, Healthy
│   ├── network-policies ✅ Synced, Healthy
│   └── monitoring ⏳ Progressing
└── api-services (애플리케이션)
    ├── auth-api ✅ Synced, Healthy
    ├── my-api ✅ Synced, Healthy
    ├── scan-api ⚠️  OutOfSync
    ├── character-api ❌ Degraded
    ├── location-api ✅ Synced, Healthy
    ├── info-api ✅ Synced, Healthy
    └── chat-api ✅ Synced, Healthy
```

---

## 📈 3. 실시간 진행 상황 확인

### Application 상세 보기

각 Application을 클릭하면:

1. **Resource Tree** (리소스 트리)
   - Deployment, Pod, Service, Ingress 등 계층 구조 시각화
   - 각 리소스의 상태를 색깔로 표시
     - 🟢 녹색: Healthy
     - 🟡 노란색: Progressing
     - 🔴 빨간색: Degraded/Failed

2. **Sync Result** (동기화 결과)
   - 어떤 리소스가 생성/수정/삭제되었는지 로그
   - Git commit 정보

3. **Events** (이벤트)
   - Kubernetes 이벤트 실시간 스트리밍
   - Pod 생성, 이미지 Pull, CrashLoopBackOff 등

4. **Pod Logs** (파드 로그)
   - 각 Pod의 로그를 직접 확인
   - 컨테이너별 로그 분리

---

## 🎨 4. ArgoCD CLI로 모니터링

### CLI 설치

```bash
# macOS
brew install argocd

# Linux
curl -sSL -o /usr/local/bin/argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
chmod +x /usr/local/bin/argocd
```

### 로그인

```bash
# Port-forward 먼저 실행
kubectl port-forward svc/argocd-server -n argocd 8080:443 &

# 로그인
argocd login localhost:8080 --username admin --password $(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d)
```

### 모니터링 명령어

```bash
# 1. 모든 Application 상태 확인
argocd app list

# 2. 특정 Application 상세 보기
argocd app get root-app

# 3. Application 트리 구조 확인
argocd app get root-app --show-operation

# 4. 실시간 Sync 진행 상황 watch
argocd app wait root-app --sync

# 5. Application Health 확인
argocd app wait root-app --health

# 6. 모든 하위 Application 상태 확인 (App of Apps)
argocd app list -l 'parent=root-app'

# 7. Sync 히스토리 확인
argocd app history root-app

# 8. 로그 실시간 스트리밍
argocd app logs root-app --follow

# 9. 리소스 diff 확인 (Git vs Cluster)
argocd app diff root-app

# 10. Manifest 미리보기
argocd app manifests root-app
```

---

## 🔄 5. 자동 동기화 vs 수동 동기화

### 자동 동기화 (권장: 프로덕션)

```yaml
# argocd/root-app.yaml
spec:
  syncPolicy:
    automated:
      prune: true      # 삭제된 리소스 자동 제거
      selfHeal: true   # Drift 자동 복구
      allowEmpty: false
```

- ✅ Git Push → 자동으로 클러스터 배포
- ✅ Drift 발생 시 자동 복구
- ✅ 완전한 GitOps

### 수동 동기화 (권장: 개발/스테이징)

```bash
# CLI로 수동 Sync
argocd app sync root-app

# 특정 리소스만 Sync
argocd app sync root-app --resource Deployment:default:my-api

# Dry-run (실제 적용 안함)
argocd app sync root-app --dry-run
```

---

## 🚨 6. 트러블슈팅 시나리오

### Scenario 1: Application이 OutOfSync

```bash
# 1. Diff 확인
argocd app diff api-services

# 2. Git 커밋 확인
argocd app get api-services --show-params

# 3. 수동 Sync
argocd app sync api-services --prune
```

### Scenario 2: Pod가 Degraded

```bash
# 1. Application 상태 확인
argocd app get api-services

# 2. 해당 Pod 로그 확인
argocd app logs api-services --kind Pod --name scan-api-xxx

# 3. Kubernetes 이벤트 확인
kubectl describe pod scan-api-xxx -n scan
```

### Scenario 3: Sync가 실패함

```bash
# 1. Sync Operation 상태 확인
argocd app get api-services --show-operation

# 2. Sync 히스토리 확인
argocd app history api-services

# 3. 이전 버전으로 Rollback
argocd app rollback api-services <REVISION_ID>
```

---

## 📱 7. ArgoCD Notifications (선택적)

### Slack 알림 설정

```yaml
# argocd-notifications-cm ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: argocd-notifications-cm
  namespace: argocd
data:
  service.slack: |
    token: $slack-token
  template.app-sync-succeeded: |
    message: |
      Application {{.app.metadata.name}} sync succeeded!
      {{.app.status.operationState.finishedAt}}
```

---

## 🎯 8. 실전 모니터링 워크플로우

### 새 클러스터 부트스트랩 시

```bash
# 1. ArgoCD 설치 확인
kubectl get pods -n argocd

# 2. Root App 배포
kubectl apply -f argocd/root-app.yaml

# 3. 실시간 모니터링 시작
argocd app wait root-app --sync --health --timeout 600

# 4. 모든 하위 App 상태 확인
argocd app list -l 'parent=root-app'

# 5. 실패한 App 트러블슈팅
argocd app get <failing-app>
argocd app logs <failing-app> --follow
```

### 일상적인 모니터링

```bash
# 대시보드 실행
kubectl port-forward svc/argocd-server -n argocd 8080:443 &

# 브라우저에서 https://localhost:8080 접속
# → Applications 탭에서 시각적으로 모니터링
```

---

## 🔑 9. 핵심 장점

| 전통적 방식 | ArgoCD 방식 |
|------------|------------|
| `kubectl get pods -A` | 시각적 대시보드 |
| 로그 수동 확인 | 실시간 이벤트 스트림 |
| Git-Cluster 차이 모름 | Diff 자동 감지 |
| 배포 히스토리 없음 | 전체 히스토리 추적 |
| Rollback 복잡 | 원클릭 Rollback |

---

## 📚 10. 다음 단계

1. ✅ ArgoCD 설치 (Ansible playbook 09-atlantis.yml)
2. ✅ Root App 배포 (`argocd/root-app.yaml`)
3. ✅ Port-forward로 대시보드 접속
4. ✅ Applications 탭에서 실시간 모니터링
5. ✅ 문제 발생 시 CLI로 트러블슈팅

---

## 🎓 참고 자료

- [ArgoCD 공식 문서](https://argo-cd.readthedocs.io/)
- [App of Apps Pattern](https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/)
- [ArgoCD Best Practices](https://argo-cd.readthedocs.io/en/stable/user-guide/best_practices/)

