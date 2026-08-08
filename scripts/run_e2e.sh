#!/bin/bash
# H-Zero E2E verification wrapper — sets env vars then runs the script
export DATABASE_URL="postgresql+asyncpg://synthera:synthera_dev_pwd@localhost:5432/synthera_genesis"
export REDIS_URL="redis://localhost:6379/0"
export SECRET_KEY="dev-secret-key-change-in-production-64chars"
cd /root/synthera-genesis
exec /root/synthera-genesis/.venv/bin/python /root/synthera-genesis/scripts/e2e_verify.py
