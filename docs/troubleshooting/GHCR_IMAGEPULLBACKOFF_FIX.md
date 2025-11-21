# GHCR ImagePullBackOff 해결 가이드

## 🚨 문제 상황

### 증상
```bash
$ kubectl get pods -A | grep ImagePullBackOff
auth              auth-api-7644c8d8f9-svrks              0/1     ImagePullBackOff   0          4h25m
character         character-api-5447cbf969-g5qtl         0/1     ImagePullBackOff   0          4h25m
chat              chat-api-7dfb99ff59-8pfbn              0/1     ImagePullBackOff   0          4h25m
info              info-api-86544dd5b7-gn9lj              0/1     ImagePullBackOff   0          4h25m
location          location-api-677dd46b59-h7wfj          0/1     ImagePullBackOff   0          4h25m
my                my-api-578cbf864c-xw4rf                0/1     ImagePullBackOff   0          4h25m
scan              scan-api-65bd4d47cf-57l9k              0/1     ImagePullBackOff   0          4h25m
```

### 상세 에러
```bash
$ kubectl describe pod auth-api-xxx -n auth | grep -A5 "Events:"
Events:
  Type     Reason     Age                From               Message
  ----     ------     ----               ----               -------
  Normal   Scheduled  5m                 default-scheduler  Successfully assigned auth/auth-api-xxx to k8s-api-auth
  Normal   Pulling    3m (x4 over 5m)    kubelet            Pulling image "ghcr.io/sesacthon/auth-api:latest"
  Warning  Failed     3m (x4 over 5m)    kubelet            Failed to pull image "ghcr.io/sesacthon/auth-api:latest": rpc error: code = Unknown desc = failed to pull and unpack image "ghcr.io/sesacthon/auth-api:latest": failed to resolve reference "ghcr.io/sesacthon/auth-api:latest": pull access denied, repository does not exist or may require authorization: server message: insufficient_scope: authorization failed
  Warning  Failed     3m (x4 over 5m)    kubelet            Error: ErrImagePull
  Normal   BackOff    2m (x6 over 5m)    kubelet            Back-off pulling image "ghcr.io/sesacthon/auth-api:latest"
  Warning  Failed     2m (x6 over 5m)    kubelet            Error: ImagePullBackOff
```

### 근본 원인
- GitHub Container Registry의 이미지가 **Private**으로 설정되어 있음
- Kubernetes Pod가 GHCR에서 이미지를 Pull할 때 인증이 필요
- `imagePullSecrets: ghcr-secret`이 정의되어 있지만, 실제 Secret이 각 네임스페이스에 존재하지 않음

---

## 🔍 원인 분석

### 1. Deployment 설정 확인
```yaml
# workloads/domains/auth/base/deployment.yaml
spec:
  template:
    spec:
      containers:
        - name: auth-api
          image: ghcr.io/sesacthon/auth-api:latest  # Private image
      imagePullSecrets:
        - name: ghcr-secret  # Secret이 필요
```

### 2. Secret 부재
```bash
$ kubectl get secret ghcr-secret -n auth
Error from server (NotFound): secrets "ghcr-secret" not found
```

### 3. 기존 방식의 문제점
- 문서에 수동 생성 가이드만 있음 (`kubectl create secret docker-registry ...`)
- 클러스터 재생성 시 매번 수동으로 Secret 생성 필요
- 7개 네임스페이스에 각각 생성해야 하므로 휴먼 에러 발생 가능
- Token 갱신 시 모든 네임스페이스 업데이트 필요

---

## ✅ 해결 방법: ExternalSecret 자동화

### 아키텍처
```
Terraform (SSM Parameter 생성)
    ↓
    ├─ /sesacthon/dev/ghcr/username: mangowhoiscloud
    └─ /sesacthon/dev/ghcr/token: gho_****... (SecureString)
    ↓
ExternalSecrets Operator (Secret 생성)
    ↓
각 네임스페이스에 ghcr-secret (type: kubernetes.io/dockerconfigjson)
    ↓
Pod의 imagePullSecrets로 자동 주입
```

---

## 📝 구현 단계

### Step 1: Terraform에 GHCR Credential 추가

**파일**: `terraform/ssm-parameters.tf`

```hcl
# GHCR Username (String)
resource "aws_ssm_parameter" "ghcr_username" {
  name        = "/sesacthon/${var.environment}/ghcr/username"
  type        = "String"
  value       = "mangowhoiscloud"
  description = "GitHub Container Registry Username"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "ghcr"
    Environment = var.environment
  }
}

# GHCR Token (SecureString)
resource "aws_ssm_parameter" "ghcr_token" {
  name        = "/sesacthon/${var.environment}/ghcr/token"
  type        = "SecureString"
  value       = var.ghcr_token
  description = "GitHub Container Registry Personal Access Token"
  tags = {
    ManagedBy   = "terraform"
    Scope       = "ghcr"
    Environment = var.environment
  }
}
```

**파일**: `terraform/variables.tf`

```hcl
variable "ghcr_token" {
  description = "GitHub Container Registry Personal Access Token (read:packages 권한 필요)"
  type        = string
  sensitive   = true
  default     = ""
}
```

### Step 2: ExternalSecret 정의

**파일**: `workloads/secrets/external-secrets/dev/ghcr-pull-secret.yaml`

```yaml
---
# auth namespace용 GHCR Pull Secret
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: ghcr-pull-secret
  namespace: auth
spec:
  refreshInterval: 24h
  secretStoreRef:
    kind: ClusterSecretStore
    name: aws-ssm-store
  data:
    - secretKey: username
      remoteRef:
        key: /sesacthon/dev/ghcr/username
    - secretKey: password
      remoteRef:
        key: /sesacthon/dev/ghcr/token
  target:
    name: ghcr-secret
    creationPolicy: Owner
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {
            "auths": {
              "ghcr.io": {
                "username": "{{ .username }}",
                "password": "{{ .password }}",
                "auth": "{{ printf "%s:%s" .username .password | b64enc }}"
              }
            }
          }
---
# my, scan, character, location, info, chat 네임스페이스도 동일
# (총 7개 네임스페이스)
```

**파일**: `workloads/secrets/external-secrets/dev/kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
- ../base
- alb-controller-secret.yaml
- data-secrets.yaml
- ingress-acm-secret.yaml
- ghcr-pull-secret.yaml  # 추가
```

### Step 3: Deployment에서 imagePullSecrets 사용

**파일**: `workloads/domains/auth/base/deployment.yaml` (이미 구현됨)

```yaml
spec:
  template:
    spec:
      containers:
        - name: auth-api
          image: ghcr.io/sesacthon/auth-api:latest
      imagePullSecrets:
        - name: ghcr-secret  # ExternalSecret이 생성한 Secret 참조
```

---

## 🚀 적용 절차

### 1. GitHub Personal Access Token 생성

1. GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. "Generate new token (classic)" 클릭
3. Scopes 선택:
   - ✅ `read:packages` (GHCR 이미지 읽기)
   - ✅ `write:packages` (이미지 푸시 필요 시)
4. Token 복사 (예: `gho_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)

또는 기존 `gh` CLI 토큰 사용:
```bash
gh auth token
```

### 2. Terraform Apply

```bash
# 서버 또는 로컬에서 실행
cd terraform

# 환경변수로 Token 주입 (Git에 저장하지 않음)
export TF_VAR_ghcr_token=$(gh auth token)

# Plan 확인
terraform plan -var-file=env/dev.tfvars

# Apply
terraform apply -var-file=env/dev.tfvars -auto-approve
```

### 3. SSM Parameter 검증

```bash
# Username 확인
aws ssm get-parameter \
  --name /sesacthon/dev/ghcr/username \
  --query Parameter.Value \
  --output text

# Token 확인 (복호화)
aws ssm get-parameter \
  --name /sesacthon/dev/ghcr/token \
  --with-decryption \
  --query Parameter.Value \
  --output text
```

### 4. Git 변경사항 적용

```bash
# 로컬에서 커밋/푸시
git add workloads/secrets/external-secrets/dev/ghcr-pull-secret.yaml
git add workloads/secrets/external-secrets/dev/kustomization.yaml
git add terraform/ssm-parameters.tf terraform/variables.tf
git commit -m "feat: Automate GHCR pull secrets via ExternalSecrets"
git push origin refactor/gitops-sync-wave

# 서버에서 pull
cd ~/backend
git pull origin refactor/gitops-sync-wave
```

### 5. ArgoCD 동기화

```bash
# ExternalSecret CR 배포
argocd app sync dev-secrets

# 또는 kubectl로 직접 적용
kubectl apply -f workloads/secrets/external-secrets/dev/ghcr-pull-secret.yaml
```

### 6. ExternalSecret → Secret 생성 확인

```bash
# ExternalSecret 상태 확인
for ns in auth my scan character location info chat; do
  echo "=== Namespace: $ns ==="
  kubectl get externalsecret ghcr-pull-secret -n $ns
  kubectl describe externalsecret ghcr-pull-secret -n $ns | grep -A5 "Status:"
done

# Secret 생성 확인
for ns in auth my scan character location info chat; do
  echo "=== Namespace: $ns ==="
  kubectl get secret ghcr-secret -n $ns
done

# Secret 내용 검증 (dockerconfigjson 형식)
kubectl get secret ghcr-secret -n auth -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq
```

### 7. API Pod 재시작

```bash
# 모든 API Deployment 재시작
for ns in auth my scan character location info chat; do
  kubectl rollout restart deployment ${ns}-api -n $ns
  kubectl rollout status deployment ${ns}-api -n $ns
done
```

### 8. ImagePullBackOff 해결 확인

```bash
# Pod 상태 확인
kubectl get pods -A | grep -E "auth-api|my-api|scan-api|character-api|location-api|info-api|chat-api"

# 모두 Running이어야 함
# 0/1 → 1/1 변경 확인
```

---

## 🔧 트러블슈팅

### 문제 1: ExternalSecret이 Secret을 생성하지 않음

**증상**:
```bash
$ kubectl describe externalsecret ghcr-pull-secret -n auth
Status:
  Conditions:
    Message: could not get secret data from provider: parameter /sesacthon/dev/ghcr/token not found
```

**원인**: SSM Parameter가 생성되지 않음

**해결**:
```bash
cd terraform
terraform apply -var-file=env/dev.tfvars
```

### 문제 2: Secret은 있는데 여전히 ImagePullBackOff

**원인**: Secret 형식 오류 또는 Token 권한 부족

**확인**:
```bash
# Secret 형식 검증
kubectl get secret ghcr-secret -n auth -o jsonpath='{.type}'
# 출력: kubernetes.io/dockerconfigjson

# .dockerconfigjson 내용 확인
kubectl get secret ghcr-secret -n auth -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq

# Token 권한 확인 (로컬에서)
TOKEN=$(gh auth token)
curl -H "Authorization: Bearer $TOKEN" https://ghcr.io/v2/sesacthon/auth-api/tags/list
```

### 문제 3: Token 만료

**증상**: Secret은 생성되었지만 시간이 지나면 다시 ImagePullBackOff

**해결**:
```bash
# 새 Token 생성
gh auth login

# SSM Parameter 업데이트
export TF_VAR_ghcr_token=$(gh auth token)
terraform apply -var-file=env/dev.tfvars

# ExternalSecret이 자동으로 24시간 이내 갱신됨
# 즉시 갱신하려면
kubectl annotate externalsecret ghcr-pull-secret -n auth \
  force-sync=$(date +%s) --overwrite
```

### 문제 4: Pod는 Running인데 CrashLoopBackOff

**원인**: 이미지는 Pull 성공했지만 애플리케이션 실행 실패

**확인**:
```bash
# 로그 확인
kubectl logs -n auth auth-api-xxx

# ConfigMap/Secret 누락 확인
kubectl get configmap auth-config -n auth
kubectl get secret auth-secret -n auth
```

---

## 📋 체크리스트

### Terraform
- [ ] `terraform/ssm-parameters.tf`에 GHCR username/token Parameter 추가
- [ ] `terraform/variables.tf`에 `ghcr_token` 변수 추가
- [ ] `export TF_VAR_ghcr_token=$(gh auth token)` 실행
- [ ] `terraform apply` 완료
- [ ] SSM Parameter 생성 확인

### ExternalSecret
- [ ] `workloads/secrets/external-secrets/dev/ghcr-pull-secret.yaml` 생성
- [ ] 7개 네임스페이스 모두 정의 (auth, my, scan, character, location, info, chat)
- [ ] `kustomization.yaml`에 추가
- [ ] Git commit/push

### ArgoCD
- [ ] `argocd app sync dev-secrets` 실행
- [ ] ExternalSecret CR 생성 확인 (`kubectl get externalsecret -A`)
- [ ] Secret 생성 확인 (`kubectl get secret ghcr-secret -A`)

### Deployment
- [ ] 모든 API Deployment 재시작
- [ ] Pod 상태 `Running` 확인
- [ ] ImagePullBackOff 해결 확인

---

## 🎯 자동화 이점

### Before (수동)
```bash
# 네임스페이스마다 수동 생성
for ns in auth my scan character location info chat; do
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username=mangowhoiscloud \
    --docker-password=gho_xxx... \
    --docker-email=ryoo0504@gmail.com \
    -n $ns
done
```

**문제점**:
- 클러스터 재생성 시 매번 반복
- Token 노출 위험 (Shell History)
- 휴먼 에러 (네임스페이스 누락)

### After (자동화)
```bash
# 1회만 Terraform apply
export TF_VAR_ghcr_token=$(gh auth token)
terraform apply -var-file=env/dev.tfvars

# 이후 자동 생성/갱신
# - ExternalSecret이 SSM에서 자동으로 가져옴
# - 각 네임스페이스에 Secret 자동 생성
# - 24시간마다 자동 갱신
```

**장점**:
- ✅ GitOps 완전 자동화
- ✅ Token을 SSM SecureString에 안전 보관
- ✅ 클러스터 재생성 시 자동 복구
- ✅ 네임스페이스 추가 시 ExternalSecret만 추가하면 끝

---

## 🔐 보안 고려사항

### 1. Token 관리
- ✅ **SSM SecureString 사용**: Token을 암호화 저장
- ✅ **Terraform sensitive 변수**: `ghcr_token`을 sensitive로 설정해 로그 노출 방지
- ✅ **환경변수 주입**: `TF_VAR_ghcr_token`으로 주입, Git에 저장하지 않음
- ⚠️ **Token 권한 최소화**: `read:packages`만 부여, `write:packages`는 CI/CD만

### 2. Secret 접근 제어
- ExternalSecrets Operator만 SSM Parameter 읽기 가능 (IRSA 또는 노드 Role)
- 각 네임스페이스의 Pod만 해당 네임스페이스의 `ghcr-secret` 접근 가능
- NetworkPolicy로 Pod 간 통신 제한

### 3. Token 갱신 절차
```bash
# 1. GitHub에서 새 Token 생성
# 2. SSM Parameter 업데이트
aws ssm put-parameter \
  --name /sesacthon/dev/ghcr/token \
  --value "gho_new_token" \
  --type SecureString \
  --overwrite

# 3. ExternalSecret이 24시간 이내 자동 갱신
# 또는 즉시 갱신
for ns in auth my scan character location info chat; do
  kubectl annotate externalsecret ghcr-pull-secret -n $ns \
    force-sync=$(date +%s) --overwrite
done
```

---

## 📊 검증 절차

### 1. SSM Parameter 확인
```bash
aws ssm get-parameter --name /sesacthon/dev/ghcr/username --query Parameter.Value --output text
# 출력: mangowhoiscloud

aws ssm get-parameter --name /sesacthon/dev/ghcr/token --with-decryption --query Parameter.Value --output text
# 출력: gho_xxxx...
```

### 2. ExternalSecret 상태
```bash
kubectl get externalsecret -n auth ghcr-pull-secret -o yaml | grep -A10 "status:"
# Conditions.Status: "SecretSynced" 확인
```

### 3. Secret 생성 및 형식
```bash
# Secret 존재 확인
kubectl get secret ghcr-secret -n auth

# Type 확인
kubectl get secret ghcr-secret -n auth -o jsonpath='{.type}'
# 출력: kubernetes.io/dockerconfigjson

# 내용 확인
kubectl get secret ghcr-secret -n auth -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d | jq
# 출력: {"auths":{"ghcr.io":{...}}}
```

### 4. Image Pull 성공
```bash
# Pod Events 확인
kubectl describe pod -n auth $(kubectl get pod -n auth -l app=auth-api -o name | head -1) | grep -A10 "Events:"
# "Successfully pulled image" 메시지 확인

# Pod 상태
kubectl get pods -n auth -l app=auth-api
# NAME                        READY   STATUS    RESTARTS   AGE
# auth-api-xxxxxxxxxx-xxxxx   1/1     Running   0          2m
```

---

## 🔄 롤백 절차

자동화 실패 시 임시로 수동 생성:

```bash
# 1. GitHub Token 확인
TOKEN=$(gh auth token)

# 2. 수동으로 Secret 생성
for ns in auth my scan character location info chat; do
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username=mangowhoiscloud \
    --docker-password=$TOKEN \
    --docker-email=ryoo0504@gmail.com \
    -n $ns
done

# 3. Pod 재시작
for ns in auth my scan character location info chat; do
  kubectl rollout restart deployment ${ns}-api -n $ns
done
```

---

## 📚 관련 문서

- [External Secrets Operator Guide](../deployment/platform/EXTERNAL_SECRETS_GUIDE.md)
- [GHCR Setup Guide](../deployment/GHCR_GUIDE.md)
- [Sync Wave Secret Matrix](../gitops/SYNC_WAVE_SECRET_MATRIX.md)
- [GitOps Deployment Troubleshooting](./gitops-deployment.md)

---

## 🔖 참고

### GHCR 이미지 리스트
```bash
# 브라우저에서 확인
https://github.com/orgs/SeSACTHON/packages

# CLI로 확인 (서버에서)
TOKEN=$(gh auth token)
for api in auth my scan character location info chat; do
  curl -H "Authorization: Bearer $TOKEN" \
    "https://ghcr.io/v2/sesacthon/${api}-api/tags/list"
done
```

### Token 권한 확인
```bash
# Token 스코프 확인
gh auth status

# 출력 예시:
# ✓ Logged in to github.com account mangowhoiscloud (keyring)
# - Token scopes: 'gist', 'read:org', 'repo', 'workflow', 'read:packages'
```

---

## 🏷️ 태그
`#troubleshooting` `#ghcr` `#imagepullbackoff` `#external-secrets` `#automation`


