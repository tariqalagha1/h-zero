# H-Zero — Terraform Variables

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "ami_id" {
  description = "AMI ID for EC2 instances (Ubuntu 22.04 LTS recommended)"
  type        = string
  default     = "ami-0c7217cdde317cfec"  # Ubuntu 22.04 us-east-1
}

variable "api_instance_type" {
  description = "EC2 instance type for API server"
  type        = string
  default     = "t3.medium"
}

variable "worker_instance_type" {
  description = "EC2 instance type for worker nodes"
  type        = string
  default     = "t3.large"
}

variable "worker_count" {
  description = "Number of worker nodes"
  type        = number
  default     = 2
}

variable "availability_zones" {
  description = "AZs for multi-zone deployment"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "vpc_cidr" {
  description = "CIDR block for the H-Zero VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_internal_cidrs" {
  description = "CIDRs for private-internal subnet (LLM + DB, no internet)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "isolated_egress_cidrs" {
  description = "CIDRs for isolated-egress subnet (outbound scraping only)"
  type        = list(string)
  default     = ["10.0.3.0/24", "10.0.4.0/24"]
}

variable "public_cidrs" {
  description = "CIDRs for public-facing subnet (API, Nginx)"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24"]
}

variable "vault_address" {
  description = "HashiCorp Vault server address"
  type        = string
  default     = "https://vault.h-zero.internal:8200"
}

variable "vault_token" {
  description = "Vault authentication token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "database_password" {
  description = "PostgreSQL master password (stored in Vault)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "secret_key" {
  description = "Application secret key (stored in Vault)"
  type        = string
  sensitive   = true
  default     = ""
}
