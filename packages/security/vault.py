"""H-Zero — Vault Secret Management Integration.

Provides dynamic credential injection for PostgreSQL, API keys, and proxy tokens.
Interfaces with HashiCorp Vault via hvac SDK. Falls back to environment variables
when Vault is unavailable (dev mode).
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("h_zero.vault")


@dataclass
class VaultCredentials:
    """Resolved credentials from Vault or environment fallback."""
    # Database
    postgres_user: str = ""
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: str = "5432"
    postgres_db: str = "h_zero"
    verifier_user: str = "verifier_role"
    verifier_password: str = ""
    transport_user: str = "transport_logger_role"
    transport_password: str = ""

    # API Keys
    pubmed_api_key: str = ""
    semantic_scholar_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Proxy
    proxy_url: str = ""
    proxy_username: str = ""
    proxy_password: str = ""

    # Application
    secret_key: str = ""
    master_encryption_key: str = ""


class VaultClient:
    """Lazy-connecting Vault client for H-Zero secret management.

    In production, reads from Vault at 'h-zero/'. In dev, falls back to env vars.
    Never logs or exposes plaintext secrets.
    """

    VAULT_MOUNT = "h-zero"

    def __init__(self, vault_addr: str = "", vault_token: str = ""):
        self._vault_addr = vault_addr or os.environ.get("VAULT_ADDR", "")
        self._vault_token = vault_token or os.environ.get("VAULT_TOKEN", "")
        self._client = None
        self._credentials: Optional[VaultCredentials] = None

    @property
    def available(self) -> bool:
        return bool(self._vault_addr and self._vault_token)

    async def _get_client(self):
        """Lazy-import hvac to avoid hard dependency in dev."""
        if self._client is not None:
            return self._client
        if not self.available:
            return None
        try:
            import hvac
            self._client = hvac.Client(url=self._vault_addr, token=self._vault_token)
            if not self._client.is_authenticated():
                logger.warning("Vault authentication failed — falling back to env vars")
                self._client = None
            else:
                logger.info("Vault client authenticated")
        except ImportError:
            logger.warning("hvac not installed — Vault integration disabled")
            self._client = None
        except Exception as e:
            logger.error(f"Vault client init failed: {e}")
            self._client = None
        return self._client

    async def resolve_credentials(self) -> VaultCredentials:
        """Resolve all H-Zero credentials from Vault or environment fallback."""
        if self._credentials is not None:
            return self._credentials

        creds = VaultCredentials()
        client = await self._get_client()

        if client:
            try:
                # Read database secrets
                db_secret = client.secrets.kv.v2.read_secret_version(
                    path="database", mount_point=self.VAULT_MOUNT
                )
                db_data = db_secret.get("data", {}).get("data", {})
                creds.postgres_user = db_data.get("postgres_user", "")
                creds.postgres_password = db_data.get("postgres_password", "")
                creds.postgres_host = db_data.get("postgres_host", "")
                creds.postgres_port = db_data.get("postgres_port", "5432")
                creds.postgres_db = db_data.get("postgres_db", "h_zero")
                creds.verifier_password = db_data.get("verifier_password", "")
                creds.transport_password = db_data.get("transport_password", "")

                # Read API keys
                api_secret = client.secrets.kv.v2.read_secret_version(
                    path="api_keys", mount_point=self.VAULT_MOUNT
                )
                api_data = api_secret.get("data", {}).get("data", {})
                creds.pubmed_api_key = api_data.get("pubmed_api_key", "")
                creds.semantic_scholar_key = api_data.get("semantic_scholar_key", "")
                creds.openai_api_key = api_data.get("openai_api_key", "")
                creds.anthropic_api_key = api_data.get("anthropic_api_key", "")
                creds.google_api_key = api_data.get("google_api_key", "")
                creds.proxy_url = api_data.get("proxy_url", "")
                creds.proxy_username = api_data.get("proxy_username", "")
                creds.proxy_password = api_data.get("proxy_password", "")

                # Read application secrets
                app_secret = client.secrets.kv.v2.read_secret_version(
                    path="application", mount_point=self.VAULT_MOUNT
                )
                app_data = app_secret.get("data", {}).get("data", {})
                creds.secret_key = app_data.get("secret_key", "")
                creds.master_encryption_key = app_data.get("master_encryption_key", "")

                logger.info("Credentials resolved from Vault")

            except Exception as e:
                logger.error(f"Vault secret resolution failed: {e} — falling back to env")

        # Fallback to environment variables
        if not creds.postgres_password:
            creds.postgres_password = os.environ.get("POSTGRES_PASSWORD", "")
        if not creds.secret_key:
            creds.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
        if not creds.master_encryption_key:
            creds.master_encryption_key = hashlib.sha256(
                creds.secret_key.encode()
            ).hexdigest()
        if not creds.openai_api_key:
            creds.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not creds.anthropic_api_key:
            creds.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not creds.google_api_key:
            creds.google_api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not creds.pubmed_api_key:
            creds.pubmed_api_key = os.environ.get("PUBMED_API_KEY", "")

        self._credentials = creds
        return creds

    def build_database_url(self, creds: VaultCredentials, async_mode: bool = True) -> str:
        """Build SQLAlchemy-compatible database URL from credentials."""
        prefix = "postgresql+asyncpg" if async_mode else "postgresql"
        return (
            f"{prefix}://{creds.postgres_user}:{creds.postgres_password}"
            f"@{creds.postgres_host}:{creds.postgres_port}/{creds.postgres_db}"
        )

    @staticmethod
    def mask_secret(value: str) -> str:
        """Return a safe masked version for logging."""
        if not value:
            return "***"
        if len(value) <= 8:
            return "*" * len(value)
        return value[:4] + "*" * (len(value) - 8) + value[-4:]


# Singleton
_vault: Optional[VaultClient] = None


def get_vault_client() -> VaultClient:
    global _vault
    if _vault is None:
        _vault = VaultClient()
    return _vault
