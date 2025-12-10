terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "SeSACTHON"
      ManagedBy   = "Terraform"
      Environment = var.environment
      Team        = "Backend"
    }
  }
}

# CloudFront requires ACM certificate in us-east-1
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "SeSACTHON"
      ManagedBy   = "Terraform"
      Environment = var.environment
      Team        = "Backend"
    }
  }
}

# Data Sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

locals {
  kubelet_profiles = {
    "k8s-master"          = "--node-labels=role=control-plane,domain=control-plane,service=platform-system,workload=control-plane,tier=platform,phase=0 --register-with-taints=role=control-plane:NoSchedule"
    "k8s-api-auth"        = "--node-labels=role=api,domain=auth,service=auth,workload=api,tier=business-logic,phase=1 --register-with-taints=domain=auth:NoSchedule"
    "k8s-api-my"          = "--node-labels=role=api,domain=my,service=my,workload=api,tier=business-logic,phase=1 --register-with-taints=domain=my:NoSchedule"
    "k8s-api-scan"        = "--node-labels=role=api,domain=scan,service=scan,workload=api,tier=business-logic,phase=2 --register-with-taints=domain=scan:NoSchedule"
    "k8s-api-character"   = "--node-labels=role=api,domain=character,service=character,workload=api,tier=business-logic,phase=2 --register-with-taints=domain=character:NoSchedule"
    "k8s-api-location"    = "--node-labels=role=api,domain=location,service=location,workload=api,tier=business-logic,phase=2 --register-with-taints=domain=location:NoSchedule"
    "k8s-api-image"       = "--node-labels=role=api,domain=image,service=image,workload=api,tier=business-logic,phase=3 --register-with-taints=domain=image:NoSchedule"
    "k8s-api-chat"        = "--node-labels=role=api,domain=chat,service=chat,workload=api,tier=business-logic,phase=3 --register-with-taints=domain=chat:NoSchedule"
    "k8s-worker-storage"  = "--node-labels=role=worker,domain=worker-storage,worker-type=storage,workload=worker-storage,tier=worker,phase=4"
    "k8s-worker-ai"       = "--node-labels=role=worker,domain=worker-ai,worker-type=ai,workload=worker-ai,tier=worker,phase=4"
    "k8s-rabbitmq"        = "--node-labels=role=infrastructure,domain=integration,infra-type=rabbitmq,workload=message-queue,tier=platform,phase=4 --register-with-taints=domain=integration:NoSchedule"
    "k8s-postgresql"      = "--node-labels=role=infrastructure,domain=data,infra-type=postgresql,workload=database,tier=data,phase=1 --register-with-taints=domain=data:NoSchedule"
    "k8s-redis"           = "--node-labels=role=infrastructure,domain=data,infra-type=redis,workload=cache,tier=data,phase=1 --register-with-taints=domain=data:NoSchedule"
    "k8s-monitoring"      = "--node-labels=role=infrastructure,domain=observability,infra-type=monitoring,workload=monitoring,tier=observability,phase=4 --register-with-taints=domain=observability:NoSchedule"
    "k8s-ingress-gateway" = "--node-labels=role=ingress-gateway,domain=gateway,infra-type=istio,workload=gateway,tier=network,phase=5 --register-with-taints=role=ingress-gateway:NoSchedule"
  }
}

# VPC Module
module "vpc" {
  source = "./modules/vpc"

  vpc_cidr    = var.vpc_cidr
  environment = var.environment
  azs         = data.aws_availability_zones.available.names
}

# Security Groups Module
module "security_groups" {
  source = "./modules/security-groups"

  vpc_id           = module.vpc.vpc_id
  allowed_ssh_cidr = var.allowed_ssh_cidr
  environment      = var.environment
}

# SSH Key Pair
resource "aws_key_pair" "k8s" {
  key_name   = "sesacthon"
  public_key = file(var.public_key_path)

  tags = {
    Name = "k8s-cluster-key"
  }
}

# EC2 Instances - Master (Control Plane + Monitoring)
module "master" {
  source = "./modules/ec2"

  instance_name        = "k8s-master"
  instance_type        = "t3.xlarge" # 16GB (Control Plane + Prometheus)
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[0]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 80 # Prometheus TSDB
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-master"
    kubelet_extra_args = local.kubelet_profiles["k8s-master"]
  })

  tags = {
    Role = "control-plane"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API Nodes (7개 노드)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Phase 1&2: MVP + Core APIs (배포 활성화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# API-1: Authentication & Authorization (필수)
module "api_auth" {
  source = "./modules/ec2"

  instance_name        = "k8s-api-auth"
  instance_type        = "t3.small" # 2GB
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[0]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 20
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-api-auth"
    kubelet_extra_args = local.kubelet_profiles["k8s-api-auth"]
  })

  tags = {
    Role     = "worker"
    Workload = "api-auth"
    Domain   = "auth"
    Phase    = "1"
  }
}

# API-2: My Page (필수)
module "api_my" {
  source = "./modules/ec2"

  instance_name        = "k8s-api-my"
  instance_type        = "t3.small" # 2GB
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[1]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 20
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-api-my"
    kubelet_extra_args = local.kubelet_profiles["k8s-api-my"]
  })

  tags = {
    Role     = "worker"
    Workload = "api-my"
    Domain   = "my"
    Phase    = "1"
  }
}

# API-3: Waste Scan (핵심 기능)
module "api_scan" {
  source = "./modules/ec2"

  instance_name        = "k8s-api-scan"
  instance_type        = "t3.medium" # 4GB
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[2]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 30
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-api-scan"
    kubelet_extra_args = local.kubelet_profiles["k8s-api-scan"]
  })

  tags = {
    Role     = "worker"
    Workload = "api-scan"
    Domain   = "scan"
    Phase    = "2"
  }
}

# API-4: Character & Mission (핵심 기능)
module "api_character" {
  source = "./modules/ec2"

  instance_name        = "k8s-api-character"
  instance_type        = "t3.small" # 2GB
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[0]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 20
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-api-character"
    kubelet_extra_args = local.kubelet_profiles["k8s-api-character"]
  })

  tags = {
    Role     = "worker"
    Workload = "api-character"
    Domain   = "character"
    Phase    = "2"
  }
}

# API-5: Location & Map (핵심 기능)
module "api_location" {
  source = "./modules/ec2"

  instance_name        = "k8s-api-location"
  instance_type        = "t3.small" # 2GB
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[1]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 20
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-api-location"
    kubelet_extra_args = local.kubelet_profiles["k8s-api-location"]
  })

  tags = {
    Role     = "worker"
    Workload = "api-location"
    Domain   = "location"
    Phase    = "2"
  }
}

# Phase 3: Extended APIs (vCPU 32개로 증가 완료 - 2025-11-08 활성화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# API-6: Image Delivery
module "api_image" {
  source = "./modules/ec2"

  instance_name        = "k8s-api-image"
  instance_type        = "t3.small" # 2GB
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[2]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 20
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-api-image"
    kubelet_extra_args = local.kubelet_profiles["k8s-api-image"]
  })

  tags = {
    Role     = "worker"
    Workload = "api-image"
    Domain   = "image"
    Phase    = "3"
  }
}

# API-7: Chat LLM
module "api_chat" {
  source = "./modules/ec2"

  instance_name        = "k8s-api-chat"
  instance_type        = "t3.medium" # 4GB
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[0]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 30
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-api-chat"
    kubelet_extra_args = local.kubelet_profiles["k8s-api-chat"]
  })

  tags = {
    Role     = "worker"
    Workload = "api-chat"
    Domain   = "chat"
    Phase    = "3"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Worker Nodes (2개 노드)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Phase 4: Workers (vCPU 32개로 증가 완료 - 2025-11-08 활성화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Worker-1: Storage & I/O Operations
module "worker_storage" {
  source = "./modules/ec2"

  instance_name        = "k8s-worker-storage"
  instance_type        = "t3.medium" # 4GB (I/O Bound - Eventlet Pool)
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[2]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 40 # Image uploads + Local WAL
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-worker-storage"
    kubelet_extra_args = local.kubelet_profiles["k8s-worker-storage"]
  })

  tags = {
    Role     = "worker"
    Workload = "worker-storage"
    Type     = "io-bound"
    Domain   = "scan"
    Phase    = "4"
  }
}

# Worker-2: AI Processing
module "worker_ai" {
  source = "./modules/ec2"

  instance_name        = "k8s-worker-ai"
  instance_type        = "t3.medium" # 4GB (Network Bound - Prefork Pool)
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[0]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 40 # AI models + GPT cache + Local WAL
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-worker-ai"
    kubelet_extra_args = local.kubelet_profiles["k8s-worker-ai"]
  })

  tags = {
    Role     = "worker"
    Workload = "worker-ai"
    Type     = "network-bound"
    Domain   = "scan,chat"
    Phase    = "4"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Infrastructure Nodes (4개 노드)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Phase 4: RabbitMQ (vCPU 32개로 증가 완료 - 2025-11-08 활성화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# EC2 Instances - RabbitMQ (Message Queue)
module "rabbitmq" {
  source = "./modules/ec2"

  instance_name        = "k8s-rabbitmq"
  instance_type        = "t3.medium" # 4GB (RabbitMQ only)
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[1]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 40 # RabbitMQ data
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-rabbitmq"
    kubelet_extra_args = local.kubelet_profiles["k8s-rabbitmq"]
  })

  tags = {
    Role     = "worker"
    Workload = "message-queue"
    Phase    = "4"
  }
}

# Phase 1&2: Core Infrastructure (배포 활성화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# EC2 Instances - PostgreSQL (Database - 도메인별 DB 분리)
module "postgresql" {
  source = "./modules/ec2"

  instance_name        = "k8s-postgresql"
  instance_type        = "t3.large" # 8GB (도메인별 DB: auth, my, scan, character, location, image, chat)
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[0]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 80 # PostgreSQL data (7 domains)
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-postgresql"
    kubelet_extra_args = local.kubelet_profiles["k8s-postgresql"]
  })

  tags = {
    Role     = "worker"
    Workload = "database"
    Phase    = "1"
  }
}

# EC2 Instances - Redis (Cache)
module "redis" {
  source = "./modules/ec2"

  instance_name        = "k8s-redis"
  instance_type        = "t3.medium" # 4GB (Redis only)
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[1]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 30 # Redis data (mostly in-memory)
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-redis"
    kubelet_extra_args = local.kubelet_profiles["k8s-redis"]
  })

  tags = {
    Role     = "worker"
    Workload = "cache"
    Phase    = "1"
  }
}

# EC2 Instances - Monitoring (Prometheus + Grafana)
# Phase 4: Monitoring (vCPU 32개로 증가 완료 - 2025-11-08 활성화)
module "monitoring" {
  source = "./modules/ec2"

  instance_name        = "k8s-monitoring"
  instance_type        = "t3.large" # 8GB (Prometheus + Grafana) - Optimized for 14-node cluster
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[1]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 60 # Prometheus TSDB + Grafana
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-monitoring"
    kubelet_extra_args = local.kubelet_profiles["k8s-monitoring"]
  })

  tags = {
    Role     = "worker"
    Workload = "monitoring"
    Phase    = "4"
  }
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 5: Network Nodes (New)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# EC2 Instances - Istio Ingress Gateway
module "ingress_gateway" {
  source = "./modules/ec2"

  instance_name        = "k8s-ingress-gateway"
  instance_type        = "t3.medium" # 2GB
  ami_id               = data.aws_ami.ubuntu.id
  subnet_id            = module.vpc.public_subnet_ids[0]
  security_group_ids   = [module.security_groups.cluster_sg_id]
  key_name             = aws_key_pair.k8s.key_name
  iam_instance_profile = aws_iam_instance_profile.k8s.name

  root_volume_size = 20
  root_volume_type = "gp3"

  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname           = "k8s-ingress-gateway"
    kubelet_extra_args = local.kubelet_profiles["k8s-ingress-gateway"]
  })

  tags = {
    Role     = "worker"
    Workload = "gateway"
    Phase    = "5"
  }
}

# Elastic IP for Master
resource "aws_eip" "master" {
  instance = module.master.instance_id
  domain   = "vpc"

  tags = {
    Name = "k8s-master-eip"
  }
}
