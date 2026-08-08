#!/bin/bash
# Run the real scenario
export DATABASE_URL="postgresql+asyncpg://synthera:synthera_dev_pwd@localhost:5432/synthera_genesis"
export REDIS_URL="redis://localhost:6379/0"
export SECRET_KEY="dev-secret-key-change-in-production-64chars"
cd /root/synthera-genesis
exec .venv/bin/python scripts/real_scenario.py
