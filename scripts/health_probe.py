#!/usr/bin/env python3
"""H-Zero — Health Probe Script.

Pings all infrastructure services and reports status.
Run as a cron job or Docker health check companion.

USAGE:
    python scripts/health_probe.py              # Check all services
    python scripts/health_probe.py --restart     # Auto-restart failed workers
"""

import argparse
import asyncio
import os
import sys
import time

SERVICES = {
    "postgres": {
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "db": os.environ.get("POSTGRES_DB", "h_zero"),
        "user": os.environ.get("POSTGRES_USER", "synthera"),
        "password": os.environ.get("POSTGRES_PASSWORD", "synthera_dev_pwd"),
    },
    "redis": {
        "host": os.environ.get("REDIS_HOST", "localhost"),
        "port": int(os.environ.get("REDIS_PORT", "6379")),
    },
    "temporal": {
        "host": os.environ.get("TEMPORAL_HOST", "localhost"),
        "port": int(os.environ.get("TEMPORAL_PORT", "7233")),
    },
    "qdrant": {
        "host": os.environ.get("QDRANT_HOST", "localhost"),
        "port": int(os.environ.get("QDRANT_PORT", "6333")),
    },
    "api": {
        "url": os.environ.get("API_URL", "http://localhost:8000/health"),
    },
    "minio": {
        "host": os.environ.get("MINIO_HOST", "localhost"),
        "port": int(os.environ.get("MINIO_PORT", "9000")),
    },
}


async def check_postgres() -> dict:
    """Check PostgreSQL connectivity."""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=SERVICES["postgres"]["host"],
            port=SERVICES["postgres"]["port"],
            database=SERVICES["postgres"]["db"],
            user=SERVICES["postgres"]["user"],
            password=SERVICES["postgres"]["password"],
            timeout=5,
        )
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        return {"status": "healthy", "detail": str(version)[:80]}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:200]}


async def check_redis() -> dict:
    """Check Redis connectivity."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis(
            host=SERVICES["redis"]["host"],
            port=SERVICES["redis"]["port"],
            socket_connect_timeout=3,
        )
        await r.ping()
        await r.close()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:200]}


async def check_temporal() -> dict:
    """Check Temporal server connectivity."""
    try:
        from temporalio.client import Client
        client = await Client.connect(
            f"{SERVICES['temporal']['host']}:{SERVICES['temporal']['port']}",
        )
        await client.workflow_service.get_system_info()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:200]}


async def check_qdrant() -> dict:
    """Check Qdrant connectivity."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(
            host=SERVICES["qdrant"]["host"],
            port=SERVICES["qdrant"]["port"],
            timeout=5,
        )
        collections = client.get_collections()
        return {"status": "healthy", "collections": len(collections.collections)}
    except ImportError:
        return {"status": "skipped", "detail": "qdrant-client not installed"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:200]}


async def check_api() -> dict:
    """Check API health endpoint."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(SERVICES["api"]["url"])
            if r.status_code == 200:
                return {"status": "healthy", "detail": r.json()}
            return {"status": "unhealthy", "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:200]}


async def check_minio() -> dict:
    """Check MinIO connectivity."""
    try:
        from minio import Minio
        client = Minio(
            f"{SERVICES['minio']['host']}:{SERVICES['minio']['port']}",
            access_key="synthera",
            secret_key="synthera_dev_pwd",
            secure=False,
        )
        buckets = client.list_buckets()
        return {"status": "healthy", "buckets": len(buckets)}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:200]}


async def run_all_checks() -> dict:
    """Run all health checks concurrently."""
    results = {}
    tasks = {
        "postgres": check_postgres(),
        "redis": check_redis(),
        "temporal": check_temporal(),
        "qdrant": check_qdrant(),
        "api": check_api(),
        "minio": check_minio(),
    }

    for name, coro in tasks.items():
        try:
            result = await coro
        except Exception as e:
            result = {"status": "error", "error": str(e)[:200]}
        results[name] = result

    healthy = sum(1 for r in results.values() if r.get("status") == "healthy")
    unhealthy = sum(1 for r in results.values() if r.get("status") != "healthy")

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "services": results,
        "summary": {
            "total": len(results),
            "healthy": healthy,
            "unhealthy": unhealthy,
            "overall": "healthy" if unhealthy == 0 else "degraded",
        },
    }


def restart_workers():
    """Attempt to restart Temporal worker process."""
    import subprocess
    try:
        result = subprocess.run(
            ["python", "-m", "apps.worker.main"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return {"restarted": True, "pid": None, "output": result.stderr[:200]}
    except subprocess.TimeoutExpired:
        return {"restarted": True, "pid": None, "detail": "worker started (timeout expected)"}
    except Exception as e:
        return {"restarted": False, "error": str(e)[:200]}


def main():
    parser = argparse.ArgumentParser(description="H-Zero Health Probe")
    parser.add_argument("--restart", action="store_true", help="Auto-restart failed workers")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    import json as json_mod
    results = asyncio.run(run_all_checks())

    if args.json:
        print(json_mod.dumps(results, indent=2))
    else:
        for name, result in results["services"].items():
            status = result.get("status", "unknown")
            icon = "✓" if status == "healthy" else "✗"
            detail = result.get("detail") or result.get("error", "")
            print(f"  {icon} {name:12s} {status:10s}  {detail}")

        print(f"\n{results['summary']['healthy']}/{results['summary']['total']} healthy")

    if args.restart:
        unhealthy_services = [
            name for name, r in results["services"].items()
            if r.get("status") != "healthy"
        ]
        if "temporal" in unhealthy_services:
            restart_result = restart_workers()
            print(f"\nWorker restart: {restart_result}")

    # Exit code: 0 if all healthy, 1 if any unhealthy
    sys.exit(0 if results["summary"]["unhealthy"] == 0 else 1)


if __name__ == "__main__":
    main()
