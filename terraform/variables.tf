variable "aws_region" {
  description = "AWS 리전"
  type        = string
  default     = "ap-northeast-2"
}

variable "environment" {
  description = "환경 (dev, prod)"
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "VPC CIDR 블록"
  type        = string
  default     = "10.0.0.0/16"
}

variable "allowed_ssh_cidr" {
  description = "SSH 접근 허용 CIDR (보안을 위해 특정 IP로 제한 권장)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "public_key_path" {
  description = "SSH 공개 키 경로"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "cluster_name" {
  description = "Kubernetes 클러스터 이름"
  type        = string
  default     = "sesacthon"
}

variable "domain_name" {
  description = "Route53 도메인 이름 (예: example.com) - 비어있으면 DNS 설정 안 함"
  type        = string
  default     = ""
}

variable "create_wildcard_record" {
  description = "Wildcard DNS 레코드 생성 여부 (*.domain.com)"
  type        = bool
  default     = false
}

