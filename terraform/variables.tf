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
  default     = "~/.ssh/sesacthon.pub"
}

variable "enable_cloudfront" {
  description = "CloudFront CDN 활성화 여부 (기본값: true)"
  type        = bool
  default     = true
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

variable "service_account_oidc_issuer_url" {
  description = "Self-managed Kubernetes ServiceAccount OIDC Issuer URL (예: https://oidc.growbin.app/dev). 비워두면 환경 이름을 기준으로 자동 구성됩니다."
  type        = string
  default     = ""
}

variable "enable_irsa" {
  description = "IRSA(OIDC) 구성을 활성화할지 여부. Self-managed Issuer가 준비되지 않았다면 false로 두고 나중에 전환합니다."
  type        = bool
  default     = false
}

variable "dockerhub_username" {
  description = "Docker Hub 사용자명 (이미지 Pull용)"
  type        = string
  default     = "mng990"
}

variable "dockerhub_password" {
  description = "Docker Hub Personal Access Token (민감정보)"
  type        = string
  sensitive   = true
}
