# Atlantis Deployment 파일을 찾을 수 없는 문제

## 📋 증상

Master 노드에서 다음 명령어 실행 시 에러 발생:

```bash
kubectl apply -f k8s/atlantis/atlantis-deployment.yaml
# error: the path "k8s/atlantis/atlantis-deployment.yaml" does not exist
```

하지만:
- ✅ Atlantis 웹사이트 접속 가능 (`https://atlantis.growbin.app`)
- ✅ GitHub Webhook 등록됨

---

## 🔍 원인 분석

### 문제점

1. **Master 노드에는 Git 저장소가 없음**
   - `k8s/atlantis/atlantis-deployment.yaml` 파일은 로컬 개발 환경에만 존재
   - Master 노드는 EC2 인스턴스로, Git 저장소가 클론되어 있지 않음

2. **Atlantis 배포 방식**
   - Atlantis는 **Ansible을 통해 배포**됨 (`ansible/playbooks/09-atlantis.yml`)
   - Ansible은 로컬에서 실행되며, Master 노드에 SSH로 접속하여 `kubectl apply` 실행
   - Ansible이 파일 경로를 `{{ playbook_dir }}/../../k8s/atlantis/atlantis-deployment.yaml`로 해석

3. **현재 상태**
   - 웹사이트 접속 가능 → Ingress/Service는 정상
   - Webhook 등록됨 → GitHub 설정은 정상
   - 하지만 Pod 상태는 확인 필요

---

## ✅ 해결 방법

### 방법 1: Ansible을 통해 재배포 (권장)

로컬 개발 환경에서 실행:

```bash
# 1. 로컬에서 Ansible 실행
cd /Users/mango/workspace/SeSACTHON/backend

# 2. Atlantis만 재배포
ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/09-atlantis.yml

# 또는 전체 재배포
ansible-playbook -i ansible/inventory/hosts.ini ansible/site.yml
```

**장점**:
- ✅ 모든 설정이 자동으로 적용됨
- ✅ Secret, ConfigMap, RBAC 모두 자동 생성
- ✅ 일관성 유지

---

### 방법 2: Master 노드에 파일 복사 후 수동 적용

```bash
# 1. 로컬에서 Master 노드로 파일 복사
scp -i ~/.ssh/id_rsa \
  k8s/atlantis/atlantis-deployment.yaml \
  ubuntu@<MASTER_IP>:/tmp/atlantis-deployment.yaml

# 2. Master 노드에서 SSH 접속
ssh -i ~/.ssh/id_rsa ubuntu@<MASTER_IP>

# 3. Master 노드에서 적용
kubectl apply -f /tmp/atlantis-deployment.yaml
```

**주의사항**:
- ⚠️ Secret과 ConfigMap은 수동으로 생성해야 함
- ⚠️ RBAC 권한도 수동으로 적용해야 함

---

### 방법 3: 현재 상태 확인 후 필요시 재배포

```bash
# Master 노드에서 실행

# 1. Atlantis Pod 상태 확인
kubectl get pods -n atlantis

# 2. StatefulSet 확인
kubectl get statefulset -n atlantis

# 3. Pod 로그 확인
kubectl logs -n atlantis atlantis-0

# 4. kubectl 설치 확인 (Phase 3)
kubectl exec -n atlantis atlantis-0 -- kubectl version --client 2>&1
```

**결과에 따른 조치**:
- Pod가 `Running`이고 kubectl이 작동하면 → 정상
- Pod가 없거나 `CrashLoopBackOff`면 → Ansible로 재배포 필요
- kubectl이 없으면 → Phase 3 업데이트 적용 필요

---

## 🎯 권장 해결 순서

### Step 1: 현재 상태 확인

Master 노드에서:

```bash
# Pod 상태
kubectl get pods -n atlantis

# StatefulSet 확인
kubectl get statefulset -n atlantis -o yaml | grep -A 5 "initContainers:"

# kubectl 확인 (Phase 3)
kubectl exec -n atlantis atlantis-0 -- kubectl version --client 2>&1 || echo "kubectl not found"
```

### Step 2: 문제 확인

- **Pod가 없음** → Ansible로 재배포 필요
- **Pod는 있지만 kubectl 없음** → Phase 3 업데이트 적용 필요
- **Pod는 있고 kubectl도 있음** → 정상 (다른 문제일 수 있음)

### Step 3: 재배포

로컬에서:

```bash
# Ansible로 재배포 (Phase 3 포함)
ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/09-atlantis.yml
```

---

## 📊 Atlantis 배포 아키텍처

```
로컬 개발 환경
  ├─ k8s/atlantis/atlantis-deployment.yaml (파일 존재)
  └─ ansible/playbooks/09-atlantis.yml (배포 스크립트)
       │
       │ SSH 접속
       ↓
Master 노드 (EC2)
  ├─ kubectl (Kubernetes API 접근)
  └─ Atlantis Pod (실제 실행)
       ├─ Init Container: kubectl 설치
       └─ Main Container: Atlantis 실행
```

---

## 🔧 Ansible 배포 과정

Ansible이 실행하는 과정:

1. **로컬에서 파일 읽기**: `{{ playbook_dir }}/../../k8s/atlantis/atlantis-deployment.yaml`
2. **Master 노드에 SSH 접속**
3. **Master 노드에서 kubectl apply 실행** (파일 내용을 stdin으로 전달하거나 임시 파일 생성)

**실제 명령어**:
```bash
# Ansible이 Master 노드에서 실행하는 명령어
kubectl apply -f /tmp/ansible-<random>/atlantis-deployment.yaml
```

---

## 💡 왜 웹사이트는 접속되는가?

1. **Ingress/Service는 이미 배포됨**
   - `k8s/ingress/14-nodes-ingress.yaml`에 Atlantis Ingress 포함
   - `07-ingress-resources.yml`에서 자동 생성됨

2. **이전 배포가 남아있을 수 있음**
   - Pod가 재시작되거나 삭제되었지만 Service/Ingress는 남아있음
   - 또는 Pod가 다른 문제로 실행 중일 수 있음

3. **확인 필요**
   - Pod 상태 확인
   - 로그 확인
   - kubectl 설치 확인 (Phase 3)

---

## 📝 다음 단계

1. **현재 상태 확인**:
   ```bash
   kubectl get pods -n atlantis
   kubectl logs -n atlantis atlantis-0
   ```

2. **문제에 따라 조치**:
   - Pod 없음 → Ansible 재배포
   - Pod 있지만 kubectl 없음 → Ansible 재배포 (Phase 3 포함)
   - Pod 정상 → 다른 문제 확인

3. **Ansible 재배포**:
   ```bash
   # 로컬에서
   ansible-playbook -i ansible/inventory/hosts.ini ansible/playbooks/09-atlantis.yml
   ```

---

## 🔗 관련 문서

- [Atlantis 배포 가이드](../deployment/ATLANTIS_SETUP_GUIDE.md)
- [Phase 3 구현 가이드](../deployment/PHASE3_IMPLEMENTATION.md)
- [Atlantis 현재 상태](../deployment/ATLANTIS_CURRENT_STATUS.md)

---

**작성일**: 2025-11-09  
**해결 버전**: v0.7.0 (Phase 3)

