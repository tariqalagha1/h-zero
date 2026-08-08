# H-Zero — Terraform Infrastructure Provisioning
# Cloud-agnostic module supporting AWS, GCP, Azure
# Phase 1: VPC, subnets, security groups, instance provisioning

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    vault = {
      source  = "hashicorp/vault"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# ── Provider Configuration ──────────────────────────────────────────────────

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "h-zero"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

provider "vault" {
  address = var.vault_address
  token   = var.vault_token
}

# ── VPC with Multi-Zone Subnet Architecture ─────────────────────────────────

module "vpc" {
  source = "./modules/vpc"

  project_name     = "h-zero"
  environment      = var.environment
  vpc_cidr         = var.vpc_cidr
  availability_zones = var.availability_zones

  # Two distinct network zones:
  # 1. private-internal: LLM inference server + database (no internet access)
  # 2. isolated-egress: outbound web traffic (scraping, API calls)
  private_subnet_cidrs   = var.private_internal_cidrs
  egress_subnet_cidrs    = var.isolated_egress_cidrs
  public_subnet_cidrs    = var.public_cidrs
}

# ── Security Groups ─────────────────────────────────────────────────────────

resource "aws_security_group" "llm_cluster" {
  name        = "h-zero-llm-cluster-${var.environment}"
  description = "LLM inference cluster — internal only, no internet access"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = var.private_internal_cidrs
    description = "vLLM/Ollama API from internal services"
  }
}

resource "aws_security_group" "database" {
  name        = "h-zero-database-${var.environment}"
  description = "PostgreSQL + Qdrant — internal only"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = var.private_internal_cidrs
    description = "PostgreSQL from private network"
  }
}

resource "aws_security_group" "browser_fleet" {
  name        = "h-zero-browser-fleet-${var.environment}"
  description = "Headless browser sandboxes — egress only, no ingress"
  vpc_id      = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Browser egress for web scraping (NAT gateway required)"
  }
}

# ── Compute: API + Worker Instances ─────────────────────────────────────────

resource "aws_instance" "api_server" {
  ami           = var.ami_id
  instance_type = var.api_instance_type
  subnet_id     = module.vpc.public_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.llm_cluster.id]

  root_block_device {
    volume_size = 50
    volume_type = "gp3"
  }

  tags = {
    Name = "h-zero-api-${var.environment}"
    Role = "api"
  }
}

resource "aws_instance" "worker_node" {
  count         = var.worker_count
  ami           = var.ami_id
  instance_type = var.worker_instance_type
  subnet_id     = module.vpc.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.database.id]

  root_block_device {
    volume_size = 100
    volume_type = "gp3"
  }

  tags = {
    Name = "h-zero-worker-${count.index + 1}-${var.environment}"
    Role = "worker"
  }
}

# ── Outputs ─────────────────────────────────────────────────────────────────

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

output "egress_subnet_ids" {
  value = module.vpc.egress_subnet_ids
}

output "api_public_ip" {
  value = aws_instance.api_server.public_ip
}
