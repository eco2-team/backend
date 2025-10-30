# Terraform 변수 값 설정

aws_region = "ap-northeast-2"
environment = "prod"

vpc_cidr = "10.0.0.0/16"

# 보안: 본인 IP로 제한 권장
# https://www.whatismyip.com/ 에서 확인
allowed_ssh_cidr = "0.0.0.0/0"  # TODO: 본인 IP로 변경 (예: "1.2.3.4/32")

public_key_path = "~/.ssh/id_rsa.pub"  # TODO: SSH 키 경로 확인

cluster_name = "sesacthon"

