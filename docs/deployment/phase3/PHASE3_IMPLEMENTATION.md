# Phase 3 구현 가이드 (Atlantis + ArgoCD Hooks)

## 🎯 개요

Phase 3는 **완전한 GitOps**를 달성하는 단계입니다. Atlantis가 Terraform을 처리하고, ArgoCD Hooks가 Ansible을 자동 실행합니다.

```
Phase 2 (Atlantis + GitHub Actions):
  - Atlantis: Terraform Plan/Apply
  - GitHub Actions: Ansible Bootstrap + ArgoCD Sync

Phase 3 (Atlantis + ArgoCD Hooks): ⭐
  - Atlantis: Terraform Plan/Apply + ConfigMap 저장
  - ArgoCD PreSync Hook: Ansible Bootstrap (자동)
  - ArgoCD PostSync Hook: Node Labeling (자동)
  - GitHub Actions: 최소화 (ArgoCD Trigger만)
```

---

## 📋 구현 완료 사항

### 1. Atlantis Pod에 kubectl 추가

**파일**: `k8s/atlantis/atlantis-deployment.yaml`

- **Init Container**: `bitnami/kubectl` 이미지에서 kubectl 설치
- **Volume**: `emptyDir`로 kubectl 바이너리 공유
- **VolumeMount**: `/usr/local/bin/kubectl`에 마운트

```yaml
initContainers:
  - name: install-kubectl
    image: bitnami/kubectl:latest
    command:
      - /bin/sh
      - -c
      - |
        cp /opt/bitnami/kubectl/bin/kubectl /shared/kubectl
        chmod +x /shared/kubectl
    volumeMounts:
      - name: kubectl
        mountPath: /shared

volumes:
  - name: kubectl
    emptyDir: {}
```

### 2. RBAC 권한 추가

**파일**: `k8s/atlantis/atlantis-deployment.yaml`

- **ClusterRole**: ConfigMap 생성/업데이트 권한
- **ClusterRoleBinding**: Atlantis ServiceAccount에 권한 부여

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: atlantis-configmap-creator
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["create", "update", "patch", "get", "list"]
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get", "list"]
```

### 3. Atlantis Workflow 개선

**파일**: `atlantis.yaml`

- Terraform Apply 후 ConfigMap에 Outputs 저장
- argocd namespace 자동 생성
- ConfigMap 확인 로그 추가

```yaml
- run: |
    terraform output -json > /tmp/tf-outputs.json
    terraform output -raw ansible_inventory > /tmp/ansible-inventory.ini
    
    kubectl get namespace argocd &>/dev/null || kubectl create namespace argocd
    kubectl create configmap terraform-outputs \
      --from-file=tf-outputs.json=/tmp/tf-outputs.json \
      --from-file=ansible-inventory.ini=/tmp/ansible-inventory.ini \
      --namespace=argocd \
      --dry-run=client -o yaml | kubectl apply -f -
```

### 4. SSH Key Secret 생성 스크립트

**파일**: `scripts/utilities/create-ssh-key-secret.sh`

- ArgoCD Hooks에서 Ansible이 SSH 접속하기 위한 Secret 생성
- 자동으로 argocd namespace에 Secret 생성

```bash
./scripts/utilities/create-ssh-key-secret.sh
```

### 5. ArgoCD Application Hooks

**파일**: `argocd/application-14nodes-with-hooks.yaml`

- **PreSync Hook**: Ansible Bootstrap 실행
- **PostSync Hook**: Node Labeling 실행
- ConfigMap에서 Terraform Outputs 읽기

### 6. GitHub Actions Phase 3 워크플로우

**파일**: `.github/workflows/infrastructure-phase3.yml`

- PR Merge 시 ArgoCD Sync만 트리거
- Ansible 실행은 ArgoCD Hooks가 담당

---

## 🚀 배포 순서

### Step 1: SSH Key Secret 생성

```bash
# SSH Key Secret 생성 (ArgoCD Hooks용)
./scripts/utilities/create-ssh-key-secret.sh

# 확인
kubectl get secret k8s-cluster-ssh-key -n argocd
```

### Step 2: Atlantis RBAC 적용

```bash
# Atlantis Deployment 재배포 (RBAC 포함)
kubectl apply -f k8s/atlantis/atlantis-deployment.yaml

# RBAC 확인
kubectl get clusterrole atlantis-configmap-creator
kubectl get clusterrolebinding atlantis-configmap-creator
```

### Step 3: ArgoCD Application 배포

```bash
# ArgoCD Application with Hooks 배포
kubectl apply -f argocd/application-14nodes-with-hooks.yaml

# 확인
argocd app get ecoeco-infrastructure-14nodes
```

### Step 4: GitHub Actions 활성화

```bash
# Phase 3 워크플로우 활성화 (선택사항)
# .github/workflows/infrastructure-phase3.yml이 자동으로 사용됨
```

---

## 🔄 워크플로우

### 시나리오: Terraform 변경

```
1. 개발자: terraform/*.tf 수정 후 PR 생성
   ↓
2. Atlantis: 자동 Plan 실행 → PR 코멘트
   ↓
3. 팀원: PR 승인
   ↓
4. 개발자: "atlantis apply" 코멘트
   ↓
5. Atlantis: terraform apply 실행
   - EC2 인스턴스 생성/수정
   - Terraform Outputs → ConfigMap 저장 (argocd namespace) ⭐
   ↓
6. PR Auto-Merge (또는 수동 Merge)
   ↓
7. GitHub Actions: ArgoCD Sync 트리거
   ↓
8. ArgoCD PreSync Hook: Ansible Bootstrap 실행 ⭐
   - ConfigMap에서 인벤토리 읽기
   - Ansible site.yml 실행
   ↓
9. ArgoCD Sync: Kubernetes 리소스 배포
   ↓
10. ArgoCD PostSync Hook: Node Labeling 실행 ⭐
   ↓
✅ 완료
```

---

## ✅ 검증

### 1. Atlantis kubectl 확인

```bash
# Atlantis Pod에서 kubectl 확인
kubectl exec -n atlantis atlantis-0 -- kubectl version --client

# ConfigMap 생성 테스트
kubectl exec -n atlantis atlantis-0 -- kubectl get configmap terraform-outputs -n argocd
```

### 2. ConfigMap 확인

```bash
# Terraform Apply 후 ConfigMap 확인
kubectl get configmap terraform-outputs -n argocd

# 내용 확인
kubectl get configmap terraform-outputs -n argocd -o yaml
```

### 3. ArgoCD Hooks 확인

```bash
# PreSync Hook Job 확인
kubectl get jobs -n argocd | grep ansible-bootstrap

# PostSync Hook Job 확인
kubectl get jobs -n argocd | grep label-nodes

# Hook 로그 확인
kubectl logs -n argocd job/ansible-bootstrap
```

### 4. 전체 워크플로우 테스트

```bash
# 1. Terraform 파일 수정
echo "# Test" >> terraform/main.tf

# 2. PR 생성
git checkout -b test/phase3
git add terraform/main.tf
git commit -m "test: Phase 3 workflow"
git push origin test/phase3

# 3. GitHub에서 PR 생성
# 4. Atlantis Plan 확인
# 5. "atlantis apply" 코멘트
# 6. ConfigMap 생성 확인
# 7. ArgoCD Sync 확인
# 8. Ansible 실행 확인
```

---

## 📊 Phase 2 vs Phase 3 비교

| 항목 | Phase 2 | Phase 3 |
|------|---------|---------|
| **Terraform** | Atlantis | Atlantis |
| **Ansible** | GitHub Actions | ArgoCD PreSync Hook ⭐ |
| **Node Labeling** | GitHub Actions | ArgoCD PostSync Hook ⭐ |
| **ConfigMap** | 수동 또는 GitHub Actions | Atlantis 자동 저장 ⭐ |
| **GitHub Actions** | Ansible + ArgoCD Sync | ArgoCD Sync만 ⭐ |
| **자동화 수준** | 부분 자동화 | 완전 자동화 ⭐ |

---

## 🎯 장점

1. **완전한 GitOps**: 모든 변경사항이 Git을 통해 관리됨
2. **자동화**: 수동 개입 최소화 (PR 승인, "atlantis apply"만)
3. **일관성**: ArgoCD가 모든 배포를 관리
4. **가시성**: ArgoCD UI에서 전체 워크플로우 확인 가능
5. **롤백**: ArgoCD를 통한 쉬운 롤백

---

## ⚠️ 주의사항

1. **SSH Key Secret**: 반드시 사전 생성 필요
2. **ConfigMap**: Terraform Apply 후에만 생성됨
3. **ArgoCD Application**: Hooks가 포함된 버전 사용 필수
4. **타임아웃**: Ansible 실행 시간 고려 (기본 30분)

---

## 📝 다음 단계

1. **모니터링**: ArgoCD Hooks 실행 상태 모니터링
2. **알림**: Slack/Email 알림 설정
3. **정책**: OPA/Gatekeeper 정책 추가
4. **다중 환경**: Dev/Staging/Prod 분리

---

**작성일**: 2025-11-09  
**버전**: v0.7.0  
**상태**: ✅ Phase 3 구현 완료

