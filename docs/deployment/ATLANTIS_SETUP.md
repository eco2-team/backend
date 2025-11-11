# Atlantis 설정 가이드 (14-Node Architecture)

## 📋 개요

Atlantis는 Terraform GitOps 도구로, GitHub Pull Request를 통해 Terraform plan/apply를 자동화합니다.

**배포 위치:**
- Namespace: `atlantis`
- Node: `k8s-monitoring` (workload=monitoring)
- URL: `https://atlantis.growbin.app`

---

## 🚀 배포 방법

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
ansible-playbook site.yml
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

### 2. Webhook 설정

```
Payload URL: https://atlantis.growbin.app/events
Content type: application/json
Secret: (위에서 생성한 github-webhook-secret)
Events: 
  ✅ Pull requests
  ✅ Pushes
Active: ✅
```

### 3. Webhook 테스트

Webhook 생성 후 "Recent Deliveries"에서 테스트 이벤트 확인

---

## 📝 사용 방법

### 1. Terraform 변경

```bash
# 브랜치 생성
git checkout -b feature/add-new-resource

# Terraform 파일 수정
vim terraform/main.tf

# 커밋 및 푸시
git add terraform/
git commit -m "feat: Add new resource"
git push origin feature/add-new-resource
```

### 2. Pull Request 생성

GitHub에서 PR 생성 → Atlantis가 자동으로 `atlantis plan` 실행

### 3. Plan 검토

PR 코멘트에서 Plan 결과 확인:
```
atlantis plan
```

### 4. Apply 실행

Plan 검토 후 PR 승인 → PR 코멘트에 입력:
```
atlantis apply
```

### 5. 자동 Merge (선택)

`atlantis.yaml`에서 `automerge: true` 설정 시 Apply 성공 후 자동 Merge

---

## ⚙️ 설정 파일

### atlantis.yaml (프로젝트 루트)

```yaml
version: 3

projects:
  - name: infrastructure
    dir: terraform
    workspace: production
    terraform_version: v1.5.0
    workflow: infrastructure-workflow
    apply_requirements:
      - approved
      - mergeable
    autoplan:
      enabled: true
      when_modified:
        - "*.tf"
        - "*.tfvars"
        - "terraform.tfvars"

workflows:
  infrastructure-workflow:
    plan:
      steps:
        - init
        - run: terraform validate
        - plan:
            extra_args:
              - -lock-timeout=5m
              - -var-file=terraform.tfvars
    apply:
      steps:
        - init
        - apply:
            extra_args:
              - -lock-timeout=5m
              - -var-file=terraform.tfvars
        - run: |
            # Terraform Outputs를 ConfigMap에 저장 (ArgoCD 연계)
            terraform output -json > /tmp/tf-outputs.json
            kubectl create configmap terraform-outputs \
              --from-file=tf-outputs.json=/tmp/tf-outputs.json \
              --namespace=argocd \
              --dry-run=client -o yaml | kubectl apply -f -
```

---

## 🔍 확인 및 디버깅

### Pod 상태 확인

```bash
kubectl get pods -n atlantis
kubectl logs -n atlantis atlantis-0
```

### Service 확인

```bash
kubectl get svc -n atlantis
```

### Ingress 확인

```bash
kubectl get ingress -n atlantis
kubectl describe ingress atlantis-ingress -n atlantis
```

### Health Check

```bash
curl https://atlantis.growbin.app/healthz
```

### Webhook 이벤트 확인

GitHub Repository → Settings → Webhooks → Recent Deliveries

---

## 🎯 주요 기능

### 1. 자동 Plan

- PR 생성 시 자동으로 `terraform plan` 실행
- `atlantis.yaml`의 `autoplan` 설정으로 제어

### 2. Apply 승인 요구사항

- `apply_requirements: ["approved"]` - PR 승인 필수
- `apply_requirements: ["mergeable"]` - Conflict 없어야 함

### 3. Workflow 커스터마이징

- `infrastructure-workflow` 사용
- Plan/Apply 단계별 커스텀 스텝 추가 가능

### 4. ArgoCD 연계

- Apply 완료 후 Terraform Outputs를 ConfigMap에 저장
- ArgoCD가 ConfigMap을 읽어서 자동 Sync

---

## 📊 리소스 요청/제한

```yaml
resources:
  requests:
    memory: 512Mi
    cpu: 250m
  limits:
    memory: 2Gi
    cpu: 1000m
```

**Storage:**
- PersistentVolumeClaim: 20Gi (EBS gp3)
- 경로: `/atlantis-data`

---

## 🔐 보안 고려사항

### 1. GitHub Token

- 최소 권한 원칙 (repo, admin:repo_hook만)
- 정기적으로 갱신

### 2. Webhook Secret

- 강력한 랜덤 문자열 사용
- Secret에 안전하게 저장

### 3. AWS Credentials

- IAM Role 사용 권장 (IRSA)
- 최소 권한 원칙

### 4. HTTPS

- ALB에서 HTTPS 종료
- ACM 인증서 사용

---

## 🐛 문제 해결

### 1. Pod가 시작되지 않음

```bash
# Pod 상태 확인
kubectl describe pod -n atlantis atlantis-0

# Secret 확인
kubectl get secret atlantis-secrets -n atlantis

# 로그 확인
kubectl logs -n atlantis atlantis-0
```

### 2. Webhook이 작동하지 않음

```bash
# Ingress 확인
kubectl get ingress -n atlantis

# ALB Health Check 확인
aws elbv2 describe-target-health --target-group-arn <TG_ARN>

# GitHub Webhook Deliveries 확인
# Repository Settings → Webhooks → Recent Deliveries
```

### 3. Terraform Plan 실패

```bash
# Atlantis Pod 로그 확인
kubectl logs -n atlantis atlantis-0 -f

# Terraform State 접근 권한 확인
# AWS Credentials 확인
```

---

## 📚 참고 문서

- [Atlantis 공식 문서](https://www.runatlantis.io/)
- [Atlantis GitHub](https://github.com/runatlantis/atlantis)
- [Terraform GitOps 가이드](https://www.runatlantis.io/docs/terraform-cloud.html)

---

**작성일:** 2025-11-09  
**버전:** v0.27.0  
**클러스터:** 14-Node Architecture

