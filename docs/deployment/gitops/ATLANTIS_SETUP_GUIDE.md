# Atlantis 설정 가이드 (14-Node Architecture)

## 📋 개요

Atlantis는 Terraform GitOps 도구로, GitHub Pull Request를 통해 Terraform plan/apply를 자동화합니다.

**배포 위치:**
- Namespace: `atlantis`
- Node: `k8s-monitoring` (정확한 노드 지정)
- URL: `https://atlantis.growbin.app`

---

## 🚀 배포 단계

### 1. Secret 생성 (필수)

Atlantis는 다음 Secret이 필요합니다:

```bash
# GitHub Webhook Secret 생성
WEBHOOK_SECRET=$(openssl rand -hex 20)
echo "Webhook Secret: $WEBHOOK_SECRET"

# Secret 생성
kubectl create secret generic atlantis-secrets -n atlantis \
  --from-literal=github-token='YOUR_GITHUB_TOKEN' \
  --from-literal=github-webhook-secret="$WEBHOOK_SECRET" \
  --from-literal=aws-access-key-id='YOUR_AWS_ACCESS_KEY_ID' \
  --from-literal=aws-secret-access-key='YOUR_AWS_SECRET_ACCESS_KEY'
```

**필요한 값:**

1. **GitHub Token:**
   - GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
   - 권한: `repo`, `admin:repo_hook`
   - 생성: https://github.com/settings/tokens

2. **GitHub Webhook Secret:**
   - 랜덤 문자열 (보안용)
   - 생성: `openssl rand -hex 20`

3. **AWS Credentials:**
   - Terraform State 접근용
   - IAM 권한: Terraform 실행에 필요한 모든 권한

### 2. Ansible로 배포

```bash
cd ansible
ansible-playbook -i inventory/hosts.ini site.yml
```

또는 Atlantis만 배포:

```bash
ansible-playbook -i inventory/hosts.ini playbooks/09-atlantis.yml
```

### 3. 수동 배포 (선택)

```bash
# Namespace 생성
kubectl create namespace atlantis

# Secret 생성 (위 참고)

# ConfigMap 생성
kubectl create configmap atlantis-config -n atlantis \
  --from-literal=AWS_REGION=ap-northeast-2

# Deployment 적용
kubectl apply -f k8s/atlantis/atlantis-deployment.yaml

# Ingress는 14-nodes-ingress.yaml에 포함됨
kubectl apply -f k8s/ingress/14-nodes-ingress.yaml
```

---

## 🔗 GitHub Webhook 설정

### 1. Repository Settings

1. GitHub Repository → Settings → Webhooks
2. "Add webhook" 클릭
3. 설정:
   - **Payload URL**: `https://atlantis.growbin.app/events`
   - **Content type**: `application/json`
   - **Secret**: (위에서 생성한 `github-webhook-secret`)
   - **SSL verification**: ✅ **Enable SSL verification** (체크)
   - **Events**: 
     - ✅ Pull requests
     - ✅ Pushes
     - ✅ Issue comments (선택)
   - **Active**: ✅ (체크)
4. "Add webhook" 클릭

### 2. Webhook 테스트

1. PR 생성 (terraform/ 디렉토리 수정)
2. GitHub에서 Webhook 전송 확인
3. Atlantis Pod 로그 확인:
   ```bash
   kubectl logs -n atlantis atlantis-0 -f
   ```

---

## 🧪 테스트

### 1. PR 생성

```bash
# terraform/ 디렉토리 수정
cd terraform
echo "# Test" >> test.tf
git add .
git commit -m "test: Atlantis test"
git push origin feature/test-atlantis

# GitHub에서 PR 생성
```

### 2. Atlantis Plan

PR 생성 시 자동으로 `atlantis plan`이 실행됩니다:
- PR 코멘트에 Plan 결과가 표시됩니다
- `atlantis.yaml`의 `autoplan` 설정에 따라 자동 실행

### 3. Atlantis Apply

PR 승인 후 코멘트에 `atlantis apply` 입력:
- Terraform Apply 실행
- 결과가 PR 코멘트에 표시
- `automerge: true` 설정 시 자동 Merge

---

## 📊 Atlantis 동작 흐름

```
1. PR 생성 (terraform/ 수정)
   ↓
2. GitHub Webhook → ALB → Atlantis Pod
   ↓
3. Atlantis Pod:
   - Git Clone
   - terraform init
   - terraform plan
   - PR 코멘트에 Plan 결과
   ↓
4. PR 승인 + "atlantis apply" 코멘트
   ↓
5. Atlantis Pod:
   - terraform apply
   - Terraform Outputs → ConfigMap (argocd namespace)
   - PR 코멘트에 Apply 결과
   ↓
6. 자동 Merge (automerge: true)
```

---

## 🔧 설정 파일

### atlantis.yaml (프로젝트 루트)

- 프로젝트 정의
- Workflow 커스터마이징
- Apply 요구사항

### k8s/atlantis/atlantis-deployment.yaml

- StatefulSet 설정
- 환경 변수
- 리소스 제한
- PersistentVolume (20Gi)

---

## 🐛 문제 해결

### 1. Pod가 시작되지 않음

```bash
# Pod 상태 확인
kubectl get pods -n atlantis

# Pod 로그 확인
kubectl logs -n atlantis atlantis-0

# Secret 확인
kubectl get secret atlantis-secrets -n atlantis -o yaml
```

### 2. Webhook이 작동하지 않음

```bash
# Ingress 확인
kubectl get ingress -n atlantis

# ALB 확인
kubectl describe ingress atlantis-ingress -n atlantis

# Webhook Secret 확인
kubectl get secret atlantis-secrets -n atlantis -o jsonpath='{.data.github-webhook-secret}' | base64 -d
```

### 3. Terraform 실행 실패

```bash
# Pod 내부 접속
kubectl exec -it -n atlantis atlantis-0 -- /bin/sh

# Terraform 디렉토리 확인
ls -la /atlantis-data/repos/github.com/SeSACTHON/backend/terraform/

# AWS Credentials 확인
echo $AWS_ACCESS_KEY_ID
```

---

## 📝 참고

- [Atlantis 공식 문서](https://www.runatlantis.io/)
- [Atlantis GitHub](https://github.com/runatlantis/atlantis)
- [Terraform GitOps 가이드](../architecture/gitops-automation-design.md)

