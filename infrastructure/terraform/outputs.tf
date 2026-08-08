# H-Zero — Terraform Outputs

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private internal subnet IDs (LLM + DB)"
  value       = module.vpc.private_subnet_ids
}

output "egress_subnet_ids" {
  description = "Isolated egress subnet IDs (browser fleet)"
  value       = module.vpc.egress_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs (API + Nginx)"
  value       = module.vpc.public_subnet_ids
}

output "api_public_ip" {
  description = "Public IP of the API server"
  value       = aws_instance.api_server.public_ip
}

output "vault_secrets_path" {
  description = "Path to H-Zero secrets in Vault"
  value       = vault_mount.h_zero_kv.path
}

output "connection_string" {
  description = "PostgreSQL connection command (run from within VPC)"
  value       = "psql -h ${module.vpc.database_endpoint} -U synthera -d h_zero"
  sensitive   = true
}
