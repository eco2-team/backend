# GitHub Actions 자동화 설정 가이드

## 🎯 개요

이 문서는 GitHub Actions를 통한 완전 자동화 인프라 배포 설정 가이드입니다.

```yaml
Git Push → Terraform → Ansible → ArgoCD → 완료
  (자동)    (자동)      (자동)     (자동)   (0분 개입)
```

---

## ✅ 1단계: GitHub Secrets 설정

### 필수 Secrets

GitHub Repository → Settings → Secrets and variables → Actions → New repository secret

#### AWS Credentials

```yaml
Name: AWS_ACCESS_KEY_ID
Value: AKIA...

Name: AWS_SECRET_ACCESS_KEY
Value: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**생성 방법**:
```bash
# AWS IAM에서 새 사용자 생성 (또는 기존 사용자 사용)
aws iam create-access-key --user-name github-actions

# 출력된 AccessKeyId와 SecretAccessKey 복사
```

**필요한 IAM 권한**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:*",
        "vpc:*",
        "s3:*",
        "iam:*",
        "acm:*",
        "cloudfront:*",
        "route53:*"
      ],
      "Resource": "*"
    }
  ]
}
```

#### SSH Private Key

```yaml
Name: SSH_PRIVATE_KEY
Value: |
  -----BEGIN RSA PRIVATE KEY-----
  MIIEpAIBAAKCAQEA...
  -----END RSA PRIVATE KEY-----
```

**생성 방법**:
```bash
# 기존 키 사용 (terraform/terraform.tfvars에 설정된 키)
cat ~/.ssh/k8s-cluster-key.pem

# 또는 새로 생성
ssh-keygen -t rsa -b 4096 -f ~/.ssh/k8s-cluster-key.pem -N ""
```

---

## ✅ 2단계: Terraform Backend 설정 (선택사항)

S3 Backend를 사용하면 상태 관리가 안전합니다.

### S3 Bucket 생성

```bash
# S3 버킷 생성
aws s3 mb s3://sesacthon-terraform-state --region ap-northeast-2

# 버전 관리 활성화
aws s3api put-bucket-versioning \
  --bucket sesacthon-terraform-state \
  --versioning-configuration Status=Enabled

# 암호화 활성화
aws s3api put-bucket-encryption \
  --bucket sesacthon-terraform-state \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

### terraform/backend.tf 수정

```hcl
terraform {
  backend "s3" {
    bucket         = "sesacthon-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "ap-northeast-2"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"  # 선택사항
  }
}
```

---

## ✅ 3단계: Workflow 트리거 방법

### 방법 1: Pull Request (권장 - 안전)

```bash
# 1. Feature 브랜치 생성
git checkout -b feature/add-monitoring-node

# 2. Terraform 파일 수정
vim terraform/main.tf

# 3. Commit & Push
git add terraform/
git commit -m "Add monitoring node"
git push origin feature/add-monitoring-node

# 4. GitHub에서 PR 생성
# → GitHub Actions가 자동으로 terraform plan 실행
# → PR에 Plan 결과 코멘트 자동 생성

# 5. PR 승인 후 Merge
# → GitHub Actions가 자동으로:
#    - terraform apply
#    - ansible-playbook site.yml
#    - argocd app sync
```

### 방법 2: Direct Push (빠르지만 위험)

```bash
# Main/Develop 브랜치에 직접 Push
git checkout main
git add terraform/
git commit -m "Update infrastructure"
git push origin main

# → 즉시 terraform apply 실행 (주의!)
```

### 방법 3: Manual Trigger (수동 실행)

```bash
# GitHub Repository → Actions 탭
# → "Infrastructure as Code - Phase 1" 선택
# → "Run workflow" 버튼 클릭
# → Action 선택 (plan/apply/destroy)
# → "Run workflow" 실행
```

---

## ✅ 4단계: Workflow 실행 확인

### GitHub Actions UI에서 확인

```yaml
1. GitHub Repository → Actions 탭
2. 최근 Workflow 실행 클릭
3. 각 Job 상태 확인:
   - ✅ Terraform Plan
   - ✅ Terraform Apply
   - ✅ Ansible Bootstrap
   - ✅ ArgoCD Sync
   - ✅ Deployment Summary
```

### 로그 확인

```yaml
각 Job 클릭 → Step별 로그 확인

주요 확인 포인트:
  - Terraform Plan: 변경 사항 확인
  - Terraform Apply: 생성된 리소스 확인
  - Ansible Bootstrap: SSH 연결 및 Playbook 실행
  - ArgoCD Sync: Application 상태
```

---

## ✅ 5단계: 배포 결과 확인

### SSH 접속 확인

```bash
# Terraform Outputs에서 IP 확인
# (GitHub Actions Summary에 표시됨)

# Master 노드 접속
ssh -i ~/.ssh/k8s-cluster-key.pem ubuntu@<MASTER_IP>

# 노드 상태 확인
kubectl get nodes

# Pod 상태 확인
kubectl get pods --all-namespaces
```

### ArgoCD 확인

```bash
# ArgoCD 접속
# URL: https://argocd.sesacthon.com (또는 Master IP:30080)

# 초기 비밀번호
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d

# Application 상태 확인
argocd app list
argocd app get sesacthon-infrastructure
```

---

## 🔧 문제 해결

### 1. Terraform Apply 실패

```yaml
증상: Job "terraform-apply" 실패

원인:
  - AWS Credentials 잘못됨
  - IAM 권한 부족
  - Terraform State 충돌

해결:
  1. GitHub Secrets 확인 (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
  2. IAM 권한 확인
  3. S3 Backend 상태 확인 (lock 제거)
```

### 2. Ansible Bootstrap 실패

```yaml
증상: SSH 연결 실패 또는 Playbook 오류

원인:
  - SSH Key 잘못됨
  - EC2 인스턴스 아직 준비 안됨
  - Security Group 규칙 문제

해결:
  1. GitHub Secret SSH_PRIVATE_KEY 확인
  2. EC2 인스턴스 상태 확인 (AWS Console)
  3. Security Group에서 22번 포트 열림 확인
  4. Workflow 재실행 (EC2 부팅 대기)
```

### 3. ArgoCD Sync 실패

```yaml
증상: ArgoCD Login 실패 또는 Application Sync 실패

원인:
  - ArgoCD 아직 설치 안됨
  - Kubeconfig 가져오기 실패
  - Application 정의 오류

해결:
  1. Master 노드에서 ArgoCD 설치 확인
     kubectl get pods -n argocd
  
  2. Kubeconfig 확인
     ssh ubuntu@<MASTER_IP> kubectl get nodes
  
  3. Application YAML 검증
     kubectl apply -f argocd/application-14nodes.yaml --dry-run=client
```

### 4. Workflow 재실행

```yaml
실패한 Job만 재실행:
  1. GitHub Actions → 실패한 Workflow 클릭
  2. "Re-run failed jobs" 버튼 클릭

전체 Workflow 재실행:
  1. "Re-run all jobs" 버튼 클릭
```

---

## 📊 예상 실행 시간

```yaml
전체 Workflow 소요 시간 (14-Node 기준):

1. Terraform Plan:     2-3분
2. Terraform Apply:    8-12분  (EC2 인스턴스 생성)
3. Ansible Bootstrap:  15-20분 (Kubernetes 클러스터 구성)
4. ArgoCD Sync:        3-5분   (Application 배포)

총 소요 시간: 약 30-40분

최초 1회 실행:
  - Terraform Init: +2분
  - Docker Image Pull: +5분
  - 총 40-50분
```

---

## 🎯 다음 단계

### Phase 2: Atlantis 도입 (2주 후)

```yaml
목표: PR 기반 Terraform 관리 강화

장점:
  - PR에 Plan 결과 자동 코멘트
  - PR 승인 후에만 Apply 가능
  - Terraform Lock 자동 관리

작업:
  1. Atlantis 설치 (K8s 또는 별도 서버)
  2. atlantis.yaml 설정
  3. GitHub Webhook 연결
```

### Phase 3: ArgoCD Hooks (4주 후)

```yaml
목표: Ansible을 ArgoCD Hook으로 이동

장점:
  - GitHub Actions에서 Ansible 제거
  - ArgoCD가 전체 배포 관리
  - 간극 완전 제거

작업:
  1. ArgoCD PreSync Hook (Ansible Bootstrap)
  2. ArgoCD PostSync Hook (Node Labeling)
  3. Terraform Outputs → ConfigMap
```

---

## 📝 체크리스트

### 배포 전

- [ ] GitHub Secrets 설정 완료
  - [ ] AWS_ACCESS_KEY_ID
  - [ ] AWS_SECRET_ACCESS_KEY
  - [ ] SSH_PRIVATE_KEY

- [ ] Terraform Backend 설정 (선택)
  - [ ] S3 Bucket 생성
  - [ ] backend.tf 수정

- [ ] Branch Protection 설정
  - [ ] Main 브랜치 보호
  - [ ] PR 필수
  - [ ] Status Check 필수 (terraform-plan)

### 배포 후

- [ ] Workflow 실행 확인
  - [ ] Terraform Apply 성공
  - [ ] Ansible Bootstrap 성공
  - [ ] ArgoCD Sync 성공

- [ ] 클러스터 상태 확인
  - [ ] 14개 노드 Ready
  - [ ] 모든 Pod Running
  - [ ] ArgoCD Application Healthy

- [ ] 모니터링 확인
  - [ ] Prometheus 동작
  - [ ] Grafana 접속 가능
  - [ ] 메트릭 수집 확인

---

**작성일**: 2025-11-08  
**버전**: Phase 1 - GitHub Actions 자동화  
**다음 단계**: Atlantis 도입 (Phase 2)

