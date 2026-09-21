from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ollama_client import OllamaClient


@pytest.mark.asyncio
async def test_concurrent_chat_serialized() -> None:
    in_flight = 0
    max_in_flight = 0

    client = OllamaClient("http://127.0.0.1:11434", "test", 30.0)
    mock_http = MagicMock()
    client._client = mock_http

    async def fake_post(url: str, json: dict) -> MagicMock:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.08)
        in_flight -= 1
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "message": {"role": "assistant", "content": "ok"},
        }
        return resp

    mock_http.post = AsyncMock(side_effect=fake_post)

    await asyncio.gather(
        client.chat([{"role": "user", "content": "a"}]),
        client.chat([{"role": "user", "content": "b"}]),
    )
    assert max_in_flight == 1
