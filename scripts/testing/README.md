# 검증 스크립트 사용 가이드

## 📋 개요

Kubernetes 클러스터와 GitOps 파이프라인이 의도대로 구축되었는지 자동으로 검증하는 스크립트입니다.

---

## 🎯 Phase 1&2 검증 대상

### Infrastructure (8 nodes)
- **Control Plane**: 1 (Master - t3.large)
- **API Services**: 5 (auth, my, scan, character, location)
- **Infrastructure**: 2 (PostgreSQL, Redis)

### GitOps Pipeline
- **GitHub Repository**: 소스 코드 및 설정
- **GitHub Actions**: 이미지 빌드 및 GHCR 푸시
- **ArgoCD**: 자동 배포 및 동기화
- **Helm**: 패키지 관리

---

## 🚀 사용 방법

### 1. 클러스터 검증

```bash
cd /Users/mango/workspace/SeSACTHON/backend
./scripts/testing/verify-cluster.sh
```

**검증 항목**:
- ✅ AWS 인프라 (EC2, VPC, Security Groups, SSM)
- ✅ Kubernetes 클러스터 (노드, Pod, CNI, CoreDNS)
- ✅ 노드 레이블 (Master, API, Infrastructure)
- ✅ 네트워크 및 DNS (Pod CIDR, Service CIDR, DNS 해석)
- ✅ ArgoCD 설치 및 Application

### 2. GitOps 파이프라인 검증

```bash
cd /Users/mango/workspace/SeSACTHON/backend
./scripts/testing/verify-gitops.sh
```

**검증 항목**:
- ✅ GitHub Repository 연결
- ✅ GitHub Actions Workflow
- ✅ Helm Chart 구성
- ✅ ArgoCD Application 배포 상태
- ✅ API Deployments 및 Services
- ✅ Ingress 설정

### 3. 통합 검증 (권장)

```bash
cd /Users/mango/workspace/SeSACTHON/backend

# 클러스터 검증
./scripts/testing/verify-cluster.sh

# GitOps 검증
./scripts/testing/verify-gitops.sh
```

---

## 📊 출력 예시

### ✅ 성공 예시

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔍 Kubernetes 클러스터 검증 시작
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ AWS 인프라 검증 (Terraform)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ PASS: Terraform state 존재
✅ PASS: EC2 인스턴스 개수: 8/8
✅ PASS: SSM Agent 등록: 8/8
✅ PASS: VPC 생성: vpc-xxxxx
✅ PASS: Security Groups 생성

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2️⃣ Kubernetes 클러스터 검증
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ PASS: Kubernetes 노드 개수: 8/8
✅ PASS: 모든 노드 Ready: 8/8
✅ PASS: Master 노드 레이블: 1개
✅ PASS: API 노드 레이블: 5개
✅ PASS: Infrastructure 노드 레이블: 2개
✅ PASS: Calico CNI 실행 중: 8/8 pods
✅ PASS: CoreDNS 실행 중: 2 pods

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 검증 결과 요약
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

총 검사 항목: 25
통과: 25
실패: 0

성공률: 100%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 모든 검증 통과!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### ⚠️ 경고 예시

```
⚠️  WARN: SSM Agent 일부 미등록: 6/8
⚠️  WARN: Application Sync 상태: OutOfSync (예상: Synced)
```

### ❌ 실패 예시

```
❌ FAIL: EC2 인스턴스 개수 불일치: 5/8 (예상)
❌ FAIL: 일부 노드 Not Ready: 6/8
```

---

## 📝 로그 파일

모든 검증 결과는 타임스탬프와 함께 로그 파일에 저장됩니다.

```bash
# 로그 위치
logs/cluster-verification-20251107-180000.log

# 최근 로그 확인
ls -lt logs/cluster-verification-*.log | head -1

# 로그 내용 확인
cat logs/cluster-verification-*.log
```

---

## 🔧 문제 해결

### Master IP를 찾을 수 없음

**증상**:
```
❌ Master IP를 찾을 수 없습니다.
```

**해결**:
```bash
cd terraform
terraform output master_public_ip
```

### SSH 연결 실패

**증상**:
```
❌ FAIL: Kubernetes 노드 개수 확인 불가
```

**해결**:
```bash
# SSH 키 확인
ls -la ~/.ssh/k8s-temp*

# 키 푸시 (EC2 Instance Connect)
./scripts/cluster/push-ssh-keys.sh

# 또는 SSM 사용
aws ssm start-session --target i-xxxxxxxxx --region ap-northeast-2
```

### ArgoCD 미설치

**증상**:
```
❌ FAIL: ArgoCD Namespace 없음
```

**해결**:
```bash
# Ansible playbook 재실행
cd ansible
ansible-playbook -i ../terraform/hosts site.yml
```

### Application Sync 실패

**증상**:
```
⚠️  WARN: Application Sync 상태: OutOfSync
```

**해결**:
```bash
# ArgoCD에서 수동 Sync
kubectl patch application ecoeco-backend-phase12 -n argocd \
  --type merge -p '{"operation":{"sync":{"revision":"HEAD"}}}'

# 또는 ArgoCD UI에서 Sync 버튼 클릭
https://argocd.growbin.app
```

---

## 🎯 검증 기준

### Phase 1&2 최소 요구사항

| 항목 | 최소 기준 | 설명 |
|------|----------|------|
| **EC2 인스턴스** | 8개 | Master(1) + API(5) + Infra(2) |
| **SSM 등록** | 8개 | 모든 노드 Online 상태 |
| **Ready 노드** | 8개 | 모든 노드 Ready |
| **Calico Pods** | 8개 | 모든 노드에 CNI Pod 실행 |
| **CoreDNS** | 2개 이상 | DNS 서비스 가용 |
| **ArgoCD Pods** | 5개 이상 | ArgoCD 구성 요소 실행 |
| **API Deployments** | 0-5개 | 배포 진행 중 (선택) |

### 성공률 기준

- **100%**: 모든 검증 통과 ✅
- **80-99%**: 일부 항목 미구성 ⚠️  (정상)
- **< 80%**: 심각한 문제 ❌

---

## 📚 추가 검증 도구

### kubectl 직접 사용

```bash
# Master 노드 SSH 접속
MASTER_IP=$(cd terraform && terraform output -raw master_public_ip)
ssh ubuntu@$MASTER_IP

# 노드 상태 확인
kubectl get nodes -o wide

# 모든 Pod 확인
kubectl get pods -A

# ArgoCD Application 확인
kubectl get applications -n argocd

# Helm Release 확인
helm list -A
```

### AWS CLI 사용

```bash
# 실행 중인 인스턴스 확인
aws ec2 describe-instances \
  --region ap-northeast-2 \
  --filters "Name=tag:Name,Values=k8s-*" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].[Tags[?Key==`Name`].Value|[0],State.Name,PublicIpAddress]' \
  --output table

# SSM Agent 상태 확인
aws ssm describe-instance-information \
  --region ap-northeast-2 \
  --filters "Key=tag:Name,Values=k8s-*" \
  --query 'InstanceInformationList[*].[InstanceId,PingStatus,ComputerName]' \
  --output table
```

---

## 🔄 CI/CD 통합

### GitHub Actions에서 자동 검증

`.github/workflows/verify-cluster.yml` 추가:

```yaml
name: Verify Cluster

on:
  workflow_dispatch:
  schedule:
    - cron: '0 */6 * * *'  # 6시간마다

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Configure AWS Credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ap-northeast-2
      
      - name: Run Cluster Verification
        run: ./scripts/testing/verify-cluster.sh
      
      - name: Run GitOps Verification
        run: ./scripts/testing/verify-gitops.sh
```

---

## 💡 권장 사항

### 배포 후 검증 프로세스

1. **Terraform Apply 완료 후**
   ```bash
   ./scripts/testing/verify-cluster.sh
   ```

2. **Ansible Playbook 완료 후**
   ```bash
   # 5분 대기 (Pod 초기화)
   sleep 300
   ./scripts/testing/verify-cluster.sh
   ```

3. **ArgoCD Application 생성 후**
   ```bash
   ./scripts/testing/verify-gitops.sh
   ```

4. **최종 통합 검증**
   ```bash
   ./scripts/testing/verify-cluster.sh && \
   ./scripts/testing/verify-gitops.sh
   ```

---

## 📞 문의

검증 스크립트 관련 문의나 개선 사항은 이슈로 남겨주세요.

**관련 문서**:
- [인프라 검증 가이드](../docs/infrastructure/INFRASTRUCTURE_VALIDATION.md)
- [배포 가이드](../docs/deployment/AUTO_REBUILD_GUIDE.md)
- [ArgoCD 가이드](../docs/deployment/ARGOCD_SETUP.md)




