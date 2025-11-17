# GitOps 배포 문제 해결 가이드

> **작성일**: 2025-11-16  
> **버전**: v0.7.3-v0.7.4  
> **아키텍처**: 14-Node GitOps Production  

## 📋 목차

- [1. Kustomize 상위 디렉토리 참조 오류](#1-kustomize-상위-디렉토리-참조-오류)
- [2. ApplicationSet kustomize.images 문법 오류](#2-applicationset-kustomizeimages-문법-오류)
- [3. CI Workflow YAML 파싱 오류](#3-ci-workflow-yaml-파싱-오류)
- [4. GHCR ImagePullBackOff](#4-ghcr-imagepullbackoff)
- [5. RabbitMQ Bitnami Debian 이미지 중단](#5-rabbitmq-bitnami-debian-이미지-중단)
- [6. Ansible import_tasks 문법 충돌](#6-ansible-import_tasks-문법-충돌)
- [7. VPC 삭제 실패 (ALB/Target Groups 남음)](#7-vpc-삭제-실패-albtarget-groups-남음)
- [8. scan-api CrashLoopBackOff](#8-scan-api-crashloopbackoff)
- [9. ArgoCD Application 자동 Sync 안됨](#9-argocd-application-자동-sync-안됨)
- [10. ALB Controller VPC ID 하드코딩](#10-alb-controller-vpc-id-하드코딩)
- [11. ALB Controller egress 차단](#11-alb-controller-egress-차단)
- [12. macOS TLS 인증서 경로 누락](#12-macos-tls-인증서-경로-누락)

---

## 1. Kustomize 상위 디렉토리 참조 오류

### 문제
```
Error: file '../namespaces/domain-based.yaml' is not in or below 'k8s/namespaces'
```

**원인**: Kustomize는 보안상 상위 디렉토리 참조 불가

### 해결
```bash
# 모든 Namespace 리소스는 k8s/namespaces 디렉터리 안에 존재해야 함
```

**커밋**: `c17defd`

---

## 2. ApplicationSet kustomize.images 문법 오류

### 문제
```
ApplicationSet.argoproj.io "api-services" is invalid: 
spec.template.spec.source.kustomize.images[0]: Invalid value: "object"
```

**원인**: ApplicationSet에서 kustomize.images는 객체 형태 사용 불가

### 해결
```yaml
# BEFORE (오류)
source:
  path: k8s/overlays/{{domain}}
  kustomize:
    images:
      - name: ghcr.io/sesacthon/{{domain}}-api
        newTag: latest

# AFTER (수정)
source:
  path: k8s/overlays/{{domain}}
  # kustomize.images 제거 - overlay의 patch-deployment.yaml에서 이미 latest 지정
```

**커밋**: `7f79d30`

---

## 3. CI Workflow YAML 파싱 오류

### 문제
```
YAML parsing failed: could not find expected ':'
in ".github/workflows/ci-quality-gate.yml", line 186
```

**원인**: Python heredoc의 들여쓰기 문제

### 해결
```yaml
# .github/workflows/ci-quality-gate.yml
# BEFORE (오류)
python <<'PY'
import json  # 들여쓰기 없음
...
PY

# AFTER (수정)
python3 <<'PYEOF'
  import json  # YAML 문법에 맞게 들여쓰기
  ...
PYEOF
```

**커밋**: `84b1c1d`

---

## 4. GHCR ImagePullBackOff

### 문제
```
Failed to pull image "ghcr.io/sesacthon/auth-api:dev-latest": 403 Forbidden
```

**원인**: Secret의 GitHub token에 `read:packages` 권한 없음

### 해결
```bash
# 1. read:packages 권한이 있는 토큰 생성
# GitHub Settings → Developer settings → Personal access tokens

# 2. 모든 namespace에 Secret 재생성
for ns in auth character chat info location my scan workers; do
  kubectl delete secret ghcr-secret -n $ns
  kubectl create secret docker-registry ghcr-secret \
    --docker-server=ghcr.io \
    --docker-username=<USERNAME> \
    --docker-password=<TOKEN_WITH_READ_PACKAGES> \
    --namespace=$ns
done

# 3. Pods 재생성
kubectl delete pod --all -n auth
```

**필수 권한**: `read:packages`, `write:packages` (빌드 시)

**커밋**: `0f6663e` (imagePullSecrets 추가)

---

## 5. RabbitMQ Bitnami Debian 이미지 중단

### 문제
```
bitnami/rabbitmq:4.1.3-debian-12-r1: not found
bitnami/rabbitmq:3.13.7-debian-12-r0: not found
```

**원인**: Bitnami의 Debian 기반 RabbitMQ 이미지가 2025-08-28부터 중단됨

### 해결 방법

**Option A: Docker Official Image** (임시):
```yaml
# platform/helm/data/databases/values.yaml
rabbitmq:
  image:
    registry: docker.io
    repository: rabbitmq
    tag: "3.13-management"
```

**주의**: Bitnami Chart의 init scripts가 Docker Official Image와 호환되지 않을 수 있음

**Option B: RabbitMQ Cluster Operator** (권장):
```yaml
# RabbitMQ Operator 사용
# platform/helm/rabbitmq-operator/app.yaml
```

**커밋**: `dd51c46`

**참고**: https://www.rabbitmq.com/kubernetes/operator/operator-overview.html

---

## 6. Ansible import_tasks 문법 충돌

### 문제
```
ERROR: conflicting action statements: hosts, tasks
Origin: ansible/playbooks/07-alb-controller.yml:4:3
```

**원인**: `import_tasks`로 호출되는 playbook에 `hosts` 정의 불가

### 해결
```yaml
# BEFORE (오류)
---
- name: Task name
  hosts: masters  # ← import_tasks로 호출 시 불가
  tasks:
    - ...

# AFTER (수정)
---
- name: Task name
  # hosts 제거, tasks만 정의
  set_fact:
    ...
```

**커밋**: `7f79d30`

---

## 7. VPC 삭제 실패 (ALB/Target Groups 남음)

### 문제
```
terraform destroy 실패
Error: VPC has dependencies and cannot be deleted
```

**원인**: Kubernetes ALB Controller가 생성한 ALB, Target Groups가 남아있음

### 해결
```bash
# VPC cleanup 스크립트 사용
bash scripts/cleanup-vpc-resources.sh

# 또는 수동 정리
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=tag:Project,Values=SeSACTHON" --query 'Vpcs[0].VpcId' --output text)

# Target Groups 삭제
aws elbv2 describe-target-groups --query "TargetGroups[?VpcId=='$VPC_ID'].TargetGroupArn" --output text | \
  xargs -I {} aws elbv2 delete-target-group --target-group-arn {}

# Load Balancers 삭제
aws elbv2 describe-load-balancers --query "LoadBalancers[?VpcId=='$VPC_ID'].LoadBalancerArn" --output text | \
  xargs -I {} aws elbv2 delete-load-balancer --load-balancer-arn {}

# 30초 대기 후 terraform destroy
sleep 30
terraform destroy -auto-approve
```

**스크립트**: `scripts/cleanup-vpc-resources.sh`

---

## 8. scan-api CrashLoopBackOff

### 문제
```
ERROR: Error loading ASGI app. Could not import module "main".
```

**원인**: Dockerfile의 uvicorn 경로가 잘못됨

### 해결
```dockerfile
# services/scan/Dockerfile
# BEFORE
CMD ["uvicorn", "main:app", ...]

# AFTER  
CMD ["uvicorn", "app.main:app", ...]
```

**커밋**: `eb154a7`

---

## 9. ArgoCD Application 자동 Sync 안됨

### 문제

Applications가 OutOfSync 상태로 남아있음

### 원인
```yaml
syncPolicy:
  automated:
    prune: true
    selfHeal: true  # 설정되어 있지만 초기 delay 있음
```

### 해결
```bash
# 수동 sync 트리거
kubectl patch application <app-name> -n argocd --type merge \
  -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{"revision":"refactor/gitops-sync-wave"}}}'

# 또는 Application 재생성 (root-app이 자동 재생성)
kubectl delete application <app-name> -n argocd
```

**자동 sync**: 시간이 지나면 자동으로 sync됨 (retryPolicy: 5회)

---

## 10. ALB Controller VPC ID 하드코딩

### 문제
```
ALB Controller CrashLoopBackOff
Error: unable to create controller
```

**원인**: ArgoCD Application에 이전 VPC ID 하드코딩됨

### 해결
```yaml
# platform/helm/alb-controller/values/dev.yaml
controller:
  extraEnv:
    - name: AWS_VPC_ID
      valueFrom:
        secretKeyRef:
          name: alb-controller-values
          key: vpcId  # External Secrets로 동적 주입
```

**개선안**: SSM Parameter → External Secret → ConfigMap/Secret

**커밋**: `0645847`

---

## 11. ALB Controller egress 차단

### 문제
```
aws-load-balancer-controller-7cbcb46f48-xxxxx  CrashLoopBackOff
unable to create controller: Post "https://10.96.0.1:443/...": dial tcp 10.96.0.1:443: i/o timeout
```

### 원인

GitOps v0.7.3의 NetworkPolicy가 kube-system egress를 과도하게 제한:
- Kubernetes API (10.96.0.1:443) 차단
- DNS (UDP 53) 차단
- AWS API (IRSA STS) 차단

### 해결

**1. 문제 Policy 제거**:
```bash
kubectl delete networkpolicy domain-isolation -n kube-system
```

**2. 올바른 egress 정책 작성**:
```yaml
# workloads/network-policies/base/allow-dns.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

**커밋**: `5c4f5cc`, `77d694c`

---

## 12. macOS TLS 인증서 경로 누락

### 문제

```
error setting certificate verify locations:  CAfile: /etc/ssl/cert.pem CApath: none
Error: looks like "https://aws.github.io/eks-charts" is not a valid chart repository or cannot be reached
```

**원인**: 로컬 macOS 개발 환경에는 `/etc/ssl/cert.pem`이 존재하지 않아 `git`, `helm`, `kustomize` 등이 시스템 CA 번들을 찾지 못함.

### 해결

1. `certifi`가 제공하는 최신 CA 번들을 기준으로 TLS 변수를 고정하는 스크립트를 추가했습니다.  
2. 아래 명령을 실행하면 필요한 변수들이 자동으로 export 됩니다.

```bash
source scripts/utilities/export-ca-env.sh
```

3. 스크립트는 다음 환경 변수를 설정합니다.

```bash
export SSL_CERT_FILE=/Users/<user>/Library/Python/.../certifi/cacert.pem
export REQUESTS_CA_BUNDLE=$SSL_CERT_FILE
export GIT_SSL_CAINFO=$SSL_CERT_FILE
```

4. 이후 `helm template`, `git clone`, `kustomize build` 등에서 `--insecure-skip-tls-verify`나 `GIT_SSL_NO_VERIFY=1`이 필요하지 않습니다.

**참고 파일**: `scripts/utilities/export-ca-env.sh`

---

**최종 업데이트**: 2025-11-16  
**다음 문서**: [ansible-label-sync.md](./ansible-label-sync.md)

