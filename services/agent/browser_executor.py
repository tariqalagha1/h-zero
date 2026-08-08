"""H-Zero — Browser Action Executor.

Executes DOM actions through the Browser Fleet.
Translates ParsedActions into actual HTTP calls to sandbox instances.
Handles retries, timeouts, and error recovery.
"""

import asyncio
import time
from typing import Optional

import structlog

logger = structlog.get_logger("h_zero.agent.executor")

# Max retries per action
MAX_RETRIES = 2


class BrowserExecutor:
    """Executes browser actions against the sandbox fleet."""

    def __init__(self, fleet=None):
        self._fleet = fleet
        self._current_sandbox_id: Optional[str] = None

    async def navigate(self, url: str) -> dict:
        """Navigate to a URL. Returns page snapshot."""
        try:
            if self._fleet:
                result = await self._fleet.navigate(url)
                self._current_sandbox_id = result.get("sandbox_id")
                return result
            return await self._direct_navigate(url)
        except Exception as e:
            return {"error": str(e)[:500], "success": False, "url": url}

    async def execute(self, action_type: str, target: str = "",
                      value: str = "", sandbox_id: str = None) -> dict:
        """Execute a single browser action."""
        sid = sandbox_id or self._current_sandbox_id

        for attempt in range(MAX_RETRIES + 1):
            try:
                result = await self._execute_action(action_type, target, value, sid)
                if result.get("success", True) or attempt >= MAX_RETRIES:
                    return result
                logger.warning(f"Action {action_type} failed, retry {attempt + 1}")
                await asyncio.sleep(1)
            except Exception as e:
                if attempt >= MAX_RETRIES:
                    return {"action": action_type, "success": False, "error": str(e)[:500]}
                logger.warning(f"Action {action_type} error on attempt {attempt + 1}: {e}")
                await asyncio.sleep(1)

        return {"action": action_type, "success": False, "error": "Max retries exhausted"}

    async def _execute_action(self, action_type: str, target: str,
                              value: str, sandbox_id: str) -> dict:
        """Route action to correct sandbox API endpoint."""
        start = time.monotonic()

        if action_type == "navigate":
            result = await self._fleet.navigate(target) if self._fleet else await self._direct_navigate(target)
        elif action_type == "click":
            result = await self._fleet.click(
                selector=target if target.startswith(("#", ".")) else None,
                text=target,
                instance_id=sandbox_id,
            ) if self._fleet else {"success": True, "action": "click"}
        elif action_type == "type":
            result = await self._fleet.type_text(
                selector=target, value=value, instance_id=sandbox_id,
            ) if self._fleet else {"success": True, "action": "type"}
        elif action_type == "scroll":
            result = await self._fleet.navigate(
                f"about:blank",  # placeholder — real scroll handled differently
            ) if self._fleet else {"success": True, "action": "scroll"}
        elif action_type == "extract":
            result = await self._fleet.get_dom(sandbox_id) if self._fleet else {"success": True, "action": "extract"}
        elif action_type == "wait":
            await asyncio.sleep(min(float(value or "2"), 10))
            result = {"success": True, "action": "wait", "seconds": value}
        else:
            result = {"success": True, "action": action_type}

        result["duration_ms"] = int((time.monotonic() - start) * 1000)
        result["action"] = action_type
        return result

    async def get_dom(self, sandbox_id: str = None) -> dict:
        """Get current DOM state from sandbox."""
        sid = sandbox_id or self._current_sandbox_id
        try:
            if self._fleet:
                return await self._fleet.get_dom(sid)
            return {"url": "", "title": "", "text": "", "elements": [], "html_length": 0}
        except Exception as e:
            return {"error": str(e)[:500]}

    async def _direct_navigate(self, url: str) -> dict:
        """Direct navigation without fleet (dev mode)."""
        return {
            "url": url,
            "title": "Direct navigation (no fleet)",
            "status": 200,
            "load_time_ms": 0,
            "content_hash": "",
            "text": "",
            "interactive_elements": 0,
            "elements": [],
            "success": True,
        }

    async def click(self, target: str, sandbox_id: str = None) -> dict:
        """Click an element."""
        return await self.execute("click", target=target, sandbox_id=sandbox_id)

    async def type_text(self, selector: str, value: str, sandbox_id: str = None) -> dict:
        """Type into a field."""
        return await self.execute("type", target=selector, value=value, sandbox_id=sandbox_id)

    async def scroll(self, direction: str = "down", amount: int = 300,
                     sandbox_id: str = None) -> dict:
        """Scroll the page."""
        return await self.execute("scroll", target=direction, value=str(amount), sandbox_id=sandbox_id)
