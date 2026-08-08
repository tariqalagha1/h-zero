# H-Zero — Vault Secret Management Module
# Injects proxy credentials, API keys, and database tokens dynamically

# ── Vault Secrets Engine Configuration ──────────────────────────────────────

resource "vault_mount" "h_zero_kv" {
  path        = "h-zero"
  type        = "kv-v2"
  description = "H-Zero platform secrets — API keys, DB creds, proxy tokens"
}

# ── Static Secrets ──────────────────────────────────────────────────────────

resource "vault_generic_secret" "database" {
  path = "${vault_mount.h_zero_kv.path}/database"

  data_json = jsonencode({
    postgres_user     = "synthera"
    postgres_password = var.database_password
    postgres_host     = module.vpc.database_endpoint
    postgres_port     = "5432"
    postgres_db       = "h_zero"
    verifier_user     = "verifier_role"
    verifier_password = random_password.verifier_password.result
    transport_user    = "transport_logger_role"
    transport_password = random_password.transport_password.result
  })
}

resource "vault_generic_secret" "api_keys" {
  path = "${vault_mount.h_zero_kv.path}/api_keys"

  data_json = jsonencode({
    pubmed_api_key        = var.pubmed_api_key
    semantic_scholar_key  = var.semantic_scholar_key
    openai_api_key        = var.openai_api_key
    anthropic_api_key     = var.anthropic_api_key
    google_api_key        = var.google_api_key
    proxy_url             = var.proxy_url
    proxy_username        = var.proxy_username
    proxy_password        = var.proxy_password
  })
}

resource "vault_generic_secret" "application" {
  path = "${vault_mount.h_zero_kv.path}/application"

  data_json = jsonencode({
    secret_key              = var.secret_key
    jwt_algorithm           = "HS256"
    access_token_minutes    = "30"
    refresh_token_days      = "7"
    master_encryption_key   = random_password.master_key.result
  })
}

# ── Dynamic AWS Credentials ─────────────────────────────────────────────────

resource "vault_aws_secret_backend" "aws" {
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key
  region     = var.aws_region
  path       = "aws-h-zero"
}

resource "vault_aws_secret_backend_role" "worker_role" {
  backend         = vault_aws_secret_backend.aws.path
  name            = "h-zero-worker"
  credential_type = "iam_user"

  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
        ]
        Resource = ["*"]
      }
    ]
  })
}

# ── Password Generation ─────────────────────────────────────────────────────

resource "random_password" "verifier_password" {
  length  = 32
  special = false
}

resource "random_password" "transport_password" {
  length  = 32
  special = false
}

resource "random_password" "master_key" {
  length  = 64
  special = false
}

# ── Outputs ─────────────────────────────────────────────────────────────────

output "vault_secrets_path" {
  value = vault_mount.h_zero_kv.path
}

output "database_credentials_path" {
  value = "${vault_mount.h_zero_kv.path}/database"
}

output "api_keys_path" {
  value = "${vault_mount.h_zero_kv.path}/api_keys"
}
