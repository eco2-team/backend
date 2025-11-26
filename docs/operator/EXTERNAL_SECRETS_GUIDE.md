# External Secrets Operator 가이드

> **목적**: AWS SSM Parameter Store를 단일 진실 공급원(Single Source of Truth)으로 사용하여, Kubernetes Secret을 자동으로 동기화하고 관리한다.  
> **환경**: dev/prod 환경별로 별도의 SSM 경로(`/sesacthon/{env}/**`)를 사용하여 격리  
> **Wave**: 10 (Operator 설치) → 11 (ExternalSecret CR 배포)  
> **작성일**: 2025-11-19

---

## 1. 아키텍처 개요

```
┌─────────────────┐
│ AWS SSM         │
│ Parameter Store │
│ /sesacthon/dev/ │
│  ├─ ghcr/       │ ← GitHub Container Registry 자격증명
│  ├─ data/       │ ← PostgreSQL, Redis, RabbitMQ 비밀번호
│  ├─ platform/   │ ← Grafana, ArgoCD 관리자 비밀번호
│  ├─ network/    │ ← VPC ID, Subnet IDs, Security Group IDs
│  └─ ingress/    │ ← ACM Certificate ARN
└─────────────────┘
         │
         │ (IAM: ssm:GetParameter)
         ▼
┌─────────────────────────────────────┐
│ ClusterSecretStore                  │
│ (aws-ssm-store)                     │
│ auth: secretRef                     │
│   - aws-global-credentials          │
│     (kube-system)                   │
└─────────────────────────────────────┘
         │
         │ (ExternalSecret CRs)
         ▼
┌─────────────────────────────────────┐
│ Kubernetes Secrets                  │
│ - ghcr-secret (7 namespaces)        │
│ - postgresql-secret                 │
│ - redis-secret                      │
│ - rabbitmq-default-user             │
│ - grafana-admin                     │
│ - argocd-admin-secret               │
│ - alb-controller-values             │
│ - ingress-acm-arn (3 namespaces)    │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ Workloads (Pods, Helm Values)       │
│ - API Pods (imagePullSecrets)       │
│ - Data Operators (credentials)      │
│ - Platform Apps (admin passwords)   │
└─────────────────────────────────────┘
```

---

## 2. Secret 분류 및 생성 절차

### 2.2 데이터 계층 Secrets (Wave 11)

#### A. PostgreSQL

**대상 Namespace**: `postgres`

**SSM Parameters**:
- `/sesacthon/dev/data/postgres-password` (SecureString)

**생성 절차**:
```bash
aws ssm put-parameter \
  --name /sesacthon/dev/data/postgres-password \
  --value "$(openssl rand -base64 32)" \
  --type SecureString \
  --description "PostgreSQL admin password for dev"
```

**생성되는 Secret**:
- Name: `postgresql-secret`
- Keys: `username`, `password`, `postgres-password`
- Usage: Postgres Operator가 클러스터 생성 시 참조

#### B. Redis

**대상 Namespace**: `redis`

**SSM Parameters**:
- `/sesacthon/dev/data/redis-password` (SecureString)

**생성 절차**:
```bash
aws ssm put-parameter \
  --name /sesacthon/dev/data/redis-password \
  --value "$(openssl rand -base64 32)" \
  --type SecureString \
  --description "Redis password for dev"
```

**생성되는 Secret**:
- Name: `redis-secret`
- Keys: `password`, `redis-password`
- Usage: Redis Operator 인스턴스 생성 시 참조

### 2.3 플랫폼 관리자 Secrets (Wave 11)

#### A. Grafana Admin

**대상 Namespace**: `grafana`

**SSM Parameters**:
- `/sesacthon/dev/platform/grafana-admin-password` (SecureString)

**생성 절차**:
```bash
aws ssm put-parameter \
  --name /sesacthon/dev/platform/grafana-admin-password \
  --value "$(openssl rand -base64 16)" \
  --type SecureString \
  --description "Grafana admin password for dev"
```

**생성되는 Secret**:
- Name: `grafana-admin`
- Keys: `admin-user` (고정값: `admin`), `admin-password`
- Usage: Grafana Helm Chart가 초기 관리자 계정 생성 시 참조

#### B. ArgoCD Admin

**대상 Namespace**: `argocd`

**SSM Parameters**:
- `/sesacthon/dev/platform/argocd-admin-password` (SecureString)

**생성 절차**:
```bash
aws ssm put-parameter \
  --name /sesacthon/dev/platform/argocd-admin-password \
  --value "$(openssl rand -base64 16)" \
  --type SecureString \
  --description "ArgoCD admin password for dev"
```

**생성되는 Secret**:
- Name: `argocd-admin-secret`
- Keys: `admin-username` (고정값: `admin`), `admin-password`
- Usage: ArgoCD 초기 비밀번호 재설정 (선택적, 기본 secret 대체용)

**ExternalSecret 파일**: `workloads/secrets/external-secrets/dev/data-secrets.yaml`

---

### 2.4 네트워크 & 인프라 Secrets (Wave 11)

#### A. ALB Controller Configuration

**대상 Namespace**: `kube-system`

**SSM Parameters**:
- `/sesacthon/dev/network/vpc-id` (String)
- `/sesacthon/dev/network/public-subnets` (StringList)
- `/sesacthon/dev/network/alb-sg-id` (String)

**생성 절차** (Terraform 자동 생성):
```hcl
# terraform/ssm-parameters.tf
resource "aws_ssm_parameter" "vpc_id" {
  name  = "/sesacthon/${var.environment}/network/vpc-id"
  type  = "String"
  value = module.vpc.vpc_id
}
```

**생성되는 Secret**:
- Name: `alb-controller-values`
- Keys: `vpcId`, `publicSubnets`, `albSgId`
- Usage: AWS Load Balancer Controller Helm values로 주입

#### B. Ingress ACM Certificate

**대상 Namespace**: `default`, `argocd`, `grafana`

**SSM Parameters**:
- `/sesacthon/dev/ingress/acm-certificate-arn` (String)

**생성 절차** (Terraform 자동 생성):
```hcl
resource "aws_ssm_parameter" "acm_cert_arn" {
  name  = "/sesacthon/${var.environment}/ingress/acm-certificate-arn"
  type  = "String"
  value = aws_acm_certificate.wildcard.arn
}
```

**생성되는 Secret**:
- Name: `ingress-acm-arn`
- Keys: `certificate-arn`
- Usage: Ingress annotation에서 참조 (선택적, 현재는 annotation에 직접 명시)

**ExternalSecret 파일**: 
- `workloads/secrets/external-secrets/dev/alb-controller-secret.yaml`
- `workloads/secrets/external-secrets/dev/ingress-acm-secret.yaml`

---

## 3. ClusterSecretStore 설정

### 3.1 인증 방식

**현재 방식**: Secret 기반 인증 (Access Key/Secret Key)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-ssm-store
spec:
  provider:
    aws:
      service: ParameterStore
      region: ap-northeast-2
      auth:
        secretRef:
          accessKeyIDSecretRef:
            name: aws-global-credentials
            namespace: kube-system
            key: aws_access_key_id
          secretAccessKeySecretRef:
            name: aws-global-credentials
            namespace: kube-system
            key: aws_secret_access_key
```

**필요 IAM 권한**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": "arn:aws:ssm:ap-northeast-2:*:parameter/sesacthon/*"
    }
  ]
}
```

### 3.2 향후 개선 (IRSA 방식)

IRSA(IAM Roles for Service Accounts) 적용 시:

```yaml
spec:
  provider:
    aws:
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
            namespace: platform-system
```

---

## 4. 트러블슈팅

### 4.1 ClusterSecretStore가 Ready 상태가 아님

**증상**:
```bash
kubectl get clustersecretstore aws-ssm-store
# STATUS: InvalidProviderConfig, READY: False
```

**원인**:
1. `aws-global-credentials` Secret이 없음
2. Secret의 key 이름이 다름 (`aws_access_key_id` vs `AWS_ACCESS_KEY_ID`)
3. IAM 권한 부족

**해결**:
```bash
# Secret 확인
kubectl get secret aws-global-credentials -n kube-system -o yaml

# Secret 재생성 (Ansible으로 자동 생성되어 있어야 함)
kubectl create secret generic aws-global-credentials \
  --from-literal=aws_access_key_id=AKIA... \
  --from-literal=aws_secret_access_key=xxx... \
  -n kube-system
```

### 4.2 ExternalSecret이 Synced인데 Secret이 생성 안 됨

**증상**:
```bash
kubectl get externalsecret grafana-admin -n grafana
# STATUS: SecretSynced

kubectl get secret grafana-admin -n grafana
# Error: not found
```

**원인**: SSM Parameter가 존재하지 않음

**해결**:
```bash
# ExternalSecret 상세 확인
kubectl describe externalsecret grafana-admin -n grafana
# Events에서 "ParameterNotFound" 확인

# SSM Parameter 생성
aws ssm put-parameter \
  --name /sesacthon/dev/platform/grafana-admin-password \
  --value "your-password" \
  --type SecureString
```

## 5. 운영 가이드

### 5.1 Secret 추가

1. **SSM Parameter 생성**:
```bash
aws ssm put-parameter \
  --name /sesacthon/dev/category/key-name \
  --value "secret-value" \
  --type SecureString
```

2. **ExternalSecret 정의 추가**:
```yaml
# workloads/secrets/external-secrets/dev/new-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: my-new-secret
  namespace: target-namespace
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: aws-ssm-store
  data:
    - secretKey: myKey
      remoteRef:
        key: /sesacthon/dev/category/key-name
  target:
    name: my-k8s-secret
    creationPolicy: Owner
```

3. **kustomization.yaml에 추가**:
```yaml
# workloads/secrets/external-secrets/dev/kustomization.yaml
resources:
  - new-secret.yaml
```

4. **Git commit & push** → ArgoCD 자동 동기화

### 5.2 Secret 회전

```bash
# 1. SSM Parameter 업데이트
aws ssm put-parameter \
  --name /sesacthon/dev/data/redis-password \
  --value "$(openssl rand -base64 32)" \
  --type SecureString \
  --overwrite

# 2. ExternalSecret 강제 동기화 (옵션)
kubectl annotate externalsecret redis-credentials \
  -n redis \
  force-sync="$(date +%s)" \
  --overwrite

# 3. 1시간 이내 자동 동기화 (refreshInterval: 1h)
```

### 5.3 모니터링

```bash
# 모든 ExternalSecret 상태 확인
kubectl get externalsecret -A

# ClusterSecretStore 상태
kubectl describe clustersecretstore aws-ssm-store

# External Secrets Operator 로그
kubectl logs -n platform-system -l app.kubernetes.io/name=external-secrets --tail=50
```

---

## 6. 참고 자료

- [External Secrets Operator 공식 문서](https://external-secrets.io/)
- [AWS SSM Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
- 관련 내부 문서:
  - `TERRAFORM_SECRET_INJECTION.md`: Terraform → SSM 자동화
  - `GHCR_IMAGEPULLBACKOFF_FIX.md`: GHCR Secret 트러블슈팅
  - `SYNC_WAVE_SECRET_MATRIX.md`: Wave별 Secret 의존성

---

## 7. Secret 목록 요약

| Secret 이름 | Namespace | SSM Parameter | 용도 | Type |
|------------|-----------|---------------|------|------|
| `postgresql-secret` | postgres | `/sesacthon/dev/data/postgres-password` | PostgreSQL 관리자 비밀번호 | `Opaque` |
| `redis-secret` | redis | `/sesacthon/dev/data/redis-password` | Redis 비밀번호 | `Opaque` |
| `grafana-admin` | grafana | `/sesacthon/dev/platform/grafana-admin-password` | Grafana 관리자 | `Opaque` |
| `argocd-admin-secret` | argocd | `/sesacthon/dev/platform/argocd-admin-password` | ArgoCD 관리자 (선택적) | `Opaque` |
| `alb-controller-values` | kube-system | `/sesacthon/dev/network/*` | ALB Controller 설정 | `Opaque` |
| `ingress-acm-arn` | default, argocd, grafana | `/sesacthon/dev/ingress/acm-certificate-arn` | ACM 인증서 ARN | `Opaque` |

