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

# EC2 Instances - Worker 1 (Application Pods - Sync API)
module "worker_1" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-worker-1"
  instance_type         = "t3.medium"  # 4GB (FastAPI Pods)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 40  # App + Images
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-worker-1"
  })
  
  tags = {
    Role     = "worker"
    Workload = "application"
  }
}

# EC2 Instances - Worker 2 (Celery Workers - Async Processing)
module "worker_2" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-worker-2"
  instance_type         = "t3.medium"  # 4GB (Celery Workers)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[2]
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 40  # Worker images
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-worker-2"
  })
  
  tags = {
    Role     = "worker"
    Workload = "async-workers"
  }
}

# EC2 Instances - RabbitMQ (Message Queue)
module "rabbitmq" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-rabbitmq"
  instance_type         = "t3.small"  # 2GB (RabbitMQ only)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[0]  # Same AZ as Master
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 40  # RabbitMQ data
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-rabbitmq"
  })
  
  tags = {
    Role     = "worker"
    Workload = "message-queue"
  }
}

# EC2 Instances - PostgreSQL (Database)
module "postgresql" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-postgresql"
  instance_type         = "t3.small"  # 2GB (PostgreSQL only)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]  # Different AZ
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 60  # PostgreSQL data
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-postgresql"
  })
  
  tags = {
    Role     = "worker"
    Workload = "database"
  }
}

# EC2 Instances - Redis (Cache)
module "redis" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-redis"
  instance_type         = "t3.small"  # 2GB (Redis only)
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[2]  # Different AZ
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 30  # Redis data (mostly in-memory)
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-redis"
  })
  
  tags = {
    Role     = "worker"
    Workload = "cache"
  }
}

# EC2 Instances - Monitoring (Prometheus + Grafana)
module "monitoring" {
  source = "./modules/ec2"
  
  instance_name         = "k8s-monitoring"
  instance_type         = "t3.large"  # 8GB (Prometheus + Grafana) - Upgraded for CPU
  ami_id                = data.aws_ami.ubuntu.id
  subnet_id             = module.vpc.public_subnet_ids[1]  # Same AZ as Worker-1
  security_group_ids    = [module.security_groups.worker_sg_id]
  key_name              = aws_key_pair.k8s.key_name
  iam_instance_profile  = aws_iam_instance_profile.k8s.name
  
  root_volume_size = 60  # Prometheus TSDB + Grafana
  root_volume_type = "gp3"
  
  user_data = templatefile("${path.module}/user-data/common.sh", {
    hostname = "k8s-monitoring"
  })
  
  tags = {
    Role     = "worker"
    Workload = "monitoring"
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

