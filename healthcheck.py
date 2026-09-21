from __future__ import annotations

import asyncio
import logging

import httpx

from config import Settings

logger = logging.getLogger(__name__)


async def log_startup_connectivity(settings: Settings) -> None:
    await _probe_ollama(settings)
    await _probe_home_assistant(settings)


async def _probe_ollama(settings: Settings) -> None:
    url = f"{settings.ollama_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
        logger.info("[startup] Ollama reachable HTTP %s url=%s", resp.status_code, settings.ollama_url)
    except httpx.HTTPError as exc:
        logger.warning(
            "[startup] Ollama not reachable url=%s err=%s "
            "(Colima: try OLLAMA_URL=http://host.lima.internal:11434 with docker-compose.colima.yml)",
            settings.ollama_url,
            exc,
        )


async def _probe_home_assistant(settings: Settings) -> None:
    if not settings.home_assistant_token:
        logger.info("[startup] HOME_ASSISTANT_TOKEN not set — HA tools disabled")
        return
    url = f"{settings.home_assistant_url.rstrip('/')}/api/"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {settings.home_assistant_token}"},
            )
        logger.info(
            "[startup] Home Assistant reachable HTTP %s url=%s",
            resp.status_code,
            settings.home_assistant_url,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "[startup] Home Assistant not reachable url=%s err=%s "
            "(Colima: run ./deploy/colima.sh — uses host network for LAN; "
            "or colima stop && colima start --network-address)",
            settings.home_assistant_url,
            exc,
        )
