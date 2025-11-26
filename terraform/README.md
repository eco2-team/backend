# 🏗️ Terraform - K8s 인프라 프로비저닝

## 🚀 빠른 시작

```bash
# 1. 초기화
terraform init

# 2. 계획 확인
terraform plan

# 3. 적용
terraform apply

# 4. Ansible Inventory 생성
terraform output -raw ansible_inventory > ../ansible/inventory/hosts.ini
```

## 📦 생성되는 리소스

- VPC (10.0.0.0/16)
- Public Subnets ×3
- Internet Gateway
- Route Tables
- Security Groups (Master, Worker)
- EC2 Instances (Master ×1, Worker ×2)
- EBS Volumes
- Elastic IP (Master)

## 💰 예상 비용

- Master (t3.medium): $30/월
- Worker 1 (t3.medium): $30/월
- Worker 2 (t3.small): $15/월
- EBS (80GB): $6/월
- Elastic IP: $0 (사용 중)
- 데이터 전송: ~$10/월

**총: $91/월**

## 🔧 커스터마이징

`terraform.tfvars` 파일 수정:

```hcl
aws_region = "ap-northeast-2"
allowed_ssh_cidr = "YOUR_IP/32"  # 본인 IP로 변경
public_key_path = "~/.ssh/id_rsa.pub"
```

## 📊 출력 확인

```bash
# 모든 출력
terraform output

# 특정 출력
terraform output master_public_ip

# SSH 명령어
terraform output -json ssh_commands
```

## 🗑️ 삭제

```bash
terraform destroy
```

---

## 📚 참고 문서
- `docs/infrastructure/03-iac-terraform-ansible.md`
- `docs/architecture/gitops/ATLANTIS_TERRAFORM_FLOW.md`
