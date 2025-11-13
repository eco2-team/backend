# SSH 키 관리 통합 가이드

**버전**: v1.0.0  
**마지막 업데이트**: 2025-11-14

## 📋 개요

EcoEco K8s 클러스터의 모든 SSH 접근은 **단일 키 페어**를 사용합니다.

```
┌─────────────────────────────────────────────────────────────┐
│  🔑 단일 SSH 키 페어: sesacthon                             │
│                                                               │
│  - 프라이빗 키: ~/.ssh/sesacthon.pem                          │
│  - 공개 키:     ~/.ssh/sesacthon.pub                          │
│  - 크기:        3389 bytes (RSA 4096)                        │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   [Terraform]           [Ansible]          [GitHub Actions]
   AWS KeyPair         ansible.cfg          Secret 저장
   자동 생성/교체      private_key_file      SSH_PRIVATE_KEY
```

---

## 🔧 구성 요소

### 1️⃣ Terraform (인프라 생성)

**파일**: `terraform/variables.tf`

```hcl
variable "public_key_path" {
  description = "SSH 공개 키 경로"
  type        = string
  default     = "~/.ssh/sesacthon.pub"
}
```

**파일**: `terraform/main.tf`

```hcl
resource "aws_key_pair" "k8s" {
  key_name   = "sesacthon"
  public_key = file(var.public_key_path)

  tags = {
    Name = "k8s-cluster-key"
  }
}
```

**동작**:
- 로컬 `sesacthon.pub`을 AWS에 업로드
- 이미 존재하면 변경사항 확인 (교체 필요 시 자동 교체)
- 모든 EC2 인스턴스에 자동 적용

---

### 2️⃣ Ansible (구성 관리)

**파일**: `ansible/ansible.cfg`

```ini
[defaults]
remote_user = ubuntu
private_key_file = ~/.ssh/sesacthon.pem
host_key_checking = False

[ssh_connection]
ssh_args = -o ControlMaster=auto -o ControlPersist=600s -o IdentitiesOnly=yes -o StrictHostKeyChecking=no
pipelining = True
```

**핵심 설정**:
- `private_key_file`: 프라이빗 키 경로 명시
- `IdentitiesOnly=yes`: 다른 키 시도 방지 (중요!)
- `StrictHostKeyChecking=no`: 자동 호스트 키 승인

**동작**:
- 모든 Ansible 명령에서 자동으로 `sesacthon.pem` 사용
- 환경 변수나 CLI 옵션 불필요

---

### 3️⃣ GitHub Actions (CI/CD)

**파일**: `.github/workflows/infrastructure.yml`

```yaml
- name: 🔑 Setup SSH Key
  run: |
    mkdir -p ~/.ssh
    echo "${{ secrets.SSH_PRIVATE_KEY }}" > ~/.ssh/sesacthon.pem
    chmod 600 ~/.ssh/sesacthon.pem
    
    # 키 검증 (크기, 형식, 지문)
    KEY_SIZE=$(wc -c < ~/.ssh/sesacthon.pem)
    ssh-keygen -y -f ~/.ssh/sesacthon.pem > /dev/null
```

**Secret 관리**:
```bash
# GitHub Secrets에 등록 (한 번만 실행)
cat ~/.ssh/sesacthon.pem | gh secret set SSH_PRIVATE_KEY --repo SeSACTHON/backend
```

**동작**:
1. Secret에서 프라이빗 키 복원
2. 파일 크기 및 형식 검증
3. Ansible이 `ansible.cfg` 설정으로 자동 사용

---

## 🚀 초기 설정

### 1단계: SSH 키 페어 생성 (최초 1회)

```bash
# 이미 존재하는 경우 스킵
ls ~/.ssh/sesacthon.pem && echo "이미 존재합니다" || \
  ssh-keygen -t rsa -b 4096 -f ~/.ssh/sesacthon.pem -C "sesacthon-k8s-cluster"
```

### 2단계: 공개키 추출

```bash
ssh-keygen -y -f ~/.ssh/sesacthon.pem > ~/.ssh/sesacthon.pub
```

### 3단계: GitHub Secrets 등록

```bash
cat ~/.ssh/sesacthon.pem | gh secret set SSH_PRIVATE_KEY --repo SeSACTHON/backend
```

### 4단계: Terraform Apply (AWS 키 페어 교체)

```bash
cd terraform
terraform init
terraform plan  # 키 교체 확인
terraform apply # 승인 후 실행
```

---

## ✅ 검증

### 로컬 → EC2 SSH 접속 테스트

```bash
# Master 노드 IP 확인
cd terraform
MASTER_IP=$(terraform output -raw master_public_ip)

# SSH 접속 테스트
ssh -i ~/.ssh/sesacthon.pem ubuntu@$MASTER_IP "echo '✅ SSH 접속 성공!'"
```

### Ansible Ping 테스트

```bash
cd ansible
ansible all -i inventory/hosts.ini -m ping
```

**예상 출력**:
```yaml
k8s-master | SUCCESS => {
    "changed": false,
    "ping": "pong"
}
```

### GitHub Actions CI 테스트

```bash
# 더미 변경으로 CI 트리거
echo "# CI Test $(date)" >> ansible/README.md
git add ansible/README.md
git commit -m "test: SSH 통합 검증"
git push origin main

# CI 로그 확인
gh run list --limit 1
gh run watch $(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')
```

**CI 로그에서 확인**:
```
✅ Key file size: 3389 bytes
✅ SSH key format is valid (RSA)
✅ Public key fingerprint (last 16 chars): ...thon-k8s-rebuild
```

---

## 🔍 문제 해결

### ❌ "Permission denied (publickey)"

**원인**: AWS 키와 로컬 키 불일치

**해결**:
```bash
# 1. 현재 AWS 키 지문 확인
aws ec2 describe-key-pairs --key-names sesacthon --region ap-northeast-2 \
  --query 'KeyPairs[0].KeyFingerprint'

# 2. 로컬 키 지문 확인
ssh-keygen -l -E md5 -f ~/.ssh/sesacthon.pub | awk '{print $2}' | sed 's/MD5://'

# 3. 불일치 시 Terraform Apply로 교체
cd terraform && terraform apply -replace="aws_key_pair.k8s"
```

### ❌ "no such identity: /home/runner/.ssh/id_rsa"

**원인**: Ansible이 `ansible.cfg`를 무시하고 기본 키 시도

**해결**: `ansible.cfg`에 `IdentitiesOnly=yes` 설정 확인

```bash
grep "IdentitiesOnly" ansible/ansible.cfg
# 출력: ssh_args = ... -o IdentitiesOnly=yes ...
```

### ❌ GitHub Actions에서 키 검증 실패

**원인**: GitHub Secrets에 잘못된 키 등록

**해결**:
```bash
# 올바른 키로 재등록
cat ~/.ssh/sesacthon.pem | gh secret set SSH_PRIVATE_KEY --repo SeSACTHON/backend

# CI 재실행
gh run rerun $(gh run list --limit 1 --json databaseId --jq '.[0].databaseId')
```

---

## 📚 참고 자료

- [AWS EC2 Key Pairs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html)
- [Ansible SSH Connection](https://docs.ansible.com/ansible/latest/collections/ansible/builtin/ssh_connection.html)
- [GitHub Actions Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)

---

## 🔒 보안 고려사항

1. **프라이빗 키 보호**:
   - 로컬: `chmod 600 ~/.ssh/sesacthon.pem`
   - GitHub: Secrets로 암호화 저장
   - 절대 Git에 커밋하지 않음

2. **키 로테이션**:
   ```bash
   # 새 키 생성
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/sesacthon-new.pem
   
   # Terraform 변수 업데이트
   # terraform/variables.tf에서 public_key_path 수정
   
   # Apply로 교체
   cd terraform && terraform apply
   ```

3. **접근 제한**:
   - Security Group에서 SSH 접근 IP 제한 권장
   - `terraform/variables.tf`의 `allowed_cidr_blocks` 설정
