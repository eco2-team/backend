# Terraform 변수 값 설정

aws_region = "ap-northeast-2"
environment = "prod"

vpc_cidr = "10.0.0.0/16"

# SSH 접근 제한 (Session Manager 사용 시 선택)
# Session Manager는 SSH 포트(22) 없이도 접속 가능
# SSH는 비상 백업용으로만 사용
allowed_ssh_cidr = "0.0.0.0/0"  # 또는 본인 IP로 제한 (예: "1.2.3.4/32")

# SSH 키 (선택사항, 백업 접속용)
# Session Manager 사용 시 SSH 키 없어도 됨
# 비상시 접근용으로만 설정
public_key_path = "~/.ssh/sesacthon.pub"  # 없으면 "~/.ssh/id_rsa.pub"

cluster_name = "sesacthon"

# Route53 DNS 설정
# 도메인: growbin.app (Route53 Hosted Zone 등록 완료)
domain_name = "growbin.app"
create_wildcard_record = true  # *.growbin.app 생성

# ⭐ 주 접속 방법: AWS Session Manager (SSH 키 불필요)
# aws ssm start-session --target <INSTANCE_ID>

