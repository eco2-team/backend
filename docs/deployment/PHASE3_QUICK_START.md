# Phase 3 빠른 시작 가이드

## 🚀 5분 안에 Phase 3 활성화하기

### Step 1: SSH Key Secret 생성 (1분)

```bash
./scripts/utilities/create-ssh-key-secret.sh
```

**확인**:
```bash
kubectl get secret k8s-cluster-ssh-key -n argocd
```

---

### Step 2: Atlantis 재배포 (2분)

```bash
# Phase 3 기능 포함된 Atlantis 배포
kubectl apply -f k8s/atlantis/atlantis-deployment.yaml

# Pod 재시작 확인
kubectl rollout status statefulset/atlantis -n atlantis

# kubectl 설치 확인
kubectl exec -n atlantis atlantis-0 -- kubectl version --client
```

---

### Step 3: ArgoCD Application 배포 (1분)

```bash
# Hooks 포함된 Application 배포
kubectl apply -f argocd/application-14nodes-with-hooks.yaml

# 확인
argocd app get ecoeco-infrastructure-14nodes
```

---

### Step 4: GitHub Webhook 설정 (1분)

1. GitHub Repository → **Settings** → **Webhooks**
2. **Add webhook** 클릭
3. 설정:
   - **Payload URL**: `https://atlantis.growbin.app/events`
   - **Content type**: `application/json`
   - **SSL verification**: ✅ Enable
   - **Secret**: (Atlantis Secret의 `github-webhook-secret` 값)
   - **Events**: 
     - ✅ Pull requests
     - ✅ Pushes
     - ✅ Issue comments

---

## ✅ 검증

### 1. Atlantis kubectl 확인

```bash
kubectl exec -n atlantis atlantis-0 -- kubectl version --client
```

**예상 결과**: `Client Version: v1.28.x`

### 2. RBAC 권한 확인

```bash
kubectl get clusterrole atlantis-configmap-creator
kubectl get clusterrolebinding atlantis-configmap-creator
```

### 3. 테스트 PR 생성

```bash
# 1. Feature 브랜치 생성
git checkout -b test/phase3

# 2. Terraform 파일 수정
echo "# Phase 3 Test" >> terraform/main.tf

# 3. 커밋 및 푸시
git add terraform/main.tf
git commit -m "test: Phase 3 workflow"
git push origin test/phase3

# 4. GitHub에서 PR 생성
# 5. Atlantis Plan 자동 실행 확인
# 6. PR에 "atlantis apply" 코멘트
# 7. ConfigMap 생성 확인
kubectl get configmap terraform-outputs -n argocd
```

---

## 🔄 워크플로우 확인

### 정상 동작 시나리오

```
1. PR 생성
   ↓
2. Atlantis Plan (자동)
   ↓
3. "atlantis apply" 코멘트
   ↓
4. Atlantis Apply
   - Terraform Outputs → ConfigMap 저장 ✅
   ↓
5. PR Merge
   ↓
6. GitHub Actions: ArgoCD Sync
   ↓
7. ArgoCD PreSync Hook: Ansible 실행 ✅
   ↓
8. ArgoCD Sync: K8s 리소스 배포
   ↓
9. ArgoCD PostSync Hook: Node Labeling ✅
   ↓
✅ 완료
```

---

## 🐛 문제 해결

### ConfigMap이 생성되지 않음

```bash
# 1. Atlantis Pod 로그 확인
kubectl logs -n atlantis atlantis-0 | grep -i configmap

# 2. RBAC 권한 확인
kubectl auth can-i create configmaps --namespace=argocd --as=system:serviceaccount:atlantis:atlantis

# 3. kubectl 설치 확인
kubectl exec -n atlantis atlantis-0 -- which kubectl
```

### ArgoCD Hook이 실행되지 않음

```bash
# 1. SSH Key Secret 확인
kubectl get secret k8s-cluster-ssh-key -n argocd

# 2. Hook Job 확인
kubectl get jobs -n argocd | grep -E "ansible-bootstrap|label-nodes"

# 3. Hook 로그 확인
kubectl logs -n argocd job/ansible-bootstrap
```

### Ansible이 SSH 접속 실패

```bash
# 1. SSH Key Secret 내용 확인
kubectl get secret k8s-cluster-ssh-key -n argocd -o jsonpath='{.data.ssh-privatekey}' | base64 -d

# 2. EC2 Security Group 확인 (SSH 포트 22 허용)
# 3. EC2 인스턴스 상태 확인
```

---

## 📚 상세 문서

- [Phase 3 구현 가이드](./PHASE3_IMPLEMENTATION.md)
- [Atlantis 현재 상태](./ATLANTIS_CURRENT_STATUS.md)
- [ArgoCD Hooks 설정 가이드](./argocd-hooks-setup-guide.md)

---

**작성일**: 2025-11-09  
**버전**: v0.7.0

