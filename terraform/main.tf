terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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

# Data Sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]  # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
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
  key_name   = "k8s-cluster-key"
  public_key = file(var.public_key_path)
  
  tags = {
    Name = "k8s-cluster-key"
  }
}

# EC2 Instances - Master (Control Plane + Monitoring)
module "master" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-master"
  instance_type         = "t3.large"  # 8GB (Control Plane + Prometheus)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]
  security_group_ids    = [module.security_groups.master_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 80  # Prometheus TSDB
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-master"
  })
  
  tags = {
    Role = "control-plane"
  }
}

# EC2 Instances - API Waste (메인 폐기물 분석)
module "api_waste" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-waste"
  instance_type         = "t3.small"  # 2GB (3 replicas)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 30
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-waste"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api"
    Service  = "waste"
    Traffic  = "high"
  }
}

# EC2 Instances - API Auth (인증/인가)
module "api_auth" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-auth"
  instance_type         = "t3.micro"  # 1GB (2 replicas)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 20
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-auth"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api"
    Service  = "auth"
    Traffic  = "high"
  }
}

# EC2 Instances - API Userinfo (사용자 정보)
module "api_userinfo" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-userinfo"
  instance_type         = "t3.micro"  # 1GB (2 replicas)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[2]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 20
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-userinfo"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api"
    Service  = "userinfo"
    Traffic  = "medium"
  }
}

# EC2 Instances - API Location (지도/위치)
module "api_location" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-location"
  instance_type         = "t3.micro"  # 1GB (2 replicas)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 20
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-location"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api"
    Service  = "location"
    Traffic  = "medium"
  }
}

# EC2 Instances - API Recycle Info (재활용 정보)
module "api_recycle_info" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-recycle-info"
  instance_type         = "t3.micro"  # 1GB (2 replicas)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 20
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-recycle-info"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api"
    Service  = "recycle-info"
    Traffic  = "low"
  }
}

# EC2 Instances - API Chat LLM (LLM 채팅)
module "api_chat_llm" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-api-chat-llm"
  instance_type         = "t3.small"  # 2GB (3 replicas)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[2]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 30
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-api-chat-llm"
  })
  
  tags = {
    Role     = "worker"
    Workload = "api"
    Service  = "chat-llm"
    Traffic  = "high"
  }
}

# EC2 Instances - Worker Storage (image-uploader, rule-retriever, beat)
module "worker_storage" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-worker-storage"
  instance_type         = "t3.medium"  # 4GB
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 40
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-worker-storage"
  })
  
  tags = {
    Role     = "worker"
    Workload = "async-workers"
    Workers  = "image-uploader,rule-retriever,task-scheduler"
    Type     = "storage-processing"
  }
}

# EC2 Instances - Worker AI (gpt5-analyzer, response-generator)
module "worker_ai" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-worker-ai"
  instance_type         = "t3.medium"  # 4GB
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 40
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-worker-ai"
  })
  
  tags = {
    Role     = "worker"
    Workload = "async-workers"
    Workers  = "gpt5-analyzer,response-generator"
    Type     = "ai-processing"
  }
}

# EC2 Instances - Storage (Stateful Services)
module "storage" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-storage"
  instance_type         = "t3.large"  # 8GB (RabbitMQ, PostgreSQL, Redis)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]  # Same AZ as Master
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 100  # Stateful data
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-storage"
  })
  
  tags = {
    Role     = "worker"
    Workload = "storage"
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

