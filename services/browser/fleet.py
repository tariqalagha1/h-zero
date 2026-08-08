"""H-Zero — Browser Fleet Manager.

Manages a pool of isolated browser sandbox instances.
Handles scaling, health monitoring, request routing, and cleanup.
"""

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog

from services.agent.security.scope_enforcer import ScopeEnforcer, create_local_scope

logger = structlog.get_logger("h_zero.browser.fleet")


class SandboxState(str, Enum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    STARTING = "STARTING"
    UNHEALTHY = "UNHEALTHY"
    TERMINATED = "TERMINATED"


@dataclass
class SandboxInstance:
    """Tracked sandbox instance in the fleet."""
    id: str = field(default_factory=lambda: f"bx-{hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]}")
    endpoint: str = "http://localhost:9222"
    state: SandboxState = SandboxState.STARTING
    current_url: str = ""
    page_count: int = 0
    action_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used_at: str = ""
    error_count: int = 0
    max_errors: int = 10


@dataclass
class FleetStats:
    """Aggregated fleet statistics."""
    total_instances: int = 0
    idle: int = 0
    busy: int = 0
    starting: int = 0
    unhealthy: int = 0
    total_pages: int = 0
    total_actions: int = 0


class BrowserFleet:
    """Manages a pool of headless browser sandbox instances.

    Provides:
    - Round-robin routing of browser requests
    - Health monitoring and auto-recycling of dead instances
    - Scale-up/down based on load
    - Request queuing when all instances are busy
    """

    MIN_INSTANCES = 1
    MAX_INSTANCES = int(os.environ.get("BROWSER_FLEET_MAX", "10"))
    IDLE_TIMEOUT_SECONDS = 300  # Recycle after 5 min idle
    HEALTH_CHECK_INTERVAL = 30

    def __init__(self):
        self._instances: dict[str, SandboxInstance] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._health_task: Optional[asyncio.Task] = None
        self._scope = create_local_scope()

    async def start(self):
        """Initialize the fleet with minimum instances."""
        for _ in range(self.MIN_INSTANCES):
            await self._add_instance()

        self._health_task = asyncio.create_task(self._health_loop())
        logger.info(f"Browser fleet started with {self.MIN_INSTANCES} instances")

    async def stop(self):
        """Gracefully shut down all instances."""
        if self._health_task:
            self._health_task.cancel()

        for instance in list(self._instances.values()):
            await self._terminate_instance(instance.id)

        logger.info("Browser fleet stopped")

    async def acquire(self) -> SandboxInstance:
        """Acquire an available sandbox instance (blocks if none available)."""
        async with self._lock:
            # Find an idle instance
            for instance in self._instances.values():
                if instance.state == SandboxState.IDLE:
                    instance.state = SandboxState.BUSY
                    instance.last_used_at = datetime.now(timezone.utc).isoformat()
                    return instance

            # Scale up if possible
            if len(self._instances) < self.MAX_INSTANCES:
                instance = await self._add_instance()
                instance.state = SandboxState.BUSY
                return instance

        # All busy — wait in queue
        logger.info("All instances busy — queuing request")
        instance = await self._queue.get()
        instance.state = SandboxState.BUSY
        instance.last_used_at = datetime.now(timezone.utc).isoformat()
        return instance

    async def release(self, instance_id: str):
        """Release an instance back to the pool."""
        async with self._lock:
            instance = self._instances.get(instance_id)
            if not instance:
                return

            instance.state = SandboxState.IDLE
            instance.current_url = ""

        # If there are queued waiters, give them this instance
        if not self._queue.empty():
            try:
                waiter = self._queue.get_nowait()
                # The waiter will handle state transition
            except asyncio.QueueEmpty:
                pass

    async def navigate(self, url: str, instance_id: str = None) -> dict:
        """Navigate a sandbox to a URL. Auto-acquires instance if not provided."""
        # Enforce scope boundaries
        scope_result = self._scope.check(url)
        if scope_result.decision.value != "ALLOWED":
            logger.warning(f"Scope blocked navigation to {url}: {scope_result.reason}")
            return {"error": f"OUT_OF_SCOPE: {scope_result.reason}"}

        instance = None
        acquired = False

        if instance_id:
            instance = self._instances.get(instance_id)
        else:
            instance = await self.acquire()
            acquired = True

        if not instance:
            return {"error": "No available sandbox instance"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"{instance.endpoint}/navigate",
                    json={"url": url},
                )
                result = r.json()
                instance.current_url = url
                instance.page_count += 1
                return result
        except Exception as e:
            instance.error_count += 1
            if instance.error_count >= instance.max_errors:
                await self._terminate_instance(instance.id)
                await self._add_instance()
            return {"error": str(e)[:500]}
        finally:
            if acquired:
                await self.release(instance.id)

    async def click(self, selector: str = None, index: int = None,
                    text: str = None, instance_id: str = None) -> dict:
        """Click in a sandbox."""
        instance = self._instances.get(instance_id) if instance_id else None
        acquired = False
        if not instance:
            instance = await self.acquire()
            acquired = True

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{instance.endpoint}/click",
                    json={"selector": selector, "index": index, "text": text},
                )
                result = r.json()
                instance.action_count += 1
                return result
        except Exception as e:
            return {"error": str(e)[:300]}
        finally:
            if acquired:
                await self.release(instance.id)

    async def get_dom(self, instance_id: str = None) -> dict:
        """Get DOM snapshot from a sandbox."""
        instance = self._instances.get(instance_id) if instance_id else None
        if not instance:
            instance = await self.acquire()
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.get(f"{instance.endpoint}/dom")
                    return r.json()
            finally:
                await self.release(instance.id)
        else:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(f"{instance.endpoint}/dom")
                return r.json()

    async def type_text(self, selector: str, value: str, instance_id: str = None) -> dict:
        """Type text in a sandbox."""
        instance = self._instances.get(instance_id) if instance_id else None
        acquired = False
        if not instance:
            instance = await self.acquire()
            acquired = True

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{instance.endpoint}/type",
                    json={"selector": selector, "value": value},
                )
                result = r.json()
                instance.action_count += 1
                return result
        except Exception as e:
            return {"error": str(e)[:300]}
        finally:
            if acquired:
                await self.release(instance.id)

    def stats(self) -> FleetStats:
        """Return aggregated fleet statistics."""
        stats = FleetStats(total_instances=len(self._instances))
        for instance in self._instances.values():
            if instance.state == SandboxState.IDLE:
                stats.idle += 1
            elif instance.state == SandboxState.BUSY:
                stats.busy += 1
            elif instance.state == SandboxState.STARTING:
                stats.starting += 1
            elif instance.state == SandboxState.UNHEALTHY:
                stats.unhealthy += 1
            stats.total_pages += instance.page_count
            stats.total_actions += instance.action_count
        return stats

    async def _add_instance(self) -> SandboxInstance:
        """Add a new sandbox instance to the fleet."""
        port = 9222 + len(self._instances)
        instance = SandboxInstance(
            endpoint=f"http://browser-sandbox:{port}" if os.environ.get("DOCKER_ENV") else f"http://localhost:{port}",
        )
        self._instances[instance.id] = instance
        instance.state = SandboxState.IDLE
        logger.info(f"Added sandbox instance {instance.id} ({instance.endpoint})")
        return instance

    async def _terminate_instance(self, instance_id: str):
        """Terminate and remove an instance."""
        instance = self._instances.pop(instance_id, None)
        if instance:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(f"{instance.endpoint}/shutdown")
            except Exception:
                pass
            instance.state = SandboxState.TERMINATED
            logger.info(f"Terminated sandbox instance {instance_id}")

    async def _health_loop(self):
        """Background health monitoring loop."""
        while True:
            await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
            async with self._lock:
                for instance in list(self._instances.values()):
                    try:
                        import httpx
                        async with httpx.AsyncClient(timeout=5) as client:
                            r = await client.get(f"{instance.endpoint}/health")
                            if r.status_code != 200:
                                instance.error_count += 1
                            else:
                                instance.error_count = 0
                    except Exception:
                        instance.error_count += 1

                    if instance.error_count >= instance.max_errors:
                        await self._terminate_instance(instance.id)

                # Recycle long-idle instances
                now = datetime.now(timezone.utc)
                for instance in list(self._instances.values()):
                    if instance.state != SandboxState.IDLE:
                        continue
                    if instance.last_used_at:
                        last_used = datetime.fromisoformat(instance.last_used_at)
                        if (now - last_used).total_seconds() > self.IDLE_TIMEOUT_SECONDS:
                            if len(self._instances) > self.MIN_INSTANCES:
                                await self._terminate_instance(instance.id)

                # Maintain minimum instances
                while len(self._instances) < self.MIN_INSTANCES:
                    await self._add_instance()


# Singleton
_fleet: Optional[BrowserFleet] = None


async def get_browser_fleet() -> BrowserFleet:
    global _fleet
    if _fleet is None:
        _fleet = BrowserFleet()
        await _fleet.start()
    return _fleet
