# Terraform State를 S3에 저장 (원격 상태 관리)
# 사용 전 S3 버킷과 DynamoDB 테이블을 미리 생성해야 합니다.

# ⚠️ 임시로 주석 처리 (TLS 인증서 오류 우회)
# terraform {
#   backend "s3" {
#     bucket = "sesacthon-terraform-state"
#     key    = "k8s-cluster/terraform.tfstate"
#     region = "ap-northeast-2"
#     
#     # State Locking (DynamoDB)
#     dynamodb_table = "terraform-state-lock"
#     encrypt        = true
#   }
# }

# 초기 설정 (최초 1회만 실행):
# 
# 1. S3 버킷 생성
# aws s3api create-bucket \
#   --bucket sesacthon-terraform-state \
#   --region ap-northeast-2 \
#   --create-bucket-configuration LocationConstraint=ap-northeast-2
#
# aws s3api put-bucket-versioning \
#   --bucket sesacthon-terraform-state \
#   --versioning-configuration Status=Enabled
#
# 2. DynamoDB 테이블 생성
# aws dynamodb create-table \
#   --table-name terraform-state-lock \
#   --attribute-definitions AttributeName=LockID,AttributeType=S \
#   --key-schema AttributeName=LockID,KeyType=HASH \
#   --billing-mode PAY_PER_REQUEST \
#   --region ap-northeast-2
#
# 3. 로컬 State를 S3로 마이그레이션
# terraform init -migrate-state

