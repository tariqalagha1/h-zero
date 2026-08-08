"""H-Zero — Standalone LLM Gateway.

Provider-neutral LLM interface. Self-contained — no Synthera dependencies.
Supports OpenAI, Anthropic, Google, and OpenAI-compatible providers.
"""

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Optional


class TaskType(str, Enum):
    GENERAL = "general"
    EMBEDDINGS = "embeddings"


@dataclass
class LLMRequest:
    messages: list[dict[str, str]]
    task_type: TaskType = TaskType.GENERAL
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    response_format: Optional[dict] = None
    timeout: Optional[int] = None


@dataclass
class LLMResponse:
    content: str
    model: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    error: Optional[str] = None


class BaseProvider(ABC):
    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = model

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse: ...


class OpenAIProvider(BaseProvider):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        import httpx
        url = f"{self.base_url or 'https://api.openai.com'}/v1/chat/completions"
        model = request.model or self.default_model or "gpt-4o-mini"
        payload = {
            "model": model, "messages": request.messages,
            "temperature": request.temperature or 0.7,
            "max_tokens": request.max_tokens or 4096,
        }
        if request.response_format:
            payload["response_format"] = request.response_format

        t0 = time.time()
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=request.timeout or 120)
        latency = (time.time() - t0) * 1000

        if r.status_code != 200:
            return LLMResponse(content="", model=model, provider="openai",
                             error=r.text[:500], latency_ms=latency)
        data = r.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=model, provider="openai", latency_ms=latency,
            input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
            output_tokens=data.get("usage", {}).get("completion_tokens", 0),
        )


class AnthropicProvider(BaseProvider):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        import httpx
        model = request.model or self.default_model or "claude-sonnet-4-20250514"
        system_msg = next((m["content"] for m in request.messages if m["role"] == "system"), None)
        user_msgs = [m for m in request.messages if m["role"] != "system"]

        payload = {"model": model, "max_tokens": request.max_tokens or 4096, "messages": user_msgs}
        if system_msg:
            payload["system"] = system_msg

        t0 = time.time()
        async with httpx.AsyncClient() as client:
            r = await client.post("https://api.anthropic.com/v1/messages", json=payload,
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                timeout=request.timeout or 120)
        latency = (time.time() - t0) * 1000

        if r.status_code != 200:
            return LLMResponse(content="", model=model, provider="anthropic",
                             error=r.text[:500], latency_ms=latency)
        data = r.json()
        return LLMResponse(
            content=data["content"][0]["text"], model=model, provider="anthropic",
            latency_ms=latency,
            input_tokens=data.get("usage", {}).get("input_tokens", 0),
            output_tokens=data.get("usage", {}).get("output_tokens", 0),
        )


class GoogleProvider(BaseProvider):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        import httpx
        model = request.model or "gemini-2.5-flash"
        contents = []
        for m in request.messages:
            role = "user" if m["role"] != "assistant" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        t0 = time.time()
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}",
                json={"contents": contents}, timeout=request.timeout or 120)
        latency = (time.time() - t0) * 1000

        if r.status_code != 200:
            return LLMResponse(content="", model=model, provider="google",
                             error=r.text[:500], latency_ms=latency)
        data = r.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        return LLMResponse(
            content=text, model=model, provider="google", latency_ms=latency,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
        )


PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
}


class LLMGateway:
    """Standalone LLM gateway. No Synthera deps."""

    def __init__(self):
        self._provider: Optional[BaseProvider] = None
        self._provider_name = ""

    def configure(self, provider: str, api_key: str = "", base_url: str = "", model: str = ""):
        cls = PROVIDERS.get(provider, OpenAIProvider)
        self._provider = cls(api_key=api_key, base_url=base_url, model=model)
        self._provider_name = provider

    @property
    def available(self) -> bool:
        return self._provider is not None

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if not self._provider:
            # Auto-detect from env
            for name, cls in PROVIDERS.items():
                key = os.environ.get(f"{name.upper()}_API_KEY", "")
                if key:
                    self._provider = cls(api_key=key)
                    self._provider_name = name
                    break
        if not self._provider:
            return LLMResponse(content="", error="No LLM provider configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY.")
        return await self._provider.generate(request)


# Singleton
_gateway: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
