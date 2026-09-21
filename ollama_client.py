from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

ChatRole = Literal["system", "user", "assistant", "tool"]
ChatMessage = dict[str, Any]

_model_lock = asyncio.Lock()


class OllamaError(Exception):
    """Base error for Ollama client failures."""


class OllamaUnavailableError(OllamaError):
    """Ollama server is unreachable."""


class OllamaTimeoutError(OllamaError):
    """Ollama request timed out."""


class OllamaModelError(OllamaError):
    """Ollama returned an HTTP error."""


def parse_chat_response(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise OllamaError("Unexpected Ollama response: missing message")
    return message


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def open(self) -> None:
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("OllamaClient is not opened")
        return self._client

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        unload_after: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/api/chat"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": 0 if unload_after else "5m",
        }
        if tools:
            body["tools"] = tools

        queue_start = time.perf_counter()
        async with _model_lock:
            queue_wait = time.perf_counter() - queue_start
            if queue_wait > 0.05:
                logger.info("[agent] waiting for model lock (%.2fs)", queue_wait)
            gen_start = time.perf_counter()
            logger.info("[ollama] started")
            try:
                response = await self.client.post(url, json=body)
            except httpx.TimeoutException as exc:
                raise OllamaTimeoutError(str(exc)) from exc
            except httpx.RequestError as exc:
                raise OllamaUnavailableError(str(exc)) from exc
            gen_duration = time.perf_counter() - gen_start
            logger.info(
                "[ollama] completed in %.1fs queue_wait=%.2fs",
                gen_duration,
                queue_wait,
            )

            if response.status_code >= 400:
                detail = response.text.strip() or f"HTTP {response.status_code}"
                logger.warning("Ollama error %s: %s", response.status_code, detail)
                raise OllamaModelError(detail)

            try:
                payload = response.json()
            except ValueError as exc:
                raise OllamaError("Invalid JSON from Ollama") from exc

            if payload.get("error"):
                raise OllamaModelError(str(payload["error"]))

            return parse_chat_response(payload)

    async def unload_model(self) -> None:
        url = f"{self.base_url}/api/generate"
        try:
            await self.client.post(
                url, json={"model": self.model, "keep_alive": 0}
            )
        except httpx.HTTPError:
            logger.debug("Model unload request failed (non-fatal)")
