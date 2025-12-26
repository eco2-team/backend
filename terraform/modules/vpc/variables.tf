variable "vpc_cidr" {
  description = "VPC CIDR 블록"
  type        = string
}

variable "environment" {
  description = "환경"
  type        = string
}

variable "azs" {
  description = "가용 영역 목록"
  type        = list(string)
}

variable "enable_karpenter" {
  description = "Karpenter 태그 활성화 여부 (karpenter.sh/discovery)"
  type        = bool
  default     = false
}
