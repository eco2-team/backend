variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "SSH 접근 허용 CIDR"
  type        = string
}

variable "environment" {
  description = "환경"
  type        = string
}

variable "enable_karpenter" {
  description = "Karpenter 태그 활성화 여부 (karpenter.sh/discovery)"
  type        = bool
  default     = false
}
