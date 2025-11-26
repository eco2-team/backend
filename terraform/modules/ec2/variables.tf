variable "instance_name" {
  description = "인스턴스 이름"
  type        = string
}

variable "instance_type" {
  description = "인스턴스 타입"
  type        = string
}

variable "ami_id" {
  description = "AMI ID"
  type        = string
}

variable "subnet_id" {
  description = "서브넷 ID"
  type        = string
}

variable "security_group_ids" {
  description = "보안 그룹 ID 목록"
  type        = list(string)
}

variable "key_name" {
  description = "SSH 키 페어 이름"
  type        = string
}

variable "iam_instance_profile" {
  description = "IAM Instance Profile (Session Manager용)"
  type        = string
  default     = ""
}

variable "root_volume_size" {
  description = "루트 볼륨 크기 (GB)"
  type        = number
  default     = 30
}

variable "root_volume_type" {
  description = "볼륨 타입"
  type        = string
  default     = "gp3"
}

variable "user_data" {
  description = "User data 스크립트"
  type        = string
  default     = ""
}

variable "tags" {
  description = "추가 태그"
  type        = map(string)
  default     = {}
}
