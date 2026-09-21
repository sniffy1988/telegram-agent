from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 4 * 1024 * 1024


class WebSearchTool:
    name = "web_search"
    description = "Search the web for current information, news, and facts."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    }

    def __init__(self, max_results: int) -> None:
        self.max_results = max_results

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"ok": False, "error": "empty_query", "results": []}
        try:
            from ddgs import DDGS

            def _search() -> list[dict[str, str]]:
                rows: list[dict[str, str]] = []
                with DDGS() as ddgs:
                    for item in ddgs.text(query, max_results=self.max_results):
                        rows.append(
                            {
                                "title": str(item.get("title", ""))[:200],
                                "snippet": str(item.get("body", item.get("snippet", "")))[
                                    :400
                                ],
                                "url": str(item.get("href", item.get("url", "")))[:500],
                            }
                        )
                return rows

            results = await asyncio.to_thread(_search)
            if not results:
                return {"ok": False, "error": "no_results", "results": []}
            return {"ok": True, "results": results}
        except Exception as exc:
            logger.warning("web_search failed: %s", exc)
            return {"ok": False, "error": "search_failed", "results": []}


class ImageSearchTool:
    name = "image_search"
    description = "Find images on the web for a query."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Image search query"},
        },
        "required": ["query"],
    }

    def __init__(self, max_images: int) -> None:
        self.max_images = max_images

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"ok": False, "error": "empty_query", "images": []}
        try:
            from ddgs import DDGS

            def _search() -> list[dict[str, str]]:
                rows: list[dict[str, str]] = []
                with DDGS() as ddgs:
                    for item in ddgs.images(query, max_results=self.max_images):
                        rows.append(
                            {
                                "title": str(item.get("title", ""))[:200],
                                "image_url": str(
                                    item.get("image", item.get("thumbnail", ""))
                                )[:800],
                                "source_url": str(item.get("url", ""))[:500],
                            }
                        )
                return rows

            images = await asyncio.to_thread(_search)
            images = [i for i in images if i.get("image_url")]
            if not images:
                return {"ok": False, "error": "no_images", "images": []}
            return {"ok": True, "images": images[: self.max_images]}
        except Exception as exc:
            logger.warning("image_search failed: %s", exc)
            return {"ok": False, "error": "image_search_failed", "images": []}


async def download_image(url: str, timeout: float = 15.0) -> bytes | None:
    if not url.startswith(("http://", "https://")):
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                return None
            data = resp.content
            if len(data) > MAX_IMAGE_BYTES:
                return None
            ctype = resp.headers.get("content-type", "")
            if "image" not in ctype and not url.lower().endswith(
                (".jpg", ".jpeg", ".png", ".webp", ".gif")
            ):
                return None
            return data
    except httpx.HTTPError:
        return None
